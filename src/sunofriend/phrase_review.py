"""Local phrase-by-phrase review of immutable vocal tracker alternatives.

The review package is deliberately downstream of ``vocal-trackers``. It
verifies the source and evidence hashes, renders short neutral-instrument
auditions, and exports the existing melody-correction format. Raw tracker
artifacts are never edited and backing harmony is not reduced to one line.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from .melody_correction import CORRECTION_FORMAT
from .midi import MidiTrack, write_midi_file
from .models import NoteEvent
from .phrase_guide import GUIDE_KINDS
from .phrase_repeat import (
    detect_repeated_review_units,
    repeat_matches_for_unit,
)
from .vocal_boundary import VOCAL_BOUNDARY_REPAIR_SCHEMA


PHRASE_REVIEW_SCHEMA = "sunofriend.melody-phrase-review.v1"
BASE_ALTERNATIVE_NAMES = ("basic-pitch", "game-boundary", "combined")


def build_melody_phrase_review(
    tracker_run: str | Path,
    *,
    out_dir: str | Path,
    source_stem: str | Path | None = None,
    padding_seconds: float = 0.25,
    minimum_bars: int = 2,
    maximum_bars: int = 8,
    beats_per_bar: int = 4,
    ranking_profile: str | Path | None = None,
    guide_path: str | Path | None = None,
    guide_unit: int | None = None,
    guide_kind: str = "hum",
    guide_search_seconds: float = 0.75,
    parent_review: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a fresh local phrase-review package from one lead tracker run."""

    padding = float(padding_seconds)
    if not math.isfinite(padding) or not 0 <= padding <= 2.0:
        raise ValueError("padding_seconds must be finite and between 0 and 2")
    minimum, maximum, beats = _validate_bar_grouping(
        minimum_bars,
        maximum_bars,
        beats_per_bar,
    )
    guide_request = _validate_guide_request(
        guide_path=guide_path,
        guide_unit=guide_unit,
        guide_kind=guide_kind,
        guide_search_seconds=guide_search_seconds,
        parent_review=parent_review,
    )
    ranking_document: Mapping[str, Any] | None = None
    ranking_record: Mapping[str, Any] | None = None
    if ranking_profile is not None:
        from .melody_profile import load_personal_melody_profile

        ranking_document, ranking_record = load_personal_melody_profile(
            ranking_profile
        )
    run_path = _run_manifest_path(tracker_run)
    run_dir = run_path.parent
    run = _read_json(run_path)
    if run.get("status") != "complete":
        raise ValueError("tracker run must be complete")
    if run.get("schema") != "sunofriend.vocal-tracker-run.v1":
        raise ValueError("unsupported vocal tracker run schema")
    if run.get("role") != "lead":
        raise ValueError(
            "melody-review currently supports lead vocals only; retain backing "
            "harmony and polyphonic evidence"
        )
    if not run.get("boundary_repair_created"):
        raise ValueError("tracker run does not contain agreed-F0 boundary repair")

    source_record = run.get("source")
    if not isinstance(source_record, Mapping) or not source_record.get("sha256"):
        raise ValueError("tracker run is missing its source record")
    stem = _resolve_source(source_stem or source_record.get("path"), run_dir)
    _verify_file_record(stem, source_record, label="source WAV")
    source_record = {**source_record, "path": str(stem)}

    boundary_path = run_dir / "boundary-repair.evidence.json"
    basic_path = run_dir / "basic-pitch.evidence.json"
    combined_midi_path = run_dir / "boundary-repair.candidate.mid"
    _verify_run_artifact(run, boundary_path)
    _verify_run_artifact(run, basic_path)
    _verify_run_artifact(run, combined_midi_path)
    boundary = _read_json(boundary_path)
    basic = _read_json(basic_path)
    if boundary.get("schema") != VOCAL_BOUNDARY_REPAIR_SCHEMA:
        raise ValueError("unsupported boundary-repair evidence schema")
    if basic.get("schema") != "sunofriend.vocal-tracker-evidence.v1":
        raise ValueError("unsupported Basic Pitch evidence schema")
    for label, document in (("boundary repair", boundary), ("Basic Pitch", basic)):
        recorded = document.get("source", {})
        if recorded.get("sha256") != source_record["sha256"]:
            raise ValueError(f"{label} source hash does not match the tracker run")

    phrase_records = boundary.get("phrases", {}).get("combined", [])
    if not isinstance(phrase_records, list) or not phrase_records:
        raise ValueError("boundary repair contains no combined lead phrases")
    variants = boundary.get("variants", {})
    sources = {
        "basic-pitch": _notes_from_document(basic.get("notes", [])),
        "game-boundary": _notes_from_document(variants.get("game", [])),
        "combined": _notes_from_document(variants.get("combined", [])),
    }
    if not sources["combined"]:
        raise ValueError("boundary repair contains no combined notes")

    bpm = float(run.get("bpm", 0.0))
    tuning_hz = float(run.get("tuning_hz", 440.0))
    if not math.isfinite(bpm) or bpm <= 0:
        raise ValueError("tracker run BPM must be finite and positive")
    if not math.isfinite(tuning_hz) or tuning_hz <= 0:
        raise ValueError("tracker run tuning must be finite and positive")

    destination = Path(out_dir).expanduser().absolute()
    if destination.exists():
        raise ValueError(f"phrase-review output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.tmp-",
            dir=str(destination.parent),
        )
    )
    try:
        package = _write_review_package(
            temporary,
            stem=stem,
            source_record=dict(source_record),
            run_path=run_path,
            run=run,
            boundary_path=boundary_path,
            boundary=boundary,
            basic_path=basic_path,
            combined_midi_path=combined_midi_path,
            phrase_records=phrase_records,
            note_sources=sources,
            bpm=bpm,
            tuning_hz=tuning_hz,
            padding_seconds=padding,
            minimum_bars=minimum,
            maximum_bars=maximum,
            beats_per_bar=beats,
            ranking_profile_document=ranking_document,
            ranking_profile_record=ranking_record,
            guide_request=guide_request,
        )
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return _relocate_paths(package, destination)


def build_guided_melody_phrase_review(
    review_package: str | Path,
    *,
    unit: int,
    guide_path: str | Path,
    out_dir: str | Path,
    guide_kind: str = "hum",
    search_seconds: float = 0.75,
) -> dict[str, Any]:
    """Create a fresh review package with one source-supported short guide."""

    manifest_path = Path(review_package).expanduser().absolute()
    if manifest_path.is_dir():
        manifest_path = manifest_path / "phrase_review.json"
    if not manifest_path.is_file():
        raise ValueError(f"phrase-review manifest not found: {manifest_path}")
    destination = Path(out_dir).expanduser().absolute()
    if destination == manifest_path.parent or manifest_path.parent in destination.parents:
        raise ValueError(
            "guided review output must be outside the immutable parent review package"
        )
    manifest = _read_json(manifest_path)
    if manifest.get("schema") != PHRASE_REVIEW_SCHEMA:
        raise ValueError("unsupported phrase-review manifest schema")
    if manifest.get("role") != "lead":
        raise ValueError("short guides currently support lead review only")
    if manifest.get("raw_candidates_mutated") is not False:
        raise ValueError("phrase-review manifest does not preserve raw candidates")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping) or not artifacts:
        raise ValueError("phrase-review manifest contains no immutable artifacts")
    verified = 0
    for relative, record in artifacts.items():
        relative_path = Path(str(relative))
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("phrase-review artifact path must stay inside its package")
        if not isinstance(record, Mapping):
            raise ValueError("phrase-review artifact record is invalid")
        _verify_file_record(
            manifest_path.parent / relative_path,
            record,
            label=f"phrase-review artifact {relative}",
        )
        verified += 1
    tracker_record = manifest.get("tracker_run")
    if not isinstance(tracker_record, Mapping):
        raise ValueError("phrase-review manifest is missing its tracker run")
    tracker_path = Path(str(tracker_record.get("path", ""))).expanduser().absolute()
    _verify_file_record(tracker_path, tracker_record, label="tracker run")
    segmentation = manifest.get("segmentation")
    if not isinstance(segmentation, Mapping):
        raise ValueError("phrase-review manifest is missing segmentation policy")
    source = manifest.get("source")
    if not isinstance(source, Mapping) or not source.get("path"):
        raise ValueError("phrase-review manifest is missing its source WAV")
    parent_record = {
        **_file_record(manifest_path),
        "verified_artifact_count": verified,
    }
    ranking_path: str | None = None
    personal_ranking = manifest.get("personal_ranking")
    if personal_ranking is not None:
        if not isinstance(personal_ranking, Mapping):
            raise ValueError("phrase-review personal ranking record is invalid")
        profile_record = personal_ranking.get("profile")
        if not isinstance(profile_record, Mapping) or not profile_record.get("path"):
            raise ValueError("phrase-review personal ranking profile is invalid")
        profile_path = Path(str(profile_record["path"])).expanduser().absolute()
        _verify_file_record(
            profile_path,
            profile_record,
            label="personal ranking profile",
        )
        ranking_path = str(profile_path)
    return build_melody_phrase_review(
        tracker_path,
        out_dir=destination,
        source_stem=str(source["path"]),
        padding_seconds=float(manifest.get("padding_seconds", 0.25)),
        minimum_bars=int(segmentation["minimum_bars"]),
        maximum_bars=int(segmentation["maximum_bars"]),
        beats_per_bar=int(segmentation["beats_per_bar"]),
        ranking_profile=ranking_path,
        guide_path=guide_path,
        guide_unit=unit,
        guide_kind=guide_kind,
        guide_search_seconds=search_seconds,
        parent_review=parent_record,
    )


def _validate_guide_request(
    *,
    guide_path: str | Path | None,
    guide_unit: int | None,
    guide_kind: str,
    guide_search_seconds: float,
    parent_review: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if guide_path is None and guide_unit is None:
        if parent_review is not None:
            raise ValueError("parent_review requires a short guide")
        return None
    if guide_path is None or guide_unit is None:
        raise ValueError("guide_path and guide_unit must be supplied together")
    guide = Path(guide_path).expanduser().absolute()
    if not guide.is_file():
        raise ValueError(f"Short guide WAV not found: {guide}")
    if isinstance(guide_unit, bool) or int(guide_unit) != guide_unit or guide_unit < 1:
        raise ValueError("guide_unit must be a positive one-based integer")
    kind = str(guide_kind)
    if kind not in GUIDE_KINDS:
        raise ValueError(f"guide_kind must be one of: {', '.join(GUIDE_KINDS)}")
    search = float(guide_search_seconds)
    if not math.isfinite(search) or not 0 <= search <= 2.0:
        raise ValueError("guide_search_seconds must be from 0 to 2")
    if parent_review is not None and not isinstance(parent_review, Mapping):
        raise ValueError("parent_review record must be an object")
    return {
        "path": guide,
        "unit": int(guide_unit),
        "kind": kind,
        "search_seconds": search,
        "parent_review": None if parent_review is None else dict(parent_review),
    }


def _validate_bar_grouping(
    minimum_bars: int,
    maximum_bars: int,
    beats_per_bar: int,
) -> tuple[int, int, int]:
    values: dict[str, int] = {}
    for name, value, upper in (
        ("minimum_bars", minimum_bars, 32),
        ("maximum_bars", maximum_bars, 32),
        ("beats_per_bar", beats_per_bar, 16),
    ):
        if isinstance(value, bool):
            raise ValueError(f"{name} must be a positive integer")
        try:
            converted = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be a positive integer") from exc
        if converted != value or not 1 <= converted <= upper:
            raise ValueError(f"{name} must be a positive integer up to {upper}")
        values[name] = converted
    if values["minimum_bars"] > values["maximum_bars"]:
        raise ValueError("minimum_bars cannot exceed maximum_bars")
    return (
        values["minimum_bars"],
        values["maximum_bars"],
        values["beats_per_bar"],
    )


def _merge_phrase_records(
    phrase_records: Sequence[Mapping[str, Any]],
    *,
    duration_seconds: float,
    bpm: float,
    minimum_bars: int = 2,
    maximum_bars: int = 8,
    beats_per_bar: int = 4,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Merge adjacent note clusters into reviewable musical-length units.

    Bar duration supplies a useful human scale without asserting that the
    excerpt begins on a downbeat. Original phrase records remain untouched and
    their indices are retained in every review unit.
    """

    minimum, maximum, beats = _validate_bar_grouping(
        minimum_bars,
        maximum_bars,
        beats_per_bar,
    )
    duration = float(duration_seconds)
    tempo = float(bpm)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("review source duration must be finite and positive")
    if not math.isfinite(tempo) or tempo <= 0:
        raise ValueError("review BPM must be finite and positive")
    if not phrase_records:
        raise ValueError("review requires at least one source phrase")

    normalised: list[dict[str, Any]] = []
    for position, record in enumerate(phrase_records):
        if not isinstance(record, Mapping):
            raise ValueError("source phrase record must be an object")
        try:
            start = float(record["start_seconds"])
            end = float(record["end_seconds"])
            source_index = int(record.get("phrase_index", position))
            agreement = float(record["mean_agreement_ratio"])
            score = float(record["mean_selection_score"])
            note_count = int(record.get("note_count", 1))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("source phrase record has invalid values") from exc
        if not all(math.isfinite(value) for value in (start, end, agreement, score)):
            raise ValueError("source phrase record values must be finite")
        if start < 0 or end <= start or end > duration + 0.05:
            raise ValueError("source phrase record falls outside the source WAV")
        if note_count < 1:
            raise ValueError("source phrase record note_count must be positive")
        normalised.append(
            {
                "source_phrase_index": source_index,
                "start_seconds": start,
                "end_seconds": min(duration, end),
                "note_count": note_count,
                "providers": sorted(str(value) for value in record.get("providers", [])),
                "mean_agreement_ratio": agreement,
                "mean_selection_score": score,
            }
        )
    normalised.sort(
        key=lambda record: (
            record["start_seconds"],
            record["end_seconds"],
            record["source_phrase_index"],
        )
    )
    for previous, current in zip(normalised, normalised[1:]):
        if current["start_seconds"] < previous["start_seconds"]:
            raise ValueError("source phrase records are not chronological")

    bar_seconds = beats * 60.0 / tempo
    minimum_seconds = minimum * bar_seconds
    maximum_seconds = maximum * bar_seconds
    groups: list[list[dict[str, Any]]] = []
    cursor = 0
    while cursor < len(normalised):
        group = [normalised[cursor]]
        cursor += 1
        while cursor < len(normalised):
            proposed = normalised[cursor]
            proposed_span = proposed["end_seconds"] - group[0]["start_seconds"]
            current_span = group[-1]["end_seconds"] - group[0]["start_seconds"]
            if proposed_span > maximum_seconds + 1e-9:
                break
            if current_span >= minimum_seconds - 1e-9:
                remaining_span = (
                    normalised[-1]["end_seconds"]
                    - normalised[cursor]["start_seconds"]
                )
                combined_span = (
                    normalised[-1]["end_seconds"] - group[0]["start_seconds"]
                )
                if not (
                    remaining_span < minimum_seconds - 1e-9
                    and combined_span <= maximum_seconds + 1e-9
                ):
                    break
            group.append(proposed)
            cursor += 1
        groups.append(group)

    units: list[dict[str, Any]] = []
    for unit_index, group in enumerate(groups):
        start = float(group[0]["start_seconds"])
        end = float(group[-1]["end_seconds"])
        span = end - start
        weights = [int(record["note_count"]) for record in group]
        total_weight = sum(weights)
        length_status = "within-range"
        if span < minimum_seconds - 1e-9:
            length_status = "short-source-or-isolated"
        elif span > maximum_seconds + 1e-9:
            length_status = "exceeds-maximum"
        units.append(
            {
                "phrase_index": unit_index,
                "source_phrase_indices": [
                    int(record["source_phrase_index"]) for record in group
                ],
                "source_phrase_count": len(group),
                "start_seconds": start,
                "end_seconds": end,
                "duration_seconds": round(span, 9),
                "duration_bars": round(span / bar_seconds, 6),
                "length_status": length_status,
                "note_count": total_weight,
                "providers": sorted(
                    {
                        provider
                        for record in group
                        for provider in record["providers"]
                    }
                ),
                "mean_selection_score": round(
                    sum(
                        float(record["mean_selection_score"]) * weight
                        for record, weight in zip(group, weights)
                    )
                    / total_weight,
                    9,
                ),
                "mean_agreement_ratio": round(
                    sum(
                        float(record["mean_agreement_ratio"]) * weight
                        for record, weight in zip(group, weights)
                    )
                    / total_weight,
                    9,
                ),
            }
        )
    ranked = sorted(
        range(len(units)),
        key=lambda position: (
            -units[position]["mean_selection_score"],
            units[position]["start_seconds"],
        ),
    )
    ranks = {position: rank + 1 for rank, position in enumerate(ranked)}
    for position, unit in enumerate(units):
        unit["confidence_rank"] = ranks[position]

    short_count = sum(
        unit["length_status"] == "short-source-or-isolated" for unit in units
    )
    long_count = sum(
        unit["length_status"] == "exceeds-maximum" for unit in units
    )
    warnings: list[str] = []
    if short_count:
        warnings.append(
            f"{short_count} review unit(s) are shorter than {minimum} bars because "
            "the source excerpt or an isolated cluster provides less material."
        )
    if long_count:
        warnings.append(
            f"{long_count} review unit(s) exceed {maximum} bars because an original "
            "source phrase is longer than the configured maximum."
        )
    segmentation = {
        "policy": "consecutive-clusters-to-musical-length-v1",
        "source_phrase_count": len(normalised),
        "review_unit_count": len(units),
        "minimum_bars": minimum,
        "maximum_bars": maximum,
        "beats_per_bar": beats,
        "bar_seconds": round(bar_seconds, 9),
        "bar_alignment": "duration-only; no unconfirmed downbeat was assumed",
        "short_unit_count": short_count,
        "long_unit_count": long_count,
        "warnings": warnings,
        "raw_phrase_records_mutated": False,
    }
    return units, segmentation


def _write_review_package(
    destination: Path,
    *,
    stem: Path,
    source_record: dict[str, Any],
    run_path: Path,
    run: Mapping[str, Any],
    boundary_path: Path,
    boundary: Mapping[str, Any],
    basic_path: Path,
    combined_midi_path: Path,
    phrase_records: Sequence[Mapping[str, Any]],
    note_sources: Mapping[str, Sequence[NoteEvent]],
    bpm: float,
    tuning_hz: float,
    padding_seconds: float,
    minimum_bars: int,
    maximum_bars: int,
    beats_per_bar: int,
    ranking_profile_document: Mapping[str, Any] | None,
    ranking_profile_record: Mapping[str, Any] | None,
    guide_request: Mapping[str, Any] | None,
) -> dict[str, Any]:
    import soundfile

    audio, sample_rate = soundfile.read(
        str(stem), dtype="float32", always_2d=True
    )
    source_info = soundfile.info(str(stem))
    duration = len(audio) / sample_rate if sample_rate else 0.0
    if duration <= 0:
        raise ValueError("source WAV contains no audio")

    review_units, segmentation = _merge_phrase_records(
        phrase_records,
        duration_seconds=duration,
        bpm=bpm,
        minimum_bars=minimum_bars,
        maximum_bars=maximum_bars,
        beats_per_bar=beats_per_bar,
    )
    available_note_sources = dict(note_sources)
    repetition = detect_repeated_review_units(
        review_units,
        available_note_sources["combined"],
        bpm=bpm,
    )
    if (ranking_profile_document is None) != (ranking_profile_record is None):
        raise ValueError("personal ranking profile document and record must agree")
    personal_ranking_summary: dict[str, Any] | None = None
    if ranking_profile_document is not None and ranking_profile_record is not None:
        personal_ranking_summary = {
            "status": "advisory",
            "profile": dict(ranking_profile_record),
            "policy": ranking_profile_document["policy"],
            "explicit_choice_count": ranking_profile_document[
                "explicit_choice_count"
            ],
            "contextual_observation_count": ranking_profile_document[
                "contextual_observation_count"
            ],
            "automatic_selection": False,
            "candidate_order_changed": False,
            "default_selection_changed": False,
            "raw_candidates_mutated": False,
        }
    guide_summary: dict[str, Any] | None = None
    guide_evidence_path: Path | None = None
    guided_unit_index: int | None = None
    if guide_request is not None:
        guided_unit_index = int(guide_request["unit"]) - 1
        if not 0 <= guided_unit_index < len(review_units):
            raise ValueError(
                f"guide unit must be from 1 to {len(review_units)} for this review"
            )
        pyin_path = run_path.parent / "pyin.evidence.json"
        _verify_run_artifact(run, pyin_path)
        from .phrase_guide import load_pyin_frames, prepare_short_guide

        source_frames = load_pyin_frames(
            pyin_path,
            source_sha256=str(source_record["sha256"]),
        )
        guided_unit = review_units[guided_unit_index]
        guide_result = prepare_short_guide(
            guide_request["path"],
            kind=guide_request["kind"],
            source_frames=source_frames,
            unit_start_seconds=float(guided_unit["start_seconds"]),
            unit_end_seconds=float(guided_unit["end_seconds"]),
            bpm=bpm,
            tuning_hz=tuning_hz,
            search_seconds=float(guide_request["search_seconds"]),
        )
        available_note_sources["guide-assisted"] = list(guide_result.notes)
        guide_evidence_path = destination / "guide.evidence.json"
        guide_evidence = {
            **dict(guide_result.report),
            "source": source_record,
            "guide": _file_record(guide_request["path"]),
            "tracker_run": _file_record(run_path),
            "pyin_evidence": _file_record(pyin_path),
            "parent_review": guide_request.get("parent_review"),
            "unit": int(guide_request["unit"]),
            "unit_index": guided_unit_index,
            "source_phrase_indices": list(guided_unit["source_phrase_indices"]),
            "notes": [_note_dict(note) for note in guide_result.notes],
            "provenance": [record.to_dict() for record in guide_result.provenance],
        }
        _write_json(guide_evidence_path, guide_evidence)
        guide_summary = {
            "status": guide_evidence["status"],
            "kind": guide_evidence["kind"],
            "unit": int(guide_request["unit"]),
            "unit_index": guided_unit_index,
            "guide": guide_evidence["guide"],
            "evidence": guide_evidence_path.name,
            "guide_note_count": guide_evidence["guide_note_count"],
            "accepted_note_count": guide_evidence["accepted_note_count"],
            "alignment": guide_evidence["alignment"],
            "warnings": guide_evidence["warnings"],
            "parent_review": guide_evidence["parent_review"],
            "source_pitch_support_required": True,
            "raw_candidates_mutated": False,
        }

    (destination / "audio").mkdir()
    (destination / "midi").mkdir()
    (destination / "evaluation").mkdir()
    total_phrases = len(review_units)
    phrase_documents: list[dict[str, Any]] = []
    tuning_cents = 1200.0 * math.log2(tuning_hz / 440.0)
    for phrase in sorted(
        review_units,
        key=lambda value: (int(value["phrase_index"]), float(value["start_seconds"])),
    ):
        phrase_index = int(phrase["phrase_index"])
        start = float(phrase["start_seconds"])
        end = float(phrase["end_seconds"])
        if not 0 <= start < end <= duration + 0.05:
            raise ValueError(f"phrase {phrase_index} falls outside the source WAV")
        window_start = max(0.0, start - padding_seconds)
        window_end = min(duration, end + padding_seconds)
        token = f"unit-{phrase_index + 1:02d}"
        source_rel = Path("audio") / f"{token}-source.wav"
        _write_excerpt(
            destination / source_rel,
            audio,
            sample_rate=sample_rate,
            start_seconds=window_start,
            end_seconds=window_end,
            subtype=source_info.subtype,
        )
        alternatives: dict[str, Any] = {}
        alternative_names = list(BASE_ALTERNATIVE_NAMES)
        if guided_unit_index == phrase_index:
            alternative_names.append("guide-assisted")
        for name in alternative_names:
            absolute_notes = _phrase_notes(
                available_note_sources[name],
                start_seconds=start,
                end_seconds=end,
            )
            local_notes = [
                NoteEvent(
                    note.start - window_start,
                    note.end - window_start,
                    note.pitch,
                    note.velocity,
                )
                for note in absolute_notes
            ]
            midi_rel = Path("midi") / f"{token}-{name}.mid"
            audio_rel = Path("audio") / f"{token}-{name}.wav"
            overlay_rel = Path("audio") / f"{token}-{name}-source-plus-midi.wav"
            evaluation_rel = Path("evaluation") / f"{token}-{name}.json"
            _write_phrase_midi(
                destination / midi_rel,
                local_notes,
                bpm=bpm,
                tuning_cents=tuning_cents,
                name=name,
            )
            if local_notes:
                from .render import render_midi_to_wav

                render_midi_to_wav(
                    destination / midi_rel,
                    destination / audio_rel,
                    sample_rate=sample_rate,
                )
            else:
                _write_silence(
                    destination / audio_rel,
                    duration_seconds=window_end - window_start,
                    sample_rate=sample_rate,
                )
            _mix_source_and_candidate(
                destination / source_rel,
                destination / audio_rel,
                destination / overlay_rel,
            )
            evaluation = _evaluate_alternative(
                destination / source_rel,
                destination / midi_rel,
            )
            _write_json(destination / evaluation_rel, evaluation)
            alternatives[name] = {
                "label": _alternative_label(name),
                "notes": [_note_dict(note) for note in absolute_notes],
                "note_count": len(absolute_notes),
                "midi": midi_rel.as_posix(),
                "audio": audio_rel.as_posix(),
                "overlay_audio": overlay_rel.as_posix(),
                "evaluation": evaluation_rel.as_posix(),
                "metrics": _headline(evaluation),
            }
            if name == "guide-assisted" and guide_evidence_path is not None:
                alternatives[name]["evidence"] = guide_evidence_path.name
        ranking_context = _ranking_context(phrase, alternatives, alternative_names)
        personal_ranking = None
        if ranking_profile_document is not None:
            from .melody_profile import rank_melody_alternatives

            personal_ranking = rank_melody_alternatives(
                ranking_profile_document,
                ranking_context,
                alternative_names,
            )
        confidence_rank = int(phrase["confidence_rank"])
        phrase_documents.append(
            {
                "phrase_index": phrase_index,
                "confidence_rank": confidence_rank,
                "review_priority": total_phrases - confidence_rank + 1,
                "start_seconds": start,
                "end_seconds": end,
                "window_start_seconds": window_start,
                "window_end_seconds": window_end,
                "mean_agreement_ratio": float(phrase["mean_agreement_ratio"]),
                "mean_selection_score": float(phrase["mean_selection_score"]),
                "duration_seconds": float(phrase["duration_seconds"]),
                "duration_bars": float(phrase["duration_bars"]),
                "length_status": str(phrase["length_status"]),
                "source_phrase_indices": list(phrase["source_phrase_indices"]),
                "source_phrase_count": int(phrase["source_phrase_count"]),
                "providers": list(phrase.get("providers", [])),
                "source_audio": source_rel.as_posix(),
                "default_alternative": "combined",
                "alternative_names": alternative_names,
                "alternatives": alternatives,
                "ranking_context": ranking_context,
                "personal_ranking": personal_ranking,
                "repeat_matches": repeat_matches_for_unit(
                    repetition,
                    phrase_index,
                ),
            }
        )

    correction = {
        "format": CORRECTION_FORMAT,
        "format_version": 1,
        "source_stem": str(stem),
        "source_stem_sha256": source_record["sha256"],
        "source_midi": str(combined_midi_path),
        "source_variant": "agreed-f0-boundary-repair-combined",
        "bpm": bpm,
        "key": None,
        "role": "lead",
        "tuning_hz": tuning_hz,
        "garageband_fine_tune_cents": tuning_cents,
        "channel": 2,
        "program": 73,
        "guide_alignment": None,
        "review": {
            "format": PHRASE_REVIEW_SCHEMA,
            "status": "unreviewed",
            "source_review_manifest": "phrase_review.json",
            "tracker_run_id": run.get("run_id"),
            "tracker_run_sha256": _sha256(run_path),
            "raw_candidates_mutated": False,
            "segmentation": segmentation,
            "guide": guide_summary,
            "personal_ranking": personal_ranking_summary,
            "repetition": {
                "schema": repetition["schema"],
                "policy": repetition["policy"],
                "accepted_pairs": repetition["accepted_pairs"],
                "groups": repetition["groups"],
                "raw_candidates_mutated": False,
            },
            "propagation_events": [],
            "choices": [
                {
                    "phrase_index": phrase["phrase_index"],
                    "source_phrase_indices": phrase["source_phrase_indices"],
                    "selected": "combined",
                    "reviewed": False,
                    "ranking_context": phrase["ranking_context"],
                }
                for phrase in phrase_documents
            ],
        },
        "notes": [_note_dict(note) for note in available_note_sources["combined"]],
    }
    correction_path = destination / "melody_corrections_unreviewed.json"
    _write_json(correction_path, correction)

    browser_phrases = sorted(
        phrase_documents,
        key=lambda phrase: (phrase["review_priority"], phrase["start_seconds"]),
    )
    html_path = destination / "melody_phrase_review.html"
    html_path.write_text(
        _phrase_review_html(correction, browser_phrases),
        encoding="utf-8",
    )

    inputs = {
        "boundary_repair": _file_record(boundary_path),
        "basic_pitch": _file_record(basic_path),
        "combined_midi": _file_record(combined_midi_path),
        "boundary_policy": boundary.get("policy"),
    }
    if guide_request is not None:
        pyin_path = run_path.parent / "pyin.evidence.json"
        inputs.update(
            {
                "pyin": _file_record(pyin_path),
                "short_guide": _file_record(guide_request["path"]),
                "parent_review": guide_request.get("parent_review"),
            }
        )
    if ranking_profile_record is not None:
        inputs["personal_ranking_profile"] = dict(ranking_profile_record)
    manifest = {
        "schema": PHRASE_REVIEW_SCHEMA,
        "status": "review-required",
        "selection_policy": (
            "human phrase choice; raw Basic Pitch and agreed-F0 boundary "
            "candidates remain unchanged"
        ),
        "source": source_record,
        "tracker_run": _file_record(run_path),
        "inputs": inputs,
        "bpm": bpm,
        "tuning_hz": tuning_hz,
        "role": "lead",
        "padding_seconds": padding_seconds,
        "segmentation": segmentation,
        "guide": guide_summary,
        "personal_ranking": personal_ranking_summary,
        "repetition": repetition,
        "source_phrase_count": segmentation["source_phrase_count"],
        "review_unit_count": len(phrase_documents),
        "phrase_count": len(phrase_documents),
        "alternative_names": [
            *BASE_ALTERNATIVE_NAMES,
            *(["guide-assisted"] if guide_summary is not None else []),
        ],
        "phrases": phrase_documents,
        "correction_seed": correction_path.name,
        "html": html_path.name,
        "raw_candidates_mutated": False,
    }
    manifest["artifacts"] = {
        path.relative_to(destination).as_posix(): _file_record(
            path, relative_to=destination
        )
        for path in sorted(destination.rglob("*"))
        if path.is_file()
    }
    manifest_path = destination / "phrase_review.json"
    _write_json(manifest_path, manifest)
    return {
        "status": "review-required",
        "manifest": str(manifest_path),
        "html": str(html_path),
        "correction_seed": str(correction_path),
        "source_phrase_count": segmentation["source_phrase_count"],
        "review_unit_count": len(phrase_documents),
        "phrase_count": len(phrase_documents),
        "segmentation": segmentation,
        "guide": guide_summary,
        "personal_ranking": personal_ranking_summary,
        "repetition": repetition,
        "alternative_names": manifest["alternative_names"],
        "raw_candidates_mutated": False,
    }


def _run_manifest_path(value: str | Path) -> Path:
    path = Path(value).expanduser().absolute()
    if path.is_dir():
        path = path / "run.json"
    if not path.is_file():
        raise ValueError(f"tracker run manifest not found: {path}")
    return path


def _resolve_source(value: Any, run_dir: Path) -> Path:
    if not isinstance(value, (str, Path)) or not str(value):
        raise ValueError("source WAV path is missing; supply --source-stem")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = run_dir / path
    path = path.absolute()
    if not path.is_file():
        raise ValueError(f"source WAV not found: {path}")
    return path


def _verify_run_artifact(run: Mapping[str, Any], path: Path) -> None:
    artifacts = run.get("artifacts", {})
    record = artifacts.get(path.name) if isinstance(artifacts, Mapping) else None
    if not isinstance(record, Mapping):
        raise ValueError(f"tracker manifest does not record {path.name}")
    _verify_file_record(path, record, label=path.name)


def _verify_file_record(
    path: Path,
    record: Mapping[str, Any],
    *,
    label: str,
) -> None:
    if not path.is_file():
        raise ValueError(f"{label} does not exist: {path}")
    if record.get("sha256") != _sha256(path):
        raise ValueError(f"{label} hash does not match its immutable record")
    if record.get("bytes") is not None and int(record["bytes"]) != path.stat().st_size:
        raise ValueError(f"{label} size does not match its immutable record")


def _notes_from_document(values: Any) -> list[NoteEvent]:
    if not isinstance(values, list):
        raise ValueError("candidate notes must be a list")
    notes: list[NoteEvent] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise ValueError("candidate note must be an object")
        try:
            start = float(value["start_seconds"])
            end = float(value["end_seconds"])
            pitch = int(value["pitch"])
            velocity = int(value.get("velocity", 90))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("candidate note has invalid values") from exc
        if not all(math.isfinite(number) for number in (start, end)):
            raise ValueError("candidate note times must be finite")
        if start < 0 or end <= start or not 0 <= pitch <= 127:
            raise ValueError("candidate note has invalid time or pitch")
        notes.append(NoteEvent(start, end, pitch, max(1, min(127, velocity))))
    return sorted(notes, key=lambda note: (note.start, note.pitch, note.end))


def _phrase_notes(
    notes: Sequence[NoteEvent],
    *,
    start_seconds: float,
    end_seconds: float,
) -> list[NoteEvent]:
    selected: list[NoteEvent] = []
    for note in notes:
        if note.end <= start_seconds or note.start >= end_seconds:
            continue
        start = max(start_seconds, note.start)
        end = min(end_seconds, note.end)
        if end - start >= 0.03:
            selected.append(NoteEvent(start, end, note.pitch, note.velocity))
    return selected


def _write_excerpt(
    path: Path,
    audio: Any,
    *,
    sample_rate: int,
    start_seconds: float,
    end_seconds: float,
    subtype: str,
) -> None:
    import soundfile

    start = max(0, int(round(start_seconds * sample_rate)))
    end = min(len(audio), int(round(end_seconds * sample_rate)))
    soundfile.write(path, audio[start:end], sample_rate, subtype=subtype)


def _write_phrase_midi(
    path: Path,
    notes: Sequence[NoteEvent],
    *,
    bpm: float,
    tuning_cents: float,
    name: str,
) -> None:
    # A silent candidate still needs a valid MIDI file for an honest audition.
    write_midi_file(
        path,
        [
            MidiTrack(
                f"Lead phrase: {_alternative_label(name)}",
                2,
                73,
                list(notes),
                pitch_bend_cents=tuning_cents,
            )
        ],
        bpm=bpm,
    )


def _write_silence(
    path: Path,
    *,
    duration_seconds: float,
    sample_rate: int,
) -> None:
    import numpy as np
    import soundfile

    frames = max(1, int(round(duration_seconds * sample_rate)))
    soundfile.write(path, np.zeros(frames, dtype=np.float32), sample_rate)


def _mix_source_and_candidate(source: Path, candidate: Path, output: Path) -> None:
    import numpy as np
    import soundfile

    source_audio, source_rate = soundfile.read(
        source, dtype="float32", always_2d=True
    )
    candidate_audio, candidate_rate = soundfile.read(
        candidate, dtype="float32", always_2d=True
    )
    if candidate_rate != source_rate:
        raise ValueError("rendered phrase sample rate does not match source excerpt")
    channels = source_audio.shape[1]
    if candidate_audio.shape[1] != channels:
        mono = np.mean(candidate_audio, axis=1, keepdims=True)
        candidate_audio = np.repeat(mono, channels, axis=1)
    aligned = np.zeros_like(source_audio)
    count = min(len(source_audio), len(candidate_audio))
    aligned[:count] = candidate_audio[:count]
    mixed = 0.68 * source_audio + 0.32 * aligned
    peak = float(np.max(np.abs(mixed))) if len(mixed) else 0.0
    if peak > 0.98:
        mixed *= 0.98 / peak
    soundfile.write(output, mixed, source_rate)


def _evaluate_alternative(source: Path, midi: Path) -> dict[str, Any]:
    from .evaluate import evaluate_stem_midi

    document = evaluate_stem_midi(source, midi, kind="lead").to_dict()
    # Evaluations are created in a temporary directory and then atomically
    # published. Never leak that random private path into immutable evidence.
    for key in ("stem_path", "midi_path", "candidate_path", "source_path"):
        if document.get(key):
            document[key] = Path(str(document[key])).name
    return document


def _headline(report: Mapping[str, Any]) -> dict[str, Any]:
    onsets = report.get("onsets", {})
    strong = onsets.get("strong", {})
    possible = onsets.get("possible", {})
    timing = onsets.get("timing", {})
    pitched = report.get("pitched") or {}
    return {
        "strong_onset_f1": strong.get("f1"),
        "possible_onset_f1": possible.get("f1"),
        "timing_p95_ms": timing.get("absolute_error_p95_ms"),
        "chroma_similarity": pitched.get("chroma_similarity"),
        "supported_note_ratio": pitched.get("supported_note_ratio"),
    }


def _ranking_context(
    phrase: Mapping[str, Any],
    alternatives: Mapping[str, Mapping[str, Any]],
    alternative_names: Sequence[str],
) -> dict[str, Any]:
    duration_bars = float(phrase["duration_bars"])
    if not math.isfinite(duration_bars) or duration_bars <= 0:
        raise ValueError("review unit duration is invalid for personal ranking")
    combined_count = int(alternatives["combined"]["note_count"])
    return {
        "duration_bars": round(duration_bars, 6),
        "mean_agreement_ratio": round(float(phrase["mean_agreement_ratio"]), 6),
        "mean_selection_score": round(float(phrase["mean_selection_score"]), 6),
        "combined_note_density_per_bar": round(
            combined_count / duration_bars,
            6,
        ),
        "alternative_names": list(alternative_names),
        "alternative_note_counts": {
            name: int(alternatives[name]["note_count"]) for name in alternative_names
        },
        "alternative_metrics": {
            name: dict(alternatives[name]["metrics"]) for name in alternative_names
        },
    }


def _alternative_label(name: str) -> str:
    return {
        "basic-pitch": "Raw Basic Pitch",
        "game-boundary": "GAME boundaries on agreed pitch",
        "combined": "Combined agreed-F0 repair",
        "guide-assisted": "Short guide + source contour",
    }[name]


def _phrase_review_html(
    correction: Mapping[str, Any],
    phrases: Sequence[Mapping[str, Any]],
) -> str:
    payload = json.dumps(
        {"correction": correction, "phrases": phrases},
        separators=(",", ":"),
    ).replace("</", "<\\/")
    cards = []
    for phrase in phrases:
        phrase_index = int(phrase["phrase_index"])
        source_audio = html.escape(str(phrase["source_audio"]), quote=True)
        length_note = ""
        if phrase["length_status"] != "within-range":
            length_note = (
                '<span class="warning">This unit is shorter than the configured '
                "minimum because the excerpt or an isolated cluster contains less "
                "material.</span>"
            )
        repeat_panel = ""
        if phrase["repeat_matches"]:
            repeat_actions = []
            for match in phrase["repeat_matches"]:
                pair = match["pair"]
                target = int(match["target_phrase_index"])
                repeat_actions.append(
                    f"""<button class="repeat-action" data-source="{phrase_index}" data-target="{target}">Apply this unit’s current choice to repeat unit {target + 1}</button>
<span>score {pair['similarity_score']:.3f} · pitch {pair['pitch_match_ratio']:.3f} · intervals {pair['interval_match_ratio']:.3f} · timing p90 {pair['timing_p90_beats']:.3f} beats</span>"""
                )
            repeat_panel = (
                '<div class="repeat-panel"><strong>Conservative repeat '
                "suggestion</strong><br>"
                + "<br>".join(repeat_actions)
                + "<p>The button copies only the alternative name; the target "
                "keeps its own source-backed notes and timing. Nothing is applied "
                "without this explicit click.</p></div>"
            )
        ranking_panel = ""
        if phrase["personal_ranking"] is not None:
            ranking_rows = " · ".join(
                f"{row['rank']}. {html.escape(_alternative_label(row['name']))} "
                f"{row['score']:.3f} ({row['global_choices']} prior choice(s))"
                for row in phrase["personal_ranking"]["ranking"]
            )
            ranking_panel = (
                '<div class="ranking-panel"><strong>Your local review history'
                "</strong><p>"
                + ranking_rows
                + "</p><p>Scores are relative preference hints, not confidence. "
                "Candidate order and the combined default remain unchanged; "
                "listen before choosing.</p></div>"
            )
        alternatives = []
        for name in phrase["alternative_names"]:
            candidate = phrase["alternatives"][name]
            audio_path = html.escape(str(candidate["audio"]), quote=True)
            overlay_path = html.escape(
                str(candidate["overlay_audio"]), quote=True
            )
            metrics = candidate["metrics"]
            alternatives.append(
                f"""<label class="candidate">
<span><input type="radio" name="phrase-{phrase_index}" value="{name}"
 {'checked' if name == 'combined' else ''}> <strong>{html.escape(candidate['label'])}</strong></span>
<span>{candidate['note_count']} notes · strong F1 {_metric(metrics.get('strong_onset_f1'))} · possible F1 {_metric(metrics.get('possible_onset_f1'))} · chroma {_metric(metrics.get('chroma_similarity'))}</span>
<span>MIDI only</span><audio controls preload="none" src="{audio_path}"></audio>
<span>Source + MIDI</span><audio controls preload="none" src="{overlay_path}"></audio>
<canvas class="mini" data-phrase="{phrase_index}" data-alternative="{name}" width="420" height="90"></canvas>
</label>"""
            )
        alternatives.append(
            f"""<label class="candidate unresolved">
<span><input type="radio" name="phrase-{phrase_index}" value="unresolved"> <strong>None are close — add a short guide</strong></span>
<span>This does not create MIDI. Exporting records the unit as unresolved; then run <code>sunofriend melody-guide REVIEW_PACKAGE --unit {phrase_index + 1} --guide GUIDE.wav --out-dir NEW_REVIEW</code>.</span>
</label>"""
        )
        cards.append(
            f"""<section class="phrase" id="phrase-{phrase_index}">
<h2>Review unit {phrase_index + 1} · priority {phrase['review_priority']} · {phrase['start_seconds']:.2f}–{phrase['end_seconds']:.2f}s</h2>
<p>{phrase['duration_bars']:.2f} bars by duration · {phrase['source_phrase_count']} original note cluster(s) · confidence rank {phrase['confidence_rank']} of {len(phrases)} · agreement {phrase['mean_agreement_ratio']:.3f}.</p>
{length_note}<p>Listen to the source, then choose the closest playable melody.</p>
<audio class="source" controls preload="none" src="{source_audio}"></audio>
{ranking_panel}
{repeat_panel}
<div class="candidates">{''.join(alternatives)}</div>
</section>"""
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sunofriend Phrase Review</title>
<style>
body{{font:15px system-ui,sans-serif;margin:0;background:#10151b;color:#eef3f7}}
main{{max-width:1260px;margin:auto;padding:20px}} h1{{margin-bottom:6px}}
.toolbar,.phrase,.roll-panel{{background:#19222c;border:1px solid #334252;border-radius:10px;padding:14px;margin:14px 0}}
.toolbar{{position:sticky;top:0;z-index:4}} button{{padding:8px 12px;background:#275174;color:white;border:1px solid #6c91ad;border-radius:6px;margin-right:6px}}
.progress{{color:#ffd34e}} .candidates{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px}}
.candidate{{display:flex;flex-direction:column;gap:7px;background:#111922;border:1px solid #405267;border-radius:8px;padding:10px}}
.candidate.unresolved{{border-style:dashed}}
.candidate:has(input:checked){{border-color:#ffd34e;box-shadow:0 0 0 1px #ffd34e}}
.repeat-panel{{background:#11291f;border:1px solid #3e8b68;border-radius:8px;padding:10px;margin:12px 0}}
.repeat-panel button{{margin:8px 8px 4px 0}}
.ranking-panel{{background:#1b2037;border:1px solid #6d78b5;border-radius:8px;padding:10px;margin:12px 0}}
audio{{width:100%}} canvas{{width:100%;background:#0b1015;border-radius:6px}}
#roll{{height:360px}} code{{color:#9ed9ff}} .warning{{display:block;color:#ffd34e;margin:8px 0}} @media(max-width:850px){{.candidates{{grid-template-columns:1fr}}}}
</style></head><body><main>
<h1>Sunofriend phrase review</h1>
<p>Original note clusters are merged into musical-length review units and the weakest units are shown first. Bar length is calculated from tempo only; no unconfirmed downbeat is assumed. Choose by recognition, not by the score alone. Every raw tracker artifact remains unchanged.</p>
<div class="toolbar"><span class="progress" id="progress"></span><br><br>
<button id="accept">Mark all current choices reviewed</button>
<button id="export">Export review JSON</button>
<span>Resolved exports can use <code>sunofriend melody-apply</code>; unresolved units can use <code>sunofriend melody-guide</code>.</span></div>
{''.join(cards)}
<div class="roll-panel"><h2>Selected full melody</h2><canvas id="roll" width="1200" height="360"></canvas></div>
<script>const DATA={payload};
let doc=structuredClone(DATA.correction), choices=new Map(doc.review.choices.map(x=>[x.phrase_index,x]));
function phrase(i){{return DATA.phrases.find(x=>x.phrase_index===i)}}
function clearPropagation(c){{delete c.propagated_from_phrase_index;delete c.propagation_policy;delete c.repeat_match}}
function clearDependents(i){{for(const c of choices.values())if(c.propagated_from_phrase_index===i){{clearPropagation(c);c.reviewed=false}}}}
function rebuild(){{let notes=[];for(const [i,c] of choices){{let p=phrase(i);if(c.selected!=='unresolved')notes.push(...p.alternatives[c.selected].notes)}}doc.notes=notes.sort((a,b)=>a.start-b.start||a.pitch-b.pitch||a.end-b.end);doc.review.choices=[...choices.values()].sort((a,b)=>a.phrase_index-b.phrase_index);drawRoll();progress()}}
document.querySelectorAll('input[type=radio]').forEach(x=>x.onchange=()=>{{let i=Number(x.name.split('-')[1]),c=choices.get(i);clearDependents(i);clearPropagation(c);c.selected=x.value;c.reviewed=true;rebuild()}});
document.querySelectorAll('.repeat-action').forEach(x=>x.onclick=()=>{{let source=Number(x.dataset.source),target=Number(x.dataset.target),s=choices.get(source),t=choices.get(target),m=phrase(source).repeat_matches.find(v=>v.target_phrase_index===target);if(s.selected==='unresolved'){{alert('Choose a playable source alternative before propagating.');return}}if(!phrase(target).alternatives[s.selected]){{alert('That alternative exists only for the source unit and cannot be propagated.');return}}clearDependents(target);clearPropagation(t);s.reviewed=true;t.selected=s.selected;t.reviewed=true;t.propagated_from_phrase_index=source;t.propagation_policy=doc.review.repetition.policy.name;t.repeat_match=structuredClone(m.pair);doc.review.propagation_events.push({{source_phrase_index:source,target_phrase_index:target,selected:s.selected,repeat_match:structuredClone(m.pair),applied_at:new Date().toISOString()}});let radio=document.querySelector(`input[name="phrase-${{target}}"][value="${{s.selected}}"]`);if(radio)radio.checked=true;rebuild()}});
function progress(){{let n=[...choices.values()].filter(x=>x.reviewed).length;document.getElementById('progress').textContent=`Reviewed ${{n}} of ${{choices.size}} units`;}}
document.getElementById('accept').onclick=()=>{{for(const c of choices.values())c.reviewed=true;rebuild()}};
document.getElementById('export').onclick=()=>{{if([...choices.values()].some(x=>!x.reviewed)){{alert('Review every unit or use “Mark all current choices reviewed” first.');return}}let unresolved=[...choices.values()].filter(x=>x.selected==='unresolved').map(x=>x.phrase_index);doc.review.status=unresolved.length?'unresolved':'reviewed';doc.review.unresolved_unit_indices=unresolved;doc.review.reviewed_at=new Date().toISOString();rebuild();let b=new Blob([JSON.stringify(doc,null,2)],{{type:'application/json'}}),u=URL.createObjectURL(b),a=document.createElement('a');a.href=u;a.download=unresolved.length?'melody-corrections-unresolved.json':'melody-corrections-reviewed.json';a.click();URL.revokeObjectURL(u)}};
function mini(canvas){{let p=phrase(Number(canvas.dataset.phrase)),ns=p.alternatives[canvas.dataset.alternative].notes,ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);if(!ns.length)return;let lo=Math.min(...ns.map(n=>n.pitch))-1,hi=Math.max(...ns.map(n=>n.pitch))+1,d=Math.max(.1,p.end_seconds-p.start_seconds);ctx.fillStyle='#38c172';for(const n of ns){{let x=(n.start-p.start_seconds)/d*canvas.width,w=(n.end-n.start)/d*canvas.width,y=(hi-n.pitch)/(hi-lo)*canvas.height;ctx.fillRect(x,y-3,Math.max(2,w),6)}}}}
document.querySelectorAll('.mini').forEach(mini);
function drawRoll(){{let c=document.getElementById('roll'),ctx=c.getContext('2d');ctx.clearRect(0,0,c.width,c.height);if(!doc.notes.length)return;let d=Math.max(...doc.notes.map(n=>n.end)),lo=Math.min(...doc.notes.map(n=>n.pitch))-2,hi=Math.max(...doc.notes.map(n=>n.pitch))+2;ctx.strokeStyle='#22303d';for(let t=0;t<d;t+=60/doc.bpm){{let x=t/d*c.width;ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,c.height);ctx.stroke()}}ctx.fillStyle='#ffd34e';for(const n of doc.notes){{let x=n.start/d*c.width,w=(n.end-n.start)/d*c.width,y=(hi-n.pitch)/(hi-lo)*c.height;ctx.fillRect(x,y-4,Math.max(2,w),8)}}}}
rebuild();</script></main></body></html>"""


def _metric(value: Any) -> str:
    return "—" if value is None else f"{float(value):.3f}"


def _note_dict(note: NoteEvent) -> dict[str, Any]:
    return {
        "start": round(note.start, 6),
        "end": round(note.end, 6),
        "pitch": note.pitch,
        "velocity": note.velocity,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _file_record(
    path: Path,
    *,
    relative_to: Path | None = None,
) -> dict[str, Any]:
    label = path.relative_to(relative_to) if relative_to else path
    return {
        "path": str(label),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON document: {path}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return document


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _relocate_paths(result: Mapping[str, Any], destination: Path) -> dict[str, Any]:
    relocated = dict(result)
    for key, name in (
        ("manifest", "phrase_review.json"),
        ("html", "melody_phrase_review.html"),
        ("correction_seed", "melody_corrections_unreviewed.json"),
    ):
        relocated[key] = str(destination / name)
    return relocated


__all__ = [
    "BASE_ALTERNATIVE_NAMES",
    "PHRASE_REVIEW_SCHEMA",
    "build_guided_melody_phrase_review",
    "build_melody_phrase_review",
]
