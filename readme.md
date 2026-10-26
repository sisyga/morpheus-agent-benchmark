# Morpheus agent benchmark

This repository holds the code of a benchmark that tests whether LLM-based coding agents can rebuild published multicellular models in the simulator [Morpheus](https://morpheus.gitlab.io). An agent receives one of 15 papers, writes a MorpheusML model of it, runs Morpheus, and revises the model within a fixed time budget. A separate scoring agent can then check the simulation output against paper-specific criteria. The code accompanies the preprint "LLM-based agents can autonomously generate, execute, and refine in silico models" (Chandratre et al., 2026).

The repository has three parts:

- a benchmark runner, built on the Codex SDK, that runs each paper under five tool configurations (modes) and scores the results;
- a Morpheus skill and a Python MCP server for PDF staging, XML writing, Morpheus execution, and output inspection, which also serve modeling tasks outside the benchmark;
- analysis scripts that turn finished benchmark folders into CSV tables, statistical tests, and figures.

The benchmark runs, automated scores, and manual scores reported in the preprint are archived in a separate Zenodo dataset (DOI to be added). Cite this code with [CITATION.cff](CITATION.cff) or its Zenodo record.

## Installation

Python dependencies are managed with [uv](https://docs.astral.sh/uv/). `pyproject.toml` declares the dependencies, `uv.lock` locks their versions across platforms, and `uv sync --locked` creates the local `.venv/` after cloning. The project defaults to Python 3.12 via `.python-version`, requires Python 3.11 or newer, and uses only uv-managed interpreters (`python-preference = "only-managed"`). Node dependencies continue to use npm.

The benchmark paper PDFs are not included because several may not be redistributed. [benchmark_papers/README.md](benchmark_papers/README.md) explains how to download them and check them against the SHA-256 checksums of the files the published runs used.

Choose the setup path for the host that will execute Morpheus:

- [Native Linux](SETUP.md#native-linux): full benchmark support with configurable parallelism.
- [WSL2](SETUP.md#wsl2): recommended Windows route for full or parallel runs; keep the repository under `~/...` and install Linux Morpheus.
- [Native Windows](SETUP.md#native-windows): supported for review and small runs with the elevated Codex sandbox and serial benchmark/scoring jobs.

Minimal native Windows setup from the repository root:

```powershell
winget install --id=astral-sh.uv -e
# Open a new PowerShell window if uv is not yet on PATH.
uv sync --locked
npm ci
```

The Python environment includes the MCP/PDF utilities plus common postprocessing packages (`numpy`, `pandas`, `matplotlib`, `scipy`, and `Pillow`) so benchmark agents can analyze generated CSVs/images and render final plots inside the run directory.

Environment activation is optional: use `uv run --locked python ...` for scripts. The benchmark runner discovers the project `.venv` automatically, so `npm run benchmark` also works without activation. It requires a uv-built `.venv` and gives benchmark subjects read-only access to it and its uv-managed interpreter.

For Linux commands, WSL2 installation, native Windows sandbox initialization, Morpheus setup, and troubleshooting, see [SETUP.md](SETUP.md).

## Quick start

1. Run `uv sync --locked` and `npm ci` to install Python and Node dependencies.
2. Confirm that `codex login status` and `morpheus --help` both work.
3. Add the paper PDFs to `benchmark_papers/` as described in [benchmark_papers/README.md](benchmark_papers/README.md).
4. Run `npm run benchmark -- --max-papers 1`.
5. Run `uv run --locked python analyze_benchmark.py benchmark_runs/<timestamp>_benchmark`.
6. Inspect the new timestamped benchmark folder under `benchmark_runs/`.

## What the benchmark does

For each PDF in `benchmark_papers/`, the runner can run one or more benchmark capability modes. The default mode is `morpheus_mcp`, which gives the agent every tool. The available modes are:

- `python_web`: web search + Python only. The agent must still produce MorpheusML `model.xml`; the host runs Morpheus on it afterward so that its output can be scored.
- `morpheus_cli`: web search + Python + Morpheus CLI, without the Morpheus skill or MCP tools.
- `morpheus_cli_docs`: Python + Morpheus CLI with internet disabled, using only staged MorpheusML documentation and the basic model template.
- `morpheus_skill`: web search + Python + Morpheus CLI + Morpheus skill, without MCP tools.
- `morpheus_mcp`: web search + Python + Morpheus CLI + Morpheus skill + Morpheus MCP tools.

For each selected paper, mode, and repetition, the runner:

1. creates a timestamped benchmark directory and one isolated paper/mode/repetition run directory inside it;
2. stages the PDF, extracted paper text, focus prompt, and a visual manifest in an isolated `agent_workspace`;
3. detects likely figure and table pages but does not attach all page images up front;
4. exposes only the capabilities allowed by the selected benchmark mode;
5. lets the agent write MorpheusML, create fresh attempt folders, inspect stdout/stderr, CSVs, plots, and local PNGs directly, and revise if needed;
6. records attempt-level self-scores, model XML versions, technical evaluation files, and reproduction-oriented evaluation files;
7. gives the subject one continuous, time-bounded execution; only a classified infrastructure failure may trigger one clean replacement with a new thread and empty workspace;
8. regenerates deterministic summaries, analysis tables, and figures unless disabled.

Each run writes up to three scores:

- `biological_scores/scorer-v...json`: the 0-1 biological score that the preprint reports, written when biological scoring is enabled (`--score-biological` or `npm run score:biology`). An independent scoring agent checks the run's output against the paper's clauses in `biological_scoring_criteria.json`. Scores are stored by scorer cohort, so rescoring never overwrites earlier scores. A same-named folder next to each score file holds that scorer's `transcript.jsonl` and `codex_home/` snapshot. The benchmark-level `biological_scores/<scorer cohort>/biological_score_details.xlsx` collects the per-run files into one clause-level workbook.
- `reproduction_report.json`: the agent's own 0-8 assessment of its final model, with four 0-2 criteria:
  - `source_coverage`
  - `mechanism_mapping`
  - `observable_alignment`
  - `parameter_plausibility`

  The agent also rates each attempt on this rubric (`attempt_reproduction.json`). These self-scores guide its revisions; the preprint does not use them for evaluation.
- `technical_evaluation.json`: a deterministic 0-7 executability score of the host's Morpheus run. The preprint does not use it.

The default runner concurrency is one job at a time. Linux and WSL2 can run independent paper/mode/repetition jobs in parallel with `--max-concurrent-jobs`; native Windows clamps benchmark, recovery, and biological-scoring agent concurrency to `1`. Each benchmark invocation writes benchmark-level diagnostics in the timestamped benchmark directory. It does not modify the source PDFs or the Morpheus skill reference material.

## Repository layout

- `pyproject.toml`, `uv.lock`, `.python-version`
  Python dependencies, cross-platform dependency lockfile, and default interpreter version, managed with uv.
- `benchmark_papers/`
  Benchmark inputs. The runner scans this folder for PDF files. The PDFs are not distributed; `papers.csv` lists the 15 papers with DOIs and checksums, and `README.md` explains how to obtain them.
- `benchmark_focus/`
  Optional per-paper focus prompts. A file named like the PDF stem, for example `10_Berkhout2025.txt`, is appended to that paper's benchmark prompt.
- `.agents/skills/morpheus/`
  The publishable Morpheus skill and reference set used by the benchmark and intended for general Morpheus modeling tasks beyond paper recreation.
- `src/benchmark/`
  TypeScript benchmark runner built on the Codex SDK.
- `server.py`
  MCP server entry point. The supported transport is stdio.
- `morpheus_mcp_server.py`
  Python implementation of the deterministic Morpheus and PDF utilities.
- `morpheus_tools_cli.py`
  JSON bridge used by the benchmark runner.
- `.mcp.json`
  Machine-readable MCP startup contract for local clients.
- `benchmark.config.json`
  Default benchmark configuration.
- `biological_scoring_criteria.json`
  Versioned runtime copy of the biological scoring criteria matched by normalized paper stem. The clause tables in `Biological_scoring_criteria_v7.xlsx` (one sheet per paper) are the authoritative source, including each clause's weight. Clause results are boolean, and a paper's score is the passed weight divided by its total weight; the v7 weights give the qualitative and numeric categories equal total weight.
- `Biological_scoring_criteria_v7.xlsx`
  Authoritative biological scoring criteria: one sheet per paper with target, scoring instructions, formula rows, and a clause table (ID, kind, weight, share, criterion).
- `sync_biological_scoring_criteria.py`
  Synchronizes the runtime JSON with the criteria workbook. It reads clause weights from the tables as written and refuses workbooks whose formula rows or Share column disagree with the clause tables. Run it without `--update` to check for drift, or with `--update` to refresh the JSON.
- `manual_biological_scores.py`
  Exports the manual scores of a scoring workbook (`Benchmark_Manual_Scores_*.xlsx`, archived with the benchmark dataset) to the CSV files that `biological_score_comparison.py` reads. It takes each run's score from the Mean column of an `Updated_manual_scores_*` sheet, or from column V of the active sheet when the workbook has no such sheet, and refuses a sheet whose Mode or Mean headers have moved.
- `biological_score_comparison.py`
  Compares the manual with the automated biological scores of the same runs to validate the scorer.
- `biological_score_details.py`
  Writes the clause-level scoring workbooks, one per scorer cohort, from the score JSON files a benchmark already contains.
- `compare_benchmarks.py`
  Compares complete benchmark runs of two or more models, with paired statistical tests.
- `scripts/`
  `benchmark_time_left.py` (the subject's time-left command), the Codex smoke checks, `stranded-runs/` (finalizes executions whose host process failed after the subject had finished; written after a full disk on 2026-10-11), and `supp_figs/` (the paper-comparison supplementary figures; see its README).
- `tests/`
  Python (`pytest`) and TypeScript (`npm run test:ts`) test suites. Tests that need the benchmark paper PDFs skip when the PDFs are missing.
- `LICENSE`, `NOTICE`, `CITATION.cff`, `.zenodo.json`
  Apache-2.0 license, third-party notices for the Morpheus-derived files, and citation metadata.

## Minimal benchmark run

Start with one paper instead of the full benchmark:

```powershell
npm run benchmark -- --max-papers 1
```

If that succeeds, you should see:

- a new run folder under `benchmark_runs/`;
- `benchmark_summary.json` and `benchmark_manifest.json` in that run folder;
- a `model.xml` generated for that paper;
- Morpheus attempt logs under host `attempts/attempt_###/` and, for agent-run attempts, under `agent_workspace/.../attempt_###/`;
- `technical_evaluation.json`;
- `reproduction_report.json`;
- transcript files under `transcripts/`;
- a paper-specific subfolder containing the generated model, reports, logs, and transcripts.

To run the full benchmark set:

```powershell
npm run benchmark
```

To run a specific capability mode:

```powershell
npm run benchmark -- --benchmark-mode python_web
```

To run all capability modes as a comparison matrix:

```powershell
npm run benchmark -- --all-benchmark-modes
```

To see available CLI options:

```powershell
npm run benchmark -- --help
```

## Benchmark CLI reference

The benchmark entry point is:

```powershell
npm run benchmark -- [options]
```

Core run selection:

- `--config <path>`: load a non-default benchmark config file.
- `--benchmark-mode <python_web|morpheus_cli|morpheus_cli_docs|morpheus_skill|morpheus_mcp>`: select one mode; repeat the flag to select multiple modes.
- `--all-benchmark-modes`: run all supported modes.
- `--papers-dir <path>`: override the PDF input folder.
- `--results-dir <path>`: override the parent output folder.
- `--benchmark-focus-dir <path>`: override the focus prompt folder.
- `--no-benchmark-focus`: disable focus prompts.
- `--max-papers <number>`: run only the first N papers after sorting.
- `--start-at-paper <pdf filename|stem>`: start from a specific paper.
- `--repetitions <number>`: repeat every paper/mode combination.

Model and runtime controls:

- `--model <name>`: override the Codex model, e.g. `gpt-6.1-sol` or `gpt-6-luna`.
- `--reasoning-effort <none|low|medium|high|xhigh|max>`: override reasoning effort. The default is `gpt-6.1-sol` at `xhigh`.
- `--total-time-limit-minutes <number>`: total active subject time per paper/mode/repetition. The default is 240 minutes (4 hours).
- `--finalization-reserve-minutes <number>`: reserve inside that total during which new Morpheus simulations are refused so the subject can inspect artifacts and finalize. The default is 10 minutes.
- `--max-concurrent-jobs <number>`: run independent paper/mode/repetition jobs in parallel on Linux or WSL2; native Windows records and uses `1`.
- `--codex-quota-job-cost-percent <number>`: initial estimate of the weekly Codex quota share one job uses, for the quota guard (default 2; 0 disables it).
- `--page-render-dpi <number>`: preferred DPI when agents render selected PDF pages.
- `--representative-output-frames <number>`: preferred number of Morpheus output frames to sample when visual inspection is needed.
- `--codex-allow-env <NAME>`: allow one additional non-secret host environment variable inside benchmark Codex agents; repeat for multiple variables.
- `--bridge-tool-timeout-ms <number>`: timeout for host-side Python bridge calls.
- `--morpheus-run-timeout-ms <number>`: timeout for individual Morpheus executions.
- `--morpheus-num-threads <number>`: set the baseline Morpheus thread count. The host technical rerun reuses the actual thread count from the newest successful agent attempt whose XML matches the canonical model; otherwise it uses this value. The checked-in `benchmark.config.json` sets `1`; set `morpheusNumThreads` to `null` to fall back to Morpheus' own `OMP_NUM_THREADS`/auto behavior.
- `--morpheus-xml-schema-path <path>`: override the MorpheusML schema used for diagnostics.
- `--score-biological`: after benchmark/recovery/combination, run opt-in biological scoring before analysis.
- `--skip-scored-attempts`: with `--score-biological`, reuse an existing score only when the attempt artifact hash, criteria hash, scorer version, scorer model, and reasoning effort all match.
- `--biological-scoring-criteria-path <path>`: criteria registry path. Defaults to `biological_scoring_criteria.json`.
- `--biological-scoring-model <name>`: Codex model used by scoring agents.
- `--biological-scoring-reasoning-effort <none|low|medium|high|xhigh|max>`: reasoning effort for scoring agents. The default is `gpt-6-luna` at `high`.
- `--biological-scoring-max-concurrent-jobs <number>`: parallel biological scoring sessions on Linux or WSL2; native Windows records and uses `1`.
- `--biological-scoring-turn-timeout-ms <number>`: timeout for one scoring turn; a scorer that exceeds it is killed and recorded as `scoring_failed`.
- `--no-analysis`: skip the automatic final `analyze_benchmark.py` step.

Recovery and aggregation:
- `--recover-run <benchmark run dir>`: rerun recorded infrastructure failures that have not used their one clean replacement, launch assignments the queue never started, re-audit stored capability events, then rebuild summaries/reports. Successful assignments and benchmark outcomes such as time limits are not relaunched. Runs of the version 1 protocol (`max_cycles_v1`) are read-only.
- `--combine-runs <benchmark run dir> <benchmark run dir> [...]`: combine completed benchmark folders from the same cohort, that is, with the same protocol, benchmark version, skill and prompt hashes, time budget, subject and scorer models and efforts, scorer version, job concurrency, and Morpheus thread count. When a later folder repeats a paper/mode repetition, its results are appended as additional repetitions (recorded with `sourceBenchmarkRunDir` and `sourceRepetition`) rather than overwriting earlier ones. The combined summary reports the source runs' configuration.
- `--combined-run-dir <output dir>`: output folder for a combined run summary.

Subject work is never resumed with mismatched context and workspace state. One classified infrastructure failure may receive one replacement execution during the run or a later explicit `--recover-run`, but that replacement starts with a new execution ID, new thread, new Codex home, empty workspace, and the full configured budget. Infrastructure failures include failures before the subject starts (run creation, paper extraction, command-runner preflight) and Codex exiting with an error mid-execution. Systemic command-runner preflight failures are not replaced automatically because the replacement would fail the same way; they stop the queue instead. A host-side error after the subject has started is not replaced automatically. The automatic post-run recovery pass only performs deterministic postprocessing. Time limits, Morpheus timeouts, malformed final output, and invalid model XML are benchmark outcomes rather than retry reasons.

Codex service refusals are handled separately. An exhausted usage quota ("You've hit your usage limit") gets no automatic replacement and stops the queue. Running jobs finish, but no new jobs start. Once the quota resets, run `--recover-run` on the same folder. It reruns every quota-failed assignment and starts the assignments that were never launched, using the run's recorded model, effort, and budget. Quota failures and "Selected model is at capacity" failures do not use up an assignment's one clean replacement, so they can be rerun as often as needed. Each rerun is a fresh execution with the full budget, and every earlier execution stays in the audit trail.

The quota guard prevents most of these mid-run cut-offs. Codex records the account's weekly quota usage in every session log. Before each job starts, the runner reads the latest value from the running jobs' sessions and starts the job only if `used + (running jobs + 1) × cost per job` stays at or below 100%. If it doesn't, no new jobs start, the running ones finish normally, and you continue with `--recover-run` after resetting the quota. The cost per job starts at `--codex-quota-job-cost-percent` (default 2%, a cautious value above the ~1.3% per job that a `gpt-6.1-sol` `max` run used). Once 5 jobs have finished, the runner measures the cost itself and keeps that measurement across manual quota resets. Until the first running job reports the quota, the guard holds the other jobs back for up to 10 minutes. `--codex-quota-job-cost-percent 0` disables the guard.

Jobs run repetition-first: rep01 of every paper and mode, then rep02, and so on. Recovery uses the same order. If the queue stops early, every paper and mode still has the same number of finished repetitions.

## Analysis figures

After a normal run, manual recovery, or run combination, the CLI runs the analysis script automatically by default. To regenerate analysis tables and figures manually, run:

```powershell
uv run --locked python analyze_benchmark.py benchmark_runs/<timestamp>_benchmark
```

By default the script writes to `<benchmark_dir>/analysis_figures/`. Use `--out-dir <path>` to choose another output directory and `--formats png svg pdf` to control figure formats. Pass `--no-analysis` to `npm run benchmark -- ...` if you want the benchmark CLI to skip the automatic final analysis step.

The analysis output includes:

- `benchmark_analysis_by_run.csv`
- `benchmark_analysis_by_mode.csv`
- `benchmark_analysis_by_paper_cohort_and_mode.csv`
- `benchmark_cost_quality_by_mode.csv`
- `benchmark_dollar_cost_quality_by_mode.csv`
- `benchmark_attempt_self_scores.csv`
- `benchmark_biological_scores.csv`
- `mode_comparison_overview`
- `score_distributions_by_mode`
- `runtime_breakdown_by_mode`
- `token_usage_by_mode`
- `api_cost_by_mode`
- `run_outcomes_by_mode`
- `scores_by_paper`
- `resource_usage_by_mode`
- `outcomes_and_efficiency`
- `token_quality_pareto`
- `api_cost_quality_pareto`
- `token_biological_score_pareto`
- `api_cost_biological_score_pareto`
- `attempt_self_scores_by_paper`
- `attempt_self_scores_by_mode`

The standalone score figure uses a box-plot grid for technical, reproduction, and available biological score sources across all papers, papers 1-10 with modeling-keyword overlap, and papers 11-15 requiring more biological abstraction. The overview quality panel uses box plots as well. The token and API-cost figures each use an all-paper two-panel layout: stacked component means on the left and total-value box plots on the right. The runtime and outcome cohort figures use three side-by-side stacked-bar panels for the same paper splits.

Attempt-level plots use `attempt_reproduction.json` files written by agents inside attempt folders. If an agent attempt folder is missing that file, the analysis script derives the attempt number from the `attempt_###` directory name and keeps its score blank rather than inventing a zero.

To compare complete benchmark runs produced by different models, run:

```powershell
uv run --locked python compare_benchmarks.py benchmark_runs/<first>_benchmark benchmark_runs/<second>_benchmark [benchmark_runs/<third>_benchmark ...] --out-dir benchmark_model_comparison
```

The comparison script accepts two or more benchmark folders, with optional `--labels` (one per folder; default `<model> (<reasoning effort>)`). It refuses to compare runs whose protocol, time budget, benchmark version, or scorer cohort differ unless `--force` is passed. Runs whose subject never started (no tokens and no cost) are excluded from both score and cost and listed in `benchmark_model_comparison_excluded_runs.csv`; failed runs that did spend tokens keep their intention-to-treat score. Repetitions are averaged within each paper and mode first, so runs with different repetition counts receive equal paper weighting, and papers are the unit of replication. It writes PNG, PDF, and SVG by default (`--formats` selects a subset): `biological_score_by_model_and_mode` and `api_cost_by_model_and_mode` (box plots of paper-level means, cost on a log axis), `technical_score_by_model_and_mode`, `active_time_by_model_and_mode` and `revisions_by_model_and_mode` (the same box plots for the technical score, subject active time and model revisions), `api_cost_biological_score_pareto_by_model` (mode means with 95% confidence intervals and the Pareto frontier), and `overall_score_and_cost_by_model` (per-model means over the four Morpheus modes with 95% confidence intervals). Confidence intervals are 95% BCa bootstrap intervals over papers (`--ci t` switches to mean ± t·SD/√n). Box plots draw the mean and its CI over each box, a bracket in each mode with asterisks for the significance level (* p < 0.05, ** p < 0.01, *** p < 0.001, n.s.) of the Holm-adjusted paired between-model test, and a compact letter display per model: modes of one model that share no letter differ (pairwise Wilcoxon over all modes, Holm-adjusted, p < 0.05). `--no-significance` leaves brackets and letters out of the figures; the MD files are written either way. Figures carry no titles so captions can describe them. Paper-level, model/mode-level, and overall source CSVs are written alongside; the summaries keep the across-paper SD next to the confidence interval.

Statistics compare the paper-level means paired by paper: two-sided Wilcoxon signed-rank tests with zero differences kept in the ranking (Pratt) and the exact sign-flip null, which stays valid with scores tied at the ceiling; cost and active time are compared on a log scale and reported as geometric-mean ratios. Between models the script tests each mode (Holm across modes) and the Morpheus-mode average; within each model it tests each Morpheus mode against Python + web (Holm across modes), runs a Friedman test across the Morpheus modes, and all Morpheus-mode pairs post hoc (Holm across pairs). Every figure gets a `<figure>_stats.md` next to it with the means, CIs, effects, raw and Holm-adjusted p-values and rank-biserial effect sizes; `statistical_tests.md` and `statistical_tests.csv` hold all tests.

To score biology for an existing run without rerunning the benchmark, run:

```powershell
npm run score:biology -- benchmark_runs/<timestamp>_benchmark --model gpt-6-luna --reasoning-effort high --max-concurrent-jobs 4 --skip-scored-attempts
uv run --locked python analyze_benchmark.py benchmark_runs/<timestamp>_benchmark
```

The standalone scorer accepts `--model`, `--reasoning-effort`, `--max-concurrent-jobs`, `--criteria-path`, `--turn-timeout-ms`, and `--skip-scored-attempts`. Its concurrency option applies on Linux and WSL2 and is clamped to `1` on native Windows. Each scorer works read-only with the canonical attempt as its sole scoring target. It can also inspect the run's `agent_workspace` and the staged Morpheus skill to interpret assets referenced by the canonical `model.xml`, but outputs or alternative models in that reference workspace are not scoring evidence. Network access, web search, plugins, and Morpheus MCP tools remain disabled. Failed canonical simulations without scoreable output receive `model_failed` and score zero without invoking a scoring agent. Missing evidence without an explicit execution failure receives `insufficient_evidence` and a null score. Partial runs with scoreable output receive credit for demonstrated behavior, using the last observed state for endpoint clauses. Cached scores are reused only when the scorer version/model/effort, criteria SHA-256, and attempt-artifact SHA-256 all match.

### Clause-level scoring workbooks

After scoring, the runner writes `biological_scores/<scorer cohort>/biological_score_details.xlsx` in the benchmark folder; if that step fails, scoring still completes and the log says why. The same workbooks can be rebuilt at any time from score files a benchmark already holds, including cohorts written by earlier scorer versions:

```powershell
uv run --locked python biological_score_details.py benchmark_runs/<timestamp>_benchmark --list-variants
uv run --locked python biological_score_details.py benchmark_runs/<timestamp>_benchmark
```

Each workbook covers one scorer cohort: `scorer-v<version>__<model>__<effort>__criteria-v<version>-<sha12>`, derived from the score files themselves; scores written before scorer provenance was recorded collect in a `legacy-unversioned` cohort. `Overview` holds the cohort provenance, status counts, and mean score per mode; `Criteria` maps each `cNN` column prefix to its clause id, kind, weight, and description; and one sheet per paper carries a row for every mode and repetition with the clause verdict, observed value, evidence, and rationale side by side, plus the summary, limitations, and total score. Runs the cohort never scored appear with status `missing`, so each sheet is a complete paper-by-mode matrix. Clause metadata comes from `biological_scoring_criteria.json` only when its SHA-256 matches the cohort; otherwise the clause columns fall back to the ids observed in the score files and `Overview` says so. `--variant` limits the export to one cohort, `--manual-csv` adds manual-score deltas, and `--all-runs-sheet` adds a flat cross-paper sheet.

The scorer of this release (scorer v8) applies criteria v7 from `Biological_scoring_criteria_v7.xlsx`, the version used in the preprint. Each paper's sheet gives the target, the scoring instructions, and the weighted clauses. The common subject prompt asks the agent for initial and final CSV states with time units, so that endpoint clauses can be checked.

The scorer reads the synchronized JSON at runtime. To check or refresh it from the criteria workbook (`--workbook` selects another file, e.g. a fresh Numbers export):

```powershell
uv run --locked python sync_biological_scoring_criteria.py
uv run --locked python sync_biological_scoring_criteria.py --update
```

### Validating the scorer against manual scores

The preprint validates the automated scorer against manual scores of the same runs. To repeat the comparison, export the manual scores of a scoring workbook into the benchmark folder and compare them with the automated scores, which `analyze_benchmark.py` writes to `analysis_figures/benchmark_biological_scores.csv`:

```powershell
uv run --locked python manual_biological_scores.py <Benchmark_Manual_Scores.xlsx> --output-dir benchmark_runs/<timestamp>_benchmark
uv run --locked python biological_score_comparison.py benchmark_runs/<timestamp>_benchmark
```

The comparison writes to `manual_score_comparison/` in the benchmark folder: CSV summaries by run, paper and mode, mode, and paper criterion, and `biological_score_discrepancy_report.md`. The criterion CSV counts exact agreements, discrepancies, over-scores, and under-scores for every paper-specific criterion. The report gives agreement statistics over all runs and over scored runs only, status coverage, common score mismatches, and the largest individual errors. It also reports the ordinary least-squares regression of unbinned automated scores on manual scores (slope, intercept, R²), the slope's deviation from 1 and from 0.5, and the mean signed bias (automated minus manual). Perfect agreement has slope 1 and intercept 0; undefined regressions or R² are reported as NA.

The figure `biological_score_manual_vs_agent` is a 10×10 count heatmap with 0.1-wide score bins (lower edge inclusive; the top bin also holds 1.0) and the count printed in each occupied bin. Scores are fractions k/n of satisfied criteria (n = 3–10), so every bin contains at least one attainable value and 0.8 stays separate from 1.0. The reversed colour map shows low counts light and high counts dark. The colour scale starts at one observation, so empty bins take the colour map's under colour (white), which the colour bar shows as an arrow below its lowest count. A second figure, `biological_score_manual_vs_agent_dark`, uses the non-reversed colour map with the same count scale, again with white empty bins so that they stay distinct from its dark low-count end. Both axes span exactly 0–1, a dashed diagonal marks perfect agreement, and the plots have no grid lines. Both figures are written as PNG, SVG, and PDF.

## Direct MCP usage

The repository's supported MCP transport is **stdio**. The benchmark runner uses the same contract internally, and the repo-root `.mcp.json` exposes it for local MCP clients.

Equivalent startup forms are:

```powershell
uv run --locked python server.py
```

or via `.mcp.json`:

```json
{
  "mcpServers": {
    "morpheus": {
      "command": "uv",
      "args": ["run", "--locked", "python", "server.py"]
    }
  }
}
```

Run these startup forms from the repository root. The benchmark's `mcpCommand` continues to use `python`, which the runner resolves to the project `.venv` interpreter; benchmark agents do not need uv or package downloads at runtime.

The server does not support an HTTP `/mcp` transport.

## Runtime defaults

Each paper/mode/repetition job receives one continuous subject execution with `totalTimeLimitMs = 14400000` (4 hours) by default. The limit is configurable, not hardcoded:

```powershell
npm run benchmark -- --total-time-limit-minutes 300 --finalization-reserve-minutes 10
```

The runner starts the authoritative clock only after the Codex child process starts successfully. The master prompt gives the subject the exact total, soft cutoff, and hard cutoff. `benchmark-time-left` reports the current remaining time whenever the subject invokes it. The runner sends no continuation prompts and grants no extra time for finalization.

Jobs run sequentially by default (`maxConcurrentJobs = 1`). On Linux or WSL2, raise the cap to run independent paper/mode jobs in parallel:

```bash
npm run benchmark -- --all-benchmark-modes --max-papers 1 --max-concurrent-jobs 2
```

This cap is also the practical upper bound on how many agents can start Morpheus work at the same time.
On native Windows, the runner automatically selects the elevated Codex sandbox and forces benchmark, recovery, and biological-scoring jobs to run serially. If the elevated sandbox cannot be initialized, use WSL2; the unelevated fallback cannot enforce the benchmark's fine-grained filesystem permission profile.

For long benchmark runs with many faulty generated MorpheusML files, native Linux or WSL2 with a Linux Morpheus installation is recommended. Avoid launching a Windows Morpheus `.exe` from WSL2; keep the repo on the Linux filesystem and make sure `morpheus --help` resolves to the Linux command. See the [platform-specific setup](SETUP.md#2-choose-your-platform).

Benchmark-subject Codex agents do not inherit the runner's full host environment. The runner passes only process-startup essentials, the local Python virtualenv, isolated `CODEX_HOME`, deadline files, and a trusted timed Morpheus launcher where the selected mode allows it. The real Morpheus directory is removed from the subject `PATH`; the launcher and its configuration live outside the writable `agent_workspace`. Host API keys and token/secret-style variables are stripped by default. If local non-secret tooling needs another variable, set `codexAllowedEnvVars` in `benchmark.config.json` or repeat `--codex-allow-env NAME`.

Individual Morpheus simulations have a 60-minute default cap (`morpheusRunTimeoutMs = 3600000`) in both CLI and MCP modes. The effective cap is `min(morpheusRunTimeoutMs, time until the soft cutoff)`, so with a 5-hour total and 10-minute reserve, new simulations are refused after 4h50m. A timed-out simulation exits with code 124. Its exact input XML, partial outputs, `stdout.log`, `stderr.log`, and `morpheus_command.json` remain in the attempt folder for the agent to inspect. POSIX process groups isolate parallel Linux/WSL2 cleanup; Windows Job Objects preserve per-invocation timeout and process-tree cleanup for serial native Windows runs. Morpheus MCP tool calls default to 62 minutes, leaving cleanup/return headroom around the 60-minute simulation cap.

Before a confirmatory run, or after changing the model or upgrading the Codex SDK, use the opt-in compatibility smoke checks (these call Codex and are never run by the test suite):

```powershell
npm run smoke -- --subject --scorer
npm run smoke -- --subject --model gpt-6.1-sol --reasoning-effort xhigh
```

Both checks default to `gpt-6-luna` at `high`; `--model`, `--reasoning-effort`, `--scorer-model`, and `--scorer-reasoning-effort` override them. The subject check verifies tool use and strict output; the scorer check verifies image input and strict output. Each run writes a dated report with the software versions under ignored `smoke_reports/`.

## Reading the outputs

Each invocation creates a master directory such as `benchmark_runs/20260427_153012_benchmark/`. Inside that directory:

- `benchmark_summary.json`
  Aggregate result across processed papers, including total duration, token totals, and timing diagnostics.
- `benchmark_manifest.json`
  Run-level diagnostics and a compact list of paper runs.
- `benchmark_comparison.json` and `benchmark_comparison.csv`
  Mode-level comparison summaries across the selected capability modes.
- `benchmark_recovery.json` and `assignment_results/`
  Incremental configuration and job state, and independently committed assignment results, used to recover after a host crash.
- `<timestamp>_<paper-stem>/`
  One isolated working directory per benchmark paper and mode. Codex runs with this paper directory as its working directory, so it does not see sibling paper outputs.

Inside a paper run directory you will typically find:

- `run_manifest.json`
  Paths and metadata for the staged inputs and run outputs.
- `agent_workspace/`
  The isolated workspace used by the benchmark subject. This contains staged paper assets, agent-created scripts, agent attempt folders, and copied model artifacts.
- `codex_home/`
  Sanitized snapshot of the isolated Codex home used for audit.
- `subject_deadline.json` and `subject_execution.json`
  Authoritative deadlines, direct active-subject duration, and stop reason.
- `paper.txt`
  Extracted text from the benchmark PDF.
- `paper_visual_manifest.json`
  A lightweight index of likely figure and table pages in the PDF.
- `model.xml`
  The most recent Morpheus model produced by the agent.
- `xml_versions/`
  Captured and harvested model XML revisions, including per-attempt `model.xml` copies when available.
- `attempts/attempt_###/`
  Host-side canonical Morpheus attempt logs and generated outputs used for technical evaluation.
- `agent_workspace/.../attempt_###/attempt_reproduction.json`
  Agent-authored attempt-level reproduction self-score, when the mode can execute Morpheus during the agent turn.
- `technical_evaluation.json`
  Executability score and breakdown (not used in the preprint).
- `reproduction_report.json`
  The structured reproduction rubric returned by the agent.
- `transcripts/`
  The single subject interaction log (`subject.jsonl`) plus separate preflight logs when present. Biological scorer transcripts live next to their score files under `biological_scores/`.

Analysis uses the directly recorded `subjectExecutionMs`; it does not reconstruct time from session logs or add timeout upper bounds. Subject Morpheus attempts are counted from attempt folders containing `morpheus_command.json`; host technical reruns are reported separately. The per-run analysis also reports attempt folders missing `model.xml`, `attempt_reproduction.json`, or either execution log. Runs that invoked Morpheus through an absolute binary path are marked `launcher_bypass`, and their agent-side Morpheus timing is left blank. Aggregate outputs include ITT scores (unscoreable/missing subject outcomes contribute zero) and valid-only scores. For the biological ITT score, `model_failed` and `insufficient_evidence` count as zero, while scorer-side failures (`scoring_failed`) and runs that were never scored stay missing; `biological_itt_n` reports how many runs the ITT mean covers. Token usage comes from the subject's `turn.completed` event; time-limited or killed subjects never emit one, so their cumulative usage is read from the last `token_count` event in the subject's Codex session rollout. Reasoning tokens are part of output tokens and are priced once, as output.
`benchmark_execution_audit.csv` retains both an infrastructure-invalid original and its clean replacement; assignment-level outcome and duration columns select only the replacement.

## Benchmark behavior

- The benchmark uses local Codex authentication. It is intended to run with a locally authenticated Codex CLI rather than direct API-key billing in the harness.
- Live web search is available during benchmark runs when the agent genuinely needs outside information, but benchmark judgments should remain grounded in the staged paper assets, the Morpheus skill or MCP reference material, and the Morpheus outputs generated in the run directory.
- The agent is given paper text and a visual manifest up front. Paper page images are not attached by default; instead, agents render only the specific figure pages they need and inspect local PNGs directly with `view_image` when available.
- If `benchmark_focus/<paper-stem>.txt` exists, the runner adds it as the showcase/validation target and tells the agent to ground the model in the paper's mechanisms first rather than treating the focus as the sole design target.
- Agents can also sample representative Morpheus output images and inspect those local PNGs directly.
- The subject receives one continuous active-time budget. Morpheus attempts are individual executions within that budget. CLI modes must use the staged `morpheus` launcher rather than an absolute binary path so timing and attempt metadata are captured.
- For Morpheus-running modes, prompts ask agents to create a fresh attempt folder for each Morpheus attempt, copy the corresponding `model.xml` into that folder, inspect the outputs, and write `attempt_reproduction.json`.
- The technical score is deterministic, but the reproduction report is a structured qualitative assessment returned by the agent from the staged evidence.
- ITT averages over every assigned paper/mode/repetition are primary; valid-only averages are reported separately. XSD findings remain diagnostic only: benchmark acceptance uses well-formed XML, required sections, and the actual Morpheus runtime result.
- Results can vary between runs because the benchmark depends on an LLM-driven modeling loop. In practice, a one-paper smoke test is the best first check, and repeated full runs should be interpreted as distributions rather than perfectly fixed outputs.
- Queueing, preflight, independent biological scoring, and host technical evaluation are outside subject active time. Time limits and malformed final output are benchmark outcomes and are never relaunched; other Codex failures are infrastructure failures with at most one clean replacement, while quota and model-capacity refusals do not count toward that limit.

## Benchmark versions

`BENCHMARK_VERSION` in `src/benchmark/types.ts` identifies the subject-facing setup: the Morpheus skill, the docs-mode references (`morpheusml-doc.md`, `model-template.md`), the prompts, and the runner behavior. This release is version 3. The preprint uses runs of all three versions:

| Version | Protocol | Morpheus skill | Subject models | Use in the preprint |
| --- | --- | --- | --- | --- |
| v1 | `max_cycles_v1` | prototype | gpt-5.5, gpt-5.4-mini | gpt-5.5 runs scored by hand to validate the automated scorer |
| v2 | `time_limit_v2` | 1.3.0 | gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna | replication with the GPT-5.6 models |
| v3 | `time_limit_v2` | 1.5.1 | gpt-6.1-sol, gpt-6-luna | main results |

Version 1 used a different time limit: each Codex turn had a 90-minute wall-clock cap that the agent was not told about, and a timed-out turn restarted in a new thread that kept the workspace. Do not pool version 1 runs with later versions.

Runs record `benchmarkVersion` and `benchmarkProvenance` in `benchmark_recovery.json`, `benchmark_summary.json`, and `benchmark_manifest.json`. The provenance holds:

- the git commit, an exact-match tag, and a dirty-tree flag;
- SHA-256 hashes (with CRLF normalized) of each staged skill folder and the docs-mode references;
- `prompts`: SHA-256 hashes of the subject prompt builder (`src/benchmark/prompt.ts`), the MCP server whose instructions and tool descriptions agents read (`morpheus_mcp_server.py`), and the focus-prompt folder;
- `software`: Node, platform, installed and locked `@openai/codex-sdk`, Codex CLI, Morpheus version and revision, gnuplot, the benchmark Python, hashes of `package-lock.json` and `uv.lock`, and whether `node_modules` and `.venv` contain exactly the locked packages (`npmInstalledMatchesLock`, `pythonInstalledMatchesLock`).

Each run folder also keeps the exact rendered subject prompt as `subject_prompt.txt`. The runner warns at start when `node_modules` drifts from `package-lock.json` (run `npm ci`) or `.venv` from `uv.lock` (run `uv sync --locked`). Version 1 and 2 runs predate this stamping; the code infers their version from the protocol.

Version boundaries are enforced:

- `--recover-run` refuses to launch subject executions (missing assignments or infrastructure-failure replacements) when the run's version, skill hash, or prompt hashes differ from the current checkout. Version 1 and 2 runs can therefore be analyzed and rescored with this release but not relaunched. Software differences are logged as warnings, and deterministic postprocessing works across versions.
- `--combine-runs` rejects runs with different versions, skill hashes, or prompt hashes, and logs software differences.
- Analysis adds a `benchmark_version` column and refuses to pool mixed versions in one mode summary. `compare_benchmarks.py` refuses to compare runs from different benchmark versions unless `--force` is passed.
- The biological scorer always stages the current skill. It logs a warning when that skill differs from the one the run recorded.

To define a new version, see [Updating the Morpheus skill, prompts, or docs-mode references](SETUP.md#updating-the-morpheus-skill-prompts-or-docs-mode-references).

## Reproducibility of the published runs

The version 3 runs of the preprint (gpt-6.1-sol and gpt-6-luna) were made in the development repository at commit c945e84, tagged `benchmark-v3`; these identifiers appear in their recorded provenance. The recorded SHA-256 hashes of the Morpheus skill, the docs-mode references, `src/benchmark/prompt.ts`, `morpheus_mcp_server.py`, `benchmark_focus/`, `package-lock.json`, and `uv.lock` match the files in this release, so recovering or rerunning those runs with this release passes the runner's provenance checks. Changes after c945e84 concern job scheduling and recovery in the runner, the analysis and comparison scripts, the figure scripts, the tests, and the documentation; none of them touches a file that the benchmark subject sees.

## Citation and license

Please cite this software with the metadata in [CITATION.cff](CITATION.cff) and cite the accompanying preprint. The code is released under the Apache License 2.0 ([LICENSE](LICENSE)); files derived from Morpheus are distributed under the 3-clause BSD license of Morpheus ([NOTICE](NOTICE)). The bundled Morpheus skill in `.agents/skills/morpheus/` carries its own Apache-2.0 license file.
