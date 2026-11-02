# Supplementary Fig. 2: Clearance of senescent mesothelial cells by ovarian cancer cells (Thapa *et al.*, 2024)

Everything needed to rebuild this figure is in this folder, except the shared engine (`../engine/`) and the paper PDF in `benchmark_papers/` at the repository root.

## Build

```bash
python figures/Supplementary/Supp_Fig_02_Thapa2024/build.py
```

writes `build/` here: the figure as SVG (editable text), PDF and 600 dpi PNG, its legend (`caption.md`, `caption.tex`), `technical_notes.md` (every crop, conversion and correction) and `sources.csv` (every input file with its SHA-256). `--from-scratch` also regenerates the model graph from `model.xml` with the Morpheus CLI and renders every intermediate file anew. The Python environment and tools are listed in `../README.md`.

## Contents

- `panel.py`: what the figure shows (panel d, legend, captions). The crops of panel a and the frames of panel b are set in `../engine/config.py` (`PANEL_A`, `FRAMES`, entry `02_Thapa2024`).
- `data/`: the files of the shown run (GPT-6.1 Sol, setup 5 (MCP), repetition 3, score 1.00) that the figure reads, copied from the benchmark run folder `20261007_223642_02_Thapa2024__morpheus_mcp__rep03`:
    - `20261007_223642_02_Thapa2024__morpheus_mcp__rep03/attempts/attempt_001/model.xml`: scored model
    - `20261007_223642_02_Thapa2024__morpheus_mcp__rep03/attempts/attempt_001/plot_000.00000.png`: panel b frame
    - `20261007_223642_02_Thapa2024__morpheus_mcp__rep03/attempts/attempt_001/plot_024.00000.png`: panel b frame
    - `20261007_223642_02_Thapa2024__morpheus_mcp__rep03/attempts/attempt_001/plot_072.00000.png`: panel b frame
    - `20261007_223642_02_Thapa2024__morpheus_mcp__rep03/attempts/attempt_001/plot_120.00000.png`: panel b frame
    - `20261007_223642_02_Thapa2024__morpheus_mcp__rep03/attempts/attempt_001/cell_counts.csv`: panel d data
    - `20261007_223642_02_Thapa2024__morpheus_mcp__rep03/agent_workspace/ensemble_summary.json`: agent's Model 4 repeats
    - `20261007_223642_02_Thapa2024__morpheus_mcp__rep03/agent_workspace/attempts/attempt_010/cell_counts.csv`: agent's Model 4 repeats
    - `20261007_223642_02_Thapa2024__morpheus_mcp__rep03/agent_workspace/attempts/attempt_012/cell_counts.csv`: agent's Model 4 repeats
    - `20261007_223642_02_Thapa2024__morpheus_mcp__rep03/agent_workspace/attempts/attempt_016/cell_counts.csv`: agent's Model 4 repeats
    - `20261007_223642_02_Thapa2024__morpheus_mcp__rep03/agent_workspace/attempts/attempt_017/cell_counts.csv`: agent's Model 4 repeats
    - `20261007_223642_02_Thapa2024__morpheus_mcp__rep03/agent_workspace/attempts/attempt_018/cell_counts.csv`: agent's Model 4 repeats
- `paper_data/`: data read off the paper's figures (digitised, or extracted from the PDF by the scripts below): `fig4Biv_cell_counts.csv`.
- `model_graph/`: the model graph of `model.xml` as Morpheus 2.4.1 writes it (`02_Thapa2024.dot`, full, on the model-graph pages; `02_Thapa2024_reduced.dot`, panel c).
- `thapa_fig4d_extract.py`: Model 4 points of Thapa et al.
- Paper source (repository root): `benchmark_papers/02_Thapa2024.pdf`.

## Legend

**Supplementary Fig. 2 | Clearance of senescent mesothelial cells by ovarian cancer cells (Thapa *et al.*, 2024).** **a**, Model 4 of Thapa *et al.*[thapa2023]: the initial layout (their Supplementary Fig. S12), snapshots of one simulation (Fig. 4B iv), the senescent area in experiments and in the four models (Fig. 4D) and the cell-type key (Fig. 4A). **b**, Model built by GPT-6.1 Sol with setup 5 (MCP; repetition 3, score 1.00). Snapshots at the same times, colored by cell type (key below). **c**, Model graph of the agent's model as drawn by Morpheus (reduced view). **d**, **i**, Senescent area relative to 0 h in the agent's model (line) and in Model 4 of Thapa *et al.*[thapa2023] (diamonds, mean ± s.d. of five simulations; data from their Fig. 4D). **ii**, Cell numbers relative to 0 h in the agent's model (lines) and counted in the snapshots of one representative simulation in **a** (diamonds), colored as in **b**. The two agree closely because the agent downloaded the authors' CompuCell3D code and translated it into Morpheus, keeping its initial layout of 8 cancer, 16 non-senescent and 25 senescent cells; it did not run CompuCell3D. Single runs still vary: in 5 runs of the agent's model that differed only in the random seed, the final number of cancer cells ranged from 104 to 144 (122 in the run shown, 123 in the paper's snapshot). Material from Thapa *et al.*[thapa2023] is adapted under a [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) license.
