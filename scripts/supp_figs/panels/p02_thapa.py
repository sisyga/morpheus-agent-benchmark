"""Thapa et al. (2024): senescent area vs paper Fig. 4D (Model 4); fold change of the other populations."""
from panels.common import axes, fold, legend, paper, split

SEN, NON, CAN = "#c40000", "#f0606a", "#4fb000"  # panel-b colours
B_LEGEND = [(SEN, "senescent mesothelial"), (NON, "non-senescent mesothelial"), (CAN, "cancer")]
CAPTION = ("(i) Senescent-cell area relative to t = 0 (cell_counts.csv, sen_area_px) with the Model 4 curve of "
           "Fig. 4D (digitised, 2_Thappa_2024/model_4.csv; fold change of the initial senescent area). "
           "(ii) Fold change (vs t = 0) of cancer and non-senescent cell numbers (cell_counts.csv).")


def draw(ctx, fig, box):
    d = ctx.csv("cell_counts.csv")
    p = ctx.paper("2_Thappa_2024/model_4.csv")
    b1, b2 = split(box, [1, 1])
    ax = axes(fig, b1, label="i")
    ax.plot(d.time_hours, fold(d.sen_area_px), color=SEN, label="agent")
    paper(ax, p.x, p.y, label="paper Fig. 4D, Model 4 (digitised)")
    ax.axhline(1, color="0.7", lw=0.4, zorder=0)
    ax.set(xlabel="time [h]", ylabel="senescent area / area at t = 0", xlim=(0, None), ylim=(0, None))
    legend(ax, loc="lower left")
    ax = axes(fig, b2, label="ii")
    ax.plot(d.time_hours, fold(d.cancer_cells), color=CAN, label="cancer")
    ax.plot(d.time_hours, fold(d.non_senescent_cells), color=NON, label="non-senescent")
    ax.axhline(1, color="0.7", lw=0.4, zorder=0)
    ax.set(xlabel="time [h]", ylabel="cell number / number at t = 0", xlim=(0, None))
    legend(ax, loc="upper left")
