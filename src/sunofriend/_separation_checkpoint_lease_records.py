"""Pure record policy for private checkpoint descriptor leases.

This module constructs and validates path-free observation and terminal
evidence.  It has no descriptor, filesystem, registry, lifecycle, model or
process authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ._separation_checkpoint_canonical import (
    canonical_sha256 as _hash,
    deep_freeze as _freeze,
    plain as _plain,
)


SEPARATION_CHECKPOINT_DESCRIPTOR_LEASE_OBSERVATION_SCHEMA = (
    "sunofriend.separation-checkpoint-descriptor-lease-observation.v1"
)
SEPARATION_CHECKPOINT_DESCRIPTOR_LEASE_RECEIPT_SCHEMA = (
    "sunofriend.separation-checkpoint-descriptor-lease-terminal-receipt.v1"
)
SEPARATION_CHECKPOINT_DESCRIPTOR_LEASE_ID = (
    "private-parent-checkpoint-descriptor-lease-v1"
)

_FALSE_EFFECTS = (
    "checkpoint_loaded",
    "checkpoint_deserialized",
    "model_imported",
    "process_started",
    "network_used",
    "audio_read",
    "files_written",
    "publication_permitted",
    "selection_permitted",
    "acceptance_eligible",
    "promotion_eligible",
)
_TERMINAL_STATUSES = frozenset(
    {
        "closed",
        "cleanup_failed",
        "integrity_failed",
        "integrity_and_cleanup_failed",
    }
)
_INTEGRITY_REASONS = frozenset(
    {
        "checkpoint_byte_count_changed",
        "checkpoint_descriptor_became_inheritable",
        "checkpoint_descriptor_ownership_lost",
        "checkpoint_descriptor_remeasurement_failed",
        "checkpoint_file_identity_changed",
        "checkpoint_file_identity_changed_during_remeasurement",
        "checkpoint_hash_changed",
        "lease_authority_binding_invalid",
        "lease_live_ownership_invalid",
        "lease_state_matrix_invalid",
        "trusted_parent_pid_convention_violated",
    }
)
_CLEANUP_OUTCOMES = {
    "complete": (),
    "close_not_attempted": ("checkpoint_descriptor_ownership_lost",),
    "close_unconfirmed": ("checkpoint_descriptor_close_failed",),
}


@dataclass(frozen=True)
class _TerminalOutcome:
    status: str
    integrity_status: str
    integrity_reasons: tuple[str, ...]
    cleanup_status: str
    cleanup_reasons: tuple[str, ...]


@dataclass(frozen=True)
class _TerminalAnchor:
    bindings: Mapping[str, Any]


def expected_acquisition_evidence(
    *,
    file_identity: Mapping[str, Any],
    request: Any,
    trusted_inspection: Mapping[str, Any],
    hash_value: Callable[[Any], str] = _hash,
) -> dict[str, Any]:
    """Derive path-free acquisition evidence from already-trusted values."""

    inspection = trusted_inspection
    checkpoint = inspection["checkpoint"]
    classification = inspection["classification"]
    archive = inspection["archive"]
    pickle = inspection["pickle"]
    identity = _plain(file_identity)
    if (
        _plain(checkpoint["file_identity"]) != identity
        or checkpoint["sha256"] != request.checkpoint_sha256
        or checkpoint["bytes"] != request.checkpoint_bytes
    ):
        raise ValueError("retained checkpoint identity authority changed")
    return {
        "bindings": {
            "worker_request_sha256": request.request_sha256,
            "preflight_sha256": request.preflight_sha256,
            "acceptance_artifact_sha256": request.acceptance_artifact_sha256,
            "trusted_checkpoint_inspection_sha256": inspection[
                "inspection_sha256"
            ],
            "checkpoint_sha256": request.checkpoint_sha256,
            "checkpoint_bytes": request.checkpoint_bytes,
            "checkpoint_file_identity_sha256": hash_value(identity),
            "classification_evidence_sha256": classification[
                "classification_evidence_sha256"
            ],
            "archive_evidence_sha256": hash_value(_plain(archive)),
            "pickle_evidence_sha256": (
                None if pickle is None else hash_value(_plain(pickle))
            ),
        },
        "classification": {
            "container_kind": classification["container_kind"],
            "confidence": classification["confidence"],
            "evidence_equal_to_trusted_inspection": True,
        },
        "archive_metadata_parsed": archive["archive_metadata_parsed"],
        "pickle_opcodes_parsed": archive["pickle_metadata_parsed"],
    }


def observation_document(evidence: Mapping[str, Any]) -> Mapping[str, Any]:
    """Seal and validate one immutable live-descriptor observation."""

    document = expected_observation_document(evidence)
    _validate_observation_document(document, evidence)
    return _freeze(document)


def expected_observation_document(
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the canonical observation document expected from evidence."""

    payload = _observation_payload(evidence)
    return {**payload, "observation_sha256": _hash(payload)}


def _observation_payload(evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": SEPARATION_CHECKPOINT_DESCRIPTOR_LEASE_OBSERVATION_SCHEMA,
        "lease_id": SEPARATION_CHECKPOINT_DESCRIPTOR_LEASE_ID,
        "status": "retained_not_loaded",
        "evidence_scope": "private_development",
        "publication_scope": "private_local_contract_evidence",
        "execution_supported": False,
        "execution_permitted": False,
        "selection_permitted": False,
        "bindings": _plain(evidence["bindings"]),
        "classification": _plain(evidence["classification"]),
        "descriptor": {
            "retained": True,
            "raw_descriptor_exposed": False,
            "inheritable": False,
            "shared_offset_reset_to_zero": True,
            "ancestor_descriptors_closed": True,
            "owner_pid_recorded_privately": True,
        },
        "limitations": [
            "checkpoint_descriptor_not_handed_to_loader",
            "checkpoint_descriptor_registry_state_is_in_process_convention",
            "checkpoint_immutable_snapshot_not_enforced",
            "checkpoint_in_place_mutation_remains_possible",
            "checkpoint_content_may_change_after_last_remeasurement",
            "lease_observation_is_historical_not_liveness_authority",
            "future_handoff_requires_remeasure_and_install_under_same_lease_lock",
            "trusted_parent_pid_convention_not_kernel_enforced",
        ],
        "effects": {
            "checkpoint_descriptor_retained": True,
            "checkpoint_descriptor_closed": False,
            "ancestor_descriptors_closed": True,
            **{key: False for key in _FALSE_EFFECTS},
        },
    }


def _validate_observation_document(
    document: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> None:
    value = _plain(document)
    expected = expected_observation_document(evidence)
    if value != expected:
        raise ValueError("checkpoint descriptor lease observation is invalid")
    _path_free(value)


def new_terminal_anchor(
    evidence: Mapping[str, Any],
    observation: Mapping[str, Any],
    *,
    maximum_checkpoint_bytes: int,
) -> _TerminalAnchor:
    """Bind terminal evidence to one sealed observation."""

    anchor = _TerminalAnchor(
        bindings=_freeze(
            {
                "lease_observation_sha256": observation[
                    "observation_sha256"
                ],
                **_plain(evidence["bindings"]),
            }
        )
    )
    validate_terminal_anchor(
        anchor,
        maximum_checkpoint_bytes=maximum_checkpoint_bytes,
    )
    return anchor


def validate_terminal_anchor(
    anchor: _TerminalAnchor,
    *,
    maximum_checkpoint_bytes: int,
) -> None:
    """Validate terminal bindings against the façade's current byte limit."""

    if type(anchor) is not _TerminalAnchor:
        raise ValueError("checkpoint descriptor terminal anchor is invalid")
    bindings = _plain(anchor.bindings)
    expected_keys = {
        "acceptance_artifact_sha256",
        "archive_evidence_sha256",
        "checkpoint_bytes",
        "checkpoint_file_identity_sha256",
        "checkpoint_sha256",
        "classification_evidence_sha256",
        "lease_observation_sha256",
        "pickle_evidence_sha256",
        "preflight_sha256",
        "trusted_checkpoint_inspection_sha256",
        "worker_request_sha256",
    }
    if set(bindings) != expected_keys:
        raise ValueError("checkpoint descriptor terminal bindings are invalid")
    for key, value in bindings.items():
        if key == "checkpoint_bytes":
            if (
                type(value) is not int
                or value <= 0
                or value > maximum_checkpoint_bytes
            ):
                raise ValueError(
                    "checkpoint descriptor terminal byte binding is invalid"
                )
        elif key == "pickle_evidence_sha256" and value is None:
            continue
        elif (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError(
                "checkpoint descriptor terminal hash binding is invalid"
            )
    _path_free(bindings)


def receipt_document(
    anchor: _TerminalAnchor,
    outcome: _TerminalOutcome,
) -> Mapping[str, Any]:
    """Seal one immutable terminal receipt."""

    payload = _receipt_payload(anchor, outcome)
    document = {**payload, "receipt_sha256": _hash(payload)}
    return _freeze(document)


def _receipt_payload(
    anchor: _TerminalAnchor,
    outcome: _TerminalOutcome,
) -> dict[str, Any]:
    return {
        "schema": SEPARATION_CHECKPOINT_DESCRIPTOR_LEASE_RECEIPT_SCHEMA,
        "lease_id": SEPARATION_CHECKPOINT_DESCRIPTOR_LEASE_ID,
        "status": outcome.status,
        "execution_supported": False,
        "execution_permitted": False,
        "selection_permitted": False,
        "bindings": _plain(anchor.bindings),
        "integrity": {
            "status": outcome.integrity_status,
            "reasons": list(outcome.integrity_reasons),
        },
        "cleanup": {
            "status": outcome.cleanup_status,
            "reasons": list(outcome.cleanup_reasons),
            "descriptor_close_attempted": (
                outcome.cleanup_status != "close_not_attempted"
            ),
            "descriptor_close_call_succeeded": (
                outcome.cleanup_status == "complete"
            ),
        },
        "limitations": [
            "checkpoint_content_may_change_after_last_remeasurement",
            "descriptor_close_call_success_is_not_post_close_proof",
        ],
        "effects": {
            "checkpoint_descriptor_retained": False,
            "checkpoint_descriptor_close_attempted": (
                outcome.cleanup_status != "close_not_attempted"
            ),
            "checkpoint_descriptor_close_call_succeeded": (
                outcome.cleanup_status == "complete"
            ),
            **{key: False for key in _FALSE_EFFECTS},
        },
    }


def validate_receipt_document(
    document: Mapping[str, Any],
    *,
    anchor: _TerminalAnchor,
    outcome: _TerminalOutcome,
    maximum_checkpoint_bytes: int,
) -> None:
    """Validate a terminal receipt and its bound outcome."""

    validate_terminal_anchor(
        anchor,
        maximum_checkpoint_bytes=maximum_checkpoint_bytes,
    )
    _validate_terminal_outcome(outcome)
    value = _plain(document)
    payload = _receipt_payload(anchor, outcome)
    expected = {**payload, "receipt_sha256": _hash(payload)}
    if value != expected:
        raise ValueError("checkpoint descriptor lease receipt is invalid")
    _path_free(value)


def _validate_terminal_outcome(outcome: _TerminalOutcome) -> None:
    integrity_reasons = outcome.integrity_reasons
    cleanup_reasons = outcome.cleanup_reasons
    if (
        outcome.status not in _TERMINAL_STATUSES
        or integrity_reasons != tuple(sorted(set(integrity_reasons)))
        or cleanup_reasons != tuple(sorted(set(cleanup_reasons)))
        or any(reason not in _INTEGRITY_REASONS for reason in integrity_reasons)
        or _CLEANUP_OUTCOMES.get(outcome.cleanup_status) != cleanup_reasons
    ):
        raise ValueError("checkpoint descriptor terminal outcome is invalid")
    verified = (
        outcome.integrity_status == "verified_before_close_attempt"
        and not integrity_reasons
        and outcome.status
        == (
            "closed"
            if outcome.cleanup_status == "complete"
            else "cleanup_failed"
        )
    )
    failed = (
        outcome.integrity_status == "failed"
        and bool(integrity_reasons)
        and outcome.status
        == (
            "integrity_failed"
            if outcome.cleanup_status == "complete"
            else "integrity_and_cleanup_failed"
        )
    )
    if not (verified or failed):
        raise ValueError("checkpoint descriptor terminal state is inconsistent")


def _path_free(value: Any) -> None:
    if isinstance(value, Mapping):
        for item in value.values():
            _path_free(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _path_free(item)
    elif isinstance(value, str) and (
        value.startswith(("/", "~/", "../", "./"))
        or "://" in value
        or "\x00" in value
    ):
        raise ValueError("checkpoint lease evidence must be path-free")
