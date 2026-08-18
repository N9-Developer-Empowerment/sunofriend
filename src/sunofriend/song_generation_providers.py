"""Public capability registry for full-song generation providers."""

from __future__ import annotations

from typing import Any


SONG_GENERATION_PROVIDERS_SCHEMA = "sunofriend.song-generation-providers.v1"
REFERENCE_CONDITIONED_OPERATION = "reference_conditioned_full_song"
NATIVE_AUDIO_REMIX_OPERATION = "native_audio_remix"
SONG_GENERATION_OPERATIONS = frozenset(
    {REFERENCE_CONDITIONED_OPERATION, NATIVE_AUDIO_REMIX_OPERATION}
)


def song_generation_providers_document() -> dict[str, Any]:
    """Return a secret-free, read-only inventory of evaluated providers."""

    return {
        "schema": SONG_GENERATION_PROVIDERS_SCHEMA,
        "operation": REFERENCE_CONDITIONED_OPERATION,
        "operations": sorted(SONG_GENERATION_OPERATIONS),
        "default_provider": "ace-step-api",
        "selection_policy": {
            "registered_only": True,
            "must_support_reference_audio_conditioning": True,
            "must_support_independent_reference_strength": True,
            "must_support_independent_style_description_strength": True,
            "must_produce_two_candidates": True,
            "candidate_count_may_use_multiple_provider_tasks": True,
            "must_archive_remote_outputs_immediately": True,
            "cloud_requires_explicit_enablement": True,
            "cloud_requires_terms_and_cost_acknowledgement": True,
            "api_keys_must_come_from_user_environment": True,
        },
        "providers": [
            _ace_step_capability(),
            _treblo_capability(),
        ],
    }


def provider_capability(provider_id: str) -> dict[str, Any]:
    """Return one provider capability or raise a bounded lookup error."""

    expected = str(provider_id).strip()
    for provider in song_generation_providers_document()["providers"]:
        if provider["id"] == expected:
            return provider
    available = ", ".join(
        provider["id"]
        for provider in song_generation_providers_document()["providers"]
    )
    raise ValueError(f"unknown song-generation provider {expected!r}: {available}")


def registered_provider_ids(
    operation: str = REFERENCE_CONDITIONED_OPERATION,
) -> tuple[str, ...]:
    """Return providers eligible for one song-generation operation."""

    selected_operation = str(operation).strip()
    if selected_operation not in SONG_GENERATION_OPERATIONS:
        raise ValueError(f"unknown song-generation operation: {selected_operation}")

    return tuple(
        provider["id"]
        for provider in song_generation_providers_document()["providers"]
        if provider["registration"].get(selected_operation, False)
    )


def _ace_step_capability() -> dict[str, Any]:
    return {
        "id": "ace-step-api",
        "name": "ACE-Step 1.5 API",
        "provider_type": "open_weights_local_or_self_hosted",
        "registration": {
            "status": "registered",
            "reference_conditioned_full_song": True,
            "native_audio_remix": True,
            "reason": None,
        },
        "capabilities": {
            "prompt_and_supplied_lyrics": True,
            "annotated_lyrics_text_preserved": True,
            "annotated_lyrics_semantics_verified": False,
            "reference_audio_conditioning": True,
            "native_audio_remix": True,
            "native_audio_remix_backend_task": "cover",
            "native_audio_remix_duration_policy": "source_locked",
            "native_audio_remix_replacement_lyrics": True,
            "native_audio_remix_quality_verified": False,
            "native_audio_remix_human_evaluation": (
                "rejected_flat_monotonic_vocals_and_unmusical_accompaniment"
            ),
            "native_audio_remix_advances": False,
            "independent_reference_strength": True,
            "independent_style_description_strength": True,
            "candidate_count_per_request": 2,
            "deterministic_seed_available": True,
            "model_selected_duration": True,
        },
        "privacy_and_access": {
            "bring_your_own_key": "optional_for_configured_server",
            "api_key_environment": "SUNOFRIEND_MUSIC_API_TOKEN",
            "reference_transport": "multipart_file_upload",
            "audio_leaves_machine": "deployment_dependent",
            "possible_charges": "deployment_dependent",
            "attribution_required": False,
            "remote_result_retention_hours": None,
        },
        "evidence": {
            "documentation": "https://github.com/ace-step/ACE-Step-1.5",
            "verified_on": "2026-08-18",
        },
    }


def _treblo_capability() -> dict[str, Any]:
    return {
        "id": "treblo-v3-api",
        "name": "TREBLO Melodia v3 API",
        "provider_type": "proprietary_cloud_byok",
        "registration": {
            "status": "evaluated_not_registered",
            "reference_conditioned_full_song": False,
            "native_audio_remix": False,
            "reason": (
                "v3 generates from prompt/lyrics but exposes source audio only for "
                "continuation; it cannot honour the required general reference-audio "
                "conditioning or independent reference-strength control"
            ),
        },
        "capabilities": {
            "prompt_and_supplied_lyrics": True,
            "annotated_lyrics_text_preserved": "provider_accepts_supplied_text",
            "annotated_lyrics_semantics_verified": False,
            "reference_audio_conditioning": False,
            "source_audio_extension": True,
            "independent_reference_strength": False,
            "independent_style_description_strength": True,
            "candidate_count_per_request": 1,
            "two_candidates_require_two_billable_tasks": True,
            "deterministic_seed_available": False,
            "explicit_bpm_available": False,
            "length_hint_maximum_seconds": 300,
            "model_selected_duration": True,
            "preview_api": True,
        },
        "privacy_and_access": {
            "bring_your_own_key": "required",
            "api_key_environment": "SUNOFRIEND_TREBLO_API_KEY",
            "api_key_committed_or_logged": False,
            "reference_transport": "cloud_upload_for_extension_only",
            "audio_leaves_machine": True,
            "possible_charges": True,
            "cost_confirmation_required": True,
            "terms_acceptance_required": True,
            "attribution_required": True,
            "remote_result_retention_hours": 168,
            "archive_result_immediately": True,
        },
        "integration_policy": {
            "default": False,
            "browser_receives_shared_key": False,
            "webhooks_enabled_by_default": False,
            "polling_preferred_until_webhook_signing_is_documented": True,
            "public_saas_or_competitive_use_requires_terms_review": True,
            "written_provider_confirmation_recommended": True,
        },
        "evidence": {
            "documentation": "https://treblo.com/developers/docs",
            "pricing": "https://treblo.com/developers/pricing",
            "terms": "https://treblo.com/tos",
            "verified_on": "2026-08-17",
        },
    }


__all__ = [
    "REFERENCE_CONDITIONED_OPERATION",
    "SONG_GENERATION_PROVIDERS_SCHEMA",
    "provider_capability",
    "registered_provider_ids",
    "song_generation_providers_document",
]
