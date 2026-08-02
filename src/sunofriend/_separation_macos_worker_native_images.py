"""Bind a stable macOS executable-region inventory to one ready model worker."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ._separation_macos_loaded_images import (
    _ExecutableRegion,
    _enumerate_executable_regions,
    _measure_mapped_files,
    _path_free_artifacts,
    _remeasure_mapped_files,
    _snapshot_key,
)
from ._separation_macos_process_image import _validate_runtime_process_image_binding
from ._separation_worker_ready_handshake import (
    READY_PHASE,
    READY_SCHEMA,
    RELEASE_PROTOCOL,
    _PreparedWorkerReadyHandshake,
    _prepare_worker_ready_handshake,
    _read_worker_ready_handshake,
    _release_worker_ready_handshake,
    _validate_worker_ready_claim,
)
from .separation_contract import _canonical_json_bytes, _freeze_json


SCHEMA = "sunofriend.private-macos-worker-native-image-inventory.v1"
POLICY_ID = "private-macos-worker-ready-native-image-inventory-v1"
_READY_TIMEOUT_SECONDS = 120.0
_SNAPSHOT_SETTLE_SECONDS = 0.02
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class _ObservedWorkerNativeImages:
    readiness: Mapping[str, Any]
    regions: tuple[_ExecutableRegion, ...]
    measured: tuple[Mapping[str, Any], ...]


def _prepare_macos_worker_native_image_observation() -> _PreparedWorkerReadyHandshake:
    if platform.system() != "Darwin":
        raise RuntimeError("worker native-image observation requires Darwin")
    return _prepare_worker_ready_handshake()


def _observe_macos_worker_native_images(
    prepared: _PreparedWorkerReadyHandshake,
    *,
    pid: int,
    process_image_path: Path,
) -> _ObservedWorkerNativeImages:
    """Wait for post-inference readiness, inventory the paused worker, release it."""

    readiness = _read_worker_ready_handshake(
        prepared,
        timeout_seconds=_READY_TIMEOUT_SECONDS,
    )
    first = _enumerate_executable_regions(pid)
    time.sleep(_SNAPSHOT_SETTLE_SECONDS)
    second = _enumerate_executable_regions(pid)
    if _snapshot_key(first) != _snapshot_key(second):
        raise RuntimeError("worker executable-region snapshots did not stabilise")
    measured = _measure_mapped_files(second, process_image_path=process_image_path)
    observed = _ObservedWorkerNativeImages(
        readiness=readiness,
        regions=tuple(second),
        measured=tuple(measured),
    )
    _release_worker_ready_handshake(prepared)
    return observed


def _complete_macos_worker_native_image_observation(
    *,
    observed: _ObservedWorkerNativeImages,
    runtime_process_image: Mapping[str, Any],
    child: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Remeasure mapped files and bind readiness to the final worker result."""

    if type(observed) is not _ObservedWorkerNativeImages:
        raise ValueError("worker native-image live observation differs")
    binding = _validate_runtime_process_image_binding(runtime_process_image)
    readiness = _validate_worker_ready_claim(observed.readiness)
    _require_readiness_matches_child(readiness, child=child)
    _remeasure_mapped_files(observed.measured)
    artifacts = _path_free_artifacts(observed.measured)
    file_backed = [region for region in observed.regions if region.path is not None]
    unpathed = [region for region in observed.regions if region.path is None]
    payload = {
        "schema": SCHEMA,
        "policy_id": POLICY_ID,
        "status": "worker_ready_executable_region_inventory_parent_verified",
        "platform": {"system": "Darwin", "machine": platform.machine()},
        "process_image_binding": _plain(binding),
        "readiness": _plain(readiness),
        "inventory": {
            "source": "libproc-proc-pidregionpathinfo",
            "snapshot_count": 2,
            "stable_consecutive_snapshots": True,
            "executable_region_count": len(observed.regions),
            "file_backed_executable_region_count": len(file_backed),
            "unpathed_executable_region_count": len(unpathed),
            "mapped_file_count": len(observed.measured),
            "artifacts": artifacts,
            "artifacts_unchanged_after_child": True,
            "paths_retained": False,
        },
        "conclusion": {
            "exact_child_pid_observed": True,
            "parent_owned_inventory": True,
            "post_inference_worker_ready_handshake_bound": True,
            "stable_file_backed_executable_regions_bound": True,
            "main_process_image_present_once": True,
            "bound_to_model_worker": True,
            "separator_enabled": False,
        },
        "permissions": {
            "automatic_selection_permitted": False,
            "source_graph_activation_permitted": False,
            "simple_mode_available": False,
            "studio_import_available": False,
            "product_route_permitted": False,
            "publication_permitted": False,
        },
        "effects": {
            "worker_observed": True,
            "worker_released_after_inventory": True,
            "source_graph_changed": False,
            "selection_changed": False,
            "product_route_changed": False,
        },
        "limitations": {
            "private_development_observation_only": True,
            "dyld_shared_cache_constituents_enumerated": False,
            "transient_loads_before_or_after_snapshots_excluded": False,
            "mapped_memory_bytes_equal_reopened_file_bytes_proven": False,
            "dynamic_native_library_closure_bound": False,
            "post_observation_image_mutability_excluded": False,
            "wider_supervisor_signal_boundary_complete": False,
        },
    }
    document = {
        **payload,
        "evidence_sha256": hashlib.sha256(_canonical_json_bytes(payload)).hexdigest(),
    }
    return _validate_macos_worker_native_image_observation(document)


def _validate_macos_worker_native_image_observation(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = _plain(document)
    required = {
        "schema",
        "policy_id",
        "status",
        "platform",
        "process_image_binding",
        "readiness",
        "inventory",
        "conclusion",
        "permissions",
        "effects",
        "limitations",
        "evidence_sha256",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("worker native-image evidence fields differ")
    digest = value.pop("evidence_sha256")
    if (
        not _is_sha(digest)
        or digest != hashlib.sha256(_canonical_json_bytes(value)).hexdigest()
    ):
        raise ValueError("worker native-image evidence self-hash differs")
    if (
        value["schema"] != SCHEMA
        or value["policy_id"] != POLICY_ID
        or value["status"] != "worker_ready_executable_region_inventory_parent_verified"
        or value["platform"].get("system") != "Darwin"
        or not isinstance(value["platform"].get("machine"), str)
        or not value["platform"]["machine"]
    ):
        raise ValueError("worker native-image evidence identity differs")
    binding = _validate_runtime_process_image_binding(value["process_image_binding"])
    if binding["platform"]["machine"] != value["platform"]["machine"]:
        raise ValueError("worker native-image process binding differs")
    readiness = _validate_worker_ready_claim(value["readiness"])
    if (
        readiness["schema"] != READY_SCHEMA
        or readiness["phase"] != READY_PHASE
        or readiness["release_protocol"] != RELEASE_PROTOCOL
    ):
        raise ValueError("worker native-image readiness differs")
    inventory = value["inventory"]
    expected_inventory = {
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
    }
    if not isinstance(inventory, dict) or set(inventory) != expected_inventory:
        raise ValueError("worker native-image inventory fields differ")
    artifacts = inventory["artifacts"]
    if not isinstance(artifacts, list) or not 1 <= len(artifacts) <= 512:
        raise ValueError("worker native-image artifact count differs")
    _validate_artifacts(artifacts)
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
        != sum(item["executable_region_count"] for item in artifacts)
        or inventory["unpathed_executable_region_count"] < 0
        or inventory["mapped_file_count"] != len(artifacts)
        or inventory["artifacts_unchanged_after_child"] is not True
        or inventory["paths_retained"] is not False
        or sum(item["matches_process_image"] for item in artifacts) != 1
    ):
        raise ValueError("worker native-image inventory counts differ")
    if value["conclusion"] != {
        "exact_child_pid_observed": True,
        "parent_owned_inventory": True,
        "post_inference_worker_ready_handshake_bound": True,
        "stable_file_backed_executable_regions_bound": True,
        "main_process_image_present_once": True,
        "bound_to_model_worker": True,
        "separator_enabled": False,
    }:
        raise ValueError("worker native-image conclusion differs")
    if any(value["permissions"].values()) or value["permissions"] != {
        "automatic_selection_permitted": False,
        "source_graph_activation_permitted": False,
        "simple_mode_available": False,
        "studio_import_available": False,
        "product_route_permitted": False,
        "publication_permitted": False,
    }:
        raise ValueError("worker native-image permissions differ")
    if value["effects"] != {
        "worker_observed": True,
        "worker_released_after_inventory": True,
        "source_graph_changed": False,
        "selection_changed": False,
        "product_route_changed": False,
    }:
        raise ValueError("worker native-image effects differ")
    if value["limitations"] != {
        "private_development_observation_only": True,
        "dyld_shared_cache_constituents_enumerated": False,
        "transient_loads_before_or_after_snapshots_excluded": False,
        "mapped_memory_bytes_equal_reopened_file_bytes_proven": False,
        "dynamic_native_library_closure_bound": False,
        "post_observation_image_mutability_excluded": False,
        "wider_supervisor_signal_boundary_complete": False,
    }:
        raise ValueError("worker native-image limitations differ")
    checked = {**value, "evidence_sha256": digest}
    encoded = json.dumps(checked, sort_keys=True, separators=(",", ":"))
    if "/Users/" in encoded or "file://" in encoded or "://" in encoded:
        raise ValueError("worker native-image evidence is not path-free")
    return _freeze_json(checked)


def _require_readiness_matches_child(
    readiness: Mapping[str, Any], *, child: Mapping[str, Any]
) -> None:
    try:
        bridge = child["model"]["bridge"]
        inference = child["model"]["inference"]
        authorisation = child["model"]["authorisation"]
        expected = {
            "schema": READY_SCHEMA,
            "phase": READY_PHASE,
            "candidate_id": bridge["candidate_id"],
            "checkpoint_sha256": bridge["checkpoint"]["sha256"],
            "authorised_audio_sha256": authorisation["audio_sha256"],
            "source_frames": inference["geometry"]["frames"],
            "vocal_float32_sha256": inference["outputs"]["vocals"]["sha256"],
            "instrumental_float32_sha256": inference["outputs"]["instrumental"][
                "sha256"
            ],
            "release_protocol": RELEASE_PROTOCOL,
        }
    except (KeyError, TypeError) as error:
        raise ValueError("worker final evidence cannot bind readiness") from error
    if _plain(readiness) != expected:
        raise ValueError("worker readiness and final evidence differ")


def _validate_artifacts(artifacts: Sequence[Mapping[str, Any]]) -> None:
    expected_fields = {
        "artifact_index",
        "bytes",
        "sha256",
        "executable_region_count",
        "executable_region_bytes",
        "static_code_status",
        "static_cdhash",
        "matches_process_image",
    }
    for index, artifact in enumerate(artifacts, start=1):
        if not isinstance(artifact, dict) or set(artifact) != expected_fields:
            raise ValueError("worker native-image artifact fields differ")
        if (
            artifact["artifact_index"] != index
            or type(artifact["bytes"]) is not int
            or artifact["bytes"] <= 0
            or not _is_sha(artifact["sha256"])
            or type(artifact["executable_region_count"]) is not int
            or artifact["executable_region_count"] <= 0
            or type(artifact["executable_region_bytes"]) is not int
            or artifact["executable_region_bytes"] <= 0
            or type(artifact["matches_process_image"]) is not bool
        ):
            raise ValueError("worker native-image artifact identity differs")
        status = artifact["static_code_status"]
        cdhash = artifact["static_cdhash"]
        if status == "strictly_valid":
            if not isinstance(cdhash, str) or not re.fullmatch(r"[0-9a-f]{40}", cdhash):
                raise ValueError("worker native-image artifact signature differs")
        elif status == "not_strictly_valid":
            if cdhash is not None:
                raise ValueError("worker native-image artifact signature differs")
        else:
            raise ValueError("worker native-image artifact signature status differs")


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA_RE.fullmatch(value))


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


__all__ = ()
