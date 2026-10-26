# Benchmark papers

The benchmark asks agents to rebuild the models of 15 published papers. The paper PDFs are not part of this
repository because several of them may not be redistributed. `papers.csv` lists each paper with its DOI and
the SHA-256 and size of the exact PDF the published benchmark runs used.

To run the benchmark on the same inputs, download each paper from its DOI, save it here as `<stem>.pdf`
(for example `01_Szabo2010.pdf`), and check the files against the manifest:

```bash
cd benchmark_papers
tail -n +2 papers.csv | awk -F, '{print $3"  "$1".pdf"}' | sha256sum -c
```

Several of the benchmark PDFs combine the article with its supplementary material, so a freshly downloaded
article PDF can differ from the file the runs used. A different PDF changes what the agent reads; record
mismatches when you compare results with the published runs.

The stem `04_Atwell2025` is a historical name: the paper is Atwell et al. (2015). The stem is kept because the
scoring criteria, focus prompts, and recorded runs refer to it.

Local PDFs in this folder are ignored by git. The test suite skips the paper-specific PDF tests when the files
are missing.
