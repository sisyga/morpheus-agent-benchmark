"""Carpenter et al. (2024): cell number vs paper Fig. 2A (apoptosis on); apoptotic cells; mean cell area in
units of A_s (the paper's notation for the model constant A_S). Panel b gets the colour key of the run's growth
palette."""

import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle

import paper_data
import style
from figure import FIG_H, FIG_W, mm_axes, text
from panels.common import AGENT_LABEL, axes, legend, paper, paper_label, split

C_N, C_APO, C_AREA = "#1e8449", "#b9770e", "#5d6d7e"
# visual_growth palette of the run's Gnuplotter (gnuplot_commands_1_*.gp: set palette defined (-0.6 'yellow',
# -0.5 '#b54d00', 0 '#e7f2d4', 0.5 '#00652a'), cbrange [-0.6:0.5]); -0.6 = apoptotic cells, drawn flat yellow
GROWTH_CMAP = LinearSegmentedColormap.from_list("growth", [(0, "#b54d00"), (0.5, "#e7f2d4"), (1, "#00652a")])
C_APOPTOTIC = "#ffff00"
B_KEY_H = 9.0  # mm below the frames: growth colour bar and the apoptotic-cell patch
B_CAPTION = ("the left one, inside its frame lines (pixels 1–399 of 400 in x, 1–398 in y): cells "
             "coloured by visual_growth, the change of the cell's area in the last MCS divided by "
             "G₀ = A_isolated/(2τ₀) ≈ 7.1 pixels per MCS, clipped to −0.5…0.5 (brown #b54d00 shrinking, pale #e7f2d4 no growth, green #00652a growing; colour bar below the "
             "frames; the preprint's colour bar in a reads ±5G, the published ±0.5 G); apoptotic cells are "
             "drawn flat yellow; τ₀ = 225 MCS")
CAPTION = ("(i) Cell number vs time (quantification.csv: time_tau0, number_of_cells; agent-generated model, "
           "apoptosis on) with Carpenter et al. (2024): the data points of the apoptosis-on curve of Fig. 2A "
           "(means of five simulations), from the published PDF's vector graphics "
           "(carpenter_fig2a_extract.py; 03_Carpenter2024/fig2A_apoptosis_on_vector.csv) and shown up to "
           "{p_t} τ₀, where the paper has {p_n} cells; the agent's model ends at {t_end} τ₀ with {n_end}. "
           "(ii) Cells currently apoptotic (shrinking before removal), logged every 0.35 τ₀ "
           "(quantification.csv: number_apoptotic). "
           "(iii) Mean cell area (occupied area / number of cells) in units of A_s (the model constant A_S = "
           "1377 pixels, the mean G1 size threshold), as on the area axis of Fig. 2D (quantification.csv: "
           "mean_cell_area_in_sizer_units). "
           "It starts at {a0} A_s (the single initial cell, a disc of area A_s/2) and grows to {apeak} A_s "
           "before the first division at {tdiv} τ₀; the saw-tooth of the next, nearly synchronous divisions "
           "damps as the population desynchronises; it ends at {aend} A_s.")


# Publication legend (legend.py): keys are the panel letters as printed; legend.py prepends the run sentence to the
# frames panel and fills {graph} and the {name} fields of ctx.fmt.
LEGEND = {
    "cite": "carpenter2024",  # bib key (morpheusai_supp.bib) cited after every mention of the authors
    "title": "Cell proliferation in a growing epithelial colony (Carpenter *et al.*, 2024).",
    "a": "Cell number with and without apoptosis, cell area against distance from the colony center with apoptosis, "
         "and colonies colored by growth rate without (top) and with apoptosis (bottom), from the preprint of Carpenter *et al.* (adapted from its Fig. 2A, D–F).",
    "b": "Colony growth from a single cell, with apoptosis. Cells are colored by the change of their area in the "
         "last Monte Carlo step relative to the reference growth rate G₀ (color bar); apoptotic cells are yellow.",
    "c": "{graph}",
    "d": "**i**, Cell number in the agent's model (line) and in Carpenter *et al.* (circles; data from Fig. 2A of the published article), both with apoptosis. **ii**, Number of apoptotic cells, which shrink before they "
         "are removed. **iii**, Mean cell area in units of A<sub>s</sub>, as in Fig. 2D of Carpenter *et al.* It "
         "starts at {a0} A<sub>s</sub> with the single initial cell and oscillates with the first, nearly "
         "synchronous divisions; the oscillations damp as the divisions lose synchrony.",
    "abbrev": "A<sub>s</sub>, mean G1 size threshold; G₀, reference growth rate of the agent's model; τ₀, mean "
              "duration of the S/G2/M phase, the unit of time.",
    "license": "Material from the preprint of Carpenter *et al.* is adapted under a CC BY 4.0 license.",
}


def draw_b_key(fig, pos, y):
    """Below panel b's frames, centred: the run's growth colour bar (visual_growth, −0.5…0.5) and a patch for
    the flat yellow of apoptotic cells."""
    x0 = pos[0][0]
    x1 = pos[-1][0] + pos[-1][2]
    bw, bh = 30.0, 1.6
    xb = (x0 + x1) / 2 - (bw + 18.0) / 2
    text(fig, xb + bw / 2, y + 0.1, "Area growth per MCS / G$_0$", ha="center", fontsize=style.FS)
    ax = mm_axes(fig, xb, y + 3.0, bw, bh)
    g = np.linspace(-0.5, 0.5, 201)
    ax.pcolormesh(g, [0, 1], g[None, :-1] + 0.0025, cmap=GROWTH_CMAP, vmin=-0.5, vmax=0.5, shading="flat")
    ax.set(xlim=(-0.5, 0.5), ylim=(0, 1), yticks=[])
    ax.set_xticks([-0.5, 0, 0.5], ["≤ −0.5", "0", "≥ 0.5"])
    for s in ("left", "right", "top"):
        ax.spines[s].set_visible(True)
    xp = xb + bw + 5.0
    fig.patches.append(Rectangle((xp / FIG_W, 1 - (y + 3.0 + bh) / FIG_H), 2.6 / FIG_W, bh / FIG_H,
                                 transform=fig.transFigure, fc=C_APOPTOTIC, ec="0.3", lw=0.3))
    text(fig, xp + 3.5, y + 2.5, "Apoptotic", fontsize=style.FS)


def draw(ctx, fig, box):
    d = ctx.csv("quantification.csv")
    # Fig. 2A apoptosis on, vertices of the published PDF's vector path (carpenter_fig2a_extract.py), shown up to
    # the first data point at or after the end of the agent's run
    p = pd.read_csv(ctx.add("paper data", paper_data.path("03_Carpenter2024/"
                                                        "fig2A_apoptosis_on_vector.csv")))
    t_end, n_end = d.time_tau0.iloc[-1], d.number_of_cells.iloc[-1]
    p_end = p[p.t_tau0 >= t_end].iloc[0]
    p = p[p.t_tau0 <= p_end.t_tau0]
    ctx.fmt.update(t_end=f"{t_end:g}", n_end=f"{n_end:.0f}", p_t=f"{p_end.t_tau0:.1f}", p_n=f"{p_end.cells:.0f}")
    b1, b2, b3 = split(box, [1.3, 1, 1], gap=10)
    ax = axes(fig, b1, label="i")
    ax.plot(d.time_tau0, d.number_of_cells, color=C_N, label=AGENT_LABEL)
    paper(ax, p.t_tau0, p.cells, label=paper_label("Carpenter", 2024))
    ax.set(xlabel="Time (τ$_0$)", ylabel="Cell number", xlim=(0, np.ceil(p_end.t_tau0 + 0.5)), ylim=(0, None))
    legend(ax, loc="lower right")
    ax = axes(fig, b2, label="ii")
    ax.plot(d.time_tau0, d.number_apoptotic, color=C_APO)
    ax.set(xlabel="Time (τ$_0$)", ylabel="Cells currently apoptotic", xlim=(0, None), ylim=(0, None))
    ax = axes(fig, b3, label="iii")
    a = d.mean_cell_area_in_sizer_units
    ax.plot(d.time_tau0, a, color=C_AREA)
    ax.set(xlabel="Time (τ$_0$)", ylabel="Mean cell area (A$_s$)", xlim=(0, None), ylim=(0, None))
    i_div = int(np.argmax(np.diff(d.number_of_cells.to_numpy()) > 0))  # last logged time before the first division
    ctx.fmt.update(a0=f"{a.iloc[0]:.2f}", apeak=f"{a.iloc[:i_div + 1].max():.2f}",
                   tdiv=f"{d.time_tau0.iloc[i_div]:.1f}–{d.time_tau0.iloc[i_div + 1]:.1f}", aend=f"{a.iloc[-1]:.2f}")
