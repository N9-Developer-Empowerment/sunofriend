"""Read-only evidence for the exact private MLX MelBand-RoFormer runtime."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any


SOURCE_MANIFEST = "private-separation-melroformer-source-manifest.json"
SOURCE_MANIFEST_SHA256 = (
    "ed2351e52fdab8e87f4065f5f50d429295e03565cbbc2a01d435db2eb3285b6d"
)
RUNTIME_LOCK = "private-separation-melroformer-runtime-lock.json"
RUNTIME_LOCK_SHA256 = (
    "d7f3389954f3bc0c9f97eb13e82ab4c9589c7cad98fbb893a9eef51f131edbc9"
)
SOURCE_REVISION = "41092c02db18efd5b9d8281b2fcc41d84801757a"
MAX_SOURCE_FILE_BYTES = 65_536
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_CALLS = {
    "__import__",
    "compile",
    "eval",
    "exec",
    "importlib.import_module",
    "runpy.run_module",
    "runpy.run_path",
}


def _verify_tracked_melroformer_runtime_evidence(
    repository_root: str | Path,
) -> dict[str, Any]:
    """Verify the two tracked JSON records without installing or importing."""

    root = Path(repository_root).expanduser().absolute()
    _require_safe_directory(root, "repository root")
    source_bytes = _read_exact_regular_file(
        root / SOURCE_MANIFEST, expected_sha256=SOURCE_MANIFEST_SHA256
    )
    lock_bytes = _read_exact_regular_file(
        root / RUNTIME_LOCK, expected_sha256=RUNTIME_LOCK_SHA256
    )
    source = json.loads(source_bytes)
    lock = json.loads(lock_bytes)
    _validate_source_manifest(source)
    _validate_runtime_lock(lock)
    return {
        "schema": "sunofriend.private-melroformer-runtime-evidence-verification.v1",
        "status": "verified_not_installed_not_imported",
        "source_manifest": {
            "path": SOURCE_MANIFEST,
            "bytes": len(source_bytes),
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
            "revision": SOURCE_REVISION,
        },
        "runtime_lock": {
            "path": RUNTIME_LOCK,
            "bytes": len(lock_bytes),
            "sha256": hashlib.sha256(lock_bytes).hexdigest(),
            "packages": [item["name"] for item in lock["packages"]],
        },
        "loader_policy": source["loader_policy"],
        "stale_runtime_licence_comment_recorded": source["licence_note"]
        ["stale_runtime_documentation_found"],
        "authorises_installation": False,
        "authorises_model_import": False,
        "authorises_checkpoint_loading": False,
        "authorises_inference": False,
        "effects": {
            "filesystem_accessed": True,
            "filesystem_written": False,
            "network_used": False,
            "package_installed": False,
            "model_imported": False,
            "process_started": False,
        },
    }


def _verify_private_melroformer_source_tree(source_root: str | Path) -> dict[str, Any]:
    """Hash and statically parse a separately obtained exact source tree."""

    root = Path(source_root).expanduser().absolute()
    _require_safe_directory(root, "source root")
    manifest = _expected_source_manifest()
    reports: list[dict[str, Any]] = []
    for item in manifest["files"]:
        _require_safe_relative_parents(root, item["path"])
        contents = _read_exact_regular_file(
            root / item["path"],
            expected_sha256=item["sha256"],
            expected_bytes=item["bytes"],
        )
        report: dict[str, Any] = {
            "path": item["path"],
            "bytes": len(contents),
            "sha256": hashlib.sha256(contents).hexdigest(),
            "kind": item["kind"],
        }
        if item["kind"] == "runtime_module":
            report["static_analysis"] = _audit_python_source(
                contents,
                path=item["path"],
                expected_roots=item["direct_import_roots"],
                permitted_relative=item["permitted_relative_imports"],
            )
        reports.append(report)
    return {
        "schema": "sunofriend.private-melroformer-source-verification.v1",
        "status": "verified_not_imported",
        "source_root": str(root),
        "revision_claim": SOURCE_REVISION,
        "revision_verified_by_git": False,
        "files": reports,
        "upstream_from_pretrained_permitted": False,
        "model_import_permitted": False,
        "effects": {
            "filesystem_accessed": True,
            "filesystem_written": False,
            "network_used": False,
            "package_installed": False,
            "model_imported": False,
            "process_started": False,
        },
    }


def _expected_source_manifest() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    contents = _read_exact_regular_file(
        root / SOURCE_MANIFEST, expected_sha256=SOURCE_MANIFEST_SHA256
    )
    value = json.loads(contents)
    _validate_source_manifest(value)
    return value


def _validate_source_manifest(value: object) -> None:
    if not isinstance(value, dict):
        raise ValueError("MelRoFormer source manifest must be an object")
    if (
        value.get("schema") != "sunofriend.private-melroformer-source-manifest.v1"
        or value.get("revision") != SOURCE_REVISION
        or value.get("license") != "MIT"
        or value.get("authorises_installation") is not False
        or value.get("authorises_model_import") is not False
        or value.get("authorises_checkpoint_loading") is not False
        or value.get("authorises_inference") is not False
    ):
        raise ValueError("MelRoFormer source manifest policy differs")
    files = value.get("files")
    if not isinstance(files, list) or len(files) != 6:
        raise ValueError("MelRoFormer source manifest file list differs")
    paths: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("MelRoFormer source manifest file is invalid")
        path = item.get("path")
        byte_count = item.get("bytes")
        digest = item.get("sha256")
        if (
            not isinstance(path, str)
            or path in paths
            or path.startswith("/")
            or ".." in Path(path).parts
            or isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or not 0 <= byte_count <= MAX_SOURCE_FILE_BYTES
            or not isinstance(digest, str)
            or not _SHA_RE.fullmatch(digest)
        ):
            raise ValueError("MelRoFormer source manifest file identity is invalid")
        paths.add(path)
    loader = value.get("loader_policy")
    if not isinstance(loader, dict) or loader.get("upstream_from_pretrained_permitted") is not False:
        raise ValueError("MelRoFormer source loader policy differs")
    note = value.get("licence_note")
    if not isinstance(note, dict) or note.get("stale_runtime_documentation_found") is not True:
        raise ValueError("MelRoFormer stale licence note is missing")


def _validate_runtime_lock(value: object) -> None:
    if not isinstance(value, dict):
        raise ValueError("MelRoFormer runtime lock must be an object")
    if (
        value.get("schema") != "sunofriend.private-melroformer-runtime-lock.v1"
        or value.get("python") != "3.12"
        or value.get("platform") != "macOS 14+ arm64"
        or value.get("installation_command") is not None
        or value.get("authorises_installation") is not False
        or value.get("authorises_model_import") is not False
        or value.get("authorises_checkpoint_loading") is not False
        or value.get("authorises_inference") is not False
    ):
        raise ValueError("MelRoFormer runtime lock policy differs")
    packages = value.get("packages")
    if not isinstance(packages, list) or [item.get("name") for item in packages if isinstance(item, dict)] != [
        "mlx",
        "mlx-metal",
        "numpy",
    ]:
        raise ValueError("MelRoFormer runtime package set differs")
    for item in packages:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("version"), str)
            or not isinstance(item.get("bytes"), int)
            or isinstance(item.get("bytes"), bool)
            or not isinstance(item.get("sha256"), str)
            or not _SHA_RE.fullmatch(item["sha256"])
        ):
            raise ValueError("MelRoFormer runtime package identity is invalid")
    overlay = value.get("source_overlay")
    if (
        not isinstance(overlay, dict)
        or overlay.get("manifest") != SOURCE_MANIFEST
        or overlay.get("manifest_sha256") != SOURCE_MANIFEST_SHA256
        or overlay.get("installed_as_mlx_audio_distribution") is not False
        or overlay.get("upstream_convenience_loader_available") is not False
    ):
        raise ValueError("MelRoFormer runtime source overlay differs")


def _audit_python_source(
    contents: bytes,
    *,
    path: str,
    expected_roots: list[str],
    permitted_relative: list[str],
) -> dict[str, Any]:
    try:
        tree = ast.parse(contents.decode("utf-8"), filename=path)
    except (SyntaxError, UnicodeDecodeError) as error:
        raise ValueError(f"MelRoFormer source syntax is invalid: {path}") from error
    roots: set[str] = set()
    relative: list[str] = []
    wildcard: list[str] = []
    forbidden: list[str] = []
    loader_calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                relative.append("." * node.level + module)
            elif module:
                roots.add(module.split(".", 1)[0])
            if any(alias.name == "*" for alias in node.names):
                wildcard.append(module)
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in _FORBIDDEN_CALLS:
                forbidden.append(name)
            if name in {"get_model_path", "mx.load", "model.load_weights"}:
                loader_calls.append(name)
    if sorted(roots) != expected_roots:
        raise ValueError(f"MelRoFormer source import surface differs: {path}")
    if sorted(relative) != sorted(permitted_relative):
        raise ValueError(f"MelRoFormer source relative import surface differs: {path}")
    if wildcard or forbidden:
        raise ValueError(f"MelRoFormer source contains forbidden Python constructs: {path}")
    return {
        "syntax": "parsed_not_executed",
        "direct_import_roots": sorted(roots),
        "relative_imports": sorted(relative),
        "wildcard_imports": wildcard,
        "dynamic_import_or_codegen_calls": forbidden,
        "loader_calls": sorted(set(loader_calls)),
        "upstream_convenience_loader_present": "get_model_path" in loader_calls,
    }


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _read_exact_regular_file(
    path: Path, *, expected_sha256: str, expected_bytes: int | None = None
) -> bytes:
    attached = path.lstat()
    if stat.S_ISLNK(attached.st_mode) or not stat.S_ISREG(attached.st_mode):
        raise ValueError(f"MelRoFormer evidence path is unsafe: {path.name}")
    if expected_bytes is not None and attached.st_size != expected_bytes:
        raise ValueError(f"MelRoFormer evidence byte count differs: {path.name}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        os.set_inheritable(descriptor, False)
        opened = os.fstat(descriptor)
        if os.get_inheritable(descriptor) or _identity(opened) != _identity(attached):
            raise ValueError(f"MelRoFormer evidence changed: {path.name}")
        digest = hashlib.sha256()
        chunks = bytearray()
        while block := os.read(descriptor, 1024 * 1024):
            digest.update(block)
            chunks.extend(block)
        rebound = path.lstat()
        if _identity(os.fstat(descriptor)) != _identity(opened) or _identity(rebound) != _identity(opened):
            raise ValueError(f"MelRoFormer evidence changed: {path.name}")
    finally:
        os.close(descriptor)
    if digest.hexdigest() != expected_sha256:
        raise ValueError(f"MelRoFormer evidence hash differs: {path.name}")
    return bytes(chunks)


def _require_safe_directory(path: Path, label: str) -> None:
    attached = path.lstat()
    if stat.S_ISLNK(attached.st_mode) or not stat.S_ISDIR(attached.st_mode):
        raise ValueError(f"MelRoFormer {label} must be a non-symlink directory")


def _require_safe_relative_parents(root: Path, relative: str) -> None:
    parts = Path(relative).parts[:-1]
    current = root
    for part in parts:
        current = current / part
        _require_safe_directory(current, f"source directory {part}")


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
    "RUNTIME_LOCK",
    "RUNTIME_LOCK_SHA256",
    "SOURCE_MANIFEST",
    "SOURCE_MANIFEST_SHA256",
    "SOURCE_REVISION",
    "_verify_private_melroformer_source_tree",
    "_verify_tracked_melroformer_runtime_evidence",
]
