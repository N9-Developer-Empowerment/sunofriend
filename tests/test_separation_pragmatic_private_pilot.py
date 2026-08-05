from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from sunofriend._separation_authorised_excerpt import _document_sha256
from sunofriend._separation_pragmatic_private_pilot import (
    POLICY_ID,
    REPORT_NAME,
    SCHEMA,
    STATUS,
    _EFFECTS,
    _PERMISSIONS,
    _load_verified_pragmatic_private_pilot,
    _path_free_artifact_binding,
    _require_pragmatic_gate,
    _validated_absolute_assessment,
    _validated_persisted_review_summary,
    _validated_review_summary,
)


def test_whole_song_good_enough_can_pass_despite_microscopic_edge_ambiguity() -> None:
    assessment = _assessment()
    summary = _validated_review_summary(_review_result())

    _require_pragmatic_gate(assessment, review_summary=summary)

    assert summary == {
        "reviewed_unit_count": 36,
        "choice_counts": {
            "equivalent": 25,
            "followup_control_preferred": 2,
            "neither": 9,
        },
        "followup_control_preference_count": 2,
        "replacement_variant_preference_count": 0,
        "replacement_variant_showed_audible_advantage": False,
    }


def test_normal_listening_join_problem_blocks_private_pilot() -> None:
    assessment = _assessment()
    assessment["joins_generally_noticeable"] = True

    with pytest.raises(ValueError, match="private-pilot gate"):
        _require_pragmatic_gate(
            assessment,
            review_summary=_validated_review_summary(_review_result()),
        )


def test_replacement_preference_blocks_automatic_control_selection() -> None:
    result = _review_result()
    result["units"][0]["resolved_choice"] = "shifted_variant_preferred"

    with pytest.raises(ValueError, match="private-pilot gate"):
        _require_pragmatic_gate(
            _assessment(), review_summary=_validated_review_summary(result)
        )


def test_quality_labels_do_not_accept_poor_or_cannot_tell() -> None:
    assessment = _assessment()
    assessment["overall_audio_quality"] = "poor"

    with pytest.raises(ValueError, match="assessment values"):
        _validated_absolute_assessment(assessment)


def test_artifact_binding_excludes_source_path() -> None:
    artifact = {
        "path": "CANDIDATES/vocals.wav",
        "sha256": "a" * 64,
        "pcm24_int32_sequence_sha256": "b" * 64,
        "bytes": 123,
        "geometry": {
            "channels": 2,
            "frames": 100,
            "sample_rate": 44_100,
            "sample_width_bytes": 3,
        },
    }

    binding = _path_free_artifact_binding(artifact, role="vocals")

    assert binding["role"] == "vocals"
    assert "path" not in binding


def test_sealed_pragmatic_authorization_can_be_reused_without_review_replay(
    tmp_path: Path,
) -> None:
    os.chmod(tmp_path, 0o700)
    report = tmp_path / REPORT_NAME
    document = _authorization_document()
    report.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report.chmod(0o600)

    snapshot = _load_verified_pragmatic_private_pilot(report)

    assert snapshot["document"]["readiness"]["bounded_private_pilot_ready"] is True
    assert snapshot["document"]["permissions"]["publication_permitted"] is False


def test_persisted_summary_rejects_inconsistent_count() -> None:
    summary = _authorization_document()["comparative_review_summary"]
    summary["reviewed_unit_count"] = 35

    with pytest.raises(ValueError, match="review summary"):
        _validated_persisted_review_summary(summary)


def _assessment() -> dict[str, object]:
    return _validated_absolute_assessment(
        {
            "overall_audio_quality": "good_or_good_enough",
            "listener_assessed_separator_accuracy": "good_or_good_enough",
            "joins_generally_noticeable": False,
            "joins_detectable_when_cued_with_concentrated_headphones": True,
            "joins_reduce_musical_usefulness": False,
            "patch_edge_beat_ambiguity_present": True,
        }
    )


def _review_result() -> dict[str, object]:
    choices = (
        ["equivalent"] * 25
        + ["followup_control_preferred"] * 2
        + ["neither"] * 9
    )
    return {"units": [{"resolved_choice": choice} for choice in choices]}


def _authorization_document() -> dict[str, object]:
    artifact = {
        "role": "",
        "sha256": "a" * 64,
        "pcm24_int32_sequence_sha256": "b" * 64,
        "bytes": 6_044,
        "geometry": {
            "channels": 2,
            "frames": 1_000,
            "sample_rate": 44_100,
            "sample_width_bytes": 3,
        },
    }
    artifacts = {}
    for index, role in enumerate(("vocals", "instrumental", "reconstruction")):
        item = dict(artifact)
        item["role"] = role
        item["sha256"] = f"{index + 1:064x}"
        item["pcm24_int32_sequence_sha256"] = f"{index + 11:064x}"
        artifacts[role] = item
    document = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "followup_control_report_sha256": "1" * 64,
            "v2_execution_report_sha256": "2" * 64,
        },
        "comparative_review_summary": {
            "reviewed_unit_count": 36,
            "choice_counts": {
                "equivalent": 25,
                "followup_control_preferred": 2,
                "neither": 9,
            },
            "followup_control_preference_count": 2,
            "replacement_variant_preference_count": 0,
            "replacement_variant_showed_audible_advantage": False,
        },
        "human_absolute_assessment": _assessment(),
        "pragmatic_private_pilot_gate": {
            "passed": True,
            "selected_candidate_identity": "followup_control",
            "selection_scope": "bounded_private_pilot_only",
            "new_model_run_required": False,
        },
        "readiness": {
            "bounded_private_pilot_ready": True,
            "whole_song_utility_gate_passed": True,
            "public_product_acceptance_complete": False,
            "publication_ready": False,
        },
        "selected_candidate": {
            "identity": "followup_control",
            "candidate_report_sha256": "1" * 64,
            "candidate_document_sha256": "3" * 64,
            "artifacts": artifacts,
        },
        "permissions": dict(_PERMISSIONS),
        "effects": dict(_EFFECTS),
    }
    document["document_sha256"] = _document_sha256(document)
    return document
