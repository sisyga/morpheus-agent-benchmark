"""Szabó et al. (2010): mean cell displacement vs paper Fig. 7b (monolayer); area fraction and speed;
co-moving flow field (compare Fig. 10c)."""
import numpy as np
import pandas as pd

from panels.common import axes, legend, paper, split

UM_PER_NODE = 5.0  # node_length_um in the agent's model.xml
MIN_PER_MCS = 1.0  # TimeSymbol: 1 MCS = 1 minute
T0_MIN = 100  # start times for displacements: after the initial relaxation of the packed monolayer
C_DISP, C_AREA, C_SPEED = "#c0392b", "#2e86c1", "#c0392b"
CAPTION = ("(i) Mean displacement of the cells vs time lag, log-log, from cell_tracks.tsv.csv (cell centres "
           "logged every MCS; displacement averaged over all cells and all start times t0 ≥ 100 MCS; "
           "1 MCS = 1 min and 1 node = 5 µm as defined in the agent's model.xml), with the monolayer curve of "
           "Fig. 7b (digitised, 1_Szabo_2010/monolayer.csv, recalibrated, see Data handling; the single-cell curve "
           "of Fig. 7b is not shown, the benchmark target is the α = 4 monolayer). "
           "(ii) Interior area fraction and mean cell speed vs time (population.tsv.csv). "
           "(iii) Co-moving flow field: mean velocity of neighbouring cells in the frame of a moving cell "
           "(rotated so that the cell moves along +x; all cells, every 20 MCS from t = 100 MCS; "
           "cell_tracks.tsv.csv), to be compared with Fig. 10c (α = 4) in a.")


def tracks(ctx):
    d = ctx.csv("cell_tracks.tsv.csv", sep="\t",
                usecols=["time", "cell.id", "cell.center.x", "cell.center.y", "velocity.x", "velocity.y"])
    d = d.loc[:, ~d.columns.duplicated()]
    return d


def displacement(d, lags):
    x = d.pivot(index="time", columns="cell.id", values="cell.center.x").to_numpy()
    y = d.pivot(index="time", columns="cell.id", values="cell.center.y").to_numpy()
    t = np.sort(d.time.unique())
    i0 = int(np.searchsorted(t, T0_MIN))
    out = []
    for L in lags:
        dx = x[i0 + L:] - x[i0:-L]
        dy = y[i0 + L:] - y[i0:-L]
        out.append(np.nanmean(np.hypot(dx, dy)))
    return np.array(out) * UM_PER_NODE


def flow_field(d, R=60, nb=12):
    edges = np.linspace(-R, R, nb + 1)
    sx = np.zeros((nb, nb))
    sy = np.zeros((nb, nb))
    n = np.zeros((nb, nb))
    for t in range(T0_MIN, int(d.time.max()) + 1, 20):
        f = d[d.time == t]
        p = f[["cell.center.x", "cell.center.y"]].to_numpy()
        v = f[["velocity.x", "velocity.y"]].to_numpy()
        sp = np.hypot(v[:, 0], v[:, 1])
        ok = sp > 0
        e = np.zeros_like(v)
        e[ok] = v[ok] / sp[ok, None]
        rel = p[None, :, :] - p[:, None, :]  # j relative to i
        a = (rel * e[:, None, :]).sum(-1)  # along the motion of i
        b = rel[..., 1] * e[:, None, 0] - rel[..., 0] * e[:, None, 1]  # perpendicular
        va = (v[None, :, :] * e[:, None, :]).sum(-1)
        vb = v[None, :, 1] * e[:, None, 0] - v[None, :, 0] * e[:, None, 1]
        m = ok[:, None] & (np.abs(a) < R) & (np.abs(b) < R) & ~np.eye(len(p), dtype=bool)
        ia = np.digitize(a[m], edges) - 1
        ib = np.digitize(b[m], edges) - 1
        np.add.at(sx, (ib, ia), va[m])
        np.add.at(sy, (ib, ia), vb[m])
        np.add.at(n, (ib, ia), 1)
    c = (edges[:-1] + edges[1:]) / 2
    with np.errstate(invalid="ignore"):
        return c, sx / n, sy / n


def draw(ctx, fig, box):
    d = tracks(ctx)
    pop = ctx.csv("population.tsv.csv", sep="\t")
    p = ctx.paper("1_Szabo_2010/monolayer.csv")
    b1, b2, b3 = split(box, [1.15, 1.1, 0.95], gap=11)

    ax = axes(fig, b1, label="i")
    lags = np.unique(np.round(np.logspace(0, np.log10(1440 - T0_MIN - 1), 40)).astype(int))
    ax.loglog(lags * MIN_PER_MCS / 60, displacement(d, lags), color=C_DISP, label="agent (α = 4)")
    paper(ax, p.x, p.y, label="paper Fig. 7b, monolayer (digitised)", ms=1.8)
    ax.set(xlabel="time lag [h]  (1 MCS = 1 min)", ylabel="mean displacement [µm]  (1 node = 5 µm)")
    legend(ax, loc="upper left")

    ax = axes(fig, b2, label="ii", right=9)
    th = pop.time * MIN_PER_MCS / 60
    ax.plot(th, pop.interior_area_fraction, color=C_AREA)
    ax.set(xlabel="time [h]", ylabel="interior area fraction", ylim=(0.9, 1.005))
    ax.yaxis.label.set_color(C_AREA)
    ax2 = ax.twinx()
    ax2.spines["right"].set_visible(True)
    ax2.plot(th, pop.mean_speed * UM_PER_NODE / MIN_PER_MCS * 60, color=C_SPEED)
    ax2.set_ylabel("mean cell speed [µm/h]", color=C_SPEED)
    ax2.set_ylim(0, None)

    ax = axes(fig, b3, label="iii", left=8)
    c, vx, vy = flow_field(d)
    X, Y = np.meshgrid(c, c)
    mag = np.hypot(vx, vy)
    ax.quiver(X, Y, vx, vy, mag, cmap="plasma_r", angles="xy", scale_units="xy", pivot="mid",
              scale=np.nanmax(mag) / 9, width=0.006, headwidth=3, headlength=3, headaxislength=2.7)
    ax.annotate("", xy=(18, 0), xytext=(0, 0), arrowprops=dict(arrowstyle="-|>", color="#1e8449", lw=0.9))
    ax.axhline(0, color="0.8", lw=0.3, zorder=0)
    ax.axvline(0, color="0.8", lw=0.3, zorder=0)
    ax.set(xlim=(-62, 62), ylim=(-62, 62), aspect="equal",
           xlabel="x relative to moving cell [nodes]", ylabel="y [nodes]")
    ctx.note("Flow-field arrows: length proportional to the mean neighbour velocity (longest = 9 nodes); "
             "colour = speed, dark = fast, as in Fig. 10c.")
