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
import re
import signal
from typing import Any, Mapping, Sequence

from .separation_contract import _canonical_json_bytes, _freeze_json


SCHEMA = "sunofriend.private-melroformer-worker-supervision.v1"
POLICY_ID = "private-melroformer-real-worker-supervision-v1"
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
    "POLICY_ID",
    "SCHEMA",
    "_build_real_worker_supervision_observation",
    "_observe_post_cpython_signal_state",
    "_validate_post_cpython_signal_state",
    "_validate_real_worker_supervision_observation",
]
