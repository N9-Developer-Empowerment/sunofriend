"""Fixed private coordinator for the future native Kim worker.

This developer-only boundary composes the measured native session, live
checkpoint-descriptor reservation, guarded lease-to-start bridge, owner-bound
observers, bounded fd4 result drain, whole-group supervision, real staging
verification and terminal lease/session cleanup.

It is intentionally absent from every CLI, TUI, Simple, Studio and source-
graph route.  The first tests substitute every effectful dependency so they
prove fixed ordering and cleanup only; they are not evidence that a checkpoint,
model or authorised audio was opened.
"""

from __future__ import annotations

import hashlib
import os
import platform
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import _separation_macos_loaded_images as _loaded_images
from . import _separation_macos_process_image as _process_image
from . import _separation_macos_sandbox_network_observer as _network_observer
from . import _separation_macos_worker_native_images as _worker_images
from . import _separation_melroformer_checkpoint_lease as _lease
from . import _separation_melroformer_native_session_darwin as _session
from . import _separation_worker_ready_handshake as _ready_handshake
from ._separation_checkpoint_canonical import (
    canonical_json_bytes as _canonical_json,
    deep_freeze as _freeze,
    plain as _plain,
)
from ._separation_melroformer_native_model_free_adapter_darwin import (
    _owner_terminal,
    _read_bounded_result_frame,
    _require_successful_terminal,
    _supervise_owner,
    _terminal_cleanup_complete,
)
from ._separation_melroformer_native_failure_records import (
    _build_no_start_coordinator_failure_receipt,
    _build_started_coordinator_failure_receipt,
)
from ._separation_melroformer_native_staging import (
    _verify_private_melroformer_native_worker_staging,
)
from ._separation_melroformer_native_transport import (
    _validate_private_melroformer_native_request,
)
from ._separation_melroformer_supervision import (
    _derive_native_terminal_projection,
)


__all__: tuple[str, ...] = ()

SCHEMA = "sunofriend.private-melroformer-native-coordinator.v1"
POLICY_ID = "private-kim-fixed-native-parent-coordinator-v1"
_READY_TIMEOUT_SECONDS = 120.0
_RESULT_TIMEOUT_SECONDS = 30.0
_SUPERVISION_TIMEOUT_SECONDS = 120.0
_SNAPSHOT_SETTLE_SECONDS = 0.02


class _PrivateMelroformerNativeCoordinatorFailure(RuntimeError):
    """One fixed attempt failed after deterministic cleanup was attempted."""

    def __init__(
        self,
        *,
        primary_error: BaseException,
        terminal_cleanup_complete: bool,
        receipt: Mapping[str, Any] | None = None,
        cleanup_stages: Sequence[str] = (),
        cleanup_errors: Sequence[BaseException] = (),
    ) -> None:
        super().__init__("private Kim native coordinator failed")
        self.primary_error = primary_error
        self.terminal_cleanup_complete = terminal_cleanup_complete
        self.receipt = receipt
        self.failure_kind = (
            "unproven"
            if receipt is None
            else (
                "no_start"
                if receipt["process"]["state"] == "not_started"
                else "started_exact_reap"
            )
        )
        self.cleanup_stages = tuple(cleanup_stages)
        self.cleanup_errors = tuple(cleanup_errors)


def _coordinate_reserved_private_melroformer_native_worker_darwin(
    trusted_lease: Any,
    *,
    trusted_reservation: Any,
    current_lease_observation: Any,
    trusted_native_session: Any,
    native_session_observation: Any,
    request: Mapping[str, Any],
    staging_directory: str | Path,
    request_read_descriptor: int,
    result_write_descriptor: int,
    result_read_descriptor: int,
) -> Mapping[str, Any]:
    """Run one fixed private lifecycle and return a path-free receipt.

    The call owns the three supplied transport descriptors and terminalises
    the supplied checkpoint reservation/lease.  It creates fd6/fd7 itself and
    never returns fd5, a PID, a PGID, a path or signal authority.

    This function is private execution machinery, not a product route.  A
    successful receipt proves only the bounded local execution provenance it
    records; it does not promote a separator or make a musical-quality claim.
    """

    checked_request = _validate_private_melroformer_native_request(request)
    staging = Path(staging_directory)
    if staging != Path(checked_request["paths"]["staging_directory"]):
        raise ValueError("private Kim coordinator staging path differs")
    if platform.system() != "Darwin":
        raise RuntimeError("private Kim native coordinator requires macOS")

    checked_session_observation = (
        _session._validate_verified_private_melroformer_native_session_observation(
            trusted_native_session,
            native_session_observation,
        )
    )
    _known_session, session_state = _session._known_session(
        trusted_native_session
    )
    del _known_session
    runtime_path = session_state.runtime_launcher_path
    expected_owner_type = session_state.owner_type
    process_binding = _process_image._prepare_runtime_process_image_binding(
        runtime_path=runtime_path
    )

    broker: Any | None = None
    handshake: Any | None = None
    native_owner: Any | None = None
    result: Mapping[str, Any] | None = None
    terminal: Mapping[str, Any] | None = None
    network_observation: Mapping[str, Any] | None = None
    observed_native_images: Any | None = None
    runtime_process_image: Mapping[str, Any] | None = None
    native_image_evidence: Mapping[str, Any] | None = None
    staging_verification: Mapping[str, Any] | None = None
    post_run_lease_observation: Mapping[str, Any] | None = None
    process_observation: Mapping[str, Any] | None = None
    terminal_projection: Mapping[str, Any] | None = None
    session_terminal: Mapping[str, Any] | None = None
    lease_terminal: Mapping[str, Any] | None = None
    worker_released = False
    no_start = False
    primary_error: BaseException | None = None
    primary_stage = "native_start"
    cleanup_stages: list[str] = []
    cleanup_errors: list[BaseException] = []

    try:
        primary_stage = "network_observer_prepare"
        broker = _network_observer._prepare_owner_bound_network_observer()
        primary_stage = "ready_handshake_prepare"
        handshake = _ready_handshake._prepare_worker_ready_handshake()
        primary_stage = "native_start"
        native_owner = _lease._start_reserved_private_melroformer_native_worker_darwin(
            trusted_lease,
            trusted_reservation=trusted_reservation,
            current_lease_observation=current_lease_observation,
            trusted_native_session=trusted_native_session,
            native_session_observation=checked_session_observation,
            request=checked_request,
            staging_directory=staging,
            request_read_descriptor=request_read_descriptor,
            result_write_descriptor=result_write_descriptor,
            ready_write_descriptor=handshake.ready_write_fd,
            release_read_descriptor=handshake.release_read_fd,
        )
        primary_stage = "owner_binding"
        _session._known_started_private_melroformer_native_owner(
            trusted_native_session,
            native_owner,
        )
        primary_stage = "ready_handshake"
        readiness = _ready_handshake._read_worker_ready_handshake(
            handshake,
            timeout_seconds=_READY_TIMEOUT_SECONDS,
        )
        primary_stage = "process_image_observation"
        process_observation = native_owner.observe_owned_process_image(
            os.fsencode(process_binding.runtime_launcher_path),
            os.fsencode(process_binding.process_image_path),
            process_binding.process_image_cdhash.encode("ascii"),
        )
        if process_observation != {
            "kernel_cdhash": process_binding.process_image_cdhash,
            "path_state": "matched_expected_process_image",
        }:
            raise RuntimeError("private Kim process-image observation differs")
        primary_stage = "executable_snapshot"
        first_regions = _loaded_images._enumerate_owned_executable_regions(
            native_owner
        )
        time.sleep(_SNAPSHOT_SETTLE_SECONDS)
        second_regions = _loaded_images._enumerate_owned_executable_regions(
            native_owner
        )
        if _loaded_images._snapshot_key(first_regions) != (
            _loaded_images._snapshot_key(second_regions)
        ):
            raise RuntimeError("private Kim executable snapshots differ")
        mapped_files = _loaded_images._measure_mapped_files(
            second_regions,
            process_image_path=process_binding.process_image_path,
        )
        observed_native_images = _worker_images._ObservedWorkerNativeImages(
            readiness=readiness,
            regions=tuple(second_regions),
            measured=tuple(mapped_files),
        )
        primary_stage = "worker_release"
        _ready_handshake._release_worker_ready_handshake(handshake)
        worker_released = True
        primary_stage = "result_read"
        result = _read_bounded_result_frame(
            result_read_descriptor,
            request=checked_request,
            timeout_seconds=_RESULT_TIMEOUT_SECONDS,
        )
        primary_stage = "network_observer_finish"
        network_observation = broker.finish(native_owner=native_owner)
        primary_stage = "native_supervision"
        terminal = _supervise_owner(
            native_owner,
            timeout_seconds=_SUPERVISION_TIMEOUT_SECONDS,
        )
        primary_stage = "terminal_validation"
        _require_successful_terminal(terminal)
    except _session._PrivateMelroformerNativeNoStart as error:
        no_start = True
        primary_stage = "native_no_start"
        primary_error = error
    except BaseException as error:
        primary_error = error
    finally:
        for descriptor in (
            request_read_descriptor,
            result_write_descriptor,
            result_read_descriptor,
        ):
            _close_if_open(descriptor)
        if handshake is not None:
            try:
                _ready_handshake._abort_worker_ready_handshake(handshake)
            except BaseException as error:
                cleanup_stages.append("ready_handshake_abort")
                cleanup_errors.append(error)
        if broker is not None and not broker.consumed:
            try:
                if native_owner is not None and worker_released:
                    network_observation = broker.finish(native_owner=native_owner)
                else:
                    broker.abort()
            except BaseException as error:
                cleanup_stages.append("network_observer")
                cleanup_errors.append(error)
        if native_owner is not None and not _owner_terminal(native_owner):
            try:
                terminal = _supervise_owner(native_owner, timeout_seconds=0.0)
            except BaseException as error:
                cleanup_stages.append("native_owner_supervision")
                cleanup_errors.append(error)

    if primary_error is None and cleanup_errors:
        primary_stage = "terminal_cleanup"
        primary_error = RuntimeError(
            "private Kim live-parent cleanup was incomplete"
        )
    if primary_error is None:
        try:
            if any(
                value is None
                for value in (
                    native_owner,
                    result,
                    terminal,
                    network_observation,
                    observed_native_images,
                    process_observation,
                )
            ):
                raise RuntimeError("private Kim live evidence is incomplete")
            primary_stage = "process_image_completion"
            runtime_process_image = (
                _process_image._complete_runtime_process_image_binding(
                    prepared=process_binding,
                    observed=process_observation,
                )
            )
            primary_stage = "native_image_completion"
            native_image_evidence = (
                _worker_images._complete_macos_worker_native_image_observation(
                    observed=observed_native_images,
                    runtime_process_image=runtime_process_image,
                    child=result["child_result"],
                )
            )
            primary_stage = "staging_verification"
            staging_verification = (
                _verify_private_melroformer_native_worker_staging(
                    request=checked_request,
                    child_result=result["child_result"],
                    runtime_environment_root=(
                        session_state.runtime_environment_root
                    ),
                    base_runtime_root=session_state.base_runtime_root,
                )
            )
            primary_stage = "checkpoint_remeasurement"
            post_run_lease_observation = (
                _lease._recheck_private_melroformer_checkpoint_lease(
                    trusted_lease
                )
            )
            execution_sha256 = _execution_observation_sha256(
                request=checked_request,
                result=result,
                terminal=terminal,
                network_observation=network_observation,
                native_image_evidence=native_image_evidence,
                staging_verification=staging_verification,
                post_run_lease_observation=post_run_lease_observation,
            )
            private_identity = result["private_process_identity"]
            primary_stage = "terminal_projection"
            terminal_projection = _derive_native_terminal_projection(
                native_owner=native_owner,
                expected_owner_type=expected_owner_type,
                native_session_observation_sha256=(
                    checked_session_observation["observation_sha256"]
                ),
                native_execution_observation_sha256=execution_sha256,
                worker_result_sha256=result["result_sha256"],
                worker_reported_pid=private_identity["pid"],
                worker_reported_pgid=private_identity["pgid"],
            )
        except BaseException as error:
            primary_error = error

    if no_start:
        try:
            session_terminal = (
                _session._finish_no_start_private_melroformer_native_session(
                    trusted_native_session
                )
            )
            cleanup_stages.extend(
                event["stage"] for event in session_terminal["cleanup"]
            )
        except BaseException as error:
            cleanup_stages.append("native_session_terminal")
            cleanup_errors.append(error)
    elif native_owner is not None and terminal is not None:
        try:
            if _normal_terminal(terminal):
                session_terminal = (
                    _session._finish_started_private_melroformer_native_session(
                        trusted_native_session,
                        native_owner,
                        terminal_observation=terminal,
                    )
                )
            elif _terminal_cleanup_complete(terminal):
                session_terminal = _session._finish_failed_started_private_melroformer_native_session(
                    trusted_native_session,
                    native_owner,
                    terminal_observation=terminal,
                )
        except BaseException as error:
            cleanup_stages.append("native_session_terminal")
            cleanup_errors.append(error)

    try:
        _lease._release_private_melroformer_checkpoint_fd5(
            trusted_lease,
            trusted_reservation,
        )
    except BaseException as error:
        cleanup_stages.append("fd5_reservation_release")
        cleanup_errors.append(error)
    try:
        lease_terminal = (
            _lease._close_private_melroformer_checkpoint_lease(trusted_lease)
        )
    except BaseException as error:
        cleanup_stages.append("checkpoint_lease_close")
        cleanup_errors.append(error)
        lease_terminal = getattr(error, "receipt", None)

    cleanup_complete = bool(
        session_terminal is not None
        and lease_terminal is not None
        and (no_start or _terminal_cleanup_complete(terminal))
        and (
            not no_start
            or session_terminal.get("cleanup_count") == 0
        )
        and _lease_terminal_cleanup_complete(lease_terminal)
    )
    if primary_error is not None or cleanup_errors:
        if primary_error is None:
            primary_stage = "terminal_cleanup"
        error = primary_error or RuntimeError(
            "private Kim coordinator terminal cleanup was incomplete"
        )
        try:
            receipt = _failure_receipt(
                request=checked_request,
                primary_stage=primary_stage,
                no_start=no_start,
                native_owner=native_owner,
                terminal=terminal,
                result=result,
                session_terminal=session_terminal,
                lease_terminal=lease_terminal,
                cleanup_stages=cleanup_stages,
            )
        except BaseException as receipt_error:
            cleanup_stages.append("failure_receipt_seal")
            cleanup_errors.append(receipt_error)
            receipt = None
        raise _PrivateMelroformerNativeCoordinatorFailure(
            primary_error=error,
            terminal_cleanup_complete=cleanup_complete,
            receipt=receipt,
            cleanup_stages=cleanup_stages,
            cleanup_errors=cleanup_errors,
        ) from error

    if any(
        value is None
        for value in (
            result,
            terminal_projection,
            network_observation,
            native_image_evidence,
            staging_verification,
            post_run_lease_observation,
            session_terminal,
            lease_terminal,
        )
    ):
        error = RuntimeError("private Kim terminal evidence is incomplete")
        try:
            receipt = _failure_receipt(
                request=checked_request,
                primary_stage="terminal_evidence",
                no_start=False,
                native_owner=native_owner,
                terminal=terminal,
                result=result,
                session_terminal=session_terminal,
                lease_terminal=lease_terminal,
                cleanup_stages=cleanup_stages,
            )
        except BaseException:
            receipt = None
        raise _PrivateMelroformerNativeCoordinatorFailure(
            primary_error=error,
            terminal_cleanup_complete=cleanup_complete,
            receipt=receipt,
        ) from error
    return _build_terminal_receipt(
        request=checked_request,
        result=result,
        terminal_projection=terminal_projection,
        network_observation=network_observation,
        native_image_evidence=native_image_evidence,
        staging_verification=staging_verification,
        post_run_lease_observation=post_run_lease_observation,
        session_terminal=session_terminal,
        lease_terminal=lease_terminal,
    )


def _execution_observation_sha256(
    *,
    request: Mapping[str, Any],
    result: Mapping[str, Any],
    terminal: Mapping[str, Any],
    network_observation: Mapping[str, Any],
    native_image_evidence: Mapping[str, Any],
    staging_verification: Mapping[str, Any],
    post_run_lease_observation: Mapping[str, Any],
) -> str:
    payload = {
        "request_sha256": request["request_sha256"],
        "worker_result_sha256": result["result_sha256"],
        "network_observation_sha256": _evidence_digest(
            network_observation,
            "network observation",
        ),
        "native_image_evidence_sha256": _evidence_digest(
            native_image_evidence,
            "native image evidence",
        ),
        "staging_verification_sha256": _evidence_digest(
            staging_verification,
            "staging verification",
        ),
        "post_run_lease_observation_sha256": _evidence_digest(
            post_run_lease_observation,
            "post-run lease observation",
        ),
        "terminal": _plain(terminal),
    }
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _build_terminal_receipt(
    *,
    request: Mapping[str, Any],
    result: Mapping[str, Any],
    terminal_projection: Mapping[str, Any],
    network_observation: Mapping[str, Any],
    native_image_evidence: Mapping[str, Any],
    staging_verification: Mapping[str, Any],
    post_run_lease_observation: Mapping[str, Any],
    session_terminal: Mapping[str, Any],
    lease_terminal: Mapping[str, Any],
) -> Mapping[str, Any]:
    payload = {
        "schema": SCHEMA,
        "policy_id": POLICY_ID,
        "status": "private_native_worker_complete_and_terminal",
        "evidence_scope": "private_local_execution_provenance_only",
        "request_sha256": request["request_sha256"],
        "worker_result_sha256": result["result_sha256"],
        "child_result_sha256": result["child_result_sha256"],
        "network_observation_sha256": _evidence_digest(
            network_observation,
            "network observation",
        ),
        "native_image_evidence_sha256": _evidence_digest(
            native_image_evidence,
            "native image evidence",
        ),
        "staging_verification_sha256": _evidence_digest(
            staging_verification,
            "staging verification",
        ),
        "post_run_lease_observation_sha256": _evidence_digest(
            post_run_lease_observation,
            "post-run lease observation",
        ),
        "session_terminal_sha256": _evidence_digest(
            session_terminal,
            "session terminal",
        ),
        "checkpoint_lease_terminal_sha256": _evidence_digest(
            lease_terminal,
            "checkpoint lease terminal",
        ),
        "terminal_projection_sha256": hashlib.sha256(
            _canonical_json(_plain(terminal_projection))
        ).hexdigest(),
        "lifecycle": {
            "observers_prepared_before_start": True,
            "ready_and_executable_images_observed_before_release": True,
            "fd4_drained_while_owner_live": True,
            "network_observer_finished_before_reap": True,
            "complete_group_exactly_reaped": True,
            "mapped_files_remeasured_after_reap": True,
            "staging_parent_verified_after_reap": True,
            "checkpoint_remeasured_after_run": True,
            "worker_identity_consumed_only_by_owner_matcher": True,
            "fd5_reservation_released": True,
            "checkpoint_lease_closed": True,
            "native_session_terminal": True,
        },
        "privacy": {
            "raw_pid_retained": False,
            "raw_pgid_retained": False,
            "paths_retained": False,
            "network_destination_retained": False,
            "signal_authority_exposed": False,
        },
        "effects": {
            "native_process_started": True,
            "accepted_checkpoint_read_by_worker": True,
            "checkpoint_remeasured_by_parent": True,
            "real_model_worker_executed": True,
            "authorised_audio_read": True,
            "private_staging_written": True,
            "source_graph_changed": False,
            "selection_changed": False,
            "product_route_changed": False,
        },
        "permissions": {
            "automatic_selection_permitted": False,
            "source_graph_activation_permitted": False,
            "simple_mode_available": False,
            "studio_import_available": False,
            "product_route_permitted": False,
            "publication_permitted": False,
        },
        "limitations": [
            "receipt_is_execution_provenance_not_separator_quality_evidence",
            "unproven_start_or_incomplete_reap_has_no_failure_receipt",
            "dyld_shared_cache_and_transient_load_coverage_remain_incomplete",
            "no_public_cli_tui_simple_studio_or_source_graph_route",
        ],
    }
    document = {
        **payload,
        "receipt_sha256": hashlib.sha256(_canonical_json(payload)).hexdigest(),
    }
    encoded = _canonical_json(document)
    if (
        b'"pid"' in encoded
        or b'"pgid"' in encoded
        or b'"paths"' in encoded
        or b'"path"' in encoded
        or b'"url"' in encoded
        or b'"destination"' in encoded
        or b'"/' in encoded
        or b"://" in encoded
    ):
        raise RuntimeError("private Kim coordinator receipt retained private data")
    return _freeze(document)


def _failure_receipt(
    *,
    request: Mapping[str, Any],
    primary_stage: str,
    no_start: bool,
    native_owner: Any | None,
    terminal: Mapping[str, Any] | None,
    result: Mapping[str, Any] | None,
    session_terminal: Mapping[str, Any] | None,
    lease_terminal: Mapping[str, Any] | None,
    cleanup_stages: Sequence[str],
) -> Mapping[str, Any] | None:
    """Seal only a proved no-start or completely reaped started failure."""

    if session_terminal is None or lease_terminal is None:
        return None
    session_sha256 = _evidence_digest(session_terminal, "session terminal")
    lease_sha256 = _evidence_digest(lease_terminal, "checkpoint lease terminal")
    if no_start:
        if (
            native_owner is not None
            or terminal is not None
            or session_terminal.get("process_started") is not False
        ):
            return None
        return _build_no_start_coordinator_failure_receipt(
            request_sha256=request["request_sha256"],
            native_session_terminal_sha256=session_sha256,
            checkpoint_lease_terminal_sha256=lease_sha256,
            native_no_start_stage=session_terminal["native_no_start_stage"],
            cleanup_stages=cleanup_stages,
        )
    if (
        native_owner is None
        or terminal is None
        or not _terminal_cleanup_complete(terminal)
    ):
        return None
    return _build_started_coordinator_failure_receipt(
        request_sha256=request["request_sha256"],
        native_session_terminal_sha256=session_sha256,
        checkpoint_lease_terminal_sha256=lease_sha256,
        primary_stage=primary_stage,
        terminal_kind=(
            "normal_exit_after_evidence_failure"
            if _normal_terminal(terminal)
            else "failed_exit_exact_reap"
        ),
        worker_result_sha256=(
            None if result is None else result["result_sha256"]
        ),
        cleanup_stages=cleanup_stages,
    )


def _evidence_digest(value: Mapping[str, Any], label: str) -> str:
    for key in (
        "evidence_sha256",
        "observation_sha256",
        "receipt_sha256",
    ):
        digest = value.get(key)
        if (
            isinstance(digest, str)
            and len(digest) == 64
            and all(character in "0123456789abcdef" for character in digest)
        ):
            return digest
    raise ValueError(f"private Kim {label} hash differs")


def _normal_terminal(value: Mapping[str, Any]) -> bool:
    return _plain(value) == {
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


def _lease_terminal_cleanup_complete(value: Mapping[str, Any]) -> bool:
    try:
        return value["cleanup"]["status"] == "complete"
    except (KeyError, TypeError):
        return False


def _close_if_open(descriptor: int) -> None:
    if type(descriptor) is not int or descriptor < 0:
        return
    try:
        os.close(descriptor)
    except OSError:
        pass
