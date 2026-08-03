from __future__ import annotations

import hashlib
import io
import json
import os
import wave
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import numpy as np
import pytest

from sunofriend import _separation_melroformer_native_staging as staging_verifier
from sunofriend import _separation_melroformer_native_worker as worker
from sunofriend._separation_checkpoint_canonical import plain
from sunofriend._separation_melroformer_native_transport import (
    _build_private_melroformer_native_request,
)
from sunofriend._separation_melroformer_pcm24_quarantine import (
    _materialize_private_melroformer_pcm24_quarantine,
    _pack_pcm24,
    _quantize_pcm24,
)
from sunofriend._separation_melroformer_real_bridge import (
    _load_private_authorised_excerpt_pcm24,
)
from sunofriend._separation_melroformer_supervision import (
    _expected_post_cpython_signal_state,
)
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)
from sunofriend._separation_python_import_closure import (
    _capture_python_import_closure_claim,
    _mark_python_import_closure_stable,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


def test_parent_reopens_real_worker_staging_and_returns_path_free_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared_staging(tmp_path, monkeypatch)

    first = staging_verifier._verify_private_melroformer_native_worker_staging(
        request=prepared["request"],
        child_result=prepared["child"],
        runtime_environment_root=prepared["runtime_root"],
        base_runtime_root=prepared["base_root"],
    )
    second = staging_verifier._verify_private_melroformer_native_worker_staging(
        request=prepared["request"],
        child_result=prepared["child"],
        runtime_environment_root=prepared["runtime_root"],
        base_runtime_root=prepared["base_root"],
    )

    assert first == second
    assert first["status"] == "private_worker_staging_parent_verified"
    assert first["quarantine"]["child_parent_evidence_identical"] is True
    assert first["python_import_closure"]["module_count"] == 1
    assert first["boundary"] == {
        "staging_entry_allowlist_verified": True,
        "owner_only_directories_verified": True,
        "regular_single_link_closure_claim_verified": True,
        "private_artifacts_independently_verified": True,
        "checkpoint_lease_remeasured": False,
        "native_session_remeasured": False,
        "live_observers_verified": False,
        "paths_retained": False,
    }
    assert all(value is False for value in first["permissions"].values())
    assert str(tmp_path) not in repr(first)


def test_parent_rejects_changed_closure_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared_staging(tmp_path, monkeypatch)
    closure = prepared["staging"] / "WORKER-EVIDENCE" / (
        "python-import-closure-claim.json"
    )
    closure.write_bytes(closure.read_bytes() + b" ")
    os.chmod(closure, 0o600)

    with pytest.raises(ValueError, match="byte count differs"):
        staging_verifier._verify_private_melroformer_native_worker_staging(
            request=prepared["request"],
            child_result=prepared["child"],
            runtime_environment_root=prepared["runtime_root"],
            base_runtime_root=prepared["base_root"],
        )


def test_parent_rejects_an_extra_staging_entry_before_reading_private_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared_staging(tmp_path, monkeypatch)
    (prepared["staging"] / "unexpected.txt").write_text("not admitted")

    with pytest.raises(ValueError, match="staging tree differs"):
        staging_verifier._verify_private_melroformer_native_worker_staging(
            request=prepared["request"],
            child_result=prepared["child"],
            runtime_environment_root=prepared["runtime_root"],
            base_runtime_root=prepared["base_root"],
        )


def test_parent_rejects_a_child_that_claims_checkpoint_path_reopen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepared_staging(tmp_path, monkeypatch)
    child = prepared["child"]
    child["model"]["bridge"]["checkpoint"]["path_reopened_by_loader"] = True

    with pytest.raises(ValueError, match="child result identity differs"):
        staging_verifier._verify_private_melroformer_native_worker_staging(
            request=prepared["request"],
            child_result=child,
            runtime_environment_root=prepared["runtime_root"],
            base_runtime_root=prepared["base_root"],
        )


def test_native_staging_verifier_has_no_public_route() -> None:
    assert staging_verifier.__all__ == ()
    assert "private-melroformer-native-staging" not in PUBLIC_COMMANDS
    assert "private-melroformer-native-staging" not in DIRECT_TUI_COMMANDS


def _prepared_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    repository = tmp_path / "repository"
    source_root = tmp_path / "source-overlay"
    runtime_root = tmp_path / "runtime-environment"
    base_root = tmp_path / "base-runtime"
    system_library = tmp_path / "system-library"
    system_usr_lib = tmp_path / "system-usr-lib"
    for directory in (
        repository,
        source_root,
        runtime_root,
        base_root,
        system_library,
        system_usr_lib,
    ):
        directory.mkdir(mode=0o700)
    roots = MappingProxyType(
        {
            "source_overlay": source_root,
            "runtime_environment": runtime_root,
            "repository": repository,
            "base_runtime": base_root,
            "system_library": system_library,
            "system_usr_lib": system_usr_lib,
        }
    )
    monkeypatch.setattr(
        staging_verifier,
        "_melroformer_python_import_roots",
        lambda **_kwargs: roots,
    )

    module_path = repository / "verified_module.py"
    module_path.write_text("VALUE = 1\n", encoding="utf-8")
    modules = {
        "verified_module": SimpleNamespace(
            __file__=str(module_path),
            __spec__=SimpleNamespace(origin=str(module_path)),
        )
    }
    closure = _mark_python_import_closure_stable(
        _capture_python_import_closure_claim(roots=roots, modules=modules),
        modules=modules,
    )

    source, vocals, instrumental = _arrays()
    authorisation_report = _authorised_excerpt(tmp_path, source)
    report_sha256 = hashlib.sha256(authorisation_report.read_bytes()).hexdigest()
    _loaded_source, authorisation = _load_private_authorised_excerpt_pcm24(
        np,
        report_path=authorisation_report,
        expected_report_sha256=report_sha256,
    )

    staging = tmp_path / "staging"
    staging.mkdir(mode=0o700)
    quarantine = _materialize_private_melroformer_pcm24_quarantine(
        destination=staging / "quarantine",
        source=source,
        vocals=vocals,
        instrumental=instrumental,
        np=np,
        allow_shared_attenuation=True,
    )
    closure_artifact = worker._write_private_closure_claim(staging, closure)
    worker_sha256 = "1" * 64
    companion_sha256 = "2" * 64
    source_manifest_sha256 = "4" * 64
    request = _build_private_melroformer_native_request(
        run_nonce="3" * 64,
        paths={
            "repository_root": str(repository),
            "source_root": str(source_root),
            "checkpoint_path": str(tmp_path / "checkpoint.safetensors"),
            "companion_root": str(tmp_path / "companions"),
            "authorisation_report_path": str(authorisation_report),
            "staging_directory": str(staging),
        },
        identities={
            "worker_source_sha256": worker_sha256,
            "checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
            "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
            "authorisation_report_sha256": report_sha256,
            "source_manifest_sha256": source_manifest_sha256,
            "companion_manifest_sha256": companion_sha256,
        },
        device="cpu",
    )
    child = {
        "schema": worker.SCHEMA,
        "status": worker.STATUS,
        "request_validated": True,
        "worker": {"bytes": 1, "sha256": worker_sha256},
        "companion_manifest": {
            "files": [],
            "manifest_sha256": companion_sha256,
        },
        "canaries": {
            "network_connect_errno": 1,
            "network_errno_name": "EPERM",
            "process_fork_errno": 1,
            "process_fork_errno_name": "EPERM",
            "outside_write_errno": 1,
            "outside_write_errno_name": "EPERM",
            "fixed_sandbox_environment_observed": True,
        },
        "signal_state": _expected_post_cpython_signal_state(),
        "model": {
            "authorisation": plain(authorisation),
            "bridge": {
                "candidate_id": "mlx-melroformer-kim-vocal-2",
                "source": {
                    "manifest_sha256": source_manifest_sha256,
                    "verified": True,
                },
                "checkpoint": {
                    "bytes": CONVERSION_CHECKPOINT_BYTES,
                    "sha256": CONVERSION_CHECKPOINT_SHA256,
                    "descriptor_pinned_during_tensor_load": True,
                    "transport": "inherited_read_only_descriptor",
                    "path_reopened_by_loader": False,
                    "descriptor_number_retained": False,
                },
            },
            "inference": {
                "geometry": {
                    "sample_rate": 44_100,
                    "channels": 2,
                    "frames": len(source),
                    "duration_seconds": len(source) / 44_100,
                    "maximum_frames": 661_500,
                },
                "outputs": {
                    "vocals": {"peak": float(np.max(np.abs(vocals)))},
                    "instrumental": {
                        "peak": float(np.max(np.abs(instrumental)))
                    },
                }
            },
        },
        "quarantine": plain(quarantine),
        "python_import_closure_claim": plain(closure_artifact),
        "descriptor_contract": {
            "request_frame_read_from_fd3": True,
            "result_frame_written_to_fd4": True,
            "checkpoint_loaded_from_fd5": True,
            "ready_release_completed_on_fd6_fd7": True,
            "checkpoint_path_reopened": False,
            "logical_descriptors_retained": False,
        },
        "permissions": {
            "publication_permitted": False,
            "automatic_selection_permitted": False,
            "product_route_permitted": False,
        },
    }
    return {
        "request": request,
        "child": child,
        "staging": staging,
        "runtime_root": runtime_root,
        "base_root": base_root,
    }


def _arrays() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    frames = 4_096
    timeline = np.arange(frames, dtype=np.float32) / np.float32(44_100.0)
    left = (0.3 * np.sin(2 * np.pi * 220 * timeline)).astype(np.float32)
    right = (0.25 * np.sin(2 * np.pi * 330 * timeline)).astype(np.float32)
    source = np.stack([left, right], axis=1)
    vocals = (source * np.float32(0.41)).astype(np.float32)
    instrumental = (source - vocals).astype(np.float32)
    return source, vocals, instrumental


def _authorised_excerpt(root: Path, source: np.ndarray) -> Path:
    audio_directory = root / "LOCAL-MODEL-INPUT"
    audio_directory.mkdir()
    audio_path = audio_directory / "source-44100.wav"
    payload = io.BytesIO()
    with wave.open(payload, "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(3)
        writer.setframerate(44_100)
        writer.writeframes(_pack_pcm24(_quantize_pcm24(source, np=np), np=np))
    audio_path.write_bytes(payload.getvalue())
    audio_sha256 = hashlib.sha256(audio_path.read_bytes()).hexdigest()
    duration = len(source) / 44_100
    document = {
        "schema": "sunofriend.private-authorised-separation-excerpt.v1",
        "status": "complete_review_required",
        "evidence_scope": "private_development_only",
        "corpus": {
            "track_id": "owned-example",
            "track_title": "Owned example",
            "permission": {
                "authority": "creator_and_copyright_holder",
                "allowed_use": "download, study, transform and reuse",
            },
        },
        "excerpt": {"start_seconds": 10.0, "end_seconds": 10.0 + duration},
        "original": {
            "local_model_input": {
                "artifact": {
                    "path": "LOCAL-MODEL-INPUT/source-44100.wav",
                    "bytes": audio_path.stat().st_size,
                    "sha256": audio_sha256,
                },
                "geometry": {
                    "channels": 2,
                    "duration_seconds": duration,
                    "frames": len(source),
                    "sample_rate": 44_100,
                },
            }
        },
        "permissions": {
            "accepted": False,
            "automatic_promotion": False,
            "automatic_selection": False,
            "production_eligible": False,
            "public_result": False,
            "simple_mode_available": False,
            "source_graph_activation": False,
            "studio_import_available": False,
        },
    }
    unsigned = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    document["document_sha256"] = hashlib.sha256(unsigned).hexdigest()
    report = root / "authorised-separation-excerpt.json"
    report.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    return report
