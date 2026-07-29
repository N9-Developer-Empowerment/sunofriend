from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from pathlib import Path

import pytest

from sunofriend.separation_contract import (
    SEPARATION_RESIDUAL_DEFINITION,
    SEPARATION_RUN_SCHEMA,
    SEPARATION_RUN_SCHEMA_V1,
    SEPARATION_RUN_SCHEMA_V2,
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
            "backend_id": "sunofriend-fake",
            "package": "sunofriend",
            "version": "0.4.0",
            "commit": _sha("3")[:40],
            "code_license": "Apache-2.0",
            "training_data_note": "Deterministic fake with no training data",
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
                "name": "python",
                "implementation": "CPython",
                "python_version": "3.11.13",
                "system": "Darwin",
                "machine": "arm64",
            },
            "device": "mps",
            "settings": {
                "overlap": 0.25,
                "segments": 8,
            },
            "seed": 17,
            "wall_time_seconds": 12.5,
            "command": [
                "sunofriend-fake-separation",
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
            "status": "review_required",
            "reconstruction": {
                "maximum_absolute_error": 0.0000001,
                "rms_error": 0.00000001,
                "threshold": 0.000001,
                "passed": True,
            },
            "leakage": {
                "bass": {
                    "status": "measured",
                    "metric": "reference_bleed_ratio_v1",
                    "score": 0.1,
                    "reference_id": f"sha256:{_sha('7')}",
                },
                "drums": {
                    "status": "measured",
                    "metric": "reference_bleed_ratio_v1",
                    "score": 0.2,
                    "reference_id": f"sha256:{_sha('8')}",
                },
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
    arguments["run_plan"] = {
        "schema": "sunofriend.separation-run-plan.v1",
        "request_fingerprint_sha256": arguments[
            "request_fingerprint_sha256"
        ],
        "runner": {
            "schema": "sunofriend.separation-parent.v1",
            "version": "1",
            "module": "sunofriend.separation",
            "module_sha256": _sha("3"),
            "package": arguments["backend"]["package"],
            "package_version": arguments["backend"]["version"],
            "backend_policy": "controlled-fake-only",
            "cache_replay": "unsupported",
        },
        "backend": {
            "backend_id": arguments["backend"]["backend_id"],
            "class": "sunofriend.separation.FakeSeparationBackend",
            "module_sha256": _sha("3"),
            "package": arguments["backend"]["package"],
            "version": arguments["backend"]["version"],
            "commit": arguments["backend"]["commit"],
            "code_license": arguments["backend"]["code_license"],
            "training_data_note": arguments["backend"][
                "training_data_note"
            ],
        },
        "checkpoint": {
            field_name: arguments["checkpoint"][field_name]
            for field_name in (
                "checkpoint_id",
                "sha256",
                "weights_license",
                "distribution_policy",
            )
        },
        "runtime": dict(arguments["execution"]["runtime"]),
        "device": arguments["execution"]["device"],
        "command": list(arguments["execution"]["command"]),
        "requested_roles": list(arguments["roles"]["requested"]),
        "settings": dict(arguments["execution"]["settings"]),
        "seed": arguments["execution"]["seed"],
    }
    arguments["run_plan_sha256"] = hashlib.sha256(
        (
            json.dumps(
                arguments["run_plan"],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()
    arguments["run_id"] = (
        f"separation-run:{arguments['run_plan_sha256']}"
    )
    return arguments


def _complete_receipt() -> SeparationRunReceipt:
    return build_separation_run_receipt(**_complete_arguments())


def _legacy_v1_document() -> dict:
    document = _complete_receipt().to_dict()
    document["schema"] = SEPARATION_RUN_SCHEMA_V1
    document.pop("run_plan_sha256")
    document.pop("run_plan")
    document["quality"]["status"] = "passed"
    document["quality"]["leakage"] = {
        "bass": 0.1,
        "drums": 0.2,
    }
    document["receipt_sha256"] = separation_run_receipt_sha256(document)
    return document


def _document_with_change(path: tuple, value) -> dict:
    document = _complete_receipt().to_dict()
    cursor = document
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = value
    document["receipt_sha256"] = separation_run_receipt_sha256(document)
    return document


def _resign_v2_plan(document: dict) -> None:
    plan_sha256 = hashlib.sha256(
        (
            json.dumps(
                document["run_plan"],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()
    document["run_plan_sha256"] = plan_sha256
    document["run_id"] = f"separation-run:{plan_sha256}"
    document["receipt_sha256"] = separation_run_receipt_sha256(document)


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
    assert document["schema"] == SEPARATION_RUN_SCHEMA_V2
    assert document["run_plan_sha256"] == hashlib.sha256(
        (
                json.dumps(
                    document["run_plan"],
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            + "\n"
        ).encode("utf-8")
    ).hexdigest()
    assert document["run_id"] == (
        f"separation-run:{document['run_plan_sha256']}"
    )
    assert loaded.run_plan_sha256 == document["run_plan_sha256"]
    assert loaded.to_dict()["run_plan"] == document["run_plan"]
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


def test_canonical_legacy_v1_float_receipt_remains_loadable() -> None:
    document = _legacy_v1_document()

    validated = validate_separation_run_receipt(document)
    loaded = SeparationRunReceipt.from_json(
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )

    assert validated == document
    assert loaded.to_dict() == document
    assert loaded.schema == SEPARATION_RUN_SCHEMA_V1
    assert loaded.quality["leakage"] == {
        "bass": 0.1,
        "drums": 0.2,
    }


def test_v1_and_v2_quality_representations_are_not_interchangeable() -> None:
    structured_v1 = _complete_receipt().to_dict()
    structured_v1["schema"] = SEPARATION_RUN_SCHEMA_V1
    structured_v1.pop("run_plan_sha256")
    structured_v1.pop("run_plan")
    structured_v1["receipt_sha256"] = separation_run_receipt_sha256(
        structured_v1
    )
    with pytest.raises(ValueError, match="finite number"):
        validate_separation_run_receipt(structured_v1)

    float_v2 = _complete_receipt().to_dict()
    float_v2["quality"]["leakage"] = {
        "bass": 0.1,
        "drums": 0.2,
    }
    float_v2["receipt_sha256"] = separation_run_receipt_sha256(float_v2)
    with pytest.raises(ValueError, match="must be an object"):
        validate_separation_run_receipt(float_v2)


def test_v2_run_plan_hash_and_runner_module_are_attested() -> None:
    tampered = _complete_receipt().to_dict()
    tampered["run_plan"]["runner"]["module_sha256"] = _sha("4")
    tampered["receipt_sha256"] = separation_run_receipt_sha256(tampered)
    with pytest.raises(ValueError, match="run_plan_sha256 does not match"):
        validate_separation_run_receipt(tampered)

    resigned = _complete_receipt().to_dict()
    resigned["run_plan"]["runner"]["module_sha256"] = _sha("4")
    _resign_v2_plan(resigned)
    assert (
        validate_separation_run_receipt(resigned)["run_plan"]["runner"][
            "module_sha256"
        ]
        == _sha("4")
    )

    placeholder = _complete_receipt().to_dict()
    placeholder["run_plan"]["runner"]["package_version"] = "<VERSION>"
    _resign_v2_plan(placeholder)
    with pytest.raises(ValueError, match="placeholder"):
        validate_separation_run_receipt(placeholder)

    path_bearing = _complete_receipt().to_dict()
    path_bearing["run_plan"]["runtime"]["config"] = "models/local.json"
    _resign_v2_plan(path_bearing)
    with pytest.raises(ValueError, match="path, URL or placeholder"):
        validate_separation_run_receipt(path_bearing)


@pytest.mark.parametrize(
    ("plan_path", "value", "message"),
    [
        (
            ("request_fingerprint_sha256",),
            _sha("4"),
            "request fingerprint",
        ),
        (
            ("checkpoint", "distribution_policy"),
            "Different local distribution",
            "checkpoint.distribution_policy",
        ),
        (
            ("requested_roles",),
            ["bass"],
            "roles.requested",
        ),
        (
            ("runtime", "machine"),
            "x86_64",
            "execution.runtime",
        ),
        (
            ("device",),
            "cpu",
            "execution.device",
        ),
        (
            ("command",),
            ["another-safe-command"],
            "execution.command",
        ),
        (
            ("settings", "overlap"),
            0.5,
            "execution.settings",
        ),
        (
            ("seed",),
            18,
            "execution.seed",
        ),
    ],
)
def test_v2_run_plan_is_cross_bound_to_receipt(
    plan_path: tuple,
    value,
    message: str,
) -> None:
    document = _complete_receipt().to_dict()
    cursor = document["run_plan"]
    for part in plan_path[:-1]:
        cursor = cursor[part]
    cursor[plan_path[-1]] = value
    _resign_v2_plan(document)

    with pytest.raises(ValueError, match=message):
        validate_separation_run_receipt(document)


def test_v2_run_plan_backend_identity_is_cross_bound_to_receipt() -> None:
    document = _complete_receipt().to_dict()
    document["run_plan"]["backend"]["version"] = "0.5.0"
    document["run_plan"]["runner"]["package_version"] = "0.5.0"
    _resign_v2_plan(document)

    with pytest.raises(ValueError, match="backend.version"):
        validate_separation_run_receipt(document)


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


def test_receipt_rejects_non_nfc_and_casefold_colliding_paths() -> None:
    non_nfc = _document_with_change(
        ("outputs", "targets", 0, "path"),
        "STEMS/cafe\u0301.wav",
    )
    with pytest.raises(ValueError, match="safe relative POSIX path"):
        validate_separation_run_receipt(non_nfc)

    collision = _document_with_change(
        ("outputs", "residuals", 0, "path"),
        "stems/BASS-TARGET.wav",
    )
    with pytest.raises(
        ValueError,
        match="Unicode NFC normalization and casefolding",
    ):
        validate_separation_run_receipt(collision)


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


def test_quality_covers_actual_roles_and_new_receipts_cannot_claim_passed() -> None:
    missing_role = _document_with_change(
        ("quality", "leakage"),
        {
            "bass": {
                "status": "measured",
                "metric": "reference_bleed_ratio_v1",
                "score": 0.1,
                "reference_id": f"sha256:{_sha('7')}",
            }
        },
    )
    with pytest.raises(ValueError, match="exactly match"):
        validate_separation_run_receipt(missing_role)

    unbound_pass = _document_with_change(
        ("quality", "status"),
        "passed",
    )
    with pytest.raises(ValueError, match="hashed acceptance profile"):
        validate_separation_run_receipt(unbound_pass)


def test_legacy_passed_quality_still_requires_non_silent_unclipped_outputs() -> None:
    silent = _legacy_v1_document()
    silent["outputs"]["targets"][0]["rms"] = 0.0
    silent["outputs"]["targets"][0]["peak"] = 0.0
    silent["outputs"]["targets"][0]["silence_fraction"] = 1.0
    silent["receipt_sha256"] = separation_run_receipt_sha256(silent)
    with pytest.raises(ValueError, match="review_required"):
        validate_separation_run_receipt(silent)

    clipped = _legacy_v1_document()
    clipped["outputs"]["targets"][0]["clipped_samples"] = 1
    clipped["receipt_sha256"] = separation_run_receipt_sha256(clipped)
    with pytest.raises(ValueError, match="review_required"):
        validate_separation_run_receipt(clipped)


def test_unbound_reconstruction_threshold_cannot_make_v2_quality_passed() -> None:
    document = _complete_receipt().to_dict()
    document["quality"]["reconstruction"] = {
        "maximum_absolute_error": 0.25,
        "rms_error": 0.1,
        "threshold": 0.5,
        "passed": True,
    }
    document["receipt_sha256"] = separation_run_receipt_sha256(document)
    assert (
        validate_separation_run_receipt(document)["quality"]["status"]
        == "review_required"
    )

    document["quality"]["status"] = "passed"
    document["receipt_sha256"] = separation_run_receipt_sha256(document)
    with pytest.raises(ValueError, match="hashed acceptance profile"):
        validate_separation_run_receipt(document)


def test_unmeasured_leakage_is_explicit_and_requires_review() -> None:
    arguments = _complete_arguments()
    arguments["quality"]["status"] = "review_required"
    arguments["quality"]["leakage"] = {
        role: {
            "status": "not_measured",
            "metric": None,
            "score": None,
            "reference_id": None,
        }
        for role in arguments["roles"]["actual"]
    }
    receipt = build_separation_run_receipt(**arguments)
    assert all(
        evidence["status"] == "not_measured"
        for evidence in receipt.to_dict()["quality"]["leakage"].values()
    )

    arguments["quality"]["status"] = "passed"
    with pytest.raises(ValueError, match="unmeasured leakage"):
        build_separation_run_receipt(**arguments)

    arguments["quality"]["status"] = "review_required"
    arguments["quality"]["leakage"]["bass"]["score"] = 0.0
    with pytest.raises(ValueError, match="must not claim"):
        build_separation_run_receipt(**arguments)


def test_missing_requested_role_requires_review() -> None:
    arguments = _complete_arguments()
    arguments["roles"]["actual"] = ["bass"]
    arguments["outputs"]["targets"] = [
        arguments["outputs"]["targets"][0]
    ]
    arguments["outputs"]["residuals"] = [
        arguments["outputs"]["residuals"][0]
    ]
    arguments["quality"]["leakage"] = {
        "bass": arguments["quality"]["leakage"]["bass"]
    }

    receipt = build_separation_run_receipt(**arguments)
    assert receipt.to_dict()["roles"] == {
        "requested": ["bass", "drums"],
        "actual": ["bass"],
    }

    legacy = receipt.to_dict()
    legacy["schema"] = SEPARATION_RUN_SCHEMA_V1
    legacy.pop("run_plan_sha256")
    legacy.pop("run_plan")
    legacy["quality"]["status"] = "passed"
    legacy["quality"]["leakage"] = {"bass": 0.1}
    legacy["receipt_sha256"] = separation_run_receipt_sha256(legacy)
    with pytest.raises(ValueError, match="missing requested roles"):
        validate_separation_run_receipt(legacy)


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
