import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import compare_benchmarks as comparison


class CompareBenchmarksTests(unittest.TestCase):
    def test_parse_args_accepts_two_or_more_folders_and_defaults_to_all_figure_formats(self) -> None:
        args = comparison.parse_args(["run_a", "run_b", "run_c", "--labels", "A", "B", "C"])

        self.assertEqual(args.benchmark_dirs, ["run_a", "run_b", "run_c"])
        self.assertEqual(args.labels, ["A", "B", "C"])
        self.assertEqual(args.formats, ["png", "pdf", "svg"])
        self.assertIsNone(args.out_dir)
        self.assertFalse(args.force)

    def test_parse_args_rejects_a_single_folder_and_mismatched_labels(self) -> None:
        with mock.patch.object(sys, "stderr"):
            with self.assertRaises(SystemExit):
                comparison.parse_args(["run_a"])
            with self.assertRaises(SystemExit):
                comparison.parse_args(["run_a", "run_b", "--labels", "A"])

    def test_confidence_half_width_uses_t_times_standard_error(self) -> None:
        values = pd.Series([0.2, 0.4, 0.6, 0.8])
        expected = 3.182446305284263 * values.std(ddof=1) / 2

        self.assertAlmostEqual(comparison.confidence_half_width(values), expected)
        self.assertTrue(pd.isna(comparison.confidence_half_width(pd.Series([0.5]))))

    def test_runs_that_never_started_are_excluded_from_score_and_cost(self) -> None:
        records = pd.DataFrame(
            [
                {"paper": "p1.pdf", "total_tokens_m": 0.0, "total_cost_usd": 0.0},
                {"paper": "p2.pdf", "total_tokens_m": 1.5, "total_cost_usd": 2.0},
                {"paper": "p3.pdf", "total_tokens_m": 0.4, "total_cost_usd": 0.0},
            ]
        )

        included, excluded = comparison.split_never_started(records)

        self.assertEqual(excluded["paper"].tolist(), ["p1.pdf"])
        self.assertEqual(included["paper"].tolist(), ["p2.pdf", "p3.pdf"])

    def test_check_comparable_refuses_mixed_protocols_and_scorers_unless_forced(self) -> None:
        records = pd.DataFrame(
            [
                {"benchmark_label": "A", "protocol": "max_cycles_v1", "total_time_limit_ms": 0.0,
                 "benchmark_version": 1, "scorer_cohort": "scorer-v8__x"},
                {"benchmark_label": "B", "protocol": "time_limit_v2", "total_time_limit_ms": 14_400_000.0,
                 "benchmark_version": 2, "scorer_cohort": "scorer-v7__y"},
            ]
        )

        with self.assertRaisesRegex(ValueError, "different protocols") as raised:
            comparison.check_comparable(records, force=False)
        self.assertIn("different scorers", str(raised.exception))
        comparison.check_comparable(records, force=True)
        comparison.check_comparable(records.iloc[[0, 0]].assign(benchmark_label=["A", "C"]), force=False)

    def test_aggregate_comparison_records_gives_each_paper_equal_weight(self) -> None:
        records = pd.DataFrame(
            [
                {
                    "benchmark_id": "run_a",
                    "benchmark_label": "gpt-5.5 · xhigh",
                    "agent_model": "gpt-5.5",
                    "mode": "morpheus_mcp",
                    "paper": "paper_1.pdf",
                    "repetition": 1,
                    "biological_score": 0.2,
                    "total_cost_usd": 1.0,
                },
                {
                    "benchmark_id": "run_a",
                    "benchmark_label": "gpt-5.5 · xhigh",
                    "agent_model": "gpt-5.5",
                    "mode": "morpheus_mcp",
                    "paper": "paper_1.pdf",
                    "repetition": 2,
                    "biological_score": 0.4,
                    "total_cost_usd": 3.0,
                },
                {
                    "benchmark_id": "run_a",
                    "benchmark_label": "gpt-5.5 · xhigh",
                    "agent_model": "gpt-5.5",
                    "mode": "morpheus_mcp",
                    "paper": "paper_2.pdf",
                    "repetition": 1,
                    "biological_score": 0.7,
                    "total_cost_usd": 6.0,
                },
            ]
        )

        paper_records, summary = comparison.aggregate_comparison_records(records)

        self.assertEqual(paper_records["paper"].tolist(), ["paper_1.pdf", "paper_2.pdf"])
        self.assertEqual(paper_records["execution_count"].tolist(), [2, 1])
        self.assertAlmostEqual(paper_records.loc[0, "biological_score"], 0.3)
        self.assertAlmostEqual(summary.loc[0, "biological_score_mean"], 0.5)
        self.assertAlmostEqual(summary.loc[0, "total_cost_usd_mean"], 4.0)
        self.assertEqual(summary.loc[0, "paper_count_total"], 2)
        self.assertEqual(summary.loc[0, "biological_score_paper_count"], 2)
        self.assertEqual(summary.loc[0, "total_cost_usd_paper_count"], 2)
        self.assertEqual(summary.loc[0, "execution_count"], 3)

    def test_aggregate_comparison_records_reports_metric_specific_paper_counts(self) -> None:
        records = pd.DataFrame(
            [
                {
                    "benchmark_id": "run_a",
                    "benchmark_label": "gpt-5.5 · xhigh",
                    "agent_model": "gpt-5.5",
                    "mode": "morpheus_mcp",
                    "paper": "paper_1.pdf",
                    "repetition": 1,
                    "biological_score": 0.75,
                    "total_cost_usd": float("nan"),
                },
                {
                    "benchmark_id": "run_a",
                    "benchmark_label": "gpt-5.5 · xhigh",
                    "agent_model": "gpt-5.5",
                    "mode": "morpheus_mcp",
                    "paper": "paper_2.pdf",
                    "repetition": 1,
                    "biological_score": float("nan"),
                    "total_cost_usd": 4.0,
                },
            ]
        )

        _, summary = comparison.aggregate_comparison_records(records)

        self.assertEqual(summary.loc[0, "paper_count_total"], 2)
        self.assertEqual(summary.loc[0, "biological_score_paper_count"], 2)
        self.assertEqual(summary.loc[0, "biological_score_valid_only_paper_count"], 1)
        self.assertEqual(summary.loc[0, "total_cost_usd_paper_count"], 1)

    def test_load_comparison_records_labels_each_folder_from_its_model_config(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dirs = [root / "run_a", root / "run_b"]
            configs = [("benchmark-a", "gpt-5.5"), ("benchmark-b", "gpt-5.4-mini")]
            for benchmark_dir, (benchmark_id, model) in zip(benchmark_dirs, configs):
                benchmark_dir.mkdir()
                summary = {
                    "benchmarkId": benchmark_id,
                    "benchmarkRunDir": "Z:/stale/original/path",
                    "config": {"model": model, "reasoningEffort": "xhigh"},
                    "results": [
                        {
                            "paper": "01_Szabo2010.pdf",
                            "mode": "morpheus_mcp",
                            "repetition": 1,
                            "status": "completed",
                            "biologicalScore": 0.75,
                            "diagnostics": {
                                "tokens": {
                                    "input": 1_000_000,
                                    "cachedInput": 500_000,
                                    "output": 100_000,
                                    "reasoningOutput": 0,
                                    "total": 1_100_000,
                                }
                            },
                        }
                    ],
                }
                (benchmark_dir / "benchmark_summary.json").write_text(json.dumps(summary), encoding="utf8")

            records = comparison.load_comparison_records(benchmark_dirs)

        self.assertEqual(records["benchmark_id"].tolist(), ["benchmark-a", "benchmark-b"])
        self.assertEqual(
            records["benchmark_label"].tolist(),
            ["gpt-5.5 (xhigh)", "gpt-5.4-mini (xhigh)"],
        )
        self.assertTrue(records["total_cost_usd"].notna().all())

    def test_load_comparison_records_prefers_reconciled_analysis_csv_costs(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp) / "run_a"
            analysis_dir = benchmark_dir / "analysis_figures"
            analysis_dir.mkdir(parents=True)
            summary = {
                "benchmarkId": "benchmark-a",
                "config": {"model": "gpt-5.5", "reasoningEffort": "xhigh"},
                "results": [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_mcp",
                        "repetition": 1,
                        "biologicalScore": 0.75,
                        "diagnostics": {
                            "tokens": {
                                "input": 1_000_000,
                                "cachedInput": 500_000,
                                "output": 100_000,
                                "reasoningOutput": 0,
                                "total": 1_100_000,
                            }
                        },
                    }
                ],
            }
            (benchmark_dir / "benchmark_summary.json").write_text(json.dumps(summary), encoding="utf8")
            pd.DataFrame(
                [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_mcp",
                        "repetition": 1,
                        "agent_model": "gpt-5.5",
                        "biological_score": 0.75,
                        "biological_score_itt": 0.75,
                        "total_cost_usd": 123.45,
                    }
                ]
            ).to_csv(analysis_dir / "benchmark_analysis_by_run.csv", index=False)

            records = comparison.load_comparison_records([benchmark_dir])

        self.assertEqual(records.loc[0, "total_cost_usd"], 123.45)

    def test_load_comparison_records_falls_back_when_analysis_csv_schema_is_incompatible(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp) / "run_a"
            analysis_dir = benchmark_dir / "analysis_figures"
            analysis_dir.mkdir(parents=True)
            summary = {
                "benchmarkId": "benchmark-a",
                "config": {"model": "gpt-5.5", "reasoningEffort": "xhigh"},
                "results": [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_mcp",
                        "repetition": 1,
                        "biologicalScore": 0.75,
                        "diagnostics": {
                            "tokens": {
                                "input": 1_000_000,
                                "cachedInput": 500_000,
                                "output": 100_000,
                                "reasoningOutput": 0,
                                "total": 1_100_000,
                            }
                        },
                    }
                ],
            }
            (benchmark_dir / "benchmark_summary.json").write_text(json.dumps(summary), encoding="utf8")
            pd.DataFrame([{"paper": "stale.pdf", "mode": "morpheus_mcp"}]).to_csv(
                analysis_dir / "benchmark_analysis_by_run.csv", index=False
            )

            records = comparison.load_comparison_records([benchmark_dir])

        self.assertEqual(records.loc[0, "paper"], "01_Szabo2010.pdf")
        self.assertAlmostEqual(records.loc[0, "total_cost_usd"], 5.75)

    def test_pareto_front_excludes_more_expensive_or_lower_scoring_points(self) -> None:
        summary = pd.DataFrame(
            [
                {"name": "a", "cost": 1.0, "score": 0.4},
                {"name": "b", "cost": 2.0, "score": 0.3},
                {"name": "c", "cost": 2.0, "score": 0.6},
                {"name": "d", "cost": 3.0, "score": 0.6},
            ]
        )

        front = comparison.pareto_front(summary, "cost", "score")

        self.assertEqual(front["name"].tolist(), ["a", "c"])

    def test_configure_pareto_cost_axis_keeps_label_consistent_with_scale(self) -> None:
        for costs, expected_scale, label_fragment in [
            ([1.0, 2.0], "log", "log scale"),
            ([0.0, 2.0], "linear", "linear scale"),
        ]:
            with self.subTest(costs=costs):
                fig, ax = plt.subplots()
                summary = pd.DataFrame({"total_cost_usd_mean": costs})

                comparison.configure_pareto_cost_axis(ax, summary)

                self.assertEqual(ax.get_xscale(), expected_scale)
                self.assertIn(label_fragment, ax.get_xlabel())
                plt.close(fig)

    def test_grouped_metric_boxplots_draw_paper_distributions_and_mean_markers(self) -> None:
        paper_records = pd.DataFrame(
            [
                {
                    "benchmark_id": "run_a",
                    "benchmark_label": "Model A",
                    "mode": "morpheus_mcp",
                    "biological_score": 0.2,
                },
                {
                    "benchmark_id": "run_a",
                    "benchmark_label": "Model A",
                    "mode": "morpheus_mcp",
                    "biological_score": 0.8,
                },
                {
                    "benchmark_id": "run_b",
                    "benchmark_label": "Model B",
                    "mode": "morpheus_mcp",
                    "biological_score": 0.6,
                },
            ]
        )
        summary = paper_records.drop_duplicates(["benchmark_id", "mode"])
        fig, ax = plt.subplots()
        try:
            comparison.grouped_metric_boxplots(
                ax,
                paper_records,
                summary,
                "biological_score",
                "Biological score",
                (0.0, 1.05),
            )

            self.assertEqual(len(ax.patches), 2)
            self.assertEqual(
                sorted(line.get_ydata()[0] for line in ax.lines if line.get_marker() == "D"),
                [0.5, 0.6],
            )
            self.assertEqual(
                [text.get_text() for text in ax.get_legend().get_texts()],
                ["Model A", "Model B"],
            )
            self.assertAlmostEqual(ax.collections[1].get_offsets()[0, 0], 0.2)
        finally:
            plt.close(fig)

    def test_write_comparison_outputs_exports_three_figures_and_source_tables(self) -> None:
        rows = []
        for benchmark_id, benchmark_label, model, cost_factor in [
            ("run_a", "gpt-5.5 · xhigh", "gpt-5.5", 2.0),
            ("run_b", "gpt-5.4-mini · xhigh", "gpt-5.4-mini", 1.0),
        ]:
            for mode_index, mode in enumerate(["python_web", "morpheus_mcp"]):
                for paper_index, paper in enumerate(["paper_1.pdf", "paper_2.pdf"]):
                    rows.append(
                        {
                            "benchmark_id": benchmark_id,
                            "benchmark_label": benchmark_label,
                            "agent_model": model,
                            "mode": mode,
                            "paper": paper,
                            "repetition": 1,
                            "biological_score": 0.4 + mode_index * 0.2 + paper_index * 0.1,
                            "total_cost_usd": cost_factor * (mode_index + paper_index + 1),
                        }
                    )
        records = pd.DataFrame(rows)

        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            comparison.write_comparison_outputs(records, output_dir, ["png", "pdf", "svg"])

            expected_stems = [
                "biological_score_by_model_and_mode",
                "api_cost_by_model_and_mode",
                "api_cost_biological_score_pareto_by_model",
                "overall_score_and_cost_by_model",
            ]
            for stem in expected_stems:
                for suffix in ["png", "pdf", "svg"]:
                    self.assertTrue((output_dir / f"{stem}.{suffix}").exists())
            self.assertTrue((output_dir / "benchmark_model_comparison_by_paper_mode.csv").exists())
            self.assertTrue((output_dir / "benchmark_model_comparison_by_model_mode.csv").exists())
            self.assertTrue((output_dir / "benchmark_model_comparison_overall.csv").exists())
            self.assertTrue((output_dir / "benchmark_model_comparison_excluded_runs.csv").exists())


if __name__ == "__main__":
    unittest.main()
