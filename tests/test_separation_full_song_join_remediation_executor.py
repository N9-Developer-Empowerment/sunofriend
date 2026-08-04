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

from sunofriend._separation_authorised_excerpt import _document_sha256, _sha256
from sunofriend._separation_checkpoint_canonical import canonical_json_bytes
from sunofriend._separation_full_song_join_remediation_executor import (
    CANDIDATE_REPORT_NAME,
    REPORT_NAME,
    SCHEMA,
    _apply_equal_power_patch,
    _execute_private_separation_full_song_join_remediation,
)
from sunofriend._separation_full_song_join_remediation_plan import (
    POLICY_ID,
    REPORT_NAME as PLAN_NAME,
    SCHEMA as PLAN_SCHEMA,
    STATUS as PLAN_STATUS,
    _FALSE_EFFECTS as PLAN_FALSE_EFFECTS,
    _FALSE_PERMISSIONS as PLAN_FALSE_PERMISSIONS,
)
from sunofriend._separation_full_song_join_remediation_review import (
    ANSWER_KEY_NAME,
    HTML_NAME,
    REPORT_NAME as REVIEW_REPORT_NAME,
    _prepare_private_join_remediation_review,
)
from sunofriend._separation_full_song_plan import (
    REPORT_NAME as SOURCE_PLAN_NAME,
    _prepare_private_separation_full_song_plan,
)
from sunofriend._separation_full_song_stitch import (
    REPORT_NAME as STITCH_NAME,
    SCHEMA as STITCH_SCHEMA,
    STATUS as STITCH_STATUS,
    _FALSE_PERMISSIONS as STITCH_FALSE_PERMISSIONS,
)
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)


SAMPLE_RATE = 44_100
FRAMES = 20 * SAMPLE_RATE


def test_join_remediation_executor_resumes_and_preserves_raw_control(
    tmp_path: Path,
) -> None:
    remediation, package, source_plan = _inputs(tmp_path)
    runtime = _runtime_arguments(tmp_path)
    output = tmp_path / "execution"
    calls: list[int] = []

    first = _execute_private_separation_full_song_join_remediation(
        remediation,
        package_dir=package,
        source_plan_path=source_plan,
        out_dir=output,
        **runtime,
        maximum_windows=1,
        attempt_runner=_fake_runner(calls),
    )

    assert first["schema"] == SCHEMA
    assert first["summary"]["all_worker_runs_complete"] is True
    assert first["summary"]["candidate_audio_complete"] is True
    assert calls == [661_500]
    candidate = json.loads((output / CANDIDATE_REPORT_NAME).read_text())
    assert candidate["summary"]["patched_boundary_role_pair_count"] == 1
    assert candidate["artifacts"]["vocals"][
        "outside_patch_pcm24_samples_exact"
    ] is True
    assert candidate["artifacts"]["instrumental"]["patch_count"] == 0
    assert candidate["readiness"]["candidate_review_complete"] is False
    assert all(value is False for value in candidate["permissions"].values())
    raw_vocal = package / "STEMS/vocals.wav"
    assert _sha256(raw_vocal) == candidate["bindings"]["raw_vocals_audio_sha256"]
    assert stat.S_IMODE((output / REPORT_NAME).stat().st_mode) == 0o600

    review_root = tmp_path / "review"
    review = _prepare_private_join_remediation_review(
        output,
        package_dir=package,
        out_dir=review_root,
    )
    assert review["expected_counts"] == {
        "boundary_role_pairs": 1,
        "patch_edge_pairs": 2,
        "complete_song_pairs": 3,
        "total_units": 6,
    }
    seed = json.loads((review_root / REVIEW_REPORT_NAME).read_text())
    answer = json.loads((review_root / ANSWER_KEY_NAME).read_text())
    page = (review_root / HTML_NAME).read_text()
    assert seed["bindings"]["answer_key_sha256"] == _sha256(
        review_root / ANSWER_KEY_NAME
    )
    assert answer["status"] == "sealed_do_not_open_before_review"
    assert "\"assignment\"" not in page
    assert "Export reviewed JSON" in page
    assert all(unit["choice"] is None for unit in seed["units"])
    assert all(not unit["heard"]["A"] for unit in seed["units"])

    repeated = _execute_private_separation_full_song_join_remediation(
        remediation,
        package_dir=package,
        source_plan_path=source_plan,
        out_dir=output,
        **runtime,
        maximum_windows=None,
        attempt_runner=_fake_runner(calls),
    )
    assert repeated["windows_executed_this_invocation"] == 0
    assert calls == [661_500]


def test_join_remediation_executor_preserves_failed_attempt(tmp_path: Path) -> None:
    remediation, package, source_plan = _inputs(tmp_path)
    runtime = _runtime_arguments(tmp_path)
    output = tmp_path / "execution"

    def fail(**kwargs: Any) -> Mapping[str, Any]:
        Path(kwargs["attempt_directory"]).mkdir(mode=0o700)
        raise RuntimeError("substituted interruption")

    with pytest.raises(RuntimeError, match="substituted interruption"):
        _execute_private_separation_full_song_join_remediation(
            remediation,
            package_dir=package,
            source_plan_path=source_plan,
            out_dir=output,
            **runtime,
            attempt_runner=fail,
        )
    state = json.loads((output / REPORT_NAME).read_text())
    assert state["windows"][0]["attempts"][0]["status"] == "preserved_incomplete"


def test_equal_power_patch_keeps_exact_outer_samples() -> None:
    destination = np.full((12, 2), 0.25, dtype=np.float32)
    replacement = np.full((8, 2), 0.75, dtype=np.float32)
    before = destination.copy()

    changed = _apply_equal_power_patch(
        destination,
        replacement,
        start=2,
        end=10,
        blend_frames=2,
        np=np,
    )

    assert changed > 0
    np.testing.assert_array_equal(destination[:2], before[:2])
    np.testing.assert_array_equal(destination[10:], before[10:])
    np.testing.assert_array_equal(destination[2], before[2])
    np.testing.assert_array_equal(destination[9], before[9])
    np.testing.assert_array_equal(destination[4:8], replacement[2:6])


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    corpus_root = tmp_path / "corpus"
    original = corpus_root / "song" / "ORIGINAL" / "song.wav"
    original.parent.mkdir(parents=True)
    time = np.arange(FRAMES, dtype=np.float64) / SAMPLE_RATE
    mono = (0.12 * np.sin(2 * np.pi * 220 * time)).astype("float32")
    source = np.column_stack((mono, mono))
    soundfile.write(original, source, SAMPLE_RATE, subtype="PCM_24")
    corpus = {
        "schema": "sunofriend.authorised-separation-corpus.v1",
        "artist": {
            "name": "Owner",
            "soundcloud_profile": "https://example.test/owner",
        },
        "permission": {
            "authority": "creator_and_copyright_holder",
            "scope": "test fixture",
            "allowed_use": "download, study, transform and reuse",
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
    corpus_path = corpus_root / "corpus.json"
    corpus_path.write_text(json.dumps(corpus) + "\n", encoding="utf-8")
    source_plan_root = tmp_path / "source-plan"
    _prepare_private_separation_full_song_plan(
        corpus_path,
        "song",
        out_dir=source_plan_root,
    )
    source_plan_path = source_plan_root / SOURCE_PLAN_NAME
    source_plan = json.loads(source_plan_path.read_text())

    package = tmp_path / "stitch"
    source_dir = package / "SOURCE"
    stems_dir = package / "STEMS"
    source_dir.mkdir(parents=True, mode=0o700)
    stems_dir.mkdir(mode=0o700)
    paths = {
        "source": source_dir / "source-44100.wav",
        "vocals": stems_dir / "vocals.wav",
        "instrumental": stems_dir / "instrumental.wav",
        "reconstruction": stems_dir / "reconstruction.wav",
    }
    arrays = {
        "source": source,
        "vocals": 0.35 * source,
        "instrumental": 0.65 * source,
        "reconstruction": source,
    }
    artifacts: dict[str, Any] = {}
    for role, path in paths.items():
        soundfile.write(path, arrays[role], SAMPLE_RATE, subtype="PCM_24")
        path.chmod(0o600)
        value, _ = soundfile.read(path, dtype="int32", always_2d=True)
        artifacts[role] = {
            "path": path.relative_to(package).as_posix(),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
            "geometry": {
                "sample_rate": SAMPLE_RATE,
                "channels": 2,
                "sample_width_bytes": 3,
                "frames": FRAMES,
            },
        }
        if role in {"source", "vocals", "instrumental"}:
            artifacts[role]["pcm24_int32_sequence_sha256"] = hashlib.sha256(
                value.astype("<i4", copy=False).tobytes(order="C")
            ).hexdigest()
    artifacts["reconstruction"]["global_gain"] = 1.0
    clock = {
        "sample_rate": SAMPLE_RATE,
        "channels": 2,
        "frames": FRAMES,
        "duration_seconds": FRAMES / SAMPLE_RATE,
        "chunk_count": len(source_plan["chunks"]),
        "boundary_count": 1,
        "gap_frames": 0,
        "overlap_frames": 0,
        "crossfade_frames": 0,
    }
    stitch = {
        "schema": STITCH_SCHEMA,
        "status": STITCH_STATUS,
        "evidence_scope": "private_development_only",
        "bindings": {
            "plan_report_sha256": _sha256(source_plan_path),
            "plan_document_sha256": source_plan["document_sha256"],
            "execution_state_sha256": hashlib.sha256(b"execution").hexdigest(),
        },
        "clock": clock,
        "artifacts": artifacts,
        "boundary_review": {"boundary_count": 1},
        "permissions": dict(STITCH_FALSE_PERMISSIONS),
    }
    stitch["document_sha256"] = _document_sha256(stitch)
    stitch_path = package / STITCH_NAME
    _write_private_json(stitch_path, stitch)
    package.chmod(0o700)

    boundary = 10 * SAMPLE_RATE
    window_start = boundary - 661_500 // 2
    remediation = {
        "schema": PLAN_SCHEMA,
        "status": PLAN_STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "stitch_report_sha256": _sha256(stitch_path),
            "stitch_document_sha256": stitch["document_sha256"],
            "source_audio_sha256": artifacts["source"]["sha256"],
            "raw_vocals_audio_sha256": artifacts["vocals"]["sha256"],
            "raw_instrumental_audio_sha256": artifacts["instrumental"]["sha256"],
            "raw_reconstruction_audio_sha256": artifacts["reconstruction"]["sha256"],
            "plan_document_sha256": source_plan["document_sha256"],
        },
        "clock": clock,
        "protocol": {
            "source_window_frames": 661_500,
            "source_window_seconds": 15.0,
            "patch_half_frames": SAMPLE_RATE,
            "patch_duration_frames": 2 * SAMPLE_RATE,
            "patch_duration_seconds": 2.0,
            "edge_blend_frames": 4_410,
            "edge_blend_seconds": 0.1,
            "edge_blend_shape": "equal_power_old_to_new_then_new_to_old",
            "model_invocation": "test exact window",
            "candidate_policy": "test candidate only",
            "raw_stitch_is_control": True,
            "source_windows_may_overlap": True,
            "patch_regions_must_not_overlap": True,
        },
        "windows": [
            {
                "window_index": 1,
                "boundary_index": 1,
                "source_start_frame": window_start,
                "source_end_frame": window_start + 661_500,
                "patch_start_frame": boundary - SAMPLE_RATE,
                "patch_end_frame": boundary + SAMPLE_RATE,
                "patch_target_roles": ["vocals"],
            }
        ],
        "permissions": dict(PLAN_FALSE_PERMISSIONS),
        "effects": dict(PLAN_FALSE_EFFECTS),
    }
    remediation["document_sha256"] = _document_sha256(remediation)
    remediation_path = tmp_path / PLAN_NAME
    _write_private_json(remediation_path, remediation)
    return remediation_path, package, source_plan_path


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


def _fake_runner(calls: list[int]):
    def run(**kwargs: Any) -> Mapping[str, Any]:
        report = json.loads(Path(kwargs["authorisation_report_path"]).read_text())
        frames = report["original"]["local_model_input"]["geometry"]["frames"]
        attempt = Path(kwargs["attempt_directory"])
        attempt.mkdir(mode=0o700)
        outputs = []
        for role, level in (("instrumental", 0.70), ("vocals", 0.30)):
            path = attempt / "staging/quarantine/STEMS" / f"{role}.wav"
            path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            with wave.open(str(path), "wb") as writer:
                writer.setnchannels(2)
                writer.setsampwidth(3)
                writer.setframerate(SAMPLE_RATE)
                sample = int(level * 8_388_607).to_bytes(3, "little", signed=True)
                writer.writeframes(sample * 2 * frames)
            path.chmod(0o600)
            outputs.append(
                {
                    "role": role,
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                    "geometry": {
                        "sample_rate": SAMPLE_RATE,
                        "channels": 2,
                        "sample_width_bytes": 3,
                        "frames": frames,
                    },
                }
            )
        request_sha = hashlib.sha256(kwargs["run_nonce"].encode()).hexdigest()
        receipt = _hash_document(
            {
                "schema": "sunofriend.private-melroformer-native-coordinator.v1",
                "status": "private_native_worker_complete_and_terminal",
                "request_sha256": request_sha,
                "permissions": {"product_route_permitted": False},
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
                "permissions": {"accepted": False},
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
        _write_private_json(attempt / "native-attempt-receipt.json", receipt)
        _write_private_json(attempt / "native-attempt-evidence.json", evidence)
        _write_private_json(attempt / "native-attempt-timing.json", timing)
        calls.append(frames)
        return receipt

    return run


def _hash_document(document: dict[str, Any], key: str) -> dict[str, Any]:
    payload = dict(document)
    payload.pop(key, None)
    document[key] = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return document


def _write_private_json(path: Path, document: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(document, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)
