from __future__ import annotations

import json
from pathlib import Path

import pytest

from sunofriend._separation_authorised_midi_comparison import _document_sha256
from sunofriend._separation_human_listening_coverage import (
    HumanListeningInput,
    SCHEMA,
    _project_private_separation_human_listening_coverage,
)
from sunofriend._separation_normalized_midi_agreement import (
    SCHEMA as AGREEMENT_SCHEMA,
)
from sunofriend._separation_vocal_candidate_audition import RESOLUTION_SCHEMA


def test_projects_phrase_reviews_without_turning_them_into_acceptance(
    tmp_path: Path,
) -> None:
    excerpts = {"track-a": ("a" * 64, "b" * 64), "track-b": ("c" * 64, "d" * 64)}
    agreement = _agreement(tmp_path, excerpts)
    earlier = _review(
        tmp_path,
        "earlier",
        excerpt=excerpts["track-b"],
        start=3.45,
        end=6.85,
        useful=["provider/suno-b/leaf-01/lead/contour-clean"],
    )
    later = _review(
        tmp_path,
        "later",
        excerpt=excerpts["track-b"],
        start=9.2,
        end=14.95,
        useful=["kim/primary", "provider/suno-b/leaf-01/lead/contour-clean"],
    )

    result = _project_private_separation_human_listening_coverage(
        agreement,
        [
            HumanListeningInput("track-b", later),
            HumanListeningInput("track-b", earlier),
        ],
        out=tmp_path / "coverage.json",
    )

    assert result["schema"] == SCHEMA
    assert result["coverage"] == {
        "agreement_track_count": 2,
        "reviewed_track_count": 1,
        "review_window_count": 2,
        "reviewed_candidate_count": 4,
        "useful_for_focus_count": 3,
        "all_reviews_classify_reference_line_for_written_focus": True,
        "all_reviews_record_candidate_usefulness_separately": True,
        "all_reviewed_tracks_are_bound_to_normalized_excerpt": True,
        "cross_song_review_coverage_complete": False,
    }
    assert [
        window["scope"]["start_seconds"] for window in result["review_windows"]
    ] == [
        3.45,
        9.2,
    ]
    assert result["interpretation"]["useful_candidate_is_winner"] is False
    assert (
        result["interpretation"]["useful_candidate_is_complete_transcription"] is False
    )
    assert result["publication_gate"]["status"] == "open"
    assert (
        "cross_song_human_listening_coverage_incomplete"
        in result["publication_gate"]["unresolved_or_out_of_scope"]
    )
    persisted_text = (tmp_path / "coverage.json").read_text(encoding="utf-8")
    persisted = json.loads(persisted_text)
    assert persisted["document_sha256"] == _document_sha256(persisted)
    assert str(tmp_path) not in persisted_text


def test_cross_song_reviews_still_do_not_close_quality_gate(tmp_path: Path) -> None:
    excerpts = {"track-a": ("a" * 64, "b" * 64), "track-b": ("c" * 64, "d" * 64)}
    agreement = _agreement(tmp_path, excerpts)
    reviews = [
        HumanListeningInput(
            track_id,
            _review(
                tmp_path,
                track_id,
                excerpt=excerpt,
                start=1.0,
                end=3.0,
                useful=["kim/primary"],
            ),
        )
        for track_id, excerpt in excerpts.items()
    ]

    result = _project_private_separation_human_listening_coverage(
        agreement,
        reviews,
        out=tmp_path / "coverage.json",
    )

    assert result["coverage"]["cross_song_review_coverage_complete"] is True
    assert (
        "cross_song_human_listening_coverage_incomplete"
        not in result["publication_gate"]["unresolved_or_out_of_scope"]
    )
    assert result["publication_gate"]["cross_method_quality_comparison_ready"] is False
    assert (
        "transcription_completeness_not_structured"
        in result["publication_gate"]["unresolved_or_out_of_scope"]
    )


def test_rejects_review_bound_to_a_different_excerpt(tmp_path: Path) -> None:
    excerpts = {"track-a": ("a" * 64, "b" * 64), "track-b": ("c" * 64, "d" * 64)}
    agreement = _agreement(tmp_path, excerpts)
    review = _review(
        tmp_path,
        "wrong-source",
        excerpt=("e" * 64, "f" * 64),
        start=1.0,
        end=2.0,
        useful=["kim/primary"],
    )

    with pytest.raises(ValueError, match="not bound to the normalized song excerpt"):
        _project_private_separation_human_listening_coverage(
            agreement,
            [HumanListeningInput("track-b", review)],
            out=tmp_path / "rejected.json",
        )
    assert not (tmp_path / "rejected.json").exists()


def test_rejects_review_without_reference_line_classification(tmp_path: Path) -> None:
    excerpts = {"track-a": ("a" * 64, "b" * 64), "track-b": ("c" * 64, "d" * 64)}
    agreement = _agreement(tmp_path, excerpts)
    review = _review(
        tmp_path,
        "unclassified",
        excerpt=excerpts["track-b"],
        start=1.0,
        end=2.0,
        useful=["kim/primary"],
        classify_reference_line=False,
    )

    with pytest.raises(ValueError, match="policy differs"):
        _project_private_separation_human_listening_coverage(
            agreement,
            [HumanListeningInput("track-b", review)],
            out=tmp_path / "rejected.json",
        )


def _agreement(root: Path, excerpts: dict[str, tuple[str, str]]) -> Path:
    permissions = {
        "accepted": False,
        "automatic_promotion": False,
        "automatic_selection": False,
        "production_eligible": False,
        "public_result": False,
        "simple_mode_available": False,
        "source_graph_activation": False,
        "studio_import_available": False,
    }
    effects = {
        "audio_created_or_mutated": False,
        "candidate_activated": False,
        "default_changed": False,
        "midi_created_or_mutated": False,
        "source_graph_mutated": False,
    }
    document = {
        "schema": AGREEMENT_SCHEMA,
        "status": "complete_pairwise_agreement_not_quality_or_acceptance",
        "evidence_scope": "private_development_only",
        "comparison_contract": {
            "quality_comparison_permitted": False,
            "method_ranking_permitted": False,
        },
        "cells": [
            {
                "track_id": track_id,
                "source_track_id": f"{track_id}-source",
                "source_binding": {
                    "authorised_excerpt_sha256": excerpt[0],
                    "authorised_excerpt_document_sha256": excerpt[1],
                    "same_authorised_excerpt": True,
                },
            }
            for track_id, excerpt in sorted(excerpts.items())
        ],
        "publication_gate": {"status": "open"},
        "permissions": permissions,
        "effects": effects,
    }
    return _write_hashed(root / "agreement.json", document)


def _review(
    root: Path,
    name: str,
    *,
    excerpt: tuple[str, str],
    start: float,
    end: float,
    useful: list[str],
    classify_reference_line: bool = True,
) -> Path:
    candidates = [
        "kim/primary",
        "provider/suno-b/leaf-01/lead/contour-clean",
    ]
    if len(useful) == 1 and useful[0] not in candidates:
        candidates.append(useful[0])
    not_useful = [candidate for candidate in candidates if candidate not in useful]
    document = {
        "schema": RESOLUTION_SCHEMA,
        "status": "complete_review_no_activation",
        "evidence_scope": "private_development_only",
        "inputs": {
            "review_sha256": "1" * 64,
            "review_seed_document_sha256": "2" * 64,
            "candidate_set_sha256": "3" * 64,
            "candidate_set_document_sha256": "4" * 64,
            "authorised_excerpt_sha256": excerpt[0],
            "authorised_excerpt_document_sha256": excerpt[1],
        },
        "focus": "Find the principal lead-vocal melody, not backing harmony.",
        "scope": {
            "candidate_count": len(candidates),
            "candidate_ids": candidates,
            "candidate_order": "sealed_inventory_order_not_rank",
            "duration_seconds": end - start,
            "end_seconds": end,
            "inventory_candidate_count": len(candidates) + 3,
            "omitted_candidate_count": 3,
            "start_seconds": start,
            "time_window_source": "explicit",
        },
        "results": {
            "useful_for_focus_count": len(useful),
            "useful_for_focus": useful,
            "not_useful_for_focus_count": len(not_useful),
            "not_useful_for_focus": not_useful,
            "cannot_tell_count": 0,
            "cannot_tell": [],
            "reference_relationships": {
                "cannot_tell": [],
                "different_line": not_useful,
                "focus_line": useful,
                "mixed_or_overlapping_lines": [],
            },
        },
        "policy": {
            "human_dispositions_verified": True,
            "human_reference_line_relationships_verified": classify_reference_line,
            "winner_selected": False,
            "automatic_selection": False,
            "automatic_merge": False,
            "automatic_repair": False,
            "singer_identity_inferred": False,
            "production_eligible": False,
        },
        "effects": {
            "audio_created": False,
            "candidate_selected": False,
            "default_changed": False,
            "midi_created_or_mutated": False,
            "source_graph_mutated": False,
            "studio_or_simple_route_enabled": False,
        },
    }
    return _write_hashed(root / f"{name}.json", document)


def _write_hashed(path: Path, document: dict[str, object]) -> Path:
    document["document_sha256"] = _document_sha256(document)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path
