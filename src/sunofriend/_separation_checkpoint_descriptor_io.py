"""Low-level descriptor I/O for private checkpoint leases."""

import hashlib
import os

from .separation_checkpoint_inspection import MAX_CHECKPOINT_BYTES


def _hash_descriptor(descriptor: int, maximum_bytes: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    try:
        while True:
            chunk = os.pread(
                descriptor,
                min(1024 * 1024, maximum_bytes + 1 - count),
                count,
            )
            if not chunk:
                break
            count += len(chunk)
            if count > maximum_bytes or count > MAX_CHECKPOINT_BYTES:
                raise ValueError("checkpoint exceeds retained byte limit")
            digest.update(chunk)
        return digest.hexdigest(), count
    finally:
        if os.lseek(descriptor, 0, os.SEEK_SET) != 0:
            raise ValueError("checkpoint descriptor offset reset failed")


def _file_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_uid,
    )


def _file_identity_document(
    value: tuple[int, ...],
) -> dict[str, int]:
    return {
        "device": value[0],
        "inode": value[1],
        "mode": value[2],
        "links": value[3],
        "bytes": value[4],
        "mtime_ns": value[5],
        "ctime_ns": value[6],
        "uid": value[7],
    }


def _close_if_owned(
    descriptor: int,
    expected_devino: tuple[int, ...],
) -> None:
    try:
        observed = os.fstat(descriptor)
        if (observed.st_dev, observed.st_ino) == expected_devino:
            os.close(descriptor)
    except OSError:
        pass
