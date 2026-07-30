"""Pure value validation for the blocked separation worker V2 projection.

The functions in this module validate JSON values supplied by a future
facade.  The values are evidence inputs, not authority.  This module cannot
access files, descriptors, leases, processes, models, networks or audio.
"""

from __future__ import annotations

import math
import re
from typing import Any, Mapping

from ._separation_checkpoint_canonical import canonical_json_bytes


_MAX_BYTES = 16 * 1024 * 1024 * 1024
_MAX_CHECKPOINT_BYTES = 8 * 1024 * 1024 * 1024
_MAX_JSON_DEPTH = 32
_MAX_JSON_ITEMS = 65_536
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._+:-]{0,191}$")
_VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._+-]{0,63}$")
_PREFLIGHT_ID_RE = re.compile(
    r"^separation-backend-preflight:[0-9a-f]{64}$"
)
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_URL_RE = re.compile(
    r"(?i)^(?:(?:https?|ftp)://|file:|mailto:|data:|www\.)"
)


def _names(value: str) -> frozenset[str]:
    return frozenset(value.split())


# Frozen pure data avoids importing source_roles.py and its pathlib authority.
# Tests assert parity with prepared_source_role_ids().
_PREPARED_ROLE_IDS = _names(
    """
    backing_vocals bass cymbals drums hat keys kick lead other other_kit
    piano rhythm snare strings synth toms vocals wind
    """
)
_CHECKPOINT_FORMATS = _names(
    "coreml onnx safetensors torch-state-dict"
)
_BINDING_FIELDS = _names(
    """
    worker_request_sha256 preflight_sha256 acceptance_artifact_sha256
    separation_request_fingerprint_sha256 output_allowlist_sha256
    execution_admission_binding_sha256 checkpoint_inspection_sha256
    checkpoint_classification_evidence_sha256 lease_observation_sha256
    checkpoint_sha256 checkpoint_bytes checkpoint_file_identity_sha256
    archive_evidence_sha256 pickle_evidence_sha256 runtime_artifact_sha256
    runtime_parent_measurements_sha256
    """
)
_LOGICAL_REQUEST_FIELDS = _names(
    "preflight identities roles settings seed isolation"
)
_IDENTITY_FIELDS = _names(
    "source checkpoint worker runtime dependency_lock"
)
_SOURCE_FIELDS = _names(
    "source_id source_sha256 canonical_sha256 bytes geometry"
)
_GEOMETRY_FIELDS = _names(
    "sample_rate channels frames duration_seconds"
)
_CHECKPOINT_FIELDS = _names("checkpoint_id format sha256 bytes")
_FILE_IDENTITY_FIELDS = _names("sha256 bytes")
_RUNTIME_FIELDS = _names(
    """
    runtime_id runtime_version python_version sha256 bytes
    verified_launcher_chain_sha256
    """
)
_PREFLIGHT_FIELDS = _names(
    "preflight_id preflight_sha256 status arm bindings"
)
_PREFLIGHT_ARM_FIELDS = _names(
    """
    arm_id separator_identity_id backend_id package_name package_version
    checkpoint_id checkpoint_format planned_device evaluation_scope
    """
)
_PREFLIGHT_DEVICE_FIELDS = _names("platform machine accelerator")
_PREFLIGHT_BINDING_FIELDS = _names(
    """
    preparation_sha256 acceptance_artifact_sha256 acceptance_profile_id
    hidden_manifest_sha256 hidden_split_sha256
    """
)
_ISOLATION_FIELDS = _names(
    """
    policy_id evidence_scope required_status provider_id profile_sha256
    environment_sha256 file_descriptor_policy_sha256 canary_sha256
    observer_id observer_sha256
    """
)


def _validated_bindings(value: Any) -> dict[str, Any]:
    bindings = _object_with_fields(value, _BINDING_FIELDS, "V2 bindings")
    _validate_path_free(bindings, "V2 bindings")
    for key, item in bindings.items():
        if key == "checkpoint_bytes":
            _bytes(item, key, maximum=_MAX_CHECKPOINT_BYTES)
        elif key == "pickle_evidence_sha256" and item is None:
            continue
        else:
            _sha(item, key)
    return bindings


def _validated_logical_request(
    value: Any,
    *,
    bindings: Mapping[str, Any],
) -> dict[str, Any]:
    request = _object_with_fields(
        value, _LOGICAL_REQUEST_FIELDS, "V2 logical request"
    )
    _validate_path_free(request, "V2 logical request")
    identities = _validated_identities(request["identities"])
    checkpoint = identities["checkpoint"]
    if (
        checkpoint["sha256"] != bindings["checkpoint_sha256"]
        or checkpoint["bytes"] != bindings["checkpoint_bytes"]
    ):
        raise ValueError(
            "logical checkpoint identity does not match facade bindings"
        )
    preflight = _validated_preflight(
        request["preflight"],
        bindings=bindings,
        checkpoint=checkpoint,
    )
    isolation = _validated_isolation(request["isolation"])
    roles = _validated_roles(request["roles"])
    settings = _json_object(request["settings"], "logical settings")
    _validate_path_free(settings, "logical settings")
    seed = request["seed"]
    if seed is not None:
        _strict_int(seed, "logical seed")
    return {
        "preflight": preflight,
        "identities": identities,
        "roles": roles,
        "settings": settings,
        "seed": seed,
        "isolation": isolation,
    }


def _validated_preflight(
    value: Any,
    *,
    bindings: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
) -> dict[str, Any]:
    preflight = _object_with_fields(
        value, _PREFLIGHT_FIELDS, "logical preflight"
    )
    preflight_id = preflight["preflight_id"]
    if (
        not isinstance(preflight_id, str)
        or _PREFLIGHT_ID_RE.fullmatch(preflight_id) is None
    ):
        raise ValueError("logical preflight_id is invalid")
    preflight_sha256 = _sha(
        preflight["preflight_sha256"], "logical preflight_sha256"
    )
    if (
        preflight_sha256 == "0" * 64
        or preflight["status"] != "verified_not_run"
        or preflight_sha256 != bindings["preflight_sha256"]
    ):
        raise ValueError("logical preflight is not the expected verified report")

    arm = _object_with_fields(
        preflight["arm"], _PREFLIGHT_ARM_FIELDS, "logical preflight arm"
    )
    if arm["arm_id"] not in {"baseline", "candidate"}:
        raise ValueError("logical preflight arm_id is invalid")
    for key in (
        "separator_identity_id",
        "backend_id",
        "package_name",
        "checkpoint_id",
    ):
        _identifier(arm[key], f"logical preflight arm.{key}")
    _version(arm["package_version"], "logical preflight package_version")
    if (
        arm["checkpoint_format"] not in _CHECKPOINT_FORMATS
        or arm["checkpoint_id"] != checkpoint["checkpoint_id"]
        or arm["checkpoint_format"] != checkpoint["format"]
        or arm["evaluation_scope"] != "private-local-evaluation-only"
    ):
        raise ValueError("logical preflight arm does not match checkpoint")
    device = _object_with_fields(
        arm["planned_device"],
        _PREFLIGHT_DEVICE_FIELDS,
        "logical preflight planned_device",
    )
    if (
        device["platform"] != "macos"
        or device["machine"] not in {"arm64", "x86_64"}
        or device["accelerator"] not in {"cpu", "mps"}
    ):
        raise ValueError("logical preflight planned_device is invalid")

    evidence = _object_with_fields(
        preflight["bindings"],
        _PREFLIGHT_BINDING_FIELDS,
        "logical preflight bindings",
    )
    for key in (
        "preparation_sha256",
        "acceptance_artifact_sha256",
        "hidden_manifest_sha256",
        "hidden_split_sha256",
    ):
        if (
            _sha(evidence[key], f"logical preflight bindings.{key}")
            == "0" * 64
        ):
            raise ValueError("logical preflight binding hash is all-zero")
    _identifier(
        evidence["acceptance_profile_id"],
        "logical preflight acceptance_profile_id",
    )
    if (
        evidence["acceptance_artifact_sha256"]
        != bindings["acceptance_artifact_sha256"]
    ):
        raise ValueError("logical preflight acceptance binding is invalid")
    return {
        "preflight_id": preflight_id,
        "preflight_sha256": preflight_sha256,
        "status": "verified_not_run",
        "arm": {
            **arm,
            "planned_device": device,
        },
        "bindings": evidence,
    }


def _validated_isolation(value: Any) -> dict[str, Any]:
    isolation = _object_with_fields(
        value, _ISOLATION_FIELDS, "logical isolation"
    )
    if (
        isolation["policy_id"] != "postinstall-os-deny-and-observe-v1"
        or isolation["evidence_scope"] != "private_development"
        or isolation["required_status"]
        != "development_enforced_observation_unproven"
    ):
        raise ValueError("logical isolation policy is invalid")
    _identifier(isolation["provider_id"], "logical isolation provider_id")
    _identifier(isolation["observer_id"], "logical isolation observer_id")
    for key in (
        "profile_sha256",
        "environment_sha256",
        "file_descriptor_policy_sha256",
        "canary_sha256",
        "observer_sha256",
    ):
        _sha(isolation[key], f"logical isolation {key}")
    return isolation


def _validated_identities(value: Any) -> dict[str, Any]:
    identities = _object_with_fields(
        value, _IDENTITY_FIELDS, "logical identities"
    )
    source = _object_with_fields(
        identities["source"], _SOURCE_FIELDS, "logical source identity"
    )
    source_sha256 = _sha(source["source_sha256"], "source_sha256")
    if source["source_id"] != f"sha256:{source_sha256}":
        raise ValueError("logical source_id does not match source_sha256")
    canonical_sha256 = _sha(
        source["canonical_sha256"], "canonical_sha256"
    )
    source_bytes = _bytes(source["bytes"], "source bytes")
    geometry = _validated_geometry(source["geometry"])

    checkpoint = _object_with_fields(
        identities["checkpoint"],
        _CHECKPOINT_FIELDS,
        "logical checkpoint identity",
    )
    checkpoint_id = _identifier(
        checkpoint["checkpoint_id"], "checkpoint_id"
    )
    if checkpoint["format"] not in _CHECKPOINT_FORMATS:
        raise ValueError("logical checkpoint format is invalid")
    checkpoint_sha256 = _sha(checkpoint["sha256"], "checkpoint sha256")
    checkpoint_bytes = _bytes(
        checkpoint["bytes"],
        "checkpoint bytes",
        maximum=_MAX_CHECKPOINT_BYTES,
    )

    runtime = _object_with_fields(
        identities["runtime"], _RUNTIME_FIELDS, "logical runtime identity"
    )
    runtime_id = _identifier(runtime["runtime_id"], "runtime_id")
    runtime_version = _version(
        runtime["runtime_version"], "runtime_version"
    )
    python_version = _version(runtime["python_version"], "python_version")
    runtime_sha256 = _sha(runtime["sha256"], "runtime sha256")
    runtime_bytes = _bytes(runtime["bytes"], "runtime bytes")
    launcher_sha256 = runtime["verified_launcher_chain_sha256"]
    if launcher_sha256 is not None:
        launcher_sha256 = _sha(
            launcher_sha256, "verified launcher chain sha256"
        )
    return {
        "source": {
            "source_id": f"sha256:{source_sha256}",
            "source_sha256": source_sha256,
            "canonical_sha256": canonical_sha256,
            "bytes": source_bytes,
            "geometry": geometry,
        },
        "checkpoint": {
            "checkpoint_id": checkpoint_id,
            "format": checkpoint["format"],
            "sha256": checkpoint_sha256,
            "bytes": checkpoint_bytes,
        },
        "worker": _validated_file_identity(
            identities["worker"], "worker"
        ),
        "runtime": {
            "runtime_id": runtime_id,
            "runtime_version": runtime_version,
            "python_version": python_version,
            "sha256": runtime_sha256,
            "bytes": runtime_bytes,
            "verified_launcher_chain_sha256": launcher_sha256,
        },
        "dependency_lock": _validated_file_identity(
            identities["dependency_lock"], "dependency lock"
        ),
    }


def _validated_file_identity(value: Any, label: str) -> dict[str, Any]:
    identity = _object_with_fields(
        value, _FILE_IDENTITY_FIELDS, f"logical {label} identity"
    )
    return {
        "sha256": _sha(identity["sha256"], f"{label} sha256"),
        "bytes": _bytes(identity["bytes"], f"{label} bytes"),
    }


def _validated_geometry(value: Any) -> dict[str, Any]:
    geometry = _object_with_fields(
        value, _GEOMETRY_FIELDS, "logical source geometry"
    )
    sample_rate = _strict_int(geometry["sample_rate"], "sample_rate")
    channels = _strict_int(geometry["channels"], "channels")
    frames = _strict_int(geometry["frames"], "frames")
    duration = _finite_number(
        geometry["duration_seconds"], "duration_seconds"
    )
    if not 1 <= sample_rate <= 768_000:
        raise ValueError("logical source sample_rate is outside bounds")
    if not 1 <= channels <= 64:
        raise ValueError("logical source channels is outside bounds")
    if frames <= 0:
        raise ValueError("logical source frames must be positive")
    if duration <= 0:
        raise ValueError("logical source duration must be positive")
    if abs(duration - frames / sample_rate) > max(
        1.0 / sample_rate, 1e-9
    ):
        raise ValueError("logical source duration does not match frames")
    return {
        "sample_rate": sample_rate,
        "channels": channels,
        "frames": frames,
        "duration_seconds": duration,
    }


def _validated_roles(value: Any) -> list[str]:
    if (
        not isinstance(value, (list, tuple))
        or isinstance(value, (str, bytes))
        or not value
    ):
        raise ValueError("logical roles are invalid")
    roles = list(value)
    if (
        roles != sorted(set(roles))
        or any(role not in _PREPARED_ROLE_IDS for role in roles)
    ):
        raise ValueError(
            "roles must be sorted unique canonical prepared roles"
        )
    _validate_path_free(roles, "logical roles")
    return roles


def _object_with_fields(
    value: Any,
    fields: frozenset[str],
    label: str,
) -> dict[str, Any]:
    document = _json_object(value, label)
    if set(document) != fields:
        raise ValueError(f"{label} fields are invalid")
    return document


def _json_object(value: Any, label: str) -> dict[str, Any]:
    document = _bounded_json_copy(value, label)
    if not isinstance(document, dict):
        raise ValueError(f"{label} must be an object")
    canonical_json_bytes(
        document,
        error_message="V2 value is not canonical JSON",
    )
    return document


def _bounded_json_copy(value: Any, label: str) -> Any:
    count = [0]

    def copy(item: Any, depth: int) -> Any:
        if depth > _MAX_JSON_DEPTH:
            raise ValueError(f"{label} exceeds maximum JSON depth")
        count[0] += 1
        if count[0] > _MAX_JSON_ITEMS:
            raise ValueError(f"{label} exceeds maximum JSON items")
        if isinstance(item, Mapping):
            result: dict[str, Any] = {}
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ValueError(f"{label} contains a non-string field")
                count[0] += 1
                if count[0] > _MAX_JSON_ITEMS:
                    raise ValueError(f"{label} exceeds maximum JSON items")
                result[key] = copy(child, depth + 1)
            return result
        if isinstance(item, (list, tuple)):
            return [copy(child, depth + 1) for child in item]
        if type(item) is float:
            if not math.isfinite(item):
                raise ValueError(f"{label} contains a non-finite number")
            return item
        if item is None or type(item) in {str, bool, int}:
            return item
        raise ValueError(f"{label} contains a non-JSON value")

    return copy(value, 0)


def _canonical_equal(left: Any, right: Any) -> bool:
    return canonical_json_bytes(
        _bounded_json_copy(left, "left canonical value")
    ) == canonical_json_bytes(
        _bounded_json_copy(right, "right canonical value")
    )


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{label} is not a lowercase SHA-256")
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")
    return value


def _version(value: Any, label: str) -> str:
    if not isinstance(value, str) or _VERSION_RE.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")
    return value


def _bytes(
    value: Any,
    label: str,
    *,
    maximum: int = _MAX_BYTES,
) -> int:
    number = _strict_int(value, label)
    if not 0 < number <= maximum:
        raise ValueError(f"{label} is outside supported bounds")
    return number


def _strict_int(value: Any, label: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{label} must be an integer")
    return value


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def _validate_path_free(value: Any, label: str) -> None:
    if isinstance(value, str):
        _validate_path_free_string(value, label)
    elif isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{label} contains a non-string field")
            _validate_path_free_string(key, f"{label} field")
            lowered = key.lower()
            if (
                lowered in {"path", "paths", "relative_path"}
                or lowered.endswith("_path")
                or lowered.endswith("_paths")
            ):
                raise ValueError(f"{label} contains a path field")
            _validate_path_free(item, f"{label}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_path_free(item, f"{label}[{index}]")
    elif type(value) is float:
        if not math.isfinite(value):
            raise ValueError(f"{label} contains a non-finite number")
    elif value is not None and type(value) not in {bool, int}:
        raise ValueError(f"{label} contains a non-JSON value")


def _validate_path_free_string(value: str, label: str) -> None:
    if (
        value != value.strip()
        or any(
            ord(character) < 32 or ord(character) == 127
            for character in value
        )
        or "/" in value
        or "\\" in value
        or value in {".", ".."}
        or _WINDOWS_ABSOLUTE_RE.match(value)
        or _URL_RE.match(value)
    ):
        raise ValueError(
            f"{label} contains a path, URL or non-canonical text"
        )
