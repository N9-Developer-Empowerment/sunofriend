"""Pure, non-executable protocol for a future private BS-RoFormer worker.

The protocol binds a maximum of two path-free canonical excerpt identities to
Sunofriend's existing separation worker schemas.  It deliberately cannot
materialise a path-bearing worker request, open a checkpoint, import model
code, start a process or validate musical quality.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping, Sequence

from ._separation_roformer_source import (
    SOURCE_MANIFEST_SHA256,
    SOURCE_REVISION,
)
from .separation_contract import (
    SeparationAudioGeometry,
    _canonical_json_bytes,
    _freeze_json,
)
from .separation_worker_contract import (
    SEPARATION_WORKER_ISOLATION_POLICY,
    SEPARATION_WORKER_REQUEST_SCHEMA,
    SEPARATION_WORKER_RESULT_SCHEMA,
)


ROFORMER_WORKER_PROTOCOL_SCHEMA = "sunofriend.private-roformer-worker-protocol.v1"
ROFORMER_WORKER_PROTOCOL_ID = "private-bs-roformer-four-stem-worker-v1"
ROFORMER_CANDIDATE_ID = "zfturbo-bs-roformer-musdb18hq-v1.0.12"
ROFORMER_CONFIG_SHA256 = (
    "d8afb980318d0c08b9c2e24a7adc00d4f3150320c127a7e4de861800d1321939"
)
ROFORMER_DEPENDENCY_LOCK_SHA256 = (
    "7b8ade3828d75cca47cacc447dfa90e733c9425eccd0e341d5a6ba220a81ba65"
)
ROFORMER_CHECKPOINT_ASSET_ID = 209_597_731
ROFORMER_CHECKPOINT_PUBLISHED_BYTES = 527_385_512

ROFORMER_WORKER_ROLES = ("bass", "drums", "other", "vocals")
ROFORMER_WORKER_OUTPUT_ALLOWLIST = tuple(
    f"STEMS/{role}.wav" for role in ROFORMER_WORKER_ROLES
)
ROFORMER_WORKER_SAMPLE_RATE = 44_100
ROFORMER_WORKER_CHANNELS = 2
ROFORMER_WORKER_BITS_PER_SAMPLE = 24
ROFORMER_WORKER_MAXIMUM_CASES = 2
ROFORMER_WORKER_MAXIMUM_SECONDS = 15.0
ROFORMER_WORKER_MAXIMUM_FRAMES = int(
    ROFORMER_WORKER_SAMPLE_RATE * ROFORMER_WORKER_MAXIMUM_SECONDS
)
ROFORMER_WORKER_MAXIMUM_SOURCE_BYTES = 4 * 1024 * 1024

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_CASE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,63}$")
_CASE_FIELDS = {
    "case_id",
    "source_id",
    "source_sha256",
    "canonical_sha256",
    "bytes",
    "geometry",
}
_DOCUMENT_FIELDS = {
    "schema",
    "protocol_sha256",
    "protocol_id",
    "status",
    "bindings",
    "batch",
    "cases",
    "request_shape",
    "result_shape",
    "permissions",
    "effects",
}


def _build_private_roformer_worker_protocol(
    *, cases: Sequence[Mapping[str, Any]]
) -> Mapping[str, Any]:
    """Build immutable, path-free planning evidence for one or two cases."""

    validated_cases = _validate_cases(cases)
    payload = _protocol_payload(validated_cases)
    document = {
        **payload,
        "protocol_sha256": hashlib.sha256(_canonical_json_bytes(payload)).hexdigest(),
    }
    return _validate_private_roformer_worker_protocol(document)


def _validate_private_roformer_worker_protocol(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Validate exact non-authorising protocol evidence and freeze it."""

    value = _plain_mapping(document, "RoFormer worker protocol")
    if set(value) != _DOCUMENT_FIELDS:
        raise ValueError("RoFormer worker protocol fields are invalid")
    if value["schema"] != ROFORMER_WORKER_PROTOCOL_SCHEMA:
        raise ValueError("unsupported RoFormer worker protocol schema")
    digest = _sha(value["protocol_sha256"], "protocol_sha256")
    cases = _validate_cases(value["cases"])
    expected = _protocol_payload(cases)
    unsigned = dict(value)
    unsigned.pop("protocol_sha256")
    if unsigned != expected:
        raise ValueError("RoFormer worker protocol differs from fixed policy")
    if digest != hashlib.sha256(_canonical_json_bytes(unsigned)).hexdigest():
        raise ValueError("RoFormer worker protocol hash is invalid")
    return _freeze_json(value)


def private_roformer_worker_protocol_sha256(
    document: Mapping[str, Any],
) -> str:
    """Return the semantic hash after validating the fixed protocol."""

    return str(_validate_private_roformer_worker_protocol(document)["protocol_sha256"])


def _protocol_payload(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": ROFORMER_WORKER_PROTOCOL_SCHEMA,
        "protocol_id": ROFORMER_WORKER_PROTOCOL_ID,
        "status": "protocol_defined_worker_absent",
        "bindings": {
            "candidate_id": ROFORMER_CANDIDATE_ID,
            "source_revision": SOURCE_REVISION,
            "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
            "config_sha256": ROFORMER_CONFIG_SHA256,
            "dependency_lock_sha256": ROFORMER_DEPENDENCY_LOCK_SHA256,
            "checkpoint_asset_id": ROFORMER_CHECKPOINT_ASSET_ID,
            "checkpoint_published_bytes": ROFORMER_CHECKPOINT_PUBLISHED_BYTES,
            "checkpoint_published_sha256": None,
            "checkpoint_identity_status": "unverified",
            "generic_request_schema": SEPARATION_WORKER_REQUEST_SCHEMA,
            "generic_result_schema": SEPARATION_WORKER_RESULT_SCHEMA,
            "isolation_policy": SEPARATION_WORKER_ISOLATION_POLICY,
        },
        "batch": {
            "case_count": len(cases),
            "maximum_cases": ROFORMER_WORKER_MAXIMUM_CASES,
            "maximum_parallel_cases": 1,
            "execution_order": "case_id_ascending",
            "worker_lifecycle": "fresh_worker_and_quarantine_per_case",
            "model_reuse_between_cases": False,
        },
        "cases": cases,
        "request_shape": {
            "materialisation_status": "blocked",
            "path_bearing_private_request": True,
            "source": {
                "container": "wav",
                "encoding": "linear-pcm",
                "bits_per_sample": ROFORMER_WORKER_BITS_PER_SAMPLE,
                "sample_rate": ROFORMER_WORKER_SAMPLE_RATE,
                "channels": ROFORMER_WORKER_CHANNELS,
                "maximum_frames": ROFORMER_WORKER_MAXIMUM_FRAMES,
                "maximum_seconds": ROFORMER_WORKER_MAXIMUM_SECONDS,
                "maximum_bytes": ROFORMER_WORKER_MAXIMUM_SOURCE_BYTES,
                "read_only": True,
            },
            "roles": list(ROFORMER_WORKER_ROLES),
            "seed": 0,
            "output_allowlist": list(ROFORMER_WORKER_OUTPUT_ALLOWLIST),
            "fresh_private_quarantine_required": True,
            "checkpoint_descriptor_lease_required": True,
            "checkpoint_hash_verified_before_load_required": True,
            "source_hash_verified_before_read_required": True,
            "network_denial_and_observation_required": True,
            "child_process_denial_required": True,
        },
        "result_shape": {
            "path_free": True,
            "terminal_result_schema": SEPARATION_WORKER_RESULT_SCHEMA,
            "required_roles": list(ROFORMER_WORKER_ROLES),
            "required_relative_outputs": list(ROFORMER_WORKER_OUTPUT_ALLOWLIST),
            "format": "PCM24 WAV",
            "sample_rate": ROFORMER_WORKER_SAMPLE_RATE,
            "channels": ROFORMER_WORKER_CHANNELS,
            "exact_source_frame_horizon_required": True,
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


def _validate_cases(value: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("RoFormer protocol cases must be an array")
    if not 1 <= len(value) <= ROFORMER_WORKER_MAXIMUM_CASES:
        raise ValueError("RoFormer protocol requires one or two cases")
    cases = [_validate_case(item) for item in value]
    case_ids = [item["case_id"] for item in cases]
    if case_ids != sorted(set(case_ids)):
        raise ValueError("RoFormer protocol case IDs must be sorted and unique")
    canonical_hashes = [item["canonical_sha256"] for item in cases]
    if len(canonical_hashes) != len(set(canonical_hashes)):
        raise ValueError("RoFormer protocol cases must use distinct canonical audio")
    return cases


def _validate_case(value: Mapping[str, Any]) -> dict[str, Any]:
    case = _plain_mapping(value, "RoFormer protocol case")
    if set(case) != _CASE_FIELDS:
        raise ValueError("RoFormer protocol case fields are invalid")
    case_id = _safe_id(case["case_id"], "case_id")
    source_id = _safe_id(case["source_id"], "source_id")
    source_sha256 = _sha(case["source_sha256"], "source_sha256")
    canonical_sha256 = _sha(case["canonical_sha256"], "canonical_sha256")
    source_bytes = _strict_int(case["bytes"], "source bytes")
    if not 1 <= source_bytes <= ROFORMER_WORKER_MAXIMUM_SOURCE_BYTES:
        raise ValueError("RoFormer protocol source bytes are outside bounds")
    geometry = SeparationAudioGeometry.from_dict(case["geometry"]).to_dict()
    if (
        geometry["sample_rate"] != ROFORMER_WORKER_SAMPLE_RATE
        or geometry["channels"] != ROFORMER_WORKER_CHANNELS
        or geometry["frames"] > ROFORMER_WORKER_MAXIMUM_FRAMES
        or geometry["duration_seconds"] > ROFORMER_WORKER_MAXIMUM_SECONDS
    ):
        raise ValueError(
            "RoFormer protocol source must be stereo 44.1 kHz and at most 15 seconds"
        )
    return {
        "case_id": case_id,
        "source_id": source_id,
        "source_sha256": source_sha256,
        "canonical_sha256": canonical_sha256,
        "bytes": source_bytes,
        "geometry": geometry,
    }


def _plain_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{label} keys must be text")
        if isinstance(item, Mapping):
            result[key] = _plain_mapping(item, f"{label}.{key}")
        elif isinstance(item, (list, tuple)):
            result[key] = [
                _plain_mapping(entry, f"{label}.{key}")
                if isinstance(entry, Mapping)
                else entry
                for entry in item
            ]
        else:
            result[key] = item
    return result


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _CASE_ID_RE.fullmatch(value):
        raise ValueError(f"RoFormer protocol {label} is invalid")
    return value


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise ValueError(f"RoFormer protocol {label} is invalid")
    return value


def _strict_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"RoFormer protocol {label} must be an integer")
    return value


__all__ = [
    "ROFORMER_WORKER_MAXIMUM_CASES",
    "ROFORMER_WORKER_MAXIMUM_FRAMES",
    "ROFORMER_WORKER_MAXIMUM_SECONDS",
    "ROFORMER_WORKER_OUTPUT_ALLOWLIST",
    "ROFORMER_WORKER_PROTOCOL_SCHEMA",
    "ROFORMER_WORKER_ROLES",
    "_build_private_roformer_worker_protocol",
    "_validate_private_roformer_worker_protocol",
    "private_roformer_worker_protocol_sha256",
]
