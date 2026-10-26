"""Atwell et al. (2015): germ-cell numbers per Fig. 3 colour class vs Table S2 (single run of Fig. 3)."""
import config
import style
from panels.common import axes, paper, split

# panel-b colours (atwell_3d.py) and the Fig. 3 colour classes they correspond to
CLASSES = [("yellow", "fig3_yellow_cells", "#e6b400", "yellow cells (proliferative + meiotic S)"),
           ("green", "fig3_green_cells", "#228b22", "green cells (meiotic)"),
           ("blue", "fig3_blue_cells", "#1f3fd6", "blue cells (spermatocyte, sperm)"),
           ("pink", "fig3_pink_cells", "#d62020", "pink cells (oogenic)")]
B_LEGEND = [("#e6b400", "proliferative"), ("#228b22", "meiotic"), ("#87cefa", "spermatocyte"),
            ("#1f3fd6", "sperm"), ("#d62020", "oocyte"), ("#0f9b9b", "distal tip cell (DTC)")]
CAPTION = ("Number of germ cells per colour class of Atwell et al. Fig. 3 vs time in hours post hatching "
           "(cell_counts.csv: fig3_yellow/green/blue/pink_cells; lines) with the cell numbers of the single "
           "simulation shown in Fig. 3 (Table S2, crosses): (i) yellow, proliferative and meiotic S phase; "
           "(ii) green, meiotic; (iii) blue, spermatogenic and sperm; (iv) pink, oogenic. The agent's oocytes are "
           "drawn red in b. The benchmark run stopped at 53.3 hph, when it reached the benchmark's 1 h per-run time "
           "limit for Morpheus (model StopTime 87.5 hph); the Table S2 values at 60.5 and 87.5 hph therefore have no "
           "simulated counterpart (grey dotted line: last logged time).")


def draw(ctx, fig, box):
    d = ctx.csv("cell_counts.csv")
    t = config.ATWELL_TABLE_S2
    for i, (b, (cls, col, c, lab)) in enumerate(zip(split(box, [1, 1, 1, 1], gap=6), CLASSES)):
        ax = axes(fig, b, label=["i", "ii", "iii", "iv"][i], left=8.5)
        ax.plot(d.time_hph, d[col], color=c, label="agent")
        paper(ax, t["time_hph"], t[cls], label="paper Table S2", marker="x", ms=3, mew=0.8, mfc=None)
        ax.axvline(d.time_hph.max(), color="0.55", lw=0.6, ls=":", zorder=0)
        ax.set(xlabel="time [hph]", ylim=(0, None), xlim=(15, 90))
        if i == 0:
            ax.text(d.time_hph.max() + 1.5, 0.62, "run stopped\n(1 h limit)", transform=ax.get_xaxis_transform(),
                    va="top", fontsize=style.FS_SMALL, color="0.45")
        ax.set_ylabel(lab, color="#a07d00" if cls == "yellow" else c)  # darker gold keeps the text legible
        if i == 0:
            ax.legend(loc="lower right")
