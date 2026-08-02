from __future__ import annotations

from pathlib import Path

import pytest

import sunofriend._separation_vocal_candidate_set as candidate_set
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


def test_candidate_set_preserves_every_family_without_ranking_or_paths() -> None:
    document = candidate_set._build_document(_input_bundle())

    assert document["summary"] == {
        "candidate_count": 4,
        "audition_available_count": 3,
        "no_note_evidence_count": 1,
        "family_counts": {
            "kim_primary": 1,
            "kim_register": 1,
            "provider_leaf": 2,
        },
        "provider_leaf_counts": {"provider-a": 2},
    }
    assert [item["candidate_id"] for item in document["candidates"]] == [
        "kim/primary",
        "kim/register/lowest-line",
        "provider/provider-a/leaf-01/backing/dominant-line",
        "provider/provider-a/leaf-01/lead/contour-clean",
    ]
    assert document["candidates"][-1]["audition_state"] == "no_note_evidence"
    assert document["policy"]["candidate_ranked"] is False
    assert document["policy"]["candidate_selected"] is False
    assert document["policy"]["candidate_merged"] is False
    assert document["policy"]["singer_identity_inferred"] is False
    assert all(value is False for value in document["permissions"].values())
    assert not _contains_key(document, "path")
    assert not _contains_key(document, "midi_path")


def test_candidate_set_rejects_duplicate_identifiers() -> None:
    inputs = _input_bundle()
    inputs["candidates"] = (inputs["candidates"][0], inputs["candidates"][0])

    with pytest.raises(ValueError, match="not unique"):
        candidate_set._build_document(inputs)


def test_path_free_artifact_strips_locator_but_keeps_identity() -> None:
    result = candidate_set._path_free_artifact(
        {"path": "private/candidate.mid", "sha256": "a" * 64, "bytes": 123},
        kind="midi",
        required=True,
    )

    assert result == {"sha256": "a" * 64, "bytes": 123}


def test_rejects_existing_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(candidate_set, "_load_inputs", lambda *args: _input_bundle())
    monkeypatch.setattr(candidate_set, "_reverify_inputs", lambda _: None)
    destination = tmp_path / "result"
    destination.mkdir()

    with pytest.raises(FileExistsError, match="already exists"):
        candidate_set._build_vocal_candidate_set(
            tmp_path / "mel.json",
            tmp_path / "leaf.json",
            tmp_path / "phrase.json",
            out_dir=destination,
        )


def test_private_candidate_set_has_no_public_route() -> None:
    command = "private-vocal-candidate-set"
    assert command not in PUBLIC_COMMANDS
    assert command not in DIRECT_TUI_COMMANDS
    assert candidate_set.__all__ == ()


def _input_bundle() -> dict[str, object]:
    available = {
        "candidate_id": "kim/primary",
        "family": "kim_primary",
        "provider_group": None,
        "leaf_id": None,
        "adapter": None,
        "variant": "primary",
        "musical_identity": "unassigned_vocal_candidate",
        "note_count": 3,
        "audition_state": "available",
        "artifacts": {
            "midi": {"sha256": "1" * 64, "bytes": 10},
            "notes": {"sha256": "2" * 64, "bytes": 20},
            "render": {"sha256": "3" * 64, "bytes": 30},
        },
        "activity_diagnostic": None,
        "selection_state": "unselected",
    }
    register = dict(available)
    register.update(
        candidate_id="kim/register/lowest-line",
        family="kim_register",
        variant="lowest_line",
    )
    leaf = dict(available)
    leaf.update(
        candidate_id="provider/provider-a/leaf-01/backing/dominant-line",
        family="provider_leaf",
        provider_group="provider-a",
        leaf_id="leaf-01",
        adapter="backing",
        variant="dominant_line",
    )
    empty = dict(leaf)
    empty.update(
        candidate_id="provider/provider-a/leaf-01/lead/contour-clean",
        adapter="lead",
        variant="contour_clean",
        note_count=0,
        audition_state="no_note_evidence",
        artifacts={
            "midi": None,
            "notes": {"sha256": "4" * 64, "bytes": 20},
            "render": None,
        },
    )
    return {
        "duration_seconds": 15.0,
        "bpm": 120.0,
        "tuning_hz": 440.0,
        "candidates": (available, register, leaf, empty),
        "melroformer_sha256": "a" * 64,
        "melroformer": {"document_sha256": "b" * 64},
        "leaf_sha256": "c" * 64,
        "leaf": {"document_sha256": "d" * 64},
        "phrase_sha256": "e" * 64,
        "phrase": {
            "document_sha256": "f" * 64,
            "provider_consensus": {
                "active_seconds": 4.0,
                "interval_count": 2,
                "phrase_count": 1,
            },
            "primary_vs_lowest": {
                "both_candidates_consensus_seconds": 0.5,
                "primary_only_consensus_seconds": 2.0,
                "lowest_only_consensus_seconds": 0.5,
                "neither_candidate_consensus_seconds": 1.0,
                "automatic_merge_performed": False,
            },
        },
    }


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False
