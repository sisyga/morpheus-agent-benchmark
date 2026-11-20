# Supplementary Fig. 5: Notch–Delta patterning with long-range signaling (Berkemeier & Page, 2023)

Everything needed to rebuild this figure is in this folder, except the shared engine (`../engine/`) and the paper PDF in `benchmark_papers/` at the repository root.

## Build

```bash
python figures/Supplementary/Supp_Fig_05_Berkemeier2023/build.py
```

writes `build/` here: the figure as SVG (editable text), PDF and 600 dpi PNG, its legend (`caption.md`, `caption.tex`), `technical_notes.md` (every crop, conversion and correction) and `sources.csv` (every input file with its SHA-256). `--from-scratch` also regenerates the model graph from `model.xml` with the Morpheus CLI and renders every intermediate file anew. The Python environment and tools are listed in `../README.md`.

## Contents

- `panel.py`: what the figure shows (panel d, legend, captions). The crops of panel a and the frames of panel b are set in `../engine/config.py` (`PANEL_A`, `FRAMES`, entry `05_Berkemeier2023`).
- `data/`: the files of the shown run (GPT-6.1 Sol, setup 4 (Skill), repetition 1, score 1.00) that the figure reads, copied from the benchmark run folder `20261008_142119_05_Berkemeier2023__morpheus_skill__rep01__replacement02`:
    - `20261008_142119_05_Berkemeier2023__morpheus_skill__rep01__replacement02/attempts/attempt_001/model.xml`: scored model
    - `20261008_142119_05_Berkemeier2023__morpheus_skill__rep01__replacement02/attempts/attempt_001/plot_000.0000.png`: panel b frame
    - `20261008_142119_05_Berkemeier2023__morpheus_skill__rep01__replacement02/attempts/attempt_001/plot_003.0000.png`: panel b frame
    - `20261008_142119_05_Berkemeier2023__morpheus_skill__rep01__replacement02/attempts/attempt_001/plot_006.0000.png`: panel b frame
    - `20261008_142119_05_Berkemeier2023__morpheus_skill__rep01__replacement02/attempts/attempt_001/plot_100.0000.png`: panel b frame
    - `20261008_142119_05_Berkemeier2023__morpheus_skill__rep01__replacement02/attempts/attempt_001/cell_states.csv`: panel d data
    - `20261008_142119_05_Berkemeier2023__morpheus_skill__rep01__replacement02/attempts/attempt_001/delta_cluster_timeseries.csv`: panel d data
- `data/seed_ensemble.csv`, `data/seed01_t20_cell_states.csv`: panel d data. Reruns of the scored `model.xml` with RandomSeed 1 to 10 (seed 1 = the scored run), stopped at t = 20 and logged every 20/99 τN; `data/seed_ensemble_setup_runs.py` makes these copies (only the seed, stop time and output intervals change; the External command and the Gnuplotter are removed). Each run was analysed with the agent's `scripts/analyze_run.py`, which writes the high-Delta fraction and mean cluster size per time point (`seed_ensemble.csv`: one row per seed and time). Panel d i shows seed 1 (`seed01_t20_cell_states.csv`).
- `model_graph/`: the model graph of `model.xml` as Morpheus 2.4.1 writes it (`05_Berkemeier2023.dot`, full, on the model-graph pages; `05_Berkemeier2023_reduced.dot`, panel c).
- `berkemeier_fig1f_extract.py`: High-Delta cells and clusters of Berkemeier & Page (2023) Fig.
- Paper source (repository root): `benchmark_papers/05_Berkemeier2023.pdf`.

## Legend

**Supplementary Fig. 5 | Notch–Delta patterning with long-range signaling (Berkemeier & Page, 2023).** **a**, Final pattern of Delta activity on a 14 × 14 periodic hexagonal lattice at ε = 1, where cells signal only through long-range protrusions, from Berkemeier & Page[berkemeier2023] (adapted from their Fig. 1f, with the color bar of their Fig. 1c–f). **b**, Model built by GPT-6.1 Sol with setup 4 (Skill; repetition 1, score 1.00). Delta activity *D* of each cell at dimensionless times *t*, in units of the Notch decay time τ<sub>N</sub> (color bar below). The pattern is final by *t* = 10 τ<sub>N</sub>. **c**, Model graph of the agent's model as drawn by Morpheus (reduced view). **d**, Time courses up to *t* = 20 τ<sub>N</sub> (the pattern does not change after *t* = 8 τ<sub>N</sub>), from reruns with output every 0.2 τ<sub>N</sub>; seed 1 is identical to the scored run. **i**, Delta activity of each cell against time (one line per cell); the cells settle at two levels. The paper has no time course at ε = 1, so **i** shows the agent's model only. **ii**, Fraction of cells with high Delta (*D* ≥ 0.5). **iii**, Mean size of clusters of adjacent high-Delta cells. In **ii** and **iii**, solid lines and shading show the mean ± s.d. of 10 simulations of the agent's model with different random initial conditions (final values 0.192 ± 0.005 and 2.38 ± 0.22 cells), and dashed lines the pattern of Fig. 1f of Berkemeier & Page[berkemeier2023], counted from the PDF (39 of 196 cells high, in 16 clusters). All 10 simulations meet both numeric scoring criteria (high-Delta fraction 0.1–0.3, mean cluster size 1.5–3.5 cells). Material from Berkemeier & Page[berkemeier2023] is adapted under a [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) license.