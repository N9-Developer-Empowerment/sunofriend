"""Exact local artifact identities shared by the private MelRoFormer worker."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Any

from ._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)


APPROVAL_RECORDED_AT = "2026-08-01"
CONFIG_NAME = "config.json"
CONFIG_BYTES = 833
CONFIG_SHA256 = "3300eacac960ab46933ef6df6b838eb35de1f0321db9242c1b06e6d2a6a62b58"
LICENSE_NAME = "LICENSE"
LICENSE_BYTES = 1_500
LICENSE_SHA256 = "1aa245b55067df5c63c847894e7040f76fa79ddde83e9e5ed8a5c29ef1865c14"


def _inspect_companion_files(
    value: str | Path,
    *,
    config_bytes: int = CONFIG_BYTES,
    config_sha256: str = CONFIG_SHA256,
    license_bytes: int = LICENSE_BYTES,
    license_sha256: str = LICENSE_SHA256,
) -> dict[str, Any]:
    root = Path(value).expanduser().absolute()
    if not root.is_dir() or root.is_symlink():
        raise ValueError("MelBand-RoFormer companion root must be a directory")
    files = {
        CONFIG_NAME: _inspect_file_identity(
            root / CONFIG_NAME,
            expected_bytes=config_bytes,
            expected_sha256=config_sha256,
        ),
        LICENSE_NAME: _inspect_file_identity(
            root / LICENSE_NAME,
            expected_bytes=license_bytes,
            expected_sha256=license_sha256,
        ),
    }
    return {
        "root": str(root),
        "files": files,
        "all_cryptographic_identities_verified": all(
            item["cryptographic_identity_verified"] for item in files.values()
        ),
    }


def _inspect_local_checkpoint(
    value: str | Path,
    *,
    expected_bytes: int = CONVERSION_CHECKPOINT_BYTES,
    expected_sha256: str = CONVERSION_CHECKPOINT_SHA256,
) -> dict[str, Any]:
    path = Path(value).expanduser().absolute()
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError(
            "MelBand-RoFormer checkpoint must be a non-symlink regular file"
        )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        os.set_inheritable(descriptor, False)
        opened = os.fstat(descriptor)
        if (
            os.get_inheritable(descriptor)
            or not stat.S_ISREG(opened.st_mode)
            or _identity(opened) != _identity(before)
        ):
            raise ValueError("MelBand-RoFormer checkpoint changed before hashing")
        digest = hashlib.sha256()
        while block := os.read(descriptor, 1024 * 1024):
            digest.update(block)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    rebound = path.lstat()
    if _identity(after) != _identity(opened) or _identity(rebound) != _identity(opened):
        raise ValueError("MelBand-RoFormer checkpoint changed during hashing")
    sha256 = digest.hexdigest()
    size_match = opened.st_size == expected_bytes
    hash_match = sha256 == expected_sha256
    return {
        "provided": True,
        "path": str(path),
        "bytes": opened.st_size,
        "sha256": sha256,
        "published_size_match": size_match,
        "published_sha256_match": hash_match,
        "cryptographic_identity_verified": size_match and hash_match,
    }


def _inspect_file_identity(
    path: Path, *, expected_bytes: int, expected_sha256: str
) -> dict[str, Any]:
    before = path.lstat()
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
    ):
        raise ValueError(
            "MelBand-RoFormer companion must be a single-link regular file"
        )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        os.set_inheritable(descriptor, False)
        opened = os.fstat(descriptor)
        if os.get_inheritable(descriptor) or _identity(opened) != _identity(before):
            raise ValueError("MelBand-RoFormer companion changed before hashing")
        digest = hashlib.sha256()
        while block := os.read(descriptor, 1024 * 1024):
            digest.update(block)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    rebound = path.lstat()
    if _identity(after) != _identity(opened) or _identity(rebound) != _identity(opened):
        raise ValueError("MelBand-RoFormer companion changed during hashing")
    sha256 = digest.hexdigest()
    size_match = opened.st_size == expected_bytes
    hash_match = sha256 == expected_sha256
    return {
        "path": str(path),
        "bytes": opened.st_size,
        "sha256": sha256,
        "published_size_match": size_match,
        "published_sha256_match": hash_match,
        "cryptographic_identity_verified": size_match and hash_match,
    }


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
    )


__all__ = [
    "APPROVAL_RECORDED_AT",
    "CONFIG_BYTES",
    "CONFIG_NAME",
    "CONFIG_SHA256",
    "LICENSE_BYTES",
    "LICENSE_NAME",
    "LICENSE_SHA256",
    "_inspect_companion_files",
    "_inspect_local_checkpoint",
]
