"""Apoptosis-on cell-number curve of Carpenter et al. (2024) Fig. 2A, taken from the published PDF's vector paths
(panel d of the Carpenter figure reads the cached copy below).

Fig. 2A (benchmark_papers/03_Carpenter2024.pdf, page 5 = index 4) is vector graphics: each condition is a stroked
line with a filled circle on every data point (the mean of five simulations, every 2/3 tau0) and a pale SD band.
The apoptosis-on line is the only stroke path left of x = 175 pt and above y = 150 pt with the orange colour
(0.824, 0.412, 0.118) and a line width of 0.369 pt. Its vertices are not quite the data points: the plotting
software dropped the vertex at 3.8 tau0 (nearly collinear) and the line runs on under the plot frame's clip to
51.2 tau0. This script therefore takes the centres of the orange filled circles (1.23 pt wide) that lie on that
line (within 0.1 pt; this leaves out the legend's circle), 1.1-49.8 tau0, and maps them to data units with
linear fits to the axis ticks.

Calibration (PDF points, y down):
  x major ticks     t = 0, 20, 40 tau0 at x = 88.854, 121.672, 154.491
  y major ticks     N = 0, 1, 2 (x 10^3 cells) at y = 143.307, 110.872, 78.437

    python figures/Supplementary/Supp_Fig_03_Carpenter2024/carpenter_fig2a_extract.py [--repo <repository root>]

Output: paper_data/fig2A_apoptosis_on_vector.csv with columns t_tau0, cells (data points in
time order).
"""
import argparse
import os

import numpy as np
import pandas as pd
import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = 4
ORANGE, WIDTH = (0.824, 0.412, 0.118), 0.369  # colour of the apoptosis-on line and markers; line width (pt)
MARKER = 1.3  # pt; the filled circles are 1.23 pt wide (their 1.48 pt edges are separate fills)
ON_LINE = 0.1  # pt; largest distance of a data marker's centre from the line
REGION = (175.0, 150.0)  # Fig. 2A lies left of x and above y (PDF points)
X_TICKS = {0: 88.854, 20: 121.672, 40: 154.491}
Y_TICKS = {0: 143.307, 1000: 110.872, 2000: 78.437}
OUT = os.path.join(HERE, "paper_data", "fig2A_apoptosis_on_vector.csv")


def fit(ticks):
    """Linear map from PDF coordinate to data value, fitted to the tick positions."""
    v, p = np.array(list(ticks.keys()), float), np.array(list(ticks.values()), float)
    b, a = np.polyfit(p, v, 1)
    return lambda q: a + b * np.asarray(q, float), np.abs(a + b * p - v).max()


def orange(c):
    return c is not None and np.allclose(c, ORANGE, atol=2e-3)


def distance(p, line):
    """Distance of points p (n x 2) from the polyline (m x 2)."""
    a, b = line[:-1], line[1:]
    ab = b - a
    u = np.clip(((p[:, None, :] - a) * ab).sum(-1) / (ab ** 2).sum(-1), 0, 1)
    return np.hypot(*(p[:, None, :] - a - u[..., None] * ab).transpose(2, 0, 1)).min(1)


def extract(pdf):
    page = pymupdf.open(pdf)[PAGE]
    fx, ex = fit(X_TICKS)
    fy, ey = fit(Y_TICKS)
    dr = [d for d in page.get_drawings() if d["rect"].x1 < REGION[0] and d["rect"].y1 < REGION[1]]
    lines = [d for d in dr
             if d["type"] == "s" and orange(d.get("color")) and abs((d.get("width") or 0) - WIDTH) < 0.01]
    assert len(lines) == 1, f"{len(lines)} candidate lines"
    items = lines[0]["items"]
    assert all(it[0] == "l" for it in items)
    line = np.array([(it[1].x, it[1].y) for it in items] + [(items[-1][2].x, items[-1][2].y)])
    dots = np.array([((d["rect"].x0 + d["rect"].x1) / 2, (d["rect"].y0 + d["rect"].y1) / 2) for d in dr
                     if "f" in d["type"] and orange(d.get("fill")) and d["rect"].width < MARKER])
    xy = dots[distance(dots, line) < ON_LINE]
    xy = xy[np.argsort(xy[:, 0])]
    assert len(dots) - len(xy) == 1, "expected exactly one marker off the line (the legend's)"
    return pd.DataFrame(dict(t_tau0=fx(xy[:, 0]), cells=fy(xy[:, 1]))), ex, ey


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.dirname(HERE))), help="repository root")
    a = ap.parse_args()
    df, ex, ey = extract(os.path.join(a.repo, "benchmark_papers", "03_Carpenter2024.pdf"))
    df.round(4).to_csv(OUT, index=False)
    print(f"{len(df)} data points, t = {df.t_tau0.min():.2f}-{df.t_tau0.max():.2f} tau0 -> {OUT}")
    print(f"tick fit residuals: t {ex:.4f} tau0, N {ey:.3f} cells")
    print(df[(df.t_tau0 > 34) & (df.t_tau0 < 36)].round(1).to_string(index=False))


if __name__ == "__main__":
    main()
