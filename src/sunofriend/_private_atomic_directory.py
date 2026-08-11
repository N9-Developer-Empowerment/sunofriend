"""Small fail-closed primitives for private atomic directory publication."""

from __future__ import annotations

import ctypes
import errno
import os
from pathlib import Path
import sys
from typing import Any


class AtomicDirectoryUnavailable(RuntimeError):
    """Raised when the platform lacks a required atomic-directory primitive."""


class UnsafeDirectoryEntryName(ValueError):
    """Raised when a directory entry is not one safe basename."""


class UnsafeDirectoryPath(ValueError):
    """Raised when an absolute directory path cannot be traversed safely."""


RenameImplementation = tuple[Any, int]


def require_safe_directory_entry_name(value: str) -> str:
    """Return one directory-entry basename without path syntax."""

    if (
        not isinstance(value, str)
        or value in {"", ".", ".."}
        or "\0" in value
        or Path(value).name != value
    ):
        raise UnsafeDirectoryEntryName("private directory entry name differs")
    return value


def open_absolute_directory_nofollow(path: str | Path) -> int:
    """Open every component of one absolute directory without following links."""

    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise AtomicDirectoryUnavailable("no-follow directory opens are unavailable")
    absolute = Path(path)
    if not absolute.is_absolute() or any(
        part in {".", ".."} for part in absolute.parts
    ):
        raise UnsafeDirectoryPath("private absolute directory path differs")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | no_follow
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = os.open("/", flags)
    try:
        os.set_inheritable(descriptor, False)
        for component in absolute.parts[1:]:
            next_descriptor = os.open(component, flags, dir_fd=descriptor)
            os.set_inheritable(next_descriptor, False)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def exclusive_directory_rename_implementation() -> RenameImplementation:
    """Resolve the platform's atomic no-replace directory rename."""

    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        function = getattr(library, "renameatx_np", None)
        flag = 0x00000004  # RENAME_EXCL from sys/stdio.h.
    elif sys.platform.startswith("linux"):
        function = getattr(library, "renameat2", None)
        flag = 0x00000001  # RENAME_NOREPLACE from linux/fs.h.
    else:
        function = None
        flag = 0
    if function is None:
        raise AtomicDirectoryUnavailable(
            "atomic exclusive directory publication is unavailable"
        )
    function.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    function.restype = ctypes.c_int
    return function, flag


def rename_directory_no_replace_at(
    parent_descriptor: int,
    source_name: str,
    destination_name: str,
    *,
    implementation: RenameImplementation | None = None,
) -> None:
    """Rename within one held parent descriptor without replacing a name."""

    source = require_safe_directory_entry_name(source_name)
    destination = require_safe_directory_entry_name(destination_name)
    function, flag = implementation or exclusive_directory_rename_implementation()
    result = function(
        parent_descriptor,
        os.fsencode(source),
        parent_descriptor,
        os.fsencode(destination),
        flag,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(
            error_number,
            os.strerror(error_number),
            destination,
        )
    raise OSError(error_number, os.strerror(error_number), destination)


__all__ = [
    "AtomicDirectoryUnavailable",
    "RenameImplementation",
    "UnsafeDirectoryEntryName",
    "UnsafeDirectoryPath",
    "exclusive_directory_rename_implementation",
    "open_absolute_directory_nofollow",
    "rename_directory_no_replace_at",
    "require_safe_directory_entry_name",
]
