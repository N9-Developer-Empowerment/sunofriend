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
    warnings: Sequence[str] = (),
) -> dict[str, Any]:
    """Build one technical result that cannot make a musical decision."""

    request_document = validate_gpu_worker_request(request)
    document: dict[str, Any] = {
        "schema": GPU_WORKER_RESULT_SCHEMA,
        "status": status,
        "request_document_sha256": request_document["document_sha256"],
        "repository_commit": request_document["repository_commit"],
        "experiment_id": request_document["experiment_id"],
        "task_kind": request_document["task_kind"],
        "environment": dict(environment),
        "outputs": [dict(item) for item in outputs],
        "timings": dict(timings),
        "resources": dict(resources),
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
    if document.get("repository_commit") != request_document.get(
        "repository_commit"
    ):
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
    training = request_document.get("training")
    if training is not None and int(document["timings"].get("optimisation_steps", -1)) > int(
        training["maximum_steps_per_arm"]
    ):
        raise ValueError("GPU result exceeded maximum optimisation steps")
    return document


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
    if not isinstance(natures, list) or not natures or any(
        item not in {"D", "I", "T", "H"} for item in natures
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
    if not isinstance(hashes, list) or not hashes or any(
        not _SHA256.fullmatch(str(item)) for item in hashes
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
    ceiling = _require_safe_mapping(document.get("resource_ceiling"), "resource ceiling")
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
    stop_rules = document.get("stop_rules")
    if not isinstance(stop_rules, list) or not stop_rules or any(
        not str(item).strip() for item in stop_rules
    ):
        raise ValueError("stop_rules must contain non-empty rules")
    _reject_private_or_path_fields(document)


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
    output_ids = [str(row["output_id"]) for row in outputs]
    if len(set(output_ids)) != len(output_ids):
        raise ValueError("GPU result output IDs must be unique")
    _require_safe_mapping(document.get("timings"), "timings")
    timings = _require_safe_mapping(document.get("timings"), "timings")
    _finite_number(timings.get("wall_seconds"), "wall_seconds")
    if isinstance(timings.get("optimisation_steps"), bool) or int(
        timings.get("optimisation_steps", -1)
    ) < 0:
        raise ValueError("timings.optimisation_steps must be non-negative")
    resources = _require_safe_mapping(document.get("resources"), "resources")
    for key in ("peak_gpu_bytes", "peak_ram_bytes"):
        if isinstance(resources.get(key), bool) or int(resources.get(key, -1)) < 0:
            raise ValueError(f"resources.{key} must be non-negative")
    warnings = document.get("warnings")
    if not isinstance(warnings, list) or any(not isinstance(item, str) for item in warnings):
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
    _reject_private_or_path_fields(document)


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
