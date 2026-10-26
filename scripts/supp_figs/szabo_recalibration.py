"""Recalibration of the digitised Szabo et al. (2010) Fig. 7b monolayer curve (paper_data/1_Szabo_2010/
monolayer.csv).

Fig. 7b has log-log axes, but the curve was digitised with a linear axis calibration, so the CSV holds
values that are affine in log10(time) and log10(displacement). This script finds the two affine maps by
fitting the CSV to the red (monolayer) curve of the figure image used for the digitisation, whose axes are
calibrated from its tick marks (time 0.01-10 h, displacement 1-100 um). The first three CSV rows are the
legend's red line and are excluded. The fitted coefficients are written into paper_data.py (SZABO_MAP).

    python scripts/supp_figs/szabo_recalibration.py <fig_7b.png>

Input used for the published figures: log_plots/quantitative_extracted_data/1_Szabo_2010/fig_7b.png
(sha256 recorded in paper_data.py).
"""
import os
import sys

import numpy as np
import pandas as pd
from PIL import Image
from scipy.optimize import least_squares

HERE = os.path.dirname(os.path.abspath(__file__))


def ticks(mask, axis_px, along):
    """Pixel positions of tick marks: runs of >= 6 dark pixels next to the axis line."""
    if along == "y":
        prof = mask[:, axis_px + 2:axis_px + 10].sum(1)
    else:
        prof = mask[axis_px - 9:axis_px - 1, :].sum(0)
    idx = np.where(prof >= 6)[0]
    groups = np.split(idx, np.where(np.diff(idx) > 1)[0] + 1)
    return [g.mean() for g in groups]


def main(png):
    im = np.asarray(Image.open(png).convert("RGB")).astype(int)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    dark = (r < 70) & (g < 70) & (b < 70)
    red = (r > 200) & (g < 80) & (b < 80)
    # frame of the plot: longest dark column (left axis) and row (bottom axis)
    left = int(np.argmax(dark.sum(0)[:im.shape[1] // 2]))
    bottom = int(np.argmax(dark.sum(1)[im.shape[0] // 2:])) + im.shape[0] // 2
    yt = [t for t in ticks(dark, left, "y") if bottom - 5 > t > 50]  # 100, 10, 1 (top to bottom)
    xt = [t for t in ticks(dark, bottom, "x") if t > left - 3]  # 0.01, 0.1, 1, 10
    print("y ticks (px):", np.round(yt, 1), " x ticks (px):", np.round(xt, 1))
    y_dec = (yt[-1] - yt[0]) / (len(yt) - 1)  # px per decade; lowest tick = 1 um
    x_dec = (xt[-1] - xt[0]) / (len(xt) - 1)  # first tick = 0.01 h
    lt = lambda px: -2 + (px - xt[0]) / x_dec
    ld = lambda py: (yt[-1] - py) / y_dec
    cx, cy = [], []
    for x in range(int(xt[0]) + 4, int(xt[-1]) - 4):
        yy = np.where(red[:, x])[0]
        top = yt[0] - 5 if x < (xt[0] + xt[-1]) / 2 else 50  # skip the legend (upper left)
        yy = yy[(yy > top) & (yy < bottom - 3)]
        if len(yy):
            cx.append(lt(x))
            cy.append(ld(np.median(yy)))
    cx, cy = np.array(cx), np.array(cy)
    d = pd.read_csv(os.path.join(HERE, "paper_data", "1_Szabo_2010", "monolayer.csv"), header=None).iloc[3:]
    x, y = d[0].to_numpy(), d[1].to_numpy()
    res = lambda p: np.interp(p[0] + p[1] * x, cx, cy) - (p[2] + p[3] * y)
    fit = least_squares(res, [-2.0, 0.3, 0.0, 0.02])
    e = res(fit.x)
    print("log10(t/h) = %.5f + %.6f * x ; log10(D/um) = %.5f + %.6f * y" % tuple(fit.x))
    print("residual: rms %.4f, max %.4f decades" % (np.sqrt(np.mean(e ** 2)), np.abs(e).max()))


if __name__ == "__main__":
    main(sys.argv[1])
