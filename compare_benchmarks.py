from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, NullFormatter
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
EXECUTION_BASELINE_MODE = "python_web"
CONFIDENCE_LEVEL = 0.95
CI_METHODS = ["bootstrap", "t"]
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20261023
# Paper-level metric -> (run-record column, label, compared on a log scale as a ratio).
COMPARISON_METRICS = {
    "biological_score": ("biological_score_itt", "Biological score", False),
    "technical_score": ("technical_score_itt", "Technical score", False),
    "total_cost_usd": ("total_cost_usd", "API cost per run (USD)", True),
    "subject_active_time_min": ("subject_active_time_min", "Active time per run (min)", True),
    "attempts": ("attempts", "Model revisions per run", False),
}
# Figures for the metrics without a dedicated figure of their own.
EXTRA_METRIC_FIGURES = {
    "technical_score": "technical_score_by_model_and_mode",
    "subject_active_time_min": "active_time_by_model_and_mode",
    "attempts": "revisions_by_model_and_mode",
}
REQUIRED_RECORD_COLUMNS = {
    "paper",
    "mode",
    "repetition",
    "agent_model",
    "biological_score_itt",
    "total_cost_usd",
}
SCORER_COHORT_PATTERN = re.compile(r"(scorer-v[^/\\]+?)__attempt-")
# Nature Methods: 180 mm double column, Arial 5–7 pt. The two box plots and the Pareto plot
# share one row, so each panel is exported at its final size and placed in the figure unscaled.
MM_PER_INCH = 25.4
PANEL_SIZE_MM = (59.0, 45.0)
PANEL_STYLE = {
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Liberation Sans", "DejaVu Sans"],
    "font.size": 6,
    "axes.labelsize": 6,
    "axes.titlesize": 7,
    "xtick.labelsize": 5,
    "ytick.labelsize": 5,
    "legend.fontsize": 5,
    "legend.title_fontsize": 6,
    "axes.linewidth": 0.5,
    "xtick.major.width": 0.5,
    "ytick.major.width": 0.5,
    "xtick.minor.width": 0.4,
    "ytick.minor.width": 0.4,
    "xtick.major.size": 2.0,
    "ytick.major.size": 2.0,
    "xtick.minor.size": 1.2,
    "ytick.minor.size": 1.2,
    "xtick.major.pad": 1.5,
    "ytick.major.pad": 1.5,
    "axes.labelpad": 2.0,
    "lines.linewidth": 0.75,
    "legend.handlelength": 1.2,
    "legend.handletextpad": 0.4,
    "legend.borderaxespad": 0.2,
    "legend.labelspacing": 0.25,
    "legend.columnspacing": 0.8,
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
}


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
    parser.add_argument(
        "--ci",
        default="bootstrap",
        choices=CI_METHODS,
        help="95%% confidence intervals over papers: BCa bootstrap (default) or mean ± t·SD/√n.",
    )
    parser.add_argument(
        "--significance",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Draw significance brackets and letters in the figures (default on); the MD files are always written.",
    )
    parser.add_argument(
        "--panel-size-mm",
        nargs=2,
        type=float,
        default=list(PANEL_SIZE_MM),
        metavar=("WIDTH", "HEIGHT"),
        help="Exported size of each panel in mm (default: %(default)s, three panels in one 180 mm row).",
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


def mean_confidence_interval(values: Iterable[float], method: str = "bootstrap") -> tuple[float, float]:
    """95% CI of the mean over papers: BCa bootstrap (stays inside the data range) or the t interval."""
    finite = pd.to_numeric(pd.Series(list(values), dtype=float), errors="coerce").dropna().to_numpy(dtype=float)
    if len(finite) < 2:
        return np.nan, np.nan
    mean = float(finite.mean())
    if np.allclose(finite, finite[0]):
        return mean, mean
    if method == "t":
        half_width = confidence_half_width(pd.Series(finite))
        return mean - half_width, mean + half_width
    result = None
    for bootstrap_method in ("BCa", "percentile"):
        result = stats.bootstrap(
            (finite,),
            np.mean,
            confidence_level=CONFIDENCE_LEVEL,
            n_resamples=BOOTSTRAP_RESAMPLES,
            method=bootstrap_method,
            random_state=np.random.default_rng(BOOTSTRAP_SEED),
        )
        if np.isfinite(result.confidence_interval.low) and np.isfinite(result.confidence_interval.high):
            break
    return float(result.confidence_interval.low), float(result.confidence_interval.high)


def never_started_mask(records: pd.DataFrame) -> pd.Series:
    """Runs whose subject never ran: no tokens and no cost, so neither score nor cost is the model's."""
    tokens = pd.to_numeric(records.get("total_tokens_m"), errors="coerce") if "total_tokens_m" in records else None
    cost = pd.to_numeric(records["total_cost_usd"], errors="coerce").fillna(0.0)
    no_tokens = tokens.fillna(0.0) <= 0 if tokens is not None else pd.Series(True, index=records.index)
    return no_tokens & (cost <= 0)


def present_metrics(frame: pd.DataFrame) -> list[str]:
    return [metric for metric in COMPARISON_METRICS if metric in frame.columns]


def aggregate_comparison_records(
    records: pd.DataFrame,
    ci_method: str = "bootstrap",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    records = with_comparison_defaults(records)
    metric_aggregations = {
        metric: (column, "mean")
        for metric, (column, _, _) in COMPARISON_METRICS.items()
        if column in records.columns
    }
    for metric, (column, _) in metric_aggregations.items():
        records[column] = pd.to_numeric(records[column], errors="coerce")
    paper_records = (
        records.groupby([*COMPARISON_GROUP_COLUMNS, "paper"], as_index=False, sort=False)
        .agg(
            **metric_aggregations,
            biological_score_valid_only=("biological_score", "mean"),
            execution_count=("repetition", "size"),
        )
    )
    summary = summarize_paper_means(paper_records, COMPARISON_GROUP_COLUMNS, ci_method)
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


def summarize_paper_means(
    paper_records: pd.DataFrame,
    group_columns: list[str],
    ci_method: str = "bootstrap",
) -> pd.DataFrame:
    """Mean, SD, and 95% CI of paper-level means; papers are the unit of replication."""
    rows = []
    for group_values, group in paper_records.groupby(group_columns, sort=False, dropna=False):
        row = dict(zip(group_columns, group_values if isinstance(group_values, tuple) else (group_values,)))
        for metric in present_metrics(group):
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            row[f"{metric}_mean"] = float(values.mean()) if len(values) else np.nan
            row[f"{metric}_std"] = float(values.std(ddof=1)) if len(values) > 1 else np.nan
            row[f"{metric}_ci95"] = confidence_half_width(values)
            row[f"{metric}_ci_low"], row[f"{metric}_ci_high"] = mean_confidence_interval(values, ci_method)
            row[f"{metric}_paper_count"] = int(len(values))
        valid_only = pd.to_numeric(group["biological_score_valid_only"], errors="coerce").dropna()
        row["biological_score_valid_only_mean"] = float(valid_only.mean()) if len(valid_only) else np.nan
        row["biological_score_valid_only_paper_count"] = int(len(valid_only))
        row["paper_count_total"] = int(group["paper"].nunique())
        row["execution_count"] = int(group["execution_count"].sum())
        rows.append(row)
    return pd.DataFrame(rows)


def aggregate_overall_records(
    paper_records: pd.DataFrame,
    ci_method: str = "bootstrap",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-model summary over the Morpheus modes: average each paper across modes, then across papers."""
    morpheus = paper_records.loc[paper_records["mode"].isin(MORPHEUS_MODES)]
    per_paper = (
        morpheus.groupby([*MODEL_GROUP_COLUMNS, "paper"], as_index=False, sort=False)
        .agg(
            **{metric: (metric, "mean") for metric in present_metrics(morpheus)},
            biological_score_valid_only=("biological_score_valid_only", "mean"),
            execution_count=("execution_count", "sum"),
        )
    )
    return per_paper, summarize_paper_means(per_paper, MODEL_GROUP_COLUMNS, ci_method)


def holm_adjust(p_values: Iterable[float]) -> np.ndarray:
    """Holm step-down adjusted p-values; missing p-values stay missing and do not count."""
    p = np.asarray(list(p_values), dtype=float)
    adjusted = np.full(len(p), np.nan)
    valid = np.flatnonzero(np.isfinite(p))
    order = valid[np.argsort(p[valid], kind="stable")]
    running_max = 0.0
    for rank, index in enumerate(order):
        running_max = max(running_max, (len(order) - rank) * p[index])
        adjusted[index] = min(1.0, running_max)
    return adjusted


def rank_biserial(differences: np.ndarray) -> float:
    """Matched-pairs rank-biserial correlation over the non-zero differences (−1 to 1)."""
    nonzero = differences[differences != 0]
    if not len(nonzero):
        return 0.0
    ranks = stats.rankdata(np.abs(nonzero))
    return float((ranks[nonzero > 0].sum() - ranks[nonzero < 0].sum()) / ranks.sum())


def paired_wilcoxon(a: np.ndarray, b: np.ndarray, log_scale: bool, ci_method: str = "bootstrap") -> dict:
    """Two-sided Wilcoxon signed-rank test of a − b (log a − log b for ratios) with an exact sign-flip null.

    Zero differences stay in the ranking (Pratt), which suits scores tied at the ceiling.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    keep = np.isfinite(a) & np.isfinite(b)
    if log_scale:
        keep &= (a > 0) & (b > 0)
    a, b = a[keep], b[keep]
    result = {
        "n": int(len(a)),
        "mean_a": float(a.mean()) if len(a) else np.nan,
        "mean_b": float(b.mean()) if len(b) else np.nan,
        "effect_type": "ratio a/b (geometric mean)" if log_scale else "difference a − b",
        "effect": np.nan,
        "effect_ci_low": np.nan,
        "effect_ci_high": np.nan,
        "statistic": np.nan,
        "p_value": np.nan,
        "effect_size_name": "rank-biserial r",
        "effect_size": np.nan,
    }
    if len(a) < 2:
        return result
    differences = np.log(a) - np.log(b) if log_scale else a - b
    low, high = mean_confidence_interval(differences, ci_method)
    effect = float(differences.mean())
    if log_scale:
        effect, low, high = float(np.exp(effect)), float(np.exp(low)), float(np.exp(high))
    result.update(effect=effect, effect_ci_low=low, effect_ci_high=high, effect_size=rank_biserial(differences))
    if np.allclose(differences, 0.0):
        result.update(statistic=0.0, p_value=1.0)
        return result
    statistic, p_value = exact_signed_rank_test(differences)
    result.update(statistic=statistic, p_value=p_value)
    return result


def exact_signed_rank_test(differences: np.ndarray) -> tuple[float, float]:
    """Wilcoxon signed-rank test with Pratt zeros and the exact sign-flip null, valid with ties.

    Returns W = min(T+, T−) and the two-sided p-value. The null distribution of T+ is built by
    convolution over the (doubled, hence integer) ranks of the non-zero differences.
    """
    ranks = stats.rankdata(np.abs(differences))
    nonzero = differences != 0
    doubled = np.rint(2 * ranks[nonzero]).astype(int)
    t_plus = int(doubled[differences[nonzero] > 0].sum())
    total = int(doubled.sum())
    counts = np.zeros(total + 1)
    counts[0] = 1.0
    for rank in doubled:
        counts[rank:] += counts[:-rank].copy()
    probabilities = counts / counts.sum()
    centre = total / 2
    extreme = np.abs(np.arange(total + 1) - centre) >= abs(t_plus - centre) - 1e-9
    p_value = float(min(1.0, probabilities[extreme].sum()))
    return min(t_plus, total - t_plus) / 2, p_value


def friedman_test(table: pd.DataFrame) -> dict:
    """Friedman test across the columns of a paper × condition table, using papers with all conditions."""
    complete = table.dropna()
    result = {"n": int(len(complete)), "statistic": np.nan, "p_value": np.nan,
              "effect_size_name": "Kendall's W", "effect_size": np.nan}
    conditions = complete.shape[1]
    if len(complete) < 2 or conditions < 3:
        return result
    values = complete.to_numpy(dtype=float)
    if np.allclose(values, values[:, :1]):
        result.update(statistic=0.0, p_value=1.0, effect_size=0.0)
        return result
    statistic, p_value = stats.friedmanchisquare(*values.T)
    result.update(
        statistic=float(statistic),
        p_value=float(p_value),
        effect_size=float(statistic / (len(complete) * (conditions - 1))),
    )
    return result


def paper_table(paper_records: pd.DataFrame, metric: str, column: str, keys: list[str]) -> pd.DataFrame:
    """Paper × condition table of a paper-level metric; ``column`` names the condition."""
    subset = paper_records.loc[paper_records[column].isin(keys)]
    table = subset.pivot_table(index="paper", columns=column, values=metric, aggfunc="mean")
    return table.reindex(columns=keys)


def stats_row(
    family: str,
    scope: str,
    metric: str,
    condition_a: str,
    condition_b: str,
    test: str,
    values: dict,
    **keys,
) -> dict:
    return {"family": family, "scope": scope, "metric": metric, "test": test,
            "condition_a": condition_a, "condition_b": condition_b, **keys, **values}


def mode_label(mode: str) -> str:
    return analysis.MODE_LABELS.get(mode, mode)


def compute_statistical_tests(
    paper_records: pd.DataFrame,
    overall_papers: pd.DataFrame,
    ci_method: str = "bootstrap",
) -> pd.DataFrame:
    """Paired tests on paper-level means, Holm-adjusted within each family, scope and metric."""
    rows = []
    benchmarks = benchmark_series(paper_records)
    modes = ordered_modes(paper_records)
    morpheus_modes = [mode for mode in MORPHEUS_MODES if mode in modes]
    for metric in present_metrics(paper_records):
        log_scale = COMPARISON_METRICS[metric][2]
        for benchmark_id, label in benchmarks:
            own = paper_records.loc[paper_records["benchmark_id"] == benchmark_id]
            table = paper_table(own, metric, "mode", modes)
            if EXECUTION_BASELINE_MODE in table.columns:
                for mode in morpheus_modes:
                    pair = table[[mode, EXECUTION_BASELINE_MODE]].dropna()
                    rows.append(stats_row(
                        "execution", label, metric, mode_label(mode), mode_label(EXECUTION_BASELINE_MODE),
                        "Wilcoxon signed-rank",
                        paired_wilcoxon(pair[mode], pair[EXECUTION_BASELINE_MODE], log_scale, ci_method),
                    ))
            if len(morpheus_modes) >= 3:
                rows.append(stats_row(
                    "morpheus_modes_omnibus", label, metric, " / ".join(map(mode_label, morpheus_modes)), "",
                    "Friedman", friedman_test(table[morpheus_modes]),
                ))
            for index, mode_a in enumerate(morpheus_modes):
                for mode_b in morpheus_modes[index + 1:]:
                    pair = table[[mode_a, mode_b]].dropna()
                    rows.append(stats_row(
                        "morpheus_modes_pairwise", label, metric, mode_label(mode_a), mode_label(mode_b),
                        "Wilcoxon signed-rank", paired_wilcoxon(pair[mode_a], pair[mode_b], log_scale, ci_method),
                    ))
            # All mode pairs in one Holm family; these drive the letters in the box plots.
            for index, mode_a in enumerate(modes):
                for mode_b in modes[index + 1:]:
                    pair = table[[mode_a, mode_b]].dropna()
                    rows.append(stats_row(
                        "modes_pairwise", label, metric, mode_label(mode_a), mode_label(mode_b),
                        "Wilcoxon signed-rank", paired_wilcoxon(pair[mode_a], pair[mode_b], log_scale, ci_method),
                        benchmark=benchmark_id, mode_a=mode_a, mode_b=mode_b,
                    ))
        for index, (id_a, label_a) in enumerate(benchmarks):
            for id_b, label_b in benchmarks[index + 1:]:
                scope = f"{label_a} vs {label_b}"
                for mode in modes:
                    table = paper_table(
                        paper_records.loc[paper_records["mode"] == mode], metric, "benchmark_id", [id_a, id_b]
                    ).dropna()
                    rows.append(stats_row(
                        "between_models_by_mode", scope, metric, f"{label_a}, {mode_label(mode)}",
                        f"{label_b}, {mode_label(mode)}", "Wilcoxon signed-rank",
                        paired_wilcoxon(table[id_a], table[id_b], log_scale, ci_method),
                        mode=mode, benchmark_a=id_a, benchmark_b=id_b,
                    ))
                if metric in overall_papers.columns:
                    table = paper_table(overall_papers, metric, "benchmark_id", [id_a, id_b]).dropna()
                    rows.append(stats_row(
                        "between_models_overall", scope, metric, f"{label_a}, Morpheus modes",
                        f"{label_b}, Morpheus modes", "Wilcoxon signed-rank",
                        paired_wilcoxon(table[id_a], table[id_b], log_scale, ci_method),
                        benchmark_a=id_a, benchmark_b=id_b,
                    ))
    tests = pd.DataFrame(rows)
    if tests.empty:
        return tests
    tests["p_holm"] = np.nan
    for _, group in tests.groupby(["family", "scope", "metric"], sort=False):
        tests.loc[group.index, "p_holm"] = holm_adjust(group["p_value"])
    tests["holm_family_size"] = tests.groupby(["family", "scope", "metric"], sort=False)["p_value"].transform(
        lambda values: int(values.notna().sum())
    )
    return tests


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
    """Log axis when every cost is positive; the decade ticks show the scale, so the label leaves it out."""
    positive = (pd.to_numeric(costs, errors="coerce").dropna() > 0).all()
    label = "Mean API cost per run (USD)"
    if axis == "x":
        if positive:
            ax.set_xscale("log")
            plain_log_ticks(ax.xaxis)
        ax.set_xlabel(label)
    else:
        if positive:
            ax.set_yscale("log")
            plain_log_ticks(ax.yaxis)
        ax.set_ylabel(label)


def plain_log_ticks(axis) -> None:
    """Label log ticks 0.1, 1, 10: mathtext exponents would print below the 5 pt minimum."""
    axis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
    axis.set_minor_formatter(NullFormatter())


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


def interval_error(mean: float, low: float, high: float, positive: bool = False) -> list[list[float]]:
    """Error-bar arms for a CI; ``positive`` keeps the lower end above zero for a log axis."""
    if pd.isna(mean) or pd.isna(low) or pd.isna(high):
        return [[0.0], [0.0]]
    lower = mean - low
    if positive:
        lower = min(lower, mean * 0.999)
    return [[max(lower, 0.0)], [max(high - mean, 0.0)]]


def summary_error(row: pd.Series, metric: str, positive: bool = False) -> list[list[float]]:
    return interval_error(row[f"{metric}_mean"], row[f"{metric}_ci_low"], row[f"{metric}_ci_high"], positive)


def benchmark_legend(ax: plt.Axes, benchmarks: list[tuple[str, str]], **kwargs) -> None:
    ax.legend(
        handles=[
            Patch(facecolor=benchmark_style(index)[0], edgecolor="black", linewidth=0.5, label=label, alpha=0.7)
            for index, (_, label) in enumerate(benchmarks)
        ],
        frameon=False,
        **kwargs,
    )


def panel_figure(size_mm: tuple[float, float], ncols: int = 1) -> tuple[plt.Figure, plt.Axes | np.ndarray]:
    """A figure at its final printed size; constrained layout keeps labels and legends inside it."""
    fig, axes = plt.subplots(
        1, ncols, figsize=(size_mm[0] / MM_PER_INCH, size_mm[1] / MM_PER_INCH), layout="constrained"
    )
    fig.get_layout_engine().set(w_pad=1 / 72, h_pad=1 / 72, wspace=0.02, hspace=0.02)
    return fig, axes


def save_panel(fig: plt.Figure, output_dir: Path, stem: str, formats: Iterable[str]) -> None:
    """Save at exactly the figure size (no tight bounding box), so the SVG drops into the layout unscaled."""
    for fmt in formats:
        fig.savefig(output_dir / f"{stem}.{fmt}")


def grouped_metric_boxplots(
    ax: plt.Axes,
    paper_records: pd.DataFrame,
    summary: pd.DataFrame,
    point_column: str,
    ylabel: str,
    ylim: tuple[float | None, float | None],
    ci_method: str = "bootstrap",
    tests: pd.DataFrame | None = None,
) -> None:
    """Box plots of paper-level values with the mean and its 95% CI drawn over each box.

    With ``tests``, each mode group gets brackets with the Holm-adjusted p-value of the paired
    between-model test.
    """
    modes = ordered_modes(summary)
    mean_intervals = []
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
                showmeans=False,
                showfliers=False,
                medianprops={"color": "black", "linewidth": 0.8},
                boxprops={"edgecolor": "black", "linewidth": 0.5},
                whiskerprops={"color": "black", "linewidth": 0.5},
                capprops={"color": "black", "linewidth": 0.5},
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
                s=3,
                facecolor="white",
                edgecolor=color,
                linewidth=0.4,
                alpha=0.75,
                zorder=3,
            )
            mean_intervals.append((position, float(points.mean()), *mean_confidence_interval(points, ci_method)))
    # Drawn after all boxes and points so the CI sits on top of both.
    positive = ax.get_yscale() == "log"
    for position, mean, low, high in mean_intervals:
        ax.errorbar(
            position, mean, yerr=interval_error(mean, low, high, positive),
            fmt="D", markersize=2.5, markerfacecolor="white", markeredgecolor="black", markeredgewidth=0.5,
            ecolor="black", elinewidth=0.6, capsize=1.5, capthick=0.6, zorder=4,
        )
    ax.set_xticks(x)
    ax.set_xticklabels([analysis.MODE_LABELS.get(mode, mode) for mode in modes], rotation=30, ha="right",
                       rotation_mode="anchor")
    if ylabel:
        ax.set_ylabel(ylabel)
    if ylim != (None, None):
        ax.set_ylim(bottom=ylim[0], top=ylim[1])
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.4)
    ax.set_axisbelow(True)
    benchmark_legend(ax, benchmarks, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncols=len(benchmarks))
    if tests is not None and not tests.empty:
        annotate_between_model_tests(ax, tests, point_column, modes, benchmarks, x, width)


def format_p(p_value: float) -> str:
    if pd.isna(p_value):
        return "n/a"
    if p_value < 0.001:
        return f"{p_value:.1e}"
    return f"{p_value:.3f}"


SIGNIFICANCE_STARS = [(0.001, "***"), (0.01, "**"), (0.05, "*")]


def significance_label(p_value: float) -> str:
    """Asterisks for a figure (* p < 0.05, ** p < 0.01, *** p < 0.001); exact p-values are in the MD files."""
    if pd.isna(p_value):
        return "n/a"
    for threshold, stars in SIGNIFICANCE_STARS:
        if p_value < threshold:
            return stars
    return "n.s."


def compact_letter_display(groups: list[str], different: set[frozenset[str]]) -> dict[str, str]:
    """Letters per group such that two groups share no letter exactly when they differ significantly.

    Insert-and-absorb (Piepho 2004); ``groups`` in display priority, e.g. by descending mean.
    """
    columns = [set(groups)]
    for pair in different:
        first, second = tuple(pair)
        split = []
        for column in columns:
            if first in column and second in column:
                split += [column - {first}, column - {second}]
            else:
                split.append(column)
        columns = [column for column in split if not any(column < other for other in split)]
        columns = [column for index, column in enumerate(columns) if column not in columns[:index]]
    columns.sort(key=lambda column: min(groups.index(group) for group in column))
    letters = "abcdefghijklmnopqrstuvwxyz"
    return {
        group: "".join(letters[index] for index, column in enumerate(columns) if group in column)
        for group in groups
    }


def mode_letters(tests: pd.DataFrame, metric: str, benchmark_id: str, alpha: float = 0.05) -> dict[str, str]:
    if "benchmark" not in tests.columns:
        return {}
    rows = tests.loc[
        (tests["family"] == "modes_pairwise") & (tests["metric"] == metric) & (tests["benchmark"] == benchmark_id)
    ]
    if rows.empty:
        return {}
    means = {}
    for _, row in rows.iterrows():
        means.setdefault(row["mode_a"], row["mean_a"])
        means.setdefault(row["mode_b"], row["mean_b"])
    groups = sorted(means, key=lambda mode: -means[mode])
    different = {
        frozenset((row["mode_a"], row["mode_b"]))
        for _, row in rows.iterrows()
        if pd.notna(row["p_holm"]) and row["p_holm"] < alpha
    }
    return compact_letter_display(groups, different)


def annotate_between_model_tests(
    ax: plt.Axes,
    tests: pd.DataFrame,
    metric: str,
    modes: list[str],
    benchmarks: list[tuple[str, str]],
    x: np.ndarray,
    width: float,
) -> None:
    """Letters for mode differences within each model, and brackets with the between-model test per mode."""
    rows = tests.loc[(tests["family"] == "between_models_by_mode") & (tests["metric"] == metric)]
    offsets = {
        benchmark_id: (index - (len(benchmarks) - 1) / 2) * width
        for index, (benchmark_id, _) in enumerate(benchmarks)
    }
    pairs = [(a, b) for index, (a, _) in enumerate(benchmarks) for b, _ in benchmarks[index + 1:]]
    letters = {benchmark_id: mode_letters(tests, metric, benchmark_id) for benchmark_id, _ in benchmarks}
    # Reserve headroom above the data in axes coordinates, so log and linear axes behave alike.
    levels = len(pairs) if not rows.empty else 0
    data_fraction = 0.86 - 0.07 * max(levels - 1, 0) - (0.06 if any(letters.values()) else 0.0)
    bottom, top = ax.get_ylim()
    if ax.get_yscale() == "log":
        ax.set_ylim(bottom, bottom * (top / bottom) ** (1 / data_fraction))
    else:
        ticks = [tick for tick in ax.get_yticks() if bottom <= tick <= top]
        ax.set_ylim(bottom, bottom + (top - bottom) / data_fraction)
        ax.set_yticks(ticks)
    transform = ax.get_xaxis_transform()
    # The meaning of letters and brackets goes in the caption; the _stats.md files spell it out.
    if any(letters.values()):
        for benchmark_index, (benchmark_id, _) in enumerate(benchmarks):
            color = benchmark_style(benchmark_index)[0]
            for mode_index, mode in enumerate(modes):
                if mode in letters[benchmark_id]:
                    ax.text(x[mode_index] + offsets[benchmark_id], data_fraction + 0.01, letters[benchmark_id][mode],
                            ha="center", va="bottom", fontsize=5, fontweight="bold", color=color,
                            transform=transform)
        data_fraction += 0.06
    for level, (id_a, id_b) in enumerate(pairs):
        y = data_fraction + 0.02 + 0.07 * level
        for mode_index, mode in enumerate(modes):
            row = rows.loc[(rows["mode"] == mode) & (rows["benchmark_a"] == id_a) & (rows["benchmark_b"] == id_b)]
            if row.empty or pd.isna(row.iloc[0]["p_value"]):
                continue
            left, right = x[mode_index] + offsets[id_a], x[mode_index] + offsets[id_b]
            ax.plot([left, left, right, right], [y, y + 0.015, y + 0.015, y], color="black",
                    linewidth=0.5, transform=transform, clip_on=False)
            label = significance_label(row.iloc[0]["p_holm"])
            ax.text((left + right) / 2, y + (0.0 if "*" in label else 0.02), label,
                    ha="center", va="bottom", fontsize=7 if "*" in label else 5, transform=transform)


def make_biological_score_figure(
    paper_records: pd.DataFrame,
    summary: pd.DataFrame,
    output_dir: Path,
    formats: Iterable[str],
    ci_method: str = "bootstrap",
    tests: pd.DataFrame | None = None,
    size_mm: tuple[float, float] = PANEL_SIZE_MM,
) -> None:
    fig, ax = panel_figure(size_mm)
    grouped_metric_boxplots(ax, paper_records, summary, "biological_score", "Score", (0.0, 1.05),
                            ci_method, tests)
    save_panel(fig, output_dir, "biological_score_by_model_and_mode", formats)
    plt.close(fig)


def make_cost_figure(
    paper_records: pd.DataFrame,
    summary: pd.DataFrame,
    output_dir: Path,
    formats: Iterable[str],
    ci_method: str = "bootstrap",
    tests: pd.DataFrame | None = None,
    size_mm: tuple[float, float] = PANEL_SIZE_MM,
) -> None:
    fig, ax = panel_figure(size_mm)
    # Set the log scale before drawing so autoscaling works in log space.
    configure_cost_axis(ax, paper_records["total_cost_usd"], "y")
    grouped_metric_boxplots(ax, paper_records, summary, "total_cost_usd", "API cost per run (USD)", (None, None),
                            ci_method, tests)
    save_panel(fig, output_dir, "api_cost_by_model_and_mode", formats)
    plt.close(fig)


def make_metric_figure(
    paper_records: pd.DataFrame,
    summary: pd.DataFrame,
    metric: str,
    output_dir: Path,
    formats: Iterable[str],
    ci_method: str = "bootstrap",
    tests: pd.DataFrame | None = None,
    size_mm: tuple[float, float] = PANEL_SIZE_MM,
) -> None:
    _, label, log_scale = COMPARISON_METRICS[metric]
    fig, ax = panel_figure(size_mm)
    values = pd.to_numeric(paper_records[metric], errors="coerce").dropna()
    if log_scale and len(values) and (values > 0).all():
        ax.set_yscale("log")
        plain_log_ticks(ax.yaxis)
    grouped_metric_boxplots(ax, paper_records, summary, metric, label, (None, None), ci_method, tests)
    save_panel(fig, output_dir, EXTRA_METRIC_FIGURES[metric], formats)
    plt.close(fig)


def make_pareto_figure(
    summary: pd.DataFrame,
    output_dir: Path,
    formats: Iterable[str],
    size_mm: tuple[float, float] = PANEL_SIZE_MM,
) -> None:
    fig, ax = panel_figure(size_mm)
    modes = ordered_modes(summary)
    benchmarks = benchmark_series(summary)
    front = pareto_front(summary, "total_cost_usd_mean", "biological_score_mean")
    ax.plot(
        front["total_cost_usd_mean"],
        front["biological_score_mean"],
        color="#999999",
        linewidth=0.6,
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
                xerr=summary_error(row, "total_cost_usd", positive=True),
                yerr=summary_error(row, "biological_score"),
                fmt=marker,
                markersize=3.5,
                markerfacecolor=color,
                markeredgecolor="black",
                markeredgewidth=0.4,
                ecolor=color,
                elinewidth=0.6,
                capsize=1.2,
                capthick=0.6,
                zorder=3,
            )
    configure_pareto_cost_axis(ax, summary)
    ax.set_ylabel("Score")
    ax.set_ylim(0, 1.05)
    ax.grid(color="#EEEEEE", linewidth=0.4)
    ax.set_axisbelow(True)

    mode_handles = [
        Line2D([0], [0], marker="o", linestyle="none", markersize=3.5, markeredgecolor="black",
               markeredgewidth=0.4, markerfacecolor=analysis.MODE_COLORS.get(mode, "#777777"),
               label=analysis.MODE_LABELS.get(mode, mode))
        for mode in modes
    ]
    model_handles = [
        Line2D([0], [0], marker=benchmark_style(index)[1], linestyle="none", markersize=3.5,
               markeredgewidth=0.4, markerfacecolor="white", markeredgecolor="black", label=label)
        for index, (_, label) in enumerate(benchmarks)
    ]
    frontier_handle = [Line2D([0], [0], color="#999999", linewidth=0.6, linestyle="--", label="Pareto frontier")]
    # Both legends sit in the empty high-cost, low-score corner so the panel keeps its full width.
    mode_legend = ax.legend(handles=mode_handles, frameon=False, loc="lower right")
    ax.add_artist(mode_legend)
    ax.legend(handles=[*model_handles, *frontier_handle], frameon=False, loc="lower right",
              bbox_to_anchor=(0.6, 0.0))
    save_panel(fig, output_dir, "api_cost_biological_score_pareto_by_model", formats)
    plt.close(fig)


def make_overall_figure(
    overall_summary: pd.DataFrame,
    output_dir: Path,
    formats: Iterable[str],
    tests: pd.DataFrame | None = None,
    size_mm: tuple[float, float] = PANEL_SIZE_MM,
) -> None:
    fig, (score_ax, cost_ax) = panel_figure(size_mm, ncols=2)
    benchmarks = benchmark_series(overall_summary)
    positions = np.arange(len(benchmarks), dtype=float)
    for index, (benchmark_id, _) in enumerate(benchmarks):
        row = overall_summary.loc[overall_summary["benchmark_id"] == benchmark_id].iloc[0]
        color, marker = benchmark_style(index)
        for ax, metric in ((score_ax, "biological_score"), (cost_ax, "total_cost_usd")):
            ax.errorbar(
                positions[index], row[f"{metric}_mean"],
                yerr=summary_error(row, metric, positive=metric == "total_cost_usd"),
                fmt=marker, markersize=4, markerfacecolor=color, markeredgecolor="black", markeredgewidth=0.5,
                ecolor="black", elinewidth=0.6, capsize=2, capthick=0.6,
            )
    labels = [label for _, label in benchmarks]
    for ax in (score_ax, cost_ax):
        ax.set_xticks(positions)
        ax.set_xticklabels(labels, rotation=30, ha="right", rotation_mode="anchor")
        ax.set_xlim(-0.6, len(benchmarks) - 0.4)
        ax.grid(axis="y", color="#EEEEEE", linewidth=0.4)
    score_ax.set_ylabel("Mean biological score")
    score_ax.set_ylim(0, 1.05)
    configure_cost_axis(cost_ax, overall_summary["total_cost_usd_mean"], "y")
    if tests is not None and not tests.empty and len(benchmarks) == 2:
        for ax, metric in ((score_ax, "biological_score"), (cost_ax, "total_cost_usd")):
            row = tests.loc[(tests["family"] == "between_models_overall") & (tests["metric"] == metric)]
            if not row.empty:
                # A label above the data rather than an axes title.
                label = significance_label(row.iloc[0]["p_value"])
                ax.text(0.5, 1.0, label, transform=ax.transAxes, ha="center", va="bottom",
                        fontsize=7 if "*" in label else 5)
    save_panel(fig, output_dir, "overall_score_and_cost_by_model", formats)
    plt.close(fig)


TEST_FAMILY_TITLES = {
    "between_models_by_mode": "Between models, per mode (paired by paper; Holm across modes)",
    "between_models_overall": "Between models, mean over the Morpheus modes (paired by paper)",
    "execution": "Within each model: each Morpheus mode vs Python + web (Holm across the Morpheus modes)",
    "morpheus_modes_omnibus": "Within each model: Friedman test across the Morpheus modes",
    "morpheus_modes_pairwise": "Within each model: Morpheus modes pairwise (post hoc; Holm across pairs)",
    "modes_pairwise": "Within each model: all modes pairwise, as shown by the letters in the figure (Holm across all pairs)",
}


def format_value(value: float) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{value:.3g}"


def methods_text(ci_method: str) -> str:
    ci = (
        f"BCa bootstrap over papers ({BOOTSTRAP_RESAMPLES:,} resamples, seed {BOOTSTRAP_SEED})"
        if ci_method == "bootstrap" else "mean ± t·SD/√n over papers"
    )
    return (
        "Repetitions are averaged per paper first, so the paper is the unit of replication and every model "
        "and mode is compared on the same papers. Paired comparisons use two-sided Wilcoxon signed-rank tests "
        "on the paper-level differences, with zero differences kept in the ranking (Pratt) and the exact "
        "sign-flip null distribution, which stays valid with tied scores. Cost and active time are compared on a log scale, so their "
        "effect is a geometric-mean ratio. p (Holm) is adjusted within each table section and model; the "
        "omnibus and overall tests stand alone. Effect size: matched-pairs rank-biserial r (positive: a > b); "
        f"Friedman: Kendall's W. 95% confidence intervals: {ci}."
    )


def means_table(summary: pd.DataFrame, metric: str, by_mode: bool = True) -> list[str]:
    header = "| Model | Mode | Papers | Mean | 95% CI |" if by_mode else "| Model | Papers | Mean | 95% CI |"
    lines = [header, "|---|---|---|---|---|" if by_mode else "|---|---|---|---|"]
    for _, row in summary.iterrows():
        cells = [str(row["benchmark_label"])]
        if by_mode:
            cells.append(mode_label(str(row["mode"])))
        cells += [
            str(int(row[f"{metric}_paper_count"])),
            format_value(row[f"{metric}_mean"]),
            f"[{format_value(row[f'{metric}_ci_low'])}, {format_value(row[f'{metric}_ci_high'])}]",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def tests_table(tests: pd.DataFrame) -> list[str]:
    if tests.empty:
        return ["No tests (not enough paired papers)."]
    if (tests["test"] == "Friedman").all():
        lines = ["| Model | Conditions | Papers | χ² | p | Kendall's W |", "|---|---|---|---|---|---|"]
        for _, row in tests.iterrows():
            lines.append(
                f"| {row['scope']} | {row['condition_a']} | {int(row['n'])} | {format_value(row['statistic'])} "
                f"| {format_p(row['p_value'])} | {format_value(row['effect_size'])} |"
            )
        return lines
    lines = [
        "| Scope | a | b | Papers | Mean a | Mean b | Effect [95% CI] | W | p | p (Holm) | r |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for _, row in tests.iterrows():
        effect = (
            f"{'ratio' if row['effect_type'].startswith('ratio') else 'Δ'} {format_value(row['effect'])} "
            f"[{format_value(row['effect_ci_low'])}, {format_value(row['effect_ci_high'])}]"
        )
        lines.append(
            f"| {row['scope']} | {row['condition_a']} | {row['condition_b']} | {int(row['n'])} "
            f"| {format_value(row['mean_a'])} | {format_value(row['mean_b'])} | {effect} "
            f"| {format_value(row['statistic'])} | {format_p(row['p_value'])} | {format_p(row['p_holm'])} "
            f"| {format_value(row['effect_size'])} |"
        )
    return lines


def metric_test_sections(tests: pd.DataFrame, metric: str, families: list[str]) -> list[str]:
    lines = []
    for family in families:
        rows = tests.loc[(tests["family"] == family) & (tests["metric"] == metric)] if not tests.empty else tests
        if rows.empty:
            continue
        lines += ["", f"### {TEST_FAMILY_TITLES[family]}", "", *tests_table(rows)]
    return lines


def write_markdown(path: Path, title: str, intro: str, ci_method: str, body: list[str]) -> None:
    text = [f"# {title}", "", intro, "", "## Methods", "", methods_text(ci_method), *body, ""]
    path.write_text("\n".join(text), encoding="utf8")


def write_statistics_markdown(
    output_dir: Path,
    summary: pd.DataFrame,
    overall_summary: pd.DataFrame,
    tests: pd.DataFrame,
    ci_method: str,
) -> None:
    """One MD file next to each figure, plus statistical_tests.md with every test."""
    by_mode_families = [
        "between_models_by_mode", "modes_pairwise", "execution", "morpheus_modes_omnibus", "morpheus_modes_pairwise",
    ]
    figure_metrics = {
        "biological_score_by_model_and_mode": "biological_score",
        "api_cost_by_model_and_mode": "total_cost_usd",
        **{stem: metric for metric, stem in EXTRA_METRIC_FIGURES.items()},
    }
    for stem, metric in figure_metrics.items():
        if f"{metric}_mean" not in summary.columns:
            continue
        label = COMPARISON_METRICS[metric][1]
        write_markdown(
            output_dir / f"{stem}_stats.md",
            f"{label}: statistics for {stem}",
            "Box plots show paper-level means; the diamond and black bar are the mean across papers and its 95% CI. "
            "Brackets mark the Holm-adjusted between-model tests of the first table section (* p < 0.05, "
            "** p < 0.01, *** p < 0.001, n.s. not significant). Letters compare the modes of one model: modes "
            "that share no letter differ (pairwise Wilcoxon, Holm-adjusted, p < 0.05; second table section).",
            ci_method,
            ["", "## Means across papers", "", *means_table(summary, metric),
             "", "## Tests", *metric_test_sections(tests, metric, by_mode_families)],
        )
    pareto_body = []
    for metric in ("biological_score", "total_cost_usd"):
        pareto_body += ["", f"## {COMPARISON_METRICS[metric][1]}", "", *means_table(summary, metric),
                        *metric_test_sections(tests, metric, ["between_models_by_mode"])]
    write_markdown(
        output_dir / "api_cost_biological_score_pareto_by_model_stats.md",
        "Statistics for api_cost_biological_score_pareto_by_model",
        "Each point is a model × mode mean across papers with 95% CIs on both axes. Tests within each model are "
        "in biological_score_by_model_and_mode_stats.md and api_cost_by_model_and_mode_stats.md.",
        ci_method,
        pareto_body,
    )
    overall_body = []
    for metric in ("biological_score", "total_cost_usd"):
        overall_body += ["", f"## {COMPARISON_METRICS[metric][1]}", "",
                         *means_table(overall_summary, metric, by_mode=False),
                         *metric_test_sections(tests, metric, ["between_models_overall"])]
    write_markdown(
        output_dir / "overall_score_and_cost_by_model_stats.md",
        "Statistics for overall_score_and_cost_by_model",
        "Each paper is first averaged over the four Morpheus modes, then over papers.",
        ci_method,
        overall_body,
    )
    all_body = []
    for metric in [metric for metric in COMPARISON_METRICS if f"{metric}_mean" in summary.columns]:
        all_body += ["", f"## {COMPARISON_METRICS[metric][1]}",
                     *metric_test_sections(tests, metric, [*by_mode_families, "between_models_overall"])]
    write_markdown(output_dir / "statistical_tests.md", "Statistical tests", "All tests; also in statistical_tests.csv.",
                   ci_method, all_body)


def write_comparison_outputs(
    records: pd.DataFrame,
    output_dir: Path,
    formats: Iterable[str],
    ci_method: str = "bootstrap",
    show_significance: bool = True,
    panel_size_mm: Iterable[float] = PANEL_SIZE_MM,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    output_dir.mkdir(parents=True, exist_ok=True)
    included, excluded = split_never_started(records)
    excluded_columns = [
        column for column in ["benchmark_label", "paper", "mode", "repetition", "status", "total_cost_usd"]
        if column in excluded.columns
    ]
    excluded[excluded_columns].to_csv(output_dir / "benchmark_model_comparison_excluded_runs.csv", index=False)
    paper_records, summary = aggregate_comparison_records(included, ci_method)
    overall_papers, overall_summary = aggregate_overall_records(paper_records, ci_method)
    tests = compute_statistical_tests(paper_records, overall_papers, ci_method)
    tests.to_csv(output_dir / "statistical_tests.csv", index=False)
    paper_records.to_csv(output_dir / "benchmark_model_comparison_by_paper_mode.csv", index=False)
    summary.to_csv(output_dir / "benchmark_model_comparison_by_model_mode.csv", index=False)
    overall_papers.to_csv(output_dir / "benchmark_model_comparison_overall_by_paper.csv", index=False)
    overall_summary.to_csv(output_dir / "benchmark_model_comparison_overall.csv", index=False)
    analysis.configure_matplotlib()
    plt.rcParams.update(PANEL_STYLE)
    figure_tests = tests if show_significance else None
    size_mm = tuple(panel_size_mm)
    make_biological_score_figure(paper_records, summary, output_dir, formats, ci_method, figure_tests, size_mm)
    make_cost_figure(paper_records, summary, output_dir, formats, ci_method, figure_tests, size_mm)
    for metric in EXTRA_METRIC_FIGURES:
        if metric in paper_records.columns and paper_records[metric].notna().any():
            make_metric_figure(paper_records, summary, metric, output_dir, formats, ci_method, figure_tests, size_mm)
    make_pareto_figure(summary, output_dir, formats, size_mm)
    make_overall_figure(overall_summary, output_dir, formats, figure_tests, size_mm)
    write_statistics_markdown(output_dir, summary, overall_summary, tests, ci_method)
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
    _, summary = write_comparison_outputs(
        records, output_dir, args.formats, args.ci, args.significance, args.panel_size_mm
    )
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
                "biological_score_ci_low",
                "biological_score_ci_high",
                "biological_score_paper_count",
                "total_cost_usd_mean",
                "total_cost_usd_ci_low",
                "total_cost_usd_ci_high",
            ]
        ].to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
