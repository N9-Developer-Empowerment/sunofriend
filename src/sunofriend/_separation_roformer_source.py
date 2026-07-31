"""Read-only verifier for the exact private BS-RoFormer source boundary."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Any


SOURCE_MANIFEST = "private-separation-roformer-source-manifest.json"
SOURCE_MANIFEST_SHA256 = (
    "74f35a148a86973a5a506575f1cdff163483a183196cfdb45b477c6cf16bc796"
)
SOURCE_REVISION = "aef04b2e52fb3beaf25e333199f5a7236e628e7b"

_SOURCE_FILES = {
    "LICENSE": {
        "bytes": 1_081,
        "sha256": ("3282dc057695ef5b9a64909a7092ca40b2c292c232580fc6ace6e5d665cc0207"),
    },
    "models/bs_roformer/attend.py": {
        "bytes": 3_681,
        "sha256": ("0459d799ade55541df2994b0becf7aec12214491360c5a06e346f6d615eaed15"),
    },
    "models/bs_roformer/bs_roformer.py": {
        "bytes": 18_561,
        "sha256": ("93408c7254c60c48e47be0657a64745065396b0b1c6da4e02c75aca57eb62bf3"),
    },
}


def _verify_private_roformer_source_tree(value: str | Path) -> dict[str, Any]:
    """Hash three fixed regular files without importing or executing them."""

    root = Path(value).expanduser().absolute()
    before = root.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
        raise ValueError("RoFormer source root must be a non-symlink directory")
    root_descriptor = _open_directory_path(root)
    descriptors = [root_descriptor]
    try:
        if _directory_identity(os.fstat(root_descriptor)) != _directory_identity(
            before
        ):
            raise ValueError("RoFormer source root changed before verification")
        models_descriptor = _open_child_directory(root_descriptor, "models")
        descriptors.append(models_descriptor)
        model_descriptor = _open_child_directory(models_descriptor, "bs_roformer")
        descriptors.append(model_descriptor)
        observed = [
            _verify_file(root_descriptor, "LICENSE", _SOURCE_FILES["LICENSE"]),
            _verify_file(
                model_descriptor,
                "attend.py",
                _SOURCE_FILES["models/bs_roformer/attend.py"],
                relative_path="models/bs_roformer/attend.py",
            ),
            _verify_file(
                model_descriptor,
                "bs_roformer.py",
                _SOURCE_FILES["models/bs_roformer/bs_roformer.py"],
                relative_path="models/bs_roformer/bs_roformer.py",
            ),
        ]
        after = root.lstat()
        if _directory_identity(after) != _directory_identity(before):
            raise ValueError("RoFormer source root changed during verification")
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    return {
        "schema": "sunofriend.private-roformer-source-verification.v1",
        "status": "verified_not_imported",
        "source_root": str(root),
        "revision_claim": SOURCE_REVISION,
        "revision_verified_by_git": False,
        "manifest": {
            "path": SOURCE_MANIFEST,
            "sha256": SOURCE_MANIFEST_SHA256,
        },
        "files": observed,
        "package_initializer_executed": False,
        "model_import_permitted": False,
        "effects": {
            "filesystem_accessed": True,
            "filesystem_written": False,
            "network_used": False,
            "model_imported": False,
            "process_started": False,
            "package_installed": False,
        },
    }


def _open_directory_path(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    os.set_inheritable(descriptor, False)
    if os.get_inheritable(descriptor):
        os.close(descriptor)
        raise ValueError("RoFormer source descriptor must be non-inheritable")
    return descriptor


def _open_child_directory(parent: int, name: str) -> int:
    attached = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if not stat.S_ISDIR(attached.st_mode) or stat.S_ISLNK(attached.st_mode):
        raise ValueError(f"RoFormer source directory is unsafe: {name}")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(name, flags, dir_fd=parent)
    os.set_inheritable(descriptor, False)
    if os.get_inheritable(descriptor) or _directory_identity(
        os.fstat(descriptor)
    ) != _directory_identity(attached):
        os.close(descriptor)
        raise ValueError(f"RoFormer source directory changed: {name}")
    return descriptor


def _verify_file(
    directory: int,
    leaf: str,
    expected: dict[str, int | str],
    *,
    relative_path: str | None = None,
) -> dict[str, Any]:
    attached = os.stat(leaf, dir_fd=directory, follow_symlinks=False)
    if not stat.S_ISREG(attached.st_mode) or stat.S_ISLNK(attached.st_mode):
        raise ValueError(f"RoFormer source file is unsafe: {leaf}")
    if attached.st_size != expected["bytes"]:
        raise ValueError(f"RoFormer source file size differs: {leaf}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(leaf, flags, dir_fd=directory)
    try:
        os.set_inheritable(descriptor, False)
        opened = os.fstat(descriptor)
        if os.get_inheritable(descriptor) or _file_identity(opened) != _file_identity(
            attached
        ):
            raise ValueError(f"RoFormer source file changed: {leaf}")
        digest = hashlib.sha256()
        count = 0
        while block := os.read(descriptor, 1024 * 1024):
            count += len(block)
            if count > expected["bytes"]:
                raise ValueError(f"RoFormer source file grew: {leaf}")
            digest.update(block)
        after = os.fstat(descriptor)
        rebound = os.stat(leaf, dir_fd=directory, follow_symlinks=False)
        if _file_identity(after) != _file_identity(opened) or _file_identity(
            rebound
        ) != _file_identity(opened):
            raise ValueError(f"RoFormer source file changed: {leaf}")
    finally:
        os.close(descriptor)
    if count != expected["bytes"] or digest.hexdigest() != expected["sha256"]:
        raise ValueError(f"RoFormer source file hash differs: {leaf}")
    return {
        "path": relative_path or leaf,
        "bytes": count,
        "sha256": digest.hexdigest(),
        "regular_file": True,
        "symlink": False,
    }


def _directory_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_mode, value.st_ctime_ns


def _file_identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )
