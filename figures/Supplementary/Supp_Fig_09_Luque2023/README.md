# Supplementary Fig. 9: Liver regeneration and recurrence of hepatocellular carcinoma (Luque *et al.*, 2023)

Everything needed to rebuild this figure is in this folder, except the shared engine (`../engine/`) and the paper PDF in `benchmark_papers/` at the repository root.

## Build

```bash
python figures/Supplementary/Supp_Fig_09_Luque2023/build.py
```

writes `build/` here: the figure as SVG (editable text), PDF and 600 dpi PNG, its legend (`caption.md`, `caption.tex`), `technical_notes.md` (every crop, conversion and correction) and `sources.csv` (every input file with its SHA-256). `--from-scratch` also regenerates the model graph from `model.xml` with the Morpheus CLI and renders every intermediate file anew. The Python environment and tools are listed in `../README.md`.

## Contents

- `panel.py`: what the figure shows (panel d, legend, captions). The crops of panel a and the frames of panel b are set in `../engine/config.py` (`PANEL_A`, `FRAMES`, entry `09_Luque2023`).
- `data/`: the files of the shown run (GPT-6.1 Sol, setup 5 (MCP), repetition 3, score 0.83) that the figure reads, copied from the benchmark run folder `20261014_135600_09_Luque2023__morpheus_mcp__rep03__replacement04`:
    - `20261014_135600_09_Luque2023__morpheus_mcp__rep03__replacement04/attempts/attempt_001/model.xml`: scored model
    - `20261014_135600_09_Luque2023__morpheus_mcp__rep03__replacement04/attempts/attempt_001/plot_00.000000.png`: panel b frame
    - `20261014_135600_09_Luque2023__morpheus_mcp__rep03__replacement04/attempts/attempt_001/plot_30.000000.png`: panel b frame
    - `20261014_135600_09_Luque2023__morpheus_mcp__rep03__replacement04/attempts/attempt_001/plot_60.000000.png`: panel b frame
    - `20261014_135600_09_Luque2023__morpheus_mcp__rep03__replacement04/attempts/attempt_001/cell_counts.csv`: panel d data
    - `20261014_135600_09_Luque2023__morpheus_mcp__rep03__replacement04/attempts/attempt_001/mechanism_diagnostics.csv`: panel d data
    - `20261014_135600_09_Luque2023__morpheus_mcp__rep03__replacement04/agent_workspace/assets/hypoxia_candidate_oxygen_initial.tif`: model input file read by model.xml (needed to regenerate the model graph)
- `paper_data/`: data read off the paper's figures (digitised, or extracted from the PDF by the scripts below): `fig10b_hepatocytes.csv`, `fig10b_cancer.csv`.
- `model_graph/`: the model graph of `model.xml` as Morpheus 2.4.1 writes it (`09_Luque2023.dot`, full, on the model-graph pages; `09_Luque2023_reduced.dot`, panel c).
- `luque_fig10b_extract.py`: Mean curves of Luque et al.
- Paper source (repository root): `benchmark_papers/09_Luque2023.pdf`.

## Legend

**Supplementary Fig. 9 | Liver regeneration and recurrence of hepatocellular carcinoma (Luque *et al.*, 2023).** **a**, The 3D liver of Luque *et al.*[luque2023] after partial hepatectomy, with a growing tumor (blue), and the fold increase of hepatocytes and cancer cells (mean of 40 simulations), adapted from their Fig. 10a, b. **b**, Model built by GPT-6.1 Sol with setup 5 (MCP; repetition 3, score 0.83). Hepatocytes and HCC cells in the agent's 2D model (key below). **c**, Model graph of the agent's model as drawn by Morpheus (reduced view). **d**, **i**, Fold increase of hepatocytes and HCC cells, that is, cell numbers divided by the initial number of hepatocytes, in the agent's model (solid lines) and in Luque *et al.*[luque2023] (dashed lines in the colors of their Fig. 10b; data from that panel). The agent's model is 2D and the paper's is 3D, so the numbers are not expected to match. The HCC cells stop increasing on day 44, when they fill the lattice. **ii**, The two well-mixed signals of the agent's model: a growth factor that follows the loss of liver mass, and a homeostatic signal X that rises with liver volume. Hepatocytes divide only while X is below the threshold (dashed line), and HCC cells only once X has reached it, on day 16.5. HCC, hepatocellular carcinoma. Material from Luque *et al.*[luque2023] is adapted under a [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) license.
