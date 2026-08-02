"""Private, model-free binding for one macOS runtime process image.

The ordinary Python launcher path is not necessarily the image that remains
mapped in the child process.  In particular, the python.org framework launcher
transitions to ``Resources/Python.app/Contents/MacOS/Python``.  This module
starts one inert child through the exact ``sandbox-exec`` provider, observes
the final image from the parent by PID, and compares the kernel CDHash with the
same image's strictly validated static code signature.

The standalone canary is narrow development evidence: it starts no model,
reads no audio, writes no output and enables no separator.  The reusable
prepared binding is also attached to one separately authorised MelRoFormer
worker observation.  Neither use proves the identity of every dynamically
loaded native library or full executable-byte identity.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ._separation_macos_sandbox_probe import (
    SANDBOX_EXEC_PATH,
    _regular_file_identity,
)
from .separation_contract import _canonical_json_bytes, _freeze_json


SCHEMA = "sunofriend.private-macos-runtime-process-image.v1"
POLICY_ID = "private-macos-runtime-process-image-observation-v1"
BINDING_SCHEMA = "sunofriend.private-macos-runtime-process-image-binding.v1"
BINDING_POLICY_ID = "private-macos-runtime-process-image-binding-v1"
PROBE_ID = "parent-pid-code-identity-v1"
_SANDBOX_PROFILE = "(version 1)\n(allow default)\n(deny network*)\n"
_CHILD_SOURCE = (
    "import json,time; "
    "print(json.dumps({'arithmetic':42,'probe_id':"
    "'parent-pid-code-identity-v1'},sort_keys=True,separators=(',',':')),"
    "flush=True); time.sleep(1.0)"
)
_ENVIRONMENT = {
    "HOME": "/var/empty",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONIOENCODING": "utf-8",
    "PYTHONNOUSERSITE": "1",
    "TMPDIR": "/var/empty",
}
_MAXIMUM_PATH_BYTES = 4096
_MAXIMUM_OUTPUT_BYTES = 16 * 1024
_OBSERVATION_TIMEOUT_SECONDS = 2.0
_POLL_SECONDS = 0.01
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_CDHASH_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class _PreparedRuntimeProcessImageBinding:
    """Private pre-launch identities needed for one exact-child observation."""

    machine: str
    provider_path: Path
    runtime_launcher_path: Path
    process_image_path: Path
    provider_identity: Mapping[str, Any]
    runtime_launcher_identity: Mapping[str, Any]
    process_image_identity: Mapping[str, Any]
    provider_cdhash: str
    runtime_launcher_cdhash: str
    process_image_cdhash: str
    transition: str


def _prepare_runtime_process_image_binding(
    *, runtime_path: str | Path
) -> _PreparedRuntimeProcessImageBinding:
    """Measure static identities before a private child is launched."""

    if platform.system() != "Darwin":
        raise RuntimeError("macOS runtime process-image binding requires Darwin")
    provider = _regular_file_identity(SANDBOX_EXEC_PATH)
    launcher = _regular_file_identity(runtime_path)
    image_path = _expected_python_process_image(Path(launcher["resolved_path"]))
    image = _regular_file_identity(image_path)
    if not _filesystem_is_read_only(Path(provider["resolved_path"])):
        raise RuntimeError("macOS Sandbox provider filesystem is not read-only")
    provider_signature = _static_code_identity(Path(provider["resolved_path"]))
    launcher_signature = _static_code_identity(Path(launcher["resolved_path"]))
    image_signature = _static_code_identity(Path(image["resolved_path"]))
    transition = (
        "python-org-framework-launcher-to-app-image"
        if launcher["resolved_path"] != image["resolved_path"]
        else "launcher-is-process-image"
    )
    return _PreparedRuntimeProcessImageBinding(
        machine=platform.machine(),
        provider_path=Path(provider["resolved_path"]),
        runtime_launcher_path=Path(launcher["resolved_path"]),
        process_image_path=Path(image["resolved_path"]),
        provider_identity=provider,
        runtime_launcher_identity=launcher,
        process_image_identity=image,
        provider_cdhash=provider_signature["cdhash"],
        runtime_launcher_cdhash=launcher_signature["cdhash"],
        process_image_cdhash=image_signature["cdhash"],
        transition=transition,
    )


def _observe_prepared_runtime_process_image(
    pid: int,
    *,
    prepared: _PreparedRuntimeProcessImageBinding,
) -> Mapping[str, str]:
    """Bind a prepared static identity to one exact live child PID."""

    if type(prepared) is not _PreparedRuntimeProcessImageBinding:
        raise ValueError("macOS runtime process-image preparation differs")
    return _observe_process_image(
        pid,
        provider_path=prepared.provider_path,
        runtime_launcher_path=prepared.runtime_launcher_path,
        expected_image_path=prepared.process_image_path,
        expected_cdhash=prepared.process_image_cdhash,
    )


def _complete_runtime_process_image_binding(
    *,
    prepared: _PreparedRuntimeProcessImageBinding,
    observed: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Remeasure inputs and seal one path-free exact-child binding."""

    if type(prepared) is not _PreparedRuntimeProcessImageBinding:
        raise ValueError("macOS runtime process-image preparation differs")
    if observed != {
        "kernel_cdhash": prepared.process_image_cdhash,
        "path_state": "matched_expected_process_image",
    }:
        raise ValueError("macOS runtime process-image live observation differs")
    for before, path, label in (
        (prepared.provider_identity, prepared.provider_path, "provider"),
        (
            prepared.runtime_launcher_identity,
            prepared.runtime_launcher_path,
            "runtime launcher",
        ),
        (
            prepared.process_image_identity,
            prepared.process_image_path,
            "runtime process image",
        ),
    ):
        after = _regular_file_identity(path)
        if _identity_projection(before) != _identity_projection(after):
            raise RuntimeError(f"macOS {label} changed during observation")
    payload = {
        "schema": BINDING_SCHEMA,
        "policy_id": BINDING_POLICY_ID,
        "status": "runtime_process_image_bound_to_exact_child_pid",
        "platform": {"system": "Darwin", "machine": prepared.machine},
        "provider": {
            **_path_free_identity(prepared.provider_identity),
            "static_cdhash": prepared.provider_cdhash,
            "strict_code_signature_valid": True,
            "filesystem_read_only": True,
        },
        "runtime": {
            "launcher": {
                **_path_free_identity(prepared.runtime_launcher_identity),
                "static_cdhash": prepared.runtime_launcher_cdhash,
                "strict_code_signature_valid": True,
            },
            "process_image": {
                **_path_free_identity(prepared.process_image_identity),
                "static_cdhash": prepared.process_image_cdhash,
                "observed_kernel_cdhash": observed["kernel_cdhash"],
                "strict_code_signature_valid": True,
                "static_and_kernel_cdhash_match": True,
            },
            "transition": prepared.transition,
        },
        "observation": {
            "exact_child_pid_observed": True,
            "child_pid_retained": False,
            "parent_proc_pidpath_used": True,
            "parent_csops_cdhash_used": True,
            "process_image_path_matched_expected": True,
            "artifacts_unchanged_after_child": True,
        },
        "conclusion": {
            "provider_path_mutation_confined_by_read_only_filesystem": True,
            "runtime_process_code_identity_bound_to_exact_child_pid": True,
            "runtime_launcher_transition_explicit": True,
        },
        "limitations": {
            "provider_runtime_complete_byte_identity_toctou_closed": False,
            "dynamic_native_library_closure_bound": False,
            "post_observation_image_mutability_excluded": False,
            "code_signature_identity_is_not_full_file_sha256": True,
        },
    }
    document = {
        **payload,
        "evidence_sha256": hashlib.sha256(_canonical_json_bytes(payload)).hexdigest(),
    }
    return _validate_runtime_process_image_binding(document)


def _run_private_macos_runtime_process_image_canary(
    *, runtime_path: str | Path
) -> Mapping[str, Any]:
    """Observe one inert runtime process from its exact parent PID."""

    prepared = _prepare_runtime_process_image_binding(runtime_path=runtime_path)

    command = [
        str(prepared.provider_path),
        "-p",
        _SANDBOX_PROFILE,
        str(prepared.runtime_launcher_path),
        "-I",
        "-S",
        "-c",
        _CHILD_SOURCE,
    ]
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd="/",
        env=_ENVIRONMENT,
    )
    try:
        observed_image = _observe_prepared_runtime_process_image(
            process.pid,
            prepared=prepared,
        )
        stdout, stderr = process.communicate(timeout=3.0)
    except BaseException:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=3.0)
        raise

    if (
        process.returncode != 0
        or stderr
        or not 1 <= len(stdout) <= _MAXIMUM_OUTPUT_BYTES
    ):
        raise RuntimeError(
            "macOS runtime process-image child did not complete cleanly: "
            f"exit={process.returncode}; stderr_bytes={len(stderr)}; "
            f"stderr_sha256={hashlib.sha256(stderr).hexdigest()}"
        )
    try:
        child = json.loads(stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "macOS runtime process-image child returned invalid JSON"
        ) from error
    if child != {"arithmetic": 42, "probe_id": PROBE_ID}:
        raise RuntimeError("macOS runtime process-image child result differs")
    binding = _complete_runtime_process_image_binding(
        prepared=prepared,
        observed=observed_image,
    )
    payload = {
        "schema": SCHEMA,
        "policy_id": POLICY_ID,
        "status": "runtime_process_image_parent_observed",
        "platform": {
            "system": "Darwin",
            "machine": platform.machine(),
        },
        "provider": {
            **_plain(binding["provider"]),
        },
        "runtime": {
            **_plain(binding["runtime"]),
        },
        "observation": {
            "probe_id": PROBE_ID,
            "exact_child_pid_observed": True,
            "child_pid_retained": False,
            "parent_proc_pidpath_used": True,
            "parent_csops_cdhash_used": True,
            "process_image_path_matched_expected": True,
            "artifacts_unchanged_after_child": True,
            "network_attempted": False,
            "filesystem_written": False,
        },
        "conclusion": {
            "provider_path_mutation_confined_by_read_only_filesystem": True,
            "runtime_process_code_identity_bound_to_exact_child_pid": True,
            "runtime_launcher_transition_explicit": True,
            "bound_to_model_worker": False,
            "separator_enabled": False,
        },
        "permissions": {
            "model_import_permitted": False,
            "checkpoint_access_permitted": False,
            "authorised_audio_access_permitted": False,
            "separator_execution_permitted": False,
            "source_graph_activation_permitted": False,
            "product_route_permitted": False,
            "publication_permitted": False,
        },
        "effects": {
            "process_started": True,
            "filesystem_written": False,
            "network_used": False,
            "checkpoint_opened": False,
            "model_imported": False,
            "audio_read": False,
            "source_graph_changed": False,
        },
        "limitations": {
            "model_free_canary_only": True,
            "authorised_worker_not_bound": True,
            "provider_runtime_complete_byte_identity_toctou_closed": False,
            "dynamic_native_library_closure_bound": False,
            "post_observation_image_mutability_excluded": False,
            "code_signature_identity_is_not_full_file_sha256": True,
        },
    }
    document = {
        **payload,
        "evidence_sha256": hashlib.sha256(_canonical_json_bytes(payload)).hexdigest(),
    }
    return _validate_private_macos_runtime_process_image(document)


def _observe_process_image(
    pid: int,
    *,
    provider_path: Path,
    runtime_launcher_path: Path,
    expected_image_path: Path,
    expected_cdhash: str,
) -> Mapping[str, str]:
    """Wait for the provider-to-runtime exec and bind its kernel CDHash."""

    if type(pid) is not int or pid <= 0:
        raise ValueError("macOS runtime process-image PID is invalid")
    expected = expected_image_path.resolve(strict=True)
    provider = provider_path.resolve(strict=True)
    launcher = runtime_launcher_path.resolve(strict=True)
    deadline = time.monotonic() + _OBSERVATION_TIMEOUT_SECONDS
    last_path: Path | None = None
    while time.monotonic() < deadline:
        try:
            current = _proc_pidpath(pid).resolve(strict=True)
        except (FileNotFoundError, ProcessLookupError):
            time.sleep(_POLL_SECONDS)
            continue
        last_path = current
        if current in {provider, launcher} and current != expected:
            time.sleep(_POLL_SECONDS)
            continue
        if current != expected:
            raise RuntimeError("macOS runtime process image path differs")
        kernel_cdhash = _pid_cdhash(pid)
        if kernel_cdhash != expected_cdhash:
            raise RuntimeError("macOS runtime process image CDHash differs")
        return {
            "kernel_cdhash": kernel_cdhash,
            "path_state": "matched_expected_process_image",
        }
    suffix = "absent" if last_path is None else "provider_did_not_exec_runtime"
    raise RuntimeError(f"macOS runtime process image observation timed out: {suffix}")


def _expected_python_process_image(runtime_path: Path) -> Path:
    """Resolve the known python.org framework launcher transition."""

    runtime = runtime_path.expanduser().resolve(strict=True)
    if runtime.parent.name == "bin":
        candidate = (
            runtime.parent.parent
            / "Resources"
            / "Python.app"
            / "Contents"
            / "MacOS"
            / "Python"
        )
        if candidate.exists():
            return candidate.resolve(strict=True)
    return runtime


def _proc_pidpath(pid: int) -> Path:
    library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    function = library.proc_pidpath
    function.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    function.restype = ctypes.c_int
    buffer = ctypes.create_string_buffer(_MAXIMUM_PATH_BYTES)
    result = function(pid, buffer, len(buffer))
    if result <= 0:
        error = ctypes.get_errno()
        if error in {3, 22}:
            raise ProcessLookupError(pid)
        raise OSError(error, "proc_pidpath failed")
    raw = bytes(buffer.value)
    if not raw or len(raw) >= _MAXIMUM_PATH_BYTES or b"\x00" in raw:
        raise RuntimeError("macOS process image path is invalid")
    try:
        return Path(raw.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise RuntimeError("macOS process image path is not UTF-8") from error


def _pid_cdhash(pid: int) -> str:
    # CS_OPS_CDHASH is the stable public csops operation used by macOS's
    # Security framework to obtain the kernel code-directory identity.
    library = ctypes.CDLL(None, use_errno=True)
    function = library.csops
    function.argtypes = [ctypes.c_int, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_size_t]
    function.restype = ctypes.c_int
    output = (ctypes.c_ubyte * 20)()
    if function(pid, 5, ctypes.byref(output), len(output)) != 0:
        error = ctypes.get_errno()
        if error in {3, 22}:
            raise ProcessLookupError(pid)
        raise OSError(error, "csops CDHash query failed")
    value = bytes(output).hex()
    if not _CDHASH_RE.fullmatch(value):
        raise RuntimeError("macOS process CDHash is invalid")
    return value


def _static_code_identity(path: Path) -> Mapping[str, str]:
    """Strictly validate one static Mach-O and return its preferred CDHash."""

    encoded = os.fsencode(path.resolve(strict=True))
    if not encoded or len(encoded) >= _MAXIMUM_PATH_BYTES or b"\x00" in encoded:
        raise ValueError("macOS static-code path is invalid")
    security = ctypes.CDLL(
        "/System/Library/Frameworks/Security.framework/Security"
    )
    core = ctypes.CDLL(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )
    _configure_security_functions(security, core)
    raw_path = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
    url = core.CFURLCreateFromFileSystemRepresentation(
        None, raw_path, len(encoded), False
    )
    if not url:
        raise RuntimeError("macOS static-code URL creation failed")
    code = ctypes.c_void_p()
    information = ctypes.c_void_p()
    try:
        if security.SecStaticCodeCreateWithPath(url, 0, ctypes.byref(code)) != 0:
            raise RuntimeError("macOS static-code creation failed")
        # Check every architecture and apply strict validation.
        if security.SecStaticCodeCheckValidity(code, 17, None) != 0:
            raise RuntimeError("macOS static-code strict validation failed")
        if (
            security.SecCodeCopySigningInformation(
                code, 2, ctypes.byref(information)
            )
            != 0
        ):
            raise RuntimeError("macOS signing-information query failed")
        key = ctypes.c_void_p.in_dll(security, "kSecCodeInfoUnique")
        value = core.CFDictionaryGetValue(information, key)
        if not value:
            raise RuntimeError("macOS static code has no CDHash")
        length = core.CFDataGetLength(value)
        pointer = core.CFDataGetBytePtr(value)
        if length != 20 or not pointer:
            raise RuntimeError("macOS static code CDHash length differs")
        cdhash = bytes(pointer[index] for index in range(length)).hex()
        if not _CDHASH_RE.fullmatch(cdhash):
            raise RuntimeError("macOS static code CDHash is invalid")
        return {"cdhash": cdhash}
    finally:
        if information.value:
            core.CFRelease(information)
        if code.value:
            core.CFRelease(code)
        core.CFRelease(url)


def _configure_security_functions(security: Any, core: Any) -> None:
    core.CFURLCreateFromFileSystemRepresentation.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_long,
        ctypes.c_bool,
    ]
    core.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
    core.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    core.CFDictionaryGetValue.restype = ctypes.c_void_p
    core.CFDataGetLength.argtypes = [ctypes.c_void_p]
    core.CFDataGetLength.restype = ctypes.c_long
    core.CFDataGetBytePtr.argtypes = [ctypes.c_void_p]
    core.CFDataGetBytePtr.restype = ctypes.POINTER(ctypes.c_ubyte)
    core.CFRelease.argtypes = [ctypes.c_void_p]
    core.CFRelease.restype = None
    security.SecStaticCodeCreateWithPath.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    security.SecStaticCodeCreateWithPath.restype = ctypes.c_int32
    security.SecStaticCodeCheckValidity.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    security.SecStaticCodeCheckValidity.restype = ctypes.c_int32
    security.SecCodeCopySigningInformation.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    security.SecCodeCopySigningInformation.restype = ctypes.c_int32


def _filesystem_is_read_only(path: Path) -> bool:
    return bool(os.statvfs(path).f_flag & os.ST_RDONLY)


def _validate_runtime_process_image_binding(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = _plain(document)
    required = {
        "schema",
        "policy_id",
        "status",
        "platform",
        "provider",
        "runtime",
        "observation",
        "conclusion",
        "limitations",
        "evidence_sha256",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("macOS runtime process-image binding fields differ")
    digest = value.pop("evidence_sha256")
    if not _is_sha(digest) or digest != hashlib.sha256(
        _canonical_json_bytes(value)
    ).hexdigest():
        raise ValueError("macOS runtime process-image binding self-hash differs")
    if (
        value["schema"] != BINDING_SCHEMA
        or value["policy_id"] != BINDING_POLICY_ID
        or value["status"] != "runtime_process_image_bound_to_exact_child_pid"
        or value["platform"].get("system") != "Darwin"
        or not isinstance(value["platform"].get("machine"), str)
        or not value["platform"]["machine"]
    ):
        raise ValueError("macOS runtime process-image binding identity differs")
    _validate_artifact(value["provider"], provider=True)
    runtime = value["runtime"]
    if not isinstance(runtime, dict) or set(runtime) != {
        "launcher",
        "process_image",
        "transition",
    }:
        raise ValueError("macOS runtime process-image binding runtime differs")
    _validate_artifact(runtime["launcher"], provider=False)
    _validate_process_image(runtime["process_image"])
    if runtime["transition"] not in {
        "python-org-framework-launcher-to-app-image",
        "launcher-is-process-image",
    }:
        raise ValueError("macOS runtime process-image binding transition differs")
    if value["observation"] != {
        "exact_child_pid_observed": True,
        "child_pid_retained": False,
        "parent_proc_pidpath_used": True,
        "parent_csops_cdhash_used": True,
        "process_image_path_matched_expected": True,
        "artifacts_unchanged_after_child": True,
    }:
        raise ValueError("macOS runtime process-image binding observation differs")
    if value["conclusion"] != {
        "provider_path_mutation_confined_by_read_only_filesystem": True,
        "runtime_process_code_identity_bound_to_exact_child_pid": True,
        "runtime_launcher_transition_explicit": True,
    }:
        raise ValueError("macOS runtime process-image binding conclusion differs")
    if value["limitations"] != {
        "provider_runtime_complete_byte_identity_toctou_closed": False,
        "dynamic_native_library_closure_bound": False,
        "post_observation_image_mutability_excluded": False,
        "code_signature_identity_is_not_full_file_sha256": True,
    }:
        raise ValueError("macOS runtime process-image binding limitations differ")
    checked = {**value, "evidence_sha256": digest}
    encoded = json.dumps(checked, sort_keys=True, separators=(",", ":"))
    if "/Users/" in encoded or "file://" in encoded or "://" in encoded:
        raise ValueError("macOS runtime process-image binding is not path-free")
    return _freeze_json(checked)


def _validate_private_macos_runtime_process_image(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = _plain(document)
    required = {
        "schema",
        "policy_id",
        "status",
        "platform",
        "provider",
        "runtime",
        "observation",
        "conclusion",
        "permissions",
        "effects",
        "limitations",
        "evidence_sha256",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("macOS runtime process-image evidence fields differ")
    digest = value.pop("evidence_sha256")
    if not _is_sha(digest) or digest != hashlib.sha256(
        _canonical_json_bytes(value)
    ).hexdigest():
        raise ValueError("macOS runtime process-image self-hash differs")
    if (
        value["schema"] != SCHEMA
        or value["policy_id"] != POLICY_ID
        or value["status"] != "runtime_process_image_parent_observed"
        or value["platform"].get("system") != "Darwin"
        or not isinstance(value["platform"].get("machine"), str)
        or not value["platform"]["machine"]
    ):
        raise ValueError("macOS runtime process-image identity differs")
    _validate_artifact(value["provider"], provider=True)
    runtime = value["runtime"]
    if not isinstance(runtime, dict) or set(runtime) != {
        "launcher",
        "process_image",
        "transition",
    }:
        raise ValueError("macOS runtime process-image runtime fields differ")
    _validate_artifact(runtime["launcher"], provider=False)
    _validate_process_image(runtime["process_image"])
    if runtime["transition"] not in {
        "python-org-framework-launcher-to-app-image",
        "launcher-is-process-image",
    }:
        raise ValueError("macOS runtime process-image transition differs")
    if value["observation"] != {
        "probe_id": PROBE_ID,
        "exact_child_pid_observed": True,
        "child_pid_retained": False,
        "parent_proc_pidpath_used": True,
        "parent_csops_cdhash_used": True,
        "process_image_path_matched_expected": True,
        "artifacts_unchanged_after_child": True,
        "network_attempted": False,
        "filesystem_written": False,
    }:
        raise ValueError("macOS runtime process-image observation differs")
    if value["conclusion"] != {
        "provider_path_mutation_confined_by_read_only_filesystem": True,
        "runtime_process_code_identity_bound_to_exact_child_pid": True,
        "runtime_launcher_transition_explicit": True,
        "bound_to_model_worker": False,
        "separator_enabled": False,
    }:
        raise ValueError("macOS runtime process-image conclusion differs")
    if any(value["permissions"].values()):
        raise ValueError("macOS runtime process-image evidence grants a permission")
    if value["permissions"] != {
        "model_import_permitted": False,
        "checkpoint_access_permitted": False,
        "authorised_audio_access_permitted": False,
        "separator_execution_permitted": False,
        "source_graph_activation_permitted": False,
        "product_route_permitted": False,
        "publication_permitted": False,
    }:
        raise ValueError("macOS runtime process-image permissions differ")
    if value["effects"] != {
        "process_started": True,
        "filesystem_written": False,
        "network_used": False,
        "checkpoint_opened": False,
        "model_imported": False,
        "audio_read": False,
        "source_graph_changed": False,
    }:
        raise ValueError("macOS runtime process-image effects differ")
    if value["limitations"] != {
        "model_free_canary_only": True,
        "authorised_worker_not_bound": True,
        "provider_runtime_complete_byte_identity_toctou_closed": False,
        "dynamic_native_library_closure_bound": False,
        "post_observation_image_mutability_excluded": False,
        "code_signature_identity_is_not_full_file_sha256": True,
    }:
        raise ValueError("macOS runtime process-image limitations differ")
    checked = {**value, "evidence_sha256": digest}
    encoded = json.dumps(checked, sort_keys=True, separators=(",", ":"))
    if "/Users/" in encoded or "file://" in encoded or "://" in encoded:
        raise ValueError("macOS runtime process-image evidence is not path-free")
    return _freeze_json(checked)


def _validate_artifact(value: Any, *, provider: bool) -> None:
    fields = {
        "bytes",
        "sha256",
        "static_cdhash",
        "strict_code_signature_valid",
    }
    if provider:
        fields.add("filesystem_read_only")
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("macOS runtime process-image artifact fields differ")
    if (
        type(value["bytes"]) is not int
        or value["bytes"] <= 0
        or not _is_sha(value["sha256"])
        or not _CDHASH_RE.fullmatch(value["static_cdhash"])
        or value["strict_code_signature_valid"] is not True
        or (provider and value["filesystem_read_only"] is not True)
    ):
        raise ValueError("macOS runtime process-image artifact identity differs")


def _validate_process_image(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {
        "bytes",
        "sha256",
        "static_cdhash",
        "observed_kernel_cdhash",
        "strict_code_signature_valid",
        "static_and_kernel_cdhash_match",
    }:
        raise ValueError("macOS runtime process-image fields differ")
    _validate_artifact(
        {
            key: value[key]
            for key in (
                "bytes",
                "sha256",
                "static_cdhash",
                "strict_code_signature_valid",
            )
        },
        provider=False,
    )
    if (
        value["observed_kernel_cdhash"] != value["static_cdhash"]
        or value["static_and_kernel_cdhash_match"] is not True
    ):
        raise ValueError("macOS runtime process-image kernel identity differs")


def _path_free_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    return {"bytes": value["bytes"], "sha256": value["sha256"]}


def _identity_projection(value: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        value["resolved_path"],
        value["bytes"],
        value["sha256"],
    )


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA_RE.fullmatch(value))


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


__all__ = ()
