"""Pure request/result contracts for one isolated separation worker.

Requests are private and path-bearing. Results are path-free evidence only:
they never express quality, ranking, preference, selection or promotion.
This module performs no filesystem access, imports no model and starts no
process.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from .separation_backend_preflight import (
    SEPARATION_BACKEND_PREFLIGHT_STATUS_VERIFIED,
    validate_separation_backend_preflight,
)
from .separation_acceptance import (
    validate_separation_acceptance_thresholds,
)
from .separation_contract import (
    SeparationAudioGeometry,
    SeparationRequest,
    _canonical_json_bytes,
    _freeze_json,
    _mapping,
    _strict_int,
    _thaw_json,
)
from .source_roles import prepared_source_role_ids


SEPARATION_WORKER_REQUEST_SCHEMA = "sunofriend.separation-worker-request.v1"
SEPARATION_WORKER_RESULT_SCHEMA = "sunofriend.separation-worker-result.v1"
SEPARATION_WORKER_ISOLATION_POLICY = "postinstall-os-deny-and-observe-v1"
SEPARATION_ISOLATION_STATUSES = frozenset(
    {"blocked", "development_enforced_observation_unproven"}
)

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._+:-]{0,191}$")
_VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._+-]{0,63}$")
_URL_RE = re.compile(r"(?:[A-Za-z][A-Za-z0-9+.-]*://|www\.)")
_WINDOWS_RE = re.compile(r"^[A-Za-z]:[\\/]")
_MAX_BYTES = 16 * 1024 * 1024 * 1024

_REQUEST_FIELDS = {
    "schema",
    "request_sha256",
    "preflight",
    "separation_request_fingerprint_sha256",
    "paths",
    "identities",
    "roles",
    "settings",
    "seed",
    "output_allowlist",
    "isolation",
}
_PATH_FIELDS = {
    "source_path",
    "output_dir",
    "checkpoint_path",
    "worker_path",
    "runtime_python_path",
    "dependency_lock_path",
}
_IDENTITY_FIELDS = {
    "source",
    "checkpoint",
    "worker",
    "runtime",
    "dependency_lock",
}
_ISOLATION_FIELDS = {
    "policy_id",
    "evidence_scope",
    "required_status",
    "provider_id",
    "profile_sha256",
    "environment_sha256",
    "file_descriptor_policy_sha256",
    "canary_sha256",
    "observer_id",
    "observer_sha256",
}
_RESULT_FIELDS = {
    "schema",
    "result_sha256",
    "worker_request_sha256",
    "preflight_id",
    "preflight_sha256",
    "separation_request_fingerprint_sha256",
    "status",
    "input_hashes",
    "outputs",
    "enforcement",
    "error",
}
_OUTPUT_FIELDS = {"role", "relative_path", "sha256", "bytes", "geometry"}
_CHECK_FIELDS = {
    "network_denial",
    "input_read_only",
    "output_allowlist",
    "child_process_denial",
    "checkpoint_identity_before_load",
}
_EFFECT_FIELDS = {
    "network_used",
    "outside_output_writes",
    "child_processes_started",
}


@dataclass(frozen=True)
class SeparationRuntimeArtifactIdentity:
    """Parent-owned identity for the exact runtime launcher artifact."""

    path: Path
    sha256: str
    bytes: int
    verified_launcher_chain_sha256: str | None = None

    def __post_init__(self) -> None:
        canonical = _absolute(str(self.path), "runtime artifact path")
        object.__setattr__(self, "path", Path(canonical))
        _sha(self.sha256, "runtime artifact sha256")
        _bytes(self.bytes, "runtime artifact bytes")
        if self.verified_launcher_chain_sha256 is not None:
            _sha(
                self.verified_launcher_chain_sha256,
                "verified launcher chain sha256",
            )


def build_separation_worker_request(
    *,
    preflight: Mapping[str, Any],
    trusted_acceptance: Mapping[str, Any],
    separation_request: SeparationRequest,
    worker_path: str | Path,
    trusted_runtime_artifact: SeparationRuntimeArtifactIdentity,
    dependency_lock_path: str | Path,
    source_bytes: int,
    checkpoint_bytes: int,
    worker_sha256: str,
    worker_bytes: int,
    runtime_id: str,
    runtime_version: str,
    python_version: str,
    dependency_lock_sha256: str,
    dependency_lock_bytes: int,
    isolation: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Build a private request from identities measured by the parent."""

    checked = validate_separation_backend_preflight(preflight)
    runtime_artifact = _trusted_runtime_artifact(trusted_runtime_artifact)
    separation_request.validate()
    arm = checked["arm"]
    roles = list(separation_request.requested_roles)
    payload = {
        "schema": SEPARATION_WORKER_REQUEST_SCHEMA,
        "preflight": _preflight_binding(checked),
        "separation_request_fingerprint_sha256": (
            separation_request.fingerprint_sha256
        ),
        "paths": {
            "source_path": str(separation_request.source_path),
            "output_dir": str(separation_request.output_dir),
            "checkpoint_path": str(separation_request.checkpoint_path),
            "worker_path": str(worker_path),
            "runtime_python_path": str(runtime_artifact.path),
            "dependency_lock_path": str(dependency_lock_path),
        },
        "identities": {
            "source": {
                "source_id": separation_request.source_id,
                "source_sha256": separation_request.source_sha256,
                "canonical_sha256": separation_request.canonical_sha256,
                "bytes": source_bytes,
                "geometry": separation_request.source_geometry.to_dict(),
            },
            "checkpoint": {
                "checkpoint_id": separation_request.checkpoint_id,
                "format": arm["checkpoint_format"],
                "sha256": separation_request.checkpoint_sha256,
                "bytes": checkpoint_bytes,
            },
            "worker": {"sha256": worker_sha256, "bytes": worker_bytes},
            "runtime": {
                "runtime_id": runtime_id,
                "runtime_version": runtime_version,
                "python_version": python_version,
                "sha256": runtime_artifact.sha256,
                "bytes": runtime_artifact.bytes,
                "verified_launcher_chain_sha256": (
                    runtime_artifact.verified_launcher_chain_sha256
                ),
            },
            "dependency_lock": {
                "sha256": dependency_lock_sha256,
                "bytes": dependency_lock_bytes,
            },
        },
        "roles": roles,
        "settings": _thaw_json(separation_request.settings),
        "seed": separation_request.seed,
        "output_allowlist": [
            {"role": role, "relative_path": f"STEMS/{role}.wav"} for role in roles
        ],
        "isolation": _thaw_json(isolation),
    }
    document = {**payload, "request_sha256": _hash(payload)}
    return validate_separation_worker_request(
        document,
        trusted_preflight=checked,
        trusted_acceptance=trusted_acceptance,
        trusted_separation_request=separation_request,
        trusted_runtime_artifact=runtime_artifact,
    )


def validate_separation_worker_request(
    document: Mapping[str, Any],
    *,
    trusted_preflight: Mapping[str, Any],
    trusted_acceptance: Mapping[str, Any],
    trusted_separation_request: SeparationRequest,
    trusted_runtime_artifact: SeparationRuntimeArtifactIdentity,
) -> Mapping[str, Any]:
    """Validate a request against trusted parent objects and freeze it."""

    value = _plain(document, "worker request")
    _fields(value, _REQUEST_FIELDS, "worker request")
    if value["schema"] != SEPARATION_WORKER_REQUEST_SCHEMA:
        raise ValueError("unsupported worker request schema")
    preflight = validate_separation_backend_preflight(trusted_preflight)
    if preflight["status"] != SEPARATION_BACKEND_PREFLIGHT_STATUS_VERIFIED:
        raise ValueError("worker request requires a verified preflight")
    if value["preflight"] != _preflight_binding(preflight):
        raise ValueError("worker request contains a forged preflight binding")
    registered = _registered_identity(trusted_acceptance, preflight)
    runtime_artifact = _trusted_runtime_artifact(trusted_runtime_artifact)
    trusted_separation_request.validate()
    if (
        _sha(value["separation_request_fingerprint_sha256"], "request fingerprint")
        != trusted_separation_request.fingerprint_sha256
    ):
        raise ValueError("worker fingerprint does not bind request")

    paths = _private_paths(value["paths"])
    expected_paths = {
        "source_path": str(trusted_separation_request.source_path),
        "output_dir": str(trusted_separation_request.output_dir),
        "checkpoint_path": str(trusted_separation_request.checkpoint_path),
        "runtime_python_path": str(runtime_artifact.path),
    }
    if any(paths[key] != expected for key, expected in expected_paths.items()):
        raise ValueError("worker paths do not bind separation request")
    identities = _identities(value["identities"])
    source, checkpoint, arm = (
        identities["source"],
        identities["checkpoint"],
        preflight["arm"],
    )
    request = trusted_separation_request
    if (
        source["source_id"] != request.source_id
        or source["source_sha256"] != request.source_sha256
        or source["canonical_sha256"] != request.canonical_sha256
        or source["geometry"] != request.source_geometry.to_dict()
        or checkpoint["checkpoint_id"] != request.checkpoint_id
        or checkpoint["sha256"] != request.checkpoint_sha256
        or checkpoint["format"] != arm["checkpoint_format"]
        or arm["backend_id"] != request.backend_id
        or arm["checkpoint_id"] != request.checkpoint_id
        or identities["worker"]["sha256"] != registered["worker_sha256"]
        or identities["dependency_lock"]["sha256"]
        != registered["runtime"]["dependency_lock_sha256"]
        or identities["runtime"]["runtime_id"] != registered["runtime"]["runtime_id"]
        or identities["runtime"]["runtime_version"]
        != registered["runtime"]["runtime_version"]
        or identities["runtime"]["python_version"]
        != registered["runtime"]["python_version"]
        or identities["runtime"]["sha256"] != runtime_artifact.sha256
        or identities["runtime"]["bytes"] != runtime_artifact.bytes
        or identities["runtime"]["verified_launcher_chain_sha256"]
        != runtime_artifact.verified_launcher_chain_sha256
        or checkpoint["checkpoint_id"] != registered["checkpoint"]["checkpoint_id"]
        or checkpoint["format"] != registered["checkpoint"]["format"]
        or checkpoint["sha256"] != registered["checkpoint"]["sha256"]
        or checkpoint["bytes"] != registered["checkpoint"]["bytes"]
    ):
        raise ValueError(
            "worker identities do not bind source, preflight and registration"
        )

    roles = _roles(value["roles"])
    if tuple(roles) != request.requested_roles:
        raise ValueError("worker roles do not bind request")
    settings = _plain(value["settings"], "settings")
    _path_free(settings, "settings")
    if _canonical_json_bytes(settings) != _canonical_json_bytes(
        _thaw_json(request.settings)
    ):
        raise ValueError("worker settings do not bind request")
    seed = value["seed"]
    if seed is not None:
        _strict_int(seed, "seed")
    if seed != request.seed:
        raise ValueError("worker seed does not bind request")
    _allowlist(value["output_allowlist"], roles)
    _isolation(value["isolation"])
    if _sha(value["request_sha256"], "request_sha256") != (
        separation_worker_request_sha256(value)
    ):
        raise ValueError("worker request hash is invalid")
    return _freeze_json(value)


def separation_worker_request_sha256(document: Mapping[str, Any]) -> str:
    """Hash a request excluding only its self-hash."""

    value = _plain(document, "worker request")
    value.pop("request_sha256", None)
    return _hash(value)


def build_separation_worker_result(
    *,
    worker_request: Mapping[str, Any],
    trusted_preflight: Mapping[str, Any],
    trusted_acceptance: Mapping[str, Any],
    trusted_separation_request: SeparationRequest,
    trusted_runtime_artifact: SeparationRuntimeArtifactIdentity,
    status: str,
    after_input_hashes: Mapping[str, str],
    outputs: Sequence[Mapping[str, Any]],
    enforcement: Mapping[str, Any],
    error: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    """Build one path-free result from already measured worker evidence."""

    request = validate_separation_worker_request(
        worker_request,
        trusted_preflight=trusted_preflight,
        trusted_acceptance=trusted_acceptance,
        trusted_separation_request=trusted_separation_request,
        trusted_runtime_artifact=trusted_runtime_artifact,
    )
    before = _input_hashes(request["identities"])
    if set(after_input_hashes) != set(before):
        raise ValueError("after input hashes must cover every input")
    inputs = {}
    for name in sorted(before):
        after = _sha(after_input_hashes[name], f"{name} after hash")
        inputs[name] = {
            "before_sha256": before[name],
            "after_sha256": after,
            "unchanged": before[name] == after,
        }
    payload = {
        "schema": SEPARATION_WORKER_RESULT_SCHEMA,
        "worker_request_sha256": request["request_sha256"],
        "preflight_id": request["preflight"]["preflight_id"],
        "preflight_sha256": request["preflight"]["preflight_sha256"],
        "separation_request_fingerprint_sha256": request[
            "separation_request_fingerprint_sha256"
        ],
        "status": status,
        "input_hashes": inputs,
        "outputs": [_thaw_json(item) for item in outputs],
        "enforcement": _thaw_json(enforcement),
        "error": _thaw_json(error) if error is not None else None,
    }
    document = {**payload, "result_sha256": _hash(payload)}
    return validate_separation_worker_result(
        document,
        worker_request=request,
        trusted_preflight=trusted_preflight,
        trusted_acceptance=trusted_acceptance,
        trusted_separation_request=trusted_separation_request,
        trusted_runtime_artifact=trusted_runtime_artifact,
    )


def validate_separation_worker_result(
    document: Mapping[str, Any],
    *,
    worker_request: Mapping[str, Any],
    trusted_preflight: Mapping[str, Any],
    trusted_acceptance: Mapping[str, Any],
    trusted_separation_request: SeparationRequest,
    trusted_runtime_artifact: SeparationRuntimeArtifactIdentity,
) -> Mapping[str, Any]:
    """Validate and freeze a path-free result against its private request."""

    request = validate_separation_worker_request(
        worker_request,
        trusted_preflight=trusted_preflight,
        trusted_acceptance=trusted_acceptance,
        trusted_separation_request=trusted_separation_request,
        trusted_runtime_artifact=trusted_runtime_artifact,
    )
    value = _plain(document, "worker result")
    _fields(value, _RESULT_FIELDS, "worker result")
    if value["schema"] != SEPARATION_WORKER_RESULT_SCHEMA:
        raise ValueError("unsupported worker result schema")
    bindings = {
        "worker_request_sha256": request["request_sha256"],
        "preflight_id": request["preflight"]["preflight_id"],
        "preflight_sha256": request["preflight"]["preflight_sha256"],
        "separation_request_fingerprint_sha256": request[
            "separation_request_fingerprint_sha256"
        ],
    }
    if any(value[key] != expected for key, expected in bindings.items()):
        raise ValueError("worker result does not bind request and preflight")
    if value["status"] not in {"blocked", "cancelled", "complete", "failed"}:
        raise ValueError("worker result status is invalid")
    unchanged = _input_evidence(value["input_hashes"], request["identities"])
    outputs = _outputs(value["outputs"], request)
    _path_free(value, "worker result", allow_output_relative_paths=True)
    enforcement = _enforcement(value["enforcement"], request["isolation"])
    error = _error(value["error"])
    if value["status"] == "complete":
        if error is not None or not unchanged:
            raise ValueError("complete result requires unchanged inputs")
        if len(outputs) != len(request["output_allowlist"]):
            raise ValueError("complete result requires every allowed output")
        _complete_enforcement(enforcement, request["isolation"])
    elif outputs or error is None:
        raise ValueError("non-complete result requires only an error")
    if value["status"] == "blocked" and (
        enforcement["worker_started"] or enforcement["inference_started"]
    ):
        raise ValueError("blocked result cannot report started execution")
    if _sha(value["result_sha256"], "result_sha256") != (
        separation_worker_result_sha256(value)
    ):
        raise ValueError("worker result hash is invalid")
    return _freeze_json(value)


def separation_worker_result_sha256(document: Mapping[str, Any]) -> str:
    """Hash a path-free result excluding only its self-hash."""

    value = _plain(document, "worker result")
    value.pop("result_sha256", None)
    return _hash(value)


def _preflight_binding(preflight: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "preflight_id": preflight["preflight_id"],
        "preflight_sha256": preflight["preflight_sha256"],
        "status": preflight["status"],
        "arm": _thaw_json(preflight["arm"]),
        "bindings": _thaw_json(preflight["bindings"]),
    }


def _registered_identity(
    acceptance_document: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> Mapping[str, Any]:
    acceptance = validate_separation_acceptance_thresholds(acceptance_document)
    bindings, arm = preflight["bindings"], preflight["arm"]
    if (
        bindings["acceptance_artifact_sha256"] != acceptance["artifact_sha256"]
        or bindings["acceptance_profile_id"] != acceptance["profile_id"]
    ):
        raise ValueError("preflight does not bind trusted acceptance")
    identity_key = (
        "baseline_separator" if arm["arm_id"] == "baseline" else "candidate_separator"
    )
    identity = acceptance["identities"][identity_key]
    checkpoint = identity["checkpoint"]
    if checkpoint["kind"] != "checkpoint":
        raise ValueError("worker contract v1 requires a registered checkpoint")
    if (
        arm["separator_identity_id"] != identity["identity_id"]
        or arm["backend_id"] != identity["backend_id"]
        or arm["package_name"] != identity["package_name"]
        or arm["package_version"] != identity["package_version"]
        or arm["checkpoint_id"] != checkpoint["checkpoint_id"]
        or arm["checkpoint_format"] != checkpoint["format"]
    ):
        raise ValueError("preflight arm does not bind registered identity")
    return identity


def _private_paths(value: Any) -> dict[str, str]:
    paths = _plain(value, "paths")
    _fields(paths, _PATH_FIELDS, "paths")
    checked = {key: _absolute(item, f"paths.{key}") for key, item in paths.items()}
    aliases = [
        unicodedata.normalize("NFC", item).casefold() for item in checked.values()
    ]
    if len(aliases) != len(set(aliases)):
        raise ValueError("worker paths contain aliases")
    # The supported deployment profile is macOS, where the default APFS
    # volume is case-insensitive.  Compare the same NFC/case-folded aliases
    # used for duplicate detection so `/PRIVATE/...` cannot disguise a path
    # physically contained by `/private/...`.
    output = PurePosixPath(
        unicodedata.normalize("NFC", checked["output_dir"]).casefold()
    )
    if any(
        _relative_to(
            PurePosixPath(unicodedata.normalize("NFC", item).casefold()),
            output,
        )
        for key, item in checked.items()
        if key != "output_dir"
    ):
        raise ValueError("worker inputs must be outside output directory")
    return checked


def _identities(value: Any) -> dict[str, Any]:
    items = _plain(value, "identities")
    _fields(items, _IDENTITY_FIELDS, "identities")
    source = _exact(
        items["source"],
        {"source_id", "source_sha256", "canonical_sha256", "bytes", "geometry"},
        "source identity",
    )
    if source["source_id"] != "sha256:" + _sha(
        source["source_sha256"], "source_sha256"
    ):
        raise ValueError("source id does not match source hash")
    _sha(source["canonical_sha256"], "canonical_sha256")
    _bytes(source["bytes"], "source bytes")
    source["geometry"] = SeparationAudioGeometry.from_dict(source["geometry"]).to_dict()
    checkpoint = _exact(
        items["checkpoint"],
        {"checkpoint_id", "format", "sha256", "bytes"},
        "checkpoint identity",
    )
    _id(checkpoint["checkpoint_id"], "checkpoint_id")
    if checkpoint["format"] not in {
        "coreml",
        "onnx",
        "safetensors",
        "torch-state-dict",
    }:
        raise ValueError("checkpoint format is invalid")
    _sha(checkpoint["sha256"], "checkpoint sha256")
    _bytes(checkpoint["bytes"], "checkpoint bytes")
    runtime = _exact(
        items["runtime"],
        {
            "runtime_id",
            "runtime_version",
            "python_version",
            "sha256",
            "bytes",
            "verified_launcher_chain_sha256",
        },
        "runtime identity",
    )
    _id(runtime["runtime_id"], "runtime_id")
    _version(runtime["runtime_version"], "runtime_version")
    _version(runtime["python_version"], "python_version")
    _sha(runtime["sha256"], "runtime sha256")
    _bytes(runtime["bytes"], "runtime bytes")
    if runtime["verified_launcher_chain_sha256"] is not None:
        _sha(
            runtime["verified_launcher_chain_sha256"],
            "verified launcher chain sha256",
        )
    return {
        "source": source,
        "checkpoint": checkpoint,
        "worker": _file_identity(items["worker"], "worker"),
        "runtime": runtime,
        "dependency_lock": _file_identity(items["dependency_lock"], "dependency lock"),
    }


def _file_identity(value: Any, label: str) -> dict[str, Any]:
    item = _exact(value, {"sha256", "bytes"}, f"{label} identity")
    _sha(item["sha256"], f"{label} sha256")
    _bytes(item["bytes"], f"{label} bytes")
    return item


def _roles(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("roles must be an array")
    roles = [_text(item, "role") for item in value]
    if (
        not roles
        or roles != sorted(set(roles))
        or any(role not in prepared_source_role_ids() for role in roles)
    ):
        raise ValueError("roles must be sorted unique canonical prepared roles")
    return roles


def _allowlist(value: Any, roles: Sequence[str]) -> None:
    if not isinstance(value, (list, tuple)):
        raise ValueError("output allowlist must be an array")
    actual = [
        _exact(item, {"role", "relative_path"}, "output allowlist entry")
        for item in value
    ]
    for item in actual:
        _relative_output(item["relative_path"])
    expected = [{"role": role, "relative_path": f"STEMS/{role}.wav"} for role in roles]
    if actual != expected:
        raise ValueError("output allowlist is not canonical")


def _isolation(value: Any) -> dict[str, Any]:
    isolation = _exact(value, _ISOLATION_FIELDS, "isolation")
    if isolation["policy_id"] != SEPARATION_WORKER_ISOLATION_POLICY:
        raise ValueError("isolation policy is unsupported")
    if isolation["evidence_scope"] != "private_development":
        raise ValueError("isolation evidence scope is invalid")
    required = isolation["required_status"]
    if required != "development_enforced_observation_unproven":
        raise ValueError("required isolation status is invalid")
    _id(isolation["provider_id"], "isolation provider")
    _id(isolation["observer_id"], "isolation observer")
    for key in (
        "profile_sha256",
        "environment_sha256",
        "file_descriptor_policy_sha256",
        "canary_sha256",
        "observer_sha256",
    ):
        _sha(isolation[key], key)
    return isolation


def _input_evidence(value: Any, identities: Mapping[str, Any]) -> bool:
    evidence = _plain(value, "input_hashes")
    _fields(evidence, _IDENTITY_FIELDS, "input_hashes")
    before = _input_hashes(identities)
    unchanged = True
    for name, item in evidence.items():
        facts = _exact(
            item,
            {"before_sha256", "after_sha256", "unchanged"},
            f"input_hashes.{name}",
        )
        after = _sha(facts["after_sha256"], f"{name} after hash")
        if facts["before_sha256"] != before[name]:
            raise ValueError("input before hash does not bind request")
        same = before[name] == after
        if facts["unchanged"] is not same:
            raise ValueError("input unchanged evidence is inconsistent")
        unchanged = unchanged and same
    return unchanged


def _input_hashes(identities: Mapping[str, Any]) -> dict[str, str]:
    return {
        "source": identities["source"]["canonical_sha256"],
        "checkpoint": identities["checkpoint"]["sha256"],
        "worker": identities["worker"]["sha256"],
        "runtime": identities["runtime"]["sha256"],
        "dependency_lock": identities["dependency_lock"]["sha256"],
    }


def _outputs(value: Any, request: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("outputs must be an array")
    allowed = {
        item["role"]: item["relative_path"] for item in request["output_allowlist"]
    }
    outputs = []
    for item in value:
        output = _exact(item, _OUTPUT_FIELDS, "worker output")
        role, path = (
            _text(output["role"], "output role"),
            _relative_output(output["relative_path"]),
        )
        if allowed.get(role) != path:
            raise ValueError("worker output is outside the allowlist")
        _sha(output["sha256"], "output sha256")
        _bytes(output["bytes"], "output bytes")
        output["geometry"] = SeparationAudioGeometry.from_dict(
            output["geometry"]
        ).to_dict()
        outputs.append(output)
    if [item["role"] for item in outputs] != sorted({item["role"] for item in outputs}):
        raise ValueError("outputs must be sorted and unique")
    return outputs


def _enforcement(value: Any, requested_isolation: Mapping[str, Any]) -> dict[str, Any]:
    evidence = _exact(
        value,
        {
            "isolation_status",
            "isolation",
            "checks",
            "effects",
            "worker_started",
            "inference_started",
        },
        "enforcement",
    )
    status = evidence["isolation_status"]
    if status not in SEPARATION_ISOLATION_STATUSES:
        raise ValueError("isolation status is invalid")
    isolation = _isolation(evidence["isolation"])
    if isolation != _thaw_json(requested_isolation):
        raise ValueError("enforcement does not bind isolation request")
    checks = _exact(evidence["checks"], _CHECK_FIELDS, "enforcement checks")
    if any(
        item not in {"enforced", "not_attempted", "violated"}
        for item in checks.values()
    ):
        raise ValueError("enforcement check state is invalid")
    effects = _exact(evidence["effects"], _EFFECT_FIELDS, "enforcement effects")
    if any(not isinstance(item, bool) for item in effects.values()):
        raise ValueError("enforcement effects must be boolean")
    if not isinstance(evidence["worker_started"], bool) or not isinstance(
        evidence["inference_started"], bool
    ):
        raise ValueError("worker start evidence must be boolean")
    if evidence["inference_started"] and not evidence["worker_started"]:
        raise ValueError("inference cannot start before worker")
    return evidence


def _complete_enforcement(
    evidence: Mapping[str, Any], isolation: Mapping[str, Any]
) -> None:
    actual = evidence["isolation_status"]
    if (
        isolation["required_status"] != "development_enforced_observation_unproven"
        or actual != "development_enforced_observation_unproven"
    ):
        raise ValueError("complete result requires development isolation evidence")
    if any(item != "enforced" for item in evidence["checks"].values()):
        raise ValueError("complete result requires enforced controls")
    if any(evidence["effects"].values()) or not (
        evidence["worker_started"] and evidence["inference_started"]
    ):
        raise ValueError("complete result has incompatible effects")


def _error(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    error = _exact(value, {"code", "message", "retryable"}, "error")
    _id(error["code"], "error code")
    _path_free(error["message"], "error message")
    if not isinstance(error["retryable"], bool):
        raise ValueError("error retryable must be boolean")
    return error


def _absolute(value: Any, label: str) -> str:
    text, path = _text(value, label), PurePosixPath(str(value))
    if (
        not text.startswith("/")
        or text.startswith("//")
        or text == "/"
        or "\\" in text
        or _URL_RE.search(text)
        or unicodedata.normalize("NFC", text) != text
        or str(path) != text
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"{label} is not a canonical absolute local path")
    return text


def _relative_output(value: Any) -> str:
    text, path = _text(value, "relative output"), PurePosixPath(str(value))
    if (
        str(path) != text
        or len(path.parts) != 2
        or path.parts[0] != "STEMS"
        or path.suffix != ".wav"
        or any(part in {"", ".", ".."} for part in path.parts)
        or _URL_RE.search(text)
        or "\\" in text
    ):
        raise ValueError("relative output contains an alias or escape")
    return text


def _path_free(
    value: Any,
    label: str,
    *,
    allow_output_relative_paths: bool = False,
) -> None:
    if isinstance(value, str):
        if (
            _URL_RE.search(value)
            or value.startswith(("/", "~"))
            or _WINDOWS_RE.match(value)
            or "/" in value
            or "\\" in value
        ):
            raise ValueError(f"{label} contains a path or URL")
    elif isinstance(value, Mapping):
        for key, item in value.items():
            if allow_output_relative_paths and key == "outputs":
                if not isinstance(item, (list, tuple)):
                    raise ValueError("worker result outputs must be an array")
                for index, output in enumerate(item):
                    _path_free_output(output, f"{label}.outputs[{index}]")
                continue
            if key == "path" or key.endswith("_path"):
                raise ValueError(f"{label} contains path field {key}")
            _path_free(item, f"{label}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _path_free(item, f"{label}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{label} contains a non-finite number")
    elif value is not None and not isinstance(value, (bool, int, float)):
        raise ValueError(f"{label} contains a non-JSON value")


def _path_free_output(value: Any, label: str) -> None:
    output = _plain(value, label)
    for key, item in output.items():
        if key == "relative_path":
            _relative_output(item)
        else:
            _path_free(item, f"{label}.{key}")


def _trusted_runtime_artifact(
    value: Any,
) -> SeparationRuntimeArtifactIdentity:
    if type(value) is not SeparationRuntimeArtifactIdentity:
        raise ValueError(
            "trusted runtime artifact must be a parent-owned exact identity"
        )
    canonical = _absolute(str(value.path), "runtime artifact path")
    if value.path != Path(canonical):
        raise ValueError("trusted runtime artifact path is not canonical")
    _sha(value.sha256, "runtime artifact sha256")
    _bytes(value.bytes, "runtime artifact bytes")
    if value.verified_launcher_chain_sha256 is not None:
        _sha(
            value.verified_launcher_chain_sha256,
            "verified launcher chain sha256",
        )
    return value


def _plain(value: Any, label: str) -> dict[str, Any]:
    mapping = _mapping(value, label)
    plain = _thaw_json(mapping)
    if not isinstance(plain, dict):
        raise ValueError(f"{label} must be an object")
    return plain


def _exact(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    item = _plain(value, label)
    _fields(item, expected, label)
    return item


def _fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields are invalid")


def _text(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\0" in value
    ):
        raise ValueError(f"{label} must be canonical non-empty text")
    return value


def _id(value: Any, label: str) -> str:
    text = _text(value, label)
    if not _ID_RE.fullmatch(text):
        raise ValueError(f"{label} is invalid")
    return text


def _version(value: Any, label: str) -> str:
    text = _text(value, label)
    if not _VERSION_RE.fullmatch(text):
        raise ValueError(f"{label} is invalid")
    return text


def _sha(value: Any, label: str) -> str:
    text = _text(value, label)
    if not _SHA_RE.fullmatch(text):
        raise ValueError(f"{label} is not a lowercase SHA-256")
    return text


def _bytes(value: Any, label: str) -> int:
    number = _strict_int(value, label)
    if not 0 < number <= _MAX_BYTES:
        raise ValueError(f"{label} is outside supported bounds")
    return number


def _relative_to(path: PurePosixPath, parent: PurePosixPath) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


__all__ = [
    "SEPARATION_ISOLATION_STATUSES",
    "SeparationRuntimeArtifactIdentity",
    "SEPARATION_WORKER_ISOLATION_POLICY",
    "SEPARATION_WORKER_REQUEST_SCHEMA",
    "SEPARATION_WORKER_RESULT_SCHEMA",
    "build_separation_worker_request",
    "build_separation_worker_result",
    "separation_worker_request_sha256",
    "separation_worker_result_sha256",
    "validate_separation_worker_request",
    "validate_separation_worker_result",
]
