"""Immutable, deterministic receipts for imported source audio."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .audio_formats import file_sha256


SOURCE_IMPORT_SCHEMA = "sunofriend.source-import.v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class SourceImportReceipt:
    """Serializable evidence for one original-to-canonical decode."""

    source_id: str
    original: Mapping[str, Any]
    canonical: Mapping[str, Any]
    clock: Mapping[str, Any]
    decoder: Mapping[str, Any]
    limits: Mapping[str, Any]
    normalised: bool = False
    network_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SOURCE_IMPORT_SCHEMA,
            "source_id": self.source_id,
            "original": dict(self.original),
            "canonical": dict(self.canonical),
            "clock": dict(self.clock),
            "decoder": dict(self.decoder),
            "limits": dict(self.limits),
            "normalised": self.normalised,
            "network_used": self.network_used,
        }


def canonical_json_bytes(document: Mapping[str, Any]) -> bytes:
    """Return the repository's stable JSON representation."""

    return (_render_finite_json(document) + "\n").encode("utf-8")


def _render_finite_json(document: Mapping[str, Any]) -> str:
    """Own finite-number enforcement and its stable public error."""

    try:
        return json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    except ValueError as error:
        raise ValueError("document values must be finite JSON numbers") from error


def document_sha256(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(document)).hexdigest()


def write_source_receipt(
    path: str | Path,
    receipt: SourceImportReceipt | Mapping[str, Any],
) -> Path:
    """Atomically create a receipt without replacing an existing one."""

    target = Path(path)
    if target.exists():
        raise FileExistsError(f"source receipt already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    document = (
        receipt.to_dict() if isinstance(receipt, SourceImportReceipt) else dict(receipt)
    )
    validate_source_receipt_document(document)
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(canonical_json_bytes(document))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def validate_source_receipt_document(document: Mapping[str, Any]) -> None:
    """Validate schema and immutable identity fields without reading files."""

    if document.get("schema") != SOURCE_IMPORT_SCHEMA:
        raise ValueError("unsupported source-import receipt schema")
    if document.get("normalised") is not False:
        raise ValueError("source import must record normalised=false")
    if document.get("network_used") is not False:
        raise ValueError("local source import must record network_used=false")
    original = _mapping(document.get("original"), "original")
    canonical = _mapping(document.get("canonical"), "canonical")
    _mapping(document.get("clock"), "clock")
    decoder = _mapping(document.get("decoder"), "decoder")
    _mapping(document.get("limits"), "limits")
    original_sha = _sha256_value(original.get("sha256"), "original.sha256")
    _sha256_value(canonical.get("sha256"), "canonical.sha256")
    source_id = document.get("source_id")
    if source_id != f"sha256:{original_sha}":
        raise ValueError("source_id must be the original SHA-256 identity")
    _safe_relative_path(original.get("path"), "original.path")
    _safe_relative_path(canonical.get("path"), "canonical.path")
    if canonical.get("sample_format") != "pcm_s24le":
        raise ValueError("canonical sample_format must be pcm_s24le")
    if canonical.get("sample_width_bytes") != 3:
        raise ValueError("canonical sample_width_bytes must be 3")
    if decoder.get("network_protocols") != ["file"]:
        raise ValueError("decoder network_protocols must contain only file")
    arguments = decoder.get("arguments")
    if not isinstance(arguments, list) or not all(
        isinstance(item, str) for item in arguments
    ):
        raise ValueError("decoder.arguments must be a list of strings")
    if any("://" in item for item in arguments):
        raise ValueError("decoder arguments must not contain a URL")


def validate_source_receipt_files(
    document: Mapping[str, Any],
    *,
    root: str | Path,
) -> None:
    """Verify that receipt paths remain within ``root`` and match their hashes."""

    validate_source_receipt_document(document)
    base = Path(root).absolute().resolve()
    for section_name in ("original", "canonical"):
        section = _mapping(document[section_name], section_name)
        relative = _safe_relative_path(section["path"], f"{section_name}.path")
        path = (base / Path(*relative.parts)).resolve()
        try:
            path.relative_to(base)
        except ValueError as exc:
            raise ValueError(f"{section_name} path escapes receipt root") from exc
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"{section_name} receipt asset is missing or unsafe")
        if file_sha256(path) != section["sha256"]:
            raise ValueError(f"{section_name} receipt asset hash does not match")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sha256_value(value: Any, label: str) -> str:
    text = str(value or "")
    if not _SHA256_RE.fullmatch(text):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return text


def _safe_relative_path(value: Any, label: str) -> PurePosixPath:
    text = str(value or "")
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} must be a safe relative POSIX path")
    return path


__all__ = [
    "SOURCE_IMPORT_SCHEMA",
    "SourceImportReceipt",
    "canonical_json_bytes",
    "document_sha256",
    "validate_source_receipt_document",
    "validate_source_receipt_files",
    "write_source_receipt",
]
