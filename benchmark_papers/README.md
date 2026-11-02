# Benchmark papers

The benchmark asks agents to rebuild the models of 15 published papers. `papers.csv` lists each paper with its
DOI, the SHA-256 and size of the exact PDF the published benchmark runs used, its licence, and whether the PDF
is in this repository.

The eleven papers published under a Creative Commons Attribution licence (CC BY 3.0 or 4.0) are included here
as the PDFs the runs used. They are redistributed under those licences; copyright stays with the authors and
publishers named in each PDF, and `papers.csv` gives the reference and DOI for attribution. The other four may
not be redistributed:

| Stem | Paper | DOI |
| --- | --- | --- |
| `01_Szabo2010` | Szabó et al. (2010) Physical Biology | [10.1088/1478-3975/7/4/046007](https://doi.org/10.1088/1478-3975/7/4/046007) |
| `03_Carpenter2024` | Carpenter et al. (2024) Biophysical Journal | [10.1016/j.bpj.2024.03.002](https://doi.org/10.1016/j.bpj.2024.03.002) |
| `07_Scheel2021` | Scheel et al. (2021) Journal of Mathematical Biology | [10.1007/s00285-021-01627-w](https://doi.org/10.1007/s00285-021-01627-w) |
| `15_Reza2025` | Al Reza et al. (2025) Nature | [10.1038/s41586-025-08850-1](https://doi.org/10.1038/s41586-025-08850-1) |

To run the full benchmark on the same inputs, download these four from their DOIs, save each here as
`<stem>.pdf` (for example `01_Szabo2010.pdf`), and check all files against the manifest:

```bash
cd benchmark_papers
tail -n +2 papers.csv | awk -F, '{print $3"  "$1".pdf"}' | sha256sum -c
```

Several of the benchmark PDFs combine the article with its supplementary material, so a freshly downloaded
article PDF can differ from the file the runs used. A different PDF changes what the agent reads; record
mismatches when you compare results with the published runs. Without the four PDFs the runner runs the other
eleven papers and warns which listed papers are missing. The test suite skips the paper-specific PDF tests
for missing files.

The stem `04_Atwell2025` is a historical name: the paper is Atwell et al. (2015). The stem is kept because the
scoring criteria, focus prompts, and recorded runs refer to it.

## Preprints used by the supplementary figures

Panel a of Supplementary Figs. 3 and 15 is cropped from the bioRxiv preprints of Carpenter et al. and Al Reza
et al. (`preprints/preprints.csv`), both included unchanged in `preprints/`: the Carpenter preprint under CC BY 4.0
and the Al Reza preprint ([10.1101/2024.08.30.610426](https://doi.org/10.1101/2024.08.30.610426)) under
CC BY-NC-ND 4.0, which permits sharing it unchanged for non-commercial purposes.
