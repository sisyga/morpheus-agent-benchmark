# Supplementary Fig. 11: Anteroposterior patterning in gastruloids (Anlaş *et al.*, 2024)

Everything needed to rebuild this figure is in this folder, except the shared engine (`../engine/`) and the paper PDF in `benchmark_papers/` at the repository root.

## Build

```bash
python figures/Supplementary/Supp_Fig_11_Anlas2024/build.py
```

writes `build/` here: the figure as SVG (editable text), PDF and 600 dpi PNG, its legend (`caption.md`, `caption.tex`), `technical_notes.md` (every crop, conversion and correction) and `sources.csv` (every input file with its SHA-256). `--from-scratch` also regenerates the model graph from `model.xml` with the Morpheus CLI and renders every intermediate file anew. The Python environment and tools are listed in `../README.md`.

## Contents

- `panel.py`: what the figure shows (panel d, legend, captions). The crops of panel a and the frames of panel b are set in `../engine/config.py` (`PANEL_A`, `FRAMES`, entry `11_Anlas2024`).
- `data/`: the files of the shown run (GPT-6.1 Sol, setup 4 (Skill), repetition 2, score 1.00) that the figure reads, copied from the benchmark run folder `20261011_183911_11_Anlas2024__morpheus_skill__rep02__replacement02`:
    - `20261011_183911_11_Anlas2024__morpheus_skill__rep02__replacement02/attempts/attempt_001/model.xml`: scored model
    - `20261011_183911_11_Anlas2024__morpheus_skill__rep02__replacement02/attempts/attempt_001/plot_00000.png`: panel b frame
    - `20261011_183911_11_Anlas2024__morpheus_skill__rep02__replacement02/attempts/attempt_001/plot_00048.png`: panel b frame
    - `20261011_183911_11_Anlas2024__morpheus_skill__rep02__replacement02/attempts/attempt_001/plot_00072.png`: panel b frame
    - `20261011_183911_11_Anlas2024__morpheus_skill__rep02__replacement02/attempts/attempt_001/cells.csv`: panel d data
    - `20261011_183911_11_Anlas2024__morpheus_skill__rep02__replacement02/attempts/attempt_001/population.csv`: panel d data
- `paper_data/`: data read off the paper's figures (digitised, or extracted from the PDF by the scripts below): `Bra_T.csv`, `Sox_2.csv`.
- `model_graph/`: the model graph of `model.xml` as Morpheus 2.4.1 writes it (`11_Anlas2024.dot`, full, on the model-graph pages; `11_Anlas2024_reduced.dot`, panel c).
- Paper source (repository root): `benchmark_papers/11_Anlas2024.pdf`.

## Legend

**Supplementary Fig. 11 | Anteroposterior patterning in gastruloids (Anlaş *et al.*, 2024).** **a**, Bra/T expression from 24 to 72 hpa, in situ stainings of Bra/T, Foxa2 and Sox2 with their profiles along the A–P axis (their Fig. 1A–E), and Bra/T profiles at 72 hpa for different initial cell numbers (their Fig. 4B), adapted from Anlaş *et al.*[anlass2024] **b**, Model built by GPT-6.1 Sol with setup 4 (Skill; repetition 2, score 1.00). Each frame shows the same cells colored by their Bra/T, Sox2 and N-cadherin levels (color bars below; dimensionless). Scale bar, 50 µm. **c**, Model graph of the agent's model as drawn by Morpheus (reduced view). **d**, **i**, Bra/T and Sox2 along the A–P axis at 72 h, each divided by its maximum, in the agent's model (lines) and in Anlaş *et al.*[anlass2024] (open markers; mean profiles at 72 hpa, digitized from their Fig. 1E). In the agent's model the A–P axis runs from the Sox2-weighted to the Bra/T-weighted center of the cells, and levels are averaged in bins along it. **ii**, Bra/T level along the A–P axis over time, as for T in Fig. 1A of Anlaş *et al.*[anlass2024] At 24 h Bra/T is nearly uniform, so the direction of the axis is arbitrary. **iii**, Number of cells. A–P, anterior–posterior; hpa, hours post-aggregation. Material from Anlaş *et al.*[anlass2024] is adapted under a [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) license.
