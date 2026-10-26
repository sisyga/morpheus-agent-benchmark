"""Curves of Berkemeier & Page (2023) Fig. 4a taken from the PDF's vector paths (panel d-i of the Berkemeier
figure calls extract() on every build; running this script writes the cached copy below).

Fig. 4a (6 x 6 periodic lattice, epsilon ~ 0.09) is vector graphics: every cell's Delta activity is one
coloured stroke path. This script keeps the coloured stroke paths inside the panel's plot frame (the grey
frame, tick and label paths are dropped) and maps their vertices to data units with linear fits to the major
tick marks.

Calibration (benchmark_papers/05_Berkemeier2023.pdf, page 6 = index 5, PDF points, y down):
  plot frame        x 60.278 - 159.066, y 57.631 - 123.490 (grey stroke 0.25 pt)
  x major ticks     t = 0, 20, ..., 120 at x = 62.254, 78.060, 93.865, 109.673, 125.479, 141.283, 157.090
  y major ticks     D = 0.0, 0.2, ..., 1.0 at y = 123.490, 110.317, 97.146, 83.974, 70.803, 57.631
  The frame's top and bottom edges coincide with D = 1 and D = 0.

    python scripts/supp_figs/berkemeier_fig4a_extract.py [--repo <repository root>]

Output: paper_data/5_Berkemier/fig4a_vector_paths.csv with columns curve_id, t, D (vertices in path order).
"""
import argparse
import os

import numpy as np
import pandas as pd
import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = 5
FRAME = pymupdf.Rect(60.278, 57.631, 159.066, 123.490)
X_TICKS = {0: 62.254, 20: 78.060, 40: 93.865, 60: 109.673, 80: 125.479, 100: 141.283, 120: 157.090}
Y_TICKS = {0.0: 123.490, 0.2: 110.317, 0.4: 97.146, 0.6: 83.974, 0.8: 70.803, 1.0: 57.631}
OUT = os.path.join(HERE, "paper_data", "5_Berkemier", "fig4a_vector_paths.csv")


def fit(ticks):
    """Linear map from PDF coordinate to data value, fitted to the tick positions."""
    v, p = np.array(list(ticks.keys()), float), np.array(list(ticks.values()), float)
    b, a = np.polyfit(p, v, 1)
    return lambda q: a + b * np.asarray(q, float), np.abs(a + b * p - v).max()


def is_grey(c):
    return c is not None and max(c) - min(c) < 0.02


def extract(pdf):
    page = pymupdf.open(pdf)[PAGE]
    fx, ex = fit(X_TICKS)
    fy, ey = fit(Y_TICKS)
    rows, n = [], 0
    for d in page.get_drawings():
        # 0.5 pt tolerance: curves at D = 1 run along the frame's top edge (line width 0.53 pt)
        if d["type"] != "s" or is_grey(d.get("color")) or not (FRAME + (-0.5, -0.5, 0.5, 0.5)).contains(d["rect"]):
            continue
        pts = []
        for it in d["items"]:
            if it[0] == "l":
                pts += [it[1], it[2]]
            elif it[0] == "c":
                pts += [it[1], it[4]]
        xy = np.array([(p.x, p.y) for p in pts])
        keep = np.r_[True, np.any(np.diff(xy, axis=0) != 0, axis=1)]  # drop repeated joint vertices
        xy = xy[keep]
        rows.append(pd.DataFrame(dict(curve_id=n, t=fx(xy[:, 0]), D=fy(xy[:, 1]))))
        n += 1
    return pd.concat(rows, ignore_index=True), ex, ey


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(HERE)), help="repository root")
    a = ap.parse_args()
    df, ex, ey = extract(os.path.join(a.repo, "benchmark_papers", "05_Berkemeier2023.pdf"))
    df.round(5).to_csv(OUT, index=False)
    print(f"{df.curve_id.nunique()} curves, {len(df)} vertices -> {OUT}")
    print(f"tick fit residuals: t {ex:.4f}, D {ey:.5f}")


if __name__ == "__main__":
    main()
