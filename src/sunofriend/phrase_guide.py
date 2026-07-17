"""Evidence-gated short guides for one melody review unit."""

from __future__ import annotations

import json
import math
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Literal, Mapping, Sequence

from .conversion import NoteProvenance
from .melody_correction import align_hummed_guide, transcribe_short_pitch_guide
from .models import NoteEvent
from .vocal import PitchFrame, VocalConfig, hz_to_fractional_midi


GuideKind = Literal["hum", "whistle", "contour", "single-note", "tap"]
GUIDE_KINDS: tuple[GuideKind, ...] = (
    "hum",
    "whistle",
    "contour",
    "single-note",
    "tap",
)
SHORT_GUIDE_SCHEMA = "sunofriend.short-melody-guide.v1"


@dataclass(frozen=True)
class ShortGuideResult:
    notes: tuple[NoteEvent, ...]
    provenance: tuple[NoteProvenance, ...]
    report: Mapping[str, Any]


def load_pyin_frames(
    evidence_path: str | Path,
    *,
    source_sha256: str,
) -> list[PitchFrame]:
    """Load immutable pYIN frame evidence for source-supported guide mapping."""

    path = Path(evidence_path).expanduser().absolute()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid pYIN evidence: {path}") from exc
    if document.get("schema") != "sunofriend.vocal-tracker-evidence.v1":
        raise ValueError("unsupported pYIN evidence schema")
    if document.get("tracker") != "pyin":
        raise ValueError("short guide requires pYIN frame evidence")
    if document.get("source", {}).get("sha256") != source_sha256:
        raise ValueError("pYIN evidence source hash does not match the review source")
    expected_fields = [
        "time_seconds",
        "frequency_hz",
        "confidence",
        "rms",
        "onset_strength",
        "source",
    ]
    if document.get("frame_fields") != expected_fields:
        raise ValueError("unsupported pYIN frame field order")
    values = document.get("frames")
    if not isinstance(values, list) or not values:
        raise ValueError("pYIN evidence contains no frames")
    frames: list[PitchFrame] = []
    for value in values:
        if not isinstance(value, list) or len(value) != len(expected_fields):
            raise ValueError("pYIN evidence contains an invalid frame")
        try:
            frame = PitchFrame(
                time=float(value[0]),
                f0_hz=None if value[1] is None else float(value[1]),
                voiced_probability=float(value[2]),
                rms=float(value[3]),
                onset_strength=float(value[4]),
                source=str(value[5]),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("pYIN evidence contains invalid frame values") from exc
        numeric = [
            frame.time,
            frame.voiced_probability,
            frame.rms,
            frame.onset_strength,
        ]
        if frame.f0_hz is not None:
            numeric.append(frame.f0_hz)
        if not all(math.isfinite(number) for number in numeric):
            raise ValueError("pYIN evidence contains non-finite frame values")
        if (
            frame.time < 0
            or (frame.f0_hz is not None and frame.f0_hz <= 0)
            or not 0 <= frame.voiced_probability <= 1
            or frame.rms < 0
            or frame.onset_strength < 0
        ):
            raise ValueError("pYIN evidence contains out-of-range frame values")
        frames.append(frame)
    if any(current.time < previous.time for previous, current in zip(frames, frames[1:])):
        raise ValueError("pYIN evidence frames are not chronological")
    return frames


def prepare_short_guide(
    guide_path: str | Path,
    *,
    kind: GuideKind,
    source_frames: Sequence[PitchFrame],
    unit_start_seconds: float,
    unit_end_seconds: float,
    bpm: float,
    tuning_hz: float,
    search_seconds: float = 0.75,
) -> ShortGuideResult:
    """Create one source-supported guide alternative for a review unit."""

    guide = Path(guide_path).expanduser().absolute()
    if not guide.is_file():
        raise ValueError(f"Short guide WAV not found: {guide}")
    if kind not in GUIDE_KINDS:
        raise ValueError(f"guide kind must be one of: {', '.join(GUIDE_KINDS)}")
    start = float(unit_start_seconds)
    end = float(unit_end_seconds)
    tempo = float(bpm)
    tuning = float(tuning_hz)
    search = float(search_seconds)
    if not all(math.isfinite(value) for value in (start, end, tempo, tuning, search)):
        raise ValueError("short guide parameters must be finite")
    if start < 0 or end <= start:
        raise ValueError("short guide unit bounds are invalid")
    if tempo <= 0 or tuning <= 0:
        raise ValueError("short guide BPM and tuning must be positive")
    if not 0 <= search <= 2.0:
        raise ValueError("guide search_seconds must be from 0 to 2")

    import soundfile

    duration = float(soundfile.info(str(guide)).duration)
    if duration <= 0:
        raise ValueError("short guide contains no audio")
    warnings: list[str] = []
    if not 2.0 <= duration <= 8.0:
        warnings.append(
            "The guide is outside the recommended two-to-eight-second range; "
            "record one short matching review unit when possible."
        )
    config = VocalConfig(
        role="lead",
        bpm=tempo,
        tuning_hz=tuning,
        tuning_source="phrase-review",
        tracker_mode="pyin",
        phrase_repair=False,
    )
    detection: dict[str, Any]
    if kind == "tap":
        guide_notes, detection = _transcribe_tap_guide(
            guide,
            bpm=tempo,
            minimum_note_ms=config.min_note_ms,
        )
        notes, provenance, alignment = _align_rhythm_guide(
            source_frames,
            guide_notes,
            config=config,
            unit_start_seconds=start,
            search_seconds=search,
            source_name="tap-guide",
        )
    else:
        guide_notes, tracker_warnings = transcribe_short_pitch_guide(
            guide,
            config=config,
        )
        warnings.extend(tracker_warnings)
        detection = {
            "method": "pyin-contour-to-notes",
            "detected_note_count": len(guide_notes),
        }
        if kind == "single-note":
            notes, provenance, alignment = _align_rhythm_guide(
                source_frames,
                guide_notes,
                config=config,
                unit_start_seconds=start,
                search_seconds=search,
                source_name="single-note-guide",
            )
        else:
            notes, provenance, alignment = align_hummed_guide(
                source_frames,
                guide_notes,
                config=config,
                offset_seconds=start,
                offset_search_radius_seconds=search,
            )
    notes, provenance = _clip_to_unit(
        notes,
        provenance,
        start_seconds=start,
        end_seconds=end,
    )
    status = "complete" if notes else "no-evidence"
    if not notes:
        warnings.append(
            "The short guide produced no notes supported by this source-vocal unit; "
            "the three automatic alternatives remain unchanged."
        )
    report = {
        "schema": SHORT_GUIDE_SCHEMA,
        "status": status,
        "kind": kind,
        "guide_duration_seconds": round(duration, 6),
        "unit_start_seconds": round(start, 6),
        "unit_end_seconds": round(end, 6),
        "search_seconds": round(search, 6),
        "guide_note_count": len(guide_notes),
        "accepted_note_count": len(notes),
        "detection": detection,
        "alignment": dict(alignment),
        "warnings": list(dict.fromkeys(warnings)),
        "source_pitch_support_required": True,
        "raw_candidates_mutated": False,
    }
    return ShortGuideResult(tuple(notes), tuple(provenance), report)


def _transcribe_tap_guide(
    guide: Path,
    *,
    bpm: float,
    minimum_note_ms: float,
) -> tuple[list[NoteEvent], dict[str, Any]]:
    import librosa
    import numpy as np

    audio, sample_rate = librosa.load(str(guide), sr=22_050, mono=True)
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if peak < 1e-5:
        return [], {"method": "librosa-onset-v1", "detected_onsets": 0}
    envelope = librosa.onset.onset_strength(y=audio, sr=sample_rate)
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=envelope,
        sr=sample_rate,
        backtrack=False,
        units="frames",
    )
    onset_times = [
        float(value)
        for value in librosa.frames_to_time(onset_frames, sr=sample_rate)
    ]
    duration = len(audio) / sample_rate
    default_duration = max(minimum_note_ms / 1000.0, 0.45 * 60.0 / bpm)
    strengths = [float(envelope[int(frame)]) for frame in onset_frames]
    maximum_strength = max(max(strengths, default=1.0), 1e-9)
    notes: list[NoteEvent] = []
    for index, onset in enumerate(onset_times):
        following = (
            onset_times[index + 1] - 0.02
            if index + 1 < len(onset_times)
            else min(duration, onset + default_duration)
        )
        end = max(onset + minimum_note_ms / 1000.0, following)
        end = min(duration, end)
        if end <= onset:
            continue
        velocity = 70 + int(round(35.0 * strengths[index] / maximum_strength))
        notes.append(NoteEvent(onset, end, 60, max(1, min(127, velocity))))
    return notes, {
        "method": "librosa-onset-v1",
        "sample_rate": sample_rate,
        "detected_onsets": len(onset_times),
        "accepted_rhythm_notes": len(notes),
        "onset_times_seconds": [round(value, 6) for value in onset_times],
    }


def _align_rhythm_guide(
    source_frames: Sequence[PitchFrame],
    guide_notes: Sequence[NoteEvent],
    *,
    config: VocalConfig,
    unit_start_seconds: float,
    search_seconds: float,
    source_name: str,
) -> tuple[list[NoteEvent], list[NoteProvenance], dict[str, Any]]:
    frames = list(source_frames)
    guide = sorted(guide_notes, key=lambda note: (note.start, note.end, note.pitch))
    if not frames or not guide:
        return [], [], {
            "status": "no-evidence",
            "offset_seconds": round(unit_start_seconds, 6),
            "alignment_score": 0.0,
        }
    times = [frame.time for frame in frames]
    midis = [
        (
            hz_to_fractional_midi(frame.f0_hz, config.tuning_hz)
            if frame.f0_hz is not None
            and frame.voiced_probability >= config.uncertain_voicing
            else None
        )
        for frame in frames
    ]
    probabilities = [frame.voiced_probability for frame in frames]
    step = min(0.10, max(0.04, 60.0 / float(config.bpm or 120.0) / 8.0))
    count = int(math.floor(search_seconds / step))
    offsets = [unit_start_seconds + index * step for index in range(-count, count + 1)]
    best: tuple[float, float, list[tuple[NoteEvent, float, float, float]]] | None = None
    best_key: tuple[float, float, float] | None = None
    for offset in offsets:
        observations: list[tuple[NoteEvent, float, float, float]] = []
        weighted_support = 0.0
        total_duration = 0.0
        for note in guide:
            region = _source_region(
                times,
                midis,
                probabilities,
                start=note.start + offset,
                end=note.end + offset,
            )
            duration = max(0.03, note.end - note.start)
            total_duration += duration
            if region is None:
                continue
            source_midi, voiced_fraction, probability = region
            observations.append((note, source_midi, voiced_fraction, probability))
            weighted_support += duration * voiced_fraction * probability
        score = weighted_support / max(total_duration, 1e-9)
        score -= min(0.02, abs(offset - unit_start_seconds) * 0.01)
        candidate = (score, offset, observations)
        candidate_key = (
            score,
            -abs(offset - unit_start_seconds),
            -offset,
        )
        if best_key is None or candidate_key > best_key:
            best = candidate
            best_key = candidate_key
    if best is None:
        return [], [], {
            "status": "no-evidence",
            "offset_seconds": round(unit_start_seconds, 6),
            "alignment_score": 0.0,
        }
    score, offset, observations = best
    notes: list[NoteEvent] = []
    provenance: list[NoteProvenance] = []
    for guide_note, source_midi, voiced_fraction, probability in observations:
        if voiced_fraction < 0.20 or probability < config.uncertain_voicing:
            continue
        start = max(0.0, guide_note.start + offset)
        end = max(start + config.min_note_ms / 1000.0, guide_note.end + offset)
        pitch = max(0, min(127, int(math.floor(source_midi + 0.5))))
        note = NoteEvent(start, end, pitch, guide_note.velocity)
        if notes and notes[-1].end > note.start:
            note = NoteEvent(notes[-1].end, end, pitch, guide_note.velocity)
            if note.end - note.start < config.min_note_ms / 1000.0:
                continue
        confidence = max(0.0, min(1.0, 0.6 * probability + 0.4 * voiced_fraction))
        notes.append(note)
        provenance.append(
            NoteProvenance.from_note(
                note,
                origin="repaired",
                confidence=confidence,
                tier="main" if confidence >= 0.55 else "possible",
                confidence_basis="measured",
                family="vocals",
                sources=(source_name, "source-contour", "rhythm-alignment"),
                details={
                    "guide_offset_seconds": round(offset, 6),
                    "source_median_midi": round(source_midi, 6),
                    "source_voiced_fraction": round(voiced_fraction, 6),
                    "source_voiced_probability": round(probability, 6),
                    "guide_pitch_ignored": True,
                },
            )
        )
    return notes, provenance, {
        "status": "complete" if notes else "no-evidence",
        "offset_seconds": round(offset, 6),
        "alignment_score": round(max(0.0, score), 6),
        "source_supported_notes": len(notes),
        "guide_pitch_ignored": True,
    }


def _source_region(
    times: Sequence[float],
    midis: Sequence[float | None],
    probabilities: Sequence[float],
    *,
    start: float,
    end: float,
) -> tuple[float, float, float] | None:
    if end <= start or not times:
        return None
    left = bisect_left(times, start)
    right = bisect_left(times, end)
    if right <= left:
        return None
    values = [value for value in midis[left:right] if value is not None]
    if not values:
        return None
    voiced = [
        probability
        for value, probability in zip(midis[left:right], probabilities[left:right])
        if value is not None
    ]
    return (
        float(median(values)),
        len(values) / max(1, right - left),
        float(median(voiced)),
    )


def _clip_to_unit(
    notes: Sequence[NoteEvent],
    provenance: Sequence[NoteProvenance],
    *,
    start_seconds: float,
    end_seconds: float,
) -> tuple[list[NoteEvent], list[NoteProvenance]]:
    clipped_notes: list[NoteEvent] = []
    clipped_records: list[NoteProvenance] = []
    for note, record in zip(notes, provenance):
        start = max(start_seconds, note.start)
        end = min(end_seconds, note.end)
        if end - start < 0.03:
            continue
        clipped = NoteEvent(start, end, note.pitch, note.velocity)
        clipped_notes.append(clipped)
        clipped_records.append(
            NoteProvenance.from_note(
                clipped,
                origin=record.origin,
                confidence=record.confidence,
                tier=record.tier,
                confidence_basis=record.confidence_basis,
                family=record.family,
                sources=record.sources,
                details={
                    **record.details,
                    "clipped_to_review_unit": (
                        start != note.start or end != note.end
                    ),
                },
            )
        )
    return clipped_notes, clipped_records


__all__ = [
    "GUIDE_KINDS",
    "SHORT_GUIDE_SCHEMA",
    "GuideKind",
    "ShortGuideResult",
    "load_pyin_frames",
    "prepare_short_guide",
]
