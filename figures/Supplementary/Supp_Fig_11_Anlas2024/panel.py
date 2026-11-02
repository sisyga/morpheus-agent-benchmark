"""Anlas et al. (2024): final A-P profiles of Bra/T and Sox2 vs Fig. 1E; Bra/T profiles at 24, 48 and 72 h
(compare Fig. 1A); cell number. Panel b gets the run's three colour bars, grey sub-plot dividers and a scale bar."""
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

import config
import style
from figure import mm_axes, text
from panels.common import AGENT_LABEL, axes, legend, paper, paper_label, split

NBINS = 10
NODE_UM = 2.0  # NodeLength of the run's lattice (µm per node)
PX_PER_NODE = 400 / 140  # Gnuplotter sub-plot: 400 pixels for the 140-node lattice (fits the frames to 0.5 px)
# the run's Gnuplotter ColorMaps (model.xml): 0 black to 1 gnuplot's named colours green, purple and orange;
# identified in the frames from the initial levels Bra 0.05 -> #000c00, Sox2 0.9 -> #ad73e6, Cdh2 0.1 -> #191000
CHANNELS = [("Bra/T", "#00ff00"), ("Sox2", "#c080ff"), ("N-cadherin", "#ffa500")]
# line colours in d: darker shades of the frame colours (pure #00ff00 and #c080ff are too light for lines on white)
C_BRA, C_SOX, C_N = "#1e9a1e", "#8e5fd0", "#444444"
C_TIMES = {24: "#b2dfa8", 48: "#5fb85a", 72: C_BRA}  # Bra/T profiles in (ii), light to dark with time
# frame geometry after config.FRAME_CROP_PX (columns 1-1198, rows 74-323 of the 1200 x 400 frame)
X0, Y0 = config.FRAME_CROP_PX["11_Anlas2024"][0], config.FRAME_CROP_PX["11_Anlas2024"][2]
FW = config.FRAME_CROP_PX["11_Anlas2024"][1] - X0
FH = config.FRAME_CROP_PX["11_Anlas2024"][3] - Y0
DIVIDERS = (400, 799)  # frame columns of the Gnuplotter sub-plot borders
SUB = [(0, 400), (400, 799), (799, 1199)]  # frame columns of the three sub-plots
B_KEY_H = 7.6  # mm below the frames: the three colour bars
B_CAPTION = ("each frame holds three sub-plots of the same cells, left to right Bra/T, Sox2 and N-cadherin (Cdh2) "
             "per cell, each on the run's ColorMap from 0 (black) to 1 (Bra/T green #00FF00, Sox2 purple #C080FF, "
             "N-cadherin orange #FFA500; Gnuplotter min 0, max 1, higher values drawn as 1; colour bars below the "
             "first frame); the levels are the model's dimensionless expression variables; frames cropped to rows "
             "74–323 of 400 (the aggregate at every shown time) and columns 1–1198 of 1200, Gnuplot's black "
             "sub-plot borders drawn over in grey; scale bar 50 µm (1 lattice node = 2 µm, as defined in the "
             "agent's model.xml); frames at 0, 48 and 72 h after aggregation (in the model, CHIR99021 is applied "
             "uniformly from 48 to 72 h)")
CAPTION = ("(i) Bra/T and Sox2 along the anterior–posterior (A–P) axis at the final time, 72 h (cells.csv: per-cell "
           "Bra and Sox2, logged every hour): the A–P axis runs from the Sox2-weighted to the Bra-weighted centroid "
           "of the cell centres; cell centres are projected on it, scaled to 0–1 (most anterior to most posterior "
           "cell) and binned into 10 equal bins; each agent curve is the mean per bin divided by its largest bin "
           "mean (Bra/T {bra_max}, Sox2 {sox_max} in model units). Anlas et al. (2024), open markers: the Bra/T and Sox2 "
           "mean lines of the 72 hpa profile plot of Fig. 1E (right-hand panel, n = 5; not the 24 and 48 hpa "
           "plots of Fig. 1C, D, which the digitised points do not follow), digitised (11_Anlas2024/Bra_T.csv, "
           "Sox_2.csv), each divided by its maximum ({pb_max} and {ps_max} a.u.). (ii) Bra/T level (mean per bin, not normalised) along the A–P axis at "
           "24, 48 and 72 h, each time with its own axis defined as in (i), as the T profiles at 24, 48 and 72 hpa "
           "in Fig. 1A; at 24 h Bra/T is still nearly uniform ({bra24} in all cells), so the direction of that "
           "axis is arbitrary. (iii) Number of cells (population.csv: celltype.stem.size, logged every hour); the "
           "benchmark asked for 50 cells growing to 100 within 72 h. Bra/T (green) and Sox2 (purple) lines and markers in darker "
           "shades of the frame colours in b.")


# Publication legend (legend.py): keys are the panel letters as printed; legend.py prepends the run sentence to the
# frames panel and fills {graph} and the {name} fields of ctx.fmt.
LEGEND = {
    "cite": "anlass2024",  # bib key (morpheusai_supp.bib) cited after every mention of the authors
    "title": "Anteroposterior patterning in gastruloids (Anlaş *et al.*, 2024).",
    "a": "Bra/T expression from 24 to 72 hpa, in situ stainings of Bra/T, Foxa2 and Sox2 with their profiles along "
         "the A–P axis (their Fig. 1A–E), and Bra/T profiles at 72 hpa for different initial cell numbers (their "
         "Fig. 4B), adapted from Anlaş *et al.*",
    "b": "Each frame shows the same cells colored by their Bra/T, Sox2 and N-cadherin levels (color bars below; "
         "dimensionless). Scale bar, 50 µm.",
    "c": "{graph}",
    "d": "**i**, Bra/T and Sox2 along the A–P axis at {t_final} h, each divided by its maximum, in the agent's model "
         "(lines) and in Anlaş *et al.* (open markers; mean profiles at 72 hpa, digitized from their Fig. 1E). In "
         "the agent's model the A–P axis runs from the Sox2-weighted to the Bra/T-weighted center of the cells, and "
         "levels are averaged in bins along it. **ii**, Bra/T level along the A–P axis over time, as for T in Fig. "
         "1A of Anlaş *et al.* At 24 h Bra/T is nearly uniform, so the direction of the axis is arbitrary. **iii**, "
         "Number of cells.",
    "abbrev": "A–P, anterior–posterior; hpa, hours post-aggregation.",
    "license": "Material from Anlaş *et al.* is adapted under a CC BY 4.0 license.",
}


def ap_profile(c, cols):
    """Per-bin means of cols along the A-P axis (Sox2-weighted to Bra-weighted centroid) of cells c."""
    p = c[["cell.center.x", "cell.center.y"]].to_numpy()
    wa, wp = c.Sox2.to_numpy(), c.Bra.to_numpy()
    a = (p * wa[:, None]).sum(0) / wa.sum()
    b = (p * wp[:, None]).sum(0) / wp.sum()
    e = (b - a) / np.linalg.norm(b - a)
    s = p @ e
    s = (s - s.min()) / (s.max() - s.min())
    k = np.minimum((s * NBINS).astype(int), NBINS - 1)
    x = (np.arange(NBINS) + 0.5) / NBINS
    return x, {col: np.array([c[col].to_numpy()[k == i].mean() for i in range(NBINS)]) for col in cols}


def _mm(pos, col, row):
    """Frame pixel (column, row of the uncropped frame) -> figure mm, for a frame drawn at pos."""
    x, y, w, h = pos
    return x + (col - X0) / FW * w, y + (row - Y0) / FH * h


def draw_b_key(fig, pos, y):
    """Grey lines over Gnuplot's black sub-plot borders in every frame, below the first frame one colour bar under each
    of its three sub-plots, and below the last frame a 50 µm scale bar."""
    for p in pos:
        ax = mm_axes(fig, *p)
        ax.set_axis_off()
        ax.set(xlim=(X0, X0 + FW), ylim=(Y0 + FH, Y0))
        for c in DIVIDERS:
            ax.axvline(c + 0.5, color="0.5", lw=0.5)
    # scale bar below the last frame, right-aligned with it
    x, _, w, _ = pos[-1]
    L = 50 / NODE_UM * PX_PER_NODE / FW * w  # mm
    ax = mm_axes(fig, x + w - L, y + 3.2, L, 0.6)
    ax.set_axis_off()
    ax.set(xlim=(0, 1), ylim=(0, 1))
    ax.axhline(0.5, color="black", lw=1.0, solid_capstyle="butt")
    text(fig, x + w - L - 1.0, y + 3.5, "50 µm", ha="right", va="center", fontsize=style.FS)
    # colour bars
    p = pos[0]
    for (name, col), (c0, c1) in zip(CHANNELS, SUB):
        xs0, _ = _mm(p, c0, 0)
        xs1, _ = _mm(p, c1, 0)
        bw = 0.6 * (xs1 - xs0)
        xb0 = (xs0 + xs1) / 2 - bw / 2
        text(fig, xb0 + bw / 2, y + 0.1, name, ha="center", fontsize=style.FS)
        ax = mm_axes(fig, xb0, y + 2.7, bw, 1.6)
        ax.imshow(np.linspace(0, 1, 256)[None, :], extent=(0, 1, 0, 1), aspect="auto", vmin=0, vmax=1,
                  interpolation="bilinear", cmap=LinearSegmentedColormap.from_list(name, ["#000000", col]))
        ax.set(xlim=(0, 1), ylim=(0, 1), yticks=[])
        ax.set_xticks([0, 0.5, 1], ["0", "0.5", "1"])
        for s in ("left", "right", "top"):
            ax.spines[s].set_visible(True)


def draw(ctx, fig, box):
    d = ctx.csv("cells.csv", sep=None, engine="python")
    pop = ctx.csv("population.csv")
    T = d.time_h.max()
    ctx.fmt.update(t_final=f"{T:g}")  # final time of the profiles in (i) (legend)
    x, prof = ap_profile(d[d.time_h == T], ["Bra", "Sox2"])
    pb = ctx.paper("11_Anlas2024/Bra_T.csv")
    ps = ctx.paper("11_Anlas2024/Sox_2.csv")
    b1, b2, b3 = split(box, [1.45, 1.05, 0.8], gap=11)

    ax = axes(fig, b1, label="i")
    ax.plot(x, prof["Bra"] / prof["Bra"].max(), color=C_BRA, label=f"{AGENT_LABEL}, Bra/T")
    ax.plot(x, prof["Sox2"] / prof["Sox2"].max(), color=C_SOX, label=f"{AGENT_LABEL}, Sox2")
    # paper markers (open) in the colour of the agent's line of the same gene
    paper(ax, pb.x, pb.y / pb.y.max(), label=paper_label("Anlas", 2024) + ", Bra/T", color=C_BRA)
    paper(ax, ps.x, ps.y / ps.y.max(), label=paper_label("Anlas", 2024) + ", Sox2", marker="s", ms=2.3,
          color=C_SOX)
    ax.set(xlabel="Normalized length A → P", ylabel="Expression (fraction of maximum)", xlim=(0, 1), ylim=(0, 1.05),
           yticks=[0, 0.25, 0.5, 0.75, 1])
    legend(ax, loc="upper center", ncol=2)
    ctx.fmt.update(bra_max=f"{prof['Bra'].max():.2f}", sox_max=f"{prof['Sox2'].max():.2f}",
                   pb_max=f"{pb.y.max():.3f}", ps_max=f"{ps.y.max():.3f}")

    ax = axes(fig, b2, label="ii")
    for t, c in C_TIMES.items():
        xt, pt = ap_profile(d[d.time_h == t], ["Bra"])
        ax.plot(xt, pt["Bra"], color=c, label=f"{t} h")
    b24 = d[d.time_h == 24].Bra
    ctx.fmt.update(bra24=f"{b24.min():.2f}–{b24.max():.2f}")
    ax.set(xlabel="Normalized length A → P", ylabel="Bra/T level (model units)", xlim=(0, 1), ylim=(0, 1.05))
    legend(ax, loc="upper left")

    ax = axes(fig, b3, label="iii")
    ax.plot(pop.time_h, pop["celltype.stem.size"], color=C_N)
    ax.set(xlabel="Time (h)", ylabel="Cell number", xlim=(0, T), ylim=(0, 110), yticks=[0, 25, 50, 75, 100])
