"""Local-only MusicFM features for one reviewed source-delta comparison.

The module binds a path-free owner label to three exact WAV identities, opens
only those locally supplied files, and emits frozen feature arrays plus
verification evidence.  It cannot train, rank, promote or select a remix.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping
import wave

from ._remix_musicfm_loader import (
    CHECKPOINT_SHA256,
    FEATURE_DIMENSION,
    LAYER_INDEX,
    SAMPLE_RATE,
    extract_audio_frozen_features,
)
from .remix_musicfm_canary import (
    _validate_environment,
    _validate_loader,
    _verify_runtime_assets,
    _verify_setup_receipt,
)
from .remix_source_delta_dataset import (
    REMIX_SOURCE_DELTA_TRAINING_SNAPSHOT_SCHEMA,
    validate_remix_source_delta_training_snapshot,
)
from .source_receipt import canonical_json_bytes, document_sha256


MUSICFM_PRIVATE_FEATURE_REQUEST_SCHEMA = (
    "sunofriend.remix-musicfm-private-feature-request.v0"
)
MUSICFM_PRIVATE_FEATURE_RESULT_SCHEMA = (
    "sunofriend.remix-musicfm-private-feature-result.v0"
)
MUSICFM_PRIVATE_FEATURE_VERIFICATION_SCHEMA = (
    "sunofriend.remix-musicfm-private-feature-verification.v0"
)

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ROLES = ("control", "left", "right")
_CHECKPOINT_BYTES = 1_316_802_154
_MAX_AUDIO_BYTES = 128 * 1024 * 1024


def create_musicfm_private_feature_request(
    *,
    repository_commit: str,
    setup_receipt_sha256: str,
    setup_receipt_bytes: int,
    training_snapshot: Mapping[str, Any],
    label_document_sha256: str,
) -> dict[str, Any]:
    """Create one path-free request for control/left/right frozen features."""

    _full_commit(repository_commit)
    _sha256(setup_receipt_sha256, "setup receipt SHA-256")
    _positive_int(setup_receipt_bytes, "setup receipt byte count")
    snapshot = validate_remix_source_delta_training_snapshot(training_snapshot)
    label, assignment = _bound_label(snapshot, label_document_sha256)
    document = _request_values(
        repository_commit=repository_commit,
        setup_receipt={
            "sha256": setup_receipt_sha256,
            "bytes": setup_receipt_bytes,
        },
        snapshot=snapshot,
        label=label,
        assignment=assignment,
    )
    document["document_sha256"] = document_sha256(document)
    return validate_musicfm_private_feature_request(document, snapshot)


def validate_musicfm_private_feature_request(
    value: Mapping[str, Any], training_snapshot: Mapping[str, Any]
) -> dict[str, Any]:
    """Recreate the complete request from its immutable snapshot binding."""

    snapshot = validate_remix_source_delta_training_snapshot(training_snapshot)
    document = dict(value)
    commit = str(document.get("repository_commit") or "")
    _full_commit(commit)
    setup = _mapping(document.get("setup_receipt"), "setup receipt")
    _sha256(str(setup.get("sha256") or ""), "setup receipt SHA-256")
    _positive_int(setup.get("bytes"), "setup receipt byte count")
    binding = _mapping(document.get("binding"), "request binding")
    label_hash = str(binding.get("label_document_sha256") or "")
    label, assignment = _bound_label(snapshot, label_hash)
    expected = _request_values(
        repository_commit=commit,
        setup_receipt=setup,
        snapshot=snapshot,
        label=label,
        assignment=assignment,
    )
    expected["document_sha256"] = document_sha256(expected)
    if document != expected:
        raise ValueError("MusicFM private feature request changed")
    _reject_paths(document)
    return document


def run_musicfm_private_features(
    request: Mapping[str, Any],
    training_snapshot: Mapping[str, Any],
    *,
    runtime_root: Path,
    inputs: Mapping[str, Path],
    out_dir: Path,
) -> dict[str, Any]:
    """Verify three local WAVs and extract frozen features exactly once."""

    checked = validate_musicfm_private_feature_request(request, training_snapshot)
    root = _real_directory(runtime_root, "runtime_root")
    paths = _verified_input_paths(inputs, checked["inputs"])
    output = _new_output_path(out_dir, root, paths)
    setup = _verify_setup_receipt(root, checked)
    assets = _verify_runtime_assets(root, checked["repository_commit"])
    waveforms, rates = _read_bound_waveforms(paths, checked["inputs"])
    extracted = extract_audio_frozen_features(root, assets, waveforms, rates)

    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(
        prefix=f".{output.name}-", dir=output.parent
    ) as temporary_name:
        temporary = Path(temporary_name)
        os.chmod(temporary, 0o700)
        artifacts = _write_artifacts(
            temporary, extracted.features, extracted.metrics
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
        validate_musicfm_private_feature_result(result, checked, training_snapshot)
        _private_json(temporary / "result.json", result)
        temporary.replace(output)
    _secure_tree(output)
    verify_musicfm_private_feature_round_trip(output, checked, training_snapshot)
    return result


def validate_musicfm_private_feature_result(
    value: Mapping[str, Any],
    request: Mapping[str, Any],
    training_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate result evidence without opening private feature arrays."""

    checked = validate_musicfm_private_feature_request(request, training_snapshot)
    document = _verified_document(value, MUSICFM_PRIVATE_FEATURE_RESULT_SCHEMA)
    if set(document) != {
        "schema",
        "status",
        "request_sha256",
        "repository_commit",
        "binding",
        "setup_receipt",
        "checkpoint",
        "loader",
        "inputs",
        "metrics",
        "artifacts",
        "environment",
        "authority",
        "effects",
        "privacy",
        "document_sha256",
    }:
        raise ValueError("MusicFM private feature result fields changed")
    if (
        document.get("status") != "complete_private_frozen_features_unpromoted"
        or document.get("request_sha256") != checked["document_sha256"]
        or document.get("repository_commit") != checked["repository_commit"]
        or document.get("binding") != checked["binding"]
        or document.get("inputs") != checked["inputs"]
        or document.get("checkpoint")
        != {
            "filename": "pretrained_fma.pt",
            "bytes": _CHECKPOINT_BYTES,
            "sha256": CHECKPOINT_SHA256,
        }
    ):
        raise ValueError("MusicFM private feature result binding changed")
    if document.get("setup_receipt") != {
        **checked["setup_receipt"],
        "packages": 26,
    }:
        raise ValueError("MusicFM private feature setup binding changed")
    _validate_loader(document.get("loader"))
    _validate_environment(document.get("environment"))
    _validate_result_policy(document)
    _validate_metrics_and_artifacts(document.get("metrics"), document.get("artifacts"))
    _reject_paths(document)
    return document


def verify_musicfm_private_feature_round_trip(
    output_dir: Path,
    request: Mapping[str, Any],
    training_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Recheck retained private features, metrics and result bytes."""

    import numpy as np

    checked = validate_musicfm_private_feature_request(request, training_snapshot)
    root = _real_directory(output_dir, "output_dir")
    expected_names = {
        *(f"{role}.musicfm-layer-{LAYER_INDEX}.npy" for role in _ROLES),
        "metrics.json",
        "result.json",
    }
    children = tuple(root.iterdir())
    if {path.name for path in children} != expected_names or any(
        path.is_symlink() for path in children
    ):
        raise ValueError("MusicFM private feature output roster changed")
    result = _json_object(root / "result.json", "MusicFM private feature result")
    validate_musicfm_private_feature_result(result, checked, training_snapshot)
    records = {row["filename"]: row for row in result["artifacts"]}
    for name in expected_names - {"result.json"}:
        record = records[name]
        if record != _file_record(root / name, record["kind"], record["media_type"]):
            raise ValueError("MusicFM private feature artifact bytes changed")
    metrics = _json_object(root / "metrics.json", "MusicFM private feature metrics")
    if metrics != result["metrics"]:
        raise ValueError("MusicFM private feature metrics changed")
    for role in _ROLES:
        array = np.load(
            root / f"{role}.musicfm-layer-{LAYER_INDEX}.npy", allow_pickle=False
        )
        expected_shape = tuple(metrics[role]["feature_shape"])
        if (
            array.shape != expected_shape
            or array.dtype.name != "float32"
            or not np.isfinite(array).all()
        ):
            raise ValueError("MusicFM private feature array changed")
    return {
        "schema": MUSICFM_PRIVATE_FEATURE_VERIFICATION_SCHEMA,
        "status": "verified_private_frozen_features_only",
        "request_sha256": checked["document_sha256"],
        "result_sha256": result["document_sha256"],
        "artifacts_verified": 4,
        "private_audio_opened": True,
        "training_started": False,
        "product_ordering_changed": False,
    }


def _request_values(
    *,
    repository_commit: str,
    setup_receipt: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    label: Mapping[str, Any],
    assignment: Mapping[str, Any],
) -> dict[str, Any]:
    geometry = dict(label["control"]["geometry"])
    inputs = [
        {"role": "control", **_audio_identity(label["control"], geometry)},
        {"role": "left", **_audio_identity(label["left"], geometry)},
        {"role": "right", **_audio_identity(label["right"], geometry)},
    ]
    return {
        "schema": MUSICFM_PRIVATE_FEATURE_REQUEST_SCHEMA,
        "status": "authorized_single_private_frozen_feature_extraction",
        "repository_commit": repository_commit,
        "setup_receipt": dict(setup_receipt),
        "binding": {
            "training_snapshot_schema": REMIX_SOURCE_DELTA_TRAINING_SNAPSHOT_SCHEMA,
            "training_snapshot_sha256": snapshot["document_sha256"],
            "label_document_sha256": label["document_sha256"],
            "source_state_sha256": assignment["source_state_sha256"],
            "variant_family_sha256": assignment["variant_family_sha256"],
            "split": assignment["split"],
        },
        "model": {
            "provider": "musicfm-fma-25hz",
            "checkpoint_sha256": CHECKPOINT_SHA256,
            "restricted_weights_only_load": True,
            "local_config_only": True,
            "frozen_eval": True,
            "layer_index": LAYER_INDEX,
            "model_sample_rate_hz": SAMPLE_RATE,
        },
        "inputs": inputs,
        "execution": {
            "device": "cuda",
            "maximum_executions": 1,
            "retries": 0,
            "network_allowed": False,
            "downloads_allowed": False,
            "staging_outside_onedrive_required": True,
        },
        "authority": {
            "model_load_authorized": True,
            "private_audio_access_authorized": True,
            "frozen_feature_extraction_authorized": True,
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
    artifacts: list[dict[str, Any]],
    environment: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": MUSICFM_PRIVATE_FEATURE_RESULT_SCHEMA,
        "status": "complete_private_frozen_features_unpromoted",
        "request_sha256": request["document_sha256"],
        "repository_commit": request["repository_commit"],
        "binding": dict(request["binding"]),
        "setup_receipt": dict(setup),
        "checkpoint": {
            "filename": "pretrained_fma.pt",
            "bytes": _CHECKPOINT_BYTES,
            "sha256": CHECKPOINT_SHA256,
        },
        "loader": dict(loader),
        "inputs": [dict(row) for row in request["inputs"]],
        "metrics": {role: dict(metrics[role]) for role in _ROLES},
        "artifacts": artifacts,
        "environment": dict(environment),
        "authority": {
            "training_execution_authorized": False,
            "checkpoint_promotion_authorized": False,
            "product_ordering_changed": False,
        },
        "effects": {
            "model_loaded_restricted": True,
            "private_audio_opened": True,
            "frozen_features_extracted": True,
            "training_started": False,
            "model_weights_changed": False,
            "product_selection_changed": False,
        },
        "privacy": {
            "owner_local_only": True,
            "paths_embedded": False,
            "audio_embedded": False,
            "feature_arrays_private": True,
            "network_used": False,
        },
    }


def _bound_label(
    snapshot: Mapping[str, Any], label_hash: str
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    _sha256(label_hash, "label document SHA-256")
    labels = [row for row in snapshot["labels"] if row["document_sha256"] == label_hash]
    assignments = [
        row
        for row in snapshot["assignments"]
        if row["label_document_sha256"] == label_hash
    ]
    if len(labels) != 1 or len(assignments) != 1:
        raise ValueError("MusicFM request label is not uniquely bound to the snapshot")
    return labels[0], assignments[0]


def _audio_identity(value: Mapping[str, Any], geometry: Mapping[str, Any]) -> dict[str, Any]:
    sha = str(value.get("audio_sha256") or "")
    size = value.get("audio_bytes")
    _sha256(sha, "audio SHA-256")
    _positive_int(size, "audio byte count")
    checked_geometry = _geometry(geometry)
    return {"audio_sha256": sha, "audio_bytes": size, "geometry": checked_geometry}


def _verified_input_paths(
    inputs: Mapping[str, Path], records: list[Mapping[str, Any]]
) -> dict[str, Path]:
    if set(inputs) != set(_ROLES):
        raise ValueError("MusicFM private inputs must be exactly control, left and right")
    expected = {row["role"]: row for row in records}
    resolved: dict[str, Path] = {}
    parents: set[Path] = set()
    for role in _ROLES:
        path = Path(inputs[role]).expanduser()
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"MusicFM {role} input is missing or unsafe")
        real = path.resolve()
        if _is_onedrive_path(real):
            raise ValueError("MusicFM private staging must be outside OneDrive")
        identity = _file_identity(real)
        record = expected[role]
        if identity != {
            "bytes": record["audio_bytes"],
            "sha256": record["audio_sha256"],
        }:
            raise ValueError(f"MusicFM {role} input identity changed")
        resolved[role] = real
        parents.add(real.parent)
    if len(parents) != 1:
        raise ValueError("MusicFM private inputs must share one isolated staging folder")
    return resolved


def _new_output_path(out_dir: Path, runtime_root: Path, inputs: Mapping[str, Path]) -> Path:
    requested = Path(out_dir).expanduser().absolute()
    parent = _real_directory(requested.parent, "output parent")
    output = parent / requested.name
    if output.exists() or output.is_symlink():
        raise ValueError("private feature output directory must not already exist")
    if _is_onedrive_path(output):
        raise ValueError("MusicFM private output must be outside OneDrive")
    if output == runtime_root or runtime_root in output.parents:
        raise ValueError("private feature output must be outside the isolated runtime")
    input_parent = next(iter(inputs.values())).parent
    if output == input_parent or input_parent in output.parents:
        raise ValueError("private feature output must not contain source inputs")
    return output


def _read_bound_waveforms(
    paths: Mapping[str, Path], records: list[Mapping[str, Any]]
) -> tuple[dict[str, Any], dict[str, int]]:
    expected = {row["role"]: row for row in records}
    waveforms: dict[str, Any] = {}
    rates: dict[str, int] = {}
    for role in _ROLES:
        waveform, geometry = _read_pcm_wav(paths[role])
        if geometry != expected[role]["geometry"]:
            raise ValueError(f"MusicFM {role} WAV geometry changed")
        waveforms[role] = waveform
        rates[role] = geometry["sample_rate_hz"]
    return waveforms, rates


def _read_pcm_wav(path: Path) -> tuple[Any, dict[str, int]]:
    import numpy as np

    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            sample_rate = handle.getframerate()
            frames = handle.getnframes()
            compression = handle.getcomptype()
            payload = handle.readframes(frames)
    except (wave.Error, OSError) as error:
        raise ValueError("MusicFM input must be readable PCM WAV") from error
    if compression != "NONE" or sample_width not in {1, 2, 3, 4}:
        raise ValueError("MusicFM input must be uncompressed 8/16/24/32-bit PCM WAV")
    geometry = _geometry(
        {"sample_rate_hz": sample_rate, "channels": channels, "frames": frames}
    )
    if len(payload) != frames * channels * sample_width:
        raise ValueError("MusicFM input PCM payload is truncated")
    if sample_width == 1:
        values = (np.frombuffer(payload, dtype=np.uint8).astype(np.float32) - 128) / 128
    elif sample_width == 2:
        values = np.frombuffer(payload, dtype="<i2").astype(np.float32) / 32768
    elif sample_width == 4:
        values = np.frombuffer(payload, dtype="<i4").astype(np.float32) / 2147483648
    else:
        packed = np.frombuffer(payload, dtype=np.uint8).reshape(-1, 3)
        integers = (
            packed[:, 0].astype(np.int32)
            | (packed[:, 1].astype(np.int32) << 8)
            | (packed[:, 2].astype(np.int32) << 16)
        )
        integers = np.where(integers & 0x800000, integers - 0x1000000, integers)
        values = integers.astype(np.float32) / 8388608
    mono = values.reshape(frames, channels).mean(axis=1, dtype=np.float32)
    return mono, geometry


def _write_artifacts(
    root: Path,
    features: Mapping[str, Any],
    metrics: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    import numpy as np

    if set(features) != set(_ROLES) or set(metrics) != set(_ROLES):
        raise ValueError("MusicFM extraction roles changed")
    artifacts: list[dict[str, Any]] = []
    for role in _ROLES:
        path = root / f"{role}.musicfm-layer-{LAYER_INDEX}.npy"
        np.save(path, features[role], allow_pickle=False)
        os.chmod(path, 0o600)
        artifacts.append(_file_record(path, f"{role}_features", "application/x-npy"))
    metrics_path = root / "metrics.json"
    _private_json(metrics_path, {role: dict(metrics[role]) for role in _ROLES})
    artifacts.append(_file_record(metrics_path, "metrics", "application/json"))
    return artifacts


def _validate_metrics_and_artifacts(metrics_value: Any, artifacts_value: Any) -> None:
    metrics = _mapping(metrics_value, "private feature metrics")
    if set(metrics) != set(_ROLES):
        raise ValueError("MusicFM private feature metrics changed")
    for role in _ROLES:
        _validate_role_metrics(_mapping(metrics[role], f"{role} metrics"))
    _validate_feature_artifacts(artifacts_value)


def _validate_role_metrics(row: Mapping[str, Any]) -> None:
    expected_fields = {
        "source_sample_rate_hz",
        "source_frames",
        "model_sample_rate_hz",
        "model_frames",
        "feature_shape",
        "feature_dtype",
        "finite",
        "feature_frames",
        "feature_dimension",
        "feature_rate_hz",
    }
    if set(row) != expected_fields:
        raise ValueError("MusicFM private feature metrics changed")
    shape = row["feature_shape"]
    if not isinstance(shape, list) or len(shape) != 3:
        raise ValueError("MusicFM private feature metrics changed")
    if shape[0] != 1 or shape[1] <= 0 or shape[2] != FEATURE_DIMENSION:
        raise ValueError("MusicFM private feature metrics changed")
    expected = {
        "feature_dtype": "float32",
        "finite": True,
        "feature_frames": shape[1],
        "feature_dimension": FEATURE_DIMENSION,
        "model_sample_rate_hz": SAMPLE_RATE,
    }
    if any(row[key] != value for key, value in expected.items()):
        raise ValueError("MusicFM private feature metrics changed")
    feature_rate = row["feature_rate_hz"]
    if (
        isinstance(feature_rate, bool)
        or not isinstance(feature_rate, (int, float))
        or feature_rate <= 0
    ):
        raise ValueError("MusicFM private feature metrics changed")


def _validate_feature_artifacts(artifacts_value: Any) -> None:
    if not isinstance(artifacts_value, list) or len(artifacts_value) != 4:
        raise ValueError("MusicFM private feature artifact roster changed")
    expected = {
        *(f"{role}.musicfm-layer-{LAYER_INDEX}.npy" for role in _ROLES),
        "metrics.json",
    }
    observed = set()
    for row in artifacts_value:
        if not isinstance(row, Mapping) or set(row) != {
            "filename",
            "kind",
            "media_type",
            "bytes",
            "sha256",
        }:
            raise ValueError("MusicFM private feature artifact record changed")
        _positive_int(row.get("bytes"), "artifact byte count")
        _sha256(str(row.get("sha256") or ""), "artifact SHA-256")
        observed.add(row["filename"])
    if observed != expected:
        raise ValueError("MusicFM private feature artifact roster changed")


def _validate_result_policy(document: Mapping[str, Any]) -> None:
    if document.get("authority") != {
        "training_execution_authorized": False,
        "checkpoint_promotion_authorized": False,
        "product_ordering_changed": False,
    } or document.get("effects") != {
        "model_loaded_restricted": True,
        "private_audio_opened": True,
        "frozen_features_extracted": True,
        "training_started": False,
        "model_weights_changed": False,
        "product_selection_changed": False,
    } or document.get("privacy") != {
        "owner_local_only": True,
        "paths_embedded": False,
        "audio_embedded": False,
        "feature_arrays_private": True,
        "network_used": False,
    }:
        raise ValueError("MusicFM private feature authority changed")


def _geometry(value: Mapping[str, Any]) -> dict[str, int]:
    geometry = _mapping(value, "audio geometry")
    if set(geometry) != {"sample_rate_hz", "channels", "frames"}:
        raise ValueError("MusicFM audio geometry changed")
    checked = {key: geometry[key] for key in ("sample_rate_hz", "channels", "frames")}
    for key, item in checked.items():
        _positive_int(item, key)
    if checked["channels"] > 8 or checked["frames"] > 96_000 * 60 * 10:
        raise ValueError("MusicFM audio geometry exceeds the private extraction bound")
    return checked


def _verified_document(value: Mapping[str, Any], schema: str) -> dict[str, Any]:
    document = dict(value)
    supplied = document.get("document_sha256")
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if document.get("schema") != schema or supplied != document_sha256(unsigned):
        raise ValueError("invalid MusicFM private feature result")
    return document


def _file_record(path: Path, kind: str, media_type: str) -> dict[str, Any]:
    return {"filename": path.name, "kind": kind, "media_type": media_type, **_file_identity(path)}


def _file_identity(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("MusicFM private artifact is missing or unsafe")
    if path.stat().st_size > _MAX_AUDIO_BYTES and path.suffix.lower() == ".wav":
        raise ValueError("MusicFM private audio exceeds the extraction bound")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def _private_json(path: Path, document: Mapping[str, Any]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(canonical_json_bytes(document))
        handle.flush()
        os.fsync(handle.fileno())


def _json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} is missing or unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} must be UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _secure_tree(root: Path) -> None:
    os.chmod(root, 0o700)
    for path in root.rglob("*"):
        os.chmod(path, 0o700 if path.is_dir() else 0o600)


def _real_directory(path: Path, label: str) -> Path:
    value = Path(path).expanduser()
    if not value.is_dir() or value.is_symlink():
        raise ValueError(f"{label} must be a real directory")
    return value.resolve()


def _is_onedrive_path(path: Path) -> bool:
    return any("onedrive" in part.casefold() for part in path.parts)


def _reject_paths(document: Mapping[str, Any]) -> None:
    encoded = json.dumps(document, sort_keys=True)
    if "/Users/" in encoded or re.search(r"[A-Za-z]:\\", encoded):
        raise ValueError("MusicFM private evidence must not embed local paths")


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return dict(value)


def _positive_int(value: Any, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be positive")


def _full_commit(value: str) -> None:
    if not _COMMIT.fullmatch(value):
        raise ValueError("repository_commit must be a full Git commit")


def _sha256(value: str, label: str) -> None:
    if not _SHA256.fullmatch(value):
        raise ValueError(f"{label} is invalid")


__all__ = [
    "MUSICFM_PRIVATE_FEATURE_REQUEST_SCHEMA",
    "MUSICFM_PRIVATE_FEATURE_RESULT_SCHEMA",
    "MUSICFM_PRIVATE_FEATURE_VERIFICATION_SCHEMA",
    "create_musicfm_private_feature_request",
    "run_musicfm_private_features",
    "validate_musicfm_private_feature_request",
    "validate_musicfm_private_feature_result",
    "verify_musicfm_private_feature_round_trip",
]
