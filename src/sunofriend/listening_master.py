"""Deterministic loudness/true-peak mastering for a reviewed MIDI balance.

The successful gain-only Workbench balance remains the technical control.
This module creates a separate listening-master challenger from that verified
WAV.  It never changes MIDI, source audio, Workbench choices, or the control
render.

FFmpeg's ``loudnorm`` filter is used in two processing passes, followed by a
third analysis pass over the encoded PCM24 artifact.  The receipt therefore
binds both the render log and measurements of the bytes that are actually
published.  The output is trimmed back to the input frame horizon after
filtering because GarageBand alignment is more important than retaining a
renderer/filter tail.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .listening_master_contract import (
    ENCODED_ARTIFACT_LABEL,
    FFMPEG_IDENTITY_POLICY,
    INTEGRATED_LOUDNESS_TOLERANCE_LU,
    LISTENING_MASTER_EFFECTS,
    LISTENING_MASTER_LABEL,
    LISTENING_MASTER_POLICY,
    LISTENING_MASTER_PROCESSING_FLAGS,
    LISTENING_MASTER_SCHEMA,
    LISTENING_MASTER_SCOPE,
    LISTENING_MASTER_TARGETS,
    LISTENING_MASTER_TIMING_POLICY,
    LISTENING_MASTER_VERIFICATION_SCHEMA,
    LOUDNORM_FIELDS,
    TARGET_INTEGRATED_LUFS,
    TARGET_LOUDNESS_RANGE_LU,
    TRUE_PEAK_CEILING_DBTP,
    TRUE_PEAK_TOLERANCE_DB,
    require_encoded_master_targets as _require_encoded_master_targets,
    validated_loudnorm_stats as _validated_loudnorm_stats,
)


# Private aliases are retained for callers of the original v2 implementation.
# New consumers must import the public names from listening_master_contract.
_TARGET_INTEGRATED_LUFS = TARGET_INTEGRATED_LUFS
_TARGET_LOUDNESS_RANGE_LU = TARGET_LOUDNESS_RANGE_LU
_TRUE_PEAK_CEILING_DBTP = TRUE_PEAK_CEILING_DBTP
_LOUDNESS_TOLERANCE_LU = INTEGRATED_LOUDNESS_TOLERANCE_LU
_TRUE_PEAK_TOLERANCE_DB = TRUE_PEAK_TOLERANCE_DB
_MAXIMUM_SECONDS = 20 * 60
_MAXIMUM_SOURCE_BYTES = 2 * 1024 * 1024 * 1024
_MAXIMUM_FFMPEG_OUTPUT_BYTES = 512 * 1024
_LOUDNORM_FIELDS = LOUDNORM_FIELDS
LISTENING_MASTER_PREFLIGHT_SCHEMA = (
    "sunofriend.listening-master-dependency-preflight.v1"
)


@dataclass(frozen=True)
class _FileIdentity:
    device: int
    inode: int


@dataclass(frozen=True)
class _PinnedExecutable:
    path: Path
    fd: int
    identity: _FileIdentity
    size: int
    mtime_ns: int
    ctime_ns: int
    sha256: str


@dataclass(frozen=True)
class _PrivateDirectory:
    parent_fd: int
    parent_path: Path
    name: str
    fd: int
    identity: _FileIdentity


@dataclass(frozen=True)
class _PrivateFile:
    directory: _PrivateDirectory
    name: str
    fd: int
    identity: _FileIdentity


def check_listening_master_dependencies(
    ffmpeg_path: str | Path | None = None,
) -> dict[str, Any]:
    """Verify the fixed mastering runtime and return path-free evidence.

    This performs the same import, pinned-executable identity, and ``loudnorm``
    capability checks used by :func:`build_listening_master`, without reading
    source audio or creating output files.  The returned document deliberately
    omits the resolved executable path so it is safe to surface in bounded
    application state and diagnostic views.  Dependency failures still raise
    ``RuntimeError`` and create no artifacts.
    """

    soundfile = _soundfile_module()
    executable = _pin_ffmpeg(_resolve_ffmpeg(ffmpeg_path))
    try:
        ffmpeg_identity = _ffmpeg_identity(executable)
        _require_loudnorm_filter(executable)
    finally:
        try:
            os.close(executable.fd)
        except OSError:
            pass

    soundfile_version = getattr(soundfile, "__version__", None)
    libsndfile_version = getattr(soundfile, "__libsndfile_version__", None)
    return {
        "schema": LISTENING_MASTER_PREFLIGHT_SCHEMA,
        "ready": True,
        "soundfile": {
            "available": True,
            "version": (
                str(soundfile_version)[:200]
                if soundfile_version is not None
                else None
            ),
            "libsndfile_version": (
                str(libsndfile_version)[:200]
                if libsndfile_version is not None
                else None
            ),
        },
        "ffmpeg": ffmpeg_identity,
    }


def build_listening_master(
    source_path: str | Path,
    *,
    output_path: str | Path,
    report_path: str | Path,
    ffmpeg_path: str | Path | None = None,
) -> dict[str, Any]:
    """Create one fresh PCM24 listening master and an exact path-free receipt.

    The policy is deliberately fixed in v1.  Callers cannot tune targets or
    inject an arbitrary filter graph, which keeps different reviews
    comparable.  Existing output or report paths are never replaced.
    """

    source = Path(source_path).expanduser().resolve()
    output = _fresh_path(output_path, label="listening-master WAV", suffix=".wav")
    report = _fresh_path(report_path, label="listening-master report", suffix=".json")
    if source in {output, report} or output == report:
        raise ValueError("listening-master input and outputs must be different")
    if not source.is_file():
        raise ValueError(f"listening-master source WAV not found: {source}")

    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    output_parent_fd = _open_directory(output.parent)
    report_parent_fd = _open_directory(report.parent)
    output_workspace: _PrivateDirectory | None = None
    report_workspace: _PrivateDirectory | None = None
    source_snapshot: _PrivateFile | None = None
    temporary: _PrivateFile | None = None
    report_temporary: _PrivateFile | None = None
    output_published = False
    report_published = False
    output_identity: _FileIdentity | None = None
    report_identity: _FileIdentity | None = None
    executable: _PinnedExecutable | None = None
    try:
        output_workspace = _create_private_directory(
            output.parent,
            output_parent_fd,
        )
        report_workspace = _create_private_directory(
            report.parent,
            report_parent_fd,
        )
        source_snapshot, source_record = _write_private_source_snapshot(
            source,
            output_workspace,
        )
        soundfile = _soundfile_module()
        source_info = _audio_info_fd(
            soundfile,
            source_snapshot,
            label="listening-master source snapshot",
        )
        if source_info["format"] not in {"WAV", "WAVEX"}:
            raise ValueError("listening-master source must be a WAV file")
        if source_info["channels"] not in {1, 2}:
            raise ValueError("listening-master source must be mono or stereo")
        if source_info["frames"] <= 0:
            raise ValueError("listening-master source contains no audio frames")
        if source_info["duration_seconds"] > _MAXIMUM_SECONDS:
            raise ValueError("listening-master supports songs up to 20 minutes")

        executable = _pin_ffmpeg(_resolve_ffmpeg(ffmpeg_path))
        ffmpeg_identity = _ffmpeg_identity(executable)
        _require_loudnorm_filter(executable)
        analysis_fd = _open_private_file_readonly(source_snapshot)
        try:
            first = _run_ffmpeg(
                executable,
                [
                    "-hide_banner",
                    "-nostdin",
                    "-nostats",
                    "-i",
                    _fd_path(analysis_fd),
                    "-af",
                    _first_pass_filter(),
                    "-f",
                    "null",
                    "-",
                ],
                label="listening-master analysis pass",
                pass_fds=(analysis_fd,),
            )
        finally:
            os.close(analysis_fd)
        first_stats = _parse_loudnorm_stats(first.stderr)
        second_filter = _second_pass_filter(
            first_stats,
            sample_rate=int(source_info["sample_rate"]),
            frames=int(source_info["frames"]),
        )

        temporary = _create_private_file(output_workspace, suffix=".tmp.wav")
        os.ftruncate(temporary.fd, 0)
        os.lseek(temporary.fd, 0, os.SEEK_SET)
        render_source_fd = _open_private_file_readonly(source_snapshot)
        try:
            second = _run_ffmpeg(
                executable,
                [
                    "-hide_banner",
                    "-nostdin",
                    "-nostats",
                    "-i",
                    _fd_path(render_source_fd),
                    "-map_metadata",
                    "-1",
                    "-af",
                    second_filter,
                    "-ar",
                    str(source_info["sample_rate"]),
                    "-ac",
                    str(source_info["channels"]),
                    "-c:a",
                    "pcm_s24le",
                    "-f",
                    "wav",
                    "-y",
                    _fd_path(temporary.fd),
                ],
                label="listening-master render pass",
                pass_fds=(render_source_fd, temporary.fd),
            )
        finally:
            os.close(render_source_fd)
        second_stats = _parse_loudnorm_stats(second.stderr)
        _require_private_file_identity(temporary)
        os.fsync(temporary.fd)
        os.lseek(temporary.fd, 0, os.SEEK_SET)
        rendered_info = _audio_info_fd(
            soundfile,
            temporary,
            label="listening-master rendered WAV",
        )
        _require_same_audio_horizon(source_info, rendered_info)

        # Validate the bytes that will be published, not FFmpeg's prediction
        # in the render log.
        verification_fd = _open_private_file_readonly(temporary)
        try:
            verification = _run_ffmpeg(
                executable,
                [
                    "-hide_banner",
                    "-nostdin",
                    "-nostats",
                    "-i",
                    _fd_path(verification_fd),
                    "-af",
                    _verification_filter(),
                    "-f",
                    "null",
                    "-",
                ],
                label="listening-master encoded-artifact verification pass",
                pass_fds=(verification_fd,),
            )
        finally:
            os.close(verification_fd)
        verification_stats = _parse_loudnorm_stats(verification.stderr)
        _require_encoded_master_targets(verification_stats)
        output_record = _file_record_fd(temporary)

        payload: dict[str, Any] = {
            "schema": LISTENING_MASTER_SCHEMA,
            "status": "complete",
            "policy": LISTENING_MASTER_POLICY,
            "label": LISTENING_MASTER_LABEL,
            "mastered": True,
            "release_master": False,
            "mastering_scope": LISTENING_MASTER_SCOPE,
            "source": {
                "sha256": source_record["sha256"],
                "bytes": source_record["bytes"],
                "format": source_info["format"],
                "subtype": source_info["subtype"],
                "sample_rate": source_info["sample_rate"],
                "channels": source_info["channels"],
                "frames": source_info["frames"],
                "duration_seconds": source_info["duration_seconds"],
            },
            "targets": dict(LISTENING_MASTER_TARGETS),
            "analysis_pass": first_stats,
            "render_pass": second_stats,
            "verification_pass": {
                **verification_stats,
                "measured_artifact": ENCODED_ARTIFACT_LABEL,
            },
            "renderer": ffmpeg_identity,
            "output": {
                "name": output.name,
                "sha256": output_record["sha256"],
                "bytes": output_record["bytes"],
                "format": rendered_info["format"],
                "subtype": rendered_info["subtype"],
                "sample_rate": rendered_info["sample_rate"],
                "channels": rendered_info["channels"],
                "frames": rendered_info["frames"],
                "duration_seconds": rendered_info["duration_seconds"],
            },
            "timing": {
                "policy": LISTENING_MASTER_TIMING_POLICY,
                "input_frames": source_info["frames"],
                "output_frames": rendered_info["frames"],
                "sample_rate": source_info["sample_rate"],
                "frame_horizon_changed": False,
                "time_shift_applied": False,
                "time_stretch_applied": False,
            },
            "processing": {
                "normalization_type": second_stats["normalization_type"],
                **dict(LISTENING_MASTER_PROCESSING_FLAGS),
            },
            "effects": dict(LISTENING_MASTER_EFFECTS),
        }
        payload["receipt_sha256"] = _document_hash(payload)
        report_temporary = _create_private_file(
            report_workspace,
            suffix=".tmp.json",
        )
        _write_json_fd(report_temporary, payload)
        report_record = _file_record_fd(report_temporary)

        _publish_private_file(
            temporary,
            destination_parent_fd=output_parent_fd,
            destination_name=output.name,
        )
        output_published = True
        output_identity = temporary.identity
        _publish_private_file(
            report_temporary,
            destination_parent_fd=report_parent_fd,
            destination_name=report.name,
        )
        report_published = True
        report_identity = report_temporary.identity
        _require_entry_identity(
            output_parent_fd,
            output.name,
            output_identity,
            label="published listening-master WAV",
        )
        _require_entry_identity(
            report_parent_fd,
            report.name,
            report_identity,
            label="published listening-master report",
        )
        _fsync_distinct_directories(output_parent_fd, report_parent_fd)
    except BaseException:
        rollback_directories: list[int] = []
        if report_published and report_identity is not None:
            if _unlink_if_identity(
                report_parent_fd,
                report.name,
                report_identity,
            ):
                rollback_directories.append(report_parent_fd)
        if output_published and output_identity is not None:
            if _unlink_if_identity(
                output_parent_fd,
                output.name,
                output_identity,
            ):
                rollback_directories.append(output_parent_fd)
        _fsync_distinct_directories(*rollback_directories)
        raise
    finally:
        if executable is not None:
            try:
                os.close(executable.fd)
            except OSError:
                pass
        for private_file in (report_temporary, temporary, source_snapshot):
            if private_file is not None:
                _close_and_unlink_private_file(private_file)
        for private_directory in (report_workspace, output_workspace):
            if private_directory is not None:
                _close_and_remove_private_directory(private_directory)
        os.close(report_parent_fd)
        os.close(output_parent_fd)

    return {
        "status": "complete",
        "master": str(output),
        "master_sha256": output_record["sha256"],
        "report": str(report),
        "report_sha256": report_record["sha256"],
        "receipt_sha256": payload["receipt_sha256"],
        "input_integrated_lufs": first_stats["input_i"],
        "output_integrated_lufs": verification_stats["input_i"],
        "output_true_peak_dbtp": verification_stats["input_tp"],
        "mastered": True,
        "release_master": False,
        "source_audio_mutated": False,
        "midi_mutated": False,
        "selection_changed": False,
    }


def _first_pass_filter() -> str:
    return (
        "loudnorm="
        f"I={_format_number(_TARGET_INTEGRATED_LUFS)}:"
        f"LRA={_format_number(_TARGET_LOUDNESS_RANGE_LU)}:"
        f"TP={_format_number(_TRUE_PEAK_CEILING_DBTP)}:"
        "print_format=json"
    )


def _verification_filter() -> str:
    # ``dual_mono`` is explicit so test doubles and receipts can distinguish
    # this third encoded-artifact measurement from the source analysis.
    return (
        "loudnorm="
        f"I={_format_number(_TARGET_INTEGRATED_LUFS)}:"
        f"LRA={_format_number(_TARGET_LOUDNESS_RANGE_LU)}:"
        f"TP={_format_number(_TRUE_PEAK_CEILING_DBTP)}:"
        "dual_mono=false:print_format=json"
    )


def _second_pass_filter(
    first_stats: Mapping[str, Any],
    *,
    sample_rate: int,
    frames: int,
) -> str:
    _validated_loudnorm_stats(first_stats)
    if sample_rate <= 0 or frames <= 0:
        raise ValueError("listening-master audio geometry is invalid")
    loudnorm = (
        "loudnorm="
        f"I={_format_number(_TARGET_INTEGRATED_LUFS)}:"
        f"LRA={_format_number(_TARGET_LOUDNESS_RANGE_LU)}:"
        f"TP={_format_number(_TRUE_PEAK_CEILING_DBTP)}:"
        f"measured_I={_format_number(first_stats['input_i'])}:"
        f"measured_LRA={_format_number(first_stats['input_lra'])}:"
        f"measured_TP={_format_number(first_stats['input_tp'])}:"
        f"measured_thresh={_format_number(first_stats['input_thresh'])}:"
        f"offset={_format_number(first_stats['target_offset'])}:"
        "linear=true:print_format=json"
    )
    return (
        f"{loudnorm},aresample={int(sample_rate)},"
        f"atrim=end_sample={int(frames)},asetpts=N/SR/TB"
    )


def _parse_loudnorm_stats(stderr: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    candidates: list[Mapping[str, Any]] = []
    for match in re.finditer(r"\{", stderr):
        try:
            value, _end = decoder.raw_decode(stderr[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping) and _LOUDNORM_FIELDS <= set(value):
            candidates.append(value)
    if not candidates:
        raise RuntimeError("FFmpeg loudnorm did not return its JSON measurements")
    return _validated_loudnorm_stats(candidates[-1])


def _resolve_ffmpeg(value: str | Path | None) -> Path:
    candidate = shutil.which("ffmpeg") if value is None else os.fspath(value)
    if not candidate:
        raise RuntimeError("listening-master requires FFmpeg with the loudnorm filter")
    path = Path(candidate).expanduser().resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise RuntimeError(f"FFmpeg executable is unavailable: {path}")
    return path


def _ffmpeg_identity(executable: _PinnedExecutable) -> dict[str, Any]:
    completed = _run_ffmpeg(
        executable,
        ["-hide_banner", "-version"],
        label="FFmpeg version check",
    )
    first_line = completed.stdout.splitlines()[0].strip() if completed.stdout else ""
    if not first_line.startswith("ffmpeg version "):
        raise RuntimeError("cannot identify the FFmpeg executable")
    return {
        "backend": "FFmpeg loudnorm",
        "executable_sha256": executable.sha256,
        "version": first_line[:500],
        "filter": "loudnorm",
        "policy": LISTENING_MASTER_POLICY,
        "identity_verification": FFMPEG_IDENTITY_POLICY,
    }


def _require_loudnorm_filter(executable: _PinnedExecutable) -> None:
    completed = _run_ffmpeg(
        executable,
        ["-hide_banner", "-filters"],
        label="FFmpeg loudnorm capability check",
    )
    if not re.search(r"(?m)^\s*\S+\s+loudnorm\s+", completed.stdout):
        raise RuntimeError("FFmpeg does not provide the required loudnorm filter")


def _run_ffmpeg(
    executable: _PinnedExecutable,
    arguments: Sequence[str],
    *,
    label: str,
    pass_fds: Sequence[int] = (),
) -> subprocess.CompletedProcess[str]:
    _require_pinned_ffmpeg(executable)
    try:
        completed = subprocess.run(
            [str(executable.path), *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            pass_fds=tuple(sorted(set(pass_fds))),
        )
    finally:
        # Recheck even when process creation or execution fails.  A concurrent
        # replacement must never leave a receipt that describes different
        # executable bytes from those admitted for the pass.
        _require_pinned_ffmpeg(executable)
    if (
        len(completed.stdout.encode("utf-8", errors="replace"))
        + len(completed.stderr.encode("utf-8", errors="replace"))
        > _MAXIMUM_FFMPEG_OUTPUT_BYTES
    ):
        raise RuntimeError(f"{label} produced too much diagnostic output")
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        suffix = f": {detail[-1][:500]}" if detail else ""
        raise RuntimeError(f"{label} failed{suffix}")
    return completed


def _pin_ffmpeg(path: Path) -> _PinnedExecutable:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError("could not pin the FFmpeg executable") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("FFmpeg executable is not a regular file")
        identity = _identity(metadata)
        pinned = _PinnedExecutable(
            path=path,
            fd=descriptor,
            identity=identity,
            size=int(metadata.st_size),
            mtime_ns=int(metadata.st_mtime_ns),
            ctime_ns=int(metadata.st_ctime_ns),
            sha256=_sha256_fd(descriptor, int(metadata.st_size)),
        )
        _require_pinned_ffmpeg(pinned)
        return pinned
    except Exception:
        os.close(descriptor)
        raise


def _require_pinned_ffmpeg(executable: _PinnedExecutable) -> None:
    descriptor_metadata = os.fstat(executable.fd)
    try:
        path_metadata = os.stat(executable.path, follow_symlinks=False)
    except OSError as exc:
        raise RuntimeError("FFmpeg executable changed identity") from exc
    expected_metadata = (
        executable.identity,
        executable.size,
        executable.mtime_ns,
        executable.ctime_ns,
    )
    for metadata in (descriptor_metadata, path_metadata):
        observed_metadata = (
            _identity(metadata),
            int(metadata.st_size),
            int(metadata.st_mtime_ns),
            int(metadata.st_ctime_ns),
        )
        if observed_metadata != expected_metadata:
            raise RuntimeError("FFmpeg executable changed identity")
    if _sha256_fd(executable.fd, executable.size) != executable.sha256:
        raise RuntimeError("FFmpeg executable content changed")


def _audio_info_fd(
    soundfile: Any,
    private_file: _PrivateFile,
    *,
    label: str,
) -> dict[str, Any]:
    _require_private_file_identity(private_file)
    position = os.lseek(private_file.fd, 0, os.SEEK_CUR)
    try:
        with os.fdopen(os.dup(private_file.fd), "rb") as handle:
            handle.seek(0)
            info = soundfile.info(handle)
    except Exception as exc:
        raise ValueError(f"{label} is unreadable") from exc
    finally:
        os.lseek(private_file.fd, position, os.SEEK_SET)
    _require_private_file_identity(private_file)
    sample_rate = int(info.samplerate)
    frames = int(info.frames)
    return {
        "format": str(info.format),
        "subtype": str(info.subtype),
        "sample_rate": sample_rate,
        "channels": int(info.channels),
        "frames": frames,
        "duration_seconds": round(frames / sample_rate, 6) if sample_rate else 0.0,
    }


def _require_same_audio_horizon(
    source: Mapping[str, Any], output: Mapping[str, Any]
) -> None:
    if (
        output.get("format") not in {"WAV", "WAVEX"}
        or output.get("subtype") != "PCM_24"
    ):
        raise RuntimeError("listening-master output is not PCM24 WAV")
    for key in ("sample_rate", "channels", "frames"):
        if output.get(key) != source.get(key):
            raise RuntimeError(
                "listening-master output changed the input audio horizon"
            )


def _fresh_path(value: str | Path, *, label: str, suffix: str) -> Path:
    expanded = Path(value).expanduser()
    absolute = Path(os.path.abspath(os.fspath(expanded)))
    destination = absolute.parent.resolve() / absolute.name
    if destination.suffix.lower() != suffix:
        raise ValueError(f"{label} must end in {suffix}")
    if os.path.lexists(destination):
        raise ValueError(f"{label} already exists: {destination}")
    return destination


def _open_directory(path: Path) -> int:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(
            f"listening-master output directory is unsafe: {path}"
        ) from exc
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        os.close(descriptor)
        raise ValueError(f"listening-master output directory is invalid: {path}")
    return descriptor


def _fsync_distinct_directories(*descriptors: int) -> None:
    seen: set[_FileIdentity] = set()
    for descriptor in descriptors:
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise RuntimeError(
                "listening-master destination parent is no longer a directory"
            )
        identity = _identity(metadata)
        if identity in seen:
            continue
        os.fsync(descriptor)
        seen.add(identity)


def _identity(metadata: os.stat_result) -> _FileIdentity:
    return _FileIdentity(device=int(metadata.st_dev), inode=int(metadata.st_ino))


def _create_private_directory(
    parent_path: Path,
    parent_fd: int,
) -> _PrivateDirectory:
    for _attempt in range(32):
        name = f".sunofriend-listening-master-{secrets.token_hex(16)}.private"
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError:
            continue
        created = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        created_identity = _identity(created)
        if not stat.S_ISDIR(created.st_mode) or created.st_mode & 0o077:
            _rmdir_if_identity(parent_fd, name, created_identity)
            raise RuntimeError(
                "listening-master private directory was not private from creation"
            )
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            descriptor = os.open(name, flags, dir_fd=parent_fd)
        except Exception:
            _rmdir_if_identity(parent_fd, name, created_identity)
            raise
        if _identity(os.fstat(descriptor)) != created_identity:
            os.close(descriptor)
            _rmdir_if_identity(parent_fd, name, created_identity)
            raise RuntimeError("listening-master private directory identity changed")
        return _PrivateDirectory(
            parent_fd=parent_fd,
            parent_path=parent_path,
            name=name,
            fd=descriptor,
            identity=created_identity,
        )
    raise RuntimeError("could not create a fresh listening-master workspace")


def _create_private_file(
    directory: _PrivateDirectory,
    *,
    suffix: str,
) -> _PrivateFile:
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    for _attempt in range(32):
        name = f"artifact-{secrets.token_hex(16)}{suffix}"
        try:
            descriptor = os.open(name, flags, 0o600, dir_fd=directory.fd)
        except FileExistsError:
            continue
        metadata = os.fstat(descriptor)
        identity = _identity(metadata)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
            os.close(descriptor)
            _unlink_if_identity(directory.fd, name, identity)
            raise RuntimeError(
                "listening-master temporary file was not private from creation"
            )
        return _PrivateFile(
            directory=directory,
            name=name,
            fd=descriptor,
            identity=identity,
        )
    raise RuntimeError("could not create a fresh listening-master temporary file")


def _write_private_source_snapshot(
    source: Path,
    directory: _PrivateDirectory,
) -> tuple[_PrivateFile, dict[str, Any]]:
    """Copy one stable private input and return its tracked descriptor."""

    source_flags = (
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        source_fd = os.open(source, source_flags)
    except OSError as exc:
        raise ValueError("listening-master source WAV is unsafe") from exc
    destination = _create_private_file(directory, suffix=".source.wav")
    digest = hashlib.sha256()
    byte_count = 0
    try:
        metadata = os.fstat(source_fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("listening-master source must be a regular file")
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            byte_count += len(chunk)
            if byte_count > _MAXIMUM_SOURCE_BYTES:
                raise ValueError("listening-master source exceeds the 2 GiB limit")
            _write_all(destination.fd, chunk)
            digest.update(chunk)
        if byte_count <= 0:
            raise ValueError("listening-master source is empty")
        os.fsync(destination.fd)
        _require_private_file_identity(destination)
        return destination, {
            "sha256": digest.hexdigest(),
            "bytes": byte_count,
        }
    except Exception:
        _close_and_unlink_private_file(destination)
        raise
    finally:
        os.close(source_fd)


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("could not write listening-master private artifact")
        view = view[written:]


def _write_json_fd(
    private_file: _PrivateFile,
    value: Mapping[str, Any],
) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    os.ftruncate(private_file.fd, 0)
    os.lseek(private_file.fd, 0, os.SEEK_SET)
    _write_all(private_file.fd, payload)
    os.fsync(private_file.fd)
    _require_private_file_identity(private_file)


def _file_record_fd(private_file: _PrivateFile) -> dict[str, Any]:
    _require_private_file_identity(private_file)
    metadata = os.fstat(private_file.fd)
    digest = hashlib.sha256()
    offset = 0
    while offset < metadata.st_size:
        chunk = os.pread(
            private_file.fd,
            min(1024 * 1024, metadata.st_size - offset),
            offset,
        )
        if not chunk:
            raise RuntimeError("listening-master artifact changed while hashing")
        digest.update(chunk)
        offset += len(chunk)
    _require_private_file_identity(private_file)
    return {"sha256": digest.hexdigest(), "bytes": int(metadata.st_size)}


def _open_private_file_readonly(private_file: _PrivateFile) -> int:
    _require_private_file_identity(private_file)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(
        private_file.name,
        flags,
        dir_fd=private_file.directory.fd,
    )
    if _identity(os.fstat(descriptor)) != private_file.identity:
        os.close(descriptor)
        raise RuntimeError("listening-master private input changed identity")
    return descriptor


def _require_private_file_identity(private_file: _PrivateFile) -> None:
    if _identity(os.fstat(private_file.fd)) != private_file.identity:
        raise RuntimeError("listening-master private file descriptor changed identity")
    _require_entry_identity(
        private_file.directory.fd,
        private_file.name,
        private_file.identity,
        label="listening-master private file",
    )


def _publish_private_file(
    private_file: _PrivateFile,
    *,
    destination_parent_fd: int,
    destination_name: str,
) -> None:
    _require_private_file_identity(private_file)
    os.link(
        private_file.name,
        destination_name,
        src_dir_fd=private_file.directory.fd,
        dst_dir_fd=destination_parent_fd,
        follow_symlinks=False,
    )
    _require_entry_identity(
        destination_parent_fd,
        destination_name,
        private_file.identity,
        label="published listening-master artifact",
    )


def _require_entry_identity(
    directory_fd: int,
    name: str,
    expected: _FileIdentity,
    *,
    label: str,
) -> None:
    try:
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise RuntimeError(f"{label} disappeared") from exc
    if _identity(metadata) != expected:
        raise RuntimeError(f"{label} changed identity")


def _unlink_if_identity(
    directory_fd: int,
    name: str,
    expected: _FileIdentity,
) -> bool:
    try:
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except (FileNotFoundError, OSError):
        return False
    if _identity(metadata) != expected:
        return False
    try:
        os.unlink(name, dir_fd=directory_fd)
    except (FileNotFoundError, OSError):
        return False
    return True


def _rmdir_if_identity(
    directory_fd: int,
    name: str,
    expected: _FileIdentity,
) -> bool:
    try:
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except (FileNotFoundError, OSError):
        return False
    if _identity(metadata) != expected:
        return False
    try:
        os.rmdir(name, dir_fd=directory_fd)
    except (FileNotFoundError, OSError):
        return False
    return True


def _close_and_unlink_private_file(private_file: _PrivateFile) -> None:
    _unlink_if_identity(
        private_file.directory.fd,
        private_file.name,
        private_file.identity,
    )
    try:
        os.close(private_file.fd)
    except OSError:
        pass


def _close_and_remove_private_directory(
    directory: _PrivateDirectory,
) -> None:
    _rmdir_if_identity(directory.parent_fd, directory.name, directory.identity)
    try:
        os.close(directory.fd)
    except OSError:
        pass


def _fd_path(descriptor: int) -> str:
    if Path("/dev/fd").is_dir():
        return f"/dev/fd/{descriptor}"
    return f"/proc/self/fd/{descriptor}"


def _document_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256_fd(descriptor: int, expected_size: int) -> str:
    digest = hashlib.sha256()
    offset = 0
    while offset < expected_size:
        chunk = os.pread(
            descriptor,
            min(1024 * 1024, expected_size - offset),
            offset,
        )
        if not chunk:
            raise RuntimeError("FFmpeg executable changed while hashing")
        digest.update(chunk)
        offset += len(chunk)
    if int(os.fstat(descriptor).st_size) != expected_size:
        raise RuntimeError("FFmpeg executable changed while hashing")
    return digest.hexdigest()


def _format_number(value: Any) -> str:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("listening-master filter value must be finite")
    return f"{number:.6f}"


def _soundfile_module() -> Any:
    try:
        import soundfile
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "listening-master requires soundfile; install Sunofriend with "
            "the convert extra"
        ) from exc
    return soundfile


__all__ = [
    "ENCODED_ARTIFACT_LABEL",
    "FFMPEG_IDENTITY_POLICY",
    "INTEGRATED_LOUDNESS_TOLERANCE_LU",
    "LISTENING_MASTER_EFFECTS",
    "LISTENING_MASTER_LABEL",
    "LISTENING_MASTER_POLICY",
    "LISTENING_MASTER_PREFLIGHT_SCHEMA",
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
    "build_listening_master",
    "check_listening_master_dependencies",
]
