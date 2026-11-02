# Supplementary Fig. 7: Planarian regeneration after cutting (Scheel *et al.*, 2021)

Everything needed to rebuild this figure is in this folder, except the shared engine (`../engine/`) and the paper PDF in `benchmark_papers/` at the repository root.

## Build

```bash
python figures/Supplementary/Supp_Fig_07_Scheel2021/build.py
```

writes `build/` here: the figure as SVG (editable text), PDF and 600 dpi PNG, its legend (`caption.md`, `caption.tex`), `technical_notes.md` (every crop, conversion and correction) and `sources.csv` (every input file with its SHA-256). `--from-scratch` also regenerates the model graph from `model.xml` with the Morpheus CLI and renders every intermediate file anew. The Python environment and tools are listed in `../README.md`.

## Contents

- `panel.py`: what the figure shows (panel d, legend, captions). The crops of panel a and the frames of panel b are set in `../engine/config.py` (`PANEL_A`, `FRAMES`, entry `07_Scheel2021`).
- `data/`: the files of the shown run (GPT-6.1 Sol, setup 5 (MCP), repetition 1, score 1.00) that the figure reads, copied from the benchmark run folder `20261008_152400_07_Scheel2021__morpheus_mcp__rep01__replacement02`:
    - `20261008_152400_07_Scheel2021__morpheus_mcp__rep01__replacement02/attempts/attempt_001/model.xml`: scored model
    - `20261008_152400_07_Scheel2021__morpheus_mcp__rep01__replacement02/attempts/attempt_001/fields_raw_plot_x_paper_s_00.00000.png`: panel b frame
    - `20261008_152400_07_Scheel2021__morpheus_mcp__rep01__replacement02/attempts/attempt_001/fields_raw_plot_x_paper_s_05.00000.png`: panel b frame
    - `20261008_152400_07_Scheel2021__morpheus_mcp__rep01__replacement02/attempts/attempt_001/fields_raw_plot_x_paper_s_10.00000.png`: panel b frame
    - `20261008_152400_07_Scheel2021__morpheus_mcp__rep01__replacement02/attempts/attempt_001/fields_raw.csv`: panel d data
    - `20261008_152400_07_Scheel2021__morpheus_mcp__rep01__replacement02/attempts/attempt_001/ranges_raw.csv`: panel d data
    - `20261008_152400_07_Scheel2021__morpheus_mcp__rep01__replacement02/attempts/attempt_001/boundary_states_raw.csv`: panel d data
- `model_graph/`: the model graph of `model.xml` as Morpheus 2.4.1 writes it (`07_Scheel2021.dot`, full, on the model-graph pages; `07_Scheel2021_reduced.dot`, panel c).

## Legend

**Supplementary Fig. 7 | Planarian regeneration after cutting (Scheel *et al.*, 2021).** **a**, Model built by GPT-6.1 Sol with setup 5 (MCP; repetition 1, score 1.00). Profiles along the fragment at three times, redrawn from the run's logged data: stem-cell density *s*, head-cell density *h*, tail-cell density *d*, short-range head and tail signals *u*<sub>h</sub> and *u*<sub>d</sub> (dashed) and the Wnt-related signal *w*. Position and time are dimensionless, in the units of Scheel *et al.*[scheel2021] **b**, Model graph of the agent's model as drawn by Morpheus (reduced view). **c**, **i**, Spatial range (maximum minus minimum) of *h*, *d* and *w* against time after cutting, the quantity the benchmark asks for. The ranges of *h* and *d* equal the head density at the left end and the tail density at the right end. **ii**, Profiles at the final time near the two ends, with the *x* axis broken between −4.7 and 4.7. Lines show the interior and circles the boundary compartments at the ends (filled for *h*, *d* and *w*, open for *u*<sub>h</sub> and *u*<sub>d</sub>). Head variables are negligible at the tail end and tail variables at the head end, so they are not drawn there.
