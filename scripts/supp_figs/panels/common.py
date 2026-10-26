"""Helpers for panel d: placing axes in mm inside the panel box, sub-panel labels, paper-data styles."""
import numpy as np

import style
from figure import mm_axes, text

PAPER_LABEL = "paper (digitised)"


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


def axes(fig, box, left=9.0, bottom=7.5, right=1.0, top=2.5, label=None, **kw):
    """Axes inside box with margins (mm) for tick and axis labels; optional sub-panel label (i, ii)."""
    x, y, w, h = box
    if label:
        text(fig, x + 1.0, y, label, fontsize=style.FS, fontweight="bold")
    return mm_axes(fig, x + left, y + top, w - left - right, h - top - bottom, **kw)


def paper(ax, x, y, label=PAPER_LABEL, line=False, **kw):
    """Digitised paper data: open black circles (optionally joined by a dashed grey line)."""
    kws = dict(style.PAPER_KW)
    kws.update(kw)
    if line:
        ax.plot(x, y, **style.PAPER_LINE_KW)
    return ax.plot(x, y, label=label, **kws)[0]


def legend(ax, **kw):
    kw.setdefault("loc", "best")
    return ax.legend(**kw)


def fold(v):
    v = np.asarray(v, float)
    return v / v[0]
