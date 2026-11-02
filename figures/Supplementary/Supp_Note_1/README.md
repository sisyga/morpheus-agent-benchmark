# Supplementary Note 1: agent prompt

The complete prompt of the agent that built the Molè et al. (2026) model shown in Fig. 2e and Supplementary
Fig. 13 (GPT-6.1 Sol, setup 4, Skill), followed by the resources block of each of the five setups.

## Build

```bash
python figures/Supplementary/Supp_Note_1/build.py
```

writes `build/Supplementary_Figures_Note_1.tex` and `.pdf` and copies the quoted prompts to
`build/Supplementary_Note_1/` (`../engine/supp_extras.py`, `collect_prompts`, `prompt_note`).

## Contents

- `data/<run>/subject_prompt.txt`: the prompt each run saved, verbatim, for the shown Molè run and one Molè run
  of each other setup (python_web, morpheus_cli, morpheus_cli_docs, morpheus_mcp).
