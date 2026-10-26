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

HERE = os.path.dirname(os.path.abspath(__file__))
GRAPH_DIR = os.path.join(HERE, "model_graphs")
GRAPH_FONT_PT = 15.0  # point size Morpheus writes for graph labels


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
    (and reduced="true"/"false") on a copy of the model and let the CLI write the dot file."""
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
    for el in root.iter():
        f = el.get("filename")
        if f and not os.path.exists(f) and f"/{run}/" in f:
            el.set("filename", os.path.join(run_dir, "agent_workspace", f.split(f"/{run}/", 1)[1]))
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


def clean_dot(src, dst):
    """Rendering copy of a committed graph: drop morph:// links, use an installed Times face."""
    txt = open(src, encoding="utf-8").read()
    txt = re.sub(r',?\s*URL="[^"]*"', "", txt)
    txt = txt.replace('face="times"', 'face="Times New Roman"')
    txt = txt.replace("digraph {", 'digraph {\nnode[fontname="Times New Roman"];edge[fontname="Times New Roman"];graph[fontname="Times New Roman"];', 1)
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
        full = os.path.join(GRAPH_DIR, f"{key}.dot")
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
        red = os.path.join(GRAPH_DIR, f"{self.key}_reduced.dot")
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


def svg_inner(svg_path, prefix):
    """Graph content of a Graphviz SVG with ids made unique, for nesting into another SVG."""
    txt = open(svg_path, encoding="utf-8").read()
    body = txt[txt.index("<g id=\"graph0\""):txt.rindex("</svg>")]
    body = re.sub(r'id="([^"]+)"', lambda m: f'id="{prefix}{m.group(1)}"', body)
    body = re.sub(r"<title>.*?</title>", "", body, flags=re.S)
    return body
