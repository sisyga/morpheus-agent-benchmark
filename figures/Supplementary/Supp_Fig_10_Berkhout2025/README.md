# Supplementary Fig. 10: Neural tube closure (Berkhout *et al.*, 2025)

Everything needed to rebuild this figure is in this folder, except the shared engine (`../engine/`) and the paper PDF in `benchmark_papers/` at the repository root.

## Build

```bash
python figures/Supplementary/Supp_Fig_10_Berkhout2025/build.py
```

writes `build/` here: the figure as SVG (editable text), PDF and 600 dpi PNG, its legend (`caption.md`, `caption.tex`), `technical_notes.md` (every crop, conversion and correction) and `sources.csv` (every input file with its SHA-256). `--from-scratch` also regenerates the model graph from `model.xml` with the Morpheus CLI and renders every intermediate file anew. The Python environment and tools are listed in `../README.md`.

## Contents

- `panel.py`: what the figure shows (panel d, legend, captions). The crops of panel a and the frames of panel b are set in `../engine/config.py` (`PANEL_A`, `FRAMES`, entry `10_Berkhout2025`).
- `data/`: the files of the shown run (GPT-6.1 Sol, setup 5 (MCP), repetition 3, score 1.00) that the figure reads, copied from the benchmark run folder `20261013_143544_10_Berkhout2025__morpheus_mcp__rep03__replacement02`:
    - `20261013_143544_10_Berkhout2025__morpheus_mcp__rep03__replacement02/attempts/attempt_001/model.xml`: scored model
    - `rerun_gnuplot_10h/model.xml`: panel b check (model.xml of the re-run)
    - `20261013_143544_10_Berkhout2025__morpheus_mcp__rep03__replacement02/attempts/attempt_001/plot_00000.000.png`: panel b check (run's own frame, compared with the re-run's)
    - `rerun_gnuplot_10h/plot_00000.000.png`: panel b check (re-run frame, compared with the run's own), panel b frame (re-run of the scored model, Gnuplotter every 600 MCS)
    - `20261013_143544_10_Berkhout2025__morpheus_mcp__rep03__replacement02/attempts/attempt_001/plot_03000.000.png`: panel b check (run's own frame, compared with the re-run's)
    - `rerun_gnuplot_10h/plot_03000.000.png`: panel b check (re-run frame, compared with the run's own)
    - `20261013_143544_10_Berkhout2025__morpheus_mcp__rep03__replacement02/attempts/attempt_001/plot_06000.000.png`: panel b check (run's own frame, compared with the re-run's)
    - `rerun_gnuplot_10h/plot_06000.000.png`: panel b check (re-run frame, compared with the run's own)
    - `20261013_143544_10_Berkhout2025__morpheus_mcp__rep03__replacement02/attempts/attempt_001/plot_09000.000.png`: panel b check (run's own frame, compared with the re-run's)
    - `rerun_gnuplot_10h/plot_09000.000.png`: panel b check (re-run frame, compared with the run's own)
    - `20261013_143544_10_Berkhout2025__morpheus_mcp__rep03__replacement02/attempts/attempt_001/plot_12000.000.png`: panel b check (run's own frame, compared with the re-run's)
    - `rerun_gnuplot_10h/plot_12000.000.png`: panel b check (re-run frame, compared with the run's own), panel b frame (re-run of the scored model, Gnuplotter every 600 MCS)
    - `rerun_gnuplot_10h/plot_02400.000.png`: panel b frame (re-run of the scored model, Gnuplotter every 600 MCS)
    - `rerun_gnuplot_10h/plot_04800.000.png`: panel b frame (re-run of the scored model, Gnuplotter every 600 MCS)
    - `rerun_gnuplot_10h/plot_07200.000.png`: panel b frame (re-run of the scored model, Gnuplotter every 600 MCS)
    - `rerun_gnuplot_10h/plot_09600.000.png`: panel b frame (re-run of the scored model, Gnuplotter every 600 MCS)
    - `20261013_143544_10_Berkhout2025__morpheus_mcp__rep03__replacement02/attempts/attempt_001/native_cell_counts_by_half.csv`: panel d data
- `paper_data/compucell3d_rerun_timecourse.csv`: cell numbers over time from one run of the authors' own CompuCell3D model (CompuCell3D 4.3.0), rerun by co-author L.B.; the dashed reference lines of panel d (not published data).
- `model_graph/`: the model graph of `model.xml` as Morpheus 2.4.1 writes it (`10_Berkhout2025.dot`, full, on the model-graph pages; `10_Berkhout2025_reduced.dot`, panel c).
- Paper source (repository root): `benchmark_papers/10_Berkhout2025.pdf`.

## Legend

**Supplementary Fig. 10 | Neural tube closure (Berkhout *et al.*, 2025).** **a**, Cell field of the model of Berkhout *et al.*[berkhout2025] from 0 to 50 h (adapted from their Fig. 1). **b**, Model built by GPT-6.1 Sol with setup 5 (MCP; repetition 3, score 1.00). The model at the same times, with cells colored by tissue as in Fig. 1 of Berkhout *et al.*[berkhout2025] (key below). **c**, Model graph of the agent's model as drawn by Morpheus (full graph, wrapped into 4 rows). **d**, Number of surface ectoderm (**i**), neural crest (**ii**; agent's model, attached cells only), paraxial mesoderm (**iii**) and somite cells (**iv**) in the agent's model (solid lines, colored as in **b**) and in a rerun of the authors' CompuCell3D model (dashed; one run, CompuCell3D 4.3.0). Material from Berkhout *et al.*[berkhout2025] is adapted under a [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) license.
