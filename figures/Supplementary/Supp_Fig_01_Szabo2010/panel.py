"""Szabó et al. (2010): RMS cell displacement vs paper Fig. 7b (monolayer, α = 2); mean cell speed; co-moving flow
field (compare Fig. 10c). Panel a (agent frames) gets column labels and the polarity colour wheel here."""
import numpy as np
import pandas as pd

from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D

import style
from figure import mm_axes, text
from panels.common import AGENT_LABEL, axes, legend, paper, paper_label, split

UM_PER_NODE = 5.0  # node_length_um in the agent's model.xml
MIN_PER_MCS = 1.0  # TimeSymbol: 1 MCS = 1 minute
T0_MIN = 100  # start times for displacements: after the initial relaxation of the packed monolayer
C_DISP, C_SPEED, C_DIR = "#c0392b", "#c0392b", "#1e8449"
# polarity.phi palette of the run's Gnuplotter (gnuplot_commands_1_*.gp: set palette defined (0 'red', 1.0472
# 'yellow', 2.0944 'green', 3.14159 'cyan', 4.18879 'blue', 5.23599 'magenta', 6.28319 'red'), gnuplot's named colours)
PHI_CMAP = LinearSegmentedColormap.from_list(
    "gnuplot_phi", list(zip(np.linspace(0, 1, 7),
                            ["#ff0000", "#ffff00", "#00ff00", "#00ffff", "#0000ff", "#ff00ff", "#ff0000"])), N=1024)
B_KEY_H = 9.5  # mm below the frames: column labels and the polarity angle colour bar
B_CAPTION = ("left half of each frame: cells coloured by cell.id (Gnuplot's cyclic 10-colour palette, which only "
             "tells neighbouring cells apart); right half: cells coloured by their polarity direction polarity.phi "
             "(0–2π, the run's cyclic palette red–yellow–green–cyan–blue–magenta–red; angle colour bar below the first "
             "frame) "
             "with arrows along the polarity vector; frames at 0, 360 and 1440 MCS (1 MCS = 1 min, as defined in the "
             "agent's model.xml)")
CAPTION = ("(i) RMS displacement d(t) (eq. 1 of Szabó et al. (2010)) vs time lag, log-log, from cell_tracks.tsv.csv "
           "(cell centres logged every MCS; squared displacements averaged over all cells and all start times "
           "t0 ≥ 100 MCS; 1 MCS = 1 min and 1 node = 5 µm as defined in the agent's model.xml). Agent-generated "
           "model: α = 4, P = 3, the benchmark target (Fig. 10c, d); Szabó et al. (2010): the monolayer curve of "
           "Fig. 7b, digitised (01_Szabo2010/monolayer.csv, recalibrated, see Data handling), for α = 2, P = 2, "
           "T = 5 min (the paper has no monolayer displacement curve for α = 4 or P = 3; its P = 3 curve, Fig. 6a, "
           "is of single, non-interacting cells). (ii) Instantaneous cell speed vs time: the "
           "centroid displacement per MCS, averaged over cells (population.tsv.csv: mean_speed, nodes per MCS "
           "converted to µm h⁻¹); it includes the CPM centroid fluctuations, so it exceeds the net speed from (i), "
           "{v1h} µm h⁻¹ at a 1 h lag and {v10h} µm h⁻¹ at a 10 h lag. The benchmark asks for a final mean speed "
           "of 0.05–0.25 node per MCS (15–75 µm h⁻¹); the paper gives no monolayer speed for α = 4, P = 3. "
           "The interior area fraction stays between {area_min} and "
           "{area_max} (0–24 h; not plotted). (iii) Co-moving flow field: mean velocity of neighbouring cells in "
           "the frame of a moving cell (positions x, y relative to the moving cell, rotated so that it moves along "
           "+x, green arrow; all cells, every 20 MCS from t = 100 MCS; cell_tracks.tsv.csv), positions in µm; "
           "arrow length proportional to the mean neighbour velocity (longest arrow = 45 µm for {vmax} µm h⁻¹), "
           "colour = neighbour speed (colour bar); compare Fig. 10c (α = 4) of Szabó et al. (2010), whose colours "
           "show the relative standard error instead. The upper half is faster than the lower half because the "
           "sheet, confined to the closed domain, turns into one clockwise rotation (normalised angular momentum "
           "about its centre {rot6} at 6 h and {rot24} at 23–24 h; −1 for rigid clockwise rotation), the "
           "rotating phase of Szabó et al. (2010), p. 7: a cell moving along +x then lies above the centre, and "
           "its neighbours below, nearer the centre, move more slowly.")


# Publication legend (legend.py): keys are the panel letters as printed; legend.py prepends the run sentence to the
# frames panel and fills {graph} and the {name} fields of ctx.fmt.
LEGEND = {
    "cite": "szabo2010",  # bib key (morpheusai_supp.bib) cited after every mention of the authors
    "title": "Collective cell motion in an endothelial monolayer (Szabó *et al.*, 2010).",
    "a": "Cells are colored by identity (the palette only separates neighbors) and by polarity direction (color "
         "scale below), with arrows along the polarity vectors.",
    "b": "{graph}",
    "c": "**i**, RMS displacement of cells against time lag in the agent's model (α = 4, the benchmark case) and in "
         "the monolayer simulation of Szabó *et al.* (circles; digitized from their Fig. 7b). The paper has no "
         "displacement curve for α = 4, so the comparison uses its curve for α = 2. **ii**, Instantaneous cell "
         "speed, averaged over all cells. It includes the fluctuations of the cell centers and therefore exceeds the "
         "net speed in **i** ({v1h} µm h⁻¹ over a 1 h lag). **iii**, Mean velocity of the neighbors of a moving cell "
         "(green arrow, moving along +x), for comparison with Fig. 10c of Szabó *et al.*; arrow length and color "
         "show the neighbor speed. The upper half of the field is faster because the sheet turns into a single "
         "clockwise rotation in the closed domain: a cell moving along +x lies above the center of rotation, and its "
         "neighbors below it, nearer the center, move more slowly.",
    "abbrev": "α, cost of cell–cell boundaries in the cellular Potts model; RMS, root mean square.",
}


def draw_b_key(fig, pos, y):
    """Below panel a's first frame: what the two halves of every frame show, and under the polarity half the
    angle colour bar of the run's polarity palette (polarity.phi, 0 to 2π, counter-clockwise from +x)."""
    x, _, w, _ = pos[0]
    for frac, lab in ((0.25, "Cell identity"), (0.75, "Polarity direction")):
        text(fig, x + frac * w, y + 0.2, lab, ha="center", fontsize=style.FS)
    bw = 0.46 * w
    ax = mm_axes(fig, x + 0.75 * w - bw / 2, y + 3.6, bw, 1.6)
    # one gradient image of 1024 palette steps: continuous, no seams between cells as with pcolormesh
    ax.imshow(np.linspace(0, 2 * np.pi, 1024)[None, :], extent=(0, 2 * np.pi, 0, 1), aspect="auto", cmap=PHI_CMAP,
              vmin=0, vmax=2 * np.pi, interpolation="nearest")
    ax.set(xlim=(0, 2 * np.pi), ylim=(0, 1), yticks=[])
    ax.set_xticks(np.arange(5) * np.pi / 2, ["0", "π/2", "π", "3π/2", "2π"])
    for s in ("left", "right", "top"):
        ax.spines[s].set_visible(True)


def tracks(ctx):
    d = ctx.csv("cell_tracks.tsv.csv", sep="\t",
                usecols=["time", "cell.id", "cell.center.x", "cell.center.y", "velocity.x", "velocity.y"])
    d = d.loc[:, ~d.columns.duplicated()]
    return d


def displacement(d, lags):
    """RMS displacement (µm) for each lag (MCS), over all cells and all start times t0 >= T0_MIN: d(t) of eq. 1 of
    Szabó et al. (2010)."""
    x = d.pivot(index="time", columns="cell.id", values="cell.center.x").to_numpy()
    y = d.pivot(index="time", columns="cell.id", values="cell.center.y").to_numpy()
    t = np.sort(d.time.unique())
    i0 = int(np.searchsorted(t, T0_MIN))
    out = []
    for L in lags:
        dx = x[i0 + L:] - x[i0:-L]
        dy = y[i0 + L:] - y[i0:-L]
        out.append(np.sqrt(np.nanmean(dx ** 2 + dy ** 2)))
    return np.array(out) * UM_PER_NODE


def rotation(d, t0, lag=60):
    """Normalised angular momentum of the sheet about its centre of mass, sum(r x v) / sum(|r| |v|), with v the
    displacement from t0 to t0 + lag: -1 for a rigid clockwise rotation, +1 counter-clockwise, ~0 without one."""
    f0 = d[d.time == t0].set_index("cell.id")[["cell.center.x", "cell.center.y"]]
    f1 = d[d.time == t0 + lag].set_index("cell.id").loc[f0.index, ["cell.center.x", "cell.center.y"]]
    r = f0.to_numpy() - f0.to_numpy().mean(0)
    v = f1.to_numpy() - f0.to_numpy()
    return (r[:, 0] * v[:, 1] - r[:, 1] * v[:, 0]).sum() / (np.hypot(*r.T) * np.hypot(*v.T)).sum()


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


def summaries(ctx, lags):
    """Panel d's numbers from the 131 MB track log, as small tables (Ctx.summary): RMS displacement per lag,
    the mean neighbour flow field, and the rotation at 6 h and 24 h."""
    cache = {}

    def d():
        if "d" not in cache:
            cache["d"] = tracks(ctx)
        return cache["d"]

    def flow():
        c, vx, vy = flow_field(d())
        ib, ia = np.meshgrid(np.arange(len(c)), np.arange(len(c)), indexing="ij")
        return pd.DataFrame({"row": ib.ravel(), "col": ia.ravel(), "centre_row": c[ib.ravel()],
                             "centre_col": c[ia.ravel()], "vx": vx.ravel(), "vy": vy.ravel()})

    disp = ctx.summary("szabo_rms_displacement", lambda: pd.DataFrame(
        {"lag_mcs": lags, "rms_displacement_um": displacement(d(), lags)}))
    fl = ctx.summary("szabo_flow_field", flow)
    rot = ctx.summary("szabo_rotation", lambda: pd.DataFrame(
        {"t0_mcs": [360, 1440 - 60], "rotation": [rotation(d(), 360), rotation(d(), 1440 - 60)]}))
    n = int(fl.row.max()) + 1
    grid = lambda col: fl[col].to_numpy().reshape(n, n)  # noqa: E731
    return (disp.set_index("lag_mcs").rms_displacement_um, (fl.centre_col.to_numpy()[:n], grid("vx"), grid("vy")),
            rot.set_index("t0_mcs").rotation)


def draw(ctx, fig, box):
    lags = np.unique(np.round(np.logspace(0, np.log10(1440 - T0_MIN - 1), 40)).astype(int))
    disp, flow, rot = summaries(ctx, np.union1d(lags, [60, 600]))
    pop = ctx.csv("population.tsv.csv", sep="\t")
    p = ctx.paper("01_Szabo2010/monolayer.csv")
    b1, b2, b3 = split(box, [1.1, 0.95, 1.15], gap=11)

    ax = axes(fig, b1, label="i")
    ax.loglog(lags * MIN_PER_MCS / 60, disp.loc[lags].to_numpy(), color=C_DISP, label=AGENT_LABEL + ", α = 4")
    paper(ax, p.x, p.y, label=paper_label("Szabó", 2010) + ", α = 2")
    ax.set(xlabel="Time lag (h)", ylabel="RMS displacement (µm)")
    legend(ax, loc="lower right")

    ax = axes(fig, b2, label="ii")
    th = pop.time * MIN_PER_MCS / 60
    ax.plot(th, pop.mean_speed * UM_PER_NODE / MIN_PER_MCS * 60, color=C_SPEED)
    ax.set(xlabel="Time (h)", ylabel="Instantaneous cell speed (µm h$^{-1}$)", xlim=(0, th.max()), ylim=(0, None))
    net = disp.loc[[60, 600]].to_numpy() / np.array([1.0, 10.0])  # µm per h over 1 h and 10 h lags (MCS = min)
    ctx.fmt.update(v1h=f"{net[0]:.0f}", v10h=f"{net[1]:.0f}")
    ctx.fmt.update(area_min=f"{pop.interior_area_fraction.min():.3f}",
                   area_max=f"{pop.interior_area_fraction.max():.3f}")

    ax = axes(fig, b3, label="iii", left=10.0, right=11.0)
    c, vx, vy = flow
    k = UM_PER_NODE / MIN_PER_MCS * 60  # nodes per MCS -> µm per h
    X, Y = np.meshgrid(c * UM_PER_NODE, c * UM_PER_NODE)
    vx, vy = vx * k, vy * k
    mag = np.hypot(vx, vy)
    longest = 45.0  # µm drawn for the fastest mean neighbour velocity
    q = ax.quiver(X, Y, vx, vy, mag, cmap="plasma_r", angles="xy", scale_units="xy", pivot="mid",
                  scale=np.nanmax(mag) / longest, width=0.006, headwidth=3, headlength=3, headaxislength=2.7)
    ax.annotate("", xy=(90, 0), xytext=(0, 0), arrowprops=dict(arrowstyle="-|>", color=C_DIR, lw=0.8))
    ax.axhline(0, color="0.8", lw=0.3, zorder=0)
    ax.axvline(0, color="0.8", lw=0.3, zorder=0)
    ax.set(xlim=(-310, 310), ylim=(-310, 310), aspect="equal",
           xlabel="x (µm)", ylabel="y (µm)")
    cb = fig.colorbar(q, ax=ax, fraction=0.06, pad=0.04)
    cb.set_label("Neighbour speed (µm h$^{-1}$)", fontsize=style.FS_LABEL)
    cb.ax.tick_params(labelsize=style.FS, width=0.5, length=2.0)
    cb.outline.set_linewidth(0.5)
    ax.legend(handles=[Line2D([], [], color=C_DIR, lw=0.8, marker=">", ms=3.0, label="Moving cell")],
              loc="lower left", bbox_to_anchor=(0.0, 1.0), borderaxespad=0.3)
    ctx.fmt.update(vmax=f"{np.nanmax(mag):.0f}", rot6=f"{rot[360]:.2f}".replace("-", "−"),
                   rot24=f"{rot[1440 - 60]:.2f}".replace("-", "−"))
