import unittest
import math
import json
import sys
from unittest import mock
from tempfile import TemporaryDirectory
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import analyze_benchmark as analysis


class AnalyzeBenchmarkTests(unittest.TestCase):
    def test_parse_args_and_load_summary_cover_cli_defaults_and_missing_files(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            summary_path = benchmark_dir / "benchmark_summary.json"
            summary_path.write_text(json.dumps({"results": []}), encoding="utf8")

            with mock.patch.object(
                sys,
                "argv",
                ["analyze_benchmark.py", str(benchmark_dir), "--formats", "png", "--out-dir", str(benchmark_dir / "out")],
            ):
                args = analysis.parse_args()

            self.assertEqual(Path(args.benchmark_dir), benchmark_dir)
            self.assertEqual(args.formats, ["png"])
            self.assertEqual(Path(args.out_dir), benchmark_dir / "out")
            self.assertEqual(analysis.load_summary(benchmark_dir), {"results": []})

            with self.assertRaisesRegex(FileNotFoundError, "Missing benchmark summary"):
                analysis.load_summary(benchmark_dir / "missing")

    def test_analysis_duration_uses_agent_wall_time_including_mcp_simulation_but_excludes_host_time(self) -> None:
        result = {"durationMs": 160 * 60 * 60 * 1000}
        diagnostics = {
            "agentWallTimeMs": 20 * 60 * 1000,
            "morpheusSimulationTimeMs": 8 * 60 * 1000,
            "hostMorpheusRunTimeMs": 2 * 60 * 1000,
            "hostTechnicalEvaluationTimeMs": 30 * 1000,
        }

        self.assertEqual(analysis.analysis_duration_ms(result, diagnostics), 20 * 60 * 1000)

    def test_analysis_duration_uses_larger_subject_time_source_for_partial_recovery_diagnostics(self) -> None:
        diagnostics = {
            "agentWallTimeMs": 10 * 60 * 1000,
            "hostMorpheusRunTimeMs": 2 * 60 * 1000,
            "hostTechnicalEvaluationTimeMs": 30 * 1000,
        }

        duration = analysis.analysis_duration_ms(
            {"durationMs": 48 * 60 * 60 * 1000},
            diagnostics,
            legacy_agent_wall_ms=25 * 60 * 1000,
        )

        self.assertEqual(duration, 25 * 60 * 1000)

    def test_analysis_duration_prefers_completed_subject_time_over_timeout_inclusive_diagnostics(self) -> None:
        diagnostics = {"agentWallTimeMs": 40 * 60 * 1000}

        duration = analysis.analysis_duration_ms(
            {"durationMs": 48 * 60 * 60 * 1000},
            diagnostics,
            legacy_agent_wall_ms=25 * 60 * 1000,
        )

        self.assertEqual(duration, 25 * 60 * 1000)

    def test_analysis_duration_falls_back_to_duration_when_diagnostics_are_absent(self) -> None:
        self.assertEqual(analysis.analysis_duration_ms({"durationMs": 12_345}, {}), 12_345)

    def test_analysis_duration_omits_implausible_recovery_gap_without_diagnostics(self) -> None:
        duration = analysis.analysis_duration_ms({"durationMs": 13 * 60 * 60 * 1000}, {})

        self.assertTrue(math.isnan(duration))

    def test_records_from_summary_prefers_longer_subject_session_over_partial_diagnostics(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            run_dir = benchmark_dir / "run_a"
            session_path = run_dir / "codex_home" / "sessions" / "2026" / "05" / "26" / "subject.jsonl"
            session_path.parent.mkdir(parents=True)
            session_path.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-05-26T17:05:00.000Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "task_complete",
                            "duration_ms": 600_000,
                            "last_agent_message": json.dumps(
                                {
                                    "runId": "run_a",
                                    "status": "completed",
                                    "summary": "final attempt",
                                    "modelChanged": True,
                                    "morpheusRan": False,
                                    "needsAnotherCycle": False,
                                }
                            ),
                        },
                    }
                ),
                encoding="utf8",
            )
            summary = {
                "benchmarkRunDir": str(benchmark_dir),
                "results": [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "python_web",
                        "status": "completed",
                        "runId": "run_a",
                        "startedAt": "2026-05-26T16:00:00.000Z",
                        "finishedAt": "2026-05-26T18:00:00.000Z",
                        "durationMs": 2 * 60 * 60 * 1000,
                        "diagnostics": {
                            "agentWallTimeMs": 5 * 60 * 1000,
                            "hostMorpheusRunTimeMs": 2 * 60 * 1000,
                            "hostTechnicalEvaluationTimeMs": 30 * 1000,
                        },
                    }
                ],
            }

            df = analysis.records_from_summary(summary, benchmark_dir)

            self.assertEqual(df.loc[0, "duration_h"], 600_000 / 3_600_000)

    def test_records_from_summary_adds_timeout_upper_bounds_to_completed_subject_time(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            run_dir = benchmark_dir / "run_a"
            session_path = run_dir / "codex_home" / "sessions" / "subject.jsonl"
            session_path.parent.mkdir(parents=True)
            session_path.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-05-26T17:05:00.000Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "task_complete",
                            "duration_ms": 10 * 60 * 1000,
                            "last_agent_message": json.dumps(
                                {
                                    "runId": "run_a",
                                    "status": "completed",
                                    "summary": "final attempt",
                                    "modelChanged": True,
                                    "morpheusRan": True,
                                    "needsAnotherCycle": False,
                                }
                            ),
                        },
                    }
                ),
                encoding="utf8",
            )
            transcript_dir = run_dir / "transcripts"
            transcript_dir.mkdir()
            (transcript_dir / "cycle_01_timeout_restart_01.jsonl").write_text(
                json.dumps({"type": "turn.started"}),
                encoding="utf8",
            )
            (transcript_dir / "cycle_01.jsonl").write_text(
                json.dumps(
                    {
                        "type": "item.started",
                        "item": {"type": "command_execution", "status": "in_progress"},
                    }
                ),
                encoding="utf8",
            )
            summary = {
                "benchmarkRunDir": str(benchmark_dir),
                "config": {"codexTurnTimeoutMs": 90 * 60 * 1000},
                "results": [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_cli",
                        "status": "completed",
                        "runId": "run_a",
                        "startedAt": "2026-05-26T16:00:00.000Z",
                        "finishedAt": "2026-05-26T18:00:00.000Z",
                        "diagnostics": {"agentWallTimeMs": 20 * 60 * 1000},
                    }
                ],
            }

            df = analysis.records_from_summary(summary, benchmark_dir)

            self.assertEqual(df.loc[0, "duration_h"], 190 / 60)
            self.assertEqual(df.loc[0, "timeout_turns"], 2)
            self.assertEqual(df.loc[0, "timeout_upper_bound_min"], 180)
            mode_summary = analysis.summarize_by_mode(df)
            self.assertIn("timeout_upper_bound_min_mean", mode_summary.columns)
            self.assertEqual(
                mode_summary.loc[mode_summary["mode"] == "morpheus_cli", "timeout_upper_bound_min_mean"].iloc[0],
                180,
            )

    def test_records_from_summary_sums_legacy_recovery_sessions_but_excludes_preflight_and_scoring(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            run_dir = benchmark_dir / "run_a"

            def write_session(session_path: Path, duration_ms: int, last_agent_message: dict) -> None:
                session_path.parent.mkdir(parents=True, exist_ok=True)
                session_path.write_text(
                    json.dumps(
                        {
                            "timestamp": "2026-05-26T17:05:00.000Z",
                            "type": "event_msg",
                            "payload": {
                                "type": "task_complete",
                                "duration_ms": duration_ms,
                                "last_agent_message": json.dumps(last_agent_message),
                            },
                        }
                    ),
                    encoding="utf8",
                )

            session_dir = run_dir / "codex_home" / "sessions" / "2026" / "05" / "26"
            write_session(
                session_dir / "original.jsonl",
                300_000,
                {
                    "runId": "run_a",
                    "status": "in_progress",
                    "summary": "original attempt",
                    "modelChanged": True,
                    "morpheusRan": False,
                    "needsAnotherCycle": True,
                    "reproduction": None,
                },
            )
            write_session(
                session_dir / "preflight.jsonl",
                120_000,
                {
                    "runId": "run_a",
                    "status": "completed",
                    "summary": "ready",
                },
            )
            recovery_session_dir = run_dir / "codex_home" / "sessions" / "2026" / "06" / "01"
            write_session(
                recovery_session_dir / "recovery.jsonl",
                600_000,
                {
                    "runId": "run_a",
                    "status": "completed",
                    "summary": "recovered final attempt",
                    "modelChanged": True,
                    "morpheusRan": True,
                    "needsAnotherCycle": False,
                    "reproduction": {"total_score": 8},
                },
            )
            later_session_dir = run_dir / "codex_home" / "sessions" / "2026" / "06" / "12"
            write_session(
                later_session_dir / "repair.jsonl",
                900_000,
                {
                    "status": "scored",
                    "score": 0.5,
                    "summary": "later biological scoring repair",
                },
            )
            transcript_dir = run_dir / "transcripts"
            transcript_dir.mkdir(parents=True)
            for transcript_name, usage in {
                "cycle_01.jsonl": {
                    "input_tokens": 1_000,
                    "cached_input_tokens": 100,
                    "output_tokens": 200,
                    "reasoning_output_tokens": 50,
                },
                "cycle_02.jsonl": {
                    "input_tokens": 3_000,
                    "cached_input_tokens": 500,
                    "output_tokens": 700,
                    "reasoning_output_tokens": 100,
                },
                "preflight_command_runner_01.jsonl": {
                    "input_tokens": 9_000,
                    "cached_input_tokens": 900,
                    "output_tokens": 900,
                    "reasoning_output_tokens": 900,
                },
                "biological_scoring.jsonl": {
                    "input_tokens": 11_000,
                    "cached_input_tokens": 1_100,
                    "output_tokens": 1_100,
                    "reasoning_output_tokens": 1_100,
                },
            }.items():
                (transcript_dir / transcript_name).write_text(
                    json.dumps({"type": "turn.completed", "usage": usage}),
                    encoding="utf8",
                )
            summary = {
                "benchmarkRunDir": str(benchmark_dir),
                "results": [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_mcp",
                        "status": "completed",
                        "runId": "run_a",
                        "runManifestPath": str(run_dir / "run_manifest.json"),
                        "startedAt": "2026-05-25T18:00:00.000Z",
                        "finishedAt": "2026-05-26T18:00:00.000Z",
                        "durationMs": 23 * 60 * 60 * 1000,
                        "diagnostics": {
                            "tokens": {
                                "input": 99_000,
                                "cachedInput": 98_000,
                                "output": 97_000,
                                "reasoningOutput": 96_000,
                                "total": 196_000,
                            },
                            "agentWallTimeMs": 0,
                            "hostMorpheusRunTimeMs": 0,
                            "hostTechnicalEvaluationTimeMs": 0,
                        },
                    }
                ],
            }

            df = analysis.records_from_summary(summary, benchmark_dir)

            self.assertEqual(df.loc[0, "duration_h"], 900_000 / 3_600_000)
            self.assertEqual(df.loc[0, "cached_input_tokens_m"], 600 / 1_000_000)
            self.assertEqual(df.loc[0, "uncached_input_tokens_m"], 3_400 / 1_000_000)
            # Reasoning tokens are already included in output_tokens.
            self.assertEqual(df.loc[0, "output_reasoning_tokens_m"], 900 / 1_000_000)
            self.assertEqual(df.loc[0, "total_tokens_m"], 4_900 / 1_000_000)

    def test_records_report_attempt_contract_and_exclude_launcher_bypass_timing(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            run_dir = benchmark_dir / "run_a"
            transcript_dir = run_dir / "transcripts"
            transcript_dir.mkdir(parents=True)
            (transcript_dir / "subject.jsonl").write_text(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "command_execution",
                            "command": "/opt/morpheus/bin/morpheus --quiet -f model.xml --outdir attempts/attempt_001",
                            "status": "completed",
                            "exit_code": 0,
                        },
                    }
                ),
                encoding="utf8",
            )
            summary = {
                "benchmarkRunDir": str(benchmark_dir),
                "benchmarkProtocol": "time_limit_v2",
                "config": {"totalTimeLimitMs": 60_000},
                "results": [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_cli",
                        "runId": "run_a",
                        "runManifestPath": str(run_dir / "run_manifest.json"),
                        "stopReason": "agent_finished",
                        "attempts": 2,
                        "subjectExecutionMs": 60_000,
                        "morpheusSimulationMs": 30_000,
                        "diagnostics": {"tokens": {}},
                        "selectedExecutionId": "execution_1",
                        "executions": [
                            {
                                "executionId": "execution_1",
                                "runId": "run_a",
                                "workspaceDir": str(run_dir / "agent_workspace"),
                                "morpheusSimulationMs": 30_000,
                            }
                        ],
                        "attemptArtifactAudit": {
                            "executedAttempts": 2,
                            "missingModelXml": 1,
                            "missingReproductionReport": 2,
                            "missingLogs": 3,
                        },
                    }
                ],
            }

            row = analysis.records_from_summary(summary, benchmark_dir).iloc[0]

            self.assertTrue(row["launcher_bypass"])
            self.assertTrue(math.isnan(row["morpheus_time_min"]))
            self.assertEqual(row["attempts"], 2)
            self.assertEqual(row["missing_attempt_xml_count"], 1)
            self.assertEqual(row["missing_attempt_report_count"], 2)
            self.assertEqual(row["missing_attempt_log_count"], 3)
            execution = analysis.execution_records_from_summary(summary, benchmark_dir).iloc[0]
            self.assertTrue(execution["launcher_bypass"])
            self.assertTrue(math.isnan(execution["morpheus_time_min"]))

    def test_direct_morpheus_binary_detection_handles_windows_paths_and_option_order(self) -> None:
        self.assertTrue(
            analysis.command_uses_direct_morpheus_binary(
                r'C:\tools\morpheus.exe --quiet --num-threads 2 -f model.xml'
            )
        )
        self.assertFalse(analysis.command_uses_direct_morpheus_binary("morpheus -f model.xml"))
        self.assertFalse(
            analysis.command_uses_direct_morpheus_binary(
                "/tmp/session/benchmark-tools/morpheus -f model.xml"
            )
        )

    def test_attempt_records_use_timestamp_order_when_attempt_field_is_absent(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            run_dir = benchmark_dir / "run_a"
            late_dir = run_dir / "agent_workspace" / "attempts" / "z_late"
            early_dir = run_dir / "agent_workspace" / "attempts" / "a_early"
            late_dir.mkdir(parents=True)
            early_dir.mkdir(parents=True)
            (late_dir / "attempt_reproduction.json").write_text(
                json.dumps(
                    {
                        "iteration": 1,
                        "timestamp": "2026-05-21T12:05:00Z",
                        "source_coverage": 2,
                        "mechanism_mapping": 1,
                        "observable_alignment": 2,
                        "parameter_plausibility": 1,
                        "comment": "late",
                    }
                ),
                encoding="utf8",
            )
            (early_dir / "attempt_reproduction.json").write_text(
                json.dumps(
                    {
                        "iteration": 1,
                        "timestamp": "2026-05-21T12:00:00Z",
                        "source_coverage": 1,
                        "mechanism_mapping": 1,
                        "observable_alignment": 1,
                        "parameter_plausibility": 1,
                    }
                ),
                encoding="utf8",
            )
            summary = {
                "benchmarkRunDir": str(benchmark_dir),
                "results": [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_mcp",
                        "runId": "run_a",
                        "repetition": 1,
                        "runManifestPath": str(run_dir / "run_manifest.json"),
                        "status": "max_turns",
                    }
                ],
            }

            attempts = analysis.attempt_records_from_summary(summary, benchmark_dir)

            self.assertEqual(attempts["attempt_number"].tolist(), [1, 2])
            self.assertEqual(attempts["self_score"].tolist(), [4, 6])
            self.assertEqual(attempts["normalized_self_score"].tolist(), [0.5, 0.75])
            self.assertEqual(attempts["paper_short"].tolist(), ["Szabo2010", "Szabo2010"])

    def test_attempt_records_preserve_explicit_attempt_field(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            attempt_dir = benchmark_dir / "run_a" / "agent_workspace" / "attempts" / "custom"
            attempt_dir.mkdir(parents=True)
            (attempt_dir / "attempt_reproduction.json").write_text(
                json.dumps(
                    {
                        "attempt": 7,
                        "iteration": 2,
                        "timestamp": "2026-05-21T12:00:00Z",
                        "source_coverage": 2,
                        "mechanism_mapping": 2,
                        "observable_alignment": 2,
                        "parameter_plausibility": 2,
                    }
                ),
                encoding="utf8",
            )
            summary = {
                "benchmarkRunDir": str(benchmark_dir),
                "results": [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_skill",
                        "runId": "run_a",
                        "repetition": 1,
                    }
                ],
            }

            attempts = analysis.attempt_records_from_summary(summary, benchmark_dir)

            self.assertEqual(attempts["attempt_number"].tolist(), [7])
            self.assertEqual(attempts["self_score"].tolist(), [8])

    def test_attempt_records_accept_utf8_bom_json(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            attempt_dir = benchmark_dir / "run_a" / "agent_workspace" / "attempts" / "attempt_001"
            attempt_dir.mkdir(parents=True)
            (attempt_dir / "attempt_reproduction.json").write_text(
                "\ufeff"
                + json.dumps(
                    {
                        "iteration": 1,
                        "timestamp": "2026-05-21T12:00:00Z",
                        "source_coverage": 2,
                        "mechanism_mapping": 2,
                        "observable_alignment": 1,
                        "parameter_plausibility": 2,
                    }
                ),
                encoding="utf8",
            )
            summary = {
                "benchmarkRunDir": str(benchmark_dir),
                "results": [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_mcp",
                        "runId": "run_a",
                        "repetition": 1,
                    }
                ],
            }

            attempts = analysis.attempt_records_from_summary(summary, benchmark_dir)

            self.assertEqual(len(attempts), 1)
            self.assertEqual(attempts.loc[0, "self_score"], 7)

    def test_attempt_records_accept_windows_1252_json_comments(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            attempt_dir = benchmark_dir / "run_a" / "agent_workspace" / "attempts" / "attempt_001"
            attempt_dir.mkdir(parents=True)
            (attempt_dir / "attempt_reproduction.json").write_bytes(
                b'{'
                b'"iteration":1,'
                b'"timestamp":"2026-05-21T12:00:00Z",'
                b'"source_coverage":2,'
                b'"mechanism_mapping":2,'
                b'"observable_alignment":2,'
                b'"parameter_plausibility":2,'
                b'"comment":"paper\x92s CPM source model"'
                b'}'
            )
            summary = {
                "benchmarkRunDir": str(benchmark_dir),
                "results": [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_mcp",
                        "runId": "run_a",
                        "repetition": 1,
                    }
                ],
            }

            attempts = analysis.attempt_records_from_summary(summary, benchmark_dir)

            self.assertEqual(len(attempts), 1)
            self.assertEqual(attempts.loc[0, "self_score"], 8)
            self.assertEqual(attempts.loc[0, "comment"], "paper\u2019s CPM source model")

    def test_attempt_records_use_attempt_directory_number_before_timestamp(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            run_dir = benchmark_dir / "run_a"
            later_named_attempt = run_dir / "agent_workspace" / "attempts" / "attempt_015"
            earlier_named_attempt = run_dir / "agent_workspace" / "attempts" / "attempt_001"
            later_named_attempt.mkdir(parents=True)
            earlier_named_attempt.mkdir(parents=True)
            (later_named_attempt / "attempt_reproduction.json").write_text(
                json.dumps(
                    {
                        "iteration": 1,
                        "timestamp": "2026-05-21T12:00:00Z",
                        "source_coverage": 2,
                        "mechanism_mapping": 2,
                        "observable_alignment": 2,
                        "parameter_plausibility": 2,
                    }
                ),
                encoding="utf8",
            )
            (earlier_named_attempt / "attempt_reproduction.json").write_text(
                json.dumps(
                    {
                        "iteration": 1,
                        "timestamp": "2026-05-21T12:30:00Z",
                        "source_coverage": 1,
                        "mechanism_mapping": 1,
                        "observable_alignment": 1,
                        "parameter_plausibility": 1,
                    }
                ),
                encoding="utf8",
            )
            summary = {
                "benchmarkRunDir": str(benchmark_dir),
                "results": [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_cli_docs",
                        "runId": "run_a",
                        "repetition": 1,
                    }
                ],
            }

            attempts = analysis.attempt_records_from_summary(summary, benchmark_dir)

            self.assertEqual(attempts["attempt_number"].tolist(), [1, 15])

    def test_attempt_records_leave_failed_attempt_without_json_unscored(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            run_dir = benchmark_dir / "run_a"
            missing_dir = run_dir / "agent_workspace" / "agent_runs" / "cli_attempts" / "attempt_001"
            scored_dir = run_dir / "agent_workspace" / "agent_runs" / "cli_attempts" / "attempt_002"
            missing_dir.mkdir(parents=True)
            scored_dir.mkdir(parents=True)
            (missing_dir / "stderr.log").write_text("morpheus failed", encoding="utf8")
            (scored_dir / "attempt_reproduction.json").write_text(
                json.dumps(
                    {
                        "attempt": 2,
                        "iteration": 1,
                        "timestamp": "2026-05-21T12:05:00Z",
                        "source_coverage": 2,
                        "mechanism_mapping": 1,
                        "observable_alignment": 2,
                        "parameter_plausibility": 1,
                    }
                ),
                encoding="utf8",
            )
            summary = {
                "benchmarkRunDir": str(benchmark_dir),
                "results": [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_cli",
                        "runId": "run_a",
                        "repetition": 1,
                    }
                ],
            }

            attempts = analysis.attempt_records_from_summary(summary, benchmark_dir)
            missing = attempts.loc[attempts["attempt_number"] == 1].iloc[0]

            self.assertEqual(attempts["attempt_number"].tolist(), [1, 2])
            self.assertTrue(all(math.isnan(missing[field]) for field in analysis.ATTEMPT_SCORE_FIELDS))
            self.assertTrue(math.isnan(missing["self_score"]))
            self.assertTrue(math.isnan(missing["normalized_self_score"]))
            self.assertEqual(missing["folder_attempt"], 1)
            self.assertRegex(missing["timestamp"], r"^\d{4}-\d{2}-\d{2}T")
            self.assertIn("Missing attempt_reproduction.json", missing["comment"])
            self.assertEqual(Path(missing["attempt_dir"]).resolve(), missing_dir.resolve())

    def test_attempt_records_leave_missing_output_attempt_json_unscored(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            run_dir = benchmark_dir / "run_a"
            missing_dir = run_dir / "agent_workspace" / "attempts" / "attempt_001"
            scored_dir = run_dir / "agent_workspace" / "attempts" / "attempt_002"
            missing_dir.mkdir(parents=True)
            scored_dir.mkdir(parents=True)
            (missing_dir / "plot_00050.png").write_bytes(b"png")
            (missing_dir / "logger.csv").write_text("time,count\n0,1\n", encoding="utf8")
            (scored_dir / "attempt_reproduction.json").write_text(
                json.dumps(
                    {
                        "attempt": 2,
                        "iteration": 1,
                        "timestamp": "2026-05-21T12:05:00Z",
                        "source_coverage": 2,
                        "mechanism_mapping": 1,
                        "observable_alignment": 2,
                        "parameter_plausibility": 1,
                    }
                ),
                encoding="utf8",
            )
            summary = {
                "benchmarkRunDir": str(benchmark_dir),
                "results": [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_mcp",
                        "runId": "run_a",
                        "repetition": 1,
                    }
                ],
            }

            attempts = analysis.attempt_records_from_summary(summary, benchmark_dir)
            missing = attempts.loc[attempts["attempt_number"] == 1].iloc[0]

            self.assertEqual(attempts["attempt_number"].tolist(), [1, 2])
            self.assertTrue(math.isnan(missing["self_score"]))
            self.assertTrue(math.isnan(missing["normalized_self_score"]))
            self.assertTrue(math.isnan(missing["source_coverage"]))
            self.assertIn("not self-scored", missing["comment"])
            self.assertEqual(Path(missing["attempt_dir"]).resolve(), missing_dir.resolve())

    def test_attempt_records_leave_invalid_agent_attempt_json_unscored(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            run_dir = benchmark_dir / "run_a"
            attempt_dir = run_dir / "agent_workspace" / "attempts" / "attempt_001"
            attempt_dir.mkdir(parents=True)
            (attempt_dir / "attempt_reproduction.json").write_text("{bad json", encoding="utf8")
            summary = {
                "benchmarkRunDir": str(benchmark_dir),
                "results": [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_mcp",
                        "runId": "run_a",
                        "repetition": 1,
                    }
                ],
            }

            attempts = analysis.attempt_records_from_summary(summary, benchmark_dir)

            self.assertEqual(len(attempts), 1)
            self.assertTrue(math.isnan(attempts.loc[0, "self_score"]))
            self.assertIn("Invalid or unreadable", attempts.loc[0, "comment"])

    def test_attempt_records_do_not_infer_runner_attempts_as_agent_scores(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            run_dir = benchmark_dir / "run_a"
            runner_attempt = run_dir / "attempts" / "attempt_001"
            runner_attempt.mkdir(parents=True)
            (runner_attempt / "stderr.log").write_text("technical evaluation failed", encoding="utf8")
            summary = {
                "benchmarkRunDir": str(benchmark_dir),
                "results": [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_mcp",
                        "runId": "run_a",
                        "repetition": 1,
                    }
                ],
            }

            attempts = analysis.attempt_records_from_summary(summary, benchmark_dir)

            self.assertTrue(attempts.empty)

    def test_result_run_dir_prefers_copied_benchmark_over_existing_original(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            original_run = root / "original" / "run_a"
            copied_run = root / "copy" / "run_a"
            original_run.mkdir(parents=True)
            copied_run.mkdir(parents=True)
            stored_manifest = str(original_run / "run_manifest.json")

            self.assertEqual(
                analysis.result_run_dir({"runManifestPath": stored_manifest, "runId": "run_a"}, root / "copy"),
                copied_run,
            )
            self.assertEqual(
                analysis.result_run_dir({"runManifestPath": stored_manifest}, root / "copy"),
                copied_run,
            )
            self.assertEqual(
                analysis.result_run_dir({"runManifestPath": stored_manifest, "runId": "run_a"}, root / "elsewhere"),
                original_run,
            )

            (original_run / "biological_scores").mkdir()
            (copied_run / "biological_scores").mkdir()
            (original_run / "biological_scores" / "score.json").write_text("{}", encoding="utf8")
            (copied_run / "biological_scores" / "score.json").write_text("{}", encoding="utf8")
            stored_score = str(original_run / "biological_scores" / "score.json")
            self.assertEqual(
                analysis.run_artifact_path(stored_score, copied_run),
                copied_run / "biological_scores" / "score.json",
            )
            self.assertEqual(
                analysis.run_artifact_path(r"E:\runs\run_a\biological_scores\score.json", copied_run),
                copied_run / "biological_scores" / "score.json",
            )
            self.assertEqual(
                analysis.run_artifact_path("biological_scores/score.json", copied_run),
                copied_run / "biological_scores" / "score.json",
            )
            self.assertEqual(analysis.run_artifact_path(stored_score, root / "other_run"), Path(stored_score))

    def test_attempt_and_log_helpers_cover_path_and_time_edge_cases(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run_a"
            relative_manifest_run = root / "manifest_run"
            relative_manifest_run.mkdir()
            self.assertEqual(
                analysis.result_run_dir({"runManifestPath": "missing_parent/manifest_run/run_manifest.json"}, root),
                root / "manifest_run",
            )
            self.assertEqual(
                analysis.result_run_dir(
                    {"runManifestPath": r"E:\benchmarks\run_a\run_manifest.json", "runId": "run_a"},
                    root,
                ),
                run_dir,
            )
            self.assertEqual(analysis.result_run_dir({"runId": "run_a"}, root), run_dir)
            self.assertIsNone(analysis.result_run_dir({}, root))

            attempt_dir = run_dir / "agent_workspace" / "attempts" / "attempt_001"
            attempt_dir.mkdir(parents=True)
            (attempt_dir / "stdout.log").write_text("Simulation finished\nWall Time = 1hr 2min 3s 4ms\n", encoding="utf8")
            self.assertTrue(analysis.attempt_has_scoreable_outputs(attempt_dir))
            self.assertEqual(analysis.parse_duration_ms("1hr 2min 3s 4ms"), 3_723_004)
            self.assertEqual(analysis.morpheus_wall_time_ms_from_run_dir(run_dir, "morpheus_mcp"), 3_723_004)
            self.assertTrue(analysis.is_agent_attempt_dir(run_dir, attempt_dir))
            self.assertFalse(analysis.is_agent_attempt_dir(run_dir, run_dir / "attempts" / "attempt_001"))
            self.assertFalse(analysis.is_agent_attempt_dir(run_dir, run_dir / "agent_workspace" / "attempts" / "custom"))
            self.assertEqual(analysis.parse_timestamp_sort_key("not-a-date"), pd.Timestamp.max.tz_localize("UTC"))
            self.assertTrue(math.isnan(analysis.positive_int_or_nan(True)))
            self.assertTrue(analysis.attempt_records_from_summary({"results": [{"runId": "missing"}]}, root).empty)

    def test_attempt_records_do_not_infer_analysis_output_attempt_folders_as_agent_scores(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            run_dir = benchmark_dir / "run_a"
            analysis_output = run_dir / "agent_workspace" / "analysis_outputs" / "attempt_001"
            analysis_output.mkdir(parents=True)
            (analysis_output / "quantification_summary.json").write_text("{}", encoding="utf8")
            summary = {
                "benchmarkRunDir": str(benchmark_dir),
                "results": [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_mcp",
                        "runId": "run_a",
                        "repetition": 1,
                    }
                ],
            }

            attempts = analysis.attempt_records_from_summary(summary, benchmark_dir)

            self.assertTrue(attempts.empty)

    def test_cost_quality_records_use_normalized_quality_and_token_cost(self) -> None:
        summary = {
            "results": [
                {
                    "paper": "01_Szabo2010.pdf",
                    "mode": "morpheus_mcp",
                    "status": "completed",
                    "technicalScore": 7,
                    "reproductionScore": 6,
                    "diagnostics": {
                        "tokens": {"total": 2_000_000},
                        "agentWallTimeMs": 60_000,
                        "hostMorpheusRunTimeMs": 30_000,
                        "hostTechnicalEvaluationTimeMs": 30_000,
                    },
                }
            ]
        }
        df = analysis.records_from_summary(summary)

        pareto = analysis.cost_quality_records(df)

        self.assertEqual(pareto.loc[0, "mode"], "morpheus_mcp")
        self.assertEqual(pareto.loc[0, "total_tokens_m_mean"], 2.0)
        # No biological score present, so quality falls back to normalized reproduction score.
        self.assertEqual(pareto.loc[0, "quality_mean"], 0.75)
        self.assertEqual(pareto.loc[0, "duration_h_mean"], 60_000 / 3_600_000)

    def test_records_from_summary_reads_biological_score_from_summary_or_fallback_json(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            run_dir = benchmark_dir / "run_b"
            run_dir.mkdir()
            (run_dir / "biological_score.json").write_text(
                json.dumps({"ok": True, "status": "scored", "score": 0.25}),
                encoding="utf8",
            )
            summary = {
                "benchmarkRunDir": str(benchmark_dir),
                "results": [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_mcp",
                        "status": "completed",
                        "technicalScore": 7,
                        "reproductionScore": 8,
                        "biologicalScore": 0.75,
                        "biologicalScorePath": "summary/path/biological_score.json",
                        "runId": "run_a",
                    },
                    {
                        "paper": "02_Thapa2024.pdf",
                        "mode": "morpheus_mcp",
                        "status": "completed",
                        "technicalScore": 7,
                        "reproductionScore": 8,
                        "runId": "run_b",
                    },
                ],
            }

            df = analysis.records_from_summary(summary, benchmark_dir)

            self.assertEqual(df["biological_score"].tolist(), [0.75, 0.25])
            self.assertEqual(df["biological_scoring_status"].tolist(), ["scored", "scored"])
            self.assertEqual(df.loc[0, "biological_score_path"], "summary/path/biological_score.json")
            self.assertEqual(Path(df.loc[1, "biological_score_path"]).resolve(), (run_dir / "biological_score.json").resolve())

    def test_records_from_summary_reads_manual_biological_scores_from_benchmark_root(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            (benchmark_dir / "manual_biological_scores.csv").write_text(
                "\n".join(
                    [
                        "canonical_paper_stem,mode,repetition,manual_score,manual_score_source",
                        "01_Szabo2010,morpheus_mcp,1,0.6,workbook_mean_score",
                    ]
                ),
                encoding="utf8",
            )
            summary = {
                "benchmarkRunDir": str(benchmark_dir),
                "results": [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_mcp",
                        "repetition": 1,
                        "status": "completed",
                        "technicalScore": 7,
                        "reproductionScore": 8,
                        "biologicalScore": 0.75,
                    },
                ],
            }

            df = analysis.records_from_summary(summary, benchmark_dir)
            summary_by_mode = analysis.summarize_by_mode(df)

            self.assertEqual(df.loc[0, "biological_score"], 0.75)
            self.assertEqual(df.loc[0, "manual_biological_score"], 0.6)
            self.assertEqual(df.loc[0, "manual_biological_score_source"], "workbook_mean_score")
            self.assertEqual(summary_by_mode.loc[summary_by_mode["mode"] == "morpheus_mcp", "manual_biological_mean"].iloc[0], 0.6)

    def test_records_from_summary_assigns_paper_number_and_cohort(self) -> None:
        summary = {
            "results": [
                {"paper": "01_Szabo2010.pdf", "mode": "morpheus_mcp", "status": "completed"},
                {"paper": "11_Anlas2024.pdf", "mode": "morpheus_mcp", "status": "completed"},
                {"paper": "paper_without_number.pdf", "mode": "morpheus_mcp", "status": "completed"},
            ]
        }

        df = analysis.records_from_summary(summary)
        by_paper = df.set_index("paper")

        self.assertEqual(by_paper.loc["01_Szabo2010.pdf", "paper_number"], 1)
        self.assertEqual(by_paper.loc["01_Szabo2010.pdf", "paper_cohort"], "papers_01_10")
        self.assertEqual(
            by_paper.loc["01_Szabo2010.pdf", "paper_cohort_label"],
            "Papers 1-10 (modeling keywords)",
        )
        self.assertEqual(by_paper.loc["11_Anlas2024.pdf", "paper_number"], 11)
        self.assertEqual(by_paper.loc["11_Anlas2024.pdf", "paper_cohort"], "papers_11_15")
        self.assertEqual(
            by_paper.loc["11_Anlas2024.pdf", "paper_cohort_label"],
            "Papers 11-15 (biology abstraction)",
        )
        self.assertTrue(pd.isna(by_paper.loc["paper_without_number.pdf", "paper_number"]))
        self.assertEqual(by_paper.loc["paper_without_number.pdf", "paper_cohort"], "unclassified")

    def test_benchmark_version_is_stamped_or_inferred_and_mixed_versions_are_not_pooled(self) -> None:
        self.assertEqual(analysis.benchmark_version({"benchmarkVersion": 3}), 3)
        self.assertEqual(analysis.benchmark_version({"benchmarkProtocol": "time_limit_v2"}), 2)
        self.assertEqual(analysis.benchmark_version({}), 1)

        result = {"paper": "01_Szabo2010.pdf", "mode": "morpheus_mcp", "status": "completed"}
        v2 = analysis.records_from_summary({"benchmarkProtocol": "time_limit_v2", "results": [result]})
        v3 = analysis.records_from_summary(
            {"benchmarkProtocol": "time_limit_v2", "benchmarkVersion": 3, "results": [result]}
        )

        self.assertEqual(v2["benchmark_version"].tolist(), [2])
        self.assertEqual(v3["benchmark_version"].tolist(), [3])
        with self.assertRaisesRegex(ValueError, "benchmark_version"):
            analysis.summarize_by_mode(pd.concat([v2, v3], ignore_index=True))

    def test_paper_cohort_helpers_cover_unclassified_and_missing_paper_columns(self) -> None:
        self.assertEqual(analysis.paper_cohort_from_number(16), "unclassified")
        self.assertEqual(analysis.paper_cohort_from_number(float("nan")), "unclassified")

        from_paper = analysis.ensure_paper_cohort_columns(pd.DataFrame([{"paper": "02_Thapa2024.pdf"}]))
        self.assertEqual(from_paper.loc[0, "paper_number"], 2)
        self.assertEqual(from_paper.loc[0, "paper_cohort"], "papers_01_10")

        work = analysis.ensure_paper_cohort_columns(pd.DataFrame([{"mode": "morpheus_mcp"}]))

        self.assertTrue(pd.isna(work.loc[0, "paper_number"]))
        self.assertEqual(work.loc[0, "paper_cohort"], "unclassified")
        self.assertEqual(work.loc[0, "paper_cohort_label"], "Unclassified papers")

    def test_manual_score_loading_skips_invalid_rows_and_defaults_source(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            score_path = benchmark_dir / "manual_biological_scores.csv"
            score_path.write_text(
                "\n".join(
                    [
                        "canonical_paper_stem,mode,repetition,manual_score",
                        "01_Szabo2010_clean,morpheus_mcp,1,0.4",
                        "02_Thapa2024,,1,0.9",
                        "04_Empty,morpheus_mcp,1,",
                    ]
                ),
                encoding="utf8",
            )

            scores = analysis.load_manual_biological_scores(benchmark_dir)

            self.assertEqual(set(scores), {("01_Szabo2010", "morpheus_mcp", 1)})
            self.assertEqual(scores[("01_Szabo2010", "morpheus_mcp", 1)]["score"], 0.4)
            self.assertEqual(scores[("01_Szabo2010", "morpheus_mcp", 1)]["source"], "")

            bad_dir = benchmark_dir / "bad"
            bad_dir.mkdir()
            (bad_dir / "manual_biological_scores.csv").write_text("mode,manual_score\nmorpheus_mcp,1\n", encoding="utf8")
            with self.assertRaisesRegex(ValueError, "missing required columns"):
                analysis.load_manual_biological_scores(bad_dir)

    def test_manual_and_repetition_helpers_cover_missing_and_run_id_fallback(self) -> None:
        self.assertEqual(analysis.repetition_from_run_id("20260524_002844_01_Szabo2010__morpheus_cli__rep03"), 3)
        self.assertTrue(math.isnan(analysis.repetition_from_run_id("bad")))
        self.assertEqual(analysis.result_repetition({"runId": "x__rep2"}), 2)
        self.assertTrue(math.isnan(analysis.manual_biological_score_from_result({"repetition": "bad"}, {} )["score"]))
        self.assertTrue(math.isnan(analysis.manual_biological_score_from_result({"paper": "01_Szabo2010.pdf", "mode": "morpheus_mcp", "repetition": 1}, {})["score"]))
        self.assertEqual(analysis.first_non_empty(["", "  ", "source"]), "source")
        self.assertEqual(analysis.first_non_empty(["", None]), "")

    def test_biological_score_helpers_cover_invalid_json_and_clause_records(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            run_dir = benchmark_dir / "run_a"
            run_dir.mkdir()
            score_path = run_dir / "relative_score.json"
            score_path.write_text(
                json.dumps(
                    {
                        "status": "scored",
                        "score": 0.5,
                        "clauses": [
                            {
                                "id": "a",
                                "passed": True,
                                "observed_value": "yes",
                                "rationale": "ok",
                                "evidence": ["one", 2],
                            },
                            "not-a-clause",
                        ],
                    }
                ),
                encoding="utf8",
            )
            summary = {
                "benchmarkRunDir": str(benchmark_dir),
                "results": [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_mcp",
                        "runId": "run_a",
                        "repetition": 1,
                        "biologicalScorePath": "relative_score.json",
                    }
                ],
            }

            clauses = analysis.biological_clause_records_from_summary(summary, benchmark_dir)

            self.assertEqual(len(clauses), 1)
            self.assertEqual(clauses.loc[0, "clause_id"], "a")
            self.assertEqual(clauses.loc[0, "evidence"], "one; 2")
            self.assertEqual(clauses.loc[0, "score"], 0.5)

            missing = dict(summary)
            missing["results"] = [dict(summary["results"][0], biologicalScorePath="missing.json")]
            self.assertTrue(analysis.biological_clause_records_from_summary(missing, benchmark_dir).empty)

            score_path.write_text("{bad json", encoding="utf8")
            self.assertTrue(analysis.biological_clause_records_from_summary(summary, benchmark_dir).empty)

            score_path.write_text(json.dumps({"status": "scored", "score": 0.5, "clauses": {}}), encoding="utf8")
            self.assertTrue(analysis.biological_clause_records_from_summary(summary, benchmark_dir).empty)

            (run_dir / "biological_score.json").write_text("{bad json", encoding="utf8")
            invalid = analysis.biological_score_from_result({"runId": "run_a"}, benchmark_dir)
            self.assertTrue(math.isnan(invalid["score"]))
            self.assertEqual(invalid["status"], "invalid")

            self.assertTrue(analysis.biological_clause_records_from_summary({"results": [{}]}, benchmark_dir).empty)
            self.assertTrue(analysis.biological_clause_records_from_summary({"results": []}, benchmark_dir).empty)

    def test_biological_score_uses_explicit_versioned_path_for_null_outcomes(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            run_dir = benchmark_dir / "run_a"
            cohort_dir = run_dir / "biological_scores"
            cohort_dir.mkdir(parents=True)
            (run_dir / "biological_score.json").write_text(
                json.dumps({"status": "scored", "score": 1.0}),
                encoding="utf8",
            )
            cohort_path = cohort_dir / "scorer-v3__criteria-v1__attempt-attempt_001.json"
            cohort_path.write_text(
                json.dumps({"status": "insufficient_evidence", "score": None}),
                encoding="utf8",
            )

            score = analysis.biological_score_from_result(
                {
                    "runId": "run_a",
                    "biologicalScore": None,
                    "biologicalScorePath": str(cohort_path.relative_to(run_dir)),
                },
                benchmark_dir,
            )

            self.assertTrue(math.isnan(score["score"]))
            self.assertEqual(score["status"], "insufficient_evidence")
            self.assertEqual(score["path"], str(cohort_path))

    def test_summarize_by_mode_includes_biological_score_stats(self) -> None:
        df = pd.DataFrame(
            [
                {"mode": "morpheus_mcp", "paper": "a.pdf", "status": "completed", "biological_score": 0.25},
                {"mode": "morpheus_mcp", "paper": "b.pdf", "status": "completed", "biological_score": 0.75},
            ]
        )
        for column in [
            "technical_score",
            "reproduction_score",
            "duration_h",
            "morpheus_time_min",
            "agent_analysis_min",
            "cached_input_tokens_m",
            "uncached_input_tokens_m",
            "output_reasoning_tokens_m",
            "total_tokens_m",
            "cycles",
            "attempts",
        ]:
            df[column] = 0

        summary = analysis.summarize_by_mode(df)

        mcp = summary.loc[summary["mode"] == "morpheus_mcp"].iloc[0]
        self.assertEqual(mcp["biological_mean"], 0.5)
        self.assertAlmostEqual(mcp["biological_std"], math.sqrt(0.125))

    def test_summarize_by_paper_cohort_and_mode_includes_all_and_split_stats(self) -> None:
        rows = [
            {
                "paper": "01_Szabo2010.pdf",
                "paper_number": 1,
                "mode": "morpheus_mcp",
                "status": "completed",
                "technical_score": 7,
                "reproduction_score": 8,
                "biological_score": 1.0,
                "duration_h": 1.0,
                "morpheus_time_min": 2.0,
                "agent_analysis_min": 3.0,
                "cached_input_tokens_m": 0.1,
                "uncached_input_tokens_m": 0.2,
                "output_reasoning_tokens_m": 0.3,
                "total_tokens_m": 0.6,
                "cycles": 1,
                "attempts": 2,
            },
            {
                "paper": "11_Anlas2024.pdf",
                "paper_number": 11,
                "mode": "morpheus_mcp",
                "status": "completed",
                "technical_score": 0,
                "reproduction_score": 0,
                "biological_score": 0.0,
                "duration_h": 5.0,
                "morpheus_time_min": 6.0,
                "agent_analysis_min": 7.0,
                "cached_input_tokens_m": 0.4,
                "uncached_input_tokens_m": 0.5,
                "output_reasoning_tokens_m": 0.6,
                "total_tokens_m": 1.5,
                "cycles": 3,
                "attempts": 4,
            },
        ]

        summary = analysis.summarize_by_paper_cohort_and_mode(pd.DataFrame(rows))
        mcp_rows = summary.loc[summary["mode"] == "morpheus_mcp"].set_index("paper_cohort")

        self.assertEqual(mcp_rows.loc["all", "paper_cohort_label"], "All papers (1-15)")
        self.assertEqual(mcp_rows.loc["papers_01_10", "paper_cohort_label"], "Papers 1-10 (modeling keywords)")
        self.assertEqual(
            mcp_rows.loc["papers_11_15", "paper_cohort_label"],
            "Papers 11-15 (biology abstraction)",
        )
        self.assertEqual(mcp_rows.loc["all", "n"], 2)
        self.assertEqual(mcp_rows.loc["papers_01_10", "n"], 1)
        self.assertEqual(mcp_rows.loc["papers_11_15", "n"], 1)
        self.assertEqual(mcp_rows.loc["all", "technical_mean"], 3.5)
        self.assertEqual(mcp_rows.loc["papers_01_10", "technical_mean"], 7)
        self.assertEqual(mcp_rows.loc["papers_11_15", "technical_mean"], 0)

    def test_openai_pricing_lookup_contains_standard_api_rates(self) -> None:
        gpt55 = analysis.OPENAI_API_PRICING_USD_PER_1M_TOKENS["gpt-5.5"]
        mini = analysis.OPENAI_API_PRICING_USD_PER_1M_TOKENS["gpt-5.4-mini"]

        self.assertEqual(gpt55["input"], 5.0)
        self.assertEqual(gpt55["cached_input"], 0.5)
        self.assertEqual(gpt55["output"], 30.0)
        self.assertEqual(gpt55["pricing_tier_note"], "standard input tier up to 272K tokens")
        self.assertEqual(mini["input"], 0.75)
        self.assertEqual(mini["cached_input"], 0.075)
        self.assertEqual(mini["output"], 4.5)

    def test_openai_pricing_lookup_contains_gpt6_family_rates(self) -> None:
        expected = {
            "gpt-6-astra": (10.0, 1.0, 50.0),
            "gpt-6.1-sol": (2.0, 0.1, 10.0),
            "gpt-6-sol": (2.0, 0.2, 10.0),
            "gpt-6-luna": (0.1, 0.01, 0.5),
        }
        for model, (input_price, cached_price, output_price) in expected.items():
            price = analysis.OPENAI_API_PRICING_USD_PER_1M_TOKENS[model]
            self.assertEqual(
                (price["input"], price["cached_input"], price["output"]),
                (input_price, cached_price, output_price),
                model,
            )
            self.assertEqual(analysis.openai_pricing_model_key(model), model)
        self.assertEqual(analysis.openai_pricing_model_key("gpt-6.1-sol-2026-09-01"), "gpt-6.1-sol")

        # Cache writes cost 1.25x input, matching the listed $2.50 for gpt-6.1-sol.
        costs = analysis.token_costs_usd("gpt-6.1-sol", 1.0, 1.0, 1.0, 1.0)
        self.assertEqual(costs["cached_input_cost_usd"], 0.1)
        self.assertEqual(costs["cache_write_input_cost_usd"], 2.5)
        self.assertEqual(costs["uncached_input_cost_usd"], 2.0)
        self.assertEqual(costs["output_reasoning_cost_usd"], 10.0)
        self.assertAlmostEqual(costs["total_cost_usd"], 14.6)

    def test_openai_pricing_lookup_contains_gpt56_family_rates_and_alias(self) -> None:
        sol = analysis.OPENAI_API_PRICING_USD_PER_1M_TOKENS["gpt-5.6-sol"]
        terra = analysis.OPENAI_API_PRICING_USD_PER_1M_TOKENS["gpt-5.6-terra"]
        luna = analysis.OPENAI_API_PRICING_USD_PER_1M_TOKENS["gpt-5.6-luna"]

        self.assertEqual(sol, {
            "input": 4.0,
            "cached_input": 0.4,
            "output": 20.0,
            "pricing_tier_note": "standard input tier up to 272K tokens; promotional pricing",
        })
        self.assertEqual(terra, {
            "input": 2.0,
            "cached_input": 0.2,
            "output": 12.0,
            "pricing_tier_note": "standard input tier up to 272K tokens",
        })
        self.assertEqual(luna, {
            "input": 0.2,
            "cached_input": 0.02,
            "output": 1.2,
            "pricing_tier_note": "standard input tier up to 272K tokens",
        })
        self.assertEqual(analysis.openai_pricing_model_key("gpt-5.6"), "gpt-5.6-sol")

        costs = analysis.token_costs_usd("gpt-5.6-terra", 0.5, 0.25, 0.5, 1.0)
        self.assertEqual(costs["cached_input_cost_usd"], 0.1)
        self.assertEqual(costs["cache_write_input_cost_usd"], 0.625)
        self.assertEqual(costs["uncached_input_cost_usd"], 1.0)
        self.assertEqual(costs["output_reasoning_cost_usd"], 12.0)
        self.assertEqual(costs["total_cost_usd"], 13.725)

    def test_records_from_summary_adds_model_aware_usd_cost_columns(self) -> None:
        summary = {
            "config": {"model": "gpt-5.5"},
            "results": [
                {
                    "paper": "01_Szabo2010.pdf",
                    "mode": "morpheus_mcp",
                    "repetition": 1,
                    "status": "completed",
                    "diagnostics": {
                        "tokens": {
                            "input": 1_000_000,
                            "cachedInput": 200_000,
                            "output": 100_000,
                            "reasoningOutput": 50_000,
                            "total": 1_100_000,
                        }
                    },
                },
                {
                    "paper": "02_Test.pdf",
                    "mode": "morpheus_mcp",
                    "model": "GPT-5.4 mini",
                    "repetition": 1,
                    "status": "completed",
                    "diagnostics": {
                        "tokens": {
                            "input": 1_000_000,
                            "cachedInput": 500_000,
                            "output": 1_000_000,
                            "reasoningOutput": 0,
                            "total": 2_000_000,
                        }
                    },
                },
            ],
        }

        df = analysis.records_from_summary(summary)
        rows = df.set_index("paper_short")

        self.assertEqual(rows.loc["Szabo2010", "agent_model"], "gpt-5.5")
        self.assertAlmostEqual(rows.loc["Szabo2010", "uncached_input_cost_usd"], 4.0)
        self.assertAlmostEqual(rows.loc["Szabo2010", "cached_input_cost_usd"], 0.1)
        self.assertAlmostEqual(rows.loc["Szabo2010", "output_reasoning_cost_usd"], 3.0)
        self.assertAlmostEqual(rows.loc["Szabo2010", "total_cost_usd"], 7.1)
        self.assertEqual(rows.loc["Test", "agent_model"], "gpt-5.4-mini")
        self.assertAlmostEqual(rows.loc["Test", "total_cost_usd"], 4.9125)

    def test_v2_records_use_direct_subject_time_without_timeout_imputation(self) -> None:
        summary = {
            "artifactSchemaVersion": 2,
            "benchmarkProtocol": "time_limit_v2",
            "config": {"model": "gpt-5.6-sol", "totalTimeLimitMs": 14_400_000},
            "results": [{
                "paper": "01_Szabo2010.pdf",
                "mode": "morpheus_mcp",
                "repetition": 1,
                "benchmarkProtocol": "time_limit_v2",
                "stopReason": "time_limit",
                "artifactStatus": "unscoreable",
                "subjectExecutionMs": 14_399_000,
                "budgetFraction": 0.99993,
                "technicalScore": None,
                "biologicalScore": None,
                "diagnostics": {
                    "agentWallTimeMs": 99_999_999,
                    "morpheusSimulationTimeMs": 3_600_000,
                    "hostMorpheusRunTimeMs": 600_000,
                    "tokens": {
                        "input": 1_000_000,
                        "cachedInput": 100_000,
                        "cacheWriteInput": 200_000,
                        "output": 10_000,
                        "reasoningOutput": 5_000,
                        "total": 1_010_000,
                    },
                },
            }],
        }

        row = analysis.records_from_summary(summary).iloc[0]

        self.assertEqual(row["protocol"], "time_limit_v2")
        self.assertEqual(row["status"], "time_limit")
        self.assertAlmostEqual(row["subject_active_time_min"], 14_399_000 / 60_000)
        self.assertEqual(row["timeout_turns"], 0)
        self.assertEqual(row["timeout_upper_bound_min"], 0)
        self.assertEqual(row["technical_score_itt"], 0)
        self.assertEqual(row["reproduction_score_itt"], 0)
        # Never biologically scored: missing, not a subject zero.
        self.assertTrue(math.isnan(row["biological_score_itt"]))
        self.assertEqual(row["total_time_limit_ms"], 14_400_000)
        self.assertTrue(math.isnan(row["legacy_v1_cycles"]))
        self.assertEqual(row["morpheus_time_min"], 60)
        self.assertEqual(row["host_morpheus_time_min"], 10)
        self.assertAlmostEqual(row["cache_write_input_cost_usd"], 0.2 * 4.0 * 1.25)

        mode = analysis.summarize_by_mode(analysis.records_from_summary(summary)).iloc[-1]
        self.assertEqual(mode["technical_itt_mean"], 0)
        self.assertTrue(math.isnan(mode["technical_valid_only_mean"]))
        self.assertEqual(mode["reproduction_itt_mean"], 0)

    def test_biological_itt_zero_fills_only_subject_attributable_outcomes(self) -> None:
        self.assertEqual(analysis.biological_itt_score(0.75, "scored"), 0.75)
        self.assertEqual(analysis.biological_itt_score(0.0, "model_failed"), 0.0)
        self.assertEqual(analysis.biological_itt_score(None, "insufficient_evidence"), 0.0)
        self.assertTrue(math.isnan(analysis.biological_itt_score(None, "scoring_failed")))
        self.assertTrue(math.isnan(analysis.biological_itt_score(None, "invalid")))
        self.assertTrue(math.isnan(analysis.biological_itt_score(None, "")))

        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            results = []
            for run_id, status in [("run_a", "insufficient_evidence"), ("run_b", "scoring_failed")]:
                run_dir = benchmark_dir / run_id
                score_path = run_dir / "biological_scores" / "score.json"
                score_path.parent.mkdir(parents=True)
                score_path.write_text(json.dumps({"status": status, "score": None}), encoding="utf8")
                results.append({
                    "paper": "01_Szabo2010.pdf",
                    "mode": "morpheus_mcp" if run_id == "run_a" else "morpheus_cli",
                    "repetition": 1,
                    "runId": run_id,
                    "runManifestPath": str(run_dir / "run_manifest.json"),
                    "benchmarkProtocol": "time_limit_v2",
                    "stopReason": "agent_finished",
                    "biologicalScore": None,
                    "biologicalScorePath": str(score_path),
                    "diagnostics": {},
                })
            df = analysis.records_from_summary({"benchmarkRunDir": str(benchmark_dir), "results": results})
            rows = df.set_index("mode")

            self.assertEqual(rows.loc["morpheus_mcp", "biological_score_itt"], 0.0)
            self.assertTrue(math.isnan(rows.loc["morpheus_cli", "biological_score_itt"]))
            modes = analysis.summarize_by_mode(df).set_index("mode")
            self.assertEqual(modes.loc["morpheus_mcp", "biological_itt_n"], 1)
            self.assertEqual(modes.loc["morpheus_cli", "biological_itt_n"], 0)

    def test_v2_time_limited_tokens_fall_back_to_subject_session_rollout(self) -> None:
        def token_count(input_tokens: int, cached: int, output: int, reasoning: int) -> str:
            usage = {
                "input_tokens": input_tokens,
                "cached_input_tokens": cached,
                "cache_write_input_tokens": 0,
                "output_tokens": output,
                "reasoning_output_tokens": reasoning,
                "total_tokens": input_tokens + output,
            }
            return json.dumps({
                "timestamp": "2026-09-22T12:00:00Z",
                "type": "event_msg",
                "payload": {"type": "token_count", "info": {"total_token_usage": usage, "last_token_usage": usage}},
            })

        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            run_dir = benchmark_dir / "run_a"
            transcript_dir = run_dir / "transcripts"
            transcript_dir.mkdir(parents=True)
            (transcript_dir / "subject.jsonl").write_text(
                json.dumps({"type": "thread.started", "thread_id": "subject-thread"}) + "\n",
                encoding="utf8",
            )
            sessions = run_dir / "codex_home" / "sessions" / "2026" / "09" / "22"
            sessions.mkdir(parents=True)
            (sessions / "rollout-2026-09-22T12-00-00-subject-thread.jsonl").write_text(
                "\n".join([token_count(1_000, 400, 100, 30), token_count(2_000_000, 1_500_000, 50_000, 20_000)]),
                encoding="utf8",
            )
            (sessions / "rollout-2026-09-22T13-00-00-scorer-thread.jsonl").write_text(
                token_count(9_000_000, 0, 9_000_000, 0),
                encoding="utf8",
            )
            summary = {
                "benchmarkRunDir": str(benchmark_dir),
                "benchmarkProtocol": "time_limit_v2",
                "config": {"model": "gpt-5.6-sol"},
                "results": [{
                    "paper": "01_Szabo2010.pdf",
                    "mode": "morpheus_mcp",
                    "repetition": 1,
                    "runId": "run_a",
                    "threadId": "subject-thread",
                    "runManifestPath": str(run_dir / "run_manifest.json"),
                    "benchmarkProtocol": "time_limit_v2",
                    "stopReason": "time_limit",
                    "subjectExecutionMs": 14_400_000,
                    "diagnostics": {"tokens": {"input": 0, "cachedInput": 0, "output": 0, "total": 0}},
                }],
            }

            row = analysis.records_from_summary(summary).iloc[0]

            self.assertAlmostEqual(row["cached_input_tokens_m"], 1.5)
            self.assertAlmostEqual(row["uncached_input_tokens_m"], 0.5)
            self.assertAlmostEqual(row["output_reasoning_tokens_m"], 0.05)
            self.assertAlmostEqual(row["total_tokens_m"], 2.05)
            self.assertAlmostEqual(row["total_cost_usd"], 1.5 * 0.4 + 0.5 * 4.0 + 0.05 * 20.0)

    def test_v2_execution_audit_retains_invalid_original_and_selected_replacement(self) -> None:
        summary = {
            "benchmarkProtocol": "time_limit_v2",
            "results": [
                {
                    "assignmentId": "paper__morpheus_mcp__rep01",
                    "selectedExecutionId": "execution_02",
                    "paper": "paper.pdf",
                    "mode": "morpheus_mcp",
                    "repetition": 1,
                    "executions": [
                        {
                            "executionId": "execution_01",
                            "runId": "invalid",
                            "replacementFor": None,
                            "replacementCount": 0,
                            "stopReason": "infrastructure_failure",
                            "artifactStatus": "unscoreable",
                            "subjectExecutionMs": 120_000,
                            "morpheusSimulationMs": 60_000,
                            "totalJobMs": 130_000,
                            "error": "stream disconnected",
                        },
                        {
                            "executionId": "execution_02",
                            "runId": "selected",
                            "replacementFor": "execution_01",
                            "replacementCount": 1,
                            "stopReason": "agent_finished",
                            "artifactStatus": "scoreable",
                            "subjectExecutionMs": 180_000,
                            "morpheusSimulationMs": 90_000,
                            "totalJobMs": 200_000,
                            "error": None,
                        },
                    ],
                }
            ]
        }

        audit = analysis.execution_records_from_summary(summary)

        self.assertEqual(audit["run_id"].tolist(), ["invalid", "selected"])
        self.assertEqual(audit["selected"].tolist(), [False, True])
        self.assertEqual(audit["stop_reason"].tolist(), ["infrastructure_failure", "agent_finished"])
        self.assertEqual(audit["subject_active_time_min"].tolist(), [2.0, 3.0])

        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            df = analysis.records_from_summary(summary)
            analysis.write_tables(
                df,
                analysis.summarize_by_mode(df),
                pd.DataFrame(),
                pd.DataFrame(),
                output_dir,
            )
            run_columns = pd.read_csv(output_dir / "benchmark_analysis_by_run.csv").columns
            mode_columns = pd.read_csv(output_dir / "benchmark_analysis_by_mode.csv").columns
            self.assertNotIn("cycles", run_columns)
            self.assertNotIn("max_turns", mode_columns)

    def test_cost_quality_records_include_median_quality_and_token_cost(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "paper": "a.pdf",
                    "mode": "morpheus_mcp",
                    "technical_score": 7,
                    "reproduction_score": 8,
                    "total_tokens_m": 1.0,
                    "duration_h": 1.0,
                    "attempts": 1,
                },
                {
                    "paper": "b.pdf",
                    "mode": "morpheus_mcp",
                    "technical_score": 3.5,
                    "reproduction_score": 4,
                    "total_tokens_m": 3.0,
                    "duration_h": 2.0,
                    "attempts": 2,
                },
                {
                    "paper": "c.pdf",
                    "mode": "morpheus_mcp",
                    "technical_score": 0,
                    "reproduction_score": 0,
                    "total_tokens_m": 100.0,
                    "duration_h": 3.0,
                    "attempts": 3,
                },
            ]
        )

        pareto = analysis.cost_quality_records(df)

        self.assertEqual(pareto.loc[0, "total_tokens_m_median"], 3.0)
        self.assertEqual(pareto.loc[0, "quality_median"], 0.5)

    def test_cost_quality_records_include_biological_score_when_present(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "paper": "a.pdf",
                    "mode": "morpheus_mcp",
                    "technical_score": 7,
                    "reproduction_score": 8,
                    "biological_score": 0.5,
                    "total_tokens_m": 1.0,
                    "duration_h": 1.0,
                    "attempts": 1,
                },
                {
                    "paper": "b.pdf",
                    "mode": "morpheus_mcp",
                    "technical_score": 7,
                    "reproduction_score": 8,
                    "biological_score": None,
                    "total_tokens_m": 1.0,
                    "duration_h": 1.0,
                    "attempts": 1,
                },
            ]
        )

        pareto = analysis.cost_quality_records(df)

        # Row a has a biological score (0.5) so quality uses it directly; row b has no
        # biological score, so quality falls back to its normalized reproduction score (1.0).
        self.assertAlmostEqual(pareto.loc[0, "quality_mean"], 0.75)

    def test_cost_quality_raw_records_include_run_level_quality_and_token_cost(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "paper": "a.pdf",
                    "paper_short": "a",
                    "mode": "morpheus_mcp",
                    "technical_score": 7,
                    "reproduction_score": 8,
                    "total_tokens_m": 1.0,
                },
                {
                    "paper": "b.pdf",
                    "paper_short": "b",
                    "mode": "morpheus_mcp",
                    "technical_score": None,
                    "reproduction_score": None,
                    "total_tokens_m": 2.0,
                },
            ]
        )

        raw = analysis.cost_quality_raw_records(df)

        self.assertEqual(len(raw), 1)
        self.assertEqual(raw.loc[0, "paper_short"], "a")
        self.assertEqual(raw.loc[0, "mode"], "morpheus_mcp")
        self.assertEqual(raw.loc[0, "total_tokens_m"], 1.0)
        self.assertEqual(raw.loc[0, "quality_score"], 1.0)

    def test_dollar_cost_quality_records_use_total_usd_cost(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "paper": "a.pdf",
                    "paper_short": "a",
                    "mode": "morpheus_mcp",
                    "technical_score": 7,
                    "reproduction_score": 8,
                    "total_tokens_m": 1.0,
                    "total_cost_usd": 3.0,
                    "duration_h": 1.0,
                    "attempts": 1,
                },
                {
                    "paper": "b.pdf",
                    "paper_short": "b",
                    "mode": "morpheus_mcp",
                    "technical_score": 3.5,
                    "reproduction_score": 4,
                    "total_tokens_m": 2.0,
                    "total_cost_usd": 9.0,
                    "duration_h": 2.0,
                    "attempts": 2,
                },
            ]
        )

        pareto = analysis.dollar_cost_quality_records(df)
        raw = analysis.dollar_cost_quality_raw_records(df)

        self.assertEqual(pareto.loc[0, "total_cost_usd_mean"], 6.0)
        self.assertEqual(pareto.loc[0, "total_cost_usd_median"], 6.0)
        self.assertEqual(raw["total_cost_usd"].tolist(), [3.0, 9.0])

    def test_single_score_cost_helpers_cover_missing_and_biological_wrappers(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "paper": "a.pdf",
                    "paper_short": "a",
                    "mode": "morpheus_mcp",
                    "biological_score": 0.75,
                    "total_tokens_m": 2.0,
                    "duration_h": 1.0,
                    "attempts": 1,
                }
            ]
        )

        self.assertTrue(analysis.cost_single_score_records(df, "missing").empty)
        self.assertTrue(analysis.cost_single_score_raw_records(df, "missing").empty)
        self.assertEqual(analysis.cost_biological_records(df).loc[0, "quality_mean"], 0.75)
        self.assertEqual(analysis.cost_biological_raw_records(df).loc[0, "quality_score"], 0.75)
        self.assertTrue(analysis.has_biological_scores(df))

        without_summary_mean = analysis.available_biological_score_specs(
            pd.DataFrame([{"manual_biological_score": 0.5}]),
            pd.DataFrame([{"mode": "morpheus_mcp"}]),
        )
        self.assertEqual(without_summary_mean, [])

    def test_records_from_summary_uses_attempt_wall_time_logs_when_diagnostics_are_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            run_dir = benchmark_dir / "run_a"
            agent_attempt = run_dir / "agent_workspace" / "agent_runs" / "cli_attempts" / "attempt_001"
            host_attempt = run_dir / "attempts" / "attempt_001"
            agent_attempt.mkdir(parents=True)
            host_attempt.mkdir(parents=True)
            (agent_attempt / "stdout_stderr.txt").write_text(
                "=== Simulation finished ===\nWall Time   = 1s 250ms\nCPU Time = 1s\n",
                encoding="utf8",
            )
            (host_attempt / "stdout.log").write_text(
                "=== Simulation finished ===\nWall Time   = 750ms\n",
                encoding="utf8",
            )
            summary = {
                "benchmarkRunDir": str(benchmark_dir),
                "results": [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_cli",
                        "status": "completed",
                        "technicalScore": 7,
                        "reproductionScore": 8,
                        "runId": "run_a",
                        "runManifestPath": str(run_dir / "run_manifest.json"),
                        "diagnostics": {
                            "tokens": {"total": 0},
                            "morpheusSimulationTimeMs": 0,
                            "hostMorpheusRunTimeMs": 0,
                        },
                    }
                ],
            }

            df = analysis.records_from_summary(summary, benchmark_dir)

            self.assertAlmostEqual(df.loc[0, "morpheus_time_min"], 2_000 / 60_000)

    def test_records_from_summary_uses_only_subject_mcp_runs_for_mcp_execution_time(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            run_dir = benchmark_dir / "run_a"
            agent_attempt = run_dir / "agent_workspace" / "attempts" / "attempt_001"
            host_attempt = run_dir / "attempts" / "attempt_001"
            agent_attempt.mkdir(parents=True)
            host_attempt.mkdir(parents=True)
            (agent_attempt / "stdout.log").write_text(
                "=== Simulation finished ===\nWall Time   = 1s 250ms\n",
                encoding="utf8",
            )
            (host_attempt / "stdout.log").write_text(
                "=== Simulation finished ===\nWall Time   = 50s\n",
                encoding="utf8",
            )
            summary = {
                "benchmarkRunDir": str(benchmark_dir),
                "results": [
                    {
                        "paper": "01_Szabo2010.pdf",
                        "mode": "morpheus_mcp",
                        "status": "completed",
                        "technicalScore": 7,
                        "reproductionScore": 8,
                        "runId": "run_a",
                        "runManifestPath": str(run_dir / "run_manifest.json"),
                        "diagnostics": {
                            "tokens": {"total": 0},
                            "morpheusSimulationTimeMs": 1_250,
                            "hostMorpheusRunTimeMs": 50_000,
                        },
                    }
                ],
            }

            df = analysis.records_from_summary(summary, benchmark_dir)

            self.assertAlmostEqual(df.loc[0, "morpheus_time_min"], 1_250 / 60_000)

    def test_attempt_wall_time_uses_one_log_per_attempt_to_avoid_double_counting(self) -> None:
        with TemporaryDirectory() as tmp:
            attempt_dir = Path(tmp) / "attempt_001"
            attempt_dir.mkdir()
            wall_time = "=== Simulation finished ===\nWall Time   = 3s 500ms\n"
            (attempt_dir / "stdout.log").write_text(wall_time, encoding="utf8")
            (attempt_dir / "morpheus_console.txt").write_text(wall_time, encoding="utf8")

            self.assertEqual(analysis.morpheus_wall_time_ms_from_attempt_dir(attempt_dir), 3_500)

    def test_attempt_wall_time_parses_nul_separated_logs(self) -> None:
        text = "\x00W\x00a\x00l\x00l\x00 \x00T\x00i\x00m\x00e\x00 \x00=\x00 \x003\x002\x00s\x00 \x005\x005\x007\x00m\x00s\x00"

        self.assertEqual(analysis.morpheus_wall_time_ms_from_text(text), 32_557)

    def test_cost_quality_pareto_draws_median_markers_for_each_mode(self) -> None:
        pareto = pd.DataFrame(
            [
                {
                    "mode": "morpheus_cli",
                    "total_tokens_m_mean": 8.0,
                    "quality_mean": 0.8,
                    "total_tokens_m_median": 6.0,
                    "quality_median": 0.7,
                },
                {
                    "mode": "morpheus_mcp",
                    "total_tokens_m_mean": 10.0,
                    "quality_mean": 1.0,
                    "total_tokens_m_median": 12.0,
                    "quality_median": 0.9,
                },
            ]
        )
        fig, ax = plt.subplots()
        try:
            analysis.cost_quality_pareto_scatter(ax, pareto)

            scatter_offsets = [collection.get_offsets().tolist() for collection in ax.collections]

            self.assertIn([[8.0, 0.8]], scatter_offsets)
            self.assertIn([[10.0, 1.0]], scatter_offsets)
            self.assertIn([[6.0, 0.7]], scatter_offsets)
            self.assertIn([[12.0, 0.9]], scatter_offsets)
        finally:
            plt.close(fig)

    def test_cost_quality_pareto_draws_raw_points_without_dashed_front_line(self) -> None:
        pareto = pd.DataFrame(
            [
                {
                    "mode": "morpheus_cli",
                    "total_tokens_m_mean": 8.0,
                    "quality_mean": 0.8,
                    "total_tokens_m_median": 6.0,
                    "quality_median": 0.7,
                },
                {
                    "mode": "morpheus_mcp",
                    "total_tokens_m_mean": 10.0,
                    "quality_mean": 1.0,
                    "total_tokens_m_median": 12.0,
                    "quality_median": 0.9,
                },
            ]
        )
        raw = pd.DataFrame(
            [
                {"mode": "morpheus_cli", "total_tokens_m": 7.5, "quality_score": 0.6},
                {"mode": "morpheus_mcp", "total_tokens_m": 11.5, "quality_score": 0.95},
            ]
        )
        fig, ax = plt.subplots()
        try:
            analysis.cost_quality_pareto_scatter(ax, pareto, raw)

            scatter_offsets = [collection.get_offsets().tolist() for collection in ax.collections]
            dashed_lines = [line for line in ax.lines if line.get_linestyle() == "--"]

            self.assertIn([[7.5, 0.6]], scatter_offsets)
            self.assertIn([[11.5, 0.95]], scatter_offsets)
            self.assertEqual(dashed_lines, [])
        finally:
            plt.close(fig)

    def test_pareto_and_plot_helpers_cover_empty_and_panel_labels(self) -> None:
        pareto = pd.DataFrame(
            [
                {"mode": "a", "total_tokens_m_mean": 2, "quality_mean": 0.5},
                {"mode": "b", "total_tokens_m_mean": 1, "quality_mean": 0.4},
                {"mode": "c", "total_tokens_m_mean": 3, "quality_mean": 0.6},
            ]
        )
        front = analysis.pareto_front_rows(pareto)
        self.assertEqual(front["mode"].tolist(), ["b", "a", "c"])

        fig, ax = plt.subplots()
        try:
            analysis.cost_quality_pareto_scatter(ax, pd.DataFrame())
            self.assertFalse(ax.axison)
        finally:
            plt.close(fig)

        fig, ax = plt.subplots()
        try:
            analysis.add_panel_label(ax, "z")
            self.assertEqual(ax.texts[0].get_text(), "z")
        finally:
            plt.close(fig)

    def test_grouped_score_boxplots_normalize_scores_and_draw_means(self) -> None:
        df = pd.DataFrame(
            [
                {"mode": "python_web", "technical_score": 0, "reproduction_score": 4},
                {"mode": "python_web", "technical_score": 7, "reproduction_score": 8},
            ]
        )
        fig, ax = plt.subplots()
        try:
            analysis.grouped_score_boxplots(ax, df)

            self.assertEqual(len(ax.patches), 2)
            self.assertEqual(
                sorted(line.get_ydata()[0] for line in ax.lines if line.get_marker() == "D"),
                [0.5, 0.75],
            )
            self.assertEqual(ax.get_ylim()[1], 1.08)
            self.assertEqual(ax.get_ylabel(), "Normalized score")
        finally:
            plt.close(fig)

    def test_grouped_score_boxplots_label_agent_and_manual_biological_scores(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "mode": "python_web",
                    "technical_score": 0,
                    "reproduction_score": 0,
                    "biological_score": 0.75,
                    "manual_biological_score": 0.6,
                },
            ]
        )
        fig, ax = plt.subplots()
        try:
            analysis.grouped_score_boxplots(ax, df)

            labels = [text.get_text() for text in ax.get_legend().get_texts()]
            agent_color = ax.patches[2].get_facecolor()
            manual_color = ax.patches[3].get_facecolor()

            self.assertEqual(
                labels,
                ["Technical", "Reproduction (self-reported)", "Biological (scoring agent)", "Biological (manual)"],
            )
            self.assertNotEqual(agent_color, manual_color)
        finally:
            plt.close(fig)

    def test_score_box_grid_groups_all_available_score_categories_by_cohort(self) -> None:
        rows = []
        for mode_index, mode in enumerate(analysis.MODE_ORDER):
            rows.append(
                {
                    "paper": f"0{mode_index + 1}_Modeling.pdf",
                    "paper_number": mode_index + 1,
                    "mode": mode,
                    "status": "completed",
                    "technical_score": 2 + mode_index,
                    "reproduction_score": 8,
                    "biological_score": 0.2 + mode_index * 0.1,
                    "manual_biological_score": 0.3 + mode_index * 0.1,
                }
            )
            rows.append(
                {
                    "paper": f"1{mode_index + 1}_Biology.pdf",
                    "paper_number": 11 + mode_index,
                    "mode": mode,
                    "status": "completed",
                    "technical_score": 3 + mode_index,
                    "reproduction_score": 0,
                    "biological_score": 0.25 + mode_index * 0.1,
                    "manual_biological_score": 0.35 + mode_index * 0.1,
                }
            )
        df = pd.DataFrame(rows)
        captured = {}

        def capture_figure(fig, output_dir, stem, formats):
            captured["fig"] = fig
            captured["stem"] = stem
            captured["formats"] = list(formats)

        with TemporaryDirectory() as tmp, mock.patch.object(analysis, "save_figure", capture_figure):
            analysis.make_score_box_grid_figure(df, Path(tmp), ["png"])

            fig = captured["fig"]
            try:
                axes = fig.axes
                visible_text = " ".join(
                    [ax.get_title() for ax in axes]
                    + [ax.get_ylabel() for ax in axes]
                    + [text.get_text() for ax in axes for text in ax.texts]
                )

                self.assertEqual(captured["stem"], "score_distributions_by_mode")
                self.assertEqual(captured["formats"], ["png"])
                self.assertEqual(len(axes), 12)
                self.assertIn("All papers", axes[0].get_title())
                self.assertIn("Papers 1-10", axes[1].get_title())
                self.assertIn("Papers 11-15", axes[2].get_title())
                self.assertEqual(axes[0].get_ylabel(), "Technical score / 7")
                self.assertEqual(axes[3].get_ylabel(), "Reproduction score (self-reported) / 8")
                self.assertEqual(axes[6].get_ylabel(), "Biological score")
                self.assertEqual(axes[9].get_ylabel(), "Manual biological score")
                self.assertIn("Reproduction", visible_text)
                self.assertTrue(all(len(ax.patches) == len(analysis.MODE_ORDER) for ax in axes))
                self.assertTrue(
                    all(
                        sum(1 for line in ax.lines if line.get_marker() == "D") == len(analysis.MODE_ORDER)
                        for ax in axes
                    )
                )
            finally:
                plt.close(fig)

    def test_score_box_grid_omits_empty_biology_rows(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "paper": "01_Modeling.pdf",
                    "paper_number": 1,
                    "mode": mode,
                    "technical_score": 7,
                    "reproduction_score": 8,
                    "biological_score": None,
                    "manual_biological_score": None,
                }
                for mode in analysis.MODE_ORDER
            ]
        )
        captured = {}

        def capture_figure(fig, output_dir, stem, formats):
            captured["fig"] = fig

        with TemporaryDirectory() as tmp, mock.patch.object(analysis, "save_figure", capture_figure):
            analysis.make_score_box_grid_figure(df, Path(tmp), ["png"])

            fig = captured["fig"]
            try:
                self.assertEqual(len(fig.axes), 6)
                self.assertEqual(fig.axes[0].get_ylabel(), "Technical score / 7")
                self.assertEqual(fig.axes[3].get_ylabel(), "Reproduction score (self-reported) / 8")
            finally:
                plt.close(fig)

    def test_time_stacked_bars_separates_timeout_upper_bound_from_completed_time(self) -> None:
        summary = pd.DataFrame(
            {
                "mode": analysis.MODE_ORDER,
                "duration_h_mean": [1.0, 2.0, 0.5, 0.0, float("nan")],
                "morpheus_time_min_mean": [15.0, 30.0, 45.0, 0.0, 6.0],
                "timeout_upper_bound_min_mean": [15.0, 60.0, 0.0, 0.0, 30.0],
            }
        )
        fig, ax = plt.subplots()
        try:
            analysis.time_stacked_bars(ax, summary)

            heights = [patch.get_height() for patch in ax.patches]
            mode_count = len(analysis.MODE_ORDER)
            self.assertEqual(heights[:mode_count], [0.25, 0.5, 0.5, 0.0, 0.0])
            self.assertEqual(heights[mode_count : 2 * mode_count], [0.5, 0.5, 0.0, 0.0, 0.0])
            self.assertEqual(heights[2 * mode_count :], [0.25, 1.0, 0.0, 0.0, 0.0])
            self.assertEqual(ax.get_ylabel(), "Upper-bound time per run (h)")
            self.assertEqual(
                [text.get_text() for text in ax.get_legend().get_texts()],
                ["Morpheus running", "Agent only", "Timeout duration (upper bound)"],
            )
        finally:
            plt.close(fig)

    def test_time_stacked_bars_splits_wall_time_by_union_of_parallel_simulations(self) -> None:
        summary = pd.DataFrame(
            {
                "mode": analysis.MODE_ORDER,
                "duration_h_mean": [1.0, 2.0, 2.0, 1.0, 1.0],
                "morpheus_time_min_mean": [0.0, 300.0, 30.0, 30.0, 30.0],
                "morpheus_active_min_mean": [float("nan"), 90.0, 30.0, 30.0, 30.0],
                "morpheus_process_min_mean": [float("nan"), 300.0, 30.0, 30.0, 30.0],
                "timeout_upper_bound_min_mean": [0.0] * 5,
            }
        )
        fig, ax = plt.subplots()
        try:
            analysis.time_stacked_bars(ax, summary)

            heights = [patch.get_height() for patch in ax.patches]
            mode_count = len(analysis.MODE_ORDER)
            self.assertEqual(len(heights), 2 * mode_count)
            self.assertEqual(heights[1], 1.5)
            self.assertEqual(heights[mode_count + 1], 0.5)
            self.assertEqual(ax.get_ylabel(), "Wall time per run (h)")
            self.assertEqual(
                [text.get_text() for text in ax.get_legend().get_texts()],
                ["Morpheus running", "Agent only"],
            )
            self.assertIn("\u00d73.3", [text.get_text() for text in ax.texts])
        finally:
            plt.close(fig)

    def test_morpheus_activity_merges_overlapping_simulation_intervals(self) -> None:
        activity = analysis.morpheus_activity_from_intervals([(0.0, 60.0), (30.0, 90.0), (120.0, 180.0)])
        self.assertEqual(activity["active_ms"], 150_000.0)
        self.assertEqual(activity["process_ms"], 180_000.0)
        self.assertEqual(activity["peak_concurrency"], 2.0)

    def test_morpheus_intervals_read_launcher_manifests(self) -> None:
        with TemporaryDirectory() as temp:
            run_dir = Path(temp)
            for name, started, finished, duration in [
                ("attempt_001", "2026-10-07T23:30:00+00:00", "2026-10-07T23:40:00+00:00", None),
                ("attempt_002", "2026-10-07T23:35:00+00:00", None, 600_000),
                ("attempt_003", "2026-10-07T23:50:00+00:00", None, None),
            ]:
                attempt_dir = run_dir / "agent_workspace" / "attempts" / name
                attempt_dir.mkdir(parents=True)
                (attempt_dir / "morpheus_command.json").write_text(
                    json.dumps({"startedAt": started, "finishedAt": finished, "durationMs": duration}),
                    encoding="utf8",
                )
            nested_dir = run_dir / "agent_workspace" / "attempts" / "attempt_004" / "out"
            nested_dir.mkdir(parents=True)
            (nested_dir / "morpheus_command.json").write_text(
                json.dumps({"startedAt": "2026-10-08T00:00:00+00:00", "finishedAt": "2026-10-08T00:05:00+00:00"}),
                encoding="utf8",
            )
            reproduction_dir = run_dir / "attempts" / "attempt_001"
            reproduction_dir.mkdir(parents=True)
            (reproduction_dir / "morpheus_command.json").write_text(
                json.dumps({"startedAt": "2026-10-08T01:00:00+00:00", "finishedAt": "2026-10-08T02:00:00+00:00"}),
                encoding="utf8",
            )
            intervals = analysis.morpheus_intervals_from_run_dir(run_dir, "morpheus_cli")
            activity = analysis.morpheus_activity_from_intervals(intervals)
            self.assertEqual(len(intervals), 3)
            self.assertEqual(activity["active_ms"], 20 * 60_000.0)
            self.assertEqual(activity["process_ms"], 25 * 60_000.0)

    def test_cohort_bar_figures_write_three_panel_bar_chart_outputs(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "paper": "01_Szabo2010.pdf",
                    "paper_number": 1,
                    "mode": "morpheus_mcp",
                    "status": "completed",
                    "technical_score": 7,
                    "reproduction_score": 8,
                    "biological_score": 1.0,
                    "duration_h": 1.0,
                    "morpheus_time_min": 2.0,
                    "agent_analysis_min": 3.0,
                    "cached_input_tokens_m": 0.1,
                    "uncached_input_tokens_m": 0.2,
                    "output_reasoning_tokens_m": 0.3,
                    "total_tokens_m": 0.6,
                    "cached_input_cost_usd": 0.05,
                    "uncached_input_cost_usd": 1.0,
                    "output_reasoning_cost_usd": 9.0,
                    "total_cost_usd": 10.05,
                    "cycles": 1,
                    "attempts": 2,
                },
                {
                    "paper": "11_Anlas2024.pdf",
                    "paper_number": 11,
                    "mode": "morpheus_mcp",
                    "status": "failed",
                    "technical_score": 0,
                    "reproduction_score": 0,
                    "biological_score": 0.0,
                    "duration_h": 5.0,
                    "morpheus_time_min": 6.0,
                    "agent_analysis_min": 7.0,
                    "cached_input_tokens_m": 0.4,
                    "uncached_input_tokens_m": 0.5,
                    "output_reasoning_tokens_m": 0.6,
                    "total_tokens_m": 1.5,
                    "cached_input_cost_usd": 0.2,
                    "uncached_input_cost_usd": 2.5,
                    "output_reasoning_cost_usd": 18.0,
                    "total_cost_usd": 20.7,
                    "cycles": 3,
                    "attempts": 4,
                },
            ]
        )

        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)

            analysis.make_cohort_bar_figures(df, output_dir, ["png"])

            self.assertTrue((output_dir / "score_distributions_by_mode.png").exists())
            self.assertTrue((output_dir / "runtime_breakdown_by_mode.png").exists())
            self.assertFalse((output_dir / "benchmark_wall_time_by_mode.png").exists())
            self.assertFalse((output_dir / "benchmark_morpheus_time_by_mode.png").exists())
            self.assertTrue((output_dir / "token_usage_by_mode.png").exists())
            self.assertTrue((output_dir / "api_cost_by_mode.png").exists())
            self.assertTrue((output_dir / "run_outcomes_by_mode.png").exists())

    def test_aggregate_attempt_self_score_lineplot_writes_mode_level_figure(self) -> None:
        attempts = pd.DataFrame(
            [
                {"paper_short": "Szabo2010", "mode": "morpheus_cli", "attempt_number": 1, "normalized_self_score": 0.25},
                {"paper_short": "Thapa2024", "mode": "morpheus_cli", "attempt_number": 1, "normalized_self_score": 0.75},
                {"paper_short": "Szabo2010", "mode": "morpheus_mcp", "attempt_number": 1, "normalized_self_score": 0.50},
                {"paper_short": "Thapa2024", "mode": "morpheus_mcp", "attempt_number": 2, "normalized_self_score": 1.00},
            ]
        )
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)

            analysis.aggregate_attempt_self_score_lineplot(attempts, output_dir, ["png"])

            self.assertTrue((output_dir / "attempt_self_scores_by_mode.png").exists())

    def test_aggregate_attempt_self_score_lineplot_draws_individual_runs(self) -> None:
        attempts = pd.DataFrame(
            [
                {"paper_short": "Szabo2010", "mode": "morpheus_cli", "run_id": "run_a", "attempt_number": 1, "self_score": 2},
                {"paper_short": "Szabo2010", "mode": "morpheus_cli", "run_id": "run_a", "attempt_number": 2, "self_score": 6},
                {"paper_short": "Thapa2024", "mode": "morpheus_cli", "run_id": "run_b", "attempt_number": 1, "self_score": 3},
                {"paper_short": "Thapa2024", "mode": "morpheus_cli", "run_id": "run_b", "attempt_number": 2, "self_score": 7},
                {"paper_short": "Szabo2010", "mode": "morpheus_mcp", "run_id": "run_c", "attempt_number": 1, "self_score": 8},
                {"paper_short": "Szabo2010", "mode": "morpheus_mcp", "run_id": "run_c", "attempt_number": 2, "self_score": 8},
            ]
        )
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            original_save_figure = analysis.save_figure
            captured_axes = []

            def capture_save_figure(fig, output_dir, stem, formats):
                captured_axes.extend(fig.axes)

            try:
                analysis.save_figure = capture_save_figure
                analysis.aggregate_attempt_self_score_lineplot(attempts, output_dir, ["png"])
            finally:
                analysis.save_figure = original_save_figure

            ax = captured_axes[0]
            line_scores = sorted(tuple(line.get_ydata().tolist()) for line in ax.lines)
            self.assertEqual(line_scores, [(2.0, 6.0), (3.0, 7.0), (8.0, 8.0)])
            self.assertTrue(all(line.get_alpha() < 1 for line in ax.lines))
            self.assertEqual(len(ax.collections), 0)

    def test_attempt_self_score_lineplots_write_paper_level_figure_and_skip_empty_inputs(self) -> None:
        attempts = pd.DataFrame(
            [
                {"paper_short": "Szabo2010", "mode": "morpheus_cli", "attempt_number": 1, "self_score": 2},
                {"paper_short": "Szabo2010", "mode": "morpheus_cli", "attempt_number": 1, "self_score": 6},
                {"paper_short": "Szabo2010", "mode": "morpheus_mcp", "attempt_number": 2, "self_score": 8},
                {"paper_short": "Thapa2024", "mode": "morpheus_mcp", "attempt_number": 1, "self_score": 4},
                {"paper_short": "Anlas2024", "mode": "morpheus_mcp", "attempt_number": 1, "self_score": 5},
            ]
        )
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)

            analysis.attempt_self_score_lineplots(pd.DataFrame(), output_dir, ["png"])
            analysis.aggregate_attempt_self_score_lineplot(pd.DataFrame(), output_dir, ["png"])
            analysis.aggregate_attempt_self_score_lineplot(
                pd.DataFrame([{"mode": "morpheus_mcp", "attempt_number": float("nan"), "self_score": float("nan")}]),
                output_dir,
                ["png"],
            )
            self.assertFalse((output_dir / "attempt_self_scores_by_paper.png").exists())
            self.assertFalse((output_dir / "attempt_self_scores_by_mode.png").exists())
            analysis.attempt_self_score_lineplots(attempts, output_dir, ["png"])

            self.assertTrue((output_dir / "attempt_self_scores_by_paper.png").exists())

    def test_attempt_self_score_lineplots_draw_each_run_per_paper_without_bands(self) -> None:
        attempts = pd.DataFrame(
            [
                {"paper_short": "Szabo2010", "mode": "morpheus_cli", "run_id": "run_a", "attempt_number": 1, "self_score": 1},
                {"paper_short": "Szabo2010", "mode": "morpheus_cli", "run_id": "run_a", "attempt_number": 2, "self_score": 5},
                {"paper_short": "Szabo2010", "mode": "morpheus_cli", "run_id": "run_b", "attempt_number": 1, "self_score": 2},
                {"paper_short": "Szabo2010", "mode": "morpheus_cli", "run_id": "run_b", "attempt_number": 2, "self_score": 6},
                {"paper_short": "Thapa2024", "mode": "morpheus_cli", "run_id": "run_c", "attempt_number": 1, "self_score": 7},
                {"paper_short": "Thapa2024", "mode": "morpheus_cli", "run_id": "run_c", "attempt_number": 2, "self_score": 8},
            ]
        )
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            original_save_figure = analysis.save_figure
            captured_axes = []

            def capture_save_figure(fig, output_dir, stem, formats):
                captured_axes.extend(fig.axes)

            try:
                analysis.save_figure = capture_save_figure
                analysis.attempt_self_score_lineplots(attempts, output_dir, ["png"])
            finally:
                analysis.save_figure = original_save_figure

            axes_by_title = {ax.get_title(): ax for ax in captured_axes if ax.get_title()}
            szabo_scores = sorted(tuple(line.get_ydata().tolist()) for line in axes_by_title["Szabo2010"].lines)
            thapa_scores = [tuple(line.get_ydata().tolist()) for line in axes_by_title["Thapa2024"].lines]
            self.assertEqual(szabo_scores, [(1.0, 5.0), (2.0, 6.0)])
            self.assertEqual(thapa_scores, [(7.0, 8.0)])
            self.assertEqual(len(axes_by_title["Szabo2010"].collections), 0)

    def test_aggregate_attempt_self_score_lineplot_uses_raw_self_score_scale(self) -> None:
        attempts = pd.DataFrame(
            [
                {
                    "paper_short": "Szabo2010",
                    "mode": "morpheus_cli",
                    "attempt_number": 1,
                    "self_score": 2,
                    "normalized_self_score": 0.25,
                },
                {
                    "paper_short": "Thapa2024",
                    "mode": "morpheus_cli",
                    "attempt_number": 1,
                    "self_score": 6,
                    "normalized_self_score": 0.75,
                },
            ]
        )
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            original_save_figure = analysis.save_figure
            captured_axes = []

            def capture_save_figure(fig, output_dir, stem, formats):
                captured_axes.extend(fig.axes)

            try:
                analysis.save_figure = capture_save_figure
                analysis.aggregate_attempt_self_score_lineplot(attempts, output_dir, ["png"])
            finally:
                analysis.save_figure = original_save_figure

            ax = captured_axes[0]
            self.assertEqual([line.get_ydata().tolist() for line in ax.lines], [[2.0], [6.0]])
            self.assertEqual(ax.get_ylabel(), "Self-reported score / 8")
            self.assertGreaterEqual(ax.get_ylim()[1], 8)

    def test_make_companion_figures_writes_biological_cost_pareto_when_scores_exist(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "paper": "01_Szabo2010.pdf",
                    "paper_short": "Szabo2010",
                    "paper_number": 1,
                    "mode": "morpheus_mcp",
                    "status": "completed",
                    "technical_score": 7,
                    "reproduction_score": 8,
                    "biological_score": 0.75,
                    "duration_h": 1.0,
                    "morpheus_time_min": 2.0,
                    "agent_analysis_min": 3.0,
                    "cached_input_tokens_m": 0.1,
                    "uncached_input_tokens_m": 0.2,
                    "output_reasoning_tokens_m": 0.3,
                    "total_tokens_m": 0.6,
                    "cycles": 1,
                    "attempts": 2,
                },
            ]
        )
        summary = analysis.summarize_by_mode(df)
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)

            analysis.make_companion_figures(df, summary, output_dir, ["png"])

            self.assertTrue((output_dir / "token_biological_score_pareto.png").exists())

    def test_make_full_figure_and_write_tables_create_expected_outputs(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "paper": "01_Szabo2010.pdf",
                    "paper_short": "Szabo2010",
                    "paper_number": 1,
                    "paper_cohort": "papers_01_10",
                    "paper_cohort_label": "Papers 1-10 (modeling keywords)",
                    "mode": "morpheus_mcp",
                    "mode_rank": 4,
                    "status": "completed",
                    "technical_score": 7,
                    "reproduction_score": 8,
                    "duration_h": 1.0,
                    "morpheus_time_min": 2.0,
                    "agent_analysis_min": 3.0,
                    "cached_input_tokens_m": 0.1,
                    "uncached_input_tokens_m": 0.2,
                    "output_reasoning_tokens_m": 0.3,
                    "total_tokens_m": 0.6,
                    "cycles": 1,
                    "attempts": 2,
                },
            ]
        )
        summary = analysis.summarize_by_mode(df)
        attempts = pd.DataFrame([{"attempt_number": 1, "self_score": 4}])
        clauses = pd.DataFrame([{"clause_id": "a", "score": 1.0}])
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)

            analysis.make_full_figure(df, summary, output_dir, ["png"])
            analysis.write_tables(df, summary, attempts, clauses, output_dir)

            self.assertTrue((output_dir / "mode_comparison_overview.png").exists())
            self.assertTrue((output_dir / "benchmark_analysis_by_run.csv").exists())
            self.assertTrue((output_dir / "benchmark_analysis_by_mode.csv").exists())
            self.assertTrue((output_dir / "benchmark_cost_quality_by_mode.csv").exists())
            self.assertTrue((output_dir / "benchmark_attempt_self_scores.csv").exists())
            self.assertTrue((output_dir / "benchmark_biological_scores.csv").exists())

    def test_make_full_figure_writes_biological_panels_when_scores_exist(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "paper": "01_Szabo2010.pdf",
                    "paper_short": "Szabo2010",
                    "mode": "morpheus_mcp",
                    "status": "completed",
                    "technical_score": 7,
                    "reproduction_score": 8,
                    "biological_score": 1.0,
                    "manual_biological_score": 0.75,
                    "duration_h": 1.0,
                    "morpheus_time_min": 2.0,
                    "agent_analysis_min": 3.0,
                    "cached_input_tokens_m": 0.1,
                    "uncached_input_tokens_m": 0.2,
                    "output_reasoning_tokens_m": 0.3,
                    "total_tokens_m": 0.6,
                    "cycles": 1,
                    "attempts": 2,
                },
            ]
        )
        summary = analysis.summarize_by_mode(df)
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)

            analysis.make_full_figure(df, summary, output_dir, ["png"])

            self.assertTrue((output_dir / "mode_comparison_overview.png").exists())

    def test_make_full_figure_hides_unused_biological_panel_for_single_score_source(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "paper": "01_Szabo2010.pdf",
                    "paper_short": "Szabo2010",
                    "mode": "morpheus_mcp",
                    "status": "completed",
                    "technical_score": 7,
                    "reproduction_score": 8,
                    "biological_score": 1.0,
                    "duration_h": 1.0,
                    "morpheus_time_min": 2.0,
                    "agent_analysis_min": 3.0,
                    "cached_input_tokens_m": 0.1,
                    "uncached_input_tokens_m": 0.2,
                    "output_reasoning_tokens_m": 0.3,
                    "total_tokens_m": 0.6,
                    "cycles": 1,
                    "attempts": 2,
                },
            ]
        )
        summary = analysis.summarize_by_mode(df)
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)

            analysis.make_full_figure(df, summary, output_dir, ["png"])

            self.assertTrue((output_dir / "mode_comparison_overview.png").exists())

    def test_main_runs_analysis_pipeline_with_figure_generation_patched_out(self) -> None:
        with TemporaryDirectory() as tmp:
            benchmark_dir = Path(tmp)
            run_dir = benchmark_dir / "run_a" / "agent_workspace" / "attempts" / "attempt_001"
            run_dir.mkdir(parents=True)
            (run_dir / "attempt_reproduction.json").write_text(
                json.dumps(
                    {
                        "attempt": 1,
                        "source_coverage": 1,
                        "mechanism_mapping": 1,
                        "observable_alignment": 1,
                        "parameter_plausibility": 1,
                    }
                ),
                encoding="utf8",
            )
            (benchmark_dir / "manual_biological_scores.csv").write_text(
                "\n".join(
                    [
                        "canonical_paper_stem,mode,repetition,manual_score",
                        "01_Szabo2010,morpheus_mcp,1,0.5",
                    ]
                ),
                encoding="utf8",
            )
            (benchmark_dir / "benchmark_summary.json").write_text(
                json.dumps(
                    {
                        "benchmarkRunDir": str(benchmark_dir),
                        "results": [
                            {
                                "paper": "01_Szabo2010.pdf",
                                "mode": "morpheus_mcp",
                                "runId": "run_a",
                                "runManifestPath": str(benchmark_dir / "run_a" / "run_manifest.json"),
                                "repetition": 1,
                                "status": "completed",
                                "technicalScore": 7,
                                "reproductionScore": 8,
                                "biologicalScore": 1.0,
                                "diagnostics": {"tokens": {"total": 1_000_000}},
                            }
                        ],
                    }
                ),
                encoding="utf8",
            )

            with (
                mock.patch.object(sys, "argv", ["analyze_benchmark.py", str(benchmark_dir), "--formats", "png"]),
                mock.patch.object(analysis, "make_full_figure") as full,
                mock.patch.object(analysis, "make_companion_figures") as companion,
                mock.patch.object(analysis, "attempt_self_score_lineplots") as by_paper,
                mock.patch.object(analysis, "aggregate_attempt_self_score_lineplot") as by_mode,
                mock.patch("builtins.print") as printer,
            ):
                analysis.main()

            output_dir = benchmark_dir / "analysis_figures"
            self.assertTrue((output_dir / "benchmark_analysis_by_run.csv").exists())
            full.assert_called_once()
            companion.assert_called_once()
            by_paper.assert_called_once()
            by_mode.assert_called_once()
            self.assertIn("Wrote analysis for 1 runs", printer.call_args_list[0].args[0])


if __name__ == "__main__":
    unittest.main()
