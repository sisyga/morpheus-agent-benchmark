"""Carpenter et al. (2024): cell number vs paper Fig. 2A (apoptosis on); dying cells; mean cell area."""
from panels.common import axes, legend, paper, split

C_N, C_APO, C_AREA = "#1e8449", "#b9770e", "#5d6d7e"
CAPTION = ("(i) Cell number vs time in units of τ₀ (quantification.csv: time_tau0, number_of_cells) with the "
           "apoptosis-on curve of Fig. 2A (digitised, 3_Carpenter_2024/apoptosis_on.csv; the paper's y axis is in "
           "units of 10³ cells, converted to cells). (ii) Number of apoptotic (dying) cells. (iii) Mean cell area "
           "relative to the area of an isolated cell (quantification.csv: "
           "mean_cell_area_relative_to_isolated_cell).")


def draw(ctx, fig, box):
    d = ctx.csv("quantification.csv")
    p = ctx.paper("3_Carpenter_2024/apoptosis_on.csv")
    b1, b2, b3 = split(box, [1.3, 1, 1], gap=10)
    ax = axes(fig, b1, label="i")
    ax.plot(d.time_tau0, d.number_of_cells, color=C_N, label="agent (apoptosis on)")
    paper(ax, p.x, p.y * 1000, label="paper Fig. 2A, apoptosis on (digitised)", ms=1.8)
    ax.set(xlabel="time [τ$_0$]", ylabel="cell number", xlim=(0, None), ylim=(0, None))
    legend(ax, loc="upper left")
    ax = axes(fig, b2, label="ii")
    ax.plot(d.time_tau0, d.number_apoptotic, color=C_APO)
    ax.set(xlabel="time [τ$_0$]", ylabel="apoptotic cells", xlim=(0, None), ylim=(0, None))
    ax = axes(fig, b3, label="iii")
    ax.plot(d.time_tau0, d.mean_cell_area_relative_to_isolated_cell, color=C_AREA)
    ax.set(xlabel="time [τ$_0$]", ylabel="mean area / isolated-cell area", xlim=(0, None))
