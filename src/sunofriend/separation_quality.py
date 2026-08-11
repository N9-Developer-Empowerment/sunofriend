"""Bounded, dependency-free PCM WAV evidence for separation experiments.

This module reads existing local files only. It does not decode compressed
audio, write reports, install a backend, contact a network service or claim
that reconstruction proves separation accuracy.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import stat
import struct
import unicodedata
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Iterable, Iterator, Sequence

from .separation_contract import (
    SEPARATION_RESIDUAL_DEFINITION,
    SeparationAudioGeometry,
)
from .source_roles import canonical_source_role, prepared_source_role_ids


MAX_PCM_WAV_FILE_BYTES = 2 * 1024**3
MAX_PCM_WAV_FRAMES = 100_000_000
MAX_PCM_WAV_CHANNELS = 2
MAX_PCM_WAV_SAMPLE_RATE = 768_000
MAX_RECONSTRUCTION_ROLES = 64
PCM_READ_FRAMES = 65_536
MAX_WAVE_FORMAT_CHUNK_BYTES = 1024 * 1024

# Source, target and residual may each differ from the ideal unquantized signal
# by half an LSB. A further half-largest-LSB guard covers chained rounding at
# a persistence boundary: 0.5 + 0.5 + 0.5 + 0.5 = two quantization steps.
RECONSTRUCTION_THRESHOLD_QUANTIZATION_STEPS = 2.0
RECONSTRUCTION_THRESHOLD_POLICY = (
    "two full-scale PCM quantization steps: half a source LSB, half a target "
    "LSB, half a residual LSB and a half-largest-LSB persistence guard"
)

_SUPPORTED_SAMPLE_WIDTH_BYTES = frozenset({2, 3})
_PCM_SUBFORMAT_GUID = bytes.fromhex("0100000000001000800000aa00389b71")


@dataclass(frozen=True)
class PcmWaveInspection:
    """Hash, geometry and level evidence read from one existing PCM WAV."""

    sha256: str
    geometry: SeparationAudioGeometry
    peak: float
    rms: float
    silence_fraction: float
    clipped_samples: int
    sample_width_bytes: int

    def to_artifact_dict(
        self,
        role: str,
        relative_path: str,
        residual_target_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Return fields accepted by ``separation-run.v1`` artifacts."""

        canonical_role = _canonical_role(role)
        artifact_path = _safe_relative_wav_path(relative_path)
        document: dict[str, Any] = {
            "role": canonical_role,
            "path": artifact_path,
            "sha256": self.sha256,
            "geometry": self.geometry.to_dict(),
            "peak": self.peak,
            "rms": self.rms,
            "silence_fraction": self.silence_fraction,
            "clipped_samples": self.clipped_samples,
        }
        if residual_target_sha256 is not None:
            document.update(
                {
                    "target_sha256": _lower_sha256(
                        residual_target_sha256,
                        "residual target SHA-256",
                    ),
                    "definition": SEPARATION_RESIDUAL_DEFINITION,
                }
            )
        return document


@dataclass(frozen=True)
class RoleReconstructionEvidence:
    """One target/residual pair compared sample-for-sample with its source."""

    role: str
    maximum_absolute_error: float
    rms_error: float
    threshold: float
    passed: bool
    samples_compared: int
    quantization_step: float
    threshold_policy: str
    source_sha256: str
    target_sha256: str
    residual_sha256: str
    geometry: SeparationAudioGeometry
    sample_width_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "maximum_absolute_error": self.maximum_absolute_error,
            "rms_error": self.rms_error,
            "threshold": self.threshold,
            "passed": self.passed,
            "samples_compared": self.samples_compared,
            "quantization_step": self.quantization_step,
            "threshold_quantization_steps": (
                RECONSTRUCTION_THRESHOLD_QUANTIZATION_STEPS
            ),
            "threshold_policy": self.threshold_policy,
            "source_sha256": self.source_sha256,
            "target_sha256": self.target_sha256,
            "residual_sha256": self.residual_sha256,
            "geometry": self.geometry.to_dict(),
            "sample_width_bytes": self.sample_width_bytes,
        }


@dataclass(frozen=True)
class ReconstructionEvaluation:
    """Aggregate receipt metrics plus immutable, richer per-role evidence."""

    maximum_absolute_error: float
    rms_error: float
    threshold: float
    passed: bool
    per_role: tuple[RoleReconstructionEvidence, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "maximum_absolute_error": self.maximum_absolute_error,
            "rms_error": self.rms_error,
            "threshold": self.threshold,
            "passed": self.passed,
            "per_role": {
                evidence.role: evidence.to_dict()
                for evidence in self.per_role
            },
        }


@dataclass(frozen=True)
class PcmWaveParameters:
    """Validated byte layout for a bounded integer-PCM WAVE file."""

    channels: int
    sample_width_bytes: int
    sample_rate: int
    frames: int
    data_offset: int
    data_bytes: int

    @property
    def frame_bytes(self) -> int:
        return self.channels * self.sample_width_bytes

    @property
    def sample_scale(self) -> int:
        return 1 << (8 * self.sample_width_bytes - 1)


@dataclass(frozen=True)
class _IntegerErrorStatistics:
    maximum_absolute_error_units: int
    squared_error_units: int
    samples_compared: int


@dataclass(frozen=True)
class _OpenedPcmWave:
    path: Path
    handle: BinaryIO
    opened_stat: os.stat_result
    parameters: PcmWaveParameters
    inspection: PcmWaveInspection


def inspect_pcm_wav(path: str | Path) -> PcmWaveInspection:
    """Inspect one bounded PCM16/PCM24 mono/stereo WAV without changing it."""

    with _open_inspected_pcm_wav(path) as opened:
        return opened.inspection


def evaluate_target_residual_reconstruction(
    source_path: str | Path,
    pairs: Sequence[tuple[str, str | Path, str | Path]],
) -> ReconstructionEvaluation:
    """Compare each persisted target plus residual with the persisted source.

    Geometry and sample width must match exactly. Passing reconstruction proves
    only that the persisted arithmetic closes within the explicit PCM
    quantization allowance; it does not prove useful or accurate separation.
    """

    normalized_pairs = _validated_pairs(pairs)
    with ExitStack() as stack:
        source = stack.enter_context(_open_inspected_pcm_wav(source_path))
        opened_pairs: list[
            tuple[str, _OpenedPcmWave, _OpenedPcmWave]
        ] = []
        for role, target_path, residual_path in normalized_pairs:
            target = stack.enter_context(
                _open_inspected_pcm_wav(target_path)
            )
            residual = stack.enter_context(
                _open_inspected_pcm_wav(residual_path)
            )
            _require_matching_pcm(
                source.inspection,
                target.inspection,
                f"target for {role}",
            )
            _require_matching_pcm(
                source.inspection,
                residual.inspection,
                f"residual for {role}",
            )
            opened_pairs.append((role, target, residual))

        # A deliberately empty, private seam lets tests deterministically
        # replace a pathname after inspection. It is not part of the public
        # API; normal execution does nothing here.
        _after_reconstruction_inputs_inspected()

        role_evidence: list[RoleReconstructionEvidence] = []
        aggregate_maximum_units = 0
        aggregate_squared_units = 0
        aggregate_samples = 0
        source_inspection = source.inspection
        for role, target, residual in opened_pairs:
            statistics = _reconstruction_error_statistics(
                source,
                target,
                residual,
            )
            scale = 1 << (
                8 * source_inspection.sample_width_bytes - 1
            )
            quantization_step = 1.0 / scale
            threshold = (
                RECONSTRUCTION_THRESHOLD_QUANTIZATION_STEPS
                * quantization_step
            )
            maximum_error = (
                statistics.maximum_absolute_error_units / scale
            )
            rms_error = (
                math.sqrt(
                    statistics.squared_error_units
                    / statistics.samples_compared
                )
                / scale
            )
            if not all(
                math.isfinite(value)
                for value in (
                    quantization_step,
                    threshold,
                    maximum_error,
                    rms_error,
                )
            ):
                raise ValueError("reconstruction metrics are not finite")
            evidence = RoleReconstructionEvidence(
                role=role,
                maximum_absolute_error=maximum_error,
                rms_error=rms_error,
                threshold=threshold,
                passed=maximum_error <= threshold,
                samples_compared=statistics.samples_compared,
                quantization_step=quantization_step,
                threshold_policy=RECONSTRUCTION_THRESHOLD_POLICY,
                source_sha256=source_inspection.sha256,
                target_sha256=target.inspection.sha256,
                residual_sha256=residual.inspection.sha256,
                geometry=source_inspection.geometry,
                sample_width_bytes=source_inspection.sample_width_bytes,
            )
            role_evidence.append(evidence)
            aggregate_maximum_units = max(
                aggregate_maximum_units,
                statistics.maximum_absolute_error_units,
            )
            aggregate_squared_units += statistics.squared_error_units
            aggregate_samples += statistics.samples_compared

        scale = 1 << (8 * source_inspection.sample_width_bytes - 1)
        aggregate_threshold = (
            RECONSTRUCTION_THRESHOLD_QUANTIZATION_STEPS / scale
        )
        aggregate_maximum = aggregate_maximum_units / scale
        aggregate_rms = math.sqrt(
            aggregate_squared_units / aggregate_samples
        ) / scale
        result = ReconstructionEvaluation(
            maximum_absolute_error=aggregate_maximum,
            rms_error=aggregate_rms,
            threshold=aggregate_threshold,
            passed=(
                aggregate_maximum <= aggregate_threshold
                and all(evidence.passed for evidence in role_evidence)
            ),
            per_role=tuple(role_evidence),
        )
    return result


def _regular_non_symlink_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    try:
        details = candidate.lstat()
    except OSError as exc:
        raise ValueError(f"PCM WAV is unavailable: {candidate}") from exc
    if stat.S_ISLNK(details.st_mode):
        raise ValueError("PCM WAV path must not be a symbolic link")
    if not stat.S_ISREG(details.st_mode):
        raise ValueError("PCM WAV path must name a regular file")
    if details.st_size <= 0:
        raise ValueError("PCM WAV must not be empty")
    if details.st_size > MAX_PCM_WAV_FILE_BYTES:
        raise ValueError("PCM WAV exceeds the hard file-size bound")
    return candidate


@contextmanager
def _open_inspected_pcm_wav(
    path: str | Path,
) -> Iterator[_OpenedPcmWave]:
    source = _regular_non_symlink_path(path)
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source, flags)
    except OSError as exc:
        raise ValueError(
            f"PCM WAV could not be opened safely: {source}"
        ) from exc
    handle = os.fdopen(descriptor, "rb")
    try:
        opened = os.fstat(handle.fileno())
        _require_opened_identity(source, opened)
        parameters = read_pcm_wave_parameters(
            handle,
            file_bytes=opened.st_size,
        )
        digest = _hash_open_file(handle)
        (
            peak_units,
            squared_units,
            silent_samples,
            clipped_samples,
            samples_read,
        ) = _inspect_open_file(handle, parameters)
        if _hash_open_file(handle) != digest:
            raise ValueError(
                "PCM WAV bytes changed while metrics were being inspected"
            )
        _require_bound_identity(source, handle, opened, digest)
        expected_samples = parameters.frames * parameters.channels
        if samples_read != expected_samples:
            raise ValueError(
                "PCM WAV data is truncated or inconsistent with its header"
            )
        scale = parameters.sample_scale
        peak = peak_units / scale
        rms = math.sqrt(squared_units / samples_read) / scale
        silence_fraction = silent_samples / samples_read
        metrics = (peak, rms, silence_fraction)
        if not all(math.isfinite(value) for value in metrics):
            raise ValueError("PCM WAV metrics are not finite")
        geometry = SeparationAudioGeometry(
            sample_rate=parameters.sample_rate,
            channels=parameters.channels,
            frames=parameters.frames,
            duration_seconds=parameters.frames / parameters.sample_rate,
        )
        inspection = PcmWaveInspection(
            sha256=digest,
            geometry=geometry,
            peak=peak,
            rms=rms,
            silence_fraction=silence_fraction,
            clipped_samples=clipped_samples,
            sample_width_bytes=parameters.sample_width_bytes,
        )
        opened_wave = _OpenedPcmWave(
            path=source,
            handle=handle,
            opened_stat=opened,
            parameters=parameters,
            inspection=inspection,
        )
        yield opened_wave
        # The final digest binds header parsing, level metrics and any
        # reconstruction reads to exactly the bytes named by the path.
        _require_bound_identity(source, handle, opened, digest)
    except (EOFError, OSError, struct.error) as exc:
        raise ValueError(
            f"unsupported or malformed PCM WAV: {source}"
        ) from exc
    finally:
        handle.close()


def _require_opened_identity(path: Path, opened: os.stat_result) -> None:
    try:
        current = path.lstat()
    except OSError as exc:
        raise ValueError("PCM WAV changed while it was being opened") from exc
    if (
        stat.S_ISLNK(current.st_mode)
        or not stat.S_ISREG(current.st_mode)
        or not stat.S_ISREG(opened.st_mode)
    ):
        raise ValueError("PCM WAV path must remain a regular non-symlink file")
    if _stat_identity(current) != _stat_identity(opened):
        raise ValueError("PCM WAV changed while it was being opened")
    if opened.st_size <= 0:
        raise ValueError("PCM WAV must not be empty")
    if opened.st_size > MAX_PCM_WAV_FILE_BYTES:
        raise ValueError("PCM WAV exceeds the hard file-size bound")


def _require_bound_identity(
    path: Path,
    handle: BinaryIO,
    opened: os.stat_result,
    expected_sha256: str,
) -> None:
    current_opened = os.fstat(handle.fileno())
    try:
        current_path = path.lstat()
    except OSError as exc:
        raise ValueError(
            "PCM WAV path changed or was replaced during inspection"
        ) from exc
    if (
        stat.S_ISLNK(current_path.st_mode)
        or not stat.S_ISREG(current_path.st_mode)
        or not stat.S_ISREG(current_opened.st_mode)
        or _stat_identity(current_path) != _stat_identity(opened)
        or _stat_identity(current_opened) != _stat_identity(opened)
    ):
        raise ValueError(
            "PCM WAV path changed or was replaced during inspection"
        )
    if _hash_open_file(handle) != expected_sha256:
        raise ValueError("PCM WAV bytes changed during inspection")


def _stat_identity(
    value: os.stat_result,
) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _hash_open_file(handle: Any) -> str:
    handle.seek(0)
    digest = hashlib.sha256()
    while True:
        chunk = handle.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def read_pcm_wave_parameters(
    handle: BinaryIO,
    *,
    file_bytes: int,
) -> PcmWaveParameters:
    """Validate classic or extensible integer-PCM RIFF/WAVE chunks.

    The caller retains ownership of the already-open binary handle.
    """
    handle.seek(0)
    header = handle.read(12)
    if (
        len(header) != 12
        or header[:4] != b"RIFF"
        or header[8:] != b"WAVE"
    ):
        raise ValueError("unsupported or malformed PCM WAV")
    riff_size = struct.unpack("<I", header[4:8])[0]
    riff_end = riff_size + 8
    if riff_end > file_bytes:
        raise ValueError("PCM WAV RIFF payload is truncated")
    if riff_end < 12:
        raise ValueError("PCM WAV RIFF payload is malformed")

    position = 12
    format_data: bytes | None = None
    data_offset: int | None = None
    data_bytes: int | None = None
    while position + 8 <= riff_end:
        handle.seek(position)
        chunk_header = handle.read(8)
        if len(chunk_header) != 8:
            raise ValueError("PCM WAV has a truncated chunk header")
        chunk_id = chunk_header[:4]
        chunk_size = struct.unpack("<I", chunk_header[4:])[0]
        chunk_offset = position + 8
        chunk_end = chunk_offset + chunk_size
        padded_end = chunk_end + (chunk_size & 1)
        if chunk_end > riff_end or (
            padded_end > riff_end and chunk_end != riff_end
        ):
            raise ValueError("PCM WAV contains a truncated chunk")
        if chunk_id == b"fmt " and format_data is None:
            if chunk_size > MAX_WAVE_FORMAT_CHUNK_BYTES:
                raise ValueError("PCM WAV format chunk exceeds bounds")
            handle.seek(chunk_offset)
            format_data = handle.read(chunk_size)
            if len(format_data) != chunk_size:
                raise ValueError("PCM WAV format chunk is truncated")
        elif chunk_id == b"data" and data_offset is None:
            data_offset = chunk_offset
            data_bytes = chunk_size
        if format_data is not None and data_offset is not None:
            break
        position = min(padded_end, riff_end)

    if format_data is None or data_offset is None or data_bytes is None:
        raise ValueError("PCM WAV needs complete fmt and data chunks")
    if len(format_data) < 16:
        raise ValueError("PCM WAV format chunk is truncated")
    (
        format_tag,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
    ) = struct.unpack("<HHIIHH", format_data[:16])
    if format_tag == 0xFFFE:
        if len(format_data) < 40:
            raise ValueError("WAVE_FORMAT_EXTENSIBLE chunk is truncated")
        extension_size = struct.unpack("<H", format_data[16:18])[0]
        if extension_size < 22 or len(format_data) < 18 + extension_size:
            raise ValueError("WAVE_FORMAT_EXTENSIBLE chunk is truncated")
        valid_bits_per_sample = struct.unpack("<H", format_data[18:20])[0]
        if format_data[24:40] != _PCM_SUBFORMAT_GUID:
            raise ValueError(
                "unsupported WAVE_FORMAT_EXTENSIBLE subformat"
            )
        if valid_bits_per_sample != bits_per_sample:
            raise ValueError(
                "WAVE_FORMAT_EXTENSIBLE valid bits must match packed PCM"
            )
    elif format_tag != 1:
        raise ValueError("unsupported non-PCM WAV encoding")

    if bits_per_sample % 8:
        raise ValueError("PCM WAV sample width must be byte-aligned")
    sample_width = bits_per_sample // 8
    if not 1 <= channels <= MAX_PCM_WAV_CHANNELS:
        raise ValueError("PCM WAV must be mono or stereo")
    if sample_width not in _SUPPORTED_SAMPLE_WIDTH_BYTES:
        raise ValueError("PCM WAV must use signed 16-bit or 24-bit samples")
    if not 1 <= sample_rate <= MAX_PCM_WAV_SAMPLE_RATE:
        raise ValueError("PCM WAV sample rate is outside bounds")
    expected_block_align = channels * sample_width
    if block_align != expected_block_align:
        raise ValueError("PCM WAV block alignment is invalid")
    if byte_rate != sample_rate * block_align:
        raise ValueError("PCM WAV byte rate is invalid")
    if data_bytes <= 0 or data_bytes % block_align:
        raise ValueError("PCM WAV data is truncated or misaligned")
    if data_offset + data_bytes > file_bytes:
        raise ValueError("PCM WAV data is truncated")
    frames = data_bytes // block_align
    if not 1 <= frames <= MAX_PCM_WAV_FRAMES:
        raise ValueError("PCM WAV frame count is outside bounds")
    parameters = PcmWaveParameters(
        channels=channels,
        sample_width_bytes=sample_width,
        sample_rate=sample_rate,
        frames=frames,
        data_offset=data_offset,
        data_bytes=data_bytes,
    )
    if frames * parameters.frame_bytes > file_bytes:
        raise ValueError("PCM WAV header declares more audio than the file contains")
    return parameters


def _inspect_open_file(
    handle: BinaryIO,
    parameters: PcmWaveParameters,
) -> tuple[int, int, int, int, int]:
    peak_units = 0
    squared_units = 0
    silent_samples = 0
    clipped_samples = 0
    samples_read = 0
    minimum = -parameters.sample_scale
    maximum = parameters.sample_scale - 1
    handle.seek(parameters.data_offset)
    while samples_read < parameters.frames * parameters.channels:
        frames = min(
            PCM_READ_FRAMES,
            parameters.frames - samples_read // parameters.channels,
        )
        raw = handle.read(frames * parameters.frame_bytes)
        if not raw:
            break
        if len(raw) % parameters.frame_bytes:
            raise ValueError("PCM WAV contains an incomplete audio frame")
        for value in _decode_pcm_samples(
            raw,
            sample_width_bytes=parameters.sample_width_bytes,
        ):
            magnitude = abs(value)
            peak_units = max(peak_units, magnitude)
            squared_units += value * value
            silent_samples += value == 0
            clipped_samples += value in {minimum, maximum}
            samples_read += 1
    return (
        peak_units,
        squared_units,
        silent_samples,
        clipped_samples,
        samples_read,
    )


def _decode_pcm_samples(
    raw: bytes,
    *,
    sample_width_bytes: int,
) -> Iterable[int]:
    if sample_width_bytes == 2:
        if len(raw) % 2:
            raise ValueError("PCM16 data has an incomplete sample")
        return (item[0] for item in struct.iter_unpack("<h", raw))
    if sample_width_bytes == 3:
        if len(raw) % 3:
            raise ValueError("PCM24 data has an incomplete sample")
        return _decode_pcm24(raw)
    raise ValueError("unsupported PCM sample width")


def _decode_pcm24(raw: bytes) -> Iterable[int]:
    for offset in range(0, len(raw), 3):
        value = (
            raw[offset]
            | raw[offset + 1] << 8
            | raw[offset + 2] << 16
        )
        if value & 0x800000:
            value -= 1 << 24
        yield value


def _validated_pairs(
    pairs: Sequence[tuple[str, str | Path, str | Path]],
) -> tuple[tuple[str, Path, Path], ...]:
    if isinstance(pairs, (str, bytes)) or not isinstance(pairs, Sequence):
        raise TypeError("reconstruction pairs must be a sequence of triples")
    if not 1 <= len(pairs) <= MAX_RECONSTRUCTION_ROLES:
        raise ValueError("reconstruction pair count is outside bounds")
    normalized: list[tuple[str, Path, Path]] = []
    for index, item in enumerate(pairs):
        if not isinstance(item, (tuple, list)) or len(item) != 3:
            raise ValueError(
                f"reconstruction pair {index} must be a role/target/residual triple"
            )
        role = _canonical_role(item[0])
        normalized.append((role, Path(item[1]), Path(item[2])))
    roles = [item[0] for item in normalized]
    if len(roles) != len(set(roles)):
        raise ValueError("reconstruction pair roles must be unique")
    return tuple(sorted(normalized, key=lambda item: item[0]))


def _canonical_role(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("separation role must be a prepared canonical role")
    try:
        canonical = canonical_source_role(value)
    except ValueError as exc:
        raise ValueError(
            "separation role must be a prepared canonical role"
        ) from exc
    if canonical != value or canonical not in prepared_source_role_ids():
        raise ValueError(
            "separation role must be a prepared canonical role"
        )
    return canonical


def _safe_relative_wav_path(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("artifact path must be a safe relative WAV path")
    text = value
    path = PurePosixPath(text)
    if (
        not text
        or text != text.strip()
        or unicodedata.normalize("NFC", text) != text
        or "\\" in text
        or "\x00" in text
        or path.is_absolute()
        or str(path) != text
        or path == PurePosixPath(".")
        or ".." in path.parts
        or "~" in path.parts
        or "://" in text
        or path.suffix.casefold() != ".wav"
    ):
        raise ValueError("artifact path must be a safe relative WAV path")
    return text


def _lower_sha256(value: str, label: str) -> str:
    text = str(value)
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return text


def _require_matching_pcm(
    source: PcmWaveInspection,
    candidate: PcmWaveInspection,
    label: str,
) -> None:
    if candidate.geometry != source.geometry:
        raise ValueError(f"{label} geometry does not exactly match source")
    if candidate.sample_width_bytes != source.sample_width_bytes:
        raise ValueError(f"{label} sample width does not exactly match source")


def _reconstruction_error_statistics(
    source: _OpenedPcmWave,
    target: _OpenedPcmWave,
    residual: _OpenedPcmWave,
) -> _IntegerErrorStatistics:
    parameters = source.parameters
    maximum = 0
    squared = 0
    samples = 0
    source.handle.seek(source.parameters.data_offset)
    target.handle.seek(target.parameters.data_offset)
    residual.handle.seek(residual.parameters.data_offset)
    try:
        remaining = parameters.frames
        while remaining:
            frames = min(PCM_READ_FRAMES, remaining)
            expected_bytes = frames * parameters.frame_bytes
            source_raw = source.handle.read(expected_bytes)
            target_raw = target.handle.read(expected_bytes)
            residual_raw = residual.handle.read(expected_bytes)
            if not (
                len(source_raw)
                == len(target_raw)
                == len(residual_raw)
                == expected_bytes
            ):
                raise ValueError(
                    "reconstruction audio changed or became truncated"
                )
            source_values = _decode_pcm_samples(
                source_raw,
                sample_width_bytes=parameters.sample_width_bytes,
            )
            target_values = _decode_pcm_samples(
                target_raw,
                sample_width_bytes=parameters.sample_width_bytes,
            )
            residual_values = _decode_pcm_samples(
                residual_raw,
                sample_width_bytes=parameters.sample_width_bytes,
            )
            for source_value, target_value, residual_value in zip(
                source_values,
                target_values,
                residual_values,
            ):
                error = source_value - target_value - residual_value
                magnitude = abs(error)
                maximum = max(maximum, magnitude)
                squared += error * error
                samples += 1
            remaining -= frames
    except OSError as exc:
        raise ValueError(
            "reconstruction audio is malformed or unavailable"
        ) from exc
    expected_samples = parameters.frames * parameters.channels
    if samples != expected_samples:
        raise ValueError("reconstruction audio sample count changed")
    return _IntegerErrorStatistics(
        maximum_absolute_error_units=maximum,
        squared_error_units=squared,
        samples_compared=samples,
    )


def _after_reconstruction_inputs_inspected() -> None:
    """Private deterministic race-test seam; normal execution is a no-op."""


__all__ = [
    "MAX_PCM_WAV_CHANNELS",
    "MAX_PCM_WAV_FILE_BYTES",
    "MAX_PCM_WAV_FRAMES",
    "MAX_PCM_WAV_SAMPLE_RATE",
    "MAX_RECONSTRUCTION_ROLES",
    "PCM_READ_FRAMES",
    "PcmWaveInspection",
    "PcmWaveParameters",
    "RECONSTRUCTION_THRESHOLD_POLICY",
    "RECONSTRUCTION_THRESHOLD_QUANTIZATION_STEPS",
    "ReconstructionEvaluation",
    "RoleReconstructionEvidence",
    "evaluate_target_residual_reconstruction",
    "inspect_pcm_wav",
    "read_pcm_wave_parameters",
]
