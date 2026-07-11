"""Independent, auditable stem-to-MIDI evaluation.

This module deliberately does not call the transcription/refinement onset
detector.  A candidate therefore cannot earn a perfect score merely by being
compared with the same observations that created it.  The evaluator derives a
separate reference from the WAV, matches MIDI events to that reference, and
reports timing, drum-family, and pitched-content diagnostics as plain,
serializable dataclasses.

The audio metrics require NumPy.  Reading a MIDI path additionally requires
the optional ``mido`` dependency; callers can always pass ``NoteEvent`` values
directly.
"""
from __future__ import annotations

import json
import math
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .models import NoteEvent


DRUM_KINDS = {"kick", "snare", "hat", "cymbals", "toms", "other_kit", "drums"}

# General MIDI percussion families.  The broad families are useful for mixed
# kit stems; callers may supply a narrower pitch_family_map (for example,
# {35: "kick_high", 36: "kick_deep"}) when a golden annotation distinguishes
# two samples from the same family.
GM_DRUM_FAMILIES: dict[str, frozenset[int]] = {
    "kick": frozenset({35, 36}),
    "snare": frozenset({37, 38, 39, 40}),
    "hat": frozenset({42, 44, 46}),
    "toms": frozenset({41, 43, 45, 47, 48, 50}),
    "cymbals": frozenset({49, 51, 52, 53, 55, 57, 59}),
}
V2_DRUM_PITCH_FAMILIES: dict[int, str] = {
    35: "kick_high",
    36: "kick_deep",
    38: "snare_body",
    40: "snare_bright",
    42: "hat_closed",
    46: "hat_open",
    41: "tom_floor",
    45: "tom_low",
    48: "tom_mid",
    50: "tom_high",
    49: "crash",
    51: "ride",
    39: "unknown",
}


def v2_pitch_family_map(kind: str) -> Mapping[int, str] | None:
    return V2_DRUM_PITCH_FAMILIES if kind.strip().lower() in DRUM_KINDS else None


@dataclass(frozen=True)
class ReferenceOnset:
    time: float
    strength: float
    tier: str  # ``strong`` or ``possible``


@dataclass(frozen=True)
class FamilyAnnotation:
    time: float
    family: str
    tier: str = "strong"


@dataclass(frozen=True)
class PrecisionRecall:
    reference_count: int
    candidate_count: int
    matched: int
    missed: int
    extra: int
    precision: float
    recall: float
    f1: float
    missed_times: tuple[float, ...] = ()
    extra_times: tuple[float, ...] = ()


@dataclass(frozen=True)
class SegmentDrift:
    index: int
    start_seconds: float
    end_seconds: float
    matched: int
    median_offset_ms: float | None


@dataclass(frozen=True)
class TimingMetrics:
    matched: int
    absolute_error_p50_ms: float | None
    absolute_error_p95_ms: float | None
    absolute_error_p99_ms: float | None
    signed_error_mean_ms: float | None
    signed_error_median_ms: float | None
    drift_ms: float | None
    drift_slope_ms_per_minute: float | None
    segments: tuple[SegmentDrift, ...]


@dataclass(frozen=True)
class OnsetMetrics:
    reference_strong_count: int
    reference_possible_count: int
    strong: PrecisionRecall
    possible: PrecisionRecall
    timing: TimingMetrics
    references: tuple[ReferenceOnset, ...]


@dataclass(frozen=True)
class DrumMetrics:
    pitch_counts: dict[str, int]
    family_counts: dict[str, int]
    family_ratios: dict[str, float]
    annotated_count: int
    annotated_matched: int
    annotated_family_accuracy: float | None
    family_confusion: dict[str, dict[str, int]]


@dataclass(frozen=True)
class PitchedMetrics:
    chroma_similarity: float
    audio_chroma: tuple[float, ...]
    midi_chroma: tuple[float, ...]
    mean_pitch_support: float
    supported_note_ratio: float
    octave_accuracy: float
    contour_pairs: int
    contour_direction_accuracy: float | None
    contour_pitch_correlation: float | None
    candidate_polyphony_mean: float
    candidate_polyphony_max: int
    audio_polyphony_mean: float
    audio_polyphony_max: int
    polyphony_mean_error: float
    candidate_notes_per_second: float
    candidate_onsets_per_second: float
    audio_onsets_per_second: float
    onset_density_ratio: float | None


@dataclass(frozen=True)
class EvaluationReport:
    stem_path: str
    kind: str
    duration_seconds: float
    note_count: int
    onsets: OnsetMetrics
    drums: DrumMetrics | None = None
    pitched: PitchedMetrics | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return only JSON-native containers and scalar values."""

        return _json_native(asdict(self))

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


def evaluate_stem_midi(
    stem_path: str | Path,
    midi_or_notes: str | Path | Sequence[NoteEvent],
    *,
    kind: str,
    annotations: Sequence[FamilyAnnotation | Mapping[str, Any]] | None = None,
    pitch_family_map: Mapping[int, str] | None = None,
    onset_tolerance: float = 0.040,
    segment_seconds: float = 30.0,
    strong_ratio: float = 0.34,
    possible_ratio: float = 0.10,
) -> EvaluationReport:
    """Evaluate MIDI notes against evidence independently extracted from a WAV.

    ``strong`` onset metrics use only high-confidence audio references.
    ``possible`` metrics are inclusive: their reference set contains both the
    strong and lower-confidence possible onsets.  This exposes the precision /
    recall trade-off without silently treating ambiguous separation residue as
    either definitely musical or definitely noise.
    """

    if onset_tolerance <= 0:
        raise ValueError("onset_tolerance must be positive")
    if segment_seconds <= 0:
        raise ValueError("segment_seconds must be positive")
    stem_path = Path(stem_path)
    notes = _coerce_notes(midi_or_notes)
    samples, sample_rate = _load_audio_mono(stem_path)
    duration = len(samples) / sample_rate if sample_rate else 0.0
    references = detect_reference_onsets(
        samples,
        sample_rate,
        strong_ratio=strong_ratio,
        possible_ratio=possible_ratio,
    )
    candidate_times = _unique_onset_times(notes)
    onset_metrics = _evaluate_onsets(
        references,
        candidate_times,
        duration=duration,
        tolerance=onset_tolerance,
        segment_seconds=segment_seconds,
    )

    normalized_kind = kind.strip().lower()
    drum_metrics = None
    pitched_metrics = None
    if normalized_kind in DRUM_KINDS:
        drum_metrics = _evaluate_drums(
            notes,
            annotations=annotations or (),
            pitch_family_map=pitch_family_map,
            tolerance=onset_tolerance,
        )
    else:
        pitched_metrics = _evaluate_pitched(
            samples,
            sample_rate,
            notes,
            references,
            duration=duration,
            kind=normalized_kind,
        )

    return EvaluationReport(
        stem_path=str(stem_path),
        kind=normalized_kind,
        duration_seconds=round(duration, 6),
        note_count=len(notes),
        onsets=onset_metrics,
        drums=drum_metrics,
        pitched=pitched_metrics,
    )


def detect_reference_onsets(
    samples_or_path: Any,
    sample_rate: int | None = None,
    *,
    strong_ratio: float = 0.34,
    possible_ratio: float = 0.10,
    min_gap_seconds: float = 0.030,
) -> tuple[ReferenceOnset, ...]:
    """Detect two confidence tiers with an independent time-domain method.

    This detector uses an adaptive short-time RMS rise envelope and non-maximum
    suppression.  It intentionally shares no code, envelope, thresholds, or
    peak picker with ``transcribe_drums`` / ``compare.extract_onsets``.
    """

    np = _numpy()
    if not 0.0 < possible_ratio <= strong_ratio <= 1.0:
        raise ValueError("onset ratios must satisfy 0 < possible <= strong <= 1")
    if min_gap_seconds <= 0:
        raise ValueError("min_gap_seconds must be positive")
    if isinstance(samples_or_path, (str, Path)):
        samples, resolved_rate = _load_audio_mono(Path(samples_or_path))
        sample_rate = resolved_rate
    else:
        samples = np.asarray(samples_or_path, dtype=np.float64)
    if sample_rate is None or sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if samples.size == 0:
        return ()

    peak = float(np.max(np.abs(samples)))
    if peak < 1e-8:
        return ()
    values = np.asarray(samples, dtype=np.float64) / peak

    frame = max(16, int(round(0.010 * sample_rate)))
    hop = max(1, int(round(0.0025 * sample_rate)))
    rms = _frame_rms(values, frame, hop)
    if rms.size < 3:
        return ()

    # Measure a rise relative to the quietest recent frame.  A minimum filter
    # rather than a global threshold keeps quiet sections visible, while the
    # multiplication by current RMS prevents tiny noise-floor ratios exploding.
    lookback = max(2, int(round(0.060 / (hop / sample_rate))))
    novelty = np.zeros_like(rms)
    for index in range(1, len(rms)):
        baseline = float(np.min(rms[max(0, index - lookback) : index]))
        novelty[index] = max(0.0, float(rms[index]) - baseline) * math.sqrt(
            max(float(rms[index]), 0.0)
        )

    novelty_peak = float(np.max(novelty))
    if novelty_peak <= 1e-10:
        return ()
    normalized = novelty / novelty_peak

    # A robust floor rejects low-level modulation.  The ratio thresholds then
    # distinguish a conservative main layer from auditable possible events.
    nonzero = normalized[normalized > 1e-6]
    median = float(np.median(nonzero)) if nonzero.size else 0.0
    mad = float(np.median(np.abs(nonzero - median))) if nonzero.size else 0.0
    noise_floor = min(0.25, median + 2.5 * mad)
    possible_threshold = max(0.015, min(possible_ratio, noise_floor))
    strong_threshold = max(strong_ratio, possible_threshold * 2.0)

    local_radius = max(1, int(round(0.020 / (hop / sample_rate))))
    candidates: list[tuple[float, int]] = []
    for index in range(1, len(normalized) - 1):
        strength = float(normalized[index])
        if strength < possible_threshold:
            continue
        left = max(0, index - local_radius)
        right = min(len(normalized), index + local_radius + 1)
        if strength + 1e-12 < float(np.max(normalized[left:right])):
            continue
        candidates.append((strength, index))

    # Keep the strongest observation in each minimum-gap neighbourhood.
    accepted: list[tuple[float, int]] = []
    gap_frames = max(1, int(round(min_gap_seconds / (hop / sample_rate))))
    for strength, index in sorted(candidates, reverse=True):
        if any(abs(index - other_index) < gap_frames for _, other_index in accepted):
            continue
        accepted.append((strength, index))

    provisional: list[ReferenceOnset] = []
    for strength, index in sorted(accepted, key=lambda item: item[1]):
        # RMS frame ``index`` spans [index*hop, index*hop+frame].  Backtracking
        # within the envelope locates the beginning of the rise more accurately
        # than using the frame centre.
        floor = max(0, index - lookback)
        target = rms[index] * 0.20
        onset_index = index
        while onset_index > floor and rms[onset_index - 1] > target:
            onset_index -= 1
        time_seconds = onset_index * hop / sample_rate
        tier = "strong" if strength >= strong_threshold else "possible"
        provisional.append(
            ReferenceOnset(
                time=round(float(time_seconds), 6),
                strength=round(float(strength), 6),
                tier=tier,
            )
        )
    # Two envelope peaks can backtrack to the same physical attack.  Apply NMS
    # again in source-time coordinates so a single transient never appears
    # twice in the independent reference report.
    result: list[ReferenceOnset] = []
    for onset in sorted(provisional, key=lambda item: item.strength, reverse=True):
        if any(abs(onset.time - kept.time) < min_gap_seconds for kept in result):
            continue
        result.append(onset)
    return tuple(sorted(result, key=lambda item: item.time))


def gm_drum_family(pitch: int, pitch_family_map: Mapping[int, str] | None = None) -> str:
    if pitch_family_map and int(pitch) in pitch_family_map:
        return str(pitch_family_map[int(pitch)])
    for family, pitches in GM_DRUM_FAMILIES.items():
        if int(pitch) in pitches:
            return family
    return "percussion_other" if 35 <= int(pitch) <= 81 else "non_drum"


def _evaluate_onsets(
    references: Sequence[ReferenceOnset],
    candidate_times: Sequence[float],
    *,
    duration: float,
    tolerance: float,
    segment_seconds: float,
) -> OnsetMetrics:
    strong_times = [item.time for item in references if item.tier == "strong"]
    inclusive_times = [item.time for item in references]
    strong = _precision_recall(strong_times, candidate_times, tolerance)
    possible = _precision_recall(inclusive_times, candidate_times, tolerance)

    # Match strong events first for timing, then use remaining candidates for
    # possible events.  A weak observation can never steal a candidate from a
    # strong reference.
    strong_pairs, _, remaining_candidates = _match_times(
        strong_times, candidate_times, tolerance
    )
    possible_only = [item.time for item in references if item.tier == "possible"]
    possible_pairs, _, _ = _match_times(possible_only, remaining_candidates, tolerance)
    timing = _timing_metrics(
        strong_pairs + possible_pairs,
        duration=duration,
        segment_seconds=segment_seconds,
    )
    return OnsetMetrics(
        reference_strong_count=len(strong_times),
        reference_possible_count=len(possible_only),
        strong=strong,
        possible=possible,
        timing=timing,
        references=tuple(references),
    )


def _precision_recall(
    reference_times: Sequence[float], candidate_times: Sequence[float], tolerance: float
) -> PrecisionRecall:
    pairs, missed, extra = _match_times(reference_times, candidate_times, tolerance)
    matched = len(pairs)
    precision = matched / len(candidate_times) if candidate_times else (1.0 if not reference_times else 0.0)
    recall = matched / len(reference_times) if reference_times else (1.0 if not candidate_times else 0.0)
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if precision + recall > 0.0
        else 0.0
    )
    return PrecisionRecall(
        reference_count=len(reference_times),
        candidate_count=len(candidate_times),
        matched=matched,
        missed=len(missed),
        extra=len(extra),
        precision=round(precision, 6),
        recall=round(recall, 6),
        f1=round(f1, 6),
        missed_times=tuple(round(value, 6) for value in missed),
        extra_times=tuple(round(value, 6) for value in extra),
    )


def _match_times(
    reference_times: Sequence[float], candidate_times: Sequence[float], tolerance: float
) -> tuple[list[tuple[float, float]], list[float], list[float]]:
    references = list(sorted(float(value) for value in reference_times))
    candidates = list(sorted(float(value) for value in candidate_times))
    options = sorted(
        (
            abs(reference - candidate),
            reference_index,
            candidate_index,
        )
        for reference_index, reference in enumerate(references)
        for candidate_index, candidate in enumerate(candidates)
        if abs(reference - candidate) <= tolerance
    )
    used_references: set[int] = set()
    used_candidates: set[int] = set()
    pairs: list[tuple[float, float]] = []
    for _, reference_index, candidate_index in options:
        if reference_index in used_references or candidate_index in used_candidates:
            continue
        used_references.add(reference_index)
        used_candidates.add(candidate_index)
        pairs.append((references[reference_index], candidates[candidate_index]))
    pairs.sort()
    missed = [value for index, value in enumerate(references) if index not in used_references]
    extra = [value for index, value in enumerate(candidates) if index not in used_candidates]
    return pairs, missed, extra


def _timing_metrics(
    pairs: Sequence[tuple[float, float]], *, duration: float, segment_seconds: float
) -> TimingMetrics:
    np = _numpy()
    if segment_seconds <= 0:
        raise ValueError("segment_seconds must be positive")
    signed_ms = np.asarray([(candidate - reference) * 1000.0 for reference, candidate in pairs])
    absolute_ms = np.abs(signed_ms)
    segment_count = max(1, int(math.ceil(max(duration, 1e-9) / segment_seconds)))
    segments: list[SegmentDrift] = []
    for index in range(segment_count):
        start = index * segment_seconds
        end = min(duration, (index + 1) * segment_seconds)
        offsets = [
            (candidate - reference) * 1000.0
            for reference, candidate in pairs
            if start <= reference < (end if index + 1 < segment_count else end + 1e-9)
        ]
        segments.append(
            SegmentDrift(
                index=index,
                start_seconds=round(start, 6),
                end_seconds=round(end, 6),
                matched=len(offsets),
                median_offset_ms=round(float(np.median(offsets)), 6) if offsets else None,
            )
        )

    populated = [segment.median_offset_ms for segment in segments if segment.median_offset_ms is not None]
    drift = populated[-1] - populated[0] if len(populated) >= 2 else None
    slope = None
    if len(pairs) >= 2:
        x = np.asarray([reference for reference, _ in pairs], dtype=np.float64)
        if float(np.ptp(x)) > 1e-9:
            slope = float(np.polyfit(x, signed_ms, 1)[0] * 60.0)
    return TimingMetrics(
        matched=len(pairs),
        absolute_error_p50_ms=_percentile(absolute_ms, 50),
        absolute_error_p95_ms=_percentile(absolute_ms, 95),
        absolute_error_p99_ms=_percentile(absolute_ms, 99),
        signed_error_mean_ms=round(float(np.mean(signed_ms)), 6) if signed_ms.size else None,
        signed_error_median_ms=round(float(np.median(signed_ms)), 6) if signed_ms.size else None,
        drift_ms=round(float(drift), 6) if drift is not None else None,
        drift_slope_ms_per_minute=round(slope, 6) if slope is not None else None,
        segments=tuple(segments),
    )


def _evaluate_drums(
    notes: Sequence[NoteEvent],
    *,
    annotations: Sequence[FamilyAnnotation | Mapping[str, Any]],
    pitch_family_map: Mapping[int, str] | None,
    tolerance: float,
) -> DrumMetrics:
    pitch_counts: dict[str, int] = {}
    family_counts: dict[str, int] = {}
    for note in notes:
        pitch_key = str(int(note.pitch))
        pitch_counts[pitch_key] = pitch_counts.get(pitch_key, 0) + 1
        family = gm_drum_family(note.pitch, pitch_family_map)
        family_counts[family] = family_counts.get(family, 0) + 1
    total = len(notes)
    family_ratios = {
        family: round(count / total, 6) if total else 0.0
        for family, count in sorted(family_counts.items())
    }

    normalized_annotations = [_coerce_annotation(item) for item in annotations]
    options = sorted(
        (
            abs(annotation.time - note.start),
            annotation_index,
            note_index,
        )
        for annotation_index, annotation in enumerate(normalized_annotations)
        for note_index, note in enumerate(notes)
        if abs(annotation.time - note.start) <= tolerance
    )
    used_annotations: set[int] = set()
    used_notes: set[int] = set()
    correct = 0
    confusion: dict[str, dict[str, int]] = {}
    for _, annotation_index, note_index in options:
        if annotation_index in used_annotations or note_index in used_notes:
            continue
        used_annotations.add(annotation_index)
        used_notes.add(note_index)
        expected = normalized_annotations[annotation_index].family
        actual = gm_drum_family(notes[note_index].pitch, pitch_family_map)
        row = confusion.setdefault(expected, {})
        row[actual] = row.get(actual, 0) + 1
        correct += int(expected == actual)
    accuracy = correct / len(used_annotations) if used_annotations else None
    return DrumMetrics(
        pitch_counts=dict(sorted(pitch_counts.items(), key=lambda item: int(item[0]))),
        family_counts=dict(sorted(family_counts.items())),
        family_ratios=family_ratios,
        annotated_count=len(normalized_annotations),
        annotated_matched=len(used_annotations),
        annotated_family_accuracy=round(accuracy, 6) if accuracy is not None else None,
        family_confusion={key: dict(sorted(value.items())) for key, value in sorted(confusion.items())},
    )


def _evaluate_pitched(
    samples: Any,
    sample_rate: int,
    notes: Sequence[NoteEvent],
    references: Sequence[ReferenceOnset],
    *,
    duration: float,
    kind: str,
) -> PitchedMetrics:
    np = _numpy()
    frame_times, pitch_energy = _pitch_energy_matrix(samples, sample_rate)
    audio_chroma = np.zeros(12, dtype=np.float64)
    if pitch_energy.size:
        for column, pitch in enumerate(range(21, 109)):
            audio_chroma[pitch % 12] += float(np.sum(pitch_energy[:, column]))
    midi_chroma = np.zeros(12, dtype=np.float64)
    for note in notes:
        weight = max(0.0, note.end - note.start) * max(1, note.velocity)
        midi_chroma[note.pitch % 12] += weight
    audio_chroma = _unit_vector(audio_chroma)
    midi_chroma = _unit_vector(midi_chroma)
    chroma_similarity = float(np.dot(audio_chroma, midi_chroma)) if notes else 0.0

    supports: list[float] = []
    octave_hits: list[bool] = []
    audio_pitch_for_note: list[float] = []
    for note in notes:
        columns = np.flatnonzero((frame_times >= note.start) & (frame_times <= note.end))
        if not len(columns):
            nearest = int(np.argmin(np.abs(frame_times - (note.start + note.end) / 2.0))) if len(frame_times) else -1
            columns = np.asarray([nearest]) if nearest >= 0 else np.asarray([], dtype=int)
        if not len(columns) or not pitch_energy.size:
            supports.append(0.0)
            octave_hits.append(False)
            audio_pitch_for_note.append(float(note.pitch))
            continue
        region = np.mean(pitch_energy[columns, :], axis=0)
        maximum = float(np.max(region))
        pitch_index = note.pitch - 21
        exact = float(region[pitch_index]) if 0 <= pitch_index < len(region) else 0.0
        support = exact / (maximum + 1e-12) if maximum > 0 else 0.0
        supports.append(min(1.0, max(0.0, support)))
        same_class = [pitch - 21 for pitch in range(21, 109) if pitch % 12 == note.pitch % 12]
        best_same_class = max((float(region[index]) for index in same_class), default=0.0)
        octave_hits.append(exact >= 0.80 * best_same_class and exact > 0.0)
        audio_pitch_for_note.append(float(21 + int(np.argmax(region))))

    voice_notes = _voice_notes(notes, kind)
    # Align each selected voice note back to its corresponding full-note metric.
    voice_audio_pitches: list[float] = []
    for voice_note in voice_notes:
        index = min(
            range(len(notes)),
            key=lambda i: (
                abs(notes[i].start - voice_note.start),
                abs(notes[i].pitch - voice_note.pitch),
            ),
            default=-1,
        )
        voice_audio_pitches.append(audio_pitch_for_note[index] if index >= 0 else float(voice_note.pitch))
    candidate_voice_pitches = [float(note.pitch) for note in voice_notes]
    direction_matches: list[bool] = []
    for index in range(1, len(candidate_voice_pitches)):
        candidate_direction = _sign(candidate_voice_pitches[index] - candidate_voice_pitches[index - 1])
        audio_direction = _sign(voice_audio_pitches[index] - voice_audio_pitches[index - 1])
        direction_matches.append(candidate_direction == audio_direction)
    contour_accuracy = (
        sum(direction_matches) / len(direction_matches) if direction_matches else None
    )
    correlation = _correlation(candidate_voice_pitches, voice_audio_pitches)

    candidate_mean, candidate_max = _candidate_polyphony(notes, duration)
    audio_mean, audio_max = _audio_polyphony(pitch_energy)
    unique_onsets = _unique_onset_times(notes)
    candidate_notes_density = len(notes) / duration if duration > 0 else 0.0
    candidate_onset_density = len(unique_onsets) / duration if duration > 0 else 0.0
    audio_onset_density = len(references) / duration if duration > 0 else 0.0
    density_ratio = (
        candidate_onset_density / audio_onset_density if audio_onset_density > 0 else None
    )
    return PitchedMetrics(
        chroma_similarity=round(chroma_similarity, 6),
        audio_chroma=tuple(round(float(value), 6) for value in audio_chroma),
        midi_chroma=tuple(round(float(value), 6) for value in midi_chroma),
        mean_pitch_support=round(float(np.mean(supports)), 6) if supports else 0.0,
        supported_note_ratio=round(sum(value >= 0.18 for value in supports) / len(supports), 6) if supports else 0.0,
        octave_accuracy=round(sum(octave_hits) / len(octave_hits), 6) if octave_hits else 0.0,
        contour_pairs=len(direction_matches),
        contour_direction_accuracy=round(contour_accuracy, 6) if contour_accuracy is not None else None,
        contour_pitch_correlation=round(correlation, 6) if correlation is not None else None,
        candidate_polyphony_mean=round(candidate_mean, 6),
        candidate_polyphony_max=candidate_max,
        audio_polyphony_mean=round(audio_mean, 6),
        audio_polyphony_max=audio_max,
        polyphony_mean_error=round(abs(candidate_mean - audio_mean), 6),
        candidate_notes_per_second=round(candidate_notes_density, 6),
        candidate_onsets_per_second=round(candidate_onset_density, 6),
        audio_onsets_per_second=round(audio_onset_density, 6),
        onset_density_ratio=round(density_ratio, 6) if density_ratio is not None else None,
    )


def _pitch_energy_matrix(samples: Any, sample_rate: int) -> tuple[Any, Any]:
    np = _numpy()
    values = np.asarray(samples, dtype=np.float64)
    if sample_rate > 24_000 and values.size:
        target_rate = 22_050
        target_length = int(round(len(values) * target_rate / sample_rate))
        source_positions = np.linspace(0.0, 1.0, len(values), endpoint=False)
        target_positions = np.linspace(0.0, 1.0, target_length, endpoint=False)
        values = np.interp(target_positions, source_positions, values)
        sample_rate = target_rate
    if values.size == 0:
        return np.zeros(0), np.zeros((0, 88))
    frame = 4096 if len(values) >= 4096 else max(256, 2 ** int(math.floor(math.log2(max(256, len(values))))))
    hop = max(64, frame // 4)
    if len(values) < frame:
        values = np.pad(values, (0, frame - len(values)))
    starts = list(range(0, max(1, len(values) - frame + 1), hop))
    if starts[-1] != len(values) - frame:
        starts.append(len(values) - frame)
    window = np.hanning(frame)
    frequencies = np.fft.rfftfreq(frame, 1.0 / sample_rate)
    midi_frequencies = 440.0 * (2.0 ** ((np.arange(21, 109) - 69.0) / 12.0))
    # Resolve semitone bands once.  Rebuilding an FFT-length mask for every
    # pitch in every frame is prohibitively expensive on full-song stems.
    pitch_bands: list[tuple[int, int, float]] = []
    for frequency in midi_frequencies:
        low = frequency * (2.0 ** (-0.45 / 12.0))
        high = frequency * (2.0 ** (0.45 / 12.0))
        low_index = int(np.searchsorted(frequencies, low, side="left"))
        high_index = int(np.searchsorted(frequencies, high, side="right"))
        pitch_bands.append((low_index, high_index, float(frequency)))
    matrix = np.zeros((len(starts), len(midi_frequencies)), dtype=np.float64)
    for row, start in enumerate(starts):
        spectrum = np.abs(np.fft.rfft(values[start : start + frame] * window)) ** 2
        # Integrate a narrow semitone-centred band rather than a single FFT bin.
        for column, (low_index, high_index, frequency) in enumerate(pitch_bands):
            if high_index > low_index:
                matrix[row, column] = float(np.sum(spectrum[low_index:high_index]))
            else:
                matrix[row, column] = float(np.interp(frequency, frequencies, spectrum))
    frame_times = (np.asarray(starts, dtype=np.float64) + frame / 2.0) / sample_rate
    return frame_times, matrix


def _audio_polyphony(pitch_energy: Any) -> tuple[float, int]:
    np = _numpy()
    if not pitch_energy.size:
        return 0.0, 0
    counts: list[int] = []
    for row in pitch_energy:
        maximum = float(np.max(row))
        if maximum <= 1e-12:
            counts.append(0)
            continue
        # Local spectral peaks above a conservative share of the strongest
        # pitch provide a stable, explicitly approximate polyphony estimate.
        active = 0
        for index, value in enumerate(row):
            if value < maximum * 0.22:
                continue
            left = row[index - 1] if index else -1.0
            right = row[index + 1] if index + 1 < len(row) else -1.0
            if value >= left and value >= right:
                active += 1
        counts.append(active)
    return float(np.mean(counts)), max(counts, default=0)


def _candidate_polyphony(notes: Sequence[NoteEvent], duration: float) -> tuple[float, int]:
    if duration <= 0 or not notes:
        return 0.0, 0
    events: list[tuple[float, int]] = []
    for note in notes:
        events.append((max(0.0, note.start), 1))
        events.append((min(duration, max(note.start, note.end)), -1))
    events.sort(key=lambda item: (item[0], item[1]))
    active = 0
    maximum = 0
    previous = 0.0
    weighted = 0.0
    for time, change in events:
        weighted += active * max(0.0, time - previous)
        active += change
        maximum = max(maximum, active)
        previous = time
    weighted += active * max(0.0, duration - previous)
    return weighted / duration, maximum


def _voice_notes(notes: Sequence[NoteEvent], kind: str) -> list[NoteEvent]:
    groups: list[list[NoteEvent]] = []
    for note in sorted(notes, key=lambda item: (item.start, item.pitch)):
        if not groups or abs(groups[-1][0].start - note.start) > 0.025:
            groups.append([note])
        else:
            groups[-1].append(note)
    return [
        (min(group, key=lambda item: item.pitch) if kind == "bass" else max(group, key=lambda item: item.pitch))
        for group in groups
    ]


def _unique_onset_times(notes: Sequence[NoteEvent], tolerance: float = 0.012) -> list[float]:
    result: list[float] = []
    for value in sorted(note.start for note in notes):
        if not result or value - result[-1] > tolerance:
            result.append(float(value))
    return result


def _coerce_notes(value: str | Path | Sequence[NoteEvent]) -> list[NoteEvent]:
    if isinstance(value, (str, Path)):
        return _read_midi_notes(Path(value))
    notes: list[NoteEvent] = []
    for item in value:
        if isinstance(item, NoteEvent):
            note = item
        elif isinstance(item, Mapping):
            note = NoteEvent(
                float(item["start"]),
                float(item["end"]),
                int(item["pitch"]),
                int(item["velocity"]),
            )
        else:
            raise TypeError("midi_or_notes must contain NoteEvent or mapping values")
        if note.end < note.start:
            raise ValueError("note end must not precede note start")
        notes.append(note)
    return sorted(notes, key=lambda item: (item.start, item.pitch, item.end))


def _read_midi_notes(path: Path) -> list[NoteEvent]:
    try:
        import mido
    except ImportError as exc:  # pragma: no cover - exercised on minimal installs
        raise RuntimeError("Reading a MIDI path requires the optional 'mido' dependency") from exc

    midi = mido.MidiFile(str(path))
    tempo = 500_000
    elapsed = 0.0
    active: dict[tuple[int, int], list[tuple[float, int]]] = {}
    notes: list[NoteEvent] = []
    for message in mido.merge_tracks(midi.tracks):
        elapsed += mido.tick2second(message.time, midi.ticks_per_beat, tempo)
        if message.type == "set_tempo":
            tempo = message.tempo
            continue
        if message.type == "note_on" and message.velocity > 0:
            active.setdefault((message.channel, message.note), []).append(
                (elapsed, int(message.velocity))
            )
            continue
        if message.type not in {"note_off", "note_on"}:
            continue
        key = (message.channel, message.note)
        starts = active.get(key)
        if not starts:
            continue
        start, velocity = starts.pop(0)
        if not starts:
            active.pop(key, None)
        notes.append(
            NoteEvent(
                start=round(start, 9),
                end=round(max(start, elapsed), 9),
                pitch=int(message.note),
                velocity=velocity,
            )
        )
    return sorted(notes, key=lambda item: (item.start, item.pitch, item.end))


def _coerce_annotation(value: FamilyAnnotation | Mapping[str, Any]) -> FamilyAnnotation:
    if isinstance(value, FamilyAnnotation):
        return value
    return FamilyAnnotation(
        time=float(value["time"]),
        family=str(value["family"]),
        tier=str(value.get("tier", "strong")),
    )


def _load_audio_mono(path: Path) -> tuple[Any, int]:
    np = _numpy()
    try:
        import soundfile

        values, sample_rate = soundfile.read(str(path), dtype="float64", always_2d=True)
        return _phase_safe_downmix(values), int(sample_rate)
    except (ImportError, RuntimeError):
        pass

    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        sample_rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    if width == 1:
        values = np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128.0
        scale = 128.0
    elif width == 2:
        values = np.frombuffer(raw, dtype="<i2").astype(np.float64)
        scale = 32768.0
    elif width == 4:
        values = np.frombuffer(raw, dtype="<i4").astype(np.float64)
        scale = 2147483648.0
    else:
        raise ValueError(f"Unsupported PCM sample width: {width}")
    values = values.reshape((-1, channels)) / scale
    return _phase_safe_downmix(values), int(sample_rate)


def _phase_safe_downmix(values: Any, cancellation_ratio: float = 0.80) -> Any:
    """Use arithmetic mono unless it materially cancels stereo evidence."""

    np = _numpy()
    channels = np.asarray(values, dtype=np.float64)
    if channels.ndim == 1:
        return channels
    if channels.shape[1] == 1:
        return channels[:, 0]
    mono = np.mean(channels, axis=1)
    mono_rms = math.sqrt(float(np.mean(mono * mono))) if len(mono) else 0.0
    channel_rms = np.sqrt(np.mean(channels * channels, axis=0))
    strongest = int(np.argmax(channel_rms)) if len(channel_rms) else 0
    strongest_rms = float(channel_rms[strongest]) if len(channel_rms) else 0.0
    if strongest_rms > 0.0 and mono_rms < strongest_rms * cancellation_ratio:
        return channels[:, strongest]
    return mono


def _frame_rms(values: Any, frame: int, hop: int) -> Any:
    np = _numpy()
    if len(values) < frame:
        values = np.pad(values, (0, frame - len(values)))
    starts = list(range(0, max(1, len(values) - frame + 1), hop))
    if starts[-1] != len(values) - frame:
        starts.append(len(values) - frame)
    return np.asarray(
        [math.sqrt(float(np.mean(values[start : start + frame] ** 2))) for start in starts],
        dtype=np.float64,
    )


def _unit_vector(values: Any) -> Any:
    np = _numpy()
    norm = float(np.linalg.norm(values))
    return values / norm if norm > 0 else np.zeros_like(values)


def _correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    np = _numpy()
    if len(left) < 2 or len(right) != len(left):
        return None
    if float(np.std(left)) <= 1e-9 or float(np.std(right)) <= 1e-9:
        return None
    return float(np.corrcoef(left, right)[0, 1])


def _percentile(values: Any, percentile: float) -> float | None:
    np = _numpy()
    return round(float(np.percentile(values, percentile)), 6) if len(values) else None


def _sign(value: float, tolerance: float = 0.5) -> int:
    if value > tolerance:
        return 1
    if value < -tolerance:
        return -1
    return 0


def _json_native(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_native(item) for item in value]
    return value


def _numpy():
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - optional dependency contract
        raise RuntimeError("Stem-to-MIDI evaluation requires the optional 'numpy' dependency") from exc
    return numpy


__all__ = [
    "DrumMetrics",
    "EvaluationReport",
    "FamilyAnnotation",
    "GM_DRUM_FAMILIES",
    "V2_DRUM_PITCH_FAMILIES",
    "OnsetMetrics",
    "PitchedMetrics",
    "PrecisionRecall",
    "ReferenceOnset",
    "SegmentDrift",
    "TimingMetrics",
    "detect_reference_onsets",
    "evaluate_stem_midi",
    "gm_drum_family",
    "v2_pitch_family_map",
]
