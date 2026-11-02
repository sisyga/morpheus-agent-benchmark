# Supplementary Fig. 14: Positional memory in limb regeneration (Otsuki *et al.*, 2025)

Everything needed to rebuild this figure is in this folder, except the shared engine (`../engine/`) and the paper PDF in `benchmark_papers/` at the repository root.

## Build

```bash
python figures/Supplementary/Supp_Fig_14_Otsuki2025/build.py
```

writes `build/` here: the figure as SVG (editable text), PDF and 600 dpi PNG, its legend (`caption.md`, `caption.tex`), `technical_notes.md` (every crop, conversion and correction) and `sources.csv` (every input file with its SHA-256). `--from-scratch` also regenerates the model graph from `model.xml` with the Morpheus CLI and renders every intermediate file anew. The Python environment and tools are listed in `../README.md`.

## Contents

- `panel.py`: what the figure shows (panel d, legend, captions). The crops of panel a and the frames of panel b are set in `../engine/config.py` (`PANEL_A`, `FRAMES`, entry `14_Otsuki2025`).
- `data/`: the files of the shown run (GPT-6.1 Sol, setup 5 (MCP), repetition 1, score 1.00) that the figure reads, copied from the benchmark run folder `20261008_213726_14_Otsuki2025__morpheus_mcp__rep01__replacement02`:
    - `20261008_213726_14_Otsuki2025__morpheus_mcp__rep01__replacement02/attempts/attempt_001/model.xml`: scored model
    - `20261008_213726_14_Otsuki2025__morpheus_mcp__rep01__replacement02/attempts/attempt_001/plot_00.00.png`: panel b frame
    - `20261008_213726_14_Otsuki2025__morpheus_mcp__rep01__replacement02/attempts/attempt_001/plot_15.00.png`: panel b frame
    - `20261008_213726_14_Otsuki2025__morpheus_mcp__rep01__replacement02/attempts/attempt_001/plot_39.00.png`: panel b frame
    - `20261008_213726_14_Otsuki2025__morpheus_mcp__rep01__replacement02/attempts/attempt_001/figure_data/otsuki_shh_max.csv`: small table that `panel.py` computes from the run's spatial.csv, 11 MB (not included)
    - `20261008_213726_14_Otsuki2025__morpheus_mcp__rep01__replacement02/attempts/attempt_001/cells.csv`: panel d data
    - `20261008_213726_14_Otsuki2025__morpheus_mcp__rep01__replacement02/attempts/attempt_001/population.csv`: panel d data
- `model_graph/`: the model graph of `model.xml` as Morpheus 2.4.1 writes it (`14_Otsuki2025.dot`, full, on the model-graph pages; `14_Otsuki2025_reduced.dot`, panel c).
- Paper source (repository root): `benchmark_papers/14_Otsuki2025.pdf`.

## Legend

**Supplementary Fig. 14 | Positional memory in limb regeneration (Otsuki *et al.*, 2025).** **a**, Model of how anterior–posterior positional memory is carried through regeneration (adapted from Fig. 5f of Otsuki *et al.*[otsuki2025]). Memory is stable at steady state but transiently flexible in the blastema, where Shh signaling can posteriorize anterior cells. **b**, Model built by GPT-6.1 Sol with setup 5 (MCP; repetition 1, score 1.00). Rows show Hand2 per cell relative to the posterior steady state, the diffusing Shh field and the posterior memory per cell. Anterior cells occupy the upper half and posterior cells the lower half; distal is to the right. Shh is almost zero at the first and last time shown. **c**, Model graph of the agent's model as drawn by Morpheus (reduced view). **d**, **i**, Mean Hand2 per cell in the posterior and anterior lineages and mean posterior memory of anterior-lineage cells, relative to the posterior steady state. Lineages are set by position at amputation and inherited at division. **ii**, Mean Shh and Fgf8 concentrations sensed per cell. **iii**, Number of connective-tissue cells, which grows by division from 192 to 283. A, anterior; a.u., arbitrary units; P, posterior. Material from Otsuki *et al.*[otsuki2025] is adapted under a [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) license.
