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

    def resource_observation(self):
        self.calls.append("native_resources")
        return {
            "peak_resident_set_bytes": 3_100_000_000,
            "lifetime_max_phys_footprint_bytes": 3_300_000_000,
            "lifetime_max_neural_footprint_bytes": 0,
            "rss_source": "wait4_ru_maxrss_darwin_bytes",
            "unified_memory_source": (
                "proc_pid_rusage_v6_lifetime_max_phys_footprint"
            ),
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
) -> tuple[Any, Any, Any, Any]:
    owner_type = type("_OwnedSpawnChild", (_Owner,), {})
    owner = owner_type(calls, fail_process_image=fail_process_image)
    native_session = object()
    lease = object()
    reservation = object()
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
    child_result = {
        "schema": "sunofriend.private-melroformer-native-worker-child.v1",
        "status": "real_worker_complete_parent_verification_required",
        "model": {
            "authorisation": {"frames": 661_500},
            "bridge": {"candidate_id": request["candidate_id"]},
            "inference": {
                "status": "private_real_single_chunk_validated_not_persisted",
                "geometry": {
                    "sample_rate": 44_100,
                    "channels": 2,
                    "frames": 661_500,
                    "duration_seconds": 15.0,
                    "maximum_frames": 661_500,
                },
                "transport": {
                    "chunk_count": 1,
                    "chunk_frames": 661_500,
                    "hop_frames": 661_500,
                    "overlap_frames": 0,
                    "weighted_overlap_add": False,
                },
                "measurement": {
                    "device": "cpu",
                    "inference_seconds": 8.25,
                    "peak_memory_bytes": 2_500_000_000,
                },
            },
        },
    }
    result = {
        "result_sha256": _digest("result"),
        "child_result_sha256": hashlib.sha256(
            coordinator._canonical_json(child_result)
        ).hexdigest(),
        "private_process_identity": {"pid": 101, "pgid": 101},
        "child_result": child_result,
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
        "_recheck_private_melroformer_checkpoint_lease",
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
        "_release_private_melroformer_checkpoint_fd5",
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
        "_close_private_melroformer_checkpoint_lease",
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
    return lease, reservation, native_session, session_observation


def test_fixed_coordinator_composes_success_in_one_nonconfigurable_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging = tmp_path / "staging"
    request = _request(staging)
    calls: list[str] = []
    lease, reservation, native_session, session_observation = (
        _install_fixed_substitutions(
            monkeypatch,
            request=request,
            calls=calls,
        )
    )

    receipt = coordinator._coordinate_reserved_private_melroformer_native_worker_darwin(
        lease,
        trusted_reservation=reservation,
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
    resources = receipt["worker_resource_projection"]
    assert resources["device"] == "cpu"
    assert resources["frames"] == 661_500
    assert resources["chunk_count"] == 1
    assert resources["inference_seconds"] == 8.25
    assert resources["peak_mlx_allocator_memory_bytes"] == 2_500_000_000
    assert resources["semantics"] == {
        "inference_time_scope": "worker_model_calls_only",
        "memory_scope": "mlx_allocator_peak_not_process_rss",
        "benchmark": False,
    }
    assert resources["bindings"]["worker_result_sha256"] == _digest("result")
    native_resources = receipt["native_process_resource_projection"]
    assert native_resources["peak_process_rss_bytes"] == 3_100_000_000
    assert native_resources["peak_total_unified_memory_bytes"] == 3_300_000_000
    assert native_resources["semantics"]["pid_retained"] is False
    assert calls.index("network_prepare") < calls.index("start")
    assert calls.index("release") < calls.index("read_result")
    assert calls.index("read_result") < calls.index("network_finish")
    assert calls.index("network_finish") < calls.index("supervise")
    assert calls.index("supervise") < calls.index("native_resources")
    assert calls.index("supervise") < calls.index("images_complete")
    assert calls.index("images_complete") < calls.index("staging_verified")
    assert calls.index("staging_verified") < calls.index("lease_rechecked")
    assert calls.index("lease_rechecked") < calls.index("identity_consumed")
    assert calls.index("identity_consumed") < calls.index("session_success")
    assert calls.index("session_success") < calls.index("lease_released")
    assert calls.index("lease_released") < calls.index("lease_closed")
    assert str(tmp_path) not in repr(receipt)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("inference_seconds", 0.0),
        ("inference_seconds", float("nan")),
        ("peak_memory_bytes", 0),
    ],
)
def test_worker_resource_projection_rejects_invalid_measurements(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    request = _request(tmp_path / "staging")
    child = {
        "schema": "sunofriend.private-melroformer-native-worker-child.v1",
        "status": "real_worker_complete_parent_verification_required",
        "model": {
            "authorisation": {},
            "bridge": {},
            "inference": {
                "status": "private_real_single_chunk_validated_not_persisted",
                "geometry": {
                    "sample_rate": 44_100,
                    "channels": 2,
                    "frames": 661_500,
                    "duration_seconds": 15.0,
                    "maximum_frames": 661_500,
                },
                "transport": {
                    "chunk_count": 1,
                    "chunk_frames": 661_500,
                    "hop_frames": 661_500,
                    "overlap_frames": 0,
                    "weighted_overlap_add": False,
                },
                "measurement": {
                    "device": "cpu",
                    "inference_seconds": 8.25,
                    "peak_memory_bytes": 2_500_000_000,
                    field: value,
                },
            },
        },
    }
    try:
        child_sha256 = hashlib.sha256(
            coordinator._canonical_json(child)
        ).hexdigest()
    except ValueError:
        child_sha256 = _digest("non-json-child")
    result = {
        "result_sha256": _digest("result"),
        "child_result_sha256": child_sha256,
        "child_result": child,
    }

    with pytest.raises(ValueError, match="resource observation differs"):
        coordinator._project_worker_resource_observation(
            request=request,
            result=result,
        )


def test_fixed_coordinator_exactly_cleans_a_pre_release_observer_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging = tmp_path / "staging"
    request = _request(staging)
    calls: list[str] = []
    lease, reservation, native_session, session_observation = (
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
    lease, reservation, native_session, session_observation = (
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
    lease, reservation, native_session, session_observation = (
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
    lease, reservation, native_session, session_observation = (
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
    lease, reservation, native_session, session_observation = (
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
    lease, reservation, native_session, session_observation = (
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
    lease, reservation, native_session, session_observation = (
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
    lease, reservation, native_session, session_observation = (
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
