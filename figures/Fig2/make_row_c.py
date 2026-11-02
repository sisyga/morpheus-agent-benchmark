"""Fig. 2c i-iii as one 180 mm row with aligned x-axes (score, cost, cost vs score), GPT-6.1 Sol vs GPT-6 Luna.

Reuses the plotting and statistics code of compare_benchmarks.py on the per-run table of both benchmarks
(figures/Fig2/data/runs_by_run.csv, the records compare_benchmarks.py loads from the full benchmark folders):
  uv run --locked python figures/Fig2/make_row_c.py
Tools are named as in Fig. 1 without numbers; one model legend (lower right of i); costs are API-equivalent
(list prices applied to the recorded tokens; the runs themselves used a subscription).
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import DATA, PANELS, REPO  # noqa: E402

sys.path.insert(0, str(REPO))
import analyze_benchmark as analysis
import compare_benchmarks as cb

OUT = PANELS / "fig2c_row"
W, H = 180.0, 40.0
BOTTOM, TOP = 8.6, 39.0                     # axes bottom/top in mm, shared by all three panels
AXES = [(8.5, 50.0), (71.0, 48.5), (130.5, 48.5)]   # (left, width) in mm
COST_LABEL = "API-equivalent cost (US$)"
cb.MODE_LABELS.clear()
cb.MODE_LABELS.update({"python_web": "Web", "morpheus_cli": "CLI", "morpheus_cli_docs": "Docs",
                       "morpheus_skill": "Skill", "morpheus_mcp": "MCP"})

records = pd.read_csv(DATA / "runs_by_run.csv", float_precision="round_trip")
included, _ = cb.split_never_started(records)
paper_records, summary = cb.aggregate_comparison_records(included, "bootstrap")
overall_papers, _ = cb.aggregate_overall_records(paper_records, "bootstrap")
tests = cb.compute_statistical_tests(paper_records, overall_papers, "bootstrap")

analysis.configure_matplotlib()
plt.rcParams.update(cb.PANEL_STYLE)
fig = plt.figure(figsize=(W / cb.MM_PER_INCH, H / cb.MM_PER_INCH))
axes = [fig.add_axes([l / W, BOTTOM / H, w / W, (TOP - BOTTOM) / H]) for l, w in AXES]

# draw each panel with compare_benchmarks' own figure functions, handing them our axes
queue = iter(axes)
cb.panel_figure = lambda *a, **k: (fig, next(queue))
cb.save_panel = lambda *a, **k: None
close = plt.close
plt.close = lambda *a, **k: None
cb.make_biological_score_figure(paper_records, summary, OUT.parent, [], "bootstrap", tests)
cb.make_cost_figure(paper_records, summary, OUT.parent, [], "bootstrap", tests)
cb.make_pareto_figure(summary, OUT.parent, [])
plt.close = close

score_ax, cost_ax, pareto_ax = axes
benchmarks = cb.benchmark_series(summary)
for ax in (score_ax, cost_ax):
    ax.get_legend().remove()
# lower right: the box sits between the lowest GPT-6 Luna Skill paper (score 0.05) and the GPT-6 Luna MCP whisker
# (0.33), so it hides no data
y0, y1 = score_ax.get_ylim()
cb.benchmark_legend(score_ax, benchmarks, loc="lower right", bbox_to_anchor=(1.0, (0.08 - y0) / (y1 - y0)),
                    borderaxespad=0.0, borderpad=0.2, handlelength=1.0, handletextpad=0.3, labelspacing=0.1)
# framed like the Fig. 1 cell-type legend: rounded box, 0.5 pt light gray line, translucent white fill
legend = score_ax.get_legend()
legend.set_frame_on(True)
frame = legend.get_frame()
frame.set_boxstyle("round", pad=0.0, rounding_size=0.38)   # 0.8 mm corners at 6 pt
frame.set_edgecolor("#cccccc")
frame.set_linewidth(0.5)
frame.set_facecolor((1, 1, 1, 0.85))
cost_ax.set_ylabel(COST_LABEL)
pareto_ax.set_xlabel(COST_LABEL)
for ax in axes:
    ax.grid(False)
for ax in (score_ax, cost_ax):
    ax.set_xlabel("Tool setup")
for fmt in ("svg", "pdf", "png"):
    fig.savefig(OUT.with_suffix(f".{fmt}"), dpi=600)
print("wrote", OUT)
