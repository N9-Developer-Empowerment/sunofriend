"""Private authority owner for one exact native Kim evaluation attempt.

This is the final developer-only composition layer around the fixed native
session, private checkpoint lease and one-shot transport.  It measures the
already-approved local inputs, creates one fresh owner-only attempt tree and
returns only the coordinator's path-free receipt.  It is intentionally absent
from every public CLI, TUI, Simple, Studio and source-graph route.
"""

from __future__ import annotations

import os
import platform
import stat
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
    repository = _canonical_directory(repository_root, "repository root")
    runtime = _explicit_runtime_launcher(runtime_launcher_path)
    source = _canonical_directory(source_root, "source root")
    checkpoint = _canonical_file(checkpoint_path, "checkpoint")
    companions = _canonical_directory(companion_root, "companion root")
    authorisation = _canonical_file(
        authorisation_report_path,
        "authorisation report",
    )
    attempt = Path(attempt_directory)
    if not attempt.is_absolute() or attempt.name in {"", ".", ".."}:
        raise ValueError("private Kim attempt path must be absolute and fresh")
    parent = _canonical_directory(attempt.parent, "attempt parent")
    if attempt.exists() or attempt.is_symlink():
        raise ValueError("private Kim attempt path must not exist")

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
    worker = repository / WORKER_RELATIVE_PATH
    worker_identity = _regular_file_identity(
        worker,
        maximum_bytes=_MAXIMUM_WORKER_BYTES,
    )

    staging = attempt / _STAGING_NAME
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
    _create_attempt_tree(parent, attempt.name)

    trusted_lease: Any | None = None
    reservation: Any | None = None
    lease_observation: Any | None = None
    primary_error: BaseException | None = None
    receipt: Mapping[str, Any] | None = None
    cleanup_stages: list[str] = []
    cleanup_errors: list[BaseException] = []
    try:
        native_session, native_observation = (
            _session._open_verified_private_melroformer_native_session(
                runtime_launcher_path=runtime,
                cache_root=attempt / _NATIVE_CACHE_NAME,
            )
        )
        trusted_lease, lease_observation = (
            _lease._acquire_private_melroformer_checkpoint_lease(request)
        )
        reservation = _lease._reserve_private_melroformer_checkpoint_fd5(
            trusted_lease,
            current_lease_observation=lease_observation,
        )
        receipt = _run_reserved_private_melroformer_native_one_shot_darwin(
            trusted_lease,
            trusted_reservation=reservation,
            current_lease_observation=lease_observation,
            trusted_native_session=native_session,
            native_session_observation=native_observation,
            request=request,
            transport_directory=attempt / _TRANSPORT_NAME,
        )
        _write_attempt_receipt(attempt, receipt)
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
