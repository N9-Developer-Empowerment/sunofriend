"""Feature-space comparison between an original stem and a rendered candidate.

Raw waveforms are never compared directly (GM SoundFont timbre != stem timbre).
Instead:
  drums  -> onset lists (time + strength), matched within a tolerance window
  pitched-> chroma similarity + onset match

The diff (missed / extra / mistimed) is what drives the refinement loop.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import NoteEvent

SR = 22050
HOP = 128


@dataclass(frozen=True)
class Onset:
    time: float
    strength: float


@dataclass
class DrumDiff:
    matched: list[tuple[float, float]] = field(default_factory=list)  # (ref_time, cand_time)
    missed: list[Onset] = field(default_factory=list)                 # in ref, not in render
    extra: list[float] = field(default_factory=list)                  # in render, not in ref
    f_measure: float = 0.0
    mean_abs_offset: float = 0.0

    @property
    def score(self) -> float:
        timing_penalty = min(self.mean_abs_offset / 0.05, 1.0) * 0.15
        return max(0.0, self.f_measure - timing_penalty)


@dataclass
class PitchedDiff:
    chroma_similarity: float = 0.0
    onset_f_measure: float = 0.0
    spurious_notes: list[int] = field(default_factory=list)  # indices into candidate notes
    edits: list[PitchedEdit] = field(default_factory=list)
    evidence_count: int = 0
    evidence_error: str | None = None

    @property
    def score(self) -> float:
        return 0.7 * self.chroma_similarity + 0.3 * self.onset_f_measure


@dataclass(frozen=True)
class PitchedNoteEvidence:
    """A note hypothesis corroborated by features from the original stem.

    ``note`` comes from a deliberately sensitive transcription pass.  It is
    not trusted on its own: ``spectral_support`` measures energy at the exact
    MIDI pitch and ``onset_strength`` records an independently detected stem
    onset.  Keeping these values explicit prevents the refinement loop from
    inventing notes merely because there is a gap in the candidate MIDI.
    """

    note: NoteEvent
    confidence: float
    spectral_support: float
    onset_strength: float | None = None
    sources: tuple[str, ...] = ("transcription", "spectrum")

    @property
    def safe_to_add(self) -> bool:
        required = {"transcription", "spectrum", "onset"}
        return (
            required.issubset(self.sources)
            and self.confidence >= 0.72
            and self.spectral_support >= 0.12
            and self.onset_strength is not None
            and self.onset_strength >= 0.15
            and self.note.end - self.note.start >= 0.06
        )


@dataclass(frozen=True)
class PitchedEdit:
    """A deterministic, auditable change proposed for pitched MIDI."""

    action: str  # ``repair`` or ``add``
    note_index: int | None
    before: NoteEvent | None
    after: NoteEvent
    fields: tuple[str, ...]
    confidence: float
    rationale: str


@dataclass
class PitchedReference:
    """Reusable stem evidence so expensive spectral work happens only once."""

    notes: list[PitchedNoteEvidence] = field(default_factory=list)
    spectrum: Any | None = field(default=None, repr=False)
    error: str | None = None


def extract_onsets(path: str, delta: float = 0.18) -> list[Onset]:
    import librosa
    import numpy as np

    y, sr = librosa.load(path, sr=SR, mono=True)
    if y.size == 0 or float(np.max(np.abs(y))) < 1e-4:
        return []
    y = y / float(np.max(np.abs(y)))
    pad = int(0.05 * sr)
    y = np.pad(y, (pad, 0))
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP, aggregate=np.median)
    from .transcribe_drums import _clip_envelope_spikes

    env = _clip_envelope_spikes(env)
    frames = librosa.onset.onset_detect(
        onset_envelope=env, sr=sr, hop_length=HOP, backtrack=False,
        delta=delta, pre_max=6, post_max=6, pre_avg=12, post_avg=12, wait=4,
    )
    times = np.maximum(librosa.frames_to_time(frames, sr=sr, hop_length=HOP) - (pad / sr), 0.0)
    peak_env = float(np.max(env)) if env.size else 1.0
    return [Onset(time=float(t), strength=float(env[f]) / (peak_env + 1e-9)) for t, f in zip(times, frames)]


def diff_drums(ref: list[Onset], rendered: list[Onset], tolerance: float = 0.035) -> DrumDiff:
    diff = DrumDiff()
    used = [False] * len(rendered)
    for r in ref:
        best_j, best_d = -1, tolerance
        for j, c in enumerate(rendered):
            if used[j]:
                continue
            d = abs(c.time - r.time)
            if d <= best_d:
                best_j, best_d = j, d
        if best_j >= 0:
            used[best_j] = True
            diff.matched.append((r.time, rendered[best_j].time))
        else:
            diff.missed.append(r)
    diff.extra = [c.time for j, c in enumerate(rendered) if not used[j]]

    tp = len(diff.matched)
    precision = tp / max(1, tp + len(diff.extra))
    recall = tp / max(1, tp + len(diff.missed))
    diff.f_measure = 0.0 if tp == 0 else 2 * precision * recall / (precision + recall)
    diff.mean_abs_offset = (
        sum(abs(a - b) for a, b in diff.matched) / len(diff.matched)
        if diff.matched else 0.0
    )
    return diff


def chroma_matrix(path: str) -> Any:
    import librosa
    import numpy as np

    y, sr = librosa.load(path, sr=SR, mono=True)
    if y.size == 0:
        return np.zeros((12, 1))
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=512)
    return chroma / (np.linalg.norm(chroma, axis=0, keepdims=True) + 1e-9)


def analyze_pitched_reference(
    path: str,
    kind: str,
    ref_onsets: list[Onset] | None = None,
) -> PitchedReference:
    """Build conservative, reusable note evidence from the original stem.

    A sensitive transcription pass is useful for finding notes omitted by the
    normal seed, but every result is checked against the exact semitone bin in
    the stem CQT.  Additions later require a third signal: an independently
    detected onset.  If the optional ML stack is unavailable this degrades to
    the original chroma-only refinement instead of making the listen command
    fail.
    """
    try:
        from .transcribe_pitched import transcribe_pitched_stem
        from .verify import StemSpectrum

        hypotheses = transcribe_pitched_stem(
            path,
            kind=kind,
            onset_threshold=0.35,
            frame_threshold=0.22,
            min_note_ms=50.0,
        )
        spectrum = StemSpectrum(path)
    except Exception as exc:  # optional refinement evidence must be fail-soft
        return PitchedReference(error=f"{type(exc).__name__}: {exc}")

    onsets = ref_onsets or []
    evidence: list[PitchedNoteEvidence] = []
    for note in hypotheses:
        support = float(spectrum.note_support(note))
        if support < 0.08:
            continue

        nearest = min(onsets, key=lambda onset: abs(onset.time - note.start), default=None)
        if nearest is not None and abs(nearest.time - note.start) <= 0.09:
            onset_strength: float | None = nearest.strength
            sources = ("transcription", "spectrum", "onset")
            # The dedicated onset detector is the most accurate attack-time
            # evidence.  Duration remains grounded in the pitch tracker.
            duration = note.end - note.start
            aligned_start = max(0.0, nearest.time)
            aligned_note = NoteEvent(
                aligned_start,
                max(aligned_start + 0.03, aligned_start + duration),
                note.pitch,
                note.velocity,
            )
        else:
            onset_strength = None
            sources = ("transcription", "spectrum")
            aligned_note = note

        spectral_confidence = min(1.0, support / 0.18)
        transcription_confidence = min(1.0, max(0.0, note.velocity / 127.0))
        onset_confidence = min(1.0, max(0.0, onset_strength or 0.0))
        confidence = (
            0.55 * spectral_confidence
            + 0.25 * transcription_confidence
            + 0.20 * onset_confidence
        )
        evidence.append(
            PitchedNoteEvidence(
                note=aligned_note,
                confidence=min(1.0, confidence),
                spectral_support=support,
                onset_strength=onset_strength,
                sources=sources,
            )
        )

    evidence.sort(key=lambda item: (item.note.start, item.note.pitch, item.note.end))
    return PitchedReference(notes=evidence, spectrum=spectrum)


def propose_pitched_edits(
    candidate_notes: list[NoteEvent],
    evidence: list[PitchedNoteEvidence],
    candidate_support: list[float] | None = None,
    timing_tolerance: float = 0.14,
    *,
    allow_additions: bool = True,
    preserve_structure: bool = False,
) -> list[PitchedEdit]:
    """Return deterministic note additions and repairs supported by the stem.

    Exact-pitch notes are paired first.  Only then can a strong evidence note
    repair a one/two-semitone or octave error, which avoids turning a missing
    chord tone into an edit of a different, valid chord tone.  Unmatched
    evidence becomes an addition only when transcription, spectrum, and onset
    all agree *and* the caller's musical policy allows additions.

    ``preserve_structure`` is used for chart/theory-generated bass, lead,
    synth, and pad parts.  Spectral evidence may shape expression there, but it
    must not bypass the generator's key, chord, grid, register, density, or
    monophony decisions by inserting or moving notes.
    """
    candidates = list(candidate_notes)
    references = list(evidence)
    used_candidates: set[int] = set()
    used_evidence: set[int] = set()
    matches: list[tuple[int, int]] = []

    def temporal_match(candidate: NoteEvent, reference: NoteEvent) -> bool:
        start_delta = abs(candidate.start - reference.start)
        if start_delta <= timing_tolerance:
            return True
        overlap = min(candidate.end, reference.end) - max(candidate.start, reference.start)
        shorter = min(candidate.end - candidate.start, reference.end - reference.start)
        return start_delta <= 0.25 and shorter > 0 and overlap >= 0.6 * shorter

    def pair(exact_pitch: bool) -> None:
        for evidence_index in sorted(
            range(len(references)),
            key=lambda i: (
                references[i].note.start,
                references[i].note.pitch,
                -references[i].confidence,
                i,
            ),
        ):
            if evidence_index in used_evidence:
                continue
            item = references[evidence_index]
            options: list[tuple[float, float, int]] = []
            for candidate_index, candidate in enumerate(candidates):
                if candidate_index in used_candidates or not temporal_match(candidate, item.note):
                    continue
                pitch_delta = abs(candidate.pitch - item.note.pitch)
                if exact_pitch:
                    if pitch_delta != 0:
                        continue
                else:
                    if (
                        pitch_delta not in {1, 2, 12, 24}
                        or item.confidence < 0.78
                        or item.spectral_support < 0.12
                    ):
                        continue
                    if candidate_support is not None and candidate_index < len(candidate_support):
                        old_support = max(0.0, float(candidate_support[candidate_index]))
                        if item.spectral_support < max(0.12, old_support * 1.35):
                            continue
                options.append(
                    (
                        abs(candidate.start - item.note.start),
                        abs((candidate.end - candidate.start) - (item.note.end - item.note.start)),
                        candidate_index,
                    )
                )
            if not options:
                continue
            _, _, candidate_index = min(options)
            used_candidates.add(candidate_index)
            used_evidence.add(evidence_index)
            matches.append((candidate_index, evidence_index))

    pair(exact_pitch=True)
    if not preserve_structure:
        pair(exact_pitch=False)

    edits: list[PitchedEdit] = []
    for candidate_index, evidence_index in sorted(matches):
        before = candidates[candidate_index]
        item = references[evidence_index]
        target = item.note
        fields: list[str] = []

        pitch = before.pitch
        if not preserve_structure and target.pitch != before.pitch:
            pitch = target.pitch
            fields.append("octave" if abs(target.pitch - before.pitch) in {12, 24} else "pitch")

        start = before.start
        duration = before.end - before.start
        start_delta = abs(target.start - before.start)
        if (
            not preserve_structure
            and "onset" in item.sources
            and item.confidence >= 0.78
            and (item.onset_strength or 0.0) >= 0.15
            and 0.008 <= start_delta <= timing_tolerance
        ):
            start = target.start
            fields.append("timing")

        target_duration = target.end - target.start
        duration_delta = abs(target_duration - duration)
        ratio = target_duration / max(duration, 1e-9)
        if (
            not preserve_structure
            and item.confidence >= 0.68
            and duration_delta >= 0.02
            and 0.5 <= ratio <= 2.0
        ):
            duration = target_duration
            fields.append("duration")

        velocity = before.velocity
        if item.confidence >= 0.62 and abs(target.velocity - before.velocity) >= 6:
            velocity = max(1, min(127, target.velocity))
            fields.append("velocity")

        # MIDI cannot sustain two independent instances of the same
        # channel/pitch.  Refinement normalizes retriggers by ending the first
        # note at the next onset, so do not repeatedly propose a duration that
        # would only be truncated back to its current value on every loop.
        if "duration" in fields:
            later_same_pitch = [
                candidate.start
                for index, candidate in enumerate(candidates)
                if index != candidate_index
                and candidate.pitch == pitch
                and candidate.start > start + 1e-9
            ]
            if later_same_pitch:
                duration = min(duration, min(later_same_pitch) - start)
            if abs(duration - (before.end - before.start)) < 0.008:
                fields.remove("duration")

        if not fields:
            continue
        after = NoteEvent(
            start=max(0.0, start),
            end=max(start + 0.03, start + duration),
            pitch=max(0, min(127, pitch)),
            velocity=velocity,
        )
        edits.append(
            PitchedEdit(
                action="repair",
                note_index=candidate_index,
                before=before,
                after=after,
                fields=tuple(fields),
                confidence=item.confidence,
                rationale=_pitched_rationale(item, fields),
            )
        )

    if allow_additions and not preserve_structure:
        for evidence_index, item in enumerate(references):
            if evidence_index in used_evidence or not item.safe_to_add:
                continue
            edits.append(
                PitchedEdit(
                    action="add",
                    note_index=None,
                    before=None,
                    after=item.note,
                    fields=("note",),
                    confidence=item.confidence,
                    rationale=_pitched_rationale(item, ["missed note"]),
                )
            )

    return sorted(
        edits,
        key=lambda edit: (
            edit.after.start,
            edit.after.pitch,
            0 if edit.action == "repair" else 1,
            edit.note_index if edit.note_index is not None else -1,
        ),
    )


def _pitched_rationale(item: PitchedNoteEvidence, fields: list[str]) -> str:
    onset = (
        f", onset={item.onset_strength:.2f}"
        if item.onset_strength is not None else ""
    )
    return (
        f"stem evidence ({'+'.join(item.sources)}; "
        f"spectral_support={item.spectral_support:.3f}{onset}) supports "
        f"{', '.join(fields)}"
    )


def pitched_edit_detail(diff: PitchedDiff, limit: int = 24) -> list[dict[str, Any]]:
    """JSON-ready audit trail for an iteration report."""
    details = []
    for edit in diff.edits[:limit]:
        details.append(
            {
                "action": edit.action,
                "note_index": edit.note_index,
                "fields": list(edit.fields),
                "target": {
                    "start": round(edit.after.start, 4),
                    "end": round(edit.after.end, 4),
                    "pitch": edit.after.pitch,
                    "velocity": edit.after.velocity,
                },
                "confidence": round(edit.confidence, 3),
                "rationale": edit.rationale,
            }
        )
    return details


def diff_pitched(
    ref_path: str,
    rendered_path: str,
    candidate_notes,
    tolerance: float = 0.05,
    ref_chroma: Any | None = None,
    ref_onsets: list[Onset] | None = None,
    ref_evidence: PitchedReference | None = None,
    *,
    allow_additions: bool = True,
    preserve_structure: bool = False,
) -> PitchedDiff:
    import numpy as np

    if ref_chroma is None:
        ref_chroma = chroma_matrix(ref_path)
    cand_chroma = chroma_matrix(rendered_path)
    frames = min(ref_chroma.shape[1], cand_chroma.shape[1])
    similarity = float(
        np.mean(np.sum(ref_chroma[:, :frames] * cand_chroma[:, :frames], axis=0))
    ) if frames else 0.0

    if ref_onsets is None:
        ref_onsets = extract_onsets(ref_path, delta=0.12)
    cand_onsets = extract_onsets(rendered_path, delta=0.12)
    onset_f = diff_drums(ref_onsets, cand_onsets, tolerance=tolerance).f_measure

    candidate_support = None
    if ref_evidence is not None and ref_evidence.spectrum is not None:
        candidate_support = [ref_evidence.spectrum.note_support(note) for note in candidate_notes]
    edits = propose_pitched_edits(
        candidate_notes,
        ref_evidence.notes if ref_evidence is not None else [],
        candidate_support=candidate_support,
        allow_additions=allow_additions,
        preserve_structure=preserve_structure,
    )
    repaired = {edit.note_index for edit in edits if edit.action == "repair"}
    spurious = [] if preserve_structure else [
        index for index in _spurious_note_indices(ref_chroma, candidate_notes)
        if index not in repaired
    ]
    return PitchedDiff(
        chroma_similarity=similarity,
        onset_f_measure=onset_f,
        spurious_notes=spurious,
        edits=edits,
        evidence_count=len(ref_evidence.notes) if ref_evidence is not None else 0,
        evidence_error=ref_evidence.error if ref_evidence is not None else None,
    )


def _spurious_note_indices(ref_chroma: Any, notes, frame_seconds: float = 512 / SR) -> list[int]:
    """Candidate notes whose pitch class has almost no energy in the stem while sounding."""
    spurious = []
    total_frames = ref_chroma.shape[1]
    for i, note in enumerate(notes):
        start_frame = int(note.start / frame_seconds)
        end_frame = min(total_frames, max(start_frame + 1, int(note.end / frame_seconds)))
        if start_frame >= total_frames:
            continue
        pc = note.pitch % 12
        energy = float(ref_chroma[pc, start_frame:end_frame].mean())
        if energy < 0.08:
            spurious.append(i)
    return spurious
