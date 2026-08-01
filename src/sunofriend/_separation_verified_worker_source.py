"""Open one private Python worker once and execute those verified bytes.

The caller hashes a non-following regular-file descriptor, rewinds that same
open file description and supplies it as Python's standard-input script.  A
pathname replacement after the open therefore cannot change the code Python
reads.  The provider and Python runtime are still launched by pathname and
remain separate, explicit TOCTOU limitations.
"""

from __future__ import annotations

import hashlib
import os
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO, Iterator, Mapping


_MAXIMUM_WORKER_BYTES = 1024 * 1024


@contextmanager
def _verified_worker_source(
    path: str | Path,
    *,
    expected_identity: Mapping[str, Any],
) -> Iterator[BinaryIO]:
    """Yield the exact verified worker as a rewound binary input stream."""

    worker = Path(path)
    attached = worker.lstat()
    _validate_worker_stat(attached)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(worker, flags)
    try:
        os.set_inheritable(descriptor, False)
        opened = os.fstat(descriptor)
        if os.get_inheritable(descriptor) or _stat_identity(opened) != _stat_identity(
            attached
        ):
            raise ValueError("private worker changed before descriptor binding")
        identity = _descriptor_identity(descriptor)
        if identity != {
            "bytes": expected_identity.get("bytes"),
            "sha256": expected_identity.get("sha256"),
        }:
            raise ValueError("private worker descriptor identity differs")
        os.lseek(descriptor, 0, os.SEEK_SET)
        with os.fdopen(descriptor, "rb", buffering=0, closefd=False) as stream:
            yield stream
        after = os.fstat(descriptor)
        if _stat_identity(after) != _stat_identity(opened):
            raise RuntimeError("private worker descriptor changed during execution")
        if _descriptor_identity(descriptor) != identity:
            raise RuntimeError("private worker descriptor bytes changed during execution")
        current = worker.lstat()
        if _stat_identity(current) != _stat_identity(attached):
            raise RuntimeError("private worker path changed during execution")
    finally:
        os.close(descriptor)


def _descriptor_identity(descriptor: int) -> dict[str, Any]:
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    size = 0
    while block := os.read(descriptor, 1024 * 1024):
        size += len(block)
        if size > _MAXIMUM_WORKER_BYTES:
            raise ValueError("private worker exceeds its byte bound")
        digest.update(block)
    return {"bytes": size, "sha256": digest.hexdigest()}


def _validate_worker_stat(value: os.stat_result) -> None:
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_nlink != 1
        or not 1 <= value.st_size <= _MAXIMUM_WORKER_BYTES
    ):
        raise ValueError("private worker must be one bounded single-link regular file")


def _stat_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


__all__ = ["_verified_worker_source"]
