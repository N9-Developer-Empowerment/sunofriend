"""Read-only metadata preflight for one frozen separation bake-off arm.

This module deliberately performs the inspection in the trusted Sunofriend
parent process.  It does not execute the supplied Python launcher or ``.pth``
startup code, import backend code, deserialize a checkpoint, read audio or run
inference.

The current acceptance v1 contract does not preregister interpreter binary,
``pyvenv.cfg`` or accelerator-availability hashes.  Those gaps are explicit
limitations.  ``verified_not_run`` means only that the metadata and files v1
did register matched at this point; it is not permission to execute a hidden
evaluation and is never a quality, offline or promotion result.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import platform
import re
import stat
import sys
import unicodedata
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import compat32
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .separation_acceptance import (
    MAX_ACCEPTANCE_BYTES,
    MAX_HIDDEN_MANIFEST_BYTES,
    canonical_json_bytes,
    load_separation_acceptance_thresholds,
)
from .separation_bakeoff import (
    MAX_BAKEOFF_PREPARATION_BYTES,
    load_separation_bakeoff_preparation,
)


SEPARATION_BACKEND_PREFLIGHT_SCHEMA = (
    "sunofriend.separation-backend-preflight.v1"
)
SEPARATION_BACKEND_PREFLIGHT_PROBE_SCHEMA = (
    "sunofriend.separation-backend-parent-metadata.v1"
)
SEPARATION_BACKEND_PREFLIGHT_STATUS_VERIFIED = "verified_not_run"
SEPARATION_BACKEND_PREFLIGHT_STATUS_BLOCKED = "blocked"
SEPARATION_PACKAGE_SOURCE_HASH_ALGORITHM = (
    "installed-package-tree-sha256-v1"
)

MAX_WORKER_BYTES = 16 * 1024 * 1024
MAX_DEPENDENCY_LOCK_BYTES = 16 * 1024 * 1024
MAX_CHECKPOINT_BYTES = 8 * 1024 * 1024 * 1024
MAX_PYVENV_CONFIG_BYTES = 64 * 1024
MAX_PACKAGE_METADATA_BYTES = 2 * 1024 * 1024
MAX_PACKAGE_RECORD_BYTES = 16 * 1024 * 1024
MAX_DIRECT_URL_BYTES = 64 * 1024
MAX_PACKAGE_FILE_BYTES = 128 * 1024 * 1024
MAX_PACKAGE_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_PACKAGE_FILES = 20_000
MAX_RUNTIME_LINKS = 8

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PREFLIGHT_ID_RE = re.compile(
    r"^separation-backend-preflight:[0-9a-f]{64}$"
)
_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._+:/-]{0,191}$")
_VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._+-]{0,63}$")
_WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")
_PEP503_RE = re.compile(r"[-_.]+")
_CONSOLE_SCRIPT_RE = re.compile(
    r"^(?:\.\./){2,4}(?:bin|Scripts)/[A-Za-z0-9._+-]+$"
)
_PYTHON_VERSION_RE = re.compile(
    r"^3\.(?:9|10|11|12)(?:\.[0-9]+)?$"
)

_BLOCKER_CODES = frozenset(
    {
        "checkpoint_changed",
        "checkpoint_format_mismatch",
        "checkpoint_hash_mismatch",
        "checkpoint_missing",
        "checkpoint_size_mismatch",
        "checkpoint_unexpected",
        "checkpoint_unsafe",
        "dependency_lock_changed",
        "dependency_lock_hash_mismatch",
        "dependency_lock_missing",
        "dependency_lock_unsafe",
        "deployment_scope_unsupported",
        "device_accelerator_incompatible",
        "device_machine_mismatch",
        "device_platform_mismatch",
        "package_commit_mismatch",
        "package_commit_unverified",
        "package_editable_unsupported",
        "package_inventory_unsafe",
        "package_missing",
        "package_source_hash_mismatch",
        "package_version_mismatch",
        "runtime_id_mismatch",
        "runtime_launcher_changed",
        "runtime_launcher_missing",
        "runtime_launcher_unsafe",
        "runtime_version_mismatch",
        "worker_changed",
        "worker_hash_mismatch",
        "worker_missing",
        "worker_unsafe",
    }
)
_LIMITATIONS = (
    "accelerator_availability_not_probed",
    "backend_importability_not_probed",
    "console_scripts_not_probed",
    "installed_dependencies_not_probed",
    "interpreter_identity_not_preregistered",
    "offline_gate_not_tested",
    "site_startup_code_outside_distribution_not_probed",
)
_CHECK_IDS = (
    "acceptance_binding",
    "checkpoint",
    "dependency_lock_artifact",
    "device_metadata",
    "hidden_manifest_binding",
    "licence_policy",
    "package_metadata_identity",
    "package_provenance",
    "package_source",
    "preparation_binding",
    "runtime_metadata",
    "worker",
)
_CHECK_STATUSES = frozenset({"blocked", "matched", "not_probed"})
_EFFECT_FIELDS = frozenset(
    {
        "audio_read",
        "audio_written",
        "automatic_defaults_changed",
        "backend_code_imported",
        "backend_worker_started",
        "candidate_selected",
        "checkpoint_deserialized",
        "checkpoint_downloaded",
        "checkpoint_loaded",
        "files_written",
        "hidden_scores_read",
        "inference_executed",
        "inference_started",
        "metrics_computed",
        "model_downloaded",
        "model_executed",
        "model_loaded",
        "network_used",
        "package_code_imported",
        "private_metadata_exposed",
        "promotion_decided",
        "results_read",
        "roles_selected",
        "scores_read",
        "threshold_values_exposed",
    }
)
_TOP_FIELDS = frozenset(
    {
        "schema",
        "status",
        "preflight_id",
        "preflight_sha256",
        "bindings",
        "arm",
        "probe",
        "checks",
        "blockers",
        "limitations",
        "effects",
    }
)
_BINDING_FIELDS = frozenset(
    {
        "preparation_sha256",
        "acceptance_artifact_sha256",
        "acceptance_profile_id",
        "hidden_manifest_sha256",
        "hidden_split_sha256",
    }
)
_ARM_FIELDS = frozenset(
    {
        "arm_id",
        "separator_identity_id",
        "backend_id",
        "package_name",
        "package_version",
        "checkpoint_id",
        "checkpoint_format",
        "planned_device",
        "evaluation_scope",
    }
)
_DEVICE_FIELDS = frozenset({"platform", "machine", "accelerator"})
_PROBE_FIELDS = frozenset(
    {
        "protocol",
        "process_started",
        "source_hash_algorithm",
    }
)


@dataclass(frozen=True)
class _ReadEvidence:
    path: Path
    data: bytes
    facts: tuple[int, int, int, int, int]


@dataclass(frozen=True)
class _MeasuredEvidence:
    path: Path
    bytes: int
    facts: tuple[int, int, int, int, int]


@dataclass(frozen=True)
class _PackageStreamEvidence:
    file: _MeasuredEvidence
    ancestors: tuple[
        tuple[Path, tuple[int, int, int, int, int]], ...
    ]


@dataclass(frozen=True)
class _PackageInventoryEvidence:
    files: tuple[str, ...]
    directories: tuple[
        tuple[str, Path, tuple[int, int, int, int, int]], ...
    ]


def separation_backend_preflight_sha256(
    document: Mapping[str, Any],
) -> str:
    """Hash a preflight report excluding only its self-hash field."""

    payload = _plain(_mapping(document, "backend preflight"))
    payload.pop("preflight_sha256", None)
    _reject_invalid_tree(payload, "backend preflight")
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def preflight_separation_backend(
    preparation_path: str | Path,
    *,
    acceptance_path: str | Path,
    hidden_manifest_path: str | Path,
    arm_id: str,
    runtime_python_path: str | Path,
    worker_path: str | Path,
    dependency_lock_path: str | Path,
    checkpoint_path: str | Path | None,
    maximum_preparation_bytes: int = MAX_BAKEOFF_PREPARATION_BYTES,
    maximum_acceptance_bytes: int = MAX_ACCEPTANCE_BYTES,
    maximum_hidden_manifest_bytes: int = MAX_HIDDEN_MANIFEST_BYTES,
) -> Mapping[str, Any]:
    """Inspect one frozen arm without executing its runtime or backend."""

    preparation = load_separation_bakeoff_preparation(
        preparation_path,
        acceptance_path=acceptance_path,
        hidden_manifest_path=hidden_manifest_path,
        maximum_bytes=maximum_preparation_bytes,
        maximum_acceptance_bytes=maximum_acceptance_bytes,
        maximum_hidden_manifest_bytes=maximum_hidden_manifest_bytes,
    )
    acceptance = load_separation_acceptance_thresholds(
        acceptance_path,
        maximum_bytes=maximum_acceptance_bytes,
    )
    if (
        acceptance["artifact_sha256"]
        != preparation["acceptance"]["artifact_sha256"]
        or acceptance["profile_id"]
        != preparation["acceptance"]["profile_id"]
    ):
        raise ValueError(
            "preparation and frozen acceptance binding changed"
        )
    if arm_id not in {"baseline", "candidate"}:
        raise ValueError("arm_id must be baseline or candidate")
    identity_key = (
        "baseline_separator"
        if arm_id == "baseline"
        else "candidate_separator"
    )
    identity = acceptance["identities"][identity_key]
    prepared_arms = {
        arm["arm_id"]: arm["separator_identity_id"]
        for arm in preparation["orchestration"]["arms"]
    }
    if prepared_arms.get(arm_id) != identity["identity_id"]:
        raise ValueError("preparation arm does not match frozen identity")

    blockers: set[str] = set()
    worker = _measure_file(
        worker_path,
        maximum_bytes=MAX_WORKER_BYTES,
        label="worker",
        blockers=blockers,
    )
    _compare_file_hash(
        worker,
        expected_sha256=identity["worker_sha256"],
        label="worker",
        blockers=blockers,
    )
    dependency_lock = _measure_file(
        dependency_lock_path,
        maximum_bytes=MAX_DEPENDENCY_LOCK_BYTES,
        label="dependency_lock",
        blockers=blockers,
    )
    _compare_file_hash(
        dependency_lock,
        expected_sha256=identity["runtime"][
            "dependency_lock_sha256"
        ],
        label="dependency_lock",
        blockers=blockers,
    )
    checkpoint_evidence = _inspect_checkpoint(
        checkpoint_path,
        expected=identity["checkpoint"],
        blockers=blockers,
    )

    runtime_snapshot = _snapshot_runtime(
        runtime_python_path,
        blockers=blockers,
    )
    package_probed = False
    package: Mapping[str, Any] | None = None
    if runtime_snapshot is not None:
        runtime = identity["runtime"]
        version = runtime_snapshot["python_version"]
        if runtime["runtime_id"] != "cpython":
            blockers.add("runtime_id_mismatch")
        if (
            runtime["runtime_version"] != version
            or runtime["python_version"] != version
        ):
            blockers.add("runtime_version_mismatch")
        observed_platform = (
            "macos" if sys.platform == "darwin" else sys.platform
        )
        observed_machine = platform.machine()
        device = identity["device"]
        if observed_platform != device["platform"]:
            blockers.add("device_platform_mismatch")
        if observed_machine != device["machine"]:
            blockers.add("device_machine_mismatch")
        if device["accelerator"] == "mps" and (
            observed_platform != "macos" or observed_machine != "arm64"
        ):
            blockers.add("device_accelerator_incompatible")
        package_probed = True
        package = _inspect_installed_distribution(
            runtime_snapshot["site_root"],
            expected_name=identity["package_name"],
            blockers=blockers,
        )
        if package is not None:
            _compare_package(
                package,
                identity=identity,
                blockers=blockers,
            )
    deployment = acceptance["deployment_profile"]
    if (
        deployment["commercial_use_requested"]
        or deployment["component_redistribution_requested"]
        or deployment["derived_output_redistribution_requested"]
        or deployment["components_bundled_with_apache_package"]
    ):
        blockers.add("deployment_scope_unsupported")

    for label, evidence in (
        ("worker", worker),
        ("dependency_lock", dependency_lock),
        ("checkpoint", checkpoint_evidence),
    ):
        if evidence is not None and not _path_facts_match(
            evidence["path"], evidence["facts"]
        ):
            blockers.add(f"{label}_changed")
    if package is not None and not _package_evidence_unchanged(package):
        blockers.add("package_inventory_unsafe")
    if runtime_snapshot is not None and not _runtime_unchanged(
        runtime_snapshot
    ):
        blockers.add("runtime_launcher_changed")
        package_probed = False

    checks = _expected_checks(
        blockers,
        package_probed=package_probed,
    )
    status = (
        SEPARATION_BACKEND_PREFLIGHT_STATUS_VERIFIED
        if not blockers
        else SEPARATION_BACKEND_PREFLIGHT_STATUS_BLOCKED
    )
    checkpoint = identity["checkpoint"]
    arm = {
        "arm_id": arm_id,
        "separator_identity_id": identity["identity_id"],
        "backend_id": identity["backend_id"],
        "package_name": identity["package_name"],
        "package_version": identity["package_version"],
        "checkpoint_id": checkpoint.get(
            "checkpoint_id", "deterministic-no-checkpoint"
        ),
        "checkpoint_format": checkpoint.get("format", "none"),
        "planned_device": _plain(identity["device"]),
        "evaluation_scope": "private-local-evaluation-only",
    }
    bindings = {
        "preparation_sha256": preparation["preparation_sha256"],
        "acceptance_artifact_sha256": acceptance["artifact_sha256"],
        "acceptance_profile_id": acceptance["profile_id"],
        "hidden_manifest_sha256": preparation["hidden_evaluation"][
            "manifest_sha256"
        ],
        "hidden_split_sha256": preparation["hidden_evaluation"][
            "split_sha256"
        ],
    }
    probe = {
        "protocol": SEPARATION_BACKEND_PREFLIGHT_PROBE_SCHEMA,
        "process_started": False,
        "source_hash_algorithm": SEPARATION_PACKAGE_SOURCE_HASH_ALGORITHM,
    }
    effects = {name: False for name in sorted(_EFFECT_FIELDS)}
    identity_payload = {
        "schema": SEPARATION_BACKEND_PREFLIGHT_SCHEMA,
        "status": status,
        "bindings": bindings,
        "arm": arm,
        "probe": probe,
        "checks": checks,
        "blockers": sorted(blockers),
        "limitations": list(_LIMITATIONS),
        "effects": effects,
    }
    preflight_id = (
        "separation-backend-preflight:"
        + hashlib.sha256(canonical_json_bytes(identity_payload)).hexdigest()
    )
    document = {
        **identity_payload,
        "preflight_id": preflight_id,
        "preflight_sha256": "",
    }
    document["preflight_sha256"] = (
        separation_backend_preflight_sha256(document)
    )
    return validate_separation_backend_preflight(document)


def validate_separation_backend_preflight(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Validate and deep-freeze one path-free preflight report."""

    value = _plain(_mapping(document, "backend preflight"))
    _exact_fields(value, _TOP_FIELDS, "backend preflight")
    _reject_invalid_tree(value, "backend preflight")
    if value["schema"] != SEPARATION_BACKEND_PREFLIGHT_SCHEMA:
        raise ValueError("unsupported backend preflight schema")
    blockers = _sequence(value["blockers"], "blockers")
    checked_blockers = [
        _safe_id(item, f"blockers[{index}]")
        for index, item in enumerate(blockers)
    ]
    if checked_blockers != sorted(set(checked_blockers)):
        raise ValueError("preflight blockers must be sorted and unique")
    if not set(checked_blockers).issubset(_BLOCKER_CODES):
        raise ValueError("preflight blocker code is unsupported")
    expected_status = (
        SEPARATION_BACKEND_PREFLIGHT_STATUS_BLOCKED
        if checked_blockers
        else SEPARATION_BACKEND_PREFLIGHT_STATUS_VERIFIED
    )
    if value["status"] != expected_status:
        raise ValueError("preflight status does not match blockers")
    preflight_id = _text(value["preflight_id"], "preflight_id")
    if not _PREFLIGHT_ID_RE.fullmatch(preflight_id):
        raise ValueError("preflight_id is invalid")
    preflight_hash = _sha256(
        value["preflight_sha256"], "preflight_sha256"
    )

    bindings = _mapping(value["bindings"], "bindings")
    _exact_fields(bindings, _BINDING_FIELDS, "bindings")
    for key, item in bindings.items():
        if key == "acceptance_profile_id":
            _safe_id(item, f"bindings.{key}")
        else:
            _sha256(item, f"bindings.{key}")
    arm = _mapping(value["arm"], "arm")
    _exact_fields(arm, _ARM_FIELDS, "arm")
    if arm["arm_id"] not in {"baseline", "candidate"}:
        raise ValueError("preflight arm is invalid")
    for field_name in (
        "separator_identity_id",
        "backend_id",
        "package_name",
        "checkpoint_id",
    ):
        _safe_id(arm[field_name], f"arm.{field_name}")
    _version(arm["package_version"], "arm.package_version")
    if arm["checkpoint_format"] not in {
        "coreml",
        "none",
        "onnx",
        "safetensors",
        "torch-state-dict",
    }:
        raise ValueError("preflight checkpoint format is invalid")
    if arm["evaluation_scope"] != "private-local-evaluation-only":
        raise ValueError("preflight evaluation scope is invalid")
    device = _mapping(arm["planned_device"], "arm.planned_device")
    _exact_fields(device, _DEVICE_FIELDS, "arm.planned_device")
    if device["platform"] != "macos":
        raise ValueError("preflight device platform is invalid")
    if device["machine"] not in {"arm64", "x86_64"}:
        raise ValueError("preflight device machine is invalid")
    if device["accelerator"] not in {"cpu", "mps"}:
        raise ValueError("preflight device accelerator is invalid")

    probe = _mapping(value["probe"], "probe")
    _exact_fields(probe, _PROBE_FIELDS, "probe")
    if probe != {
        "protocol": SEPARATION_BACKEND_PREFLIGHT_PROBE_SCHEMA,
        "process_started": False,
        "source_hash_algorithm": SEPARATION_PACKAGE_SOURCE_HASH_ALGORITHM,
    }:
        raise ValueError("preflight probe evidence is invalid")
    checks = _mapping(value["checks"], "checks")
    _exact_fields(checks, frozenset(_CHECK_IDS), "checks")
    for check_id in _CHECK_IDS:
        if checks[check_id] not in _CHECK_STATUSES:
            raise ValueError("preflight check status is invalid")
    expected_checks = _expected_checks(
        set(checked_blockers),
        package_probed=not any(
            blocker.startswith("runtime_launcher")
            for blocker in checked_blockers
        ),
    )
    if _plain(checks) != expected_checks:
        raise ValueError("preflight checks do not match blockers")

    limitations = _sequence(value["limitations"], "limitations")
    if tuple(limitations) != _LIMITATIONS:
        raise ValueError("preflight limitations are fixed")
    effects = _mapping(value["effects"], "effects")
    _exact_fields(effects, _EFFECT_FIELDS, "effects")
    if any(item is not False for item in effects.values()):
        raise ValueError("every preflight effect must be false")
    id_payload = {
        key: _plain(value[key])
        for key in (
            "schema",
            "status",
            "bindings",
            "arm",
            "probe",
            "checks",
            "blockers",
            "limitations",
            "effects",
        )
    }
    expected_id = (
        "separation-backend-preflight:"
        + hashlib.sha256(canonical_json_bytes(id_payload)).hexdigest()
    )
    if preflight_id != expected_id:
        raise ValueError("preflight_id does not match report")
    if preflight_hash != separation_backend_preflight_sha256(value):
        raise ValueError("preflight_sha256 does not match report")
    return _freeze(value)


def _inspect_checkpoint(
    path: str | Path | None,
    *,
    expected: Mapping[str, Any],
    blockers: set[str],
) -> Mapping[str, Any] | None:
    if expected["kind"] == "deterministic-no-checkpoint":
        if path is not None:
            blockers.add("checkpoint_unexpected")
        return None
    if path is None:
        blockers.add("checkpoint_missing")
        return None
    evidence = _measure_file(
        path,
        maximum_bytes=min(
            MAX_CHECKPOINT_BYTES,
            expected["bytes"] + 1,
        ),
        label="checkpoint",
        blockers=blockers,
    )
    suffixes = {
        "safetensors": {".safetensors"},
        "torch-state-dict": {".pt", ".pth", ".th"},
        "onnx": {".onnx"},
        "coreml": {".mlmodel"},
    }
    if Path(path).suffix.casefold() not in suffixes[expected["format"]]:
        blockers.add("checkpoint_format_mismatch")
    if evidence is None:
        return None
    if evidence["bytes"] != expected["bytes"]:
        blockers.add("checkpoint_size_mismatch")
    if evidence["sha256"] != expected["sha256"]:
        blockers.add("checkpoint_hash_mismatch")
    return evidence


def _snapshot_runtime(
    path: str | Path,
    *,
    blockers: set[str],
) -> Mapping[str, Any] | None:
    launcher = Path(path)
    if not launcher.is_absolute():
        blockers.add("runtime_launcher_unsafe")
        return None
    chain: list[tuple[str, tuple[int, int, int, int, int], str | None]] = []
    current = launcher
    seen: set[str] = set()
    try:
        for _index in range(MAX_RUNTIME_LINKS + 1):
            key = os.path.abspath(os.fspath(current))
            if key in seen:
                blockers.add("runtime_launcher_unsafe")
                return None
            seen.add(key)
            info = current.lstat()
            facts = _facts(info)
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(current)
                chain.append((key, facts, target))
                current = Path(target)
                if not current.is_absolute():
                    current = Path(key).parent / current
                current = Path(os.path.abspath(os.fspath(current)))
                continue
            chain.append((key, facts, None))
            if not stat.S_ISREG(info.st_mode) or not os.access(
                current, os.X_OK
            ):
                blockers.add("runtime_launcher_unsafe")
                return None
            break
        else:
            blockers.add("runtime_launcher_unsafe")
            return None
    except FileNotFoundError:
        blockers.add("runtime_launcher_missing")
        return None
    except OSError:
        blockers.add("runtime_launcher_unsafe")
        return None

    if not _native_executable_header_matches(current, facts):
        blockers.add("runtime_launcher_unsafe")
        return None

    venv_root = launcher.parent.parent
    config_path = venv_root / "pyvenv.cfg"
    config_evidence = _read_file_evidence(
        config_path,
        maximum_bytes=MAX_PYVENV_CONFIG_BYTES,
        label="runtime_launcher",
        blockers=blockers,
    )
    if config_evidence is None:
        blockers.discard("runtime_launcher_missing")
        blockers.add("runtime_launcher_unsafe")
        return None
    try:
        config_text = config_evidence.data.decode("utf-8")
    except UnicodeDecodeError:
        blockers.add("runtime_launcher_unsafe")
        return None
    values: dict[str, str] = {}
    for raw_line in config_text.splitlines():
        if not raw_line.strip():
            continue
        if "=" not in raw_line:
            blockers.add("runtime_launcher_unsafe")
            return None
        key, raw_value = raw_line.split("=", 1)
        key = key.strip().casefold()
        value = raw_value.strip()
        if key in values or not key or not value:
            blockers.add("runtime_launcher_unsafe")
            return None
        values[key] = value
    version = values.get("version")
    if version is None or not _PYTHON_VERSION_RE.fullmatch(version):
        blockers.add("runtime_launcher_unsafe")
        return None
    major_minor = ".".join(version.split(".")[:2])
    site_root = (
        venv_root
        / "lib"
        / f"python{major_minor}"
        / "site-packages"
    )
    try:
        site_info = site_root.lstat()
    except OSError:
        blockers.add("runtime_launcher_unsafe")
        return None
    if stat.S_ISLNK(site_info.st_mode) or not stat.S_ISDIR(
        site_info.st_mode
    ):
        blockers.add("runtime_launcher_unsafe")
        return None
    return {
        "chain": tuple(chain),
        "venv_root": venv_root,
        "python_version": version,
        "config_facts": config_evidence.facts,
        "site_root": site_root,
        "site_facts": _stat_path(site_root),
    }


def _runtime_unchanged(snapshot: Mapping[str, Any]) -> bool:
    try:
        for path_text, facts, target in snapshot["chain"]:
            path = Path(path_text)
            if _stat_path(path) != tuple(facts):
                return False
            if target is not None and os.readlink(path) != target:
                return False
        return (
            _stat_path(Path(snapshot["venv_root"]) / "pyvenv.cfg")
            == tuple(snapshot["config_facts"])
            and _stat_path(Path(snapshot["site_root"]))
            == tuple(snapshot["site_facts"])
        )
    except OSError:
        return False


def _native_executable_header_matches(
    path: Path,
    expected_facts: tuple[int, int, int, int, int],
) -> bool:
    """Recognise a stable native launcher without executing it."""

    native_magics = {
        b"\x7fELF",
        b"\xca\xfe\xba\xbe",
        b"\xca\xfe\xba\xbf",
        b"\xce\xfa\xed\xfe",
        b"\xcf\xfa\xed\xfe",
        b"\xfe\xed\xfa\xce",
        b"\xfe\xed\xfa\xcf",
    }
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        header = os.read(descriptor, 4)
        finished = os.fstat(descriptor)
        after = path.lstat()
    except OSError:
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return (
        header in native_magics
        and _facts(opened) == expected_facts
        and _facts(finished) == expected_facts
        and _facts(after) == expected_facts
    )


def _inspect_installed_distribution(
    site_root: Path,
    *,
    expected_name: str,
    blockers: set[str],
) -> Mapping[str, Any] | None:
    try:
        entries = list(os.scandir(site_root))
    except OSError:
        blockers.add("package_inventory_unsafe")
        return None
    matches: list[tuple[Path, bytes, tuple[int, int, int, int, int]]] = []
    for entry in entries:
        if not entry.name.casefold().endswith(".dist-info"):
            continue
        try:
            info = entry.stat(follow_symlinks=False)
        except OSError:
            blockers.add("package_inventory_unsafe")
            return None
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            blockers.add("package_inventory_unsafe")
            return None
        dist_path = Path(entry.path)
        metadata_evidence = _read_package_file_evidence(
            site_root,
            f"{entry.name}/METADATA",
            maximum_bytes=MAX_PACKAGE_METADATA_BYTES,
            blockers=blockers,
        )
        if metadata_evidence is None:
            continue
        metadata = metadata_evidence.data
        try:
            parsed = BytesParser(policy=compat32).parsebytes(metadata)
            name = parsed.get("Name")
        except (TypeError, ValueError):
            blockers.add("package_inventory_unsafe")
            return None
        if (
            isinstance(name, str)
            and _canonical_package_name(name)
            == _canonical_package_name(expected_name)
        ):
            matches.append(
                (dist_path, metadata, metadata_evidence.facts)
            )
    if not matches:
        blockers.add("package_missing")
        return None
    if len(matches) != 1:
        blockers.add("package_inventory_unsafe")
        return None
    dist_path, metadata_bytes, metadata_facts = matches[0]
    try:
        metadata = BytesParser(policy=compat32).parsebytes(metadata_bytes)
        observed_name = str(metadata["Name"])
        observed_version = str(metadata["Version"])
    except (KeyError, TypeError, ValueError):
        blockers.add("package_inventory_unsafe")
        return None

    record_evidence = _read_package_file_evidence(
        site_root,
        f"{dist_path.name}/RECORD",
        maximum_bytes=MAX_PACKAGE_RECORD_BYTES,
        blockers=blockers,
    )
    if record_evidence is None:
        blockers.add("package_inventory_unsafe")
        return None
    record = record_evidence.data
    try:
        rows = list(csv.reader(io.StringIO(record.decode("utf-8"))))
    except (UnicodeDecodeError, csv.Error):
        blockers.add("package_inventory_unsafe")
        return None
    if not rows or len(rows) > MAX_PACKAGE_FILES:
        blockers.add("package_inventory_unsafe")
        return None
    relative_paths: set[str] = set()
    package_roots: set[str] = set()
    seen: set[str] = set()
    direct_url_path: Path | None = None
    for row in rows:
        if not row:
            blockers.add("package_inventory_unsafe")
            return None
        raw = row[0].replace("\\", "/")
        if _CONSOLE_SCRIPT_RE.fullmatch(raw):
            continue
        relative = _safe_distribution_relative(raw)
        if relative is None or relative in seen:
            blockers.add("package_inventory_unsafe")
            return None
        seen.add(relative)
        folded = relative.casefold()
        if folded.endswith(".dist-info/direct_url.json"):
            direct_url_path = site_root / PurePosixPath(relative)
            continue
        relative_paths.add(relative)
        parts = PurePosixPath(relative).parts
        if (
            len(parts) > 1
            and not parts[0].casefold().endswith(".dist-info")
        ):
            package_roots.add(parts[0])
    inventoried = _inventory_package_roots(
        site_root,
        roots=package_roots | {dist_path.name},
        blockers=blockers,
    )
    if inventoried is None:
        return None
    relative_paths.update(inventoried.files)
    relative_paths = {
        relative
        for relative in relative_paths
        if not relative.casefold().endswith(
            ".dist-info/direct_url.json"
        )
    }
    if not relative_paths or len(relative_paths) > MAX_PACKAGE_FILES:
        blockers.add("package_inventory_unsafe")
        return None

    digest = hashlib.sha256()
    for relative, _path, _facts_value in inventoried.directories:
        digest.update(b"directory\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
    total_bytes = 0
    source_files = 0
    streamed: list[_PackageStreamEvidence] = []
    for relative in sorted(relative_paths):
        measured = _stream_package_file_into_digest(
            site_root,
            relative,
            relative=relative,
            digest=digest,
            maximum_bytes=MAX_PACKAGE_FILE_BYTES,
            blockers=blockers,
        )
        if measured is None:
            blockers.add("package_inventory_unsafe")
            return None
        streamed.append(measured)
        total_bytes += measured.file.bytes
        if total_bytes > MAX_PACKAGE_TOTAL_BYTES:
            blockers.add("package_inventory_unsafe")
            return None
        if ".dist-info/" not in relative.casefold():
            source_files += 1
    if source_files < 1:
        blockers.add("package_inventory_unsafe")
        return None

    commit: str | None = None
    editable = False
    direct_facts: tuple[int, int, int, int, int] | None = None
    if direct_url_path is not None:
        direct_evidence = _read_package_file_evidence(
            site_root,
            direct_url_path.relative_to(site_root).as_posix(),
            maximum_bytes=MAX_DIRECT_URL_BYTES,
            blockers=blockers,
        )
        if direct_evidence is None:
            blockers.add("package_inventory_unsafe")
            return None
        direct = direct_evidence.data
        direct_facts = direct_evidence.facts
        try:
            document = json.loads(
                direct.decode("utf-8"),
                object_pairs_hook=_reject_duplicate_pairs,
                parse_constant=_reject_json_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            blockers.add("package_inventory_unsafe")
            return None
        if not isinstance(document, dict):
            blockers.add("package_inventory_unsafe")
            return None
        directory = document.get("dir_info")
        if directory is not None:
            if not isinstance(directory, dict):
                blockers.add("package_inventory_unsafe")
                return None
            editable_value = directory.get("editable", False)
            if not isinstance(editable_value, bool):
                blockers.add("package_inventory_unsafe")
                return None
            editable = editable_value
        vcs = document.get("vcs_info")
        if isinstance(vcs, dict) and vcs.get("vcs") == "git":
            raw_commit = vcs.get("commit_id")
            if isinstance(raw_commit, str) and re.fullmatch(
                r"[0-9a-f]{40}|[0-9a-f]{64}", raw_commit
            ):
                commit = raw_commit

    if not _path_facts_match(dist_path / "METADATA", metadata_facts):
        blockers.add("package_inventory_unsafe")
        return None
    if not _path_facts_match(
        dist_path / "RECORD", record_evidence.facts
    ):
        blockers.add("package_inventory_unsafe")
        return None
    if direct_url_path is not None and (
        direct_facts is None
        or not _path_facts_match(direct_url_path, direct_facts)
    ):
        blockers.add("package_inventory_unsafe")
        return None
    return {
        "name": observed_name,
        "version": observed_version,
        "source_sha256": digest.hexdigest(),
        "commit": commit,
        "editable": editable,
        "stability_files": tuple(
            (
                item.file.path,
                item.file.facts,
                item.ancestors,
            )
            for item in streamed
        )
        + (
            (
                metadata_evidence.path,
                metadata_evidence.facts,
                (),
            ),
            (
                record_evidence.path,
                record_evidence.facts,
                (),
            ),
        )
        + (
            ()
            if direct_url_path is None or direct_facts is None
            else ((direct_url_path, direct_facts, ()),)
        ),
        "stability_directories": inventoried.directories,
    }


def _compare_package(
    package: Mapping[str, Any],
    *,
    identity: Mapping[str, Any],
    blockers: set[str],
) -> None:
    if package["version"] != identity["package_version"]:
        blockers.add("package_version_mismatch")
    if package["editable"]:
        blockers.add("package_editable_unsupported")
    if package["source_sha256"] != identity["package_source_sha256"]:
        blockers.add("package_source_hash_mismatch")
    expected_commit = identity["package_commit"]
    observed_commit = package["commit"]
    if len(expected_commit) not in {40, 64} or observed_commit is None:
        blockers.add("package_commit_unverified")
    elif observed_commit != expected_commit:
        blockers.add("package_commit_mismatch")


def _package_evidence_unchanged(package: Mapping[str, Any]) -> bool:
    for path, facts, ancestors in package["stability_files"]:
        if not _path_facts_match(path, facts):
            return False
        if not _package_ancestors_unchanged(ancestors):
            return False
    return all(
        _path_facts_match(path, facts)
        for _relative, path, facts in package["stability_directories"]
    )


def _safe_distribution_relative(value: str) -> str | None:
    if (
        not value
        or value.startswith("/")
        or _WINDOWS_ABSOLUTE_PATH_RE.match(value)
        or unicodedata.normalize("NFC", value) != value
    ):
        return None
    path = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path.as_posix()


def _inventory_package_roots(
    site_root: Path,
    *,
    roots: set[str],
    blockers: set[str],
) -> _PackageInventoryEvidence | None:
    """Inventory every regular file below the distribution-owned roots."""

    files: set[str] = set()
    directories: list[
        tuple[str, Path, tuple[int, int, int, int, int]]
    ] = []
    visited_directories: set[tuple[int, int]] = set()
    pending: list[tuple[Path, str]] = []
    for root in sorted(roots):
        safe_root = _safe_distribution_relative(root)
        if safe_root is None or safe_root != root or "/" in root:
            blockers.add("package_inventory_unsafe")
            return None
        pending.append((site_root / root, root))

    visited_entries = 0
    while pending:
        directory, relative_directory = pending.pop()
        try:
            before = directory.lstat()
            if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(
                before.st_mode
            ):
                blockers.add("package_inventory_unsafe")
                return None
            directory_id = (before.st_dev, before.st_ino)
            if directory_id in visited_directories:
                blockers.add("package_inventory_unsafe")
                return None
            visited_directories.add(directory_id)
            with os.scandir(directory) as scanner:
                entries = list(scanner)
        except OSError:
            blockers.add("package_inventory_unsafe")
            return None
        for entry in entries:
            visited_entries += 1
            if visited_entries > MAX_PACKAGE_FILES:
                blockers.add("package_inventory_unsafe")
                return None
            relative = (
                PurePosixPath(relative_directory) / entry.name
            ).as_posix()
            if _safe_distribution_relative(relative) != relative:
                blockers.add("package_inventory_unsafe")
                return None
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError:
                blockers.add("package_inventory_unsafe")
                return None
            if stat.S_ISLNK(info.st_mode):
                blockers.add("package_inventory_unsafe")
                return None
            if stat.S_ISDIR(info.st_mode):
                pending.append((Path(entry.path), relative))
            elif stat.S_ISREG(info.st_mode):
                files.add(relative)
            else:
                blockers.add("package_inventory_unsafe")
                return None
        try:
            after = directory.lstat()
        except OSError:
            blockers.add("package_inventory_unsafe")
            return None
        if _facts(after) != _facts(before):
            blockers.add("package_inventory_unsafe")
            return None
        directories.append(
            (relative_directory, directory, _facts(before))
        )
    return _PackageInventoryEvidence(
        files=tuple(sorted(files)),
        directories=tuple(sorted(directories, key=lambda item: item[0])),
    )


def _measure_file(
    path: str | Path,
    *,
    maximum_bytes: int,
    label: str,
    blockers: set[str],
) -> Mapping[str, Any] | None:
    evidence = _read_file_evidence(
        path,
        maximum_bytes=maximum_bytes,
        label=label,
        blockers=blockers,
    )
    if evidence is None:
        return None
    return {
        "sha256": hashlib.sha256(evidence.data).hexdigest(),
        "bytes": len(evidence.data),
        "path": evidence.path,
        "facts": evidence.facts,
    }


def _read_file_evidence(
    path: str | Path,
    *,
    maximum_bytes: int,
    label: str,
    blockers: set[str],
) -> _ReadEvidence | None:
    file_path = Path(path)
    missing = f"{label}_missing"
    unsafe = f"{label}_unsafe"
    changed = f"{label}_changed"
    if label == "package":
        missing = unsafe = changed = "package_inventory_unsafe"
    if not file_path.is_absolute():
        blockers.add(unsafe)
        return None
    try:
        before = file_path.lstat()
    except FileNotFoundError:
        blockers.add(missing)
        return None
    except OSError:
        blockers.add(unsafe)
        return None
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        blockers.add(unsafe)
        return None
    if before.st_size < 1 or before.st_size > maximum_bytes:
        if label == "checkpoint":
            blockers.add("checkpoint_size_mismatch")
        else:
            blockers.add(unsafe)
        return None
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(file_path, flags)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
        ):
            blockers.add(changed)
            return None
        chunks: list[bytes] = []
        total = 0
        while total <= maximum_bytes:
            chunk = os.read(
                descriptor,
                min(1024 * 1024, maximum_bytes + 1 - total),
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        finished = os.fstat(descriptor)
    except OSError:
        blockers.add(unsafe)
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    try:
        after = file_path.lstat()
    except OSError:
        blockers.add(changed)
        return None
    if (
        total > maximum_bytes
        or total != before.st_size
        or _facts(opened) != _facts(finished)
        or _facts(before) != _facts(after)
    ):
        blockers.add(changed)
        return None
    return _ReadEvidence(
        path=file_path,
        data=b"".join(chunks),
        facts=_facts(before),
    )


def _read_package_file_evidence(
    site_root: Path,
    relative: str,
    *,
    maximum_bytes: int,
    blockers: set[str],
) -> _ReadEvidence | None:
    snapshot = _package_ancestor_snapshot(
        site_root,
        relative,
        blockers=blockers,
    )
    if snapshot is None:
        return None
    evidence = _read_file_evidence(
        site_root / PurePosixPath(relative),
        maximum_bytes=maximum_bytes,
        label="package",
        blockers=blockers,
    )
    if evidence is None:
        return None
    if not _package_ancestors_unchanged(snapshot):
        blockers.add("package_inventory_unsafe")
        return None
    return evidence


def _stream_package_file_into_digest(
    site_root: Path,
    path_relative: str,
    *,
    relative: str,
    digest: Any,
    maximum_bytes: int,
    blockers: set[str],
) -> _PackageStreamEvidence | None:
    snapshot = _package_ancestor_snapshot(
        site_root,
        path_relative,
        blockers=blockers,
    )
    if snapshot is None:
        return None
    measured = _stream_file_into_digest(
        site_root / PurePosixPath(path_relative),
        relative=relative,
        digest=digest,
        maximum_bytes=maximum_bytes,
        blockers=blockers,
    )
    if measured is None:
        return None
    if not _package_ancestors_unchanged(snapshot):
        blockers.add("package_inventory_unsafe")
        return None
    return _PackageStreamEvidence(
        file=measured,
        ancestors=snapshot,
    )


def _package_ancestor_snapshot(
    site_root: Path,
    relative: str,
    *,
    blockers: set[str],
) -> tuple[tuple[Path, tuple[int, int, int, int, int]], ...] | None:
    safe_relative = _safe_distribution_relative(relative)
    if safe_relative is None or safe_relative != relative:
        blockers.add("package_inventory_unsafe")
        return None
    snapshots: list[tuple[Path, tuple[int, int, int, int, int]]] = []
    current = site_root
    try:
        for part in (None, *PurePosixPath(relative).parts[:-1]):
            if part is not None:
                current = current / part
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(
                info.st_mode
            ):
                blockers.add("package_inventory_unsafe")
                return None
            snapshots.append((current, _facts(info)))
    except OSError:
        blockers.add("package_inventory_unsafe")
        return None
    return tuple(snapshots)


def _package_ancestors_unchanged(
    snapshot: Sequence[tuple[Path, tuple[int, int, int, int, int]]],
) -> bool:
    try:
        return all(
            _stat_path(path) == facts for path, facts in snapshot
        )
    except OSError:
        return False


def _stream_file_into_digest(
    path: Path,
    *,
    relative: str,
    digest: Any,
    maximum_bytes: int,
    blockers: set[str],
) -> _MeasuredEvidence | None:
    try:
        before = path.lstat()
    except OSError:
        blockers.add("package_inventory_unsafe")
        return None
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_size > maximum_bytes
    ):
        blockers.add("package_inventory_unsafe")
        return None
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    total = 0
    digest.update(b"file\0")
    digest.update(relative.encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(before.st_size).encode("ascii"))
    digest.update(b"\0")
    try:
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
        ):
            blockers.add("package_inventory_unsafe")
            return None
        while total <= maximum_bytes:
            chunk = os.read(
                descriptor,
                min(1024 * 1024, maximum_bytes + 1 - total),
            )
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
        finished = os.fstat(descriptor)
    except OSError:
        blockers.add("package_inventory_unsafe")
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    try:
        after = path.lstat()
    except OSError:
        blockers.add("package_inventory_unsafe")
        return None
    if (
        total > maximum_bytes
        or total != before.st_size
        or _facts(opened) != _facts(finished)
        or _facts(before) != _facts(after)
    ):
        blockers.add("package_inventory_unsafe")
        return None
    digest.update(b"\0")
    return _MeasuredEvidence(
        path=path,
        bytes=total,
        facts=_facts(before),
    )


def _compare_file_hash(
    evidence: Mapping[str, Any] | None,
    *,
    expected_sha256: str,
    label: str,
    blockers: set[str],
) -> None:
    if evidence is not None and evidence["sha256"] != expected_sha256:
        blockers.add(f"{label}_hash_mismatch")


def _expected_checks(
    blockers: set[str],
    *,
    package_probed: bool,
) -> dict[str, str]:
    checks = {check_id: "matched" for check_id in _CHECK_IDS}
    checks["runtime_metadata"] = "not_probed"
    if not package_probed:
        for check_id in (
            "device_metadata",
            "package_metadata_identity",
            "package_provenance",
            "package_source",
        ):
            checks[check_id] = "not_probed"
    mapping = {
        "checkpoint": "checkpoint",
        "dependency_lock": "dependency_lock_artifact",
        "deployment": "licence_policy",
        "device": "device_metadata",
        "package_commit": "package_provenance",
        "package_editable": "package_provenance",
        "package_inventory": "package_source",
        "package_missing": "package_metadata_identity",
        "package_source": "package_source",
        "package_version": "package_metadata_identity",
        "runtime": "runtime_metadata",
        "worker": "worker",
    }
    for blocker in blockers:
        for prefix, check_id in mapping.items():
            if blocker.startswith(prefix):
                checks[check_id] = "blocked"
                break
    if "package_missing" in blockers:
        checks["package_provenance"] = "not_probed"
        checks["package_source"] = "not_probed"
    if "package_inventory_unsafe" in blockers:
        for check_id in (
            "package_metadata_identity",
            "package_provenance",
            "package_source",
        ):
            checks[check_id] = "blocked"
    return checks


def _canonical_package_name(value: str) -> str:
    return _PEP503_RE.sub("-", value).casefold()


def _facts(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _stat_path(path: Path) -> tuple[int, int, int, int, int]:
    return _facts(path.lstat())


def _path_facts_match(
    path: Path,
    expected: tuple[int, int, int, int, int],
) -> bool:
    try:
        return _stat_path(path) == expected
    except OSError:
        return False


def _reject_duplicate_pairs(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _exact_fields(
    value: Mapping[str, Any],
    expected: frozenset[str],
    label: str,
) -> None:
    if set(value) != set(expected):
        raise ValueError(f"{label} fields are invalid")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, (list, tuple)) or isinstance(value, str):
        raise ValueError(f"{label} must be an array")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    if not value or value != value.strip() or len(value) > 512:
        raise ValueError(f"{label} must be bounded non-blank text")
    if any(ord(character) < 32 for character in value):
        raise ValueError(f"{label} must not contain control characters")
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError(f"{label} must use NFC-normalized text")
    _reject_private_path_or_url(value, label)
    return value


def _reject_private_path_or_url(value: str, label: str) -> None:
    folded = value.casefold()
    embedded_private_roots = (
        ":/applications/",
        ":/home/",
        ":/library/",
        ":/private/",
        ":/tmp/",
        ":/users/",
        ":/var/",
        ":/volumes/",
    )
    if (
        value.startswith(("/", "~", "./", "../"))
        or _WINDOWS_ABSOLUTE_PATH_RE.match(value)
        or "://" in value
        or folded.startswith("file:")
        or "/users/" in folded
        or "\\users\\" in folded
        or any(root in folded for root in embedded_private_roots)
    ):
        raise ValueError(f"{label} must not contain a private path or URL")


def _safe_id(value: Any, label: str) -> str:
    text = _text(value, label)
    if not _SAFE_ID_RE.fullmatch(text):
        raise ValueError(f"{label} must be a safe identifier")
    return text


def _version(value: Any, label: str) -> str:
    text = _text(value, label)
    if not _VERSION_RE.fullmatch(text):
        raise ValueError(f"{label} must be a version")
    return text


def _sha256(value: Any, label: str) -> str:
    text = _text(value, label)
    if not _SHA256_RE.fullmatch(text) or set(text) == {"0"}:
        raise ValueError(f"{label} must be a non-zero lowercase SHA-256")
    return text


def _reject_invalid_tree(value: Any, label: str) -> None:
    if value is None:
        raise ValueError(f"{label} must not contain null")
    if isinstance(value, bool) or isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value) or (
            value == 0.0 and math.copysign(1.0, value) < 0.0
        ):
            raise ValueError(f"{label} contains an invalid number")
        return
    if isinstance(value, str):
        _text(value, label)
        return
    if isinstance(value, Mapping):
        if not value:
            raise ValueError(f"{label} must not contain empty objects")
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{label} keys must be strings")
            _text(key, f"{label} key")
            _reject_invalid_tree(item, f"{label}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_invalid_tree(item, f"{label}[{index}]")
        return
    raise ValueError(f"{label} contains an unsupported value")


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("object keys must be strings")
            result[key] = _plain(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze(value[key]) for key in sorted(value)}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


__all__ = [
    "MAX_CHECKPOINT_BYTES",
    "MAX_DEPENDENCY_LOCK_BYTES",
    "MAX_WORKER_BYTES",
    "SEPARATION_BACKEND_PREFLIGHT_PROBE_SCHEMA",
    "SEPARATION_BACKEND_PREFLIGHT_SCHEMA",
    "SEPARATION_BACKEND_PREFLIGHT_STATUS_BLOCKED",
    "SEPARATION_BACKEND_PREFLIGHT_STATUS_VERIFIED",
    "SEPARATION_PACKAGE_SOURCE_HASH_ALGORITHM",
    "preflight_separation_backend",
    "separation_backend_preflight_sha256",
    "validate_separation_backend_preflight",
]
