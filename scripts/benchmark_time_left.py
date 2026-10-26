#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = (
    "subjectStartedAtEpochMs",
    "softCutoffEpochMs",
    "hardCutoffEpochMs",
    "morpheusRunTimeoutMs",
)


def format_ms(milliseconds: int) -> str:
    total_seconds = max(0, milliseconds) // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def _read_deadline() -> dict[str, Any]:
    raw_path = os.environ.get("BENCHMARK_DEADLINE_PATH")
    if not raw_path:
        raise ValueError("BENCHMARK_DEADLINE_PATH is not set")
    path = Path(raw_path)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid benchmark deadline: {exc}") from exc
    if not isinstance(record, dict) or any(
        not isinstance(record.get(field), (int, float)) for field in REQUIRED_FIELDS
    ):
        raise ValueError("Invalid benchmark deadline: required numeric fields are missing")
    return record


def main(now_epoch_ms: int | None = None) -> int:
    try:
        record = _read_deadline()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    now_ms = int(time.time() * 1000) if now_epoch_ms is None else now_epoch_ms
    print(f"elapsed: {format_ms(max(0, now_ms - int(record['subjectStartedAtEpochMs'])))}")
    print(f"soft cutoff in: {format_ms(max(0, int(record['softCutoffEpochMs']) - now_ms))}")
    print(f"hard cutoff in: {format_ms(max(0, int(record['hardCutoffEpochMs']) - now_ms))}")
    print(f"configured Morpheus limit: {format_ms(int(record['morpheusRunTimeoutMs']))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
