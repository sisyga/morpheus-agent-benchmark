"""Herron et al. (2022): agent-only quantification of the active GTPase u: (i) maximum, mean and minimum over the
domain vs time, with the paper's rosette-formation window; (ii) azimuthally averaged radial profile of u from the
run's float TIFF snapshots. Panel b gets the colour bar of the run's u palette."""
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image

import style
from figure import mm_axes, text
from panels.common import axes, legend, split

DX_UM = 0.03125  # dx_um and NodeLength in the agent's model.xml (µm per node)
DISK_R_UM = 1.75  # disk_radius_um: radius of the IgG disk (logistic rate profiles gamma_r, c_r change here)
TIFF = "u_v_G_g.tif"  # TiffPlotter: channels u, v, G, g (unscaled float), 5 times every 10 s (XYCZT)
TIFF_T = [0, 10, 20, 30, 40]  # s
PROFILE_T = [10, 20, 40]  # s, the frames of panel b after the initial state
C_MAX, C_MEAN, C_MIN = "#D55E00", "#009E73", "#0072B2"  # Okabe-Ito vermilion, bluish green, blue
C_PROF = {10: "0.72", 20: "0.45", 40: "0.0"}
# the run's Gnuplotter ColorMap of u (model.xml: Field symbol-ref="u" min="0" max="200"; Color value 0 #440154,
# 50 #3b528b, 100 #21918c, 150 #5ec962, 200 #fde725, i.e. viridis), linear between the stops
U_STOPS = [(0, "#440154"), (50, "#3b528b"), (100, "#21918c"), (150, "#5ec962"), (200, "#fde725")]
U_CMAP = LinearSegmentedColormap.from_list("u_palette", [(v / 200, c) for v, c in U_STOPS], N=1024)
B_KEY_H = 8.0  # mm below the frames: the u colour bar
B_CAPTION = ("each frame is the plot area of the run's Gnuplotter output, cropped inside its black frame lines "
             "(pixels 20–624 of 791 in x and 52–656 of 700 in y; the Gnuplot title, colour bar and axis tick were "
             "cut off): the active GTPase u on the 256 × 256 lattice (8 × 8 µm, 1 node = 0.03125 µm), coloured with "
             "the run's palette (Gnuplotter ColorMap, viridis stops #440154 at 0, #3b528b at 50, #21918c at 100, "
             "#5ec962 at 150 and #fde725 at 200 molecules µm⁻²; colour bar below the frames); outside the "
             "circular domain (radius 4 µm) u is 0. Frames at 0 s (random initial u), 10, 20 and 40 s")
CAPTION = ("Agent-only quantification (the paper reports no matching time course or profile). (i) Maximum, mean and "
           "minimum of the active membrane-bound GTPase u over the circular domain vs time (u_range.csv, every "
           "0.404 s; Mapper of u with mapping maximum, mean and minimum; the benchmark quantity, the range "
           "max − min, ends at {range_end} molecules µm⁻² at 40 s; the minimum stays near the axis, {u_min_end} "
           "molecules µm⁻² at 40 s). Shaded: 0–20 s, the time in which the "
           "rosette pattern forms in the paper's simulations (S4 Fig). Total GTPase u + v and total GAP G + g, "
           "averaged over the domain (u_range.csv), stay at {T_mean} and {Tg_mean} molecules µm⁻² at all logged "
           "times (mass conservation). (ii) Radial profile of u, ring-averaged: the mean of u over all lattice "
           "nodes at the same distance from the domain centre (rings of 1 node = 0.03125 µm width), at 10, 20 and 40 s, from the run's "
           "unscaled float TIFF snapshots (u_v_G_g.tif, channel u). Dashed line: edge of the IgG disk "
           "(disk_radius_um = 1.75 µm), where the logistic spatial rates γ(r) and c(r) are halfway between "
           "their maxima inside and minima outside the disk. From 20 s on the profile peaks at r = {r_peak} µm, just outside the disk edge, where the spots "
           "of the rosette sit; the ring average is lower than the spot maxima in (i) because it also averages "
           "over the gaps between the spots.")


# Publication legend (legend.py): keys are the panel letters as printed; legend.py prepends the run sentence to the
# frames panel and fills {graph} and the {name} fields of ctx.fmt.
LEGEND = {
    "cite": "herron2022",  # bib key (morpheusai_supp.bib) cited after every mention of the authors
    "title": "Rosette patterns of GTPase activity during phagocytosis (Herron *et al.*, 2022).",
    "a": "The wave-pinning GAP model of Herron *et al.*: reaction scheme, spatial profiles of the modulated "
         "parameters with the resulting patterns of active GTPase (their Fig. 2A, C, D), and the rosette obtained "
         "with their fitted parameters, the benchmark target (their Fig. 4F).",
    "b": "Active GTPase *u* on the circular domain, starting from a random state (color bar below).",
    "c": "{graph}",
    "d": "**i**, Maximum, mean and minimum of *u* over the domain. Shading marks the first 20 s, during which the rosette "
         "forms in the paper's simulations (their S4 Fig). **ii**, Mean of *u* over all nodes at the same distance "
         "from the domain center, at three times. From 20 s on, the profile peaks at {r_peak} µm, just outside the "
         "edge of the IgG disk (dashed line), where the spots of the rosette sit. The model's spatially varying "
         "rates switch between their inner and outer values at this edge.",
    "abbrev": "GAP, GTPase-activating protein; IgG, immunoglobulin G.",
    "license": "Material from Herron *et al.* is adapted under a CC BY 4.0 license.",
}


def draw_b_key(fig, pos, y):
    """Below panel b's frames, centred: the colour bar of the run's u palette, 0–200 molecules µm⁻²."""
    x0 = pos[0][0]
    x1 = pos[-1][0] + pos[-1][2]
    bw, bh = 40.0, 1.6
    xb = (x0 + x1) / 2 - bw / 2
    text(fig, xb + bw / 2, y + 0.1, "Active GTPase u (molecules µm$^{-2}$)", ha="center", fontsize=style.FS)
    ax = mm_axes(fig, xb, y + 3.0, bw, bh)
    # one gradient image of 1024 palette steps: continuous, no seams between cells as with pcolormesh
    ax.imshow(np.linspace(0, 200, 1024)[None, :], extent=(0, 200, 0, 1), aspect="auto", cmap=U_CMAP, vmin=0,
              vmax=200, interpolation="nearest")
    ax.set(xlim=(0, 200), ylim=(0, 1), yticks=[])
    ax.set_xticks([0, 50, 100, 150, 200])
    for s in ("left", "right", "top"):
        ax.spines[s].set_visible(True)


def tiff_u(ctx):
    """u at TIFF_T from the run's TiffPlotter file (OME XYCZT, 4 channels: u is every 4th page) and the domain
    mask (u + v > 0; nodes outside the circular domain are 0 in every channel)."""
    im = Image.open(ctx.attempt(TIFF))
    pages = []
    for i in range(im.n_frames):
        im.seek(i)
        pages.append(np.asarray(im, dtype=float))
    u = {t: pages[4 * k] for k, t in enumerate(TIFF_T)}
    mask = (pages[0] + pages[1]) > 0
    return u, mask


def radial_profile(u, mask):
    """Mean of u over the domain nodes in rings of 1 node width around the domain centre (the mask centroid)."""
    yy, xx = np.nonzero(mask)
    cy, cx = yy.mean(), xx.mean()
    Y, X = np.indices(mask.shape)
    r = np.hypot(X - cx, Y - cy)[mask]
    k = np.floor(r).astype(int)
    n = np.bincount(k)
    out = {}
    for t, f in u.items():
        out[t] = np.bincount(k, f[mask]) / np.maximum(n, 1)
    rc = (np.arange(len(n)) + 0.5) * DX_UM
    ok = n > 0
    return rc[ok], {t: p[ok] for t, p in out.items()}


def draw(ctx, fig, box):
    d = ctx.csv("u_range.csv")
    b1, b2 = split(box, [1, 1], gap=12)

    ax = axes(fig, b1, label="i", left=14.0)
    ax.axvspan(0, 20, color="0.92", lw=0, zorder=0)
    ax.text(10, 0.62, "Rosette formation\n(paper, 0–20 s)", transform=ax.get_xaxis_transform(), ha="center",
            va="center", fontsize=style.FS)
    ax.plot(d.time_s, d.u_max_molecules_per_um2, color=C_MAX, label="Maximum")
    ax.plot(d.time_s, d.u_mean_molecules_per_um2, color=C_MEAN, label="Mean")
    ax.plot(d.time_s, d.u_min_molecules_per_um2, color=C_MIN, label="Minimum")
    ax.set(xlabel="Time (s)", ylabel="Active GTPase u\n(molecules µm$^{-2}$)", xlim=(0, d.time_s.max()),
           ylim=(0, 210))
    legend(ax, loc="center right")
    ctx.fmt.update(range_end=f"{d.u_range_molecules_per_um2.iloc[-1]:.1f}",
                   u_min_end=f"{d.u_min_molecules_per_um2.iloc[-1]:.2f}")
    T = d.gtpase_mean_molecules_per_um2
    Tg = d.gap_mean_molecules_per_um2
    ctx.fmt.update(T_mean=f"{T.min():g}" if T.min() == T.max() else f"{T.min():g}–{T.max():g}",
                   Tg_mean=f"{Tg.min():g}" if Tg.min() == Tg.max() else f"{Tg.min():g}–{Tg.max():g}")

    ax = axes(fig, b2, label="ii", left=14.0)
    u, mask = tiff_u(ctx)
    rc, prof = radial_profile(u, mask)
    ax.axvline(DISK_R_UM, color="0.35", lw=style.LW_REF, ls=(0, (2.5, 1.5)), zorder=1)
    ax.text(DISK_R_UM - 0.08, 0.97, "IgG disk edge", transform=ax.get_xaxis_transform(), ha="right", va="top",
            fontsize=style.FS)
    for t in PROFILE_T:
        ax.plot(rc, prof[t], color=C_PROF[t], label=f"{t} s")
    ax.set(xlabel="Distance from domain center (µm)", ylabel="Ring-averaged u\n(molecules µm$^{-2}$)",
           xlim=(0, 4), ylim=(0, None))
    legend(ax, loc="upper right")
    peaks = {t: rc[np.argmax(prof[t])] for t in (20, 30, 40)}
    ctx.fmt.update(r_peak="–".join(sorted({f"{p:.2f}" for p in peaks.values()})))
