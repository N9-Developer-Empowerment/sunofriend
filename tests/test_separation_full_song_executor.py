from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
from typing import Any, Mapping
import wave

import numpy as np
import pytest
import soundfile

from sunofriend._separation_checkpoint_canonical import canonical_json_bytes
from sunofriend._separation_full_song_executor import (
    REPORT_NAME,
    SCHEMA,
    __all__,
    _execute_private_separation_full_song_queue,
)
from sunofriend._separation_full_song_plan import (
    REPORT_NAME as PLAN_REPORT_NAME,
    _prepare_private_separation_full_song_plan,
)
from sunofriend._separation_full_song_stitch import (
    REVIEW_HTML_NAME,
    _stitch_private_separation_full_song,
)
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


def _plan(tmp_path: Path) -> Path:
    track = tmp_path / "corpus" / "song"
    original = track / "ORIGINAL" / "song.wav"
    original.parent.mkdir(parents=True)
    frames = 18_000
    time = np.arange(frames, dtype=np.float64) / 44_100
    tone = (np.sin(2 * np.pi * 220 * time) * 0.1).astype("float32")
    soundfile.write(original, np.column_stack((tone, tone)), 44_100, subtype="PCM_24")
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
    out = tmp_path / "plan"
    _prepare_private_separation_full_song_plan(
        corpus_path,
        "song",
        out_dir=out,
        maximum_chunk_frames=9_000,
    )
    return out / PLAN_REPORT_NAME


def _runtime_arguments(tmp_path: Path) -> dict[str, Path]:
    values = {
        "repository_root": tmp_path / "repository",
        "runtime_launcher_path": tmp_path / "python",
        "source_root": tmp_path / "source",
        "checkpoint_path": tmp_path / "model.safetensors",
        "companion_root": tmp_path / "companions",
    }
    for key in ("repository_root", "source_root", "companion_root"):
        values[key].mkdir()
    values["runtime_launcher_path"].write_text("runtime", encoding="utf-8")
    values["checkpoint_path"].write_text("checkpoint", encoding="utf-8")
    return values


def _hash_document(document: dict[str, Any], key: str) -> dict[str, Any]:
    payload = dict(document)
    payload.pop(key, None)
    document[key] = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return document


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(document, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def _write_pcm24(path: Path, frames: int) -> dict[str, Any]:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    current = path.parent
    while current.name not in {"ATTEMPTS", ""}:
        current.chmod(0o700)
        current = current.parent
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(3)
        writer.setframerate(44_100)
        writer.writeframes(b"\0" * frames * 2 * 3)
    path.chmod(0o600)
    contents = path.read_bytes()
    return {
        "bytes": len(contents),
        "sha256": hashlib.sha256(contents).hexdigest(),
        "geometry": {
            "sample_rate": 44_100,
            "channels": 2,
            "sample_width_bytes": 3,
            "frames": frames,
        },
    }


def _fake_runner(calls: list[int]):
    def run(**kwargs: Any) -> Mapping[str, Any]:
        report = json.loads(Path(kwargs["authorisation_report_path"]).read_text())
        frames = report["original"]["local_model_input"]["geometry"]["frames"]
        attempt = Path(kwargs["attempt_directory"])
        attempt.mkdir(mode=0o700)
        stems = attempt / "staging/quarantine/STEMS"
        outputs = []
        for role in ("instrumental", "vocals"):
            claim = _write_pcm24(stems / f"{role}.wav", frames)
            outputs.append({"role": role, **claim})
        request_sha = hashlib.sha256(kwargs["run_nonce"].encode("ascii")).hexdigest()
        receipt = _hash_document(
            {
                "schema": "sunofriend.private-melroformer-native-coordinator.v1",
                "status": "private_native_worker_complete_and_terminal",
                "request_sha256": request_sha,
                "permissions": {
                    "automatic_selection_permitted": False,
                    "product_route_permitted": False,
                },
            },
            "receipt_sha256",
        )
        evidence = _hash_document(
            {
                "schema": "sunofriend.private-kim-native-attempt-evidence.v1",
                "status": "private_native_attempt_verified_not_selected",
                "bindings": {
                    "request_sha256": request_sha,
                    "terminal_receipt_sha256": receipt["receipt_sha256"],
                    "authorisation_report_sha256": kwargs[
                        "authorisation_report_sha256"
                    ],
                    "checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
                    "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
                },
                "outputs": outputs,
                "permissions": {"accepted": False, "product_route_permitted": False},
            },
            "evidence_sha256",
        )
        timing = _hash_document(
            {
                "schema": "sunofriend.private-kim-native-attempt-timing.v1",
                "bindings": {
                    "request_sha256": request_sha,
                    "terminal_receipt_sha256": receipt["receipt_sha256"],
                    "output_evidence_sha256": evidence["evidence_sha256"],
                },
                "permissions": {"benchmark_claim": False},
            },
            "timing_sha256",
        )
        _write_json(attempt / "native-attempt-receipt.json", receipt)
        _write_json(attempt / "native-attempt-evidence.json", evidence)
        _write_json(attempt / "native-attempt-timing.json", timing)
        calls.append(frames)
        return receipt

    return run


def test_full_song_executor_runs_one_then_resumes_all(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    runtime = _runtime_arguments(tmp_path)
    out = tmp_path / "execution"
    calls: list[int] = []

    first = _execute_private_separation_full_song_queue(
        plan,
        out_dir=out,
        **runtime,
        attempt_runner=_fake_runner(calls),
    )
    assert __all__ == ()
    assert first["schema"] == SCHEMA
    assert first["chunks_executed_this_invocation"] == 1
    assert first["summary"]["verified_chunks"] == 1
    assert first["summary"]["remaining_chunks"] == 1
    assert first["summary"]["stitched_outputs_complete"] is False
    assert all(value is False for value in first["permissions"].values())

    complete = _execute_private_separation_full_song_queue(
        plan,
        out_dir=out,
        **runtime,
        maximum_chunks=None,
        attempt_runner=_fake_runner(calls),
    )
    assert complete["chunks_executed_this_invocation"] == 1
    assert complete["summary"]["verified_chunks"] == 2
    assert complete["summary"]["all_worker_runs_complete"] is True
    assert complete["status"] == "private_chunk_execution_complete_not_selected"
    assert calls == [9_000, 9_000]
    persisted = json.loads((out / REPORT_NAME).read_text(encoding="utf-8"))
    assert persisted["state_sha256"]
    assert stat.S_IMODE((out / REPORT_NAME).stat().st_mode) == 0o600


def test_full_song_executor_preserves_failed_attempt_and_retries(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path)
    runtime = _runtime_arguments(tmp_path)
    out = tmp_path / "execution"

    def fail(**kwargs: Any) -> Mapping[str, Any]:
        Path(kwargs["attempt_directory"]).mkdir(mode=0o700)
        raise RuntimeError("substituted interruption")

    with pytest.raises(RuntimeError, match="substituted interruption"):
        _execute_private_separation_full_song_queue(
            plan,
            out_dir=out,
            **runtime,
            attempt_runner=fail,
        )
    failed_state = json.loads((out / REPORT_NAME).read_text(encoding="utf-8"))
    assert failed_state["chunks"][0]["attempts"][0]["status"] == "preserved_incomplete"

    calls: list[int] = []
    result = _execute_private_separation_full_song_queue(
        plan,
        out_dir=out,
        **runtime,
        attempt_runner=_fake_runner(calls),
    )
    assert result["chunks"][0]["selected_attempt"] == 2
    assert [item["status"] for item in result["chunks"][0]["attempts"]] == [
        "preserved_incomplete",
        "verified_complete",
    ]


def test_full_song_executor_rejects_changed_completed_output(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    runtime = _runtime_arguments(tmp_path)
    out = tmp_path / "execution"
    calls: list[int] = []
    _execute_private_separation_full_song_queue(
        plan,
        out_dir=out,
        **runtime,
        attempt_runner=_fake_runner(calls),
    )
    vocal = out / "ATTEMPTS/chunk-0000-attempt-001/staging/quarantine/STEMS/vocals.wav"
    vocal.write_bytes(vocal.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="output binding differs"):
        _execute_private_separation_full_song_queue(
            plan,
            out_dir=out,
            **runtime,
            attempt_runner=_fake_runner(calls),
        )


def test_full_song_executor_is_not_publicly_routed() -> None:
    assert not any("full-song-execute" in command for command in PUBLIC_COMMANDS)
    assert not any("full-song-execute" in command for command in DIRECT_TUI_COMMANDS)


def test_full_song_stitch_preserves_clock_and_prepares_review(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    runtime = _runtime_arguments(tmp_path)
    execution = tmp_path / "execution"
    _execute_private_separation_full_song_queue(
        plan,
        out_dir=execution,
        **runtime,
        maximum_chunks=None,
        attempt_runner=_fake_runner([]),
    )

    result = _stitch_private_separation_full_song(
        plan,
        execution / REPORT_NAME,
        out_dir=tmp_path / "stitch",
    )

    assert result["clock"]["frames"] == 18_000
    assert result["clock"]["boundary_count"] == 1
    assert result["clock"]["crossfade_frames"] == 0
    assert result["readiness"]["stitched_outputs_complete"] is True
    assert result["readiness"]["boundary_listening_complete"] is False
    assert result["reconstruction"]["quality_established"] is False
    assert all(value is False for value in result["permissions"].values())
    review = tmp_path / "stitch/BOUNDARY-REVIEW" / REVIEW_HTML_NAME
    assert review.is_file()
    review_html = review.read_text(encoding="utf-8")
    assert "complete song outputs" in review_html
    assert "every exact chunk join" in review_html
    review_seed = json.loads(
        (tmp_path / "stitch/BOUNDARY-REVIEW/separation_boundary_review.json").read_text()
    )
    assert review_seed["full_song"]["heard_all"] is False
    assert set(review_seed["full_song"]["audio"]) == {
        "source",
        "vocals",
        "instrumental",
        "reconstruction",
    }
