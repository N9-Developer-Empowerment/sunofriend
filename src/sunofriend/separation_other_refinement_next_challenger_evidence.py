"""Bounded, non-loading evidence for the MVSep Mega-53 artifacts.

The inspector deliberately imports no model runtime.  It hashes two exact
regular files, inventories the checkpoint ZIP container, parses only the
``data.pkl`` opcode stream with :mod:`pickletools`, and reads the configuration
as bounded UTF-8 text.  It never deserializes checkpoint objects or reads
tensor-storage member payloads.
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


MEGA53_EVIDENCE_SCHEMA = "sunofriend.mvsep-mega53-artifact-evidence.v1"
CHECKPOINT_FILE = "mvsep_mega_model_bs_roformer_53_stems_v1.ckpt"
CHECKPOINT_BYTES = 1_368_919_887
CHECKPOINT_SHA256 = "c62820893bbf86d4e734f966bd142d9157cfc8bb8e79e9d8f9ea553f3ff3519f"
CONFIG_FILE = "mvsep_mega_model_bs_roformer_53_stems.yaml"
CONFIG_BYTES = 4_184
CONFIG_SHA256 = "7e198062a251587088adb91215a4f44ab59e67bd62fcc805cf54d6e7dfc51103"
APPROVED_TOTAL_BYTES = 1_610_612_736
MAX_ZIP_MEMBERS = 65_536
MAX_MEMBER_NAME_BYTES = 2_048
MAX_PICKLE_BYTES = 64 * 1024 * 1024
MAX_PICKLE_OPCODES = 4_000_000
MAX_PICKLE_GLOBALS = 16_384

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CONSTRUCTION_OPCODES = frozenset({"INST", "NEWOBJ", "NEWOBJ_EX", "OBJ", "REDUCE"})
_REQUIRED_CONFIG_TOKENS = ("synth", "wind", "guitar", "instruments")


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


def _open_regular(path: Path) -> tuple[int, os.stat_result]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    details = os.fstat(descriptor)
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        os.close(descriptor)
        raise ValueError("artifact must be one non-linked regular file")
    return descriptor, details


def _same_file(before: os.stat_result, after: os.stat_result) -> bool:
    return (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) == (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )


def _hash_descriptor(descriptor: int, *, maximum_bytes: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_count = 0
    os.lseek(descriptor, 0, os.SEEK_SET)
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        byte_count += len(chunk)
        if byte_count > maximum_bytes:
            raise ValueError("artifact exceeds its approved byte boundary")
        digest.update(chunk)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return digest.hexdigest(), byte_count


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
                globals_found.add(" ".join(argument.split()))
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


def _inspect_checkpoint(
    path: Path,
    *,
    expected_bytes: int,
    expected_sha256: str,
    artifact_file: str = CHECKPOINT_FILE,
    maximum_bytes: int = APPROVED_TOTAL_BYTES,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    descriptor, before = _open_regular(path)
    try:
        sha256, byte_count = _hash_descriptor(
            descriptor, maximum_bytes=maximum_bytes
        )
        if byte_count != expected_bytes:
            raise ValueError("checkpoint byte count differs from reviewed identity")
        if sha256 != expected_sha256:
            raise ValueError("checkpoint SHA-256 differs from reviewed identity")

        duplicate = os.dup(descriptor)
        try:
            with os.fdopen(duplicate, "rb", closefd=True) as stream:
                duplicate = -1
                try:
                    archive = zipfile.ZipFile(stream, mode="r", allowZip64=True)
                except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
                    raise ValueError("checkpoint is not a readable ZIP container") from exc
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
                            raise ValueError("checkpoint ZIP has duplicate member names")
                        seen.add(normalized)
                        if info.file_size < 0 or info.compress_size < 0:
                            raise ValueError("checkpoint ZIP has an invalid member size")
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
                        "total_compressed_bytes": sum(info.compress_size for info in infos),
                        "total_uncompressed_bytes": sum(info.file_size for info in infos),
                        "data_pickle_bytes": len(data),
                        "data_pickle_sha256": hashlib.sha256(data).hexdigest(),
                        "data_pickle_crc_verified": True,
                        "non_pickle_member_payloads_read": False,
                    }
        finally:
            if duplicate >= 0:
                os.close(duplicate)

        if not _same_file(before, os.fstat(descriptor)):
            raise ValueError("checkpoint changed during static inspection")
    finally:
        os.close(descriptor)

    return (
        {"file": artifact_file, "bytes": byte_count, "sha256": sha256},
        archive_evidence,
        pickle_evidence,
    )


def _inspect_config(
    path: Path,
    *,
    expected_bytes: int,
    expected_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    descriptor, before = _open_regular(path)
    try:
        sha256, byte_count = _hash_descriptor(
            descriptor, maximum_bytes=APPROVED_TOTAL_BYTES
        )
        if byte_count != expected_bytes:
            raise ValueError("configuration byte count differs from reviewed identity")
        if sha256 != expected_sha256:
            raise ValueError("configuration SHA-256 differs from reviewed identity")
        data = os.read(descriptor, expected_bytes + 1)
        if len(data) != expected_bytes:
            raise ValueError("configuration bounded read differs")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("configuration is not UTF-8") from exc
        if "\x00" in text:
            raise ValueError("configuration contains a NUL byte")
        missing = [token for token in _REQUIRED_CONFIG_TOKENS if token not in text]
        if missing:
            raise ValueError("configuration lacks reviewed role tokens")
        if not _same_file(before, os.fstat(descriptor)):
            raise ValueError("configuration changed during static inspection")
    finally:
        os.close(descriptor)
    lines = text.splitlines()
    return (
        {"file": CONFIG_FILE, "bytes": byte_count, "sha256": sha256},
        {
            "kind": "bounded-utf8-text-identity",
            "line_count": len(lines),
            "nonempty_line_count": sum(bool(line.strip()) for line in lines),
            "nul_bytes": 0,
            "required_role_tokens_present": list(_REQUIRED_CONFIG_TOKENS),
            "yaml_constructed": False,
        },
    )


def inspect_mega53_artifact_evidence(
    checkpoint_path: str | Path,
    config_path: str | Path,
    *,
    expected_checkpoint_bytes: int = CHECKPOINT_BYTES,
    expected_checkpoint_sha256: str = CHECKPOINT_SHA256,
    expected_config_bytes: int = CONFIG_BYTES,
    expected_config_sha256: str = CONFIG_SHA256,
) -> dict[str, Any]:
    """Return exact static evidence without importing or loading a model."""

    checkpoint, archive, pickle = _inspect_checkpoint(
        Path(checkpoint_path),
        expected_bytes=expected_checkpoint_bytes,
        expected_sha256=expected_checkpoint_sha256,
    )
    config, config_structure = _inspect_config(
        Path(config_path),
        expected_bytes=expected_config_bytes,
        expected_sha256=expected_config_sha256,
    )
    combined_bytes = checkpoint["bytes"] + config["bytes"]
    if combined_bytes > APPROVED_TOTAL_BYTES:
        raise ValueError("combined artifacts exceed the approved 1.5 GiB cap")
    document: dict[str, Any] = {
        "schema": MEGA53_EVIDENCE_SCHEMA,
        "status": "artifacts_verified_statically_not_loaded",
        "profile_id": "bs-roformer-mega-53-synth-v1",
        "artifacts": {"checkpoint": checkpoint, "config": config},
        "download": {
            "approved_cap_bytes": APPROVED_TOTAL_BYTES,
            "observed_total_bytes": combined_bytes,
            "within_approved_cap": True,
        },
        "checkpoint_archive": archive,
        "checkpoint_pickle": pickle,
        "config_structure": config_structure,
        "classification": {
            "kind": "pytorch_zip_checkpoint_static_structure_only",
            "loading_safety": "not_established_by_static_opcode_inspection",
            "future_required_loader": "torch.load(weights_only=True, map_location='cpu')",
            "authorizes_loading": False,
            "authorizes_execution": False,
        },
        "terms": {
            "checkpoint_registry_value": "not-reviewed",
            "provisional_use": "local_noncommercial_evaluation_only",
            "hosted_service_or_redistribution_allowed": False,
        },
        "limitations": [
            "pickle_opcodes_were_parsed_but_never_executed",
            "pickle_stack_memo_and_persistent_id_semantics_not_proven",
            "tensor_storage_payloads_were_not_read",
            "static_evidence_does_not_qualify_a_runtime_or_model",
        ],
        "effects": {
            "artifact_bytes_read": True,
            "archive_metadata_parsed": True,
            "pickle_opcodes_parsed": True,
            "checkpoint_deserialized": False,
            "torch_load_called": False,
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


def validate_mega53_artifact_evidence(value: dict[str, Any]) -> dict[str, Any]:
    """Validate exact artifact identities and the no-runtime boundary."""

    candidate = dict(value)
    digest = candidate.pop("evidence_sha256", None)
    if not isinstance(digest, str) or digest != _canonical_sha256(candidate):
        raise ValueError("Mega-53 artifact evidence hash differs")
    if candidate.get("schema") != MEGA53_EVIDENCE_SCHEMA:
        raise ValueError("Mega-53 artifact evidence schema differs")
    artifacts = candidate.get("artifacts", {})
    checkpoint = artifacts.get("checkpoint", {})
    config = artifacts.get("config", {})
    if checkpoint.get("bytes") != CHECKPOINT_BYTES or checkpoint.get("sha256") != CHECKPOINT_SHA256:
        raise ValueError("Mega-53 checkpoint identity differs")
    if config.get("bytes") != CONFIG_BYTES or config.get("sha256") != CONFIG_SHA256:
        raise ValueError("Mega-53 configuration identity differs")
    download = candidate.get("download", {})
    if download.get("approved_cap_bytes") != APPROVED_TOTAL_BYTES:
        raise ValueError("Mega-53 approved cap differs")
    if download.get("observed_total_bytes") != CHECKPOINT_BYTES + CONFIG_BYTES:
        raise ValueError("Mega-53 combined byte count differs")
    if download.get("within_approved_cap") is not True:
        raise ValueError("Mega-53 artifact evidence exceeds approved cap")
    effects = candidate.get("effects", {})
    forbidden = (
        "checkpoint_deserialized",
        "torch_load_called",
        "dependency_installed",
        "model_imported",
        "model_constructed",
        "public_activation",
        "source_selection",
        "midi_created",
    )
    if any(effects.get(key) is not False for key in forbidden):
        raise ValueError("Mega-53 artifact evidence expands authority")
    if effects.get("inference_runs") != 0 or effects.get("audio_reads") != 0:
        raise ValueError("Mega-53 artifact evidence records execution")
    if not _SHA256_RE.fullmatch(digest):
        raise ValueError("Mega-53 evidence SHA-256 is invalid")
    return value
