"""Dependency-substituted lifecycle core for the private native Kim parent.

This module deliberately does not open a checkpoint, import a model, read
audio, build a native extension or start a process. Its v2 exercise fixes the
fail-closed order that the later macOS adapter must use around one exact opaque
native owner:

1. prepare bounded observers before native spawn;
2. start through a separately admitted fixed native method;
3. capture worker readiness and executable state, then release the worker;
4. drain and decode fd4 while the owner is live;
5. consume live observers before synchronously draining and exact-reaping the
   complete process group;
6. remeasure and seal deferred observations and private staging after reap; and
7. consume PID/PGID only through the owner's boolean identity matcher.

The v1 exercise remains as compatibility evidence for its earlier simplified
ordering. It is not the production integration contract.

Both executable entry points in this module are explicitly marked as
dependency-substituted exercises. Neither can be used as evidence that the
real Kim model ran, and neither grants product, selection or publication
authority.
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
TWO_PHASE_SCHEMA = "sunofriend.private-melroformer-native-parent-exercise.v2"
TWO_PHASE_POLICY_ID = "private-kim-native-parent-two-phase-substituted-v1"
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
    return _build_dependency_substituted_parent_evidence(
        schema=SCHEMA,
        policy_id=POLICY_ID,
        status="dependency_substituted_lifecycle_complete",
        evidence_scope="private_model_free_parent_orchestration_only",
        checked_request=checked_request,
        expected_owner_type=expected_owner_type,
        native_session_observation_sha256=(
            native_session_observation_sha256
        ),
        native_owner=native_owner,
        live_observation=live_observation,
        terminal=terminal,
        result=result,
        staging_verification=staging_verification,
        limitations=[
            "all_lifecycle_dependencies_were_substituted",
            "no_native_process_checkpoint_model_audio_or_staging_was_opened",
            "live_macos_adapter_and_fresh_admission_remain_required",
            "no_public_cli_tui_simple_studio_or_source_graph_route",
        ],
    )


def _exercise_dependency_substituted_two_phase_parent_lifecycle(
    *,
    request: Mapping[str, Any],
    expected_owner_type: type[Any],
    native_session_observation_sha256: str,
    prepare_observers: Callable[[], Any],
    spawn_native: Callable[[Any], Any],
    capture_ready_and_release: Callable[[Any, Any], Any],
    read_result_frame: Callable[[], bytes],
    finish_live_observers: Callable[[Any, Any], Any],
    supervise_owner: Callable[[Any], Mapping[str, Any]],
    seal_post_reap_observation: Callable[
        [Any, Any, Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]
    ],
    verify_private_staging: Callable[
        [Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]
    ],
    abort_prepared_observers: Callable[[Any], None],
) -> Mapping[str, Any]:
    """Exercise the safe two-phase parent order without real dependencies.

    The observer handle is prepared before spawn. The worker-ready capture and
    fd4 drain happen while the exact owner is live; live observers are then
    consumed before whole-group supervision. Only after exact reap may mapped
    artifacts and other deferred observations be remeasured and sealed.

    All operations remain caller-supplied and private. This function opens no
    path or descriptor and cannot enable a product route. The later fixed macOS
    adapter must replace these hooks rather than expose them to users.
    """

    checked_request = _validate_private_melroformer_native_request(request)
    _require_sha(
        native_session_observation_sha256,
        "native session observation",
    )
    if not isinstance(expected_owner_type, type):
        raise TypeError("private Kim parent owner type is invalid")
    for callback in (
        prepare_observers,
        spawn_native,
        capture_ready_and_release,
        read_result_frame,
        finish_live_observers,
        supervise_owner,
        seal_post_reap_observation,
        verify_private_staging,
        abort_prepared_observers,
    ):
        if not callable(callback):
            raise TypeError("private Kim parent lifecycle hook is not callable")

    prepared: Any | None = None
    native_owner: Any | None = None
    live_capture: Any | None = None
    live_observer_capture: Any | None = None
    result: Mapping[str, Any] | None = None
    terminal: Mapping[str, Any] | None = None
    observers_terminal = False
    primary_error: BaseException | None = None
    cleanup_error: BaseException | None = None

    try:
        prepared = prepare_observers()
        if prepared is None:
            raise RuntimeError("private Kim prepared observer handle is absent")
        candidate_owner = spawn_native(prepared)
        _require_live_exact_owner(
            candidate_owner,
            expected_owner_type=expected_owner_type,
        )
        native_owner = candidate_owner
        live_capture = capture_ready_and_release(native_owner, prepared)
        result = _decode_private_melroformer_native_result(
            read_result_frame(),
            request=checked_request,
        )
    except BaseException as error:
        primary_error = error

    if native_owner is not None and prepared is not None:
        try:
            live_observer_capture = finish_live_observers(
                native_owner,
                prepared,
            )
            observers_terminal = True
        except BaseException as error:
            if primary_error is None:
                primary_error = error
            else:
                cleanup_error = error

    if native_owner is not None:
        try:
            terminal = _validate_terminal_observation(
                supervise_owner(native_owner)
            )
        except BaseException as error:
            if primary_error is None:
                primary_error = error
            elif cleanup_error is None:
                cleanup_error = error

    if prepared is not None and not observers_terminal:
        try:
            abort_prepared_observers(prepared)
        except BaseException as error:
            if primary_error is None:
                primary_error = error
            elif cleanup_error is None:
                cleanup_error = error

    cleanup_complete = _terminal_cleanup_complete(terminal)
    if primary_error is not None:
        raise _PrivateMelroformerParentLifecycleFailure(
            primary_error=primary_error,
            terminal_cleanup_complete=cleanup_complete,
            cleanup_error=cleanup_error,
        ) from primary_error
    if (
        native_owner is None
        or live_capture is None
        or live_observer_capture is None
        or result is None
        or terminal is None
    ):
        error = RuntimeError(
            "private Kim two-phase lifecycle evidence is incomplete"
        )
        raise _PrivateMelroformerParentLifecycleFailure(
            primary_error=error,
            terminal_cleanup_complete=cleanup_complete,
        ) from error

    try:
        live_observation = _validate_live_observation(
            seal_post_reap_observation(
                live_capture,
                live_observer_capture,
                checked_request,
                result["child_result"],
            )
        )
        staging_verification = _validate_staging_verification(
            verify_private_staging(checked_request, result["child_result"])
        )
        return _build_dependency_substituted_parent_evidence(
            schema=TWO_PHASE_SCHEMA,
            policy_id=TWO_PHASE_POLICY_ID,
            status="dependency_substituted_two_phase_lifecycle_complete",
            evidence_scope="private_model_free_two_phase_parent_orchestration_only",
            checked_request=checked_request,
            expected_owner_type=expected_owner_type,
            native_session_observation_sha256=(
                native_session_observation_sha256
            ),
            native_owner=native_owner,
            live_observation=live_observation,
            terminal=terminal,
            result=result,
            staging_verification=staging_verification,
            limitations=[
                "all_two_phase_lifecycle_dependencies_were_substituted",
                "no_native_process_checkpoint_model_audio_or_staging_was_opened",
                "concrete_macos_observer_and_supervisor_adapter_remains_required",
                "no_public_cli_tui_simple_studio_or_source_graph_route",
            ],
        )
    except BaseException as error:
        raise _PrivateMelroformerParentLifecycleFailure(
            primary_error=error,
            terminal_cleanup_complete=cleanup_complete,
        ) from error


def _terminal_cleanup_complete(
    terminal: Mapping[str, Any] | None,
) -> bool:
    return bool(
        terminal is not None
        and terminal["leader_reaped"] is True
        and terminal["group_empty"] is True
        and terminal["ownership_released"] is True
    )


def _build_dependency_substituted_parent_evidence(
    *,
    schema: str,
    policy_id: str,
    status: str,
    evidence_scope: str,
    checked_request: Mapping[str, Any],
    expected_owner_type: type[Any],
    native_session_observation_sha256: str,
    native_owner: Any,
    live_observation: Mapping[str, Any],
    terminal: Mapping[str, Any],
    result: Mapping[str, Any],
    staging_verification: Mapping[str, Any],
    limitations: list[str],
) -> Mapping[str, Any]:
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
        "schema": schema,
        "policy_id": policy_id,
        "status": status,
        "evidence_scope": evidence_scope,
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
        "limitations": limitations,
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
