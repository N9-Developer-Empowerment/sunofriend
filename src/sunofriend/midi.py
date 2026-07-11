from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from .grid import seconds_per_beat
from .models import NoteEvent
from .note_safety import MidiNoteInterval, normalize_midi_intervals


@dataclass(frozen=True)
class MidiTrack:
    name: str
    channel: int
    program: int
    notes: list[NoteEvent]


def write_midi_file(path: str | Path, tracks: list[MidiTrack], bpm: float, ticks_per_beat: int = 480) -> None:
    if not tracks:
        raise ValueError("At least one track is required")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    raw_notes: list[MidiNoteInterval] = []
    for track_index, track in enumerate(tracks):
        for note in track.notes:
            start = _seconds_to_ticks(note.start, bpm, ticks_per_beat)
            end = _seconds_to_ticks(note.end, bpm, ticks_per_beat)
            raw_notes.append(
                MidiNoteInterval(
                    owner=track_index,
                    channel=track.channel,
                    start_tick=start,
                    end_tick=end,
                    pitch=_clamp(note.pitch, 0, 127),
                    velocity=_clamp(note.velocity, 1, 127),
                )
            )
    safe_notes = normalize_midi_intervals(raw_notes)
    notes_by_track: dict[int, list[MidiNoteInterval]] = {
        index: [] for index in range(len(tracks))
    }
    for note in safe_notes:
        notes_by_track[note.owner].append(note)

    chunks = [_tempo_track_chunk(bpm)]
    chunks.extend(
        _track_chunk(track, notes_by_track[index])
        for index, track in enumerate(tracks)
    )
    header = b"MThd" + struct.pack(">IHHH", 6, 1, len(chunks), ticks_per_beat)
    path.write_bytes(header + b"".join(chunks))


def _tempo_track_chunk(bpm: float) -> bytes:
    micros = int(round(60_000_000 / bpm))
    data = bytearray()
    data.extend(_var_len(0))
    data.extend(b"\xff\x03\x05Tempo")
    data.extend(_var_len(0))
    data.extend(b"\xff\x51\x03")
    data.extend(micros.to_bytes(3, "big"))
    data.extend(_var_len(0))
    data.extend(b"\xff\x58\x04\x04\x02\x18\x08")
    data.extend(_var_len(0))
    data.extend(b"\xff\x2f\x00")
    return b"MTrk" + struct.pack(">I", len(data)) + bytes(data)


def _track_chunk(track: MidiTrack, notes: list[MidiNoteInterval]) -> bytes:
    events: list[tuple[int, int, bytes]] = []
    name = track.name.encode("utf-8")
    events.append((0, 0, b"\xff\x03" + _var_len(len(name)) + name))
    if track.channel != 9:
        events.append((0, 1, bytes([0xC0 | track.channel, _clamp(track.program, 0, 127)])))

    for note in notes:
        events.append(
            (note.start_tick, 3, bytes([0x90 | track.channel, note.pitch, note.velocity]))
        )
        events.append(
            (note.end_tick, 2, bytes([0x80 | track.channel, note.pitch, note.release_velocity]))
        )

    events.sort(key=lambda event: (event[0], event[1], event[2]))
    data = bytearray()
    previous_tick = 0
    for tick, _, payload in events:
        data.extend(_var_len(tick - previous_tick))
        data.extend(payload)
        previous_tick = tick
    data.extend(_var_len(0))
    data.extend(b"\xff\x2f\x00")
    return b"MTrk" + struct.pack(">I", len(data)) + bytes(data)


def _seconds_to_ticks(seconds: float, bpm: float, ticks_per_beat: int) -> int:
    return int(round(seconds / seconds_per_beat(bpm) * ticks_per_beat))


def _var_len(value: int) -> bytes:
    if value < 0:
        raise ValueError("MIDI delta time cannot be negative")
    buffer = value & 0x7F
    value >>= 7
    output = [buffer]
    while value:
        output.insert(0, (value & 0x7F) | 0x80)
        value >>= 7
    return bytes(output)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))
