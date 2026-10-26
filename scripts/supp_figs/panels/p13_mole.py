"""Mole et al. (2026): agent-only trophectoderm outgrowth distance vs time."""
import numpy as np

from panels.common import axes, split

UM_PER_NODE = 3.0  # dx_um in the agent's model.xml
C_MEAN, C_MAX = "#8e4585", "#8e4585"  # panel-b trophectoderm colour
CAPTION = ("Agent-only quantification: trophectoderm outgrowth, the distance of trophoblast cells (trophectoderm "
           "and invasive trophoblast, cells.csv) from the centroid of the trophectoderm at 6 d.p.f., mean "
           "(solid) and maximum (dashed) over cells, vs embryo age (1 node = 3 µm as defined in the agent's "
           "model.xml). Dotted lines: the stages of Fig. 3A.")


def draw(ctx, fig, box):
    d = ctx.csv("cells.csv", sep="\t")
    d = d.loc[:, ~d.columns.duplicated()]
    tro = d[d.is_trophoblast == 1]
    t0 = tro.dpf.min()
    c0 = tro[tro.dpf == t0][["cell.center.x", "cell.center.y"]].mean().to_numpy()
    r = tro.assign(dist=np.hypot(tro["cell.center.x"] - c0[0], tro["cell.center.y"] - c0[1]) * UM_PER_NODE)
    g = r.groupby("dpf").dist
    b1, _ = split(box, [1.2, 1.6], gap=10)
    ax = axes(fig, b1)
    ax.plot(g.mean().index, g.mean().values, color=C_MEAN, label="mean")
    ax.plot(g.max().index, g.max().values, color=C_MAX, ls=(0, (3, 1.5)), label="maximum")
    for x, lab in [(6, "apposition"), (7, "adhesion"), (8, "implantation")]:
        ax.axvline(x, color="0.7", lw=0.4, ls=":", zorder=0)
        ax.text(x + 0.03, 0.99, lab, transform=ax.get_xaxis_transform(), fontsize=5, color="0.4", va="top")
    ax.set(xlabel="embryo age [d.p.f.]", ylabel="trophoblast distance from initial centroid [µm]",
           xlim=(t0, d.dpf.max()), ylim=(0, None))
    ax.legend(loc="lower right")
