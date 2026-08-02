"""Private model-free inventory of one macOS child's executable mappings.

The process-image observer binds the main signed image, but Python can also
load native extension modules and framework binaries outside ``sys.modules``
file accounting.  This module asks macOS ``libproc`` for the file-backed,
executable VM regions of one exact inert child, requires two stable snapshots,
and hashes every reported file before and after the child exits.

This is deliberately not a complete dyld audit.  In particular, macOS dyld
shared-cache constituents are not enumerated by this contract, transient
loads between snapshots are not excluded, and reopening a mapped file does not
prove that its current bytes are the bytes in memory.  The canary loads no
model or checkpoint, reads no audio, writes no output and enables no product
route.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import re
import selectors
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ._separation_macos_process_image import (
    _complete_runtime_process_image_binding,
    _observe_prepared_runtime_process_image,
    _prepare_runtime_process_image_binding,
    _static_code_identity,
    _validate_runtime_process_image_binding,
)
from ._separation_macos_sandbox_probe import _regular_file_identity
from .separation_contract import _canonical_json_bytes, _freeze_json


SCHEMA = "sunofriend.private-macos-native-image-inventory.v1"
POLICY_ID = "private-macos-native-image-inventory-v1"
PROBE_ID = "parent-libproc-executable-region-inventory-v1"
_SANDBOX_PROFILE = "(version 1)\n(allow default)\n(deny network*)\n"
_NATIVE_MODULES = (
    "_bz2",
    "_ctypes",
    "_hashlib",
    "_lzma",
    "_sqlite3",
    "_ssl",
    "zlib",
)
_CHILD_SOURCE = (
    "import _bz2,_ctypes,_hashlib,_lzma,_sqlite3,_ssl,zlib,json,time; "
    "print(json.dumps({'native_modules':"
    + repr(list(_NATIVE_MODULES))
    + ",'probe_id':'"
    + PROBE_ID
    + "'},sort_keys=True,separators=(',',':')),flush=True); time.sleep(2.0)"
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
_PROC_PIDREGIONPATHINFO = 8
_VM_PROT_EXECUTE = 0x04
_MAXPATHLEN = 1024
_MAXIMUM_REGIONS = 4096
_MAXIMUM_MAPPED_FILES = 512
_MAXIMUM_READY_BYTES = 16 * 1024
_READY_TIMEOUT_SECONDS = 3.0
_SNAPSHOT_SETTLE_SECONDS = 0.02
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_CDHASH_RE = re.compile(r"^[0-9a-f]{40}$")


class _ProcRegionInfo(ctypes.Structure):
    _fields_ = [
        ("pri_protection", ctypes.c_uint32),
        ("pri_max_protection", ctypes.c_uint32),
        ("pri_inheritance", ctypes.c_uint32),
        ("pri_flags", ctypes.c_uint32),
        ("pri_offset", ctypes.c_uint64),
        ("pri_behavior", ctypes.c_uint32),
        ("pri_user_wired_count", ctypes.c_uint32),
        ("pri_user_tag", ctypes.c_uint32),
        ("pri_pages_resident", ctypes.c_uint32),
        ("pri_pages_shared_now_private", ctypes.c_uint32),
        ("pri_pages_swapped_out", ctypes.c_uint32),
        ("pri_pages_dirtied", ctypes.c_uint32),
        ("pri_ref_count", ctypes.c_uint32),
        ("pri_shadow_depth", ctypes.c_uint32),
        ("pri_share_mode", ctypes.c_uint32),
        ("pri_private_pages_resident", ctypes.c_uint32),
        ("pri_shared_pages_resident", ctypes.c_uint32),
        ("pri_obj_id", ctypes.c_uint32),
        ("pri_depth", ctypes.c_uint32),
        ("pri_address", ctypes.c_uint64),
        ("pri_size", ctypes.c_uint64),
    ]


class _VinfoStat(ctypes.Structure):
    _fields_ = [
        ("vst_dev", ctypes.c_uint32),
        ("vst_mode", ctypes.c_uint16),
        ("vst_nlink", ctypes.c_uint16),
        ("vst_ino", ctypes.c_uint64),
        ("vst_uid", ctypes.c_uint32),
        ("vst_gid", ctypes.c_uint32),
        ("vst_atime", ctypes.c_int64),
        ("vst_atimensec", ctypes.c_int64),
        ("vst_mtime", ctypes.c_int64),
        ("vst_mtimensec", ctypes.c_int64),
        ("vst_ctime", ctypes.c_int64),
        ("vst_ctimensec", ctypes.c_int64),
        ("vst_birthtime", ctypes.c_int64),
        ("vst_birthtimensec", ctypes.c_int64),
        ("vst_size", ctypes.c_int64),
        ("vst_blocks", ctypes.c_int64),
        ("vst_blksize", ctypes.c_int32),
        ("vst_flags", ctypes.c_uint32),
        ("vst_gen", ctypes.c_uint32),
        ("vst_rdev", ctypes.c_uint32),
        ("vst_qspare", ctypes.c_int64 * 2),
    ]


class _Fsid(ctypes.Structure):
    _fields_ = [("val", ctypes.c_int32 * 2)]


class _VnodeInfo(ctypes.Structure):
    _fields_ = [
        ("vi_stat", _VinfoStat),
        ("vi_type", ctypes.c_int),
        ("vi_pad", ctypes.c_int),
        ("vi_fsid", _Fsid),
    ]


class _VnodeInfoPath(ctypes.Structure):
    _fields_ = [
        ("vip_vi", _VnodeInfo),
        ("vip_path", ctypes.c_char * _MAXPATHLEN),
    ]


class _ProcRegionWithPathInfo(ctypes.Structure):
    _fields_ = [
        ("prp_prinfo", _ProcRegionInfo),
        ("prp_vip", _VnodeInfoPath),
    ]


@dataclass(frozen=True)
class _ExecutableRegion:
    path: Path | None
    address: int
    size: int
    offset: int
    protection: int


def _run_private_macos_native_image_inventory_canary(
    *, runtime_path: str | Path
) -> Mapping[str, Any]:
    """Inventory stable executable mappings in one inert exact child."""

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
        ready = _read_child_ready(process)
        first = _enumerate_executable_regions(process.pid)
        time.sleep(_SNAPSHOT_SETTLE_SECONDS)
        second = _enumerate_executable_regions(process.pid)
        if _snapshot_key(first) != _snapshot_key(second):
            raise RuntimeError("macOS executable-region snapshots did not stabilise")
        measured = _measure_mapped_files(
            second,
            process_image_path=prepared.process_image_path,
        )
        remaining_stdout, stderr = process.communicate(timeout=3.0)
    except BaseException:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=3.0)
        raise

    if process.returncode != 0 or remaining_stdout or stderr:
        raise RuntimeError(
            "macOS native-image child did not complete cleanly: "
            f"exit={process.returncode}; stdout_bytes={len(remaining_stdout)}; "
            f"stderr_bytes={len(stderr)}; "
            f"stderr_sha256={hashlib.sha256(stderr).hexdigest()}"
        )
    if ready != {
        "native_modules": list(_NATIVE_MODULES),
        "probe_id": PROBE_ID,
    }:
        raise RuntimeError("macOS native-image child readiness differs")
    _remeasure_mapped_files(measured)
    process_binding = _complete_runtime_process_image_binding(
        prepared=prepared,
        observed=observed_image,
    )
    artifacts = _path_free_artifacts(measured)
    file_backed_regions = [region for region in second if region.path is not None]
    unpathed_regions = [region for region in second if region.path is None]
    payload = {
        "schema": SCHEMA,
        "policy_id": POLICY_ID,
        "status": "stable_file_backed_executable_region_inventory_observed",
        "platform": {"system": "Darwin", "machine": platform.machine()},
        "process_image_binding": _plain(process_binding),
        "probe": {
            "probe_id": PROBE_ID,
            "native_module_count": len(_NATIVE_MODULES),
            "ready_received_before_inventory": True,
            "child_reported_inventory": False,
        },
        "inventory": {
            "source": "libproc-proc-pidregionpathinfo",
            "snapshot_count": 2,
            "stable_consecutive_snapshots": True,
            "executable_region_count": len(second),
            "file_backed_executable_region_count": len(file_backed_regions),
            "unpathed_executable_region_count": len(unpathed_regions),
            "mapped_file_count": len(measured),
            "artifacts": artifacts,
            "artifacts_unchanged_after_child": True,
            "paths_retained": False,
        },
        "conclusion": {
            "exact_child_pid_observed": True,
            "parent_owned_inventory": True,
            "stable_file_backed_executable_regions_bound": True,
            "main_process_image_present_once": True,
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
            "dyld_shared_cache_constituents_enumerated": False,
            "transient_loads_between_snapshots_excluded": False,
            "mapped_memory_bytes_equal_reopened_file_bytes_proven": False,
            "dynamic_native_library_closure_bound": False,
            "post_observation_image_mutability_excluded": False,
        },
    }
    document = {
        **payload,
        "evidence_sha256": hashlib.sha256(_canonical_json_bytes(payload)).hexdigest(),
    }
    return _validate_private_macos_native_image_inventory(document)


def _read_child_ready(process: subprocess.Popen[bytes]) -> Mapping[str, Any]:
    if process.stdout is None:
        raise RuntimeError("macOS native-image child stdout is unavailable")
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + _READY_TIMEOUT_SECONDS
    received = bytearray()
    try:
        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            if not selector.select(remaining):
                break
            block = os.read(process.stdout.fileno(), _MAXIMUM_READY_BYTES + 1)
            if not block:
                break
            received.extend(block)
            if len(received) > _MAXIMUM_READY_BYTES:
                raise RuntimeError("macOS native-image child readiness is too large")
            if b"\n" in received:
                break
    finally:
        selector.close()
    if not received.endswith(b"\n") or received.count(b"\n") != 1:
        raise RuntimeError("macOS native-image child readiness is incomplete")
    try:
        value = json.loads(received)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("macOS native-image child readiness is invalid") from error
    if not isinstance(value, dict):
        raise RuntimeError("macOS native-image child readiness fields differ")
    return value


def _enumerate_executable_regions(pid: int) -> tuple[_ExecutableRegion, ...]:
    """Return a bounded parent-side snapshot of executable VM regions."""

    if platform.system() != "Darwin":
        raise RuntimeError("macOS executable-region inventory requires Darwin")
    if type(pid) is not int or pid <= 0:
        raise ValueError("macOS executable-region PID is invalid")
    if (
        ctypes.sizeof(_ProcRegionInfo) != 96
        or ctypes.sizeof(_ProcRegionWithPathInfo) != 1272
        or _ProcRegionWithPathInfo.prp_vip.offset + _VnodeInfoPath.vip_path.offset
        != 248
    ):
        raise RuntimeError("macOS executable-region structure layout differs")
    library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    function = library.proc_pidinfo
    function.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint64,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    function.restype = ctypes.c_int
    address = 0
    regions: list[_ExecutableRegion] = []
    for _ in range(_MAXIMUM_REGIONS):
        output = _ProcRegionWithPathInfo()
        ctypes.set_errno(0)
        result = function(
            pid,
            _PROC_PIDREGIONPATHINFO,
            address,
            ctypes.byref(output),
            ctypes.sizeof(output),
        )
        if result <= 0:
            error = ctypes.get_errno()
            if error in {0, 22}:
                break
            if error == 3:
                raise ProcessLookupError(pid)
            raise OSError(error, "proc_pidinfo region-path query failed")
        if result != ctypes.sizeof(output):
            raise RuntimeError("macOS executable-region result size differs")
        region = output.prp_prinfo
        next_address = int(region.pri_address + region.pri_size)
        if region.pri_size <= 0 or next_address <= address:
            raise RuntimeError("macOS executable-region traversal did not advance")
        address = next_address
        if not (region.pri_protection & _VM_PROT_EXECUTE):
            continue
        raw_path = bytes(output.prp_vip.vip_path).split(b"\x00", 1)[0]
        path: Path | None = None
        if raw_path:
            try:
                path = Path(raw_path.decode("utf-8")).resolve(strict=True)
            except UnicodeDecodeError as error:
                raise RuntimeError(
                    "macOS executable-region path is not UTF-8"
                ) from error
        regions.append(
            _ExecutableRegion(
                path=path,
                address=int(region.pri_address),
                size=int(region.pri_size),
                offset=int(region.pri_offset),
                protection=int(region.pri_protection),
            )
        )
    else:
        raise RuntimeError("macOS executable-region count exceeds the bound")
    if not regions:
        raise RuntimeError("macOS executable-region inventory is empty")
    return tuple(regions)


def _snapshot_key(regions: Sequence[_ExecutableRegion]) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        (
            None if region.path is None else str(region.path),
            region.address,
            region.size,
            region.offset,
            region.protection,
        )
        for region in regions
    )


def _measure_mapped_files(
    regions: Sequence[_ExecutableRegion],
    *,
    process_image_path: Path,
) -> tuple[dict[str, Any], ...]:
    paths = sorted({region.path for region in regions if region.path is not None})
    if not 1 <= len(paths) <= _MAXIMUM_MAPPED_FILES:
        raise RuntimeError("macOS mapped executable-file count is outside bounds")
    expected = process_image_path.resolve(strict=True)
    measured: list[dict[str, Any]] = []
    for path in paths:
        identity = _regular_file_identity(path)
        mapped = [region for region in regions if region.path == path]
        try:
            signature = _static_code_identity(path)
        except RuntimeError:
            signature_status = "not_strictly_valid"
            cdhash = None
        else:
            signature_status = "strictly_valid"
            cdhash = signature["cdhash"]
        measured.append(
            {
                "path": path,
                "identity": identity,
                "executable_region_count": len(mapped),
                "executable_region_bytes": sum(region.size for region in mapped),
                "signature_status": signature_status,
                "static_cdhash": cdhash,
                "matches_process_image": path == expected,
            }
        )
    if sum(item["matches_process_image"] for item in measured) != 1:
        raise RuntimeError("macOS process image is not present exactly once")
    return tuple(measured)


def _remeasure_mapped_files(measured: Sequence[Mapping[str, Any]]) -> None:
    for item in measured:
        after = _regular_file_identity(item["path"])
        before = item["identity"]
        if (
            before["resolved_path"],
            before["bytes"],
            before["sha256"],
        ) != (
            after["resolved_path"],
            after["bytes"],
            after["sha256"],
        ):
            raise RuntimeError("macOS mapped executable file changed after child")


def _path_free_artifacts(
    measured: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    artifacts = []
    for index, item in enumerate(measured, start=1):
        artifacts.append(
            {
                "artifact_index": index,
                "bytes": item["identity"]["bytes"],
                "sha256": item["identity"]["sha256"],
                "executable_region_count": item["executable_region_count"],
                "executable_region_bytes": item["executable_region_bytes"],
                "static_code_status": item["signature_status"],
                "static_cdhash": item["static_cdhash"],
                "matches_process_image": item["matches_process_image"],
            }
        )
    return artifacts


def _validate_private_macos_native_image_inventory(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = _plain(document)
    required = {
        "schema",
        "policy_id",
        "status",
        "platform",
        "process_image_binding",
        "probe",
        "inventory",
        "conclusion",
        "permissions",
        "effects",
        "limitations",
        "evidence_sha256",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("macOS native-image inventory fields differ")
    digest = value.pop("evidence_sha256")
    if not _is_sha(digest) or digest != hashlib.sha256(
        _canonical_json_bytes(value)
    ).hexdigest():
        raise ValueError("macOS native-image inventory self-hash differs")
    if (
        value["schema"] != SCHEMA
        or value["policy_id"] != POLICY_ID
        or value["status"]
        != "stable_file_backed_executable_region_inventory_observed"
        or value["platform"].get("system") != "Darwin"
        or not isinstance(value["platform"].get("machine"), str)
        or not value["platform"]["machine"]
    ):
        raise ValueError("macOS native-image inventory identity differs")
    binding = _plain(
        _validate_runtime_process_image_binding(value["process_image_binding"])
    )
    if (
        binding.get("status") != "runtime_process_image_bound_to_exact_child_pid"
        or binding.get("platform", {}).get("machine")
        != value["platform"]["machine"]
        or binding.get("conclusion", {}).get(
            "runtime_process_code_identity_bound_to_exact_child_pid"
        )
        is not True
    ):
        raise ValueError("macOS native-image process binding differs")
    probe = value["probe"]
    if probe != {
        "probe_id": PROBE_ID,
        "native_module_count": len(_NATIVE_MODULES),
        "ready_received_before_inventory": True,
        "child_reported_inventory": False,
    }:
        raise ValueError("macOS native-image probe differs")
    inventory = value["inventory"]
    if not isinstance(inventory, dict) or set(inventory) != {
        "source",
        "snapshot_count",
        "stable_consecutive_snapshots",
        "executable_region_count",
        "file_backed_executable_region_count",
        "unpathed_executable_region_count",
        "mapped_file_count",
        "artifacts",
        "artifacts_unchanged_after_child",
        "paths_retained",
    }:
        raise ValueError("macOS native-image inventory payload differs")
    artifacts = inventory["artifacts"]
    if not isinstance(artifacts, list) or not 1 <= len(artifacts) <= 512:
        raise ValueError("macOS native-image artifact count differs")
    for index, artifact in enumerate(artifacts, start=1):
        _validate_artifact(artifact, index=index)
    if (
        inventory["source"] != "libproc-proc-pidregionpathinfo"
        or inventory["snapshot_count"] != 2
        or inventory["stable_consecutive_snapshots"] is not True
        or type(inventory["executable_region_count"]) is not int
        or type(inventory["file_backed_executable_region_count"]) is not int
        or type(inventory["unpathed_executable_region_count"]) is not int
        or inventory["executable_region_count"]
        != inventory["file_backed_executable_region_count"]
        + inventory["unpathed_executable_region_count"]
        or inventory["file_backed_executable_region_count"]
        != sum(artifact["executable_region_count"] for artifact in artifacts)
        or inventory["unpathed_executable_region_count"] < 0
        or inventory["mapped_file_count"] != len(artifacts)
        or inventory["artifacts_unchanged_after_child"] is not True
        or inventory["paths_retained"] is not False
        or sum(artifact["matches_process_image"] for artifact in artifacts) != 1
    ):
        raise ValueError("macOS native-image inventory counts differ")
    if value["conclusion"] != {
        "exact_child_pid_observed": True,
        "parent_owned_inventory": True,
        "stable_file_backed_executable_regions_bound": True,
        "main_process_image_present_once": True,
        "bound_to_model_worker": False,
        "separator_enabled": False,
    }:
        raise ValueError("macOS native-image conclusion differs")
    if any(value["permissions"].values()) or value["permissions"] != {
        "model_import_permitted": False,
        "checkpoint_access_permitted": False,
        "authorised_audio_access_permitted": False,
        "separator_execution_permitted": False,
        "source_graph_activation_permitted": False,
        "product_route_permitted": False,
        "publication_permitted": False,
    }:
        raise ValueError("macOS native-image permissions differ")
    if value["effects"] != {
        "process_started": True,
        "filesystem_written": False,
        "network_used": False,
        "checkpoint_opened": False,
        "model_imported": False,
        "audio_read": False,
        "source_graph_changed": False,
    }:
        raise ValueError("macOS native-image effects differ")
    if value["limitations"] != {
        "model_free_canary_only": True,
        "authorised_worker_not_bound": True,
        "dyld_shared_cache_constituents_enumerated": False,
        "transient_loads_between_snapshots_excluded": False,
        "mapped_memory_bytes_equal_reopened_file_bytes_proven": False,
        "dynamic_native_library_closure_bound": False,
        "post_observation_image_mutability_excluded": False,
    }:
        raise ValueError("macOS native-image limitations differ")
    checked = {**value, "evidence_sha256": digest}
    encoded = json.dumps(checked, sort_keys=True, separators=(",", ":"))
    if "/Users/" in encoded or "file://" in encoded or "://" in encoded:
        raise ValueError("macOS native-image inventory is not path-free")
    return _freeze_json(checked)


def _validate_artifact(value: Any, *, index: int) -> None:
    if not isinstance(value, dict) or set(value) != {
        "artifact_index",
        "bytes",
        "sha256",
        "executable_region_count",
        "executable_region_bytes",
        "static_code_status",
        "static_cdhash",
        "matches_process_image",
    }:
        raise ValueError("macOS native-image artifact fields differ")
    if (
        value["artifact_index"] != index
        or type(value["bytes"]) is not int
        or value["bytes"] <= 0
        or not _is_sha(value["sha256"])
        or type(value["executable_region_count"]) is not int
        or value["executable_region_count"] <= 0
        or type(value["executable_region_bytes"]) is not int
        or value["executable_region_bytes"] <= 0
        or type(value["matches_process_image"]) is not bool
    ):
        raise ValueError("macOS native-image artifact identity differs")
    if value["static_code_status"] == "strictly_valid":
        if not isinstance(value["static_cdhash"], str) or not _CDHASH_RE.fullmatch(
            value["static_cdhash"]
        ):
            raise ValueError("macOS native-image artifact signature differs")
    elif value["static_code_status"] == "not_strictly_valid":
        if value["static_cdhash"] is not None:
            raise ValueError("macOS native-image artifact signature differs")
    else:
        raise ValueError("macOS native-image artifact signature status differs")


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA_RE.fullmatch(value))


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


__all__ = ()
