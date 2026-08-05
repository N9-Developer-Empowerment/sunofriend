from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

import sunofriend._separation_multi_song_private_pilot_coverage as coverage
from sunofriend._separation_authorised_excerpt import _document_sha256, _sha256


def test_builds_path_free_two_source_private_coverage_without_activation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    output = context["output_parent"] / coverage.REPORT_NAME

    result = coverage._build_multi_song_private_pilot_coverage(
        context["authorization"],
        pilots=[
            (
                context["evidence"],
                context["review"],
                context["handoff"],
            )
        ],
        out=output,
    )

    assert result["status"] == coverage.STATUS
    assert result["coverage"] == {
        "reference_case_count": 1,
        "song_disjoint_pilot_count": 1,
        "distinct_source_count": 2,
        "all_source_hashes_distinct": True,
        "all_song_disjoint_pilots_automatic_chain_verified": True,
        "all_song_disjoint_pilots_full_song_reviewed": True,
        "all_song_disjoint_pilots_full_song_roles_useful": True,
        "all_song_disjoint_pilots_two_stem_handoff_complete": True,
        "reviewed_song_disjoint_boundary_count": 2,
        "reviewed_role_boundary_judgement_count": 6,
        "boundary_rating_totals": {
            "audible_join": 1,
            "cannot_tell": 1,
            "clean": 4,
        },
    }
    assert result["private_evaluation_checkpoint"] == {
        "two_distinct_source_evidence_checkpoint_met": True,
        "minimum_song_disjoint_pilots_before_private_route_design": 2,
        "private_route_design_checkpoint_met": False,
        "next_action": (
            "run_and_review_at_least_one_additional_song_disjoint_private_pilot"
        ),
    }
    assert result["permissions"]["product_route_permitted"] is False
    assert result["permissions"]["publication_permitted"] is False
    assert result["effects"]["model_run"] is False
    assert result["effects"]["coverage_report_created"] is True
    assert os.stat(output.parent).st_mode & 0o777 == 0o700
    assert os.stat(output).st_mode & 0o777 == 0o600
    persisted = output.read_text(encoding="utf-8")
    assert str(tmp_path) not in persisted
    assert "listener note" not in persisted
    document = json.loads(persisted)
    assert document["document_sha256"] == _document_sha256(document)


def test_rejects_duplicate_source_content_across_song_disjoint_pilots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    second = _add_pilot(
        context,
        tmp_path,
        track_id="second-track",
        track_title="Second Track",
        source_sha256=context["pilot_source_sha256"],
    )

    with pytest.raises(ValueError, match="sources are not all distinct"):
        coverage._build_multi_song_private_pilot_coverage(
            context["authorization"],
            pilots=[
                (context["evidence"], context["review"], context["handoff"]),
                (second["evidence"], second["review"], second["handoff"]),
            ],
            out=context["output_parent"] / coverage.REPORT_NAME,
        )


def test_two_song_disjoint_pilots_reach_only_private_route_design_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    second = _add_pilot(
        context,
        tmp_path,
        track_id="another-track",
        track_title="Another Track",
        source_sha256="9" * 64,
    )

    result = coverage._build_multi_song_private_pilot_coverage(
        context["authorization"],
        pilots=[
            (context["evidence"], context["review"], context["handoff"]),
            (second["evidence"], second["review"], second["handoff"]),
        ],
        out=context["output_parent"] / coverage.REPORT_NAME,
    )

    assert result["coverage"]["distinct_source_count"] == 3
    assert result["coverage"]["song_disjoint_pilot_count"] == 2
    assert [case.get("track_id") for case in result["cases"][1:]] == [
        "another-track",
        "track-one",
    ]
    checkpoint = result["private_evaluation_checkpoint"]
    assert checkpoint["private_route_design_checkpoint_met"] is True
    assert checkpoint["next_action"] == (
        "assess_a_separately_bounded_private_only_integration_design"
    )
    assert result["permissions"]["product_route_permitted"] is False
    assert result["effects"]["product_contract_mutated"] is False


def test_rejects_changed_handoff_audio(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    (context["handoff"] / "STEMS/vocals.wav").write_bytes(b"changed")
    os.chmod(context["handoff"] / "STEMS/vocals.wav", 0o600)

    with pytest.raises(ValueError, match="handoff artifact differs"):
        coverage._build_multi_song_private_pilot_coverage(
            context["authorization"],
            pilots=[
                (context["evidence"], context["review"], context["handoff"])
            ],
            out=context["output_parent"] / coverage.REPORT_NAME,
        )


def test_rejects_review_that_does_not_authorize_the_exact_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    document = json.loads(context["review"].read_text(encoding="utf-8"))
    document["bindings"]["pilot_evidence_sha256"] = "f" * 64
    _write_json(context["review"], document)

    with pytest.raises(ValueError, match="review result differs"):
        coverage._build_multi_song_private_pilot_coverage(
            context["authorization"],
            pilots=[
                (context["evidence"], context["review"], context["handoff"])
            ],
            out=context["output_parent"] / coverage.REPORT_NAME,
        )


def test_requires_fresh_named_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    context = _context(tmp_path, monkeypatch)
    pilots = [(context["evidence"], context["review"], context["handoff"])]

    with pytest.raises(ValueError, match="filename"):
        coverage._build_multi_song_private_pilot_coverage(
            context["authorization"],
            pilots=pilots,
            out=context["output_parent"] / "other.json",
        )

    output = context["output_parent"] / coverage.REPORT_NAME
    coverage._build_multi_song_private_pilot_coverage(
        context["authorization"], pilots=pilots, out=output
    )
    with pytest.raises(FileExistsError):
        coverage._build_multi_song_private_pilot_coverage(
            context["authorization"], pilots=pilots, out=output
        )


def _context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    os.chmod(tmp_path, 0o700)
    authorization = _private_file(tmp_path / "authorization.json", b"authorization\n")
    authorization_document = {
        "document_sha256": "a" * 64,
        "selected_candidate": {"identity": "followup_control"},
    }
    authorization_snapshot = {
        "path": authorization,
        "sha256": _sha256(authorization),
        "document": authorization_document,
    }
    context: dict[str, object] = {
        "authorization": authorization,
        "authorization_snapshot": authorization_snapshot,
        "pilot_snapshots": {},
        "reference_source_sha256": "1" * 64,
        "pilot_source_sha256": "2" * 64,
        "output_parent": _private_dir(tmp_path / "outputs"),
    }
    first = _add_pilot(
        context,
        tmp_path,
        track_id="track-one",
        track_title="Track One",
        source_sha256=context["pilot_source_sha256"],
    )
    context.update(first)

    def load_authorization(value: str | Path) -> dict[str, object]:
        assert Path(value) == authorization
        return deepcopy(authorization_snapshot)

    def load_evidence(value: str | Path) -> dict[str, object]:
        return deepcopy(context["pilot_snapshots"][Path(value)])

    monkeypatch.setattr(
        coverage,
        "_load_verified_pragmatic_private_pilot",
        load_authorization,
    )
    monkeypatch.setattr(
        coverage,
        "_load_verified_song_disjoint_private_pilot_evidence",
        load_evidence,
    )
    return context


def _add_pilot(
    context: dict[str, object],
    tmp_path: Path,
    *,
    track_id: str,
    track_title: str,
    source_sha256: str,
) -> dict[str, Path]:
    suffix = track_id.replace("-", "_")
    evidence = _private_file(tmp_path / f"{suffix}-evidence.json", b"evidence\n")
    evidence_document = {
        "document_sha256": "b" * 64,
        "bindings": {
            "pragmatic_authorization_sha256": context["authorization_snapshot"][
                "sha256"
            ],
            "pragmatic_authorization_document_sha256": context[
                "authorization_snapshot"
            ]["document"]["document_sha256"],
            "pilot_stitch_sha256": "3" * 64,
            "pilot_stitch_document_sha256": "4" * 64,
            "pilot_review_seed_sha256": "5" * 64,
            "pilot_review_package_commitment": "6" * 64,
        },
        "source_distinction": {
            "pilot_track_id": track_id,
            "pilot_track_title": track_title,
            "reference_source_audio_sha256": context["reference_source_sha256"],
            "pilot_source_audio_sha256": source_sha256,
        },
        "automatic_execution": {"clock": _clock()},
    }
    evidence_snapshot = {
        "path": evidence,
        "sha256": _sha256(evidence),
        "document": evidence_document,
    }
    context["pilot_snapshots"][evidence] = evidence_snapshot

    review = tmp_path / f"{suffix}-{coverage.REVIEW_REPORT_NAME}"
    review = review.with_name(coverage.REVIEW_REPORT_NAME)
    if review.exists():
        review = _private_dir(tmp_path / f"{suffix}-review") / coverage.REVIEW_REPORT_NAME
    review_document = _review_document(evidence_snapshot)
    _write_json(review, review_document)
    review_sha256 = _sha256(review)

    handoff_root = _private_dir(tmp_path / f"{suffix}-handoff")
    stems = _private_dir(handoff_root / "STEMS")
    diagnostic = _private_dir(handoff_root / "DIAGNOSTIC")
    artifact_bytes = {
        "vocals": f"{track_id}-vocals".encode(),
        "instrumental": f"{track_id}-instrumental".encode(),
        "reconstruction": f"{track_id}-reconstruction".encode(),
    }
    paths = {
        "vocals": stems / "vocals.wav",
        "instrumental": stems / "instrumental.wav",
        "reconstruction": diagnostic / "reconstruction.wav",
    }
    for role, path in paths.items():
        _private_file(path, artifact_bytes[role])
    handoff_document = _handoff_document(
        evidence_snapshot,
        review_document=review_document,
        review_sha256=review_sha256,
        track_id=track_id,
        track_title=track_title,
        source_sha256=source_sha256,
        paths=paths,
    )
    _write_json(handoff_root / coverage.HANDOFF_REPORT_NAME, handoff_document)
    return {"evidence": evidence, "review": review, "handoff": handoff_root}


def _review_document(evidence: dict[str, object]) -> dict[str, object]:
    bindings = evidence["document"]["bindings"]
    document: dict[str, object] = {
        "schema": coverage.REVIEW_SCHEMA,
        "status": coverage.RESULT_STATUS_AUTHORIZED,
        "evidence_scope": "private_development_only",
        "policy_id": coverage.REVIEW_POLICY_ID,
        "bindings": {
            "pilot_evidence_sha256": evidence["sha256"],
            "pilot_evidence_document_sha256": evidence["document"][
                "document_sha256"
            ],
            "pilot_stitch_sha256": bindings["pilot_stitch_sha256"],
            "pilot_stitch_document_sha256": bindings[
                "pilot_stitch_document_sha256"
            ],
            "pilot_review_seed_sha256": bindings["pilot_review_seed_sha256"],
            "pilot_review_package_commitment": bindings[
                "pilot_review_package_commitment"
            ],
            "review_export_sha256": "7" * 64,
            "verified_full_song_review_document_sha256": "8" * 64,
        },
        "clock": _clock(),
        "review_summary": {
            "full_song_heard_all": True,
            "full_song_ratings": {role: "useful" for role in coverage._ROLES},
            "reviewed_boundary_count": 2,
            "boundary_rating_counts_by_role": {
                "vocals": {"audible_join": 1, "cannot_tell": 0, "clean": 1},
                "instrumental": {
                    "audible_join": 0,
                    "cannot_tell": 1,
                    "clean": 1,
                },
                "reconstruction": {
                    "audible_join": 0,
                    "cannot_tell": 0,
                    "clean": 2,
                },
            },
            "audible_join_boundaries_by_role": {
                "vocals": [1],
                "instrumental": [],
                "reconstruction": [],
            },
            "cannot_tell_boundaries_by_role": {
                "vocals": [],
                "instrumental": [2],
                "reconstruction": [],
            },
            "all_boundaries_clean": False,
            "listener_notes_copied": False,
        },
        "private_pilot_assessment": {
            "all_generated_full_song_roles_useful": True,
            "bounded_private_pilot_output_use_permitted": True,
            "selection_scope": "this_exact_reviewed_private_output_only",
            "boundary_findings_retained_as_diagnostics": True,
            "boundary_findings_are_an_automatic_veto": False,
            "model_run_required": False,
            "next_action": "continue_bounded_multi_song_private_evaluation",
        },
        "readiness": {
            "automatic_pilot_evidence_complete": True,
            "human_full_song_and_boundary_review_complete": True,
            "whole_song_utility_conclusion_ready": True,
            "bounded_private_pilot_output_use_permitted": True,
            "separator_accuracy_ground_truth_established": False,
            "public_product_acceptance_complete": False,
            "publication_ready": False,
        },
        "permissions": deepcopy(coverage._REVIEW_PERMISSIONS),
        "effects": deepcopy(coverage._REVIEW_EFFECTS),
        "limitations": ["listener note is not copied"],
    }
    document["document_sha256"] = _document_sha256(document)
    return document


def _handoff_document(
    evidence: dict[str, object],
    *,
    review_document: dict[str, object],
    review_sha256: str,
    track_id: str,
    track_title: str,
    source_sha256: str,
    paths: dict[str, Path],
) -> dict[str, object]:
    geometry = {
        "channels": 2,
        "frames": 132300,
        "sample_rate": 44100,
        "sample_width_bytes": 3,
    }
    relative_paths = {
        "vocals": "STEMS/vocals.wav",
        "instrumental": "STEMS/instrumental.wav",
        "reconstruction": "DIAGNOSTIC/reconstruction.wav",
    }
    document: dict[str, object] = {
        "schema": coverage.HANDOFF_SCHEMA,
        "status": coverage.HANDOFF_STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": coverage.HANDOFF_POLICY_ID,
        "bindings": {
            "pilot_evidence_sha256": evidence["sha256"],
            "pilot_evidence_document_sha256": evidence["document"][
                "document_sha256"
            ],
            "review_result_sha256": review_sha256,
            "review_result_document_sha256": review_document["document_sha256"],
            "review_export_sha256": review_document["bindings"][
                "review_export_sha256"
            ],
            "source_audio_sha256": source_sha256,
            "stitch_report_sha256": evidence["document"]["bindings"][
                "pilot_stitch_sha256"
            ],
            "stitch_document_sha256": evidence["document"]["bindings"][
                "pilot_stitch_document_sha256"
            ],
        },
        "track": {"track_id": track_id, "track_title": track_title},
        "clock": _clock(),
        "handoff": {
            "kind": "two_stem_vocals_and_instrumental",
            "primary_roles": list(coverage._PRIMARY_ROLES),
            "diagnostic_roles": ["reconstruction"],
            "source_audio_included": False,
            "audio_sample_values_changed": False,
            "all_copies_match_reviewed_stitch_sha256": True,
            "private_pilot_scope": "this_exact_reviewed_output_only",
        },
        "artifacts": {
            role: {
                "path": relative_paths[role],
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
                "geometry": deepcopy(geometry),
                "copied_byte_identically": True,
                "sample_values_changed": False,
            }
            for role, path in paths.items()
        },
        "human_review": {
            "full_song_ratings": review_document["review_summary"][
                "full_song_ratings"
            ],
            "reviewed_boundary_count": review_document["review_summary"][
                "reviewed_boundary_count"
            ],
            "audible_join_boundaries_by_role": review_document["review_summary"][
                "audible_join_boundaries_by_role"
            ],
            "cannot_tell_boundaries_by_role": review_document["review_summary"][
                "cannot_tell_boundaries_by_role"
            ],
            "listener_notes_copied": False,
        },
        "readiness": {
            "automatic_pilot_evidence_complete": True,
            "human_review_complete": True,
            "exact_output_authorized_for_bounded_private_pilot": True,
            "two_stem_handoff_complete": True,
            "separator_selected_or_accepted": False,
            "public_product_acceptance_complete": False,
            "publication_ready": False,
        },
        "permissions": deepcopy(coverage._HANDOFF_PERMISSIONS),
        "effects": deepcopy(coverage._HANDOFF_EFFECTS),
        "limitations": ["private only"],
    }
    document["document_sha256"] = _document_sha256(document)
    return document


def _clock() -> dict[str, int | float]:
    return {
        "boundary_count": 2,
        "channels": 2,
        "chunk_count": 3,
        "crossfade_frames": 0,
        "duration_seconds": 3.0,
        "frames": 132300,
        "gap_frames": 0,
        "overlap_frames": 0,
        "sample_rate": 44100,
    }


def _private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def _private_file(path: Path, contents: bytes) -> Path:
    path.write_bytes(contents)
    os.chmod(path, 0o600)
    return path


def _write_json(path: Path, document: dict[str, object]) -> None:
    document["document_sha256"] = _document_sha256(document)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    os.chmod(path, 0o600)
