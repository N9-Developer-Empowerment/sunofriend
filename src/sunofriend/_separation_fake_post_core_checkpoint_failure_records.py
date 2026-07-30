"""Pure evidence for checkpoint mutation after fake execution succeeds.

This boundary is intentionally narrower than the general fake-execution and
post-lease failure receipts.  It describes a fixed worker that completed and
was exactly reaped, followed by a parent post-core checkpoint remeasurement
that detected one of the explicitly admitted identity, byte-count or hash
changes.  The checkpoint lease must still have closed cleanly.

The receipt is historical and inert.  In particular, a post-reap mismatch
does not prove which checkpoint bytes the child executed or whether any bytes
were deserialized.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ._separation_checkpoint_canonical import (
    canonical_sha256 as _hash,
    deep_freeze as _freeze,
    plain as _plain,
)
from ._separation_checkpoint_lease_records import (
    _TerminalAnchor,
    _TerminalOutcome,
    validate_receipt_document as _validate_lease_receipt_document,
)
from ._separation_fake_execution_records import (
    _SeparationFakeLaunchPlanV3Record,
    _SeparationFakeWorkerResultV2Record,
    _validate_prepared_separation_fake_launch_plan_v3_record_shape,
    _validate_separation_fake_worker_result_v2_record_shape,
)
from ._separation_fake_launch_v2_records import (
    _SeparationFakeLaunchPlanV2Record,
    _validate_blocked_separation_fake_launch_plan_v2_record_shape,
)
from ._separation_fake_post_lease_failure_records import (
    _validate_success_native_execution_observation,
)
from ._separation_fake_transport_records import (
    _SeparationFakeLaunchPlanRecord,
    _SeparationFakeWorkerRequestRecord,
    _validate_fake_launch_plan_shape,
    _validate_fake_worker_request_shape,
)
from ._separation_native_session_darwin import (
    _VerifiedNativeLauncherExecutionObservation,
)
from ._separation_worker_request_v2_values import _validate_path_free
from .separation_checkpoint_descriptor_lease import (
    SeparationCheckpointDescriptorLeaseTerminalReceipt,
)
from .separation_checkpoint_inspection import MAX_CHECKPOINT_BYTES


__all__: tuple[str, ...] = ()

_SCHEMA = "sunofriend.separation-fake-post-core-checkpoint-failure.v1"
_POLICY_ID = "private-post-core-checkpoint-integrity-failure-v1"
_PRIMARY_SCOPE = "parent_post_core_checkpoint_integrity"
_PRIMARY_STAGE = "checkpoint_post_core_remeasurement"
_CLEANUP_STAGE = "private_root_descriptor_close"
_INTEGRITY_REASONS = frozenset(
    {
        "checkpoint_file_identity_changed",
        "checkpoint_file_identity_changed_during_remeasurement",
        "checkpoint_byte_count_changed",
        "checkpoint_hash_changed",
    }
)
_FIELDS = {
    "schema",
    "policy_id",
    "status",
    "evidence_scope",
    "run_nonce",
    "backend_scope",
    "bindings",
    "failure",
    "process",
    "checkpoint",
    "lease",
    "outputs",
    "permissions",
    "limitations",
    "receipt_sha256",
}
_BINDING_FIELDS = {
    "fake_worker_request_v1_sha256",
    "fake_launch_plan_v1_sha256",
    "blocked_fake_launch_plan_v2_sha256",
    "fake_launch_plan_v3_sha256",
    "fake_worker_result_v2_sha256",
    "native_execution_observation_sha256",
    "lease_terminal_receipt_sha256",
}
_CHECKPOINT = {
    "worker_result_reports_checkpoint_remeasured": True,
    "worker_result_reports_checkpoint_deserialized": False,
    "parent_post_core_remeasurement_attempted": True,
    "parent_post_core_integrity_matched": False,
    "exact_checkpoint_bytes_executed_proven": False,
    "deserialization_absence_at_exec_proven": False,
}
_OUTPUTS = {
    "worker_result_validated": True,
    "materialization_started": False,
    "quarantine_verification_present": False,
    "materialization_observation_present": False,
    "private_transport_files_may_remain": True,
    "publication_created": False,
}
_PERMISSIONS = {
    "serialized_receipt_is_authority": False,
    "publication_permitted": False,
    "selection_permitted": False,
    "acceptance_eligible": False,
    "promotion_eligible": False,
}
_LIMITATIONS = [
    "child_checkpoint_hash_is_worker_report",
    "parent_post_reap_mismatch_not_proof_of_bytes_executed_or_deserialized",
    "runtime_exec_and_worker_script_path_toctou_not_eliminated",
    "transient_changes_outside_observed_stat_hash_windows_not_excluded",
    "deterministic_fixture_only_no_source_audio_or_model",
    "private_transport_files_may_remain_after_failure",
    "no_public_cli_tui_selection_or_publication_route",
]


@dataclass(frozen=True, init=False)
class _SeparationFakeExecutionPostCoreCheckpointFailedReceipt(
    Mapping[str, Any]
):
    """Immutable, path-free post-core checkpoint-integrity evidence."""

    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


def _build_post_core_checkpoint_failed_terminal_receipt(
    *,
    fake_worker_request: _SeparationFakeWorkerRequestRecord,
    fake_launch_plan_v1: _SeparationFakeLaunchPlanRecord,
    blocked_fake_launch_plan_v2: _SeparationFakeLaunchPlanV2Record,
    fake_launch_plan_v3: _SeparationFakeLaunchPlanV3Record,
    fake_worker_result_v2: _SeparationFakeWorkerResultV2Record,
    native_execution_observation: (
        _VerifiedNativeLauncherExecutionObservation
    ),
    lease_terminal_receipt: (
        SeparationCheckpointDescriptorLeaseTerminalReceipt
    ),
    cleanup_stages: Sequence[str],
) -> _SeparationFakeExecutionPostCoreCheckpointFailedReceipt:
    """Seal one exact, inert post-core checkpoint-integrity failure."""

    checked_request = _validate_fake_worker_request_shape(
        fake_worker_request
    )
    checked_launch_v1 = _validate_fake_launch_plan_shape(
        fake_launch_plan_v1
    )
    checked_launch_v2 = (
        _validate_blocked_separation_fake_launch_plan_v2_record_shape(
            blocked_fake_launch_plan_v2,
            fake_worker_request=checked_request,
            fake_launch_plan_v1=checked_launch_v1,
        )
    )
    checked_launch_v3 = (
        _validate_prepared_separation_fake_launch_plan_v3_record_shape(
            fake_launch_plan_v3,
            fake_worker_request=checked_request,
            fake_launch_plan_v1=checked_launch_v1,
            blocked_fake_launch_plan_v2=checked_launch_v2,
        )
    )
    checked_result = _validate_separation_fake_worker_result_v2_record_shape(
        fake_worker_result_v2,
        fake_launch_plan_v3=checked_launch_v3,
    )
    native = _validate_success_native_execution_observation(
        native_execution_observation
    )
    lease = _validate_failed_lease_terminal_receipt(
        lease_terminal_receipt
    )
    if (
        native["fake_launch_plan_v3_sha256"]
        != checked_launch_v3["plan_sha256"]
        or native["fake_worker_result_v2_sha256"]
        != checked_result["result_sha256"]
    ):
        raise ValueError("post-core native success binding changed")
    request_bindings = checked_request["bindings"]
    lease_bindings = lease["bindings"]
    if any(
        request_bindings[request_key] != lease_bindings[lease_key]
        for request_key, lease_key in (
            ("worker_request_v1_sha256", "worker_request_sha256"),
            ("lease_observation_sha256", "lease_observation_sha256"),
            ("preflight_sha256", "preflight_sha256"),
            (
                "checkpoint_inspection_sha256",
                "trusted_checkpoint_inspection_sha256",
            ),
            ("checkpoint_sha256", "checkpoint_sha256"),
            ("checkpoint_bytes", "checkpoint_bytes"),
            (
                "checkpoint_file_identity_sha256",
                "checkpoint_file_identity_sha256",
            ),
        )
    ):
        raise ValueError("post-core checkpoint lease binding changed")
    integrity_reasons = list(lease["integrity"]["reasons"])
    cleanup = [
        {
            "ordinal": ordinal,
            "stage": stage,
            "reason_code": f"{stage}_failed",
        }
        for ordinal, stage in enumerate(cleanup_stages)
    ]
    payload = {
        "schema": _SCHEMA,
        "policy_id": _POLICY_ID,
        "status": (
            "failed_post_core_checkpoint_integrity_with_cleanup_failures"
            if cleanup
            else "failed_post_core_checkpoint_integrity"
        ),
        "evidence_scope": "private_deterministic_transport_execution",
        "run_nonce": checked_launch_v3["run_nonce"],
        "backend_scope": "deterministic_transport_fixture_only",
        "bindings": {
            "fake_worker_request_v1_sha256": (
                checked_request["request_sha256"]
            ),
            "fake_launch_plan_v1_sha256": (
                checked_launch_v1["plan_sha256"]
            ),
            "blocked_fake_launch_plan_v2_sha256": (
                checked_launch_v2["plan_sha256"]
            ),
            "fake_launch_plan_v3_sha256": (
                checked_launch_v3["plan_sha256"]
            ),
            "fake_worker_result_v2_sha256": (
                checked_result["result_sha256"]
            ),
            "native_execution_observation_sha256": (
                native["observation_sha256"]
            ),
            "lease_terminal_receipt_sha256": lease["receipt_sha256"],
        },
        "failure": {
            "primary": {
                "scope": _PRIMARY_SCOPE,
                "stage": _PRIMARY_STAGE,
                "reason_codes": integrity_reasons,
            },
            "cleanup": cleanup,
            "cleanup_count": len(cleanup),
            "exception_text_recorded": False,
        },
        "process": {
            "state": "started_exact_reaped_success",
            "wait": native["wait"],
            "timed_out": False,
            "term_sent": False,
            "kill_sent": False,
            "leader_reaped": True,
            "ownership_released": True,
            "ownership_lost": False,
            "worker_reported_identity_matched": True,
            "raw_pid_in_observation": False,
            "signal_authority_exposed": False,
        },
        "checkpoint": dict(_CHECKPOINT),
        "lease": {
            "terminal_receipt_present": True,
            "status": lease["status"],
            "integrity_status": lease["integrity"]["status"],
            "integrity_reasons": integrity_reasons,
            "cleanup_status": lease["cleanup"]["status"],
            "cleanup_reasons": list(lease["cleanup"]["reasons"]),
        },
        "outputs": dict(_OUTPUTS),
        "permissions": dict(_PERMISSIONS),
        "limitations": list(_LIMITATIONS),
    }
    return _validate_post_core_checkpoint_failed_terminal_receipt(
        _wrapper(
            _freeze(
                {
                    **payload,
                    "receipt_sha256": _hash(payload),
                }
            )
        )
    )


def _validate_post_core_checkpoint_failed_terminal_receipt(
    value: Any,
) -> _SeparationFakeExecutionPostCoreCheckpointFailedReceipt:
    """Validate one exact post-core checkpoint-integrity receipt."""

    if (
        type(value)
        is not _SeparationFakeExecutionPostCoreCheckpointFailedReceipt
    ):
        raise ValueError(
            "post-core checkpoint failure receipt type is invalid"
        )
    document = _plain(value)
    if not isinstance(document, dict) or set(document) != _FIELDS:
        raise ValueError(
            "post-core checkpoint failure receipt fields are invalid"
        )
    _validate_path_free(document, "post-core checkpoint failure receipt")
    if (
        document["schema"] != _SCHEMA
        or document["policy_id"] != _POLICY_ID
        or document["status"]
        not in {
            "failed_post_core_checkpoint_integrity",
            (
                "failed_post_core_checkpoint_integrity_with_cleanup_"
                "failures"
            ),
        }
        or document["evidence_scope"]
        != "private_deterministic_transport_execution"
        or document["backend_scope"]
        != "deterministic_transport_fixture_only"
        or not _valid_sha256(document["run_nonce"])
    ):
        raise ValueError(
            "post-core checkpoint failure receipt policy is invalid"
        )
    bindings = document["bindings"]
    if (
        not isinstance(bindings, dict)
        or set(bindings) != _BINDING_FIELDS
        or any(not _valid_sha256(item) for item in bindings.values())
    ):
        raise ValueError(
            "post-core checkpoint failure bindings are invalid"
        )
    failure = document["failure"]
    if not isinstance(failure, dict) or set(failure) != {
        "primary",
        "cleanup",
        "cleanup_count",
        "exception_text_recorded",
    }:
        raise ValueError(
            "post-core checkpoint failure evidence is invalid"
        )
    primary = failure["primary"]
    if (
        not isinstance(primary, dict)
        or set(primary) != {"scope", "stage", "reason_codes"}
        or primary["scope"] != _PRIMARY_SCOPE
        or primary["stage"] != _PRIMARY_STAGE
        or not _valid_integrity_reasons(primary["reason_codes"])
        or failure["exception_text_recorded"] is not False
    ):
        raise ValueError(
            "post-core checkpoint primary evidence is invalid"
        )
    cleanup = failure["cleanup"]
    if (
        not isinstance(cleanup, list)
        or len(cleanup) > 1
        or type(failure["cleanup_count"]) is not int
        or failure["cleanup_count"] != len(cleanup)
    ):
        raise ValueError(
            "post-core checkpoint cleanup evidence is invalid"
        )
    for ordinal, event in enumerate(cleanup):
        if (
            not isinstance(event, dict)
            or set(event) != {"ordinal", "stage", "reason_code"}
            or type(event["ordinal"]) is not int
            or event["ordinal"] != ordinal
            or event["stage"] != _CLEANUP_STAGE
            or event["reason_code"] != f"{_CLEANUP_STAGE}_failed"
        ):
            raise ValueError(
                "post-core checkpoint cleanup evidence is invalid"
            )
    expected_status = (
        "failed_post_core_checkpoint_integrity_with_cleanup_failures"
        if cleanup
        else "failed_post_core_checkpoint_integrity"
    )
    if document["status"] != expected_status:
        raise ValueError(
            "post-core checkpoint failure status is inconsistent"
        )
    if not _valid_process(document["process"]):
        raise ValueError(
            "post-core checkpoint process evidence is invalid"
        )
    if document["checkpoint"] != _CHECKPOINT:
        raise ValueError(
            "post-core checkpoint proof evidence is invalid"
        )
    lease = document["lease"]
    if (
        not isinstance(lease, dict)
        or set(lease)
        != {
            "terminal_receipt_present",
            "status",
            "integrity_status",
            "integrity_reasons",
            "cleanup_status",
            "cleanup_reasons",
        }
        or lease["terminal_receipt_present"] is not True
        or lease["status"] != "integrity_failed"
        or lease["integrity_status"] != "failed"
        or not _valid_integrity_reasons(lease["integrity_reasons"])
        or lease["integrity_reasons"] != primary["reason_codes"]
        or lease["cleanup_status"] != "complete"
        or lease["cleanup_reasons"] != []
    ):
        raise ValueError(
            "post-core checkpoint lease evidence is invalid"
        )
    if document["outputs"] != _OUTPUTS:
        raise ValueError(
            "post-core checkpoint output evidence is invalid"
        )
    if document["permissions"] != _PERMISSIONS:
        raise ValueError(
            "post-core checkpoint permissions are invalid"
        )
    if document["limitations"] != _LIMITATIONS:
        raise ValueError(
            "post-core checkpoint limitations are invalid"
        )
    receipt_sha256 = document["receipt_sha256"]
    payload = dict(document)
    payload.pop("receipt_sha256")
    if (
        not _valid_sha256(receipt_sha256)
        or receipt_sha256 != _hash(payload)
    ):
        raise ValueError(
            "post-core checkpoint failure self-hash is invalid"
        )
    return value


def _validate_failed_lease_terminal_receipt(
    value: Any,
) -> dict[str, Any]:
    if type(value) is not SeparationCheckpointDescriptorLeaseTerminalReceipt:
        raise ValueError(
            "post-core checkpoint failure requires an exact lease receipt"
        )
    document = _plain(value)
    try:
        anchor = _TerminalAnchor(
            bindings=_freeze(_plain(document["bindings"]))
        )
        outcome = _TerminalOutcome(
            status=document["status"],
            integrity_status=document["integrity"]["status"],
            integrity_reasons=tuple(document["integrity"]["reasons"]),
            cleanup_status=document["cleanup"]["status"],
            cleanup_reasons=tuple(document["cleanup"]["reasons"]),
        )
        _validate_lease_receipt_document(
            document,
            anchor=anchor,
            outcome=outcome,
            maximum_checkpoint_bytes=MAX_CHECKPOINT_BYTES,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "post-core checkpoint lease receipt is invalid"
        ) from exc
    if (
        outcome.status != "integrity_failed"
        or outcome.integrity_status != "failed"
        or not _valid_integrity_reasons(
            list(outcome.integrity_reasons)
        )
        or outcome.cleanup_status != "complete"
        or outcome.cleanup_reasons
    ):
        raise ValueError(
            "post-core checkpoint lease receipt is not a narrow "
            "integrity failure with complete cleanup"
        )
    return document


def _valid_integrity_reasons(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 1
        and value[0] in _INTEGRITY_REASONS
    )


def _valid_process(value: Any) -> bool:
    return value == {
        "state": "started_exact_reaped_success",
        "wait": {
            "kind": "exited",
            "exit_code": 0,
            "signal": None,
            "core_dumped": False,
        },
        "timed_out": False,
        "term_sent": False,
        "kill_sent": False,
        "leader_reaped": True,
        "ownership_released": True,
        "ownership_lost": False,
        "worker_reported_identity_matched": True,
        "raw_pid_in_observation": False,
        "signal_authority_exposed": False,
    }


def _valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _wrapper(
    document: Mapping[str, Any],
) -> _SeparationFakeExecutionPostCoreCheckpointFailedReceipt:
    value = object.__new__(
        _SeparationFakeExecutionPostCoreCheckpointFailedReceipt
    )
    object.__setattr__(value, "_document", _freeze(_plain(document)))
    return value
