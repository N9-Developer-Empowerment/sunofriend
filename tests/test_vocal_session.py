from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping

import pytest

from sunofriend.musical_state import (
    MUSICAL_STATE_SCHEMA,
    VOCAL_COMP_TIMELINE_SCHEMA,
    VOCAL_PERFORMANCE_STATE_SCHEMA,
)
from sunofriend.source_receipt import document_sha256
from sunofriend.vocal_phrase_decision import create_phrase_decision
from sunofriend.vocal_session import (
    VOCAL_SESSION_DRAFT_SCHEMA,
    VOCAL_SESSION_EVENT_SCHEMA,
    VOCAL_SESSION_SCHEMA,
    VocalSessionDraftConflictError,
    VocalSessionStore,
    build_vocal_session,
    validate_vocal_session,
)


def test_session_projection_is_path_free_neutral_and_non_authoritative() -> None:
    state = _musical_state()

    session = build_vocal_session(state)

    assert session["schema"] == VOCAL_SESSION_SCHEMA
    assert session["status"] == "in_progress_unrendered"
    assert session["binding"] == {
        "musical_state_schema": MUSICAL_STATE_SCHEMA,
        "musical_state_sha256": state["document_sha256"],
    }
    assert session["authority"] == {
        "selection_authority": "explicit_human_decision_only",
        "playback_creates_decision": False,
        "dwell_creates_decision": False,
        "draft_creates_decision": False,
    }
    assert [row["phrase_id"] for row in session["phrases"]] == [
        "phrase-001",
        "phrase-002",
    ]
    assert [row["source_id"] for row in session["sources"]] == [
        "reference-vocal-001",
        "take-001",
        "take-002",
    ]
    assert all(row["decision"] is None for row in session["phrases"])
    assert session["coverage"] == {
        "phrase_count": 2,
        "decision_count": 0,
        "remaining_phrase_count": 2,
    }
    assert session["effects"] == _zero_session_effects()
    assert session["network_used"] is False
    assert not _keys_named_path(session)
    assert not _absolute_path_values(session)
    assert validate_vocal_session(session, state) == session


def test_projection_folds_only_exact_explicit_phrase_decisions() -> None:
    state = _musical_state()
    human = create_phrase_decision(
        state,
        phrase_id="phrase-001",
        outcome="human_take",
        source_id="take-002",
        notes="Chosen only after listening in phrase context.",
    )
    unresolved = create_phrase_decision(
        state,
        phrase_id="phrase-002",
        outcome="record_again",
    )

    partial = build_vocal_session(state, [human])
    completed = build_vocal_session(state, [human, unresolved])

    assert partial["status"] == "in_progress_unrendered"
    assert partial["coverage"]["decision_count"] == 1
    assert partial["phrases"][0]["decision"] == {
        "decision_document_sha256": human["document_sha256"],
        "outcome": "human_take",
        "selected_source_id": "take-002",
        "selected_source_sha256": "5" * 64,
    }
    assert partial["phrases"][1]["decision"] is None

    assert completed["status"] == "reviewed_unrendered"
    assert completed["coverage"] == {
        "phrase_count": 2,
        "decision_count": 2,
        "remaining_phrase_count": 0,
    }
    assert completed["phrases"][1]["decision"] == {
        "decision_document_sha256": unresolved["document_sha256"],
        "outcome": "record_again",
        "selected_source_id": None,
        "selected_source_sha256": None,
    }
    assert completed["effects"] == _zero_session_effects()


def test_projection_rejects_duplicate_foreign_or_tampered_decisions() -> None:
    state = _musical_state()
    decision = create_phrase_decision(
        state,
        phrase_id="phrase-001",
        outcome="human_take",
        source_id="take-001",
    )
    with pytest.raises(ValueError, match="duplicate"):
        build_vocal_session(state, [decision, decision])

    foreign_state = deepcopy(state)
    foreign_state["clock"]["bpm"] = 101.0
    _rehash(foreign_state)
    foreign = create_phrase_decision(
        foreign_state,
        phrase_id="phrase-002",
        outcome="ai_fallback",
    )
    with pytest.raises(ValueError, match="musical.state|state.*hash|state.*SHA-256"):
        build_vocal_session(state, [decision, foreign])

    tampered = deepcopy(decision)
    tampered["outcome"] = "ai_fallback"
    with pytest.raises(ValueError, match="document.*hash|SHA-256"):
        build_vocal_session(state, [tampered])


def test_draft_is_atomic_owner_only_non_authoritative_and_revision_checked(
    tmp_path: Path,
) -> None:
    state = _musical_state()
    session = build_vocal_session(state)
    store = VocalSessionStore(tmp_path / "private-session-state")

    saved = store.save_draft(
        session,
        {
            "active_phrase_id": "phrase-002",
            "notes_by_phrase": {
                "phrase-001": "Listen again in context.",
                "phrase-002": "Try a stronger final word.",
            },
        },
        expected_revision=0,
    )

    draft_path = tmp_path / "private-session-state" / "draft.json"
    assert saved["schema"] == VOCAL_SESSION_DRAFT_SCHEMA
    assert saved["revision"] == 1
    assert saved["authority"] == "none"
    assert saved["binding"]["session_id"] == session["session_id"]
    assert saved["effects"] == _zero_session_effects()
    assert store.load_draft(session) == saved
    assert json.loads(draft_path.read_text(encoding="utf-8")) == saved
    assert os.stat(tmp_path / "private-session-state").st_mode & 0o777 == 0o700
    assert os.stat(draft_path).st_mode & 0o777 == 0o600
    assert list(draft_path.parent.glob(".draft.json.*.tmp")) == []

    # Drafts can help the reviewer resume, but cannot change musical authority.
    current = store.current_session(state)
    assert current["coverage"]["decision_count"] == 0
    assert all(row["decision"] is None for row in current["phrases"])

    with pytest.raises(VocalSessionDraftConflictError):
        store.save_draft(
            session,
            {"active_phrase_id": "phrase-001", "notes_by_phrase": {}},
            expected_revision=0,
        )
    assert store.load_draft(session) == saved


@pytest.mark.parametrize(
    "forbidden_payload",
    (
        {"active_phrase_id": "phrase-001", "outcome": "human_take"},
        {"active_phrase_id": "phrase-001", "selected_source_id": "take-001"},
        {"active_phrase_id": "phrase-001", "preferred_take": "take-001"},
        {"active_phrase_id": "phrase-001", "decision": {"outcome": "human_take"}},
    ),
)
def test_draft_rejects_decision_like_authority(
    tmp_path: Path,
    forbidden_payload: Mapping[str, Any],
) -> None:
    state = _musical_state()
    session = build_vocal_session(state)
    store = VocalSessionStore(tmp_path / "state")

    with pytest.raises(ValueError, match="draft.*decision|non-authoritative"):
        store.save_draft(session, forbidden_payload, expected_revision=0)

    assert store.load_draft(session) is None
    assert store.events(session["session_id"]) == []


def test_store_appends_exact_decisions_and_reopens_without_reinterpreting(
    tmp_path: Path,
) -> None:
    state = _musical_state()
    session = build_vocal_session(state)
    decision = create_phrase_decision(
        state,
        phrase_id="phrase-001",
        outcome="human_take",
        source_id="take-001",
    )
    store = VocalSessionStore(tmp_path / "state")

    event = store.append(
        session,
        {"event_type": "phrase_decision", "decision": decision},
    )

    assert event["schema"] == VOCAL_SESSION_EVENT_SCHEMA
    assert event["event_type"] == "phrase_decision"
    assert event["session_id"] == session["session_id"]
    assert event["musical_state_sha256"] == state["document_sha256"]
    assert event["decision_document_sha256"] == decision["document_sha256"]
    assert event["decision"] == decision
    assert store.events(session["session_id"]) == [event]
    assert (
        store.current_session(state)["phrases"][0]["decision"]["selected_source_id"]
        == "take-001"
    )

    reopened = VocalSessionStore(tmp_path / "state")
    assert reopened.events(session["session_id"]) == [event]
    assert reopened.current_session(state) == store.current_session(state)


def test_store_is_append_only_and_playback_or_dwell_cannot_create_decisions(
    tmp_path: Path,
) -> None:
    state = _musical_state()
    session = build_vocal_session(state)
    store = VocalSessionStore(tmp_path / "state")

    for event_type in ("playback", "audition", "dwell", "phrase_viewed"):
        with pytest.raises(ValueError, match="explicit.*decision|event_type"):
            store.append(
                session,
                {
                    "event_type": event_type,
                    "phrase_id": "phrase-001",
                    "source_id": "take-001",
                    "seconds": 120.0,
                },
            )

    assert store.events(session["session_id"]) == []
    assert store.current_session(state)["coverage"]["decision_count"] == 0

    decision = create_phrase_decision(
        state,
        phrase_id="phrase-001",
        outcome="human_take",
        source_id="take-001",
    )
    store.append(
        session,
        {"event_type": "phrase_decision", "decision": decision},
    )
    database = tmp_path / "state" / "vocal-session.sqlite3"
    for path in database.parent.glob("vocal-session.sqlite3*"):
        assert os.stat(path).st_mode & 0o777 == 0o600
    for statement in (
        "UPDATE vocal_session_events SET event_type = 'playback'",
        "DELETE FROM vocal_session_events",
    ):
        with sqlite3.connect(database) as connection:
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                connection.execute(statement)


def _musical_state() -> dict[str, Any]:
    phrases = [
        {
            "phrase_id": "phrase-001",
            "start_seconds": 0.2,
            "end_seconds": 1.4,
            "lyrics": "And tell myself those comforting lies",
        },
        {
            "phrase_id": "phrase-002",
            "start_seconds": 1.6,
            "end_seconds": 3.8,
            "lyrics": "Cause the heart sees exactly what it wants to see",
        },
    ]
    state: dict[str, Any] = {
        "schema": MUSICAL_STATE_SCHEMA,
        "status": "complete_unreviewed_no_selection",
        "state_scope": "audio_native_vocal_foundation",
        "method_natures": ["D", "H"],
        "clock": {
            "origin": "common_recorded_song_zero",
            "bpm": 96.0,
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
            "phrases": phrases,
        },
        "vocal_performance_state": {
            "schema": VOCAL_PERFORMANCE_STATE_SCHEMA,
            "processing_chain": "dry",
            "reference": {
                "source_id": "reference-vocal-001",
                "source_class": "reference_vocal",
                "audio": _file_record(
                    "SOURCES/reference/reference-vocal.wav", "3" * 64
                ),
                "recorded_zero_offset_seconds": 0.0,
                "authority": "phrasing_and_contour_reference_only",
            },
            "takes": [
                _take("take-001", "4" * 64),
                _take("take-002", "5" * 64),
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
            "sample_rate": 44_100,
            "channels": 1,
            "frames": 220_500,
            "duration_seconds": 5.0,
        },
        "recorded_zero_offset_seconds": 0.0,
        "review_status": "not_reviewed_in_this_state",
    }


def _file_record(path: str, sha256: str) -> dict[str, Any]:
    return {"path": path, "sha256": sha256, "bytes": 1_024}


def _rehash(document: dict[str, Any]) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)


def _zero_session_effects() -> dict[str, bool]:
    return {
        "human_phrase_decision_created": False,
        "audio_comp_rendered": False,
        "join_created": False,
        "pitch_correction_applied": False,
        "timing_correction_applied": False,
        "training_label_created": False,
    }


def _keys_named_path(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            "path" in str(key).casefold() or _keys_named_path(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_keys_named_path(item) for item in value)
    return False


def _absolute_path_values(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_absolute_path_values(item) for item in value.values())
    if isinstance(value, list):
        return any(_absolute_path_values(item) for item in value)
    if isinstance(value, str):
        return value.startswith(("/", "\\\\")) or (
            len(value) >= 3 and value[1:3] in {":/", ":\\"}
        )
    return False
