"""Berkemeier & Page (2023): per-cell Delta, high-Delta fraction and mean cluster size of the agent's eps = 1 run vs
the final eps = 1 pattern of paper Fig. 1f (the paper shows no Delta time courses at eps = 1). Panel b gets the
colour bar of the run's Delta palette."""
import os

import numpy as np
from matplotlib.colors import LinearSegmentedColormap

import berkemeier_fig1f_extract
import style
from figure import mm_axes, text
from panels.common import AGENT_LABEL, axes, legend, paper_label, split

AB_LAYOUT = "side"
# D palette of the run's Gnuplotter (model.xml: Cells value="D" min="0" max="1", ColorMap 0 -> #65ad2f,
# 1 -> white), linear in RGB as gnuplot's "set palette defined"
D_CMAP = LinearSegmentedColormap.from_list("delta", [(0, "#65ad2f"), (1, "#ffffff")])
C_D, C_FRAC, C_CL = "#4d9a2a", "#4d9a2a", "#566573"  # agent: a darker shade of the frames' low-Delta green
# two authors: "Berkemeier & Page (2023)", no "et al."
PAPER = paper_label("Berkemeier & Page", 2023, et_al=False) + ",\nFig. 1f (ε = 1)"
# time axis: the model's dimensionless time t, in units of the Notch decay time τ_N
T_LABEL = "Time $\\mathit{t}$ (τ$_\\mathrm{N}$)"
B_KEY_H = 8.0  # mm below the frames: Delta colour bar
B_CAPTION = ("each frame is the run's Gnuplotter plot cropped inside its plot frame (pixels 23–710 of 900 in x, "
             "59–652 of 703 in y; the Gnuplot title, the colour bar and the time tick label are cropped off and "
             "replaced by the frame labels and the colour bar below the frames): cells coloured by their Delta "
             "activity D with the run's palette, #65ad2f (green) at D = 0 to white at D = 1, linear in RGB "
             "(model.xml Gnuplotter ColorMap); white areas outside the black cell outlines are the plot "
             "background around the 14 × 14 periodic hexagonal lattice; t is the dimensionless time of the model in "
             "units of the Notch decay time τ_N (Eqs. 1–2 of the paper); the pattern at t = 10 τ_N is the same as at 100 τ_N")
CAPTION = ("(i) Delta activity D of all {a_n} cells of the agent's 14 × 14 lattice at ε = 1 (cell_states.csv) vs "
           "time t in units of the Notch decay time τ_N, the dimensionless time of Eqs. 1–2. The cells end at two "
           "levels (medians {a_hi} and {a_lo} at t = 100 τ_N). The paper shows no D time courses at ε = 1, so "
           "(i) has no paper data. (ii) Fraction of cells with "
           "high Delta (D ≥ 0.5, the agent's threshold; delta_cluster_timeseries.csv: fraction_high_delta_cells) and "
           "(iii) mean size of the high-Delta clusters (connected components of high-Delta cells on the six direct "
           "neighbours of the periodic lattice, singletons included; mean_high_delta_cluster_size_cells, set to "
           "0 while there is no high-Delta cell), logged every 100/99 τ_N. Dashed lines: Fig. 1f (p. 3; ε = 1, "
           "14 × 14 lattice), counted from the PDF's vector fills (berkemeier_fig1f_extract.py; white = high Delta): "
           "{p_high} of {p_n} cells high ({p_frac}) in {p_ncl} clusters of mean size {p_mean} cells. Agent at "
           "t = 100 τ_N: {a_high} of {a_n} cells ({a_frac}), {a_ncl} clusters of mean size {a_mean} cells "
           "(the same algorithm applied to cell_states.csv reproduces the logged values).")


# Publication legend (legend.py): keys are the panel letters as printed; legend.py prepends the run sentence to the
# frames panel and fills {graph} and the {name} fields of ctx.fmt.
LEGEND = {
    "cite": "berkemeier2023",  # bib key (morpheusai_supp.bib) cited after every mention of the authors
    "title": "Notch–Delta patterning with long-range signaling (Berkemeier & Page, 2023).",
    "a": "Final pattern of Delta activity on a 14 × 14 periodic hexagonal lattice at ε = 1, where cells signal only "
         "through long-range protrusions, from Berkemeier & Page (adapted from their Fig. 1f, with the color bar of "
         "their Fig. 1c–f).",
    "b": "Delta activity *D* of each cell at dimensionless times *t*, in units of the Notch decay time τ<sub>N</sub> "
         "(color bar below). The pattern is final by *t* = 10 τ<sub>N</sub>.",
    "c": "{graph}",
    "d": "**i**, Delta activity of each cell against time (one line per cell); the cells settle at two levels. The "
         "paper has no time course at ε = 1, so **i** shows the agent's model only. **ii**, Fraction of cells with "
         "high Delta (*D* ≥ 0.5). **iii**, Mean size of clusters of adjacent high-Delta cells. In **ii** and **iii**, "
         "solid lines show the agent's model and dashed lines the pattern of Fig. 1f of Berkemeier & Page, counted "
         "from the PDF ({p_high} of {p_n} cells high, in {p_ncl} clusters).",
    "license": "Material from Berkemeier & Page is adapted under a CC BY 4.0 license.",
}


def draw_b_key(fig, pos, y):
    """Below panel b's frames, centred: the colour bar of the run's Delta palette (D = 0…1, dimensionless)."""
    x0 = pos[0][0]
    x1 = pos[-1][0] + pos[-1][2]
    bw, bh = 30.0, 1.6
    xb = (x0 + x1) / 2 - bw / 2
    text(fig, xb + bw / 2, y + 0.1, "Delta activity D", ha="center", fontsize=style.FS)
    ax = mm_axes(fig, xb, y + 3.0, bw, bh)
    g = np.linspace(0, 1, 201)
    ax.pcolormesh(g, [0, 1], g[None, :-1] + 0.0025, cmap=D_CMAP, vmin=0, vmax=1, shading="flat")
    ax.set(xlim=(0, 1), ylim=(0, 1), yticks=[])
    ax.set_xticks([0, 0.5, 1], ["0", "0.5", "1"])
    for s in ("left", "right", "top"):
        ax.spines[s].set_visible(True)


def draw(ctx, fig, box):
    d = ctx.csv("cell_states.csv", sep=None, engine="python")
    s = ctx.csv("delta_cluster_timeseries.csv")
    pdf = ctx.add("paper figure (vector fills of Fig. 1f)",
                  os.path.join(ctx.repo, "benchmark_papers", "05_Berkemeier2023.pdf"))
    pn, ph, ps = berkemeier_fig1f_extract.fig1f(pdf)
    t_end = d.t.max()
    an, ah, as_ = berkemeier_fig1f_extract.cells(d, t_end)
    fin = d[np.isclose(d.t, t_end)].D
    ctx.fmt.update(p_n=pn, p_high=ph, p_low=pn - ph, p_frac=f"{ph / pn:.3f}", p_ncl=len(ps),
                   p_mean=f"{np.mean(ps):.2f}",
                   a_hi=f"{fin[fin >= 0.5].median():.4f}", a_lo=f"{fin[fin < 0.5].median():.4f}",
                   a_n=an, a_high=ah, a_frac=f"{ah / an:.3f}", a_ncl=len(as_), a_mean=f"{np.mean(as_):.2f}")
    b1, b2, b3 = split(box, [1.4, 1, 1], gap=10)

    ax = axes(fig, b1, label="i")
    for _, c in d.groupby("cell.id"):
        ax.plot(c.t, c.D, color=C_D, lw=0.35, alpha=0.45, zorder=2)
    ax.plot([], [], color=C_D, label=AGENT_LABEL + " (one line per cell)")
    ax.set(xlabel=T_LABEL, ylabel="Delta activity D", xlim=(0, t_end), ylim=(0, 1.05))
    legend(ax, loc="center right")

    t = s.time_notch_decay_units
    for b, col, y, ref, lab, c in ((b2, "fraction_high_delta_cells", "High-Delta fraction of cells", ph / pn, "ii",
                                    C_FRAC),
                                   (b3, "mean_high_delta_cluster_size_cells", "Mean high-Delta cluster size (cells)",
                                    np.mean(ps), "iii", C_CL)):
        ax = axes(fig, b, label=lab)
        ax.plot(t, s[col], color=c, label=AGENT_LABEL)
        ax.axhline(ref, **style.PAPER_LINE_KW, label=PAPER)
        ax.set(xlabel=T_LABEL, ylabel=y, xlim=(0, t.max()), ylim=(0, None))
        legend(ax, loc="lower right")
