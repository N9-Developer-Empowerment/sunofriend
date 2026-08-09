"""Two source-only additions needed to complete the fine-stem canary cohort."""

from __future__ import annotations

from typing import Any

from .separation_target_presence_plan import (
    build_target_presence_plan,
    target_presence_document_sha256,
)


TARGET_PRESENCE_ADDITION_PLAN_SCHEMA = (
    "sunofriend.fine-stem-target-presence-addition-plan.v1"
)
TARGET_PRESENCE_ADDITION_PACKAGE_NAME = "fine-stem-target-presence-v3"


def build_target_presence_addition_plan() -> dict[str, Any]:
    """Bind one new song per target without opening a separator model."""

    targets = build_target_presence_plan()["targets"]
    plan: dict[str, Any] = {
        "schema": TARGET_PRESENCE_ADDITION_PLAN_SCHEMA,
        "document_sha256": "",
        "status": "approved_source_addition_preflight_no_model_inference",
        "checked_on": "2026-08-09",
        "package_name": TARGET_PRESENCE_ADDITION_PACKAGE_NAME,
        "source_root": "/Users/errolelliott/Downloads",
        "prior_presence": {
            "manifest_sha256": (
                "7f882947bf156bc0b998a39c7a3a29e9db4fbe0deb28f4f095db2d8b33599f63"
            ),
            "result_sha256": (
                "09bddb63e81ed6ab113428f83c2f63d10c0d5d4593c3563380518d06f464f91a"
            ),
            "present_cases_per_target": 3,
        },
        "authority": {
            "artist_catalogue": "creator-owned Ezzye/associated personas",
            "user_statement": (
                "the streaming radio channel contains only the user's songs; "
                "creator downloads may be used and up to five Moises stem packs "
                "may be supplied"
            ),
            "rights_category": "owned",
            "provider_derived_audio": "local_private_attention_hint_only",
            "audio_upload": False,
            "repository_distribution": False,
        },
        "targets": targets,
        "cases": [
            {
                "case_id": "uni-ava--synth_keyboard--addition",
                "track_id": "uni-ava",
                "title": "Uni Ava",
                "target_id": "synth_keyboard",
                "window_seconds": [71, 86],
                "selection_score": 0.894002808,
                "rights_category": "owned",
                "source": "Uni Ava - 03_08_2026, 21.44.wav",
                "source_sha256": (
                    "c0afd4ef1ff394fce200f0c2888e2289b712c2a52a59c1bbc0349fe068372d15"
                ),
                "hints": [
                    "Uni Ava - 03_08_2026, 21.44-G major-123bpm-440hz/"
                    "Uni Ava - 03_08_2026, 21.44-keys-G major-123bpm-440hz.wav",
                    "Uni Ava - 03_08_2026, 21.44-G major-123bpm-440hz/"
                    "Uni Ava - 03_08_2026, 21.44-lead-G major-123bpm-440hz.wav",
                ],
                "hint_sha256": [
                    "9bc2bb7abd5a98e2bd705e3927c217c18ee7e44c503dea8acb5925c51a676831",
                    "091315f1e0705c322e9b58cc3f4df640615a7bf890ceb311e736198eb4e82e62",
                ],
                "public_notes_url": "https://streamit2.me/track/uni-ava",
                "public_notes_summary": "shimmering pop and EDM textures",
            },
            {
                "case_id": "like-fire--guitar--addition",
                "track_id": "like-fire",
                "title": "Like Fire",
                "target_id": "guitar",
                "window_seconds": [18, 33],
                "selection_score": 0.332264876,
                "rights_category": "owned",
                "source": "Like Fire - 30_07_2026, 19.58.wav",
                "source_sha256": (
                    "55e372fff7a563db73b01fe287b6d36014965cdc1f6ef7982b07c97a0be31a68"
                ),
                "hints": [
                    "Like Fire - 30_07_2026, 19.58-Bb major-128bpm-440hz/"
                    "Like Fire - 30_07_2026, 19.58-rhythm-Bb major-128bpm-440hz.wav"
                ],
                "hint_sha256": [
                    "63c38abbd8a3c26aadcbeaa1886616c2e0034946fb507a4a81949438089dc0df"
                ],
                "public_notes_url": "https://streamit2.me/track/like-fire",
                "public_notes_summary": "reggae backbone with drum-and-bass urgency",
            },
        ],
        "selection": {
            "method": (
                "highest pre-model normalized one-second RMS consensus from local "
                "Moises attention hints"
            ),
            "duration_seconds": 15,
            "model_output_used": False,
            "provider_estimates_are_truth": False,
            "human_presence_required": True,
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


def validate_target_presence_addition_plan(value: dict[str, Any]) -> dict[str, Any]:
    expected = build_target_presence_addition_plan()
    if value != expected:
        raise ValueError("target-presence addition plan differs")
    if value["document_sha256"] != target_presence_document_sha256(value):
        raise ValueError("target-presence addition plan hash differs")
    if {case["target_id"] for case in value["cases"]} != set(value["targets"]):
        raise ValueError("target-presence addition targets differ")
    if len({case["track_id"] for case in value["cases"]}) != len(value["cases"]):
        raise ValueError("target-presence additions are not song-disjoint")
    return value


__all__ = [
    "TARGET_PRESENCE_ADDITION_PACKAGE_NAME",
    "TARGET_PRESENCE_ADDITION_PLAN_SCHEMA",
    "build_target_presence_addition_plan",
    "validate_target_presence_addition_plan",
]
