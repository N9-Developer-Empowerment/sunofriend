"""Path-free request/result contracts for bounded RTX experiments."""

from __future__ import annotations

import math
import re
from typing import Any, Mapping, Sequence

from .source_receipt import document_sha256


GPU_WORKER_REQUEST_SCHEMA = "sunofriend.gpu-worker-request.v1"
GPU_WORKER_RESULT_SCHEMA = "sunofriend.gpu-worker-result.v1"

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_TASK_KINDS = frozenset(
    {
        "frozen_feature_extraction",
        "tiny_overfit_test",
        "pairwise_vocal_ranker",
        "remix_identity_probe",
    }
)
_STATUSES = frozenset({"complete", "failed", "stopped_resource_gate"})
_REQUIRED_NATURE = {
    "frozen_feature_extraction": "I",
    "tiny_overfit_test": "T",
    "pairwise_vocal_ranker": "T",
    "remix_identity_probe": "I",
}
_C0_EXPERIMENT_ID = "c0-synthetic-tiny-overfit-001"


def build_gpu_worker_request(
    *,
    repository_commit: str,
    experiment_id: str,
    task_kind: str,
    method_natures: Sequence[str],
    authorised_asset_hashes: Sequence[str],
    dataset: Mapping[str, Any],
    model: Mapping[str, Any] | None,
    windows: Sequence[Mapping[str, Any]],
    training: Mapping[str, Any] | None,
    expected_outputs: Sequence[Mapping[str, Any]],
    resource_ceiling: Mapping[str, Any],
    execution_policy: Mapping[str, Any],
    stop_rules: Sequence[str],
) -> dict[str, Any]:
    """Build one no-authority request after validating all path-free fields."""

    document: dict[str, Any] = {
        "schema": GPU_WORKER_REQUEST_SCHEMA,
        "status": "planned_no_execution",
        "repository_commit": repository_commit,
        "experiment_id": experiment_id,
        "task_kind": task_kind,
        "method_natures": list(method_natures),
        "authorised_asset_hashes": list(authorised_asset_hashes),
        "dataset": dict(dataset),
        "model": dict(model) if model is not None else None,
        "windows": [dict(item) for item in windows],
        "training": dict(training) if training is not None else None,
        "expected_outputs": [dict(item) for item in expected_outputs],
        "resource_ceiling": dict(resource_ceiling),
        "execution_policy": dict(execution_policy),
        "stop_rules": list(stop_rules),
        "privacy": {
            "absolute_paths_permitted": False,
            "raw_audio_embedded": False,
            "credentials_embedded": False,
        },
        "authority": {
            "musical_selection": False,
            "product_promotion": False,
            "model_installation": False,
            "checkpoint_download": False,
        },
    }
    _validate_request_fields(document)
    document["document_sha256"] = document_sha256(document)
    return document


def validate_gpu_worker_request(value: Mapping[str, Any]) -> dict[str, Any]:
    document = dict(value)
    if document.get("schema") != GPU_WORKER_REQUEST_SCHEMA:
        raise ValueError("unsupported GPU worker request schema")
    _verify_document_hash(document)
    _validate_request_fields(document)
    return document


def build_gpu_worker_result(
    *,
    request: Mapping[str, Any],
    status: str,
    environment: Mapping[str, Any],
    outputs: Sequence[Mapping[str, Any]],
    timings: Mapping[str, Any],
    resources: Mapping[str, Any],
    training_evidence: Mapping[str, Any] | None = None,
    warnings: Sequence[str] = (),
) -> dict[str, Any]:
    """Build one technical result that cannot make a musical decision."""

    request_document = validate_gpu_worker_request(request)
    expected_outputs = {
        str(row["output_id"]): row for row in request_document["expected_outputs"]
    }
    normalized_outputs: list[dict[str, Any]] = []
    for raw in outputs:
        row = dict(raw)
        expected = expected_outputs.get(str(row.get("output_id", "")))
        if expected is not None:
            row.setdefault("media_type", expected["media_type"])
            if "shape" in expected:
                row.setdefault("shape", expected["shape"])
        normalized_outputs.append(row)
    document: dict[str, Any] = {
        "schema": GPU_WORKER_RESULT_SCHEMA,
        "status": status,
        "request_document_sha256": request_document["document_sha256"],
        "repository_commit": request_document["repository_commit"],
        "experiment_id": request_document["experiment_id"],
        "task_kind": request_document["task_kind"],
        "environment": dict(environment),
        "outputs": normalized_outputs,
        "timings": dict(timings),
        "resources": dict(resources),
        "training_evidence": (
            dict(training_evidence) if training_evidence is not None else None
        ),
        "warnings": list(warnings),
        "authority": {
            "technical_completion_only": True,
            "musical_selection": False,
            "representation_admitted": False,
            "checkpoint_promoted": False,
            "product_changed": False,
        },
    }
    _validate_result_fields(document)
    document["document_sha256"] = document_sha256(document)
    return document


def validate_gpu_worker_result(
    value: Mapping[str, Any], *, request: Mapping[str, Any]
) -> dict[str, Any]:
    document = dict(value)
    if document.get("schema") != GPU_WORKER_RESULT_SCHEMA:
        raise ValueError("unsupported GPU worker result schema")
    _verify_document_hash(document)
    _validate_result_fields(document)
    request_document = validate_gpu_worker_request(request)
    if document.get("request_document_sha256") != request_document.get(
        "document_sha256"
    ):
        raise ValueError("GPU result does not bind the supplied request")
    if document.get("repository_commit") != request_document.get("repository_commit"):
        raise ValueError("GPU result repository commit does not match request")
    for key in ("experiment_id", "task_kind"):
        if document.get(key) != request_document.get(key):
            raise ValueError(f"GPU result {key} does not match request")
    requested_outputs = {
        str(row["output_id"]): row for row in request_document["expected_outputs"]
    }
    returned_outputs = {str(row["output_id"]): row for row in document["outputs"]}
    if not returned_outputs.keys() <= requested_outputs.keys():
        raise ValueError("GPU result contains an output not authorised by request")
    if document.get("status") == "complete" and (
        returned_outputs.keys() != requested_outputs.keys()
    ):
        raise ValueError("complete GPU result must contain every expected output")
    for output_id, row in returned_outputs.items():
        expected = requested_outputs[output_id]
        if row.get("kind") != expected.get("kind"):
            raise ValueError(f"GPU result output kind changed: {output_id}")
        if ("media_type" in row or "shape" in expected) and row.get(
            "media_type"
        ) != expected.get("media_type"):
            raise ValueError(f"GPU result output media type changed: {output_id}")
        if ("shape" in row or "shape" in expected) and row.get("shape") != expected.get(
            "shape"
        ):
            raise ValueError(f"GPU result output shape changed: {output_id}")
    ceiling = request_document["resource_ceiling"]
    if _finite_number(document["timings"].get("wall_seconds"), "wall_seconds") > int(
        ceiling["maximum_wall_seconds"]
    ):
        raise ValueError("GPU result exceeded maximum wall time")
    if int(document["resources"].get("peak_gpu_bytes", -1)) > int(
        ceiling["maximum_gpu_bytes"]
    ):
        raise ValueError("GPU result exceeded maximum GPU memory")
    if int(document["resources"].get("peak_ram_bytes", -1)) > int(
        ceiling["maximum_ram_bytes"]
    ):
        raise ValueError("GPU result exceeded maximum RAM")
    if sum(int(row["bytes"]) for row in returned_outputs.values()) > int(
        ceiling["maximum_output_bytes"]
    ):
        raise ValueError("GPU result exceeded maximum output bytes")
    reported_output_bytes = document["resources"].get("output_bytes")
    if request_document.get("experiment_id") == _C0_EXPERIMENT_ID:
        if isinstance(reported_output_bytes, bool) or int(
            reported_output_bytes if reported_output_bytes is not None else -1
        ) != sum(int(row["bytes"]) for row in returned_outputs.values()):
            raise ValueError("GPU result output bytes do not match returned outputs")
    if reported_output_bytes is not None and int(reported_output_bytes) > int(
        ceiling["maximum_output_bytes"]
    ):
        raise ValueError("GPU result exceeded maximum output bytes")
    training = request_document.get("training")
    if training is not None and int(
        document["timings"].get("optimisation_steps", -1)
    ) > int(training["maximum_steps_per_arm"]):
        raise ValueError("GPU result exceeded maximum optimisation steps")
    training_evidence = document.get("training_evidence")
    if request_document.get("experiment_id") == _C0_EXPERIMENT_ID:
        if training_evidence is None:
            raise ValueError("C0 result must include training evidence")
        _validate_training_evidence(
            training_evidence,
            request=request_document,
            result=document,
        )
    if request_document.get("task_kind") == "pairwise_vocal_ranker":
        _validate_offline_pairwise_result_envelope(
            document,
            request=request_document,
            returned_outputs=returned_outputs,
        )
    return document


def _validate_offline_pairwise_result_envelope(
    result: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    returned_outputs: Mapping[str, Mapping[str, Any]],
) -> None:
    """Keep the pairwise-vocal boundary safe even via the generic validator."""

    environment = _require_safe_mapping(result.get("environment"), "environment")
    if (
        environment.get("network_used") is not False
        or environment.get("network_attempts") != 0
        or environment.get("downloads_used") is not False
        or environment.get("deterministic_algorithms") is not True
        or environment.get("cublas_workspace_config")
        != request["execution_policy"].get("cublas_workspace_config")
    ):
        raise ValueError(
            "pairwise vocal GPU result must retain offline deterministic execution"
        )
    evidence = _require_safe_mapping(
        result.get("training_evidence"), "pairwise vocal training evidence"
    )
    if (
        evidence.get("synthetic_only") is not True
        or evidence.get("network_attempts") != 0
        or evidence.get("retries") != 0
    ):
        raise ValueError(
            "pairwise vocal GPU evidence must be synthetic, offline and zero-retry"
        )
    output_bytes = sum(int(row["bytes"]) for row in returned_outputs.values())
    if result["resources"].get("output_bytes") != output_bytes:
        raise ValueError("pairwise vocal GPU output byte receipt changed")


def _validate_request_fields(document: Mapping[str, Any]) -> None:
    if document.get("status") != "planned_no_execution":
        raise ValueError("GPU worker request status must be planned_no_execution")
    if not _COMMIT.fullmatch(str(document.get("repository_commit", ""))):
        raise ValueError("repository_commit must be a 40-character lowercase SHA")
    if not _SAFE_ID.fullmatch(str(document.get("experiment_id", ""))):
        raise ValueError("experiment_id must be a safe identifier")
    if document.get("task_kind") not in _TASK_KINDS:
        raise ValueError("unsupported GPU worker task_kind")
    natures = document.get("method_natures")
    if (
        not isinstance(natures, list)
        or not natures
        or any(item not in {"D", "I", "T", "H"} for item in natures)
    ):
        raise ValueError("method_natures must contain D, I, T or H labels")
    if len(set(natures)) != len(natures):
        raise ValueError("method_natures must be unique")
    required_nature = _REQUIRED_NATURE[str(document.get("task_kind"))]
    if required_nature not in natures:
        raise ValueError(
            f"{document.get('task_kind')} must declare {required_nature} work"
        )
    hashes = document.get("authorised_asset_hashes")
    if (
        not isinstance(hashes, list)
        or not hashes
        or any(not _SHA256.fullmatch(str(item)) for item in hashes)
    ):
        raise ValueError("authorised_asset_hashes must contain lowercase SHA-256s")
    if len(set(hashes)) != len(hashes):
        raise ValueError("authorised asset hashes must be unique")
    dataset = _require_safe_mapping(document.get("dataset"), "dataset")
    if not _SAFE_ID.fullmatch(str(dataset.get("dataset_id", ""))):
        raise ValueError("dataset.dataset_id must be safe")
    if not _SAFE_ID.fullmatch(str(dataset.get("schema", ""))):
        raise ValueError("dataset.schema must be safe")
    dataset_sha = str(dataset.get("sha256", ""))
    if not _SHA256.fullmatch(dataset_sha) or dataset_sha not in hashes:
        raise ValueError("dataset.sha256 must be an authorised lowercase SHA-256")
    if not isinstance(dataset.get("synthetic"), bool):
        raise ValueError("dataset.synthetic must be boolean")
    if int(dataset.get("group_count", 0)) <= 1:
        raise ValueError("dataset.group_count must be greater than one")
    model = document.get("model")
    if model is not None:
        _require_safe_mapping(model, "model")
        if not str(model.get("name", "")).strip():
            raise ValueError("model.name is required")
        checkpoint = model.get("checkpoint_sha256")
        if checkpoint is not None and not _SHA256.fullmatch(str(checkpoint)):
            raise ValueError("model.checkpoint_sha256 must be a lowercase SHA-256")
    windows = document.get("windows")
    if not isinstance(windows, list):
        raise ValueError("GPU request windows must be a list")
    if not windows and not (
        document.get("task_kind") == "tiny_overfit_test"
        and dataset.get("synthetic") is True
    ):
        raise ValueError("non-synthetic GPU requests require a time window")
    for row in windows:
        _require_safe_mapping(row, "window")
        if not _SAFE_ID.fullmatch(str(row.get("window_id", ""))):
            raise ValueError("window.window_id must be safe")
        start = float(row.get("start_seconds", -1.0))
        end = float(row.get("end_seconds", -1.0))
        if not math.isfinite(start) or not math.isfinite(end):
            raise ValueError("window bounds must be finite")
        if start < 0 or end <= start:
            raise ValueError("window bounds must be non-negative and ordered")
        if not _SHA256.fullmatch(str(row.get("source_sha256", ""))):
            raise ValueError("window.source_sha256 must be a lowercase SHA-256")
        if row.get("source_sha256") not in hashes:
            raise ValueError("window source is not in authorised_asset_hashes")
    window_ids = [str(row["window_id"]) for row in windows]
    if len(set(window_ids)) != len(window_ids):
        raise ValueError("window IDs must be unique")
    outputs = document.get("expected_outputs")
    if not isinstance(outputs, list) or not outputs:
        raise ValueError("GPU request requires expected outputs")
    for row in outputs:
        _require_safe_mapping(row, "expected output")
        if not _SAFE_ID.fullmatch(str(row.get("output_id", ""))):
            raise ValueError("expected output ID must be safe")
    output_ids = [str(row["output_id"]) for row in outputs]
    if len(set(output_ids)) != len(output_ids):
        raise ValueError("expected output IDs must be unique")
    for row in outputs:
        if not _SAFE_ID.fullmatch(str(row.get("kind", ""))):
            raise ValueError("expected output kind must be safe")
        if not str(row.get("media_type", "")).strip():
            raise ValueError("expected output media_type is required")
    training = document.get("training")
    if "T" in natures:
        training = _require_safe_mapping(training, "training")
        if not 0 <= int(training.get("seed", -1)) <= 2**32 - 1:
            raise ValueError("training.seed must be a uint32")
        if not _SAFE_ID.fullmatch(str(training.get("optimiser", ""))):
            raise ValueError("training.optimiser must be safe")
        for key in ("maximum_steps_per_arm", "batch_size", "resume_step"):
            value = training.get(key, 0)
            if isinstance(value, bool) or int(value) <= 0:
                raise ValueError(f"training.{key} must be positive")
        if int(training["resume_step"]) >= int(training["maximum_steps_per_arm"]):
            raise ValueError("training.resume_step must precede maximum steps")
        if _finite_number(training.get("learning_rate"), "learning_rate") <= 0:
            raise ValueError("training.learning_rate must be positive")
        if training.get("shuffled_label_control") is not True:
            raise ValueError("training must require a shuffled-label control")
    elif training is not None:
        raise ValueError("non-training request cannot contain training config")
    ceiling = _require_safe_mapping(
        document.get("resource_ceiling"), "resource ceiling"
    )
    for key in (
        "maximum_wall_seconds",
        "maximum_gpu_bytes",
        "maximum_ram_bytes",
        "maximum_output_bytes",
    ):
        value = ceiling.get(key, 0)
        if isinstance(value, bool) or int(value) <= 0:
            raise ValueError(f"resource_ceiling.{key} must be positive")
    policy = _require_safe_mapping(document.get("execution_policy"), "execution policy")
    if policy.get("network_allowed") is not False:
        raise ValueError("GPU worker network must be disabled")
    if policy.get("downloads_allowed") is not False:
        raise ValueError("GPU worker downloads must be disabled")
    if policy.get("maximum_retries") != 0:
        raise ValueError("GPU worker retries must be disabled")
    if "T" in natures and policy.get("cublas_workspace_config") not in {
        ":4096:8",
        ":16:8",
    }:
        raise ValueError(
            "GPU training must declare a deterministic CuBLAS workspace config"
        )
    stop_rules = document.get("stop_rules")
    if (
        not isinstance(stop_rules, list)
        or not stop_rules
        or any(not str(item).strip() for item in stop_rules)
    ):
        raise ValueError("stop_rules must contain non-empty rules")
    if document.get("experiment_id") == _C0_EXPERIMENT_ID:
        _validate_c0_request(document)
    _reject_private_or_path_fields(document)


def _validate_c0_request(document: Mapping[str, Any]) -> None:
    dataset = _require_safe_mapping(document.get("dataset"), "C0 dataset")
    if dataset.get("schema") != "sunofriend.synthetic-pairwise.v1":
        raise ValueError("C0 dataset schema changed")
    generation_seed = dataset.get("generation_seed")
    if (
        isinstance(generation_seed, bool)
        or not isinstance(generation_seed, int)
        or not 0 <= generation_seed <= 2**32 - 1
    ):
        raise ValueError("C0 dataset generation seed must be a uint32")
    train_ids = [f"composition-{index:02d}" for index in range(12)]
    heldout_ids = [f"composition-{index:02d}" for index in range(12, 16)]
    for key, expected in (
        ("train_group_ids", train_ids),
        ("heldout_group_ids", heldout_ids),
        ("train_composition_ids", train_ids),
        ("heldout_composition_ids", heldout_ids),
    ):
        observed = dataset.get(key)
        if not isinstance(observed, list) or not observed:
            raise ValueError(f"C0 {key} must be non-empty")
        if any(not _SAFE_ID.fullmatch(str(item)) for item in observed):
            raise ValueError(f"C0 {key} contains an unsafe group ID")
    if set(dataset["train_group_ids"]) & set(dataset["heldout_group_ids"]):
        raise ValueError("C0 train and heldout group IDs must be disjoint")
    for key, expected in (
        ("train_group_ids", train_ids),
        ("heldout_group_ids", heldout_ids),
        ("train_composition_ids", train_ids),
        ("heldout_composition_ids", heldout_ids),
    ):
        if dataset[key] != expected:
            raise ValueError(f"C0 {key} changed; group IDs must remain disjoint")
    expected_dataset = {
        "group_count": 16,
        "feature_count": 16,
        "example_count": 256,
        "feature_shape": [256, 16],
        "train_shape": [192, 16],
        "heldout_shape": [64, 16],
        "dtype": "float32",
        "train_group_count": 12,
        "heldout_group_count": 4,
        "generation_seed": 1729,
    }
    for key, expected in expected_dataset.items():
        if dataset.get(key) != expected:
            raise ValueError(f"C0 dataset {key} changed")

    model = _require_safe_mapping(document.get("model"), "C0 model")
    expected_model = {
        "name": "tiny-pairwise-pipeline-canary",
        "version": "0.0.1",
        "architecture": "linear16-tanh-linear1",
        "input_features": 16,
        "hidden_features": 16,
        "output_features": 1,
        "parameter_dtype": "float32",
        "initialisation_seed": 1729,
        "authority": "pipeline_test_only",
    }
    if dict(model) != expected_model:
        raise ValueError("C0 model architecture or identity changed")

    training = _require_safe_mapping(document.get("training"), "C0 training")
    expected_training = {
        "seed": 1729,
        "optimiser": "adamw",
        "maximum_steps_per_arm": 200,
        "resume_step": 100,
        "checkpoint_steps": [100, 200],
        "batch_size": 32,
        "learning_rate": 0.01,
        "shuffled_label_control": True,
        "deterministic_algorithms": True,
    }
    if dict(training) != expected_training:
        raise ValueError(
            "C0 training must retain AdamW, 200 steps, resume 100 and checkpoints 100/200"
        )

    expected_outputs = [
        {
            "output_id": "metrics-json",
            "kind": "metrics",
            "media_type": "application/json",
            "shape": {"arm_count": 3, "scalar_metric_count": 3},
        },
        *[
            {
                "output_id": output_id,
                "kind": "checkpoint",
                "media_type": "application/x-pytorch",
                "shape": {"parameter_count": 289, "step": step},
            }
            for output_id, step in (
                ("checkpoint-step-100", 100),
                ("checkpoint-final-uninterrupted", 200),
                ("checkpoint-final-resumed", 200),
                ("checkpoint-final-shuffled", 200),
            )
        ],
    ]
    if document.get("expected_outputs") != expected_outputs:
        raise ValueError("C0 expected output kind, shape or checkpoint roster changed")


def _validate_result_fields(document: Mapping[str, Any]) -> None:
    if document.get("status") not in _STATUSES:
        raise ValueError("unsupported GPU worker result status")
    if not _SHA256.fullmatch(str(document.get("request_document_sha256", ""))):
        raise ValueError("request_document_sha256 must be a lowercase SHA-256")
    if not _COMMIT.fullmatch(str(document.get("repository_commit", ""))):
        raise ValueError("repository_commit must be a lowercase Git SHA")
    if not _SAFE_ID.fullmatch(str(document.get("experiment_id", ""))):
        raise ValueError("experiment_id must be a safe identifier")
    if document.get("task_kind") not in _TASK_KINDS:
        raise ValueError("unsupported GPU worker task_kind")
    _require_safe_mapping(document.get("environment"), "environment")
    outputs = document.get("outputs")
    if not isinstance(outputs, list):
        raise ValueError("outputs must be a list")
    for row in outputs:
        _require_safe_mapping(row, "output")
        if not _SAFE_ID.fullmatch(str(row.get("output_id", ""))):
            raise ValueError("output.output_id must be safe")
        if not _SHA256.fullmatch(str(row.get("sha256", ""))):
            raise ValueError("output.sha256 must be a lowercase SHA-256")
        if int(row.get("bytes", -1)) < 0:
            raise ValueError("output.bytes must be non-negative")
        if "media_type" in row and not str(row.get("media_type", "")).strip():
            raise ValueError("output.media_type is required")
        if "shape" in row:
            _require_safe_mapping(row["shape"], "output.shape")
    output_ids = [str(row["output_id"]) for row in outputs]
    if len(set(output_ids)) != len(output_ids):
        raise ValueError("GPU result output IDs must be unique")
    _require_safe_mapping(document.get("timings"), "timings")
    timings = _require_safe_mapping(document.get("timings"), "timings")
    _finite_number(timings.get("wall_seconds"), "wall_seconds")
    if (
        isinstance(timings.get("optimisation_steps"), bool)
        or int(timings.get("optimisation_steps", -1)) < 0
    ):
        raise ValueError("timings.optimisation_steps must be non-negative")
    resources = _require_safe_mapping(document.get("resources"), "resources")
    for key in ("peak_gpu_bytes", "peak_ram_bytes"):
        if isinstance(resources.get(key), bool) or int(resources.get(key, -1)) < 0:
            raise ValueError(f"resources.{key} must be non-negative")
    if "output_bytes" in resources and (
        isinstance(resources["output_bytes"], bool)
        or int(resources["output_bytes"]) < 0
    ):
        raise ValueError("resources.output_bytes must be non-negative")
    warnings = document.get("warnings")
    if not isinstance(warnings, list) or any(
        not isinstance(item, str) for item in warnings
    ):
        raise ValueError("warnings must be a list of strings")
    authority = _require_safe_mapping(document.get("authority"), "authority")
    if authority.get("technical_completion_only") is not True:
        raise ValueError("GPU result authority must be technical completion only")
    if any(
        authority.get(key) is not False
        for key in (
            "musical_selection",
            "representation_admitted",
            "checkpoint_promoted",
            "product_changed",
        )
    ):
        raise ValueError("GPU result cannot grant musical or product authority")
    training_evidence = document.get("training_evidence")
    if training_evidence is not None:
        _require_safe_mapping(training_evidence, "training_evidence")
    _reject_private_or_path_fields(document)


def _validate_training_evidence(
    value: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    result: Mapping[str, Any],
) -> None:
    training = _require_safe_mapping(request.get("training"), "request training")
    dataset = _require_safe_mapping(value.get("dataset"), "training dataset evidence")
    if dataset.get("sha256") != request["dataset"].get("sha256"):
        raise ValueError("training evidence dataset does not bind the request")
    if dataset.get("generation_seed") != request["dataset"].get("generation_seed"):
        raise ValueError("training evidence generation seed changed")
    if dataset.get("dtype") != "float32":
        raise ValueError("training evidence must declare float32")
    for key in (
        "train_group_ids",
        "heldout_group_ids",
        "train_composition_ids",
        "heldout_composition_ids",
    ):
        rows = dataset.get(key)
        if (
            not isinstance(rows, list)
            or not rows
            or any(not _SAFE_ID.fullmatch(str(item)) for item in rows)
        ):
            raise ValueError(f"training evidence {key} must contain safe IDs")
        if len(rows) != len(set(rows)):
            raise ValueError(f"training evidence {key} must be unique")
    if set(dataset["train_group_ids"]) & set(dataset["heldout_group_ids"]):
        raise ValueError("training and heldout group IDs must be disjoint")
    if set(dataset["train_composition_ids"]) & set(dataset["heldout_composition_ids"]):
        raise ValueError("training and heldout composition IDs must be disjoint")
    if dataset.get("train_shape") != [192, 16] or dataset.get("heldout_shape") != [
        64,
        16,
    ]:
        raise ValueError("training evidence fixture shapes changed")

    model = _require_safe_mapping(value.get("model"), "training model evidence")
    request_model = _require_safe_mapping(request.get("model"), "request model")
    for key in (
        "architecture",
        "input_features",
        "hidden_features",
        "output_features",
        "parameter_dtype",
    ):
        if model.get(key) != request_model.get(key):
            raise ValueError(f"training evidence model {key} changed")

    execution = _require_safe_mapping(
        value.get("execution"), "training execution evidence"
    )
    for key in (
        "seed",
        "optimiser",
        "learning_rate",
        "batch_size",
        "maximum_steps_per_arm",
        "resume_step",
        "checkpoint_steps",
        "deterministic_algorithms",
    ):
        if execution.get(key) != training.get(key):
            raise ValueError(f"training execution {key} changed")
    if execution.get("network_attempts") != 0:
        raise ValueError("training evidence must report zero network attempts")
    if execution.get("retries") != 0:
        raise ValueError("training evidence must report zero retries")

    arms = value.get("arms")
    if not isinstance(arms, list) or [row.get("arm_id") for row in arms] != [
        "clean_uninterrupted",
        "clean_resumed",
        "shuffled_label_control",
    ]:
        raise ValueError("training evidence must contain the exact three C0 arms")
    maximum_steps = int(training["maximum_steps_per_arm"])
    for row in arms:
        _require_safe_mapping(row, "training arm")
        if (
            isinstance(row.get("steps"), bool)
            or not 0 < int(row.get("steps", 0)) <= maximum_steps
        ):
            raise ValueError("training arm steps exceed the request")
        if (
            request.get("experiment_id") == _C0_EXPERIMENT_ID
            and int(row["steps"]) != maximum_steps
        ):
            raise ValueError("every C0 arm must finish at request step 200")
        for key in ("final_loss", "heldout_accuracy"):
            _finite_number(row.get(key), f"training arm {key}")
        if row.get("finite_losses") is not True:
            raise ValueError("training arm losses must all be finite")

    resume = _require_safe_mapping(
        value.get("resume_equivalence"), "resume equivalence"
    )
    for key in (
        "maximum_parameter_difference",
        "maximum_optimiser_difference",
        "tolerance",
    ):
        if _finite_number(resume.get(key), f"resume {key}") < 0:
            raise ValueError(f"resume {key} must be non-negative")
    calculated_resume_pass = max(
        float(resume["maximum_parameter_difference"]),
        float(resume["maximum_optimiser_difference"]),
    ) <= float(resume["tolerance"])
    if resume.get("passed") is not calculated_resume_pass:
        raise ValueError("resume equivalence flag does not match its evidence")
    if result.get("status") == "complete" and not calculated_resume_pass:
        raise ValueError("complete training evidence requires resume equivalence")

    acceptance = _require_safe_mapping(
        value.get("acceptance"), "training acceptance evidence"
    )
    if set(acceptance) != {
        "clean_accuracy_at_least_0_90",
        "clean_advantage_at_least_0_20",
        "resume_equivalence_at_most_1e_7",
    } or any(not isinstance(item, bool) for item in acceptance.values()):
        raise ValueError("training acceptance fields changed")
    clean_accuracy = float(arms[0]["heldout_accuracy"])
    shuffled_accuracy = float(arms[2]["heldout_accuracy"])
    calculated_acceptance = {
        "clean_accuracy_at_least_0_90": clean_accuracy >= 0.90,
        "clean_advantage_at_least_0_20": (clean_accuracy - shuffled_accuracy >= 0.20),
        "resume_equivalence_at_most_1e_7": (
            calculated_resume_pass and float(resume["tolerance"]) == 1e-7
        ),
    }
    if dict(acceptance) != calculated_acceptance:
        raise ValueError("training acceptance flags do not match their evidence")
    if result.get("status") == "complete" and not all(acceptance.values()):
        raise ValueError("complete training result must pass every C0 acceptance gate")


def _verify_document_hash(document: Mapping[str, Any]) -> None:
    expected = str(document.get("document_sha256", ""))
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if expected != document_sha256(unsigned):
        raise ValueError("document SHA-256 does not match")


def _require_safe_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _reject_private_or_path_fields(value: Any) -> None:
    forbidden = {"path", "absolute_path", "credentials", "raw_audio", "private_notes"}
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).casefold() in forbidden:
                raise ValueError(f"cross-machine manifest may not contain {key}")
            _reject_private_or_path_fields(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _reject_private_or_path_fields(item)


__all__ = [
    "GPU_WORKER_REQUEST_SCHEMA",
    "GPU_WORKER_RESULT_SCHEMA",
    "build_gpu_worker_request",
    "build_gpu_worker_result",
    "validate_gpu_worker_request",
    "validate_gpu_worker_result",
]
