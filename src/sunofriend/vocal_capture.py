"""Path-free evidence for one bounded browser microphone capture."""

from __future__ import annotations

import math
import re
from typing import Any, Mapping, Sequence

from .musical_state import MUSICAL_STATE_SCHEMA, validate_musical_state
from .source_receipt import document_sha256


VOCAL_CAPTURE_SCHEMA = "sunofriend.browser-vocal-capture.v1"

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ACTUAL_PROCESSING_KEYS = frozenset(
    {
        "echo_cancellation",
        "noise_suppression",
        "automatic_gain_control",
        "sample_rate",
        "channel_count",
    }
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
    document = dict(capture)
    if document.get("schema") != VOCAL_CAPTURE_SCHEMA:
        raise ValueError("unsupported vocal capture schema")
    if document.get("status") != "stored_unreviewed":
        raise ValueError("vocal capture must remain stored_unreviewed")
    _verify_hash(document)
    if set(document) != {
        "schema",
        "status",
        "method_natures",
        "binding",
        "capture",
        "phrase",
        "cue",
        "audio",
        "placement",
        "browser_processing",
        "authority",
        "effects",
        "network_used",
        "document_sha256",
    }:
        raise ValueError(
            "vocal capture contains an unsupported decision, training or private field"
        )
    if document.get("method_natures") != ["D", "H"]:
        raise ValueError("vocal capture must declare deterministic and human work")
    _validate_capture_binding_and_identity(document, state=state)
    phrase = _validate_capture_phrase_and_cue(document, state=state)
    sample_rate, frame_count = _validate_capture_audio(document)
    _validate_capture_placement(
        document, phrase=phrase, sample_rate=sample_rate, frame_count=frame_count
    )
    _validate_capture_browser_processing(document, sample_rate=sample_rate)
    _validate_capture_authority(document)
    _reject_private_or_path_fields(document)
    return document


def _validate_capture_binding_and_identity(
    document: Mapping[str, Any], *, state: Mapping[str, Any]
) -> None:
    if document.get("binding") != {
        "musical_state_schema": MUSICAL_STATE_SCHEMA,
        "musical_state_sha256": state["document_sha256"],
    }:
        raise ValueError("vocal capture does not bind this exact musical state")

    capture_row = _mapping(document.get("capture"), "capture")
    capture_id = _safe_id(capture_row.get("capture_id"), "capture_id")
    if capture_row != {
        "capture_id": capture_id,
        "source_id": f"browser-capture-{capture_id}",
        "source_class": "browser_microphone_phrase_capture",
        "scope": "bounded_phrase_with_guards",
        "common_recorded_song_zero": False,
    }:
        raise ValueError("vocal capture identity or bounded scope changed")


def _validate_capture_phrase_and_cue(
    document: Mapping[str, Any], *, state: Mapping[str, Any]
) -> Mapping[str, Any]:
    if state.get("structure", {}).get("review_status") != "reviewed":
        raise ValueError("vocal capture requires a reviewed phrase timeline")
    phrase_row = _mapping(document.get("phrase"), "phrase")
    phrase = _phrase(state, str(phrase_row.get("phrase_id", "")))
    if phrase_row != {
        "phrase_id": phrase["phrase_id"],
        "lyrics": phrase["lyrics"],
        "review_status": "reviewed",
    }:
        raise ValueError("vocal capture phrase or reviewed lyrics changed")

    cue = _mapping(document.get("cue"), "cue")
    if set(cue) != {"cue_id", "audio_sha256", "authority"}:
        raise ValueError("vocal capture cue fields changed")
    _safe_id(cue.get("cue_id"), "cue_id")
    _sha256(cue.get("audio_sha256"), "cue asset")
    if cue.get("authority") != "explicit_hash_bound_recording_cue_only":
        raise ValueError("vocal capture cue authority is invalid")
    return phrase


def _validate_capture_audio(document: Mapping[str, Any]) -> tuple[int, int]:
    audio = _mapping(document.get("audio"), "audio")
    if set(audio) != {
        "sha256",
        "bytes",
        "format",
        "subtype",
        "channels",
        "sample_rate",
        "frames",
    }:
        raise ValueError("vocal capture audio fields changed")
    _sha256(audio.get("sha256"), "capture audio")
    audio_bytes = _positive_integer(audio.get("bytes"), "audio bytes")
    sample_rate = _positive_integer(audio.get("sample_rate"), "sample rate")
    frame_count = _positive_integer(audio.get("frames"), "frame count")
    if (
        audio.get("format") != "WAV"
        or audio.get("subtype") != "PCM_24"
        or audio.get("channels") != 1
    ):
        raise ValueError("vocal capture audio must be mono WAV PCM_24")
    if audio_bytes != 44 + frame_count * 3:
        raise ValueError("vocal capture bytes must match deterministic PCM24 geometry")
    return sample_rate, frame_count


def _validate_capture_placement(
    document: Mapping[str, Any],
    *,
    phrase: Mapping[str, Any],
    sample_rate: int,
    frame_count: int,
) -> None:
    placement = _mapping(document.get("placement"), "placement")
    if set(placement) != {
        "source_phrase_start_frame",
        "source_phrase_end_frame",
        "pre_guard_frames",
        "post_guard_frames",
        "destination_start_seconds",
        "destination_end_seconds",
        "destination_start_frame",
        "destination_end_frame",
        "capture_song_start_seconds",
    }:
        raise ValueError("vocal capture placement fields changed")
    start_frame = _non_negative_integer(
        placement.get("source_phrase_start_frame"), "source phrase start frame"
    )
    end_frame = _positive_integer(
        placement.get("source_phrase_end_frame"), "source phrase end frame"
    )
    pre_guard = _non_negative_integer(
        placement.get("pre_guard_frames"), "pre guard frames"
    )
    post_guard = _non_negative_integer(
        placement.get("post_guard_frames"), "post guard frames"
    )
    destination_start = _finite(
        placement.get("destination_start_seconds"), "destination start"
    )
    destination_end = _finite(
        placement.get("destination_end_seconds"), "destination end"
    )
    capture_song_start = _finite(
        placement.get("capture_song_start_seconds"), "capture song start"
    )
    destination_start_frame = _non_negative_integer(
        placement.get("destination_start_frame"), "destination start frame"
    )
    destination_end_frame = _positive_integer(
        placement.get("destination_end_frame"), "destination end frame"
    )
    if not 0 <= start_frame < end_frame <= frame_count:
        raise ValueError("vocal capture phrase frame window is invalid")
    if start_frame != pre_guard or frame_count - end_frame != post_guard:
        raise ValueError("vocal capture guard frames do not match its source window")
    if pre_guard + post_guard <= 0:
        raise ValueError("vocal capture must retain at least one guard frame")
    if (
        pre_guard > sample_rate * 5
        or post_guard > sample_rate * 5
        or frame_count > (end_frame - start_frame) + sample_rate * 10
    ):
        raise ValueError(
            "vocal capture must stay short and bounded; full-song padding is unsupported"
        )
    tolerance = 0.5 / sample_rate + 1e-12
    if (
        abs(destination_start - float(phrase["start_seconds"])) > tolerance
        or abs(destination_end - float(phrase["end_seconds"])) > tolerance
    ):
        raise ValueError("vocal capture destination does not match reviewed phrase")
    if (
        abs(
            (end_frame - start_frame) / sample_rate
            - (destination_end - destination_start)
        )
        > tolerance
    ):
        raise ValueError(
            "vocal capture source window and destination duration disagree"
        )
    expected_capture_start = destination_start - start_frame / sample_rate
    if abs(capture_song_start - expected_capture_start) > tolerance:
        raise ValueError("vocal capture song placement is inconsistent")
    if destination_start_frame != round(
        destination_start * sample_rate
    ) or destination_end_frame != round(destination_end * sample_rate):
        raise ValueError("vocal capture destination frame geometry is inconsistent")


def _validate_capture_browser_processing(
    document: Mapping[str, Any], *, sample_rate: int
) -> None:
    browser = _mapping(document.get("browser_processing"), "browser processing")
    requested = _mapping(browser.get("requested"), "requested processing")
    expected_requested = {
        "echo_cancellation": False,
        "noise_suppression": False,
        "automatic_gain_control": False,
    }
    if requested != expected_requested:
        raise ValueError("vocal capture must request all browser processing off")
    actual = _mapping(browser.get("actual"), "actual processing")
    if not set(actual).issubset(_ACTUAL_PROCESSING_KEYS):
        raise ValueError("actual browser processing contains unsupported fields")
    _validate_actual_processing(actual)
    if "sample_rate" in actual and actual["sample_rate"] != sample_rate:
        raise ValueError("actual browser sample rate differs from capture audio")
    if browser != {
        "requested": requested,
        "actual": actual,
        "native_microphone_bit_depth_claimed": False,
        "encoding_description": "deterministic_pcm24_projection_of_webaudio_float32",
    }:
        raise ValueError("browser capture encoding declaration changed")


def _validate_capture_authority(document: Mapping[str, Any]) -> None:
    if document.get("authority") != {
        "review_status": "unreviewed",
        "selection_authority": "none",
        "phrase_decision_created": False,
        "source_map_admission": False,
    }:
        raise ValueError("vocal capture claims unsupported musical authority")
    if document.get("effects") != _zero_effects():
        raise ValueError("vocal capture cannot select, render, correct or train")
    if document.get("network_used") is not False:
        raise ValueError("vocal capture must record network_used=false")


def _phrase(state: Mapping[str, Any], phrase_id: str) -> Mapping[str, Any]:
    for row in state["structure"]["phrases"]:
        if row["phrase_id"] == phrase_id:
            return row
    raise ValueError("vocal capture phrase is unknown in musical state")


def _verify_hash(document: Mapping[str, Any]) -> None:
    expected = str(document.get("document_sha256", ""))
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if expected != document_sha256(unsigned):
        raise ValueError("vocal capture document SHA-256 does not match")


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise ValueError(f"{label} must be a safe identifier")
    return value


def _sha256(value: Any, label: str) -> str:
    text = str(value)
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return text


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _non_negative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return dict(value)


def _validate_actual_processing(actual: Mapping[str, Any]) -> None:
    for name in ("echo_cancellation", "noise_suppression", "automatic_gain_control"):
        if (
            name in actual
            and actual[name] is not None
            and not isinstance(actual[name], bool)
        ):
            raise ValueError(f"actual {name} must be boolean or null")
    if "sample_rate" in actual:
        _positive_integer(actual["sample_rate"], "actual sample rate")
    if "channel_count" in actual and actual["channel_count"] != 1:
        raise ValueError("actual channel count must be one")


def _zero_effects() -> dict[str, bool]:
    return {
        "source_mutated": False,
        "take_selected": False,
        "phrase_decision_created": False,
        "audio_comp_rendered": False,
        "pitch_correction_applied": False,
        "timing_correction_applied": False,
        "training_label_created": False,
        "training_started": False,
        "model_weights_changed": False,
    }


def _reject_private_or_path_fields(value: Any) -> None:
    forbidden = {"path", "filename", "device_id", "device_label", "private_path"}
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = str(key).casefold()
            if lowered in forbidden or lowered.endswith("_path"):
                raise ValueError(
                    "vocal capture must remain path-free and private-id-free"
                )
            _reject_private_or_path_fields(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _reject_private_or_path_fields(item)


__all__ = [
    "VOCAL_CAPTURE_SCHEMA",
    "create_vocal_capture",
    "validate_vocal_capture",
]
