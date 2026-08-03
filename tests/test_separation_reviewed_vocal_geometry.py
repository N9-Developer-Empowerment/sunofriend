from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sunofriend._separation_authorised_midi_comparison import _document_sha256
from sunofriend._separation_reviewed_vocal_geometry import (
    SCHEMA,
    _build_document,
    _load_resolution,
    _positive_tolerance,
)
from sunofriend._separation_vocal_candidate_audition import RESOLUTION_SCHEMA
from sunofriend.models import NoteEvent


def test_geometry_document_is_diagnostic_path_free_and_does_not_choose() -> None:
    resolution = _resolution()
    notes = {
        "kim/primary": (
            NoteEvent(start=9.20, end=9.60, pitch=64, velocity=90),
            NoteEvent(start=10.00, end=10.45, pitch=66, velocity=92),
        ),
        "provider/suno-a/leaf-01/lead/contour-clean": (
            NoteEvent(start=9.24, end=9.58, pitch=64, velocity=88),
            NoteEvent(start=10.06, end=10.51, pitch=66, velocity=90),
            NoteEvent(start=11.00, end=11.20, pitch=67, velocity=86),
        ),
    }

    document = _build_document(
        resolution=resolution,
        resolution_file_sha256="f" * 64,
        useful_notes=notes,
        tolerance_seconds=0.08,
    )

    assert document["schema"] == SCHEMA
    assert document["policy"]["candidate_ranked_or_selected"] is False
    assert document["policy"]["automatic_merge"] is False
    assert document["effects"]["candidate_selected"] is False
    assert document["effects"]["midi_created_or_mutated"] is False
    assert document["observations"]["pair_count"] == 1
    pair = document["pairwise"][0]
    assert pair["orientation"] == "human_review_order_not_preference"
    assert pair["metrics"]["exact_pitch_onset"]["matched_count"] == 2
    assert "path" not in json.dumps(document).lower()


def test_geometry_document_requires_exact_reviewed_order() -> None:
    resolution = _resolution()
    notes = {
        "provider/suno-a/leaf-01/lead/contour-clean": (
            NoteEvent(start=9.2, end=9.5, pitch=64, velocity=90),
        ),
        "kim/primary": (
            NoteEvent(start=9.2, end=9.5, pitch=64, velocity=90),
        ),
    }

    with pytest.raises(ValueError, match="order or membership"):
        _build_document(
            resolution=resolution,
            resolution_file_sha256="f" * 64,
            useful_notes=notes,
            tolerance_seconds=0.08,
        )


def test_load_resolution_rejects_activation_or_tampering(tmp_path: Path) -> None:
    resolution = _resolution()
    path = tmp_path / "resolution.json"
    path.write_text(json.dumps(resolution), encoding="utf-8")
    _, _, loaded = _load_resolution(path)
    assert loaded["status"] == "complete_review_no_activation"

    changed = copy.deepcopy(resolution)
    changed["policy"]["winner_selected"] = True
    changed["document_sha256"] = _document_sha256(changed)
    changed_path = tmp_path / "changed.json"
    changed_path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="not inactive"):
        _load_resolution(changed_path)


@pytest.mark.parametrize("value", [0.0, -0.1, 0.50001, float("nan")])
def test_tolerance_is_bounded(value: float) -> None:
    with pytest.raises(ValueError):
        _positive_tolerance(value)


def _resolution() -> dict[str, object]:
    useful = [
        "kim/primary",
        "provider/suno-a/leaf-01/lead/contour-clean",
    ]
    document: dict[str, object] = {
        "schema": RESOLUTION_SCHEMA,
        "status": "complete_review_no_activation",
        "evidence_scope": "private_development_only",
        "inputs": {
            "review_sha256": "a" * 64,
            "review_seed_document_sha256": "b" * 64,
            "candidate_set_sha256": "c" * 64,
            "candidate_set_document_sha256": "d" * 64,
            "authorised_excerpt_sha256": "e" * 64,
            "authorised_excerpt_document_sha256": "f" * 64,
        },
        "focus": "Follow the principal lead melody, not backing harmony.",
        "scope": {
            "start_seconds": 9.2,
            "end_seconds": 14.95,
            "duration_seconds": 5.75,
            "candidate_ids": useful,
            "candidate_count": 2,
            "inventory_candidate_count": 2,
            "omitted_candidate_count": 0,
            "candidate_order": "sealed_inventory_order_not_rank",
            "time_window_source": "explicit",
        },
        "results": {
            "useful_for_focus_count": 2,
            "useful_for_focus": useful,
            "not_useful_for_focus_count": 0,
            "not_useful_for_focus": [],
            "cannot_tell_count": 0,
            "cannot_tell": [],
            "reference_relationships": {
                "cannot_tell": [],
                "different_line": [],
                "focus_line": useful,
                "mixed_or_overlapping_lines": [],
            },
        },
        "policy": {
            "human_dispositions_verified": True,
            "multiple_useful_candidates_allowed": True,
            "winner_selected": False,
            "automatic_selection": False,
            "automatic_merge": False,
            "automatic_repair": False,
            "singer_identity_inferred": False,
            "human_reference_line_relationships_verified": True,
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
        "limitations": [],
    }
    document["document_sha256"] = _document_sha256(document)
    return document
