"""Fig. 2a table: per-paper results of GPT-6.1 Sol in the configuration shown in the supplementary figures.

Writes table1_gpt61sol.xlsx (sheet "Table 1": one row per paper as printed; sheet "Runs": every run behind it)
and fig2a_table.svg (180 mm page coordinates, editable text). Nature style: Arial, horizontal rules only,
no shading; the triplets are repetitions 1-3, the bold value is the run shown in the supplementary figures.
Usage: uv run --locked python figures/Fig2/make_table.py   (writes to $FIGURE_OUT/panels, see paths.py)
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import DATA, PANELS, arial, config  # noqa: E402

HERE = PANELS
RUNS = DATA / "runs_by_run.csv"
TOOLS = {"morpheus_mcp": "MCP", "morpheus_skill": "Skill", "morpheus_cli": "CLI", "morpheus_cli_docs": "Docs",
         "python_web": "Web"}
PAPERS = [  # number, source paper, biological domain, model type in the study (None: no model in the literature)
    (1, "Szabó et al. (2010)", "Collective cell motion", "CPM"),
    (2, "Thapa et al. (2024)", "Ovarian cancer", "CPM"),
    (3, "Carpenter et al. (2024)", "Monolayer growth", "CPM"),
    (4, "Atwell et al. (2015)", "Germ cell proliferation", "ABM"),
    (5, "Berkemeier et al. (2023)", "Pattern formation", "ABM"),
    (6, "Herron et al. (2022)", "Pattern formation", "PDE"),
    (7, "Scheel et al. (2021)", "Tissue regeneration", "PDE"),
    (8, "Mu et al. (2024)", "Morphogenesis", "Multiscale"),
    (9, "Luque et al. (2023)", "Liver cancer", "Multiscale"),
    (10, "Berkhout et al. (2025)", "Morphogenesis", "Multiscale"),
    (11, "Anlaş et al. (2024)", "Axis formation", None),
    (12, "Malkmus et al. (2025)", "Digit patterning", None),
    (13, "Molè et al. (2026)", "Embryogenesis", None),
    (14, "Otsuki et al. (2025)", "Limb regeneration", None),
    (15, "Al Reza et al. (2025)", "Liver organoid", None),
]
COLUMNS = [  # header, key, alignment
    ("No.", "no", "middle"), ("Study", "paper", "start"), ("Biological domain", "domain", "start"),
    ("Published\nmodel", "model", "start"), ("Setup", "tool", "start"), ("Duration (min)", "duration", "middle"),
    ("Cost (US$)", "price", "middle"), ("Score", "score", "middle"),
]
FMT = {"duration": "{:.0f}", "price": "{:.2f}", "score": "{:.2f}"}

runs = pd.read_csv(RUNS, float_precision="round_trip")
runs = runs[runs["benchmark_label"] == "GPT-6.1 Sol"].copy()
runs["no"] = runs["paper"].str[:2].astype(int)
# the run shown in the supplementary figures (bold): figures/Supplementary/engine/config.py
best = pd.DataFrame([dict(paper=k, run=r, mode=m, rep=rep) for k, (r, m, rep, _) in config.RUNS.items()])
best["no"] = best["paper"].str[:2].astype(int)
rows, run_rows = [], []
for no, paper, domain, model in PAPERS:
    b = best.loc[best["no"] == no].iloc[0]
    g = runs[(runs["no"] == no) & (runs["mode"] == b["mode"])].sort_values("repetition")
    assert list(g["repetition"]) == [1, 2, 3], (paper, list(g["repetition"]))
    row = {"no": no, "paper": paper, "domain": domain, "model": model or "–", "tool": TOOLS[b["mode"]],
           "best_rep": int(b["rep"]), "best_run": b["run"]}
    for key, col in (("duration", "subject_active_time_min"), ("price", "total_cost_usd"),
                     ("score", "biological_score_itt")):
        row[key] = [float(v) for v in g[col]]
    rows.append(row)
    run_rows.append(g.assign(paper_name=paper, tool=TOOLS[b["mode"]], shown_in_supp=g["repetition"] == b["rep"]))


def triplet(r, key):
    return "(" + ", ".join(FMT[key].format(v) for v in r[key]) + ")"


xlsx = pd.DataFrame([{
    "No.": r["no"], "Study": r["paper"], "Biological domain": r["domain"], "Published model": r["model"],
    "Setup": r["tool"],
    "Duration (min)": triplet(r, "duration"), "Cost (US$)": triplet(r, "price"), "Score": triplet(r, "score"),
    "Supp. figure repetition (bold)": r["best_rep"],
    **{f"{h} rep {i + 1}": round(r[k][i], 0 if k == "duration" else 2)
       for h, k in (("Duration (min)", "duration"), ("Cost (US$)", "price"), ("Score", "score")) for i in range(3)},
    "Supp. figure run": r["best_run"],
} for r in rows])
with pd.ExcelWriter(HERE / "table1_gpt61sol.xlsx") as writer:
    xlsx.to_excel(writer, sheet_name="Table 1", index=False)
    pd.concat(run_rows)[["no", "paper_name", "tool", "repetition", "shown_in_supp", "subject_active_time_min",
                         "total_cost_usd", "biological_score_itt", "biological_score", "stop_reason",
                         "benchmark_id"]].to_excel(writer, sheet_name="Runs", index=False)

# ---- SVG table -------------------------------------------------------------------------------------------
PT = 25.4 / 72
SIZE = 6 * PT                      # 6 pt body and header text
ROW = 3.0                          # row pitch (mm)
LINE = 2.3                         # extra height of a two-line column head (mm)
X0, X1, Y0 = 4.4, 131.2, 2.2       # table left/right edge and top rule (page mm)
PAD = 1.0
font = arial()
bold = arial(bold=True)


def width(s, f=font):
    return f.getlength(s) / 1000 * SIZE


def cell_text(r, key):
    return triplet(r, key) if key in FMT else str(r[key])


natural = [max(*(width(line, bold) for line in h.split("\n")), *(width(cell_text(r, k)) for r in rows)) + 2 * PAD for h, k, _ in COLUMNS]
extra = (X1 - X0 - sum(natural)) / len(COLUMNS)
assert extra >= 0, f"table too wide by {-extra * len(COLUMNS):.1f} mm"
widths = [w + extra for w in natural]
edges = [X0]
for w in widths:
    edges.append(edges[-1] + w)

out = [f'<g id="fig2a_table" font-family="Arial, Helvetica, sans-serif" font-size="{SIZE:.4f}" fill="#000">']


def text(x, y, s, anchor="start", weight=None, style=None):
    s = s.replace("&", "&amp;")
    a = f' font-weight="{weight}"' if weight else ""
    a += f' font-style="{style}"' if style else ""
    out.append(f'<text x="{x:.3f}" y="{y:.3f}" text-anchor="{anchor}"{a}>{s}</text>')


def rule(y, x0=X0, x1=X1, w=0.25):
    out.append(f'<line x1="{x0:.3f}" y1="{y:.3f}" x2="{x1:.3f}" y2="{y:.3f}" stroke="#000" '
               f'stroke-width="{w * PT:.4f}"/>')


def cell_x(i, anchor):
    return edges[i] + PAD if anchor == "start" else (edges[i] + edges[i + 1]) / 2


base = 0.70 * ROW                  # baseline offset inside a row
y = Y0
rule(y, w=0.75)
# spanner heads with short rules underneath
for label, a, b in [("Benchmark", 0, 4), ("GPT-6.1 Sol, runs 1–3", 4, 8)]:
    text((edges[a] + edges[b]) / 2, y + base, label, "middle", "bold")
    rule(y + ROW - 0.2, edges[a] + PAD, edges[b] - PAD)
y += ROW
# column heads, bottom-aligned; "Published model" takes two lines
for i, (h, _, anchor) in enumerate(COLUMNS):
    lines = h.split("\n")
    for j, line in enumerate(lines):
        text(cell_x(i, anchor), y + base + LINE * (j + 2 - len(lines)), line, anchor, "bold")
y += ROW + LINE
rule(y, w=0.5)
y += 0.3
for r in rows:
    if r["no"] == 11:           # papers without a published model
        rule(y - 0.15)
        text(cell_x(3, "start"), y + base, "No published model", weight="bold")   # matches the column head
        y += ROW
        rule(y - 0.15)
        y += 0.15
    for i, (_, key, anchor) in enumerate(COLUMNS):
        if key in FMT:
            parts = [FMT[key].format(v) for v in r[key]]
            body = ", ".join(f'<tspan font-weight="bold">{p}</tspan>' if j + 1 == r["best_rep"] else p
                             for j, p in enumerate(parts))
            out.append(f'<text x="{cell_x(i, anchor):.3f}" y="{y + base:.3f}" text-anchor="middle">({body})</text>')
        else:
            text(cell_x(i, anchor), y + base, cell_text(r, key), anchor)
    y += ROW
y += 0.1
rule(y, w=0.75)
out.append("</g>")
(HERE / "fig2a_table.svg").write_text(
    f'<svg xmlns="http://www.w3.org/2000/svg" width="180mm" height="{y + 2:.1f}mm" viewBox="0 0 180 {y + 2:.1f}">'
    + "\n".join(out) + "</svg>", encoding="utf-8")
print(f"table {X0}-{X1} mm, y {Y0}-{y:.1f} mm, spare width per column {extra:.2f} mm")
print(xlsx[["No.", "Setup", "Duration (min)", "Cost (US$)", "Score", "Supp. figure repetition (bold)"]].to_string(index=False))
