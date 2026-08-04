from __future__ import annotations

import json
from pathlib import Path
import stat

import numpy as np
import pytest
import soundfile

from sunofriend._separation_full_song_resource_benchmark import (
    SCHEMA,
    _prepare_private_full_song_resource_benchmark_plan,
)
from sunofriend._separation_full_song_plan import (
    REPORT_NAME,
    _prepare_private_separation_full_song_plan,
)
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
)


def _probe(command: tuple[str, ...] | list[str]) -> str:
    key = tuple(command)
    if key == ("/usr/bin/sw_vers", "-productVersion"):
        return "26.5.1\n"
    if key == ("/usr/bin/sw_vers", "-buildVersion"):
        return "25F80\n"
    if key == ("/usr/bin/uname", "-m"):
        return "arm64\n"
    if key == ("/usr/sbin/sysctl", "-n", "hw.memsize"):
        return f"{36 * 1024**3}\n"
    if len(key) == 4 and key[1:3] == ("-I", "-c"):
        return '["CPython", "3.12.10"]\n'
    raise AssertionError(key)


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    track = tmp_path / "corpus" / "song"
    original = track / "ORIGINAL" / "song.wav"
    original.parent.mkdir(parents=True)
    frames = 18_000
    time = np.arange(frames, dtype=np.float64) / 44_100
    tone = (np.sin(2 * np.pi * 220 * time) * 0.1).astype("float32")
    soundfile.write(
        original,
        np.column_stack((tone, tone)),
        44_100,
        subtype="PCM_24",
    )
    corpus = {
        "schema": "sunofriend.authorised-separation-corpus.v1",
        "artist": {
            "name": "Owner",
            "soundcloud_profile": "https://example.test/owner",
        },
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
    corpus_path = tmp_path / "corpus" / "corpus.json"
    corpus_path.write_text(json.dumps(corpus) + "\n", encoding="utf-8")
    plan_root = tmp_path / "plan"
    _prepare_private_separation_full_song_plan(
        corpus_path,
        "song",
        out_dir=plan_root,
        maximum_chunk_frames=9_000,
    )
    plan = plan_root / REPORT_NAME
    runtime = tmp_path / "python"
    runtime.write_bytes(b"python-runtime")
    checkpoint = tmp_path / "model.safetensors"
    with checkpoint.open("wb") as handle:
        handle.truncate(CONVERSION_CHECKPOINT_BYTES)
    return plan, runtime, checkpoint


def test_resource_benchmark_plan_freezes_three_runs_without_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, runtime, checkpoint = _inputs(tmp_path)
    monkeypatch.setattr(
        "sunofriend._separation_full_song_resource_benchmark._sha256",
        lambda path: (
            "312c38e5b698f8dfaa4d6064e8f79010744825828917871a9d22673a43eb7fe5"
            if Path(path) == checkpoint
            else "a" * 64
        ),
    )
    output = tmp_path / "benchmark-plan.json"

    result = _prepare_private_full_song_resource_benchmark_plan(
        plan,
        runtime_launcher_path=runtime,
        checkpoint_path=checkpoint,
        out=output,
        command_runner=_probe,
    )

    assert result["schema"] == SCHEMA
    assert result["status"] == "controlled_resource_benchmark_planned_not_executed"
    assert result["machine_class"]["class_id"] == "apple-silicon-36gib"
    assert result["machine_class"]["runtime"] == "cpython-3.12.10"
    assert result["benchmark_contract"]["repetitions"] == 3
    assert [
        slot["status"] for slot in result["benchmark_contract"]["repetition_slots"]
    ] == [
        "not_run",
        "not_run",
        "not_run",
    ]
    assert result["coverage"]["required_16_gib_acceptance_class_observed"] is False
    assert result["readiness"]["resource_envelope_accepted"] is False
    assert all(value is False for value in result["permissions"].values())
    assert all(value is False for value in result["effects"].values())
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


@pytest.mark.parametrize("repetitions", [0, 2, 11, True])
def test_resource_benchmark_plan_rejects_unbounded_repetitions(
    tmp_path: Path, repetitions: object
) -> None:
    with pytest.raises(ValueError, match="repetitions must be 3..10"):
        _prepare_private_full_song_resource_benchmark_plan(
            tmp_path / "missing-plan.json",
            runtime_launcher_path=tmp_path / "python",
            checkpoint_path=tmp_path / "checkpoint",
            out=tmp_path / "out.json",
            repetitions=repetitions,  # type: ignore[arg-type]
            command_runner=_probe,
        )


def test_resource_benchmark_plan_rejects_non_arm_machine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, runtime, checkpoint = _inputs(tmp_path)
    monkeypatch.setattr(
        "sunofriend._separation_full_song_resource_benchmark._sha256",
        lambda path: (
            "312c38e5b698f8dfaa4d6064e8f79010744825828917871a9d22673a43eb7fe5"
            if Path(path) == checkpoint
            else "b" * 64
        ),
    )

    def wrong_arch(command: tuple[str, ...] | list[str]) -> str:
        if tuple(command) == ("/usr/bin/uname", "-m"):
            return "x86_64\n"
        return _probe(command)

    with pytest.raises(ValueError, match="machine probe differs"):
        _prepare_private_full_song_resource_benchmark_plan(
            plan,
            runtime_launcher_path=runtime,
            checkpoint_path=checkpoint,
            out=tmp_path / "out.json",
            command_runner=wrong_arch,
        )


def test_resource_benchmark_plan_is_path_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, runtime, checkpoint = _inputs(tmp_path)
    monkeypatch.setattr(
        "sunofriend._separation_full_song_resource_benchmark._sha256",
        lambda path: (
            "312c38e5b698f8dfaa4d6064e8f79010744825828917871a9d22673a43eb7fe5"
            if Path(path) == checkpoint
            else "c" * 64
        ),
    )
    output = tmp_path / "out.json"
    _prepare_private_full_song_resource_benchmark_plan(
        plan,
        runtime_launcher_path=runtime,
        checkpoint_path=checkpoint,
        out=output,
        command_runner=_probe,
    )
    serialized = output.read_text(encoding="utf-8")
    assert str(tmp_path) not in serialized
    assert "model.safetensors" not in serialized
    assert "python" not in json.loads(serialized)["bindings"]
