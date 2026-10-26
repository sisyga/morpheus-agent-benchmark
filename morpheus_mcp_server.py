from __future__ import annotations

import json
import math
import os
import re
import signal
import shutil
import subprocess
import time
import uuid
import hashlib
import xml.etree.ElementTree as ET
from functools import lru_cache
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from morpheus_process import run_bounded_command

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args: Any, **kwargs: Any) -> bool:
        return False

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    class FastMCP:  # type: ignore[override]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.kwargs = kwargs

        def tool(self):
            def decorator(func):
                return func

            return decorator

        def run(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("mcp is not installed. Run 'uv sync --locked' before starting the MCP server.")

try:
    import xmlschema as xmlschema_lib
except ImportError:
    xmlschema_lib = None

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent
RUNS_ROOT = Path(os.getenv("MORPHEUS_RUNS_DIR", REPO_ROOT / "runs")).expanduser()
RUNS_ROOT.mkdir(parents=True, exist_ok=True)
ACTIVE_RUN_ID_ENV = "MORPHEUS_ACTIVE_RUN_ID"
BENCHMARK_DEADLINE_PATH_ENV = "BENCHMARK_DEADLINE_PATH"

DEFAULT_XML_SCHEMA_PATH = REPO_ROOT / "src" / "benchmark" / "MorpheusML.xsd"
DEFAULT_MORPHEUS_RUN_TIMEOUT_MS = 3_600_000
MORPHEUS_LOG_CAPTURE_MAX_BYTES = 10 * 1024 * 1024
MORPHEUS_TIMEOUT_EXIT_CODE = 124
MORPHEUS_FINALIZATION_EXIT_CODE = 125
MORPHEUS_BIN = os.getenv("MORPHEUS_BIN", "morpheus")
MAX_TEXT_PREVIEW = 1_000
MAX_READ_CHARS = 50_000
MAX_REFERENCE_READ_CHARS = 250_000
MAX_LOG_PREVIEW_CHARS = 1_500
MAX_COMPACT_LOG_PREVIEW_CHARS = 600
MAX_COMPACT_ERRORS = 5
MAX_OUTPUT_PATHS = 6
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
ATTEMPT_ID_PATTERN = re.compile(r"^attempt_(\d{3})$")
FIGURE_CAPTION_PATTERN = re.compile(r"\bfig(?:ure)?\.?\s*[A-Za-z]?\s*\d+", re.IGNORECASE)
FIGURE_LABEL_PATTERN = re.compile(r"^\s*(fig(?:ure)?\.?\s*[A-Za-z]?\d+[A-Za-z]?)", re.IGNORECASE)
TABLE_LABEL_PATTERN = re.compile(r"^\s*((?:table|tab\.)\s*[A-Za-z]?\d+[A-Za-z]?)", re.IGNORECASE)
SUPPLEMENTARY_TABLE_LABEL_PATTERN = re.compile(r"^\s*(s\d+\s+note\s+table\s+[A-Za-z0-9]+)", re.IGNORECASE)
TABLE_LABEL_ANYWHERE_PATTERN = re.compile(r"((?:table|tab\.)\s*[A-Za-z]?\d+[A-Za-z]?)", re.IGNORECASE)

REFERENCES_ROOT = REPO_ROOT / ".agents" / "skills" / "morpheus" / "references"
REFERENCE_CATEGORIES = {
    "CPM": REFERENCES_ROOT / "cpm-examples.md",
    "PDE": REFERENCES_ROOT / "pde-examples.md",
    "ODE": REFERENCES_ROOT / "ode-examples.md",
    "Multiscale": REFERENCES_ROOT / "multiscale-examples.md",
    "Miscellaneous": REFERENCES_ROOT / "miscellaneous-examples.md",
}

MORPHEUS_MCP_INSTRUCTIONS = """
Morpheus MCP helps agents create, translate, run, and debug MorpheusML models.
Ground model design in the user's paper, notes, existing XML, and generated outputs;
identify the source model class; use reference examples as structural templates; write
valid MorpheusML; run Morpheus; inspect logs, CSVs, plots, and sampled PNG outputs;
then revise conservatively. Prefer biologically meaningful mechanisms over visual-only
shortcuts. Use reference tools before inventing syntax. When images matter, use
sample_output_images to locate PNGs/contact sheets and inspect them with an image-capable
tool when available.
""".strip()

mcp = FastMCP(name="morpheus-mcp", instructions=MORPHEUS_MCP_INSTRUCTIONS)

MCP_EXPOSED_TOOL_NAMES = frozenset(
    {
        "render_pdf_pages",
        "list_references",
        "read_reference",
        "write_model_xml",
        "run_morpheus_model",
        "summarize_morpheus_run",
        "sample_output_images",
        "evaluate_technical_run",
        "read_file_text",
    }
)
MCP_HIDDEN_TOOL_NAMES = frozenset(
    {
        "create_run",
        "extract_paper_text",
        "list_paper_figures",
        "list_paper_visuals",
        "validate_model_xml",
        "capture_model_xml_version",
        "read_pdf",
    }
)
_MCP_REGISTERED_TOOL_NAMES: List[str] = []
MCP_REGISTERED_TOOL_NAMES: Tuple[str, ...] = ()


def benchmark_mcp_tool(func):
    tool_name = func.__name__
    if tool_name in MCP_HIDDEN_TOOL_NAMES:
        return func
    if tool_name not in MCP_EXPOSED_TOOL_NAMES:
        raise RuntimeError(f"Unclassified Morpheus MCP tool: {tool_name}")
    _MCP_REGISTERED_TOOL_NAMES.append(tool_name)
    return mcp.tool()(func)


def _now_iso() -> str:
    return datetime.now().isoformat()


def _now_epoch_ms() -> int:
    return int(time.time() * 1000)


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _new_run_id() -> str:
    return f"{_now_stamp()}_{uuid.uuid4().hex[:8]}"


def _active_run_id() -> Optional[str]:
    run_id = os.getenv(ACTIVE_RUN_ID_ENV, "").strip()
    return run_id or None


def _sanitize_run_name(name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")
    return sanitized or "run"


def _validate_run_id(run_id: str) -> str:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(
            f"Invalid run_id {run_id!r}. Run IDs may only contain letters, numbers, underscores, and hyphens."
        )
    return run_id


def _coerce_run_id(run_id: Optional[str]) -> str:
    active_run_id = _active_run_id()
    if active_run_id:
        _validate_run_id(active_run_id)
        if run_id and run_id != active_run_id:
            raise ValueError(
                f"Active benchmark run is {active_run_id!r}; received run_id {run_id!r}. "
                "Use the active run_id exactly and do not create paper-specific output folders."
            )
        return active_run_id

    if run_id is None:
        return _new_run_id()
    return _validate_run_id(run_id)


def _run_dir(run_id: str) -> Path:
    run_id = _validate_run_id(run_id)
    run_path = (RUNS_ROOT / run_id).resolve()
    runs_root = RUNS_ROOT.resolve()
    if run_path != runs_root and runs_root not in run_path.parents:
        raise ValueError(f"Resolved run directory escapes the configured runs root: {run_path}")
    run_path.mkdir(parents=True, exist_ok=True)
    return run_path


def _is_within(root: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _resolve_run_file_path(run_path: Path, requested_path: str) -> Path:
    if not requested_path or not requested_path.strip():
        raise ValueError("file_name must not be empty")

    raw_path = Path(requested_path).expanduser()
    resolved = raw_path.resolve() if raw_path.is_absolute() else (run_path / raw_path).resolve()
    if not _is_within(run_path, resolved):
        raise ValueError("file_name must stay within the run directory")
    if resolved.exists() and resolved.is_dir():
        raise ValueError("file_name must point to a file, not a directory")
    return resolved


def _allowed_read_roots() -> List[Path]:
    active_run_id = _active_run_id()
    if active_run_id:
        return [_run_dir(active_run_id).resolve(), REFERENCES_ROOT.resolve()]
    return [RUNS_ROOT.resolve(), REFERENCES_ROOT.resolve()]


def _resolve_allowed_read_path(requested_path: str) -> Path:
    if not requested_path or not requested_path.strip():
        raise ValueError("path must not be empty")

    raw_path = Path(requested_path).expanduser()
    if raw_path.is_absolute():
        candidates = [raw_path.resolve()]
    else:
        active_run_id = _active_run_id()
        candidates = [
            (REPO_ROOT / raw_path).resolve(),
            *(
                [(RUNS_ROOT / active_run_id / raw_path).resolve()]
                if active_run_id
                else []
            ),
            (RUNS_ROOT / raw_path).resolve(),
            (REFERENCES_ROOT / raw_path).resolve(),
        ]

    for candidate in candidates:
        if any(_is_within(root, candidate) for root in _allowed_read_roots()):
            return candidate

    allowed_roots = ", ".join(str(root) for root in _allowed_read_roots())
    raise ValueError(
        f"Invalid path: {requested_path}. read_file_text only allows files inside {allowed_roots}"
    )


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _write_text(path: Path, text: str) -> None:
    _ensure_parent(path)
    path.write_text(text, encoding="utf-8", errors="ignore")


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    _ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_text(path: Path, max_chars: int = MAX_READ_CHARS) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]


def _read_text_tail(path: Path, max_chars: int = MAX_LOG_PREVIEW_CHARS) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _read_text_full(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _manifest_path(run_id: str) -> Path:
    return _run_dir(run_id) / "run_manifest.json"


def _load_manifest(run_id: str) -> Dict[str, Any]:
    manifest_path = _manifest_path(run_id)
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "run_id": run_id,
        "run_dir": str(_run_dir(run_id)),
        "created_at": _now_iso(),
    }


def _merge_manifest(run_id: str, updates: Dict[str, Any]) -> Path:
    manifest_path = _manifest_path(run_id)
    manifest = _load_manifest(run_id)
    manifest.update(updates)
    _write_json(manifest_path, manifest)
    return manifest_path


def _append_manifest_event(run_id: str, key: str, entry: Dict[str, Any]) -> Path:
    manifest_path = _manifest_path(run_id)
    manifest = _load_manifest(run_id)
    existing = manifest.get(key)
    if not isinstance(existing, list):
        existing = []
    existing.append(entry)
    manifest[key] = existing
    _write_json(manifest_path, manifest)
    return manifest_path


def _list_outputs(run_path: Path) -> Dict[str, List[str]]:
    return {
        "png": sorted(str(path) for path in run_path.rglob("*.png")),
        "csv": sorted(str(path) for path in run_path.rglob("*.csv")),
        "xml": sorted(str(path) for path in run_path.rglob("*.xml")),
        "dot": sorted(str(path) for path in run_path.rglob("*.dot")),
        "log": sorted(str(path) for path in run_path.rglob("*.log")),
    }


def _relative_to_run(run_path: Path, target: Path) -> str:
    try:
        return target.resolve().relative_to(run_path.resolve()).as_posix()
    except Exception:
        return target.as_posix()


def _sample_paths(run_path: Path, paths: Sequence[str], limit: int = MAX_OUTPUT_PATHS) -> List[str]:
    sampled = [Path(path) for path in paths[:limit]]
    return [_relative_to_run(run_path, path) for path in sampled]


def _last_relative(run_path: Path, paths: Sequence[str]) -> Optional[str]:
    if not paths:
        return None
    return _relative_to_run(run_path, Path(paths[-1]))


def _output_counts(outputs: Dict[str, List[str]]) -> Dict[str, int]:
    return {key: len(value) for key, value in outputs.items()}


def _compact_list(values: Sequence[str], limit: int = MAX_COMPACT_ERRORS) -> List[str]:
    return list(values[:limit])


def _compact_validation(validation: Dict[str, Any]) -> Dict[str, Any]:
    errors = validation.get("errors") if isinstance(validation.get("errors"), list) else []
    warnings = validation.get("warnings") if isinstance(validation.get("warnings"), list) else []
    schema_errors = validation.get("schema_errors") if isinstance(validation.get("schema_errors"), list) else []
    required_section_errors = (
        validation.get("required_section_errors")
        if isinstance(validation.get("required_section_errors"), list)
        else []
    )
    return {
        "valid": bool(validation.get("valid")),
        "graph_generation_ready": bool(validation.get("graph_generation_ready")),
        "schema_validation_enabled": bool(validation.get("schema_validation_enabled")),
        "schema_valid": validation.get("schema_valid"),
        "error_count": len(errors),
        "errors": _compact_list(errors),
        "warning_count": len(warnings),
        "warnings": _compact_list(warnings),
        "schema_error_count": len(schema_errors),
        "schema_errors": _compact_list(schema_errors),
        "required_section_errors": required_section_errors,
        "checks": {
            key: bool(validation.get(key))
            for key in [
                "has_root",
                "has_version",
                "has_description",
                "has_space",
                "has_time",
                "has_analysis",
                "has_gnuplotter",
                "has_logger",
                "has_model_graph",
            ]
        },
    }


def _read_compact_tail(path: Path, max_chars: int = MAX_COMPACT_LOG_PREVIEW_CHARS) -> str:
    return _read_text_tail(path, max_chars=max_chars)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _time_progress_summary(stdout_text: str) -> Dict[str, Any]:
    time_lines, time_values = _count_time_lines(stdout_text)
    return {
        "time_lines_count": time_lines,
        "first_time_value": time_values[0] if time_values else None,
        "last_time_value": time_values[-1] if time_values else None,
    }


def _validate_attempt_id(attempt_id: str) -> str:
    if not ATTEMPT_ID_PATTERN.fullmatch(attempt_id):
        raise ValueError("attempt_id must match attempt_###, for example attempt_001")
    return attempt_id


def _attempts_root(run_path: Path) -> Path:
    attempts_root = run_path / "attempts"
    attempts_root.mkdir(parents=True, exist_ok=True)
    return attempts_root


def _existing_attempt_ids(run_path: Path) -> List[str]:
    attempts_root = _attempts_root(run_path)
    attempts = [
        path.name
        for path in attempts_root.iterdir()
        if path.is_dir() and ATTEMPT_ID_PATTERN.fullmatch(path.name)
    ]
    return sorted(attempts)


def _next_attempt_id(run_path: Path) -> str:
    indices = [
        int(match.group(1))
        for attempt_id in _existing_attempt_ids(run_path)
        if (match := ATTEMPT_ID_PATTERN.fullmatch(attempt_id))
    ]
    next_index = (max(indices) if indices else 0) + 1
    return f"attempt_{next_index:03d}"


def _attempt_dir(run_path: Path, attempt_id: str) -> Path:
    attempt_id = _validate_attempt_id(attempt_id)
    attempt_path = (_attempts_root(run_path) / attempt_id).resolve()
    attempts_root = _attempts_root(run_path).resolve()
    if attempt_path != attempts_root and attempts_root not in attempt_path.parents:
        raise ValueError(f"Resolved attempt directory escapes the attempts root: {attempt_path}")
    return attempt_path


def _latest_attempt_id(run_id: str, run_path: Optional[Path] = None) -> Optional[str]:
    run_path = run_path or _run_dir(run_id)
    manifest = _load_manifest(run_id)
    latest_attempt_id = manifest.get("latest_attempt_id")
    if isinstance(latest_attempt_id, str):
        attempt_path = _attempt_dir(run_path, latest_attempt_id)
        if attempt_path.is_dir():
            return latest_attempt_id
    existing = _existing_attempt_ids(run_path)
    return existing[-1] if existing else None


def _resolve_attempt(run_id: str, run_path: Path, attempt_id: Optional[str]) -> Tuple[Optional[str], Optional[Path]]:
    resolved_attempt_id = _validate_attempt_id(attempt_id) if attempt_id else _latest_attempt_id(run_id, run_path)
    if not resolved_attempt_id:
        return None, None
    attempt_path = _attempt_dir(run_path, resolved_attempt_id)
    if not attempt_path.exists():
        return None, None
    return resolved_attempt_id, attempt_path


def _non_contact_sheet_pngs(paths: Sequence[str]) -> List[str]:
    return [path for path in paths if Path(path).name != "sample_contact_sheet.png"]


def _which(command: str) -> Optional[str]:
    return shutil.which(command)


def _integer_env(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= minimum else default


def _positive_int_or_none(value: Optional[Any]) -> Optional[int]:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _configured_xml_schema_path() -> Optional[Path]:
    raw = os.getenv("MORPHEUS_XML_SCHEMA_PATH", str(DEFAULT_XML_SCHEMA_PATH)).strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


@lru_cache(maxsize=4)
def _load_xml_schema(schema_path: str) -> Any:
    if xmlschema_lib is None:
        raise RuntimeError("xmlschema is not installed")
    return xmlschema_lib.XMLSchema11(schema_path, validation="lax")


def _run_cmd(
    command: Sequence[str],
    cwd: Optional[Path] = None,
    timeout_s: Optional[float] = None,
    max_output_bytes: Optional[int] = None,
) -> Dict[str, Any]:
    command_list = list(command)
    if max_output_bytes is not None:
        return _run_cmd_bounded(command_list, cwd=cwd, timeout_s=timeout_s, max_output_bytes=max_output_bytes)

    popen_kwargs: Dict[str, Any] = {
        "cwd": str(cwd) if cwd else None,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "ignore",
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True

    process = subprocess.Popen(command_list, **popen_kwargs)
    windows_job = _create_windows_kill_on_close_job(process) if os.name == "nt" else None
    try:
        stdout, stderr = process.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process, windows_job)
        windows_job = None
        try:
            stdout, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if process.poll() is None:
                process.kill()
        return {
            "returncode": None,
            "stdout": _trim_cmd_output(stdout),
            "stderr": _trim_cmd_output(stderr),
            "command": command_list,
            "timed_out": True,
            "timeout_s": timeout_s,
        }
    finally:
        if windows_job is not None:
            _close_windows_handle(windows_job)
    return {
        "returncode": process.returncode,
        "stdout": _trim_cmd_output(stdout),
        "stderr": _trim_cmd_output(stderr),
        "command": command_list,
        "timed_out": False,
        "timeout_s": timeout_s,
    }


def _run_cmd_bounded(
    command_list: List[str],
    cwd: Optional[Path] = None,
    timeout_s: Optional[float] = None,
    max_output_bytes: int = MORPHEUS_LOG_CAPTURE_MAX_BYTES,
) -> Dict[str, Any]:
    effective_timeout_s = timeout_s if timeout_s is not None else 24 * 60 * 60
    result = run_bounded_command(
        command_list,
        cwd=cwd,
        timeout_ms=max(1, math.ceil(effective_timeout_s * 1000)),
        max_output_bytes=max_output_bytes,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "command": result.command,
        "timed_out": result.timed_out,
        "timeout_s": timeout_s,
        "stdout_truncated": result.stdout_truncated,
        "stderr_truncated": result.stderr_truncated,
        "stdout_bytes": result.stdout_bytes,
        "stderr_bytes": result.stderr_bytes,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "duration_ms": result.duration_ms,
    }


def _terminate_process_tree(process: subprocess.Popen[str], windows_job: Optional[int] = None) -> None:
    if os.name == "nt":
        if windows_job is not None:
            _close_windows_handle(windows_job)
        if process.poll() is None:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if process.poll() is None:
                process.kill()
        return

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    if process.poll() is None:
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass

    if not _posix_process_group_exists(process.pid):
        return

    try:
        os.killpg(process.pid, getattr(signal, "SIGKILL", 9))
    except ProcessLookupError:
        return


def _posix_process_group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _create_windows_kill_on_close_job(process: subprocess.Popen[str]) -> Optional[int]:
    if os.name != "nt":
        return None

    import ctypes
    from ctypes import wintypes

    class IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JobObjectBasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class JobObjectExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JobObjectBasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    job_object_extended_limit_information = 9
    job_object_limit_kill_on_job_close = 0x2000
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None

    info = JobObjectExtendedLimitInformation()
    info.BasicLimitInformation.LimitFlags = job_object_limit_kill_on_job_close
    if not kernel32.SetInformationJobObject(
        job,
        job_object_extended_limit_information,
        ctypes.byref(info),
        ctypes.sizeof(info),
    ):
        _close_windows_handle(job)
        return None

    if not kernel32.AssignProcessToJobObject(job, int(process._handle)):
        _close_windows_handle(job)
        return None
    return int(job)


def _close_windows_handle(handle: int) -> None:
    if os.name != "nt":
        return
    import ctypes

    ctypes.windll.kernel32.CloseHandle(handle)


def _trim_cmd_output(output: Any) -> str:
    if isinstance(output, bytes):
        text = output.decode("utf-8", errors="ignore")
    else:
        text = output or ""
    if len(text) <= MAX_READ_CHARS:
        return text
    return text[-MAX_READ_CHARS:]


def _sanitize_xml(xml: str) -> str:
    xml = xml.strip()
    xml = re.sub(r"^\s*```xml\s*", "", xml, flags=re.IGNORECASE)
    xml = re.sub(r"\s*```\s*$", "", xml)
    return xml.strip()


def _looks_like_morpheus_xml(xml: str) -> bool:
    return "<MorpheusModel" in xml and "</MorpheusModel>" in xml


def _poppler_extract_text(pdf_path: Path) -> Optional[str]:
    if not _which("pdftotext"):
        return None
    result = _run_cmd(["pdftotext", "-layout", str(pdf_path), "-"])
    if result["returncode"] != 0 or not result["stdout"].strip():
        return None
    return result["stdout"]


def _python_extract_text(pdf_path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Could not extract PDF text. Install pypdf or provide Poppler's pdftotext."
        ) from exc

    reader = PdfReader(str(pdf_path))
    chunks: List[str] = []
    for page in reader.pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n\n".join(chunks).strip()


def _extract_pdf_text(pdf_path: Path) -> str:
    text = _poppler_extract_text(pdf_path)
    if text is not None:
        return text.strip()
    return _python_extract_text(pdf_path)


def _poppler_extract_page_texts(pdf_path: Path) -> Optional[List[str]]:
    if not _which("pdftotext"):
        return None
    result = _run_cmd(["pdftotext", "-layout", str(pdf_path), "-"])
    if result["returncode"] != 0 or not result["stdout"]:
        return None
    pages = result["stdout"].split("\f")
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    return [page.rstrip("\n") for page in pages]


def _python_extract_page_texts(pdf_path: Path) -> List[str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Could not extract per-page PDF text. Install pypdf or provide Poppler's pdftotext."
        ) from exc

    pages: List[str] = []
    reader = PdfReader(str(pdf_path))
    for page in reader.pages:
        try:
            pages.append((page.extract_text() or "").strip())
        except Exception:
            pages.append("")
    return pages


def _extract_pdf_page_texts(pdf_path: Path) -> Tuple[List[str], List[str]]:
    pages = _poppler_extract_page_texts(pdf_path)
    if pages is not None:
        return pages, []
    try:
        return _python_extract_page_texts(pdf_path), [
            "Poppler's pdftotext was unavailable; used pypdf page text extraction for visual detection.",
        ]
    except Exception as exc:
        return [], [str(exc)]


def _normalize_visual_label(raw_label: str) -> str:
    label = re.sub(r"\s+", " ", raw_label.strip())
    if label.lower().startswith("tab."):
        suffix = re.sub(r"^tab\.\s*", "", label, flags=re.IGNORECASE)
        return f"Table {suffix}"
    if label.lower().startswith("fig"):
        suffix = re.sub(r"^fig(?:ure)?\.?\s*", "", label, flags=re.IGNORECASE)
        return f"Figure {suffix}"
    return label


def _clean_caption_snippet(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip())


def _strip_leading_line_number(line: str) -> str:
    return re.sub(r"^\s*\d+\s+", "", line)


def _line_has_caption_tail(line: str, label_pattern: re.Pattern[str]) -> bool:
    label_match = label_pattern.match(line)
    if not label_match:
        return False
    remainder = line[label_match.end():].lstrip()
    if not remainder:
        return True
    if remainder[0] in ".:-–":
        return True
    for char in remainder:
        if char.isalpha():
            return char.isupper()
        if char in "([{" or char.isdigit():
            continue
        if char in "_/":
            return False
    return False


def _match_table_label_at_start(line: str) -> Optional[re.Match[str]]:
    normalized = _strip_leading_line_number(line)
    for pattern in (TABLE_LABEL_PATTERN, SUPPLEMENTARY_TABLE_LABEL_PATTERN):
        match = pattern.match(normalized)
        if match:
            return match
    return None


def _is_figure_caption_line(line: str) -> bool:
    return _line_has_caption_tail(line, FIGURE_LABEL_PATTERN)


def _is_table_caption_line(line: str) -> bool:
    normalized = _strip_leading_line_number(line)
    match = _match_table_label_at_start(normalized)
    if not match:
        return False
    remainder = normalized[match.end():].lstrip()
    if not remainder:
        return True
    if remainder[0] in ".:-–":
        return True
    for char in remainder:
        if char.isalpha():
            return char.isupper()
        if char in "([{" or char.isdigit():
            continue
        if char in "_/":
            return False
    return False


def _split_table_row_segments(line: str) -> List[str]:
    return [segment.strip() for segment in re.split(r"\s{2,}|\t+", line.strip()) if segment.strip()]


def _looks_like_table_value_segment(segment: str) -> bool:
    stripped = segment.strip()
    if not stripped:
        return False
    if re.search(r"\d", stripped):
        return True
    if re.fullmatch(r"[*†‡§¶]+", stripped):
        return True
    if stripped.startswith("(") and len(stripped) <= 40:
        return True
    if re.search(r"(μm|µm|hr|min|dimensionless|s-1|s−1|%)", stripped, re.IGNORECASE):
        return True
    return False


def _is_cell_like_segment(segment: str) -> bool:
    stripped = segment.strip()
    if not stripped:
        return False
    return len(stripped) <= 35 or _looks_like_table_value_segment(stripped)


def _has_cell_like_run(segments: Sequence[str], run_length: int = 3) -> bool:
    run = 0
    for segment in segments:
        if _is_cell_like_segment(segment):
            run += 1
            if run >= run_length:
                return True
        else:
            run = 0
    return False


def _is_table_like_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _is_table_caption_line(stripped):
        return False
    segments = _split_table_row_segments(stripped)
    if len(segments) >= 3 and _has_cell_like_run(segments, 3):
        return True
    if len(segments) >= 3 and len(segments[0]) <= 25 and _looks_like_table_value_segment(segments[-1]):
        return True
    if (
        len(segments) >= 2
        and len(segments[0]) <= 40
        and len(segments[1]) <= 25
        and _looks_like_table_value_segment(segments[1])
    ):
        return True
    return False


def _count_table_like_lines(lines: Sequence[str], caption_index: int, radius: int = 18) -> int:
    start = max(0, caption_index - radius)
    end = min(len(lines), caption_index + radius + 1)
    return sum(1 for idx in range(start, end) if idx != caption_index and _is_table_like_line(lines[idx]))


def _extract_visual_label(line: str, label_pattern: re.Pattern[str], fallback_prefix: str, page: int) -> str:
    match = label_pattern.match(line)
    if match:
        return _normalize_visual_label(match.group(1))
    return f"{fallback_prefix} page {page}"


def _base_table_label(label: str) -> str:
    return re.sub(r"\s*\((?:continued|preceding page)\)\s*$", "", label, flags=re.IGNORECASE)


def _extract_table_label_anywhere(text: str) -> Optional[str]:
    match = TABLE_LABEL_ANYWHERE_PATTERN.search(text)
    if not match:
        return None
    return _normalize_visual_label(match.group(1))


def _extract_right_column_table_caption(
    lines: Sequence[str],
    line_index: int,
) -> Optional[Tuple[str, str]]:
    segments = _split_table_row_segments(lines[line_index])
    for segment_index, segment in enumerate(segments):
        match = TABLE_LABEL_ANYWHERE_PATTERN.search(segment)
        if not match or match.start() != 0 or not _is_table_caption_line(segment):
            continue
        label = _normalize_visual_label(match.group(1))

        snippet_parts = [_clean_caption_snippet(segment)]
        for next_index in range(line_index + 1, min(len(lines), line_index + 3)):
            next_segments = _split_table_row_segments(lines[next_index])
            if segment_index >= len(next_segments):
                break
            candidate = next_segments[segment_index].strip()
            if not candidate or _extract_table_label_anywhere(candidate):
                break
            if _is_table_like_line(candidate):
                break
            if not any(char.isalpha() for char in candidate):
                break
            snippet_parts.append(candidate)
            break
        return label, _clean_caption_snippet(" ".join(snippet_parts))
    return None


def _extract_table_caption(lines: Sequence[str], line_index: int, page_index: int) -> Optional[Tuple[str, str]]:
    line = lines[line_index]
    if _is_table_caption_line(line):
        normalized = _strip_leading_line_number(line)
        label_match = _match_table_label_at_start(normalized)
        label = _normalize_visual_label(label_match.group(1)) if label_match else f"Table page {page_index}"
        return (label, _clean_caption_snippet(normalized))
    return _extract_right_column_table_caption(lines, line_index)


def _count_table_like_lines_near_top(lines: Sequence[str], limit: int = 24) -> int:
    return sum(1 for line in lines[:limit] if _is_table_like_line(line))


def _count_table_like_lines_near_bottom(lines: Sequence[str], limit: int = 12) -> int:
    return sum(1 for line in lines[-limit:] if _is_table_like_line(line))


def _caption_is_near_page_bottom(lines: Sequence[str], line_index: int, trailing_lines: int = 4) -> bool:
    return line_index >= max(0, len(lines) - trailing_lines)


def _page_looks_like_table_preceding_caption(lines: Sequence[str]) -> bool:
    if not lines:
        return False
    if any(_extract_table_caption(lines, idx, 1) for idx in range(max(0, len(lines) - 8), len(lines))):
        return False
    return _count_table_like_lines_near_bottom(lines) >= 2


def _page_looks_like_table_continuation(lines: Sequence[str]) -> bool:
    if not lines:
        return False
    if any(_extract_table_caption(lines, idx, 1) for idx in range(min(len(lines), 12))):
        return False
    return _count_table_like_lines_near_top(lines) >= 5


def _detect_table_items_from_page_texts(page_texts: Sequence[str]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    page_lines = [[line.rstrip() for line in page_text.splitlines() if line.strip()] for page_text in page_texts]
    table_items_by_page: Dict[int, List[Dict[str, Any]]] = {}
    caption_metadata_by_page: Dict[int, List[Dict[str, Any]]] = {}
    for page_index, lines in enumerate(page_lines, start=1):
        page_items: List[Dict[str, Any]] = []
        page_caption_metadata: List[Dict[str, Any]] = []
        for line_index, line in enumerate(lines):
            caption = _extract_table_caption(lines, line_index, page_index)
            if not caption:
                continue
            label, caption_snippet = caption
            support_count = _count_table_like_lines(lines, line_index)
            if support_count < 2:
                continue
            page_caption_metadata.append(
                {
                    "label": label,
                    "line_index": line_index,
                    "support_count": support_count,
                }
            )
            page_items.append(
                {
                    "kind": "table",
                    "label": label,
                    "page": page_index,
                    "caption_snippet": caption_snippet,
                    "detection_method": "layout_caption",
                    "confidence": "high" if support_count >= 3 else "medium",
                }
            )
        table_items_by_page[page_index] = page_items
        caption_metadata_by_page[page_index] = page_caption_metadata
        items.extend(page_items)

    for page_index, lines in enumerate(page_lines[1:], start=2):
        if table_items_by_page.get(page_index - 1):
            continue
        current_page_items = table_items_by_page.get(page_index, [])
        current_caption_metadata = caption_metadata_by_page.get(page_index, [])
        if len(current_page_items) != 1 or len(current_caption_metadata) != 1:
            continue
        current_caption = current_caption_metadata[0]
        if current_page_items[0]["detection_method"] != "layout_caption":
            continue
        if not _caption_is_near_page_bottom(lines, current_caption["line_index"]):
            continue
        if _count_table_like_lines_near_top(lines) < 2:
            continue

        previous_lines = page_lines[page_index - 2]
        if not _page_looks_like_table_preceding_caption(previous_lines):
            continue

        base_label = _base_table_label(current_page_items[0]["label"])
        preceding_item = {
            "kind": "table",
            "label": f"{base_label} (preceding page)",
            "page": page_index - 1,
            "caption_snippet": f"{base_label} (preceding page)",
            "detection_method": "table_preceding_page",
            "confidence": "medium",
        }
        table_items_by_page[page_index - 1] = [preceding_item]
        items.append(preceding_item)

    for page_index, lines in enumerate(page_lines[1:], start=2):
        if table_items_by_page.get(page_index):
            continue
        previous_page_items = table_items_by_page.get(page_index - 1, [])
        previous_labels = {_base_table_label(item["label"]) for item in previous_page_items}
        if len(previous_labels) != 1:
            continue
        if not _page_looks_like_table_continuation(lines):
            continue
        base_label = next(iter(previous_labels))
        continuation_item = {
            "kind": "table",
            "label": f"{base_label} (continued)",
            "page": page_index,
            "caption_snippet": f"{base_label} (continued)",
            "detection_method": "table_continuation",
            "confidence": "medium",
        }
        table_items_by_page[page_index] = [continuation_item]
        items.append(continuation_item)

    items.sort(key=lambda item: (item.get("page", 0), item.get("label", "")))
    return items


def _detect_figure_items_from_page_texts(
    page_texts: Sequence[str],
    figure_pages: Sequence[int],
    figure_method: str,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    figure_page_set = {page for page in figure_pages if isinstance(page, int)}
    caption_pages: set[int] = set()
    for page, page_text in enumerate(page_texts, start=1):
        lines = [line.rstrip() for line in page_text.splitlines() if line.strip()]
        page_items: List[Dict[str, Any]] = []
        detection_method = f"{figure_method}+caption" if page in figure_page_set else "caption_text"
        confidence = "high" if page in figure_page_set else "medium"
        for line in lines:
            if not _is_figure_caption_line(line):
                continue
            page_items.append(
                {
                    "kind": "figure",
                    "label": _extract_visual_label(line, FIGURE_LABEL_PATTERN, "Figure", page),
                    "page": page,
                    "caption_snippet": _clean_caption_snippet(line),
                    "detection_method": detection_method,
                    "confidence": confidence,
                }
            )
        if not page_items:
            continue
        caption_pages.add(page)
        items.extend(page_items)

    for page in sorted(figure_page_set - caption_pages):
        page_text = page_texts[page - 1] if 0 < page <= len(page_texts) else ""
        lines = [line.rstrip() for line in page_text.splitlines() if line.strip()]
        items.append(
            {
                "kind": "figure",
                "label": f"Figure page {page}",
                "page": page,
                "caption_snippet": "Likely figure page detected from embedded images or page graphics.",
                "detection_method": figure_method,
                "confidence": "medium",
            }
        )
    items.sort(key=lambda item: (item.get("page", 0), item.get("label", "")))
    return items


def _extract_visual_items_from_pdf(pdf_path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    page_texts, text_warnings = _extract_pdf_page_texts(pdf_path)
    warnings.extend(text_warnings)

    figures = _list_pdf_figures(pdf_path)
    figure_method = "pdfimages"
    if not figures:
        figure_method = "pymupdf_heuristic"
        figures, figure_warnings = _list_pdf_figures_with_pymupdf(pdf_path)
        warnings.extend(figure_warnings)
    figure_pages = sorted({figure["page"] for figure in figures if isinstance(figure.get("page"), int)})

    items = _detect_figure_items_from_page_texts(page_texts, figure_pages, figure_method)
    items.extend(_detect_table_items_from_page_texts(page_texts))
    items.sort(key=lambda item: (item.get("page", 0), item.get("kind", ""), item.get("label", "")))
    return items, warnings


def _render_with_poppler(
    pdf_path: Path,
    out_dir: Path,
    pages: Sequence[int],
    dpi: int,
) -> List[Path]:
    rendered: List[Path] = []
    if not _which("pdftoppm"):
        return rendered

    for page in pages:
        prefix = out_dir / f"page_{page:04d}"
        result = _run_cmd(
            [
                "pdftoppm",
                "-f",
                str(page),
                "-l",
                str(page),
                "-r",
                str(dpi),
                "-png",
                str(pdf_path),
                str(prefix),
            ]
        )
        if result["returncode"] != 0:
            continue
        candidates = sorted(out_dir.glob(f"{prefix.name}*.png"))
        if candidates:
            target = out_dir / f"page_{page:04d}.png"
            if candidates[0] != target:
                candidates[0].replace(target)
                for extra in candidates[1:]:
                    extra.unlink(missing_ok=True)
            if _is_nonempty_file(target):
                rendered.append(target)
    return rendered


def _is_nonempty_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _rendered_page_number(path: Path) -> Optional[int]:
    match = re.search(r"page_(\d{4})\.png$", path.name)
    return int(match.group(1)) if match else None


def _render_with_pymupdf(
    pdf_path: Path,
    out_dir: Path,
    pages: Sequence[int],
    dpi: int,
) -> List[Path]:
    try:
        import fitz  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Could not render PDF pages. Install PyMuPDF or provide Poppler's pdftoppm."
        ) from exc

    doc = fitz.open(str(pdf_path))
    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)
    rendered: List[Path] = []
    for page_num in pages:
        pix = doc.load_page(page_num - 1).get_pixmap(matrix=matrix, alpha=False)
        out_path = out_dir / f"page_{page_num:04d}.png"
        pix.save(str(out_path))
        if _is_nonempty_file(out_path):
            rendered.append(out_path)
    return rendered


def _render_pdf_pages(
    pdf_path: Path,
    out_dir: Path,
    pages: Sequence[int],
    dpi: int,
) -> List[Path]:
    rendered_by_page = {
        page: path
        for path in _render_with_poppler(pdf_path, out_dir, pages, dpi)
        if (page := _rendered_page_number(path)) is not None and _is_nonempty_file(path)
    }
    missing_pages = [page for page in pages if page not in rendered_by_page]
    if missing_pages:
        for path in _render_with_pymupdf(pdf_path, out_dir, missing_pages, dpi):
            page = _rendered_page_number(path)
            if page is not None and _is_nonempty_file(path):
                rendered_by_page[page] = path
    return [rendered_by_page[page] for page in pages if page in rendered_by_page]


def _parse_pdf_page_count(pdf_path: Path) -> int:
    if _which("pdfinfo"):
        result = _run_cmd(["pdfinfo", str(pdf_path)])
        if result["returncode"] == 0:
            for line in result["stdout"].splitlines():
                if line.startswith("Pages:"):
                    return int(line.split(":", 1)[1].strip())
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Could not determine PDF page count. Install pypdf or provide Poppler's pdfinfo."
        ) from exc
    return len(PdfReader(str(pdf_path)).pages)


def _parse_pdfimages_output(raw_output: str) -> List[Dict[str, Any]]:
    figures: List[Dict[str, Any]] = []
    lines = [line for line in raw_output.splitlines() if line.strip()]
    for line in lines[2:]:
        parts = re.split(r"\s+", line.strip())
        if len(parts) < 16:
            continue
        figures.append(
            {
                "page": int(parts[0]),
                "num": int(parts[1]),
                "type": parts[2],
                "width": int(parts[3]),
                "height": int(parts[4]),
                "color": parts[5],
                "encoding": parts[8],
                "object_id": f"{parts[10]} {parts[11]}",
                "x_ppi": int(parts[12]),
                "y_ppi": int(parts[13]),
                "size": parts[14],
                "ratio": parts[15],
            }
        )
    return figures


def _list_pdf_figures(pdf_path: Path) -> List[Dict[str, Any]]:
    if not _which("pdfimages"):
        return []
    result = _run_cmd(["pdfimages", "-list", str(pdf_path)])
    if result["returncode"] != 0:
        return []
    return _parse_pdfimages_output(result["stdout"])


def _list_pdf_figures_with_pymupdf(pdf_path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    try:
        import fitz  # type: ignore
    except ImportError:
        return [], ["PyMuPDF is not installed, so figure-page heuristic detection is unavailable."]

    warnings = [
        "pdfimages is unavailable or returned no figures; used PyMuPDF figure-page heuristics based on captions and page graphics."
    ]
    figures: List[Dict[str, Any]] = []
    doc = fitz.open(str(pdf_path))
    try:
        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            text = page.get_text("text") or ""
            caption_matches = FIGURE_CAPTION_PATTERN.findall(text)
            image_count = len(page.get_images(full=True))
            try:
                drawing_count = len(page.get_drawings())
            except Exception:
                drawing_count = 0
            has_figure_caption = len(caption_matches) > 0
            has_page_graphics = image_count > 0 or drawing_count > 0
            if not has_figure_caption or not has_page_graphics:
                continue
            figures.append(
                {
                    "page": page_index + 1,
                    "num": len(figures) + 1,
                    "type": "heuristic_page",
                    "width": page.rect.width,
                    "height": page.rect.height,
                    "caption_matches": caption_matches[:5],
                    "image_count": image_count,
                    "drawing_count": drawing_count,
                }
            )
    finally:
        doc.close()
    if not figures:
        warnings.append("No figure pages matched the fallback caption-and-graphics heuristic.")
    return figures, warnings


def _infer_reference_categories_from_text(text: str) -> Dict[str, Any]:
    lower = text.lower()
    scores = {"CPM": 0, "PDE": 0, "ODE": 0, "Multiscale": 0}

    cpm_keywords = [
        "cellular potts",
        "cpm",
        "adhesion",
        "contact energy",
        "surface constraint",
        "cell sorting",
        "motility",
    ]
    pde_keywords = [
        "reaction-diffusion",
        "diffusion",
        "morphogen",
        "concentration field",
        "gradient",
    ]
    ode_keywords = [
        "ode",
        "ordinary differential equation",
        "kinetic model",
        "gene regulatory",
        "signaling network",
    ]
    multiscale_keywords = [
        "multiscale",
        "hybrid",
        "cellular potts model",
        "chemokine",
        "feedback loop",
    ]

    scores["CPM"] += sum(keyword in lower for keyword in cpm_keywords)
    scores["PDE"] += sum(keyword in lower for keyword in pde_keywords)
    scores["ODE"] += sum(keyword in lower for keyword in ode_keywords)
    scores["Multiscale"] += sum(keyword in lower for keyword in multiscale_keywords)

    selected = [name for name, score in scores.items() if score > 0]
    if not selected:
        selected = ["Miscellaneous"]

    return {"scores": scores, "selected_categories": selected}


def _local_xml_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _format_xsd_error(error: Any) -> str:
    reason = getattr(error, "reason", None) or str(error).splitlines()[0]
    path_value = getattr(error, "path", None)
    return f"{path_value}: {reason}" if path_value else str(reason)


def _validate_xml_completeness(xml: str) -> Dict[str, Any]:
    cleaned = _sanitize_xml(xml)
    root: Optional[ET.Element] = None
    xml_parse_errors: List[str] = []
    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError as exc:
        xml_parse_errors.append(f"Malformed XML: {exc}")

    direct_children = {_local_xml_name(child.tag) for child in list(root)} if root is not None else set()
    has_root = root is not None and _local_xml_name(root.tag) == "MorpheusModel"
    has_description = has_root and "Description" in direct_children
    has_space = has_root and "Space" in direct_children
    has_time = has_root and "Time" in direct_children
    has_analysis = has_root and "Analysis" in direct_children
    has_version = has_root and root is not None and root.attrib.get("version") == "4"
    elements = list(root.iter()) if root is not None else []
    has_png_terminal = any(
        _local_xml_name(element.tag) == "Terminal" and element.attrib.get("name") == "png"
        for element in elements
    )
    checks = {
        "has_root": has_root,
        "has_description": has_description,
        "has_space": has_space,
        "has_time": has_time,
        "has_analysis": has_analysis,
        "has_gnuplotter": any(_local_xml_name(element.tag) == "Gnuplotter" for element in elements)
        and has_png_terminal,
        "has_logger": any(_local_xml_name(element.tag) == "Logger" for element in elements)
        and any(_local_xml_name(element.tag) == "TextOutput" for element in elements),
        "has_model_graph": any(_local_xml_name(element.tag) == "ModelGraph" for element in elements),
        "has_version": has_version,
    }

    required_section_errors: List[str] = []
    if not checks["has_root"]:
        required_section_errors.append("Missing MorpheusModel root element")
    if checks["has_root"] and not checks["has_version"]:
        required_section_errors.append('MorpheusModel must declare version="4"')
    if checks["has_root"] and not checks["has_description"]:
        required_section_errors.append("Missing required Description section")
    if checks["has_root"] and not checks["has_space"]:
        required_section_errors.append("Missing required Space section")
    if checks["has_root"] and not checks["has_time"]:
        required_section_errors.append("Missing required Time section")
    if checks["has_root"] and not checks["has_analysis"]:
        required_section_errors.append("Missing required Analysis section")

    warnings: List[str] = []
    if checks["has_analysis"] and not checks["has_gnuplotter"]:
        warnings.append("Analysis section is missing Gnuplotter PNG output")
    if checks["has_analysis"] and not checks["has_logger"]:
        warnings.append("Analysis section is missing Logger CSV output")
    if checks["has_analysis"] and not checks["has_model_graph"]:
        warnings.append("Analysis section is missing ModelGraph output")

    schema_path = _configured_xml_schema_path()
    schema_validation_enabled = False
    schema_valid: Optional[bool] = None
    schema_errors: List[str] = []
    if root is not None and schema_path is not None:
        if not schema_path.exists():
            warnings.append(f"MorpheusML XSD schema not found: {schema_path}")
        elif xmlschema_lib is None:
            warnings.append("xmlschema is not installed; skipped MorpheusML XSD validation")
        else:
            schema_validation_enabled = True
            try:
                schema = _load_xml_schema(str(schema_path))
                schema_errors = [_format_xsd_error(error) for error in schema.iter_errors(root)]
                schema_valid = len(schema_errors) == 0
            except Exception as exc:
                schema_valid = False
                schema_errors = [f"XSD validation failed: {exc}"]

    if schema_validation_enabled and schema_valid is False and not schema_errors:
        schema_errors.append("XML did not validate against the MorpheusML XSD")

    errors = [*xml_parse_errors, *required_section_errors]

    return {
        **checks,
        "valid": len(errors) == 0,
        "graph_generation_ready": checks["has_analysis"] and checks["has_gnuplotter"],
        "errors": errors,
        "warnings": warnings,
        "xml_parse_errors": xml_parse_errors,
        "schema_path": str(schema_path) if schema_path else None,
        "schema_validation_enabled": schema_validation_enabled,
        "schema_valid": schema_valid,
        "schema_errors": schema_errors,
        "required_section_errors": required_section_errors,
    }


def _extract_stop_time(xml_text: str) -> Optional[float]:
    patterns = [
        r'<StopTime\b[^>]*\bvalue\s*=\s*["\']?([\d.eE+-]+)["\']?[^>]*/?>',
        r'<StopTime[^>]*>([\d.eE+-]+)</StopTime>',
    ]
    for pattern in patterns:
        match = re.search(pattern, xml_text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return None


def _count_time_lines(stdout_text: str) -> Tuple[int, List[float]]:
    time_values: List[float] = []
    pattern = re.compile(r"^Time:\s*<?([\d.eE+-]+)>?", re.IGNORECASE)
    for line in stdout_text.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        try:
            time_values.append(float(match.group(1)))
        except ValueError:
            continue
    return len(time_values), time_values


def _calculate_time_score(time_line_count: int, stop_time_match: bool = False) -> int:
    if time_line_count == 0:
        return 0
    if time_line_count == 1:
        return 1
    if stop_time_match:
        return 3
    if 1 < time_line_count < 101:
        return 2
    return 3


def _count_error_lines(stderr_text: str) -> int:
    stderr_text = stderr_text.strip()
    if not stderr_text:
        return 0
    count = 0
    patterns = [r"\[ERROR\]", r"\[FATAL\]", r"Error:", r"error:", r"Exception"]
    for line in stderr_text.splitlines():
        if not line.strip():
            continue
        if any(re.search(pattern, line) for pattern in patterns):
            count += 1
    return count if count > 0 else len([line for line in stderr_text.splitlines() if line.strip()])


def _extract_time_from_png_name(path_value: Optional[str]) -> Optional[float]:
    if not path_value:
        return None
    match = re.search(r"_(\d+(?:\.\d+)?)\.png$", Path(path_value).name)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _pick_evenly_spaced(items: Sequence[Path], limit: int) -> List[Path]:
    if not items or limit <= 0:
        return []
    if len(items) <= limit:
        return list(items)
    if limit == 1:
        return [items[0]]

    indices = [0]
    for step in range(1, limit - 1):
        ratio = step / (limit - 1)
        indices.append(round(ratio * (len(items) - 1)))
    indices.append(len(items) - 1)

    ordered = sorted(set(indices))
    return [items[index] for index in ordered][:limit]


def _create_contact_sheet(image_paths: Sequence[Path], output_path: Path) -> Optional[Path]:
    if not image_paths:
        return None
    try:
        from PIL import Image, ImageOps  # type: ignore
    except ImportError:
        return None

    thumbs: List[Any] = []
    for path in image_paths:
        try:
            image = Image.open(path).convert("RGB")
            image.thumbnail((320, 320))
            thumbs.append(ImageOps.pad(image, (320, 320), color="white"))
        except Exception:
            continue

    if not thumbs:
        return None

    columns = min(3, len(thumbs))
    rows = math.ceil(len(thumbs) / columns)
    sheet = Image.new("RGB", (columns * 320, rows * 320), color="white")
    for index, thumb in enumerate(thumbs):
        x = (index % columns) * 320
        y = (index // columns) * 320
        sheet.paste(thumb, (x, y))
    _ensure_parent(output_path)
    sheet.save(output_path)
    return output_path


def _sample_run_images(run_path: Path, limit: int) -> Dict[str, Any]:
    pngs = sorted(path for path in run_path.rglob("*.png") if path.name != "sample_contact_sheet.png")
    primary = [path for path in pngs if path.name.startswith("plot_")]
    logger = [path for path in pngs if path.name.startswith("logger_")]

    selected_primary = _pick_evenly_spaced(primary, limit)
    selected_logger: List[Path] = []
    if logger:
        selected_logger.append(logger[0])
        if logger[-1] != logger[0]:
            selected_logger.append(logger[-1])

    selected = selected_primary + [path for path in selected_logger if path not in selected_primary]
    return {
        "all_png_count": len(pngs),
        "primary_plot_count": len(primary),
        "logger_plot_count": len(logger),
        "selected": selected,
    }


@benchmark_mcp_tool
def create_run(name: Optional[str] = None) -> Dict[str, Any]:
    active_run_id = _active_run_id()
    if active_run_id:
        run_id = _validate_run_id(active_run_id)
        run_path = _run_dir(run_id)
        manifest_path = _merge_manifest(
            run_id,
            {
                "run_id": run_id,
                "run_dir": str(run_path),
                "runs_root": str(RUNS_ROOT),
            },
        )
        return {
            "ok": True,
            "run_id": run_id,
            "run_dir": str(run_path),
            "runs_root": str(RUNS_ROOT),
            "run_manifest_path": str(manifest_path),
            "note": "Using the active benchmark run; create_run is a no-op inside benchmark cycles.",
        }

    if name:
        sanitized_name = _sanitize_run_name(name)
        existing_path = RUNS_ROOT / sanitized_name
        run_id = sanitized_name if existing_path.is_dir() else f"{_now_stamp()}_{sanitized_name}"
    else:
        run_id = _new_run_id()

    run_path = _run_dir(run_id)
    manifest_path = _merge_manifest(
        run_id,
        {
            "run_id": run_id,
            "run_dir": str(run_path),
            "created_at": _now_iso(),
            "runs_root": str(RUNS_ROOT),
        },
    )
    return {
        "ok": True,
        "run_id": run_id,
        "run_dir": str(run_path),
        "runs_root": str(RUNS_ROOT),
        "run_manifest_path": str(manifest_path),
    }


@benchmark_mcp_tool
def extract_paper_text(pdf_path: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    """Extract text from a paper PDF into paper.txt and suggest reference categories.

    Use this for text grounding before parameter recovery or model design. Prefer
    rendering only selected pages separately when visual inspection is needed.
    """
    pdf_file = Path(pdf_path).expanduser().resolve()
    if not pdf_file.exists():
        return {"ok": False, "error": f"PDF not found: {pdf_path}"}

    try:
        run_id = _coerce_run_id(run_id)
        run_path = _run_dir(run_id)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    try:
        text = _extract_pdf_text(pdf_file)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    if not text.strip():
        return {"ok": False, "error": "No text could be extracted from PDF"}

    text_path = run_path / "paper.txt"
    _write_text(text_path, text)

    page_count = _parse_pdf_page_count(pdf_file)
    suggestions = _infer_reference_categories_from_text(text[:50_000])
    manifest_path = _merge_manifest(
        run_id,
        {
            "paper_pdf_path": str(pdf_file),
            "paper_text_path": str(text_path),
            "paper_page_count": page_count,
            "reference_suggestions": suggestions,
        },
    )

    return {
        "ok": True,
        "run_id": run_id,
        "run_dir": str(run_path),
        "pdf_path": str(pdf_file),
        "text_path": str(text_path),
        "page_count": page_count,
        "text_preview": text[:MAX_TEXT_PREVIEW],
        "reference_suggestions": suggestions,
        "run_manifest_path": str(manifest_path),
    }


def _normalize_page_request(
    total_pages: int,
    pages: Optional[List[int]],
    max_pages: Optional[int],
) -> Tuple[Optional[List[int]], List[int], List[str]]:
    warnings: List[str] = []
    requested_pages = list(pages) if pages is not None else None
    selected_pages = requested_pages or list(range(1, total_pages + 1))
    out_of_range_pages = [page for page in selected_pages if page < 1 or page > total_pages]
    if out_of_range_pages:
        warnings.append(
            f"Ignored out-of-range pages: {', '.join(str(page) for page in sorted(set(out_of_range_pages)))}."
        )
    selected_pages = [page for page in selected_pages if 1 <= page <= total_pages]
    if max_pages is not None and len(selected_pages) > max_pages:
        warnings.append(f"Truncated page render request to max_pages={max_pages}.")
        selected_pages = selected_pages[:max_pages]
    return requested_pages, selected_pages, warnings


@benchmark_mcp_tool
def render_pdf_pages(
    pdf_path: str,
    run_id: Optional[str] = None,
    pages: Optional[List[int]] = None,
    dpi: int = 150,
    max_pages: Optional[int] = None,
) -> Dict[str, Any]:
    """Render selected PDF pages to PNG files inside the run directory.

    Prefer calling list_paper_visuals first, then render only the specific figure
    or table pages that matter instead of rendering the whole paper.
    """
    pdf_file = Path(pdf_path).expanduser().resolve()
    if not pdf_file.exists():
        return {"ok": False, "error": f"PDF not found: {pdf_path}"}

    try:
        run_id = _coerce_run_id(run_id)
        run_path = _run_dir(run_id)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    out_dir = run_path / "paper_pages"
    out_dir.mkdir(parents=True, exist_ok=True)

    total_pages = _parse_pdf_page_count(pdf_file)
    requested_pages, selected_pages, warnings = _normalize_page_request(total_pages, pages, max_pages)
    if requested_pages is not None and not selected_pages:
        return {
            "ok": False,
            "error": f"None of the requested pages are within the PDF page range 1..{total_pages}.",
            "run_id": run_id,
            "pdf_path": str(pdf_file),
            "total_pages": total_pages,
            "requested_pages": requested_pages,
            "selected_pages": selected_pages,
            "warnings": warnings,
        }

    try:
        rendered_paths = _render_pdf_pages(pdf_file, out_dir, selected_pages, dpi)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    rendered_by_page = {
        page: path
        for path in rendered_paths
        if (page := _rendered_page_number(path)) is not None and _is_nonempty_file(path)
    }
    page_entries = [
        {"page": page, "path": _relative_to_run(run_path, rendered_by_page[page])}
        for page in selected_pages
        if page in rendered_by_page
    ]
    manifest_path = run_path / "paper_page_manifest.json"
    if selected_pages and len(page_entries) != len(selected_pages):
        missing_pages = [page for page in selected_pages if page not in rendered_by_page]
        warnings.append(
            f"Only rendered {len(page_entries)} of {len(selected_pages)} requested page(s); missing pages: {', '.join(str(page) for page in missing_pages)}."
        )
    _write_json(
        manifest_path,
        {
            "pdf_path": str(pdf_file),
            "dpi": dpi,
            "total_pages": total_pages,
            "requested_pages": requested_pages,
            "selected_pages": selected_pages,
            "pages": page_entries,
            "warnings": warnings,
            "generated_at": _now_iso(),
        },
    )
    _merge_manifest(
        run_id,
        {
            "paper_page_manifest_path": str(manifest_path),
            "paper_page_image_count": len(page_entries),
            "paper_page_warnings": warnings,
        },
    )

    return {
        "ok": True,
        "run_id": run_id,
        "pdf_path": str(pdf_file),
        "dpi": dpi,
        "total_pages": total_pages,
        "requested_pages": requested_pages,
        "selected_pages": selected_pages,
        "pages": page_entries,
        "warnings": warnings,
        "manifest_path": _relative_to_run(run_path, manifest_path),
    }


@benchmark_mcp_tool
def list_paper_figures(pdf_path: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    """Return likely figure pages for a paper PDF.

    This older figure-only manifest is useful for page discovery, but
    list_paper_visuals is preferred when tables also matter.
    """
    pdf_file = Path(pdf_path).expanduser().resolve()
    if not pdf_file.exists():
        return {"ok": False, "error": f"PDF not found: {pdf_path}"}

    try:
        run_id = _coerce_run_id(run_id)
        run_path = _run_dir(run_id)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    warnings: List[str] = []
    figures = _list_pdf_figures(pdf_file)
    detection_method = "pdfimages"
    if not figures:
        detection_method = "pymupdf_heuristic"
        figures, warnings = _list_pdf_figures_with_pymupdf(pdf_file)
    figure_pages = sorted({figure["page"] for figure in figures if isinstance(figure.get("page"), int)})
    manifest_path = run_path / "paper_figure_manifest.json"
    _write_json(
        manifest_path,
        {
            "pdf_path": str(pdf_file),
            "generated_at": _now_iso(),
            "figure_count": len(figures),
            "figure_pages": figure_pages,
            "detection_method": detection_method,
            "warnings": warnings,
        },
    )
    _merge_manifest(
        run_id,
        {
            "paper_figure_manifest_path": str(manifest_path),
            "paper_figure_count": len(figures),
            "paper_figure_detection_method": detection_method,
            "paper_figure_warnings": warnings,
        },
    )

    return {
        "ok": True,
        "run_id": run_id,
        "pdf_path": str(pdf_file),
        "figure_count": len(figures),
        "figure_pages": figure_pages,
        "detection_method": detection_method,
        "warnings": warnings,
        "manifest_path": _relative_to_run(run_path, manifest_path),
        "note": "Likely pages containing figures. Render only specific pages when visual inspection is needed.",
    }


@benchmark_mcp_tool
def list_paper_visuals(pdf_path: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    """Return a combined manifest of likely figure and table pages for a paper PDF.

    Use this to discover relevant visuals first, then call render_pdf_pages only
    for the pages that matter.
    """
    pdf_file = Path(pdf_path).expanduser().resolve()
    if not pdf_file.exists():
        return {"ok": False, "error": f"PDF not found: {pdf_path}"}

    try:
        run_id = _coerce_run_id(run_id)
        run_path = _run_dir(run_id)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    items, warnings = _extract_visual_items_from_pdf(pdf_file)
    figure_pages = sorted({item["page"] for item in items if item.get("kind") == "figure"})
    table_pages = sorted({item["page"] for item in items if item.get("kind") == "table"})
    visual_pages = sorted({item["page"] for item in items if isinstance(item.get("page"), int)})
    manifest_path = run_path / "paper_visual_manifest.json"
    _write_json(
        manifest_path,
        {
            "pdf_path": str(pdf_file),
            "generated_at": _now_iso(),
            "item_count": len(items),
            "figure_pages": figure_pages,
            "table_pages": table_pages,
            "visual_pages": visual_pages,
            "items": items,
            "warnings": warnings,
        },
    )
    _merge_manifest(
        run_id,
        {
            "paper_visual_manifest_path": str(manifest_path),
            "paper_visual_item_count": len(items),
            "paper_visual_pages": visual_pages,
            "paper_table_pages": table_pages,
            "paper_figure_pages": figure_pages,
            "paper_visual_warnings": warnings,
        },
    )

    return {
        "ok": True,
        "run_id": run_id,
        "pdf_path": str(pdf_file),
        "item_count": len(items),
        "figure_pages": figure_pages,
        "table_pages": table_pages,
        "visual_pages": visual_pages,
        "items": items,
        "warnings": warnings,
        "manifest_path": _relative_to_run(run_path, manifest_path),
        "note": "Combined figure-and-table manifest. Render only specific relevant pages when visual inspection is needed.",
    }


@benchmark_mcp_tool
def list_references(category: Optional[str] = None) -> Dict[str, Any]:
    """List bundled Morpheus reference models and examples by category.

    Use this before read_reference to discover structurally similar examples.
    """
    categories = {category: REFERENCE_CATEGORIES.get(category)} if category else REFERENCE_CATEGORIES
    results: Dict[str, List[str]] = {}
    for name, reference_path in categories.items():
        if not reference_path or not reference_path.exists():
            continue
        if reference_path.is_file():
            results[name] = [reference_path.name]
            continue
        results[name] = sorted(path.name for path in reference_path.iterdir() if path.is_file())
    return {"ok": True, "categories": results}


@benchmark_mcp_tool
def read_reference(category: str, name: str, max_chars: int = MAX_REFERENCE_READ_CHARS) -> Dict[str, Any]:
    """Read one bundled Morpheus reference model or example file.

    Prefer this over direct file reads when MCP is available so example discovery
    and access stay within the server's allowed reference set.
    """
    reference_path = REFERENCE_CATEGORIES.get(category)
    if not reference_path:
        return {
            "ok": False,
            "error": f"Unknown category: {category}. Valid categories: {list(REFERENCE_CATEGORIES)}",
        }
    if reference_path.is_file():
        path = reference_path.resolve()
        if name != reference_path.name:
            return {"ok": False, "error": f"Reference not found: {category}/{name}"}
    else:
        path = (reference_path / name).resolve()
    if not path.exists() or not path.is_file():
        return {"ok": False, "error": f"Reference not found: {category}/{name}"}
    if REFERENCES_ROOT.resolve() not in path.parents:
        return {"ok": False, "error": "Invalid reference path"}

    content = _read_text(path, max_chars)
    return {
        "ok": True,
        "category": category,
        "name": name,
        "path": str(path),
        "content": content,
        "validation": _validate_xml_completeness(content) if path.suffix == ".xml" else None,
    }


@benchmark_mcp_tool
def validate_model_xml(xml_content: str) -> Dict[str, Any]:
    """Validate a Morpheus XML string for basic structural completeness."""
    validation = _validate_xml_completeness(xml_content)
    return {"ok": validation["valid"], **validation}


@benchmark_mcp_tool
def write_model_xml(
    xml_content: str,
    run_id: Optional[str] = None,
    file_name: str = "model.xml",
) -> Dict[str, Any]:
    """Write the canonical Morpheus XML file into the run directory.

    This also stores an incrementing versioned snapshot and returns structural
    validation results. Prefer this over editing the XML file manually.
    """
    cleaned = _sanitize_xml(xml_content)
    if not _looks_like_morpheus_xml(cleaned):
        return {
            "ok": False,
            "error": "Provided XML does not look like a MorpheusModel document",
        }

    try:
        run_id = _coerce_run_id(run_id)
        run_path = _run_dir(run_id)
        xml_path = _resolve_run_file_path(run_path, file_name)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    version_dir = run_path / "xml_versions"
    version_dir.mkdir(parents=True, exist_ok=True)

    existing_versions = sorted(version_dir.glob("model_v*.xml"))
    version_index = len(existing_versions) + 1
    version_path = version_dir / f"model_v{version_index:03d}.xml"

    _write_text(xml_path, cleaned)
    _write_text(version_path, cleaned)

    validation = _validate_xml_completeness(cleaned)
    manifest_path = _merge_manifest(
        run_id,
        {
            "current_model_xml_path": str(xml_path),
            "latest_xml_version_path": str(version_path),
            "xml_version_count": version_index,
            "last_xml_validation": validation,
        },
    )

    return {
        "ok": True,
        "run_id": run_id,
        "xml_path": str(xml_path),
        "version_path": str(version_path),
        "validation": _compact_validation(validation),
        "run_manifest_path": str(manifest_path),
    }


@benchmark_mcp_tool
def capture_model_xml_version(run_id: str, reason: str = "host_captured") -> Dict[str, Any]:
    """Snapshot the current model.xml into the version history if it changed."""
    try:
        run_id = _coerce_run_id(run_id)
        run_path = _run_dir(run_id)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    xml_path = run_path / "model.xml"
    if not xml_path.exists():
        return {
            "ok": True,
            "run_id": run_id,
            "model_present": False,
            "snapshot_created": False,
            "reason": reason,
        }

    current_text = _read_text_full(xml_path)
    current_hash = _sha256_text(current_text)
    version_dir = run_path / "xml_versions"
    version_dir.mkdir(parents=True, exist_ok=True)
    existing_versions = sorted(version_dir.glob("model_v*.xml"))
    latest_version_path = existing_versions[-1] if existing_versions else None
    latest_hash = _sha256_text(_read_text_full(latest_version_path)) if latest_version_path else None
    if latest_hash == current_hash:
        manifest_path = _merge_manifest(
            run_id,
            {
                "current_model_xml_path": str(xml_path),
                "current_model_xml_sha256": current_hash,
                "latest_xml_version_path": str(latest_version_path) if latest_version_path else None,
                "xml_version_count": len(existing_versions),
            },
        )
        return {
            "ok": True,
            "run_id": run_id,
            "model_present": True,
            "snapshot_created": False,
            "current_model_sha256": current_hash,
            "latest_version_path": str(latest_version_path) if latest_version_path else None,
            "xml_version_count": len(existing_versions),
            "run_manifest_path": str(manifest_path),
            "reason": reason,
        }

    version_index = len(existing_versions) + 1
    version_path = version_dir / f"model_v{version_index:03d}.xml"
    _write_text(version_path, current_text)
    validation = _validate_xml_completeness(current_text)
    manifest_path = _merge_manifest(
        run_id,
        {
            "current_model_xml_path": str(xml_path),
            "current_model_xml_sha256": current_hash,
            "latest_xml_version_path": str(version_path),
            "xml_version_count": version_index,
            "last_xml_validation": validation,
            "last_host_captured_xml_version": {
                "timestamp": _now_iso(),
                "reason": reason,
                "version_path": str(version_path),
                "sha256": current_hash,
            },
        },
    )
    _append_manifest_event(
        run_id,
        "host_captured_xml_versions",
        {
            "timestamp": _now_iso(),
            "reason": reason,
            "version_path": str(version_path),
            "sha256": current_hash,
        },
    )
    return {
        "ok": True,
        "run_id": run_id,
        "model_present": True,
        "snapshot_created": True,
        "current_model_sha256": current_hash,
        "version_path": str(version_path),
        "xml_version_count": version_index,
        "validation": validation,
        "run_manifest_path": str(manifest_path),
        "reason": reason,
    }


@benchmark_mcp_tool
def run_morpheus_model(
    xml_path: str,
    run_id: Optional[str] = None,
    threads: Optional[int] = None,
    attempt_id: Optional[str] = None,
    timeout_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Run Morpheus for one XML model and store outputs in a numbered attempt directory.

    The executed XML is copied into the attempt folder so the run can be audited
    against its exact inputs later.
    """
    xml_file = Path(xml_path).expanduser().resolve()
    if not xml_file.exists():
        return {"ok": False, "error": f"XML not found: {xml_path}"}

    try:
        inferred_run_id = None if _active_run_id() else xml_file.parent.name
        run_id = _coerce_run_id(run_id or inferred_run_id)
        run_path = _run_dir(run_id)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    if _active_run_id():
        try:
            xml_file.relative_to(run_path)
        except ValueError:
            return {
                "ok": False,
                "error": f"XML path must be inside the active benchmark run directory: {run_path}",
            }

    resolved_attempt_id = _validate_attempt_id(attempt_id) if attempt_id else _next_attempt_id(run_path)
    attempt_path = _attempt_dir(run_path, resolved_attempt_id)
    if attempt_path.exists() and any(attempt_path.iterdir()):
        return {
            "ok": False,
            "error": f"Attempt directory already exists and is not empty: {resolved_attempt_id}",
        }
    attempt_path.mkdir(parents=True, exist_ok=True)
    executed_xml_path = attempt_path / "model.xml"
    shutil.copy2(xml_file, executed_xml_path)

    command = [MORPHEUS_BIN, "-f", str(executed_xml_path), "--outdir", str(attempt_path)]
    effective_threads = _positive_int_or_none(threads)
    if effective_threads is None:
        env_threads = _integer_env("MORPHEUS_NUM_THREADS", 0, 1)
        effective_threads = env_threads if env_threads > 0 else None
    if effective_threads is not None:
        command.extend(["--num-threads", str(effective_threads)])
    public_command = ["morpheus", *command[1:]]
    configured_timeout_ms = _integer_env(
        "MORPHEUS_RUN_TIMEOUT_MS", DEFAULT_MORPHEUS_RUN_TIMEOUT_MS, 1
    )
    requested_timeout_ms = _positive_int_or_none(timeout_ms) or configured_timeout_ms
    selected_timeout_ms = min(configured_timeout_ms, requested_timeout_ms)
    deadline_path_value = os.getenv(BENCHMARK_DEADLINE_PATH_ENV, "").strip()
    deadline: Optional[Dict[str, Any]] = None
    if deadline_path_value:
        try:
            deadline = json.loads(Path(deadline_path_value).read_text(encoding="utf-8"))
            if not isinstance(deadline.get("softCutoffEpochMs"), (int, float)) or not isinstance(
                deadline.get("hardCutoffEpochMs"), (int, float)
            ):
                raise ValueError("missing numeric softCutoffEpochMs or hardCutoffEpochMs")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            return {"ok": False, "error": f"Invalid benchmark deadline: {exc}"}

    before_ms = _now_epoch_ms()
    remaining_before_ms: Optional[int] = None
    hard_remaining_before_ms: Optional[int] = None
    effective_timeout_ms = selected_timeout_ms
    if deadline is not None:
        remaining_before_ms = max(0, int(deadline["softCutoffEpochMs"]) - before_ms)
        hard_remaining_before_ms = max(0, int(deadline["hardCutoffEpochMs"]) - before_ms)
        effective_timeout_ms = min(selected_timeout_ms, remaining_before_ms)
    refused_for_finalization = deadline is not None and effective_timeout_ms <= 0

    if refused_for_finalization:
        result: Dict[str, Any] = {
            "returncode": MORPHEUS_FINALIZATION_EXIT_CODE,
            "stdout": "",
            "stderr": "",
            "command": public_command,
            "timed_out": False,
            "timeout_s": 0,
            "duration_ms": 0,
            "started_at": _now_iso(),
            "finished_at": _now_iso(),
        }
    else:
        _write_json(
            attempt_path / "morpheus_command.json",
            {
                "artifactSchemaVersion": 2,
                "benchmarkProtocol": "time_limit_v2" if deadline is not None else "legacy",
                "command": public_command,
                "inputXmlPath": str(xml_file),
                "executedXmlPath": str(executed_xml_path),
                "inputXmlSha256": hashlib.sha256(executed_xml_path.read_bytes()).hexdigest(),
                "attemptPath": str(attempt_path),
                "configuredTimeoutMs": configured_timeout_ms,
                "requestedTimeoutMs": requested_timeout_ms,
                "effectiveTimeoutMs": effective_timeout_ms,
                "remainingBeforeMs": remaining_before_ms,
                "remainingAfterMs": None,
                "hardRemainingBeforeMs": hard_remaining_before_ms,
                "returnCode": None,
                "timedOut": False,
                "refusedForFinalization": False,
                "startedAt": _now_iso(),
                "finishedAt": None,
                "durationMs": None,
                "stdoutTruncated": False,
                "stderrTruncated": False,
                "stdoutBytes": 0,
                "stderrBytes": 0,
            },
        )
        try:
            result = _run_cmd(
                command,
                cwd=xml_file.parent,
                timeout_s=max(0.001, effective_timeout_ms / 1000),
                max_output_bytes=MORPHEUS_LOG_CAPTURE_MAX_BYTES,
            )
        except FileNotFoundError:
            return {
                "ok": False,
                "error": f"Morpheus binary not found: {MORPHEUS_BIN}",
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    after_ms = _now_epoch_ms()
    remaining_after_ms = (
        max(0, int(deadline["softCutoffEpochMs"]) - after_ms) if deadline is not None else None
    )

    stdout_path = attempt_path / "stdout.log"
    stderr_path = attempt_path / "stderr.log"
    _write_text(stdout_path, result["stdout"])
    _write_text(stderr_path, result["stderr"])
    timed_out = bool(result.get("timed_out"))
    returncode = MORPHEUS_TIMEOUT_EXIT_CODE if timed_out else result["returncode"]
    stdout_truncated = bool(result.get("stdout_truncated"))
    stderr_truncated = bool(result.get("stderr_truncated"))
    stdout_bytes = int(result.get("stdout_bytes") or len(str(result["stdout"]).encode("utf-8")))
    stderr_bytes = int(result.get("stderr_bytes") or len(str(result["stderr"]).encode("utf-8")))

    command_manifest_path = attempt_path / "morpheus_command.json"
    _write_json(
        command_manifest_path,
        {
            "artifactSchemaVersion": 2,
            "benchmarkProtocol": "time_limit_v2" if deadline is not None else "legacy",
            "command": public_command,
            "inputXmlPath": str(xml_file),
            "executedXmlPath": str(executed_xml_path),
            "inputXmlSha256": hashlib.sha256(executed_xml_path.read_bytes()).hexdigest(),
            "attemptPath": str(attempt_path),
            "configuredTimeoutMs": configured_timeout_ms,
            "requestedTimeoutMs": requested_timeout_ms,
            "effectiveTimeoutMs": effective_timeout_ms,
            "remainingBeforeMs": remaining_before_ms,
            "remainingAfterMs": remaining_after_ms,
            "hardRemainingBeforeMs": hard_remaining_before_ms,
            "returnCode": returncode,
            "timedOut": timed_out,
            "refusedForFinalization": refused_for_finalization,
            "startedAt": result.get("started_at") or _now_iso(),
            "finishedAt": result.get("finished_at") or _now_iso(),
            "durationMs": int(result.get("duration_ms") or 0),
            "stdoutTruncated": stdout_truncated,
            "stderrTruncated": stderr_truncated,
            "stdoutBytes": stdout_bytes,
            "stderrBytes": stderr_bytes,
        },
    )

    outputs = _list_outputs(attempt_path)
    png_outputs = _non_contact_sheet_pngs(outputs["png"])
    primary_pngs = [path for path in png_outputs if Path(path).name.startswith("plot_")]
    logger_pngs = [path for path in png_outputs if Path(path).name.startswith("logger_")]
    stdout_summary = _time_progress_summary(result["stdout"])
    manifest_path = _merge_manifest(
        run_id,
        {
            "last_run_at": _now_iso(),
            "last_run_command": public_command,
            "last_run_returncode": returncode,
            "last_run_timed_out": timed_out,
            "last_run_timeout_ms": effective_timeout_ms,
            "last_run_configured_timeout_ms": configured_timeout_ms,
            "last_run_remaining_before_ms": remaining_before_ms,
            "last_run_remaining_after_ms": remaining_after_ms,
            "last_run_png_count": len(png_outputs),
            "last_run_csv_count": len(outputs["csv"]),
            "latest_attempt_id": resolved_attempt_id,
            "latest_attempt_dir": str(attempt_path),
            "latest_attempt_xml_path": str(executed_xml_path),
            "latest_attempt_stdout_path": str(stdout_path),
            "latest_attempt_stderr_path": str(stderr_path),
            "latest_attempt_returncode": returncode,
            "latest_attempt_timed_out": timed_out,
            "latest_attempt_timeout_ms": effective_timeout_ms,
            "latest_attempt_refused_for_finalization": refused_for_finalization,
            "latest_attempt_command_manifest_path": str(command_manifest_path),
            "latest_attempt_stdout_truncated": stdout_truncated,
            "latest_attempt_stderr_truncated": stderr_truncated,
            "latest_attempt_stdout_bytes": stdout_bytes,
            "latest_attempt_stderr_bytes": stderr_bytes,
            "latest_attempt_png_count": len(png_outputs),
            "latest_attempt_csv_count": len(outputs["csv"]),
        },
    )
    _append_manifest_event(
        run_id,
        "attempt_history",
        {
            "attempt_id": resolved_attempt_id,
            "attempt_dir": str(attempt_path),
            "executed_xml_path": str(executed_xml_path),
            "command": public_command,
            "returncode": returncode,
            "timed_out": timed_out,
            "timeout_ms": effective_timeout_ms,
            "configured_timeout_ms": configured_timeout_ms,
            "remaining_before_ms": remaining_before_ms,
            "remaining_after_ms": remaining_after_ms,
            "refused_for_finalization": refused_for_finalization,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "stdout_bytes": stdout_bytes,
            "stderr_bytes": stderr_bytes,
            "started_at": _now_iso(),
            "png_count": len(png_outputs),
            "csv_count": len(outputs["csv"]),
        },
    )

    ok = returncode == 0
    return {
        "ok": ok,
        "run_id": run_id,
        "attempt_id": resolved_attempt_id,
        "attempt_dir": _relative_to_run(run_path, attempt_path),
        "xml_path": _relative_to_run(run_path, xml_file),
        "executed_xml_path": _relative_to_run(run_path, executed_xml_path),
        "run_dir": str(run_path),
        "returncode": returncode,
        "timed_out": timed_out,
        "timeout_ms": effective_timeout_ms,
        "configured_timeout_ms": configured_timeout_ms,
        "effective_timeout_ms": effective_timeout_ms,
        "remaining_before_ms": remaining_before_ms,
        "remaining_after_ms": remaining_after_ms,
        "refused_for_finalization": refused_for_finalization,
        "stdout_path": _relative_to_run(run_path, stdout_path),
        "stderr_path": _relative_to_run(run_path, stderr_path),
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "stdout_bytes": stdout_bytes,
        "stderr_bytes": stderr_bytes,
        "stdout_tail": _read_compact_tail(stdout_path),
        "stderr_tail": _read_compact_tail(stderr_path),
        "time_progress": stdout_summary,
        "output_counts": {
            **_output_counts(outputs),
            "primary_plot_count": len(primary_pngs),
            "logger_plot_count": len(logger_pngs),
        },
        "key_outputs": {
            "latest_primary_plot": _last_relative(run_path, primary_pngs),
            "latest_logger_plot": _last_relative(run_path, logger_pngs),
            "latest_csv": _last_relative(run_path, outputs["csv"]),
        },
        "run_manifest_path": _relative_to_run(run_path, manifest_path),
        "command_manifest_path": _relative_to_run(run_path, command_manifest_path),
        "message": (
            "Morpheus simulation was not started because the finalization reserve has begun"
            if refused_for_finalization
            else "Morpheus run timed out; partial outputs and logs remain inspectable"
            if timed_out
            else "Morpheus run completed"
            if ok
            else "Morpheus run failed"
        ),
    }


@benchmark_mcp_tool
def summarize_morpheus_run(run_id: str, attempt_id: Optional[str] = None) -> Dict[str, Any]:
    """Summarize the latest or selected Morpheus attempt and its key artifacts."""
    try:
        run_id = _coerce_run_id(run_id)
        run_path = _run_dir(run_id)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    resolved_attempt_id, attempt_path = _resolve_attempt(run_id, run_path, attempt_id)
    if not resolved_attempt_id or not attempt_path:
        return {"ok": False, "error": f"No Morpheus attempt exists yet for run_id={run_id}."}
    outputs = _list_outputs(attempt_path)
    png_outputs = _non_contact_sheet_pngs(outputs["png"])
    stdout_path = attempt_path / "stdout.log"
    stderr_path = attempt_path / "stderr.log"
    xml_path = run_path / "model.xml"
    executed_xml_path = attempt_path / "model.xml"
    primary_pngs = [path for path in png_outputs if Path(path).name.startswith("plot_")]
    logger_pngs = [path for path in png_outputs if Path(path).name.startswith("logger_")]
    stdout_text = _read_text_full(stdout_path) if stdout_path.exists() else ""
    stderr_text = _read_compact_tail(stderr_path) if stderr_path.exists() else ""

    return {
        "ok": True,
        "run_id": run_id,
        "attempt_id": resolved_attempt_id,
        "attempt_dir": _relative_to_run(run_path, attempt_path),
        "run_dir": str(run_path),
        "xml_path": _relative_to_run(run_path, xml_path) if xml_path.exists() else None,
        "executed_xml_path": _relative_to_run(run_path, executed_xml_path) if executed_xml_path.exists() else None,
        "stdout_path": _relative_to_run(run_path, stdout_path) if stdout_path.exists() else None,
        "stderr_path": _relative_to_run(run_path, stderr_path) if stderr_path.exists() else None,
        "output_counts": {
            **{**_output_counts(outputs), "png": len(png_outputs)},
            "primary_plot_count": len(primary_pngs),
            "logger_plot_count": len(logger_pngs),
        },
        "key_outputs": {
            "latest_primary_plot": _last_relative(run_path, primary_pngs),
            "latest_logger_plot": _last_relative(run_path, logger_pngs),
            "latest_csv": _last_relative(run_path, outputs["csv"]),
            "sample_output_paths": _sample_paths(run_path, png_outputs),
        },
        "time_progress": _time_progress_summary(stdout_text),
        "stdout_tail": _read_compact_tail(stdout_path) if stdout_path.exists() else "",
        "stderr_tail": stderr_text,
    }


@benchmark_mcp_tool
def sample_output_images(
    run_id: str,
    limit: int = 5,
    create_contact_sheet: bool = False,
    attempt_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Select representative PNG outputs from a Morpheus attempt.

    Optionally creates a contact sheet to make quick visual review easier.
    """
    try:
        run_id = _coerce_run_id(run_id)
        run_path = _run_dir(run_id)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    resolved_attempt_id, attempt_path = _resolve_attempt(run_id, run_path, attempt_id)
    if not resolved_attempt_id or not attempt_path:
        return {"ok": False, "error": f"No Morpheus attempt exists yet for run_id={run_id}."}
    sample = _sample_run_images(attempt_path, limit)
    selected_paths = [_relative_to_run(run_path, path) for path in sample["selected"]]
    contact_sheet_path: Optional[str] = None

    if create_contact_sheet and sample["selected"]:
        output_path = attempt_path / "sample_contact_sheet.png"
        created = _create_contact_sheet(sample["selected"], output_path)
        if created:
            contact_sheet_path = _relative_to_run(run_path, created)

    return {
        "ok": True,
        "run_id": run_id,
        "attempt_id": resolved_attempt_id,
        "attempt_dir": _relative_to_run(run_path, attempt_path),
        "selected_images": selected_paths,
        "primary_plot_count": sample["primary_plot_count"],
        "logger_plot_count": sample["logger_plot_count"],
        "all_png_count": sample["all_png_count"],
        "contact_sheet_path": contact_sheet_path,
    }


@benchmark_mcp_tool
def evaluate_technical_run(run_id: str, attempt_id: Optional[str] = None) -> Dict[str, Any]:
    """Score a Morpheus run for technical completeness and output generation.

    This is a technical sanity check, not a biological correctness judgment.
    """
    try:
        run_id = _coerce_run_id(run_id)
        run_path = _run_dir(run_id)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    xml_path = run_path / "model.xml"
    evaluation_json = run_path / "technical_evaluation.json"
    evaluation_txt = run_path / "technical_evaluation.txt"
    resolved_attempt_id, attempt_path = _resolve_attempt(run_id, run_path, attempt_id)
    if not resolved_attempt_id or not attempt_path:
        return {"ok": False, "error": f"No Morpheus attempt exists yet for run_id={run_id}."}
    stdout_path = attempt_path / "stdout.log"
    stderr_path = attempt_path / "stderr.log"
    executed_xml_path = attempt_path / "model.xml"

    xml_text = _read_text(xml_path, max_chars=1_000_000)
    executed_xml_text = _read_text(executed_xml_path, max_chars=1_000_000) if executed_xml_path.exists() else ""
    stdout_text = _read_text_full(stdout_path)
    stderr_text = _read_text_full(stderr_path)
    outputs = _list_outputs(attempt_path)
    png_outputs = _non_contact_sheet_pngs(outputs["png"])
    validation = _validate_xml_completeness(xml_text) if xml_text else {}
    current_model_sha256 = _sha256_text(xml_text) if xml_text else None
    scored_attempt_xml_sha256 = _sha256_text(executed_xml_text) if executed_xml_text else None
    attempt_count = len(_existing_attempt_ids(run_path))
    manifest = _load_manifest(run_id)
    attempt_returncode = None
    attempt_timed_out = False
    attempt_history = manifest.get("attempt_history")
    if isinstance(attempt_history, list):
        for entry in attempt_history:
            if isinstance(entry, dict) and entry.get("attempt_id") == resolved_attempt_id:
                attempt_returncode = entry.get("returncode")
                attempt_timed_out = bool(entry.get("timed_out"))
                break
    if attempt_returncode is None and manifest.get("latest_attempt_id") == resolved_attempt_id:
        attempt_returncode = manifest.get("latest_attempt_returncode")
        attempt_timed_out = bool(manifest.get("latest_attempt_timed_out"))

    error_count = _count_error_lines(stderr_text)
    model_graph_present = any(Path(path).name == "model_graph.dot" for path in outputs["dot"])
    model_graph_matches_xml = bool(validation.get("has_model_graph")) == bool(model_graph_present)
    time_lines, time_values = _count_time_lines(stdout_text)
    stop_time = _extract_stop_time(xml_text) if xml_text else None
    last_time = time_values[-1] if time_values else None
    stop_time_match = stop_time is not None and last_time is not None and abs(stop_time - last_time) < 1e-6
    time_score = _calculate_time_score(time_lines, stop_time_match=stop_time_match)
    png_count = len(png_outputs)
    csv_count = len(outputs["csv"])
    results_score = 1 if (png_count > 0 or csv_count > 0) else 0
    bonus_many_results = 1 if png_count >= 10 else 0
    model_graph_score = 1 if model_graph_present and bool(validation.get("has_model_graph")) else 0
    primary_pngs = [path for path in png_outputs if Path(path).name.startswith("plot_")]
    logger_pngs = [path for path in png_outputs if Path(path).name.startswith("logger_")]
    latest_primary_plot = _last_relative(run_path, primary_pngs)
    latest_logger_plot = _last_relative(run_path, logger_pngs)
    latest_primary_plot_time = _extract_time_from_png_name(latest_primary_plot)
    latest_logger_plot_time = _extract_time_from_png_name(latest_logger_plot)
    latest_primary_plot_within_last_time = (
        latest_primary_plot_time is None or last_time is None or latest_primary_plot_time <= last_time + 1e-6
    )
    latest_logger_plot_within_last_time = (
        latest_logger_plot_time is None or last_time is None or latest_logger_plot_time <= last_time + 1e-6
    )

    raw_score = (
        -error_count
        + model_graph_score
        + time_score
        + (1 if stop_time_match else 0)
        + results_score
        + bonus_many_results
    )
    total_score = max(0, min(7, raw_score))
    warnings: List[str] = []
    if attempt_returncode not in (None, 0):
        warnings.append(f"latest Morpheus attempt returned nonzero exit code {attempt_returncode}")
    if attempt_timed_out:
        warnings.append("latest Morpheus attempt timed out")
    if current_model_sha256 and scored_attempt_xml_sha256 and current_model_sha256 != scored_attempt_xml_sha256:
        warnings.append("current model.xml differs from the scored attempt XML")

    breakdown = {
        "xml_error_count": error_count,
        "xml_error_penalty": -error_count,
        "model_graph_present": model_graph_present,
        "model_graph_score": model_graph_score,
        "model_graph_matches_xml": model_graph_matches_xml,
        "time_lines_count": time_lines,
        "time_score": time_score,
        "time_values_sample": time_values[:5],
        "last_time_value": last_time,
        "stop_time": stop_time,
        "stop_time_match": stop_time_match,
        "stop_time_score": 1 if stop_time_match else 0,
        "results_generated": png_count > 0 or csv_count > 0,
        "png_count": png_count,
        "csv_count": csv_count,
        "results_score": results_score,
        "bonus_many_results": bonus_many_results,
        "latest_primary_plot": latest_primary_plot,
        "latest_primary_plot_time": latest_primary_plot_time,
        "latest_primary_plot_within_last_time": latest_primary_plot_within_last_time,
        "latest_logger_plot": latest_logger_plot,
        "latest_logger_plot_time": latest_logger_plot_time,
        "latest_logger_plot_within_last_time": latest_logger_plot_within_last_time,
        "xml_validation": validation,
        "attempt_returncode": attempt_returncode,
        "attempt_timed_out": attempt_timed_out,
        "current_model_sha256": current_model_sha256,
        "scored_attempt_xml_sha256": scored_attempt_xml_sha256,
        "scored_attempt_xml_path": _relative_to_run(run_path, executed_xml_path) if executed_xml_path.exists() else None,
    }
    payload = {
        "ok": True,
        "run_id": run_id,
        "attempt_id": resolved_attempt_id,
        "attempt_dir": _relative_to_run(run_path, attempt_path),
        "attempt_count": attempt_count,
        "returncode": attempt_returncode,
        "timed_out": attempt_timed_out,
        "warnings": warnings,
        "total_score": total_score,
        "max_possible_score": 7,
        "score_percentage": round((total_score / 7) * 100, 2),
        "breakdown": breakdown,
        "evaluation_json_path": str(evaluation_json),
        "evaluation_txt_path": str(evaluation_txt),
        "generated_at": _now_iso(),
    }
    compact_breakdown = {
        key: breakdown[key]
        for key in [
            "xml_error_count",
            "xml_error_penalty",
            "model_graph_present",
            "model_graph_score",
            "model_graph_matches_xml",
            "time_lines_count",
            "time_score",
            "last_time_value",
            "stop_time",
            "stop_time_match",
            "stop_time_score",
            "results_generated",
            "png_count",
            "csv_count",
            "results_score",
            "bonus_many_results",
            "latest_primary_plot",
            "latest_primary_plot_time",
            "latest_primary_plot_within_last_time",
            "latest_logger_plot",
            "latest_logger_plot_time",
            "latest_logger_plot_within_last_time",
            "attempt_returncode",
            "attempt_timed_out",
            "scored_attempt_xml_path",
        ]
    }
    compact_breakdown["xml_validation"] = _compact_validation(validation) if validation else {}
    response_payload = {
        **payload,
        "breakdown": compact_breakdown,
    }
    _write_json(evaluation_json, payload)
    _write_text(
        evaluation_txt,
        "\n".join(
            [
                "============================================================",
                "MORPHEUS TECHNICAL EVALUATION",
                "============================================================",
                f"Run ID: {run_id}",
                f"Timestamp: {payload['generated_at']}",
                "",
                f"TOTAL SCORE: {total_score} / 7 ({payload['score_percentage']}%)",
                "",
                f"Error penalty: {-error_count}",
                f"Model graph: {model_graph_score}/1",
                f"Time progression: {time_score}/3",
                f"StopTime match: {1 if stop_time_match else 0}/1",
                f"Result files: {results_score}/1",
                f"Bonus (10+ PNGs): {bonus_many_results}/1",
                "",
                f"Attempt ID: {resolved_attempt_id}",
                f"Attempt count: {attempt_count}",
                f"Attempt return code: {attempt_returncode}",
                f"Attempt timed out: {attempt_timed_out}",
                f"PNG files: {png_count}",
                f"CSV files: {csv_count}",
                "",
                "Warnings:",
                *(f"- {warning}" for warning in warnings),
            ]
        ),
    )
    _merge_manifest(
        run_id,
        {
            "technical_evaluation_json_path": str(evaluation_json),
            "technical_evaluation_txt_path": str(evaluation_txt),
            "technical_score": total_score,
            "technical_warnings": warnings,
            "technical_attempt_count": attempt_count,
            "technical_attempt_id": resolved_attempt_id,
            "technical_attempt_dir": str(attempt_path),
        },
    )
    return response_payload


@benchmark_mcp_tool
def read_file_text(path: str, max_chars: int = MAX_READ_CHARS) -> Dict[str, Any]:
    """Read a generated run artifact or bundled reference file from allowed roots."""
    try:
        file_path = _resolve_allowed_read_path(path)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    if not file_path.exists() or not file_path.is_file():
        return {"ok": False, "error": f"File not found: {path}"}
    return {"ok": True, "path": str(file_path), "text": _read_text(file_path, max_chars)}


@benchmark_mcp_tool
def read_pdf(pdf_path: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    """Alias for extract_paper_text for callers that expect a read_pdf-style name."""
    return extract_paper_text(pdf_path=pdf_path, run_id=run_id)


MCP_REGISTERED_TOOL_NAMES = tuple(_MCP_REGISTERED_TOOL_NAMES)


if __name__ == "__main__":
    mcp.run(transport="stdio")
