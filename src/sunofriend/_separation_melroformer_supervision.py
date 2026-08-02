"""Path-free supervision evidence for one private Kim Vocal 2 worker.

This module records a deliberately narrow boundary: the private launcher began
with only the standard descriptors, the real worker reported its main-thread
signal state after CPython startup, and the parent synchronously waited for the
exact child to exit normally.  It is development evidence, not execution
authority or a public separation route.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
from typing import Any, Mapping, Sequence

from .separation_contract import _canonical_json_bytes, _freeze_json


SCHEMA = "sunofriend.private-melroformer-worker-supervision.v1"
POLICY_ID = "private-melroformer-real-worker-supervision-v1"
NATIVE_TERMINAL_PROJECTION_SCHEMA = (
    "sunofriend.private-melroformer-native-terminal-projection.v1"
)
NATIVE_PLAN_SCHEMA = "sunofriend.private-melroformer-native-supervision-plan.v1"
NATIVE_PLAN_POLICY_ID = "private-melroformer-native-supervision-plan-v1"
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_OBSERVED_SIGNAL_NAMES = (
    "SIGHUP",
    "SIGINT",
    "SIGQUIT",
    "SIGPIPE",
    "SIGTERM",
    "SIGCHLD",
    "SIGXFSZ",
)


def _observe_post_cpython_signal_state() -> Mapping[str, Any]:
    """Observe the current main thread without claiming the pre-exec instant."""

    blocked = signal.pthread_sigmask(signal.SIG_BLOCK, [])
    if blocked is None:
        raise RuntimeError("MelRoFormer worker signal-mask observation failed")
    blocked_names = sorted(signal.Signals(number).name for number in blocked)
    handlers = {
        name: _signal_handler_name(signal.getsignal(getattr(signal, name)))
        for name in _OBSERVED_SIGNAL_NAMES
    }
    report = {
        "observation_point": "real_worker_main_after_cpython_startup",
        "main_thread_mask_empty": blocked_names == [],
        "blocked_signal_names": blocked_names,
        "handlers": handlers,
        "termination_signals_default": all(
            handlers[name] == "default"
            for name in ("SIGHUP", "SIGQUIT", "SIGTERM")
        ),
        "sigchld_default": handlers["SIGCHLD"] == "default",
        "cpython_runtime_adjustments_observed": (
            handlers["SIGINT"] == "python_default_int_handler"
            and handlers["SIGPIPE"] == "ignored"
            and handlers["SIGXFSZ"] == "ignored"
        ),
        "pre_exec_signal_state_reconstructed": False,
    }
    return _validate_post_cpython_signal_state(report)


def _validate_post_cpython_signal_state(value: Any) -> Mapping[str, Any]:
    report = _plain(value)
    if report != _expected_post_cpython_signal_state():
        raise ValueError("MelRoFormer worker post-CPython signal state differs")
    return _freeze_json(report)


def _build_real_worker_supervision_observation(
    *,
    worker_signal_state: Mapping[str, Any],
    outer_open_descriptors: Sequence[int],
    child_returncode: int,
) -> Mapping[str, Any]:
    """Bind the worker report to one completed synchronous parent wait."""

    signal_state = _validate_post_cpython_signal_state(worker_signal_state)
    descriptors = list(outer_open_descriptors)
    if descriptors != [0, 1, 2]:
        raise ValueError(
            "MelRoFormer outer supervisor inherited unexpected descriptors"
        )
    if type(child_returncode) is not int or child_returncode != 0:
        raise ValueError("MelRoFormer supervised worker did not exit normally")
    payload = {
        "schema": SCHEMA,
        "policy_id": POLICY_ID,
        "status": "real_worker_supervision_bound_complete",
        "outer_supervisor": {
            "observation_point": (
                "private_launcher_main_before_sunofriend_execution_setup"
            ),
            "open_descriptors": descriptors,
            "only_standard_descriptors_open": True,
            "raw_descriptor_identities_retained": False,
        },
        "worker_signal_state": _plain(signal_state),
        "terminal": {
            "parent_wait_contract": "subprocess_popen_communicate_exact_child",
            "exact_child_reaped": True,
            "normal_zero_exit": True,
            "exit_code": 0,
            "signal_termination_observed": False,
            "raw_pid_retained": False,
            "raw_pgid_retained": False,
            "signal_authority_exposed": False,
            "process_group_supervision_bound": False,
            "descendant_supervision_bound": False,
        },
        "scope": {
            "real_model_worker_observed": True,
            "worker_signal_report_bound": True,
            "outer_descriptor_boundary_bound": True,
            "pre_exec_signal_state_reconstructed": False,
            "product_authority_granted": False,
        },
        "limitations": [
            "post_cpython_state_does_not_reconstruct_pre_exec_signal_instant",
            "subprocess_wait_is_not_native_process_group_supervision",
            "worker_descendants_are_denied_by_sandbox_but_not_supervisor_owned",
            "provider_and_runtime_path_to_execution_toctou_remain_open",
            "no_public_cli_tui_simple_studio_or_source_graph_route",
        ],
    }
    return _validate_real_worker_supervision_observation(
        {
            **payload,
            "observation_sha256": hashlib.sha256(
                _canonical_json_bytes(payload)
            ).hexdigest(),
        }
    )


def _validate_native_terminal_projection(value: Any) -> Mapping[str, Any]:
    """Validate the future native-owner projection without granting authority.

    The current Kim route cannot produce this record.  A future bridge must
    derive it from the exact nonconstructible native owner after the complete
    private process group has drained; accepting this shape is not itself proof
    that such an owner existed.
    """

    projection = _plain(value)
    if not isinstance(projection, dict) or set(projection) != {
        "schema",
        "native_session_observation_sha256",
        "native_execution_observation_sha256",
        "worker_result_sha256",
        "start_state",
        "wait",
        "timed_out",
        "term_sent",
        "kill_sent",
        "worker_reported_identity_matched",
        "leader_exit_observed",
        "leader_reaped",
        "group_empty",
        "ownership_released",
        "ownership_lost",
        "raw_pid_retained",
        "raw_pgid_retained",
        "signal_authority_exposed",
    }:
        raise ValueError("native real-worker terminal projection fields differ")
    if projection["schema"] != NATIVE_TERMINAL_PROJECTION_SCHEMA:
        raise ValueError("native real-worker terminal projection schema differs")
    for key in (
        "native_session_observation_sha256",
        "native_execution_observation_sha256",
        "worker_result_sha256",
    ):
        digest = projection[key]
        if not isinstance(digest, str) or _SHA_RE.fullmatch(digest) is None:
            raise ValueError("native real-worker terminal projection hash differs")
    if projection["start_state"] != "started_owned":
        raise ValueError("native real-worker was not started with exact ownership")
    if projection["wait"] != {
        "kind": "exited",
        "exit_code": 0,
        "signal": None,
        "core_dumped": False,
    }:
        raise ValueError("native real-worker terminal wait evidence differs")
    required_true = (
        "worker_reported_identity_matched",
        "leader_exit_observed",
        "leader_reaped",
        "group_empty",
        "ownership_released",
    )
    if any(projection[key] is not True for key in required_true):
        raise ValueError("native real-worker terminal ownership is incomplete")
    required_false = (
        "timed_out",
        "term_sent",
        "kill_sent",
        "ownership_lost",
        "raw_pid_retained",
        "raw_pgid_retained",
        "signal_authority_exposed",
    )
    if any(projection[key] is not False for key in required_false):
        raise ValueError("native real-worker terminal safety boundary differs")
    return _freeze_json(projection)


def _derive_model_free_native_terminal_projection(
    *,
    native_owner: Any,
    expected_owner_type: type[Any],
    native_session_observation_sha256: str,
    native_execution_observation_sha256: str,
    worker_result_sha256: str,
    worker_reported_pid: int,
    worker_reported_pgid: int,
) -> Mapping[str, Any]:
    """Project one completed fixed-worker owner without exporting authority.

    This is deliberately narrower than the future Kim bridge.  It accepts the
    exact nonconstructible owner type supplied by the freshly loaded private
    native extension, asks that owner to match the worker's private result
    identity, and reads the cached wait and complete group-lifetime state only
    after exact reap.  Raw PID/PGID values are consumed for the boolean match
    and are never included in the returned projection.
    """

    if (
        not isinstance(expected_owner_type, type)
        or type(native_owner) is not expected_owner_type
        or getattr(expected_owner_type, "__name__", None) != "_OwnedSpawnChild"
    ):
        raise TypeError("model-free terminal projection requires the exact owner")
    if hasattr(native_owner, "pid") or hasattr(native_owner, "__dict__"):
        raise TypeError("model-free terminal projection owner exposes authority")
    for digest in (
        native_session_observation_sha256,
        native_execution_observation_sha256,
        worker_result_sha256,
    ):
        if not isinstance(digest, str) or _SHA_RE.fullmatch(digest) is None:
            raise ValueError("model-free terminal projection hash differs")
    if (
        type(worker_reported_pid) is not int
        or worker_reported_pid <= 0
        or type(worker_reported_pgid) is not int
        or worker_reported_pgid <= 0
    ):
        raise ValueError("model-free worker identity report is invalid")
    matched = native_owner.matches_pid_and_pgid(
        worker_reported_pid,
        worker_reported_pgid,
    )
    if matched is not True:
        raise ValueError("model-free worker identity does not match its owner")
    raw_wait_status = native_owner.wait_nohang()
    if type(raw_wait_status) is not int or not os.WIFEXITED(raw_wait_status):
        raise ValueError("model-free native owner lacks a normal cached wait")
    if os.WEXITSTATUS(raw_wait_status) != 0:
        raise ValueError("model-free fixed worker did not exit successfully")
    projection = {
        "schema": NATIVE_TERMINAL_PROJECTION_SCHEMA,
        "native_session_observation_sha256": (
            native_session_observation_sha256
        ),
        "native_execution_observation_sha256": (
            native_execution_observation_sha256
        ),
        "worker_result_sha256": worker_result_sha256,
        "start_state": native_owner.start_state,
        "wait": {
            "kind": "exited",
            "exit_code": os.WEXITSTATUS(raw_wait_status),
            "signal": None,
            "core_dumped": False,
        },
        "timed_out": False,
        "term_sent": False,
        "kill_sent": False,
        "worker_reported_identity_matched": matched,
        "leader_exit_observed": native_owner.leader_exit_observed,
        "leader_reaped": native_owner.leader_reaped,
        "group_empty": native_owner.group_empty,
        "ownership_released": native_owner.ownership_released,
        "ownership_lost": native_owner.ownership_lost,
        "raw_pid_retained": False,
        "raw_pgid_retained": False,
        "signal_authority_exposed": False,
    }
    return _validate_native_terminal_projection(projection)


def _build_native_real_worker_supervision_plan() -> Mapping[str, Any]:
    """Describe the exact blocked bridge after validating no live input."""

    payload = {
        "schema": NATIVE_PLAN_SCHEMA,
        "policy_id": NATIVE_PLAN_POLICY_ID,
        "status": "blocked_not_run",
        "current_observation": {
            "schema": SCHEMA,
            "parent_wait_contract": "subprocess_popen_communicate_exact_child",
            "native_process_group_supervision_bound": False,
            "complete_descendant_supervision_bound": False,
        },
        "required_projection": {
            "schema": NATIVE_TERMINAL_PROJECTION_SCHEMA,
            "validated_shape_implemented": True,
            "must_be_derived_from_exact_nonconstructible_native_owner": True,
            "complete_private_group_drain_required": True,
            "exact_leader_reap_required": True,
            "normal_zero_exit_required": True,
            "worker_identity_binding_required": True,
            "native_session_and_execution_hashes_required": True,
            "worker_result_hash_required": True,
            "raw_pid_or_pgid_permitted": False,
        },
        "missing_bridge": {
            "fixed_real_worker_native_entrypoint_implemented": False,
            "owner_bound_process_image_observer_implemented": True,
            "owner_bound_network_observer_implemented": True,
            "owner_bound_native_image_ready_observer_implemented": True,
            "model_free_combined_fixed_worker_bridge_implemented": True,
            "model_free_terminal_projection_derived_from_live_owner": True,
            "fixed_model_free_ready_release_entrypoint_implemented": True,
            "existing_kim_ready_release_transport_shape_exercised": True,
            "private_native_request_result_frame_contract_implemented": True,
            "fixed_model_free_frame_bootstrap_implemented": True,
            "native_frame_bootstrap_exercised_under_live_owner": True,
            "fixed_native_sandbox_launch_shape_implemented": True,
            "native_sandbox_launch_exercised_model_free": True,
            "native_terminal_projection_derived_from_live_owner": False,
            "native_terminal_projection_bound_to_real_worker_result": False,
        },
        "effects": {
            "process_started": False,
            "model_imported": False,
            "checkpoint_opened": False,
            "audio_opened": False,
            "filesystem_written": False,
            "network_used": False,
            "separator_route_enabled": False,
            "product_authority_granted": False,
        },
        "limitations": [
            "projection_shape_validation_is_not_execution_provenance",
            "owner_bound_worker_ready_observer_not_attached_to_real_kim_worker",
            "owner_bound_network_broker_not_attached_to_real_kim_worker",
            "combined_fixed_worker_bridge_is_model_free_not_kim_vocal_2",
            "native_ready_release_transport_is_model_free_not_kim_vocal_2",
            "native_frame_bootstrap_consumes_values_but_grants_no_spawn_authority",
            "native_frame_bootstrap_opens_no_request_path_checkpoint_or_audio",
            "native_sandbox_launch_shape_exercised_only_by_model_free_bootstrap",
            "current_kim_worker_remains_on_the_subprocess_supervision_route",
            "no_public_cli_tui_simple_studio_or_source_graph_route",
        ],
    }
    return _freeze_json(
        {
            **payload,
            "plan_sha256": hashlib.sha256(
                _canonical_json_bytes(payload)
            ).hexdigest(),
        }
    )


def _validate_real_worker_supervision_observation(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = _plain(document)
    digest = value.pop("observation_sha256", None) if isinstance(value, dict) else None
    if (
        not isinstance(digest, str)
        or _SHA_RE.fullmatch(digest) is None
        or digest != hashlib.sha256(_canonical_json_bytes(value)).hexdigest()
    ):
        raise ValueError("MelRoFormer worker supervision self-hash differs")
    if (
        value.get("schema") != SCHEMA
        or value.get("policy_id") != POLICY_ID
        or value.get("status") != "real_worker_supervision_bound_complete"
        or set(value)
        != {
            "schema",
            "policy_id",
            "status",
            "outer_supervisor",
            "worker_signal_state",
            "terminal",
            "scope",
            "limitations",
        }
    ):
        raise ValueError("MelRoFormer worker supervision fields differ")
    _validate_post_cpython_signal_state(value["worker_signal_state"])
    if value["outer_supervisor"] != {
        "observation_point": (
            "private_launcher_main_before_sunofriend_execution_setup"
        ),
        "open_descriptors": [0, 1, 2],
        "only_standard_descriptors_open": True,
        "raw_descriptor_identities_retained": False,
    }:
        raise ValueError("MelRoFormer outer supervisor evidence differs")
    if value["terminal"] != {
        "parent_wait_contract": "subprocess_popen_communicate_exact_child",
        "exact_child_reaped": True,
        "normal_zero_exit": True,
        "exit_code": 0,
        "signal_termination_observed": False,
        "raw_pid_retained": False,
        "raw_pgid_retained": False,
        "signal_authority_exposed": False,
        "process_group_supervision_bound": False,
        "descendant_supervision_bound": False,
    }:
        raise ValueError("MelRoFormer worker terminal evidence differs")
    if value["scope"] != {
        "real_model_worker_observed": True,
        "worker_signal_report_bound": True,
        "outer_descriptor_boundary_bound": True,
        "pre_exec_signal_state_reconstructed": False,
        "product_authority_granted": False,
    }:
        raise ValueError("MelRoFormer worker supervision scope differs")
    if value["limitations"] != [
        "post_cpython_state_does_not_reconstruct_pre_exec_signal_instant",
        "subprocess_wait_is_not_native_process_group_supervision",
        "worker_descendants_are_denied_by_sandbox_but_not_supervisor_owned",
        "provider_and_runtime_path_to_execution_toctou_remain_open",
        "no_public_cli_tui_simple_studio_or_source_graph_route",
    ]:
        raise ValueError("MelRoFormer worker supervision limitations differ")
    checked = {**value, "observation_sha256": digest}
    encoded = json.dumps(checked, sort_keys=True, separators=(",", ":"))
    if "/Users/" in encoded or "file://" in encoded or "://" in encoded:
        raise ValueError("MelRoFormer worker supervision is not path-free")
    return _freeze_json(checked)


def _expected_post_cpython_signal_state() -> dict[str, Any]:
    return {
        "observation_point": "real_worker_main_after_cpython_startup",
        "main_thread_mask_empty": True,
        "blocked_signal_names": [],
        "handlers": {
            "SIGHUP": "default",
            "SIGINT": "python_default_int_handler",
            "SIGQUIT": "default",
            "SIGPIPE": "ignored",
            "SIGTERM": "default",
            "SIGCHLD": "default",
            "SIGXFSZ": "ignored",
        },
        "termination_signals_default": True,
        "sigchld_default": True,
        "cpython_runtime_adjustments_observed": True,
        "pre_exec_signal_state_reconstructed": False,
    }


def _signal_handler_name(handler: Any) -> str:
    if handler is signal.SIG_DFL:
        return "default"
    if handler is signal.SIG_IGN:
        return "ignored"
    if handler is signal.default_int_handler:
        return "python_default_int_handler"
    return "unexpected_python_handler"


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


__all__ = [
    "NATIVE_PLAN_POLICY_ID",
    "NATIVE_PLAN_SCHEMA",
    "NATIVE_TERMINAL_PROJECTION_SCHEMA",
    "POLICY_ID",
    "SCHEMA",
    "_build_native_real_worker_supervision_plan",
    "_build_real_worker_supervision_observation",
    "_derive_model_free_native_terminal_projection",
    "_observe_post_cpython_signal_state",
    "_validate_native_terminal_projection",
    "_validate_post_cpython_signal_state",
    "_validate_real_worker_supervision_observation",
]
