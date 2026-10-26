"""Berkemeier & Page (2023): per-cell Delta vs paper Fig. 4a; high-Delta fraction and cluster size."""
import os

import berkemeier_fig4a_extract
from panels.common import axes, split

AB_LAYOUT = "side"
C_D, C_FRAC, C_CL = "#4d9a2a", "#4d9a2a", "#566573"  # panel-b green (low Delta)
B_LEGEND = [("#5aa832", "low Delta"), ("#ffffff", "high Delta")]
CAPTION = ("(i) Delta activity D of every cell vs time (cell_states.csv, 196 cells; green) with all 36 cells of "
           "Fig. 4a (6 × 6 lattice; grey). The paper's curves are the vector paths of Fig. 4a, taken from page 6 "
           "of the PDF and calibrated with the panel's axis ticks (berkemeier_fig4a_extract.py; cached copy "
           "5_Berkemier/fig4a_vector_paths.csv). Time in units of the Notch decay time in both. (ii) Fraction of "
           "high-Delta cells and (iii) mean size of high-Delta clusters (delta_cluster_timeseries.csv).")


def draw(ctx, fig, box):
    d = ctx.csv("cell_states.csv", sep=None, engine="python")
    s = ctx.csv("delta_cluster_timeseries.csv")
    pdf = ctx.add("paper figure (vector paths of Fig. 4a)",
                  os.path.join(ctx.repo, "benchmark_papers", "05_Berkemeier2023.pdf"))
    p, _, _ = berkemeier_fig4a_extract.extract(pdf)
    b1, b2, b3 = split(box, [1.4, 1, 1], gap=10)
    ax = axes(fig, b1, label="i")
    for _, c in p.groupby("curve_id"):
        ax.plot(c.t, c.D, color="0.6", lw=0.45, zorder=1)
    for _, c in d.groupby("cell.id"):
        ax.plot(c.t, c.D, color=C_D, lw=0.35, alpha=0.45, zorder=2)
    ax.plot([], [], color=C_D, lw=0.8, label="agent, all cells")
    ax.plot([], [], color="0.6", lw=0.8, label="paper Fig. 4a, all cells (from the PDF's vector graphics)")
    ax.set(xlabel="time [Notch decay times]", ylabel="Delta activity", xlim=(0, 120), ylim=(0, 1.12))
    ax.legend(loc="lower right", bbox_to_anchor=(1, 0.12))  # free band between the 0.74 plateau and D ~ 0
    t = s.time_notch_decay_units
    ax = axes(fig, b2, label="ii")
    ax.plot(t, s.fraction_high_delta_cells, color=C_FRAC)
    ax.set(xlabel="time [Notch decay times]", ylabel="fraction of high-Delta cells", ylim=(0, None))
    ax = axes(fig, b3, label="iii")
    ax.plot(t, s.mean_high_delta_cluster_size_cells, color=C_CL)
    ax.set(xlabel="time [Notch decay times]", ylabel="mean high-Delta cluster size [cells]", ylim=(0, None))
