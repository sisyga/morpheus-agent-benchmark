"""Mu et al. (2024): B-cell numbers (total, dark zone, light zone) vs Fig. 3A; mean affinity vs Fig. 4A.
Panel b gets the colour key of the run's affinity palette."""
import glob
import json
import os
import re
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
from PIL import Image
from matplotlib.colors import LinearSegmentedColormap, to_rgb
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

import config
import style
from figure import FIG_H, FIG_W, mm_axes, text, text_width_mm
from panels.common import AGENT_LABEL, axes, legend, paper_label, split

AB_LAYOUT = "side"
# zones in colour-blind-safe Okabe-Ito colours (the paper's Fig. 3A draws DZ red, LZ green, total blue)
C_TOT, C_DZ, C_LZ, C_AFF = "0.15", "#D55E00", "#0072B2", "#7d3c98"
# the agent's own last test of the submitted model (its attempt folder in the run's agent_workspace)
A21 = os.path.join("agent_workspace", "attempts", "attempt_021")
SERIES = [("Total", "08_Mu2024/total.csv", C_TOT, "o"), ("Dark zone", "08_Mu2024/DZ.csv", C_DZ, "s"),
          ("Light zone", "08_Mu2024/LZ.csv", C_LZ, "^")]
# affinity palette of the run's Gnuplotter (model.xml ColorMap and gnuplot_commands_1_*.gp: set palette defined
# (0 'black', 4 '#304990', 5 '#31c9d0', 7 '#43b946', 8 'yellow', 9 'red', 11 '#9c0000'), cbrange [0:11])
AFF_NODES = [(0, "#000000"), (4, "#304990"), (5, "#31c9d0"), (7, "#43b946"), (8, "#ffff00"), (9, "#ff0000"),
             (11, "#9c0000")]
AFF_CMAP = LinearSegmentedColormap.from_list("mu_affinity", [(v / 11, to_rgb(c)) for v, c in AFF_NODES])
C_RESIDENT = "#304990"  # CRC, FDC and Tfh cells: constant affinity 4 in model.xml
B_KEY_H = 9.0  # mm below the frames: affinity colour bar and the resident-cell patch
B_CAPTION = ("each frame is the right sub-plot (B-cell affinity in the z = 5 µm slice of the "
             "250 × 200 × 11 µm lattice; the CXCL12 and CXCL13 sub-plots are not shown), cropped inside its frame lines (pixels 810–1115 of 1200 in x, 26–269 "
             "of 292 in y), which removes the raster title, x label and colour bar; cells coloured by affinity in "
             "the run's palette (black 0, #304990 dark blue 4, #31C9D0 cyan 5, #43B946 green 7, yellow 8, red 9, "
             "#9C0000 dark red 11; colour bar below the frames; affinity is dimensionless as in the paper); "
             "B cells carrying a lethal mutation have affinity −1 in the model and are drawn black (below the "
             "colour range); CRC, FDC and Tfh cells have a fixed affinity of 4 in the model and appear as the "
             "dark blue squares (CRC on the left, dark-zone side; FDC and Tfh on the right, light-zone side). "
             "1 MCS = 0.01 h in the agent's model (MCSDuration 0.01, time in hours), i.e. 100 MCS = 1 h as "
             "stated in the paper, so the frames at 0, 100, 300 and 400 h correspond to the 0, 10,000, 30,000 "
             "and 40,000 mcs snapshots of Fig. 2D")
CAPTION = ("(i) Number of B cells present at each time, in total and per zone (aggregate_raw.csv, logged every "
           "0.01 h: dark zone = B_left, the B cells with centre x < 125 µm, the CXCL12/CRC half; light zone = "
           "B_right, centre x ≥ 125 µm, the CXCL13/FDC half; total = B_left + B_right; agent-generated model) "
           "with Mu et al. (2024): the total, DZ and LZ curves of Fig. 3A, digitised (08_Mu2024/total.csv, DZ.csv, "
           "LZ.csv; the paper's y axis is in units of 10³ cells, converted to cells). "
           "(ii) Mean affinity of all B cells (aggregate_raw.csv: affinity_mean, the mean of the B-cell property "
           "affinity) with the mean-affinity curve of Fig. 4A of Mu et al. (2024), digitised "
           "(08_Mu2024/mean_affinity.csv). The model's mean includes the few B cells that carry a lethal mutation, "
           "whose affinity is set to −1 until they die (at most {lethal_max} of the B cells at the hourly "
           "samples of cells_raw.csv; excluding them raises the mean by at most {lethal_shift}). "
           "Time: the paper's axes are in units of 100 mcs and are plotted as hours (paper: 100 mcs ≈ 1 h; "
           "72,000 mcs = 30 days); the agent's model runs in hours with 1 MCS = 0.01 h, the same conversion. "
           "At 400 h the agent's model has {n_end} B cells, about {pct} % of the paper's (Fig. 3A). Its set-up "
           "follows the paper's (200 initial B cells of affinity 5, 45 CRC, 45 FDC and 36 Tfh cells, the 250 × 200 "
           "× 11 µm domain, no cap on the cell number), and the run was not limited by the benchmark's 1 h "
           "per-run limit (scored run: {wall} min of Morpheus wall time, morpheus_command.json), so the shortfall "
           "does not come from a reduced set-up (set-up values from the scored model.xml). It most likely lies in "
           "the agent's approximation of the paper's stochastic AP4/MYC/BLIMP1 network (a Tellurium/Gillespie "
           "model, p. 4, whose code the agent could not download), which the agent replaced by rate equations "
           "(with added noise for AP4) and event rules (model_notes.md); this network sets how long B cells keep "
           "dividing. The final number also varies strongly between runs of the same model: the agent's own last "
           "test of the identical model.xml (agent_workspace attempt_021) ended with {n_a21} B cells at {t_a21} h. "
           "The agent's run ends at 400 h because the benchmark task asked for 0–40,000 mcs, the final time of "
           "Fig. 2D (benchmark_focus/08_Mu2024.txt); the paper's curves continue to 720 h. Colours: dark zone vermilion, light zone blue (red and green in "
           "the paper).")


# Publication legend (legend.py): keys are the panel letters as printed; legend.py prepends the run sentence to the
# frames panel and fills {graph} and the {name} fields of ctx.fmt.
LEGEND = {
    "cite": "mu2024",  # bib key (morpheusai_supp.bib) cited after every mention of the authors
    "title": "B-cell dynamics in the germinal center (Mu *et al.*, 2024).",
    "a": "Positions of the resident cells, chemokine fields and simulation snapshots colored by B-cell affinity, "
         "from Mu *et al.* (adapted from their Fig. 2A–D).",
    "b": "B cells in a single layer (*z* = {z_slice} µm) of the {z_depth} µm thick 3D domain, colored by affinity; "
         "the dark blue squares are the resident CRC, FDC and Tfh cells, which have a fixed affinity (key below). "
         "Because the layer holds only the B cells that cross it ({n_slice} of {n_b} at {t_slice} h), the frames "
         "look less densely packed than a projection of the whole domain. The agent's model uses the paper's time "
         "scale (100 MCS = 1 h), so the frames correspond to snapshots in **a** and the curves in **d** compare "
         "directly.",
    "c": "{graph}",
    "d": "**i**, Number of B cells in total and in the dark and light zones in the agent's model (lines) and in Mu "
         "*et al.* (markers; digitized from their Fig. 3A). The run ended at {t_end} h because the benchmark asked for 40,000 MCS, the final time of their Fig. 2D. "
         "**ii**, Mean B-cell affinity in the agent's model (line) and in Mu *et al.* (circles; digitized from their "
         "Fig. 4A).",
    "abbrev": "CRC, CXCL12-expressing reticular cell; FDC, follicular dendritic cell; MCS, Monte Carlo steps; Tfh, T "
              "follicular helper cell.",
    "license": "Material from Mu *et al.* is adapted under a CC BY 4.0 license.",
}


# the resident cells in the paper's wording (p. 3, "CXCL12-expressing reticular cells (CRCs) ... FDCs and Tfh
# cells"; p. 2, "follicular dendritic cells (FDCs)", "T follicular helper (Tfh) cells"), one line each
RESIDENT_KEY = ["CXCL12-expressing reticular cells (CRC)", "Follicular dendritic cells (FDC)",
                "T follicular helper (Tfh) cells"]


def draw_b_key(fig, pos, y):
    """Below panel b's frames, centred: the run's affinity colour bar (0-11) and a patch for the CRC, FDC and
    Tfh cells (written out, one per line), which carry the fixed affinity 4."""
    x0 = min(p[0] for p in pos)
    x1 = max(p[0] + p[2] for p in pos)
    title = "B-cell affinity (dimensionless)"
    bw, bh, gap, pw, tg = 26.0, 1.6, 3.0, 2.6, 0.9
    over = max(0.0, (text_width_mm(title) - bw) / 2)  # the bar's title is wider than the bar
    w = over + bw + gap + pw + tg + max(text_width_mm(s) for s in RESIDENT_KEY)
    xb = (x0 + x1) / 2 - w / 2 + over
    text(fig, xb + bw / 2, y + 0.1, title, ha="center", fontsize=style.FS)
    ax = mm_axes(fig, xb, y + 3.0, bw, bh)
    ax.imshow(np.linspace(0, 11, 551)[None, :], cmap=AFF_CMAP, vmin=0, vmax=11, extent=(0, 11, 0, 1),
              aspect="auto", interpolation="bilinear")
    ax.set(xlim=(0, 11), ylim=(0, 1), yticks=[])
    ax.set_xticks([0, 2, 4, 6, 8, 10])
    for s in ("left", "right", "top"):
        ax.spines[s].set_visible(True)
    xp = xb + bw + gap
    fig.patches.append(Rectangle((xp / FIG_W, 1 - (y + 3.0 + bh) / FIG_H), pw / FIG_W, bh / FIG_H,
                                 transform=fig.transFigure, fc=C_RESIDENT, ec="0.3", lw=0.3))
    for i, s in enumerate(RESIDENT_KEY):
        text(fig, xp + pw + tg, y + 0.1 + 2.5 * i, s, fontsize=style.FS)


def lethal_stats(ctx):
    """Largest fraction of B cells with affinity −1 (lethal mutation) and largest shift of the mean affinity
    when they are excluded, over the hourly samples of cells_raw.csv."""
    def compute():
        c = ctx.csv("cells_raw.csv", usecols=["time_hours", "affinity"])
        g = c.groupby("time_hours").affinity
        return pd.DataFrame({"lethal_fraction": g.apply(lambda a: (a < 0).mean()),
                             "mean_shift_without_lethal": g.apply(lambda a: a[a >= 0].mean() - a.mean())}
                            ).reset_index()
    s = ctx.summary("mu_lethal_affinity", compute)  # 22 MB per-cell log -> one row per hour
    return s.lethal_fraction.max(), s.mean_shift_without_lethal.max()


def tiff_pages(path, channels, slices):
    """{(t, z, c): 2D array} of a Morpheus TiffPlotter stack, pages ordered channel fastest, then z, then time.
    The stack's ImageJ description gives channels, slices and frames; without one (OME-header="false", as in the
    Mu run), channels and slices come from model.xml and the frames from the page count."""
    im = Image.open(path)
    meta = dict(ln.split("=", 1) for ln in str(im.tag_v2.get(270) or "").splitlines() if "=" in ln)
    nc, nz = int(meta.get("channels", channels)), int(meta.get("slices", slices))
    nt = int(meta.get("frames", im.n_frames // (nc * nz)))
    if im.n_frames != nc * nz * nt:
        raise RuntimeError(f"{path}: {im.n_frames} pages, expected {nc} channels x {nz} slices x {nt} frames")
    pages = {}
    for i in range(im.n_frames):
        im.seek(i)
        pages[(i // (nc * nz), i // nc % nz, i % nc)] = np.array(im)
    return pages, (nc, nz, nt)


def slice_counts(ctx, agg):
    """Panel b's frames are the Gnuplotter's z slice of the 3D lattice. B cells that reach that layer and all B
    cells at the last frame, from the run's TiffPlotter stack (cell.id of every voxel; resident CRC, FDC and Tfh
    cells are the frozen cells of model.xml's populations); the total must equal aggregate_raw.csv."""
    root = ET.parse(os.path.join(ctx.att, "model.xml")).getroot()
    nz = int(root.find("Space/Lattice/Size").get("value").split(",")[2])
    h = float(root.find("Space/Lattice/NodeLength").get("value"))  # µm (the paper's 1 pixel = 1 µm)
    plot = next(p for p in root.iter("Plot") if p.find("Cells") is not None)
    z = int(plot.get("slice"))
    tp = root.find("Analysis/TiffPlotter")
    dt = float(tp.get("time-step"))
    t0 = float(root.find("Time/StartTime").get("value"))
    ch = [c.get("symbol-ref") for c in tp.findall("Channel")].index("cell.id")
    resident = {int(c.get("id")) for pop in root.iter("Population") if pop.get("type") != "BCell"
                for c in pop.iter("Cell")}
    t = float(re.search(r"plot_([\d.]+)\.png$", config.FRAMES[ctx.key][-1][0]).group(1))
    def compute():  # the 40 MB stack -> the B-cell ids in each z layer of the shown frame
        tifs = sorted(glob.glob(os.path.join(ctx.att, "*.tif*")))
        if len(tifs) != 1:
            raise RuntimeError(f"expected one TiffPlotter stack in {ctx.att}, found {tifs}")
        pages, (_, nz_tif, nt) = tiff_pages(
            ctx.add("TiffPlotter stack (panel b: B cells in the plotted layer)", tifs[0]), len(tp.findall("Channel")),
            nz)
        k = round((t - t0) / dt)
        if nz_tif != nz or not 0 <= k < nt:
            raise RuntimeError(f"{tifs[0]}: {nz_tif} slices, {nt} frames; lattice depth {nz}, frame {k} for {t} h")
        rows = [(zz, i) for zz in range(nz)
                for i in sorted(set(np.unique(pages[(k, zz, ch)]).astype(int)) - resident - {0})]
        return pd.DataFrame(rows, columns=["z", "cell_id"]).assign(time_hours=t)
    layers = ctx.summary("mu_bcells_by_layer", compute)
    ids = lambda zz: set(layers.cell_id[layers.z == zz])  # noqa: E731
    every = set(layers.cell_id)
    total = agg.B_left + agg.B_right
    n_log = int(total.iloc[(agg.time_hours - t).abs().idxmin()])
    if len(every) != n_log:
        raise RuntimeError(f"{len(every)} B cells in the TIFF at {t} h, {n_log} in aggregate_raw.csv")
    ctx.fmt.update(z_slice=f"{z * h:g}", z_depth=f"{nz * h:g}", n_slice=len(ids(z)), n_b=len(every), t_slice=f"{t:g}")


def draw(ctx, fig, box):
    d = ctx.csv("aggregate_raw.csv")
    slice_counts(ctx, d)
    b1, b2 = split(box, [1.25, 1], gap=12)
    ax = axes(fig, b1, label="i")
    agent = {"Total": d.B_left + d.B_right, "Dark zone": d.B_left, "Light zone": d.B_right}
    pk = {k: v for k, v in style.PAPER_KW.items() if k not in ("color", "marker")}
    zone_h, pdat = [], {}  # paper data per series, each loaded once (its correction notes once)
    for name, rel, c, m in SERIES:
        p = pdat[name] = ctx.paper(rel)
        ax.plot(d.time_hours, agent[name], color=c)
        ax.plot(p.x, p.y * 1000, marker=m, mec=c, **pk)
        zone_h.append((Line2D([], [], color=c), Line2D([], [], marker=m, mec=c, **pk)))
    src_h = [Line2D([], [], color="0.45"), Line2D([], [], marker="o", mec="0.45", **pk)]
    ax.set(xlabel="Time (h)", ylabel="Number of B cells", xlim=(0, 730), ylim=(0, None))
    legend(ax, handles=zone_h + src_h, labels=[n for n, *_ in SERIES] + [AGENT_LABEL, paper_label("Mu", 2024)],
           loc="upper left", ncol=2)

    p = ctx.paper("08_Mu2024/mean_affinity.csv")
    ax = axes(fig, b2, label="ii")
    ax.plot(d.time_hours, d.affinity_mean, color=C_AFF, label=AGENT_LABEL)
    ax.plot(p.x, p.y, label=paper_label("Mu", 2024), **style.PAPER_KW)
    ax.set(xlabel="Time (h)", ylabel="Mean B-cell affinity (dimensionless)", xlim=(0, 730))
    legend(ax, loc="upper left")
    fmax, smax = lethal_stats(ctx)
    ctx.fmt.update(lethal_max=f"{100 * fmax:.1f} %", lethal_shift=f"{smax:.2f}")
    # B cells at the end vs the paper's total at the same time, and the scored run's Morpheus wall time
    t_end = d.time_hours.iloc[-1]
    p_tot = pdat["Total"].sort_values("x")
    n_end = agent["Total"].iloc[-1]
    run = json.load(open(ctx.attempt("morpheus_command.json", role="run record (Morpheus wall time)"),
                         encoding="utf-8"))
    ctx.fmt.update(n_end=f"{n_end:.0f}", pct=f"{100 * n_end / (1000 * np.interp(t_end, p_tot.x, p_tot.y)):.0f}",
                   wall=f"{run['durationMs'] / 60000:.1f}")
    # legend: the paper's total at the end of the agent's run, rounded to 10 cells (digitized curve)
    ctx.fmt.update(t_end=f"{t_end:g}",
                   p_end=f"{round(1000 * np.interp(t_end, p_tot.x, p_tot.y), -1):,.0f}")
    # the agent's last test: the scored model.xml (checked byte for byte) and its own logger output
    xml = ctx.add("agent's last test, model.xml", os.path.join(ctx.run_dir, A21, "model.xml"))
    with open(xml, "rb") as a, open(os.path.join(ctx.att, "model.xml"), "rb") as b:
        assert a.read() == b.read(), "attempt_021/model.xml differs from the scored model.xml"
    a21 = pd.read_csv(ctx.add("agent's last test, B-cell numbers",
                              os.path.join(ctx.run_dir, A21, "aggregate_raw.csv")))
    e = a21.iloc[-1]
    ctx.fmt.update(n_a21=f"{e.B_left + e.B_right:.0f}", t_a21=f"{e.time_hours:g}")
