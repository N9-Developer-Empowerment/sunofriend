from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from sunofriend import _separation_melroformer_native_failure_records as records
from sunofriend._separation_checkpoint_canonical import (
    canonical_sha256,
    deep_freeze,
    plain,
)


def _no_start(
    *,
    cleanup_stages: tuple[str, ...] = (),
) -> records._PrivateMelroformerCoordinatorNoStartReceipt:
    return records._build_no_start_coordinator_failure_receipt(
        request_sha256="1" * 64,
        native_session_terminal_sha256="2" * 64,
        checkpoint_lease_terminal_sha256="3" * 64,
        native_no_start_stage="posix_spawn",
        cleanup_stages=cleanup_stages,
    )


def _started(
    *,
    cleanup_stages: tuple[str, ...] = (),
    worker_result_sha256: str | None = "4" * 64,
) -> records._PrivateMelroformerCoordinatorFailedTerminalReceipt:
    return records._build_started_coordinator_failure_receipt(
        request_sha256="1" * 64,
        native_session_terminal_sha256="2" * 64,
        checkpoint_lease_terminal_sha256="3" * 64,
        primary_stage="staging_verification",
        terminal_kind="normal_exit_after_evidence_failure",
        worker_result_sha256=worker_result_sha256,
        cleanup_stages=cleanup_stages,
    )


def test_no_start_receipt_is_path_free_self_hashed_and_inert() -> None:
    receipt = _no_start(
        cleanup_stages=(
            "child_transport_descriptor_close",
            "child_transport_descriptor_close",
            "native_admission_finish",
        )
    )
    document = plain(receipt)
    receipt_sha256 = document.pop("receipt_sha256")

    assert records.__all__ == ()
    assert document["status"] == "failed_no_start_with_cleanup_failures"
    assert document["process"]["state"] == "not_started"
    assert document["process"]["child_created"] is False
    assert document["process"]["wait_attempted"] is False
    assert document["process"]["signal_attempted"] is False
    assert [event["stage"] for event in document["failure"]["cleanup"]] == [
        "child_transport_descriptor_close",
        "child_transport_descriptor_close",
        "native_admission_finish",
    ]
    assert document["failure"]["exception_text_recorded"] is False
    assert all(value is False for value in document["permissions"].values())
    assert receipt_sha256 == canonical_sha256(document)
    assert not any(
        isinstance(item, str)
        and (item.startswith(("/", "~/", "../", "./")) or "://" in item)
        for item in _values(document)
    )


def test_started_receipt_is_path_free_self_hashed_and_binds_result() -> None:
    receipt = _started(cleanup_stages=("fd5_reservation_release",))
    document = plain(receipt)
    receipt_sha256 = document.pop("receipt_sha256")

    assert document["status"] == (
        "failed_started_exact_reap_with_cleanup_failures"
    )
    assert document["process"]["state"] == "started_exact_reaped"
    assert document["process"]["complete_group_drained"] is True
    assert document["process"]["ownership_released"] is True
    assert document["bindings"]["worker_result_sha256"] == "4" * 64
    assert document["outputs"]["worker_result_validated"] is True
    assert document["outputs"]["staging_accepted"] is False
    assert document["failure"]["exception_text_recorded"] is False
    assert receipt_sha256 == canonical_sha256(document)
    assert not any(
        isinstance(item, str)
        and (item.startswith(("/", "~/", "../", "./")) or "://" in item)
        for item in _values(document)
    )


def test_receipt_types_are_not_interchangeable() -> None:
    with pytest.raises(ValueError, match="started failure receipt type"):
        records._validate_started_coordinator_failure_receipt(_no_start())
    with pytest.raises(ValueError, match="no-start receipt type"):
        records._validate_no_start_coordinator_failure_receipt(_started())


@pytest.mark.parametrize(
    "mutation",
    (
        "process",
        "permission",
        "limitation",
        "cleanup",
        "binding",
        "exception",
    ),
)
def test_no_start_receipt_rejects_rehashed_tampering(mutation: str) -> None:
    document = plain(_no_start())
    document.pop("receipt_sha256")
    if mutation == "process":
        document["process"]["child_created"] = True
    elif mutation == "permission":
        document["permissions"]["publication_permitted"] = True
    elif mutation == "limitation":
        document["limitations"].pop()
    elif mutation == "cleanup":
        document["failure"]["cleanup"] = [
            {
                "ordinal": 1,
                "stage": "network_observer",
                "reason_code": "network_observer_failed",
            }
        ]
        document["failure"]["cleanup_count"] = 1
        document["status"] = "failed_no_start_with_cleanup_failures"
    elif mutation == "binding":
        document["bindings"]["request_sha256"] = "f" * 63
    else:
        document["failure"]["exception_text_recorded"] = True
    document["receipt_sha256"] = canonical_sha256(document)
    tampered = records._wrap_no_start(deep_freeze(document))

    with pytest.raises(ValueError):
        records._validate_no_start_coordinator_failure_receipt(tampered)


@pytest.mark.parametrize(
    "mutation",
    ("stage", "process", "output", "cleanup", "binding"),
)
def test_started_receipt_rejects_rehashed_tampering(mutation: str) -> None:
    document = plain(_started())
    document.pop("receipt_sha256")
    if mutation == "stage":
        document["failure"]["primary_stage"] = "native_no_start"
    elif mutation == "process":
        document["process"]["ownership_lost"] = True
    elif mutation == "output":
        document["outputs"]["staging_accepted"] = True
    elif mutation == "cleanup":
        document["failure"]["cleanup"] = [
            {
                "ordinal": 0,
                "stage": "unknown",
                "reason_code": "unknown_failed",
            }
        ]
        document["failure"]["cleanup_count"] = 1
        document["status"] = (
            "failed_started_exact_reap_with_cleanup_failures"
        )
    else:
        document["bindings"]["worker_result_sha256"] = "f" * 63
    document["receipt_sha256"] = canonical_sha256(document)
    tampered = records._wrap_started(deep_freeze(document))

    with pytest.raises(ValueError):
        records._validate_started_coordinator_failure_receipt(tampered)


def test_builders_reject_unknown_stages_and_invalid_hashes() -> None:
    with pytest.raises(ValueError, match="cleanup stages"):
        _no_start(cleanup_stages=("private/path",))
    with pytest.raises(ValueError, match="failure evidence"):
        records._build_started_coordinator_failure_receipt(
            request_sha256="1" * 64,
            native_session_terminal_sha256="2" * 64,
            checkpoint_lease_terminal_sha256="3" * 64,
            primary_stage="native_start",
            terminal_kind="failed_exit_exact_reap",
            worker_result_sha256=None,
            cleanup_stages=(),
        )
    with pytest.raises(ValueError, match="request hash"):
        records._build_no_start_coordinator_failure_receipt(
            request_sha256="1" * 63,
            native_session_terminal_sha256="2" * 64,
            checkpoint_lease_terminal_sha256="3" * 64,
            native_no_start_stage="posix_spawn",
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
