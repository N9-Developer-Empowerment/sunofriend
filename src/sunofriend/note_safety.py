"""Make MIDI note lifetimes unambiguous without removing musical onsets.

MIDI identifies an active note by channel and pitch.  It has no note-instance
identifier, so starting the same channel/pitch twice before its first note-off
makes the later note's lifetime synth-dependent.  These helpers retain every
distinct onset but end the earlier note at the next onset.  Notes with the
same onset are one musical event and are collapsed deterministically.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Iterable

from .models import NoteEvent


@dataclass(frozen=True)
class MidiNoteInterval:
    """A note already converted to the ticks/channel used in a MIDI file."""

    owner: int
    channel: int
    start_tick: int
    end_tick: int
    pitch: int
    velocity: int
    release_velocity: int = 0


@dataclass(frozen=True)
class _Interval:
    owner: int
    channel: int
    start: int | float
    end: int | float
    pitch: int
    velocity: int
    release_velocity: int


def normalize_note_events(
    notes: Iterable[NoteEvent], *, minimum_duration: float = 1e-6
) -> list[NoteEvent]:
    """Return stable, non-overlapping same-pitch notes in source seconds.

    Distinct pitches remain polyphonic.  A later onset of the same pitch is
    retained and truncates only the preceding note.  Exact duplicate starts
    collapse to the longest end and greatest velocity, independent of input
    order.
    """

    if not math.isfinite(minimum_duration) or minimum_duration <= 0:
        raise ValueError("minimum_duration must be finite and greater than zero")
    intervals = []
    for note in notes:
        if not math.isfinite(note.start) or not math.isfinite(note.end):
            raise ValueError("Note start and end must be finite")
        intervals.append(
            _Interval(0, 0, note.start, note.end, note.pitch, note.velocity, 0)
        )
    normalized = _normalize_intervals(intervals, minimum_duration)
    return [
        NoteEvent(
            start=float(note.start),
            end=float(note.end),
            pitch=note.pitch,
            velocity=note.velocity,
        )
        for note in normalized
    ]


def normalize_midi_intervals(
    notes: Iterable[MidiNoteInterval],
) -> list[MidiNoteInterval]:
    """Normalize actual MIDI ticks independently within each file track.

    Performing this after time-to-tick conversion also catches distinct source
    times that quantize to the same MIDI onset. ``owner`` identifies a Standard
    MIDI File track: GarageBand imports those as independent regions/tracks, so
    notes in one owner must never truncate or consume notes in another merely
    because their channel numbers match.
    """

    intervals = []
    for note in notes:
        values = (note.owner, note.channel, note.start_tick, note.end_tick, note.pitch)
        if any(isinstance(value, bool) or int(value) != value for value in values):
            raise ValueError("MIDI note interval fields must be integers")
        if note.start_tick < 0:
            raise ValueError("MIDI export cannot represent a note before time zero")
        intervals.append(
            _Interval(
                int(note.owner),
                int(note.channel),
                int(note.start_tick),
                int(note.end_tick),
                int(note.pitch),
                int(note.velocity),
                int(note.release_velocity),
            )
        )
    normalized = _normalize_intervals(intervals, 1)
    return [
        MidiNoteInterval(
            owner=note.owner,
            channel=note.channel,
            start_tick=int(note.start),
            end_tick=int(note.end),
            pitch=note.pitch,
            velocity=note.velocity,
            release_velocity=note.release_velocity,
        )
        for note in normalized
    ]


def _normalize_intervals(
    intervals: Iterable[_Interval], minimum_duration: int | float
) -> list[_Interval]:
    # A duplicate onset cannot be represented as two independent MIDI notes.
    # Choose the earliest track owner and combine duration/expression by max,
    # making the result independent of source iteration order.
    by_start: dict[tuple[int, int, int, int | float], _Interval] = {}
    for note in intervals:
        key = (note.owner, note.channel, note.pitch, note.start)
        existing = by_start.get(key)
        safe_end = max(note.end, note.start + minimum_duration)
        candidate = replace(note, end=safe_end)
        if existing is None:
            by_start[key] = candidate
        else:
            by_start[key] = _Interval(
                owner=min(existing.owner, candidate.owner),
                channel=existing.channel,
                start=existing.start,
                end=max(existing.end, candidate.end),
                pitch=existing.pitch,
                velocity=max(existing.velocity, candidate.velocity),
                release_velocity=max(
                    existing.release_velocity, candidate.release_velocity
                ),
            )

    by_voice: dict[tuple[int, int, int], list[_Interval]] = {}
    for note in by_start.values():
        by_voice.setdefault((note.owner, note.channel, note.pitch), []).append(note)

    result: list[_Interval] = []
    for voice in by_voice.values():
        voice.sort(key=lambda note: (note.start, note.end, note.owner))
        for index, note in enumerate(voice):
            end = note.end
            if index + 1 < len(voice):
                end = min(end, voice[index + 1].start)
            result.append(replace(note, end=end))
    return sorted(
        result,
        key=lambda note: (
            note.start,
            note.channel,
            note.pitch,
            note.end,
            note.owner,
            -note.velocity,
        ),
    )


__all__ = ["MidiNoteInterval", "normalize_midi_intervals", "normalize_note_events"]
