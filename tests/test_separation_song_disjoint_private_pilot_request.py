from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path

import numpy as np
import pytest
import soundfile

import sunofriend._separation_song_disjoint_private_pilot_request as request
from sunofriend._separation_authorised_excerpt import _document_sha256


def test_private_pilot_request_prepares_path_free_owner_only_queue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path)
    monkeypatch.setattr(request, "_load_request_inputs", lambda *a, **k: context)
    monkeypatch.setattr(
        request, "_require_output_disjoint_from_inputs", lambda *a, **k: None
    )
    corpus = _corpus(tmp_path)
    output = tmp_path / "request"

    result = request._prepare_song_disjoint_private_pilot_request(
        "authorization.json",
        reference_v2_execution_path="reference.json",
        reference_stitch_package_dir="reference-stitch",
        corpus_manifest_path=corpus,
        track_id="new-song",
        repository_root="repository",
        runtime_launcher_path="runtime",
        source_root="source",
        checkpoint_path="checkpoint",
        companion_root="companions",
        out_dir=output,
    )

    assert request.__all__ == ()
    assert result["schema"] == request.SCHEMA
    assert result["status"] == request.STATUS
    assert result["readiness"]["private_worker_execution_ready"] is True
    assert result["readiness"]["worker_runs_complete"] is False
    assert result["permissions"]["bounded_private_worker_execution_permitted"]
    assert result["permissions"]["simple_mode_available"] is False
    assert result["effects"]["model_run"] is False
    assert result["effects"]["canonical_chunk_audio_created"] is True
    assert result["plan"]["chunk_count"] == 2
    assert result["plan"]["gap_frames"] == 0
    assert result["plan"]["overlap_frames"] == 0
    report = output / request.REPORT_NAME
    persisted = report.read_text(encoding="utf-8")
    assert str(tmp_path) not in persisted
    assert os.stat(output).st_mode & 0o777 == 0o700
    assert os.stat(report).st_mode & 0o777 == 0o600
    assert os.stat(output / request.PLAN_DIRECTORY).st_mode & 0o777 == 0o700

    verified = request._load_verified_song_disjoint_private_pilot_request(report)
    assert verified["document"] == json.loads(persisted)
    assert verified["plan"]["corpus"]["track_id"] == "new-song"

    tampered = verified["document"]
    tampered["source_distinction"]["byte_distinct"] = False
    tampered["document_sha256"] = _document_sha256(tampered)
    report.write_text(
        json.dumps(tampered, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="source distinction"):
        request._load_verified_song_disjoint_private_pilot_request(report)


def test_private_pilot_request_rejects_input_drift_and_removes_partial_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _context(tmp_path)
    second = deepcopy(first)
    second["source_observation"]["files"][0]["sha256"] = "f" * 64
    calls = iter((first, second))
    monkeypatch.setattr(
        request, "_load_request_inputs", lambda *a, **k: next(calls)
    )
    monkeypatch.setattr(
        request, "_require_output_disjoint_from_inputs", lambda *a, **k: None
    )
    output = tmp_path / "request"

    with pytest.raises(ValueError, match="inputs changed"):
        request._prepare_song_disjoint_private_pilot_request(
            "authorization.json",
            reference_v2_execution_path="reference.json",
            reference_stitch_package_dir="reference-stitch",
            corpus_manifest_path=_corpus(tmp_path),
            track_id="new-song",
            repository_root="repository",
            runtime_launcher_path="runtime",
            source_root="source",
            checkpoint_path="checkpoint",
            companion_root="companions",
            out_dir=output,
        )

    assert not output.exists()


def test_private_pilot_request_rejects_reference_source_reuse() -> None:
    digest = "a" * 64
    with pytest.raises(ValueError, match="not distinct"):
        request._require_source_distinction(
            {
                "canonical_clock": {
                    "pcm24_int32_sequence_sha256": digest,
                }
            },
            inputs={"reference_source_pcm24_sha256": digest},
        )


def test_private_pilot_request_loader_rejects_changed_plan_audio(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path)
    monkeypatch.setattr(request, "_load_request_inputs", lambda *a, **k: context)
    monkeypatch.setattr(
        request, "_require_output_disjoint_from_inputs", lambda *a, **k: None
    )
    output = tmp_path / "request"
    result = request._prepare_song_disjoint_private_pilot_request(
        "authorization.json",
        reference_v2_execution_path="reference.json",
        reference_stitch_package_dir="reference-stitch",
        corpus_manifest_path=_corpus(tmp_path),
        track_id="new-song",
        repository_root="repository",
        runtime_launcher_path="runtime",
        source_root="source",
        checkpoint_path="checkpoint",
        companion_root="companions",
        out_dir=output,
    )
    plan = json.loads(Path(result["plan_report"]).read_text(encoding="utf-8"))
    chunk = output / request.PLAN_DIRECTORY / plan["chunks"][0]["audio_artifact"]["path"]
    chunk.chmod(0o600)
    with chunk.open("ab") as handle:
        handle.write(b"changed")

    with pytest.raises(ValueError, match="artifact hash"):
        request._load_verified_song_disjoint_private_pilot_request(
            output / request.REPORT_NAME
        )


def _corpus(root: Path) -> Path:
    track = root / "corpus" / "new-song"
    source = track / "ORIGINAL" / "song.wav"
    source.parent.mkdir(parents=True, exist_ok=True)
    frames = 700_000
    time = np.arange(frames, dtype=np.float64) / 44_100
    tone = (0.15 * np.sin(2.0 * np.pi * 220.0 * time)).astype("float32")
    soundfile.write(source, np.column_stack([tone, tone]), 44_100, subtype="PCM_24")
    manifest = root / "corpus" / "corpus.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "sunofriend.authorised-separation-corpus.v1",
                "artist": {
                    "name": "Owner",
                    "soundcloud_profile": "https://example.test/owner",
                },
                "permission": {
                    "authority": "creator_and_copyright_holder",
                    "scope": "new private pilot song",
                    "allowed_use": "download, study, transform and reuse",
                    "condition": "credit Owner",
                    "recorded_on": "2026-08-05",
                },
                "tracks": [
                    {
                        "id": "new-song",
                        "title": "New song",
                        "directory": "new-song",
                        "evaluation_state": "ready_for_excerpt_selection",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


def _context(root: Path) -> dict[str, object]:
    reference_stitch = root / "reference-stitch"
    reference_stitch.mkdir(exist_ok=True)
    reference_stitch.chmod(0o700)
    reference_stitch_path = reference_stitch / "private-separation-full-song-stitch.json"
    reference_stitch_path.write_text("reference\n", encoding="utf-8")
    reference_stitch_path.chmod(0o600)
    authorization_document = {
        "document_sha256": "1" * 64,
        "permissions": {"bounded_private_pilot_use": True},
    }
    reference_document = {
        "document_sha256": "2" * 64,
        "bindings": {},
    }
    return {
        "authorization": {
            "path": root / "authorization.json",
            "sha256": "3" * 64,
            "document": authorization_document,
        },
        "reference_execution": {
            "path": root / "reference.json",
            "sha256": "4" * 64,
            "document": reference_document,
        },
        "reference_stitch_package": reference_stitch,
        "reference_stitch_path": reference_stitch_path,
        "reference_stitch": {"document_sha256": "5" * 64},
        "reference_source_pcm24_sha256": "6" * 64,
        "repository_root": root / "repository",
        "upstream": {"verification_sha256": "7" * 64},
        "code": {
            item: {"bytes": 100, "sha256": format(index, "x") * 64}
            for index, item in enumerate(request._CODE_FILES, start=8)
        },
        "runtime_launcher_path": root / "runtime" / "bin" / "python",
        "runtime": _runtime(),
        "source_root": root / "source",
        "source_observation": {
            "status": "verified_not_imported",
            "files": [
                {"path": "model.py", "bytes": 10, "sha256": "b" * 64}
            ],
        },
        "checkpoint_path": root / "model.safetensors",
        "checkpoint_observation": {
            "schema": "sunofriend.private-safetensors-static-inspection.v1",
            "status": "verified_header_only_not_deserialized",
            "bytes": request.CONVERSION_CHECKPOINT_BYTES,
            "sha256": request.CONVERSION_CHECKPOINT_SHA256,
            "container": "safetensors",
            "header_bytes": 100,
            "data_bytes": request.CONVERSION_CHECKPOINT_BYTES - 100,
            "tensor_count": 708,
            "tensor_names_sha256": "d" * 64,
            "dtype_counts": {"BF16": 708},
            "tensor_values_observed": False,
            "tensor_library_imported": False,
        },
        "companion_root": root / "companions",
        "companion_observation": {
            "all_cryptographic_identities_verified": True,
            "files": {
                "LICENSE": {"bytes": 10, "sha256": "e" * 64},
                "config.json": {"bytes": 20, "sha256": "f" * 64},
            },
        },
    }


def _runtime() -> dict[str, object]:
    file_binding = {
        "sha256": "a" * 64,
        "bytes": 100,
        "stat_identity_sha256": "b" * 64,
    }
    return {
        "python_version": "3.12.10",
        "launcher_entry": {
            "kind": "symlink",
            "stat_identity_sha256": "c" * 64,
            "target_sha256": "d" * 64,
        },
        "resolved_runtime": file_binding,
        "pyvenv_config": file_binding,
        "runtime_environment": {"stat_identity_sha256": "e" * 64},
        "runtime_bin": {"stat_identity_sha256": "f" * 64},
        "base_runtime": {"stat_identity_sha256": "0" * 64},
    }
