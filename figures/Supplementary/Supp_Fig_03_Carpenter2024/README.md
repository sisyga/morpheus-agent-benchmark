# Supplementary Fig. 3: Cell proliferation in a growing epithelial colony (Carpenter *et al.*, 2024)

Everything needed to rebuild this figure is in this folder, except the shared engine (`../engine/`) and the paper PDF in `benchmark_papers/` at the repository root.

## Build

```bash
python figures/Supplementary/Supp_Fig_03_Carpenter2024/build.py
```

writes `build/` here: the figure as SVG (editable text), PDF and 600 dpi PNG, its legend (`caption.md`, `caption.tex`), `technical_notes.md` (every crop, conversion and correction) and `sources.csv` (every input file with its SHA-256). `--from-scratch` also regenerates the model graph from `model.xml` with the Morpheus CLI and renders every intermediate file anew. The Python environment and tools are listed in `../README.md`.

## Contents

- `panel.py`: what the figure shows (panel d, legend, captions). The crops of panel a and the frames of panel b are set in `../engine/config.py` (`PANEL_A`, `FRAMES`, entry `03_Carpenter2024`).
- `data/`: the files of the shown run (GPT-6.1 Sol, setup 4 (Skill), repetition 1, score 1.00) that the figure reads, copied from the benchmark run folder `20261007_232808_03_Carpenter2024__morpheus_skill__rep01`:
    - `20261007_232808_03_Carpenter2024__morpheus_skill__rep01/attempts/attempt_001/model.xml`: scored model
    - `20261007_232808_03_Carpenter2024__morpheus_skill__rep01/attempts/attempt_001/plot_0000.0000.png`: panel b frame
    - `20261007_232808_03_Carpenter2024__morpheus_skill__rep01/attempts/attempt_001/plot_4050.0000.png`: panel b frame
    - `20261007_232808_03_Carpenter2024__morpheus_skill__rep01/attempts/attempt_001/plot_7875.0000.png`: panel b frame
    - `20261007_232808_03_Carpenter2024__morpheus_skill__rep01/attempts/attempt_001/quantification.csv`: panel d data
- `paper_data/`: data read off the paper's figures (digitised, or extracted from the PDF by the scripts below): `fig2A_apoptosis_on_vector.csv`.
- `model_graph/`: the model graph of `model.xml` as Morpheus 2.4.1 writes it (`03_Carpenter2024.dot`, full, on the model-graph pages; `03_Carpenter2024_reduced.dot`, panel c).
- `carpenter_fig2a_extract.py`: Apoptosis-on cell-number curve of Carpenter et al.
- Paper source (repository root): `benchmark_papers/preprints/03_Carpenter2023_bioRxiv.pdf`.

## Legend

**Supplementary Fig. 3 | Cell proliferation in a growing epithelial colony (Carpenter *et al.*, 2024).** **a**, Cell number with and without apoptosis, cell area against distance from the colony center with apoptosis, and colonies colored by growth rate without (top) and with apoptosis (bottom), from the preprint of Carpenter *et al.*[carpenter2024] (adapted from its Fig. 2A, D–F). **b**, Model built by GPT-6.1 Sol with setup 4 (Skill; repetition 1, score 1.00). Colony growth from a single cell, with apoptosis. Cells are colored by the change of their area in the last Monte Carlo step relative to the reference growth rate G₀ (color bar); apoptotic cells are yellow. **c**, Model graph of the agent's model as drawn by Morpheus (reduced view). **d**, **i**, Cell number in the agent's model (line) and in Carpenter *et al.*[carpenter2024] (circles; data from Fig. 2A of the published article), both with apoptosis. **ii**, Number of apoptotic cells, which shrink before they are removed. **iii**, Mean cell area in units of A<sub>s</sub>, as in Fig. 2D of Carpenter *et al.*[carpenter2024] It starts at 0.49 A<sub>s</sub> with the single initial cell and oscillates with the first, nearly synchronous divisions; the oscillations damp as the divisions lose synchrony. A<sub>s</sub>, mean G1 size threshold; G₀, reference growth rate of the agent's model; τ₀, mean duration of the S/G2/M phase, the unit of time. Material from the preprint of Carpenter *et al.*[carpenter2024] is adapted under a [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) license.
