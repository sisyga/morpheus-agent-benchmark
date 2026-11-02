"""Luque et al. (2023): hepatocyte and HCC numbers relative to the initial hepatocytes vs Fig. 10b; the two bulk
signals that gate liver and cancer proliferation in the agent's model."""
import os
import xml.etree.ElementTree as ET

import pandas as pd
from matplotlib.lines import Line2D

import paper_data
import style
from panels.common import AGENT_LABEL, axes, legend, paper_label, split

# frame colours of the run's Gnuplotter (cell.type ColorMap pink / royalblue at opacity 0.85 on white, as rendered:
# #ffc9c9 and #5d7fe5, the only flat cell colours in the frames); pink and blue stay apart for colour-blind readers,
# so the frames are not recoloured. The hepatocyte line is a darker shade of the frame pink so it shows on white.
F_HEP, F_HCC = "#ffc9c9", "#5d7fe5"
C_HEP, C_HCC = "#e07b91", F_HCC
C_GF, C_X = "#E69F00", "#009E73"  # Okabe-Ito orange and bluish green for the two signals
# the paper's data in the line colours of its Fig. 10b (hepatocytes green, cancer blue)
C_P_HEP, C_P_HCC = "#008000", "#0000ff"
P_LINE = dict(lw=style.LW_DATA, ls=(0, (2.5, 1.5)), zorder=3)
GF_PROL = 0.25  # model.xml Global Constant GF_prol, the threshold of all three gates
B_LEGEND = [(F_HEP, "Hepatocytes"), (F_HCC, "HCC cells")]
B_CAPTION = ("cells coloured by cell.type as in the run's ColorMap (white medium, pink hepatocytes, royal-blue HCC "
             "cells, drawn at opacity 0.85, i.e. #ffc9c9 and #5d7fe5 on white; not recoloured), cropped inside "
             "Gnuplot's frame lines (pixels 1–599 of 600 in x, 1–598 in y) and outlined in grey; whole "
             "250 × 250-node lattice, 1 node = 4 µm")
CAPTION = ("(i) Fold increase, as on the y axis of the paper's Fig. 10b: hepatocyte and HCC cell numbers divided "
           "by the initial number of hepatocytes ({h0}) vs time (cell_counts.csv: liver_cell_count = "
           "celltype.liver.size, cancer_cell_count = celltype.cancer.size; agent-generated model, solid lines: "
           "hepatocytes pink, a darker shade of the frame colour, HCC cells blue) with Luque et al. (2023), "
           "dashed, in the paper's colours (hepatocytes green, cancer blue): the mean lines of Fig. 10b "
           "(40 simulations, p. 16) as daily values, extracted from the PDF's raster image by "
           "luque_fig10b_extract.py (09_Luque2023/fig10b_hepatocytes.csv, fig10b_cancer.csv). The paper does not "
           "define the normaliser (Fig. 10 caption, p. 17; text, p. 16). A common denominator, the initial number "
           "of hepatocytes, is the only reading consistent with both curves (hepatocytes 1 and cancer 0 at day 0, "
           "cancer {p_c60} at day 60), and cell numbers rather than volume fit the hepatocyte curve ({p_h1} at "
           "day 1, {p_h8} at day 8): the paper's hepatocytes divide from day 2 after the hepatectomy (p. 12; "
           "Figs. 6e and 8b), whereas its liver volume rises at once through hypertrophy (Fig. 6b, d, whose "
           "captions name volume). The agent's model is 2D ({lattice}-node {lclass} lattice, model.xml), whereas "
           "Luque et al. simulate a 3D liver (a reduced spherical model, p. 6; Fig. 10a), so the cell numbers and "
           "their fold increases are not expected to match quantitatively: cell numbers scale differently with "
           "dimension. The agent's HCC number stops rising at {n_hcc} cells on day {t_full}, when the cells fill "
           "the 2D lattice (b, day 60). "
           "(ii) The two well-mixed signals of the agent's model (mechanism_diagnostics.csv, every 0.25 days, "
           "dimensionless): the regenerative growth factor (growth_factor; relaxes to the liver-mass deficit "
           "1 − 0.3 × liver volume / initial liver volume) and the homeostatic signal X (homeostatic_signal_X; "
           "secreted in proportion to the liver volume, saturating at 1). Dashed line: the threshold "
           "GF_prol = 0.25 of the model's gates: hepatocytes enter hypertrophy while the growth factor is above "
           "it and the cell cycle only while X is below it; HCC cells enter the cell cycle only once X ≥ 0.25. "
           "X reaches 0.25 on day {t_x} (maximum {x_max}), the last hepatocyte division is logged on day "
           "{t_liver} and the first HCC division on day {t_hcc}.")


# Publication legend (legend.py): keys are the panel letters as printed; legend.py prepends the run sentence to the
# frames panel and fills {graph} and the {name} fields of ctx.fmt.
LEGEND = {
    "cite": "luque2023",  # bib key (morpheusai_supp.bib) cited after every mention of the authors
    "title": "Liver regeneration and recurrence of hepatocellular carcinoma (Luque *et al.*, 2023).",
    "a": "The 3D liver of Luque *et al.* after partial hepatectomy, with a growing tumor (blue), and the fold "
         "increase of hepatocytes and cancer cells (mean of 40 simulations), adapted from their Fig. 10a, b.",
    "b": "Hepatocytes and HCC cells in the agent's 2D model (key below).",
    "c": "{graph}",
    "d": "**i**, Fold increase of hepatocytes and HCC cells, that is, cell numbers divided by the initial number of "
         "hepatocytes, in the agent's model (solid lines) and in Luque *et al.* (dashed lines in the colors of their "
         "Fig. 10b; data from that panel). The agent's model is 2D and the paper's is 3D, so the numbers are not "
         "expected to match. The HCC cells stop increasing on day {t_full}, when they fill the lattice. **ii**, The "
         "two well-mixed signals of the agent's model: a growth factor that follows the loss of liver mass, and a "
         "homeostatic signal X that rises with liver volume. Hepatocytes divide only while X is below the threshold "
         "(dashed line), and HCC cells only once X has reached it, on day {t_x}.",
    "abbrev": "HCC, hepatocellular carcinoma.",
    "license": "Material from Luque *et al.* is adapted under a CC BY 4.0 license.",
}


def draw(ctx, fig, box):
    d = ctx.csv("cell_counts.csv", sep=None, engine="python")
    m = ctx.csv("mechanism_diagnostics.csv", sep=None, engine="python")
    # Fig. 10b mean lines (40 runs), daily values extracted from the PDF's raster by luque_fig10b_extract.py
    h, c = (pd.read_csv(ctx.add("paper data", paper_data.path("09_Luque2023/"
                                                            f"fig10b_{k}.csv"))) for k in ("hepatocytes", "cancer"))
    ph, pc = h.set_index("day").fold, c.set_index("day").fold
    ctx.fmt.update(p_h1=f"{ph[1]:.2f}", p_h8=f"{ph[8]:.2f}", p_c60=f"{pc[60]:.2f}")
    b1, b2 = split(box, [1.25, 1], gap=12)

    ax = axes(fig, b1, label="i")
    h0 = d.liver_cell_count.iloc[0]
    lat = ET.parse(os.path.join(ctx.att, "model.xml")).getroot().find("Space/Lattice")
    size = [int(float(v)) for v in lat.find("Size").get("value").split(",")]
    assert len(size) < 3 or size[2] <= 1, "Luque model.xml lattice is not 2D"
    ctx.fmt.update(h0=f"{h0}", lattice=" × ".join(str(v) for v in size[:2]), lclass=lat.get("class"))
    ax.plot(d.time_days, d.liver_cell_count / h0, color=C_HEP)
    ax.plot(d.time_days, d.cancer_cell_count / h0, color=C_HCC)
    ax.plot(h.day, h.fold, color=C_P_HEP, **P_LINE)
    ax.plot(c.day, c.fold, color=C_P_HCC, **P_LINE)
    hnd = [Line2D([], [], color=C_HEP, label=f"{AGENT_LABEL}, hepatocytes"),
           Line2D([], [], color=C_HCC, label=f"{AGENT_LABEL}, HCC cells"),
           Line2D([], [], color=C_P_HEP, label=paper_label("Luque", 2023) + ", hepatocytes", **P_LINE),
           Line2D([], [], color=C_P_HCC, label=paper_label("Luque", 2023) + ", cancer", **P_LINE)]
    ax.set(xlabel="Time (days)", ylabel="Fold increase", xlim=(-1.5, 62), ylim=(-0.3, None))
    legend(ax, handles=hnd, loc="upper left")

    ax = axes(fig, b2, label="ii")
    ax.axhline(GF_PROL, color="0.45", lw=0.5, ls=(0, (3, 2)), zorder=1)
    ax.plot(m.time_days, m.growth_factor, color=C_GF, label="Growth factor")
    ax.plot(m.time_days, m.homeostatic_signal_X, color=C_X, label="Homeostatic signal X")
    ax.text(61, GF_PROL - 0.02, "Threshold 0.25", ha="right", va="top")
    ax.set(xlabel="Time (days)", ylabel="Signal (dimensionless)", xlim=(-1.5, 62), ylim=(0, 0.75))
    legend(ax, loc="upper right")

    x = m.homeostatic_signal_X
    full = d.cancer_cell_count == d.cancer_cell_count.max()
    lv = m.liver_cell_count.diff() > 0
    cv = m.cancer_cell_count.diff() > 0
    ctx.fmt.update(t_x=f"{m.time_days[(x >= GF_PROL).idxmax()]:g}", x_max=f"{x.max():.4f}",
                   t_liver=f"{m.time_days[lv[lv].index[-1]]:g}", t_hcc=f"{m.time_days[cv.idxmax()]:g}",
                   t_full=f"{d.time_days[full.idxmax()]:.0f}", n_hcc=f"{d.cancer_cell_count.max()}")
