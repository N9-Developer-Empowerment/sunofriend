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
from sunofriend._separation_audio_quality_review import (
    POLICY_ID as AUDIO_QUALITY_POLICY_ID,
    RESULT_SCHEMA as AUDIO_QUALITY_RESULT_SCHEMA,
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


def test_closes_only_the_audio_gate_for_source_bound_minimum_usable_review(
    tmp_path: Path,
) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    audio_quality = _audio_quality(tmp_path, agreement, minimum_usable=True)

    result = _project_private_separation_publication_readiness(
        agreement,
        listening,
        separated_audio_quality_path=audio_quality,
        out=tmp_path / "readiness-with-audio.json",
    )

    gates = {gate["gate_id"]: gate["status"] for gate in result["gates"]}
    assert gates["separator_audio_quality_cross_song"] == "passed"
    assert gates["full_song_duration_and_alignment"] == "open"
    assert gates["public_cli_tui_simple_studio_route"] == "open"
    assert result["readiness"]["passed_gate_count"] == 4
    assert result["readiness"]["open_gate_count"] == 7
    assessment = result["separated_audio_quality_assessment"]
    assert assessment["gate_passed"] is True
    assert assessment["minimum_usable_track_count"] == 2
    assert assessment["requirements"]["provider_preference_affects_gate"] is False
    persisted = (tmp_path / "readiness-with-audio.json").read_text()
    assert "Private listening note" not in persisted
    assert all(value is False for value in result["permissions"].values())
    assert all(value is False for value in result["effects"].values())


def test_completed_audio_review_stays_open_when_one_kim_excerpt_is_partial(
    tmp_path: Path,
) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    audio_quality = _audio_quality(tmp_path, agreement, minimum_usable=False)

    result = _project_private_separation_publication_readiness(
        agreement,
        listening,
        separated_audio_quality_path=audio_quality,
        out=tmp_path / "readiness-audio-open.json",
    )

    gates = {gate["gate_id"]: gate["status"] for gate in result["gates"]}
    assert gates["separator_audio_quality_cross_song"] == "open"
    assert result["readiness"]["passed_gate_count"] == 3
    assert result["separated_audio_quality_assessment"]["gate_passed"] is False


def test_rejects_audio_review_bound_to_different_excerpt(tmp_path: Path) -> None:
    agreement = _agreement(tmp_path)
    listening = _listening(tmp_path, agreement)
    audio_quality = _audio_quality(tmp_path, agreement, minimum_usable=True)
    document = json.loads(audio_quality.read_text(encoding="utf-8"))
    document["units"][0]["source_binding"][
        "authorised_excerpt_sha256"
    ] = "f" * 64
    audio_quality = _write_hashed(tmp_path / "wrong-audio.json", document)

    with pytest.raises(ValueError, match="source binding differs"):
        _project_private_separation_publication_readiness(
            agreement,
            listening,
            separated_audio_quality_path=audio_quality,
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
            _agreement_cell("track-a", "source-a", "a", "b", "c", "d"),
            _agreement_cell("track-b", "source-b", "e", "f", "0", "1"),
        ],
        "publication_gate": {"status": "open"},
        "permissions": _permissions(),
        "effects": _agreement_effects(),
    }
    return _write_hashed(root / "agreement.json", document)


def _agreement_cell(
    track_id: str,
    source_track_id: str,
    excerpt_file: str,
    excerpt_document: str,
    mapping_file: str,
    mapping_document: str,
) -> dict[str, object]:
    return {
        "track_id": track_id,
        "source_track_id": source_track_id,
        "source_binding": {
            "authorised_excerpt_sha256": excerpt_file * 64,
            "authorised_excerpt_document_sha256": excerpt_document * 64,
            "role_mapping_sha256": mapping_file * 64,
            "role_mapping_document_sha256": mapping_document * 64,
        },
    }


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


def _audio_quality(
    root: Path,
    agreement: Path,
    *,
    minimum_usable: bool,
) -> Path:
    agreement_document = json.loads(agreement.read_text(encoding="utf-8"))
    units = []
    for index, cell in enumerate(agreement_document["cells"]):
        binding = dict(cell["source_binding"])
        binding.update(
            {
                "track_id": cell["track_id"],
                "source_track_id": cell["source_track_id"],
                "provider_id": "moises",
                "start_seconds": 10.0 + index,
                "end_seconds": 10.5 + index,
                "candidate_evaluation_sha256": "2" * 64,
                "candidate_evaluation_document_sha256": "3" * 64,
                "source_audio_sha256": "4" * 64,
                "candidate_audio_sha256": "5" * 64,
                "provider_audio_sha256": "6" * 64,
            }
        )
        retention = (
            "partially_complete"
            if index == 1 and not minimum_usable
            else "substantially_complete"
        )
        units.append(
            {
                "unit_id": f"0{index + 1}-{cell['track_id']}",
                "track_id": cell["track_id"],
                "source_track_id": cell["source_track_id"],
                "source_seconds": [10.0 + index, 10.5 + index],
                "source_binding": binding,
                "candidate_a_method": "kim-vocal-2",
                "candidate_b_method": "provider-moises-broad-vocals",
                "ratings_by_method": {
                    "kim-vocal-2": {
                        "vocal_retention": retention,
                        "non_vocal_bleed": "noticeable",
                        "artefacts": "low",
                    },
                    "provider-moises-broad-vocals": {
                        "vocal_retention": "substantially_complete",
                        "non_vocal_bleed": "low",
                        "artefacts": "noticeable",
                    },
                },
                "preference": "candidate_b",
                "resolved_preference": "provider-moises-broad-vocals",
                "notes": "Private listening note",
            }
        )
    document = {
        "schema": AUDIO_QUALITY_RESULT_SCHEMA,
        "status": "complete_review_no_activation",
        "evidence_scope": "private_development_only",
        "policy_id": AUDIO_QUALITY_POLICY_ID,
        "unit_count": len(units),
        "units": units,
        "permissions": _permissions(),
        "effects": {**_agreement_effects(), "separator_selected": False},
    }
    return _write_hashed(root / "audio-quality.json", document)


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
