from __future__ import annotations

from pathlib import Path

import pytest

import sunofriend._separation_vocal_phrase_completeness as completeness
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS
from sunofriend.models import NoteEvent


def test_provider_support_gives_each_group_at_most_one_vote() -> None:
    groups = {
        "a": ((0.0, 2.0),),
        "b": ((1.0, 3.0),),
        "c": ((2.5, 4.0),),
    }

    segments = completeness._provider_support_segments(
        groups, minimum_support=2
    )

    assert segments == [
        {
            "start": 1.0,
            "end": 2.0,
            "providers": ["a", "b"],
            "support_count": 2,
        },
        {
            "start": 2.5,
            "end": 3.0,
            "providers": ["b", "c"],
            "support_count": 2,
        },
    ]


def test_primary_and_lowest_are_observed_without_ranking_or_merging() -> None:
    document = completeness._build_document(_input_bundle())

    assert document["provider_consensus"] == {
        "active_seconds": 1.5,
        "interval_count": 2,
        "phrase_count": 2,
        "intervals": [
            {"start": 1.0, "end": 2.0},
            {"start": 2.5, "end": 3.0},
        ],
        "support_segments": [
            {
                "start": 1.0,
                "end": 2.0,
                "providers": ["a", "b"],
                "support_count": 2,
            },
            {
                "start": 2.5,
                "end": 3.0,
                "providers": ["b", "c"],
                "support_count": 2,
            },
        ],
    }
    assert document["primary_vs_lowest"] == {
        "both_candidates_consensus_seconds": 0.0,
        "primary_only_consensus_seconds": 0.7,
        "lowest_only_consensus_seconds": 0.6,
        "neither_candidate_consensus_seconds": 0.2,
        "reported_lowest_only_consensus_span_count": 2,
        "reported_lowest_only_consensus_spans": [
            {"start": 1.5, "end": 2.0},
            {"start": 2.5, "end": 2.6},
        ],
        "reported_neither_candidate_consensus_span_count": 1,
        "reported_neither_candidate_consensus_spans": [
            {"start": 2.6, "end": 2.8},
        ],
        "automatic_merge_performed": False,
    }
    assert document["policy"]["candidate_ranked_or_selected"] is False
    assert document["observations"]["coverage_is_activity_only_not_melody_accuracy"]
    assert all(value is False for value in document["permissions"].values())
    assert document["effects"] == {
        "audio_created": False,
        "midi_created": False,
        "review_created": False,
        "source_audio_mutated": False,
        "source_graph_mutated": False,
    }


def test_rejects_existing_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(completeness, "_load_inputs", lambda *args: _input_bundle())
    monkeypatch.setattr(completeness, "_reverify_inputs", lambda _: None)
    destination = tmp_path / "result"
    destination.mkdir()

    with pytest.raises(FileExistsError, match="already exists"):
        completeness._evaluate_vocal_phrase_completeness(
            tmp_path / "controls.json",
            tmp_path / "melroformer.json",
            tmp_path / "leaves.json",
            out_dir=destination,
        )


def test_private_phrase_completeness_has_no_public_route() -> None:
    command = "private-vocal-phrase-completeness"
    assert command not in PUBLIC_COMMANDS
    assert command not in DIRECT_TUI_COMMANDS
    assert completeness.__all__ == ()


def _input_bundle() -> dict[str, object]:
    providers = {
        "a": (NoteEvent(0.0, 2.0, 60, 90),),
        "b": (NoteEvent(1.0, 3.0, 62, 90),),
        "c": (NoteEvent(2.5, 4.0, 64, 90),),
    }
    primary = (
        NoteEvent(0.0, 1.5, 67, 90),
        NoteEvent(2.8, 4.0, 69, 90),
    )
    lowest = (NoteEvent(1.5, 2.6, 48, 90),)
    return {
        "duration_seconds": 4.0,
        "bpm": 120.0,
        "tuning_hz": 440.0,
        "provider_group_notes": providers,
        "controls": providers,
        "leaf_primary_notes": {provider_id: {} for provider_id in providers},
        "target_notes": {
            "primary": primary,
            "lowest_line": lowest,
            "dominant_line": primary,
            "harmony_stack": primary + lowest,
            "top_line": primary,
        },
        "control_sha256": "a" * 64,
        "control": {"document_sha256": "b" * 64},
        "melroformer_sha256": "c" * 64,
        "melroformer": {"document_sha256": "d" * 64},
        "leaf_sha256": "e" * 64,
        "leaf": {"document_sha256": "f" * 64},
    }
