"""Pure blocked launch-plan V2 records for checkpoint transport design.

This internal module describes a future path-free FD3, FD4 and FD5 transport
without implementing any part of it.  The record is permanently blocked and
non-executable.  In particular, it contains no path, raw descriptor, argv,
reservation authority, worker protocol, process operation, checkpoint loader
or model operation.

The fixed construction requirements are not proof.  A caller must validate
the exact live lease, exact reservation and exact V2 request under the lease
lock before invoking the private builder.  Neither this module nor the
serialized record can perform, prove or authorize that validation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from ._separation_checkpoint_canonical import (
    canonical_json_bytes as _canonical_json,
    canonical_sha256 as _hash,
    deep_freeze as _freeze,
    plain as _plain,
)
from ._separation_checkpoint_transport_records import (
    SEPARATION_WORKER_REQUEST_V2_MAXIMUM_BYTES,
    SeparationWorkerRequestV2Record,
    _validate_separation_worker_request_v2_record_shape,
)
from ._separation_worker_request_v2_values import (
    _bounded_json_copy,
    _object_with_fields,
    _sha,
    _validate_path_free,
)


_SEPARATION_LAUNCH_PLAN_V2_SCHEMA = "sunofriend.separation-launch-plan.v2"
_SEPARATION_LAUNCH_PLAN_V2_POLICY_ID = (
    "private-blocked-checkpoint-transport-plan-v2"
)
_SEPARATION_LAUNCH_PLAN_V2_EXECUTION_SUPPORTED = False
_SEPARATION_LAUNCH_PLAN_V2_MAXIMUM_BYTES = 262_144
_LOGICAL_DESCRIPTOR_POLICY_ID = "blocked-logical-descriptor-design-v2"
_FD5_INSTALLATION_DESIGN_POLICY_ID = (
    "atomic-child-checkpoint-fd5-design-v2"
)
_WORKER_RESULT_MAXIMUM_BYTES = 16_777_216
_MAX_CHECKPOINT_BYTES = 8 * 1024 * 1024 * 1024
_MAX_DECISION_REASONS = 256
_REASON_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,191}$")


def _names(value: str) -> frozenset[str]:
    return frozenset(value.split())


_REQUEST_BINDING_FIELDS = _names(
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
_TOP_LEVEL_FIELDS = _names(
    """
    schema policy_id evidence_scope publication_scope status run_status
    real_execution_supported execution_permitted worker_start_permitted
    descriptor_installation_permitted bindings binding_authority
    construction_requirements logical_descriptor_design
    checkpoint_fd5_installation_design decision limitations capabilities
    effects plan_sha256
    """
)
_BINDING_FIELDS = frozenset(
    {
        *_REQUEST_BINDING_FIELDS,
        "worker_request_v2_sha256",
        "worker_request_v2_bindings_sha256",
    }
)
_BINDING_AUTHORITY_FIELDS = _names(
    "lease_facade_cross_binding_requirements sealed_but_unproven"
)
_CONSTRUCTION_REQUIREMENT_FIELDS = _names(
    """
    authority_scope exact_worker_request_v2_required
    exact_reservation_required lease_remeasurement_under_lock_required
    conditions_proven_by_serialized_record
    reservation_authority_serialized authorizes_descriptor_installation
    authorizes_worker_start authorizes_execution
    """
)
_DESCRIPTOR_DESIGN_FIELDS = _names(
    """
    policy_id inherit_unlisted_descriptors raw_descriptor_values_serialized
    logical_descriptors design_sha256
    """
)
_FD5_INSTALLATION_DESIGN_FIELDS = _names(
    """
    policy_id status run_status target_logical_descriptor
    parent_checkpoint_path_reopened parent_descriptor_table_mutated
    installation_implemented installation_attempted atomicity_boundary
    installation_mechanism required_sequence design_sha256
    """
)
_DECISION_FIELDS = _names(
    "status run_status blocker_sources blockers advisories"
)
_BLOCKER_SOURCE_FIELDS = _names("worker_request_v2 launch_plan_v2")
_CAPABILITY_FIELDS = _names(
    """
    source_transport_defined output_transport_defined
    worker_protocol_implemented fd3_materialization_supported
    fd4_result_capture_supported checkpoint_fd5_installation_supported
    child_checkpoint_remeasurement_supported child_handshake_supported
    checkpoint_immutable_backing_proven
    unsafe_executable_pickle_loading_authorized process_start_supported
    worker_start_supported checkpoint_loading_supported
    checkpoint_deserialization_supported model_import_supported
    inference_supported selection_supported publication_supported
    acceptance_supported promotion_supported real_execution_supported
    """
)
_EFFECT_FIELDS = _names(
    """
    source_opened output_opened request_descriptor_materialized
    result_descriptor_created checkpoint_descriptor_installed
    checkpoint_remeasured_in_child checkpoint_loaded
    checkpoint_deserialized model_imported process_started worker_started
    inference_started network_used audio_read outputs_created
    quarantine_created files_written publication_permitted
    selection_permitted acceptance_eligible promotion_eligible
    """
)
_SEALED_BUT_UNPROVEN_BINDINGS = (
    "execution_admission_binding_sha256",
    "runtime_artifact_sha256",
    "runtime_parent_measurements_sha256",
)
_RESERVATION_CROSS_BOUND_BINDINGS = tuple(
    sorted(_REQUEST_BINDING_FIELDS - set(_SEALED_BUT_UNPROVEN_BINDINGS))
)
_REQUEST_V2_REQUIRED_BLOCKERS = _names(
    """
    checkpoint_descriptor_not_carried_to_loader
    checkpoint_path_to_loader_toctou_unresolved
    static_checkpoint_inspection_not_load_authority
    validated_v1_projection_facade_not_implemented
    source_transport_undefined output_transport_undefined
    worker_protocol_not_implemented checkpoint_fd5_installation_not_attempted
    child_checkpoint_remeasurement_not_implemented
    checkpoint_immutable_backing_not_proven
    unsafe_executable_pickle_loading_not_authorized
    real_execution_unsupported
    """
)
_LAUNCH_V2_BLOCKERS = _names(
    """
    blocked_launch_v2_not_child_executable
    exact_reservation_is_not_installation_authority
    atomic_checkpoint_fd5_installation_not_implemented
    child_fd5_identity_and_hash_handshake_not_implemented
    runtime_and_admission_authority_not_revalidated_by_lease
    shared_checkpoint_file_offset_protocol_not_defined
    """
)
_LIMITATIONS = (
    "serialized_plan_does_not_prove_construction_preconditions",
    "serialized_plan_does_not_carry_reservation_authority",
    "ordinary_checkpoint_inode_is_not_immutable_backing",
    "logical_descriptor_design_does_not_install_a_descriptor",
    "worker_request_v2_is_permanently_non_executable",
    "future_executable_transport_requires_new_request_and_launch_schemas",
)
_CONSTRUCTION_REQUIREMENTS = {
    "authority_scope": "requirements_only_not_proven_by_record",
    "exact_worker_request_v2_required": True,
    "exact_reservation_required": True,
    "lease_remeasurement_under_lock_required": True,
    "conditions_proven_by_serialized_record": False,
    "reservation_authority_serialized": False,
    "authorizes_descriptor_installation": False,
    "authorizes_worker_start": False,
    "authorizes_execution": False,
}
_FD5_REQUIRED_SEQUENCE = (
    "revalidate_exact_live_lease_reservation_and_request",
    "hold_lease_lock_through_child_creation_result",
    "remeasure_retained_checkpoint_before_child_creation",
    "verify_retained_checkpoint_is_read_only_and_noninheritable",
    "allocate_collision_free_staging_descriptors",
    "require_offset_independent_child_reader_or_serialized_offset_protocol",
    "install_logical_fd5_with_one_child_creation_file_action",
    "set_child_fd5_noninheritable_immediately_after_exec",
    "verify_child_fd5_read_only_before_checkpoint_read",
    "verify_child_fd5_identity_before_full_hash",
    "verify_child_fd5_full_hash_before_deserialization",
    "verify_child_fd5_identity_after_full_hash",
    "close_all_transport_descriptors_on_every_failure",
)


@dataclass(frozen=True, init=False)
class _SeparationLaunchPlanV2Record(Mapping[str, Any]):
    """Deeply immutable blocked evidence, never transport authority."""

    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


def _build_blocked_separation_launch_plan_v2_record(
    *,
    worker_request_v2: SeparationWorkerRequestV2Record,
) -> _SeparationLaunchPlanV2Record:
    """Build historical design evidence from one exact blocked V2 request.

    The caller is responsible for validating the exact live reservation and
    remeasuring its lease under the lease lock immediately before this call.
    Calling this pure helper directly does not confer or prove that authority.
    """

    request = _validate_separation_worker_request_v2_record_shape(
        worker_request_v2
    )
    request_bindings = _plain(request["bindings"])
    bindings = {
        **request_bindings,
        "worker_request_v2_sha256": request["request_sha256"],
        "worker_request_v2_bindings_sha256": _hash(request_bindings),
    }
    descriptor_design = _logical_descriptor_design(bindings)
    installation_design = _fd5_installation_design()
    request_blockers = _validated_reasons(
        request["decision"]["blockers"],
        "worker request V2 blockers",
    )
    if not _REQUEST_V2_REQUIRED_BLOCKERS.issubset(request_blockers):
        raise ValueError("worker request V2 omits required launch blockers")
    advisories = _validated_reasons(
        request["decision"]["advisories"],
        "worker request V2 advisories",
    )
    payload = {
        "schema": _SEPARATION_LAUNCH_PLAN_V2_SCHEMA,
        "policy_id": _SEPARATION_LAUNCH_PLAN_V2_POLICY_ID,
        "evidence_scope": "private_development",
        "publication_scope": "private_local_contract_evidence",
        "status": "blocked",
        "run_status": "not_run",
        "real_execution_supported": (
            _SEPARATION_LAUNCH_PLAN_V2_EXECUTION_SUPPORTED
        ),
        "execution_permitted": False,
        "worker_start_permitted": False,
        "descriptor_installation_permitted": False,
        "bindings": bindings,
        "binding_authority": {
            "lease_facade_cross_binding_requirements": list(
                _RESERVATION_CROSS_BOUND_BINDINGS
            ),
            "sealed_but_unproven": list(_SEALED_BUT_UNPROVEN_BINDINGS),
        },
        "construction_requirements": dict(_CONSTRUCTION_REQUIREMENTS),
        "logical_descriptor_design": descriptor_design,
        "checkpoint_fd5_installation_design": installation_design,
        "decision": {
            "status": "blocked",
            "run_status": "not_run",
            "blocker_sources": {
                "worker_request_v2": request_blockers,
                "launch_plan_v2": sorted(_LAUNCH_V2_BLOCKERS),
            },
            "blockers": sorted(
                {*request_blockers, *_LAUNCH_V2_BLOCKERS}
            ),
            "advisories": advisories,
        },
        "limitations": list(_LIMITATIONS),
        "capabilities": {
            key: False for key in sorted(_CAPABILITY_FIELDS)
        },
        "effects": {key: False for key in sorted(_EFFECT_FIELDS)},
    }
    _validate_path_free(payload, "blocked launch plan V2")
    return _new_record({**payload, "plan_sha256": _hash(payload)})


def _validate_blocked_separation_launch_plan_v2_record_shape(
    value: Any,
) -> _SeparationLaunchPlanV2Record:
    """Revalidate an exact issued record without claiming live authority."""

    if type(value) is not _SeparationLaunchPlanV2Record:
        raise ValueError(
            "blocked launch plan V2 must be an exact validated record"
        )
    checked = _new_record(value)
    if _canonical_json(_plain(value)) != _canonical_json(_plain(checked)):
        raise ValueError(
            "blocked launch plan V2 record changed after validation"
        )
    return value


def _separation_launch_plan_v2_sha256(
    document: Mapping[str, Any],
) -> str:
    """Hash canonical plan bytes excluding only the record self-hash."""

    value = _bounded_json_copy(document, "blocked launch plan V2")
    if not isinstance(value, dict):
        raise ValueError("blocked launch plan V2 must be an object")
    _validate_path_free(value, "blocked launch plan V2")
    value.pop("plan_sha256", None)
    return _hash(value)


def _new_record(
    document: Mapping[str, Any],
) -> _SeparationLaunchPlanV2Record:
    value = _object_with_fields(
        document,
        _TOP_LEVEL_FIELDS,
        "blocked launch plan V2",
    )
    _validate_path_free(value, "blocked launch plan V2")
    if (
        value["schema"] != _SEPARATION_LAUNCH_PLAN_V2_SCHEMA
        or value["policy_id"] != _SEPARATION_LAUNCH_PLAN_V2_POLICY_ID
    ):
        raise ValueError("unsupported blocked launch plan V2 policy")
    if (
        value["evidence_scope"] != "private_development"
        or value["publication_scope"]
        != "private_local_contract_evidence"
        or value["status"] != "blocked"
        or value["run_status"] != "not_run"
        or value["real_execution_supported"] is not False
        or value["execution_permitted"] is not False
        or value["worker_start_permitted"] is not False
        or value["descriptor_installation_permitted"] is not False
    ):
        raise ValueError(
            "blocked launch plan V2 must remain blocked and not run"
        )

    bindings = _validated_plan_bindings(value["bindings"])
    authority = _object_with_fields(
        value["binding_authority"],
        _BINDING_AUTHORITY_FIELDS,
        "blocked launch plan V2 binding authority",
    )
    if authority != {
        "lease_facade_cross_binding_requirements": list(
            _RESERVATION_CROSS_BOUND_BINDINGS
        ),
        "sealed_but_unproven": list(_SEALED_BUT_UNPROVEN_BINDINGS),
    }:
        raise ValueError(
            "blocked launch plan V2 binding authority is invalid"
        )
    if (
        _object_with_fields(
            value["construction_requirements"],
            _CONSTRUCTION_REQUIREMENT_FIELDS,
            "blocked launch plan V2 construction requirements",
        )
        != _CONSTRUCTION_REQUIREMENTS
    ):
        raise ValueError(
            "blocked launch plan V2 construction requirements are invalid"
        )
    if _object_with_fields(
        value["logical_descriptor_design"],
        _DESCRIPTOR_DESIGN_FIELDS,
        "blocked launch plan V2 descriptor design",
    ) != _logical_descriptor_design(bindings):
        raise ValueError(
            "blocked launch plan V2 descriptor design is invalid"
        )
    if _object_with_fields(
        value["checkpoint_fd5_installation_design"],
        _FD5_INSTALLATION_DESIGN_FIELDS,
        "blocked launch plan V2 FD5 installation design",
    ) != _fd5_installation_design():
        raise ValueError(
            "blocked launch plan V2 FD5 installation design is invalid"
        )

    decision = _object_with_fields(
        value["decision"],
        _DECISION_FIELDS,
        "blocked launch plan V2 decision",
    )
    sources = _object_with_fields(
        decision["blocker_sources"],
        _BLOCKER_SOURCE_FIELDS,
        "blocked launch plan V2 blocker sources",
    )
    request_blockers = _validated_reasons(
        sources["worker_request_v2"],
        "worker request V2 blockers",
    )
    launch_blockers = _validated_reasons(
        sources["launch_plan_v2"],
        "launch plan V2 blockers",
    )
    advisories = _validated_reasons(
        decision["advisories"],
        "launch plan V2 advisories",
    )
    if (
        decision["status"] != "blocked"
        or decision["run_status"] != "not_run"
        or not _REQUEST_V2_REQUIRED_BLOCKERS.issubset(request_blockers)
        or launch_blockers != sorted(_LAUNCH_V2_BLOCKERS)
        or decision["blockers"]
        != sorted({*request_blockers, *launch_blockers})
        or decision["advisories"] != advisories
    ):
        raise ValueError("blocked launch plan V2 decision is invalid")
    if value["limitations"] != list(_LIMITATIONS):
        raise ValueError(
            "blocked launch plan V2 limitations are invalid"
        )
    _all_false(
        value["capabilities"],
        _CAPABILITY_FIELDS,
        "blocked launch plan V2 capabilities",
    )
    _all_false(
        value["effects"],
        _EFFECT_FIELDS,
        "blocked launch plan V2 effects",
    )
    _sha(value["plan_sha256"], "blocked launch plan V2 plan_sha256")
    if value["plan_sha256"] != _separation_launch_plan_v2_sha256(value):
        raise ValueError("blocked launch plan V2 hash is invalid")
    if len(_canonical_json(value)) > _SEPARATION_LAUNCH_PLAN_V2_MAXIMUM_BYTES:
        raise ValueError("blocked launch plan V2 exceeds maximum bytes")

    record = object.__new__(_SeparationLaunchPlanV2Record)
    object.__setattr__(record, "_document", _freeze(value))
    return record


def _validated_plan_bindings(value: Any) -> dict[str, Any]:
    bindings = _object_with_fields(
        value,
        _BINDING_FIELDS,
        "blocked launch plan V2 bindings",
    )
    request_bindings = {
        key: bindings[key] for key in _REQUEST_BINDING_FIELDS
    }
    for key, item in request_bindings.items():
        if key == "checkpoint_bytes":
            if (
                type(item) is not int
                or not 0 < item <= _MAX_CHECKPOINT_BYTES
            ):
                raise ValueError(
                    "blocked launch plan V2 checkpoint bytes are invalid"
                )
        elif key == "pickle_evidence_sha256" and item is None:
            continue
        else:
            _sha(item, f"blocked launch plan V2 {key}")
    _sha(
        bindings["worker_request_v2_sha256"],
        "blocked launch plan V2 worker request sha256",
    )
    _sha(
        bindings["worker_request_v2_bindings_sha256"],
        "blocked launch plan V2 request bindings sha256",
    )
    if bindings["worker_request_v2_bindings_sha256"] != _hash(
        request_bindings
    ):
        raise ValueError(
            "blocked launch plan V2 request bindings hash is invalid"
        )
    return bindings


def _logical_descriptor_design(
    bindings: Mapping[str, Any],
) -> dict[str, Any]:
    request_sha256 = bindings["worker_request_v2_sha256"]
    result_identity = _hash(
        {
            "maximum_bytes": _WORKER_RESULT_MAXIMUM_BYTES,
            "purpose": "bounded_path_free_worker_result",
            "worker_request_v2_sha256": request_sha256,
        }
    )
    checkpoint_identity = _hash(
        {
            "checkpoint_bytes": bindings["checkpoint_bytes"],
            "checkpoint_file_identity_sha256": bindings[
                "checkpoint_file_identity_sha256"
            ],
            "checkpoint_sha256": bindings["checkpoint_sha256"],
        }
    )
    payload = {
        "policy_id": _LOGICAL_DESCRIPTOR_POLICY_ID,
        "inherit_unlisted_descriptors": False,
        "raw_descriptor_values_serialized": False,
        "logical_descriptors": [
            {
                "logical_descriptor": 3,
                "purpose": "sealed_path_free_worker_request",
                "direction": "parent_to_worker",
                "access": "read_only",
                "maximum_bytes": (
                    SEPARATION_WORKER_REQUEST_V2_MAXIMUM_BYTES
                ),
                "state": "transport_undefined_not_materialized",
                "identity_sha256": request_sha256,
            },
            {
                "logical_descriptor": 4,
                "purpose": "bounded_path_free_worker_result",
                "direction": "worker_to_parent",
                "access": "write_only",
                "maximum_bytes": _WORKER_RESULT_MAXIMUM_BYTES,
                "state": "transport_undefined_not_created",
                "identity_sha256": result_identity,
            },
            {
                "logical_descriptor": 5,
                "purpose": "read_only_checkpoint",
                "direction": "parent_to_worker",
                "access": "read_only",
                "expected_bytes": bindings["checkpoint_bytes"],
                "state": "reserved_not_installed",
                "identity_sha256": checkpoint_identity,
            },
        ],
    }
    return {**payload, "design_sha256": _hash(payload)}


def _fd5_installation_design() -> dict[str, Any]:
    payload = {
        "policy_id": _FD5_INSTALLATION_DESIGN_POLICY_ID,
        "status": "design_only_not_implemented",
        "run_status": "not_run",
        "target_logical_descriptor": 5,
        "parent_checkpoint_path_reopened": False,
        "parent_descriptor_table_mutated": False,
        "installation_implemented": False,
        "installation_attempted": False,
        "atomicity_boundary": "lease_lock_through_child_creation_result",
        "installation_mechanism": "single_child_creation_file_action",
        "required_sequence": list(_FD5_REQUIRED_SEQUENCE),
    }
    return {**payload, "design_sha256": _hash(payload)}


def _validated_reasons(value: Any, label: str) -> list[str]:
    if (
        not isinstance(value, (list, tuple))
        or isinstance(value, (str, bytes))
        or len(value) > _MAX_DECISION_REASONS
    ):
        raise ValueError(f"{label} are invalid")
    reasons = list(value)
    if (
        reasons != sorted(set(reasons))
        or any(
            not isinstance(item, str)
            or _REASON_RE.fullmatch(item) is None
            for item in reasons
        )
    ):
        raise ValueError(f"{label} must be sorted unique identifiers")
    _validate_path_free(reasons, label)
    return reasons


def _all_false(
    value: Any,
    fields: frozenset[str],
    label: str,
) -> None:
    document = _object_with_fields(value, fields, label)
    if any(item is not False for item in document.values()):
        raise ValueError(f"{label} must all be false")


__all__: list[str] = []
