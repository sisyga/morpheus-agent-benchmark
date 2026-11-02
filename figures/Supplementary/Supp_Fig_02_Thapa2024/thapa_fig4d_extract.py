"""Model 4 points of Thapa et al. (2024) Fig. 4D, read from the PDF's raster image (panel d-i of the Thapa figure
calls extract() on every build; running this script writes the cached copy below).

Fig. 4 is one raster image (1554 x 2658 pixels, placed at 300 dpi on page 6 = index 5 of
benchmark_papers/02_Thapa2024.pdf). Fig. 4D plots the fold change of the senescent area (wrt the initial area;
mean ± SD of n = 5 runs, every 12 h, 0-72 h) of the experiment and of Models 1-4. Model 4 is magenta (#F747D3):
diamonds, error bars with caps and a dashed connector between the means.

Calibration: the tick marks of Fig. 4D, found in the image (x ticks t = 0, 20, ..., 80 h below the x-axis line,
y ticks 0, 0.5, 1, 1.5 left of the y-axis line), mapped linearly; residuals are reported. Magenta pixels: colour
mask MAGENTA below (anti-aliased #F747D3; it excludes the red, green, blue and black series).

Per time point, in the column of the tick-calibrated time (+- 9 pixels):
  - 0 h: 1 by definition (fold change wrt the initial area); all five series start there and hide each other.
  - 12 h: hidden behind the other series' markers and error bars; omitted.
  - 24 h: the diamond is hidden behind the Model 1-3 markers, and red/blue anti-aliasing there passes the colour
    mask, so it is not read in its column. Instead, the dashed connector from 24 to 36 h (a straight segment
    between the two means) is fitted by a line to its visible dashes (25-34 h) and evaluated at 24 h. Its SD is
    not visible.
  - 36 h: the diamond is hidden behind the black experimental marker; the mean is the midpoint of the magenta
    error-bar caps, the SD half their distance. The upper cap is partly covered (one pixel row instead of two),
    so this point is less certain than 48 and 60 h (about +- 1 pixel = +- 0.004).
  - 48 and 60 h: mean = midpoint of the caps, SD = half their distance (symmetric error bars); the diamond centre
    is reported as a check.
  - 72 h: diamond centre; the error bar is shorter than the marker (SD not visible).
The connector fits between the later means (36-48, 48-60, 60-72 h), evaluated at their end points, are reported
as a check of the means.

    python figures/Supplementary/Supp_Fig_02_Thapa2024/thapa_fig4d_extract.py [--repo <repository root>]

Output: paper_data/fig4D_model4_points.csv with columns t_h, mean, sd, method (sd empty where not
visible).
"""
import argparse
import os

import numpy as np
import pandas as pd
import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = 5
# Fig. 4D inside the Fig. 4 image (pixels): plot area with its axes and tick marks, legend excluded
AX_X, AX_Y = (700, 1350), (2190, 2580)
X_TICKS, Y_TICKS = [0, 20, 40, 60, 80], [0.0, 0.5, 1.0, 1.5]
HALF = 9  # half width (pixels) of the column searched at each time point (diamond 17 pixels, caps 10)
OUT = os.path.join(HERE, "paper_data", "fig4D_model4_points.csv")


def MAGENTA(a):
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    return (R > 170) & (B > 140) & (G < 150) & (R - G > 80) & (B - G > 60)


def image(pdf):
    """The Fig. 4 raster image of page 6 (the page's only image) as an RGB array."""
    doc = pymupdf.open(pdf)
    xref = doc[PAGE].get_images(full=True)[0][0]
    pix = pymupdf.Pixmap(doc, xref)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[..., :3].astype(int)


def runs(idx):
    """Contiguous runs of sorted indices, as (first, last) pairs."""
    if len(idx) == 0:
        return []
    cut = np.where(np.diff(idx) > 1)[0]
    return list(zip(np.r_[idx[0], idx[cut + 1]], np.r_[idx[cut], idx[-1]]))


def calibration(a):
    """Linear maps pixel -> t (h) and pixel -> fold change from the tick marks, and the largest residuals."""
    dark = a.sum(2) < 200
    x0, x1 = AX_X
    y0, y1 = AX_Y
    yax = max(range(y0, y1), key=lambda y: dark[y, x0:x1].sum())  # x-axis line: darkest row
    xax = max(range(x0, x1), key=lambda x: dark[y0:y1, x].sum())  # y-axis line: darkest column
    xt = [(p + q) / 2 for p, q in runs(np.where(dark[yax + 3:yax + 10, xax - 3:x1].any(0))[0] + xax - 3)]
    yt = [(p + q) / 2 for p, q in runs(np.where(dark[y0:yax + 3, xax - 9:xax - 2].any(1))[0] + y0)]
    if len(xt) != len(X_TICKS) or len(yt) != len(Y_TICKS):
        raise ValueError(f"Fig. 4D ticks not found: x {xt}, y {yt}")
    fx = np.polyfit(xt, X_TICKS, 1)
    fy = np.polyfit(yt[::-1], Y_TICKS, 1)  # image rows grow downwards
    ex = np.abs(np.polyval(fx, xt) - X_TICKS).max()
    ey = np.abs(np.polyval(fy, yt[::-1]) - Y_TICKS).max()
    return fx, fy, ex, ey


def column(m, x, rows):
    """Wide magenta row groups (>= 6 pixels in the column x +- HALF) within rows: thin ones (<= 4 rows) are error-bar
    caps, thick ones (>= 8 rows) diamonds; as (first row, last row)."""
    w = m[rows[0]:rows[1], x - HALF:x + HALF + 1].sum(1)
    groups = [(p + rows[0], q + rows[0]) for p, q in runs(np.where(w >= 6)[0])]
    caps = [g for g in groups if g[1] - g[0] <= 3]
    diamonds = [g for g in groups if g[1] - g[0] >= 7]
    return caps, diamonds


def extract(pdf):
    """DataFrame t_h, mean, sd, method of the Model 4 points, and a list of check lines."""
    a = image(pdf)
    m = MAGENTA(a)
    fx, fy, ex, ey = calibration(a)
    t2x = lambda t: (t - fx[1]) / fx[0]
    v2y = lambda v: (v - fy[1]) / fy[0]
    y2v = lambda y: np.polyval(fy, y)
    checks = [f"tick fit residuals: t {ex:.3f} h, fold change {ey:.4f}"]
    rows = [dict(t_h=0.0, mean=1.0, sd=np.nan, method="1 by definition (fold change wrt the initial area)")]

    def connector(t0, t1, v_lo, v_hi):
        """Line through the mean magenta row of every column between t0 and t1 (fold change v_lo..v_hi)."""
        r0, r1 = int(v2y(v_hi)), int(v2y(v_lo))
        xs, ys = [], []
        for x in range(int(np.ceil(t2x(t0))), int(t2x(t1)) + 1):
            hit = np.where(m[r0:r1, x])[0]
            if len(hit):
                xs.append(x)
                ys.append(r0 + hit.mean())
        return np.polyfit(xs, ys, 1)

    c = connector(25, 34, 0.86, 1.02)
    rows.append(dict(t_h=24.0, mean=y2v(np.polyval(c, t2x(24))), sd=np.nan,
                     method="connector 24-36 h (dashes at 25-34 h) evaluated at 24 h; marker hidden"))
    checks.append(f"connector 24-36 h at 36 h: {y2v(np.polyval(c, t2x(36))):.4f}")
    span = (int(v2y(0.97)), int(v2y(0.35)))  # below the Model 1-3 markers (fold change >= 0.97)
    for t in (36, 48, 60, 72):
        x = int(round(t2x(t)))
        caps, diamonds = column(m, x, span)
        mid = lambda g: (g[0] + g[1]) / 2
        d = y2v(mid(diamonds[0])) if len(diamonds) == 1 else np.nan
        if len(caps) >= 2:
            top, bot = mid(caps[0]), mid(caps[-1])
            mean, sd = y2v((top + bot) / 2), (y2v(top) - y2v(bot)) / 2
            how = "midpoint of the error-bar caps" + ("; diamond hidden" if np.isnan(d) else "")
            if not np.isnan(d):
                checks.append(f"{t} h: diamond centre {d:.4f}, caps midpoint {mean:.4f}")
        elif not np.isnan(d) and not caps:
            mean, sd, how = d, np.nan, "diamond centre; error bar shorter than the marker"
        else:
            raise ValueError(f"Fig. 4D Model 4 at {t} h: caps {caps}, diamonds {diamonds}")
        rows.append(dict(t_h=float(t), mean=mean, sd=sd, method=how))
    for t0, t1, lo, hi in ((36, 48, 0.72, 0.92), (48, 60, 0.5, 0.75), (60, 72, 0.4, 0.58)):
        c = connector(t0 + 2, t1 - 2, lo, hi)
        checks.append(f"connector {t0}-{t1} h at its ends: {y2v(np.polyval(c, t2x(t0))):.4f}, "
                      f"{y2v(np.polyval(c, t2x(t1))):.4f}")
    return pd.DataFrame(rows), checks


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.dirname(HERE))), help="repository root")
    a = ap.parse_args()
    df, checks = extract(os.path.join(a.repo, "benchmark_papers", "02_Thapa2024.pdf"))
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        f.write("# Thapa et al. (2024) Fig. 4D, Model 4 (magenta): fold change of the senescent area, mean +- SD of "
                "n = 5 runs.\n# Written by figures/Supplementary/Supp_Fig_02_Thapa2024/thapa_fig4d_extract.py from the Fig. 4 raster image on "
                "page 6 of benchmark_papers/02_Thapa2024.pdf (see its docstring); 12 h hidden and omitted.\n")
        df.round(4).to_csv(f, index=False)
    print(df.round(4).to_string(index=False))
    print("\n".join(checks))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
