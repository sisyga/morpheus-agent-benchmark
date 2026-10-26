import os
import sys
import time
from pathlib import Path

import pytest

from morpheus_process import run_bounded_command


def test_run_bounded_command_returns_success_and_audit_metadata(tmp_path):
    result = run_bounded_command(
        [sys.executable, "-c", "import sys; print('ok'); print('warn', file=sys.stderr)"],
        cwd=tmp_path,
        timeout_ms=1_000,
        max_output_bytes=1_024,
    )

    assert result.returncode == 0
    assert result.timed_out is False
    assert result.stdout.strip() == "ok"
    assert result.stderr.strip() == "warn"
    assert result.stdout_bytes >= 3
    assert result.stderr_bytes >= 5
    assert result.duration_ms >= 0
    assert result.started_at.endswith("+00:00")
    assert result.finished_at.endswith("+00:00")


def test_run_bounded_command_preserves_head_and_tail_when_logs_are_truncated(tmp_path):
    result = run_bounded_command(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('START-' + 'x' * 2000 + '-END')",
        ],
        cwd=tmp_path,
        timeout_ms=1_000,
        max_output_bytes=128,
    )

    assert result.returncode == 0
    assert result.stdout_truncated is True
    assert result.stdout_bytes > 128
    assert "START-" in result.stdout
    assert "-END" in result.stdout
    assert "truncated" in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group integration test")
def test_run_bounded_command_timeout_preserves_files_and_kills_descendants(tmp_path):
    child_pid_path = tmp_path / "child.pid"
    partial_path = tmp_path / "partial.csv"
    script = tmp_path / "parent.py"
    script.write_text(
        "\n".join(
            [
                "import subprocess",
                "import sys",
                "import time",
                "from pathlib import Path",
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])",
                f"Path({str(child_pid_path)!r}).write_text(str(child.pid), encoding='utf-8')",
                f"Path({str(partial_path)!r}).write_text('time,value\\n0,1\\n', encoding='utf-8')",
                "print('started', flush=True)",
                "time.sleep(60)",
            ]
        ),
        encoding="utf-8",
    )

    result = run_bounded_command(
        [sys.executable, str(script)],
        cwd=tmp_path,
        timeout_ms=300,
        max_output_bytes=1_024,
    )

    assert result.timed_out is True
    assert result.returncode is None
    assert partial_path.read_text(encoding="utf-8") == "time,value\n0,1\n"
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    deadline = time.time() + 2
    while _pid_exists(child_pid) and time.time() < deadline:
        time.sleep(0.05)
    assert _pid_exists(child_pid) is False


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    stat_path = Path(f"/proc/{pid}/stat")
    if stat_path.exists():
        fields = stat_path.read_text(encoding="utf-8", errors="ignore").split()
        if len(fields) > 2 and fields[2] == "Z":
            return False
    return True
