"""Fixed model-free macOS parent adapter for the future native Kim route.

This private developer-only adapter joins the already-audited native sandbox
spawn shape, ready/release gate, owner-bound process-image and executable-
region observations, kernel Sandbox denial broker, bounded fd4 result reader,
whole-group supervisor and post-reap staging remeasurement around one fixed
stdlib canary worker.

It deliberately rejects a checkpoint-sized fd5 input, reads no accepted
checkpoint or audio, imports no model and is not imported by any CLI, TUI,
Simple, Studio or source-graph route.  Its purpose is to prove the concrete
parent lifecycle before the separately guarded real-worker start is attached.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import platform
import re
import stat
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import _separation_macos_loaded_images as _loaded_images
from . import _separation_macos_sandbox_network_observer as _network_observer
from . import _separation_native_session_darwin as _native_session
from . import _separation_worker_ready_handshake as _ready_handshake
from ._separation_checkpoint_canonical import (
    canonical_json_bytes as _canonical_json,
    deep_freeze as _freeze,
    plain as _plain,
)
from ._separation_melroformer_native_parent import _require_live_exact_owner
from ._separation_melroformer_native_transport import (
    RESULT_MAXIMUM_BYTES,
    _decode_private_melroformer_native_result,
    _encode_private_melroformer_native_request,
    _validate_private_melroformer_native_request,
)
from ._separation_melroformer_supervision import (
    _derive_model_free_native_terminal_projection,
)
from ._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
)


SCHEMA = "sunofriend.private-melroformer-native-model-free-adapter.v1"
POLICY_ID = "private-kim-fixed-model-free-macos-parent-adapter-v1"
_SANDBOX_PROVIDER = Path("/usr/bin/sandbox-exec")
_FIXED_WORKER = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "_separation_native_spawn_frame_bootstrap_worker.py"
)
_SPAWN_METHOD = "_spawn_bound_private_melroformer_worker"
_SPAWN_MODULE = "_separation_native_spawn_darwin"
_MAXIMUM_PLACEHOLDER_BYTES = 65_536
_MAXIMUM_WORKER_BYTES = 1_048_576
_MAXIMUM_RUNTIME_BYTES = 134_217_728
_MAXIMUM_PROVIDER_BYTES = 8_388_608
_MAXIMUM_STAGING_ENTRIES = 3
_READY_TIMEOUT_SECONDS = 5.0
_RESULT_TIMEOUT_SECONDS = 5.0
_SNAPSHOT_SETTLE_SECONDS = 0.02
_POLL_SECONDS = 0.005
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_CDHASH_RE = re.compile(r"^[0-9a-f]{40}$")


class _FixedModelFreeMacosParentAdapterFailure(RuntimeError):
    """One canary lifecycle failed after bounded cleanup was attempted."""

    def __init__(
        self,
        *,
        primary_error: BaseException,
        terminal_cleanup_complete: bool,
        cleanup_errors: Sequence[BaseException] = (),
    ) -> None:
        super().__init__("fixed model-free macOS parent adapter failed")
        self.primary_error = primary_error
        self.terminal_cleanup_complete = terminal_cleanup_complete
        self.cleanup_errors = tuple(cleanup_errors)


def _run_fixed_model_free_macos_parent_adapter(
    *,
    request: Mapping[str, Any],
    native_session_observation_sha256: str,
    spawn_native: Callable[..., Any],
    expected_owner_type: type[Any],
    runtime_path: str | Path,
    expected_process_image_path: str | Path,
    expected_process_image_cdhash: str,
    staging_directory: str | Path,
    request_read_descriptor: int,
    result_write_descriptor: int,
    result_read_descriptor: int,
    checkpoint_placeholder_descriptor: int,
) -> Mapping[str, Any]:
    """Run the fixed stdlib canary through one concrete native lifecycle.

    The caller retains all four descriptors if preflight fails.  Once native
    spawn is attempted, descriptor ownership transfers to this call: the first
    three child-source descriptors are closed immediately after that attempt,
    and the separate result reader is closed after bounded decoding.  The
    checkpoint input must be a small model-free placeholder, never the
    accepted Kim checkpoint.
    """

    checked_request = _validate_private_melroformer_native_request(request)
    _require_sha(native_session_observation_sha256, "native session observation")
    if platform.system() != "Darwin":
        raise RuntimeError("fixed model-free parent adapter requires macOS")
    _validate_spawn_binding(spawn_native)
    if (
        not isinstance(expected_owner_type, type)
        or getattr(expected_owner_type, "__name__", None) != "_OwnedSpawnChild"
    ):
        raise TypeError("fixed model-free parent owner type differs")

    runtime = Path(runtime_path).resolve(strict=True)
    process_image = Path(expected_process_image_path).resolve(strict=True)
    staging = Path(staging_directory).resolve(strict=True)
    provider = _SANDBOX_PROVIDER.resolve(strict=True)
    worker = _FIXED_WORKER.resolve(strict=True)
    if staging != Path(checked_request["paths"]["staging_directory"]):
        raise ValueError("fixed model-free staging path differs from request")
    if _CDHASH_RE.fullmatch(expected_process_image_cdhash) is None:
        raise ValueError("fixed model-free process-image CDHash differs")

    bindings_before = _measure_fixed_bindings(
        runtime=runtime,
        process_image=process_image,
        provider=provider,
        worker=worker,
    )
    if (
        bindings_before["worker"]["sha256"]
        != checked_request["identities"]["worker_source_sha256"]
    ):
        raise ValueError("fixed model-free worker does not match the request")
    transport_before = _validate_transport_descriptors(
        request=checked_request,
        request_read_descriptor=request_read_descriptor,
        result_write_descriptor=result_write_descriptor,
        result_read_descriptor=result_read_descriptor,
        checkpoint_placeholder_descriptor=checkpoint_placeholder_descriptor,
    )
    staging_before = _measure_model_free_staging(
        staging,
        transport=transport_before,
        expected_result_frame=None,
    )

    broker: Any | None = None
    handshake: Any | None = None
    native_owner: Any | None = None
    mapped_files: tuple[dict[str, Any], ...] | None = None
    result: Mapping[str, Any] | None = None
    network_observation: Mapping[str, Any] | None = None
    terminal: Mapping[str, Any] | None = None
    ready_claim: Mapping[str, Any] | None = None
    process_image_observation: Mapping[str, Any] | None = None
    inventory_capture: Mapping[str, Any] | None = None
    worker_released = False
    primary_error: BaseException | None = None
    cleanup_errors: list[BaseException] = []

    try:
        broker = _network_observer._prepare_owner_bound_network_observer()
        handshake = _ready_handshake._prepare_worker_ready_handshake()
        try:
            native_owner = spawn_native(
                os.fsencode(provider),
                os.fsencode(runtime),
                os.fsencode(worker),
                os.fsencode(staging),
                request_read_descriptor,
                result_write_descriptor,
                checkpoint_placeholder_descriptor,
                handshake.ready_write_fd,
                handshake.release_read_fd,
            )
        finally:
            for descriptor in (
                request_read_descriptor,
                result_write_descriptor,
                checkpoint_placeholder_descriptor,
            ):
                _close_if_open(descriptor)
        _require_live_exact_owner(
            native_owner,
            expected_owner_type=expected_owner_type,
        )
        ready_claim = _ready_handshake._read_worker_ready_handshake(
            handshake,
            timeout_seconds=_READY_TIMEOUT_SECONDS,
        )
        process_image_observation = native_owner.observe_owned_process_image(
            os.fsencode(runtime),
            os.fsencode(process_image),
            expected_process_image_cdhash.encode("ascii"),
        )
        _validate_process_image_observation(
            process_image_observation,
            expected_cdhash=expected_process_image_cdhash,
        )
        first = _loaded_images._enumerate_owned_executable_regions(native_owner)
        time.sleep(_SNAPSHOT_SETTLE_SECONDS)
        second = _loaded_images._enumerate_owned_executable_regions(native_owner)
        if _loaded_images._snapshot_key(first) != _loaded_images._snapshot_key(
            second
        ):
            raise RuntimeError("fixed model-free executable snapshots differ")
        mapped_files = _loaded_images._measure_mapped_files(
            second,
            process_image_path=process_image,
        )
        inventory_capture = _build_inventory_capture(
            regions=second,
            mapped_files=mapped_files,
        )
        _ready_handshake._release_worker_ready_handshake(handshake)
        worker_released = True
        result = _read_bounded_result_frame(
            result_read_descriptor,
            request=checked_request,
            timeout_seconds=_RESULT_TIMEOUT_SECONDS,
        )
        _validate_model_free_child_result(result["child_result"])
        network_observation = broker.finish(native_owner=native_owner)
        terminal = _supervise_owner(native_owner, timeout_seconds=5.0)
        _require_successful_terminal(terminal)
    except BaseException as error:
        primary_error = error
    finally:
        _close_if_open(result_read_descriptor)
        if handshake is not None:
            _ready_handshake._abort_worker_ready_handshake(handshake)
        if broker is not None and not broker.consumed:
            if native_owner is not None and worker_released:
                try:
                    network_observation = broker.finish(native_owner=native_owner)
                except BaseException as error:
                    cleanup_errors.append(error)
            else:
                try:
                    broker.abort()
                except BaseException as error:
                    cleanup_errors.append(error)
        if native_owner is not None and not _owner_terminal(native_owner):
            try:
                terminal = _supervise_owner(native_owner, timeout_seconds=0.0)
            except BaseException as error:
                cleanup_errors.append(error)

    cleanup_complete = _terminal_cleanup_complete(terminal)
    if primary_error is not None:
        raise _FixedModelFreeMacosParentAdapterFailure(
            primary_error=primary_error,
            terminal_cleanup_complete=cleanup_complete,
            cleanup_errors=cleanup_errors,
        ) from primary_error
    if cleanup_errors:
        error = RuntimeError("fixed model-free parent cleanup was incomplete")
        raise _FixedModelFreeMacosParentAdapterFailure(
            primary_error=error,
            terminal_cleanup_complete=cleanup_complete,
            cleanup_errors=cleanup_errors,
        ) from error
    if any(
        value is None
        for value in (
            native_owner,
            mapped_files,
            result,
            network_observation,
            terminal,
            ready_claim,
            process_image_observation,
            inventory_capture,
        )
    ):
        error = RuntimeError("fixed model-free parent evidence is incomplete")
        raise _FixedModelFreeMacosParentAdapterFailure(
            primary_error=error,
            terminal_cleanup_complete=cleanup_complete,
        ) from error

    try:
        _loaded_images._remeasure_mapped_files(mapped_files)
        bindings_after = _measure_fixed_bindings(
            runtime=runtime,
            process_image=process_image,
            provider=provider,
            worker=worker,
        )
        if bindings_after != bindings_before:
            raise RuntimeError("fixed model-free execution binding changed")
        result_frame = _encode_result_for_staging_check(result, checked_request)
        staging_after = _measure_model_free_staging(
            staging,
            transport=transport_before,
            expected_result_frame=result_frame,
        )
        if staging_after["stable_input_manifest_sha256"] != staging_before[
            "stable_input_manifest_sha256"
        ]:
            raise RuntimeError("fixed model-free staging inputs changed")
        return _build_adapter_evidence(
            checked_request=checked_request,
            native_session_observation_sha256=(
                native_session_observation_sha256
            ),
            native_owner=native_owner,
            expected_owner_type=expected_owner_type,
            ready_claim=ready_claim,
            process_image_observation=process_image_observation,
            inventory_capture=inventory_capture,
            network_observation=network_observation,
            terminal=terminal,
            result=result,
            staging_before=staging_before,
            staging_after=staging_after,
            bindings=bindings_after,
        )
    except BaseException as error:
        raise _FixedModelFreeMacosParentAdapterFailure(
            primary_error=error,
            terminal_cleanup_complete=cleanup_complete,
        ) from error


def _validate_spawn_binding(value: Any) -> None:
    owner = getattr(value, "__self__", None)
    if (
        type(value).__name__ != "builtin_function_or_method"
        or getattr(value, "__name__", None) != _SPAWN_METHOD
        or getattr(owner, "__name__", None) != _SPAWN_MODULE
    ):
        raise TypeError("fixed model-free native spawn binding differs")


def _validate_transport_descriptors(
    *,
    request: Mapping[str, Any],
    request_read_descriptor: int,
    result_write_descriptor: int,
    result_read_descriptor: int,
    checkpoint_placeholder_descriptor: int,
) -> Mapping[str, Any]:
    descriptors = (
        request_read_descriptor,
        result_write_descriptor,
        result_read_descriptor,
        checkpoint_placeholder_descriptor,
    )
    if (
        any(type(value) is not int or value < 3 for value in descriptors)
        or len(set(descriptors)) != len(descriptors)
    ):
        raise ValueError("fixed model-free transport descriptors differ")
    measured = {
        "request": _measure_descriptor(request_read_descriptor),
        "result_write": _measure_descriptor(result_write_descriptor),
        "result_read": _measure_descriptor(result_read_descriptor),
        "checkpoint_placeholder": _measure_descriptor(
            checkpoint_placeholder_descriptor
        ),
    }
    if any(value["inheritable"] for value in measured.values()):
        raise ValueError("fixed model-free transport descriptor is inheritable")
    if (
        measured["request"]["access_mode"] != os.O_RDONLY
        or measured["result_write"]["access_mode"] != os.O_WRONLY
        or measured["result_read"]["access_mode"] != os.O_RDONLY
        or measured["checkpoint_placeholder"]["access_mode"] != os.O_RDONLY
        or any(value["file_type"] != "regular" for value in measured.values())
        or measured["result_write"]["identity"]
        != measured["result_read"]["identity"]
        or measured["result_write"]["size"] != 0
        or measured["request"]["size"]
        != len(_encode_private_melroformer_native_request(request))
        or not 1
        <= measured["checkpoint_placeholder"]["size"]
        <= _MAXIMUM_PLACEHOLDER_BYTES
        or measured["checkpoint_placeholder"]["size"]
        == CONVERSION_CHECKPOINT_BYTES
    ):
        raise ValueError("fixed model-free transport geometry differs")
    request_frame = _pread_exact(
        request_read_descriptor,
        measured["request"]["size"],
    )
    if request_frame != _encode_private_melroformer_native_request(request):
        raise ValueError("fixed model-free request descriptor differs")
    checkpoint_placeholder = _pread_exact(
        checkpoint_placeholder_descriptor,
        measured["checkpoint_placeholder"]["size"],
    )
    return _freeze(
        {
            **measured,
            "request_frame_sha256": hashlib.sha256(request_frame).hexdigest(),
            "checkpoint_placeholder_sha256": hashlib.sha256(
                checkpoint_placeholder
            ).hexdigest(),
        }
    )


def _measure_descriptor(descriptor: int) -> Mapping[str, Any]:
    try:
        flags = fcntl.fcntl(descriptor, fcntl.F_GETFL)
        value = os.fstat(descriptor)
    except OSError as error:
        raise ValueError("fixed model-free descriptor is unavailable") from error
    return _freeze(
        {
            "access_mode": flags & os.O_ACCMODE,
            "append": bool(flags & os.O_APPEND),
            "inheritable": os.get_inheritable(descriptor),
            "file_type": "regular" if stat.S_ISREG(value.st_mode) else "other",
            "identity": [value.st_dev, value.st_ino],
            "size": value.st_size,
            "mode": stat.S_IMODE(value.st_mode),
            "uid": value.st_uid,
            "links": value.st_nlink,
        }
    )


def _measure_model_free_staging(
    directory: Path,
    *,
    transport: Mapping[str, Any],
    expected_result_frame: bytes | None,
) -> Mapping[str, Any]:
    state = directory.lstat()
    if (
        not stat.S_ISDIR(state.st_mode)
        or state.st_uid != os.getuid()
        or stat.S_IMODE(state.st_mode) & 0o077
    ):
        raise ValueError("fixed model-free staging directory is not owner-only")
    roles = {
        tuple(transport["request"]["identity"]): "request",
        tuple(transport["result_read"]["identity"]): "result",
        tuple(transport["checkpoint_placeholder"]["identity"]): (
            "checkpoint_placeholder"
        ),
    }
    entries: list[dict[str, Any]] = []
    with os.scandir(directory) as iterator:
        for entry in iterator:
            if len(entries) >= _MAXIMUM_STAGING_ENTRIES:
                raise ValueError("fixed model-free staging has extra entries")
            item = entry.stat(follow_symlinks=False)
            identity = (item.st_dev, item.st_ino)
            if not stat.S_ISREG(item.st_mode) or identity not in roles:
                raise ValueError("fixed model-free staging entry differs")
            if entry.is_symlink():
                raise ValueError("fixed model-free staging contains a link")
            path = Path(entry.path)
            content = _read_bounded_file(path, limit=RESULT_MAXIMUM_BYTES)
            entries.append(
                {
                    "role": roles[identity],
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "mode": stat.S_IMODE(item.st_mode),
                    "uid_matches_parent": item.st_uid == os.getuid(),
                    "links": item.st_nlink,
                }
            )
    if len(entries) != _MAXIMUM_STAGING_ENTRIES or len(roles) != 3:
        raise ValueError("fixed model-free staging transport set differs")
    entries.sort(key=lambda item: item["role"])
    by_role = {item["role"]: item for item in entries}
    if (
        by_role["request"]["sha256"] != transport["request_frame_sha256"]
        or by_role["checkpoint_placeholder"]["sha256"]
        != transport["checkpoint_placeholder_sha256"]
    ):
        raise RuntimeError("fixed model-free staging input changed")
    if expected_result_frame is None:
        if by_role["result"]["bytes"] != 0:
            raise ValueError("fixed model-free result was not initially empty")
    elif (
        by_role["result"]["bytes"] != len(expected_result_frame)
        or by_role["result"]["sha256"]
        != hashlib.sha256(expected_result_frame).hexdigest()
    ):
        raise RuntimeError("fixed model-free staged result differs")
    stable_inputs = [
        item for item in entries if item["role"] != "result"
    ]
    return _freeze(
        {
            "entry_count": len(entries),
            "manifest_sha256": hashlib.sha256(
                _canonical_json(entries)
            ).hexdigest(),
            "stable_input_manifest_sha256": hashlib.sha256(
                _canonical_json(stable_inputs)
            ).hexdigest(),
            "result_frame_sha256": by_role["result"]["sha256"],
            "owner_only": True,
            "paths_retained": False,
        }
    )


def _read_bounded_result_frame(
    descriptor: int,
    *,
    request: Mapping[str, Any],
    timeout_seconds: float,
) -> Mapping[str, Any]:
    if (
        type(descriptor) is not int
        or descriptor < 3
        or not isinstance(timeout_seconds, (int, float))
        or not 0 < float(timeout_seconds) <= 30
    ):
        raise ValueError("fixed model-free result reader arguments differ")
    before = _measure_descriptor(descriptor)
    if (
        before["access_mode"] != os.O_RDONLY
        or before["file_type"] != "regular"
        or before["inheritable"] is not False
    ):
        raise ValueError("fixed model-free result reader differs")
    deadline = time.monotonic() + float(timeout_seconds)
    last_error: BaseException | None = None
    while time.monotonic() < deadline:
        current = _measure_descriptor(descriptor)
        if current["identity"] != before["identity"]:
            raise RuntimeError("fixed model-free result identity changed")
        if current["size"] > RESULT_MAXIMUM_BYTES:
            raise RuntimeError("fixed model-free result exceeds its bound")
        if current["size"]:
            frame = _pread_exact(descriptor, current["size"])
            try:
                return _decode_private_melroformer_native_result(
                    frame,
                    request=request,
                )
            except ValueError as error:
                last_error = error
        time.sleep(_POLL_SECONDS)
    raise TimeoutError("fixed model-free fd4 result did not complete") from last_error


def _supervise_owner(
    native_owner: Any,
    *,
    timeout_seconds: float,
) -> Mapping[str, Any]:
    raw, timed_out, term_sent, kill_sent = _native_session._supervise_native_owner(
        native_owner,
        timeout_ns=int(timeout_seconds * 1_000_000_000),
    )
    wait = _native_session._normalise_owned_wait_status(raw)
    return _freeze(
        {
            "wait": _plain(wait),
            "timed_out": timed_out,
            "term_sent": term_sent,
            "kill_sent": kill_sent,
            "leader_exit_observed": native_owner.leader_exit_observed,
            "leader_reaped": native_owner.leader_reaped,
            "group_empty": native_owner.group_empty,
            "ownership_released": native_owner.ownership_released,
            "ownership_lost": native_owner.ownership_lost,
        }
    )


def _require_successful_terminal(value: Mapping[str, Any]) -> None:
    if value != {
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
    }:
        raise RuntimeError("fixed model-free owner did not exit cleanly")


def _validate_process_image_observation(
    value: Mapping[str, Any],
    *,
    expected_cdhash: str,
) -> None:
    if _plain(value) != {
        "kernel_cdhash": expected_cdhash,
        "path_state": "matched_expected_process_image",
    }:
        raise RuntimeError("fixed model-free process-image observation differs")


def _build_inventory_capture(
    *,
    regions: Sequence[Any],
    mapped_files: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    artifacts = _loaded_images._path_free_artifacts(mapped_files)
    unpathed = sum(region.path is None for region in regions)
    payload = {
        "snapshot_count": 2,
        "stable_consecutive_snapshots": True,
        "executable_region_count": len(regions),
        "file_backed_executable_region_count": len(regions) - unpathed,
        "unpathed_executable_region_count": unpathed,
        "mapped_file_count": len(mapped_files),
        "artifacts": artifacts,
        "paths_retained": False,
    }
    return _freeze(
        {
            **payload,
            "inventory_sha256": hashlib.sha256(_canonical_json(payload)).hexdigest(),
        }
    )


def _validate_model_free_child_result(value: Mapping[str, Any]) -> None:
    child = _plain(value)
    if (
        child.get("schema")
        != "sunofriend.private-melroformer-native-sandbox-bootstrap-child.v1"
        or child.get("status")
        != "model_free_native_sandbox_bootstrap_complete"
        or child.get("request_frame_validated") is not True
        or child.get("request_paths_opened") is not False
        or child.get("request_paths_retained") is not False
        or child.get("checkpoint_descriptor_bytes_read") != 0
        or child.get("ready_release_completed") is not True
        or child.get("model_imported") is not False
        or child.get("checkpoint_loaded") is not False
        or child.get("audio_read") is not False
        or child.get("network_used") is not False
        or child.get("product_authority_granted") is not False
    ):
        raise ValueError("fixed model-free child result differs")
    canaries = child.get("sandbox_canaries")
    if (
        not isinstance(canaries, dict)
        or canaries.get("network_errno_name") != "EPERM"
        or canaries.get("process_fork_errno_name") != "EPERM"
        or canaries.get("outside_write_errno_name") != "EPERM"
        or canaries.get("fixed_sandbox_environment_observed") is not True
    ):
        raise ValueError("fixed model-free sandbox canary differs")


def _encode_result_for_staging_check(
    result: Mapping[str, Any],
    request: Mapping[str, Any],
) -> bytes:
    from ._separation_melroformer_native_transport import (
        _encode_private_melroformer_native_result,
    )

    return _encode_private_melroformer_native_result(result, request=request)


def _build_adapter_evidence(
    *,
    checked_request: Mapping[str, Any],
    native_session_observation_sha256: str,
    native_owner: Any,
    expected_owner_type: type[Any],
    ready_claim: Mapping[str, Any],
    process_image_observation: Mapping[str, Any],
    inventory_capture: Mapping[str, Any],
    network_observation: Mapping[str, Any],
    terminal: Mapping[str, Any],
    result: Mapping[str, Any],
    staging_before: Mapping[str, Any],
    staging_after: Mapping[str, Any],
    bindings: Mapping[str, Any],
) -> Mapping[str, Any]:
    ready_sha256 = hashlib.sha256(
        _canonical_json(_plain(ready_claim)) + b"\n"
    ).hexdigest()
    process_image_sha256 = hashlib.sha256(
        _canonical_json(_plain(process_image_observation))
    ).hexdigest()
    execution_payload = {
        "request_sha256": checked_request["request_sha256"],
        "worker_result_sha256": result["result_sha256"],
        "ready_claim_sha256": ready_sha256,
        "process_image_observation_sha256": process_image_sha256,
        "network_observation_sha256": network_observation["evidence_sha256"],
        "native_image_inventory_sha256": inventory_capture["inventory_sha256"],
        "staging_after_sha256": staging_after["manifest_sha256"],
        "wait": _plain(terminal["wait"]),
        "group_empty": terminal["group_empty"],
        "exact_reap": terminal["leader_reaped"],
    }
    execution_sha256 = hashlib.sha256(
        _canonical_json(execution_payload)
    ).hexdigest()
    private_identity = result["private_process_identity"]
    projection = _derive_model_free_native_terminal_projection(
        native_owner=native_owner,
        expected_owner_type=expected_owner_type,
        native_session_observation_sha256=native_session_observation_sha256,
        native_execution_observation_sha256=execution_sha256,
        worker_result_sha256=result["result_sha256"],
        worker_reported_pid=private_identity["pid"],
        worker_reported_pgid=private_identity["pgid"],
    )
    payload = {
        "schema": SCHEMA,
        "policy_id": POLICY_ID,
        "status": "fixed_model_free_macos_parent_adapter_complete",
        "evidence_scope": "private_model_free_native_parent_canary_only",
        "request_sha256": checked_request["request_sha256"],
        "worker_result_sha256": result["result_sha256"],
        "child_result_sha256": result["child_result_sha256"],
        "native_execution_observation_sha256": execution_sha256,
        "live_observation": {
            "ready_claim_sha256": ready_sha256,
            "process_image_observation_sha256": process_image_sha256,
            "network_observation_sha256": network_observation["evidence_sha256"],
            "native_image_inventory_sha256": inventory_capture[
                "inventory_sha256"
            ],
            "deliberate_network_denial_count": network_observation[
                "observation"
            ]["deliberate_canary_denial_count"],
            "other_owned_network_denial_count": network_observation[
                "observation"
            ]["other_target_network_denial_count"],
            "ready_release_completed": True,
            "paths_retained": False,
        },
        "staging_verification": {
            "entry_count": staging_after["entry_count"],
            "before_manifest_sha256": staging_before["manifest_sha256"],
            "after_manifest_sha256": staging_after["manifest_sha256"],
            "stable_input_manifest_sha256": staging_after[
                "stable_input_manifest_sha256"
            ],
            "result_frame_sha256": staging_after["result_frame_sha256"],
            "worker_inputs_unchanged": True,
            "only_result_frame_changed": True,
            "paths_retained": False,
        },
        "binding_sha256": hashlib.sha256(
            _canonical_json(_plain(bindings))
        ).hexdigest(),
        "terminal_projection": _plain(projection),
        "privacy": {
            "raw_pid_retained": False,
            "raw_pgid_retained": False,
            "paths_retained": False,
            "network_destination_retained": False,
            "signal_authority_exposed": False,
        },
        "effects": {
            "native_process_started": True,
            "model_free_worker_started": True,
            "accepted_checkpoint_opened": False,
            "checkpoint_descriptor_bytes_read_by_worker": 0,
            "model_imported": False,
            "audio_read": False,
            "network_used": False,
            "denied_network_canary_attempted": True,
            "staged_result_frame_written": True,
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
            "fixed_stdlib_model_free_worker_only",
            "small_placeholder_fd5_explicitly_rejects_the_real_checkpoint",
            "real_guarded_session_admission_and_live_lease_not_composed",
            "no_checkpoint_model_or_authorised_audio_was_opened",
            "dyld_shared_cache_and_transient_load_coverage_remain_incomplete",
            "no_public_cli_tui_simple_studio_or_source_graph_route",
        ],
    }
    document = {
        **payload,
        "evidence_sha256": hashlib.sha256(_canonical_json(payload)).hexdigest(),
    }
    encoded = _canonical_json(document)
    if b'"pid"' in encoded or b'"pgid"' in encoded or b'"paths"' in encoded:
        raise RuntimeError("fixed model-free evidence retained a private field")
    if b'"/' in encoded or b"://" in encoded:
        raise RuntimeError("fixed model-free evidence retained a path or URL")
    return _freeze(document)


def _measure_fixed_bindings(
    *,
    runtime: Path,
    process_image: Path,
    provider: Path,
    worker: Path,
) -> Mapping[str, Any]:
    return _freeze(
        {
            "runtime": _measure_regular_file(runtime, _MAXIMUM_RUNTIME_BYTES),
            "process_image": _measure_regular_file(
                process_image,
                _MAXIMUM_RUNTIME_BYTES,
            ),
            "sandbox_provider": _measure_regular_file(
                provider,
                _MAXIMUM_PROVIDER_BYTES,
            ),
            "worker": _measure_regular_file(worker, _MAXIMUM_WORKER_BYTES),
        }
    )


def _measure_regular_file(path: Path, maximum_bytes: int) -> Mapping[str, Any]:
    state = path.stat()
    if not stat.S_ISREG(state.st_mode) or not 1 <= state.st_size <= maximum_bytes:
        raise ValueError("fixed model-free binding file differs")
    content = _read_bounded_file(path, limit=maximum_bytes)
    after = path.stat()
    if (state.st_dev, state.st_ino, state.st_size, state.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise RuntimeError("fixed model-free binding changed during measurement")
    return _freeze(
        {
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "mode": stat.S_IMODE(state.st_mode),
            "uid": state.st_uid,
        }
    )


def _read_bounded_file(path: Path, *, limit: int) -> bytes:
    with path.open("rb") as handle:
        content = handle.read(limit + 1)
    if len(content) > limit:
        raise ValueError("fixed model-free file exceeds its bound")
    return content


def _pread_exact(descriptor: int, byte_count: int) -> bytes:
    received = bytearray()
    offset = 0
    while len(received) < byte_count:
        block = os.pread(descriptor, byte_count - len(received), offset)
        if not block:
            break
        received.extend(block)
        offset += len(block)
    return bytes(received)


def _owner_terminal(native_owner: Any) -> bool:
    return bool(
        getattr(native_owner, "leader_reaped", False) is True
        and getattr(native_owner, "group_empty", False) is True
        and getattr(native_owner, "ownership_released", False) is True
        and getattr(native_owner, "ownership_lost", True) is False
    )


def _terminal_cleanup_complete(value: Mapping[str, Any] | None) -> bool:
    return bool(
        value is not None
        and value.get("leader_reaped") is True
        and value.get("group_empty") is True
        and value.get("ownership_released") is True
        and value.get("ownership_lost") is False
    )


def _close_if_open(descriptor: int) -> None:
    if type(descriptor) is not int or descriptor < 0:
        return
    try:
        os.close(descriptor)
    except OSError:
        pass


def _require_sha(value: Any, label: str) -> None:
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise ValueError(f"fixed model-free {label} hash differs")


__all__: tuple[str, ...] = ()
