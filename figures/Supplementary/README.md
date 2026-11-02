# Supplementary information

One folder per item. Each holds a `README.md`, a `build.py` that rebuilds it into `build/` in that folder, and
everything the item needs except the shared code in `engine/` and the paper PDFs in `benchmark_papers/`.

| Item | Folder |
| --- | --- |
| Supplementary Note 1, agent prompt | [`Supp_Note_1/`](Supp_Note_1/) |
| Supplementary Table 1, scoring criteria and weights | [`Supp_Table_1/`](Supp_Table_1/) |
| Supplementary Fig. 1, Szabó et al. (2010) | [`Supp_Fig_01_Szabo2010/`](Supp_Fig_01_Szabo2010/) |
| Supplementary Fig. 2, Thapa et al. (2024) | [`Supp_Fig_02_Thapa2024/`](Supp_Fig_02_Thapa2024/) |
| Supplementary Fig. 3, Carpenter et al. (2024) | [`Supp_Fig_03_Carpenter2024/`](Supp_Fig_03_Carpenter2024/) |
| Supplementary Fig. 4, Atwell et al. (2015) | [`Supp_Fig_04_Atwell2015/`](Supp_Fig_04_Atwell2015/) |
| Supplementary Fig. 5, Berkemeier et al. (2023) | [`Supp_Fig_05_Berkemeier2023/`](Supp_Fig_05_Berkemeier2023/) |
| Supplementary Fig. 6, Herron et al. (2022) | [`Supp_Fig_06_Herron2022/`](Supp_Fig_06_Herron2022/) |
| Supplementary Fig. 7, Scheel et al. (2021) | [`Supp_Fig_07_Scheel2021/`](Supp_Fig_07_Scheel2021/) |
| Supplementary Fig. 8, Mu et al. (2024) | [`Supp_Fig_08_Mu2024/`](Supp_Fig_08_Mu2024/) |
| Supplementary Fig. 9, Luque et al. (2023) | [`Supp_Fig_09_Luque2023/`](Supp_Fig_09_Luque2023/) |
| Supplementary Fig. 10, Berkhout et al. (2025) | [`Supp_Fig_10_Berkhout2025/`](Supp_Fig_10_Berkhout2025/) |
| Supplementary Fig. 11, Anlaş et al. (2024) | [`Supp_Fig_11_Anlas2024/`](Supp_Fig_11_Anlas2024/) |
| Supplementary Fig. 12, Malkmus et al. (2025) | [`Supp_Fig_12_Malkmus2025/`](Supp_Fig_12_Malkmus2025/) |
| Supplementary Fig. 13, Molè et al. (2026) | [`Supp_Fig_13_Mole2026/`](Supp_Fig_13_Mole2026/) |
| Supplementary Fig. 14, Otsuki et al. (2025) | [`Supp_Fig_14_Otsuki2025/`](Supp_Fig_14_Otsuki2025/) |
| Supplementary Fig. 15, Al Reza et al. (2025) | [`Supp_Fig_15_AlReza2025/`](Supp_Fig_15_AlReza2025/) |
| Supplementary Data, the 15 shown `model.xml` | `data/<run>/attempts/attempt_001/model.xml` in each figure folder; zipped by `build_supplement.py` |

## Build everything

```bash
uv venv ~/.venvs/morpheus_supp_figs --python 3.12
uv pip install --python ~/.venvs/morpheus_supp_figs -r figures/Supplementary/engine/requirements.txt
~/.venvs/morpheus_supp_figs/bin/python figures/Supplementary/build_supplement.py --out <new folder>
```

(On Windows the interpreter is `~/.venvs/morpheus_supp_figs/Scripts/python.exe`.)

This writes every figure, the model-graph pages, Supplementary Table 1 and Note 1, `Supp_Fig_best_model_xmls.zip`
and `Supplementary_Figures.pdf`, all legends (`captions.md`) and a style check against the Nature figure guide.
On our system (Windows 11 with the tools below), the figures and legends built this way matched the published
supplement pixel for pixel and word for word; other systems may differ slightly in fonts and anti-aliasing. `--from-scratch` also
regenerates every model graph from its `model.xml` with the Morpheus CLI.

Tools used for the published supplement: Python 3.12 with the packages pinned in `engine/requirements.txt`,
Graphviz 16.1.0 (`dot` on `PATH`), Morpheus 2.4.1 (only for `--from-scratch`), Arial, and TeX Live 2025 with
revtex4-2 for the PDF.

## Data

Each figure's `data/` holds only the files of the shown benchmark run that the figure reads; `DATA_MANIFEST.csv`
lists every file with its SHA-256. Three kinds of file differ from the run, and the manifest gives both checksums:

- `figure_data/*.csv` in a run's attempt folder: small tables that `panel.py` computes from a large output that is
  not included (Szabo's 131 MB track log, Mu's 40 MB TIFF stack and 22 MB cell log, Otsuki's 11 MB field log);
- Atwell's Morpheus checkpoints, renamed `checkpoint_<time>.xml.gz` and without their field data (the 3D renders
  read only the cell nodes);
- `Supp_Table_1/data/biological_scores/<scorer>/README.md`, which stands in for the scorer folder whose name
  carries the hash of the criteria file.

Four shown models refer to files on the machine that ran the benchmark. Thapa and Berkemeier call an analysis
script of the agent at the end of the simulation; it is not included, and Morpheus only reports that the command
failed. Mu and Luque read TIFF inputs by absolute path; to rerun them, point the `TIFFReader` paths to the files in
`data/<run>/agent_workspace/assets/`. The complete run outputs (agent transcripts, workspaces, all logs) are not
published; they are available on request.

`engine/` holds the shared code (layout, legends, model graphs, the LaTeX document); its `README.md` documents
every input and option.
