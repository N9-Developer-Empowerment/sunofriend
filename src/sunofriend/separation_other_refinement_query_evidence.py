"""Non-loading static evidence for the Banquet query checkpoint.

This module deliberately does not import PyTorch, Lightning or Banquet.  It
hashes one descriptor-pinned file, inventories a bounded ZIP container and
parses only the ``data.pkl`` opcode stream with :mod:`pickletools`.  It never
deserializes the pickle or reads tensor-storage member payloads.
"""

from __future__ import annotations

import hashlib
import json
import os
import pickletools
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


QUERY_CHECKPOINT_EVIDENCE_SCHEMA = (
    "sunofriend.other-refinement-query-checkpoint-evidence.v1"
)
EXPECTED_CHECKPOINT_BYTES = 645_470_187
EXPECTED_CHECKPOINT_MD5 = "4dfb91d6d27c2dfd4992a15070915541"
MAX_CHECKPOINT_BYTES = 700 * 1024 * 1024
MAX_ZIP_MEMBERS = 16_384
MAX_MEMBER_NAME_BYTES = 2_048
MAX_PICKLE_BYTES = 32 * 1024 * 1024
MAX_PICKLE_OPCODES = 1_000_000
MAX_PICKLE_GLOBALS = 4_096

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CONSTRUCTION_OPCODES = frozenset({"INST", "NEWOBJ", "NEWOBJ_EX", "OBJ", "REDUCE"})


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


def _hash_descriptor(descriptor: int) -> tuple[str, str, int]:
    sha256 = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)
    byte_count = 0
    os.lseek(descriptor, 0, os.SEEK_SET)
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        byte_count += len(chunk)
        if byte_count > MAX_CHECKPOINT_BYTES:
            raise ValueError("checkpoint exceeds the approved 700 MiB cap")
        sha256.update(chunk)
        md5.update(chunk)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return sha256.hexdigest(), md5.hexdigest(), byte_count


def _safe_member_name(name: str) -> PurePosixPath:
    if not name or len(name.encode("utf-8")) > MAX_MEMBER_NAME_BYTES:
        raise ValueError("checkpoint ZIP member name is empty or too long")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError("checkpoint ZIP member name is unsafe")
    return path


def _inspect_pickle(data: bytes) -> dict[str, Any]:
    protocol: int | None = None
    opcode_count = 0
    opcode_names: set[str] = set()
    globals_found: set[str] = set()
    unresolved_stack_globals = 0
    opcode_hash = hashlib.sha256()
    stop_end: int | None = None
    try:
        for opcode, argument, position in pickletools.genops(data):
            opcode_count += 1
            if opcode_count > MAX_PICKLE_OPCODES:
                raise ValueError("checkpoint pickle opcode count exceeds limit")
            name = opcode.name
            opcode_names.add(name)
            opcode_hash.update(f"{position}:{name}\n".encode("ascii"))
            if name == "PROTO" and isinstance(argument, int):
                protocol = argument
            elif name == "GLOBAL":
                if not isinstance(argument, str):
                    raise ValueError("checkpoint GLOBAL opcode is invalid")
                normalized = " ".join(argument.split())
                globals_found.add(normalized)
                if len(globals_found) > MAX_PICKLE_GLOBALS:
                    raise ValueError("checkpoint pickle global count exceeds limit")
            elif name == "STACK_GLOBAL":
                unresolved_stack_globals += 1
            if name == "STOP":
                stop_end = position + 1
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("checkpoint pickle opcode stream is invalid") from exc
    if stop_end is None or stop_end != len(data):
        raise ValueError("checkpoint pickle is unterminated or has trailing bytes")
    globals_list = sorted(globals_found)
    return {
        "protocol": protocol,
        "opcode_count": opcode_count,
        "opcode_stream_sha256": opcode_hash.hexdigest(),
        "opcode_names_sha256": _canonical_sha256({"names": sorted(opcode_names)}),
        "global_count": len(globals_list),
        "globals": globals_list,
        "globals_sha256": _canonical_sha256({"globals": globals_list}),
        "unresolved_stack_globals": unresolved_stack_globals,
        "object_construction_opcodes": sorted(
            opcode_names.intersection(_CONSTRUCTION_OPCODES)
        ),
        "persistent_storage_opcode_observed": bool(
            {"BINPERSID", "PERSID"}.intersection(opcode_names)
        ),
        "trailing_bytes": 0,
    }


def inspect_query_checkpoint_evidence(
    checkpoint_path: str | Path,
    *,
    expected_bytes: int = EXPECTED_CHECKPOINT_BYTES,
    expected_md5: str = EXPECTED_CHECKPOINT_MD5,
) -> dict[str, Any]:
    """Return bounded static evidence without loading checkpoint objects."""

    path = Path(checkpoint_path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("checkpoint must be one non-linked regular file")
        sha256, md5, byte_count = _hash_descriptor(descriptor)
        if byte_count != expected_bytes:
            raise ValueError("checkpoint byte count differs from published evidence")
        if md5 != expected_md5:
            raise ValueError("checkpoint MD5 differs from published evidence")
        if not _SHA256_RE.fullmatch(sha256):
            raise ValueError("checkpoint SHA-256 is invalid")

        duplicate = os.dup(descriptor)
        try:
            with os.fdopen(duplicate, "rb", closefd=True) as stream:
                duplicate = -1
                try:
                    archive = zipfile.ZipFile(stream, mode="r", allowZip64=True)
                except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
                    raise ValueError(
                        "checkpoint is not a readable ZIP container"
                    ) from exc
                with archive:
                    infos = archive.infolist()
                    if not 0 < len(infos) <= MAX_ZIP_MEMBERS:
                        raise ValueError("checkpoint ZIP member count exceeds limit")
                    seen: set[str] = set()
                    inventory: list[dict[str, Any]] = []
                    pickle_infos: list[zipfile.ZipInfo] = []
                    for info in infos:
                        member = _safe_member_name(info.filename)
                        normalized = member.as_posix()
                        if normalized in seen:
                            raise ValueError(
                                "checkpoint ZIP has duplicate member names"
                            )
                        seen.add(normalized)
                        if info.file_size < 0 or info.compress_size < 0:
                            raise ValueError(
                                "checkpoint ZIP has an invalid member size"
                            )
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
                        raise ValueError("checkpoint ZIP must contain one data.pkl")
                    pickle_info = pickle_infos[0]
                    if pickle_info.file_size > MAX_PICKLE_BYTES:
                        raise ValueError("checkpoint data.pkl exceeds inspection limit")
                    with archive.open(pickle_info, mode="r") as member:
                        data = member.read(MAX_PICKLE_BYTES + 1)
                    if len(data) != pickle_info.file_size:
                        raise ValueError("checkpoint data.pkl bounded read differs")
                    pickle_evidence = _inspect_pickle(data)
                    inventory.sort(key=lambda item: item["header_offset"])
                    archive_evidence = {
                        "kind": "zip-with-pickle-metadata",
                        "member_count": len(infos),
                        "inventory_sha256": _canonical_sha256({"members": inventory}),
                        "total_compressed_bytes": sum(
                            info.compress_size for info in infos
                        ),
                        "total_uncompressed_bytes": sum(
                            info.file_size for info in infos
                        ),
                        "data_pickle_bytes": len(data),
                        "data_pickle_sha256": hashlib.sha256(data).hexdigest(),
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
            raise ValueError("checkpoint changed during static inspection")
    finally:
        os.close(descriptor)

    document: dict[str, Any] = {
        "schema": QUERY_CHECKPOINT_EVIDENCE_SCHEMA,
        "status": "statically_inspected_not_loaded",
        "checkpoint": {
            "record_id": 13_694_558,
            "file": "ev-pre-aug.ckpt",
            "bytes": byte_count,
            "published_md5": expected_md5,
            "observed_md5": md5,
            "sha256": sha256,
            "license": "CC-BY-NC-SA-4.0",
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
            "pickle_opcodes_were_parsed_but_never_executed",
            "pickle_stack_memo_and_persistent_id_semantics_not_proven",
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


def validate_query_checkpoint_evidence(value: dict[str, Any]) -> dict[str, Any]:
    """Validate the immutable boundaries of an evidence document."""

    candidate = dict(value)
    digest = candidate.pop("evidence_sha256", None)
    if not isinstance(digest, str) or digest != _canonical_sha256(candidate):
        raise ValueError("query checkpoint evidence hash differs")
    if candidate.get("schema") != QUERY_CHECKPOINT_EVIDENCE_SCHEMA:
        raise ValueError("query checkpoint evidence schema differs")
    checkpoint = candidate.get("checkpoint", {})
    if checkpoint.get("bytes") != EXPECTED_CHECKPOINT_BYTES:
        raise ValueError("query checkpoint evidence byte count differs")
    if checkpoint.get("observed_md5") != EXPECTED_CHECKPOINT_MD5:
        raise ValueError("query checkpoint evidence MD5 differs")
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
        raise ValueError("query checkpoint evidence expands authority")
    if effects.get("inference_runs") != 0 or effects.get("audio_reads") != 0:
        raise ValueError("query checkpoint evidence records execution")
    return value
