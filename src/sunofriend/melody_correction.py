"""Human-guided vocal melody repair and a self-contained correction report."""

from __future__ import annotations

import html
import hashlib
import json
import math
from bisect import bisect_left
from dataclasses import replace
from pathlib import Path
from statistics import median
from typing import Any, Sequence

from .conversion import NoteProvenance
from .models import NoteEvent
from .vocal import (
    PitchFrame,
    VocalConfig,
    VocalTranscription,
    extract_consensus_pitch_frames,
    extract_pitch_frames,
    hz_to_fractional_midi,
    transcribe_vocal_frames,
)


CORRECTION_FORMAT = "sunofriend-melody-corrections-v1"


def add_hummed_snippet_variants(
    result: VocalTranscription,
    snippets: Sequence[tuple[str | Path, str | Path, float]],
    *,
    config: VocalConfig,
    grid: Any | None = None,
    prefer_guide: bool = False,
) -> tuple[VocalTranscription, dict[str, Any]]:
    """Patch short, positioned hums into an automatic full-song melody.

    Each tuple contains a reference excerpt, the matching hum, and the
    reference excerpt's start time in the full source.  The reference is kept
    for audit and duration checks.  Pitch is still measured from the full
    source contour, so a comfortable humming register cannot invent notes.
    """

    if not snippets:
        raise ValueError("At least one hummed snippet is required")
    base_variant = result.primary_variant
    base_notes = list(result.notes)
    base_records = list(result.provenance.get(base_variant, []))
    reports: list[dict[str, Any]] = []
    accepted_pairs: list[tuple[NoteEvent, NoteProvenance]] = []
    warnings: list[str] = []

    for index, (reference_path, hum_path, start_seconds) in enumerate(snippets, 1):
        reference = Path(reference_path).expanduser()
        hum = Path(hum_path).expanduser()
        if not reference.is_file():
            raise ValueError(f"Guide snippet reference WAV not found: {reference}")
        if not hum.is_file():
            raise ValueError(f"Guide snippet hum WAV not found: {hum}")
        start = float(start_seconds)
        if not math.isfinite(start) or start < 0:
            raise ValueError("Guide snippet start time must be finite and non-negative")

        reference_duration = _audio_duration(reference)
        hum_duration = _audio_duration(hum)
        snippet_warnings: list[str] = []
        if reference_duration is not None and not 5.0 <= reference_duration <= 30.0:
            snippet_warnings.append(
                "Reference excerpt is outside the recommended 5–30 second range."
            )
        if hum_duration is not None and not 5.0 <= hum_duration <= 30.0:
            snippet_warnings.append(
                "Hummed excerpt is outside the recommended 5–30 second range."
            )
        if (
            reference_duration is not None
            and hum_duration is not None
            and abs(reference_duration - hum_duration) > 2.0
        ):
            snippet_warnings.append(
                "Reference and hum durations differ by more than two seconds; "
                "start them from the same phrase boundary."
            )

        guide_notes, tracker_warnings = _transcribe_hummed_notes(
            hum,
            config=config,
            grid=grid,
        )
        snippet_warnings.extend(tracker_warnings)
        notes, records, alignment = align_hummed_guide(
            result.contour,
            guide_notes,
            config=config,
            offset_seconds=start,
            offset_search_radius_seconds=2.0,
        )
        annotated_records = [
            NoteProvenance.from_note(
                note,
                origin=record.origin,
                confidence=record.confidence,
                tier=record.tier,
                confidence_basis=record.confidence_basis,
                family=record.family,
                sources=tuple(
                    dict.fromkeys([*record.sources, "hummed-snippet"])
                ),
                details={
                    **record.details,
                    "snippet_index": index,
                    "snippet_reference": str(reference.resolve()),
                    "snippet_hum": str(hum.resolve()),
                    "snippet_start_seconds": round(start, 6),
                },
            )
            for note, record in zip(notes, records)
        ]
        accepted_pairs.extend(zip(notes, annotated_records))
        reports.append(
            {
                "index": index,
                "reference": str(reference.resolve()),
                "hum": str(hum.resolve()),
                "start_seconds": round(start, 6),
                "reference_duration_seconds": (
                    round(reference_duration, 6)
                    if reference_duration is not None
                    else None
                ),
                "hum_duration_seconds": (
                    round(hum_duration, 6) if hum_duration is not None else None
                ),
                "guide_note_count": len(guide_notes),
                "accepted_note_count": len(notes),
                "alignment": alignment,
                "warnings": snippet_warnings,
            }
        )
        warnings.extend(snippet_warnings)

    accepted_pairs = _select_non_overlapping_snippet_notes(accepted_pairs)
    snippet_notes = [note for note, _ in accepted_pairs]
    snippet_records = [record for _, record in accepted_pairs]
    accepted_snippets = len(
        {
            int(record.details["snippet_index"])
            for record in snippet_records
            if "snippet_index" in record.details
        }
    )
    summary = {
        "mode": "snippets",
        "status": "complete" if snippet_notes else "no-evidence",
        "snippet_count": len(reports),
        "accepted_snippet_count": accepted_snippets,
        "guide_note_count": sum(report["guide_note_count"] for report in reports),
        "accepted_note_count": len(snippet_notes),
        "preferred": bool(prefer_guide and snippet_notes),
        "snippets": reports,
        "warnings": list(dict.fromkeys(warnings)),
    }
    if not snippet_notes:
        warning = (
            "Hummed snippets produced no notes supported by the full source contour."
        )
        result.diagnostics = replace(
            result.diagnostics,
            warnings=tuple(
                [*result.diagnostics.warnings, *summary["warnings"], warning]
            ),
        )
        return result, summary

    patched_notes, patched_records = _patch_base_with_snippets(
        base_notes,
        base_records,
        snippet_notes,
        snippet_records,
        config=config,
    )
    result.variants["snippet_guides"] = snippet_notes
    result.provenance["snippet_guides"] = snippet_records
    result.descriptions["snippet_guides"] = (
        "Only the short hummed excerpts, positioned in the full song and retained "
        "where the source vocal contour supports them."
    )
    result.variants["snippet_patched"] = patched_notes
    result.provenance["snippet_patched"] = patched_records
    result.descriptions["snippet_patched"] = (
        f"The automatic {base_variant.replace('_', ' ')} melody with source-supported "
        "short hummed excerpts replacing only their overlapping notes."
    )
    if prefer_guide:
        result.primary_variant = "snippet_patched"
    result.diagnostics = replace(
        result.diagnostics,
        guide_used=True,
        warnings=tuple(
            [*result.diagnostics.warnings, *summary["warnings"]]
        ),
    )
    summary["base_variant"] = base_variant
    summary["patched_note_count"] = len(patched_notes)
    return result, summary


def add_hummed_guide_variant(
    result: VocalTranscription,
    guide_path: str | Path,
    *,
    config: VocalConfig,
    grid: Any | None = None,
    offset_seconds: float | None = None,
    prefer_guide: bool = False,
) -> tuple[VocalTranscription, dict[str, Any]]:
    """Add an evidence-gated melody variant from a roughly hummed guide."""

    guide = Path(guide_path).expanduser()
    if not guide.is_file():
        raise ValueError(f"Hummed guide WAV not found: {guide}")
    guide_notes, warnings = _transcribe_hummed_notes(
        guide,
        config=config,
        grid=grid,
    )
    notes, provenance, alignment = align_hummed_guide(
        result.contour,
        guide_notes,
        config=config,
        offset_seconds=offset_seconds,
    )
    alignment.update(
        {
            "guide": str(guide.resolve()),
            "guide_note_count": len(guide_notes),
            "accepted_note_count": len(notes),
            "warnings": warnings,
        }
    )
    if not notes:
        warning = "Hummed guide produced no notes supported by the source contour."
        result.diagnostics = replace(
            result.diagnostics,
            warnings=tuple([*result.diagnostics.warnings, *warnings, warning]),
        )
        alignment["status"] = "no-evidence"
        return result, alignment

    result.variants["guide_assisted"] = notes
    result.provenance["guide_assisted"] = provenance
    result.descriptions["guide_assisted"] = (
        "Hummed rhythm and contour, automatically aligned and retained only where the source stem supports the resulting pitch."
    )
    if prefer_guide:
        result.primary_variant = "guide_assisted"
    result.diagnostics = replace(
        result.diagnostics,
        guide_used=True,
        warnings=tuple([*result.diagnostics.warnings, *warnings]),
    )
    alignment["status"] = "complete"
    alignment["preferred"] = bool(prefer_guide)
    return result, alignment


def _transcribe_hummed_notes(
    guide: Path,
    *,
    config: VocalConfig,
    grid: Any | None,
) -> tuple[list[NoteEvent], list[str]]:
    guide_config = replace(config, role="lead", phrase_repair=False)
    warnings: list[str] = []
    if guide_config.tracker_mode == "consensus":
        guide_frames, tracker_warnings = extract_consensus_pitch_frames(
            guide, config=guide_config
        )
        warnings.extend(tracker_warnings)
    else:
        guide_frames = extract_pitch_frames(guide, config=guide_config)
    guide_result = transcribe_vocal_frames(
        guide_frames,
        config=guide_config,
        grid=grid,
    )
    return list(guide_result.notes), warnings


def _select_non_overlapping_snippet_notes(
    pairs: Sequence[tuple[NoteEvent, NoteProvenance]],
) -> list[tuple[NoteEvent, NoteProvenance]]:
    """Resolve accidentally overlapping snippet submissions conservatively."""

    accepted: list[tuple[NoteEvent, NoteProvenance]] = []
    for note, record in sorted(
        pairs,
        key=lambda item: (
            item[0].start,
            -item[1].confidence,
            item[0].pitch,
            item[0].end,
        ),
    ):
        if accepted and accepted[-1][0].end > note.start:
            previous_note, previous_record = accepted[-1]
            if record.confidence > previous_record.confidence:
                accepted[-1] = (note, record)
            continue
        accepted.append((note, record))
    return accepted


def _patch_base_with_snippets(
    base_notes: Sequence[NoteEvent],
    base_records: Sequence[NoteProvenance],
    snippet_notes: Sequence[NoteEvent],
    snippet_records: Sequence[NoteProvenance],
    *,
    config: VocalConfig,
) -> tuple[list[NoteEvent], list[NoteProvenance]]:
    """Replace only automatic notes that overlap accepted snippet notes."""

    fallback_records = [
        NoteProvenance.from_note(
            note,
            origin="repaired",
            confidence=0.5,
            tier="possible",
            confidence_basis="aggregate",
            family="vocals" if config.role == "lead" else "backing_vocals",
            sources=("automatic-vocal-melody",),
        )
        for note in base_notes[len(base_records) :]
    ]
    base_pairs = list(zip(base_notes, [*base_records, *fallback_records]))

    def replaced(note: NoteEvent) -> bool:
        midpoint = (note.start + note.end) / 2.0
        for snippet in snippet_notes:
            overlap = min(note.end, snippet.end) - max(note.start, snippet.start)
            if overlap > 0.0 or snippet.start - 0.03 <= midpoint <= snippet.end + 0.03:
                return True
        return False

    combined = [pair for pair in base_pairs if not replaced(pair[0])]
    combined.extend(zip(snippet_notes, snippet_records))
    combined.sort(key=lambda item: (item[0].start, item[0].pitch, item[0].end))
    return (
        [note for note, _ in combined],
        [record for _, record in combined],
    )


def _audio_duration(path: Path) -> float | None:
    try:
        import soundfile

        return float(soundfile.info(str(path)).duration)
    except Exception:
        return None


def align_hummed_guide(
    source_frames: Sequence[PitchFrame],
    guide_notes: Sequence[NoteEvent],
    *,
    config: VocalConfig,
    offset_seconds: float | None = None,
    maximum_auto_offset_seconds: float = 8.0,
    offset_search_radius_seconds: float = 0.0,
) -> tuple[list[NoteEvent], list[NoteProvenance], dict[str, Any]]:
    """Align guide rhythm to source F0 and reject unsupported guide notes."""

    frames = list(source_frames)
    guide = sorted(guide_notes, key=lambda note: (note.start, note.pitch, note.end))
    if not frames or not guide:
        return (
            [],
            [],
            {
                "status": "no-evidence",
                "offset_seconds": offset_seconds,
                "transpose_semitones": None,
                "alignment_score": 0.0,
            },
        )
    if maximum_auto_offset_seconds < 0 or not math.isfinite(
        maximum_auto_offset_seconds
    ):
        raise ValueError("maximum_auto_offset_seconds must be finite and non-negative")
    if offset_seconds is not None and not math.isfinite(offset_seconds):
        raise ValueError("offset_seconds must be finite")
    if (
        not math.isfinite(offset_search_radius_seconds)
        or offset_search_radius_seconds < 0
    ):
        raise ValueError(
            "offset_search_radius_seconds must be finite and non-negative"
        )

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
    step = (
        min(0.10, max(0.04, 60.0 / float(config.bpm) / 8.0))
        if config.bpm is not None and config.bpm > 0
        else 0.08
    )
    if offset_seconds is None:
        count = int(math.floor(maximum_auto_offset_seconds / step))
        offsets = [index * step for index in range(-count, count + 1)]
    elif offset_search_radius_seconds > 0:
        count = int(math.floor(offset_search_radius_seconds / step))
        offsets = [
            float(offset_seconds) + index * step
            for index in range(-count, count + 1)
        ]
    else:
        offsets = [float(offset_seconds)]

    best: (
        tuple[float, float, int, list[tuple[NoteEvent, float, float, float]]] | None
    ) = None
    for offset in offsets:
        observations: list[tuple[NoteEvent, float, float, float]] = []
        differences: list[float] = []
        weights: list[float] = []
        for note in guide:
            region = _source_region(
                times,
                midis,
                probabilities,
                start=note.start + offset,
                end=note.end + offset,
            )
            if region is None:
                continue
            source_midi, voiced_fraction, probability = region
            duration = max(0.03, note.end - note.start)
            differences.append(source_midi - note.pitch)
            weights.append(duration * voiced_fraction * probability)
            observations.append((note, source_midi, voiced_fraction, probability))
        if not observations:
            continue
        transpose = max(
            -36, min(36, int(round(_weighted_median(differences, weights))))
        )
        matched_weight = 0.0
        total_weight = 0.0
        voiced_duration = 0.0
        guide_duration = sum(max(0.03, note.end - note.start) for note in guide)
        for note, source_midi, voiced_fraction, probability in observations:
            duration = max(0.03, note.end - note.start)
            weight = duration * voiced_fraction * probability
            distance = abs(source_midi - (note.pitch + transpose))
            matched_weight += weight * max(0.0, 1.0 - distance / 1.5)
            total_weight += weight
            voiced_duration += duration * voiced_fraction
        coverage = len(observations) / len(guide)
        voiced_coverage = voiced_duration / max(guide_duration, 1e-9)
        score = (matched_weight / max(total_weight, 1e-9)) * (
            0.55 + 0.25 * coverage + 0.20 * voiced_coverage
        )
        score -= min(0.02, abs(offset) * 0.0005)
        candidate = (score, offset, transpose, observations)
        if best is None or candidate[:3] > best[:3]:
            best = candidate
    if best is None:
        return (
            [],
            [],
            {
                "status": "no-evidence",
                "offset_seconds": offset_seconds,
                "transpose_semitones": None,
                "alignment_score": 0.0,
            },
        )

    score, offset, transpose, observations = best
    notes: list[NoteEvent] = []
    records: list[NoteProvenance] = []
    for guide_note, source_midi, voiced_fraction, probability in observations:
        intended = guide_note.pitch + transpose
        distance = abs(source_midi - intended)
        if voiced_fraction < 0.20 or probability < config.uncertain_voicing:
            continue
        if distance > 1.50:
            continue
        pitch = max(0, min(127, int(math.floor(source_midi + 0.5))))
        start = max(0.0, guide_note.start + offset)
        end = max(start + config.min_note_ms / 1000.0, guide_note.end + offset)
        note = NoteEvent(start, end, pitch, guide_note.velocity)
        if notes and notes[-1].end > note.start:
            previous = notes[-1]
            boundary = max(previous.start + 0.03, min(note.start, previous.end))
            if boundary >= note.end - 0.03:
                continue
            notes[-1] = NoteEvent(
                previous.start,
                boundary,
                previous.pitch,
                previous.velocity,
            )
            previous_record = records.pop()
            records.append(
                NoteProvenance.from_note(
                    notes[-1],
                    origin=previous_record.origin,
                    confidence=previous_record.confidence,
                    tier=previous_record.tier,
                    confidence_basis=previous_record.confidence_basis,
                    family=previous_record.family,
                    sources=previous_record.sources,
                    details=previous_record.details,
                )
            )
            note = NoteEvent(boundary, note.end, note.pitch, note.velocity)
        closeness = max(0.0, 1.0 - distance / 1.5)
        confidence = max(
            0.0,
            min(1.0, 0.50 * probability + 0.25 * voiced_fraction + 0.25 * closeness),
        )
        notes.append(note)
        records.append(
            NoteProvenance.from_note(
                note,
                origin="repaired",
                confidence=confidence,
                tier="main" if confidence >= 0.55 else "possible",
                confidence_basis="measured",
                family="vocals" if config.role == "lead" else "backing_vocals",
                sources=("hummed-guide", "source-contour", "guide-alignment"),
                details={
                    "guide_pitch": guide_note.pitch,
                    "guide_transpose_semitones": transpose,
                    "guide_offset_seconds": round(offset, 6),
                    "source_median_midi": round(source_midi, 6),
                    "source_voiced_fraction": round(voiced_fraction, 6),
                    "source_voiced_probability": round(probability, 6),
                },
            )
        )
    return (
        notes,
        records,
        {
            "status": "complete" if notes else "no-evidence",
            "offset_seconds": round(offset, 6),
            "transpose_semitones": transpose,
            "alignment_score": round(max(0.0, score), 6),
            "source_supported_notes": len(notes),
        },
    )


def write_melody_correction_artifacts(
    stem_path: str | Path,
    result: VocalTranscription,
    *,
    out_dir: str | Path,
    bpm: float,
    key: str | None,
    role: str,
    primary_midi: str | Path | None,
    guide_alignment: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Write an editable JSON seed and a self-contained local HTML editor."""

    stem = Path(stem_path).expanduser().resolve()
    destination = Path(out_dir).expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    notes = list(result.notes)
    template = {
        "format": CORRECTION_FORMAT,
        "format_version": 1,
        "source_stem": str(stem),
        "source_midi": str(primary_midi) if primary_midi is not None else None,
        "source_variant": result.primary_variant,
        "bpm": float(bpm),
        "key": key,
        "role": role,
        "tuning_hz": float(result.diagnostics.tuning_hz),
        "garageband_fine_tune_cents": float(
            result.diagnostics.garageband_fine_tune_cents
        ),
        "channel": 2 if role == "lead" else 3,
        "program": 73 if role == "lead" else 65,
        "guide_alignment": guide_alignment,
        "notes": [_note_dict(note) for note in notes],
    }
    json_path = destination / "melody_corrections.json"
    _write_json(json_path, template)
    waveform = _waveform_points(stem)
    contour = [
        {
            "time": round(frame.time, 6),
            "midi": (
                round(
                    hz_to_fractional_midi(frame.f0_hz, result.diagnostics.tuning_hz),
                    5,
                )
                if frame.f0_hz is not None
                else None
            ),
            "probability": round(frame.voiced_probability, 5),
        }
        for frame in _downsample(result.contour, 5000)
    ]
    html_path = destination / "melody_correction.html"
    html_path.write_text(
        _correction_html(template, waveform, contour, stem.as_uri()),
        encoding="utf-8",
    )
    return {"html": str(html_path), "json": str(json_path)}


def apply_melody_corrections(
    corrections_path: str | Path,
    *,
    out_path: str | Path,
) -> dict[str, Any]:
    """Validate a browser-exported correction document and write tuned MIDI."""

    corrections = Path(corrections_path).expanduser()
    output = Path(out_path).expanduser()
    if not corrections.is_file():
        raise ValueError(f"Correction JSON not found: {corrections}")
    if output.exists():
        raise ValueError(f"Output MIDI already exists: {output}")
    if output.suffix.lower() not in {".mid", ".midi"}:
        raise ValueError("Corrected MIDI output must end in .mid or .midi")
    document = json.loads(corrections.read_text(encoding="utf-8"))
    if document.get("format") != CORRECTION_FORMAT:
        raise ValueError(f"Correction JSON must use format {CORRECTION_FORMAT}")
    source_sha256 = document.get("source_stem_sha256")
    if source_sha256 is not None:
        source = Path(str(document.get("source_stem", ""))).expanduser()
        if not source.is_file():
            raise ValueError("Correction JSON source stem is missing")
        if _file_sha256(source) != str(source_sha256):
            raise ValueError("Correction JSON source stem hash does not match")
    review = document.get("review")
    if isinstance(review, dict) and review.get("format") == (
        "sunofriend.melody-phrase-review.v1"
    ):
        choices = review.get("choices", [])
        if review.get("status") != "reviewed":
            raise ValueError("Phrase-review correction must be reviewed before apply")
        if not isinstance(choices, list) or not choices or any(
            not isinstance(choice, dict)
            or not choice.get("reviewed")
            or choice.get("selected")
            not in {"basic-pitch", "game-boundary", "combined"}
            for choice in choices
        ):
            raise ValueError("Phrase-review correction has incomplete choices")
    bpm = float(document.get("bpm", 0.0))
    if not math.isfinite(bpm) or bpm <= 0:
        raise ValueError("Correction JSON bpm must be positive")
    notes = [
        NoteEvent(
            float(value["start"]),
            float(value["end"]),
            int(value["pitch"]),
            int(value.get("velocity", 90)),
        )
        for value in document.get("notes", [])
    ]
    from .note_safety import normalize_note_events

    notes = normalize_note_events(notes)
    if not notes:
        raise ValueError("Correction JSON contains no valid notes")
    tuning_cents = float(document.get("garageband_fine_tune_cents", 0.0))
    if not math.isfinite(tuning_cents) or abs(tuning_cents) > 200.0:
        raise ValueError("Correction JSON tuning must be finite and within ±200 cents")
    channel = int(document.get("channel", 2))
    program = int(document.get("program", 73))
    if not 0 <= channel <= 15:
        raise ValueError("Correction JSON channel must be from 0 to 15")
    if not 0 <= program <= 127:
        raise ValueError("Correction JSON program must be from 0 to 127")
    from .midi import MidiTrack, write_midi_file

    write_midi_file(
        output,
        [
            MidiTrack(
                "Corrected Vocal Melody",
                channel,
                program,
                notes,
                pitch_bend_cents=tuning_cents,
            )
        ],
        bpm=bpm,
    )
    audit = {
        "operation": "melody-apply",
        "status": "complete",
        "format": CORRECTION_FORMAT,
        "corrections": str(corrections.resolve()),
        "output_midi": str(output.resolve()),
        "bpm": bpm,
        "tuning_cents": tuning_cents,
        "note_count": len(notes),
        "review": review,
    }
    audit_path = output.with_suffix(".correction.json")
    _write_json(audit_path, audit)
    audit["audit"] = str(audit_path)
    return audit


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
    voiced_probability = [
        probability
        for value, probability in zip(midis[left:right], probabilities[left:right])
        if value is not None
    ]
    return (
        float(median(values)),
        len(values) / max(1, right - left),
        float(median(voiced_probability)),
    )


def _weighted_median(values: Sequence[float], weights: Sequence[float]) -> float:
    ordered = sorted(zip(values, weights), key=lambda item: item[0])
    total = sum(max(0.0, weight) for _, weight in ordered)
    if total <= 0:
        return float(median(values))
    running = 0.0
    for value, weight in ordered:
        running += max(0.0, weight)
        if running >= total / 2.0:
            return float(value)
    return float(ordered[-1][0])


def _note_dict(note: NoteEvent) -> dict[str, Any]:
    return {
        "start": round(note.start, 6),
        "end": round(note.end, 6),
        "pitch": note.pitch,
        "velocity": note.velocity,
    }


def _waveform_points(path: Path, maximum: int = 3000) -> list[float]:
    try:
        import numpy as np
        import soundfile

        values, _ = soundfile.read(str(path), dtype="float32", always_2d=True)
        mono = np.max(np.abs(values), axis=1) if len(values) else np.asarray([])
        if not len(mono):
            return []
        bins = min(maximum, len(mono))
        edges = np.linspace(0, len(mono), bins + 1, dtype=int)
        peak = max(float(np.max(mono)), 1e-9)
        return [
            round(float(np.max(mono[edges[index] : edges[index + 1]])) / peak, 5)
            for index in range(bins)
            if edges[index + 1] > edges[index]
        ]
    except Exception:
        return []


def _downsample(values: Sequence[Any], maximum: int) -> list[Any]:
    if len(values) <= maximum:
        return list(values)
    step = len(values) / maximum
    return [values[min(len(values) - 1, int(index * step))] for index in range(maximum)]


def _write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _correction_html(
    template: dict[str, Any],
    waveform: Sequence[float],
    contour: Sequence[dict[str, Any]],
    audio_uri: str,
) -> str:
    payload = json.dumps(
        {"document": template, "waveform": waveform, "contour": contour},
        separators=(",", ":"),
    ).replace("</", "<\\/")
    safe_audio = html.escape(audio_uri, quote=True)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend Melody Correction</title>
<style>
body{{font:15px system-ui,sans-serif;margin:0;background:#10151b;color:#eef3f7}}
main{{max-width:1200px;margin:auto;padding:20px}} h1{{margin:0 0 8px}}
.panel{{background:#19222c;border:1px solid #334252;border-radius:10px;padding:14px;margin:14px 0}}
canvas{{width:100%;height:460px;background:#0b1015;border-radius:8px;cursor:pointer}}
button{{margin:3px;padding:7px 10px;background:#253546;color:#fff;border:1px solid #526579;border-radius:6px}}
button:hover{{background:#36506a}} .selected{{color:#ffd34e}} code{{color:#9ed9ff}}
</style></head><body><main>
<h1>Sunofriend melody correction</h1>
<p>Click a note, adjust it, audition the source, then export the edited JSON and run <code>sunofriend melody-apply</code>.</p>
<div class="panel"><audio controls src="{safe_audio}" style="width:100%"></audio></div>
<div class="panel"><canvas id="roll" width="1160" height="460"></canvas></div>
<div class="panel">
<span id="selection">No note selected</span><br>
<button data-action="down12">Octave −</button><button data-action="down1">Semitone −</button>
<button data-action="up1">Semitone +</button><button data-action="up12">Octave +</button>
<button data-action="left">Start earlier</button><button data-action="right">Start later</button>
<button data-action="shorter">Shorter</button><button data-action="longer">Longer</button>
<button data-action="split">Split</button><button data-action="merge">Merge next</button>
<button data-action="delete">Delete</button><button data-action="reset">Reset</button>
<button data-action="export">Export corrections JSON</button>
</div>
<script>const DATA={payload};
let doc=structuredClone(DATA.document), original=structuredClone(DATA.document), selected=-1;
const canvas=document.getElementById('roll'),ctx=canvas.getContext('2d'),label=document.getElementById('selection');
function extent(){{let n=doc.notes;return Math.max(1,...n.map(x=>x.end),...DATA.contour.map(x=>x.time||0));}}
function pitchRange(){{let p=[...doc.notes.map(x=>x.pitch),...DATA.contour.filter(x=>x.midi!=null).map(x=>x.midi)];return [Math.floor(Math.min(...p,48))-2,Math.ceil(Math.max(...p,72))+2];}}
function xy(note){{let d=extent(),[lo,hi]=pitchRange();return [note.start/d*canvas.width,(hi-note.pitch)/(hi-lo)*canvas.height,(note.end-note.start)/d*canvas.width,canvas.height/(hi-lo)];}}
function draw(){{ctx.clearRect(0,0,canvas.width,canvas.height);let d=extent(),beat=60/doc.bpm;
ctx.strokeStyle='#22303d';ctx.lineWidth=1;for(let t=0;t<d;t+=beat){{let x=t/d*canvas.width;ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,canvas.height);ctx.stroke();}}
if(DATA.waveform.length){{ctx.fillStyle='#234056';let w=canvas.width/DATA.waveform.length;DATA.waveform.forEach((v,i)=>ctx.fillRect(i*w,canvas.height/2-v*55,w,2*v*55));}}
let [lo,hi]=pitchRange();ctx.strokeStyle='#72a8c7';ctx.lineWidth=1.5;ctx.beginPath();let started=false;DATA.contour.forEach(v=>{{if(v.midi==null){{started=false;return}}let x=v.time/d*canvas.width,y=(hi-v.midi)/(hi-lo)*canvas.height;if(!started)ctx.moveTo(x,y);else ctx.lineTo(x,y);started=true}});ctx.stroke();
doc.notes.forEach((n,i)=>{{let [x,y,w,h]=xy(n);ctx.fillStyle=i===selected?'#ffd34e':'#38c172';ctx.fillRect(x,y-h/2,Math.max(2,w),Math.max(5,h*.72));}});
label.textContent=selected<0?'No note selected':`Selected ${{selected+1}}: MIDI ${{doc.notes[selected].pitch}}, ${{doc.notes[selected].start.toFixed(3)}}–${{doc.notes[selected].end.toFixed(3)}}s`;}}
canvas.onclick=e=>{{let r=canvas.getBoundingClientRect(),x=(e.clientX-r.left)*canvas.width/r.width,y=(e.clientY-r.top)*canvas.height/r.height;selected=doc.notes.findIndex(n=>{{let q=xy(n);return x>=q[0]&&x<=q[0]+q[2]&&y>=q[1]-q[3]&&y<=q[1]+q[3]}});draw();}};
document.querySelectorAll('button').forEach(b=>b.onclick=()=>act(b.dataset.action));
function act(a){{if(a==='reset'){{doc=structuredClone(original);selected=-1;draw();return}}if(a==='export'){{let blob=new Blob([JSON.stringify(doc,null,2)],{{type:'application/json'}}),u=URL.createObjectURL(blob),x=document.createElement('a');x.href=u;x.download='melody-corrections-edited.json';x.click();URL.revokeObjectURL(u);return}}if(selected<0)return;let n=doc.notes[selected];
if(a==='down12')n.pitch=Math.max(0,n.pitch-12);if(a==='down1')n.pitch=Math.max(0,n.pitch-1);if(a==='up1')n.pitch=Math.min(127,n.pitch+1);if(a==='up12')n.pitch=Math.min(127,n.pitch+12);
if(a==='left')n.start=Math.max(0,n.start-.02);if(a==='right')n.start=Math.min(n.end-.03,n.start+.02);if(a==='shorter')n.end=Math.max(n.start+.03,n.end-.02);if(a==='longer')n.end+=.02;
if(a==='delete'){{doc.notes.splice(selected,1);selected=-1}}if(a==='split'&&n.end-n.start>.08){{let m=(n.start+n.end)/2;n.end=m;doc.notes.splice(selected+1,0,{{...n,start:m}})}}if(a==='merge'&&selected+1<doc.notes.length){{let q=doc.notes[selected+1];n.end=Math.max(n.end,q.end);doc.notes.splice(selected+1,1)}}draw();}}
draw();</script></main></body></html>"""


__all__ = [
    "CORRECTION_FORMAT",
    "add_hummed_guide_variant",
    "add_hummed_snippet_variants",
    "align_hummed_guide",
    "apply_melody_corrections",
    "write_melody_correction_artifacts",
]
