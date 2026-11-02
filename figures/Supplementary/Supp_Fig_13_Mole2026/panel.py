"""Mole et al. (2026): agent-only quantification of the CREST implantation model: depth of the deepest
trophoblast cell below the uterine surface and embryo cell numbers per cell type. Panel b gets the cell-type key
in the run's frame palette."""
import numpy as np

import style
from figure import key_rows
from panels.common import axes, legend, split

UM_PER_NODE = 3.0  # dx_um in the agent's model.xml
SURFACE_Y = 60  # surface_y in the agent's model.xml: top node row of the luminal epithelium (rows 56-60)
# cell.type values of the run (order of the CellTypes in model.xml, medium = 0) with the run's Gnuplotter ColorMap
# colours, which are also the Molè cell colours of the main Fig. 2 (Fig2_v17_source/build_fig2_v17.py CELLS_E)
TYPES = {1: ("Trophectoderm", "#c59d59"), 2: ("Invasive trophoblast", "#bd6d35"), 3: ("Epiblast", "#68558d"),
         4: ("Hypoblast", "#51ada9"), 8: ("Blastocoel", "#f5e4c9"), 5: ("Epithelium", "#edb5b8"),
         6: ("Gland", "#cf7e96"), 7: ("Stroma", "#cb727a")}
KEY_ROWS = [[1, 2, 3, 4, 8], [5, 6, 7]]  # embryo, then host tissue
C_DEPTH = TYPES[2][1]
STAGES = [(6, "Apposition"), (7, "Adhesion"), (8, "Implantation")]
AB_LAYOUT = "side"  # a beside b: stacked, the four frames would leave panel c a single row of 1 pt text
D_HEIGHT = 46.0
B_KEY_H = 7.4  # mm below the frames: two rows of cell-type patches
B_CAPTION = ("frames cropped inside the Gnuplotter frame lines (pixels 2–872 of 875 in x, 2–697 of 700 in y; the "
             "full 200 × 160-node domain, 600 × 480 µm), in the colours of the run's cell.type ColorMap, which are "
             "also the cell colours of main Fig. 2 (key below the frames): trophectoderm #c59d59, invasive "
             "trophoblast (EVT in Fig. 2) #bd6d35, epiblast #68558d, hypoblast #51ada9, luminal epithelium "
             "#edb5b8, gland #cf7e96, stroma #cb727a, blastocoel #f5e4c9; black cell outlines, white medium; "
             "frames at 0, 24, 48 and 72 h (dpf = 6 + elapsed_hours/24 in model.xml; 6, 7 and 8 d.p.f. are the "
             "apposition, adhesion and implantation stages of Fig. 3A)")
CAPTION = ("Agent-only quantification from the run's per-cell log (cells.csv, every 1 h; 1 node = 3 µm, dx_um in "
           "the agent's model.xml), vs embryo age dpf = 6 + elapsed_hours/24 (d.p.f.). (i) Invasion depth: depth "
           "of the deepest trophoblast cell centre (trophectoderm and invasive trophoblast, is_trophoblast = 1) "
           "below the uterine surface, (surface_y − min cell.center.y) × 3 µm with surface_y = 60 nodes, the top "
           "node row of the luminal epithelium (grey line); negative values: above the surface. It is {d0} µm at "
           "6 d.p.f., crosses the surface at {tcross} d.p.f. and reaches {dend} µm at 9 d.p.f. Dotted lines: the "
           "stages of Fig. 3A (apposition 6, adhesion 7, implantation 8 d.p.f.). (ii) Number of embryo cells per "
           "cell type (cell.type), colours as in b; the first invasive trophoblast cells (contact-induced change of "
           "type from trophectoderm) appear at {tinv} d.p.f., and trophectoderm cells number {nte0} at 6 and "
           "{nte1} at 9 d.p.f.")


# Publication legend (legend.py): keys are the panel letters as printed; legend.py prepends the run sentence to the
# frames panel and fills {graph} and the {name} fields of ctx.fmt.
LEGEND = {
    "cite": "molè2026",  # bib key (morpheusai_supp.bib) cited after every mention of the authors
    "title": "Human embryo implantation (Molè *et al.*, 2026).",
    "a": "Stages of human embryo implantation in vitro (adapted from Fig. 3A of Molè *et al.*).",
    "b": "Embryo and endometrium colored by cell type (key below).",
    "c": "{graph}",
    "d": "**i**, Depth of "
         "the deepest trophoblast cell below the uterine surface (gray line); negative values lie above it. Dotted "
         "lines mark the apposition, adhesion and implantation stages of Fig. 3A of Molè *et al.* The trophoblast "
         "crosses the surface at {tcross} d.p.f. **ii**, Number of embryo cells of each type, colored as in **b**. "
         "The first invasive trophoblast cells, which arise from trophectoderm cells by a contact-induced change of "
         "type, appear at {tinv} d.p.f.",
    "abbrev": "d.p.f., days post-fertilization.",
    "license": "Material from Molè *et al.* is adapted under a CC BY 4.0 license.",
}


def draw_b_key(fig, pos, y):
    """Below panel b's frames, centred: the cell types in the run's frame palette, embryo then host."""
    key_rows(fig, pos[0][0], pos[-1][0] + pos[-1][2], y, [[TYPES[k][::-1] for k in row] for row in KEY_ROWS],
             row_h=3.4)


def stages(ax, labels=False):
    for x, lab in STAGES:
        ax.axvline(x, color="0.7", lw=style.LW_REF, ls=":", zorder=0)
        if labels:
            ax.text(x + 0.04, 0.99, lab, transform=ax.get_xaxis_transform(), fontsize=style.FS, va="top")


def draw(ctx, fig, box):
    d = ctx.csv("cells.csv", sep="\t")
    d = d.loc[:, ~d.columns.duplicated()]
    t_end = d.dpf.max()
    tro = d[d.is_trophoblast == 1]
    t0 = tro.dpf.min()
    b1, b2 = split(box, [1, 1], gap=14)

    # (i) depth of the deepest trophoblast cell centre below the uterine surface
    depth = (SURFACE_Y - tro.groupby("dpf")["cell.center.y"].min()) * UM_PER_NODE
    ax = axes(fig, b1, label="i")
    stages(ax, labels=True)
    ax.axhline(0, color="0.5", lw=0.5, zorder=1)
    ax.plot(depth.index, depth.values, color=C_DEPTH)
    ax.set(xlabel="Embryo age (d.p.f.)", ylabel="Invasion depth (µm)", xlim=(t0, t_end), ylim=(-25, 55),
           xticks=[6, 7, 8, 9])
    ax.text(t0 + 0.04, 1.5, "Surface", fontsize=style.FS, va="bottom")
    below = depth[depth > 0]

    # (ii) embryo cell numbers per type
    n = d.groupby(["dpf", "cell.type"]).size().unstack(fill_value=0)
    ax = axes(fig, b2, label="ii")  # no stage lines: the legend needs the space (the lines would count as data)
    for k in (1, 2, 3, 4):
        lab, c = TYPES[k]
        ax.plot(n.index, n[k] if k in n else np.zeros(len(n)), color=c, label=lab, drawstyle="steps-post")
    ax.set(xlabel="Embryo age (d.p.f.)", ylabel="Cell number", xlim=(t0, t_end), ylim=(0, 72), xticks=[6, 7, 8, 9])
    legend(ax, loc="upper left")

    inv = n[2] if 2 in n else None
    ctx.fmt.update(d0=f"{depth.iloc[0]:.0f}".replace("-", "−"), tcross=f"{below.index[0]:.2f}", dend=f"{depth.iloc[-1]:.0f}",
                   tinv=f"{inv[inv > 0].index[0]:.2f}", nte0=int(n[1].iloc[0]), nte1=int(n[1].iloc[-1]))
