"""Private exact-weight parity check for the Kim Vocal 2 MLX conversion.

The pinned upstream converter performs four material operations: extract a
state dictionary, remove training-only entries, split packed Q/K/V weights and
cast every retained value to BF16.  This module reproduces those operations
without importing the converter or an MLX model.  The original checkpoint is
opened only after its complete published identity is verified and is loaded
with PyTorch's restricted ``weights_only=True`` mode.

This is weight-conversion evidence, not inference-output parity, separator
quality, product eligibility or permission to publish a model.
"""

from __future__ import annotations

import hashlib
import json
import mmap
import os
import re
import stat
import struct
from pathlib import Path
from typing import Any, Callable, Mapping

from ._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
    SOURCE_CHECKPOINT_BYTES,
    SOURCE_CHECKPOINT_SHA256,
)
from ._separation_safetensors_inspection import (
    MAX_HEADER_BYTES,
    _parse_unique_json,
    _validate_inventory,
)


SCHEMA = "sunofriend.private-melroformer-weight-conversion-parity.v1"
POLICY_ID = "kim-vocal-2-exact-bf16-weight-conversion-parity-v1"
CONVERSION_TOOL_REVISION = "8380ab8"
EVIDENCE_NAME = "private-separation-melroformer-weight-conversion-parity.json"
EVIDENCE_BYTES = 1_989
EVIDENCE_SHA256 = (
    "7386eaa1d6e93f6b638e60780a589597737ffd3d7bcd48db5586ce93d8080a4c"
)
_HEADER_SIZE = struct.Struct("<Q")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_STRIP_PREFIXES = (
    "optimizer_states",
    "lr_schedulers",
    "callbacks",
    "hyper_parameters",
    "ema.",
    "ema_model.",
)
_STRIP_SUFFIXES = (
    ".num_batches_tracked",
    ".running_mean",
    ".running_var",
)
_QKV_SUFFIX = "to_qkv.weight"


def _verify_private_melroformer_weight_conversion(
    source_checkpoint: str | Path,
    converted_checkpoint: str | Path,
    *,
    checkpoint_loader: Callable[[Any], object] | None = None,
    expected_source_bytes: int = SOURCE_CHECKPOINT_BYTES,
    expected_source_sha256: str = SOURCE_CHECKPOINT_SHA256,
    expected_converted_bytes: int = CONVERSION_CHECKPOINT_BYTES,
    expected_converted_sha256: str = CONVERSION_CHECKPOINT_SHA256,
) -> dict[str, Any]:
    """Verify the exact deterministic BF16 conversion without model inference."""

    source_path = _absolute_path(source_checkpoint, "source checkpoint")
    converted_path = _absolute_path(converted_checkpoint, "converted checkpoint")
    source_fd, source_identity = _open_verified_regular(
        source_path,
        expected_bytes=expected_source_bytes,
        expected_sha256=expected_source_sha256,
        label="source checkpoint",
    )
    converted_fd = -1
    converted_map: mmap.mmap | None = None
    try:
        converted_fd, converted_identity = _open_verified_regular(
            converted_path,
            expected_bytes=expected_converted_bytes,
            expected_sha256=expected_converted_sha256,
            label="converted checkpoint",
        )
        target_entries, data_start, target_inventory = _target_entries(
            converted_fd, expected_bytes=expected_converted_bytes
        )
        if target_inventory["dtype_counts"] != {
            "BF16": target_inventory["tensor_count"]
        }:
            raise ValueError("converted checkpoint contains a non-BF16 tensor")

        loader = checkpoint_loader or _load_checkpoint_weights_only
        with os.fdopen(os.dup(source_fd), "rb", closefd=True) as source_handle:
            root = loader(source_handle)
        state = _extract_state_dict(root)
        normalized = _normalise_model_prefix(state)
        filtered = {
            key: value
            for key, value in normalized.items()
            if not _should_strip(key)
        }
        expected_names = _converted_names(filtered)
        if set(expected_names) != set(target_entries):
            missing = sorted(set(expected_names) - set(target_entries))
            unexpected = sorted(set(target_entries) - set(expected_names))
            raise ValueError(
                "converted checkpoint tensor names differ: "
                f"missing={missing[:8]!r}, unexpected={unexpected[:8]!r}"
            )

        np = _numpy()
        converted_map = mmap.mmap(converted_fd, 0, access=mmap.ACCESS_READ)
        manifest_rows: list[dict[str, Any]] = []
        qkv_split_count = 0
        source_float32_bytes = 0
        converted_bf16_bytes = 0
        for source_name in sorted(filtered):
            array = _source_float32_array(filtered[source_name], np=np)
            source_float32_bytes += int(array.nbytes)
            if source_name.endswith(_QKV_SUFFIX):
                if array.ndim == 0 or array.shape[0] % 3:
                    raise ValueError("packed QKV first dimension is not divisible by three")
                qkv_split_count += 1
                prefix = source_name[: -len(_QKV_SUFFIX)]
                third = array.shape[0] // 3
                parts = (
                    (f"{prefix}to_q.weight", array[:third]),
                    (f"{prefix}to_k.weight", array[third : 2 * third]),
                    (f"{prefix}to_v.weight", array[2 * third :]),
                )
            else:
                parts = ((source_name, array),)
            for target_name, part in parts:
                entry = target_entries[target_name]
                shape = tuple(int(item) for item in part.shape)
                if entry["dtype"] != "BF16" or tuple(entry["shape"]) != shape:
                    raise ValueError(
                        f"converted checkpoint tensor geometry differs: {target_name}"
                    )
                expected_payload = _float32_to_bf16_bytes(part, np=np)
                begin = data_start + entry["begin"]
                end = data_start + entry["end"]
                if len(expected_payload) != end - begin:
                    raise ValueError(
                        f"converted checkpoint tensor byte count differs: {target_name}"
                    )
                target_view = memoryview(converted_map)[begin:end]
                try:
                    expected_sha256 = hashlib.sha256(expected_payload).hexdigest()
                    target_sha256 = hashlib.sha256(target_view).hexdigest()
                finally:
                    target_view.release()
                if expected_sha256 != target_sha256:
                    raise ValueError(
                        f"converted checkpoint tensor values differ: {target_name}"
                    )
                converted_bf16_bytes += len(expected_payload)
                manifest_rows.append(
                    {
                        "name": target_name,
                        "shape": list(shape),
                        "dtype": "BF16",
                        "payload_sha256": target_sha256,
                    }
                )

        manifest_rows.sort(key=lambda item: item["name"])
        manifest_sha256 = hashlib.sha256(
            json.dumps(manifest_rows, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
        _revalidate_open_file(
            source_fd,
            source_path,
            source_identity,
            expected_sha256=expected_source_sha256,
            label="source checkpoint",
        )
        _revalidate_open_file(
            converted_fd,
            converted_path,
            converted_identity,
            expected_sha256=expected_converted_sha256,
            label="converted checkpoint",
        )
    finally:
        if converted_map is not None:
            converted_map.close()
        if converted_fd >= 0:
            os.close(converted_fd)
        os.close(source_fd)

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "verified_exact_bf16_weight_conversion",
        "policy_id": POLICY_ID,
        "conversion_tool_revision": CONVERSION_TOOL_REVISION,
        "source": {
            "bytes": expected_source_bytes,
            "sha256": expected_source_sha256,
            "load_policy": "torch-load-weights-only-true-from-verified-open-file",
            "state_dict_key_count": len(state),
            "normalized_key_count": len(normalized),
            "retained_key_count": len(filtered),
            "float32_payload_bytes": source_float32_bytes,
        },
        "converted": {
            "bytes": expected_converted_bytes,
            "sha256": expected_converted_sha256,
            "tensor_count": len(target_entries),
            "bf16_payload_bytes": converted_bf16_bytes,
            "qkv_split_count": qkv_split_count,
            "tensor_payload_manifest_sha256": manifest_sha256,
        },
        "claims": {
            "every_retained_source_weight_accounted_for": True,
            "every_converted_weight_accounted_for": True,
            "tensor_names_exact": True,
            "tensor_shapes_exact": True,
            "bf16_tensor_payloads_bit_exact": True,
            "weight_conversion_parity_independently_verified": True,
            "inference_output_parity_independently_verified": False,
            "separator_quality_measured": False,
            "winner_selected": False,
        },
        "permissions": {
            "simple_mode": False,
            "studio_mode": False,
            "source_graph": False,
            "automatic_selection": False,
            "automatic_promotion": False,
            "checkpoint_publication": False,
        },
        "effects": {
            "filesystem_accessed": True,
            "filesystem_written": False,
            "network_used": False,
            "checkpoint_deserialized": True,
            "restricted_weights_only_load": True,
            "model_imported": False,
            "model_inference": False,
            "audio_read": False,
            "audio_written": False,
            "process_started": False,
            "product_route_changed": False,
        },
    }
    report["document_sha256"] = _document_sha256(report)
    return report


def _verify_tracked_weight_conversion_evidence(
    repository_root: str | Path,
) -> dict[str, Any]:
    """Verify and read the path-free tracked observation without model access."""

    root = _absolute_path(repository_root, "repository root")
    attached = root.lstat()
    if stat.S_ISLNK(attached.st_mode) or not stat.S_ISDIR(attached.st_mode):
        raise ValueError("repository root must be a non-symlink directory")
    descriptor, _ = _open_verified_regular(
        root / EVIDENCE_NAME,
        expected_bytes=EVIDENCE_BYTES,
        expected_sha256=EVIDENCE_SHA256,
        label="weight-conversion evidence",
    )
    try:
        encoded = os.pread(descriptor, EVIDENCE_BYTES, 0)
    finally:
        os.close(descriptor)
    evidence = _parse_unique_json(encoded[:-1] if encoded.endswith(b"\n") else encoded)
    if (
        evidence.get("schema") != SCHEMA
        or evidence.get("policy_id") != POLICY_ID
        or evidence.get("status") != "verified_exact_bf16_weight_conversion"
        or evidence.get("document_sha256") != _document_sha256(evidence)
    ):
        raise ValueError("weight-conversion evidence semantics differ")
    claims = evidence.get("claims")
    if not isinstance(claims, dict) or claims != {
        "bf16_tensor_payloads_bit_exact": True,
        "every_converted_weight_accounted_for": True,
        "every_retained_source_weight_accounted_for": True,
        "inference_output_parity_independently_verified": False,
        "separator_quality_measured": False,
        "tensor_names_exact": True,
        "tensor_shapes_exact": True,
        "weight_conversion_parity_independently_verified": True,
        "winner_selected": False,
    }:
        raise ValueError("weight-conversion evidence claims differ")
    return evidence


def _load_checkpoint_weights_only(handle: Any) -> object:
    try:
        import torch
    except ImportError as error:  # pragma: no cover - private runtime preflight
        raise RuntimeError("PyTorch is required for conversion parity") from error
    return torch.load(handle, map_location="cpu", weights_only=True)


def _target_entries(
    descriptor: int, *, expected_bytes: int
) -> tuple[dict[str, dict[str, Any]], int, dict[str, Any]]:
    prefix = os.pread(descriptor, _HEADER_SIZE.size, 0)
    if len(prefix) != _HEADER_SIZE.size:
        raise ValueError("converted checkpoint header is truncated")
    header_bytes = _HEADER_SIZE.unpack(prefix)[0]
    if not 2 <= header_bytes <= MAX_HEADER_BYTES:
        raise ValueError("converted checkpoint header exceeds the inspection bound")
    encoded = os.pread(descriptor, header_bytes, _HEADER_SIZE.size)
    if len(encoded) != header_bytes:
        raise ValueError("converted checkpoint header is truncated")
    header = _parse_unique_json(encoded)
    data_start = _HEADER_SIZE.size + header_bytes
    inventory = _validate_inventory(header, data_bytes=expected_bytes - data_start)
    entries: dict[str, dict[str, Any]] = {}
    for name, value in header.items():
        if name == "__metadata__":
            continue
        begin, end = value["data_offsets"]
        entries[name] = {
            "dtype": value["dtype"],
            "shape": tuple(value["shape"]),
            "begin": begin,
            "end": end,
        }
    return entries, data_start, inventory


def _extract_state_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("source checkpoint root must be a dictionary")
    state = value.get("state_dict")
    if isinstance(state, dict):
        value = state
    if not all(isinstance(key, str) and key for key in value):
        raise ValueError("source checkpoint state dictionary has an invalid key")
    return dict(value)


def _normalise_model_prefix(state: Mapping[str, object]) -> dict[str, object]:
    if not any(key.startswith("model.") for key in state):
        return dict(state)
    result: dict[str, object] = {}
    for key, value in state.items():
        normalized = key[len("model.") :] if key.startswith("model.") else key
        if normalized in result:
            raise ValueError("source checkpoint model-prefix normalization collides")
        result[normalized] = value
    return result


def _should_strip(key: str) -> bool:
    return key.startswith(_STRIP_PREFIXES) or key.endswith(_STRIP_SUFFIXES)


def _converted_names(state: Mapping[str, object]) -> list[str]:
    names: list[str] = []
    for key in state:
        if key.endswith(_QKV_SUFFIX):
            prefix = key[: -len(_QKV_SUFFIX)]
            names.extend(
                (
                    f"{prefix}to_q.weight",
                    f"{prefix}to_k.weight",
                    f"{prefix}to_v.weight",
                )
            )
        else:
            names.append(key)
    if len(names) != len(set(names)):
        raise ValueError("source checkpoint conversion produces a key collision")
    return names


def _source_float32_array(value: object, *, np: Any) -> Any:
    if hasattr(value, "detach"):
        value = value.detach().cpu().float().numpy()
    array = np.asarray(value, dtype=np.dtype("<f4"), order="C")
    if not np.isfinite(array).all():
        raise ValueError("source checkpoint contains a non-finite weight")
    return np.ascontiguousarray(array)


def _float32_to_bf16_bytes(value: Any, *, np: Any) -> bytes:
    array = np.ascontiguousarray(value, dtype=np.dtype("<f4"))
    bits = array.view(np.dtype("<u4"))
    # Round-to-nearest-even: add 0x7fff plus the retained-low-bit tie breaker.
    rounded = bits + np.uint32(0x7FFF) + ((bits >> np.uint32(16)) & np.uint32(1))
    bf16 = (rounded >> np.uint32(16)).astype(np.dtype("<u2"), copy=False)
    return bf16.tobytes(order="C")


def _open_verified_regular(
    path: Path, *, expected_bytes: int, expected_sha256: str, label: str
) -> tuple[int, tuple[int, int, int, int, int, int]]:
    if (
        isinstance(expected_bytes, bool)
        or not isinstance(expected_bytes, int)
        or expected_bytes <= 0
        or not isinstance(expected_sha256, str)
        or not _SHA_RE.fullmatch(expected_sha256)
    ):
        raise ValueError(f"expected {label} identity is invalid")
    attached = path.lstat()
    if (
        stat.S_ISLNK(attached.st_mode)
        or not stat.S_ISREG(attached.st_mode)
        or attached.st_nlink != 1
        or attached.st_size != expected_bytes
    ):
        raise ValueError(f"{label} is not the expected single-link regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        os.set_inheritable(descriptor, False)
        opened = os.fstat(descriptor)
        identity = _identity(opened)
        if os.get_inheritable(descriptor) or identity != _identity(attached):
            raise ValueError(f"{label} changed before opening")
        if _hash_descriptor(descriptor, expected_bytes=expected_bytes) != expected_sha256:
            raise ValueError(f"{label} SHA-256 differs")
        return descriptor, identity
    except Exception:
        os.close(descriptor)
        raise


def _revalidate_open_file(
    descriptor: int,
    path: Path,
    identity: tuple[int, int, int, int, int, int],
    *,
    expected_sha256: str,
    label: str,
) -> None:
    opened = os.fstat(descriptor)
    rebound = path.lstat()
    if _identity(opened) != identity or _identity(rebound) != identity:
        raise ValueError(f"{label} changed during conversion parity")
    if _hash_descriptor(descriptor, expected_bytes=opened.st_size) != expected_sha256:
        raise ValueError(f"{label} SHA-256 changed during conversion parity")


def _hash_descriptor(descriptor: int, *, expected_bytes: int) -> str:
    digest = hashlib.sha256()
    offset = 0
    while offset < expected_bytes:
        block = os.pread(descriptor, min(1024 * 1024, expected_bytes - offset), offset)
        if not block:
            raise ValueError("checkpoint ended during hashing")
        digest.update(block)
        offset += len(block)
    return digest.hexdigest()


def _absolute_path(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{label} path must be absolute")
    return path


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
    )


def _numpy() -> Any:
    try:
        import numpy as np
    except ImportError as error:  # pragma: no cover - private runtime preflight
        raise RuntimeError("NumPy is required for conversion parity") from error
    return np


def _document_sha256(value: Mapping[str, Any]) -> str:
    document = dict(value)
    document.pop("document_sha256", None)
    return hashlib.sha256(
        json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


__all__ = [
    "CONVERSION_TOOL_REVISION",
    "EVIDENCE_BYTES",
    "EVIDENCE_NAME",
    "EVIDENCE_SHA256",
    "POLICY_ID",
    "SCHEMA",
    "_document_sha256",
    "_float32_to_bf16_bytes",
    "_verify_private_melroformer_weight_conversion",
    "_verify_tracked_weight_conversion_evidence",
]
