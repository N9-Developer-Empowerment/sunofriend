"""Loss-preserving transformations for complete Standard MIDI Files.

The higher-level Clip API deliberately rebuilds MIDI from musical notes.  This
module has a different contract: retain the original SMF byte stream and patch
only the data bytes that the caller explicitly asks to change.  Transposition
therefore leaves ticks, velocities, channels, controllers, programs, metadata,
SysEx and running-status encoding untouched.  Tempo changes delegate to the
raw tempo transformer, which likewise leaves event ticks unchanged.

Concert-pitch cleanup is intentionally conservative.  It removes only the
exact, zero-delta RPN-0 pitch-bend setup written by :mod:`sunofriend.midi`, and
only when that channel has no other pitch-wheel events.  Ambiguous expressive
pitch-bend material is never silently discarded.
"""

from __future__ import annotations

import math
import operator
import os
import struct
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from .midi_codec import (
    MidiEvent as _CodecMidiEvent,
    MidiTrack as _CodecMidiTrack,
    _inspect_midi_header_structure,
    _parse_midi_structure,
)
from .midi_tempo import MidiTempoChange, retime_midi_bytes


MIDI_SUFFIXES = {".mid", ".midi"}
DRUM_CHANNEL = 9


@dataclass(frozen=True)
class TuningRemoval:
    """One safely recognised constant source-tuning setup."""

    track_index: int
    channel: int
    tick: int
    bend_value: int
    bend_range_semitones: int
    tuning_cents: float
    events_removed: int = 7


@dataclass(frozen=True)
class MidiTransformChange:
    """Auditable description of a raw-SMF transformation."""

    semitones: int
    note_events_transposed: int
    drum_note_events_preserved: int
    tempo_change: MidiTempoChange | None
    tuning_removals: tuple[TuningRemoval, ...]
    midi_format: int
    ticks_per_beat: int
    track_count: int

    @property
    def tuning_setups_removed(self) -> int:
        return len(self.tuning_removals)

    @property
    def tuning_events_removed(self) -> int:
        return sum(item.events_removed for item in self.tuning_removals)


@dataclass(frozen=True)
class MidiTransformFileResult:
    """Input/output paths and the transformation applied to one MIDI file."""

    input_path: Path
    output_path: Path
    change: MidiTransformChange

    def to_dict(self) -> dict:
        value = asdict(self.change)
        value["tuning_setups_removed"] = self.change.tuning_setups_removed
        value["tuning_events_removed"] = self.change.tuning_events_removed
        value["input"] = str(self.input_path)
        value["output"] = str(self.output_path)
        return value


@dataclass(frozen=True)
class _TransformPathPlan:
    pairs: tuple[tuple[Path, Path], ...]
    output_root: Path


@dataclass(frozen=True)
class _TransformOptions:
    semitones: int
    target_bpm: float | None
    source_bpm: float | None
    concert_pitch: bool
    max_tuning_cents: float


@dataclass(frozen=True)
class _PreparedTransform:
    input_path: Path
    output_path: Path
    payload: bytes
    change: MidiTransformChange


@dataclass(frozen=True)
class _Event:
    track_index: int
    tick: int
    delta: int
    raw_start: int
    raw_end: int
    status: int
    explicit_status: bool
    category: str
    data_offsets: tuple[int, ...] = ()
    data: tuple[int, ...] = ()

    @property
    def event_type(self) -> int:
        return self.status & 0xF0

    @property
    def channel(self) -> int | None:
        return self.status & 0x0F if self.category == "channel" else None


@dataclass(frozen=True)
class _Track:
    index: int
    header_offset: int
    data_offset: int
    length: int
    events: tuple[_Event, ...]


@dataclass(frozen=True)
class _Layout:
    midi_format: int
    ticks_per_beat: int
    tracks: tuple[_Track, ...]


@dataclass(frozen=True)
class _TuningCandidate:
    removal: TuningRemoval
    events: tuple[_Event, ...]
    safe_to_splice: bool


def transform_midi_bytes(
    data: bytes,
    *,
    semitones: int = 0,
    target_bpm: float | None = None,
    source_bpm: float | None = None,
    concert_pitch: bool = False,
    max_tuning_cents: float = 100.0,
) -> tuple[bytes, MidiTransformChange]:
    """Transform a complete SMF without rebuilding its musical events.

    ``semitones`` changes note-on and note-off pitch bytes on every channel
    except General MIDI drum channel 10 (zero-based channel 9).  The operation
    rejects the whole file rather than clipping a note outside ``0..127``.

    ``target_bpm`` changes Set Tempo payloads while retaining every event tick,
    so bars, groove and controller automation speed up or slow down together.
    ``source_bpm`` is an optional safety check and is valid only with a target.

    ``concert_pitch`` removes a Sunofriend-style constant tuning bend and its
    RPN-0 bend-range setup.  Cleanup is performed only for a complete seven-
    event setup with zero deltas and no other pitch-wheel event on that channel.
    An otherwise recognisable but unsafe setup raises ``ValueError``.
    """

    raw = bytes(data)
    shift = _validated_semitones(semitones)
    if not isinstance(concert_pitch, bool):
        raise ValueError("concert_pitch must be true or false")
    tuning_limit = _validated_tuning_limit(max_tuning_cents)
    if target_bpm is None and source_bpm is not None:
        raise ValueError("source_bpm requires target_bpm")

    layout = _parse_midi(raw)
    output = bytearray(raw)
    transposed = 0
    drums_preserved = 0

    note_events = [
        event
        for track in layout.tracks
        for event in track.events
        if event.category == "channel" and event.event_type in {0x80, 0x90}
    ]
    if shift:
        invalid = []
        for event in note_events:
            if event.channel == DRUM_CHANNEL:
                continue
            pitch = event.data[0]
            shifted = pitch + shift
            if not 0 <= shifted <= 127:
                invalid.append((event, pitch, shifted))
        if invalid:
            event, pitch, shifted = invalid[0]
            raise ValueError(
                "transposition places a note outside MIDI 0..127: "
                f"track={event.track_index}, tick={event.tick}, "
                f"channel={event.channel + 1}, pitch={pitch}, result={shifted}"
            )

        for event in note_events:
            if event.channel == DRUM_CHANNEL:
                drums_preserved += 1
                continue
            output[event.data_offsets[0]] = event.data[0] + shift
            transposed += 1

    tuning_removals: tuple[TuningRemoval, ...] = ()
    if concert_pitch:
        candidates = _find_tuning_candidates(layout, tuning_limit)
        _validate_tuning_candidates(layout, candidates)
        if candidates:
            output = _remove_event_ranges(output, layout, candidates)
            tuning_removals = tuple(candidate.removal for candidate in candidates)

    tempo_change = None
    transformed = bytes(output)
    if target_bpm is not None:
        transformed, tempo_change = retime_midi_bytes(
            transformed,
            target_bpm=target_bpm,
            source_bpm=source_bpm,
        )

    return transformed, MidiTransformChange(
        semitones=shift,
        note_events_transposed=transposed,
        drum_note_events_preserved=drums_preserved,
        tempo_change=tempo_change,
        tuning_removals=tuning_removals,
        midi_format=layout.midi_format,
        ticks_per_beat=layout.ticks_per_beat,
        track_count=len(layout.tracks),
    )


def transform_midi_file(
    input_path: str | Path,
    output_path: str | Path,
    *,
    semitones: int = 0,
    target_bpm: float | None = None,
    source_bpm: float | None = None,
    concert_pitch: bool = False,
    max_tuning_cents: float = 100.0,
    overwrite: bool = False,
) -> MidiTransformFileResult:
    """Transform one MIDI file and publish it atomically."""

    source = Path(input_path)
    if not source.is_file():
        raise ValueError("transform_midi_file requires a MIDI file input")
    results = transform_midi_path(
        source,
        output_path,
        semitones=semitones,
        target_bpm=target_bpm,
        source_bpm=source_bpm,
        concert_pitch=concert_pitch,
        max_tuning_cents=max_tuning_cents,
        overwrite=overwrite,
    )
    return results[0]


def transform_midi_path(
    input_path: str | Path,
    output_path: str | Path,
    *,
    semitones: int = 0,
    target_bpm: float | None = None,
    source_bpm: float | None = None,
    concert_pitch: bool = False,
    max_tuning_cents: float = 100.0,
    overwrite: bool = False,
) -> list[MidiTransformFileResult]:
    """Transform one MIDI or a recursive MIDI tree into a separate target.

    Directory processing preserves relative paths and ignores non-MIDI files.
    Every input is transformed and every collision is checked before the first
    destination is written, preventing a late validation error from publishing
    a partial batch.
    """

    plan = _plan_transform_paths(Path(input_path), Path(output_path))
    _preflight_transform_destinations(plan, overwrite=overwrite)
    prepared = _prepare_transforms(
        plan.pairs,
        _TransformOptions(
            semitones,
            target_bpm,
            source_bpm,
            concert_pitch,
            max_tuning_cents,
        ),
    )
    return _publish_prepared_transforms(prepared)


def _plan_transform_paths(source: Path, destination: Path) -> _TransformPathPlan:
    if not source.exists():
        raise ValueError(f"input does not exist: {source}")
    if source.is_file():
        return _plan_file_transform(source, destination)
    if source.is_dir():
        return _plan_directory_transform(source, destination)
    raise ValueError(f"input must be a MIDI file or directory: {source}")


def _plan_file_transform(source: Path, destination: Path) -> _TransformPathPlan:
    if source.suffix.lower() not in MIDI_SUFFIXES:
        raise ValueError("file input must end in .mid or .midi")
    if destination.exists() and destination.is_dir():
        raise ValueError("a file input requires a MIDI file output path")
    return _TransformPathPlan(((source, destination),), destination.parent)


def _plan_directory_transform(source: Path, destination: Path) -> _TransformPathPlan:
    if destination.exists() and not destination.is_dir():
        raise ValueError("a directory input requires a directory output path")
    source_resolved = source.resolve()
    destination_resolved = destination.resolve()
    if destination_resolved == source_resolved or source_resolved in destination_resolved.parents:
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
    return _TransformPathPlan(
        tuple((path, destination / path.relative_to(source)) for path in inputs),
        destination,
    )



def _preflight_transform_destinations(
    plan: _TransformPathPlan,
    *,
    overwrite: bool,
) -> None:
    resolved_outputs: set[Path] = set()
    for input_path, output_path in plan.pairs:
        _preflight_transform_destination(
            input_path,
            output_path,
            resolved_outputs=resolved_outputs,
            output_root=plan.output_root,
            overwrite=overwrite,
        )


def _preflight_transform_destination(
    input_path: Path,
    output_path: Path,
    *,
    resolved_outputs: set[Path],
    output_root: Path,
    overwrite: bool,
) -> None:
    resolved = output_path.resolve()
    if input_path.resolve() == resolved:
        raise ValueError(f"input and output must be different: {input_path}")
    if resolved in resolved_outputs:
        raise ValueError(f"multiple inputs resolve to the same output: {output_path}")
    resolved_outputs.add(resolved)
    if output_path.is_symlink():
        raise ValueError(f"output must not be a symbolic link: {output_path}")
    if output_path.exists() and output_path.is_dir():
        raise ValueError(f"output MIDI path is a directory: {output_path}")
    if output_path.exists() and not overwrite:
        raise ValueError(f"output already exists: {output_path}")
    _validate_output_parents(output_path.parent, stop=output_root)


def _prepare_transforms(
    pairs: tuple[tuple[Path, Path], ...],
    options: _TransformOptions,
) -> tuple[_PreparedTransform, ...]:
    prepared = []
    for input_file, output_file in pairs:
        transformed, change = transform_midi_bytes(
            input_file.read_bytes(),
            semitones=options.semitones,
            target_bpm=options.target_bpm,
            source_bpm=options.source_bpm,
            concert_pitch=options.concert_pitch,
            max_tuning_cents=options.max_tuning_cents,
        )
        prepared.append(_PreparedTransform(input_file, output_file, transformed, change))
    return tuple(prepared)


def _publish_prepared_transforms(
    prepared: tuple[_PreparedTransform, ...],
) -> list[MidiTransformFileResult]:
    for parent in sorted(
        {item.output_path.parent for item in prepared},
        key=lambda path: (len(path.parts), str(path)),
    ):
        parent.mkdir(parents=True, exist_ok=True)

    results = []
    for item in prepared:
        _write_bytes_atomic(item.output_path, item.payload)
        results.append(MidiTransformFileResult(item.input_path, item.output_path, item.change))
    return results


def _validated_semitones(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError("semitones must be an integer")
    try:
        return operator.index(value)
    except TypeError as exc:
        raise ValueError("semitones must be an integer") from exc


def _validated_tuning_limit(value: float) -> float:
    if isinstance(value, bool):
        raise ValueError("max_tuning_cents must be a finite number greater than zero")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_tuning_cents must be a finite number greater than zero") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError("max_tuning_cents must be a finite number greater than zero")
    return result


def _parse_midi(data: bytes) -> _Layout:
    source = bytes(data)
    header = _inspect_midi_header_structure(source)
    if header.midi_format not in {0, 1}:
        raise ValueError("only Standard MIDI File format 0 and 1 are supported")
    if header.track_count < 1:
        raise ValueError("MIDI file contains no tracks")
    if header.division & 0x8000:
        raise ValueError("SMPTE-time MIDI is not supported")
    if header.division == 0:
        raise ValueError("MIDI ticks per beat must be greater than zero")

    document = _parse_midi_structure(source)
    return _Layout(
        document.midi_format,
        document.division,
        tuple(_project_codec_track(document.source, track) for track in document.tracks),
    )


def _project_codec_track(source: bytes, track: _CodecMidiTrack) -> _Track:
    return _Track(
        track.index,
        track.header_offset,
        track.data_offset,
        track.length,
        tuple(_project_codec_event(source, event) for event in track.events),
    )


def _project_codec_event(source: bytes, event: _CodecMidiEvent) -> _Event:
    if event.category == "meta":
        data = () if event.meta_type is None else (event.meta_type,)
        data_offsets = ()
    elif event.category in {"channel", "system"}:
        data = tuple(source[event.data_start : event.data_end])
        data_offsets = tuple(range(event.data_start, event.data_end))
    else:
        data = ()
        data_offsets = ()
    return _Event(
        event.track_index,
        event.tick,
        event.delta,
        event.raw_start,
        event.raw_end,
        event.status,
        event.explicit_status,
        event.category,
        data_offsets,
        data,
    )


def _find_tuning_candidates(layout: _Layout, max_cents: float) -> tuple[_TuningCandidate, ...]:
    result = []
    for track in layout.tracks:
        events = track.events
        index = 0
        while index + 6 < len(events):
            group = events[index : index + 7]
            channel = group[0].channel
            if (
                channel is not None
                and channel != DRUM_CHANNEL
                and _is_cc(group[0], channel, 101, 0)
                and _is_cc(group[1], channel, 100, 0)
                and _is_cc_number(group[2], channel, 6)
                and 1 <= group[2].data[1] <= 24
                and _is_cc(group[3], channel, 38, 0)
                and _is_cc(group[4], channel, 101, 127)
                and _is_cc(group[5], channel, 100, 127)
                and group[6].category == "channel"
                and group[6].event_type == 0xE0
                and group[6].channel == channel
                and len({event.tick for event in group}) == 1
            ):
                bend = group[6].data[0] | (group[6].data[1] << 7)
                if bend != 8192:
                    bend_range = group[2].data[1]
                    scale = 8191.0 if bend > 8192 else 8192.0
                    cents = (bend - 8192) / scale * bend_range * 100.0
                    if abs(cents) <= max_cents:
                        next_event = events[index + 7] if index + 7 < len(events) else None
                        safe = (
                            all(event.delta == 0 and event.explicit_status for event in group)
                            and all(
                                left.raw_end == right.raw_start
                                for left, right in zip(group, group[1:])
                            )
                            and not (
                                next_event is not None
                                and next_event.category == "channel"
                                and not next_event.explicit_status
                            )
                        )
                        result.append(
                            _TuningCandidate(
                                TuningRemoval(
                                    track.index,
                                    channel,
                                    group[0].tick,
                                    bend,
                                    bend_range,
                                    round(cents, 6),
                                ),
                                tuple(group),
                                safe,
                            )
                        )
                        index += 7
                        continue
            index += 1
    return tuple(result)


def _validate_tuning_candidates(
    layout: _Layout,
    candidates: tuple[_TuningCandidate, ...],
) -> None:
    if not candidates:
        return
    selected_bends = {candidate.events[-1] for candidate in candidates}
    channels = {candidate.removal.channel for candidate in candidates}
    for candidate in candidates:
        if not candidate.safe_to_splice:
            raise ValueError(
                "recognised source-tuning setup cannot be removed without rewriting "
                f"running status or event timing: track={candidate.removal.track_index}, "
                f"channel={candidate.removal.channel + 1}"
            )
    for track in layout.tracks:
        for event in track.events:
            if (
                event.category == "channel"
                and event.event_type == 0xE0
                and event.channel in channels
                and event not in selected_bends
            ):
                raise ValueError(
                    "cannot remove constant source tuning from a channel that also "
                    f"contains expressive pitch bends: channel={event.channel + 1}, "
                    f"track={event.track_index}, tick={event.tick}"
                )


def _remove_event_ranges(
    data: bytearray,
    layout: _Layout,
    candidates: tuple[_TuningCandidate, ...],
) -> bytearray:
    output = bytearray(data)
    by_track: dict[int, list[tuple[int, int]]] = {}
    for candidate in candidates:
        by_track.setdefault(candidate.removal.track_index, []).append(
            (candidate.events[0].raw_start, candidate.events[-1].raw_end)
        )

    for track in reversed(layout.tracks):
        ranges = sorted(by_track.get(track.index, ()), reverse=True)
        removed = 0
        previous_start = track.data_offset + track.length
        for start, end in ranges:
            if not (track.data_offset <= start < end <= track.data_offset + track.length):
                raise ValueError("tuning event range lies outside its MIDI track")
            if end > previous_start:
                raise ValueError("overlapping tuning event ranges")
            del output[start:end]
            removed += end - start
            previous_start = start
        if removed:
            output[track.header_offset + 4 : track.header_offset + 8] = struct.pack(
                ">I", track.length - removed
            )
    return output


def _is_cc(event: _Event, channel: int, controller: int, value: int) -> bool:
    return _is_cc_number(event, channel, controller) and event.data[1] == value


def _is_cc_number(event: _Event, channel: int, controller: int) -> bool:
    return (
        event.category == "channel"
        and event.event_type == 0xB0
        and event.channel == channel
        and event.data[0] == controller
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
    "MidiTransformChange",
    "MidiTransformFileResult",
    "TuningRemoval",
    "transform_midi_bytes",
    "transform_midi_file",
    "transform_midi_path",
]
