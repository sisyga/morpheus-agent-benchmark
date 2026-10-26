"""Berkhout et al. (2025): cell numbers per tissue vs the original CC3D model; other tissues left vs right."""
from panels.common import axes, split, vsplit
import style

D_HEIGHT = 62.0
# tissue colours of the paper's Fig. 1 legend (the agent's Gnuplotter uses the same scheme)
COL = {"surface_ectoderm": "#6f8ee8", "neural_crest": "#e77fd0", "mesoderm": "#ef8f8a", "somite": "#c0504d",
       "neuroectoderm": "#b48ae0", "floor_plate": "#8a6aa8", "notochord": "#79b86a", "endoderm": "#a8595e",
       "neural_crest_delaminated": "#c2509f"}
PAIRS = [("surface_ectoderm", "N_Surface_Ectoderm_y", "surface ectoderm"),
         ("neural_crest", "N_Neural_Crest_y", "neural crest"),
         ("mesoderm", "N_Mesoderm_y", "paraxial mesoderm"),
         ("somite", "N_Somite_y", "somite")]
OTHER = [("neuroectoderm", "neuroectoderm"), ("floor_plate", "floor plate"), ("notochord", "notochord"),
         ("endoderm", "endoderm"), ("neural_crest_delaminated", "delaminated neural crest")]
CAPTION = ("(i) Number of cells per tissue (left + right half) vs time (native_cell_counts_by_half.csv) with the "
           "time course of the paper's original CompuCell3D model (output file 10_Berkhout_2025/"
           "My_cNTC_timecourse_hours.csv; grey, dashed). Absolute numbers differ because the "
           "models resolve cells at different sizes. (ii) The other tissues, left (solid) vs right (dashed) half.")


def draw(ctx, fig, box):
    d = ctx.csv("native_cell_counts_by_half.csv")
    p = ctx.paper("10_Berkhout_2025/My_cNTC_timecourse_hours.csv")
    r1, r2 = vsplit(box, [1, 1], gap=3)
    for i, (b, (col, pcol, lab)) in enumerate(zip(split(r1, [1] * 4, gap=6), PAIRS)):
        ax = axes(fig, b, label="i" if i == 0 else None, left=8.5, bottom=7)
        ax.plot(p["Time (hours)"], p[pcol], color="0.45", lw=0.7, ls=(0, (2.5, 1.5)), label="paper model (CC3D)")
        ax.plot(d.time_hours, d[col + "_left"] + d[col + "_right"], color=COL[col], label="agent")
        ax.text(0.03, 1.02, lab, transform=ax.transAxes, va="bottom", fontsize=style.FS_SMALL, color=COL[col])
        ax.set(xlabel="time [h]", ylim=(0, None), xlim=(0, 50))
        if i == 0:
            ax.set_ylabel("cells")
        if i == 3:
            ax.legend(loc="center right")
    for i, (b, (col, lab)) in enumerate(zip(split(r2, [1] * 5, gap=5), OTHER)):
        ax = axes(fig, b, label="ii" if i == 0 else None, left=8.0, bottom=7)
        ax.plot(d.time_hours, d[col + "_left"], color=COL[col], label="left")
        ax.plot(d.time_hours, d[col + "_right"], color=COL[col], ls=(0, (3, 1.5)), label="right")
        ax.text(0.03, 1.02, lab, transform=ax.transAxes, va="bottom", fontsize=style.FS_SMALL, color=COL[col])
        top = max(d[col + "_left"].max(), d[col + "_right"].max())
        ax.set(xlabel="time [h]", ylim=(0, top * 1.15 + 1), xlim=(0, 50))
        if i == 0:
            ax.set_ylabel("cells per half")
            ax.legend(loc="lower left")
