"""Panel b of the Malkmus et al. (2025) figure: the run's Gnuplotter frames rearranged as one column per species.

Every frame (plot_<time>.png, 1500 x 884 pixels) holds six Gnuplotter plots in a 3 x 2 grid (Sfrp2, WNT2,
beta_cat / BMP2, SULF1, Sox9), each a field image with a Gnuplot title, a colour bar and its tick text. Each
field image is cropped to the circular domain plus about one lattice node of the black background (no titles,
colour bars or raster text remain), in the run's own colours; the crops of the frames in config.FRAMES are stacked
into one column per species, one row per frame time. The figure's own 6 pt text names the species (above the
columns) and the times (left of the rows), and one colour key replaces the six Gnuplot colour bars
(p12_malkmus.draw_b_key).

Colour ramps: every plot's ColorMap in the scored model.xml is a linear ramp from black (value 0) to one colour c
(value 2), fixed range (adaptive-range="false", min="0", max="2" for all six). Each pixel p of a plot is t * c with
t = value / 2 = p.c / |c|^2; ramp() redraws it as t * c (within 1 RGB level, residual reported) and gives the value.
"""
import os

import numpy as np
from PIL import Image

import config

KEY = "12_Malkmus2025"
# Gnuplotter plot order. (symbol, label, colour of value 2 in the run's ColorMap, line style in panel d). The
# follower of each in-phase pair of the final pattern (SULF1 of Sox9, beta_cat of WNT2) is dashed in panel d, which
# also sets these two apart from WNT2, the third blue.
SPECIES = [("Sfrp2", "Sfrp2", "#ff00ff", "-"),
           ("WNT2", "WNT2", "#00bfff", "-"),
           ("beta_cat", "β-catenin", "#0066dd", (0, (3, 1.5))),
           ("BMP2", "BMP2", "#00aa55", "-"),
           ("SULF1", "SULF1", "#00e5e5", (0, (3, 1.5))),
           ("Sox9", "Sox9", "#ff3333", "-")]
VMAX = 2.0  # ColorMap value of the full colour (all six plots: min 0, max 2)
# field images of the six plots in the frame: left columns 12, 511, 1011 and top rows 32, 473 (385 x 385 pixels,
# first row and column anti-aliased with the plot border). The domain disc (lattice nodes 5-104 of 110 at
# 3.5 pixels per node) spans pixels 17-366 of each image; the crop keeps pixels 13-370 (358 x 358).
IMG_X0 = (12, 511, 1011)
IMG_Y0 = (32, 473)
CROP = (13, 371)
DISC_CENTRE = 191.5  # pixels, in each plot image (the disc spans pixels 17-366)
GAP_PX = 24  # white rows between the frame times in a species column (about 1 mm as printed)


def _hex(c):
    return np.array([int(c[i:i + 2], 16) for i in (1, 3, 5)], float)


def ramp(sub, colour):
    """Black-to-colour ramp image redrawn from its values: (image, value t*VMAX per pixel, max RGB residual)."""
    p = sub.reshape(-1, 3).astype(float)
    c = _hex(colour)
    t = np.clip(p @ c / (c @ c), 0.0, 1.0)
    res = float(np.linalg.norm(p - t[:, None] * c[None], axis=1).max())
    out = np.clip(np.round(t[:, None] * c[None]), 0, 255).astype(np.uint8).reshape(sub.shape)
    return out, (t * VMAX).reshape(sub.shape[:2]), res


def crops(path):
    """The six field images of one frame, in plot order: [(image, max residual)]."""
    im = np.asarray(Image.open(path).convert("RGB"))
    out = []
    for k, (_, _, colour, _) in enumerate(SPECIES):
        x0, y0 = IMG_X0[k % 3], IMG_Y0[k // 3]
        sub = im[y0 + CROP[0]:y0 + CROP[1], x0 + CROP[0]:x0 + CROP[1]]
        img, _, res = ramp(sub, colour)
        img[outside(sub)] = 255  # nodes outside the circular domain (Gnuplot value 0, black) drawn white
        out.append((img, res))
    return out


def outside(sub):
    """Pixels of a cropped plot outside the circular domain: exactly black in the Gnuplot image (value 0; inside
    the domain every field is > 0) and more than 150 pixels from the disc centre (disc radius 175 pixels)."""
    n = sub.shape[0]
    yy, xx = np.mgrid[0:n, 0:n]
    c = DISC_CENTRE - CROP[0]
    return (sub.max(axis=-1) <= 3) & (np.hypot(xx - c, yy - c) > 150)


def columns(ctx):
    """Panel b rows for figure.build: one row of six species columns, each the stacked crops of the frames in
    config.FRAMES (top to bottom), labelled with the species name."""
    frames = [crops(ctx.attempt(f, role="panel b frame")) for f, _ in config.FRAMES[KEY]]
    n = CROP[1] - CROP[0]
    cols = []
    for k, (_, lab, _, _) in enumerate(SPECIES):
        col = np.full((len(frames) * n + (len(frames) - 1) * GAP_PX, n, 3), 255, np.uint8)
        for i, fr in enumerate(frames):
            col[i * (n + GAP_PX):i * (n + GAP_PX) + n] = fr[k][0]
        cols.append((col, lab))
    return [cols]


def row_centres(pos):
    """Vertical centres (mm) of the frame-time rows, from the position (x, y, w, h) of a species column."""
    n, m = CROP[1] - CROP[0], len(config.FRAMES[KEY])
    H = m * n + (m - 1) * GAP_PX
    _, y, _, h = pos
    return [y + (i * (n + GAP_PX) + n / 2) / H * h for i in range(m)]


if __name__ == "__main__":  # residual check: python malkmus_frames.py <attempt folder>
    import sys
    for f, _ in config.FRAMES[KEY]:
        for (sym, *_), (_, r) in zip(SPECIES, crops(os.path.join(sys.argv[1], f))):
            print(f, sym, f"max residual {r:.2f}")
