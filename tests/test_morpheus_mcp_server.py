from __future__ import annotations

import json
import os
import re
import signal
import shutil
import sys
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import morpheus_mcp_server as server

BENCHMARK_PAPERS_DIR = Path("benchmark_papers")


def benchmark_paper_pdfs() -> list[Path]:
    """Benchmark paper PDFs present in this checkout; they are not redistributed (see benchmark_papers/README.md)."""
    pdfs = []
    for pdf_path in sorted(BENCHMARK_PAPERS_DIR.glob("*.pdf")):
        with pdf_path.open("rb") as handle:
            if handle.read(5) == b"%PDF-":
                pdfs.append(pdf_path)
    return pdfs


def minimal_xml(stop_time: str = "500", with_model_graph: bool = True) -> str:
    model_graph = '<ModelGraph include-tags="#untagged" format="dot" reduced="false"/>' if with_model_graph else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<MorpheusModel version="4">
  <Description>
    <Title>Test Model</Title>
  </Description>
  <Space>
    <Lattice class="square">
      <Neighborhood><Order>1</Order></Neighborhood>
      <Size symbol="size" value="20,20,0"/>
    </Lattice>
    <SpaceSymbol symbol="space"/>
  </Space>
  <Time>
    <StartTime value="0"/>
    <StopTime value="{stop_time}"/>
    <TimeSymbol symbol="time"/>
  </Time>
  <Analysis>
    {model_graph}
    <Gnuplotter time-step="100">
      <Terminal name="png"/>
      <Plot><Cells value="cell.id"/></Plot>
    </Gnuplotter>
    <Logger time-step="100">
      <Input><Symbol symbol-ref="time"/></Input>
      <Output><TextOutput/></Output>
    </Logger>
  </Analysis>
</MorpheusModel>
"""


def xsd_valid_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<MorpheusModel version="4">
  <Description>
    <Details>Schema-valid benchmark smoke model.</Details>
    <Title>Schema Valid Model</Title>
  </Description>
  <Space>
    <Lattice class="square">
      <Size symbol="size" value="20,20,0"/>
      <BoundaryConditions>
        <Condition type="periodic" boundary="x"/>
        <Condition type="periodic" boundary="y"/>
      </BoundaryConditions>
      <Neighborhood><Order>1</Order></Neighborhood>
    </Lattice>
    <SpaceSymbol symbol="space"/>
  </Space>
  <Time>
    <TimeSymbol symbol="time"/>
    <StartTime value="0"/>
    <StopTime value="500"/>
  </Time>
  <Analysis>
    <ModelGraph include-tags="#untagged" format="dot" reduced="false"/>
    <Gnuplotter time-step="100">
      <Terminal name="png"/>
      <Plot><Cells value="cell.id"/></Plot>
    </Gnuplotter>
    <Logger time-step="100">
      <Input><Symbol symbol-ref="cell.id"/></Input>
      <Output><TextOutput/></Output>
    </Logger>
  </Analysis>
</MorpheusModel>
"""


class MorpheusMcpServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.local_tmp_root = Path.cwd() / ".tmp_test_runs"
        self.local_tmp_root.mkdir(parents=True, exist_ok=True)
        self.original_runs_root = server.RUNS_ROOT
        self.test_runs_root = self.local_tmp_root / f"runs_{uuid.uuid4().hex[:8]}"
        self.test_runs_root.mkdir(parents=True, exist_ok=True)
        server.RUNS_ROOT = self.test_runs_root
        server.RUNS_ROOT.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        server.RUNS_ROOT = self.original_runs_root
        shutil.rmtree(self.test_runs_root, ignore_errors=True)

    def _sample_pdf(self) -> Path:
        """Writes a small two-page text PDF for tests of the generic PDF tools."""
        import fitz  # type: ignore

        pdf_path = self.test_runs_root / "sample_paper.pdf"
        document = fitz.open()
        for page_number in (1, 2):
            page = document.new_page()
            page.insert_text((72, 72), f"Sample paper, page {page_number}. Figure {page_number}. Example caption.")
        document.save(pdf_path)
        document.close()
        return pdf_path.resolve()

    def _benchmark_paper(self, stem: str) -> Path:
        pdf_path = BENCHMARK_PAPERS_DIR / f"{stem}.pdf"
        if pdf_path not in benchmark_paper_pdfs():
            self.skipTest(f"{pdf_path} is not present; see benchmark_papers/README.md to obtain it")
        return pdf_path.resolve()

    def test_mcp_registration_hides_host_only_tools(self) -> None:
        expected_exposed = (
            "render_pdf_pages",
            "list_references",
            "read_reference",
            "write_model_xml",
            "run_morpheus_model",
            "summarize_morpheus_run",
            "sample_output_images",
            "evaluate_technical_run",
            "read_file_text",
        )
        hidden_but_callable = (
            "create_run",
            "extract_paper_text",
            "list_paper_figures",
            "list_paper_visuals",
            "validate_model_xml",
            "capture_model_xml_version",
            "read_pdf",
        )

        self.assertEqual(server.MCP_REGISTERED_TOOL_NAMES, expected_exposed)
        self.assertEqual(server.MCP_EXPOSED_TOOL_NAMES, frozenset(expected_exposed))
        self.assertTrue(server.MCP_HIDDEN_TOOL_NAMES.isdisjoint(server.MCP_EXPOSED_TOOL_NAMES))
        self.assertTrue(set(hidden_but_callable).issubset(server.MCP_HIDDEN_TOOL_NAMES))
        for tool_name in hidden_but_callable:
            self.assertTrue(callable(getattr(server, tool_name)))

    def test_mcp_server_has_general_workflow_instructions(self) -> None:
        self.assertIn("MorpheusML models", server.MORPHEUS_MCP_INSTRUCTIONS)
        self.assertIn("sample_output_images", server.MORPHEUS_MCP_INSTRUCTIONS)
        self.assertIn("biologically meaningful mechanisms", server.MORPHEUS_MCP_INSTRUCTIONS)
        self.assertEqual(server.mcp.instructions, server.MORPHEUS_MCP_INSTRUCTIONS)

    def test_mcp_decorator_rejects_unclassified_tools_and_basic_helpers(self) -> None:
        def unclassified_tool() -> None:
            return None

        with self.assertRaisesRegex(RuntimeError, "Unclassified Morpheus MCP tool"):
            server.benchmark_mcp_tool(unclassified_tool)

        with patch.object(server, "_now_stamp", return_value="20260102_030405"), patch.object(
            server.uuid,
            "uuid4",
            return_value=type("FakeUuid", (), {"hex": "abcdef0123456789"})(),
        ):
            self.assertEqual(server._new_run_id(), "20260102_030405_abcdef01")

        generated = server._coerce_run_id(None)
        self.assertRegex(generated, r"^\d{8}_\d{6}_[0-9a-f]{8}$")
        self.assertEqual(server._trim_cmd_output(b"\xffhello"), "hello")

    def test_path_text_env_and_schema_helpers_cover_defensive_branches(self) -> None:
        run_path = server._run_dir("run_defensive_helpers")
        short_log = run_path / "short.log"
        long_log = run_path / "long.log"
        short_log.write_text("short", encoding="utf-8")
        long_log.write_text("abcdef", encoding="utf-8")

        self.assertEqual(server._read_text(run_path / "missing.txt"), "")
        self.assertEqual(server._read_text_tail(run_path / "missing.log"), "")
        self.assertEqual(server._read_text_tail(short_log, max_chars=10), "short")
        self.assertEqual(server._read_text_tail(long_log, max_chars=3), "def")
        self.assertEqual(server._read_text_full(run_path / "missing.txt"), "")
        with self.assertRaisesRegex(ValueError, "file_name must not be empty"):
            server._resolve_run_file_path(run_path, " ")
        with self.assertRaisesRegex(ValueError, "path must not be empty"):
            server._resolve_allowed_read_path("")

        compact = server._compact_validation({"valid": True, "errors": "not-list", "warnings": None})
        self.assertEqual(compact["error_count"], 0)
        self.assertEqual(compact["warning_count"], 0)

        with patch.dict(server.os.environ, {"BAD_INT": "nope", "TOO_SMALL": "0", "OK_INT": "5"}, clear=False):
            self.assertEqual(server._integer_env("BAD_INT", 7), 7)
            self.assertEqual(server._integer_env("TOO_SMALL", 7), 7)
            self.assertEqual(server._integer_env("OK_INT", 7), 5)
        self.assertIsNone(server._positive_int_or_none("bad"))
        self.assertIsNone(server._positive_int_or_none(0))
        self.assertEqual(server._positive_int_or_none("4"), 4)
        with patch.dict(server.os.environ, {"MORPHEUS_XML_SCHEMA_PATH": " "}, clear=False):
            self.assertIsNone(server._configured_xml_schema_path())
        with patch.object(server, "xmlschema_lib", None):
            server._load_xml_schema.cache_clear()
            with self.assertRaisesRegex(RuntimeError, "xmlschema is not installed"):
                server._load_xml_schema("missing.xsd")

    def test_reference_tools_use_skill_reference_bundle(self) -> None:
        listed = server.list_references("CPM")

        self.assertTrue(listed["ok"])
        self.assertEqual(listed["categories"]["CPM"], ["cpm-examples.md"])

        read = server.read_reference("CPM", "cpm-examples.md", max_chars=120)

        self.assertTrue(read["ok"])
        self.assertEqual(read["name"], "cpm-examples.md")
        self.assertIn(".agents", read["path"])
        self.assertIn("Cellular Potts Model", read["content"])

    def test_render_pdf_pages_fails_when_requested_pages_are_all_out_of_range(self) -> None:
        pdf_path = self._sample_pdf()
        with patch.object(server, "_parse_pdf_page_count", return_value=7):
            result = server.render_pdf_pages(
                pdf_path=str(pdf_path),
                run_id="run_render",
                pages=[9999],
                dpi=72,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["requested_pages"], [9999])
        self.assertEqual(result["selected_pages"], [])
        self.assertGreater(result["total_pages"], 0)
        self.assertTrue(result["warnings"])

    def test_render_pdf_pages_falls_back_when_poppler_reports_missing_file(self) -> None:
        pdf_path = self._sample_pdf()

        def fake_pymupdf(_pdf_path: Path, out_dir: Path, pages: list[int], _dpi: int) -> list[Path]:
            rendered = []
            for page in pages:
                out_path = out_dir / f"page_{page:04d}.png"
                out_path.write_bytes(b"png")
                rendered.append(out_path)
            return rendered

        with patch.object(server, "_parse_pdf_page_count", return_value=7), patch.object(
            server,
            "_render_with_poppler",
            return_value=[self.test_runs_root / "run_render_fallback" / "paper_pages" / "page_0005.png"],
        ), patch.object(server, "_render_with_pymupdf", side_effect=fake_pymupdf):
            result = server.render_pdf_pages(
                pdf_path=str(pdf_path),
                run_id="run_render_fallback",
                pages=[5],
                dpi=72,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["pages"], [{"page": 5, "path": (Path("paper_pages") / "page_0005.png").as_posix()}])
        self.assertTrue((self.test_runs_root / "run_render_fallback" / "paper_pages" / "page_0005.png").exists())

    def test_list_paper_figures_uses_fallback_detection_when_pdfimages_is_unavailable(self) -> None:
        pdf_path = self._sample_pdf()
        with patch.object(server, "_list_pdf_figures", return_value=[]), patch.object(
            server,
            "_list_pdf_figures_with_pymupdf",
            return_value=([{"page": 2, "num": 1, "type": "heuristic_page"}], ["fallback used"]),
        ):
            result = server.list_paper_figures(pdf_path=str(pdf_path), run_id="run_figures")

        self.assertTrue(result["ok"])
        self.assertEqual(result["detection_method"], "pymupdf_heuristic")
        self.assertEqual(result["figure_pages"], [2])
        self.assertEqual(result["warnings"], ["fallback used"])

    def test_read_pdf_alias_matches_extract_paper_text(self) -> None:
        pdf_path = self._sample_pdf()

        aliased = server.read_pdf(pdf_path=str(pdf_path), run_id="run_read_pdf_alias")

        self.assertTrue(aliased["ok"])
        self.assertEqual(aliased["run_id"], "run_read_pdf_alias")
        self.assertTrue(Path(aliased["text_path"]).exists())
        self.assertGreater(aliased["page_count"], 0)

    def test_read_file_text_blocks_sibling_runs_when_active_run_is_set(self) -> None:
        active_path = server._run_dir("active_run") / "paper.txt"
        sibling_path = server._run_dir("sibling_run") / "paper.txt"
        active_path.write_text("active paper", encoding="utf-8")
        sibling_path.write_text("sibling paper", encoding="utf-8")

        with patch.dict(server.os.environ, {server.ACTIVE_RUN_ID_ENV: "active_run"}, clear=False):
            active = server.read_file_text(str(active_path))
            sibling = server.read_file_text(str(sibling_path))

        self.assertTrue(active["ok"])
        self.assertEqual(active["text"], "active paper")
        self.assertFalse(sibling["ok"])
        self.assertIn("only allows files inside", sibling["error"])

    def test_run_id_and_path_helpers_enforce_benchmark_boundaries(self) -> None:
        run_path = server._run_dir("active_run")
        nested = run_path / "nested"
        nested.mkdir(parents=True)

        self.assertEqual(server._sanitize_run_name("  paper 1 / model! "), "paper_1_model")
        self.assertEqual(server._sanitize_run_name("!!!"), "run")
        self.assertEqual(server._validate_run_id("run-01_ok"), "run-01_ok")
        with self.assertRaises(ValueError):
            server._validate_run_id("../escape")
        with patch.dict(server.os.environ, {server.ACTIVE_RUN_ID_ENV: "active_run"}, clear=False):
            self.assertEqual(server._coerce_run_id(None), "active_run")
            with self.assertRaises(ValueError):
                server._coerce_run_id("other_run")
            self.assertEqual(
                server._resolve_allowed_read_path("paper.txt"),
                run_path / "paper.txt",
            )

        self.assertEqual(
            server._resolve_run_file_path(run_path, "nested/model.xml"),
            nested / "model.xml",
        )
        self.assertEqual(
            server._relative_to_run(run_path, self.test_runs_root / "outside.txt"),
            (self.test_runs_root / "outside.txt").as_posix(),
        )
        with self.assertRaises(ValueError):
            server._resolve_run_file_path(run_path, "../outside.xml")
        with self.assertRaises(ValueError):
            server._resolve_run_file_path(run_path, "nested")

    def test_output_attempt_and_validation_helpers_summarize_deterministically(self) -> None:
        run_path = server._run_dir("run_helpers")
        (run_path / "nested").mkdir()
        for relative in ["a.png", "b.csv", "nested/c.xml", "nested/d.dot", "nested/e.log"]:
            (run_path / relative).write_text("x", encoding="utf-8")

        outputs = server._list_outputs(run_path)
        self.assertEqual(server._output_counts(outputs), {"png": 1, "csv": 1, "xml": 1, "dot": 1, "log": 1})
        self.assertEqual(server._sample_paths(run_path, outputs["xml"], limit=1), ["nested/c.xml"])

        compact = server._compact_validation(
            {
                "valid": False,
                "graph_generation_ready": True,
                "schema_validation_enabled": True,
                "schema_valid": False,
                "errors": [f"error {index}" for index in range(7)],
                "warnings": ["warning"],
                "schema_errors": ["schema"],
                "required_section_errors": ["Missing Analysis"],
                "has_root": True,
                "has_analysis": False,
            }
        )
        self.assertEqual(compact["error_count"], 7)
        self.assertEqual(compact["errors"], ["error 0", "error 1", "error 2", "error 3", "error 4"])
        self.assertEqual(compact["warning_count"], 1)
        self.assertTrue(compact["checks"]["has_root"])
        self.assertFalse(compact["checks"]["has_analysis"])

        server._attempt_dir(run_path, "attempt_001").mkdir(parents=True)
        server._attempt_dir(run_path, "attempt_003").mkdir(parents=True)
        server._merge_manifest("run_helpers", {"latest_attempt_id": "attempt_002"})
        self.assertEqual(server._validate_attempt_id("attempt_123"), "attempt_123")
        with self.assertRaises(ValueError):
            server._validate_attempt_id("attempt_12")
        self.assertEqual(server._next_attempt_id(run_path), "attempt_004")
        self.assertEqual(server._latest_attempt_id("run_helpers", run_path), "attempt_003")
        self.assertEqual(server._resolve_attempt("run_helpers", run_path, "attempt_999"), (None, None))
        server._attempt_dir(run_path, "attempt_002").mkdir(parents=True)
        self.assertEqual(server._latest_attempt_id("run_helpers", run_path), "attempt_002")

    def test_xml_log_time_and_image_sampling_helpers_cover_edge_cases(self) -> None:
        fenced = "```xml\n<MorpheusModel version='4'></MorpheusModel>\n```"
        self.assertEqual(server._sanitize_xml(fenced), "<MorpheusModel version='4'></MorpheusModel>")
        self.assertTrue(server._looks_like_morpheus_xml(fenced))
        self.assertFalse(server._looks_like_morpheus_xml("<MorpheusModel version='4'/>"))
        self.assertEqual(server._extract_stop_time("<StopTime value='1.5e2'/>"), 150.0)
        self.assertEqual(server._extract_stop_time("<StopTime>250</StopTime>"), 250.0)
        self.assertIsNone(server._extract_stop_time("<StopTime value='bad'/>"))
        self.assertEqual(server._count_time_lines("Time: 0\nTime: <1.5e2>\nTime: bad\n")[0], 2)
        self.assertEqual(server._count_time_lines("Time: 0\nTime: <1.5e2>\n")[1], [0.0, 150.0])
        self.assertEqual([server._calculate_time_score(count) for count in [0, 1, 2, 101]], [0, 1, 2, 3])
        self.assertEqual(server._calculate_time_score(2, stop_time_match=True), 3)
        self.assertEqual(server._count_error_lines(""), 0)
        self.assertEqual(server._count_error_lines("[ERROR] bad\ninfo\nException raised"), 2)
        self.assertEqual(server._count_error_lines("warning only\nanother line"), 2)
        self.assertEqual(server._extract_time_from_png_name("plot_001.5.png"), 1.5)
        self.assertIsNone(server._extract_time_from_png_name("plot_latest.png"))
        self.assertEqual(
            [path.name for path in server._pick_evenly_spaced([Path(f"p{index}") for index in range(5)], 3)],
            ["p0", "p2", "p4"],
        )
        self.assertEqual([path.name for path in server._pick_evenly_spaced([Path("p0"), Path("p1")], 1)], ["p0"])
        self.assertEqual(server._pick_evenly_spaced([Path("p0")], 0), [])
        self.assertIsNone(server._create_contact_sheet([], self.test_runs_root / "empty.png"))
        self.assertIsNone(server._create_contact_sheet([self.test_runs_root / "missing.png"], self.test_runs_root / "bad.png"))

        run_path = server._run_dir("run_images")
        for name in [
            "plot_00000.png",
            "plot_00010.png",
            "plot_00020.png",
            "plot_00030.png",
            "logger_plot_time_00000.png",
            "logger_plot_time_00030.png",
            "sample_contact_sheet.png",
        ]:
            (run_path / name).write_bytes(b"png")
        sample = server._sample_run_images(run_path, limit=2)

        self.assertEqual(sample["all_png_count"], 6)
        self.assertEqual(sample["primary_plot_count"], 4)
        self.assertEqual(sample["logger_plot_count"], 2)
        self.assertEqual(
            [path.name for path in sample["selected"]],
            ["plot_00000.png", "plot_00030.png", "logger_plot_time_00000.png", "logger_plot_time_00030.png"],
        )

    def test_pdf_text_render_and_parse_helpers_use_mocked_dependencies(self) -> None:
        pdf_path = self.test_runs_root / "paper.pdf"
        pdf_path.write_bytes(b"%PDF")

        with patch.object(server, "_which", return_value=None):
            self.assertIsNone(server._poppler_extract_text(pdf_path))
            self.assertIsNone(server._poppler_extract_page_texts(pdf_path))
            self.assertEqual(server._list_pdf_figures(pdf_path), [])

        with patch.object(server, "_which", return_value="/usr/bin/pdftotext"), patch.object(
            server,
            "_run_cmd",
            return_value={"returncode": 1, "stdout": ""},
        ):
            self.assertIsNone(server._poppler_extract_text(pdf_path))
            self.assertIsNone(server._poppler_extract_page_texts(pdf_path))
        with patch.object(server, "_which", return_value="/usr/bin/pdfimages"), patch.object(
            server,
            "_run_cmd",
            return_value={"returncode": 1, "stdout": ""},
        ):
            self.assertEqual(server._list_pdf_figures(pdf_path), [])

        with patch.object(server, "_which", return_value="/usr/bin/pdftotext"), patch.object(
            server,
            "_run_cmd",
            return_value={"returncode": 0, "stdout": "page one\fpage two\f"},
        ):
            self.assertEqual(server._poppler_extract_text(pdf_path), "page one\fpage two\f")
            self.assertEqual(server._poppler_extract_page_texts(pdf_path), ["page one", "page two"])
            self.assertEqual(server._extract_pdf_text(pdf_path), "page one\fpage two")
            self.assertEqual(server._extract_pdf_page_texts(pdf_path), (["page one", "page two"], []))

        with patch.object(server, "_poppler_extract_page_texts", return_value=None), patch.object(
            server,
            "_python_extract_page_texts",
            side_effect=RuntimeError("no extractor"),
        ):
            self.assertEqual(server._extract_pdf_page_texts(pdf_path), ([], ["no extractor"]))

        raw_pdfimages = "\n".join(
            [
                "page num type width height color comp bpc enc interp object ID x-ppi y-ppi size ratio",
                "---- --- ---- ----- ------ ----- ---- --- --- ------ ------ -- ----- ----- ---- -----",
                "1 0 image 100 200 rgb 3 8 jpeg no 12 0 72 72 10K 50%",
                "malformed",
            ]
        )
        figures = server._parse_pdfimages_output(raw_pdfimages)
        self.assertEqual(figures[0]["page"], 1)
        self.assertEqual(figures[0]["object_id"], "12 0")

        out_dir = self.test_runs_root / "rendered"
        out_dir.mkdir()

        def fake_run_cmd(command: list[str], **_kwargs: object) -> dict[str, object]:
            prefix = Path(command[-1])
            (out_dir / f"{prefix.name}-1.png").write_bytes(b"png")
            return {"returncode": 0, "stdout": "", "stderr": ""}

        with patch.object(server, "_which", return_value="/usr/bin/pdftoppm"), patch.object(
            server,
            "_run_cmd",
            side_effect=fake_run_cmd,
        ):
            self.assertEqual([path.name for path in server._render_with_poppler(pdf_path, out_dir, [1], 72)], ["page_0001.png"])
        with patch.object(server, "_which", return_value=None):
            self.assertEqual(server._render_with_poppler(pdf_path, out_dir, [2], 72), [])
        with patch.object(server, "_which", return_value="/usr/bin/pdftoppm"), patch.object(
            server,
            "_run_cmd",
            return_value={"returncode": 1, "stdout": "", "stderr": ""},
        ):
            self.assertEqual(server._render_with_poppler(pdf_path, out_dir, [2], 72), [])

        poppler_path = out_dir / "page_0002.png"
        pymupdf_path = out_dir / "page_0003.png"
        poppler_path.write_bytes(b"png")
        pymupdf_path.write_bytes(b"png")
        with patch.object(server, "_render_with_poppler", return_value=[poppler_path]), patch.object(
            server,
            "_render_with_pymupdf",
            return_value=[pymupdf_path],
        ):
            self.assertEqual([path.name for path in server._render_pdf_pages(pdf_path, out_dir, [2, 3], 72)], ["page_0002.png", "page_0003.png"])

        with patch.object(Path, "stat", side_effect=OSError("stat failed")):
            self.assertFalse(server._is_nonempty_file(pdf_path))

    def test_terminate_process_tree_escalates_when_parent_exits_but_process_group_survives(self) -> None:
        class ParentExits:
            pid = 4321

            def poll(self) -> None:
                return None

            def wait(self, timeout: int) -> int:
                self.wait_timeout = timeout
                return -signal.SIGTERM

        calls: list[tuple[int, int]] = []

        def fake_killpg(pid: int, sig: int) -> None:
            calls.append((pid, sig))

        process = ParentExits()
        sigkill = getattr(signal, "SIGKILL", 9)
        with patch.object(server.os, "name", "posix"), patch.object(
            server.os,
            "killpg",
            side_effect=fake_killpg,
            create=True,
        ):
            server._terminate_process_tree(process)  # type: ignore[arg-type]

        self.assertEqual(process.wait_timeout, 2)
        self.assertEqual(calls, [(4321, signal.SIGTERM), (4321, 0), (4321, sigkill)])

    def test_terminate_process_tree_kills_surviving_group_even_when_parent_already_exited(self) -> None:
        class ParentAlreadyExited:
            pid = 5432

            def poll(self) -> int:
                return 0

            def wait(self, timeout: int) -> int:
                raise AssertionError("wait should not be needed when the parent already exited")

        calls: list[tuple[int, int]] = []

        def fake_killpg(pid: int, sig: int) -> None:
            calls.append((pid, sig))

        sigkill = getattr(signal, "SIGKILL", 9)
        with patch.object(server.os, "name", "posix"), patch.object(
            server.os,
            "killpg",
            side_effect=fake_killpg,
            create=True,
        ):
            server._terminate_process_tree(ParentAlreadyExited())  # type: ignore[arg-type]

        self.assertEqual(calls, [(5432, signal.SIGTERM), (5432, 0), (5432, sigkill)])

    def test_detect_figure_items_includes_caption_only_pages(self) -> None:
        page_texts = [
            "\n".join(
                [
                    "Results",
                    "Some body text introducing the figure panel.",
                ]
            ),
            "\n".join(
                [
                    "Fig. 2. The computational model.",
                    "Additional caption text.",
                ]
            ),
            "\n".join(
                [
                    "Supplementary information",
                    "Boundary condition enforcement algorithm.",
                ]
            ),
        ]

        items = server._detect_figure_items_from_page_texts(
            page_texts=page_texts,
            figure_pages=[3],
            figure_method="pdfimages",
        )

        self.assertEqual([item["page"] for item in items], [2, 3])
        self.assertEqual(items[0]["label"], "Figure 2")
        self.assertEqual(items[0]["detection_method"], "caption_text")
        self.assertEqual(items[1]["label"], "Figure page 3")
        self.assertEqual(items[1]["detection_method"], "pdfimages")

    def test_detect_table_items_requires_caption_like_lines_not_body_references(self) -> None:
        page_texts = [
            "\n".join(
                [
                    "Results",
                    "As shown in Table 1 we varied the parameters across conditions.",
                    "The model reproduces the expected trend.",
                ]
            ),
            "\n".join(
                [
                    "alpha     2     1-4",
                    "beta      1     -",
                    "gamma     8     2-16",
                    "",
                    "Table 1. Parameters used in the model.",
                ]
            ),
        ]

        items = server._detect_table_items_from_page_texts(page_texts)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["page"], 2)
        self.assertEqual(items[0]["label"], "Table 1")
        self.assertIn("Parameters used in the model", items[0]["caption_snippet"])

    def test_detect_table_items_finds_right_column_caption_and_title(self) -> None:
        page_texts = [
            "\n".join(
                [
                    "development, the median hinge point cells anchor to the notochord                      Table 1",
                    "beneath them and start to form the floor plate. The floor plate gives                  Summary of the molecules and behavior in the neural tube closure model.",
                    "stability to the neural plate and starts to produce SHH, reinforcing the                Cell type        Behavior                Signal              Reference",
                    "physical forces outside of the neural plate are also at work. The surface               Surface          BMP4 secretion,         BMP4, FGF8,         (Liu and Niswander, 2005)",
                ]
            )
        ]

        items = server._detect_table_items_from_page_texts(page_texts)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["label"], "Table 1")
        self.assertIn("Summary of the molecules and behavior", items[0]["caption_snippet"])

    def test_detect_table_items_marks_continuation_pages(self) -> None:
        page_texts = [
            "\n".join(
                [
                    "Table S1. Parameter values and sources.",
                    "",
                    "Parameter                      Value              Reference           Notes",
                    "Mitotic germ cell             2.8 μm             †                   Our GFP z stacks put this in",
                    "Meiotic germ cell             4 μm               (Maddox et al., 2005)",
                    "Oocyte radius                 10 μm                                  Oocytes fill the proximal arm",
                ]
            ),
            "\n".join(
                [
                    "Time at start of turning      23 hr              (Stupay and Hubbard, 2003)",
                    "Cell sizes:",
                    "Mitotic germ cell             2.8 μm             †                   Our GFP z stacks put this in",
                    "Meiotic germ cell             4 μm               (Maddox et al., 2005)",
                    "Oocyte radius                 10 μm                                  Oocytes fill the proximal arm",
                    "Sperm radius                  1.5 μm             (Shakes et al., 2011)",
                    "Cell growth rate              1.0 μm/hr          *",
                ]
            ),
        ]

        items = server._detect_table_items_from_page_texts(page_texts)

        self.assertEqual([item["page"] for item in items], [1, 2])
        self.assertEqual(items[0]["label"], "Table S1")
        self.assertEqual(items[1]["label"], "Table S1 (continued)")
        self.assertEqual(items[1]["detection_method"], "table_continuation")

    def test_detect_table_items_handles_below_table_supplementary_caption(self) -> None:
        page_texts = [
            "\n".join(
                [
                    "and we took the single best scoring parameter set. However, this was sufficient to",
                    "demonstrate that a model that explicitly considered species that modulate g(r) and",
                    "c(r) was able to generate a GTPase rosette (S5 Fig, S1 Note Table A, below). In",
                ]
            ),
            "\n".join(
                [
                    "kbasal - g   Off disk/basal activation rate of a species       9.9e-5 s-1",
                    "modulating g",
                    "dg           Inactivation rate of a species modulating g       5.06 s-1",
                    "Dg           Diffusion coefficient of a species modulating g   4.21 mm2s-1",
                    "",
                    "S1 Note Table A. Parameters for describing diffusing species that modulate",
                    "the GAP activation rate, c, and the self-positive feedback rate, g.",
                ]
            ),
        ]

        items = server._detect_table_items_from_page_texts(page_texts)

        self.assertEqual([item["page"] for item in items], [2])
        self.assertEqual(items[0]["label"], "S1 Note Table A")
        self.assertIn("Parameters for describing diffusing species", items[0]["caption_snippet"])

    def test_visual_caption_and_reference_heuristic_edges(self) -> None:
        self.assertEqual(server._normalize_visual_label("Tab. 2"), "Table 2")
        self.assertEqual(server._normalize_visual_label("Fig. S1"), "Figure S1")
        self.assertFalse(server._line_has_caption_tail("Fig. 2 abc", server.FIGURE_LABEL_PATTERN))
        self.assertFalse(server._line_has_caption_tail("Fig. 2 _bad", server.FIGURE_LABEL_PATTERN))
        self.assertTrue(server._line_has_caption_tail("Fig. 2 (A) Results", server.FIGURE_LABEL_PATTERN))
        self.assertTrue(server._is_table_caption_line("Table 2"))
        self.assertFalse(server._is_table_caption_line("Table 2 abc"))
        self.assertFalse(server._is_table_caption_line("Table 2 / not a caption"))
        self.assertFalse(server._looks_like_table_value_segment(""))
        self.assertTrue(server._looks_like_table_value_segment("†"))
        self.assertTrue(server._looks_like_table_value_segment("(Smith 2020)"))
        self.assertTrue(server._looks_like_table_value_segment("10 μm"))
        self.assertFalse(server._looks_like_table_value_segment("parameter name"))
        self.assertFalse(server._is_cell_like_segment(""))
        self.assertEqual(server._extract_visual_label("body", server.FIGURE_LABEL_PATTERN, "Figure", 4), "Figure page 4")
        self.assertEqual(server._extract_visual_label("Fig. 4 Results", server.FIGURE_LABEL_PATTERN, "Figure", 4), "Figure 4")
        self.assertIsNone(server._extract_table_label_anywhere("body text"))
        self.assertEqual(server._extract_table_label_anywhere("see tab. 7"), "Table 7")
        self.assertEqual(
            server._extract_right_column_table_caption(
                [
                    "body text padded far to the right                         Table 3",
                    "more body text padded far to the right                     Parameters used in simulations.",
                ],
                0,
            ),
            ("Table 3", "Table 3 Parameters used in simulations."),
        )
        self.assertEqual(
            server._infer_reference_categories_from_text("Plain descriptive prose without method signals.")["selected_categories"],
            ["Miscellaneous"],
        )
        self.assertFalse(server._page_looks_like_table_preceding_caption([]))
        self.assertFalse(server._page_looks_like_table_continuation([]))
        self.assertFalse(server._page_looks_like_table_preceding_caption(["Table 1. Caption"]))
        self.assertFalse(server._page_looks_like_table_continuation(["Table 1. Caption"]))
        with patch.object(server, "_extract_pdf_page_texts", return_value=(["Fig. 1. Caption"], [])), patch.object(
            server,
            "_list_pdf_figures",
            return_value=[],
        ), patch.object(server, "_list_pdf_figures_with_pymupdf", return_value=([{"page": 1}], ["fallback"])):
            items, warnings = server._extract_visual_items_from_pdf(Path("paper.pdf"))
        self.assertEqual(warnings, ["fallback"])
        self.assertEqual(items[0]["detection_method"], "pymupdf_heuristic+caption")

    def test_detect_table_items_marks_page_before_below_table_caption(self) -> None:
        page_texts = [
            "\n".join(
                [
                    "Results for the fitted parameter set are shown below.",
                    "Parameter Description                                              Value",
                    "kdisk - c    On disk activation rate of a species modulating       113 s-1",
                    "             c",
                    "kbasal - c   Off disk/basal activation rate of a species           6.8 s-1",
                ]
            ),
            "\n".join(
                [
                    "dc           Inactivation rate of a species modulating c       6.96 s-1",
                    "Dc           Diffusion coefficient of a species modulating c   0.04 mm2s-1",
                    "",
                    "S1 Note Table A. Parameters for describing diffusing species that modulate",
                    "the GAP activation rate, c, and the self-positive feedback rate, g.",
                ]
            ),
        ]

        items = server._detect_table_items_from_page_texts(page_texts)

        self.assertEqual([item["page"] for item in items], [1, 2])
        self.assertEqual(items[0]["label"], "S1 Note Table A (preceding page)")
        self.assertEqual(items[0]["detection_method"], "table_preceding_page")
        self.assertEqual(items[1]["label"], "S1 Note Table A")

    def test_list_paper_visuals_combines_figures_and_tables(self) -> None:
        pdf_path = self._sample_pdf()
        with patch.object(
            server,
            "_list_pdf_figures",
            return_value=[{"page": 2, "num": 1, "type": "image"}],
        ), patch.object(
            server,
            "_extract_visual_items_from_pdf",
            return_value=(
                [
                    {
                        "kind": "figure",
                        "label": "Figure 1",
                        "page": 2,
                        "caption_snippet": "Figure 1. Example figure.",
                        "detection_method": "pdfimages+caption",
                        "confidence": "high",
                    },
                    {
                        "kind": "table",
                        "label": "Table 2",
                        "page": 4,
                        "caption_snippet": "Table 2. Example table.",
                        "detection_method": "layout_caption",
                        "confidence": "high",
                    },
                ],
                ["visual fallback used"],
            ),
        ):
            result = server.list_paper_visuals(pdf_path=str(pdf_path), run_id="run_visuals")

        self.assertTrue(result["ok"])
        self.assertEqual(result["figure_pages"], [2])
        self.assertEqual(result["table_pages"], [4])
        self.assertEqual(result["visual_pages"], [2, 4])
        self.assertEqual(result["warnings"], ["visual fallback used"])

    def test_benchmark_visual_manifest_keeps_berkhout_lfs_paper_table_free(self) -> None:
        pdf_path = self._benchmark_paper("10_Berkhout2025")
        result = server.list_paper_visuals(pdf_path=str(pdf_path), run_id="run_berkhout_tables")

        self.assertTrue(result["ok"])
        self.assertEqual(result["table_pages"], [])

    def test_validate_model_xml_uses_morpheus_xsd_for_known_good_xml(self) -> None:
        validation = server.validate_model_xml(xsd_valid_xml())

        self.assertTrue(validation["ok"], validation.get("schema_errors"))
        self.assertTrue(validation["schema_validation_enabled"])
        self.assertTrue(validation["schema_valid"])
        self.assertEqual(validation["required_section_errors"], [])

    def test_validate_model_xml_reports_schema_errors_without_failing_structural_validation(self) -> None:
        malformed = server.validate_model_xml("<MorpheusModel version='4'><Description>")
        self.assertFalse(malformed["ok"])
        self.assertTrue(malformed["xml_parse_errors"])

        invalid = server.validate_model_xml(
            xsd_valid_xml().replace("</Analysis>", "<UnknownAnalysisPlugin/></Analysis>")
        )
        self.assertTrue(invalid["ok"])
        self.assertFalse(invalid["schema_valid"])
        self.assertTrue(invalid["schema_errors"])

    def test_validate_model_xml_reports_missing_version_warnings_and_schema_failures(self) -> None:
        no_version = minimal_xml().replace(' version="4"', "")
        validation = server.validate_model_xml(no_version)

        self.assertFalse(validation["ok"])
        self.assertIn('MorpheusModel must declare version="4"', validation["required_section_errors"])

        missing_outputs = minimal_xml().replace("<Gnuplotter time-step=\"100\">", "<DisabledGnuplotter time-step=\"100\">").replace(
            "</Gnuplotter>",
            "</DisabledGnuplotter>",
        ).replace("<Logger time-step=\"100\">", "<DisabledLogger time-step=\"100\">").replace("</Logger>", "</DisabledLogger>").replace(
            '<ModelGraph include-tags="#untagged" format="dot" reduced="false"/>',
            "",
        )
        warning_validation = server.validate_model_xml(missing_outputs)
        self.assertIn("Analysis section is missing Gnuplotter PNG output", warning_validation["warnings"])
        self.assertIn("Analysis section is missing Logger CSV output", warning_validation["warnings"])
        self.assertIn("Analysis section is missing ModelGraph output", warning_validation["warnings"])

        with patch.object(server, "_configured_xml_schema_path", return_value=self.test_runs_root / "missing.xsd"):
            missing_schema = server.validate_model_xml(minimal_xml())
        self.assertIn("MorpheusML XSD schema not found", missing_schema["warnings"][0])
        with patch.object(server, "_configured_xml_schema_path", return_value=self.test_runs_root), patch.object(
            server,
            "xmlschema_lib",
            None,
        ):
            no_xmlschema = server.validate_model_xml(minimal_xml())
        self.assertIn("xmlschema is not installed", no_xmlschema["warnings"][0])

        missing_sections = server.validate_model_xml("<MorpheusModel version='4'></MorpheusModel>")
        self.assertIn("Missing required Description section", missing_sections["required_section_errors"])
        self.assertIn("Missing required Space section", missing_sections["required_section_errors"])
        self.assertIn("Missing required Time section", missing_sections["required_section_errors"])

        class BrokenSchema:
            def iter_errors(self, _root: object) -> list[object]:
                raise RuntimeError("schema boom")

        with patch.object(server, "_configured_xml_schema_path", return_value=self.test_runs_root), patch.object(
            server,
            "xmlschema_lib",
            object(),
        ), patch.object(server, "_load_xml_schema", return_value=BrokenSchema()):
            schema_failure = server.validate_model_xml(minimal_xml())
        self.assertFalse(schema_failure["schema_valid"])
        self.assertEqual(schema_failure["schema_errors"], ["XSD validation failed: schema boom"])

    def test_validate_model_xml_keeps_benchmark_required_sections_stricter_than_xsd(self) -> None:
        without_analysis = xsd_valid_xml().replace(
            """  <Analysis>
    <ModelGraph include-tags="#untagged" format="dot" reduced="false"/>
    <Gnuplotter time-step="100">
      <Terminal name="png"/>
      <Plot><Cells value="cell.id"/></Plot>
    </Gnuplotter>
    <Logger time-step="100">
      <Input><Symbol symbol-ref="cell.id"/></Input>
      <Output><TextOutput/></Output>
    </Logger>
  </Analysis>
""",
            "",
        )

        validation = server.validate_model_xml(without_analysis)

        self.assertFalse(validation["ok"])
        self.assertTrue(validation["schema_valid"])
        self.assertIn("Missing required Analysis section", validation["required_section_errors"])

    def test_benchmark_visual_manifest_marks_atwell_table_continuation_page(self) -> None:
        pdf_path = self._benchmark_paper("04_Atwell2025")
        result = server.list_paper_visuals(pdf_path=str(pdf_path), run_id="run_atwell_tables")

        self.assertTrue(result["ok"])
        self.assertEqual(result["table_pages"], [14, 15, 16])
        continuation_items = [
            item for item in result["items"] if item["kind"] == "table" and item["detection_method"] == "table_continuation"
        ]
        self.assertTrue(any(item["page"] == 15 and item["label"] == "Table S1 (continued)" for item in continuation_items))

    def test_benchmark_visual_manifest_detects_atwell_caption_only_figure_pages(self) -> None:
        pdf_path = self._benchmark_paper("04_Atwell2025")
        result = server.list_paper_visuals(pdf_path=str(pdf_path), run_id="run_atwell_figures")

        self.assertTrue(result["ok"])
        self.assertEqual(result["figure_pages"], [2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 24, 26, 27, 28])
        self.assertTrue(
            any(item["page"] == 5 and item["label"] == "Figure S2" and item["detection_method"] == "caption_text" for item in result["items"])
        )
        self.assertTrue(
            any(item["page"] == 6 and item["label"] == "Figure S3" and item["detection_method"] == "pdfimages+caption" for item in result["items"])
        )

    def test_benchmark_visual_manifest_detects_herron_supplementary_table(self) -> None:
        pdf_path = self._benchmark_paper("06_Herron2022")
        result = server.list_paper_visuals(pdf_path=str(pdf_path), run_id="run_herron_tables")

        self.assertTrue(result["ok"])
        self.assertIn(10, result["table_pages"])
        self.assertIn(11, result["table_pages"])
        self.assertTrue(
            any(item["page"] == 11 and item["label"] == "S1 Note Table A" for item in result["items"] if item["kind"] == "table")
        )
        self.assertTrue(
            any(
                item["page"] == 10 and item["label"] == "S1 Note Table A (preceding page)"
                for item in result["items"]
                if item["kind"] == "table"
            )
        )

    def test_benchmark_table_detection_snippets_stay_caption_like(self) -> None:
        pdfs = benchmark_paper_pdfs()
        if not pdfs:
            self.skipTest("no benchmark paper PDFs present; see benchmark_papers/README.md to obtain them")

        caption_like = re.compile(
            r"^\s*((table|tab\.)\s*[a-z]?\s*\d+|s\d+\s+note\s+table\s+[a-z0-9]+)\s*([.:\-–]|\s+[A-Z])",
            re.IGNORECASE,
        )

        for index, pdf_path in enumerate(pdfs, start=1):
            result = server.list_paper_visuals(
                pdf_path=str(pdf_path.resolve()),
                run_id=f"run_visual_validation_{index}",
            )
            self.assertTrue(result["ok"], msg=pdf_path.name)
            for item in result["items"]:
                if item["kind"] != "table":
                    continue
                if item["detection_method"] == "table_continuation":
                    self.assertRegex(
                        item["caption_snippet"],
                        re.compile(r"\(continued\)|continuation", re.IGNORECASE),
                        msg=f"{pdf_path.name}: {item['caption_snippet']}",
                    )
                    continue
                if item["detection_method"] == "table_preceding_page":
                    self.assertRegex(
                        item["caption_snippet"],
                        re.compile(r"\(preceding page\)|previous page", re.IGNORECASE),
                        msg=f"{pdf_path.name}: {item['caption_snippet']}",
                    )
                    continue
                self.assertRegex(
                    item["caption_snippet"],
                    caption_like,
                    msg=f"{pdf_path.name}: {item['caption_snippet']}",
                )

    def test_latest_attempt_controls_summary_and_sampling(self) -> None:
        run_id = "run_attempts"
        run_path = server._run_dir(run_id)
        (run_path / "model.xml").write_text(minimal_xml(stop_time="500"), encoding="utf-8")
        server._merge_manifest(run_id, {"latest_attempt_id": "attempt_002"})

        attempt_one = server._attempt_dir(run_path, "attempt_001")
        attempt_one.mkdir(parents=True, exist_ok=True)
        (attempt_one / "stdout.log").write_text("Time: 0\nTime: 800\n", encoding="utf-8")
        (attempt_one / "plot_00800.png").write_bytes(b"old")
        (attempt_one / "logger_plot_time_00800.png").write_bytes(b"old")
        (attempt_one / "logger.csv").write_text("time\n800\n", encoding="utf-8")

        attempt_two = server._attempt_dir(run_path, "attempt_002")
        attempt_two.mkdir(parents=True, exist_ok=True)
        (attempt_two / "stdout.log").write_text("Time: 0\nTime: 500\n", encoding="utf-8")
        (attempt_two / "stderr.log").write_text("", encoding="utf-8")
        (attempt_two / "plot_00500.png").write_bytes(b"new")
        (attempt_two / "logger_plot_time_00500.png").write_bytes(b"new")
        (attempt_two / "logger.csv").write_text("time\n500\n", encoding="utf-8")

        summary = server.summarize_morpheus_run(run_id=run_id)
        sample = server.sample_output_images(run_id=run_id, limit=5)
        latest_primary_plot = Path(summary["key_outputs"]["latest_primary_plot"]).as_posix()
        selected_images = [Path(value).as_posix() for value in sample["selected_images"]]

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["attempt_id"], "attempt_002")
        self.assertEqual(summary["time_progress"]["last_time_value"], 500.0)
        self.assertEqual(latest_primary_plot, "attempts/attempt_002/plot_00500.png")
        self.assertNotIn("plot_00800.png", json.dumps(summary))

        self.assertTrue(sample["ok"])
        self.assertEqual(sample["attempt_id"], "attempt_002")
        self.assertEqual(selected_images, ["attempts/attempt_002/plot_00500.png", "attempts/attempt_002/logger_plot_time_00500.png"])

    def test_evaluate_technical_run_uses_latest_attempt_only_and_flags_graph_mismatch(self) -> None:
        run_id = "run_eval"
        run_path = server._run_dir(run_id)
        (run_path / "model.xml").write_text(minimal_xml(stop_time="500", with_model_graph=False), encoding="utf-8")

        attempt_one = server._attempt_dir(run_path, "attempt_001")
        attempt_one.mkdir(parents=True, exist_ok=True)
        (attempt_one / "stdout.log").write_text("Time: 0\nTime: 800\n", encoding="utf-8")
        (attempt_one / "plot_00800.png").write_bytes(b"old")
        (attempt_one / "logger.csv").write_text("time\n800\n", encoding="utf-8")

        attempt_two = server._attempt_dir(run_path, "attempt_002")
        attempt_two.mkdir(parents=True, exist_ok=True)
        (attempt_two / "stdout.log").write_text("Time: 0\nTime: 500\n", encoding="utf-8")
        (attempt_two / "stderr.log").write_text("", encoding="utf-8")
        (attempt_two / "plot_00500.png").write_bytes(b"new")
        (attempt_two / "logger_plot_time_00500.png").write_bytes(b"new")
        (attempt_two / "logger.csv").write_text("time\n500\n", encoding="utf-8")
        (attempt_two / "model_graph.dot").write_text("digraph G {}", encoding="utf-8")
        server._merge_manifest(run_id, {"latest_attempt_id": "attempt_002"})

        evaluation = server.evaluate_technical_run(run_id=run_id)
        latest_primary_plot = Path(evaluation["breakdown"]["latest_primary_plot"]).as_posix()

        self.assertTrue(evaluation["ok"])
        self.assertEqual(evaluation["attempt_id"], "attempt_002")
        self.assertEqual(latest_primary_plot, "attempts/attempt_002/plot_00500.png")
        self.assertTrue(evaluation["breakdown"]["model_graph_present"])
        self.assertFalse(evaluation["breakdown"]["model_graph_matches_xml"])
        self.assertEqual(evaluation["breakdown"]["model_graph_score"], 0)

    def test_evaluate_technical_run_gives_full_time_score_when_stop_time_is_reached(self) -> None:
        run_id = "run_eval_sparse_progress"
        run_path = server._run_dir(run_id)
        (run_path / "model.xml").write_text(minimal_xml(stop_time="450"), encoding="utf-8")

        attempt_path = server._attempt_dir(run_path, "attempt_001")
        attempt_path.mkdir(parents=True, exist_ok=True)
        sparse_progress = "\n".join(f"Time: {value}" for value in range(0, 451, 5)) + "\n"
        (attempt_path / "model.xml").write_text(minimal_xml(stop_time="450"), encoding="utf-8")
        (attempt_path / "stdout.log").write_text(sparse_progress, encoding="utf-8")
        (attempt_path / "stderr.log").write_text("", encoding="utf-8")
        (attempt_path / "plot_00450.png").write_bytes(b"new")
        (attempt_path / "logger.csv").write_text("time\n450\n", encoding="utf-8")
        (attempt_path / "model_graph.dot").write_text("digraph G {}", encoding="utf-8")
        server._merge_manifest(
            run_id,
            {
                "latest_attempt_id": "attempt_001",
                "latest_attempt_returncode": 0,
                "latest_attempt_timed_out": False,
            },
        )

        evaluation = server.evaluate_technical_run(run_id=run_id)

        self.assertTrue(evaluation["ok"])
        self.assertEqual(evaluation["breakdown"]["time_lines_count"], 91)
        self.assertEqual(evaluation["breakdown"]["last_time_value"], 450.0)
        self.assertTrue(evaluation["breakdown"]["stop_time_match"])
        self.assertEqual(evaluation["breakdown"]["time_score"], 3)

    def test_evaluate_technical_run_emits_audit_warnings_without_changing_score(self) -> None:
        run_id = "run_eval_warnings"
        run_path = server._run_dir(run_id)
        (run_path / "model.xml").write_text(minimal_xml(stop_time="500"), encoding="utf-8")

        attempt_path = server._attempt_dir(run_path, "attempt_001")
        attempt_path.mkdir(parents=True, exist_ok=True)
        (attempt_path / "model.xml").write_text(minimal_xml(stop_time="400"), encoding="utf-8")
        (attempt_path / "stdout.log").write_text("Time: 0\nTime: 500\n", encoding="utf-8")
        (attempt_path / "stderr.log").write_text("", encoding="utf-8")
        (attempt_path / "plot_00500.png").write_bytes(b"new")
        (attempt_path / "logger.csv").write_text("time\n500\n", encoding="utf-8")
        (attempt_path / "model_graph.dot").write_text("digraph G {}", encoding="utf-8")
        server._merge_manifest(
            run_id,
            {
                "latest_attempt_id": "attempt_001",
                "latest_attempt_returncode": 1,
                "latest_attempt_timed_out": True,
            },
        )

        evaluation = server.evaluate_technical_run(run_id=run_id)

        self.assertTrue(evaluation["ok"])
        self.assertEqual(evaluation["attempt_count"], 1)
        self.assertGreater(evaluation["total_score"], 0)
        self.assertIn("latest Morpheus attempt returned nonzero exit code 1", evaluation["warnings"])
        self.assertIn("latest Morpheus attempt timed out", evaluation["warnings"])
        self.assertIn("current model.xml differs from the scored attempt XML", evaluation["warnings"])

    def test_run_morpheus_model_timeout_records_logs_and_manifest_metadata(self) -> None:
        run_id = "run_timeout"
        run_path = server._run_dir(run_id)
        xml_path = run_path / "model.xml"
        xml_path.write_text(minimal_xml(stop_time="500"), encoding="utf-8")

        with patch.object(
            server,
            "_run_cmd",
            return_value={
                "returncode": None,
                "stdout": "Time: 0\n",
                "stderr": "timed out",
                "command": ["morpheus"],
                "timed_out": True,
                "timeout_s": 1,
            },
        ):
            result = server.run_morpheus_model(
                xml_path=str(xml_path),
                run_id=run_id,
                timeout_ms=1,
            )

        manifest = json.loads((run_path / "run_manifest.json").read_text(encoding="utf-8"))

        self.assertFalse(result["ok"])
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["timeout_ms"], 1)
        self.assertTrue((run_path / "attempts" / "attempt_001" / "stdout.log").exists())
        self.assertTrue((run_path / "attempts" / "attempt_001" / "stderr.log").exists())
        self.assertTrue(manifest["latest_attempt_timed_out"])
        self.assertEqual(manifest["latest_attempt_timeout_ms"], 1)

    def test_run_morpheus_model_clamps_to_subject_soft_cutoff_and_preserves_outputs(self) -> None:
        run_id = "run_deadline_clamp"
        run_path = server._run_dir(run_id)
        xml_path = run_path / "model.xml"
        xml_path.write_text(minimal_xml(stop_time="500"), encoding="utf-8")
        deadline_path = run_path / "subject_deadline.json"
        deadline_path.write_text(
            json.dumps({"softCutoffEpochMs": 10_500, "hardCutoffEpochMs": 20_000}),
            encoding="utf-8",
        )

        def fake_run(command, **kwargs):
            attempt_path = Path(command[command.index("--outdir") + 1])
            (attempt_path / "partial.csv").write_text("time,value\n0,1\n", encoding="utf-8")
            return {
                "returncode": None,
                "stdout": "Time: 0\n",
                "stderr": "timed out",
                "command": command,
                "timed_out": True,
                "timeout_s": kwargs["timeout_s"],
                "duration_ms": 500,
                "started_at": "1970-01-01T00:00:10+00:00",
                "finished_at": "1970-01-01T00:00:10.500000+00:00",
            }

        with patch.dict(
            server.os.environ,
            {
                "BENCHMARK_DEADLINE_PATH": str(deadline_path),
                "MORPHEUS_RUN_TIMEOUT_MS": "3600000",
            },
            clear=False,
        ), patch.object(server, "_now_epoch_ms", side_effect=[10_000, 10_500]), patch.object(
            server, "_run_cmd", side_effect=fake_run
        ) as run_cmd:
            result = server.run_morpheus_model(xml_path=str(xml_path), run_id=run_id, timeout_ms=7_200_000)

        attempt_path = run_path / "attempts" / "attempt_001"
        command_manifest = json.loads((attempt_path / "morpheus_command.json").read_text(encoding="utf-8"))
        executed_command = run_cmd.call_args.args[0]
        self.assertEqual(Path(executed_command[executed_command.index("-f") + 1]), attempt_path / "model.xml")
        self.assertEqual(run_cmd.call_args.kwargs["timeout_s"], 0.5)
        self.assertEqual(result["returncode"], 124)
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["configured_timeout_ms"], 3_600_000)
        self.assertEqual(result["effective_timeout_ms"], 500)
        self.assertEqual(result["remaining_before_ms"], 500)
        self.assertEqual(result["remaining_after_ms"], 0)
        self.assertTrue((attempt_path / "partial.csv").exists())
        self.assertEqual(command_manifest["returnCode"], 124)
        self.assertEqual(command_manifest["effectiveTimeoutMs"], 500)
        self.assertTrue(command_manifest["timedOut"])
        self.assertEqual(command_manifest["command"][0], "morpheus")

    def test_run_morpheus_model_refuses_at_soft_cutoff_without_spawning(self) -> None:
        run_id = "run_deadline_refusal"
        run_path = server._run_dir(run_id)
        xml_path = run_path / "model.xml"
        xml_path.write_text(minimal_xml(stop_time="500"), encoding="utf-8")
        deadline_path = run_path / "subject_deadline.json"
        deadline_path.write_text(
            json.dumps({"softCutoffEpochMs": 10_000, "hardCutoffEpochMs": 20_000}),
            encoding="utf-8",
        )

        with patch.dict(
            server.os.environ,
            {"BENCHMARK_DEADLINE_PATH": str(deadline_path), "MORPHEUS_RUN_TIMEOUT_MS": "3600000"},
            clear=False,
        ), patch.object(server, "_now_epoch_ms", return_value=10_000), patch.object(server, "_run_cmd") as run_cmd:
            result = server.run_morpheus_model(xml_path=str(xml_path), run_id=run_id)

        attempt_path = run_path / "attempts" / "attempt_001"
        command_manifest = json.loads((attempt_path / "morpheus_command.json").read_text(encoding="utf-8"))
        run_cmd.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertEqual(result["returncode"], 125)
        self.assertTrue(result["refused_for_finalization"])
        self.assertEqual(result["effective_timeout_ms"], 0)
        self.assertTrue((attempt_path / "model.xml").exists())
        self.assertEqual((attempt_path / "stdout.log").read_text(encoding="utf-8"), "")
        self.assertTrue(command_manifest["refusedForFinalization"])

    def test_public_tool_error_branches_without_live_morpheus(self) -> None:
        with patch.dict(server.os.environ, {server.ACTIVE_RUN_ID_ENV: "active_run"}, clear=False):
            active_created = server.create_run("ignored")
        self.assertTrue(active_created["ok"])
        self.assertEqual(active_created["run_id"], "active_run")
        self.assertIn("no-op", active_created["note"])

        with patch.object(server, "_now_stamp", return_value="20260102_030405"):
            named_created = server.create_run("paper model")
        self.assertEqual(named_created["run_id"], "20260102_030405_paper_model")
        with patch.object(server, "_new_run_id", return_value="run_default"):
            self.assertEqual(server.create_run()["run_id"], "run_default")
        existing_name_path = server.RUNS_ROOT / "existing_model"
        existing_name_path.mkdir(parents=True, exist_ok=True)
        self.assertEqual(server.create_run("existing model")["run_id"], "existing_model")

        missing_pdf = server.extract_paper_text(str(self.test_runs_root / "missing.pdf"), run_id="run_missing_pdf")
        self.assertFalse(missing_pdf["ok"])
        self.assertIn("PDF not found", missing_pdf["error"])

        pdf_path = self.test_runs_root / "paper.pdf"
        pdf_path.write_bytes(b"%PDF")
        with patch.object(server, "_extract_pdf_text", side_effect=RuntimeError("extract boom")):
            extraction_failed = server.extract_paper_text(str(pdf_path), run_id="run_extract_fail")
        self.assertFalse(extraction_failed["ok"])
        self.assertEqual(extraction_failed["error"], "extract boom")
        with patch.object(server, "_extract_pdf_text", return_value=" "):
            empty_text = server.extract_paper_text(str(pdf_path), run_id="run_empty_pdf")
        self.assertFalse(empty_text["ok"])
        self.assertEqual(empty_text["error"], "No text could be extracted from PDF")

        requested, selected, warnings = server._normalize_page_request(5, [0, 1, 2, 6], max_pages=1)
        self.assertEqual(requested, [0, 1, 2, 6])
        self.assertEqual(selected, [1])
        self.assertEqual(len(warnings), 2)

        missing_render = server.render_pdf_pages(str(self.test_runs_root / "missing.pdf"), run_id="run_missing_render")
        self.assertFalse(missing_render["ok"])
        self.assertIn("PDF not found", missing_render["error"])
        with patch.dict(server.os.environ, {server.ACTIVE_RUN_ID_ENV: "active_run"}, clear=False):
            invalid_run = server.render_pdf_pages(str(pdf_path), run_id="other_run")
        self.assertFalse(invalid_run["ok"])
        self.assertIn("Active benchmark run", invalid_run["error"])
        with patch.dict(server.os.environ, {server.ACTIVE_RUN_ID_ENV: "active_run"}, clear=False):
            invalid_extract_run = server.extract_paper_text(str(pdf_path), run_id="other_run")
        self.assertFalse(invalid_extract_run["ok"])
        self.assertIn("Active benchmark run", invalid_extract_run["error"])
        with patch.object(server, "_parse_pdf_page_count", return_value=2), patch.object(
            server,
            "_render_pdf_pages",
            side_effect=RuntimeError("render boom"),
        ):
            render_failed = server.render_pdf_pages(str(pdf_path), run_id="run_render_fail", pages=[1])
        self.assertFalse(render_failed["ok"])
        self.assertEqual(render_failed["error"], "render boom")
        rendered_page = server._run_dir("run_partial_render") / "paper_pages" / "page_0001.png"
        rendered_page.parent.mkdir(parents=True, exist_ok=True)
        rendered_page.write_bytes(b"png")
        with patch.object(server, "_parse_pdf_page_count", return_value=2), patch.object(
            server,
            "_render_pdf_pages",
            return_value=[rendered_page],
        ):
            partial_render = server.render_pdf_pages(str(pdf_path), run_id="run_partial_render", pages=[1, 2])
        self.assertTrue(partial_render["ok"])
        self.assertEqual(
            partial_render["pages"],
            [{"page": 1, "path": (Path("paper_pages") / "page_0001.png").as_posix()}],
        )
        self.assertIn("Only rendered 1 of 2", partial_render["warnings"][-1])

        self.assertFalse(server.list_paper_figures(str(self.test_runs_root / "missing.pdf"), run_id="run_fig_missing")["ok"])
        self.assertFalse(server.list_paper_visuals(str(self.test_runs_root / "missing.pdf"), run_id="run_vis_missing")["ok"])
        with patch.dict(server.os.environ, {server.ACTIVE_RUN_ID_ENV: "active_run"}, clear=False):
            self.assertFalse(server.list_paper_figures(str(pdf_path), run_id="other_run")["ok"])
            self.assertFalse(server.list_paper_visuals(str(pdf_path), run_id="other_run")["ok"])
        self.assertFalse(server.write_model_xml("not xml", run_id="run_bad_xml")["ok"])
        self.assertFalse(server.write_model_xml(minimal_xml(), run_id="run_bad_file", file_name="../model.xml")["ok"])
        self.assertFalse(server.run_morpheus_model(str(self.test_runs_root / "missing.xml"), run_id="run_missing_xml")["ok"])

        run_id = "run_no_attempts"
        server._run_dir(run_id)
        self.assertFalse(server.capture_model_xml_version("../bad")["ok"])
        no_model = server.capture_model_xml_version(run_id)
        self.assertTrue(no_model["ok"])
        self.assertFalse(no_model["model_present"])
        self.assertFalse(server.summarize_morpheus_run(run_id)["ok"])
        self.assertFalse(server.sample_output_images(run_id)["ok"])
        self.assertFalse(server.evaluate_technical_run(run_id)["ok"])
        self.assertFalse(server.summarize_morpheus_run("../bad")["ok"])
        self.assertFalse(server.sample_output_images("../bad")["ok"])
        self.assertFalse(server.evaluate_technical_run("../bad")["ok"])
        self.assertFalse(server.read_file_text(str(self.test_runs_root / "missing.txt"))["ok"])

    def test_model_capture_and_run_error_branches_without_live_morpheus(self) -> None:
        run_id = "run_model_error_branches"
        run_path = server._run_dir(run_id)
        xml_path = run_path / "model.xml"
        xml_path.write_text(minimal_xml(), encoding="utf-8")
        version_dir = run_path / "xml_versions"
        version_dir.mkdir()
        (version_dir / "model_v001.xml").write_text(minimal_xml(), encoding="utf-8")

        unchanged = server.capture_model_xml_version(run_id)
        self.assertTrue(unchanged["ok"])
        self.assertFalse(unchanged["snapshot_created"])
        self.assertEqual(unchanged["xml_version_count"], 1)

        busy_attempt = server._attempt_dir(run_path, "attempt_001")
        busy_attempt.mkdir(parents=True)
        (busy_attempt / "old.txt").write_text("busy", encoding="utf-8")
        busy = server.run_morpheus_model(str(xml_path), run_id=run_id, attempt_id="attempt_001")
        self.assertFalse(busy["ok"])
        self.assertIn("already exists", busy["error"])

        outside_xml = self.test_runs_root / "outside_model.xml"
        outside_xml.write_text(minimal_xml(), encoding="utf-8")
        with patch.dict(server.os.environ, {server.ACTIVE_RUN_ID_ENV: run_id}, clear=False):
            outside = server.run_morpheus_model(str(outside_xml), run_id=run_id)
        self.assertFalse(outside["ok"])
        self.assertIn("inside the active benchmark run directory", outside["error"])
        invalid_run_id = server.run_morpheus_model(str(xml_path), run_id="../bad")
        self.assertFalse(invalid_run_id["ok"])
        self.assertIn("Invalid run_id", invalid_run_id["error"])

        with patch.object(server, "_run_cmd", side_effect=FileNotFoundError()):
            missing_binary = server.run_morpheus_model(str(xml_path), run_id=run_id, attempt_id="attempt_002")
        self.assertFalse(missing_binary["ok"])
        self.assertIn("Morpheus binary not found", missing_binary["error"])

        with patch.dict(server.os.environ, {"MORPHEUS_RUN_TIMEOUT_MS": "bad"}, clear=False), patch.object(
            server,
            "_run_cmd",
            side_effect=RuntimeError("runner boom"),
        ):
            generic_failure = server.run_morpheus_model(str(xml_path), run_id=run_id, attempt_id="attempt_003")
        self.assertFalse(generic_failure["ok"])
        self.assertEqual(generic_failure["error"], "runner boom")

    def test_sample_images_contact_sheet_and_evaluation_read_attempt_history(self) -> None:
        run_id = "run_success_helpers"
        run_path = server._run_dir(run_id)
        (run_path / "paper.txt").write_text("cellular potts diffusion", encoding="utf-8")
        (run_path / "model.xml").write_text(minimal_xml(), encoding="utf-8")
        attempt_path = server._attempt_dir(run_path, "attempt_001")
        attempt_path.mkdir(parents=True)
        (attempt_path / "model.xml").write_text(minimal_xml(), encoding="utf-8")
        (attempt_path / "stdout.log").write_text("Time: 0\nTime: 500\n", encoding="utf-8")
        (attempt_path / "stderr.log").write_text("", encoding="utf-8")
        (attempt_path / "plot_00500.png").write_bytes(b"png")
        (attempt_path / "logger.csv").write_text("time\n500\n", encoding="utf-8")
        (attempt_path / "model_graph.dot").write_text("digraph G {}", encoding="utf-8")
        server._merge_manifest(
            run_id,
            {"attempt_history": [{"attempt_id": "attempt_001", "returncode": 2, "timed_out": True}]},
        )

        with patch.object(server, "_create_contact_sheet", return_value=attempt_path / "sample_contact_sheet.png"):
            sample = server.sample_output_images(run_id, create_contact_sheet=True)
        self.assertTrue(sample["ok"])
        self.assertEqual(
            sample["contact_sheet_path"],
            (Path("attempts") / "attempt_001" / "sample_contact_sheet.png").as_posix(),
        )

        evaluation = server.evaluate_technical_run(run_id)
        self.assertEqual(evaluation["returncode"], 2)
        self.assertTrue(evaluation["timed_out"])
        self.assertIn("nonzero exit code 2", evaluation["warnings"][0])

    def test_reference_tools_reject_missing_and_escaping_paths(self) -> None:
        refs_root = self.test_runs_root / "refs"
        category_dir = refs_root / "Custom"
        category_dir.mkdir(parents=True)
        (category_dir / "example.xml").write_text(minimal_xml(), encoding="utf-8")
        outside_file = self.test_runs_root / "outside.xml"
        outside_file.write_text(minimal_xml(), encoding="utf-8")

        with patch.object(server, "REFERENCES_ROOT", refs_root), patch.object(
            server,
            "REFERENCE_CATEGORIES",
            {"Custom": category_dir, "Outside": outside_file},
        ):
            self.assertEqual(server.list_references("Custom")["categories"], {"Custom": ["example.xml"]})
            self.assertTrue(server.read_reference("Custom", "example.xml")["ok"])
            self.assertFalse(server.read_reference("Missing", "example.xml")["ok"])
            self.assertFalse(server.read_reference("Custom", "missing.xml")["ok"])
            self.assertFalse(server.read_reference("Outside", "wrong.xml")["ok"])
            self.assertFalse(server.read_reference("Outside", "outside.xml")["ok"])

    def test_run_morpheus_model_uses_thread_env_default(self) -> None:
        run_id = "run_threads"
        run_path = server._run_dir(run_id)
        xml_path = run_path / "model.xml"
        xml_path.write_text(minimal_xml(stop_time="500"), encoding="utf-8")
        captured_commands: list[list[str]] = []

        def fake_run_cmd(command: list[str], **_kwargs: object) -> dict[str, object]:
            captured_commands.append(command)
            return {
                "returncode": 0,
                "stdout": "Time: 0\nTime: 500\n",
                "stderr": "",
                "command": command,
                "timed_out": False,
                "timeout_s": 1,
            }

        with patch.dict(server.os.environ, {"MORPHEUS_NUM_THREADS": "4"}, clear=False):
            with patch.object(server, "_run_cmd", side_effect=fake_run_cmd):
                result = server.run_morpheus_model(
                    xml_path=str(xml_path),
                    run_id=run_id,
                    timeout_ms=1,
                )

        self.assertTrue(result["ok"])
        self.assertIn("--num-threads", captured_commands[0])
        self.assertEqual(captured_commands[0][captured_commands[0].index("--num-threads") + 1], "4")

    def test_run_morpheus_model_requests_bounded_log_capture_and_records_metadata(self) -> None:
        run_id = "run_bounded_logs"
        run_path = server._run_dir(run_id)
        xml_path = run_path / "model.xml"
        xml_path.write_text(minimal_xml(stop_time="500"), encoding="utf-8")
        captured_kwargs: list[dict[str, object]] = []
        expected_cap = 10 * 1024 * 1024

        def fake_run_cmd(command: list[str], **kwargs: object) -> dict[str, object]:
            captured_kwargs.append(kwargs)
            return {
                "returncode": 0,
                "stdout": "START\n[... command output truncated ...]\nEND\n",
                "stderr": "",
                "command": command,
                "timed_out": False,
                "timeout_s": 1,
                "stdout_truncated": True,
                "stderr_truncated": False,
                "stdout_bytes": expected_cap + 1,
                "stderr_bytes": 0,
            }

        with patch.object(server, "_run_cmd", side_effect=fake_run_cmd):
            result = server.run_morpheus_model(
                xml_path=str(xml_path),
                run_id=run_id,
                timeout_ms=1,
            )

        manifest = json.loads((run_path / "run_manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(result["ok"])
        self.assertEqual(captured_kwargs[0]["max_output_bytes"], expected_cap)
        self.assertTrue(result["stdout_truncated"])
        self.assertTrue(manifest["latest_attempt_stdout_truncated"])
        self.assertGreater(manifest["latest_attempt_stdout_bytes"], expected_cap)

    def test_run_cmd_caps_stdout_and_stderr_with_tail_preserved(self) -> None:
        work_dir = self.test_runs_root / "bounded_subprocess"
        work_dir.mkdir(parents=True, exist_ok=True)
        script = work_dir / "emit_large_output.py"
        script.write_text(
            "\n".join(
                [
                    "import sys",
                    "sys.stdout.write('OUT-START-' + ('A' * 2000) + '-OUT-END')",
                    "sys.stderr.write('ERR-START-' + ('B' * 2000) + '-ERR-END')",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        result = server._run_cmd([sys.executable, str(script)], cwd=work_dir, timeout_s=5, max_output_bytes=256)

        self.assertFalse(result["timed_out"])
        self.assertTrue(result["stdout_truncated"])
        self.assertTrue(result["stderr_truncated"])
        self.assertIn("OUT-START", result["stdout"])
        self.assertIn("OUT-END", result["stdout"])
        self.assertNotIn("A" * 500, result["stdout"])
        self.assertIn("ERR-START", result["stderr"])
        self.assertIn("ERR-END", result["stderr"])
        self.assertIn("truncated", result["stdout"])
        self.assertIn("truncated", result["stderr"])

    def test_run_cmd_timeout_terminates_spawned_child_process(self) -> None:
        work_dir = self.test_runs_root / "subprocess_timeout"
        work_dir.mkdir(parents=True, exist_ok=True)
        pid_path = work_dir / "child.pid"
        child_script = work_dir / "child.py"
        child_script.write_text("import time\nwhile True:\n    time.sleep(1)\n", encoding="utf-8")
        parent_script = work_dir / "parent.py"
        parent_script.write_text(
            "\n".join(
                [
                    "from pathlib import Path",
                    "import subprocess",
                    "import sys",
                    "import time",
                    f"child = subprocess.Popen([sys.executable, {str(child_script)!r}], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)",
                    f"Path({str(pid_path)!r}).write_text(str(child.pid), encoding='utf-8')",
                    "while True:",
                    "    time.sleep(1)",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        result = server._run_cmd([sys.executable, str(parent_script)], cwd=work_dir, timeout_s=1)
        deadline = time.time() + 2
        while not pid_path.exists() and time.time() < deadline:
            time.sleep(0.05)

        child_pid = int(pid_path.read_text(encoding="utf-8"))
        child_survived = self._pid_exists(child_pid)
        try:
            self.assertTrue(result["timed_out"])
            self.assertFalse(child_survived, f"child process survived timed-out command: pid={child_pid}")
        finally:
            if child_survived:
                self._terminate_pid(child_pid)

    @staticmethod
    def _pid_exists(pid: int) -> bool:
        if sys.platform == "win32":
            import ctypes

            process_query_limited_information = 0x1000
            still_active = 259
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return False
                return exit_code.value == still_active
            finally:
                kernel32.CloseHandle(handle)
        try:
            os.kill(pid, 0)
            return True
        except PermissionError:
            return True
        except OSError:
            return False

    @staticmethod
    def _terminate_pid(pid: int) -> None:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return

    def test_capture_model_xml_version_creates_host_snapshot_for_external_edits(self) -> None:
        run_id = "run_capture"
        write_result = server.write_model_xml(xml_content=minimal_xml(stop_time="100"), run_id=run_id)
        self.assertTrue(write_result["ok"])

        run_path = server._run_dir(run_id)
        (run_path / "model.xml").write_text(minimal_xml(stop_time="200"), encoding="utf-8")

        capture = server.capture_model_xml_version(run_id=run_id, reason="cycle_01_main_turn")
        manifest = json.loads((run_path / "run_manifest.json").read_text(encoding="utf-8"))

        self.assertTrue(capture["ok"])
        self.assertTrue(capture["snapshot_created"])
        self.assertEqual(capture["xml_version_count"], 2)
        self.assertTrue((run_path / "xml_versions" / "model_v002.xml").exists())
        self.assertEqual(manifest["last_host_captured_xml_version"]["reason"], "cycle_01_main_turn")
        self.assertEqual(len(manifest["host_captured_xml_versions"]), 1)


if __name__ == "__main__":
    unittest.main()
