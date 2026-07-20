"""Read-only outer comparison of aligned specialist and AI MIDI candidates.

Phase 5's MuScriptor matrix deliberately cannot treat Sunofriend's specialist
MIDI as another model lane.  This module provides the narrower outer boundary:
it verifies one source excerpt, the existing S0/M1/M3 evidence, and an existing
three-unit phrase-review geometry before publishing path-free disagreement
evidence.  It never creates MIDI or makes a musical choice.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping, Sequence

from .clip import read_midi_clips
from .models import NoteEvent
from .note_alignment import AlignmentEvent, AlignmentResult, align_events
from .phrase_repeat import (
    REPEAT_MAXIMUM_CONTENT_TIME_SCALE,
    REPEAT_MAXIMUM_TIMING_P90_BEATS,
    REPEAT_MINIMUM_CONTENT_TIME_SCALE,
    REPEAT_MINIMUM_INTERVAL_MATCH,
    REPEAT_MINIMUM_NOTES,
    REPEAT_MINIMUM_NOTE_DURATION_SIMILARITY,
    REPEAT_MINIMUM_PITCH_MATCH,
    REPEAT_MINIMUM_UNIT_DURATION_RATIO,
)
from .verify import StemSpectrum


HYBRID_REPORT_SCHEMA = "sunofriend.hybrid-candidate-report.v1"
REQUIRED_LANES = ("S0", "M1", "M3")
ONSET_TOLERANCE_SECONDS = 0.080
BOUNDARY_TOLERANCE_SECONDS = 0.080
DUPLICATE_TOLERANCE_SECONDS = 0.020
_SEGMENTATION_POLICY = "consecutive-clusters-to-musical-length-v1"
_SEGMENTATION_ALIGNMENT = "duration-only; no unconfirmed downbeat was assumed"
_REPETITION_SCHEMA = "sunofriend.melody-review-repetition.v1"
_REPETITION_POLICY = "exact-count-source-contour-repeat-v1"
_SAFE_TEXT = re.compile(r"^[^/\\\x00-\x1f\x7f]{1,128}$")


@dataclass(frozen=True)
class _CandidateNote:
    index: int
    start: float
    end: float
    pitch: int
    velocity: int

    @property
    def duration(self) -> float:
        return self.end - self.start

    def as_note_event(self) -> NoteEvent:
        return NoteEvent(self.start, self.end, self.pitch, self.velocity)

    def as_alignment_event(self, *, pitch: int | None = None) -> AlignmentEvent:
        return AlignmentEvent(
            source_index=self.index,
            onset=self.start,
            pitch=self.pitch if pitch is None else pitch,
        )


@dataclass(frozen=True)
class _Phrase:
    index: int
    start: float
    end: float
    duration_bars: float
    length_status: str
    source_phrase_indices: tuple[int, ...]


def write_hybrid_report(
    source_wav: str | Path,
    *,
    role: str,
    bpm: float,
    candidates: Mapping[str, str | Path],
    evidence: Mapping[str, str | Path],
    phrase_review: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Build and atomically publish a report at a fresh output path."""

    output = Path(output_path).expanduser().absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"hybrid candidate report already exists: {output}")
    report = build_hybrid_report(
        source_wav,
        role=role,
        bpm=bpm,
        candidates=candidates,
        evidence=evidence,
        phrase_review=phrase_review,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, output)
        except FileExistsError as exc:
            raise FileExistsError(
                f"hybrid candidate report already exists: {output}"
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return report


def build_hybrid_report(
    source_wav: str | Path,
    *,
    role: str,
    bpm: float,
    candidates: Mapping[str, str | Path],
    evidence: Mapping[str, str | Path],
    phrase_review: str | Path,
) -> dict[str, Any]:
    """Verify and compare exactly S0, M1 and M3 without changing them."""

    source = _existing_file(source_wav, "source WAV")
    normalized_role = _path_free_text(role, "hybrid role")
    if normalized_role != "lead":
        raise ValueError("hybrid candidate report v1 supports the lead role only")
    normalized_bpm = _positive_number(bpm, "hybrid BPM")
    candidate_paths = _named_paths(candidates, "candidate MIDI")
    evidence_paths = _named_paths(evidence, "candidate evidence")
    if len({path.resolve() for path in candidate_paths.values()}) != len(
        REQUIRED_LANES
    ):
        raise ValueError("hybrid candidate MIDI files must be distinct")
    if len({_sha256(path) for path in candidate_paths.values()}) != len(REQUIRED_LANES):
        raise ValueError("hybrid candidate MIDI contents must be distinct")
    review_path = _existing_file(phrase_review, "phrase review")
    input_paths = (
        source,
        review_path,
        *(candidate_paths[lane] for lane in REQUIRED_LANES),
        *(evidence_paths[lane] for lane in REQUIRED_LANES),
    )
    input_fingerprints = _input_fingerprints(input_paths)

    source_record = _wav_record(source)
    review_document = _read_object(review_path, "phrase review")
    phrases = _verify_phrase_review(
        review_document,
        source=source_record,
        role=normalized_role,
        bpm=normalized_bpm,
    )

    lane_notes: dict[str, tuple[_CandidateNote, ...]] = {}
    lane_records: dict[str, dict[str, Any]] = {}
    for lane in REQUIRED_LANES:
        midi_path = candidate_paths[lane]
        notes, embedded_bpms = _read_candidate_notes(
            midi_path,
            source_duration=float(source_record["duration_seconds"]),
            expected_bpm=normalized_bpm,
        )
        evidence_document = _read_object(evidence_paths[lane], f"{lane} evidence")
        evidence_record = _verify_lane_evidence(
            lane,
            evidence_document,
            evidence_path=evidence_paths[lane],
            source=source_record,
            source_path=source,
            midi_path=midi_path,
            notes=notes,
            bpm=normalized_bpm,
            role=normalized_role,
        )
        lane_notes[lane] = notes
        lane_records[lane] = {
            "lane": lane,
            "midi": _file_identity(midi_path),
            "evidence": evidence_record,
            "note_count": len(notes),
            "pitch_range": [
                min(note.pitch for note in notes),
                max(note.pitch for note in notes),
            ],
            "time_range_seconds": [
                _round(min(note.start for note in notes)),
                _round(max(note.end for note in notes)),
            ],
            "embedded_bpms": [_round(value) for value in embedded_bpms],
        }

    spectrum = StemSpectrum(str(source))
    phrase_rows = _phrase_rows(phrases)
    duplicate_records: dict[str, dict[str, Any]] = {}
    for lane in REQUIRED_LANES:
        notes = lane_notes[lane]
        supports = [
            float(spectrum.note_support(note.as_note_event())) for note in notes
        ]
        lane_records[lane]["notes"] = [
            _note_record(note, support, phrases)
            for note, support in zip(notes, supports)
        ]
        duplicates = _duplicate_evidence(notes, phrases)
        lane_records[lane]["duplicate_evidence"] = duplicates
        duplicate_records[lane] = duplicates

    pairwise = []
    for left_lane, right_lane in (("S0", "M1"), ("S0", "M3"), ("M1", "M3")):
        pairwise.append(
            _pairwise_report(
                left_lane,
                lane_notes[left_lane],
                right_lane,
                lane_notes[right_lane],
                phrases,
            )
        )

    rankings = _rank_disagreement_phrases(
        phrase_rows,
        pairwise=pairwise,
        duplicates=duplicate_records,
    )
    repetition = review_document.get("repetition")
    if not isinstance(repetition, dict):
        raise ValueError("phrase review repetition evidence must be an object")
    repetition_record = _verified_repetition_record(
        repetition,
        phrases=phrases,
    )
    segmentation_record = _verified_segmentation_record(
        review_document.get("segmentation"),
        phrases=phrases,
        bpm=normalized_bpm,
    )
    m1_verification = lane_records["M1"]["evidence"]["verification"]
    m3_verification = lane_records["M3"]["evidence"]["verification"]

    report = {
        "schema": HYBRID_REPORT_SCHEMA,
        "status": "diagnostic-only",
        "purpose": (
            "Align one specialist, one caller-supplied full-mix derivative and one "
            "conditioned-stem candidate without creating or selecting a hybrid MIDI."
        ),
        "role": normalized_role,
        "bpm": _round(normalized_bpm),
        "source": source_record,
        "phrase_review": {
            "sha256": _sha256(review_path),
            "bytes": review_path.stat().st_size,
            "schema": review_document.get("schema"),
            "review_unit_count": len(phrases),
            "segmentation": segmentation_record,
        },
        "lineage": {
            "comparison_source": {
                "status": "hash-and-size-verified",
                "verified_lanes": ["S0", "M3"],
            },
            "M1_full_mix_association": {
                "status": "caller-supplied-derivation-unverified",
                "full_mix_source": m1_verification["full_mix_source"],
                "reason": (
                    "The label-split pins its own full-mix source, but no supplied "
                    "reproducible lineage manifest proves that source was built from "
                    "this comparison stem or song."
                ),
            },
            "M3_original_source_midi": {
                "status": "manifest-claimed-payload-unverified",
                "sha256": m3_verification["original_source_midi_sha256"],
                "reason": (
                    "The projection manifest names the original MIDI, but that "
                    "payload was not supplied to this report for comparison."
                ),
            },
        },
        "policies": {
            "exact_pitch_onset_tolerance_ms": 80.0,
            "same_pitch_boundary_tolerance_ms": 80.0,
            "octave_equivalent_onset_tolerance_ms": 80.0,
            "duplicate_same_pitch_onset_tolerance_ms": 20.0,
            "cross_boundary_match_counting": (
                "per-phrase counts include one reference for every phrase or "
                "review-unit gap touched by either match endpoint"
            ),
            "source_support": (
                "raw StemSpectrum note_support; diagnostic only, with no threshold "
                "or note deletion"
            ),
        },
        "candidates": [lane_records[lane] for lane in REQUIRED_LANES],
        "phrases": phrase_rows,
        "pairwise": pairwise,
        "ranked_disagreement_phrases": rankings,
        "chord_evidence": {
            "status": "unavailable-unpinned",
            "reason": (
                "No chord timeline hash-pinned to this exact excerpt was supplied; "
                "the report does not infer one."
            ),
        },
        "repetition_evidence": repetition_record,
        "interpretation": {
            "agreement_is_accuracy": False,
            "source_support_is_selection": False,
            "octave_equivalence_is_agreement": False,
            "ranking_is_preference": False,
            "review_required_before_hybrid_midi": True,
            "m1_same_song_derivation_verified": False,
            "m3_original_source_midi_payload_verified": False,
        },
        "effects": {
            "ai_inference_runs": 0,
            "midi_files_created": 0,
            "midi_notes_mutated": 0,
            "source_audio_mutated": False,
            "raw_candidates_mutated": False,
            "automatic_selection": False,
            "automatic_promotion": False,
            "default_changed": False,
        },
    }
    if _input_fingerprints(input_paths) != input_fingerprints:
        raise ValueError("hybrid report input changed while it was being verified")
    return report


def _named_paths(values: Mapping[str, str | Path], label: str) -> dict[str, Path]:
    if not isinstance(values, Mapping) or set(values) != set(REQUIRED_LANES):
        raise ValueError(f"{label} must contain exactly S0, M1 and M3")
    return {
        lane: _existing_file(values[lane], f"{lane} {label}") for lane in REQUIRED_LANES
    }


def _read_candidate_notes(
    path: Path,
    *,
    source_duration: float,
    expected_bpm: float,
) -> tuple[tuple[_CandidateNote, ...], tuple[float, ...]]:
    clips = read_midi_clips(path)
    if not clips:
        raise ValueError(f"hybrid candidate has no MIDI notes: {path.name}")
    tempo_values = sorted(
        {point.bpm for clip in clips for point in clip.tempo_map.tempo_points}
    )
    if not tempo_values or any(
        abs(value - expected_bpm) > 0.001 for value in tempo_values
    ):
        raise ValueError(
            f"hybrid candidate BPM does not match {expected_bpm:g}: {path.name}"
        )
    rows = sorted(
        (
            float(note.source_start_seconds),
            float(note.source_end_seconds),
            int(note.pitch),
            int(note.velocity),
            track_index,
            note_index,
        )
        for track_index, clip in enumerate(clips)
        for note_index, note in enumerate(clip.notes)
    )
    if not rows:
        raise ValueError(f"hybrid candidate has no MIDI notes: {path.name}")
    notes = tuple(
        _CandidateNote(index, start, end, pitch, velocity)
        for index, (start, end, pitch, velocity, _track, _note) in enumerate(rows)
    )
    for note in notes:
        if note.start < -1e-9 or note.end > source_duration + 1e-6:
            raise ValueError(
                f"hybrid candidate note lies outside the source excerpt: {path.name}"
            )
        if note.end <= note.start:
            raise ValueError(f"hybrid candidate note has no duration: {path.name}")
    return notes, tuple(tempo_values)


def _verify_phrase_review(
    document: Mapping[str, Any],
    *,
    source: Mapping[str, Any],
    role: str,
    bpm: float,
) -> tuple[_Phrase, ...]:
    if document.get("schema") != "sunofriend.melody-phrase-review.v1":
        raise ValueError("hybrid report requires a melody phrase-review v1 manifest")
    if document.get("status") != "review-required":
        raise ValueError("hybrid report requires an unresolved phrase-review manifest")
    if document.get("raw_candidates_mutated") is not False:
        raise ValueError("phrase review does not preserve its raw candidates")
    if document.get("selection_policy") != (
        "human phrase choice; raw Basic Pitch and agreed-F0 boundary candidates "
        "remain unchanged"
    ):
        raise ValueError("phrase review has an unsupported selection policy")
    review_source = document.get("source")
    if not isinstance(review_source, Mapping):
        raise ValueError("phrase review has no source evidence")
    review_bytes = _json_integer(
        review_source.get("bytes"), "phrase review source bytes"
    )
    if (
        review_source.get("sha256") != source["sha256"]
        or review_bytes != source["bytes"]
    ):
        raise ValueError("phrase review source does not match the hybrid source")
    if _positive_number(document.get("bpm"), "phrase review BPM") != bpm:
        raise ValueError("phrase review BPM does not match the hybrid BPM")
    if document.get("role") != role:
        raise ValueError("phrase review role does not match the hybrid role")
    review_unit_count = _json_integer(
        document.get("review_unit_count"), "phrase review unit count"
    )
    if review_unit_count <= 0:
        raise ValueError("hybrid report requires at least one phrase-review unit")
    phrase_values = document.get("phrases")
    if not isinstance(phrase_values, list) or len(phrase_values) != review_unit_count:
        raise ValueError("phrase review unit count does not match its phrase records")
    if (
        _json_integer(document.get("phrase_count"), "phrase review phrase count")
        != review_unit_count
    ):
        raise ValueError("phrase review phrase count is inconsistent")
    source_phrase_count = _positive_integer(
        document.get("source_phrase_count"), "phrase review source phrase count"
    )
    segmentation = document.get("segmentation")
    if (
        not isinstance(segmentation, Mapping)
        or _json_integer(
            segmentation.get("review_unit_count"), "phrase segmentation unit count"
        )
        != review_unit_count
    ):
        raise ValueError("phrase review segmentation unit count is inconsistent")
    if (
        _positive_integer(
            segmentation.get("source_phrase_count"),
            "phrase segmentation source phrase count",
        )
        != source_phrase_count
    ):
        raise ValueError("phrase review source phrase count is inconsistent")
    if segmentation.get("raw_phrase_records_mutated") is not False:
        raise ValueError("phrase review does not preserve its raw phrase records")
    phrases: list[_Phrase] = []
    phrase_indices: set[int] = set()
    source_phrase_indices: set[int] = set()
    duration = float(source["duration_seconds"])
    for position, value in enumerate(phrase_values, start=1):
        if not isinstance(value, Mapping):
            raise ValueError(f"phrase review unit {position} is malformed")
        phrase_index = _json_integer(
            value.get("phrase_index"), f"phrase {position} index"
        )
        if phrase_index < 0 or phrase_index in phrase_indices:
            raise ValueError("phrase review indices must be unique and non-negative")
        phrase_indices.add(phrase_index)
        start = _finite_number(value.get("start_seconds"), f"phrase {position} start")
        end = _finite_number(value.get("end_seconds"), f"phrase {position} end")
        stated_duration = _finite_number(
            value.get("duration_seconds"), f"phrase {position} duration"
        )
        if start < 0 or end <= start or end > duration + 1e-6:
            raise ValueError(
                f"phrase review unit {position} has invalid source geometry"
            )
        if abs(stated_duration - (end - start)) > 1e-6:
            raise ValueError(f"phrase review unit {position} duration is inconsistent")
        if phrases and start < phrases[-1].end:
            raise ValueError("phrase review units must be non-overlapping")
        duration_bars = _positive_number(
            value.get("duration_bars"), f"phrase {position} duration bars"
        )
        length_status = value.get("length_status")
        if length_status not in {
            "within-range",
            "short-source-or-isolated",
            "exceeds-maximum",
        }:
            raise ValueError(f"phrase review unit {position} has invalid length status")
        source_indices_value = value.get("source_phrase_indices")
        if not isinstance(source_indices_value, list):
            raise ValueError(
                f"phrase review unit {position} has no source phrase indices"
            )
        unit_source_count = _positive_integer(
            value.get("source_phrase_count"),
            f"phrase {position} source phrase count",
        )
        unit_source_indices = tuple(
            _nonnegative_integer(item, f"phrase {position} source phrase index")
            for item in source_indices_value
        )
        if (
            len(unit_source_indices) != unit_source_count
            or tuple(sorted(set(unit_source_indices))) != unit_source_indices
            or source_phrase_indices & set(unit_source_indices)
        ):
            raise ValueError("phrase review source phrase membership is inconsistent")
        source_phrase_indices.update(unit_source_indices)
        phrases.append(
            _Phrase(
                phrase_index,
                start,
                end,
                duration_bars,
                length_status,
                unit_source_indices,
            )
        )
    if source_phrase_indices != set(range(source_phrase_count)):
        raise ValueError("phrase review source phrases are not covered exactly once")
    return tuple(phrases)


def _verified_segmentation_record(
    value: Any, *, phrases: Sequence[_Phrase], bpm: float
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("phrase review segmentation must be an object")
    if value.get("policy") != _SEGMENTATION_POLICY:
        raise ValueError("phrase review segmentation has an unsupported policy")
    if value.get("bar_alignment") != _SEGMENTATION_ALIGNMENT:
        raise ValueError("phrase review segmentation has unsupported bar alignment")
    if value.get("raw_phrase_records_mutated") is not False:
        raise ValueError("phrase review does not preserve its raw phrase records")
    if _json_integer(
        value.get("review_unit_count"), "phrase segmentation unit count"
    ) != len(phrases):
        raise ValueError("phrase review segmentation unit count is inconsistent")
    source_phrase_count = _nonnegative_integer(
        value.get("source_phrase_count"), "phrase segmentation source phrase count"
    )
    if source_phrase_count != sum(
        len(phrase.source_phrase_indices) for phrase in phrases
    ):
        raise ValueError("phrase segmentation source phrase count is inconsistent")
    minimum_bars = _positive_integer(
        value.get("minimum_bars"), "phrase segmentation minimum bars"
    )
    maximum_bars = _positive_integer(
        value.get("maximum_bars"), "phrase segmentation maximum bars"
    )
    beats_per_bar = _positive_integer(
        value.get("beats_per_bar"), "phrase segmentation beats per bar"
    )
    if maximum_bars < minimum_bars:
        raise ValueError("phrase segmentation maximum bars is below its minimum")
    bar_seconds = _positive_number(
        value.get("bar_seconds"), "phrase segmentation bar seconds"
    )
    short_count = _nonnegative_integer(
        value.get("short_unit_count"), "phrase segmentation short unit count"
    )
    long_count = _nonnegative_integer(
        value.get("long_unit_count"), "phrase segmentation long unit count"
    )
    expected_bar_seconds = 60.0 / bpm * beats_per_bar
    if abs(bar_seconds - expected_bar_seconds) > 1e-8:
        raise ValueError("phrase segmentation bar seconds disagree with BPM")
    warnings = value.get("warnings")
    if not isinstance(warnings, list) or any(
        not isinstance(item, str) for item in warnings
    ):
        raise ValueError("phrase review segmentation warnings must be text")
    minimum_seconds = minimum_bars * bar_seconds
    maximum_seconds = maximum_bars * bar_seconds
    expected_statuses = []
    for phrase in phrases:
        duration = phrase.end - phrase.start
        expected_bars = _round(duration / bar_seconds, 6)
        if not math.isclose(
            phrase.duration_bars, expected_bars, rel_tol=0.0, abs_tol=1e-6
        ):
            raise ValueError("phrase duration bars disagree with segmentation")
        if duration < minimum_seconds - 1e-9:
            expected_status = "short-source-or-isolated"
        elif duration > maximum_seconds + 1e-9:
            expected_status = "exceeds-maximum"
        else:
            expected_status = "within-range"
        if phrase.length_status != expected_status:
            raise ValueError("phrase length status disagrees with segmentation")
        expected_statuses.append(expected_status)
    expected_short_count = expected_statuses.count("short-source-or-isolated")
    expected_long_count = expected_statuses.count("exceeds-maximum")
    if short_count != expected_short_count or long_count != expected_long_count:
        raise ValueError("phrase segmentation length-status counts are inconsistent")
    expected_warnings = []
    if expected_short_count:
        expected_warnings.append(
            f"{expected_short_count} review unit(s) are shorter than {minimum_bars} "
            "bars because the source excerpt or an isolated cluster provides less "
            "material."
        )
    if expected_long_count:
        expected_warnings.append(
            f"{expected_long_count} review unit(s) exceed {maximum_bars} bars "
            "because an original source phrase is longer than the configured maximum."
        )
    if warnings != expected_warnings:
        raise ValueError("phrase segmentation warnings disagree with length statuses")
    return {
        "policy": _SEGMENTATION_POLICY,
        "source_phrase_count": source_phrase_count,
        "review_unit_count": len(phrases),
        "minimum_bars": minimum_bars,
        "maximum_bars": maximum_bars,
        "beats_per_bar": beats_per_bar,
        "bar_seconds": _round(bar_seconds),
        "bar_alignment": _SEGMENTATION_ALIGNMENT,
        "short_unit_count": short_count,
        "long_unit_count": long_count,
        "warning_count": len(warnings),
        "raw_phrase_records_mutated": False,
    }


def _verified_repetition_record(
    document: Mapping[str, Any], *, phrases: Sequence[_Phrase]
) -> dict[str, Any]:
    phrase_by_index = {phrase.index: phrase for phrase in phrases}
    phrase_indices = set(phrase_by_index)
    if document.get("schema") != _REPETITION_SCHEMA:
        raise ValueError("phrase review repetition evidence has an unsupported schema")
    if _json_integer(document.get("review_unit_count"), "repetition unit count") != len(
        phrase_indices
    ):
        raise ValueError("repetition unit count does not match the phrase review")
    if document.get("raw_candidates_mutated") is not False:
        raise ValueError("repetition evidence does not preserve raw candidates")
    policy = document.get("policy")
    if not isinstance(policy, Mapping):
        raise ValueError("repetition policy must be an object")
    fixed_policy = {
        "name": _REPETITION_POLICY,
        "note_count": "exact",
        "absolute_pitch_required": True,
        "automatic_selection": False,
        "human_confirmation_required": True,
    }
    if any(policy.get(key) != expected for key, expected in fixed_policy.items()):
        raise ValueError("repetition evidence has an unsupported policy")
    minimum_notes = _positive_integer(
        policy.get("minimum_notes"), "repetition minimum notes"
    )
    minimum_unit_duration_ratio = _unit_ratio(
        policy.get("minimum_unit_duration_ratio"),
        "repetition minimum unit duration ratio",
    )
    minimum_pitch_match_ratio = _unit_ratio(
        policy.get("minimum_pitch_match_ratio"),
        "repetition minimum pitch match ratio",
    )
    minimum_interval_match_ratio = _unit_ratio(
        policy.get("minimum_interval_match_ratio"),
        "repetition minimum interval match ratio",
    )
    maximum_timing_p90_beats = _positive_number(
        policy.get("maximum_timing_p90_beats"),
        "repetition maximum timing p90",
    )
    minimum_note_duration_similarity = _unit_ratio(
        policy.get("minimum_note_duration_similarity"),
        "repetition minimum note duration similarity",
    )
    scale_range = policy.get("content_time_scale_range")
    if not isinstance(scale_range, list) or len(scale_range) != 2:
        raise ValueError("repetition content time-scale range must have two values")
    scale_low = _positive_number(scale_range[0], "repetition minimum time scale")
    scale_high = _positive_number(scale_range[1], "repetition maximum time scale")
    if scale_high < scale_low:
        raise ValueError("repetition content time-scale range is reversed")
    expected_policy_numbers = (
        (minimum_notes, REPEAT_MINIMUM_NOTES),
        (minimum_unit_duration_ratio, REPEAT_MINIMUM_UNIT_DURATION_RATIO),
        (minimum_pitch_match_ratio, REPEAT_MINIMUM_PITCH_MATCH),
        (minimum_interval_match_ratio, REPEAT_MINIMUM_INTERVAL_MATCH),
        (maximum_timing_p90_beats, REPEAT_MAXIMUM_TIMING_P90_BEATS),
        (
            minimum_note_duration_similarity,
            REPEAT_MINIMUM_NOTE_DURATION_SIMILARITY,
        ),
        (scale_low, REPEAT_MINIMUM_CONTENT_TIME_SCALE),
        (scale_high, REPEAT_MAXIMUM_CONTENT_TIME_SCALE),
    )
    if any(
        not math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=1e-12)
        for actual, expected in expected_policy_numbers
    ):
        raise ValueError("repetition evidence policy thresholds are unsupported")

    pair_records: dict[str, list[dict[str, Any]]] = {}
    pair_ids: dict[str, set[int]] = {}
    for field in ("evaluated_pairs", "accepted_pairs"):
        pairs = document.get(field)
        if not isinstance(pairs, list):
            raise ValueError(f"repetition {field} must be a list")
        records = [
            _verified_repetition_pair(
                pair,
                field=field,
                phrases=phrase_by_index,
            )
            for pair in pairs
        ]
        identifiers = {record["pair_index"] for record in records}
        if len(identifiers) != len(records):
            raise ValueError(f"repetition {field} pair indices must be unique")
        pair_records[field] = records
        pair_ids[field] = identifiers
    expected_pair_endpoints = set(combinations(sorted(phrase_indices), 2))
    evaluated_endpoints = {
        (record["left_phrase_index"], record["right_phrase_index"])
        for record in pair_records["evaluated_pairs"]
    }
    if (
        len(pair_records["evaluated_pairs"]) != len(expected_pair_endpoints)
        or evaluated_endpoints != expected_pair_endpoints
        or pair_ids["evaluated_pairs"] != set(range(len(expected_pair_endpoints)))
    ):
        raise ValueError(
            "repetition evidence does not cover every phrase pair exactly once"
        )
    if _nonnegative_integer(
        document.get("evaluated_pair_count"), "repetition evaluated pair count"
    ) != len(pair_records["evaluated_pairs"]):
        raise ValueError("repetition evaluated pair count is inconsistent")
    if _nonnegative_integer(
        document.get("accepted_pair_count"), "repetition accepted pair count"
    ) != len(pair_records["accepted_pairs"]):
        raise ValueError("repetition accepted pair count is inconsistent")
    for record in pair_records["evaluated_pairs"]:
        expected_status = "accepted" if _repetition_pair_passes(record) else "rejected"
        if record["status"] != expected_status:
            raise ValueError("repetition pair status disagrees with its policy metrics")
    accepted_from_evaluated = {
        record["pair_index"]: record
        for record in pair_records["evaluated_pairs"]
        if record["status"] == "accepted"
    }
    accepted_supplied = {
        record["pair_index"]: record for record in pair_records["accepted_pairs"]
    }
    if accepted_supplied != accepted_from_evaluated:
        raise ValueError("repetition accepted pairs disagree with evaluated pairs")
    groups = document.get("groups")
    if not isinstance(groups, list):
        raise ValueError("repetition groups must be a list")
    group_records = []
    group_indices: set[int] = set()
    grouped_phrases: set[int] = set()
    grouped_pair_indices: set[int] = set()
    for group in groups:
        if not isinstance(group, Mapping) or not isinstance(
            group.get("phrase_indices"), list
        ):
            raise ValueError("repetition groups contain a malformed group")
        group_index = _nonnegative_integer(
            group.get("group_index"), "repetition group index"
        )
        if group_index in group_indices:
            raise ValueError("repetition group indices must be unique")
        group_indices.add(group_index)
        members = [
            _json_integer(value, "repetition group phrase index")
            for value in group["phrase_indices"]
        ]
        if (
            not members
            or len(members) != len(set(members))
            or any(value not in phrase_indices for value in members)
        ):
            raise ValueError("repetition group refers to an unknown phrase index")
        indices = group.get("pair_indices")
        if not isinstance(indices, list):
            raise ValueError("repetition group pair indices must be a list")
        member_pair_indices = [
            _nonnegative_integer(value, "repetition group pair index")
            for value in indices
        ]
        if len(member_pair_indices) != len(set(member_pair_indices)) or any(
            value not in pair_ids["accepted_pairs"] for value in member_pair_indices
        ):
            raise ValueError("repetition group refers to an unknown accepted pair")
        member_set = set(members)
        expected_group_pairs = {
            pair_index
            for pair_index, pair in accepted_from_evaluated.items()
            if pair["left_phrase_index"] in member_set
            and pair["right_phrase_index"] in member_set
        }
        endpoints = {
            endpoint
            for pair_index in member_pair_indices
            for endpoint in (
                accepted_from_evaluated[pair_index]["left_phrase_index"],
                accepted_from_evaluated[pair_index]["right_phrase_index"],
            )
        }
        if (
            set(member_pair_indices) != expected_group_pairs
            or endpoints != member_set
            or grouped_phrases & member_set
            or grouped_pair_indices & set(member_pair_indices)
        ):
            raise ValueError(
                "repetition group does not match its accepted-pair component"
            )
        grouped_phrases |= member_set
        grouped_pair_indices |= set(member_pair_indices)
        group_records.append(
            {
                "group_index": group_index,
                "phrase_indices": members,
                "pair_indices": member_pair_indices,
            }
        )
    expected_grouped_phrases = {
        endpoint
        for pair in accepted_from_evaluated.values()
        for endpoint in (pair["left_phrase_index"], pair["right_phrase_index"])
    }
    if (
        grouped_pair_indices != set(accepted_from_evaluated)
        or grouped_phrases != expected_grouped_phrases
    ):
        raise ValueError("repetition groups do not cover the accepted pairs")
    return {
        "schema": _REPETITION_SCHEMA,
        "policy": {
            **fixed_policy,
            "minimum_notes": minimum_notes,
            "minimum_unit_duration_ratio": _round(minimum_unit_duration_ratio),
            "minimum_pitch_match_ratio": _round(minimum_pitch_match_ratio),
            "minimum_interval_match_ratio": _round(minimum_interval_match_ratio),
            "maximum_timing_p90_beats": _round(maximum_timing_p90_beats),
            "minimum_note_duration_similarity": _round(
                minimum_note_duration_similarity
            ),
            "content_time_scale_range": [_round(scale_low), _round(scale_high)],
        },
        "review_unit_count": len(phrase_indices),
        "evaluated_pair_count": len(pair_records["evaluated_pairs"]),
        "accepted_pair_count": len(pair_records["accepted_pairs"]),
        "evaluated_pairs": pair_records["evaluated_pairs"],
        "accepted_pairs": list(accepted_from_evaluated.values()),
        "groups": group_records,
        "raw_candidates_mutated": False,
    }


def _verified_repetition_pair(
    value: Any, *, field: str, phrases: Mapping[int, _Phrase]
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"repetition {field} contains a malformed pair")
    pair_index = _nonnegative_integer(
        value.get("pair_index"), f"repetition {field} pair index"
    )
    left = _json_integer(
        value.get("left_phrase_index"), f"repetition {field} left index"
    )
    right = _json_integer(
        value.get("right_phrase_index"), f"repetition {field} right index"
    )
    if left == right or left not in phrases or right not in phrases:
        raise ValueError("repetition pair refers to an unknown phrase index")
    status = value.get("status")
    if status not in {"accepted", "rejected"}:
        raise ValueError("repetition pair has an unsupported status")
    record = {
        "pair_index": pair_index,
        "status": status,
        "left_phrase_index": left,
        "right_phrase_index": right,
        "lag_seconds": _round(
            _finite_number(value.get("lag_seconds"), "repetition pair lag"), 6
        ),
        "left_note_count": _nonnegative_integer(
            value.get("left_note_count"), "repetition left note count"
        ),
        "right_note_count": _nonnegative_integer(
            value.get("right_note_count"), "repetition right note count"
        ),
        "unit_duration_ratio": _round(
            _unit_ratio(value.get("unit_duration_ratio"), "repetition duration ratio"),
            6,
        ),
        "pitch_match_ratio": _round(
            _unit_ratio(value.get("pitch_match_ratio"), "repetition pitch ratio"), 6
        ),
        "interval_match_ratio": _round(
            _unit_ratio(value.get("interval_match_ratio"), "repetition interval ratio"),
            6,
        ),
        "timing_p90_beats": _optional_nonnegative_number(
            value.get("timing_p90_beats"), "repetition timing p90"
        ),
        "note_duration_similarity": _round(
            _unit_ratio(
                value.get("note_duration_similarity"),
                "repetition note duration similarity",
            ),
            6,
        ),
        "content_time_scale": _optional_positive_number(
            value.get("content_time_scale"), "repetition content time scale"
        ),
        "similarity_score": _round(
            _unit_ratio(value.get("similarity_score"), "repetition similarity score"),
            6,
        ),
        "absolute_pitch_required": _exact_boolean(
            value.get("absolute_pitch_required"),
            True,
            "repetition pair absolute-pitch policy",
        ),
        "automatic_selection": _exact_boolean(
            value.get("automatic_selection"),
            False,
            "repetition pair automatic-selection policy",
        ),
    }
    left_phrase = phrases[left]
    right_phrase = phrases[right]
    expected_lag = _round(right_phrase.start - left_phrase.start, 6)
    left_duration = left_phrase.end - left_phrase.start
    right_duration = right_phrase.end - right_phrase.start
    expected_duration_ratio = _round(
        min(left_duration, right_duration) / max(left_duration, right_duration),
        6,
    )
    if not math.isclose(record["lag_seconds"], expected_lag, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError("repetition pair lag disagrees with phrase geometry")
    if not math.isclose(
        record["unit_duration_ratio"],
        expected_duration_ratio,
        rel_tol=0.0,
        abs_tol=1e-6,
    ):
        raise ValueError("repetition duration ratio disagrees with phrase geometry")
    expected_reasons = _repetition_rejection_reasons(record)
    reasons = value.get("rejection_reasons")
    if reasons != expected_reasons:
        raise ValueError("repetition rejection reasons disagree with policy metrics")
    timing_p90 = record["timing_p90_beats"]
    timing_similarity = 0.0 if timing_p90 is None else max(0.0, 1.0 - timing_p90 / 0.5)
    expected_score = round(
        0.35 * record["pitch_match_ratio"]
        + 0.25 * record["interval_match_ratio"]
        + 0.20 * timing_similarity
        + 0.10 * record["note_duration_similarity"]
        + 0.10 * record["unit_duration_ratio"],
        6,
    )
    if not math.isclose(
        record["similarity_score"], expected_score, rel_tol=0.0, abs_tol=2e-6
    ):
        raise ValueError("repetition similarity score disagrees with policy metrics")
    record["rejection_reasons"] = expected_reasons
    return record


def _repetition_rejection_reasons(record: Mapping[str, Any]) -> list[str]:
    reasons = []
    left_count = int(record["left_note_count"])
    right_count = int(record["right_note_count"])
    if min(left_count, right_count) < REPEAT_MINIMUM_NOTES:
        reasons.append("insufficient-notes")
    if left_count != right_count:
        reasons.append("note-count-mismatch")
    if float(record["unit_duration_ratio"]) < REPEAT_MINIMUM_UNIT_DURATION_RATIO:
        reasons.append("unit-duration-mismatch")
    if float(record["pitch_match_ratio"]) < REPEAT_MINIMUM_PITCH_MATCH:
        reasons.append("absolute-pitch-mismatch")
    if float(record["interval_match_ratio"]) < REPEAT_MINIMUM_INTERVAL_MATCH:
        reasons.append("contour-interval-mismatch")
    timing_p90 = record["timing_p90_beats"]
    if timing_p90 is None or float(timing_p90) > REPEAT_MAXIMUM_TIMING_P90_BEATS:
        reasons.append("onset-timing-mismatch")
    if (
        float(record["note_duration_similarity"])
        < REPEAT_MINIMUM_NOTE_DURATION_SIMILARITY
    ):
        reasons.append("note-duration-mismatch")
    content_scale = record["content_time_scale"]
    if content_scale is None or not (
        REPEAT_MINIMUM_CONTENT_TIME_SCALE
        <= float(content_scale)
        <= REPEAT_MAXIMUM_CONTENT_TIME_SCALE
    ):
        reasons.append("content-time-scale-mismatch")
    return reasons


def _repetition_pair_passes(record: Mapping[str, Any]) -> bool:
    return not _repetition_rejection_reasons(record)


def _verify_lane_evidence(
    lane: str,
    document: Mapping[str, Any],
    *,
    evidence_path: Path,
    source: Mapping[str, Any],
    source_path: Path,
    midi_path: Path,
    notes: Sequence[_CandidateNote],
    bpm: float,
    role: str,
) -> dict[str, Any]:
    if lane == "S0":
        details = _verify_s0_evidence(
            document,
            source=source,
            source_path=source_path,
            notes=notes,
        )
    elif lane == "M1":
        details = _verify_m1_evidence(
            document,
            source=source,
            midi_path=midi_path,
            notes=notes,
            bpm=bpm,
        )
    else:
        details = _verify_m3_evidence(
            document,
            source=source,
            midi_path=midi_path,
            notes=notes,
            bpm=bpm,
            role=role,
        )
    return {
        "schema": details.pop("schema"),
        "bytes": evidence_path.stat().st_size,
        "sha256": _sha256(evidence_path),
        "verification": details,
    }


def _verify_s0_evidence(
    document: Mapping[str, Any],
    *,
    source: Mapping[str, Any],
    source_path: Path,
    notes: Sequence[_CandidateNote],
) -> dict[str, Any]:
    if (
        _json_integer(document.get("schema_version"), "S0 provenance schema version")
        != 1
    ):
        raise ValueError("S0 evidence must be a Sunofriend provenance v1 document")
    source_stem = _existing_file(document.get("source_stem"), "S0 provenance source")
    if (
        source_stem.resolve() != source_path.resolve()
        or _sha256(source_stem) != source["sha256"]
        or source_stem.stat().st_size != source["bytes"]
    ):
        raise ValueError("S0 provenance source does not match the hybrid source")
    counts = document.get("counts")
    provenance_notes = document.get("notes")
    if (
        not isinstance(counts, Mapping)
        or _json_integer(counts.get("notes"), "S0 provenance note count") != len(notes)
        or not isinstance(provenance_notes, list)
        or len(provenance_notes) != len(notes)
    ):
        raise ValueError("S0 provenance note count does not match its MIDI")
    events: list[AlignmentEvent] = []
    by_index: dict[int, Mapping[str, Any]] = {}
    for index, value in enumerate(provenance_notes):
        if not isinstance(value, Mapping):
            raise ValueError("S0 provenance contains a malformed note")
        start = _finite_number(value.get("start"), "S0 provenance note start")
        end = _finite_number(value.get("end"), "S0 provenance note end")
        pitch = _json_integer(value.get("pitch"), "S0 provenance note pitch")
        velocity = _json_integer(value.get("velocity"), "S0 provenance note velocity")
        if end <= start:
            raise ValueError("S0 provenance note has no duration")
        events.append(AlignmentEvent(index, start, pitch))
        by_index[index] = {"end": end, "velocity": velocity}
    midi_events = [note.as_alignment_event() for note in notes]
    alignment = align_events(
        events,
        midi_events,
        left_offset=0.0,
        right_offset=0.0,
        tolerance=0.002,
        pitch_policy="exact_integer",
        require_exact_label=False,
    )
    if alignment.unmatched_left_indices or alignment.unmatched_right_indices:
        raise ValueError("S0 provenance note onsets do not match its MIDI")
    for match in alignment.matches:
        evidence_note = by_index[match.left_index]
        midi_note = notes[match.right_index]
        if abs(float(evidence_note["end"]) - midi_note.end) > 0.002:
            raise ValueError("S0 provenance note endings do not match its MIDI")
        if evidence_note["velocity"] != midi_note.velocity:
            raise ValueError("S0 provenance velocities do not match its MIDI")
    return {
        "schema": "sunofriend.provenance.v1",
        "source_hash_verified": True,
        "note_count_verified": True,
        "note_payload_verified_with_midi_tick_tolerance": True,
        "variant": _path_free_text(document.get("variant"), "S0 variant"),
        "conversion_mode": _path_free_text(
            document.get("conversion_mode"), "S0 conversion mode"
        ),
    }


def _verify_m1_evidence(
    document: Mapping[str, Any],
    *,
    source: Mapping[str, Any],
    midi_path: Path,
    notes: Sequence[_CandidateNote],
    bpm: float,
) -> dict[str, Any]:
    if document.get("schema") != "sunofriend.ai-label-split.v1":
        raise ValueError("M1 evidence must be an AI label-split v1 report")
    if document.get("status") != "review-required":
        raise ValueError("M1 AI label-split evidence is not review-required")
    if document.get("operation") != "ai-label-split":
        raise ValueError("M1 evidence has an unsupported operation")
    label = _path_free_text(document.get("label"), "M1 model label")
    expected_report_hash = document.get("report_sha256")
    unhashed = dict(document)
    unhashed.pop("report_sha256", None)
    if expected_report_hash != _document_hash(unhashed):
        raise ValueError("M1 AI label-split evidence failed its document hash")
    if _positive_number(document.get("bpm"), "M1 evidence BPM") != bpm:
        raise ValueError("M1 evidence BPM does not match the hybrid BPM")
    artifacts = document.get("artifacts")
    midi_record = (
        artifacts.get("requested-label.mid") if isinstance(artifacts, Mapping) else None
    )
    if not isinstance(midi_record, Mapping) or not _record_matches(
        midi_record, midi_path
    ):
        raise ValueError("M1 evidence does not pin the supplied requested-label MIDI")
    selection = document.get("evidence")
    if not isinstance(selection, Mapping):
        raise ValueError("M1 evidence has no label-selection record")
    selected_count = _positive_integer(
        selection.get("selected_note_count"), "M1 selected note count"
    )
    complement_count = _nonnegative_integer(
        selection.get("complement_note_count"), "M1 complement note count"
    )
    detected_counts = selection.get("detected_label_counts")
    if not isinstance(detected_counts, Mapping):
        raise ValueError("M1 evidence has no detected-label counts")
    normalized_counts = {
        _path_free_text(name, "M1 detected label"): _nonnegative_integer(
            count, "M1 detected-label count"
        )
        for name, count in detected_counts.items()
    }
    selected_indices = selection.get("selected_source_indices")
    complement_indices = selection.get("complement_source_indices")
    if not isinstance(selected_indices, list) or not isinstance(
        complement_indices, list
    ):
        raise ValueError("M1 evidence source-index partitions must be lists")
    selected_index_set = {
        _nonnegative_integer(value, "M1 selected source index")
        for value in selected_indices
    }
    complement_index_set = {
        _nonnegative_integer(value, "M1 complement source index")
        for value in complement_indices
    }
    if (
        selection.get("selection_policy") != "exact-model-reported-instrument-label"
        or selection.get("physical_instrument_identified") is not False
        or len(selected_indices) != selected_count
        or len(selected_index_set) != selected_count
        or len(complement_indices) != complement_count
        or len(complement_index_set) != complement_count
        or selected_index_set & complement_index_set
        or selected_index_set | complement_index_set
        != set(range(selected_count + complement_count))
        or normalized_counts.get(label) != selected_count
        or sum(normalized_counts.values()) != selected_count + complement_count
    ):
        raise ValueError("M1 evidence has an inconsistent exact-label partition")
    effects = document.get("effects")
    required_effects = {
        "automatic_promotion": False,
        "model_rerun": False,
        "source_run_mutated": False,
        "raw_candidate_mutated": False,
        "source_midi_mutated": False,
        "source_partition_events_deleted": 0,
        "source_partition_events_duplicated": 0,
        "source_request_control_byte_identical": True,
        "source_candidate_control_byte_identical": True,
        "unchanged_control_byte_identical": True,
        "selected_audition_velocities_written": selected_count,
    }
    if not isinstance(effects, Mapping) or any(
        effects.get(key) != expected for key, expected in required_effects.items()
    ):
        raise ValueError("M1 evidence has inconsistent mutation or control effects")
    rendering = effects.get("midi_rendering")
    selected_render = (
        rendering.get("requested-label.mid") if isinstance(rendering, Mapping) else None
    )
    if not isinstance(selected_render, Mapping):
        raise ValueError("M1 evidence has no requested-label MIDI-render audit")
    rendered_count = _positive_integer(
        selected_render.get("rendered_midi_note_count"),
        "M1 rendered MIDI note count",
    )
    source_event_count = _positive_integer(
        selected_render.get("source_event_count"), "M1 source event count"
    )
    render_delta = _json_integer(
        selected_render.get("source_event_to_midi_note_count_delta"),
        "M1 source-to-rendered note-count delta",
    )
    counter_fields = {
        "integer_pitch_quantized_event_count": "integer-pitch quantized",
        "onset_tick_quantized_event_count": "onset quantized",
        "end_tick_quantized_event_count": "end quantized",
        "duration_tick_quantized_event_count": "duration quantized",
        "minimum_duration_extended_event_count": "minimum-duration extended",
        "duplicate_same_pitch_tick_onset_collapsed_event_count": (
            "collapsed duplicate"
        ),
        "same_pitch_overlap_truncated_event_count": "truncated overlap",
    }
    render_counters = {
        field: _nonnegative_integer(
            selected_render.get(field), f"M1 {label_text} event count"
        )
        for field, label_text in counter_fields.items()
    }
    duplicate_collapsed = render_counters[
        "duplicate_same_pitch_tick_onset_collapsed_event_count"
    ]
    overlap_truncated = render_counters["same_pitch_overlap_truncated_event_count"]
    if (
        any(
            count > source_event_count
            for field, count in render_counters.items()
            if field != "same_pitch_overlap_truncated_event_count"
        )
        or overlap_truncated > rendered_count
    ):
        raise ValueError("M1 evidence MIDI-render counters exceed possible events")
    if (
        source_event_count != selected_count
        or rendered_count != len(notes)
        or rendered_count > source_event_count
        or rendered_count != source_event_count - duplicate_collapsed
        or render_delta != -duplicate_collapsed
    ):
        raise ValueError("M1 evidence MIDI-render counts do not match its MIDI")
    lossless = selected_render.get("lossless_event_render")
    if not isinstance(lossless, bool) or lossless is not (
        not any(render_counters.values())
    ):
        raise ValueError("M1 evidence has an inconsistent lossless-render flag")
    recorded_signatures = selected_render.get("rendered_midi_note_signatures")
    actual_signatures = _midi_tick_signatures(midi_path)
    if (
        not isinstance(recorded_signatures, list)
        or len(recorded_signatures) != rendered_count
        or _normalized_render_signatures(recorded_signatures) != actual_signatures
    ):
        raise ValueError("M1 evidence MIDI-render signatures do not match its MIDI")
    source_run = document.get("source_run")
    if not isinstance(source_run, Mapping):
        raise ValueError("M1 evidence has no pinned source-run geometry")
    if source_run.get("backend") != "muscriptor":
        raise ValueError("M1 evidence is not a MuScriptor label split")
    duration = _positive_number(
        source_run.get("duration_seconds"), "M1 source duration"
    )
    request = source_run.get("request")
    if not isinstance(request, Mapping):
        raise ValueError("M1 evidence has no pinned source request")
    request_start = _finite_number(request.get("start_seconds"), "M1 request start")
    request_end = _finite_number(request.get("end_seconds"), "M1 request end")
    request_roles = request.get("roles")
    if (
        not isinstance(request_roles, list)
        or not request_roles
        or any(
            _path_free_text(value, "M1 request role") != value
            for value in request_roles
        )
        or len(request_roles) != len(set(request_roles))
        or label not in request_roles
    ):
        raise ValueError("M1 model label is not an exact requested source role")
    source_duration = float(source["duration_seconds"])
    if (
        abs(duration - source_duration) > 1e-6
        or abs(request_start) > 1e-9
        or abs(request_end - source_duration) > 1e-6
    ):
        raise ValueError("M1 source-run geometry does not match the hybrid excerpt")
    source_identity = source_run.get("source")
    if not isinstance(source_identity, Mapping):
        raise ValueError("M1 evidence has no pinned full-mix source identity")
    source_sha256 = _sha256_text(
        source_identity.get("sha256"), "M1 full-mix source SHA-256"
    )
    source_bytes = _positive_integer(source_identity.get("bytes"), "M1 source bytes")
    return {
        "schema": document["schema"],
        "manifest_status_validated": True,
        "manifest_operation_validated": True,
        "backend": "muscriptor",
        "midi_hash_verified": True,
        "raw_selected_event_count_manifest_consistent": True,
        "rendered_midi_note_count_verified": True,
        "rendered_midi_note_count": rendered_count,
        "raw_selected_event_count": source_event_count,
        "duplicate_same_pitch_tick_onset_collapsed_event_count": duplicate_collapsed,
        "same_pitch_overlap_truncated_event_count": overlap_truncated,
        "render_change_event_counts": render_counters,
        "rendered_midi_note_signatures_verified": True,
        "lossless_event_render": lossless,
        "excerpt_geometry_verified": True,
        "mutation_control_claims_validated": True,
        "label_partition_payload_verified": False,
        "source_control_payloads_verified": False,
        "same_song_derivation_verified": False,
        "full_mix_source": {
            "bytes": source_bytes,
            "sha256": source_sha256,
        },
        "exact_model_label": label,
        "manifest_label_in_request_roles": True,
        "physical_instrument_identified": False,
    }


def _verify_m3_evidence(
    document: Mapping[str, Any],
    *,
    source: Mapping[str, Any],
    midi_path: Path,
    notes: Sequence[_CandidateNote],
    bpm: float,
    role: str,
) -> dict[str, Any]:
    if document.get("schema") != "sunofriend.phase5-review-projection.v1":
        raise ValueError("M3 evidence must be a Phase 5 review-projection v1 report")
    if document.get("status") != "complete":
        raise ValueError("M3 review projection is not complete")
    roles = document.get("roles")
    if not isinstance(roles, Mapping):
        raise ValueError("M3 review projection has no role evidence")
    projection_role = "vocals" if role in {"lead", "backing", "vocals"} else role
    role_record = roles.get(projection_role)
    midi_hash = _sha256(midi_path)
    if (
        not isinstance(role_record, Mapping)
        or role_record.get("projected_midi_sha256") != midi_hash
        or role_record.get("excerpt_audio_sha256") != source["sha256"]
    ):
        raise ValueError(
            "M3 review projection does not pin the supplied source and MIDI"
        )
    if _json_integer(role_record.get("note_count"), "M3 projected note count") != len(
        notes
    ):
        raise ValueError("M3 review projection note payload is inconsistent")
    if role_record.get("pitch_velocity_duration_unchanged") is not True:
        raise ValueError("M3 projection does not claim an unchanged note payload")
    original_source_audio_sha256 = _sha256_text(
        role_record.get("source_audio_sha256"), "M3 original source audio SHA-256"
    )
    original_source_midi_sha256 = _sha256_text(
        role_record.get("source_midi_sha256"), "M3 original source MIDI SHA-256"
    )
    transform = document.get("midi_transform")
    transform_fields = (
        "pitch_changed",
        "duration_changed",
        "velocity_changed",
        "note_count_changed",
    )
    if not isinstance(transform, Mapping) or any(
        _json_integer(transform.get(field), f"M3 {field}") != 0
        for field in transform_fields
    ):
        raise ValueError("M3 review projection contains a musical mutation")
    if (
        transform.get("operation") != "midi-anchor"
        or _json_integer(transform.get("semitones"), "M3 semitones") != 0
    ):
        raise ValueError("M3 review projection has an unsupported transform")
    source_bpm = _positive_number(transform.get("source_bpm"), "M3 source BPM")
    target_bpm = _positive_number(transform.get("target_bpm"), "M3 target BPM")
    source_downbeat_seconds = _finite_number(
        transform.get("source_downbeat_seconds"), "M3 source downbeat"
    )
    target_downbeat_beat = _finite_number(
        transform.get("target_downbeat_beat"), "M3 target downbeat"
    )
    shift_ticks = _json_integer(transform.get("shift_ticks"), "M3 shift ticks")
    expected_shift_ticks = round(
        target_downbeat_beat * 480 - source_downbeat_seconds * source_bpm / 60.0 * 480
    )
    if (
        abs(source_bpm - bpm) > 0.001
        or abs(target_bpm - bpm) > 0.001
        or abs(target_downbeat_beat) > 1e-9
        or shift_ticks != expected_shift_ticks
    ):
        raise ValueError(
            "M3 review projection timing does not match the hybrid excerpt"
        )
    excerpt = document.get("source_excerpt")
    if not isinstance(excerpt, Mapping):
        raise ValueError("M3 review projection has no source excerpt geometry")
    excerpt_start = _finite_number(excerpt.get("start_seconds"), "M3 excerpt start")
    excerpt_end = _finite_number(excerpt.get("end_seconds"), "M3 excerpt end")
    excerpt_duration = _positive_number(
        excerpt.get("duration_seconds"), "M3 excerpt duration"
    )
    excerpt_sample_rate = _positive_integer(
        excerpt.get("sample_rate_hz"), "M3 excerpt sample rate"
    )
    excerpt_channels = _positive_integer(excerpt.get("channels"), "M3 excerpt channels")
    excerpt_codec = _path_free_text(excerpt.get("codec"), "M3 excerpt codec")
    expected_codec = _wav_codec(
        str(source["subtype"]),
        container=str(source["format"]),
        endian=str(source["endian"]),
    )
    if (
        excerpt_start < 0
        or abs(excerpt_end - excerpt_start - excerpt_duration) > 1e-6
        or abs(excerpt_duration - float(source["duration_seconds"])) > 1e-6
        or excerpt_sample_rate != source["sample_rate_hz"]
        or excerpt_channels != source["channels"]
        or excerpt_codec != expected_codec
        or abs(source_downbeat_seconds - excerpt_start) > 1e-6
    ):
        raise ValueError("M3 source excerpt geometry does not match the hybrid source")
    effects = document.get("effects")
    if (
        not isinstance(effects, Mapping)
        or effects.get("model_rerun") is not False
        or effects.get("source_audio_mutated") is not False
        or effects.get("source_ai_run_mutated") is not False
        or effects.get("automatic_selection") is not False
        or effects.get("musical_repair") is not False
    ):
        raise ValueError("M3 review projection effects are inconsistent")
    return {
        "schema": document["schema"],
        "source_hash_verified": True,
        "midi_hash_verified": True,
        "note_count_verified": True,
        "projection_manifest_contract_validated": True,
        "projection_manifest_claims_payload_unchanged": True,
        "original_source_midi_payload_verified": False,
        "original_source_midi_sha256": original_source_midi_sha256,
        "original_source_audio_payload_verified": False,
        "original_source_audio_sha256": original_source_audio_sha256,
        "projection_role": projection_role,
        "excerpt_geometry_verified": True,
        "excerpt_media_format_verified": True,
        "mutation_effect_claims_validated": True,
    }


def _pairwise_report(
    left_lane: str,
    left_notes: Sequence[_CandidateNote],
    right_lane: str,
    right_notes: Sequence[_CandidateNote],
    phrases: Sequence[_Phrase],
) -> dict[str, Any]:
    exact = _align(left_notes, right_notes)
    exact_matches = []
    boundary_disputes = []
    for match in exact.matches:
        left = left_notes[match.left_index]
        right = right_notes[match.right_index]
        row = _match_record(match, left, right, phrases)
        exact_matches.append(row)
        if (
            abs(right.end - left.end) > BOUNDARY_TOLERANCE_SECONDS
            or abs(right.duration - left.duration) > BOUNDARY_TOLERANCE_SECONDS
        ):
            boundary_disputes.append(row)
    cross_phrase_matches = [
        row for row in exact_matches if row["cross_phrase_boundary"]
    ]

    exact_left_unmatched = [left_notes[index] for index in exact.unmatched_left_indices]
    exact_right_unmatched = [
        right_notes[index] for index in exact.unmatched_right_indices
    ]
    octave = align_events(
        [
            note.as_alignment_event(pitch=note.pitch % 12)
            for note in exact_left_unmatched
        ],
        [
            note.as_alignment_event(pitch=note.pitch % 12)
            for note in exact_right_unmatched
        ],
        left_offset=0.0,
        right_offset=0.0,
        tolerance=ONSET_TOLERANCE_SECONDS,
        pitch_policy="exact_integer",
        require_exact_label=False,
    )
    octave_matches = []
    used_left: set[int] = set()
    used_right: set[int] = set()
    for match in octave.matches:
        left = left_notes[match.left_index]
        right = right_notes[match.right_index]
        pitch_delta = right.pitch - left.pitch
        if pitch_delta == 0 or pitch_delta % 12 != 0:
            continue
        row = _match_record(match, left, right, phrases)
        row["pitch_delta_semitones"] = pitch_delta
        octave_matches.append(row)
        used_left.add(left.index)
        used_right.add(right.index)

    left_only = [
        _lane_only_record(note, phrases)
        for note in exact_left_unmatched
        if note.index not in used_left
    ]
    right_only = [
        _lane_only_record(note, phrases)
        for note in exact_right_unmatched
        if note.index not in used_right
    ]
    return {
        "left_lane": left_lane,
        "right_lane": right_lane,
        "exact_pitch_onset_matches": exact_matches,
        "cross_phrase_boundary_matches": cross_phrase_matches,
        "same_pitch_boundary_duration_disputes": boundary_disputes,
        "octave_equivalent_onset_disputes": octave_matches,
        "lane_only_notes": {
            left_lane: left_only,
            right_lane: right_only,
        },
        "counts": {
            "exact_pitch_onset_matches": len(exact_matches),
            "cross_phrase_boundary_matches": len(cross_phrase_matches),
            "same_pitch_boundary_duration_disputes": len(boundary_disputes),
            "octave_equivalent_onset_disputes": len(octave_matches),
            f"{left_lane}_only_notes": len(left_only),
            f"{right_lane}_only_notes": len(right_only),
        },
        "per_phrase": [
            _pair_phrase_counts(
                phrase_index,
                exact_matches,
                cross_phrase_matches,
                boundary_disputes,
                octave_matches,
                left_only,
                right_only,
                left_lane,
                right_lane,
            )
            for phrase_index in (phrase.index for phrase in phrases)
        ],
        "outside_phrase_counts": _pair_phrase_counts(
            None,
            exact_matches,
            cross_phrase_matches,
            boundary_disputes,
            octave_matches,
            left_only,
            right_only,
            left_lane,
            right_lane,
        ),
    }


def _align(
    left: Sequence[_CandidateNote], right: Sequence[_CandidateNote]
) -> AlignmentResult:
    return align_events(
        [note.as_alignment_event() for note in left],
        [note.as_alignment_event() for note in right],
        left_offset=0.0,
        right_offset=0.0,
        tolerance=ONSET_TOLERANCE_SECONDS,
        pitch_policy="exact_integer",
        require_exact_label=False,
    )


def _match_record(
    match: Any,
    left: _CandidateNote,
    right: _CandidateNote,
    phrases: Sequence[_Phrase],
) -> dict[str, Any]:
    left_phrase_index = _phrase_index(left.start, phrases)
    right_phrase_index = _phrase_index(right.start, phrases)
    shared_phrase_index = (
        left_phrase_index if left_phrase_index == right_phrase_index else None
    )
    return {
        "left_note_index": left.index,
        "right_note_index": right.index,
        "pitch": left.pitch,
        "left_start_seconds": _round(left.start),
        "right_start_seconds": _round(right.start),
        "onset_delta_ms": _round((right.start - left.start) * 1000.0, 6),
        "end_delta_ms": _round((right.end - left.end) * 1000.0, 6),
        "duration_delta_ms": _round((right.duration - left.duration) * 1000.0, 6),
        "left_phrase_index": left_phrase_index,
        "right_phrase_index": right_phrase_index,
        "phrase_index": shared_phrase_index,
        "cross_phrase_boundary": left_phrase_index != right_phrase_index,
    }


def _lane_only_record(
    note: _CandidateNote, phrases: Sequence[_Phrase]
) -> dict[str, Any]:
    return {
        "note_index": note.index,
        "start_seconds": _round(note.start),
        "end_seconds": _round(note.end),
        "pitch": note.pitch,
        "phrase_index": _phrase_index(note.start, phrases),
    }


def _pair_phrase_counts(
    phrase_index: int | None,
    exact: Sequence[Mapping[str, Any]],
    cross_phrase: Sequence[Mapping[str, Any]],
    boundary: Sequence[Mapping[str, Any]],
    octave: Sequence[Mapping[str, Any]],
    left_only: Sequence[Mapping[str, Any]],
    right_only: Sequence[Mapping[str, Any]],
    left_lane: str,
    right_lane: str,
) -> dict[str, Any]:
    return {
        "phrase_index": phrase_index,
        "exact_pitch_onset_matches": _count_match_phrase(exact, phrase_index),
        "cross_phrase_boundary_matches": _count_cross_phrase_reference(
            cross_phrase, phrase_index
        ),
        "same_pitch_boundary_duration_disputes": _count_match_reference(
            boundary, phrase_index
        ),
        "octave_equivalent_onset_disputes": _count_match_reference(
            octave, phrase_index
        ),
        f"{left_lane}_only_notes": _count_phrase(left_only, phrase_index),
        f"{right_lane}_only_notes": _count_phrase(right_only, phrase_index),
    }


def _count_phrase(rows: Sequence[Mapping[str, Any]], phrase_index: int | None) -> int:
    return sum(row.get("phrase_index") == phrase_index for row in rows)


def _count_match_phrase(
    rows: Sequence[Mapping[str, Any]], phrase_index: int | None
) -> int:
    if phrase_index is None:
        return sum(
            row.get("left_phrase_index") is None
            and row.get("right_phrase_index") is None
            for row in rows
        )
    return sum(row.get("phrase_index") == phrase_index for row in rows)


def _count_cross_phrase_reference(
    rows: Sequence[Mapping[str, Any]], phrase_index: int | None
) -> int:
    return _count_match_reference(rows, phrase_index)


def _count_match_reference(
    rows: Sequence[Mapping[str, Any]], phrase_index: int | None
) -> int:
    """Count a match once for each phrase (or gap) touched by either endpoint."""

    if phrase_index is None:
        return sum(
            row.get("left_phrase_index") is None
            or row.get("right_phrase_index") is None
            for row in rows
        )
    return sum(
        phrase_index in {row.get("left_phrase_index"), row.get("right_phrase_index")}
        for row in rows
    )


def _note_record(
    note: _CandidateNote,
    support: float,
    phrases: Sequence[_Phrase],
) -> dict[str, Any]:
    if not math.isfinite(support):
        raise ValueError("StemSpectrum returned non-finite source support")
    return {
        "note_index": note.index,
        "start_seconds": _round(note.start),
        "end_seconds": _round(note.end),
        "pitch": note.pitch,
        "velocity": note.velocity,
        "raw_source_support": _round(support),
        "phrase_index": _phrase_index(note.start, phrases),
    }


def _duplicate_evidence(
    notes: Sequence[_CandidateNote], phrases: Sequence[_Phrase]
) -> dict[str, Any]:
    by_pitch: dict[int, list[_CandidateNote]] = {}
    for note in notes:
        by_pitch.setdefault(note.pitch, []).append(note)
    groups = []
    for pitch in sorted(by_pitch):
        ordered = sorted(by_pitch[pitch], key=lambda note: (note.start, note.index))
        group: list[_CandidateNote] = []
        for note in ordered:
            if group and note.start - group[0].start > DUPLICATE_TOLERANCE_SECONDS:
                if len(group) > 1:
                    groups.append(group)
                group = []
            group.append(note)
        if len(group) > 1:
            groups.append(group)
    records = [
        {
            "pitch": group[0].pitch,
            "note_indices": [note.index for note in group],
            "onset_span_ms": _round((group[-1].start - group[0].start) * 1000.0, 6),
            "phrase_index": _phrase_index(group[0].start, phrases),
        }
        for group in groups
    ]
    return {
        "policy": "same-pitch onsets within 20 ms; evidence only",
        "group_count": len(records),
        "note_count": sum(len(record["note_indices"]) for record in records),
        "groups": records,
    }


def _phrase_rows(phrases: Sequence[_Phrase]) -> list[dict[str, Any]]:
    return [
        {
            "phrase_index": phrase.index,
            "start_seconds": _round(phrase.start),
            "end_seconds": _round(phrase.end),
            "duration_seconds": _round(phrase.end - phrase.start),
        }
        for phrase in phrases
    ]


def _rank_disagreement_phrases(
    phrases: Sequence[Mapping[str, Any]],
    *,
    pairwise: Sequence[Mapping[str, Any]],
    duplicates: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for phrase in phrases:
        index = int(phrase["phrase_index"])
        cross_phrase = boundary = octave = lane_only = 0
        for pair in pairwise:
            per_phrase = next(
                row for row in pair["per_phrase"] if row["phrase_index"] == index
            )
            cross_phrase += int(per_phrase["cross_phrase_boundary_matches"])
            boundary += int(per_phrase["same_pitch_boundary_duration_disputes"])
            octave += int(per_phrase["octave_equivalent_onset_disputes"])
            lane_only += sum(
                int(value)
                for key, value in per_phrase.items()
                if key.endswith("_only_notes")
            )
        duplicate_groups = sum(
            sum(group.get("phrase_index") == index for group in record["groups"])
            for record in duplicates.values()
        )
        score = cross_phrase + boundary + octave + lane_only + duplicate_groups
        rows.append(
            {
                **phrase,
                "disagreement_evidence_count": score,
                "cross_phrase_boundary_match_references": cross_phrase,
                "same_pitch_boundary_duration_disputes": boundary,
                "octave_equivalent_onset_disputes": octave,
                "lane_only_note_references": lane_only,
                "duplicate_groups": duplicate_groups,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            -int(row["disagreement_evidence_count"]),
            int(row["phrase_index"]),
        ),
    )


def _phrase_index(time_seconds: float, phrases: Sequence[_Phrase]) -> int | None:
    for position, phrase in enumerate(phrases):
        is_last = position == len(phrases) - 1
        if phrase.start <= time_seconds < phrase.end or (
            is_last and time_seconds == phrase.end
        ):
            return phrase.index
    return None


def _wav_record(path: Path) -> dict[str, Any]:
    try:
        import soundfile

        info = soundfile.info(str(path))
        frame_count = int(info.frames)
        sample_rate = int(info.samplerate)
        channels = int(info.channels)
        subtype = str(info.subtype)
        container = str(info.format)
        endian = str(info.endian)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"invalid source WAV: {exc}") from exc
    if sample_rate <= 0 or frame_count <= 0:
        raise ValueError("source WAV must contain audio frames")
    if container not in {"WAV", "WAVEX", "RF64"} or endian not in {
        "FILE",
        "LITTLE",
    }:
        raise ValueError("source WAV must use a little-endian WAV-family container")
    return {
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "frame_count": frame_count,
        "sample_rate_hz": sample_rate,
        "channels": channels,
        "format": container,
        "endian": endian,
        "subtype": subtype,
        "duration_seconds": _round(frame_count / sample_rate),
    }


def _file_identity(path: Path) -> dict[str, Any]:
    return {"bytes": path.stat().st_size, "sha256": _sha256(path)}


def _input_fingerprints(
    paths: Sequence[Path],
) -> dict[str, tuple[int, int, int, int, str]]:
    result = {}
    for path in paths:
        resolved = path.resolve()
        stat = resolved.stat()
        result[str(resolved)] = (
            stat.st_dev,
            stat.st_ino,
            stat.st_size,
            stat.st_mtime_ns,
            _sha256(resolved),
        )
    return result


def _record_matches(record: Mapping[str, Any], path: Path) -> bool:
    try:
        byte_count = _json_integer(record.get("bytes"), "artifact byte count")
    except ValueError:
        return False
    return record.get("sha256") == _sha256(path) and byte_count == path.stat().st_size


def _midi_tick_signatures(path: Path) -> list[tuple[int, int, int, int, int, int]]:
    from .midi_tempo import _scan_midi

    layout = _scan_midi(path.read_bytes())
    if layout.ticks_per_beat != 480:
        raise ValueError("M1 requested-label MIDI must use 480 ticks per beat")
    signatures = [
        (
            owner,
            clip.instrument.channel,
            round(note.start_beat * layout.ticks_per_beat),
            round(note.end_beat * layout.ticks_per_beat),
            note.pitch,
            note.velocity,
        )
        for owner, clip in enumerate(read_midi_clips(path))
        for note in clip.notes
    ]
    return sorted(signatures)


def _normalized_render_signatures(
    values: Sequence[Any],
) -> list[tuple[int, int, int, int, int, int]]:
    expected_keys = {
        "track_index",
        "channel",
        "start_tick",
        "end_tick",
        "pitch",
        "velocity",
    }
    records = []
    for value in values:
        if not isinstance(value, Mapping) or set(value) != expected_keys:
            raise ValueError("M1 evidence has a malformed MIDI-render signature")
        track_index = _nonnegative_integer(
            value.get("track_index"), "M1 render signature track index"
        )
        channel = _json_integer(value.get("channel"), "M1 render signature channel")
        start_tick = _nonnegative_integer(
            value.get("start_tick"), "M1 render signature start tick"
        )
        end_tick = _positive_integer(
            value.get("end_tick"), "M1 render signature end tick"
        )
        pitch = _json_integer(value.get("pitch"), "M1 render signature pitch")
        velocity = _json_integer(value.get("velocity"), "M1 render signature velocity")
        if (
            not 0 <= channel <= 15
            or end_tick <= start_tick
            or not 0 <= pitch <= 127
            or not 1 <= velocity <= 127
        ):
            raise ValueError("M1 evidence has an invalid MIDI-render signature")
        records.append((track_index, channel, start_tick, end_tick, pitch, velocity))
    return sorted(records)


def _existing_file(value: Any, label: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise ValueError(f"{label} path is missing")
    path = Path(value).expanduser().absolute()
    if not path.is_file():
        raise FileNotFoundError(f"{label} does not exist: {path}")
    return path


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), parse_constant=_reject_constant
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid {label} JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} JSON must be an object")
    return value


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _document_hash(document: Mapping[str, Any]) -> str:
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def _round(value: float, digits: int = 9) -> float:
    return round(float(value), digits)


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{label} must be a finite number")
    return converted


def _positive_number(value: Any, label: str) -> float:
    converted = _finite_number(value, label)
    if converted <= 0:
        raise ValueError(f"{label} must be greater than zero")
    return converted


def _json_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _nonnegative_integer(value: Any, label: str) -> int:
    converted = _json_integer(value, label)
    if converted < 0:
        raise ValueError(f"{label} must be non-negative")
    return converted


def _positive_integer(value: Any, label: str) -> int:
    converted = _json_integer(value, label)
    if converted <= 0:
        raise ValueError(f"{label} must be greater than zero")
    return converted


def _unit_ratio(value: Any, label: str) -> float:
    converted = _finite_number(value, label)
    if not 0.0 <= converted <= 1.0:
        raise ValueError(f"{label} must be between zero and one")
    return converted


def _optional_nonnegative_number(value: Any, label: str) -> float | None:
    if value is None:
        return None
    converted = _finite_number(value, label)
    if converted < 0:
        raise ValueError(f"{label} must be non-negative")
    return _round(converted, 6)


def _optional_positive_number(value: Any, label: str) -> float | None:
    if value is None:
        return None
    return _round(_positive_number(value, label), 6)


def _exact_boolean(value: Any, expected: bool, label: str) -> bool:
    if value is not expected:
        raise ValueError(f"{label} must be {str(expected).lower()}")
    return expected


def _sha256_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{label} must be a lowercase hexadecimal SHA-256")
    return value


def _path_free_text(value: Any, label: str) -> str:
    text = _nonempty_text(value, label)
    if text != value or _SAFE_TEXT.fullmatch(text) is None:
        raise ValueError(f"{label} must be short path-free text")
    return text


def _wav_codec(subtype: str, *, container: str, endian: str) -> str:
    if container not in {"WAV", "WAVEX", "RF64"} or endian not in {
        "FILE",
        "LITTLE",
    }:
        raise ValueError("M3 codec verification requires little-endian WAV audio")
    codecs = {
        "PCM_U8": "pcm_u8",
        "PCM_16": "pcm_s16le",
        "PCM_24": "pcm_s24le",
        "PCM_32": "pcm_s32le",
        "FLOAT": "pcm_f32le",
        "DOUBLE": "pcm_f64le",
    }
    try:
        return codecs[subtype]
    except KeyError as exc:
        raise ValueError(
            f"unsupported source WAV subtype for M3 verification: {subtype}"
        ) from exc


def _nonempty_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


__all__ = [
    "BOUNDARY_TOLERANCE_SECONDS",
    "DUPLICATE_TOLERANCE_SECONDS",
    "HYBRID_REPORT_SCHEMA",
    "ONSET_TOLERANCE_SECONDS",
    "REQUIRED_LANES",
    "build_hybrid_report",
    "write_hybrid_report",
]
