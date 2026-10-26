from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Sequence


@dataclass(frozen=True)
class BoundedProcessResult:
    command: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool
    timeout_ms: int
    started_at: str
    finished_at: str
    duration_ms: int
    stdout_truncated: bool
    stderr_truncated: bool
    stdout_bytes: int
    stderr_bytes: int


class BoundedTextCapture:
    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max(1, max_bytes)
        self.head_limit = max(1, self.max_bytes // 2)
        self.tail_limit = max(1, self.max_bytes - self.head_limit)
        self.total_bytes = 0
        self.truncated = False
        self._full = bytearray()
        self._head = bytearray()
        self._tail = bytearray()

    def append(self, data: bytes) -> None:
        if not data:
            return
        self.total_bytes += len(data)
        if not self.truncated:
            self._full.extend(data)
            if len(self._full) > self.max_bytes:
                self.truncated = True
                self._head = bytearray(self._full[: self.head_limit])
                self._tail = bytearray(self._full[-self.tail_limit :])
                self._full.clear()
            return
        self._tail.extend(data)
        if len(self._tail) > self.tail_limit:
            del self._tail[: len(self._tail) - self.tail_limit]

    def text(self) -> str:
        if not self.truncated:
            return bytes(self._full).decode("utf-8", errors="ignore")
        marker = (
            "\n\n[... command output truncated: "
            f"captured first {len(self._head)} bytes and last {len(self._tail)} bytes "
            f"of {self.total_bytes} bytes; limit {self.max_bytes} bytes ...]\n\n"
        )
        return (
            bytes(self._head).decode("utf-8", errors="ignore")
            + marker
            + bytes(self._tail).decode("utf-8", errors="ignore")
        )


def run_bounded_command(
    command: Sequence[str],
    *,
    cwd: Path | None,
    timeout_ms: int,
    max_output_bytes: int,
) -> BoundedProcessResult:
    if timeout_ms < 1:
        raise ValueError("timeout_ms must be an integer >= 1")
    command_list = [str(part) for part in command]
    started_at = datetime.now(timezone.utc).isoformat()
    started_monotonic = time.monotonic()
    stdout_capture = BoundedTextCapture(max_output_bytes)
    stderr_capture = BoundedTextCapture(max_output_bytes)
    process = subprocess.Popen(command_list, **_contained_popen_kwargs(cwd))
    windows_job = _create_windows_kill_on_close_job(process) if os.name == "nt" else None
    if os.name == "nt":
        try:
            _resume_windows_process(process)
        except Exception:
            if windows_job is not None:
                _close_windows_handle(windows_job)
            raise
    stdout_thread = _start_capture_thread(process.stdout, stdout_capture)
    stderr_thread = _start_capture_thread(process.stderr, stderr_capture)
    timed_out = False
    returncode: int | None = None
    try:
        try:
            returncode = process.wait(timeout=timeout_ms / 1000)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_tree(process, windows_job)
            windows_job = None
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                if process.poll() is None:
                    process.kill()
    finally:
        if windows_job is not None:
            _close_windows_handle(windows_job)
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)
    return BoundedProcessResult(
        command=command_list,
        returncode=None if timed_out else returncode,
        stdout=stdout_capture.text(),
        stderr=stderr_capture.text(),
        timed_out=timed_out,
        timeout_ms=timeout_ms,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc).isoformat(),
        duration_ms=max(0, round((time.monotonic() - started_monotonic) * 1000)),
        stdout_truncated=stdout_capture.truncated,
        stderr_truncated=stderr_capture.truncated,
        stdout_bytes=stdout_capture.total_bytes,
        stderr_bytes=stderr_capture.total_bytes,
    )


def _contained_popen_kwargs(cwd: Path | None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "cwd": str(cwd) if cwd else None,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_SUSPENDED", 0x00000004)
        )
    else:
        kwargs["start_new_session"] = True
    return kwargs


def _start_capture_thread(
    stream: BinaryIO | None,
    capture: BoundedTextCapture,
) -> threading.Thread:
    if stream is None:
        raise RuntimeError("Bounded subprocess stream was not created")
    thread = threading.Thread(target=_read_process_stream, args=(stream, capture), daemon=True)
    thread.start()
    return thread


def _read_process_stream(stream: BinaryIO, capture: BoundedTextCapture) -> None:
    try:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                break
            capture.append(chunk)
    finally:
        stream.close()


def _terminate_process_tree(
    process: subprocess.Popen[bytes],
    windows_job: int | None = None,
) -> None:
    if os.name == "nt":
        if windows_job is not None:
            _close_windows_handle(windows_job)
            return
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


def _create_windows_kill_on_close_job(process: subprocess.Popen[bytes]) -> int | None:
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

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    info = JobObjectExtendedLimitInformation()
    info.BasicLimitInformation.LimitFlags = 0x2000
    if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
        _close_windows_handle(int(job))
        return None
    if not kernel32.AssignProcessToJobObject(job, int(process._handle)):
        _close_windows_handle(int(job))
        return None
    return int(job)


def _close_windows_handle(handle: int) -> None:
    if os.name != "nt":
        return
    import ctypes

    ctypes.windll.kernel32.CloseHandle(handle)


def _resume_windows_process(process: subprocess.Popen[bytes]) -> None:
    if os.name != "nt":
        return
    import ctypes

    status = ctypes.windll.ntdll.NtResumeProcess(int(process._handle))
    if status != 0:
        process.kill()
        raise OSError(f"NtResumeProcess failed with status {status}")
