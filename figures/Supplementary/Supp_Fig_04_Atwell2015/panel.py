"""Atwell et al. (2015): germ-cell numbers per Fig. 3 colour class vs Table S2 (single run of Fig. 3)."""
from matplotlib import patheffects
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Rectangle
from matplotlib.textpath import TextToPath

import os

import pandas as pd

import atwell_3d
import atwell_tables2_extract
import config
import style
from figure import FIG_H, FIG_W, text
from panels.common import AGENT_LABEL, axes, legend, paper, paper_label, split

C = {k: c for k, (c, _) in atwell_3d.COLOURS.items()}  # panel-b render colours (cell types of main Figs. 1, 2)
# (Table S2 key, cell_counts.csv column, line colour, y label). Classes as defined by the run's Mappers
# (fig3_*_cells) and named as in Table S2; spermatogenic + sperm combines panel-b colours 3 and 4 and is drawn
# in the sperm blue
CLASSES = [("yellow", "fig3_yellow_cells", C[1], "Proliferative +\nmeiotic S cells"),
           ("green", "fig3_green_cells", C[2], "Meiotic prophase\ncells"),
           ("blue", "fig3_blue_cells", C[4], "Spermatogenic +\nsperm cells"),
           ("pink", "fig3_pink_cells", C[5], "Oogenic cells")]
# colour key of panel b, two rows of three (one row would be wider than panel b)
B_KEY = [[(C[1], "Proliferative + meiotic S"), (C[2], "Meiotic prophase"), (C[3], "Spermatogenic")],
         [(C[4], "Sperm"), (C[5], "Oogenic"), (atwell_3d.DTC_COLOUR[0], "Distal tip cell")]]
B_KEY_H = 6.4  # mm below the frames
B_SOURCE = ("3D renders (atwell_3d.py) of the run's raw CPM lattice states: its Morpheus checkpoint files (*.xml.gz) "
            "and, at 18.5 hph, the initial lattice rebuilt from model.xml; at "
            + ", ".join(lab for _, lab in config.ATWELL_FRAMES))
B_CAPTION = ("colour key below the frames; germ cells are coloured by the model's cell property colour, their "
             "Atwell et al. Fig. 3 class, which the run's Gnuplotter draws gold, forest green, light blue, blue "
             "and red; here they are drawn in the cell-type colours of the main Figs. 1 and 2: gold #e6b400, "
             "proliferative and meiotic S (phase < 6, fate 0: mitotic cycle, committed G1 and meiotic S phase); "
             "green #228b22, meiotic prophase (phase 6, fate 0); light blue #87cefa, spermatogenic (fate 1); blue "
             "#1f3fd6, sperm (fate 3; single-voxel cells, drawn as small spheres); red #d62020, oogenic (fate 2, "
             "growing, or 4, mature oocyte). The distal tip cell is no CPM cell in the "
             "model but a global leader coordinate (cell_counts.csv: dtc_x/y/z_um); it is drawn as a teal #0f9b9b "
             "sphere (radius 3 µm = 3 lattice nodes, a drawing choice; cyan in Atwell et al. Fig. 3) moved along its "
             "direction of migration to just ahead of the germ cells. Orthographic view onto the plane of the U, "
             "as in Fig. 3")
CAPTION = ("Current number of germ cells in each class of Atwell et al. Fig. 3 and Table S2 vs time in hours post "
           "hatching (hph), logged every 0.70 h (cell_counts.csv, lines; Mapper sums over all germ cells): "
           "(i) proliferative + meiotic S, the yellow cells of Fig. 3 (fig3_yellow_cells: phase < 6 and fate 0, "
           "i.e. mitotic cycle G1/S/G2/M, committed G1 and meiotic S); (ii) meiotic prophase, the green cells "
           "(fig3_green_cells: phase 6 and fate 0); (iii) spermatogenic + sperm, the blue cells "
           "(fig3_blue_cells: fate 1 or 3); (iv) oogenic, the pink cells (fig3_pink_cells: fate 2 or 4, growing "
           "and mature oocytes). Crosses: the cell counts of the single simulation shown in Atwell et al. Fig. 3 "
           "(supplementary Table S2, PDF page 23, columns Proliferative + Meiotic S, Meiotic, Sperm/Spermatogenic and "
           "Oogenic; read from the PDF's text by atwell_tables2_extract.py, cached copy 04_Atwell2025/tableS2_counts.csv). These counts are "
           "output of the authors' model, not experimental data, and Table S2 was part of the paper supplied to "
           "the agent. Line colours are "
           "those of b (iii in the sperm blue; the yellow line in i with a thin dark edge). The benchmark run stopped at 53.3 hph, "
           "when it reached the benchmark's 1 h per-run time limit for Morpheus (model StopTime 87.5 hph); the "
           "Table S2 values at 60.5 "
           "and 87.5 hph therefore have no simulated counterpart (grey dotted line: last logged time).")


# Publication legend (legend.py): keys are the panel letters as printed; legend.py prepends the run sentence to the
# frames panel and fills {graph} and the {name} fields of ctx.fmt.
LEGEND = {
    "cite": "atwell2015",  # bib key (morpheusai_supp.bib) cited after every mention of the authors
    "title": "Germ-line development in *C. elegans* (Atwell *et al.*, 2015).",
    "a": "Simulation snapshots from Atwell *et al.* (adapted from their Fig. 3).",
    "b": "The model at comparable stages, rendered in 3D from the raw lattice states of the run, with germ cells "
         "colored by class (key below). The model represents the distal tip cell as a moving point; it is drawn here "
         "as a sphere.",
    "c": "{graph}",
    "d": "Number of germ cells per class in the agent's model (lines, colored as in **b**) and in the simulation of "
         "Atwell *et al.* (crosses; data from their Table S2, which lists the output of the authors' model): "
         "proliferative and meiotic S-phase cells (**i**), meiotic prophase cells (**ii**), spermatogenic cells and "
         "sperm (**iii**) and oogenic cells (**iv**). The run stopped at {t_stop} hph (dotted line), when it reached "
         "the benchmark's limit of 1 h of Morpheus run time, so the later time points of Table S2 have no "
         "counterpart.",
    "abbrev": "hph, hours post-hatching.",
    "license": "Material from Atwell *et al.* is adapted under a CC BY 3.0 license.",
}


def draw_b_key(fig, pos, y):
    """Colour key of the render classes below panel b's frames, centred: two rows of patches in aligned columns."""
    x0, x1 = min(p[0] for p in pos), max(p[0] + p[2] for p in pos)
    fp = FontProperties(family="Arial", size=style.FS)
    tw = lambda lab: TextToPath().get_text_width_height_descent(lab, fp, ismath=False)[0] * 0.3528  # pt -> mm
    cols = [max(3.5 + tw(r[j][1]) for r in B_KEY) for j in range(3)]
    gap = 3.5
    xs = (x0 + x1) / 2 - (sum(cols) + gap * 2) / 2
    for i, row in enumerate(B_KEY):
        xx, yy = xs, y + 0.1 + 2.9 * i
        for (c, lab), w in zip(row, cols):
            fig.patches.append(Rectangle((xx / FIG_W, 1 - (yy + 2.1) / FIG_H), 2.6 / FIG_W, 1.8 / FIG_H,
                                         transform=fig.transFigure, fc=c, ec="0.3", lw=0.3))
            text(fig, xx + 3.5, yy, lab, fontsize=style.FS)
            xx += w + gap


def draw(ctx, fig, box):
    d = ctx.csv("cell_counts.csv")
    ctx.fmt.update(t_stop=f"{d.time_hph.max():.1f}")  # last logged time of the run (legend)
    pdf = ctx.add("paper PDF (Table S2, read by atwell_tables2_extract.py)",
                  os.path.join(ctx.repo, "benchmark_papers", "04_Atwell2025.pdf"))
    t = atwell_tables2_extract.extract(pdf)
    pd.testing.assert_frame_equal(t, ctx.paper("04_Atwell2025/tableS2_counts.csv"), check_dtype=False)
    for i, (b, (cls, col, c, lab)) in enumerate(zip(split(box, [1, 1, 1, 1], gap=6), CLASSES)):
        # top margin: room for the common legend in one row above the plots, below the numerals
        ax = axes(fig, b, label=["i", "ii", "iii", "iv"][i], left=12.5, top=7.6)
        # thin dark edge only on the light yellow line, so it stays visible on white
        edge = [patheffects.withStroke(linewidth=style.LW_DATA + 0.5, foreground="0.25"), patheffects.Normal()]
        ax.plot(d.time_hph, d[col], color=c, label=AGENT_LABEL, path_effects=edge if cls == "yellow" else None)
        paper(ax, t["time_hph"], t[cls], label=paper_label("Atwell", 2015), marker="x", ms=3.5,
              mfc=None)
        ax.axvline(d.time_hph.max(), color="0.55", lw=style.LW_REF, ls=":", zorder=0)
        ax.set(xlabel="Time (hph)", ylabel=lab, ylim=(0, None), xlim=(15, 90))
        if i == 0:
            ax.text(d.time_hph.max() + 1.5, 0.62, "Run stopped\n(1 h limit)", transform=ax.get_xaxis_transform(),
                    va="top", fontsize=style.FS)
            legend(ax, loc="lower right")
