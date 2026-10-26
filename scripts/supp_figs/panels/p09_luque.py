"""Luque et al. (2023): hepatocyte and HCC numbers relative to the initial hepatocytes vs Fig. 10b."""
from panels.common import axes, paper, split

C_HEP, C_HCC = "#e07b91", "#3a5bd0"  # panel-b colours (darker pink for the line)
B_LEGEND = [("#f4b6c0", "hepatocytes"), ("#3a5bd0", "HCC cells")]
CAPTION = ("Hepatocyte and HCC cell numbers divided by the initial number of hepatocytes vs time "
           "(cell_counts.csv: liver_cell_count, cancer_cell_count) with the mean curves of Fig. 10b (digitised, "
           "9_Luque_2023/hepatocytes.csv, cancer.csv). The digitised curves carry small calibration offsets "
           "(about −0.05 in y, cancer baseline below 0, and about −0.7 days in x); they are shown as digitised.")


def draw(ctx, fig, box):
    d = ctx.csv("cell_counts.csv", sep=None, engine="python")
    h = ctx.paper("9_Luque_2023/hepatocytes.csv")
    c = ctx.paper("9_Luque_2023/cancer.csv")
    b1, _ = split(box, [1.2, 1.4], gap=10)
    ax = axes(fig, b1)
    h0 = d.liver_cell_count.iloc[0]
    ax.plot(d.time_days, d.liver_cell_count / h0, color=C_HEP, label="agent, hepatocytes")
    ax.plot(d.time_days, d.cancer_cell_count / h0, color=C_HCC, label="agent, HCC")
    paper(ax, h.x, h.y, label="paper Fig. 10b, hepatocytes (digitised)", ms=1.8)
    paper(ax, c.x, c.y, label="paper Fig. 10b, cancer (digitised)", marker="s", ms=1.6)
    ax.set(xlabel="time [days]", ylabel="cells / initial hepatocytes", xlim=(-1.5, 62))
    ax.legend(loc="upper left")
