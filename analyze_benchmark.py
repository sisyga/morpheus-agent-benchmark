from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd


MODE_ORDER = ["python_web", "morpheus_cli", "morpheus_cli_docs", "morpheus_skill", "morpheus_mcp"]
MODE_LABELS = {
    "python_web": "Python + web",
    "morpheus_cli": "Morpheus CLI",
    "morpheus_cli_docs": "Morpheus CLI + docs",
    "morpheus_skill": "Skill + CLI",
    "morpheus_mcp": "Morpheus MCP",
}
MODE_COLORS = {
    "python_web": "#0072B2",
    "morpheus_cli": "#E69F00",
    "morpheus_cli_docs": "#009E73",
    "morpheus_skill": "#D55E00",
    "morpheus_mcp": "#000000",
}
SCORE_COLORS = {
    "Technical": "#3366AA",
    "Reproduction (self-reported)": "#CC6677",
    "Biological": "#117733",
    "Biological (scoring agent)": "#117733",
    "Biological (manual)": "#44AA66",
}
MANUAL_BIOLOGICAL_SCORE_FILE = "manual_biological_scores.csv"
MANUAL_BIOLOGICAL_SCORE_COLUMNS = {"canonical_paper_stem", "mode", "repetition", "manual_score"}
BIOLOGICAL_SCORE_SPECS = [
    {
        "label": "Biological (scoring agent)",
        "point_col": "biological_score",
        "mean_col": "biological_mean",
        "std_col": "biological_std",
        "title": "Biological score (scoring agent)",
        "box_ylabel": "Biological score",
    },
    {
        "label": "Biological (manual)",
        "point_col": "manual_biological_score",
        "mean_col": "manual_biological_mean",
        "std_col": "manual_biological_std",
        "title": "Biological score (manual)",
        "box_ylabel": "Manual biological score",
    },
]
SCORE_BOX_SPECS = [
    {
        "point_col": "technical_score",
        "divisor": 7.0,
        "ylabel": "Technical score / 7",
    },
    {
        "point_col": "reproduction_score",
        "divisor": 8.0,
        "ylabel": "Reproduction score (self-reported) / 8",
    },
]
QUALITY_SCORE_YLABEL = "Mean biological score (scoring agent)"
QUALITY_SCORE_FALLBACK_NOTE = (
    "Small points: runs; circle: mean; diamond: median. Falls back to self-reported\n"
    "reproduction score where the biological score is unscored."
)
TOKEN_COLORS = {
    "Cached input": "#88CCEE",
    "Cache write input": "#CCBB44",
    "Uncached input": "#4477AA",
    "Output (incl. reasoning)": "#EE7733",
}
TIME_COMPONENT_COLORS = {
    "Morpheus running": "#66A61E",
    "Agent only": "#7570B3",
    "Timeout duration (upper bound)": "#D95F02",
}
COST_COMPONENT_COLUMNS = [
    "cached_input_cost_usd",
    "cache_write_input_cost_usd",
    "uncached_input_cost_usd",
    "output_reasoning_cost_usd",
    "total_cost_usd",
]
OPENAI_API_PRICING_SOURCE_URL = "https://developers.openai.com/api/docs/pricing"
OPENAI_API_PRICING_USD_PER_1M_TOKENS = {
    # Standard tier, short context, as listed on OPENAI_API_PRICING_SOURCE_URL on 2026-10-02.
    "gpt-6-astra": {
        "input": 10.0,
        "cached_input": 1.0,
        "output": 50.0,
        "pricing_tier_note": "standard input tier up to 272K tokens",
    },
    "gpt-6.1-sol": {
        "input": 2.0,
        "cached_input": 0.1,
        "output": 10.0,
        "pricing_tier_note": "standard input tier up to 272K tokens",
    },
    "gpt-6-sol": {
        "input": 2.0,
        "cached_input": 0.2,
        "output": 10.0,
        "pricing_tier_note": "standard input tier up to 272K tokens",
    },
    "gpt-6-luna": {
        "input": 0.1,
        "cached_input": 0.01,
        "output": 0.5,
        "pricing_tier_note": "standard input tier up to 272K tokens",
    },
    # Promotional price, active since 2026-08-22 (archived pricing page) and at least through 2026-11-21.
    # Before that it was $5.00 / $0.50 / $30.00; the benchmark v2 gpt-5.6-sol run started 2026-08-25.
    "gpt-5.6-sol": {
        "input": 4.0,
        "cached_input": 0.4,
        "output": 20.0,
        "pricing_tier_note": "standard input tier up to 272K tokens; promotional pricing",
    },
    "gpt-5.6-terra": {
        "input": 2.0,
        "cached_input": 0.2,
        "output": 12.0,
        "pricing_tier_note": "standard input tier up to 272K tokens",
    },
    "gpt-5.6-luna": {
        "input": 0.2,
        "cached_input": 0.02,
        "output": 1.2,
        "pricing_tier_note": "standard input tier up to 272K tokens",
    },
    "gpt-5.5": {
        "input": 5.0,
        "cached_input": 0.5,
        "output": 30.0,
        "pricing_tier_note": "standard input tier up to 272K tokens",
    },
    "gpt-5.4-mini": {
        "input": 0.75,
        "cached_input": 0.075,
        "output": 4.5,
        "pricing_tier_note": "",
    },
}
PAPER_COHORT_LABELS = {
    "papers_01_10": "Papers 1-10 (modeling keywords)",
    "papers_11_15": "Papers 11-15 (biology abstraction)",
    "unclassified": "Unclassified papers",
}
PAPER_COHORT_VIEW_LABELS = {
    "all": "All papers (1-15)",
    "papers_01_10": PAPER_COHORT_LABELS["papers_01_10"],
    "papers_11_15": PAPER_COHORT_LABELS["papers_11_15"],
}
PAPER_COHORT_VIEW_ORDER = ["all", "papers_01_10", "papers_11_15"]
MAX_FALLBACK_DURATION_MS = 12 * 60 * 60 * 1000
SUBJECT_ATTRIBUTABLE_UNSCORED_BIOLOGICAL_STATUSES = frozenset({"insufficient_evidence"})
ATTEMPT_SCORE_FIELDS = [
    "source_coverage",
    "mechanism_mapping",
    "observable_alignment",
    "parameter_plausibility",
]
ATTEMPT_COLUMNS = [
    "paper",
    "paper_short",
    "mode",
    "mode_label",
    "run_id",
    "repetition",
    "status",
    "attempt_number",
    "reported_attempt",
    "folder_attempt",
    "timestamp",
    "iteration",
    "source_coverage",
    "mechanism_mapping",
    "observable_alignment",
    "parameter_plausibility",
    "self_score",
    "normalized_self_score",
    "comment",
    "attempt_json_path",
    "attempt_dir",
]
MORPHEUS_ATTEMPT_LOG_NAMES = (
    "stdout.log",
    "stdout_stderr.txt",
    "morpheus_console.txt",
    "stderr.log",
)
MORPHEUS_LOG_TAIL_BYTES = 512 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create summary plots and tables for a Morpheus benchmark_summary.json run."
    )
    parser.add_argument(
        "benchmark_dir",
        nargs="?",
        default="benchmark_runs/20260509_benchmark_full",
        help="Benchmark folder containing benchmark_summary.json.",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory. Defaults to <benchmark_dir>/analysis_figures.",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["png", "pdf", "svg"],
        choices=["png", "pdf", "svg"],
        help="Figure formats to write.",
    )
    return parser.parse_args()


def load_summary(benchmark_dir: Path) -> dict:
    summary_path = benchmark_dir / "benchmark_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing benchmark summary: {summary_path}")
    return json.loads(summary_path.read_text(encoding="utf8"))


def load_json_artifact(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(encoding="cp1252")
    return json.loads(text)


def paper_short_name(paper: str) -> str:
    stem = Path(paper).stem
    stem = re.sub(r"_(clean|short)$", "", stem)
    stem = re.sub(r"^\d+_", "", stem)
    return stem.replace("_", " ")


def paper_number_from_name(paper: object) -> float:
    stem = Path(str(paper or "")).stem
    match = re.match(r"^(\d+)(?:[_\W]|$)", stem)
    if not match:
        return np.nan
    return float(int(match.group(1)))


def paper_cohort_from_number(paper_number: object) -> str:
    if pd.isna(paper_number):
        return "unclassified"
    number_value = int(float(paper_number))
    if 1 <= number_value <= 10:
        return "papers_01_10"
    if 11 <= number_value <= 15:
        return "papers_11_15"
    return "unclassified"


def ensure_paper_cohort_columns(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    if "paper_number" not in work.columns:
        if "paper" in work.columns:
            work["paper_number"] = work["paper"].map(paper_number_from_name)
        else:
            work["paper_number"] = np.nan
    if "paper_cohort" not in work.columns:
        work["paper_cohort"] = work["paper_number"].map(paper_cohort_from_number)
    if "paper_cohort_label" not in work.columns:
        work["paper_cohort_label"] = work["paper_cohort"].map(PAPER_COHORT_LABELS).fillna(
            PAPER_COHORT_LABELS["unclassified"]
        )
    return work


def benchmark_version(summary: dict) -> int:
    """Return the stamped benchmark version, inferring 1/2 for runs written before versions were stamped."""
    version = summary.get("benchmarkVersion")
    if isinstance(version, int) and not isinstance(version, bool):
        return version
    return 2 if summary.get("benchmarkProtocol") == "time_limit_v2" else 1


def records_from_summary(summary: dict, benchmark_dir: Path | None = None) -> pd.DataFrame:
    records = []
    explicit_benchmark_dir = benchmark_dir or summary.get("benchmarkRunDir")
    summary_benchmark_dir = Path(explicit_benchmark_dir or "").resolve()
    manual_scores = load_manual_biological_scores(summary_benchmark_dir) if explicit_benchmark_dir else {}
    turn_timeout_ms = number((summary.get("config") or {}).get("codexTurnTimeoutMs"))
    summary_protocol = summary.get("benchmarkProtocol") or "max_cycles_v1"
    summary_benchmark_version = benchmark_version(summary)
    for result in summary.get("results", []):
        paper = result.get("paper")
        mode = result.get("mode")
        repetition = result_repetition(result)
        paper_number = paper_number_from_name(paper)
        paper_cohort = paper_cohort_from_number(paper_number)
        diagnostics = result.get("diagnostics") or {}
        tokens = (
            subject_transcript_tokens_from_result(result, summary_benchmark_dir)
            or subject_session_tokens_from_result(result, summary_benchmark_dir)
            or diagnostics.get("tokens")
            or {}
        )
        input_tokens = number(tokens.get("input"))
        cached_tokens = number(tokens.get("cachedInput"))
        cache_write_tokens = number(tokens.get("cacheWriteInput"))
        output_tokens = number(tokens.get("output"))
        uncached_tokens = max(0.0, input_tokens - cached_tokens - cache_write_tokens)
        cached_input_tokens_m = cached_tokens / 1_000_000.0
        cache_write_input_tokens_m = cache_write_tokens / 1_000_000.0
        uncached_input_tokens_m = uncached_tokens / 1_000_000.0
        # Codex reports reasoning tokens as a subset of output_tokens (total = input + output).
        output_reasoning_tokens_m = output_tokens / 1_000_000.0
        agent_model = agent_model_from_result(result, summary)
        token_costs = token_costs_usd(
            agent_model,
            cached_input_tokens_m,
            cache_write_input_tokens_m,
            uncached_input_tokens_m,
            output_reasoning_tokens_m,
        )
        recorded_morpheus_ms = number(diagnostics.get("morpheusSimulationTimeMs"))
        host_morpheus_ms = number(diagnostics.get("hostMorpheusRunTimeMs"))
        agent_analysis_ms = number(diagnostics.get("agentAnalysisTimeMs"))
        host_eval_ms = number(diagnostics.get("hostTechnicalEvaluationTimeMs"))
        protocol = result.get("benchmarkProtocol") or summary_protocol
        if protocol == "time_limit_v2":
            timeout_turns = 0
            timeout_upper_bound_ms = 0.0
            duration_ms = number(result.get("subjectExecutionMs"))
            morpheus_ms = number(result.get("morpheusSimulationMs")) or recorded_morpheus_ms
        else:
            if mode != "morpheus_mcp":
                recorded_morpheus_ms += host_morpheus_ms
            artifact_morpheus_ms = morpheus_wall_time_ms_from_result(result, summary_benchmark_dir)
            morpheus_ms = max(recorded_morpheus_ms, artifact_morpheus_ms)
            legacy_agent_wall_ms = codex_session_wall_time_ms_from_result(result, summary_benchmark_dir)
            timeout_turns = codex_timeout_turn_count_from_result(result, summary_benchmark_dir)
            timeout_upper_bound_ms = timeout_turns * turn_timeout_ms
            duration_ms = analysis_duration_ms(
                result,
                diagnostics,
                legacy_agent_wall_ms,
                timeout_upper_bound_ms,
            )
        morpheus_activity = morpheus_activity_from_result(result, summary_benchmark_dir)
        launcher_bypass = subject_used_direct_morpheus_binary(result, summary_benchmark_dir)
        if launcher_bypass:
            morpheus_ms = np.nan
            morpheus_activity = {key: np.nan for key in morpheus_activity}
        attempt_audit = result.get("attemptArtifactAudit") or {}
        biological = biological_score_from_result(result, summary_benchmark_dir)
        manual_biological = manual_biological_score_from_result(result, manual_scores)

        records.append(
            {
                "paper": paper,
                "paper_short": paper_short_name(str(paper or "")),
                "paper_number": paper_number,
                "paper_cohort": paper_cohort,
                "paper_cohort_label": PAPER_COHORT_LABELS[paper_cohort],
                "mode": mode,
                "mode_label": MODE_LABELS.get(mode, mode),
                "repetition": repetition,
                "protocol": protocol,
                "benchmark_version": summary_benchmark_version,
                "status": result.get("stopReason") if protocol == "time_limit_v2" else result.get("status"),
                "stop_reason": result.get("stopReason"),
                "artifact_status": result.get("artifactStatus"),
                "replacement_used": number(result.get("replacementCount")) > 0,
                "infrastructure_failure_execution_count": sum(
                    1
                    for execution in (result.get("executions") or [])
                    if execution.get("stopReason") == "infrastructure_failure"
                ),
                "agent_model": agent_model,
                "agent_reasoning_effort": (
                    result.get("reasoningEffort")
                    or (summary.get("config") or {}).get("reasoningEffort")
                    or ""
                ),
                "scorer_model": (summary.get("config") or {}).get("biologicalScoringModel") or "",
                "scorer_reasoning_effort": (
                    (summary.get("config") or {}).get("biologicalScoringReasoningEffort") or ""
                ),
                "scorer_version": summary.get("biologicalScorerVersion"),
                "max_concurrent_jobs": (summary.get("config") or {}).get("maxConcurrentJobs"),
                "morpheus_num_threads": (summary.get("config") or {}).get("morpheusNumThreads"),
                "technical_score": nullable_number(result.get("technicalScore")),
                "technical_score_itt": number(result.get("technicalScore")),
                "reproduction_score": nullable_number(result.get("reproductionScore")),
                "reproduction_score_itt": number(result.get("reproductionScore")),
                "biological_score": biological["score"],
                "biological_score_itt": biological_itt_score(biological["score"], biological["status"]),
                "biological_scoring_status": biological["status"],
                "biological_score_path": biological["path"],
                "manual_biological_score": manual_biological["score"],
                "manual_biological_score_source": manual_biological["source"],
                "manual_biological_score_path": manual_biological["path"],
                "cycles": number(result.get("cycles")),
                "legacy_v1_cycles": (
                    number(result.get("cycles")) if protocol != "time_limit_v2" else np.nan
                ),
                "attempts": number(result.get("attempts")),
                "missing_attempt_xml_count": number(attempt_audit.get("missingModelXml")),
                "missing_attempt_report_count": number(attempt_audit.get("missingReproductionReport")),
                "missing_attempt_log_count": number(attempt_audit.get("missingLogs")),
                "launcher_bypass": launcher_bypass,
                "duration_h": duration_ms / 3_600_000.0,
                "subject_active_time_min": duration_ms / 60_000.0,
                "budget_fraction": number(result.get("budgetFraction")),
                "total_time_limit_ms": (
                    number(result.get("totalTimeLimitMs"))
                    or number((summary.get("config") or {}).get("totalTimeLimitMs"))
                ),
                "timeout_turns": timeout_turns,
                "timeout_upper_bound_min": timeout_upper_bound_ms / 60_000.0,
                "morpheus_time_min": morpheus_ms / 60_000.0,
                "morpheus_active_min": morpheus_activity["active_ms"] / 60_000.0,
                "morpheus_process_min": morpheus_activity["process_ms"] / 60_000.0,
                "morpheus_peak_concurrency": morpheus_activity["peak_concurrency"],
                "morpheus_interval_count": morpheus_activity["interval_count"],
                "host_morpheus_time_min": host_morpheus_ms / 60_000.0,
                "agent_analysis_min": agent_analysis_ms / 60_000.0,
                "host_technical_eval_min": host_eval_ms / 60_000.0,
                "cached_input_tokens_m": cached_input_tokens_m,
                "cache_write_input_tokens_m": cache_write_input_tokens_m,
                "uncached_input_tokens_m": uncached_input_tokens_m,
                "output_reasoning_tokens_m": output_reasoning_tokens_m,
                "total_tokens_m": number(tokens.get("total")) / 1_000_000.0,
                **token_costs,
            }
        )
    df = pd.DataFrame.from_records(records)
    mode_rank = {mode: i for i, mode in enumerate(MODE_ORDER)}
    df["mode_rank"] = df["mode"].map(mode_rank)
    df = df.sort_values(["paper_short", "mode_rank"]).reset_index(drop=True)
    return df


def execution_records_from_summary(summary: dict, benchmark_dir: Path | None = None) -> pd.DataFrame:
    summary_benchmark_dir = Path(
        benchmark_dir or summary.get("benchmarkRunDir") or "."
    )
    records = []
    for result in summary.get("results", []):
        selected_execution_id = result.get("selectedExecutionId") or result.get("executionId")
        for execution in result.get("executions") or []:
            run_id = execution.get("runId")
            run_dir = summary_benchmark_dir / str(run_id)
            workspace_dir = execution.get("workspaceDir")
            if not run_dir.exists() and isinstance(workspace_dir, str):
                run_dir = Path(workspace_dir).parent
            launcher_bypass = transcript_uses_direct_morpheus_binary(
                run_dir / "transcripts" / "subject.jsonl"
            )
            records.append(
                {
                    "assignment_id": result.get("assignmentId"),
                    "paper": result.get("paper"),
                    "mode": result.get("mode"),
                    "repetition": result_repetition(result),
                    "execution_id": execution.get("executionId"),
                    "selected": execution.get("executionId") == selected_execution_id,
                    "replacement_for": execution.get("replacementFor"),
                    "replacement_count": number(execution.get("replacementCount")),
                    "stop_reason": execution.get("stopReason"),
                    "artifact_status": execution.get("artifactStatus"),
                    "subject_active_time_min": number(execution.get("subjectExecutionMs")) / 60_000.0,
                    "morpheus_time_min": (
                        np.nan
                        if launcher_bypass
                        else number(execution.get("morpheusSimulationMs")) / 60_000.0
                    ),
                    "launcher_bypass": launcher_bypass,
                    "total_job_time_min": number(execution.get("totalJobMs")) / 60_000.0,
                    "started_at": execution.get("startedAt"),
                    "finished_at": execution.get("finishedAt"),
                    "run_id": execution.get("runId"),
                    "workspace_dir": execution.get("workspaceDir"),
                    "codex_home_dir": execution.get("codexHomeDir"),
                    "error": execution.get("error"),
                }
            )
    return pd.DataFrame.from_records(records)


def load_manual_biological_scores(benchmark_dir: Path) -> dict[tuple[str, str, int], dict[str, object]]:
    score_path = benchmark_dir / MANUAL_BIOLOGICAL_SCORE_FILE
    if not score_path.exists():
        return {}
    rows = pd.read_csv(score_path)
    missing = sorted(MANUAL_BIOLOGICAL_SCORE_COLUMNS.difference(rows.columns))
    if missing:
        raise ValueError(f"Manual biological score CSV is missing required columns: {', '.join(missing)}")

    rows = rows.copy()
    rows["canonical_paper_stem"] = rows["canonical_paper_stem"].map(canonical_paper_stem)
    rows["mode"] = rows["mode"].map(clean_string)
    rows["repetition"] = rows["repetition"].map(positive_int_or_nan)
    rows["manual_score"] = pd.to_numeric(rows["manual_score"], errors="coerce")
    if "manual_score_source" not in rows.columns:
        rows["manual_score_source"] = ""

    scores = {}
    for group_values, group in rows.groupby(["canonical_paper_stem", "mode", "repetition"], dropna=False):
        canonical_stem, mode, repetition = group_values
        if pd.isna(repetition) or not canonical_stem or not mode:
            continue
        values = group["manual_score"].dropna()
        if values.empty:
            continue
        scores[(canonical_stem, mode, int(repetition))] = {
            "score": float(values.mean()),
            "source": first_non_empty(group["manual_score_source"]),
            "path": str(score_path),
        }
    return scores


def manual_biological_score_from_result(
    result: dict,
    manual_scores: dict[tuple[str, str, int], dict[str, object]],
) -> dict:
    repetition = result_repetition(result)
    if pd.isna(repetition):
        return {"score": np.nan, "source": "", "path": ""}
    key = (canonical_paper_stem(result.get("paper")), clean_string(result.get("mode")), int(repetition))
    score = manual_scores.get(key)
    if score is None:
        return {"score": np.nan, "source": "", "path": ""}
    return score


def result_repetition(result: dict) -> float:
    repetition = positive_int_or_nan(result.get("repetition"))
    if pd.notna(repetition):
        return repetition
    return repetition_from_run_id(result.get("runId"))


def repetition_from_run_id(run_id: object) -> float:
    text = clean_string(run_id)
    match = re.search(r"__rep(\d+)$", text)
    if not match:
        return np.nan
    return float(int(match.group(1)))


def canonical_paper_stem(value: object) -> str:
    stem = Path(str(value or "")).stem
    stem = re.sub(r"_(clean|short)$", "", stem)
    return stem


def clean_string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def normalized_openai_model_id(value: object) -> str:
    text = clean_string(value).lower()
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    if re.match(r"^gpt\d", text):
        text = "gpt-" + text[3:]
    return text.strip("-")


def openai_pricing_model_key(value: object) -> str:
    model = normalized_openai_model_id(value)
    if model == "gpt-5.6":
        return "gpt-5.6-sol"
    if model in OPENAI_API_PRICING_USD_PER_1M_TOKENS:
        return model
    for key in sorted(OPENAI_API_PRICING_USD_PER_1M_TOKENS, key=len, reverse=True):
        if model.startswith(f"{key}-"):
            return key
    return model


def agent_model_from_result(result: dict, summary: dict) -> str:
    diagnostics = result.get("diagnostics") or {}
    config = summary.get("config") or {}
    for source in (result, diagnostics, config):
        if not isinstance(source, dict):
            continue
        for key in ("agentModel", "model", "codexModel"):
            model = clean_string(source.get(key))
            if model:
                return openai_pricing_model_key(model)
    return ""


def token_costs_usd(
    model: object,
    cached_input_tokens_m: float,
    cache_write_input_tokens_m: float,
    uncached_input_tokens_m: float,
    output_reasoning_tokens_m: float,
) -> dict[str, float]:
    price = OPENAI_API_PRICING_USD_PER_1M_TOKENS.get(openai_pricing_model_key(model))
    if price is None:
        return {
            "cached_input_cost_usd": np.nan,
            "cache_write_input_cost_usd": np.nan,
            "uncached_input_cost_usd": np.nan,
            "output_reasoning_cost_usd": np.nan,
            "total_cost_usd": np.nan,
        }
    cached_cost = cached_input_tokens_m * float(price["cached_input"])
    cache_write_cost = cache_write_input_tokens_m * float(price["input"]) * 1.25
    uncached_cost = uncached_input_tokens_m * float(price["input"])
    output_cost = output_reasoning_tokens_m * float(price["output"])
    return {
        "cached_input_cost_usd": cached_cost,
        "cache_write_input_cost_usd": cache_write_cost,
        "uncached_input_cost_usd": uncached_cost,
        "output_reasoning_cost_usd": output_cost,
        "total_cost_usd": cached_cost + cache_write_cost + uncached_cost + output_cost,
    }


def first_non_empty(values: Iterable[object]) -> str:
    for value in values:
        text = clean_string(value)
        if text:
            return text
    return ""


def biological_itt_score(score: object, status: object) -> float:
    """ITT biological score: subject-attributable failures count as 0.

    ``model_failed`` already carries a 0 score and ``insufficient_evidence`` (no canonical
    output to score) is treated as 0. Scorer-side outcomes (``scoring_failed``, unreadable
    score files) and runs that were never scored stay missing instead of penalizing the subject.
    """
    numeric = nullable_number(score)
    if pd.notna(numeric):
        return numeric
    return 0.0 if clean_string(status) in SUBJECT_ATTRIBUTABLE_UNSCORED_BIOLOGICAL_STATUSES else np.nan


def biological_score_from_result(result: dict, benchmark_dir: Path) -> dict:
    summary_score = nullable_number(result.get("biologicalScore"))
    summary_path = str(result.get("biologicalScorePath") or "")
    if pd.notna(summary_score):
        return {"score": summary_score, "status": "scored", "path": summary_path}

    run_dir = result_run_dir(result, benchmark_dir)
    if summary_path:
        score_path = run_artifact_path(summary_path, run_dir or benchmark_dir)
    elif run_dir is not None:
        score_path = run_dir / "biological_score.json"
    else:
        return {"score": np.nan, "status": "", "path": ""}
    if not score_path.exists():
        return {"score": np.nan, "status": "", "path": ""}
    try:
        payload = load_json_artifact(score_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"score": np.nan, "status": "invalid", "path": str(score_path)}
    return {
        "score": nullable_number(payload.get("score")),
        "status": str(payload.get("status") or ""),
        "path": str(score_path),
    }


def biological_clause_records_from_summary(summary: dict, benchmark_dir: Path) -> pd.DataFrame:
    records = []
    benchmark_dir = Path(benchmark_dir or summary.get("benchmarkRunDir") or ".").resolve()
    for result in summary.get("results", []):
        run_dir = result_run_dir(result, benchmark_dir)
        if run_dir is None:
            continue
        score_path = run_dir / "biological_score.json"
        explicit_path = result.get("biologicalScorePath")
        if isinstance(explicit_path, str) and explicit_path:
            score_path = run_artifact_path(explicit_path, run_dir)
        if not score_path.exists():
            continue
        try:
            payload = load_json_artifact(score_path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        clauses = payload.get("clauses")
        if not isinstance(clauses, list):
            continue
        for clause in clauses:
            if not isinstance(clause, dict):
                continue
            evidence = clause.get("evidence")
            records.append(
                {
                    "paper": result.get("paper"),
                    "paper_short": paper_short_name(str(result.get("paper", ""))),
                    "mode": result.get("mode"),
                    "mode_label": MODE_LABELS.get(result.get("mode"), result.get("mode")),
                    "run_id": result.get("runId"),
                    "repetition": positive_int_or_nan(result.get("repetition")),
                    "status": payload.get("status", ""),
                    "score": nullable_number(payload.get("score")),
                    "clause_id": clause.get("id", ""),
                    "passed": clause.get("passed"),
                    "observed_value": clause.get("observed_value", ""),
                    "rationale": clause.get("rationale", ""),
                    "evidence": "; ".join(str(item) for item in evidence) if isinstance(evidence, list) else "",
                    "biological_score_path": str(score_path),
                }
            )
    if not records:
        return pd.DataFrame(
            columns=[
                "paper",
                "paper_short",
                "mode",
                "mode_label",
                "run_id",
                "repetition",
                "status",
                "score",
                "clause_id",
                "passed",
                "observed_value",
                "rationale",
                "evidence",
                "biological_score_path",
            ]
        )
    return pd.DataFrame.from_records(records)


def attempt_records_from_summary(summary: dict, benchmark_dir: Path) -> pd.DataFrame:
    records = []
    benchmark_dir = Path(benchmark_dir or summary.get("benchmarkRunDir") or ".").resolve()
    for result in summary.get("results", []):
        run_dir = result_run_dir(result, benchmark_dir)
        if run_dir is None or not run_dir.exists():
            continue

        run_records = []
        seen_attempt_dirs: set[Path] = set()
        for attempt_json in sorted(run_dir.glob("**/attempt_reproduction.json")):
            attempt_dir = attempt_json.parent
            try:
                attempt = load_json_artifact(attempt_json)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                if is_agent_attempt_dir(run_dir, attempt_dir):
                    seen_attempt_dirs.add(resolved_path(attempt_dir))
                    run_records.append(
                        unscored_attempt_record(
                            result,
                            attempt_dir,
                            attempt_json,
                            "Invalid or unreadable attempt_reproduction.json; attempt was not self-scored.",
                        )
                    )
                continue
            seen_attempt_dirs.add(resolved_path(attempt_dir))
            scores = {field: nullable_number(attempt.get(field)) for field in ATTEMPT_SCORE_FIELDS}
            self_score = sum(scores.values()) if all(pd.notna(value) for value in scores.values()) else np.nan
            reported_attempt = positive_int_or_nan(attempt.get("attempt"))
            folder_attempt = attempt_number_from_path(attempt_dir)
            timestamp = str(attempt.get("timestamp") or "")
            run_records.append(
                {
                    "paper": result.get("paper"),
                    "paper_short": paper_short_name(str(result.get("paper", ""))),
                    "mode": result.get("mode"),
                    "mode_label": MODE_LABELS.get(result.get("mode"), result.get("mode")),
                    "run_id": result.get("runId"),
                    "repetition": positive_int_or_nan(result.get("repetition")),
                    "status": result.get("status"),
                    "reported_attempt": reported_attempt,
                    "folder_attempt": folder_attempt,
                    "timestamp": timestamp,
                    "iteration": positive_int_or_nan(attempt.get("iteration")),
                    **scores,
                    "self_score": self_score,
                    "normalized_self_score": self_score / 8.0 if pd.notna(self_score) else np.nan,
                    "comment": attempt.get("comment", ""),
                    "attempt_json_path": str(attempt_json),
                    "attempt_dir": str(attempt_dir),
                    "_timestamp_sort": parse_timestamp_sort_key(timestamp),
                }
            )

        for attempt_dir in discover_missing_agent_attempt_dirs(run_dir, seen_attempt_dirs):
            run_records.append(missing_attempt_record(result, attempt_dir, attempt_dir / "attempt_reproduction.json"))

        run_records = assign_attempt_numbers(run_records)
        records.extend(run_records)

    if not records:
        return pd.DataFrame(columns=ATTEMPT_COLUMNS)
    df = pd.DataFrame.from_records(records).drop(columns=["_timestamp_sort"], errors="ignore")
    mode_rank = {mode: i for i, mode in enumerate(MODE_ORDER)}
    df["_mode_rank"] = df["mode"].map(mode_rank)
    df = df.sort_values(["paper_short", "_mode_rank", "repetition", "run_id", "attempt_number"]).drop(
        columns=["_mode_rank"]
    )
    return df.reset_index(drop=True)


def run_artifact_path(stored_path: str, run_dir: Path) -> Path:
    # Summaries store artifact paths from the machine that wrote them. Rebase an absolute
    # path onto run_dir when it lies inside a folder of the same name, so a copied
    # benchmark reads its own artifacts rather than the original run folder's.
    parts = stored_path.replace("\\", "/").split("/")
    if not Path(stored_path).is_absolute() and not re.match(r"^[A-Za-z]:$", parts[0]):
        return run_dir / stored_path
    if run_dir.name in parts:
        rebased = run_dir.joinpath(*parts[len(parts) - parts[::-1].index(run_dir.name):])
        if rebased.exists():
            return rebased
    return Path(stored_path)


def result_run_dir(result: dict, benchmark_dir: Path) -> Path | None:
    # Prefer run folders inside benchmark_dir so analysing a copied benchmark never
    # reads the original run folder that the stored absolute manifest path points at.
    manifest = result.get("runManifestPath")
    run_id = result.get("runId")
    run_id = run_id if isinstance(run_id, str) and run_id else None
    manifest = manifest if isinstance(manifest, str) and manifest else None
    manifest_parent_parts = manifest.replace("\\", "/").rstrip("/").split("/") if manifest else []
    manifest_parent_name = manifest_parent_parts[-2] if len(manifest_parent_parts) >= 2 else None
    local_candidates = [benchmark_dir / name for name in (run_id, manifest_parent_name) if name]
    for candidate in local_candidates:
        if candidate.exists():
            return candidate
    if manifest:
        stored_run_dir = Path(manifest).parent
        if stored_run_dir != Path(".") and stored_run_dir.exists():
            return stored_run_dir
    return local_candidates[0] if local_candidates else None


def subject_used_direct_morpheus_binary(result: dict, benchmark_dir: Path) -> bool:
    run_dir = result_run_dir(result, benchmark_dir)
    if run_dir is None:
        return False
    return transcript_uses_direct_morpheus_binary(run_dir / "transcripts" / "subject.jsonl")


def transcript_uses_direct_morpheus_binary(transcript_path: Path) -> bool:
    try:
        lines = transcript_path.open(encoding="utf8", errors="ignore")
    except OSError:
        return False
    with lines:
        for line in lines:
            try:
                event = json.loads(line)
            except (TypeError, ValueError):
                continue
            item = event.get("item") if isinstance(event, dict) else None
            if not isinstance(item, dict) or item.get("type") != "command_execution":
                continue
            command = item.get("command")
            if isinstance(command, str) and command_uses_direct_morpheus_binary(command):
                return True
    return False


def command_uses_direct_morpheus_binary(command: str) -> bool:
    executable_pattern = re.compile(
        r"(?i)(?:[a-z]:[\\/]|/|\\\\)[^\s\"';&|]*[\\/]morpheus(?:\.exe)?(?=[\s\"']|$)"
    )
    for match in executable_pattern.finditer(command):
        executable_path = match.group(0).replace("\\", "/").lower()
        if "/benchmark-tools/morpheus" in executable_path:
            continue
        segment_tail = re.split(r"\r?\n|;|&&|\|\|?", command[match.end() :], maxsplit=1)[0]
        if re.search(r"(?:^|\s)-f(?:\s|$)", segment_tail):
            return True
    return False


def morpheus_wall_time_ms_from_result(result: dict, benchmark_dir: Path) -> float:
    run_dir = result_run_dir(result, benchmark_dir)
    if run_dir is None or not run_dir.exists():
        return 0.0
    return morpheus_wall_time_ms_from_run_dir(run_dir, result.get("mode"))


def morpheus_wall_time_ms_from_run_dir(run_dir: Path, mode: object = None) -> float:
    seen: set[Path] = set()
    total = 0.0
    for root in morpheus_attempt_search_roots(run_dir, mode):
        for candidate in attempt_dirs_under_root(root):
            resolved = resolved_path(candidate)
            if resolved in seen:
                continue
            seen.add(resolved)
            total += morpheus_wall_time_ms_from_attempt_dir(candidate)
    return total


def morpheus_activity_from_result(result: dict, benchmark_dir: Path) -> dict[str, float]:
    run_dir = result_run_dir(result, benchmark_dir)
    if run_dir is None or not run_dir.exists():
        return morpheus_activity_from_intervals([])
    return morpheus_activity_from_intervals(morpheus_intervals_from_run_dir(run_dir, result.get("mode")))


def morpheus_intervals_from_run_dir(run_dir: Path, mode: object = None) -> list[tuple[float, float]]:
    """Read per-simulation start/end times from the launcher's morpheus_command.json manifests.

    Only the agent's workspace is searched: <run_dir>/attempts holds the evaluator's post-run
    reproduction, which falls outside the agent's wall time. The launcher writes the manifest
    into the --outdir the agent chose, which is often a subfolder of the attempt folder.
    """
    seen: set[Path] = set()
    intervals = []
    agent_workspace = run_dir / "agent_workspace"
    for root in (agent_workspace / "attempts", agent_workspace / "agent_runs"):
        for manifest_path in morpheus_manifests_under_root(root):
            resolved = resolved_path(manifest_path)
            if resolved in seen:
                continue
            seen.add(resolved)
            interval = morpheus_interval_from_manifest(manifest_path)
            if interval is not None:
                intervals.append(interval)
    return intervals


def morpheus_manifests_under_root(root: Path, max_depth: int = 4) -> list[Path]:
    manifests = []
    pending = [(root, 0)]
    while pending:
        current, depth = pending.pop()
        try:
            children = sorted(current.iterdir())
        except OSError:
            continue
        for child in children:
            if child.name == "morpheus_command.json" and child.is_file():
                manifests.append(child)
            elif depth < max_depth and child.is_dir():
                pending.append((child, depth + 1))
    return manifests


def morpheus_interval_from_manifest(path: Path) -> tuple[float, float] | None:
    try:
        manifest = load_json_artifact(path) if path.is_file() else {}
    except (OSError, ValueError):
        return None
    if not isinstance(manifest, dict):
        return None
    started = parse_iso_datetime_utc(manifest.get("startedAt"))
    if started is None:
        return None
    start_s = started.timestamp()
    finished = parse_iso_datetime_utc(manifest.get("finishedAt"))
    if finished is not None:
        end_s = finished.timestamp()
    elif number(manifest.get("durationMs")) > 0:
        end_s = start_s + number(manifest.get("durationMs")) / 1000.0
    else:
        return None
    if end_s < start_s:
        return None
    return start_s, end_s


def morpheus_activity_from_intervals(intervals: Iterable[tuple[float, float]]) -> dict[str, float]:
    """Union (wall time with >=1 simulation running), summed process time and peak concurrency."""
    ordered = sorted(intervals)
    process_s = sum(end - start for start, end in ordered)
    active_s = 0.0
    current_start = current_end = None
    for start, end in ordered:
        if current_end is None or start > current_end:
            if current_end is not None:
                active_s += current_end - current_start
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    if current_end is not None:
        active_s += current_end - current_start
    peak = 0
    running = 0
    for _, delta in sorted([(start, 1) for start, _ in ordered] + [(end, -1) for _, end in ordered]):
        running += delta
        peak = max(peak, running)
    return {
        "active_ms": active_s * 1000.0,
        "process_ms": process_s * 1000.0,
        "peak_concurrency": float(peak),
        "interval_count": float(len(ordered)),
    }


def morpheus_attempt_search_roots(run_dir: Path, mode: object = None) -> list[Path]:
    agent_workspace = run_dir / "agent_workspace"
    if mode == "morpheus_mcp":
        roots = [agent_workspace / "attempts"]
        return [root for root in roots if root.exists()]
    roots = [
        run_dir / "attempts",
        agent_workspace / "attempts",
        agent_workspace / "agent_runs",
    ]
    return [root for root in roots if root.exists()]


def attempt_dirs_under_root(root: Path, max_depth: int = 3) -> list[Path]:
    attempt_dirs = []
    pending = [(root, 0)]
    while pending:
        current, depth = pending.pop()
        try:
            children = sorted(current.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir():
                continue
            if pd.notna(attempt_number_from_name(child.name)):
                attempt_dirs.append(child)
                continue
            if depth < max_depth:
                pending.append((child, depth + 1))
    return attempt_dirs


def morpheus_wall_time_ms_from_attempt_dir(attempt_dir: Path) -> float:
    durations = []
    for log_name in MORPHEUS_ATTEMPT_LOG_NAMES:
        log_path = attempt_dir / log_name
        if not log_path.exists() or not log_path.is_file():
            continue
        try:
            durations.append(morpheus_wall_time_ms_from_text(read_log_tail(log_path)))
        except OSError:
            continue
    return max(durations, default=0.0)


def read_log_tail(path: Path, max_bytes: int = MORPHEUS_LOG_TAIL_BYTES) -> str:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - max_bytes))
        return handle.read().decode("utf-8", errors="ignore")


def morpheus_wall_time_ms_from_text(text: str) -> float:
    text = normalize_log_text(text)
    total = 0.0
    for line in text.splitlines():
        match = re.search(r"\bWall\s+Time\s*=\s*(.+)$", line, flags=re.IGNORECASE)
        if match:
            total += parse_duration_ms(match.group(1))
    return total


def normalize_log_text(text: str) -> str:
    if "\x00" not in text:
        return text
    return text.replace("\x00", "")


def parse_duration_ms(text: str) -> float:
    total = 0.0
    for value, unit in re.findall(
        r"([0-9]+(?:\.[0-9]+)?)\s*(milliseconds?|msecs?|ms|hours?|hrs?|hr|h|minutes?|mins?|min|m|seconds?|secs?|sec|s)\b",
        text,
        flags=re.IGNORECASE,
    ):
        amount = float(value)
        normalized = unit.lower()
        if normalized in {"h", "hr", "hrs", "hour", "hours"}:
            total += amount * 3_600_000
        elif normalized in {"m", "min", "mins", "minute", "minutes"}:
            total += amount * 60_000
        elif normalized in {"s", "sec", "secs", "second", "seconds"}:
            total += amount * 1_000
        else:
            total += amount
    return total


def unscored_attempt_record(result: dict, attempt_dir: Path, attempt_json_path: Path, comment: str) -> dict:
    scores = {field: np.nan for field in ATTEMPT_SCORE_FIELDS}
    timestamp = attempt_timestamp_from_filesystem(attempt_dir)
    return {
        "paper": result.get("paper"),
        "paper_short": paper_short_name(str(result.get("paper", ""))),
        "mode": result.get("mode"),
        "mode_label": MODE_LABELS.get(result.get("mode"), result.get("mode")),
        "run_id": result.get("runId"),
        "repetition": positive_int_or_nan(result.get("repetition")),
        "status": result.get("status"),
        "reported_attempt": np.nan,
        "folder_attempt": attempt_number_from_path(attempt_dir),
        "timestamp": timestamp,
        "iteration": np.nan,
        **scores,
        "self_score": np.nan,
        "normalized_self_score": np.nan,
        "comment": comment,
        "attempt_json_path": str(attempt_json_path),
        "attempt_dir": str(attempt_dir),
        "_timestamp_sort": parse_timestamp_sort_key(timestamp),
    }


def missing_attempt_record(result: dict, attempt_dir: Path, attempt_json_path: Path) -> dict:
    if not attempt_has_scoreable_outputs(attempt_dir):
        return unscored_attempt_record(
            result,
            attempt_dir,
            attempt_json_path,
            "Missing attempt_reproduction.json; attempt was not self-scored.",
        )
    scores = {field: np.nan for field in ATTEMPT_SCORE_FIELDS}
    timestamp = attempt_timestamp_from_filesystem(attempt_dir)
    return {
        "paper": result.get("paper"),
        "paper_short": paper_short_name(str(result.get("paper", ""))),
        "mode": result.get("mode"),
        "mode_label": MODE_LABELS.get(result.get("mode"), result.get("mode")),
        "run_id": result.get("runId"),
        "repetition": positive_int_or_nan(result.get("repetition")),
        "status": result.get("status"),
        "reported_attempt": np.nan,
        "folder_attempt": attempt_number_from_path(attempt_dir),
        "timestamp": timestamp,
        "iteration": np.nan,
        **scores,
        "self_score": np.nan,
        "normalized_self_score": np.nan,
        "comment": "Missing attempt_reproduction.json; output artifacts exist but the attempt was not self-scored.",
        "attempt_json_path": str(attempt_json_path),
        "attempt_dir": str(attempt_dir),
        "_timestamp_sort": parse_timestamp_sort_key(timestamp),
    }


def attempt_has_scoreable_outputs(attempt_dir: Path) -> bool:
    scoreable_suffixes = {".png", ".jpg", ".jpeg", ".csv", ".tsv", ".svg"}
    try:
        files = [path for path in attempt_dir.iterdir() if path.is_file()]
    except OSError:
        return False
    for path in files:
        name = path.name.lower()
        if path.suffix.lower() in scoreable_suffixes or name.endswith(".xml.gz"):
            return True
    for log_name in ("stdout.log", "morpheus_console.txt"):
        log_path = attempt_dir / log_name
        if not log_path.exists():
            continue
        try:
            text = log_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "simulation finished" in text.lower():
            return True
    return False


def discover_missing_agent_attempt_dirs(run_dir: Path, seen_attempt_dirs: set[Path]) -> list[Path]:
    missing_dirs = []
    for root in agent_attempt_search_roots(run_dir):
        for candidate in attempt_dirs_under_root(root):
            if resolved_path(candidate) not in seen_attempt_dirs:
                missing_dirs.append(candidate)
    return missing_dirs


def is_agent_attempt_dir(run_dir: Path, attempt_dir: Path) -> bool:
    resolved_attempt_dir = resolved_path(attempt_dir)
    if pd.isna(attempt_number_from_name(attempt_dir.name)):
        return False
    for root in agent_attempt_search_roots(run_dir):
        try:
            resolved_attempt_dir.relative_to(resolved_path(root))
        except ValueError:
            continue
        return True
    return False


def agent_attempt_search_roots(run_dir: Path) -> list[Path]:
    agent_workspace = run_dir / "agent_workspace"
    roots = [agent_workspace / "attempts", agent_workspace / "agent_runs"]
    return [root for root in roots if root.exists()]


def resolved_path(path: Path) -> Path:
    return path.resolve(strict=False)


def assign_attempt_numbers(records: list[dict]) -> list[dict]:
    ordered = sorted(
        records,
        key=lambda record: (
            record["_timestamp_sort"],
            record["attempt_json_path"],
        ),
    )
    for index, record in enumerate(ordered, start=1):
        reported = record["reported_attempt"]
        folder_attempt = record["folder_attempt"]
        if pd.notna(reported):
            record["attempt_number"] = int(reported)
        elif pd.notna(folder_attempt):
            record["attempt_number"] = int(folder_attempt)
        else:
            record["attempt_number"] = index
    return ordered


def attempt_number_from_path(attempt_dir: Path) -> float:
    for part in reversed(attempt_dir.parts):
        attempt_number = attempt_number_from_name(part)
        if pd.notna(attempt_number):
            return attempt_number
    return np.nan


def attempt_number_from_name(name: str) -> float:
    match = re.fullmatch(r"attempt[_-](\d+)", name, flags=re.IGNORECASE)
    if match:
        return float(int(match.group(1)))
    return np.nan


def attempt_timestamp_from_filesystem(attempt_dir: Path) -> str:
    mtimes = []
    try:
        mtimes.append(attempt_dir.stat().st_mtime)
    except OSError:
        return ""
    try:
        children = attempt_dir.rglob("*")
    except OSError:
        children = []
    for child in children:
        try:
            if child.is_file():
                mtimes.append(child.stat().st_mtime)
        except OSError:
            continue
    timestamp = datetime.fromtimestamp(max(mtimes), timezone.utc)
    return timestamp.isoformat().replace("+00:00", "Z")


def parse_timestamp_sort_key(timestamp: str) -> pd.Timestamp:
    parsed = pd.to_datetime(timestamp, errors="coerce", utc=True)
    if pd.isna(parsed):
        return pd.Timestamp.max.tz_localize("UTC")
    return parsed


def codex_session_wall_time_ms_from_result(result: dict, benchmark_dir: Path) -> float:
    run_dir = result_run_dir(result, benchmark_dir)
    if run_dir is None or not run_dir.exists():
        return 0.0
    started_at = parse_iso_datetime_utc(result.get("startedAt"))
    finished_at = parse_iso_datetime_utc(result.get("finishedAt"))
    if started_at is None or finished_at is None or finished_at < started_at:
        return 0.0
    sessions_root = run_dir / "codex_home" / "sessions"
    if not sessions_root.exists():
        return 0.0

    total = 0.0
    for session_path in sorted(sessions_root.rglob("*.jsonl")):
        try:
            text = session_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        marker_at = text.find("task_complete")
        while marker_at >= 0:
            line_start = text.rfind("\n", 0, marker_at) + 1
            line_end = text.find("\n", marker_at)
            if line_end < 0:
                line_end = len(text)
            line = text[line_start:line_end]
            total += contributing_codex_task_complete_duration_ms(
                line,
                result.get("runId"),
                started_at,
                finished_at,
            )
            marker_at = text.find("task_complete", line_end)
    return total


def codex_timeout_turn_count_from_result(result: dict, benchmark_dir: Path) -> int:
    run_dir = result_run_dir(result, benchmark_dir)
    if run_dir is None:
        return 0
    transcript_dir = run_dir / "transcripts"
    if not transcript_dir.exists():
        return 0

    restart_paths = sorted(transcript_dir.glob("cycle_*_timeout_restart_*.jsonl"))
    restarted_cycles = {path.name.split("_timeout_restart_", 1)[0] for path in restart_paths}
    terminal_retries = 0
    for transcript_path in sorted(transcript_dir.glob("cycle_[0-9][0-9].jsonl")):
        if transcript_path.stem not in restarted_cycles:
            continue
        try:
            text = read_log_tail(transcript_path)
        except OSError:
            continue
        if '"type":"turn.completed"' not in text and '"type": "turn.completed"' not in text:
            terminal_retries += 1
    return len(restart_paths) + terminal_retries


def contributing_codex_task_complete_duration_ms(
    line: str,
    expected_run_id: object,
    started_at: datetime,
    finished_at: datetime,
) -> float:
    timestamp, duration_ms, last_message = codex_task_complete_line_record(line)
    if timestamp is None or duration_ms <= 0:
        return 0.0
    message_kind = codex_last_agent_message_kind(last_message, expected_run_id)
    if message_kind == "scoring":
        return 0.0
    if message_kind == "preflight":
        return 0.0
    if message_kind == "subject":
        return duration_ms
    return 0.0


def subject_transcript_tokens_from_result(result: dict, benchmark_dir: Path) -> dict[str, float] | None:
    run_dir = result_run_dir(result, benchmark_dir)
    if run_dir is None or not run_dir.exists():
        return None
    transcript_dir = run_dir / "transcripts"
    if not transcript_dir.exists():
        return None

    totals = {
        "input": 0.0,
        "cachedInput": 0.0,
        "cacheWriteInput": 0.0,
        "output": 0.0,
        "reasoningOutput": 0.0,
        "total": 0.0,
    }
    found_usage = False
    protocol = result.get("benchmarkProtocol") or "max_cycles_v1"
    transcript_paths = (
        [transcript_dir / "subject.jsonl"]
        if protocol == "time_limit_v2"
        else sorted(transcript_dir.glob("cycle_*.jsonl"))
    )
    for transcript_path in transcript_paths:
        if not transcript_path.exists():
            continue
        usage = transcript_usage_tokens_from_file(transcript_path)
        if usage is None:
            continue
        found_usage = True
        totals["input"] += usage["input"]
        totals["cachedInput"] += usage["cachedInput"]
        totals["cacheWriteInput"] += usage["cacheWriteInput"]
        totals["output"] += usage["output"]
        totals["reasoningOutput"] += usage["reasoningOutput"]
    if not found_usage:
        return None
    totals["total"] = totals["input"] + totals["output"]
    return totals


def subject_session_tokens_from_result(result: dict, benchmark_dir: Path) -> dict[str, float] | None:
    """Cumulative v2 subject usage from its Codex session rollout.

    Time-limited or killed subjects never emit turn.completed, so the transcript has no
    usage; the rollout's last token_count event holds the same cumulative totals.
    """
    protocol = result.get("benchmarkProtocol") or "max_cycles_v1"
    thread_id = clean_string(result.get("threadId"))
    if protocol != "time_limit_v2" or not re.fullmatch(r"[A-Za-z0-9_-]+", thread_id):
        return None
    run_dir = result_run_dir(result, benchmark_dir)
    if run_dir is None:
        return None
    sessions_root = run_dir / "codex_home" / "sessions"
    if not sessions_root.exists():
        return None
    usage = None
    for rollout_path in sorted(sessions_root.rglob(f"rollout-*{thread_id}*.jsonl")):
        usage = rollout_token_usage_from_file(rollout_path) or usage
    return usage


def rollout_token_usage_from_file(rollout_path: Path) -> dict[str, float] | None:
    usage = None
    try:
        lines = rollout_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None
    for line in lines:
        if "token_count" not in line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = event.get("payload") if isinstance(event, dict) else None
        info = payload.get("info") if isinstance(payload, dict) and payload.get("type") == "token_count" else None
        total = info.get("total_token_usage") if isinstance(info, dict) else None
        if not isinstance(total, dict):
            continue
        input_tokens = number(total.get("input_tokens"))
        output_tokens = number(total.get("output_tokens"))
        usage = {
            "input": input_tokens,
            "cachedInput": number(total.get("cached_input_tokens")),
            "cacheWriteInput": number(total.get("cache_write_input_tokens")),
            "output": output_tokens,
            "reasoningOutput": number(total.get("reasoning_output_tokens")),
            "total": input_tokens + output_tokens,
        }
    return usage


def transcript_usage_tokens_from_file(transcript_path: Path) -> dict[str, float] | None:
    totals = {"input": 0.0, "cachedInput": 0.0, "cacheWriteInput": 0.0, "output": 0.0, "reasoningOutput": 0.0}
    found_usage = False
    try:
        text = read_log_tail(transcript_path)
    except OSError:
        return None
    for line in text.splitlines():
        if "turn.completed" not in line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "turn.completed" or not isinstance(event.get("usage"), dict):
            continue
        usage = event["usage"]
        totals["input"] += number(usage.get("input_tokens"))
        totals["cachedInput"] += number(usage.get("cached_input_tokens"))
        totals["cacheWriteInput"] += number(usage.get("cache_write_input_tokens"))
        totals["output"] += number(usage.get("output_tokens"))
        totals["reasoningOutput"] += number(usage.get("reasoning_output_tokens"))
        found_usage = True
    return totals if found_usage else None


def codex_task_complete_line_record(line: str) -> tuple[datetime | None, float, str]:
    timestamp_match = re.search(r'"timestamp"\s*:\s*"([^"]+)"', line[:200])
    if not timestamp_match:
        return None, 0.0, ""
    duration_key_at = line.rfind('"duration_ms"')
    if duration_key_at < 0:
        return None, 0.0, ""
    duration_match = re.match(r'"duration_ms"\s*:\s*([0-9]+)', line[duration_key_at:])
    if not duration_match:
        return None, 0.0, ""
    return (
        parse_iso_datetime_utc(timestamp_match.group(1)),
        float(duration_match.group(1)),
        codex_last_agent_message_from_task_complete_line(line),
    )


def codex_last_agent_message_from_task_complete_line(line: str) -> str:
    key_at = line.rfind('"last_agent_message"')
    if key_at < 0:
        return ""
    value_at = line.find(":", key_at)
    if value_at < 0:
        return ""
    try:
        value, _ = json.JSONDecoder().raw_decode(line[value_at + 1 :].lstrip())
    except json.JSONDecodeError:
        return ""
    return value if isinstance(value, str) else ""


def codex_last_agent_message_kind(message: str, expected_run_id: object) -> str:
    if not message:
        return "unknown"
    try:
        parsed = json.loads(message)
    except json.JSONDecodeError:
        return "unknown"
    if not isinstance(parsed, dict):
        return "unknown"
    status = clean_string(parsed.get("status"))
    if status == "scored":
        return "scoring"
    if status == "completed" and clean_string(parsed.get("summary")).lower() == "ready":
        return "preflight"
    if (
        clean_string(parsed.get("runId")) == clean_string(expected_run_id)
        and status in {"in_progress", "completed", "failed"}
        and isinstance(parsed.get("modelChanged"), bool)
        and isinstance(parsed.get("morpheusRan"), bool)
        and isinstance(parsed.get("needsAnotherCycle"), bool)
    ):
        return "subject"
    return "unknown"


def agent_wall_time_ms_from_diagnostics(diagnostics: dict) -> float:
    return number(diagnostics.get("agentWallTimeMs"))


def parse_iso_datetime_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def positive_int_or_nan(value: object) -> float:
    if isinstance(value, bool):
        return np.nan
    if isinstance(value, (int, float)) and math.isfinite(float(value)) and int(value) == float(value) and value > 0:
        return float(int(value))
    return np.nan


def number(value: object) -> float:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return 0.0


def nullable_number(value: object) -> float:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return np.nan


def analysis_duration_ms(
    result: dict,
    diagnostics: dict,
    legacy_agent_wall_ms: float = 0.0,
    timeout_upper_bound_ms: float = 0.0,
) -> float:
    if legacy_agent_wall_ms > 0:
        return legacy_agent_wall_ms + timeout_upper_bound_ms
    diagnostic_duration_ms = agent_wall_time_ms_from_diagnostics(diagnostics)
    if diagnostic_duration_ms > 0:
        return diagnostic_duration_ms
    fallback_duration_ms = number(result.get("durationMs"))
    if fallback_duration_ms > MAX_FALLBACK_DURATION_MS:
        return np.nan
    return fallback_duration_ms


def summarize_by_mode(df: pd.DataFrame) -> pd.DataFrame:
    work = ensure_score_columns(df)
    work = ensure_cost_columns(work)
    work = add_normalized_quality_columns(work)
    if "timeout_upper_bound_min" not in work.columns:
        work["timeout_upper_bound_min"] = 0.0
    if "cache_write_input_tokens_m" not in work.columns:
        work["cache_write_input_tokens_m"] = 0.0
    if "host_morpheus_time_min" not in work.columns:
        work["host_morpheus_time_min"] = 0.0
    for column in ("morpheus_active_min", "morpheus_process_min", "morpheus_peak_concurrency"):
        if column not in work.columns:
            work[column] = np.nan
    if "replacement_used" not in work.columns:
        work["replacement_used"] = False
    if "infrastructure_failure_execution_count" not in work.columns:
        work["infrastructure_failure_execution_count"] = 0
    cohort_columns = [
        column
        for column in (
            "protocol",
            "benchmark_version",
            "total_time_limit_ms",
            "agent_model",
            "agent_reasoning_effort",
            "scorer_model",
            "scorer_reasoning_effort",
            "scorer_version",
            "max_concurrent_jobs",
            "morpheus_num_threads",
        )
        if column in work.columns
    ]
    mixed_columns = [
        column for column in cohort_columns if work[column].astype(str).nunique(dropna=False) > 1
    ]
    if mixed_columns:
        raise ValueError(
            "Cannot pool mixed benchmark cohorts in one mode summary; stratify by: "
            + ", ".join(mixed_columns)
        )
    summary = (
        work.groupby("mode", dropna=False)
        .agg(
            n=("paper", "count"),
            agent_finished=("status", lambda s: int((s == "agent_finished").sum())),
            completed=("status", lambda s: int((s == "completed").sum())),
            max_turns=("status", lambda s: int((s == "max_turns").sum())),
            failed=("status", lambda s: int((s == "failed").sum())),
            time_limit=("status", lambda s: int((s == "time_limit").sum())),
            infrastructure_failure=("status", lambda s: int((s == "infrastructure_failure").sum())),
            replacements=("replacement_used", "sum"),
            infrastructure_failure_executions=("infrastructure_failure_execution_count", "sum"),
            technical_mean=("technical_score", "mean"),
            technical_valid_only_mean=("technical_score", "mean"),
            technical_itt_mean=("technical_score_itt", "mean"),
            technical_std=("technical_score", "std"),
            reproduction_mean=("reproduction_score", "mean"),
            reproduction_valid_only_mean=("reproduction_score", "mean"),
            reproduction_itt_mean=("reproduction_score_itt", "mean"),
            reproduction_std=("reproduction_score", "std"),
            quality_mean=("quality_score", "mean"),
            quality_std=("quality_score", "std"),
            biological_mean=("biological_score", "mean"),
            biological_valid_only_mean=("biological_score", "mean"),
            biological_itt_mean=("biological_score_itt", "mean"),
            biological_itt_n=("biological_score_itt", "count"),
            biological_std=("biological_score", "std"),
            manual_biological_mean=("manual_biological_score", "mean"),
            manual_biological_std=("manual_biological_score", "std"),
            duration_h_mean=("duration_h", "mean"),
            duration_h_std=("duration_h", "std"),
            timeout_upper_bound_min_mean=("timeout_upper_bound_min", "mean"),
            morpheus_time_min_mean=("morpheus_time_min", "mean"),
            morpheus_time_min_std=("morpheus_time_min", "std"),
            morpheus_active_min_mean=("morpheus_active_min", "mean"),
            morpheus_process_min_mean=("morpheus_process_min", "mean"),
            morpheus_peak_concurrency_mean=("morpheus_peak_concurrency", "mean"),
            host_morpheus_time_min_mean=("host_morpheus_time_min", "mean"),
            host_morpheus_time_min_std=("host_morpheus_time_min", "std"),
            agent_analysis_min_mean=("agent_analysis_min", "mean"),
            agent_analysis_min_std=("agent_analysis_min", "std"),
            cached_input_tokens_m_mean=("cached_input_tokens_m", "mean"),
            cache_write_input_tokens_m_mean=("cache_write_input_tokens_m", "mean"),
            uncached_input_tokens_m_mean=("uncached_input_tokens_m", "mean"),
            output_reasoning_tokens_m_mean=("output_reasoning_tokens_m", "mean"),
            total_tokens_m_mean=("total_tokens_m", "mean"),
            total_tokens_m_std=("total_tokens_m", "std"),
            cached_input_cost_usd_mean=("cached_input_cost_usd", "mean"),
            cache_write_input_cost_usd_mean=("cache_write_input_cost_usd", "mean"),
            uncached_input_cost_usd_mean=("uncached_input_cost_usd", "mean"),
            output_reasoning_cost_usd_mean=("output_reasoning_cost_usd", "mean"),
            total_cost_usd_mean=("total_cost_usd", "mean"),
            total_cost_usd_std=("total_cost_usd", "std"),
            cycles_mean=("cycles", "mean"),
            legacy_v1_cycles_mean=("legacy_v1_cycles", "mean"),
            attempts_mean=("attempts", "mean"),
        )
        .reindex(MODE_ORDER)
        .reset_index()
    )
    for column in cohort_columns:
        summary[column] = work[column].iloc[0] if len(work) else np.nan
    summary["mode_label"] = summary["mode"].map(MODE_LABELS)
    return summary


def ensure_score_columns(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    for column in ["biological_score", "manual_biological_score"]:
        if column not in work.columns:
            work[column] = np.nan
    for source, target in [
        ("technical_score", "technical_score_itt"),
        ("reproduction_score", "reproduction_score_itt"),
    ]:
        if target not in work.columns:
            source_values = work[source] if source in work.columns else pd.Series(np.nan, index=work.index)
            work[target] = pd.to_numeric(source_values, errors="coerce").fillna(0.0)
    if "biological_score_itt" not in work.columns:
        work["biological_score_itt"] = biological_itt_series(work)
    if "legacy_v1_cycles" not in work.columns:
        cycle_values = work["cycles"] if "cycles" in work.columns else pd.Series(np.nan, index=work.index)
        work["legacy_v1_cycles"] = pd.to_numeric(cycle_values, errors="coerce")
    return work


def biological_itt_series(df: pd.DataFrame) -> pd.Series:
    """Vectorized ``biological_itt_score``; legacy frames without a status keep the zero fill."""
    if "biological_scoring_status" not in df.columns:
        scores = df["biological_score"] if "biological_score" in df.columns else pd.Series(np.nan, index=df.index)
        return pd.to_numeric(scores, errors="coerce").fillna(0.0)
    return pd.Series(
        [
            biological_itt_score(score, status)
            for score, status in zip(df["biological_score"], df["biological_scoring_status"])
        ],
        index=df.index,
        dtype=float,
    )


def ensure_cost_columns(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    if "agent_model" not in work.columns:
        work["agent_model"] = ""
    for column in COST_COMPONENT_COLUMNS:
        if column not in work.columns:
            work[column] = np.nan
    return work


def paper_cohort_views(df: pd.DataFrame) -> list[dict]:
    work = ensure_paper_cohort_columns(df)
    views = []
    for cohort in PAPER_COHORT_VIEW_ORDER:
        subset = work if cohort == "all" else work.loc[work["paper_cohort"] == cohort].copy()
        views.append(
            {
                "paper_cohort": cohort,
                "paper_cohort_label": PAPER_COHORT_VIEW_LABELS[cohort],
                "df": subset,
            }
        )
    return views


def summarize_by_paper_cohort_and_mode(df: pd.DataFrame) -> pd.DataFrame:
    summaries = []
    for view in paper_cohort_views(df):
        summary = summarize_by_mode(view["df"])
        summary.insert(0, "paper_cohort_label", view["paper_cohort_label"])
        summary.insert(0, "paper_cohort", view["paper_cohort"])
        summaries.append(summary)
    return pd.concat(summaries, ignore_index=True)


def cost_quality_records(df: pd.DataFrame) -> pd.DataFrame:
    work = add_normalized_quality_columns(df)
    pareto = (
        work.groupby("mode", dropna=False)
        .agg(
            n=("paper", "count"),
            quality_mean=("quality_score", "mean"),
            quality_median=("quality_score", "median"),
            quality_std=("quality_score", "std"),
            technical_normalized_mean=("technical_normalized", "mean"),
            reproduction_normalized_mean=("reproduction_normalized", "mean"),
            biological_normalized_mean=("biological_normalized", "mean"),
            total_tokens_m_mean=("total_tokens_m", "mean"),
            total_tokens_m_median=("total_tokens_m", "median"),
            total_tokens_m_std=("total_tokens_m", "std"),
            duration_h_mean=("duration_h", "mean"),
            duration_h_std=("duration_h", "std"),
            attempts_mean=("attempts", "mean"),
        )
        .reindex(MODE_ORDER)
        .reset_index()
    )
    pareto["mode_label"] = pareto["mode"].map(MODE_LABELS)
    return pareto.dropna(subset=["quality_mean", "total_tokens_m_mean"], how="any").reset_index(drop=True)


def cost_quality_raw_records(df: pd.DataFrame) -> pd.DataFrame:
    raw = add_normalized_quality_columns(df)
    raw["mode_label"] = raw["mode"].map(MODE_LABELS)
    columns = ["paper", "paper_short", "mode", "mode_label", "total_tokens_m", "quality_score"]
    return raw.dropna(subset=["quality_score", "total_tokens_m"], how="any")[columns].reset_index(drop=True)


def dollar_cost_quality_records(df: pd.DataFrame) -> pd.DataFrame:
    if "total_cost_usd" not in df.columns:
        return pd.DataFrame()
    work = add_normalized_quality_columns(df)
    pareto = (
        work.groupby("mode", dropna=False)
        .agg(
            n=("paper", "count"),
            quality_mean=("quality_score", "mean"),
            quality_median=("quality_score", "median"),
            quality_std=("quality_score", "std"),
            technical_normalized_mean=("technical_normalized", "mean"),
            reproduction_normalized_mean=("reproduction_normalized", "mean"),
            biological_normalized_mean=("biological_normalized", "mean"),
            total_cost_usd_mean=("total_cost_usd", "mean"),
            total_cost_usd_median=("total_cost_usd", "median"),
            total_cost_usd_std=("total_cost_usd", "std"),
            duration_h_mean=("duration_h", "mean"),
            duration_h_std=("duration_h", "std"),
            attempts_mean=("attempts", "mean"),
        )
        .reindex(MODE_ORDER)
        .reset_index()
    )
    pareto["mode_label"] = pareto["mode"].map(MODE_LABELS)
    return pareto.dropna(subset=["quality_mean", "total_cost_usd_mean"], how="any").reset_index(drop=True)


def dollar_cost_quality_raw_records(df: pd.DataFrame) -> pd.DataFrame:
    if "total_cost_usd" not in df.columns:
        return pd.DataFrame()
    raw = add_normalized_quality_columns(df)
    raw["mode_label"] = raw["mode"].map(MODE_LABELS)
    columns = ["paper", "paper_short", "mode", "mode_label", "total_cost_usd", "quality_score"]
    return raw.dropna(subset=["quality_score", "total_cost_usd"], how="any")[columns].reset_index(drop=True)


def cost_single_score_records(df: pd.DataFrame, score_col: str) -> pd.DataFrame:
    if score_col not in df.columns:
        return pd.DataFrame()
    pareto = (
        df.groupby("mode", dropna=False)
        .agg(
            n=("paper", "count"),
            quality_mean=(score_col, "mean"),
            quality_median=(score_col, "median"),
            quality_std=(score_col, "std"),
            total_tokens_m_mean=("total_tokens_m", "mean"),
            total_tokens_m_median=("total_tokens_m", "median"),
            total_tokens_m_std=("total_tokens_m", "std"),
            duration_h_mean=("duration_h", "mean"),
            duration_h_std=("duration_h", "std"),
            attempts_mean=("attempts", "mean"),
        )
        .reindex(MODE_ORDER)
        .reset_index()
    )
    pareto["mode_label"] = pareto["mode"].map(MODE_LABELS)
    return pareto.dropna(subset=["quality_mean", "total_tokens_m_mean"], how="any").reset_index(drop=True)


def cost_single_score_raw_records(df: pd.DataFrame, score_col: str) -> pd.DataFrame:
    if score_col not in df.columns:
        return pd.DataFrame()
    raw = df.copy()
    raw["mode_label"] = raw["mode"].map(MODE_LABELS)
    raw["quality_score"] = raw[score_col]
    columns = ["paper", "paper_short", "mode", "mode_label", "total_tokens_m", "quality_score"]
    return raw.dropna(subset=["quality_score", "total_tokens_m"], how="any")[columns].reset_index(drop=True)


def dollar_cost_single_score_records(df: pd.DataFrame, score_col: str) -> pd.DataFrame:
    if score_col not in df.columns or "total_cost_usd" not in df.columns:
        return pd.DataFrame()
    pareto = (
        df.groupby("mode", dropna=False)
        .agg(
            n=("paper", "count"),
            quality_mean=(score_col, "mean"),
            quality_median=(score_col, "median"),
            quality_std=(score_col, "std"),
            total_cost_usd_mean=("total_cost_usd", "mean"),
            total_cost_usd_median=("total_cost_usd", "median"),
            total_cost_usd_std=("total_cost_usd", "std"),
            duration_h_mean=("duration_h", "mean"),
            duration_h_std=("duration_h", "std"),
            attempts_mean=("attempts", "mean"),
        )
        .reindex(MODE_ORDER)
        .reset_index()
    )
    pareto["mode_label"] = pareto["mode"].map(MODE_LABELS)
    return pareto.dropna(subset=["quality_mean", "total_cost_usd_mean"], how="any").reset_index(drop=True)


def dollar_cost_single_score_raw_records(df: pd.DataFrame, score_col: str) -> pd.DataFrame:
    if score_col not in df.columns or "total_cost_usd" not in df.columns:
        return pd.DataFrame()
    raw = df.copy()
    raw["mode_label"] = raw["mode"].map(MODE_LABELS)
    raw["quality_score"] = raw[score_col]
    columns = ["paper", "paper_short", "mode", "mode_label", "total_cost_usd", "quality_score"]
    return raw.dropna(subset=["quality_score", "total_cost_usd"], how="any")[columns].reset_index(drop=True)


def cost_biological_records(df: pd.DataFrame) -> pd.DataFrame:
    return cost_single_score_records(df, "biological_score")


def cost_biological_raw_records(df: pd.DataFrame) -> pd.DataFrame:
    return cost_single_score_raw_records(df, "biological_score")


def add_normalized_quality_columns(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["technical_normalized"] = work["technical_score"] / 7.0
    work["reproduction_normalized"] = work["reproduction_score"] / 8.0
    if "biological_score" in work.columns:
        work["biological_normalized"] = work["biological_score"]
    else:
        work["biological_normalized"] = np.nan
    work["quality_score"] = work["biological_normalized"].fillna(work["reproduction_normalized"])
    return work


def configure_matplotlib() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 140,
            "savefig.dpi": 600,
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "DejaVu Sans", "Liberation Sans"],
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 0.8,
            "axes.labelsize": 9,
            "axes.titlesize": 10,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


def add_panel_label(ax: plt.Axes, label: str) -> None:
    ax.text(
        -0.12,
        1.08,
        label,
        transform=ax.transAxes,
        fontsize=12,
        fontweight="bold",
        va="top",
        ha="left",
    )


def mode_positions() -> np.ndarray:
    return np.arange(len(MODE_ORDER), dtype=float)


def set_mode_axis(ax: plt.Axes) -> None:
    ax.set_xticks(mode_positions())
    ax.set_xticklabels([MODE_LABELS[mode] for mode in MODE_ORDER], rotation=25, ha="right")


def available_biological_score_specs(df: pd.DataFrame, summary: pd.DataFrame | None = None) -> list[dict]:
    specs = []
    for spec in BIOLOGICAL_SCORE_SPECS:
        point_col = spec["point_col"]
        mean_col = spec["mean_col"]
        if point_col not in df.columns or not df[point_col].notna().any():
            continue
        if summary is not None and mean_col not in summary.columns:
            continue
        specs.append(spec)
    return specs


def grouped_score_boxplots(ax: plt.Axes, df: pd.DataFrame) -> None:
    x = mode_positions()
    score_specs = [
        {
            "label": "Technical",
            "point_col": "technical_score",
            "divisor": 7.0,
        },
        {
            "label": "Reproduction (self-reported)",
            "point_col": "reproduction_score",
            "divisor": 8.0,
        },
    ]
    for spec in available_biological_score_specs(df):
        score_specs.append({**spec, "divisor": 1.0})
    width = 0.72 / len(score_specs)
    offsets = np.linspace(-width * (len(score_specs) - 1) / 2, width * (len(score_specs) - 1) / 2, len(score_specs))
    for spec, offset in zip(score_specs, offsets):
        label = spec["label"]
        point_col = spec["point_col"]
        divisor = spec["divisor"]
        values_by_mode = []
        positions = []
        for mode_index, mode in enumerate(MODE_ORDER):
            values = df.loc[df["mode"] == mode, point_col].dropna().to_numpy(dtype=float) / divisor
            values = values[np.isfinite(values)]
            if len(values) == 0:
                continue
            values_by_mode.append(values)
            positions.append(x[mode_index] + offset)

        if values_by_mode:
            boxes = ax.boxplot(
                values_by_mode,
                positions=positions,
                widths=width * 0.82,
                patch_artist=True,
                showmeans=True,
                showfliers=False,
                meanprops={
                    "marker": "D",
                    "markerfacecolor": "white",
                    "markeredgecolor": "black",
                    "markersize": 3.5,
                },
                medianprops={"color": "black", "linewidth": 1.1},
                boxprops={"edgecolor": "black", "linewidth": 0.7},
                whiskerprops={"color": "black", "linewidth": 0.7},
                capprops={"color": "black", "linewidth": 0.7},
            )
            for patch in boxes["boxes"]:
                patch.set_facecolor(SCORE_COLORS[label])
                patch.set_alpha(0.7)

        for position, values in zip(positions, values_by_mode):
            jitter = (
                np.linspace(-width * 0.18, width * 0.18, len(values))
                if len(values) > 1
                else np.array([0.0])
            )
            ax.scatter(
                np.full(len(values), position) + jitter,
                values,
                s=10,
                color="white",
                edgecolor="black",
                linewidth=0.35,
                alpha=0.65,
                zorder=3,
            )
    ax.set_ylabel("Normalized score")
    ax.set_ylim(0, 1.08)
    set_mode_axis(ax)
    ax.legend(
        handles=[
            Patch(
                facecolor=SCORE_COLORS[spec["label"]],
                edgecolor="black",
                label=spec["label"],
                alpha=0.7,
            )
            for spec in score_specs
        ],
        frameon=False,
        loc="upper left",
    )
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.6)


def time_stacked_bars(ax: plt.Axes, summary: pd.DataFrame) -> None:
    """Split mean wall time into time with >=1 Morpheus simulation running and agent-only time.

    Simulations can run in parallel, so summed simulation time is not a share of wall time;
    the split uses the union of simulation intervals and the mean summed/union ratio is
    printed above each bar.
    """
    x = mode_positions()
    wall_h = summary["duration_h_mean"].to_numpy(dtype=float)
    timeout_h = np.nan_to_num(summary["timeout_upper_bound_min_mean"].to_numpy(dtype=float) / 60.0, nan=0.0)
    timeout_h = np.maximum(0.0, timeout_h)
    active_min = (
        summary["morpheus_active_min_mean"].to_numpy(dtype=float)
        if "morpheus_active_min_mean" in summary.columns
        else np.full(len(summary), np.nan)
    )
    legacy_min = summary["morpheus_time_min_mean"].to_numpy(dtype=float)
    has_intervals = np.isfinite(active_min) & (active_min > 0)
    morpheus_h = np.nan_to_num(np.where(has_intervals, active_min, legacy_min) / 60.0, nan=0.0)
    morpheus_h = np.maximum(0.0, morpheus_h)
    valid_wall = np.isfinite(wall_h)
    timeout_h = np.where(valid_wall, np.minimum(timeout_h, np.maximum(0.0, wall_h)), 0.0)
    completed_h = np.where(valid_wall, np.maximum(0.0, wall_h - timeout_h), 0.0)
    morpheus_h = np.minimum(morpheus_h, completed_h)
    agent_h = np.maximum(0.0, completed_h - morpheus_h)
    components = [
        ("Morpheus running", morpheus_h, np.zeros(len(MODE_ORDER))),
        ("Agent only", agent_h, morpheus_h),
    ]
    if np.any(timeout_h > 0):
        components.append(("Timeout duration (upper bound)", timeout_h, morpheus_h + agent_h))
    for label, values, bottom in components:
        ax.bar(
            x,
            values,
            bottom=bottom,
            color=TIME_COMPONENT_COLORS[label],
            edgecolor="black",
            linewidth=0.6,
            label=label,
        )
    if "morpheus_process_min_mean" in summary.columns:
        process_min = summary["morpheus_process_min_mean"].to_numpy(dtype=float)
        top_h = morpheus_h + agent_h + timeout_h
        for xpos, process, active, top in zip(x, process_min, active_min, top_h):
            if np.isfinite(process) and np.isfinite(active) and active > 0:
                ax.text(xpos, top, f"\u00d7{process / active:.1f}", ha="center", va="bottom", fontsize=7)
    set_mode_axis(ax)
    ax.set_ylabel("Wall time per run (h)" if not np.any(timeout_h > 0) else "Upper-bound time per run (h)")
    ax.legend(frameon=False, loc="upper left")
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.6)


def metric_boxplot(
    ax: plt.Axes,
    df: pd.DataFrame,
    value_col: str,
    ylabel: str,
    ylim_bottom: float = 0.0,
) -> None:
    values_by_mode = []
    positions = []
    for index, mode in enumerate(MODE_ORDER):
        values = df.loc[df["mode"] == mode, value_col].dropna().to_numpy(dtype=float)
        values = values[np.isfinite(values)]
        if len(values) == 0:
            continue
        values_by_mode.append(values)
        positions.append(index)

    if values_by_mode:
        boxes = ax.boxplot(
            values_by_mode,
            positions=positions,
            widths=0.56,
            patch_artist=True,
            showmeans=True,
            showfliers=False,
            meanprops={
                "marker": "D",
                "markerfacecolor": "white",
                "markeredgecolor": "black",
                "markersize": 4,
            },
            medianprops={"color": "black", "linewidth": 1.2},
            boxprops={"edgecolor": "black", "linewidth": 0.7},
            whiskerprops={"color": "black", "linewidth": 0.7},
            capprops={"color": "black", "linewidth": 0.7},
            flierprops={
                "marker": "o",
                "markerfacecolor": "white",
                "markeredgecolor": "black",
                "markersize": 3,
                "alpha": 0.65,
            },
        )
        for patch, position in zip(boxes["boxes"], positions):
            patch.set_facecolor(MODE_COLORS.get(MODE_ORDER[position], "#999999"))
            patch.set_alpha(0.6)

    for position, values in zip(positions, values_by_mode):
        jitter = np.linspace(-0.08, 0.08, len(values)) if len(values) > 1 else np.array([0.0])
        color = MODE_COLORS.get(MODE_ORDER[position], "#999999")
        ax.scatter(
            np.full(len(values), position) + jitter,
            values,
            s=13,
            color="white",
            edgecolor=color,
            linewidth=0.65,
            alpha=0.8,
            zorder=3,
        )

    set_mode_axis(ax)
    ax.set_ylabel(ylabel)
    ax.set_ylim(bottom=ylim_bottom)
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.6)


def score_boxplot(
    ax: plt.Axes,
    df: pd.DataFrame,
    score_col: str,
    divisor: float,
    ylabel: str = "",
    show_x_labels: bool = True,
) -> None:
    values_by_mode = []
    positions = []
    for index, mode in enumerate(MODE_ORDER):
        values = df.loc[df["mode"] == mode, score_col].dropna().to_numpy(dtype=float)
        values = values[np.isfinite(values)] / divisor
        if len(values) == 0:
            continue
        values_by_mode.append(values)
        positions.append(index)

    if values_by_mode:
        boxes = ax.boxplot(
            values_by_mode,
            positions=positions,
            widths=0.56,
            patch_artist=True,
            showmeans=True,
            showfliers=False,
            meanprops={
                "marker": "D",
                "markerfacecolor": "white",
                "markeredgecolor": "black",
                "markersize": 4,
            },
            medianprops={"color": "black", "linewidth": 1.2},
            boxprops={"edgecolor": "black", "linewidth": 0.7},
            whiskerprops={"color": "black", "linewidth": 0.7},
            capprops={"color": "black", "linewidth": 0.7},
            flierprops={
                "marker": "o",
                "markerfacecolor": "white",
                "markeredgecolor": "black",
                "markersize": 3,
                "alpha": 0.65,
            },
        )
        for patch, position in zip(boxes["boxes"], positions):
            patch.set_facecolor(MODE_COLORS.get(MODE_ORDER[position], "#999999"))
            patch.set_alpha(0.6)
        for position, values in zip(positions, values_by_mode):
            jitter = np.linspace(-0.08, 0.08, len(values)) if len(values) > 1 else np.array([0.0])
            color = MODE_COLORS.get(MODE_ORDER[position], "#999999")
            ax.scatter(
                np.full(len(values), position) + jitter,
                values,
                s=12,
                color="white",
                edgecolor=color,
                linewidth=0.6,
                alpha=0.8,
                zorder=3,
            )
    else:
        ax.text(0.5, 0.5, "No data", transform=ax.transAxes, ha="center", va="center", color="#666666")

    set_mode_axis(ax)
    if not show_x_labels:
        ax.set_xticklabels([])
        ax.tick_params(axis="x", length=0)
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, 1.08)
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.6)


def token_stacked_bars(ax: plt.Axes, summary: pd.DataFrame) -> None:
    x = mode_positions()
    bottom = np.zeros(len(MODE_ORDER))
    specs = [
        ("Cached input", "cached_input_tokens_m_mean"),
        ("Cache write input", "cache_write_input_tokens_m_mean"),
        ("Uncached input", "uncached_input_tokens_m_mean"),
        ("Output (incl. reasoning)", "output_reasoning_tokens_m_mean"),
    ]
    for label, col in specs:
        values = np.nan_to_num(summary[col].to_numpy(dtype=float), nan=0.0)
        ax.bar(
            x,
            values,
            bottom=bottom,
            color=TOKEN_COLORS[label],
            edgecolor="black",
            linewidth=0.6,
            label=label,
        )
        bottom += values
    set_mode_axis(ax)
    ax.set_ylabel("Tokens per run (million)")
    ax.legend(frameon=False, loc="upper left")
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.6)


def usd_cost_stacked_bars(ax: plt.Axes, summary: pd.DataFrame) -> None:
    x = mode_positions()
    bottom = np.zeros(len(MODE_ORDER))
    specs = [
        ("Cached input", "cached_input_cost_usd_mean"),
        ("Cache write input", "cache_write_input_cost_usd_mean"),
        ("Uncached input", "uncached_input_cost_usd_mean"),
        ("Output (incl. reasoning)", "output_reasoning_cost_usd_mean"),
    ]
    for label, col in specs:
        values = np.nan_to_num(summary[col].to_numpy(dtype=float), nan=0.0)
        ax.bar(
            x,
            values,
            bottom=bottom,
            color=TOKEN_COLORS[label],
            edgecolor="black",
            linewidth=0.6,
            label=label,
        )
        bottom += values
    set_mode_axis(ax)
    ax.set_ylabel("Cost per run (USD)")
    ax.legend(frameon=False, loc="upper left")
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.6)


def status_stacked_bars(ax: plt.Axes, summary: pd.DataFrame) -> None:
    x = mode_positions()
    bottom = np.zeros(len(MODE_ORDER))
    v2_count = summary[["agent_finished", "time_limit", "infrastructure_failure"]].fillna(0).to_numpy().sum()
    specs = (
        [
            ("Agent finished", "agent_finished", "#4C78A8"),
            ("Time limit", "time_limit", "#F58518"),
            ("Infrastructure failure", "infrastructure_failure", "#E45756"),
        ]
        if v2_count > 0
        else [
            ("Completed", "completed", "#4C78A8"),
            ("Max turns", "max_turns", "#F58518"),
            ("Failed", "failed", "#E45756"),
        ]
    )
    for label, col, color in specs:
        values = np.nan_to_num(summary[col].to_numpy(dtype=float), nan=0.0)
        ax.bar(x, values, bottom=bottom, color=color, edgecolor="black", linewidth=0.6, label=label)
        bottom += values
    set_mode_axis(ax)
    ax.set_ylabel("Runs")
    max_n = summary["n"].max()
    if pd.isna(max_n):
        max_n = 0
    ax.set_ylim(0, max(1, int(max_n)) + 1)
    ax.legend(frameon=False, loc="upper left")
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.6)


def score_heatmap(ax: plt.Axes, df: pd.DataFrame, score_col: str, title: str, vmax: float, cmap: str = "viridis") -> None:
    pivot = (
        df.pivot_table(index="paper_short", columns="mode", values=score_col, aggfunc="mean")
        .reindex(columns=MODE_ORDER)
        .sort_index()
    )
    image = ax.imshow(pivot.to_numpy(dtype=float), aspect="auto", vmin=0, vmax=vmax, cmap=cmap)
    ax.set_title(title)
    ax.set_xticks(np.arange(len(MODE_ORDER)))
    ax.set_xticklabels([MODE_LABELS[mode] for mode in MODE_ORDER], rotation=30, ha="right")
    ax.set_yticks(np.arange(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    ax.tick_params(length=0)
    for y in range(pivot.shape[0]):
        for x in range(pivot.shape[1]):
            value = pivot.iat[y, x]
            if pd.notna(value):
                label = f"{value:.2f}" if vmax <= 1 else f"{value:.0f}"
                ax.text(x, y, label, ha="center", va="center", fontsize=6, color="white")
    return image


def efficiency_scatter(
    ax: plt.Axes,
    summary: pd.DataFrame,
    x_col: str = "total_tokens_m_mean",
    xlabel: str = "Mean total tokens per run (million)",
) -> None:
    for _, row in summary.iterrows():
        if pd.isna(row.get(x_col)) or pd.isna(row.get("quality_mean")):
            continue
        mode = row["mode"]
        ax.scatter(
            row[x_col],
            row["quality_mean"],
            s=70,
            color=MODE_COLORS[mode],
            edgecolor="black",
            linewidth=0.7,
            zorder=3,
        )
        ax.text(
            row[x_col] * 1.02,
            row["quality_mean"],
            MODE_LABELS[mode],
            va="center",
            fontsize=8,
        )
    ax.set_xlabel(xlabel)
    ax.set_ylabel(QUALITY_SCORE_YLABEL)
    ax.set_ylim(0, 1.05)
    ax.grid(color="#DDDDDD", linewidth=0.6)


def pareto_front_rows(pareto: pd.DataFrame) -> pd.DataFrame:
    front = []
    best_quality = -np.inf
    for _, row in pareto.sort_values("total_tokens_m_mean").iterrows():
        if row["quality_mean"] > best_quality:
            front.append(row)
            best_quality = row["quality_mean"]
    return pd.DataFrame(front)


def cost_quality_pareto_scatter(
    ax: plt.Axes,
    pareto: pd.DataFrame,
    raw: pd.DataFrame | None = None,
    ylabel: str = QUALITY_SCORE_YLABEL,
    x_mean_col: str = "total_tokens_m_mean",
    x_median_col: str = "total_tokens_m_median",
    x_raw_col: str = "total_tokens_m",
    xlabel: str = "Total tokens per run (million, log scale)",
    legend_caption: str = "Small points: runs; circle: mean; diamond: median",
) -> None:
    if pareto.empty:
        ax.text(0.5, 0.5, "No cost-quality data", transform=ax.transAxes, ha="center", va="center")
        ax.set_axis_off()
        return
    if raw is not None and not raw.empty:
        for mode in MODE_ORDER:
            mode_raw = raw.loc[raw["mode"] == mode]
            if mode_raw.empty:
                continue
            ax.scatter(
                mode_raw[x_raw_col],
                mode_raw["quality_score"],
                s=20,
                color=MODE_COLORS.get(mode, "#999999"),
                edgecolor="none",
                alpha=0.35,
                zorder=1,
            )
    for _, row in pareto.iterrows():
        mode = row["mode"]
        ax.scatter(
            row[x_mean_col],
            row["quality_mean"],
            s=70,
            color=MODE_COLORS.get(mode, "#999999"),
            edgecolor="black",
            linewidth=0.7,
            zorder=3,
            label=MODE_LABELS.get(mode, mode),
        )
        if pd.notna(row.get(x_median_col)) and pd.notna(row.get("quality_median")):
            ax.scatter(
                row[x_median_col],
                row["quality_median"],
                s=70,
                marker="D",
                facecolors="white",
                edgecolor=MODE_COLORS.get(mode, "#999999"),
                linewidth=1.2,
                zorder=4,
            )
    ax.set_xscale("log")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, 1.05)
    ax.grid(color="#DDDDDD", linewidth=0.6)
    ax.legend(
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.18),
        ncols=min(len(pareto), 3),
        title=legend_caption,
        title_fontsize=8,
    )


def attempt_self_score_lineplots(attempts: pd.DataFrame, output_dir: Path, formats: Iterable[str]) -> None:
    if attempts.empty:
        return
    attempts = attempt_self_score_plot_rows(attempts)
    if attempts.empty or "paper_short" not in attempts.columns:
        return
    papers = sorted(attempts["paper_short"].dropna().unique())
    if not papers:
        return
    cols = 2 if len(papers) > 1 else 1
    rows = int(math.ceil(len(papers) / cols))
    fig, axes = plt.subplots(
        rows,
        cols,
        figsize=(5.8 * cols, 3.2 * rows),
        constrained_layout=True,
        squeeze=False,
    )
    for ax in axes.ravel()[len(papers) :]:
        ax.set_axis_off()
    modes_drawn = []
    for ax, paper in zip(axes.ravel(), papers):
        paper_df = attempts.loc[attempts["paper_short"] == paper]
        for mode in ordered_modes_in_attempts(paper_df):
            mode_df = paper_df.loc[paper_df["mode"] == mode]
            if mode_df.empty:
                continue
            color = MODE_COLORS.get(mode, "#999999")
            for _, run_df in mode_df.groupby("_attempt_run_key", sort=True, dropna=False):
                run_df = sort_attempt_run_rows(run_df)
                ax.plot(
                    run_df["attempt_number"].to_numpy(dtype=float),
                    run_df["self_score"].to_numpy(dtype=float),
                    linewidth=1.2,
                    color=color,
                    alpha=0.38,
                    marker="o",
                    markersize=3,
                )
                modes_drawn.append(mode)
        ax.set_title(paper)
        ax.set_xlabel("Attempt")
        ax.set_ylabel("Self-reported score / 8")
        ax.set_ylim(0, 8.4)
        ax.grid(color="#DDDDDD", linewidth=0.6)
    handles = attempt_mode_legend_handles(modes_drawn)
    if handles:
        fig.legend(
            handles,
            [handle.get_label() for handle in handles],
            loc="lower center",
            bbox_to_anchor=(0.5, -0.02),
            ncols=min(len(handles), 5),
            frameon=False,
        )
    fig.suptitle("Agent self-reported reproduction score over attempts", fontsize=13, fontweight="bold", y=1.02)
    save_figure(fig, output_dir, "attempt_self_scores_by_paper", formats)
    plt.close(fig)


def aggregate_attempt_self_score_lineplot(attempts: pd.DataFrame, output_dir: Path, formats: Iterable[str]) -> None:
    if attempts.empty:
        return
    attempts = attempt_self_score_plot_rows(attempts)
    if attempts.empty:
        return
    fig, ax = plt.subplots(figsize=(7.2, 4.2), constrained_layout=True)
    modes_drawn = []
    group_columns = [column for column in ["paper_short", "_attempt_run_key"] if column in attempts.columns]
    for mode in ordered_modes_in_attempts(attempts):
        mode_df = attempts.loc[attempts["mode"] == mode]
        if mode_df.empty:
            continue
        color = MODE_COLORS.get(mode, "#999999")
        for _, run_df in mode_df.groupby(group_columns, sort=True, dropna=False):
            run_df = sort_attempt_run_rows(run_df)
            ax.plot(
                run_df["attempt_number"].to_numpy(dtype=float),
                run_df["self_score"].to_numpy(dtype=float),
                linewidth=1.3,
                color=color,
                alpha=0.38,
                marker="o",
                markersize=3,
            )
            modes_drawn.append(mode)
    ax.set_xlabel("Attempt")
    ax.set_ylabel("Self-reported score / 8")
    ax.set_ylim(0, 8.4)
    ax.grid(color="#DDDDDD", linewidth=0.6)
    handles = attempt_mode_legend_handles(modes_drawn)
    if handles:
        ax.legend(
            handles=handles,
            frameon=False,
            loc="upper center",
            bbox_to_anchor=(0.5, -0.16),
            ncols=min(len(handles), 5),
        )
    ax.set_title("Agent self-reported reproduction score over attempts")
    save_figure(fig, output_dir, "attempt_self_scores_by_mode", formats)
    plt.close(fig)


def attempt_self_score_plot_rows(attempts: pd.DataFrame) -> pd.DataFrame:
    work = add_raw_attempt_self_score(attempts)
    required = {"mode", "attempt_number", "self_score"}
    if not required.issubset(work.columns):
        return pd.DataFrame()
    work = work.dropna(subset=["attempt_number", "self_score"]).copy()
    if work.empty:
        return work
    work["_attempt_run_key"] = [attempt_run_key(index, row) for index, row in work.iterrows()]
    return work


def attempt_run_key(index: object, row: pd.Series) -> str:
    run_id = clean_string(row.get("run_id"))
    if run_id:
        return f"run:{run_id}"
    repetition = row.get("repetition")
    if pd.notna(repetition):
        return f"rep:{repetition}"
    attempt_dir = clean_string(row.get("attempt_dir"))
    if attempt_dir:
        return f"dir:{Path(attempt_dir).parent}"
    return f"row:{index}"


def ordered_modes_in_attempts(attempts: pd.DataFrame) -> list:
    modes = list(dict.fromkeys(attempts["mode"].dropna().tolist()))
    return [mode for mode in MODE_ORDER if mode in modes] + sorted(
        [mode for mode in modes if mode not in MODE_ORDER],
        key=str,
    )


def sort_attempt_run_rows(attempts: pd.DataFrame) -> pd.DataFrame:
    sort_columns = ["attempt_number"]
    for column in ["attempt_json_path", "attempt_dir"]:
        if column in attempts.columns:
            sort_columns.append(column)
            break
    return attempts.sort_values(sort_columns)


def attempt_mode_legend_handles(modes: Iterable[object]) -> list[Line2D]:
    return [
        Line2D(
            [0],
            [0],
            color=MODE_COLORS.get(mode, "#999999"),
            marker="o",
            linewidth=1.4,
            markersize=4,
            label=MODE_LABELS.get(mode, mode),
        )
        for mode in ordered_modes_from_values(modes)
    ]


def ordered_modes_from_values(modes: Iterable[object]) -> list:
    unique_modes = list(dict.fromkeys(mode for mode in modes if pd.notna(mode)))
    return [mode for mode in MODE_ORDER if mode in unique_modes] + sorted(
        [mode for mode in unique_modes if mode not in MODE_ORDER],
        key=str,
    )


def add_raw_attempt_self_score(attempts: pd.DataFrame) -> pd.DataFrame:
    work = attempts.copy()
    if "self_score" not in work.columns and "normalized_self_score" in work.columns:
        work["self_score"] = work["normalized_self_score"] * 8.0
    return work


def save_figure(fig: plt.Figure, output_dir: Path, stem: str, formats: Iterable[str]) -> None:
    for fmt in formats:
        fig.savefig(output_dir / f"{stem}.{fmt}", bbox_inches="tight")


def cohort_panel_title(view: dict) -> str:
    subset = view["df"]
    paper_count = subset["paper"].nunique() if "paper" in subset.columns else 0
    return f"{view['paper_cohort_label']}\n{paper_count} papers, {len(subset)} runs"


def synchronize_y_limits(axes: Iterable[plt.Axes]) -> None:
    axes = list(axes)
    bottoms = [ax.get_ylim()[0] for ax in axes]
    tops = [ax.get_ylim()[1] for ax in axes]
    bottom = min(bottoms)
    top = max(tops)
    if math.isfinite(bottom) and math.isfinite(top) and top > bottom:
        for ax in axes:
            ax.set_ylim(bottom, top)


def move_legend_to_figure(fig: plt.Figure, axes: Iterable[plt.Axes], ncols: int) -> None:
    axes = list(axes)
    handles: list = []
    labels: list[str] = []
    for ax in axes:
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            break
    for ax in axes:
        legend = ax.get_legend()
        if legend is not None:
            legend.remove()
    if handles:
        fig.legend(
            handles,
            labels,
            loc="lower center",
            bbox_to_anchor=(0.5, -0.04),
            ncols=ncols,
            frameon=False,
        )


def make_cohort_bar_figure(
    df: pd.DataFrame,
    output_dir: Path,
    formats: Iterable[str],
    stem: str,
    title: str,
    plotter,
    legend_ncols: int = 0,
) -> None:
    views = paper_cohort_views(df)
    fig, axes = plt.subplots(1, len(views), figsize=(12.2, 3.9), constrained_layout=True, squeeze=False)
    axes = axes.ravel()
    for index, (ax, view) in enumerate(zip(axes, views)):
        summary = summarize_by_mode(view["df"])
        plotter(ax, summary, view["df"])
        ax.set_title(cohort_panel_title(view))
        if index > 0:
            ax.set_ylabel("")
    synchronize_y_limits(axes)
    if legend_ncols:
        move_legend_to_figure(fig, axes, legend_ncols)
    fig.suptitle(title, fontsize=12, fontweight="bold", y=1.06)
    save_figure(fig, output_dir, stem, formats)
    plt.close(fig)


def make_score_box_grid_figure(df: pd.DataFrame, output_dir: Path, formats: Iterable[str]) -> None:
    df = ensure_score_columns(ensure_paper_cohort_columns(df))
    views = paper_cohort_views(df)
    score_box_specs = SCORE_BOX_SPECS + [
        {
            "point_col": spec["point_col"],
            "divisor": 1.0,
            "ylabel": spec["box_ylabel"],
        }
        for spec in available_biological_score_specs(df)
    ]
    fig, axes = plt.subplots(
        len(score_box_specs),
        len(views),
        figsize=(12.6, 2.4 * len(score_box_specs) + 1.4),
        constrained_layout=True,
        squeeze=False,
        sharey="row",
    )
    for row_index, spec in enumerate(score_box_specs):
        for col_index, view in enumerate(views):
            ax = axes[row_index, col_index]
            score_boxplot(
                ax,
                view["df"],
                spec["point_col"],
                spec["divisor"],
                ylabel=spec["ylabel"] if col_index == 0 else "",
                show_x_labels=row_index == len(score_box_specs) - 1,
            )
            if row_index == 0:
                ax.set_title(cohort_panel_title(view))

    fig.legend(
        handles=[
            Line2D([0], [0], color="black", linewidth=1.2, label="Median"),
            Line2D(
                [0],
                [0],
                marker="D",
                color="none",
                markerfacecolor="white",
                markeredgecolor="black",
                markersize=4,
                label="Mean",
            ),
        ],
        loc="lower center",
        bbox_to_anchor=(0.5, -0.01),
        ncols=2,
        frameon=False,
    )
    fig.suptitle("Benchmark score distributions by mode and paper cohort", fontsize=12, fontweight="bold", y=1.02)
    save_figure(fig, output_dir, "score_distributions_by_mode", formats)
    plt.close(fig)


def make_stacked_bar_and_box_figure(
    df: pd.DataFrame,
    output_dir: Path,
    formats: Iterable[str],
    stem: str,
    title: str,
    stacked_plotter,
    value_col: str,
    box_ylabel: str,
) -> None:
    summary = summarize_by_mode(df)
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.9), constrained_layout=True)
    stacked_plotter(axes[0], summary)
    axes[0].set_title("Mean component breakdown")
    metric_boxplot(axes[1], df, value_col, box_ylabel)
    axes[1].set_title("Total distribution")
    fig.suptitle(title, fontsize=12, fontweight="bold", y=1.04)
    save_figure(fig, output_dir, stem, formats)
    plt.close(fig)


def make_cohort_bar_figures(df: pd.DataFrame, output_dir: Path, formats: Iterable[str]) -> None:
    make_score_box_grid_figure(df, output_dir, formats)
    make_cohort_bar_figure(
        df,
        output_dir,
        formats,
        "runtime_breakdown_by_mode",
        "End-to-end runtime split by paper cohort",
        lambda ax, summary, subset: time_stacked_bars(ax, summary),
        legend_ncols=2,
    )
    make_stacked_bar_and_box_figure(
        df,
        output_dir,
        formats,
        "token_usage_by_mode",
        "Token use by mode",
        token_stacked_bars,
        "total_tokens_m",
        "Total tokens per run (million)",
    )
    make_stacked_bar_and_box_figure(
        df,
        output_dir,
        formats,
        "api_cost_by_mode",
        "API cost by mode",
        usd_cost_stacked_bars,
        "total_cost_usd",
        "Total cost per run (USD)",
    )
    make_cohort_bar_figure(
        df,
        output_dir,
        formats,
        "run_outcomes_by_mode",
        "Run outcomes by paper cohort",
        lambda ax, summary, subset: status_stacked_bars(ax, summary),
        legend_ncols=3,
    )


def make_full_figure(df: pd.DataFrame, summary: pd.DataFrame, output_dir: Path, formats: Iterable[str]) -> None:
    biological_specs = available_biological_score_specs(df, summary)
    has_biology = bool(biological_specs)
    rows = 4 if has_biology else 3
    fig = plt.figure(figsize=(11.2, 9.2 if has_biology else 7.2), constrained_layout=True)
    gs = fig.add_gridspec(rows, 2, height_ratios=[1.05, 1.0, 1.25, 1.25] if has_biology else [1.05, 1.0, 1.25])

    score_ax = fig.add_subplot(gs[0, 0])
    time_ax = fig.add_subplot(gs[0, 1])
    token_ax = fig.add_subplot(gs[1, :])
    technical_ax = fig.add_subplot(gs[2, 0])
    reproduction_ax = fig.add_subplot(gs[2, 1])
    biological_axes = [fig.add_subplot(gs[3, 0]), fig.add_subplot(gs[3, 1])] if has_biology else []

    grouped_score_boxplots(score_ax, df)
    score_ax.set_title("Benchmark quality score distributions")
    add_panel_label(score_ax, "a")

    time_stacked_bars(time_ax, summary)
    time_ax.set_title("Runtime split")
    add_panel_label(time_ax, "b")

    token_stacked_bars(token_ax, summary)
    token_ax.set_title("Token use")
    add_panel_label(token_ax, "c")

    image = score_heatmap(technical_ax, df, "technical_score", "Technical score by paper", 7)
    add_panel_label(technical_ax, "d")
    cbar = fig.colorbar(image, ax=technical_ax, shrink=0.8, pad=0.01)
    cbar.set_label("Technical score")

    image = score_heatmap(reproduction_ax, df, "reproduction_score", "Reproduction score (self-reported) by paper", 8)
    add_panel_label(reproduction_ax, "e")
    cbar = fig.colorbar(image, ax=reproduction_ax, shrink=0.8, pad=0.01)
    cbar.set_label("Reproduction score (self-reported)")

    if has_biology:
        for index, spec in enumerate(biological_specs[:2]):
            ax = biological_axes[index]
            image = score_heatmap(ax, df, spec["point_col"], f"{spec['title']} by paper", 1, cmap="Greens")
            add_panel_label(ax, chr(ord("f") + index))
            cbar = fig.colorbar(image, ax=ax, shrink=0.8, pad=0.01)
            cbar.set_label(spec["title"])
        for ax in biological_axes[len(biological_specs[:2]) :]:
            ax.set_axis_off()

    fig.suptitle("Benchmark comparison across agent modes", fontsize=13, fontweight="bold")
    save_figure(fig, output_dir, "mode_comparison_overview", formats)
    plt.close(fig)


def make_companion_figures(df: pd.DataFrame, summary: pd.DataFrame, output_dir: Path, formats: Iterable[str]) -> None:
    df = ensure_cost_columns(df)
    make_cohort_bar_figures(df, output_dir, formats)

    fig, axes = plt.subplots(1, 4, figsize=(13.8, 3.6), constrained_layout=True)
    metric_boxplot(axes[0], df, "duration_h", "Wall time per run (h)")
    axes[0].set_title("Wall time")
    morpheus_col = (
        "morpheus_active_min"
        if "morpheus_active_min" in df.columns and df["morpheus_active_min"].fillna(0).gt(0).any()
        else "morpheus_time_min"
    )
    metric_boxplot(axes[1], df, morpheus_col, "Time with Morpheus running (min)")
    axes[1].set_title("Morpheus running")
    metric_boxplot(axes[2], df, "total_tokens_m", "Tokens per run (million)")
    axes[2].set_title("Token use")
    metric_boxplot(axes[3], df, "total_cost_usd", "Cost per run (USD)")
    axes[3].set_title("API cost")
    save_figure(fig, output_dir, "resource_usage_by_mode", formats)
    plt.close(fig)

    biological_specs = available_biological_score_specs(df, summary)
    heatmap_count = 2 + len(biological_specs)
    fig, axes = plt.subplots(1, heatmap_count, figsize=(5.5 * heatmap_count, 5.2), constrained_layout=True)
    axes = np.atleast_1d(axes)
    image = score_heatmap(axes[0], df, "technical_score", "Technical score", 7)
    fig.colorbar(image, ax=axes[0], shrink=0.85, pad=0.01)
    image = score_heatmap(axes[1], df, "reproduction_score", "Reproduction score (self-reported)", 8)
    fig.colorbar(image, ax=axes[1], shrink=0.85, pad=0.01)
    for index, spec in enumerate(biological_specs, start=2):
        image = score_heatmap(axes[index], df, spec["point_col"], spec["title"], 1, cmap="Greens")
        fig.colorbar(image, ax=axes[index], shrink=0.85, pad=0.01)
    save_figure(fig, output_dir, "scores_by_paper", formats)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(12.8, 3.7), constrained_layout=True)
    status_stacked_bars(axes[0], summary)
    axes[0].set_title("Run outcomes")
    efficiency_scatter(axes[1], summary)
    axes[1].set_title("Quality/token trade-off")
    efficiency_scatter(axes[2], summary, x_col="total_cost_usd_mean", xlabel="Mean API cost per run (USD)")
    axes[2].set_title("Quality/API-cost trade-off")
    save_figure(fig, output_dir, "outcomes_and_efficiency", formats)
    plt.close(fig)

    pareto = cost_quality_records(df)
    raw_pareto = cost_quality_raw_records(df)
    fig, ax = plt.subplots(figsize=(6.2, 4.0), constrained_layout=True)
    cost_quality_pareto_scatter(ax, pareto, raw_pareto, legend_caption=QUALITY_SCORE_FALLBACK_NOTE)
    ax.set_title("Token-quality Pareto comparison")
    save_figure(fig, output_dir, "token_quality_pareto", formats)
    plt.close(fig)

    dollar_pareto = dollar_cost_quality_records(df)
    dollar_raw_pareto = dollar_cost_quality_raw_records(df)
    fig, ax = plt.subplots(figsize=(6.2, 4.0), constrained_layout=True)
    cost_quality_pareto_scatter(
        ax,
        dollar_pareto,
        dollar_raw_pareto,
        x_mean_col="total_cost_usd_mean",
        x_median_col="total_cost_usd_median",
        x_raw_col="total_cost_usd",
        xlabel="API cost per run (USD, log scale)",
        legend_caption=QUALITY_SCORE_FALLBACK_NOTE,
    )
    ax.set_title("API cost-quality Pareto comparison")
    save_figure(fig, output_dir, "api_cost_quality_pareto", formats)
    plt.close(fig)

    if biological_specs:
        fig, axes = plt.subplots(
            1,
            len(biological_specs),
            figsize=(6.2 * len(biological_specs), 4.0),
            constrained_layout=True,
            squeeze=False,
        )
        for ax, spec in zip(axes.ravel(), biological_specs):
            biological_pareto = cost_single_score_records(df, spec["point_col"])
            biological_raw_pareto = cost_single_score_raw_records(df, spec["point_col"])
            cost_quality_pareto_scatter(ax, biological_pareto, biological_raw_pareto, ylabel=f"Mean {spec['title'].lower()}")
            ax.set_title(f"Token-{spec['title'].lower()} Pareto comparison")
        save_figure(fig, output_dir, "token_biological_score_pareto", formats)
        plt.close(fig)

        fig, axes = plt.subplots(
            1,
            len(biological_specs),
            figsize=(6.2 * len(biological_specs), 4.0),
            constrained_layout=True,
            squeeze=False,
        )
        for ax, spec in zip(axes.ravel(), biological_specs):
            biological_pareto = dollar_cost_single_score_records(df, spec["point_col"])
            biological_raw_pareto = dollar_cost_single_score_raw_records(df, spec["point_col"])
            cost_quality_pareto_scatter(
                ax,
                biological_pareto,
                biological_raw_pareto,
                ylabel=f"Mean {spec['title'].lower()}",
                x_mean_col="total_cost_usd_mean",
                x_median_col="total_cost_usd_median",
                x_raw_col="total_cost_usd",
                xlabel="API cost per run (USD, log scale)",
            )
            ax.set_title(f"API cost-{spec['title'].lower()} Pareto comparison")
        save_figure(fig, output_dir, "api_cost_biological_score_pareto", formats)
        plt.close(fig)


def has_biological_scores(df: pd.DataFrame) -> bool:
    return bool(available_biological_score_specs(df))


def write_tables(
    df: pd.DataFrame,
    summary: pd.DataFrame,
    attempts: pd.DataFrame,
    biological_clauses: pd.DataFrame,
    output_dir: Path,
    execution_records: pd.DataFrame | None = None,
) -> None:
    if execution_records is None:
        execution_records = pd.DataFrame()
    v2_only = "protocol" in df.columns and len(df) > 0 and set(df["protocol"].dropna()) == {"time_limit_v2"}
    run_table = df.drop(columns=["mode_rank"])
    mode_table = summary
    cohort_table = summarize_by_paper_cohort_and_mode(df)
    if v2_only:
        run_table = run_table.drop(columns=["cycles"], errors="ignore")
        legacy_columns = ["completed", "max_turns", "failed", "cycles_mean", "legacy_v1_cycles_mean"]
        mode_table = mode_table.drop(columns=legacy_columns, errors="ignore")
        cohort_table = cohort_table.drop(columns=legacy_columns, errors="ignore")
    run_table.to_csv(output_dir / "benchmark_analysis_by_run.csv", index=False)
    mode_table.to_csv(output_dir / "benchmark_analysis_by_mode.csv", index=False)
    cohort_table.to_csv(
        output_dir / "benchmark_analysis_by_paper_cohort_and_mode.csv",
        index=False,
    )
    cost_quality_records(df).to_csv(output_dir / "benchmark_cost_quality_by_mode.csv", index=False)
    dollar_cost_quality_records(df).to_csv(output_dir / "benchmark_dollar_cost_quality_by_mode.csv", index=False)
    attempts.to_csv(output_dir / "benchmark_attempt_self_scores.csv", index=False)
    biological_clauses.to_csv(output_dir / "benchmark_biological_scores.csv", index=False)
    execution_records.to_csv(output_dir / "benchmark_execution_audit.csv", index=False)


def main() -> None:
    args = parse_args()
    benchmark_dir = Path(args.benchmark_dir).resolve()
    output_dir = Path(args.out_dir).resolve() if args.out_dir else benchmark_dir / "analysis_figures"
    output_dir.mkdir(parents=True, exist_ok=True)

    configure_matplotlib()
    summary_json = load_summary(benchmark_dir)
    df = records_from_summary(summary_json, benchmark_dir)
    summary = summarize_by_mode(df)
    attempts = attempt_records_from_summary(summary_json, benchmark_dir)
    biological_clauses = biological_clause_records_from_summary(summary_json, benchmark_dir)
    execution_records = execution_records_from_summary(summary_json, benchmark_dir)

    write_tables(df, summary, attempts, biological_clauses, output_dir, execution_records)
    make_full_figure(df, summary, output_dir, args.formats)
    make_companion_figures(df, summary, output_dir, args.formats)
    attempt_self_score_lineplots(attempts, output_dir, args.formats)
    aggregate_attempt_self_score_lineplot(attempts, output_dir, args.formats)

    print(f"Wrote analysis for {len(df)} runs to {output_dir}")
    if len(attempts):
        print(f"Wrote {len(attempts)} attempt-level self-score records")
    columns = ["mode", "technical_mean", "technical_std", "reproduction_mean", "reproduction_std"]
    if "biological_mean" in summary.columns:
        columns.extend(["biological_mean", "biological_std"])
    if (
        "manual_biological_mean" in summary.columns
        and "manual_biological_score" in df.columns
        and df["manual_biological_score"].notna().any()
    ):
        columns.extend(["manual_biological_mean", "manual_biological_std"])
    print(summary[columns].to_string(index=False))


if __name__ == "__main__":
    main()
