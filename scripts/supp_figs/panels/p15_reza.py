"""Reza et al. (2025): agent-only zone cell numbers and mean GST, GS, glutamine per zone vs time."""
from panels.common import axes, split
import style

A_SHARE = 0.55
B_LEGEND = [("#c0392b", "Z1-HLO (mCherry)"), ("#1e8449", "Z3-HLO (GFP)")]
C_Z1, C_Z3 = "#c0392b", "#1e8449"  # panel b: Z1-HLO (mCherry) red, Z3-HLO (GFP) green
TYPES = {2: ("Z1-HLO", C_Z1), 3: ("Z3-HLO", C_Z3)}  # cell.type index in cells.csv (model.xml order)
CAPTION = ("Agent-only quantification: (i) number of Z1-HLO and Z3-HLO cells vs time (counts.csv); mean per cell "
           "of (ii) GST activity, (iii) GS activity and (iv) glutamine output per zone (cells.csv: gst, gs, "
           "glutamine; model units), to be compared qualitatively with Fig. 4g–i in a. Frames in b show the lineage plot of the run (first Gnuplotter panel).")


def draw(ctx, fig, box):
    n = ctx.csv("counts.csv")
    n = n.loc[:, ~n.columns.duplicated()]
    d = ctx.csv("cells.csv")
    d = d.loc[:, ~d.columns.duplicated()]
    m = d[d["cell.type"].isin(TYPES)].groupby(["elapsed_days", "cell.type"])[["gst", "gs", "glutamine"]].mean()
    bs = split(box, [1, 1, 1, 1], gap=7)
    ax = axes(fig, bs[0], label="i", left=8.5)
    ax.plot(n.elapsed_days, n["celltype.Z1.size"], color=C_Z1, label="Z1-HLO")
    ax.plot(n.elapsed_days, n["celltype.Z3.size"], color=C_Z3, label="Z3-HLO")
    ax.set(xlabel="time [days]", ylabel="cells", xlim=(0, n.elapsed_days.max()), ylim=(0, None))
    ax.legend(loc="lower right")
    for b, col, lab, sub in zip(bs[1:], ["gst", "gs", "glutamine"], ["GST activity", "GS activity",
                                                                     "glutamine output"], ["ii", "iii", "iv"]):
        ax = axes(fig, b, label=sub, left=8.5)
        for t, (name, c) in TYPES.items():
            s = m[col].xs(t, level="cell.type")
            ax.plot(s.index, s.values, color=c, label=name)
        ax.text(0.03, 0.99, lab, transform=ax.transAxes, va="top", fontsize=style.FS_SMALL)
        ax.set(xlabel="time [days]", xlim=(0, s.index.max()), ylim=(0, None))
        if sub == "ii":
            ax.set_ylabel("mean per cell [model units]")
