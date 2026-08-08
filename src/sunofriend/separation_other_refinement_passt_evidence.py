"""Non-loading static evidence for Banquet's OpenMIC PaSST checkpoint."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .separation_other_refinement_query_evidence import _inspect_pickle


PASST_CHECKPOINT_EVIDENCE_SCHEMA = (
    "sunofriend.other-refinement-passt-checkpoint-evidence.v1"
)
EXPECTED_PASST_CHECKPOINT_BYTES = 341_546_630
MAX_PASST_CHECKPOINT_BYTES = 375 * 1024 * 1024
MAX_ZIP_MEMBERS = 16_384
MAX_PICKLE_BYTES = 32 * 1024 * 1024
MAX_MEMBER_NAME_BYTES = 2_048


def _canonical_sha256(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _safe_member_name(name: str) -> PurePosixPath:
    if not name or len(name.encode("utf-8")) > MAX_MEMBER_NAME_BYTES:
        raise ValueError("PaSST checkpoint ZIP member name is empty or too long")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError("PaSST checkpoint ZIP member name is unsafe")
    return path


def _hash_descriptor(descriptor: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_count = 0
    os.lseek(descriptor, 0, os.SEEK_SET)
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        byte_count += len(chunk)
        if byte_count > MAX_PASST_CHECKPOINT_BYTES:
            raise ValueError("PaSST checkpoint exceeds the approved 375 MiB cap")
        digest.update(chunk)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return digest.hexdigest(), byte_count


def inspect_passt_checkpoint_evidence(
    checkpoint_path: str | Path,
    *,
    expected_bytes: int = EXPECTED_PASST_CHECKPOINT_BYTES,
) -> dict[str, Any]:
    """Hash and statically inspect one file without deserialising it."""

    path = Path(checkpoint_path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("PaSST checkpoint must be one non-linked regular file")
        sha256, byte_count = _hash_descriptor(descriptor)
        if byte_count != expected_bytes:
            raise ValueError("PaSST checkpoint byte count differs from release evidence")

        duplicate = os.dup(descriptor)
        try:
            with os.fdopen(duplicate, "rb", closefd=True) as stream:
                duplicate = -1
                try:
                    archive = zipfile.ZipFile(stream, mode="r", allowZip64=True)
                except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
                    raise ValueError(
                        "PaSST checkpoint is not a readable ZIP container"
                    ) from exc
                with archive:
                    infos = archive.infolist()
                    if not 0 < len(infos) <= MAX_ZIP_MEMBERS:
                        raise ValueError("PaSST checkpoint ZIP member count exceeds limit")
                    seen: set[str] = set()
                    inventory: list[dict[str, Any]] = []
                    pickle_infos: list[zipfile.ZipInfo] = []
                    for info in infos:
                        member = _safe_member_name(info.filename)
                        normalized = member.as_posix()
                        if normalized in seen:
                            raise ValueError(
                                "PaSST checkpoint ZIP has duplicate member names"
                            )
                        seen.add(normalized)
                        if member.name == "data.pkl":
                            pickle_infos.append(info)
                        inventory.append(
                            {
                                "name_sha256": hashlib.sha256(
                                    normalized.encode("utf-8")
                                ).hexdigest(),
                                "compressed_bytes": info.compress_size,
                                "uncompressed_bytes": info.file_size,
                                "compression": info.compress_type,
                                "crc32": f"{info.CRC:08x}",
                                "header_offset": info.header_offset,
                            }
                        )
                    if len(pickle_infos) != 1:
                        raise ValueError(
                            "PaSST checkpoint ZIP must contain one data.pkl"
                        )
                    pickle_info = pickle_infos[0]
                    if pickle_info.file_size > MAX_PICKLE_BYTES:
                        raise ValueError("PaSST checkpoint data.pkl exceeds limit")
                    with archive.open(pickle_info, mode="r") as member:
                        pickle_data = member.read(MAX_PICKLE_BYTES + 1)
                    if len(pickle_data) != pickle_info.file_size:
                        raise ValueError("PaSST checkpoint bounded pickle read differs")
                    pickle_evidence = _inspect_pickle(pickle_data)
                    inventory.sort(key=lambda item: item["header_offset"])
                    archive_evidence = {
                        "kind": "zip-with-pickle-metadata",
                        "member_count": len(infos),
                        "inventory_sha256": _canonical_sha256(
                            {"members": inventory}
                        ),
                        "total_compressed_bytes": sum(
                            info.compress_size for info in infos
                        ),
                        "total_uncompressed_bytes": sum(
                            info.file_size for info in infos
                        ),
                        "data_pickle_bytes": len(pickle_data),
                        "data_pickle_sha256": hashlib.sha256(
                            pickle_data
                        ).hexdigest(),
                        "data_pickle_crc_verified": True,
                        "non_pickle_member_payloads_read": False,
                    }
        finally:
            if duplicate >= 0:
                os.close(duplicate)

        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError("PaSST checkpoint changed during static inspection")
    finally:
        os.close(descriptor)

    document: dict[str, Any] = {
        "schema": PASST_CHECKPOINT_EVIDENCE_SCHEMA,
        "status": "statically_inspected_not_loaded",
        "checkpoint": {
            "release": "https://github.com/kkoutini/PaSST/releases/tag/v0.0.5",
            "file": "openmic-passt-s-f128-10sec-p16-s10-ap.85.pt",
            "bytes": byte_count,
            "sha256": sha256,
            "code_license_evidence": "Apache-2.0",
            "training_dataset": "OpenMIC-2018",
            "training_dataset_license": "CC-BY-4.0",
        },
        "archive": archive_evidence,
        "pickle": pickle_evidence,
        "classification": {
            "kind": "pickle_checkpoint_static_structure_only",
            "loading_safety": "not_established_by_static_opcode_inspection",
            "authorizes_loading": False,
            "authorizes_execution": False,
        },
        "limitations": [
            "release_metadata_did_not_publish_a_sha256",
            "the_observed_sha256_establishes_the_local_artifact_identity",
            "pickle_opcodes_were_parsed_but_never_executed",
            "tensor_storage_payloads_were_not_read",
            "static_evidence_does_not_qualify_a_runtime_or_model",
        ],
        "effects": {
            "checkpoint_bytes_read": True,
            "archive_metadata_parsed": True,
            "pickle_opcodes_parsed": True,
            "checkpoint_deserialized": False,
            "dependency_installed": False,
            "model_imported": False,
            "model_constructed": False,
            "inference_runs": 0,
            "audio_reads": 0,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
        },
    }
    document["evidence_sha256"] = _canonical_sha256(document)
    return document


def validate_passt_checkpoint_evidence(value: dict[str, Any]) -> dict[str, Any]:
    """Validate identity and the non-execution boundary."""

    candidate = dict(value)
    digest = candidate.pop("evidence_sha256", None)
    if not isinstance(digest, str) or digest != _canonical_sha256(candidate):
        raise ValueError("PaSST checkpoint evidence hash differs")
    if candidate.get("schema") != PASST_CHECKPOINT_EVIDENCE_SCHEMA:
        raise ValueError("PaSST checkpoint evidence schema differs")
    if (
        candidate.get("checkpoint", {}).get("bytes")
        != EXPECTED_PASST_CHECKPOINT_BYTES
    ):
        raise ValueError("PaSST checkpoint evidence byte count differs")
    effects = candidate.get("effects", {})
    forbidden = (
        "checkpoint_deserialized",
        "dependency_installed",
        "model_imported",
        "model_constructed",
        "public_activation",
        "source_selection",
        "midi_created",
    )
    if any(effects.get(key) is not False for key in forbidden):
        raise ValueError("PaSST checkpoint evidence expands authority")
    if effects.get("inference_runs") != 0 or effects.get("audio_reads") != 0:
        raise ValueError("PaSST checkpoint evidence records execution")
    return value
