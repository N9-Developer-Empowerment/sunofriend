"""Explicit human A/B labels for immutable vocal attempts.

Playback behaviour is deliberately absent from this contract.  A label exists
only when the musician performs the labelled A/B action.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Mapping, Sequence

from .musical_state import MUSICAL_STATE_SCHEMA, validate_musical_state
from .source_receipt import document_sha256


VOCAL_PAIRWISE_LABEL_SCHEMA = "sunofriend.vocal-attempt-pairwise-label.v1"

PAIRWISE_OUTCOMES = frozenset({"left", "right", "equivalent", "neither", "cannot_tell"})
PAIRWISE_REASON_CODES = frozenset(
    {
        "pitch_contour",
        "lyric_delivery",
        "phrase_completeness",
        "timing_feel",
        "vocal_tone",
        "dynamics",
        "breath_control",
        "technical_quality",
        "context_fit",
        "performance_consistency",
        "no_usable_attempt",
        "unable_to_compare",
    }
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def create_vocal_pairwise_label(
    musical_state: Mapping[str, Any],
    *,
    phrase_id: str,
    left_source_id: str,
    right_source_id: str,
    outcome: str,
    reason_codes: Sequence[str],
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    """Create one explicit comparison label bound to exact state evidence."""

    state = validate_musical_state(musical_state)
    phrase = _phrase(state, phrase_id)
    left = _source(state, phrase_id, left_source_id)
    right = _source(state, phrase_id, right_source_id)
    if left["source_id"] == right["source_id"]:
        raise ValueError("pairwise label requires two different sources")
    if left["audio_sha256"] == right["audio_sha256"]:
        raise ValueError("pairwise label requires two different audio artifacts")
    reasons = _reason_codes(outcome, reason_codes)
    if reviewed_at is not None and not str(reviewed_at).strip():
        raise ValueError("reviewed_at must be non-empty text or null")

    phrase_binding = {
        "phrase_id": phrase["phrase_id"],
        "start_seconds": phrase["start_seconds"],
        "end_seconds": phrase["end_seconds"],
    }
    phrase_binding["phrase_sha256"] = document_sha256(phrase_binding)
    document: dict[str, Any] = {
        "schema": VOCAL_PAIRWISE_LABEL_SCHEMA,
        "status": "complete_explicit_human_pairwise_label",
        "method_natures": ["H"],
        "binding": {
            "musical_state_schema": MUSICAL_STATE_SCHEMA,
            "musical_state_sha256": state["document_sha256"],
        },
        "phrase": phrase_binding,
        "left": left,
        "right": right,
        "outcome": outcome,
        "reason_codes": reasons,
        "review": {
            "authority": "explicit_human_ab_action",
            "reviewed_at": reviewed_at,
        },
        "interaction_limits": {
            "playback_implies_label": False,
            "dwell_implies_label": False,
            "audition_count_implies_label": False,
            "phrase_selection_implies_label": False,
        },
        "training": {
            "explicit_pairwise_label": True,
            "training_eligible": False,
            "reason": "one label requires a gated composition-disjoint snapshot",
        },
        "authority_limits": {
            "source_selected": False,
            "comp_render_authorized": False,
            "correction_authorized": False,
            "training_execution_authorized": False,
        },
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return validate_vocal_pairwise_label(document, musical_state=state)


def validate_vocal_pairwise_label(
    value: Mapping[str, Any],
    *,
    musical_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a label structurally and, when supplied, against exact state."""

    document = dict(value)
    if document.get("schema") != VOCAL_PAIRWISE_LABEL_SCHEMA:
        raise ValueError("unsupported vocal pairwise label schema")
    if document.get("status") != "complete_explicit_human_pairwise_label":
        raise ValueError("pairwise label must be an explicit completed action")
    _verify_hash(document)
    expected_keys = {
        "schema",
        "status",
        "method_natures",
        "binding",
        "phrase",
        "left",
        "right",
        "outcome",
        "reason_codes",
        "review",
        "interaction_limits",
        "training",
        "authority_limits",
        "network_used",
        "document_sha256",
    }
    if set(document) != expected_keys:
        raise ValueError("vocal pairwise label fields changed")
    if document.get("method_natures") != ["H"]:
        raise ValueError("pairwise label must declare human work only")
    binding = _mapping(document.get("binding"), "binding")
    if set(binding) != {"musical_state_schema", "musical_state_sha256"}:
        raise ValueError("pairwise label binding fields changed")
    if binding.get("musical_state_schema") != MUSICAL_STATE_SCHEMA:
        raise ValueError("pairwise label musical-state schema changed")
    _sha256(binding.get("musical_state_sha256"), "musical-state binding")

    phrase = _mapping(document.get("phrase"), "phrase")
    if set(phrase) != {
        "phrase_id",
        "start_seconds",
        "end_seconds",
        "phrase_sha256",
    }:
        raise ValueError("pairwise phrase binding fields changed")
    expected_phrase_hash = document_sha256(
        {key: phrase[key] for key in ("phrase_id", "start_seconds", "end_seconds")}
    )
    if phrase.get("phrase_sha256") != expected_phrase_hash:
        raise ValueError("pairwise phrase binding hash changed")
    for side in ("left", "right"):
        row = _source_row(document.get(side), side)
        if row["source_id"] == document["left" if side == "right" else "right"].get(
            "source_id"
        ):
            raise ValueError("pairwise label requires two different sources")
    if document["left"]["audio_sha256"] == document["right"]["audio_sha256"]:
        raise ValueError("pairwise label requires two different audio artifacts")

    _reason_codes(str(document.get("outcome", "")), document.get("reason_codes", []))
    review = _mapping(document.get("review"), "review")
    if (
        set(review) != {"authority", "reviewed_at"}
        or review.get("authority") != "explicit_human_ab_action"
    ):
        raise ValueError("pairwise label lacks explicit human A/B authority")
    reviewed_at = review.get("reviewed_at")
    if reviewed_at is not None and not str(reviewed_at).strip():
        raise ValueError("reviewed_at must be non-empty text or null")
    if document.get("interaction_limits") != {
        "playback_implies_label": False,
        "dwell_implies_label": False,
        "audition_count_implies_label": False,
        "phrase_selection_implies_label": False,
    }:
        raise ValueError("pairwise interaction limits changed")
    if document.get("training") != {
        "explicit_pairwise_label": True,
        "training_eligible": False,
        "reason": "one label requires a gated composition-disjoint snapshot",
    }:
        raise ValueError("one pairwise label cannot grant training eligibility")
    if document.get("authority_limits") != {
        "source_selected": False,
        "comp_render_authorized": False,
        "correction_authorized": False,
        "training_execution_authorized": False,
    }:
        raise ValueError("pairwise label authority is missing or excessive")
    if document.get("network_used") is not False:
        raise ValueError("pairwise label must record network_used=false")
    _reject_private_fields_and_paths(document)

    if musical_state is not None:
        state = validate_musical_state(musical_state)
        if binding.get("musical_state_sha256") != state["document_sha256"]:
            raise ValueError("pairwise label does not bind this exact musical state")
        state_phrase = _phrase(state, str(phrase.get("phrase_id", "")))
        expected_phrase = {
            "phrase_id": state_phrase["phrase_id"],
            "start_seconds": state_phrase["start_seconds"],
            "end_seconds": state_phrase["end_seconds"],
        }
        expected_phrase["phrase_sha256"] = document_sha256(expected_phrase)
        if dict(phrase) != expected_phrase:
            raise ValueError("pairwise label phrase geometry changed")
        for side in ("left", "right"):
            expected = _source(
                state, state_phrase["phrase_id"], document[side]["source_id"]
            )
            if document[side] != expected:
                raise ValueError(f"pairwise {side} source identity changed")
    return document


def _phrase(state: Mapping[str, Any], phrase_id: str) -> Mapping[str, Any]:
    for row in state["structure"]["phrases"]:
        if row.get("phrase_id") == phrase_id:
            return row
    raise ValueError("pairwise label phrase is not in the musical state")


def _source(state: Mapping[str, Any], phrase_id: str, source_id: str) -> dict[str, str]:
    vocal = state["vocal_performance_state"]
    candidates = list(vocal.get("takes", [])) + list(vocal.get("phrase_captures", []))
    for row in candidates:
        if row.get("source_id") != source_id:
            continue
        if row.get("source_class") not in {
            "human_vocal_take",
            "human_vocal_phrase_capture",
        }:
            raise ValueError("pairwise label supports human vocal attempts only")
        bound_phrase = row.get("phrase")
        if (
            isinstance(bound_phrase, Mapping)
            and bound_phrase.get("phrase_id") != phrase_id
        ):
            raise ValueError("phrase-local capture is not available for this phrase")
        return {
            "source_id": str(row["source_id"]),
            "source_class": str(row["source_class"]),
            "audio_sha256": str(row["audio"]["sha256"]),
        }
    raise ValueError("pairwise label source is not in the musical state")


def _source_row(value: Any, label: str) -> dict[str, Any]:
    row = dict(_mapping(value, label))
    if set(row) != {"source_id", "source_class", "audio_sha256"}:
        raise ValueError(f"pairwise {label} source fields changed")
    source_id = str(row.get("source_id", ""))
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", source_id):
        raise ValueError(f"pairwise {label} source_id must be path-free")
    if row.get("source_class") not in {
        "human_vocal_take",
        "human_vocal_phrase_capture",
    }:
        raise ValueError(f"pairwise {label} source class changed")
    _sha256(row.get("audio_sha256"), f"pairwise {label} audio")
    return row


def _reason_codes(outcome: str, values: Sequence[str]) -> list[str]:
    if outcome not in PAIRWISE_OUTCOMES:
        raise ValueError("unsupported vocal pairwise outcome")
    if isinstance(values, (str, bytes)):
        raise ValueError("pairwise reason_codes must be a list")
    reasons = [str(item) for item in values]
    if not 1 <= len(reasons) <= 4 or len(reasons) != len(set(reasons)):
        raise ValueError("pairwise label requires 1-4 unique reason codes")
    if any(item not in PAIRWISE_REASON_CODES for item in reasons):
        raise ValueError("unsupported vocal pairwise reason code")
    if outcome == "cannot_tell" and "unable_to_compare" not in reasons:
        raise ValueError("cannot_tell requires unable_to_compare")
    if outcome == "neither" and "no_usable_attempt" not in reasons:
        raise ValueError("neither requires no_usable_attempt")
    if outcome not in {"cannot_tell", "neither"} and {
        "unable_to_compare",
        "no_usable_attempt",
    }.intersection(reasons):
        raise ValueError("reason code does not match pairwise outcome")
    return reasons


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sha256(value: Any, label: str) -> str:
    text = str(value or "")
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return text


def _verify_hash(document: Mapping[str, Any]) -> None:
    supplied = _sha256(document.get("document_sha256"), "pairwise label document")
    without_hash = dict(document)
    without_hash.pop("document_sha256", None)
    if document_sha256(without_hash) != supplied:
        raise ValueError("vocal pairwise label document hash changed")


def _reject_private_fields_and_paths(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = str(key).casefold()
            if lowered in {
                "path",
                "notes",
                "note",
                "lyrics",
                "filename",
                "source_name",
            }:
                raise ValueError("pairwise label contains private text or a path field")
            _reject_private_fields_and_paths(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _reject_private_fields_and_paths(item)
    elif isinstance(value, str):
        if PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute():
            raise ValueError("pairwise label contains an absolute path")
