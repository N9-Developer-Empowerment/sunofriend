from __future__ import annotations

from copy import deepcopy
import math
from typing import Any, Callable

import pytest

from sunofriend.gpu_canary import (
    EXPERIMENT_ID,
    SYNTHETIC_FIXTURE_SCHEMA,
    build_c0_canary_request,
    build_synthetic_fixture,
)
from sunofriend.gpu_worker_contract import (
    GPU_WORKER_REQUEST_SCHEMA,
    GPU_WORKER_RESULT_SCHEMA,
    build_gpu_worker_result,
    validate_gpu_worker_request,
    validate_gpu_worker_result,
)
from sunofriend.source_receipt import document_sha256


SEED = 1729
TRAIN_GROUP_IDS = [f"composition-{index:02d}" for index in range(12)]
HELDOUT_GROUP_IDS = [f"composition-{index:02d}" for index in range(12, 16)]
TRAIN_COMPOSITION_IDS = TRAIN_GROUP_IDS
HELDOUT_COMPOSITION_IDS = HELDOUT_GROUP_IDS


def test_c0_request_and_result_are_exact_hash_bound_technical_evidence() -> None:
    fixture = build_synthetic_fixture()
    request = _request()

    assert request == _request()
    assert request["schema"] == GPU_WORKER_REQUEST_SCHEMA
    assert request["experiment_id"] == EXPERIMENT_ID
    assert request["dataset"]["schema"] == SYNTHETIC_FIXTURE_SCHEMA
    assert request["dataset"]["sha256"] == document_sha256(fixture)
    assert request["dataset"]["generation_seed"] == SEED
    assert request["dataset"]["train_group_ids"] == TRAIN_GROUP_IDS
    assert request["dataset"]["heldout_group_ids"] == HELDOUT_GROUP_IDS
    assert set(TRAIN_GROUP_IDS).isdisjoint(HELDOUT_GROUP_IDS)
    assert request["model"] == _expected_model()
    assert request["training"] == _expected_training()
    assert request["expected_outputs"] == _expected_outputs()
    assert request["windows"] == []
    assert request["execution_policy"] == {
        "network_allowed": False,
        "downloads_allowed": False,
        "maximum_retries": 0,
        "cublas_workspace_config": ":4096:8",
    }
    assert not any(request["authority"].values())
    assert validate_gpu_worker_request(request) == request

    result = _result(request)
    assert result["schema"] == GPU_WORKER_RESULT_SCHEMA
    assert result["request_document_sha256"] == request["document_sha256"]
    assert result["repository_commit"] == request["repository_commit"]
    assert result["experiment_id"] == request["experiment_id"]
    assert result["task_kind"] == request["task_kind"]
    assert result["training_evidence"] == _training_evidence(request)
    assert result["resources"]["output_bytes"] == sum(
        row["bytes"] for row in result["outputs"]
    )
    assert result["authority"] == {
        "technical_completion_only": True,
        "musical_selection": False,
        "representation_admitted": False,
        "checkpoint_promoted": False,
        "product_changed": False,
    }
    assert validate_gpu_worker_result(result, request=request) == result


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda row: row["dataset"].update({"schema": "unknown.synthetic.v1"}),
            "dataset.*schema|C0",
        ),
        (
            lambda row: row["dataset"].update({"generation_seed": -1}),
            "generation.*seed|uint32",
        ),
        (
            lambda row: row["dataset"].update({"generation_seed": True}),
            "generation.*seed|uint32",
        ),
        (
            lambda row: row["dataset"]["heldout_group_ids"].append(TRAIN_GROUP_IDS[0]),
            "group.*disjoint|overlap",
        ),
        (
            lambda row: row["dataset"].update({"heldout_group_ids": []}),
            "heldout.*group|non-empty",
        ),
        (
            lambda row: row["dataset"].update({"group_count": 15}),
            "group_count|group.*count",
        ),
        (
            lambda row: row["dataset"]["train_group_ids"].append("../private"),
            "group.*ID|safe|path",
        ),
        (
            lambda row: row["model"].update({"input_features": 15}),
            "model|input.*features|architecture",
        ),
        (
            lambda row: row["training"].update({"optimiser": "sgd"}),
            "optimiser|AdamW|adamw",
        ),
        (
            lambda row: row["training"].update({"maximum_steps_per_arm": 201}),
            "200|maximum.*steps",
        ),
        (
            lambda row: row["training"].update({"resume_step": 99}),
            "resume|100",
        ),
        (
            lambda row: row["training"].update({"checkpoint_steps": [100]}),
            "checkpoint|200",
        ),
    ),
)
def test_c0_request_rejects_a_changed_dataset_or_training_protocol(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    changed = deepcopy(_request())
    mutate(changed)
    _rehash(changed)

    with pytest.raises(ValueError, match=message):
        validate_gpu_worker_request(changed)


@pytest.mark.parametrize(
    ("value", "message"),
    (
        (0.0, "learning_rate|positive"),
        (math.inf, "learning_rate|finite"),
        (math.nan, "learning_rate|finite"),
    ),
)
def test_c0_request_rejects_invalid_numeric_training_values(
    value: float, message: str
) -> None:
    changed = deepcopy(_request())
    changed["training"]["learning_rate"] = value
    if not math.isfinite(value):
        with pytest.raises(ValueError, match="finite JSON numbers"):
            _rehash(changed)
        return
    _rehash(changed)

    with pytest.raises(ValueError, match=message):
        validate_gpu_worker_request(changed)


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda row: row["expected_outputs"][1].update({"kind": "metrics"}),
            "output.*kind|checkpoint",
        ),
        (
            lambda row: row["expected_outputs"][1].update({"shape": {}}),
            "output.*shape|positive|parameter",
        ),
        (
            lambda row: row["expected_outputs"].pop(),
            "expected output|shuffled|checkpoint",
        ),
    ),
)
def test_c0_request_requires_exact_output_kinds_and_shapes(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    changed = deepcopy(_request())
    mutate(changed)
    _rehash(changed)

    with pytest.raises(ValueError, match=message):
        validate_gpu_worker_request(changed)


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda row: row["outputs"][0].update({"media_type": "text/plain"}),
            "media type|media_type",
        ),
        (
            lambda row: row["outputs"][1].update(
                {"shape": {"parameter_count": 1, "step": 100}}
            ),
            "shape",
        ),
        (
            lambda row: row["training_evidence"]["arms"][0].update({"steps": 199}),
            "steps|200|request",
        ),
        (
            lambda row: row["training_evidence"]["arms"][1].update(
                {"arm_id": "clean_resumed_changed"}
            ),
            "three C0 arms|arms",
        ),
        (
            lambda row: row["training_evidence"]["execution"].update(
                {"network_attempts": 1}
            ),
            "network",
        ),
        (
            lambda row: row["training_evidence"]["execution"].update({"retries": 1}),
            "retr",
        ),
        (
            lambda row: row["resources"].update({"output_bytes": 1}),
            "output.*bytes",
        ),
    ),
)
def test_c0_result_must_match_protocol_and_actual_execution(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    request = _request()
    changed = deepcopy(_result(request))
    mutate(changed)
    _rehash(changed)

    with pytest.raises(ValueError, match=message):
        validate_gpu_worker_result(changed, request=request)


@pytest.mark.parametrize("value", (math.inf, -math.inf, math.nan))
def test_c0_result_rejects_non_finite_training_measurements(value: float) -> None:
    request = _request()
    evidence = _training_evidence(request)
    evidence["arms"][0]["final_loss"] = value

    with pytest.raises(ValueError, match="finite|final_loss"):
        _build_result(request, training_evidence=evidence)


@pytest.mark.parametrize(
    ("section", "field", "value", "message"),
    (
        ("timings", "wall_seconds", 901.0, "wall time"),
        ("resources", "peak_gpu_bytes", 4_294_967_297, "GPU memory"),
        ("resources", "peak_ram_bytes", 8_589_934_593, "RAM"),
        ("resources", "output_bytes", 67_108_865, "output bytes"),
    ),
)
def test_c0_result_enforces_declared_resource_ceilings(
    section: str, field: str, value: Any, message: str
) -> None:
    request = _request()
    changed = deepcopy(_result(request))
    changed[section][field] = value
    _rehash(changed)

    with pytest.raises(ValueError, match=message):
        validate_gpu_worker_result(changed, request=request)


def test_c0_result_rejects_another_request_and_private_or_path_fields() -> None:
    request = _request()
    result = _result(request)
    other = deepcopy(request)
    other["repository_commit"] = "f" * 40
    _rehash(other)
    with pytest.raises(ValueError, match="does not bind|repository commit"):
        validate_gpu_worker_result(result, request=other)

    changed = deepcopy(result)
    changed["training_evidence"]["private_notes"] = "owner recording details"
    _rehash(changed)
    with pytest.raises(ValueError, match="may not contain|private_notes"):
        validate_gpu_worker_result(changed, request=request)


def test_c0_result_remains_technical_only() -> None:
    request = _request()
    changed = deepcopy(_result(request))
    changed["authority"]["checkpoint_promoted"] = True
    _rehash(changed)

    with pytest.raises(ValueError, match="musical or product authority"):
        validate_gpu_worker_result(changed, request=request)


def _request() -> dict[str, Any]:
    return build_c0_canary_request("a" * 40)


def _expected_model() -> dict[str, Any]:
    return {
        "name": "tiny-pairwise-pipeline-canary",
        "version": "0.0.1",
        "architecture": "linear16-tanh-linear1",
        "input_features": 16,
        "hidden_features": 16,
        "output_features": 1,
        "parameter_dtype": "float32",
        "initialisation_seed": SEED,
        "authority": "pipeline_test_only",
    }


def _expected_training() -> dict[str, Any]:
    return {
        "seed": SEED,
        "optimiser": "adamw",
        "maximum_steps_per_arm": 200,
        "resume_step": 100,
        "checkpoint_steps": [100, 200],
        "batch_size": 32,
        "learning_rate": 0.01,
        "shuffled_label_control": True,
        "deterministic_algorithms": True,
    }


def _expected_outputs() -> list[dict[str, Any]]:
    return [
        {
            "output_id": "metrics-json",
            "kind": "metrics",
            "media_type": "application/json",
            "shape": {"arm_count": 3, "scalar_metric_count": 3},
        },
        {
            "output_id": "checkpoint-step-100",
            "kind": "checkpoint",
            "media_type": "application/x-pytorch",
            "shape": {"parameter_count": 289, "step": 100},
        },
        {
            "output_id": "checkpoint-final-uninterrupted",
            "kind": "checkpoint",
            "media_type": "application/x-pytorch",
            "shape": {"parameter_count": 289, "step": 200},
        },
        {
            "output_id": "checkpoint-final-resumed",
            "kind": "checkpoint",
            "media_type": "application/x-pytorch",
            "shape": {"parameter_count": 289, "step": 200},
        },
        {
            "output_id": "checkpoint-final-shuffled",
            "kind": "checkpoint",
            "media_type": "application/x-pytorch",
            "shape": {"parameter_count": 289, "step": 200},
        },
    ]


def _training_evidence(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset": {
            "sha256": request["dataset"]["sha256"],
            "generation_seed": SEED,
            "dtype": "float32",
            "train_group_ids": TRAIN_GROUP_IDS,
            "heldout_group_ids": HELDOUT_GROUP_IDS,
            "train_composition_ids": TRAIN_COMPOSITION_IDS,
            "heldout_composition_ids": HELDOUT_COMPOSITION_IDS,
            "train_shape": [192, 16],
            "heldout_shape": [64, 16],
        },
        "model": {
            "architecture": "linear16-tanh-linear1",
            "input_features": 16,
            "hidden_features": 16,
            "output_features": 1,
            "parameter_dtype": "float32",
        },
        "execution": {
            **_expected_training(),
            "network_attempts": 0,
            "retries": 0,
        },
        "arms": [
            {
                "arm_id": "clean_uninterrupted",
                "steps": 200,
                "final_loss": 0.002,
                "heldout_accuracy": 0.96,
                "finite_losses": True,
            },
            {
                "arm_id": "clean_resumed",
                "steps": 200,
                "final_loss": 0.002,
                "heldout_accuracy": 0.96,
                "finite_losses": True,
            },
            {
                "arm_id": "shuffled_label_control",
                "steps": 200,
                "final_loss": 0.85,
                "heldout_accuracy": 0.52,
                "finite_losses": True,
            },
        ],
        "resume_equivalence": {
            "maximum_parameter_difference": 0.0,
            "maximum_optimiser_difference": 0.0,
            "tolerance": 1e-7,
            "passed": True,
        },
        "acceptance": {
            "clean_accuracy_at_least_0_90": True,
            "clean_advantage_at_least_0_20": True,
            "resume_equivalence_at_most_1e_7": True,
        },
    }


def _result(request: dict[str, Any]) -> dict[str, Any]:
    return _build_result(request, training_evidence=_training_evidence(request))


def _build_result(
    request: dict[str, Any], *, training_evidence: dict[str, Any]
) -> dict[str, Any]:
    outputs = [
        {
            **expected,
            "sha256": str(index) * 64,
            "bytes": 1000 + index,
        }
        for index, expected in enumerate(request["expected_outputs"], 1)
    ]
    return build_gpu_worker_result(
        request=request,
        status="complete",
        environment={
            "operating_system": "Windows",
            "gpu": "RTX 4080 Laptop GPU",
            "cuda": "12.8",
            "deterministic_algorithms": True,
            "cublas_workspace_config": ":4096:8",
        },
        outputs=outputs,
        timings={"wall_seconds": 12.5, "optimisation_steps": 200},
        resources={
            "peak_gpu_bytes": 1_000_000_000,
            "peak_ram_bytes": 2_000_000_000,
            "output_bytes": sum(row["bytes"] for row in outputs),
        },
        training_evidence=training_evidence,
        warnings=[],
    )


def _rehash(document: dict[str, Any]) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)
