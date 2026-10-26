"""Herron et al. (2022): agent-only range of active GTPase u, with the paper's rosette-formation window."""
from panels.common import axes, split

C_MAX, C_MIN = "#d35400", "#1b2a6b"
CAPTION = ("Agent-only quantification (the paper reports no matching time course): maximum and minimum of the "
           "active membrane-bound GTPase u over the domain vs time (u_range.csv). Shaded: 0–20 s, the time in "
           "which the rosette pattern forms in the paper.")


def draw(ctx, fig, box):
    d = ctx.csv("u_range.csv")
    b1, _ = split(box, [1.2, 1.6], gap=10)
    ax = axes(fig, b1)
    ax.axvspan(0, 20, color="0.92", lw=0, zorder=0)
    ax.text(10, 0.5, "rosette formation\n(paper, 0–20 s)", transform=ax.get_xaxis_transform(), ha="center",
            va="center", fontsize=5, color="0.4")
    ax.plot(d.time_s, d.u_max_molecules_per_um2, color=C_MAX, label="max u")
    ax.plot(d.time_s, d.u_min_molecules_per_um2, color=C_MIN, label="min u")
    ax.set(xlabel="time [s]", ylabel="active GTPase u [molecules/µm²]", xlim=(0, d.time_s.max()), ylim=(0, None))
    ax.legend(loc="center right")
