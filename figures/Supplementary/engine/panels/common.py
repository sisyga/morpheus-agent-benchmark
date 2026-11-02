"""Helpers for panel d: placing axes in mm inside the panel box, sub-panel labels, paper-data styles."""
import numpy as np

import style
from figure import heading, legend_hits, mm_axes

PAPER_LABEL = "Paper (digitized)"
AGENT_LABEL = "Agent-generated model"  # legend label of the agent's curve, as in Fig. 2


def paper_label(author, year, et_al=True):
    """Legend label of a paper's data, as in Fig. 2: 'Thapa et al. (2024)' with 'et al.' in italics (mathtext
    italic, which style.py maps to Arial Italic, so it stays live Arial text in SVG and PDF)."""
    # no space before "(": mathtext already ends the italic run with a space-wide gap
    return rf"{author} $\it{{et}}$ $\it{{al.}}$({year})" if et_al else f"{author} ({year})"


def split(box, fracs, gap=10.0):
    """Split box (x, y, w, h) horizontally into parts with relative widths fracs."""
    x, y, w, h = box
    tot = w - gap * (len(fracs) - 1)
    out = []
    for f in fracs:
        ww = tot * f / sum(fracs)
        out.append((x, y, ww, h))
        x += ww + gap
    return out


def vsplit(box, fracs, gap=6.0):
    x, y, w, h = box
    tot = h - gap * (len(fracs) - 1)
    out = []
    for f in fracs:
        hh = tot * f / sum(fracs)
        out.append((x, y, w, hh))
        y += hh + gap
    return out


def axes(fig, box, left=10.5, bottom=8.0, right=1.0, top=4.2, label=None, **kw):
    """Axes inside box with margins (mm) for tick and axis labels; optional sub-panel numeral (i, ii) in 8 pt
    bold at the box's top-left, above the top tick label."""
    x, y, w, h = box
    if label:
        heading(fig, x + 1.5, y, label)
    return mm_axes(fig, x + left, y + top, w - left - right, h - top - bottom, **kw)


def paper(ax, x, y, label=PAPER_LABEL, line=False, **kw):
    """Digitised paper data: open black circles (optionally joined by a dashed grey line)."""
    kws = dict(style.PAPER_KW)
    kws.update(kw)
    if line:
        ax.plot(x, y, **style.PAPER_LINE_KW)
    return ax.plot(x, y, label=label, **kws)[0]


LOCS = ["upper left", "upper right", "lower left", "lower right", "center left", "center right", "upper center",
        "lower center", "center"]


def _clear(ax, leg, r):
    """True if the legend (plus 2 pt) covers no data (figure.legend_hits) and no annotation text of its axes."""
    if legend_hits(ax.figure, leg, r, pad_pt=2.0):  # placement keeps 2 pt clear; the reported check uses 1 pt
        return False
    b = leg.get_window_extent(r)
    return not any(b.overlaps(t.get_window_extent(r)) for t in ax.texts if t.get_visible() and t.get_text())


def legend(ax, loc=None, **kw):
    """Frameless legend where it covers no data: loc first, then the other inside positions; if none is free,
    the y range is extended (up to 45 %) for the upper positions; last resort, one row above the axes.
    Call it after everything is drawn in this axes (and its twin) and the limits are set."""
    fig = ax.figure
    r = fig.canvas.get_renderer()
    for a in fig.axes:  # settle autoscaled limits before measuring in display space
        a.get_xlim(), a.get_ylim()
    for l in ([loc] if loc else []) + [l for l in LOCS if l != loc]:
        leg = ax.legend(loc=l, **kw)
        if _clear(ax, leg, r):
            return leg
    lo, hi = ax.get_ylim()
    for f in (1.15, 1.3, 1.45):
        ax.set_ylim(lo, hi * (hi / lo) ** (f - 1) if ax.get_yscale() == "log" else lo + (hi - lo) * f)
        for l in ("upper left", "upper right", "upper center"):
            leg = ax.legend(loc=l, **kw)
            if _clear(ax, leg, r):
                return leg
    ax.set_ylim(lo, hi)
    n = len(ax.get_legend_handles_labels()[0]) if "handles" not in kw else len(kw["handles"])
    kw.setdefault("ncol", n)
    return ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), borderaxespad=0.3, **kw)


def fold(v):
    v = np.asarray(v, float)
    return v / v[0]
