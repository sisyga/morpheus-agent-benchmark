from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Iterable

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
JOIN_KEYS = ["canonical_paper_stem", "mode", "repetition"]
RUN_ID_PATTERN = re.compile(r"^\d{8}_\d{6}_(?P<paper>.+?)__(?P<mode>.+?)__rep(?P<rep>\d+)$")
WINDOWS_DRIVE_PATH_PATTERN = re.compile(r"^([A-Za-z]):[\\/]*(.*)$")
HEATMAP_BIN_WIDTH = 0.1
HEATMAP_BINS = round(1 / HEATMAP_BIN_WIDTH)
HEATMAP_EMPTY_COLOR = "white"
SCORE_TOLERANCE = 1e-6
REPORT_ROW_LIMIT = 10

MANUAL_REQUIRED_COLUMNS = {
    "canonical_paper_stem",
    "manual_paper_number",
    "paper_key",
    "paper_title",
    "workbook_run_id",
    "mode",
    "mode_label",
    "repetition",
    "manual_score",
    "manual_score_source",
}
AGENT_REQUIRED_COLUMNS = {"mode", "score"}

COMPARISON_COLUMNS = [
    "canonical_paper_stem",
    "manual_paper_number",
    "paper_key",
    "paper_title",
    "workbook_run_id",
    "mode",
    "mode_label",
    "repetition",
    "manual_score",
    "manual_score_source",
    "agent_biological_score",
    "agent_biological_status",
    "score_delta",
    "abs_error",
    "join_status",
    "agent_run_id",
    "agent_score_path",
    "agent_clause_count",
    "agent_score_conflict",
]


def compare_manual_to_agent(manual_csv: str | Path, agent_scores: str | Path) -> pd.DataFrame:
    manual = load_manual_scores(manual_csv)
    agent = load_agent_scores(agent_scores)
    if manual.empty and agent.empty:
        return pd.DataFrame(columns=COMPARISON_COLUMNS)

    rows = manual.merge(agent, on=JOIN_KEYS, how="outer", indicator=True, suffixes=("", "_agent"))
    rows["mode_label"] = rows["mode_label"].fillna(rows.get("agent_mode_label", pd.Series(dtype=object)))
    rows["mode_label"] = rows["mode_label"].fillna(rows["mode"].map(MODE_LABELS)).fillna(rows["mode"])
    rows["score_delta"] = rows["agent_biological_score"] - rows["manual_score"]
    rows["abs_error"] = rows["score_delta"].abs()
    rows["join_status"] = rows.apply(join_status, axis=1)
    rows = rows.drop(columns=["_merge", "agent_mode_label"], errors="ignore")
    for column in COMPARISON_COLUMNS:
        if column not in rows.columns:
            rows[column] = np.nan
    rows["_mode_rank"] = rows["mode"].map({mode: index for index, mode in enumerate(MODE_ORDER)}).fillna(999)
    rows["_paper_rank"] = rows["canonical_paper_stem"].map(paper_number_from_stem).fillna(999)
    rows = rows.sort_values(["_paper_rank", "canonical_paper_stem", "_mode_rank", "mode", "repetition"]).drop(
        columns=["_paper_rank", "_mode_rank"]
    )
    return rows[COMPARISON_COLUMNS].reset_index(drop=True)


def load_manual_scores(manual_csv: str | Path) -> pd.DataFrame:
    path = Path(manual_csv)
    rows = pd.read_csv(path)
    missing = sorted(MANUAL_REQUIRED_COLUMNS.difference(rows.columns))
    if missing:
        raise ValueError(f"Manual score CSV is missing required columns: {', '.join(missing)}")
    rows = rows.copy()
    rows["canonical_paper_stem"] = rows["canonical_paper_stem"].map(canonical_stem)
    rows["mode"] = rows["mode"].map(clean_string)
    rows["mode_label"] = rows["mode_label"].fillna(rows["mode"].map(MODE_LABELS)).fillna(rows["mode"])
    rows["repetition"] = rows["repetition"].map(positive_int_or_nan)
    rows["manual_score"] = pd.to_numeric(rows["manual_score"], errors="coerce")
    return rows[
        [
            "canonical_paper_stem",
            "manual_paper_number",
            "paper_key",
            "paper_title",
            "workbook_run_id",
            "mode",
            "mode_label",
            "repetition",
            "manual_score",
            "manual_score_source",
        ]
    ]


def load_agent_scores(agent_scores: str | Path) -> pd.DataFrame:
    path = Path(agent_scores)
    if path.is_dir():
        json_rows = scan_agent_score_jsons(path)
        if not json_rows.empty:
            return json_rows
        csv_path = first_existing(
            [
                path / "benchmark_biological_scores.csv",
                path / "analysis_figures" / "benchmark_biological_scores.csv",
            ]
        )
        if csv_path is not None:
            return load_agent_scores_csv(csv_path)
        return empty_agent_scores()
    if path.suffix.lower() == ".csv":
        return load_agent_scores_csv(path)
    if path.name == "biological_score.json":
        return agent_rows_from_score_json(path)
    raise ValueError(f"Unsupported agent score input: {path}")


def load_agent_scores_csv(path: str | Path) -> pd.DataFrame:
    rows = pd.read_csv(path)
    missing = sorted(AGENT_REQUIRED_COLUMNS.difference(rows.columns))
    if missing:
        raise ValueError(f"Agent score CSV is missing required columns: {', '.join(missing)}")

    rows = rows.copy()
    run_parts = rows.get("run_id", pd.Series([""] * len(rows), index=rows.index)).map(parse_run_id)
    if "canonical_paper_stem" not in rows.columns:
        paper_values = rows.get("paper", pd.Series([""] * len(rows), index=rows.index))
        rows["canonical_paper_stem"] = [
            canonical_stem(paper) or parsed["canonical_paper_stem"] for paper, parsed in zip(paper_values, run_parts)
        ]
    rows["mode"] = [
        clean_string(mode) or parsed["mode"] for mode, parsed in zip(rows["mode"], run_parts)
    ]
    if "repetition" not in rows.columns:
        rows["repetition"] = [parsed["repetition"] for parsed in run_parts]
    else:
        rows["repetition"] = [
            positive_int_or_nan(value) if not math.isnan(positive_int_or_nan(value)) else parsed["repetition"]
            for value, parsed in zip(rows["repetition"], run_parts)
        ]
    if "mode_label" not in rows.columns:
        rows["mode_label"] = rows["mode"].map(MODE_LABELS).fillna(rows["mode"])
    rows["score"] = pd.to_numeric(rows["score"], errors="coerce")
    rows["status"] = rows.get("status", "")
    rows["run_id"] = rows.get("run_id", "")
    rows["biological_score_path"] = rows.get("biological_score_path", "")
    return collapse_agent_rows(rows)


def scan_agent_score_jsons(benchmark_dir: str | Path) -> pd.DataFrame:
    records = []
    for score_path in agent_score_json_paths(Path(benchmark_dir)):
        records.extend(agent_records_from_score_payload(score_path, read_json(score_path)))
    if not records:
        return empty_agent_scores()
    return collapse_agent_rows(pd.DataFrame.from_records(records))


def agent_score_json_paths(benchmark_dir: Path) -> list[Path]:
    summary_path = benchmark_dir / "benchmark_summary.json"
    if summary_path.exists():
        try:
            summary = read_json(summary_path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            summary = {}
        summary_paths = []
        for result in summary.get("results", []):
            if not isinstance(result, dict):
                continue
            run_id = clean_string(result.get("runId"))
            run_dir = benchmark_dir / run_id if run_id else benchmark_dir
            explicit = clean_string(result.get("biologicalScorePath"))
            score_path = Path(explicit) if explicit else run_dir / "biological_score.json"
            if explicit and not score_path.is_absolute():
                score_path = run_dir / score_path
            if score_path.exists():
                summary_paths.append(score_path)
        if summary_paths:
            return sorted(set(summary_paths))

    paths = list(benchmark_dir.glob("*/biological_score.json"))
    paths.extend(benchmark_dir.glob("*/biological_scores/*.json"))
    return sorted(set(paths))


def agent_rows_from_score_json(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    return collapse_agent_rows(pd.DataFrame.from_records(agent_records_from_score_payload(path, read_json(path))))


def agent_records_from_score_payload(score_path: Path, payload: dict) -> list[dict[str, object]]:
    run_id = clean_string(payload.get("runId")) or score_path.parent.name
    parsed = parse_run_id(run_id)
    paper = clean_string(payload.get("paper")) or parsed["canonical_paper_stem"]
    mode = clean_string(payload.get("mode")) or parsed["mode"]
    repetition = positive_int_or_nan(payload.get("repetition"))
    if math.isnan(repetition):
        repetition = parsed["repetition"]
    clauses = payload.get("clauses")
    clause_count = len(clauses) if isinstance(clauses, list) else 0
    return [
        {
            "canonical_paper_stem": canonical_stem(paper) or parsed["canonical_paper_stem"],
            "mode": mode,
            "mode_label": MODE_LABELS.get(mode, mode),
            "run_id": run_id,
            "repetition": repetition,
            "status": clean_string(payload.get("status")),
            "score": nullable_number(payload.get("score")),
            "clause_id": "",
            "biological_score_path": str(score_path),
            "_json_clause_count": clause_count,
        }
    ]


def collapse_agent_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return empty_agent_scores()
    rows = rows.copy()
    rows["canonical_paper_stem"] = rows["canonical_paper_stem"].map(canonical_stem)
    rows["mode"] = rows["mode"].map(clean_string)
    rows["mode_label"] = rows["mode_label"].fillna(rows["mode"].map(MODE_LABELS)).fillna(rows["mode"])
    rows["repetition"] = rows["repetition"].map(positive_int_or_nan)
    rows["score"] = pd.to_numeric(rows["score"], errors="coerce")

    records = []
    group_columns = ["canonical_paper_stem", "mode", "repetition", "run_id"]
    for group_values, group in rows.groupby(group_columns, dropna=False, sort=False):
        scores = sorted(set(round(float(score), 12) for score in group["score"].dropna()))
        status = first_non_empty(group.get("status", []))
        if "_json_clause_count" in group and (
            int(group["_json_clause_count"].max()) > 0 or status == "insufficient_evidence"
        ):
            clause_count = int(group["_json_clause_count"].max())
        else:
            clause_count = int(group["clause_id"].notna().sum()) if "clause_id" in group else int(len(group))
        mode = group_values[1]
        records.append(
            {
                "canonical_paper_stem": group_values[0],
                "mode": mode,
                "agent_mode_label": first_non_empty(group.get("mode_label", [])) or MODE_LABELS.get(mode, mode),
                "repetition": positive_int_or_nan(group_values[2]),
                "agent_run_id": first_non_empty(group.get("run_id", [])),
                "agent_biological_status": status,
                "agent_biological_score": float(group["score"].dropna().iloc[0])
                if group["score"].notna().any()
                else np.nan,
                "agent_score_path": first_non_empty(group.get("biological_score_path", [])),
                "agent_clause_count": clause_count,
                "agent_score_conflict": len(scores) > 1,
            }
        )
    if not records:
        return empty_agent_scores()
    return pd.DataFrame.from_records(records)


def summarize_by_paper_mode(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(
            columns=[
                "canonical_paper_stem",
                "manual_paper_number",
                "paper_title",
                "mode",
                "mode_label",
                "matched_count",
                "manual_score_mean",
                "agent_biological_score_mean",
                "mean_signed_error",
                "mean_abs_error",
                "rmse",
            ]
        )
    matched = rows.loc[rows["join_status"] == "matched"].copy()
    if matched.empty:
        return pd.DataFrame(columns=summarize_by_paper_mode(rows.iloc[0:0]).columns)
    group_columns = ["canonical_paper_stem", "manual_paper_number", "paper_title", "mode", "mode_label"]
    summary = (
        matched.groupby(group_columns, dropna=False)
        .agg(
            matched_count=("score_delta", "count"),
            manual_score_mean=("manual_score", "mean"),
            agent_biological_score_mean=("agent_biological_score", "mean"),
            mean_signed_error=("score_delta", "mean"),
            mean_abs_error=("abs_error", "mean"),
            rmse=("score_delta", rmse),
        )
        .reset_index()
    )
    summary["_mode_rank"] = summary["mode"].map({mode: index for index, mode in enumerate(MODE_ORDER)}).fillna(999)
    summary["_paper_rank"] = summary["canonical_paper_stem"].map(paper_number_from_stem).fillna(999)
    return summary.sort_values(["_paper_rank", "canonical_paper_stem", "_mode_rank", "mode"]).drop(
        columns=["_paper_rank", "_mode_rank"]
    )


def summarize_by_mode(rows: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "mode",
        "mode_label",
        "row_count",
        "matched_count",
        "missing_agent_count",
        "missing_manual_count",
        "manual_score_mean",
        "agent_biological_score_mean",
        "mean_signed_error",
        "mean_abs_error",
        "rmse",
        "pearson_r",
        "spearman_r",
    ]
    if rows.empty:
        return pd.DataFrame(columns=columns)
    records = []
    for mode, group in rows.groupby("mode", dropna=False):
        matched = group.loc[group["join_status"] == "matched"]
        records.append(
            {
                "mode": mode,
                "mode_label": first_non_empty(group["mode_label"]) or MODE_LABELS.get(mode, mode),
                "row_count": int(len(group)),
                "matched_count": int(len(matched)),
                "missing_agent_count": int(group["join_status"].isin(["missing_agent_run", "missing_agent_score"]).sum()),
                "missing_manual_count": int(group["join_status"].isin(["missing_manual_row", "missing_manual_score"]).sum()),
                "manual_score_mean": nullable_mean(matched["manual_score"]),
                "agent_biological_score_mean": nullable_mean(matched["agent_biological_score"]),
                "mean_signed_error": nullable_mean(matched["score_delta"]),
                "mean_abs_error": nullable_mean(matched["abs_error"]),
                "rmse": rmse(matched["score_delta"]),
                "pearson_r": correlation(matched["manual_score"], matched["agent_biological_score"], "pearson"),
                "spearman_r": correlation(matched["manual_score"], matched["agent_biological_score"], "spearman"),
            }
        )
    summary = pd.DataFrame.from_records(records)
    summary["_mode_rank"] = summary["mode"].map({mode: index for index, mode in enumerate(MODE_ORDER)}).fillna(999)
    return summary.sort_values(["_mode_rank", "mode"]).drop(columns=["_mode_rank"])[columns].reset_index(drop=True)


def summarize_by_criterion(rows: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "canonical_paper_stem",
        "manual_paper_number",
        "paper_title",
        "row_count",
        "matched_count",
        "scored_count",
        "exact_match_count",
        "discrepancy_count",
        "discrepancy_rate",
        "agent_over_score_count",
        "agent_under_score_count",
        "mean_signed_error",
        "mean_abs_error",
        "rmse",
        "max_abs_error",
        "pearson_r",
        "spearman_r",
    ]
    if rows.empty:
        return pd.DataFrame(columns=columns)

    authoritative = rows.loc[
        rows["manual_paper_number"].notna() & rows["canonical_paper_stem"].map(clean_string).ne("")
    ]
    if authoritative.empty:
        return pd.DataFrame(columns=columns)

    records = []
    for canonical_paper_stem, group in authoritative.groupby("canonical_paper_stem", dropna=False):
        metrics = performance_metrics(group)
        matched = group.loc[group["join_status"] == "matched"]
        records.append(
            {
                "canonical_paper_stem": canonical_paper_stem,
                "manual_paper_number": float(group["manual_paper_number"].dropna().iloc[0]),
                "paper_title": first_non_empty(group["paper_title"]),
                "row_count": int(len(group)),
                "matched_count": metrics["matched_count"],
                "scored_count": int((matched["agent_biological_status"] == "scored").sum()),
                "exact_match_count": metrics["exact_match_count"],
                "discrepancy_count": metrics["discrepancy_count"],
                "discrepancy_rate": metrics["discrepancy_rate"],
                "agent_over_score_count": metrics["agent_over_score_count"],
                "agent_under_score_count": metrics["agent_under_score_count"],
                "mean_signed_error": metrics["mean_signed_error"],
                "mean_abs_error": metrics["mean_abs_error"],
                "rmse": metrics["rmse"],
                "max_abs_error": metrics["max_abs_error"],
                "pearson_r": metrics["pearson_r"],
                "spearman_r": metrics["spearman_r"],
            }
        )
    summary = pd.DataFrame.from_records(records)
    summary["_paper_rank"] = summary["canonical_paper_stem"].map(paper_number_from_stem).fillna(999)
    return summary.sort_values(["_paper_rank", "canonical_paper_stem"]).drop(columns=["_paper_rank"])[columns].reset_index(
        drop=True
    )


def performance_metrics(rows: pd.DataFrame) -> dict[str, float | int]:
    if rows.empty or "join_status" not in rows:
        matched = rows.iloc[0:0]
    else:
        matched = rows.loc[rows["join_status"] == "matched"]
    errors = matched["score_delta"].dropna().copy() if "score_delta" in matched else pd.Series(dtype=float)
    errors.loc[errors.abs() <= SCORE_TOLERANCE] = 0.0
    absolute_errors = errors.abs()
    count = int(len(errors))
    exact_count = int((absolute_errors <= SCORE_TOLERANCE).sum())
    return {
        **regression_metrics(matched),
        "matched_count": count,
        "exact_match_count": exact_count,
        "discrepancy_count": count - exact_count,
        "discrepancy_rate": (count - exact_count) / count if count else np.nan,
        "agent_over_score_count": int((errors > SCORE_TOLERANCE).sum()),
        "agent_under_score_count": int((errors < -SCORE_TOLERANCE).sum()),
        "mean_signed_error": float(errors.mean()) if count else np.nan,
        "mean_abs_error": float(absolute_errors.mean()) if count else np.nan,
        "rmse": rmse(errors),
        "max_abs_error": float(absolute_errors.max()) if count else np.nan,
        "pearson_r": correlation(matched["manual_score"], matched["agent_biological_score"], "pearson")
        if count
        else np.nan,
        "spearman_r": correlation(matched["manual_score"], matched["agent_biological_score"], "spearman")
        if count
        else np.nan,
    }


def regression_metrics(rows: pd.DataFrame) -> dict[str, float]:
    """OLS of agent score on manual score, with a fitted intercept."""
    result = dict.fromkeys(
        ["regression_slope", "regression_intercept", "regression_r_squared",
         "slope_deviation_from_one", "slope_deviation_from_half"], np.nan
    )
    if rows.empty:
        return result
    pairs = rows[["manual_score", "agent_biological_score"]].apply(
        pd.to_numeric, errors="coerce"
    ).replace([np.inf, -np.inf], np.nan).dropna()
    if len(pairs) < 2 or pairs["manual_score"].nunique() < 2:
        return result
    x = pairs["manual_score"].to_numpy()
    y = pairs["agent_biological_score"].to_numpy()
    slope = float(np.sum((x - x.mean()) * (y - y.mean())) / np.sum((x - x.mean()) ** 2))
    intercept = float(y.mean() - slope * x.mean())
    total = float(np.sum((y - y.mean()) ** 2))
    result.update(
        regression_slope=slope,
        regression_intercept=intercept,
        regression_r_squared=1 - float(np.sum((y - (slope * x + intercept)) ** 2)) / total
        if total > 0 else np.nan,
        slope_deviation_from_one=slope - 1,
        slope_deviation_from_half=slope - 0.5,
    )
    return result


def render_discrepancy_report(
    rows: pd.DataFrame,
    by_criterion: pd.DataFrame,
    by_mode: pd.DataFrame,
) -> str:
    all_metrics = performance_metrics(rows)
    scored_metrics = performance_metrics(rows.loc[rows["agent_biological_status"] == "scored"])
    lines = [
        "# Biological score discrepancy report",
        "",
        f"Scores within {SCORE_TOLERANCE:g} are treated as exact matches.",
        "",
        "## Coverage and scorer status",
        "",
        f"- Comparison rows: {len(rows)}",
        f"- Comparable rows: {all_metrics['matched_count']}",
        f"- Rows without a comparable score: {len(rows) - int(all_metrics['matched_count'])}",
        "",
        "| Agent status | Count |",
        "|---|---:|",
    ]
    statuses = rows["agent_biological_status"].fillna("").replace("", "(missing)").value_counts(dropna=False)
    lines.extend(f"| {markdown_text(status)} | {count} |" for status, count in statuses.items())

    lines.extend(
        [
            "",
            "## Performance statistics",
            "",
            "| Cohort | Comparable | Exact matches | MAE | RMSE | Bias | Pearson r | Spearman r | Agent over | Agent under |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            performance_table_row("All comparable runs", all_metrics),
            performance_table_row("Scorer status `scored` only", scored_metrics),
            "",
            "Bias is mean(agent − manual); positive values indicate higher agent scores.",
            "",
            "### Linear regression",
            "",
            "OLS uses unbinned scores: agent = intercept + slope × manual. "
            "Perfect agreement has slope 1 and intercept 0 on these identical 0–1 axes. "
            "The deviation from 0.5 is also reported to address the email's reference; "
            "it is not the perfect-agreement slope. Undefined fits/R² are shown as NA.",
            "",
            "| Cohort | Slope | Intercept | R² | Slope − 1 | Slope − 0.5 |",
            "|---|---:|---:|---:|---:|---:|",
            *[
                "| " + label + " | " + " | ".join(format_number(metrics[key]) for key in
                    ["regression_slope", "regression_intercept", "regression_r_squared",
                     "slope_deviation_from_one", "slope_deviation_from_half"]) + " |"
                for label, metrics in [("All comparable runs", all_metrics),
                                       ("Scorer status `scored` only", scored_metrics)]
            ],
            "",
            "## Discrepancies by paper criterion",
            "",
            "| Criterion | Comparable | Discrepancies | Rate | MAE | RMSE | Bias | Maximum error |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    criterion_rows = by_criterion.sort_values(
        ["discrepancy_rate", "mean_abs_error", "canonical_paper_stem"],
        ascending=[False, False, True],
        na_position="last",
    )
    for _, row in criterion_rows.iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_text(row["canonical_paper_stem"]),
                    str(int(row["matched_count"])),
                    str(int(row["discrepancy_count"])),
                    format_percent(row["discrepancy_rate"]),
                    format_number(row["mean_abs_error"]),
                    format_number(row["rmse"]),
                    format_number(row["mean_signed_error"]),
                    format_number(row["max_abs_error"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Performance by mode",
            "",
            "| Mode | Comparable | Exact matches | MAE | RMSE | Bias | Pearson r | Spearman r | Agent over | Agent under |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for mode in by_mode["mode"]:
        group = rows.loc[rows["mode"] == mode]
        label = first_non_empty(group["mode_label"]) or MODE_LABELS.get(mode, mode)
        lines.append(performance_table_row(label, performance_metrics(group)))

    lines.extend(
        [
            "",
            "## Most common non-exact score pairs",
            "",
            "| Manual → agent | Count | Direction | Mean absolute error |",
            "|---|---:|---|---:|",
        ]
    )
    mismatches = rows.loc[
        (rows["join_status"] == "matched") & (rows["abs_error"] > SCORE_TOLERANCE)
    ].copy()
    if mismatches.empty:
        lines.append("| None | 0 | — | 0.000000 |")
    else:
        mismatches["manual_rounded"] = mismatches["manual_score"].round(6)
        mismatches["agent_rounded"] = mismatches["agent_biological_score"].round(6)
        pairs = (
            mismatches.groupby(["manual_rounded", "agent_rounded"], dropna=False)
            .agg(count=("abs_error", "size"), mean_abs_error=("abs_error", "mean"))
            .reset_index()
            .sort_values(["count", "mean_abs_error", "manual_rounded", "agent_rounded"], ascending=[False, False, True, True])
            .head(REPORT_ROW_LIMIT)
        )
        for _, row in pairs.iterrows():
            direction = "over" if row["agent_rounded"] > row["manual_rounded"] else "under"
            lines.append(
                f"| {row['manual_rounded']:.6f} → {row['agent_rounded']:.6f} | {int(row['count'])} | {direction} | "
                f"{format_number(row['mean_abs_error'])} |"
            )

    lines.extend(
        [
            "",
            "## Largest individual discrepancies",
            "",
            "| Run | Criterion | Mode | Rep | Status | Manual | Agent | Signed error | Absolute error |",
            "|---|---|---|---:|---|---:|---:|---:|---:|",
        ]
    )
    outliers = mismatches.sort_values(
        ["abs_error", "canonical_paper_stem", "mode", "repetition"], ascending=[False, True, True, True]
    ).head(REPORT_ROW_LIMIT)
    if outliers.empty:
        lines.append("| None | — | — | — | — | — | — | — | — |")
    else:
        for _, row in outliers.iterrows():
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_text(first_non_empty([row["agent_run_id"], row["workbook_run_id"]])),
                        markdown_text(row["canonical_paper_stem"]),
                        markdown_text(row["mode"]),
                        format_integer(row["repetition"]),
                        markdown_text(row["agent_biological_status"]),
                        format_number(row["manual_score"]),
                        format_number(row["agent_biological_score"]),
                        format_number(row["score_delta"]),
                        format_number(row["abs_error"]),
                    ]
                )
                + " |"
            )

    lines.extend(
        [
            "",
            "Non-scored statuses with numeric scores (for example, model failures scored as zero) are included in the all-runs cohort. "
            "The scored-only cohort contains only rows whose agent status is `scored`.",
            "",
        ]
    )
    return "\n".join(lines)


def performance_table_row(label: object, metrics: dict[str, float | int]) -> str:
    matched_count = int(metrics["matched_count"])
    exact_count = int(metrics["exact_match_count"])
    exact_rate = exact_count / matched_count if matched_count else np.nan
    return (
        f"| {markdown_text(label)} | {matched_count} | {exact_count} ({format_percent(exact_rate)}) | "
        f"{format_number(metrics['mean_abs_error'])} | {format_number(metrics['rmse'])} | "
        f"{format_number(metrics['mean_signed_error'])} | {format_number(metrics['pearson_r'])} | "
        f"{format_number(metrics['spearman_r'])} | {int(metrics['agent_over_score_count'])} | "
        f"{int(metrics['agent_under_score_count'])} |"
    )


def format_number(value: object) -> str:
    numeric = nullable_number(value)
    return "NA" if pd.isna(numeric) else f"{numeric:.6f}"


def format_percent(value: object) -> str:
    numeric = nullable_number(value)
    return "NA" if pd.isna(numeric) else f"{100 * numeric:.2f}%"


def format_integer(value: object) -> str:
    numeric = nullable_number(value)
    return str(int(numeric)) if not pd.isna(numeric) and int(numeric) == numeric else "—"


def markdown_text(value: object) -> str:
    return clean_string(value).replace("|", "\\|") or "—"


def export_comparison(
    manual_csv: str | Path,
    agent_scores: str | Path,
    output_dir: str | Path,
    make_plots: bool = True,
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = compare_manual_to_agent(manual_csv, agent_scores)
    by_paper_mode = summarize_by_paper_mode(rows)
    by_mode = summarize_by_mode(rows)
    by_criterion = summarize_by_criterion(rows)

    written = {
        "rows": output_dir / "biological_score_manual_comparison.csv",
        "by_paper_mode": output_dir / "biological_score_manual_comparison_by_paper_mode.csv",
        "by_mode": output_dir / "biological_score_manual_comparison_by_mode.csv",
        "by_criterion": output_dir / "biological_score_manual_comparison_by_criterion.csv",
        "discrepancy_report": output_dir / "biological_score_discrepancy_report.md",
    }
    rows.to_csv(written["rows"], index=False)
    by_paper_mode.to_csv(written["by_paper_mode"], index=False)
    by_mode.to_csv(written["by_mode"], index=False)
    by_criterion.to_csv(written["by_criterion"], index=False)
    written["discrepancy_report"].write_text(
        render_discrepancy_report(rows, by_criterion, by_mode), encoding="utf8"
    )
    if make_plots:
        plot_path = output_dir / "biological_score_manual_vs_agent.png"
        if write_scatter_plot(rows, plot_path):
            written["scatter_plot"] = plot_path
        dark_path = output_dir / "biological_score_manual_vs_agent_dark.png"
        if write_scatter_plot(rows, dark_path, dark_background=True):
            written["heatmap_dark"] = dark_path
    return written


def write_scatter_plot(rows: pd.DataFrame, output_path: Path, *, dark_background: bool = False) -> bool:
    """Write a raw binned-count heatmap for matched manual/agent scores.

    The historical function name is retained because this is part of the script's
    public surface, but the plot no longer contains scatter markers.
    """
    matched = rows.loc[rows["join_status"] == "matched"].copy()
    if matched.empty:
        return False
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    fig, ax = plt.subplots(figsize=(5.2, 5.0), constrained_layout=True)
    counts, x_edges, y_edges = score_count_grid(matched)
    # Empty bins sit below the colour range (vmin=1) and take the colormap's "under"
    # colour, which the colorbar shows as a separate arrow below its lowest count.
    cmap = plt.get_cmap("viridis" if dark_background else "viridis_r").with_extremes(under=HEATMAP_EMPTY_COLOR)
    heatmap = ax.pcolormesh(
        x_edges,
        y_edges,
        counts,
        cmap=cmap,
        vmin=1,
        vmax=max(2, float(counts.max())),
        shading="flat",
        rasterized=True,
    )
    ax.plot(
        [0, 1],
        [0, 1],
        color="#E66100",
        linewidth=3.0,
        linestyle="--",
        zorder=3,
        label="Perfect agreement",
    )
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Manual biological score")
    ax.set_ylabel("Agent biological score")
    ax.set_title("Manual vs agent biological scores")
    for iy, ix in np.argwhere(counts > 0):
        rgba = heatmap.cmap(heatmap.norm(counts[iy, ix]))
        luminance = 0.2126 * rgba[0] + 0.7152 * rgba[1] + 0.0722 * rgba[2]
        ax.text((x_edges[ix] + x_edges[ix + 1]) / 2,
                (y_edges[iy] + y_edges[iy + 1]) / 2, str(int(counts[iy, ix])),
                ha="center", va="center", color="black" if luminance > 0.5 else "white",
                fontsize=9, zorder=4)
    ax.legend(fontsize=8, loc="lower right", frameon=True, facecolor="white", edgecolor="none", framealpha=0.85)
    colorbar = fig.colorbar(heatmap, ax=ax, fraction=0.046, pad=0.04, extend="min")
    bin_width_label = f"{HEATMAP_BIN_WIDTH:.4g}"
    colorbar.set_label(f"Observations per {bin_width_label} × {bin_width_label} score bin")
    for suffix in (".png", ".svg", ".pdf"):
        fig.savefig(output_path.with_suffix(suffix), dpi=220)
    plt.close(fig)
    return True


def score_count_grid(
    rows: pd.DataFrame,
    bins: int = HEATMAP_BINS,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return raw 2D bin counts over the zero-to-one score range."""
    valid = rows[["manual_score", "agent_biological_score"]].apply(pd.to_numeric, errors="coerce").dropna()
    counts, x_edges, y_edges = np.histogram2d(
        valid["manual_score"],
        valid["agent_biological_score"],
        bins=np.round(np.linspace(0.0, 1.0, bins + 1), 12),
        range=((0.0, 1.0), (0.0, 1.0)),
    )
    return counts.T, x_edges, y_edges


def default_agent_scores_path(benchmark_dir: Path) -> Path:
    if agent_score_json_paths(benchmark_dir):
        return benchmark_dir
    candidate = first_existing(
        [
            benchmark_dir / "benchmark_biological_scores.csv",
            benchmark_dir / "analysis_figures" / "benchmark_biological_scores.csv",
        ]
    )
    return candidate if candidate is not None else benchmark_dir


def resolve_cli_path(
    path: str | Path,
    description: str,
    must_exist: bool = True,
    map_windows_drives: bool | None = None,
) -> Path:
    original = Path(path)
    handle_drive_path = os.name != "nt" if map_windows_drives is None else map_windows_drives
    candidates = path_candidates(original, handle_drive_path)

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    if must_exist:
        raise FileNotFoundError(missing_path_message(description, original, candidates[-1]))
    return candidates[-1]


def path_candidates(path: Path, handle_windows_drive_paths: bool) -> list[Path]:
    candidates = [path]
    if handle_windows_drive_paths:
        tail = windows_drive_relative_tail(path)
        if tail is not None:
            candidates.append(tail)
    return candidates


def windows_drive_path_parts(path: str | Path) -> tuple[str, Path] | None:
    text = str(path)
    match = WINDOWS_DRIVE_PATH_PATTERN.match(text)
    if not match:
        return None
    drive = match.group(1).upper()
    tail_text = match.group(2).replace("\\", "/").strip("/")
    return drive, Path(tail_text)


def windows_drive_relative_tail(path: str | Path) -> Path | None:
    parts = windows_drive_path_parts(path)
    if parts is None:
        return None
    _, tail = parts
    return tail if str(tail) else Path(".")


def missing_path_message(description: str, original: Path, candidate: Path) -> str:
    message = f"Missing {description}: {candidate}"
    parts = windows_drive_path_parts(original)
    if parts is None:
        return message
    lines = [
        message,
        f"Received a Windows drive path on this OS: {original}",
        "Pass the path as it exists on this machine.",
    ]
    lines.append("In Bash, quote Windows-style paths; unquoted backslashes are stripped.")
    return "\n".join(lines)


def first_existing(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def join_status(row: pd.Series) -> str:
    merge_status = row.get("_merge")
    if merge_status == "left_only":
        return "missing_agent_run"
    if merge_status == "right_only":
        return "missing_manual_row"
    if pd.isna(row.get("manual_score")):
        return "missing_manual_score"
    if pd.isna(row.get("agent_biological_score")):
        return "missing_agent_score"
    return "matched"


def canonical_stem(value: object) -> str:
    text = clean_string(value)
    if not text:
        return ""
    stem = Path(text).stem
    stem = re.sub(r"_(clean|short)$", "", stem)
    return stem


def parse_run_id(run_id: object) -> dict[str, object]:
    text = clean_string(run_id)
    match = RUN_ID_PATTERN.match(text)
    if not match:
        return {"canonical_paper_stem": "", "mode": "", "repetition": np.nan}
    return {
        "canonical_paper_stem": canonical_stem(match.group("paper")),
        "mode": match.group("mode"),
        "repetition": float(int(match.group("rep"))),
    }


def positive_int_or_nan(value: object) -> float:
    if isinstance(value, bool) or pd.isna(value):
        return np.nan
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return np.nan
    if math.isfinite(numeric) and numeric > 0 and int(numeric) == numeric:
        return float(int(numeric))
    return np.nan


def nullable_number(value: object) -> float:
    if isinstance(value, bool) or pd.isna(value):
        return np.nan
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return np.nan
    return numeric if math.isfinite(numeric) else np.nan


def clean_string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def first_non_empty(values: Iterable[object]) -> str:
    for value in values:
        text = clean_string(value)
        if text:
            return text
    return ""


def paper_number_from_stem(value: object) -> float:
    match = re.match(r"^(\d+)_", clean_string(value))
    return float(int(match.group(1))) if match else np.nan


def nullable_mean(values: pd.Series) -> float:
    clean = values.dropna()
    return float(clean.mean()) if not clean.empty else np.nan


def rmse(values: pd.Series) -> float:
    clean = values.dropna()
    return float(np.sqrt(np.mean(np.square(clean)))) if not clean.empty else np.nan


def correlation(x: pd.Series, y: pd.Series, method: str) -> float:
    paired = pd.concat([x, y], axis=1).dropna()
    if len(paired) < 2:
        return np.nan
    left = paired.iloc[:, 0]
    right = paired.iloc[:, 1]
    if method == "spearman":
        left = left.rank(method="average")
        right = right.rank(method="average")
    return pearson_correlation(left, right)


def pearson_correlation(x: pd.Series, y: pd.Series) -> float:
    left = x.astype(float).to_numpy()
    right = y.astype(float).to_numpy()
    left_delta = left - left.mean()
    right_delta = right - right.mean()
    denominator = math.sqrt(float(np.square(left_delta).sum() * np.square(right_delta).sum()))
    if denominator == 0:
        return np.nan
    return float((left_delta * right_delta).sum() / denominator)


def read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def empty_agent_scores() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "canonical_paper_stem",
            "mode",
            "agent_mode_label",
            "repetition",
            "agent_run_id",
            "agent_biological_status",
            "agent_biological_score",
            "agent_score_path",
            "agent_clause_count",
            "agent_score_conflict",
        ]
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare manual biological scores against scoring-agent outputs.")
    parser.add_argument(
        "benchmark_dir",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Benchmark folder. Defaults to the current directory.",
    )
    parser.add_argument(
        "--manual-csv",
        type=Path,
        default=None,
        help="Manual score CSV. Defaults to <benchmark_dir>/manual_biological_scores.csv.",
    )
    parser.add_argument(
        "--agent-scores",
        type=Path,
        default=None,
        help=(
            "Agent score CSV or benchmark folder. Defaults to benchmark_biological_scores.csv "
            "in <benchmark_dir> or <benchmark_dir>/analysis_figures."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to <benchmark_dir>/manual_score_comparison.",
    )
    parser.add_argument("--no-plots", action="store_true", help="Skip count heatmap generation.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        benchmark_dir = resolve_cli_path(args.benchmark_dir, "benchmark directory")
        manual_csv = resolve_cli_path(args.manual_csv or benchmark_dir / "manual_biological_scores.csv", "manual score CSV")
        agent_scores = resolve_cli_path(args.agent_scores or default_agent_scores_path(benchmark_dir), "agent score input")
        output_dir = resolve_cli_path(
            args.output_dir or benchmark_dir / "manual_score_comparison",
            "output directory",
            must_exist=False,
        )
        written = export_comparison(manual_csv, agent_scores, output_dir, make_plots=not args.no_plots)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote row-level comparison: {written['rows']}")
    print(f"Wrote paper/mode summary: {written['by_paper_mode']}")
    print(f"Wrote mode summary: {written['by_mode']}")
    print(f"Wrote criterion discrepancy summary: {written['by_criterion']}")
    print(f"Wrote discrepancy report: {written['discrepancy_report']}")
    if "scatter_plot" in written:
        print(f"Wrote count heatmap: {written['scatter_plot']}")
    if "heatmap_dark" in written:
        print(f"Wrote dark-background alternative: {written['heatmap_dark']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
