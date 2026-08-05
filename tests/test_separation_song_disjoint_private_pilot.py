from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import sunofriend._separation_song_disjoint_private_pilot as pilot
from sunofriend._separation_authorised_excerpt import _document_sha256
from sunofriend._separation_full_song_join_remediation_executor_v2 import (
    REPORT_NAME as REFERENCE_REPORT_NAME,
    SCHEMA as REFERENCE_SCHEMA,
    STATUS as REFERENCE_STATUS,
)


def test_automatic_pilot_envelope_stays_pending_and_path_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    os.chmod(tmp_path, 0o700)
    context = _context(tmp_path)
    monkeypatch.setattr(pilot, "_load_context", lambda *args, **kwargs: context)
    monkeypatch.setattr(pilot, "_require_output_disjoint", lambda *args, **kwargs: None)
    output = tmp_path / "result" / pilot.REPORT_NAME

    result = pilot._bind_song_disjoint_private_pilot_evidence(
        "authorization.json",
        reference_v2_execution_path="reference.json",
        plan_report_path="plan.json",
        execution_report_path="execution.json",
        stitch_package_dir="stitch",
        alignment_result_path="alignment.json",
        out=output,
    )

    assert result["status"] == pilot.STATUS
    assert result["readiness"] == {
        "authorization_bound": True,
        "source_distinct_from_authorization_reference": True,
        "automatic_execution_chain_verified": True,
        "exact_source_clock_verified": True,
        "alignment_gate_passed": True,
        "human_full_song_and_boundary_review_complete": False,
        "private_pilot_quality_conclusion_ready": False,
        "public_product_acceptance_complete": False,
        "publication_ready": False,
    }
    assert result["human_review"]["status"] == "pending"
    assert result["human_review"]["boundary_count"] == 2
    assert result["source_distinction"]["song_disjoint_content_check_passed"] is True
    assert all(value is False for value in result["permissions"].values())
    assert result["effects"]["evidence_report_created"] is True
    assert result["effects"]["model_run"] is False
    persisted = output.read_text(encoding="utf-8")
    assert str(tmp_path) not in persisted
    assert os.stat(output).st_mode & 0o777 == 0o600
    assert os.stat(output.parent).st_mode & 0o777 == 0o700
    loaded = pilot._load_verified_song_disjoint_private_pilot_evidence(output)
    assert loaded["sha256"]
    assert loaded["document"]["document_sha256"] == result["document_sha256"]


def test_reference_execution_must_be_exactly_bound_by_authorization(
    tmp_path: Path,
) -> None:
    os.chmod(tmp_path, 0o700)
    report = tmp_path / REFERENCE_REPORT_NAME
    document = _reference_document()
    report.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report.chmod(0o600)
    authorization = {
        "bindings": {"v2_execution_report_sha256": "f" * 64},
        "selected_candidate": {"artifacts": _selected_artifacts()},
    }

    with pytest.raises(ValueError, match="reference execution"):
        pilot._load_reference_v2_execution(report, authorization=authorization)


def test_stitch_chain_rejects_execution_drift() -> None:
    context = _context(Path("/tmp/private-pilot-test"))
    stitch = context["stitch"]
    stitch["bindings"]["execution_state_sha256"] = "f" * 64

    with pytest.raises(ValueError, match="stitch binding"):
        pilot._verify_stitch_chain(
            stitch,
            plan=context["plan"],
            plan_sha256=context["plan_sha256"],
            execution=context["execution"]["document"],
            execution_sha256=context["execution"]["sha256"],
        )


def _context(root: Path) -> dict[str, object]:
    source_sha = "6" * 64
    reference_sha = "5" * 64
    plan_sha = "7" * 64
    execution_sha = "8" * 64
    stitch_sha = "9" * 64
    alignment_sha = "a" * 64
    seed_sha = "b" * 64
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
    authorization_document = {
        "document_sha256": "c" * 64,
        "policy_id": "whole-song-utility-over-microscopic-edge-v1",
        "selected_candidate": {"identity": "followup_control"},
    }
    reference_document = {
        "document_sha256": "d" * 64,
        "bindings": {"source_audio_sha256": reference_sha},
    }
    plan = {
        "document_sha256": "e" * 64,
        "policy_id": "contiguous-canonical-44100-worker-chunks-v1",
        "corpus": {"track_id": "fresh-track", "track_title": "Fresh track"},
        "chunks": [{}, {}, {}],
        "canonical_clock": {
            "sample_rate": 44_100,
            "channels": 2,
            "frames": 1_000,
            "pcm24_int32_sequence_sha256": "1" * 64,
        },
    }
    execution_document = {
        "state_sha256": "2" * 64,
        "bindings": {"checkpoint_sha256": "3" * 64},
        "summary": {"verified_chunks": 3},
    }
    stitch = {
        "document_sha256": "4" * 64,
        "bindings": {
            "plan_report_sha256": plan_sha,
            "plan_document_sha256": plan["document_sha256"],
            "execution_report_sha256": execution_sha,
            "execution_state_sha256": execution_document["state_sha256"],
            "canonical_pcm24_int32_sequence_sha256": plan["canonical_clock"][
                "pcm24_int32_sequence_sha256"
            ],
        },
        "clock": clock,
        "artifacts": {
            "source": {"sha256": source_sha},
            "reconstruction": {"sha256": "0" * 64},
        },
        "boundary_review": {
            "html": "BOUNDARY-REVIEW/separation_boundary_review.html",
            "html_sha256": "f" * 64,
        },
    }
    alignment_document = {
        "document_sha256": "0" * 64,
        "policy_id": "source-reconstruction-spectral-clock-v1",
        "summary": {
            "eligible_window_count": 9,
            "maximum_absolute_lag_milliseconds": 0.0,
            "lag_spread_milliseconds": 0.0,
            "minimum_window_normalized_correlation": 1.0,
            "early_middle_late_coverage_complete": True,
        },
    }
    seed = {
        "status": "unreviewed",
        "package_commitment": "1" * 64,
        "full_song": {
            "audio": {
                "source": {},
                "vocals": {},
                "instrumental": {},
                "reconstruction": {},
            }
        },
        "units": [{}, {}],
    }
    return {
        "authorization": {
            "path": root / "authorization.json",
            "sha256": "2" * 64,
            "document": authorization_document,
        },
        "reference": {
            "path": root / "reference.json",
            "sha256": "3" * 64,
            "document": reference_document,
        },
        "plan_path": root / "plan.json",
        "plan": plan,
        "plan_sha256": plan_sha,
        "execution": {
            "path": root / "execution.json",
            "sha256": execution_sha,
            "document": execution_document,
        },
        "stitch_package": root / "stitch",
        "stitch_path": root / "stitch" / "private-separation-full-song-stitch.json",
        "stitch": stitch,
        "stitch_sha256": stitch_sha,
        "alignment": {
            "path": root / "alignment.json",
            "sha256": alignment_sha,
            "document": alignment_document,
        },
        "review_seed": seed,
        "review_seed_sha256": seed_sha,
    }


def _selected_artifacts() -> dict[str, dict[str, object]]:
    return {
        role: {
            "geometry": {"sample_rate": 44_100, "channels": 2, "frames": 1_000}
        }
        for role in ("vocals", "instrumental", "reconstruction")
    }


def _reference_document() -> dict[str, object]:
    document = {
        "schema": REFERENCE_SCHEMA,
        "status": REFERENCE_STATUS,
        "evidence_scope": "private_development_only",
        "bindings": {"source_audio_sha256": "5" * 64},
        "clock": {
            "sample_rate": 44_100,
            "channels": 2,
            "frames": 1_000,
        },
        "permissions": dict(pilot._REFERENCE_FALSE_PERMISSIONS),
    }
    document["document_sha256"] = _document_sha256(document)
    return document
