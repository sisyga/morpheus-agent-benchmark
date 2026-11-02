# Supplementary Fig. 15: Multi-zonal liver organoids (Al Reza *et al.*, 2025)

Everything needed to rebuild this figure is in this folder, except the shared engine (`../engine/`) and the paper PDF in `benchmark_papers/` at the repository root.

## Build

```bash
python figures/Supplementary/Supp_Fig_15_AlReza2025/build.py
```

writes `build/` here: the figure as SVG (editable text), PDF and 600 dpi PNG, its legend (`caption.md`, `caption.tex`), `technical_notes.md` (every crop, conversion and correction) and `sources.csv` (every input file with its SHA-256). `--from-scratch` also regenerates the model graph from `model.xml` with the Morpheus CLI and renders every intermediate file anew. The Python environment and tools are listed in `../README.md`.

## Contents

- `panel.py`: what the figure shows (panel d, legend, captions). The crops of panel a and the frames of panel b are set in `../engine/config.py` (`PANEL_A`, `FRAMES`, entry `15_Reza2025`).
- `data/`: the files of the shown run (GPT-6.1 Sol, setup 5 (MCP), repetition 3, score 1.00) that the figure reads, copied from the benchmark run folder `20261013_185544_15_Reza2025__morpheus_mcp__rep03__replacement02`:
    - `20261013_185544_15_Reza2025__morpheus_mcp__rep03__replacement02/attempts/attempt_001/model.xml`: scored model
    - `20261013_185544_15_Reza2025__morpheus_mcp__rep03__replacement02/attempts/attempt_001/plot_00000.png`: panel b frame
    - `20261013_185544_15_Reza2025__morpheus_mcp__rep03__replacement02/attempts/attempt_001/plot_04320.png`: panel b frame
    - `20261013_185544_15_Reza2025__morpheus_mcp__rep03__replacement02/attempts/attempt_001/plot_08640.png`: panel b frame
    - `20261013_185544_15_Reza2025__morpheus_mcp__rep03__replacement02/attempts/attempt_001/counts.csv`: panel d data
    - `20261013_185544_15_Reza2025__morpheus_mcp__rep03__replacement02/attempts/attempt_001/cells.csv`: panel d data
- `model_graph/`: the model graph of `model.xml` as Morpheus 2.4.1 writes it (`15_Reza2025.dot`, full, on the model-graph pages; `15_Reza2025_reduced.dot`, panel c).
- Paper source (repository root): `benchmark_papers/preprints/15_Reza2024_bioRxiv.pdf`.

## Legend

**Supplementary Fig. 15 | Multi-zonal liver organoids (Al Reza *et al.*, 2025).** **a**, Generation of zone 1 and zone 3 liver organoids and their fusion (Fig. 1a, f), and the GST and GS activities and glutamine production measured for each organoid type (Fig. 4g–i), from the preprint of Al Reza *et al.*[alreza2025] **b**, Model built by GPT-6.1 Sol with setup 5 (MCP; repetition 3, score 1.00). Two organoids of Z1-HLO and Z3-HLO cells around lumens, which fuse over time (key below). **c**, Model graph of the agent's model as drawn by Morpheus (reduced view). **d**, **i**, Number of Z1-HLO and Z3-HLO cells. **ii**–**iv**, Mean over the cells of each zone of the model's GST capacity (**ii**), GS capacity (**iii**) and glutamine production (**iv**). These are dimensionless proxies, so only their ordering between Z1 and Z3 compares with the measurements of Al Reza *et al.*[alreza2025] in **a**. GS, glutamine synthetase; GST, glutathione S-transferase; HLO, human liver organoid; Z1 and Z3, zones 1 and 3. The panels in **a** are excerpted (cropped and rearranged, otherwise unaltered) from the preprint of Al Reza *et al.*[alreza2025], available under a [CC BY-NC-ND 4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/) license.
