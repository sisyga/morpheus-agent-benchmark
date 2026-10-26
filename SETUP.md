# Setup

This guide is written for someone who has not worked with this repository before. If your goal is simply to verify that the benchmark runs, follow the sections in order and start with a one-paper smoke test before attempting the full benchmark.

## 1. What you need

Required:

- [uv](https://docs.astral.sh/uv/getting-started/installation/) for Python installation and dependency management
- Python 3.11 or newer; `.python-version` selects 3.12 by default. `pyproject.toml` sets `python-preference = "only-managed"`, so uv downloads and uses its own interpreter rather than a system Python
- Node.js 18 or newer
- Morpheus installed and runnable from the command line
- gnuplot on `PATH`; Morpheus 2.4 segfaults on models with plot or logger output when it cannot find gnuplot
- Codex CLI installed and authenticated locally

Optional but recommended:

- `rg` / ripgrep on `PATH` for fast repository searches during agent runs and manual debugging
- Poppler tools on `PATH`
  - `pdftotext`
  - `pdftoppm`
  - `pdfimages`

If Poppler is not installed, the repository falls back to Python PDF tooling. The benchmark should still run, but PDF staging may be slower or less complete.

## 1a. Add the benchmark paper PDFs

The benchmark paper PDFs are not distributed with the repository. Download them from the DOIs in `benchmark_papers/papers.csv`, save them as `benchmark_papers/<stem>.pdf`, and verify them against the recorded checksums as described in [benchmark_papers/README.md](benchmark_papers/README.md). PDFs in that folder are ignored by git.

## 2. Choose your platform

Install uv before following your platform's setup steps. On Linux or WSL2:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On native Windows:

```powershell
winget install --id=astral-sh.uv -e
```

Open a new terminal if necessary and confirm `uv --version` works. See the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/) for other installation methods.

| Host | Benchmark jobs | Biological scoring jobs | Recommendation |
|---|---:|---:|---|
| Native Linux | Configurable | Configurable | Preferred for full runs |
| WSL2 | Configurable | Configurable | Preferred on Windows for full runs |
| Native Windows | Forced to 1 | Forced to 1 | Supported for review and small runs |

`--max-concurrent-jobs` and biological-scoring concurrency remain configurable on Linux and WSL2. On native Windows the runner records and logs an effective value of `1`, even if a larger value was requested. This does not limit Morpheus' own CPU thread count; use `--morpheus-num-threads` separately when that is needed.

Install Morpheus for the operating system in which the benchmark will actually run. The official [Morpheus download page](https://morpheus.gitlab.io/) provides Linux and Windows packages.

### Native Linux

From the repository root:

```bash
uv sync --locked
npm ci
npm install -g @openai/codex
codex login
codex login status
morpheus --help
```

On Ubuntu or Debian, `sudo apt-get install poppler-utils` installs the optional PDF command-line tools. If Morpheus is not on `PATH`, set `export MORPHEUS_BIN=/absolute/path/to/morpheus`.

### WSL2

Install WSL2 from an administrator PowerShell prompt, then enter the Linux shell:

```powershell
wsl --install
wsl
```

Clone the repository under the Linux home directory, not under `/mnt/c`:

```bash
mkdir -p ~/code
cd ~/code
git clone https://github.com/sisyga/morpheus-agent-benchmark.git
cd morpheus-agent-benchmark
uv sync --locked
npm ci
curl -fsSL https://chatgpt.com/codex/install.sh | sh
codex login
codex login status
morpheus --help
```

Install a Linux Morpheus build inside WSL. Do not reuse the Windows `.venv`, `node_modules`, Codex executable, or a Windows `morpheus.exe`. OpenAI's [WSL guidance](https://learn.chatgpt.com/docs/windows/wsl) likewise recommends keeping the checkout under `~/...` for Linux filesystem performance and permission behavior.

### Native Windows

Windows 11 is the recommended native Codex host; current Windows 10 support is best effort. From PowerShell in the repository root:

```powershell
uv sync --locked
npm ci
npm install -g @openai/codex
codex login
codex login status
morpheus --help
```

Activation is optional. Use `uv run --locked python ...` for Python scripts; the benchmark runner automatically uses the `.venv` created by uv. If Morpheus is installed outside `PATH`, set it for the current shell:

```powershell
$env:MORPHEUS_BIN = "D:\Programs\Morpheus\morpheus.exe"
```

Run Codex once and approve the administrator prompt that initializes the elevated native sandbox. The benchmark selects that sandbox automatically because its fine-grained filesystem permission profile is not compatible with the unelevated fallback. See OpenAI's [Windows sandbox setup and troubleshooting](https://learn.chatgpt.com/docs/windows/windows-sandbox).

Native Windows limitations:

- benchmark, recovery, and biological-scoring agent jobs are serial;
- long unattended runs are less robust because a crashing Windows Morpheus process can open a Windows Error Reporting dialog;
- if the elevated sandbox cannot be initialized because of local or enterprise policy, use WSL2 rather than the unelevated sandbox.

Poppler is optional on every platform. If it is unavailable, the benchmark falls back to Python PDF tooling.

## 3. Verify the repository before running the benchmark

`pyproject.toml` is the source of Python dependencies, and `uv.lock` records exact versions. `uv sync --locked` installs runtime packages and the default development group (including pytest) into the repo-root `.venv`. It recreates a `.venv` that was not built on a uv-managed interpreter, and it removes packages that are not declared in the lockfile, including `pip`. Python 3.11+ is required by the scientific dependencies.

Benchmark subjects run against this uv-controlled environment. The runner refuses to start unless `.venv/pyvenv.cfg` shows the venv was created by uv, and it grants the subject sandbox read-only access to `.venv` and to the uv-managed interpreter installation it points to. Subjects therefore get exactly the locked packages and cannot install or remove packages. On Linux and macOS, the runner also denies the resolved system interpreters it finds on `PATH` and in `/usr/bin`, `/usr/local/bin`, and `/bin`, plus their `lib/pythonX.Y` stdlib directories, so `python`, `python3`, and `/usr/bin/python3` inside the sandbox can only reach the uv environment. On merged-`/usr` Linux distributions the sandbox also exposes `/usr/lib` as `/lib`, so stdlib sources and `libpython` remain readable there, but no system interpreter binary can be executed. Native Windows does not apply these deny entries. To use a different interpreter version, rebuild the venv with uv (for example `uv sync --locked --python 3.11`); the same checks then apply.

These checks are fast and catch most setup problems:

```powershell
npm run typecheck
npm run test:ts
uv run --locked python -m pytest
```

You do not need to start `server.py` manually for the benchmark. The benchmark runner starts the MCP server automatically from `benchmark.config.json`.

### Updating Python dependencies

Use uv to update the manifest, lockfile, and local environment together:

```bash
uv add <package>
uv add --dev <test-or-development-package>
uv remove <package>
uv lock --upgrade-package <package>
uv sync --locked
```

Commit `pyproject.toml`, `uv.lock`, and `.python-version` when they change. Keep `.venv` and uv's cache out of Git. To change only your local interpreter, use `uv sync --locked --python 3.11`; to change the team's default, use `uv python pin <version>` and verify the environment and tests.

If an external tool needs a requirements file, generate one with `uv export --locked --no-dev --format requirements.txt --output-file /path/to/requirements.txt`.

## 4. Run a one-paper smoke test

This is the recommended first run:

```powershell
npm run benchmark -- --max-papers 1
```

This command scans `benchmark_papers/`, takes the first PDF in sorted order, and creates one timestamped benchmark directory under `benchmark_runs/`.

If the smoke test works, you should see:

- a new folder such as `benchmark_runs/20260427_153012_benchmark/`;
- `benchmark_summary.json` and `benchmark_manifest.json` inside that benchmark folder;
- one paper-specific subfolder inside the benchmark folder;
- `paper.txt` and `paper_visual_manifest.json`;
- a generated `model.xml`;
- Morpheus logs under host `attempts/attempt_###/` and, for agent-run attempts, under `agent_workspace/.../attempt_###/`;
- `technical_evaluation.json`;
- `reproduction_report.json`;
- transcript files under `transcripts/`;

## 5. Run the full benchmark

Once the smoke test succeeds:

```powershell
npm run benchmark
```

Useful variants:

```powershell
npm run benchmark -- --help
npm run benchmark -- --max-papers 3
npm run benchmark -- --benchmark-mode python_web
npm run benchmark -- --all-benchmark-modes
npm run benchmark -- --total-time-limit-minutes 300 --finalization-reserve-minutes 10
npm run benchmark -- --repetitions 3
npm run benchmark -- --all-benchmark-modes --max-concurrent-jobs 5
npm run benchmark -- --results-dir benchmark_runs_review
npm run benchmark -- --model gpt-6.1-sol --reasoning-effort xhigh
npm run benchmark -- --score-biological
npm run benchmark -- --score-biological --skip-scored-attempts
npm run benchmark -- --no-analysis
```

The default runner concurrency is one job at a time. On Linux and WSL2, paper/mode/repetition jobs are independent, so `--max-concurrent-jobs` can shorten full benchmark runs when the machine has enough CPU/RAM and Codex quota headroom. Native Windows always runs these jobs serially. Each job gets one continuous subject execution. Only a classified infrastructure failure can receive one clean replacement, which uses a new thread and empty workspace.

## 5a. CLI options and recovery

`npm run benchmark -- --help` lists every option. The [benchmark CLI reference](readme.md#benchmark-cli-reference) in the README describes each one, including how `--recover-run` reruns infrastructure failures and quota-stopped assignments and which runs `--combine-runs` accepts.

## 6. Understand the configuration

The default configuration is stored in `benchmark.config.json`:

```json
{
  "papersDir": "benchmark_papers",
  "resultsDir": "benchmark_runs",
  "benchmarkFocusDir": "benchmark_focus",
  "benchmarkModes": ["morpheus_mcp"],
  "benchmarkRepetitions": 1,
  "model": "gpt-6.1-sol",
  "reasoningEffort": "xhigh",
  "totalTimeLimitMs": 14400000,
  "finalizationReserveMs": 600000,
  "maxConcurrentJobs": 1,
  "pageRenderDpi": 150,
  "representativeOutputFrames": 5,
  "codexApprovalPolicy": "never",
  "codexAllowedEnvVars": [],
  "biologicalScoringCriteriaPath": "biological_scoring_criteria.json",
  "biologicalScoringModel": "gpt-6-luna",
  "biologicalScoringReasoningEffort": "high",
  "biologicalScoringMaxConcurrentJobs": 1,
  "biologicalScoringTurnTimeoutMs": 5400000,
  "mcpCommand": ["python", "server.py"],
  "mcpToolTimeoutMs": 3720000,
  "bridgeToolTimeoutMs": 3720000,
  "morpheusRunTimeoutMs": 3600000,
  "morpheusNumThreads": 1,
  "morpheusXmlSchemaPath": "src/benchmark/MorpheusML.xsd",
  "skillPaths": [".agents/skills/morpheus/SKILL.md"]
}
```

Important fields:

- `papersDir`
  Folder scanned for benchmark PDFs. The default `benchmark_papers/` corpus is not distributed; see `1a. Add the benchmark paper PDFs` after cloning.
- `resultsDir`
  Parent folder where each benchmark invocation creates a timestamped master directory. Paper run directories and benchmark-level diagnostics are written inside that master directory.
- `benchmarkFocusDir`
  Optional folder of per-paper focus prompts. Set to `null` or use `--no-benchmark-focus` to disable focus prompts.
- `benchmarkModes`
  Capability modes to run for each paper. The default `morpheus_mcp` is the full harness. Use `--all-benchmark-modes` to compare `python_web`, `morpheus_cli`, `morpheus_cli_docs`, `morpheus_skill`, and `morpheus_mcp`.
- `benchmarkRepetitions`
  Number of independent repetitions for every paper/mode combination. Use this for variance estimates and statistical comparisons.
- `totalTimeLimitMs`
  Total active subject time for one paper/mode/repetition. Default: 4 hours. Override with `--total-time-limit-minutes`.
- `finalizationReserveMs`
  Portion of the total budget reserved for inspection and finalization. New Morpheus starts are refused after the derived soft cutoff. Default: 10 minutes.
- `maxConcurrentJobs`
  Maximum independent paper/mode jobs to run in parallel on Linux and WSL2. Native Windows clamps the effective value to `1` and records that effective value in benchmark artifacts.
- `pageRenderDpi`
  Preferred resolution suggested to the agent when it renders specific paper pages for visual inspection.
- `representativeOutputFrames`
  Preferred number of Morpheus output images the agent should sample for visual inspection.
- `codexApprovalPolicy`
  Codex approval policy used for benchmark subject sessions.
- `codexAllowedEnvVars`
  Additional non-secret host environment variable names to pass into benchmark-subject Codex agents. The default is `[]`; API keys, token/secret-style variables, and broad Morpheus host state are not inherited by default. Use this only for local tooling flags or paths that the benchmark agent genuinely needs.
- `biologicalScoringCriteriaPath`
  Versioned JSON criteria registry for opt-in biological scoring. It is a runtime copy synchronized from the clause tables of `Biological_scoring_criteria_v7.xlsx` (one sheet per paper); the benchmark does not open the workbook during scoring. Clause results are boolean, and a paper's score is the passed clause weight divided by its total weight, with weights taken from the workbook's Weight column. Check synchronization with `uv run --locked python sync_biological_scoring_criteria.py` and refresh it with `uv run --locked python sync_biological_scoring_criteria.py --update`.
- `biologicalScoringModel`, `biologicalScoringReasoningEffort`
  Model and reasoning effort used for independent biological scoring agents.
- `biologicalScoringMaxConcurrentJobs`
  Maximum parallel biological scoring sessions on Linux and WSL2. Native Windows clamps the effective value to `1`.
- `biologicalScoringTurnTimeoutMs`
  Timeout for one biological scoring Codex turn.
- `mcpCommand`
  Command used to start the MCP server.
- `mcpToolTimeoutMs`
  Per-call timeout for Morpheus MCP tools. The default is 62 minutes, leaving two minutes for the server to clean up and return after the one-hour Morpheus execution timeout.
- `bridgeToolTimeoutMs`
  Timeout for host-side Python bridge subprocesses.
- `morpheusRunTimeoutMs`
  Maximum for each CLI or MCP Morpheus simulation. The runner clamps it to the remaining time before the soft cutoff. On timeout, exit code 124 is returned and exact XML, partial outputs, stdout/stderr, and `morpheus_command.json` remain inspectable.
- `morpheusNumThreads`
  Optional baseline thread count for Morpheus executions. The host technical rerun reuses the recorded thread count from the newest successful agent attempt whose copied XML exactly matches the canonical model, which also preserves the XML's `RandomSeed`. If no matching count is available, the host uses this setting. The checked-in config uses `1`; `null` (also the value when the field is omitted) preserves Morpheus' own `OMP_NUM_THREADS`/auto behavior as the fallback.
- `morpheusXmlSchemaPath`
  MorpheusML XSD path used for non-blocking schema diagnostics. Benchmark acceptance uses XML well-formedness, required-section checks for `version="4"`, `Description`, `Space`, `Time`, and `Analysis`, and the actual Morpheus runtime result.
- `skillPaths`
  Skills enabled for the Codex run. Each skill folder is copied into the job's `codex_home` when the job starts, and its SHA-256 is recorded in the run's `benchmarkProvenance`.

### Updating the Morpheus skill, prompts, or docs-mode references

Subject prompts (`src/benchmark/prompt.ts`), MCP server instructions (`morpheus_mcp_server.py`), and `benchmark_focus/` are hashed into each run's provenance like the skill. Changing any of them is also a new benchmark version.

The MCP server reads `.agents/skills/morpheus/references/*-examples.md` live, and every job copies the skill when it starts. Swap files only while no benchmark, recovery, or scoring job is running, and treat every swap as a new benchmark version:

1. Tag the commit that produced the current version's runs: `git tag -a benchmark-v<N> <commit> -m "..."`. Prefer tags over branches; branches move.
2. Bump `BENCHMARK_VERSION` in `src/benchmark/types.ts`.
3. Replace the skill folder as a whole so stale files do not linger: `rsync -a --delete <published-skill>/ .agents/skills/morpheus/`.
4. Keep the paths the code expects: the folder name `morpheus`, `references/morpheusml-doc.md` and `references/model-template.md` (staged for `morpheus_cli_docs`), and the five `references/{cpm,pde,ode,multiscale,miscellaneous}-examples.md` files (MCP `list_references`/`read_reference`). Renamed or added reference files need matching code changes.
5. Run `npm run typecheck`, `npm run test:ts`, and `uv run --locked python -m pytest tests`, then do a one-paper smoke run for `morpheus_cli_docs` and `morpheus_mcp`, and check `agent_workspace/morpheusml_doc.txt` and `codex_home/skills/morpheus/`.
6. Commit, start fresh benchmark runs from a clean tree (the runner warns about uncommitted changes), and tag the release commit `benchmark-v<N+1>`.

## 6a. Direct MCP use

Outside the benchmark, start the MCP server over stdio with `uv run --locked python server.py` from the repository root, or let an MCP client read the repo-root `.mcp.json`. See [Direct MCP usage](readme.md#direct-mcp-usage) in the README.

## 7. Read the outputs

The main files to inspect are:

- `benchmark_runs/<timestamp>_benchmark/benchmark_summary.json`
  Aggregate result across all processed papers, including total duration, token totals, and timing diagnostics.
- `benchmark_runs/<timestamp>_benchmark/benchmark_manifest.json`
  Run-level diagnostics and a compact list of paper run IDs, paths, statuses, and scores.
- `benchmark_runs/<timestamp>_benchmark/benchmark_comparison.json`
  Mode-level comparison summary.
- `benchmark_runs/<timestamp>_benchmark/benchmark_comparison.csv`
  Spreadsheet-friendly mode-level comparison summary.
- `benchmark_runs/<timestamp>_benchmark/<paper_run_dir>/run_manifest.json`
  File map for that paper run.
- `benchmark_runs/<timestamp>_benchmark/<paper_run_dir>/subject_prompt.txt`
  Exact rendered prompt given to the benchmark subject.
- `benchmark_runs/<timestamp>_benchmark/<paper_run_dir>/agent_workspace/`
  Isolated workspace used by the benchmark subject. This contains staged paper assets, agent-created scripts, and agent attempt folders.
- `benchmark_runs/<timestamp>_benchmark/<paper_run_dir>/codex_home/`
  Sanitized audit snapshot of the isolated Codex home.
- `benchmark_runs/<timestamp>_benchmark/<paper_run_dir>/subject_deadline.json`
  Exact total, soft cutoff, and hard cutoff.
- `benchmark_runs/<timestamp>_benchmark/<paper_run_dir>/subject_execution.json`
  Direct active-subject duration and stop reason.
- `benchmark_runs/<timestamp>_benchmark/<paper_run_dir>/model.xml`
  Final Morpheus model produced for the paper.
- `benchmark_runs/<timestamp>_benchmark/<paper_run_dir>/xml_versions/`
  Captured and harvested model XML revisions.
- `benchmark_runs/<timestamp>_benchmark/<paper_run_dir>/technical_evaluation.json`
  0-7 executability score (not used in the preprint).
- `benchmark_runs/<timestamp>_benchmark/<paper_run_dir>/reproduction_report.json`
  Structured 0-8 reproduction rubric.
- `benchmark_runs/<timestamp>_benchmark/<paper_run_dir>/biological_scores/scorer-v...json`
  Optional 0-1 biological score generated by `--score-biological` or `npm run score:biology -- <benchmark_dir>`. The path encodes scorer, criteria, and attempt provenance, so a new scorer cohort does not overwrite earlier scores. Each scorer works read-only with the canonical attempt as its sole scoring target. It can inspect the run's `agent_workspace` and the staged Morpheus skill only to interpret assets referenced by the canonical `model.xml`; outputs and alternative models there are not scoring evidence. Network access, web search, plugins, and Morpheus MCP tools remain disabled. Failed canonical simulations without scoreable output receive `model_failed` and score zero without invoking a scoring agent. Missing evidence without an explicit execution failure receives `insufficient_evidence` and a null score. Partial runs with scoreable output receive credit for demonstrated behavior, using the last observed state for endpoint clauses. Use `--skip-scored-attempts` to reuse scores only when the canonical attempt, scorer version, model, effort, criteria, and artifact identity match. The standalone scorer accepts `--model`, `--reasoning-effort`, `--max-concurrent-jobs`, `--criteria-path`, `--turn-timeout-ms`, and `--skip-scored-attempts` for scoring-agent overrides.
- `benchmark_runs/<timestamp>_benchmark/<paper_run_dir>/biological_scores/scorer-v...txt`
  Human-readable companion to that scorer-cohort JSON.
- `benchmark_runs/<timestamp>_benchmark/<paper_run_dir>/biological_scores/scorer-v.../`
  Same-named folder with that scorer's `transcript.jsonl` and `codex_home/` snapshot. The score JSON links them as `scorerTranscriptPath` and `scorerCodexHomePath`; the subject's `codex_home/` snapshot is never overwritten by scoring.
- `benchmark_runs/<timestamp>_benchmark/<paper_run_dir>/attempts/attempt_###/stdout.log`
  Attempt-scoped Morpheus standard output.
- `benchmark_runs/<timestamp>_benchmark/<paper_run_dir>/attempts/attempt_###/stderr.log`
  Attempt-scoped Morpheus errors and warnings.
- `benchmark_runs/<timestamp>_benchmark/<paper_run_dir>/transcripts/`
  Single subject transcript (`subject.jsonl`) plus separate preflight transcripts. Scorer transcripts live under `biological_scores/`.

Codex uses the paper-specific `agent_workspace` as its working directory, so one paper agent does not see sibling paper outputs from the same benchmark invocation. The runner prepares a mode-specific isolated `codex_home`, including allowed skills, MCP config, and sandbox trust root. Analysis uses direct `subjectExecutionMs` without timeout imputation and reports Morpheus, host-evaluation, cache-read, and cache-write usage separately. Subject attempts are counted only when their folders contain `morpheus_command.json`; host technical reruns are excluded. The per-run CSV reports missing attempt XML, reproduction report, and logs. ITT averages treat missing/unscoreable subject outcomes as zero; valid-only averages are secondary. For biological ITT, `model_failed` and `insufficient_evidence` count as zero, while `scoring_failed` and never-scored runs stay missing (`biological_itt_n` gives the covered count). Time-limited or killed subjects never emit `turn.completed`, so their token usage is read from the subject's Codex session rollout; reasoning tokens are part of output tokens and are priced once.
The trusted Morpheus launcher is staged outside the writable subject workspace, and the real executable directory is removed from the subject `PATH`. `benchmark_recovery.json` plus per-assignment result files allow recovery even if the final summary was not written; ambiguous subject state is retained as infrastructure-invalid and receives at most one clean replacement. Analysis writes `benchmark_execution_audit.csv` with both executions while assignment metrics select the replacement only.

The benchmark is text-first. It does not attach all page images or all Morpheus output images up front. Instead:

- the agent reads `paper.txt` first;
- if it needs figures or tables, it uses `paper_visual_manifest.json` to choose specific pages and renders only those pages;
- if it needs Morpheus visual output, it samples representative output images;
- the agent inspects local PNGs directly with `view_image` when available.

Morpheus attempts are executions of `run_morpheus_model(...)` or CLI Morpheus runs inside the continuous active-time budget. CLI modes must use the staged `morpheus` command; absolute Morpheus binary paths bypass capture and are flagged in analysis with agent-side Morpheus timing left blank. For Morpheus-running modes, the prompt asks the agent to use fresh attempt folders, copy the corresponding `model.xml`, inspect outputs, including partial outputs preserved after a timeout, and write `attempt_reproduction.json` with four 0-2 self-scores.

## 7a. Generate analysis figures

The benchmark CLI runs analysis automatically after normal runs, manual recovery runs, and combined-run creation unless `--no-analysis` is set. To regenerate the analysis outputs manually, run:

```powershell
uv run --locked python analyze_benchmark.py benchmark_runs/<timestamp>_benchmark
```

The default output folder is:

```text
benchmark_runs/<timestamp>_benchmark/analysis_figures/
```

Useful analysis options:

```powershell
uv run --locked python analyze_benchmark.py benchmark_runs/<timestamp>_benchmark --out-dir analysis_review
uv run --locked python analyze_benchmark.py benchmark_runs/<timestamp>_benchmark --formats png svg pdf
```

The script writes run-level, mode-level, and paper-cohort-by-mode CSVs; token-cost and API-dollar cost-quality summaries; score heatmaps and box plots; stacked runtime, token-use, API-cost-component, and outcome charts; token-cost and API-cost Pareto plots for mixed normalized quality and, when available, biological score; and attempt self-score trajectories. Attempt trajectories use `attempt_reproduction.json` files from agent attempt folders. Missing JSON in an attempt folder leaves that attempt unscored (blank) rather than inventing zero self-scores.

When biological score files exist, analysis also writes `benchmark_biological_scores.csv`, includes biological score columns in run/mode CSVs, adds biological heatmaps, and folds the normalized biological score into cost-quality summaries.

### Compare benchmark models

To compare complete benchmark folders produced by different models, run:

```powershell
uv run --locked python compare_benchmarks.py benchmark_runs/<first>_benchmark benchmark_runs/<second>_benchmark [benchmark_runs/<third>_benchmark ...] --out-dir benchmark_model_comparison
```

If `--out-dir` is omitted, outputs go to `benchmark_comparison_figures/` in the current directory. The README section [Analysis figures](readme.md#analysis-figures) lists the figures, confidence intervals, and statistical tests the script writes.

## 8. Common setup failures

`uv` command not found:

- Install uv using the platform instructions above and open a new terminal.

The benchmark refuses to start with `.venv was not created by uv` or `No project .venv was found`:

- Run `uv sync --locked` from the repository root. It rebuilds `.venv` on a uv-managed interpreter.

Python scripts cannot import a project dependency:

- Run `uv sync --locked` from the repository root.
- Use `uv run --locked python ...` instead of a system Python interpreter. Activation is optional.

`codex` command not found:

- Install Codex CLI, then rerun `codex login`.

`codex login status` shows that you are not authenticated:

- Run `codex login` and complete the local login flow.

Native Windows reports `unelevated restricted-token sandbox cannot enforce split filesystem read restrictions`:

- Initialize the elevated Codex sandbox and approve its administrator prompt.
- If machine policy blocks elevated sandbox setup, run the benchmark in WSL2.

Native Windows reports `CreateProcessWithLogonW error 1326`:

- Retry the elevated sandbox setup and check the Codex sandbox log under `CODEX_HOME/.sandbox/sandbox.log`.
- Confirm that local policy permits the sandbox accounts and their required logon rights.
- Use WSL2 if the machine is centrally managed and those rights cannot be granted.

`morpheus` command not found:

- Install Morpheus or set `MORPHEUS_BIN` to the executable path.

The benchmark starts but fails while staging PDFs:

- Install Poppler if possible.
- If Poppler is unavailable, confirm that `uv sync --locked` completed successfully and that the runner is using the repo-root `.venv`.

The benchmark creates a run folder but Morpheus does not complete:

- Inspect the latest `attempts/attempt_###/stdout.log`, `attempts/attempt_###/stderr.log`, and `technical_evaluation.json` in that run directory.
- Check whether the generated `model.xml` is syntactically valid and whether Morpheus reported XML or runtime errors.

The smoke test works but the full benchmark is slow:

- That is expected. Each paper receives up to the configured total active-time limit and may run several Morpheus attempts.
- Use `--max-papers` first to measure behavior on your machine before running the full set.
- On native Windows, jobs intentionally remain serial; use Linux or WSL2 for parallel benchmark and scoring jobs.

## 9. What you do not need to do

- Apart from adding the paper PDFs, you do not need to move files around before running the benchmark.
- You do not need to launch `server.py` separately for the benchmark path.
