from __future__ import annotations

import argparse
import hashlib
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from biological_score_comparison import (
    MODE_LABELS,
    MODE_ORDER,
    canonical_stem,
    clean_string,
    first_non_empty,
    load_manual_scores,
    nullable_number,
    paper_number_from_stem,
    parse_run_id,
    positive_int_or_nan,
    read_json,
    resolve_cli_path,
)


SCORE_DIR_NAME = "biological_scores"
LEGACY_SCORE_FILENAME = "biological_score.json"
WORKBOOK_FILENAME = "biological_score_details.xlsx"
OVERVIEW_SHEET = "Overview"
CRITERIA_SHEET = "Criteria"
ALL_RUNS_SHEET = "All runs"

MISSING_STATUS = "missing"
EXCEL_CELL_LIMIT = 32767
TRUNCATION_MARKER = " [... truncated]"
EVIDENCE_SEPARATOR = "\n"
LIMITATION_SEPARATOR = " | "
UNKNOWN_VARIANT_KEY = "legacy-unversioned"

CLAUSE_FIELDS = ("passed", "observed_value", "evidence", "rationale")
IDENTITY_COLUMNS = [
    "paper_stem",
    "paper",
    "mode",
    "mode_label",
    "repetition",
    "run_id",
    "canonical_attempt",
]
TOTAL_COLUMNS = [
    "status",
    "score",
    "max_score",
    "passed_clause_count",
    "clause_count",
    "passed_weight",
    "total_weight",
]
MANUAL_COLUMNS = ["manual_score", "score_delta", "abs_error"]
NARRATIVE_COLUMNS = ["summary", "limitations"]
PROVENANCE_COLUMNS = [
    "scorer_version",
    "scorer_model",
    "scorer_reasoning_effort",
    "criteria_version",
    "criteria_sha",
    "attempt_id",
    "attempt_identity",
    "generated_at",
    "score_json_path",
]

ATTEMPT_NUMBER_PATTERN = re.compile(r"(\d+)\s*$")
VARIANT_FILENAME_PATTERN = re.compile(r"^(?P<key>.+?)__attempt-[0-9A-Za-z]+$")
UNSAFE_MODEL_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
INVALID_SHEET_CHARACTERS = re.compile(r"[\[\]:*?/\\]")
SHEET_NAME_LIMIT = 31

COLUMN_WIDTHS = {
    "paper_stem": 18,
    "paper": 22,
    "mode": 18,
    "mode_label": 20,
    "repetition": 11,
    "run_id": 46,
    "canonical_attempt": 17,
    "status": 20,
    "score": 9,
    "max_score": 10,
    "passed_clause_count": 19,
    "clause_count": 13,
    "passed_weight": 14,
    "total_weight": 13,
    "manual_score": 13,
    "score_delta": 12,
    "abs_error": 11,
    "summary": 70,
    "limitations": 50,
    "scorer_version": 15,
    "scorer_model": 18,
    "scorer_reasoning_effort": 23,
    "criteria_version": 16,
    "criteria_sha": 20,
    "attempt_id": 14,
    "attempt_identity": 20,
    "generated_at": 24,
    "score_json_path": 60,
}
CLAUSE_FIELD_WIDTHS = {
    "passed": 10,
    "observed_value": 42,
    "evidence": 70,
    "rationale": 70,
}
WRAPPED_FIELDS = {"observed_value", "evidence", "rationale"}
WRAPPED_COLUMNS = {"summary", "limitations", "score_json_path", "description", "target"}

HEADER_FILL = PatternFill("solid", start_color="FFD9E1F2", end_color="FFD9E1F2")
PASS_FILL = PatternFill("solid", start_color="FFC6EFCE", end_color="FFC6EFCE")
FAIL_FILL = PatternFill("solid", start_color="FFFFC7CE", end_color="FFFFC7CE")
PASS_TEXT = "PASS"
FAIL_TEXT = "FAIL"


def export_score_details(
    benchmark_dir: str | Path,
    variants: Iterable[str] | None = None,
    criteria_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    manual_csv: str | Path | None = None,
    all_runs_sheet: bool = False,
) -> dict[str, Path]:
    """Write one clause-level workbook per scoring variant found under a benchmark folder."""
    benchmark_dir = Path(benchmark_dir)
    inventory = load_run_inventory(benchmark_dir)
    records = load_score_records(benchmark_dir, inventory)
    if not records:
        return {}

    registry = load_criteria_registry(criteria_path)
    manual = load_manual_scores(manual_csv) if manual_csv else None
    selected = set(variants or [])
    written: dict[str, Path] = {}
    for variant_key, variant_records in sorted(group_records_by_variant(records).items()):
        if selected and variant_key not in selected:
            continue
        workbook_dir = (
            Path(output_dir)
            if output_dir is not None
            else benchmark_dir / SCORE_DIR_NAME / variant_key
        )
        written[variant_key] = write_variant_workbook(
            benchmark_dir=benchmark_dir,
            variant_key=variant_key,
            records=variant_records,
            inventory=inventory,
            registry=registry,
            manual=manual,
            output_path=workbook_dir / WORKBOOK_FILENAME,
            all_runs_sheet=all_runs_sheet,
        )
    return written


def load_run_inventory(benchmark_dir: Path) -> list[dict[str, object]]:
    """List every run of the benchmark, from the summary when present and from disk otherwise."""
    entries: dict[str, dict[str, object]] = {}
    summary = read_json(benchmark_dir / "benchmark_summary.json")
    for result in summary.get("results", []):
        if not isinstance(result, dict):
            continue
        run_id = clean_string(result.get("runId"))
        if not run_id:
            continue
        entries[run_id] = run_entry(
            run_id=run_id,
            run_dir=benchmark_dir / run_id,
            paper=clean_string(result.get("paper")),
            mode=clean_string(result.get("mode")),
            repetition=positive_int_or_nan(result.get("repetition")),
        )
    for run_dir in sorted(path for path in benchmark_dir.glob("*") if path.is_dir()):
        run_id = run_dir.name
        if run_id in entries or not run_has_scores(run_dir):
            continue
        entries[run_id] = run_entry(run_id=run_id, run_dir=run_dir)
    return sorted(entries.values(), key=run_sort_key)


def run_entry(
    run_id: str,
    run_dir: Path,
    paper: str = "",
    mode: str = "",
    repetition: float = np.nan,
) -> dict[str, object]:
    parsed = parse_run_id(run_id)
    stem = canonical_stem(paper) or parsed["canonical_paper_stem"]
    resolved_mode = mode or parsed["mode"]
    resolved_repetition = repetition if not math.isnan(repetition) else parsed["repetition"]
    return {
        "run_id": run_id,
        "run_dir": run_dir,
        "paper": paper,
        "paper_stem": stem,
        "mode": resolved_mode,
        "mode_label": MODE_LABELS.get(resolved_mode, resolved_mode),
        "repetition": resolved_repetition,
    }


def run_has_scores(run_dir: Path) -> bool:
    if (run_dir / LEGACY_SCORE_FILENAME).exists():
        return True
    return any((run_dir / SCORE_DIR_NAME).glob("*.json"))


def load_score_records(benchmark_dir: Path, inventory: list[dict[str, object]]) -> list[dict[str, object]]:
    """Read every biological score JSON of the benchmark, newest first per run and variant."""
    records = []
    for entry in inventory:
        run_dir = Path(entry["run_dir"])
        score_paths = sorted((run_dir / SCORE_DIR_NAME).glob("*.json"))
        legacy_path = run_dir / LEGACY_SCORE_FILENAME
        if legacy_path.exists():
            score_paths.append(legacy_path)
        for score_path in score_paths:
            payload = read_json(score_path)
            if not clean_string(payload.get("status")):
                continue
            records.append(build_score_record(entry, payload, score_path, benchmark_dir))
    return records


def build_score_record(
    entry: dict[str, object],
    payload: dict,
    score_path: Path,
    benchmark_dir: Path,
) -> dict[str, object]:
    paper = clean_string(payload.get("paper")) or clean_string(entry.get("paper"))
    mode = clean_string(payload.get("mode")) or clean_string(entry.get("mode"))
    repetition = positive_int_or_nan(payload.get("repetition"))
    if math.isnan(repetition):
        repetition = positive_int_or_nan(entry.get("repetition"))
    attempt_id = clean_string(payload.get("attemptId")) or Path(
        clean_string(payload.get("attemptDir"))
    ).name
    return {
        "variant_key": score_variant_key(payload, score_path),
        "run_id": clean_string(entry.get("run_id")),
        "paper": paper,
        "paper_stem": canonical_stem(paper) or clean_string(entry.get("paper_stem")),
        "mode": mode,
        "mode_label": MODE_LABELS.get(mode, mode),
        "repetition": repetition,
        "status": clean_string(payload.get("status")),
        "score": nullable_number(payload.get("score")),
        "max_score": nullable_number(payload.get("maxScore")),
        "target": clean_string(payload.get("target")),
        "summary": clean_string(payload.get("summary")),
        "limitations": LIMITATION_SEPARATOR.join(
            text for text in (clean_string(item) for item in as_list(payload.get("limitations"))) if text
        ),
        "clauses": clause_decisions(payload.get("clauses")),
        "attempt_id": attempt_id,
        "canonical_attempt": attempt_number(attempt_id),
        "attempt_identity": clean_string(payload.get("attemptIdentity")),
        "scorer_version": nullable_number(payload.get("scorerVersion")),
        "scorer_model": clean_string(payload.get("scorerModel")),
        "scorer_reasoning_effort": clean_string(payload.get("scorerReasoningEffort")),
        "criteria_version": nullable_number(payload.get("criteriaVersion")),
        "criteria_sha": clean_string(payload.get("criteriaSha256")),
        "generated_at": clean_string(payload.get("generatedAt")),
        "score_json_path": relative_to_benchmark(score_path, benchmark_dir),
    }


def clause_decisions(value: object) -> dict[str, dict[str, object]]:
    decisions: dict[str, dict[str, object]] = {}
    for clause in as_list(value):
        if not isinstance(clause, dict):
            continue
        clause_id = clean_string(clause.get("id"))
        if not clause_id or clause_id in decisions:
            continue
        decisions[clause_id] = {
            "passed": clause.get("passed") if isinstance(clause.get("passed"), bool) else None,
            "observed_value": clean_string(clause.get("observed_value")),
            "evidence": EVIDENCE_SEPARATOR.join(
                text for text in (clean_string(item) for item in as_list(clause.get("evidence"))) if text
            ),
            "rationale": clean_string(clause.get("rationale")),
        }
    return decisions


def score_variant_key(payload: dict, score_path: Path) -> str:
    """Identify the scoring cohort a score file belongs to, ignoring the per-run attempt hash."""
    scorer_version = nullable_number(payload.get("scorerVersion"))
    criteria_version = nullable_number(payload.get("criteriaVersion"))
    model = clean_string(payload.get("scorerModel"))
    effort = clean_string(payload.get("scorerReasoningEffort"))
    if math.isnan(scorer_version) or math.isnan(criteria_version) or not model or not effort:
        return variant_key_from_filename(score_path) or UNKNOWN_VARIANT_KEY
    criteria_sha = clean_string(payload.get("criteriaSha256")) or "unknown"
    return (
        f"scorer-v{int(scorer_version)}"
        f"__{UNSAFE_MODEL_PATTERN.sub('-', model)}"
        f"__{effort}"
        f"__criteria-v{int(criteria_version)}-{criteria_sha[:12]}"
    )


def variant_key_from_filename(score_path: Path) -> str:
    match = VARIANT_FILENAME_PATTERN.match(score_path.stem)
    return match.group("key") if match else ""


def group_records_by_variant(records: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    """Group score records by variant, keeping the newest file when a run has several."""
    newest: dict[tuple[str, str], dict[str, object]] = {}
    conflicts: dict[str, int] = {}
    for record in records:
        variant_key = str(record["variant_key"])
        key = (variant_key, str(record["run_id"]))
        previous = newest.get(key)
        if previous is None:
            newest[key] = record
            continue
        conflicts[variant_key] = conflicts.get(variant_key, 0) + 1
        if str(record["generated_at"]) > str(previous["generated_at"]):
            newest[key] = record
    grouped: dict[str, list[dict[str, object]]] = {}
    for (variant_key, _), record in newest.items():
        record["variant_conflict_count"] = conflicts.get(variant_key, 0)
        grouped.setdefault(variant_key, []).append(record)
    return grouped


def load_criteria_registry(criteria_path: str | Path | None) -> dict[str, object] | None:
    """Load the scoring criteria so clause descriptions, kinds, and weights can be shown."""
    if criteria_path is None:
        return None
    path = Path(criteria_path)
    if not path.exists():
        return None
    payload = read_json(path)
    criteria = payload.get("criteria")
    if not isinstance(criteria, list):
        return None
    by_stem: dict[str, dict[str, object]] = {}
    for criterion in criteria:
        if not isinstance(criterion, dict):
            continue
        clauses = [
            {
                "id": clean_string(clause.get("id")),
                "kind": clean_string(clause.get("kind")),
                "weight": nullable_number(clause.get("weight")),
                "description": clean_string(clause.get("description")),
            }
            for clause in as_list(criterion.get("clauses"))
            if isinstance(clause, dict) and clean_string(clause.get("id"))
        ]
        entry = {"target": clean_string(criterion.get("target")), "clauses": clauses}
        for paper_stem in as_list(criterion.get("paper_stems")):
            for candidate in paper_stem_candidates(clean_string(paper_stem)):
                by_stem.setdefault(candidate, entry)
    return {
        "version": nullable_number(payload.get("version")),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "by_stem": by_stem,
    }


def paper_stem_candidates(value: str) -> list[str]:
    normalized = normalize_paper_stem(value)
    without_prefix = re.sub(r"^\d+_", "", normalized)
    return [candidate for candidate in dict.fromkeys([normalized, without_prefix]) if candidate]


def normalize_paper_stem(value: str) -> str:
    text = re.sub(r"\.[^.\\/]+$", "", value.strip())
    text = re.sub(r"_(?:clean|short)$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[^A-Za-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text.strip("_")).lower()


def resolve_clause_specs(
    paper_stem: str,
    records: list[dict[str, object]],
    registry: dict[str, object] | None,
) -> list[dict[str, object]]:
    """Pick the clause columns of a paper sheet, preferring the criteria file when it matches."""
    criterion = registry_criterion(paper_stem, records, registry)
    if criterion is not None:
        specs = [dict(clause) for clause in criterion["clauses"]]
        known = {str(spec["id"]) for spec in specs}
        for clause_id in observed_clause_ids(records):
            if clause_id not in known:
                specs.append({"id": clause_id, "kind": "", "weight": np.nan, "description": ""})
        return finalize_clause_specs(specs, "criteria_file")
    specs = [
        {"id": clause_id, "kind": "", "weight": np.nan, "description": ""}
        for clause_id in observed_clause_ids(records)
    ]
    return finalize_clause_specs(specs, "observed")


def registry_criterion(
    paper_stem: str,
    records: list[dict[str, object]],
    registry: dict[str, object] | None,
) -> dict[str, object] | None:
    if registry is None:
        return None
    criteria_sha = first_non_empty(str(record["criteria_sha"]) for record in records)
    if criteria_sha and criteria_sha != registry["sha256"]:
        return None
    by_stem = registry["by_stem"]
    for candidate in paper_stem_candidates(paper_stem):
        criterion = by_stem.get(candidate)
        if criterion is not None:
            return criterion
    return None


def observed_clause_ids(records: list[dict[str, object]]) -> list[str]:
    """Order clause ids by the richest score record, then append ids only seen elsewhere."""
    ordered = sorted(records, key=lambda record: (-len(record["clauses"]), str(record["run_id"])))
    clause_ids: dict[str, None] = {}
    for record in ordered:
        for clause_id in record["clauses"]:
            clause_ids.setdefault(clause_id, None)
    return list(clause_ids)


def finalize_clause_specs(specs: list[dict[str, object]], source: str) -> list[dict[str, object]]:
    for index, spec in enumerate(specs, start=1):
        spec["column_prefix"] = f"c{index:02d}"
        spec["clause_source"] = source
    return specs


def build_paper_rows(
    paper_stem: str,
    records: list[dict[str, object]],
    inventory: list[dict[str, object]],
    clause_specs: list[dict[str, object]],
    manual: pd.DataFrame | None,
) -> pd.DataFrame:
    """Build one row per mode and repetition of a paper, including runs this variant never scored."""
    records_by_run = {str(record["run_id"]): record for record in records}
    rows = []
    for entry in inventory:
        if clean_string(entry.get("paper_stem")) != paper_stem:
            continue
        rows.append(
            build_paper_row(entry, records_by_run.get(str(entry["run_id"])), clause_specs)
        )
    frame = pd.DataFrame(rows, columns=paper_sheet_columns(clause_specs, manual is not None))
    return attach_manual_scores(frame, manual)


def build_paper_row(
    entry: dict[str, object],
    record: dict[str, object] | None,
    clause_specs: list[dict[str, object]],
) -> dict[str, object]:
    row: dict[str, object] = {
        "paper_stem": clean_string(entry.get("paper_stem")),
        "paper": first_non_empty([record["paper"] if record else "", entry.get("paper")]),
        "mode": clean_string(entry.get("mode")),
        "mode_label": clean_string(entry.get("mode_label")),
        "repetition": positive_int_or_nan(entry.get("repetition")),
        "run_id": clean_string(entry.get("run_id")),
    }
    if record is None:
        row["canonical_attempt"] = np.nan
        row["status"] = MISSING_STATUS
        for column in TOTAL_COLUMNS[1:] + NARRATIVE_COLUMNS + PROVENANCE_COLUMNS:
            row[column] = np.nan if column in TOTAL_COLUMNS else ""
        for spec in clause_specs:
            for field in CLAUSE_FIELDS:
                row[clause_column(spec, field)] = ""
        return row

    decisions = record["clauses"]
    weights = [nullable_number(spec["weight"]) for spec in clause_specs]
    row["canonical_attempt"] = record["canonical_attempt"]
    row["status"] = record["status"]
    row["score"] = record["score"]
    row["max_score"] = record["max_score"]
    row["passed_clause_count"] = sum(
        1 for decision in decisions.values() if decision["passed"] is True
    )
    row["clause_count"] = len(decisions)
    row["passed_weight"] = passed_weight(clause_specs, decisions, weights)
    row["total_weight"] = total_weight(weights)
    for spec in clause_specs:
        decision = decisions.get(str(spec["id"]))
        row[clause_column(spec, "passed")] = passed_text(decision)
        for field in CLAUSE_FIELDS[1:]:
            row[clause_column(spec, field)] = truncate_cell(str(decision[field])) if decision else ""
    row["summary"] = truncate_cell(str(record["summary"]))
    row["limitations"] = truncate_cell(str(record["limitations"]))
    for column in PROVENANCE_COLUMNS:
        row[column] = record[column]
    return row


def passed_weight(
    clause_specs: list[dict[str, object]],
    decisions: dict[str, dict[str, object]],
    weights: list[float],
) -> float:
    if math.isnan(total_weight(weights)):
        return np.nan
    return sum(
        weight
        for spec, weight in zip(clause_specs, weights)
        if (decisions.get(str(spec["id"])) or {}).get("passed") is True
    )


def total_weight(weights: list[float]) -> float:
    """Total weight of the criterion, so a failed run still shows what it was scored against."""
    if not weights or any(math.isnan(weight) for weight in weights):
        return np.nan
    return sum(weights)


def passed_text(decision: dict[str, object] | None) -> str:
    if decision is None or decision["passed"] is None:
        return ""
    return PASS_TEXT if decision["passed"] else FAIL_TEXT


def clause_column(spec: dict[str, object], field: str) -> str:
    return f"{spec['column_prefix']}__{field}"


def paper_sheet_columns(clause_specs: list[dict[str, object]], with_manual: bool) -> list[str]:
    clause_columns = [clause_column(spec, field) for spec in clause_specs for field in CLAUSE_FIELDS]
    manual_columns = MANUAL_COLUMNS if with_manual else []
    return IDENTITY_COLUMNS + TOTAL_COLUMNS + manual_columns + clause_columns + NARRATIVE_COLUMNS + PROVENANCE_COLUMNS


def attach_manual_scores(frame: pd.DataFrame, manual: pd.DataFrame | None) -> pd.DataFrame:
    if manual is None or frame.empty:
        return frame
    keys = manual[["canonical_paper_stem", "mode", "repetition", "manual_score"]].rename(
        columns={"canonical_paper_stem": "paper_stem"}
    )
    merged = frame.drop(columns=MANUAL_COLUMNS, errors="ignore").merge(
        keys.drop_duplicates(subset=["paper_stem", "mode", "repetition"]),
        on=["paper_stem", "mode", "repetition"],
        how="left",
    )
    merged["score_delta"] = merged["score"] - merged["manual_score"]
    merged["abs_error"] = merged["score_delta"].abs()
    return merged[frame.columns]


def build_criteria_frame(paper_specs: dict[str, list[dict[str, object]]], records: list[dict[str, object]]) -> pd.DataFrame:
    targets = {}
    for record in records:
        stem = str(record["paper_stem"])
        if stem not in targets and clean_string(record["target"]):
            targets[stem] = clean_string(record["target"])
    rows = []
    for paper_stem, specs in paper_specs.items():
        for spec in specs:
            rows.append(
                {
                    "paper_stem": paper_stem,
                    "paper_number": paper_number_from_stem(paper_stem),
                    "column_prefix": spec["column_prefix"],
                    "clause_id": spec["id"],
                    "kind": spec["kind"],
                    "weight": spec["weight"],
                    "description": spec["description"],
                    "clause_source": spec["clause_source"],
                    "target": targets.get(paper_stem, ""),
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "paper_stem",
            "paper_number",
            "column_prefix",
            "clause_id",
            "kind",
            "weight",
            "description",
            "clause_source",
            "target",
        ],
    )


def build_overview_frame(
    benchmark_dir: Path,
    variant_key: str,
    records: list[dict[str, object]],
    paper_frames: dict[str, pd.DataFrame],
    registry: dict[str, object] | None,
) -> pd.DataFrame:
    rows = [
        ("Variant", "variant_key", variant_key),
        ("Variant", "scorer_version", format_optional_int(records[0]["scorer_version"])),
        ("Variant", "scorer_model", records[0]["scorer_model"]),
        ("Variant", "scorer_reasoning_effort", records[0]["scorer_reasoning_effort"]),
        ("Variant", "criteria_version", format_optional_int(records[0]["criteria_version"])),
        ("Variant", "criteria_sha256", records[0]["criteria_sha"]),
        ("Variant", "criteria_file_match", criteria_file_match(records, registry)),
        ("Benchmark", "benchmark_dir", str(benchmark_dir)),
        ("Benchmark", "workbook_generated_at", datetime.now(timezone.utc).isoformat(timespec="seconds")),
        ("Benchmark", "papers_in_workbook", len(paper_frames)),
        ("Benchmark", "rows_in_workbook", sum(len(frame) for frame in paper_frames.values())),
        ("Benchmark", "score_files_used", len(records)),
        ("Benchmark", "score_files_superseded", records[0].get("variant_conflict_count", 0)),
    ]
    all_rows = concat_frames(paper_frames.values())
    for status, count in status_counts(all_rows).items():
        rows.append(("Rows by status", status, count))
    for mode_label, mean_score in mean_score_by_mode(all_rows).items():
        rows.append(("Mean score by mode", mode_label, mean_score))
    return pd.DataFrame(rows, columns=["section", "item", "value"])


def criteria_file_match(records: list[dict[str, object]], registry: dict[str, object] | None) -> str:
    if registry is None:
        return "criteria file not loaded"
    criteria_sha = first_non_empty(str(record["criteria_sha"]) for record in records)
    if not criteria_sha:
        return "unknown"
    return "yes" if criteria_sha == registry["sha256"] else "no (clause metadata omitted)"


def status_counts(rows: pd.DataFrame) -> dict[str, int]:
    if rows.empty:
        return {}
    counts = rows["status"].fillna("").replace("", MISSING_STATUS).value_counts()
    return {str(status): int(count) for status, count in counts.items()}


def mean_score_by_mode(rows: pd.DataFrame) -> dict[str, float]:
    if rows.empty:
        return {}
    means = rows.groupby("mode", dropna=False)["score"].mean()
    ranked = sorted(
        means.items(),
        key=lambda item: (mode_rank(str(item[0])), str(item[0])),
    )
    return {MODE_LABELS.get(str(mode), str(mode)): float(value) for mode, value in ranked if pd.notna(value)}


def build_all_runs_frame(paper_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    columns = IDENTITY_COLUMNS + TOTAL_COLUMNS + ["summary", "limitations", "score_json_path"]
    rows = concat_frames(paper_frames.values())
    if rows.empty:
        return pd.DataFrame(columns=columns)
    return rows[[column for column in columns if column in rows.columns]].reset_index(drop=True)


def concat_frames(frames: Iterable[pd.DataFrame]) -> pd.DataFrame:
    usable = [frame for frame in frames if not frame.empty]
    return pd.concat(usable, ignore_index=True) if usable else pd.DataFrame()


def write_variant_workbook(
    benchmark_dir: Path,
    variant_key: str,
    records: list[dict[str, object]],
    inventory: list[dict[str, object]],
    registry: dict[str, object] | None,
    manual: pd.DataFrame | None,
    output_path: Path,
    all_runs_sheet: bool,
) -> Path:
    records_by_paper: dict[str, list[dict[str, object]]] = {}
    for record in records:
        records_by_paper.setdefault(str(record["paper_stem"]), []).append(record)

    paper_specs: dict[str, list[dict[str, object]]] = {}
    paper_frames: dict[str, pd.DataFrame] = {}
    for paper_stem in sorted(records_by_paper, key=paper_sort_key):
        paper_records = records_by_paper[paper_stem]
        specs = resolve_clause_specs(paper_stem, paper_records, registry)
        paper_specs[paper_stem] = specs
        paper_frames[paper_stem] = sort_paper_rows(
            build_paper_rows(paper_stem, paper_records, inventory, specs, manual)
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheets: dict[str, pd.DataFrame] = {
        OVERVIEW_SHEET: build_overview_frame(benchmark_dir, variant_key, records, paper_frames, registry),
        CRITERIA_SHEET: build_criteria_frame(paper_specs, records),
    }
    if all_runs_sheet:
        sheets[ALL_RUNS_SHEET] = build_all_runs_frame(paper_frames)
    for paper_stem, frame in paper_frames.items():
        sheets[sheet_name(paper_stem, sheets)] = frame

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
        for name, frame in sheets.items():
            style_worksheet(writer.book[name], frame)
    return output_path


def sort_paper_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    ordered = frame.copy()
    ordered["_mode_rank"] = ordered["mode"].map(mode_rank)
    ordered = ordered.sort_values(["_mode_rank", "mode", "repetition", "run_id"], na_position="last")
    return ordered.drop(columns=["_mode_rank"]).reset_index(drop=True)


def mode_rank(mode: object) -> int:
    text = clean_string(mode)
    return MODE_ORDER.index(text) if text in MODE_ORDER else len(MODE_ORDER)


def paper_sort_key(paper_stem: str) -> tuple[float, str]:
    number = paper_number_from_stem(paper_stem)
    return (number if not math.isnan(number) else math.inf, paper_stem)


def sheet_name(paper_stem: str, existing: dict[str, pd.DataFrame]) -> str:
    base = INVALID_SHEET_CHARACTERS.sub("_", paper_stem).strip() or "paper"
    candidate = base[:SHEET_NAME_LIMIT]
    suffix = 2
    while candidate in existing:
        marker = f"_{suffix}"
        candidate = f"{base[: SHEET_NAME_LIMIT - len(marker)]}{marker}"
        suffix += 1
    return candidate


def style_worksheet(worksheet, frame: pd.DataFrame) -> None:
    """Make a sheet readable: sticky header, filters, sized columns, and pass/fail colouring."""
    columns = list(frame.columns)
    if not columns:
        return
    header_row = 1
    for index, column in enumerate(columns, start=1):
        cell = worksheet.cell(row=header_row, column=index)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        letter = get_column_letter(index)
        worksheet.column_dimensions[letter].width = column_width(column)
        if wrapped_column(column):
            for row in range(header_row + 1, header_row + len(frame) + 1):
                worksheet.cell(row=row, column=index).alignment = Alignment(vertical="top", wrap_text=True)
        if column.endswith("__passed"):
            apply_pass_fail_fill(worksheet, index, len(frame))
    worksheet.freeze_panes = worksheet.cell(row=header_row + 1, column=frozen_column(columns))
    if len(frame) > 0:
        worksheet.auto_filter.ref = (
            f"A{header_row}:{get_column_letter(len(columns))}{header_row + len(frame)}"
        )


def apply_pass_fail_fill(worksheet, column_index: int, row_count: int) -> None:
    for row in range(2, row_count + 2):
        cell = worksheet.cell(row=row, column=column_index)
        if cell.value == PASS_TEXT:
            cell.fill = PASS_FILL
        elif cell.value == FAIL_TEXT:
            cell.fill = FAIL_FILL
        cell.alignment = Alignment(horizontal="center")


def column_width(column: str) -> float:
    if "__" in column:
        return CLAUSE_FIELD_WIDTHS.get(column.split("__", 1)[1], 24)
    return COLUMN_WIDTHS.get(column, 24)


def wrapped_column(column: str) -> bool:
    if "__" in column:
        return column.split("__", 1)[1] in WRAPPED_FIELDS
    return column in WRAPPED_COLUMNS


def frozen_column(columns: list[str]) -> int:
    frozen = sum(1 for column in columns if column in IDENTITY_COLUMNS)
    return min(frozen, len(columns)) + 1


def truncate_cell(value: str) -> str:
    if len(value) <= EXCEL_CELL_LIMIT:
        return value
    return value[: EXCEL_CELL_LIMIT - len(TRUNCATION_MARKER)] + TRUNCATION_MARKER


def attempt_number(attempt_id: str) -> float:
    match = ATTEMPT_NUMBER_PATTERN.search(clean_string(attempt_id))
    return float(int(match.group(1))) if match else np.nan


def relative_to_benchmark(path: Path, benchmark_dir: Path) -> str:
    try:
        return str(path.relative_to(benchmark_dir))
    except ValueError:
        return str(path)


def format_optional_int(value: object) -> str:
    number = nullable_number(value)
    return "" if math.isnan(number) else str(int(number))


def as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def run_sort_key(entry: dict[str, object]) -> tuple[float, str, int, float, str]:
    paper_stem = clean_string(entry.get("paper_stem"))
    number = paper_number_from_stem(paper_stem)
    repetition = positive_int_or_nan(entry.get("repetition"))
    return (
        number if not math.isnan(number) else math.inf,
        paper_stem,
        mode_rank(entry.get("mode")),
        repetition if not math.isnan(repetition) else math.inf,
        str(entry.get("run_id")),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write clause-level biological scoring workbooks, one per scoring variant."
    )
    parser.add_argument(
        "benchmark_dir",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Benchmark folder. Defaults to the current directory.",
    )
    parser.add_argument(
        "--variant",
        action="append",
        default=None,
        dest="variants",
        help="Scoring variant key to export. Repeatable. Defaults to every variant found.",
    )
    parser.add_argument(
        "--criteria-path",
        type=Path,
        default=None,
        help="Scoring criteria JSON used for clause descriptions, kinds, and weights.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to <benchmark_dir>/biological_scores/<variant>.",
    )
    parser.add_argument(
        "--manual-csv",
        type=Path,
        default=None,
        help="Manual score CSV. Adds manual_score, score_delta, and abs_error columns.",
    )
    parser.add_argument(
        "--all-runs-sheet",
        action="store_true",
        help="Add a flat sheet with every run of the benchmark and no clause columns.",
    )
    parser.add_argument("--list-variants", action="store_true", help="List the variants found and exit.")
    return parser.parse_args(argv)


def default_criteria_path(benchmark_dir: Path) -> Path | None:
    for candidate in (
        benchmark_dir / "biological_scoring_criteria.json",
        Path(__file__).resolve().parent / "biological_scoring_criteria.json",
    ):
        if candidate.exists():
            return candidate
    return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        benchmark_dir = resolve_cli_path(args.benchmark_dir, "benchmark directory")
        criteria_path = (
            resolve_cli_path(args.criteria_path, "scoring criteria JSON")
            if args.criteria_path
            else default_criteria_path(benchmark_dir)
        )
        manual_csv = resolve_cli_path(args.manual_csv, "manual score CSV") if args.manual_csv else None
        if args.list_variants:
            inventory = load_run_inventory(benchmark_dir)
            variants = group_records_by_variant(load_score_records(benchmark_dir, inventory))
            for variant_key, records in sorted(variants.items()):
                print(f"{variant_key}\t{len(records)} runs")
            return 0
        written = export_score_details(
            benchmark_dir,
            variants=args.variants,
            criteria_path=criteria_path,
            output_dir=args.output_dir,
            manual_csv=manual_csv,
            all_runs_sheet=args.all_runs_sheet,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    if not written:
        print(f"No biological score files found under {benchmark_dir}.", file=sys.stderr)
        return 1
    for variant_key, path in written.items():
        print(f"Wrote {variant_key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
