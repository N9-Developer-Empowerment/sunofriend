from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pytest

from sunofriend.musical_state import (
    VOCAL_PERFORMANCE_STATE_SCHEMA,
    VOCAL_PERFORMANCE_STATE_SCHEMA_V3,
    validate_musical_state,
)
from sunofriend.source_receipt import canonical_json_bytes, document_sha256
from sunofriend.vocal_capture import VOCAL_CAPTURE_SCHEMA
from sunofriend.vocal_phrase_decision import (
    create_phrase_decision,
    create_vocal_source_map,
)
from sunofriend.vocal_session import build_vocal_session
from sunofriend.vocal_session_server import create_vocal_session_server
from tests.test_vocal_capture_admission import _admit, _fixture
from tests.test_vocal_session import _musical_state


SAMPLE_RATE = 44_100
CAPTURE_ID = "browser-capture-attempt-001"
CAPTURE_SHA256 = "9" * 64
CAPTURE_RECEIPT_SHA256 = "8" * 64
PRE_GUARD_FRAMES = SAMPLE_RATE // 20
POST_GUARD_FRAMES = SAMPLE_RATE // 20


def test_v2_state_and_full_take_artifacts_keep_their_existing_shape() -> None:
    state = _musical_state()
    original_bytes = canonical_json_bytes(state)

    validated = validate_musical_state(state)
    decision = create_phrase_decision(
        state,
        phrase_id="phrase-001",
        outcome="human_take",
        source_id="take-001",
    )
    source_map = create_vocal_source_map(state, [decision])
    session = build_vocal_session(state)

    assert VOCAL_PERFORMANCE_STATE_SCHEMA == "sunofriend.vocal-performance-state.v2"
    assert validated == state
    assert canonical_json_bytes(validated) == original_bytes
    assert "phrase_captures" not in validated["vocal_performance_state"]
    assert decision["selected_source_class"] == "human_vocal_take"
    assert set(decision) == {
        "schema",
        "status",
        "method_natures",
        "binding",
        "phrase",
        "outcome",
        "selected_source_id",
        "selected_source_class",
        "selected_source_sha256",
        "review",
        "authority_limits",
        "training",
        "effects",
        "network_used",
        "document_sha256",
    }
    assert source_map["segments"][0]["source_start_seconds"] == 0.2
    assert source_map["segments"][0]["source_end_seconds"] == 1.4
    assert set(source_map["segments"][0]) == {
        "phrase_id",
        "decision_document_sha256",
        "outcome",
        "destination_start_seconds",
        "destination_end_seconds",
        "source_id",
        "source_class",
        "source_audio_sha256",
        "source_start_seconds",
        "source_end_seconds",
        "join_status",
        "correction_status",
    }
    assert [row["source_id"] for row in session["sources"]] == [
        "reference-vocal-001",
        "take-001",
        "take-002",
    ]
    assert all(
        set(row)
        == {"source_id", "source_class", "label", "audio_sha256", "audio_bytes"}
        for row in session["sources"]
    )
    assert all(
        set(row) == {"phrase_id", "start_seconds", "end_seconds", "lyrics", "decision"}
        for row in session["phrases"]
    )


def test_v3_dual_read_preserves_capture_local_identity_without_paths() -> None:
    state = _v3_state()

    validated = validate_musical_state(state)
    session = build_vocal_session(state)

    assert validated == state
    assert validated["vocal_performance_state"]["schema"] == (
        VOCAL_PERFORMANCE_STATE_SCHEMA_V3
    )
    capture = validated["vocal_performance_state"]["phrase_captures"][0]
    assert capture["source_id"] == CAPTURE_ID
    assert capture["source_class"] == "human_vocal_phrase_capture"
    assert capture["phrase"]["phrase_id"] == "phrase-001"
    assert "recorded_zero_offset_seconds" not in capture

    projected = next(
        row for row in session["sources"] if row["source_id"] == CAPTURE_ID
    )
    assert projected == {
        "source_id": CAPTURE_ID,
        "source_class": "human_vocal_phrase_capture",
        "label": "Browser attempt 001",
        "audio_sha256": CAPTURE_SHA256,
        "audio_bytes": capture["audio"]["bytes"],
        "bound_phrase_id": "phrase-001",
    }
    assert not _keys_named_path(session)
    assert all(row["decision"] is None for row in session["phrases"])
    assert session["coverage"]["decision_count"] == 0
    assert not any(session["effects"].values())
    assert not _keys_named_like_automatic_choice(session)


def test_phrase_capture_can_be_selected_only_for_its_bound_phrase() -> None:
    state = _v3_state()

    decision = create_phrase_decision(
        state,
        phrase_id="phrase-001",
        outcome="human_take",
        source_id=CAPTURE_ID,
        notes="Explicitly chosen after listening in phrase context.",
    )

    assert decision["outcome"] == "human_take"
    assert decision["selected_source_id"] == CAPTURE_ID
    assert decision["selected_source_class"] == "human_vocal_phrase_capture"
    assert decision["selected_source_sha256"] == CAPTURE_SHA256
    assert decision["training"]["pairwise_labels"] == []
    assert decision["training"]["inferred_labels"] == []
    assert decision["training"]["training_eligible"] is False

    with pytest.raises(
        ValueError, match="bound.*phrase|phrase.*capture|capture.*phrase"
    ):
        create_phrase_decision(
            state,
            phrase_id="phrase-002",
            outcome="human_take",
            source_id=CAPTURE_ID,
        )


def test_source_map_uses_capture_local_frames_and_reviewed_song_destination() -> None:
    state = _v3_state()
    capture = state["vocal_performance_state"]["phrase_captures"][0]
    placement = capture["placement"]
    decision = create_phrase_decision(
        state,
        phrase_id="phrase-001",
        outcome="human_take",
        source_id=CAPTURE_ID,
    )

    source_map = create_vocal_source_map(state, [decision])
    segment = source_map["segments"][0]

    assert segment["destination_start_seconds"] == 0.2
    assert segment["destination_end_seconds"] == 1.4
    assert segment["source_start_frame"] == placement["source_phrase_start_frame"]
    assert segment["source_end_frame"] == placement["source_phrase_end_frame"]
    assert segment["source_start_seconds"] == pytest.approx(
        placement["source_phrase_start_frame"] / SAMPLE_RATE
    )
    assert segment["source_end_seconds"] == pytest.approx(
        placement["source_phrase_end_frame"] / SAMPLE_RATE
    )
    assert segment["source_start_seconds"] != segment["destination_start_seconds"]
    assert segment["source_class"] == "human_vocal_phrase_capture"
    assert segment["source_audio_sha256"] == CAPTURE_SHA256
    assert source_map["training"] == {
        "pairwise_labels": [],
        "inferred_labels": [],
        "training_eligible": False,
    }
    assert source_map["authority"]["automatic_fill"] is False
    assert source_map["effects"]["audio_comp_rendered"] is False


def test_v3_capture_cannot_claim_common_zero_or_invalid_phrase_geometry() -> None:
    common_zero = _v3_state()
    common_zero["vocal_performance_state"]["phrase_captures"][0][
        "recorded_zero_offset_seconds"
    ] = 0.0
    _rehash(common_zero)
    with pytest.raises(ValueError, match="common.*zero|recorded|capture.*field"):
        validate_musical_state(common_zero)

    wrong_phrase = _v3_state()
    wrong_phrase["vocal_performance_state"]["phrase_captures"][0]["phrase"][
        "phrase_id"
    ] = "phrase-does-not-exist"
    _rehash(wrong_phrase)
    with pytest.raises(ValueError, match="phrase"):
        validate_musical_state(wrong_phrase)

    changed_guard = _v3_state()
    changed_guard["vocal_performance_state"]["phrase_captures"][0]["placement"][
        "pre_guard_frames"
    ] += 1
    _rehash(changed_guard)
    with pytest.raises(ValueError, match="guard|frame|placement"):
        validate_musical_state(changed_guard)


def test_loopback_session_serves_capture_on_its_source_local_window(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    out_dir = tmp_path / "derived"
    state = _admit(fixture, out_dir)
    capture = state["vocal_performance_state"]["phrase_captures"][0]
    server = create_vocal_session_server(
        out_dir / "musical-state.json",
        state_dir=tmp_path / "session-state",
        token="t" * 48,
    )
    try:
        browser = server.browser_state()
        projected = next(
            row
            for row in browser["sources"]
            if row["source_id"] == capture["source_id"]
        )
        sample_rate = capture["audio_properties"]["sample_rate"]
        assert projected["bound_phrase_id"] == capture["phrase"]["phrase_id"]
        assert projected["playback_start_seconds"] == pytest.approx(
            capture["placement"]["source_phrase_start_frame"] / sample_rate
        )
        assert projected["playback_end_seconds"] == pytest.approx(
            capture["placement"]["source_phrase_end_frame"] / sample_rate
        )
        assert not _keys_named_path(browser["session"])
    finally:
        server.server_close()


def _v3_state() -> dict[str, Any]:
    state = _musical_state()
    parent_sha256 = state["document_sha256"]
    phrase = state["structure"]["phrases"][0]
    phrase_frames = round(
        (phrase["end_seconds"] - phrase["start_seconds"]) * SAMPLE_RATE
    )
    capture_frames = PRE_GUARD_FRAMES + phrase_frames + POST_GUARD_FRAMES
    state["vocal_performance_state"]["schema"] = VOCAL_PERFORMANCE_STATE_SCHEMA_V3
    state["vocal_performance_state"]["phrase_captures"] = [
        {
            "source_id": CAPTURE_ID,
            "source_class": "human_vocal_phrase_capture",
            "label": "Browser attempt 001",
            "audio": {
                "path": f"SOURCES/captures/{CAPTURE_ID}.wav",
                "sha256": CAPTURE_SHA256,
                "bytes": 44 + capture_frames * 3,
            },
            "audio_properties": {
                "format": "WAV",
                "subtype": "PCM_24",
                "sample_rate": SAMPLE_RATE,
                "channels": 1,
                "frames": capture_frames,
                "duration_seconds": capture_frames / SAMPLE_RATE,
            },
            "capture_receipt": {
                "schema": VOCAL_CAPTURE_SCHEMA,
                "document_sha256": CAPTURE_RECEIPT_SHA256,
                "artifact": {
                    "path": (f"RECEIPTS/vocal-capture-{CAPTURE_RECEIPT_SHA256}.json"),
                    "sha256": "7" * 64,
                    "bytes": 1_024,
                },
            },
            "phrase": {
                "phrase_id": phrase["phrase_id"],
                "lyrics": phrase["lyrics"],
                "review_status": "reviewed",
            },
            "placement": {
                "source_phrase_start_frame": PRE_GUARD_FRAMES,
                "source_phrase_end_frame": PRE_GUARD_FRAMES + phrase_frames,
                "pre_guard_frames": PRE_GUARD_FRAMES,
                "post_guard_frames": POST_GUARD_FRAMES,
                "destination_start_seconds": phrase["start_seconds"],
                "destination_end_seconds": phrase["end_seconds"],
                "destination_start_frame": round(phrase["start_seconds"] * SAMPLE_RATE),
                "destination_end_frame": round(phrase["end_seconds"] * SAMPLE_RATE),
                "capture_song_start_seconds": phrase["start_seconds"]
                - PRE_GUARD_FRAMES / SAMPLE_RATE,
            },
            "review_status": "stored_unreviewed",
            "authority": {
                "review_status": "unreviewed",
                "selection_authority": "none",
                "phrase_decision_created": False,
                "source_map_admission": False,
            },
        }
    ]
    state["lineage"] = {
        "operation": "admit_vocal_phrase_capture",
        "parent": {
            "schema": state["schema"],
            "document_sha256": parent_sha256,
            "manifest": {
                "path": f"LINEAGE/musical-state-{parent_sha256}.json",
                "sha256": "6" * 64,
                "bytes": 2_048,
            },
        },
        "admitted_capture": {
            "schema": VOCAL_CAPTURE_SCHEMA,
            "document_sha256": CAPTURE_RECEIPT_SHA256,
            "audio_sha256": CAPTURE_SHA256,
        },
    }
    _rehash(state)
    return state


def _rehash(document: dict[str, Any]) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)


def _keys_named_path(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            "path" in str(key).casefold() or _keys_named_path(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_keys_named_path(item) for item in value)
    return False


def _keys_named_like_automatic_choice(value: Any) -> bool:
    forbidden = {"score", "rank", "preferred", "automatic_choice", "selected"}
    if isinstance(value, Mapping):
        return any(
            str(key).casefold() in forbidden or _keys_named_like_automatic_choice(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_keys_named_like_automatic_choice(item) for item in value)
    return False
