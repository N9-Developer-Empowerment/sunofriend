"""Bounded, non-deserializing inspection for a local Safetensors file.

This private helper validates the documented container geometry and hashes the
exact regular file.  It parses only the bounded UTF-8 JSON header.  Tensor data
is hashed as opaque bytes and is never mapped into MLX, NumPy or Safetensors.
Nothing returned by this module authorises model loading or inference.
"""

from __future__ import annotations

import hashlib
import json
import os
import fcntl
import re
import stat
import struct
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA = "sunofriend.private-safetensors-static-inspection.v1"
MAX_FILE_BYTES = 8 * 1024 * 1024 * 1024
MAX_HEADER_BYTES = 16 * 1024 * 1024
MAX_TENSORS = 100_000
MAX_TENSOR_NAME_BYTES = 1024
MAX_RANK = 64
MAX_DIMENSION = (1 << 63) - 1
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_HEADER_SIZE = struct.Struct("<Q")
_DTYPE_BITS = {
    "BOOL": 8,
    "F4": 4,
    "F6_E2M3": 6,
    "F6_E3M2": 6,
    "U8": 8,
    "I8": 8,
    "F8_E5M2": 8,
    "F8_E4M3": 8,
    "F8_E8M0": 8,
    "F8_E4M3FNUZ": 8,
    "F8_E5M2FNUZ": 8,
    "I16": 16,
    "U16": 16,
    "F16": 16,
    "BF16": 16,
    "I32": 32,
    "U32": 32,
    "F32": 32,
    "C64": 64,
    "F64": 64,
    "I64": 64,
    "U64": 64,
}


def _inspect_private_safetensors(
    value: str | Path, *, expected_bytes: int, expected_sha256: str
) -> dict[str, Any]:
    """Hash and validate one exact local file without loading tensor values."""

    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("Safetensors path must be absolute")
    _validate_expected_identity(expected_bytes, expected_sha256)

    attached = path.lstat()
    if (
        stat.S_ISLNK(attached.st_mode)
        or not stat.S_ISREG(attached.st_mode)
        or attached.st_nlink != 1
    ):
        raise ValueError("Safetensors checkpoint must be a single-link regular file")
    if attached.st_size != expected_bytes:
        raise ValueError("Safetensors checkpoint byte count differs")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        os.set_inheritable(descriptor, False)
        opened = os.fstat(descriptor)
        if os.get_inheritable(descriptor) or _identity(opened) != _identity(attached):
            raise ValueError("Safetensors checkpoint changed before inspection")
        result = _inspect_private_safetensors_descriptor(
            descriptor,
            expected_bytes=expected_bytes,
            expected_sha256=expected_sha256,
        )
        after = os.fstat(descriptor)
        rebound = path.lstat()
        if _identity(after) != _identity(opened) or _identity(rebound) != _identity(
            opened
        ):
            raise ValueError("Safetensors checkpoint changed during inspection")
    finally:
        os.close(descriptor)

    path_result = dict(result)
    path_result.pop("descriptor_pinned")
    path_result.pop("path_retained")
    path_result["path"] = str(path)
    return path_result


def _inspect_private_safetensors_descriptor(
    descriptor: int,
    *,
    expected_bytes: int,
    expected_sha256: str,
) -> dict[str, Any]:
    """Inspect one already-open, non-inheritable read-only descriptor.

    The descriptor offset is unchanged and no pathname is resolved or retained.
    This is the static-inspection half of the future native fd5 checkpoint
    transport; it still grants no loading or execution authority.
    """

    _validate_expected_identity(expected_bytes, expected_sha256)
    if isinstance(descriptor, bool) or not isinstance(descriptor, int) or descriptor < 0:
        raise ValueError("Safetensors descriptor is invalid")
    try:
        attached = os.fstat(descriptor)
        inheritable = os.get_inheritable(descriptor)
        access_mode = fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE
    except OSError as error:
        raise ValueError("Safetensors descriptor is unavailable") from error
    if (
        inheritable
        or access_mode != os.O_RDONLY
        or not stat.S_ISREG(attached.st_mode)
        or attached.st_nlink != 1
        or attached.st_size != expected_bytes
    ):
        raise ValueError(
            "Safetensors descriptor must be non-inheritable read-only single-link "
            "regular file"
        )

    prefix = _pread_exact(descriptor, _HEADER_SIZE.size, 0)
    header_bytes = _HEADER_SIZE.unpack(prefix)[0]
    if not 2 <= header_bytes <= MAX_HEADER_BYTES:
        raise ValueError("Safetensors header size exceeds the inspection bound")
    if _HEADER_SIZE.size + header_bytes > expected_bytes:
        raise ValueError("Safetensors header extends beyond the file")
    header = _pread_exact(descriptor, header_bytes, _HEADER_SIZE.size)
    if not header.startswith(b"{"):
        raise ValueError("Safetensors header must begin with an object")
    parsed = _parse_unique_json(header)
    inventory = _validate_inventory(
        parsed, data_bytes=expected_bytes - _HEADER_SIZE.size - header_bytes
    )

    digest = hashlib.sha256()
    count = 0
    while count < expected_bytes:
        block = os.pread(descriptor, min(1024 * 1024, expected_bytes - count), count)
        if not block:
            raise ValueError("Safetensors checkpoint is truncated")
        count += len(block)
        digest.update(block)
    if (
        count != expected_bytes
        or digest.hexdigest() != expected_sha256
        or _identity(os.fstat(descriptor)) != _identity(attached)
    ):
        raise ValueError("Safetensors checkpoint SHA-256 differs")
    return {
        "schema": SCHEMA,
        "status": "verified_header_only_not_deserialized",
        "bytes": count,
        "sha256": digest.hexdigest(),
        "container": "safetensors",
        "header_bytes": header_bytes,
        "data_bytes": inventory["data_bytes"],
        "tensor_count": inventory["tensor_count"],
        "tensor_names_sha256": inventory["tensor_names_sha256"],
        "dtype_counts": inventory["dtype_counts"],
        "metadata_keys": inventory["metadata_keys"],
        "metadata_encoding": inventory["metadata_encoding"],
        "metadata_spec_conformant": inventory["metadata_spec_conformant"],
        "mlx_null_metadata_compatibility_applied": inventory[
            "mlx_null_metadata_compatibility_applied"
        ],
        "metadata_values_observed": False,
        "tensor_values_observed": False,
        "tensor_library_imported": False,
        "descriptor_pinned": True,
        "path_retained": False,
        "authorises_loading": False,
        "authorises_model_import": False,
        "authorises_inference": False,
        "effects": {
            "filesystem_accessed": True,
            "filesystem_written": False,
            "network_used": False,
            "package_installed": False,
            "tensor_deserialized": False,
            "model_imported": False,
            "process_started": False,
        },
    }


def _validate_expected_identity(expected_bytes: int, expected_sha256: str) -> None:
    if (
        isinstance(expected_bytes, bool)
        or not isinstance(expected_bytes, int)
        or not _HEADER_SIZE.size < expected_bytes <= MAX_FILE_BYTES
    ):
        raise ValueError("expected Safetensors byte count is invalid")
    if not isinstance(expected_sha256, str) or not _SHA_RE.fullmatch(
        expected_sha256
    ):
        raise ValueError("expected Safetensors SHA-256 is invalid")


def _pread_exact(descriptor: int, size: int, offset: int) -> bytes:
    payload = bytearray()
    while len(payload) < size:
        block = os.pread(descriptor, size - len(payload), offset + len(payload))
        if not block:
            raise ValueError("Safetensors checkpoint is truncated")
        payload.extend(block)
    return bytes(payload)


def _parse_unique_json(contents: bytes) -> dict[str, Any]:
    try:
        text = contents.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Safetensors header is not UTF-8") from error
    # The published format allows only ASCII spaces after the JSON object.
    if text.rstrip(" ") != text.rstrip():
        raise ValueError("Safetensors header has unsupported trailing whitespace")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("Safetensors header contains a duplicate key")
            result[key] = item
        return result

    try:
        parsed = json.loads(text, object_pairs_hook=unique)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("Safetensors header JSON is invalid") from error
    if not isinstance(parsed, dict):
        raise ValueError("Safetensors header must be an object")
    return parsed


def _validate_inventory(header: dict[str, Any], *, data_bytes: int) -> dict[str, Any]:
    metadata_value = header.get("__metadata__", {})
    if metadata_value is None:
        # The MLX conversion used by the pinned Kim Vocal 2 checkpoint writes
        # JSON null here.  Safetensors documents a string-to-string map, so do
        # not disguise this as standards-conformant metadata.  Treating null as
        # an empty map cannot enlarge or reinterpret the tensor inventory.
        metadata: dict[str, str] = {}
        metadata_encoding = "json_null_treated_as_empty_for_mlx_compatibility"
        metadata_spec_conformant = False
        mlx_null_metadata_compatibility_applied = True
    elif isinstance(metadata_value, dict) and all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in metadata_value.items()
    ):
        metadata = metadata_value
        metadata_encoding = "string_to_string_map"
        metadata_spec_conformant = True
        mlx_null_metadata_compatibility_applied = False
    else:
        raise ValueError("Safetensors metadata must map strings to strings or be null")
    tensor_items = [(key, value) for key, value in header.items() if key != "__metadata__"]
    if len(tensor_items) > MAX_TENSORS:
        raise ValueError("Safetensors tensor count exceeds the inspection bound")

    tensors: list[tuple[int, int, str, str]] = []
    dtype_counts: Counter[str] = Counter()
    for name, info in tensor_items:
        if (
            not isinstance(name, str)
            or not name
            or "\x00" in name
            or len(name.encode("utf-8")) > MAX_TENSOR_NAME_BYTES
        ):
            raise ValueError("Safetensors tensor name is invalid")
        if not isinstance(info, dict) or set(info) != {"dtype", "shape", "data_offsets"}:
            raise ValueError(f"Safetensors tensor entry is invalid: {name}")
        dtype = info["dtype"]
        shape = info["shape"]
        offsets = info["data_offsets"]
        if not isinstance(dtype, str) or dtype not in _DTYPE_BITS:
            raise ValueError(f"Safetensors dtype is unsupported: {name}")
        if not isinstance(shape, list) or len(shape) > MAX_RANK:
            raise ValueError(f"Safetensors shape is invalid: {name}")
        elements = 1
        for dimension in shape:
            if (
                isinstance(dimension, bool)
                or not isinstance(dimension, int)
                or not 0 <= dimension <= MAX_DIMENSION
            ):
                raise ValueError(f"Safetensors dimension is invalid: {name}")
            elements *= dimension
            if elements > MAX_FILE_BYTES * 8:
                raise ValueError(f"Safetensors shape exceeds the inspection bound: {name}")
        if (
            not isinstance(offsets, list)
            or len(offsets) != 2
            or any(isinstance(item, bool) or not isinstance(item, int) for item in offsets)
        ):
            raise ValueError(f"Safetensors offsets are invalid: {name}")
        begin, end = offsets
        if not 0 <= begin <= end <= data_bytes:
            raise ValueError(f"Safetensors offsets are outside the data buffer: {name}")
        bits = elements * _DTYPE_BITS[dtype]
        if bits % 8 or end - begin != bits // 8:
            raise ValueError(f"Safetensors shape, dtype and offsets disagree: {name}")
        tensors.append((begin, end, name, dtype))
        dtype_counts[dtype] += 1

    cursor = 0
    for begin, end, name, _dtype in sorted(tensors):
        if begin != cursor:
            raise ValueError(f"Safetensors data buffer has a hole or overlap: {name}")
        cursor = end
    if cursor != data_bytes:
        raise ValueError("Safetensors data buffer is not entirely indexed")

    names = sorted(name for _begin, _end, name, _dtype in tensors)
    names_bytes = json.dumps(names, ensure_ascii=False, separators=(",", ":")).encode()
    return {
        "data_bytes": data_bytes,
        "tensor_count": len(tensors),
        "tensor_names_sha256": hashlib.sha256(names_bytes).hexdigest(),
        "dtype_counts": dict(sorted(dtype_counts.items())),
        "metadata_keys": sorted(metadata),
        "metadata_encoding": metadata_encoding,
        "metadata_spec_conformant": metadata_spec_conformant,
        "mlx_null_metadata_compatibility_applied": (
            mlx_null_metadata_compatibility_applied
        ),
    }


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
    )


__all__ = [
    "_inspect_private_safetensors",
    "_inspect_private_safetensors_descriptor",
]
