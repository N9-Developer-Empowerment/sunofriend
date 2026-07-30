from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from sunofriend import (
    _separation_fake_post_core_checkpoint_failure_records as records,
)
from sunofriend import _separation_native_session_darwin as native_module
from sunofriend._separation_checkpoint_canonical import (
    canonical_sha256,
    deep_freeze,
    plain,
)
from sunofriend._separation_checkpoint_lease_records import (
    _TerminalAnchor,
    _TerminalOutcome,
    receipt_document,
)
from sunofriend.separation_checkpoint_descriptor_lease import (
    SeparationCheckpointDescriptorLeaseTerminalReceipt,
)
from tests.test_separation_fake_execution_records import _execution_records


_ALLOWED_REASONS = (
    "checkpoint_byte_count_changed",
    "checkpoint_file_identity_changed",
    "checkpoint_file_identity_changed_during_remeasurement",
    "checkpoint_hash_changed",
)


def _native_observation(
    *,
    plan_sha256: str,
    result_sha256: str,
) -> native_module._VerifiedNativeLauncherExecutionObservation:
    payload = {
        "schema": "sunofriend.separation-native-launcher-execution.v1",
        "status": "verified_after_exact_reap",
        "native_session_observation_sha256": "1" * 64,
        "fake_launch_plan_v3_sha256": plan_sha256,
        "fake_worker_result_v2_sha256": result_sha256,
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
        "native_artifact_remeasured_after_reap": True,
        "runtime_remeasured_after_reap": True,
        "fake_worker_remeasured_after_reap": True,
        "raw_pid_in_execution_observation": False,
        "private_result_frame_contains_worker_pid": True,
        "signal_authority_exposed": False,
        "limitations": [
            "runtime_exec_and_worker_script_path_toctou_not_eliminated",
            "destructor_backstop_is_not_terminal_evidence",
            "outer_one_shot_supervisor_required_for_strict_hard_timeout",
            "deterministic_fixture_only_no_source_audio_or_model",
        ],
    }
    return native_module._execution_observation(
        deep_freeze(
            {
                **payload,
                "observation_sha256": canonical_sha256(payload),
            }
        )
    )


def _lease_receipt(
    request: Mapping[str, Any],
    *,
    reasons: tuple[str, ...] = ("checkpoint_hash_changed",),
    status: str = "integrity_failed",
    integrity_status: str = "failed",
    cleanup_status: str = "complete",
    cleanup_reasons: tuple[str, ...] = (),
    checkpoint_sha256: str | None = None,
    worker_request_sha256: str | None = None,
) -> SeparationCheckpointDescriptorLeaseTerminalReceipt:
    request_bindings = request["bindings"]
    anchor = _TerminalAnchor(
        bindings=deep_freeze(
            {
                "acceptance_artifact_sha256": "8" * 64,
                "archive_evidence_sha256": "9" * 64,
                "checkpoint_bytes": request_bindings["checkpoint_bytes"],
                "checkpoint_file_identity_sha256": request_bindings[
                    "checkpoint_file_identity_sha256"
                ],
                "checkpoint_sha256": (
                    request_bindings["checkpoint_sha256"]
                    if checkpoint_sha256 is None
                    else checkpoint_sha256
                ),
                "classification_evidence_sha256": "7" * 64,
                "lease_observation_sha256": request_bindings[
                    "lease_observation_sha256"
                ],
                "pickle_evidence_sha256": None,
                "preflight_sha256": request_bindings[
                    "preflight_sha256"
                ],
                "trusted_checkpoint_inspection_sha256": request_bindings[
                    "checkpoint_inspection_sha256"
                ],
                "worker_request_sha256": (
                    request_bindings["worker_request_v1_sha256"]
                    if worker_request_sha256 is None
                    else worker_request_sha256
                ),
            }
        )
    )
    outcome = _TerminalOutcome(
        status=status,
        integrity_status=integrity_status,
        integrity_reasons=reasons,
        cleanup_status=cleanup_status,
        cleanup_reasons=cleanup_reasons,
    )
    value = object.__new__(
        SeparationCheckpointDescriptorLeaseTerminalReceipt
    )
    object.__setattr__(value, "_document", receipt_document(anchor, outcome))
    return value


@pytest.fixture
def evidence(tmp_path: Path) -> dict[str, Any]:
    request, _historical, launch_v1, launch_v2, launch_v3, result = (
        _execution_records(tmp_path)
    )
    return {
        "request": request,
        "launch_v1": launch_v1,
        "launch_v2": launch_v2,
        "launch_v3": launch_v3,
        "result": result,
        "native": _native_observation(
            plan_sha256=launch_v3["plan_sha256"],
            result_sha256=result["result_sha256"],
        ),
    }


def _receipt(
    evidence: Mapping[str, Any],
    *,
    reasons: tuple[str, ...] = ("checkpoint_hash_changed",),
    cleanup_stages: tuple[str, ...] = (),
    native: Any | None = None,
    lease: Any | None = None,
) -> records._SeparationFakeExecutionPostCoreCheckpointFailedReceipt:
    return records._build_post_core_checkpoint_failed_terminal_receipt(
        fake_worker_request=evidence["request"],
        fake_launch_plan_v1=evidence["launch_v1"],
        blocked_fake_launch_plan_v2=evidence["launch_v2"],
        fake_launch_plan_v3=evidence["launch_v3"],
        fake_worker_result_v2=evidence["result"],
        native_execution_observation=(
            evidence["native"] if native is None else native
        ),
        lease_terminal_receipt=(
            _lease_receipt(evidence["request"], reasons=reasons)
            if lease is None
            else lease
        ),
        cleanup_stages=cleanup_stages,
    )


@pytest.mark.parametrize(
    "reasons",
    tuple((reason,) for reason in _ALLOWED_REASONS),
)
def test_post_core_receipt_is_path_free_self_hashed_and_inert(
    reasons: tuple[str, ...],
    evidence: Mapping[str, Any],
) -> None:
    receipt = _receipt(evidence, reasons=reasons)
    document = plain(receipt)
    receipt_sha256 = document.pop("receipt_sha256")

    assert records.__all__ == ()
    assert (
        type(receipt)
        is records._SeparationFakeExecutionPostCoreCheckpointFailedReceipt
    )
    assert (
        document["schema"]
        == "sunofriend.separation-fake-post-core-checkpoint-failure.v1"
    )
    assert document["policy_id"] == (
        "private-post-core-checkpoint-integrity-failure-v1"
    )
    assert document["status"] == (
        "failed_post_core_checkpoint_integrity"
    )
    assert document["failure"]["primary"] == {
        "scope": "parent_post_core_checkpoint_integrity",
        "stage": "checkpoint_post_core_remeasurement",
        "reason_codes": list(reasons),
    }
    assert document["process"] == {
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
    assert document["checkpoint"] == {
        "worker_result_reports_checkpoint_remeasured": True,
        "worker_result_reports_checkpoint_deserialized": False,
        "parent_post_core_remeasurement_attempted": True,
        "parent_post_core_integrity_matched": False,
        "exact_checkpoint_bytes_executed_proven": False,
        "deserialization_absence_at_exec_proven": False,
    }
    assert document["lease"]["integrity_reasons"] == list(reasons)
    assert document["lease"]["cleanup_status"] == "complete"
    assert document["outputs"] == {
        "worker_result_validated": True,
        "materialization_started": False,
        "quarantine_verification_present": False,
        "materialization_observation_present": False,
        "private_transport_files_may_remain": True,
        "publication_created": False,
    }
    assert document["permissions"] == {
        "serialized_receipt_is_authority": False,
        "publication_permitted": False,
        "selection_permitted": False,
        "acceptance_eligible": False,
        "promotion_eligible": False,
    }
    assert receipt_sha256 == canonical_sha256(document)
    assert not any(
        isinstance(item, str)
        and (item.startswith(("/", "~/", "../", "./")) or "://" in item)
        for item in _values(document)
    )


def test_post_core_cleanup_is_single_and_narrow(
    evidence: Mapping[str, Any],
) -> None:
    receipt = _receipt(
        evidence,
        cleanup_stages=("private_root_descriptor_close",),
    )

    assert receipt["status"] == (
        "failed_post_core_checkpoint_integrity_with_cleanup_failures"
    )
    assert receipt["failure"]["cleanup"] == (
        {
            "ordinal": 0,
            "stage": "private_root_descriptor_close",
            "reason_code": "private_root_descriptor_close_failed",
        },
    )
    with pytest.raises(ValueError, match="cleanup evidence"):
        _receipt(evidence, cleanup_stages=("native_final_supervision",))
    with pytest.raises(ValueError, match="cleanup evidence"):
        _receipt(
            evidence,
            cleanup_stages=(
                "private_root_descriptor_close",
                "private_root_descriptor_close",
            ),
        )


def test_post_core_rejects_multiple_integrity_reasons(
    evidence: Mapping[str, Any],
) -> None:
    with pytest.raises(ValueError, match="narrow integrity failure"):
        _receipt(evidence, reasons=_ALLOWED_REASONS)


@pytest.mark.parametrize(
    "mutation",
    (
        "reason",
        "process",
        "checkpoint",
        "lease",
        "output",
        "permission",
        "limitation",
        "cleanup",
        "binding",
    ),
)
def test_post_core_receipt_rejects_rehashed_tampering(
    mutation: str,
    evidence: Mapping[str, Any],
) -> None:
    document = plain(_receipt(evidence))
    document.pop("receipt_sha256")
    if mutation == "reason":
        document["failure"]["primary"]["reason_codes"] = [
            "checkpoint_descriptor_remeasurement_failed"
        ]
        document["lease"]["integrity_reasons"] = [
            "checkpoint_descriptor_remeasurement_failed"
        ]
    elif mutation == "process":
        document["process"]["leader_reaped"] = False
    elif mutation == "checkpoint":
        document["checkpoint"][
            "exact_checkpoint_bytes_executed_proven"
        ] = True
    elif mutation == "lease":
        document["lease"]["cleanup_status"] = "close_unconfirmed"
    elif mutation == "output":
        document["outputs"]["materialization_started"] = True
    elif mutation == "permission":
        document["permissions"]["publication_permitted"] = True
    elif mutation == "limitation":
        document["limitations"].pop()
    elif mutation == "cleanup":
        document["failure"]["cleanup"] = [
            {
                "ordinal": 0,
                "stage": "quarantine_directory_descriptor_close",
                "reason_code": (
                    "quarantine_directory_descriptor_close_failed"
                ),
            }
        ]
        document["failure"]["cleanup_count"] = 1
        document["status"] = (
            "failed_post_core_checkpoint_integrity_with_cleanup_failures"
        )
    else:
        document["bindings"]["fake_worker_result_v2_sha256"] = "f" * 63
    document["receipt_sha256"] = canonical_sha256(document)
    tampered = records._wrapper(deep_freeze(document))

    with pytest.raises(ValueError):
        records._validate_post_core_checkpoint_failed_terminal_receipt(
            tampered
        )


def test_post_core_builder_rejects_cross_bound_native_and_lease(
    evidence: Mapping[str, Any],
) -> None:
    with pytest.raises(ValueError, match="native success binding changed"):
        _receipt(
            evidence,
            native=_native_observation(
                plan_sha256="f" * 64,
                result_sha256=evidence["result"]["result_sha256"],
            ),
        )
    with pytest.raises(ValueError, match="native success binding changed"):
        _receipt(
            evidence,
            native=_native_observation(
                plan_sha256=evidence["launch_v3"]["plan_sha256"],
                result_sha256="e" * 64,
            ),
        )
    with pytest.raises(ValueError, match="lease binding changed"):
        _receipt(
            evidence,
            lease=_lease_receipt(
                evidence["request"],
                checkpoint_sha256="f" * 64,
            ),
        )
    with pytest.raises(ValueError, match="lease binding changed"):
        _receipt(
            evidence,
            lease=_lease_receipt(
                evidence["request"],
                worker_request_sha256="e" * 64,
            ),
        )


def test_post_core_builder_requires_exact_narrow_failed_lease(
    evidence: Mapping[str, Any],
) -> None:
    failed = _lease_receipt(evidence["request"])
    with pytest.raises(ValueError, match="exact lease receipt"):
        _receipt(evidence, lease=plain(failed))
    with pytest.raises(ValueError, match="not a narrow integrity failure"):
        _receipt(
            evidence,
            lease=_lease_receipt(
                evidence["request"],
                reasons=(),
                status="closed",
                integrity_status="verified_before_close_attempt",
            ),
        )
    with pytest.raises(ValueError, match="not a narrow integrity failure"):
        _receipt(
            evidence,
            lease=_lease_receipt(
                evidence["request"],
                status="integrity_and_cleanup_failed",
                cleanup_status="close_unconfirmed",
                cleanup_reasons=("checkpoint_descriptor_close_failed",),
            ),
        )
    with pytest.raises(ValueError, match="not a narrow integrity failure"):
        _receipt(
            evidence,
            lease=_lease_receipt(
                evidence["request"],
                reasons=("checkpoint_descriptor_remeasurement_failed",),
            ),
        )


def test_post_core_proof_limitations_do_not_claim_checkpoint_execution(
    evidence: Mapping[str, Any],
) -> None:
    receipt = _receipt(evidence)

    assert receipt["checkpoint"][
        "exact_checkpoint_bytes_executed_proven"
    ] is False
    assert receipt["checkpoint"][
        "deserialization_absence_at_exec_proven"
    ] is False
    assert receipt["limitations"] == (
        "child_checkpoint_hash_is_worker_report",
        (
            "parent_post_reap_mismatch_not_proof_of_bytes_executed_or_"
            "deserialized"
        ),
        "runtime_exec_and_worker_script_path_toctou_not_eliminated",
        (
            "transient_changes_outside_observed_stat_hash_windows_not_"
            "excluded"
        ),
        "deterministic_fixture_only_no_source_audio_or_model",
        "private_transport_files_may_remain_after_failure",
        "no_public_cli_tui_selection_or_publication_route",
    )
    assert all(
        permitted is False
        for permitted in receipt["permissions"].values()
    )


def test_post_core_receipt_type_is_not_substitutable(
    evidence: Mapping[str, Any],
) -> None:
    receipt = _receipt(evidence)
    with pytest.raises(ValueError, match="type"):
        records._validate_post_core_checkpoint_failed_terminal_receipt(
            plain(receipt)
        )
    with pytest.raises(ValueError, match="exact native"):
        _receipt(evidence, native=plain(evidence["native"]))


def _values(value: Any) -> list[Any]:
    if isinstance(value, Mapping):
        return [
            item
            for nested in value.values()
            for item in [nested, *_values(nested)]
        ]
    if isinstance(value, (tuple, list)):
        return [item for nested in value for item in _values(nested)]
    return [value]
