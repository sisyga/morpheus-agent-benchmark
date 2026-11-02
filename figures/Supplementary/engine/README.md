# Paper-comparison supplementary figures

Script-built supplementary figures of the benchmark paper: one figure per benchmark paper
(180 x 170 mm, never scaled) comparing the agent's reimplementation with the original publication, plus a model-graph
supplementary figure.

Style as Fig. 1 and Fig. 2 of the paper and the Nature Methods figure guide (`style.py`): Arial; 8 pt bold panel
letters and sub-panel numerals, 7 pt axis labels, 6 pt tick labels, legends and annotations; black text only;
no panel headings (the captions carry the paper figure numbers, model, mode, repetition and score).

Panels of each paper figure:

- **a** original publication figure, cropped from `benchmark_papers/<paper>.pdf` (page and bounding box in
  `config.py`, `PANEL_A`);
- **b** output frames of the agent's scored attempt, starting at the initial state (`FRAMES`); for Atwell,
  3D renders of the run's lattice checkpoints made by `atwell_3d.py`;
- **c** the reduced Morpheus model graph (`ModelGraph reduced="true"`) of the scored `model.xml`, as large as the
  panel-c slot allows (vector, live text; wrapped into rows when wide); the full graph is on the model-graph pages;
- **d** quantification, drawn by `panel.py` of the figure folder: agent output vs digitised paper data on the same
  axes where a like-for-like comparison exists, agent-only otherwise.

## Usage

```bash
uv venv ~/.venvs/morpheus_supp_figs --python 3.12
uv pip install --python ~/.venvs/morpheus_supp_figs -r figures/Supplementary/engine/requirements.txt
~/.venvs/morpheus_supp_figs/bin/python figures/Supplementary/build_supplement.py [--out <new folder>] [--from-scratch]
```

Every figure folder (`../Supp_Fig_NN_<Paper>/build.py`) and `../Supp_Table_1/build.py`, `../Supp_Note_1/build.py`
build their part alone. `build_all.py` is the engine behind them: `--only 02_Thapa2024 ...` builds single papers;
the output folder must be new (or one made by this script); nothing else is overwritten.

### Inputs: the figure folders

Without `--runs`, each figure reads the files of its shown run from `data/` in its own folder (only the files the
figure reads; see `../README.md`), and the build is identical to one from the full benchmark run. Where a panel draws
only a few numbers from a large output (Szabo's track log, Mu's TIFF stack and cell log, Otsuki's field log), the
panel module computes them through `Ctx.summary(name, compute)`: with the full run the table is computed and saved to
`<out>/<paper>/figure_data/<name>.csv`; in the figure folder only that table exists and is read back.

### Full reproduction from the benchmark run

```bash
~/.venvs/morpheus_supp_figs/bin/python figures/Supplementary/engine/build_all.py --runs <benchmark dir> --out <new folder>     --from-scratch [--compare-to <previous build>]
```

Inputs, and nothing else:

1. the scored outputs of the shown run of every paper, `<benchmark dir>/<run>/attempts/attempt_001/` (run per paper in
   `config.py`, `RUNS`): `model.xml`, the run's logger CSVs, Gnuplotter frames, Atwell's lattice checkpoints
   (`*.xml.gz`), Herron's TIFF, `morpheus_command.json`; for Luque and Mu also the images their `model.xml`
   reads (TIFFReader; Luque's initial oxygen field and Mu's eight CXCL12/CXCL13 fields and gradients in
   `<run>/agent_workspace/assets/`, the model inputs of the original runs), needed only to regenerate the model
   graphs; for Mu also the agent's own last test of the submitted model, `<run>/agent_workspace/attempts/
   attempt_021/` (`model.xml`, checked to be identical to the scored one, and `aggregate_raw.csv`, its final B-cell
   number quoted in the caption);
2. paper sources in this repository: `benchmark_papers/*.pdf` (see `benchmark_papers/README.md`; Carpenter and Al Reza as bioRxiv
   preprints in `benchmark_papers/preprints/`), digitised curves and the Berkhout CompuCell3D time course in the figure folders' `paper_data/`
   (`compucell3d_rerun_timecourse.csv`, the output of co-author L.B.'s CompuCell3D 4.3.0 rerun of the authors'
   model);
3. this folder's code and `config.py`;
4. for Berkhout's panel b (frames every 10 h, as in the paper's Fig. 1), a re-run of the scored `model.xml` with
   only the Gnuplotter time-step changed from 3000 to 600 MCS (Morpheus 2.4.1, 1 thread, RandomSeed 42), in
   `Supp_Fig_10_Berkhout2025/data/rerun_gnuplot_10h/` (`config.py`, `BERKHOUT_RERUN_LOCAL`) with the `model.xml`
   it ran. The build stops unless that model.xml equals the scored one apart from the time-step and the re-run's
   frames at the run's own frame times are byte-identical to the run's (`Supp_Fig_10_Berkhout2025/panel.py`, `b_frames`);
   `BERKHOUT_RERUN = None` shows the run's own five frames (every 12.5 h) instead.

Derived inputs are rebuilt from (1) during the build: the model graphs are regenerated from each run's `model.xml`
with the Morpheus CLI (`--from-scratch`; Morpheus writes the lines of a graph in a varying order, so a regenerated
graph is checked against the committed `model_graph/*.dot` of the figure folders (lines as a set, `morph://` links ignored and edges
to a cluster compared by cluster, since Morpheus may also drop a repeated node definition, renumber a link or draw a
cluster edge to another member node), and the committed file keeps the layout
fixed; a graph that differs would be used as regenerated and reported); Atwell's 3D
renders are made from the run's checkpoints by `atwell_3d.py`; crops and redrawn frames are made in
memory. `--from-scratch` requires a new, empty intermediate folder, so no cached file is used. Every input is listed
in each figure's `sources.csv` with its category (benchmark run output; paper source; derived, built here; derived,
committed model graph), its path relative to the benchmark root, the repository or the intermediate folder, and its
SHA-256. Apart from these files, no file from the agents' workspaces and no hand-made file is read.

Tools used for the published figures: Python 3.12.12 with the packages pinned in `requirements.txt` (numpy 2.5.4,
pandas 3.1.0, matplotlib 3.11.2, pymupdf 2.0, pillow 13.0.0, scipy 1.18.1, pyvista 0.49.1, vtk 9.7.1), Graphviz
16.1.0 (`dot` on `PATH`), Morpheus 2.4.1 (CLI, found on `PATH` or in the standard install folders), Arial (Windows
system font), and for `Supplementary_Figures.pdf` a TeX distribution with revtex4-2 (TeX Live 2025).
Graphviz `dot` must be on `PATH`. Intermediate files (graph renders, Atwell 3D renders and VTK files) go to
`<out>/_intermediate`.

Outputs, one folder per paper, `NN_<Paper><year>/`: the figure `.svg/.pdf/.png` (text stays text in the SVG),
`<paper>_model_graph.svg` (full graph), the legend (`caption.md`, `caption.tex`), `technical_notes.md`, the scored
`model.xml` and `sources.csv` (every input file with its sha256 and the build commit, for comparing reruns). Top
level: `captions.md` (the publication legends), `technical_notes.md` (every input, crop, conversion and correction
of digitized data), `Supplementary_Figures.pdf` (every figure on its own page followed by its legend; see Legends
below), `best_models.csv` and `Supp_Fig_best_model_xmls.zip`,
`Supp_model_graphs/` (the full graph of every paper on a landscape page, vector, to be zoomed), `README.md` (build
commit) and `style_check.md`: `check_style.py` lists every text below 5 pt or above 8 pt, bold text other than
panel letters and numerals, non-black text, square brackets, pages other than 180 x 170 mm and legends that
cover data (line segments, markers or points inside the legend box plus 1 pt, measured at build time by
`figure.legend_overlaps`), plus the text it cannot restyle (Graphviz labels, text in raster images) per paper.
It runs at the end of every build and never stops it; with `--compare-to <previous build>` it also lists, per SVG, the text strings that disappeared or
appeared (a regression check; `check_style.py <out> --compare-to <prev> --diff-only` prints it without writing).
`python figures/Supplementary/engine/check_style.py <out>` reruns
the text checks on their own. Panel legends are placed by `panels/common.legend`: the preferred position if it
covers no data (2 pt margin), else the first free inside position, else a slightly extended y range, else one
row above the axes. Graph labels are set in Arial (`graphs.GRAPH_FONT`).

Optional hooks of a panel module `panel.py` of the figure folder (besides `draw`, `LEGEND` and `CAPTION`, whose `{name}`
fields are filled from `ctx.fmt`): `B_LEGEND` (colour patches under the frames), `B_KEY_H` + `draw_b_key(fig, frame
positions, y)` (own key below the frames), `b_frames(ctx)` (rows of frame images instead of `config.FRAMES`, e.g.
Malkmus' species columns and Otsuki's 3 x 3 grid), `a_images(ctx)` (rows of (image, label) for panel a instead of the `PANEL_A` crops, e.g. Thapa's crops with time labels), `draw_b(ctx, fig, frame positions, y)` (drawing on and around
the placed frames, e.g. Otsuki's row labels and colour bars; with `B_DRAW_IMAGES = False` the frames only size the
slots, as for Scheel's vector-drawn profiles), `B_SOURCE` and `B_CAPTION` (caption text of the frame panel),
`B_EXEMPT` (raster-text note for `style_check.md`; `[]` for vector-drawn frames), `D_HEIGHT`, `GRAPH_MAX_H`,
`AB_LAYOUT`, `A_SHARE`, `AB_GAP` (mm between a and b side by side, default 4).
Legends: every panel module defines `LEGEND`, the publication legend in the style of the manuscript's
main-figure legends (`"title"`, one entry per printed panel letter, optional `"abbrev"` and `"license"`), in a small
markup (`**bold**`, `*italic*`, `<sub>`, `<sup>`, Unicode symbols) with `{name}` fields from `ctx.fmt` and `{graph}`
(the standard model-graph sentence). `legend.py` prepends the run sentence (model, setup as numbered in the
manuscript, repetition, score; `config.MODEL_NAME`, `config.SETUP`) to the frame panel and writes Markdown
(`caption.md`) and LaTeX (`caption.tex`); a symbol without a LaTeX mapping stops the build. `supp_document.py` sets
all figures with their legends in one document with the manuscript's class and preamble (revtex4-2) and compiles
it with `latexmk` or `pdflatex` if installed (`python figures/Supplementary/engine/supp_document.py <out>` re-typesets an
existing build). The detailed captions (`CAPTION`, `B_CAPTION`, `B_SOURCE`) go to `technical_notes.md`.
Citations: `LEGEND["cite"]` is the paper's key in `morpheusai_supp.bib` (the manuscript's bibliography of the
benchmark papers), cited after every "Name *et al.*" outside the title; `<cite>key</cite>` cites another key at a
given mention. Each paper is cited once, as its published version; where panel a is cropped from a bioRxiv preprint
(Carpenter, Al Reza: `benchmark_papers/preprints/`, the license of the material), the legend says "the preprint of"
and the bib entry's note gives "Preprint at <doi link> (<license link>)". "CC BY … N.N" in a legend becomes a link
to the license deed.
The PDF ends with the reference list (`naturemag.bst`, as in the manuscript); `caption.md` writes citations as
`[key]`.
Before the figures, `Supplementary_Figures.pdf` holds Supplementary Table 1 and Supplementary Note 1
(`supp_extras.py`): the scorer's target, criteria and weights for every study, quoted from
`biological_scoring_criteria.json` (version 7; with the benchmark directory, its SHA-256 must match the criteria
hash in `biological_scores/scorer-...`), and the agent prompt: the saved `subject_prompt.txt` of the shown Molè
run plus the resources block of every setup (one run per other setup), copied into `<out>/Supplementary_Note_1/` (with
`sources.txt`).
Shared helpers in `figure.py`: `text_width_mm` (printed text width from the font metrics)
and `key_rows` (rows of colour patches with labels). `PANEL_A[...]["same_scale"]` prints the crops of a row at
the PDF's common scale instead of a common height. Where the reduced graph leaves more than 8 mm of its panel-c
slot unused, the layout is redone so panels a, b and d use the page.
Frames are cropped (`FRAME_CROP`, `FRAME_CROP_PX`) and outlined (`FRAME_OUTLINE`) in `config.py` and keep the
run's own colours. Per-paper helpers:
`atwell_3d.py`, `berkemeier_fig1f_extract.py`, `malkmus_frames.py`.

## Inputs

| input | where |
|---|---|
| shown runs, modes, repetitions, scores | `config.py`, `RUNS` |
| paper crops (panel a) | `config.py`, `PANEL_A`; PDFs in `benchmark_papers/` |
| frames (panel b) | `config.py`, `FRAMES`, `ATWELL_FRAMES`, `FRAME_CROP` |
| model graphs (panel c) | `model_graph/<paper>.dot` and `<paper>_reduced.dot` in each figure folder |
| digitised paper data (panel d) | `paper_data/` of each figure folder (WebPlotDigitizer x,y CSVs; Berkhout: one run of the paper's CompuCell3D model, rerun by co-author L.B., not published data; Berkemeier: Fig. 1f counted from the PDF's vector fills) |
| corrections of digitised data | `paper_data.py`, `CORRECTIONS` |
| Atwell et al. Table S2 | `Supp_Fig_04_Atwell2015/paper_data/tableS2_counts.csv`, read from the PDF's text by `atwell_tables2_extract.py` (checked on every build) |

The model graphs were generated from each scored `model.xml` with Morpheus 2.4.1, which writes an empty graph
unless `<ModelGraph include-tags="#untagged"/>` is set (`make_model_graphs.py --runs <benchmark dir>`
regenerates them; Morpheus writes the lines in a varying order, so the committed files are used for the
figures). Panel c uses the reduced graph (`reduced="true"`) wherever Graphviz can lay it out (not Berkhout with
Graphviz 16.1 on Windows: "trouble in init_rank"), sized in the panel-c slot set by `GRAPH_REDUCE_ASPECT`.

The Szabo et al. Fig. 7b monolayer curve was digitised with a linear calibration on log-log axes;
`szabo_recalibration.py <fig_7b.png>` fits the log-space mapping that `paper_data.py` applies.

Carpenter et al. Fig. 2A is vector graphics in the published PDF: `carpenter_fig2a_extract.py` takes the centres of
the orange data markers on the apoptosis-on line (page 5 of `benchmark_papers/03_Carpenter2024.pdf`, calibrated
with the axis ticks) and writes `Supp_Fig_03_Carpenter2024/paper_data/fig2A_apoptosis_on_vector.csv`, which panel d reads.

Luque et al. Fig. 10b is a raster image in the PDF (page 17, a 300 dpi JPEG): `luque_fig10b_extract.py` finds the
two mean lines by colour, calibrates them with the tick marks and fits daily values (the plotted lines are
polylines through daily values), and writes `Supp_Fig_09_Luque2023/paper_data/fig10b_hepatocytes.csv` and
`fig10b_cancer.csv`, which panel d reads (`--overlay <png>` draws them over the raster for checking).

`CORRECTIONS` in `paper_data.py` drops points, fixes a point whose intended value is obvious (`fix`, with the new
x, y) or applies the Szabo mapping; each entry is listed in the figure's technical notes (Data handling) and in
`technical_notes.md` (Mu: total at t = 0 and three points on the dark-zone line; Anlas: one Sox2 point beyond the axis).

Berkemeier & Page Fig. 1f (ε = 1, the benchmark's case) is vector graphics: panel d counts its high- and
low-Delta cells and high-Delta clusters from the fill paths on page 3 of `benchmark_papers/05_Berkemeier2023.pdf`
(`berkemeier_fig1f_extract.py`, run on every build). The paper's only Delta time courses (Fig. 4) are at
ε ≈ 0.09 and 0.78, not at ε = 1, so the figure does not use them.
