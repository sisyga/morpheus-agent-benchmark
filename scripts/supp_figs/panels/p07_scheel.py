"""Scheel et al. (2021): agent-only pattern ranges over time and final head/tail/Wnt profiles."""
from panels.common import axes, split

C_H, C_D, C_W = "#1f3fd6", "#c0392b", "#1e8449"  # paper colours of h (head), d (tail), w (Wnt)
CAPTION = ("Agent-only quantification: (i) spatial range (max − min) of head-cell density h and tail-cell density "
           "d vs time after cutting (ranges_raw.csv); (ii) profiles of h, d and the Wnt signal w along the "
           "regenerating fragment at the final time (fields_raw.csv), to be compared with the cutting → "
           "regeneration column of Fig. 2 and with Fig. 5 in a. x and time in the paper's units.")


def draw(ctx, fig, box):
    r = ctx.csv("ranges_raw.csv")
    f = ctx.csv("fields_raw.csv")
    b1, b2 = split(box, [1, 1.2], gap=12)
    ax = axes(fig, b1, label="i")
    ax.plot(r["T"], r.h_range, color=C_H, label="head cells h")
    ax.plot(r["T"], r.d_range, color=C_D, ls=(0, (3, 2)), label="tail cells d")
    ax.set(xlabel="time [model units]", ylabel="spatial range (max − min)", xlim=(0, r["T"].max()), ylim=(0, None))
    ax.legend(loc="lower right")
    T = f["T"].max()
    e = f[f["T"] == T].sort_values("x_paper")
    ax = axes(fig, b2, label="ii")
    ax.plot(e.x_paper, e.h, color=C_H, label="head cells h")
    ax.plot(e.x_paper, e.d, color=C_D, label="tail cells d")
    ax.plot(e.x_paper, e.wnt, color=C_W, label="Wnt signal w")
    ax.set(xlabel="position x", ylabel=f"level at t = {T:g}", ylim=(0, None))
    ax.legend(loc="upper left", bbox_to_anchor=(0.1, 1.0))
