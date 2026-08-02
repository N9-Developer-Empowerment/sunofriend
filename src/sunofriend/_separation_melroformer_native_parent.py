"""Dependency-substituted lifecycle core for the private native Kim parent.

This module deliberately does not open a checkpoint, import a model, read
audio, build a native extension or start a process. It fixes the order and
fail-closed behaviour that the later macOS adapter must use around one exact
opaque native owner:

1. start through a separately admitted fixed native method;
2. attach live owner-bound observers and release the ready worker;
3. synchronously drain and exact-reap the complete process group;
4. decode the fd4 result against the exact fd3 request;
5. independently verify the private staging artifacts; and
6. consume PID/PGID only through the owner's boolean identity matcher.

The only executable entry point in this module is explicitly marked as a
dependency-substituted exercise. It cannot be used as evidence that the real
Kim model ran and grants no product, selection or publication authority.
"""

from __future__ import annotations

import hashlib
from typing import Any, Callable, Mapping

from ._separation_checkpoint_canonical import (
    canonical_json_bytes as _canonical_json,
    deep_freeze as _freeze,
    plain as _plain,
)
from ._separation_melroformer_native_transport import (
    _decode_private_melroformer_native_result,
    _validate_private_melroformer_native_request,
)
from ._separation_melroformer_supervision import (
    _derive_native_terminal_projection,
)


SCHEMA = "sunofriend.private-melroformer-native-parent-exercise.v1"
POLICY_ID = "private-kim-native-parent-dependency-substituted-v1"
_SHA_FIELDS = (
    "process_image_observation_sha256",
    "network_observation_sha256",
    "native_image_inventory_sha256",
)
_VERIFICATION_SHA_FIELDS = (
    "python_import_closure_evidence_sha256",
    "quarantine_evidence_sha256",
)


class _PrivateMelroformerParentLifecycleFailure(RuntimeError):
    """A dependency-substituted exercise failed after bounded cleanup."""

    def __init__(
        self,
        *,
        primary_error: BaseException,
        terminal_cleanup_complete: bool,
        cleanup_error: BaseException | None = None,
    ) -> None:
        super().__init__("private Kim parent lifecycle exercise failed")
        self.primary_error = primary_error
        self.terminal_cleanup_complete = terminal_cleanup_complete
        self.cleanup_error = cleanup_error


def _exercise_dependency_substituted_parent_lifecycle(
    *,
    request: Mapping[str, Any],
    expected_owner_type: type[Any],
    native_session_observation_sha256: str,
    spawn_native: Callable[[], Any],
    observe_and_release: Callable[[Any], Mapping[str, Any]],
    supervise_owner: Callable[[Any], Mapping[str, Any]],
    read_result_frame: Callable[[], bytes],
    verify_private_staging: Callable[
        [Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]
    ],
) -> Mapping[str, Any]:
    """Exercise the future parent order without starting a real process.

    Every operation is supplied by the caller so this function cannot reach a
    checkpoint, model, source, staging path or native launcher on its own.
    Production integration must replace this exercise with one fixed adapter;
    it must not expose these hooks as a public or user-configurable route.
    """

    checked_request = _validate_private_melroformer_native_request(request)
    _require_sha(
        native_session_observation_sha256,
        "native session observation",
    )
    if not isinstance(expected_owner_type, type):
        raise TypeError("private Kim parent owner type is invalid")
    for callback in (
        spawn_native,
        observe_and_release,
        supervise_owner,
        read_result_frame,
        verify_private_staging,
    ):
        if not callable(callback):
            raise TypeError("private Kim parent lifecycle hook is not callable")

    native_owner = spawn_native()
    _require_live_exact_owner(native_owner, expected_owner_type=expected_owner_type)

    live_observation: Mapping[str, Any] | None = None
    terminal: Mapping[str, Any] | None = None
    primary_error: BaseException | None = None
    cleanup_error: BaseException | None = None
    try:
        live_observation = _validate_live_observation(
            observe_and_release(native_owner)
        )
    except BaseException as error:
        primary_error = error
    try:
        terminal = _validate_terminal_observation(supervise_owner(native_owner))
    except BaseException as error:
        cleanup_error = error

    if primary_error is not None or cleanup_error is not None:
        raise _PrivateMelroformerParentLifecycleFailure(
            primary_error=primary_error or cleanup_error,  # type: ignore[arg-type]
            terminal_cleanup_complete=(
                terminal is not None
                and terminal["leader_reaped"] is True
                and terminal["group_empty"] is True
                and terminal["ownership_released"] is True
            ),
            cleanup_error=cleanup_error if primary_error is not None else None,
        ) from primary_error or cleanup_error
    if live_observation is None or terminal is None:
        raise RuntimeError("private Kim parent lifecycle evidence is incomplete")

    result = _decode_private_melroformer_native_result(
        read_result_frame(),
        request=checked_request,
    )
    staging_verification = _validate_staging_verification(
        verify_private_staging(checked_request, result["child_result"])
    )
    execution_payload = {
        "request_sha256": checked_request["request_sha256"],
        "worker_result_sha256": result["result_sha256"],
        "live_observation": _plain(live_observation),
        "staging_verification": _plain(staging_verification),
        "wait": _plain(terminal["wait"]),
        "leader_exit_observed": terminal["leader_exit_observed"],
        "leader_reaped": terminal["leader_reaped"],
        "group_empty": terminal["group_empty"],
        "ownership_released": terminal["ownership_released"],
        "ownership_lost": terminal["ownership_lost"],
    }
    native_execution_observation_sha256 = hashlib.sha256(
        _canonical_json(execution_payload)
    ).hexdigest()
    process_identity = result["private_process_identity"]
    terminal_projection = _derive_native_terminal_projection(
        native_owner=native_owner,
        expected_owner_type=expected_owner_type,
        native_session_observation_sha256=(
            native_session_observation_sha256
        ),
        native_execution_observation_sha256=(
            native_execution_observation_sha256
        ),
        worker_result_sha256=result["result_sha256"],
        worker_reported_pid=process_identity["pid"],
        worker_reported_pgid=process_identity["pgid"],
    )
    payload = {
        "schema": SCHEMA,
        "policy_id": POLICY_ID,
        "status": "dependency_substituted_lifecycle_complete",
        "evidence_scope": "private_model_free_parent_orchestration_only",
        "request_sha256": checked_request["request_sha256"],
        "worker_result_sha256": result["result_sha256"],
        "native_execution_observation_sha256": (
            native_execution_observation_sha256
        ),
        "live_observation": _plain(live_observation),
        "staging_verification": _plain(staging_verification),
        "terminal_projection": _plain(terminal_projection),
        "privacy": {
            "raw_pid_retained": False,
            "raw_pgid_retained": False,
            "paths_retained": False,
            "signal_authority_exposed": False,
        },
        "effects": {
            "real_native_process_started": False,
            "checkpoint_opened": False,
            "model_imported": False,
            "audio_read": False,
            "filesystem_written": False,
            "network_used": False,
        },
        "permissions": {
            "real_model_execution_proven": False,
            "automatic_selection_permitted": False,
            "source_graph_activation_permitted": False,
            "simple_mode_available": False,
            "studio_import_available": False,
            "product_route_permitted": False,
            "publication_permitted": False,
        },
        "limitations": [
            "all_lifecycle_dependencies_were_substituted",
            "no_native_process_checkpoint_model_audio_or_staging_was_opened",
            "live_macos_adapter_and_fresh_admission_remain_required",
            "no_public_cli_tui_simple_studio_or_source_graph_route",
        ],
    }
    document = {
        **payload,
        "evidence_sha256": hashlib.sha256(_canonical_json(payload)).hexdigest(),
    }
    _reject_private_values(document)
    return _freeze(document)


def _require_live_exact_owner(
    native_owner: Any,
    *,
    expected_owner_type: type[Any],
) -> None:
    if (
        type(native_owner) is not expected_owner_type
        or getattr(expected_owner_type, "__name__", None) != "_OwnedSpawnChild"
        or getattr(native_owner, "start_state", None) != "started_owned"
        or getattr(native_owner, "ownership_released", None) is not False
        or getattr(native_owner, "ownership_lost", None) is not False
        or hasattr(native_owner, "pid")
        or hasattr(native_owner, "pgid")
        or hasattr(native_owner, "__dict__")
        or not callable(getattr(native_owner, "matches_pid_and_pgid", None))
    ):
        raise TypeError("private Kim parent requires one exact live opaque owner")


def _validate_live_observation(value: Mapping[str, Any]) -> Mapping[str, Any]:
    observation = _plain(value)
    if not isinstance(observation, dict) or set(observation) != {
        *_SHA_FIELDS,
        "ready_release_completed",
        "raw_pid_or_pgid_retained",
        "paths_retained",
    }:
        raise ValueError("private Kim live observation fields differ")
    for key in _SHA_FIELDS:
        _require_sha(observation[key], key)
    if (
        observation["ready_release_completed"] is not True
        or observation["raw_pid_or_pgid_retained"] is not False
        or observation["paths_retained"] is not False
    ):
        raise ValueError("private Kim live observation boundary differs")
    return _freeze(observation)


def _validate_terminal_observation(value: Mapping[str, Any]) -> Mapping[str, Any]:
    terminal = _plain(value)
    if not isinstance(terminal, dict) or set(terminal) != {
        "wait",
        "timed_out",
        "term_sent",
        "kill_sent",
        "leader_exit_observed",
        "leader_reaped",
        "group_empty",
        "ownership_released",
        "ownership_lost",
    }:
        raise ValueError("private Kim terminal observation fields differ")
    if terminal["wait"] != {
        "kind": "exited",
        "exit_code": 0,
        "signal": None,
        "core_dumped": False,
    }:
        raise ValueError("private Kim worker did not exit normally")
    if any(
        terminal[key] is not True
        for key in (
            "leader_exit_observed",
            "leader_reaped",
            "group_empty",
            "ownership_released",
        )
    ) or any(
        terminal[key] is not False
        for key in (
            "timed_out",
            "term_sent",
            "kill_sent",
            "ownership_lost",
        )
    ):
        raise ValueError("private Kim terminal ownership is incomplete")
    return _freeze(terminal)


def _validate_staging_verification(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    verification = _plain(value)
    if not isinstance(verification, dict) or set(verification) != {
        *_VERIFICATION_SHA_FIELDS,
        "worker_inputs_unchanged",
        "private_artifacts_independently_verified",
        "paths_retained",
    }:
        raise ValueError("private Kim staging verification fields differ")
    for key in _VERIFICATION_SHA_FIELDS:
        _require_sha(verification[key], key)
    if (
        verification["worker_inputs_unchanged"] is not True
        or verification["private_artifacts_independently_verified"] is not True
        or verification["paths_retained"] is not False
    ):
        raise ValueError("private Kim staging verification is incomplete")
    return _freeze(verification)


def _require_sha(value: Any, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} hash differs")


def _reject_private_values(value: Mapping[str, Any]) -> None:
    encoded = _canonical_json(value)
    if b'"pid"' in encoded or b'"pgid"' in encoded or b'"paths"' in encoded:
        raise RuntimeError("private Kim parent evidence retained a private field")
    if b"://" in encoded or b'"/' in encoded:
        raise RuntimeError("private Kim parent evidence retained a path or URL")


__all__: tuple[str, ...] = ()
