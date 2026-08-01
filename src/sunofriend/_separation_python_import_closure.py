"""Private, path-free binding for one Python worker import closure.

The child inventories every entry in ``sys.modules`` after its bounded work is
complete.  Every file-backed module is read through a non-following descriptor
and grouped by an explicitly named root.  The parent independently reopens and
hashes the same records before retaining only root-relative, path-free
evidence.

This binds the Python module closure observed in one worker.  It deliberately
does not claim to inventory arbitrary libraries opened through ``ctypes`` or a
native runtime, and it does not close the separate path-to-exec TOCTOU gap.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from .separation_contract import _canonical_json_bytes, _freeze_json


CLAIM_SCHEMA = "sunofriend.private-python-import-closure-claim.v1"
VERIFIED_SCHEMA = "sunofriend.private-python-import-closure-verified.v1"
POLICY_ID = "private-python-sys-modules-file-closure-v1"
_MAXIMUM_MODULES = 4_096
_MAXIMUM_FILES = 2_048
_MAXIMUM_FILE_BYTES = 512 * 1024 * 1024
_MAXIMUM_AGGREGATE_BYTES = 2 * 1024 * 1024 * 1024
_MODULE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,512}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_MANUAL_NAMESPACE_MODULES = {
    "mlx_audio",
    "mlx_audio.sts",
    "mlx_audio.sts.models",
    "mlx_audio.sts.models.mel_roformer",
}
_EXTENSION_GENERATED_PREFIXES = {"mlx.core.": "mlx.core"}
_RUNTIME_GENERATED_MODULES = {"typing.io": "typing", "typing.re": "typing"}
_ROOT_ORDER = (
    "source_overlay",
    "runtime_environment",
    "repository",
    "base_runtime",
    "system_library",
    "system_usr_lib",
)


def _melroformer_python_import_roots(
    *,
    repository_root: str | Path,
    source_root: str | Path,
    runtime_environment_root: str | Path,
    base_runtime_root: str | Path,
) -> Mapping[str, Path]:
    """Return the exact ordered roots permitted for this private worker."""

    roots = {
        "repository": _safe_root(repository_root, "repository"),
        "source_overlay": _safe_root(source_root, "source overlay"),
        "runtime_environment": _safe_root(
            runtime_environment_root, "runtime environment"
        ),
        "base_runtime": _safe_root(base_runtime_root, "base runtime"),
        "system_library": _safe_root("/System/Library", "system library"),
        "system_usr_lib": _safe_root("/usr/lib", "system usr lib"),
    }
    return MappingProxyType({name: roots[name] for name in _ROOT_ORDER})


def _capture_python_import_closure_claim(
    *,
    roots: Mapping[str, Path],
    modules: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Capture a bounded, self-hashed child claim from ``sys.modules``."""

    checked_roots = _validate_roots(roots)
    observed = sys.modules if modules is None else modules
    names = tuple(sorted(observed))
    if not 1 <= len(names) <= _MAXIMUM_MODULES:
        raise ValueError("Python import closure module count is outside bounds")
    if any(not isinstance(name, str) or not _MODULE_RE.fullmatch(name) for name in names):
        raise ValueError("Python import closure module name is invalid")

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    built_in: list[str] = []
    frozen: list[str] = []
    namespaces: list[str] = []
    extension_generated: list[str] = []
    runtime_generated: list[str] = []
    for name in names:
        module = observed[name]
        file_value = getattr(module, "__file__", None)
        if isinstance(file_value, str) and file_value:
            path = Path(file_value).expanduser().resolve(strict=True)
            root_id, relative = _classify_file(path, checked_roots)
            try:
                identity = _descriptor_file_identity(path)
            except ValueError as error:
                raise ValueError(
                    f"Python import closure module file is unsafe: {name}"
                ) from error
            key = (root_id, relative)
            entry = grouped.setdefault(
                key,
                {
                    "root_id": root_id,
                    "relative_path": relative,
                    "absolute_path": str(path),
                    "bytes": identity["bytes"],
                    "sha256": identity["sha256"],
                    "module_names": [],
                },
            )
            if (
                entry["bytes"] != identity["bytes"]
                or entry["sha256"] != identity["sha256"]
            ):
                raise ValueError("Python import closure aliases disagree")
            entry["module_names"].append(name)
            continue

        spec = getattr(module, "__spec__", None)
        origin = getattr(spec, "origin", None)
        if origin == "built-in":
            built_in.append(name)
        elif origin == "frozen":
            frozen.append(name)
        elif hasattr(module, "__path__") or name in _MANUAL_NAMESPACE_MODULES:
            namespaces.append(name)
        elif _extension_generated_producer(name, observed) is not None:
            extension_generated.append(name)
        elif _runtime_generated_producer(name, observed) is not None:
            runtime_generated.append(name)
        else:
            raise ValueError(
                f"Python import closure has an unclassified no-file module: {name}"
            )

    files = []
    aggregate_bytes = 0
    for key in sorted(grouped):
        item = grouped[key]
        item["module_names"].sort()
        aggregate_bytes += item["bytes"]
        files.append(item)
    if not 1 <= len(files) <= _MAXIMUM_FILES:
        raise ValueError("Python import closure file count is outside bounds")
    if aggregate_bytes > _MAXIMUM_AGGREGATE_BYTES:
        raise ValueError("Python import closure aggregate size is outside bounds")

    payload = {
        "schema": CLAIM_SCHEMA,
        "policy_id": POLICY_ID,
        "status": "captured_after_worker_actions",
        "root_paths": {name: str(path) for name, path in checked_roots.items()},
        "module_count": len(names),
        "module_names_sha256": _name_sequence_sha256(names),
        "file_count": len(files),
        "aggregate_file_bytes": aggregate_bytes,
        "files": files,
        "built_in_module_names": built_in,
        "frozen_module_names": frozen,
        "namespace_module_names": namespaces,
        "extension_generated_module_names": extension_generated,
        "runtime_generated_module_names": runtime_generated,
        "unclassified_module_names": [],
        "stable_before_output": False,
    }
    document = {
        **payload,
        "claim_sha256": hashlib.sha256(_canonical_json_bytes(payload)).hexdigest(),
    }
    return _freeze_json(document)


def _mark_python_import_closure_stable(
    claim: Mapping[str, Any], *, modules: Mapping[str, Any] | None = None
) -> Mapping[str, Any]:
    """Seal that JSON preparation imported no additional Python module."""

    value = _plain(claim)
    _validate_claim_shape(value, require_stable=False)
    observed = sys.modules if modules is None else modules
    names = tuple(sorted(observed))
    if (
        len(names) != value["module_count"]
        or _name_sequence_sha256(names) != value["module_names_sha256"]
    ):
        raise RuntimeError("Python import closure changed before worker output")
    value["stable_before_output"] = True
    value.pop("claim_sha256")
    value["claim_sha256"] = hashlib.sha256(
        _canonical_json_bytes(value)
    ).hexdigest()
    _validate_claim_shape(value, require_stable=True)
    return _freeze_json(value)


def _verify_python_import_closure_claim(
    claim: Mapping[str, Any], *, roots: Mapping[str, Path]
) -> Mapping[str, Any]:
    """Parent-verify every claimed file and return path-free evidence."""

    value = _plain(claim)
    _validate_claim_shape(value, require_stable=True)
    checked_roots = _validate_roots(roots)
    expected_root_paths = {name: str(path) for name, path in checked_roots.items()}
    if value["root_paths"] != expected_root_paths:
        raise ValueError("Python import closure root binding differs")

    clean_files: list[dict[str, Any]] = []
    for item in value["files"]:
        root = checked_roots[item["root_id"]]
        relative = _safe_relative_path(item["relative_path"])
        path = (root / relative).resolve(strict=True)
        if path != Path(item["absolute_path"]).resolve(strict=True):
            raise ValueError("Python import closure absolute/relative path differs")
        identity = _descriptor_file_identity(path)
        if identity != {"bytes": item["bytes"], "sha256": item["sha256"]}:
            raise ValueError("Python import closure file identity differs")
        clean_files.append(
            {
                "root_id": item["root_id"],
                "relative_path": item["relative_path"],
                "bytes": item["bytes"],
                "sha256": item["sha256"],
                "module_names": list(item["module_names"]),
            }
        )

    root_summaries = []
    for root_id in _ROOT_ORDER:
        entries = [item for item in clean_files if item["root_id"] == root_id]
        root_summaries.append(
            {
                "root_id": root_id,
                "file_count": len(entries),
                "module_count": sum(len(item["module_names"]) for item in entries),
                "bytes": sum(item["bytes"] for item in entries),
                "manifest_sha256": hashlib.sha256(
                    _canonical_json_bytes(entries)
                ).hexdigest(),
            }
        )
    payload = {
        "schema": VERIFIED_SCHEMA,
        "policy_id": POLICY_ID,
        "status": "complete_python_import_closure_parent_verified",
        "child_claim_sha256": value["claim_sha256"],
        "module_count": value["module_count"],
        "module_names_sha256": value["module_names_sha256"],
        "file_count": value["file_count"],
        "aggregate_file_bytes": value["aggregate_file_bytes"],
        "files": clean_files,
        "built_in_module_names": value["built_in_module_names"],
        "frozen_module_names": value["frozen_module_names"],
        "namespace_module_names": value["namespace_module_names"],
        "extension_generated_module_names": value[
            "extension_generated_module_names"
        ],
        "runtime_generated_module_names": value["runtime_generated_module_names"],
        "unclassified_module_names": [],
        "root_summaries": root_summaries,
        "child_stable_before_output": True,
        "parent_reopened_every_file": True,
        "python_sys_modules_closure_bound": True,
        "native_non_module_loads_bound": False,
        "hash_before_exec_path_toctou_closed": False,
    }
    document = {
        **payload,
        "evidence_sha256": hashlib.sha256(_canonical_json_bytes(payload)).hexdigest(),
    }
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"))
    if "/Users/" in encoded or "file://" in encoded or "://" in encoded:
        raise ValueError("Verified Python import closure is not path-free")
    return _freeze_json(document)


def _validate_verified_python_import_closure(value: Mapping[str, Any]) -> None:
    """Validate one already path-free parent result without filesystem access."""

    document = _plain(value)
    digest = document.pop("evidence_sha256", None)
    required = {
        "schema",
        "policy_id",
        "status",
        "child_claim_sha256",
        "module_count",
        "module_names_sha256",
        "file_count",
        "aggregate_file_bytes",
        "files",
        "built_in_module_names",
        "frozen_module_names",
        "namespace_module_names",
        "extension_generated_module_names",
        "runtime_generated_module_names",
        "unclassified_module_names",
        "root_summaries",
        "child_stable_before_output",
        "parent_reopened_every_file",
        "python_sys_modules_closure_bound",
        "native_non_module_loads_bound",
        "hash_before_exec_path_toctou_closed",
    }
    if not isinstance(document, dict) or set(document) != required:
        raise ValueError("Verified Python import closure fields differ")
    if not isinstance(digest, str) or not _SHA_RE.fullmatch(digest) or digest != hashlib.sha256(
        _canonical_json_bytes(document)
    ).hexdigest():
        raise ValueError("Verified Python import closure self-hash differs")
    if (
        document.get("schema") != VERIFIED_SCHEMA
        or document.get("policy_id") != POLICY_ID
        or document.get("status")
        != "complete_python_import_closure_parent_verified"
        or document.get("python_sys_modules_closure_bound") is not True
        or document.get("native_non_module_loads_bound") is not False
        or document.get("hash_before_exec_path_toctou_closed") is not False
        or document.get("child_stable_before_output") is not True
        or document.get("parent_reopened_every_file") is not True
        or document.get("unclassified_module_names") != []
    ):
        raise ValueError("Verified Python import closure policy differs")
    if (
        type(document.get("module_count")) is not int
        or not 1 <= document["module_count"] <= _MAXIMUM_MODULES
        or type(document.get("file_count")) is not int
        or not 1 <= document["file_count"] <= _MAXIMUM_FILES
        or not isinstance(document.get("module_names_sha256"), str)
        or not _SHA_RE.fullmatch(document["module_names_sha256"])
        or not isinstance(document.get("child_claim_sha256"), str)
        or not _SHA_RE.fullmatch(document["child_claim_sha256"])
    ):
        raise ValueError("Verified Python import closure counts differ")
    files = document.get("files")
    if not isinstance(files, list) or len(files) != document["file_count"]:
        raise ValueError("Verified Python import closure files differ")
    module_names = []
    aggregate_bytes = 0
    previous = None
    for item in files:
        if not isinstance(item, dict) or set(item) != {
            "root_id",
            "relative_path",
            "bytes",
            "sha256",
            "module_names",
        }:
            raise ValueError("Verified Python import closure file record differs")
        if item["root_id"] not in _ROOT_ORDER:
            raise ValueError("Verified Python import closure root differs")
        _safe_relative_path(item["relative_path"])
        ordering = (item["root_id"], item["relative_path"])
        if previous is not None and ordering <= previous:
            raise ValueError("Verified Python import closure file order differs")
        previous = ordering
        if (
            type(item["bytes"]) is not int
            or not 0 <= item["bytes"] <= _MAXIMUM_FILE_BYTES
            or not isinstance(item["sha256"], str)
            or not _SHA_RE.fullmatch(item["sha256"])
            or not isinstance(item["module_names"], list)
            or item["module_names"] != sorted(set(item["module_names"]))
            or not item["module_names"]
        ):
            raise ValueError("Verified Python import closure file identity differs")
        module_names.extend(item["module_names"])
        aggregate_bytes += item["bytes"]
    for key in (
        "built_in_module_names",
        "frozen_module_names",
        "namespace_module_names",
        "extension_generated_module_names",
        "runtime_generated_module_names",
    ):
        names = document.get(key)
        if (
            not isinstance(names, list)
            or names != sorted(set(names))
            or any(not _MODULE_RE.fullmatch(name) for name in names)
        ):
            raise ValueError("Verified Python import closure no-file modules differ")
        if key == "extension_generated_module_names" and any(
            not any(name.startswith(prefix) for prefix in _EXTENSION_GENERATED_PREFIXES)
            for name in names
        ):
            raise ValueError("Verified Python import closure generated module differs")
        if key == "runtime_generated_module_names" and any(
            name not in _RUNTIME_GENERATED_MODULES for name in names
        ):
            raise ValueError("Verified Python import closure generated module differs")
        module_names.extend(names)
    if (
        len(module_names) != document["module_count"]
        or len(module_names) != len(set(module_names))
        or _name_sequence_sha256(tuple(sorted(module_names)))
        != document["module_names_sha256"]
        or aggregate_bytes != document.get("aggregate_file_bytes")
        or aggregate_bytes > _MAXIMUM_AGGREGATE_BYTES
    ):
        raise ValueError("Verified Python import closure aggregate differs")
    summaries = document.get("root_summaries")
    expected_summaries = []
    for root_id in _ROOT_ORDER:
        entries = [item for item in files if item["root_id"] == root_id]
        expected_summaries.append(
            {
                "root_id": root_id,
                "file_count": len(entries),
                "module_count": sum(len(item["module_names"]) for item in entries),
                "bytes": sum(item["bytes"] for item in entries),
                "manifest_sha256": hashlib.sha256(
                    _canonical_json_bytes(entries)
                ).hexdigest(),
            }
        )
    if summaries != expected_summaries:
        raise ValueError("Verified Python import closure summaries differ")
    encoded = json.dumps({**document, "evidence_sha256": digest}, sort_keys=True)
    if "/Users/" in encoded or "file://" in encoded or "://" in encoded:
        raise ValueError("Verified Python import closure is not path-free")


def _validate_claim_shape(value: Any, *, require_stable: bool) -> None:
    required = {
        "schema",
        "policy_id",
        "status",
        "root_paths",
        "module_count",
        "module_names_sha256",
        "file_count",
        "aggregate_file_bytes",
        "files",
        "built_in_module_names",
        "frozen_module_names",
        "namespace_module_names",
        "extension_generated_module_names",
        "runtime_generated_module_names",
        "unclassified_module_names",
        "stable_before_output",
        "claim_sha256",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("Python import closure claim fields differ")
    digest = value.get("claim_sha256")
    unsigned = dict(value)
    unsigned.pop("claim_sha256", None)
    if (
        value.get("schema") != CLAIM_SCHEMA
        or value.get("policy_id") != POLICY_ID
        or value.get("status") != "captured_after_worker_actions"
        or value.get("stable_before_output") is not require_stable
        or not isinstance(digest, str)
        or not _SHA_RE.fullmatch(digest)
        or digest != hashlib.sha256(_canonical_json_bytes(unsigned)).hexdigest()
        or value.get("unclassified_module_names") != []
    ):
        raise ValueError("Python import closure claim identity differs")
    if (
        type(value.get("module_count")) is not int
        or not 1 <= value["module_count"] <= _MAXIMUM_MODULES
        or type(value.get("file_count")) is not int
        or not 1 <= value["file_count"] <= _MAXIMUM_FILES
        or not isinstance(value.get("module_names_sha256"), str)
        or not _SHA_RE.fullmatch(value["module_names_sha256"])
        or type(value.get("aggregate_file_bytes")) is not int
        or not 1 <= value["aggregate_file_bytes"] <= _MAXIMUM_AGGREGATE_BYTES
    ):
        raise ValueError("Python import closure claim counts differ")
    if not isinstance(value.get("root_paths"), dict) or set(
        value["root_paths"]
    ) != set(_ROOT_ORDER):
        raise ValueError("Python import closure claim roots differ")
    files = value.get("files")
    if not isinstance(files, list) or len(files) != value["file_count"]:
        raise ValueError("Python import closure claim files differ")
    module_names = []
    aggregate_bytes = 0
    previous = None
    for item in files:
        if not isinstance(item, dict) or set(item) != {
            "root_id",
            "relative_path",
            "absolute_path",
            "bytes",
            "sha256",
            "module_names",
        }:
            raise ValueError("Python import closure claim file record differs")
        ordering = (item["root_id"], item["relative_path"])
        if previous is not None and ordering <= previous:
            raise ValueError("Python import closure claim file order differs")
        previous = ordering
        if item["root_id"] not in _ROOT_ORDER:
            raise ValueError("Python import closure claim root differs")
        _safe_relative_path(item["relative_path"])
        if not isinstance(item["absolute_path"], str) or not item["absolute_path"].startswith("/"):
            raise ValueError("Python import closure claim absolute path differs")
        if (
            type(item["bytes"]) is not int
            or not 0 <= item["bytes"] <= _MAXIMUM_FILE_BYTES
            or not isinstance(item["sha256"], str)
            or not _SHA_RE.fullmatch(item["sha256"])
            or not isinstance(item["module_names"], list)
            or item["module_names"] != sorted(set(item["module_names"]))
            or not item["module_names"]
        ):
            raise ValueError("Python import closure claim file identity differs")
        module_names.extend(item["module_names"])
        aggregate_bytes += item["bytes"]
    for key in (
        "built_in_module_names",
        "frozen_module_names",
        "namespace_module_names",
        "extension_generated_module_names",
        "runtime_generated_module_names",
    ):
        names = value.get(key)
        if (
            not isinstance(names, list)
            or names != sorted(set(names))
            or any(not _MODULE_RE.fullmatch(name) for name in names)
        ):
            raise ValueError("Python import closure claim no-file modules differ")
        if key == "extension_generated_module_names" and any(
            not any(name.startswith(prefix) for prefix in _EXTENSION_GENERATED_PREFIXES)
            for name in names
        ):
            raise ValueError("Python import closure generated module differs")
        if key == "runtime_generated_module_names" and any(
            name not in _RUNTIME_GENERATED_MODULES for name in names
        ):
            raise ValueError("Python import closure generated module differs")
        module_names.extend(names)
    if (
        len(module_names) != value["module_count"]
        or len(module_names) != len(set(module_names))
        or _name_sequence_sha256(tuple(sorted(module_names)))
        != value["module_names_sha256"]
        or aggregate_bytes != value["aggregate_file_bytes"]
    ):
        raise ValueError("Python import closure claim aggregate differs")


def _validate_roots(roots: Mapping[str, Path]) -> Mapping[str, Path]:
    if not isinstance(roots, Mapping) or list(roots) != list(_ROOT_ORDER):
        raise ValueError("Python import closure roots differ")
    checked = {
        name: _safe_root(path, name.replace("_", " ")) for name, path in roots.items()
    }
    return MappingProxyType(checked)


def _classify_file(path: Path, roots: Mapping[str, Path]) -> tuple[str, str]:
    for root_id in _ROOT_ORDER:
        root = roots[root_id]
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        return root_id, relative.as_posix()
    raise ValueError("Python import closure file is outside every admitted root")


def _extension_generated_producer(
    name: str, modules: Mapping[str, Any]
) -> str | None:
    for prefix, producer_name in _EXTENSION_GENERATED_PREFIXES.items():
        if not name.startswith(prefix):
            continue
        producer = modules.get(producer_name)
        producer_file = getattr(producer, "__file__", None)
        if isinstance(producer_file, str) and producer_file:
            return producer_name
    return None


def _runtime_generated_producer(
    name: str, modules: Mapping[str, Any]
) -> str | None:
    producer_name = _RUNTIME_GENERATED_MODULES.get(name)
    if producer_name is None:
        return None
    producer = modules.get(producer_name)
    producer_file = getattr(producer, "__file__", None)
    return producer_name if isinstance(producer_file, str) and producer_file else None


def _descriptor_file_identity(path: Path) -> dict[str, Any]:
    attached = path.lstat()
    if (
        stat.S_ISLNK(attached.st_mode)
        or not stat.S_ISREG(attached.st_mode)
        or attached.st_nlink != 1
        or not 0 <= attached.st_size <= _MAXIMUM_FILE_BYTES
    ):
        raise ValueError("Python import closure module must be a single-link file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        os.set_inheritable(descriptor, False)
        opened = os.fstat(descriptor)
        if os.get_inheritable(descriptor) or _stat_identity(opened) != _stat_identity(attached):
            raise ValueError("Python import closure file changed before hashing")
        digest = hashlib.sha256()
        while block := os.read(descriptor, 1024 * 1024):
            digest.update(block)
        if _stat_identity(os.fstat(descriptor)) != _stat_identity(opened):
            raise ValueError("Python import closure file changed while hashing")
    finally:
        os.close(descriptor)
    if _stat_identity(path.lstat()) != _stat_identity(attached):
        raise ValueError("Python import closure path changed while hashing")
    return {"bytes": attached.st_size, "sha256": digest.hexdigest()}


def _safe_root(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser().resolve(strict=True)
    attached = path.lstat()
    if stat.S_ISLNK(attached.st_mode) or not stat.S_ISDIR(attached.st_mode):
        raise ValueError(f"Python import closure {label} root is unsafe")
    return path


def _safe_relative_path(value: Any) -> Path:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        raise ValueError("Python import closure relative path is invalid")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Python import closure relative path is invalid")
    return path


def _name_sequence_sha256(names: tuple[str, ...]) -> str:
    return hashlib.sha256(
        json.dumps(list(names), separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
    )


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


__all__ = [
    "CLAIM_SCHEMA",
    "POLICY_ID",
    "VERIFIED_SCHEMA",
    "_capture_python_import_closure_claim",
    "_mark_python_import_closure_stable",
    "_melroformer_python_import_roots",
    "_validate_verified_python_import_closure",
    "_verify_python_import_closure_claim",
]
