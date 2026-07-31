"""Read-only admission evidence for the blocked private BS-RoFormer plan.

This module binds the exact source audit to Sunofriend's tracked dependency
and licence evidence.  It does not inspect or open a checkpoint, install the
runtime, import model code, start a process, or authorize execution.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping

from ._separation_roformer_challenger_plan import (
    POLICY_ID,
    RUNTIME_DEPENDENCY_INPUT,
    RUNTIME_DEPENDENCY_INPUT_SHA256,
    RUNTIME_DEPENDENCY_LOCK,
    RUNTIME_DEPENDENCY_LOCK_SHA256,
    RUNTIME_LICENSE_AUDIT,
    RUNTIME_LICENSE_AUDIT_SHA256,
)
from ._separation_roformer_contract_plan import (
    ROFORMER_ADMISSION_POLICY,
    ROFORMER_ADMISSION_SCHEMA,
)
from ._separation_roformer_source import (
    SOURCE_MANIFEST,
    SOURCE_MANIFEST_SHA256,
    SOURCE_REVISION,
    _verify_private_roformer_source_tree,
)
from ._separation_roformer_upstream_evidence import (
    UPSTREAM_EVIDENCE,
    UPSTREAM_EVIDENCE_BYTES,
    UPSTREAM_EVIDENCE_SHA256,
    _report_from_verified_contents,
)


_EXPECTED_FILES = {
    SOURCE_MANIFEST: {
        "bytes": 1_749,
        "sha256": SOURCE_MANIFEST_SHA256,
        "maximum_bytes": 64 * 1024,
    },
    RUNTIME_DEPENDENCY_INPUT: {
        "bytes": 1_219,
        "sha256": RUNTIME_DEPENDENCY_INPUT_SHA256,
        "maximum_bytes": 64 * 1024,
    },
    RUNTIME_DEPENDENCY_LOCK: {
        "bytes": 19_093,
        "sha256": RUNTIME_DEPENDENCY_LOCK_SHA256,
        "maximum_bytes": 4 * 1024 * 1024,
    },
    RUNTIME_LICENSE_AUDIT: {
        "bytes": 6_598,
        "sha256": RUNTIME_LICENSE_AUDIT_SHA256,
        "maximum_bytes": 512 * 1024,
    },
    UPSTREAM_EVIDENCE: {
        "bytes": UPSTREAM_EVIDENCE_BYTES,
        "sha256": UPSTREAM_EVIDENCE_SHA256,
        "maximum_bytes": 64 * 1024,
    },
}
_PACKAGE_LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s\\]+)")
_NORMALIZE_PACKAGE = re.compile(r"[-_.]+")
_BLOCKERS = (
    "apple_runtime_resource_bounds_unmeasured",
    "checkpoint_allowed_use_unverified",
    "checkpoint_sha256_unpublished",
    "checkpoint_static_inspection_not_completed",
    "checkpoint_terms_unverified",
    "explicit_private_evaluation_approval_missing",
    "runtime_environment_not_installed",
    "runtime_worker_not_implemented",
)


def _build_private_roformer_admission(
    *, repository_root: str | Path, source_tree: str | Path
) -> dict[str, Any]:
    """Verify exact code/runtime planning evidence without enabling execution."""

    source = _path_free_source_verification(
        _verify_private_roformer_source_tree(source_tree)
    )
    files, contents = _read_repository_evidence(repository_root)
    manifest = _parse_object(contents[SOURCE_MANIFEST], "source manifest")
    dependency_audit = _parse_object(
        contents[RUNTIME_LICENSE_AUDIT], "runtime licence audit"
    )
    direct_packages = _parse_requirement_packages(
        contents[RUNTIME_DEPENDENCY_INPUT], "dependency input"
    )
    locked_packages = _parse_requirement_packages(
        contents[RUNTIME_DEPENDENCY_LOCK], "dependency lock"
    )
    upstream = _report_from_verified_contents(contents[UPSTREAM_EVIDENCE])
    _verify_source_manifest(manifest, source)
    _verify_runtime_evidence(
        dependency_audit,
        direct_packages=direct_packages,
        locked_packages=locked_packages,
    )

    result: dict[str, Any] = {
        "schema": ROFORMER_ADMISSION_SCHEMA,
        "admission_policy": ROFORMER_ADMISSION_POLICY,
        "candidate_policy_id": POLICY_ID,
        "status": "blocked",
        "path_free": True,
        "admission_sha256": "",
        "source": source,
        "repository_evidence": {
            "status": "verified_read_only",
            "files": files,
            "direct_packages": list(direct_packages),
            "direct_package_count": len(direct_packages),
            "locked_packages": list(locked_packages),
            "locked_package_count": len(locked_packages),
            "all_locked_packages_have_licence_evidence": True,
            "private_local_evaluation_licence_compatible": True,
            "runtime_installation_permitted_by_this_admission": False,
            "checkpoint_terms_covered": False,
            "redistribution_review_required": True,
            "upstream_release": upstream,
        },
        "readiness": {
            "exact_source_tree_verified": True,
            "exact_import_surface_verified": True,
            "runtime_input_verified": True,
            "runtime_lock_verified": True,
            "runtime_licence_audit_verified": True,
            "official_upstream_release_evidence_verified": True,
            "code_and_runtime_plan_ready": True,
            "checkpoint_identity_verified": False,
            "checkpoint_terms_verified": False,
            "checkpoint_static_inspection_completed": False,
            "runtime_environment_installed_and_verified": False,
            "worker_implemented": False,
            "private_evaluation_eligible": False,
            "worker_start_permitted": False,
        },
        "blockers": list(_BLOCKERS),
        "effects": {
            "filesystem_accessed": True,
            "filesystem_written": False,
            "network_used": False,
            "package_installed": False,
            "checkpoint_opened": False,
            "checkpoint_downloaded": False,
            "checkpoint_deserialized": False,
            "model_imported": False,
            "process_started": False,
            "product_route_changed": False,
        },
    }
    result["admission_sha256"] = _admission_sha256(result)
    return result


def _admission_sha256(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("admission_sha256", None)
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _path_free_source_verification(value: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("schema") != "sunofriend.private-roformer-source-verification.v2":
        raise ValueError("RoFormer source verification schema is unsupported")
    if value.get("status") != "verified_not_imported":
        raise ValueError("RoFormer source verification did not pass")
    if value.get("revision_claim") != SOURCE_REVISION:
        raise ValueError("RoFormer source revision differs")
    manifest = value.get("manifest")
    if not isinstance(manifest, Mapping) or manifest.get("sha256") != (
        SOURCE_MANIFEST_SHA256
    ):
        raise ValueError("RoFormer source verification manifest differs")
    effects = value.get("effects")
    if not isinstance(effects, Mapping) or effects != {
        "filesystem_accessed": True,
        "filesystem_written": False,
        "network_used": False,
        "model_imported": False,
        "process_started": False,
        "package_installed": False,
    }:
        raise ValueError("RoFormer source verification effects differ")
    if (
        value.get("package_initializer_executed") is not False
        or value.get("model_import_permitted") is not False
    ):
        raise ValueError("RoFormer source verification execution boundary differs")
    files = value.get("files")
    policy = value.get("static_source_policy")
    if (
        not isinstance(files, list)
        or len(files) != 3
        or not isinstance(policy, Mapping)
    ):
        raise ValueError("RoFormer source verification evidence is incomplete")
    return {
        "schema": value["schema"],
        "status": value["status"],
        "revision_claim": value["revision_claim"],
        "revision_verified_by_git": value.get("revision_verified_by_git"),
        "manifest": dict(manifest),
        "files": files,
        "static_source_policy": dict(policy),
        "package_initializer_executed": False,
        "model_import_permitted": False,
        "effects": dict(effects),
    }


def _read_repository_evidence(
    value: str | Path,
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    root = Path(value).expanduser().absolute()
    before = root.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
        raise ValueError("RoFormer repository root must be a non-symlink directory")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(root, flags)
    try:
        os.set_inheritable(descriptor, False)
        opened = os.fstat(descriptor)
        if os.get_inheritable(descriptor) or _directory_identity(opened) != (
            _directory_identity(before)
        ):
            raise ValueError("RoFormer repository root changed before admission")
        files: list[dict[str, Any]] = []
        contents: dict[str, bytes] = {}
        for name, expected in _EXPECTED_FILES.items():
            report, data = _read_exact_file(descriptor, name, expected)
            files.append(report)
            contents[name] = data
        after = root.lstat()
        if _directory_identity(after) != _directory_identity(before):
            raise ValueError("RoFormer repository root changed during admission")
    finally:
        os.close(descriptor)
    return files, contents


def _read_exact_file(
    directory: int, name: str, expected: Mapping[str, object]
) -> tuple[dict[str, Any], bytes]:
    attached = os.stat(name, dir_fd=directory, follow_symlinks=False)
    expected_bytes = expected["bytes"]
    expected_sha256 = expected["sha256"]
    maximum_bytes = expected["maximum_bytes"]
    if not stat.S_ISREG(attached.st_mode) or stat.S_ISLNK(attached.st_mode):
        raise ValueError(f"RoFormer repository evidence is unsafe: {name}")
    if attached.st_size != expected_bytes or attached.st_size > maximum_bytes:
        raise ValueError(f"RoFormer repository evidence size differs: {name}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(name, flags, dir_fd=directory)
    try:
        os.set_inheritable(descriptor, False)
        opened = os.fstat(descriptor)
        if os.get_inheritable(descriptor) or _file_identity(opened) != _file_identity(
            attached
        ):
            raise ValueError(f"RoFormer repository evidence changed: {name}")
        data = bytearray()
        digest = hashlib.sha256()
        while block := os.read(descriptor, 1024 * 1024):
            data.extend(block)
            digest.update(block)
            if len(data) > maximum_bytes:
                raise ValueError(f"RoFormer repository evidence exceeds bound: {name}")
        after = os.fstat(descriptor)
        rebound = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if _file_identity(after) != _file_identity(opened) or _file_identity(
            rebound
        ) != _file_identity(opened):
            raise ValueError(f"RoFormer repository evidence changed: {name}")
    finally:
        os.close(descriptor)
    observed_sha256 = digest.hexdigest()
    if len(data) != expected_bytes or observed_sha256 != expected_sha256:
        raise ValueError(f"RoFormer repository evidence hash differs: {name}")
    return {
        "path": name,
        "bytes": len(data),
        "sha256": observed_sha256,
        "regular_file": True,
        "symlink": False,
    }, bytes(data)


def _parse_object(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"RoFormer {label} is invalid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"RoFormer {label} must be a JSON object")
    return value


def _parse_requirement_packages(data: bytes, label: str) -> tuple[str, ...]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"RoFormer {label} is not UTF-8") from error
    packages: list[str] = []
    for line in text.splitlines():
        match = _PACKAGE_LINE.match(line)
        if match:
            packages.append(_normalise_package_name(match.group(1)))
    if not packages or len(packages) != len(set(packages)):
        raise ValueError(f"RoFormer {label} package pins are invalid")
    return tuple(packages)


def _verify_source_manifest(
    manifest: Mapping[str, Any], source: Mapping[str, Any]
) -> None:
    if manifest.get("schema") != "sunofriend.private-roformer-source-manifest.v2":
        raise ValueError("RoFormer source manifest schema differs")
    if manifest.get("revision") != SOURCE_REVISION:
        raise ValueError("RoFormer source manifest revision differs")
    if (
        manifest.get("package_initializer_permitted") is not False
        or manifest.get("model_import_permitted_by_manifest") is not False
    ):
        raise ValueError("RoFormer source manifest execution policy differs")
    if manifest.get("static_source_policy", {}).get("analysis_executes_source") is not (
        False
    ):
        raise ValueError("RoFormer source manifest analysis policy differs")
    manifest_files = manifest.get("files")
    source_files = source.get("files")
    if not isinstance(manifest_files, list) or not isinstance(source_files, list):
        raise ValueError("RoFormer source file evidence is incomplete")
    manifest_by_path = {item.get("path"): item for item in manifest_files}
    source_by_path = {item.get("path"): item for item in source_files}
    if set(manifest_by_path) != set(source_by_path) or len(manifest_by_path) != 3:
        raise ValueError("RoFormer source manifest file set differs")
    for path, expected in manifest_by_path.items():
        observed = source_by_path[path]
        if observed.get("bytes") != expected.get("bytes") or observed.get(
            "sha256"
        ) != expected.get("sha256"):
            raise ValueError(f"RoFormer verified source differs from manifest: {path}")
        if expected.get("kind") == "runtime_module":
            roots = observed.get("static_analysis", {}).get("direct_import_roots")
            if roots != expected.get("direct_import_roots"):
                raise ValueError(f"RoFormer verified import roots differ: {path}")


def _verify_runtime_evidence(
    audit: Mapping[str, Any],
    *,
    direct_packages: tuple[str, ...],
    locked_packages: tuple[str, ...],
) -> None:
    if len(direct_packages) != 6 or len(locked_packages) != 15:
        raise ValueError("RoFormer runtime package count differs")
    if not set(direct_packages).issubset(locked_packages):
        raise ValueError("RoFormer direct runtime packages are not lock-contained")
    if audit.get("schema") != "sunofriend.private-runtime-license-audit.v1":
        raise ValueError("RoFormer runtime licence-audit schema differs")
    scope = audit.get("scope")
    finding = audit.get("finding")
    packages = audit.get("packages")
    if (
        not isinstance(scope, Mapping)
        or not isinstance(finding, Mapping)
        or not isinstance(packages, list)
    ):
        raise ValueError("RoFormer runtime licence evidence is incomplete")
    if scope.get("requirements_input_sha256") != RUNTIME_DEPENDENCY_INPUT_SHA256 or (
        scope.get("requirements_lock_sha256") != RUNTIME_DEPENDENCY_LOCK_SHA256
    ):
        raise ValueError("RoFormer runtime licence-audit binding differs")
    if (
        scope.get("resolved_packages") != 15
        or scope.get("installation_performed") is not False
    ):
        raise ValueError("RoFormer runtime licence-audit scope differs")
    audited_packages = tuple(
        _normalise_package_name(item.get("name", ""))
        for item in packages
        if isinstance(item, Mapping)
    )
    if len(audited_packages) != len(packages) or set(audited_packages) != set(
        locked_packages
    ):
        raise ValueError("RoFormer locked-package licence coverage differs")
    required_findings = {
        "status": "complete_for_private_local_evaluation",
        "all_locked_packages_accounted_for": True,
        "all_primary_licenses_allow_private_local_evaluation": True,
        "runtime_installation_permitted_by_this_audit": False,
        "checkpoint_terms_covered": False,
        "redistribution_review_required": True,
    }
    if any(finding.get(key) != expected for key, expected in required_findings.items()):
        raise ValueError("RoFormer runtime licence-audit finding differs")


def _normalise_package_name(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("RoFormer runtime package name is invalid")
    return _NORMALIZE_PACKAGE.sub("-", value).lower()


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


__all__ = [
    "ROFORMER_ADMISSION_POLICY",
    "ROFORMER_ADMISSION_SCHEMA",
    "_admission_sha256",
    "_build_private_roformer_admission",
]
