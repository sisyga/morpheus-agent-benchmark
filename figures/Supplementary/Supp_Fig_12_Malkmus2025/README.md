# Supplementary Fig. 12: Digit–interdigit patterning in the mouse limb bud (Malkmus *et al.*, 2025)

Everything needed to rebuild this figure is in this folder, except the shared engine (`../engine/`) and the paper PDF in `benchmark_papers/` at the repository root.

## Build

```bash
python figures/Supplementary/Supp_Fig_12_Malkmus2025/build.py
```

writes `build/` here: the figure as SVG (editable text), PDF and 600 dpi PNG, its legend (`caption.md`, `caption.tex`), `technical_notes.md` (every crop, conversion and correction) and `sources.csv` (every input file with its SHA-256). `--from-scratch` also regenerates the model graph from `model.xml` with the Morpheus CLI and renders every intermediate file anew. The Python environment and tools are listed in `../README.md`.

## Contents

- `panel.py`: what the figure shows (panel d, legend, captions). The crops of panel a and the frames of panel b are set in `../engine/config.py` (`PANEL_A`, `FRAMES`, entry `12_Malkmus2025`).
- `data/`: the files of the shown run (GPT-6.1 Sol, setup 4 (Skill), repetition 1, score 0.80) that the figure reads, copied from the benchmark run folder `20261008_203824_12_Malkmus2025__morpheus_skill__rep01__replacement02`:
    - `20261008_203824_12_Malkmus2025__morpheus_skill__rep01__replacement02/attempts/attempt_001/model.xml`: scored model
    - `20261008_203824_12_Malkmus2025__morpheus_skill__rep01__replacement02/attempts/attempt_001/plot_00000.png`: panel b frame
    - `20261008_203824_12_Malkmus2025__morpheus_skill__rep01__replacement02/attempts/attempt_001/plot_00018.png`: panel b frame
    - `20261008_203824_12_Malkmus2025__morpheus_skill__rep01__replacement02/attempts/attempt_001/plot_00036.png`: panel b frame
    - `20261008_203824_12_Malkmus2025__morpheus_skill__rep01__replacement02/attempts/attempt_001/fields_raw.csv`: panel d data
- `model_graph/`: the model graph of `model.xml` as Morpheus 2.4.1 writes it (`12_Malkmus2025.dot`, full, on the model-graph pages; `12_Malkmus2025_reduced.dot`, panel c).
- `malkmus_frames.py`: Panel b of the Malkmus et al.
- Paper source (repository root): `benchmark_papers/12_Malkmus2025.pdf`.

## Legend

**Supplementary Fig. 12 | Digit–interdigit patterning in the mouse limb bud (Malkmus *et al.*, 2025).** **a**, *Sox9* with *Sulf1* (top) and *Sfrp2* with *Sulf1* (bottom) in wild-type forelimb buds from 12 to 36 h after E10.5 (adapted from Fig. 5A, C of Malkmus *et al.*[malkmus2025]). **b**, Model built by GPT-6.1 Sol with setup 4 (Skill; repetition 1, score 0.80). Activities of the six species on the circular domain, one column per species, starting from the uniform steady state with a small random perturbation. Activities are normalized so that the steady state is 1; each color ramp runs from black at 0 to the species color at 2 (key below). **c**, Model graph of the agent's model as drawn by Morpheus (reduced view). **d**, **i**, Activities at the final time along a line through the domain center. Dashed lines mark species that follow another in phase (SULF1 follows Sox9, β-catenin follows WNT2). **ii**, Spatial standard deviation of each species over time (log scale), colored as in **i**. The initial perturbation first decays, then grows exponentially and levels off. **iii**, Sox9 activity along the line in **i** over time (kymograph); the stripes form and then stay in place. E10.5, embryonic day 10.5. Material from Malkmus *et al.*[malkmus2025] is adapted under a [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) license.
