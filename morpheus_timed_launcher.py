#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from morpheus_process import run_bounded_command


MORPHEUS_LOG_CAPTURE_MAX_BYTES = 10 * 1024 * 1024
MORPHEUS_TIMEOUT_EXIT_CODE = 124
MORPHEUS_FINALIZATION_EXIT_CODE = 125
INFO_ONLY_FLAGS = frozenset({"-h", "--help", "-v", "--version", "-r", "--revision", "--gnuplot-version"})
INFO_COMMAND_TIMEOUT_S = 60
# Morpheus also accepts single-dash long names; `-o` works as an abbreviation of --outdir.
INPUT_FLAGS = ("-f", "--file", "-file")
OUTDIR_FLAGS = ("--outdir", "-outdir", "-o")


@dataclass(frozen=True)
class LauncherResult:
    exit_code: int
    timed_out: bool
    refused_for_finalization: bool
    configured_timeout_ms: int
    effective_timeout_ms: int
    attempt_path: str
    message: str


def launch_morpheus(
    args: Sequence[str],
    *,
    real_binary: str,
    deadline_path: Path,
    configured_timeout_ms: int,
    now_epoch_ms: int | None = None,
) -> LauncherResult:
    input_value = _argument_value(args, INPUT_FLAGS)
    if input_value is None:
        raise ValueError("Morpheus invocation requires -f/--file")
    output_value = _argument_value(args, OUTDIR_FLAGS)
    if output_value is None:
        raise ValueError("Morpheus invocation requires --outdir")
    input_path = Path(input_value).expanduser().resolve()
    if not input_path.is_file():
        raise ValueError(f"Morpheus input XML not found: {input_path}")
    attempt_path = Path(output_value).expanduser().resolve()
    attempt_path.mkdir(parents=True, exist_ok=True)
    executed_xml_path = attempt_path / "model.xml"
    if input_path != executed_xml_path:
        shutil.copy2(input_path, executed_xml_path)

    deadline = _read_deadline(deadline_path)
    before_ms = _epoch_ms() if now_epoch_ms is None else now_epoch_ms
    available_ms = int(deadline["softCutoffEpochMs"]) - before_ms
    effective_timeout_ms = max(0, min(configured_timeout_ms, available_ms))
    hard_remaining_before_ms = max(0, int(deadline["hardCutoffEpochMs"]) - before_ms)
    executed_args = _replace_argument_value(args, INPUT_FLAGS, str(executed_xml_path))
    command = [real_binary, *executed_args]
    public_command = ["morpheus", *executed_args]

    if available_ms <= 0:
        message = (
            "MORPHEUS_FINALIZATION_REQUIRED: soft cutoff reached; "
            f"simulation was not started; artifacts: {attempt_path}"
        )
        _write_text(attempt_path / "stdout.log", "")
        _write_text(attempt_path / "stderr.log", "")
        _write_manifest(
            attempt_path,
            command=public_command,
            input_path=input_path,
            executed_xml_path=executed_xml_path,
            configured_timeout_ms=configured_timeout_ms,
            effective_timeout_ms=0,
            remaining_before_ms=0,
            remaining_after_ms=0,
            hard_remaining_before_ms=hard_remaining_before_ms,
            return_code=MORPHEUS_FINALIZATION_EXIT_CODE,
            timed_out=False,
            refused_for_finalization=True,
            started_at=_iso_from_epoch_ms(before_ms),
            finished_at=_iso_from_epoch_ms(before_ms),
            duration_ms=0,
            stdout_truncated=False,
            stderr_truncated=False,
            stdout_bytes=0,
            stderr_bytes=0,
        )
        return LauncherResult(
            exit_code=MORPHEUS_FINALIZATION_EXIT_CODE,
            timed_out=False,
            refused_for_finalization=True,
            configured_timeout_ms=configured_timeout_ms,
            effective_timeout_ms=0,
            attempt_path=str(attempt_path),
            message=message,
        )

    _write_running_manifest(
        attempt_path,
        command=public_command,
        input_path=input_path,
        executed_xml_path=executed_xml_path,
        configured_timeout_ms=configured_timeout_ms,
        effective_timeout_ms=effective_timeout_ms,
        remaining_before_ms=max(0, available_ms),
        hard_remaining_before_ms=hard_remaining_before_ms,
        started_at=_iso_from_epoch_ms(before_ms),
    )
    process_result = run_bounded_command(
        command,
        cwd=input_path.parent,
        timeout_ms=effective_timeout_ms,
        max_output_bytes=MORPHEUS_LOG_CAPTURE_MAX_BYTES,
    )
    after_ms = _epoch_ms() if now_epoch_ms is None else now_epoch_ms
    remaining_after_ms = max(0, int(deadline["softCutoffEpochMs"]) - after_ms)
    exit_code = (
        MORPHEUS_TIMEOUT_EXIT_CODE
        if process_result.timed_out
        else process_result.returncode if process_result.returncode is not None else 1
    )
    _write_text(attempt_path / "stdout.log", process_result.stdout)
    _write_text(attempt_path / "stderr.log", process_result.stderr)
    _write_manifest(
        attempt_path,
        command=public_command,
        input_path=input_path,
        executed_xml_path=executed_xml_path,
        configured_timeout_ms=configured_timeout_ms,
        effective_timeout_ms=effective_timeout_ms,
        remaining_before_ms=max(0, available_ms),
        remaining_after_ms=remaining_after_ms,
        hard_remaining_before_ms=hard_remaining_before_ms,
        return_code=exit_code,
        timed_out=process_result.timed_out,
        refused_for_finalization=False,
        started_at=process_result.started_at,
        finished_at=process_result.finished_at,
        duration_ms=process_result.duration_ms,
        stdout_truncated=process_result.stdout_truncated,
        stderr_truncated=process_result.stderr_truncated,
        stdout_bytes=process_result.stdout_bytes,
        stderr_bytes=process_result.stderr_bytes,
    )
    if process_result.timed_out:
        message = (
            "MORPHEUS_TIMEOUT: terminated process tree; "
            f"artifacts: {attempt_path}; effective timeout: {effective_timeout_ms} ms; "
            f"soft time remaining after call: {remaining_after_ms} ms"
        )
    else:
        message = (
            f"MORPHEUS_FINISHED: exit code {exit_code}; artifacts: {attempt_path}; "
            f"soft time remaining after call: {remaining_after_ms} ms"
        )
    return LauncherResult(
        exit_code=exit_code,
        timed_out=process_result.timed_out,
        refused_for_finalization=False,
        configured_timeout_ms=configured_timeout_ms,
        effective_timeout_ms=effective_timeout_ms,
        attempt_path=str(attempt_path),
        message=message,
    )


def is_info_only_invocation(args: Sequence[str]) -> bool:
    """Help/version calls start no simulation, so they bypass attempt capture."""
    return bool(args) and all(str(arg) in INFO_ONLY_FLAGS for arg in args)


def run_info_command(args: Sequence[str], *, real_binary: str) -> int:
    try:
        return subprocess.run(
            [real_binary, *args], timeout=INFO_COMMAND_TIMEOUT_S, check=False
        ).returncode
    except subprocess.TimeoutExpired:
        return MORPHEUS_TIMEOUT_EXIT_CODE


def _argument_value(args: Sequence[str], names: tuple[str, ...]) -> str | None:
    for index, arg in enumerate(args):
        if arg in names and index + 1 < len(args):
            return str(args[index + 1])
        for name in names:
            prefix = f"{name}="
            if str(arg).startswith(prefix):
                return str(arg)[len(prefix) :]
    return None


def _replace_argument_value(
    args: Sequence[str], names: tuple[str, ...], replacement: str
) -> list[str]:
    updated = [str(arg) for arg in args]
    for index, arg in enumerate(updated):
        if arg in names and index + 1 < len(updated):
            updated[index + 1] = replacement
            return updated
        for name in names:
            prefix = f"{name}="
            if arg.startswith(prefix):
                updated[index] = f"{name}={replacement}"
                return updated
    raise ValueError("Morpheus invocation requires -f/--file")


def _write_running_manifest(attempt_path: Path, **values: Any) -> None:
    _write_manifest(
        attempt_path,
        **values,
        remaining_after_ms=None,
        return_code=None,
        timed_out=False,
        refused_for_finalization=False,
        finished_at=None,
        duration_ms=None,
        stdout_truncated=False,
        stderr_truncated=False,
        stdout_bytes=0,
        stderr_bytes=0,
    )


def _read_deadline(path: Path) -> dict[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid benchmark deadline: {exc}") from exc
    for name in ("softCutoffEpochMs", "hardCutoffEpochMs"):
        if not isinstance(record.get(name), (int, float)):
            raise ValueError(f"Invalid benchmark deadline: missing numeric {name}")
    return record


def _write_manifest(attempt_path: Path, **values: Any) -> None:
    input_path = Path(values.pop("input_path"))
    executed_xml_path = Path(values.pop("executed_xml_path"))
    manifest = {
        "artifactSchemaVersion": 2,
        "benchmarkProtocol": "time_limit_v2",
        "command": values.pop("command"),
        "inputXmlPath": str(input_path),
        "executedXmlPath": str(executed_xml_path),
        "inputXmlSha256": hashlib.sha256(executed_xml_path.read_bytes()).hexdigest(),
        "attemptPath": str(attempt_path),
        "configuredTimeoutMs": values.pop("configured_timeout_ms"),
        "effectiveTimeoutMs": values.pop("effective_timeout_ms"),
        "remainingBeforeMs": values.pop("remaining_before_ms"),
        "remainingAfterMs": values.pop("remaining_after_ms"),
        "hardRemainingBeforeMs": values.pop("hard_remaining_before_ms"),
        "returnCode": values.pop("return_code"),
        "timedOut": values.pop("timed_out"),
        "refusedForFinalization": values.pop("refused_for_finalization"),
        "startedAt": values.pop("started_at"),
        "finishedAt": values.pop("finished_at"),
        "durationMs": values.pop("duration_ms"),
        "stdoutTruncated": values.pop("stdout_truncated"),
        "stderrTruncated": values.pop("stderr_truncated"),
        "stdoutBytes": values.pop("stdout_bytes"),
        "stderrBytes": values.pop("stderr_bytes"),
    }
    _write_text(
        attempt_path / "morpheus_command.json",
        f"{json.dumps(manifest, indent=2)}\n",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temporary_path.write_text(text, encoding="utf-8")
    os.replace(temporary_path, path)


def _epoch_ms() -> int:
    return int(time.time() * 1000)


def _iso_from_epoch_ms(epoch_ms: int) -> str:
    return datetime.fromtimestamp(epoch_ms / 1000, timezone.utc).isoformat()


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    config_path = os.environ.get("MORPHEUS_LAUNCHER_CONFIG")
    deadline_path = os.environ.get("BENCHMARK_DEADLINE_PATH")
    if not config_path or not deadline_path:
        print(
            "MORPHEUS_LAUNCHER_ERROR: launcher configuration or benchmark deadline is missing",
            file=sys.stderr,
        )
        return 2
    try:
        config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        if is_info_only_invocation(args):
            return run_info_command(args, real_binary=str(config["realMorpheusBin"]))
        result = launch_morpheus(
            args,
            real_binary=str(config["realMorpheusBin"]),
            deadline_path=Path(deadline_path),
            configured_timeout_ms=int(config["morpheusRunTimeoutMs"]),
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        print(f"MORPHEUS_LAUNCHER_ERROR: {exc}", file=sys.stderr)
        return 2
    print(result.message)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
