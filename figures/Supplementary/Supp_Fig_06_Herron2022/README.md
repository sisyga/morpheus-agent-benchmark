# Supplementary Fig. 6: Rosette patterns of GTPase activity during phagocytosis (Herron *et al.*, 2022)

Everything needed to rebuild this figure is in this folder, except the shared engine (`../engine/`) and the paper PDF in `benchmark_papers/` at the repository root.

## Build

```bash
python figures/Supplementary/Supp_Fig_06_Herron2022/build.py
```

writes `build/` here: the figure as SVG (editable text), PDF and 600 dpi PNG, its legend (`caption.md`, `caption.tex`), `technical_notes.md` (every crop, conversion and correction) and `sources.csv` (every input file with its SHA-256). `--from-scratch` also regenerates the model graph from `model.xml` with the Morpheus CLI and renders every intermediate file anew. The Python environment and tools are listed in `../README.md`.

## Contents

- `panel.py`: what the figure shows (panel d, legend, captions). The crops of panel a and the frames of panel b are set in `../engine/config.py` (`PANEL_A`, `FRAMES`, entry `06_Herron2022`).
- `data/`: the files of the shown run (GPT-6.1 Sol, setup 4 (Skill), repetition 1, score 1.00) that the figure reads, copied from the benchmark run folder `20261008_142120_06_Herron2022__morpheus_skill__rep01__replacement02`:
    - `20261008_142120_06_Herron2022__morpheus_skill__rep01__replacement02/attempts/attempt_001/model.xml`: scored model
    - `20261008_142120_06_Herron2022__morpheus_skill__rep01__replacement02/attempts/attempt_001/plot_00.00000.png`: panel b frame
    - `20261008_142120_06_Herron2022__morpheus_skill__rep01__replacement02/attempts/attempt_001/plot_10.00000.png`: panel b frame
    - `20261008_142120_06_Herron2022__morpheus_skill__rep01__replacement02/attempts/attempt_001/plot_20.00000.png`: panel b frame
    - `20261008_142120_06_Herron2022__morpheus_skill__rep01__replacement02/attempts/attempt_001/plot_40.00000.png`: panel b frame
    - `20261008_142120_06_Herron2022__morpheus_skill__rep01__replacement02/attempts/attempt_001/u_range.csv`: panel d data
    - `20261008_142120_06_Herron2022__morpheus_skill__rep01__replacement02/attempts/attempt_001/u_v_G_g.tif`: panel d data
- `model_graph/`: the model graph of `model.xml` as Morpheus 2.4.1 writes it (`06_Herron2022.dot`, full, on the model-graph pages; `06_Herron2022_reduced.dot`, panel c).
- Paper source (repository root): `benchmark_papers/06_Herron2022.pdf`.

## Legend

**Supplementary Fig. 6 | Rosette patterns of GTPase activity during phagocytosis (Herron *et al.*, 2022).** **a**, The wave-pinning GAP model of Herron *et al.*[herron2022]: reaction scheme, spatial profiles of the modulated parameters with the resulting patterns of active GTPase (their Fig. 2A, C, D), and the rosette obtained with their fitted parameters, the benchmark target (their Fig. 4F). **b**, Model built by GPT-6.1 Sol with setup 4 (Skill; repetition 1, score 1.00). Active GTPase *u* on the circular domain, starting from a random state (color bar below). **c**, Model graph of the agent's model as drawn by Morpheus (reduced view). **d**, **i**, Maximum, mean and minimum of *u* over the domain. Shading marks the first 20 s, during which the rosette forms in the paper's simulations (their S4 Fig). **ii**, Mean of *u* over all nodes at the same distance from the domain center, at three times. From 20 s on, the profile peaks at 2.08 µm, just outside the edge of the IgG disk (dashed line), where the spots of the rosette sit. The model's spatially varying rates switch between their inner and outer values at this edge. GAP, GTPase-activating protein; IgG, immunoglobulin G. Material from Herron *et al.*[herron2022] is adapted under a [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) license.
