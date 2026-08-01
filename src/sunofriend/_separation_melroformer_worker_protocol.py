"""Non-executable protocol for a future private MLX MelBand-RoFormer worker."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping, Sequence

from ._separation_melroformer_runtime_evidence import (
    RUNTIME_LOCK_SHA256,
    SOURCE_MANIFEST_SHA256,
    SOURCE_REVISION,
)
from ._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
    UPSTREAM_EVIDENCE_SHA256,
)
from ._separation_safetensors_inspection import SCHEMA as SAFETENSORS_INSPECTION_SCHEMA
from .separation_contract import _canonical_json_bytes, _freeze_json
from .separation_worker_contract import (
    SEPARATION_WORKER_ISOLATION_POLICY,
    SEPARATION_WORKER_REQUEST_SCHEMA,
    SEPARATION_WORKER_RESULT_SCHEMA,
)


SCHEMA = "sunofriend.private-melroformer-worker-protocol.v1"
PROTOCOL_ID = "private-mlx-melroformer-kim-vocal-2-worker-v1"
CANDIDATE_ID = "mlx-melroformer-kim-vocal-2"
CONFIG_SHA256 = "3300eacac960ab46933ef6df6b838eb35de1f0321db9242c1b06e6d2a6a62b58"
ROLES = ("vocals", "instrumental")
OUTPUT_ALLOWLIST = ("STEMS/vocals.wav", "STEMS/instrumental.wav")
SAMPLE_RATE = 44_100
CHANNELS = 2
BITS_PER_SAMPLE = 24
MAXIMUM_CASES = 2
MAXIMUM_SECONDS = 15.0
MAXIMUM_FRAMES = int(SAMPLE_RATE * MAXIMUM_SECONDS)
MAXIMUM_SOURCE_BYTES = 4 * 1024 * 1024
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,63}$")
_CASE_FIELDS = {
    "case_id",
    "source_id",
    "source_sha256",
    "canonical_sha256",
    "bytes",
    "geometry",
}


def _build_private_melroformer_worker_protocol(
    *, cases: Sequence[Mapping[str, Any]]
) -> Mapping[str, Any]:
    """Build path-free planning evidence for one or two canonical excerpts."""

    validated = _validate_cases(cases)
    payload = _payload(validated)
    document = {
        **payload,
        "protocol_sha256": hashlib.sha256(_canonical_json_bytes(payload)).hexdigest(),
    }
    return _validate_private_melroformer_worker_protocol(document)


def _validate_private_melroformer_worker_protocol(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = _plain_mapping(document, "MelRoFormer worker protocol")
    digest = _sha(value.get("protocol_sha256"), "protocol_sha256")
    cases = _validate_cases(value.get("cases"))
    expected = _payload(cases)
    unsigned = dict(value)
    unsigned.pop("protocol_sha256", None)
    if unsigned != expected:
        raise ValueError("MelRoFormer worker protocol differs from fixed policy")
    if digest != hashlib.sha256(_canonical_json_bytes(unsigned)).hexdigest():
        raise ValueError("MelRoFormer worker protocol hash is invalid")
    return _freeze_json(value)


def _payload(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "status": "protocol_defined_worker_absent",
        "bindings": {
            "candidate_id": CANDIDATE_ID,
            "upstream_evidence_sha256": UPSTREAM_EVIDENCE_SHA256,
            "source_revision": SOURCE_REVISION,
            "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
            "runtime_lock_sha256": RUNTIME_LOCK_SHA256,
            "config_sha256": CONFIG_SHA256,
            "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
            "checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
            "safetensors_inspection_schema": SAFETENSORS_INSPECTION_SCHEMA,
            "generic_request_schema": SEPARATION_WORKER_REQUEST_SCHEMA,
            "generic_result_schema": SEPARATION_WORKER_RESULT_SCHEMA,
            "isolation_policy": SEPARATION_WORKER_ISOLATION_POLICY,
        },
        "batch": {
            "case_count": len(cases),
            "maximum_cases": MAXIMUM_CASES,
            "maximum_parallel_cases": 1,
            "execution_order": "case_id_ascending",
            "fresh_worker_per_case": True,
            "model_reuse_between_cases": False,
        },
        "cases": cases,
        "request_shape": {
            "materialisation_status": "blocked",
            "source": {
                "container": "wav",
                "encoding": "linear-pcm",
                "bits_per_sample": BITS_PER_SAMPLE,
                "sample_rate": SAMPLE_RATE,
                "channels": CHANNELS,
                "maximum_frames": MAXIMUM_FRAMES,
                "maximum_seconds": MAXIMUM_SECONDS,
                "maximum_bytes": MAXIMUM_SOURCE_BYTES,
                "read_only": True,
            },
            "roles": list(ROLES),
            "seed": 0,
            "output_allowlist": list(OUTPUT_ALLOWLIST),
            "checkpoint_descriptor_lease_required": True,
            "checkpoint_hash_before_tensor_load_required": True,
            "safetensors_header_inspection_required": True,
            "source_hash_before_read_required": True,
            "network_denial_and_observation_required": True,
            "child_process_denial_required": True,
            "upstream_from_pretrained_permitted": False,
            "fixed_config": "MelRoFormerConfig.kim_vocal_2()",
            "post_sanitisation_model_key_coverage_required": True,
            "missing_model_keys_permitted": False,
            "unexpected_sanitised_keys_permitted": False,
        },
        "result_shape": {
            "path_free": True,
            "terminal_result_schema": SEPARATION_WORKER_RESULT_SCHEMA,
            "required_roles": list(ROLES),
            "required_relative_outputs": list(OUTPUT_ALLOWLIST),
            "format": "PCM24 WAV",
            "sample_rate": SAMPLE_RATE,
            "channels": CHANNELS,
            "exact_source_frame_horizon_required": True,
            "instrumental_equation": "instrumental = mixture - vocals",
            "mixture_reconstruction_within_pcm_tolerance_required": True,
            "parent_hash_and_geometry_verification_required": True,
            "quality_or_preference_claim_permitted": False,
        },
        "permissions": {
            "runtime_installation_permitted": False,
            "checkpoint_download_permitted": False,
            "checkpoint_access_permitted": False,
            "checkpoint_deserialization_permitted": False,
            "model_import_permitted": False,
            "request_materialisation_permitted": False,
            "worker_start_permitted": False,
            "inference_permitted": False,
            "publication_permitted": False,
            "automatic_selection_permitted": False,
            "product_route_permitted": False,
        },
        "effects": {
            "filesystem_accessed": False,
            "filesystem_written": False,
            "network_used": False,
            "package_installed": False,
            "checkpoint_opened": False,
            "checkpoint_deserialized": False,
            "model_imported": False,
            "process_started": False,
            "source_graph_changed": False,
            "product_route_changed": False,
        },
    }


def _validate_cases(value: object) -> list[dict[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("MelRoFormer protocol cases must be an array")
    if not 1 <= len(value) <= MAXIMUM_CASES:
        raise ValueError("MelRoFormer protocol requires one or two cases")
    cases = [_validate_case(item) for item in value]
    ids = [item["case_id"] for item in cases]
    if ids != sorted(set(ids)):
        raise ValueError("MelRoFormer protocol case IDs must be sorted and unique")
    if len({item["canonical_sha256"] for item in cases}) != len(cases):
        raise ValueError("MelRoFormer cases must use distinct canonical audio")
    return cases


def _validate_case(value: object) -> dict[str, Any]:
    case = _plain_mapping(value, "MelRoFormer protocol case")
    if set(case) != _CASE_FIELDS:
        raise ValueError("MelRoFormer protocol case fields are invalid")
    geometry = _plain_mapping(case["geometry"], "MelRoFormer case geometry")
    if set(geometry) != {
        "sample_rate",
        "channels",
        "bits_per_sample",
        "frames",
        "duration_seconds",
    }:
        raise ValueError("MelRoFormer case geometry fields are invalid")
    frames = _bounded_int(geometry["frames"], "frames", minimum=1, maximum=MAXIMUM_FRAMES)
    duration = geometry["duration_seconds"]
    if isinstance(duration, bool) or not isinstance(duration, (int, float)):
        raise ValueError("MelRoFormer duration_seconds is invalid")
    expected_duration = frames / SAMPLE_RATE
    if abs(float(duration) - expected_duration) > 1e-9:
        raise ValueError("MelRoFormer duration_seconds differs from frame count")
    if (
        geometry["sample_rate"] != SAMPLE_RATE
        or geometry["channels"] != CHANNELS
        or geometry["bits_per_sample"] != BITS_PER_SAMPLE
    ):
        raise ValueError("MelRoFormer case geometry differs from fixed PCM policy")
    return {
        "case_id": _safe_id(case["case_id"], "case_id"),
        "source_id": _safe_id(case["source_id"], "source_id"),
        "source_sha256": _sha(case["source_sha256"], "source_sha256"),
        "canonical_sha256": _sha(case["canonical_sha256"], "canonical_sha256"),
        "bytes": _bounded_int(
            case["bytes"], "bytes", minimum=1, maximum=MAXIMUM_SOURCE_BYTES
        ),
        "geometry": {
            "sample_rate": SAMPLE_RATE,
            "channels": CHANNELS,
            "bits_per_sample": BITS_PER_SAMPLE,
            "frames": frames,
            "duration_seconds": expected_duration,
        },
    }


def _plain_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return dict(value)


def _safe_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ValueError(f"MelRoFormer {label} is invalid")
    return value


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise ValueError(f"MelRoFormer {label} is invalid")
    return value


def _bounded_int(value: object, label: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"MelRoFormer {label} is invalid")
    return value


__all__ = [
    "_build_private_melroformer_worker_protocol",
    "_validate_private_melroformer_worker_protocol",
]
