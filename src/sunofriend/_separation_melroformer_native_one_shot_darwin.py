"""Private one-shot transport owner for the fixed native Kim coordinator.

This module owns the remaining parent-side request/result file assembly for
one already-authorised execution.  It does not create a checkpoint lease,
mint trust records, choose audio, expose a command or change product state.
"""

from __future__ import annotations

import errno
import fcntl
import os
import stat
from pathlib import Path
from typing import Any, Mapping, Sequence

from ._separation_melroformer_native_coordinator_darwin import (
    _coordinate_reserved_private_melroformer_native_worker_darwin,
)
from ._separation_melroformer_native_transport import (
    _encode_private_melroformer_native_request,
    _validate_private_melroformer_native_request,
)


__all__: tuple[str, ...] = ()

_REQUEST_NAME = "request.frame"
_RESULT_NAME = "result.frame"
_DIRECTORY_MODE = 0o700
_FILE_MODE = 0o600


class _PrivateMelroformerNativeOneShotFailure(RuntimeError):
    """One private transport attempt failed after bounded cleanup."""

    def __init__(
        self,
        *,
        primary_error: BaseException,
        cleanup_stages: Sequence[str] = (),
        cleanup_errors: Sequence[BaseException] = (),
    ) -> None:
        super().__init__("private Kim native one-shot transport failed")
        self.primary_error = primary_error
        self.cleanup_stages = tuple(cleanup_stages)
        self.cleanup_errors = tuple(cleanup_errors)


def _run_reserved_private_melroformer_native_one_shot_darwin(
    trusted_lease: Any,
    *,
    trusted_reservation: Any,
    current_lease_observation: Any,
    trusted_native_session: Any,
    native_session_observation: Any,
    request: Mapping[str, Any],
    transport_directory: str | Path,
) -> Mapping[str, Any]:
    """Prepare exact fd3/fd4 files and call the sole fixed coordinator.

    The caller must already hold every live trust object and must have created
    the fresh owner-only output staging named by ``request``.  This function
    creates a separate fresh owner-only transport directory, supplies distinct
    read/write descriptions for one result inode, and removes the transport
    files after the coordinator returns or fails.
    """

    checked_request = _validate_private_melroformer_native_request(request)
    directory = Path(transport_directory)
    _validate_transport_path(directory, request=checked_request)

    parent_descriptor: int | None = None
    directory_descriptor: int | None = None
    request_read_descriptor: int | None = None
    result_write_descriptor: int | None = None
    result_read_descriptor: int | None = None
    directory_created = False
    request_created = False
    result_created = False
    primary_error: BaseException | None = None
    receipt: Mapping[str, Any] | None = None
    cleanup_stages: list[str] = []
    cleanup_errors: list[BaseException] = []

    try:
        parent_descriptor = _open_owner_only_directory(directory.parent)
        os.mkdir(
            directory.name,
            mode=_DIRECTORY_MODE,
            dir_fd=parent_descriptor,
        )
        directory_created = True
        directory_descriptor = _open_owner_only_child_directory(
            parent_descriptor,
            directory.name,
        )
        frame = _encode_private_melroformer_native_request(checked_request)
        request_write_descriptor = _create_empty_file(
            directory_descriptor,
            _REQUEST_NAME,
        )
        request_created = True
        try:
            _write_exact_file(request_write_descriptor, frame)
        finally:
            os.close(request_write_descriptor)
        request_read_descriptor = _open_file(
            directory_descriptor,
            _REQUEST_NAME,
            os.O_RDONLY,
        )
        result_write_descriptor = _create_empty_file(
            directory_descriptor,
            _RESULT_NAME,
        )
        result_created = True
        result_read_descriptor = _open_file(
            directory_descriptor,
            _RESULT_NAME,
            os.O_RDONLY,
        )
        _validate_transport_geometry(
            request_read_descriptor=request_read_descriptor,
            result_write_descriptor=result_write_descriptor,
            result_read_descriptor=result_read_descriptor,
            request_frame=frame,
        )
        receipt = _coordinate_reserved_private_melroformer_native_worker_darwin(
            trusted_lease,
            trusted_reservation=trusted_reservation,
            current_lease_observation=current_lease_observation,
            trusted_native_session=trusted_native_session,
            native_session_observation=native_session_observation,
            request=checked_request,
            staging_directory=checked_request["paths"]["staging_directory"],
            request_read_descriptor=request_read_descriptor,
            result_write_descriptor=result_write_descriptor,
            result_read_descriptor=result_read_descriptor,
        )
    except BaseException as error:
        primary_error = error
    finally:
        for descriptor in (
            request_read_descriptor,
            result_write_descriptor,
            result_read_descriptor,
        ):
            _cleanup_call(
                "transport_descriptor_close",
                lambda descriptor=descriptor: _close_if_open(descriptor),
                cleanup_stages,
                cleanup_errors,
            )
        if directory_descriptor is not None:
            if request_created:
                _cleanup_call(
                    "request_frame_unlink",
                    lambda: os.unlink(
                        _REQUEST_NAME,
                        dir_fd=directory_descriptor,
                    ),
                    cleanup_stages,
                    cleanup_errors,
                )
            if result_created:
                _cleanup_call(
                    "result_frame_unlink",
                    lambda: os.unlink(
                        _RESULT_NAME,
                        dir_fd=directory_descriptor,
                    ),
                    cleanup_stages,
                    cleanup_errors,
                )
            _cleanup_call(
                "transport_directory_descriptor_close",
                lambda: _close_if_open(directory_descriptor),
                cleanup_stages,
                cleanup_errors,
            )
            directory_descriptor = None
        if directory_created and parent_descriptor is not None:
            _cleanup_call(
                "transport_directory_remove",
                lambda: os.rmdir(
                    directory.name,
                    dir_fd=parent_descriptor,
                ),
                cleanup_stages,
                cleanup_errors,
            )
        _cleanup_call(
            "transport_parent_descriptor_close",
            lambda: _close_if_open(parent_descriptor),
            cleanup_stages,
            cleanup_errors,
        )

    if primary_error is not None or cleanup_errors:
        if primary_error is None:
            primary_error = RuntimeError(
                "private Kim native transport cleanup was incomplete"
            )
        raise _PrivateMelroformerNativeOneShotFailure(
            primary_error=primary_error,
            cleanup_stages=cleanup_stages,
            cleanup_errors=cleanup_errors,
        ) from primary_error
    if receipt is None:
        raise RuntimeError("private Kim native one-shot returned no receipt")
    return receipt


def _validate_transport_path(
    directory: Path,
    *,
    request: Mapping[str, Any],
) -> None:
    try:
        parent_is_canonical = (
            directory.parent.resolve(strict=True) == directory.parent
        )
    except OSError as error:
        raise ValueError(
            "private Kim native transport parent is unavailable"
        ) from error
    if (
        not directory.is_absolute()
        or directory.name in {"", ".", ".."}
        or not parent_is_canonical
        or str(directory) in set(request["paths"].values())
    ):
        raise ValueError("private Kim native transport path differs")


def _open_owner_only_directory(path: Path) -> int:
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        _require_owner_only_directory(descriptor)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_owner_only_child_directory(parent_descriptor: int, name: str) -> int:
    descriptor = os.open(
        name,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        dir_fd=parent_descriptor,
    )
    try:
        _require_owner_only_directory(descriptor)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _require_owner_only_directory(descriptor: int) -> None:
    value = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(value.st_mode)
        or value.st_uid != os.getuid()
        or stat.S_IMODE(value.st_mode) & 0o077
        or os.get_inheritable(descriptor)
    ):
        raise ValueError("private Kim native transport root is not owner-only")


def _write_exact_file(descriptor: int, content: bytes) -> None:
    offset = 0
    while offset < len(content):
        written = os.write(descriptor, content[offset:])
        if written <= 0:
            raise OSError(errno.EIO, "private transport write stopped")
        offset += written
    os.fsync(descriptor)


def _create_empty_file(directory_descriptor: int, name: str) -> int:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            _FILE_MODE,
            dir_fd=directory_descriptor,
        )
        os.set_inheritable(descriptor, False)
        return descriptor
    except BaseException:
        _close_if_open(descriptor)
        if descriptor is not None:
            try:
                os.unlink(name, dir_fd=directory_descriptor)
            except OSError:
                pass
        raise


def _open_file(directory_descriptor: int, name: str, flags: int) -> int:
    descriptor = os.open(
        name,
        flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        dir_fd=directory_descriptor,
    )
    os.set_inheritable(descriptor, False)
    return descriptor


def _validate_transport_geometry(
    *,
    request_read_descriptor: int,
    result_write_descriptor: int,
    result_read_descriptor: int,
    request_frame: bytes,
) -> None:
    request_state = os.fstat(request_read_descriptor)
    result_write_state = os.fstat(result_write_descriptor)
    result_read_state = os.fstat(result_read_descriptor)
    if (
        fcntl.fcntl(request_read_descriptor, fcntl.F_GETFL) & os.O_ACCMODE
        != os.O_RDONLY
        or fcntl.fcntl(result_write_descriptor, fcntl.F_GETFL) & os.O_ACCMODE
        != os.O_WRONLY
        or fcntl.fcntl(result_read_descriptor, fcntl.F_GETFL) & os.O_ACCMODE
        != os.O_RDONLY
        or any(
            os.get_inheritable(descriptor)
            for descriptor in (
                request_read_descriptor,
                result_write_descriptor,
                result_read_descriptor,
            )
        )
        or not stat.S_ISREG(request_state.st_mode)
        or not stat.S_ISREG(result_write_state.st_mode)
        or not stat.S_ISREG(result_read_state.st_mode)
        or request_state.st_nlink != 1
        or result_write_state.st_nlink != 1
        or result_read_state.st_nlink != 1
        or request_state.st_size != len(request_frame)
        or result_write_state.st_size != 0
        or (result_write_state.st_dev, result_write_state.st_ino)
        != (result_read_state.st_dev, result_read_state.st_ino)
        or os.pread(request_read_descriptor, len(request_frame), 0)
        != request_frame
    ):
        raise ValueError("private Kim native transport geometry differs")


def _cleanup_call(
    stage: str,
    operation: Any,
    stages: list[str],
    errors: list[BaseException],
) -> None:
    try:
        operation()
    except BaseException as error:
        stages.append(stage)
        errors.append(error)


def _close_if_open(descriptor: int | None) -> None:
    if descriptor is None:
        return
    try:
        os.close(descriptor)
    except OSError as error:
        if error.errno != errno.EBADF:
            raise
