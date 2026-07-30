"""Read-only parent measurement for a private separation runtime.

This module is the filesystem-facing counterpart of
``separation_runtime_artifact``.  It hashes only the validated runtime,
worker and dependency-lock paths.  It never starts a process, imports a
backend, loads a checkpoint, reads source audio, makes a network API call or
writes.  Filesystem reads still rely on the trusted local-filesystem boundary;
portable metadata cannot identify every network mount or same-device alias.

Remeasurement detects change between two parent observations.  It still does
not prove which nodes a later exec will use; the returned artifact keeps that
TOCTOU boundary explicit.  The runtime tree digest is stability evidence, not
a complete executable import closure: base stdlib/dynamic libraries and the
startup semantics of measured ``.pth`` files remain a later launch boundary.
System site packages are therefore required to be disabled.
Cross-device descendants are rejected; same-device APFS firmlinks or mount
aliases cannot be distinguished by these portable observations and remain an
explicit operating-system boundary.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from .separation_runtime_artifact import (
    MAX_RUNTIME_CHAIN_ENTRIES,
    SEPARATION_RUNTIME_PACKAGE_TREE_ALGORITHM,
    SeparationRuntimeArtifactParentEvidence,
    build_separation_runtime_artifact,
    separation_runtime_launcher_chain_sha256,
    separation_runtime_measurements_sha256,
    validate_separation_runtime_artifact,
)
from .separation_worker_contract import (
    SeparationRuntimeArtifactIdentity,
    validate_separation_worker_request,
)


MAX_RUNTIME_EXECUTABLE_BYTES = 2 * 1024 * 1024 * 1024
MAX_PYVENV_CONFIG_BYTES = 64 * 1024
MAX_WORKER_BYTES = 16 * 1024 * 1024
MAX_DEPENDENCY_LOCK_BYTES = 16 * 1024 * 1024
MAX_SITE_PACKAGE_FILE_BYTES = 256 * 1024 * 1024
MAX_SITE_PACKAGE_TOTAL_BYTES = 4 * 1024 * 1024 * 1024
MAX_SITE_PACKAGE_FILES = 50_000
MAX_SITE_PACKAGE_DIRECTORIES = 20_000
MAX_RUNTIME_PATH_BYTES = 4096
MAX_RUNTIME_PATH_DEPTH = 64

_PYTHON_VERSION_RE = re.compile(r"^3\.(?:9|10|11|12)(?:\.[0-9]+)?$")
_NATIVE_MAGICS = frozenset(
    {
        b"\x7fELF",
        b"\xca\xfe\xba\xbe",
        b"\xca\xfe\xba\xbf",
        b"\xce\xfa\xed\xfe",
        b"\xcf\xfa\xed\xfe",
        b"\xfe\xed\xfa\xce",
        b"\xfe\xed\xfa\xcf",
    }
)


@dataclass(frozen=True, init=False)
class SeparationRuntimeMeasurement:
    """One immutable parent assertion and its validated pure artifact.

    Its in-process authority marker prevents casual construction, but is not
    a sandbox against malicious code already running in the trusted parent.
    """

    parent_evidence: SeparationRuntimeArtifactParentEvidence
    artifact: Mapping[str, Any]
    _authority: object = field(repr=False, compare=False)


@dataclass(frozen=True, init=False)
class SeparationRuntimeTrustedRequest:
    """Parent-owned validated request and its non-overridable runtime paths.

    The authority is a parent-process construction convention.  It rejects
    ordinary mappings and casually fabricated records, but it is not a
    sandbox against malicious code already executing inside that parent.
    """

    request: Mapping[str, Any]
    request_sha256: str
    preflight_sha256: str
    runtime_python_path: Path
    worker_path: Path
    dependency_lock_path: Path
    _authority: object = field(repr=False, compare=False)


@dataclass(frozen=True)
class _ObservedNode:
    path: Path
    facts: tuple[int, int, int, int, int, int]
    kind: str
    raw_target: str | None = None
    resolved_path: str | None = None


@dataclass
class _SiteTreeBudget:
    directories: int = 0
    files: int = 0
    total_bytes: int = 0
    discovered_nodes: int = 1


_TRUSTED_REQUEST_AUTHORITY = object()
_MEASUREMENT_AUTHORITY = object()


class _Registry:
    def __init__(self) -> None:
        self.by_path: dict[str, _ObservedNode] = {}
        self.by_alias: dict[str, str] = {}
        self.by_node: dict[tuple[int, int], str] = {}

    def add(self, observed: _ObservedNode) -> None:
        path = _canonical_path(observed.path, allow_root=True)
        previous = self.by_path.get(path)
        if previous is not None:
            if previous != observed:
                raise ValueError("one runtime path changed between observations")
            return
        alias = unicodedata.normalize("NFC", path).casefold()
        previous_path = self.by_alias.get(alias)
        if previous_path is not None:
            raise ValueError("runtime paths contain an NFC/casefold alias")
        node = (observed.facts[0], observed.facts[1])
        previous_node = self.by_node.get(node)
        if previous_node is not None:
            raise ValueError("runtime paths contain a device/inode alias")
        self.by_path[path] = observed
        self.by_alias[alias] = path
        self.by_node[node] = path

    def recheck_all(self) -> None:
        for observed in self.by_path.values():
            try:
                current = observed.path.lstat()
            except OSError as exc:
                raise ValueError("runtime node disappeared after measurement") from exc
            current_facts = _facts(current)
            if observed.kind == "ancestor_directory":
                current_facts = _stable_directory_facts(current_facts)
            if current_facts != observed.facts:
                raise ValueError("runtime node changed after measurement")
            if (
                observed.kind
                in {
                    "native_executable",
                    "regular_file",
                    "symlink",
                }
                and current.st_nlink != 1
            ):
                raise ValueError("runtime node gained a hardlink alias")
            if observed.kind == "symlink":
                try:
                    target = os.readlink(observed.path)
                except OSError as exc:
                    raise ValueError(
                        "runtime symlink changed after measurement"
                    ) from exc
                if target != observed.raw_target:
                    raise ValueError("runtime symlink target changed after measurement")
            if (
                observed.kind in {"ancestor_directory", "directory"}
                and observed.resolved_path is not None
                and (os.path.realpath(observed.path) != observed.resolved_path)
            ):
                raise ValueError(
                    "runtime ancestor resolution changed after measurement"
                )


def bind_separation_runtime_request(
    worker_request: Mapping[str, Any],
    *,
    trusted_preflight: Mapping[str, Any],
    trusted_acceptance: Mapping[str, Any],
    trusted_separation_request: Any,
    trusted_runtime_artifact: SeparationRuntimeArtifactIdentity,
) -> SeparationRuntimeTrustedRequest:
    """Create the exact parent-owned path binding used by measurement.

    Only the trusted parent should call this after it creates the request.
    The record is an authority boundary between parent modules, not a defence
    against arbitrary code already running in the parent interpreter.
    """

    request = _validated_request(
        worker_request,
        trusted_preflight=trusted_preflight,
        trusted_acceptance=trusted_acceptance,
        trusted_separation_request=trusted_separation_request,
        trusted_runtime_artifact=trusted_runtime_artifact,
    )
    return _new_trusted_request(request)


def _new_trusted_request(
    request: Mapping[str, Any],
) -> SeparationRuntimeTrustedRequest:
    paths = request["paths"]
    value = object.__new__(SeparationRuntimeTrustedRequest)
    object.__setattr__(value, "request", request)
    object.__setattr__(value, "request_sha256", request["request_sha256"])
    object.__setattr__(
        value, "preflight_sha256", request["preflight"]["preflight_sha256"]
    )
    object.__setattr__(value, "runtime_python_path", Path(paths["runtime_python_path"]))
    object.__setattr__(value, "worker_path", Path(paths["worker_path"]))
    object.__setattr__(
        value, "dependency_lock_path", Path(paths["dependency_lock_path"])
    )
    object.__setattr__(value, "_authority", _TRUSTED_REQUEST_AUTHORITY)
    return value


def measure_separation_runtime(
    worker_request: Mapping[str, Any],
    *,
    trusted_request: SeparationRuntimeTrustedRequest,
    trusted_preflight: Mapping[str, Any],
    trusted_acceptance: Mapping[str, Any],
    trusted_separation_request: Any,
    trusted_runtime_artifact: SeparationRuntimeArtifactIdentity,
) -> SeparationRuntimeMeasurement:
    """Measure, cross-bind and freeze one validated private runtime."""

    bound = _trusted_request_binding(
        trusted_request,
        trusted_preflight=trusted_preflight,
        trusted_acceptance=trusted_acceptance,
        trusted_separation_request=trusted_separation_request,
        trusted_runtime_artifact=trusted_runtime_artifact,
    )
    request = _validated_request(
        worker_request,
        trusted_preflight=trusted_preflight,
        trusted_acceptance=trusted_acceptance,
        trusted_separation_request=trusted_separation_request,
        trusted_runtime_artifact=trusted_runtime_artifact,
    )
    if request["request_sha256"] != bound.request_sha256 or (
        _plain(request) != _plain(bound.request)
    ):
        raise ValueError("worker request was substituted after parent validation")
    if request["preflight"]["preflight_sha256"] != bound.preflight_sha256:
        raise ValueError("worker request does not bind trusted preflight")

    registry = _Registry()
    paths = request["paths"]
    if (
        Path(paths["runtime_python_path"]) != bound.runtime_python_path
        or Path(paths["worker_path"]) != bound.worker_path
        or Path(paths["dependency_lock_path"]) != bound.dependency_lock_path
    ):
        raise ValueError("worker request paths do not bind parent-owned record")
    launcher_chain, final_path, final_facts = _snapshot_launcher_chain(
        Path(paths["runtime_python_path"]), registry=registry
    )
    runtime_identity = request["identities"]["runtime"]
    python_version = runtime_identity["python_version"]
    major_minor = ".".join(python_version.split(".")[:2])
    venv_root = Path(paths["runtime_python_path"]).parent.parent
    config_path = venv_root / "pyvenv.cfg"
    site_path = venv_root / "lib" / f"python{major_minor}" / "site-packages"
    logical_paths = [
        *(Path(item["canonical_path"]) for item in launcher_chain),
        config_path,
        site_path,
        Path(paths["worker_path"]),
        Path(paths["dependency_lock_path"]),
    ]
    ancestors = _measure_complete_ancestors(logical_paths, registry=registry)

    final = _measure_regular_file(
        final_path,
        label="native runtime executable",
        maximum_bytes=MAX_RUNTIME_EXECUTABLE_BYTES,
        expected_sha256=trusted_runtime_artifact.sha256,
        expected_bytes=trusted_runtime_artifact.bytes,
        registry=registry,
        executable=True,
    )[0]
    if final["lstat"] != _facts_document(final_facts):
        raise ValueError("native runtime changed before descriptor hashing")
    chain_hash = separation_runtime_launcher_chain_sha256(launcher_chain)
    if (
        Path(paths["runtime_python_path"]) != trusted_runtime_artifact.path
        or final["sha256"] != trusted_runtime_artifact.sha256
        or final["bytes"] != trusted_runtime_artifact.bytes
        or chain_hash != trusted_runtime_artifact.verified_launcher_chain_sha256
    ):
        raise ValueError("measured launcher does not bind trusted runtime identity")

    config, config_bytes = _measure_regular_file(
        config_path,
        label="pyvenv config",
        maximum_bytes=MAX_PYVENV_CONFIG_BYTES,
        expected_sha256=None,
        expected_bytes=None,
        registry=registry,
        return_bytes=True,
    )
    config_version = _parse_pyvenv_version(config_bytes)
    if config_version != python_version:
        raise ValueError("pyvenv version does not bind worker request")

    worker = _measure_regular_file(
        Path(paths["worker_path"]),
        label="worker",
        maximum_bytes=MAX_WORKER_BYTES,
        expected_sha256=request["identities"]["worker"]["sha256"],
        expected_bytes=request["identities"]["worker"]["bytes"],
        registry=registry,
    )[0]
    dependency_lock = _measure_regular_file(
        Path(paths["dependency_lock_path"]),
        label="dependency lock",
        maximum_bytes=MAX_DEPENDENCY_LOCK_BYTES,
        expected_sha256=request["identities"]["dependency_lock"]["sha256"],
        expected_bytes=request["identities"]["dependency_lock"]["bytes"],
        registry=registry,
    )[0]
    site = _measure_site_tree(site_path, registry=registry)

    registry.recheck_all()

    measurements_hash = separation_runtime_measurements_sha256(
        launcher_chain=launcher_chain,
        ancestor_directories=ancestors,
        final_native_executable=final,
        pyvenv_config=config,
        site_packages=site,
        worker=worker,
        dependency_lock=dependency_lock,
    )
    parent_evidence = SeparationRuntimeArtifactParentEvidence(
        worker_request_sha256=request["request_sha256"],
        preflight_sha256=request["preflight"]["preflight_sha256"],
        measurements_sha256=measurements_hash,
    )
    artifact = build_separation_runtime_artifact(
        launcher_chain=launcher_chain,
        ancestor_directories=ancestors,
        final_native_executable=final,
        pyvenv_config=config,
        site_packages=site,
        worker=worker,
        dependency_lock=dependency_lock,
        worker_request_sha256=request["request_sha256"],
        preflight_sha256=request["preflight"]["preflight_sha256"],
        trusted_runtime_artifact=trusted_runtime_artifact,
        trusted_parent_evidence=parent_evidence,
    )
    artifact = validate_separation_runtime_artifact(
        artifact,
        trusted_runtime_artifact=trusted_runtime_artifact,
        trusted_parent_evidence=parent_evidence,
        trusted_worker_request_sha256=request["request_sha256"],
        trusted_preflight_sha256=request["preflight"]["preflight_sha256"],
    )
    return _new_measurement(parent_evidence, artifact)


def remeasure_separation_runtime(
    previous: SeparationRuntimeMeasurement,
    worker_request: Mapping[str, Any],
    *,
    trusted_request: SeparationRuntimeTrustedRequest,
    trusted_preflight: Mapping[str, Any],
    trusted_acceptance: Mapping[str, Any],
    trusted_separation_request: Any,
    trusted_runtime_artifact: SeparationRuntimeArtifactIdentity,
) -> SeparationRuntimeMeasurement:
    """Repeat every read and reject any changed fact or digest.

    Success is still a parent observation made before exec, not execution or
    TOCTOU proof.
    """

    if type(previous) is not SeparationRuntimeMeasurement:
        raise ValueError("previous measurement must be an exact parent result")
    if getattr(previous, "_authority", None) is not _MEASUREMENT_AUTHORITY:
        raise ValueError("previous measurement lacks parent-process authority")
    bound = _trusted_request_binding(
        trusted_request,
        trusted_preflight=trusted_preflight,
        trusted_acceptance=trusted_acceptance,
        trusted_separation_request=trusted_separation_request,
        trusted_runtime_artifact=trusted_runtime_artifact,
    )
    validated_previous = validate_separation_runtime_artifact(
        previous.artifact,
        trusted_runtime_artifact=trusted_runtime_artifact,
        trusted_parent_evidence=previous.parent_evidence,
        trusted_worker_request_sha256=bound.request_sha256,
        trusted_preflight_sha256=bound.preflight_sha256,
    )
    if _plain(validated_previous) != _plain(previous.artifact):
        raise ValueError("previous runtime artifact is not exact trusted evidence")
    current = measure_separation_runtime(
        worker_request,
        trusted_request=bound,
        trusted_preflight=trusted_preflight,
        trusted_acceptance=trusted_acceptance,
        trusted_separation_request=trusted_separation_request,
        trusted_runtime_artifact=trusted_runtime_artifact,
    )
    if (
        current.parent_evidence != previous.parent_evidence
        or current.artifact["artifact_sha256"] != previous.artifact["artifact_sha256"]
        or _plain(current.artifact) != _plain(previous.artifact)
    ):
        raise ValueError("runtime remeasurement changed before execution")
    return current


def _new_measurement(
    parent_evidence: SeparationRuntimeArtifactParentEvidence,
    artifact: Mapping[str, Any],
) -> SeparationRuntimeMeasurement:
    value = object.__new__(SeparationRuntimeMeasurement)
    object.__setattr__(value, "parent_evidence", parent_evidence)
    object.__setattr__(value, "artifact", artifact)
    object.__setattr__(value, "_authority", _MEASUREMENT_AUTHORITY)
    return value


def _trusted_request_binding(
    value: Any,
    *,
    trusted_preflight: Mapping[str, Any],
    trusted_acceptance: Mapping[str, Any],
    trusted_separation_request: Any,
    trusted_runtime_artifact: SeparationRuntimeArtifactIdentity,
) -> SeparationRuntimeTrustedRequest:
    if type(value) is not SeparationRuntimeTrustedRequest:
        raise ValueError("trusted request must be an exact parent-owned record")
    if getattr(value, "_authority", None) is not _TRUSTED_REQUEST_AUTHORITY:
        raise ValueError("trusted request lacks parent-process authority")
    request = _validated_request(
        value.request,
        trusted_preflight=trusted_preflight,
        trusted_acceptance=trusted_acceptance,
        trusted_separation_request=trusted_separation_request,
        trusted_runtime_artifact=trusted_runtime_artifact,
    )
    paths = request["paths"]
    if (
        request["request_sha256"] != value.request_sha256
        or request["preflight"]["preflight_sha256"] != value.preflight_sha256
        or Path(paths["runtime_python_path"]) != value.runtime_python_path
        or Path(paths["worker_path"]) != value.worker_path
        or Path(paths["dependency_lock_path"]) != value.dependency_lock_path
    ):
        raise ValueError("trusted request record was changed or resigned")
    return _new_trusted_request(request)


def _validated_request(
    document: Mapping[str, Any],
    *,
    trusted_preflight: Mapping[str, Any],
    trusted_acceptance: Mapping[str, Any],
    trusted_separation_request: Any,
    trusted_runtime_artifact: SeparationRuntimeArtifactIdentity,
) -> Mapping[str, Any]:
    return validate_separation_worker_request(
        document,
        trusted_preflight=trusted_preflight,
        trusted_acceptance=trusted_acceptance,
        trusted_separation_request=trusted_separation_request,
        trusted_runtime_artifact=trusted_runtime_artifact,
    )


def _snapshot_launcher_chain(
    launcher: Path,
    *,
    registry: _Registry,
) -> tuple[
    list[dict[str, Any]],
    Path,
    tuple[int, int, int, int, int, int],
]:
    current = Path(_canonical_path(launcher))
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _index in range(MAX_RUNTIME_CHAIN_ENTRIES):
        alias = unicodedata.normalize("NFC", str(current)).casefold()
        if alias in seen:
            raise ValueError("runtime launcher chain contains a loop or path alias")
        seen.add(alias)
        try:
            before = current.lstat()
        except OSError as exc:
            raise ValueError("runtime launcher is missing or unreadable") from exc
        facts = _facts(before)
        if stat.S_ISLNK(before.st_mode):
            if before.st_nlink != 1:
                raise ValueError("runtime launcher symlink has hardlink aliases")
            try:
                raw_target = os.readlink(current)
                after = current.lstat()
            except OSError as exc:
                raise ValueError("runtime launcher symlink is unsafe") from exc
            if _facts(after) != facts or after.st_nlink != 1:
                raise ValueError("runtime launcher symlink changed during read")
            target = _resolve_symlink_target(current, raw_target)
            observed = _ObservedNode(current, facts, "symlink", raw_target)
            registry.add(observed)
            chain.append(
                {
                    "canonical_path": str(current),
                    "kind": "symlink",
                    "lstat": _facts_document(facts),
                    "raw_target": raw_target,
                    "canonical_resolved_target": str(target),
                }
            )
            current = target
            continue
        if not stat.S_ISREG(before.st_mode) or not before.st_mode & 0o111:
            raise ValueError("runtime final must be a regular executable file")
        registry.add(_ObservedNode(current, facts, "native_executable"))
        chain.append(
            {
                "canonical_path": str(current),
                "kind": "native_executable",
                "lstat": _facts_document(facts),
                "raw_target": None,
                "canonical_resolved_target": str(current),
            }
        )
        return chain, current, facts
    raise ValueError("runtime launcher chain exceeds eight entries")


def _measure_regular_file(
    path: Path,
    *,
    label: str,
    maximum_bytes: int,
    expected_sha256: str | None,
    expected_bytes: int | None,
    registry: _Registry,
    executable: bool = False,
    return_bytes: bool = False,
) -> tuple[dict[str, Any], bytes]:
    path = Path(_canonical_path(path))
    try:
        before = path.lstat()
    except OSError as exc:
        raise ValueError(f"{label} is missing or unreadable") from exc
    before_facts = _facts(before)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"{label} must be a regular file")
    if executable and not before.st_mode & 0o111:
        raise ValueError(f"{label} must be an executable regular file")
    if before.st_nlink != 1:
        raise ValueError(f"{label} must not have hardlink aliases")
    if before.st_size < 1 or before.st_size > maximum_bytes:
        raise ValueError(f"{label} is outside the supported size bound")

    flags = os.O_RDONLY | os.O_NONBLOCK
    flags |= os.O_CLOEXEC | os.O_NOFOLLOW
    descriptor: int | None = None
    digest = hashlib.sha256()
    data = bytearray() if return_bytes else None
    header = b""
    total = 0
    try:
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            _facts(opened) != before_facts
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
        ):
            raise ValueError(f"{label} changed before descriptor read")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            if not header:
                header = chunk[:4]
            total += len(chunk)
            if total > maximum_bytes:
                raise ValueError(f"{label} exceeded the supported size bound")
            digest.update(chunk)
            if data is not None:
                data.extend(chunk)
        finished = os.fstat(descriptor)
    except OSError as exc:
        raise ValueError(f"{label} descriptor read failed") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    try:
        after = path.lstat()
    except OSError as exc:
        raise ValueError(f"{label} disappeared after descriptor read") from exc
    if (
        _facts(opened) != _facts(finished)
        or _facts(after) != before_facts
        or finished.st_nlink != 1
        or after.st_nlink != 1
        or total != before.st_size
    ):
        raise ValueError(f"{label} changed during descriptor hashing")
    if executable and header not in _NATIVE_MAGICS:
        raise ValueError("runtime final is not a recognised native executable")
    sha256 = digest.hexdigest()
    if expected_sha256 is not None and sha256 != expected_sha256:
        raise ValueError(f"{label} hash does not bind worker request")
    if expected_bytes is not None and total != expected_bytes:
        raise ValueError(f"{label} bytes do not bind worker request")
    kind = "native_executable" if executable else "regular_file"
    observed = _ObservedNode(path, before_facts, kind)
    registry.add(observed)
    return (
        {
            "path": str(path),
            "kind": kind,
            "sha256": sha256,
            "bytes": total,
            "lstat": _facts_document(before_facts),
        },
        bytes(data or b""),
    )


def _measure_complete_ancestors(
    paths: Sequence[Path],
    *,
    registry: _Registry,
) -> list[dict[str, Any]]:
    ancestor_paths: set[str] = set()
    for leaf in paths:
        parent = Path(_canonical_path(leaf)).parent
        while True:
            ancestor_paths.add(str(parent))
            if parent == Path("/"):
                break
            parent = parent.parent
    result: list[dict[str, Any]] = []
    ordered = sorted(
        ancestor_paths,
        key=lambda item: (len(PurePosixPath(item).parts), item),
    )
    descriptors: dict[str, int] = {}
    stable_facts: dict[str, tuple[int, int, int, int, int, int]] = {}
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_DIRECTORY
    try:
        for text in ordered:
            path = Path(text)
            try:
                if text == "/":
                    before = path.lstat()
                    if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
                        raise ValueError("runtime ancestor must be a real directory")
                    descriptor = os.open(path, flags)
                else:
                    parent_text = path.parent.as_posix()
                    parent_descriptor = descriptors.get(parent_text)
                    if parent_descriptor is None:
                        raise ValueError(
                            "runtime ancestor parent binding is incomplete"
                        )
                    before = os.stat(
                        path.name,
                        dir_fd=parent_descriptor,
                        follow_symlinks=False,
                    )
                    if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
                        raise ValueError("runtime ancestor must be a real directory")
                    descriptor = os.open(
                        path.name,
                        flags,
                        dir_fd=parent_descriptor,
                    )
            except OSError as exc:
                raise ValueError("runtime ancestor is missing or unreadable") from exc
            descriptors[text] = descriptor
            facts = _stable_directory_facts(_facts(before))
            opened = os.fstat(descriptor)
            if _stable_directory_facts(_facts(opened)) != facts or not stat.S_ISDIR(
                opened.st_mode
            ):
                raise ValueError("runtime ancestor changed before descriptor pin")
            resolved = os.path.realpath(path)
            if resolved != text:
                raise ValueError("runtime ancestor contains a resolved path alias")
            stable_facts[text] = facts

        for text in ordered:
            path = Path(text)
            descriptor = descriptors[text]
            facts = stable_facts[text]
            finished = os.fstat(descriptor)
            try:
                if text == "/":
                    after = path.lstat()
                else:
                    after = os.stat(
                        path.name,
                        dir_fd=descriptors[path.parent.as_posix()],
                        follow_symlinks=False,
                    )
                path_after = path.lstat()
            except OSError as exc:
                raise ValueError(
                    "runtime ancestor changed during pinned resolution"
                ) from exc
            if (
                _stable_directory_facts(_facts(finished)) != facts
                or _stable_directory_facts(_facts(after)) != facts
                or _stable_directory_facts(_facts(path_after)) != facts
                or os.path.realpath(path) != text
            ):
                raise ValueError("runtime ancestor changed during pinned resolution")
            registry.add(
                _ObservedNode(
                    path,
                    facts,
                    "ancestor_directory",
                    resolved_path=text,
                )
            )
            result.append(
                {
                    "canonical_path": text,
                    "kind": "directory",
                    "lstat": _facts_document(facts),
                    "canonical_resolved_path": text,
                }
            )
    finally:
        for descriptor in reversed(tuple(descriptors.values())):
            os.close(descriptor)
    return result


def _measure_site_tree(
    site_root: Path,
    *,
    registry: _Registry,
) -> dict[str, Any]:
    site_root = Path(_canonical_path(site_root))
    try:
        before = site_root.lstat()
    except OSError as exc:
        raise ValueError("site-packages root is unreadable") from exc
    root_facts = _facts(before)
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
        raise ValueError("site-packages root must be a real directory")
    resolved = os.path.realpath(site_root)
    if resolved != str(site_root):
        raise ValueError("site-packages root contains a resolved alias")

    descriptor: int | None = None
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_DIRECTORY
    try:
        descriptor = os.open(site_root, flags)
        opened = os.fstat(descriptor)
        if _facts(opened) != root_facts or not stat.S_ISDIR(opened.st_mode):
            raise ValueError("site-packages root changed before descriptor pin")
        registry.add(
            _ObservedNode(
                site_root,
                root_facts,
                "directory",
                resolved_path=resolved,
            )
        )
        digest = hashlib.sha256()
        _measure_site_directory(
            descriptor,
            relative="",
            directory_path=site_root,
            expected_facts=root_facts,
            root_device=root_facts[0],
            digest=digest,
            budget=_SiteTreeBudget(),
            registry=registry,
        )
        finished = os.fstat(descriptor)
    except OSError as exc:
        raise ValueError("site-packages descriptor traversal failed") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    try:
        after = site_root.lstat()
    except OSError as exc:
        raise ValueError("site-packages root disappeared after traversal") from exc
    if (
        _facts(finished) != root_facts
        or _facts(after) != root_facts
        or os.path.realpath(site_root) != resolved
    ):
        raise ValueError("site-packages root changed during traversal")
    return {
        "path": str(site_root),
        "kind": "directory",
        "lstat": _facts_document(root_facts),
        "package_tree_algorithm": SEPARATION_RUNTIME_PACKAGE_TREE_ALGORITHM,
        "package_tree_sha256": digest.hexdigest(),
    }


def _measure_site_directory(
    descriptor: int,
    *,
    relative: str,
    directory_path: Path,
    expected_facts: tuple[int, int, int, int, int, int],
    root_device: int,
    digest: Any,
    budget: _SiteTreeBudget,
    registry: _Registry,
) -> None:
    opened = os.fstat(descriptor)
    if _facts(opened) != expected_facts or not stat.S_ISDIR(opened.st_mode):
        raise ValueError("site-packages directory descriptor changed")
    budget.directories += 1
    if budget.directories > MAX_SITE_PACKAGE_DIRECTORIES:
        raise ValueError("site-packages tree contains too many directories")
    digest.update(b"directory\0")
    digest.update((relative or ".").encode("utf-8"))
    digest.update(b"\0")
    _update_digest_facts(digest, expected_facts)

    maximum_entries = (
        MAX_SITE_PACKAGE_FILES + MAX_SITE_PACKAGE_DIRECTORIES - budget.discovered_nodes
    )
    entries = _scan_site_directory_entries(
        descriptor,
        maximum_entries=maximum_entries,
    )
    budget.discovered_nodes += len(entries)
    for name, entry_facts in entries:
        child_relative = f"{relative}/{name}" if relative else name
        child_path = Path(_canonical_path(directory_path / name))
        if entry_facts[0] != root_device:
            raise ValueError("site-packages tree crosses a device boundary")
        mode = entry_facts[2]
        if stat.S_ISLNK(mode):
            raise ValueError("site-packages tree contains a symlink")
        if stat.S_ISDIR(mode):
            _measure_site_child_directory(
                descriptor,
                name=name,
                relative=child_relative,
                child_path=child_path,
                expected_facts=entry_facts,
                root_device=root_device,
                digest=digest,
                budget=budget,
                registry=registry,
            )
        elif stat.S_ISREG(mode):
            budget.files += 1
            if budget.files > MAX_SITE_PACKAGE_FILES:
                raise ValueError("site-packages tree contains too many files")
            digest.update(b"file\0")
            digest.update(child_relative.encode("utf-8"))
            digest.update(b"\0")
            _update_digest_facts(digest, entry_facts)
            budget.total_bytes += _measure_site_file(
                descriptor,
                name=name,
                path=child_path,
                expected_facts=entry_facts,
                digest=digest,
                registry=registry,
            )
            if budget.total_bytes > MAX_SITE_PACKAGE_TOTAL_BYTES:
                raise ValueError("site-packages tree exceeds the total size bound")
            digest.update(b"\0")
        else:
            raise ValueError("site-packages tree contains a device or socket")

    after_entries = _scan_site_directory_entries(
        descriptor,
        maximum_entries=len(entries),
    )
    if after_entries != entries:
        raise ValueError("site-packages entries changed during tree hashing")
    finished = os.fstat(descriptor)
    if _facts(finished) != expected_facts:
        raise ValueError("site-packages directory changed during tree hashing")
    try:
        path_after = directory_path.lstat()
    except OSError as exc:
        raise ValueError("site-packages directory path disappeared") from exc
    if _facts(path_after) != expected_facts or os.path.realpath(directory_path) != str(
        directory_path
    ):
        raise ValueError("site-packages directory path changed during tree hashing")


def _measure_site_child_directory(
    parent_descriptor: int,
    *,
    name: str,
    relative: str,
    child_path: Path,
    expected_facts: tuple[int, int, int, int, int, int],
    root_device: int,
    digest: Any,
    budget: _SiteTreeBudget,
    registry: _Registry,
) -> None:
    before = _stat_at(parent_descriptor, name, "site-packages directory")
    if _facts(before) != expected_facts or not stat.S_ISDIR(before.st_mode):
        raise ValueError("site-packages child directory changed before open")
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_DIRECTORY
    descriptor: int | None = None
    try:
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
        opened = os.fstat(descriptor)
        if _facts(opened) != expected_facts or not stat.S_ISDIR(opened.st_mode):
            raise ValueError("site-packages child directory changed during open")
        resolved = os.path.realpath(child_path)
        if resolved != str(child_path):
            raise ValueError("site-packages child directory contains a resolved alias")
        registry.add(
            _ObservedNode(
                child_path,
                expected_facts,
                "directory",
                resolved_path=resolved,
            )
        )
        _measure_site_directory(
            descriptor,
            relative=relative,
            directory_path=child_path,
            expected_facts=expected_facts,
            root_device=root_device,
            digest=digest,
            budget=budget,
            registry=registry,
        )
        finished = os.fstat(descriptor)
    except OSError as exc:
        raise ValueError("site-packages child directory open failed") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    after = _stat_at(parent_descriptor, name, "site-packages directory")
    if _facts(finished) != expected_facts or _facts(after) != expected_facts:
        raise ValueError("site-packages child directory changed during traversal")


def _measure_site_file(
    parent_descriptor: int,
    *,
    name: str,
    path: Path,
    expected_facts: tuple[int, int, int, int, int, int],
    digest: Any,
    registry: _Registry,
) -> int:
    before = _stat_at(parent_descriptor, name, "site-packages file")
    if before.st_nlink != 1:
        raise ValueError("site-packages file must not have hardlink aliases")
    if _facts(before) != expected_facts or not stat.S_ISREG(before.st_mode):
        raise ValueError("site-packages file changed before descriptor open")
    if before.st_size > MAX_SITE_PACKAGE_FILE_BYTES:
        raise ValueError("site-packages file exceeds its size bound")
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW
    descriptor: int | None = None
    total = 0
    try:
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
        opened = os.fstat(descriptor)
        if (
            _facts(opened) != expected_facts
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
        ):
            raise ValueError("site-packages file changed during descriptor open")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_SITE_PACKAGE_FILE_BYTES:
                raise ValueError("site-packages file exceeded its size bound")
            digest.update(chunk)
        finished = os.fstat(descriptor)
    except OSError as exc:
        raise ValueError("site-packages file descriptor read failed") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    after = _stat_at(parent_descriptor, name, "site-packages file")
    try:
        path_after = path.lstat()
    except OSError as exc:
        raise ValueError("site-packages file path disappeared") from exc
    if (
        _facts(finished) != expected_facts
        or finished.st_nlink != 1
        or _facts(after) != expected_facts
        or after.st_nlink != 1
        or _facts(path_after) != expected_facts
        or path_after.st_nlink != 1
        or total != expected_facts[3]
    ):
        raise ValueError("site-packages file changed during descriptor hashing")
    registry.add(_ObservedNode(path, expected_facts, "regular_file"))
    return total


def _scan_site_directory_entries(
    anchor_descriptor: int,
    *,
    maximum_entries: int,
) -> tuple[tuple[str, tuple[int, int, int, int, int, int]], ...]:
    if (
        type(maximum_entries) is not int
        or maximum_entries < 0
        or maximum_entries > MAX_SITE_PACKAGE_FILES + MAX_SITE_PACKAGE_DIRECTORIES
    ):
        raise ValueError("site-packages scan entry bound is invalid")
    anchor = os.fstat(anchor_descriptor)
    if not stat.S_ISDIR(anchor.st_mode):
        raise ValueError("site-packages scan anchor is not a directory")
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_DIRECTORY
    scan_descriptor: int | None = None
    try:
        scan_descriptor = os.open(".", flags, dir_fd=anchor_descriptor)
        opened = os.fstat(scan_descriptor)
        if _facts(opened) != _facts(anchor):
            raise ValueError("site-packages scan descriptor changed")
        result: list[tuple[str, tuple[int, int, int, int, int, int]]] = []
        names: set[str] = set()
        with os.scandir(scan_descriptor) as iterator:
            for entry in iterator:
                if len(result) >= maximum_entries:
                    raise ValueError(
                        "site-packages tree exceeds the bounded node count"
                    )
                name = _checked_tree_name(entry.name)
                alias = name.casefold()
                if alias in names:
                    raise ValueError("site-packages tree contains a casefold alias")
                names.add(alias)
                info = _stat_at(scan_descriptor, name, "site-packages node")
                result.append((name, _facts(info)))
        finished = os.fstat(scan_descriptor)
    except OSError as exc:
        raise ValueError("site-packages directory scan failed") from exc
    finally:
        if scan_descriptor is not None:
            os.close(scan_descriptor)
    after = os.fstat(anchor_descriptor)
    if _facts(finished) != _facts(anchor) or _facts(after) != _facts(anchor):
        raise ValueError("site-packages directory changed during descriptor scan")
    return tuple(sorted(result))


def _stat_at(descriptor: int, name: str, label: str) -> os.stat_result:
    try:
        return os.stat(name, dir_fd=descriptor, follow_symlinks=False)
    except OSError as exc:
        raise ValueError(f"{label} changed during descriptor lookup") from exc


def _checked_tree_name(value: str) -> str:
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ValueError("site-packages tree contains a non-UTF-8 name") from exc
    if (
        not value
        or value in {".", ".."}
        or len(encoded) > 255
        or "\0" in value
        or "/" in value
        or "\\" in value
        or unicodedata.normalize("NFC", value) != value
    ):
        raise ValueError("site-packages tree contains an unsafe name")
    return value


def _update_digest_facts(
    digest: Any,
    facts: tuple[int, int, int, int, int, int],
) -> None:
    for number in facts:
        digest.update(str(number).encode("ascii"))
        digest.update(b"\0")


def _parse_pyvenv_version(data: bytes) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("pyvenv config is not UTF-8") from exc
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        if "=" not in line:
            raise ValueError("pyvenv config contains an invalid line")
        key, value = line.split("=", 1)
        key = key.strip().casefold()
        value = value.strip()
        if not key or not value or key in values:
            raise ValueError("pyvenv config contains ambiguous keys")
        values[key] = value
    version = values.get("version")
    if version is None or not _PYTHON_VERSION_RE.fullmatch(version):
        raise ValueError("pyvenv config version is unsupported")
    system_site_packages = values.get("include-system-site-packages")
    if system_site_packages is None or system_site_packages.casefold() != "false":
        raise ValueError("pyvenv config must disable system site packages")
    return version


def _resolve_symlink_target(link: Path, raw_target: str) -> Path:
    try:
        encoded_target = raw_target.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ValueError("runtime launcher target is not UTF-8") from exc
    if (
        not raw_target
        or len(encoded_target) > MAX_RUNTIME_PATH_BYTES
        or raw_target != raw_target.strip()
        or "\0" in raw_target
        or "\\" in raw_target
        or "//" in raw_target
        or unicodedata.normalize("NFC", raw_target) != raw_target
    ):
        raise ValueError("runtime launcher contains an unsafe symlink target")
    raw = PurePosixPath(raw_target)
    if str(raw) != raw_target or any(part in {"", ".", ".."} for part in raw.parts):
        raise ValueError("runtime launcher symlink contains an upward escape")
    target = raw if raw.is_absolute() else PurePosixPath(str(link.parent)) / raw
    return Path(_canonical_path(Path(str(target))))


def _canonical_path(path: Path, *, allow_root: bool = False) -> str:
    text = str(path)
    pure = PurePosixPath(text)
    try:
        encoded = text.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ValueError("runtime path is not UTF-8") from exc
    if (
        not text.startswith("/")
        or (text == "/" and not allow_root)
        or len(encoded) > MAX_RUNTIME_PATH_BYTES
        or len(pure.parts) > MAX_RUNTIME_PATH_DEPTH
        or "\0" in text
        or "//" in text
        or "\\" in text
        or unicodedata.normalize("NFC", text) != text
        or str(pure) != text
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise ValueError("runtime path is not canonical absolute local path")
    return text


def _facts(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _stable_directory_facts(
    facts: tuple[int, int, int, int, int, int],
) -> tuple[int, int, int, int, int, int]:
    """Project ancestor evidence to stable path identity.

    Directory size and timestamps reflect unrelated sibling activity.  Their
    zero values are an explicit deterministic projection, not observed zeros.
    """

    return (facts[0], facts[1], facts[2], 0, 0, 0)


def _facts_document(
    facts: tuple[int, int, int, int, int, int],
) -> dict[str, int]:
    return {
        "device": facts[0],
        "inode": facts[1],
        "mode": facts[2],
        "size": facts[3],
        "mtime_ns": facts[4],
        "ctime_ns": facts[5],
    }


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


__all__ = [
    "SeparationRuntimeMeasurement",
    "SeparationRuntimeTrustedRequest",
    "bind_separation_runtime_request",
    "measure_separation_runtime",
    "remeasure_separation_runtime",
]
