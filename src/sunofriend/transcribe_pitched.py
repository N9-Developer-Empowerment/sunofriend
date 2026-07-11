"""Pitched stem (keys / synth / bass) -> MIDI notes.

Primary engine: Spotify basic-pitch (polyphonic, ML). Bass combines its event
evidence with librosa pYIN and falls back to either engine independently.
Output is plain NoteEvent lists in seconds.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import ChordSegment, NoteEvent

# Sensible per-kind ranges (Hz) to stop octave errors / rumble artifacts.
_KIND_FREQS = {
    # B0..E3.  Letting a monophonic bass tracker search to 500 Hz makes it
    # prefer bright upper harmonics (often B4 in the Lidl stem) over the bass
    # fundamental and then fold that error into a plausible-looking octave.
    "bass": (30.0, 170.0),
    "keys": (60.0, 2500.0),
    "synth": (40.0, 3000.0),
}


def transcribe_pitched_stem(
    path: str,
    kind: str = "keys",
    onset_threshold: float = 0.5,
    frame_threshold: float = 0.3,
    min_note_ms: float = 60.0,
) -> list[NoteEvent]:
    if kind == "bass":
        return _transcribe_bass_hybrid(
            path,
            onset_threshold=onset_threshold,
            frame_threshold=frame_threshold,
            min_note_ms=min_note_ms,
        )
    try:
        return _basic_pitch_notes(path, kind, onset_threshold, frame_threshold, min_note_ms)
    except ImportError:
        raise


def _transcribe_bass_hybrid(
    path: str,
    *,
    onset_threshold: float,
    frame_threshold: float,
    min_note_ms: float,
) -> list[NoteEvent]:
    """Combine polyphonic ML hypotheses with a monophonic f0 contour.

    Either engine can be absent or fail on a particular machine.  A usable
    result from the other engine is still returned; when both work, dynamic
    programming selects the globally coherent source-supported path.
    """
    basic_notes: list[NoteEvent] = []
    pyin_notes: list[NoteEvent] = []
    basic_error: Exception | None = None
    pyin_error: Exception | None = None

    try:
        basic_notes = _basic_pitch_notes(
            path,
            "bass",
            onset_threshold,
            frame_threshold,
            min_note_ms,
        )
    except Exception as exc:  # optional ML inference must fail soft for bass
        basic_error = exc

    try:
        pyin_notes = _pyin_notes(path)
    except Exception as exc:  # librosa may also be optional in minimal installs
        pyin_error = exc

    if basic_notes or pyin_notes:
        return select_bass_contour(basic_notes, pyin_notes)
    if basic_error is not None and pyin_error is not None:
        raise RuntimeError(
            "Bass transcription failed in both Basic Pitch "
            f"({type(basic_error).__name__}: {basic_error}) and pYIN "
            f"({type(pyin_error).__name__}: {pyin_error})"
        ) from pyin_error
    return []


def _basic_pitch_notes(
    path: str, kind: str, onset_threshold: float, frame_threshold: float, min_note_ms: float
) -> list[NoteEvent]:
    from basic_pitch.inference import predict

    fmin, fmax = _KIND_FREQS.get(kind, (30.0, 3000.0))
    _, _, note_events = predict(
        path,
        model_or_model_path=_model_path(),
        onset_threshold=onset_threshold,
        frame_threshold=frame_threshold,
        minimum_note_length=min_note_ms,
        minimum_frequency=fmin,
        maximum_frequency=fmax,
        melodia_trick=True,
        multiple_pitch_bends=False,
    )
    notes = [
        NoteEvent(
            start=float(start),
            end=float(end),
            pitch=int(pitch),
            velocity=max(1, min(127, int(round(float(amplitude) * 127)))),
        )
        for start, end, pitch, amplitude, *_ in note_events
    ]
    notes.sort(key=lambda n: (n.start, n.pitch))
    notes = _drop_octave_ghosts(notes)
    notes = _merge_split_notes(notes)
    # Merging same-pitch fragments can reveal that a short octave candidate is
    # nested in a longer fundamental even when the pre-merge events did not
    # overlap enough to classify it as a ghost.
    notes = _drop_octave_ghosts(notes)
    return notes


@dataclass(frozen=True)
class _TaggedBassNote:
    source: str
    note: NoteEvent


@dataclass(frozen=True)
class _BassCandidate:
    pitch: int
    start: float
    end: float
    velocity: int
    emission: float
    sources: frozenset[str]


def select_bass_contour(
    basic_notes: list[NoteEvent],
    pyin_notes: list[NoteEvent],
    *,
    low: int = 23,
    high: int = 52,
    onset_tolerance: float = 0.11,
) -> list[NoteEvent]:
    """Select a monophonic bass path without assuming the lowest pitch wins.

    Basic Pitch is good at attacks and durations but can emit fundamental,
    subharmonic and harmonic candidates together.  pYIN supplies an
    independent monophonic contour.  Notes that both engines place in the same
    octave receive the strongest emission score; transition costs discourage
    unsupported octave flips and implausibly jagged motion.  This is a small
    Viterbi-style decoder over onset groups and has no audio dependencies,
    which also makes its behaviour directly testable.
    """
    if low > high:
        raise ValueError("low must not be greater than high")
    if onset_tolerance < 0:
        raise ValueError("onset_tolerance must be non-negative")

    if not basic_notes and not pyin_notes:
        return []

    if basic_notes:
        # Basic Pitch supplies event boundaries.  pYIN is independent pitch
        # evidence at those events, not a second onset detector: using every
        # short pYIN harmonic fragment as a new event more than doubled the
        # Lidl candidate count.  Only exact, temporally overlapping pYIN
        # support is attached to a Basic Pitch onset group.
        groups = _group_tagged_bass_onsets(
            [_TaggedBassNote("basic", note) for note in basic_notes],
            onset_tolerance,
        )
        for pyin_note in pyin_notes:
            folded_pyin = _fold_pitch_class(pyin_note.pitch, low, high)
            choices: list[tuple[float, float, int]] = []
            for index, group in enumerate(groups):
                matching = [
                    item.note
                    for item in group
                    if _fold_pitch_class(item.note.pitch, low, high) == folded_pyin
                ]
                if not matching:
                    continue
                overlap = max(
                    0.0,
                    max(
                        min(note.end, pyin_note.end) - max(note.start, pyin_note.start)
                        for note in matching
                    ),
                )
                onset_distance = min(abs(note.start - pyin_note.start) for note in matching)
                if overlap > 0.02 or onset_distance <= onset_tolerance:
                    choices.append((overlap, -onset_distance, index))
            if choices:
                _, _, best_group = max(choices)
                groups[best_group].append(_TaggedBassNote("pyin", pyin_note))
    else:
        groups = _group_tagged_bass_onsets(
            [_TaggedBassNote("pyin", note) for note in pyin_notes],
            onset_tolerance,
        )
    states = [_bass_candidates(group, low, high) for group in groups]
    states = [candidates for candidates in states if candidates]
    if not states:
        return []

    # Maximise evidence support minus melodic transition cost.
    scores: list[list[float]] = []
    back: list[list[int]] = []
    scores.append([candidate.emission for candidate in states[0]])
    back.append([-1] * len(states[0]))
    for index in range(1, len(states)):
        row_scores: list[float] = []
        row_back: list[int] = []
        for candidate in states[index]:
            options = [
                (
                    scores[index - 1][previous_index]
                    - _bass_transition_cost(previous, candidate)
                    + candidate.emission,
                    previous_index,
                )
                for previous_index, previous in enumerate(states[index - 1])
            ]
            best_score, best_index = max(options, key=lambda item: (item[0], -item[1]))
            row_scores.append(best_score)
            row_back.append(best_index)
        scores.append(row_scores)
        back.append(row_back)

    state_index = max(
        range(len(states[-1])),
        key=lambda candidate_index: (scores[-1][candidate_index], -candidate_index),
    )
    path: list[_BassCandidate] = []
    for group_index in range(len(states) - 1, -1, -1):
        path.append(states[group_index][state_index])
        state_index = back[group_index][state_index]
    path.reverse()

    notes: list[NoteEvent] = []
    for candidate in path:
        start = max(0.0, candidate.start)
        end = max(start + 0.03, candidate.end)
        note = NoteEvent(start, end, candidate.pitch, candidate.velocity)
        if notes and note.start < notes[-1].end:
            previous = notes[-1]
            clipped_end = max(previous.start + 0.03, note.start)
            notes[-1] = NoteEvent(previous.start, clipped_end, previous.pitch, previous.velocity)
        notes.append(note)
    return _merge_split_notes(notes)


def _group_tagged_bass_onsets(
    notes: list[_TaggedBassNote],
    tolerance: float,
) -> list[list[_TaggedBassNote]]:
    groups: list[list[_TaggedBassNote]] = []
    group_anchor = 0.0
    for tagged in sorted(notes, key=lambda item: (item.note.start, item.note.pitch, item.source)):
        if not groups or tagged.note.start - group_anchor > tolerance:
            groups.append([tagged])
            group_anchor = tagged.note.start
        else:
            groups[-1].append(tagged)
    return groups


def _bass_candidates(
    group: list[_TaggedBassNote],
    low: int,
    high: int,
) -> list[_BassCandidate]:
    by_pitch: dict[int, list[_TaggedBassNote]] = {}
    for tagged in group:
        pitch = _fold_pitch_class(tagged.note.pitch, low, high)
        by_pitch.setdefault(pitch, []).append(tagged)

    candidates: list[_BassCandidate] = []
    for pitch, support in sorted(by_pitch.items()):
        source_velocities = {
            source: max(item.note.velocity for item in support if item.source == source)
            for source in {item.source for item in support}
        }
        sources = frozenset(source_velocities)
        emission = 0.0
        if "basic" in sources:
            emission += 0.62 + 0.38 * source_velocities["basic"] / 127.0
        if "pyin" in sources:
            # A monophonic f0 observation is particularly valuable when Basic
            # Pitch offers simultaneous octave/subharmonic alternatives.
            emission += 0.95 + 0.25 * source_velocities["pyin"] / 127.0
        if sources == {"basic", "pyin"}:
            emission += 0.75

        preferred = [item.note for item in support if item.source == "basic"] or [
            item.note for item in support
        ]
        representative = max(preferred, key=lambda note: (note.velocity, note.end - note.start))
        start = min(item.note.start for item in support)
        end = max(item.note.end for item in support)
        velocity = max(item.note.velocity for item in support)
        # Reward stable, non-fragmentary evidence slightly, without allowing a
        # long harmonic ghost to dominate agreement between both engines.
        emission += min(0.12, max(0.0, representative.end - representative.start) * 0.08)
        candidates.append(
            _BassCandidate(pitch, start, end, velocity, emission, sources)
        )

    # Treat octave as a path-level decision.  A tracker often emits the right
    # pitch class in the wrong octave for one event; without octave-equivalent
    # states the decoder is forced to accept that jump.  Single-engine evidence
    # gets a modest alternative, while exact Basic Pitch+pYIN octave agreement
    # remains expensive to override and can therefore express a real leap.
    observed_pitches = {candidate.pitch for candidate in candidates}
    alternatives: dict[int, _BassCandidate] = {}
    for candidate in candidates:
        if candidate.sources == {"basic", "pyin"}:
            octave_penalty = 1.85
        elif candidate.sources == {"pyin"}:
            octave_penalty = 0.80
        else:
            octave_penalty = 0.52
        for alternate_pitch in range(low, high + 1):
            if alternate_pitch % 12 != candidate.pitch % 12:
                continue
            if alternate_pitch in observed_pitches or alternate_pitch == candidate.pitch:
                continue
            octaves = abs(alternate_pitch - candidate.pitch) / 12.0
            alternate = _BassCandidate(
                alternate_pitch,
                candidate.start,
                candidate.end,
                candidate.velocity,
                candidate.emission - octave_penalty * octaves,
                candidate.sources,
            )
            previous = alternatives.get(alternate_pitch)
            if previous is None or alternate.emission > previous.emission:
                alternatives[alternate_pitch] = alternate
    return sorted([*candidates, *alternatives.values()], key=lambda candidate: candidate.pitch)


def _bass_transition_cost(previous: _BassCandidate, current: _BassCandidate) -> float:
    jump = abs(current.pitch - previous.pitch)
    cost = jump * 0.07
    if jump > 7:
        cost += (jump - 7) * 0.08
    if jump >= 12:
        cost += 0.45
    if jump in (0, 1, 2, 3, 4, 5, 7):
        cost -= 0.12
    # Large motion is less suspect after a real silence than in a legato line.
    silence = max(0.0, current.start - previous.end)
    if silence > 0.35:
        cost *= max(0.35, 1.0 - min(0.65, silence * 0.3))
    return max(0.0, cost)


def _fold_pitch_class(pitch: int, low: int, high: int) -> int:
    """Fold by octaves into a register, retaining pitch class exactly."""
    candidates = [candidate for candidate in range(low, high + 1) if candidate % 12 == pitch % 12]
    if not candidates:
        return min((low, high), key=lambda candidate: abs(candidate - pitch))
    return min(candidates, key=lambda candidate: (abs(candidate - pitch), candidate))


@dataclass(frozen=True)
class KeysRoleSeparation:
    """Auditionable voices recovered from a dense keys transcription."""

    melody: list[NoteEvent]
    accompaniment: list[NoteEvent]
    uncertain: list[NoteEvent]


def separate_keys_roles(
    notes: list[NoteEvent],
    segments: list[ChordSegment] | None = None,
    *,
    onset_tolerance: float = 0.08,
    melody_floor: int = 60,
) -> KeysRoleSeparation:
    """Separate dense keys evidence without rewriting its pitches.

    Melody selection combines relative velocity (salience), register,
    continuity and local polyphony.  When a chord chart is supplied it is used
    *only* to decide whether a remaining note is safe accompaniment; a melodic
    chromatic or passing tone is therefore retained unchanged.  Low-salience
    and chart-inconsistent leftovers are made explicit as ``uncertain`` rather
    than mixed into the principal keyboard track.
    """
    if onset_tolerance < 0:
        raise ValueError("onset_tolerance must be non-negative")

    groups = _group_note_onsets(notes, onset_tolerance)
    melody: list[NoteEvent] = []
    accompaniment: list[NoteEvent] = []
    uncertain: list[NoteEvent] = []
    previous_melody: NoteEvent | None = None

    for group in groups:
        max_velocity = max(note.velocity for note in group)
        sorted_velocities = sorted(note.velocity for note in group)
        median_velocity = sorted_velocities[len(sorted_velocities) // 2]
        melody_candidates = [
            note
            for note in group
            if note.pitch >= melody_floor
            or (
                previous_melody is not None
                and note.pitch >= melody_floor - 5
                and abs(note.pitch - previous_melody.pitch) <= 12
            )
        ]

        selected: NoteEvent | None = None
        if melody_candidates:
            ranked = sorted(
                melody_candidates,
                key=lambda note: (
                    _melody_role_score(note, max_velocity, previous_melody),
                    note.velocity,
                    note.pitch,
                ),
                reverse=True,
            )
            best = ranked[0]
            close_to_previous = (
                previous_melody is not None
                and best.start - previous_melody.end <= 0.8
                and abs(best.pitch - previous_melody.pitch) <= 7
            )
            if len(group) == 1:
                prominent = best.velocity >= 45
            else:
                prominent = (
                    best.velocity >= max(35, round(median_velocity * 1.1))
                    and best.velocity >= max_velocity * 0.8
                )
                prominent = prominent or (
                    close_to_previous and best.velocity >= max_velocity * 0.72
                )
            if prominent:
                selected = best
                melody.append(best)
                previous_melody = best

        polyphonic = len(group) > 1
        for note in group:
            if note is selected:
                continue
            sufficiently_salient = note.velocity >= max(24, round(max_velocity * 0.28))
            note_chart_pcs = _chart_pcs_at(segments, note.start)
            chart_safe = note_chart_pcs is None or note.pitch % 12 in note_chart_pcs
            # Without a chart, only polyphonic/sustained material is labelled
            # accompaniment.  A lone weak note remains available for review.
            texture_safe = polyphonic or note.end - note.start >= 0.45
            if sufficiently_salient and chart_safe and texture_safe:
                accompaniment.append(note)
            else:
                uncertain.append(note)

    key = lambda note: (note.start, note.pitch, note.end, note.velocity)
    return KeysRoleSeparation(
        melody=sorted(melody, key=key),
        accompaniment=sorted(accompaniment, key=key),
        uncertain=sorted(uncertain, key=key),
    )


def _group_note_onsets(notes: list[NoteEvent], tolerance: float) -> list[list[NoteEvent]]:
    groups: list[list[NoteEvent]] = []
    anchor = 0.0
    for note in sorted(notes, key=lambda item: (item.start, item.pitch, -item.velocity)):
        if not groups or note.start - anchor > tolerance:
            groups.append([note])
            anchor = note.start
        else:
            groups[-1].append(note)
    return groups


def _melody_role_score(
    note: NoteEvent,
    max_velocity: int,
    previous: NoteEvent | None,
) -> float:
    salience = note.velocity / max(1, max_velocity)
    register = max(0.0, min(1.0, (note.pitch - 55) / 24.0))
    score = salience * 1.7 + register * 0.55
    if previous is not None:
        gap = max(0.0, note.start - previous.end)
        if gap <= 0.8:
            interval = abs(note.pitch - previous.pitch)
            score += max(-0.7, 0.8 - interval * 0.10)
    duration = note.end - note.start
    if duration > 1.5:
        score -= min(0.35, (duration - 1.5) * 0.1)
    return score


def _chart_pcs_at(
    segments: list[ChordSegment] | None,
    time_seconds: float,
) -> set[int] | None:
    if not segments:
        return None
    for segment in segments:
        if segment.start <= time_seconds < segment.end:
            return set(segment.pitch_classes)
    if time_seconds >= segments[-1].end:
        return set(segments[-1].pitch_classes)
    return None


def _merge_split_notes(notes: list[NoteEvent], max_gap: float = 0.06, fragment_len: float = 0.35) -> list[NoteEvent]:
    """Join same-pitch notes separated by a tiny gap (transcription splits).

    Only merges when one side is a short fragment — a re-struck sustained note
    (e.g. a common tone across two chords) is a real musical event, not a split.
    """
    merged: list[NoteEvent] = []
    for note in sorted(notes, key=lambda n: (n.pitch, n.start)):
        is_fragment = (note.end - note.start) < fragment_len or (
            merged and merged[-1].pitch == note.pitch and (merged[-1].end - merged[-1].start) < fragment_len
        )
        if (
            merged
            and merged[-1].pitch == note.pitch
            and note.start - merged[-1].end <= max_gap
            and is_fragment
        ):
            prev = merged.pop()
            merged.append(
                NoteEvent(prev.start, max(prev.end, note.end), prev.pitch, max(prev.velocity, note.velocity))
            )
        else:
            merged.append(note)
    return sorted(merged, key=lambda n: (n.start, n.pitch))


def _drop_octave_ghosts(notes: list[NoteEvent], ratio: float = 0.72) -> list[NoteEvent]:
    """Drop notes that are octave duplicates of a much louder simultaneous note.

    Sub-octave and first-harmonic ghosts are the dominant basic-pitch error on
    synth/keys stems. Genuine octave doublings survive because their levels
    are comparable (velocity ratio above `ratio`).
    """
    drop: set[int] = set()
    for i, a in enumerate(notes):
        for j, b in enumerate(notes):
            if i == j or j in drop:
                continue
            if abs(a.pitch - b.pitch) not in (12, 24):
                continue
            overlap = min(a.end, b.end) - max(a.start, b.start)
            if overlap < 0.6 * (a.end - a.start):
                continue
            if a.velocity < b.velocity * ratio:
                drop.add(i)
                break
    return [n for i, n in enumerate(notes) if i not in drop]


def _model_path():
    """Prefer the ONNX model (loads everywhere); fall back to the default."""
    from basic_pitch import ICASSP_2022_MODEL_PATH

    try:
        import onnxruntime  # noqa: F401
        from basic_pitch import build_icassp_2022_model_path, FilenameSuffix

        return build_icassp_2022_model_path(FilenameSuffix.onnx)
    except Exception:
        return ICASSP_2022_MODEL_PATH


def _keep_lowest_voice(notes: list[NoteEvent]) -> list[NoteEvent]:
    """Bass stems are monophonic in practice: drop overlapping higher notes."""
    kept: list[NoteEvent] = []
    for note in notes:
        overlapping = [k for k in kept if k.end > note.start + 0.02]
        if overlapping and all(k.pitch <= note.pitch for k in overlapping):
            continue
        kept = [k for k in kept if not (k.start >= note.start - 0.02 and k.pitch > note.pitch and k.end > note.start)]
        kept.append(note)
    return sorted(kept, key=lambda n: n.start)


def _pyin_notes(path: str, sr: int = 22050, hop: int = 256) -> list[NoteEvent]:
    """Monophonic fallback (no ML): pyin f0 track segmented into notes."""
    import librosa
    import numpy as np

    y, _ = librosa.load(path, sr=sr, mono=True)
    if y.size == 0:
        return []
    bass_fmin, bass_fmax = _KIND_FREQS["bass"]
    f0, voiced, _ = librosa.pyin(
        y,
        fmin=bass_fmin,
        fmax=bass_fmax,
        sr=sr,
        hop_length=hop,
        fill_na=np.nan,
    )
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    times = librosa.times_like(f0, sr=sr, hop_length=hop)

    notes: list[NoteEvent] = []
    current_pitch: int | None = None
    start_time = 0.0
    strengths: list[float] = []

    def flush(end_time: float) -> None:
        nonlocal current_pitch, strengths
        if current_pitch is not None and end_time - start_time >= 0.06:
            peak = max(strengths) if strengths else 0.1
            vel = max(30, min(127, int(round(peak / (np.max(rms) + 1e-9) * 127))))
            notes.append(NoteEvent(start=start_time, end=end_time, pitch=current_pitch, velocity=vel))
        current_pitch = None
        strengths = []

    for i, t in enumerate(times):
        pitch = None
        if voiced is not None and i < len(voiced) and voiced[i] and not np.isnan(f0[i]):
            pitch = int(round(librosa.hz_to_midi(float(f0[i]))))
        if pitch != current_pitch:
            flush(t)
            if pitch is not None:
                current_pitch = pitch
                start_time = t
        if pitch is not None and i < len(rms):
            strengths.append(float(rms[i]))
    flush(float(times[-1]) if len(times) else 0.0)
    return notes
