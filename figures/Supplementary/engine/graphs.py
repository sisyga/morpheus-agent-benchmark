"""Morpheus model graphs: generation (Morpheus CLI), rendering with Graphviz, and the slices
in which a wide graph is wrapped into several rows of panel c."""
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image

import config

HERE = os.path.dirname(os.path.abspath(__file__))
DOT_OVERRIDE = {}  # file name -> path of a dot file used instead of model_graphs/<name> (build_all --from-scratch)


def dot_path(name):
    """The dot file of a model graph: model_graph/<name> in its figure folder, or its regenerated replacement."""
    return DOT_OVERRIDE.get(name, committed(name))


def committed(name):
    """The committed dot file <key>.dot or <key>_reduced.dot in the figure folder of <key>."""
    return os.path.join(config.fig_dir(name[:-4].removesuffix("_reduced")), "model_graph", name)


def _canonical(path):
    """Lines of a dot file as a set, without the morph:// URL attributes; an edge drawn to a cluster (lhead=...)
    is written with the cluster as its target, since Morpheus picks an arbitrary member node of the cluster."""
    out = set()
    for ln in open(path, encoding="utf-8").read().splitlines():
        ln = re.sub(r',?\s*URL="[^"]*"', "", ln)
        m = re.match(r'(\s*\S+ -> )\S+( \[.*lhead=(cluster\w+).*)', ln)
        out.add(m.group(1) + m.group(3) + m.group(2) if m else ln)
    return out


def regenerate(key, model_xml, work, morpheus):
    """Regenerate the full and reduced graph of a model with the Morpheus CLI into work and compare each with the
    committed file. Morpheus writes the lines in a varying order and, in reduced mode, may drop a repeated definition
    of a merged node, number its morph:// link differently or draw a cluster edge to another member node, so the
    comparison is of the sets of lines without the URL attributes (which clean_dot removes before layout) and with
    cluster edges pointing at their cluster: if equal, the committed file (same graph, fixed
    order) stays in use; otherwise the regenerated file replaces it (DOT_OVERRIDE). Returns ([(name, regenerated path, 'identical up to line order' | 'differs, regenerated
    used')], [input files the model reads])."""
    os.makedirs(work, exist_ok=True)
    out, used = [], set()
    for reduced in (False, True):
        name = f"{key}_reduced.dot" if reduced else f"{key}.dot"
        dst = os.path.join(work, name)
        used |= set(generate_dot(model_xml, dst, morpheus, reduced=reduced))
        ref = committed(name)
        same = os.path.exists(ref) and _canonical(dst) == _canonical(ref)
        if not same:
            DOT_OVERRIDE[name] = dst
        out.append((name, dst, "same graph (lines as a set, links ignored)" if same else "differs, regenerated used"))
    return out, sorted(used)
GRAPH_FONT_PT = 15.0  # point size Morpheus writes for graph labels
GRAPH_FONT = "Arial"  # the figures' face; Graphviz's cairo backend resolves it on Windows (Times New Roman fell back to DejaVu)


def find_morpheus():
    for name in ("morpheus", "morpheus.exe"):
        p = shutil.which(name)
        if p:
            return p
    for p in (r"C:\Program Files\Morpheus\morpheus.exe", r"E:\Program Files\Morpheus\morpheus.exe"):
        if os.path.exists(p):
            return p
    return None


def generate_dot(model_xml, dst, morpheus, reduced=False):
    """Morpheus 2.4.1 writes an empty graph unless <ModelGraph include-tags="#untagged"/> is set; set it
    (and reduced="true"/"false") on a copy of the model and let the CLI write the dot file. Returns the input
    files the model reads (e.g. a TIFFReader image), as found in the run folder."""
    tree = ET.parse(model_xml)
    root = tree.getroot()
    analysis = root.find("Analysis")
    if analysis is None:
        analysis = ET.SubElement(root, "Analysis")
    mg = analysis.find("ModelGraph")
    if mg is None:
        mg = ET.SubElement(analysis, "ModelGraph", {"format": "dot", "reduced": "false"})
    mg.set("include-tags", "#untagged")
    mg.set("reduced", "true" if reduced else "false")
    # input files (e.g. TIFFReader) point into the agent's sandbox; map them to the run's agent_workspace
    run_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(model_xml))))
    run = os.path.basename(run_dir)
    used = []
    for el in root.iter():
        f = el.get("filename")
        if f and not os.path.exists(f) and f"/{run}/" in f:
            el.set("filename", os.path.join(run_dir, "agent_workspace", f.split(f"/{run}/", 1)[1]))
        if f and el.tag.endswith("Reader"):
            used.append(el.get("filename"))
    with tempfile.TemporaryDirectory() as tmp:
        m = os.path.join(tmp, "model.xml")
        tree.write(m, encoding="utf-8", xml_declaration=True)
        # Morpheus 2.4.1 on Windows exits with a heap error after writing the graph, so the exit code
        # is not checked; the written file is
        r = subprocess.run([morpheus, "-f", m, "--model-graph=dot", "--outdir", os.path.join(tmp, "out")],
                           cwd=tmp, capture_output=True, text=True, timeout=600)
        out = os.path.join(tmp, "out", "model_graph.dot")
        if "Generated symbol dependency graph" not in r.stdout or not os.path.exists(out):
            raise RuntimeError(f"Morpheus wrote no model graph for {model_xml}:\n{r.stdout[-2000:]}{r.stderr[-2000:]}")
        shutil.copyfile(out, dst)
    return used


def clean_dot(src, dst):
    """Rendering copy of a committed graph: drop morph:// links, set every label in GRAPH_FONT (Arial, as the
    figures) instead of the Times face Morpheus writes."""
    txt = open(src, encoding="utf-8").read()
    txt = re.sub(r',?\s*URL="[^"]*"', "", txt)
    txt = txt.replace('face="times"', f'face="{GRAPH_FONT}"')
    txt = txt.replace("digraph {", f'digraph {{\nnode[fontname="{GRAPH_FONT}"];edge[fontname="{GRAPH_FONT}"];'
                      f'graph[fontname="{GRAPH_FONT}"];', 1)
    open(dst, "w", encoding="utf-8").write(txt)


def run_dot(dot, fmt, out, extra=()):
    cmd = ["dot", f"-T{fmt}", *extra, dot, "-o", out]
    r = subprocess.run(cmd, capture_output=True, timeout=900)
    if r.returncode:  # dot occasionally loses a flat edge next to a record node; newrank avoids it
        subprocess.run(["dot", f"-T{fmt}", "-Gnewrank=true", *extra, dot, "-o", out],
                       check=True, capture_output=True, timeout=900)


class Graph:
    """A rendered graph (svg + pdf + raster), sizes in pt."""

    def __init__(self, key, work):
        self.key = key
        full = dot_path(f"{key}.dot")
        self.sources = [full]
        self.reduced = False
        os.makedirs(work, exist_ok=True)
        self.work = work
        w, h = self._render(full, "full")
        self.full_size = (w, h)
        self.full_svg = self.svg

    def _render(self, src, tag):
        dot = os.path.join(self.work, f"{self.key}_{tag}.dot")
        clean_dot(src, dot)
        self.svg = os.path.join(self.work, f"{self.key}_{tag}.svg")
        self.pdf = os.path.join(self.work, f"{self.key}_{tag}.pdf")
        self.png = os.path.join(self.work, f"{self.key}_{tag}.png")
        run_dot(dot, "svg", self.svg)
        run_dot(dot, "pdf", self.pdf)
        run_dot(dot, "png", self.png, ["-Gdpi=36"])
        vb = re.search(r'viewBox="([\d.\s-]+)"', open(self.svg, encoding="utf-8").read()).group(1).split()
        self.w, self.h = float(vb[2]), float(vb[3])
        return self.w, self.h

    def use_reduced(self):
        """Switch to the reduced graph; returns False (keeping the full graph) if Graphviz cannot lay it out."""
        red = dot_path(f"{self.key}_reduced.dot")
        full = (self.svg, self.pdf, self.png, self.w, self.h)
        try:
            self._render(red, "reduced")
        except subprocess.CalledProcessError:
            self.svg, self.pdf, self.png, self.w, self.h = full
            return False
        self.sources.append(red)
        self.reduced = True
        return True

    def slices(self, k, window=0.06, any_ink=False):
        """Cut the graph into k vertical strips at the columns with the least ink (so nodes are rarely
        split), searching +-window/k of the graph width around each even cut; returns [(x0, x1)] in pt.
        any_ink counts every pixel that is not background (white or a cluster fill: colours covering > 1 % of
        the image), so antialiased label text is not cut either."""
        if k == 1:
            return [(0.0, self.w)]
        im = np.asarray(Image.open(self.png).convert("RGB")).astype(int)
        if any_ink:
            code = (im[..., 0] << 16) | (im[..., 1] << 8) | im[..., 2]
            cols, n = np.unique(code, return_counts=True)
            ink = (~np.isin(code, cols[n > 0.01 * code.size])).sum(0)
        else:
            ink = ((np.abs(im[..., 0] - im[..., 2]) > 60) | (im.sum(-1) < 200)).sum(0)
        px = im.shape[1] / self.w
        cuts = [0.0]
        for i in range(1, k):
            c = int(im.shape[1] * i / k)
            r = int(im.shape[1] * window / k)
            win = ink[c - r:c + r]
            best = np.flatnonzero(win == win.min())  # least ink; of equal columns the one nearest c
            cuts.append((c - r + int(best[np.argmin(np.abs(best - r))])) / px)
        cuts.append(self.w)
        return list(zip(cuts[:-1], cuts[1:]))


def counts(svg_path):
    """(nodes, edges) of a Graphviz SVG as laid out (nodes with the same id are one node)."""
    txt = open(svg_path, encoding="utf-8").read()
    return len(re.findall(r'<g id="[^"]*" class="node"', txt)), len(re.findall(r'<g id="[^"]*" class="edge"', txt))


def svg_inner(svg_path, prefix):
    """Graph content of a Graphviz SVG with ids made unique, for nesting into another SVG."""
    txt = open(svg_path, encoding="utf-8").read()
    body = txt[txt.index("<g id=\"graph0\""):txt.rindex("</svg>")]
    body = re.sub(r'id="([^"]+)"', lambda m: f'id="{prefix}{m.group(1)}"', body)
    body = re.sub(r"<title>.*?</title>", "", body, flags=re.S)
    return body
