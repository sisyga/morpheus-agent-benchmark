import json
import os
import sys
import unittest
from unittest import mock
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

import biological_score_comparison as comparison


class BiologicalScoreComparisonTests(unittest.TestCase):
    def test_default_grid_includes_endpoints_in_ten_bins(self) -> None:
        rows = pd.DataFrame({"manual_score": [0, 0.05, 0.3, 0.8, 0.9, 1],
                             "agent_biological_score": [0, 0.05, 0.3, 0.8, 0.9, 1]})
        counts, _, _ = comparison.score_count_grid(rows)
        self.assertEqual(counts.shape, (10, 10))
        self.assertEqual(counts.sum(), 6)
        self.assertEqual(counts[0, 0], 2)
        self.assertEqual(counts[3, 3], 1)
        self.assertEqual(counts[8, 8], 1)
        self.assertEqual(counts[-1, -1], 2)

    def test_regression_uses_unbinned_scores_and_fitted_intercept(self) -> None:
        rows = pd.DataFrame({"manual_score": [0, 0.2, 0.6, 1, float("nan")],
                             "agent_biological_score": [0.2, 0.3, 0.5, 0.7, 0]})
        metrics = comparison.regression_metrics(rows)
        self.assertAlmostEqual(metrics["regression_slope"], 0.5)
        self.assertAlmostEqual(metrics["regression_intercept"], 0.2)
        self.assertAlmostEqual(metrics["regression_r_squared"], 1)
        self.assertAlmostEqual(metrics["slope_deviation_from_one"], -0.5)
        self.assertAlmostEqual(metrics["slope_deviation_from_half"], 0)

    def test_regression_handles_degenerate_inputs(self) -> None:
        for x, y in [([], []), ([0], [1]), ([0, 0], [0, 1])]:
            metrics = comparison.regression_metrics(pd.DataFrame(
                {"manual_score": x, "agent_biological_score": y}))
            self.assertTrue(all(pd.isna(value) for value in metrics.values()))
        metrics = comparison.regression_metrics(pd.DataFrame(
            {"manual_score": [0, 1], "agent_biological_score": [0.5, 0.5]}))
        self.assertAlmostEqual(metrics["regression_slope"], 0)
        self.assertTrue(pd.isna(metrics["regression_r_squared"]))

    def test_score_count_grid_counts_duplicate_coordinates(self) -> None:
        rows = pd.DataFrame.from_records(
            [
                {"manual_score": 0.8, "agent_biological_score": 0.8},
                {"manual_score": 0.8, "agent_biological_score": 0.8},
                {"manual_score": 0.6, "agent_biological_score": 0.4},
            ]
        )

        counts, x_edges, y_edges = comparison.score_count_grid(rows, bins=10)

        self.assertEqual(counts.sum(), 3)
        self.assertEqual(counts[8, 8], 2)
        self.assertEqual(counts[4, 6], 1)
        self.assertEqual(len(x_edges), 11)
        self.assertEqual(len(y_edges), 11)

    def test_score_heatmap_combines_coordinates_across_modes_and_paper_types(self) -> None:
        rows = pd.DataFrame.from_records(
            [
                {
                    "join_status": "matched",
                    "mode": "python_web",
                    "manual_paper_number": 1,
                    "manual_score": 0.8,
                    "agent_biological_score": 0.8,
                },
                {
                    "join_status": "matched",
                    "mode": "morpheus_mcp",
                    "manual_paper_number": 11,
                    "manual_score": 0.8,
                    "agent_biological_score": 0.8,
                },
            ]
        )

        with TemporaryDirectory() as tmp, mock.patch("matplotlib.axes.Axes.scatter", autospec=True) as scatter:
            written = comparison.write_scatter_plot(rows, Path(tmp) / "scatter.png")

        self.assertTrue(written)
        scatter.assert_not_called()

    def test_load_manual_scores_rejects_missing_required_columns(self) -> None:
        with TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "manual.csv"
            pd.DataFrame.from_records([{"mode": "python_web"}]).to_csv(csv_path, index=False)

            with self.assertRaisesRegex(ValueError, "Manual score CSV is missing required columns"):
                comparison.load_manual_scores(csv_path)

    def test_load_agent_scores_csv_rejects_missing_required_columns(self) -> None:
        with TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "agent.csv"
            pd.DataFrame.from_records([{"mode": "python_web"}]).to_csv(csv_path, index=False)

            with self.assertRaisesRegex(ValueError, "Agent score CSV is missing required columns: score"):
                comparison.load_agent_scores_csv(csv_path)

    def test_agent_clause_csv_collapses_to_one_score_per_run(self) -> None:
        with TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "benchmark_biological_scores.csv"
            write_agent_clause_csv(
                csv_path,
                [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_cli",
                        "mode_label": "Morpheus CLI",
                        "run_id": "20260524_002844_01_Szabo2010__morpheus_cli__rep01",
                        "repetition": 1.0,
                        "status": "scored",
                        "score": 0.5,
                        "clause_id": "a",
                        "biological_score_path": "/run/biological_score.json",
                    },
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_cli",
                        "mode_label": "Morpheus CLI",
                        "run_id": "20260524_002844_01_Szabo2010__morpheus_cli__rep01",
                        "repetition": 1.0,
                        "status": "scored",
                        "score": 0.5,
                        "clause_id": "b",
                        "biological_score_path": "/run/biological_score.json",
                    },
                ],
            )

            rows = comparison.load_agent_scores(csv_path)

            self.assertEqual(len(rows), 1)
            row = rows.iloc[0]
            self.assertEqual(row["canonical_paper_stem"], "01_Szabo2010")
            self.assertEqual(row["mode"], "morpheus_cli")
            self.assertEqual(row["repetition"], 1)
            self.assertAlmostEqual(row["agent_biological_score"], 0.5)
            self.assertEqual(row["agent_clause_count"], 2)
            self.assertFalse(row["agent_score_conflict"])

    def test_agent_clause_csv_marks_conflicting_scores(self) -> None:
        with TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "benchmark_biological_scores.csv"
            write_agent_clause_csv(
                csv_path,
                [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_cli",
                        "run_id": "20260524_002844_01_Szabo2010__morpheus_cli__rep01",
                        "score": 0.5,
                        "clause_id": "a",
                    },
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_cli",
                        "run_id": "20260524_002844_01_Szabo2010__morpheus_cli__rep01",
                        "score": 1.0,
                        "clause_id": "b",
                    },
                ],
            )

            row = comparison.load_agent_scores_csv(csv_path).iloc[0]

            self.assertAlmostEqual(row["agent_biological_score"], 0.5)
            self.assertTrue(row["agent_score_conflict"])
            self.assertEqual(row["agent_clause_count"], 2)

    def test_comparison_joins_manual_and_agent_scores_by_paper_mode_repetition(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manual_path = root / "manual_biological_scores.csv"
            agent_path = root / "benchmark_biological_scores.csv"
            write_manual_csv(
                manual_path,
                [
                    {
                        "canonical_paper_stem": "01_Szabo2010",
                        "manual_paper_number": 1,
                        "paper_key": "szabo2010",
                        "paper_title": "Szabo et al. (2010)",
                        "workbook_run_id": "1b1",
                        "mode": "morpheus_cli",
                        "mode_label": "Morpheus CLI",
                        "repetition": 1,
                        "manual_score": 0.25,
                        "manual_score_source": "workbook_mean_score",
                    },
                    {
                        "canonical_paper_stem": "01_Szabo2010",
                        "manual_paper_number": 1,
                        "paper_key": "szabo2010",
                        "paper_title": "Szabo et al. (2010)",
                        "workbook_run_id": "1b2",
                        "mode": "morpheus_cli",
                        "mode_label": "Morpheus CLI",
                        "repetition": 2,
                        "manual_score": 1.0,
                        "manual_score_source": "workbook_mean_score",
                    },
                ],
            )
            write_agent_clause_csv(
                agent_path,
                [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_cli",
                        "mode_label": "Morpheus CLI",
                        "run_id": "20260524_002844_01_Szabo2010__morpheus_cli__rep01",
                        "repetition": 1,
                        "status": "scored",
                        "score": 0.75,
                        "clause_id": "a",
                        "biological_score_path": "/run/rep01/biological_score.json",
                    }
                ],
            )

            rows = comparison.compare_manual_to_agent(manual_path, agent_path)

            matched = rows.loc[rows["repetition"] == 1].iloc[0]
            self.assertEqual(matched["join_status"], "matched")
            self.assertAlmostEqual(matched["score_delta"], 0.5)
            self.assertAlmostEqual(matched["abs_error"], 0.5)
            self.assertEqual(matched["agent_run_id"], "20260524_002844_01_Szabo2010__morpheus_cli__rep01")

            missing = rows.loc[rows["repetition"] == 2].iloc[0]
            self.assertEqual(missing["join_status"], "missing_agent_run")
            self.assertTrue(pd.isna(missing["agent_biological_score"]))

    def test_comparison_reports_missing_manual_rows_and_scores(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manual_path = root / "manual_biological_scores.csv"
            agent_path = root / "benchmark_biological_scores.csv"
            write_manual_csv(
                manual_path,
                [
                    {
                        "canonical_paper_stem": "01_Szabo2010",
                        "manual_paper_number": 1,
                        "paper_key": "szabo2010",
                        "paper_title": "Szabo et al. (2010)",
                        "workbook_run_id": "1b1",
                        "mode": "morpheus_cli",
                        "mode_label": "Morpheus CLI",
                        "repetition": 1,
                        "manual_score": "",
                        "manual_score_source": "missing",
                    }
                ],
            )
            write_agent_clause_csv(
                agent_path,
                [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_cli",
                        "run_id": "20260524_002844_01_Szabo2010__morpheus_cli__rep01",
                        "repetition": 1,
                        "score": 0.75,
                        "clause_id": "a",
                    },
                    {
                        "paper": "02_Thapa2024.pdf",
                        "mode": "morpheus_cli",
                        "run_id": "20260524_002844_02_Thapa2024__morpheus_cli__rep01",
                        "repetition": 1,
                        "score": 0.5,
                        "clause_id": "a",
                    },
                ],
            )

            rows = comparison.compare_manual_to_agent(manual_path, agent_path)

            self.assertEqual(
                rows.loc[rows["canonical_paper_stem"] == "01_Szabo2010", "join_status"].iloc[0],
                "missing_manual_score",
            )
            self.assertEqual(
                rows.loc[rows["canonical_paper_stem"] == "02_Thapa2024", "join_status"].iloc[0],
                "missing_manual_row",
            )

    def test_comparison_empty_inputs_and_agent_only_rows_use_stable_schema(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manual_path = root / "manual_biological_scores.csv"
            agent_path = root / "benchmark_biological_scores.csv"
            write_manual_csv(manual_path, [])
            manual_path.write_text(",".join(sorted(comparison.MANUAL_REQUIRED_COLUMNS)) + "\n", encoding="utf8")

            empty_rows = comparison.compare_manual_to_agent(manual_path, root)
            self.assertEqual(list(empty_rows.columns), comparison.COMPARISON_COLUMNS)
            self.assertTrue(empty_rows.empty)

            write_agent_clause_csv(
                agent_path,
                [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_cli",
                        "run_id": "20260524_002844_01_Szabo2010__morpheus_cli__rep01",
                        "score": 0.5,
                    }
                ],
            )
            agent_only = comparison.compare_manual_to_agent(manual_path, agent_path)

            self.assertEqual(agent_only.loc[0, "join_status"], "missing_manual_row")
            self.assertTrue(pd.isna(agent_only.loc[0, "manual_score"]))

    def test_scan_benchmark_directory_reads_biological_score_json_files(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "20260524_002844_01_Szabo2010__morpheus_cli__rep03"
            run_dir.mkdir()
            (run_dir / "biological_score.json").write_text(
                json.dumps(
                    {
                        "status": "scored",
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_cli",
                        "repetition": 3,
                        "runId": run_dir.name,
                        "score": 0.3333333333333333,
                        "clauses": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
                    }
                ),
                encoding="utf8",
            )

            rows = comparison.load_agent_scores(root)

            self.assertEqual(len(rows), 1)
            row = rows.iloc[0]
            self.assertEqual(row["canonical_paper_stem"], "01_Szabo2010")
            self.assertEqual(row["repetition"], 3)
            self.assertAlmostEqual(row["agent_biological_score"], 1 / 3)
            self.assertEqual(row["agent_clause_count"], 3)

    def test_load_agent_scores_uses_csv_fallbacks_and_rejects_unknown_files(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            analysis_dir = root / "analysis_figures"
            analysis_dir.mkdir()
            csv_path = analysis_dir / "benchmark_biological_scores.csv"
            write_agent_clause_csv(
                csv_path,
                [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_cli",
                        "run_id": "20260524_002844_01_Szabo2010__morpheus_cli__rep01",
                        "score": 0.5,
                        "clause_id": "a",
                    }
                ],
            )

            rows = comparison.load_agent_scores(root)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows.loc[0, "agent_biological_score"], 0.5)
            (root / "empty").mkdir()
            self.assertTrue(comparison.load_agent_scores(root / "empty").empty)
            with self.assertRaisesRegex(ValueError, "Unsupported agent score input"):
                comparison.load_agent_scores(root / "scores.json")

    def test_score_json_payload_falls_back_to_run_id_fields(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "20260524_002844_01_Szabo2010__morpheus_cli__rep02"
            run_dir.mkdir()
            score_path = run_dir / "biological_score.json"
            score_path.write_text(
                json.dumps({"status": "scored", "score": 0.25, "clauses": [{"id": "a"}]}),
                encoding="utf8",
            )

            row = comparison.agent_rows_from_score_json(score_path).iloc[0]

            self.assertEqual(row["canonical_paper_stem"], "01_Szabo2010")
            self.assertEqual(row["mode"], "morpheus_cli")
            self.assertEqual(row["repetition"], 2)
            self.assertEqual(row["agent_run_id"], run_dir.name)
            self.assertEqual(row["agent_clause_count"], 1)

    def test_direct_score_json_and_invalid_json_use_stable_defaults(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "20260524_002844_01_Szabo2010__morpheus_cli__rep02"
            run_dir.mkdir()
            score_path = run_dir / "biological_score.json"
            score_path.write_text("{bad json", encoding="utf8")

            row = comparison.load_agent_scores(score_path).iloc[0]

            self.assertEqual(row["canonical_paper_stem"], "01_Szabo2010")
            self.assertTrue(pd.isna(row["agent_biological_score"]))
            self.assertEqual(row["agent_clause_count"], 1)
            self.assertEqual(comparison.read_json(root / "missing.json"), {})

    def test_benchmark_directory_prefers_fresh_score_jsons_over_derived_clause_csv(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            stale_csv = root / "analysis_figures" / "benchmark_biological_scores.csv"
            stale_csv.parent.mkdir()
            write_agent_clause_csv(
                stale_csv,
                [
                    {
                        "paper": "13_Mole2026.pdf",
                        "mode": "python_web",
                        "mode_label": "Python + web",
                        "run_id": "20260529_041330_13_Mole2026__python_web__rep03",
                        "repetition": 3,
                        "status": "scored",
                        "score": 1.0,
                        "clause_id": "chemotaxis_to_gland",
                        "biological_score_path": "/run/old/biological_score.json",
                    }
                ],
            )
            run_dir = root / "20260529_041330_13_Mole2026__python_web__rep03"
            run_dir.mkdir()
            (run_dir / "biological_score.json").write_text(
                json.dumps(
                    {
                        "status": "missing_scoreable_artifacts",
                        "paper": "13_Mole2026.pdf",
                        "mode": "python_web",
                        "repetition": 3,
                        "runId": run_dir.name,
                        "score": 0,
                        "clauses": [{"id": "chemotaxis_to_gland"}],
                    }
                ),
                encoding="utf8",
            )

            rows = comparison.load_agent_scores(root)

            self.assertEqual(len(rows), 1)
            row = rows.iloc[0]
            self.assertEqual(row["agent_run_id"], run_dir.name)
            self.assertEqual(row["agent_biological_status"], "missing_scoreable_artifacts")
            self.assertAlmostEqual(row["agent_biological_score"], 0)
            self.assertEqual(row["agent_score_path"], str(run_dir / "biological_score.json"))

    def test_benchmark_directory_preserves_insufficient_evidence_without_a_score(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "20260529_041330_13_Mole2026__python_web__rep03"
            run_dir.mkdir()
            score_path = run_dir / "biological_score.json"
            score_path.write_text(
                json.dumps(
                    {
                        "status": "insufficient_evidence",
                        "paper": "13_Mole2026.pdf",
                        "mode": "python_web",
                        "repetition": 3,
                        "runId": run_dir.name,
                        "score": None,
                        "clauses": [],
                    }
                ),
                encoding="utf8",
            )

            row = comparison.load_agent_scores(root).iloc[0]

            self.assertEqual(row["agent_biological_status"], "insufficient_evidence")
            self.assertTrue(pd.isna(row["agent_biological_score"]))
            self.assertEqual(row["agent_clause_count"], 0)
            self.assertEqual(row["agent_score_path"], str(score_path))

    def test_default_agent_scores_path_uses_benchmark_directory_when_score_jsons_exist(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            stale_csv = root / "analysis_figures" / "benchmark_biological_scores.csv"
            stale_csv.parent.mkdir()
            stale_csv.write_text("mode,score\npython_web,1\n", encoding="utf8")
            run_dir = root / "20260529_041330_13_Mole2026__python_web__rep03"
            run_dir.mkdir()
            (run_dir / "biological_score.json").write_text('{"score": 0}', encoding="utf8")

            self.assertEqual(comparison.default_agent_scores_path(root), root)

    def test_benchmark_directory_follows_versioned_score_paths_from_summary(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "20260529_041330_13_Mole2026__python_web__rep03"
            cohort_dir = run_dir / "biological_scores"
            cohort_dir.mkdir(parents=True)
            score_path = cohort_dir / "scorer-v3__criteria-v1__attempt-attempt_001.json"
            score_path.write_text(
                json.dumps(
                    {
                        "status": "insufficient_evidence",
                        "paper": "13_Mole2026.pdf",
                        "mode": "python_web",
                        "repetition": 3,
                        "runId": run_dir.name,
                        "score": None,
                        "clauses": [],
                    }
                ),
                encoding="utf8",
            )
            (root / "benchmark_summary.json").write_text(
                json.dumps(
                    {
                        "benchmarkRunDir": str(root),
                        "results": [
                            {
                                "runId": run_dir.name,
                                "biologicalScorePath": str(score_path.relative_to(run_dir)),
                            }
                        ],
                    }
                ),
                encoding="utf8",
            )

            row = comparison.load_agent_scores(root).iloc[0]

            self.assertEqual(row["agent_biological_status"], "insufficient_evidence")
            self.assertTrue(pd.isna(row["agent_biological_score"]))
            self.assertEqual(row["agent_score_path"], str(score_path))
            self.assertEqual(comparison.default_agent_scores_path(root), root)

    def test_default_agent_scores_path_uses_existing_csv_or_directory_fallback(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            root_csv = root / "benchmark_biological_scores.csv"
            root_csv.write_text("mode,score\npython_web,1\n", encoding="utf8")
            self.assertEqual(comparison.default_agent_scores_path(root), root_csv)

            root_csv.unlink()
            nested_csv = root / "analysis_figures" / "benchmark_biological_scores.csv"
            nested_csv.parent.mkdir()
            nested_csv.write_text("mode,score\npython_web,1\n", encoding="utf8")
            self.assertEqual(comparison.default_agent_scores_path(root), nested_csv)

            nested_csv.unlink()
            self.assertEqual(comparison.default_agent_scores_path(root), root)

    def test_empty_agent_score_scan_and_summary_helpers_return_stable_schemas(self) -> None:
        with TemporaryDirectory() as tmp:
            empty_scores = comparison.scan_agent_score_jsons(Path(tmp))

        self.assertEqual(list(empty_scores.columns), list(comparison.empty_agent_scores().columns))
        self.assertTrue(empty_scores.empty)
        self.assertTrue(comparison.collapse_agent_rows(pd.DataFrame()).empty)
        self.assertTrue(comparison.summarize_by_paper_mode(pd.DataFrame()).empty)

        no_matches = pd.DataFrame.from_records(
            [
                {
                    "canonical_paper_stem": "02_Thapa2024",
                    "manual_paper_number": 2,
                    "paper_title": "Thapa et al. (2024)",
                    "mode": "morpheus_cli",
                    "mode_label": "Morpheus CLI",
                    "join_status": "missing_agent_run",
                    "manual_score": 0.5,
                    "agent_biological_score": float("nan"),
                    "score_delta": float("nan"),
                    "abs_error": float("nan"),
                }
            ]
        )
        self.assertTrue(comparison.summarize_by_paper_mode(no_matches).empty)

    def test_scalar_helpers_handle_invalid_values_and_constant_correlation(self) -> None:
        bad_run_id = comparison.parse_run_id("bad")
        self.assertEqual(bad_run_id["canonical_paper_stem"], "")
        self.assertEqual(bad_run_id["mode"], "")
        self.assertTrue(pd.isna(bad_run_id["repetition"]))
        self.assertEqual(comparison.parse_run_id("20260524_002844_01_Szabo2010__morpheus_cli__rep03")["repetition"], 3.0)
        self.assertTrue(pd.isna(comparison.positive_int_or_nan(True)))
        self.assertTrue(pd.isna(comparison.positive_int_or_nan("2.5")))
        self.assertEqual(comparison.positive_int_or_nan("2"), 2.0)
        self.assertTrue(pd.isna(comparison.nullable_number(False)))
        self.assertTrue(pd.isna(comparison.nullable_number(float("inf"))))
        self.assertEqual(comparison.nullable_number("0.75"), 0.75)
        self.assertTrue(
            pd.isna(comparison.pearson_correlation(pd.Series([1, 1, 1]), pd.Series([0, 1, 2])))
        )

    def test_write_scatter_plot_skips_when_no_rows_are_matched(self) -> None:
        with TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "plot.png"
            rows = pd.DataFrame.from_records(
                [
                    {
                        "join_status": "missing_agent_run",
                        "manual_score": 0.5,
                        "agent_biological_score": float("nan"),
                        "mode": "morpheus_cli",
                        "manual_paper_number": 1,
                    }
                ]
            )

            self.assertFalse(comparison.write_scatter_plot(rows, output_path))
            self.assertFalse(output_path.exists())

    def test_write_scatter_plot_writes_matched_modeling_and_biology_points(self) -> None:
        with TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "plot.png"
            rows = pd.DataFrame.from_records(
                [
                    {
                        "join_status": "matched",
                        "manual_score": 0.5,
                        "agent_biological_score": 0.75,
                        "mode": "morpheus_cli",
                        "manual_paper_number": 1,
                    },
                    {
                        "join_status": "matched",
                        "manual_score": 0.25,
                        "agent_biological_score": 0.5,
                        "mode": "custom_mode",
                        "manual_paper_number": 11,
                    },
                ]
            )

            self.assertTrue(comparison.write_scatter_plot(rows, output_path))
            self.assertTrue(output_path.exists())

    def test_export_writes_scatter_plot_in_png_svg_and_pdf_when_plots_are_enabled(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manual_path = root / "manual_biological_scores.csv"
            agent_path = root / "benchmark_biological_scores.csv"
            output_dir = root / "comparison"
            write_manual_csv(
                manual_path,
                [
                    {
                        "canonical_paper_stem": "01_Szabo2010",
                        "manual_paper_number": 1,
                        "paper_key": "szabo2010",
                        "paper_title": "Szabo et al. (2010)",
                        "workbook_run_id": "1b1",
                        "mode": "morpheus_cli",
                        "mode_label": "Morpheus CLI",
                        "repetition": 1,
                        "manual_score": 0.5,
                        "manual_score_source": "workbook_mean_score",
                    }
                ],
            )
            write_agent_clause_csv(
                agent_path,
                [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_cli",
                        "run_id": "20260524_002844_01_Szabo2010__morpheus_cli__rep01",
                        "score": 0.5,
                        "clause_id": "a",
                    }
                ],
            )

            written = comparison.export_comparison(manual_path, agent_path, output_dir)

            self.assertIn("scatter_plot", written)
            self.assertTrue(written["scatter_plot"].exists())
            self.assertTrue((output_dir / "biological_score_manual_vs_agent.svg").exists())
            self.assertTrue((output_dir / "biological_score_manual_vs_agent.pdf").exists())

    def test_export_writes_comparison_and_summary_csvs(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manual_path = root / "manual_biological_scores.csv"
            agent_path = root / "benchmark_biological_scores.csv"
            output_dir = root / "comparison"
            write_manual_csv(
                manual_path,
                [
                    {
                        "canonical_paper_stem": "01_Szabo2010",
                        "manual_paper_number": 1,
                        "paper_key": "szabo2010",
                        "paper_title": "Szabo et al. (2010)",
                        "workbook_run_id": "1b1",
                        "mode": "morpheus_cli",
                        "mode_label": "Morpheus CLI",
                        "repetition": 1,
                        "manual_score": 0.5,
                        "manual_score_source": "workbook_mean_score",
                    }
                ],
            )
            write_agent_clause_csv(
                agent_path,
                [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_cli",
                        "mode_label": "Morpheus CLI",
                        "run_id": "run_a",
                        "repetition": 1,
                        "status": "scored",
                        "score": 1.0,
                        "clause_id": "a",
                        "biological_score_path": "/run/biological_score.json",
                    }
                ],
            )

            written = comparison.export_comparison(manual_path, agent_path, output_dir, make_plots=False)

            self.assertTrue(written["rows"].exists())
            self.assertTrue(written["by_paper_mode"].exists())
            self.assertTrue(written["by_mode"].exists())
            self.assertTrue(written["by_criterion"].exists())
            self.assertTrue(written["discrepancy_report"].exists())
            self.assertIn("score_delta", written["rows"].read_text(encoding="utf8"))
            by_mode = pd.read_csv(written["by_mode"])
            self.assertEqual(by_mode.loc[0, "matched_count"], 1)
            self.assertAlmostEqual(by_mode.loc[0, "mean_abs_error"], 0.5)
            by_criterion = pd.read_csv(written["by_criterion"])
            self.assertEqual(by_criterion.loc[0, "discrepancy_count"], 1)
            self.assertIn("# Biological score discrepancy report", written["discrepancy_report"].read_text())

    def test_summary_spearman_correlation_does_not_require_scipy(self) -> None:
        rows = pd.DataFrame.from_records(
            [
                {
                    "mode": "morpheus_cli",
                    "mode_label": "Morpheus CLI",
                    "join_status": "matched",
                    "manual_score": 0.0,
                    "agent_biological_score": 0.25,
                    "score_delta": 0.25,
                    "abs_error": 0.25,
                },
                {
                    "mode": "morpheus_cli",
                    "mode_label": "Morpheus CLI",
                    "join_status": "matched",
                    "manual_score": 0.5,
                    "agent_biological_score": 0.5,
                    "score_delta": 0.0,
                    "abs_error": 0.0,
                },
                {
                    "mode": "morpheus_cli",
                    "mode_label": "Morpheus CLI",
                    "join_status": "matched",
                    "manual_score": 1.0,
                    "agent_biological_score": 0.75,
                    "score_delta": -0.25,
                    "abs_error": 0.25,
                },
            ]
        )

        summary = comparison.summarize_by_mode(rows)

        self.assertAlmostEqual(summary.loc[0, "spearman_r"], 1.0)

    def test_criterion_summary_counts_discrepancies_with_fraction_tolerance(self) -> None:
        rows = pd.DataFrame.from_records(
            [
                {
                    "canonical_paper_stem": "01_Szabo2010",
                    "manual_paper_number": 1,
                    "paper_title": "Szabo et al. (2010)",
                    "join_status": "matched",
                    "agent_biological_status": "scored",
                    "manual_score": 2 / 3,
                    "agent_biological_score": 0.666667,
                    "score_delta": 0.666667 - (2 / 3),
                    "abs_error": abs(0.666667 - (2 / 3)),
                },
                {
                    "canonical_paper_stem": "01_Szabo2010",
                    "manual_paper_number": 1,
                    "paper_title": "Szabo et al. (2010)",
                    "join_status": "matched",
                    "agent_biological_status": "scored",
                    "manual_score": 0.6,
                    "agent_biological_score": 0.8,
                    "score_delta": 0.2,
                    "abs_error": 0.2,
                },
                {
                    "canonical_paper_stem": "01_Szabo2010",
                    "manual_paper_number": 1,
                    "paper_title": "Szabo et al. (2010)",
                    "join_status": "matched",
                    "agent_biological_status": "model_failed",
                    "manual_score": 0.4,
                    "agent_biological_score": 0.0,
                    "score_delta": -0.4,
                    "abs_error": 0.4,
                },
            ]
        )

        summary = comparison.summarize_by_criterion(rows)

        self.assertEqual(len(summary), 1)
        criterion = summary.iloc[0]
        self.assertEqual(criterion["matched_count"], 3)
        self.assertEqual(criterion["scored_count"], 2)
        self.assertEqual(criterion["exact_match_count"], 1)
        self.assertEqual(criterion["discrepancy_count"], 2)
        self.assertAlmostEqual(criterion["discrepancy_rate"], 2 / 3)
        self.assertEqual(criterion["agent_over_score_count"], 1)
        self.assertEqual(criterion["agent_under_score_count"], 1)
        self.assertAlmostEqual(criterion["mean_signed_error"], -0.2 / 3)
        self.assertAlmostEqual(criterion["mean_abs_error"], 0.2)
        self.assertAlmostEqual(criterion["rmse"], (0.2 / 3) ** 0.5)
        self.assertAlmostEqual(criterion["max_abs_error"], 0.4)

    def test_criterion_summary_contains_only_authoritative_manual_criteria(self) -> None:
        rows = pd.DataFrame.from_records(
            [
                {
                    "canonical_paper_stem": "01_Szabo2010",
                    "manual_paper_number": 1,
                    "paper_title": "Szabo et al. (2010)",
                    "join_status": "missing_agent_run",
                    "agent_biological_status": "",
                    "manual_score": 0.5,
                    "agent_biological_score": float("nan"),
                    "score_delta": float("nan"),
                    "abs_error": float("nan"),
                },
                {
                    "canonical_paper_stem": "01_Szabo2010",
                    "manual_paper_number": float("nan"),
                    "paper_title": float("nan"),
                    "join_status": "missing_manual_row",
                    "agent_biological_status": "scored",
                    "manual_score": float("nan"),
                    "agent_biological_score": 0.75,
                    "score_delta": float("nan"),
                    "abs_error": float("nan"),
                },
                {
                    "canonical_paper_stem": "99_Unknown",
                    "manual_paper_number": float("nan"),
                    "paper_title": float("nan"),
                    "join_status": "missing_manual_row",
                    "agent_biological_status": "scored",
                    "manual_score": float("nan"),
                    "agent_biological_score": 1.0,
                    "score_delta": float("nan"),
                    "abs_error": float("nan"),
                },
            ]
        )

        summary = comparison.summarize_by_criterion(rows)

        self.assertEqual(summary["canonical_paper_stem"].tolist(), ["01_Szabo2010"])
        self.assertEqual(summary.loc[0, "row_count"], 1)

    def test_discrepancy_report_includes_overall_scored_only_and_error_patterns(self) -> None:
        rows = pd.DataFrame.from_records(
            [
                {
                    "canonical_paper_stem": "01_Szabo2010",
                    "manual_paper_number": 1,
                    "paper_title": "Szabo et al. (2010)",
                    "workbook_run_id": "1b1",
                    "mode": "morpheus_cli",
                    "mode_label": "Morpheus CLI",
                    "repetition": 1,
                    "join_status": "matched",
                    "agent_biological_status": "scored",
                    "manual_score": 0.5,
                    "agent_biological_score": 0.5,
                    "score_delta": 0.0,
                    "abs_error": 0.0,
                    "agent_run_id": "run-exact",
                },
                {
                    "canonical_paper_stem": "01_Szabo2010",
                    "manual_paper_number": 1,
                    "paper_title": "Szabo et al. (2010)",
                    "workbook_run_id": "1b2",
                    "mode": "morpheus_cli",
                    "mode_label": "Morpheus CLI",
                    "repetition": 2,
                    "join_status": "matched",
                    "agent_biological_status": "scored",
                    "manual_score": 0.5,
                    "agent_biological_score": 0.75,
                    "score_delta": 0.25,
                    "abs_error": 0.25,
                    "agent_run_id": "run-over",
                },
                {
                    "canonical_paper_stem": "02_Thapa2024",
                    "manual_paper_number": 2,
                    "paper_title": "Thapa et al. (2024)",
                    "workbook_run_id": "2d3",
                    "mode": "morpheus_mcp",
                    "mode_label": "Morpheus MCP",
                    "repetition": 3,
                    "join_status": "matched",
                    "agent_biological_status": "model_failed",
                    "manual_score": 1.0,
                    "agent_biological_score": 0.0,
                    "score_delta": -1.0,
                    "abs_error": 1.0,
                    "agent_run_id": "run-failed",
                },
                {
                    "canonical_paper_stem": "02_Thapa2024",
                    "manual_paper_number": 2,
                    "paper_title": "Thapa et al. (2024)",
                    "workbook_run_id": "2d2",
                    "mode": "morpheus_mcp",
                    "mode_label": "Morpheus MCP",
                    "repetition": 2,
                    "join_status": "missing_agent_score",
                    "agent_biological_status": "insufficient_evidence",
                    "manual_score": 0.5,
                    "agent_biological_score": float("nan"),
                    "score_delta": float("nan"),
                    "abs_error": float("nan"),
                    "agent_run_id": "run-insufficient",
                },
            ]
        )
        by_criterion = comparison.summarize_by_criterion(rows)
        by_mode = comparison.summarize_by_mode(rows)

        report = comparison.render_discrepancy_report(rows, by_criterion, by_mode)

        self.assertIn("All comparable runs | 3 | 1 (33.33%)", report)
        self.assertIn("Scorer status `scored` only | 2 | 1 (50.00%)", report)
        self.assertIn("model_failed | 1", report)
        self.assertIn("insufficient_evidence | 1", report)
        self.assertIn("0.500000 → 0.750000", report)
        self.assertIn("1.000000 → 0.000000", report)
        self.assertIn("02_Thapa2024", report)
        self.assertIn("run-failed", report)

    def test_discrepancy_report_renders_a_missing_repetition(self) -> None:
        rows = pd.DataFrame.from_records(
            [
                {
                    "canonical_paper_stem": "01_Szabo2010",
                    "manual_paper_number": 1,
                    "paper_title": "Szabo et al. (2010)",
                    "workbook_run_id": "bad-repetition",
                    "mode": "morpheus_cli",
                    "mode_label": "Morpheus CLI",
                    "repetition": float("nan"),
                    "join_status": "matched",
                    "agent_biological_status": "scored",
                    "manual_score": 0.5,
                    "agent_biological_score": 0.75,
                    "score_delta": 0.25,
                    "abs_error": 0.25,
                    "agent_run_id": "run-missing-repetition",
                }
            ]
        )

        report = comparison.render_discrepancy_report(
            rows,
            comparison.summarize_by_criterion(rows),
            comparison.summarize_by_mode(rows),
        )

        self.assertIn("run-missing-repetition", report)
        self.assertIn("| — | scored |", report)

    def test_summary_and_scalar_helpers_cover_empty_and_missing_score_status(self) -> None:
        self.assertTrue(comparison.summarize_by_mode(pd.DataFrame()).empty)
        row = pd.Series({"_merge": "both", "manual_score": 0.5, "agent_biological_score": float("nan")})
        self.assertEqual(comparison.join_status(row), "missing_agent_score")
        self.assertEqual(comparison.clean_string(None), "")
        self.assertEqual(comparison.canonical_stem(None), "")
        self.assertTrue(pd.isna(comparison.paper_number_from_stem(None)))
        self.assertTrue(pd.isna(comparison.positive_int_or_nan(object())))
        self.assertTrue(pd.isna(comparison.nullable_number(object())))
        self.assertTrue(pd.isna(comparison.correlation(pd.Series([1.0]), pd.Series([1.0]), "pearson")))

    def test_bash_stripped_windows_drive_path_falls_back_to_relative_tail(self) -> None:
        with TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            benchmark_dir = Path(tmp) / "20260524_002842_benchmark"
            benchmark_dir.mkdir()
            try:
                os.chdir(tmp)
                resolved = comparison.resolve_cli_path(
                    Path("W:20260524_002842_benchmark"),
                    "benchmark directory",
                    must_exist=True,
                    map_windows_drives=True,
                )
            finally:
                os.chdir(old_cwd)

            self.assertEqual(resolved, benchmark_dir.resolve())

    def test_quoted_windows_drive_path_falls_back_to_relative_tail(self) -> None:
        with TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            benchmark_dir = Path(tmp) / "20260524_002842_benchmark"
            benchmark_dir.mkdir()
            try:
                os.chdir(tmp)
                resolved = comparison.resolve_cli_path(
                    Path(r"W:\20260524_002842_benchmark"),
                    "benchmark directory",
                    must_exist=True,
                    map_windows_drives=True,
                )
            finally:
                os.chdir(old_cwd)

            self.assertEqual(resolved, benchmark_dir.resolve())

    def test_missing_windows_drive_path_error_is_mount_agnostic(self) -> None:
        with TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            try:
                os.chdir(tmp)
                with self.assertRaises(FileNotFoundError) as error:
                    comparison.resolve_cli_path(
                        Path("W:20260524_002842_benchmark"),
                        "benchmark directory",
                        must_exist=True,
                        map_windows_drives=True,
                    )
            finally:
                os.chdir(old_cwd)

        message = str(error.exception)
        self.assertIn("Windows drive path", message)
        self.assertIn("path as it exists on this machine", message)
        self.assertIn("quote Windows-style paths", message)
        self.assertNotIn("/mnt/", message)

    def test_path_candidate_helpers_cover_non_drive_paths_and_missing_outputs(self) -> None:
        path = Path("plain/path")
        self.assertEqual(comparison.path_candidates(path, handle_windows_drive_paths=True), [path])
        self.assertIsNone(comparison.windows_drive_path_parts(path))
        self.assertIsNone(comparison.windows_drive_relative_tail(path))
        self.assertEqual(comparison.resolve_cli_path(path, "output", must_exist=False, map_windows_drives=False), path)
        self.assertIsNone(comparison.first_existing([Path("missing-a"), Path("missing-b")]))

    def test_main_reports_success_and_validation_errors(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manual_path = root / "manual_biological_scores.csv"
            agent_path = root / "benchmark_biological_scores.csv"
            output_dir = root / "comparison"
            write_manual_csv(
                manual_path,
                [
                    {
                        "canonical_paper_stem": "01_Szabo2010",
                        "manual_paper_number": 1,
                        "paper_key": "szabo2010",
                        "paper_title": "Szabo et al. (2010)",
                        "workbook_run_id": "1b1",
                        "mode": "morpheus_cli",
                        "mode_label": "Morpheus CLI",
                        "repetition": 1,
                        "manual_score": 0.5,
                        "manual_score_source": "workbook_mean_score",
                    }
                ],
            )
            write_agent_clause_csv(
                agent_path,
                [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_cli",
                        "run_id": "20260524_002844_01_Szabo2010__morpheus_cli__rep01",
                        "score": 0.5,
                        "clause_id": "a",
                    }
                ],
            )

            with mock.patch("builtins.print") as printer:
                exit_code = comparison.main(
                    [
                        str(root),
                        "--manual-csv",
                        str(manual_path),
                        "--agent-scores",
                        str(agent_path),
                        "--output-dir",
                        str(output_dir),
                        "--no-plots",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue((output_dir / "biological_score_manual_comparison.csv").exists())
            self.assertIn("Wrote row-level comparison", printer.call_args_list[0].args[0])
            self.assertTrue(any("Wrote discrepancy report" in call.args[0] for call in printer.call_args_list))

            plot_dir = root / "comparison_with_plot"
            with mock.patch("builtins.print") as plot_printer:
                plot_exit_code = comparison.main(
                    [
                        str(root),
                        "--manual-csv",
                        str(manual_path),
                        "--agent-scores",
                        str(agent_path),
                        "--output-dir",
                        str(plot_dir),
                    ]
                )

            self.assertEqual(plot_exit_code, 0)
            self.assertTrue((plot_dir / "biological_score_manual_vs_agent.png").exists())
            self.assertTrue(any("Wrote count heatmap" in call.args[0] for call in plot_printer.call_args_list))

            with mock.patch.object(sys, "stderr"):
                self.assertEqual(comparison.main([str(root / "missing")]), 2)


def write_manual_csv(path: Path, rows: list[dict[str, object]]) -> None:
    pd.DataFrame.from_records(rows).to_csv(path, index=False)


def write_agent_clause_csv(path: Path, rows: list[dict[str, object]]) -> None:
    pd.DataFrame.from_records(rows).to_csv(path, index=False)


if __name__ == "__main__":
    unittest.main()
