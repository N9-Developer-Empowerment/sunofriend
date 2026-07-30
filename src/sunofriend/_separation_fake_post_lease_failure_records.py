"""Pure failure evidence after successful fake execution and lease closure.

This boundary is intentionally separate from native exact-reap and no-start
failure records.  It describes a run whose fixed worker completed, whose
Result V2 was validated and whose checkpoint lease closed, but whose
parent-side materialization, verification, receipt sealing or final private
root cleanup failed.  The record is inert and grants no publication,
selection, acceptance or promotion authority.
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

_SCHEMA = "sunofriend.separation-fake-post-lease-failure.v1"
_POLICY_ID = "private-post-lease-fake-failure-v1"
_NATIVE_SCHEMA = "sunofriend.separation-native-launcher-execution.v1"
_SHA256 = frozenset("0123456789abcdef")
_PRIMARY_STAGES = frozenset(
    {
        "result_revalidation",
        "private_root_revalidation",
        "quarantine_directory_materialization",
        "quarantine_output_materialization",
        "quarantine_verification",
        "materialization_observation_seal",
        "materialization_descriptor_cleanup",
        "whole_run_receipt_seal",
        "private_root_descriptor_close",
    }
)
_CLEANUP_STAGES = frozenset(
    {
        "quarantine_output_write_descriptor_close",
        "quarantine_output_read_descriptor_close",
        "quarantine_directory_descriptor_close",
        "private_root_descriptor_close",
    }
)
_ALLOWED_CLEANUP_BY_PRIMARY = {
    "result_revalidation": frozenset({"private_root_descriptor_close"}),
    "private_root_revalidation": frozenset(
        {"private_root_descriptor_close"}
    ),
    "quarantine_directory_materialization": frozenset(
        {
            "quarantine_directory_descriptor_close",
            "private_root_descriptor_close",
        }
    ),
    "quarantine_output_materialization": _CLEANUP_STAGES,
    "quarantine_verification": (
        _CLEANUP_STAGES
        - {"quarantine_output_write_descriptor_close"}
    ),
    "materialization_observation_seal": (
        _CLEANUP_STAGES
        - {"quarantine_output_write_descriptor_close"}
    ),
    "materialization_descriptor_cleanup": (
        _CLEANUP_STAGES
        - {"quarantine_output_write_descriptor_close"}
    ),
    "whole_run_receipt_seal": frozenset(
        {"private_root_descriptor_close"}
    ),
    "private_root_descriptor_close": frozenset(),
}
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
    "quarantine_verification_sha256",
    "materialization_observation_sha256",
}
_NATIVE_FIELDS = {
    "schema",
    "status",
    "native_session_observation_sha256",
    "fake_launch_plan_v3_sha256",
    "fake_worker_result_v2_sha256",
    "wait",
    "timed_out",
    "term_sent",
    "kill_sent",
    "leader_reaped",
    "ownership_released",
    "ownership_lost",
    "worker_reported_identity_matched",
    "native_artifact_remeasured_after_reap",
    "runtime_remeasured_after_reap",
    "fake_worker_remeasured_after_reap",
    "raw_pid_in_execution_observation",
    "private_result_frame_contains_worker_pid",
    "signal_authority_exposed",
    "limitations",
    "observation_sha256",
}
_NATIVE_LIMITATIONS = [
    "runtime_exec_and_worker_script_path_toctou_not_eliminated",
    "destructor_backstop_is_not_terminal_evidence",
    "outer_one_shot_supervisor_required_for_strict_hard_timeout",
    "deterministic_fixture_only_no_source_audio_or_model",
]
_LIMITATIONS = [
    "successful_fixed_worker_and_closed_checkpoint_lease_only",
    "parent_side_post_lease_failure_only",
    "runtime_exec_and_worker_script_path_toctou_not_eliminated",
    "cleanup_events_are_code_owned_stages_not_exception_text",
    "private_transport_or_quarantine_files_may_remain_after_failure",
    "no_public_cli_tui_selection_or_publication_route",
]


@dataclass(frozen=True, init=False)
class _SeparationFakeExecutionPostLeaseFailedReceipt(Mapping[str, Any]):
    """Immutable, path-free evidence for one parent-side failed run."""

    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


def _build_post_lease_failed_terminal_receipt(
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
    primary_stage: str,
    materialization_started: bool,
    quarantine_verification_sha256: str | None,
    materialization_observation_sha256: str | None,
    cleanup_stages: Sequence[str],
) -> _SeparationFakeExecutionPostLeaseFailedReceipt:
    """Seal inert failure evidence from one validated post-lease anchor."""

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
    lease = _validate_closed_lease_terminal_receipt(
        lease_terminal_receipt
    )
    if (
        native["fake_launch_plan_v3_sha256"]
        != checked_launch_v3["plan_sha256"]
        or native["fake_worker_result_v2_sha256"]
        != checked_result["result_sha256"]
    ):
        raise ValueError("post-lease native success binding changed")
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
        raise ValueError("post-lease checkpoint lease binding changed")
    bindings = {
        "fake_worker_request_v1_sha256": (
            checked_request["request_sha256"]
        ),
        "fake_launch_plan_v1_sha256": checked_launch_v1["plan_sha256"],
        "blocked_fake_launch_plan_v2_sha256": (
            checked_launch_v2["plan_sha256"]
        ),
        "fake_launch_plan_v3_sha256": checked_launch_v3["plan_sha256"],
        "fake_worker_result_v2_sha256": checked_result["result_sha256"],
        "native_execution_observation_sha256": native[
            "observation_sha256"
        ],
        "lease_terminal_receipt_sha256": lease["receipt_sha256"],
        "quarantine_verification_sha256": (
            quarantine_verification_sha256
        ),
        "materialization_observation_sha256": (
            materialization_observation_sha256
        ),
    }
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
            "failed_post_lease_with_cleanup_failures"
            if cleanup
            else "failed_post_lease"
        ),
        "evidence_scope": "private_deterministic_transport_execution",
        "run_nonce": checked_launch_v3["run_nonce"],
        "backend_scope": "deterministic_transport_fixture_only",
        "bindings": bindings,
        "failure": {
            "primary": {
                "scope": "parent_post_lease",
                "stage": primary_stage,
                "reason_code": f"parent_{primary_stage}_failed",
            },
            "cleanup": cleanup,
            "cleanup_count": len(cleanup),
            "exception_text_recorded": False,
        },
        "process": {
            "state": "started_exact_reaped_success",
            "wait": native["wait"],
            "timed_out": False,
            "leader_reaped": True,
            "ownership_released": True,
            "ownership_lost": False,
            "worker_reported_identity_matched": True,
            "raw_pid_in_observation": False,
            "signal_authority_exposed": False,
        },
        "lease": {
            "terminal_receipt_present": True,
            "status": "closed",
            "integrity_status": "verified_before_close_attempt",
            "cleanup_status": "complete",
        },
        "outputs": {
            "worker_result_validated": True,
            "materialization_started": materialization_started,
            "quarantine_verification_present": (
                quarantine_verification_sha256 is not None
            ),
            "materialization_observation_present": (
                materialization_observation_sha256 is not None
            ),
            "private_transport_or_quarantine_files_may_remain": True,
            "publication_created": False,
        },
        "permissions": {
            "serialized_receipt_is_authority": False,
            "publication_permitted": False,
            "selection_permitted": False,
            "acceptance_eligible": False,
            "promotion_eligible": False,
        },
        "limitations": list(_LIMITATIONS),
    }
    return _validate_post_lease_failed_terminal_receipt(
        _wrapper(
            _freeze(
                {
                    **payload,
                    "receipt_sha256": _hash(payload),
                }
            )
        )
    )


def _validate_post_lease_failed_terminal_receipt(
    value: Any,
) -> _SeparationFakeExecutionPostLeaseFailedReceipt:
    """Validate one exact inert post-lease failure receipt."""

    if type(value) is not _SeparationFakeExecutionPostLeaseFailedReceipt:
        raise ValueError("post-lease failure receipt type is invalid")
    document = _plain(value)
    if not isinstance(document, dict) or set(document) != _FIELDS:
        raise ValueError("post-lease failure receipt fields are invalid")
    _validate_path_free(document, "post-lease failure receipt")
    if (
        document["schema"] != _SCHEMA
        or document["policy_id"] != _POLICY_ID
        or document["status"]
        not in {
            "failed_post_lease",
            "failed_post_lease_with_cleanup_failures",
        }
        or document["evidence_scope"]
        != "private_deterministic_transport_execution"
        or document["backend_scope"]
        != "deterministic_transport_fixture_only"
        or not _valid_sha256(document["run_nonce"])
    ):
        raise ValueError("post-lease failure receipt policy is invalid")
    bindings = document["bindings"]
    if (
        not isinstance(bindings, dict)
        or set(bindings) != _BINDING_FIELDS
        or any(
            key
            not in {
                "quarantine_verification_sha256",
                "materialization_observation_sha256",
            }
            and not _valid_sha256(item)
            for key, item in bindings.items()
        )
        or any(
            bindings[key] is not None
            and not _valid_sha256(bindings[key])
            for key in (
                "quarantine_verification_sha256",
                "materialization_observation_sha256",
            )
        )
    ):
        raise ValueError("post-lease failure bindings are invalid")
    failure = document["failure"]
    if not isinstance(failure, dict) or set(failure) != {
        "primary",
        "cleanup",
        "cleanup_count",
        "exception_text_recorded",
    }:
        raise ValueError("post-lease failure evidence is invalid")
    primary = failure["primary"]
    if (
        not isinstance(primary, dict)
        or set(primary) != {"scope", "stage", "reason_code"}
        or primary["scope"] != "parent_post_lease"
        or type(primary["stage"]) is not str
        or primary["stage"] not in _PRIMARY_STAGES
        or primary["reason_code"]
        != f"parent_{primary['stage']}_failed"
        or failure["exception_text_recorded"] is not False
    ):
        raise ValueError("post-lease primary evidence is invalid")
    cleanup = failure["cleanup"]
    allowed_cleanup = _ALLOWED_CLEANUP_BY_PRIMARY[primary["stage"]]
    if (
        not isinstance(cleanup, list)
        or len(cleanup) > 128
        or type(failure["cleanup_count"]) is not int
        or failure["cleanup_count"] != len(cleanup)
    ):
        raise ValueError("post-lease cleanup evidence is invalid")
    for ordinal, event in enumerate(cleanup):
        if (
            not isinstance(event, dict)
            or set(event) != {"ordinal", "stage", "reason_code"}
            or type(event["ordinal"]) is not int
            or event["ordinal"] != ordinal
            or type(event["stage"]) is not str
            or event["stage"] not in allowed_cleanup
            or event["reason_code"] != f"{event['stage']}_failed"
        ):
            raise ValueError("post-lease cleanup evidence is invalid")
    expected_status = (
        "failed_post_lease_with_cleanup_failures"
        if cleanup
        else "failed_post_lease"
    )
    if document["status"] != expected_status:
        raise ValueError("post-lease failure status is inconsistent")
    if not _valid_process(document["process"]):
        raise ValueError("post-lease process evidence is invalid")
    if document["lease"] != {
        "terminal_receipt_present": True,
        "status": "closed",
        "integrity_status": "verified_before_close_attempt",
        "cleanup_status": "complete",
    }:
        raise ValueError("post-lease lease evidence is invalid")
    outputs = document["outputs"]
    if (
        not isinstance(outputs, dict)
        or set(outputs)
        != {
            "worker_result_validated",
            "materialization_started",
            "quarantine_verification_present",
            "materialization_observation_present",
            "private_transport_or_quarantine_files_may_remain",
            "publication_created",
        }
        or outputs["worker_result_validated"] is not True
        or type(outputs["materialization_started"]) is not bool
        or outputs["quarantine_verification_present"]
        is not (
            bindings["quarantine_verification_sha256"] is not None
        )
        or outputs["materialization_observation_present"]
        is not (
            bindings["materialization_observation_sha256"] is not None
        )
        or outputs[
            "private_transport_or_quarantine_files_may_remain"
        ]
        is not True
        or outputs["publication_created"] is not False
    ):
        raise ValueError("post-lease output evidence is invalid")
    _validate_progress(
        primary["stage"],
        materialization_started=outputs["materialization_started"],
        quarantine_present=outputs["quarantine_verification_present"],
        materialization_present=outputs[
            "materialization_observation_present"
        ],
    )
    if document["permissions"] != {
        "serialized_receipt_is_authority": False,
        "publication_permitted": False,
        "selection_permitted": False,
        "acceptance_eligible": False,
        "promotion_eligible": False,
    }:
        raise ValueError("post-lease failure permissions are invalid")
    if document["limitations"] != _LIMITATIONS:
        raise ValueError("post-lease failure limitations are invalid")
    receipt_sha256 = document["receipt_sha256"]
    payload = dict(document)
    payload.pop("receipt_sha256")
    if not _valid_sha256(receipt_sha256) or receipt_sha256 != _hash(payload):
        raise ValueError("post-lease failure self-hash is invalid")
    return value


def _validate_closed_lease_terminal_receipt(
    value: Any,
) -> dict[str, Any]:
    if type(value) is not SeparationCheckpointDescriptorLeaseTerminalReceipt:
        raise ValueError(
            "post-lease failure requires an exact checkpoint lease receipt"
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
            "post-lease checkpoint lease receipt is invalid"
        ) from exc
    if (
        outcome.status != "closed"
        or outcome.integrity_status
        != "verified_before_close_attempt"
        or outcome.integrity_reasons
        or outcome.cleanup_status != "complete"
        or outcome.cleanup_reasons
    ):
        raise ValueError(
            "post-lease checkpoint lease receipt is not healthy and closed"
        )
    return document


def _validate_success_native_execution_observation(
    value: Any,
) -> dict[str, Any]:
    if type(value) is not _VerifiedNativeLauncherExecutionObservation:
        raise ValueError(
            "post-lease failure requires an exact native success observation"
        )
    document = _plain(value)
    if not isinstance(document, dict) or set(document) != _NATIVE_FIELDS:
        raise ValueError("native success observation fields are invalid")
    _validate_path_free(document, "native success observation")
    if (
        document["schema"] != _NATIVE_SCHEMA
        or document["status"] != "verified_after_exact_reap"
        or any(
            not _valid_sha256(document[key])
            for key in (
                "native_session_observation_sha256",
                "fake_launch_plan_v3_sha256",
                "fake_worker_result_v2_sha256",
                "observation_sha256",
            )
        )
        or document["wait"]
        != {
            "kind": "exited",
            "exit_code": 0,
            "signal": None,
            "core_dumped": False,
        }
        or document["timed_out"] is not False
        or document["term_sent"] is not False
        or document["kill_sent"] is not False
        or any(
            document[key] is not True
            for key in (
                "leader_reaped",
                "ownership_released",
                "worker_reported_identity_matched",
                "native_artifact_remeasured_after_reap",
                "runtime_remeasured_after_reap",
                "fake_worker_remeasured_after_reap",
                "private_result_frame_contains_worker_pid",
            )
        )
        or any(
            document[key] is not False
            for key in (
                "ownership_lost",
                "raw_pid_in_execution_observation",
                "signal_authority_exposed",
            )
        )
        or document["limitations"] != _NATIVE_LIMITATIONS
    ):
        raise ValueError("native success observation policy is invalid")
    observation_sha256 = document["observation_sha256"]
    payload = dict(document)
    payload.pop("observation_sha256")
    if observation_sha256 != _hash(payload):
        raise ValueError("native success observation self-hash is invalid")
    return document


def _validate_progress(
    stage: str,
    *,
    materialization_started: bool,
    quarantine_present: bool,
    materialization_present: bool,
) -> None:
    if stage in {"result_revalidation", "private_root_revalidation"}:
        expected = (False, False, False)
    elif stage in {
        "quarantine_directory_materialization",
        "quarantine_output_materialization",
        "quarantine_verification",
    }:
        expected = (True, False, False)
    elif stage == "materialization_observation_seal":
        expected = (True, True, False)
    elif stage in {
        "materialization_descriptor_cleanup",
        "whole_run_receipt_seal",
        "private_root_descriptor_close",
    }:
        expected = (True, True, True)
    else:
        raise ValueError("post-lease primary stage is invalid")
    if (
        materialization_started,
        quarantine_present,
        materialization_present,
    ) != expected:
        raise ValueError("post-lease progress is inconsistent")


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
        and all(character in _SHA256 for character in value)
    )


def _wrapper(
    document: Mapping[str, Any],
) -> _SeparationFakeExecutionPostLeaseFailedReceipt:
    value = object.__new__(_SeparationFakeExecutionPostLeaseFailedReceipt)
    object.__setattr__(value, "_document", _freeze(_plain(document)))
    return value
