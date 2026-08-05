from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

import sunofriend._separation_private_route_design as design
from sunofriend._separation_authorised_excerpt import _document_sha256
from sunofriend._separation_multi_song_private_pilot_coverage import (
    POLICY_ID as COVERAGE_POLICY_ID,
    SCHEMA as COVERAGE_SCHEMA,
    STATUS as COVERAGE_STATUS,
)


def test_builds_path_free_non_activating_private_route_design(tmp_path: Path) -> None:
    context = _context(tmp_path)
    output = context["output_parent"] / design.REPORT_NAME

    result = design._build_private_separation_route_design(
        context["coverage"],
        out=output,
    )

    assert result["status"] == design.STATUS
    assert result["route_boundary"]["availability"] == "design_only"
    assert result["route_boundary"]["primary_outputs"] == [
        "vocals",
        "instrumental",
    ]
    assert result["route_boundary"]["diagnostic_outputs"] == ["reconstruction"]
    assert result["readiness"] == {
        "evidence_checkpoint_verified": True,
        "private_only_route_design_complete": True,
        "next_stage": "implement_stage_1_sealed_backend_adapter_contract",
        "private_execution_implemented": False,
        "private_execution_available": False,
        "product_integration_assessed": False,
        "product_integration_permitted": False,
        "public_release_permitted": False,
    }
    assert not any(result["permissions"].values())
    assert result["effects"]["design_record_created"] is True
    assert result["effects"]["model_run"] is False
    assert result["effects"]["source_graph_mutated"] is False
    assert os.stat(output.parent).st_mode & 0o777 == 0o700
    assert os.stat(output).st_mode & 0o777 == 0o600
    persisted = output.read_text(encoding="utf-8")
    assert str(tmp_path) not in persisted
    document = json.loads(persisted)
    assert document["document_sha256"] == _document_sha256(document)


def test_rejects_coverage_below_design_checkpoint(tmp_path: Path) -> None:
    context = _context(tmp_path)
    document = _read(context["coverage"])
    document["private_evaluation_checkpoint"][
        "private_route_design_checkpoint_met"
    ] = False
    document["private_evaluation_checkpoint"]["next_action"] = (
        "run_and_review_at_least_one_additional_song_disjoint_private_pilot"
    )
    _write_private_json(context["coverage"], document)

    with pytest.raises(ValueError, match="checkpoint is not met"):
        design._build_private_separation_route_design(
            context["coverage"],
            out=context["output_parent"] / design.REPORT_NAME,
        )


def test_rejects_coverage_that_exposes_a_product_route(tmp_path: Path) -> None:
    context = _context(tmp_path)
    document = _read(context["coverage"])
    document["permissions"]["simple_mode_available"] = True
    _write_private_json(context["coverage"], document)

    with pytest.raises(ValueError, match="coverage differs"):
        design._build_private_separation_route_design(
            context["coverage"],
            out=context["output_parent"] / design.REPORT_NAME,
        )


def test_rejects_inconsistent_review_counts(tmp_path: Path) -> None:
    context = _context(tmp_path)
    document = _read(context["coverage"])
    document["coverage"]["boundary_rating_totals"]["clean"] += 1
    _write_private_json(context["coverage"], document)

    with pytest.raises(ValueError, match="summary differs"):
        design._build_private_separation_route_design(
            context["coverage"],
            out=context["output_parent"] / design.REPORT_NAME,
        )


def test_rejects_changed_case_boundary_evidence(tmp_path: Path) -> None:
    context = _context(tmp_path)
    document = _read(context["coverage"])
    document["cases"][1]["audible_join_boundaries_by_role"]["vocals"] = [1, 2]
    _write_private_json(context["coverage"], document)

    with pytest.raises(ValueError, match="case totals differ"):
        design._build_private_separation_route_design(
            context["coverage"],
            out=context["output_parent"] / design.REPORT_NAME,
        )


def test_requires_fresh_fixed_named_output(tmp_path: Path) -> None:
    context = _context(tmp_path)
    with pytest.raises(ValueError, match="filename"):
        design._build_private_separation_route_design(
            context["coverage"],
            out=context["output_parent"] / "different.json",
        )

    output = context["output_parent"] / design.REPORT_NAME
    design._build_private_separation_route_design(context["coverage"], out=output)
    with pytest.raises(FileExistsError):
        design._build_private_separation_route_design(
            context["coverage"],
            out=output,
        )


def _context(tmp_path: Path) -> dict[str, Path]:
    os.chmod(tmp_path, 0o700)
    coverage_path = tmp_path / "private-separation-multi-song-private-pilot-coverage.json"
    _write_private_json(coverage_path, _coverage_document())
    output_parent = tmp_path / "output"
    output_parent.mkdir(mode=0o700)
    return {"coverage": coverage_path, "output_parent": output_parent}


def _coverage_document() -> dict[str, object]:
    cases = [
        {
            "case_kind": "pragmatic_reference",
            "source_audio_sha256": "1" * 64,
        },
        _pilot("track-a", "2" * 64, audible={"vocals": [1]}),
        _pilot("track-b", "3" * 64, audible={"instrumental": [2]}),
    ]
    document: dict[str, object] = {
        "schema": COVERAGE_SCHEMA,
        "status": COVERAGE_STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": COVERAGE_POLICY_ID,
        "coverage": {
            "reference_case_count": 1,
            "song_disjoint_pilot_count": 2,
            "distinct_source_count": 3,
            "all_source_hashes_distinct": True,
            "all_song_disjoint_pilots_automatic_chain_verified": True,
            "all_song_disjoint_pilots_full_song_reviewed": True,
            "all_song_disjoint_pilots_full_song_roles_useful": True,
            "all_song_disjoint_pilots_two_stem_handoff_complete": True,
            "reviewed_song_disjoint_boundary_count": 4,
            "reviewed_role_boundary_judgement_count": 12,
            "boundary_rating_totals": {
                "audible_join": 2,
                "cannot_tell": 0,
                "clean": 10,
            },
        },
        "cases": cases,
        "private_evaluation_checkpoint": {
            "two_distinct_source_evidence_checkpoint_met": True,
            "minimum_song_disjoint_pilots_before_private_route_design": 2,
            "private_route_design_checkpoint_met": True,
            "next_action": "assess_a_separately_bounded_private_only_integration_design",
        },
        "interpretation": deepcopy(design._COVERAGE_INTERPRETATION),
        "permissions": deepcopy(design._COVERAGE_FALSE_PERMISSIONS),
        "effects": deepcopy(design._COVERAGE_EFFECTS),
        "limitations": ["test evidence only"],
    }
    document["document_sha256"] = _document_sha256(document)
    return document


def _pilot(
    track_id: str,
    source_hash: str,
    *,
    audible: dict[str, list[int]],
) -> dict[str, object]:
    roles = ("vocals", "instrumental", "reconstruction")
    audible_by_role = {role: list(audible.get(role, [])) for role in roles}
    return {
        "case_kind": "reviewed_song_disjoint_pilot",
        "track_id": track_id,
        "source_audio_sha256": source_hash,
        "reviewed_boundary_count": 2,
        "full_song_ratings": {role: "useful" for role in roles},
        "audible_join_boundaries_by_role": audible_by_role,
        "cannot_tell_boundaries_by_role": {role: [] for role in roles},
        "exact_two_stem_handoff_complete": True,
        "audio_sample_values_changed_in_handoff": False,
    }


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_private_json(path: Path, document: dict[str, object]) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = _document_sha256(document)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
