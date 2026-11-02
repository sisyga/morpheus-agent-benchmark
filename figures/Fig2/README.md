# Fig. 2: benchmark scope and results

## Build

```bash
uv run --locked python figures/Fig2/build.py
```

runs the panel scripts into `build/panels/`, assembles `build/Fig2.svg` and renders `Fig2.pdf` and a 600 dpi
`Fig2.png` with headless Chrome. On our system the figure built from this folder matched the published one pixel for pixel.

| Panel | Script | Data |
| --- | --- | --- |
| a, table of the 15 studies | `make_table.py` (also writes `table1_gpt61sol.xlsx`) | `data/runs_by_run.csv`; bold = the run shown in the supplement (`../Supplementary/engine/config.py`, `RUNS`) |
| b, automated vs manual score | `make_heatmap.py` | `data/manual_vs_automated.csv` |
| c i–iii, score and cost per setup | `make_row_c.py` (plotting and statistics of `compare_benchmarks.py`) | `data/runs_by_run.csv` |
| d i, e i | from `assets/fig2_layout.svg` | Atwell et al. (2015) Fig. 3 (CC BY 3.0), Molè et al. (2026) graphical abstract (CC BY 4.0) |
| d ii, e iii | from `assets/fig2_layout.svg` | snapshots of the shown Atwell and Molè runs (as in Supplementary Figs. 4 and 13) |
| d iii, germ-cell numbers | `make_plots_de.py` | `data/atwell_cell_counts.csv`, Atwell et al. Table S2 |
| e ii, mechanism graph | `mechanism_graph.py` (every edge with the `model.xml` element behind it) | the shown Molè model, `../Supplementary/Supp_Fig_13_Mole2026/data/` |
| e iv, heights | `make_plots_de.py` | `data/mole_height_rerun/` |

`assemble.py` places the panels into `assets/fig2_layout.svg`, the hand-drawn Inkscape layout of rows d and e (reduced to the elements the figure shows),
which it leaves untouched.

## Statistics in the text

Every test, ratio and confidence interval in the text is recomputed by

```bash
uv run --locked python compare_benchmarks.py --runs-csv figures/Fig2/data/runs_by_run.csv --out-dir <folder>
```

(`statistical_tests.md`, `benchmark_model_comparison_overall.csv` and a `_stats.md` per figure); run on the two
benchmark folders instead, it gives identical tables.

## Data

- `runs_by_run.csv`: one row per run of the two final benchmarks (225 GPT-6.1 Sol runs, 375 GPT-6 Luna runs):
  scores, active time, revisions, tokens and API-equivalent cost (`runs_by_run_columns.md`). Rows are in the order
  `compare_benchmarks.py` reads the benchmark folders; read floats with `float_precision="round_trip"` to get the
  published numbers exactly.
- `manual_vs_automated.csv`: manual and automated score of the 225 runs of the earlier GPT-5.5 benchmark (also the
  agreement statistics in Methods).
- `atwell_cell_counts.csv`: `cell_counts.csv` of the shown Atwell run, unchanged.
- `mole_height_rerun/`: the model and Logger output behind e iv (`README.md` there).
