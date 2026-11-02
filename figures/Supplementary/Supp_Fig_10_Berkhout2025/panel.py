"""Berkhout et al. (2025): cell numbers of the four tissues that have a reference curve (surface ectoderm, neural
crest, paraxial mesoderm, somites) vs one run of the paper's own CompuCell3D model, rerun by co-author L.B.
(paper_data/compucell3d_rerun_timecourse.csv). Panel b gets the tissue colour key; with config.BERKHOUT_RERUN set, it shows six frames every
10 h from a checked Morpheus re-run (b_frames)."""
import os
import xml.etree.ElementTree as ET

import numpy as np
from matplotlib.lines import Line2D
from PIL import Image

import config
import figure
import style
from figure import key_rows
from panels.common import AGENT_LABEL, axes, paper_label, split

D_HEIGHT = 46.0
# Tissue colours: the run's Gnuplotter ColorMap (Cells value="stain", stain = tissue with somite 3 drawn as
# mesoderm 4), which follows the paper's Fig. 1 legend. Panel d uses the same colours.
COL = {"surface_ectoderm": "#7890fa", "neural_crest": "#f09ee4", "neuroectoderm": "#c79ce4",
       "floor_plate": "#9575ac", "notochord": "#a7d78f", "mesoderm": "#ff9daf", "somite": "#ff9daf",
       "endoderm": "#b96d7b", "ECM": "#fff59a"}
KEY = [[("surface_ectoderm", "Surface ectoderm"), ("neural_crest", "Neural crest (incl. delaminated)"),
        ("neuroectoderm", "Neuroectoderm"), ("floor_plate", "Floor plate")],
       [("notochord", "Notochord"), ("mesoderm", "Paraxial mesoderm and somites"), ("endoderm", "Endoderm"),
        ("ECM", "Extracellular matrix")]]
B_KEY_H = 7.0  # mm below the frames: two rows of tissue colour patches
# (agent column of native_cell_counts_by_half.csv without _left/_right, CompuCell3D column, y label)
PAIRS = [("surface_ectoderm", "N_Surface_Ectoderm_y", "Surface ectoderm\ncell number"),
         ("neural_crest", "N_Neural_Crest_y", "Neural crest\ncell number"),
         ("mesoderm", "N_Mesoderm_y", "Paraxial mesoderm\ncell number"),
         ("somite", "N_Somite_y", "Somite cell number")]
PAPER_MODEL_LABEL = "CompuCell3D model of " + paper_label("Berkhout", 2025)
REF_KW = dict(color="0.45", lw=style.LW_REF, ls=(0, (2.5, 1.5)))

# Panel b from a Morpheus re-run (config.BERKHOUT_RERUN): the scored model.xml with only the Gnuplotter time-step
# changed from 3000 to RERUN_STEP MCS. The build stops unless the re-run's model.xml equals the scored one apart from
# that time-step and its frames at the run's own frame times (config.FRAMES: 0, 12.5, 25, 37.5, 50 h) are byte-identical
# (SHA-256) to the run's.
RERUN_STEP = 600.0  # MCS = 2.5 h; the shown frames are every 2400 MCS = 10 h
RERUN = config.BERKHOUT_RERUN
B_SOURCE = None if RERUN is None else (
    f"frames of a re-run of the identical scored model.xml with a denser Gnuplotter interval ({RERUN_STEP:.0f} "
    "instead of 3000 MCS; RandomSeed 42), verified at build time to be bit-identical to the run's own frames at the "
    "shared times (0, 12.5, 25, 37.5 and 50 h; SHA-256) (" + "; ".join(f"{f}: {lab}" for f, lab in
                                                                       config.BERKHOUT_RERUN_FRAMES) + ")")
B_EXEMPT = None if RERUN is None else [
    f"panel b: {len(config.BERKHOUT_RERUN_FRAMES)} raster Gnuplotter frames of the re-run of the scored model, cropped "
    "(any text left in them is the run's own)"]
B_CAPTION = ("each frame is the cell-fate sub-plot (left quarter) of the Gnuplotter output, cropped inside its "
             "frame lines (pixels 1–299 of 300 in x) and below the medium that is empty in every frame shown (rows "
             "66–236 of 238 kept; the frame spans the 252 µm width of the domain, 1 lattice site = 1 µm); 240 MCS = "
             "1 h. Cells are coloured by tissue in the run's ColorMap of stain, which uses the tissue colours of the "
             "paper's Fig. 1 (key below the frames; black lines are cell outlines, white is medium). Neural cells "
             "are drawn as their three CPM compartments, attached and delaminated neural crest cells share one "
             "colour, and so do paraxial mesoderm and somite cells (stain maps somite to the mesoderm colour)")
CAPTION = ("Number of cells of (i) surface ectoderm, (ii) neural crest (agent: attached cells only), (iii) paraxial "
           "mesoderm and (iv) somites vs time. Solid: agent-generated model, in the tissue colours of b "
           "(native_cell_counts_by_half.csv, left + right half, logged every 121.2 MCS = 0.505 h; one Mapper per "
           "cell type sums one per cell). Grey dashed: one run of the authors' CompuCell3D model (Invitro_NTC_2D, "
           "CompuCell3D 4.3.0, 2D, 12,000 MCS = 50 h), rerun by co-author L.B., not published data; the time course "
           "(10_Berkhout2025/compucell3d_rerun_timecourse.csv, every MCS; N_* columns) is the rerun's output. The "
           "authors' model divides cells (its parameters.py: cell_cycle_time = 4000 MCS; Table 1, p. 5, lists "
           "mesoderm proliferation), although the paper's Methods say that cell volume grows \"without "
           "inducing cell proliferation\" (p. 11). The agent followed the Methods, so its cells never divide: its "
           "{meso0_a} paraxial mesoderm cells (CompuCell3D run: {meso0_p}, rising to {mesomax_p} by about 17 h) "
           "become {som1_a} somite cells, against {som1_p} in the CompuCell3D run at 50 h.")


# Publication legend (legend.py): keys are the panel letters as printed; legend.py prepends the run sentence to the
# frames panel and fills {graph} and the {name} fields of ctx.fmt.
LEGEND = {
    "cite": "berkhout2025",  # bib key (morpheusai_supp.bib) cited after every mention of the authors
    "title": "Neural tube closure (Berkhout *et al.*, 2025).",
    "a": "Cell field of the model of Berkhout *et al.* from 0 to 50 h (adapted from their Fig. 1).",
    "b": "The model at the same times, with cells colored by tissue as in Fig. 1 of Berkhout *et al.* (key below).",
    "c": "{graph}",
    "d": "Number of surface ectoderm (**i**), neural crest (**ii**; agent's model, attached cells only), paraxial "
         "mesoderm (**iii**) and somite cells (**iv**) in the agent's model (solid lines, colored as in **b**) and "
         "in a rerun of the authors' CompuCell3D model (dashed; one run, CompuCell3D 4.3.0).",
    "license": "Material from Berkhout *et al.* is adapted under a CC BY 4.0 license.",
}


def draw_b_key(fig, pos, y):
    """Tissue colour key below the frames, two rows, columns aligned and the block centred under the frames."""
    key_rows(fig, pos[0][0], pos[-1][0] + pos[-1][2], y + 0.3, [[(COL[t], lab) for t, lab in row] for row in KEY],
             align=True, gap=3.0)


class _Rerun:
    """ctx for figure.load_frame that reads the frames from the re-run folder (recorded under their own role)."""

    def __init__(self, ctx, folder):
        self.ctx, self.folder = ctx, folder

    def __getattr__(self, name):
        return getattr(self.ctx, name)

    def attempt(self, name, role=None):
        return self.ctx.add(f"panel b frame (re-run of the scored model, Gnuplotter every {RERUN_STEP:.0f} MCS)",
                            os.path.join(self.folder, name))


def _canonical(path):
    """(model.xml as canonical XML with the Gnuplotter time-step blanked, that time-step)."""
    root = ET.parse(path).getroot()
    gp = root.find("./Analysis/Gnuplotter")
    t = float(gp.get("time-step"))
    gp.set("time-step", "")
    return ET.canonicalize(ET.tostring(root, encoding="unicode"), with_comments=True, strip_text=True), t


def b_frames(ctx):
    """Panel b: the run's own frames (config.FRAMES), or with config.BERKHOUT_RERUN the re-run's frames every 10 h,
    after checking that the re-run reproduces the scored run."""
    if RERUN is None:
        return figure.panel_b_images(ctx)
    # data/rerun_gnuplot_10h of this figure folder; with --runs, relative to the folder that holds the benchmark
    # directory, or absolute
    folder = os.path.join(os.path.dirname(os.path.abspath(ctx.run_dir)), config.BERKHOUT_RERUN_LOCAL)
    if not os.path.isdir(folder):
        folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(ctx.run_dir))), RERUN)
    stop = f"Berkhout re-run {folder}: {{}}; set config.BERKHOUT_RERUN = None to show the run's own frames."
    if not os.path.isdir(folder):
        raise SystemExit(stop.format("folder not found"))
    rerun, step = _canonical(ctx.add("panel b check (model.xml of the re-run)", os.path.join(folder, "model.xml")))
    scored, _ = _canonical(os.path.join(ctx.att, "model.xml"))
    if rerun != scored or step != RERUN_STEP:
        raise SystemExit(stop.format(f"model.xml is not the scored one with only the Gnuplotter time-step set to "
                                     f"{RERUN_STEP:g} MCS (its time-step: {step:g})"))
    for f, _ in config.FRAMES[ctx.key]:
        own = ctx.attempt(f, role="panel b check (run's own frame, compared with the re-run's)")
        new = ctx.add("panel b check (re-run frame, compared with the run's own)", os.path.join(folder, f))
        if figure.sha256(own) != figure.sha256(new):
            raise SystemExit(stop.format(f"{f} is not byte-identical to the scored run's frame"))
    # the rows above the tissue that FRAME_CROP_PX leaves out (below the frame line, row 0) must be white medium
    w0, w1 = config.FRAME_CROP[ctx.key][:2]
    x0, x1, y0, _ = config.FRAME_CROP_PX[ctx.key]
    for f, _ in config.BERKHOUT_RERUN_FRAMES:
        im = np.asarray(Image.open(os.path.join(folder, f)).convert("RGB"))
        if (im[1:y0, int(w0 * im.shape[1]):int(w1 * im.shape[1])][:, x0:x1] != 255).any():
            raise SystemExit(f"Berkhout re-run {folder}: {f} has tissue in rows 1-{y0 - 1}, which "
                             "config.FRAME_CROP_PX leaves out; lower its y0.")
    rerun_ctx = _Rerun(ctx, folder)
    return [[(figure.load_frame(rerun_ctx, f), lab) for f, lab in config.BERKHOUT_RERUN_FRAMES]]


CC3D_CSV = "10_Berkhout2025/compucell3d_rerun_timecourse.csv"


def draw(ctx, fig, box):
    d = ctx.csv("native_cell_counts_by_half.csv")
    p = ctx.paper(CC3D_CSV)
    tot = {c: d[c + "_left"] + d[c + "_right"] for c, _, _ in PAIRS}
    # 2 x 2 plots; the top row's top margin leaves room for the common legend in one row above the plots, below
    # the numerals, and its box is taller by as much, so all four axes have the same size
    x, y, w, h = box
    gap, top, extra = 3.0, 4.2, 3.4
    h2 = (h - gap - extra) / 2
    rows = [(x, y, w, h2 + extra), (x, y + h2 + extra + gap, w, h2)]
    boxes = [b for r in rows for b in split(r, [1, 1], gap=12)]
    for i, (b, (col, pcol, lab)) in enumerate(zip(boxes, PAIRS)):
        ax = axes(fig, b, label=["i", "ii", "iii", "iv"][i], left=12.0, top=top + (extra if i < 2 else 0.0))
        ax.plot(p["Time (hours)"], p[pcol], **REF_KW)
        ax.plot(d.time_hours, tot[col], color=COL[col], lw=1.0)
        ax.set(xlabel="Time (h)", ylabel=lab, ylim=(0, None), xlim=(0, 50), xticks=[0, 10, 20, 30, 40, 50])
        if i == 0:
            ax.legend(handles=[Line2D([], [], color="0.2", lw=1.0, label=AGENT_LABEL + " (colors as in b)"),
                               Line2D([], [], **REF_KW, label=PAPER_MODEL_LABEL)],
                      loc="lower left", bbox_to_anchor=(0.0, 1.0), borderaxespad=0.4, ncol=2)
    i17 = p["Time (hours)"] <= 17.5
    ctx.fmt.update(meso0_a=f"{tot['mesoderm'].iloc[0]:.0f}", meso0_p=f"{p.N_Mesoderm_y.iloc[0]:.0f}",
                   mesomax_p=f"{p.N_Mesoderm_y[i17].max():.0f}", som1_p=f"{p.N_Somite_y.iloc[-1]:.0f}",
                   som1_a=f"{tot['somite'].iloc[-1]:.0f}")
