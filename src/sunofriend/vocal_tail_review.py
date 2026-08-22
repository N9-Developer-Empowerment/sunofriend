"""Path-free human review contracts for a bounded vocal tail comparison."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .source_receipt import document_sha256
from .vocal_comp_render import VOCAL_DRY_RENDER_RESULT_SCHEMA


VOCAL_TAIL_COMPARISON_SCHEMA = "sunofriend.vocal-tail-comparison.v0"
VOCAL_TAIL_CHOICE_SCHEMA = "sunofriend.vocal-tail-choice.v0"
VOCAL_USABLE_BASE_REVIEW_SCHEMA = "sunofriend.vocal-usable-base-review.v0"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def create_vocal_tail_comparison(
    *,
    parent_result_schema: str,
    parent_result_sha256: str,
    phrase_id: str,
    dry_excerpt_audio_sha256: str,
    candidate_a_audio_sha256: str,
    candidate_b_audio_sha256: str,
    sample_rate: int,
    channels: int,
    excerpt_frames: int,
    tail_start_frame: int,
    tail_end_frame: int,
) -> dict[str, Any]:
    """Bind one exact dry excerpt and two already-created tail candidates."""

    document: dict[str, Any] = {
        "schema": VOCAL_TAIL_COMPARISON_SCHEMA,
        "status": "ready_unreviewed",
        "method_natures": ["D"],
        "parent_result": {
            "schema": _dry_result_schema(parent_result_schema),
            "document_sha256": _sha(parent_result_sha256, "parent result"),
        },
        "phrase_id": _identifier(phrase_id, "phrase_id"),
        "audio": {
            "dry_excerpt_sha256": _sha(dry_excerpt_audio_sha256, "dry excerpt"),
            "candidate_a_sha256": _sha(candidate_a_audio_sha256, "candidate A"),
            "candidate_b_sha256": _sha(candidate_b_audio_sha256, "candidate B"),
            "sample_rate": _positive(sample_rate, "sample rate"),
            "channels": _bounded_channels(channels),
            "excerpt_frames": _positive(excerpt_frames, "excerpt frames"),
        },
        "tail_window": {
            "start_frame": _non_negative(tail_start_frame, "tail start"),
            "end_frame": _positive(tail_end_frame, "tail end"),
        },
        "review_policy": {
            "choices": ["a", "b", "neither"],
            "both_candidates_must_be_heard": True,
            "playback_creates_decision": False,
            "visible_default": None,
        },
        "authority": _zero_authority(),
        "effects": _zero_effects(),
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return validate_vocal_tail_comparison(document)


def validate_vocal_tail_comparison(value: Mapping[str, Any]) -> dict[str, Any]:
    document = dict(value)
    _verify(document, VOCAL_TAIL_COMPARISON_SCHEMA, "tail comparison")
    if set(document) != {
        "schema",
        "status",
        "method_natures",
        "parent_result",
        "phrase_id",
        "audio",
        "tail_window",
        "review_policy",
        "authority",
        "effects",
        "network_used",
        "document_sha256",
    }:
        raise ValueError("tail comparison fields changed")
    if document.get("status") != "ready_unreviewed" or document.get(
        "method_natures"
    ) != ["D"]:
        raise ValueError("tail comparison status or method changed")
    parent = _mapping(document.get("parent_result"), "parent result")
    if set(parent) != {"schema", "document_sha256"}:
        raise ValueError("tail comparison parent binding fields changed")
    _dry_result_schema(parent.get("schema"))
    _sha(parent.get("document_sha256"), "parent result")
    _identifier(document.get("phrase_id"), "phrase_id")
    audio = _mapping(document.get("audio"), "audio")
    if set(audio) != {
        "dry_excerpt_sha256",
        "candidate_a_sha256",
        "candidate_b_sha256",
        "sample_rate",
        "channels",
        "excerpt_frames",
    }:
        raise ValueError("tail comparison audio fields changed")
    for key in ("dry_excerpt_sha256", "candidate_a_sha256", "candidate_b_sha256"):
        _sha(audio.get(key), key)
    if audio["candidate_a_sha256"] == audio["candidate_b_sha256"]:
        raise ValueError("tail comparison candidate audio identities must be distinct")
    _positive(audio.get("sample_rate"), "sample rate")
    _bounded_channels(audio.get("channels"))
    frames = _positive(audio.get("excerpt_frames"), "excerpt frames")
    window = _mapping(document.get("tail_window"), "tail window")
    if set(window) != {"start_frame", "end_frame"}:
        raise ValueError("tail window fields changed")
    start = _non_negative(window.get("start_frame"), "tail start")
    end = _positive(window.get("end_frame"), "tail end")
    if not 0 <= start < end <= frames:
        raise ValueError("tail window escapes the exact dry excerpt")
    if document.get("review_policy") != {
        "choices": ["a", "b", "neither"],
        "both_candidates_must_be_heard": True,
        "playback_creates_decision": False,
        "visible_default": None,
    }:
        raise ValueError("tail comparison review policy changed")
    _require_zero_authority(document)
    return document


def create_vocal_tail_choice(
    comparison: Mapping[str, Any],
    *,
    choice: str,
    heard_a: bool,
    heard_b: bool,
    notes: str | None = None,
) -> dict[str, Any]:
    checked = validate_vocal_tail_comparison(comparison)
    if choice not in {"a", "b", "neither"}:
        raise ValueError("tail choice must be a, b or neither")
    if heard_a is not True or heard_b is not True:
        raise ValueError("tail choice requires explicit playback of A and B")
    if not isinstance(notes, (str, type(None))):
        raise ValueError("tail choice notes must be text or null")
    document: dict[str, Any] = {
        "schema": VOCAL_TAIL_CHOICE_SCHEMA,
        "status": "complete_human_tail_choice",
        "method_natures": ["H"],
        "binding": {
            "comparison_schema": VOCAL_TAIL_COMPARISON_SCHEMA,
            "comparison_sha256": checked["document_sha256"],
            "parent_result_sha256": checked["parent_result"]["document_sha256"],
        },
        "phrase_id": checked["phrase_id"],
        "choice": choice,
        "heard": {"a": True, "b": True},
        "notes": notes,
        "authority": _zero_authority(),
        "effects": _zero_effects(),
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return validate_vocal_tail_choice(document, checked)


def validate_vocal_tail_choice(
    value: Mapping[str, Any], comparison: Mapping[str, Any]
) -> dict[str, Any]:
    checked = validate_vocal_tail_comparison(comparison)
    document = dict(value)
    _verify(document, VOCAL_TAIL_CHOICE_SCHEMA, "tail choice")
    if set(document) != {
        "schema",
        "status",
        "method_natures",
        "binding",
        "phrase_id",
        "choice",
        "heard",
        "notes",
        "authority",
        "effects",
        "network_used",
        "document_sha256",
    }:
        raise ValueError("tail choice fields changed")
    if document.get("status") != "complete_human_tail_choice" or document.get(
        "method_natures"
    ) != ["H"]:
        raise ValueError("tail choice status or method changed")
    if (
        document.get("binding")
        != {
            "comparison_schema": VOCAL_TAIL_COMPARISON_SCHEMA,
            "comparison_sha256": checked["document_sha256"],
            "parent_result_sha256": checked["parent_result"]["document_sha256"],
        }
        or document.get("phrase_id") != checked["phrase_id"]
    ):
        raise ValueError("tail choice exact comparison binding changed")
    if document.get("choice") not in {"a", "b", "neither"}:
        raise ValueError("tail choice is unsupported")
    if document.get("heard") != {"a": True, "b": True}:
        raise ValueError("tail choice lacks explicit A/B listening")
    if not isinstance(document.get("notes"), (str, type(None))):
        raise ValueError("tail choice notes changed")
    _require_zero_authority(document)
    return document


def create_vocal_usable_base_review(
    comparison: Mapping[str, Any],
    tail_choice: Mapping[str, Any],
    *,
    outcome: str,
    notes: str | None = None,
) -> dict[str, Any]:
    checked_comparison = validate_vocal_tail_comparison(comparison)
    checked_choice = validate_vocal_tail_choice(tail_choice, checked_comparison)
    if outcome not in {"usable_base", "not_usable_base"}:
        raise ValueError("usable-base outcome is unsupported")
    if outcome == "usable_base" and checked_choice["choice"] == "neither":
        raise ValueError("neither tail candidate cannot become a usable base")
    if not isinstance(notes, (str, type(None))):
        raise ValueError("usable-base notes must be text or null")
    document: dict[str, Any] = {
        "schema": VOCAL_USABLE_BASE_REVIEW_SCHEMA,
        "status": "complete_human_usable_base_review",
        "method_natures": ["H"],
        "binding": {
            "comparison_sha256": checked_comparison["document_sha256"],
            "tail_choice_sha256": checked_choice["document_sha256"],
            "parent_result_sha256": checked_comparison["parent_result"][
                "document_sha256"
            ],
        },
        "phrase_id": checked_comparison["phrase_id"],
        "outcome": outcome,
        "selected_tail": checked_choice["choice"] if outcome == "usable_base" else None,
        "notes": notes,
        "authority": _zero_authority(),
        "effects": _zero_effects(),
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return validate_vocal_usable_base_review(
        document, checked_comparison, checked_choice
    )


def validate_vocal_usable_base_review(
    value: Mapping[str, Any],
    comparison: Mapping[str, Any],
    tail_choice: Mapping[str, Any],
) -> dict[str, Any]:
    checked_comparison = validate_vocal_tail_comparison(comparison)
    checked_choice = validate_vocal_tail_choice(tail_choice, checked_comparison)
    document = dict(value)
    _verify(document, VOCAL_USABLE_BASE_REVIEW_SCHEMA, "usable-base review")
    if set(document) != {
        "schema",
        "status",
        "method_natures",
        "binding",
        "phrase_id",
        "outcome",
        "selected_tail",
        "notes",
        "authority",
        "effects",
        "network_used",
        "document_sha256",
    }:
        raise ValueError("usable-base review fields changed")
    if document.get("status") != "complete_human_usable_base_review" or document.get(
        "method_natures"
    ) != ["H"]:
        raise ValueError("usable-base review status or method changed")
    if (
        document.get("binding")
        != {
            "comparison_sha256": checked_comparison["document_sha256"],
            "tail_choice_sha256": checked_choice["document_sha256"],
            "parent_result_sha256": checked_comparison["parent_result"][
                "document_sha256"
            ],
        }
        or document.get("phrase_id") != checked_comparison["phrase_id"]
    ):
        raise ValueError("usable-base review exact binding changed")
    outcome = document.get("outcome")
    if outcome not in {"usable_base", "not_usable_base"}:
        raise ValueError("usable-base review outcome changed")
    expected_tail = checked_choice["choice"] if outcome == "usable_base" else None
    if expected_tail == "neither" or document.get("selected_tail") != expected_tail:
        raise ValueError("usable-base review selected tail changed")
    if not isinstance(document.get("notes"), (str, type(None))):
        raise ValueError("usable-base review notes changed")
    _require_zero_authority(document)
    return document


def _zero_authority() -> dict[str, bool]:
    return {
        "release_authorized": False,
        "source_replacement_authorized": False,
        "correction_authorized": False,
        "training_authorized": False,
        "model_promotion_authorized": False,
    }


def _zero_effects() -> dict[str, bool]:
    return {
        "audio_created": False,
        "source_mutated": False,
        "render_mutated": False,
        "correction_applied": False,
        "training_label_created": False,
        "model_weights_changed": False,
    }


def _require_zero_authority(document: Mapping[str, Any]) -> None:
    if (
        document.get("authority") != _zero_authority()
        or document.get("effects") != _zero_effects()
        or document.get("network_used") is not False
    ):
        raise ValueError(
            "tail review cannot claim release, correction, training or effects"
        )


def _verify(document: Mapping[str, Any], schema: str, label: str) -> None:
    if document.get("schema") != schema:
        raise ValueError(f"unsupported {label} schema")
    expected = str(document.get("document_sha256", ""))
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if expected != document_sha256(unsigned):
        raise ValueError(f"{label} document SHA-256 changed")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sha(value: Any, label: str) -> str:
    text = str(value)
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return text


def _dry_result_schema(value: Any) -> str:
    text = str(value)
    if text != VOCAL_DRY_RENDER_RESULT_SCHEMA:
        raise ValueError("parent result must be an exact dry vocal render result")
    return text


def _identifier(value: Any, label: str) -> str:
    text = str(value)
    if not _SAFE_ID.fullmatch(text):
        raise ValueError(f"{label} must be a safe identifier")
    return text


def _positive(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _non_negative(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _bounded_channels(value: Any) -> int:
    channels = _positive(value, "channels")
    if channels not in {1, 2}:
        raise ValueError("tail comparison supports mono or stereo audio")
    return channels


__all__ = [
    "VOCAL_TAIL_CHOICE_SCHEMA",
    "VOCAL_TAIL_COMPARISON_SCHEMA",
    "VOCAL_USABLE_BASE_REVIEW_SCHEMA",
    "create_vocal_tail_choice",
    "create_vocal_tail_comparison",
    "create_vocal_usable_base_review",
    "validate_vocal_tail_choice",
    "validate_vocal_tail_comparison",
    "validate_vocal_usable_base_review",
]
