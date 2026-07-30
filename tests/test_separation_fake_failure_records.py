from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from sunofriend import _separation_fake_failure_records as records
from sunofriend import _separation_native_failure_records as native_records
from sunofriend._separation_checkpoint_canonical import (
    canonical_sha256,
    deep_freeze,
    plain,
)


def _native_observation() -> (
    native_records._VerifiedNativeLauncherFailedTerminalObservation
):
    return native_records._build_exact_reap_failure_observation(
        native_session_observation_sha256="1" * 64,
        fake_launch_plan_v3_sha256="4" * 64,
        failure_stage="result_decode",
        wait={
            "kind": "exited",
            "exit_code": 0,
            "signal": None,
            "core_dumped": False,
        },
        timed_out=False,
        term_sent=False,
        kill_sent=False,
        fake_worker_result_v2_sha256=None,
        worker_reported_identity_matched=None,
        post_reap_remeasurement_complete=True,
    )


def _receipt(
    *,
    cleanup_stages: tuple[str, ...] = (),
) -> records._SeparationFakeExecutionFailedTerminalReceipt:
    return records._build_exact_reap_failed_terminal_receipt(
        run_nonce="a" * 64,
        fake_worker_request_v1_sha256="b" * 64,
        fake_launch_plan_v1_sha256="c" * 64,
        blocked_fake_launch_plan_v2_sha256="d" * 64,
        fake_launch_plan_v3_sha256="4" * 64,
        native_failure_observation=_native_observation(),
        lease_terminal_receipt_sha256="e" * 64,
        lease_status="closed",
        lease_integrity_status="verified_before_close_attempt",
        lease_cleanup_status="complete",
        cleanup_stages=cleanup_stages,
    )


def test_failed_terminal_receipt_is_path_free_self_hashed_and_inert() -> None:
    receipt = _receipt()
    document = plain(receipt)
    receipt_sha256 = document.pop("receipt_sha256")

    assert records.__all__ == ()
    assert document["status"] == "failed_terminal"
    assert document["process"]["state"] == "started_exact_reaped"
    assert document["lease"]["status"] == "closed"
    assert document["failure"]["cleanup"] == []
    assert document["outputs"]["materialization_started"] is False
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


def test_cleanup_events_preserve_order_and_duplicates() -> None:
    receipt = _receipt(
        cleanup_stages=(
            "native_final_supervision",
            "lease_bridge_finish",
            "lease_bridge_finish",
            "private_root_descriptor_close",
        )
    )

    assert receipt["status"] == "failed_terminal_with_cleanup_failures"
    assert [event["stage"] for event in receipt["failure"]["cleanup"]] == [
        "native_final_supervision",
        "lease_bridge_finish",
        "lease_bridge_finish",
        "private_root_descriptor_close",
    ]
    assert receipt["failure"]["cleanup_count"] == 4


def test_failed_terminal_rejects_unproven_process_and_inconsistent_lease() -> (
    None
):
    receipt = _receipt()
    document = plain(receipt)
    process = dict(document["process"])
    process["leader_reaped"] = False
    document["process"] = process
    document.pop("receipt_sha256")
    document["receipt_sha256"] = canonical_sha256(document)
    tampered = records._wrapper(deep_freeze(document))

    with pytest.raises(ValueError, match="process evidence"):
        records._validate_failed_terminal_receipt(tampered)
    with pytest.raises(ValueError, match="lease status"):
        records._build_exact_reap_failed_terminal_receipt(
            run_nonce="a" * 64,
            fake_worker_request_v1_sha256="b" * 64,
            fake_launch_plan_v1_sha256="c" * 64,
            blocked_fake_launch_plan_v2_sha256="d" * 64,
            fake_launch_plan_v3_sha256="4" * 64,
            native_failure_observation=_native_observation(),
            lease_terminal_receipt_sha256="e" * 64,
            lease_status="closed",
            lease_integrity_status="failed",
            lease_cleanup_status="complete",
            cleanup_stages=(),
        )


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
