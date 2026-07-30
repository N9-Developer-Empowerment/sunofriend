"""Pure provenance contract for one measured separation runtime.

The filesystem-facing parent measures the launcher, virtual environment and
registered worker inputs, then passes plain data to this module.  This module
only validates, canonicalises, hashes and deep-freezes that data.  It performs
no filesystem access, starts no process, imports no backend and uses no
network.

Static backend preflight v1 does not register a runtime-artifact hash.
Consequently every v1 document produced here is explicitly private
development evidence and is never acceptance or promotion evidence.
"""

from __future__ import annotations

import hashlib
import posixpath
import re
import stat
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .separation_acceptance import canonical_json_bytes
from .separation_worker_contract import SeparationRuntimeArtifactIdentity


SEPARATION_RUNTIME_ARTIFACT_SCHEMA = "sunofriend.separation-runtime-artifact.v1"
SEPARATION_RUNTIME_ARTIFACT_STATUS = "private_development_unregistered"
SEPARATION_RUNTIME_LAUNCHER_CHAIN_ALGORITHM = "canonical-launcher-chain-sha256-v1"
SEPARATION_RUNTIME_PACKAGE_TREE_ALGORITHM = "installed-package-tree-sha256-v1"
SEPARATION_RUNTIME_REGISTRATION_REASON = (
    "static-preflight-v1-lacks-runtime-artifact-sha256"
)

MAX_RUNTIME_CHAIN_ENTRIES = 8
MAX_RUNTIME_ANCESTOR_DIRECTORIES = 256
MAX_RUNTIME_FILE_BYTES = 16 * 1024 * 1024 * 1024
MAX_RUNTIME_PATH_BYTES = 4096
_MAX_STAT_INTEGER = (1 << 63) - 1

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PYTHON_LAUNCHER_RE = re.compile(r"^python(?:3(?:\.[0-9]+)?)?$")
_PYTHON_SITE_RE = re.compile(r"^python3\.(?:9|10|11|12)$")
_URL_RE = re.compile(r"(?:[A-Za-z][A-Za-z0-9+.-]*://|www\.)")

_TOP_FIELDS = frozenset(
    {
        "schema",
        "status",
        "acceptance_eligible",
        "artifact_sha256",
        "bindings",
        "registration",
        "runtime",
        "files",
    }
)
_BINDING_FIELDS = frozenset(
    {
        "worker_request_sha256",
        "preflight_sha256",
        "parent_measurements_sha256",
        "trusted_runtime_identity",
    }
)
_IDENTITY_FIELDS = frozenset(
    {
        "path",
        "sha256",
        "bytes",
        "verified_launcher_chain_sha256",
    }
)
_REGISTRATION_FIELDS = frozenset(
    {
        "static_preflight_schema",
        "runtime_artifact_sha256_registered",
        "reason_code",
        "evidence_kind",
        "execution_proven",
        "toctou_closed",
        "remeasure_before_exec_required",
    }
)
_RUNTIME_FIELDS = frozenset(
    {
        "venv_root",
        "launcher_chain_algorithm",
        "launcher_chain_sha256",
        "launcher_chain",
        "ancestor_directories",
        "final_native_executable",
        "pyvenv_config",
        "site_packages",
    }
)
_CHAIN_FIELDS = frozenset(
    {
        "canonical_path",
        "kind",
        "lstat",
        "raw_target",
        "canonical_resolved_target",
    }
)
_LSTAT_FIELDS = frozenset({"device", "inode", "mode", "size", "mtime_ns", "ctime_ns"})
_FILE_FIELDS = frozenset({"path", "kind", "sha256", "bytes", "lstat"})
_SITE_FIELDS = frozenset(
    {
        "path",
        "kind",
        "lstat",
        "package_tree_algorithm",
        "package_tree_sha256",
    }
)
_FILES_FIELDS = frozenset({"worker", "dependency_lock"})
_ANCESTOR_FIELDS = frozenset(
    {"canonical_path", "kind", "lstat", "canonical_resolved_path"}
)


@dataclass(frozen=True)
class SeparationRuntimeArtifactParentEvidence:
    """Exact parent-owned binding to all pre-execution measurements.

    This is contract evidence, not proof that the same nodes will be used by a
    later exec.  The launch boundary must remeasure and bind this digest.
    """

    worker_request_sha256: str
    preflight_sha256: str
    measurements_sha256: str

    def __post_init__(self) -> None:
        _sha256(self.worker_request_sha256, "parent worker request sha256")
        _sha256(self.preflight_sha256, "parent preflight sha256")
        _sha256(self.measurements_sha256, "parent measurements sha256")


def build_separation_runtime_artifact(
    *,
    launcher_chain: Sequence[Mapping[str, Any]],
    ancestor_directories: Sequence[Mapping[str, Any]],
    final_native_executable: Mapping[str, Any],
    pyvenv_config: Mapping[str, Any],
    site_packages: Mapping[str, Any],
    worker: Mapping[str, Any],
    dependency_lock: Mapping[str, Any],
    worker_request_sha256: str,
    preflight_sha256: str,
    trusted_runtime_artifact: SeparationRuntimeArtifactIdentity,
    trusted_parent_evidence: SeparationRuntimeArtifactParentEvidence,
) -> Mapping[str, Any]:
    """Build immutable private runtime evidence from parent measurements."""

    trusted = _trusted_identity(trusted_runtime_artifact)
    chain = _validate_launcher_chain(launcher_chain)
    ancestors = _validate_ancestor_directories(ancestor_directories)
    chain_hash = separation_runtime_launcher_chain_sha256(chain)
    final = _validate_file(
        final_native_executable,
        "final native executable",
        expected_kind="native_executable",
    )
    config = _validate_file(
        pyvenv_config,
        "pyvenv config",
        expected_kind="regular_file",
    )
    site = _validate_site_packages(site_packages)
    checked_worker = _validate_file(worker, "worker", expected_kind="regular_file")
    checked_lock = _validate_file(
        dependency_lock,
        "dependency lock",
        expected_kind="regular_file",
    )
    _validate_runtime_relationships(
        chain=chain,
        ancestors=ancestors,
        final=final,
        config=config,
        site=site,
        worker=checked_worker,
        dependency_lock=checked_lock,
        trusted=trusted,
        chain_hash=chain_hash,
    )
    measurements_hash = separation_runtime_measurements_sha256(
        launcher_chain=chain,
        ancestor_directories=ancestors,
        final_native_executable=final,
        pyvenv_config=config,
        site_packages=site,
        worker=checked_worker,
        dependency_lock=checked_lock,
    )
    parent_evidence = _trusted_parent_evidence(trusted_parent_evidence)
    worker_request_hash = _sha256(worker_request_sha256, "worker request sha256")
    preflight_hash = _sha256(preflight_sha256, "preflight sha256")
    if (
        parent_evidence.worker_request_sha256 != worker_request_hash
        or parent_evidence.preflight_sha256 != preflight_hash
        or parent_evidence.measurements_sha256 != measurements_hash
    ):
        raise ValueError("runtime measurements do not bind parent-owned evidence")
    payload = {
        "schema": SEPARATION_RUNTIME_ARTIFACT_SCHEMA,
        "status": SEPARATION_RUNTIME_ARTIFACT_STATUS,
        "acceptance_eligible": False,
        "bindings": {
            "worker_request_sha256": worker_request_hash,
            "preflight_sha256": preflight_hash,
            "parent_measurements_sha256": measurements_hash,
            "trusted_runtime_identity": _identity_document(trusted),
        },
        "registration": {
            "static_preflight_schema": ("sunofriend.separation-backend-preflight.v1"),
            "runtime_artifact_sha256_registered": False,
            "reason_code": SEPARATION_RUNTIME_REGISTRATION_REASON,
            "evidence_kind": "parent_asserted_contract_evidence",
            "execution_proven": False,
            "toctou_closed": False,
            "remeasure_before_exec_required": True,
        },
        "runtime": {
            "venv_root": _venv_root(chain[0]["canonical_path"]),
            "launcher_chain_algorithm": (SEPARATION_RUNTIME_LAUNCHER_CHAIN_ALGORITHM),
            "launcher_chain_sha256": chain_hash,
            "launcher_chain": chain,
            "ancestor_directories": ancestors,
            "final_native_executable": final,
            "pyvenv_config": config,
            "site_packages": site,
        },
        "files": {
            "worker": checked_worker,
            "dependency_lock": checked_lock,
        },
    }
    document = {
        **payload,
        "artifact_sha256": _canonical_hash(payload),
    }
    return validate_separation_runtime_artifact(
        document,
        trusted_runtime_artifact=trusted,
        trusted_parent_evidence=parent_evidence,
        trusted_worker_request_sha256=worker_request_sha256,
        trusted_preflight_sha256=preflight_sha256,
    )


def validate_separation_runtime_artifact(
    document: Mapping[str, Any],
    *,
    trusted_runtime_artifact: SeparationRuntimeArtifactIdentity,
    trusted_parent_evidence: SeparationRuntimeArtifactParentEvidence,
    trusted_worker_request_sha256: str,
    trusted_preflight_sha256: str,
) -> Mapping[str, Any]:
    """Validate and deep-freeze runtime evidence against parent bindings."""

    value = _plain_mapping(document, "runtime artifact")
    _exact_fields(value, _TOP_FIELDS, "runtime artifact")
    _reject_invalid_tree(value, "runtime artifact")
    if value["schema"] != SEPARATION_RUNTIME_ARTIFACT_SCHEMA:
        raise ValueError("unsupported runtime artifact schema")
    if value["status"] != SEPARATION_RUNTIME_ARTIFACT_STATUS:
        raise ValueError("runtime artifact status must remain private development")
    if value["acceptance_eligible"] is not False:
        raise ValueError("runtime artifact v1 is never acceptance eligible")

    trusted = _trusted_identity(trusted_runtime_artifact)
    parent_evidence = _trusted_parent_evidence(trusted_parent_evidence)
    bindings = _plain_mapping(value["bindings"], "bindings")
    _exact_fields(bindings, _BINDING_FIELDS, "bindings")
    expected_worker_request = _sha256(
        trusted_worker_request_sha256, "trusted worker request sha256"
    )
    expected_preflight = _sha256(trusted_preflight_sha256, "trusted preflight sha256")
    if (
        _sha256(
            bindings["worker_request_sha256"],
            "bindings.worker_request_sha256",
        )
        != expected_worker_request
        or _sha256(bindings["preflight_sha256"], "bindings.preflight_sha256")
        != expected_preflight
    ):
        raise ValueError(
            "runtime artifact does not bind the trusted request and preflight"
        )
    if (
        parent_evidence.worker_request_sha256 != expected_worker_request
        or parent_evidence.preflight_sha256 != expected_preflight
        or _sha256(
            bindings["parent_measurements_sha256"],
            "bindings.parent_measurements_sha256",
        )
        != parent_evidence.measurements_sha256
    ):
        raise ValueError("runtime artifact does not bind parent-owned evidence")
    identity = _validate_identity_document(bindings["trusted_runtime_identity"])
    if identity != _identity_document(trusted):
        raise ValueError("runtime artifact contains a resigned runtime identity")

    registration = _plain_mapping(value["registration"], "registration")
    _exact_fields(registration, _REGISTRATION_FIELDS, "registration")
    expected_registration = {
        "static_preflight_schema": ("sunofriend.separation-backend-preflight.v1"),
        "runtime_artifact_sha256_registered": False,
        "reason_code": SEPARATION_RUNTIME_REGISTRATION_REASON,
        "evidence_kind": "parent_asserted_contract_evidence",
        "execution_proven": False,
        "toctou_closed": False,
        "remeasure_before_exec_required": True,
    }
    if registration != expected_registration:
        raise ValueError("runtime artifact registration boundary is invalid")

    runtime = _plain_mapping(value["runtime"], "runtime")
    _exact_fields(runtime, _RUNTIME_FIELDS, "runtime")
    chain = _validate_launcher_chain(runtime["launcher_chain"])
    ancestors = _validate_ancestor_directories(runtime["ancestor_directories"])
    if runtime["launcher_chain_algorithm"] != (
        SEPARATION_RUNTIME_LAUNCHER_CHAIN_ALGORITHM
    ):
        raise ValueError("launcher chain algorithm is unsupported")
    chain_hash = separation_runtime_launcher_chain_sha256(chain)
    if _sha256(runtime["launcher_chain_sha256"], "launcher chain sha256") != chain_hash:
        raise ValueError("launcher chain hash does not match facts")
    if runtime["venv_root"] != _venv_root(chain[0]["canonical_path"]):
        raise ValueError("runtime venv root does not bind launcher")

    final = _validate_file(
        runtime["final_native_executable"],
        "final native executable",
        expected_kind="native_executable",
    )
    config = _validate_file(
        runtime["pyvenv_config"],
        "pyvenv config",
        expected_kind="regular_file",
    )
    site = _validate_site_packages(runtime["site_packages"])
    files = _plain_mapping(value["files"], "files")
    _exact_fields(files, _FILES_FIELDS, "files")
    worker = _validate_file(files["worker"], "worker", expected_kind="regular_file")
    dependency_lock = _validate_file(
        files["dependency_lock"],
        "dependency lock",
        expected_kind="regular_file",
    )
    _validate_runtime_relationships(
        chain=chain,
        ancestors=ancestors,
        final=final,
        config=config,
        site=site,
        worker=worker,
        dependency_lock=dependency_lock,
        trusted=trusted,
        chain_hash=chain_hash,
    )
    measurements_hash = separation_runtime_measurements_sha256(
        launcher_chain=chain,
        ancestor_directories=ancestors,
        final_native_executable=final,
        pyvenv_config=config,
        site_packages=site,
        worker=worker,
        dependency_lock=dependency_lock,
    )
    if (
        measurements_hash != parent_evidence.measurements_sha256
        or measurements_hash != bindings["parent_measurements_sha256"]
    ):
        raise ValueError("runtime artifact measurements were changed or resigned")

    artifact_hash = _sha256(value["artifact_sha256"], "artifact sha256")
    if artifact_hash != separation_runtime_artifact_sha256(value):
        raise ValueError("runtime artifact self-hash does not match document")
    return _freeze_json(value)


def separation_runtime_artifact_sha256(
    document: Mapping[str, Any],
) -> str:
    """Hash an artifact excluding only its canonical self-hash field."""

    value = _plain_mapping(document, "runtime artifact")
    value.pop("artifact_sha256", None)
    _reject_invalid_tree(value, "runtime artifact")
    return _canonical_hash(value)


def separation_runtime_launcher_chain_sha256(
    launcher_chain: Sequence[Mapping[str, Any]],
) -> str:
    """Return the canonical hash for one validated launcher chain."""

    chain = _validate_launcher_chain(launcher_chain)
    return hashlib.sha256(canonical_json_bytes(chain)).hexdigest()


def separation_runtime_measurements_sha256(
    *,
    launcher_chain: Sequence[Mapping[str, Any]],
    ancestor_directories: Sequence[Mapping[str, Any]],
    final_native_executable: Mapping[str, Any],
    pyvenv_config: Mapping[str, Any],
    site_packages: Mapping[str, Any],
    worker: Mapping[str, Any],
    dependency_lock: Mapping[str, Any],
) -> str:
    """Hash every exact parent measurement required by the launch boundary."""

    chain = _validate_launcher_chain(launcher_chain)
    ancestors = _validate_ancestor_directories(ancestor_directories)
    final = _validate_file(
        final_native_executable,
        "final native executable",
        expected_kind="native_executable",
    )
    config = _validate_file(
        pyvenv_config,
        "pyvenv config",
        expected_kind="regular_file",
    )
    site = _validate_site_packages(site_packages)
    checked_worker = _validate_file(worker, "worker", expected_kind="regular_file")
    checked_lock = _validate_file(
        dependency_lock,
        "dependency lock",
        expected_kind="regular_file",
    )
    payload = {
        "launcher_chain": chain,
        "ancestor_directories": ancestors,
        "final_native_executable": final,
        "pyvenv_config": config,
        "site_packages": site,
        "worker": checked_worker,
        "dependency_lock": checked_lock,
    }
    return _canonical_hash(payload)


def _validate_ancestor_directories(
    value: Any,
) -> list[dict[str, Any]]:
    if (
        not isinstance(value, (list, tuple))
        or isinstance(value, str)
        or not 1 <= len(value) <= MAX_RUNTIME_ANCESTOR_DIRECTORIES
    ):
        raise ValueError("ancestor directories must contain between 1 and 256 entries")
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        item = _plain_mapping(raw, f"ancestor directories[{index}]")
        _exact_fields(item, _ANCESTOR_FIELDS, f"ancestor directories[{index}]")
        path = _absolute_directory_path(
            item["canonical_path"],
            f"ancestor directories[{index}].canonical_path",
        )
        resolved = _absolute_directory_path(
            item["canonical_resolved_path"],
            f"ancestor directories[{index}].canonical_resolved_path",
        )
        if item["kind"] != "directory":
            raise ValueError("every ancestor must be an observed directory")
        facts = _lstat(item["lstat"], f"ancestor directories[{index}].lstat")
        _facts_match_kind(facts, "directory", f"ancestor directories[{index}]")
        if resolved != path:
            raise ValueError("ancestor directory contains a symlink or resolved alias")
        result.append(
            {
                "canonical_path": path,
                "kind": "directory",
                "lstat": facts,
                "canonical_resolved_path": resolved,
            }
        )
    paths = [item["canonical_path"] for item in result]
    _alias_free(paths, "ancestor directories")
    expected_order = sorted(
        result,
        key=lambda item: (
            len(PurePosixPath(item["canonical_path"]).parts),
            item["canonical_path"],
        ),
    )
    if result != expected_order:
        raise ValueError("ancestor directories are not in canonical order")
    return result


def _validate_launcher_chain(
    value: Any,
) -> list[dict[str, Any]]:
    if (
        not isinstance(value, (list, tuple))
        or isinstance(value, str)
        or not 1 <= len(value) <= MAX_RUNTIME_CHAIN_ENTRIES
    ):
        raise ValueError("launcher chain must contain between 1 and 8 entries")
    chain: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        entry = _plain_mapping(raw, f"launcher chain[{index}]")
        _exact_fields(entry, _CHAIN_FIELDS, f"launcher chain[{index}]")
        path = _absolute_path(
            entry["canonical_path"],
            f"launcher chain[{index}].canonical_path",
        )
        kind = entry["kind"]
        expected_kind = "native_executable" if index == len(value) - 1 else "symlink"
        if kind != expected_kind:
            raise ValueError("launcher chain must end in exactly one native executable")
        facts = _lstat(entry["lstat"], f"launcher chain[{index}].lstat")
        _facts_match_kind(facts, kind, f"launcher chain[{index}]")
        target = _absolute_path(
            entry["canonical_resolved_target"],
            f"launcher chain[{index}].canonical_resolved_target",
        )
        raw_target = entry["raw_target"]
        if kind == "symlink":
            raw_target = _raw_symlink_target(
                raw_target, f"launcher chain[{index}].raw_target"
            )
            resolved = _resolve_target(path, raw_target)
            if resolved != target:
                raise ValueError(
                    "symlink raw target does not match canonical resolved target"
                )
        else:
            if raw_target is not None or target != path:
                raise ValueError(
                    "final native executable cannot contain a symlink target"
                )
        chain.append(
            {
                "canonical_path": path,
                "kind": kind,
                "lstat": facts,
                "raw_target": raw_target,
                "canonical_resolved_target": target,
            }
        )

    paths = [item["canonical_path"] for item in chain]
    _alias_free(paths, "launcher chain")
    for index, entry in enumerate(chain[:-1]):
        if entry["canonical_resolved_target"] != chain[index + 1]["canonical_path"]:
            raise ValueError("launcher chain target does not bind the next entry")
    first = PurePosixPath(paths[0])
    if (
        first.parent.name != "bin"
        or not _PYTHON_LAUNCHER_RE.fullmatch(first.name)
        or first.parent.parent == PurePosixPath("/")
    ):
        raise ValueError("launcher is not a bounded virtual-environment Python")
    return chain


def _validate_file(
    value: Any,
    label: str,
    *,
    expected_kind: str,
) -> dict[str, Any]:
    item = _plain_mapping(value, label)
    _exact_fields(item, _FILE_FIELDS, label)
    path = _absolute_path(item["path"], f"{label}.path")
    if item["kind"] != expected_kind:
        raise ValueError(f"{label} kind is invalid")
    facts = _lstat(item["lstat"], f"{label}.lstat")
    _facts_match_kind(facts, expected_kind, label)
    byte_count = _bytes(item["bytes"], f"{label}.bytes")
    if facts["size"] != byte_count:
        raise ValueError(f"{label} bytes do not match lstat facts")
    return {
        "path": path,
        "kind": expected_kind,
        "sha256": _sha256(item["sha256"], f"{label}.sha256"),
        "bytes": byte_count,
        "lstat": facts,
    }


def _validate_site_packages(value: Any) -> dict[str, Any]:
    item = _plain_mapping(value, "site packages")
    _exact_fields(item, _SITE_FIELDS, "site packages")
    if item["kind"] != "directory":
        raise ValueError("site packages kind must be directory")
    facts = _lstat(item["lstat"], "site packages.lstat")
    _facts_match_kind(facts, "directory", "site packages")
    if item["package_tree_algorithm"] != (SEPARATION_RUNTIME_PACKAGE_TREE_ALGORITHM):
        raise ValueError("site package-tree algorithm is unsupported")
    return {
        "path": _absolute_path(item["path"], "site packages.path"),
        "kind": "directory",
        "lstat": facts,
        "package_tree_algorithm": (SEPARATION_RUNTIME_PACKAGE_TREE_ALGORITHM),
        "package_tree_sha256": _sha256(
            item["package_tree_sha256"], "site package-tree sha256"
        ),
    }


def _validate_runtime_relationships(
    *,
    chain: Sequence[Mapping[str, Any]],
    ancestors: Sequence[Mapping[str, Any]],
    final: Mapping[str, Any],
    config: Mapping[str, Any],
    site: Mapping[str, Any],
    worker: Mapping[str, Any],
    dependency_lock: Mapping[str, Any],
    trusted: SeparationRuntimeArtifactIdentity,
    chain_hash: str,
) -> None:
    launcher_path = chain[0]["canonical_path"]
    final_entry = chain[-1]
    if final["path"] != final_entry["canonical_path"]:
        raise ValueError("final executable does not bind launcher chain")
    if final["lstat"] != final_entry["lstat"]:
        raise ValueError("final executable facts changed after chain measurement")
    if (
        str(trusted.path) != launcher_path
        or trusted.sha256 != final["sha256"]
        or trusted.bytes != final["bytes"]
        or trusted.verified_launcher_chain_sha256 != chain_hash
    ):
        raise ValueError("runtime measurements do not bind trusted runtime identity")

    root = _venv_root(launcher_path)
    if config["path"] != f"{root}/pyvenv.cfg":
        raise ValueError("pyvenv config escapes the virtual environment")
    site_path = PurePosixPath(site["path"])
    try:
        relative_site = site_path.relative_to(PurePosixPath(root))
    except ValueError as exc:
        raise ValueError("site packages escapes the virtual environment") from exc
    if (
        len(relative_site.parts) != 3
        or relative_site.parts[0] != "lib"
        or not _PYTHON_SITE_RE.fullmatch(relative_site.parts[1])
        or relative_site.parts[2] != "site-packages"
    ):
        raise ValueError("site packages path is not canonical for the venv")

    logical_paths = [
        *(item["canonical_path"] for item in chain),
        config["path"],
        site["path"],
        worker["path"],
        dependency_lock["path"],
    ]
    _alias_free(logical_paths, "runtime artifact paths")
    ancestor_paths = {item["canonical_path"] for item in ancestors}
    expected_ancestors: set[str] = set()
    for leaf in logical_paths:
        parent = PurePosixPath(leaf).parent
        while True:
            expected_ancestors.add(parent.as_posix())
            if parent == PurePosixPath("/"):
                break
            parent = parent.parent
    if ancestor_paths != expected_ancestors:
        raise ValueError("ancestor directory evidence is incomplete or contains extras")

    nodes: list[tuple[str, Mapping[str, int]]] = [
        *((item["canonical_path"], item["lstat"]) for item in chain),
        *((item["canonical_path"], item["lstat"]) for item in ancestors),
        (config["path"], config["lstat"]),
        (site["path"], site["lstat"]),
        (worker["path"], worker["lstat"]),
        (dependency_lock["path"], dependency_lock["lstat"]),
    ]
    seen_nodes: dict[tuple[int, int], str] = {}
    for path, facts in nodes:
        node = (facts["device"], facts["inode"])
        previous = seen_nodes.get(node)
        if previous is not None:
            raise ValueError(
                "runtime artifact contains a hardlink, firmlink or inode alias"
            )
        seen_nodes[node] = path


def _validate_identity_document(value: Any) -> dict[str, Any]:
    identity = _plain_mapping(value, "trusted runtime identity")
    _exact_fields(identity, _IDENTITY_FIELDS, "trusted runtime identity")
    chain_hash = identity["verified_launcher_chain_sha256"]
    if chain_hash is None:
        raise ValueError("trusted runtime identity requires a launcher chain")
    return {
        "path": _absolute_path(identity["path"], "runtime identity.path"),
        "sha256": _sha256(identity["sha256"], "runtime identity.sha256"),
        "bytes": _bytes(identity["bytes"], "runtime identity.bytes"),
        "verified_launcher_chain_sha256": _sha256(
            chain_hash, "runtime identity launcher chain sha256"
        ),
    }


def _trusted_identity(
    value: Any,
) -> SeparationRuntimeArtifactIdentity:
    if type(value) is not SeparationRuntimeArtifactIdentity:
        raise ValueError(
            "trusted runtime artifact must be a parent-owned exact identity"
        )
    document = _validate_identity_document(_identity_document(value))
    if Path(document["path"]) != value.path:
        raise ValueError("trusted runtime artifact path is not canonical")
    return value


def _trusted_parent_evidence(
    value: Any,
) -> SeparationRuntimeArtifactParentEvidence:
    if type(value) is not SeparationRuntimeArtifactParentEvidence:
        raise ValueError(
            "trusted parent evidence must be a parent-owned exact identity"
        )
    _sha256(value.worker_request_sha256, "parent worker request sha256")
    _sha256(value.preflight_sha256, "parent preflight sha256")
    _sha256(value.measurements_sha256, "parent measurements sha256")
    return value


def _identity_document(
    value: SeparationRuntimeArtifactIdentity,
) -> dict[str, Any]:
    return {
        "path": str(value.path),
        "sha256": value.sha256,
        "bytes": value.bytes,
        "verified_launcher_chain_sha256": (value.verified_launcher_chain_sha256),
    }


def _venv_root(launcher_path: str) -> str:
    launcher = PurePosixPath(_absolute_path(launcher_path, "runtime launcher path"))
    return launcher.parent.parent.as_posix()


def _resolve_target(link_path: str, raw_target: str) -> str:
    if raw_target.startswith("/"):
        resolved = posixpath.normpath(raw_target)
    else:
        resolved = posixpath.normpath(
            posixpath.join(posixpath.dirname(link_path), raw_target)
        )
    if resolved == "/":
        raise ValueError("symlink target escapes the bounded runtime")
    return _absolute_path(resolved, "resolved symlink target")


def _raw_symlink_target(value: Any, label: str) -> str:
    text = _text(value, label)
    if (
        len(text.encode("utf-8")) > MAX_RUNTIME_PATH_BYTES
        or text.startswith("~")
        or text.endswith("/")
        or "\\" in text
        or "//" in text
        or _URL_RE.search(text)
        or unicodedata.normalize("NFC", text) != text
    ):
        raise ValueError(f"{label} is unsafe")
    path = PurePosixPath(text)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} contains a path alias or upward escape")
    return text


def _absolute_path(value: Any, label: str) -> str:
    text = _text(value, label)
    path = PurePosixPath(text)
    if (
        len(text.encode("utf-8")) > MAX_RUNTIME_PATH_BYTES
        or not text.startswith("/")
        or text == "/"
        or "//" in text
        or "\\" in text
        or _URL_RE.search(text)
        or unicodedata.normalize("NFC", text) != text
        or str(path) != text
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"{label} is not a canonical absolute local path")
    return text


def _absolute_directory_path(value: Any, label: str) -> str:
    if value == "/":
        return "/"
    return _absolute_path(value, label)


def _alias_free(paths: Sequence[str], label: str) -> None:
    aliases = [unicodedata.normalize("NFC", path).casefold() for path in paths]
    if len(aliases) != len(set(aliases)):
        raise ValueError(f"{label} contains a cycle or NFC/casefold path alias")


def _lstat(value: Any, label: str) -> dict[str, int]:
    facts = _plain_mapping(value, label)
    _exact_fields(facts, _LSTAT_FIELDS, label)
    checked: dict[str, int] = {}
    for key in (
        "device",
        "inode",
        "mode",
        "size",
        "mtime_ns",
        "ctime_ns",
    ):
        number = _strict_int(facts[key], f"{label}.{key}")
        if not 0 <= number <= _MAX_STAT_INTEGER:
            raise ValueError(f"{label}.{key} is outside supported bounds")
        checked[key] = number
    if checked["device"] == 0 or checked["inode"] == 0:
        raise ValueError(f"{label} must identify a concrete filesystem node")
    return checked


def _facts_match_kind(facts: Mapping[str, int], kind: str, label: str) -> None:
    mode = facts["mode"]
    if kind == "symlink":
        matches = stat.S_ISLNK(mode)
    elif kind in {"regular_file", "native_executable"}:
        matches = stat.S_ISREG(mode)
        if kind == "native_executable":
            matches = matches and bool(mode & 0o111)
    elif kind == "directory":
        matches = stat.S_ISDIR(mode)
    else:
        matches = False
    if not matches:
        raise ValueError(f"{label} kind does not match lstat mode")


def _bytes(value: Any, label: str) -> int:
    number = _strict_int(value, label)
    if not 0 < number <= MAX_RUNTIME_FILE_BYTES:
        raise ValueError(f"{label} is outside supported bounds")
    return number


def _sha256(value: Any, label: str) -> str:
    text = _text(value, label)
    if not _SHA256_RE.fullmatch(text):
        raise ValueError(f"{label} is not a lowercase SHA-256")
    return text


def _strict_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _text(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\0" in value
    ):
        raise ValueError(f"{label} must be canonical non-empty text")
    return value


def _plain_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return {key: _plain_json(item) for key, item in value.items()}


def _plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    return value


def _exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    if set(value) != set(expected):
        raise ValueError(f"{label} fields are invalid")


def _reject_invalid_tree(value: Any, label: str) -> None:
    if isinstance(value, Mapping):
        folded: set[str] = set()
        for key, item in value.items():
            if (
                not isinstance(key, str)
                or not key
                or key != key.strip()
                or unicodedata.normalize("NFC", key) != key
            ):
                raise ValueError(f"{label} contains an invalid object key")
            alias = key.casefold()
            if alias in folded:
                raise ValueError(f"{label} contains aliased object keys")
            folded.add(alias)
            _reject_invalid_tree(item, f"{label}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_invalid_tree(item, f"{label}[{index}]")
    elif isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value or "\0" in value:
            raise ValueError(f"{label} contains invalid text")
    elif isinstance(value, bool) or value is None or isinstance(value, int):
        return
    else:
        raise ValueError(f"{label} contains a non-canonical JSON value")


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _canonical_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


__all__ = [
    "MAX_RUNTIME_ANCESTOR_DIRECTORIES",
    "MAX_RUNTIME_CHAIN_ENTRIES",
    "SEPARATION_RUNTIME_ARTIFACT_SCHEMA",
    "SEPARATION_RUNTIME_ARTIFACT_STATUS",
    "SEPARATION_RUNTIME_LAUNCHER_CHAIN_ALGORITHM",
    "SEPARATION_RUNTIME_PACKAGE_TREE_ALGORITHM",
    "SEPARATION_RUNTIME_REGISTRATION_REASON",
    "SeparationRuntimeArtifactParentEvidence",
    "build_separation_runtime_artifact",
    "separation_runtime_artifact_sha256",
    "separation_runtime_launcher_chain_sha256",
    "separation_runtime_measurements_sha256",
    "validate_separation_runtime_artifact",
]
