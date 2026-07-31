"""Read-only verifier for the exact private BS-RoFormer source boundary."""

from __future__ import annotations

import ast
import hashlib
import os
import stat
from pathlib import Path
from typing import Any


SOURCE_MANIFEST = "private-separation-roformer-source-manifest.json"
SOURCE_MANIFEST_SHA256 = (
    "6c106b71464563052ca626412fd4456f864274e40c0ca4eda441d7119c28947a"
)
SOURCE_REVISION = "aef04b2e52fb3beaf25e333199f5a7236e628e7b"
_MAX_SOURCE_FILE_BYTES = 64 * 1024
_FORBIDDEN_RUNTIME_CALLS = frozenset({"__import__", "compile", "eval", "exec"})

_SOURCE_FILES = {
    "LICENSE": {
        "bytes": 1_081,
        "sha256": ("3282dc057695ef5b9a64909a7092ca40b2c292c232580fc6ace6e5d665cc0207"),
    },
    "models/bs_roformer/attend.py": {
        "bytes": 3_681,
        "sha256": ("0459d799ade55541df2994b0becf7aec12214491360c5a06e346f6d615eaed15"),
        "direct_import_roots": (
            "collections",
            "einops",
            "functools",
            "os",
            "packaging",
            "torch",
        ),
    },
    "models/bs_roformer/bs_roformer.py": {
        "bytes": 18_561,
        "sha256": ("93408c7254c60c48e47be0657a64745065396b0b1c6da4e02c75aca57eb62bf3"),
        "direct_import_roots": (
            "beartype",
            "einops",
            "functools",
            "models",
            "rotary_embedding_torch",
            "torch",
        ),
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
        license_report, _ = _verify_file(
            root_descriptor, "LICENSE", _SOURCE_FILES["LICENSE"]
        )
        attend_report, attend_source = _verify_file(
            model_descriptor,
            "attend.py",
            _SOURCE_FILES["models/bs_roformer/attend.py"],
            relative_path="models/bs_roformer/attend.py",
        )
        model_report, model_source = _verify_file(
            model_descriptor,
            "bs_roformer.py",
            _SOURCE_FILES["models/bs_roformer/bs_roformer.py"],
            relative_path="models/bs_roformer/bs_roformer.py",
        )
        observed = [
            license_report,
            _verify_python_import_surface(
                attend_report,
                attend_source,
                _SOURCE_FILES["models/bs_roformer/attend.py"]["direct_import_roots"],
            ),
            _verify_python_import_surface(
                model_report,
                model_source,
                _SOURCE_FILES["models/bs_roformer/bs_roformer.py"][
                    "direct_import_roots"
                ],
            ),
        ]
        after = root.lstat()
        if _directory_identity(after) != _directory_identity(before):
            raise ValueError("RoFormer source root changed during verification")
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    return {
        "schema": "sunofriend.private-roformer-source-verification.v2",
        "status": "verified_not_imported",
        "source_root": str(root),
        "revision_claim": SOURCE_REVISION,
        "revision_verified_by_git": False,
        "manifest": {
            "path": SOURCE_MANIFEST,
            "sha256": SOURCE_MANIFEST_SHA256,
        },
        "files": observed,
        "static_source_policy": {
            "maximum_file_bytes": _MAX_SOURCE_FILE_BYTES,
            "exact_direct_import_roots_required": True,
            "relative_imports_permitted": False,
            "wildcard_imports_permitted": False,
            "dynamic_import_or_codegen_calls_permitted": False,
        },
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
    expected: dict[str, object],
    *,
    relative_path: str | None = None,
) -> tuple[dict[str, Any], bytes]:
    expected_bytes = expected.get("bytes")
    expected_sha256 = expected.get("sha256")
    if (
        not isinstance(expected_bytes, int)
        or isinstance(expected_bytes, bool)
        or expected_bytes < 0
        or not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
    ):
        raise ValueError(f"RoFormer expected file policy is invalid: {leaf}")
    attached = os.stat(leaf, dir_fd=directory, follow_symlinks=False)
    if not stat.S_ISREG(attached.st_mode) or stat.S_ISLNK(attached.st_mode):
        raise ValueError(f"RoFormer source file is unsafe: {leaf}")
    if attached.st_size != expected_bytes:
        raise ValueError(f"RoFormer source file size differs: {leaf}")
    if attached.st_size > _MAX_SOURCE_FILE_BYTES:
        raise ValueError(f"RoFormer source file exceeds static audit bound: {leaf}")
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
        contents = bytearray()
        while block := os.read(descriptor, 1024 * 1024):
            count += len(block)
            if count > expected_bytes:
                raise ValueError(f"RoFormer source file grew: {leaf}")
            digest.update(block)
            contents.extend(block)
        after = os.fstat(descriptor)
        rebound = os.stat(leaf, dir_fd=directory, follow_symlinks=False)
        if _file_identity(after) != _file_identity(opened) or _file_identity(
            rebound
        ) != _file_identity(opened):
            raise ValueError(f"RoFormer source file changed: {leaf}")
    finally:
        os.close(descriptor)
    if count != expected_bytes or digest.hexdigest() != expected_sha256:
        raise ValueError(f"RoFormer source file hash differs: {leaf}")
    return (
        {
            "path": relative_path or leaf,
            "bytes": count,
            "sha256": digest.hexdigest(),
            "regular_file": True,
            "symlink": False,
        },
        bytes(contents),
    )


def _verify_python_import_surface(
    report: dict[str, Any],
    contents: bytes,
    expected_roots: object,
) -> dict[str, Any]:
    """Parse a hash-verified module and reject an unexpected import surface."""

    path = str(report["path"])
    if not isinstance(expected_roots, tuple) or not all(
        isinstance(value, str) and value for value in expected_roots
    ):
        raise ValueError(f"RoFormer expected import policy is invalid: {path}")
    try:
        tree = ast.parse(contents.decode("utf-8"), filename=path)
    except (SyntaxError, UnicodeDecodeError) as error:
        raise ValueError(f"RoFormer source syntax is invalid: {path}") from error

    roots: set[str] = set()
    relative_imports: list[str] = []
    wildcard_imports: list[str] = []
    forbidden_calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                relative_imports.append("." * node.level + module)
            elif module:
                roots.add(module.split(".", 1)[0])
            if any(alias.name == "*" for alias in node.names):
                wildcard_imports.append(module)
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in _FORBIDDEN_RUNTIME_CALLS or name in {
                "importlib.import_module",
                "runpy.run_module",
                "runpy.run_path",
            }:
                forbidden_calls.append(name)

    observed_roots = tuple(sorted(roots))
    if observed_roots != tuple(expected_roots):
        raise ValueError(f"RoFormer source import surface differs: {path}")
    if relative_imports:
        raise ValueError(f"RoFormer source contains a relative import: {path}")
    if wildcard_imports:
        raise ValueError(f"RoFormer source contains a wildcard import: {path}")
    if forbidden_calls:
        raise ValueError(
            f"RoFormer source contains a dynamic import or codegen call: {path}"
        )

    return {
        **report,
        "static_analysis": {
            "syntax": "parsed_not_executed",
            "direct_import_roots": list(observed_roots),
            "relative_imports": [],
            "wildcard_imports": [],
            "dynamic_import_or_codegen_calls": [],
        },
    }


def _call_name(value: ast.expr) -> str:
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name):
        return f"{value.value.id}.{value.attr}"
    return ""


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
