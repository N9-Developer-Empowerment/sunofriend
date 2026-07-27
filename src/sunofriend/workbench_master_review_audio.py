"""Verified audio primitives shared by Listening Master review services.

The public review contracts deliberately remain in their service modules.
This internal module owns only bounded file verification, exact-frame decode,
deterministic review encoding and simple sample measurements.  Keeping those
operations here lets later review stages reuse the same security boundary
without adding mode flags to the blind matched-level v1 contract.
"""

from __future__ import annotations

import hashlib
import math
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any


MASTER_REVIEW_LEVEL_POLICY = "pairwise-fixed-window-rms-attenuation-only-v1"
MINIMUM_RMS_DBFS = -60.0
MAXIMUM_ATTENUATION_DB = 18.0
MAXIMUM_FINAL_RMS_MISMATCH_DB = 0.05
MAXIMUM_AUDIO_BYTES = 4 * 1024 * 1024 * 1024
FULL_SCALE_GUARD = 1.0

_BALANCED_CONTROL = "balanced_control"
_LISTENING_MASTER = "listening_master"


def pairwise_level_match(
    audio: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Attenuate only the louder of the two fixed-window review inputs."""

    np = numpy_module()
    if set(audio) != {_BALANCED_CONTROL, _LISTENING_MASTER}:
        raise ValueError("Listening Master review requires exactly two inputs")
    rms_values = {name: rms(np, values) for name, values in audio.items()}
    peaks = {
        name: float(np.max(np.abs(values))) if len(values) else 0.0
        for name, values in audio.items()
    }
    if any(
        not math.isfinite(value) or dbfs(value) < MINIMUM_RMS_DBFS
        for value in rms_values.values()
    ):
        raise ValueError(
            "Listening Master review audio is silent, non-finite, or below "
            f"{MINIMUM_RMS_DBFS:g} dBFS RMS"
        )
    if any(
        not math.isfinite(value) or value >= FULL_SCALE_GUARD
        for value in peaks.values()
    ):
        raise ValueError("Listening Master review audio is clipped or non-finite")
    target = min(rms_values.values())
    scales = {name: target / value for name, value in rms_values.items()}
    gains = {name: 20.0 * math.log10(scale) for name, scale in scales.items()}
    if any(gain < -MAXIMUM_ATTENUATION_DB for gain in gains.values()):
        raise ValueError(
            "Listening Master review candidates differ by more than "
            f"{MAXIMUM_ATTENUATION_DB:g} dB"
        )
    matched = {
        name: np.asarray(values * scales[name], dtype=np.float64)
        for name, values in audio.items()
    }
    after = {name: rms(np, values) for name, values in matched.items()}
    return matched, {
        "policy": MASTER_REVIEW_LEVEL_POLICY,
        "target_rms": round(target, 12),
        "minimum_rms_dbfs": MINIMUM_RMS_DBFS,
        "maximum_attenuation_db": MAXIMUM_ATTENUATION_DB,
        "limiter_used": False,
        "compression_used": False,
        "equalisation_used": False,
        "inputs": {
            name: {
                "rms_before": round(rms_values[name], 12),
                "rms_before_dbfs": round(dbfs(rms_values[name]), 6),
                "sample_peak_before": round(peaks[name], 12),
                "sample_peak_before_dbfs": round(dbfs(peaks[name]), 6),
                "linear_scale": round(scales[name], 12),
                "applied_gain_db": round(gains[name], 6),
                "rms_after": round(after[name], 12),
                "rms_after_dbfs": round(dbfs(after[name]), 6),
            }
            for name in (_BALANCED_CONTROL, _LISTENING_MASTER)
        },
    }


def read_audio_window(
    path: Path,
    *,
    expected: Mapping[str, Any],
    start_frame: int,
    frame_count: int,
    label: str,
) -> Any:
    """Hash-verify and decode one exact frame window from an owner-only file."""

    descriptor = open_owner_only_regular(path, label=label)
    before = os.fstat(descriptor)
    try:
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            total += len(block)
            if total > MAXIMUM_AUDIO_BYTES:
                raise ValueError(f"{label} exceeds the supported byte limit")
        if total != expected.get("bytes") or digest.hexdigest() != expected.get(
            "sha256"
        ):
            raise ValueError(f"{label} changed before review decoding")
        os.lseek(descriptor, 0, os.SEEK_SET)
        with os.fdopen(os.dup(descriptor), "rb") as handle:
            with soundfile_module().SoundFile(handle) as source:
                source.seek(start_frame)
                values = source.read(
                    frame_count,
                    dtype="float64",
                    always_2d=True,
                )
        after = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
        require_same_identity(before, after, current, total=total, label=label)
    finally:
        os.close(descriptor)
    np = numpy_module()
    if len(values) != frame_count or not np.all(np.isfinite(values)):
        raise ValueError(f"{label} review window is incomplete or non-finite")
    return values


def write_pcm16(path: Path, values: Any, sample_rate: int) -> None:
    """Write one deterministic private PCM16 WAV review crop."""

    soundfile_module().write(
        str(path),
        values,
        sample_rate,
        format="WAV",
        subtype="PCM_16",
    )
    path.chmod(0o600)
    require_owner_only_regular_file(path)


def verified_output_audio(
    path: Path,
    *,
    expected_frames: int,
    expected_sample_rate: int,
    expected_channels: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify one PCM16 review crop and return private and measured evidence."""

    record = private_file_record(
        path,
        label="review output",
        maximum_bytes=MAXIMUM_AUDIO_BYTES,
    )
    soundfile = soundfile_module()
    info = soundfile.info(str(path))
    values, sample_rate = soundfile.read(str(path), dtype="float64", always_2d=True)
    np = numpy_module()
    if (
        str(info.format) != "WAV"
        or str(info.subtype) != "PCM_16"
        or int(sample_rate) != expected_sample_rate
        or int(info.channels) != expected_channels
        or int(info.frames) != expected_frames
        or not np.all(np.isfinite(values))
    ):
        raise RuntimeError("Listening Master review output geometry changed")
    rms_value = rms(np, values)
    peak = float(np.max(np.abs(values))) if len(values) else 0.0
    if peak >= FULL_SCALE_GUARD:
        raise RuntimeError("Listening Master review output is clipped")
    return record, {
        "sample_rate": int(sample_rate),
        "channels": int(info.channels),
        "frames": int(info.frames),
        "rms_dbfs": round(dbfs(rms_value), 6),
        "sample_peak_dbfs": round(dbfs(peak), 6),
    }


def validated_private_record(value: Any, *, label: str) -> dict[str, Any]:
    """Validate a path-bearing immutable private file record."""

    if not isinstance(value, Mapping):
        raise ValueError(f"{label} record is invalid")
    path_value = value.get("path")
    if not isinstance(path_value, str) or not path_value:
        raise ValueError(f"{label} path is invalid")
    actual = private_file_record(
        absolute_path(path_value),
        label=label,
        maximum_bytes=MAXIMUM_AUDIO_BYTES,
    )
    if (
        value.get("name") != actual["name"]
        or value.get("bytes") != actual["bytes"]
        or value.get("sha256") != actual["sha256"]
    ):
        raise ValueError(f"{label} changed")
    return actual


def private_file_record(
    path: Path,
    *,
    label: str,
    maximum_bytes: int,
) -> dict[str, Any]:
    """Read and hash one stable owner-only regular file without following links."""

    canonical = absolute_path(path)
    descriptor = open_owner_only_regular(canonical, label=label)
    before = os.fstat(descriptor)
    try:
        if before.st_size > maximum_bytes:
            raise ValueError(f"{label} exceeds the supported byte limit")
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > maximum_bytes:
                raise ValueError(f"{label} exceeds the supported byte limit")
            digest.update(block)
        after = os.fstat(descriptor)
        current = os.stat(canonical, follow_symlinks=False)
        require_same_identity(before, after, current, total=total, label=label)
    finally:
        os.close(descriptor)
    return {
        "path": str(canonical),
        "name": canonical.name,
        "bytes": total,
        "sha256": digest.hexdigest(),
    }


def open_owner_only_regular(path: Path, *, label: str) -> int:
    """Open one owner-only regular file without following a final symlink."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"{label} is not a readable regular file") from exc
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or stat.S_IMODE(details.st_mode) & 0o077:
            raise ValueError(f"{label} is not an owner-only regular file")
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def require_same_identity(
    before: os.stat_result,
    after: os.stat_result,
    current: os.stat_result,
    *,
    total: int,
    label: str,
) -> None:
    """Reject a file that changed identity or metadata during a verified read."""

    identity = (
        int(before.st_dev),
        int(before.st_ino),
        int(before.st_size),
        int(before.st_mtime_ns),
        int(before.st_ctime_ns),
    )
    if total != int(before.st_size) or any(
        (
            int(value.st_dev),
            int(value.st_ino),
            int(value.st_size),
            int(value.st_mtime_ns),
            int(value.st_ctime_ns),
        )
        != identity
        for value in (after, current)
    ):
        raise ValueError(f"{label} changed while it was being read")


def require_owner_only_regular_file(path: Path) -> None:
    """Require a non-symlink regular file with no group/other permissions."""

    details = os.stat(path, follow_symlinks=False)
    if (
        path.is_symlink()
        or not stat.S_ISREG(details.st_mode)
        or stat.S_IMODE(details.st_mode) & 0o077
    ):
        raise ValueError("review storage must contain owner-only regular files")


def absolute_path(value: str | Path) -> Path:
    """Return one absolute final-component-no-symlink path."""

    expanded = Path(value).expanduser()
    absolute = Path(os.path.abspath(os.fspath(expanded)))
    if absolute.is_symlink():
        raise ValueError("review path must not be a symlink")
    return absolute.parent.resolve() / absolute.name


def rms(np: Any, values: Any) -> float:
    return float(np.sqrt(np.mean(np.square(values, dtype=np.float64))))


def dbfs(value: float) -> float:
    return 20.0 * math.log10(max(float(value), 1e-12))


def numpy_module() -> Any:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - dependency boundary
        raise RuntimeError(
            "Listening Master review requires NumPy; install Sunofriend audio extras"
        ) from exc
    return np


def soundfile_module() -> Any:
    try:
        import soundfile
    except ImportError as exc:  # pragma: no cover - dependency boundary
        raise RuntimeError(
            "Listening Master review requires SoundFile; install Sunofriend audio extras"
        ) from exc
    return soundfile


__all__ = [
    "FULL_SCALE_GUARD",
    "MASTER_REVIEW_LEVEL_POLICY",
    "MAXIMUM_ATTENUATION_DB",
    "MAXIMUM_AUDIO_BYTES",
    "MAXIMUM_FINAL_RMS_MISMATCH_DB",
    "MINIMUM_RMS_DBFS",
    "absolute_path",
    "dbfs",
    "numpy_module",
    "open_owner_only_regular",
    "pairwise_level_match",
    "private_file_record",
    "read_audio_window",
    "require_owner_only_regular_file",
    "require_same_identity",
    "rms",
    "soundfile_module",
    "validated_private_record",
    "verified_output_audio",
    "write_pcm16",
]
