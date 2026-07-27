"""Public immutable contract and verifier for Listening Master v2 artifacts.

The mastering renderer and every consumer share this module so a schema or
policy change cannot leave a verifier interpreting receipts with duplicated
constants.  Verification is read-only, rejects symlinks and file drift, and
returns only receipt data, hashes, names and measurements: no local path is
included in the result.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from copy import deepcopy
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


LISTENING_MASTER_SCHEMA = "sunofriend.listening-master.v2"
LISTENING_MASTER_VERIFICATION_SCHEMA = (
    "sunofriend.listening-master-verification.v1"
)
LISTENING_MASTER_POLICY = "ffmpeg-loudnorm-two-pass-fixed-horizon-v1"
FFMPEG_IDENTITY_POLICY = "stat-and-sha256-before-after-every-pass-v1"
LISTENING_MASTER_TIMING_POLICY = "retain-input-frame-horizon-v1"
LISTENING_MASTER_LABEL = "Balanced MIDI listening master challenger"
LISTENING_MASTER_SCOPE = (
    "two-pass integrated-loudness normalisation and true-peak limiting for "
    "comparative listening; not a human-approved release master"
)
ENCODED_ARTIFACT_LABEL = "encoded_pcm24_output"

TARGET_INTEGRATED_LUFS = -16.0
TARGET_LOUDNESS_RANGE_LU = 11.0
TRUE_PEAK_CEILING_DBTP = -1.0
INTEGRATED_LOUDNESS_TOLERANCE_LU = 0.2
TRUE_PEAK_TOLERANCE_DB = 0.05

LISTENING_MASTER_TARGETS = MappingProxyType(
    {
        "integrated_lufs": TARGET_INTEGRATED_LUFS,
        "loudness_range_lu": TARGET_LOUDNESS_RANGE_LU,
        "true_peak_ceiling_dbtp": TRUE_PEAK_CEILING_DBTP,
        "integrated_loudness_tolerance_lu": (
            INTEGRATED_LOUDNESS_TOLERANCE_LU
        ),
        "true_peak_tolerance_db": TRUE_PEAK_TOLERANCE_DB,
    }
)
LISTENING_MASTER_EFFECTS = MappingProxyType(
    {
        "source_audio_mutated": False,
        "source_audio_overwritten": False,
        "midi_mutated": False,
        "selection_changed": False,
        "feedback_recorded": False,
        "automatic_selection": False,
        "automatic_ranking": False,
        "default_selection_changed": False,
        "control_balance_replaced": False,
        "listening_master_created": True,
    }
)
LISTENING_MASTER_PROCESSING_FLAGS = MappingProxyType(
    {
        "integrated_loudness_normalisation": True,
        "true_peak_limiting": True,
        "encoded_artifact_verified": True,
        "equalisation": False,
        "stereo_widening": False,
        "reverb": False,
        "chorus": False,
        "saturation": False,
    }
)
LOUDNORM_FIELDS = frozenset(
    {
        "input_i",
        "input_tp",
        "input_lra",
        "input_thresh",
        "output_i",
        "output_tp",
        "output_lra",
        "output_thresh",
        "normalization_type",
        "target_offset",
    }
)

MAXIMUM_RECEIPT_BYTES = 4 * 1024 * 1024
MAXIMUM_AUDIO_BYTES = 4 * 1024 * 1024 * 1024
_SHA256_LENGTH = 64
_RECEIPT_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema",
        "status",
        "policy",
        "label",
        "mastered",
        "release_master",
        "mastering_scope",
        "source",
        "targets",
        "analysis_pass",
        "render_pass",
        "verification_pass",
        "renderer",
        "output",
        "timing",
        "processing",
        "effects",
        "receipt_sha256",
    }
)


def verify_listening_master_artifacts(
    source_path: str | Path,
    master_path: str | Path,
    receipt_path: str | Path,
) -> dict[str, Any]:
    """Verify one exact control/master/receipt set and return path-free facts.

    ``source_path`` is the unchanged balanced MIDI-derived WAV used to create
    the challenger. ``master_path`` must be the receipt-bound PCM24 output.
    The returned ``receipt`` is the exact, already path-free receipt document;
    ``receipt_file`` binds its serialized bytes separately from its semantic
    self-hash.
    """

    source = _canonical_file_path(source_path, label="listening-master source")
    master = _canonical_file_path(master_path, label="listening-master WAV")
    receipt = _canonical_file_path(
        receipt_path, label="listening-master receipt"
    )
    if source.suffix.lower() != ".wav":
        raise ValueError("listening-master source must be a .wav file")
    if master.suffix.lower() != ".wav":
        raise ValueError("listening-master audition must be a .wav file")
    if receipt.suffix.lower() != ".json":
        raise ValueError("listening-master receipt must be a .json file")
    if len({source, master, receipt}) != 3:
        raise ValueError("listening-master source, WAV and receipt must differ")

    source_file, source_info = _read_audio_file(
        source,
        label="listening-master source",
        maximum_bytes=MAXIMUM_AUDIO_BYTES,
        require_pcm24=False,
    )
    master_file, master_info = _read_audio_file(
        master,
        label="listening-master WAV",
        maximum_bytes=MAXIMUM_AUDIO_BYTES,
        require_pcm24=True,
    )
    receipt_bytes, receipt_file = _read_regular_bytes(
        receipt,
        label="listening-master receipt",
        maximum_bytes=MAXIMUM_RECEIPT_BYTES,
    )
    try:
        document = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "listening-master receipt is not valid UTF-8 JSON"
        ) from exc
    if not isinstance(document, dict):
        raise ValueError("listening-master receipt must contain one JSON object")

    verified = _verify_receipt_document(
        document,
        source_file=source_file,
        source_info=source_info,
        master_name=master.name,
        master_file=master_file,
        master_info=master_info,
    )
    return {
        "schema": LISTENING_MASTER_VERIFICATION_SCHEMA,
        "status": "verified",
        "receipt_schema": LISTENING_MASTER_SCHEMA,
        "policy": LISTENING_MASTER_POLICY,
        "mastered": True,
        "release_master": False,
        "receipt_document_sha256": verified["receipt_document_sha256"],
        "receipt_file": receipt_file,
        "source": verified["source"],
        "master": verified["output"],
        "targets": dict(LISTENING_MASTER_TARGETS),
        "measurements": {
            "analysis": verified["analysis"],
            "render": verified["render"],
            "verification": verified["verification"],
        },
        "renderer": verified["renderer"],
        "timing": verified["timing"],
        "processing": verified["processing"],
        "effects": dict(LISTENING_MASTER_EFFECTS),
        "receipt": deepcopy(document),
    }


def validated_loudnorm_stats(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return the canonical bounded representation of loudnorm measurements."""

    if not isinstance(value, Mapping) or not LOUDNORM_FIELDS <= set(value):
        raise ValueError("FFmpeg loudnorm measurements are incomplete")
    output: dict[str, Any] = {}
    for key in sorted(LOUDNORM_FIELDS - {"normalization_type"}):
        try:
            number = float(value[key])
        except (TypeError, ValueError) as exc:
            raise ValueError("FFmpeg loudnorm measurements are invalid") from exc
        if not math.isfinite(number) or not -200.0 <= number <= 200.0:
            raise ValueError("FFmpeg loudnorm measurements are invalid")
        output[key] = round(number, 6)
    normalization_type = str(value["normalization_type"]).strip().lower()
    if normalization_type not in {"linear", "dynamic"}:
        raise ValueError("FFmpeg loudnorm normalization type is invalid")
    output["normalization_type"] = normalization_type
    return output


def require_encoded_master_targets(stats: Mapping[str, Any]) -> None:
    """Raise when encoded-artifact measurements miss the fixed v2 targets."""

    values = validated_loudnorm_stats(stats)
    loudness_error = float(values["input_i"]) - TARGET_INTEGRATED_LUFS
    if abs(loudness_error) > INTEGRATED_LOUDNESS_TOLERANCE_LU:
        raise RuntimeError(
            "listening-master integrated loudness missed its fixed target"
        )
    if (
        float(values["input_tp"])
        > TRUE_PEAK_CEILING_DBTP + TRUE_PEAK_TOLERANCE_DB
    ):
        raise RuntimeError("listening-master true-peak protection failed")


def _verify_receipt_document(
    receipt: Mapping[str, Any],
    *,
    source_file: Mapping[str, Any],
    source_info: Mapping[str, Any],
    master_name: str,
    master_file: Mapping[str, Any],
    master_info: Mapping[str, Any],
) -> dict[str, Any]:
    if set(receipt) != _RECEIPT_TOP_LEVEL_FIELDS or (
        receipt.get("schema") != LISTENING_MASTER_SCHEMA
        or receipt.get("status") != "complete"
        or receipt.get("policy") != LISTENING_MASTER_POLICY
        or receipt.get("label") != LISTENING_MASTER_LABEL
        or receipt.get("mastered") is not True
        or receipt.get("release_master") is not False
        or receipt.get("mastering_scope") != LISTENING_MASTER_SCOPE
    ):
        raise ValueError("unsupported listening-master receipt")

    unsigned = {
        key: value for key, value in receipt.items() if key != "receipt_sha256"
    }
    document_sha256 = _document_hash(unsigned)
    if receipt.get("receipt_sha256") != document_sha256:
        raise ValueError("listening-master receipt self-hash is invalid")
    if receipt.get("effects") != dict(LISTENING_MASTER_EFFECTS):
        raise ValueError("listening-master receipt effects are invalid")

    source = _audio_receipt_record(
        receipt.get("source"),
        label="listening-master source",
        require_pcm24=False,
    )
    output = _audio_receipt_record(
        receipt.get("output"),
        label="listening-master output",
        require_pcm24=True,
        includes_name=True,
    )
    _require_audio_binding(
        source,
        source_file,
        source_info,
        label="listening-master source",
    )
    if (
        output["name"] != master_name
        or output["sha256"] != master_file["sha256"]
        or output["bytes"] != master_file["bytes"]
    ):
        raise ValueError("listening-master WAV does not match its exact receipt")
    for key in (
        "format",
        "subtype",
        "sample_rate",
        "channels",
        "frames",
        "duration_seconds",
    ):
        if output[key] != master_info[key]:
            raise ValueError(
                "listening-master WAV geometry does not match its exact receipt"
            )
    for key in ("sample_rate", "channels", "frames"):
        if output[key] != source[key]:
            raise ValueError(
                "listening-master output changed the source audio horizon"
            )

    if receipt.get("targets") != dict(LISTENING_MASTER_TARGETS):
        raise ValueError("listening-master targets are invalid")
    analysis = _loudnorm_receipt_stats(
        receipt.get("analysis_pass"),
        label="listening-master analysis pass",
    )
    rendered = _loudnorm_receipt_stats(
        receipt.get("render_pass"),
        label="listening-master render pass",
    )
    verification_value = receipt.get("verification_pass")
    verification_keys = set(LOUDNORM_FIELDS) | {"measured_artifact"}
    if (
        not isinstance(verification_value, Mapping)
        or set(verification_value) != verification_keys
        or verification_value.get("measured_artifact")
        != ENCODED_ARTIFACT_LABEL
    ):
        raise ValueError(
            "listening-master encoded-artifact verification is invalid"
        )
    verification = _loudnorm_receipt_stats(
        {key: verification_value[key] for key in LOUDNORM_FIELDS},
        label="listening-master encoded-artifact verification",
    )
    try:
        require_encoded_master_targets(verification)
    except (RuntimeError, ValueError) as exc:
        raise ValueError(
            "listening-master encoded artifact missed its receipt targets"
        ) from exc

    renderer = _renderer_record(receipt.get("renderer"))
    timing = {
        "policy": LISTENING_MASTER_TIMING_POLICY,
        "input_frames": source["frames"],
        "output_frames": output["frames"],
        "sample_rate": source["sample_rate"],
        "frame_horizon_changed": False,
        "time_shift_applied": False,
        "time_stretch_applied": False,
    }
    if receipt.get("timing") != timing:
        raise ValueError("listening-master timing contract is invalid")
    processing = {
        "integrated_loudness_normalisation": True,
        "true_peak_limiting": True,
        "normalization_type": rendered["normalization_type"],
        "encoded_artifact_verified": True,
        "equalisation": False,
        "stereo_widening": False,
        "reverb": False,
        "chorus": False,
        "saturation": False,
    }
    if receipt.get("processing") != processing:
        raise ValueError("listening-master processing contract is invalid")
    canonical_verification = {
        **verification,
        "measured_artifact": ENCODED_ARTIFACT_LABEL,
    }
    if (
        analysis != receipt["analysis_pass"]
        or rendered != receipt["render_pass"]
        or canonical_verification != receipt["verification_pass"]
    ):
        raise ValueError("listening-master measurement records are not canonical")
    return {
        "receipt_document_sha256": document_sha256,
        "source": source,
        "output": output,
        "analysis": analysis,
        "render": rendered,
        "verification": canonical_verification,
        "renderer": renderer,
        "timing": timing,
        "processing": processing,
    }


def _require_audio_binding(
    receipt_record: Mapping[str, Any],
    file_record: Mapping[str, Any],
    audio_info: Mapping[str, Any],
    *,
    label: str,
) -> None:
    if (
        receipt_record["sha256"] != file_record["sha256"]
        or receipt_record["bytes"] != file_record["bytes"]
    ):
        raise ValueError(
            "listening-master source does not match the exact balanced control"
        )
    for key in (
        "format",
        "subtype",
        "sample_rate",
        "channels",
        "frames",
        "duration_seconds",
    ):
        if receipt_record[key] != audio_info[key]:
            raise ValueError(f"{label} geometry does not match the balanced control")


def _renderer_record(value: Any) -> dict[str, Any]:
    expected = {
        "backend",
        "executable_sha256",
        "version",
        "filter",
        "policy",
        "identity_verification",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("listening-master renderer is invalid")
    version = _bounded_text(
        value.get("version"),
        label="listening-master renderer version",
        maximum=500,
    )
    record = {
        "backend": value.get("backend"),
        "executable_sha256": _require_sha256(
            value.get("executable_sha256"),
            label="listening-master renderer executable SHA-256",
        ),
        "version": version,
        "filter": value.get("filter"),
        "policy": value.get("policy"),
        "identity_verification": value.get("identity_verification"),
    }
    if (
        record["backend"] != "FFmpeg loudnorm"
        or record["filter"] != "loudnorm"
        or record["policy"] != LISTENING_MASTER_POLICY
        or record["identity_verification"] != FFMPEG_IDENTITY_POLICY
        or not version.startswith("ffmpeg version ")
    ):
        raise ValueError("listening-master renderer is invalid")
    return record


def _audio_receipt_record(
    value: Any,
    *,
    label: str,
    require_pcm24: bool,
    includes_name: bool = False,
) -> dict[str, Any]:
    expected = {
        "sha256",
        "bytes",
        "format",
        "subtype",
        "sample_rate",
        "channels",
        "frames",
        "duration_seconds",
    }
    if includes_name:
        expected.add("name")
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError(f"{label} record is invalid")
    sha256 = _require_sha256(value.get("sha256"), label=f"{label} SHA-256")
    byte_count = _positive_int(value.get("bytes"), label=f"{label} bytes")
    audio_format = value.get("format")
    subtype = _bounded_text(
        value.get("subtype"), label=f"{label} subtype", maximum=64
    )
    sample_rate = _positive_int(
        value.get("sample_rate"), label=f"{label} sample rate"
    )
    channels = _positive_int(value.get("channels"), label=f"{label} channels")
    frames = _positive_int(value.get("frames"), label=f"{label} frames")
    if audio_format not in {"WAV", "WAVEX"} or channels not in {1, 2}:
        raise ValueError(f"{label} audio geometry is invalid")
    if require_pcm24 and subtype != "PCM_24":
        raise ValueError(f"{label} must be PCM24 WAV")
    expected_duration = round(frames / sample_rate, 6)
    duration = _finite_number(
        value.get("duration_seconds"), label=f"{label} duration"
    )
    if duration != expected_duration:
        raise ValueError(f"{label} duration does not match its frame horizon")
    record: dict[str, Any] = {
        "sha256": sha256,
        "bytes": byte_count,
        "format": audio_format,
        "subtype": subtype,
        "sample_rate": sample_rate,
        "channels": channels,
        "frames": frames,
        "duration_seconds": duration,
    }
    if includes_name:
        name = _bounded_text(
            value.get("name"), label=f"{label} name", maximum=512
        )
        if Path(name).name != name or Path(name).suffix.lower() != ".wav":
            raise ValueError(f"{label} name is invalid")
        record["name"] = name
    return record


def _loudnorm_receipt_stats(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(LOUDNORM_FIELDS):
        raise ValueError(f"{label} measurements are invalid")
    try:
        return validated_loudnorm_stats(value)
    except ValueError as exc:
        raise ValueError(f"{label} measurements are invalid") from exc


def _read_audio_file(
    path: Path,
    *,
    label: str,
    maximum_bytes: int,
    require_pcm24: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    descriptor = _open_regular_file(path, label=label)
    try:
        before = os.fstat(descriptor)
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
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            with os.fdopen(os.dup(descriptor), "rb") as handle:
                info = _soundfile_module().info(handle)
        except Exception as exc:
            raise ValueError(f"{label} is not readable audio") from exc
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    _require_unchanged_stat(before, after, total=total, label=label)
    sample_rate = int(info.samplerate)
    frames = int(info.frames)
    channels = int(info.channels)
    audio_info = {
        "format": str(info.format),
        "subtype": str(info.subtype),
        "sample_rate": sample_rate,
        "channels": channels,
        "frames": frames,
        "duration_seconds": (
            round(frames / sample_rate, 6) if sample_rate > 0 else 0.0
        ),
    }
    if (
        audio_info["format"] not in {"WAV", "WAVEX"}
        or sample_rate <= 0
        or frames <= 0
        or channels not in {1, 2}
        or (require_pcm24 and audio_info["subtype"] != "PCM_24")
    ):
        raise ValueError(f"{label} audio geometry is invalid")
    return {"bytes": total, "sha256": digest.hexdigest()}, audio_info


def _read_regular_bytes(
    path: Path,
    *,
    label: str,
    maximum_bytes: int,
) -> tuple[bytes, dict[str, Any]]:
    descriptor = _open_regular_file(path, label=label)
    chunks: list[bytes] = []
    total = 0
    digest = hashlib.sha256()
    try:
        before = os.fstat(descriptor)
        if before.st_size > maximum_bytes:
            raise ValueError(f"{label} exceeds the supported byte limit")
        while True:
            block = os.read(descriptor, min(1024 * 1024, maximum_bytes + 1 - total))
            if not block:
                break
            chunks.append(block)
            total += len(block)
            if total > maximum_bytes:
                raise ValueError(f"{label} exceeds the supported byte limit")
            digest.update(block)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    _require_unchanged_stat(before, after, total=total, label=label)
    return b"".join(chunks), {"bytes": total, "sha256": digest.hexdigest()}


def _canonical_file_path(value: str | Path, *, label: str) -> Path:
    expanded = Path(value).expanduser()
    absolute = Path(os.path.abspath(os.fspath(expanded)))
    try:
        if absolute.is_symlink():
            raise ValueError(f"{label} must not be a symlink: {absolute}")
    except OSError as exc:
        raise ValueError(f"cannot inspect {label}: {absolute}") from exc
    return absolute.parent.resolve() / absolute.name


def _open_regular_file(path: Path, *, label: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"{label} is not a readable regular file: {path}") from exc
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise ValueError(f"{label} is not a regular file: {path}")
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def _require_unchanged_stat(
    before: os.stat_result,
    after: os.stat_result,
    *,
    total: int,
    label: str,
) -> None:
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if identity_before != identity_after or total != after.st_size:
        raise ValueError(f"{label} changed while it was being read")


def _soundfile_module() -> Any:
    try:
        import soundfile
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "listening-master verification requires soundfile; install "
            "Sunofriend with the convert extra"
        ) from exc
    return soundfile


def _bounded_text(value: Any, *, label: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    text = value.strip()
    if (
        not text
        or len(text) > maximum
        or any(ord(character) < 32 for character in text)
    ):
        raise ValueError(f"{label} is missing or outside its supported bounds")
    return text


def _positive_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _finite_number(value: Any, *, label: str) -> float | int:
    if (
        isinstance(value, bool)
        or not isinstance(value, (float, int))
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{label} must be a finite number")
    return value


def _require_sha256(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _document_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "ENCODED_ARTIFACT_LABEL",
    "FFMPEG_IDENTITY_POLICY",
    "INTEGRATED_LOUDNESS_TOLERANCE_LU",
    "LISTENING_MASTER_EFFECTS",
    "LISTENING_MASTER_LABEL",
    "LISTENING_MASTER_POLICY",
    "LISTENING_MASTER_PROCESSING_FLAGS",
    "LISTENING_MASTER_SCHEMA",
    "LISTENING_MASTER_SCOPE",
    "LISTENING_MASTER_TARGETS",
    "LISTENING_MASTER_TIMING_POLICY",
    "LISTENING_MASTER_VERIFICATION_SCHEMA",
    "LOUDNORM_FIELDS",
    "TARGET_INTEGRATED_LUFS",
    "TARGET_LOUDNESS_RANGE_LU",
    "TRUE_PEAK_CEILING_DBTP",
    "TRUE_PEAK_TOLERANCE_DB",
    "require_encoded_master_targets",
    "validated_loudnorm_stats",
    "verify_listening_master_artifacts",
]
