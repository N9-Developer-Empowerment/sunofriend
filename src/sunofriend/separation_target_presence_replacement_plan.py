"""Frozen source-only replacement cases for synth and guitar canaries."""

from __future__ import annotations

import unicodedata
from typing import Any

from .separation_target_presence_plan import (
    build_target_presence_plan,
    target_presence_document_sha256,
)


TARGET_PRESENCE_REPLACEMENT_PLAN_SCHEMA = (
    "sunofriend.fine-stem-target-presence-replacement-plan.v1"
)
TARGET_PRESENCE_REPLACEMENT_PACKAGE_NAME = "fine-stem-target-presence-v2"
PRIVATE_REFERENCE_CORPUS_MANIFEST_SHA256 = (
    "e5c58e06572a15ed38bb45223e72ed9a50cc9426d5a2f2b48055306ba7a33e96"
)


def _base_tracks() -> dict[str, dict[str, Any]]:
    return {
        track["track_id"]: track for track in build_target_presence_plan()["tracks"]
    }


def _base_case(
    track_id: str,
    target_id: str,
    start_seconds: int,
    selection_score: float,
) -> dict[str, Any]:
    track = _base_tracks()[track_id]
    return {
        "case_id": f"{track_id}--{target_id}--replacement",
        "track_id": track_id,
        "title": track["title"],
        "target_id": target_id,
        "window_seconds": [start_seconds, start_seconds + 15],
        "selection_score": selection_score,
        "corpus_manifest": "corpus.json",
        "rights_category": "owned",
        "source": track["source"],
        "hints": track["hints"][target_id],
    }


def _mauvais_guitar_case() -> dict[str, Any]:
    directory = unicodedata.normalize(
        "NFD", "Mauvais djo - 06. Pilé-Bb minor-130bpm-440hz"
    )
    stem_name = unicodedata.normalize("NFD", "Mauvais djo - 06. Pilé")
    return {
        "case_id": "mauvais-djo-pile--guitar--replacement",
        "track_id": "mauvais-djo-pile",
        "title": "Mauvais djo - Pilé",
        "target_id": "guitar",
        "window_seconds": [50, 65],
        "selection_score": 0.725253,
        "corpus_manifest": "private-reference-corpus.json",
        "rights_category": "authorised_private_use",
        "source": f"{directory}/ORIGINAL/Mauvais djo - 06. Pilé.flac",
        "hints": [f"{directory}/MOISES/{stem_name}-rhythm-Bb minor-130bpm-440hz.wav"],
    }


def build_target_presence_replacement_plan() -> dict[str, Any]:
    """Bind one source-only replacement cohort without opening a model."""

    base = build_target_presence_plan()
    cases = [
        _base_case("be-alone", "synth_keyboard", 201, 1.052803),
        _base_case("i-am-a-alien-mashup", "synth_keyboard", 210, 0.977039),
        _base_case("in-the-way", "synth_keyboard", 129, 0.893093),
        _base_case("tell-me-that-i-do-it-bitch", "synth_keyboard", 135, 0.87884),
        _base_case("be-alone", "guitar", 53, 0.748635),
        _base_case("i-am-a-alien-mashup", "guitar", 5, 0.403382),
        _base_case("in-the-way", "guitar", 73, 0.747657),
        _mauvais_guitar_case(),
    ]
    plan: dict[str, Any] = {
        "schema": TARGET_PRESENCE_REPLACEMENT_PLAN_SCHEMA,
        "document_sha256": "",
        "status": "approved_source_replacement_preflight_no_model_inference",
        "checked_on": "2026-08-09",
        "package_name": TARGET_PRESENCE_REPLACEMENT_PACKAGE_NAME,
        "replaces_manifest_sha256": (
            "0d04d23d9af4cd0817d6e0a745e6c7ef45a06e9027847f3277977f7381e576aa"
        ),
        "replacement_reason": (
            "the first reviewed windows did not establish four present, "
            "song-disjoint cases for either target"
        ),
        "corpora": {
            "corpus.json": {
                "manifest_sha256": base["corpus"]["manifest_sha256"],
                "rights_category": "owned",
                "owner_credit": base["corpus"]["owner_credit"],
            },
            "private-reference-corpus.json": {
                "manifest_sha256": PRIVATE_REFERENCE_CORPUS_MANIFEST_SHA256,
                "rights_category": "authorised_private_use",
                "scope": "private_local_evaluation_only",
            },
        },
        "targets": base["targets"],
        "cases": cases,
        "selection": {
            "method": (
                "frozen pre-model provider-role activity windows from "
                "other-refinement-evaluation-v1"
            ),
            "duration_seconds": 15,
            "model_output_used": False,
            "provider_estimates_are_truth": False,
            "human_presence_required": True,
            "present_required_before_model_inference": True,
            "absent_or_cannot_tell_counts_as_model_failure": False,
            "automatic_retry": False,
        },
        "effects": {
            "source_and_provider_audio_read": True,
            "private_pcm24_presence_audio_written": True,
            "checkpoint_opened": False,
            "model_constructed": False,
            "inference_attempts": 0,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "audio_uploaded": False,
            "telemetry": False,
        },
    }
    plan["document_sha256"] = target_presence_document_sha256(plan)
    return plan


def validate_target_presence_replacement_plan(
    value: dict[str, Any],
) -> dict[str, Any]:
    expected = build_target_presence_replacement_plan()
    if value != expected:
        raise ValueError("target-presence replacement plan differs")
    if value["document_sha256"] != target_presence_document_sha256(value):
        raise ValueError("target-presence replacement plan hash differs")
    for target_id in expected["targets"]:
        tracks = [
            case["track_id"]
            for case in expected["cases"]
            if case["target_id"] == target_id
        ]
        if len(tracks) != 4 or len(set(tracks)) != 4:
            raise ValueError("replacement target cases are not song-disjoint")
    return value


__all__ = [
    "PRIVATE_REFERENCE_CORPUS_MANIFEST_SHA256",
    "TARGET_PRESENCE_REPLACEMENT_PACKAGE_NAME",
    "TARGET_PRESENCE_REPLACEMENT_PLAN_SCHEMA",
    "build_target_presence_replacement_plan",
    "validate_target_presence_replacement_plan",
]
