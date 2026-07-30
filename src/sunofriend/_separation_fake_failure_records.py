"""Pure whole-run failure records for the private fake separator.

Only exact-reap native failure evidence and an already-issued checkpoint lease
terminal receipt may reach this boundary.  The records are descriptive and
grant no execution, publication, selection, acceptance or promotion authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ._separation_checkpoint_canonical import (
    canonical_sha256 as _hash,
    deep_freeze as _freeze,
    plain as _plain,
)
from ._separation_native_failure_records import (
    _VerifiedNativeLauncherFailedTerminalObservation,
    _validate_exact_reap_failure_observation,
)
from ._separation_worker_request_v2_values import _validate_path_free


__all__: tuple[str, ...] = ()

_SCHEMA = "sunofriend.separation-fake-execution-failed-terminal.v1"
_POLICY_ID = "private-lease-bound-fake-failure-v1"
_SHA256 = frozenset("0123456789abcdef")
_PRIMARY_STAGES = frozenset(
    {
        "owner_terminality",
        "post_reap_remeasurement",
        "result_decode",
        "result_writer_close",
        "worker_exit",
        "worker_identity",
    }
)
_CLEANUP_STAGES = frozenset(
    {
        "checkpoint_lease_cleanup",
        "checkpoint_lease_close",
        "checkpoint_lease_forced_terminalization",
        "checkpoint_lease_terminal_status",
        "admission_finish",
        "fd5_reservation_release",
        "lease_bridge_finish",
        "native_cached_wait_read",
        "native_final_supervision",
        "native_post_reap_remeasurement",
        "native_result_writer_close",
        "private_root_descriptor_close",
        "request_descriptor_close",
        "result_read_descriptor_close",
        "result_write_descriptor_close",
        "transport_descriptor_close",
    }
)
_LEASE_STATUSES = frozenset(
    {
        "closed",
        "cleanup_failed",
        "integrity_failed",
        "integrity_and_cleanup_failed",
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
    "lease",
    "outputs",
    "permissions",
    "limitations",
    "receipt_sha256",
}


@dataclass(frozen=True, init=False)
class _SeparationFakeExecutionFailedTerminalReceipt(Mapping[str, Any]):
    """Immutable path-free whole-run failure evidence."""

    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


def _build_exact_reap_failed_terminal_receipt(
    *,
    run_nonce: str,
    fake_worker_request_v1_sha256: str,
    fake_launch_plan_v1_sha256: str,
    blocked_fake_launch_plan_v2_sha256: str,
    fake_launch_plan_v3_sha256: str,
    native_failure_observation: (
        _VerifiedNativeLauncherFailedTerminalObservation
    ),
    lease_terminal_receipt_sha256: str,
    lease_status: str,
    lease_integrity_status: str,
    lease_cleanup_status: str,
    cleanup_stages: Sequence[str],
) -> _SeparationFakeExecutionFailedTerminalReceipt:
    """Seal one failed run with exact reap and terminal lease evidence."""

    native = _validate_exact_reap_failure_observation(
        native_failure_observation
    )
    native_document = _plain(native)
    if (
        native_document["bindings"]["fake_launch_plan_v3_sha256"]
        != fake_launch_plan_v3_sha256
    ):
        raise ValueError("native failure plan binding changed")
    result = native_document["result"]
    cleanup = [
        {
            "ordinal": ordinal,
            "stage": stage,
            "reason_code": f"{stage}_failed",
        }
        for ordinal, stage in enumerate(cleanup_stages)
    ]
    cleanup_failures_present = (
        bool(cleanup)
        or lease_status != "closed"
        or lease_cleanup_status != "complete"
    )
    payload = {
        "schema": _SCHEMA,
        "policy_id": _POLICY_ID,
        "status": (
            "failed_terminal_with_cleanup_failures"
            if cleanup_failures_present
            else "failed_terminal"
        ),
        "evidence_scope": "private_deterministic_transport_execution",
        "run_nonce": run_nonce,
        "backend_scope": "deterministic_transport_fixture_only",
        "bindings": {
            "fake_worker_request_v1_sha256": (fake_worker_request_v1_sha256),
            "fake_launch_plan_v1_sha256": fake_launch_plan_v1_sha256,
            "blocked_fake_launch_plan_v2_sha256": (
                blocked_fake_launch_plan_v2_sha256
            ),
            "fake_launch_plan_v3_sha256": fake_launch_plan_v3_sha256,
            "native_failure_observation_sha256": native_document[
                "observation_sha256"
            ],
            "lease_terminal_receipt_sha256": (lease_terminal_receipt_sha256),
            "fake_worker_result_v2_sha256": result[
                "fake_worker_result_v2_sha256"
            ],
        },
        "failure": {
            "primary": {
                "scope": "native_execution",
                "stage": native_document["failure_stage"],
                "reason_code": (
                    f"native_{native_document['failure_stage']}_failed"
                ),
            },
            "cleanup": cleanup,
            "cleanup_count": len(cleanup),
            "exception_text_recorded": False,
        },
        "process": native_document["process"],
        "lease": {
            "terminal_receipt_present": True,
            "status": lease_status,
            "integrity_status": lease_integrity_status,
            "cleanup_status": lease_cleanup_status,
        },
        "outputs": {
            "worker_result_validated": result["validated"],
            "materialization_started": False,
            "quarantine_verification_present": False,
            "private_transport_files_may_remain": True,
            "publication_created": False,
        },
        "permissions": {
            "serialized_receipt_is_authority": False,
            "publication_permitted": False,
            "selection_permitted": False,
            "acceptance_eligible": False,
            "promotion_eligible": False,
        },
        "limitations": [
            "exact_reap_native_failures_only",
            "spawn_failure_and_unproven_reap_have_no_terminal_receipt",
            "runtime_exec_and_worker_script_path_toctou_not_eliminated",
            "cleanup_events_are_code_owned_stages_not_exception_text",
            "private_transport_files_may_remain_after_failure",
            "no_public_cli_tui_selection_or_publication_route",
        ],
    }
    return _validate_failed_terminal_receipt(
        _wrapper(
            _freeze(
                {
                    **payload,
                    "receipt_sha256": _hash(payload),
                }
            )
        )
    )


def _validate_failed_terminal_receipt(
    value: Any,
) -> _SeparationFakeExecutionFailedTerminalReceipt:
    """Validate one path-free failed terminal receipt."""

    if type(value) is not _SeparationFakeExecutionFailedTerminalReceipt:
        raise ValueError("fake failed terminal receipt type is invalid")
    document = _plain(value)
    if set(document) != _FIELDS:
        raise ValueError("fake failed terminal receipt fields are invalid")
    _validate_path_free(document, "fake failed terminal receipt")
    if (
        document["schema"] != _SCHEMA
        or document["policy_id"] != _POLICY_ID
        or document["status"]
        not in {
            "failed_terminal",
            "failed_terminal_with_cleanup_failures",
        }
        or document["evidence_scope"]
        != "private_deterministic_transport_execution"
        or document["backend_scope"] != "deterministic_transport_fixture_only"
        or not _valid_sha256(document["run_nonce"])
    ):
        raise ValueError("fake failed terminal policy is invalid")
    bindings = document["bindings"]
    expected_binding_keys = {
        "fake_worker_request_v1_sha256",
        "fake_launch_plan_v1_sha256",
        "blocked_fake_launch_plan_v2_sha256",
        "fake_launch_plan_v3_sha256",
        "native_failure_observation_sha256",
        "lease_terminal_receipt_sha256",
        "fake_worker_result_v2_sha256",
    }
    if (
        not isinstance(bindings, dict)
        or set(bindings) != expected_binding_keys
        or any(
            key != "fake_worker_result_v2_sha256" and not _valid_sha256(item)
            for key, item in bindings.items()
        )
        or (
            bindings["fake_worker_result_v2_sha256"] is not None
            and not _valid_sha256(bindings["fake_worker_result_v2_sha256"])
        )
    ):
        raise ValueError("fake failed terminal bindings are invalid")
    failure = document["failure"]
    if not isinstance(failure, dict) or set(failure) != {
        "primary",
        "cleanup",
        "cleanup_count",
        "exception_text_recorded",
    }:
        raise ValueError("fake failed terminal failure evidence is invalid")
    primary = failure["primary"]
    if (
        not isinstance(primary, dict)
        or set(primary) != {"scope", "stage", "reason_code"}
        or primary["scope"] != "native_execution"
        or not isinstance(primary["stage"], str)
        or primary["stage"] not in _PRIMARY_STAGES
        or primary["reason_code"] != f"native_{primary['stage']}_failed"
        or failure["exception_text_recorded"] is not False
    ):
        raise ValueError("fake failed terminal primary evidence is invalid")
    cleanup = failure["cleanup"]
    if (
        not isinstance(cleanup, list)
        or len(cleanup) > 32
        or type(failure["cleanup_count"]) is not int
        or failure["cleanup_count"] != len(cleanup)
    ):
        raise ValueError("fake failed terminal cleanup evidence is invalid")
    for ordinal, event in enumerate(cleanup):
        if (
            not isinstance(event, dict)
            or set(event) != {"ordinal", "stage", "reason_code"}
            or type(event["ordinal"]) is not int
            or event["ordinal"] != ordinal
            or not isinstance(event["stage"], str)
            or event["stage"] not in _CLEANUP_STAGES
            or event["reason_code"] != f"{event['stage']}_failed"
        ):
            raise ValueError(
                "fake failed terminal cleanup evidence is invalid"
            )
    process = document["process"]
    if not _valid_exact_reap_process(process):
        raise ValueError("fake failed terminal process evidence is invalid")
    lease = document["lease"]
    if (
        not isinstance(lease, dict)
        or set(lease)
        != {
            "terminal_receipt_present",
            "status",
            "integrity_status",
            "cleanup_status",
        }
        or lease["terminal_receipt_present"] is not True
        or lease["status"] not in _LEASE_STATUSES
        or not isinstance(lease["integrity_status"], str)
        or lease["cleanup_status"]
        not in {"complete", "close_not_attempted", "close_unconfirmed"}
    ):
        raise ValueError("fake failed terminal lease evidence is invalid")
    verified_lease = lease[
        "integrity_status"
    ] == "verified_before_close_attempt" and lease["status"] == (
        "closed" if lease["cleanup_status"] == "complete" else "cleanup_failed"
    )
    failed_lease = lease["integrity_status"] == "failed" and lease[
        "status"
    ] == (
        "integrity_failed"
        if lease["cleanup_status"] == "complete"
        else "integrity_and_cleanup_failed"
    )
    if not (verified_lease or failed_lease):
        raise ValueError("fake failed terminal lease status is inconsistent")
    cleanup_failures_present = (
        bool(cleanup)
        or lease["status"] != "closed"
        or lease["cleanup_status"] != "complete"
    )
    expected_status = (
        "failed_terminal_with_cleanup_failures"
        if cleanup_failures_present
        else "failed_terminal"
    )
    if document["status"] != expected_status:
        raise ValueError("fake failed terminal status is inconsistent")
    if document["outputs"] != {
        "worker_result_validated": (
            bindings["fake_worker_result_v2_sha256"] is not None
        ),
        "materialization_started": False,
        "quarantine_verification_present": False,
        "private_transport_files_may_remain": True,
        "publication_created": False,
    }:
        raise ValueError("fake failed terminal output evidence is invalid")
    if document["permissions"] != {
        "serialized_receipt_is_authority": False,
        "publication_permitted": False,
        "selection_permitted": False,
        "acceptance_eligible": False,
        "promotion_eligible": False,
    }:
        raise ValueError("fake failed terminal permissions are invalid")
    if document["limitations"] != [
        "exact_reap_native_failures_only",
        "spawn_failure_and_unproven_reap_have_no_terminal_receipt",
        "runtime_exec_and_worker_script_path_toctou_not_eliminated",
        "cleanup_events_are_code_owned_stages_not_exception_text",
        "private_transport_files_may_remain_after_failure",
        "no_public_cli_tui_selection_or_publication_route",
    ]:
        raise ValueError("fake failed terminal limitations are invalid")
    receipt_sha256 = document["receipt_sha256"]
    payload = dict(document)
    payload.pop("receipt_sha256")
    if not _valid_sha256(receipt_sha256) or receipt_sha256 != _hash(payload):
        raise ValueError("fake failed terminal receipt hash is invalid")
    return value


def _valid_exact_reap_process(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "state",
        "wait",
        "timed_out",
        "term_sent",
        "kill_sent",
        "leader_reaped",
        "ownership_released",
        "ownership_lost",
        "raw_pid_in_observation",
        "signal_authority_exposed",
    }:
        return False
    if (
        value["state"] != "started_exact_reaped"
        or any(
            type(value[key]) is not bool
            for key in ("timed_out", "term_sent", "kill_sent")
        )
        or value["leader_reaped"] is not True
        or value["ownership_released"] is not True
        or value["ownership_lost"] is not False
        or value["raw_pid_in_observation"] is not False
        or value["signal_authority_exposed"] is not False
    ):
        return False
    wait = value["wait"]
    if not isinstance(wait, dict) or set(wait) != {
        "kind",
        "exit_code",
        "signal",
        "core_dumped",
    }:
        return False
    kind = wait["kind"]
    return type(wait["core_dumped"]) is bool and (
        (
            kind == "exited"
            and type(wait["exit_code"]) is int
            and 0 <= wait["exit_code"] <= 255
            and wait["signal"] is None
            and wait["core_dumped"] is False
        )
        or (
            kind == "signaled"
            and wait["exit_code"] is None
            and type(wait["signal"]) is int
            and 0 < wait["signal"] <= 255
        )
    )


def _valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _SHA256 for character in value)
    )


def _wrapper(
    document: Mapping[str, Any],
) -> _SeparationFakeExecutionFailedTerminalReceipt:
    value = object.__new__(_SeparationFakeExecutionFailedTerminalReceipt)
    object.__setattr__(value, "_document", document)
    return value
