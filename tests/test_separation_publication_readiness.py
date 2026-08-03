from __future__ import annotations

import json
from pathlib import Path

import pytest

from sunofriend._separation_authorised_midi_comparison import (
    _document_sha256,
    _sha256,
)
from sunofriend._separation_human_listening_coverage import (
    SCHEMA as HUMAN_LISTENING_SCHEMA,
)
from sunofriend._separation_normalized_midi_agreement import (
    SCHEMA as AGREEMENT_SCHEMA,
)
from sunofriend._separation_publication_readiness import (
    SCHEMA,
    _project_private_separation_publication_readiness,
)


def test_projects_passed_and_open_gates_without_enabling_separation(
    tmp_path: Path,
) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)

    result = _project_private_separation_publication_readiness(
        agreement,
        listening,
        out=tmp_path / "readiness.json",
    )

    assert result["schema"] == SCHEMA
    assert result["status"] == "blocked_private_bounded_vocal_midi_evidence_only"
    assert result["readiness"] == {
        "stage": "private_bounded_vocal_research",
        "passed_gate_count": 3,
        "open_gate_count": 8,
        "required_gate_count": 11,
        "publication_ready": False,
        "experimental_studio_route_ready": False,
        "one_action_simple_route_ready": False,
    }
    gates = {gate["gate_id"]: gate["status"] for gate in result["gates"]}
    assert gates["source_bound_cross_song_downstream_midi"] == "passed"
    assert gates["source_bound_cross_song_human_listening"] == "passed"
    assert gates["separator_audio_quality_cross_song"] == "open"
    assert gates["public_cli_tui_simple_studio_route"] == "open"
    assert (
        result["interpretation"][
            "private_separator_derived_midi_has_useful_evidence"
        ]
        is True
    )
    assert result["interpretation"]["human_usefulness_is_accuracy"] is False
    assert all(value is False for value in result["permissions"].values())
    assert all(value is False for value in result["effects"].values())

    text = (tmp_path / "readiness.json").read_text(encoding="utf-8")
    persisted = json.loads(text)
    assert persisted["document_sha256"] == _document_sha256(persisted)
    assert str(tmp_path) not in text


def test_rejects_listening_report_bound_to_different_agreement(
    tmp_path: Path,
) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    document = json.loads(listening.read_text(encoding="utf-8"))
    document["inputs"]["normalized_midi_agreement_sha256"] = "f" * 64
    listening = _write_hashed(tmp_path / "wrong-listening.json", document)

    with pytest.raises(ValueError, match="not bound to agreement"):
        _project_private_separation_publication_readiness(
            agreement,
            listening,
            out=tmp_path / "rejected.json",
        )
    assert not (tmp_path / "rejected.json").exists()


def test_rejects_incomplete_human_listening_coverage(tmp_path: Path) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    document = json.loads(listening.read_text(encoding="utf-8"))
    document["coverage"]["cross_song_review_coverage_complete"] = False
    listening = _write_hashed(tmp_path / "incomplete-listening.json", document)

    with pytest.raises(ValueError, match="coverage contract differs"):
        _project_private_separation_publication_readiness(
            agreement,
            listening,
            out=tmp_path / "rejected.json",
        )


def test_rejects_active_input_permissions(tmp_path: Path) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    document = json.loads(listening.read_text(encoding="utf-8"))
    document["permissions"]["accepted"] = True
    listening = _write_hashed(tmp_path / "active-listening.json", document)

    with pytest.raises(ValueError, match="listening permissions differ"):
        _project_private_separation_publication_readiness(
            agreement,
            listening,
            out=tmp_path / "rejected.json",
        )


def test_rejects_forged_coverage_counts(tmp_path: Path) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    document = json.loads(listening.read_text(encoding="utf-8"))
    document["coverage"]["reviewed_candidate_count"] = -1
    listening = _write_hashed(tmp_path / "forged-listening.json", document)

    with pytest.raises(ValueError, match="non-negative integer"):
        _project_private_separation_publication_readiness(
            agreement,
            listening,
            out=tmp_path / "rejected.json",
        )


def _agreement(root: Path) -> Path:
    document = {
        "schema": AGREEMENT_SCHEMA,
        "status": "complete_pairwise_agreement_not_quality_or_acceptance",
        "evidence_scope": "private_development_only",
        "comparison_contract": {
            "quality_comparison_permitted": False,
            "method_ranking_permitted": False,
        },
        "cells": [
            {"track_id": "track-a"},
            {"track_id": "track-b"},
        ],
        "publication_gate": {"status": "open"},
        "permissions": _permissions(),
        "effects": _agreement_effects(),
    }
    return _write_hashed(root / "agreement.json", document)


def _listening(root: Path, agreement: Path) -> Path:
    agreement_document = json.loads(agreement.read_text(encoding="utf-8"))
    document = {
        "schema": HUMAN_LISTENING_SCHEMA,
        "status": "complete_human_listening_projection_not_acceptance",
        "evidence_scope": "private_development_only",
        "inputs": {
            "normalized_midi_agreement_sha256": _sha256(agreement),
            "normalized_midi_agreement_document_sha256": agreement_document[
                "document_sha256"
            ],
        },
        "review_windows": [
            {"track_id": "track-a"},
            {"track_id": "track-b"},
        ],
        "coverage": {
            "agreement_track_count": 2,
            "reviewed_track_count": 2,
            "review_window_count": 2,
            "reviewed_candidate_count": 7,
            "useful_for_focus_count": 3,
            "structured_focus_phrase_coverage_window_count": 2,
            "all_reviews_record_focus_phrase_coverage": True,
            "all_reviewed_tracks_are_bound_to_normalized_excerpt": True,
            "cross_song_review_coverage_complete": True,
        },
        "publication_gate": {"status": "open"},
        "permissions": _permissions(),
        "effects": {
            **_agreement_effects(),
            "review_notes_copied": False,
        },
    }
    return _write_hashed(root / "listening.json", document)


def _permissions() -> dict[str, bool]:
    return {
        "accepted": False,
        "automatic_promotion": False,
        "automatic_selection": False,
        "production_eligible": False,
        "public_result": False,
        "simple_mode_available": False,
        "source_graph_activation": False,
        "studio_import_available": False,
    }


def _agreement_effects() -> dict[str, bool]:
    return {
        "audio_created_or_mutated": False,
        "candidate_activated": False,
        "default_changed": False,
        "midi_created_or_mutated": False,
        "source_graph_mutated": False,
    }


def _write_hashed(path: Path, document: dict[str, object]) -> Path:
    document.pop("document_sha256", None)
    document["document_sha256"] = _document_sha256(document)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path
