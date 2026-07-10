from __future__ import annotations

from .chords import chord_at_time
from .grid import seconds_per_beat
from .models import ChordSegment, NoteEvent, StemAnalysis

DRUM_PITCHES = {
    "kick": 36,
    "snare": 38,
    "hat": 42,
    "cymbals": 49,
    "toms": 45,
    "other_kit": 39,
}


def drum_notes_from_analysis(part: str, analysis: StemAnalysis, duration: float = 0.075) -> list[NoteEvent]:
    pitch = DRUM_PITCHES[part]
    velocity_base = {"kick": 110, "snare": 102, "hat": 72, "cymbals": 82, "toms": 92, "other_kit": 78}.get(part, 80)
    notes = []
    peak = analysis.peak_rms or 1.0
    for event in analysis.events:
        velocity = int(min(127, max(45, velocity_base * (0.65 + 0.35 * event.strength / peak))))
        notes.append(NoteEvent(start=event.time, end=event.time + duration, pitch=pitch, velocity=velocity))
    return notes


def bass_notes_from_activity(
    bass: StemAnalysis | None,
    kick: StemAnalysis | None,
    chords: list[ChordSegment],
    bpm: float,
) -> list[NoteEvent]:
    source_events = bass.events if bass and len(bass.events) >= 4 else []
    if not source_events and kick:
        source_events = kick.events
    if not source_events:
        source_events = [_synthetic_event(segment.start, bpm) for segment in chords]

    beat = seconds_per_beat(bpm)
    notes: list[NoteEvent] = []
    for index, event in enumerate(source_events):
        segment = chord_at_time(chords, event.time)
        if not segment:
            continue
        next_time = source_events[index + 1].time if index + 1 < len(source_events) else min(segment.end, event.time + beat)
        end = min(segment.end, max(event.time + beat * 0.45, next_time - 0.025))
        pitch = _bass_pitch(segment.root_pc)
        notes.append(NoteEvent(start=event.time, end=end, pitch=pitch, velocity=94))
    return _thin_repeated_bass(notes, min_gap=beat * 0.25)


def _bass_pitch(pc: int, low: int = 36, high: int = 50) -> int:
    candidates = [pitch for pitch in range(low, high + 1) if pitch % 12 == pc]
    return candidates[len(candidates) // 2] if candidates else low + pc


def _synthetic_event(time: float, bpm: float):
    from .models import StemEvent
    from .grid import seconds_to_beats

    return StemEvent(time=time, beat=seconds_to_beats(time, bpm), strength=1.0)


def _thin_repeated_bass(notes: list[NoteEvent], min_gap: float) -> list[NoteEvent]:
    kept: list[NoteEvent] = []
    for note in notes:
        if kept and note.pitch == kept[-1].pitch and note.start - kept[-1].start < min_gap:
            continue
        kept.append(note)
    return kept
