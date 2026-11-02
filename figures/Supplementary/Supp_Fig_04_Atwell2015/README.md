# Supplementary Fig. 4: Germ-line development in *C. elegans* (Atwell *et al.*, 2015)

Everything needed to rebuild this figure is in this folder, except the shared engine (`../engine/`) and the paper PDF in `benchmark_papers/` at the repository root.

The benchmark names this study `04_Atwell2025` (a historical file name kept by the scoring criteria and the runs); the paper is Atwell et al. (2015).

## Build

```bash
python figures/Supplementary/Supp_Fig_04_Atwell2015/build.py
```

writes `build/` here: the figure as SVG (editable text), PDF and 600 dpi PNG, its legend (`caption.md`, `caption.tex`), `technical_notes.md` (every crop, conversion and correction) and `sources.csv` (every input file with its SHA-256). `--from-scratch` also regenerates the model graph from `model.xml` with the Morpheus CLI and renders every intermediate file anew. The Python environment and tools are listed in `../README.md`.

## Contents

- `panel.py`: what the figure shows (panel d, legend, captions). The crops of panel a and the frames of panel b are set in `../engine/config.py` (`PANEL_A`, `FRAMES`, entry `04_Atwell2025`).
- `data/`: the files of the shown run (GPT-6.1 Sol, setup 4 (Skill), repetition 2, score 1.00) that the figure reads, copied from the benchmark run folder `20261008_222700_04_Atwell2025__morpheus_skill__rep02__replacement02`:
    - `20261008_222700_04_Atwell2025__morpheus_skill__rep02__replacement02/attempts/attempt_001/model.xml`: panel b input (3D render), scored model
    - `20261008_222700_04_Atwell2025__morpheus_skill__rep02__replacement02/attempts/attempt_001/cell_states.csv`: panel b input (3D render)
    - `20261008_222700_04_Atwell2025__morpheus_skill__rep02__replacement02/attempts/attempt_001/cell_counts.csv`: panel b input (3D render), panel d data
    - `20261008_222700_04_Atwell2025__morpheus_skill__rep02__replacement02/attempts/attempt_001/checkpoint_25.46970.xml.gz`: panel b input (3D render) (Morpheus checkpoint without its field data; the 3D renders read only the cell nodes)
    - `20261008_222700_04_Atwell2025__morpheus_skill__rep02__replacement02/attempts/attempt_001/checkpoint_32.43939.xml.gz`: panel b input (3D render) (Morpheus checkpoint without its field data; the 3D renders read only the cell nodes)
    - `20261008_222700_04_Atwell2025__morpheus_skill__rep02__replacement02/attempts/attempt_001/checkpoint_39.40909.xml.gz`: panel b input (3D render) (Morpheus checkpoint without its field data; the 3D renders read only the cell nodes)
    - `20261008_222700_04_Atwell2025__morpheus_skill__rep02__replacement02/attempts/attempt_001/checkpoint_46.37879.xml.gz`: panel b input (3D render) (Morpheus checkpoint without its field data; the 3D renders read only the cell nodes)
    - `20261008_222700_04_Atwell2025__morpheus_skill__rep02__replacement02/attempts/attempt_001/checkpoint_53.34848.xml.gz`: panel b input (3D render) (Morpheus checkpoint without its field data; the 3D renders read only the cell nodes)
- `paper_data/`: data read off the paper's figures (digitised, or extracted from the PDF by the scripts below): `tableS2_counts.csv`.
- `model_graph/`: the model graph of `model.xml` as Morpheus 2.4.1 writes it (`04_Atwell2025.dot`, full, on the model-graph pages; `04_Atwell2025_reduced.dot`, panel c).
- `atwell_3d.py`: renders the run's Morpheus checkpoints in 3D (panel b).
- `atwell_tables2_extract.py`: reads Atwell et al. (2015) Table S2 from the text layer of the PDF (panel d).
- Paper source (repository root): `benchmark_papers/04_Atwell2025.pdf`.

## Legend

**Supplementary Fig. 4 | Germ-line development in *C. elegans* (Atwell *et al.*, 2015).** **a**, Simulation snapshots from Atwell *et al.*[atwell2015] (adapted from their Fig. 3). **b**, Model built by GPT-6.1 Sol with setup 4 (Skill; repetition 2, score 1.00). The model at comparable stages, rendered in 3D from the raw lattice states of the run, with germ cells colored by class (key below). The model represents the distal tip cell as a moving point; it is drawn here as a sphere. **c**, Model graph of the agent's model as drawn by Morpheus (reduced view, wrapped into 2 rows). **d**, Number of germ cells per class in the agent's model (lines, colored as in **b**) and in the simulation of Atwell *et al.*[atwell2015] (crosses; data from their Table S2, which lists the output of the authors' model): proliferative and meiotic S-phase cells (**i**), meiotic prophase cells (**ii**), spermatogenic cells and sperm (**iii**) and oogenic cells (**iv**). The run stopped at 53.3 hph (dotted line), when it reached the benchmark's limit of 1 h of Morpheus run time, so the later time points of Table S2 have no counterpart. hph, hours post-hatching. Material from Atwell *et al.*[atwell2015] is adapted under a [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) license.
