"""Private, evidence-first phrase-level vocal comping pilot.

The first increment admits immutable vocal takes and publishes transparent
target-relative phrase rankings.  It deliberately cannot render, correct or
select a comp.  The optional AI reference is exposed only as a fallback when
no human take clears the fixed pilot policy.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import os
import re
import shutil
import tempfile
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

from .models import NoteEvent
from .source_project import RIGHTS_CATEGORIES
from .vocal import (
    PitchFrame,
    VocalConfig,
    consensus_pitch_frames_with_audit,
    extract_backing_candidates,
    extract_pitch_frames,
    hz_to_fractional_midi,
    project_basic_pitch_candidates,
)
from .vocal_trackers import load_rmvpe_evidence


VOCAL_COMP_PROJECT_SCHEMA = "sunofriend.vocal-comp-project.v1"
VOCAL_COMP_TIMELINE_SCHEMA = "sunofriend.vocal-comp-timeline.v1"
VOCAL_TAKE_ANALYSIS_SCHEMA = "sunofriend.vocal-take-analysis.v1"
VOCAL_COMP_CANDIDATES_SCHEMA = "sunofriend.vocal-comp-candidates.v1"
VOCAL_COMP_PICKUPS_SCHEMA = "sunofriend.vocal-comp-pickups.v1"

_TAKE_ID = re.compile(r"^take-[0-9]{3}$")
_PHRASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_AUDIO_SUFFIXES = frozenset({".wav"})
_MAX_TAKES = 24
_MAX_PHRASES = 128
_MAX_LYRICS_BYTES = 256 * 1024
_MAX_TIMELINE_BYTES = 512 * 1024
_MIN_PHRASE_SECONDS = 0.10
_MAX_PHRASE_SECONDS = 30.0

RANKING_POLICY = {
    "name": "transparent-target-relative-phrase-ranking-pilot-v1",
    "weights": {
        "melody": 0.50,
        "completeness": 0.25,
        "timing": 0.20,
        "signal": 0.05,
    },
    "melody_components": {
        "exact_register_50_cents": 0.60,
        "octave_aware_50_cents": 0.40,
    },
    "uncertainty_penalty_maximum": 0.25,
    "not_attempted_activity_ratio_below": 0.15,
    "minimum_agreement_coverage": 0.30,
    "minimum_acceptable_score": 0.45,
    "minimum_acceptable_voiced_coverage": 0.35,
    "timing_full_penalty_seconds": 0.75,
    "expression_weight": 0.0,
    "status": "experimental_not_calibrated",
}


def plan_vocal_comp_project(
    take_dir: str | Path,
    *,
    lyrics: str | Path,
    target_midi: str | Path,
    phrase_timeline: str | Path,
    bpm: float,
    tuning_hz: float,
    rights_category: str,
    processing_chain: str,
    target_vocal: str | Path | None = None,
    confirm_common_recorded_zero: bool = False,
    confirm_target_reviewed: bool = False,
) -> dict[str, Any]:
    """Validate one future project without writing or normalising anything."""

    source_dir = _directory(take_dir, "take directory")
    take_paths = sorted(
        (
            path
            for path in source_dir.iterdir()
            if path.is_file() and path.suffix.casefold() in _AUDIO_SUFFIXES
        ),
        key=lambda path: path.name.casefold(),
    )
    if not 2 <= len(take_paths) <= _MAX_TAKES:
        raise ValueError("vocal comping requires 2-24 top-level WAV takes")
    if any(path.is_symlink() for path in take_paths):
        raise ValueError("vocal takes may not be symbolic links")
    inodes = {(path.stat().st_dev, path.stat().st_ino) for path in take_paths}
    if len(inodes) != len(take_paths):
        raise ValueError("duplicate or hard-linked vocal takes are not allowed")

    lyrics_path = _file(lyrics, "lyrics")
    target_path = _file(target_midi, "target MIDI")
    timeline_path = _file(phrase_timeline, "phrase timeline")
    target_vocal_path = _file(target_vocal, "target vocal") if target_vocal else None
    if not confirm_common_recorded_zero:
        raise ValueError("confirm_common_recorded_zero is required")
    if not confirm_target_reviewed:
        raise ValueError("confirm_target_reviewed is required")
    if rights_category not in RIGHTS_CATEGORIES:
        raise ValueError(
            "rights_category must be one of: "
            + ", ".join(sorted(RIGHTS_CATEGORIES))
        )
    normalized_chain = str(processing_chain).strip().casefold().replace("-", "_")
    if normalized_chain not in {"dry", "same_gentle_chain"}:
        raise ValueError("processing_chain must be dry or same-gentle-chain")
    if not math.isfinite(float(bpm)) or float(bpm) <= 0:
        raise ValueError("bpm must be finite and positive")
    if not math.isfinite(float(tuning_hz)) or float(tuning_hz) <= 0:
        raise ValueError("tuning_hz must be finite and positive")

    lyrics_bytes = lyrics_path.read_bytes()
    if not lyrics_bytes or len(lyrics_bytes) > _MAX_LYRICS_BYTES:
        raise ValueError("lyrics must be non-empty and no larger than 256 KiB")
    try:
        canonical_lyrics = lyrics_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("lyrics must be UTF-8 text") from exc
    if not canonical_lyrics.strip():
        raise ValueError("lyrics must contain non-whitespace text")

    timeline = _load_timeline(timeline_path, canonical_lyrics)
    target_notes = _read_midi_notes(target_path)
    _validate_target_notes(target_notes)
    take_records = [
        {
            "take_id": f"take-{index:03d}",
            "source_name": path.name,
            "source": _file_record(path),
            "audio": _audio_record(path),
            "recorded_zero_offset_seconds": 0.0,
        }
        for index, path in enumerate(take_paths, 1)
    ]
    maximum_duration = max(row["audio"]["duration_seconds"] for row in take_records)
    final_phrase_end = float(timeline["phrases"][-1]["end_seconds"])
    if final_phrase_end > maximum_duration + 1e-6:
        raise ValueError("phrase timeline extends beyond every supplied vocal take")
    phrases_without_targets = [
        phrase["phrase_id"]
        for phrase in timeline["phrases"]
        if not any(
            note.end > float(phrase["start_seconds"])
            and note.start < float(phrase["end_seconds"])
            for note in target_notes
        )
    ]
    if phrases_without_targets:
        raise ValueError(
            "reviewed target MIDI has no note in phrase(s): "
            + ", ".join(phrases_without_targets)
        )
    if target_vocal_path is not None:
        target_audio = _audio_record(target_vocal_path)
        if target_audio["duration_seconds"] + 1e-6 < final_phrase_end:
            raise ValueError("target vocal ends before the reviewed phrase timeline")
    else:
        target_audio = None

    return {
        "schema": VOCAL_COMP_PROJECT_SCHEMA,
        "operation": "plan",
        "status": "ready",
        "source_directory": str(source_dir),
        "take_count": len(take_records),
        "takes": take_records,
        "lyrics": _file_record(lyrics_path),
        "target_midi": {
            **_file_record(target_path),
            "note_count": len(target_notes),
            "review_status": "reviewed",
        },
        "phrase_timeline": {
            **_file_record(timeline_path),
            "phrase_count": len(timeline["phrases"]),
            "review_status": "reviewed",
        },
        "target_vocal": (
            {**_file_record(target_vocal_path), "audio": target_audio}
            if target_vocal_path is not None
            else None
        ),
        "bpm": float(bpm),
        "tuning_hz": float(tuning_hz),
        "rights_category": rights_category,
        "processing_chain": normalized_chain,
        "recorded_zero": "common_confirmed",
        "ai_voice_policy": "fallback_only",
        "network_used": False,
        "effects": _zero_effects(),
    }


def create_vocal_comp_project(
    take_dir: str | Path,
    *,
    out_dir: str | Path,
    lyrics: str | Path,
    target_midi: str | Path,
    phrase_timeline: str | Path,
    bpm: float,
    tuning_hz: float,
    rights_category: str,
    processing_chain: str,
    target_vocal: str | Path | None = None,
    confirm_common_recorded_zero: bool = False,
    confirm_target_reviewed: bool = False,
) -> dict[str, Any]:
    """Copy exact admitted evidence into one fresh owner-only project."""

    plan = plan_vocal_comp_project(
        take_dir,
        lyrics=lyrics,
        target_midi=target_midi,
        phrase_timeline=phrase_timeline,
        bpm=bpm,
        tuning_hz=tuning_hz,
        rights_category=rights_category,
        processing_chain=processing_chain,
        target_vocal=target_vocal,
        confirm_common_recorded_zero=confirm_common_recorded_zero,
        confirm_target_reviewed=confirm_target_reviewed,
    )
    destination = Path(out_dir).expanduser().absolute()
    if destination.exists():
        raise ValueError(f"vocal-comp project output already exists: {destination}")
    source_dir = Path(plan["source_directory"])
    if destination == source_dir or source_dir in destination.parents:
        raise ValueError("vocal-comp output must be outside the take directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent)
    )
    os.chmod(temporary, 0o700)
    try:
        takes_dir = temporary / "SOURCES" / "takes"
        target_dir = temporary / "TARGET"
        lyrics_dir = temporary / "LYRICS"
        timeline_dir = temporary / "TIMELINE"
        for directory in (takes_dir, target_dir, lyrics_dir, timeline_dir):
            directory.mkdir(parents=True, exist_ok=True)
            os.chmod(directory, 0o700)

        copied_takes: list[dict[str, Any]] = []
        for row in plan["takes"]:
            source = source_dir / row["source_name"]
            copied = takes_dir / f"{row['take_id']}.wav"
            _copy_private(source, copied)
            if _sha256(source) != row["source"]["sha256"]:
                raise ValueError(f"vocal take changed during import: {source.name}")
            _verify_copied_source(copied, row["source"], source.name)
            copied_takes.append(
                {
                    "take_id": row["take_id"],
                    "label": row["source_name"],
                    "audio": _file_record(copied, relative_to=temporary),
                    "source_sha256": row["source"]["sha256"],
                    "audio_properties": row["audio"],
                    "recorded_zero_offset_seconds": 0.0,
                    "attempt_policy": "silence_is_not_attempted_not_failure",
                }
            )

        copied_lyrics = lyrics_dir / "lyrics.txt"
        copied_target = target_dir / "reviewed-target.mid"
        copied_timeline = timeline_dir / "reviewed-phrase-timeline.json"
        _copy_private(Path(lyrics).expanduser().absolute(), copied_lyrics)
        _copy_private(Path(target_midi).expanduser().absolute(), copied_target)
        _copy_private(Path(phrase_timeline).expanduser().absolute(), copied_timeline)
        _verify_copied_source(copied_lyrics, plan["lyrics"], "lyrics")
        _verify_copied_source(copied_target, plan["target_midi"], "target MIDI")
        _verify_copied_source(
            copied_timeline,
            plan["phrase_timeline"],
            "phrase timeline",
        )
        copied_reference: Path | None = None
        if target_vocal is not None:
            copied_reference = target_dir / "ai-reference-vocal.wav"
            _copy_private(Path(target_vocal).expanduser().absolute(), copied_reference)
            _verify_copied_source(
                copied_reference,
                plan["target_vocal"],
                "target vocal",
            )

        artifacts = {
            str(path.relative_to(temporary)): _file_record(path, relative_to=temporary)
            for path in sorted(temporary.rglob("*"))
            if path.is_file()
        }
        manifest = {
            "schema": VOCAL_COMP_PROJECT_SCHEMA,
            "status": "complete",
            "project_kind": "private_ranked_evidence_pilot",
            "takes": copied_takes,
            "lyrics": _file_record(copied_lyrics, relative_to=temporary),
            "target": {
                "midi": _file_record(copied_target, relative_to=temporary),
                "review_status": "reviewed",
                "authority": "user_confirmed_reviewed_target_melody",
                "reference_vocal": (
                    _file_record(copied_reference, relative_to=temporary)
                    if copied_reference is not None
                    else None
                ),
            },
            "timeline": {
                "document": _file_record(copied_timeline, relative_to=temporary),
                "schema": VOCAL_COMP_TIMELINE_SCHEMA,
                "review_status": "reviewed",
            },
            "bpm": plan["bpm"],
            "tuning_hz": plan["tuning_hz"],
            "rights": {
                "category": plan["rights_category"],
                "authority_confirmed": True,
            },
            "processing_chain": plan["processing_chain"],
            "recorded_zero": "common_confirmed",
            "ai_voice_policy": "fallback_only",
            "artifacts": artifacts,
            "network_used": False,
            "effects": _zero_effects(),
        }
        manifest["project_sha256"] = _document_sha256(manifest)
        manifest_path = temporary / "vocal-comp-project.json"
        _write_json(manifest_path, manifest)
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return _relocate_project(manifest, destination)


def analyze_vocal_comp_project(
    project: str | Path,
    *,
    out_dir: str | Path,
    rmvpe_frames: Mapping[str, str | Path] | None = None,
    fmin_hz: float = 65.4,
    fmax_hz: float = 1046.5,
) -> dict[str, Any]:
    """Publish phrase rankings and pickups without selecting or rendering."""

    project_path = Path(project).expanduser().absolute()
    manifest_path = (
        project_path / "vocal-comp-project.json"
        if project_path.is_dir()
        else project_path
    )
    root = manifest_path.parent
    manifest = _read_json(manifest_path)
    _verify_project(root, manifest)
    destination = Path(out_dir).expanduser().absolute()
    if destination.exists():
        raise ValueError(f"vocal-comp analysis output already exists: {destination}")
    if destination == root or root in destination.parents:
        raise ValueError("analysis output must be outside the immutable project")
    destination.parent.mkdir(parents=True, exist_ok=True)
    unknown_evidence = set(rmvpe_frames or {}) - {
        row["take_id"] for row in manifest["takes"]
    }
    if unknown_evidence:
        raise ValueError(
            "RMVPE evidence names unknown takes: " + ", ".join(sorted(unknown_evidence))
        )

    timeline = _read_json(root / manifest["timeline"]["document"]["path"])
    phrases = _validated_phrase_rows(timeline)
    target_notes = _read_midi_notes(root / manifest["target"]["midi"]["path"])
    config = VocalConfig(
        role="lead",
        tuning_hz=float(manifest["tuning_hz"]),
        tuning_source="vocal-comp-project",
        bpm=float(manifest["bpm"]),
        fmin_hz=float(fmin_hz),
        fmax_hz=float(fmax_hz),
        tracker_mode="consensus",
        phrase_repair=False,
    )
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent)
    )
    os.chmod(temporary, 0o700)
    try:
        evidence_dir = temporary / "EVIDENCE"
        audio_dir = temporary / "AUDIO"
        evidence_dir.mkdir()
        audio_dir.mkdir()
        os.chmod(evidence_dir, 0o700)
        os.chmod(audio_dir, 0o700)
        analyses: dict[str, dict[str, Any]] = {}
        measurements: dict[str, dict[str, dict[str, Any]]] = {}
        for take in manifest["takes"]:
            take_id = take["take_id"]
            audio_path = root / take["audio"]["path"]
            pyin = extract_pitch_frames(audio_path, config=config)
            basic_candidates = extract_backing_candidates(audio_path, config=config)
            basic = project_basic_pitch_candidates(
                basic_candidates,
                config=config,
                reference_frames=pyin,
            )
            trackers: dict[str, Sequence[PitchFrame]] = {
                "pyin": pyin,
                "basic-pitch": basic,
            }
            rmvpe_record = None
            if rmvpe_frames and take_id in rmvpe_frames:
                rmvpe, rmvpe_record = load_rmvpe_evidence(
                    rmvpe_frames[take_id],
                    source_sha256=take["source_sha256"],
                    reference_frames=pyin,
                )
                trackers["rmvpe"] = rmvpe
                rmvpe_record = _path_free_rmvpe_record(rmvpe_record)
            consensus, audit = consensus_pitch_frames_with_audit(
                trackers,
                config=config,
            )
            signal = _signal_record(audio_path)
            analysis = {
                "schema": VOCAL_TAKE_ANALYSIS_SCHEMA,
                "take_id": take_id,
                "source": take["audio"],
                "trackers": sorted(trackers),
                "rmvpe_evidence": rmvpe_record,
                "independent_evidence": {
                    "pyin_frames": [_frame_values(frame) for frame in pyin],
                    "basic_pitch_candidates": [
                        _candidate_values(candidate)
                        for candidate in basic_candidates
                    ],
                    "basic_pitch_projected_frames": [
                        _frame_values(frame) for frame in basic
                    ],
                    "rmvpe_frames": (
                        [_frame_values(frame) for frame in trackers["rmvpe"]]
                        if "rmvpe" in trackers
                        else None
                    ),
                },
                "frame_count": len(consensus),
                "classification_counts": _counts(
                    row.get("classification", "unknown") for row in audit
                ),
                "signal": signal,
                "frame_fields": [
                    "time_seconds",
                    "frequency_hz",
                    "confidence",
                    "rms",
                    "onset_strength",
                    "source",
                ],
                "frames": [_frame_values(frame) for frame in consensus],
                "consensus_audit": audit,
                "selection_effect": False,
                "render_effect": False,
                "correction_effect": False,
            }
            evidence_path = evidence_dir / f"{take_id}.json"
            _write_json(evidence_path, analysis)
            analyses[take_id] = {
                **analysis,
                "evidence": _file_record(evidence_path, relative_to=temporary),
            }
            measurements[take_id] = {
                phrase["phrase_id"]: _measure_phrase(
                    phrase,
                    target_notes=target_notes,
                    frames=consensus,
                    audit=audit,
                    signal=signal,
                    tuning_hz=config.tuning_hz,
                )
                for phrase in phrases
            }

        phrase_reports: list[dict[str, Any]] = []
        pickup_rows: list[dict[str, Any]] = []
        for phrase in phrases:
            phrase_id = phrase["phrase_id"]
            candidates = [
                {
                    "take_id": take["take_id"],
                    **measurements[take["take_id"]][phrase_id],
                }
                for take in manifest["takes"]
            ]
            candidates.sort(key=_candidate_sort_key)
            for rank, candidate in enumerate(
                (row for row in candidates if row["state"] == "eligible"), 1
            ):
                candidate["rank"] = rank
            acceptable = [row for row in candidates if row["acceptable"]]
            fallback = None
            if not acceptable and manifest["target"].get("reference_vocal"):
                fallback = {
                    "kind": "ai_reference_vocal",
                    "state": "available_for_review",
                    "policy": "fallback_only_after_no_acceptable_human_candidate",
                }
            ranked_ids = [
                row["take_id"]
                for row in candidates
                if row["state"] == "eligible"
            ]
            report = {
                "phrase_id": phrase_id,
                "start_seconds": phrase["start_seconds"],
                "end_seconds": phrase["end_seconds"],
                "lyrics": phrase["lyrics"],
                "target_notes": _target_rows(target_notes, phrase),
                "status": (
                    "ranked_human_candidates"
                    if acceptable
                    else "no_acceptable_candidate"
                ),
                "ranked_candidate_ids": ranked_ids,
                "top_three_candidate_ids": ranked_ids[:3],
                "candidates": candidates,
                "ai_fallback": fallback,
                "automatic_selection": False,
            }
            phrase_reports.append(report)
            if not acceptable:
                pickup_rows.append(_pickup_row(report))

        _write_audition_excerpts(
            temporary,
            project_root=root,
            manifest=manifest,
            phrase_reports=phrase_reports,
        )
        candidates_document = {
            "schema": VOCAL_COMP_CANDIDATES_SCHEMA,
            "status": "complete_unreviewed",
            "project": _identity_record(manifest_path),
            "project_sha256": manifest["project_sha256"],
            "ranking_policy": RANKING_POLICY,
            "phrase_count": len(phrase_reports),
            "take_count": len(manifest["takes"]),
            "phrases": phrase_reports,
            "automatic_selection": False,
            "audio_rendered": False,
            "correction_applied": False,
            "network_used": False,
            "effects": _zero_effects(),
        }
        pickups_document = {
            "schema": VOCAL_COMP_PICKUPS_SCHEMA,
            "status": "complete_unreviewed",
            "project_sha256": manifest["project_sha256"],
            "pickup_count": len(pickup_rows),
            "pickups": pickup_rows,
            "ai_voice_policy": "fallback_only",
            "automatic_selection": False,
            "effects": _zero_effects(),
        }
        candidates_path = temporary / "phrase-candidates.json"
        pickups_path = temporary / "pickup-plan.json"
        csv_path = temporary / "phrase-candidates.csv"
        html_path = temporary / "vocal-comp-report.html"
        _write_json(candidates_path, candidates_document)
        _write_json(pickups_path, pickups_document)
        _write_candidates_csv(csv_path, phrase_reports)
        html_path.write_text(_report_html(phrase_reports), encoding="utf-8")
        os.chmod(html_path, 0o600)
        artifacts = {
            str(path.relative_to(temporary)): _file_record(path, relative_to=temporary)
            for path in sorted(temporary.rglob("*"))
            if path.is_file()
        }
        result = {
            "schema": "sunofriend.vocal-comp-analysis.v1",
            "status": "complete_unreviewed",
            "project": _identity_record(manifest_path),
            "project_sha256": manifest["project_sha256"],
            "take_analyses": {
                take_id: analyses[take_id]["evidence"] for take_id in sorted(analyses)
            },
            "candidates": _file_record(candidates_path, relative_to=temporary),
            "pickups": _file_record(pickups_path, relative_to=temporary),
            "csv": _file_record(csv_path, relative_to=temporary),
            "html": _file_record(html_path, relative_to=temporary),
            "artifacts": artifacts,
            "phrase_count": len(phrase_reports),
            "no_acceptable_candidate_count": len(pickup_rows),
            "automatic_selection": False,
            "audio_rendered": False,
            "correction_applied": False,
            "network_used": False,
            "effects": _zero_effects(),
        }
        result["analysis_sha256"] = _document_sha256(result)
        result_path = temporary / "vocal-comp-analysis.json"
        _write_json(result_path, result)
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return _relocate_analysis(result, destination)


def _measure_phrase(
    phrase: Mapping[str, Any],
    *,
    target_notes: Sequence[NoteEvent],
    frames: Sequence[PitchFrame],
    audit: Sequence[Mapping[str, Any]],
    signal: Mapping[str, Any],
    tuning_hz: float,
) -> dict[str, Any]:
    start = float(phrase["start_seconds"])
    end = float(phrase["end_seconds"])
    selected = [frame for frame in frames if start <= frame.time < end]
    audit_by_time = {
        round(float(row.get("time_seconds", -1.0)), 6): row for row in audit
    }
    targets = [note for note in target_notes if note.end > start and note.start < end]
    target_frames: list[tuple[PitchFrame, NoteEvent, Mapping[str, Any] | None]] = []
    for frame in selected:
        active = [note for note in targets if note.start <= frame.time < note.end]
        if active:
            target_frames.append(
                (frame, active[0], audit_by_time.get(round(frame.time, 6)))
            )
    floor = max(5e-4, float(signal["rms_linear"]) * 0.08)
    activity_ratio = (
        sum(frame.rms >= floor for frame in selected) / len(selected)
        if selected
        else 0.0
    )
    pitched = [row for row in target_frames if row[0].f0_hz is not None]
    voiced_coverage = len(pitched) / len(target_frames) if target_frames else 0.0
    agreements = sum(
        1
        for _frame, _target, row in target_frames
        if row is not None and row.get("classification") == "agreement"
    )
    agreement_coverage = agreements / len(target_frames) if target_frames else 0.0
    errors: list[float] = []
    octave_errors: list[float] = []
    for frame, target, _row in pitched:
        observed = hz_to_fractional_midi(float(frame.f0_hz), tuning_hz)
        error = (observed - target.pitch) * 100.0
        errors.append(error)
        octave_errors.append(abs(error - round(error / 1200.0) * 1200.0))
    exact = sum(abs(value) <= 50.0 for value in errors) / len(errors) if errors else 0.0
    octave = sum(value <= 50.0 for value in octave_errors) / len(octave_errors) if octave_errors else 0.0
    target_start = min((note.start for note in targets), default=start)
    target_end = max((note.end for note in targets), default=end)
    voiced_times = [frame.time for frame, _target, _row in pitched]
    onset_error = voiced_times[0] - target_start if voiced_times else None
    offset_error = voiced_times[-1] - target_end if voiced_times else None
    timing_error = (
        (abs(onset_error) + abs(offset_error)) / 2.0
        if onset_error is not None and offset_error is not None
        else RANKING_POLICY["timing_full_penalty_seconds"]
    )
    timing_score = max(
        0.0,
        1.0
        - timing_error / float(RANKING_POLICY["timing_full_penalty_seconds"]),
    )
    melody_score = 0.60 * exact + 0.40 * octave
    completeness_score = min(1.0, voiced_coverage / 0.80)
    signal_score = 0.0 if signal["full_scale_sample_count"] else 1.0
    uncertainty_penalty = (
        1.0 - agreement_coverage
    ) * float(RANKING_POLICY["uncertainty_penalty_maximum"])
    score = max(
        0.0,
        0.50 * melody_score
        + 0.25 * completeness_score
        + 0.20 * timing_score
        + 0.05 * signal_score
        - uncertainty_penalty,
    )
    block_reasons: list[str] = []
    if activity_ratio < float(RANKING_POLICY["not_attempted_activity_ratio_below"]):
        state = "not_attempted"
        block_reasons.append("not_attempted_low_activity")
    elif signal["full_scale_sample_count"]:
        state = "blocked_signal"
        block_reasons.append("full_scale_samples")
    elif agreement_coverage < float(RANKING_POLICY["minimum_agreement_coverage"]):
        state = "insufficient_evidence"
        block_reasons.append("insufficient_multi_tracker_agreement")
    elif not targets:
        state = "insufficient_evidence"
        block_reasons.append("target_contains_no_notes")
    else:
        state = "eligible"
    acceptable = bool(
        state == "eligible"
        and score >= float(RANKING_POLICY["minimum_acceptable_score"])
        and voiced_coverage
        >= float(RANKING_POLICY["minimum_acceptable_voiced_coverage"])
    )
    if state == "eligible" and not acceptable:
        block_reasons.append("below_experimental_acceptance_floor")
    return {
        "state": state,
        "acceptable": acceptable,
        "score": round(score, 6),
        "dimensions": {
            "melody": round(melody_score, 6),
            "completeness": round(completeness_score, 6),
            "timing": round(timing_score, 6),
            "signal": round(signal_score, 6),
            "uncertainty_penalty": round(uncertainty_penalty, 6),
        },
        "measurements": {
            "activity_ratio": round(activity_ratio, 6),
            "target_frame_count": len(target_frames),
            "voiced_coverage": round(voiced_coverage, 6),
            "multi_tracker_agreement_coverage": round(agreement_coverage, 6),
            "exact_register_within_50_cents": round(exact, 6),
            "octave_aware_within_50_cents": round(octave, 6),
            "signed_pitch_error_median_cents": _round_or_none(
                median(errors) if errors else None
            ),
            "absolute_pitch_error_p90_cents": _round_or_none(
                _percentile([abs(value) for value in errors], 90.0)
                if errors
                else None
            ),
            "onset_displacement_seconds": _round_or_none(onset_error),
            "offset_displacement_seconds": _round_or_none(offset_error),
        },
        "block_reasons": block_reasons,
        "expression_score_used": False,
        "automatic_selection": False,
    }


def _load_timeline(path: Path, canonical_lyrics: str) -> dict[str, Any]:
    if path.stat().st_size > _MAX_TIMELINE_BYTES:
        raise ValueError("phrase timeline must be no larger than 512 KiB")
    timeline = _read_json(path)
    if timeline.get("schema") != VOCAL_COMP_TIMELINE_SCHEMA:
        raise ValueError(f"phrase timeline schema must be {VOCAL_COMP_TIMELINE_SCHEMA}")
    if timeline.get("status") != "reviewed":
        raise ValueError("phrase timeline must have status reviewed")
    phrases = _validated_phrase_rows(timeline)
    canonical_words = _words(canonical_lyrics)
    position = 0
    for phrase in phrases:
        phrase_words = _words(phrase["lyrics"])
        if not phrase_words:
            raise ValueError(f"phrase {phrase['phrase_id']} has no lyric words")
        found = _find_words(canonical_words, phrase_words, position)
        if found is None:
            raise ValueError(
                f"phrase {phrase['phrase_id']} lyrics are not in canonical lyric order"
            )
        position = found + len(phrase_words)
    return timeline


def _validated_phrase_rows(timeline: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = timeline.get("phrases")
    if not isinstance(raw, list) or not 1 <= len(raw) <= _MAX_PHRASES:
        raise ValueError("phrase timeline requires 1-128 phrase rows")
    result: list[dict[str, Any]] = []
    ids: set[str] = set()
    previous_end = 0.0
    for row in raw:
        if not isinstance(row, Mapping):
            raise ValueError("each phrase row must be an object")
        phrase_id = str(row.get("phrase_id", ""))
        if not _PHRASE_ID.fullmatch(phrase_id) or phrase_id in ids:
            raise ValueError("phrase IDs must be unique safe identifiers")
        start = float(row.get("start_seconds", -1.0))
        end = float(row.get("end_seconds", -1.0))
        if not math.isfinite(start) or not math.isfinite(end) or start < 0:
            raise ValueError(f"phrase {phrase_id} has invalid bounds")
        duration = end - start
        if not _MIN_PHRASE_SECONDS <= duration <= _MAX_PHRASE_SECONDS:
            raise ValueError(f"phrase {phrase_id} duration must be 0.1-30 seconds")
        if result and start < previous_end - 1e-9:
            raise ValueError("phrase rows must be chronological and non-overlapping")
        lyric_text = str(row.get("lyrics", "")).strip()
        if not lyric_text:
            raise ValueError(f"phrase {phrase_id} must bind canonical lyrics")
        ids.add(phrase_id)
        previous_end = end
        result.append(
            {
                "phrase_id": phrase_id,
                "start_seconds": start,
                "end_seconds": end,
                "lyrics": lyric_text,
            }
        )
    return result


def _read_midi_notes(path: Path) -> list[NoteEvent]:
    try:
        import mido
    except ImportError as exc:
        raise RuntimeError("vocal comping requires the optional mido dependency") from exc
    midi = mido.MidiFile(str(path))
    tempo = 500_000
    elapsed = 0.0
    active: dict[tuple[int, int], list[tuple[float, int]]] = {}
    notes: list[NoteEvent] = []
    for message in mido.merge_tracks(midi.tracks):
        elapsed += mido.tick2second(message.time, midi.ticks_per_beat, tempo)
        if message.type == "set_tempo":
            tempo = int(message.tempo)
        elif message.type == "note_on" and message.velocity > 0:
            active.setdefault((message.channel, message.note), []).append(
                (elapsed, int(message.velocity))
            )
        elif message.type in {"note_off", "note_on"}:
            key = (message.channel, message.note)
            queue = active.get(key, [])
            if queue:
                start, velocity = queue.pop(0)
                if elapsed > start:
                    notes.append(NoteEvent(start, elapsed, message.note, velocity))
    return sorted(notes, key=lambda note: (note.start, note.pitch, note.end))


def _validate_target_notes(notes: Sequence[NoteEvent]) -> None:
    if not notes:
        raise ValueError("target MIDI must contain at least one note")
    active_end = notes[0].end
    active_pitch = notes[0].pitch
    for current in notes[1:]:
        if current.start < active_end - 0.02 and current.pitch != active_pitch:
            raise ValueError("target MIDI must contain one unambiguous monophonic lead line")
        if current.start >= active_end - 0.02 or current.end > active_end:
            active_end = current.end
            active_pitch = current.pitch


def _signal_record(path: Path) -> dict[str, Any]:
    import numpy as np
    import soundfile

    square_sum = 0.0
    sample_count = 0
    peak = 0.0
    full_scale = 0
    dc_sum = 0.0
    with soundfile.SoundFile(path) as handle:
        for block in handle.blocks(blocksize=1 << 18, dtype="float64", always_2d=True):
            if not block.size:
                continue
            peak = max(peak, float(np.max(np.abs(block))))
            full_scale += int(np.count_nonzero(np.abs(block) >= 1.0))
            square_sum += float(np.sum(block * block))
            dc_sum += float(np.sum(block))
            sample_count += int(block.size)
    rms = math.sqrt(square_sum / sample_count) if sample_count else 0.0
    return {
        "peak_linear": round(peak, 9),
        "peak_dbfs": _dbfs(peak),
        "rms_linear": round(rms, 9),
        "rms_dbfs": _dbfs(rms),
        "dc_offset": round(dc_sum / sample_count, 9) if sample_count else 0.0,
        "full_scale_sample_count": full_scale,
        "absolute_loudness_used_for_ranking": False,
    }


def _audio_record(path: Path) -> dict[str, Any]:
    import soundfile

    info = soundfile.info(path)
    if info.format != "WAV":
        raise ValueError(f"vocal take must be a WAV file: {path.name}")
    if info.frames <= 0 or info.samplerate <= 0 or not 1 <= info.channels <= 2:
        raise ValueError(f"vocal take has unsupported audio geometry: {path.name}")
    return {
        "format": info.format,
        "subtype": info.subtype,
        "sample_rate": int(info.samplerate),
        "channels": int(info.channels),
        "frames": int(info.frames),
        "duration_seconds": round(info.frames / info.samplerate, 9),
    }


def _write_audition_excerpts(
    output_root: Path,
    *,
    project_root: Path,
    manifest: Mapping[str, Any],
    phrase_reports: Sequence[Mapping[str, Any]],
) -> None:
    take_paths = {
        row["take_id"]: project_root / row["audio"]["path"]
        for row in manifest["takes"]
    }
    reference = manifest["target"].get("reference_vocal")
    for phrase in phrase_reports:
        ids = phrase["top_three_candidate_ids"]
        for take_id in ids:
            relative = Path("AUDIO") / f"{phrase['phrase_id']}-{take_id}.wav"
            _write_excerpt(
                take_paths[take_id],
                output_root / relative,
                float(phrase["start_seconds"]),
                float(phrase["end_seconds"]),
            )
            candidate = next(
                row for row in phrase["candidates"] if row["take_id"] == take_id
            )
            candidate["audition"] = str(relative)
        if phrase.get("ai_fallback") and reference:
            relative = Path("AUDIO") / f"{phrase['phrase_id']}-ai-fallback.wav"
            _write_excerpt(
                project_root / reference["path"],
                output_root / relative,
                float(phrase["start_seconds"]),
                float(phrase["end_seconds"]),
            )
            phrase["ai_fallback"]["audition"] = str(relative)


def _write_excerpt(source: Path, destination: Path, start: float, end: float) -> None:
    import soundfile

    with soundfile.SoundFile(source) as handle:
        sample_rate = int(handle.samplerate)
        first = max(0, int(round((start - 0.15) * sample_rate)))
        final = min(len(handle), int(round((end + 0.15) * sample_rate)))
        handle.seek(first)
        values = handle.read(final - first, dtype="float64", always_2d=True)
    soundfile.write(destination, values, sample_rate, subtype="PCM_24")
    os.chmod(destination, 0o600)


def _write_candidates_csv(path: Path, phrases: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "phrase_id",
                "take_id",
                "rank",
                "state",
                "acceptable",
                "score",
                "melody",
                "completeness",
                "timing",
                "signal",
                "uncertainty_penalty",
                "block_reasons",
            ),
        )
        writer.writeheader()
        for phrase in phrases:
            for candidate in phrase["candidates"]:
                writer.writerow(
                    {
                        "phrase_id": phrase["phrase_id"],
                        "take_id": candidate["take_id"],
                        "rank": candidate.get("rank"),
                        "state": candidate["state"],
                        "acceptable": candidate["acceptable"],
                        "score": candidate["score"],
                        **candidate["dimensions"],
                        "block_reasons": ";".join(candidate["block_reasons"]),
                    }
                )
    os.chmod(path, 0o600)


def _report_html(phrases: Sequence[Mapping[str, Any]]) -> str:
    cards: list[str] = []
    for phrase in phrases:
        rows: list[str] = []
        for candidate in phrase["candidates"]:
            audio = candidate.get("audition")
            player = (
                f'<audio controls preload="none" src="{html.escape(audio)}"></audio>'
                if audio
                else ""
            )
            rows.append(
                "<tr>"
                f"<td>{html.escape(candidate['take_id'])}</td>"
                f"<td>{candidate.get('rank', '')}</td>"
                f"<td>{html.escape(candidate['state'])}</td>"
                f"<td>{candidate['score']:.3f}</td>"
                f"<td>{candidate['measurements']['exact_register_within_50_cents']:.3f}</td>"
                f"<td>{candidate['measurements']['voiced_coverage']:.3f}</td>"
                f"<td>{candidate['measurements']['multi_tracker_agreement_coverage']:.3f}</td>"
                f"<td>{player}</td>"
                "</tr>"
            )
        fallback = ""
        if phrase.get("ai_fallback"):
            audio = html.escape(phrase["ai_fallback"].get("audition", ""))
            fallback = (
                '<p class="fallback">No acceptable human candidate. '
                'AI reference is available as fallback only. '
                f'<audio controls preload="none" src="{audio}"></audio></p>'
            )
        cards.append(
            f"<section><h2>{html.escape(phrase['phrase_id'])}: "
            f"{phrase['start_seconds']:.2f}-{phrase['end_seconds']:.2f}s</h2>"
            f"<p>{html.escape(phrase['lyrics'])}</p>"
            f"<p>Status: <strong>{html.escape(phrase['status'])}</strong>. "
            "Ranks are evidence, not selections.</p>"
            "<table><thead><tr><th>Take</th><th>Rank</th><th>State</th>"
            "<th>Score</th><th>Exact pitch</th><th>Voiced</th>"
            "<th>Agreement</th><th>Audition</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table>"
            + fallback
            + "</section>"
        )
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Sunofriend vocal comp evidence</title><style>
body{font-family:system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;background:#10131a;color:#eef2ff}
section{background:#1b2030;border:1px solid #343c55;border-radius:12px;padding:1rem;margin:1rem 0;overflow:auto}
table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #343c55;padding:.5rem;text-align:left}audio{max-width:240px}.fallback{color:#ffd58a}
</style></head><body><h1>Ranked vocal-comp evidence</h1>
<p>This private report renders no comp, applies no correction and makes no selection. Expression has zero ranking weight.</p>
""" + "".join(cards) + "</body></html>\n"


def _pickup_row(report: Mapping[str, Any]) -> dict[str, Any]:
    reasons = _counts(
        reason
        for candidate in report["candidates"]
        for reason in candidate["block_reasons"]
    )
    notes = report["target_notes"]
    return {
        "phrase_id": report["phrase_id"],
        "start_seconds": report["start_seconds"],
        "end_seconds": report["end_seconds"],
        "lyrics": report["lyrics"],
        "reason_counts": reasons,
        "target_pitches": sorted({row["pitch"] for row in notes}),
        "target_note_count": len(notes),
        "instruction": (
            "Record another complete musical phrase against the same recorded zero; "
            "retain the breath that leads into the phrase and the same processing chain."
        ),
        "ai_fallback_available": report.get("ai_fallback") is not None,
    }


def _target_rows(notes: Sequence[NoteEvent], phrase: Mapping[str, Any]) -> list[dict[str, Any]]:
    start = float(phrase["start_seconds"])
    end = float(phrase["end_seconds"])
    return [
        {
            "start_seconds": note.start,
            "end_seconds": note.end,
            "pitch": note.pitch,
        }
        for note in notes
        if note.end > start and note.start < end
    ]


def _verify_project(root: Path, manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema") != VOCAL_COMP_PROJECT_SCHEMA or manifest.get("status") != "complete":
        raise ValueError("unsupported or incomplete vocal-comp project")
    expected = manifest.get("project_sha256")
    copy = dict(manifest)
    copy.pop("project_sha256", None)
    if expected != _document_sha256(copy):
        raise ValueError("vocal-comp project manifest hash does not match")
    for relative, record in manifest.get("artifacts", {}).items():
        path = root / _safe_relative(relative)
        _verify_file_record(path, record)


def _candidate_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    state_order = {"eligible": 0, "insufficient_evidence": 1, "blocked_signal": 2, "not_attempted": 3}
    return (state_order.get(str(row["state"]), 9), -float(row["score"]), str(row["take_id"]))


def _zero_effects() -> dict[str, bool]:
    return {
        "source_mutated": False,
        "target_mutated": False,
        "lyrics_mutated": False,
        "selection_created": False,
        "human_decision_created": False,
        "audio_comp_rendered": False,
        "pitch_correction_applied": False,
        "ai_voice_generated": False,
    }


def _copy_private(source: Path, destination: Path) -> None:
    shutil.copyfile(source, destination)
    os.chmod(destination, 0o600)


def _verify_copied_source(
    copied: Path,
    source_record: Mapping[str, Any],
    label: str,
) -> None:
    actual = _identity_record(copied)
    if (
        actual["bytes"] != source_record.get("bytes")
        or actual["sha256"] != source_record.get("sha256")
    ):
        raise ValueError(f"{label} changed during import")


def _file_record(path: Path, *, relative_to: Path | None = None) -> dict[str, Any]:
    label = path.relative_to(relative_to) if relative_to else path
    return {"path": str(label), "bytes": path.stat().st_size, "sha256": _sha256(path)}


def _identity_record(path: Path) -> dict[str, Any]:
    return {"bytes": path.stat().st_size, "sha256": _sha256(path)}


def _path_free_rmvpe_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return _without_path_fields(record)


def _without_path_fields(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _without_path_fields(item)
            for key, item in value.items()
            if str(key).casefold() != "path"
        }
    if isinstance(value, (list, tuple)):
        return [_without_path_fields(item) for item in value]
    return value


def _verify_file_record(path: Path, record: Mapping[str, Any]) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"project artifact is missing or linked: {path}")
    actual = _file_record(path)
    if actual["bytes"] != record.get("bytes") or actual["sha256"] != record.get("sha256"):
        raise ValueError(f"project artifact changed: {path.name}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _document_sha256(document: Mapping[str, Any]) -> str:
    payload = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON document: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return value


def _file(value: str | Path | None, label: str) -> Path:
    path = Path(str(value)).expanduser().absolute()
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} does not exist or is linked: {path}")
    return path


def _directory(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser().absolute()
    if not path.is_dir() or path.is_symlink():
        raise ValueError(f"{label} does not exist or is linked: {path}")
    return path


def _safe_relative(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("project artifact paths must remain relative")
    return path


def _words(value: str) -> list[str]:
    return re.findall(r"[\w']+", value.casefold(), flags=re.UNICODE)


def _find_words(haystack: Sequence[str], needle: Sequence[str], start: int) -> int | None:
    for index in range(start, len(haystack) - len(needle) + 1):
        if list(haystack[index : index + len(needle)]) == list(needle):
            return index
    return None


def _counts(values: Sequence[str] | Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        key = str(value)
        result[key] = result.get(key, 0) + 1
    return dict(sorted(result.items()))


def _frame_values(frame: PitchFrame) -> list[Any]:
    return [frame.time, frame.f0_hz, frame.voiced_probability, frame.rms, frame.onset_strength, frame.source]


def _candidate_values(candidate: Any) -> dict[str, Any]:
    return {
        "start_seconds": candidate.note.start,
        "end_seconds": candidate.note.end,
        "pitch": candidate.note.pitch,
        "velocity": candidate.note.velocity,
        "confidence": candidate.confidence,
        "spectral_support": candidate.spectral_support,
        "sources": list(candidate.sources),
    }


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile / 100.0
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _round_or_none(value: float | None) -> float | None:
    return round(float(value), 6) if value is not None and math.isfinite(float(value)) else None


def _dbfs(value: float) -> float | None:
    return round(20.0 * math.log10(value), 6) if value > 0 else None


def _relocate_project(manifest: Mapping[str, Any], destination: Path) -> dict[str, Any]:
    return {
        **manifest,
        "project": str(destination / "vocal-comp-project.json"),
        "output_directory": str(destination),
    }


def _relocate_analysis(result: Mapping[str, Any], destination: Path) -> dict[str, Any]:
    return {
        **result,
        "analysis": str(destination / "vocal-comp-analysis.json"),
        "candidates_path": str(destination / result["candidates"]["path"]),
        "pickups_path": str(destination / result["pickups"]["path"]),
        "csv_path": str(destination / result["csv"]["path"]),
        "html_path": str(destination / result["html"]["path"]),
        "output_directory": str(destination),
    }


__all__ = [
    "RANKING_POLICY",
    "VOCAL_COMP_CANDIDATES_SCHEMA",
    "VOCAL_COMP_PICKUPS_SCHEMA",
    "VOCAL_COMP_PROJECT_SCHEMA",
    "VOCAL_COMP_TIMELINE_SCHEMA",
    "VOCAL_TAKE_ANALYSIS_SCHEMA",
    "analyze_vocal_comp_project",
    "create_vocal_comp_project",
    "plan_vocal_comp_project",
]
