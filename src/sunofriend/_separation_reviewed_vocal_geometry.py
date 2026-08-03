"""Pairwise geometry evidence for human-reviewed vocal MIDI candidates.

This private-development report starts only from candidates that a completed
human review marked useful for one exact musical focus.  It compares their
note geometry without treating one candidate as truth, selecting a winner or
creating a merged transcription.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from ._separation_authorised_midi_comparison import (
    _document_sha256,
    _regular_json,
    _sha256,
)
from ._separation_demucs_midi_metrics import _compare_note_events
from ._separation_vocal_candidate_audition import (
    RESOLUTION_SCHEMA,
    _AuditionContext,
    _load_audition_context,
    _open_verified_note_evidence,
    _write_fresh_private_json,
)
from .models import NoteEvent


SCHEMA = "sunofriend.private-reviewed-vocal-geometry.v1"
_MAX_REPORT_BYTES = 256 * 1024
_MAX_NOTE_BYTES = 8 * 1024 * 1024
_DEFAULT_TOLERANCE_SECONDS = 0.080


def _compare_reviewed_vocal_geometry(
    review_resolution_path: str | Path,
    candidate_set_path: str | Path,
    melroformer_evaluation_path: str | Path,
    vocal_leaf_evaluation_path: str | Path,
    phrase_completeness_path: str | Path,
    excerpt_path: str | Path,
    *,
    out: str | Path,
    tolerance_seconds: float = _DEFAULT_TOLERANCE_SECONDS,
) -> dict[str, Any]:
    """Compare useful reviewed candidates without choosing or changing them."""

    tolerance = _positive_tolerance(tolerance_seconds)
    resolution_path, resolution_file_sha256, resolution = _load_resolution(
        review_resolution_path
    )
    scope = resolution["scope"]
    context = _load_audition_context(
        candidate_set_path,
        melroformer_evaluation_path,
        vocal_leaf_evaluation_path,
        phrase_completeness_path,
        excerpt_path,
        focus=resolution["focus"],
        start_seconds=float(scope["start_seconds"]),
        end_seconds=float(scope["end_seconds"]),
        candidate_ids=tuple(scope["candidate_ids"]),
        classify_reference_line=bool(
            resolution["policy"]["human_reference_line_relationships_verified"]
        ),
    )
    _require_resolution_binding(resolution, context)

    useful_ids = tuple(resolution["results"]["useful_for_focus"])
    expected_counts = {
        str(row["candidate_id"]): int(row["note_count"])
        for row in context.candidate_set["candidates"]
    }
    notes = {
        candidate_id: _load_scoped_notes(
            context,
            candidate_id,
            expected_total=expected_counts[candidate_id],
            start_seconds=float(scope["start_seconds"]),
            end_seconds=float(scope["end_seconds"]),
        )
        for candidate_id in useful_ids
    }
    document = _build_document(
        resolution=resolution,
        resolution_file_sha256=resolution_file_sha256,
        useful_notes=notes,
        tolerance_seconds=tolerance,
    )
    document["document_sha256"] = _document_sha256(document)

    if _sha256(resolution_path) != resolution_file_sha256:
        raise ValueError("review resolution changed during geometry comparison")
    _write_fresh_private_json(Path(out), document)
    document["report"] = str(Path(out).expanduser().absolute())
    return document


def _load_resolution(path: str | Path) -> tuple[Path, str, dict[str, Any]]:
    resolution_path = _regular_json(path, "reviewed vocal candidate resolution")
    if resolution_path.stat().st_size > _MAX_REPORT_BYTES:
        raise ValueError("reviewed vocal candidate resolution is too large")
    file_sha256 = _sha256(resolution_path)
    resolution = json.loads(resolution_path.read_text(encoding="utf-8"))
    if (
        not isinstance(resolution, dict)
        or resolution.get("schema") != RESOLUTION_SCHEMA
        or resolution.get("status") != "complete_review_no_activation"
        or resolution.get("evidence_scope") != "private_development_only"
        or resolution.get("document_sha256") != _document_sha256(resolution)
    ):
        raise ValueError("reviewed vocal candidate resolution differs")
    policy = resolution.get("policy")
    effects = resolution.get("effects")
    if not isinstance(policy, Mapping) or not isinstance(effects, Mapping):
        raise ValueError("reviewed vocal candidate resolution policy differs")
    if (
        policy.get("human_dispositions_verified") is not True
        or policy.get("winner_selected") is not False
        or policy.get("automatic_selection") is not False
        or policy.get("automatic_merge") is not False
        or policy.get("automatic_repair") is not False
        or effects.get("candidate_selected") is not False
        or effects.get("midi_created_or_mutated") is not False
        or effects.get("source_graph_mutated") is not False
    ):
        raise ValueError("reviewed vocal candidate resolution is not inactive")
    results = resolution.get("results")
    scope = resolution.get("scope")
    if not isinstance(results, Mapping) or not isinstance(scope, Mapping):
        raise ValueError("reviewed vocal candidate resolution results differ")
    useful = results.get("useful_for_focus")
    candidate_ids = scope.get("candidate_ids")
    if (
        not isinstance(useful, list)
        or len(useful) < 2
        or len(useful) != len(set(useful))
        or not all(isinstance(value, str) and value for value in useful)
        or not isinstance(candidate_ids, list)
        or any(value not in candidate_ids for value in useful)
        or results.get("useful_for_focus_count") != len(useful)
    ):
        raise ValueError("at least two distinct useful reviewed candidates are required")
    return resolution_path, file_sha256, resolution


def _require_resolution_binding(
    resolution: Mapping[str, Any], context: _AuditionContext
) -> None:
    inputs = resolution.get("inputs", {})
    expected = {
        "candidate_set_sha256": context.candidate_set_file_sha256,
        "candidate_set_document_sha256": context.candidate_set["document_sha256"],
        "authorised_excerpt_sha256": context.excerpt_file_sha256,
        "authorised_excerpt_document_sha256": context.excerpt["document_sha256"],
        "review_seed_document_sha256": context.seed["document_sha256"],
    }
    if not isinstance(inputs, Mapping) or any(
        inputs.get(key) != value for key, value in expected.items()
    ):
        raise ValueError("review resolution is not bound to the exact sealed evidence")
    if resolution.get("focus") != context.focus or resolution.get("scope") != dict(
        context.seed["scope"]
    ):
        raise ValueError("review resolution focus or scope differs")


def _load_scoped_notes(
    context: _AuditionContext,
    candidate_id: str,
    *,
    expected_total: int,
    start_seconds: float,
    end_seconds: float,
) -> tuple[NoteEvent, ...]:
    evidence = context.candidate_notes.get(candidate_id)
    if evidence is None:
        raise ValueError("useful reviewed candidate has no note evidence")
    descriptor = _open_verified_note_evidence(evidence)
    try:
        payload = bytearray()
        while len(payload) <= _MAX_NOTE_BYTES:
            block = os.read(
                descriptor, min(128 * 1024, _MAX_NOTE_BYTES + 1 - len(payload))
            )
            if not block:
                break
            payload.extend(block)
    finally:
        os.close(descriptor)
    if len(payload) != evidence.size:
        raise ValueError("vocal candidate note evidence size differs")
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("vocal candidate note evidence is not valid JSON") from error
    raw_notes = document.get("notes") if isinstance(document, Mapping) else None
    if not isinstance(raw_notes, list) or len(raw_notes) != expected_total:
        raise ValueError("vocal candidate note count differs")
    notes: list[NoteEvent] = []
    for raw in raw_notes:
        if not isinstance(raw, Mapping):
            raise ValueError("vocal candidate note geometry differs")
        start = _finite_number(raw.get("start_seconds"), "note start")
        end = _finite_number(raw.get("end_seconds"), "note end")
        pitch = raw.get("pitch")
        velocity = raw.get("velocity")
        if (
            start < 0.0
            or end <= start
            or isinstance(pitch, bool)
            or not isinstance(pitch, int)
            or not 0 <= pitch <= 127
            or isinstance(velocity, bool)
            or not isinstance(velocity, int)
            or not 1 <= velocity <= 127
        ):
            raise ValueError("vocal candidate note geometry differs")
        if start < end_seconds and end > start_seconds:
            notes.append(NoteEvent(start=start, end=end, pitch=pitch, velocity=velocity))
    if not notes:
        raise ValueError("useful reviewed candidate has no notes in the review window")
    return tuple(sorted(notes, key=lambda note: (note.start, note.pitch, note.end)))


def _build_document(
    *,
    resolution: Mapping[str, Any],
    resolution_file_sha256: str,
    useful_notes: Mapping[str, Sequence[NoteEvent]],
    tolerance_seconds: float,
) -> dict[str, Any]:
    useful_ids = tuple(resolution["results"]["useful_for_focus"])
    if tuple(useful_notes) != useful_ids:
        raise ValueError("reviewed useful-candidate order or membership differs")
    candidates = {
        candidate_id: _candidate_geometry(useful_notes[candidate_id])
        for candidate_id in useful_ids
    }
    pairs = []
    for left_index, left_id in enumerate(useful_ids):
        for right_id in useful_ids[left_index + 1 :]:
            pairs.append(
                {
                    "left_candidate_id": left_id,
                    "right_candidate_id": right_id,
                    "orientation": "human_review_order_not_preference",
                    "metrics": _compare_note_events(
                        useful_notes[left_id],
                        useful_notes[right_id],
                        tolerance_seconds=tolerance_seconds,
                    ),
                }
            )
    return {
        "schema": SCHEMA,
        "status": "complete_diagnostic_no_activation",
        "evidence_scope": "private_development_only",
        "inputs": {
            "review_resolution_sha256": resolution_file_sha256,
            "review_resolution_document_sha256": resolution["document_sha256"],
            "review_sha256": resolution["inputs"]["review_sha256"],
            "candidate_set_document_sha256": resolution["inputs"][
                "candidate_set_document_sha256"
            ],
            "authorised_excerpt_document_sha256": resolution["inputs"][
                "authorised_excerpt_document_sha256"
            ],
        },
        "focus": resolution["focus"],
        "scope": dict(resolution["scope"]),
        "policy": {
            "candidate_source": "human_reviewed_useful_for_exact_focus",
            "candidate_count": len(useful_ids),
            "candidate_order": "human_review_order_not_rank",
            "onset_tolerance_ms": round(tolerance_seconds * 1000.0, 9),
            "note_inclusion": "any temporal overlap with the exact review window",
            "pair_orientation_is_preference": False,
            "candidate_ranked_or_selected": False,
            "automatic_merge": False,
            "automatic_repair": False,
            "agreement_is_ground_truth": False,
        },
        "candidates": candidates,
        "pairwise": pairs,
        "observations": {
            "pair_count": len(pairs),
            "agreement_is_diagnostic_only": True,
            "human_listening_remains_authoritative": True,
        },
        "permissions": {
            "accepted": False,
            "automatic_promotion": False,
            "automatic_selection": False,
            "production_eligible": False,
            "public_result": False,
            "simple_mode_available": False,
            "source_graph_activation": False,
            "studio_import_available": False,
        },
        "effects": {
            "audio_created": False,
            "candidate_selected": False,
            "default_changed": False,
            "midi_created_or_mutated": False,
            "source_graph_mutated": False,
            "studio_or_simple_route_enabled": False,
        },
        "limitations": [
            "Pairwise agreement compares estimated MIDI candidates, not a score or isolated-vocal ground truth.",
            "The left and right labels preserve review order and do not make either candidate a reference truth.",
            "Human usefulness labels apply only to the exact written focus and time window.",
            "No candidate is chosen, merged, repaired, promoted or activated by this report.",
        ],
        "next": {
            "candidate_specific_strengths_need_human_interpretation": True,
            "focused_note_correction_review_created": False,
            "automatic_merge_allowed": False,
        },
    }


def _candidate_geometry(notes: Sequence[NoteEvent]) -> dict[str, Any]:
    if not notes:
        raise ValueError("reviewed useful candidate note set is empty")
    pitches = [note.pitch for note in notes]
    durations = [note.end - note.start for note in notes]
    return {
        "note_count": len(notes),
        "pitch_min": min(pitches),
        "pitch_max": max(pitches),
        "distinct_pitch_count": len(set(pitches)),
        "first_onset_seconds": round(min(note.start for note in notes), 6),
        "last_onset_seconds": round(max(note.start for note in notes), 6),
        "median_note_duration_seconds": round(_median(durations), 6),
    }


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _positive_tolerance(raw: Any) -> float:
    value = _finite_number(raw, "onset tolerance")
    if not 0.0 < value <= 0.5:
        raise ValueError("onset tolerance must be greater than zero and at most 0.5 seconds")
    return value


def _finite_number(raw: Any, label: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(f"{label} differs")
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError(f"{label} differs")
    return value


__all__: Sequence[str] = ()
