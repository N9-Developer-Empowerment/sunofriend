from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path

import pytest

from sunofriend.separation_contract import (
    SEPARATION_RESIDUAL_DEFINITION,
    SEPARATION_RUN_SCHEMA,
    SeparationAudioGeometry,
    SeparationBackendOutput,
    SeparationError,
    SeparationRequest,
    SeparationResult,
    SeparationRunReceipt,
    build_separation_run_receipt,
    separation_request_fingerprint_sha256,
    separation_run_receipt_sha256,
    validate_separation_run_receipt,
)


def _sha(character: str) -> str:
    return character * 64


def _geometry() -> dict:
    return {
        "sample_rate": 48_000,
        "channels": 2,
        "frames": 96_000,
        "duration_seconds": 2.0,
    }


def _artifact(
    role: str,
    character: str,
    *,
    residual: bool = False,
) -> dict:
    value = {
        "role": role,
        "path": f"STEMS/{role}-{'residual' if residual else 'target'}.wav",
        "sha256": _sha(character),
        "geometry": _geometry(),
        "peak": 0.75,
        "rms": 0.2,
        "silence_fraction": 0.01,
        "clipped_samples": 0,
    }
    if residual:
        value.update(
            {
                "target_sha256": _sha(
                    {"bass": "c", "drums": "d"}[role]
                ),
                "definition": SEPARATION_RESIDUAL_DEFINITION,
            }
        )
    return value


def _complete_arguments() -> dict:
    arguments = {
        "run_id": f"separation-run:{_sha('9')}",
        "status": "complete",
        "loadable": True,
        "source": {
            "source_id": f"sha256:{_sha('a')}",
            "source_sha256": _sha("a"),
            "canonical_sha256": _sha("b"),
            "geometry": _geometry(),
        },
        "scope": {
            "mode": "broad",
            "parent_node_id": f"node:{_sha('7')}",
        },
        "backend": {
            "backend_id": "demucs",
            "package": "demucs",
            "version": "4.0.1",
            "commit": _sha("1")[:40],
            "code_license": "MIT",
            "training_data_note": "Published training-data note reviewed",
        },
        "checkpoint": {
            "checkpoint_id": "htdemucs",
            "sha256": _sha("2"),
            "weights_license": "Private local evaluation profile",
            "hash_verified_before_load": True,
            "distribution_policy": "External and never bundled",
        },
        "roles": {
            "requested": ["bass", "drums"],
            "actual": ["bass", "drums"],
        },
        "execution": {
            "runtime": {
                "name": "isolated-worker",
                "version": "1.0",
            },
            "device": "mps",
            "settings": {
                "overlap": 0.25,
                "segments": 8,
            },
            "seed": 17,
            "wall_time_seconds": 12.5,
            "command": [
                "python",
                "-m",
                "sunofriend.ai_separation_worker",
                "<SOURCE>",
                "<CHECKPOINT>",
                "<OUTPUT>",
            ],
            "network_used": False,
        },
        "outputs": {
            "targets": [
                _artifact("bass", "c"),
                _artifact("drums", "d"),
            ],
            "residuals": [
                _artifact("bass", "e", residual=True),
                _artifact("drums", "f", residual=True),
            ],
        },
        "quality": {
            "path": "QUALITY/separation-quality.json",
            "sha256": _sha("6"),
            "status": "passed",
            "reconstruction": {
                "maximum_absolute_error": 0.0000001,
                "rms_error": 0.00000001,
                "threshold": 0.000001,
                "passed": True,
            },
            "leakage": {
                "bass": 0.1,
                "drums": 0.2,
            },
            "reconstruction_is_accuracy_evidence": False,
        },
        "effects": {
            "checkpoint_mutated": False,
            "model_downloaded": False,
            "network_used": False,
            "outside_output_writes": False,
            "source_mutated": False,
        },
        "error": None,
    }
    arguments["request_fingerprint_sha256"] = (
        separation_request_fingerprint_sha256(
            source=arguments["source"],
            scope=arguments["scope"],
            backend_id=arguments["backend"]["backend_id"],
            checkpoint_id=arguments["checkpoint"]["checkpoint_id"],
            checkpoint_sha256=arguments["checkpoint"]["sha256"],
            requested_roles=arguments["roles"]["requested"],
            settings=arguments["execution"]["settings"],
            seed=arguments["execution"]["seed"],
        )
    )
    return arguments


def _complete_receipt() -> SeparationRunReceipt:
    return build_separation_run_receipt(**_complete_arguments())


def _document_with_change(path: tuple, value) -> dict:
    document = _complete_receipt().to_dict()
    cursor = document
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = value
    document["receipt_sha256"] = separation_run_receipt_sha256(document)
    return document


def test_request_is_immutable_path_bearing_and_fingerprint_is_path_free(
    tmp_path: Path,
) -> None:
    request = SeparationRequest.create(
        source_path=tmp_path / "private song.wav",
        output_dir=tmp_path / "out",
        checkpoint_path=tmp_path / "models" / "model.ckpt",
        source_id=f"sha256:{_sha('a')}",
        source_sha256=_sha("a"),
        canonical_sha256=_sha("b"),
        source_geometry=_geometry(),
        scope="broad",
        parent_node_id=f"node:{_sha('7')}",
        backend_id="demucs",
        checkpoint_id="htdemucs",
        checkpoint_sha256=_sha("2"),
        requested_roles=["drums", "bass"],
        settings={"overlap": 0.25},
        seed=17,
    )
    relocated = SeparationRequest.create(
        source_path=tmp_path / "elsewhere.wav",
        output_dir=tmp_path / "another-out",
        checkpoint_path=tmp_path / "other-model.ckpt",
        source_id=request.source_id,
        source_sha256=request.source_sha256,
        canonical_sha256=request.canonical_sha256,
        source_geometry=request.source_geometry,
        scope=request.scope,
        parent_node_id=request.parent_node_id,
        backend_id=request.backend_id,
        checkpoint_id=request.checkpoint_id,
        checkpoint_sha256=request.checkpoint_sha256,
        requested_roles=["bass", "drums"],
        settings={"overlap": 0.25},
        seed=17,
    )

    assert request.requested_roles == ("bass", "drums")
    assert request.fingerprint_sha256 == relocated.fingerprint_sha256
    assert str(tmp_path) not in json.dumps(request.fingerprint_document())
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.backend_id = "other"  # type: ignore[misc]
    with pytest.raises(TypeError):
        request.settings["overlap"] = 0.5  # type: ignore[index]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_id", f"sha256:{_sha('f')}", "bind source_sha256"),
        ("checkpoint_sha256", "ABC", "lowercase SHA-256"),
        ("offline_required", False, "offline inference"),
    ],
)
def test_request_rejects_invalid_identities_and_online_mode(
    tmp_path: Path,
    field: str,
    value,
    message: str,
) -> None:
    arguments = {
        "source_path": tmp_path / "source.wav",
        "output_dir": tmp_path / "out",
        "checkpoint_path": tmp_path / "checkpoint",
        "source_id": f"sha256:{_sha('a')}",
        "source_sha256": _sha("a"),
        "canonical_sha256": _sha("b"),
        "source_geometry": SeparationAudioGeometry.from_dict(_geometry()),
        "scope": "broad",
        "parent_node_id": None,
        "backend_id": "demucs",
        "checkpoint_id": "htdemucs",
        "checkpoint_sha256": _sha("2"),
        "requested_roles": ("bass",),
        "settings": {},
        "offline_required": True,
    }
    arguments[field] = value
    with pytest.raises(ValueError, match=message):
        SeparationRequest(**arguments)


def test_request_rejects_alias_duplicate_and_non_finite_settings(
    tmp_path: Path,
) -> None:
    base = {
        "source_path": tmp_path / "source.wav",
        "output_dir": tmp_path / "out",
        "checkpoint_path": tmp_path / "checkpoint",
        "source_id": f"sha256:{_sha('a')}",
        "source_sha256": _sha("a"),
        "canonical_sha256": _sha("b"),
        "source_geometry": SeparationAudioGeometry.from_dict(_geometry()),
        "scope": "broad",
        "parent_node_id": None,
        "backend_id": "demucs",
        "checkpoint_id": "htdemucs",
        "checkpoint_sha256": _sha("2"),
    }
    with pytest.raises(ValueError, match="canonical role"):
        SeparationRequest(
            **base,
            requested_roles=("hats",),
        )
    with pytest.raises(ValueError, match="unique"):
        SeparationRequest(
            **base,
            requested_roles=("bass", "bass"),
        )
    with pytest.raises(ValueError, match="non-finite"):
        SeparationRequest(
            **base,
            requested_roles=("bass",),
            settings={"temperature": math.inf},
        )


def test_backend_result_is_separate_and_terminal() -> None:
    output = SeparationBackendOutput(
        role="bass",
        target_path=Path("/private/work/target.wav"),
        residual_path=Path("/private/work/residual.wav"),
    )
    result = SeparationResult(
        status="complete",
        outputs=(output,),
        diagnostics={"frames": 96_000},
    )
    assert result.succeeded is True
    assert result.cancelled is False
    with pytest.raises(ValueError, match="requires outputs"):
        SeparationResult(status="complete")
    with pytest.raises(ValueError, match="must not publish outputs"):
        SeparationResult(
            status="failed",
            outputs=(output,),
            error=SeparationError(
                code="worker_failed",
                message="Worker stopped",
                retryable=True,
            ),
        )
    with pytest.raises(ValueError, match="requires an error"):
        SeparationResult(status="cancelled")


def test_complete_receipt_round_trips_strictly_and_is_deeply_immutable() -> None:
    receipt = _complete_receipt()
    document = receipt.to_dict()
    loaded = SeparationRunReceipt.from_json(receipt.canonical_bytes())

    assert document["schema"] == SEPARATION_RUN_SCHEMA
    assert loaded.to_dict() == document
    assert (
        document["receipt_sha256"]
        == separation_run_receipt_sha256(document)
    )
    assert b"/Users/" not in receipt.canonical_bytes()
    with pytest.raises(TypeError):
        receipt.source["canonical_sha256"] = _sha("0")  # type: ignore[index]


def test_receipt_hash_excludes_only_receipt_sha256() -> None:
    document = _complete_receipt().to_dict()
    expected = document["receipt_sha256"]
    document["receipt_sha256"] = _sha("0")
    assert separation_run_receipt_sha256(document) == expected
    document["backend"]["version"] = "4.0.2"
    assert separation_run_receipt_sha256(document) != expected


def test_request_fingerprint_binds_source_model_roles_settings_and_seed() -> None:
    document = _document_with_change(
        ("execution", "settings", "overlap"),
        0.5,
    )
    with pytest.raises(ValueError, match="does not bind"):
        validate_separation_run_receipt(document)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("status",), "running", "terminal"),
        (("loadable",), False, "status/loadable"),
        (("source", "source_id"), f"sha256:{_sha('0')}", "bind"),
        (("roles", "requested"), ["drums", "bass"], "canonical role order"),
        (("roles", "actual"), ["bass", "hat"], "subset"),
        (("execution", "wall_time_seconds"), "NaN", "finite"),
        (("execution", "command"), ["python", "/tmp/worker.py"], "path or URL"),
        (("checkpoint", "hash_verified_before_load"), False, "verified"),
        (
            ("quality", "reconstruction_is_accuracy_evidence"),
            True,
            "must be false",
        ),
    ],
)
def test_complete_receipt_rejects_contract_violations(
    path: tuple,
    value,
    message: str,
) -> None:
    document = _document_with_change(path, value)
    with pytest.raises(ValueError, match=message):
        validate_separation_run_receipt(document)


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "/tmp/bass.wav",
        "../bass.wav",
        "STEMS/../bass.wav",
        "STEMS\\bass.wav",
        "file://private/bass.wav",
    ],
)
def test_receipt_rejects_unsafe_artifact_paths(unsafe_path: str) -> None:
    document = _document_with_change(
        ("outputs", "targets", 0, "path"),
        unsafe_path,
    )
    with pytest.raises(ValueError, match="safe relative POSIX path"):
        validate_separation_run_receipt(document)


def test_receipt_rejects_private_paths_in_nested_metadata_and_errors() -> None:
    document = _document_with_change(
        ("execution", "settings"),
        {"source_path": "/Users/example/private.wav"},
    )
    with pytest.raises(ValueError, match="private path field"):
        validate_separation_run_receipt(document)

    arguments = _complete_arguments()
    arguments.update(
        {
            "status": "failed",
            "loadable": False,
            "roles": {
                "requested": ["bass", "drums"],
                "actual": [],
            },
            "checkpoint": {
                **arguments["checkpoint"],
                "hash_verified_before_load": False,
            },
            "outputs": {"targets": [], "residuals": []},
            "quality": None,
            "error": {
                "code": "model_missing",
                "message": "Missing /Users/example/model.ckpt",
                "retryable": False,
            },
        }
    )
    with pytest.raises(ValueError, match="private path"):
        build_separation_run_receipt(**arguments)


def test_target_residual_pairs_must_match_role_hash_and_source_geometry() -> None:
    wrong_hash = _document_with_change(
        ("outputs", "residuals", 0, "target_sha256"),
        _sha("0"),
    )
    with pytest.raises(ValueError, match="not bound"):
        validate_separation_run_receipt(wrong_hash)

    wrong_role = _document_with_change(
        ("outputs", "residuals", 0, "role"),
        "cymbals",
    )
    with pytest.raises(ValueError, match="exactly match"):
        validate_separation_run_receipt(wrong_role)

    wrong_frames = _document_with_change(
        ("outputs", "targets", 0, "geometry", "frames"),
        48_000,
    )
    wrong_frames["outputs"]["targets"][0]["geometry"][
        "duration_seconds"
    ] = 1.0
    wrong_frames["receipt_sha256"] = separation_run_receipt_sha256(
        wrong_frames
    )
    with pytest.raises(ValueError, match="source geometry"):
        validate_separation_run_receipt(wrong_frames)


def test_residual_definition_and_reconstruction_evidence_are_explicit() -> None:
    document = _document_with_change(
        ("outputs", "residuals", 0, "definition"),
        "source-minus-model-output",
    )
    with pytest.raises(ValueError, match="unsupported"):
        validate_separation_run_receipt(document)

    document = _document_with_change(
        ("quality", "reconstruction", "passed"),
        False,
    )
    with pytest.raises(ValueError, match="pass flag"):
        validate_separation_run_receipt(document)


def test_quality_covers_actual_roles_and_flags_silent_or_clipped_outputs() -> None:
    missing_role = _document_with_change(
        ("quality", "leakage"),
        {"bass": 0.1},
    )
    with pytest.raises(ValueError, match="exactly match"):
        validate_separation_run_receipt(missing_role)

    silent = _document_with_change(
        ("outputs", "targets", 0, "rms"),
        0.0,
    )
    silent["outputs"]["targets"][0]["peak"] = 0.0
    silent["outputs"]["targets"][0]["silence_fraction"] = 1.0
    silent["receipt_sha256"] = separation_run_receipt_sha256(silent)
    with pytest.raises(ValueError, match="review_required"):
        validate_separation_run_receipt(silent)

    clipped = _document_with_change(
        ("outputs", "targets", 0, "clipped_samples"),
        1,
    )
    with pytest.raises(ValueError, match="review_required"):
        validate_separation_run_receipt(clipped)


def test_complete_receipt_requires_backend_commit_and_consistent_network_fact() -> None:
    no_commit = _document_with_change(("backend", "commit"), None)
    with pytest.raises(ValueError, match="requires a commit"):
        validate_separation_run_receipt(no_commit)

    network_mismatch = _document_with_change(
        ("effects", "network_used"),
        True,
    )
    with pytest.raises(ValueError, match="must match"):
        validate_separation_run_receipt(network_mismatch)


@pytest.mark.parametrize("status", ["failed", "cancelled", "abandoned"])
def test_non_complete_receipts_are_terminal_non_loadable_and_artifact_free(
    status: str,
) -> None:
    arguments = _complete_arguments()
    arguments.update(
        {
            "status": status,
            "loadable": False,
            "roles": {
                "requested": ["bass", "drums"],
                "actual": [],
            },
            "checkpoint": {
                **arguments["checkpoint"],
                "hash_verified_before_load": False,
            },
            "outputs": {"targets": [], "residuals": []},
            "quality": None,
            "error": {
                "code": f"run_{status}",
                "message": f"Separation run {status}",
                "retryable": status == "failed",
            },
        }
    )
    receipt = build_separation_run_receipt(**arguments)

    assert receipt.status == status
    assert receipt.loadable is False
    assert receipt.to_dict()["outputs"] == {
        "targets": [],
        "residuals": [],
    }
    assert receipt.quality is None


def test_non_complete_receipt_cannot_expose_outputs_or_quality() -> None:
    arguments = _complete_arguments()
    arguments.update(
        {
            "status": "failed",
            "loadable": False,
            "error": {
                "code": "worker_failed",
                "message": "Worker failed",
                "retryable": True,
            },
        }
    )
    with pytest.raises(ValueError, match="expose no artifacts"):
        build_separation_run_receipt(**arguments)

    arguments["outputs"] = {"targets": [], "residuals": []}
    with pytest.raises(ValueError, match="quality artifact"):
        build_separation_run_receipt(**arguments)


def test_receipt_rejects_unknown_fields_and_hash_drift() -> None:
    document = _complete_receipt().to_dict()
    document["local_source_path"] = "/Users/example/song.wav"
    document["receipt_sha256"] = separation_run_receipt_sha256(document)
    with pytest.raises(ValueError, match="unexpected"):
        validate_separation_run_receipt(document)

    document = _complete_receipt().to_dict()
    document["backend"]["version"] = "changed"
    with pytest.raises(ValueError, match="does not match"):
        validate_separation_run_receipt(document)
