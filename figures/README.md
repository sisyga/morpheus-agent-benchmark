# Figures and tables of the preprint

Every figure and table of the preprint has its own folder with a `README.md`, a `build.py` and everything it needs:

| Figure or table | Folder | Command (repository root) |
| --- | --- | --- |
| Fig. 1 | [`Fig1/`](Fig1/) | `uv run --locked python figures/Fig1/build.py` |
| Fig. 2 and the statistics in the text | [`Fig2/`](Fig2/) | `uv run --locked python figures/Fig2/build.py` |
| Supplementary Note 1 | [`Supplementary/Supp_Note_1/`](Supplementary/Supp_Note_1/) | `python figures/Supplementary/Supp_Note_1/build.py` |
| Supplementary Table 1 | [`Supplementary/Supp_Table_1/`](Supplementary/Supp_Table_1/) | `python figures/Supplementary/Supp_Table_1/build.py` |
| Supplementary Figs. 1–15 | [`Supplementary/Supp_Fig_NN_<Paper>/`](Supplementary/) | `python figures/Supplementary/Supp_Fig_NN_<Paper>/build.py` |
| The whole supplement (PDF) | [`Supplementary/`](Supplementary/) | `python figures/Supplementary/build_supplement.py` |

Each command writes to `build/` in its folder (ignored by git). The main figures use the repository's locked
environment (`uv sync --locked`) and headless Chrome to render PDF and PNG (`render_fig.py`); the supplement uses
its own pinned environment (see `Supplementary/README.md`).

On our system, Fig. 2 and Supplementary Figs. 1–15 built from these folders matched the published versions pixel
for pixel. Fig. 1 differs from the version in the first preprint only in its icons, which are our own drawings now. The data in the
folders are the files the figures read and nothing else from the benchmark runs; the complete run outputs (agent
transcripts, workspaces, all logs) are available on request.
