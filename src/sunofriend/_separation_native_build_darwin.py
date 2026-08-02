"""Private, explicit build provenance for the Darwin spawn source.

This module is intentionally absent from every public Sunofriend import and
command path.  Its sole entry point compiles the packaged, hash-pinned C
source into a fresh private directory when an internal caller explicitly asks
it to.
It verifies the build recipe, Mach-O identity and ad-hoc signature, but never
imports the extension and never starts a separation worker.

The builder compiles one measured object and invokes the measured Darwin linker
directly with only that object and one measured SDK libSystem stub as link
inputs.  Recorded post-scan provenance does not claim to enumerate dynamic
runtime libraries used internally by the compiler, linker or signing tools.
"""

from __future__ import annotations

import ctypes
import hashlib
import importlib.resources
import json
import os
import platform
import re
import selectors
import signal
import shutil
import stat
import struct
import subprocess
import sys
import sysconfig
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ._separation_checkpoint_canonical import (
    canonical_json_bytes as _canonical_json,
    canonical_sha256 as _canonical_hash,
    deep_freeze as _freeze,
    plain as _plain,
)


__all__: tuple[str, ...] = ()

_SCHEMA = "sunofriend.separation-native-launcher-build-receipt.v1"
_BUILD_POLICY_ID = "private-darwin-source-build-provenance-v1"
_SOURCE_RESOURCE_NAME = "_separation_native_spawn_darwin.c"
_NATIVE_MODULE_NAME = "_separation_native_spawn_darwin"
_EXPECTED_SOURCE_SHA256 = (
    "fa7d1fe2ad4512fbe6ce280439e957fe544b9ca0037a02e6483145d76e9c3e2c"
)
_XCRUN = Path("/usr/bin/xcrun")
_DEPLOYMENT_TARGET = "12.0"
_PRIVATE_BUILD_ROOT_NAME = "native-launcher-build-v1"
_RECEIPT_NAME = "build-receipt.json"
_SOURCE_COPY_NAME = "launcher-source.c"
_OBJECT_NAME = "launcher-object.o"
_SCAN_DEPENDENCY_NAME = "scan-dependencies.d"
_COMPILE_DEPENDENCY_NAME = "compile-dependencies.d"
_PRIVATE_DIRECTORY_MODE = 0o700
_PRIVATE_RECEIPT_MODE = 0o600
_PRIVATE_SOURCE_MODE = 0o600
_PRIVATE_EXECUTABLE_MODE = 0o500
_MAXIMUM_SOURCE_BYTES = 1_048_576
_MAXIMUM_BINARY_BYTES = 16_777_216
_MAXIMUM_RECEIPT_BYTES = 262_144
_MAXIMUM_DEPENDENCY_BYTES = 1_048_576
_MAXIMUM_DEPENDENCIES = 4096
_MAXIMUM_TOOL_OUTPUT_BYTES = 65_536
_DISCOVERY_TIMEOUT_SECONDS = 10.0
_COMPILE_TIMEOUT_SECONDS = 120.0
_CODESIGN_TIMEOUT_SECONDS = 20.0
_TOOL_CLEANUP_TIMEOUT_SECONDS = 2.0
_DARWIN_SA_NOCLDWAIT = 0x20
_FIXED_ENVIRONMENT = {
    "LANG": "C",
    "LC_ALL": "C",
    "TZ": "UTC",
}
_SUPPORTED_ARCHITECTURES = {
    "arm64": {
        "clang_arch": "arm64",
        "mach_cpu_type": 0x0100000C,
    },
    "x86_64": {
        "clang_arch": "x86_64",
        "mach_cpu_type": 0x01000007,
    },
}
_ALLOWED_DYLIBS = ("/usr/lib/libSystem.B.dylib",)
_MACH_LOAD_DYLIB = 0xC
_MACH_ID_DYLIB = 0xD
_MACH_LOAD_DYLINKER = 0xE
_MACH_ID_DYLINKER = 0xF
_MACH_PREBOUND_DYLIB = 0x10
_MACH_LOAD_WEAK_DYLIB = 0x80000018
_MACH_LAZY_LOAD_DYLIB = 0x20
_MACH_REEXPORT_DYLIB = 0x8000001F
_MACH_RPATH = 0x8000001C
_MACH_LOAD_UPWARD_DYLIB = 0x80000023
_MACH_DYLD_ENVIRONMENT = 0x27
_MACH_CODE_SIGNATURE = 0x1D
_MACH_BUILD_VERSION = 0x32
_MACH_UUID = 0x1B
_EXTENSION_SUFFIX_RE = re.compile(r"^\.[A-Za-z0-9_.-]{1,120}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PROVENANCE_SCOPE = _freeze(
    {
        "recorded_inputs": (
            "prebuild_recipe_header_closure_compiled_object_explicit_sdk_libSystem_tbd"
        ),
        "dynamic_build_tool_runtime_closure_recorded": False,
    }
)
_BUILD_CONTRACT = _freeze(
    {
        "schema": "sunofriend.separation-native-launcher-build-contract.v1",
        "policy_id": _BUILD_POLICY_ID,
        "source_sha256": _EXPECTED_SOURCE_SHA256,
        "xcrun": str(_XCRUN),
        "architectures": sorted(_SUPPORTED_ARCHITECTURES),
        "deployment_target": _DEPLOYMENT_TARGET,
        "compile_flags": [
            "-c",
            "-std=c11",
            "-O2",
            "-fno-common",
            "-fvisibility=hidden",
            "-Wall",
            "-Wextra",
            "-Werror",
            "SUNOFRIEND_NATIVE_SOURCE_SHA256",
            "SUNOFRIEND_NATIVE_BUILD_CONTRACT_SHA256",
        ],
        "link_flags": [
            "-arch",
            "-bundle",
            "-undefined",
            "dynamic_lookup",
            "-platform_version",
            "macos",
            "-syslibroot",
            "explicit_compiled_object",
            "explicit_sdk_libSystem_tbd",
        ],
        "environment": _FIXED_ENVIRONMENT,
        "signing": {
            "kind": "adhoc",
            "timestamp": False,
            "strict_verification": True,
        },
        "timeouts_seconds": {
            "discovery": _DISCOVERY_TIMEOUT_SECONDS,
            "compile": _COMPILE_TIMEOUT_SECONDS,
            "codesign": _CODESIGN_TIMEOUT_SECONDS,
        },
        "artifact_policy": {
            "thin_host_architecture": True,
            "file_type": "MH_BUNDLE",
            "rpath_permitted": False,
            "allowed_dylibs": list(_ALLOWED_DYLIBS),
            "embedded_signature_required": True,
            "uuid_required_exactly_once": True,
            "header_closure_hash_before_after": True,
            "compiled_object_hash_before_after_link": True,
            "explicit_sdk_linker_input_hash_before_after": True,
            "import_permitted": False,
            "worker_start_permitted": False,
        },
    }
)
_EXPECTED_BUILD_CONTRACT_SHA256 = (
    "01eb89ccc95caa09daa95485be12309cd0fc73b7c70d707fc268d38128267843"
)


class _DarwinSigaction(ctypes.Structure):
    _fields_ = [
        ("handler", ctypes.c_void_p),
        ("mask", ctypes.c_uint32),
        ("flags", ctypes.c_int),
    ]


@dataclass(frozen=True)
class _NativeLauncherBuildReceipt:
    """One immutable canonical build receipt."""

    _document: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return _plain(self._document)

    def canonical_bytes(self) -> bytes:
        return _canonical_json(self.to_dict())

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True)
class _NativeLauncherBuild:
    """Fresh verified artifact plus its immutable receipt."""

    artifact_path: Path
    receipt: _NativeLauncherBuildReceipt
    receipt_sha256: str


@dataclass(frozen=True)
class _BuildContext:
    source_bytes: bytes
    fingerprint: Mapping[str, Any]
    prebuild_recipe_sha256: str
    artifact_name: str
    compiler_path: Path
    linker_path: Path
    codesign_path: Path


def _darwin_host() -> bool:
    return sys.platform == "darwin" and platform.system() == "Darwin"


def _default_private_build_root() -> Path:
    return Path.home() / "Library" / "Caches" / "Sunofriend" / _PRIVATE_BUILD_ROOT_NAME


def _build_native_launcher(
    *,
    cache_root: str | Path | None = None,
) -> _NativeLauncherBuild:
    """Explicitly make one fresh private Darwin launcher artifact.

    This function invokes only the measured compiler, linker and code-signing
    tools. It does not import the resulting extension or start a worker.
    """

    if not _darwin_host():
        raise RuntimeError("native launcher builds are supported only on macOS")

    source_bytes = _read_packaged_source_once()
    context = _discover_build_context(source_bytes)
    root = _normalise_cache_root(
        _default_private_build_root() if cache_root is None else Path(cache_root)
    )
    _ensure_private_directory(root)

    stage_directory = Path(tempfile.mkdtemp(prefix=".fresh-build-", dir=str(root)))
    os.chmod(stage_directory, _PRIVATE_DIRECTORY_MODE)
    complete = False
    try:
        _build_in_stage(context=context, stage_directory=stage_directory)
        _fsync_directory(stage_directory)
        result = _verify_fresh_build(
            context=context,
            cache_root=root,
            build_directory=stage_directory,
        )
        complete = True
        return result
    finally:
        if not complete and _lexists(stage_directory):
            shutil.rmtree(stage_directory)


def _read_packaged_source_once() -> bytes:
    resource = importlib.resources.files("sunofriend").joinpath(_SOURCE_RESOURCE_NAME)
    payload = resource.read_bytes()
    if not payload or len(payload) > _MAXIMUM_SOURCE_BYTES:
        raise RuntimeError("packaged native launcher source has an invalid size")
    if hashlib.sha256(payload).hexdigest() != _EXPECTED_SOURCE_SHA256:
        raise RuntimeError("packaged native launcher source failed its pinned hash")
    return payload


def _discover_build_context(source_bytes: bytes) -> _BuildContext:
    if (
        not source_bytes
        or len(source_bytes) > _MAXIMUM_SOURCE_BYTES
        or hashlib.sha256(source_bytes).hexdigest() != _EXPECTED_SOURCE_SHA256
    ):
        raise RuntimeError("native launcher source failed its pinned identity")
    if _canonical_hash(_plain(_BUILD_CONTRACT)) != _EXPECTED_BUILD_CONTRACT_SHA256:
        raise RuntimeError("native launcher build contract failed its pinned hash")
    xcrun_record = _trusted_executable_record(_XCRUN, label="xcrun")
    compiler_path = _resolve_xcrun_path("--find", "clang")
    linker_path = _resolve_xcrun_path("--find", "ld")
    codesign_path = _resolve_xcrun_path("--find", "codesign")
    sdk_path = _resolve_xcrun_path(
        "--sdk",
        "macosx",
        "--show-sdk-path",
        expect_directory=True,
    )
    sdk_version = _single_line(
        _run_tool(
            _XCRUN,
            ("--sdk", "macosx", "--show-sdk-version"),
            timeout=_DISCOVERY_TIMEOUT_SECONDS,
        ).stdout,
        "SDK version",
    )
    compiler_record = _trusted_executable_record(
        compiler_path,
        label="compiler",
    )
    codesign_record = _trusted_executable_record(
        codesign_path,
        label="codesign",
    )
    linker_record = _trusted_executable_record(
        linker_path,
        label="linker",
    )
    sdk_record = _trusted_directory_record(sdk_path, label="SDK")
    direct_linker_input = _direct_linker_input_record(sdk_path)

    compiler_version = _bounded_text(
        _run_tool(
            compiler_path,
            ("--version",),
            timeout=_DISCOVERY_TIMEOUT_SECONDS,
        ).stdout,
        "compiler version",
    )
    if not compiler_version.startswith("Apple clang version "):
        raise RuntimeError("the native launcher requires Apple clang")
    compiler_resource_path = Path(
        _single_line(
            _run_tool(
                compiler_path,
                ("-print-resource-dir",),
                timeout=_DISCOVERY_TIMEOUT_SECONDS,
            ).stdout,
            "compiler resource directory",
        )
    )
    if not compiler_resource_path.is_absolute():
        raise RuntimeError("compiler resource directory is not absolute")
    compiler_resource_path = compiler_resource_path.resolve(strict=True)
    compiler_resource_record = _trusted_directory_record(
        compiler_resource_path,
        label="compiler resource directory",
    )

    architecture = platform.machine()
    architecture_policy = _SUPPORTED_ARCHITECTURES.get(architecture)
    if architecture_policy is None:
        raise RuntimeError("native launcher builds require arm64 or x86_64 macOS")

    extension_suffix = sysconfig.get_config_var("EXT_SUFFIX")
    if not isinstance(extension_suffix, str) or not _EXTENSION_SUFFIX_RE.fullmatch(
        extension_suffix
    ):
        raise RuntimeError("Python reported an unsafe extension suffix")
    include_value = sysconfig.get_paths().get("include")
    if not isinstance(include_value, str):
        raise RuntimeError("Python did not report its include directory")
    include_path = Path(include_value).expanduser()
    if not include_path.is_absolute():
        raise RuntimeError("Python include directory is not absolute")
    include_path = include_path.resolve(strict=True)
    python_header = include_path / "Python.h"
    python_header_record = _trusted_regular_record(
        python_header,
        label="Python.h",
        executable=False,
        root_owner_required=False,
    )
    include_record = _trusted_directory_record(
        include_path,
        label="Python include directory",
        root_owner_required=False,
    )

    artifact_name = f"{_NATIVE_MODULE_NAME}{extension_suffix}"
    compile_template = _compile_arguments(
        compiler_path=compiler_path,
        architecture=architecture,
        sdk_path=sdk_path,
        include_path=include_path,
        source_path="$SOURCE",
        object_path="$OBJECT",
        dependency_path="$DEPFILE",
    )
    link_template = _link_arguments(
        linker_path=linker_path,
        architecture=architecture,
        sdk_path=sdk_path,
        sdk_version=sdk_version,
        object_path="$OBJECT",
        direct_linker_input_path=Path(direct_linker_input["path"]),
        output_path="$OUTPUT",
    )
    dependency_template = _dependency_arguments(
        compiler_path=compiler_path,
        architecture=architecture,
        sdk_path=sdk_path,
        include_path=include_path,
        source_path="$SOURCE",
        dependency_path="$DEPFILE",
    )
    fingerprint = {
        "schema": "sunofriend.separation-native-launcher-build-input.v1",
        "policy_id": _BUILD_POLICY_ID,
        "build_contract_sha256": _EXPECTED_BUILD_CONTRACT_SHA256,
        "source": {
            "resource_name": _SOURCE_RESOURCE_NAME,
            "sha256": _EXPECTED_SOURCE_SHA256,
            "bytes": len(source_bytes),
        },
        "toolchain": {
            "xcrun": xcrun_record,
            "compiler": {
                **compiler_record,
                "version": compiler_version,
                "resource_directory": compiler_resource_record,
            },
            "linker": linker_record,
            "explicit_sdk_linker_input": direct_linker_input,
            "sdk": {
                **sdk_record,
                "version": sdk_version,
            },
            "codesign": codesign_record,
        },
        "target": {
            "architecture": architecture,
            "clang_architecture": architecture_policy["clang_arch"],
            "mach_cpu_type": architecture_policy["mach_cpu_type"],
            "deployment_target": _DEPLOYMENT_TARGET,
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "python_cache_tag": sys.implementation.cache_tag,
            "python_extension_suffix": extension_suffix,
            "python_include": {
                **include_record,
                "python_header": python_header_record,
            },
        },
        "recipe": {
            "environment": {
                **_FIXED_ENVIRONMENT,
                "TMPDIR": "$STAGE",
            },
            "compile_arguments_template": list(compile_template),
            "link_arguments_template": list(link_template),
            "dependency_arguments_template": list(dependency_template),
            "sign_arguments_template": [
                str(codesign_path),
                "--force",
                "--sign",
                "-",
                "--timestamp=none",
                "$OUTPUT",
            ],
            "verify_arguments_template": [
                str(codesign_path),
                "--verify",
                "--strict",
                "--verbose=2",
                "$OUTPUT",
            ],
            "display_arguments_template": [
                str(codesign_path),
                "--display",
                "--verbose=4",
                "$OUTPUT",
            ],
            "entitlements_arguments_template": [
                str(codesign_path),
                "--display",
                "--entitlements",
                "-",
                "$OUTPUT",
            ],
            "timeouts_seconds": {
                "compile": _COMPILE_TIMEOUT_SECONDS,
                "link": _COMPILE_TIMEOUT_SECONDS,
                "codesign": _CODESIGN_TIMEOUT_SECONDS,
            },
        },
        "artifact_name": artifact_name,
    }
    prebuild_recipe_sha256 = _canonical_hash(fingerprint)
    return _BuildContext(
        source_bytes=source_bytes,
        fingerprint=_freeze(fingerprint),
        prebuild_recipe_sha256=prebuild_recipe_sha256,
        artifact_name=artifact_name,
        compiler_path=compiler_path,
        linker_path=linker_path,
        codesign_path=codesign_path,
    )


def _resolve_xcrun_path(
    *arguments: str,
    expect_directory: bool = False,
) -> Path:
    value = _single_line(
        _run_tool(
            _XCRUN,
            arguments,
            timeout=_DISCOVERY_TIMEOUT_SECONDS,
        ).stdout,
        "xcrun result",
    )
    path = Path(value)
    if not path.is_absolute():
        raise RuntimeError("xcrun returned a non-absolute path")
    path = path.resolve(strict=True)
    if expect_directory:
        _trusted_directory_record(path, label="xcrun directory result")
    else:
        _trusted_executable_record(path, label="xcrun executable result")
    return path


def _direct_linker_input_record(sdk_path: Path) -> dict[str, Any]:
    sdk_path = sdk_path.resolve(strict=True)
    requested = sdk_path / "usr" / "lib" / "libSystem.tbd"
    resolved = requested.resolve(strict=True)
    try:
        relative = resolved.relative_to(sdk_path)
    except ValueError as exc:
        raise RuntimeError(
            "the direct libSystem linker input escaped the audited SDK"
        ) from exc
    measured = _trusted_regular_record(
        resolved,
        label="direct libSystem linker input",
        executable=False,
        root_owner_required=True,
    )
    return {
        "requested_logical_path": "$SDK/usr/lib/libSystem.tbd",
        "logical_path": f"$SDK/{relative.as_posix()}",
        **measured,
    }


def _compile_arguments(
    *,
    compiler_path: Path,
    architecture: str,
    sdk_path: Path,
    include_path: Path,
    source_path: str,
    object_path: str,
    dependency_path: str,
) -> tuple[str, ...]:
    if architecture not in _SUPPORTED_ARCHITECTURES:
        raise RuntimeError("unsupported native launcher architecture")
    return (
        str(compiler_path),
        "-c",
        "-std=c11",
        "-O2",
        "-fno-common",
        "-fvisibility=hidden",
        "-Wall",
        "-Wextra",
        "-Werror",
        (f'-DSUNOFRIEND_NATIVE_SOURCE_SHA256="{_EXPECTED_SOURCE_SHA256}"'),
        (
            "-DSUNOFRIEND_NATIVE_BUILD_CONTRACT_SHA256="
            f'"{_EXPECTED_BUILD_CONTRACT_SHA256}"'
        ),
        "-arch",
        architecture,
        f"-mmacosx-version-min={_DEPLOYMENT_TARGET}",
        "-isysroot",
        str(sdk_path),
        "-I",
        str(include_path),
        "-MD",
        "-MF",
        dependency_path,
        "-MT",
        "sunofriend-native-output",
        source_path,
        "-o",
        object_path,
    )


def _link_arguments(
    *,
    linker_path: Path,
    architecture: str,
    sdk_path: Path,
    sdk_version: str,
    object_path: str,
    direct_linker_input_path: Path,
    output_path: str,
) -> tuple[str, ...]:
    if architecture not in _SUPPORTED_ARCHITECTURES:
        raise RuntimeError("unsupported native launcher architecture")
    _packed_mach_version(sdk_version)
    return (
        str(linker_path),
        "-arch",
        architecture,
        "-bundle",
        "-undefined",
        "dynamic_lookup",
        "-platform_version",
        "macos",
        _DEPLOYMENT_TARGET,
        sdk_version,
        "-syslibroot",
        str(sdk_path),
        "-o",
        output_path,
        object_path,
        str(direct_linker_input_path),
    )


def _dependency_arguments(
    *,
    compiler_path: Path,
    architecture: str,
    sdk_path: Path,
    include_path: Path,
    source_path: str,
    dependency_path: str,
) -> tuple[str, ...]:
    if architecture not in _SUPPORTED_ARCHITECTURES:
        raise RuntimeError("unsupported native launcher architecture")
    return (
        str(compiler_path),
        "-std=c11",
        (f'-DSUNOFRIEND_NATIVE_SOURCE_SHA256="{_EXPECTED_SOURCE_SHA256}"'),
        (
            "-DSUNOFRIEND_NATIVE_BUILD_CONTRACT_SHA256="
            f'"{_EXPECTED_BUILD_CONTRACT_SHA256}"'
        ),
        "-arch",
        architecture,
        f"-mmacosx-version-min={_DEPLOYMENT_TARGET}",
        "-isysroot",
        str(sdk_path),
        "-I",
        str(include_path),
        "-M",
        "-MT",
        "sunofriend-native-output",
        "-MF",
        dependency_path,
        source_path,
    )


def _parse_dependency_file(
    path: Path,
    *,
    relative_source_path: Path | None = None,
) -> tuple[Path, ...]:
    payload = _read_regular_file(
        path,
        maximum_bytes=_MAXIMUM_DEPENDENCY_BYTES,
        expected_mode=_PRIVATE_SOURCE_MODE,
    )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("native dependency file is not UTF-8") from exc
    unfolded = text.replace("\\\r\n", "").replace("\\\n", "")
    target, separator, body = unfolded.partition(":")
    if separator != ":" or target.strip() != "sunofriend-native-output":
        raise RuntimeError("native dependency file target is invalid")
    values = _parse_make_dependency_tokens(body)
    if not values or len(values) > _MAXIMUM_DEPENDENCIES:
        raise RuntimeError("native dependency closure has an invalid size")
    resolved: list[Path] = []
    seen: set[Path] = set()
    for value in values:
        candidate = Path(value)
        if not candidate.is_absolute():
            if (
                relative_source_path is None
                or candidate != Path(relative_source_path.name)
                or relative_source_path.parent != path.parent
            ):
                raise RuntimeError("native dependency paths must be absolute")
            candidate = relative_source_path.resolve(strict=True)
        else:
            candidate = candidate.resolve(strict=True)
        if candidate in seen:
            raise RuntimeError("native dependency closure contains duplicates")
        seen.add(candidate)
        resolved.append(candidate)
    return tuple(sorted(resolved, key=str))


def _parse_make_dependency_tokens(body: str) -> tuple[str, ...]:
    """Decode the make escaping emitted by Clang dependency files.

    Make dependency paths are not shell words: backslash quotes the following
    byte and a literal dollar is written as ``$$``.  Keeping this parser local
    and deliberately small avoids silently changing valid paths containing
    spaces, backslashes or dollar signs through shell-style tokenization.
    """

    values: list[str] = []
    token: list[str] = []
    index = 0
    while index < len(body):
        character = body[index]
        if character == "\\":
            index += 1
            if index >= len(body):
                raise RuntimeError("native dependency file escaping is invalid")
            token.append(body[index])
        elif character == "$" and index + 1 < len(body):
            if body[index + 1] == "$":
                token.append("$")
                index += 1
            else:
                token.append(character)
        elif character.isspace():
            if token:
                values.append("".join(token))
                token.clear()
        else:
            token.append(character)
        index += 1
    if token:
        values.append("".join(token))
    return tuple(values)


def _dependency_records(
    paths: tuple[Path, ...],
    *,
    source_path: Path,
    sdk_path: Path,
    python_include_path: Path,
    compiler_resource_path: Path,
) -> list[dict[str, Any]]:
    roots = (
        ("sdk", sdk_path.resolve(strict=True)),
        ("python_include", python_include_path.resolve(strict=True)),
        ("compiler_resource", compiler_resource_path.resolve(strict=True)),
    )
    source_path = source_path.resolve(strict=True)
    records: list[dict[str, Any]] = []
    for path in paths:
        if path == source_path:
            logical_path = "$SOURCE"
        else:
            logical_path = ""
            for label, root in roots:
                try:
                    relative = path.relative_to(root)
                except ValueError:
                    continue
                logical_path = f"${label.upper()}/{relative.as_posix()}"
                break
            if not logical_path:
                raise RuntimeError(
                    "native dependency escaped the audited include roots"
                )
        measured = _trusted_regular_record(
            path,
            label="native dependency",
            executable=False,
            root_owner_required=False,
        )
        records.append(
            {
                "logical_path": logical_path,
                "sha256": measured["sha256"],
                "bytes": measured["stat_identity"]["bytes"],
            }
        )
    records.sort(key=lambda item: item["logical_path"])
    if not any(record["logical_path"] == "$SOURCE" for record in records):
        raise RuntimeError("native dependency closure does not bind its source")
    _validate_dependency_records(records)
    return records


def _validate_dependency_records(value: Any) -> None:
    if not isinstance(value, list) or not value or len(value) > _MAXIMUM_DEPENDENCIES:
        raise RuntimeError("native dependency records are invalid")
    logical_paths: list[str] = []
    for record in value:
        if not isinstance(record, dict) or set(record) != {
            "logical_path",
            "sha256",
            "bytes",
        }:
            raise RuntimeError("native dependency record fields are invalid")
        logical_path = record["logical_path"]
        if (
            not isinstance(logical_path, str)
            or not logical_path.startswith("$")
            or "\x00" in logical_path
        ):
            raise RuntimeError("native dependency logical path is invalid")
        if not isinstance(record["sha256"], str) or not _SHA256_RE.fullmatch(
            record["sha256"]
        ):
            raise RuntimeError("native dependency hash is invalid")
        if (
            not isinstance(record["bytes"], int)
            or isinstance(record["bytes"], bool)
            or record["bytes"] < 0
        ):
            raise RuntimeError("native dependency byte count is invalid")
        logical_paths.append(logical_path)
    if logical_paths != sorted(set(logical_paths)):
        raise RuntimeError("native dependency logical paths are not canonical")
    if "$SOURCE" not in logical_paths:
        raise RuntimeError("native dependency source record is missing")


def _explicit_sdk_linker_input_receipt_records(
    record: Mapping[str, Any],
) -> list[dict[str, Any]]:
    value = [
        {
            "requested_logical_path": record["requested_logical_path"],
            "logical_path": record["logical_path"],
            "sha256": record["sha256"],
            "bytes": record["stat_identity"]["bytes"],
        }
    ]
    _validate_explicit_sdk_linker_input_records(value)
    return value


def _validate_explicit_sdk_linker_input_records(value: Any) -> None:
    if not isinstance(value, list) or len(value) != 1:
        raise RuntimeError("native direct linker-input records are invalid")
    record = value[0]
    if not isinstance(record, dict) or set(record) != {
        "requested_logical_path",
        "logical_path",
        "sha256",
        "bytes",
    }:
        raise RuntimeError("native direct linker-input fields are invalid")
    if record["requested_logical_path"] != "$SDK/usr/lib/libSystem.tbd":
        raise RuntimeError("native requested linker-input path is invalid")
    if (
        not isinstance(record["logical_path"], str)
        or not record["logical_path"].startswith("$SDK/usr/lib/")
        or not record["logical_path"].endswith("libSystem.B.tbd")
    ):
        raise RuntimeError("native resolved linker-input path is invalid")
    if not isinstance(record["sha256"], str) or not _SHA256_RE.fullmatch(
        record["sha256"]
    ):
        raise RuntimeError("native direct linker-input hash is invalid")
    if (
        not isinstance(record["bytes"], int)
        or isinstance(record["bytes"], bool)
        or record["bytes"] <= 0
    ):
        raise RuntimeError("native direct linker-input byte count is invalid")


def _compiled_object_receipt_record(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    value = {
        "filename": _OBJECT_NAME,
        "mode": _PRIVATE_SOURCE_MODE,
        "sha256": record["sha256"],
        "bytes": record["stat_identity"]["bytes"],
    }
    _validate_compiled_object_record(value)
    return value


def _validate_compiled_object_record(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {
        "filename",
        "mode",
        "sha256",
        "bytes",
    }:
        raise RuntimeError("native compiled-object record is invalid")
    if (
        value["filename"] != _OBJECT_NAME
        or value["mode"] != _PRIVATE_SOURCE_MODE
        or not isinstance(value["sha256"], str)
        or not _SHA256_RE.fullmatch(value["sha256"])
        or not isinstance(value["bytes"], int)
        or isinstance(value["bytes"], bool)
        or value["bytes"] <= 0
    ):
        raise RuntimeError("native compiled-object identity is invalid")


def _recorded_artifact_input_provenance_sha256(
    *,
    prebuild_recipe_sha256: str,
    header_closure: list[dict[str, Any]],
    compiled_object: dict[str, Any],
    explicit_sdk_linker_inputs: list[dict[str, Any]],
) -> str:
    _validate_dependency_records(header_closure)
    _validate_compiled_object_record(compiled_object)
    _validate_explicit_sdk_linker_input_records(explicit_sdk_linker_inputs)
    return _canonical_hash(
        {
            "schema": (
                "sunofriend.separation-native-launcher-"
                "recorded-artifact-input-provenance.v1"
            ),
            "scope": _plain(_PROVENANCE_SCOPE),
            "prebuild_recipe_sha256": prebuild_recipe_sha256,
            "header_closure": header_closure,
            "compiled_object": compiled_object,
            "explicit_sdk_linker_inputs": explicit_sdk_linker_inputs,
        }
    )


def _build_in_stage(
    *,
    context: _BuildContext,
    stage_directory: Path,
) -> None:
    _verify_private_directory(stage_directory)
    source_path = stage_directory / _SOURCE_COPY_NAME
    object_path = stage_directory / _OBJECT_NAME
    output_path = stage_directory / context.artifact_name
    receipt_path = stage_directory / _RECEIPT_NAME
    scan_dependency_path = stage_directory / _SCAN_DEPENDENCY_NAME
    compile_dependency_path = stage_directory / _COMPILE_DEPENDENCY_NAME
    _write_exclusive(
        source_path,
        context.source_bytes,
        mode=_PRIVATE_SOURCE_MODE,
    )
    copied_source = _read_regular_file(
        source_path,
        maximum_bytes=_MAXIMUM_SOURCE_BYTES,
        expected_mode=_PRIVATE_SOURCE_MODE,
    )
    if copied_source != context.source_bytes:
        raise RuntimeError("private source copy differs from packaged source")

    fingerprint = _plain(context.fingerprint)
    target = fingerprint["target"]
    toolchain = fingerprint["toolchain"]
    dependency_arguments = _dependency_arguments(
        compiler_path=context.compiler_path,
        architecture=target["architecture"],
        sdk_path=Path(toolchain["sdk"]["path"]),
        include_path=Path(target["python_include"]["path"]),
        source_path=_SOURCE_COPY_NAME,
        dependency_path=_SCAN_DEPENDENCY_NAME,
    )
    compile_arguments = _compile_arguments(
        compiler_path=context.compiler_path,
        architecture=target["architecture"],
        sdk_path=Path(toolchain["sdk"]["path"]),
        include_path=Path(target["python_include"]["path"]),
        source_path=_SOURCE_COPY_NAME,
        object_path=_OBJECT_NAME,
        dependency_path=_COMPILE_DEPENDENCY_NAME,
    )
    link_arguments = _link_arguments(
        linker_path=context.linker_path,
        architecture=target["architecture"],
        sdk_path=Path(toolchain["sdk"]["path"]),
        sdk_version=toolchain["sdk"]["version"],
        object_path=_OBJECT_NAME,
        direct_linker_input_path=Path(toolchain["explicit_sdk_linker_input"]["path"]),
        output_path=context.artifact_name,
    )
    environment = {
        **_FIXED_ENVIRONMENT,
        "TMPDIR": str(stage_directory),
    }
    _run_tool(
        context.compiler_path,
        dependency_arguments[1:],
        timeout=_COMPILE_TIMEOUT_SECONDS,
        cwd=stage_directory,
        environment=environment,
    )
    os.chmod(scan_dependency_path, _PRIVATE_SOURCE_MODE)
    dependency_paths = _parse_dependency_file(
        scan_dependency_path,
        relative_source_path=source_path,
    )
    dependency_records_before = _dependency_records(
        dependency_paths,
        source_path=source_path,
        sdk_path=Path(toolchain["sdk"]["path"]),
        python_include_path=Path(target["python_include"]["path"]),
        compiler_resource_path=Path(
            toolchain["compiler"]["resource_directory"]["path"]
        ),
    )
    _run_tool(
        context.compiler_path,
        compile_arguments[1:],
        timeout=_COMPILE_TIMEOUT_SECONDS,
        cwd=stage_directory,
        environment=environment,
    )
    os.chmod(object_path, _PRIVATE_SOURCE_MODE)
    os.chmod(compile_dependency_path, _PRIVATE_SOURCE_MODE)
    compiled_dependency_paths = _parse_dependency_file(
        compile_dependency_path,
        relative_source_path=source_path,
    )
    if compiled_dependency_paths != dependency_paths:
        raise RuntimeError(
            "native launcher dependency closure changed during compilation"
        )
    dependency_records_after = _dependency_records(
        dependency_paths,
        source_path=source_path,
        sdk_path=Path(toolchain["sdk"]["path"]),
        python_include_path=Path(target["python_include"]["path"]),
        compiler_resource_path=Path(
            toolchain["compiler"]["resource_directory"]["path"]
        ),
    )
    if dependency_records_after != dependency_records_before:
        raise RuntimeError(
            "native launcher dependency bytes changed during compilation"
        )
    compiled_object_before_link = _trusted_regular_record(
        object_path,
        label="compiled native object",
        executable=False,
        root_owner_required=False,
    )
    direct_linker_input_before_link = _direct_linker_input_record(
        Path(toolchain["sdk"]["path"])
    )
    _require_exact_mapping(
        direct_linker_input_before_link,
        toolchain["explicit_sdk_linker_input"],
        "explicit SDK linker-input identity before linking",
    )
    _run_tool(
        context.linker_path,
        link_arguments[1:],
        timeout=_COMPILE_TIMEOUT_SECONDS,
        cwd=stage_directory,
        environment=environment,
    )
    compiled_object_after_link = _trusted_regular_record(
        object_path,
        label="compiled native object",
        executable=False,
        root_owner_required=False,
    )
    _require_exact_mapping(
        compiled_object_after_link,
        compiled_object_before_link,
        "compiled object identity during linking",
    )
    direct_linker_input_after_link = _direct_linker_input_record(
        Path(toolchain["sdk"]["path"])
    )
    _require_exact_mapping(
        direct_linker_input_after_link,
        direct_linker_input_before_link,
        "explicit SDK linker-input identity during linking",
    )
    compiled_object = _compiled_object_receipt_record(compiled_object_after_link)
    explicit_sdk_linker_inputs = _explicit_sdk_linker_input_receipt_records(
        direct_linker_input_after_link
    )
    recorded_artifact_input_provenance_sha256 = (
        _recorded_artifact_input_provenance_sha256(
            prebuild_recipe_sha256=context.prebuild_recipe_sha256,
            header_closure=dependency_records_after,
            compiled_object=compiled_object,
            explicit_sdk_linker_inputs=explicit_sdk_linker_inputs,
        )
    )
    os.chmod(output_path, _PRIVATE_DIRECTORY_MODE)

    sign_arguments = (
        str(context.codesign_path),
        "--force",
        "--sign",
        "-",
        "--timestamp=none",
        str(output_path),
    )
    _run_tool(
        context.codesign_path,
        sign_arguments[1:],
        timeout=_CODESIGN_TIMEOUT_SECONDS,
        cwd=stage_directory,
        environment=environment,
    )
    os.chmod(output_path, _PRIVATE_EXECUTABLE_MODE)
    _fsync_file(output_path)

    verify_arguments = (
        str(context.codesign_path),
        "--verify",
        "--strict",
        "--verbose=2",
        str(output_path),
    )
    _run_tool(
        context.codesign_path,
        verify_arguments[1:],
        timeout=_CODESIGN_TIMEOUT_SECONDS,
        cwd=stage_directory,
        environment=environment,
    )
    display_arguments = (
        str(context.codesign_path),
        "--display",
        "--verbose=4",
        str(output_path),
    )
    display = _run_tool(
        context.codesign_path,
        display_arguments[1:],
        timeout=_CODESIGN_TIMEOUT_SECONDS,
        cwd=stage_directory,
        environment=environment,
    )
    entitlements_arguments = (
        str(context.codesign_path),
        "--display",
        "--entitlements",
        "-",
        str(output_path),
    )
    entitlements = _run_tool(
        context.codesign_path,
        entitlements_arguments[1:],
        timeout=_CODESIGN_TIMEOUT_SECONDS,
        cwd=stage_directory,
        environment=environment,
    )
    _require_no_entitlements(entitlements)
    signing_state = _codesign_state(
        display,
        architecture=target["architecture"],
        expected_identifier=Path(context.artifact_name).stem,
    )
    artifact = _measure_native_artifact(
        output_path,
        architecture=target["architecture"],
        expected_cpu_type=target["mach_cpu_type"],
        expected_sdk_version=toolchain["sdk"]["version"],
    )

    _remeasure_toolchain(context.fingerprint)
    receipt_document = {
        "schema": _SCHEMA,
        "policy_id": _BUILD_POLICY_ID,
        "status": "verified_private_build",
        "evidence_scope": "native_launcher_build_only",
        "execution_scope": "no_import_no_worker_no_separation",
        "prebuild_recipe_sha256": context.prebuild_recipe_sha256,
        "recorded_artifact_input_provenance_sha256": (
            recorded_artifact_input_provenance_sha256
        ),
        "provenance_scope": _plain(_PROVENANCE_SCOPE),
        "build_input": fingerprint,
        "build_invocation": {
            "source_copy": {
                "filename": _SOURCE_COPY_NAME,
                "mode": _PRIVATE_SOURCE_MODE,
                "sha256": hashlib.sha256(copied_source).hexdigest(),
                "bytes": len(copied_source),
            },
            "header_closure": dependency_records_after,
            "compiled_object": compiled_object,
            "explicit_sdk_linker_inputs": explicit_sdk_linker_inputs,
            "artifact_filename": context.artifact_name,
            "logical_dependency_arguments": fingerprint["recipe"][
                "dependency_arguments_template"
            ],
            "logical_compile_arguments": fingerprint["recipe"][
                "compile_arguments_template"
            ],
            "logical_link_arguments": fingerprint["recipe"]["link_arguments_template"],
            "logical_sign_arguments": fingerprint["recipe"]["sign_arguments_template"],
            "logical_verify_arguments": fingerprint["recipe"][
                "verify_arguments_template"
            ],
            "logical_display_arguments": fingerprint["recipe"][
                "display_arguments_template"
            ],
            "logical_entitlements_arguments": fingerprint["recipe"][
                "entitlements_arguments_template"
            ],
            "logical_environment": fingerprint["recipe"]["environment"],
            "transient_paths_serialized": False,
        },
        "artifact": {
            **artifact,
            "filename": context.artifact_name,
            "signing": signing_state,
        },
        "capabilities": {
            "source_verified": True,
            "native_artifact_built": True,
            "native_artifact_signed": True,
            "native_artifact_verified": True,
            "native_artifact_imported": False,
            "worker_started": False,
            "separation_started": False,
        },
    }
    receipt = _NativeLauncherBuildReceipt(_freeze(receipt_document))
    _write_exclusive(
        receipt_path,
        receipt.canonical_bytes(),
        mode=_PRIVATE_RECEIPT_MODE,
    )


def _verify_fresh_build(
    *,
    context: _BuildContext,
    cache_root: Path,
    build_directory: Path,
) -> _NativeLauncherBuild:
    _verify_private_directory(cache_root)
    if build_directory.parent != cache_root:
        raise RuntimeError("native build escaped its private root")
    if not build_directory.name.startswith(".fresh-build-"):
        raise RuntimeError("fresh native build directory name is invalid")
    _verify_private_directory(build_directory)

    receipt_bytes = _read_regular_file(
        build_directory / _RECEIPT_NAME,
        maximum_bytes=_MAXIMUM_RECEIPT_BYTES,
        expected_mode=_PRIVATE_RECEIPT_MODE,
    )
    document = _decode_canonical_receipt(receipt_bytes)
    _validate_receipt(document=document, context=context)
    object_path = build_directory / _OBJECT_NAME
    object_before = _compiled_object_receipt_record(
        _trusted_regular_record(
            object_path,
            label="fresh compiled native object",
            executable=False,
            root_owner_required=False,
        )
    )
    _require_exact_mapping(
        object_before,
        document["build_invocation"]["compiled_object"],
        "fresh compiled native object",
    )
    artifact_path = build_directory / context.artifact_name
    expected_artifact = document["artifact"]
    measured_before = _measure_native_artifact(
        artifact_path,
        architecture=document["build_input"]["target"]["architecture"],
        expected_cpu_type=document["build_input"]["target"]["mach_cpu_type"],
        expected_sdk_version=document["build_input"]["toolchain"]["sdk"]["version"],
    )
    _require_exact_mapping(
        measured_before,
        {key: expected_artifact[key] for key in measured_before},
        "fresh native artifact",
    )

    environment = {
        **_FIXED_ENVIRONMENT,
        "TMPDIR": str(build_directory),
    }
    verify = _run_tool(
        context.codesign_path,
        (
            "--verify",
            "--strict",
            "--verbose=2",
            str(artifact_path),
        ),
        timeout=_CODESIGN_TIMEOUT_SECONDS,
        cwd=build_directory,
        environment=environment,
    )
    del verify
    display = _run_tool(
        context.codesign_path,
        (
            "--display",
            "--verbose=4",
            str(artifact_path),
        ),
        timeout=_CODESIGN_TIMEOUT_SECONDS,
        cwd=build_directory,
        environment=environment,
    )
    entitlements = _run_tool(
        context.codesign_path,
        (
            "--display",
            "--entitlements",
            "-",
            str(artifact_path),
        ),
        timeout=_CODESIGN_TIMEOUT_SECONDS,
        cwd=build_directory,
        environment=environment,
    )
    _require_no_entitlements(entitlements)
    signing_state = _codesign_state(
        display,
        architecture=document["build_input"]["target"]["architecture"],
        expected_identifier=Path(context.artifact_name).stem,
    )
    _require_exact_mapping(
        signing_state,
        expected_artifact["signing"],
        "fresh native signature",
    )
    measured_after = _measure_native_artifact(
        artifact_path,
        architecture=document["build_input"]["target"]["architecture"],
        expected_cpu_type=document["build_input"]["target"]["mach_cpu_type"],
        expected_sdk_version=document["build_input"]["toolchain"]["sdk"]["version"],
    )
    _require_exact_mapping(
        measured_after,
        measured_before,
        "native artifact identity during signature verification",
    )
    object_after = _compiled_object_receipt_record(
        _trusted_regular_record(
            object_path,
            label="fresh compiled native object",
            executable=False,
            root_owner_required=False,
        )
    )
    _require_exact_mapping(
        object_after,
        object_before,
        "compiled object identity during artifact verification",
    )
    _remeasure_toolchain(context.fingerprint)

    receipt = _NativeLauncherBuildReceipt(_freeze(document))
    if receipt.canonical_bytes() != receipt_bytes:
        raise RuntimeError("fresh native build receipt is not canonical")
    return _NativeLauncherBuild(
        artifact_path=artifact_path,
        receipt=receipt,
        receipt_sha256=receipt.sha256,
    )


def _validate_receipt(
    *,
    document: Mapping[str, Any],
    context: _BuildContext,
) -> None:
    expected_fields = {
        "schema",
        "policy_id",
        "status",
        "evidence_scope",
        "execution_scope",
        "prebuild_recipe_sha256",
        "recorded_artifact_input_provenance_sha256",
        "provenance_scope",
        "build_input",
        "build_invocation",
        "artifact",
        "capabilities",
    }
    if set(document) != expected_fields:
        raise RuntimeError("native build receipt fields are invalid")
    if (
        document["schema"] != _SCHEMA
        or document["policy_id"] != _BUILD_POLICY_ID
        or document["status"] != "verified_private_build"
        or document["evidence_scope"] != "native_launcher_build_only"
        or document["execution_scope"] != "no_import_no_worker_no_separation"
        or document["prebuild_recipe_sha256"] != context.prebuild_recipe_sha256
        or document["provenance_scope"] != _plain(_PROVENANCE_SCOPE)
        or document["build_input"] != _plain(context.fingerprint)
    ):
        raise RuntimeError("native build receipt differs from current inputs")

    invocation = document["build_invocation"]
    if not isinstance(invocation, dict) or set(invocation) != {
        "source_copy",
        "header_closure",
        "compiled_object",
        "explicit_sdk_linker_inputs",
        "artifact_filename",
        "logical_dependency_arguments",
        "logical_compile_arguments",
        "logical_link_arguments",
        "logical_sign_arguments",
        "logical_verify_arguments",
        "logical_display_arguments",
        "logical_entitlements_arguments",
        "logical_environment",
        "transient_paths_serialized",
    }:
        raise RuntimeError("native build invocation provenance is invalid")
    source_copy = invocation["source_copy"]
    if not isinstance(source_copy, dict) or set(source_copy) != {
        "filename",
        "mode",
        "sha256",
        "bytes",
    }:
        raise RuntimeError("native build source-copy provenance is invalid")
    if (
        source_copy["filename"] != _SOURCE_COPY_NAME
        or source_copy["mode"] != _PRIVATE_SOURCE_MODE
        or source_copy["sha256"] != _EXPECTED_SOURCE_SHA256
        or source_copy["bytes"] != len(context.source_bytes)
    ):
        raise RuntimeError("recorded native source copy is invalid")

    fingerprint = _plain(context.fingerprint)
    if (
        invocation["artifact_filename"] != context.artifact_name
        or invocation["logical_dependency_arguments"]
        != fingerprint["recipe"]["dependency_arguments_template"]
        or invocation["logical_compile_arguments"]
        != fingerprint["recipe"]["compile_arguments_template"]
        or invocation["logical_link_arguments"]
        != fingerprint["recipe"]["link_arguments_template"]
        or invocation["logical_sign_arguments"]
        != fingerprint["recipe"]["sign_arguments_template"]
        or invocation["logical_verify_arguments"]
        != fingerprint["recipe"]["verify_arguments_template"]
        or invocation["logical_display_arguments"]
        != fingerprint["recipe"]["display_arguments_template"]
        or invocation["logical_entitlements_arguments"]
        != fingerprint["recipe"]["entitlements_arguments_template"]
        or invocation["logical_environment"] != fingerprint["recipe"]["environment"]
        or invocation["transient_paths_serialized"] is not False
    ):
        raise RuntimeError("recorded native build invocation is invalid")
    _validate_dependency_records(invocation["header_closure"])
    _validate_compiled_object_record(invocation["compiled_object"])
    _validate_explicit_sdk_linker_input_records(
        invocation["explicit_sdk_linker_inputs"]
    )
    expected_input_provenance_hash = _recorded_artifact_input_provenance_sha256(
        prebuild_recipe_sha256=context.prebuild_recipe_sha256,
        header_closure=invocation["header_closure"],
        compiled_object=invocation["compiled_object"],
        explicit_sdk_linker_inputs=invocation["explicit_sdk_linker_inputs"],
    )
    if (
        document["recorded_artifact_input_provenance_sha256"]
        != expected_input_provenance_hash
    ):
        raise RuntimeError("native artifact-input provenance hash is invalid")

    artifact = document["artifact"]
    if not isinstance(artifact, dict) or set(artifact) != {
        "filename",
        "sha256",
        "bytes",
        "stat_identity",
        "mach_o",
        "signing",
    }:
        raise RuntimeError("native build artifact receipt is invalid")
    if artifact["filename"] != context.artifact_name:
        raise RuntimeError("native build artifact filename is invalid")
    capabilities = document["capabilities"]
    if capabilities != {
        "source_verified": True,
        "native_artifact_built": True,
        "native_artifact_signed": True,
        "native_artifact_verified": True,
        "native_artifact_imported": False,
        "worker_started": False,
        "separation_started": False,
    }:
        raise RuntimeError("native build capabilities are invalid")


def _decode_canonical_receipt(payload: bytes) -> dict[str, Any]:
    if not payload or len(payload) > _MAXIMUM_RECEIPT_BYTES:
        raise RuntimeError("native build receipt has an invalid size")

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise RuntimeError("native build receipt has duplicate fields")
            result[key] = value
        return result

    try:
        document = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                RuntimeError(f"native build receipt contains non-finite {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("native build receipt is not canonical JSON") from exc
    if not isinstance(document, dict):
        raise RuntimeError("native build receipt must be a JSON object")
    if _canonical_json(document) != payload:
        raise RuntimeError("native build receipt is not canonical JSON")
    return document


def _measure_native_artifact(
    path: Path,
    *,
    architecture: str,
    expected_cpu_type: int,
    expected_sdk_version: str,
) -> dict[str, Any]:
    payload, identity = _read_regular_file_with_identity(
        path,
        maximum_bytes=_MAXIMUM_BINARY_BYTES,
        expected_mode=_PRIVATE_EXECUTABLE_MODE,
    )
    if not payload:
        raise RuntimeError("native launcher artifact is empty")
    mach_o = _parse_thin_mach_o(
        payload,
        architecture=architecture,
        expected_cpu_type=expected_cpu_type,
        expected_sdk_version=expected_sdk_version,
    )
    return {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "stat_identity": identity,
        "mach_o": mach_o,
    }


def _parse_thin_mach_o(
    payload: bytes,
    *,
    architecture: str,
    expected_cpu_type: int,
    expected_sdk_version: str,
) -> dict[str, Any]:
    if len(payload) < 32:
        raise RuntimeError("native launcher artifact is not a Mach-O bundle")
    magic = payload[:4]
    if magic == b"\xcf\xfa\xed\xfe":
        byte_order = "little"
        values = struct.unpack("<8I", payload[:32])
    elif magic == b"\xfe\xed\xfa\xcf":
        byte_order = "big"
        values = struct.unpack(">8I", payload[:32])
    else:
        raise RuntimeError("native launcher artifact is not thin 64-bit Mach-O")
    (
        magic_value,
        cpu_type,
        cpu_subtype,
        file_type,
        command_count,
        command_bytes,
        flags,
        reserved,
    ) = values
    if cpu_type != expected_cpu_type:
        raise RuntimeError("native launcher Mach-O architecture is invalid")
    if file_type != 8:
        raise RuntimeError("native launcher Mach-O is not a bundle")
    if command_bytes > len(payload) - 32:
        raise RuntimeError("native launcher Mach-O load commands are truncated")
    load_commands = _parse_mach_load_commands(
        payload,
        byte_order="<" if byte_order == "little" else ">",
        command_count=command_count,
        command_bytes=command_bytes,
        expected_sdk_version=expected_sdk_version,
    )
    return {
        "format": "mach_o_64",
        "byte_order": byte_order,
        "magic": magic_value,
        "architecture": architecture,
        "cpu_type": cpu_type,
        "cpu_subtype": cpu_subtype,
        "file_type": file_type,
        "file_type_name": "MH_BUNDLE",
        "load_command_count": command_count,
        "load_command_bytes": command_bytes,
        "flags": flags,
        "reserved": reserved,
        **load_commands,
    }


def _parse_mach_load_commands(
    payload: bytes,
    *,
    byte_order: str,
    command_count: int,
    command_bytes: int,
    expected_sdk_version: str,
) -> dict[str, Any]:
    offset = 32
    limit = offset + command_bytes
    command_ids: list[int] = []
    dylibs: list[str] = []
    build_versions: list[dict[str, int]] = []
    signature_commands: list[dict[str, int]] = []
    uuid_commands: list[str] = []
    forbidden_dynamic_commands = {
        _MACH_ID_DYLIB,
        _MACH_LOAD_DYLINKER,
        _MACH_ID_DYLINKER,
        _MACH_PREBOUND_DYLIB,
        _MACH_LOAD_WEAK_DYLIB,
        _MACH_LAZY_LOAD_DYLIB,
        _MACH_REEXPORT_DYLIB,
        _MACH_LOAD_UPWARD_DYLIB,
        _MACH_DYLD_ENVIRONMENT,
    }
    for _ in range(command_count):
        if offset + 8 > limit:
            raise RuntimeError("native launcher Mach-O load command is truncated")
        command, command_size = struct.unpack(
            f"{byte_order}2I",
            payload[offset : offset + 8],
        )
        if command_size < 8 or command_size % 4 != 0 or offset + command_size > limit:
            raise RuntimeError("native launcher Mach-O load command size is invalid")
        command_payload = payload[offset : offset + command_size]
        command_ids.append(command)
        if command == _MACH_RPATH:
            raise RuntimeError("native launcher Mach-O must not contain an RPATH")
        if command == _MACH_UUID:
            if command_size != 24:
                raise RuntimeError("native launcher Mach-O UUID command is invalid")
            uuid = command_payload[8:24]
            if uuid == b"\x00" * 16:
                raise RuntimeError("native launcher Mach-O UUID is all zero")
            uuid_commands.append(uuid.hex())
        if command in forbidden_dynamic_commands:
            raise RuntimeError(
                "native launcher Mach-O contains a forbidden dynamic dependency"
            )
        if command == _MACH_LOAD_DYLIB:
            if command_size < 24:
                raise RuntimeError("native launcher dylib command is truncated")
            name_offset = struct.unpack(
                f"{byte_order}I",
                command_payload[8:12],
            )[0]
            if name_offset < 24 or name_offset >= command_size:
                raise RuntimeError("native launcher dylib name offset is invalid")
            name_bytes = command_payload[name_offset:]
            terminator = name_bytes.find(b"\x00")
            if terminator <= 0:
                raise RuntimeError("native launcher dylib name is invalid")
            try:
                name = name_bytes[:terminator].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise RuntimeError("native launcher dylib name is not UTF-8") from exc
            dylibs.append(name)
        elif command == _MACH_BUILD_VERSION:
            if command_size < 24:
                raise RuntimeError("native launcher build-version command is truncated")
            platform_id, minimum, sdk, tool_count = struct.unpack(
                f"{byte_order}4I",
                command_payload[8:24],
            )
            if command_size < 24 + tool_count * 8:
                raise RuntimeError("native launcher build-version tools are truncated")
            build_versions.append(
                {
                    "platform": platform_id,
                    "minimum": minimum,
                    "sdk": sdk,
                    "tool_count": tool_count,
                }
            )
        elif command == _MACH_CODE_SIGNATURE:
            if command_size != 16:
                raise RuntimeError("native launcher code-signature command is invalid")
            data_offset, data_size = struct.unpack(
                f"{byte_order}2I",
                command_payload[8:16],
            )
            if (
                data_size == 0
                or data_offset < limit
                or data_offset + data_size > len(payload)
            ):
                raise RuntimeError(
                    "native launcher embedded signature range is invalid"
                )
            signature_commands.append(
                {
                    "data_offset": data_offset,
                    "data_bytes": data_size,
                }
            )
        offset += command_size
    if offset != limit:
        raise RuntimeError("native launcher Mach-O load-command bytes are invalid")
    if dylibs != list(_ALLOWED_DYLIBS):
        raise RuntimeError("native launcher Mach-O dylib allowlist failed")
    expected_minimum = _packed_mach_version(_DEPLOYMENT_TARGET)
    expected_sdk = _packed_mach_version(expected_sdk_version)
    if (
        len(build_versions) != 1
        or build_versions[0]["platform"] != 1
        or build_versions[0]["minimum"] != expected_minimum
        or build_versions[0]["sdk"] != expected_sdk
    ):
        raise RuntimeError("native launcher Mach-O build version is invalid")
    if len(signature_commands) != 1:
        raise RuntimeError("native launcher Mach-O must contain one embedded signature")
    if len(uuid_commands) != 1:
        raise RuntimeError("native launcher Mach-O must contain exactly one UUID")
    return {
        "load_command_ids": command_ids,
        "linked_dylibs": dylibs,
        "rpaths": [],
        "build_version": build_versions[0],
        "code_signature": signature_commands[0],
        "uuid": uuid_commands[0],
    }


def _packed_mach_version(value: str) -> int:
    components = value.split(".")
    if not 1 <= len(components) <= 3:
        raise RuntimeError("invalid Mach-O deployment target")
    try:
        numbers = [int(component) for component in components]
    except ValueError as exc:
        raise RuntimeError("invalid Mach-O deployment target") from exc
    numbers.extend([0] * (3 - len(numbers)))
    major, minor, patch = numbers
    if not 0 <= major <= 0xFFFF or not 0 <= minor <= 0xFF or not 0 <= patch <= 0xFF:
        raise RuntimeError("invalid Mach-O deployment target")
    return (major << 16) | (minor << 8) | patch


def _codesign_state(
    result: subprocess.CompletedProcess[bytes],
    *,
    architecture: str,
    expected_identifier: str,
) -> dict[str, Any]:
    text = _bounded_text(
        result.stdout + result.stderr,
        "codesign display",
        allow_empty=False,
    )
    values: dict[str, str] = {}
    wanted = {
        "Identifier",
        "Format",
        "Signature",
        "Info.plist",
        "TeamIdentifier",
        "Sealed Resources",
        "Internal requirements",
        "CDHash",
        "CandidateCDHash sha256",
        "CandidateCDHashFull sha256",
        "Hash type",
        "Hash choices",
        "VersionPlatform",
        "VersionMin",
        "VersionSDK",
        "CMSDigest",
        "CMSDigestType",
    }
    for line in text.splitlines():
        if line.startswith("CodeDirectory "):
            if "CodeDirectory" in values:
                raise RuntimeError("codesign display repeated an identity field")
            values["CodeDirectory"] = line.removeprefix("CodeDirectory ")
            continue
        if line.startswith("Internal requirements "):
            if "Internal requirements" in values:
                raise RuntimeError("codesign display repeated an identity field")
            values["Internal requirements"] = line.removeprefix(
                "Internal requirements "
            )
            continue
        key, separator, value = line.partition("=")
        if separator and key in wanted:
            if key in values:
                raise RuntimeError("codesign display repeated an identity field")
            values[key] = value
    if values.get("Signature") != "adhoc":
        raise RuntimeError("native launcher does not have an ad-hoc signature")
    code_directory = values.get("CodeDirectory", "")
    cdhash = values.get("CDHash", "")
    candidate = values.get("CandidateCDHash sha256", "")
    candidate_full = values.get("CandidateCDHashFull sha256", "")
    if (
        values.get("Identifier") != expected_identifier
        or values.get("Format") != f"Mach-O thin ({architecture})"
        or values.get("Hash type") != "sha256 size=32"
        or values.get("Hash choices") != "sha256"
        or values.get("TeamIdentifier") != "not set"
        or values.get("Info.plist") != "not bound"
        or values.get("Sealed Resources") != "none"
        or values.get("Internal requirements") != "count=0 size=12"
        or values.get("CMSDigestType") != "2"
        or not re.fullmatch(
            r"v=[0-9]+ size=[0-9]+ flags=0x2\(adhoc\) "
            r"hashes=[0-9]+\+[0-9]+ location=embedded",
            code_directory,
        )
        or not re.fullmatch(r"[0-9a-f]{40}", cdhash)
        or candidate != cdhash
        or not re.fullmatch(r"[0-9a-f]{64}", candidate_full)
        or not candidate_full.startswith(cdhash)
        or values.get("CMSDigest") != candidate_full
    ):
        raise RuntimeError("native launcher signature identity is incomplete")
    return {
        "kind": "adhoc",
        "verified_strict": True,
        "entitlements_present": False,
        "identity": {key: values[key] for key in sorted(values)},
    }


def _require_no_entitlements(
    result: subprocess.CompletedProcess[bytes],
) -> None:
    if result.stdout:
        raise RuntimeError("native launcher signature contains entitlements")
    stderr = _bounded_text(
        result.stderr,
        "codesign entitlements",
        allow_empty=True,
    )
    residual = [
        line
        for line in stderr.splitlines()
        if line and not line.startswith("Executable=")
    ]
    if residual:
        raise RuntimeError("native launcher entitlement state is ambiguous")


def _run_tool(
    executable: Path,
    arguments: tuple[str, ...],
    *,
    timeout: float,
    cwd: Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    if not executable.is_absolute():
        raise RuntimeError("native build tools must use absolute paths")
    command = (str(executable), *arguments)
    process: subprocess.Popen[bytes] | None = None
    cleanup_attempted = False
    stdout_buffer = bytearray()
    stderr_buffer = bytearray()
    selector = selectors.DefaultSelector()
    try:
        _validate_parent_sigchld()
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            close_fds=True,
            pass_fds=(),
            start_new_session=True,
            cwd=None if cwd is None else str(cwd),
            env=dict(_FIXED_ENVIRONMENT if environment is None else environment),
        )
        if process.stdout is None or process.stderr is None:
            raise RuntimeError("native build tool pipes were not created")
        os.set_blocking(process.stdout.fileno(), False)
        os.set_blocking(process.stderr.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ, stdout_buffer)
        selector.register(process.stderr, selectors.EVENT_READ, stderr_buffer)
        deadline = time.monotonic() + timeout
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                cleanup_attempted = True
                _kill_process_group_and_reap(
                    process,
                    timeout=_TOOL_CLEANUP_TIMEOUT_SECONDS,
                )
                raise RuntimeError(
                    f"{executable.name} exceeded its fixed build timeout"
                )
            events = selector.select(min(remaining, 0.25))
            for key, _ in events:
                try:
                    chunk = os.read(key.fd, 8192)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                buffer = key.data
                buffer.extend(chunk)
                if len(buffer) > _MAXIMUM_TOOL_OUTPUT_BYTES:
                    cleanup_attempted = True
                    _kill_process_group_and_reap(
                        process,
                        timeout=_TOOL_CLEANUP_TIMEOUT_SECONDS,
                    )
                    raise RuntimeError(
                        f"{executable.name} emitted excessive build output"
                    )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            cleanup_attempted = True
            _kill_process_group_and_reap(
                process,
                timeout=_TOOL_CLEANUP_TIMEOUT_SECONDS,
            )
            raise RuntimeError(f"{executable.name} exceeded its fixed build timeout")
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            cleanup_attempted = True
            _kill_process_group_and_reap(
                process,
                timeout=_TOOL_CLEANUP_TIMEOUT_SECONDS,
            )
            raise RuntimeError(
                f"{executable.name} exceeded its fixed build timeout"
            ) from exc
    except BaseException:
        if process is not None and not cleanup_attempted:
            _kill_process_group_and_reap(
                process,
                timeout=_TOOL_CLEANUP_TIMEOUT_SECONDS,
            )
        raise
    finally:
        selector.close()
        if process is not None:
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
    result = subprocess.CompletedProcess(
        command,
        process.returncode,
        bytes(stdout_buffer),
        bytes(stderr_buffer),
    )
    if (
        len(result.stdout) > _MAXIMUM_TOOL_OUTPUT_BYTES
        or len(result.stderr) > _MAXIMUM_TOOL_OUTPUT_BYTES
    ):
        raise RuntimeError(f"{executable.name} emitted excessive build output")
    if result.returncode != 0:
        detail = (
            (result.stderr or result.stdout)[:4096]
            .decode(
                "utf-8",
                errors="replace",
            )
            .strip()
        )
        if cwd is not None:
            detail = detail.replace(str(cwd), "$STAGE")
        raise RuntimeError(
            f"{executable.name} failed with exit {result.returncode}: {detail}"
        )
    return result


def _validate_parent_sigchld() -> None:
    if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
        raise RuntimeError("native build tools require the default SIGCHLD disposition")
    if sys.platform != "darwin":
        return

    libc = ctypes.CDLL(None, use_errno=True)
    sigaction = libc.sigaction
    sigaction.argtypes = (
        ctypes.c_int,
        ctypes.POINTER(_DarwinSigaction),
        ctypes.POINTER(_DarwinSigaction),
    )
    sigaction.restype = ctypes.c_int
    current = _DarwinSigaction()
    if sigaction(signal.SIGCHLD, None, ctypes.byref(current)) != 0:
        error_number = ctypes.get_errno()
        raise RuntimeError(
            "native build could not inspect the parent SIGCHLD disposition "
            f"(errno {error_number})"
        )
    if current.handler not in (None, 0):
        raise RuntimeError("native build tools require the raw default SIGCHLD handler")
    if current.flags & _DARWIN_SA_NOCLDWAIT:
        raise RuntimeError("native build tools reject SIGCHLD SA_NOCLDWAIT")


def _kill_process_group_and_reap(
    process: subprocess.Popen[bytes],
    *,
    timeout: float,
) -> None:
    deadline = time.monotonic() + timeout
    group_error: OSError | None = None
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError as exc:
        group_error = exc

    if process.poll() is None:
        try:
            os.kill(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RuntimeError("native build tool cleanup deadline expired")
    try:
        process.wait(timeout=remaining)
    except subprocess.TimeoutExpired as exc:
        if process.poll() is None:
            try:
                os.kill(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(
                "native build tool was not reaped before its cleanup deadline"
            ) from exc
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as final_exc:
            raise RuntimeError(
                "native build tool was not reaped before its cleanup deadline"
            ) from final_exc
    if group_error is not None:
        raise RuntimeError(
            "native build tool process-group kill failed"
        ) from group_error


def _remeasure_toolchain(fingerprint: Mapping[str, Any]) -> None:
    toolchain = fingerprint["toolchain"]
    current_xcrun = _trusted_executable_record(_XCRUN, label="xcrun")
    current_compiler = _trusted_executable_record(
        Path(toolchain["compiler"]["path"]),
        label="compiler",
    )
    current_codesign = _trusted_executable_record(
        Path(toolchain["codesign"]["path"]),
        label="codesign",
    )
    current_linker = _trusted_executable_record(
        Path(toolchain["linker"]["path"]),
        label="linker",
    )
    current_sdk = _trusted_directory_record(
        Path(toolchain["sdk"]["path"]),
        label="SDK",
    )
    _require_exact_mapping(
        current_xcrun,
        {key: toolchain["xcrun"][key] for key in current_xcrun},
        "xcrun identity",
    )
    _require_exact_mapping(
        current_compiler,
        {key: toolchain["compiler"][key] for key in current_compiler},
        "compiler identity",
    )
    current_compiler_resource = _trusted_directory_record(
        Path(toolchain["compiler"]["resource_directory"]["path"]),
        label="compiler resource directory",
    )
    _require_exact_mapping(
        current_compiler_resource,
        toolchain["compiler"]["resource_directory"],
        "compiler resource directory identity",
    )
    _require_exact_mapping(
        current_codesign,
        {key: toolchain["codesign"][key] for key in current_codesign},
        "codesign identity",
    )
    _require_exact_mapping(
        current_linker,
        {key: toolchain["linker"][key] for key in current_linker},
        "linker identity",
    )
    current_direct_linker_input = _direct_linker_input_record(
        Path(toolchain["sdk"]["path"])
    )
    _require_exact_mapping(
        current_direct_linker_input,
        toolchain["explicit_sdk_linker_input"],
        "direct linker-input identity",
    )
    _require_exact_mapping(
        current_sdk,
        {key: toolchain["sdk"][key] for key in current_sdk},
        "SDK identity",
    )
    python_include = fingerprint["target"]["python_include"]
    current_include = _trusted_directory_record(
        Path(python_include["path"]),
        label="Python include directory",
        root_owner_required=False,
    )
    current_header = _trusted_regular_record(
        Path(python_include["python_header"]["path"]),
        label="Python.h",
        executable=False,
        root_owner_required=False,
    )
    _require_exact_mapping(
        current_include,
        {key: python_include[key] for key in current_include},
        "Python include identity",
    )
    _require_exact_mapping(
        current_header,
        python_include["python_header"],
        "Python.h identity",
    )


def _trusted_executable_record(path: Path, *, label: str) -> dict[str, Any]:
    return _trusted_regular_record(
        path,
        label=label,
        executable=True,
        root_owner_required=True,
    )


def _trusted_regular_record(
    path: Path,
    *,
    label: str,
    executable: bool,
    root_owner_required: bool,
) -> dict[str, Any]:
    if not path.is_absolute():
        raise RuntimeError(f"{label} path must be absolute")
    path = path.resolve(strict=True)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        measured = os.fstat(descriptor)
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1_048_576)
            if not chunk:
                break
            digest.update(chunk)
        measured_after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if not stat.S_ISREG(measured.st_mode):
        raise RuntimeError(f"{label} must be a regular file")
    if root_owner_required and measured.st_uid != 0:
        raise RuntimeError(f"{label} must be owned by root")
    if measured.st_mode & 0o022:
        raise RuntimeError(f"{label} must not be group/other writable")
    if executable and measured.st_mode & 0o111 == 0:
        raise RuntimeError(f"{label} must be executable")
    if _stat_identity(measured_after) != _stat_identity(measured):
        raise RuntimeError(f"{label} changed during hashing")
    return {
        "path": str(path),
        "sha256": digest.hexdigest(),
        "stat_identity": _stat_identity(measured),
    }


def _trusted_directory_record(
    path: Path,
    *,
    label: str,
    root_owner_required: bool = True,
) -> dict[str, Any]:
    if not path.is_absolute():
        raise RuntimeError(f"{label} path must be absolute")
    path = path.resolve(strict=True)
    measured = os.lstat(path)
    if not stat.S_ISDIR(measured.st_mode):
        raise RuntimeError(f"{label} must be a directory")
    if root_owner_required and measured.st_uid != 0:
        raise RuntimeError(f"{label} must be owned by root")
    if measured.st_mode & 0o022:
        raise RuntimeError(f"{label} must not be group/other writable")
    return {
        "path": str(path),
        "stat_identity": _stat_identity(measured),
    }


def _stat_identity(measured: os.stat_result) -> dict[str, int]:
    return {
        "device": measured.st_dev,
        "inode": measured.st_ino,
        "mode": stat.S_IMODE(measured.st_mode),
        "links": measured.st_nlink,
        "owner": measured.st_uid,
        "group": measured.st_gid,
        "bytes": measured.st_size,
        "modified_ns": measured.st_mtime_ns,
        "changed_ns": measured.st_ctime_ns,
    }


def _normalise_cache_root(path: Path) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    return expanded.absolute()


def _ensure_private_directory(path: Path) -> None:
    try:
        path.mkdir(mode=_PRIVATE_DIRECTORY_MODE, parents=True, exist_ok=False)
    except FileExistsError:
        pass
    _verify_private_directory(path)


def _verify_private_directory(path: Path) -> None:
    measured = os.lstat(path)
    if (
        not stat.S_ISDIR(measured.st_mode)
        or measured.st_uid != os.getuid()
        or stat.S_IMODE(measured.st_mode) != _PRIVATE_DIRECTORY_MODE
    ):
        raise RuntimeError("native build directories must be owner-only")


def _write_exclusive(path: Path, payload: bytes, *, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, mode)
    try:
        os.fchmod(descriptor, mode)
        view = memoryview(payload)
        offset = 0
        while offset < len(view):
            written = os.write(descriptor, view[offset:])
            if written <= 0:
                raise RuntimeError("native build file write made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_regular_file(
    path: Path,
    *,
    maximum_bytes: int,
    expected_mode: int,
) -> bytes:
    payload, _ = _read_regular_file_with_identity(
        path,
        maximum_bytes=maximum_bytes,
        expected_mode=expected_mode,
    )
    return payload


def _read_regular_file_with_identity(
    path: Path,
    *,
    maximum_bytes: int,
    expected_mode: int,
) -> tuple[bytes, dict[str, int]]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != expected_mode
            or before.st_size < 0
            or before.st_size > maximum_bytes
        ):
            raise RuntimeError("native build file identity is invalid")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(131_072, remaining))
            if not chunk:
                raise RuntimeError("native build file was truncated")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise RuntimeError("native build file grew during inspection")
        after = os.fstat(descriptor)
        if _stat_identity(after) != _stat_identity(before):
            raise RuntimeError("native build file changed during inspection")
        return b"".join(chunks), _stat_identity(after)
    finally:
        os.close(descriptor)


def _fsync_file(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _lexists(path: Path) -> bool:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    return True


def _single_line(payload: bytes, label: str) -> str:
    text = _bounded_text(payload, label)
    lines = text.splitlines()
    if len(lines) != 1 or not lines[0].strip():
        raise RuntimeError(f"{label} must contain exactly one line")
    return lines[0].strip()


def _bounded_text(
    payload: bytes,
    label: str,
    *,
    allow_empty: bool = False,
) -> str:
    if len(payload) > _MAXIMUM_TOOL_OUTPUT_BYTES:
        raise RuntimeError(f"{label} is too large")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"{label} is not UTF-8") from exc
    text = text.strip()
    if not text and not allow_empty:
        raise RuntimeError(f"{label} is empty")
    return text


def _absolute_recorded_path(value: Any, *, label: str) -> Path:
    if not isinstance(value, str) or "\x00" in value:
        raise RuntimeError(f"{label} is invalid")
    path = Path(value)
    if not path.is_absolute():
        raise RuntimeError(f"{label} must be absolute")
    return path


def _require_exact_mapping(
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
    label: str,
) -> None:
    if _plain(actual) != _plain(expected):
        raise RuntimeError(f"{label} changed")
