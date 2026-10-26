import argparse
import math
import re
import unicodedata
from pathlib import Path
from typing import Iterable

import pandas as pd
from openpyxl import load_workbook


MODE_LABELS = {
    "python_web": "Python + web",
    "morpheus_cli": "Morpheus CLI",
    "morpheus_cli_docs": "Morpheus CLI + docs",
    "morpheus_skill": "Skill + CLI",
    "morpheus_mcp": "Morpheus MCP",
}

MODE_BY_LETTER = {
    "a": "python_web",
    "b": "morpheus_cli",
    "c": "morpheus_skill",
    "d": "morpheus_mcp",
    "e": "morpheus_cli_docs",
}

MODE_ALIASES = {
    "python_web": "python_web",
    "morpheus_cli": "morpheus_cli",
    "morpheus_skill": "morpheus_skill",
    "morpheus_mcp": "morpheus_mcp",
    "morpheus_cli_docs": "morpheus_cli_docs",
    "morpheus_cli+docs": "morpheus_cli_docs",
    "morpheus_cli+docs_offline": "morpheus_cli_docs",
    "morpheus_cli_docs_offline": "morpheus_cli_docs",
}

CANONICAL_STEM_BY_PAPER_KEY = {
    "szabo2010": "01_Szabo2010",
    "thapa2024": "02_Thapa2024",
    "carpenter2024": "03_Carpenter2024",
    "atwell2015": "04_Atwell2025",
    "berkemeier2023": "05_Berkemeier2023",
    "herron2022": "06_Herron2022",
    "scheel2021": "07_Scheel2021",
    "mu2024": "08_Mu2024",
    "luque2023": "09_Luque2023",
    "berkhout2025": "10_Berkhout2025",
    "anlas2024": "11_Anlas2024",
    "malkmus2025": "12_Malkmus2025",
    "mole2026": "13_Mole2026",
    "otsuki2025": "14_Otsuki2025",
    "reza2025": "15_Reza2025",
}

RESULT_CRITERION_COLUMN = 9  # J
MODE_COLUMN = 12  # M
LUTZ_20260601_SCORE_COLUMN = 19  # T
PRERANA_ANJALI_20260601_SCORE_COLUMN = 20  # U
WORKBOOK_MEAN_SCORE_COLUMN = 21  # V
WORKBOOK_AF_SCORE_COLUMN = 31  # AF

# The 05.10.2026 rescoring lives on its own sheet with two criterion columns and a
# per-run mean in column O. When present it is authoritative over the legacy column V.
UPDATED_SHEET_PREFIX = "Updated_manual_scores"
UPDATED_MODE_COLUMN = 9  # J
UPDATED_CRITERION_COLUMNS = (10, 11)  # K, L
UPDATED_MEAN_SCORE_COLUMN = 14  # O

LEGACY_LAYOUT = {
    "sheet": None,
    "mode_column": MODE_COLUMN,
    "score_column": WORKBOOK_MEAN_SCORE_COLUMN,
    "criterion_columns": (RESULT_CRITERION_COLUMN,),
    "reviewer_columns": (LUTZ_20260601_SCORE_COLUMN, PRERANA_ANJALI_20260601_SCORE_COLUMN, WORKBOOK_AF_SCORE_COLUMN),
    "score_source": "workbook_mean_score",
}
UPDATED_LAYOUT = {
    "sheet": UPDATED_SHEET_PREFIX,
    "mode_column": UPDATED_MODE_COLUMN,
    "score_column": UPDATED_MEAN_SCORE_COLUMN,
    "criterion_columns": UPDATED_CRITERION_COLUMNS,
    "reviewer_columns": (None, None, None),
    "score_source": "updated_manual_mean_score",
    "expected_headers": {UPDATED_MODE_COLUMN: "mode", UPDATED_MEAN_SCORE_COLUMN: "mean"},
}

ROW_COLUMNS = [
    "canonical_paper_stem",
    "manual_paper_number",
    "paper_key",
    "paper_title",
    "workbook_group_number",
    "workbook_run_id",
    "workbook_row",
    "mode",
    "mode_label",
    "repetition",
    "manual_score",
    "manual_score_source",
    "manual_score_source_count",
    "manual_score_overlap",
    "lutz_20260601_score",
    "prerana_anjali_20260601_score",
    "workbook_mean_score",
    "workbook_af_score",
    "result_criterion",
]

AGGREGATE_COLUMNS = [
    "canonical_paper_stem",
    "manual_paper_number",
    "paper_key",
    "paper_title",
    "mode",
    "mode_label",
    "manual_score_mean",
    "manual_score_std",
    "manual_score_min",
    "manual_score_max",
    "manual_score_count",
    "manual_score_missing_count",
    "manual_score_overlap_count",
    "repetitions",
]


def extract_manual_score_rows(workbook_path: str | Path) -> pd.DataFrame:
    layout, rows = manual_score_sheet(workbook_path)
    titles_by_group = group_titles(rows)
    lutz_column, prerana_anjali_column, af_column = layout["reviewer_columns"]
    records = []

    for row_number, values in rows:
        parsed = parse_workbook_run_id(cell(values, 0))
        if parsed is None:
            continue
        group_number, mode_letter, repetition, workbook_run_id = parsed
        paper_title = titles_by_group.get(group_number)
        if not paper_title:
            continue
        paper_key = paper_key_from_title(paper_title)
        canonical_stem = CANONICAL_STEM_BY_PAPER_KEY.get(paper_key, "")
        manual_paper_number = paper_number_from_canonical_stem(canonical_stem)
        lutz_score = nullable_number(cell(values, lutz_column))
        prerana_anjali_score = nullable_number(cell(values, prerana_anjali_column))
        workbook_mean_score = nullable_number(cell(values, layout["score_column"]))
        workbook_af_score = nullable_number(cell(values, af_column))
        manual_score, source, source_count, overlap = manual_score_from_policy(
            workbook_mean_score, layout["score_source"]
        )
        mode = normalize_mode(cell(values, layout["mode_column"])) or MODE_BY_LETTER.get(mode_letter, "")
        records.append(
            {
                "canonical_paper_stem": canonical_stem,
                "manual_paper_number": manual_paper_number,
                "paper_key": paper_key,
                "paper_title": paper_title,
                "workbook_group_number": group_number,
                "workbook_run_id": workbook_run_id,
                "workbook_row": row_number,
                "mode": mode,
                "mode_label": MODE_LABELS.get(mode, mode),
                "repetition": repetition,
                "manual_score": manual_score,
                "manual_score_source": source,
                "manual_score_source_count": source_count,
                "manual_score_overlap": overlap,
                "lutz_20260601_score": lutz_score,
                "prerana_anjali_20260601_score": prerana_anjali_score,
                "workbook_mean_score": workbook_mean_score,
                "workbook_af_score": workbook_af_score,
                "result_criterion": " | ".join(
                    text for text in (string_value(cell(values, column)) for column in layout["criterion_columns"]) if text
                ),
            }
        )

    if not records:
        return pd.DataFrame(columns=ROW_COLUMNS)
    result = pd.DataFrame.from_records(records)
    return result[ROW_COLUMNS].sort_values(["manual_paper_number", "mode", "repetition"]).reset_index(drop=True)


def aggregate_manual_scores(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=AGGREGATE_COLUMNS)

    records = []
    group_columns = ["canonical_paper_stem", "manual_paper_number", "paper_key", "paper_title", "mode", "mode_label"]
    for group_values, group in rows.groupby(group_columns, dropna=False):
        scores = group["manual_score"].dropna()
        records.append(
            {
                **dict(zip(group_columns, group_values)),
                "manual_score_mean": float(scores.mean()) if not scores.empty else math.nan,
                "manual_score_std": float(scores.std()) if len(scores) > 1 else math.nan,
                "manual_score_min": float(scores.min()) if not scores.empty else math.nan,
                "manual_score_max": float(scores.max()) if not scores.empty else math.nan,
                "manual_score_count": int(scores.count()),
                "manual_score_missing_count": int(group["manual_score"].isna().sum()),
                "manual_score_overlap_count": int(group["manual_score_overlap"].sum()),
                "repetitions": ";".join(str(int(value)) for value in sorted(group["repetition"].dropna().unique())),
            }
        )
    if not records:
        return pd.DataFrame(columns=AGGREGATE_COLUMNS)
    result = pd.DataFrame.from_records(records)
    return result[AGGREGATE_COLUMNS].sort_values(["manual_paper_number", "mode"]).reset_index(drop=True)


def export_manual_score_csvs(
    workbook_path: str | Path,
    rows_output_path: str | Path,
    aggregate_output_path: str | Path,
) -> dict[str, Path]:
    rows_output = Path(rows_output_path)
    aggregate_output = Path(aggregate_output_path)
    rows = extract_manual_score_rows(workbook_path)
    aggregate = aggregate_manual_scores(rows)
    rows_output.parent.mkdir(parents=True, exist_ok=True)
    aggregate_output.parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(rows_output, index=False)
    aggregate.to_csv(aggregate_output, index=False)
    return {"rows": rows_output, "aggregate": aggregate_output}


def workbook_rows(workbook_path: str | Path) -> list[tuple[int, tuple[object, ...]]]:
    return manual_score_sheet(workbook_path)[1]


def manual_score_sheet(workbook_path: str | Path) -> tuple[dict, list[tuple[int, tuple[object, ...]]]]:
    workbook = load_workbook(workbook_path, data_only=True, read_only=True)
    try:
        updated = [name for name in workbook.sheetnames if name.startswith(UPDATED_SHEET_PREFIX)]
        layout = UPDATED_LAYOUT if updated else LEGACY_LAYOUT
        sheet = workbook[updated[-1]] if updated else workbook.active
        all_rows = list(sheet.iter_rows(values_only=True))
    finally:
        workbook.close()
    header = all_rows[0] if all_rows else ()
    for column, expected in layout.get("expected_headers", {}).items():
        found = string_value(cell(header, column)).lower()
        if found != expected:
            raise ValueError(
                f"Sheet {sheet.title!r} column {column + 1} header is {found!r}, expected {expected!r}; "
                "the manual score layout changed."
            )
    return layout, [(index, tuple(row)) for index, row in enumerate(all_rows, start=1) if index > 1]


def group_titles(rows: Iterable[tuple[int, tuple[object, ...]]]) -> dict[int, str]:
    titles = {}
    for _, values in rows:
        parsed = parse_workbook_run_id(cell(values, 0))
        title = string_value(cell(values, 1))
        if parsed is None or not title or title.lower() == "paper":
            continue
        if "additional biology papers" in title.lower():
            continue
        titles[parsed[0]] = title
    return titles


def parse_workbook_run_id(value: object) -> tuple[int, str, int, str] | None:
    text = string_value(value)
    if not text:
        return None
    match = re.match(r"\s*(\d+)([A-Za-z])(\d+)", text)
    if not match:
        return None
    group_number = int(match.group(1))
    mode_letter = match.group(2).lower()
    repetition = int(match.group(3))
    workbook_run_id = f"{group_number}{mode_letter}{repetition}"
    return group_number, mode_letter, repetition, workbook_run_id


def paper_key_from_title(title: str) -> str:
    normalized = strip_accents(title)
    match = re.search(r"([A-Za-z]+).*?(\d{4})", normalized)
    if not match:
        return re.sub(r"[^a-z0-9]+", "", normalized.lower())
    return f"{match.group(1).lower()}{match.group(2)}"


def normalize_mode(value: object) -> str:
    text = string_value(value)
    if not text:
        return ""
    key = strip_accents(text).lower()
    key = re.sub(r"\s*\([^)]*\)", "", key)
    key = key.replace(" ", "_")
    return MODE_ALIASES.get(key, key)


def manual_score_from_policy(
    workbook_mean_score: float, source: str = "workbook_mean_score"
) -> tuple[float, str, int, bool]:
    if not math.isnan(workbook_mean_score):
        return workbook_mean_score, source, 1, False
    return math.nan, f"missing_{source}", 0, False


def paper_number_from_canonical_stem(stem: str) -> float:
    match = re.match(r"^(\d+)_", stem)
    return float(int(match.group(1))) if match else math.nan


def nullable_number(value: object) -> float:
    if value is None or value == "":
        return math.nan
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return math.nan
    return numeric if math.isfinite(numeric) else math.nan


def string_value(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def cell(values: tuple[object, ...], index: int | None) -> object:
    return values[index] if index is not None and index < len(values) else None


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def default_output_paths(workbook_path: Path, output_dir: Path | None) -> tuple[Path, Path]:
    target_dir = output_dir if output_dir is not None else workbook_path.parent
    return target_dir / "manual_biological_scores.csv", target_dir / "manual_biological_scores_by_paper_mode.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract normalized manual biological scores from the benchmark workbook.")
    parser.add_argument("manual_workbook", type=Path, help="Path to Benchmark_Manual_Scores_*.xlsx")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directory for the exported CSV files.")
    parser.add_argument("--rows-output", type=Path, default=None, help="Optional explicit row-level CSV output path.")
    parser.add_argument("--aggregate-output", type=Path, default=None, help="Optional explicit aggregate CSV output path.")
    args = parser.parse_args(argv)

    default_rows, default_aggregate = default_output_paths(args.manual_workbook, args.output_dir)
    rows_output = args.rows_output or default_rows
    aggregate_output = args.aggregate_output or default_aggregate
    written = export_manual_score_csvs(args.manual_workbook, rows_output, aggregate_output)
    print(f"Wrote row-level manual scores: {written['rows']}")
    print(f"Wrote aggregate manual scores: {written['aggregate']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
