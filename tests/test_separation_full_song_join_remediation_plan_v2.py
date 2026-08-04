from __future__ import annotations

import json
from pathlib import Path
import shutil
import stat

import numpy as np
import pytest
import soundfile

import sunofriend._separation_full_song_join_remediation_plan_v2 as plan_v2

from sunofriend._separation_authorised_excerpt import _document_sha256, _sha256
from sunofriend._separation_full_song_join_remediation_executor import (
    CANDIDATE_REPORT_NAME,
    REPORT_NAME as EXECUTION_REPORT_NAME,
    SCHEMA as EXECUTION_SCHEMA,
    STATUS_COMPLETE as EXECUTION_STATUS,
    _FALSE_PERMISSIONS,
    _state_sha256,
)
from sunofriend._separation_full_song_join_remediation_plan import (
    POLICY_ID as V1_POLICY_ID,
    _plan_private_separation_full_song_join_remediation,
)
from sunofriend._separation_full_song_join_remediation_plan_v2 import (
    PATCH_DURATION_FRAMES,
    PATCH_HALF_FRAMES,
    POLICY_ID,
    REPORT_NAME,
    SCHEMA,
    _plan_private_separation_full_song_join_remediation_v2,
)
from sunofriend._separation_full_song_join_remediation_review import (
    POLICY_ID as REVIEW_POLICY_ID,
)
from sunofriend._separation_full_song_join_remediation_review_result import (
    RESULT_SCHEMA,
    RESULT_STATUS,
)
from sunofriend._separation_full_song_executor import _verify_attempt
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)
from sunofriend._separation_publication_readiness import (
    SCHEMA as READINESS_SCHEMA,
    _assess_join_remediation_review,
)
from tests.test_separation_full_song_join_remediation_plan import (
    _evidence as _v1_evidence,
)
from tests.test_separation_full_song_join_remediation_executor import _fake_runner
from tests.test_separation_publication_readiness import (
    _join_remediation_review_result,
)


SAMPLE_RATE = 44_100


def test_v2_plan_derives_equivalent_pairs_and_reuses_sealed_workers(
    tmp_path: Path,
) -> None:
    evidence = _evidence(tmp_path)
    output_root = tmp_path / "v2-plan"
    output_root.mkdir(mode=0o700)
    output = output_root / REPORT_NAME

    result = _run_plan(evidence, output)

    assert result["schema"] == SCHEMA
    assert result["policy_id"] == POLICY_ID
    assert result["summary"]["human_equivalent_boundary_role_pair_count"] == 3
    assert result["summary"]["planned_model_call_count"] == 0
    assert result["summary"]["sealed_v1_worker_output_count"] == 3
    assert result["protocol"]["patch_half_frames"] == PATCH_HALF_FRAMES
    assert result["protocol"]["patch_duration_frames"] == PATCH_DURATION_FRAMES
    assert result["protocol"]["edge_blend_frames"] == 4_410
    assert result["protocol"]["edge_blend_shape"].startswith("equal_power")
    assert result["protocol"]["model_invocation"] == (
        "none_reuse_verified_v1_worker_output"
    )
    assert result["protocol_delta_from_v1"]["candidate_base"] == (
        "verified_v1_candidate"
    )
    assert result["protocol_delta_from_v1"]["new_model_calls"] == 0
    assert all(
        item["worker_local_patch_end_frame"] - item["worker_local_patch_start_frame"]
        == PATCH_DURATION_FRAMES
        for item in result["windows"]
    )
    assert {
        (item["boundary_index"], item["patch_target_role"])
        for item in result["windows"]
    } == {(1, "instrumental"), (1, "vocals"), (2, "vocals")}
    assert all(value is False for value in result["permissions"].values())
    assert all(value is False for value in result["effects"].values())
    persisted = output.read_text(encoding="utf-8")
    assert "Private remediation note" not in persisted
    assert str(tmp_path) not in persisted
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    document = json.loads(persisted)
    assert document["document_sha256"] == _document_sha256(document)
    assert "report" not in document


@pytest.mark.parametrize(
    ("target", "message"),
    (
        ("worker_audio", "output binding differs"),
        ("readiness_assessment", "publication-readiness ledger differs"),
        ("candidate_patch", "candidate patch inventory differs"),
        ("resolved_binding", "review input binding differs"),
        ("v1_plan_geometry", "v1 join-remediation plan differs"),
        ("v1_model_invocation", "v1 join-remediation plan differs"),
        ("authorisation_policy", "authorisation differs"),
    ),
)
def test_v2_plan_rejects_tampered_bound_evidence(
    tmp_path: Path,
    target: str,
    message: str,
) -> None:
    evidence = _evidence(tmp_path)
    if target == "worker_audio":
        worker = next(
            evidence.execution_dir.glob("ATTEMPTS/*/staging/*/STEMS/vocals.wav")
        )
        worker.write_bytes(worker.read_bytes() + b"changed")
    elif target == "readiness_assessment":
        document = _read(evidence.readiness)
        document["full_song_join_remediation_assessment"][
            "equivalent_boundary_role_count"
        ] += 1
        _rewrite_hashed(evidence.readiness, document)
    elif target == "candidate_patch":
        document = _read(evidence.candidate)
        document["patches"][0]["worker_output_sha256"] = "f" * 64
        _rewrite_hashed(evidence.candidate, document)
        execution = _read(evidence.execution)
        execution["candidate_report"] = _file_claim(evidence.candidate)
        execution["state_sha256"] = _state_sha256(execution)
        _write_private_json(evidence.execution, execution)
        resolved = _read(evidence.resolved_review)
        resolved["bindings"].update(
            {
                "candidate_report_sha256": _sha256(evidence.candidate),
                "candidate_document_sha256": document["document_sha256"],
                "execution_report_sha256": _sha256(evidence.execution),
                "execution_state_sha256": execution["state_sha256"],
            }
        )
        _rewrite_hashed(evidence.resolved_review, resolved)
        readiness = _read(evidence.readiness)
        readiness["inputs"].update(
            {
                "full_song_join_remediation_review_result_sha256": _sha256(
                    evidence.resolved_review
                ),
                "full_song_join_remediation_review_result_document_sha256": resolved[
                    "document_sha256"
                ],
            }
        )
        _rewrite_hashed(evidence.readiness, readiness)
    elif target == "resolved_binding":
        document = _read(evidence.resolved_review)
        document["bindings"]["candidate_report_sha256"] = "f" * 64
        _rewrite_hashed(evidence.resolved_review, document)
    elif target == "v1_plan_geometry":
        document = _read(evidence.v1_plan)
        document["protocol"]["edge_blend_frames"] += 1
        _rewrite_hashed(evidence.v1_plan, document)
    elif target == "v1_model_invocation":
        document = _read(evidence.v1_plan)
        document["protocol"]["model_invocation"] = "none"
        _rewrite_hashed(evidence.v1_plan, document)
    elif target == "authorisation_policy":
        execution = _read(evidence.execution)
        claim = execution["windows"][0]["authorisation_report"]
        report = evidence.execution_dir / claim["path"]
        document = _read(report)
        document["excerpt"]["selection_policy"] = "changed-policy"
        _rewrite_hashed(report, document)
        claim.update(
            {
                "sha256": _sha256(report),
                "document_sha256": document["document_sha256"],
                "bytes": report.stat().st_size,
            }
        )
        execution["state_sha256"] = _state_sha256(execution)
        _write_private_json(evidence.execution, execution)
    else:  # pragma: no cover
        raise AssertionError(target)

    output_root = tmp_path / "v2-plan"
    output_root.mkdir(mode=0o700)
    with pytest.raises(ValueError, match=message):
        _run_plan(evidence, output_root / REPORT_NAME)


def test_v2_plan_rejects_readiness_gate_closed(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    document = _read(evidence.readiness)
    next(
        gate
        for gate in document["gates"]
        if gate["gate_id"] == "full_song_duration_and_alignment"
    )["status"] = "passed"
    _rewrite_hashed(evidence.readiness, document)

    output_root = tmp_path / "v2-plan"
    output_root.mkdir(mode=0o700)
    with pytest.raises(ValueError, match="publication-readiness ledger differs"):
        _run_plan(evidence, output_root / REPORT_NAME)


def test_v2_plan_rejects_non_private_input(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    evidence.resolved_review.chmod(0o644)
    output_root = tmp_path / "v2-plan"
    output_root.mkdir(mode=0o700)

    with pytest.raises(ValueError, match="must not be readable"):
        _run_plan(evidence, output_root / REPORT_NAME)


def test_v2_plan_never_overwrites_existing_output(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    output_root = tmp_path / "v2-plan"
    output_root.mkdir(mode=0o700)
    output = output_root / REPORT_NAME
    output.write_text("keep\n", encoding="utf-8")
    output.chmod(0o600)

    with pytest.raises(FileExistsError, match="plan exists"):
        _run_plan(evidence, output)
    assert output.read_text(encoding="utf-8") == "keep\n"


def test_v2_plan_rechecks_worker_audio_immediately_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = _evidence(tmp_path)
    worker = next(evidence.execution_dir.glob("ATTEMPTS/*/staging/*/STEMS/vocals.wav"))
    original = plan_v2._require_snapshot_unchanged

    def mutate_after_last_json(snapshot: object, label: str) -> None:
        original(snapshot, label)  # type: ignore[arg-type]
        if label == "private publication-readiness ledger":
            worker.write_bytes(worker.read_bytes() + b"changed-after-first-pass")

    monkeypatch.setattr(plan_v2, "_require_snapshot_unchanged", mutate_after_last_json)
    output_root = tmp_path / "v2-plan"
    output_root.mkdir(mode=0o700)

    with pytest.raises(ValueError, match="output binding differs"):
        _run_plan(evidence, output_root / REPORT_NAME)


class _Evidence:
    def __init__(
        self,
        *,
        package: Path,
        review: Path,
        v1_plan: Path,
        execution_dir: Path,
        execution: Path,
        candidate: Path,
        resolved_review: Path,
        readiness: Path,
    ) -> None:
        self.package = package
        self.review = review
        self.v1_plan = v1_plan
        self.execution_dir = execution_dir
        self.execution = execution
        self.candidate = candidate
        self.resolved_review = resolved_review
        self.readiness = readiness


def _evidence(tmp_path: Path) -> _Evidence:
    tmp_path.chmod(0o700)
    package, review_path, alignment_path = _v1_evidence(tmp_path)
    review = _read(review_path)
    review["bindings"]["review_export_sha256"] = "9" * 64
    review["full_song"] = {
        "heard_all": True,
        "ratings": {
            "vocals": "useful",
            "instrumental": "useful",
            "reconstruction": "useful",
        },
        "notes": "private full-song note",
    }
    review["readiness"] = {
        "worker_runs_complete": True,
        "stitched_outputs_complete": True,
        "exact_duration_and_frame_count_verified": True,
        "full_song_and_boundary_listening_complete": True,
        "full_song_quality_accepted": False,
        "publication_ready": False,
    }
    review["interpretation"] = {
        "ratings_are_human_listening_evidence": True,
        "clean_boundary_is_separator_accuracy": False,
        "review_completion_is_quality_acceptance": False,
        "automatic_winner_selected": False,
        "separator_accepted": False,
    }
    review["effects"] = {
        "product_contract_mutated": False,
        "publication_state_mutated": False,
        "separator_accepted": False,
        "separator_selected": False,
        "source_audio_mutated": False,
        "source_graph_mutated": False,
        "stitched_audio_mutated": False,
    }
    _rewrite_hashed(review_path, review)

    v1_plan_root = tmp_path / "v1-plan"
    v1_plan_root.mkdir(mode=0o700)
    v1_plan = v1_plan_root / "private-separation-full-song-join-remediation-plan.json"
    _plan_private_separation_full_song_join_remediation(
        package,
        review_path,
        alignment_path,
        out=v1_plan,
    )
    plan = _read(v1_plan)

    execution_dir = tmp_path / "v1-execution"
    execution_dir.mkdir(mode=0o700)
    stitch = _read(package / "private-separation-full-song-stitch.json")
    windows = []
    for planned in plan["windows"]:
        window_index = planned["window_index"]
        attempt_relative = f"ATTEMPTS/window-{window_index:04d}-attempt-001"
        attempt = execution_dir / attempt_relative
        frames = planned["source_end_frame"] - planned["source_start_frame"]
        window_root = execution_dir / f"WINDOWS/window-{window_index:04d}"
        source_audio = window_root / "LOCAL-MODEL-INPUT/source-44100.wav"
        source_audio.parent.mkdir(parents=True, mode=0o700)
        source = np.zeros((frames, 2), dtype=np.float32)
        soundfile.write(source_audio, source, SAMPLE_RATE, subtype="PCM_24")
        source_audio.chmod(0o600)
        authorisation = {
            "schema": "sunofriend.private-authorised-separation-excerpt.v1",
            "status": "complete_review_required",
            "evidence_scope": "private_development_only",
            "excerpt": {
                "start_seconds": planned["source_start_frame"] / SAMPLE_RATE,
                "end_seconds": planned["source_end_frame"] / SAMPLE_RATE,
                "selection_policy": V1_POLICY_ID,
                "join_remediation_window_index": window_index,
                "boundary_index": planned["boundary_index"],
                "canonical_start_frame": planned["source_start_frame"],
                "canonical_end_frame": planned["source_end_frame"],
            },
            "original": {
                "local_model_input": {
                    "artifact": {
                        "path": "LOCAL-MODEL-INPUT/source-44100.wav",
                        "sha256": _sha256(source_audio),
                        "bytes": source_audio.stat().st_size,
                    },
                    "geometry": {
                        "sample_rate": SAMPLE_RATE,
                        "channels": 2,
                        "frames": frames,
                        "duration_seconds": frames / SAMPLE_RATE,
                    },
                }
            },
            "permissions": dict(_FALSE_PERMISSIONS),
            "effects": {
                "local_excerpt_created": True,
                "model_run": False,
                "source_audio_mutated": False,
                "source_graph_mutated": False,
            },
        }
        authorisation["document_sha256"] = _document_sha256(authorisation)
        authorisation_path = window_root / "authorised-separation-excerpt.json"
        _write_private_json(authorisation_path, authorisation)
        attempt.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        _fake_runner([])(
            run_nonce=f"window-{window_index}",
            authorisation_report_path=authorisation_path,
            authorisation_report_sha256=_sha256(authorisation_path),
            attempt_directory=attempt,
        )
        verified = _verify_attempt(
            attempt,
            expected_frames=frames,
            expected_authorisation_sha256=_sha256(authorisation_path),
        )
        windows.append(
            {
                "window_index": window_index,
                "boundary_index": planned["boundary_index"],
                "source_start_frame": planned["source_start_frame"],
                "source_end_frame": planned["source_end_frame"],
                "patch_start_frame": planned["patch_start_frame"],
                "patch_end_frame": planned["patch_end_frame"],
                "patch_target_roles": planned["patch_target_roles"],
                "authorisation_report": {
                    "path": authorisation_path.relative_to(execution_dir).as_posix(),
                    "sha256": _sha256(authorisation_path),
                    "document_sha256": authorisation["document_sha256"],
                    "bytes": authorisation_path.stat().st_size,
                    "audio": {
                        "path": source_audio.relative_to(execution_dir).as_posix(),
                        "sha256": _sha256(source_audio),
                        "bytes": source_audio.stat().st_size,
                        "frames": frames,
                    },
                },
                "status": "verified_complete",
                "selected_attempt": 1,
                "attempts": [
                    {
                        "attempt": 1,
                        "path": attempt_relative,
                        "status": "verified_complete",
                        **verified,
                    }
                ],
            }
        )

    candidate_root = execution_dir / "CANDIDATES"
    candidate_root.mkdir(mode=0o700)
    artifacts = {}
    for role in ("vocals", "instrumental", "reconstruction"):
        source_path = package / stitch["artifacts"][role]["path"]
        target = candidate_root / f"{role}.wav"
        shutil.copyfile(source_path, target)
        target.chmod(0o600)
        artifacts[role] = {
            "path": target.relative_to(execution_dir).as_posix(),
            "sha256": _sha256(target),
            "bytes": target.stat().st_size,
            "geometry": {
                "sample_rate": SAMPLE_RATE,
                "channels": 2,
                "sample_width_bytes": 3,
                "frames": stitch["clock"]["frames"],
            },
        }
        if role == "reconstruction":
            artifacts[role].update({"pre_gain_peak": 0.1, "global_gain": 1.0})
        else:
            artifacts[role].update(
                {
                    "outside_patch_pcm24_samples_exact": True,
                    "patch_count": sum(
                        role in window["patch_target_roles"] for window in windows
                    ),
                    "peak_before_write": 0.1,
                }
            )
    patches = []
    for role in ("vocals", "instrumental"):
        for planned, window in zip(plan["windows"], windows):
            if role not in planned["patch_target_roles"]:
                continue
            patches.append(
                {
                    "window_index": planned["window_index"],
                    "boundary_index": planned["boundary_index"],
                    "role": role,
                    "start_frame": planned["patch_start_frame"],
                    "end_frame": planned["patch_end_frame"],
                    "edge_blend_frames": plan["protocol"]["edge_blend_frames"],
                    "worker_output_sha256": window["attempts"][0]["outputs"][role][
                        "sha256"
                    ],
                    "changed_sample_values_before_pcm24_rounding": 1,
                }
            )
    candidate = {
        "schema": "sunofriend.private-separation-full-song-join-remediation-candidates.v1",
        "status": "candidate_audio_complete_review_required",
        "evidence_scope": "private_development_only",
        "policy_id": V1_POLICY_ID,
        "bindings": {
            "execution_state_sha256_before_candidate_report": "a" * 64,
            "remediation_plan_document_sha256": plan["document_sha256"],
            "stitch_document_sha256": stitch["document_sha256"],
            "source_audio_sha256": stitch["artifacts"]["source"]["sha256"],
            "raw_vocals_audio_sha256": stitch["artifacts"]["vocals"]["sha256"],
            "raw_instrumental_audio_sha256": stitch["artifacts"]["instrumental"][
                "sha256"
            ],
            "raw_reconstruction_audio_sha256": stitch["artifacts"]["reconstruction"][
                "sha256"
            ],
        },
        "clock": plan["clock"],
        "patches": patches,
        "artifacts": artifacts,
        "summary": {
            "verified_worker_window_count": len(windows),
            "patched_boundary_role_pair_count": len(patches),
            "candidate_role_count": 3,
            "raw_control_count": 1,
            "raw_stitch_hashes_unchanged": True,
            "blind_boundary_review_required": True,
            "patch_edge_review_required": True,
            "complete_song_review_required": True,
        },
        "readiness": {
            "worker_runs_complete": True,
            "candidate_audio_complete": True,
            "candidate_integrity_verified": True,
            "candidate_review_complete": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": {
            "candidate_audio_created": True,
            "model_run": True,
            "raw_stitch_mutated": False,
            "review_evidence_mutated": False,
            "separator_accepted": False,
            "separator_selected": False,
            "source_graph_mutated": False,
        },
        "limitations": [],
    }
    candidate["document_sha256"] = _document_sha256(candidate)
    candidate_path = execution_dir / CANDIDATE_REPORT_NAME
    _write_private_json(candidate_path, candidate)

    execution = {
        "schema": EXECUTION_SCHEMA,
        "status": EXECUTION_STATUS,
        "evidence_scope": "private_development_only",
        "execution_nonce": "b" * 64,
        "bindings": {
            "remediation_plan_sha256": _sha256(v1_plan),
            "remediation_plan_document_sha256": plan["document_sha256"],
            "stitch_report_sha256": _sha256(
                package / "private-separation-full-song-stitch.json"
            ),
            "stitch_document_sha256": stitch["document_sha256"],
            "source_plan_sha256": "c" * 64,
            "source_plan_document_sha256": stitch["bindings"]["plan_document_sha256"],
            "checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
            "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
        },
        "clock": plan["clock"],
        "protocol": plan["protocol"],
        "windows": windows,
        "candidate_report": _file_claim(candidate_path),
        "summary": {
            "total_windows": len(windows),
            "verified_windows": len(windows),
            "remaining_windows": 0,
            "all_worker_runs_complete": True,
            "candidate_audio_complete": True,
            "human_candidate_review_complete": False,
            "quality_accepted": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": {
            "authorisation_windows_created": True,
            "candidate_audio_created": True,
            "model_run": True,
            "raw_stitch_mutated": False,
            "review_evidence_mutated": False,
            "separator_accepted": False,
            "separator_selected": False,
            "source_graph_mutated": False,
        },
        "limitations": [],
    }
    execution["state_sha256"] = _state_sha256(execution)
    execution_path = execution_dir / EXECUTION_REPORT_NAME
    _write_private_json(execution_path, execution)

    resolved_path = _join_remediation_review_result(tmp_path, review_path)
    resolved = _read(resolved_path)
    resolved["bindings"].update(
        {
            "candidate_document_sha256": candidate["document_sha256"],
            "candidate_report_sha256": _sha256(candidate_path),
            "execution_report_sha256": _sha256(execution_path),
            "execution_state_sha256": execution["state_sha256"],
            "stitch_document_sha256": stitch["document_sha256"],
            "stitch_report_sha256": _sha256(
                package / "private-separation-full-song-stitch.json"
            ),
        }
    )
    resolved["schema"] = RESULT_SCHEMA
    resolved["status"] = RESULT_STATUS
    resolved["policy_id"] = REVIEW_POLICY_ID
    _rewrite_hashed(resolved_path, resolved)

    readiness = {
        "schema": READINESS_SCHEMA,
        "status": "blocked_private_bounded_vocal_midi_evidence_only",
        "evidence_scope": "private_development_only",
        "inputs": {
            "full_song_review_result_sha256": _sha256(review_path),
            "full_song_review_result_document_sha256": review["document_sha256"],
            "full_song_join_remediation_review_result_sha256": _sha256(resolved_path),
            "full_song_join_remediation_review_result_document_sha256": resolved[
                "document_sha256"
            ],
            "full_song_alignment_result_sha256": plan["bindings"][
                "alignment_result_sha256"
            ],
            "full_song_alignment_result_document_sha256": plan["bindings"][
                "alignment_document_sha256"
            ],
        },
        "full_song_join_remediation_assessment": (
            _assess_join_remediation_review(resolved)
        ),
        "full_song_duration_alignment_assessment": {
            "audible_join_boundaries_by_role": review["boundary_summary"][
                "audible_join_boundaries_by_role"
            ],
            "gate_passed": False,
            "acceptance_gate_closed": False,
            "all_role_boundaries_clean": False,
        },
        "readiness": {
            "experimental_studio_route_ready": False,
            "one_action_simple_route_ready": False,
            "open_gate_count": 8,
            "passed_gate_count": 3,
            "publication_ready": False,
            "required_gate_count": 11,
            "stage": "private_bounded_vocal_research",
        },
        "policy": {"join_remediation_review_can_close_duration_alignment_gate": False},
        "gates": [
            {
                "gate_id": "full_song_duration_and_alignment",
                "status": "open",
                "finding": "Original absolute clean-boundary minimum remains unmet.",
            }
        ],
        "permissions": {
            "accepted": False,
            "automatic_promotion": False,
            "automatic_selection": False,
            "production_eligible": False,
            "public_result": False,
            "simple_mode_available": False,
            "source_graph_activation": False,
            "studio_import_available": False,
        },
        "effects": {
            "audio_created_or_mutated": False,
            "candidate_activated": False,
            "default_changed": False,
            "midi_created_or_mutated": False,
            "product_contract_mutated": False,
            "source_graph_mutated": False,
        },
    }
    readiness_path = tmp_path / "private-separation-publication-readiness.json"
    _write_hashed(readiness_path, readiness)

    for path in execution_dir.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)
    execution_dir.chmod(0o700)

    return _Evidence(
        package=package,
        review=review_path,
        v1_plan=v1_plan,
        execution_dir=execution_dir,
        execution=execution_path,
        candidate=candidate_path,
        resolved_review=resolved_path,
        readiness=readiness_path,
    )


def _run_plan(evidence: _Evidence, output: Path) -> dict[str, object]:
    return _plan_private_separation_full_song_join_remediation_v2(
        evidence.package,
        full_song_review_result_path=evidence.review,
        v1_plan_path=evidence.v1_plan,
        v1_execution_report_path=evidence.execution,
        v1_candidate_report_path=evidence.candidate,
        resolved_join_review_result_path=evidence.resolved_review,
        publication_readiness_path=evidence.readiness,
        out=output,
    )


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _rewrite_hashed(path: Path, document: dict[str, object]) -> None:
    document["document_sha256"] = _document_sha256(document)
    _write_private_json(path, document)


def _write_hashed(path: Path, document: dict[str, object]) -> Path:
    _rewrite_hashed(path, document)
    return path


def _write_private_json(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    path.chmod(0o600)


def _file_claim(path: Path) -> dict[str, object]:
    document = _read(path)
    return {
        "path": path.name,
        "sha256": _sha256(path),
        "document_sha256": document["document_sha256"],
        "bytes": path.stat().st_size,
    }
