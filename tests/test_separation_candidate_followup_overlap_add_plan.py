from __future__ import annotations

from typing import Any

import pytest

from sunofriend._separation_candidate_followup_overlap_add_plan import (
    MAXIMUM_EXCERPT_FRAMES,
    MINIMUM_OVERLAP_FRAMES,
    _balanced_overlap_windows,
    _original_audible_targets,
    _validated_failed_variant_evidence,
)


def test_balanced_windows_cover_be_alone_exactly_without_short_tail() -> None:
    windows = _balanced_overlap_windows(
        total_frames=11_578_896,
        window_frames=MAXIMUM_EXCERPT_FRAMES,
        minimum_overlap_frames=MINIMUM_OVERLAP_FRAMES,
    )

    assert len(windows) == 21
    assert windows[0]["source_start_frame"] == 0
    assert windows[-1]["source_end_frame"] == 11_578_896
    assert all(
        item["source_end_frame"] - item["source_start_frame"] == MAXIMUM_EXCERPT_FRAMES
        for item in windows
    )
    overlaps = [item["overlap_with_previous_frames"] for item in windows[1:]]
    assert min(overlaps) == 115_630
    assert max(overlaps) == 115_631
    assert all(item["status"] == "not_run" for item in windows)


def test_window_geometry_rejects_non_overlapping_request() -> None:
    with pytest.raises(ValueError, match="window geometry"):
        _balanced_overlap_windows(
            total_frames=1_000,
            window_frames=500,
            minimum_overlap_frames=500,
        )


def test_failed_variant_gate_preserves_both_without_selecting() -> None:
    result = _failed_result()

    evidence = _validated_failed_variant_evidence(
        result, known_variant_ids=["standard", "preserved"]
    )

    assert [item["variant_id"] for item in evidence] == ["standard", "preserved"]
    assert all(item["selected"] is False for item in evidence)
    assert all(item["accepted"] is False for item in evidence)
    assert evidence[0]["failed_targeted_checks"][0]["failed_edges"] == ["end"]


def test_failed_variant_gate_rejects_an_eligible_candidate() -> None:
    result = _failed_result()
    result["fresh_all_boundary_review_eligible_variant_ids"] = ["standard"]
    result["readiness_evidence"][
        "one_or_more_variants_eligible_for_fresh_all_boundary_review"
    ] = True

    with pytest.raises(ValueError, match="zero-eligible"):
        _validated_failed_variant_evidence(
            result, known_variant_ids=["standard", "preserved"]
        )


def test_original_targets_require_the_complete_ten_pair_inventory() -> None:
    patches = [
        {
            "boundary_index": index,
            "role": "vocals" if index % 2 else "instrumental",
            "patch_start_frame": index * 100,
            "patch_end_frame": index * 100 + 50,
        }
        for index in range(1, 11)
    ]
    context: dict[str, Any] = {"inputs": {"candidate": {"patches": patches}}}

    targets = _original_audible_targets(context)

    assert len(targets) == 10
    assert targets[0]["boundary_index"] == 1
    assert targets[-1]["boundary_index"] == 10
    assert all(
        item["source_end_frame"] > item["source_start_frame"] for item in targets
    )


def _failed_result() -> dict[str, Any]:
    check = {
        "action": "edge_aware_reinference_and_blend_search",
        "boundary_index": 4,
        "role": "instrumental",
        "boundary_gate_pass": True,
        "edge_gate_pass": False,
        "failed_edges": ["end"],
        "outcomes": {"boundary": "equivalent", "start": "equivalent", "end": "neither"},
        "pass": False,
    }
    gate = {
        variant_id: {
            "accepted": False,
            "selected": False,
            "eligible_for_fresh_all_boundary_review": False,
            "all_targeted_checks_pass": False,
            "all_complete_songs_candidate_or_equivalent": True,
            "complete_song_outcomes": {
                "vocals": "equivalent",
                "instrumental": "equivalent",
                "reconstruction": "equivalent",
            },
            "targeted_checks": [dict(check)],
        }
        for variant_id in ("standard", "preserved")
    }
    return {
        "readiness_evidence": {
            "variant_review_complete": True,
            "one_or_more_variants_eligible_for_fresh_all_boundary_review": False,
        },
        "fresh_all_boundary_review_eligible_variant_ids": [],
        "candidate_gate_evidence": gate,
        "units": [{"resolved_choice": "equivalent"}],
        "reviewed_unit_count": 1,
    }
