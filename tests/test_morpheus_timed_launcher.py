import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from morpheus_timed_launcher import launch_morpheus, main


def _write_fake_morpheus(tmp_path: Path) -> Path:
    executable = tmp_path / "fake_morpheus"
    executable.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import argparse",
                "import time",
                "from pathlib import Path",
                "parser = argparse.ArgumentParser()",
                "parser.add_argument('-f', '--file', required=True)",
                "parser.add_argument('--outdir', '-o', required=True)",
                "parser.add_argument('--sleep', type=float, default=0)",
                "args, _ = parser.parse_known_args()",
                "outdir = Path(args.outdir)",
                "outdir.mkdir(parents=True, exist_ok=True)",
                "(outdir / 'input_path.txt').write_text(str(Path(args.file).resolve()), encoding='utf-8')",
                "(outdir / 'partial.png').write_bytes(b'png')",
                "(outdir / 'partial.csv').write_text('time,value\\n0,1\\n', encoding='utf-8')",
                "print('fake stdout', flush=True)",
                "time.sleep(args.sleep)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return executable


def _write_deadline(tmp_path: Path, soft_cutoff_ms: int, hard_cutoff_ms: int = 10_000) -> Path:
    path = tmp_path / "subject_deadline.json"
    path.write_text(
        json.dumps(
            {
                "subjectStartedAtEpochMs": 0,
                "softCutoffEpochMs": soft_cutoff_ms,
                "hardCutoffEpochMs": hard_cutoff_ms,
                "morpheusRunTimeoutMs": 60_000,
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.mark.skipif(os.name == "nt", reason="fake POSIX executable")
def test_launcher_timeout_preserves_partial_outputs_and_writes_manifest(tmp_path):
    fake = _write_fake_morpheus(tmp_path)
    source_model = tmp_path / "source.xml"
    source_model.write_text("<MorpheusModel />", encoding="utf-8")
    attempt = tmp_path / "attempt_001"
    deadline = _write_deadline(tmp_path, soft_cutoff_ms=1_200)

    result = launch_morpheus(
        ["-f", str(source_model), "--outdir", str(attempt), "--sleep", "5"],
        real_binary=str(fake),
        deadline_path=deadline,
        configured_timeout_ms=60_000,
        now_epoch_ms=1_000,
    )

    assert result.exit_code == 124
    assert result.timed_out is True
    assert result.refused_for_finalization is False
    assert result.configured_timeout_ms == 60_000
    assert result.effective_timeout_ms == 200
    assert (attempt / "model.xml").read_bytes() == source_model.read_bytes()
    assert Path((attempt / "input_path.txt").read_text(encoding="utf-8")) == attempt / "model.xml"
    assert (attempt / "partial.png").exists()
    assert (attempt / "partial.csv").exists()
    assert "fake stdout" in (attempt / "stdout.log").read_text(encoding="utf-8")
    assert (attempt / "stderr.log").exists()
    manifest = json.loads((attempt / "morpheus_command.json").read_text(encoding="utf-8"))
    assert manifest["configuredTimeoutMs"] == 60_000
    assert manifest["effectiveTimeoutMs"] == 200
    assert manifest["timedOut"] is True
    assert manifest["returnCode"] == 124
    assert manifest["command"][0] == "morpheus"
    assert str(fake) not in json.dumps(manifest)
    assert "MORPHEUS_TIMEOUT" in result.message
    assert str(attempt) in result.message


@pytest.mark.skipif(os.name == "nt", reason="fake POSIX executable")
def test_launcher_refuses_new_simulation_at_soft_cutoff_without_spawning(tmp_path):
    fake = _write_fake_morpheus(tmp_path)
    source_model = tmp_path / "source.xml"
    source_model.write_text("<MorpheusModel />", encoding="utf-8")
    attempt = tmp_path / "attempt_002"
    deadline = _write_deadline(tmp_path, soft_cutoff_ms=1_000)

    result = launch_morpheus(
        ["-f", str(source_model), "--outdir", str(attempt), "--sleep", "0"],
        real_binary=str(fake),
        deadline_path=deadline,
        configured_timeout_ms=60_000,
        now_epoch_ms=1_000,
    )

    assert result.exit_code == 125
    assert result.refused_for_finalization is True
    assert result.timed_out is False
    assert (attempt / "model.xml").exists()
    assert not (attempt / "partial.png").exists()
    assert (attempt / "stdout.log").read_text(encoding="utf-8") == ""
    manifest = json.loads((attempt / "morpheus_command.json").read_text(encoding="utf-8"))
    assert manifest["refusedForFinalization"] is True
    assert manifest["effectiveTimeoutMs"] == 0
    assert "MORPHEUS_FINALIZATION_REQUIRED" in result.message


@pytest.mark.skipif(os.name == "nt", reason="fake POSIX executable")
def test_launcher_success_retains_outputs_and_real_return_code(tmp_path):
    fake = _write_fake_morpheus(tmp_path)
    source_model = tmp_path / "source.xml"
    source_model.write_text("<MorpheusModel />", encoding="utf-8")
    attempt = tmp_path / "attempt_003"
    deadline = _write_deadline(tmp_path, soft_cutoff_ms=10_000)

    result = launch_morpheus(
        ["-f", str(source_model), "--outdir", str(attempt)],
        real_binary=str(fake),
        deadline_path=deadline,
        configured_timeout_ms=1_000,
        now_epoch_ms=1_000,
    )

    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.effective_timeout_ms == 1_000
    assert (attempt / "partial.png").exists()
    assert json.loads((attempt / "morpheus_command.json").read_text())["returnCode"] == 0


def test_launcher_requires_explicit_model_and_output_directory(tmp_path):
    deadline = _write_deadline(tmp_path, soft_cutoff_ms=10_000)
    with pytest.raises(ValueError, match="-f/--file"):
        launch_morpheus(
            ["--outdir", str(tmp_path / "attempt")],
            real_binary="morpheus",
            deadline_path=deadline,
            configured_timeout_ms=1_000,
            now_epoch_ms=1_000,
        )
    source_model = tmp_path / "model.xml"
    source_model.write_text("<MorpheusModel />", encoding="utf-8")
    with pytest.raises(ValueError, match="requires --outdir"):
        launch_morpheus(
            ["-f", str(source_model)],
            real_binary="morpheus",
            deadline_path=deadline,
            configured_timeout_ms=1_000,
            now_epoch_ms=1_000,
        )


@pytest.mark.skipif(os.name == "nt", reason="fake POSIX executable")
def test_parallel_launchers_keep_attempts_and_process_groups_independent(tmp_path):
    fake = _write_fake_morpheus(tmp_path)
    source_model = tmp_path / "source.xml"
    source_model.write_text("<MorpheusModel />", encoding="utf-8")
    deadline = _write_deadline(tmp_path, soft_cutoff_ms=10_000)
    slow_attempt = tmp_path / "attempt_slow"
    fast_attempt = tmp_path / "attempt_fast"

    with ThreadPoolExecutor(max_workers=2) as pool:
        slow_future = pool.submit(
            launch_morpheus,
            ["-f", str(source_model), "--outdir", str(slow_attempt), "--sleep", "5"],
            real_binary=str(fake),
            deadline_path=deadline,
            configured_timeout_ms=200,
            now_epoch_ms=1_000,
        )
        fast_future = pool.submit(
            launch_morpheus,
            ["-f", str(source_model), "--outdir", str(fast_attempt)],
            real_binary=str(fake),
            deadline_path=deadline,
            configured_timeout_ms=1_000,
            now_epoch_ms=1_000,
        )
        slow_result = slow_future.result()
        fast_result = fast_future.result()

    assert slow_result.exit_code == 124
    assert fast_result.exit_code == 0
    assert (slow_attempt / "partial.csv").exists()
    assert (fast_attempt / "partial.csv").exists()
    assert json.loads((slow_attempt / "morpheus_command.json").read_text())["timedOut"] is True
    assert json.loads((fast_attempt / "morpheus_command.json").read_text())["timedOut"] is False


@pytest.mark.skipif(os.name == "nt", reason="fake POSIX executable")
def test_launcher_passes_help_and_version_through_without_attempt_capture(tmp_path, monkeypatch, capfd):
    fake = tmp_path / "fake_morpheus_info"
    fake.write_text('#!/bin/sh\necho "real morpheus $*"\nexit 3\n', encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    config = tmp_path / "morpheus_launcher.json"
    config.write_text(json.dumps({"realMorpheusBin": str(fake), "morpheusRunTimeoutMs": 60_000}), encoding="utf-8")
    monkeypatch.setenv("MORPHEUS_LAUNCHER_CONFIG", str(config))
    monkeypatch.setenv("BENCHMARK_DEADLINE_PATH", str(tmp_path / "subject_deadline.json"))
    monkeypatch.chdir(tmp_path)

    assert main(["--help"]) == 3
    assert main(["--version"]) == 3
    assert capfd.readouterr().out.splitlines() == ["real morpheus --help", "real morpheus --version"]
    assert not list(tmp_path.rglob("morpheus_command.json"))

    # Simulations still require an explicit model and output directory.
    assert main(["--help", "-f", "model.xml"]) == 2
    assert "requires --outdir" in capfd.readouterr().err
