# Paper-comparison supplementary figures

Script-built supplementary figures of the Morpheus.AI benchmark paper: one figure per benchmark paper
(180 x 185 mm) comparing the agent's reimplementation with the original publication, plus a model-graph
supplementary figure.

Panels of each paper figure:

- **a** original publication figure, cropped from `benchmark_papers/<paper>.pdf` (page and bounding box in
  `config.py`, `PANEL_A`);
- **b** output frames of the agent's scored attempt, starting at the initial state (`FRAMES`); for Atwell,
  3D renders of the run's lattice checkpoints made by `atwell_3d.py`;
- **c** the Morpheus model graph of the scored `model.xml` (vector; wrapped into rows when wide);
- **d** quantification, drawn by `panels/pNN_<paper>.py`: agent output vs digitised paper data on the same
  axes where a like-for-like comparison exists, agent-only otherwise.

## Usage

```bash
uv venv ~/.venvs/morpheus_supp_figs --python 3.12
uv pip install --python ~/.venvs/morpheus_supp_figs -r scripts/supp_figs/requirements.txt
~/.venvs/morpheus_supp_figs/bin/python scripts/supp_figs/build_all.py --runs <benchmark dir> --out <new folder>
```

`--runs` is the benchmark directory `20261007_202940_benchmark`; `--only 02_Thapa2024 ...` builds single
papers. The output folder must be new (or one made by this script); nothing else is overwritten.
Graphviz `dot` must be on `PATH`. Intermediate files (graph renders, Atwell 3D renders and VTK files) go to
`<out>/_intermediate`.

Outputs: `NN_<Paper><year>.svg/.pdf/.png` (text stays text in the SVG), `Supp_model_graphs_pNN.*` and
`Supp_model_graphs.pdf` (landscape pages for graphs whose labels print below 5 pt in panel c),
`model_graphs/<paper>.svg` (every full graph), `sources.csv` (every input file with its sha256, for comparing
reruns) and `captions.md` (legend text, conversions and corrections of digitised data).

## Inputs

| input | where |
|---|---|
| shown runs, modes, repetitions, scores | `config.py`, `RUNS` |
| paper crops (panel a) | `config.py`, `PANEL_A`; PDFs in `benchmark_papers/` |
| frames (panel b) | `config.py`, `FRAMES`, `ATWELL_FRAMES`, `FRAME_CROP` |
| model graphs (panel c) | `model_graphs/<paper>.dot` and `<paper>_reduced.dot` |
| digitised paper data (panel d) | `paper_data/` (WebPlotDigitizer x,y CSVs; Berkhout: output of the paper's CompuCell3D model; Berkemeier: vector paths from the PDF) |
| corrections of digitised data | `paper_data.py`, `CORRECTIONS` |
| Atwell et al. Table S2 | `config.py`, `ATWELL_TABLE_S2` |

The model graphs were generated from each scored `model.xml` with Morpheus 2.4.1, which writes an empty graph
unless `<ModelGraph include-tags="#untagged"/>` is set (`make_model_graphs.py --runs <benchmark dir>`
regenerates them; Morpheus writes the lines in a varying order, so the committed files are used for the
figures). Graphs wider than 3.2:1 use the reduced graph (`reduced="true"`) in panel c.

The Szabo et al. Fig. 7b monolayer curve was digitised with a linear calibration on log-log axes;
`szabo_recalibration.py <fig_7b.png>` fits the log-space mapping that `paper_data.py` applies.

Berkemeier & Page Fig. 4a is vector graphics: panel d takes all 36 cell curves from the stroke paths on page 6
of `benchmark_papers/05_Berkemeier2023.pdf`, calibrated with the panel's axis ticks
(`berkemeier_fig4a_extract.py`, run on every build). `berkemeier_fig4a_extract.py` on its own writes the
cached copy `paper_data/5_Berkemier/fig4a_vector_paths.csv`; the older digitised `delta_activity.csv` is unused.
