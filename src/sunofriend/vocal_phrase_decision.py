"""Human-only phrase decisions and non-rendering vocal source maps."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from .musical_state import MUSICAL_STATE_SCHEMA, validate_musical_state
from .source_receipt import document_sha256


VOCAL_PHRASE_DECISION_SCHEMA = "sunofriend.vocal-comp-phrase-decision.v1"
VOCAL_SOURCE_MAP_SCHEMA = "sunofriend.vocal-comp-source-map.v1"
VOCAL_RENDER_SOURCE_MAP_SCHEMA = "sunofriend.vocal-comp-source-map.v2"

PHRASE_OUTCOMES = frozenset(
    {
        "human_take",
        "ai_fallback",
        "record_again",
        "no_acceptable_candidate",
    }
)
_SOURCE_OUTCOMES = frozenset({"human_take", "ai_fallback"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def create_phrase_decision(
    musical_state: Mapping[str, Any],
    phrase_id: str,
    outcome: str,
    *,
    source_id: str | None = None,
    notes: str | None = None,
    reviewed_at: str | None = None,
    review_evidence_sha256: str | None = None,
) -> dict[str, Any]:
    """Create one explicit human decision without rendering or training labels."""

    state = validate_musical_state(musical_state)
    phrase = _phrase(state, phrase_id)
    if outcome not in PHRASE_OUTCOMES:
        raise ValueError("unsupported vocal phrase outcome")
    _require_reviewed_structure(state)
    selected_source = _selected_source(state, phrase_id, outcome, source_id)
    if not isinstance(notes, (str, type(None))):
        raise ValueError("decision notes must be text or null")
    if reviewed_at is not None and not str(reviewed_at).strip():
        raise ValueError("reviewed_at must be non-empty text or null")
    if review_evidence_sha256 is not None and not _SHA256.fullmatch(
        str(review_evidence_sha256)
    ):
        raise ValueError("review evidence must be a lowercase SHA-256")

    document: dict[str, Any] = {
        "schema": VOCAL_PHRASE_DECISION_SCHEMA,
        "status": "complete_human_decision",
        "method_natures": ["H"],
        "binding": {
            "musical_state_schema": MUSICAL_STATE_SCHEMA,
            "musical_state_sha256": state["document_sha256"],
        },
        "phrase": {
            "phrase_id": phrase["phrase_id"],
            "start_seconds": phrase["start_seconds"],
            "end_seconds": phrase["end_seconds"],
            "lyrics": phrase["lyrics"],
            "review_status": "reviewed",
        },
        "outcome": outcome,
        "selected_source_id": (
            selected_source["source_id"] if selected_source is not None else None
        ),
        "selected_source_class": (
            selected_source["source_class"] if selected_source is not None else None
        ),
        "selected_source_sha256": (
            selected_source["audio_sha256"] if selected_source is not None else None
        ),
        "review": {
            "authority": "explicit_human_review",
            "reviewed_at": reviewed_at,
            "evidence_sha256": review_evidence_sha256,
            "notes": notes,
        },
        "authority_limits": {
            "comp_render_authorized": False,
            "pitch_correction_authorized": False,
            "timing_correction_authorized": False,
            "word_level_splice_authorized": False,
        },
        "training": {
            "pairwise_labels": [],
            "inferred_labels": [],
            "training_eligible": False,
            "reason": "a phrase choice is not a complete pairwise comparison label",
        },
        "effects": _decision_effects(),
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return validate_phrase_decision(document, state)


def validate_phrase_decision(
    decision: Mapping[str, Any], musical_state: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate one phrase decision against the exact immutable state."""

    state = validate_musical_state(musical_state)
    document = dict(decision)
    _reject_private_or_path_fields(document)
    if set(document) != {
        "schema",
        "status",
        "method_natures",
        "binding",
        "phrase",
        "outcome",
        "selected_source_id",
        "selected_source_class",
        "selected_source_sha256",
        "review",
        "authority_limits",
        "training",
        "effects",
        "network_used",
        "document_sha256",
    }:
        raise ValueError("vocal phrase decision fields changed")
    if document.get("schema") != VOCAL_PHRASE_DECISION_SCHEMA:
        raise ValueError("unsupported vocal phrase decision schema")
    if document.get("status") != "complete_human_decision":
        raise ValueError("vocal phrase decision must be a complete human decision")
    _verify_hash(document, "vocal phrase decision")
    _require_reviewed_structure(state)
    if document.get("method_natures") != ["H"]:
        raise ValueError("vocal phrase decision must declare human work")
    binding = _mapping(document.get("binding"), "binding")
    if binding != {
        "musical_state_schema": MUSICAL_STATE_SCHEMA,
        "musical_state_sha256": state["document_sha256"],
    }:
        raise ValueError("phrase decision does not bind this exact musical state")
    phrase_row = _mapping(document.get("phrase"), "phrase")
    phrase = _phrase(state, str(phrase_row.get("phrase_id", "")))
    expected_phrase = {
        "phrase_id": phrase["phrase_id"],
        "start_seconds": phrase["start_seconds"],
        "end_seconds": phrase["end_seconds"],
        "lyrics": phrase["lyrics"],
        "review_status": "reviewed",
    }
    if phrase_row != expected_phrase:
        raise ValueError("phrase decision geometry or lyrics changed")
    outcome = document.get("outcome")
    if outcome not in PHRASE_OUTCOMES:
        raise ValueError("unsupported vocal phrase outcome")
    expected_source = _selected_source(
        state,
        phrase["phrase_id"],
        str(outcome),
        str(document.get("selected_source_id"))
        if outcome == "human_take" and document.get("selected_source_id") is not None
        else None,
    )
    expected_identity = (
        (
            expected_source["source_id"],
            expected_source["source_class"],
            expected_source["audio_sha256"],
        )
        if expected_source is not None
        else (None, None, None)
    )
    actual_identity = (
        document.get("selected_source_id"),
        document.get("selected_source_class"),
        document.get("selected_source_sha256"),
    )
    if actual_identity != expected_identity:
        raise ValueError(
            "phrase decision source SHA-256 or identity does not match state"
        )
    review = _mapping(document.get("review"), "review")
    if set(review) != {"authority", "reviewed_at", "evidence_sha256", "notes"}:
        raise ValueError("vocal phrase decision review fields changed")
    if review.get("authority") != "explicit_human_review":
        raise ValueError("phrase decision lacks explicit human authority")
    if not isinstance(review.get("notes"), (str, type(None))):
        raise ValueError("decision notes must be text or null")
    reviewed_at = review.get("reviewed_at")
    if reviewed_at is not None and not str(reviewed_at).strip():
        raise ValueError("reviewed_at must be non-empty text or null")
    evidence_sha = review.get("evidence_sha256")
    if evidence_sha is not None and not _SHA256.fullmatch(str(evidence_sha)):
        raise ValueError("review evidence must be a lowercase SHA-256")
    if document.get("authority_limits") != {
        "comp_render_authorized": False,
        "pitch_correction_authorized": False,
        "timing_correction_authorized": False,
        "word_level_splice_authorized": False,
    }:
        raise ValueError("phrase decision authority is missing or excessive")
    if document.get("training") != {
        "pairwise_labels": [],
        "inferred_labels": [],
        "training_eligible": False,
        "reason": "a phrase choice is not a complete pairwise comparison label",
    }:
        raise ValueError("phrase decision cannot create pairwise training labels")
    if document.get("effects") != _decision_effects():
        raise ValueError("phrase decision cannot render, correct, join or train")
    if document.get("network_used") is not False:
        raise ValueError("phrase decision must record network_used=false")
    _reject_private_or_path_fields(document)
    return document


def create_vocal_render_source_map(
    musical_state: Mapping[str, Any],
    decisions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Create a render-safe v2 map with embedded canonical decisions."""

    state = validate_musical_state(musical_state)
    validated = [validate_phrase_decision(item, state) for item in decisions]
    legacy = create_vocal_source_map(state, validated)
    document = dict(legacy)
    document.pop("document_sha256", None)
    document["schema"] = VOCAL_RENDER_SOURCE_MAP_SCHEMA
    document["embedded_decisions"] = validated
    document["render_projection"] = "exact_reprojection_from_embedded_decisions"
    document["document_sha256"] = document_sha256(document)
    return validate_vocal_render_source_map(document, state)


def validate_vocal_render_source_map(
    source_map: Mapping[str, Any], musical_state: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate v2 by reprojecting every source row from full decisions."""

    state = validate_musical_state(musical_state)
    document = dict(source_map)
    _verify_hash(document, "vocal render source map")
    expected_keys = {
        "schema",
        "status",
        "method_natures",
        "binding",
        "segments",
        "unresolved_phrases",
        "undecided_phrase_ids",
        "coverage",
        "authority",
        "training",
        "effects",
        "network_used",
        "embedded_decisions",
        "render_projection",
        "document_sha256",
    }
    if set(document) != expected_keys:
        raise ValueError("vocal render source map fields changed")
    if document.get("schema") != VOCAL_RENDER_SOURCE_MAP_SCHEMA:
        raise ValueError("unsupported vocal render source map schema")
    embedded = document.get("embedded_decisions")
    if not isinstance(embedded, list):
        raise ValueError("vocal render source map requires embedded decisions")
    validated = [validate_phrase_decision(item, state) for item in embedded]
    legacy = create_vocal_source_map(state, validated)
    expected = dict(legacy)
    expected.pop("document_sha256", None)
    expected["schema"] = VOCAL_RENDER_SOURCE_MAP_SCHEMA
    expected["embedded_decisions"] = validated
    expected["render_projection"] = "exact_reprojection_from_embedded_decisions"
    expected["document_sha256"] = document_sha256(expected)
    if document != expected:
        raise ValueError("vocal render source map is not the exact decision projection")
    return document


def create_vocal_source_map(
    musical_state: Mapping[str, Any],
    decisions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Reduce explicit decisions into a partial, non-rendering source map."""

    state = validate_musical_state(musical_state)
    _require_reviewed_structure(state)
    validated = [validate_phrase_decision(item, state) for item in decisions]
    decision_by_phrase: dict[str, dict[str, Any]] = {}
    for decision in validated:
        phrase_id = decision["phrase"]["phrase_id"]
        if phrase_id in decision_by_phrase:
            raise ValueError(
                "vocal source map cannot contain duplicate phrase decisions"
            )
        decision_by_phrase[phrase_id] = decision
    phrase_ids = [row["phrase_id"] for row in state["structure"]["phrases"]]
    undecided = [
        phrase_id for phrase_id in phrase_ids if phrase_id not in decision_by_phrase
    ]

    segments: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for phrase in state["structure"]["phrases"]:
        phrase_id = phrase["phrase_id"]
        decision = decision_by_phrase.get(phrase_id)
        if decision is None:
            continue
        if decision["outcome"] in _SOURCE_OUTCOMES:
            segment = {
                "phrase_id": phrase_id,
                "decision_document_sha256": decision["document_sha256"],
                "outcome": decision["outcome"],
                "destination_start_seconds": phrase["start_seconds"],
                "destination_end_seconds": phrase["end_seconds"],
                "source_id": decision["selected_source_id"],
                "source_class": decision["selected_source_class"],
                "source_audio_sha256": decision["selected_source_sha256"],
                **_source_geometry(
                    state,
                    phrase_id,
                    str(decision["selected_source_id"]),
                ),
                "join_status": "not_reviewed",
                "correction_status": "off",
            }
            segments.append(segment)
        else:
            unresolved.append(
                {
                    "phrase_id": phrase_id,
                    "decision_document_sha256": decision["document_sha256"],
                    "outcome": decision["outcome"],
                }
            )
    document: dict[str, Any] = {
        "schema": VOCAL_SOURCE_MAP_SCHEMA,
        "status": (
            "complete_unrendered"
            if not unresolved and not undecided
            else "partial_unrendered"
        ),
        "method_natures": ["D", "H"],
        "binding": {
            "musical_state_schema": MUSICAL_STATE_SCHEMA,
            "musical_state_sha256": state["document_sha256"],
        },
        "segments": segments,
        "unresolved_phrases": unresolved,
        "undecided_phrase_ids": undecided,
        "coverage": {
            "phrase_count": len(state["structure"]["phrases"]),
            "decision_count": len(validated),
            "source_segment_count": len(segments),
            "unresolved_count": len(unresolved),
            "undecided_count": len(undecided),
        },
        "authority": {
            "human_decisions_only": True,
            "automatic_fill": False,
            "join_review_complete": False,
            "audio_render_authorised": False,
            "correction_authorised": False,
        },
        "training": {
            "pairwise_labels": [],
            "inferred_labels": [],
            "training_eligible": False,
        },
        "effects": _source_map_effects(),
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return validate_vocal_source_map(document, state)


def validate_vocal_source_map(
    source_map: Mapping[str, Any], musical_state: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate a partial source map without granting render or join authority."""

    state = validate_musical_state(musical_state)
    document = dict(source_map)
    if document.get("schema") != VOCAL_SOURCE_MAP_SCHEMA:
        raise ValueError("unsupported vocal source map schema")
    _verify_hash(document, "vocal source map")
    _require_reviewed_structure(state)
    if document.get("method_natures") != ["D", "H"]:
        raise ValueError("vocal source map must declare deterministic and human work")
    binding = _mapping(document.get("binding"), "binding")
    if binding != {
        "musical_state_schema": MUSICAL_STATE_SCHEMA,
        "musical_state_sha256": state["document_sha256"],
    }:
        raise ValueError("vocal source map does not bind this exact musical state")
    phrases = {row["phrase_id"]: row for row in state["structure"]["phrases"]}
    sources = _sources(state)
    segments = document.get("segments")
    if not isinstance(segments, list):
        raise ValueError("vocal source map segments must be a list")
    seen: set[str] = set()
    for segment in segments:
        row = _mapping(segment, "source segment")
        phrase_id = str(row.get("phrase_id", ""))
        if phrase_id not in phrases or phrase_id in seen:
            raise ValueError("source segment phrase is unknown or duplicated")
        outcome = row.get("outcome")
        if outcome not in _SOURCE_OUTCOMES:
            raise ValueError("source segment outcome cannot be unresolved")
        source_id = str(row.get("source_id", ""))
        if source_id not in sources:
            raise ValueError("source segment source is not in musical state")
        phrase = phrases[phrase_id]
        source = sources[source_id]
        expected = {
            "phrase_id": phrase_id,
            "decision_document_sha256": row.get("decision_document_sha256"),
            "outcome": outcome,
            "destination_start_seconds": phrase["start_seconds"],
            "destination_end_seconds": phrase["end_seconds"],
            "source_id": source_id,
            "source_class": source["source_class"],
            "source_audio_sha256": source["audio_sha256"],
            **_source_geometry(state, phrase_id, source_id),
            "join_status": "not_reviewed",
            "correction_status": "off",
        }
        if not _SHA256.fullmatch(str(row.get("decision_document_sha256", ""))):
            raise ValueError("source segment decision hash is invalid")
        if row != expected:
            raise ValueError("source segment geometry or source identity changed")
        seen.add(phrase_id)
    unresolved = document.get("unresolved_phrases")
    if not isinstance(unresolved, list):
        raise ValueError("unresolved_phrases must be a list")
    unresolved_ids: set[str] = set()
    for row in unresolved:
        item = _mapping(row, "unresolved phrase")
        phrase_id = str(item.get("phrase_id", ""))
        if phrase_id not in phrases or phrase_id in seen or phrase_id in unresolved_ids:
            raise ValueError("unresolved phrase is unknown or duplicated")
        if item.get("outcome") not in PHRASE_OUTCOMES - _SOURCE_OUTCOMES:
            raise ValueError("unresolved phrase has a source-bearing outcome")
        if set(item) != {
            "phrase_id",
            "decision_document_sha256",
            "outcome",
        }:
            raise ValueError("unresolved phrase must not select a source")
        if not _SHA256.fullmatch(str(item.get("decision_document_sha256", ""))):
            raise ValueError("unresolved phrase decision hash is invalid")
        unresolved_ids.add(phrase_id)
    undecided = document.get("undecided_phrase_ids")
    if not isinstance(undecided, list) or any(
        item not in phrases for item in undecided
    ):
        raise ValueError("undecided phrase roster is invalid")
    if len(set(undecided)) != len(undecided):
        raise ValueError("undecided phrase roster contains duplicates")
    if set(undecided) & (seen | unresolved_ids):
        raise ValueError("a phrase cannot be both decided and undecided")
    if seen | unresolved_ids | set(undecided) != set(phrases):
        raise ValueError("vocal source map does not account for every phrase")
    coverage = _mapping(document.get("coverage"), "coverage")
    expected_coverage = {
        "phrase_count": len(phrases),
        "decision_count": len(seen) + len(unresolved_ids),
        "source_segment_count": len(seen),
        "unresolved_count": len(unresolved_ids),
        "undecided_count": len(undecided),
    }
    if coverage != expected_coverage:
        raise ValueError("vocal source map coverage summary changed")
    expected_status = (
        "complete_unrendered" if len(seen) == len(phrases) else "partial_unrendered"
    )
    if document.get("status") != expected_status:
        raise ValueError("vocal source map status does not match coverage")
    if document.get("authority") != {
        "human_decisions_only": True,
        "automatic_fill": False,
        "join_review_complete": False,
        "audio_render_authorised": False,
        "correction_authorised": False,
    }:
        raise ValueError("vocal source map authority is missing or excessive")
    if document.get("training") != {
        "pairwise_labels": [],
        "inferred_labels": [],
        "training_eligible": False,
    }:
        raise ValueError("vocal source map cannot create training labels")
    if document.get("effects") != _source_map_effects():
        raise ValueError("vocal source map effect declaration is unsupported")
    if document.get("network_used") is not False:
        raise ValueError("vocal source map must record network_used=false")
    _reject_private_or_path_fields(document)
    return document


def _selected_source(
    state: Mapping[str, Any],
    phrase_id: str,
    outcome: str,
    source_id: str | None,
) -> dict[str, Any] | None:
    vocal = state["vocal_performance_state"]
    if outcome == "human_take":
        if not source_id:
            raise ValueError("human_take requires source_id")
        for take in vocal["takes"]:
            if take["source_id"] == source_id:
                eligible = take.get("eligible_phrase_ids")
                if eligible is not None and phrase_id not in eligible:
                    raise ValueError("human take is bound to another phrase")
                return {
                    "source_id": source_id,
                    "source_class": "human_vocal_take",
                    "audio_sha256": take["audio"]["sha256"],
                }
        for capture in vocal.get("phrase_captures", []):
            if capture["source_id"] != source_id:
                continue
            if capture["phrase"]["phrase_id"] != phrase_id:
                raise ValueError("human phrase capture is bound to another phrase")
            return {
                "source_id": source_id,
                "source_class": "human_vocal_phrase_capture",
                "audio_sha256": capture["audio"]["sha256"],
            }
        reference = vocal.get("reference")
        if isinstance(reference, Mapping) and reference.get("source_id") == source_id:
            raise ValueError("human_take requires a human take source")
        raise ValueError("human_take source is unknown in musical state")
    if outcome == "ai_fallback":
        if source_id is not None:
            raise ValueError("ai_fallback source is determined by musical state")
        reference = vocal.get("reference")
        if not isinstance(reference, Mapping):
            raise ValueError("ai_fallback requires an admitted reference vocal")
        return {
            "source_id": reference["source_id"],
            "source_class": "reference_vocal",
            "audio_sha256": reference["audio"]["sha256"],
        }
    if source_id is not None:
        raise ValueError(f"{outcome} must not select a source")
    return None


def _sources(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    vocal = state["vocal_performance_state"]
    result = {
        take["source_id"]: {
            "source_class": "human_vocal_take",
            "audio_sha256": take["audio"]["sha256"],
        }
        for take in vocal["takes"]
    }
    reference = vocal.get("reference")
    if isinstance(reference, Mapping):
        result[reference["source_id"]] = {
            "source_class": "reference_vocal",
            "audio_sha256": reference["audio"]["sha256"],
        }
    for capture in vocal.get("phrase_captures", []):
        result[capture["source_id"]] = {
            "source_class": "human_vocal_phrase_capture",
            "audio_sha256": capture["audio"]["sha256"],
            "phrase_id": capture["phrase"]["phrase_id"],
        }
    return result


def _source_geometry(
    state: Mapping[str, Any], phrase_id: str, source_id: str
) -> dict[str, Any]:
    vocal = state["vocal_performance_state"]
    for capture in vocal.get("phrase_captures", []):
        if capture["source_id"] != source_id:
            continue
        if capture["phrase"]["phrase_id"] != phrase_id:
            raise ValueError("human phrase capture is bound to another phrase")
        placement = capture["placement"]
        sample_rate = capture["audio_properties"]["sample_rate"]
        start_frame = placement["source_phrase_start_frame"]
        end_frame = placement["source_phrase_end_frame"]
        return {
            "source_start_frame": start_frame,
            "source_end_frame": end_frame,
            "source_start_seconds": start_frame / sample_rate,
            "source_end_seconds": end_frame / sample_rate,
        }
    phrase = _phrase(state, phrase_id)
    for take in vocal["takes"]:
        if take["source_id"] == source_id:
            eligible = take.get("eligible_phrase_ids")
            if eligible is not None and phrase_id not in eligible:
                raise ValueError("human take is bound to another phrase")
            break
    return {
        "source_start_seconds": phrase["start_seconds"],
        "source_end_seconds": phrase["end_seconds"],
    }


def _phrase(state: Mapping[str, Any], phrase_id: str) -> Mapping[str, Any]:
    for phrase in state["structure"]["phrases"]:
        if phrase["phrase_id"] == phrase_id:
            return phrase
    raise ValueError("unknown phrase_id in musical state")


def _require_reviewed_structure(state: Mapping[str, Any]) -> None:
    structure = _mapping(state.get("structure"), "structure")
    if structure.get("review_status") != "reviewed":
        raise ValueError("phrase structure must be reviewed before a decision")


def _decision_effects() -> dict[str, bool]:
    return {
        "human_phrase_decision_created": True,
        "source_map_created": False,
        "audio_comp_rendered": False,
        "join_created": False,
        "pitch_correction_applied": False,
        "timing_correction_applied": False,
        "training_label_created": False,
    }


def _source_map_effects() -> dict[str, bool]:
    return {
        "human_phrase_decision_created": False,
        "source_map_created": True,
        "audio_comp_rendered": False,
        "join_created": False,
        "pitch_correction_applied": False,
        "timing_correction_applied": False,
        "training_label_created": False,
    }


def _verify_hash(document: Mapping[str, Any], label: str) -> None:
    expected = str(document.get("document_sha256", ""))
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if expected != document_sha256(unsigned):
        raise ValueError(f"{label} document SHA-256 does not match")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _reject_private_or_path_fields(value: Any) -> None:
    forbidden = {"path", "absolute_path", "raw_audio", "audio_bytes"}
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).casefold() in forbidden:
                raise ValueError(f"portable vocal decision may not contain {key}")
            _reject_private_or_path_fields(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _reject_private_or_path_fields(item)


__all__ = [
    "PHRASE_OUTCOMES",
    "VOCAL_PHRASE_DECISION_SCHEMA",
    "VOCAL_RENDER_SOURCE_MAP_SCHEMA",
    "VOCAL_SOURCE_MAP_SCHEMA",
    "create_phrase_decision",
    "create_vocal_source_map",
    "create_vocal_render_source_map",
    "validate_phrase_decision",
    "validate_vocal_source_map",
    "validate_vocal_render_source_map",
]
