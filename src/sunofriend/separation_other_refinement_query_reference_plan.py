"""Pure, no-effects plan for the first Banquet reference-query canary."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .separation_other_refinement_query_load_contract import (
    EXPECTED_CHECKPOINTS,
    QUERY_BANDIT_SOURCE_REVISION,
    QUERY_PROFILE_ID,
)


QUERY_REFERENCE_PLAN_SCHEMA = (
    "sunofriend.other-refinement-query-reference-canary-plan.v1"
)
QUERY_REFERENCE_PLAN_STATUS = (
    "blocked_pending_explicit_rights_bound_reference_inference_approval"
)
SYNTHETIC_REPORT_SHA256 = (
    "bd5fa57716267488cfd9a0d1d69bc1627da6244d283fdaec5a5592234d51cec8"
)


def query_reference_plan_sha256(value: dict[str, Any]) -> str:
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


def build_query_reference_plan() -> dict[str, Any]:
    """Build the bounded song-disjoint plan without opening local audio."""

    query_track = (
        "I am a Alien - 18_07_2026, 17.02 x I am a Alien - 18_07_2026, "
        "17.02 (Mashup)-Eb minor-114bpm-440hz"
    )
    query_pack = (
        "I am a Alien - 18_07_2026, 17.02 x I am a Alien - 18_07_2026, "
        "17.02 (Mashup) Stems"
    )
    plan: dict[str, Any] = {
        "schema": QUERY_REFERENCE_PLAN_SCHEMA,
        "document_sha256": "",
        "status": QUERY_REFERENCE_PLAN_STATUS,
        "checked_on": "2026-08-08",
        "scope_id": "other-query-refinement-v1",
        "profile_id": QUERY_PROFILE_ID,
        "release_tier": "studio_challenger",
        "registered": False,
        "executable": False,
        "evidence_binding": {
            "source_revision": QUERY_BANDIT_SOURCE_REVISION,
            "checkpoints": EXPECTED_CHECKPOINTS,
            "model_load_report_sha256": (
                "12c028e88afdb94a22aa4344b75fb63a23386fd4f2292d9bf9aac0405b12dced"
            ),
            "synthetic_report_sha256": SYNTHETIC_REPORT_SHA256,
            "authorised_corpus_manifest": "stem_examples/corpus.json",
            "authorised_corpus_manifest_sha256": (
                "1b61e53f41eeb929d12a6e0184916a9e760e4aff364e2d4d647f7f14535127c3"
            ),
            "frozen_window_manifest": (
                "stem_examples/other-refinement-evaluation-v1.json"
            ),
            "frozen_window_manifest_sha256": (
                "d838c000b6b75cf4937669a8a063bf8a20f9b7af9ce9cc42ada0d2fea8e683f4"
            ),
        },
        "rights_and_privacy": {
            "rights_category": "owned",
            "owner_credit": "Music by Ezzye — https://soundcloud.com/ezzye-1",
            "tracks_in_scope": [
                "i-am-a-alien-mashup",
                "be-alone",
                "in-the-way",
                "tell-me-that-i-do-it-bitch",
            ],
            "provider_derived_audio_use": (
                "local comparison estimate and query hint, never ground truth"
            ),
            "audio_upload": False,
            "telemetry": False,
            "repository_audio": False,
            "hosted_conversion": False,
        },
        "query_bank": {
            "track_id": "i-am-a-alien-mashup",
            "song_disjoint_from_every_test_mixture": True,
            "duration_seconds_each": 10.0,
            "selection": "one fixed first Suno pack; no post-result query hunt",
            "queries": [
                {
                    "target_id": "guitar",
                    "relative_path": f"{query_track}/SUNO/{query_pack}/4 Guitar.wav",
                    "start_seconds": 5.0,
                    "end_seconds": 15.0,
                    "provider_label_is_truth": False,
                },
                {
                    "target_id": "keyboard",
                    "relative_path": f"{query_track}/SUNO/{query_pack}/5 Keyboard.wav",
                    "start_seconds": 210.0,
                    "end_seconds": 220.0,
                    "provider_label_is_truth": False,
                },
                {
                    "target_id": "synth",
                    "relative_path": f"{query_track}/SUNO/{query_pack}/7 Synth.wav",
                    "start_seconds": 210.0,
                    "end_seconds": 220.0,
                    "provider_label_is_truth": False,
                },
            ],
        },
        "test_mixtures": [
            {
                "track_id": "be-alone",
                "relative_path": (
                    "Be Alone - 16_07_2026, 22.45-G# minor-136bpm-440hz/"
                    "ORIGINAL/Be Alone - 16_07_2026, 22.45.wav"
                ),
                "windows": {
                    "guitar": [53.0, 68.0],
                    "keyboard": [201.0, 216.0],
                    "synth": [201.0, 216.0],
                },
            },
            {
                "track_id": "in-the-way",
                "relative_path": (
                    "In the way - 22_07_2026, 17.43-Bb minor-90bpm-440hz/"
                    "ORIGINAL/In the way - 22:07:2026, 17.43.wav"
                ),
                "windows": {
                    "guitar": [73.0, 88.0],
                    "keyboard": [129.0, 144.0],
                    "synth": [129.0, 144.0],
                },
            },
            {
                "track_id": "tell-me-that-i-do-it-bitch",
                "relative_path": (
                    "Tell Me That I Do It Bitch - 19_07_2026, 11.20-Cm-130bpm-441hz "
                    "(1)-C# minor-129bpm-440hz/ORIGINAL/Tell Me That I Do It Bitch "
                    "- 19_07_2026, 11.20-Cm-130bpm-441hz (1).wav"
                ),
                "windows": {
                    "guitar": [29.0, 44.0],
                    "keyboard": [135.0, 150.0],
                    "synth": [135.0, 150.0],
                },
            },
        ],
        "execution_contract": {
            "configuration_count": 1,
            "query_count": 3,
            "mixture_count": 3,
            "inference_attempt_limit": 9,
            "remediation_cycle_limit": 1,
            "remediation_trigger": "objective execution fault only",
            "device": "cpu",
            "network_denied": True,
            "canonical_input": "stereo 44.1 kHz float32 in memory",
            "mixture_duration_seconds_each": 15.0,
            "query_duration_seconds_each": 10.0,
            "load_models_once_per_worker": True,
            "query_or_configuration_change_after_feedback": False,
            "shared_attenuation_before_pcm24_if_required": True,
            "pcm24_residual_definition": "canonical_mixture - persisted_target",
            "maximum_persisted_reconstruction_error_lsb": 2,
            "maximum_elapsed_seconds_total": 180.0,
            "maximum_peak_resident_set_bytes": 12_884_901_888,
        },
        "private_outputs": {
            "per_case": ["source_reference", "query_reference", "target", "residual"],
            "audio_format": "stereo PCM24 WAV at 44.1 kHz",
            "report": "hash-bound objective JSON",
            "reconstruction_accounting_is_not_separation_accuracy": True,
            "review": "local-only page with download and copy fallbacks",
            "automatic_upload": False,
        },
        "objective_gates": [
            "exact model, checkpoint, corpus and input hashes",
            "zero network attempts",
            "nine exact song-disjoint inference attempts",
            "matching output shape and clock",
            "finite target and residual samples",
            "target plus residual reconstructs each canonical mixture",
            "persisted PCM24 reconstruction is within two LSBs",
            "elapsed and peak-memory ceilings",
            "atomic private publication",
        ],
        "feedback_policy": {
            "one_complete_listen_per_case": True,
            "minimum_usefulness_rating": None,
            "cannot_tell_is_valid": True,
            "poor_feedback_disables_last_profile": False,
            "poor_feedback_triggers_query_hunt": False,
            "result_selects_source": False,
            "result_starts_midi": False,
        },
        "next_approval": {
            "required": True,
            "exact_text": (
                "I approve one network-denied, CPU-only Banquet reference-query "
                "canary using the four owner-authorised Ezzye tracks and the exact "
                "frozen guitar, keyboard and synth query/window plan, including "
                "hashing and locally decoding those files, nine song-disjoint "
                "inference attempts, and private PCM24 review artifacts. Provider "
                "stems remain comparison estimates, not truth. This does not approve "
                "public activation, source selection, MIDI, audio upload, hosting, "
                "checkpoint redistribution, a commercial default or automatic retry."
            ),
            "authorizes_audio_reads": True,
            "authorizes_inference_attempts": 9,
            "authorizes_private_review_audio": True,
            "authorizes_public_activation": False,
            "authorizes_source_selection": False,
            "authorizes_midi": False,
        },
        "effects": {
            "audio_read_by_plan": False,
            "checkpoint_opened_by_plan": False,
            "model_constructed_by_plan": False,
            "inference_runs": 0,
            "audio_written_by_plan": False,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
        },
    }
    plan["document_sha256"] = query_reference_plan_sha256(plan)
    return plan


def validate_query_reference_plan(value: dict[str, Any]) -> dict[str, Any]:
    expected = build_query_reference_plan()
    if value != expected:
        raise ValueError("query reference plan differs from the reviewed plan")
    if value["document_sha256"] != query_reference_plan_sha256(value):
        raise ValueError("query reference plan document hash differs")
    return value


__all__ = [
    "QUERY_REFERENCE_PLAN_SCHEMA",
    "QUERY_REFERENCE_PLAN_STATUS",
    "build_query_reference_plan",
    "query_reference_plan_sha256",
    "validate_query_reference_plan",
]
