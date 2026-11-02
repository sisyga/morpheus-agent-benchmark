# Supplementary Fig. 8: B-cell dynamics in the germinal center (Mu *et al.*, 2024)

Everything needed to rebuild this figure is in this folder, except the shared engine (`../engine/`) and the paper PDF in `benchmark_papers/` at the repository root.

## Build

```bash
python figures/Supplementary/Supp_Fig_08_Mu2024/build.py
```

writes `build/` here: the figure as SVG (editable text), PDF and 600 dpi PNG, its legend (`caption.md`, `caption.tex`), `technical_notes.md` (every crop, conversion and correction) and `sources.csv` (every input file with its SHA-256). `--from-scratch` also regenerates the model graph from `model.xml` with the Morpheus CLI and renders every intermediate file anew. The Python environment and tools are listed in `../README.md`.

## Contents

- `panel.py`: what the figure shows (panel d, legend, captions). The crops of panel a and the frames of panel b are set in `../engine/config.py` (`PANEL_A`, `FRAMES`, entry `08_Mu2024`).
- `data/`: the files of the shown run (GPT-6.1 Sol, setup 5 (MCP), repetition 2, score 0.83) that the figure reads, copied from the benchmark run folder `20261011_140942_08_Mu2024__morpheus_mcp__rep02__replacement03`:
    - `20261011_140942_08_Mu2024__morpheus_mcp__rep02__replacement03/attempts/attempt_001/model.xml`: scored model
    - `20261011_140942_08_Mu2024__morpheus_mcp__rep02__replacement03/attempts/attempt_001/plot_000.00.png`: panel b frame
    - `20261011_140942_08_Mu2024__morpheus_mcp__rep02__replacement03/attempts/attempt_001/plot_100.00.png`: panel b frame
    - `20261011_140942_08_Mu2024__morpheus_mcp__rep02__replacement03/attempts/attempt_001/plot_300.00.png`: panel b frame
    - `20261011_140942_08_Mu2024__morpheus_mcp__rep02__replacement03/attempts/attempt_001/plot_400.00.png`: panel b frame
    - `20261011_140942_08_Mu2024__morpheus_mcp__rep02__replacement03/attempts/attempt_001/aggregate_raw.csv`: panel d data
    - `20261011_140942_08_Mu2024__morpheus_mcp__rep02__replacement03/attempts/attempt_001/figure_data/mu_bcells_by_layer.csv`: small table that `panel.py` computes from the run's TiffPlotter stack cell.id_affinity.tif, 40 MB (not included)
    - `20261011_140942_08_Mu2024__morpheus_mcp__rep02__replacement03/attempts/attempt_001/figure_data/mu_lethal_affinity.csv`: small table that `panel.py` computes from the run's cells_raw.csv, 22 MB (not included)
    - `20261011_140942_08_Mu2024__morpheus_mcp__rep02__replacement03/attempts/attempt_001/morpheus_command.json`: run record (Morpheus wall time)
    - `20261011_140942_08_Mu2024__morpheus_mcp__rep02__replacement03/agent_workspace/attempts/attempt_021/model.xml`: agent's last test, model.xml
    - `20261011_140942_08_Mu2024__morpheus_mcp__rep02__replacement03/agent_workspace/attempts/attempt_021/aggregate_raw.csv`: agent's last test, B-cell numbers
    - `20261011_140942_08_Mu2024__morpheus_mcp__rep02__replacement03/agent_workspace/assets/resident_6x1/CXCL12.tif`: model input file read by model.xml (needed to regenerate the model graph)
    - `20261011_140942_08_Mu2024__morpheus_mcp__rep02__replacement03/agent_workspace/assets/resident_6x1/CXCL12_gradient_x.tif`: model input file read by model.xml (needed to regenerate the model graph)
    - `20261011_140942_08_Mu2024__morpheus_mcp__rep02__replacement03/agent_workspace/assets/resident_6x1/CXCL12_gradient_y.tif`: model input file read by model.xml (needed to regenerate the model graph)
    - `20261011_140942_08_Mu2024__morpheus_mcp__rep02__replacement03/agent_workspace/assets/resident_6x1/CXCL12_gradient_z.tif`: model input file read by model.xml (needed to regenerate the model graph)
    - `20261011_140942_08_Mu2024__morpheus_mcp__rep02__replacement03/agent_workspace/assets/resident_6x1/CXCL13.tif`: model input file read by model.xml (needed to regenerate the model graph)
    - `20261011_140942_08_Mu2024__morpheus_mcp__rep02__replacement03/agent_workspace/assets/resident_6x1/CXCL13_gradient_x.tif`: model input file read by model.xml (needed to regenerate the model graph)
    - `20261011_140942_08_Mu2024__morpheus_mcp__rep02__replacement03/agent_workspace/assets/resident_6x1/CXCL13_gradient_y.tif`: model input file read by model.xml (needed to regenerate the model graph)
    - `20261011_140942_08_Mu2024__morpheus_mcp__rep02__replacement03/agent_workspace/assets/resident_6x1/CXCL13_gradient_z.tif`: model input file read by model.xml (needed to regenerate the model graph)
- `paper_data/`: data read off the paper's figures (digitised, or extracted from the PDF by the scripts below): `total.csv`, `DZ.csv`, `LZ.csv`, `mean_affinity.csv`.
- `model_graph/`: the model graph of `model.xml` as Morpheus 2.4.1 writes it (`08_Mu2024.dot`, full, on the model-graph pages; `08_Mu2024_reduced.dot`, panel c).
- Paper source (repository root): `benchmark_papers/08_Mu2024.pdf`.

## Legend

**Supplementary Fig. 8 | B-cell dynamics in the germinal center (Mu *et al.*, 2024).** **a**, Positions of the resident cells, chemokine fields and simulation snapshots colored by B-cell affinity, from Mu *et al.*[mu2024] (adapted from their Fig. 2A–D). **b**, Model built by GPT-6.1 Sol with setup 5 (MCP; repetition 2, score 0.83). B cells in a single layer (*z* = 5 µm) of the 11 µm thick 3D domain, colored by affinity; the dark blue squares are the resident CRC, FDC and Tfh cells, which have a fixed affinity (key below). Because the layer holds only the B cells that cross it (243 of 635 at 400 h), the frames look less densely packed than a projection of the whole domain. The agent's model uses the paper's time scale (100 MCS = 1 h), so the frames correspond to snapshots in **a** and the curves in **d** compare directly. **c**, Model graph of the agent's model as drawn by Morpheus (reduced view). **d**, **i**, Number of B cells in total and in the dark and light zones in the agent's model (lines) and in Mu *et al.*[mu2024] (markers; digitized from their Fig. 3A). The run ended at 400 h because the benchmark asked for 40,000 MCS, the final time of their Fig. 2D. **ii**, Mean B-cell affinity in the agent's model (line) and in Mu *et al.*[mu2024] (circles; digitized from their Fig. 4A). CRC, CXCL12-expressing reticular cell; FDC, follicular dendritic cell; MCS, Monte Carlo steps; Tfh, T follicular helper cell. Material from Mu *et al.*[mu2024] is adapted under a [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) license.
