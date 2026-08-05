"""Immutable receipts for audio derived from a prepared project source.

The ordinary source-import receipt proves an external original and its PCM24
canonicalisation.  A derived source has no second external original: its
canonical WAV is the generated evidence.  This separate schema keeps that
distinction explicit while binding the asset to its parent graph node and the
reviewed derivation evidence.
"""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .audio_formats import file_sha256
from .source_receipt import canonical_json_bytes


DERIVED_SOURCE_RECEIPT_SCHEMA = "sunofriend.derived-source-receipt.v1"
_FIELDS = frozenset(
    {
        "schema",
        "asset_id",
        "canonical",
        "parent",
        "derivation",
        "normalised",
        "network_used",
    }
)
_CANONICAL_FIELDS = frozenset(
    {
        "path",
        "sha256",
        "bytes",
        "sample_format",
        "sample_width_bytes",
        "sample_rate",
        "channels",
        "frames",
    }
)
_PARENT_FIELDS = frozenset({"node_id", "asset_id"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA256_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_NODE_ID_RE = re.compile(r"^node:[0-9a-f]{64}$")


def build_derived_source_receipt(
    *,
    canonical_path: str,
    canonical_sha256: str,
    canonical_bytes: int,
    sample_rate: int,
    channels: int,
    frames: int,
    parent_node_id: str,
    parent_asset_id: str,
    derivation: Mapping[str, Any],
) -> dict[str, Any]:
    """Build and validate one path-free derived-source receipt."""

    document = {
        "schema": DERIVED_SOURCE_RECEIPT_SCHEMA,
        "asset_id": f"sha256:{canonical_sha256}",
        "canonical": {
            "path": canonical_path,
            "sha256": canonical_sha256,
            "bytes": canonical_bytes,
            "sample_format": "pcm_s24le",
            "sample_width_bytes": 3,
            "sample_rate": sample_rate,
            "channels": channels,
            "frames": frames,
        },
        "parent": {
            "node_id": parent_node_id,
            "asset_id": parent_asset_id,
        },
        "derivation": dict(derivation),
        "normalised": False,
        "network_used": False,
    }
    validate_derived_source_receipt_document(document)
    return document


def write_derived_source_receipt(
    path: str | Path,
    receipt: Mapping[str, Any],
) -> Path:
    """Atomically create a canonical receipt without replacing evidence."""

    target = Path(path)
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"derived source receipt already exists: {target}")
    document = dict(receipt)
    validate_derived_source_receipt_document(document)
    target.parent.mkdir(parents=True, exist_ok=True)
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


def validate_derived_source_receipt_document(
    document: Mapping[str, Any],
) -> None:
    """Validate identity, parent and derivation pins without reading audio."""

    if set(document) != _FIELDS or document.get("schema") != DERIVED_SOURCE_RECEIPT_SCHEMA:
        raise ValueError("unsupported derived-source receipt schema or fields")
    if document.get("normalised") is not False:
        raise ValueError("derived source receipt must record normalised=false")
    if document.get("network_used") is not False:
        raise ValueError("derived source receipt must record network_used=false")

    canonical = _mapping(document.get("canonical"), "canonical")
    if set(canonical) != _CANONICAL_FIELDS:
        raise ValueError("derived source canonical fields are invalid")
    sha256 = _sha256(canonical.get("sha256"), "canonical.sha256")
    if document.get("asset_id") != f"sha256:{sha256}":
        raise ValueError("derived source asset_id must identify canonical audio")
    _safe_relative_path(canonical.get("path"), "canonical.path")
    for field in ("bytes", "sample_rate", "channels", "frames"):
        _positive_integer(canonical.get(field), f"canonical.{field}")
    if canonical.get("sample_format") != "pcm_s24le":
        raise ValueError("derived source canonical audio must be pcm_s24le")
    if canonical.get("sample_width_bytes") != 3:
        raise ValueError("derived source canonical sample width must be 3")

    parent = _mapping(document.get("parent"), "parent")
    if set(parent) != _PARENT_FIELDS:
        raise ValueError("derived source parent fields are invalid")
    if not _NODE_ID_RE.fullmatch(str(parent.get("node_id") or "")):
        raise ValueError("derived source parent.node_id is invalid")
    if not _SHA256_ID_RE.fullmatch(str(parent.get("asset_id") or "")):
        raise ValueError("derived source parent.asset_id is invalid")

    derivation = _mapping(document.get("derivation"), "derivation")
    process = derivation.get("process")
    if not isinstance(process, str) or not process.strip():
        raise ValueError("derived source derivation.process is invalid")
    if not _SHA256_ID_RE.fullmatch(str(derivation.get("evidence_id") or "")):
        raise ValueError("derived source derivation.evidence_id is invalid")
    _validate_json_value(derivation, label="derivation")


def validate_derived_source_receipt_files(
    document: Mapping[str, Any],
    *,
    root: str | Path,
) -> None:
    """Verify the canonical derived asset stays inside ``root`` and matches."""

    validate_derived_source_receipt_document(document)
    base = Path(root).absolute().resolve()
    canonical = _mapping(document["canonical"], "canonical")
    relative = _safe_relative_path(canonical["path"], "canonical.path")
    path = (base / Path(*relative.parts)).resolve()
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise ValueError("derived source canonical path escapes receipt root") from exc
    if not path.is_file() or path.is_symlink():
        raise ValueError("derived source canonical asset is missing or unsafe")
    if path.stat().st_size != canonical["bytes"]:
        raise ValueError("derived source canonical byte count does not match")
    if file_sha256(path) != canonical["sha256"]:
        raise ValueError("derived source canonical asset hash does not match")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sha256(value: Any, label: str) -> str:
    text = str(value or "")
    if not _SHA256_RE.fullmatch(text):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return text


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _safe_relative_path(value: Any, label: str) -> PurePosixPath:
    text = str(value or "")
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} must be a safe relative POSIX path")
    return path


def _validate_json_value(value: Any, *, label: str) -> None:
    if value is None or isinstance(value, (bool, int, float, str)):
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item, label=label)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{label} keys must be strings")
            _validate_json_value(item, label=label)
        return
    raise ValueError(f"{label} must contain only JSON values")


__all__ = [
    "DERIVED_SOURCE_RECEIPT_SCHEMA",
    "build_derived_source_receipt",
    "validate_derived_source_receipt_document",
    "validate_derived_source_receipt_files",
    "write_derived_source_receipt",
]
