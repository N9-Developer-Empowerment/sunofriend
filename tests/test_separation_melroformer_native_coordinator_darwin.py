from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

import pytest

from sunofriend import _separation_melroformer_native_coordinator_darwin as coordinator
from sunofriend import _separation_melroformer_native_failure_records as failures
from sunofriend._separation_melroformer_native_transport import (
    _build_private_melroformer_native_request,
)
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _request(staging: Path):
    return _build_private_melroformer_native_request(
        run_nonce=_digest("fixed-coordinator-run"),
        paths={
            "repository_root": str(staging.parent / "repository"),
            "source_root": str(staging.parent / "source"),
            "checkpoint_path": str(staging.parent / "checkpoint.safetensors"),
            "companion_root": str(staging.parent / "companions"),
            "authorisation_report_path": str(staging.parent / "authorisation.json"),
            "staging_directory": str(staging),
        },
        identities={
            "worker_source_sha256": _digest("worker"),
            "checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
            "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
            "authorisation_report_sha256": _digest("authorisation"),
            "source_manifest_sha256": _digest("source"),
            "companion_manifest_sha256": _digest("companions"),
        },
        device="cpu",
    )


def _clean_terminal() -> dict[str, Any]:
    return {
        "wait": {
            "kind": "exited",
            "exit_code": 0,
            "signal": None,
            "core_dumped": False,
        },
        "timed_out": False,
        "term_sent": False,
        "kill_sent": False,
        "leader_exit_observed": True,
        "leader_reaped": True,
        "group_empty": True,
        "ownership_released": True,
        "ownership_lost": False,
    }


def _failed_terminal() -> dict[str, Any]:
    value = _clean_terminal()
    value["wait"]["exit_code"] = 9
    value["timed_out"] = True
    value["term_sent"] = True
    return value


class _Broker:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.consumed = False

    def finish(self, *, native_owner: Any):
        del native_owner
        self.calls.append("network_finish")
        self.consumed = True
        return {"evidence_sha256": _digest("network")}

    def abort(self) -> None:
        self.calls.append("network_abort")
        self.consumed = True


class _Owner:
    start_state = "started_owned"
    leader_exit_observed = False
    leader_reaped = False
    group_empty = False
    ownership_released = False
    ownership_lost = False

    def __init__(self, calls: list[str], *, fail_process_image: bool = False) -> None:
        self.calls = calls
        self.fail_process_image = fail_process_image

    def observe_owned_process_image(self, *_arguments: Any):
        self.calls.append("process_image")
        if self.fail_process_image:
            raise RuntimeError("substituted process-image failure")
        return {
            "kernel_cdhash": "c" * 40,
            "path_state": "matched_expected_process_image",
        }


class _ReceiptError(RuntimeError):
    def __init__(self, receipt: Mapping[str, Any]) -> None:
        super().__init__("substituted terminal receipt failure")
        self.receipt = receipt


def _install_fixed_substitutions(
    monkeypatch: pytest.MonkeyPatch,
    *,
    request,
    calls: list[str],
    fail_process_image: bool = False,
    no_start: bool = False,
    no_start_cleanup_stages: tuple[str, ...] = (),
    unproven_start: bool = False,
    release_failure: bool = False,
    handshake_abort_failure: bool = False,
    lease_close_failure: bool = False,
) -> tuple[Any, Any, Any, Any, Any]:
    owner_type = type("_OwnedSpawnChild", (_Owner,), {})
    owner = owner_type(calls, fail_process_image=fail_process_image)
    native_session = object()
    lease = object()
    reservation = object()
    worker_request = object()
    session_observation = {"observation_sha256": _digest("session")}
    state = SimpleNamespace(
        runtime_launcher_path=Path("/fixed/runtime-env/bin/python"),
        runtime_environment_root=Path("/fixed/runtime-env"),
        base_runtime_root=Path("/fixed/base-runtime"),
        owner_type=owner_type,
    )
    binding = SimpleNamespace(
        runtime_launcher_path=Path("/fixed/runtime-env/bin/python"),
        process_image_path=Path("/fixed/runtime/Python"),
        process_image_cdhash="c" * 40,
    )
    handshake = SimpleNamespace(
        ready_write_fd=61,
        release_read_fd=62,
    )

    monkeypatch.setattr(coordinator.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        coordinator._session,
        "_validate_verified_private_melroformer_native_session_observation",
        lambda trusted, value: value,
    )
    monkeypatch.setattr(
        coordinator._session,
        "_known_session",
        lambda trusted: (trusted, state),
    )
    def prepare_process_image(**kwargs):
        assert kwargs == {"runtime_path": state.runtime_launcher_path}
        calls.append("process_prepare")
        return binding

    monkeypatch.setattr(
        coordinator._process_image,
        "_prepare_runtime_process_image_binding",
        prepare_process_image,
    )
    monkeypatch.setattr(
        coordinator._network_observer,
        "_prepare_owner_bound_network_observer",
        lambda: calls.append("network_prepare") or _Broker(calls),
    )
    monkeypatch.setattr(
        coordinator._ready_handshake,
        "_prepare_worker_ready_handshake",
        lambda: calls.append("handshake_prepare") or handshake,
    )
    def start(*args, **kwargs):
        del args, kwargs
        calls.append("start")
        if no_start:
            raise coordinator._session._PrivateMelroformerNativeNoStart()
        if unproven_start:
            raise RuntimeError("substituted unproven start")
        return owner

    monkeypatch.setattr(
        coordinator._lease,
        "_start_reserved_private_melroformer_native_worker_darwin",
        start,
    )
    monkeypatch.setattr(
        coordinator._session,
        "_known_started_private_melroformer_native_owner",
        lambda *args: calls.append("known_owner") or owner,
    )
    monkeypatch.setattr(
        coordinator._ready_handshake,
        "_read_worker_ready_handshake",
        lambda *args, **kwargs: calls.append("ready") or {"ready": True},
    )
    monkeypatch.setattr(
        coordinator._loaded_images,
        "_enumerate_owned_executable_regions",
        lambda value: calls.append("snapshot") or ("region",),
    )
    monkeypatch.setattr(coordinator.time, "sleep", lambda _value: None)
    monkeypatch.setattr(
        coordinator._loaded_images,
        "_snapshot_key",
        lambda value: tuple(value),
    )
    monkeypatch.setattr(
        coordinator._loaded_images,
        "_measure_mapped_files",
        lambda *args, **kwargs: calls.append("measure_mapped") or ({"mapped": True},),
    )
    monkeypatch.setattr(
        coordinator._ready_handshake,
        "_release_worker_ready_handshake",
        lambda value: calls.append("release"),
    )
    result = {
        "result_sha256": _digest("result"),
        "child_result_sha256": _digest("child"),
        "private_process_identity": {"pid": 101, "pgid": 101},
        "child_result": {"child": True},
    }
    monkeypatch.setattr(
        coordinator,
        "_read_bounded_result_frame",
        lambda *args, **kwargs: calls.append("read_result") or result,
    )

    def supervise(value, *, timeout_seconds):
        calls.append("supervise")
        value.leader_exit_observed = True
        value.leader_reaped = True
        value.group_empty = True
        value.ownership_released = True
        return _failed_terminal() if fail_process_image else _clean_terminal()

    monkeypatch.setattr(coordinator, "_supervise_owner", supervise)
    monkeypatch.setattr(
        coordinator,
        "_require_successful_terminal",
        lambda value: calls.append("terminal_checked"),
    )
    monkeypatch.setattr(
        coordinator._process_image,
        "_complete_runtime_process_image_binding",
        lambda **kwargs: calls.append("process_complete")
        or {"evidence_sha256": _digest("process")},
    )
    monkeypatch.setattr(
        coordinator._worker_images,
        "_complete_macos_worker_native_image_observation",
        lambda **kwargs: calls.append("images_complete")
        or {"evidence_sha256": _digest("images")},
    )
    def verify_staging(**kwargs):
        assert kwargs["runtime_environment_root"] == (
            state.runtime_environment_root
        )
        assert kwargs["base_runtime_root"] == state.base_runtime_root
        calls.append("staging_verified")
        return {"evidence_sha256": _digest("staging")}

    monkeypatch.setattr(
        coordinator,
        "_verify_private_melroformer_native_worker_staging",
        verify_staging,
    )
    monkeypatch.setattr(
        coordinator._lease,
        "recheck_separation_checkpoint_descriptor_lease",
        lambda value: calls.append("lease_rechecked")
        or {"observation_sha256": _digest("lease-observation")},
    )
    monkeypatch.setattr(
        coordinator,
        "_derive_native_terminal_projection",
        lambda **kwargs: calls.append("identity_consumed")
        or {"projection": "path-free"},
    )
    monkeypatch.setattr(
        coordinator._session,
        "_finish_started_private_melroformer_native_session",
        lambda *args, **kwargs: calls.append("session_success")
        or {"evidence_sha256": _digest("session-terminal")},
    )
    monkeypatch.setattr(
        coordinator._session,
        "_finish_failed_started_private_melroformer_native_session",
        lambda *args, **kwargs: calls.append("session_failure")
        or {"evidence_sha256": _digest("session-failure")},
    )
    monkeypatch.setattr(
        coordinator._session,
        "_finish_no_start_private_melroformer_native_session",
        lambda *args: calls.append("session_no_start")
        or {
            "evidence_sha256": _digest("session-no-start"),
            "native_no_start_stage": "posix_spawn",
            "process_started": False,
            "cleanup": tuple(
                {
                    "ordinal": ordinal,
                    "stage": stage,
                    "reason_code": f"{stage}_failed",
                }
                for ordinal, stage in enumerate(no_start_cleanup_stages)
            ),
            "cleanup_count": len(no_start_cleanup_stages),
        },
    )

    def release(*args):
        del args
        calls.append("lease_released")
        if release_failure:
            raise RuntimeError("substituted release failure")

    monkeypatch.setattr(
        coordinator._lease,
        "_release_separation_checkpoint_descriptor_fd5",
        release,
    )
    def close_lease(value):
        del value
        calls.append("lease_closed")
        receipt = {
            "receipt_sha256": _digest("lease-terminal"),
            "status": "cleanup_failed" if lease_close_failure else "closed",
            "cleanup": {
                "status": "failed" if lease_close_failure else "complete"
            },
        }
        if lease_close_failure:
            raise _ReceiptError(receipt)
        return receipt

    monkeypatch.setattr(
        coordinator._lease,
        "close_separation_checkpoint_descriptor_lease",
        close_lease,
    )
    monkeypatch.setattr(
        coordinator,
        "_close_if_open",
        lambda descriptor: calls.append(f"close:{descriptor}"),
    )
    def abort_handshake(value):
        del value
        calls.append("handshake_abort")
        if handshake_abort_failure:
            raise RuntimeError("substituted handshake-abort failure")

    monkeypatch.setattr(
        coordinator._ready_handshake,
        "_abort_worker_ready_handshake",
        abort_handshake,
    )
    return lease, reservation, worker_request, native_session, session_observation


def test_fixed_coordinator_composes_success_in_one_nonconfigurable_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging = tmp_path / "staging"
    request = _request(staging)
    calls: list[str] = []
    lease, reservation, worker_request, native_session, session_observation = (
        _install_fixed_substitutions(
            monkeypatch,
            request=request,
            calls=calls,
        )
    )

    receipt = coordinator._coordinate_reserved_private_melroformer_native_worker_darwin(
        lease,
        trusted_reservation=reservation,
        trusted_worker_request_v2=worker_request,
        current_lease_observation={"observation_sha256": _digest("lease")},
        trusted_native_session=native_session,
        native_session_observation=session_observation,
        request=request,
        staging_directory=staging,
        request_read_descriptor=51,
        result_write_descriptor=52,
        result_read_descriptor=53,
    )

    assert receipt["status"] == "private_native_worker_complete_and_terminal"
    assert receipt["lifecycle"]["fd4_drained_while_owner_live"] is True
    assert receipt["privacy"] == {
        "raw_pid_retained": False,
        "raw_pgid_retained": False,
        "paths_retained": False,
        "network_destination_retained": False,
        "signal_authority_exposed": False,
    }
    assert all(value is False for value in receipt["permissions"].values())
    assert calls.index("network_prepare") < calls.index("start")
    assert calls.index("release") < calls.index("read_result")
    assert calls.index("read_result") < calls.index("network_finish")
    assert calls.index("network_finish") < calls.index("supervise")
    assert calls.index("supervise") < calls.index("images_complete")
    assert calls.index("images_complete") < calls.index("staging_verified")
    assert calls.index("staging_verified") < calls.index("lease_rechecked")
    assert calls.index("lease_rechecked") < calls.index("identity_consumed")
    assert calls.index("identity_consumed") < calls.index("session_success")
    assert calls.index("session_success") < calls.index("lease_released")
    assert calls.index("lease_released") < calls.index("lease_closed")
    assert str(tmp_path) not in repr(receipt)


def test_fixed_coordinator_exactly_cleans_a_pre_release_observer_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging = tmp_path / "staging"
    request = _request(staging)
    calls: list[str] = []
    lease, reservation, worker_request, native_session, session_observation = (
        _install_fixed_substitutions(
            monkeypatch,
            request=request,
            calls=calls,
            fail_process_image=True,
        )
    )

    with pytest.raises(
        coordinator._PrivateMelroformerNativeCoordinatorFailure
    ) as captured:
        coordinator._coordinate_reserved_private_melroformer_native_worker_darwin(
            lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker_request,
            current_lease_observation={"observation_sha256": _digest("lease")},
            trusted_native_session=native_session,
            native_session_observation=session_observation,
            request=request,
            staging_directory=staging,
            request_read_descriptor=51,
            result_write_descriptor=52,
            result_read_descriptor=53,
        )

    failure = captured.value
    assert str(failure.primary_error) == "substituted process-image failure"
    assert failure.terminal_cleanup_complete is True
    assert failure.failure_kind == "started_exact_reap"
    assert failure.receipt["status"] == "failed_started_exact_reap"
    assert failure.receipt["failure"]["exception_text_recorded"] is False
    assert str(tmp_path) not in repr(failure.receipt)
    assert "release" not in calls
    assert "network_finish" not in calls
    assert calls.index("network_abort") < calls.index("supervise")
    assert calls.index("supervise") < calls.index("session_failure")
    assert calls.index("session_failure") < calls.index("lease_released")
    assert calls.index("lease_released") < calls.index("lease_closed")


def test_fixed_coordinator_seals_a_disjoint_no_start_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging = tmp_path / "staging"
    request = _request(staging)
    calls: list[str] = []
    lease, reservation, worker_request, native_session, session_observation = (
        _install_fixed_substitutions(
            monkeypatch,
            request=request,
            calls=calls,
            no_start=True,
        )
    )

    with pytest.raises(
        coordinator._PrivateMelroformerNativeCoordinatorFailure
    ) as captured:
        coordinator._coordinate_reserved_private_melroformer_native_worker_darwin(
            lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker_request,
            current_lease_observation={"observation_sha256": _digest("lease")},
            trusted_native_session=native_session,
            native_session_observation=session_observation,
            request=request,
            staging_directory=staging,
            request_read_descriptor=51,
            result_write_descriptor=52,
            result_read_descriptor=53,
        )

    failure = captured.value
    assert failure.failure_kind == "no_start"
    assert failure.terminal_cleanup_complete is True
    assert failure.receipt["status"] == "failed_no_start"
    assert failure.receipt["process"]["state"] == "not_started"
    assert failure.receipt["failure"]["native_no_start_stage"] == "posix_spawn"
    assert "supervise" not in calls
    assert calls.index("session_no_start") < calls.index("lease_released")
    assert str(tmp_path) not in repr(failure.receipt)
    with pytest.raises(ValueError, match="started failure receipt type"):
        failures._validate_started_coordinator_failure_receipt(failure.receipt)


def test_fixed_coordinator_preserves_started_failure_with_cleanup_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging = tmp_path / "staging"
    request = _request(staging)
    calls: list[str] = []
    lease, reservation, worker_request, native_session, session_observation = (
        _install_fixed_substitutions(
            monkeypatch,
            request=request,
            calls=calls,
            fail_process_image=True,
            release_failure=True,
        )
    )

    with pytest.raises(
        coordinator._PrivateMelroformerNativeCoordinatorFailure
    ) as captured:
        coordinator._coordinate_reserved_private_melroformer_native_worker_darwin(
            lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker_request,
            current_lease_observation={"observation_sha256": _digest("lease")},
            trusted_native_session=native_session,
            native_session_observation=session_observation,
            request=request,
            staging_directory=staging,
            request_read_descriptor=51,
            result_write_descriptor=52,
            result_read_descriptor=53,
        )

    failure = captured.value
    assert str(failure.primary_error) == "substituted process-image failure"
    assert failure.failure_kind == "started_exact_reap"
    assert failure.terminal_cleanup_complete is True
    assert failure.cleanup_stages == ("fd5_reservation_release",)
    assert failure.receipt["status"] == (
        "failed_started_exact_reap_with_cleanup_failures"
    )
    assert failure.receipt["failure"]["cleanup"] == (
        {
            "ordinal": 0,
            "stage": "fd5_reservation_release",
            "reason_code": "fd5_reservation_release_failed",
        },
    )


def test_fixed_coordinator_preserves_each_no_start_cleanup_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging = tmp_path / "staging"
    request = _request(staging)
    calls: list[str] = []
    lease, reservation, worker_request, native_session, session_observation = (
        _install_fixed_substitutions(
            monkeypatch,
            request=request,
            calls=calls,
            no_start=True,
            no_start_cleanup_stages=(
                "child_transport_descriptor_close",
                "child_transport_descriptor_close",
                "native_admission_finish",
            ),
        )
    )

    with pytest.raises(
        coordinator._PrivateMelroformerNativeCoordinatorFailure
    ) as captured:
        coordinator._coordinate_reserved_private_melroformer_native_worker_darwin(
            lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker_request,
            current_lease_observation={"observation_sha256": _digest("lease")},
            trusted_native_session=native_session,
            native_session_observation=session_observation,
            request=request,
            staging_directory=staging,
            request_read_descriptor=51,
            result_write_descriptor=52,
            result_read_descriptor=53,
        )

    failure = captured.value
    assert failure.failure_kind == "no_start"
    assert failure.terminal_cleanup_complete is False
    assert failure.cleanup_stages == (
        "child_transport_descriptor_close",
        "child_transport_descriptor_close",
        "native_admission_finish",
    )
    assert [
        event["stage"] for event in failure.receipt["failure"]["cleanup"]
    ] == list(failure.cleanup_stages)


def test_fixed_coordinator_labels_cleanup_only_failure_as_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging = tmp_path / "staging"
    request = _request(staging)
    calls: list[str] = []
    lease, reservation, worker_request, native_session, session_observation = (
        _install_fixed_substitutions(
            monkeypatch,
            request=request,
            calls=calls,
            release_failure=True,
        )
    )

    with pytest.raises(
        coordinator._PrivateMelroformerNativeCoordinatorFailure
    ) as captured:
        coordinator._coordinate_reserved_private_melroformer_native_worker_darwin(
            lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker_request,
            current_lease_observation={"observation_sha256": _digest("lease")},
            trusted_native_session=native_session,
            native_session_observation=session_observation,
            request=request,
            staging_directory=staging,
            request_read_descriptor=51,
            result_write_descriptor=52,
            result_read_descriptor=53,
        )

    failure = captured.value
    assert failure.receipt["failure"]["primary_stage"] == "terminal_cleanup"
    assert failure.cleanup_stages == ("fd5_reservation_release",)
    assert failure.receipt["process"]["terminal_kind"] == (
        "normal_exit_after_evidence_failure"
    )


def test_fixed_coordinator_retains_receipt_when_lease_cleanup_is_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging = tmp_path / "staging"
    request = _request(staging)
    calls: list[str] = []
    lease, reservation, worker_request, native_session, session_observation = (
        _install_fixed_substitutions(
            monkeypatch,
            request=request,
            calls=calls,
            fail_process_image=True,
            lease_close_failure=True,
        )
    )

    with pytest.raises(
        coordinator._PrivateMelroformerNativeCoordinatorFailure
    ) as captured:
        coordinator._coordinate_reserved_private_melroformer_native_worker_darwin(
            lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker_request,
            current_lease_observation={"observation_sha256": _digest("lease")},
            trusted_native_session=native_session,
            native_session_observation=session_observation,
            request=request,
            staging_directory=staging,
            request_read_descriptor=51,
            result_write_descriptor=52,
            result_read_descriptor=53,
        )

    failure = captured.value
    assert str(failure.primary_error) == "substituted process-image failure"
    assert failure.terminal_cleanup_complete is False
    assert failure.failure_kind == "started_exact_reap"
    assert failure.cleanup_stages == ("checkpoint_lease_close",)
    assert failure.receipt["status"] == (
        "failed_started_exact_reap_with_cleanup_failures"
    )


def test_fixed_coordinator_keeps_primary_when_handshake_abort_also_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging = tmp_path / "staging"
    request = _request(staging)
    calls: list[str] = []
    lease, reservation, worker_request, native_session, session_observation = (
        _install_fixed_substitutions(
            monkeypatch,
            request=request,
            calls=calls,
            fail_process_image=True,
            handshake_abort_failure=True,
        )
    )

    with pytest.raises(
        coordinator._PrivateMelroformerNativeCoordinatorFailure
    ) as captured:
        coordinator._coordinate_reserved_private_melroformer_native_worker_darwin(
            lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker_request,
            current_lease_observation={"observation_sha256": _digest("lease")},
            trusted_native_session=native_session,
            native_session_observation=session_observation,
            request=request,
            staging_directory=staging,
            request_read_descriptor=51,
            result_write_descriptor=52,
            result_read_descriptor=53,
        )

    failure = captured.value
    assert str(failure.primary_error) == "substituted process-image failure"
    assert failure.cleanup_stages == ("ready_handshake_abort",)
    assert failure.receipt["failure"]["cleanup"][0]["stage"] == (
        "ready_handshake_abort"
    )


def test_fixed_coordinator_gives_unproven_start_no_terminal_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging = tmp_path / "staging"
    request = _request(staging)
    calls: list[str] = []
    lease, reservation, worker_request, native_session, session_observation = (
        _install_fixed_substitutions(
            monkeypatch,
            request=request,
            calls=calls,
            unproven_start=True,
        )
    )

    with pytest.raises(
        coordinator._PrivateMelroformerNativeCoordinatorFailure
    ) as captured:
        coordinator._coordinate_reserved_private_melroformer_native_worker_darwin(
            lease,
            trusted_reservation=reservation,
            trusted_worker_request_v2=worker_request,
            current_lease_observation={"observation_sha256": _digest("lease")},
            trusted_native_session=native_session,
            native_session_observation=session_observation,
            request=request,
            staging_directory=staging,
            request_read_descriptor=51,
            result_write_descriptor=52,
            result_read_descriptor=53,
        )

    failure = captured.value
    assert str(failure.primary_error) == "substituted unproven start"
    assert failure.failure_kind == "unproven"
    assert failure.terminal_cleanup_complete is False
    assert failure.receipt is None
    assert "session_no_start" not in calls
    assert "session_failure" not in calls


def test_fixed_coordinator_has_no_public_or_tui_route() -> None:
    assert coordinator.__all__ == ()
    assert "private-melroformer-native-coordinator" not in PUBLIC_COMMANDS
    assert (
        "private-melroformer-native-coordinator" not in DIRECT_TUI_COMMANDS
    )
