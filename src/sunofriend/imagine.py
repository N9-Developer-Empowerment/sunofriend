"""Theory-constrained MIDI generation ("imagine mode").

For stems where raw transcription is unreliable (synth bass with glides,
leads with portamento/vibrato), we don't transcribe — we compose the most
musically sensible line that is consistent with:

  1. RHYTHM evidence  - onset times and energy from the stem (reliable),
  2. PITCH evidence   - basic-pitch output (noisy; treated as hints),
  3. THEORY constraints - the chord chart (Moises PDF), the key scale,
                          and the BPM grid.

Every emitted note is on-grid, in-key, and register-appropriate. Pitch
evidence only chooses *among* allowed options, so a wrong hint degrades
gracefully to the chord root instead of producing a sour note.
"""
from __future__ import annotations

from .beatgrid import Grid
from .chords import chord_at_time, choose_voicing, parse_key
from .models import ChordSegment, NoteEvent

BASS_LOW, BASS_HIGH = 28, 52       # E1..E3
LEAD_LOW, LEAD_HIGH = 55, 84       # G3..C6


def imagine_bass(
    stem_path: str,
    grid: Grid,
    segments: list[ChordSegment],
    key_name: str | None = None,
) -> list[NoteEvent]:
    """Bass line: evidence-first, theory-cleaned, monophonic, bass register."""
    from .transcribe_pitched import transcribe_pitched_stem

    evidence = transcribe_pitched_stem(stem_path, kind="bass")
    evidence = _verified(stem_path, evidence, threshold=0.18)
    return _theory_clean(
        evidence, segments, key_name, grid, low=BASS_LOW, high=BASS_HIGH, min_beats=0.4
    )


def imagine_lead(
    stem_path: str,
    grid: Grid,
    segments: list[ChordSegment],
    key_name: str | None = None,
) -> list[NoteEvent]:
    """Lead line: evidence-first, theory-cleaned, monophonic, lead register."""
    from .transcribe_pitched import transcribe_pitched_stem

    evidence = transcribe_pitched_stem(stem_path, kind="synth")
    evidence = _verified(stem_path, evidence, threshold=0.10)
    return _theory_clean(
        evidence, segments, key_name, grid, low=LEAD_LOW, high=LEAD_HIGH, min_beats=0.2
    )


def _verified(stem_path: str, notes: list[NoteEvent], threshold: float) -> list[NoteEvent]:
    """Drop notes with no spectral support in the stem (transcription ghosts)."""
    from .verify import verify_notes

    return verify_notes(stem_path, notes, threshold=threshold).kept


def imagine_pads(
    stem_path: str,
    grid: Grid,
    segments: list[ChordSegment],
    key_name: str | None = None,
) -> list[NoteEvent]:
    """Block-chord pad: chart voicings, timing from segments, dynamics from stem.

    Instead of transcribing a dense/hazy keys stem, play the chart: one smooth
    voicing per chord segment, velocity taken from the stem's energy during
    that segment (so builds and drops survive), silent where the stem is silent.
    """
    import librosa
    import numpy as np

    y, sr = librosa.load(stem_path, sr=22050, mono=True)
    rms = librosa.feature.rms(y=y, hop_length=512)[0]
    rms_times = librosa.times_like(rms, sr=sr, hop_length=512)
    peak = float(np.max(rms)) if rms.size else 1.0

    notes: list[NoteEvent] = []
    previous: list[int] | None = None
    for segment in segments:
        mask = (rms_times >= segment.start) & (rms_times < segment.end)
        level = float(np.mean(rms[mask])) / (peak + 1e-9) if np.any(mask) else 0.0
        if level < 0.06:
            continue  # stem is silent here: don't invent a pad
        voicing = choose_voicing(list(segment.pitch_classes), previous)
        if not voicing:
            continue
        previous = voicing
        velocity = max(35, min(112, int(round(35 + level * 85))))
        for pitch in voicing:
            notes.append(NoteEvent(segment.start, max(segment.start + 0.1, segment.end - 0.02), pitch, velocity))
    return notes


def _theory_clean(
    evidence: list[NoteEvent],
    segments: list[ChordSegment],
    key_name: str | None,
    grid: Grid,
    low: int,
    high: int,
    subdiv: int = 4,
    min_beats: float = 0.0,
) -> list[NoteEvent]:
    """Clean a noisy transcription with music theory.

    The transcription supplies WHAT was (probably) played; theory decides what
    is admissible: starts/ends snap to the metronome-true grid, pitches snap to
    the key scale (chord tones required on strong beats when the pitch is out
    of key), the line is made monophonic, and everything folds into register.
    """
    key_pcs = parse_key(key_name) or set(range(12))
    step = grid.beat_seconds / subdiv

    mono = _monophonic(evidence)
    notes: list[NoteEvent] = []
    previous_pitch: int | None = None
    for note in mono:
        start = grid.snap(note.start, subdiv)
        end = max(start + step * 0.9, grid.snap(note.end, subdiv))
        segment = chord_at_time(segments, start)
        on_beat = grid.is_strong(start)

        if note.pitch % 12 in key_pcs and low <= note.pitch <= high:
            # in key and in register: trust the evidence as-is
            pitch = note.pitch
        else:
            allowed = _allowed_pcs(segment, key_pcs, on_beat)
            pitch = _snap_pitch(note.pitch, allowed, low, high, previous_pitch)

        if notes and notes[-1].start == start:
            continue  # quantization collision: keep the earlier (stronger) voice
        if notes and notes[-1].end > start:
            notes[-1] = NoteEvent(notes[-1].start, start, notes[-1].pitch, notes[-1].velocity)
        previous_pitch = pitch
        notes.append(NoteEvent(start=round(start, 4), end=round(end, 4), pitch=pitch, velocity=note.velocity))
    min_len = max(step * 0.4, min_beats * grid.beat_seconds * 0.9)
    return [n for n in notes if n.end - n.start >= min_len]


def _allowed_pcs(segment: ChordSegment | None, key_pcs: set[int], on_beat: bool) -> set[int]:
    if segment is None:
        return key_pcs
    chord_pcs = set(segment.pitch_classes)
    return chord_pcs if on_beat else (key_pcs | chord_pcs)


def _snap_pitch(pitch: int, allowed_pcs: set[int], low: int, high: int, previous: int | None) -> int:
    """Nearest pitch whose class is allowed, minimizing distance to the
    evidence pitch and (secondarily) melodic jump from the previous note."""
    best, best_cost = pitch, float("inf")
    for candidate in range(low, high + 1):
        if candidate % 12 not in allowed_pcs:
            continue
        cost = abs(candidate - pitch) * 2.0
        if previous is not None:
            cost += abs(candidate - previous) * 0.5
        if cost < best_cost:
            best, best_cost = candidate, cost
    return best


def _to_register(pc: int, low: int, high: int, anchor: int) -> int:
    candidates = [p for p in range(low, high + 1) if p % 12 == pc]
    if not candidates:
        return max(low, min(high, anchor))
    return min(candidates, key=lambda p: abs(p - anchor))


def _monophonic(notes: list[NoteEvent]) -> list[NoteEvent]:
    """Reduce polyphonic evidence to the single strongest concurrent voice."""
    result: list[NoteEvent] = []
    for note in sorted(notes, key=lambda n: (n.start, -n.velocity)):
        if result and note.start < result[-1].end:
            if note.velocity > result[-1].velocity * 1.4:
                prev = result.pop()
                if note.start - prev.start > 0.05:
                    result.append(NoteEvent(prev.start, note.start, prev.pitch, prev.velocity))
            else:
                continue
        result.append(note)
    return result
