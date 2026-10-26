import hashlib
import json
import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

import biological_score_details as details


CRITERIA = {
    "version": 3,
    "criteria": [
        {
            "paper_stems": ["01_Szabo2010", "1_Szabo2010_clean"],
            "target": "Dense motile monolayer.",
            "scoring_instructions": "Score both categories.",
            "clauses": [
                {
                    "id": "unoccupied_space_end_below_0_001_total",
                    "kind": "qualitative",
                    "weight": 2,
                    "description": "unoccupied space at end < 0.001*total space",
                },
                {
                    "id": "mean_cell_speed_end_above_0_01",
                    "kind": "numeric",
                    "weight": 1,
                    "description": "mean cell speed(t_end) > 0.01node/MCS",
                },
            ],
        }
    ],
}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf8")


def write_criteria(root: Path) -> tuple[Path, str]:
    path = root / "biological_scoring_criteria.json"
    write_json(path, CRITERIA)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def run_id(paper: str, mode: str, repetition: int) -> str:
    return f"20260524_002844_{paper}__{mode}__rep{repetition:02d}"


def write_summary(root: Path, runs: list[tuple[str, str, int]]) -> None:
    write_json(
        root / "benchmark_summary.json",
        {
            "results": [
                {
                    "paper": f"{paper}.pdf",
                    "mode": mode,
                    "repetition": repetition,
                    "runId": run_id(paper, mode, repetition),
                }
                for paper, mode, repetition in runs
            ]
        },
    )


def score_payload(
    paper: str,
    mode: str,
    repetition: int,
    criteria_sha: str,
    passed: tuple[bool, ...] = (True, True),
    score: float | None = 1.0,
    status: str = "scored",
    attempt_id: str = "attempt_001",
    scorer_model: str = "gpt-5.6-sol",
    generated_at: str = "2026-08-31T09:46:05.358Z",
    clause_ids: tuple[str, ...] | None = None,
) -> dict:
    ids = clause_ids or tuple(clause["id"] for clause in CRITERIA["criteria"][0]["clauses"])
    return {
        "ok": True,
        "status": status,
        "generatedAt": generated_at,
        "paper": f"{paper}.pdf",
        "mode": mode,
        "repetition": repetition,
        "runId": run_id(paper, mode, repetition),
        "attemptId": attempt_id,
        "attemptDir": f"attempts/{attempt_id}",
        "scorerVersion": 7,
        "scorerModel": scorer_model,
        "scorerReasoningEffort": "high",
        "criteriaVersion": 3,
        "criteriaSha256": criteria_sha,
        "attemptIdentity": "67eee74f82c7290ed30507a3977ed81c",
        "target": "Dense motile monolayer.",
        "score": score,
        "maxScore": 1,
        "clauses": [
            {
                "id": clause_id,
                "passed": clause_passed,
                "observed_value": f"observed {clause_id}",
                "evidence": [f"{clause_id} evidence one", f"{clause_id} evidence two"],
                "rationale": f"rationale for {clause_id}",
            }
            for clause_id, clause_passed in zip(ids, passed)
        ],
        "summary": "The run reached its configured endpoint.",
        "limitations": ["First limitation.", "Second limitation."],
    }


def write_score(root: Path, payload: dict, criteria_sha: str) -> Path:
    directory = root / payload["runId"] / details.SCORE_DIR_NAME
    variant = details.score_variant_key(payload, Path("unused.json"))
    path = directory / f"{variant}__attempt-{payload['attemptIdentity'][:12]}.json"
    write_json(path, payload)
    return path


class BiologicalScoreDetailsTests(unittest.TestCase):
    def test_variant_key_matches_the_scorer_artifact_name(self) -> None:
        payload = {
            "scorerVersion": 7,
            "scorerModel": "gpt-5.6 sol",
            "scorerReasoningEffort": "high",
            "criteriaVersion": 3,
            "criteriaSha256": "1adfb5d366a0ef41e132dd152164aaff",
        }

        key = details.score_variant_key(payload, Path("ignored.json"))

        self.assertEqual(key, "scorer-v7__gpt-5.6-sol__high__criteria-v3-1adfb5d366a0")

    def test_variant_key_falls_back_to_the_file_name_then_the_legacy_bucket(self) -> None:
        named = Path("scorer-v3__gpt-5.6-terra__high__criteria-v2-8a5d264634f3__attempt-67eee74f82c7.json")

        self.assertEqual(
            details.score_variant_key({}, named),
            "scorer-v3__gpt-5.6-terra__high__criteria-v2-8a5d264634f3",
        )
        self.assertEqual(details.score_variant_key({}, Path("biological_score.json")), details.UNKNOWN_VARIANT_KEY)

    def test_workbook_lands_in_the_scoring_folder_of_each_variant(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            criteria_path, criteria_sha = write_criteria(root)
            write_summary(root, [("01_Szabo2010", "morpheus_cli", 1)])
            write_score(root, score_payload("01_Szabo2010", "morpheus_cli", 1, criteria_sha), criteria_sha)
            write_score(
                root,
                score_payload("01_Szabo2010", "morpheus_cli", 1, criteria_sha, scorer_model="gpt-5.6-terra"),
                criteria_sha,
            )

            written = details.export_score_details(root, criteria_path=criteria_path)

            self.assertEqual(len(written), 2)
            for variant_key, path in written.items():
                self.assertEqual(path, root / "biological_scores" / variant_key / "biological_score_details.xlsx")
                self.assertTrue(path.exists())

    def test_paper_sheets_cover_every_mode_and_repetition_including_unscored_runs(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            criteria_path, criteria_sha = write_criteria(root)
            runs = [("01_Szabo2010", mode, rep) for mode in ("python_web", "morpheus_cli") for rep in (1, 2)]
            write_summary(root, runs)
            for mode, rep in [("morpheus_cli", 1), ("morpheus_cli", 2), ("python_web", 2)]:
                write_score(root, score_payload("01_Szabo2010", mode, rep, criteria_sha), criteria_sha)

            written = details.export_score_details(root, criteria_path=criteria_path)
            sheet = pd.read_excel(next(iter(written.values())), "01_Szabo2010")

            self.assertEqual(
                list(zip(sheet["mode"], sheet["repetition"])),
                [("python_web", 1), ("python_web", 2), ("morpheus_cli", 1), ("morpheus_cli", 2)],
            )
            self.assertEqual(sheet.loc[0, "status"], details.MISSING_STATUS)
            self.assertTrue(pd.isna(sheet.loc[0, "score"]))
            self.assertEqual(list(sheet["status"])[1:], ["scored", "scored", "scored"])

    def test_clause_columns_use_the_criteria_file_when_its_checksum_matches(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            criteria_path, criteria_sha = write_criteria(root)
            write_summary(root, [("01_Szabo2010", "morpheus_cli", 1)])
            write_score(
                root,
                score_payload("01_Szabo2010", "morpheus_cli", 1, criteria_sha, passed=(True, False), score=2 / 3),
                criteria_sha,
            )

            path = next(iter(details.export_score_details(root, criteria_path=criteria_path).values()))
            sheet = pd.read_excel(path, "01_Szabo2010")
            criteria = pd.read_excel(path, "Criteria")

            self.assertEqual(sheet.loc[0, "c01__passed"], details.PASS_TEXT)
            self.assertEqual(sheet.loc[0, "c02__passed"], details.FAIL_TEXT)
            self.assertEqual(sheet.loc[0, "passed_weight"], 2)
            self.assertEqual(sheet.loc[0, "total_weight"], 3)
            self.assertEqual(sheet.loc[0, "passed_clause_count"], 1)
            self.assertEqual(sheet.loc[0, "clause_count"], 2)
            self.assertEqual(list(criteria["clause_source"]), ["criteria_file", "criteria_file"])
            self.assertEqual(list(criteria["weight"]), [2, 1])
            self.assertEqual(criteria.loc[0, "description"], "unoccupied space at end < 0.001*total space")
            self.assertEqual(criteria.loc[0, "kind"], "qualitative")

    def test_clause_columns_fall_back_to_observed_ids_for_other_criteria_versions(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            criteria_path, _ = write_criteria(root)
            write_summary(root, [("01_Szabo2010", "morpheus_cli", 1)])
            payload = score_payload(
                "01_Szabo2010",
                "morpheus_cli",
                1,
                "8a5d264634f3951f3f0a9ca796c17f86",
                clause_ids=("legacy_clause_a", "legacy_clause_b"),
            )
            write_score(root, payload, "8a5d264634f3951f3f0a9ca796c17f86")

            path = next(iter(details.export_score_details(root, criteria_path=criteria_path).values()))
            criteria = pd.read_excel(path, "Criteria")
            sheet = pd.read_excel(path, "01_Szabo2010")
            overview = pd.read_excel(path, "Overview")

            self.assertEqual(list(criteria["clause_id"]), ["legacy_clause_a", "legacy_clause_b"])
            self.assertEqual(list(criteria["clause_source"]), ["observed", "observed"])
            self.assertTrue(criteria["weight"].isna().all())
            self.assertTrue(pd.isna(sheet.loc[0, "total_weight"]))
            self.assertEqual(sheet.loc[0, "c01__passed"], details.PASS_TEXT)
            self.assertEqual(
                overview.loc[overview["item"] == "criteria_file_match", "value"].iloc[0],
                "no (clause metadata omitted)",
            )

    def test_legacy_scores_without_provenance_form_their_own_variant(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            criteria_path, criteria_sha = write_criteria(root)
            write_summary(root, [("01_Szabo2010", "morpheus_cli", 1)])
            legacy = score_payload("01_Szabo2010", "morpheus_cli", 1, criteria_sha, score=0.5)
            for field in ("scorerVersion", "scorerModel", "scorerReasoningEffort", "criteriaVersion", "criteriaSha256"):
                legacy.pop(field)
            write_json(root / legacy["runId"] / details.LEGACY_SCORE_FILENAME, legacy)
            write_score(root, score_payload("01_Szabo2010", "morpheus_cli", 1, criteria_sha), criteria_sha)

            written = details.export_score_details(root, criteria_path=criteria_path)

            self.assertIn(details.UNKNOWN_VARIANT_KEY, written)
            sheet = pd.read_excel(written[details.UNKNOWN_VARIANT_KEY], "01_Szabo2010")
            self.assertEqual(sheet.loc[0, "score"], 0.5)
            self.assertEqual(sheet.loc[0, "score_json_path"], f"{legacy['runId']}/{details.LEGACY_SCORE_FILENAME}")

    def test_canonical_attempt_reports_the_scored_attempt_number(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            criteria_path, criteria_sha = write_criteria(root)
            write_summary(root, [("01_Szabo2010", "morpheus_cli", 1), ("01_Szabo2010", "morpheus_cli", 2)])
            write_score(root, score_payload("01_Szabo2010", "morpheus_cli", 1, criteria_sha), criteria_sha)
            write_score(
                root,
                score_payload("01_Szabo2010", "morpheus_cli", 2, criteria_sha, attempt_id="attempt_002"),
                criteria_sha,
            )

            path = next(iter(details.export_score_details(root, criteria_path=criteria_path).values()))
            sheet = pd.read_excel(path, "01_Szabo2010")

            self.assertEqual(list(sheet["canonical_attempt"]), [1, 2])
            self.assertEqual(list(sheet["attempt_id"]), ["attempt_001", "attempt_002"])

    def test_evidence_stacks_on_separate_lines_and_limitations_stay_on_one(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            criteria_path, criteria_sha = write_criteria(root)
            write_summary(root, [("01_Szabo2010", "morpheus_cli", 1)])
            write_score(root, score_payload("01_Szabo2010", "morpheus_cli", 1, criteria_sha), criteria_sha)

            path = next(iter(details.export_score_details(root, criteria_path=criteria_path).values()))
            sheet = pd.read_excel(path, "01_Szabo2010")

            self.assertEqual(
                sheet.loc[0, "c01__evidence"],
                "unoccupied_space_end_below_0_001_total evidence one\n"
                "unoccupied_space_end_below_0_001_total evidence two",
            )
            self.assertEqual(sheet.loc[0, "limitations"], "First limitation. | Second limitation.")
            self.assertNotIn("\n", sheet.loc[0, "limitations"])
            self.assertEqual(sheet.loc[0, "c01__rationale"], "rationale for unoccupied_space_end_below_0_001_total")

    def test_oversized_text_is_truncated_to_the_excel_cell_limit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            criteria_path, criteria_sha = write_criteria(root)
            write_summary(root, [("01_Szabo2010", "morpheus_cli", 1)])
            payload = score_payload("01_Szabo2010", "morpheus_cli", 1, criteria_sha)
            payload["clauses"][0]["rationale"] = "x" * (details.EXCEL_CELL_LIMIT + 100)
            write_score(root, payload, criteria_sha)

            path = next(iter(details.export_score_details(root, criteria_path=criteria_path).values()))
            sheet = pd.read_excel(path, "01_Szabo2010")

            self.assertEqual(len(sheet.loc[0, "c01__rationale"]), details.EXCEL_CELL_LIMIT)
            self.assertTrue(sheet.loc[0, "c01__rationale"].endswith(details.TRUNCATION_MARKER))

    def test_the_newest_score_file_wins_when_a_run_has_several_for_one_variant(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            criteria_path, criteria_sha = write_criteria(root)
            write_summary(root, [("01_Szabo2010", "morpheus_cli", 1)])
            older = score_payload("01_Szabo2010", "morpheus_cli", 1, criteria_sha, score=0.25)
            older["attemptIdentity"] = "aaaaaaaaaaaa1111"
            older["generatedAt"] = "2026-08-01T00:00:00.000Z"
            newer = score_payload("01_Szabo2010", "morpheus_cli", 1, criteria_sha, score=0.75)
            newer["attemptIdentity"] = "bbbbbbbbbbbb2222"
            newer["generatedAt"] = "2026-08-31T00:00:00.000Z"
            write_score(root, older, criteria_sha)
            write_score(root, newer, criteria_sha)

            path = next(iter(details.export_score_details(root, criteria_path=criteria_path).values()))
            sheet = pd.read_excel(path, "01_Szabo2010")
            overview = pd.read_excel(path, "Overview")

            self.assertEqual(len(sheet), 1)
            self.assertEqual(sheet.loc[0, "score"], 0.75)
            self.assertEqual(
                int(overview.loc[overview["item"] == "score_files_superseded", "value"].iloc[0]),
                1,
            )

    def test_manual_scores_add_delta_columns(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            criteria_path, criteria_sha = write_criteria(root)
            write_summary(root, [("01_Szabo2010", "morpheus_cli", 1)])
            write_score(
                root,
                score_payload("01_Szabo2010", "morpheus_cli", 1, criteria_sha, passed=(True, False), score=0.5),
                criteria_sha,
            )
            manual_csv = root / "manual_biological_scores.csv"
            pd.DataFrame.from_records(
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
                        "manual_score": 0.75,
                        "manual_score_source": "workbook_mean_score",
                    }
                ]
            ).to_csv(manual_csv, index=False)

            path = next(
                iter(details.export_score_details(root, criteria_path=criteria_path, manual_csv=manual_csv).values())
            )
            sheet = pd.read_excel(path, "01_Szabo2010")

            self.assertEqual(sheet.loc[0, "manual_score"], 0.75)
            self.assertAlmostEqual(sheet.loc[0, "score_delta"], -0.25)
            self.assertAlmostEqual(sheet.loc[0, "abs_error"], 0.25)

    def test_all_runs_sheet_pools_every_paper_without_clause_columns(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            criteria_path, criteria_sha = write_criteria(root)
            write_summary(root, [("01_Szabo2010", "morpheus_cli", 1), ("02_Thapa2024", "morpheus_cli", 1)])
            write_score(root, score_payload("01_Szabo2010", "morpheus_cli", 1, criteria_sha), criteria_sha)
            write_score(root, score_payload("02_Thapa2024", "morpheus_cli", 1, criteria_sha), criteria_sha)

            path = next(
                iter(details.export_score_details(root, criteria_path=criteria_path, all_runs_sheet=True).values())
            )
            names = pd.ExcelFile(path).sheet_names
            all_runs = pd.read_excel(path, details.ALL_RUNS_SHEET)

            self.assertEqual(names[:3], ["Overview", "Criteria", details.ALL_RUNS_SHEET])
            self.assertEqual(names[3:], ["01_Szabo2010", "02_Thapa2024"])
            self.assertEqual(list(all_runs["paper_stem"]), ["01_Szabo2010", "02_Thapa2024"])
            self.assertFalse([column for column in all_runs.columns if "__" in column])

    def test_export_without_score_files_writes_nothing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            criteria_path, _ = write_criteria(root)
            write_summary(root, [("01_Szabo2010", "morpheus_cli", 1)])

            self.assertEqual(details.export_score_details(root, criteria_path=criteria_path), {})

    def test_runs_missing_from_the_summary_are_recovered_from_disk(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            criteria_path, criteria_sha = write_criteria(root)
            write_summary(root, [])
            write_score(root, score_payload("01_Szabo2010", "morpheus_cli", 2, criteria_sha), criteria_sha)

            path = next(iter(details.export_score_details(root, criteria_path=criteria_path).values()))
            sheet = pd.read_excel(path, "01_Szabo2010")

            self.assertEqual(list(sheet["mode"]), ["morpheus_cli"])
            self.assertEqual(list(sheet["repetition"]), [2])

    def test_sheet_names_stay_within_the_excel_limit(self) -> None:
        long_stem = "20260524_a_very_long_paper_stem_that_exceeds_excel"

        self.assertEqual(len(details.sheet_name(long_stem, {})), details.SHEET_NAME_LIMIT)
        self.assertEqual(details.sheet_name("01/Szabo:2010", {}), "01_Szabo_2010")
        first = details.sheet_name(long_stem, {})
        self.assertNotEqual(details.sheet_name(long_stem, {first: pd.DataFrame()}), first)

    def test_attempt_number_and_truncation_helpers(self) -> None:
        self.assertEqual(details.attempt_number("attempt_012"), 12)
        self.assertTrue(math.isnan(details.attempt_number("")))
        self.assertEqual(details.truncate_cell("short"), "short")

    def test_main_lists_variants(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, criteria_sha = write_criteria(root)
            write_summary(root, [("01_Szabo2010", "morpheus_cli", 1)])
            write_score(root, score_payload("01_Szabo2010", "morpheus_cli", 1, criteria_sha), criteria_sha)

            self.assertEqual(details.main([str(root), "--list-variants"]), 0)
            self.assertEqual(details.main([str(root)]), 0)
            self.assertTrue((root / "biological_scores").is_dir())

    def test_main_reports_a_missing_benchmark_folder(self) -> None:
        with TemporaryDirectory() as tmp:
            self.assertEqual(details.main([str(Path(tmp) / "absent")]), 2)


if __name__ == "__main__":
    unittest.main()
