# Supplementary Table 1: scoring criteria and weights

For each study, the target given to the LLM scorer and its weighted criteria, quoted from
`biological_scoring_criteria.json` (version 7) at the repository root, the file the benchmark's scorer used.

## Build

```bash
python figures/Supplementary/Supp_Table_1/build.py
```

writes `build/Supplementary_Figures_Table_1.tex` and `.pdf`, typeset as in the supplement
(`../engine/supp_extras.py`, `criteria_table`).

## Contents

- `data/biological_scores/<scorer folder>/README.md`: stands in for the scorer folder of the benchmark run. Its
  name (`scorer-v8__gpt-6-luna__high__criteria-v7-d1ebdab0ba34`) holds the first 12 hex digits of the SHA-256 of
  the criteria file that scored the runs; the build stops if `biological_scoring_criteria.json` does not match.
