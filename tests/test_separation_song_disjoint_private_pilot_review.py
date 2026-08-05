from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path

import pytest

import sunofriend._separation_song_disjoint_private_pilot_review as review_policy
from sunofriend._separation_authorised_excerpt import _document_sha256
from sunofriend._separation_full_song_review import (
    SCHEMA as FULL_SONG_REVIEW_SCHEMA,
    STATUS as FULL_SONG_REVIEW_STATUS,
    _FALSE_EFFECTS as FULL_SONG_FALSE_EFFECTS,
)
from sunofriend._separation_full_song_stitch import _FALSE_PERMISSIONS


def test_status_verifies_without_authorizing_or_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _fake_inputs(tmp_path, monkeypatch)

    status = review_policy._status_private_song_disjoint_pilot_review(
        context["review"],
        pilot_evidence_path=context["pilot"],
        package_dir=context["package"],
    )

    assert status["status"] == "complete_review_verified_no_activation"
    assert status["assessment_preview"] == {
        "all_generated_full_song_roles_useful": True,
        "would_authorize_bounded_private_pilot_output_use": True,
        "boundary_findings_are_an_automatic_veto": False,
    }
    assert status["permissions"]["bounded_private_pilot_output_use"] is False
    assert status["effects"]["review_result_created"] is False
    assert not list(tmp_path.glob("**/verified-full-song-review.json"))


def test_resolution_authorizes_exact_useful_output_and_retains_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _fake_inputs(tmp_path, monkeypatch)
    output_parent = _private_dir(tmp_path / "result")
    output = output_parent / review_policy.REPORT_NAME

    result = review_policy._resolve_private_song_disjoint_pilot_review(
        context["review"],
        pilot_evidence_path=context["pilot"],
        package_dir=context["package"],
        out=output,
    )

    assert result["status"] == review_policy.RESULT_STATUS_AUTHORIZED
    assert result["private_pilot_assessment"] == {
        "all_generated_full_song_roles_useful": True,
        "bounded_private_pilot_output_use_permitted": True,
        "selection_scope": "this_exact_reviewed_private_output_only",
        "boundary_findings_retained_as_diagnostics": True,
        "boundary_findings_are_an_automatic_veto": False,
        "model_run_required": False,
        "next_action": "continue_bounded_multi_song_private_evaluation",
    }
    assert result["review_summary"]["audible_join_boundaries_by_role"] == {
        "vocals": [1],
        "instrumental": [],
        "reconstruction": [],
    }
    assert result["review_summary"]["cannot_tell_boundaries_by_role"] == {
        "vocals": [],
        "instrumental": [2],
        "reconstruction": [1],
    }
    assert result["review_summary"]["all_boundaries_clean"] is False
    assert result["permissions"]["bounded_private_pilot_output_use"] is True
    assert result["permissions"]["product_route_permitted"] is False
    assert result["effects"]["bounded_private_pilot_output_authorized"] is True
    assert result["effects"]["separator_accepted"] is False
    persisted = output.read_text(encoding="utf-8")
    assert str(tmp_path) not in persisted
    assert "private listener note" not in persisted
    assert os.stat(output).st_mode & 0o777 == 0o600


def test_resolution_does_not_authorize_when_one_complete_role_is_not_useful(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review_result = _review_result()
    review_result["full_song"]["ratings"]["vocals"] = "noticeable_problems"
    review_result["document_sha256"] = _document_sha256(review_result)
    context = _fake_inputs(tmp_path, monkeypatch, review_result=review_result)
    output = _private_dir(tmp_path / "result") / review_policy.REPORT_NAME

    result = review_policy._resolve_private_song_disjoint_pilot_review(
        context["review"],
        pilot_evidence_path=context["pilot"],
        package_dir=context["package"],
        out=output,
    )

    assert result["status"] == review_policy.RESULT_STATUS_NOT_AUTHORIZED
    assert result["permissions"]["bounded_private_pilot_output_use"] is False
    assert result["private_pilot_assessment"]["next_action"] == (
        "retain_output_for_diagnosis_or_bounded_remediation"
    )


def test_review_must_bind_the_exact_sealed_pilot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review_result = _review_result()
    review_result["bindings"]["package_commitment"] = "f" * 64
    review_result["document_sha256"] = _document_sha256(review_result)
    context = _fake_inputs(tmp_path, monkeypatch, review_result=review_result)

    with pytest.raises(ValueError, match="review binding"):
        review_policy._status_private_song_disjoint_pilot_review(
            context["review"],
            pilot_evidence_path=context["pilot"],
            package_dir=context["package"],
        )


def _fake_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    review_result: dict[str, object] | None = None,
) -> dict[str, Path]:
    os.chmod(tmp_path, 0o700)
    package = _private_dir(tmp_path / "package")
    pilot_path = _private_file(tmp_path / "pilot.json", b"pilot\n")
    review_path = _private_file(tmp_path / "review.json", b"review\n")
    pilot_document = _pilot_document()
    pilot_snapshot = {
        "path": pilot_path,
        "sha256": "1" * 64,
        "document": pilot_document,
    }
    result = deepcopy(review_result or _review_result())
    monkeypatch.setattr(
        review_policy,
        "_load_verified_song_disjoint_private_pilot_evidence",
        lambda value: pilot_snapshot,
    )
    monkeypatch.setattr(
        review_policy,
        "_resolve_private_separation_full_song_review",
        lambda *args, **kwargs: {**deepcopy(result), "report": str(kwargs["out"])},
    )
    return {"package": package, "pilot": pilot_path, "review": review_path}


def _pilot_document() -> dict[str, object]:
    clock = {
        "sample_rate": 44_100,
        "channels": 2,
        "frames": 1_000,
        "duration_seconds": 1_000 / 44_100,
        "chunk_count": 3,
        "boundary_count": 2,
        "gap_frames": 0,
        "overlap_frames": 0,
        "crossfade_frames": 0,
    }
    return {
        "document_sha256": "2" * 64,
        "bindings": {
            "pilot_stitch_sha256": "3" * 64,
            "pilot_stitch_document_sha256": "4" * 64,
            "pilot_review_seed_sha256": "5" * 64,
            "pilot_review_package_commitment": "6" * 64,
        },
        "automatic_execution": {"clock": clock},
        "human_review": {"boundary_count": 2},
    }


def _review_result() -> dict[str, object]:
    clock = _pilot_document()["automatic_execution"]["clock"]
    result: dict[str, object] = {
        "schema": FULL_SONG_REVIEW_SCHEMA,
        "status": FULL_SONG_REVIEW_STATUS,
        "evidence_scope": "private_development_only",
        "bindings": {
            "stitch_report_sha256": "3" * 64,
            "stitch_document_sha256": "4" * 64,
            "review_seed_sha256": "5" * 64,
            "review_export_sha256": "7" * 64,
            "package_commitment": "6" * 64,
            "plan_document_sha256": "8" * 64,
            "execution_state_sha256": "9" * 64,
        },
        "clock": deepcopy(clock),
        "full_song": {
            "heard_all": True,
            "ratings": {
                "vocals": "useful",
                "instrumental": "useful",
                "reconstruction": "useful",
            },
            "notes": "private listener note",
        },
        "boundary_summary": {
            "reviewed_boundaries": 2,
            "rating_counts_by_role": {
                "vocals": {"audible_join": 1, "cannot_tell": 0, "clean": 1},
                "instrumental": {
                    "audible_join": 0,
                    "cannot_tell": 1,
                    "clean": 1,
                },
                "reconstruction": {
                    "audible_join": 0,
                    "cannot_tell": 1,
                    "clean": 1,
                },
            },
            "audible_join_boundaries_by_role": {
                "vocals": [1],
                "instrumental": [],
                "reconstruction": [],
            },
        },
        "boundaries": [
            {
                "boundary_index": 1,
                "frame": 400,
                "seconds": 400 / 44_100,
                "ratings": {
                    "vocals": "audible_join",
                    "instrumental": "clean",
                    "reconstruction": "cannot_tell",
                },
                "notes": "private listener note",
            },
            {
                "boundary_index": 2,
                "frame": 700,
                "seconds": 700 / 44_100,
                "ratings": {
                    "vocals": "clean",
                    "instrumental": "cannot_tell",
                    "reconstruction": "clean",
                },
                "notes": "private listener note",
            },
        ],
        "readiness": {
            "worker_runs_complete": True,
            "stitched_outputs_complete": True,
            "exact_duration_and_frame_count_verified": True,
            "full_song_and_boundary_listening_complete": True,
            "full_song_quality_accepted": False,
            "publication_ready": False,
        },
        "interpretation": {},
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(FULL_SONG_FALSE_EFFECTS),
    }
    result["bindings"]["review_export_sha256"] = _sha256_bytes(b"review\n")
    result["document_sha256"] = _document_sha256(result)
    return result


def _private_dir(path: Path) -> Path:
    path.mkdir(parents=True)
    path.chmod(0o700)
    return path


def _private_file(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    path.chmod(0o600)
    return path


def _sha256_bytes(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()
