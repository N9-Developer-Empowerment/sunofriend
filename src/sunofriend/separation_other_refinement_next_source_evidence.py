"""Safe, non-importing evidence for the pinned BS-RoFormer source archive."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
from typing import Any, Mapping


SOURCE_EVIDENCE_SCHEMA = "sunofriend.mega53-source-evidence.v1"
SOURCE_REVISION = "de35ada5817b878da0194ee2860253dda3a9c2b2"
SOURCE_ARCHIVE_ROOT = f"bs-roformer-infer-{SOURCE_REVISION}"
ARCHIVE_CAP_BYTES = 33_554_432
UNCOMPRESSED_CAP_BYTES = 67_108_864
EXPECTED_FILE_HASHES = {
    "LICENSE": "d5ca885481147d15e92e5e525ba1a024ad1e92df743a10874bcdf7494f7e26eb",
    "pyproject.toml": "7244eb4250e4a35573f54cbc7a6d6bb304dc794a2615a29b296c53efd175389e",
    "src/bs_roformer/config/checkpoints.toml": (
        "ed63c020d57ab30c73fd16d51e78ec9e124e9eee3cd966d68ddb3b1c132e5ca5"
    ),
    "src/bs_roformer/backends/mlx_backend.py": (
        "355ff36235503dadbfc17fc9bcec01703b09224c038fcb7c7b1a1270f9482954"
    ),
    "src/bs_roformer/mlx/convert.py": (
        "83e92b88e4553e2b6f387d8e55c2e3810195983bc8415df8ed9effc2a339a8a5"
    ),
    "src/bs_roformer/utils.py": (
        "c30906f036e95480b8ab43f028fcc32ceef25eb24a144bb21e23261729fa4195"
    ),
}


def _document_sha256(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "evidence_sha256"}
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _safe_relative_path(name: str) -> PurePosixPath | None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError(f"unsafe source archive member path: {name}")
    if not path.parts or path.parts[0] != SOURCE_ARCHIVE_ROOT:
        raise ValueError(f"unexpected source archive root: {name}")
    if len(path.parts) == 1:
        return None
    relative = PurePosixPath(*path.parts[1:])
    return relative


def inspect_source_archive(
    archive_path: Path,
    *,
    extract_root: Path | None = None,
    expected_file_hashes: Mapping[str, str] = EXPECTED_FILE_HASHES,
    archive_cap_bytes: int = ARCHIVE_CAP_BYTES,
    uncompressed_cap_bytes: int = UNCOMPRESSED_CAP_BYTES,
) -> dict[str, Any]:
    """Hash and optionally extract a safe source tar without importing its code."""

    archive_path = archive_path.resolve()
    archive_bytes = archive_path.stat().st_size
    if archive_bytes <= 0 or archive_bytes > archive_cap_bytes:
        raise ValueError("source archive byte count is outside the approved cap")

    files: list[dict[str, Any]] = []
    observed_hashes: dict[str, str] = {}
    total_uncompressed_bytes = 0
    with tarfile.open(archive_path, mode="r:*") as archive:
        members = archive.getmembers()
        if not members:
            raise ValueError("source archive is empty")
        for member in members:
            relative = _safe_relative_path(member.name)
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise ValueError(f"source archive contains forbidden member: {member.name}")
            if member.isdir():
                continue
            if relative is None:
                raise ValueError(f"source archive root is not a directory: {member.name}")
            if not member.isfile():
                raise ValueError(f"source archive contains unsupported member: {member.name}")
            total_uncompressed_bytes += member.size
            if total_uncompressed_bytes > uncompressed_cap_bytes:
                raise ValueError("source archive exceeds the uncompressed byte cap")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ValueError(f"source archive member cannot be read: {member.name}")
            payload = extracted.read()
            if len(payload) != member.size:
                raise ValueError(f"source archive member byte count differs: {member.name}")
            relative_text = relative.as_posix()
            if relative_text in observed_hashes:
                raise ValueError(f"source archive contains a duplicate path: {member.name}")
            digest = hashlib.sha256(payload).hexdigest()
            observed_hashes[relative_text] = digest
            files.append(
                {
                    "path": relative_text,
                    "bytes": len(payload),
                    "sha256": digest,
                }
            )
            if extract_root is not None:
                destination = extract_root / Path(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(payload)

    expected = dict(expected_file_hashes)
    observed_critical = {path: observed_hashes.get(path) for path in expected}
    if observed_critical != expected:
        raise ValueError("critical source-file hashes differ from the audited revision")

    evidence: dict[str, Any] = {
        "schema": SOURCE_EVIDENCE_SCHEMA,
        "evidence_sha256": "",
        "status": "exact_source_archive_verified_statically_not_imported",
        "source_revision": SOURCE_REVISION,
        "archive": {
            "file": archive_path.name,
            "bytes": archive_bytes,
            "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
            "approved_cap_bytes": archive_cap_bytes,
            "member_count": len(files),
            "uncompressed_file_bytes": total_uncompressed_bytes,
            "uncompressed_cap_bytes": uncompressed_cap_bytes,
        },
        "critical_file_hashes": observed_critical,
        "files": sorted(files, key=lambda item: item["path"]),
        "inspection": {
            "network_denied": True,
            "archive_paths_validated": True,
            "links_and_special_members_allowed": False,
            "source_imported": False,
            "source_executed": False,
            "extracted": extract_root is not None,
        },
        "effects": {
            "dependency_installed": False,
            "checkpoint_loaded": False,
            "model_constructed": False,
            "inference_runs": 0,
            "audio_reads": 0,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
        },
    }
    evidence["evidence_sha256"] = _document_sha256(evidence)
    return evidence


def validate_source_evidence(
    evidence: dict[str, Any],
    *,
    expected_file_hashes: Mapping[str, str] = EXPECTED_FILE_HASHES,
) -> dict[str, Any]:
    """Validate immutable identity and no-effects source evidence."""

    if evidence.get("schema") != SOURCE_EVIDENCE_SCHEMA:
        raise ValueError("Mega-53 source evidence schema differs")
    if evidence.get("source_revision") != SOURCE_REVISION:
        raise ValueError("Mega-53 source revision differs")
    if evidence.get("critical_file_hashes") != dict(expected_file_hashes):
        raise ValueError("Mega-53 critical source-file hashes differ")
    if any(evidence.get("effects", {}).values()):
        raise ValueError("Mega-53 source evidence expands authority")
    if evidence.get("evidence_sha256") != _document_sha256(evidence):
        raise ValueError("Mega-53 source evidence hash differs")
    return json.loads(json.dumps(evidence))


def verify_extracted_source_tree(
    evidence: dict[str, Any],
    source_root: Path,
    *,
    expected_file_hashes: Mapping[str, str] = EXPECTED_FILE_HASHES,
) -> dict[str, Any]:
    """Re-hash the extracted source tree against its complete sealed inventory."""

    validated = validate_source_evidence(
        evidence, expected_file_hashes=expected_file_hashes
    )
    source_root = source_root.resolve()
    if not source_root.is_dir() or source_root.is_symlink():
        raise ValueError("Mega-53 extracted source root is not a regular directory")
    expected = {
        item["path"]: {"bytes": item["bytes"], "sha256": item["sha256"]}
        for item in validated["files"]
    }
    observed: dict[str, dict[str, Any]] = {}
    for path in sorted(source_root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Mega-53 extracted source tree contains a symbolic link")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("Mega-53 extracted source tree contains a special file")
        relative = path.relative_to(source_root).as_posix()
        observed[relative] = {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    if observed != expected:
        raise ValueError("Mega-53 extracted source tree differs from sealed evidence")
    return {
        "file_count": len(observed),
        "logical_bytes": sum(item["bytes"] for item in observed.values()),
        "inventory_matches": True,
    }
