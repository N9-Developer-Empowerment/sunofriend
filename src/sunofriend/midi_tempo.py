"""Tempo-only speed changes for complete Standard MIDI Files.

Unlike the Clip v1 importer/exporter, this module does not rebuild MIDI from
notes.  It patches only ``Set Tempo`` meta-event payloads, preserving every
track, tick, channel event, controller, pitch bend, SysEx message and unrelated
meta event byte-for-byte.  This is the correct operation when a complete song
should keep the same bars and groove but play faster or slower.
"""

from __future__ import annotations

import math
import os
import re
import struct
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path


MICROSECONDS_PER_MINUTE = 60_000_000.0
MAX_TEMPO_MICROSECONDS = 0xFFFFFF
SOURCE_BPM_TOLERANCE = 0.05
MIDI_SUFFIXES = {".mid", ".midi"}


@dataclass(frozen=True)
class MidiTempoChange:
    """Auditable result of retiming one MIDI payload."""

    source_bpm: float
    target_bpm: float
    embedded_target_bpm: float
    speed_ratio: float
    duration_ratio: float
    tempo_events_changed: int
    tempo_event_inserted: bool
    midi_format: int
    ticks_per_beat: int
    track_count: int


@dataclass(frozen=True)
class MidiTempoFileResult:
    """Input/output paths plus the musical change made to one file."""

    input_path: Path
    output_path: Path
    change: MidiTempoChange

    def to_dict(self) -> dict:
        value = asdict(self.change)
        value["input"] = str(self.input_path)
        value["output"] = str(self.output_path)
        return value


@dataclass(frozen=True)
class _TempoEvent:
    track_index: int
    tick: int
    payload_offset: int
    microseconds_per_quarter: int

    @property
    def bpm(self) -> float:
        return MICROSECONDS_PER_MINUTE / self.microseconds_per_quarter


@dataclass(frozen=True)
class _TrackChunk:
    header_offset: int
    data_offset: int
    length: int


@dataclass(frozen=True)
class _MidiLayout:
    midi_format: int
    ticks_per_beat: int
    tracks: tuple[_TrackChunk, ...]
    tempo_events: tuple[_TempoEvent, ...]


def retime_midi_bytes(
    data: bytes,
    *,
    target_bpm: float,
    source_bpm: float | None = None,
    source_tolerance_bpm: float = SOURCE_BPM_TOLERANCE,
) -> tuple[bytes, MidiTempoChange]:
    """Change MIDI playback speed while keeping every event at the same tick.

    When a tick-zero tempo is present, ``source_bpm`` is optional and otherwise
    acts as a safety check.  Without one, an explicit source BPM describes the
    DAW/project tempo; otherwise the Standard MIDI File default of 120 BPM is
    used.  The target is inserted at tick zero and later tempo-map events are
    scaled proportionally so rubato is retained.
    """

    raw = bytes(data)
    target = _validated_bpm(target_bpm, "target_bpm", require_encodable=True)
    source = (
        None
        if source_bpm is None
        else _validated_bpm(source_bpm, "source_bpm", require_encodable=False)
    )
    tolerance = float(source_tolerance_bpm)
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("source_tolerance_bpm must be a finite non-negative number")

    layout = _scan_midi(raw)
    tick_zero = sorted(
        (event for event in layout.tempo_events if event.tick == 0),
        key=lambda event: (event.track_index, event.payload_offset),
    )
    inserted = False
    if tick_zero:
        detected = tick_zero[0].bpm
        if any(
            event.microseconds_per_quarter
            != tick_zero[0].microseconds_per_quarter
            for event in tick_zero[1:]
        ):
            values = ", ".join(f"{event.bpm:.6g}" for event in tick_zero)
            raise ValueError(f"MIDI has conflicting tick-zero tempos: {values} BPM")
        if source is not None and abs(source - detected) > tolerance:
            raise ValueError(
                f"embedded source tempo is {detected:.6g} BPM, not "
                f"the requested {source:.6g} BPM"
            )
        effective_source = source if source is not None else detected
    else:
        # SMF defines an implicit 120 BPM before the first Set Tempo event.
        # An explicit source value deliberately overrides that standalone
        # default for MIDI whose timing came from an external DAW project.
        effective_source = 120.0 if source is None else source
        inserted = True

    speed_ratio = target / effective_source
    target_microseconds = _bpm_to_microseconds(target)
    output = bytearray(raw)
    for event in layout.tempo_events:
        microseconds = (
            target_microseconds
            if event.tick == 0
            else int(round(event.microseconds_per_quarter / speed_ratio))
        )
        _validate_tempo_microseconds(microseconds, target)
        start = event.payload_offset
        output[start : start + 3] = microseconds.to_bytes(3, "big")

    if inserted:
        output = bytearray(
            _insert_tick_zero_tempo(bytes(output), layout.tracks[0], target_microseconds)
        )

    change = MidiTempoChange(
        source_bpm=effective_source,
        target_bpm=target,
        embedded_target_bpm=MICROSECONDS_PER_MINUTE / target_microseconds,
        speed_ratio=speed_ratio,
        duration_ratio=effective_source / target,
        tempo_events_changed=len(layout.tempo_events),
        tempo_event_inserted=inserted,
        midi_format=layout.midi_format,
        ticks_per_beat=layout.ticks_per_beat,
        track_count=len(layout.tracks),
    )
    return bytes(output), change


def retime_midi_path(
    input_path: str | Path,
    *,
    target_bpm: float,
    source_bpm: float | None = None,
    output_path: str | Path | None = None,
    overwrite: bool = False,
) -> list[MidiTempoFileResult]:
    """Retime one MIDI file or every MIDI file under a directory.

    Directory processing is recursive and preserves relative paths.  Every
    input is parsed and every destination collision is checked before the first
    output is written, so validation failures cannot leave a partial batch.
    """

    source = Path(input_path)
    if not source.exists():
        raise ValueError(f"input does not exist: {source}")

    if source.is_file():
        if source.suffix.lower() not in MIDI_SUFFIXES:
            raise ValueError("file input must end in .mid or .midi")
        output = (
            Path(output_path)
            if output_path is not None
            else source.with_name(
                f"{_replace_bpm_suffix(source.stem, target_bpm)}{source.suffix}"
            )
        )
        if output.exists() and output.is_dir():
            raise ValueError("a file input requires a MIDI file output path")
        pairs = [(source, output)]
    elif source.is_dir():
        default_source = (
            source.resolve() if source.name in {"", ".", ".."} else source
        )
        output = (
            Path(output_path)
            if output_path is not None
            else default_source.with_name(
                _replace_bpm_suffix(default_source.name, target_bpm)
            )
        )
        if output.exists() and not output.is_dir():
            raise ValueError("a directory input requires a directory output path")
        source_resolved = source.resolve()
        output_resolved = output.resolve()
        if output_resolved == source_resolved or source_resolved in output_resolved.parents:
            raise ValueError("output directory must not be the input directory or inside it")
        inputs = sorted(
            (
                path
                for path in source.rglob("*")
                if path.is_file() and path.suffix.lower() in MIDI_SUFFIXES
            ),
            key=lambda path: str(path.relative_to(source)).casefold(),
        )
        if not inputs:
            raise ValueError(f"no .mid or .midi files found under: {source}")
        pairs = [(path, output / path.relative_to(source)) for path in inputs]
    else:
        raise ValueError(f"input must be a MIDI file or directory: {source}")

    output_root = output if source.is_dir() else output.parent
    output_root_resolved = output_root.resolve()
    resolved_outputs: dict[Path, Path] = {}
    for input_file, output_file in pairs:
        resolved_output = output_file.resolve()
        if input_file.resolve() == resolved_output:
            raise ValueError(f"input and output must be different: {input_file}")
        if resolved_output in resolved_outputs:
            raise ValueError(
                "multiple inputs resolve to the same output: "
                f"{resolved_outputs[resolved_output]} and {output_file}"
            )
        resolved_outputs[resolved_output] = output_file
        if output_file.is_symlink():
            raise ValueError(f"output must not be a symbolic link: {output_file}")
        if output_file.exists() and output_file.is_dir():
            raise ValueError(f"output MIDI path is a directory: {output_file}")
        if output_file.exists() and not overwrite:
            raise ValueError(
                f"output already exists: {output_file} (use --overwrite to replace it)"
            )
        if source.is_dir() and not _path_is_within(
            resolved_output, output_root_resolved
        ):
            raise ValueError(
                f"output path escapes the selected output directory: {output_file}"
            )
        _validate_output_parents(output_file.parent, stop=output_root)

    prepared: list[tuple[Path, Path, bytes, MidiTempoChange]] = []
    for input_file, output_file in pairs:
        transformed, change = retime_midi_bytes(
            input_file.read_bytes(),
            target_bpm=target_bpm,
            source_bpm=source_bpm,
        )
        prepared.append((input_file, output_file, transformed, change))

    if source_bpm is None and prepared:
        expected = prepared[0][3].source_bpm
        mismatches = [
            item
            for item in prepared[1:]
            if abs(item[3].source_bpm - expected) > SOURCE_BPM_TOLERANCE
        ]
        if mismatches:
            details = ", ".join(
                f"{item[0]}={item[3].source_bpm:.6g}" for item in mismatches[:3]
            )
            raise ValueError(
                f"batch contains mixed source tempos; expected {expected:.6g} BPM, "
                f"found {details}"
            )

    # Create the complete directory tree before writing any MIDI.  This keeps a
    # blocked nested path from causing a partial batch after earlier files have
    # already been published.
    for parent in sorted(
        {output_file.parent for _, output_file, _, _ in prepared},
        key=lambda path: (len(path.parts), str(path)),
    ):
        parent.mkdir(parents=True, exist_ok=True)

    results = []
    for input_file, output_file, transformed, change in prepared:
        _write_bytes_atomic(output_file, transformed)
        results.append(MidiTempoFileResult(input_file, output_file, change))
    return results


def _scan_midi(data: bytes) -> _MidiLayout:
    if len(data) < 14 or data[:4] != b"MThd":
        raise ValueError("not a Standard MIDI File")
    header_length = struct.unpack(">I", data[4:8])[0]
    if header_length < 6 or len(data) < 8 + header_length:
        raise ValueError("invalid or truncated MIDI header")
    midi_format, track_count, division = struct.unpack(">HHH", data[8:14])
    if midi_format not in {0, 1}:
        raise ValueError("only Standard MIDI File format 0 and 1 are supported")
    if track_count < 1:
        raise ValueError("MIDI file contains no tracks")
    if division & 0x8000:
        raise ValueError("SMPTE-time MIDI cannot be retimed with tempo events")
    if division == 0:
        raise ValueError("MIDI ticks per beat must be greater than zero")

    position = 8 + header_length
    tracks: list[_TrackChunk] = []
    tempo_events: list[_TempoEvent] = []
    for track_index in range(track_count):
        if position + 8 > len(data) or data[position : position + 4] != b"MTrk":
            raise ValueError(f"missing or truncated MIDI track {track_index}")
        length = struct.unpack(">I", data[position + 4 : position + 8])[0]
        data_offset = position + 8
        end = data_offset + length
        if end > len(data):
            raise ValueError(f"truncated MIDI track {track_index}")
        track = _TrackChunk(position, data_offset, length)
        tracks.append(track)
        tempo_events.extend(
            _scan_track(data[data_offset:end], data_offset, track_index)
        )
        position = end

    return _MidiLayout(
        midi_format,
        division,
        tuple(tracks),
        tuple(tempo_events),
    )


def _scan_track(data: bytes, base_offset: int, track_index: int) -> list[_TempoEvent]:
    position = 0
    tick = 0
    running_status: int | None = None
    result: list[_TempoEvent] = []
    while position < len(data):
        delta, position = _read_varlen(data, position)
        tick += delta
        if position >= len(data):
            raise ValueError(f"truncated event in MIDI track {track_index}")

        status_byte = data[position]
        if status_byte & 0x80:
            status = status_byte
            position += 1
            if status < 0xF0:
                running_status = status
        else:
            if running_status is None:
                raise ValueError(
                    f"running status used before a status byte in MIDI track {track_index}"
                )
            status = running_status

        if status == 0xFF:
            running_status = None
            if position >= len(data):
                raise ValueError(f"truncated meta event in MIDI track {track_index}")
            kind = data[position]
            position += 1
            length, position = _read_varlen(data, position)
            payload_offset = position
            end = position + length
            if end > len(data):
                raise ValueError(f"truncated meta payload in MIDI track {track_index}")
            if kind == 0x51:
                if length != 3:
                    raise ValueError("Set Tempo meta event must contain exactly three bytes")
                microseconds = int.from_bytes(data[position:end], "big")
                if microseconds == 0:
                    raise ValueError("Set Tempo meta event cannot be zero")
                result.append(
                    _TempoEvent(
                        track_index,
                        tick,
                        base_offset + payload_offset,
                        microseconds,
                    )
                )
            position = end
            if kind == 0x2F:
                break
            continue

        if status in {0xF0, 0xF7}:
            running_status = None
            length, position = _read_varlen(data, position)
            position += length
            if position > len(data):
                raise ValueError(f"truncated SysEx event in MIDI track {track_index}")
            continue

        if status >= 0xF0:
            lengths = {
                0xF1: 1,
                0xF2: 2,
                0xF3: 1,
                0xF6: 0,
                0xF8: 0,
                0xFA: 0,
                0xFB: 0,
                0xFC: 0,
                0xFE: 0,
            }
            if status not in lengths:
                raise ValueError(f"unsupported MIDI system event 0x{status:02x}")
            if status < 0xF8:
                running_status = None
            position += lengths[status]
            if position > len(data):
                raise ValueError(f"truncated system event in MIDI track {track_index}")
            continue

        event_type = status & 0xF0
        if event_type not in {0x80, 0x90, 0xA0, 0xB0, 0xC0, 0xD0, 0xE0}:
            raise ValueError(f"unsupported channel event 0x{status:02x}")
        length = 1 if event_type in {0xC0, 0xD0} else 2
        end = position + length
        if end > len(data):
            raise ValueError(f"truncated channel event in MIDI track {track_index}")
        if any(byte & 0x80 for byte in data[position:end]):
            raise ValueError(f"invalid channel-event data in MIDI track {track_index}")
        position = end
    return result


def _insert_tick_zero_tempo(
    data: bytes,
    first_track: _TrackChunk,
    microseconds_per_quarter: int,
) -> bytes:
    event = b"\x00\xff\x51\x03" + microseconds_per_quarter.to_bytes(3, "big")
    new_length = first_track.length + len(event)
    if new_length > 0xFFFFFFFF:
        raise ValueError("MIDI track is too large to insert a tempo event")
    output = bytearray(data)
    length_offset = first_track.header_offset + 4
    output[length_offset : length_offset + 4] = struct.pack(">I", new_length)
    return bytes(
        output[: first_track.data_offset]
        + event
        + output[first_track.data_offset :]
    )


def _read_varlen(data: bytes, position: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if position >= len(data):
            raise ValueError("truncated MIDI variable-length value")
        byte = data[position]
        position += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, position
    raise ValueError("MIDI variable-length value is too long")


def _validated_bpm(value: float, label: str, *, require_encodable: bool) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number greater than zero")
    try:
        bpm = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number greater than zero") from exc
    if not math.isfinite(bpm) or bpm <= 0:
        raise ValueError(f"{label} must be a finite number greater than zero")
    if require_encodable:
        _bpm_to_microseconds(bpm)
    return bpm


def _bpm_to_microseconds(bpm: float) -> int:
    microseconds = int(round(MICROSECONDS_PER_MINUTE / float(bpm)))
    _validate_tempo_microseconds(microseconds, bpm)
    return microseconds


def _validate_tempo_microseconds(microseconds: int, bpm: float) -> None:
    if not 1 <= microseconds <= MAX_TEMPO_MICROSECONDS:
        raise ValueError(
            f"BPM {bpm:.6g} cannot be represented by a three-byte MIDI tempo event"
        )


def _bpm_token(value: float) -> str:
    bpm = _validated_bpm(value, "target_bpm", require_encodable=True)
    return f"{bpm:.6f}".rstrip("0").rstrip(".")


def _replace_bpm_suffix(value: str, target_bpm: float) -> str:
    suffix = f"-{_bpm_token(target_bpm)}bpm"
    match = re.search(r"(?i)[-_ ]?\d+(?:\.\d+)?bpm$", value)
    if match is None:
        return f"{value}{suffix}"
    prefix = value[: match.start()]
    return f"{prefix or 'midi'}{suffix}"


def _path_is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _validate_output_parents(parent: Path, *, stop: Path) -> None:
    current = parent
    while True:
        if current.is_symlink():
            raise ValueError(f"output parent must not be a symbolic link: {current}")
        if current.exists() and not current.is_dir():
            raise ValueError(f"output parent is not a directory: {current}")
        if current == stop:
            return
        if stop not in current.parents:
            raise ValueError(f"output path is not under the selected output: {parent}")
        current = current.parent


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = [
    "MidiTempoChange",
    "MidiTempoFileResult",
    "retime_midi_bytes",
    "retime_midi_path",
]
