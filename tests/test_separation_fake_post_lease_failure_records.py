from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from sunofriend import _separation_fake_post_lease_failure_records as records
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


def _native_observation(
    *,
    plan_sha256: str,
    result_sha256: str,
    term_sent: bool = False,
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
        "term_sent": term_sent,
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
    healthy: bool = True,
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
    outcome = (
        _TerminalOutcome(
            status="closed",
            integrity_status="verified_before_close_attempt",
            integrity_reasons=(),
            cleanup_status="complete",
            cleanup_reasons=(),
        )
        if healthy
        else _TerminalOutcome(
            status="cleanup_failed",
            integrity_status="verified_before_close_attempt",
            integrity_reasons=(),
            cleanup_status="close_unconfirmed",
            cleanup_reasons=("checkpoint_descriptor_close_failed",),
        )
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
        "lease": _lease_receipt(request),
    }


def _progress(stage: str) -> tuple[bool, str | None, str | None]:
    if stage in {"result_revalidation", "private_root_revalidation"}:
        return False, None, None
    if stage in {
        "quarantine_directory_materialization",
        "quarantine_output_materialization",
        "quarantine_verification",
    }:
        return True, None, None
    if stage == "materialization_observation_seal":
        return True, "6" * 64, None
    return True, "6" * 64, "7" * 64


def _receipt(
    evidence: Mapping[str, Any],
    *,
    primary_stage: str = "quarantine_directory_materialization",
    cleanup_stages: tuple[str, ...] = (),
    progress: tuple[bool, str | None, str | None] | None = None,
    native: Any | None = None,
    lease: Any | None = None,
) -> records._SeparationFakeExecutionPostLeaseFailedReceipt:
    materialization_started, quarantine_hash, materialization_hash = (
        _progress(primary_stage) if progress is None else progress
    )
    return records._build_post_lease_failed_terminal_receipt(
        fake_worker_request=evidence["request"],
        fake_launch_plan_v1=evidence["launch_v1"],
        blocked_fake_launch_plan_v2=evidence["launch_v2"],
        fake_launch_plan_v3=evidence["launch_v3"],
        fake_worker_result_v2=evidence["result"],
        native_execution_observation=(
            evidence["native"] if native is None else native
        ),
        lease_terminal_receipt=(
            evidence["lease"] if lease is None else lease
        ),
        primary_stage=primary_stage,
        materialization_started=materialization_started,
        quarantine_verification_sha256=quarantine_hash,
        materialization_observation_sha256=materialization_hash,
        cleanup_stages=cleanup_stages,
    )


@pytest.mark.parametrize(
    "primary_stage",
    (
        "result_revalidation",
        "private_root_revalidation",
        "quarantine_directory_materialization",
        "quarantine_output_materialization",
        "quarantine_verification",
        "materialization_observation_seal",
        "materialization_descriptor_cleanup",
        "whole_run_receipt_seal",
        "private_root_descriptor_close",
    ),
)
def test_post_lease_receipt_is_path_free_self_hashed_and_inert(
    primary_stage: str,
    evidence: Mapping[str, Any],
) -> None:
    receipt = _receipt(evidence, primary_stage=primary_stage)
    document = plain(receipt)
    receipt_sha256 = document.pop("receipt_sha256")

    assert records.__all__ == ()
    assert (
        type(receipt)
        is records._SeparationFakeExecutionPostLeaseFailedReceipt
    )
    assert document["status"] == "failed_post_lease"
    assert document["failure"]["primary"]["stage"] == primary_stage
    assert document["process"]["state"] == "started_exact_reaped_success"
    assert document["lease"]["status"] == "closed"
    assert document["outputs"]["worker_result_validated"] is True
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


def test_post_lease_cleanup_preserves_reachable_order_and_duplicates(
    evidence: Mapping[str, Any],
) -> None:
    receipt = _receipt(
        evidence,
        primary_stage="materialization_descriptor_cleanup",
        cleanup_stages=(
            "quarantine_output_read_descriptor_close",
            "quarantine_output_read_descriptor_close",
            "quarantine_directory_descriptor_close",
            "private_root_descriptor_close",
        ),
    )

    assert receipt["status"] == (
        "failed_post_lease_with_cleanup_failures"
    )
    assert [event["stage"] for event in receipt["failure"]["cleanup"]] == [
        "quarantine_output_read_descriptor_close",
        "quarantine_output_read_descriptor_close",
        "quarantine_directory_descriptor_close",
        "private_root_descriptor_close",
    ]


@pytest.mark.parametrize(
    ("primary_stage", "cleanup_stage"),
    (
        (
            "result_revalidation",
            "quarantine_output_read_descriptor_close",
        ),
        (
            "private_root_revalidation",
            "quarantine_directory_descriptor_close",
        ),
        (
            "private_root_descriptor_close",
            "private_root_descriptor_close",
        ),
    ),
)
def test_post_lease_receipt_rejects_unreachable_cleanup(
    primary_stage: str,
    cleanup_stage: str,
    evidence: Mapping[str, Any],
) -> None:
    with pytest.raises(ValueError, match="cleanup evidence"):
        _receipt(
            evidence,
            primary_stage=primary_stage,
            cleanup_stages=(cleanup_stage,),
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "process",
        "lease",
        "permission",
        "progress",
        "cleanup",
        "binding_format",
    ),
)
def test_post_lease_receipt_rejects_rehashed_tampering(
    mutation: str,
    evidence: Mapping[str, Any],
) -> None:
    document = plain(_receipt(evidence))
    document.pop("receipt_sha256")
    if mutation == "process":
        document["process"]["leader_reaped"] = False
    elif mutation == "lease":
        document["lease"]["cleanup_status"] = "close_unconfirmed"
    elif mutation == "permission":
        document["permissions"]["publication_permitted"] = True
    elif mutation == "progress":
        document["outputs"]["quarantine_verification_present"] = True
    elif mutation == "cleanup":
        document["failure"]["cleanup"] = [
            {
                "ordinal": 0,
                "stage": "native_final_supervision",
                "reason_code": "native_final_supervision_failed",
            }
        ]
        document["failure"]["cleanup_count"] = 1
        document["status"] = "failed_post_lease_with_cleanup_failures"
    else:
        document["bindings"]["fake_worker_result_v2_sha256"] = "f" * 63
    document["receipt_sha256"] = canonical_sha256(document)
    tampered = records._wrapper(deep_freeze(document))

    with pytest.raises(ValueError):
        records._validate_post_lease_failed_terminal_receipt(tampered)


def test_post_lease_builder_rejects_cross_bound_native_and_lease(
    evidence: Mapping[str, Any],
) -> None:
    launch_v3 = evidence["launch_v3"]
    result = evidence["result"]
    with pytest.raises(ValueError, match="binding changed"):
        _receipt(
            evidence,
            native=_native_observation(
                plan_sha256="f" * 64,
                result_sha256=result["result_sha256"],
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
    with pytest.raises(ValueError, match="native success.*policy"):
        _receipt(
            evidence,
            native=_native_observation(
                plan_sha256=launch_v3["plan_sha256"],
                result_sha256=result["result_sha256"],
                term_sent=True,
            ),
        )


def test_post_lease_builder_requires_exact_healthy_closed_lease(
    evidence: Mapping[str, Any],
) -> None:
    with pytest.raises(ValueError, match="exact checkpoint lease"):
        _receipt(evidence, lease=plain(evidence["lease"]))
    with pytest.raises(ValueError, match="not healthy and closed"):
        _receipt(
            evidence,
            lease=_lease_receipt(evidence["request"], healthy=False),
        )


def test_post_lease_builder_rejects_impossible_progress(
    evidence: Mapping[str, Any],
) -> None:
    with pytest.raises(ValueError, match="progress"):
        _receipt(
            evidence,
            primary_stage="quarantine_verification",
            progress=(True, "6" * 64, None),
        )
    with pytest.raises(ValueError, match="progress"):
        _receipt(
            evidence,
            primary_stage="whole_run_receipt_seal",
            progress=(True, "6" * 64, None),
        )
    with pytest.raises(ValueError, match="progress"):
        _receipt(
            evidence,
            primary_stage="private_root_descriptor_close",
            progress=(True, "6" * 64, None),
        )


def test_post_lease_receipt_type_is_not_substitutable(
    evidence: Mapping[str, Any],
) -> None:
    with pytest.raises(ValueError, match="type"):
        records._validate_post_lease_failed_terminal_receipt(
            plain(_receipt(evidence))
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
