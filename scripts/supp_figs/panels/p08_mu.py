"""Mu et al. (2024): B-cell numbers (total, dark zone, light zone) vs Fig. 3A; mean affinity vs Fig. 4A."""
from matplotlib.lines import Line2D

from panels.common import axes, paper, split

AB_LAYOUT = "side"
C_TOT, C_DZ, C_LZ, C_AFF = "#444444", "#c0392b", "#1e8449", "#7d3c98"
SERIES = [("total", "8_Mu/total.csv", C_TOT, "o"), ("dark zone", "8_Mu/DZ.csv", C_DZ, "s"),
          ("light zone", "8_Mu/LZ.csv", C_LZ, "^")]
CAPTION = ("(i) Number of B cells, total and per zone, vs time (aggregate_raw.csv: dark zone = B_left, the "
           "CXCL12/CRC half; light zone = B_right, the CXCL13/FDC half; total = sum) with Fig. 3A (digitised, "
           "8_Mu/total.csv, DZ.csv, LZ.csv; paper y axis in units of 10³ cells, converted to cells). "
           "(ii) Mean B-cell affinity (aggregate_raw.csv: affinity_mean) with Fig. 4A (digitised, "
           "8_Mu/mean_affinity.csv). The paper's time axis is in units of 100 MCS and is read as hours "
           "(paper: 100 MCS ≈ 1 h); the agent's model logs time in hours.")


def draw(ctx, fig, box):
    d = ctx.csv("aggregate_raw.csv")
    b1, b2 = split(box, [1.25, 1], gap=12)
    ax = axes(fig, b1, label="i")
    agent = {"total": d.B_left + d.B_right, "dark zone": d.B_left, "light zone": d.B_right}
    for name, rel, c, m in SERIES:
        p = ctx.paper(rel)
        ax.plot(d.time_hours, agent[name], color=c)
        paper(ax, p.x, p.y * 1000, label=None, marker=m, ms=2.0)
    h = [Line2D([], [], color=c, label=f"agent, {n}") for n, _, c, _ in SERIES] + \
        [Line2D([], [], lw=0, marker=m, mfc="none", mec="0.15", mew=0.6, ms=2.5, label=f"paper Fig. 3A, {n}")
         for n, _, _, m in SERIES]
    ax.legend(handles=h, loc="upper left", ncol=2, fontsize=4.8)
    ax.set(xlabel="time [h]  (paper: 100 MCS read as 1 h)", ylabel="B cells", xlim=(0, None), ylim=(0, None))
    p = ctx.paper("8_Mu/mean_affinity.csv")
    ax = axes(fig, b2, label="ii")
    ax.plot(d.time_hours, d.affinity_mean, color=C_AFF, label="agent")
    paper(ax, p.x, p.y, label="paper Fig. 4A (digitised)", ms=2.0)
    ax.set(xlabel="time [h]  (paper: 100 MCS read as 1 h)", ylabel="mean affinity", xlim=(0, None))
    ax.legend(loc="upper left")
