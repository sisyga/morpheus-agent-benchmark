from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd
from scipy import stats

import analyze_benchmark as analysis


COMPARISON_GROUP_COLUMNS = [
    "benchmark_id",
    "benchmark_label",
    "protocol",
    "benchmark_version",
    "total_time_limit_ms",
    "agent_model",
    "agent_reasoning_effort",
    "scorer_cohort",
    "mode",
]
MODEL_GROUP_COLUMNS = [column for column in COMPARISON_GROUP_COLUMNS if column != "mode"]
# Paul Tol's bright palette and distinct marker shapes; enough for six benchmark models.
BENCHMARK_COLORS = ["#4477AA", "#EE6677", "#228833", "#CCBB44", "#66CCEE", "#AA3377"]
BENCHMARK_MARKERS = ["o", "D", "s", "^", "v", "P"]
MORPHEUS_MODES = ["morpheus_cli", "morpheus_cli_docs", "morpheus_skill", "morpheus_mcp"]
CONFIDENCE_LEVEL = 0.95
REQUIRED_RECORD_COLUMNS = {
    "paper",
    "mode",
    "repetition",
    "agent_model",
    "biological_score_itt",
    "total_cost_usd",
}
SCORER_COHORT_PATTERN = re.compile(r"(scorer-v[^/\\]+?)__attempt-")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare biological scores and API costs from two or more Morpheus benchmark runs."
    )
    parser.add_argument(
        "benchmark_dirs",
        nargs="+",
        help="Two or more benchmark folders containing benchmark_summary.json.",
    )
    parser.add_argument(
        "--labels",
        nargs="+",
        default=None,
        help="Display labels, one per benchmark folder. Defaults to '<model> (<reasoning effort>)'.",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory. Defaults to ./benchmark_comparison_figures.",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["png", "pdf", "svg"],
        choices=["png", "pdf", "svg"],
        help="Figure formats to write.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Compare runs even if their protocol, time budget, benchmark version, or scorer differ.",
    )
    args = parser.parse_args(argv)
    if len(args.benchmark_dirs) < 2:
        parser.error("at least two benchmark folders are required")
    if args.labels is not None and len(args.labels) != len(args.benchmark_dirs):
        parser.error("--labels needs exactly one label per benchmark folder")
    return args


def confidence_half_width(values: pd.Series) -> float:
    """Half-width of the t-based confidence interval of the mean (mean ± t·SD/√n)."""
    finite = pd.to_numeric(values, errors="coerce").dropna()
    count = len(finite)
    if count < 2:
        return np.nan
    t_value = stats.t.ppf(0.5 + CONFIDENCE_LEVEL / 2, count - 1)
    return float(t_value * finite.std(ddof=1) / np.sqrt(count))


def never_started_mask(records: pd.DataFrame) -> pd.Series:
    """Runs whose subject never ran: no tokens and no cost, so neither score nor cost is the model's."""
    tokens = pd.to_numeric(records.get("total_tokens_m"), errors="coerce") if "total_tokens_m" in records else None
    cost = pd.to_numeric(records["total_cost_usd"], errors="coerce").fillna(0.0)
    no_tokens = tokens.fillna(0.0) <= 0 if tokens is not None else pd.Series(True, index=records.index)
    return no_tokens & (cost <= 0)


def aggregate_comparison_records(records: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    records = with_comparison_defaults(records)
    paper_records = (
        records.groupby([*COMPARISON_GROUP_COLUMNS, "paper"], as_index=False, sort=False)
        .agg(
            biological_score=("biological_score_itt", "mean"),
            biological_score_valid_only=("biological_score", "mean"),
            total_cost_usd=("total_cost_usd", "mean"),
            execution_count=("repetition", "size"),
        )
    )
    summary = summarize_paper_means(paper_records, COMPARISON_GROUP_COLUMNS)
    return paper_records, summary


def with_comparison_defaults(records: pd.DataFrame) -> pd.DataFrame:
    records = records.copy()
    if "protocol" not in records.columns:
        records["protocol"] = "max_cycles_v1"
    if "total_time_limit_ms" not in records.columns:
        records["total_time_limit_ms"] = 0.0
    if "benchmark_version" not in records.columns:
        records["benchmark_version"] = np.where(records["protocol"] == "time_limit_v2", 2, 1)
    for column, value in {"agent_reasoning_effort": "unknown", "scorer_cohort": "unknown"}.items():
        if column not in records.columns:
            records[column] = value
    if "biological_score" not in records.columns:
        records["biological_score"] = np.nan
    if "biological_scoring_status" in records.columns or "biological_score_itt" not in records.columns:
        # Recompute so cached analysis CSVs also treat scorer failures as missing, not as subject zeros.
        records["biological_score_itt"] = analysis.biological_itt_series(records)
    return records


def summarize_paper_means(paper_records: pd.DataFrame, group_columns: list[str]) -> pd.DataFrame:
    """Mean, SD, and 95% CI of paper-level means; papers are the unit of replication."""
    rows = []
    for group_values, group in paper_records.groupby(group_columns, sort=False, dropna=False):
        row = dict(zip(group_columns, group_values if isinstance(group_values, tuple) else (group_values,)))
        for metric in ("biological_score", "total_cost_usd"):
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            row[f"{metric}_mean"] = float(values.mean()) if len(values) else np.nan
            row[f"{metric}_std"] = float(values.std(ddof=1)) if len(values) > 1 else np.nan
            row[f"{metric}_ci95"] = confidence_half_width(values)
            row[f"{metric}_paper_count"] = int(len(values))
        valid_only = pd.to_numeric(group["biological_score_valid_only"], errors="coerce").dropna()
        row["biological_score_valid_only_mean"] = float(valid_only.mean()) if len(valid_only) else np.nan
        row["biological_score_valid_only_paper_count"] = int(len(valid_only))
        row["paper_count_total"] = int(group["paper"].nunique())
        row["execution_count"] = int(group["execution_count"].sum())
        rows.append(row)
    return pd.DataFrame(rows)


def aggregate_overall_records(paper_records: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-model summary over the Morpheus modes: average each paper across modes, then across papers."""
    morpheus = paper_records.loc[paper_records["mode"].isin(MORPHEUS_MODES)]
    per_paper = (
        morpheus.groupby([*MODEL_GROUP_COLUMNS, "paper"], as_index=False, sort=False)
        .agg(
            biological_score=("biological_score", "mean"),
            biological_score_valid_only=("biological_score_valid_only", "mean"),
            total_cost_usd=("total_cost_usd", "mean"),
            execution_count=("execution_count", "sum"),
        )
    )
    return per_paper, summarize_paper_means(per_paper, MODEL_GROUP_COLUMNS)


def default_benchmark_label(summary: dict) -> str:
    config = summary.get("config") or {}
    model = str(config.get("model") or "unknown model")
    reasoning_effort = config.get("reasoningEffort")
    return f"{model} ({reasoning_effort})" if reasoning_effort else model


def scorer_cohorts(records: pd.DataFrame) -> set[str]:
    if "biological_score_path" not in records.columns:
        return set()
    cohorts = records["biological_score_path"].astype(str).str.extract(SCORER_COHORT_PATTERN)[0]
    return set(cohorts.dropna())


def load_comparison_records(
    benchmark_dirs: list[Path],
    labels: list[str] | None = None,
    force: bool = False,
) -> pd.DataFrame:
    frames = []
    for index, benchmark_dir in enumerate(benchmark_dirs):
        benchmark_dir = Path(benchmark_dir).resolve()
        summary = analysis.load_summary(benchmark_dir)
        analysis_csv = benchmark_dir / "analysis_figures" / "benchmark_analysis_by_run.csv"
        records = None
        if analysis_csv.exists():
            cached_records = pd.read_csv(analysis_csv)
            if REQUIRED_RECORD_COLUMNS.issubset(cached_records.columns):
                records = cached_records
        if records is None:
            summary["benchmarkRunDir"] = str(benchmark_dir)
            records = analysis.records_from_summary(summary, benchmark_dir)
        config = summary.get("config") or {}
        cohorts = scorer_cohorts(records)
        records["protocol"] = str(summary.get("benchmarkProtocol") or "max_cycles_v1")
        records["benchmark_version"] = analysis.benchmark_version(summary)
        records["total_time_limit_ms"] = analysis.number(config.get("totalTimeLimitMs"))
        records["agent_reasoning_effort"] = config.get("reasoningEffort") or "unknown"
        records["scorer_cohort"] = ";".join(sorted(cohorts)) if cohorts else "unknown"
        label = labels[index] if labels else default_benchmark_label(summary)
        records.insert(0, "benchmark_label", label)
        records.insert(0, "benchmark_id", str(summary.get("benchmarkId") or benchmark_dir.name))
        frames.append(records)
    records = pd.concat(frames, ignore_index=True)
    check_comparable(records, force)
    return records


def check_comparable(records: pd.DataFrame, force: bool) -> None:
    problems = []
    for column, description in [
        ("protocol", "protocols"),
        ("total_time_limit_ms", "time budgets"),
        ("benchmark_version", "benchmark versions"),
    ]:
        per_run = records.groupby("benchmark_label", sort=False)[column].first()
        if per_run.nunique(dropna=False) > 1:
            problems.append(f"different {description}: " + ", ".join(f"{k}={v}" for k, v in per_run.items()))
    per_run_scorer = records.groupby("benchmark_label", sort=False)["scorer_cohort"].first()
    known = per_run_scorer.loc[per_run_scorer != "unknown"]
    if known.str.contains(";").any() or known.nunique() > 1:
        problems.append("different scorers: " + ", ".join(f"{k}={v}" for k, v in per_run_scorer.items()))
    if problems and not force:
        raise ValueError("Benchmark runs are not comparable (pass --force to compare anyway):\n- " + "\n- ".join(problems))


def split_never_started(records: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    mask = never_started_mask(records)
    return records.loc[~mask].reset_index(drop=True), records.loc[mask].reset_index(drop=True)


def pareto_front(records: pd.DataFrame, cost_column: str, score_column: str) -> pd.DataFrame:
    candidates = records.dropna(subset=[cost_column, score_column]).sort_values(
        [cost_column, score_column], ascending=[True, False]
    )
    front_indices = []
    best_score = float("-inf")
    for index, row in candidates.iterrows():
        score = float(row[score_column])
        if score > best_score:
            front_indices.append(index)
            best_score = score
    return candidates.loc[front_indices].reset_index(drop=True)


def configure_cost_axis(ax: plt.Axes, costs: pd.Series, axis: str = "x") -> None:
    positive = (pd.to_numeric(costs, errors="coerce").dropna() > 0).all()
    scale_label = "log scale" if positive else "linear scale"
    label = f"Mean API cost per execution (USD, {scale_label})"
    if axis == "x":
        if positive:
            ax.set_xscale("log")
        ax.set_xlabel(label)
    else:
        if positive:
            ax.set_yscale("log")
        ax.set_ylabel(label)


def configure_pareto_cost_axis(ax: plt.Axes, summary: pd.DataFrame) -> None:
    configure_cost_axis(ax, summary["total_cost_usd_mean"], "x")


def ordered_modes(records: pd.DataFrame) -> list[str]:
    present = [str(mode) for mode in records["mode"].dropna().unique()]
    known = [mode for mode in analysis.MODE_ORDER if mode in present]
    return [*known, *sorted(set(present).difference(known))]


def benchmark_series(records: pd.DataFrame) -> list[tuple[str, str]]:
    values = records[["benchmark_id", "benchmark_label"]].drop_duplicates()
    return [(str(row["benchmark_id"]), str(row["benchmark_label"])) for _, row in values.iterrows()]


def benchmark_style(index: int) -> tuple[str, str]:
    return BENCHMARK_COLORS[index % len(BENCHMARK_COLORS)], BENCHMARK_MARKERS[index % len(BENCHMARK_MARKERS)]


def asymmetric_cost_error(mean: float, half_width: float) -> list[list[float]]:
    """Clip the lower arm above zero so a CI stays drawable on a log cost axis."""
    if pd.isna(half_width):
        return [[0.0], [0.0]]
    return [[min(half_width, mean * 0.999)], [half_width]]


def benchmark_legend(ax: plt.Axes, benchmarks: list[tuple[str, str]], **kwargs) -> None:
    ax.legend(
        handles=[
            Patch(facecolor=benchmark_style(index)[0], edgecolor="black", label=label, alpha=0.7)
            for index, (_, label) in enumerate(benchmarks)
        ],
        frameon=False,
        title="Model",
        **kwargs,
    )


def grouped_metric_boxplots(
    ax: plt.Axes,
    paper_records: pd.DataFrame,
    summary: pd.DataFrame,
    point_column: str,
    ylabel: str,
    ylim: tuple[float | None, float | None],
) -> None:
    modes = ordered_modes(summary)
    benchmarks = benchmark_series(summary)
    x = np.arange(len(modes), dtype=float)
    width = 0.8 / len(benchmarks)
    for benchmark_index, (benchmark_id, label) in enumerate(benchmarks):
        offset = (benchmark_index - (len(benchmarks) - 1) / 2) * width
        color, _ = benchmark_style(benchmark_index)
        values_by_mode = []
        positions = []
        for mode_index, mode in enumerate(modes):
            points = paper_records.loc[
                (paper_records["benchmark_id"] == benchmark_id) & (paper_records["mode"] == mode),
                point_column,
            ].dropna().to_numpy(dtype=float)
            points = points[np.isfinite(points)]
            if not len(points):
                continue
            values_by_mode.append(points)
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
                    "markersize": 4,
                },
                medianprops={"color": "black", "linewidth": 1.2},
                boxprops={"edgecolor": "black", "linewidth": 0.7},
                whiskerprops={"color": "black", "linewidth": 0.7},
                capprops={"color": "black", "linewidth": 0.7},
            )
            for patch in boxes["boxes"]:
                patch.set_facecolor(color)
                patch.set_alpha(0.7)

        for position, points in zip(positions, values_by_mode):
            jitter = (
                np.linspace(-width * 0.18, width * 0.18, len(points))
                if len(points) > 1
                else np.array([0.0])
            )
            ax.scatter(
                np.full(len(points), position) + jitter,
                points,
                s=11,
                facecolor="white",
                edgecolor=color,
                linewidth=0.6,
                alpha=0.75,
                zorder=3,
            )
    ax.set_xticks(x)
    ax.set_xticklabels([analysis.MODE_LABELS.get(mode, mode) for mode in modes], rotation=25, ha="right")
    if ylabel:
        ax.set_ylabel(ylabel)
    if ylim != (None, None):
        ax.set_ylim(bottom=ylim[0], top=ylim[1])
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.6)
    benchmark_legend(ax, benchmarks, loc="upper left", bbox_to_anchor=(1.01, 1.0))


def make_biological_score_figure(
    paper_records: pd.DataFrame,
    summary: pd.DataFrame,
    output_dir: Path,
    formats: Iterable[str],
) -> None:
    fig, ax = plt.subplots(figsize=(8.6, 4.5), constrained_layout=True)
    grouped_metric_boxplots(ax, paper_records, summary, "biological_score", "Biological score", (0.0, 1.05))
    analysis.save_figure(fig, output_dir, "biological_score_by_model_and_mode", formats)
    plt.close(fig)


def make_cost_figure(
    paper_records: pd.DataFrame,
    summary: pd.DataFrame,
    output_dir: Path,
    formats: Iterable[str],
) -> None:
    fig, ax = plt.subplots(figsize=(8.6, 4.5), constrained_layout=True)
    # Set the log scale before drawing so autoscaling works in log space.
    configure_cost_axis(ax, paper_records["total_cost_usd"], "y")
    ax.set_ylabel(ax.get_ylabel().replace("Mean API cost", "API cost"))
    grouped_metric_boxplots(ax, paper_records, summary, "total_cost_usd", "", (None, None))
    analysis.save_figure(fig, output_dir, "api_cost_by_model_and_mode", formats)
    plt.close(fig)


def make_pareto_figure(
    summary: pd.DataFrame,
    output_dir: Path,
    formats: Iterable[str],
) -> None:
    fig, ax = plt.subplots(figsize=(8.0, 4.8), constrained_layout=True)
    modes = ordered_modes(summary)
    benchmarks = benchmark_series(summary)
    front = pareto_front(summary, "total_cost_usd_mean", "biological_score_mean")
    ax.plot(
        front["total_cost_usd_mean"],
        front["biological_score_mean"],
        color="#999999",
        linewidth=1.0,
        linestyle="--",
        zorder=1,
    )
    for benchmark_index, (benchmark_id, _) in enumerate(benchmarks):
        _, marker = benchmark_style(benchmark_index)
        for mode in modes:
            point = summary.loc[(summary["benchmark_id"] == benchmark_id) & (summary["mode"] == mode)]
            if point.empty:
                continue
            row = point.iloc[0]
            color = analysis.MODE_COLORS.get(mode, "#777777")
            ax.errorbar(
                row["total_cost_usd_mean"],
                row["biological_score_mean"],
                xerr=asymmetric_cost_error(row["total_cost_usd_mean"], row["total_cost_usd_ci95"]),
                yerr=0 if pd.isna(row["biological_score_ci95"]) else row["biological_score_ci95"],
                fmt=marker,
                markersize=7,
                markerfacecolor=color,
                markeredgecolor="black",
                markeredgewidth=0.7,
                ecolor=color,
                elinewidth=0.9,
                capsize=2,
                zorder=3,
            )
    configure_pareto_cost_axis(ax, summary)
    ax.set_ylabel("Mean biological score")
    ax.set_ylim(0, 1.05)
    ax.grid(color="#EEEEEE", linewidth=0.6)

    mode_handles = [
        Line2D([0], [0], marker="o", linestyle="none", markersize=6, markeredgecolor="black",
               markerfacecolor=analysis.MODE_COLORS.get(mode, "#777777"),
               label=analysis.MODE_LABELS.get(mode, mode))
        for mode in modes
    ]
    model_handles = [
        Line2D([0], [0], marker=benchmark_style(index)[1], linestyle="none", markersize=6,
               markerfacecolor="white", markeredgecolor="black", label=label)
        for index, (_, label) in enumerate(benchmarks)
    ]
    frontier_handle = [Line2D([0], [0], color="#999999", linestyle="--", label="Pareto frontier")]
    mode_legend = ax.legend(handles=mode_handles, frameon=False, title="Mode",
                            loc="upper left", bbox_to_anchor=(1.01, 1.0))
    ax.add_artist(mode_legend)
    ax.legend(handles=[*model_handles, *frontier_handle], frameon=False, title="Model",
              loc="lower left", bbox_to_anchor=(1.01, 0.0))
    analysis.save_figure(fig, output_dir, "api_cost_biological_score_pareto_by_model", formats)
    plt.close(fig)


def make_overall_figure(
    overall_summary: pd.DataFrame,
    output_dir: Path,
    formats: Iterable[str],
) -> None:
    fig, (score_ax, cost_ax) = plt.subplots(1, 2, figsize=(7.6, 3.6), constrained_layout=True)
    benchmarks = benchmark_series(overall_summary)
    positions = np.arange(len(benchmarks), dtype=float)
    for index, (benchmark_id, _) in enumerate(benchmarks):
        row = overall_summary.loc[overall_summary["benchmark_id"] == benchmark_id].iloc[0]
        color, marker = benchmark_style(index)
        score_ax.errorbar(
            positions[index], row["biological_score_mean"],
            yerr=0 if pd.isna(row["biological_score_ci95"]) else row["biological_score_ci95"],
            fmt=marker, markersize=8, markerfacecolor=color, markeredgecolor="black",
            ecolor="black", elinewidth=1.0, capsize=4,
        )
        cost_ax.errorbar(
            positions[index], row["total_cost_usd_mean"],
            yerr=asymmetric_cost_error(row["total_cost_usd_mean"], row["total_cost_usd_ci95"]),
            fmt=marker, markersize=8, markerfacecolor=color, markeredgecolor="black",
            ecolor="black", elinewidth=1.0, capsize=4,
        )
    labels = [label for _, label in benchmarks]
    for ax in (score_ax, cost_ax):
        ax.set_xticks(positions)
        ax.set_xticklabels(labels, rotation=20, ha="right")
        ax.set_xlim(-0.6, len(benchmarks) - 0.4)
        ax.grid(axis="y", color="#EEEEEE", linewidth=0.6)
    score_ax.set_ylabel("Mean biological score")
    score_ax.set_ylim(0, 1.05)
    configure_cost_axis(cost_ax, overall_summary["total_cost_usd_mean"], "y")
    analysis.save_figure(fig, output_dir, "overall_score_and_cost_by_model", formats)
    plt.close(fig)


def write_comparison_outputs(
    records: pd.DataFrame,
    output_dir: Path,
    formats: Iterable[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    output_dir.mkdir(parents=True, exist_ok=True)
    included, excluded = split_never_started(records)
    excluded_columns = [
        column for column in ["benchmark_label", "paper", "mode", "repetition", "status", "total_cost_usd"]
        if column in excluded.columns
    ]
    excluded[excluded_columns].to_csv(output_dir / "benchmark_model_comparison_excluded_runs.csv", index=False)
    paper_records, summary = aggregate_comparison_records(included)
    overall_papers, overall_summary = aggregate_overall_records(paper_records)
    paper_records.to_csv(output_dir / "benchmark_model_comparison_by_paper_mode.csv", index=False)
    summary.to_csv(output_dir / "benchmark_model_comparison_by_model_mode.csv", index=False)
    overall_papers.to_csv(output_dir / "benchmark_model_comparison_overall_by_paper.csv", index=False)
    overall_summary.to_csv(output_dir / "benchmark_model_comparison_overall.csv", index=False)
    analysis.configure_matplotlib()
    make_biological_score_figure(paper_records, summary, output_dir, formats)
    make_cost_figure(paper_records, summary, output_dir, formats)
    make_pareto_figure(summary, output_dir, formats)
    make_overall_figure(overall_summary, output_dir, formats)
    return paper_records, summary


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    benchmark_dirs = [Path(value).resolve() for value in args.benchmark_dirs]
    output_dir = Path(args.out_dir).resolve() if args.out_dir else Path.cwd() / "benchmark_comparison_figures"
    try:
        records = load_comparison_records(benchmark_dirs, args.labels, args.force)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 2
    excluded = never_started_mask(records)
    _, summary = write_comparison_outputs(records, output_dir, args.formats)
    print(f"Wrote comparison for {len(benchmark_dirs)} benchmark runs to {output_dir}")
    if excluded.any():
        counts = records.loc[excluded].groupby("benchmark_label", sort=False).size()
        print("Excluded runs that never started (no tokens, no cost): "
              + ", ".join(f"{label}: {count}" for label, count in counts.items()))
    print(
        summary[
            [
                "benchmark_label",
                "mode",
                "biological_score_mean",
                "biological_score_ci95",
                "biological_score_paper_count",
                "total_cost_usd_mean",
                "total_cost_usd_ci95",
            ]
        ].to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
