"""Otsuki et al. (2025): agent-only mean per-cell signals by lineage and cell number vs time.

Panel b: every Gnuplotter frame of the run has three sub-plots (Hand2 per cell, diffusing Shh, posterior memory)
in a 2 x 2 grid with raster titles and colour boxes. The figure shows them as a grid, one column per time point and
one row per sub-plot: b_frames returns the three rows (row 1 = config.FRAMES with FRAME_CROP_PX, the Hand2
sub-plot inside its frame lines, with the time labels; rows 2 and 3 the Shh and memory sub-plots), the framework
lays them out and draws them, and draw_b adds the row labels and one colour bar per row in the run's own
palettes."""
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, ListedColormap
from matplotlib.ticker import MultipleLocator
from PIL import Image

import config
import style
from figure import load_frame, mm_axes, text
from panels.common import axes, legend, split

C_P, C_A, C_MEM, C_SHH, C_FGF, C_N = "#1f3a93", "#5dade2", "#c71585", "#e67e22", "#9a7d0a", "#444444"

# Sub-plots of the 1200 x 507 Gnuplotter frames: interior of each plot box (inside the 1-pixel black frame
# lines at x = 14/475 and 613/1074, y = 38/222 and 291/475), as (x0, x1, y0, y1), x1 and y1 exclusive.
# Row 1 (Hand2) is config.FRAME_CROP_PX; the domain is 320 x 128 nodes in 460 x 183 pixels.
SUB_SHH = (614, 1074, 39, 222)
SUB_MEM = (15, 475, 292, 475)
SHH_BOX = (1096, 1100, 39, 222)  # centre of the Shh colour box (frame lines x = 1086/1109; its tick marks at y = 84, 130, 176 span
# x = 1087-1095 and 1100-1108): the palette from 0.2 (top row) to 0 (bottom row)
SHH_PALETTE_FRAME = "plot_15.00.png"  # any frame: the colour box is the same in all
# Cells ColorMaps of the run's Gnuplotter (model.xml), interpolated linearly in value (checked against the
# rendered colour boxes: 0 #eeeeee, 1 #a7cfe2, 3 #2376ad, 7 #150b51)
HAND2_CMAP = LinearSegmentedColormap.from_list(
    "hand2", [(0, "#eeeeee"), (1 / 7, "#a7cfe2"), (3 / 7, "#2275ad"), (1, "#160a50")])
MEM_CMAP = LinearSegmentedColormap.from_list("memory", [(0, "#eeeeee"), (1, "#409dc4")])
# rows: (label, max of the colour range, ticks)
ROWS = [("Hand2 per cell\n(1 = P steady state)", 7.0, [0, 2, 4, 6]),
        ("Diffusing Shh\n(a.u.)", 0.2, [0, 0.1, 0.2]),
        ("Posterior memory\nper cell (0–1)", 1.0, [0, 0.5, 1])]
A_SHARE = 0.68
D_HEIGHT = 40.0
GRAPH_MAX_H = 40.0

B_CAPTION = ("each Gnuplotter frame (1200 x 507 pixels) has three sub-plots of the 320 x 128-node domain "
             "(1 node = 5 µm as assumed in the agent's model.xml; x: proximal–distal, distal to the right, amputation "
             "plane at x = 96 nodes; upper half: anterior (A) "
             "lineage, lower half: posterior (P) lineage); each sub-plot is cropped inside its plot-box frame lines "
             "(460 x 183 pixels), its raster title and colour box are cropped off, and the sub-plots are arranged "
             "in rows, one column per time point. Rows: Hand2 per cell (hand2, relative to the posterior steady "
             "state; the run's ColorMap 0 #eeeeee, 1 #a7cfe2, 3 #2275ad, 7 #160a50, range 0–7); diffusing Shh "
             "(field Shh, arbitrary units, range 0–0.2; the run's Gnuplotter sets no ColorMap for it, so Morpheus's "
             "default white–yellow–orange–red field palette is used, and the colour bar is redrawn from the "
             "run's own colour box); posterior memory per cell (memory, 0–1, inherited by daughter cells; ColorMap "
             "0 #eeeeee, 1 #409dc4). Colour bars in these palettes at the right. The Shh sub-plots at day 0 and day 39 are blank because "
             "the field is (almost) zero there (maxima in Data handling). Cells are drawn with black "
             "outlines; a 0.5 pt grey line outlines each sub-plot")
CAPTION = ("Agent-only quantification (cells.csv, population.csv; logged every 0.25 day): (i) mean over cells of "
           "Hand2 (hand2) per original lineage, P (lower half at day 0) and A (upper half), and mean posterior "
           "memory (memory) of A-lineage cells; lineage is set from the initial position and inherited at "
           "division; both quantities are relative to the posterior steady state (P-lineage cells start at "
           "hand2 = memory = 1). (ii) Mean over all cells of the Shh and Fgf8 concentrations each cell senses "
           "(shh_seen, fgf_seen: Mapper average of the field over the cell's nodes; arbitrary units). "
           "(iii) Number of connective-tissue cells (celltype.CT.size, the only cell type; it grows from "
           "{n0} to {n1} by division). Amputation at day 0.")


# Publication legend (legend.py): keys are the panel letters as printed; legend.py prepends the run sentence to the
# frames panel and fills {graph} and the {name} fields of ctx.fmt.
LEGEND = {
    "cite": "otsuki2025",  # bib key (morpheusai_supp.bib) cited after every mention of the authors
    "title": "Positional memory in limb regeneration (Otsuki *et al.*, 2025).",
    "a": "Model of how anterior–posterior positional memory is carried through regeneration (adapted from Fig. 5f of "
         "Otsuki *et al.*). Memory is stable at steady state but transiently flexible in the blastema, where Shh "
         "signaling can posteriorize anterior cells.",
    "b": "Rows show Hand2 per cell relative to the posterior steady state, the diffusing Shh field and the posterior "
         "memory per cell. Anterior cells occupy the upper half and posterior cells the lower half; distal is to the "
         "right. Shh is almost zero at the first and last time shown.",
    "c": "{graph}",
    "d": "**i**, Mean Hand2 per cell in the posterior and anterior "
         "lineages and mean posterior memory of anterior-lineage cells, relative to the posterior steady state. "
         "Lineages are set by position at amputation and inherited at division. **ii**, Mean Shh and Fgf8 "
         "concentrations sensed per cell. **iii**, Number of connective-tissue cells, which grows by division from "
         "{n0} to {n1}.",
    "abbrev": "A, anterior; a.u., arbitrary units; P, posterior.",
    "license": "Material from Otsuki *et al.* is adapted under a CC BY 4.0 license.",
}


def _sci(v):
    if v == 0:
        return "0"
    m, e = f"{v:.1e}".split("e")
    return f"{m} × 10{str(int(e)).translate(str.maketrans('-0123456789', '⁻⁰¹²³⁴⁵⁶⁷⁸⁹'))}"


def _crop(im, box):
    x0, x1, y0, y1 = box
    return im[y0:y1, x0:x1]


def _colour_bar(fig, x, y, h, cmap, vmax, ticks):
    """Vertical colour bar, 2.4 mm shorter than its row so the end tick labels of neighbouring rows stay apart."""
    ax = mm_axes(fig, x, y + 1.2, 1.5, h - 2.4)
    v = np.linspace(0, vmax, 512)
    ax.imshow(v[::-1, None], cmap=cmap, vmin=0, vmax=vmax, extent=(0, 1, 0, vmax), aspect="auto",
              interpolation="nearest")
    ax.set(xlim=(0, 1), ylim=(0, vmax), xticks=[])
    ax.yaxis.tick_right()
    ax.set_yticks(ticks, [f"{t:g}" for t in ticks])
    for s in ("left", "right", "top", "bottom"):
        ax.spines[s].set_visible(True)
        ax.spines[s].set_linewidth(0.5)


def b_frames(ctx):
    """Panel b rows: Hand2 (with the time labels), Shh and memory sub-plots of each frame, one column per time."""
    frames = config.FRAMES[ctx.key]
    rows = [[], [], []]
    for f, lab in frames:
        rows[0].append((load_frame(ctx, f), lab))
        im = np.asarray(Image.open(ctx.attempt(f, role="panel b frame")).convert("RGB"))
        rows[1].append((_crop(im, SUB_SHH), ""))
        rows[2].append((_crop(im, SUB_MEM), ""))
    return rows


def draw_b(ctx, fig, pos, y_below):
    """Row labels and one colour bar per row (the run's palettes; Shh read from the run's own colour box)."""
    frames = config.FRAMES[ctx.key]
    im = np.asarray(Image.open(ctx.attempt(SHH_PALETTE_FRAME, role="panel b frame")).convert("RGB"))
    x0, x1, y0, y1 = SHH_BOX
    col = np.median(im[y0:y1, x0:x1].astype(float), axis=1)[::-1] / 255  # bottom (0) to top (0.2)
    shh_cmap = ListedColormap(col, name="shh_gnuplot")
    def compute():  # 11 MB spatial log -> the Shh maximum per logged time
        sp = pd.read_csv(ctx.attempt("spatial.csv", role="panel b note (Shh field)"), usecols=[3, 7])  # time_days, Shh
        return sp.groupby(sp.columns[0])[sp.columns[1]].max().rename_axis("time_days").rename("shh_max").reset_index()
    mx = ctx.summary("otsuki_shh_max", compute).set_index("time_days").shh_max
    t = [float(lab.split()[-1]) for _, lab in frames]
    ctx.note("Panel b: maximum of the Shh field over the domain (spatial.csv) "
             + ", ".join(f"{_sci(mx.loc[ti])} at day {ti:g}" for ti in t) + ".")
    n = len(frames)
    xr = pos[n - 1][0] + pos[n - 1][2] + 1.2
    for k, ((lab, vmax, ticks), cmap) in enumerate(zip(ROWS, (HAND2_CMAP, shh_cmap, MEM_CMAP))):
        x, yk, _, h = pos[k * n]
        text(fig, x - 1.5, yk + h / 2, lab, ha="right", va="center", fontsize=style.FS, linespacing=1.1)
        _colour_bar(fig, xr, yk, h, cmap, vmax, ticks)


def draw(ctx, fig, box):
    d = ctx.csv("cells.csv")
    d = d.loc[:, ~d.columns.duplicated()]
    pop = ctx.csv("population.csv")
    g = d.groupby(["time_days", "lineage"])[["hand2", "memory"]].mean().unstack()
    a = d.groupby("time_days")[["shh_seen", "fgf_seen"]].mean()
    b1, b2, b3 = split(box, [1.45, 1, 0.9], gap=10)
    ax = axes(fig, b1, label="i", left=13.0)
    ax.plot(g.index, g["hand2"][1], color=C_P, label="Hand2, P lineage")
    ax.plot(g.index, g["hand2"][0], color=C_A, ls=(0, (3, 1.5)), label="Hand2, A lineage")
    ax.plot(g.index, g["memory"][0], color=C_MEM, label="Memory, A lineage")
    ax.set(xlabel="Time after amputation (days)", ylabel="Mean per cell\n(P steady state = 1)",
           xlim=(0, g.index.max()), ylim=(0, None))
    ax.xaxis.set_major_locator(MultipleLocator(10))
    legend(ax, loc="upper right")
    ax = axes(fig, b2, label="ii", left=13.0)
    ax.plot(a.index, a.shh_seen, color=C_SHH, label="Shh")
    ax.plot(a.index, a.fgf_seen, color=C_FGF, ls=(0, (3, 1.5)), label="Fgf8")
    ax.set(xlabel="Time after amputation (days)", ylabel="Mean signal sensed\nper cell (a.u.)",
           xlim=(0, a.index.max()), ylim=(0, None))
    legend(ax, loc="upper right")
    ax = axes(fig, b3, label="iii")
    n = pop["celltype.CT.size"]
    ax.plot(pop.time_days, n, color=C_N)
    ax.set(xlabel="Time after amputation (days)", ylabel="Cell number", xlim=(0, pop.time_days.max()))
    ctx.fmt.update(n0=f"{n.iloc[0]:.0f}", n1=f"{n.iloc[-1]:.0f}")
