from __future__ import annotations

from copy import deepcopy
import math
from typing import Any, Callable, Mapping

import pytest

from sunofriend.musical_state import (
    MUSICAL_STATE_SCHEMA,
    VOCAL_COMP_TIMELINE_SCHEMA,
    VOCAL_PERFORMANCE_STATE_SCHEMA,
)
from sunofriend.source_receipt import document_sha256
from sunofriend.vocal_capture import (
    VOCAL_CAPTURE_SCHEMA,
    create_vocal_capture,
    validate_vocal_capture,
)


SAMPLE_RATE = 44_100
PHRASE_ID = "cause-the-heart-sees-exactly-what-it-wants-to-see"
PHRASE_START = 47.62
PHRASE_END = 56.12
PHRASE_START_FRAME = round(PHRASE_START * SAMPLE_RATE)
PHRASE_END_FRAME = round(PHRASE_END * SAMPLE_RATE)
PHRASE_FRAMES = PHRASE_END_FRAME - PHRASE_START_FRAME
PRE_GUARD_FRAMES = SAMPLE_RATE // 2
POST_GUARD_FRAMES = SAMPLE_RATE // 2
CAPTURE_FRAMES = PRE_GUARD_FRAMES + PHRASE_FRAMES + POST_GUARD_FRAMES
CAPTURE_BYTES = 44 + (CAPTURE_FRAMES * 3)


def test_short_browser_capture_binds_state_phrase_cue_audio_and_placement() -> None:
    state = _musical_state()

    capture = _capture(state)

    assert capture["schema"] == VOCAL_CAPTURE_SCHEMA
    assert capture["status"] == "stored_unreviewed"
    assert capture["method_natures"] == ["D", "H"]
    assert capture["binding"]["musical_state_sha256"] == state["document_sha256"]
    assert capture["capture"] == {
        "capture_id": "attempt-001",
        "source_id": "browser-capture-attempt-001",
        "source_class": "browser_microphone_phrase_capture",
        "scope": "bounded_phrase_with_guards",
        "common_recorded_song_zero": False,
    }
    assert capture["phrase"] == {
        "phrase_id": PHRASE_ID,
        "lyrics": "'Cause the heart sees exactly what it wants to see",
        "review_status": "reviewed",
    }
    assert capture["cue"] == {
        "cue_id": "backing-plus-reviewed-melody",
        "audio_sha256": "a" * 64,
        "authority": "explicit_hash_bound_recording_cue_only",
    }
    assert capture["audio"] == {
        "sha256": "b" * 64,
        "bytes": CAPTURE_BYTES,
        "format": "WAV",
        "subtype": "PCM_24",
        "channels": 1,
        "sample_rate": SAMPLE_RATE,
        "frames": CAPTURE_FRAMES,
    }
    assert capture["placement"] == {
        "source_phrase_start_frame": PRE_GUARD_FRAMES,
        "source_phrase_end_frame": PRE_GUARD_FRAMES + PHRASE_FRAMES,
        "pre_guard_frames": PRE_GUARD_FRAMES,
        "post_guard_frames": POST_GUARD_FRAMES,
        "destination_start_seconds": PHRASE_START,
        "destination_end_seconds": PHRASE_END,
        "destination_start_frame": PHRASE_START_FRAME,
        "destination_end_frame": PHRASE_END_FRAME,
        "capture_song_start_seconds": PHRASE_START - PRE_GUARD_FRAMES / SAMPLE_RATE,
    }
    assert capture["browser_processing"]["requested"] == _requested_processing()
    assert capture["browser_processing"]["actual"] == _actual_processing()
    assert capture["browser_processing"]["native_microphone_bit_depth_claimed"] is False
    assert (
        capture["browser_processing"]["encoding_description"]
        == "deterministic_pcm24_projection_of_webaudio_float32"
    )
    assert capture["authority"] == {
        "review_status": "unreviewed",
        "selection_authority": "none",
        "phrase_decision_created": False,
        "source_map_admission": False,
    }
    assert capture["effects"] == {
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
    assert capture["network_used"] is False
    assert not _keys_named_path_or_filename(capture)
    assert validate_vocal_capture(capture, state) == capture


def test_actual_browser_processing_is_recorded_as_evidence_not_authority() -> None:
    state = _musical_state()
    overridden = {
        "echo_cancellation": True,
        "noise_suppression": True,
        "automatic_gain_control": True,
    }

    capture = _capture(state, actual_processing=overridden)

    assert capture["browser_processing"]["requested"] == _requested_processing()
    assert capture["browser_processing"]["actual"] == overridden
    assert capture["authority"]["selection_authority"] == "none"
    assert capture["status"] == "stored_unreviewed"
    assert not any(capture["effects"].values())


@pytest.mark.parametrize(
    ("requested", "message"),
    (
        (
            {
                "echo_cancellation": True,
                "noise_suppression": False,
                "automatic_gain_control": False,
            },
            "echo|processing",
        ),
        (
            {
                "echo_cancellation": False,
                "noise_suppression": True,
                "automatic_gain_control": False,
            },
            "noise|processing",
        ),
        (
            {
                "echo_cancellation": False,
                "noise_suppression": False,
                "automatic_gain_control": True,
            },
            "gain|processing",
        ),
    ),
)
def test_capture_requires_browser_processing_to_be_requested_off(
    requested: dict[str, bool], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _capture(_musical_state(), requested_processing=requested)


def test_capture_rejects_unknown_or_unreviewed_phrase() -> None:
    state = _musical_state()
    with pytest.raises(ValueError, match="phrase.*musical state|unknown.*phrase"):
        _capture(state, phrase_id="not-a-reviewed-phrase")

    unreviewed = deepcopy(state)
    unreviewed["structure"]["review_status"] = "automatic_unreviewed"
    _rehash(unreviewed)
    with pytest.raises(ValueError, match="reviewed"):
        _capture(unreviewed)


@pytest.mark.parametrize(
    ("override", "message"),
    (
        ({"cue_asset_sha256": "not-a-sha"}, "cue.*SHA-256|cue.*hash"),
        ({"audio_sha256": "f" * 63}, "audio.*SHA-256|audio.*hash"),
        ({"audio_bytes": 0}, "bytes"),
        ({"sample_rate": 0}, "sample.rate"),
        ({"frame_count": 0}, "frame"),
        ({"destination_start_seconds": math.nan}, "finite"),
        ({"destination_end_seconds": math.inf}, "finite"),
    ),
)
def test_capture_creation_rejects_invalid_hash_geometry_or_nonfinite_values(
    override: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _capture(_musical_state(), **override)


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda row: row["placement"].update(
                {
                    "source_phrase_end_frame": row["placement"][
                        "source_phrase_end_frame"
                    ]
                    + 1
                }
            ),
            "duration|geometry|window",
        ),
        (
            lambda row: row["placement"].update(
                {
                    "source_phrase_start_frame": row["placement"][
                        "source_phrase_start_frame"
                    ]
                    + 1
                }
            ),
            "guard|geometry|window",
        ),
        (
            lambda row: row["placement"].update(
                {"pre_guard_frames": row["placement"]["pre_guard_frames"] + 1}
            ),
            "guard|geometry|window",
        ),
        (
            lambda row: row["placement"].update(
                {"post_guard_frames": row["placement"]["post_guard_frames"] + 1}
            ),
            "guard|geometry|frame",
        ),
        (
            lambda row: row["placement"].update(
                {
                    "destination_start_frame": row["placement"].get(
                        "destination_start_frame", PHRASE_START_FRAME
                    )
                    + 1
                }
            ),
            "destination|geometry|frame|placement fields",
        ),
        (
            lambda row: row["placement"].update(
                {
                    "destination_end_seconds": row["placement"][
                        "destination_end_seconds"
                    ]
                    + (0.51 / SAMPLE_RATE)
                }
            ),
            "half.*sample|duration|geometry|destination|reviewed phrase",
        ),
        (
            lambda row: row["audio"].update({"frames": row["audio"]["frames"] + 1}),
            "guard|frame|geometry",
        ),
        (
            lambda row: row["audio"].update({"bytes": row["audio"]["bytes"] + 3}),
            "bytes|PCM24|geometry",
        ),
    ),
    ids=(
        "source-duration",
        "source-start-vs-pre-guard",
        "pre-guard",
        "post-guard",
        "destination-frame",
        "half-sample-tolerance",
        "total-frames",
        "pcm24-bytes",
    ),
)
def test_capture_validation_rejects_source_and_destination_geometry_changes(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    state = _musical_state()
    changed = _capture(state)
    mutate(changed)
    _rehash(changed)

    with pytest.raises(ValueError, match=message):
        validate_vocal_capture(changed, state)


def test_capture_is_bounded_and_rejects_full_song_project_zero_semantics() -> None:
    state = _musical_state()
    project_frames = round(280.781587 * SAMPLE_RATE)
    padded_before = PHRASE_START_FRAME
    padded_after = project_frames - padded_before - PHRASE_FRAMES

    with pytest.raises(ValueError, match="short|guard|padded|project.zero|bounded"):
        _capture(
            state,
            frame_count=project_frames,
            audio_bytes=44 + project_frames * 3,
            phrase_start_frame=padded_before,
            phrase_end_frame=padded_before + PHRASE_FRAMES,
            pre_guard_frames=padded_before,
            post_guard_frames=padded_after,
        )

    changed = _capture(state)
    changed["capture"]["scope"] = "full_song_project_zero"
    _rehash(changed)
    with pytest.raises(ValueError, match="short|project.zero|scope"):
        validate_vocal_capture(changed, state)

    changed = _capture(state)
    changed["capture"]["recorded_zero_offset_seconds"] = 0.0
    _rehash(changed)
    with pytest.raises(
        ValueError, match="common.zero|project.zero|field|short|recorded|identity"
    ):
        validate_vocal_capture(changed, state)


def test_capture_is_path_free_and_rejects_client_paths_or_filenames() -> None:
    state = _musical_state()
    for field, value in (
        ("path", "/Users/private/voice.wav"),
        ("client_filename", "../../../private-voice.wav"),
        ("filename", "voice.wav"),
    ):
        changed = _capture(state)
        changed["capture"][field] = value
        _rehash(changed)
        with pytest.raises(ValueError, match="path|filename|portable|identity"):
            validate_vocal_capture(changed, state)


def test_capture_detects_document_audio_and_state_binding_tampering() -> None:
    state = _musical_state()
    capture = _capture(state)

    changed_without_rehash = deepcopy(capture)
    changed_without_rehash["audio"]["sha256"] = "c" * 64
    with pytest.raises(ValueError, match="document SHA-256|document.*hash"):
        validate_vocal_capture(changed_without_rehash, state)

    changed_audio = deepcopy(capture)
    changed_audio["audio"]["sha256"] = "c" * 64
    _rehash(changed_audio)
    assert validate_vocal_capture(changed_audio, state) == changed_audio

    stale_state = deepcopy(state)
    stale_state["clock"]["bpm"] = 97.0
    _rehash(stale_state)
    with pytest.raises(ValueError, match="musical.state|state.*SHA-256|state.*hash"):
        validate_vocal_capture(capture, stale_state)


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda row: row.update({"status": "selected_for_comp"}),
            "stored_unreviewed|status",
        ),
        (
            lambda row: row.update({"selected_source": True}),
            "decision|selected|field|authority",
        ),
        (
            lambda row: row["authority"].update({"selection_authority": "capture"}),
            "authority|selected",
        ),
        (
            lambda row: row["effects"].update({"selection_created": True}),
            "effect|selection|select",
        ),
        (
            lambda row: row["effects"].update({"audio_comp_rendered": True}),
            "effect|render",
        ),
        (
            lambda row: row["effects"].update({"pitch_correction_applied": True}),
            "effect|correction|correct",
        ),
        (
            lambda row: row.setdefault("training", {}).update(
                {"training_eligible": True}
            ),
            "training",
        ),
    ),
)
def test_unreviewed_capture_rejects_implicit_decisions_or_product_effects(
    mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    state = _musical_state()
    changed = _capture(state)
    mutate(changed)
    _rehash(changed)

    with pytest.raises(ValueError, match=message):
        validate_vocal_capture(changed, state)


def _capture(
    state: Mapping[str, Any],
    **overrides: Any,
) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "capture_id": "attempt-001",
        "phrase_id": PHRASE_ID,
        "cue_id": "backing-plus-reviewed-melody",
        "cue_asset_sha256": "a" * 64,
        "audio_sha256": "b" * 64,
        "audio_bytes": CAPTURE_BYTES,
        "sample_rate": SAMPLE_RATE,
        "frame_count": CAPTURE_FRAMES,
        "phrase_start_frame": PRE_GUARD_FRAMES,
        "phrase_end_frame": PRE_GUARD_FRAMES + PHRASE_FRAMES,
        "destination_start_seconds": PHRASE_START,
        "destination_end_seconds": PHRASE_END,
        "pre_guard_frames": PRE_GUARD_FRAMES,
        "post_guard_frames": POST_GUARD_FRAMES,
        "requested_processing": _requested_processing(),
        "actual_processing": _actual_processing(),
    }
    arguments.update(overrides)
    return create_vocal_capture(state, **arguments)


def _requested_processing() -> dict[str, bool]:
    return {
        "echo_cancellation": False,
        "noise_suppression": False,
        "automatic_gain_control": False,
    }


def _actual_processing() -> dict[str, bool]:
    return {
        "echo_cancellation": False,
        "noise_suppression": False,
        "automatic_gain_control": False,
    }


def _musical_state() -> dict[str, Any]:
    state: dict[str, Any] = {
        "schema": MUSICAL_STATE_SCHEMA,
        "status": "complete_unreviewed_no_selection",
        "state_scope": "audio_native_vocal_foundation",
        "method_natures": ["D", "H"],
        "clock": {
            "origin": "common_recorded_song_zero",
            "bpm": 86.00005160003096,
            "tuning_hz": 440.0,
        },
        "authorization": {
            "rights_category": "owned",
            "rights_confirmed": True,
            "common_recorded_zero_confirmed": True,
        },
        "lyrics": {
            "canonical": _file_record("LYRICS/lyrics.txt", "1" * 64),
            "authority": "user_supplied_canonical",
            "automatic_rewrite_permitted": False,
        },
        "structure": {
            "phrase_timeline": _file_record(
                "TIMELINE/reviewed-phrase-timeline.json", "2" * 64
            ),
            "phrase_timeline_schema": VOCAL_COMP_TIMELINE_SCHEMA,
            "review_status": "reviewed",
            "phrases": [
                {
                    "phrase_id": PHRASE_ID,
                    "start_seconds": PHRASE_START,
                    "end_seconds": PHRASE_END,
                    "lyrics": "'Cause the heart sees exactly what it wants to see",
                }
            ],
        },
        "vocal_performance_state": {
            "schema": VOCAL_PERFORMANCE_STATE_SCHEMA,
            "processing_chain": "dry",
            "reference": None,
            "takes": [
                _take("take-001", "3" * 64),
                _take("take-002", "4" * 64),
            ],
            "continuous_f0_evidence": [],
            "lyric_phoneme_evidence": [],
            "non_pitched_event_evidence": [],
            "signal_quality_evidence": [],
            "explicit_phrase_decisions": [],
            "edit_maps": [],
            "correction_derivatives": [],
            "selection_authority": "human_only",
        },
        "optional_derived_evidence": {"midi": [], "notes": []},
        "training": {
            "explicit_labels": [],
            "training_eligible": False,
            "reason": "no explicit phrase comparison decision in this state",
        },
        "network_used": False,
        "effects": {
            "source_mutated": False,
            "lyrics_mutated": False,
            "selection_created": False,
            "human_decision_created": False,
            "audio_comp_rendered": False,
            "pitch_correction_applied": False,
            "training_started": False,
            "model_weights_changed": False,
            "remix_rendered": False,
        },
    }
    _rehash(state)
    return state


def _take(source_id: str, sha256: str) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "source_class": "human_vocal_take",
        "label": f"{source_id}.wav",
        "audio": _file_record(f"SOURCES/takes/{source_id}.wav", sha256),
        "audio_properties": {
            "format": "WAV",
            "subtype": "PCM_24",
            "sample_rate": SAMPLE_RATE,
            "channels": 1,
            "frames": round(280.781587 * SAMPLE_RATE),
            "duration_seconds": 280.781587,
        },
        "recorded_zero_offset_seconds": 0.0,
        "review_status": "not_reviewed_in_this_state",
    }


def _file_record(path: str, sha256: str) -> dict[str, Any]:
    return {"path": path, "bytes": 128, "sha256": sha256}


def _keys_named_path_or_filename(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).casefold() in {
                "path",
                "absolute_path",
                "filename",
                "client_filename",
            }:
                found.append(str(item))
            found.extend(_keys_named_path_or_filename(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_keys_named_path_or_filename(item))
    return found


def _rehash(document: dict[str, Any]) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)
