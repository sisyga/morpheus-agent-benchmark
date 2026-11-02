"""Thapa et al. (2024): panel a arranged here (a_images); senescent area vs the Model 4 points of paper Fig. 4D;
cell numbers vs the cells counted in the Fig. 4B iv snapshots."""
import json
import os

import numpy as np
import pandas as pd
import pymupdf
from matplotlib.legend_handler import HandlerTuple
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

import config
import thapa_fig4d_extract
from panels.common import AGENT_LABEL, axes, fold, legend, paper_label, split

# the run's own cell-type colours (model.xml Gnuplotter ColorMap: SEN 1, NON_SEN 2, CANCER 3), as in panel b
SEN, NON, CAN = "#cf0000", "#ff606b", "#60d400"
M4 = "#F747D3"  # Model 4 of the paper's Fig. 4D (magenta)
B_LEGEND = [(SEN, "Senescent mesothelial"), (NON, "Non-senescent mesothelial"), (CAN, "Cancer")]
B_CAPTION = ("frames cropped to the simulation domain inside the yellow WALL cells (pixels 5–594 of 600 in x and y); "
             "cell colours of the run's ColorMap: senescent mesothelial #cf0000, non-senescent mesothelial #ff606b, "
             "cancer #60d400")
CAPTION = ("(i) Senescent area relative to t = 0 (cell_counts.csv, sen_area_px) and Model 4 of Fig. 4D of Thapa et "
           "al. (2024), mean ± SD of n = 5 runs, read from the PDF's raster image (thapa_fig4d_extract.py; cached "
           "copy 02_Thapa2024/fig4D_model4_points.csv). The paper's 12 h point is hidden behind the other series "
           "and omitted. The 24 h marker is hidden too, so its value is read from the dashed connector; at 36 h the "
           "black experimental marker covers the diamond and part of the upper error bar, so the mean is the "
           "midpoint of the error-bar caps; at 72 h the error bar is shorter than the marker. (ii) Cell numbers "
           "relative to t = 0. Lines: cell_counts.csv. Diamonds: cells counted in the Fig. 4B iv snapshots of one "
           "representative run (24, 72 and 120 h) and in the initial layout of Suppl. Fig. S12 (t = 0) "
           "(02_Thapa2024/fig4Biv_cell_counts.csv). Colours as in b.")

# Publication legend (legend.py): keys are the panel letters as printed; legend.py prepends the run sentence to the
# frames panel and fills {graph} and the {name} fields of ctx.fmt.
LEGEND = {
    "cite": "thapa2023",  # bib key (morpheusai_supp.bib) cited after every mention of the authors
    "title": "Clearance of senescent mesothelial cells by ovarian cancer cells (Thapa *et al.*, 2024).",
    "a": "Model 4 of Thapa *et al.*: the initial layout (their Supplementary Fig. S12), snapshots of one simulation "
         "(Fig. 4B iv), the senescent area in experiments and in the four models (Fig. 4D) and the cell-type key "
         "(Fig. 4A).",
    "b": "Snapshots at the same times, colored by cell type (key below).",
    "c": "{graph}",
    "d": "**i**, Senescent area relative to 0 h in the agent's model (line) and in Model 4 of Thapa *et al.* "
         "(diamonds, mean ± s.d. of five simulations; data from their Fig. 4D). **ii**, Cell numbers relative to 0 h "
         "in the agent's model (lines) and counted in the snapshots of one representative simulation in **a** "
         "(diamonds), colored as in **b**. The two agree closely because the agent downloaded the authors' "
         "CompuCell3D code and translated it into Morpheus, keeping its initial layout of {n0_can} cancer, "
         "{n0_non} non-senescent and {n0_sen} senescent cells; it did not run CompuCell3D. Single runs still vary: "
         "in {rep_n} runs of the agent's model that differed only in the random seed, the final number of cancer "
         "cells ranged from {rep_min} to {rep_max} ({can_end} in the run shown, {p_can_end} in the paper's "
         "snapshot).",
    "license": "Material from Thapa *et al.* is adapted under a CC BY 4.0 license.",
}


# Panel a (figure.build hook a_images): the PANEL_A crops of its row, labelled with the paper's time points (Suppl.
# Fig. S12 is the initial layout), and the crop not in the row (the Fig. 4A colour key) below the row's last crop
A_LABELS = ["0 h", "24 h", "72 h", "120 h", ""]
A_KEY_GAP = 4.0  # pt between Fig. 4D and the Fig. 4A key
A_SHARE = 0.45  # panel a (a row of five images) as wide as the page allows; panel b keeps its four frames large
D_HEIGHT = 43.0


def _crop(doc, page, bb):
    pix = doc[page].get_pixmap(dpi=600, clip=pymupdf.Rect(*bb))
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[..., :3]


def _stack(top, bottom, gap):
    """bottom below top, both centred, white padding (same PDF scale: both from 600-dpi renders)."""
    w = max(top.shape[1], bottom.shape[1])
    pad = lambda im: np.pad(im, ((0, 0), ((w - im.shape[1]) // 2, w - im.shape[1] - (w - im.shape[1]) // 2), (0, 0)),
                            constant_values=255)
    return np.vstack([pad(top), np.full((gap, w, 3), 255, np.uint8), pad(bottom)])


def a_images(ctx):
    spec = config.PANEL_A[ctx.key]
    pdf = ctx.add("paper PDF (panel a)", os.path.join(ctx.repo, f"benchmark_papers/{ctx.key}.pdf"))
    doc = pymupdf.open(pdf)
    ims = [_crop(doc, page, bb) for page, bb, _ in spec["crops"]]
    row = spec["rows"][0]
    key = [i for i in range(len(ims)) if i not in row]
    out = [ims[i] for i in row]
    for i in key:
        out[-1] = _stack(out[-1], ims[i], int(A_KEY_GAP * 600 / 72))
    return [list(zip(out, A_LABELS))]


def repeats(ctx, t_end):
    """Cancer cells at t_end (nearest logged time) in each of the agent's own Model 4 repeats, which differ only in
    the random seed: agent_workspace/ensemble_summary.json lists them with their cell_counts.csv."""
    ws = os.path.join(ctx.run_dir, "agent_workspace")
    with open(ctx.add("agent's Model 4 repeats", os.path.join(ws, "ensemble_summary.json")), encoding="utf-8") as f:
        runs = json.load(f)["model4_attempts"]
    n = []
    for r in runs:
        e = pd.read_csv(ctx.add("agent's Model 4 repeats", os.path.join(ws, r["population_csv"])))
        n.append(int(e.cancer_cells.iloc[(e.time_hours - t_end).abs().idxmin()]))
    return n


def draw(ctx, fig, box):
    d = ctx.csv("cell_counts.csv")
    n = repeats(ctx, d.time_hours.iloc[-1])
    ctx.fmt.update(rep_n=len(n), rep_min=min(n), rep_max=max(n))
    pdf = ctx.add("paper figure (Fig. 4D raster, Model 4 points by thapa_fig4d_extract.py)",
                  os.path.join(ctx.repo, "benchmark_papers", "02_Thapa2024.pdf"))
    p, _ = thapa_fig4d_extract.extract(pdf)
    c = ctx.paper("02_Thapa2024/fig4Biv_cell_counts.csv")
    # legend: the initial layout of the agent's model and the final cancer cells of the run shown and of the
    # paper's 120 h snapshot
    ctx.fmt.update(n0_can=f"{d.cancer_cells.iloc[0]:.0f}", n0_non=f"{d.non_senescent_cells.iloc[0]:.0f}",
                   n0_sen=f"{d.senescent_cells.iloc[0]:.0f}", can_end=f"{d.cancer_cells.iloc[-1]:.0f}",
                   p_can_end=f"{c.cancer_cells[c.t_h.idxmax()]:.0f}")
    b1, b2 = split(box, [1, 1])

    ax = axes(fig, b1, label="i")
    ax.plot(d.time_hours, fold(d.sen_area_px), color=SEN, label=AGENT_LABEL)
    ax.plot(p.t_h, p["mean"], color=M4, lw=0.5, ls=(0, (2.5, 1.5)), zorder=2)
    ax.errorbar(p.t_h, p["mean"], yerr=p.sd, fmt="D", color=M4, ms=2.6, mew=0, elinewidth=0.5, capsize=1.3,
                capthick=0.5, zorder=3, clip_on=False, label=paper_label("Thapa", 2024))
    ax.axhline(1, color="0.7", lw=0.5, zorder=0)
    ax.set(xlabel="Time (h)", ylabel="Relative senescent area", xlim=(0, None), ylim=(0, None))
    legend(ax, loc="lower left")

    ax = axes(fig, b2, label="ii")
    hs = []
    for col, colour, lab in (("cancer_cells", CAN, "Cancer"), ("non_senescent_cells", NON, "Non-senescent"),
                             ("senescent_cells", SEN, "Senescent")):
        ln, = ax.plot(d.time_hours, fold(d[col]), color=colour)
        mk, = ax.plot(c.t_h, c[col] / c[col].iloc[0], "D", ms=2.6, mfc=colour, mec="0.15", mew=0.4, zorder=3,
                       clip_on=False)
        hs.append(((ln, mk), lab))
    hs.append((Line2D([], [], color="0.3"), AGENT_LABEL))
    hs.append((Line2D([], [], ls="", marker="D", ms=2.6, mfc="white", mec="0.15", mew=0.4),
               paper_label("Thapa", 2024)))
    ax.axhline(1, color="0.7", lw=0.5, zorder=0)
    ax.set(xlabel="Time (h)", ylabel="Relative cell number", xlim=(0, None), ylim=(0, None))
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    legend(ax, loc="upper left", handles=[h for h, _ in hs], labels=[lab for _, lab in hs],
           handler_map={tuple: HandlerTuple(ndivide=1)})
