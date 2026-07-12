"""Bar-anchor complete MIDI files without flattening their groove.

This is the constant-offset counterpart to :mod:`sunofriend.midi_align`.
``midi_align`` maps source seconds through a detected beat grid; this module
first delegates transposition, tick-preserving tempo changes, and optional
concert-pitch cleanup to :mod:`sunofriend.midi_transform`, then moves musical
events by one constant number of ticks.  Every performance interval therefore
retains its original tick length and microtiming.

Event classification is intentionally conservative and targets MIDI written
by Sunofriend.  At tick zero we retain conductor/setup metadata (tempo, time
signature, key signature, track/instrument names), program changes, SysEx and
system initialization, plus the exact seven-event RPN-0 tuning sequence that
Sunofriend writes.  Notes, markers, lyrics, ordinary controllers, pressure,
and non-initialization pitch bends are musical/timed events and move even when
they originally occur at tick zero.  Unknown tick-zero CC sequences are moved
rather than guessed to be setup.
"""

from __future__ import annotations

import math
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .midi_transform import (
    MIDI_SUFFIXES,
    MidiTransformChange,
    _parse_midi,
    _read_varlen,
    _validate_output_parents,
    _write_bytes_atomic,
    transform_midi_bytes,
)


# Meta events that describe the file/track rather than a performance gesture.
# They stay at zero only when they were already at zero; later changes move.
_TICK_ZERO_SETUP_META = {
    0x00,  # sequence number
    0x02,  # copyright
    0x03,  # track name
    0x04,  # instrument name
    0x20,  # MIDI channel prefix
    0x21,  # MIDI port
    0x51,  # set tempo
    0x54,  # SMPTE offset
    0x58,  # time signature
    0x59,  # key signature
}


@dataclass(frozen=True)
class MidiAnchorChange:
    """Auditable description of one groove-preserving anchor operation."""

    source_downbeat_seconds: float
    source_bpm: float
    target_bpm: float
    target_downbeat_beat: float
    source_downbeat_tick: int
    target_downbeat_tick: int
    shift_ticks: int
    shifted_events: int
    shifted_note_events: int
    shifted_channel_events: int
    shifted_meta_events: int
    shifted_other_events: int
    tick_zero_setup_events_preserved: int
    midi_format: int
    ticks_per_beat: int
    track_count: int
    concert_pitch_cleanup_requested: bool
    transform: MidiTransformChange

    @property
    def semitones(self) -> int:
        return self.transform.semitones

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["semitones"] = self.semitones
        value["transform"][
            "tuning_setups_removed"
        ] = self.transform.tuning_setups_removed
        value["transform"][
            "tuning_events_removed"
        ] = self.transform.tuning_events_removed
        return value


@dataclass(frozen=True)
class MidiAnchorFileResult:
    input_path: Path
    output_path: Path
    change: MidiAnchorChange

    def to_dict(self) -> dict[str, Any]:
        value = self.change.to_dict()
        value["input"] = str(self.input_path)
        value["output"] = str(self.output_path)
        return value


@dataclass(frozen=True)
class _ShiftedEvent:
    tick: int
    order: int
    payload: bytes
    shifted: bool
    category: str
    event_type: int
    is_end_of_track: bool = False


def anchor_midi_bytes(
    data: bytes,
    *,
    source_downbeat_seconds: float,
    source_bpm: float,
    target_bpm: float,
    target_downbeat_beat: float = 4.0,
    semitones: int = 0,
    concert_pitch: bool = False,
    max_tuning_cents: float = 100.0,
) -> tuple[bytes, MidiAnchorChange]:
    """Transform and then bar-anchor one complete Standard MIDI File.

    Tempo replacement performed by ``midi_transform`` deliberately leaves all
    ticks untouched. The source downbeat tick is therefore recovered from the
    original tempo map (whose tick-zero tempo is checked against
    ``source_bpm``) even though the byte stream has already received the target
    tempo payload when its events are shifted.
    """

    source_downbeat = _non_negative_number(
        source_downbeat_seconds, "source_downbeat_seconds"
    )
    source_tempo = _positive_number(source_bpm, "source_bpm")
    target_tempo = _positive_number(target_bpm, "target_bpm")
    target_beat = _non_negative_number(target_downbeat_beat, "target_downbeat_beat")

    raw = bytes(data)
    transformed, transform_change = transform_midi_bytes(
        raw,
        semitones=semitones,
        source_bpm=source_tempo,
        target_bpm=target_tempo,
        concert_pitch=concert_pitch,
        max_tuning_cents=max_tuning_cents,
    )
    source_layout = _parse_midi(raw)
    source_tick = _seconds_to_source_tick(
        raw,
        source_layout,
        source_downbeat,
    )
    layout = _parse_midi(transformed)
    ticks_per_beat = layout.ticks_per_beat
    if source_layout.ticks_per_beat != ticks_per_beat:
        raise ValueError("MIDI transform unexpectedly changed ticks per beat")
    target_tick = int(round(target_beat * ticks_per_beat))
    shift_ticks = target_tick - source_tick

    if shift_ticks == 0:
        setup_count = sum(
            len(_setup_event_indices(track.events)) for track in layout.tracks
        )
        return transformed, MidiAnchorChange(
            source_downbeat_seconds=source_downbeat,
            source_bpm=source_tempo,
            target_bpm=target_tempo,
            target_downbeat_beat=target_beat,
            source_downbeat_tick=source_tick,
            target_downbeat_tick=target_tick,
            shift_ticks=0,
            shifted_events=0,
            shifted_note_events=0,
            shifted_channel_events=0,
            shifted_meta_events=0,
            shifted_other_events=0,
            tick_zero_setup_events_preserved=setup_count,
            midi_format=layout.midi_format,
            ticks_per_beat=ticks_per_beat,
            track_count=len(layout.tracks),
            concert_pitch_cleanup_requested=concert_pitch,
            transform=transform_change,
        )

    rebuilt_tracks: list[bytes] = []
    shifted_events = 0
    shifted_notes = 0
    shifted_channels = 0
    shifted_meta = 0
    shifted_other = 0
    setup_preserved = 0

    for track in layout.tracks:
        setup_indices = _setup_event_indices(track.events)
        setup_preserved += len(setup_indices)
        encoded: list[_ShiftedEvent] = []
        end_event: _ShiftedEvent | None = None
        maximum_tick = 0
        track_has_shifted_event = False

        for order, event in enumerate(track.events):
            payload = _canonical_event_payload(transformed, event)
            is_eot = (
                event.category == "meta"
                and event.data
                and event.data[0] == 0x2F
            )
            if is_eot:
                end_event = _ShiftedEvent(
                    event.tick,
                    order,
                    payload,
                    False,
                    event.category,
                    event.event_type,
                    True,
                )
                continue

            should_shift = order not in setup_indices
            new_tick = event.tick + shift_ticks if should_shift else event.tick
            if new_tick < 0:
                raise ValueError(
                    "bar anchor would move an event before MIDI tick zero: "
                    f"track={track.index}, source_tick={event.tick}, "
                    f"shift_ticks={shift_ticks}"
                )
            maximum_tick = max(maximum_tick, new_tick)
            track_has_shifted_event = track_has_shifted_event or should_shift
            encoded.append(
                _ShiftedEvent(
                    new_tick,
                    order,
                    payload,
                    should_shift,
                    event.category,
                    event.event_type,
                )
            )
            if should_shift:
                shifted_events += 1
                if event.category == "channel":
                    shifted_channels += 1
                    if event.event_type in {0x80, 0x90}:
                        shifted_notes += 1
                elif event.category == "meta":
                    shifted_meta += 1
                else:
                    shifted_other += 1

        if end_event is None:
            raise ValueError(f"MIDI track {track.index} has no End Of Track event")
        eot_tick = end_event.tick
        if track_has_shifted_event:
            eot_tick += shift_ticks
        eot_tick = max(0, maximum_tick, eot_tick)
        encoded.append(
            _ShiftedEvent(
                eot_tick,
                end_event.order,
                end_event.payload,
                track_has_shifted_event,
                end_event.category,
                end_event.event_type,
                True,
            )
        )
        encoded.sort(
            key=lambda item: (
                item.tick,
                1 if item.is_end_of_track else 0,
                item.order,
            )
        )

        body = bytearray()
        previous_tick = 0
        for item in encoded:
            if item.tick < previous_tick:
                raise ValueError(
                    "internal error: shifted MIDI events are not monotonic"
                )
            body.extend(_varlen(item.tick - previous_tick))
            body.extend(item.payload)
            previous_tick = item.tick

        # Preserve non-event padding after End Of Track, if a producer wrote
        # any. It remains semantically unreachable but is still part of the SMF.
        original_end = track.data_offset + track.length
        parsed_end = track.events[-1].raw_end if track.events else track.data_offset
        if parsed_end < original_end:
            body.extend(transformed[parsed_end:original_end])
        rebuilt_tracks.append(b"MTrk" + struct.pack(">I", len(body)) + bytes(body))

    header_end = layout.tracks[0].header_offset
    output = bytearray(transformed[:header_end])
    output.extend(b"".join(rebuilt_tracks))
    last = layout.tracks[-1]
    trailing_start = last.data_offset + last.length
    output.extend(transformed[trailing_start:])

    return bytes(output), MidiAnchorChange(
        source_downbeat_seconds=source_downbeat,
        source_bpm=source_tempo,
        target_bpm=target_tempo,
        target_downbeat_beat=target_beat,
        source_downbeat_tick=source_tick,
        target_downbeat_tick=target_tick,
        shift_ticks=shift_ticks,
        shifted_events=shifted_events,
        shifted_note_events=shifted_notes,
        shifted_channel_events=shifted_channels,
        shifted_meta_events=shifted_meta,
        shifted_other_events=shifted_other,
        tick_zero_setup_events_preserved=setup_preserved,
        midi_format=layout.midi_format,
        ticks_per_beat=ticks_per_beat,
        track_count=len(layout.tracks),
        concert_pitch_cleanup_requested=concert_pitch,
        transform=transform_change,
    )


def anchor_midi_path(
    input_path: str | Path,
    output_path: str | Path,
    *,
    source_downbeat_seconds: float,
    source_bpm: float,
    target_bpm: float,
    target_downbeat_beat: float = 4.0,
    semitones: int = 0,
    concert_pitch: bool = False,
    max_tuning_cents: float = 100.0,
    overwrite: bool = False,
) -> list[MidiAnchorFileResult]:
    """Anchor one MIDI file or a recursive MIDI directory atomically.

    Every destination and every input transformation is preflighted before the
    first output is published. Directory processing preserves relative paths
    and ignores non-MIDI files.
    """

    source = Path(input_path)
    destination = Path(output_path)
    pairs, output_root = _input_output_pairs(source, destination)
    _preflight_destinations(pairs, output_root=output_root, overwrite=overwrite)

    prepared: list[tuple[Path, Path, bytes, MidiAnchorChange]] = []
    for input_file, output_file in pairs:
        payload, change = anchor_midi_bytes(
            input_file.read_bytes(),
            source_downbeat_seconds=source_downbeat_seconds,
            source_bpm=source_bpm,
            target_bpm=target_bpm,
            target_downbeat_beat=target_downbeat_beat,
            semitones=semitones,
            concert_pitch=concert_pitch,
            max_tuning_cents=max_tuning_cents,
        )
        prepared.append((input_file, output_file, payload, change))

    for parent in sorted(
        {output_file.parent for _, output_file, _, _ in prepared},
        key=lambda path: (len(path.parts), str(path)),
    ):
        parent.mkdir(parents=True, exist_ok=True)

    results: list[MidiAnchorFileResult] = []
    for input_file, output_file, payload, change in prepared:
        _write_bytes_atomic(output_file, payload)
        results.append(MidiAnchorFileResult(input_file, output_file, change))
    return results


def anchor_midi_file(
    input_path: str | Path,
    output_path: str | Path,
    **kwargs: Any,
) -> MidiAnchorFileResult:
    source = Path(input_path)
    if not source.is_file():
        raise ValueError("anchor_midi_file requires a MIDI file input")
    return anchor_midi_path(source, output_path, **kwargs)[0]


def _setup_event_indices(events: tuple[Any, ...]) -> set[int]:
    setup: set[int] = set()
    for index, event in enumerate(events):
        if event.tick != 0:
            continue
        if event.category == "meta" and event.data:
            if event.data[0] in _TICK_ZERO_SETUP_META:
                setup.add(index)
        elif event.category == "channel" and event.event_type == 0xC0:
            setup.add(index)
        elif event.category in {"sysex", "system"}:
            # Sunofriend does not emit these today. Keeping tick-zero system
            # messages is the conservative device-initialization policy.
            setup.add(index)

    # Exact setup emitted by MidiTrack(pitch_bend_cents=...): RPN 0,0, bend
    # range MSB/LSB, RPN null, then one constant pitch-wheel value.
    for index in range(max(0, len(events) - 6)):
        group = events[index : index + 7]
        if len(group) < 7 or any(event.tick != 0 for event in group):
            continue
        channel = group[0].channel
        if channel is None or channel == 9:
            continue
        if (
            _is_cc(group[0], channel, 101, 0)
            and _is_cc(group[1], channel, 100, 0)
            and _is_cc_number(group[2], channel, 6)
            and 1 <= group[2].data[1] <= 24
            and _is_cc(group[3], channel, 38, 0)
            and _is_cc(group[4], channel, 101, 127)
            and _is_cc(group[5], channel, 100, 127)
            and group[6].category == "channel"
            and group[6].event_type == 0xE0
            and group[6].channel == channel
        ):
            setup.update(range(index, index + 7))
    return setup


def _canonical_event_payload(data: bytes, event: Any) -> bytes:
    _, payload_start = _read_varlen(data, event.raw_start)
    payload = data[payload_start : event.raw_end]
    if event.category == "channel" and not event.explicit_status:
        # Reordering tick-zero setup before shifted musical events can break a
        # running-status dependency. Canonical explicit status makes every
        # channel event self-contained while retaining its exact data bytes.
        return bytes((event.status,)) + payload
    return payload


def _input_output_pairs(
    source: Path, destination: Path
) -> tuple[list[tuple[Path, Path]], Path]:
    if not source.exists():
        raise ValueError(f"input does not exist: {source}")
    if source.is_file():
        if source.suffix.lower() not in MIDI_SUFFIXES:
            raise ValueError("file input must end in .mid or .midi")
        if destination.exists() and destination.is_dir():
            raise ValueError("a file input requires a MIDI file output path")
        if destination.suffix.lower() not in MIDI_SUFFIXES:
            raise ValueError("file output must end in .mid or .midi")
        return [(source, destination)], destination.parent
    if not source.is_dir():
        raise ValueError(f"input must be a MIDI file or directory: {source}")
    if destination.exists() and not destination.is_dir():
        raise ValueError("a directory input requires a directory output path")
    source_resolved = source.resolve()
    destination_resolved = destination.resolve()
    if (
        destination_resolved == source_resolved
        or source_resolved in destination_resolved.parents
    ):
        raise ValueError(
            "output directory must not be the input directory or inside it"
        )
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
    return [
        (path, destination / path.relative_to(source)) for path in inputs
    ], destination


def _preflight_destinations(
    pairs: list[tuple[Path, Path]],
    *,
    output_root: Path,
    overwrite: bool,
) -> None:
    resolved_outputs: set[Path] = set()
    for input_file, output_file in pairs:
        resolved = output_file.resolve()
        if input_file.resolve() == resolved:
            raise ValueError(f"input and output must be different: {input_file}")
        if resolved in resolved_outputs:
            raise ValueError(
                f"multiple inputs resolve to the same output: {output_file}"
            )
        resolved_outputs.add(resolved)
        if output_file.is_symlink():
            raise ValueError(f"output must not be a symbolic link: {output_file}")
        if output_file.exists() and output_file.is_dir():
            raise ValueError(f"output MIDI path is a directory: {output_file}")
        if output_file.exists() and not overwrite:
            raise ValueError(f"output already exists: {output_file}")
        _validate_output_parents(output_file.parent, stop=output_root)


def _positive_number(value: float, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number greater than zero")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number greater than zero") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{label} must be a finite number greater than zero")
    return result


def _seconds_to_source_tick(data: bytes, layout: Any, seconds: float) -> int:
    """Invert the original SMF tempo map without assuming constant tempo."""

    tempos: list[tuple[int, int, int]] = []
    order = 0
    for track in layout.tracks:
        for event in track.events:
            if (
                event.category != "meta"
                or not event.data
                or event.data[0] != 0x51
            ):
                continue
            _, payload_start = _read_varlen(data, event.raw_start)
            if data[payload_start : payload_start + 2] != b"\xff\x51":
                raise ValueError("invalid Set Tempo event")
            length, value_start = _read_varlen(data, payload_start + 2)
            if length != 3 or value_start + 3 > event.raw_end:
                raise ValueError("Set Tempo event must contain three bytes")
            micros = int.from_bytes(data[value_start : value_start + 3], "big")
            if micros <= 0:
                raise ValueError("Set Tempo value must be greater than zero")
            tempos.append((event.tick, order, micros))
            order += 1

    # SMF default tempo is 120 BPM until the first Set Tempo event. Conflicting
    # simultaneous tempo events are rejected by midi_transform's retimer; the
    # last stable ordering here matters only long enough to compute a preflight
    # value before that validation runs.
    tempos.sort(key=lambda item: (item[0], item[1]))
    current_tempo = 500_000
    current_tick = 0
    elapsed = 0.0
    index = 0
    while index < len(tempos):
        tick = tempos[index][0]
        segment = (
            (tick - current_tick)
            * current_tempo
            / 1_000_000.0
            / layout.ticks_per_beat
        )
        if seconds <= elapsed + segment + 1e-12:
            delta_seconds = max(0.0, seconds - elapsed)
            return current_tick + int(
                round(
                    delta_seconds
                    * 1_000_000.0
                    * layout.ticks_per_beat
                    / current_tempo
                )
            )
        elapsed += segment
        current_tick = tick
        while index < len(tempos) and tempos[index][0] == tick:
            current_tempo = tempos[index][2]
            index += 1
    delta_seconds = max(0.0, seconds - elapsed)
    return current_tick + int(
        round(
            delta_seconds
            * 1_000_000.0
            * layout.ticks_per_beat
            / current_tempo
        )
    )


def _non_negative_number(value: float, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite non-negative number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite non-negative number") from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return result


def _varlen(value: int) -> bytes:
    if value < 0:
        raise ValueError("MIDI delta cannot be negative")
    result = [value & 0x7F]
    value >>= 7
    while value:
        result.insert(0, (value & 0x7F) | 0x80)
        value >>= 7
    return bytes(result)


def _is_cc(event: Any, channel: int, controller: int, value: int) -> bool:
    return _is_cc_number(event, channel, controller) and event.data[1] == value


def _is_cc_number(event: Any, channel: int, controller: int) -> bool:
    return (
        event.category == "channel"
        and event.event_type == 0xB0
        and event.channel == channel
        and event.data[0] == controller
    )


__all__ = [
    "MidiAnchorChange",
    "MidiAnchorFileResult",
    "anchor_midi_bytes",
    "anchor_midi_file",
    "anchor_midi_path",
]
