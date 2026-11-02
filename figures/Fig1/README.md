# Fig. 1: autonomous construction of virtual tissue models

## Build

```bash
uv run --locked python figures/Fig1/build.py
```

writes `build/Fig1.svg` (editable text) and renders `Fig1.pdf` and a 600 dpi `Fig1.png` with headless Chrome
(`../render_fig.py`; Chrome is looked up in the usual install folders or `$CHROME`).

## Contents

- `build.py`: the whole figure (180 x 119 mm), drawn as SVG at print size; the schematic panels, the tool table (d),
  the attempt folder (e) and the scorer's verdicts (f) for the shown Atwell run are written out in the script.
- `icons/`: our own vector icons (`doc`, `csv`, `png`, `log`, `dot`, `globe`, `cli`, `person`, `agent`,
  `microscope`, `.svg`); the official Python and Model Context Protocol logos (`python.png`, `mcp.png`), unmodified;
  our custom icons with the Morpheus logo (`xml.png`) and the skill folder (`skill.png`).
- `images/`:
    - `atwell2015_fig1d.png`, `atwell2015_fig3.png`: crops of Atwell et al. (2015) Fig. 1D and Fig. 3
      (Development 142:3902, CC BY 3.0, as credited in the legend);
    - `agent_model_18.5hph.png` … `agent_model_39.4hph.png`, `agent_model_32.4hph_crop.png`: 3D renders of the shown
      Atwell run (GPT-6.1 Sol, setup 4) from the same Morpheus checkpoints as Supplementary Fig. 4,
      whose build renders them anew with `../Supplementary/Supp_Fig_04_Atwell2015/atwell_3d.py` in slightly different
      colours.
- `fig1d_paths.json`: the outlines of Atwell et al. Fig. 1D, read from page 2 of `benchmark_papers/04_Atwell2025.pdf`.
