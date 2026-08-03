"""Private authority owner for one exact native Kim evaluation attempt.

This is the final developer-only composition layer around the fixed native
session, private checkpoint lease and one-shot transport.  It measures the
already-approved local inputs, creates one fresh owner-only attempt tree and
returns only the coordinator's path-free receipt.  It is intentionally absent
from every public CLI, TUI, Simple, Studio and source-graph route.
"""

from __future__ import annotations

import hashlib
import math
import os
import platform
import stat
import time
import wave
from pathlib import Path
from typing import Any, Mapping

from . import _separation_melroformer_checkpoint_lease as _lease
from . import _separation_melroformer_native_session_darwin as _session
from ._separation_checkpoint_canonical import (
    canonical_json_bytes as _canonical_json,
    plain as _plain,
)
from ._separation_melroformer_artifacts import _inspect_companion_files
from ._separation_melroformer_native_one_shot_darwin import (
    _run_reserved_private_melroformer_native_one_shot_darwin,
)
from ._separation_melroformer_native_transport import (
    _build_private_melroformer_native_request,
)
from ._separation_melroformer_native_worker import (
    WORKER_RELATIVE_PATH,
    _companion_manifest_identity,
    _regular_file_identity,
)
from ._separation_melroformer_runtime_evidence import (
    SOURCE_MANIFEST_SHA256,
    _read_exact_regular_file,
    _verify_private_melroformer_source_tree,
)
from ._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)
from ._separation_worker_request_v2_values import _validate_path_free


__all__: tuple[str, ...] = ()

_ATTEMPT_DIRECTORY_MODE = 0o700
_STAGING_NAME = "staging"
_TRANSPORT_NAME = "transport"
_NATIVE_CACHE_NAME = "native-cache"
_RECEIPT_NAME = "native-attempt-receipt.json"
_EVIDENCE_NAME = "native-attempt-evidence.json"
_EVIDENCE_SCHEMA = "sunofriend.private-kim-native-attempt-evidence.v1"
_TIMING_NAME = "native-attempt-timing.json"
_TIMING_SCHEMA = "sunofriend.private-kim-native-attempt-timing.v1"
_TIMING_STAGES = (
    "input_measurement",
    "attempt_tree_creation",
    "native_session_open",
    "checkpoint_lease_acquire",
    "checkpoint_fd5_reserve",
    "native_one_shot",
    "terminal_receipt_persistence",
    "output_evidence_persistence",
)
_MAXIMUM_WORKER_BYTES = 1024 * 1024
_MAXIMUM_AUTHORISATION_REPORT_BYTES = 2 * 1024 * 1024
_MAXIMUM_RECEIPT_BYTES = 2 * 1024 * 1024


class _PrivateMelroformerNativeAttemptFailure(RuntimeError):
    """One authority-composed attempt failed after cleanup was attempted."""

    def __init__(
        self,
        *,
        primary_error: BaseException,
        cleanup_stages: tuple[str, ...] = (),
        cleanup_errors: tuple[BaseException, ...] = (),
    ) -> None:
        super().__init__("private Kim native authority attempt failed")
        self.primary_error = primary_error
        self.cleanup_stages = cleanup_stages
        self.cleanup_errors = cleanup_errors


def _run_private_melroformer_native_attempt_darwin(
    *,
    run_nonce: str,
    repository_root: str | Path,
    runtime_launcher_path: str | Path,
    source_root: str | Path,
    checkpoint_path: str | Path,
    companion_root: str | Path,
    authorisation_report_path: str | Path,
    authorisation_report_sha256: str,
    attempt_directory: str | Path,
    device: str,
) -> Mapping[str, Any]:
    """Own one exact private authority chain and leave verified output staged."""

    if platform.system() != "Darwin":
        raise RuntimeError("private Kim native attempt requires macOS")
    attempt_started = time.monotonic()
    stage_seconds: dict[str, float] = {}
    attempt = Path(attempt_directory)
    if not attempt.is_absolute() or attempt.name in {"", ".", ".."}:
        raise ValueError("private Kim attempt path must be absolute and fresh")
    parent = _canonical_directory(attempt.parent, "attempt parent")
    if attempt.exists() or attempt.is_symlink():
        raise ValueError("private Kim attempt path must not exist")

    staging = attempt / _STAGING_NAME
    runtime, request = _observe_stage(
        stage_seconds,
        "input_measurement",
        lambda: _prepare_private_melroformer_native_request(
            run_nonce=run_nonce,
            repository_root=repository_root,
            runtime_launcher_path=runtime_launcher_path,
            source_root=source_root,
            checkpoint_path=checkpoint_path,
            companion_root=companion_root,
            authorisation_report_path=authorisation_report_path,
            authorisation_report_sha256=authorisation_report_sha256,
            staging_directory=staging,
            device=device,
        ),
    )
    _observe_stage(
        stage_seconds,
        "attempt_tree_creation",
        lambda: _create_attempt_tree(parent, attempt.name),
    )

    trusted_lease: Any | None = None
    reservation: Any | None = None
    lease_observation: Any | None = None
    primary_error: BaseException | None = None
    receipt: Mapping[str, Any] | None = None
    cleanup_stages: list[str] = []
    cleanup_errors: list[BaseException] = []
    try:
        native_session, native_observation = _observe_stage(
            stage_seconds,
            "native_session_open",
            lambda: _session._open_verified_private_melroformer_native_session(
                runtime_launcher_path=runtime,
                cache_root=attempt / _NATIVE_CACHE_NAME,
            ),
        )
        trusted_lease, lease_observation = _observe_stage(
            stage_seconds,
            "checkpoint_lease_acquire",
            lambda: _lease._acquire_private_melroformer_checkpoint_lease(request),
        )
        reservation = _observe_stage(
            stage_seconds,
            "checkpoint_fd5_reserve",
            lambda: _lease._reserve_private_melroformer_checkpoint_fd5(
                trusted_lease,
                current_lease_observation=lease_observation,
            ),
        )
        receipt = _observe_stage(
            stage_seconds,
            "native_one_shot",
            lambda: _run_reserved_private_melroformer_native_one_shot_darwin(
                trusted_lease,
                trusted_reservation=reservation,
                current_lease_observation=lease_observation,
                trusted_native_session=native_session,
                native_session_observation=native_observation,
                request=request,
                transport_directory=attempt / _TRANSPORT_NAME,
            ),
        )
        _observe_stage(
            stage_seconds,
            "terminal_receipt_persistence",
            lambda: _write_attempt_receipt(attempt, receipt),
        )
        evidence = _observe_stage(
            stage_seconds,
            "output_evidence_persistence",
            lambda: _write_attempt_evidence(
                attempt,
                request=request,
                receipt=receipt,
            ),
        )
        _write_attempt_timing(
            attempt,
            request=request,
            receipt=receipt,
            evidence=evidence,
            stage_seconds=stage_seconds,
            observed_total_seconds=_elapsed_seconds(attempt_started),
        )
    except BaseException as error:
        primary_error = error
    if primary_error is not None:
        if trusted_lease is not None:
            _cleanup(
                "checkpoint_authority_terminal",
                lambda: _terminalize_checkpoint_authority(
                    trusted_lease,
                    reservation,
                ),
                cleanup_stages,
                cleanup_errors,
            )
        raise _PrivateMelroformerNativeAttemptFailure(
            primary_error=primary_error,
            cleanup_stages=tuple(cleanup_stages),
            cleanup_errors=tuple(cleanup_errors),
        ) from primary_error
    if receipt is None:
        raise RuntimeError("private Kim native attempt returned no receipt")
    return receipt


def _observe_stage(
    stages: dict[str, float],
    name: str,
    action: Any,
) -> Any:
    if name not in _TIMING_STAGES or name in stages:
        raise ValueError("private Kim timing stage differs")
    started = time.monotonic()
    result = action()
    stages[name] = _elapsed_seconds(started)
    return result


def _elapsed_seconds(started: float) -> float:
    elapsed = time.monotonic() - started
    if not math.isfinite(elapsed) or not 0.0 <= elapsed <= 3_600.0:
        raise ValueError("private Kim timing observation differs")
    return round(elapsed, 6)


def _prepare_private_melroformer_native_request(
    *,
    run_nonce: str,
    repository_root: str | Path,
    runtime_launcher_path: str | Path,
    source_root: str | Path,
    checkpoint_path: str | Path,
    companion_root: str | Path,
    authorisation_report_path: str | Path,
    authorisation_report_sha256: str,
    staging_directory: str | Path,
    device: str,
) -> tuple[Path, Mapping[str, Any]]:
    repository = _canonical_directory(repository_root, "repository root")
    runtime = _explicit_runtime_launcher(runtime_launcher_path)
    source = _canonical_directory(source_root, "source root")
    checkpoint = _canonical_file(checkpoint_path, "checkpoint")
    companions = _canonical_directory(companion_root, "companion root")
    authorisation = _canonical_file(
        authorisation_report_path,
        "authorisation report",
    )
    staging = Path(staging_directory)
    if not staging.is_absolute():
        raise ValueError("private Kim staging path must be absolute")

    _verify_private_melroformer_source_tree(source)
    report_state = authorisation.lstat()
    _read_exact_regular_file(
        authorisation,
        expected_sha256=authorisation_report_sha256,
        expected_bytes=report_state.st_size,
    )
    if not 1 <= report_state.st_size <= _MAXIMUM_AUTHORISATION_REPORT_BYTES:
        raise ValueError("private Kim authorisation report size differs")
    companion_identity = _companion_manifest_identity(
        _inspect_companion_files(companions)
    )
    worker_identity = _regular_file_identity(
        repository / WORKER_RELATIVE_PATH,
        maximum_bytes=_MAXIMUM_WORKER_BYTES,
    )
    request = _build_private_melroformer_native_request(
        run_nonce=run_nonce,
        paths={
            "repository_root": str(repository),
            "source_root": str(source),
            "checkpoint_path": str(checkpoint),
            "companion_root": str(companions),
            "authorisation_report_path": str(authorisation),
            "staging_directory": str(staging),
        },
        identities={
            "worker_source_sha256": worker_identity["sha256"],
            "checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
            "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
            "authorisation_report_sha256": authorisation_report_sha256,
            "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
            "companion_manifest_sha256": companion_identity[
                "manifest_sha256"
            ],
        },
        device=device,
    )
    return runtime, request


def _canonical_directory(value: str | Path, label: str) -> Path:
    path = Path(value)
    try:
        resolved = path.resolve(strict=True)
        state = path.lstat()
    except OSError as error:
        raise ValueError(f"private Kim {label} is unavailable") from error
    if (
        not path.is_absolute()
        or resolved != path
        or stat.S_ISLNK(state.st_mode)
        or not stat.S_ISDIR(state.st_mode)
    ):
        raise ValueError(f"private Kim {label} differs")
    return path


def _canonical_file(value: str | Path, label: str) -> Path:
    path = Path(value)
    try:
        resolved = path.resolve(strict=True)
        state = path.lstat()
    except OSError as error:
        raise ValueError(f"private Kim {label} is unavailable") from error
    if (
        not path.is_absolute()
        or resolved != path
        or stat.S_ISLNK(state.st_mode)
        or not stat.S_ISREG(state.st_mode)
        or state.st_nlink != 1
    ):
        raise ValueError(f"private Kim {label} differs")
    return path


def _explicit_runtime_launcher(value: str | Path) -> Path:
    path = Path(value)
    try:
        target = path.resolve(strict=True)
        state = target.stat()
    except OSError as error:
        raise ValueError("private Kim AI runtime launcher is unavailable") from error
    if (
        not path.is_absolute()
        or not stat.S_ISREG(state.st_mode)
        or not os.access(path, os.X_OK)
    ):
        raise ValueError("private Kim AI runtime launcher differs")
    return path


def _open_dir(path: Path) -> int:
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    os.set_inheritable(descriptor, False)
    return descriptor


def _create_attempt_tree(parent: Path, name: str) -> None:
    parent_descriptor = _open_dir(parent)
    attempt_descriptor: int | None = None
    staging_descriptor: int | None = None
    try:
        os.mkdir(
            name,
            mode=_ATTEMPT_DIRECTORY_MODE,
            dir_fd=parent_descriptor,
        )
        attempt_descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_descriptor,
        )
        os.set_inheritable(attempt_descriptor, False)
        os.fchmod(attempt_descriptor, _ATTEMPT_DIRECTORY_MODE)
        _require_owner_only_directory(attempt_descriptor)
        os.mkdir(
            _STAGING_NAME,
            mode=_ATTEMPT_DIRECTORY_MODE,
            dir_fd=attempt_descriptor,
        )
        staging_descriptor = os.open(
            _STAGING_NAME,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=attempt_descriptor,
        )
        os.set_inheritable(staging_descriptor, False)
        os.fchmod(staging_descriptor, _ATTEMPT_DIRECTORY_MODE)
        _require_owner_only_directory(staging_descriptor)
    finally:
        if staging_descriptor is not None:
            os.close(staging_descriptor)
        if attempt_descriptor is not None:
            os.close(attempt_descriptor)
        os.close(parent_descriptor)


def _require_owner_only_directory(descriptor: int) -> None:
    state = os.fstat(descriptor)
    if (
        os.get_inheritable(descriptor)
        or not stat.S_ISDIR(state.st_mode)
        or state.st_uid != os.geteuid()
        or stat.S_IMODE(state.st_mode) != _ATTEMPT_DIRECTORY_MODE
    ):
        raise ValueError("private Kim attempt directory is unsafe")


def _terminalize_checkpoint_authority(
    trusted_lease: Any,
    trusted_reservation: Any | None,
) -> None:
    _known, state = _lease._known_state(trusted_lease)
    del _known
    with state.lock:
        if state.status != "retained":
            return
        if state.fd5_reservation is not None:
            if trusted_reservation is None:
                raise RuntimeError(
                    "private Kim fd5 reservation authority is unavailable"
                )
            _lease._release_private_melroformer_checkpoint_fd5(
                trusted_lease,
                trusted_reservation,
            )
        _lease._close_private_melroformer_checkpoint_lease(trusted_lease)


def _write_attempt_receipt(
    attempt: Path,
    receipt: Mapping[str, Any],
) -> None:
    document = _plain(receipt)
    _validate_path_free(document, "private Kim native attempt receipt")
    encoded = _canonical_json(document)
    if not 1 <= len(encoded) <= _MAXIMUM_RECEIPT_BYTES:
        raise ValueError("private Kim native attempt receipt size differs")
    directory_descriptor = _open_dir(attempt)
    descriptor: int | None = None
    try:
        descriptor = os.open(
            _RECEIPT_NAME,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=directory_descriptor,
        )
        os.set_inheritable(descriptor, False)
        offset = 0
        while offset < len(encoded):
            written = os.write(descriptor, encoded[offset:])
            if written <= 0:
                raise RuntimeError("private Kim attempt receipt write stalled")
            offset += written
        os.fsync(descriptor)
        state = os.fstat(descriptor)
        if (
            os.get_inheritable(descriptor)
            or not stat.S_ISREG(state.st_mode)
            or state.st_nlink != 1
            or state.st_uid != os.geteuid()
            or stat.S_IMODE(state.st_mode) != 0o600
            or state.st_size != len(encoded)
        ):
            raise RuntimeError("private Kim attempt receipt file differs")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory_descriptor)


def _write_attempt_evidence(
    attempt: Path,
    *,
    request: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> Mapping[str, Any]:
    receipt_document = _plain(receipt)
    receipt_payload = dict(receipt_document)
    receipt_sha256 = receipt_payload.pop("receipt_sha256", None)
    if (
        receipt_document.get("schema")
        != "sunofriend.private-melroformer-native-coordinator.v1"
        or receipt_document.get("status")
        != "private_native_worker_complete_and_terminal"
        or receipt_document.get("request_sha256")
        != request["request_sha256"]
        or receipt_sha256
        != hashlib.sha256(_canonical_json(receipt_payload)).hexdigest()
        or any(
            value is not True
            for value in receipt_document.get("lifecycle", {}).values()
        )
        or any(
            value is not False
            for value in receipt_document.get("permissions", {}).values()
        )
    ):
        raise ValueError("private Kim native terminal receipt differs")
    outputs = [
        _inspect_attempt_pcm24(attempt, role=role)
        for role in ("instrumental", "vocals")
    ]
    payload = {
        "schema": _EVIDENCE_SCHEMA,
        "status": "private_native_attempt_verified_not_selected",
        "evidence_scope": "private_local_execution_and_output_binding_only",
        "candidate_id": request["candidate_id"],
        "bindings": {
            "request_sha256": request["request_sha256"],
            "terminal_receipt_sha256": receipt_sha256,
            **_plain(request["identities"]),
        },
        "outputs": outputs,
        "conclusion": {
            "native_execution_terminal": True,
            "network_denial_bound_to_model_worker": True,
            "pcm24_quarantine_bound_to_model_worker": True,
            "parent_staging_verification_complete": True,
            "checkpoint_remeasured_and_closed": True,
            "listening_quality_established": False,
        },
        "permissions": {
            "accepted": False,
            "automatic_selection": False,
            "source_graph_activation": False,
            "simple_mode_available": False,
            "studio_import_available": False,
            "product_route_permitted": False,
            "publication_permitted": False,
        },
        "limitations": [
            "evidence_is_private_execution_provenance_not_quality_acceptance",
            "relative_artifact_location_is_fixed_by_schema_not_serialized",
            "gpu_outputs_are_not_claimed_bitwise_repeatable",
            "no_public_cli_tui_simple_studio_or_source_graph_route",
        ],
    }
    document = {
        **payload,
        "evidence_sha256": hashlib.sha256(_canonical_json(payload)).hexdigest(),
    }
    _write_private_json(attempt, _EVIDENCE_NAME, document)
    return document


def _inspect_attempt_pcm24(attempt: Path, *, role: str) -> Mapping[str, Any]:
    if role not in {"instrumental", "vocals"}:
        raise ValueError("private Kim native output role differs")
    path = attempt / "staging" / "quarantine" / "STEMS" / f"{role}.wav"
    state = path.lstat()
    if (
        stat.S_ISLNK(state.st_mode)
        or not stat.S_ISREG(state.st_mode)
        or state.st_nlink != 1
        or state.st_uid != os.geteuid()
        or stat.S_IMODE(state.st_mode) != 0o600
    ):
        raise ValueError("private Kim native PCM24 artifact differs")
    contents = path.read_bytes()
    with wave.open(str(path), "rb") as reader:
        geometry = {
            "sample_rate": reader.getframerate(),
            "channels": reader.getnchannels(),
            "sample_width_bytes": reader.getsampwidth(),
            "frames": reader.getnframes(),
        }
        if reader.getcomptype() != "NONE":
            raise ValueError("private Kim native PCM24 compression differs")
    if geometry != {
        "sample_rate": 44_100,
        "channels": 2,
        "sample_width_bytes": 3,
        "frames": 661_500,
    }:
        raise ValueError("private Kim native PCM24 geometry differs")
    return {
        "role": role,
        "bytes": len(contents),
        "sha256": hashlib.sha256(contents).hexdigest(),
        "geometry": geometry,
    }


def _write_attempt_timing(
    attempt: Path,
    *,
    request: Mapping[str, Any],
    receipt: Mapping[str, Any],
    evidence: Mapping[str, Any],
    stage_seconds: Mapping[str, float],
    observed_total_seconds: float,
) -> Mapping[str, Any]:
    if tuple(stage_seconds) != _TIMING_STAGES:
        raise ValueError("private Kim timing stage order differs")
    checked_stages = {
        name: _checked_timing_value(value) for name, value in stage_seconds.items()
    }
    total = _checked_timing_value(observed_total_seconds)
    if total + 0.000010 < sum(checked_stages.values()):
        raise ValueError("private Kim timing total differs")
    receipt_sha256 = receipt.get("receipt_sha256")
    evidence_sha256 = evidence.get("evidence_sha256")
    if (
        not _is_sha256(receipt_sha256)
        or not _is_sha256(evidence_sha256)
        or receipt.get("request_sha256") != request["request_sha256"]
        or evidence.get("bindings", {}).get("request_sha256")
        != request["request_sha256"]
        or evidence.get("bindings", {}).get("terminal_receipt_sha256")
        != receipt_sha256
    ):
        raise ValueError("private Kim timing bindings differ")
    longest_stage = max(_TIMING_STAGES, key=checked_stages.__getitem__)
    payload = {
        "schema": _TIMING_SCHEMA,
        "status": "private_runtime_observation_not_benchmark",
        "evidence_scope": "private_local_coarse_stage_timing_only",
        "bindings": {
            "request_sha256": request["request_sha256"],
            "terminal_receipt_sha256": receipt_sha256,
            "output_evidence_sha256": evidence_sha256,
        },
        "clock": {
            "source": "time.monotonic",
            "wall_clock_recorded": False,
            "timestamps_recorded": False,
        },
        "stage_order": list(_TIMING_STAGES),
        "stage_seconds": checked_stages,
        "observed_total_through_output_evidence_seconds": total,
        "longest_stage": {
            "name": longest_stage,
            "seconds": checked_stages[longest_stage],
        },
        "semantics": {
            "native_one_shot": (
                "transport, native spawn, model inference, live observation, "
                "staging verification and terminal cleanup"
            ),
            "timing_document_write_included": False,
            "stages_are_coarse_not_profiler_spans": True,
        },
        "permissions": {
            "benchmark_claim": False,
            "performance_acceptance": False,
            "automatic_selection": False,
            "source_graph_activation": False,
            "product_route_permitted": False,
            "publication_permitted": False,
        },
        "limitations": [
            "one_run_is_not_a_runtime_benchmark",
            "coarse_stage_timing_does_not_split_model_load_from_inference",
            "scheduler_cache_and_thermal_state_are_not_controlled",
            "no_paths_pids_wall_clock_or_process_identity_are_recorded",
        ],
    }
    document = {
        **payload,
        "timing_sha256": hashlib.sha256(_canonical_json(payload)).hexdigest(),
    }
    _write_private_json(attempt, _TIMING_NAME, document)
    return document


def _checked_timing_value(value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 3_600.0
    ):
        raise ValueError("private Kim timing value differs")
    return round(float(value), 6)


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _write_private_json(
    attempt: Path,
    name: str,
    document: Mapping[str, Any],
) -> None:
    _validate_path_free(document, "private Kim native attempt evidence")
    encoded = _canonical_json(document)
    if not 1 <= len(encoded) <= _MAXIMUM_RECEIPT_BYTES:
        raise ValueError("private Kim native attempt evidence size differs")
    directory_descriptor = _open_dir(attempt)
    descriptor: int | None = None
    try:
        descriptor = os.open(
            name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=directory_descriptor,
        )
        os.set_inheritable(descriptor, False)
        offset = 0
        while offset < len(encoded):
            written = os.write(descriptor, encoded[offset:])
            if written <= 0:
                raise RuntimeError("private Kim attempt evidence write stalled")
            offset += written
        os.fsync(descriptor)
        state = os.fstat(descriptor)
        if (
            os.get_inheritable(descriptor)
            or not stat.S_ISREG(state.st_mode)
            or state.st_nlink != 1
            or state.st_uid != os.geteuid()
            or stat.S_IMODE(state.st_mode) != 0o600
            or state.st_size != len(encoded)
        ):
            raise RuntimeError("private Kim attempt evidence file differs")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory_descriptor)


def _cleanup(
    stage: str,
    action: Any,
    stages: list[str],
    errors: list[BaseException],
) -> None:
    try:
        action()
    except BaseException as error:
        stages.append(stage)
        errors.append(error)
