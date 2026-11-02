"""Fig. 2b: automated vs manual score, 0.1 x 0.1 bins, exported at print size (Arial 5-7 pt, editable SVG text).

Data: manual scores of the GPT-5.5 benchmark (20260524_002842_benchmark, 225 runs) against the automated scorer
used for the final benchmarks (scorer v8, GPT-6 Luna high, criteria v7), from
manual_score_comparison_luna6_criteria_v7_manual_20261005/biological_score_manual_comparison.csv.
Usage: uv run --locked python figures/Fig2/make_heatmap.py [comparison.csv] [out_stem]
"""
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import DATA, PANELS  # noqa: E402

HERE = PANELS
CSV = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA / "manual_vs_automated.csv"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "fig2b_manual_vs_automated_bin01"
SIZE_MM = (47.0, 38.5)
BIN = 0.1
MM = 1 / 25.4

plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Liberation Sans", "DejaVu Sans"],
    "font.size": 7, "axes.labelsize": 7, "xtick.labelsize": 6, "ytick.labelsize": 6, "legend.fontsize": 6,
    "axes.linewidth": 0.5, "xtick.major.width": 0.5, "ytick.major.width": 0.5, "xtick.major.size": 2.0,
    "ytick.major.size": 2.0, "xtick.major.pad": 1.5, "ytick.major.pad": 1.5, "axes.labelpad": 2.0,
    "svg.fonttype": "none", "pdf.fonttype": 42,
})

rows = pd.read_csv(CSV)
rows = rows[rows["join_status"] == "matched"]
manual = pd.to_numeric(rows["manual_score"], errors="coerce")
agent = pd.to_numeric(rows["agent_biological_score"], errors="coerce")
ok = manual.notna() & agent.notna()
manual, agent = manual[ok].to_numpy(), agent[ok].to_numpy()
edges = np.round(np.linspace(0, 1, round(1 / BIN) + 1), 12)
counts, _, _ = np.histogram2d(manual, agent, bins=[edges, edges])
counts = counts.T

fig = plt.figure(figsize=(SIZE_MM[0] * MM, SIZE_MM[1] * MM))
# fixed axes in mm so the square plot and colour bar land at the same place on every export
W, H = SIZE_MM
ax = fig.add_axes([8.0 / W, 7.0 / H, 30.0 / W, 30.0 / H])
cax = fig.add_axes([39.5 / W, 7.0 / H, 1.6 / W, 30.0 / H])
cmap = plt.get_cmap("viridis_r").with_extremes(under="white")
mesh = ax.pcolormesh(edges, edges, counts, cmap=cmap, vmin=1, vmax=counts.max(), shading="flat", rasterized=True)
ax.plot([0, 1], [0, 1], color="#E66100", linewidth=0.8, linestyle="--", zorder=3, label="Perfect\nagreement")
for iy, ix in np.argwhere(counts > 0):
    r, g, b, _ = mesh.cmap(mesh.norm(counts[iy, ix]))
    ax.text((edges[ix] + edges[ix + 1]) / 2, (edges[iy] + edges[iy + 1]) / 2, str(int(counts[iy, ix])),
            ha="center", va="center", fontsize=5, zorder=4,
            color="black" if 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.5 else "white")
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
ax.set_xlabel("Manual score")
ax.set_ylabel("Automated score")
ax.legend(loc="lower right", frameon=False, handlelength=1.6, borderaxespad=0.3)
cb = fig.colorbar(mesh, cax=cax, extend="min", extendfrac=0.04)
cb.outline.set_linewidth(0.5)
cb.ax.tick_params(width=0.5, length=1.5, pad=1.0, labelsize=6)
cb.set_label("Runs per bin", labelpad=2)
for ext in ("svg", "pdf", "png"):
    fig.savefig(OUT.with_suffix(f".{ext}"), dpi=600)
r = np.corrcoef(manual, agent)[0, 1]
print(f"{len(manual)} runs, max bin {int(counts.max())}, exact {int(np.sum(np.abs(manual - agent) < 1e-6))}, r = {r:.3f}")
