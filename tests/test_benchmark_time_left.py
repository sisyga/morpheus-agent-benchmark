import importlib.util
import json
import os
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_time_left.py"


def load_module():
    spec = importlib.util.spec_from_file_location("benchmark_time_left", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_time_left_reports_elapsed_cutoffs_and_morpheus_limit(tmp_path, monkeypatch, capsys):
    deadline = tmp_path / "subject_deadline.json"
    deadline.write_text(
        json.dumps(
            {
                "subjectStartedAtEpochMs": 1_000,
                "softCutoffEpochMs": 5_000,
                "hardCutoffEpochMs": 6_000,
                "morpheusRunTimeoutMs": 3_600_000,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BENCHMARK_DEADLINE_PATH", str(deadline))
    module = load_module()

    assert module.main(now_epoch_ms=4_000) == 0

    output = capsys.readouterr().out
    assert "elapsed: 3s" in output
    assert "soft cutoff in: 1s" in output
    assert "hard cutoff in: 2s" in output
    assert "configured Morpheus limit: 1h" in output


def test_time_left_clamps_expired_cutoffs_to_zero(tmp_path, monkeypatch, capsys):
    deadline = tmp_path / "subject_deadline.json"
    deadline.write_text(
        json.dumps(
            {
                "subjectStartedAtEpochMs": 1_000,
                "softCutoffEpochMs": 2_000,
                "hardCutoffEpochMs": 3_000,
                "morpheusRunTimeoutMs": 60_000,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BENCHMARK_DEADLINE_PATH", str(deadline))
    module = load_module()

    assert module.main(now_epoch_ms=4_000) == 0

    output = capsys.readouterr().out
    assert "soft cutoff in: 0s" in output
    assert "hard cutoff in: 0s" in output


def test_time_left_returns_nonzero_for_missing_or_invalid_deadline(tmp_path, monkeypatch, capsys):
    module = load_module()
    monkeypatch.delenv("BENCHMARK_DEADLINE_PATH", raising=False)
    assert module.main(now_epoch_ms=4_000) == 2
    assert "BENCHMARK_DEADLINE_PATH is not set" in capsys.readouterr().err

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("BENCHMARK_DEADLINE_PATH", str(invalid))
    assert module.main(now_epoch_ms=4_000) == 2
    assert "Invalid benchmark deadline" in capsys.readouterr().err
