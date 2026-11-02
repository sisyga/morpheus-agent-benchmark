"""High-Delta cells and clusters of Berkemeier & Page (2023) Fig. 1f (14 x 14 periodic lattice, epsilon = 1), taken
from the PDF's vector fills (panel d of the Berkemeier figure calls fig1f() on every build), and the same cluster
statistics for the agent's logged cell states (cells(), clusters()).

Fig. 1c-f (benchmark_papers/05_Berkemeier2023.pdf, page 3 = index 2) are vector graphics: every cell is one
filled and stroked flat-top hexagon (width 9.97 pt, height 8.63 pt), green (0.373, 0.675, 0.212) for low Delta
and white for high Delta (caption: "SOP cells (white, high Delta, low Notch)"). The four 196-cell panels are
told apart by position; Fig. 1f is the bottom-right one (hexagon centres x > 368 pt, y > 195 pt). The fill
colours are bimodal (all 39 cells of Fig. 1f with red channel >= 0.5 of the way to white are pure white), so
"high Delta" = white fill, which matches D >= 0.5 of the agent's analysis.

Clusters: connected components of high-Delta cells on the six direct neighbours of the periodic lattice
(torus distance of hexagon centres within 1.1 centre spacings), singletons included, as in the agent's
analysis (analysis.json: "components of high-Delta cells on actual physical contacts, including singletons").

    python figures/Supplementary/Supp_Fig_05_Berkemeier2023/berkemeier_fig1f_extract.py [--repo <repository root>]
"""
import argparse
import os

import numpy as np
import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = 2
N = 14  # lattice size of Fig. 1c-f (caption)


def clusters(xy, high, period, spacing):
    """Sizes of the connected components of the high cells; neighbours: periodic distance < 1.1 spacing."""
    p = xy[high]
    d = p[:, None, :] - p[None, :, :]
    d -= np.round(d / period) * period
    adj = np.hypot(d[..., 0], d[..., 1]) < 1.1 * spacing
    seen, sizes = np.zeros(len(p), bool), []
    for i in range(len(p)):
        if seen[i]:
            continue
        stack, n = [i], 0
        seen[i] = True
        while stack:
            j = stack.pop()
            n += 1
            for k in np.where(adj[j] & ~seen)[0]:
                seen[k] = True
                stack.append(k)
        sizes.append(n)
    return sorted(sizes)


def fig1f(pdf):
    """(n cells, n high-Delta cells, cluster sizes) of Fig. 1f."""
    page = pymupdf.open(pdf)[PAGE]
    rows = []
    for d in page.get_drawings():
        if d["type"] != "fs" or not d.get("fill"):
            continue
        r = d["rect"]
        c = ((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
        if c[0] > 368 and c[1] > 195 and 9 < r.width < 11:
            rows.append((*c, min(d["fill"])))
    a = np.array(rows)
    xy, high = a[:, :2], a[:, 2] > 0.99
    assert len(a) == N * N, len(a)
    dx = np.median(np.diff(np.unique(np.round(xy[:, 0], 1))))  # column spacing, 1.5 r
    h = dx * 2 / np.sqrt(3)  # centre spacing of flat-top hexagons, sqrt(3) r
    return len(a), int(high.sum()), clusters(xy, high, np.array([N * dx, N * h]), h)


def cells(d, t):
    """Agent cells at logged time t (cell_states.csv): (n cells, n high-Delta cells, cluster sizes) on the run's
    14 x 14 periodic hexagonal lattice (model.xml: Lattice class="hexagonal", Size 14, 14; periodic x and y)."""
    f = d[np.isclose(d.t, t)]
    xy = f[["cell.center.x", "cell.center.y"]].to_numpy(float)
    high = (f.D >= 0.5).to_numpy()
    return len(f), int(high.sum()), clusters(xy, high, np.array([N, N * np.sqrt(3) / 2]), 1.0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.dirname(HERE))), help="repository root")
    a = ap.parse_args()
    n, nh, s = fig1f(os.path.join(a.repo, "benchmark_papers", "05_Berkemeier2023.pdf"))
    print(f"Fig. 1f: {n} cells, {nh} high Delta ({nh / n:.3f}), {len(s)} clusters, mean size {np.mean(s):.2f}: {s}")


if __name__ == "__main__":
    main()
