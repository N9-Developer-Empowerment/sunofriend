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

BASS_LOW, BASS_HIGH = 23, 52       # B0..E3 (five-string / synth-bass range)
LEAD_LOW, LEAD_HIGH = 55, 84       # G3..C6


def imagine_bass(
    stem_path: str,
    grid: Grid,
    segments: list[ChordSegment],
    key_name: str | None = None,
) -> list[NoteEvent]:
    """Return the default contour-preserving bass interpretation.

    ``imagine_bass_variants`` exposes the evidence and conservative chord-root
    alternatives for auditioning.  Keeping this wrapper means existing callers
    continue to receive one list of notes.
    """
    return imagine_bass_variants(
        stem_path,
        grid=grid,
        segments=segments,
        key_name=key_name,
    )["contour_clean"]


def imagine_bass_variants(
    stem_path: str,
    grid: Grid,
    segments: list[ChordSegment],
    key_name: str | None = None,
) -> dict[str, list[NoteEvent]]:
    """Build three deterministic bass candidates from the same stem evidence.

    ``raw_verified`` preserves the hybrid Basic Pitch / pYIN contour without
    quantisation. ``contour_clean`` adds the existing grid and harmony safety
    rules while retaining supported passing tones. ``root_safe`` keeps the
    contour-clean rhythm and expression but uses the active chord root.  The
    explicit alternatives make the creative trade-off audible instead of
    silently replacing a walking line with roots.
    """
    from .transcribe_pitched import transcribe_pitched_stem

    evidence = transcribe_pitched_stem(stem_path, kind="bass")
    raw_verified = _verified(stem_path, evidence, threshold=0.18)
    contour_clean = _theory_clean(
        raw_verified,
        segments,
        key_name,
        grid,
        low=BASS_LOW,
        high=BASS_HIGH,
        min_beats=0.4,
    )
    return {
        "raw_verified": raw_verified,
        "contour_clean": contour_clean,
        "root_safe": _root_safe_bass(contour_clean, segments, BASS_LOW, BASS_HIGH),
    }


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
    # Separation models often leave a very quiet, harmonically coherent copy
    # of the rest of the mix in an otherwise sparse lead stem.  Pitch/spectral
    # checks alone can mistake that bleed for a full-song melody.  Require each
    # surviving hypothesis to overlap locally audible activity (still a very
    # permissive -40 dB relative to the stem's loudest RMS frame, plus an
    # absolute -66 dBFS RMS floor so an all-bleed file cannot normalize itself
    # into looking active).
    evidence = _filter_notes_by_activity(stem_path, evidence, min_peak_ratio=0.01)
    return _theory_clean(
        evidence, segments, key_name, grid, low=LEAD_LOW, high=LEAD_HIGH, min_beats=0.2
    )


def _verified(stem_path: str, notes: list[NoteEvent], threshold: float) -> list[NoteEvent]:
    """Drop notes with no spectral support in the stem (transcription ghosts)."""
    from .verify import verify_notes

    return verify_notes(stem_path, notes, threshold=threshold).kept


def _filter_notes_by_activity(
    stem_path: str,
    notes: list[NoteEvent],
    *,
    min_peak_ratio: float = 0.01,
    absolute_rms_floor: float = 5e-4,
) -> list[NoteEvent]:
    """Reject pitch hypotheses that exist only in very-low-level stem bleed.

    This is intentionally a local gate rather than a whole-file RMS test: a
    legitimate lead can be silent for most of a song.  A small margin around
    each note catches short attacks that fall just outside a tracker boundary.
    The absolute floor rejects a uniformly tiny tonal residue even when it is
    the loudest material in the stem.
    """

    if not notes:
        return []
    if not 0.0 < min_peak_ratio <= 1.0:
        raise ValueError("min_peak_ratio must be between 0 and 1")
    if not 0.0 <= absolute_rms_floor <= 1.0:
        raise ValueError("absolute_rms_floor must be between 0 and 1")

    import librosa
    import numpy as np

    sample_rate = 22050
    hop_length = 512
    audio, _ = librosa.load(stem_path, sr=sample_rate, mono=True)
    if audio.size == 0:
        return []
    rms = librosa.feature.rms(y=audio, hop_length=hop_length)[0]
    if rms.size == 0:
        return []
    peak = float(np.max(rms))
    if peak <= 1e-9:
        return []
    threshold = max(peak * min_peak_ratio, absolute_rms_floor)
    frame_seconds = hop_length / sample_rate
    margin_seconds = 0.03

    kept: list[NoteEvent] = []
    for note in notes:
        first = max(0, int((note.start - margin_seconds) / frame_seconds))
        last = min(
            len(rms),
            max(first + 1, int(np.ceil((note.end + margin_seconds) / frame_seconds)) + 1),
        )
        if first < len(rms) and float(np.max(rms[first:last])) >= threshold:
            kept.append(note)
    return kept


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

        # Register correction is an octave operation, not a theory operation:
        # fold first while preserving the detected pitch class.  Previously a
        # D#1 (MIDI 27) fell below the E1 boundary and could be snapped to E1.
        folded_pitch = _fold_pitch_to_register(note.pitch, low, high, previous_pitch)
        if folded_pitch % 12 in key_pcs:
            # in key: trust the evidence pitch class, including passing tones
            pitch = folded_pitch
        else:
            allowed = _allowed_pcs(segment, key_pcs, on_beat)
            pitch = _snap_pitch(folded_pitch, allowed, low, high, previous_pitch)

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


def _fold_pitch_to_register(
    pitch: int,
    low: int,
    high: int,
    previous: int | None = None,
) -> int:
    """Move a pitch by whole octaves into ``low..high``.

    Pitch class is an invariant.  The closest octave to the observation wins;
    melodic continuity is only a tie-breaker, so a previous note can never
    turn (for example) D# into E.
    """
    if low > high:
        raise ValueError("low must not be greater than high")
    candidates = [candidate for candidate in range(low, high + 1) if candidate % 12 == pitch % 12]
    if not candidates:
        # A range narrower than an octave may not contain the pitch class.  It
        # is impossible to satisfy both constraints; retain the closest bound
        # rather than returning an out-of-range note.
        return min((low, high), key=lambda candidate: abs(candidate - pitch))
    return min(
        candidates,
        key=lambda candidate: (
            abs(candidate - pitch),
            abs(candidate - previous) if previous is not None else 0,
            candidate,
        ),
    )


def _root_safe_bass(
    notes: list[NoteEvent],
    segments: list[ChordSegment],
    low: int,
    high: int,
) -> list[NoteEvent]:
    """Retain a cleaned line's rhythm while replacing pitches with roots."""
    result: list[NoteEvent] = []
    previous_pitch: int | None = None
    for note in notes:
        segment = chord_at_time(segments, note.start)
        if segment is None:
            pitch = _fold_pitch_to_register(note.pitch, low, high, previous_pitch)
        else:
            anchor = previous_pitch if previous_pitch is not None else note.pitch
            pitch = _to_register(segment.root_pc, low, high, anchor)
        result.append(NoteEvent(note.start, note.end, pitch, note.velocity))
        previous_pitch = pitch
    return result


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
