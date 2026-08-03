"""Human-listening coverage over source-bound private separation evidence.

This owner-only projection binds completed, focus-relative vocal reviews to
the exact authorised excerpts already present in a normalized MIDI-agreement
report.  It records coverage and reviewed outcomes without converting a human
choice into accuracy, ranking, selection or publication acceptance.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from ._separation_authorised_midi_comparison import (
    _document_sha256,
    _regular_json,
    _sha256,
)
from ._separation_cross_song_evidence_index import _ID_PATTERN
from ._separation_normalized_midi_agreement import (
    SCHEMA as NORMALIZED_AGREEMENT_SCHEMA,
)
from ._separation_vocal_candidate_audition import (
    _FOCUS_PHRASE_COVERAGE,
    RESOLUTION_SCHEMA,
    _write_fresh_private_json,
)


SCHEMA = "sunofriend.private-separation-human-listening-coverage.v1"
_MAXIMUM_REPORT_BYTES = 2 * 1024 * 1024
_MAXIMUM_REVIEWS = 64
_REFERENCE_RELATIONSHIPS = frozenset(
    ("focus_line", "different_line", "mixed_or_overlapping_lines", "cannot_tell")
)


@dataclass(frozen=True)
class HumanListeningInput:
    """One completed review attached to a caller-declared track alias."""

    track_id: str
    review_resolution: Path


@dataclass(frozen=True)
class _LoadedJson:
    path: Path
    file_sha256: str
    document: dict[str, Any]


@dataclass(frozen=True)
class _BoundReview:
    track_id: str
    source_track_id: str
    review: _LoadedJson


def _project_private_separation_human_listening_coverage(
    normalized_agreement_path: str | Path,
    reviews: Sequence[HumanListeningInput],
    *,
    out: str | Path,
) -> dict[str, Any]:
    """Bind completed line/usefulness reviews to normalized song evidence."""

    if not 1 <= len(reviews) <= _MAXIMUM_REVIEWS:
        raise ValueError("human listening coverage requires 1-64 reviews")
    agreement = _load_agreement(normalized_agreement_path)
    agreement_cells = _agreement_cells(agreement.document)

    loaded = tuple(
        _bind_review(
            source,
            track_id=_safe_id(source.track_id, "track ID"),
            agreement_cells=agreement_cells,
        )
        for source in reviews
    )
    if len({item.review.file_sha256 for item in loaded}) != len(loaded):
        raise ValueError("human listening coverage duplicates a review report")
    windows = {
        (
            item.track_id,
            float(item.review.document["scope"]["start_seconds"]),
            float(item.review.document["scope"]["end_seconds"]),
            str(item.review.document["focus"]),
        )
        for item in loaded
    }
    if len(windows) != len(loaded):
        raise ValueError("human listening coverage duplicates a review window")

    ordered = tuple(
        sorted(
            loaded,
            key=lambda item: (
                item.track_id,
                float(item.review.document["scope"]["start_seconds"]),
                float(item.review.document["scope"]["end_seconds"]),
                item.review.file_sha256,
            ),
        )
    )
    document = _build_document(agreement=agreement, reviews=ordered)
    document["document_sha256"] = _document_sha256(document)
    _reverify(agreement, ordered)
    _write_fresh_private_json(Path(out), document)
    document["report"] = str(Path(out).expanduser().absolute())
    return document


def _load_agreement(path: str | Path) -> _LoadedJson:
    loaded = _load_json(path, "normalized MIDI agreement")
    document = loaded.document
    if (
        document.get("schema") != NORMALIZED_AGREEMENT_SCHEMA
        or document.get("status")
        != "complete_pairwise_agreement_not_quality_or_acceptance"
        or document.get("evidence_scope") != "private_development_only"
        or document.get("document_sha256") != _document_sha256(document)
    ):
        raise ValueError("normalized MIDI agreement contract differs")
    _require_all_false(document.get("permissions"), "agreement permissions")
    _require_all_false(document.get("effects"), "agreement effects")
    contract = document.get("comparison_contract")
    gate = document.get("publication_gate")
    if (
        not isinstance(contract, Mapping)
        or contract.get("quality_comparison_permitted") is not False
        or contract.get("method_ranking_permitted") is not False
        or not isinstance(gate, Mapping)
        or gate.get("status") != "open"
    ):
        raise ValueError("normalized MIDI agreement safety policy differs")
    return loaded


def _agreement_cells(
    agreement: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    rows = agreement.get("cells")
    if not isinstance(rows, list) or len(rows) < 2:
        raise ValueError("normalized MIDI agreement cells differ")
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("normalized MIDI agreement cell differs")
        track_id = _safe_id(row.get("track_id"), "agreement track ID")
        _safe_id(row.get("source_track_id"), "source track ID")
        binding = row.get("source_binding")
        if (
            track_id in result
            or not isinstance(binding, Mapping)
            or binding.get("same_authorised_excerpt") is not True
            or not _sha256_value(binding.get("authorised_excerpt_sha256"))
            or not _sha256_value(binding.get("authorised_excerpt_document_sha256"))
        ):
            raise ValueError("normalized MIDI agreement source binding differs")
        result[track_id] = row
    return result


def _bind_review(
    source: HumanListeningInput,
    *,
    track_id: str,
    agreement_cells: Mapping[str, Mapping[str, Any]],
) -> _BoundReview:
    cell = agreement_cells.get(track_id)
    if cell is None:
        raise ValueError("human review track is absent from normalized agreement")
    review = _load_review(source.review_resolution)
    binding = cell["source_binding"]
    inputs = review.document["inputs"]
    if inputs.get("authorised_excerpt_sha256") != binding.get(
        "authorised_excerpt_sha256"
    ) or inputs.get("authorised_excerpt_document_sha256") != binding.get(
        "authorised_excerpt_document_sha256"
    ):
        raise ValueError("human review is not bound to the normalized song excerpt")
    return _BoundReview(
        track_id=track_id,
        source_track_id=str(cell["source_track_id"]),
        review=review,
    )


def _load_review(path: str | Path) -> _LoadedJson:
    loaded = _load_json(path, "human vocal review resolution")
    document = loaded.document
    if (
        document.get("schema") != RESOLUTION_SCHEMA
        or document.get("status") != "complete_review_no_activation"
        or document.get("evidence_scope") != "private_development_only"
        or document.get("document_sha256") != _document_sha256(document)
    ):
        raise ValueError("human vocal review resolution contract differs")
    policy = document.get("policy")
    required_policy = {
        "human_dispositions_verified": True,
        "human_reference_line_relationships_verified": True,
        "winner_selected": False,
        "automatic_selection": False,
        "automatic_merge": False,
        "automatic_repair": False,
        "singer_identity_inferred": False,
        "production_eligible": False,
    }
    if not isinstance(policy, Mapping) or any(
        policy.get(key) is not value for key, value in required_policy.items()
    ):
        raise ValueError("human vocal review resolution policy differs")
    coverage_policy = policy.get("human_focus_phrase_coverage_verified")
    if coverage_policy not in (None, False, True):
        raise ValueError("human vocal review phrase-coverage policy differs")
    _require_all_false(document.get("effects"), "review effects")
    _validate_review_inputs(document.get("inputs"))
    _validate_review_focus(document.get("focus"))
    candidate_ids = _validate_review_scope(document.get("scope"))
    _validate_review_results(
        document.get("results"),
        candidate_ids,
        focus_phrase_coverage_required=coverage_policy is True,
    )
    return loaded


def _validate_review_inputs(raw: Any) -> None:
    required = (
        "review_sha256",
        "review_seed_document_sha256",
        "candidate_set_sha256",
        "candidate_set_document_sha256",
        "authorised_excerpt_sha256",
        "authorised_excerpt_document_sha256",
    )
    if not isinstance(raw, Mapping) or any(
        not _sha256_value(raw.get(key)) for key in required
    ):
        raise ValueError("human vocal review resolution inputs differ")


def _validate_review_focus(raw: Any) -> None:
    if (
        not isinstance(raw, str)
        or not raw.strip()
        or raw != raw.strip()
        or len(raw) > 180
        or "\n" in raw
        or "\r" in raw
        or "\x00" in raw
    ):
        raise ValueError("human vocal review focus differs")


def _validate_review_scope(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, Mapping):
        raise ValueError("human vocal review scope differs")
    candidate_ids = raw.get("candidate_ids")
    if (
        not isinstance(candidate_ids, list)
        or not candidate_ids
        or len(candidate_ids) != len(set(candidate_ids))
        or not all(isinstance(value, str) and value for value in candidate_ids)
        or raw.get("candidate_count") != len(candidate_ids)
        or raw.get("candidate_order") != "sealed_inventory_order_not_rank"
        or raw.get("time_window_source") != "explicit"
    ):
        raise ValueError("human vocal review scope differs")
    start = _finite_number(raw.get("start_seconds"), "review start")
    end = _finite_number(raw.get("end_seconds"), "review end")
    duration = _finite_number(raw.get("duration_seconds"), "review duration")
    inventory_count = raw.get("inventory_candidate_count")
    omitted_count = raw.get("omitted_candidate_count")
    if (
        start < 0.0
        or end <= start
        or not math.isclose(duration, end - start, abs_tol=1e-9)
        or isinstance(inventory_count, bool)
        or not isinstance(inventory_count, int)
        or inventory_count < len(candidate_ids)
        or isinstance(omitted_count, bool)
        or not isinstance(omitted_count, int)
        or omitted_count != inventory_count - len(candidate_ids)
    ):
        raise ValueError("human vocal review scope geometry differs")
    return tuple(candidate_ids)


def _validate_review_results(
    raw: Any,
    candidate_ids: Sequence[str],
    *,
    focus_phrase_coverage_required: bool,
) -> None:
    if not isinstance(raw, Mapping):
        raise ValueError("human vocal review results differ")
    dispositions = []
    for key in ("useful_for_focus", "not_useful_for_focus", "cannot_tell"):
        values = raw.get(key)
        if (
            not isinstance(values, list)
            or len(values) != len(set(values))
            or not all(isinstance(value, str) and value for value in values)
            or raw.get(f"{key}_count") != len(values)
        ):
            raise ValueError("human vocal review disposition results differ")
        dispositions.extend(values)
    if sorted(dispositions) != sorted(candidate_ids):
        raise ValueError("human vocal review dispositions do not partition scope")

    relationships = raw.get("reference_relationships")
    if (
        not isinstance(relationships, Mapping)
        or frozenset(relationships) != _REFERENCE_RELATIONSHIPS
    ):
        raise ValueError("human vocal review reference relationships differ")
    classified = []
    for key in sorted(_REFERENCE_RELATIONSHIPS):
        values = relationships[key]
        if (
            not isinstance(values, list)
            or len(values) != len(set(values))
            or not all(isinstance(value, str) and value for value in values)
        ):
            raise ValueError("human vocal review reference relationships differ")
        classified.extend(values)
    if sorted(classified) != sorted(candidate_ids):
        raise ValueError("human vocal review relationships do not partition scope")

    coverage = raw.get("focus_phrase_coverage")
    if coverage is None and not focus_phrase_coverage_required:
        return
    if (
        not isinstance(coverage, Mapping)
        or frozenset(coverage) != _FOCUS_PHRASE_COVERAGE
    ):
        raise ValueError("human vocal review focus-phrase coverage differs")
    covered = []
    for key in sorted(_FOCUS_PHRASE_COVERAGE):
        values = coverage[key]
        if (
            not isinstance(values, list)
            or len(values) != len(set(values))
            or not all(isinstance(value, str) and value for value in values)
        ):
            raise ValueError("human vocal review focus-phrase coverage differs")
        covered.extend(values)
    expected = sorted(candidate_ids) if focus_phrase_coverage_required else []
    if sorted(covered) != expected:
        raise ValueError(
            "human vocal review focus-phrase coverage does not match policy"
        )


def _build_document(
    *,
    agreement: _LoadedJson,
    reviews: Sequence[_BoundReview],
) -> dict[str, Any]:
    agreement_track_ids = {
        str(cell["track_id"]) for cell in agreement.document["cells"]
    }
    reviewed_track_ids = {item.track_id for item in reviews}
    reviewed_candidate_count = sum(
        int(item.review.document["scope"]["candidate_count"]) for item in reviews
    )
    useful_count = sum(
        int(item.review.document["results"]["useful_for_focus_count"])
        for item in reviews
    )
    structured_coverage_count = sum(
        item.review.document["policy"].get("human_focus_phrase_coverage_verified")
        is True
        for item in reviews
    )
    unresolved = [
        "full_excerpt_or_full_song_listening_coverage_not_proved",
        "human_usefulness_is_not_accuracy_or_score_truth",
        "provider_control_is_not_score_ground_truth",
        "hidden_test_set_not_represented",
        "checkpoint_licensing_not_evaluated",
        "offline_and_resource_acceptance_not_evaluated",
    ]
    if reviewed_track_ids != agreement_track_ids:
        unresolved.insert(0, "cross_song_human_listening_coverage_incomplete")
    if structured_coverage_count != len(reviews):
        unresolved.insert(
            1, "transcription_completeness_not_structured_for_every_window"
        )
    return {
        "schema": SCHEMA,
        "status": "complete_human_listening_projection_not_acceptance",
        "evidence_scope": "private_development_only",
        "inputs": {
            "normalized_midi_agreement_sha256": agreement.file_sha256,
            "normalized_midi_agreement_document_sha256": agreement.document[
                "document_sha256"
            ],
        },
        "review_windows": [_review_window(item) for item in reviews],
        "coverage": {
            "agreement_track_count": len(agreement_track_ids),
            "reviewed_track_count": len(reviewed_track_ids),
            "review_window_count": len(reviews),
            "reviewed_candidate_count": reviewed_candidate_count,
            "useful_for_focus_count": useful_count,
            "structured_focus_phrase_coverage_window_count": (
                structured_coverage_count
            ),
            "all_reviews_classify_reference_line_for_written_focus": True,
            "all_reviews_record_candidate_usefulness_separately": True,
            "all_reviews_record_focus_phrase_coverage": (
                structured_coverage_count == len(reviews)
            ),
            "all_reviewed_tracks_are_bound_to_normalized_excerpt": True,
            "cross_song_review_coverage_complete": (
                reviewed_track_ids == agreement_track_ids
            ),
        },
        "interpretation": {
            "line_identity_and_listening_are_projected_for_observed_windows": True,
            "reference_relationships_are_focus_relative": True,
            "useful_candidate_is_winner": False,
            "useful_candidate_is_complete_transcription": False,
            "human_result_is_accuracy_score": False,
            "focus_phrase_coverage_is_note_recall": False,
            "agreement_is_ground_truth": False,
        },
        "publication_gate": {
            "status": "open",
            "cross_method_quality_comparison_ready": False,
            "unresolved_or_out_of_scope": unresolved,
        },
        "policy": {
            "review_source": "completed_human_focus_relative_resolution",
            "identifiers_are_caller_declared": True,
            "source_report_files_hash_verified": True,
            "source_reports_self_hash_verified": True,
            "review_notes_copied": False,
            "candidate_ranked_or_selected": False,
            "aggregate_quality_score_computed": False,
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
            "review_notes_copied": False,
            "source_graph_mutated": False,
        },
        "limitations": [
            "This projection covers only the explicit phrase windows and candidate subsets in the supplied completed reviews.",
            "A focus-line label identifies the requested musical role for one window; it does not identify a singer or prove note accuracy.",
            "Useful for focus is a human audition outcome, not a complete-transcription claim, quality score or method ranking.",
            "Free-text listener notes are deliberately not copied or interpreted, so missed-note completeness remains an explicit structured-evidence gap.",
            "No audio, MIDI, source path or report path is copied into this report.",
        ],
    }


def _review_window(item: _BoundReview) -> dict[str, Any]:
    review = item.review.document
    results = review["results"]
    coverage_verified = (
        review["policy"].get("human_focus_phrase_coverage_verified") is True
    )
    coverage = results.get("focus_phrase_coverage") or {
        key: [] for key in sorted(_FOCUS_PHRASE_COVERAGE)
    }
    return {
        "track_id": item.track_id,
        "source_track_id": item.source_track_id,
        "review_resolution_sha256": item.review.file_sha256,
        "review_resolution_document_sha256": review["document_sha256"],
        "authorised_excerpt_sha256": review["inputs"]["authorised_excerpt_sha256"],
        "authorised_excerpt_document_sha256": review["inputs"][
            "authorised_excerpt_document_sha256"
        ],
        "focus": review["focus"],
        "scope": dict(review["scope"]),
        "results": {
            "useful_for_focus_count": results["useful_for_focus_count"],
            "useful_for_focus": list(results["useful_for_focus"]),
            "not_useful_for_focus_count": results["not_useful_for_focus_count"],
            "not_useful_for_focus": list(results["not_useful_for_focus"]),
            "cannot_tell_count": results["cannot_tell_count"],
            "cannot_tell": list(results["cannot_tell"]),
            "reference_relationships": {
                key: list(results["reference_relationships"][key])
                for key in sorted(_REFERENCE_RELATIONSHIPS)
            },
            "focus_phrase_coverage_verified": coverage_verified,
            "focus_phrase_coverage": {
                key: list(coverage[key]) for key in sorted(_FOCUS_PHRASE_COVERAGE)
            },
        },
        "interpretation": (
            "completed focus-relative human evidence for this exact phrase; "
            "not a winner, completeness claim or global method judgement"
        ),
    }


def _load_json(value: str | Path, label: str) -> _LoadedJson:
    path = _regular_json(value, label)
    if path.stat().st_size > _MAXIMUM_REPORT_BYTES:
        raise ValueError(f"{label} is too large")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid JSON") from error
    if not isinstance(document, dict):
        raise ValueError(f"{label} must be a JSON object")
    return _LoadedJson(path=path, file_sha256=_sha256(path), document=document)


def _require_all_false(raw: Any, label: str) -> None:
    if (
        not isinstance(raw, Mapping)
        or not raw
        or any(value is not False for value in raw.values())
    ):
        raise ValueError(f"{label} differ")


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or _ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase ASCII token")
    return value


def _sha256_value(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _reverify(agreement: _LoadedJson, reviews: Sequence[_BoundReview]) -> None:
    if _sha256(agreement.path) != agreement.file_sha256:
        raise ValueError("normalized MIDI agreement changed during projection")
    for item in reviews:
        if _sha256(item.review.path) != item.review.file_sha256:
            raise ValueError("human vocal review changed during projection")


__all__ = [
    "HumanListeningInput",
    "SCHEMA",
    "_project_private_separation_human_listening_coverage",
]
