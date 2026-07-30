"""Blocked design-evidence records for a future separation transport.

V2 is permanently a non-executable, stricter subset projection that a future
facade may derive from an already validated and inspected V1 request. Its
expected inputs are shape-checked values, not provenance or live authority.
Executable source, output and worker transport requires a new request schema
plus a separate blocked launch V2 that owns descriptor binding, size and
installation policy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ._separation_checkpoint_canonical import (
    canonical_json_bytes as _canonical_json,
    canonical_sha256 as _hash,
    deep_freeze as _freeze,
)
from ._separation_worker_request_v2_values import (
    _bounded_json_copy,
    _canonical_equal,
    _object_with_fields,
    _sha,
    _validated_bindings,
    _validated_logical_request,
    _validate_path_free,
)


SEPARATION_WORKER_REQUEST_V2_SCHEMA = "sunofriend.separation-worker-request.v2"
SEPARATION_WORKER_REQUEST_V2_POLICY_ID = (
    "private-path-free-checkpoint-transport-record-v2"
)
SEPARATION_WORKER_REQUEST_V2_EXECUTION_SUPPORTED = False
SEPARATION_WORKER_REQUEST_V2_MAXIMUM_BYTES = 1_048_576

_MAX_DECISION_REASONS = 128
_REASON_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,191}$")


def _names(value: str) -> frozenset[str]:
    return frozenset(value.split())


_TOP_LEVEL_FIELDS = _names(
    """
    schema policy_id evidence_scope publication_scope status run_status
    real_execution_supported execution_permitted selection_permitted
    bindings logical_request structure transport decision limitations
    capabilities effects request_sha256
    """
)
_STRUCTURE_FIELDS = _names(
    "logical_descriptor_requirements output_slots"
)
_TRANSPORT_FIELDS = _names(
    """
    source_transport output_transport worker_protocol
    checkpoint_fd5_installation child_checkpoint_remeasurement
    checkpoint_immutable_backing unsafe_executable_pickle_loading
    """
)
_DECISION_FIELDS = _names(
    "status run_status blocker_sources blockers advisories"
)
_BLOCKER_SOURCE_FIELDS = _names("admission_binding transport_v2")
_CAPABILITY_FIELDS = _names(
    """
    source_transport_defined output_transport_defined
    worker_protocol_implemented checkpoint_fd5_installation_supported
    child_checkpoint_remeasurement_supported
    checkpoint_immutable_backing_proven
    unsafe_executable_pickle_loading_authorized worker_start_supported
    checkpoint_loading_supported checkpoint_deserialization_supported
    model_import_supported inference_supported selection_supported
    publication_supported acceptance_supported promotion_supported
    child_executable_request_supported real_execution_supported
    """
)
_EFFECT_FIELDS = _names(
    """
    filesystem_accessed checkpoint_opened checkpoint_descriptor_retained
    checkpoint_lease_reserved checkpoint_descriptor_installed
    checkpoint_remeasured_in_child checkpoint_loaded
    checkpoint_deserialized model_imported process_started worker_started
    inference_started network_used audio_read outputs_created
    quarantine_created files_written publication_permitted
    selection_permitted acceptance_eligible promotion_eligible
    """
)
_ADMISSION_BINDING_MINIMUM = _names(
    """
    checkpoint_descriptor_not_carried_to_loader
    checkpoint_path_to_loader_toctou_unresolved
    static_checkpoint_inspection_not_load_authority
    """
)
_TRANSPORT_BLOCKERS = _names(
    """
    validated_v1_projection_facade_not_implemented
    source_transport_undefined output_transport_undefined
    worker_protocol_not_implemented checkpoint_fd5_installation_not_attempted
    child_checkpoint_remeasurement_not_implemented
    checkpoint_immutable_backing_not_proven
    unsafe_executable_pickle_loading_not_authorized
    real_execution_unsupported
    """
)
_LIMITATIONS = (
    "v2_is_blocked_design_evidence_not_a_child_executable_request",
    "v2_record_does_not_prove_expected_input_provenance",
    "v2_is_a_stricter_admitted_and_inspected_v1_subset",
    "future_executable_transport_requires_a_new_request_schema",
    "future_blocked_launch_v2_owns_descriptor_binding_size_and_installation",
    "v2_false_capabilities_are_permanent",
)
_TRANSPORT_POLICY = {
    "source_transport": "undefined",
    "output_transport": "undefined",
    "worker_protocol": "not_implemented",
    "checkpoint_fd5_installation": "not_attempted",
    "child_checkpoint_remeasurement": "not_implemented",
    "checkpoint_immutable_backing": "not_proven",
    "unsafe_executable_pickle_loading": "not_authorized",
}
_LOGICAL_DESCRIPTOR_ROWS = (
    (3, "sealed_path_free_worker_request", "parent_to_worker", "read_only"),
    (4, "bounded_path_free_worker_result", "worker_to_parent", "write_only"),
    (5, "read_only_checkpoint", "parent_to_worker", "read_only"),
)
_RAW_DESCRIPTOR_FIELDS = _names(
    """
    fd raw_fd source_fd checkpoint_fd file_descriptor raw_descriptor
    descriptor descriptor_number file_descriptor_number
    """
)


@dataclass(frozen=True, init=False)
class SeparationWorkerRequestV2Record(Mapping[str, Any]):
    """Exact immutable design record, never live transport authority."""

    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


def build_separation_worker_request_v2_record(
    *,
    expected_bindings: Mapping[str, Any],
    expected_logical_request: Mapping[str, Any],
    expected_admission_blockers: Sequence[str],
    expected_admission_advisories: Sequence[str],
) -> SeparationWorkerRequestV2Record:
    """Build a projection from expected values, which confer no authority."""

    bindings = _validated_bindings(expected_bindings)
    logical_request = _validated_logical_request(
        expected_logical_request,
        bindings=bindings,
    )
    inherited = _validated_reasons(
        expected_admission_blockers, "admission blockers"
    )
    if not _ADMISSION_BINDING_MINIMUM.issubset(inherited):
        raise ValueError("admission blockers omit required inherited blockers")
    advisories = _validated_reasons(
        expected_admission_advisories, "admission advisories"
    )
    transport_blockers = sorted(_TRANSPORT_BLOCKERS)
    payload = {
        "schema": SEPARATION_WORKER_REQUEST_V2_SCHEMA,
        "policy_id": SEPARATION_WORKER_REQUEST_V2_POLICY_ID,
        "evidence_scope": "private_development",
        "publication_scope": "private_local_contract_evidence",
        "status": "blocked",
        "run_status": "not_run",
        "real_execution_supported": False,
        "execution_permitted": False,
        "selection_permitted": False,
        "bindings": bindings,
        "logical_request": logical_request,
        "structure": {
            "logical_descriptor_requirements": (
                _logical_descriptor_requirements()
            ),
            "output_slots": _output_slots(logical_request["roles"]),
        },
        "transport": dict(_TRANSPORT_POLICY),
        "decision": {
            "status": "blocked",
            "run_status": "not_run",
            "blocker_sources": {
                "admission_binding": inherited,
                "transport_v2": transport_blockers,
            },
            "blockers": sorted({*inherited, *transport_blockers}),
            "advisories": advisories,
        },
        "limitations": list(_LIMITATIONS),
        "capabilities": {
            key: False for key in sorted(_CAPABILITY_FIELDS)
        },
        "effects": {key: False for key in sorted(_EFFECT_FIELDS)},
    }
    _validate_path_free(payload, "worker request v2")
    _reject_protocol_descriptor_claims(payload, ())
    return _new_record({**payload, "request_sha256": _hash(payload)})


def validate_separation_worker_request_v2_record(
    document: Mapping[str, Any],
    *,
    expected_bindings: Mapping[str, Any],
    expected_logical_request: Mapping[str, Any],
    expected_admission_blockers: Sequence[str],
    expected_admission_advisories: Sequence[str],
) -> SeparationWorkerRequestV2Record:
    """Recompute from expected facade values, which are not authority here."""

    expected = build_separation_worker_request_v2_record(
        expected_bindings=expected_bindings,
        expected_logical_request=expected_logical_request,
        expected_admission_blockers=expected_admission_blockers,
        expected_admission_advisories=expected_admission_advisories,
    )
    actual = _new_record(document)
    if not _canonical_equal(dict(actual), dict(expected)):
        raise ValueError(
            "worker request v2 does not match expected facade components"
        )
    return actual


def _validate_separation_worker_request_v2_record_shape(
    value: Any,
) -> SeparationWorkerRequestV2Record:
    """Revalidate one exact issued V2 value without claiming provenance.

    This private helper exists for parent-owned contracts that already hold
    an exact ``SeparationWorkerRequestV2Record``.  It re-runs the complete
    structural, semantic and self-hash validation, but deliberately does not
    turn the record into execution authority or prove where its projection
    inputs came from.
    """

    if type(value) is not SeparationWorkerRequestV2Record:
        raise ValueError(
            "worker request v2 must be an exact validated record"
        )
    checked = _new_record(value)
    if not _canonical_equal(dict(value), dict(checked)):
        raise ValueError("worker request v2 record changed after validation")
    return value


def separation_worker_request_v2_sha256(
    document: Mapping[str, Any],
) -> str:
    """Hash canonical request bytes excluding only the record self-hash."""

    value = _bounded_json_copy(document, "worker request v2")
    if not isinstance(value, dict):
        raise ValueError("worker request v2 must be an object")
    _validate_path_free(value, "worker request v2")
    _reject_protocol_descriptor_claims(value, ())
    value.pop("request_sha256", None)
    return _hash(value)


def _new_record(document: Mapping[str, Any]) -> SeparationWorkerRequestV2Record:
    value = _object_with_fields(
        document, _TOP_LEVEL_FIELDS, "worker request v2"
    )
    _validate_path_free(value, "worker request v2")
    _reject_protocol_descriptor_claims(value, ())
    if value["schema"] != SEPARATION_WORKER_REQUEST_V2_SCHEMA:
        raise ValueError("unsupported worker request v2 schema")
    if value["policy_id"] != SEPARATION_WORKER_REQUEST_V2_POLICY_ID:
        raise ValueError("unsupported worker request v2 policy")
    if (
        value["evidence_scope"] != "private_development"
        or value["publication_scope"]
        != "private_local_contract_evidence"
        or value["status"] != "blocked"
        or value["run_status"] != "not_run"
        or value["real_execution_supported"] is not False
        or value["execution_permitted"] is not False
        or value["selection_permitted"] is not False
    ):
        raise ValueError("worker request v2 must remain blocked and not run")

    bindings = _validated_bindings(value["bindings"])
    logical_request = _validated_logical_request(
        value["logical_request"], bindings=bindings
    )
    if not _canonical_equal(logical_request, value["logical_request"]):
        raise ValueError("worker request v2 logical request is not canonical")
    structure = _object_with_fields(
        value["structure"],
        _STRUCTURE_FIELDS,
        "worker request v2 structure",
    )
    expected_structure = {
        "logical_descriptor_requirements": (
            _logical_descriptor_requirements()
        ),
        "output_slots": _output_slots(logical_request["roles"]),
    }
    if not _canonical_equal(structure, expected_structure):
        raise ValueError("worker request v2 structure is invalid")
    if (
        _object_with_fields(
            value["transport"],
            _TRANSPORT_FIELDS,
            "worker request v2 transport policy",
        )
        != _TRANSPORT_POLICY
    ):
        raise ValueError("worker request v2 transport policy is invalid")

    decision = _object_with_fields(
        value["decision"], _DECISION_FIELDS, "worker request v2 decision"
    )
    sources = _object_with_fields(
        decision["blocker_sources"],
        _BLOCKER_SOURCE_FIELDS,
        "worker request v2 blocker sources",
    )
    inherited = _validated_reasons(
        sources["admission_binding"], "admission blockers"
    )
    transport = _validated_reasons(
        sources["transport_v2"], "transport blockers"
    )
    advisories = _validated_reasons(
        decision["advisories"], "admission advisories"
    )
    if (
        not _ADMISSION_BINDING_MINIMUM.issubset(inherited)
        or decision["status"] != "blocked"
        or decision["run_status"] != "not_run"
        or transport != sorted(_TRANSPORT_BLOCKERS)
        or decision["blockers"] != sorted({*inherited, *transport})
        or decision["advisories"] != advisories
    ):
        raise ValueError("worker request v2 decision is invalid")
    if value["limitations"] != list(_LIMITATIONS):
        raise ValueError("worker request v2 limitations are invalid")
    _all_false(
        value["capabilities"],
        _CAPABILITY_FIELDS,
        "worker request v2 capabilities",
    )
    _all_false(
        value["effects"], _EFFECT_FIELDS, "worker request v2 effects"
    )
    _sha(value["request_sha256"], "worker request v2 request_sha256")
    if value["request_sha256"] != separation_worker_request_v2_sha256(value):
        raise ValueError("worker request v2 hash is invalid")
    if len(_canonical_json(value)) > SEPARATION_WORKER_REQUEST_V2_MAXIMUM_BYTES:
        raise ValueError("worker request v2 exceeds sealed FD3 maximum bytes")

    record = object.__new__(SeparationWorkerRequestV2Record)
    object.__setattr__(record, "_document", _freeze(value))
    return record


def _validated_reasons(value: Any, label: str) -> list[str]:
    if (
        not isinstance(value, (list, tuple))
        or isinstance(value, (str, bytes))
        or len(value) > _MAX_DECISION_REASONS
    ):
        raise ValueError(f"worker request v2 {label} are invalid")
    reasons = list(value)
    if (
        reasons != sorted(set(reasons))
        or any(
            not isinstance(item, str)
            or _REASON_RE.fullmatch(item) is None
            for item in reasons
        )
    ):
        raise ValueError(
            f"worker request v2 {label} must be sorted unique identifiers"
        )
    _validate_path_free(reasons, f"worker request v2 {label}")
    return reasons


def _logical_descriptor_requirements() -> list[dict[str, Any]]:
    return [
        {
            "logical_descriptor": number,
            "purpose": purpose,
            "direction": direction,
            "access": access,
        }
        for number, purpose, direction, access in _LOGICAL_DESCRIPTOR_ROWS
    ]


def _output_slots(roles: Sequence[str]) -> list[dict[str, str]]:
    return [
        {
            "role": role,
            "artifact_kind": "pcm24_wav",
            "slot_id": f"stem-{index:02d}",
        }
        for index, role in enumerate(roles, 1)
    ]


def _all_false(
    value: Any,
    fields: frozenset[str],
    label: str,
) -> None:
    document = _object_with_fields(value, fields, label)
    if any(item is not False for item in document.values()):
        raise ValueError(f"{label} must all be false")


def _reject_protocol_descriptor_claims(
    value: Any,
    location: tuple[Any, ...],
) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(
                    "worker request v2 contains a non-string field"
                )
            lowered = key.lower()
            in_settings = location[:2] == (
                "logical_request",
                "settings",
            )
            generic_model_setting = (
                in_settings and lowered in {"fd", "descriptor"}
            )
            if (
                lowered in _RAW_DESCRIPTOR_FIELDS
                or lowered.endswith("_fd")
            ) and not generic_model_setting:
                raise ValueError("worker request v2 contains a raw descriptor")
            if lowered == "logical_descriptor" and not (
                len(location) == 3
                and location[0] == "structure"
                and location[1] == "logical_descriptor_requirements"
                and isinstance(location[2], int)
            ):
                raise ValueError(
                    "worker request v2 logical descriptor is out of place"
                )
            _reject_protocol_descriptor_claims(item, (*location, key))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_protocol_descriptor_claims(item, (*location, index))


__all__ = [
    "SEPARATION_WORKER_REQUEST_V2_EXECUTION_SUPPORTED",
    "SEPARATION_WORKER_REQUEST_V2_MAXIMUM_BYTES",
    "SEPARATION_WORKER_REQUEST_V2_POLICY_ID",
    "SEPARATION_WORKER_REQUEST_V2_SCHEMA",
    "SeparationWorkerRequestV2Record",
    "build_separation_worker_request_v2_record",
    "separation_worker_request_v2_sha256",
    "validate_separation_worker_request_v2_record",
]
