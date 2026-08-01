"""Deterministic private PCM24 quarantine for precomputed MelRoFormer audio.

This is a model-independent output boundary. It accepts only bounded stereo
44.1 kHz arrays, creates one fresh owner-only quarantine, writes exactly the
fixed vocals/instrumental files, then reopens and verifies their bytes,
geometry and additive PCM reconstruction. It does not start a worker or grant
publication, selection or product authority.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import stat
import struct
import wave
from pathlib import Path
from typing import Any, Mapping

from .separation_contract import _canonical_json_bytes, _freeze_json


SCHEMA = "sunofriend.private-melroformer-pcm24-quarantine.v1"
POLICY_ID = "private-melroformer-fixed-two-role-pcm24-quarantine-v1"
SAMPLE_RATE = 44_100
CHANNELS = 2
BITS_PER_SAMPLE = 24
ROLES = ("instrumental", "vocals")
MINIMUM_PROBE_FRAMES = 4_096
MAXIMUM_EXCERPT_FRAMES = 661_500
_MAXIMUM_FILE_BYTES = 4 * 1024 * 1024
_MAXIMUM_RECONSTRUCTION_ERROR_LSB = 2
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _materialize_private_melroformer_pcm24_quarantine(
    *,
    destination: str | Path,
    source: Any,
    vocals: Any,
    instrumental: Any,
    np: Any,
) -> Mapping[str, Any]:
    """Create and independently verify one fresh, private two-role quarantine."""

    arrays = _validate_arrays(
        source=source,
        vocals=vocals,
        instrumental=instrumental,
        np=np,
    )
    root = Path(destination).expanduser().absolute()
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    os.chmod(root, 0o700)
    root_descriptor = _open_private_directory(root)
    try:
        os.mkdir("STEMS", mode=0o700, dir_fd=root_descriptor)
        stems_descriptor = os.open(
            "STEMS",
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=root_descriptor,
        )
        os.set_inheritable(stems_descriptor, False)
        try:
            claims = _write_outputs(
                stems_descriptor=stems_descriptor,
                arrays={
                    "instrumental": arrays["instrumental"],
                    "vocals": arrays["vocals"],
                },
                np=np,
            )
        finally:
            os.close(stems_descriptor)
    finally:
        os.close(root_descriptor)
    return _verify_private_melroformer_pcm24_quarantine(
        destination=root,
        source=arrays["source"],
        claims=claims,
        np=np,
    )


def _verify_private_melroformer_pcm24_quarantine(
    *,
    destination: str | Path,
    source: Any,
    claims: Mapping[str, Mapping[str, Any]],
    np: Any,
) -> Mapping[str, Any]:
    """Reopen the exact quarantine and return path-free parent evidence."""

    source_array = _validate_one_array(source, "source", np=np)
    if set(claims) != set(ROLES):
        raise ValueError("MelRoFormer PCM24 claims must cover both fixed roles")
    root = Path(destination).expanduser().absolute()
    root_descriptor = _open_private_directory(root)
    try:
        if sorted(os.listdir(root_descriptor)) != ["STEMS"]:
            raise ValueError("MelRoFormer PCM24 quarantine root entries differ")
        stems_descriptor = os.open(
            "STEMS",
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=root_descriptor,
        )
        os.set_inheritable(stems_descriptor, False)
        try:
            _require_private_directory_descriptor(stems_descriptor)
            expected_names = [f"{role}.wav" for role in ROLES]
            if sorted(os.listdir(stems_descriptor)) != expected_names:
                raise ValueError("MelRoFormer PCM24 quarantine output entries differ")
            outputs: list[dict[str, Any]] = []
            decoded: dict[str, Any] = {}
            for role in ROLES:
                output, samples = _verify_output(
                    stems_descriptor=stems_descriptor,
                    role=role,
                    claim=claims[role],
                    expected_frames=len(source_array),
                    np=np,
                )
                outputs.append(output)
                decoded[role] = samples
        finally:
            os.close(stems_descriptor)
    finally:
        os.close(root_descriptor)

    source_pcm24 = _quantize_pcm24(source_array, np=np)
    reconstruction = source_pcm24.astype(np.int64) - (
        decoded["vocals"].astype(np.int64)
        + decoded["instrumental"].astype(np.int64)
    )
    maximum = int(np.max(np.abs(reconstruction)))
    rms = float(np.sqrt(np.mean(reconstruction.astype(np.float64) ** 2)))
    if maximum > _MAXIMUM_RECONSTRUCTION_ERROR_LSB:
        raise ValueError("MelRoFormer persisted PCM24 reconstruction exceeds tolerance")
    payload = {
        "schema": SCHEMA,
        "policy_id": POLICY_ID,
        "status": "verified_quarantine_not_worker_bound",
        "source": {
            "sample_rate": SAMPLE_RATE,
            "channels": CHANNELS,
            "bits_per_sample": BITS_PER_SAMPLE,
            "frames": len(source_array),
            "pcm24_projection_sha256": hashlib.sha256(
                _pack_pcm24(source_pcm24, np=np)
            ).hexdigest(),
        },
        "outputs": outputs,
        "additive_reconstruction": {
            "equation": "source = vocals + instrumental",
            "maximum_integer_error_lsb": maximum,
            "root_mean_square_error_lsb": round(rms, 12),
            "permitted_maximum_integer_error_lsb": (
                _MAXIMUM_RECONSTRUCTION_ERROR_LSB
            ),
            "within_pcm24_tolerance": True,
        },
        "boundary": {
            "fresh_directory_created": True,
            "owner_only_directory_permissions": True,
            "exact_entry_allowlist_verified": True,
            "outputs_reopened_read_only_by_parent": True,
            "output_hashes_verified": True,
            "output_geometry_verified": True,
            "output_identity_stable_during_verification": True,
            "outside_write_denial_proven": False,
            "bound_to_worker": False,
        },
        "permissions": {
            "worker_start_permitted": False,
            "model_import_permitted": False,
            "automatic_selection_permitted": False,
            "source_graph_activation_permitted": False,
            "product_route_permitted": False,
            "publication_permitted": False,
        },
        "effects": {
            "filesystem_accessed": True,
            "filesystem_written": True,
            "output_files_created": True,
            "network_used": False,
            "process_started": False,
            "checkpoint_opened": False,
            "model_imported": False,
            "audio_inference_called": False,
        },
        "limitations": {
            "precomputed_arrays_only": True,
            "worker_execution_proven": False,
            "outside_write_denial_proven": False,
            "ordinary_files_can_change_after_verification": True,
            "publication_or_selection_authorized": False,
        },
    }
    document = {
        **payload,
        "evidence_sha256": hashlib.sha256(_canonical_json_bytes(payload)).hexdigest(),
    }
    return _validate_private_melroformer_pcm24_quarantine(document)


def _validate_private_melroformer_pcm24_quarantine(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Validate a path-free output-boundary observation without reopening files."""

    value = _plain(document)
    required = {
        "schema",
        "policy_id",
        "status",
        "source",
        "outputs",
        "additive_reconstruction",
        "boundary",
        "permissions",
        "effects",
        "limitations",
        "evidence_sha256",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("MelRoFormer PCM24 quarantine evidence fields differ")
    digest = value.pop("evidence_sha256")
    if not isinstance(digest, str) or not _SHA_RE.fullmatch(digest):
        raise ValueError("MelRoFormer PCM24 quarantine evidence hash is invalid")
    if digest != hashlib.sha256(_canonical_json_bytes(value)).hexdigest():
        raise ValueError("MelRoFormer PCM24 quarantine evidence self-hash differs")
    if (
        value["schema"] != SCHEMA
        or value["policy_id"] != POLICY_ID
        or value["status"] != "verified_quarantine_not_worker_bound"
    ):
        raise ValueError("MelRoFormer PCM24 quarantine evidence identity differs")
    source = value["source"]
    if (
        set(source)
        != {
            "sample_rate",
            "channels",
            "bits_per_sample",
            "frames",
            "pcm24_projection_sha256",
        }
        or source["sample_rate"] != SAMPLE_RATE
        or source["channels"] != CHANNELS
        or source["bits_per_sample"] != BITS_PER_SAMPLE
        or type(source["frames"]) is not int
        or not MINIMUM_PROBE_FRAMES <= source["frames"] <= MAXIMUM_EXCERPT_FRAMES
        or not _is_sha(source["pcm24_projection_sha256"])
    ):
        raise ValueError("MelRoFormer PCM24 quarantine source evidence differs")
    outputs = value["outputs"]
    if not isinstance(outputs, list) or [item.get("role") for item in outputs] != list(
        ROLES
    ):
        raise ValueError("MelRoFormer PCM24 quarantine outputs differ")
    for item in outputs:
        if (
            set(item)
            != {
                "role",
                "relative_path",
                "bytes",
                "sha256",
                "geometry",
                "owner_only_permissions",
                "read_only_parent_verification",
                "identity_stable_during_verification",
            }
            or item["relative_path"] != f"STEMS/{item['role']}.wav"
            or type(item["bytes"]) is not int
            or not 1 <= item["bytes"] <= _MAXIMUM_FILE_BYTES
            or not _is_sha(item["sha256"])
            or item["geometry"]
            != {
                "sample_rate": SAMPLE_RATE,
                "channels": CHANNELS,
                "bits_per_sample": BITS_PER_SAMPLE,
                "frames": source["frames"],
            }
            or any(
                item[key] is not True
                for key in (
                    "owner_only_permissions",
                    "read_only_parent_verification",
                    "identity_stable_during_verification",
                )
            )
        ):
            raise ValueError("MelRoFormer PCM24 quarantine output evidence differs")
    reconstruction = value["additive_reconstruction"]
    if (
        reconstruction.get("equation") != "source = vocals + instrumental"
        or type(reconstruction.get("maximum_integer_error_lsb")) is not int
        or not 0
        <= reconstruction["maximum_integer_error_lsb"]
        <= _MAXIMUM_RECONSTRUCTION_ERROR_LSB
        or not isinstance(reconstruction.get("root_mean_square_error_lsb"), float)
        or not math.isfinite(reconstruction["root_mean_square_error_lsb"])
        or reconstruction["root_mean_square_error_lsb"] < 0.0
        or reconstruction.get("permitted_maximum_integer_error_lsb")
        != _MAXIMUM_RECONSTRUCTION_ERROR_LSB
        or reconstruction.get("within_pcm24_tolerance") is not True
    ):
        raise ValueError("MelRoFormer PCM24 reconstruction evidence differs")
    if value["boundary"] != {
        "fresh_directory_created": True,
        "owner_only_directory_permissions": True,
        "exact_entry_allowlist_verified": True,
        "outputs_reopened_read_only_by_parent": True,
        "output_hashes_verified": True,
        "output_geometry_verified": True,
        "output_identity_stable_during_verification": True,
        "outside_write_denial_proven": False,
        "bound_to_worker": False,
    }:
        raise ValueError("MelRoFormer PCM24 quarantine boundary evidence differs")
    if value["permissions"] != {
        "worker_start_permitted": False,
        "model_import_permitted": False,
        "automatic_selection_permitted": False,
        "source_graph_activation_permitted": False,
        "product_route_permitted": False,
        "publication_permitted": False,
    }:
        raise ValueError("MelRoFormer PCM24 quarantine grants a permission")
    if value["effects"] != {
        "filesystem_accessed": True,
        "filesystem_written": True,
        "output_files_created": True,
        "network_used": False,
        "process_started": False,
        "checkpoint_opened": False,
        "model_imported": False,
        "audio_inference_called": False,
    }:
        raise ValueError("MelRoFormer PCM24 quarantine effects differ")
    if value["limitations"] != {
        "precomputed_arrays_only": True,
        "worker_execution_proven": False,
        "outside_write_denial_proven": False,
        "ordinary_files_can_change_after_verification": True,
        "publication_or_selection_authorized": False,
    }:
        raise ValueError("MelRoFormer PCM24 quarantine limitations differ")
    checked = {**value, "evidence_sha256": digest}
    if "/Users/" in json.dumps(checked, sort_keys=True) or "://" in json.dumps(
        checked, sort_keys=True
    ):
        raise ValueError("MelRoFormer PCM24 quarantine evidence is not path-free")
    return _freeze_json(checked)


def _validate_arrays(
    *, source: Any, vocals: Any, instrumental: Any, np: Any
) -> dict[str, Any]:
    arrays = {
        "source": _validate_one_array(source, "source", np=np),
        "vocals": _validate_one_array(vocals, "vocals", np=np),
        "instrumental": _validate_one_array(
            instrumental, "instrumental", np=np
        ),
    }
    if any(value.shape != arrays["source"].shape for value in arrays.values()):
        raise ValueError("MelRoFormer PCM24 arrays must share exact geometry")
    residual = arrays["source"].astype(np.float64) - (
        arrays["vocals"].astype(np.float64)
        + arrays["instrumental"].astype(np.float64)
    )
    if float(np.max(np.abs(residual))) > 1e-6:
        raise ValueError("MelRoFormer PCM24 arrays fail additive accounting")
    return arrays


def _validate_one_array(value: Any, label: str, *, np: Any) -> Any:
    array = np.asarray(value)
    if (
        array.ndim != 2
        or array.shape[1] != CHANNELS
        or not MINIMUM_PROBE_FRAMES <= len(array) <= MAXIMUM_EXCERPT_FRAMES
        or array.dtype not in (np.dtype("float32"), np.dtype("float64"))
        or not bool(np.isfinite(array).all())
        or bool((array < -1.0).any())
        or bool((array >= 1.0).any())
    ):
        raise ValueError(f"MelRoFormer PCM24 {label} array is invalid")
    return np.ascontiguousarray(array.astype(np.float32, copy=False))


def _write_outputs(
    *, stems_descriptor: int, arrays: Mapping[str, Any], np: Any
) -> dict[str, dict[str, Any]]:
    claims: dict[str, dict[str, Any]] = {}
    for role in ROLES:
        samples = _quantize_pcm24(arrays[role], np=np)
        contents = _canonical_pcm24_wav(samples, np=np)
        if len(contents) > _MAXIMUM_FILE_BYTES:
            raise ValueError("MelRoFormer PCM24 output exceeds its byte limit")
        descriptor = os.open(
            f"{role}.wav",
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=stems_descriptor,
        )
        try:
            os.set_inheritable(descriptor, False)
            view = memoryview(contents)
            offset = 0
            while offset < len(view):
                written = os.write(descriptor, view[offset:])
                if written <= 0:
                    raise OSError("MelRoFormer PCM24 write made no progress")
                offset += written
            os.fsync(descriptor)
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)
        claims[role] = {
            "role": role,
            "relative_path": f"STEMS/{role}.wav",
            "bytes": len(contents),
            "sha256": hashlib.sha256(contents).hexdigest(),
            "geometry": {
                "sample_rate": SAMPLE_RATE,
                "channels": CHANNELS,
                "bits_per_sample": BITS_PER_SAMPLE,
                "frames": len(samples),
            },
        }
    return claims


def _verify_output(
    *,
    stems_descriptor: int,
    role: str,
    claim: Mapping[str, Any],
    expected_frames: int,
    np: Any,
) -> tuple[dict[str, Any], Any]:
    if claim != {
        "role": role,
        "relative_path": f"STEMS/{role}.wav",
        "bytes": claim.get("bytes"),
        "sha256": claim.get("sha256"),
        "geometry": {
            "sample_rate": SAMPLE_RATE,
            "channels": CHANNELS,
            "bits_per_sample": BITS_PER_SAMPLE,
            "frames": expected_frames,
        },
    }:
        raise ValueError("MelRoFormer PCM24 output claim differs")
    if (
        type(claim["bytes"]) is not int
        or not 1 <= claim["bytes"] <= _MAXIMUM_FILE_BYTES
        or not _is_sha(claim["sha256"])
    ):
        raise ValueError("MelRoFormer PCM24 output claim identity differs")
    descriptor = os.open(
        f"{role}.wav",
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        dir_fd=stems_descriptor,
    )
    try:
        os.set_inheritable(descriptor, False)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_size != claim["bytes"]
        ):
            raise ValueError("MelRoFormer PCM24 output file identity differs")
        contents = _read_descriptor(descriptor, before.st_size)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if _stat_identity(before) != _stat_identity(after):
        raise ValueError("MelRoFormer PCM24 output changed during verification")
    if hashlib.sha256(contents).hexdigest() != claim["sha256"]:
        raise ValueError("MelRoFormer PCM24 output hash differs")
    samples = _parse_canonical_pcm24_wav(
        contents, expected_frames=expected_frames, np=np
    )
    return (
        {
            **dict(claim),
            "owner_only_permissions": True,
            "read_only_parent_verification": True,
            "identity_stable_during_verification": True,
        },
        samples,
    )


def _canonical_pcm24_wav(samples: Any, *, np: Any) -> bytes:
    stream = io.BytesIO()
    with wave.open(stream, "wb") as writer:
        writer.setnchannels(CHANNELS)
        writer.setsampwidth(BITS_PER_SAMPLE // 8)
        writer.setframerate(SAMPLE_RATE)
        writer.writeframes(_pack_pcm24(samples, np=np))
    return stream.getvalue()


def _parse_canonical_pcm24_wav(contents: bytes, *, expected_frames: int, np: Any) -> Any:
    expected_data_bytes = expected_frames * CHANNELS * 3
    if (
        len(contents) != 44 + expected_data_bytes
        or contents[:4] != b"RIFF"
        or struct.unpack("<I", contents[4:8])[0] != len(contents) - 8
        or contents[8:16] != b"WAVEfmt "
        or struct.unpack("<I", contents[16:20])[0] != 16
        or struct.unpack("<HHIIHH", contents[20:36])
        != (1, CHANNELS, SAMPLE_RATE, SAMPLE_RATE * CHANNELS * 3, CHANNELS * 3, 24)
        or contents[36:40] != b"data"
        or struct.unpack("<I", contents[40:44])[0] != expected_data_bytes
    ):
        raise ValueError("MelRoFormer output is not canonical PCM24 WAV")
    packed = np.frombuffer(contents, dtype=np.uint8, offset=44).reshape(-1, 3)
    unsigned = (
        packed[:, 0].astype(np.int32)
        | (packed[:, 1].astype(np.int32) << 8)
        | (packed[:, 2].astype(np.int32) << 16)
    )
    signed = np.where(unsigned & 0x800000, unsigned - 0x1000000, unsigned)
    return signed.astype(np.int32).reshape(expected_frames, CHANNELS)


def _quantize_pcm24(values: Any, *, np: Any) -> Any:
    quantized = np.rint(values.astype(np.float64) * 8_388_608.0)
    return quantized.astype(np.int32)


def _pack_pcm24(values: Any, *, np: Any) -> bytes:
    unsigned = values.astype(np.int32).reshape(-1) & 0xFFFFFF
    packed = np.empty((len(unsigned), 3), dtype=np.uint8)
    packed[:, 0] = unsigned & 0xFF
    packed[:, 1] = (unsigned >> 8) & 0xFF
    packed[:, 2] = (unsigned >> 16) & 0xFF
    return packed.tobytes()


def _open_private_directory(path: Path) -> int:
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    os.set_inheritable(descriptor, False)
    try:
        _require_private_directory_descriptor(descriptor)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _require_private_directory_descriptor(descriptor: int) -> None:
    attached = os.fstat(descriptor)
    if (
        os.get_inheritable(descriptor)
        or not stat.S_ISDIR(attached.st_mode)
        or attached.st_uid != os.geteuid()
        or stat.S_IMODE(attached.st_mode) != 0o700
    ):
        raise ValueError("MelRoFormer PCM24 quarantine directory is not private")


def _read_descriptor(descriptor: int, size: int) -> bytes:
    blocks: list[bytes] = []
    offset = 0
    while offset < size:
        block = os.pread(descriptor, min(1024 * 1024, size - offset), offset)
        if not block:
            raise ValueError("MelRoFormer PCM24 output is truncated")
        blocks.append(block)
        offset += len(block)
    return b"".join(blocks)


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
    )


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and _SHA_RE.fullmatch(value) is not None


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


__all__ = [
    "POLICY_ID",
    "SCHEMA",
    "_materialize_private_melroformer_pcm24_quarantine",
    "_validate_private_melroformer_pcm24_quarantine",
    "_verify_private_melroformer_pcm24_quarantine",
]
