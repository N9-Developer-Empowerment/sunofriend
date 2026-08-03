"""Pure path-free failure receipts for the private native Kim coordinator.

The two receipt types are deliberately disjoint: one proves the code-owned
native launcher created no child; the other requires a started owner that was
completely drained and exactly reaped.  Unproven start or cleanup state has no
receipt constructor here.  These values grant no product or execution power.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ._separation_checkpoint_canonical import (
    canonical_sha256 as _hash,
    deep_freeze as _freeze,
    plain as _plain,
)
from ._separation_worker_request_v2_values import _validate_path_free


__all__: tuple[str, ...] = ()

_NO_START_SCHEMA = "sunofriend.private-melroformer-coordinator-no-start.v1"
_NO_START_POLICY = "private-kim-coordinator-no-start-v1"
_STARTED_SCHEMA = "sunofriend.private-melroformer-coordinator-failed-terminal.v1"
_STARTED_POLICY = "private-kim-coordinator-failed-terminal-v1"
_SHA256 = frozenset("0123456789abcdef")
_NO_START_STAGES = frozenset(
    {
        "file_actions_init",
        "file_actions",
        "attributes_init",
        "attributes",
        "posix_spawn",
    }
)
_PRIMARY_STAGES = frozenset(
    {
        "ready_handshake",
        "owner_binding",
        "process_image_observation",
        "executable_snapshot",
        "worker_release",
        "result_read",
        "network_observer_finish",
        "native_supervision",
        "terminal_validation",
        "process_image_completion",
        "native_image_completion",
        "staging_verification",
        "checkpoint_remeasurement",
        "terminal_projection",
        "terminal_cleanup",
        "terminal_evidence",
    }
)
_CLEANUP_STAGES = frozenset(
    {
        "ready_handshake_abort",
        "network_observer",
        "native_owner_supervision",
        "native_session_terminal",
        "child_transport_descriptor_close",
        "native_admission_finish",
        "fd5_reservation_release",
        "checkpoint_lease_close",
        "failure_receipt_seal",
    }
)
_FIELDS = {
    "schema",
    "policy_id",
    "status",
    "evidence_scope",
    "bindings",
    "failure",
    "process",
    "outputs",
    "privacy",
    "permissions",
    "limitations",
    "receipt_sha256",
}


@dataclass(frozen=True, init=False)
class _PrivateMelroformerCoordinatorNoStartReceipt(Mapping[str, Any]):
    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


@dataclass(frozen=True, init=False)
class _PrivateMelroformerCoordinatorFailedTerminalReceipt(Mapping[str, Any]):
    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


def _build_no_start_coordinator_failure_receipt(
    *,
    request_sha256: str,
    native_session_terminal_sha256: str,
    checkpoint_lease_terminal_sha256: str,
    native_no_start_stage: str,
    cleanup_stages: Sequence[str],
) -> _PrivateMelroformerCoordinatorNoStartReceipt:
    cleanup = _cleanup_events(cleanup_stages)
    payload = {
        "schema": _NO_START_SCHEMA,
        "policy_id": _NO_START_POLICY,
        "status": (
            "failed_no_start_with_cleanup_failures"
            if cleanup
            else "failed_no_start"
        ),
        "evidence_scope": "private_local_execution_failure_only",
        "bindings": {
            "request_sha256": _sha(request_sha256, "request"),
            "native_session_terminal_sha256": _sha(
                native_session_terminal_sha256,
                "native session terminal",
            ),
            "checkpoint_lease_terminal_sha256": _sha(
                checkpoint_lease_terminal_sha256,
                "checkpoint lease terminal",
            ),
        },
        "failure": {
            "primary_stage": "native_no_start",
            "native_no_start_stage": native_no_start_stage,
            "cleanup": cleanup,
            "cleanup_count": len(cleanup),
            "exception_text_recorded": False,
        },
        "process": {
            "state": "not_started",
            "child_created": False,
            "wait_attempted": False,
            "signal_attempted": False,
            "native_status_nonzero": True,
            "raw_process_identity_retained": False,
        },
        "outputs": {
            "worker_result_validated": False,
            "staging_accepted": False,
            "source_graph_changed": False,
            "product_output_created": False,
        },
        "privacy": _privacy(),
        "permissions": _permissions(),
        "limitations": _no_start_limitations(),
    }
    return _validate_no_start_coordinator_failure_receipt(
        _wrap_no_start({**payload, "receipt_sha256": _hash(payload)})
    )


def _build_started_coordinator_failure_receipt(
    *,
    request_sha256: str,
    native_session_terminal_sha256: str,
    checkpoint_lease_terminal_sha256: str,
    primary_stage: str,
    terminal_kind: str,
    worker_result_sha256: str | None,
    cleanup_stages: Sequence[str],
) -> _PrivateMelroformerCoordinatorFailedTerminalReceipt:
    cleanup = _cleanup_events(cleanup_stages)
    payload = {
        "schema": _STARTED_SCHEMA,
        "policy_id": _STARTED_POLICY,
        "status": (
            "failed_started_exact_reap_with_cleanup_failures"
            if cleanup
            else "failed_started_exact_reap"
        ),
        "evidence_scope": "private_local_execution_failure_only",
        "bindings": {
            "request_sha256": _sha(request_sha256, "request"),
            "native_session_terminal_sha256": _sha(
                native_session_terminal_sha256,
                "native session terminal",
            ),
            "checkpoint_lease_terminal_sha256": _sha(
                checkpoint_lease_terminal_sha256,
                "checkpoint lease terminal",
            ),
            "worker_result_sha256": (
                None
                if worker_result_sha256 is None
                else _sha(worker_result_sha256, "worker result")
            ),
        },
        "failure": {
            "primary_stage": primary_stage,
            "cleanup": cleanup,
            "cleanup_count": len(cleanup),
            "exception_text_recorded": False,
        },
        "process": {
            "state": "started_exact_reaped",
            "terminal_kind": terminal_kind,
            "complete_group_drained": True,
            "ownership_released": True,
            "ownership_lost": False,
            "raw_process_identity_retained": False,
        },
        "outputs": {
            "worker_result_validated": worker_result_sha256 is not None,
            "staging_accepted": False,
            "source_graph_changed": False,
            "product_output_created": False,
        },
        "privacy": _privacy(),
        "permissions": _permissions(),
        "limitations": _started_limitations(),
    }
    return _validate_started_coordinator_failure_receipt(
        _wrap_started({**payload, "receipt_sha256": _hash(payload)})
    )


def _validate_no_start_coordinator_failure_receipt(
    value: Any,
) -> _PrivateMelroformerCoordinatorNoStartReceipt:
    if type(value) is not _PrivateMelroformerCoordinatorNoStartReceipt:
        raise ValueError("private Kim no-start receipt type is invalid")
    document = _validate_common(value, schema=_NO_START_SCHEMA, policy=_NO_START_POLICY)
    failure = document["failure"]
    if (
        set(failure)
        != {
            "primary_stage",
            "native_no_start_stage",
            "cleanup",
            "cleanup_count",
            "exception_text_recorded",
        }
        or failure["primary_stage"] != "native_no_start"
        or failure["native_no_start_stage"] not in _NO_START_STAGES
    ):
        raise ValueError("private Kim no-start failure evidence is invalid")
    cleanup = _validate_cleanup(failure)
    if set(document["bindings"]) != {
        "request_sha256",
        "native_session_terminal_sha256",
        "checkpoint_lease_terminal_sha256",
    } or document["limitations"] != _no_start_limitations():
        raise ValueError("private Kim no-start bindings are invalid")
    expected_status = (
        "failed_no_start_with_cleanup_failures"
        if cleanup
        else "failed_no_start"
    )
    if document["status"] != expected_status or document["process"] != {
        "state": "not_started",
        "child_created": False,
        "wait_attempted": False,
        "signal_attempted": False,
        "native_status_nonzero": True,
        "raw_process_identity_retained": False,
    }:
        raise ValueError("private Kim no-start process evidence is invalid")
    if document["outputs"] != {
        "worker_result_validated": False,
        "staging_accepted": False,
        "source_graph_changed": False,
        "product_output_created": False,
    }:
        raise ValueError("private Kim no-start output evidence is invalid")
    return value


def _validate_started_coordinator_failure_receipt(
    value: Any,
) -> _PrivateMelroformerCoordinatorFailedTerminalReceipt:
    if type(value) is not _PrivateMelroformerCoordinatorFailedTerminalReceipt:
        raise ValueError("private Kim started failure receipt type is invalid")
    document = _validate_common(value, schema=_STARTED_SCHEMA, policy=_STARTED_POLICY)
    failure = document["failure"]
    if (
        set(failure)
        != {
            "primary_stage",
            "cleanup",
            "cleanup_count",
            "exception_text_recorded",
        }
        or failure["primary_stage"] not in _PRIMARY_STAGES
    ):
        raise ValueError("private Kim started failure evidence is invalid")
    cleanup = _validate_cleanup(failure)
    if set(document["bindings"]) != {
        "request_sha256",
        "native_session_terminal_sha256",
        "checkpoint_lease_terminal_sha256",
        "worker_result_sha256",
    } or document["limitations"] != _started_limitations():
        raise ValueError("private Kim started bindings are invalid")
    expected_status = (
        "failed_started_exact_reap_with_cleanup_failures"
        if cleanup
        else "failed_started_exact_reap"
    )
    process = document["process"]
    if (
        document["status"] != expected_status
        or process
        not in (
            {
                "state": "started_exact_reaped",
                "terminal_kind": "normal_exit_after_evidence_failure",
                "complete_group_drained": True,
                "ownership_released": True,
                "ownership_lost": False,
                "raw_process_identity_retained": False,
            },
            {
                "state": "started_exact_reaped",
                "terminal_kind": "failed_exit_exact_reap",
                "complete_group_drained": True,
                "ownership_released": True,
                "ownership_lost": False,
                "raw_process_identity_retained": False,
            },
        )
    ):
        raise ValueError("private Kim started process evidence is invalid")
    result_sha256 = document["bindings"]["worker_result_sha256"]
    if result_sha256 is not None and not _valid_sha(result_sha256):
        raise ValueError("private Kim worker-result binding is invalid")
    if document["outputs"] != {
        "worker_result_validated": result_sha256 is not None,
        "staging_accepted": False,
        "source_graph_changed": False,
        "product_output_created": False,
    }:
        raise ValueError("private Kim started output evidence is invalid")
    return value


def _validate_common(value: Mapping[str, Any], *, schema: str, policy: str) -> dict[str, Any]:
    document = _plain(value)
    if set(document) != _FIELDS:
        raise ValueError("private Kim failure receipt fields are invalid")
    _validate_path_free(document, "private Kim failure receipt")
    if (
        document["schema"] != schema
        or document["policy_id"] != policy
        or document["evidence_scope"] != "private_local_execution_failure_only"
        or document["privacy"] != _privacy()
        or document["permissions"] != _permissions()
    ):
        raise ValueError("private Kim failure receipt policy is invalid")
    bindings = document["bindings"]
    if not isinstance(bindings, dict) or any(
        key != "worker_result_sha256" and not _valid_sha(item)
        for key, item in bindings.items()
    ):
        raise ValueError("private Kim failure receipt bindings are invalid")
    receipt_sha256 = document["receipt_sha256"]
    payload = dict(document)
    payload.pop("receipt_sha256")
    if not _valid_sha(receipt_sha256) or receipt_sha256 != _hash(payload):
        raise ValueError("private Kim failure receipt hash is invalid")
    return document


def _cleanup_events(stages: Sequence[str]) -> list[dict[str, Any]]:
    if (
        isinstance(stages, (str, bytes))
        or len(stages) > 16
        or any(stage not in _CLEANUP_STAGES for stage in stages)
    ):
        raise ValueError("private Kim cleanup stages are invalid")
    return [
        {
            "ordinal": ordinal,
            "stage": stage,
            "reason_code": f"{stage}_failed",
        }
        for ordinal, stage in enumerate(stages)
    ]


def _validate_cleanup(failure: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    cleanup = failure["cleanup"]
    if (
        not isinstance(cleanup, list)
        or type(failure["cleanup_count"]) is not int
        or failure["cleanup_count"] != len(cleanup)
        or failure["exception_text_recorded"] is not False
    ):
        raise ValueError("private Kim cleanup evidence is invalid")
    stages: list[str] = []
    for ordinal, event in enumerate(cleanup):
        if (
            not isinstance(event, dict)
            or set(event) != {"ordinal", "stage", "reason_code"}
            or event["ordinal"] != ordinal
            or event["stage"] not in _CLEANUP_STAGES
            or event["reason_code"] != f"{event['stage']}_failed"
        ):
            raise ValueError("private Kim cleanup evidence is invalid")
        stages.append(event["stage"])
    return cleanup


def _privacy() -> dict[str, bool]:
    return {
        "raw_process_identity_retained": False,
        "private_paths_retained": False,
        "network_destination_retained": False,
        "exception_text_retained": False,
        "signal_authority_exposed": False,
    }


def _permissions() -> dict[str, bool]:
    return {
        "serialized_receipt_is_authority": False,
        "automatic_selection_permitted": False,
        "source_graph_activation_permitted": False,
        "product_route_permitted": False,
        "publication_permitted": False,
    }


def _no_start_limitations() -> list[str]:
    return [
        "code_owned_no_child_start_only",
        "started_or_unproven_attempts_use_no_start_receipt_never",
        "cleanup_stages_are_codes_not_exception_text",
        "receipt_is_failure_evidence_not_separator_quality_evidence",
        "no_public_cli_tui_simple_studio_or_source_graph_route",
    ]


def _started_limitations() -> list[str]:
    return [
        "complete_group_exact_reap_failures_only",
        "no_child_start_uses_a_separate_receipt_type",
        "unproven_start_or_reap_has_no_terminal_receipt",
        "checkpoint_model_or_audio_access_may_have_occurred",
        "cleanup_stages_are_codes_not_exception_text",
        "receipt_is_failure_evidence_not_separator_quality_evidence",
        "no_public_cli_tui_simple_studio_or_source_graph_route",
    ]


def _sha(value: str, label: str) -> str:
    if not _valid_sha(value):
        raise ValueError(f"private Kim {label} hash is invalid")
    return value


def _valid_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _SHA256 for character in value)
    )


def _wrap_no_start(
    document: Mapping[str, Any],
) -> _PrivateMelroformerCoordinatorNoStartReceipt:
    value = object.__new__(_PrivateMelroformerCoordinatorNoStartReceipt)
    object.__setattr__(value, "_document", _freeze(document))
    return value


def _wrap_started(
    document: Mapping[str, Any],
) -> _PrivateMelroformerCoordinatorFailedTerminalReceipt:
    value = object.__new__(_PrivateMelroformerCoordinatorFailedTerminalReceipt)
    object.__setattr__(value, "_document", _freeze(document))
    return value
