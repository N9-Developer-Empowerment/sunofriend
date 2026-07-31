from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from sunofriend import (
    _separation_fake_lease_close_checkpoint_failure_records as records,
)
from sunofriend._separation_checkpoint_canonical import (
    canonical_sha256,
    deep_freeze,
    plain,
)
from tests.test_separation_fake_execution_records import _execution_records
from tests.test_separation_fake_post_core_checkpoint_failure_records import (
    _lease_receipt,
    _native_observation,
    _receipt as _post_core_receipt,
)
from tests.test_separation_fake_reservation_release_checkpoint_failure_records import (
    _receipt as _release_receipt,
)


_ALLOWED_REASONS = (
    "checkpoint_byte_count_changed",
    "checkpoint_file_identity_changed",
    "checkpoint_file_identity_changed_during_remeasurement",
    "checkpoint_hash_changed",
)


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
) -> records._SeparationFakeExecutionLeaseCloseCheckpointFailedReceipt:
    return records._build_lease_close_checkpoint_failed_terminal_receipt(
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
def test_lease_close_receipt_is_path_free_hashed_and_inert(
    reasons: tuple[str, ...],
    evidence: Mapping[str, Any],
    tmp_path: Path,
) -> None:
    receipt = _receipt(evidence, reasons=reasons)
    document = plain(receipt)
    receipt_sha256 = document.pop("receipt_sha256")

    assert records.__all__ == ()
    assert type(receipt) is (
        records._SeparationFakeExecutionLeaseCloseCheckpointFailedReceipt
    )
    assert document["schema"] == (
        "sunofriend.separation-fake-lease-close-checkpoint-failure.v1"
    )
    assert document["policy_id"] == (
        "private-lease-close-checkpoint-integrity-failure-v1"
    )
    assert document["status"] == (
        "failed_lease_close_checkpoint_integrity"
    )
    assert document["failure"]["primary"] == {
        "scope": "parent_checkpoint_lease_close_integrity",
        "stage": "checkpoint_lease_close_checkpoint_remeasurement",
        "reason_codes": list(reasons),
    }
    assert document["failure"]["cleanup"] == []
    assert document["failure"]["cleanup_count"] == 0
    assert document["failure"]["exception_text_recorded"] is False
    assert document["lease"] == {
        "terminal_receipt_present": True,
        "status": "integrity_failed",
        "integrity_status": "failed",
        "integrity_reasons": list(reasons),
        "cleanup_status": "complete",
        "cleanup_reasons": [],
    }
    assert document["permissions"] == {
        "serialized_receipt_is_authority": False,
        "publication_permitted": False,
        "selection_permitted": False,
        "acceptance_eligible": False,
        "promotion_eligible": False,
    }
    assert document["outputs"]["materialization_started"] is False
    assert document["outputs"]["publication_created"] is False
    assert receipt_sha256 == canonical_sha256(document)
    serialized = json.dumps(document, sort_keys=True)
    assert str(tmp_path) not in serialized
    assert "/" not in serialized
    with pytest.raises((AttributeError, TypeError)):
        receipt._document = deep_freeze({})  # type: ignore[misc]


def test_lease_close_receipt_binds_exact_chain_and_process(
    evidence: Mapping[str, Any],
) -> None:
    receipt = _receipt(evidence)

    assert receipt["run_nonce"] == evidence["launch_v3"]["run_nonce"]
    assert receipt["bindings"] == {
        "fake_worker_request_v1_sha256": (
            evidence["request"]["request_sha256"]
        ),
        "fake_launch_plan_v1_sha256": (
            evidence["launch_v1"]["plan_sha256"]
        ),
        "blocked_fake_launch_plan_v2_sha256": (
            evidence["launch_v2"]["plan_sha256"]
        ),
        "fake_launch_plan_v3_sha256": (
            evidence["launch_v3"]["plan_sha256"]
        ),
        "fake_worker_result_v2_sha256": (
            evidence["result"]["result_sha256"]
        ),
        "native_execution_observation_sha256": (
            evidence["native"]["observation_sha256"]
        ),
        "lease_terminal_receipt_sha256": (
            _lease_receipt(evidence["request"])["receipt_sha256"]
        ),
    }
    assert receipt["process"] == {
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


def test_lease_close_receipt_has_exact_lifecycle_facts(
    evidence: Mapping[str, Any],
) -> None:
    receipt = _receipt(evidence)

    assert receipt["checkpoint"] == {
        "worker_result_reports_checkpoint_remeasured": True,
        "worker_result_reports_checkpoint_deserialized": False,
        "parent_post_core_remeasurement_attempted": True,
        "parent_post_core_integrity_matched": True,
        "lease_bridge_finish_completed": True,
        "parent_reservation_release_remeasurement_attempted": True,
        "parent_reservation_release_integrity_matched": True,
        "fd5_reservation_release_completed": True,
        "parent_checkpoint_lease_close_remeasurement_attempted": True,
        "parent_checkpoint_lease_close_integrity_matched": False,
        "exact_checkpoint_bytes_executed_proven": False,
        "deserialization_absence_at_exec_proven": False,
    }
    assert plain(receipt["limitations"]) == [
        "child_checkpoint_hash_is_worker_report",
        (
            "lease_close_mismatch_not_proof_of_bytes_executed_or_"
            "deserialized"
        ),
        "lease_close_mismatch_does_not_locate_mutation_time",
        "runtime_exec_and_worker_script_path_toctou_not_eliminated",
        (
            "transient_changes_outside_observed_stat_hash_windows_not_"
            "excluded"
        ),
        "deterministic_fixture_only_no_source_audio_or_model",
        "private_transport_files_may_remain_after_failure",
        "no_public_cli_tui_selection_or_publication_route",
        "historical_receipt_is_not_post_close_immutability_proof",
        "descriptor_close_call_success_is_not_post_close_proof",
    ]


def test_lease_close_cleanup_is_single_and_narrow(
    evidence: Mapping[str, Any],
) -> None:
    receipt = _receipt(
        evidence,
        cleanup_stages=("private_root_descriptor_close",),
    )

    assert receipt["status"] == (
        "failed_lease_close_checkpoint_integrity_with_cleanup_failures"
    )
    assert plain(receipt["failure"]["cleanup"]) == [
        {
            "ordinal": 0,
            "stage": "private_root_descriptor_close",
            "reason_code": "private_root_descriptor_close_failed",
        }
    ]
    with pytest.raises(ValueError):
        _receipt(
            evidence,
            cleanup_stages=(
                "private_root_descriptor_close",
                "private_root_descriptor_close",
            ),
        )
    with pytest.raises(ValueError):
        _receipt(
            evidence,
            cleanup_stages=("checkpoint_lease_close",),
        )


@pytest.mark.parametrize(
    "reasons",
    (
        (),
        (
            "checkpoint_byte_count_changed",
            "checkpoint_hash_changed",
        ),
        ("checkpoint_descriptor_ownership_lost",),
        ("checkpoint_descriptor_became_inheritable",),
        ("checkpoint_descriptor_remeasurement_failed",),
        ("lease_authority_binding_invalid",),
    ),
)
def test_lease_close_rejects_non_narrow_integrity_reasons(
    reasons: tuple[str, ...],
    evidence: Mapping[str, Any],
) -> None:
    with pytest.raises(ValueError):
        _receipt(evidence, reasons=reasons)


def test_lease_close_rejects_wrong_lease_outcomes(
    evidence: Mapping[str, Any],
) -> None:
    wrong_leases = (
        _lease_receipt(
            evidence["request"],
            status="integrity_and_cleanup_failed",
            cleanup_status="close_unconfirmed",
            cleanup_reasons=("checkpoint_descriptor_close_failed",),
        ),
        _lease_receipt(
            evidence["request"],
            status="closed",
            integrity_status="verified_before_close_attempt",
            reasons=(),
        ),
        _lease_receipt(
            evidence["request"],
            status="cleanup_failed",
            integrity_status="verified_before_close_attempt",
            reasons=(),
            cleanup_status="close_unconfirmed",
            cleanup_reasons=("checkpoint_descriptor_close_failed",),
        ),
    )

    for lease in wrong_leases:
        with pytest.raises(ValueError):
            _receipt(evidence, lease=lease)


def test_lease_close_rejects_cross_bound_native_and_lease(
    evidence: Mapping[str, Any],
    tmp_path: Path,
) -> None:
    second_root = tmp_path / "second"
    second_root.mkdir()
    (
        second_request,
        _historical,
        _launch_v1,
        _launch_v2,
        second_launch_v3,
        second_result,
    ) = _execution_records(second_root)
    wrong_native = _native_observation(
        plan_sha256=second_launch_v3["plan_sha256"],
        result_sha256=second_result["result_sha256"],
    )

    with pytest.raises(ValueError):
        _receipt(evidence, native=wrong_native)
    with pytest.raises(ValueError):
        _receipt(
            evidence,
            lease=_lease_receipt(second_request),
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("parent_post_core_integrity_matched", False),
        ("lease_bridge_finish_completed", False),
        ("parent_reservation_release_integrity_matched", False),
        ("fd5_reservation_release_completed", False),
        ("parent_checkpoint_lease_close_remeasurement_attempted", False),
        ("parent_checkpoint_lease_close_integrity_matched", True),
        ("exact_checkpoint_bytes_executed_proven", True),
    ),
)
def test_lease_close_rejects_rehashed_lifecycle_tampering(
    field: str,
    replacement: bool,
    evidence: Mapping[str, Any],
) -> None:
    receipt = _receipt(evidence)
    document = plain(receipt)
    document["checkpoint"][field] = replacement
    document.pop("receipt_sha256")
    document["receipt_sha256"] = canonical_sha256(document)
    forged = records._wrapper(deep_freeze(document))

    with pytest.raises(ValueError):
        records._validate_lease_close_checkpoint_failed_terminal_receipt(
            forged
        )


def test_lease_close_rejects_rehashed_status_and_permission_tampering(
    evidence: Mapping[str, Any],
) -> None:
    for mutate in (
        lambda document: document["failure"]["primary"].__setitem__(
            "stage",
            "checkpoint_lease_close",
        ),
        lambda document: document["permissions"].__setitem__(
            "publication_permitted",
            True,
        ),
        lambda document: document["outputs"].__setitem__(
            "materialization_started",
            True,
        ),
    ):
        document = plain(_receipt(evidence))
        mutate(document)
        document.pop("receipt_sha256")
        document["receipt_sha256"] = canonical_sha256(document)
        forged = records._wrapper(deep_freeze(document))
        with pytest.raises(ValueError):
            records._validate_lease_close_checkpoint_failed_terminal_receipt(
                forged
            )


def test_lease_close_receipt_type_is_not_substitutable(
    evidence: Mapping[str, Any],
) -> None:
    earlier_receipts = (
        _post_core_receipt(evidence),
        _release_receipt(evidence),
    )

    for earlier in earlier_receipts:
        with pytest.raises(ValueError):
            records._validate_lease_close_checkpoint_failed_terminal_receipt(
                earlier
            )
