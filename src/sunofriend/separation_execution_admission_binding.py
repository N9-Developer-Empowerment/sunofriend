"""Trusted-checkpoint binding around one blocked V1 execution admission.

The V1 execution-admission record intentionally contains only synthetic,
untrusted reports.  This module preserves that API and schema unchanged.  It
adds a separate, pure V2 wrapper which revalidates the complete V1 record and
cross-binds its checkpoint policy to an exact parent-issued static checkpoint
inspection.

Only the checkpoint inspection has parent-observation authority.  Runtime,
isolation, output and resource reports remain synthetic, the inspected
descriptor is already closed, and no descriptor is carried to a loader.
Consequently every wrapper remains ``blocked`` and ``not_run``.  This module
has no filesystem, process, network, model, audio, import, deserialization or
write surface.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from .separation_checkpoint_inspection import (
    SeparationCheckpointInspection,
    SeparationCheckpointInspectionRequest,
    validate_separation_checkpoint_inspection,
)
from .separation_checkpoint_policy import SeparationCheckpointPolicyRecord
from .separation_execution_admission import (
    SeparationExecutionAdmissionRecord,
    SeparationIsolationEvidence,
    SeparationOutputBoundaryEvidence,
    SeparationResourceLimitEvidence,
    SeparationRuntimeClosureEvidence,
    validate_separation_execution_admission,
)


SEPARATION_EXECUTION_ADMISSION_BINDING_SCHEMA = (
    "sunofriend.separation-execution-admission-binding.v2"
)
SEPARATION_EXECUTION_ADMISSION_BINDING_POLICY_ID = (
    "private-development-trusted-checkpoint-admission-binding-v2"
)
TRUSTED_CHECKPOINT_ADMISSION_EXECUTION_SUPPORTED = False

_CLASSIFICATION_MAPPING_ID = "static-inspection-to-checkpoint-policy-v1"
_INSPECTION_TO_POLICY_CONTAINER_KIND = {
    "torch-zip-pickle-model-package": "torch-pickle-model-package",
    "unknown": "uninspected",
}
_ADDITIONAL_BLOCKERS = frozenset(
    {
        "checkpoint_descriptor_not_carried_to_loader",
        "checkpoint_path_to_loader_toctou_unresolved",
        "static_checkpoint_inspection_not_load_authority",
    }
)
_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema",
        "policy_id",
        "evidence_scope",
        "publication_scope",
        "public_redacted_projection_available",
        "evidence_authority",
        "reported_claims_trusted",
        "status",
        "run_status",
        "real_execution_supported",
        "execution_permitted",
        "bindings",
        "checkpoint_static_inspection",
        "decision",
        "effects",
        "binding_sha256",
    }
)
_EFFECT_FIELDS = frozenset(
    {
        "filesystem_accessed",
        "checkpoint_opened",
        "checkpoint_loaded",
        "checkpoint_deserialized",
        "model_imported",
        "process_started",
        "worker_started",
        "inference_started",
        "network_used",
        "audio_read",
        "outputs_created",
        "quarantine_created",
        "files_written",
        "publication_permitted",
        "acceptance_eligible",
        "promotion_eligible",
    }
)
_URL_RE = re.compile(r"(?:[A-Za-z][A-Za-z0-9+.-]*://|www\.)")
_WINDOWS_RE = re.compile(r"^[A-Za-z]:[\\/]")


@dataclass(frozen=True, init=False)
class SeparationExecutionAdmissionBindingRecord(Mapping[str, Any]):
    """Deeply immutable mixed-authority, blocked-only admission wrapper."""

    _document: Mapping[str, Any]
    _admission: SeparationExecutionAdmissionRecord
    _checkpoint_policy: SeparationCheckpointPolicyRecord
    _inspection: SeparationCheckpointInspection
    _inspection_request: SeparationCheckpointInspectionRequest

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


def build_separation_execution_admission_binding(
    *,
    execution_admission: SeparationExecutionAdmissionRecord,
    checkpoint_policy: SeparationCheckpointPolicyRecord,
    runtime: SeparationRuntimeClosureEvidence,
    isolation: SeparationIsolationEvidence,
    output: SeparationOutputBoundaryEvidence,
    resources: SeparationResourceLimitEvidence,
    checkpoint_inspection: SeparationCheckpointInspection,
    trusted_checkpoint_inspection: SeparationCheckpointInspection,
    trusted_checkpoint_inspection_request: (
        SeparationCheckpointInspectionRequest
    ),
) -> SeparationExecutionAdmissionBindingRecord:
    """Cross-bind one trusted static inspection without enabling a worker."""

    admission = _trusted_v1_admission(
        execution_admission=execution_admission,
        checkpoint_policy=checkpoint_policy,
        runtime=runtime,
        isolation=isolation,
        output=output,
        resources=resources,
    )
    inspection = _trusted_inspection(
        checkpoint_inspection,
        trusted_inspection=trusted_checkpoint_inspection,
        trusted_request=trusted_checkpoint_inspection_request,
    )
    cross_binding = _checkpoint_cross_binding(
        admission=admission,
        checkpoint_policy=checkpoint_policy,
        inspection=inspection,
    )
    blockers = sorted(
        {
            *admission["decision"]["blockers"],
            *_ADDITIONAL_BLOCKERS,
        }
    )
    advisories = list(admission["decision"]["advisories"])
    payload = {
        "schema": SEPARATION_EXECUTION_ADMISSION_BINDING_SCHEMA,
        "policy_id": SEPARATION_EXECUTION_ADMISSION_BINDING_POLICY_ID,
        "evidence_scope": "private_development",
        "publication_scope": "private_local_contract_evidence",
        "public_redacted_projection_available": False,
        "evidence_authority": (
            "mixed_parent_checkpoint_inspection_and_synthetic_reports"
        ),
        "reported_claims_trusted": False,
        "status": "blocked",
        "run_status": "not_run",
        "real_execution_supported": (
            TRUSTED_CHECKPOINT_ADMISSION_EXECUTION_SUPPORTED
        ),
        "execution_permitted": False,
        "bindings": {
            "execution_admission_sha256": admission["admission_sha256"],
            "checkpoint_policy_sha256": (
                admission["bindings"]["checkpoint_policy_sha256"]
            ),
            "checkpoint_inspection_sha256": (
                inspection["inspection_sha256"]
            ),
            "checkpoint_classification_evidence_sha256": (
                inspection["classification"][
                    "classification_evidence_sha256"
                ]
            ),
            "worker_request_sha256": (
                inspection["bindings"]["worker_request_sha256"]
            ),
            "preflight_sha256": (
                inspection["bindings"]["preflight_sha256"]
            ),
            "acceptance_artifact_sha256": (
                inspection["bindings"]["acceptance_artifact_sha256"]
            ),
            "checkpoint_sha256": inspection["checkpoint"]["sha256"],
        },
        "checkpoint_static_inspection": cross_binding,
        "decision": {
            "status": "blocked",
            "run_status": "not_run",
            "blockers": blockers,
            "advisories": advisories,
        },
        "effects": {
            "filesystem_accessed": False,
            "checkpoint_opened": False,
            "checkpoint_loaded": False,
            "checkpoint_deserialized": False,
            "model_imported": False,
            "process_started": False,
            "worker_started": False,
            "inference_started": False,
            "network_used": False,
            "audio_read": False,
            "outputs_created": False,
            "quarantine_created": False,
            "files_written": False,
            "publication_permitted": False,
            "acceptance_eligible": False,
            "promotion_eligible": False,
        },
    }
    _path_free(payload, "execution admission binding")
    document = {**payload, "binding_sha256": _hash(payload)}
    return _new_record(
        document,
        admission=admission,
        checkpoint_policy=checkpoint_policy,
        inspection=inspection,
        inspection_request=trusted_checkpoint_inspection_request,
    )


def validate_separation_execution_admission_binding(
    document: Mapping[str, Any],
    *,
    execution_admission: SeparationExecutionAdmissionRecord,
    checkpoint_policy: SeparationCheckpointPolicyRecord,
    runtime: SeparationRuntimeClosureEvidence,
    isolation: SeparationIsolationEvidence,
    output: SeparationOutputBoundaryEvidence,
    resources: SeparationResourceLimitEvidence,
    checkpoint_inspection: SeparationCheckpointInspection,
    trusted_checkpoint_inspection: SeparationCheckpointInspection,
    trusted_checkpoint_inspection_request: (
        SeparationCheckpointInspectionRequest
    ),
) -> SeparationExecutionAdmissionBindingRecord:
    """Recompute the complete wrapper from all exact source authorities."""

    expected = build_separation_execution_admission_binding(
        execution_admission=execution_admission,
        checkpoint_policy=checkpoint_policy,
        runtime=runtime,
        isolation=isolation,
        output=output,
        resources=resources,
        checkpoint_inspection=checkpoint_inspection,
        trusted_checkpoint_inspection=trusted_checkpoint_inspection,
        trusted_checkpoint_inspection_request=(
            trusted_checkpoint_inspection_request
        ),
    )
    value = _json_object(document, "execution admission binding")
    if value != _plain(expected):
        raise ValueError(
            "execution admission binding does not match trusted evidence"
        )
    return _new_record(
        value,
        admission=expected._admission,
        checkpoint_policy=expected._checkpoint_policy,
        inspection=expected._inspection,
        inspection_request=trusted_checkpoint_inspection_request,
    )


def separation_execution_admission_binding_sha256(
    document: Mapping[str, Any],
) -> str:
    """Return the canonical wrapper hash excluding only its self-hash."""

    value = _json_object(document, "execution admission binding")
    value.pop("binding_sha256", None)
    return _hash(value)


def _trusted_v1_admission(
    *,
    execution_admission: Any,
    checkpoint_policy: SeparationCheckpointPolicyRecord,
    runtime: SeparationRuntimeClosureEvidence,
    isolation: SeparationIsolationEvidence,
    output: SeparationOutputBoundaryEvidence,
    resources: SeparationResourceLimitEvidence,
) -> SeparationExecutionAdmissionRecord:
    if type(execution_admission) is not SeparationExecutionAdmissionRecord:
        raise ValueError(
            "execution admission must be an exact canonical V1 record"
        )
    checked = validate_separation_execution_admission(
        execution_admission,
        checkpoint_policy=checkpoint_policy,
        runtime=runtime,
        isolation=isolation,
        output=output,
        resources=resources,
    )
    if _plain(checked) != _plain(execution_admission):
        raise ValueError("execution admission is not canonical")
    return checked


def _trusted_inspection(
    value: Any,
    *,
    trusted_inspection: SeparationCheckpointInspection,
    trusted_request: SeparationCheckpointInspectionRequest,
) -> SeparationCheckpointInspection:
    if type(value) is not SeparationCheckpointInspection:
        raise ValueError(
            "checkpoint inspection must be an exact parent-issued record"
        )
    return validate_separation_checkpoint_inspection(
        value,
        trusted_inspection=trusted_inspection,
        trusted_request=trusted_request,
    )


def _checkpoint_cross_binding(
    *,
    admission: SeparationExecutionAdmissionRecord,
    checkpoint_policy: SeparationCheckpointPolicyRecord,
    inspection: SeparationCheckpointInspection,
) -> dict[str, Any]:
    policy_checkpoint = checkpoint_policy["checkpoint"]
    inspected_checkpoint = inspection["checkpoint"]
    inspected_classification = inspection["classification"]
    inspected_kind = inspected_classification["container_kind"]
    mapped_kind = _INSPECTION_TO_POLICY_CONTAINER_KIND.get(inspected_kind)
    if mapped_kind is None:
        raise ValueError(
            "checkpoint inspection classification has no code-owned mapping"
        )
    expected = (
        policy_checkpoint["checkpoint_id"],
        policy_checkpoint["declared_format"],
        policy_checkpoint["sha256"],
        policy_checkpoint["bytes"],
        policy_checkpoint["classification_evidence_sha256"],
        policy_checkpoint["classified_container_kind"],
    )
    observed = (
        inspected_checkpoint["checkpoint_id"],
        inspected_checkpoint["declared_format"],
        inspected_checkpoint["sha256"],
        inspected_checkpoint["bytes"],
        inspected_classification["classification_evidence_sha256"],
        mapped_kind,
    )
    if observed != expected:
        raise ValueError(
            "checkpoint policy does not bind trusted static inspection"
        )
    if (
        admission["bindings"]["checkpoint_policy_sha256"]
        != checkpoint_policy["policy_sha256"]
        or admission["bindings"]["checkpoint_sha256"]
        != inspected_checkpoint["sha256"]
    ):
        raise ValueError(
            "execution admission does not bind checkpoint inspection"
        )
    return {
        "status": "cross_bound_inspected_not_loaded",
        "evidence_authority": "parent_issued_static_observation",
        "inspection_sha256": inspection["inspection_sha256"],
        "classification_evidence_sha256": (
            inspected_classification["classification_evidence_sha256"]
        ),
        "classification_mapping_id": _CLASSIFICATION_MAPPING_ID,
        "inspection_container_kind": inspected_kind,
        "policy_container_kind": mapped_kind,
        "checkpoint_descriptor_transport": "not_carried_to_loader",
        "checkpoint_path_to_loader_toctou": "unresolved",
        "authorizes_loading": False,
        "authorizes_execution": False,
    }


def _new_record(
    document: Mapping[str, Any],
    *,
    admission: SeparationExecutionAdmissionRecord,
    checkpoint_policy: SeparationCheckpointPolicyRecord,
    inspection: SeparationCheckpointInspection,
    inspection_request: SeparationCheckpointInspectionRequest,
) -> SeparationExecutionAdmissionBindingRecord:
    value = _json_object(document, "execution admission binding")
    if set(value) != _TOP_LEVEL_FIELDS:
        raise ValueError("execution admission binding fields are invalid")
    if value.get("schema") != SEPARATION_EXECUTION_ADMISSION_BINDING_SCHEMA:
        raise ValueError("unsupported execution admission binding schema")
    if value.get("policy_id") != (
        SEPARATION_EXECUTION_ADMISSION_BINDING_POLICY_ID
    ):
        raise ValueError("unsupported execution admission binding policy")
    if value.get("binding_sha256") != (
        separation_execution_admission_binding_sha256(value)
    ):
        raise ValueError("execution admission binding hash is invalid")
    if (
        value.get("status") != "blocked"
        or value.get("run_status") != "not_run"
        or value.get("real_execution_supported") is not False
        or value.get("execution_permitted") is not False
        or value.get("reported_claims_trusted") is not False
        or value.get("public_redacted_projection_available") is not False
    ):
        raise ValueError(
            "execution admission binding must remain blocked and untrusted"
        )
    decision = value.get("decision")
    if (
        not isinstance(decision, dict)
        or decision.get("status") != "blocked"
        or decision.get("run_status") != "not_run"
        or decision.get("blockers") != sorted(set(decision.get("blockers", ())))
        or decision.get("advisories")
        != sorted(set(decision.get("advisories", ())))
        or not _ADDITIONAL_BLOCKERS.issubset(decision.get("blockers", ()))
    ):
        raise ValueError("execution admission binding decision is invalid")
    checkpoint = value.get("checkpoint_static_inspection")
    if (
        not isinstance(checkpoint, dict)
        or checkpoint.get("status") != "cross_bound_inspected_not_loaded"
        or checkpoint.get("authorizes_loading") is not False
        or checkpoint.get("authorizes_execution") is not False
        or checkpoint.get("checkpoint_descriptor_transport")
        != "not_carried_to_loader"
        or checkpoint.get("checkpoint_path_to_loader_toctou")
        != "unresolved"
    ):
        raise ValueError(
            "checkpoint inspection binding cannot authorize loading"
        )
    effects = value.get("effects")
    if (
        not isinstance(effects, dict)
        or set(effects) != _EFFECT_FIELDS
        or any(item is not False for item in effects.values())
    ):
        raise ValueError("execution admission binding effects must all be false")
    expected_bindings = {
        "execution_admission_sha256": admission["admission_sha256"],
        "checkpoint_policy_sha256": (
            admission["bindings"]["checkpoint_policy_sha256"]
        ),
        "checkpoint_inspection_sha256": inspection["inspection_sha256"],
        "checkpoint_classification_evidence_sha256": (
            inspection["classification"]["classification_evidence_sha256"]
        ),
        "worker_request_sha256": (
            inspection["bindings"]["worker_request_sha256"]
        ),
        "preflight_sha256": inspection["bindings"]["preflight_sha256"],
        "acceptance_artifact_sha256": (
            inspection["bindings"]["acceptance_artifact_sha256"]
        ),
        "checkpoint_sha256": inspection["checkpoint"]["sha256"],
    }
    if value.get("bindings") != expected_bindings:
        raise ValueError(
            "execution admission binding hashes do not bind source evidence"
        )
    if value.get("checkpoint_static_inspection") != _checkpoint_cross_binding(
        admission=admission,
        checkpoint_policy=checkpoint_policy,
        inspection=inspection,
    ):
        raise ValueError(
            "checkpoint inspection projection does not bind source evidence"
        )
    if (
        decision["blockers"]
        != sorted(
            {
                *admission["decision"]["blockers"],
                *_ADDITIONAL_BLOCKERS,
            }
        )
        or decision["advisories"]
        != list(admission["decision"]["advisories"])
    ):
        raise ValueError("execution admission decision does not bind V1")
    _path_free(value, "execution admission binding")
    record = object.__new__(SeparationExecutionAdmissionBindingRecord)
    object.__setattr__(record, "_document", _freeze(value))
    object.__setattr__(record, "_admission", admission)
    object.__setattr__(record, "_checkpoint_policy", checkpoint_policy)
    object.__setattr__(record, "_inspection", inspection)
    object.__setattr__(record, "_inspection_request", inspection_request)
    return record


def _json_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    plain = _plain(value)
    if not isinstance(plain, dict) or any(
        not isinstance(key, str) for key in plain
    ):
        raise ValueError(f"{label} must be a string-keyed object")
    _canonical_json(plain)
    return plain


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "execution admission binding is not canonical JSON"
        ) from exc


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _path_free(value: Any, label: str) -> None:
    if isinstance(value, str):
        if (
            _URL_RE.search(value)
            or value.startswith(("/", "~"))
            or _WINDOWS_RE.match(value)
            or "/" in value
            or "\\" in value
            or "\0" in value
        ):
            raise ValueError(f"{label} contains a path or URL")
    elif isinstance(value, Mapping):
        for key, item in value.items():
            if key == "path" or key.endswith("_path"):
                raise ValueError(f"{label} contains a path field")
            _path_free(item, f"{label}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _path_free(item, f"{label}[{index}]")
    elif value is not None and not isinstance(value, (bool, int)):
        raise ValueError(f"{label} contains a non-canonical value")


__all__ = [
    "SEPARATION_EXECUTION_ADMISSION_BINDING_POLICY_ID",
    "SEPARATION_EXECUTION_ADMISSION_BINDING_SCHEMA",
    "TRUSTED_CHECKPOINT_ADMISSION_EXECUTION_SUPPORTED",
    "SeparationExecutionAdmissionBindingRecord",
    "build_separation_execution_admission_binding",
    "separation_execution_admission_binding_sha256",
    "validate_separation_execution_admission_binding",
]
