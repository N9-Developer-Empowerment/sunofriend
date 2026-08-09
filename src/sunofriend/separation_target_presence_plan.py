"""Pure plan for source-only fine-stem target-presence review."""

from __future__ import annotations

import hashlib
import json
from typing import Any


TARGET_PRESENCE_PLAN_SCHEMA = "sunofriend.fine-stem-target-presence-plan.v1"
TARGET_PRESENCE_PACKAGE_NAME = "fine-stem-target-presence-v1"
CORPUS_MANIFEST_SHA256 = (
    "1b61e53f41eeb929d12a6e0184916a9e760e4aff364e2d4d647f7f14535127c3"
)


def target_presence_document_sha256(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "document_sha256"}
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _tracks() -> list[dict[str, Any]]:
    be_alone = "Be Alone - 16_07_2026, 22.45-G# minor-136bpm-440hz"
    alien = (
        "I am a Alien - 18_07_2026, 17.02 x I am a Alien - 18_07_2026, "
        "17.02 (Mashup)-Eb minor-114bpm-440hz"
    )
    alien_stem = (
        "I am a Alien - 18_07_2026, 17.02 x I am a Alien - 18_07_2026, "
        "17.02 (Mashup) Stems"
    )
    in_way = "In the way - 22_07_2026, 17.43-Bb minor-90bpm-440hz"
    tell = (
        "Tell Me That I Do It Bitch - 19_07_2026, 11.20-Cm-130bpm-441hz "
        "(1)-C# minor-129bpm-440hz"
    )
    tell_stem = "Tell Me That I Do It Bitch - 19_07_2026, 11.20-Cm-130bpm-441hz"
    return [
        {
            "track_id": "be-alone",
            "title": "Be Alone",
            "directory": be_alone,
            "source": f"{be_alone}/ORIGINAL/Be Alone - 16_07_2026, 22.45.wav",
            "hints": {
                "synth_keyboard": [
                    f"{be_alone}/SUNO/Be Alone - 16_07_2026, 22.45 Stems/6 Synth.wav",
                    f"{be_alone}/SUNO/Be Alone - 16_07_2026, 22.45 Stems (1)/6 Synth.wav",
                ],
                "guitar": [
                    f"{be_alone}/MOISES/Be Alone - 16_07_2026, 22.45-rhythm-G# minor-136bpm-440hz.wav"
                ],
            },
        },
        {
            "track_id": "i-am-a-alien-mashup",
            "title": "I am a Alien mashup",
            "directory": alien,
            "source": (
                f"{alien}/ORIGINAL/I am a Alien - 18_07_2026, 17.02 x "
                "I am a Alien - 18_07_2026, 17.02 (Mashup).wav"
            ),
            "hints": {
                "synth_keyboard": [
                    f"{alien}/SUNO/{alien_stem}/7 Synth.wav",
                    f"{alien}/SUNO/{alien_stem} (1)/7 Synth.wav",
                ],
                "guitar": [
                    f"{alien}/SUNO/{alien_stem}/4 Guitar.wav",
                    f"{alien}/SUNO/{alien_stem} (1)/4 Guitar.wav",
                    f"{alien}/MOISES/I am a Alien - 18_07_2026, 17.02 x I am a Alien - 18_07_2026, 17.02 (Mashup)-rhythm-Eb minor-114bpm-440hz.wav",
                ],
            },
        },
        {
            "track_id": "in-the-way",
            "title": "In the way",
            "directory": in_way,
            "source": f"{in_way}/ORIGINAL/In the way - 22:07:2026, 17.43.wav",
            "hints": {
                "synth_keyboard": [
                    f"{in_way}/SUNO/In the way - 22_07_2026, 17.43 Stems/6 Synth.wav",
                    f"{in_way}/SUNO/In the way - 22_07_2026, 17.43 Stems (1)/6 Synth.wav",
                ],
                "guitar": [
                    f"{in_way}/SUNO/In the way - 22_07_2026, 17.43 Stems/4 Guitar.wav",
                    f"{in_way}/SUNO/In the way - 22_07_2026, 17.43 Stems (1)/4 Guitar.wav",
                    f"{in_way}/MOISES/In the way - 22_07_2026, 17.43-rhythm-Bb minor-90bpm-440hz.wav",
                ],
            },
        },
        {
            "track_id": "tell-me-that-i-do-it-bitch",
            "title": "Tell Me That I Do It Bitch",
            "directory": tell,
            "source": (
                f"{tell}/ORIGINAL/Tell Me That I Do It Bitch - "
                "19_07_2026, 11.20-Cm-130bpm-441hz (1).wav"
            ),
            "hints": {
                "synth_keyboard": [
                    f"{tell}/SUNO/{tell_stem} Stems (2)/5 Synth.wav",
                    f"{tell}/SUNO/{tell_stem} Stems (3)/5 Synth.wav",
                ],
                "guitar": [
                    f"{tell}/MOISES/Tell Me That I Do It Bitch - 19_07_2026, 11.20-Cm-130bpm-441hz (1)-rhythm-C# minor-129bpm-440hz.wav"
                ],
            },
        },
    ]


def build_target_presence_plan() -> dict[str, Any]:
    plan: dict[str, Any] = {
        "schema": TARGET_PRESENCE_PLAN_SCHEMA,
        "document_sha256": "",
        "status": "approved_source_presence_preflight_no_model_inference",
        "checked_on": "2026-08-09",
        "package_name": TARGET_PRESENCE_PACKAGE_NAME,
        "corpus": {
            "manifest": "corpus.json",
            "manifest_sha256": CORPUS_MANIFEST_SHA256,
            "rights_category": "owned",
            "owner_credit": "Music by Ezzye — https://soundcloud.com/ezzye-1",
            "provider_estimates_are_truth": False,
        },
        "targets": {
            "synth_keyboard": {
                "label": "Synth / broad keyboards",
                "model_profile": "bs-roformer-mega-53-synth-v1",
                "definition": (
                    "audible electronic or keyboard tonal material; acoustic piano "
                    "alone does not establish this target"
                ),
            },
            "guitar": {
                "label": "Guitar",
                "model_profile": "bs-roformer-sw-guitar-v1",
                "definition": (
                    "audible acoustic or electric plucked, strummed or sustained "
                    "guitar; a provider rhythm label is only an attention hint"
                ),
            },
        },
        "tracks": _tracks(),
        "selection": {
            "duration_seconds": 15,
            "step_seconds": 1,
            "boundary_margin_seconds": 5,
            "method": (
                "highest pre-inference provider-hint consensus using normalized "
                "one-second RMS; no separator output is available during selection"
            ),
            "human_decisions": ["present", "absent", "cannot_tell"],
            "present_required_before_model_inference": True,
            "absent_or_cannot_tell_counts_as_model_failure": False,
            "replacement_song_allowed_before_inference": True,
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


def validate_target_presence_plan(value: dict[str, Any]) -> dict[str, Any]:
    expected = build_target_presence_plan()
    if value != expected:
        raise ValueError("target-presence plan differs")
    if value["document_sha256"] != target_presence_document_sha256(value):
        raise ValueError("target-presence plan hash differs")
    return value


__all__ = [
    "CORPUS_MANIFEST_SHA256",
    "TARGET_PRESENCE_PACKAGE_NAME",
    "TARGET_PRESENCE_PLAN_SCHEMA",
    "build_target_presence_plan",
    "target_presence_document_sha256",
    "validate_target_presence_plan",
]
