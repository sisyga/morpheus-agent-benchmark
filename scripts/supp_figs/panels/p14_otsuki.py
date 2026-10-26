"""Otsuki et al. (2025): agent-only mean per-cell signals by lineage and cell number vs time."""
from panels.common import axes, split

C_P, C_A, C_MEM, C_SHH, C_FGF, C_N = "#1f3a93", "#5dade2", "#c71585", "#e67e22", "#9a7d0a", "#444444"
CAPTION = ("Agent-only quantification (cells.csv, population.csv): (i) mean Hand2 per cell of the original "
           "posterior (P) and anterior (A) lineages and mean acquired posterior memory of A-lineage cells; "
           "(ii) mean Shh and Fgf8 sensed per cell (both lineages); (iii) number of connective-tissue cells. "
           "Amputation at day 0.")


def draw(ctx, fig, box):
    d = ctx.csv("cells.csv")
    d = d.loc[:, ~d.columns.duplicated()]
    pop = ctx.csv("population.csv")
    g = d.groupby(["time_days", "lineage"])[["hand2", "memory"]].mean().unstack()
    a = d.groupby("time_days")[["shh_seen", "fgf_seen"]].mean()
    b1, b2, b3 = split(box, [1.2, 1, 1], gap=10)
    ax = axes(fig, b1, label="i")
    ax.plot(g.index, g["hand2"][1], color=C_P, label="Hand2, P lineage")
    ax.plot(g.index, g["hand2"][0], color=C_A, ls=(0, (3, 1.5)), label="Hand2, A lineage")
    ax.plot(g.index, g["memory"][0], color=C_MEM, label="posterior memory, A lineage")
    ax.set(xlabel="time after amputation [days]", ylabel="mean per cell", xlim=(0, g.index.max()), ylim=(0, None))
    ax.legend(loc="upper right", fontsize=4.8)
    ax = axes(fig, b2, label="ii")
    ax.plot(a.index, a.shh_seen, color=C_SHH, label="Shh")
    ax.plot(a.index, a.fgf_seen, color=C_FGF, ls=(0, (3, 1.5)), label="Fgf8")
    ax.set(xlabel="time after amputation [days]", ylabel="mean signal sensed per cell", xlim=(0, a.index.max()),
           ylim=(0, None))
    ax.legend(loc="upper right")
    ax = axes(fig, b3, label="iii")
    ax.plot(pop.time_days, pop["celltype.CT.size"], color=C_N)
    ax.set(xlabel="time after amputation [days]", ylabel="connective-tissue cells", xlim=(0, pop.time_days.max()))
