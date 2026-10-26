"""Shared layout of one supplementary figure (180 x 185 mm):
a) original publication figure (crops of the paper PDF), b) agent output frames, c) model graph
(vector, wrapped into rows when wide), d) quantification drawn by panels/<paper>.py."""
import hashlib
import os
import re

import numpy as np
import pandas as pd
import pymupdf
from PIL import Image
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

import config
import paper_data
import style
import graphs
from graphs import Graph, svg_inner
from style import MM, FIG_W, FIG_H

HERE = os.path.dirname(os.path.abspath(__file__))
PT = 72 / 25.4  # pt per mm
HEAD = 4.2  # mm, panel heading line
GAP = 2.6  # mm between panels
LAB = 2.8  # mm, label line above a sub-image
INDENT = 3.5  # mm, content indent from the panel letter
MAX_GRAPH_TEXT = 6.5  # pt; panel c is not enlarged beyond this label size


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


class Ctx:
    """Inputs of one figure; every file read through it is recorded for sources.csv."""

    def __init__(self, key, runs, repo, work):
        self.key = key
        self.run, self.mode, self.rep, self.score = config.RUNS[key]
        self.run_dir = os.path.join(runs, self.run)
        self.att = os.path.join(self.run_dir, config.ATTEMPT)
        self.repo, self.work = repo, work
        self.inputs = []  # (role, path)
        self.notes = []  # caption sentences about panel d
        self.missing = []  # agent-only quantities the run did not log
        self.add("scored model", os.path.join(self.att, "model.xml"))

    def add(self, role, path):
        if (role, path) not in self.inputs:
            self.inputs.append((role, path))
        return path

    def attempt(self, name, role="panel d data"):
        return self.add(role, os.path.join(self.att, name))

    def csv(self, name, **kw):
        return pd.read_csv(self.attempt(name), **kw)

    def paper(self, rel):
        self.add("paper data", os.path.join(HERE, "paper_data", rel))
        df, notes = paper_data.load(rel)
        self.notes += notes
        return df

    def note(self, s):
        self.notes.append(s)


# ---------------------------------------------------------------- packing of image rows

def rows_extent(rows, gap, lab):
    """rows: list of rows, each a list of (aspect w/h, has_label). The height of the packed block at
    width W is A*W + B; returns (A, B)."""
    A, B = 0.0, gap * (len(rows) - 1)
    for r in rows:
        A += 1.0 / sum(a for a, _ in r)
        B += -gap * (len(r) - 1) / sum(a for a, _ in r) + (lab if any(l for _, l in r) else 0.0)
    return A, B


def place_rows(rows, x, y, W, gap, lab):
    """Positions (x, y, w, h) in mm of every item, rows centred in width W."""
    out = []
    for r in rows:
        tot = sum(a for a, _ in r)
        h = (W - gap * (len(r) - 1)) / tot
        ly = lab if any(l for _, l in r) else 0.0
        xx = x
        for a, _ in r:
            out.append((xx, y + ly, a * h, h))
            xx += a * h + gap
        y += ly + h + gap
    return out


def width_for(ext, Wmax, Hmax):
    A, B = ext
    return max(5.0, min(Wmax, (Hmax - B) / A))


# ---------------------------------------------------------------- inputs of panels a and b

def panel_a_images(ctx):
    spec = config.PANEL_A[ctx.key]
    pdf = ctx.add("paper PDF (panel a)", os.path.join(ctx.repo, "benchmark_papers", f"{ctx.key}.pdf"))
    doc = pymupdf.open(pdf)
    ims = []
    for page, bb, lab in spec["crops"]:
        pix = doc[page].get_pixmap(dpi=600, clip=pymupdf.Rect(*bb))
        ims.append((np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[..., :3], lab))
    rows = [[ims[i] for i in r] for r in spec["rows"]]
    return rows


def load_frame(ctx, f):
    if ctx.key == "04_Atwell2025":
        path = os.path.join(ctx.work, "atwell3d", "png", f"atwell_3d_{f}hph.png")
        ctx.add("panel b frame (3D render of the run's checkpoints)", path)
    else:
        path = ctx.attempt(f, role="panel b frame")
    im = Image.open(path).convert("RGB")
    if ctx.key in config.FRAME_CROP:
        x0, x1, y0, y1 = (tuple(config.FRAME_CROP[ctx.key]) + (0.0, 1.0))[:4]
        im = im.crop((int(x0 * im.width), int(y0 * im.height), int(x1 * im.width), int(y1 * im.height)))
    return np.asarray(im)


def panel_b_images(ctx):
    frames = config.ATWELL_FRAMES if ctx.key == "04_Atwell2025" else config.FRAMES[ctx.key]
    ims = [(load_frame(ctx, f), lab) for f, lab in frames]
    n = config.FRAME_COLS.get(ctx.key, len(ims))
    return [ims[i:i + n] for i in range(0, len(ims), n)]


def aspects(rows):
    return [[(im.shape[1] / im.shape[0], bool(lab)) for im, lab in r] for r in rows]


# ---------------------------------------------------------------- drawing helpers

def mm_axes(fig, x, y, w, h, **kw):
    """Axes at (x, y) mm from the top-left corner with size w x h mm."""
    return fig.add_axes([x / FIG_W, 1 - (y + h) / FIG_H, w / FIG_W, h / FIG_H], **kw)


def text(fig, x, y, s, **kw):
    kw.setdefault("fontsize", style.FS)
    kw.setdefault("va", "top")
    return fig.text(x / FIG_W, 1 - y / FIG_H, s, **kw)


def heading(fig, x, y, letter, s=""):
    text(fig, x, y - 0.35, letter, fontsize=style.FS_LETTER, fontweight="bold")
    if s:
        text(fig, x + INDENT, y, s, fontsize=style.FS)


def sub_letter(fig, x, y, s):
    text(fig, x, y, s, fontsize=style.FS, fontweight="bold")


def draw_images(fig, rows, pos, lab_fs=style.FS_SMALL, frame=False):
    flat = [it for r in rows for it in r]
    for (im, lab), (x, y, w, h) in zip(flat, pos):
        ax = mm_axes(fig, x, y, w, h)
        ax.imshow(im, interpolation="none", aspect="auto")
        ax.set_axis_off()
        if frame:
            ax.add_patch(Rectangle((0, 0), 1, 1, transform=ax.transAxes, fill=False, lw=0.4, ec="0.6"))
        if lab:
            text(fig, x + w / 2, y - LAB + 0.2, lab, fontsize=lab_fs, ha="center")


def legend_row(fig, x, y, W, items):
    """Single-row colour key centred in width W."""
    fs = style.FS_SMALL
    widths = [2.6 + 0.9 + 0.62 * fs * 0.3528 * len(lab) for _, lab in items]
    tot = sum(widths) + 2.5 * (len(items) - 1)
    xx = x + (W - tot) / 2
    for (c, lab), w in zip(items, widths):
        fig.patches.append(Rectangle((xx / FIG_W, 1 - (y + 2.2) / FIG_H), 2.6 / FIG_W, 1.8 / FIG_H,
                                     transform=fig.transFigure, fc=c, ec="0.3", lw=0.3))
        text(fig, xx + 3.5, y + 0.1, lab, fontsize=fs)
        xx += w + 2.5


# ---------------------------------------------------------------- the figure

def graph_plan(graph, W, Hmax, gap=1.6, kmax=4, max_text_pt=None, **cut):
    """Rows k and scale (mm per pt) that make the graph largest within W x Hmax (and, optionally, no larger
    than needed for labels of max_text_pt). cut: options of Graph.slices."""
    best = None
    for k in range(1, kmax + 1):
        sl = graph.slices(k, **cut) if k > 1 else [(0.0, graph.w)]
        mw = max(b - a for a, b in sl)
        s = min(W / (mw / PT), (Hmax - gap * (k - 1)) / (k * graph.h / PT)) / PT  # mm per pt
        if max_text_pt:
            s = min(s, max_text_pt / (graphs.GRAPH_FONT_PT * PT))
        if best is None or s > best[1] * 1.08:
            best = (k, s, sl)
    return best


def build(key, mod, ctx, out_base, log=print):
    style.apply()
    fig = plt.figure(figsize=(FIG_W * MM, FIG_H * MM))
    W = FIG_W - INDENT - 1.0

    # c) graph: decide reduced/full and its size first
    graph = Graph(key, os.path.join(ctx.work, "graphs"))
    for p in graph.sources:
        ctx.add("model graph (dot)", p)
    gnote = []
    d_h = getattr(mod, "D_HEIGHT", 46.0)
    c_max = getattr(mod, "GRAPH_MAX_H", 46.0)
    if graph.w / graph.h > config.GRAPH_REDUCE_ASPECT:
        s_full = graph_plan(graph, W, c_max)[1]
        if graph.use_reduced():
            if graph_plan(graph, W, c_max)[1] > s_full:  # keep the reduced graph only if it prints larger
                ctx.add("model graph (dot)", graph.sources[-1])
                gnote.append("reduced graph")
            else:
                graph = Graph(key, os.path.join(ctx.work, "graphs"))
        else:
            ctx.note("The reduced model graph could not be laid out by Graphviz dot (error 'trouble in "
                     "init_rank'), so panel c shows the full graph.")
    k, s, sl = graph_plan(graph, W, c_max, max_text_pt=MAX_GRAPH_TEXT)
    c_h = k * graph.h * s + 1.6 * (k - 1)

    # a) and b)
    spec = config.PANEL_A[key]
    ra = panel_a_images(ctx)
    rb = panel_b_images(ctx)
    b_leg = getattr(mod, "B_LEGEND", None)
    leg_h = 3.4 if b_leg else 0.0
    ea = rows_extent(aspects(ra), 1.8, LAB)
    eb = rows_extent(aspects(rb), 1.8, LAB)
    eb = (eb[0], eb[1] + leg_h)
    avail = FIG_H - 1.2 - (d_h + HEAD) - (c_h + HEAD) - 2 * GAP

    def stacked():
        # image heights split 40:60 between a and b (optimum of the layout score below), widths capped at W
        H = avail - (ea[1] + eb[1] + 2 * HEAD + GAP)
        fa = getattr(mod, "A_SHARE", 0.4)
        wa, wb = fa * H / ea[0], (1 - fa) * H / eb[0]
        if wa > W:
            wa, wb = W, (H - ea[0] * W) / eb[0]
        if wb > W:
            wb, wa = W, min(W, (H - eb[0] * W) / ea[0])
        wa, wb = max(5.0, min(wa, W)), max(5.0, min(wb, W))
        return dict(kind="stacked", wa=wa, wb=wb, ha=ea[0] * wa + ea[1], hb=eb[0] * wb + eb[1])

    def side():
        g = 4.0
        # equal heights: Aa*wa + Ba = Ab*wb + Bb, wa + wb = W - g
        wa = (eb[0] * (W - g) + eb[1] - ea[1]) / (ea[0] + eb[0])
        wa = min(max(wa, 20.0), W - g - 20.0)
        wb = W - g - wa
        h = max(ea[0] * wa + ea[1], eb[0] * wb + eb[1])
        if h > avail - HEAD:
            f = (avail - HEAD - max(ea[1], eb[1])) / (h - max(ea[1], eb[1]))
            wa, wb = wa * f, wb * f
        L = dict(kind="side", wa=wa, wb=wb, ha=ea[0] * wa + ea[1], hb=eb[0] * wb + eb[1])
        # the panel-a heading must fit above panel a (about 1.1 mm per character at 6 pt)
        L["fits"] = INDENT + 1.1 * len(spec["title"]) < wa + 4.0
        return L

    def area(L):  # weighted geometric mean of the image areas of a and b (b, the agent output, counts more)
        if not L.get("fits", True):
            return 0.0
        return (max(L["ha"] - ea[1], 0) * L["wa"]) ** 0.4 * (max(L["hb"] - eb[1], 0) * L["wb"]) ** 0.6

    forced = getattr(mod, "AB_LAYOUT", None)
    L = {"stacked": stacked, "side": side}[forced]() if forced else max((stacked(), side()), key=area)
    used = (L["ha"] + L["hb"] + 2 * HEAD + GAP) if L["kind"] == "stacked" else max(L["ha"], L["hb"]) + HEAD
    spare = max(0.0, avail - used)
    # give spare height to the graph (if its height limits it) and the rest to panel d
    k2, s2, sl2 = graph_plan(graph, W, c_h + spare, max_text_pt=MAX_GRAPH_TEXT)
    c_h2 = k2 * graph.h * s2 + 1.6 * (k2 - 1)
    if s2 > s * 1.02:
        k, s, sl, spare = k2, s2, sl2, spare - (c_h2 - c_h)
        c_h = c_h2
    d_h += max(0.0, spare)

    y = 1.2
    btitle = f"Agent reimplementation ({config.MODEL}, {config.MODE_LABEL[ctx.mode]}; score {ctx.score:.2f})"
    if L["kind"] == "stacked":
        heading(fig, 0, y, "a", spec["title"])
        draw_images(fig, ra, place_rows(aspects(ra), INDENT + (W - L["wa"]) / 2, y + HEAD, L["wa"], 1.8, LAB))
        y += HEAD + L["ha"] + GAP
        heading(fig, 0, y, "b", btitle)
        hb = L["hb"] - leg_h
        draw_images(fig, rb, place_rows(aspects(rb), INDENT + (W - L["wb"]) / 2, y + HEAD, L["wb"], 1.8, LAB))
        if b_leg:
            legend_row(fig, INDENT, y + HEAD + hb + 0.6, W, b_leg)
        y += HEAD + L["hb"] + GAP
    else:
        heading(fig, 0, y, "a", spec["title"])
        draw_images(fig, ra, place_rows(aspects(ra), INDENT, y + HEAD, L["wa"], 1.8, LAB))
        xb = INDENT + L["wa"] + 4.0
        heading(fig, xb - INDENT, y, "b", btitle)
        hb = L["hb"] - leg_h
        draw_images(fig, rb, place_rows(aspects(rb), xb + (FIG_W - xb - L["wb"]) / 2, y + HEAD, L["wb"], 1.8, LAB))
        if b_leg:
            legend_row(fig, xb, y + HEAD + hb + 0.6, FIG_W - xb, b_leg)
        y += HEAD + max(L["ha"], L["hb"]) + GAP

    # c)
    text_pt = graphs.GRAPH_FONT_PT * s * PT  # printed size of the graph's labels
    if k > 1:
        gnote.append(f"wrapped into {k} rows")
    if text_pt < config.GRAPH_MIN_TEXT_PT:
        gnote.append("full size: Supplementary Fig. model graphs")
    heading(fig, 0, y, "c", "Morpheus model graph" + (f" ({'; '.join(gnote)})" if gnote else ""))
    yc = y + HEAD
    slots = []
    for i, (a, b) in enumerate(sl):
        w_mm, h_mm = (b - a) * s, graph.h * s
        x = INDENT + (W - w_mm) / 2 if k == 1 else INDENT
        slots.append(((a, b), (x, yc, w_mm, h_mm)))
        if i < k - 1:
            text(fig, INDENT + w_mm + 0.5, yc + h_mm - 2.2, "…", fontsize=style.FS, color="0.45")
        yc += h_mm + 1.6
    y += HEAD + c_h + GAP

    # d)
    heading(fig, 0, y, "d")
    mod.draw(ctx, fig, (INDENT, y + 0.6, W, FIG_H - y - 0.6))

    svg, pdf, png = out_base + ".svg", out_base + ".pdf", out_base + ".png"
    fig.savefig(svg)
    fig.savefig(pdf)
    plt.close(fig)
    insert_graph_svg(svg, graph, slots)
    insert_graph_pdf(pdf, graph, slots)
    d = pymupdf.open(pdf)
    d[0].get_pixmap(dpi=600).save(png)
    log(f"  layout {L['kind']}, graph {'reduced' if graph.reduced else 'full'} in {k} row(s), "
        f"graph text {text_pt:.1f} pt, panel d height {d_h:.0f} mm")
    return dict(graph=graph, graph_rows=k, graph_text_pt=text_pt, graph_note=gnote, layout=L["kind"])


def insert_graph_svg(svg, graph, slots):
    txt = open(svg, encoding="utf-8").read()
    parts = []
    for i, ((a, b), (x, y, w, h)) in enumerate(slots):
        parts.append(f'<svg x="{x * PT:.3f}" y="{y * PT:.3f}" width="{w * PT:.3f}" height="{h * PT:.3f}" '
                     f'viewBox="{a:.3f} 0 {b - a:.3f} {graph.h:.3f}" preserveAspectRatio="none" overflow="hidden">'
                     + svg_inner(graph.svg, f"g{i}_") + "</svg>")
    i = txt.rindex("</svg>")
    open(svg, "w", encoding="utf-8").write(txt[:i] + "\n".join(parts) + txt[i:])


def insert_graph_pdf(pdf, graph, slots):
    doc = pymupdf.open(pdf)
    src = pymupdf.open(graph.pdf)
    # dot pads its pdf page by a margin that the svg viewBox does not have
    mx = (src[0].rect.width - graph.w) / 2
    my = (src[0].rect.height - graph.h) / 2
    for (a, b), (x, y, w, h) in slots:
        clip = pymupdf.Rect(mx + a, my, mx + b, my + graph.h)
        doc[0].show_pdf_page(pymupdf.Rect(x * PT, y * PT, (x + w) * PT, (y + h) * PT), src, 0, clip=clip,
                             keep_proportion=False)
    doc.save(pdf + ".tmp", garbage=3, deflate=True)
    doc.close()
    os.replace(pdf + ".tmp", pdf)
