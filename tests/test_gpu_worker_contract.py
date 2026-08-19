from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from sunofriend.gpu_worker_contract import (
    GPU_WORKER_REQUEST_SCHEMA,
    GPU_WORKER_RESULT_SCHEMA,
    build_gpu_worker_request,
    build_gpu_worker_result,
    validate_gpu_worker_request,
    validate_gpu_worker_result,
)
from sunofriend.source_receipt import document_sha256


def test_gpu_worker_request_and_result_are_bounded_path_free_evidence() -> None:
    request = _request()

    assert request["schema"] == GPU_WORKER_REQUEST_SCHEMA
    assert request["status"] == "planned_no_execution"
    assert request["method_natures"] == ["D", "T"]
    assert request["privacy"] == {
        "absolute_paths_permitted": False,
        "raw_audio_embedded": False,
        "credentials_embedded": False,
    }
    assert not any(request["authority"].values())
    assert validate_gpu_worker_request(request) == request

    result = _result(request)
    assert result["schema"] == GPU_WORKER_RESULT_SCHEMA
    assert result["request_document_sha256"] == request["document_sha256"]
    assert result["authority"] == {
        "technical_completion_only": True,
        "musical_selection": False,
        "representation_admitted": False,
        "checkpoint_promoted": False,
        "product_changed": False,
    }
    assert validate_gpu_worker_result(result, request=request) == result


def test_gpu_worker_contract_detects_document_tampering() -> None:
    request = _request()
    changed_request = deepcopy(request)
    changed_request["experiment_id"] = "changed-after-signing"
    with pytest.raises(ValueError, match="document SHA-256"):
        validate_gpu_worker_request(changed_request)

    result = _result(request)
    changed_result = deepcopy(result)
    changed_result["outputs"][0]["bytes"] += 1
    with pytest.raises(ValueError, match="document SHA-256"):
        validate_gpu_worker_result(changed_result, request=request)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("path", "outputs/features.npy"),
        ("absolute_path", "C:/private/features.npy"),
        ("credentials", {"token": "secret"}),
        ("raw_audio", "base64-private-audio"),
        ("private_notes", "owner-only observation"),
    ),
)
def test_gpu_worker_request_rejects_path_and_private_fields(
    field: str, value: Any
) -> None:
    with pytest.raises(ValueError, match="may not contain"):
        _request(model_extra={field: value})


@pytest.mark.parametrize(
    "authority_key",
    (
        "musical_selection",
        "representation_admitted",
        "checkpoint_promoted",
        "product_changed",
    ),
)
def test_gpu_worker_result_cannot_claim_musical_or_product_authority(
    authority_key: str,
) -> None:
    request = _request()
    result = _result(request)
    changed = deepcopy(result)
    changed["authority"][authority_key] = True
    _rehash(changed)

    with pytest.raises(ValueError, match="cannot grant musical or product authority"):
        validate_gpu_worker_result(changed, request=request)


def test_gpu_worker_result_must_retain_technical_only_authority() -> None:
    request = _request()
    result = _result(request)
    changed = deepcopy(result)
    changed["authority"]["technical_completion_only"] = False
    _rehash(changed)

    with pytest.raises(ValueError, match="technical completion only"):
        validate_gpu_worker_result(changed, request=request)


@pytest.mark.parametrize("field", ("experiment_id", "task_kind"))
def test_gpu_worker_result_identity_must_match_bound_request(field: str) -> None:
    request = _request()
    result = _result(request)
    changed = deepcopy(result)
    changed[field] = (
        "different-experiment"
        if field == "experiment_id"
        else "remix_identity_probe"
    )
    _rehash(changed)

    with pytest.raises(ValueError, match=field):
        validate_gpu_worker_result(changed, request=request)


def test_gpu_worker_result_rejects_a_different_request() -> None:
    request = _request()
    result = _result(request)
    different = _request(experiment_id="another-experiment")

    with pytest.raises(ValueError, match="does not bind"):
        validate_gpu_worker_result(result, request=different)


@pytest.mark.parametrize(
    ("section", "field", "value", "message"),
    (
        ("execution_policy", "network_allowed", True, "network"),
        ("execution_policy", "downloads_allowed", True, "downloads"),
        ("execution_policy", "maximum_retries", 1, "retries"),
        (
            "execution_policy",
            "cublas_workspace_config",
            "invalid",
            "CuBLAS workspace",
        ),
        ("training", "shuffled_label_control", False, "shuffled-label"),
    ),
)
def test_gpu_request_enforces_offline_reproducible_training(
    section: str, field: str, value: Any, message: str
) -> None:
    request = _request()
    changed = deepcopy(request)
    changed[section][field] = value
    _rehash(changed)

    with pytest.raises(ValueError, match=message):
        validate_gpu_worker_request(changed)


@pytest.mark.parametrize(
    ("section", "field", "value", "message"),
    (
        ("timings", "wall_seconds", 301.0, "wall time"),
        ("timings", "optimisation_steps", 201, "optimisation steps"),
        ("resources", "peak_gpu_bytes", 8_000_000_001, "GPU memory"),
        ("resources", "peak_ram_bytes", 16_000_000_001, "RAM"),
    ),
)
def test_gpu_result_is_checked_against_request_resource_ceilings(
    section: str, field: str, value: Any, message: str
) -> None:
    request = _request()
    result = _result(request)
    changed = deepcopy(result)
    changed[section][field] = value
    _rehash(changed)

    with pytest.raises(ValueError, match=message):
        validate_gpu_worker_result(changed, request=request)


def _request(
    *,
    experiment_id: str = "cycle-01-tiny-overfit",
    model_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    model = {
        "name": "tiny-pairwise-vocal-ranker",
        "version": "0.0.1",
        "checkpoint_sha256": "c" * 64,
    }
    if model_extra:
        model.update(model_extra)
    return build_gpu_worker_request(
        repository_commit="a" * 40,
        experiment_id=experiment_id,
        task_kind="tiny_overfit_test",
        method_natures=["D", "T"],
        authorised_asset_hashes=["b" * 64],
        dataset={
            "dataset_id": "synthetic-margin-v1",
            "schema": "sunofriend.synthetic-pairwise.v1",
            "sha256": "b" * 64,
            "synthetic": True,
            "group_count": 8,
        },
        model=model,
        windows=[],
        training={
            "seed": 1729,
            "optimiser": "adamw",
            "maximum_steps_per_arm": 200,
            "resume_step": 100,
            "batch_size": 32,
            "learning_rate": 0.001,
            "shuffled_label_control": True,
        },
        expected_outputs=[
            {
                "output_id": "training-metrics-json",
                "kind": "metrics",
                "media_type": "application/json",
            }
        ],
        resource_ceiling={
            "maximum_wall_seconds": 300,
            "maximum_gpu_bytes": 8_000_000_000,
            "maximum_ram_bytes": 16_000_000_000,
            "maximum_output_bytes": 10_000_000,
        },
        execution_policy={
            "network_allowed": False,
            "downloads_allowed": False,
            "maximum_retries": 0,
            "cublas_workspace_config": ":4096:8",
        },
        stop_rules=[
            "stop on non-finite loss",
            "stop before any resource ceiling is exceeded",
        ],
    )


def _result(request: dict[str, Any]) -> dict[str, Any]:
    return build_gpu_worker_result(
        request=request,
        status="complete",
        environment={
            "operating_system": "Windows",
            "gpu": "RTX 4080 Laptop GPU",
            "cuda": "12.8",
        },
        outputs=[
            {
                "output_id": "training-metrics-json",
                "kind": "metrics",
                "sha256": "d" * 64,
                "bytes": 4096,
            }
        ],
        timings={"wall_seconds": 12.5, "optimisation_steps": 200},
        resources={
            "peak_gpu_bytes": 1_000_000_000,
            "peak_ram_bytes": 2_000_000_000,
        },
        warnings=[],
    )


def _rehash(document: dict[str, Any]) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)
