from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil

import numpy as np
import pytest
import soundfile

from sunofriend._separation_authorised_excerpt import _document_sha256, _sha256
from sunofriend._separation_candidate_followup_variant_review import (
    _prepare_private_candidate_followup_variant_review,
)
from sunofriend._separation_candidate_followup_variant_review_result import (
    RESULT_SCHEMA,
    STATUS_SCHEMA,
    _resolve_private_candidate_followup_variant_review,
    _status_private_candidate_followup_variant_review,
)
from sunofriend._separation_candidate_join_remediation_review import (
    ANSWER_KEY_NAME,
    REPORT_NAME,
)

SAMPLE_RATE = 44_100


def test_status_is_key_blind_and_resolution_records_no_selection(
    tmp_path: Path, monkeypatch
) -> None:
    context = _context(tmp_path)
    _patch_context(monkeypatch, context)
    package = tmp_path / "review"
    _prepare_private_candidate_followup_variant_review(
        context["plan_snapshot"]["path"],
        execution_dir=context["base_root"],
        v2_execution_dir=context["v2_root"],
        variant_execution_dir=context["variant_root"],
        out_dir=package,
    )
    reviewed_path = _completed_review(package, tmp_path / "reviewed.json")

    answer = package / ANSWER_KEY_NAME
    hidden_answer = package / f"{ANSWER_KEY_NAME}.hidden"
    answer.rename(hidden_answer)
    status = _status_private_candidate_followup_variant_review(
        reviewed_path,
        plan_path=context["plan_snapshot"]["path"],
        review_package_dir=package,
        execution_dir=context["base_root"],
        v2_execution_dir=context["v2_root"],
        variant_execution_dir=context["variant_root"],
    )
    hidden_answer.rename(answer)

    assert status["schema"] == STATUS_SCHEMA
    assert status["status"] == "complete_review_verified_key_unopened"
    assert status["reviewed_units"] == 15
    assert status["audio_references_verified"] == 30
    assert status["unique_audio_files_verified"] == 27
    assert status["pcm24_identical_short_pairs"] == 0
    assert status["answer_key_opened"] is False
    assert status["identity_mapping_revealed"] is False
    assert status["document_sha256"] == _document_sha256(status)
    assert all(value is False for value in status["permissions"].values())
    assert all(value is False for value in status["effects"].values())

    result = _resolve_private_candidate_followup_variant_review(
        reviewed_path,
        plan_path=context["plan_snapshot"]["path"],
        review_package_dir=package,
        execution_dir=context["base_root"],
        v2_execution_dir=context["v2_root"],
        variant_execution_dir=context["variant_root"],
        out=tmp_path / "result" / "resolved.json",
    )
    assert result["schema"] == RESULT_SCHEMA
    assert result["status"] == "complete_review_no_activation"
    assert result["reviewed_unit_count"] == 15
    assert result["overall_outcome_counts"]["equivalent"] == 15
    assert result["fresh_all_boundary_review_eligible_variant_ids"] == []
    assert len(result["inherited_pcm24_identical_units"]) == 3
    assert result["readiness_evidence"]["variant_review_complete"] is True
    assert result["readiness_evidence"]["variant_selected"] is False
    assert result["readiness_evidence"]["publication_ready"] is False
    persisted = _read(Path(result["report"]))
    assert result["document_sha256"] == _document_sha256(persisted)
    assert all(value is False for value in result["permissions"].values())
    assert all(value is False for value in result["effects"].values())


def test_status_rejects_incomplete_browser_export(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    _patch_context(monkeypatch, context)
    package = tmp_path / "review"
    _prepare_private_candidate_followup_variant_review(
        context["plan_snapshot"]["path"],
        execution_dir=context["base_root"],
        v2_execution_dir=context["v2_root"],
        variant_execution_dir=context["variant_root"],
        out_dir=package,
    )
    seed = _read(package / REPORT_NAME)
    reviewed = deepcopy(seed)
    reviewed["status"] = "reviewed"
    reviewed["summary"] = {
        "reviewed_units": len(reviewed["units"]) - 1,
        "total_units": len(reviewed["units"]),
        "complete": False,
    }
    for unit in reviewed["units"][:-1]:
        unit["heard"] = {"A": True, "B": True}
        unit["choice"] = "equivalent"
    reviewed_path = _write_private_json(tmp_path / "incomplete.json", reviewed)

    with pytest.raises(ValueError, match="incomplete"):
        _status_private_candidate_followup_variant_review(
            reviewed_path,
            plan_path=context["plan_snapshot"]["path"],
            review_package_dir=package,
            execution_dir=context["base_root"],
            v2_execution_dir=context["v2_root"],
            variant_execution_dir=context["variant_root"],
        )


def test_status_rejects_unreferenced_package_audio(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    _patch_context(monkeypatch, context)
    package = tmp_path / "review"
    _prepare_private_candidate_followup_variant_review(
        context["plan_snapshot"]["path"],
        execution_dir=context["base_root"],
        v2_execution_dir=context["v2_root"],
        variant_execution_dir=context["variant_root"],
        out_dir=package,
    )
    reviewed_path = _completed_review(package, tmp_path / "reviewed.json")
    extra = package / "audio" / "unreferenced.wav"
    extra.write_bytes(b"not audio")
    extra.chmod(0o600)

    with pytest.raises(ValueError, match="inventory"):
        _status_private_candidate_followup_variant_review(
            reviewed_path,
            plan_path=context["plan_snapshot"]["path"],
            review_package_dir=package,
            execution_dir=context["base_root"],
            v2_execution_dir=context["v2_root"],
            variant_execution_dir=context["variant_root"],
        )


def test_resolution_can_leave_both_variants_eligible_without_selecting_one(
    tmp_path: Path, monkeypatch
) -> None:
    context = _context(tmp_path)
    _patch_context(monkeypatch, context)
    package = tmp_path / "review"
    _prepare_private_candidate_followup_variant_review(
        context["plan_snapshot"]["path"],
        execution_dir=context["base_root"],
        v2_execution_dir=context["v2_root"],
        variant_execution_dir=context["variant_root"],
        out_dir=package,
    )
    review = deepcopy(_read(package / REPORT_NAME))
    answer = _read(package / ANSWER_KEY_NAME)
    answers = {item["unit_id"]: item for item in answer["units"]}
    review["status"] = "reviewed"
    review["summary"] = {
        "reviewed_units": len(review["units"]),
        "total_units": len(review["units"]),
        "complete": True,
    }
    for unit in review["units"]:
        unit["heard"] = {"A": True, "B": True}
        unit["notes"] = ""
        prefer_candidate = (
            unit["kind"] == "boundary_role_pair" and "instrumental" in unit["unit_id"]
        ) or (
            unit["kind"] == "patch_edge_pair"
            and "vocals" in unit["unit_id"]
            and unit["unit_id"].endswith("-end-edge")
        )
        if prefer_candidate:
            assignment = answers[unit["unit_id"]]["assignment"]
            unit["choice"] = next(
                slot
                for slot, identity in assignment.items()
                if identity != "followup_control"
            )
        else:
            unit["choice"] = "equivalent"
    reviewed_path = _write_private_json(tmp_path / "gate-reviewed.json", review)

    result = _resolve_private_candidate_followup_variant_review(
        reviewed_path,
        plan_path=context["plan_snapshot"]["path"],
        review_package_dir=package,
        execution_dir=context["base_root"],
        v2_execution_dir=context["v2_root"],
        variant_execution_dir=context["variant_root"],
        out=tmp_path / "gate-result" / "resolved.json",
    )

    assert result["fresh_all_boundary_review_eligible_variant_ids"] == [
        "shifted-context-standard-edge",
        "preserved-centre-extended-edge",
    ]
    assert result["readiness_evidence"]["variant_selected"] is False
    assert all(
        evidence["eligible_for_fresh_all_boundary_review"] is True
        and evidence["selected"] is False
        for evidence in result["candidate_gate_evidence"].values()
    )
    assert all(value is False for value in result["effects"].values())


def test_identical_short_pairs_verify_without_resolving_a_blind_letter_identity(
    tmp_path: Path, monkeypatch
) -> None:
    context = _context(tmp_path)
    control = context["base_paths"]["instrumental"]
    for candidate_id in (
        "shifted-context-standard-edge",
        "preserved-centre-extended-edge",
    ):
        candidate = context["variant_paths"][candidate_id]["instrumental"]
        shutil.copyfile(control, candidate)
        candidate.chmod(0o600)
    _patch_context(monkeypatch, context)
    package = tmp_path / "review"
    _prepare_private_candidate_followup_variant_review(
        context["plan_snapshot"]["path"],
        execution_dir=context["base_root"],
        v2_execution_dir=context["v2_root"],
        variant_execution_dir=context["variant_root"],
        out_dir=package,
    )
    review = deepcopy(_read(package / REPORT_NAME))
    review["status"] = "reviewed"
    review["summary"] = {
        "reviewed_units": len(review["units"]),
        "total_units": len(review["units"]),
        "complete": True,
    }
    for unit in review["units"]:
        unit["heard"] = {"A": True, "B": True}
        unit["choice"] = "A" if "instrumental" in unit["unit_id"] else "equivalent"
        unit["notes"] = ""
    reviewed_path = _write_private_json(tmp_path / "identical-reviewed.json", review)

    status = _status_private_candidate_followup_variant_review(
        reviewed_path,
        plan_path=context["plan_snapshot"]["path"],
        review_package_dir=package,
        execution_dir=context["base_root"],
        v2_execution_dir=context["v2_root"],
        variant_execution_dir=context["variant_root"],
    )
    assert status["pcm24_identical_short_pairs"] == 3

    result = _resolve_private_candidate_followup_variant_review(
        reviewed_path,
        plan_path=context["plan_snapshot"]["path"],
        review_package_dir=package,
        execution_dir=context["base_root"],
        v2_execution_dir=context["v2_root"],
        variant_execution_dir=context["variant_root"],
        out=tmp_path / "identical-result" / "resolved.json",
    )
    identical_units = [item for item in result["units"] if item["pcm24_identical"]]
    identical_short_units = [
        item for item in identical_units if item["kind"] != "complete_song_pair"
    ]
    assert len(identical_short_units) == 3
    assert all(item["resolved_choice"] == "equivalent" for item in identical_units)
    assert all(
        item["blind_letter_preference_identity_suppressed"] is True
        for item in identical_units
    )


def _patch_context(monkeypatch, context: dict[str, object]) -> None:
    for module in (
        "sunofriend._separation_candidate_followup_variant_review",
        "sunofriend._separation_candidate_followup_variant_review_result",
    ):
        monkeypatch.setattr(
            f"{module}._load_verified_variant_inputs",
            lambda *args, **kwargs: context,
        )


def _completed_review(package: Path, path: Path) -> Path:
    review = deepcopy(_read(package / REPORT_NAME))
    review["status"] = "reviewed"
    review["summary"] = {
        "reviewed_units": len(review["units"]),
        "total_units": len(review["units"]),
        "complete": True,
    }
    for unit in review["units"]:
        unit["heard"] = {"A": True, "B": True}
        unit["choice"] = "equivalent"
        unit["notes"] = ""
    return _write_private_json(path, review)


def _write_private_json(path: Path, value: dict[str, object]) -> Path:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    path.chmod(0o600)
    return path


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _context(tmp_path: Path) -> dict[str, object]:
    tmp_path.chmod(0o700)
    frames = 6 * SAMPLE_RATE
    time = np.arange(frames, dtype="float64") / SAMPLE_RATE
    base_values = {
        "vocals": _stereo(0.08 * np.sin(2 * np.pi * 220 * time)),
        "instrumental": _stereo(0.11 * np.sin(2 * np.pi * 110 * time)),
    }
    base_values["reconstruction"] = base_values["vocals"] + base_values["instrumental"]
    base_root = _private_directory(tmp_path / "followup-control")
    v2_root = _private_directory(tmp_path / "v2")
    variant_root = _private_directory(tmp_path / "variants")
    standard_root = _private_directory(variant_root / "standard")
    preserved_root = _private_directory(variant_root / "preserved")
    base_paths = {
        role: _write_audio(base_root / f"{role}.wav", values)
        for role, values in base_values.items()
    }
    variant_paths: dict[str, dict[str, Path]] = {}
    for variant_id, root, scales in (
        (
            "shifted-context-standard-edge",
            standard_root,
            {"vocals": 0.92, "instrumental": 0.92, "reconstruction": 0.92},
        ),
        (
            "preserved-centre-extended-edge",
            preserved_root,
            {"vocals": 0.86, "instrumental": 0.92, "reconstruction": 0.86},
        ),
    ):
        variant_paths[variant_id] = {
            role: _write_audio(root / f"{role}.wav", values * scales[role])
            for role, values in base_values.items()
        }

    plan_path = _write_private_json(tmp_path / "plan.json", {"kind": "plan"})
    execution_path = _write_private_json(
        variant_root / "execution.json", {"kind": "run"}
    )
    candidates_path = _write_private_json(
        variant_root / "candidates.json", {"kind": "candidates"}
    )
    control_execution_path = _write_private_json(
        base_root / "execution.json", {"kind": "control-run"}
    )
    control_candidate_path = _write_private_json(
        base_root / "candidate.json", {"kind": "control-candidate"}
    )
    v2_path = _write_private_json(v2_root / "execution.json", {"kind": "v2"})
    plan = {
        "document_sha256": "a" * 64,
        "protocol": {
            "candidate_variants": [
                {
                    "variant_id": "shifted-context-standard-edge",
                    "failed_edge_source": "shifted_context_worker",
                },
                {
                    "variant_id": "preserved-centre-extended-edge",
                    "failed_edge_source": "exact_followup_candidate_patch",
                },
            ]
        },
        "windows": [
            {
                "boundary_index": 4,
                "role_actions": {
                    "vocals": {
                        "action": "edge_aware_reinference_and_blend_search",
                        "patch_start_frame": 2 * SAMPLE_RATE,
                        "patch_end_frame": 4 * SAMPLE_RATE,
                        "failed_edges": [{"edge": "end", "outcome": "neither"}],
                    },
                    "instrumental": {
                        "action": "fresh_window_reinference_and_blend_search",
                        "patch_start_frame": 2 * SAMPLE_RATE,
                        "patch_end_frame": 4 * SAMPLE_RATE,
                        "failed_edges": [],
                    },
                },
            }
        ],
    }
    return {
        "plan_snapshot": {"path": plan_path, "sha256": _sha256(plan_path)},
        "plan": plan,
        "inputs": {
            "execution_snapshot": {
                "path": control_execution_path,
                "sha256": _sha256(control_execution_path),
            },
            "candidate_snapshot": {
                "path": control_candidate_path,
                "sha256": _sha256(control_candidate_path),
            },
            "v2_snapshot": {"path": v2_path, "sha256": _sha256(v2_path)},
        },
        "execution_snapshot": {
            "path": execution_path,
            "sha256": _sha256(execution_path),
        },
        "execution": {"document_sha256": "b" * 64},
        "candidates_snapshot": {
            "path": candidates_path,
            "sha256": _sha256(candidates_path),
        },
        "candidates": {"document_sha256": "c" * 64},
        "base_root": base_root,
        "v2_root": v2_root,
        "variant_root": variant_root,
        "base_paths": base_paths,
        "variant_paths": variant_paths,
    }


def _stereo(values: np.ndarray) -> np.ndarray:
    return np.column_stack((values, values))


def _private_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def _write_audio(path: Path, values: np.ndarray) -> Path:
    soundfile.write(path, values, SAMPLE_RATE, subtype="PCM_24")
    path.chmod(0o600)
    return path
