"""Fig. 2d iii (germ-cell counts) and e iv (tissue heights), redrawn at print size in the Fig. 1 type scale.

d iii: germ-cell numbers per colour class of Atwell et al. Fig. 3 in the run shown in d ii and in bold in the table
       (GPT-6.1 Sol, Skill, rep02 replacement02: attempts/attempt_001/cell_counts.csv, fig3_yellow/green/blue/pink
       columns, lines; logged to 53.3 hph) against Atwell et al. (2015) Table S2, the single simulation of their Fig. 3
       (crosses; values as in figures/Supplementary/engine/config.py), Fig. 1 cell-type colours; same classes as Supp. Fig. 4.
e iv: Molè model logger (data/mole_height_rerun/logger_height.csv): epithelium (gray) and blastocyst (black, lowest point)
       height relative to the epithelium at 6 d.p.f. (t = 0; above +, below -), in epithelial cell diameters: the model (mole_height_rerun/13_Mole_model.xml) has 3 um per lattice node and an epithelial target
       area of 22 nodes, i.e. an equivalent diameter 2*sqrt(22/pi) = 5.29 nodes (15.9 um).
Usage: uv run --locked python figures/Fig2/make_plots_de.py
"""
import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import DATA, PANELS  # noqa: E402

HERE = PANELS
COUNTS = DATA / "atwell_cell_counts.csv"   # cell_counts.csv of the run shown in d ii (bold in the table)
HEIGHT = DATA / "mole_height_rerun" / "logger_height.csv"
MM = 1 / 25.4
ATWELL_TABLE_S2 = {  # Atwell et al. (2015) Table S2, single run of their Fig. 3
    "time_hph": [18.5, 27.5, 30.5, 32.5, 33.5, 35.5, 60.5, 87.5],
    "fig3_yellow_cells": [16, 113, 147, 184, 174, 228, 366, 314],
    "fig3_green_cells": [0, 8, 85, 80, 76, 57, 143, 178],
    "fig3_blue_cells": [0, 0, 0, 38, 38, 152, 111, 47],
    "fig3_pink_cells": [0, 0, 0, 0, 36, 69, 60, 83],
}
# Fig. 3 colour classes in the Fig. 1 cell-type colours (proliferative, meiotic, sperm, oocyte)
SERIES = [("fig3_yellow_cells", "#e6b400"), ("fig3_green_cells", "#228b22"), ("fig3_blue_cells", "#1f3fd6"),
          ("fig3_pink_cells", "#d62020")]

plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Liberation Sans", "DejaVu Sans"],
    "font.size": 6, "axes.labelsize": 6, "xtick.labelsize": 5, "ytick.labelsize": 5, "legend.fontsize": 5,
    "axes.linewidth": 0.5, "xtick.major.width": 0.5, "ytick.major.width": 0.5, "xtick.major.size": 2.0,
    "ytick.major.size": 2.0, "xtick.major.pad": 1.2, "ytick.major.pad": 1.2, "axes.labelpad": 1.5,
    "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 0.75,
    "legend.handlelength": 1.4, "legend.handletextpad": 0.4, "legend.borderaxespad": 0.2,
    "legend.labelspacing": 0.2, "svg.fonttype": "none", "pdf.fonttype": 42,
    "mathtext.fontset": "custom", "mathtext.rm": "Arial", "mathtext.it": "Arial:italic",   # italic "et al."
})


def read(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    return {k: [float(r[k]) for r in rows] for k in rows[0]}


def figure(w, h, box):
    """Figure of w x h mm with one axes at box = (left, bottom, right, top) margins in mm."""
    fig = plt.figure(figsize=(w * MM, h * MM))
    l, b, r, t = box
    return fig, fig.add_axes([l / w, b / h, (w - l - r) / w, (h - b - t) / h])


def save(fig, stem):
    for ext in ("svg", "pdf", "png"):
        fig.savefig(HERE / f"{stem}.{ext}", dpi=600)
    plt.close(fig)


# d iii: germ-cell counts
with open(COUNTS, newline="") as f:
    rows = list(csv.DictReader(f))
sim = {k: [float(r[k]) for r in rows] for k in ["time_hph", *(key for key, _ in SERIES)]}
t_end = sim["time_hph"][-1]   # last logged time (53.3 hph); the axis stops there
keep = [i for i, t in enumerate(ATWELL_TABLE_S2["time_hph"]) if t <= t_end]
# 42.25 mm wide, placed at x = 41.75 mm, so the y-axis lands at 48.75 mm on the time axis of d ii
fig, ax = figure(42.25, 20.0, (7.0, 6.0, 1.0, 2.6))   # top margin holds the one-row legend
for key, color in SERIES:
    ax.plot(sim["time_hph"], sim[key], color=color)
    ax.plot([ATWELL_TABLE_S2["time_hph"][i] for i in keep], [ATWELL_TABLE_S2[key][i] for i in keep], "x",
            color=color, markersize=2.5, markeredgewidth=0.6, clip_on=False)
ax.set_xlim(18.5, t_end)
ax.set_ylim(0, 250)
ax.set_yticks([0, 100, 200])
ax.set_xticks([20, 30, 40, 50])
ax.set_xlabel("Time (hph)")
ax.set_ylabel("Cell count")
ax.legend(handles=[Line2D([], [], color="black", label="Agent-generated model"),
                   Line2D([], [], color="black", marker="x", linestyle="none", markersize=2.5,
                          markeredgewidth=0.6, label=r"Atwell $\mathit{et\ al.}$")],
          frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncols=2, columnspacing=1.0, borderaxespad=0.1)
save(fig, "fig2diii_cell_counts")

# e iv: tissue heights
h = read(HEIGHT)
CELL_DIAMETER = 2 * (22 / 3.141592653589793) ** 0.5   # nodes
# heights relative to the epithelium at t = 0 (6 d.p.f.): above +, below -
ref = h["height_epithelium"][0]
blast = [(v - ref) / CELL_DIAMETER for v in h["height_blastocyst"]]
epi = [(v - ref) / CELL_DIAMETER for v in h["height_epithelium"]]
# as tall as d iii (same axes height); placed at x = 132.5 mm, clear of the label "iii"
fig, ax = figure(47.5, 20.0, (8.5, 6.0, 1.0, 2.6))
# colours of the e iii/e iv legend: epithelium, and trophectoderm for the blastocyst (its outer cells, incl. EVT)
ax.plot(h["dpf"], epi, color="#edb5b8", linewidth=1.0, label="Mean epithelial position")
ax.plot(h["dpf"], blast, color="#c59d59", linewidth=1.0, label="Minimal blastocyst position")
ax.set_xlim(6, 9)
ax.set_xticks([6, 7, 8, 9])
ax.set_xlabel("Time (d.p.f.)")
ax.set_yticks([-2, -1, 0, 1])
ax.set_ylabel("Relative height\n(cell diameters)")
ax.legend(frameon=False, loc="lower left", borderaxespad=0.1, reverse=True)
save(fig, "fig2eiv_height")
print("wrote d iii and e iv")
