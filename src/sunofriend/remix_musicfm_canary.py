"""Hermetic boundary for the qualified MusicFM-FMA synthetic canary.

The public operations create one path-free request, run that exact synthetic
request in an already-prepared isolated runtime, and verify retained output.
They do not download, open private audio, train, rank, promote or alter product
ordering.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Sequence

from ._remix_musicfm_loader import (
    CHECKPOINT_SHA256,
    EXPECTED_FEATURE_FRAMES,
    FEATURE_DIMENSION,
    SAMPLE_RATE,
    SYNTHETIC_FRAMES,
    WEIGHT_NORM_MIGRATIONS,
    expected_loader_evidence,
    extract_synthetic_frozen_features,
)
from .remix_musicfm_fma_windows_setup import create_windows_asset_manifest
from .source_receipt import canonical_json_bytes, document_sha256


MUSICFM_SYNTHETIC_CANARY_REQUEST_SCHEMA = (
    "sunofriend.remix-musicfm-fma-synthetic-canary-request.v0"
)
MUSICFM_SYNTHETIC_CANARY_RESULT_SCHEMA = (
    "sunofriend.remix-musicfm-fma-synthetic-canary-result.v0"
)
MUSICFM_SYNTHETIC_CANARY_VERIFICATION_SCHEMA = (
    "sunofriend.remix-musicfm-fma-synthetic-canary-verification.v0"
)

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CHECKPOINT_BYTES = 1_316_802_154
_OUTPUT_NAMES = {
    "features-run-1.npy",
    "features-run-2.npy",
    "metrics.json",
    "result.json",
}
_EXPECTED_ENVIRONMENT = {
    "torch_version": "2.7.1+cu128",
    "cuda_version": "12.8",
    "device_name": "NVIDIA GeForce RTX 4080 Laptop GPU",
    "cublas_workspace_config": ":4096:8",
}


def create_musicfm_synthetic_canary_request(
    *,
    repository_commit: str,
    setup_receipt_sha256: str,
    setup_receipt_bytes: int,
) -> dict[str, Any]:
    """Create the sole synthetic-only, no-network and no-training request."""

    _full_commit(repository_commit)
    _sha256(setup_receipt_sha256, "setup receipt SHA-256")
    if (
        isinstance(setup_receipt_bytes, bool)
        or not isinstance(setup_receipt_bytes, int)
        or setup_receipt_bytes <= 0
    ):
        raise ValueError("setup receipt byte count must be positive")
    document = _request_values(
        repository_commit=repository_commit,
        setup_receipt_sha256=setup_receipt_sha256,
        setup_receipt_bytes=setup_receipt_bytes,
    )
    document["document_sha256"] = document_sha256(document)
    return validate_musicfm_synthetic_canary_request(document)


def validate_musicfm_synthetic_canary_request(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Recreate and compare the complete request rather than trust flags."""

    document = dict(value)
    commit = str(document.get("repository_commit") or "")
    setup = document.get("setup_receipt")
    if not isinstance(setup, Mapping):
        raise ValueError("invalid MusicFM synthetic canary request")
    _full_commit(commit)
    setup_sha256 = str(setup.get("sha256") or "")
    _sha256(setup_sha256, "setup receipt SHA-256")
    setup_bytes = setup.get("bytes")
    if (
        isinstance(setup_bytes, bool)
        or not isinstance(setup_bytes, int)
        or setup_bytes <= 0
    ):
        raise ValueError("invalid MusicFM synthetic canary request")
    expected = _request_values(
        repository_commit=commit,
        setup_receipt_sha256=setup_sha256,
        setup_receipt_bytes=setup_bytes,
    )
    expected["document_sha256"] = document_sha256(expected)
    if document != expected:
        raise ValueError("MusicFM synthetic canary request changed")
    return document


def run_musicfm_synthetic_canary(
    request: Mapping[str, Any],
    *,
    runtime_root: Path,
    out_dir: Path,
) -> dict[str, Any]:
    """Run one frozen synthetic extraction in an existing pinned runtime."""

    checked = validate_musicfm_synthetic_canary_request(request)
    root = _real_directory(runtime_root, "runtime_root")
    requested_output = Path(out_dir).expanduser().absolute()
    output_parent = _real_directory(requested_output.parent, "output parent")
    output = output_parent / requested_output.name
    if output.exists() or output.is_symlink():
        raise ValueError("canary output directory must not already exist")
    if output == root or root in output.parents:
        raise ValueError("canary output must be outside the isolated runtime")
    setup = _verify_setup_receipt(root, checked)
    assets = _verify_runtime_assets(root, checked["repository_commit"])
    extracted = extract_synthetic_frozen_features(root, assets)

    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(
        prefix=f".{output.name}-", dir=output.parent
    ) as temporary_name:
        temporary = Path(temporary_name)
        os.chmod(temporary, 0o700)
        artifacts = _write_feature_artifacts(
            temporary,
            first=extracted.first,
            second=extracted.second,
            metrics=extracted.metrics,
        )
        result = _result_values(
            checked,
            setup=setup,
            loader=extracted.loader,
            metrics=extracted.metrics,
            artifacts=artifacts,
            environment=extracted.environment,
        )
        result["document_sha256"] = document_sha256(result)
        validate_musicfm_synthetic_canary_result(result, checked)
        _private_json(temporary / "result.json", result)
        temporary.replace(output)
    _secure_tree(output)
    verify_musicfm_synthetic_canary_round_trip(output, checked)
    return result


def validate_musicfm_synthetic_canary_result(
    value: Mapping[str, Any], request: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate exact evidence without opening arrays or loading the model."""

    checked = validate_musicfm_synthetic_canary_request(request)
    document = _verified_document(value, MUSICFM_SYNTHETIC_CANARY_RESULT_SCHEMA)
    expected_fields = {
        "schema",
        "status",
        "request_sha256",
        "repository_commit",
        "setup_receipt",
        "checkpoint",
        "loader",
        "synthetic_input",
        "metrics",
        "artifacts",
        "environment",
        "authority",
        "effects",
        "document_sha256",
    }
    if set(document) != expected_fields:
        raise ValueError("MusicFM synthetic canary result fields changed")
    _validate_result_binding(document, checked)
    _validate_loader(document.get("loader"))
    _validate_environment(document.get("environment"))
    _validate_metrics(document.get("metrics"))
    _validate_authority_and_effects(document)
    _validate_artifact_records(document.get("artifacts"))
    return document


def verify_musicfm_synthetic_canary_round_trip(
    output_dir: Path,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify retained JSON and feature bytes without importing Torch."""

    checked = validate_musicfm_synthetic_canary_request(request)
    root = _real_directory(output_dir, "output_dir")
    children = tuple(root.iterdir())
    if {path.name for path in children} != _OUTPUT_NAMES or any(
        path.is_symlink() for path in children
    ):
        raise ValueError("MusicFM canary output roster changed")
    result = _json_object(root / "result.json", "MusicFM canary result")
    validate_musicfm_synthetic_canary_result(result, checked)
    records = {row["filename"]: row for row in result["artifacts"]}
    for name in _OUTPUT_NAMES - {"result.json"}:
        path = root / name
        record = records[name]
        if record != _file_record(path, record["kind"], record["media_type"]):
            raise ValueError("MusicFM canary artifact bytes changed")
    _verify_feature_arrays(root)
    metrics = _json_object(root / "metrics.json", "MusicFM canary metrics")
    if metrics != result["metrics"]:
        raise ValueError("MusicFM canary metrics artifact changed")
    return {
        "schema": MUSICFM_SYNTHETIC_CANARY_VERIFICATION_SCHEMA,
        "status": "verified_synthetic_frozen_features_only",
        "request_sha256": checked["document_sha256"],
        "result_sha256": result["document_sha256"],
        "artifacts_verified": 3,
        "private_audio_opened": False,
        "training_started": False,
        "product_ordering_changed": False,
    }


def _request_values(
    *, repository_commit: str, setup_receipt_sha256: str, setup_receipt_bytes: int
) -> dict[str, Any]:
    return {
        "schema": MUSICFM_SYNTHETIC_CANARY_REQUEST_SCHEMA,
        "status": "authorized_single_synthetic_frozen_feature_canary",
        "repository_commit": repository_commit,
        "setup_receipt": {
            "sha256": setup_receipt_sha256,
            "bytes": setup_receipt_bytes,
        },
        "model": {
            "provider": "musicfm-fma-25hz",
            "checkpoint_sha256": CHECKPOINT_SHA256,
            "restricted_weights_only_load": True,
            "local_config_only": True,
            "frozen_eval": True,
            "layer_index": 7,
        },
        "synthetic_input": {
            "generator": "fixed_sines_chirp_and_pulses_v1",
            "sample_rate_hz": SAMPLE_RATE,
            "channels": 1,
            "frames": SYNTHETIC_FRAMES,
            "private_audio": False,
        },
        "expected_output": {
            "shape": [1, EXPECTED_FEATURE_FRAMES, FEATURE_DIMENSION],
            "dtype": "float32",
            "finite": True,
            "exact_repeat_required": True,
        },
        "execution": {
            "device": "cuda",
            "maximum_executions": 1,
            "retries": 0,
            "network_allowed": False,
            "downloads_allowed": False,
        },
        "authority": {
            "model_load_authorized": True,
            "synthetic_inference_authorized": True,
            "private_audio_access_authorized": False,
            "training_execution_authorized": False,
            "checkpoint_promotion_authorized": False,
            "product_ordering_changed": False,
        },
    }


def _result_values(
    request: Mapping[str, Any],
    *,
    setup: Mapping[str, Any],
    loader: Mapping[str, Any],
    metrics: Mapping[str, Any],
    artifacts: Sequence[Mapping[str, Any]],
    environment: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": MUSICFM_SYNTHETIC_CANARY_RESULT_SCHEMA,
        "status": "complete_verified_structure_unpromoted",
        "request_sha256": request["document_sha256"],
        "repository_commit": request["repository_commit"],
        "setup_receipt": dict(setup),
        "checkpoint": {
            "filename": "pretrained_fma.pt",
            "bytes": _CHECKPOINT_BYTES,
            "sha256": CHECKPOINT_SHA256,
        },
        "loader": dict(loader),
        "synthetic_input": dict(request["synthetic_input"]),
        "metrics": dict(metrics),
        "artifacts": [dict(row) for row in artifacts],
        "environment": dict(environment),
        "authority": {
            "private_audio_access_authorized": False,
            "training_execution_authorized": False,
            "checkpoint_promotion_authorized": False,
            "product_ordering_changed": False,
        },
        "effects": {
            "model_loaded_restricted": True,
            "synthetic_features_extracted": True,
            "private_audio_opened": False,
            "training_started": False,
            "model_weights_changed": False,
        },
    }


def _validate_result_binding(
    document: Mapping[str, Any], request: Mapping[str, Any]
) -> None:
    expected = {
        "status": "complete_verified_structure_unpromoted",
        "request_sha256": request["document_sha256"],
        "repository_commit": request["repository_commit"],
        "setup_receipt": {**request["setup_receipt"], "packages": 26},
        "checkpoint": {
            "filename": "pretrained_fma.pt",
            "bytes": _CHECKPOINT_BYTES,
            "sha256": CHECKPOINT_SHA256,
        },
        "synthetic_input": request["synthetic_input"],
    }
    if any(document.get(key) != value for key, value in expected.items()):
        raise ValueError("MusicFM synthetic canary evidence binding changed")


def _validate_loader(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("MusicFM synthetic canary loader evidence changed")
    count = value.get("state_tensor_count")
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValueError("MusicFM synthetic canary loader evidence changed")
    expected = expected_loader_evidence(state_tensor_count=count)
    expected["state_key_migrations"] = WEIGHT_NORM_MIGRATIONS
    if value != expected:
        raise ValueError("MusicFM synthetic canary loader evidence changed")


def _validate_environment(value: Any) -> None:
    if value != _EXPECTED_ENVIRONMENT:
        raise ValueError("MusicFM synthetic canary environment changed")
    if any("/" in text or "\\" in text for text in value.values()):
        raise ValueError("MusicFM synthetic canary environment changed")


def _validate_metrics(value: Any) -> None:
    expected = {
        "feature_shape": [1, EXPECTED_FEATURE_FRAMES, FEATURE_DIMENSION],
        "feature_dtype": "float32",
        "finite": True,
        "feature_frames": EXPECTED_FEATURE_FRAMES,
        "feature_dimension": FEATURE_DIMENSION,
        "feature_rate_hz": 25.0,
        "maximum_repeat_difference": 0.0,
        "network_attempts": 0,
    }
    if value != expected:
        raise ValueError("MusicFM synthetic canary metrics changed")


def _validate_authority_and_effects(document: Mapping[str, Any]) -> None:
    authority = {
        "private_audio_access_authorized": False,
        "training_execution_authorized": False,
        "checkpoint_promotion_authorized": False,
        "product_ordering_changed": False,
    }
    effects = {
        "model_loaded_restricted": True,
        "synthetic_features_extracted": True,
        "private_audio_opened": False,
        "training_started": False,
        "model_weights_changed": False,
    }
    if document.get("authority") != authority or document.get("effects") != effects:
        raise ValueError("MusicFM synthetic canary authority changed")


def _validate_artifact_records(value: Any) -> None:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("MusicFM synthetic canary artifact roster changed")
    expected = {
        ("features-run-1.npy", "features_run_1", "application/x-npy"),
        ("features-run-2.npy", "features_run_2", "application/x-npy"),
        ("metrics.json", "metrics", "application/json"),
    }
    observed = set()
    for row in value:
        _validate_artifact_record(row)
        observed.add((row["filename"], row["kind"], row["media_type"]))
    if observed != expected:
        raise ValueError("MusicFM synthetic canary artifact names changed")


def _validate_artifact_record(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "filename",
        "kind",
        "media_type",
        "bytes",
        "sha256",
    }:
        raise ValueError("MusicFM synthetic canary artifact record changed")
    size = value.get("bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ValueError("MusicFM synthetic canary artifact record changed")
    _sha256(str(value.get("sha256") or ""), "artifact SHA-256")


def _verify_setup_receipt(root: Path, request: Mapping[str, Any]) -> dict[str, Any]:
    path = root / "setup-receipt.json"
    expected = request["setup_receipt"]
    document = _read_bound_setup_receipt(path, expected)
    _validate_setup_receipt_claims(document)
    return {
        "sha256": expected["sha256"],
        "bytes": expected["bytes"],
        "packages": 26,
    }


def _read_bound_setup_receipt(
    path: Path, expected: Mapping[str, Any]
) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("MusicFM setup receipt is missing")
    raw = path.read_bytes()
    if (
        len(raw) != expected["bytes"]
        or hashlib.sha256(raw).hexdigest() != expected["sha256"]
    ):
        raise ValueError("MusicFM setup receipt identity changed")
    return _json_bytes(raw, "MusicFM setup receipt")


def _validate_setup_receipt_claims(document: Mapping[str, Any]) -> None:
    if document.get("schema") != (
        "sunofriend.remix-musicfm-fma-windows-setup-receipt.v0"
    ):
        raise ValueError("MusicFM setup receipt claims changed effects")
    if document.get("packages") != 26:
        raise ValueError("MusicFM setup receipt claims changed effects")
    if document.get("fresh_environment") is not True:
        raise ValueError("MusicFM setup receipt claims changed effects")
    if document.get("offline_no_deps_install") is not True:
        raise ValueError("MusicFM setup receipt claims changed effects")
    _validate_setup_receipt_false_effects(document)


def _validate_setup_receipt_false_effects(document: Mapping[str, Any]) -> None:
    expected_false = (
        "model_imported",
        "checkpoint_loaded",
        "synthetic_canary_run",
        "private_audio_opened",
    )
    if any(document.get(key) is not False for key in expected_false):
        raise ValueError("MusicFM setup receipt claims changed effects")


def _verify_runtime_assets(
    root: Path, repository_commit: str
) -> dict[str, dict[str, Any]]:
    manifest = create_windows_asset_manifest(repository_commit=repository_commit)
    records: dict[str, dict[str, Any]] = {}
    for row in manifest["items"]:
        relative = row["target_relative_path"]
        path = root.joinpath(*relative.split("/"))
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"MusicFM runtime asset is missing: {relative}")
        observed = _file_identity(path)
        if observed != {"bytes": row["bytes"], "sha256": row["sha256"]}:
            raise ValueError(f"MusicFM runtime asset changed: {relative}")
        records[relative] = {"filename": Path(relative).name, **observed}
    return records


def _write_feature_artifacts(
    root: Path, *, first: Any, second: Any, metrics: Mapping[str, Any]
) -> list[dict[str, Any]]:
    import numpy as np

    first_path = root / "features-run-1.npy"
    second_path = root / "features-run-2.npy"
    metrics_path = root / "metrics.json"
    np.save(first_path, first, allow_pickle=False)
    np.save(second_path, second, allow_pickle=False)
    _private_json(metrics_path, metrics)
    for path in (first_path, second_path):
        os.chmod(path, 0o600)
    return [
        _file_record(first_path, "features_run_1", "application/x-npy"),
        _file_record(second_path, "features_run_2", "application/x-npy"),
        _file_record(metrics_path, "metrics", "application/json"),
    ]


def _verify_feature_arrays(root: Path) -> None:
    import numpy as np

    first = np.load(root / "features-run-1.npy", allow_pickle=False)
    second = np.load(root / "features-run-2.npy", allow_pickle=False)
    if (
        first.shape != (1, EXPECTED_FEATURE_FRAMES, FEATURE_DIMENSION)
        or first.dtype.name != "float32"
        or not np.isfinite(first).all()
        or not np.array_equal(first, second)
    ):
        raise ValueError("MusicFM canary feature arrays changed")


def _verified_document(value: Mapping[str, Any], schema: str) -> dict[str, Any]:
    document = dict(value)
    supplied = document.get("document_sha256")
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if (
        document.get("schema") != schema
        or not isinstance(supplied, str)
        or supplied != document_sha256(unsigned)
    ):
        raise ValueError("invalid MusicFM synthetic canary result")
    return document


def _file_record(path: Path, kind: str, media_type: str) -> dict[str, Any]:
    return {
        "filename": path.name,
        "kind": kind,
        "media_type": media_type,
        **_file_identity(path),
    }


def _file_identity(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("MusicFM canary artifact is missing or unsafe")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def _json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} is missing or unsafe")
    return _json_bytes(path.read_bytes(), label)


def _json_bytes(payload: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} must be UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _private_json(path: Path, document: Mapping[str, Any]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(canonical_json_bytes(document))
        handle.flush()
        os.fsync(handle.fileno())


def _secure_tree(root: Path) -> None:
    os.chmod(root, 0o700)
    for path in root.rglob("*"):
        os.chmod(path, 0o700 if path.is_dir() else 0o600)


def _real_directory(path: Path, label: str) -> Path:
    value = Path(path).expanduser()
    if not value.is_dir() or value.is_symlink():
        raise ValueError(f"{label} must be a real directory")
    return value.resolve()


def _full_commit(value: str) -> None:
    if not _COMMIT.fullmatch(value):
        raise ValueError("repository_commit must be a full Git commit")


def _sha256(value: str, label: str) -> None:
    if not _SHA256.fullmatch(value):
        raise ValueError(f"{label} is invalid")


__all__ = [
    "MUSICFM_SYNTHETIC_CANARY_REQUEST_SCHEMA",
    "MUSICFM_SYNTHETIC_CANARY_RESULT_SCHEMA",
    "MUSICFM_SYNTHETIC_CANARY_VERIFICATION_SCHEMA",
    "create_musicfm_synthetic_canary_request",
    "run_musicfm_synthetic_canary",
    "validate_musicfm_synthetic_canary_request",
    "validate_musicfm_synthetic_canary_result",
    "verify_musicfm_synthetic_canary_round_trip",
]
