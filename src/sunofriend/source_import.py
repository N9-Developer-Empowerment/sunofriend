"""Plan and execute one bounded, deterministic local source-audio import."""

from __future__ import annotations

import ctypes
import errno
import math
import os
import re
import secrets
import shutil
import stat
import struct
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .audio_formats import (
    DEFAULT_AUDIO_IMPORT_LIMITS,
    AudioImportLimits,
    AudioProbe,
    decode_timeout_seconds,
    decoder_capability_report,
    file_sha256,
    probe_stable_audio,
    resolve_executable,
    validate_local_source_path,
)
from .source_project import (
    RIGHTS_CATEGORIES,
    SourceMetadata,
    SourcePart,
    build_source_project,
    discover_chord_document,
    normalize_source_role,
    resolve_source_metadata,
    write_source_project,
)
from .source_receipt import (
    SourceImportReceipt,
    validate_source_receipt_files,
    write_source_receipt,
)


@dataclass(frozen=True)
class SourceImportPlan:
    """Read-only plan whose identities are rechecked immediately before import."""

    source: Path
    destination: Path
    ffmpeg: Path
    ffprobe: Path
    source_sha256: str
    probe: AudioProbe
    decoder_capabilities: Mapping[str, Any]
    limits: AudioImportLimits
    role: str
    instrument_label: str | None
    metadata: SourceMetadata
    rights_category: str
    title: str
    chord_document: Path | None
    chord_sha256: str | None
    chord_bytes: int
    original_relative_path: str
    canonical_relative_path: str
    receipt_relative_path: str
    project_relative_path: str
    chord_relative_path: str | None
    decode_timeout_seconds: float
    required_free_bytes: int
    available_free_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "sunofriend.source-import-plan.v1",
            "read_only": True,
            "network_used": False,
            "source": {
                "path": str(self.source),
                "name": self.source.name,
                "bytes": self.probe.source_bytes,
                "sha256": self.source_sha256,
                "probe": self.probe.to_dict(),
            },
            "destination": str(self.destination),
            "outputs": {
                "original": self.original_relative_path,
                "canonical": self.canonical_relative_path,
                "receipt": self.receipt_relative_path,
                "source_project": self.project_relative_path,
                "chord_document": self.chord_relative_path,
            },
            "context": {
                "title": self.title,
                "role": self.role,
                "instrument_label": self.instrument_label,
                "metadata": self.metadata.to_dict(),
                "rights_category": self.rights_category,
                "original_name": self.source.name,
                "chord_sha256": self.chord_sha256,
                "chord_bytes": self.chord_bytes,
            },
            "decoder": dict(self.decoder_capabilities),
            "limits": {
                **self.limits.to_dict(),
                "decode_timeout_seconds": self.decode_timeout_seconds,
                "required_free_bytes": self.required_free_bytes,
                "available_free_bytes": self.available_free_bytes,
            },
            "side_effects_if_executed": {
                "filesystem": [str(self.destination)],
                "network": [],
                "installs": [],
            },
        }


@dataclass(frozen=True)
class SourceImportResult:
    root: Path
    original: Path
    canonical: Path
    receipt: Path
    source_project: Path
    chord_document: Path | None
    source_id: str


def plan_source_import(
    source: str | Path,
    destination: str | Path,
    *,
    ffmpeg: str | Path,
    ffprobe: str | Path,
    role: str | None = None,
    instrument_label: str | None = None,
    key: str | None = None,
    bpm: float | None = None,
    tuning_hz: float | None = None,
    chord_document: str | Path | None = None,
    discover_chords: bool = True,
    rights_category: str = "declined_to_state",
    title: str | None = None,
    limits: AudioImportLimits = DEFAULT_AUDIO_IMPORT_LIMITS,
    allow_conditional_format: bool = False,
) -> SourceImportPlan:
    """Inspect an import completely without creating its destination."""

    source_path = validate_local_source_path(source, limits=limits)
    destination_path = _destination_path(destination)
    if destination_path == source_path.parent or _is_relative_to(
        destination_path, source_path.parent
    ):
        raise ValueError(
            "source import destination must be outside the source folder"
        )
    ffmpeg_path = resolve_executable(ffmpeg)
    ffprobe_path = resolve_executable(ffprobe)
    capabilities = decoder_capability_report(
        ffmpeg=ffmpeg_path,
        ffprobe=ffprobe_path,
        timeout_seconds=limits.probe_timeout_seconds,
    )
    if not capabilities["policy"]["pcm24_encoder_available"]:
        raise RuntimeError("the selected FFmpeg build does not report pcm_s24le")
    probe, source_hash = probe_stable_audio(
        source_path,
        ffprobe=ffprobe_path,
        limits=limits,
        allow_conditional=allow_conditional_format,
    )
    for name, executable in (("ffmpeg", ffmpeg_path), ("ffprobe", ffprobe_path)):
        if file_sha256(executable) != capabilities[name]["sha256"]:
            raise ValueError(
                f"{name} changed while the import plan was being created"
            )
    source_role = normalize_source_role(role, fallback_from=source_path)
    normalized_rights = str(rights_category).strip()
    if normalized_rights not in RIGHTS_CATEGORIES:
        raise ValueError(
            "rights_category must be one of: "
            + ", ".join(sorted(RIGHTS_CATEGORIES))
        )
    metadata = resolve_source_metadata(
        source_path, key=key, bpm=bpm, tuning_hz=tuning_hz
    )
    chord_path = _resolve_chord_document(
        source_path,
        explicit=chord_document,
        discover=discover_chords,
    )
    chord_hash = file_sha256(chord_path) if chord_path is not None else None
    chord_bytes = chord_path.stat().st_size if chord_path is not None else 0

    safe_original = _safe_filename(source_path.name)
    safe_canonical = f"{_safe_stem(source_path.stem)}.wav"
    original_relative = f"INPUT/original/{safe_original}"
    canonical_relative = f"INPUT/canonical/{safe_canonical}"
    chord_relative = (
        f"INPUT/context/{_safe_filename(chord_path.name)}"
        if chord_path is not None
        else None
    )
    required_free = (
        probe.source_bytes
        + 2 * probe.projected_pcm24_bytes
        + chord_bytes
        + limits.minimum_free_space_headroom_bytes
    )
    available_free = shutil.disk_usage(
        _nearest_existing_parent(destination_path.parent)
    ).free
    if available_free < required_free:
        raise OSError(
            "insufficient free space for deterministic source import: "
            f"need {required_free} bytes, found {available_free}"
        )
    resolved_title = (
        str(title).strip()
        if title is not None and str(title).strip()
        else source_path.parent.name or source_path.stem
    )
    label = str(instrument_label).strip() if instrument_label is not None else None
    return SourceImportPlan(
        source=source_path,
        destination=destination_path,
        ffmpeg=ffmpeg_path,
        ffprobe=ffprobe_path,
        source_sha256=source_hash,
        probe=probe,
        decoder_capabilities=capabilities,
        limits=limits,
        role=source_role,
        instrument_label=label or None,
        metadata=metadata,
        rights_category=normalized_rights,
        title=resolved_title,
        chord_document=chord_path,
        chord_sha256=chord_hash,
        chord_bytes=chord_bytes,
        original_relative_path=original_relative,
        canonical_relative_path=canonical_relative,
        receipt_relative_path="INPUT/source-import.json",
        project_relative_path="INPUT/source-project.json",
        chord_relative_path=chord_relative,
        decode_timeout_seconds=decode_timeout_seconds(
            probe.duration_seconds, limits=limits
        ),
        required_free_bytes=required_free,
        available_free_bytes=available_free,
    )


def execute_source_import(plan: SourceImportPlan) -> SourceImportResult:
    """Execute one previously inspected plan into a new atomic run directory."""

    source = validate_local_source_path(plan.source, limits=plan.limits)
    if source != plan.source or file_sha256(source) != plan.source_sha256:
        raise ValueError("source audio changed after the import plan was created")
    destination = _execution_destination(plan, source=source)
    _verify_decoder_identities(plan)
    if plan.chord_document is not None:
        chord = _validate_chord_document(plan.chord_document)
        if chord != plan.chord_document or file_sha256(chord) != plan.chord_sha256:
            raise ValueError("chord document changed after the import plan")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(
            f"source import destination already exists: {destination}"
        )
    available_free = shutil.disk_usage(
        _nearest_existing_parent(destination.parent)
    ).free
    if available_free < plan.required_free_bytes:
        raise OSError(
            "free space fell below the amount required by the import plan"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination = _execution_destination(plan, source=source)
    parent_fd = _open_destination_parent(destination.parent)
    staging: Path | None = None
    try:
        staging = _create_staging_directory(parent_fd, destination)
        _require_parent_descriptor(destination.parent, parent_fd)
        original = staging / plan.original_relative_path
        canonical = staging / plan.canonical_relative_path
        receipt_path = staging / plan.receipt_relative_path
        project_path = staging / plan.project_relative_path
        copied_chord = (
            staging / plan.chord_relative_path
            if plan.chord_relative_path is not None
            else None
        )
        original.parent.mkdir(parents=True, exist_ok=False)
        canonical.parent.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(source, original)
        if file_sha256(original) != plan.source_sha256:
            raise RuntimeError("copied original does not match its planned hash")
        if copied_chord is not None and plan.chord_document is not None:
            copied_chord.parent.mkdir(parents=True, exist_ok=False)
            shutil.copyfile(plan.chord_document, copied_chord)
            if file_sha256(copied_chord) != plan.chord_sha256:
                raise RuntimeError("copied chord document does not match its hash")
        _require_parent_descriptor(destination.parent, parent_fd)

        arguments = _ffmpeg_decode_arguments(
            original,
            canonical,
            duration_seconds=plan.probe.duration_seconds,
            maximum_output_bytes=plan.limits.maximum_canonical_bytes,
        )
        _run_decode(
            plan.ffmpeg,
            arguments,
            timeout_seconds=plan.decode_timeout_seconds,
        )
        _verify_decoder_identities(plan)
        _require_parent_descriptor(destination.parent, parent_fd)
        canonical_geometry = {
            **inspect_pcm24_wav(canonical),
            "container_bytes": canonical.stat().st_size,
        }
        _validate_canonical_geometry(plan, canonical_geometry)
        canonical_hash = file_sha256(canonical)
        receipt = _build_receipt(
            plan,
            canonical_geometry=canonical_geometry,
            canonical_sha256=canonical_hash,
            decoder_arguments=_receipt_arguments(arguments),
        )
        write_source_receipt(receipt_path, receipt)

        chord_record = (
            {
                "name": plan.chord_document.name,
                "path": plan.chord_relative_path,
                "sha256": plan.chord_sha256,
                "bytes": copied_chord.stat().st_size,
            }
            if copied_chord is not None
            and plan.chord_document is not None
            and plan.chord_relative_path is not None
            else None
        )
        source_part = SourcePart(
            source_id=receipt.source_id,
            role=plan.role,
            instrument_label=plan.instrument_label,
            original_name=plan.source.name,
            original_path=plan.original_relative_path,
            canonical_path=plan.canonical_relative_path,
            receipt_path=plan.receipt_relative_path,
        )
        project = build_source_project(
            title=plan.title,
            metadata=plan.metadata,
            rights_category=plan.rights_category,
            source=source_part,
            chord_document=chord_record,
        )
        write_source_project(project_path, project)
        validate_source_receipt_files(receipt.to_dict(), root=staging)

        for immutable in (
            original,
            canonical,
            copied_chord,
            receipt_path,
            project_path,
        ):
            if immutable is not None:
                immutable.chmod(0o444)
        _publish_directory_no_replace(
            staging,
            destination,
            parent_fd=parent_fd,
        )
    except BaseException:
        if staging is not None and _parent_descriptor_matches(
            destination.parent, parent_fd
        ):
            shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        os.close(parent_fd)

    return SourceImportResult(
        root=destination,
        original=destination / plan.original_relative_path,
        canonical=destination / plan.canonical_relative_path,
        receipt=destination / plan.receipt_relative_path,
        source_project=destination / plan.project_relative_path,
        chord_document=(
            destination / plan.chord_relative_path
            if plan.chord_relative_path is not None
            else None
        ),
        source_id=f"sha256:{plan.source_sha256}",
    )


def import_source(
    source: str | Path,
    destination: str | Path,
    *,
    ffmpeg: str | Path,
    ffprobe: str | Path,
    **options: Any,
) -> SourceImportResult:
    """Convenience wrapper retaining the explicit plan/execute implementation."""

    plan = plan_source_import(
        source,
        destination,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        **options,
    )
    return execute_source_import(plan)


def inspect_pcm24_wav(path: str | Path) -> dict[str, Any]:
    """Inspect integer PCM24 RIFF/RF64 geometry without optional audio packages."""

    source = Path(path)
    with source.open("rb") as handle:
        header = handle.read(12)
        if len(header) != 12 or header[8:12] != b"WAVE":
            raise ValueError("canonical output is not a WAVE file")
        if header[:4] not in {b"RIFF", b"RF64"}:
            raise ValueError("canonical output is not RIFF or RF64")
        rf64 = header[:4] == b"RF64"
        data_size_64: int | None = None
        fmt: bytes | None = None
        data_size: int | None = None
        while True:
            chunk_header = handle.read(8)
            if not chunk_header:
                break
            if len(chunk_header) != 8:
                raise ValueError("canonical WAVE has a truncated chunk header")
            chunk_id, chunk_size = struct.unpack("<4sI", chunk_header)
            if chunk_id == b"data":
                data_size = (
                    data_size_64
                    if rf64 and chunk_size == 0xFFFFFFFF
                    else chunk_size
                )
                remaining = source.stat().st_size - handle.tell()
                if data_size is None or data_size > remaining:
                    raise ValueError("canonical WAVE has a truncated data chunk")
                break
            chunk = handle.read(chunk_size)
            if len(chunk) != chunk_size:
                raise ValueError("canonical WAVE has a truncated chunk")
            if chunk_size % 2:
                if len(handle.read(1)) != 1:
                    raise ValueError("canonical WAVE has truncated chunk padding")
            if chunk_id == b"ds64" and len(chunk) >= 16:
                data_size_64 = struct.unpack_from("<Q", chunk, 8)[0]
            elif chunk_id == b"fmt ":
                fmt = chunk
        if fmt is None or len(fmt) < 16:
            raise ValueError("canonical WAVE has no complete fmt chunk")
        if data_size is None:
            raise ValueError("canonical WAVE has no data chunk")
        audio_format, channels, sample_rate = struct.unpack_from("<HHI", fmt, 0)
        block_align, bits_per_sample = struct.unpack_from("<HH", fmt, 12)
        if audio_format == 0xFFFE:
            if len(fmt) < 40 or struct.unpack_from("<H", fmt, 24)[0] != 1:
                raise ValueError("canonical WAVE extensible subtype is not PCM")
        elif audio_format != 1:
            raise ValueError("canonical WAVE format is not integer PCM")
        if bits_per_sample != 24 or block_align != channels * 3:
            raise ValueError("canonical WAVE is not packed 24-bit PCM")
        if channels <= 0 or sample_rate <= 0 or data_size % block_align:
            raise ValueError("canonical WAVE geometry is invalid")
        return {
            "sample_format": "pcm_s24le",
            "sample_width_bytes": 3,
            "sample_rate": sample_rate,
            "channels": channels,
            "frames": data_size // block_align,
            "data_bytes": data_size,
        }


def _build_receipt(
    plan: SourceImportPlan,
    *,
    canonical_geometry: Mapping[str, Any],
    canonical_sha256: str,
    decoder_arguments: list[str],
) -> SourceImportReceipt:
    original = {
        "name": plan.source.name,
        "path": plan.original_relative_path,
        "bytes": plan.probe.source_bytes,
        "sha256": plan.source_sha256,
        "container": plan.probe.decision.container,
        "reported_container_names": list(plan.probe.container_names),
        "codec": plan.probe.codec,
        "sample_format": plan.probe.sample_format,
        "sample_rate": plan.probe.sample_rate,
        "channels": plan.probe.channels,
        "channel_layout": plan.probe.channel_layout,
        "duration_seconds": plan.probe.duration_seconds,
        "lossless": plan.probe.decision.lossless,
    }
    public_geometry = {
        key: value
        for key, value in canonical_geometry.items()
        if key != "container_bytes"
    }
    canonical = {
        "path": plan.canonical_relative_path,
        "sha256": canonical_sha256,
        "bytes": int(
            canonical_geometry.get(
                "container_bytes", int(canonical_geometry["data_bytes"]) + 44
            )
        ),
        **public_geometry,
        "channel_layout": plan.probe.channel_layout,
    }
    clock = {
        "format_start_time_seconds": plan.probe.format_start_time_seconds,
        "stream_start_time_seconds": plan.probe.stream_start_time_seconds,
        "stream_time_base": plan.probe.stream_time_base,
        "stream_start_pts": plan.probe.stream_start_pts,
        "stream_duration_ts": plan.probe.stream_duration_ts,
        "initial_padding_samples": plan.probe.initial_padding_samples,
        "trailing_padding_samples": plan.probe.trailing_padding_samples,
        "skip_samples": plan.probe.skip_samples,
        "discard_padding_samples": plan.probe.discard_padding_samples,
        "first_retained_source_sample": plan.probe.first_retained_source_sample,
        "decoder_padding_samples": plan.probe.decoder_padding_samples,
        "decoded_frame_count": canonical_geometry["frames"],
    }
    capabilities = plan.decoder_capabilities
    decoder = {
        "name": "ffmpeg",
        "ffmpeg": dict(capabilities["ffmpeg"]),
        "ffprobe": dict(capabilities["ffprobe"]),
        "arguments": decoder_arguments,
        "argument_path_bindings": {
            "<SOURCE>": plan.original_relative_path,
            "<CANONICAL>": plan.canonical_relative_path,
        },
        "network_protocols": ["file"],
        "normalization_filters": [],
    }
    return SourceImportReceipt(
        source_id=f"sha256:{plan.source_sha256}",
        original=original,
        canonical=canonical,
        clock=clock,
        decoder=decoder,
        limits={
            **plan.limits.to_dict(),
            "decode_timeout_seconds": plan.decode_timeout_seconds,
            "projected_canonical_bytes": plan.probe.projected_pcm24_bytes,
            "required_free_bytes": plan.required_free_bytes,
        },
    )


def _validate_canonical_geometry(
    plan: SourceImportPlan,
    canonical_geometry: Mapping[str, Any],
) -> None:
    """Apply the common one-part decoded-size and clock boundary."""

    if (
        canonical_geometry["container_bytes"]
        > plan.limits.maximum_canonical_bytes
    ):
        raise RuntimeError(
            "decoded canonical asset exceeds its planned size limit"
        )
    if canonical_geometry["sample_rate"] != plan.probe.sample_rate:
        raise RuntimeError("canonical decode changed the source sample rate")
    if canonical_geometry["channels"] != plan.probe.channels:
        raise RuntimeError("canonical decode changed the source channel count")
    maximum_declared_frames = (
        math.ceil(plan.probe.duration_seconds * plan.probe.sample_rate) + 1
    )
    minimum_plausible_frames = max(
        1,
        math.floor(plan.probe.duration_seconds * plan.probe.sample_rate)
        - plan.probe.first_retained_source_sample
        - plan.probe.decoder_padding_samples
        - 1,
    )
    if canonical_geometry["frames"] < minimum_plausible_frames:
        raise RuntimeError(
            "canonical decode is shorter than the declared source clock "
            "and codec-padding evidence allow"
        )
    if canonical_geometry["frames"] > maximum_declared_frames:
        raise RuntimeError(
            "canonical decode exceeded the declared source duration"
        )


def _ffmpeg_decode_arguments(
    source: Path,
    canonical: Path,
    *,
    duration_seconds: float,
    maximum_output_bytes: int,
) -> list[str]:
    return [
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-protocol_whitelist",
        "file",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        "-vn",
        "-sn",
        "-dn",
        "-t",
        f"{duration_seconds:.9f}",
        "-c:a",
        "pcm_s24le",
        "-fflags",
        "+bitexact",
        "-flags:a",
        "+bitexact",
        "-metadata",
        "encoder=",
        "-write_bext",
        "0",
        "-rf64",
        "auto",
        "-f",
        "wav",
        "-fs",
        str(maximum_output_bytes),
        str(canonical),
    ]


def _receipt_arguments(arguments: list[str]) -> list[str]:
    result = list(arguments)
    input_index = result.index("-i") + 1
    result[input_index] = "<SOURCE>"
    result[-1] = "<CANONICAL>"
    return result


def _run_decode(
    ffmpeg: Path, arguments: list[str], *, timeout_seconds: float
) -> None:
    environment = dict(os.environ)
    environment.update({"LANG": "C", "LC_ALL": "C"})
    try:
        completed = subprocess.run(
            [str(ffmpeg), *arguments],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
            env=environment,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"ffmpeg decode exceeded the {timeout_seconds:.1f}s limit"
        ) from exc
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        if len(detail) > 1000:
            detail = detail[:1000] + "..."
        raise RuntimeError(
            f"ffmpeg decode failed with exit code {completed.returncode}: "
            f"{detail or 'no diagnostic output'}"
        )


def _verify_decoder_identities(plan: SourceImportPlan) -> None:
    """Reject a decoder path or binary that drifted from the inspected plan."""

    for name, executable in (("ffmpeg", plan.ffmpeg), ("ffprobe", plan.ffprobe)):
        expected = plan.decoder_capabilities[name]["sha256"]
        try:
            current = resolve_executable(executable)
            current_hash = file_sha256(current)
        except (FileNotFoundError, PermissionError, OSError) as exc:
            raise ValueError(
                f"{name} changed after the import plan was created"
            ) from exc
        if current != executable or current_hash != expected:
            raise ValueError(
                f"{name} changed after the import plan was created"
            )


def _publish_directory_no_replace(
    staging: Path,
    destination: Path,
    *,
    parent_fd: int,
) -> None:
    """Atomically publish one directory while refusing an occupied path."""

    if staging.parent != destination.parent:
        raise ValueError("atomic import publication must stay on one parent")
    _require_parent_descriptor(destination.parent, parent_fd)
    library = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(staging.name)
    destination_bytes = os.fsencode(destination.name)
    if sys.platform == "darwin":
        rename = library.renameatx_np
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        result = rename(
            parent_fd,
            source_bytes,
            parent_fd,
            destination_bytes,
            0x00000004 | 0x00000010 | 0x00000020,
        )
    elif sys.platform.startswith("linux"):
        try:
            rename = library.renameat2
        except AttributeError as exc:
            raise RuntimeError(
                "this platform cannot publish an import atomically "
                "without replacing an existing destination"
            ) from exc
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        result = rename(
            parent_fd,
            source_bytes,
            parent_fd,
            destination_bytes,
            1,
        )
    else:
        raise RuntimeError(
            "this platform cannot publish an import atomically "
            "without replacing an existing destination"
        )
    if result == 0:
        return
    error = ctypes.get_errno()
    if error in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(
            f"source import destination became occupied: {destination}"
        )
    raise OSError(error, os.strerror(error), str(destination))


def _open_destination_parent(parent: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(parent, flags)
    try:
        _require_parent_descriptor(parent, descriptor)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _create_staging_directory(parent_fd: int, destination: Path) -> Path:
    for _attempt in range(100):
        name = (
            f".{destination.name}.importing-"
            f"{secrets.token_hex(8)}"
        )
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError:
            continue
        return destination.parent / name
    raise FileExistsError("could not reserve a unique import staging directory")


def _parent_descriptor_matches(parent: Path, descriptor: int) -> bool:
    try:
        current = os.stat(parent, follow_symlinks=False)
        opened = os.fstat(descriptor)
    except OSError:
        return False
    return (
        stat.S_ISDIR(current.st_mode)
        and current.st_dev == opened.st_dev
        and current.st_ino == opened.st_ino
    )


def _require_parent_descriptor(parent: Path, descriptor: int) -> None:
    if not _parent_descriptor_matches(parent, descriptor):
        raise ValueError(
            "source import destination parent changed during execution"
        )


def _execution_destination(
    plan: SourceImportPlan,
    *,
    source: Path,
) -> Path:
    if plan.destination == source.parent or _is_relative_to(
        plan.destination, source.parent
    ):
        raise ValueError(
            "source import destination must remain outside the source folder"
        )
    destination = _destination_path(plan.destination)
    if destination != plan.destination:
        raise ValueError(
            "source import destination path changed after planning"
        )
    if destination == source.parent or _is_relative_to(
        destination, source.parent
    ):
        raise ValueError(
            "source import destination must remain outside the source folder"
        )
    return destination


def _resolve_chord_document(
    source: Path,
    *,
    explicit: str | Path | None,
    discover: bool,
) -> Path | None:
    if explicit is not None:
        return _validate_chord_document(explicit)
    return discover_chord_document(source) if discover else None


def _validate_chord_document(path: str | Path) -> Path:
    text = os.fspath(path)
    if "://" in text:
        raise ValueError("remote chord documents are not accepted")
    candidate = Path(text).expanduser().absolute()
    if candidate.is_symlink():
        raise ValueError("symbolic-link chord documents are not accepted")
    if not candidate.is_file():
        raise FileNotFoundError(f"chord document is not a file: {candidate}")
    candidate = candidate.resolve()
    if candidate.suffix.casefold() not in {".pdf", ".txt"}:
        raise ValueError("chord document must be PDF or plain text")
    if candidate.stat().st_size > 64 * 1024**2:
        raise ValueError("chord document exceeds the 64 MiB safety limit")
    return candidate


def _destination_path(destination: str | Path) -> Path:
    text = os.fspath(destination)
    if "://" in text:
        raise ValueError("source import destination must be local")
    candidate = Path(text).expanduser().absolute()
    if candidate.exists() or candidate.is_symlink():
        raise FileExistsError(f"source import destination exists: {candidate}")
    parent = _nearest_existing_parent(candidate.parent).resolve()
    unresolved = candidate.parent
    missing_parts: list[str] = []
    while not unresolved.exists():
        missing_parts.append(unresolved.name)
        unresolved = unresolved.parent
    rebuilt = parent
    for part in reversed(missing_parts):
        rebuilt /= part
    return rebuilt / candidate.name


def _nearest_existing_parent(path: Path) -> Path:
    candidate = path
    while not candidate.exists():
        if candidate == candidate.parent:
            raise FileNotFoundError("no existing parent for import destination")
        candidate = candidate.parent
    if not candidate.is_dir():
        raise NotADirectoryError(f"import destination parent is not a directory: {candidate}")
    return candidate


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _safe_filename(value: str) -> str:
    stem = _safe_stem(Path(value).stem)
    suffix = re.sub(r"[^a-z0-9]+", "", Path(value).suffix.casefold())
    return f"{stem}.{suffix}" if suffix else stem


def _safe_stem(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", normalized).strip("._-")
    safe = re.sub(r"-{2,}", "-", safe)
    return (safe or "source")[:180]


__all__ = [
    "SourceImportPlan",
    "SourceImportResult",
    "execute_source_import",
    "import_source",
    "inspect_pcm24_wav",
    "plan_source_import",
]
