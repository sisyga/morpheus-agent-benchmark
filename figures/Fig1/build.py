"""Build Fig. 1 of the preprint (Fig1.svg): Nature Methods layout of the agentic modeling workflow overview.

Usage (repository root): uv run --locked python figures/Fig1/build.py [out.svg]
(default build/Fig1.svg here; renders .pdf and a 600 dpi .png next to it with figures/render_fig.py)
Inputs are in this folder: icons/ (our own SVG icons; the official Python and MCP logos; the custom XML and
SKILL.MD icons), images/ (crops of Atwell et al. (2015) Fig. 1D and Fig. 3, CC BY 3.0; 3D renders of the shown
Atwell run, made from its Morpheus checkpoints with an earlier version of
figures/Supplementary/Supp_Fig_04_Atwell2015/atwell_3d.py, in other colours than Supplementary Fig. 4) and
fig1d_paths.json (the outlines of Atwell et al. Fig. 1D, read
from page 2 of benchmark_papers/04_Atwell2025.pdf).

All coordinates are millimetres at final print size (180 mm, double column). Arial, 6 pt text (7 pt in
the workflow steps), 8 pt bold lowercase panel labels, short 6 pt panel headings, black text, American spelling
(Nature Methods house style). Colour is used only where it carries meaning: the five tool configurations
use the Fig. 2 mode colours (analyze_benchmark.MODE_COLORS).

Panels: a, the shared observations (Atwell et al.'s micrograph and measured data) feeding both workflows;
b, traditional workflow: human modeling loop ending in Atwell et al.'s published simulation (unchanged source
plot); c, novel workflow, benchmarked in this study: the LLM agent loop ending in the agent's own 3D Morpheus
model (shaded); d, tools available in configurations 1-5 (Methods); e, files kept for every attempt;
f, the LLM scorer's verdicts for the run in c.
"""
import base64
import io
import os
import re
import sys

from PIL import Image, ImageFont

PT = 25.4 / 72  # mm per point
W = 180.0
LABEL, STEP, BODY = 8 * PT, 7 * PT, 6 * PT
FONT = "Arial, Helvetica, sans-serif"
LW = 0.5 * PT        # keylines
LW_ARROW = 1.0 * PT
X0 = 4.0             # content starts right of the panel labels
INK = "#000000"
GREY = "#7a7a7a"     # envisioned / secondary lines
SCOPE = "#efefef"    # benchmarked part of panel b
ROW_SHADE = "#f3f3f3"
MODES = [("Python\n+ web", "#0072B2"), ("Morpheus\nCLI", "#E69F00"), ("Morpheus\nCLI + docs", "#009E73"),
         ("Skill\n+ CLI", "#D55E00"), ("Morpheus\nMCP", "#000000")]

def _arial(*names):
    """Arial for text widths: Windows fonts, msttcorefonts on Linux, or macOS (same metrics)."""
    for d in ("C:/Windows/Fonts", "/usr/share/fonts/truetype/msttcorefonts", "/Library/Fonts/Supplemental"):
        for n in names:
            if os.path.exists(f"{d}/{n}"):
                return ImageFont.truetype(f"{d}/{n}", 1000)
    raise FileNotFoundError(f"Arial not found ({names[0]})")


_ttf = {False: _arial("arial.ttf", "Arial.ttf"), True: _arial("arialbd.ttf", "Arial Bold.ttf")}


def text_w(s, size, bold=False):
    return _ttf[bold].getlength(s) / 1000 * size


out, defs, sizes, boxes, vector = [], [], {}, [], set()


HERE = os.path.dirname(os.path.abspath(__file__))
ICONS = os.path.join(HERE, "icons")  # our own and official icons
IMAGES = os.path.join(HERE, "images")  # crops of Atwell et al. (2015) and 3D renders of the shown run


def asset(name):
    svg = os.path.join(ICONS, f"{name}.svg")
    if name not in sizes and os.path.exists(svg):  # own vector icon: nested <svg>, so it clips to its viewBox
        src = open(svg, encoding="utf-8").read()
        w, h = (float(v) for v in re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', src).groups())
        inner = re.sub(r"<!--.*?-->", "", src[src.index(">", src.index("<svg")) + 1:src.rindex("</svg>")], flags=re.S)
        sizes[name] = (w, h)
        vector.add(name)
        defs.append(f'<svg id="img-{name}" width="{w:g}" height="{h:g}" viewBox="0 0 {w:g} {h:g}" overflow="hidden">'
                    f'{" ".join(inner.split())}</svg>')
    if name not in sizes:
        im = Image.open(os.path.join(ICONS if os.path.exists(os.path.join(ICONS, f"{name}.png")) else IMAGES,
                                     f"{name}.png"))
        sizes[name] = im.size
        b = io.BytesIO()
        im.save(b, "PNG", optimize=True)
        defs.append(f'<image id="img-{name}" width="{im.width}" height="{im.height}" preserveAspectRatio="none" '
                    f'xlink:href="data:image/png;base64,{base64.b64encode(b.getvalue()).decode()}"/>')
    return sizes[name]


def derived_asset(name, im):
    """Register an image made in memory (e.g. an edited crop of an icon) under name, for img()."""
    if name not in sizes:
        sizes[name] = im.size
        b = io.BytesIO()
        im.save(b, "PNG", optimize=True)
        defs.append(f'<image id="img-{name}" width="{im.width}" height="{im.height}" preserveAspectRatio="none" '
                    f'xlink:href="data:image/png;base64,{base64.b64encode(b.getvalue()).decode()}"/>')
    return sizes[name]


def img(name, x, y, w=None, h=None):
    """Place an asset by width or height (mm); returns (w, h)."""
    pw, ph = asset(name)
    if w is None:
        w = h * pw / ph
    if h is None:
        h = w * ph / pw
    out.append(f'<use xlink:href="#img-{name}" transform="translate({x:.3f},{y:.3f}) scale({w / pw:.6f})"/>')
    boxes.append(("img:" + name, x, y, x + w, y + h, pw / (w / 25.4)))
    return w, h


def icon_box(name, x, y, size):
    """Fit an asset into a size x size square."""
    pw, ph = asset(name)
    w = min(size, size * pw / ph)
    h = w * ph / pw
    img(name, x + (size - w) / 2, y + (size - h) / 2, w=w)


def text(x, y, s, size=BODY, bold=False, italic=False, anchor="start", raw=None, fill=None):
    st = ' font-weight="bold"' if bold else ""
    st += ' font-style="italic"' if italic else ""
    st += f' fill="{fill}"' if fill else ""
    body = raw if raw is not None else s.replace("&", "&amp;")
    out.append(f'<text x="{x:.3f}" y="{y:.3f}" font-size="{size:.4f}"{st} text-anchor="{anchor}">{body}</text>')
    w = text_w(s, size, bold)
    x0 = {"middle": x - w / 2, "end": x - w}.get(anchor, x)
    boxes.append(("txt:" + s, x0, y - 0.72 * size, x0 + w, y + 0.21 * size, size / PT))


def rect(x, y, w, h, stroke=INK, fill="none", lw=LW, rx=0.0):
    out.append(f'<rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" rx="{rx:.3f}" fill="{fill}" '
               f'stroke="{stroke}" stroke-width="{lw:.4f}"/>')


def line(x1, y1, x2, y2, color=INK, lw=LW):
    out.append(f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" stroke="{color}" '
               f'stroke-width="{lw:.4f}"/>')


def arrow(x1, y1, x2, y2, color=INK, lw=LW_ARROW):
    out.append(f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" stroke="{color}" '
               f'stroke-width="{lw:.4f}" marker-end="url(#ah-{color[1:]})"/>')


def path(d, color, lw=LW_ARROW, dash="1.2,0.8"):
    out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{lw:.4f}" stroke-dasharray="{dash}" '
               f'marker-end="url(#ah-{color[1:]})"/>')


LETTER_SHIFT = {"c": "d", "d": "e", "e": "f"}


def panel_label(x, y0, letter):
    text(x, y0 + 2.8, LETTER_SHIFT.get(letter, letter), LABEL, bold=True)


# Atwell et al.'s plot (images/atwell2015_fig3.png, 940 x 709 px) at 46/940 mm per px, where its scale-bar labels are
# 5.2 pt. The developmental stages left of the time axis (L3 ... L4/Adult) are cropped away, and the time axis
# itself (title, line and the four time points) is painted out and redrawn as a vector y axis with live 5 pt labels
# at the same positions (left edge and baseline of each label, in px).
ATWELL_MM = 46.0 / 940
ATWELL_CROP = 116                  # px: the stage labels end at x = 111, the axis line spans x = 122-125
ATWELL_AXIS_PX = 123.5
ATWELL_PAINT = [(116, 0, 213, 40), (120, 36, 128, 709), (133, 50, 205, 83), (131, 181, 206, 214),
                (134, 355, 209, 387), (132, 574, 194, 604)]   # white boxes (x0, y0, x1, y1), px
ATWELL_TIMES = [("18.5", 136, 80), ("27.5", 134, 211), ("30.5", 137, 384), ("35.5", 131, 598)]  # 35.5: 4 px left,
# so the larger label clears the first cell of that row
ATWELL_AXIS_Y = (38, 707)          # px rows of the axis line
MW = (940 - ATWELL_CROP) * ATWELL_MM   # width of the model column


def time_axis(x, y0, y1, title_y):
    """Vertical time axis pointing down (time runs downwards) with its 5 pt title starting at the axis (no title
    when title_y is None)."""
    line(x, y0, x, y1 - 1.0, lw=0.5 * PT)
    out.append(f'<path d="M {x - 0.5:.3f},{y1 - 1.2:.3f} L {x + 0.5:.3f},{y1 - 1.2:.3f} L {x:.3f},{y1:.3f} Z" '
               f'fill="{INK}"/>')
    if title_y is not None:
        text(x - 0.3, title_y, "Time (hph)", LEGEND)


def atwell_output(mx, mw, top):
    """Panel b output: Atwell et al.'s published simulation, without its stage labels and with the time axis
    redrawn (see ATWELL_PAINT)."""
    if "atwell_plot" not in sizes:
        from PIL import ImageDraw
        im = Image.open(os.path.join(IMAGES, "atwell2015_fig3.png")).convert("RGB")
        dr = ImageDraw.Draw(im)
        for box in ATWELL_PAINT:
            dr.rectangle((box[0], box[1], box[2] - 1, box[3] - 1), fill=(255, 255, 255))
        derived_asset("atwell_plot", im.crop((ATWELL_CROP, 0, im.width, im.height)))
    _, mh = img("atwell_plot", mx, top, w=mw)
    k = ATWELL_MM
    xa = mx + (ATWELL_AXIS_PX - ATWELL_CROP) * k
    time_axis(xa, top + ATWELL_AXIS_Y[0] * k, top + mh + 0.6, top + 30 * k)
    for lab, x, yb in ATWELL_TIMES:
        text(mx + (x - ATWELL_CROP) * k, top + yb * k, lab, LEGEND)
    return top + mh + 0.6



def agent_output(mx, mw, top):
    """Panel b output: the agent's 3D Morpheus model at four time points (same camera, same scale), with a time
    axis laid out like Atwell et al.'s plot in panel a: Time (hph) on top, values right of a vertical line."""
    frames = [("18.5", "agent_model_18.5hph"), ("25.5", "agent_model_25.5hph"), ("32.4", "agent_model_32.4hph"), ("39.4", "agent_model_39.4hph")]
    xl = mx + (ATWELL_AXIS_PX - ATWELL_CROP) * ATWELL_MM   # same x as the time axis in the row above
    fx = xl + 0.9 + text_w("39.4", LEGEND) + 0.7
    fw = mw - (fx - mx)
    y = y_top = top + 2.6
    for lab, name in frames:
        _, fh = img(name, fx, y, w=fw)
        text(xl + 0.9, y + fh / 2 + LEGEND * 0.35, lab, LEGEND)
        y += fh + 0.3
    time_axis(xl, y_top, y + 0.3, None)   # same axis as in b, so no second title
    return y + 0.3

# Atwell et al. (2015), Table 1: gonad arm length measured on DIC images (mean, s.d.; n = 10, 10, 15, 6)
ATWELL_LENGTH = [(22.0, 61.7, 9.33), (26.0, 91.4, 7.76), (31.0, 198.0, 23.3), (35.5, 405.0, 46.7)]


FIG1D_PX_PER_UM = 3.805  # images/atwell2015_fig1d.png: 1000 px wide; the source 25 um bar is 21.1 pt in the PDF
OBS_W = 38.4             # width of the observation column (micrograph and observables card at 7 pt)
INK_ICON = "#2c2f32"     # colour of the person icon, used for the robot as well
# kinds of data that the 15 benchmark studies use or produce (biological_scoring_criteria.json): counts of cells
# and cell types, growth over time, cell speeds and migration, expression time courses, spatial patterns of
# morphogens and markers, and tissue shapes
OBS_ROWS = ["Cell counts", "Growth curves", "Cell motility data", "Gene expression dynamics", "Spatial expression patterns",
            "Tissue morphology",
            "Biological hypotheses", "Literature"]
OBS_CARD_H = len(OBS_ROWS) * 3.1 + 2 * 0.6    # observables card: 7 pt rows plus padding


def observations(x, y, w):
    """Biological observations from Atwell et al. (2015, CC BY 3.0): the DIC micrograph of an early adult gonad
    arm (Fig. 1D, rendered from the PDF without its vector labels and scale bar) with our own 25 um scale bar,
    and the observables Atwell et al. fitted their model to (Fig. 4). Returns (right edge, bottom)."""
    pw, ph = asset("atwell2015_fig1d")
    _, ih = img("atwell2015_fig1d", x, y, w=w)
    rect(x, y, w, ih, stroke=GREY, lw=LW)
    fig1d_annotation(x, y, w, ih)
    return observables_card(x, y + ih + 0.8, w)


# Atwell et al. (2015) Fig. 1D annotation. The outlines of the gonad arm and the proximal-most oocyte are their own
# vector paths (fig1d_paths.json, read from the PDF, page 2); labels are redrawn as live 6 pt text, moved onto the
# background so they stay legible at this size, with leader lines to the structures Atwell et al. point at.
# Coordinates are fractions of the micrograph (x from the left, y from the top; baseline for labels).
FIG1D_FRAME = (201.4, 232.8, 423.2, 351.8)  # PDF points of the rendered micrograph
FIG1D_LABELS = [  # text, label x, baseline y, leader start, leader end (= Atwell's target)
    ("DTC", 0.40, 0.095, (0.545, 0.055), (0.905, 0.044)),
    ("Turn", 0.02, 0.37, None, None),
    ("region", 0.02, 0.48, (0.06, 0.505), (0.059, 0.717)),
    ("Sperm", 0.585, 0.72, (0.60, 0.645), (0.573, 0.582)),   # Atwell's "Spermatheca", named as in the legend
    ("Most proximal oocyte", 0.33, 0.975, (0.37, 0.895), (0.378, 0.716)),
]


def fig1d_annotation(x, y, w, h):
    import json
    fx0, fy0, fx1, fy1 = FIG1D_FRAME
    mp = lambda px, py: (x + (px - fx0) / (fx1 - fx0) * w, y + (py - fy0) / (fy1 - fy0) * h)
    for pth in json.load(open(os.path.join(HERE, "fig1d_paths.json")))["paths"]:
        if not all(sg[0] == "c" for sg in pth["segs"]):
            continue  # leader lines and the scale bar are redrawn below
        d, last = [], None
        for _, pts in pth["segs"]:
            (ax, ay), c1, c2, e = [mp(*pt) for pt in pts]
            if last is None or abs(last[0] - ax) + abs(last[1] - ay) > 0.01:
                d.append(f"M {ax:.3f},{ay:.3f}")
            d.append(f"C {c1[0]:.3f},{c1[1]:.3f} {c2[0]:.3f},{c2[1]:.3f} {e[0]:.3f},{e[1]:.3f}")
            last = e
        out.append(f'<path d="{" ".join(d)}" fill="none" stroke="#ffffff" stroke-width="{0.5 * PT:.4f}"/>')
    for lab, lx, lb, a, b in FIG1D_LABELS:
        text(x + lx * w, y + lb * h, lab, fill="#ffffff")
        if a:
            line(x + a[0] * w, y + a[1] * h, x + b[0] * w, y + b[1] * h, "#ffffff", lw=0.5 * PT)
    text(x + 0.02 * w, y + 0.105 * h, "C. elegans", italic=True, fill="#ffffff")
    pw, _ = asset("atwell2015_fig1d")
    sb = 25 * FIG1D_PX_PER_UM * w / pw
    bxr, byb = x + 0.93 * w, y + 0.875 * h
    line(bxr - sb, byb, bxr, byb, "#ffffff", lw=1.0 * PT)
    text(bxr, y + 0.835 * h, "25 µm", anchor="end", fill="#ffffff")


def observables_card(x, y, w):
    """The kinds of biological data the workflow starts from (OBS_ROWS): a CSV file icon centred on the data rows
    and a document icon centred on the last two rows (hypotheses, literature)."""
    rows = OBS_ROWS
    rh, pad = 3.1, 0.6
    h = OBS_CARD_H
    rect(x, y, w, h, stroke=GREY, fill="#ffffff", rx=0.6)
    s = 6.4
    n_data = len(rows) - 2
    icon_box("csv", x + 0.7, y + pad + n_data * rh / 2 - s / 2, s)
    icon_box("doc", x + 0.7, y + pad + (n_data + 1) * rh - s / 2, s)
    for k, lab in enumerate(rows):
        cy = y + pad + (k + 0.5) * rh
        text(x + 0.7 + s + 0.9, cy + STEP * 0.35, lab, STEP)
    assert x + 0.7 + s + 0.9 + max(text_w(r, STEP) for r in rows) < x + w - 0.5, "observables card too narrow"
    return x + w, y + h


def robot(x, y, h):
    """Robot glyph in the style and colour of the person icon, h mm tall; returns its width."""
    s = h / 5.0
    c = INK_ICON
    out.extend([
        f'<line x1="{x + 2.1 * s:.3f}" y1="{y + 0.45 * s:.3f}" x2="{x + 2.1 * s:.3f}" y2="{y + 1.0 * s:.3f}" '
        f'stroke="{c}" stroke-width="{0.28 * s:.3f}"/>',
        f'<circle cx="{x + 2.1 * s:.3f}" cy="{y + 0.4 * s:.3f}" r="{0.36 * s:.3f}" fill="{c}"/>',
        f'<rect x="{x + 0.55 * s:.3f}" y="{y + 1.0 * s:.3f}" width="{3.1 * s:.3f}" height="{2.15 * s:.3f}" '
        f'rx="{0.55 * s:.3f}" fill="{c}"/>',
        f'<rect x="{x + 0.15 * s:.3f}" y="{y + 1.65 * s:.3f}" width="{0.5 * s:.3f}" height="{0.85 * s:.3f}" '
        f'rx="{0.15 * s:.3f}" fill="{c}"/>',
        f'<rect x="{x + 3.55 * s:.3f}" y="{y + 1.65 * s:.3f}" width="{0.5 * s:.3f}" height="{0.85 * s:.3f}" '
        f'rx="{0.15 * s:.3f}" fill="{c}"/>',
        f'<circle cx="{x + 1.45 * s:.3f}" cy="{y + 1.85 * s:.3f}" r="{0.36 * s:.3f}" fill="#ffffff"/>',
        f'<circle cx="{x + 2.75 * s:.3f}" cy="{y + 1.85 * s:.3f}" r="{0.36 * s:.3f}" fill="#ffffff"/>',
        f'<rect x="{x + 1.4 * s:.3f}" y="{y + 2.55 * s:.3f}" width="{1.4 * s:.3f}" height="{0.22 * s:.3f}" '
        f'rx="{0.1 * s:.3f}" fill="#ffffff"/>',
        f'<path d="M {x + 0.25 * s:.3f},{y + 5.0 * s:.3f} V {y + 4.25 * s:.3f} Q {x + 0.25 * s:.3f},{y + 3.45 * s:.3f} '
        f'{x + 1.05 * s:.3f},{y + 3.45 * s:.3f} H {x + 3.15 * s:.3f} Q {x + 3.95 * s:.3f},{y + 3.45 * s:.3f} '
        f'{x + 3.95 * s:.3f},{y + 4.25 * s:.3f} V {y + 5.0 * s:.3f} Z" fill="{c}"/>',
    ])
    return 4.2 * s


def label_on_line(cx, y, s, bg):
    """Italic label sitting on a dashed line, with a background patch that interrupts the line."""
    w = text_w(s, STEP) + 1.8
    rect(cx - w / 2, y - 1.35, w, 2.7, stroke="none", fill=bg)
    text(cx, y + STEP * 0.33, s, STEP, italic=True, anchor="middle")


def elbow(points, color, dash="1.2,0.8"):
    d = "M " + " L ".join(f"{px:.3f},{py:.3f}" for px, py in points)
    out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{LW_ARROW:.4f}" stroke-dasharray="{dash}" '
               f'stroke-linejoin="round" marker-end="url(#ah-{color[1:]})"/>')


def workflow(y0, letter, actor, actor_label, output, scope=False):
    """Observations -> modeling loop (human or agent) -> in silico model, with the outer iteration.
    Loops use right-angled connectors. In panel b the benchmarked part (agent box and model output) is shaded,
    and the box names the tool setups of panel c and points to the attempt files of panel d."""
    panel_label(0, y0, letter)
    dy = 0.0
    top = y0 + dy
    ox = X0 + 11.4                       # observation column
    bx0 = ox + OBS_W + 5.0
    mx, mw = 144.0, 36.0                 # model output column
    bx1 = mx - 5.6
    # centre the modeling box on the observation column (micrograph + observables card)
    pw, ph = asset("atwell2015_fig1d")
    obs_top, obs_h = top + 3.9, OBS_W * ph / pw + 0.8 + OBS_CARD_H
    box_h = 6.8 + 7.6 + 2.3 + 2.6 + 1.6
    by0 = obs_top + (obs_h - box_h) / 2
    sy0, sh = by0 + 6.8, 7.6
    mid = sy0 + sh / 2
    yl = sy0 + sh + 2.3                  # inner loop
    yat = yl + 2.6                       # attempt output row (panel b)
    by1 = yat + 1.6
    # model output first (its height sets the row); the shaded scope must sit behind everything in b
    out_start = len(out)
    text(mx + mw / 2, top + 2.8, "In silico model", anchor="middle",
         raw='<tspan font-style="italic">In silico</tspan> model')
    bottom = output(mx, mw, top + 4.0)
    out_items = out[out_start:]
    del out[out_start:]
    yo = max(bottom - 1.6, obs_top + obs_h + 2.0, by1 + 2.0)  # outer loop runs below everything
    if scope:
        x_l, x_m = bx0 - 1.2, mx - 1.6
        y_t, y_b, y_n = top + 0.6, bottom + 0.8, by1 + 1.2
        out.append(f'<path d="M {x_l:.3f},{y_t:.3f} H {W:.3f} V {y_b:.3f} H {x_m:.3f} V {y_n:.3f} H {x_l:.3f} Z" '
                   f'fill="{SCOPE}"/>')
        text(bx0, by0 - 1.0, "Benchmarked in this study")
        yo = max(yo, y_n + 1.8)
    out.extend(out_items)
    # observations
    text(X0, top + 2.8, "Biological problem, data")
    img("microscope", X0, mid - 4.4, h=8.0)
    arrow(X0 + 6.9, mid, ox - 0.4, mid)
    img("person", X0 + 6.4, mid - 6.4, h=5.0)    # same size as the actor icons in the boxes
    obs_r, obs_b = observations(ox, obs_top, OBS_W)
    arrow(obs_r + 0.4, mid, bx0 - 0.15, mid)
    # modeling loop
    rect(bx0, by0, bx1 - bx0, by1 - by0, stroke=INK, fill="#ffffff", rx=0.8)
    if actor == "robot":
        aw = robot(bx0 + 1.4, by0 + 0.8, 5.0)
    else:
        aw, _ = img(actor, bx0 + 1.4, by0 + 0.8, h=5.0)
    text(bx0 + 1.4 + aw + 1.2, by0 + 3.9, actor_label, STEP)
    sw_ = 15.6
    steps = [("Extract info", sw_), ("Generate", sw_), ("Execute", sw_), ("Evaluate", sw_)]
    gap = 4.6
    sx = bx0 + (bx1 - bx0 - sum(w for _, w in steps) - gap * (len(steps) - 1)) / 2
    centers = []
    for i, (lab, w) in enumerate(steps):
        rect(sx, sy0, w, sh, stroke=INK, fill="#ffffff", rx=0.9)
        text(sx + w / 2, mid + STEP * 0.35, lab, STEP, anchor="middle")
        centers.append(sx + w / 2)
        if i < len(steps) - 1:
            arrow(sx + w + 0.3, mid, sx + w + gap - 0.3, mid)
        sx += w + gap
    xa, xb = centers[3] - sw_ / 2 + 3.0, centers[1]  # the loop leaves from the left part of Evaluate
    elbow([(xa, sy0 + sh), (xa, yl), (xb, yl), (xb, sy0 + sh + 0.25)], INK)
    label_on_line((xa + xb) / 2, yl, "iterate", "#ffffff")
    if scope:
        # tool setups (panel c) listed next to the agent; the attempt output (panel d) at the top right of the box
        cy = by0 + 3.9 - STEP * 0.35
        lx = bx0 + 1.4 + aw + 1.2 + text_w(actor_label, STEP) + 1.0
        text(lx, by0 + 3.9, "with tool setups", STEP)
        dx = lx + text_w("with tool setups", STEP) + 2.0
        for j in range(5):
            out.append(f'<circle cx="{dx + j * 3.0:.3f}" cy="{cy:.3f}" r="1.2" fill="{MODES[j][1]}"/>')
            text(dx + j * 3.0, cy + BODY * 0.35, str(j + 1), bold=True, anchor="middle", fill="#ffffff")
        ar = centers[3] + sw_ / 2       # right-aligned under Evaluate, below the loop
        fx = ar - text_w("Attempt output", BODY)
        out.append(f'<path d="M {fx - 3.6:.3f},{yat - 0.95:.3f} h 1.1 l 0.35,0.45 h 1.4 v 1.45 h -2.85 Z" '
                   f'fill="none" stroke="{INK}" stroke-width="{LW:.4f}"/>')
        text(ar, yat + BODY * 0.35, "Attempt output", anchor="end")
    arrow(bx1 + 0.4, mid, mx - 0.6, mid)
    # outer iteration: model -> biological problem, under the observations and the box (right angles)
    ex = X0 + 3.0
    if scope:
        elbow([(mx - 1.6, yo), (ex, yo), (ex, mid + 4.0)], GREY)
    else:
        xr = bx1 + 2.8
        elbow([(mx - 0.6, bottom - 4.0), (xr, bottom - 4.0), (xr, yo), (ex, yo), (ex, mid + 4.0)], GREY)
    label_on_line((bx0 + bx1) / 2, yo, "iterate", "#ffffff")
    OUT_BOTTOM[letter] = bottom + (0.8 if scope else 0.0)
    return max(bottom, yo + 1.2)


def tools_matrix(y0):
    """Panel c: which tools each configuration exposes (Methods, 'Agent configurations')."""
    panel_label(0, y0, "c")
    rows = [("globe", "Web search", [1, 1, 0, 1, 1]),
            ("python", "Python", [1, 1, 1, 1, 1]),
            ("cli", "Morpheus CLI", [0, 1, 1, 1, 1]),
            ("doc", "Morpheus documentation", [0, 0, 1, 1, 1]),
            ("xml", "Example models (43)", [0, 0, 0, 1, 1]),
            ("skill", "Agent skill (instructions)", [0, 0, 0, 1, 1]),
            ("mcp", "MCP server tools", [0, 0, 0, 0, 1])]
    li, rh = 2.9, 3.4
    lab_w = li + 1.0 + max(text_w(r[1], STEP) for r in rows)
    names = ["Web", "CLI", "Docs", "Skill", "MCP"]   # setups 1-5; 2-5 sit under "Runs Morpheus simulator"
    cws = [max(text_w(name, STEP) + 1.4, 7.2) for name in names]
    cx0 = X0 + lab_w + 1.0
    # header: execution bracket, numbered colour discs, configuration names (as in Fig. 2)
    yb = y0 + 2.4
    xs = [cx0 + sum(cws[:j]) + cws[j] / 2 for j in range(5)]
    bl, br = xs[1] - cws[1] / 2 + 0.6, xs[4] + cws[4] / 2 - 0.6
    line(bl, yb + 1.0, br, yb + 1.0)
    line(bl, yb + 1.0, bl, yb + 1.8)
    line(br, yb + 1.0, br, yb + 1.8)
    text((xs[1] + xs[4]) / 2, yb, "Runs Morpheus simulator", STEP, anchor="middle")
    yd = y0 + 5.6
    for j, (name, (_, col)) in enumerate(zip(names, MODES)):
        out.append(f'<circle cx="{xs[j]:.3f}" cy="{yd:.3f}" r="1.5" fill="{col}"/>')
        text(xs[j], yd + STEP * 0.35, str(j + 1), STEP, bold=True, anchor="middle", fill="#ffffff")
        text(xs[j], yd + 3.9, name, STEP, anchor="middle")
    text(X0, yd + 3.9, "Tools", STEP, bold=True)   # heading of the first column, on the line of the setup names
    ytab = yd + 5.0
    for i, (icon, lab, has) in enumerate(rows):
        y = ytab + i * rh
        if i % 2 == 0:
            rect(X0 - 0.4, y, cx0 + sum(cws) - X0 + 0.4, rh, stroke="none", fill=ROW_SHADE)
        icon_box(icon, X0, y + (rh - li) / 2, li)
        text(X0 + li + 1.0, y + rh / 2 + STEP * 0.35, lab, STEP)
        for j, v in enumerate(has):
            if v:
                out.append(f'<circle cx="{xs[j]:.3f}" cy="{y + rh / 2:.3f}" r="0.95" fill="{MODES[j][1]}"/>')
    return cx0 + sum(cws), ytab + len(rows) * rh


def attempt_tree(x0, y0, bottom, right):
    """Panel d: the files kept in every attempt folder (stylized)."""
    panel_label(x0, y0, "d")
    x = x0 + 3.6
    items = [("xml", "model.xml", "MorpheusML model"),
             ("dot", "model_graph.dot", "Model graph"),
             ("log", "stdout.log", "Simulation log"),
             ("csv", "cell_counts.csv", "Simulation data"),
             ("png", "cell_counts.png", "Analysis plots"),
             (None, "snapshots/", "Simulation snapshots")]
    li = 3.2
    # content starts lower than the panel letter, so that the bold "Attempt output" heading shares its baseline
    # with "LLM scorer" in the next panel (2.55 + 2.7 mm below the row top); the rows are packed tighter by the
    # same amount, so the snapshot still ends level with the last row of the tools table
    shift = (2.55 + 2.7) - (1.2 + 2.4)
    y = y0 + 1.2 + shift
    out.append(f'<path d="M {x:.3f},{y + 0.5:.3f} h 1.6 l 0.5,0.6 h 2.0 v 2.0 h -4.1 Z" fill="none" stroke="{INK}" '
               f'stroke-width="{LW:.4f}"/>')
    text(x + 5.0, y + 2.4, "attempt_001/", STEP)
    trunk_x, y = x + 1.6, y + 3.9
    name_x = trunk_x + 2.6 + li + 1.0
    desc_x = name_x + max(text_w(n, STEP) for _, n, _ in items) + 1.8
    text(desc_x, y - 3.9 + 2.4, "Attempt output", STEP, bold=True)   # heading of the description column
    rowh = 3.8 - shift / 5
    last_mid = None
    for k, (icon, name, desc) in enumerate(items):
        ym = y + k * rowh + li / 2
        line(trunk_x, ym, trunk_x + 2.0, ym, GREY)
        if icon:
            icon_box(icon, trunk_x + 2.6, ym - li / 2, li)
        else:
            out.append(f'<path d="M {trunk_x + 2.6:.3f},{ym - 1.0:.3f} h 1.3 l 0.4,0.5 h 1.3 v 1.5 h -3.0 Z" '
                       f'fill="none" stroke="{INK}" stroke-width="{LW:.4f}"/>')
        text(name_x, ym + STEP * 0.35, name, STEP)
        text(desc_x, ym + STEP * 0.35, desc, STEP)
        last_mid = ym
    line(trunk_x, y - 0.4, trunk_x, last_mid, GREY)
    # small snapshot of the same agent run at 32.4 hph (no scale bar), a child of snapshots/ in the tree,
    # ending level with the last row of panel c
    pw, ph = asset("agent_model_32.4hph_crop")
    top_i = last_mid + 2.0
    room = (bottom - 0.9) - top_i
    kx = trunk_x + 2.6 + 1.5
    ix = kx + 2.6
    iw = min(right - ix, 16.0, room * pw / ph)
    _, th = img("agent_model_32.4hph_crop", ix, top_i, w=iw)
    line(kx, last_mid + 1.0, kx, top_i + th / 2, GREY)
    line(kx, top_i + th / 2, ix - 0.4, top_i + th / 2, GREY)
    return top_i + th



# cell-type colours of Atwell et al. Fig. 3, used by the agent's model and by atwell_3d.py (render colours)
CELL_TYPES = [("Proliferative", "#e6b400"), ("Meiotic", "#228b22"), ("Spermatocyte", "#87cefa"),
              ("Sperm", "#1f3fd6"), ("Oocyte", "#d62020"), ("DTC", "#0f9b9b")]


LEGEND = 5 * PT          # the cell-type legend uses Nature's 5 pt minimum to stay compact


def cell_legend(x0, y0):
    """Compact legend with its left edge at x0: a bold 5 pt title "Cell types" above three rows by two columns of
    colour swatches (cells drawn as discs) with 5 pt labels, filled column-wise in developmental order
    (proliferative, meiotic, spermatocyte | sperm, oocyte, DTC). y0 is the centre of the first row.
    Returns (left, top, bottom, right)."""
    order = [[0, 1, 2], [3, 4, 5]]
    r, pitch, gap = 0.55, 2.1, 0.5
    cw = [max(text_w(CELL_TYPES[k][0], LEGEND) for k in col) + 2 * r + 0.5 for col in order]
    text(x0, y0 - pitch + LEGEND * 0.35, "Cell types", LEGEND, bold=True)
    for c, col in enumerate(order):
        x = x0 + sum(cw[:c]) + c * gap
        for i, k in enumerate(col):
            lab, colr = CELL_TYPES[k]
            y = y0 + i * pitch
            out.append(f'<circle cx="{x + r:.3f}" cy="{y:.3f}" r="{r:.3f}" fill="{colr}"/>')
            text(x + 2 * r + 0.5, y + LEGEND * 0.35, lab, LEGEND)
    return x0, y0 - pitch - 0.9, y0 + 2 * pitch + 0.8, x0 + sum(cw) + gap


OUT_BOTTOM = {}
E_TOP = [0.0]
E_X0 = 145.0             # panel f sits under the model output column of panel c, right-aligned
# Atwell et al. criteria (biological_scoring_criteria.json, criteria v7) and the verdicts of the shown run
# (20261008_222700_04_Atwell2025__morpheus_skill__rep02__replacement02, scorer v8: all ten clauses pass, score 1)
ATWELL_CLAUSES = [("Qualitative criteria", "Observed"),
                  ("All cell types present", ""),
                  ("U-shaped tissue domain", ""),
                  ("Quantitative criteria", None),
                  ("Proliferative 200–400", "206"),
                  ("Meiotic 50–200", "136"),
                  ("Sperm 30–180", "108"),
                  ("Oogenic 30–100", "92"),
                  ("≥10 cells past the U-turn", "226")]


def check(x, y):
    out.append(f'<path d="M {x:.3f},{y - 0.05:.3f} l 0.45,0.5 l 0.95,-1.1" fill="none" stroke="{INK}" '
               f'stroke-width="{0.75 * PT:.4f}" stroke-linecap="round" stroke-linejoin="round"/>')


def scoring(x0, y0):
    """Panel e: the LLM scorer checks the final attempt against paper-specific criteria (shown: Atwell et al.)."""
    panel_label(x0 - 3.8, y0, "e")
    rh = 2.95
    y0 += 2.55                  # one line lower than the panel label, so the arrow from c is longer
    rw = robot(x0, y0 + 0.1, 3.4)
    text(x0 + rw + 1.0, y0 + 2.7, "LLM scorer", STEP, bold=True)
    E_TOP[0] = y0
    y = y0 + 6.0
    for lab, val in ATWELL_CLAUSES:
        if val is None and y > y0 + 7.0:   # section header below the first one: separate it by a rule with equal
            rule = y - rh + 0.21 * STEP + 0.6  # white space (0.6 mm) to the descenders above and the capitals below
            line(x0, rule, W, rule, lw=0.5 * PT)
            y = rule + 0.6 + 0.72 * STEP
        if val is None or val == "Observed":
            text(x0, y, lab, STEP, italic=True)
            if val:
                text(W, y, val, STEP, italic=True, anchor="end")
        else:
            text(x0, y, lab, STEP)
            if val:
                text(W - 2.2, y, val, STEP, anchor="end")
            check(W - 1.5, y - 0.85)
        y += rh
    line(x0, y - 1.7, W, y - 1.7, lw=0.5 * PT)
    text(x0, y + 1.0, "Score", STEP)
    text(W, y + 1.0, "1.0", STEP, bold=True, anchor="end")
    return y + 1.7


C_OUT = -0.6          # c's snapshots start this far below the row top minus 2.6 mm (no time-axis title)
LEG_Y = 3.9           # first legend row below the top of row c (title above it)
LEG_LEFT = 145.7      # legend left edge: right of the time-axis labels, left of the 18.5 hph tissue


# ---- alternative layout ------------------------------------------------------------------------------------------
OX, MX = X0 + 11.4, W - MW   # MW: see ATWELL_MM
A_OBS_R = OX + OBS_W
BX0, BX1 = A_OBS_R + 9.6, MX - 4.8
BOX_H = 6.8 + 7.6 + 2.3 + 2.9 + 1.8
STEP_GAP, STEP_PAD = 3.0, 1.2   # between the step boxes; between the steps and the box edge
STEP_W = (BX1 - BX0 - 2 * STEP_PAD - 3 * STEP_GAP) / 4


def model_row(letter, top, by0, actor, actor_label, output, scope):
    """Modeling box (human or agent) and its in silico model; returns geometry for the loops."""
    text(BX0 - 4.6, top + 2.8, letter, LABEL, bold=True)   # rows b and c keep their letters
    sy0, sh = by0 + 6.8, 7.6
    mid = sy0 + sh / 2
    yl = sy0 + sh + 2.3
    yat = yl + 2.9
    by1 = by0 + BOX_H
    if not scope:   # one column title above both model outputs
        text(MX + MW / 2, top + 2.8, "Virtual tissue model", LABEL, bold=True, anchor="middle")
    bottom = output(MX, MW, top + (C_OUT if scope else 5.4))
    y_n = by1 + 1.2
    text(BX0, top + 2.8, "Morpheus.AI workflow, benchmarked in this study" if scope else "Traditional workflow", LABEL,
         bold=True)
    rect(BX0, by0, BX1 - BX0, by1 - by0, stroke=INK, fill="#ffffff", rx=0.8)
    if actor == "robot":
        aw = robot(BX0 + 1.4, by0 + 0.8, 5.0)
    else:
        aw, _ = img(actor, BX0 + 1.4, by0 + 0.8, h=5.0)
    text(BX0 + 1.4 + aw + 1.2, by0 + 3.9, actor_label, STEP)
    sw_, gap = STEP_W, STEP_GAP
    sx = BX0 + STEP_PAD
    centers = []
    for i, lab in enumerate(["Extract info", "Generate", "Execute", "Evaluate"]):
        rect(sx, sy0, sw_, sh, stroke=INK, fill="#ffffff", rx=0.9)
        text(sx + sw_ / 2, mid + STEP * 0.35, lab, STEP, anchor="middle")
        centers.append(sx + sw_ / 2)
        if i < 3:
            arrow(sx + sw_ + 0.3, mid, sx + sw_ + gap - 0.3, mid)
        sx += sw_ + gap
    xa, xb = centers[3] - sw_ / 2 + 3.0, centers[1]
    elbow([(xa, sy0 + sh), (xa, yl), (xb, yl), (xb, sy0 + sh + 0.25)], INK)
    elbow([(xb, yl), (centers[0], yl), (centers[0], sy0 + sh + 0.25)], INK)   # second ending at Extract info
    label_on_line((xa + xb) / 2, yl, "iterate", "#ffffff")
    if scope:
        cy = by0 + 3.9 - STEP * 0.35
        lx = BX0 + 1.4 + aw + 1.2 + text_w(actor_label, STEP) + 1.0
        text(lx, by0 + 3.9, "with tools", STEP)
        dx = lx + text_w("with tools", STEP) + 2.2
        for j in range(5):
            out.append(f'<circle cx="{dx + j * 3.4:.3f}" cy="{cy:.3f}" r="1.45" fill="{MODES[j][1]}"/>')
            text(dx + j * 3.4, cy + STEP * 0.35, str(j + 1), STEP, bold=True, anchor="middle", fill="#ffffff")
        ar = centers[3] + sw_ / 2
        fx = ar - text_w("Attempt output", STEP)
        out.append(f'<path d="M {fx - 3.9:.3f},{yat - 1.05:.3f} h 1.2 l 0.4,0.5 h 1.55 v 1.6 h -3.15 Z" '
                   f'fill="none" stroke="{INK}" stroke-width="{LW:.4f}"/>')
        text(ar, yat + STEP * 0.35, "Attempt output", STEP, anchor="end")
    arrow(BX1 + 0.4, mid, MX - 1.0, mid)
    return dict(mid=mid, by0=by0, by1=by1, bottom=bottom, y_n=y_n)


def observation_panel(top):
    """Panel a: microscope, observer, micrograph with Atwell et al.'s annotation, observables card."""
    panel_label(OX - 4.6, top - 3.8, "a")   # letter and subtitle on one baseline, as in b and c
    text(OX, top - 1.0, "Biological problem, data", LABEL, bold=True)
    pw, ph = asset("atwell2015_fig1d")
    ym = top + OBS_W * ph / pw / 2
    img("microscope", X0, ym - 4.4, h=8.0)
    arrow(X0 + 6.9, ym, OX - 0.4, ym)
    img("person", X0 + 6.4, ym - 6.4, h=5.0)
    _, bottom = observations(OX, top, OBS_W)
    return ym - 4.4, ym + 3.6, bottom


# row b: human scientist
top_b = 0.0
loop_b = 5.4
row_b = model_row("b", top_b, 8.4, "person", "Human scientist", atwell_output, scope=False)
OUT_BOTTOM["a"] = row_b["bottom"]
# row c: LLM agent (benchmarked). The cell-type legend sits half in the gap under b's model and half in the top of
# c's model column, which is empty above the first (18.5 hph) snapshot; its first row is LEG_Y below the top of row c
top_c = max(row_b["by1"] + 4.0, row_b["bottom"] - 0.6)
row_c = model_row("c", top_c, top_c + 5.0, "robot", "LLM agent", agent_output, scope=True)
_k = len(out)
leg_left, leg_top, leg_bottom, leg_right = cell_legend(LEG_LEFT, top_c + LEG_Y)
out.insert(_k, f'<rect x="{leg_left - 0.7:.3f}" y="{leg_top:.3f}" width="{leg_right - leg_left + 1.0:.3f}" '
               f'height="{leg_bottom - leg_top + 0.4:.3f}" rx="0.8" fill="#ffffff" fill-opacity="0.85" stroke="#cccccc" '
               f'stroke-width="{0.5 * PT:.4f}"/>')
print(f"legend x {leg_left:.1f}-{leg_right:.1f}, y {leg_top:.1f}-{leg_bottom:.1f}; b model ends {row_b['bottom']:.1f}, "
      f"c snapshots start {top_c + 3.8:.1f}")
OUT_BOTTOM["b"] = row_c["bottom"] + 0.8
# panel a, centred between the two modeling boxes: a bracket gathers the micrograph and the data, and both arrows
# leave from its middle, so b and c receive the same observations
y_fork = (row_b["mid"] + row_c["mid"]) / 2
pw_, ph_ = asset("atwell2015_fig1d")
obs_h = OBS_W * ph_ / pw_ + 0.8 + OBS_CARD_H
obs_top = y_fork - obs_h / 2
mic_top, mic_bot, obs_bottom = observation_panel(obs_top)
xk = A_OBS_R + 1.2
out.append(f'<path d="M {xk - 0.7:.3f},{obs_top:.3f} H {xk:.3f} V {obs_bottom:.3f} H {xk - 0.7:.3f}" fill="none" '
           f'stroke="{INK}" stroke-width="{LW_ARROW:.4f}" stroke-linejoin="miter"/>')   # as thick as the arrows
arrow(xk, y_fork, BX0 - 0.2, row_b["mid"])
arrow(xk, y_fork, BX0 - 0.2, row_c["mid"])
# outer loops, both straight from the model output: b over the top of its box, c below its box
ex = X0 + 3.0
elbow([(MX - 1.6, loop_b), (ex, loop_b), (ex, mic_top - 0.3)], GREY)   # starts clear of the time axis
label_on_line((MX - 1.6 + ex) / 2, loop_b, "iterate", "#ffffff")
gap_b = row_b["by0"] - loop_b
yo_c = max(row_c["by1"] + gap_b, obs_bottom + 1.5)
print(f"outer loops: b {gap_b:.1f} mm above its box, c {yo_c - row_c['by1']:.1f} mm below its box "
      f"(panel a ends {obs_bottom:.1f})")
elbow([(MX - 1.6, yo_c), (ex, yo_c), (ex, mic_bot + 0.3)], GREY)
label_on_line((MX - 1.6 + ex) / 2, yo_c, "iterate", "#ffffff")
ARROW_LEN = (MX - 1.0) - (BX1 + 0.4)       # box-to-model arrows in b and c
y = max(row_c["bottom"] + 0.8, yo_c + 1.2)
yc = max(yo_c + 2.6, OUT_BOTTOM["b"] + 0.3 + ARROW_LEN + 0.2 - 2.55)   # f's content starts 2.55 mm below yc
print(f"lower row at {yc:.1f} mm (loop c at {yo_c:.1f}, c model ends {OUT_BOTTOM['b']:.1f})")
cx1, cbottom = tools_matrix(yc)
dright = E_X0 - 5.0
dbottom = attempt_tree(cx1 + 4.0, yc, cbottom, dright)
ebottom = scoring(E_X0, yc)
arrow(E_X0 + (W - E_X0) / 2, OUT_BOTTOM["b"] + 0.3, E_X0 + (W - E_X0) / 2, E_TOP[0] - 0.2, lw=1.0 * PT)
right_e = max(b[3] for b in boxes if cx1 < b[1] < E_X0 - 4.0 and b[2] > yc - 1.0)
print(f"panel d ends {cx1:.1f} mm, panel e ends {right_e:.1f} mm, panel f starts {E_X0:.1f} mm (letter {E_X0 - 3.8:.1f})")
H = round(max(cbottom, dbottom, ebottom) + 0.8, 1)

markers = "".join(
    f'<marker id="ah-{c[1:]}" viewBox="0 0 6 6" refX="5" refY="3" markerWidth="4.2" markerHeight="4.2" '
    f'orient="auto-start-reverse" markerUnits="strokeWidth"><path d="M0,0.4 L5.6,3 L0,5.6 Z" fill="{c}"/></marker>'
    for c in (INK, GREY))
svg = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
       f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
       f'width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}" font-family="{FONT}" fill="#000">\n'
       f'<defs>{markers}{"".join(defs)}</defs>\n'
       f'<rect width="{W}" height="{H}" fill="#ffffff"/>\n' + "\n".join(out) + "\n</svg>\n")
out_svg = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "build", "Fig1.svg")
os.makedirs(os.path.dirname(os.path.abspath(out_svg)), exist_ok=True)
open(out_svg, "w", encoding="utf-8").write(svg)
print(f"size {W} x {H} mm, {len(svg) // 1024} KB")

print("outside page:", [b[0] for b in boxes if b[1] < -0.01 or b[3] > W + 0.01 or b[4] > H])
print("font sizes (pt):", sorted({round(b[5], 2) for b in boxes if b[0].startswith("txt:")}))
print("lowest raster image dpi:", sorted((round(b[5]), b[0]) for b in boxes if b[0].startswith("img:") and b[0][4:] not in vector)[:3])
T = [b for b in boxes if b[0].startswith("txt:")]
for i in range(len(T)):
    for j in range(i + 1, len(T)):
        a, b = T[i], T[j]
        if a[1] < b[3] and b[1] < a[3] and a[2] < b[4] and b[2] < a[4]:
            print("text overlap:", a[0], "|", b[0])

import subprocess  # noqa: E402
subprocess.run([sys.executable, os.path.join(os.path.dirname(HERE), "render_fig.py"), out_svg], check=True)
