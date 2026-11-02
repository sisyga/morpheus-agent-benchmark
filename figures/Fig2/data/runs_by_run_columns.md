# Columns of runs_by_run.csv

One row per run of the two final benchmarks, in the order compare_benchmarks.py loads them. Read floats with `float_precision="round_trip"`.

| Column | Description |
|---|---|
| `benchmark_label` | Model label used in the figures |
| `agent_model` | Subject (agent) model |
| `agent_reasoning_effort` | Subject reasoning effort |
| `paper` | Paper PDF |
| `paper_short` | Short paper name |
| `paper_number` | Paper number |
| `mode` | Tool mode |
| `repetition` | Repetition (1-based) |
| `in_figures` | False if the run never started (no tokens, no cost) and is left out of every figure |
| `stop_reason` | Why the subject stopped (agent_finished or time_limit) |
| `artifact_status` | Status of the final model artifacts |
| `biological_score` | Biological score from the scoring agent (0-1; empty if not scored) |
| `biological_scoring_status` | Scoring-agent status (scored, insufficient_evidence, ...) |
| `biological_score_itt` | Biological score as plotted: intention-to-treat, unscored subject failures count as 0 |
| `reproduction_score` | Agent self-score of its reproduction (0-8) |
| `technical_score` | Technical score from the host checks (0-7; empty if not evaluated) |
| `technical_score_itt` | Technical score as plotted: intention-to-treat, unevaluated runs count as 0 |
| `manual_biological_score` | Manual biological score, where one exists (none for the version 3 runs) |
| `attempts` | Model revisions (plotted as revisions) |
| `subject_active_time_min` | Subject wall-clock time in minutes (plotted as active time) |
| `budget_fraction` | Subject time as a fraction of the time limit |
| `morpheus_time_min` | Summed Morpheus simulation time in minutes; concurrent simulations add up, so it can exceed wall-clock time; empty if the agent bypassed the launcher |
| `launcher_bypass` | True if the agent ran the Morpheus binary directly, so simulation time was not recorded |
| `uncached_input_tokens_m` | Uncached input tokens (millions) |
| `cached_input_tokens_m` | Cached input tokens (millions) |
| `cache_write_input_tokens_m` | Cache-write input tokens (millions) |
| `output_reasoning_tokens_m` | Output tokens including reasoning tokens (millions) |
| `total_tokens_m` | All tokens (millions) |
| `uncached_input_cost_usd` | Cost of uncached input tokens (USD) |
| `cached_input_cost_usd` | Cost of cached input tokens (USD) |
| `cache_write_input_cost_usd` | Cost of cache-write input tokens (USD) |
| `output_reasoning_cost_usd` | Cost of output tokens (USD) |
| `total_cost_usd` | API cost of the run (USD, as plotted) |
| `scorer_model` | Scoring-agent model |
| `scorer_reasoning_effort` | Scoring-agent reasoning effort |
| `scorer_version` | Scorer version (the criteria version is in scorer_cohort) |
| `benchmark_id` | Benchmark folder |
| `protocol` | Benchmark protocol |
| `total_time_limit_ms` | Time limit per run (ms) |
| `benchmark_version` | Benchmark version (subject-facing setup) |
| `scorer_cohort` | Scorer version, model, reasoning effort and criteria hash |
