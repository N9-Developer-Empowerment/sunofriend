"""Cross-song MIDI agreement over source-bound private separation evidence.

This owner-only report repeats one candidate/control method pair across songs.
It recomputes the existing note metric from sealed note evidence, verifies that
both sides came from the same authorised excerpt, and remains descriptive:
agreement is not transcription accuracy, listening preference or acceptance.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from ._separation_authorised_excerpt import (
    AUTHORISED_EXCERPT_SCHEMA,
    _document_sha256 as _excerpt_document_sha256,
)
from ._separation_authorised_midi_comparison import (
    AUTHORISED_MIDI_COMPARISON_SCHEMA,
    _artifact_path,
    _document_sha256,
    _regular_json,
    _sha256,
)
from ._separation_authorised_role_mapping import (
    AUTHORISED_ROLE_MAPPING_SCHEMA,
    _document_sha256 as _mapping_document_sha256,
)
from ._separation_corpus_coverage import _load_index
from ._separation_cross_song_evidence_index import _ID_PATTERN
from ._separation_demucs_midi_metrics import _compare_note_events
from ._separation_demucs_refinement_evaluation import _validated_notes
from ._separation_melroformer_midi_evaluation import (
    SCHEMA as MELROFORMER_MIDI_SCHEMA,
    _load_control_notes,
    _validated_control_policy,
)
from ._separation_vocal_candidate_audition import _write_fresh_private_json
from .models import NoteEvent


SCHEMA = "sunofriend.private-separation-normalized-midi-agreement.v1"
_METRIC_SCHEMA = "sunofriend.private-demucs-midi-note-metrics.v1"
_MAXIMUM_COMPARISONS = 64
_MAXIMUM_REPORT_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class MidiAgreementInput:
    """The four sealed reports required to prove one same-excerpt cell."""

    track_id: str
    candidate_report: Path
    control_comparison: Path
    role_mapping: Path
    authorised_excerpt: Path


@dataclass(frozen=True)
class _LoadedJson:
    path: Path
    file_sha256: str
    document: dict[str, Any]


@dataclass(frozen=True)
class _LoadedCell:
    track_id: str
    source_track_id: str
    candidate: _LoadedJson
    control: _LoadedJson
    mapping: _LoadedJson
    excerpt: _LoadedJson
    metrics: dict[str, Any]
    control_note_count: int
    candidate_note_count: int


def _normalize_private_separation_midi_agreement(
    evidence_index_path: str | Path,
    comparisons: Sequence[MidiAgreementInput],
    *,
    candidate_method_family: str,
    control_method_family: str,
    control_id: str,
    out: str | Path,
) -> dict[str, Any]:
    """Recompute one source-bound MIDI agreement contract across songs."""

    candidate_method = _safe_id(candidate_method_family, "candidate method family")
    control_method = _safe_id(control_method_family, "control method family")
    control = _safe_id(control_id, "control ID")
    if candidate_method == control_method:
        raise ValueError("candidate and control method families must differ")
    if not 2 <= len(comparisons) <= _MAXIMUM_COMPARISONS:
        raise ValueError("normalized MIDI agreement requires 2-64 song comparisons")

    index_path, index_file_sha256, index = _load_index(evidence_index_path)
    track_ids = [_safe_id(item.track_id, "track ID") for item in comparisons]
    if len(track_ids) != len(set(track_ids)):
        raise ValueError("normalized MIDI agreement track IDs must be unique")

    indexed = _indexed_cells(index)
    loaded = tuple(
        _load_cell(
            item,
            track_id=track_id,
            control_id=control,
            indexed=indexed,
            candidate_method=candidate_method,
            control_method=control_method,
        )
        for item, track_id in zip(comparisons, track_ids)
    )
    ordered = tuple(sorted(loaded, key=lambda item: item.track_id))
    document = _build_document(
        index=index,
        index_file_sha256=index_file_sha256,
        cells=ordered,
        candidate_method=candidate_method,
        control_method=control_method,
        control_id=control,
    )
    document["document_sha256"] = _document_sha256(document)
    _reverify(index_path, index_file_sha256, ordered, control_id=control)
    _write_fresh_private_json(Path(out), document)
    document["report"] = str(Path(out).expanduser().absolute())
    return document


def _load_cell(
    source: MidiAgreementInput,
    *,
    track_id: str,
    control_id: str,
    indexed: Mapping[tuple[str, str, str], Mapping[str, Any]],
    candidate_method: str,
    control_method: str,
) -> _LoadedCell:
    candidate = _load_report(
        source.candidate_report,
        "candidate MIDI report",
        schema=MELROFORMER_MIDI_SCHEMA,
        status="complete_observation_not_acceptance",
    )
    control = _load_report(
        source.control_comparison,
        "control MIDI comparison",
        schema=AUTHORISED_MIDI_COMPARISON_SCHEMA,
        status="complete_observation_not_acceptance",
    )
    mapping = _load_report(
        source.role_mapping,
        "authorised role mapping",
        schema=AUTHORISED_ROLE_MAPPING_SCHEMA,
        status="complete_review_required",
        document_hasher=_mapping_document_sha256,
    )
    excerpt = _load_report(
        source.authorised_excerpt,
        "authorised separation excerpt",
        schema=AUTHORISED_EXCERPT_SCHEMA,
        status="complete_review_required",
        document_hasher=_excerpt_document_sha256,
    )
    for loaded in (candidate, control, mapping, excerpt):
        _require_inactive(loaded.document)

    _require_index_entry(
        indexed,
        track_id=track_id,
        method_family=candidate_method,
        evidence_kind="vocal_midi",
        expected_file_sha256=candidate.file_sha256,
        expected_document_sha256=str(candidate.document["document_sha256"]),
    )
    _require_index_entry(
        indexed,
        track_id=track_id,
        method_family=control_method,
        evidence_kind="provider_midi",
    )
    source_track_id = _bind_source_chain(
        candidate=candidate,
        control=control,
        mapping=mapping,
        excerpt=excerpt,
    )

    bpm, tuning_hz = _validated_control_policy(control.document.get("policy"))
    candidate_policy = candidate.document.get("policy")
    if (
        not isinstance(candidate_policy, Mapping)
        or _number(candidate_policy.get("bpm"), "candidate BPM") != bpm
        or _number(candidate_policy.get("tuning_hz"), "candidate tuning")
        != tuning_hz
        or _number(candidate_policy.get("onset_tolerance_ms"), "candidate tolerance")
        != 40.0
        or candidate_policy.get("absolute_ground_truth_claimed") is not False
        or candidate_policy.get("winner_selected") is not False
    ):
        raise ValueError("candidate MIDI comparison policy differs")

    controls = _load_control_notes(control.path.parent, control.document)
    if control_id not in controls:
        raise ValueError(f"control ID is not present in authorised MIDI evidence: {control_id}")
    control_notes = controls[control_id]
    _control_note_path(control, control_id)
    candidate_notes, _ = _candidate_notes(candidate)
    metrics = _compare_note_events(
        control_notes,
        candidate_notes,
        tolerance_seconds=0.040,
    )
    sealed = candidate.document.get("comparisons_to_existing_controls", {}).get(
        control_id
    )
    if (
        not isinstance(sealed, Mapping)
        or sealed.get("control_note_count") != len(control_notes)
        or sealed.get("candidate_note_count") != len(candidate_notes)
        or sealed.get("comparison") != metrics
        or sealed.get("reference_semantics")
        != "control MIDI is a relative comparison baseline, not score truth"
    ):
        raise ValueError("sealed candidate/control MIDI comparison differs")
    return _LoadedCell(
        track_id=track_id,
        source_track_id=source_track_id,
        candidate=candidate,
        control=control,
        mapping=mapping,
        excerpt=excerpt,
        metrics=metrics,
        control_note_count=len(control_notes),
        candidate_note_count=len(candidate_notes),
    )


def _bind_source_chain(
    *,
    candidate: _LoadedJson,
    control: _LoadedJson,
    mapping: _LoadedJson,
    excerpt: _LoadedJson,
) -> str:
    mapping_source = mapping.document.get("source_excerpt")
    control_mapping = control.document.get("source_role_mapping")
    candidate_worker = candidate.document.get("worker")
    candidate_controls = candidate.document.get("controls")
    if (
        not isinstance(mapping_source, Mapping)
        or mapping_source.get("report_sha256") != excerpt.file_sha256
        or mapping_source.get("document_sha256")
        != excerpt.document.get("document_sha256")
        or not isinstance(control_mapping, Mapping)
        or control_mapping.get("report_sha256") != mapping.file_sha256
        or control_mapping.get("document_sha256")
        != mapping.document.get("document_sha256")
        or not isinstance(candidate_worker, Mapping)
        or candidate_worker.get("authorisation_report_sha256")
        != excerpt.file_sha256
        or not isinstance(candidate_controls, Mapping)
        or candidate_controls.get("comparison_sha256") != control.file_sha256
        or candidate_controls.get("document_sha256")
        != control.document.get("document_sha256")
    ):
        raise ValueError("candidate and control are not bound to one authorised excerpt")
    excerpt_geometry = excerpt.document.get("excerpt")
    if not isinstance(excerpt_geometry, Mapping):
        raise ValueError("authorised excerpt geometry differs")
    if (
        _number(mapping_source.get("start_seconds"), "role-mapping start")
        != _number(excerpt_geometry.get("start_seconds"), "excerpt start")
        or _number(mapping_source.get("end_seconds"), "role-mapping end")
        != _number(excerpt_geometry.get("end_seconds"), "excerpt end")
    ):
        raise ValueError("authorised excerpt window identity differs")
    return _safe_id(mapping_source.get("track_id"), "source track ID")


def _candidate_notes(candidate: _LoadedJson) -> tuple[tuple[NoteEvent, ...], Path]:
    try:
        raw = candidate.document["candidate"]["primary"]["notes"]
    except (KeyError, TypeError) as error:
        raise ValueError("candidate primary note evidence is missing") from error
    path = _artifact_path(candidate.path.parent, raw, "candidate primary note evidence")
    payload = _read_json(path, "candidate primary note evidence")
    if (
        payload.get("schema") != "sunofriend.private-authorised-midi-note-evidence.v1"
        or payload.get("role") != "vocals"
        or payload.get("candidate") != "primary"
        or not isinstance(payload.get("notes"), list)
    ):
        raise ValueError("candidate primary note evidence differs")
    return _notes(payload["notes"]), path


def _control_note_path(control: _LoadedJson, control_id: str) -> Path:
    try:
        raw = control.document["packs"][control_id]["vocals"]["primary"]["notes"]
    except (KeyError, TypeError) as error:
        raise ValueError("control primary note evidence is missing") from error
    return _artifact_path(control.path.parent, raw, "control primary note evidence")


def _notes(raw_notes: Sequence[Mapping[str, Any]]) -> tuple[NoteEvent, ...]:
    try:
        notes = tuple(
            NoteEvent(
                start=float(note["start_seconds"]),
                end=float(note["end_seconds"]),
                pitch=int(note["pitch"]),
                velocity=int(note["velocity"]),
            )
            for note in raw_notes
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("MIDI note evidence differs") from error
    return _validated_notes(notes)


def _load_report(
    value: str | Path,
    label: str,
    *,
    schema: str,
    status: str,
    document_hasher: Any = _document_sha256,
) -> _LoadedJson:
    path = _regular_json(value, label)
    if path.stat().st_size > _MAXIMUM_REPORT_BYTES:
        raise ValueError(f"{label} is too large")
    document = _read_json(path, label)
    if (
        document.get("schema") != schema
        or document.get("status") != status
        or document.get("evidence_scope") != "private_development_only"
        or document.get("document_sha256") != document_hasher(document)
    ):
        raise ValueError(f"{label} contract differs")
    return _LoadedJson(path, _sha256(path), document)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _require_inactive(document: Mapping[str, Any]) -> None:
    permissions = document.get("permissions")
    if (
        not isinstance(permissions, Mapping)
        or not permissions
        or any(value is not False for value in permissions.values())
    ):
        raise ValueError("private source report grants a permission")


def _indexed_cells(
    index: Mapping[str, Any],
) -> dict[tuple[str, str, str], Mapping[str, Any]]:
    return {
        (
            str(entry["track_id"]),
            str(entry["method_family"]),
            str(entry["evidence_kind"]),
        ): entry
        for entry in index["entries"]
    }


def _require_index_entry(
    indexed: Mapping[tuple[str, str, str], Mapping[str, Any]],
    *,
    track_id: str,
    method_family: str,
    evidence_kind: str,
    expected_file_sha256: str | None = None,
    expected_document_sha256: str | None = None,
) -> None:
    entry = indexed.get((track_id, method_family, evidence_kind))
    if entry is None:
        raise ValueError("normalized MIDI agreement source is absent from the index")
    if expected_file_sha256 is not None and (
        entry.get("report_sha256") != expected_file_sha256
        or entry.get("report_document_sha256") != expected_document_sha256
    ):
        raise ValueError("indexed candidate report identity differs")


def _build_document(
    *,
    index: Mapping[str, Any],
    index_file_sha256: str,
    cells: Sequence[_LoadedCell],
    candidate_method: str,
    control_method: str,
    control_id: str,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": "complete_pairwise_agreement_not_quality_or_acceptance",
        "evidence_scope": "private_development_only",
        "inputs": {
            "evidence_index_sha256": index_file_sha256,
            "evidence_index_document_sha256": index["document_sha256"],
            "candidate_method_family": candidate_method,
            "control_method_family": control_method,
            "control_id": control_id,
        },
        "comparison_contract": {
            "metric_schema": _METRIC_SCHEMA,
            "reference": "authorised provider-control vocal MIDI",
            "estimate": "candidate separated-vocal MIDI",
            "onset_tolerance_ms": 40.0,
            "same_note_comparator_used_for_every_song": True,
            "metrics_recomputed_from_sealed_note_evidence": True,
            "recomputed_metrics_equal_sealed_candidate_comparisons": True,
            "same_authorised_excerpt_proved_for_each_pair": True,
            "pairwise_agreement_comparison_permitted": True,
            "quality_comparison_permitted": False,
            "method_ranking_permitted": False,
        },
        "cells": [
            {
                "track_id": cell.track_id,
                "source_track_id": cell.source_track_id,
                "source_binding": {
                    "authorised_excerpt_sha256": cell.excerpt.file_sha256,
                    "authorised_excerpt_document_sha256": cell.excerpt.document[
                        "document_sha256"
                    ],
                    "role_mapping_sha256": cell.mapping.file_sha256,
                    "role_mapping_document_sha256": cell.mapping.document[
                        "document_sha256"
                    ],
                    "control_comparison_sha256": cell.control.file_sha256,
                    "control_comparison_document_sha256": cell.control.document[
                        "document_sha256"
                    ],
                    "candidate_report_sha256": cell.candidate.file_sha256,
                    "candidate_report_document_sha256": cell.candidate.document[
                        "document_sha256"
                    ],
                    "same_authorised_excerpt": True,
                },
                "control_note_count": cell.control_note_count,
                "candidate_note_count": cell.candidate_note_count,
                "agreement": cell.metrics,
                "interpretation": (
                    "pairwise note agreement against an estimated provider control; "
                    "not score truth, melody accuracy or listening preference"
                ),
            }
            for cell in cells
        ],
        "observations": {
            "song_count": len(cells),
            "same_method_pair_repeated_across_songs": len(cells) >= 2,
            "all_metric_schemas_identical": all(
                cell.metrics.get("schema") == _METRIC_SCHEMA for cell in cells
            ),
            "aggregate_quality_score_computed": False,
            "winner_selected": False,
        },
        "publication_gate": {
            "status": "open",
            "cross_method_quality_comparison_ready": False,
            "unresolved_or_out_of_scope": [
                "provider_control_is_not_score_ground_truth",
                "human_line_identity_and_listening_not_normalized",
                "hidden_test_set_not_represented",
                "checkpoint_licensing_not_evaluated",
                "offline_and_resource_acceptance_not_evaluated",
            ],
        },
        "policy": {
            "identifiers_are_caller_declared": True,
            "source_track_ids_are_preserved_separately_from_index_aliases": True,
            "indexed_provider_report_is_not_the_metric_source": True,
            "normalized_pairwise_agreement_only": True,
            "absolute_ground_truth_claimed": False,
            "method_ranked_or_selected": False,
            "cross_song_acceptance_evaluated": False,
            "automatic_selection": False,
            "automatic_promotion": False,
            "production_eligible": False,
            "public_result": False,
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
            "audio_created_or_mutated": False,
            "candidate_activated": False,
            "default_changed": False,
            "midi_created_or_mutated": False,
            "source_graph_mutated": False,
        },
        "limitations": [
            "Agreement with one estimated provider control is not transcription accuracy or musical quality.",
            "The provider-reference index cell establishes catalogue topology; the exact metric source is the separately source-bound authorised control report.",
            "Direction-sensitive precision, recall and signed timing drift retain control-as-reference semantics.",
            "No aggregate score is computed because it could conceal different failure modes between songs.",
            "No audio, MIDI, source path, report path or listening decision is copied into this report.",
        ],
    }


def _reverify(
    index_path: Path,
    index_sha256: str,
    cells: Sequence[_LoadedCell],
    *,
    control_id: str,
) -> None:
    if _sha256(index_path) != index_sha256:
        raise ValueError("private separation evidence index changed during normalization")
    for cell in cells:
        for loaded in (cell.candidate, cell.control, cell.mapping, cell.excerpt):
            if _sha256(loaded.path) != loaded.file_sha256:
                raise ValueError("private source report changed during normalization")
        _artifact_path(
            cell.candidate.path.parent,
            cell.candidate.document["candidate"]["primary"]["notes"],
            "candidate primary note evidence",
        )
        _control_note_path(cell.control, control_id)


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or _ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase ASCII token")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return float(value)


__all__ = [
    "MidiAgreementInput",
    "SCHEMA",
    "_normalize_private_separation_midi_agreement",
]
