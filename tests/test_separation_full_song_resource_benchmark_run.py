from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pytest
import soundfile

from sunofriend._separation_authorised_excerpt import _document_sha256
from sunofriend._separation_full_song_executor import REPORT_NAME as EXECUTION_REPORT
from sunofriend._separation_full_song_plan import (
    REPORT_NAME as PLAN_REPORT,
    _prepare_private_separation_full_song_plan,
)
from sunofriend._separation_full_song_resource import SCHEMA as RESOURCE_SCHEMA
from sunofriend._separation_full_song_resource_benchmark import (
    _prepare_private_full_song_resource_benchmark_plan,
)
from sunofriend._separation_full_song_resource_benchmark_result import (
    SCHEMA as RESULT_SCHEMA,
    _verify_private_full_song_resource_benchmark,
)
from sunofriend._separation_full_song_resource_benchmark_run import (
    REPORT_NAME,
    SCHEMA,
    _run_private_full_song_resource_benchmark_repetition,
)
from sunofriend._separation_full_song_stitch import REPORT_NAME as STITCH_REPORT
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
)


def _probe(command: tuple[str, ...] | list[str]) -> str:
    key = tuple(command)
    values = {
        ("/usr/bin/sw_vers", "-productVersion"): "26.5.1\n",
        ("/usr/bin/sw_vers", "-buildVersion"): "25F80\n",
        ("/usr/bin/uname", "-m"): "arm64\n",
        ("/usr/sbin/sysctl", "-n", "hw.memsize"): f"{36 * 1024**3}\n",
    }
    if key in values:
        return values[key]
    if len(key) == 4 and key[1:3] == ("-I", "-c"):
        return '["CPython", "3.12.10"]\n'
    raise AssertionError(key)


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    original = tmp_path / "corpus/song/ORIGINAL/song.wav"
    original.parent.mkdir(parents=True)
    frames = 18_000
    time = np.arange(frames, dtype=np.float64) / 44_100
    tone = (np.sin(2 * np.pi * 220 * time) * 0.1).astype("float32")
    soundfile.write(original, np.column_stack((tone, tone)), 44_100, subtype="PCM_24")
    corpus = {
        "schema": "sunofriend.authorised-separation-corpus.v1",
        "artist": {"name": "Owner", "soundcloud_profile": "https://example.test"},
        "permission": {
            "authority": "creator_and_copyright_holder",
            "scope": "test fixture",
            "allowed_use": "study",
            "condition": "credit Owner",
            "recorded_on": "2026-08-04",
        },
        "tracks": [
            {
                "id": "song",
                "title": "Song",
                "directory": "song",
                "evaluation_state": "ready_for_excerpt_selection",
            }
        ],
    }
    corpus_path = tmp_path / "corpus/corpus.json"
    corpus_path.write_text(json.dumps(corpus) + "\n", encoding="utf-8")
    plan_root = tmp_path / "plan"
    _prepare_private_separation_full_song_plan(
        corpus_path,
        "song",
        out_dir=plan_root,
        maximum_chunk_frames=9_000,
    )
    base_runtime = tmp_path / "base-python"
    base_runtime.write_bytes(b"runtime")
    runtime = tmp_path / "venv/bin/python"
    runtime.parent.mkdir(parents=True)
    runtime.symlink_to(base_runtime)
    checkpoint = tmp_path / "model.safetensors"
    with checkpoint.open("wb") as handle:
        handle.truncate(CONVERSION_CHECKPOINT_BYTES)
    benchmark = tmp_path / "benchmark-plan.json"
    _prepare_private_full_song_resource_benchmark_plan(
        plan_root / PLAN_REPORT,
        runtime_launcher_path=runtime,
        checkpoint_path=checkpoint,
        out=benchmark,
        command_runner=_probe,
    )
    return plan_root / PLAN_REPORT, runtime, checkpoint, benchmark


def _write_private_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")
    path.chmod(0o600)


def _fake_pipeline() -> tuple[Any, Any, Any]:
    def executor(*_args: Any, **kwargs: Any) -> Mapping[str, Any]:
        assert Path(kwargs["runtime_launcher_path"]).parent.name == "bin"
        report = Path(kwargs["out_dir"]) / EXECUTION_REPORT
        document = {
            "status": "private_chunk_execution_complete_not_selected",
            "state_sha256": "1" * 64,
            "summary": {"all_worker_runs_complete": True},
        }
        _write_private_json(report, document)
        return document

    def stitcher(*_args: Any, **kwargs: Any) -> Mapping[str, Any]:
        report = Path(kwargs["out_dir"]) / STITCH_REPORT
        document = {
            "status": "exact_clock_stitch_complete_review_required",
            "document_sha256": "2" * 64,
        }
        _write_private_json(report, document)
        return document

    def observer(*_args: Any, **kwargs: Any) -> Mapping[str, Any]:
        document = {
            "schema": RESOURCE_SCHEMA,
            "document_sha256": "3" * 64,
            "execution_observation": {
                "worker_resources": {
                    "complete_for_selected_attempts": True,
                    "summed_inference_seconds": 0.3,
                    "maximum_peak_mlx_allocator_memory_bytes": 2_500_000_000,
                },
                "native_process_resources": {
                    "complete_for_selected_attempts": True,
                    "maximum_peak_process_rss_bytes": 3_000_000_000,
                    "maximum_peak_total_unified_memory_bytes": 3_200_000_000,
                },
            },
            "coverage": {
                "peak_process_rss_observed": True,
                "peak_total_unified_memory_observed": True,
                "peak_mlx_allocator_memory_observed": True,
                "worker_model_inference_time_observed": True,
            },
        }
        _write_private_json(Path(kwargs["out"]), document)
        return document

    return executor, stitcher, observer


def _run(
    tmp_path: Path,
    *,
    index: int,
    wall_start: int,
) -> Path:
    plan, runtime, checkpoint, benchmark = _inputs(tmp_path)
    executor, stitcher, observer = _fake_pipeline()
    monotonic = iter((100_000_000_000, 100_500_000_000))
    wall = iter((wall_start, wall_start + 500_000_000))
    thermal = iter(
        (
            {"value": 0, "name": "nominal"},
            {"value": 1, "name": "fair"},
        )
    )
    destination = tmp_path / f"run-{index}"
    _run_private_full_song_resource_benchmark_repetition(
        benchmark,
        plan,
        repetition_index=index,
        out_dir=destination,
        repository_root=tmp_path,
        runtime_launcher_path=runtime,
        source_root=tmp_path,
        checkpoint_path=checkpoint,
        companion_root=tmp_path,
        command_runner=_probe,
        thermal_probe=lambda: next(thermal),
        monotonic_ns=lambda: next(monotonic),
        wall_time_ns=lambda: next(wall),
        nonce_factory=lambda: f"repetition-{index}-" + "x" * 32,
        executor=executor,
        stitcher=stitcher,
        observer=observer,
    )
    return destination / REPORT_NAME


@pytest.fixture(autouse=True)
def _fake_large_file_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sunofriend._separation_full_song_resource_benchmark._sha256",
        lambda path: (
            "312c38e5b698f8dfaa4d6064e8f79010744825828917871a9d22673a43eb7fe5"
            if Path(path).name == "model.safetensors"
            else "a" * 64
        ),
    )


def test_one_repetition_retains_every_required_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_path = _run(
        tmp_path,
        index=1,
        wall_start=1_000_000_000_000,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["schema"] == SCHEMA
    assert report["measurements"]["parent_observed_full_song_wall_time_seconds"] == 0.5
    assert report["measurements"]["summed_worker_model_call_seconds"] == 0.3
    assert report["measurements"]["peak_process_rss_bytes"] == 3_000_000_000
    assert report["measurements"]["peak_total_unified_memory_bytes"] == 3_200_000_000
    assert report["measurements"]["thermal_state_before"]["name"] == "nominal"
    assert report["measurements"]["thermal_state_after"]["name"] == "fair"
    assert report["readiness"]["controlled_repeated_benchmark_complete"] is False
    assert report["readiness"]["resource_envelope_accepted"] is False
    assert all(value is False for value in report["permissions"].values())
    assert str(tmp_path) not in report_path.read_text(encoding="utf-8")


def test_result_requires_all_serial_runs_and_keeps_36_gib_unaccepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports = []
    for index in range(1, 4):
        run_root = tmp_path / f"fixture-{index}"
        run_root.mkdir()
        reports.append(
            _run(
                run_root,
                index=index,
                wall_start=index * 1_000_000_000_000,
            )
        )
    benchmark = tmp_path / "fixture-1/benchmark-plan.json"
    result = _verify_private_full_song_resource_benchmark(
        benchmark,
        reports,
        out=tmp_path / "result.json",
    )

    assert result["schema"] == RESULT_SCHEMA
    assert result["protocol"]["verified_repetitions"] == 3
    assert result["coverage"]["all_required_measurements_observed"] is True
    assert result["coverage"]["development_machine_thresholds_met"] is True
    assert result["coverage"]["required_16_gib_acceptance_class_observed"] is False
    assert result["readiness"]["resource_envelope_accepted"] is False
    assert result["readiness"]["publication_ready"] is False
    assert all(value is False for value in result["permissions"].values())


def test_result_rejects_semantically_tampered_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports = []
    for index in range(1, 4):
        run_root = tmp_path / f"fixture-{index}"
        run_root.mkdir()
        reports.append(
            _run(
                run_root,
                index=index,
                wall_start=index * 1_000_000_000_000,
            )
        )
    changed = json.loads(reports[1].read_text(encoding="utf-8"))
    changed["measurements"]["peak_total_unified_memory_gib"] = 0.1
    changed["document_sha256"] = _document_sha256(changed)
    _write_private_json(reports[1], changed)

    with pytest.raises(ValueError, match="measurement differs"):
        _verify_private_full_song_resource_benchmark(
            tmp_path / "fixture-1/benchmark-plan.json",
            reports,
            out=tmp_path / "result.json",
        )


@pytest.mark.parametrize("failure", ["reused_nonce", "overlap"])
def test_result_rejects_non_independent_repetitions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    reports = []
    for index in range(1, 4):
        run_root = tmp_path / f"fixture-{index}"
        run_root.mkdir()
        reports.append(
            _run(
                run_root,
                index=index,
                wall_start=index * 1_000_000_000_000,
            )
        )
    first = json.loads(reports[0].read_text(encoding="utf-8"))
    changed = json.loads(reports[1].read_text(encoding="utf-8"))
    if failure == "reused_nonce":
        changed["repetition"]["nonce_sha256"] = first["repetition"][
            "nonce_sha256"
        ]
        match = "nonce differs"
    else:
        changed["interval"]["wall_started_unix_ns"] = first["interval"][
            "wall_finished_unix_ns"
        ] - 1
        changed["interval"]["wall_finished_unix_ns"] = (
            changed["interval"]["wall_started_unix_ns"] + 500_000_000
        )
        match = "overlap"
    changed["document_sha256"] = _document_sha256(changed)
    _write_private_json(reports[1], changed)

    with pytest.raises(ValueError, match=match):
        _verify_private_full_song_resource_benchmark(
            tmp_path / "fixture-1/benchmark-plan.json",
            reports,
            out=tmp_path / "result.json",
        )
