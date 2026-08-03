"""Private virtual-environment binding for the future native Kim worker.

This module measures one explicit Python virtual-environment launcher without
starting it.  It preserves the invocation path that controls ``sys.prefix``
while separately binding the resolved base executable and environment roots.
Returned private measurements contain paths; the observation projection does
not.  This is pathname stability evidence, not a TOCTOU or immutability proof.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import unicodedata
from pathlib import Path
from typing import Any, Mapping

from . import _separation_native_session_darwin as _base
from ._separation_checkpoint_canonical import (
    canonical_sha256 as _canonical_sha256,
    plain as _plain,
)


__all__: tuple[str, ...] = ()

_MAXIMUM_RUNTIME_BYTES = 2_147_483_648
_MAXIMUM_PYVENV_CONFIG_BYTES = 65_536
_MAXIMUM_RUNTIME_PATH_BYTES = 4_096
_PYTHON_VERSION_RE = re.compile(r"^3\.(?:9|10|11|12|13)(?:\.[0-9]+)?$")


def _measure_private_runtime_launcher(value: str | Path) -> Mapping[str, Any]:
    """Bind one exact virtual-environment launcher without executing it."""

    raw_path = os.fspath(value)
    if (
        not raw_path
        or len(os.fsencode(raw_path)) > _MAXIMUM_RUNTIME_PATH_BYTES
        or "\0" in raw_path
        or unicodedata.normalize("NFC", raw_path) != raw_path
    ):
        raise ValueError("private Kim runtime launcher path is unsafe")
    launcher = Path(raw_path)
    if (
        not launcher.is_absolute()
        or Path(os.path.normpath(raw_path)) != launcher
        or launcher.parent.name != "bin"
        or not re.fullmatch(r"python(?:3(?:\.[0-9]+)?)?", launcher.name)
    ):
        raise ValueError(
            "private Kim runtime launcher must be a canonical virtual-environment Python path"
        )

    environment_root = launcher.parent.parent
    environment = _measure_runtime_directory(
        environment_root,
        label="private Kim runtime environment",
        require_not_group_or_other_writable=True,
    )
    runtime_bin = _measure_runtime_directory(
        launcher.parent,
        label="private Kim runtime bin directory",
        require_not_group_or_other_writable=True,
    )
    config_path = environment_root / "pyvenv.cfg"
    config, config_bytes = _measure_runtime_config(config_path)
    config_values = _parse_private_pyvenv_config(config_bytes)

    try:
        entry_before = os.lstat(launcher)
    except OSError as exc:
        raise ValueError("private Kim runtime launcher is unavailable") from exc
    entry_kind: str
    raw_target: str | None
    if stat.S_ISLNK(entry_before.st_mode):
        entry_kind = "symlink"
        try:
            raw_target = os.readlink(launcher)
        except OSError as exc:
            raise ValueError("private Kim runtime launcher changed") from exc
        if (
            not raw_target
            or len(os.fsencode(raw_target)) > _MAXIMUM_RUNTIME_PATH_BYTES
            or "\0" in raw_target
            or unicodedata.normalize("NFC", raw_target) != raw_target
        ):
            raise ValueError("private Kim runtime launcher target is unsafe")
    elif stat.S_ISREG(entry_before.st_mode):
        entry_kind = "regular_file"
        raw_target = None
    else:
        raise ValueError("private Kim runtime launcher is not a file or symlink")
    if (
        entry_before.st_nlink != 1
        or entry_before.st_uid not in {0, os.getuid()}
    ):
        raise ValueError("private Kim runtime launcher ownership is invalid")
    entry_identity = _base._stat_identity(entry_before)
    try:
        resolved_runtime = launcher.resolve(strict=True)
        entry_after = os.lstat(launcher)
    except OSError as exc:
        raise ValueError("private Kim runtime launcher is unavailable") from exc
    if _base._stat_identity(entry_after) != entry_identity or (
        entry_kind == "symlink" and os.readlink(launcher) != raw_target
    ):
        raise RuntimeError("private Kim runtime launcher changed during measurement")

    runtime = _base._measure_bound_file(
        resolved_runtime,
        label="private Kim resolved Python runtime",
        maximum_bytes=_MAXIMUM_RUNTIME_BYTES,
        executable=True,
        # python.org framework launchers may be admin-group writable.  The
        # later code-signature/process-image and import-closure observations
        # are the execution-time checks for that operating-system boundary.
        require_not_group_or_other_writable=False,
    )
    home = Path(config_values["home"])
    if not home.is_absolute():
        raise ValueError("private Kim pyvenv home must be absolute")
    try:
        resolved_home = home.resolve(strict=True)
    except OSError as exc:
        raise ValueError("private Kim pyvenv home is unavailable") from exc
    if resolved_runtime.parent != resolved_home:
        raise ValueError("private Kim runtime target does not bind pyvenv home")
    base_runtime_root = resolved_home.parent
    base_runtime = _measure_runtime_directory(
        base_runtime_root,
        label="private Kim base runtime",
        require_not_group_or_other_writable=False,
    )
    return {
        "runtime_launcher_path": str(launcher),
        "runtime_environment_root": str(environment_root),
        "base_runtime_root": str(base_runtime_root),
        "python_version": config_values["version"],
        "launcher_entry": {
            "kind": entry_kind,
            "stat_identity": entry_identity,
            "stat_identity_sha256": _canonical_sha256(entry_identity),
            "target_sha256": (
                None
                if raw_target is None
                else hashlib.sha256(os.fsencode(raw_target)).hexdigest()
            ),
        },
        "resolved_runtime": runtime,
        "pyvenv_config": config,
        "runtime_environment": environment,
        "runtime_bin": runtime_bin,
        "base_runtime": base_runtime,
    }


def _measure_runtime_config(path: Path) -> tuple[Mapping[str, Any], bytes]:
    measured = _base._measure_bound_file(
        path,
        label="private Kim pyvenv config",
        maximum_bytes=_MAXIMUM_PYVENV_CONFIG_BYTES,
        executable=False,
        require_not_group_or_other_writable=True,
    )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        os.set_inheritable(descriptor, False)
        before = os.fstat(descriptor)
        chunks: list[bytes] = []
        offset = 0
        while offset < before.st_size:
            chunk = os.pread(descriptor, before.st_size - offset, offset)
            if not chunk:
                raise RuntimeError("private Kim pyvenv config is truncated")
            chunks.append(chunk)
            offset += len(chunk)
        data = b"".join(chunks)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        len(data) != measured["bytes"]
        or hashlib.sha256(data).hexdigest() != measured["sha256"]
        or _base._stat_identity(before) != measured["stat_identity"]
        or _base._stat_identity(after) != measured["stat_identity"]
    ):
        raise RuntimeError("private Kim pyvenv config changed during measurement")
    return measured, data


def _parse_private_pyvenv_config(data: bytes) -> Mapping[str, str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("private Kim pyvenv config is not UTF-8") from exc
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        if "=" not in line:
            raise ValueError("private Kim pyvenv config contains an invalid line")
        key, raw_value = line.split("=", 1)
        key = key.strip().casefold()
        item = raw_value.strip()
        if not key or not item or key in values:
            raise ValueError("private Kim pyvenv config contains ambiguous keys")
        values[key] = item
    version = values.get("version", values.get("version_info"))
    if version is None or not _PYTHON_VERSION_RE.fullmatch(version):
        raise ValueError("private Kim pyvenv version is unsupported")
    if values.get("include-system-site-packages", "").casefold() != "false":
        raise ValueError("private Kim pyvenv must disable system site packages")
    if "home" not in values:
        raise ValueError("private Kim pyvenv home is missing")
    home = values["home"]
    if (
        len(os.fsencode(home)) > _MAXIMUM_RUNTIME_PATH_BYTES
        or "\0" in home
        or unicodedata.normalize("NFC", home) != home
    ):
        raise ValueError("private Kim pyvenv home is unsafe")
    if (
        "implementation" in values
        and values["implementation"].casefold() != "cpython"
    ):
        raise ValueError("private Kim pyvenv implementation is unsupported")
    version_info = values.get("version_info")
    declared_version = values.get("version")
    if (
        version_info is not None
        and declared_version is not None
        and version_info != declared_version
    ):
        raise ValueError("private Kim pyvenv version fields differ")
    values["version"] = version
    return values


def _measure_runtime_directory(
    path: Path,
    *,
    label: str,
    require_not_group_or_other_writable: bool,
) -> Mapping[str, Any]:
    try:
        before = os.lstat(path)
        resolved = path.resolve(strict=True)
        after = os.stat(resolved)
        listed_after = os.lstat(path)
    except OSError as exc:
        raise ValueError(f"{label} is unavailable") from exc
    if (
        not stat.S_ISDIR(before.st_mode)
        or resolved != path
        or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
        or _base._stat_identity(listed_after) != _base._stat_identity(before)
        or before.st_uid not in {0, os.getuid()}
        or (require_not_group_or_other_writable and before.st_mode & 0o022)
    ):
        raise ValueError(f"{label} ownership or geometry is invalid")
    identity = _base._stat_identity(before)
    return {
        "stat_identity": identity,
        "stat_identity_sha256": _canonical_sha256(identity),
    }


def _path_free_runtime_binding(value: Mapping[str, Any]) -> Mapping[str, Any]:
    measured = _plain(value)
    return {
        "python_version": measured["python_version"],
        "launcher_entry_kind": measured["launcher_entry"]["kind"],
        "launcher_entry_stat_identity_sha256": measured["launcher_entry"][
            "stat_identity_sha256"
        ],
        "launcher_target_sha256": measured["launcher_entry"]["target_sha256"],
        "resolved_runtime": _path_free_binding(measured["resolved_runtime"]),
        "pyvenv_config": _path_free_binding(measured["pyvenv_config"]),
        "runtime_environment_stat_identity_sha256": measured[
            "runtime_environment"
        ]["stat_identity_sha256"],
        "runtime_bin_stat_identity_sha256": measured["runtime_bin"][
            "stat_identity_sha256"
        ],
        "base_runtime_stat_identity_sha256": measured["base_runtime"][
            "stat_identity_sha256"
        ],
        "system_site_packages_enabled": False,
    }


def _path_free_binding(value: Mapping[str, Any]) -> Mapping[str, Any]:
    measured = _plain(value)
    return {
        "sha256": measured["sha256"],
        "bytes": measured["bytes"],
        "stat_identity_sha256": measured["stat_identity_sha256"],
    }
