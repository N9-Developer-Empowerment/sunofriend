from __future__ import annotations

import copy
from pathlib import Path

import pytest

from sunofriend.separation_fine_stem_full_song_plan import (
    FULL_SONG_PLAN_STATUS,
    build_fine_stem_full_song_plan,
    full_song_plan_document_sha256,
    validate_fine_stem_full_song_plan,
)
from sunofriend.separation_fine_stem_integration_outcome import (
    QUALIFIED_STATUS,
    integration_outcome_document_sha256,
)
from sunofriend.separation_target_presence_review import (
    PRESENCE_MANIFEST_SCHEMA,
    PRESENCE_RESULT_SCHEMA,
    presence_document_sha256,
    validate_presence_result,
)


def _source(track_id: str, *, index: int) -> dict:
    return {
        "relative_path": f"{track_id}/source.wav",
        "bytes": 1_000 + index,
        "channels": 2,
        "frames": 480_000 + index * 160,
        "sample_rate_hz": 48_000,
        "sha256": f"{index + 1:064x}",
    }


def _presence_case(
    case_id: str,
    track_id: str,
    target_id: str,
    *,
    index: int,
) -> dict:
    source = _source(track_id, index=index)
    return {
        "case_id": case_id,
        "track_id": track_id,
        "title": track_id.replace("-", " ").title(),
        "target_id": target_id,
        "rights_category": "owned",
        "window_seconds": [index * 15, index * 15 + 15],
        "source_input": source,
        "artifacts": {
            "source": {
                "relative_path": f"CASES/{case_id}/source.wav",
                "bytes": 3_969_044,
                "channels": 2,
                "frames": 661_500,
                "sample_rate_hz": 44_100,
                "sha256": f"{index + 20:064x}",
                "subtype": "PCM_24",
            },
            "hints": [],
        },
    }


def _evidence() -> tuple[dict, dict, dict]:
    cases = [
        _presence_case("both-synth", "both", "synth_keyboard", index=0),
        _presence_case("synth-only", "synth-only", "synth_keyboard", index=1),
        _presence_case("synth-three", "synth-three", "synth_keyboard", index=2),
        _presence_case("synth-four", "synth-four", "synth_keyboard", index=3),
        _presence_case("both-guitar", "both", "guitar", index=0),
        _presence_case("guitar-only", "guitar-only", "guitar", index=4),
        _presence_case("guitar-three", "guitar-three", "guitar", index=5),
        _presence_case("guitar-four", "guitar-four", "guitar", index=6),
    ]
    qualification = {
        "schema": "sunofriend.fine-stem-target-presence-qualification.v1",
        "document_sha256": "",
        "status": "qualified_source_presence_no_model_inference",
        "source_reviews": [],
        "rules": {
            "decision_required": "present",
            "song_disjoint_within_target": True,
        },
        "effects": {},
    }
    qualification["document_sha256"] = presence_document_sha256(qualification)
    manifest = {
        "schema": PRESENCE_MANIFEST_SCHEMA,
        "document_sha256": "",
        "status": "source_presence_pending_no_model_inference",
        "plan_sha256": qualification["document_sha256"],
        "targets": {
            "synth_keyboard": {"label": "Synth"},
            "guitar": {"label": "Guitar"},
        },
        "cases": cases,
        "input_count": len(cases),
        "qualification": qualification,
        "effects": {},
    }
    manifest["document_sha256"] = presence_document_sha256(manifest)
    result = {
        "schema": PRESENCE_RESULT_SCHEMA,
        "document_sha256": "",
        "status": "presence_review_complete_no_model_inference",
        "manifest_sha256": manifest["document_sha256"],
        "qualification_sha256": qualification["document_sha256"],
        "cases": [
            {
                "case_id": case["case_id"],
                "track_id": case["track_id"],
                "target_id": case["target_id"],
                "window_seconds": case["window_seconds"],
                "played_items": ["source"],
                "listened": True,
                "decision": "present",
                "notes": "",
            }
            for case in cases
        ],
        "boundaries": {
            "provider_estimates_are_truth": False,
            "model_inference_started": False,
            "source_selected": False,
            "midi_created": False,
            "audio_uploaded": False,
            "telemetry": False,
        },
    }
    result = validate_presence_result(result, manifest)
    outcome = {
        "schema": "sunofriend.fine-stem-six-role-integration-outcome.v1",
        "document_sha256": "",
        "status": QUALIFIED_STATUS,
        "report_sha256": "a" * 64,
        "review_document_sha256": "b" * 64,
        "plan_sha256": "c" * 64,
        "targets": [
            {
                "target_role": "synth",
                "case_ids": [case["case_id"] for case in cases[:4]],
            },
            {
                "target_role": "guitar",
                "case_ids": [case["case_id"] for case in cases[4:]],
            },
        ],
        "qualified_for_private_six_role_integration": True,
        "boundaries": {
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
            "audio_upload": False,
        },
        "effects": {
            "checkpoint_loads": 0,
            "model_constructions": 0,
            "inference_attempts": 0,
            "audio_reads": 0,
            "audio_writes": 0,
            "network_attempts": 0,
        },
    }
    outcome["document_sha256"] = integration_outcome_document_sha256(outcome)
    return manifest, result, outcome


def _observations(manifest: dict, source_root: Path) -> dict:
    tracks = {case["track_id"]: case["source_input"] for case in manifest["cases"]}
    return {
        track_id: {
            "absolute_path": (source_root / source["relative_path"]).as_posix(),
            "regular_file": True,
            "observed_bytes": source["bytes"],
            "content_opened": False,
        }
        for track_id, source in tracks.items()
        if track_id in {"both", "synth-only", "guitar-only"}
    }


def _plan(tmp_path: Path) -> dict:
    manifest, result, outcome = _evidence()
    return build_fine_stem_full_song_plan(
        presence_manifest=manifest,
        presence_result=result,
        integration_outcome=outcome,
        selections={
            "both_targets": "both",
            "synth": "synth-only",
            "guitar": "guitar-only",
        },
        source_root=tmp_path.as_posix(),
        source_observations=_observations(manifest, tmp_path),
    )


def test_full_song_plan_binds_three_song_disjoint_presence_scopes(
    tmp_path: Path,
) -> None:
    plan = validate_fine_stem_full_song_plan(_plan(tmp_path))

    assert plan["status"] == FULL_SONG_PLAN_STATUS
    assert [case["slot"] for case in plan["cases"]] == [
        "both_targets",
        "synth",
        "guitar",
    ]
    assert plan["cases"][0]["scored_target_roles"] == ["guitar", "synth"]
    assert plan["cases"][1]["scored_target_roles"] == ["synth"]
    assert plan["cases"][1]["unscored_target_roles"] == ["guitar"]
    assert plan["cases"][2]["scored_target_roles"] == ["guitar"]
    assert plan["execution_contract"]["profile_inference_attempts"]["total"] == 9
    assert plan["execution_contract"]["automatic_retry"] is False
    assert plan["admission_policy"]["minimum_usefulness_rating"] is None
    assert plan["review_contract"]["listened_checkbox"] is False
    assert not any(plan["effects"].values())


def test_full_song_plan_rejects_duplicate_song_slots(tmp_path: Path) -> None:
    manifest, result, outcome = _evidence()
    with pytest.raises(ValueError, match="song-disjoint"):
        build_fine_stem_full_song_plan(
            presence_manifest=manifest,
            presence_result=result,
            integration_outcome=outcome,
            selections={
                "both_targets": "both",
                "synth": "synth-only",
                "guitar": "synth-only",
            },
            source_root=tmp_path.as_posix(),
            source_observations=_observations(manifest, tmp_path),
        )


def test_full_song_plan_rejects_unconfirmed_target(tmp_path: Path) -> None:
    manifest, result, outcome = _evidence()
    changed = copy.deepcopy(result)
    changed["cases"][0]["decision"] = "absent"
    changed["document_sha256"] = presence_document_sha256(changed)
    with pytest.raises(ValueError, match="confirmed-present"):
        build_fine_stem_full_song_plan(
            presence_manifest=manifest,
            presence_result=changed,
            integration_outcome=outcome,
            selections={
                "both_targets": "both",
                "synth": "synth-only",
                "guitar": "guitar-only",
            },
            source_root=tmp_path.as_posix(),
            source_observations=_observations(manifest, tmp_path),
        )


def test_full_song_plan_rejects_source_metadata_drift(tmp_path: Path) -> None:
    manifest, result, outcome = _evidence()
    observations = _observations(manifest, tmp_path)
    observations["both"]["observed_bytes"] += 1
    with pytest.raises(ValueError, match="metadata observation"):
        build_fine_stem_full_song_plan(
            presence_manifest=manifest,
            presence_result=result,
            integration_outcome=outcome,
            selections={
                "both_targets": "both",
                "synth": "synth-only",
                "guitar": "guitar-only",
            },
            source_root=tmp_path.as_posix(),
            source_observations=observations,
        )


def test_full_song_plan_hash_detects_permission_change(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    plan["boundaries"]["inference_run"] = True
    plan["document_sha256"] = full_song_plan_document_sha256(plan)
    with pytest.raises(ValueError, match="grants permission"):
        validate_fine_stem_full_song_plan(plan)


def test_full_song_plan_rejects_rehashed_feedback_doom_loop(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    plan["admission_policy"]["minimum_usefulness_rating"] = "useful"
    plan["document_sha256"] = full_song_plan_document_sha256(plan)
    with pytest.raises(ValueError, match="feedback or approval"):
        validate_fine_stem_full_song_plan(plan)
