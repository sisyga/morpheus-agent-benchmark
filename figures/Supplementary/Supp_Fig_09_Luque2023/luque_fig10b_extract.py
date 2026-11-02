"""Mean curves of Luque et al. (2023) Fig. 10b (hepatocytes and cancer, fold increase vs days), extracted from the
raster image embedded in the PDF (panel d of the Luque figure reads the cached copies below).

Fig. 10 (benchmark_papers/09_Luque2023.pdf, page 17 = index 16) is one embedded JPEG (xref 487, 2000 x 1227
pixels, 300 dpi) without vector paths. Fig. 10b plots two mean lines (40 runs; hepatocytes green #008000, cancer
blue #0000ff) with +-SD bands at alpha 0.3 and no markers. This script finds, in every pixel column of the plot
area, the centroid of the line core (the dark, fully saturated pixels; the paler SD bands and the legend box are
excluded), maps it to data units with linear fits to the tick marks and fits a linear spline with knots at whole
days, the plotted lines being polylines through daily values.

Calibration (pixels of the embedded image, centres of the tick marks):
  x major ticks     day 0, 10, ..., 60 at x = 109.11, 251.06, 393.14, 534.88, 676.91, 818.99, 960.69
  y major ticks     0.0, 0.5, ..., 2.0 at y = 1088.75, 990.13, 891.27, 792.64, 693.68
Line cores (R, G, B of the decoded JPEG, 0-255):
  hepatocytes       G - R > 50, G - B > 50, R < 110
  cancer            B - R > 100, R < 110, G < 110
Masked: the legend box (x 390-695, y 850-975) and everything outside the plot frame (columns 110-960, rows
676-1089). The cancer line lies on the x axis until day 20; daily values below 0.006 there are set to 0.

    python figures/Supplementary/Supp_Fig_09_Luque2023/luque_fig10b_extract.py [--repo <repository root>] [--overlay <png>]

Output: paper_data/fig10b_hepatocytes.csv and fig10b_cancer.csv, columns day, fold (days 0-60).
--overlay also draws the daily values over the raster, to check the extraction by eye.
"""
import argparse
import io
import os

import numpy as np
import pandas as pd
import pymupdf
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE, XREF = 16, 487
X_TICKS = {0: 109.11, 10: 251.06, 20: 393.14, 30: 534.88, 40: 676.91, 50: 818.99, 60: 960.69}
Y_TICKS = {0.0: 1088.75, 0.5: 990.13, 1.0: 891.27, 1.5: 792.64, 2.0: 693.68}
COLS, ROWS = (110, 961), (676, 1090)  # plot area inside the frame (pixel columns, rows; end exclusive)
LEGEND = (slice(850, 975), slice(390, 695))  # rows, columns
DAYS = np.arange(61)
COLOURS = {"hepatocytes": "#008000", "cancer": "#0000ff"}  # line colours of Fig. 10b
OUT = {k: os.path.join(HERE, "paper_data", f"fig10b_{k}.csv") for k in COLOURS}


def fit(ticks):
    """Linear map from pixel coordinate to data value, fitted to the tick positions."""
    v, p = np.array(list(ticks.keys()), float), np.array(list(ticks.values()), float)
    b, a = np.polyfit(p, v, 1)
    return lambda q: a + b * np.asarray(q, float), np.abs(a + b * p - v).max()


def image(pdf):
    doc = pymupdf.open(pdf)
    assert any(im[0] == XREF for im in doc[PAGE].get_images()), f"image {XREF} not on page index {PAGE}"
    return np.asarray(Image.open(io.BytesIO(doc.extract_image(XREF)["image"])).convert("RGB")).astype(float)


def cores(im):
    R, G, B = im[..., 0], im[..., 1], im[..., 2]
    m = {"hepatocytes": (G - R > 50) & (G - B > 50) & (R < 110), "cancer": (B - R > 100) & (R < 110) & (G < 110)}
    keep = np.zeros(R.shape, bool)
    keep[ROWS[0]:ROWS[1], COLS[0]:COLS[1]] = True
    keep[LEGEND] = False
    return {k: v & keep for k, v in m.items()}


def hat(x):
    """Design matrix of the linear spline with knots at DAYS."""
    A = np.zeros((len(x), len(DAYS)))
    i = np.clip(np.floor(x).astype(int), 0, len(DAYS) - 2)
    t = x - i
    A[np.arange(len(x)), i] = 1 - t
    A[np.arange(len(x)), i + 1] = t
    return A


def extract(pdf):
    """Daily mean values {curve: DataFrame(day, fold)}, the column centroids {curve: (day, fold)} and the rms
    residual of each spline fit (fold units)."""
    im = image(pdf)
    fx, ex = fit(X_TICKS)
    fy, ey = fit(Y_TICKS)
    assert ex < 0.05 and ey < 0.005, (ex, ey)
    w = 255 - im[..., 0]  # weight: darkness in the red channel (the lines carry no red)
    out, cols, rms = {}, {}, {}
    for k, m in cores(im).items():
        xs, ys = [], []
        for x in range(*COLS):
            r = np.nonzero(m[:, x])[0]
            if len(r):
                xs.append(x)
                ys.append((r * w[r, x]).sum() / w[r, x].sum())
        d, f = fx(xs), fy(ys)
        A = hat(d)
        v, *_ = np.linalg.lstsq(A, f, rcond=None)
        if k == "cancer":  # the line runs on the x axis until about day 20
            v[(DAYS <= 20) & (v < 0.006)] = 0.0
        out[k] = pd.DataFrame(dict(day=DAYS, fold=v.round(4)))
        cols[k] = (d, f)
        rms[k] = float(np.sqrt(((f - A @ v) ** 2).mean()))
    return out, cols, rms


def overlay(pdf, out, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    im = image(pdf).astype(np.uint8)
    fx, _ = fit(X_TICKS)
    fy, _ = fit(Y_TICKS)
    H, W, _ = im.shape
    ext = (fx(-0.5), fx(W - 0.5), fy(H - 0.5), fy(-0.5))
    fig, axs = plt.subplots(1, 3, figsize=(18, 5), dpi=150)
    for a, (xl, yl) in zip(axs, (((-2, 62), (-0.1, 2.15)), ((-0.5, 10), (0.9, 2.05)), ((35, 61), (-0.02, 1.2)))):
        a.imshow(im, extent=ext, aspect="auto", interpolation="nearest")
        for k, df in out.items():
            a.plot(df.day, df.fold, "o", ms=4, mfc="none", mec="#ff00ff" if k == "hepatocytes" else "#ff8000",
                   mew=0.9, label=f"{k} (daily values)")
        a.set(xlim=xl, ylim=yl)
    axs[0].legend(loc="center right")
    fig.suptitle("Luque et al. (2023) Fig. 10b raster (xref 487) with the extracted daily values")
    fig.tight_layout()
    fig.savefig(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.dirname(HERE))), help="repository root")
    ap.add_argument("--overlay", help="also write a PNG of the daily values drawn over the raster")
    a = ap.parse_args()
    pdf = os.path.join(a.repo, "benchmark_papers", "09_Luque2023.pdf")
    out, _, rms = extract(pdf)
    for k, df in out.items():
        df.to_csv(OUT[k], index=False)
        f = df.set_index("day").fold
        print(f"{k}: {len(df)} days -> {OUT[k]}; spline rms residual {rms[k]:.4f} "
              f"({rms[k] / abs(fit(Y_TICKS)[0](1) - fit(Y_TICKS)[0](0)):.2f} px); "
              f"day 1 {f[1]:.3f}, day 8 {f[8]:.3f}, day 60 {f[60]:.3f}")
    if a.overlay:
        overlay(pdf, out, a.overlay)
        print("overlay ->", a.overlay)


if __name__ == "__main__":
    main()
