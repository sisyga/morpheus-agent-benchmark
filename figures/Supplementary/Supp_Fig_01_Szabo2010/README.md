# Supplementary Fig. 1: Collective cell motion in an endothelial monolayer (Szabó *et al.*, 2010)

Everything needed to rebuild this figure is in this folder, except the shared engine (`../engine/`) and the paper PDF in `benchmark_papers/` at the repository root.

## Build

```bash
python figures/Supplementary/Supp_Fig_01_Szabo2010/build.py
```

writes `build/` here: the figure as SVG (editable text), PDF and 600 dpi PNG, its legend (`caption.md`, `caption.tex`), `technical_notes.md` (every crop, conversion and correction) and `sources.csv` (every input file with its SHA-256). `--from-scratch` also regenerates the model graph from `model.xml` with the Morpheus CLI and renders every intermediate file anew. The Python environment and tools are listed in `../README.md`.

## Contents

- `panel.py`: what the figure shows (panel d, legend, captions). The crops of panel a and the frames of panel b are set in `../engine/config.py` (`PANEL_A`, `FRAMES`, entry `01_Szabo2010`).
- `data/`: the files of the shown run (GPT-6.1 Sol, setup 5 (MCP), repetition 3, score 1.00) that the figure reads, copied from the benchmark run folder `20261007_211902_01_Szabo2010__morpheus_mcp__rep03`:
    - `20261007_211902_01_Szabo2010__morpheus_mcp__rep03/attempts/attempt_001/model.xml`: scored model
    - `20261007_211902_01_Szabo2010__morpheus_mcp__rep03/attempts/attempt_001/plot_00000.png`: panel b frame
    - `20261007_211902_01_Szabo2010__morpheus_mcp__rep03/attempts/attempt_001/plot_00360.png`: panel b frame
    - `20261007_211902_01_Szabo2010__morpheus_mcp__rep03/attempts/attempt_001/plot_01440.png`: panel b frame
    - `20261007_211902_01_Szabo2010__morpheus_mcp__rep03/attempts/attempt_001/figure_data/szabo_rms_displacement.csv`: small table that `panel.py` computes from the run's cell_tracks.tsv.csv, 131 MB (not included)
    - `20261007_211902_01_Szabo2010__morpheus_mcp__rep03/attempts/attempt_001/figure_data/szabo_flow_field.csv`: small table that `panel.py` computes from the run's cell_tracks.tsv.csv, 131 MB (not included)
    - `20261007_211902_01_Szabo2010__morpheus_mcp__rep03/attempts/attempt_001/figure_data/szabo_rotation.csv`: small table that `panel.py` computes from the run's cell_tracks.tsv.csv, 131 MB (not included)
    - `20261007_211902_01_Szabo2010__morpheus_mcp__rep03/attempts/attempt_001/population.tsv.csv`: panel d data
- `paper_data/`: data read off the paper's figures (digitised, or extracted from the PDF by the scripts below): `monolayer.csv`.
- `model_graph/`: the model graph of `model.xml` as Morpheus 2.4.1 writes it (`01_Szabo2010.dot`, full, on the model-graph pages; `01_Szabo2010_reduced.dot`, panel c).
- `szabo_recalibration.py`: Recalibration of the digitised Szabo et al.

## Legend

**Supplementary Fig. 1 | Collective cell motion in an endothelial monolayer (Szabó *et al.*, 2010).** **a**, Model built by GPT-6.1 Sol with setup 5 (MCP; repetition 3, score 1.00). Cells are colored by identity (the palette only separates neighbors) and by polarity direction (color scale below), with arrows along the polarity vectors. **b**, Model graph of the agent's model as drawn by Morpheus (reduced view). **c**, **i**, RMS displacement of cells against time lag in the agent's model (α = 4, the benchmark case) and in the monolayer simulation of Szabó *et al.*[szabo2010] (circles; digitized from their Fig. 7b). The paper has no displacement curve for α = 4, so the comparison uses its curve for α = 2. **ii**, Instantaneous cell speed, averaged over all cells. It includes the fluctuations of the cell centers and therefore exceeds the net speed in **i** (28 µm h⁻¹ over a 1 h lag). **iii**, Mean velocity of the neighbors of a moving cell (green arrow, moving along +x), for comparison with Fig. 10c of Szabó *et al.*[szabo2010]; arrow length and color show the neighbor speed. The upper half of the field is faster because the sheet turns into a single clockwise rotation in the closed domain: a cell moving along +x lies above the center of rotation, and its neighbors below it, nearer the center, move more slowly. α, cost of cell–cell boundaries in the cellular Potts model; RMS, root mean square.
