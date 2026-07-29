"""Bounded, container-aware audio inspection for source imports.

This module deliberately does not install FFmpeg, choose a decoder implicitly,
or write project files.  Callers provide the exact ``ffmpeg`` and ``ffprobe``
executables they intend to use.  The capability doctor and probe operations
are read-only and invoke tools without a shell or network protocols.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


PORTABLE_AUDIO_SUFFIXES = frozenset(
    {
        ".wav",
        ".wave",
        ".aif",
        ".aiff",
        ".flac",
        ".m4a",
        ".mp3",
        ".ogg",
        ".oga",
        ".opus",
    }
)
CONDITIONAL_AUDIO_SUFFIXES = frozenset({".aifc", ".caf", ".wma"})
KNOWN_AUDIO_SUFFIXES = PORTABLE_AUDIO_SUFFIXES | CONDITIONAL_AUDIO_SUFFIXES

_PCM_WAV_CODECS = frozenset({"pcm_s16le", "pcm_s24le", "pcm_s32le"})
_PCM_AIFF_CODECS = frozenset({"pcm_s16be", "pcm_s24be", "pcm_s32be"})
_M4A_CONTAINERS = frozenset({"mov", "mp4", "m4a", "3gp", "3g2", "mj2"})
_WMA_CODECS = frozenset(
    {"wmav1", "wmav2", "wmapro", "wmalossless", "wmavoice"}
)
_CHANNEL_LAYOUT_CHANNELS = {
    "mono": 1,
    "stereo": 2,
    "2.1": 3,
    "3.0": 3,
    "3.0(back)": 3,
    "quad": 4,
    "4.0": 4,
    "5.0": 5,
    "5.0(side)": 5,
    "5.1": 6,
    "5.1(side)": 6,
    "6.0": 6,
    "6.0(front)": 6,
    "hexagonal": 6,
    "6.1": 7,
    "6.1(back)": 7,
    "6.1(front)": 7,
    "7.0": 7,
    "7.0(front)": 7,
    "7.1": 8,
    "7.1(wide)": 8,
    "7.1(wide-side)": 8,
    "octagonal": 8,
}


@dataclass(frozen=True)
class AudioImportLimits:
    """Safety limits for an audio import.

    Limits are values recorded in every receipt.  They can be replaced by an
    explicit advanced policy later, but are never expanded silently.
    """

    maximum_input_bytes: int = 2 * 1024**3
    maximum_duration_seconds: float = 30.0 * 60.0
    maximum_channels: int = 8
    maximum_canonical_bytes: int = 8 * 1024**3
    minimum_free_space_headroom_bytes: int = 1024**3
    probe_timeout_seconds: float = 30.0
    minimum_decode_timeout_seconds: float = 120.0
    decode_duration_multiplier: float = 4.0
    maximum_decode_timeout_seconds: float = 30.0 * 60.0

    def __post_init__(self) -> None:
        positive = {
            "maximum_input_bytes": self.maximum_input_bytes,
            "maximum_duration_seconds": self.maximum_duration_seconds,
            "maximum_channels": self.maximum_channels,
            "maximum_canonical_bytes": self.maximum_canonical_bytes,
            "probe_timeout_seconds": self.probe_timeout_seconds,
            "minimum_decode_timeout_seconds": self.minimum_decode_timeout_seconds,
            "decode_duration_multiplier": self.decode_duration_multiplier,
            "maximum_decode_timeout_seconds": self.maximum_decode_timeout_seconds,
        }
        for name, value in positive.items():
            if not math.isfinite(float(value)) or float(value) <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.minimum_free_space_headroom_bytes < 0:
            raise ValueError(
                "minimum_free_space_headroom_bytes must not be negative"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_AUDIO_IMPORT_LIMITS = AudioImportLimits()


@dataclass(frozen=True)
class AudioFormatDecision:
    """Validated public format classification for one probed audio stream."""

    policy_name: str
    container: str
    codec: str
    lossless: bool
    conditional: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AudioProbe:
    """The bounded subset of FFprobe evidence required by source import."""

    source: Path
    source_bytes: int
    stream_index: int
    container_names: tuple[str, ...]
    codec: str
    sample_format: str | None
    sample_rate: int
    channels: int
    channel_layout: str
    duration_seconds: float
    format_start_time_seconds: float | None
    stream_start_time_seconds: float | None
    stream_time_base: str | None
    stream_start_pts: int | None
    stream_duration_ts: int | None
    initial_padding_samples: int
    trailing_padding_samples: int
    skip_samples: int
    discard_padding_samples: int
    decision: AudioFormatDecision

    @property
    def first_retained_source_sample(self) -> int:
        return max(self.initial_padding_samples, self.skip_samples)

    @property
    def decoder_padding_samples(self) -> int:
        return max(self.trailing_padding_samples, self.discard_padding_samples)

    @property
    def projected_pcm24_bytes(self) -> int:
        frames = math.ceil(self.duration_seconds * self.sample_rate)
        return frames * self.channels * 3

    def to_dict(self, *, include_source_path: bool = False) -> dict[str, Any]:
        value: dict[str, Any] = {
            "source_bytes": self.source_bytes,
            "stream_index": self.stream_index,
            "container_names": list(self.container_names),
            "codec": self.codec,
            "sample_format": self.sample_format,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "channel_layout": self.channel_layout,
            "duration_seconds": self.duration_seconds,
            "format_start_time_seconds": self.format_start_time_seconds,
            "stream_start_time_seconds": self.stream_start_time_seconds,
            "stream_time_base": self.stream_time_base,
            "stream_start_pts": self.stream_start_pts,
            "stream_duration_ts": self.stream_duration_ts,
            "initial_padding_samples": self.initial_padding_samples,
            "trailing_padding_samples": self.trailing_padding_samples,
            "skip_samples": self.skip_samples,
            "discard_padding_samples": self.discard_padding_samples,
            "first_retained_source_sample": self.first_retained_source_sample,
            "decoder_padding_samples": self.decoder_padding_samples,
            "projected_pcm24_bytes": self.projected_pcm24_bytes,
            "format_policy": self.decision.to_dict(),
        }
        if include_source_path:
            value["source"] = str(self.source)
        return value


def resolve_executable(executable: str | Path) -> Path:
    """Resolve one caller-selected executable to an exact local file."""

    text = os.fspath(executable)
    if not text.strip():
        raise ValueError("decoder executable must not be empty")
    candidate = Path(text).expanduser()
    if candidate.parent == Path("."):
        found = shutil.which(text)
        if found is None:
            raise FileNotFoundError(f"decoder executable was not found: {text}")
        candidate = Path(found)
    candidate = candidate.absolute().resolve()
    if not candidate.is_file():
        raise FileNotFoundError(f"decoder executable is not a file: {candidate}")
    if not os.access(candidate, os.X_OK):
        raise PermissionError(f"decoder executable is not executable: {candidate}")
    return candidate


def decoder_capability_report(
    *,
    ffmpeg: str | Path,
    ffprobe: str | Path,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Return a read-only capability report for an explicit FFmpeg toolchain."""

    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be finite and positive")
    ffmpeg_path = resolve_executable(ffmpeg)
    ffprobe_path = resolve_executable(ffprobe)
    ffmpeg_version = _run_tool(
        ffmpeg_path, ("-version",), timeout_seconds=timeout_seconds
    )
    ffprobe_version = _run_tool(
        ffprobe_path, ("-version",), timeout_seconds=timeout_seconds
    )
    if not ffmpeg_version.casefold().startswith("ffmpeg version"):
        raise ValueError("selected ffmpeg executable did not identify as FFmpeg")
    if not ffprobe_version.casefold().startswith("ffprobe version"):
        raise ValueError("selected ffprobe executable did not identify as FFprobe")
    formats = _run_tool(
        ffmpeg_path,
        ("-hide_banner", "-formats"),
        timeout_seconds=timeout_seconds,
    )
    codecs = _run_tool(
        ffmpeg_path,
        ("-hide_banner", "-codecs"),
        timeout_seconds=timeout_seconds,
    )
    return {
        "schema": "sunofriend.audio-decoder-capability.v1",
        "read_only": True,
        "network_used": False,
        "ffmpeg": _tool_record(ffmpeg_path, ffmpeg_version),
        "ffprobe": _tool_record(ffprobe_path, ffprobe_version),
        "policy": {
            "portable_suffixes": sorted(PORTABLE_AUDIO_SUFFIXES),
            "conditional_suffixes": sorted(CONDITIONAL_AUDIO_SUFFIXES),
            "protocol_whitelist": ["file"],
            "pcm24_encoder_available": _codec_encoder_available(
                codecs, "pcm_s24le"
            ),
            "reported_formats_sha256": hashlib.sha256(
                formats.encode("utf-8")
            ).hexdigest(),
            "reported_codecs_sha256": hashlib.sha256(
                codecs.encode("utf-8")
            ).hexdigest(),
        },
    }


def probe_audio(
    source: str | Path,
    *,
    ffprobe: str | Path,
    limits: AudioImportLimits = DEFAULT_AUDIO_IMPORT_LIMITS,
    allow_conditional: bool = False,
) -> AudioProbe:
    """Inspect and validate exactly one local audio stream without writing."""

    source_path = validate_local_source_path(source, limits=limits)
    ffprobe_path = resolve_executable(ffprobe)
    arguments = (
        "-v",
        "error",
        "-protocol_whitelist",
        "file",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(source_path),
    )
    output = _run_tool(
        ffprobe_path,
        arguments,
        timeout_seconds=limits.probe_timeout_seconds,
    )
    try:
        document = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ValueError("ffprobe returned invalid JSON") from exc
    if not isinstance(document, Mapping):
        raise ValueError("ffprobe result must be a JSON object")
    streams = document.get("streams")
    if not isinstance(streams, list):
        raise ValueError("ffprobe did not report any streams")
    if any(not isinstance(row, Mapping) for row in streams):
        raise ValueError("ffprobe reported a malformed stream")
    non_audio_types = sorted(
        {
            str(row.get("codec_type") or "<unknown>").strip().casefold()
            for row in streams
            if row.get("codec_type") != "audio"
        }
    )
    if non_audio_types:
        raise ValueError(
            "source must contain audio only; non-audio streams are not "
            f"accepted: {', '.join(non_audio_types)}"
        )
    audio_streams = [
        row
        for row in streams
        if row.get("codec_type") == "audio"
    ]
    if len(audio_streams) != 1:
        raise ValueError(
            "source must contain exactly one audio stream; "
            f"ffprobe reported {len(audio_streams)}"
        )
    stream = audio_streams[0]
    format_row = document.get("format")
    if not isinstance(format_row, Mapping):
        format_row = {}
    if _looks_encrypted(stream, format_row):
        raise ValueError("encrypted or DRM-protected audio is not accepted")

    codec = _required_text(stream, "codec_name").casefold()
    raw_format_names = str(format_row.get("format_name") or "")
    container_names = tuple(
        sorted({item.strip().casefold() for item in raw_format_names.split(",") if item.strip()})
    )
    decision = classify_audio_format(
        source_path.suffix,
        container_names=container_names,
        codec=codec,
        allow_conditional=allow_conditional,
    )
    sample_rate = _positive_int(stream.get("sample_rate"), "sample_rate")
    channels = _positive_int(stream.get("channels"), "channels")
    if channels > limits.maximum_channels:
        raise ValueError(
            f"source has {channels} channels; maximum is {limits.maximum_channels}"
        )
    channel_layout = str(stream.get("channel_layout") or "").strip().casefold()
    if not channel_layout:
        if channels == 1:
            channel_layout = "mono"
        elif channels == 2:
            channel_layout = "stereo"
        else:
            raise ValueError(
                "multichannel source has no declared channel layout"
            )
    expected_channels = _CHANNEL_LAYOUT_CHANNELS.get(channel_layout)
    if expected_channels != channels:
        raise ValueError(
            "unsupported or inconsistent channel layout: "
            f"{channel_layout} with {channels} channels"
        )
    duration = _duration_seconds(stream, format_row)
    if duration > limits.maximum_duration_seconds:
        raise ValueError(
            f"source duration {duration:.3f}s exceeds "
            f"{limits.maximum_duration_seconds:.3f}s"
        )
    format_start_time = _optional_finite_float(
        format_row.get("start_time"), "format start_time"
    )
    stream_start_time = _optional_finite_float(
        stream.get("start_time"), "stream start_time"
    )

    side_data = stream.get("side_data_list")
    if not isinstance(side_data, list):
        side_data = []
    packet_skip_samples, packet_discard_padding = _probe_edge_packet_padding(
        source_path,
        ffprobe=ffprobe_path,
        duration_seconds=duration,
        start_time_seconds=(
            stream_start_time
            if stream_start_time is not None
            else format_start_time
        ),
        timeout_seconds=limits.probe_timeout_seconds,
    )
    skip_samples = max(
        _maximum_side_data_int(side_data, "skip_samples"),
        packet_skip_samples,
    )
    discard_padding = max(
        _maximum_side_data_int(side_data, "discard_padding"),
        packet_discard_padding,
    )
    probe = AudioProbe(
        source=source_path,
        source_bytes=source_path.stat().st_size,
        stream_index=_nonnegative_int(stream.get("index"), "stream index"),
        container_names=container_names,
        codec=codec,
        sample_format=_optional_text(stream.get("sample_fmt")),
        sample_rate=sample_rate,
        channels=channels,
        channel_layout=channel_layout,
        duration_seconds=duration,
        format_start_time_seconds=format_start_time,
        stream_start_time_seconds=stream_start_time,
        stream_time_base=_optional_text(stream.get("time_base")),
        stream_start_pts=_optional_int(stream.get("start_pts"), "stream start_pts"),
        stream_duration_ts=_optional_int(
            stream.get("duration_ts"), "stream duration_ts"
        ),
        initial_padding_samples=_nonnegative_int(
            stream.get("initial_padding", 0), "initial_padding"
        ),
        trailing_padding_samples=_nonnegative_int(
            stream.get("trailing_padding", 0), "trailing_padding"
        ),
        skip_samples=skip_samples,
        discard_padding_samples=discard_padding,
        decision=decision,
    )
    if probe.projected_pcm24_bytes > limits.maximum_canonical_bytes:
        raise ValueError(
            "projected canonical PCM24 asset exceeds "
            f"{limits.maximum_canonical_bytes} bytes"
        )
    return probe


def probe_stable_audio(
    source: str | Path,
    *,
    ffprobe: str | Path,
    limits: AudioImportLimits = DEFAULT_AUDIO_IMPORT_LIMITS,
    allow_conditional: bool = False,
) -> tuple[AudioProbe, str]:
    """Probe one file only when the same bytes exist before and afterwards."""

    source_path = validate_local_source_path(source, limits=limits)
    hash_before = file_sha256(source_path)
    probe = probe_audio(
        source_path,
        ffprobe=ffprobe,
        limits=limits,
        allow_conditional=allow_conditional,
    )
    hash_after = file_sha256(source_path)
    if hash_after != hash_before:
        raise ValueError(
            f"source audio changed while it was being probed: {source_path.name}"
        )
    if probe.source != source_path or probe.source_bytes != source_path.stat().st_size:
        raise ValueError(
            f"source audio identity changed while it was being probed: "
            f"{source_path.name}"
        )
    return probe, hash_after


def validate_local_source_path(
    source: str | Path,
    *,
    limits: AudioImportLimits = DEFAULT_AUDIO_IMPORT_LIMITS,
) -> Path:
    """Validate the local source boundary before invoking an external tool."""

    text = os.fspath(source)
    if "://" in text:
        raise ValueError("remote URLs are not accepted as local source audio")
    path = Path(text).expanduser().absolute()
    if path.is_symlink():
        raise ValueError(f"symbolic-link source audio is not accepted: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"source audio is not an existing file: {path}")
    path = path.resolve()
    size = path.stat().st_size
    if size <= 0:
        raise ValueError("source audio is empty")
    if size > limits.maximum_input_bytes:
        raise ValueError(
            f"source is {size} bytes; maximum is {limits.maximum_input_bytes}"
        )
    suffix = path.suffix.casefold()
    if suffix not in KNOWN_AUDIO_SUFFIXES:
        supported = ", ".join(sorted(KNOWN_AUDIO_SUFFIXES))
        raise ValueError(
            f"unsupported audio filename suffix {suffix or '<none>'}; "
            f"known suffixes: {supported}"
        )
    return path


def classify_audio_format(
    suffix: str,
    *,
    container_names: Sequence[str],
    codec: str,
    allow_conditional: bool = False,
) -> AudioFormatDecision:
    """Validate a filename, reported container and codec as one combination."""

    normalized_suffix = suffix.casefold()
    names = {str(item).strip().casefold() for item in container_names}
    normalized_codec = codec.casefold()
    conditional = normalized_suffix in CONDITIONAL_AUDIO_SUFFIXES
    if conditional and not allow_conditional:
        raise ValueError(
            f"{normalized_suffix} is a conditional format; enable it only "
            "after this exact decoder build has been approved"
        )

    accepted = False
    policy_name = ""
    lossless = False
    container = ""
    if normalized_suffix in {".wav", ".wave"}:
        accepted = "wav" in names and normalized_codec in _PCM_WAV_CODECS
        policy_name, lossless, container = "wav-integer-pcm", True, "wav"
    elif normalized_suffix in {".aif", ".aiff"}:
        accepted = "aiff" in names and normalized_codec in _PCM_AIFF_CODECS
        policy_name, lossless, container = "aiff-integer-pcm", True, "aiff"
    elif normalized_suffix == ".flac":
        accepted = "flac" in names and normalized_codec == "flac"
        policy_name, lossless, container = "flac", True, "flac"
    elif normalized_suffix == ".mp3":
        accepted = "mp3" in names and normalized_codec == "mp3"
        policy_name, lossless, container = "mp3", False, "mp3"
    elif normalized_suffix == ".m4a":
        accepted = bool(names & _M4A_CONTAINERS) and normalized_codec in {
            "aac",
            "alac",
        }
        policy_name = f"m4a-{normalized_codec}"
        lossless, container = normalized_codec == "alac", "m4a"
    elif normalized_suffix in {".ogg", ".oga", ".opus"}:
        accepted = "ogg" in names and normalized_codec in {"vorbis", "opus"}
        if normalized_suffix == ".opus":
            accepted = accepted and normalized_codec == "opus"
        policy_name = f"ogg-{normalized_codec}"
        lossless, container = False, "ogg"
    elif normalized_suffix == ".aifc":
        accepted = (
            bool(names & {"aiff", "aifc"})
            and normalized_codec in (_PCM_AIFF_CODECS | {"fl32", "fl64"})
        )
        policy_name, lossless, container = "conditional-aifc", True, "aifc"
    elif normalized_suffix == ".caf":
        accepted = "caf" in names and normalized_codec in (
            _PCM_WAV_CODECS | _PCM_AIFF_CODECS | {"alac", "aac"}
        )
        policy_name = f"conditional-caf-{normalized_codec}"
        lossless, container = normalized_codec != "aac", "caf"
    elif normalized_suffix == ".wma":
        accepted = bool(names & {"asf", "wma"}) and normalized_codec in _WMA_CODECS
        policy_name = f"conditional-wma-{normalized_codec}"
        lossless, container = normalized_codec == "wmalossless", "wma"

    if not accepted:
        reported = ",".join(sorted(names)) or "<unknown>"
        raise ValueError(
            "filename/container/codec combination is not in the tested policy: "
            f"{normalized_suffix or '<none>'}, {reported}, {normalized_codec}"
        )
    return AudioFormatDecision(
        policy_name=policy_name,
        container=container,
        codec=normalized_codec,
        lossless=lossless,
        conditional=conditional,
    )


def decode_timeout_seconds(
    duration_seconds: float,
    *,
    limits: AudioImportLimits = DEFAULT_AUDIO_IMPORT_LIMITS,
) -> float:
    """Return the bounded decode timeout recorded in the import plan."""

    candidate = max(
        limits.minimum_decode_timeout_seconds,
        duration_seconds * limits.decode_duration_multiplier,
    )
    return min(candidate, limits.maximum_decode_timeout_seconds)


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _codec_encoder_available(codecs_output: str, codec_name: str) -> bool:
    """Return whether one exact ``ffmpeg -codecs`` row has encoder support."""

    for line in codecs_output.splitlines():
        columns = line.split()
        if len(columns) < 2:
            continue
        flags, reported_name = columns[:2]
        if (
            len(flags) == 6
            and reported_name == codec_name
            and flags[1] == "E"
        ):
            return True
    return False


def _probe_edge_packet_padding(
    source: Path,
    *,
    ffprobe: Path,
    duration_seconds: float,
    start_time_seconds: float | None,
    timeout_seconds: float,
) -> tuple[int, int]:
    """Read bounded packet windows that expose AAC/MP3 priming metadata."""

    timeline_start = max(0.0, start_time_seconds or 0.0)
    tail_start = max(timeline_start, timeline_start + duration_seconds - 1.0)
    intervals = ("%+#1", f"{tail_start:.6f}%+2.000000")
    side_data: list[Any] = []
    for interval in intervals:
        output = _run_tool(
            ffprobe,
            (
                "-v",
                "error",
                "-protocol_whitelist",
                "file",
                "-select_streams",
                "a:0",
                "-read_intervals",
                interval,
                "-show_packets",
                "-show_entries",
                "packet=side_data_list",
                "-of",
                "json",
                str(source),
            ),
            timeout_seconds=timeout_seconds,
        )
        try:
            document = json.loads(output)
        except json.JSONDecodeError as exc:
            raise ValueError("ffprobe packet probe returned invalid JSON") from exc
        if not isinstance(document, Mapping):
            raise ValueError("ffprobe packet probe must be a JSON object")
        packets = document.get("packets", [])
        if not isinstance(packets, list):
            raise ValueError("ffprobe packet probe returned malformed packets")
        for packet in packets:
            if not isinstance(packet, Mapping):
                raise ValueError("ffprobe packet probe returned a malformed packet")
            rows = packet.get("side_data_list", [])
            if not isinstance(rows, list):
                raise ValueError(
                    "ffprobe packet probe returned malformed side data"
                )
            side_data.extend(rows)
    return (
        _maximum_side_data_int(side_data, "skip_samples"),
        _maximum_side_data_int(side_data, "discard_padding"),
    )


def _run_tool(
    executable: Path,
    arguments: Sequence[str],
    *,
    timeout_seconds: float,
) -> str:
    environment = dict(os.environ)
    environment.update({"LANG": "C", "LC_ALL": "C"})
    try:
        completed = subprocess.run(
            [str(executable), *arguments],
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
            f"{executable.name} exceeded the {timeout_seconds:.1f}s limit"
        ) from exc
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        if len(detail) > 1000:
            detail = detail[:1000] + "..."
        raise RuntimeError(
            f"{executable.name} failed with exit code {completed.returncode}: "
            f"{detail or 'no diagnostic output'}"
        )
    return completed.stdout


def _tool_record(path: Path, version_output: str) -> dict[str, Any]:
    lines = version_output.splitlines()
    first_line = lines[0] if lines else ""
    configuration = next(
        (
            line.partition(":")[2].strip()
            for line in lines
            if line.casefold().startswith("configuration:")
        ),
        None,
    )
    lowered = (configuration or "").casefold()
    license_profile = (
        "nonfree"
        if "--enable-nonfree" in lowered
        else "gpl"
        if "--enable-gpl" in lowered
        else "lgpl-default"
    )
    return {
        "path": str(path),
        "sha256": file_sha256(path),
        "version": first_line,
        "build_configuration": configuration,
        "license_profile_from_build_flags": license_profile,
        "version_output": lines,
        "version_output_sha256": hashlib.sha256(
            version_output.encode("utf-8")
        ).hexdigest(),
    }


def _required_text(row: Mapping[str, Any], key: str) -> str:
    value = str(row.get(key) or "").strip()
    if not value:
        raise ValueError(f"ffprobe audio stream has no {key}")
    return value


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _positive_int(value: Any, label: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"ffprobe {label} is not an integer") from exc
    if parsed <= 0:
        raise ValueError(f"ffprobe {label} must be positive")
    return parsed


def _nonnegative_int(value: Any, label: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"ffprobe {label} is not an integer") from exc
    if parsed < 0:
        raise ValueError(f"ffprobe {label} must not be negative")
    return parsed


def _optional_int(value: Any, label: str) -> int | None:
    if value in {None, "", "N/A"}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"ffprobe {label} is not an integer") from exc


def _optional_finite_float(value: Any, label: str) -> float | None:
    if value in {None, "", "N/A"}:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"ffprobe {label} is not numeric") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"ffprobe {label} must be finite")
    return parsed


def _duration_seconds(
    stream: Mapping[str, Any], format_row: Mapping[str, Any]
) -> float:
    value = stream.get("duration")
    if value in {None, "", "N/A"}:
        value = format_row.get("duration")
    duration = _optional_finite_float(value, "duration")
    if duration is None or duration <= 0:
        raise ValueError("ffprobe duration must be finite and positive")
    return duration


def _maximum_side_data_int(rows: Sequence[Any], key: str) -> int:
    values = []
    for row in rows:
        if isinstance(row, Mapping) and row.get(key) not in {None, "", "N/A"}:
            values.append(_nonnegative_int(row[key], key))
    return max(values, default=0)


def _looks_encrypted(
    stream: Mapping[str, Any], format_row: Mapping[str, Any]
) -> bool:
    codec_tag = str(stream.get("codec_tag_string") or "").casefold()
    if codec_tag in {"enca", "drms"}:
        return True
    for row in (stream, format_row):
        encrypted = row.get("is_encrypted")
        if encrypted not in {None, False, 0, "0", "false", "False"}:
            return True
    side_data = stream.get("side_data_list")
    if isinstance(side_data, list):
        return any(
            "encrypt" in str(row.get("side_data_type") or "").casefold()
            for row in side_data
            if isinstance(row, Mapping)
        )
    return False


__all__ = [
    "AudioFormatDecision",
    "AudioImportLimits",
    "AudioProbe",
    "CONDITIONAL_AUDIO_SUFFIXES",
    "DEFAULT_AUDIO_IMPORT_LIMITS",
    "KNOWN_AUDIO_SUFFIXES",
    "PORTABLE_AUDIO_SUFFIXES",
    "classify_audio_format",
    "decode_timeout_seconds",
    "decoder_capability_report",
    "file_sha256",
    "probe_audio",
    "probe_stable_audio",
    "resolve_executable",
    "validate_local_source_path",
]
