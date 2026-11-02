"""Shared layout of one supplementary figure (180 x 170 mm):
a) original publication figure (crops of the paper PDF), b) agent output frames, c) model graph
(vector, wrapped into rows when wide), d) quantification drawn by panels/<paper>.py."""
import hashlib
import io
import os

import numpy as np
import pandas as pd
import pymupdf
from PIL import Image
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Rectangle
from matplotlib.textpath import TextToPath

import config
import paper_data
import style
import graphs
from graphs import Graph, svg_inner
from style import MM, FIG_W, FIG_H

HERE = os.path.dirname(os.path.abspath(__file__))
_TEXT_TO_PATH = TextToPath()
PT = 72 / 25.4  # pt per mm
HEAD = 0.0  # mm above a panel's content: the bold letter sits in the indent column, its top on the panel's top edge
TOP, LEFT = 1.2, 1.0  # mm, page margins above and left of the layout, so no letter touches the page edge (right: 1.0)
GAP = 3.0  # mm between panels
LAB = 3.0  # mm, label line above a sub-image (6 pt)
INDENT = 3.5  # mm, content indent from the panel letter
MAX_GRAPH_TEXT = 6.5  # pt; panel c is not enlarged beyond this label size
MIN_FILL = 0.75  # wrapped rows of the reduced graph span at least this fraction of the width (Atwell 0.81 kept, Scheel 0.56 not)
SUMMARY_DIR = "figure_data"  # per attempt: small tables summarising large run outputs (Ctx.summary)
SUMMARISED = "large output, not published; summarised in figure_data/"
SPARE_MM = 8.0  # a reduced graph that leaves more than this unused below panel c triggers a new layout


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
        self.summary_dir = os.path.join(self.att, SUMMARY_DIR)  # summaries of large outputs, see summary()
        self.summarising = None  # name of the summary being computed; its raw inputs are not published
        self.inputs = []  # (role, path)
        self.summaries = {}  # name -> table computed from a large output in this build
        self.notes = []  # caption sentences about panel d
        self.fmt = {}  # values a panel module fills into its CAPTION ("{name}" fields), e.g. data ranges
        self.missing = []  # agent-only quantities the run did not log
        self.add("scored model", os.path.join(self.att, "model.xml"))

    def add(self, role, path):
        if self.summarising:
            role = f"{SUMMARISED} {self.summarising}.csv ({role})"
        if (role, path) not in self.inputs:
            self.inputs.append((role, path))
        return path

    def summary(self, name, compute):
        """The small table a panel draws from a large run output (e.g. Szabo's 131 MB track log). With the full
        benchmark run, compute() reads the output and the table is also written to <out>/<paper>/figure_data/<name>.csv;
        in the figure folders' data/ only that table exists and is read back. Floats are written with repr and read with round_trip precision, so both give the same
        figure."""
        path = os.path.join(self.summary_dir, name + ".csv")
        if os.path.exists(path):
            return pd.read_csv(self.add(f"summary of a large run output ({name})", path),
                               float_precision="round_trip")
        self.summarising = name
        try:
            df = compute()
        finally:
            self.summarising = None
        self.summaries[name] = df
        return pd.read_csv(io.StringIO(df.to_csv(index=False)), float_precision="round_trip")

    def attempt(self, name, role="panel d data"):
        return self.add(role, os.path.join(self.att, name))

    def csv(self, name, **kw):
        return pd.read_csv(self.attempt(name), **kw)

    def paper(self, rel):
        self.add("paper data", paper_data.path(rel))
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
    pdf = ctx.add("paper PDF (panel a)", os.path.join(ctx.repo, spec.get("pdf", f"benchmark_papers/{ctx.key}.pdf")))
    doc = pymupdf.open(pdf)
    ims = []
    for page, bb, _ in spec["crops"]:  # the crops' figure numbers are named in the caption, not drawn
        pix = doc[page].get_pixmap(dpi=600, clip=pymupdf.Rect(*bb))
        ims.append((np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[..., :3], ""))
    rows = [[ims[i] for i in r] for r in spec["rows"]]
    if spec.get("same_scale"):  # crops of a row print at the same scale as the PDF: pad to the tallest, centred
        for r in rows:
            hmax = max(im.shape[0] for im, _ in r)
            for j, (im, lab) in enumerate(r):
                pad = hmax - im.shape[0]
                r[j] = (np.pad(im, ((pad // 2, pad - pad // 2), (0, 0), (0, 0)), constant_values=255), lab)
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
    if ctx.key in config.FRAME_CROP_PX:
        x0, x1, y0, y1 = config.FRAME_CROP_PX[ctx.key]
        im = im.crop((x0, y0, x1, y1))
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


def heading(fig, x, y, letter):
    """Bold panel letter; the top of the glyph on the panel's top edge y. Matplotlib's text box (va="top") starts at
    the ink top of "lp", i.e. the ascender of b, d, l (Arial 0.716 em, as the capitals), not at the font's ascent."""
    text(fig, x, y, letter, fontsize=style.FS_LETTER, fontweight="bold")


def draw_images(fig, rows, pos, lab_fs=style.FS, frame=False, images=True):
    """Images at their positions with their labels above; images=False draws only the labels (frames that a
    panel module draws itself, B_DRAW_IMAGES = False)."""
    flat = [it for r in rows for it in r]
    for (im, lab), (x, y, w, h) in zip(flat, pos):
        if lab:
            text(fig, x + w / 2, y - LAB + 0.2, lab, fontsize=lab_fs, ha="center")
        if not images:
            continue
        ax = mm_axes(fig, x, y, w, h)
        ax.imshow(im, interpolation="none", aspect="auto")
        ax.set_axis_off()
        if frame:
            ax.add_patch(Rectangle((0, 0), 1, 1, transform=ax.transAxes, fill=False, lw=0.5, ec="0.5"))


def text_width_mm(s, fontsize=style.FS):
    """Printed width (mm) of a text from the font's advance widths (as in the SVG/PDF; Agg measures hinted text at
    the screen dpi, about 9 % narrower). Mathtext ($...$) is laid out as matplotlib does."""
    prop = FontProperties(family=plt.rcParams["font.family"], size=fontsize)
    w, _, _ = _TEXT_TO_PATH.get_text_width_height_descent(s, prop, ismath="$" in s)
    return w * 25.4 / 72


def key_rows(fig, x0, x1, y, rows, align=False, row_h=3.2, pw=2.6, gap_t=0.9, gap=2.5):
    """Colour key of patches (rows of (colour, label)) centred between x0 and x1 (mm), first row at y; align: the
    columns of all rows aligned (each column as wide as its widest entry), otherwise each row centred."""
    w = [[pw + gap_t + text_width_mm(lab) for _, lab in row] for row in rows]
    if align:
        cw = [max(r[j] for r in w if j < len(r)) for j in range(max(map(len, w)))]
        w = [cw[:len(r)] for r in w]
    for i, row in enumerate(rows):
        tot = (sum(w[0]) + gap * (len(w[0]) - 1)) if align else (sum(w[i]) + gap * (len(w[i]) - 1))
        xx, yy = (x0 + x1) / 2 - tot / 2, y + row_h * i
        for (c, lab), wi in zip(row, w[i]):
            fig.patches.append(Rectangle((xx / FIG_W, 1 - (yy + 2.1) / FIG_H), pw / FIG_W, 1.8 / FIG_H,
                                         transform=fig.transFigure, fc=c, ec="0.3", lw=0.3))
            text(fig, xx + pw + gap_t, yy, lab, fontsize=style.FS)
            xx += wi + gap


def legend_row(fig, x, y, W, items):
    """Single-row colour key centred in width W."""
    fs = style.FS
    widths = [2.6 + 0.9 + 0.62 * fs * 0.3528 * len(lab) for _, lab in items]
    tot = sum(widths) + 2.5 * (len(items) - 1)
    xx = x + (W - tot) / 2
    for (c, lab), w in zip(items, widths):
        fig.patches.append(Rectangle((xx / FIG_W, 1 - (y + 2.2) / FIG_H), 2.6 / FIG_W, 1.8 / FIG_H,
                                     transform=fig.transFigure, fc=c, ec="0.3", lw=0.3))
        text(fig, xx + 3.5, y + 0.1, lab, fontsize=fs)
        xx += w + 2.5


# ---------------------------------------------------------------- the figure

def graph_plan(graph, W, Hmax, gap=1.6, kmax=4, max_text_pt=None, min_fill=None, **cut):
    """Rows k and scale (mm per pt) that make the graph largest within W x Hmax (and, optionally, no larger
    than needed for labels of max_text_pt). min_fill: wrapped rows (k > 1) must span at least this fraction of
    W, so a height-limited graph is not wrapped into short rows that leave the page half empty.
    cut: options of Graph.slices."""
    best = None
    for k in range(1, kmax + 1):
        sl = graph.slices(k, **cut) if k > 1 else [(0.0, graph.w)]
        mw = max(b - a for a, b in sl)
        s = min(W / (mw / PT), (Hmax - gap * (k - 1)) / (k * graph.h / PT)) / PT  # mm per pt
        if max_text_pt:
            s = min(s, max_text_pt / (graphs.GRAPH_FONT_PT * PT))
        if k > 1 and min_fill and mw * s < min_fill * W:
            continue
        if best is None or s > best[1] * 1.08:
            best = (k, s, sl)
    return best


def build(key, mod, ctx, out_base, log=print):
    style.apply()
    fig = plt.figure(figsize=(FIG_W * MM, FIG_H * MM))
    X0 = LEFT + INDENT  # left edge of the panels' content; the letters sit at LEFT
    W = FIG_W - X0 - 1.0
    Wg = W - 2.5  # graph rows leave room for the 6 pt "…" that marks a wrapped row

    # c) graph: decide reduced/full and its size first
    graph = Graph(key, os.path.join(ctx.work, "graphs"))
    for p in graph.sources:
        ctx.add("model graph (dot)", p)
    gnote = []
    d_h = getattr(mod, "D_HEIGHT", 46.0)
    c_max = getattr(mod, "GRAPH_MAX_H", 46.0)
    if graph.w / graph.h > config.GRAPH_REDUCE_ASPECT:
        s_full = graph_plan(graph, Wg, c_max)[1]
        if graph.use_reduced():
            if graph_plan(graph, Wg, c_max)[1] > s_full:  # keep the reduced graph only if it prints larger
                ctx.add("model graph (dot)", graph.sources[-1])
                gnote.append("reduced graph")
            else:
                graph = Graph(key, os.path.join(ctx.work, "graphs"))
        else:
            ctx.note("The reduced model graph could not be laid out by Graphviz dot (error 'trouble in "
                     "init_rank'), so panel c shows the full graph.")
    # a) and b); without panel a (spec omit) the remaining panels are lettered a-c
    spec = config.PANEL_A[key]
    omit_a = spec.get("omit", False)
    lt = dict(zip("bcd", "abc")) if omit_a else dict(zip("bcd", "bcd"))
    ra = [] if omit_a else (mod.a_images(ctx) if hasattr(mod, "a_images") else panel_a_images(ctx))
    rb = mod.b_frames(ctx) if hasattr(mod, "b_frames") else panel_b_images(ctx)  # module may arrange its own frames
    b_leg = getattr(mod, "B_LEGEND", None)
    leg_h = 3.4 if b_leg else getattr(mod, "B_KEY_H", 0.0)  # mm below the frames: colour key or own key
    b_key = getattr(mod, "draw_b_key", None)  # mod.draw_b_key(fig, frame positions, y below the frames)
    draw_b = getattr(mod, "draw_b", None)  # mod.draw_b(ctx, fig, frame positions, y below the frames)
    b_images = getattr(mod, "B_DRAW_IMAGES", True)  # False: the frames only size the slots, draw_b draws them
    ea = rows_extent(aspects(ra), 1.8, LAB) if ra else (0.0, 0.0)
    eb = rows_extent(aspects(rb), 1.8, LAB)
    eb = (eb[0], eb[1] + leg_h)
    d_h0 = d_h

    def layout(graph, min_fill=None):
        """Panel sizes for this graph: (L, k, s, sl, c_h, d_h); spare height goes to the graph (if its height
        limits it) and the rest to panel d. min_fill: see graph_plan."""
        k, s, sl = graph_plan(graph, Wg, c_max, max_text_pt=MAX_GRAPH_TEXT, min_fill=min_fill)
        c_h = k * graph.h * s + 1.6 * (k - 1)
        avail = FIG_H - TOP - 1.2 - (d_h0 + HEAD) - (c_h + HEAD) - 2 * GAP

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
            g = getattr(mod, "AB_GAP", 4.0)
            # equal heights: Aa*wa + Ba = Ab*wb + Bb, wa + wb = W - g
            wa = (eb[0] * (W - g) + eb[1] - ea[1]) / (ea[0] + eb[0])
            wa = min(max(wa, 20.0), W - g - 20.0)
            wb = W - g - wa
            h = max(ea[0] * wa + ea[1], eb[0] * wb + eb[1])
            if h > avail - HEAD:
                f = (avail - HEAD - max(ea[1], eb[1])) / (h - max(ea[1], eb[1]))
                wa, wb = wa * f, wb * f
            return dict(kind="side", wa=wa, wb=wb, ha=ea[0] * wa + ea[1], hb=eb[0] * wb + eb[1])

        def area(L):  # weighted geometric mean of the image areas of a and b (b, the agent output, counts more)
            return (max(L["ha"] - ea[1], 0) * L["wa"]) ** 0.4 * (max(L["hb"] - eb[1], 0) * L["wb"]) ** 0.6

        def b_only():
            wb = max(5.0, min(W, (avail - HEAD - eb[1]) / eb[0]))
            return dict(kind="b_only", wa=0.0, wb=wb, ha=0.0, hb=eb[0] * wb + eb[1])

        forced = getattr(mod, "AB_LAYOUT", None)
        if omit_a:
            L = b_only()
        else:
            L = {"stacked": stacked, "side": side}[forced]() if forced else max((stacked(), side()), key=area)
        used = {"stacked": L["ha"] + L["hb"] + 2 * HEAD + GAP, "side": max(L["ha"], L["hb"]) + HEAD,
                "b_only": L["hb"] + HEAD}[L["kind"]]
        spare = max(0.0, avail - used)
        # give spare height to the graph (if its height limits it) and the rest to panel d
        k2, s2, sl2 = graph_plan(graph, Wg, c_h + spare, max_text_pt=MAX_GRAPH_TEXT, min_fill=min_fill)
        c_h2 = k2 * graph.h * s2 + 1.6 * (k2 - 1)
        if s2 > s * 1.02:
            k, s, sl, spare = k2, s2, sl2, spare - (c_h2 - c_h)
            c_h = c_h2
        return L, k, s, sl, c_h, d_h0 + max(0.0, spare)

    # Panel c shows Morpheus's reduced model graph (the full one is on its model-graph page). The layout
    # (graph chosen above) fixes the slot W x c_h; the reduced graph is scaled as large as that slot allows and
    # panels a, b and d keep their size. If that leaves more than SPARE_MM unused, the layout is redone for the
    # reduced graph, so the page is filled (a, b and d grow).
    L, k, s, sl, c_h, d_h = layout(graph)
    slot_h = c_h
    if not graph.reduced:
        if graph.use_reduced():
            ctx.add("model graph (dot)", graph.sources[-1])
        # else: Graphviz cannot lay out the reduced graph; panel c keeps the full one (build_all.caption says so)
    elif graph.sources[-1] not in [p for _, p in ctx.inputs]:
        ctx.add("model graph (dot)", graph.sources[-1])
    k, s, sl = graph_plan(graph, Wg, slot_h, max_text_pt=MAX_GRAPH_TEXT, min_fill=MIN_FILL)
    c_h = k * graph.h * s + 1.6 * (k - 1)
    if slot_h - c_h > SPARE_MM:
        L, k, s, sl, c_h, d_h = layout(graph, MIN_FILL)
        slot_h = c_h
    gnote = ["reduced graph"] if graph.reduced else []

    y = TOP
    if L["kind"] == "b_only":
        heading(fig, LEFT, y, lt["b"])
        hb = L["hb"] - leg_h
        pb = place_rows(aspects(rb), X0 + (W - L["wb"]) / 2, y + HEAD, L["wb"], 1.8, LAB)
        draw_images(fig, rb, pb, frame=ctx.key in config.FRAME_OUTLINE, images=b_images)
        if b_leg:
            legend_row(fig, X0, y + HEAD + hb + 0.6, W, b_leg)
        if b_key:
            b_key(fig, pb, y + HEAD + hb + 0.6)
        if draw_b:
            draw_b(ctx, fig, pb, y + HEAD + hb + 0.6)
        y += HEAD + L["hb"] + GAP
    elif L["kind"] == "stacked":
        heading(fig, LEFT, y, "a")
        draw_images(fig, ra, place_rows(aspects(ra), X0 + (W - L["wa"]) / 2, y + HEAD, L["wa"], 1.8, LAB))
        y += HEAD + L["ha"] + GAP
        heading(fig, LEFT, y, "b")
        hb = L["hb"] - leg_h
        pb = place_rows(aspects(rb), X0 + (W - L["wb"]) / 2, y + HEAD, L["wb"], 1.8, LAB)
        draw_images(fig, rb, pb, frame=ctx.key in config.FRAME_OUTLINE, images=b_images)
        if b_leg:
            legend_row(fig, X0, y + HEAD + hb + 0.6, W, b_leg)
        if b_key:
            b_key(fig, pb, y + HEAD + hb + 0.6)
        if draw_b:
            draw_b(ctx, fig, pb, y + HEAD + hb + 0.6)
        y += HEAD + L["hb"] + GAP
    else:
        heading(fig, LEFT, y, "a")
        draw_images(fig, ra, place_rows(aspects(ra), X0, y + HEAD, L["wa"], 1.8, LAB))
        xb = X0 + L["wa"] + getattr(mod, "AB_GAP", 4.0)
        heading(fig, xb - INDENT, y, "b")
        hb = L["hb"] - leg_h
        pb = place_rows(aspects(rb), xb + (FIG_W - 1.0 - xb - L["wb"]) / 2, y + HEAD, L["wb"], 1.8, LAB)
        draw_images(fig, rb, pb, frame=ctx.key in config.FRAME_OUTLINE, images=b_images)
        if b_leg:
            legend_row(fig, xb, y + HEAD + hb + 0.6, FIG_W - 1.0 - xb, b_leg)
        if b_key:
            b_key(fig, pb, y + HEAD + hb + 0.6)
        if draw_b:
            draw_b(ctx, fig, pb, y + HEAD + hb + 0.6)
        y += HEAD + max(L["ha"], L["hb"]) + GAP

    # c)
    text_pt = graphs.GRAPH_FONT_PT * s * PT  # printed size of the graph's labels
    if k > 1:
        gnote.append(f"wrapped into {k} rows")
    heading(fig, LEFT, y, lt["c"])
    yc = y + HEAD
    slots = []
    for i, (a, b) in enumerate(sl):
        w_mm, h_mm = (b - a) * s, graph.h * s
        x = X0 + ((W if k == 1 else Wg) - w_mm) / 2  # each row centred; wrapped rows in Wg, beside their "…"
        slots.append(((a, b), (x, yc, w_mm, h_mm)))
        if i < k - 1:
            text(fig, x + w_mm + 0.5, yc + h_mm - 2.2, "…", fontsize=style.FS)
        yc += h_mm + 1.6
    y += HEAD + c_h + GAP

    # d)
    heading(fig, LEFT, y, lt["d"])
    mod.draw(ctx, fig, (X0, y, W, FIG_H - y - max(0.0, slot_h - c_h)))  # below SPARE_MM: d keeps its height
    overlaps = text_overlaps(fig)
    leg_hits = legend_overlaps(fig)
    for desc, k in leg_hits:
        log(f"  legend overlaps data: {desc}: {k} element(s)")

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
    for o in overlaps:
        log("  text overlap: " + o)
    return dict(graph=graph, graph_rows=k, graph_text_pt=text_pt, graph_note=gnote, layout=L["kind"],
                counts_full=graphs.counts(graph.full_svg), counts_shown=graphs.counts(graph.svg),
                overlaps=overlaps, legend_hits=leg_hits)


def _texts(fig):
    """Every drawn, non-empty text of the figure (axes labels, tick labels, legends, colour bars, fig.text)."""
    out = list(fig.texts)
    for ax in fig.axes:
        if not ax.axison:  # image axes of panels a and b
            out += list(ax.texts)
            continue
        out += [ax.title, ax._left_title, ax._right_title, ax.xaxis.label, ax.yaxis.label] + list(ax.texts)
        for axis in (ax.xaxis, ax.yaxis):
            if not axis.get_visible():  # e.g. the shared x axis of a twinx
                continue
            for t in axis._update_ticks():
                out += [lab for lab, on in ((t.label1, t.label1.get_visible()), (t.label2, t.label2.get_visible())) if on]
        if ax.get_legend():
            out += ax.get_legend().get_texts()
        out += [c for c in ax.get_children() if c.__class__.__name__ == "Annotation"]
    seen, res = set(), []
    for t in out:
        if id(t) not in seen and t.get_visible() and t.get_text().strip():
            seen.add(id(t))
            res.append(t)
    return res


def text_overlaps(fig, tol=0.3, edge=0.3):
    """Pairs of texts whose boxes overlap by more than tol pt, and texts whose box reaches more than edge pt
    beyond the page (the box spans the ink of the text and of "lp", ascender to descender)."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    k = 72 / fig.dpi
    boxes = [(t, t.get_window_extent(r)) for t in _texts(fig)]
    W, H = fig.bbox.width, fig.bbox.height
    out = []
    for i, (t, b) in enumerate(boxes):
        if b.x0 < -edge / k or b.y0 < -edge / k or b.x1 > W + edge / k or b.y1 > H + edge / k:
            out.append(f"'{t.get_text()}' beyond the page")
        for u, c in boxes[i + 1:]:
            if min(b.x1, c.x1) - max(b.x0, c.x0) > tol / k and min(b.y1, c.y1) - max(b.y0, c.y0) > tol / k:
                out.append(f"'{t.get_text()}' / '{u.get_text()}'")
    # labels, legends and annotations of a plot running into a colour bar drawn next to it
    cbars = [a for a in fig.axes if a.get_label() == "<colorbar>"]
    for ax in fig.axes:
        if not ax.axison or ax in cbars:
            continue
        own = [ax.xaxis.label, ax.yaxis.label] + list(ax.texts)
        if ax.get_legend():
            own += list(ax.get_legend().get_texts())
        for t in own:
            if not (t.get_visible() and t.get_text().strip()):
                continue
            b = t.get_window_extent(r)
            for cb in cbars:
                c = cb.bbox
                if min(b.x1, c.x1) - max(b.x0, c.x0) > tol / k and min(b.y1, c.y1) - max(b.y0, c.y0) > tol / k:
                    out.append(f"'{t.get_text()}' / colour bar '{cb.get_ylabel() or cb.get_xlabel()}'")
    return out


def _segments_hit(p0, p1, box):
    """Which display-space segments p0 -> p1 (N x 2) intersect the box (x0, y0, x1, y1): Liang-Barsky clipping."""
    d = p1 - p0
    tmin, tmax = np.zeros(len(p0)), np.ones(len(p0))
    ok = np.ones(len(p0), bool)
    for k, (lo, hi) in enumerate(((box[0], box[2]), (box[1], box[3]))):
        flat = d[:, k] == 0
        ok &= ~flat | ((p0[:, k] >= lo) & (p0[:, k] <= hi))
        with np.errstate(divide="ignore", invalid="ignore"):
            t1, t2 = (lo - p0[:, k]) / d[:, k], (hi - p0[:, k]) / d[:, k]
        tmin = np.where(flat, tmin, np.maximum(tmin, np.minimum(t1, t2)))
        tmax = np.where(flat, tmax, np.minimum(tmax, np.maximum(t1, t2)))
    return ok & (tmin <= tmax)


def legend_hits(fig, leg, renderer, pad_pt=1.0):
    """Number of data elements drawn inside the legend's box (plus pad_pt): line segments and markers of every
    Line2D, scatter offsets and LineCollection (errorbar) segments of all axes of the figure, each only within
    its own axes (data are clipped there)."""
    b = leg.get_window_extent(renderer)
    pad = pad_pt * fig.dpi / 72
    lbox = (b.x0 - pad, b.y0 - pad, b.x1 + pad, b.y1 + pad)
    n = 0
    for ax in fig.axes:
        if not ax.axison:
            continue
        a = ax.bbox
        box = (max(lbox[0], a.x0), max(lbox[1], a.y0), min(lbox[2], a.x1), min(lbox[3], a.y1))
        if box[0] >= box[2] or box[1] >= box[3]:
            continue
        for ln in ax.lines:
            if not ln.get_visible():
                continue
            xy = ln.get_transform().transform(np.asarray(ln.get_xydata(), float))
            xy = xy[np.isfinite(xy).all(1)]
            if len(xy) == 0:
                continue
            if ln.get_linestyle() not in ("None", "", " ") and len(xy) > 1:
                n += int(_segments_hit(xy[:-1], xy[1:], box).sum())
            if ln.get_marker() not in (None, "None", "", " "):
                r = ln.get_markersize() / 2 * fig.dpi / 72
                n += int(((xy[:, 0] > box[0] - r) & (xy[:, 0] < box[2] + r) &
                          (xy[:, 1] > box[1] - r) & (xy[:, 1] < box[3] + r)).sum())
        for c in ax.collections:
            name = type(c).__name__
            if name == "PathCollection" and len(c.get_offsets()):
                xy = c.get_offset_transform().transform(np.asarray(c.get_offsets(), float))
                n += int(((xy[:, 0] > box[0]) & (xy[:, 0] < box[2]) & (xy[:, 1] > box[1]) & (xy[:, 1] < box[3])).sum())
            elif name == "LineCollection":
                for seg in c.get_segments():
                    xy = c.get_transform().transform(np.asarray(seg, float))
                    if len(xy) > 1:
                        n += int(_segments_hit(xy[:-1], xy[1:], box).sum())
    return n


def legend_overlaps(fig):
    """[(axes description, number of data elements under its legend)] for every legend with a count above 0."""
    r = fig.canvas.get_renderer()
    out = []
    for ax in fig.axes:
        leg = ax.get_legend()
        if leg is not None and leg.get_visible():
            k = legend_hits(fig, leg, r)
            if k:
                out.append((f"legend '{leg.get_texts()[0].get_text()}' ... (axes y label "
                            f"'{ax.get_ylabel()}')", k))
    return out


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
