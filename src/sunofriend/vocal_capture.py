"""Path-free evidence for one bounded browser microphone capture."""

from __future__ import annotations

from typing import Any, Mapping

from .musical_state import MUSICAL_STATE_SCHEMA, validate_musical_state
from .source_receipt import document_sha256
from .vocal_capture_contract import (
    VOCAL_CAPTURE_SCHEMA,
    _finite,
    _mapping,
    _non_negative_integer,
    _phrase,
    _positive_integer,
    _safe_id,
    _sha256,
    _zero_effects,
    validate_vocal_capture_against_state,
)


def create_vocal_capture(
    musical_state: Mapping[str, Any],
    *,
    capture_id: str,
    phrase_id: str,
    cue_id: str,
    cue_asset_sha256: str,
    audio_sha256: str,
    audio_bytes: int,
    sample_rate: int,
    frame_count: int,
    phrase_start_frame: int,
    phrase_end_frame: int,
    destination_start_seconds: float,
    destination_end_seconds: float,
    pre_guard_frames: int,
    post_guard_frames: int,
    requested_processing: Mapping[str, Any],
    actual_processing: Mapping[str, Any],
) -> dict[str, Any]:
    """Create one stored-but-unreviewed phrase capture receipt."""

    state = validate_musical_state(musical_state)
    phrase = _phrase(state, phrase_id)
    capture_id = _safe_id(capture_id, "capture_id")
    cue_id = _safe_id(cue_id, "cue_id")
    cue_asset_sha256 = _sha256(cue_asset_sha256, "cue asset")
    audio_sha256 = _sha256(audio_sha256, "capture audio")
    audio_bytes = _positive_integer(audio_bytes, "audio_bytes")
    sample_rate = _positive_integer(sample_rate, "sample_rate")
    frame_count = _positive_integer(frame_count, "frame_count")
    phrase_start_frame = _non_negative_integer(phrase_start_frame, "phrase_start_frame")
    phrase_end_frame = _positive_integer(phrase_end_frame, "phrase_end_frame")
    pre_guard_frames = _non_negative_integer(pre_guard_frames, "pre_guard_frames")
    post_guard_frames = _non_negative_integer(post_guard_frames, "post_guard_frames")
    destination_start_seconds = _finite(
        destination_start_seconds, "destination_start_seconds"
    )
    destination_end_seconds = _finite(
        destination_end_seconds, "destination_end_seconds"
    )
    requested = _mapping(requested_processing, "requested processing")
    actual = _mapping(actual_processing, "actual processing")

    document: dict[str, Any] = {
        "schema": VOCAL_CAPTURE_SCHEMA,
        "status": "stored_unreviewed",
        "method_natures": ["D", "H"],
        "binding": {
            "musical_state_schema": MUSICAL_STATE_SCHEMA,
            "musical_state_sha256": state["document_sha256"],
        },
        "capture": {
            "capture_id": capture_id,
            "source_id": f"browser-capture-{capture_id}",
            "source_class": "browser_microphone_phrase_capture",
            "scope": "bounded_phrase_with_guards",
            "common_recorded_song_zero": False,
        },
        "phrase": {
            "phrase_id": phrase["phrase_id"],
            "lyrics": phrase["lyrics"],
            "review_status": "reviewed",
        },
        "cue": {
            "cue_id": cue_id,
            "audio_sha256": cue_asset_sha256,
            "authority": "explicit_hash_bound_recording_cue_only",
        },
        "audio": {
            "sha256": audio_sha256,
            "bytes": audio_bytes,
            "format": "WAV",
            "subtype": "PCM_24",
            "channels": 1,
            "sample_rate": sample_rate,
            "frames": frame_count,
        },
        "placement": {
            "source_phrase_start_frame": phrase_start_frame,
            "source_phrase_end_frame": phrase_end_frame,
            "pre_guard_frames": pre_guard_frames,
            "post_guard_frames": post_guard_frames,
            "destination_start_seconds": destination_start_seconds,
            "destination_end_seconds": destination_end_seconds,
            "destination_start_frame": round(destination_start_seconds * sample_rate),
            "destination_end_frame": round(destination_end_seconds * sample_rate),
            "capture_song_start_seconds": destination_start_seconds
            - phrase_start_frame / sample_rate,
        },
        "browser_processing": {
            "requested": requested,
            "actual": actual,
            "native_microphone_bit_depth_claimed": False,
            "encoding_description": "deterministic_pcm24_projection_of_webaudio_float32",
        },
        "authority": {
            "review_status": "unreviewed",
            "selection_authority": "none",
            "phrase_decision_created": False,
            "source_map_admission": False,
        },
        "effects": _zero_effects(),
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return validate_vocal_capture(document, state)


def validate_vocal_capture(
    capture: Mapping[str, Any], musical_state: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate a bounded capture against the exact reviewed Musical State."""

    state = validate_musical_state(musical_state)
    return validate_vocal_capture_against_state(capture, state)


__all__ = [
    "VOCAL_CAPTURE_SCHEMA",
    "create_vocal_capture",
    "validate_vocal_capture",
]
