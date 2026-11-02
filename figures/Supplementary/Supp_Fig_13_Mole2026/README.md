# Supplementary Fig. 13: Human embryo implantation (Molè *et al.*, 2026)

Everything needed to rebuild this figure is in this folder, except the shared engine (`../engine/`) and the paper PDF in `benchmark_papers/` at the repository root.

## Build

```bash
python figures/Supplementary/Supp_Fig_13_Mole2026/build.py
```

writes `build/` here: the figure as SVG (editable text), PDF and 600 dpi PNG, its legend (`caption.md`, `caption.tex`), `technical_notes.md` (every crop, conversion and correction) and `sources.csv` (every input file with its SHA-256). `--from-scratch` also regenerates the model graph from `model.xml` with the Morpheus CLI and renders every intermediate file anew. The Python environment and tools are listed in `../README.md`.

## Contents

- `panel.py`: what the figure shows (panel d, legend, captions). The crops of panel a and the frames of panel b are set in `../engine/config.py` (`PANEL_A`, `FRAMES`, entry `13_Mole2026`).
- `data/`: the files of the shown run (GPT-6.1 Sol, setup 4 (Skill), repetition 3, score 0.88) that the figure reads, copied from the benchmark run folder `20261013_173228_13_Mole2026__morpheus_skill__rep03__replacement02`:
    - `20261013_173228_13_Mole2026__morpheus_skill__rep03__replacement02/attempts/attempt_001/model.xml`: scored model
    - `20261013_173228_13_Mole2026__morpheus_skill__rep03__replacement02/attempts/attempt_001/plot_00000.png`: panel b frame
    - `20261013_173228_13_Mole2026__morpheus_skill__rep03__replacement02/attempts/attempt_001/plot_00024.png`: panel b frame
    - `20261013_173228_13_Mole2026__morpheus_skill__rep03__replacement02/attempts/attempt_001/plot_00048.png`: panel b frame
    - `20261013_173228_13_Mole2026__morpheus_skill__rep03__replacement02/attempts/attempt_001/plot_00072.png`: panel b frame
    - `20261013_173228_13_Mole2026__morpheus_skill__rep03__replacement02/attempts/attempt_001/cells.csv`: panel d data
- `model_graph/`: the model graph of `model.xml` as Morpheus 2.4.1 writes it (`13_Mole2026.dot`, full, on the model-graph pages; `13_Mole2026_reduced.dot`, panel c).
- Paper source (repository root): `benchmark_papers/13_Mole2026.pdf`.

## Legend

**Supplementary Fig. 13 | Human embryo implantation (Molè *et al.*, 2026).** **a**, Stages of human embryo implantation in vitro (adapted from Fig. 3A of Molè *et al.*[molè2026]). **b**, Model built by GPT-6.1 Sol with setup 4 (Skill; repetition 3, score 0.88). Embryo and endometrium colored by cell type (key below). **c**, Model graph of the agent's model as drawn by Morpheus (reduced view, wrapped into 2 rows). **d**, **i**, Depth of the deepest trophoblast cell below the uterine surface (gray line); negative values lie above it. Dotted lines mark the apposition, adhesion and implantation stages of Fig. 3A of Molè *et al.*[molè2026] The trophoblast crosses the surface at 8.17 d.p.f. **ii**, Number of embryo cells of each type, colored as in **b**. The first invasive trophoblast cells, which arise from trophectoderm cells by a contact-induced change of type, appear at 7.58 d.p.f. d.p.f., days post-fertilization. Material from Molè *et al.*[molè2026] is adapted under a [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) license.
