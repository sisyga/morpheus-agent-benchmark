"""Scheel et al. (2021): agent-only. Panel a: the six concentration profiles of the run's Logger plot at times 0, 5
and 10, redrawn as vector line plots from the logged data (fields_raw.csv); panel c: spatial ranges of h, d and w vs
time and the head and tail boundary layers at the final time."""
import numpy as np
from matplotlib.lines import Line2D

import style
from figure import FIG_H, FIG_W, heading, mm_axes, text, text_width_mm
from panels.common import axes, legend, split

# Species colours of the run's own Gnuplot frames (Gnuplot's default line colours), used in a and c: s dark violet,
# h green, d sky blue, uh orange, ud yellow, wnt blue; the short-range signals uh and ud dashed
C_S, C_H, C_D, C_UH, C_UD, C_W = "#9400D3", "#009E73", "#56B4E9", "#E69F00", "#F0E442", "#0072B2"
DASH = (0, (3.0, 1.6))
SPECIES = [  # (column of fields_raw.csv, colour, line style, legend label)
    ("s", C_S, "-", "Stem cells s"),
    ("h", C_H, "-", "Head cells h"),
    ("d", C_D, "-", "Tail cells d"),
    ("uh", C_UH, DASH, "Head signal u$_h$"),
    ("ud", C_UD, DASH, "Tail signal u$_d$"),
    ("wnt", C_W, "-", "Wnt signal w"),
]
FRAME_T = [0.0, 5.0, 10.0]  # times of the frames in config.FRAMES (Logger Plot time-step 2.5)
ZOOM = 0.3  # width (paper length units) of the boundary layers shown in c(ii)

B_KEY_H = 4.2  # mm below the frames: line key of the six species
B_DRAW_IMAGES = False  # the placeholder crops only size the frame slots; draw_b draws the frames

B_SOURCE = "the run's logged profiles at times 0, 5 and 10"  # caption: replaces "the run's own Gnuplotter output"
B_EXEMPT = []  # panel a is vector graphics (the placeholder crops are blank)
B_CAPTION = ("the frames are redrawn here as vector line plots from the run's logged data, fields_raw.csv (Logger "
             "\"six spatial fields\", include-boundary=\"true\", every 0.1 time units: x_paper, s, h, d, uh, ud, "
             "wnt), at the times of the Gnuplot frames 0, 5 and 10 (dimensionless model time; the Logger's Plot "
             "wrote a frame every 2.5); the plotted values are those of the Gnuplot frames, whose raster titles, "
             "axis text and in-plot key (covering the curves) are replaced by our own axes and the line key below. "
             "Lines, in the colours of the run's frames: stem-cell density s (violet), head-cell density h (green), "
             "tail-cell density d (sky blue), the short-range head and tail signals uh (orange) and ud (yellow), "
             "both dashed, and the Wnt-related signal w (symbol wnt; blue), all dimensionless, vs position x in the "
             "paper's length units (x_paper, −L…L with L = 5, node spacing dx = 0.01). "
             "The points at x = ±5 are the logged boundary rows (space.x = −0.5 and 998.5), whose values are the "
             "model's Dirichlet face values, the mean of the boundary compartment and the first bulk node "
             "(BoundaryValue 0.5*(h_left+h_bulk_left) etc.), not the compartments themselves (c(ii)). At times 5 "
             "and 10, h, uh, d and ud are non-zero only within about 0.2 of the ends (c(ii))")
CAPTION = ("Agent-only quantification (the publication is not open access, so no paper data are shown). "
           "(i) Spatial range (maximum − minimum over the fragment, bulk and both boundary compartments) of the "
           "head-cell density h, the tail-cell density d and the Wnt signal w vs dimensionless time after cutting "
           "(ranges_raw.csv: h_range, d_range, wnt_range, logged every 10/99 time units), the quantity the "
           "benchmark asks for. The maximum of h is always the left boundary compartment and that of d the right "
           "one (h_range = h_left and d_range = d_right at every logged time; minima below 10⁻⁵⁷), so the ranges "
           "are the head density at the left end and the tail density at the right end; they exceed 0.01 from "
           "time {h_on} (h) and {d_on} (d) and reach {h_end} and {d_end} at time 10; the Wnt range grows from "
           "0.02 (the initial linear gradient from 0.70 to 0.72) to {w_end}. (ii) Profiles at the final time 10 within "
           "{zoom} of the two ends of the fragment (x axis broken, grey band: {xin_lo} to {xin_hi} "
           "not shown; left: head end, right: tail end): h and uh, "
           "d and ud and w at the bulk nodes (fields_raw.csv, x_paper = ±4.99 and inwards) and the dynamic "
           "boundary compartments at x = ±5 (markers: h_left, uh_left, wnt_left and d_right, ud_right, "
           "wnt_right from boundary_states_raw.csv; filled for h, d and w, open for uh and ud; at x = ±5 the frames in a show the face values instead, e.g. "
           "h = {h_face} vs h_left = {h_left}); h and uh are below {h_far} at the tail end, d and ud "
           "below {d_far} at the head end, and are not drawn there. Colours and line styles as in a. x and "
           "time in the paper's dimensionless units (x_paper = −L + (space.x + 1) dx in model.xml).")


# Publication legend (legend.py): keys are the panel letters as printed; legend.py prepends the run sentence to the
# frames panel and fills {graph} and the {name} fields of ctx.fmt.
LEGEND = {
    "cite": "scheel2021",  # bib key (morpheusai_supp.bib) cited after every mention of the authors
    "title": "Planarian regeneration after cutting (Scheel *et al.*, 2021).",
    "a": "Profiles along the fragment at three times, redrawn from the run's logged data: stem-cell density *s*, "
         "head-cell density *h*, tail-cell density *d*, short-range head and tail signals *u*<sub>h</sub> and "
         "*u*<sub>d</sub> (dashed) and the Wnt-related signal *w*. Position and time are dimensionless, in the units of "
         "Scheel *et al.*",
    "b": "{graph}",
    "c": "**i**, Spatial range (maximum minus minimum) of *h*, *d* and *w* "
         "against time after cutting, the quantity the benchmark asks for. The ranges of *h* and *d* equal the head "
         "density at the left end and the tail density at the right end. **ii**, Profiles at the final time near the "
         "two ends, with the *x* axis broken between {xin_lo} and {xin_hi}. Lines show the interior and circles the "
         "boundary compartments at the ends (filled for *h*, *d* and *w*, open for *u*<sub>h</sub> and *u*<sub>d</sub>). Head "
         "variables are negligible at the tail end and tail variables at the head end, so they are not drawn there.",
}


def draw_b(ctx, fig, pos, y):
    """Panel a: one vector line plot per frame time in the frame slots, and the line key of the six species in one
    row below the frames."""
    frames(ctx, fig, ctx.csv("fields_raw.csv"), pos)
    x0, x1 = pos[0][0], pos[-1][0] + pos[-1][2]
    seg, gap_t, gap = 4.0, 0.8, 3.2  # mm: line sample, line-to-text, item spacing
    widths = [seg + gap_t + text_width_mm(lab) for _, _, _, lab in SPECIES]
    xx = (x0 + x1) / 2 - (sum(widths) + gap * (len(widths) - 1)) / 2
    yl = y + 1.9  # mm, line height of the key
    for (_, c, ls, lab), w in zip(SPECIES, widths):
        fig.lines.append(Line2D([xx / FIG_W, (xx + seg) / FIG_W], [1 - yl / FIG_H] * 2, transform=fig.transFigure,
                                color=c, ls=ls, lw=style.LW_DATA))
        text(fig, xx + seg + gap_t, yl, lab, va="center_baseline", fontsize=style.FS)
        xx += w + gap


def _sci(v):
    """Upper bound 1 x 10^n (n rounded up) as printed text, e.g. 8.3e-08 -> '10⁻⁷'."""
    n = int(np.ceil(np.log10(v)))
    return "10" + str(n).translate(str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹"))


def frames(ctx, fig, f, pos):
    """Panel a: one vector line plot per frame time, in the frame slots of the layout."""
    for i, ((x, y, w, h), T) in enumerate(zip(pos, FRAME_T)):
        e = f[np.isclose(f["T"], T)].sort_values("x_paper")
        ax = mm_axes(fig, x + 7.6, y + 0.6, w - 8.4, h - 7.2)
        for col, c, ls, _ in SPECIES:
            ax.plot(e.x_paper, e[col], color=c, ls=ls, lw=style.LW_DATA, clip_on=False)
        ax.set(xlim=(-5, 5), ylim=(0, 1.05), xticks=[-4, -2, 0, 2, 4], yticks=[0, 0.5, 1])
        ax.set_yticklabels(["0", "0.5", "1"])
        ax.set_xlabel("Position x")
        if i == 0:
            ax.set_ylabel("Density or signal")


def draw(ctx, fig, box):
    f = ctx.csv("fields_raw.csv")
    r = ctx.csv("ranges_raw.csv")
    bs = ctx.csv("boundary_states_raw.csv")

    b1, b2 = split(box, [1, 1.25], gap=12)
    ax = axes(fig, b1, label="i")
    ax.plot(r["T"], r.h_range, color=C_H, label="Head cells h")
    ax.plot(r["T"], r.d_range, color=C_D, label="Tail cells d")
    ax.plot(r["T"], r.wnt_range, color=C_W, label="Wnt signal w")
    ax.set(xlabel="Time (dimensionless)", ylabel="Spatial range (max − min)", xlim=(0, 10), ylim=(0, 1.0))
    legend(ax, loc="lower right")

    # (ii) boundary layers at the final time, broken x axis: head end | tail end
    T = 10.0
    e = f[np.isclose(f["T"], T) & (f["space.x"] >= 0) & (f["space.x"] <= 998)].sort_values("x_paper")
    b = bs[np.isclose(bs["T"], T)].iloc[0]
    x, y, w, h = b2
    left, bottom, top, mid = 10.5, 8.0, 6.0, 6.0
    wa = (w - left - 1.0 - mid) / 2
    heading(fig, x + 1.5, y, "ii")
    axl = mm_axes(fig, x + left, y + top, wa, h - top - bottom)
    axr = mm_axes(fig, x + left + wa + mid, y + top, wa, h - top - bottom)
    lo, hi = e[e.x_paper <= -5 + ZOOM], e[e.x_paper >= 5 - ZOOM]
    mk = dict(marker="o", ms=2.6, mew=0.5, ls="none", clip_on=False, zorder=4)
    for col, c, ls, lab in SPECIES:
        if col in ("h", "uh", "wnt"):
            axl.plot(lo.x_paper, lo[col], color=c, ls=ls, label=lab, clip_on=False)
            axl.plot([-5], [b[f"{col}_left"]], color=c, mfc=c if ls == "-" else "white", **mk)
        if col in ("d", "ud", "wnt"):
            axr.plot(hi.x_paper, hi[col], color=c, ls=ls, label=None if col == "wnt" else lab, clip_on=False)
            axr.plot([5], [b[f"{col}_right"]], color=c, mfc=c if ls == "-" else "white", **mk)
    axl.set(xlim=(-5, -5 + ZOOM), ylim=(0, 1.0), xticks=[-5, -4.9, -4.8], ylabel="Density or signal at time 10")
    axr.set(xlim=(5 - ZOOM, 5), ylim=(0, 1.0), xticks=[4.8, 4.9, 5])
    axl.set_xticklabels(["−5", "−4.9", "−4.8"])
    axr.set_xticklabels(["4.8", "4.9", "5"])
    axr.spines["left"].set_visible(False)
    axr.tick_params(axis="y", left=False, labelleft=False)
    # axis break: a light grey band over the omitted interval with a double break mark on the x axis, and the two
    # ends named above the halves
    xg0, xg1 = x + left + wa, x + left + wa + mid
    yt, yb = y + top, y + h - bottom
    band = mm_axes(fig, xg0, yt, mid, yb - yt, zorder=0)
    band.set_facecolor("0.92")
    band.set(xticks=[], yticks=[])
    for s in band.spines.values():
        s.set_visible(False)
    d = 1.0  # mm
    for xb in (xg0 + 1.2, xg1 - 1.2):
        for dx in (-0.35, 0.35):
            fig.lines.append(Line2D([(xb + dx - d / 2) / FIG_W, (xb + dx + d / 2) / FIG_W],
                                    [1 - (yb + d / 2) / FIG_H, 1 - (yb - d / 2) / FIG_H],
                                    transform=fig.transFigure, color="black", lw=0.5))
    text(fig, xg0 + mid / 2, (yt + yb) / 2,
         f"x axis broken: {-5 + ZOOM:g} to {5 - ZOOM:g} not shown".replace("-", "−"),
         ha="center", va="center", rotation=90)
    text(fig, xg0 - wa / 2, y + 2.6, "Head end", ha="center", va="center")
    text(fig, xg1 + wa / 2, y + 2.6, "Tail end", ha="center", va="center")
    axl.set_xlabel("Position x")
    axl.xaxis.label.set_x((wa + mid / 2) / wa)  # centred under both halves
    legend(axl, loc="upper right")
    legend(axr, loc="upper left")

    on = lambda c: r["T"][r[c] > 0.01].iloc[0]
    far_h = max(e.loc[e.x_paper >= 5 - ZOOM, ["h", "uh"]].to_numpy().max(), b.h_right, b.uh_right)
    far_d = max(e.loc[e.x_paper <= -5 + ZOOM, ["d", "ud"]].to_numpy().max(), b.d_left, b.ud_left)
    e10 = f[np.isclose(f["T"], T)].sort_values("x_paper")
    ctx.fmt.update(h_on=f"{on('h_range'):.2f}", d_on=f"{on('d_range'):.2f}", h_end=f"{r.h_range.iloc[-1]:.3f}",
                   d_end=f"{r.d_range.iloc[-1]:.3f}", w_end=f"{r.wnt_range.iloc[-1]:.3f}", zoom=f"{ZOOM:g}",
                   h_far=_sci(far_h), d_far=_sci(far_d),
                   xin_lo=f"−{5 - ZOOM:g}", xin_hi=f"{5 - ZOOM:g}", h_face=f"{e10.h.iloc[0]:.3f}", h_left=f"{b.h_left:.3f}")
    assert np.allclose(r.h_range, r.h_left) and np.allclose(r.d_range, r.d_right)
