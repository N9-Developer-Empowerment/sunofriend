from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

import pytest

from sunofriend.musical_state import (
    MUSICAL_STATE_SCHEMA,
    VOCAL_COMP_TIMELINE_SCHEMA,
    VOCAL_PERFORMANCE_STATE_SCHEMA,
)
from sunofriend.source_receipt import document_sha256
from sunofriend.vocal_phrase_decision import (
    VOCAL_PHRASE_DECISION_SCHEMA,
    VOCAL_SOURCE_MAP_SCHEMA,
    create_phrase_decision,
    create_vocal_source_map,
    validate_phrase_decision,
    validate_vocal_source_map,
)


@pytest.mark.parametrize(
    ("phrase_id", "outcome", "source_id", "expected_source_id"),
    (
        ("phrase-human", "human_take", "take-001", "take-001"),
        ("phrase-ai", "ai_fallback", None, "reference-vocal-001"),
        ("phrase-retry", "record_again", None, None),
        ("phrase-none", "no_acceptable_candidate", None, None),
    ),
)
def test_explicit_phrase_outcomes_bind_reviewed_state_and_exact_source(
    phrase_id: str,
    outcome: str,
    source_id: str | None,
    expected_source_id: str | None,
) -> None:
    state = _musical_state()

    decision = create_phrase_decision(
        state,
        phrase_id=phrase_id,
        outcome=outcome,
        source_id=source_id,
        notes="Explicitly chosen after listening in phrase context.",
    )

    assert decision["schema"] == VOCAL_PHRASE_DECISION_SCHEMA
    assert decision["status"] == "complete_human_decision"
    assert decision["method_natures"] == ["H"]
    assert decision["binding"]["musical_state_sha256"] == state["document_sha256"]
    assert decision["phrase"]["phrase_id"] == phrase_id
    assert decision["phrase"]["review_status"] == "reviewed"
    assert decision["outcome"] == outcome
    assert decision["selected_source_id"] == expected_source_id
    if expected_source_id is None:
        assert decision["selected_source_sha256"] is None
    else:
        assert decision["selected_source_sha256"] == _source_hash(
            state, expected_source_id
        )
    assert decision["training"]["pairwise_labels"] == []
    assert decision["training"]["inferred_labels"] == []
    assert decision["authority_limits"] == {
        "comp_render_authorized": False,
        "pitch_correction_authorized": False,
        "timing_correction_authorized": False,
        "word_level_splice_authorized": False,
    }
    assert decision["effects"]["human_phrase_decision_created"] is True
    assert decision["effects"]["audio_comp_rendered"] is False
    assert decision["effects"]["pitch_correction_applied"] is False
    assert decision["effects"]["timing_correction_applied"] is False
    assert not _keys_named_path(decision)
    assert validate_phrase_decision(decision, state) == decision


def test_source_map_is_path_free_unrendered_and_preserves_all_human_outcomes() -> None:
    state = _musical_state()
    decisions = [
        create_phrase_decision(
            state,
            phrase_id="phrase-human",
            outcome="human_take",
            source_id="take-002",
        ),
        create_phrase_decision(
            state,
            phrase_id="phrase-ai",
            outcome="ai_fallback",
        ),
        create_phrase_decision(
            state,
            phrase_id="phrase-retry",
            outcome="record_again",
        ),
        create_phrase_decision(
            state,
            phrase_id="phrase-none",
            outcome="no_acceptable_candidate",
        ),
    ]

    source_map = create_vocal_source_map(state, decisions)

    assert source_map["schema"] == VOCAL_SOURCE_MAP_SCHEMA
    assert source_map["status"] == "partial_unrendered"
    assert source_map["binding"]["musical_state_sha256"] == state["document_sha256"]
    assert [row["outcome"] for row in source_map["segments"]] == [
        "human_take",
        "ai_fallback",
    ]
    assert [row["outcome"] for row in source_map["unresolved_phrases"]] == [
        "record_again",
        "no_acceptable_candidate",
    ]
    assert source_map["segments"][0]["source_audio_sha256"] == _source_hash(
        state, "take-002"
    )
    assert source_map["segments"][1]["source_audio_sha256"] == _source_hash(
        state, "reference-vocal-001"
    )
    assert "source_id" not in source_map["unresolved_phrases"][0]
    assert "source_id" not in source_map["unresolved_phrases"][1]
    assert source_map["undecided_phrase_ids"] == []
    assert source_map["training"]["pairwise_labels"] == []
    assert source_map["training"]["inferred_labels"] == []
    assert source_map["effects"]["source_map_created"] is True
    assert source_map["effects"]["audio_comp_rendered"] is False
    assert source_map["effects"]["pitch_correction_applied"] is False
    assert source_map["effects"]["timing_correction_applied"] is False
    assert not _keys_named_path(source_map)
    assert validate_vocal_source_map(source_map, state) == source_map


@pytest.mark.parametrize(
    ("outcome", "source_id", "message"),
    (
        ("human_take", None, "source"),
        ("human_take", "take-999", "unknown.*source|source.*unknown"),
        ("human_take", "reference-vocal-001", "human.*take"),
        ("ai_fallback", "take-001", "AI fallback|ai_fallback|source"),
        ("record_again", "take-001", "must not.*source|source"),
        ("no_acceptable_candidate", "take-001", "must not.*source|source"),
        ("automatic_best", "take-001", "outcome"),
    ),
)
def test_phrase_decision_rejects_unknown_or_outcome_incompatible_sources(
    outcome: str,
    source_id: str | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        create_phrase_decision(
            _musical_state(),
            phrase_id="phrase-human",
            outcome=outcome,
            source_id=source_id,
        )


def test_phrase_decision_rejects_unknown_or_unreviewed_phrase() -> None:
    state = _musical_state()
    with pytest.raises(
        ValueError, match="unknown.*phrase|phrase.*unknown|phrase.*musical state"
    ):
        create_phrase_decision(
            state,
            phrase_id="phrase-does-not-exist",
            outcome="record_again",
        )

    unreviewed = deepcopy(state)
    unreviewed["structure"]["review_status"] = "automatic_unreviewed"
    _rehash(unreviewed)
    with pytest.raises(ValueError, match="reviewed"):
        create_phrase_decision(
            unreviewed,
            phrase_id="phrase-human",
            outcome="record_again",
        )


def test_ai_fallback_requires_an_exact_admitted_reference() -> None:
    state = _musical_state()
    state["vocal_performance_state"]["reference"] = None
    _rehash(state)

    with pytest.raises(ValueError, match="reference"):
        create_phrase_decision(
            state,
            phrase_id="phrase-ai",
            outcome="ai_fallback",
        )


def test_decision_validation_detects_document_and_state_binding_tampering() -> None:
    state = _musical_state()
    decision = create_phrase_decision(
        state,
        phrase_id="phrase-human",
        outcome="human_take",
        source_id="take-001",
    )

    changed_without_rehash = deepcopy(decision)
    changed_without_rehash["selected_source_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="document SHA-256|document.*hash"):
        validate_phrase_decision(changed_without_rehash, state)

    rehashed_wrong_source = deepcopy(decision)
    rehashed_wrong_source["selected_source_sha256"] = "f" * 64
    _rehash(rehashed_wrong_source)
    with pytest.raises(ValueError, match="source.*SHA-256|source.*hash"):
        validate_phrase_decision(rehashed_wrong_source, state)

    rehashed_wrong_state = deepcopy(decision)
    rehashed_wrong_state["binding"]["musical_state_sha256"] = "e" * 64
    _rehash(rehashed_wrong_state)
    with pytest.raises(ValueError, match="musical.state|state.*SHA-256|state.*hash"):
        validate_phrase_decision(rehashed_wrong_state, state)


def test_decision_validation_rejects_added_paths_pairwise_labels_or_effects() -> None:
    state = _musical_state()
    decision = create_phrase_decision(
        state,
        phrase_id="phrase-human",
        outcome="human_take",
        source_id="take-001",
    )

    changed_path = deepcopy(decision)
    changed_path["evidence"] = {"path": "/Users/private/vocal.wav"}
    _rehash(changed_path)
    with pytest.raises(ValueError, match="path|absolute"):
        validate_phrase_decision(changed_path, state)

    changed_label = deepcopy(decision)
    changed_label["training"]["pairwise_labels"] = [
        {"preferred": "take-001", "rejected": "take-002"}
    ]
    _rehash(changed_label)
    with pytest.raises(ValueError, match="pairwise"):
        validate_phrase_decision(changed_label, state)

    changed_effect = deepcopy(decision)
    changed_effect["effects"]["audio_comp_rendered"] = True
    _rehash(changed_effect)
    with pytest.raises(ValueError, match="render"):
        validate_phrase_decision(changed_effect, state)


def test_source_map_retains_undecided_and_rejects_duplicate_or_foreign_decisions() -> (
    None
):
    state = _musical_state()
    first = create_phrase_decision(
        state,
        phrase_id="phrase-human",
        outcome="human_take",
        source_id="take-001",
    )

    partial = create_vocal_source_map(state, [first])
    assert partial["status"] == "partial_unrendered"
    assert partial["undecided_phrase_ids"] == [
        "phrase-ai",
        "phrase-retry",
        "phrase-none",
    ]
    assert partial["coverage"] == {
        "phrase_count": 4,
        "decision_count": 1,
        "source_segment_count": 1,
        "unresolved_count": 0,
        "undecided_count": 3,
    }
    with pytest.raises(ValueError, match="duplicate"):
        create_vocal_source_map(state, [first, first, first, first])

    other_state = deepcopy(state)
    other_state["clock"]["bpm"] = 97.0
    _rehash(other_state)
    foreign = create_phrase_decision(
        other_state,
        phrase_id="phrase-ai",
        outcome="ai_fallback",
    )
    decisions = [
        first,
        foreign,
        create_phrase_decision(state, phrase_id="phrase-retry", outcome="record_again"),
        create_phrase_decision(
            state,
            phrase_id="phrase-none",
            outcome="no_acceptable_candidate",
        ),
    ]
    with pytest.raises(ValueError, match="musical.state|state.*SHA-256|state.*hash"):
        create_vocal_source_map(state, decisions)


def _musical_state() -> dict[str, Any]:
    phrases = [
        {
            "phrase_id": "phrase-human",
            "start_seconds": 0.0,
            "end_seconds": 1.0,
            "lyrics": "Cause the heart sees",
        },
        {
            "phrase_id": "phrase-ai",
            "start_seconds": 1.1,
            "end_seconds": 2.0,
            "lyrics": "exactly what it wants to see",
        },
        {
            "phrase_id": "phrase-retry",
            "start_seconds": 2.1,
            "end_seconds": 3.0,
            "lyrics": "You know the truth",
        },
        {
            "phrase_id": "phrase-none",
            "start_seconds": 3.1,
            "end_seconds": 4.0,
            "lyrics": "between you and me",
        },
    ]
    empty_effects = {
        "source_mutated": False,
        "lyrics_mutated": False,
        "selection_created": False,
        "human_decision_created": False,
        "audio_comp_rendered": False,
        "pitch_correction_applied": False,
        "training_started": False,
        "model_weights_changed": False,
        "remix_rendered": False,
    }
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
        "effects": empty_effects,
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
    return {"path": path, "bytes": 128, "sha256": sha256}


def _source_hash(state: Mapping[str, Any], source_id: str) -> str:
    vocal = state["vocal_performance_state"]
    rows = [*vocal["takes"]]
    if vocal["reference"] is not None:
        rows.append(vocal["reference"])
    return next(
        str(row["audio"]["sha256"]) for row in rows if row["source_id"] == source_id
    )


def _keys_named_path(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).casefold() == "path":
                found.append(str(item))
            found.extend(_keys_named_path(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_keys_named_path(item))
    return found


def _rehash(document: dict[str, Any]) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)
