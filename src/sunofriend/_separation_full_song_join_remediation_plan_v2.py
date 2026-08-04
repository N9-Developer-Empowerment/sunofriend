"""Plan a second, model-free pass over equivalent reviewed join candidates.

This private-development contract is deliberately narrower than the frozen v1
join-remediation plan.  It derives its targets from the resolved blind review,
reuses only the already sealed v1 worker outputs, and changes only the patch
context from one second to two seconds on each side of the join.  It creates no
audio, runs no model, and cannot close a readiness gate.
"""

from __future__ import annotations

from copy import deepcopy
import math
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_full_song_executor import (
    _require_private_directory,
    _require_private_regular,
    _verify_attempt,
)
from ._separation_full_song_join_remediation_executor import (
    CANDIDATE_REPORT_NAME,
    REPORT_NAME as V1_EXECUTION_REPORT_NAME,
    SCHEMA as V1_EXECUTION_SCHEMA,
    STATUS_COMPLETE as V1_EXECUTION_STATUS,
    _FALSE_PERMISSIONS,
    _state_sha256,
)
from ._separation_full_song_join_remediation_plan import (
    EDGE_BLEND_FRAMES,
    PATCH_HALF_FRAMES as V1_PATCH_HALF_FRAMES,
    POLICY_ID as V1_PLAN_POLICY_ID,
    REPORT_NAME as V1_PLAN_REPORT_NAME,
    SCHEMA as V1_PLAN_SCHEMA,
    STATUS as V1_PLAN_STATUS,
    TARGET_SAMPLE_RATE,
    _target_roles_by_boundary,
    _verify_review_result,
    _window_plan as _v1_window_plan,
)
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
    _write_json_exclusive,
)
from ._separation_full_song_review import (
    _load_stitch_report,
    _verify_stitch_audio,
)
from ._separation_full_song_stitch import (
    REPORT_NAME as STITCH_REPORT_NAME,
    REVIEW_NAME,
)
from ._separation_melroformer_real_bridge import MAXIMUM_EXCERPT_FRAMES
from ._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)
from ._separation_publication_readiness import (
    SCHEMA as READINESS_SCHEMA,
    _assess_join_remediation_review,
    _load_full_song_join_remediation_review_result,
    _load_full_song_review_result,
    _require_join_remediation_bound_to_full_song_review,
)


SCHEMA = "sunofriend.private-separation-full-song-join-remediation-plan.v2"
STATUS = "planned_equivalent_join_expanded_context_repatch_no_model_run"
POLICY_ID = "human-equivalent-join-expanded-context-repatch-v2"
REPORT_NAME = "private-separation-full-song-join-remediation-plan-v2.json"

PATCH_HALF_FRAMES = 2 * TARGET_SAMPLE_RATE
PATCH_DURATION_FRAMES = 2 * PATCH_HALF_FRAMES
_ROLES = ("vocals", "instrumental")
_FULL_SONG_ROLES = (*_ROLES, "reconstruction")
_OUTCOMES = (
    "candidate_preferred",
    "raw_preferred",
    "equivalent",
    "neither",
    "cannot_tell",
)
_PLAN_KEYS = {
    "schema",
    "status",
    "evidence_scope",
    "policy_id",
    "bindings",
    "clock",
    "protocol",
    "protocol_delta_from_v1",
    "windows",
    "summary",
    "required_future_review",
    "readiness",
    "interpretation",
    "permissions",
    "effects",
    "limitations",
    "document_sha256",
}
_FALSE_EFFECTS = {
    "audio_created_or_mutated": False,
    "candidate_audio_created": False,
    "model_run": False,
    "publication_state_mutated": False,
    "raw_stitch_mutated": False,
    "review_evidence_mutated": False,
    "separator_accepted": False,
    "separator_selected": False,
    "source_graph_mutated": False,
    "v1_worker_output_mutated": False,
}
_READINESS_PERMISSIONS = {
    "accepted": False,
    "automatic_promotion": False,
    "automatic_selection": False,
    "production_eligible": False,
    "public_result": False,
    "simple_mode_available": False,
    "source_graph_activation": False,
    "studio_import_available": False,
}
_READINESS_EFFECTS = {
    "audio_created_or_mutated": False,
    "candidate_activated": False,
    "default_changed": False,
    "midi_created_or_mutated": False,
    "product_contract_mutated": False,
    "source_graph_mutated": False,
}
_V1_CANDIDATE_SCHEMA = (
    "sunofriend.private-separation-full-song-join-remediation-candidates.v1"
)
_V1_CANDIDATE_STATUS = "candidate_audio_complete_review_required"


def _plan_private_separation_full_song_join_remediation_v2(
    package_dir: str | Path,
    *,
    full_song_review_result_path: str | Path,
    v1_plan_path: str | Path,
    v1_execution_report_path: str | Path,
    v1_candidate_report_path: str | Path,
    resolved_join_review_result_path: str | Path,
    publication_readiness_path: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Write a fresh path-free plan for equivalent v1 boundary-role results."""

    package = Path(package_dir).expanduser().absolute()
    _require_private_directory(package, "private stitch package")
    stitch_path = package / STITCH_REPORT_NAME
    stitch_snapshot = _load_private_json_snapshot(
        stitch_path, "private full-song stitch report"
    )
    stitch = _load_stitch_report(stitch_path)
    if stitch != stitch_snapshot["document"]:
        raise ValueError("private full-song stitch report changed")
    _verify_stitch_audio(package, stitch)

    review_snapshot = _load_private_json_snapshot(
        full_song_review_result_path, "private full-song review result"
    )
    review_loaded = _load_full_song_review_result(full_song_review_result_path)
    review = review_loaded.document
    if (
        review_loaded.file_sha256 != review_snapshot["sha256"]
        or review != review_snapshot["document"]
    ):
        raise ValueError("private full-song review result changed")
    review_seed_path = package / "BOUNDARY-REVIEW" / REVIEW_NAME
    review_seed_snapshot = _load_private_json_snapshot(
        review_seed_path, "private full-song review seed"
    )
    _verify_review_result(
        review,
        review_path=review_snapshot["path"],
        review_seed=review_seed_snapshot["document"],
        review_seed_path=review_seed_snapshot["path"],
        stitch=stitch,
        stitch_path=stitch_path,
    )

    v1_plan_snapshot = _load_private_json_snapshot(
        v1_plan_path, "private v1 join-remediation plan"
    )
    v1_plan = v1_plan_snapshot["document"]
    _verify_v1_plan(
        v1_plan,
        file_sha256=v1_plan_snapshot["sha256"],
        path=v1_plan_snapshot["path"],
        stitch=stitch,
        stitch_sha256=stitch_snapshot["sha256"],
        review=review,
        review_sha256=review_snapshot["sha256"],
        review_seed_sha256=review_seed_snapshot["sha256"],
    )

    execution_snapshot = _load_private_json_snapshot(
        v1_execution_report_path, "private v1 join-remediation execution"
    )
    execution = execution_snapshot["document"]
    execution_root = execution_snapshot["path"].parent
    _require_private_directory(execution_root, "private v1 remediation execution root")
    _verify_v1_execution(
        execution,
        execution_root=execution_root,
        file_sha256=execution_snapshot["sha256"],
        path=execution_snapshot["path"],
        v1_plan=v1_plan,
        v1_plan_sha256=v1_plan_snapshot["sha256"],
        stitch=stitch,
        stitch_sha256=stitch_snapshot["sha256"],
    )

    candidate_snapshot = _load_private_json_snapshot(
        v1_candidate_report_path, "private v1 join-remediation candidate report"
    )
    candidate = candidate_snapshot["document"]
    _verify_v1_candidate(
        candidate,
        path=candidate_snapshot["path"],
        file_sha256=candidate_snapshot["sha256"],
        execution=execution,
        execution_root=execution_root,
        v1_plan=v1_plan,
        stitch=stitch,
    )

    remediation_snapshot = _load_private_json_snapshot(
        resolved_join_review_result_path,
        "private resolved join-remediation review result",
    )
    remediation_loaded = _load_full_song_join_remediation_review_result(
        resolved_join_review_result_path
    )
    remediation = remediation_loaded.document
    if (
        remediation_loaded.file_sha256 != remediation_snapshot["sha256"]
        or remediation != remediation_snapshot["document"]
    ):
        raise ValueError("private resolved join-remediation review result changed")
    _require_join_remediation_bound_to_full_song_review(
        remediation_loaded, review_loaded
    )
    _verify_resolved_review_bindings(
        remediation,
        stitch=stitch,
        stitch_sha256=stitch_snapshot["sha256"],
        execution=execution,
        execution_sha256=execution_snapshot["sha256"],
        candidate=candidate,
        candidate_sha256=candidate_snapshot["sha256"],
    )

    readiness_snapshot = _load_private_json_snapshot(
        publication_readiness_path, "private publication-readiness ledger"
    )
    readiness = readiness_snapshot["document"]
    _verify_readiness_ledger(
        readiness,
        full_song_review=review,
        full_song_review_sha256=review_snapshot["sha256"],
        remediation=remediation,
        remediation_sha256=remediation_snapshot["sha256"],
        v1_plan=v1_plan,
    )

    unresolved_pairs = _equivalent_boundary_role_pairs(remediation)
    if not unresolved_pairs:
        raise ValueError("resolved join-remediation review has no equivalent join pair")
    v1_patches = _verified_v1_patch_inventory(
        candidate,
        execution=execution,
        execution_root=execution_root,
    )
    windows = _expanded_windows(
        unresolved_pairs,
        review=review,
        v1_plan=v1_plan,
        execution=execution,
        v1_patches=v1_patches,
        total_frames=int(stitch["clock"]["frames"]),
    )
    _require_disjoint_patch_regions(windows)

    protocol = deepcopy(v1_plan["protocol"])
    protocol.update(
        {
            "patch_half_frames": PATCH_HALF_FRAMES,
            "patch_duration_frames": PATCH_DURATION_FRAMES,
            "patch_duration_seconds": PATCH_DURATION_FRAMES / TARGET_SAMPLE_RATE,
            "model_invocation": "none_reuse_verified_v1_worker_output",
            "candidate_policy": (
                "start from the verified v1 candidate; repatch only the named "
                "equivalent role from its matching sealed v1 worker output, "
                "preserve untargeted v1 candidate samples, and recompute a "
                "separate diagnostic reconstruction"
            ),
        }
    )
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "stitch_report_sha256": stitch_snapshot["sha256"],
            "stitch_document_sha256": stitch["document_sha256"],
            "full_song_review_result_sha256": review_snapshot["sha256"],
            "full_song_review_document_sha256": review["document_sha256"],
            "v1_plan_sha256": v1_plan_snapshot["sha256"],
            "v1_plan_document_sha256": v1_plan["document_sha256"],
            "v1_execution_report_sha256": execution_snapshot["sha256"],
            "v1_execution_state_sha256": execution["state_sha256"],
            "v1_candidate_report_sha256": candidate_snapshot["sha256"],
            "v1_candidate_document_sha256": candidate["document_sha256"],
            "resolved_join_review_result_sha256": remediation_snapshot["sha256"],
            "resolved_join_review_document_sha256": remediation["document_sha256"],
            "publication_readiness_sha256": readiness_snapshot["sha256"],
            "publication_readiness_document_sha256": readiness["document_sha256"],
            "source_audio_sha256": stitch["artifacts"]["source"]["sha256"],
            "raw_vocals_audio_sha256": stitch["artifacts"]["vocals"]["sha256"],
            "raw_instrumental_audio_sha256": stitch["artifacts"]["instrumental"][
                "sha256"
            ],
            "raw_reconstruction_audio_sha256": stitch["artifacts"]["reconstruction"][
                "sha256"
            ],
        },
        "clock": deepcopy(stitch["clock"]),
        "protocol": protocol,
        "protocol_delta_from_v1": {
            "signal_processing_changed_fields": {
                "patch_half_frames": {
                    "v1": V1_PATCH_HALF_FRAMES,
                    "v2": PATCH_HALF_FRAMES,
                },
                "patch_duration_frames": {
                    "v1": 2 * V1_PATCH_HALF_FRAMES,
                    "v2": PATCH_DURATION_FRAMES,
                },
                "patch_duration_seconds": {
                    "v1": 2 * V1_PATCH_HALF_FRAMES / TARGET_SAMPLE_RATE,
                    "v2": PATCH_DURATION_FRAMES / TARGET_SAMPLE_RATE,
                },
            },
            "operational_scope_changes": {
                "model_invocation": {
                    "v1": v1_plan["protocol"]["model_invocation"],
                    "v2": protocol["model_invocation"],
                },
                "candidate_policy": {
                    "v1": v1_plan["protocol"]["candidate_policy"],
                    "v2": protocol["candidate_policy"],
                },
            },
            "edge_blend_frames_unchanged": EDGE_BLEND_FRAMES,
            "edge_blend_shape_unchanged": v1_plan["protocol"]["edge_blend_shape"],
            "source_windows_unchanged": True,
            "sealed_v1_worker_outputs_reused": True,
            "new_model_calls": 0,
            "candidate_base": "verified_v1_candidate",
            "untargeted_v1_patches_preserved": True,
        },
        "windows": windows,
        "summary": {
            "human_equivalent_boundary_role_pair_count": len(unresolved_pairs),
            "unique_boundary_count": len({pair[0] for pair in unresolved_pairs}),
            "planned_model_call_count": 0,
            "sealed_v1_worker_output_count": len(windows),
            "target_roles": [
                role
                for role in _ROLES
                if any(pair[1] == role for pair in unresolved_pairs)
            ],
            "private_listener_notes_copied": False,
            "raw_control_count": 1,
            "v1_candidate_control_count": 1,
            "v2_candidate_count": 0,
            "preserved_v1_patch_boundary_role_pairs": [
                {"boundary_index": boundary_index, "role": role}
                for boundary_index, role in sorted(
                    set(v1_patches) - set(unresolved_pairs)
                )
            ],
        },
        "required_future_review": {
            "blind_v1_candidate_versus_v2_candidate_boundary_role_pairs": len(
                unresolved_pairs
            ),
            "absolute_cleanliness_rating_per_anonymous_boundary_candidate": True,
            "expanded_patch_edge_role_checks": 2 * len(unresolved_pairs),
            "new_candidate_bound_complete_song_roles": list(_FULL_SONG_ROLES),
            "new_candidate_bound_full_song_review_required": True,
            "new_candidate_bound_alignment_required": True,
            "automatic_preference_inference": False,
            "review_result_required_before_readiness_reassessment": True,
        },
        "readiness": {
            "resolved_review_targets_verified": True,
            "readiness_ledger_gate_open_verified": True,
            "sealed_v1_worker_outputs_verified": True,
            "v1_candidate_is_v2_assembly_base": True,
            "untargeted_v1_patches_must_remain_byte_exact": True,
            "targeted_repatch_plan_ready": True,
            "v2_candidate_created": False,
            "v2_candidate_review_complete": False,
            "new_candidate_full_song_review_complete": False,
            "new_candidate_alignment_complete": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "interpretation": {
            "equivalent_preference_is_absolute_cleanliness": False,
            "expanded_context_is_repair_success": False,
            "reused_worker_output_is_new_model_evidence": False,
            "readiness_ledger_is_target_authority": False,
            "readiness_ledger_can_close_a_gate": False,
            "automatic_winner_selected": False,
            "separator_accepted": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_FALSE_EFFECTS),
        "limitations": [
            "This plan creates no audio and runs no model.",
            "Only equivalent boundary-role outcomes from the resolved v1 review are targeted.",
            "The wider patch can introduce different edge or continuity artefacts and must be reviewed.",
            "Comparative review cannot replace a fresh candidate-bound full-song review and alignment result.",
            "The plan does not close or alter any publication-readiness gate.",
            "The readiness ledger is contextual cross-check evidence, not target authority.",
            "Worker, authorisation and candidate WAVs are reverified immediately before publication, but their descriptors are not held for the whole operation; the private v1 tree must remain quiescent.",
        ],
    }
    if set(document) != _PLAN_KEYS - {"document_sha256"}:
        raise AssertionError("private v2 plan construction differs")
    document["document_sha256"] = _document_sha256(document)

    snapshots = (
        (stitch_snapshot, "private full-song stitch report"),
        (review_snapshot, "private full-song review result"),
        (review_seed_snapshot, "private full-song review seed"),
        (v1_plan_snapshot, "private v1 join-remediation plan"),
        (execution_snapshot, "private v1 join-remediation execution"),
        (candidate_snapshot, "private v1 join-remediation candidate report"),
        (remediation_snapshot, "private resolved join-remediation review result"),
        (readiness_snapshot, "private publication-readiness ledger"),
    )
    for snapshot, label in snapshots:
        _require_snapshot_unchanged(snapshot, label)
    _verify_stitch_audio(package, stitch)
    _verify_v1_execution(
        execution,
        execution_root=execution_root,
        file_sha256=execution_snapshot["sha256"],
        path=execution_snapshot["path"],
        v1_plan=v1_plan,
        v1_plan_sha256=v1_plan_snapshot["sha256"],
        stitch=stitch,
        stitch_sha256=stitch_snapshot["sha256"],
    )
    _verify_v1_candidate(
        candidate,
        path=candidate_snapshot["path"],
        file_sha256=candidate_snapshot["sha256"],
        execution=execution,
        execution_root=execution_root,
        v1_plan=v1_plan,
        stitch=stitch,
    )
    _verified_v1_patch_inventory(
        candidate,
        execution=execution,
        execution_root=execution_root,
    )

    output = Path(out).expanduser().absolute()
    if output.name != REPORT_NAME:
        raise ValueError(
            f"private v2 join-remediation plan filename must be {REPORT_NAME}"
        )
    if os.path.lexists(output):
        raise FileExistsError(f"private v2 join-remediation plan exists: {output}")
    if not output.parent.exists():
        output.parent.mkdir(parents=True, mode=0o700)
    _require_private_directory(output.parent, "private v2 join-remediation output root")
    _write_json_exclusive(output, document)
    _require_private_regular(output, "private v2 join-remediation plan")
    if stat.S_IMODE(output.stat().st_mode) != 0o600:
        raise ValueError("private v2 join-remediation plan mode differs")
    return {**document, "report": str(output)}


def _verify_v1_plan(
    plan: Mapping[str, Any],
    *,
    file_sha256: str,
    path: Path,
    stitch: Mapping[str, Any],
    stitch_sha256: str,
    review: Mapping[str, Any],
    review_sha256: str,
    review_seed_sha256: str,
) -> None:
    bindings = plan.get("bindings")
    target_roles = _target_roles_by_boundary(review)
    boundary_rows = {int(row["boundary_index"]): row for row in review["boundaries"]}
    expected_windows = [
        _v1_window_plan(
            boundary_rows[index],
            target_roles=roles,
            total_frames=int(stitch["clock"]["frames"]),
            window_index=window_index,
        )
        for window_index, (index, roles) in enumerate(
            sorted(target_roles.items()), start=1
        )
    ]
    expected_protocol = {
        "source_window_frames": MAXIMUM_EXCERPT_FRAMES,
        "source_window_seconds": MAXIMUM_EXCERPT_FRAMES / TARGET_SAMPLE_RATE,
        "patch_half_frames": V1_PATCH_HALF_FRAMES,
        "patch_duration_frames": 2 * V1_PATCH_HALF_FRAMES,
        "patch_duration_seconds": 2 * V1_PATCH_HALF_FRAMES / TARGET_SAMPLE_RATE,
        "edge_blend_frames": EDGE_BLEND_FRAMES,
        "edge_blend_seconds": EDGE_BLEND_FRAMES / TARGET_SAMPLE_RATE,
        "edge_blend_shape": "equal_power_old_to_new_then_new_to_old",
        "model_invocation": (
            "one independent Kim Vocal 2 inference over the exact canonical "
            "source window per unique reviewed boundary"
        ),
        "candidate_policy": (
            "replace only the named role inside the patch, blend only at the "
            "two patch edges, and recompute a separate diagnostic reconstruction"
        ),
        "raw_stitch_is_control": True,
        "source_windows_may_overlap": True,
        "patch_regions_must_not_overlap": True,
    }
    target_pair_count = sum(len(item) for item in target_roles.values())
    if (
        path.name != V1_PLAN_REPORT_NAME
        or plan.get("schema") != V1_PLAN_SCHEMA
        or plan.get("status") != V1_PLAN_STATUS
        or plan.get("evidence_scope") != "private_development_only"
        or plan.get("policy_id") != V1_PLAN_POLICY_ID
        or plan.get("document_sha256") != _document_sha256(plan)
        or not isinstance(bindings, Mapping)
        or bindings.get("stitch_report_sha256") != stitch_sha256
        or bindings.get("stitch_document_sha256") != stitch["document_sha256"]
        or bindings.get("review_result_sha256") != review_sha256
        or bindings.get("review_document_sha256") != review["document_sha256"]
        or bindings.get("review_seed_sha256") != review_seed_sha256
        or bindings.get("source_audio_sha256")
        != stitch["artifacts"]["source"]["sha256"]
        or bindings.get("raw_vocals_audio_sha256")
        != stitch["artifacts"]["vocals"]["sha256"]
        or bindings.get("raw_instrumental_audio_sha256")
        != stitch["artifacts"]["instrumental"]["sha256"]
        or bindings.get("raw_reconstruction_audio_sha256")
        != stitch["artifacts"]["reconstruction"]["sha256"]
        or plan.get("clock") != stitch["clock"]
        or plan.get("protocol") != expected_protocol
        or plan.get("windows") != expected_windows
        or plan.get("summary")
        != {
            "human_rated_audible_role_join_count": target_pair_count,
            "unique_boundary_count": len(expected_windows),
            "planned_model_call_count": len(expected_windows),
            "target_roles": [
                role
                for role in _ROLES
                if any(role in roles for roles in target_roles.values())
            ],
            "private_listener_notes_copied": False,
            "raw_control_count": 1,
            "repaired_candidate_count": 0,
        }
        or plan.get("permissions") != _FALSE_PERMISSIONS
        or not _all_false(plan.get("effects"))
        or not _sha256_hex(file_sha256)
    ):
        raise ValueError("private v1 join-remediation plan differs")


def _verify_v1_execution(
    execution: Mapping[str, Any],
    *,
    execution_root: Path,
    file_sha256: str,
    path: Path,
    v1_plan: Mapping[str, Any],
    v1_plan_sha256: str,
    stitch: Mapping[str, Any],
    stitch_sha256: str,
) -> None:
    bindings = execution.get("bindings")
    windows = execution.get("windows")
    candidate_claim = execution.get("candidate_report")
    if (
        path.name != V1_EXECUTION_REPORT_NAME
        or execution.get("schema") != V1_EXECUTION_SCHEMA
        or execution.get("status") != V1_EXECUTION_STATUS
        or execution.get("evidence_scope") != "private_development_only"
        or execution.get("state_sha256") != _state_sha256(execution)
        or execution.get("clock") != v1_plan["clock"]
        or execution.get("protocol") != v1_plan["protocol"]
        or execution.get("permissions") != _FALSE_PERMISSIONS
        or execution.get("effects")
        != {
            "authorisation_windows_created": True,
            "candidate_audio_created": True,
            "model_run": True,
            "raw_stitch_mutated": False,
            "review_evidence_mutated": False,
            "separator_accepted": False,
            "separator_selected": False,
            "source_graph_mutated": False,
        }
        or not isinstance(bindings, Mapping)
        or bindings.get("remediation_plan_sha256") != v1_plan_sha256
        or bindings.get("remediation_plan_document_sha256")
        != v1_plan["document_sha256"]
        or bindings.get("stitch_report_sha256") != stitch_sha256
        or bindings.get("stitch_document_sha256") != stitch["document_sha256"]
        or bindings.get("source_plan_document_sha256")
        != stitch["bindings"]["plan_document_sha256"]
        or bindings.get("checkpoint_sha256") != CONVERSION_CHECKPOINT_SHA256
        or bindings.get("checkpoint_bytes") != CONVERSION_CHECKPOINT_BYTES
        or not _sha256_hex(bindings.get("source_plan_sha256"))
        or not isinstance(windows, list)
        or len(windows) != len(v1_plan["windows"])
        or not isinstance(candidate_claim, Mapping)
        or candidate_claim.get("path") != CANDIDATE_REPORT_NAME
        or execution.get("summary")
        != {
            "total_windows": len(windows),
            "verified_windows": len(windows),
            "remaining_windows": 0,
            "all_worker_runs_complete": True,
            "candidate_audio_complete": True,
            "human_candidate_review_complete": False,
            "quality_accepted": False,
        }
        or not isinstance(execution.get("execution_nonce"), str)
        or len(execution["execution_nonce"]) != 64
        or not _sha256_hex(execution["execution_nonce"])
        or not _sha256_hex(file_sha256)
    ):
        raise ValueError("private v1 join-remediation execution differs")
    for planned, actual in zip(v1_plan["windows"], windows):
        for field in (
            "window_index",
            "boundary_index",
            "source_start_frame",
            "source_end_frame",
            "patch_start_frame",
            "patch_end_frame",
            "patch_target_roles",
        ):
            if actual.get(field) != planned[field]:
                raise ValueError("private v1 remediation execution window differs")
        selected = _selected_attempt(actual)
        _verify_v1_authorisation(
            execution_root,
            actual.get("authorisation_report"),
            planned=planned,
        )
        relative_attempt = selected.get("path")
        if not isinstance(relative_attempt, str):
            raise ValueError("private v1 selected worker path differs")
        attempt_root = _private_child_directory(
            execution_root,
            relative_attempt,
            "private v1 selected attempt",
        )
        observed = _verify_attempt(
            attempt_root,
            expected_frames=int(planned["source_end_frame"])
            - int(planned["source_start_frame"]),
            expected_authorisation_sha256=actual["authorisation_report"]["sha256"],
        )
        for field in (
            "evidence_sha256",
            "receipt_sha256",
            "timing_sha256",
            "outputs",
        ):
            if selected.get(field) != observed[field]:
                raise ValueError("private v1 selected attempt record differs")


def _verify_v1_candidate(
    candidate: Mapping[str, Any],
    *,
    path: Path,
    file_sha256: str,
    execution: Mapping[str, Any],
    execution_root: Path,
    v1_plan: Mapping[str, Any],
    stitch: Mapping[str, Any],
) -> None:
    claim = execution["candidate_report"]
    expected_path = execution_root / CANDIDATE_REPORT_NAME
    if path != expected_path:
        raise ValueError("private v1 candidate report path differs from execution")
    bindings = candidate.get("bindings")
    if (
        candidate.get("schema") != _V1_CANDIDATE_SCHEMA
        or candidate.get("status") != _V1_CANDIDATE_STATUS
        or candidate.get("evidence_scope") != "private_development_only"
        or candidate.get("policy_id") != V1_PLAN_POLICY_ID
        or candidate.get("document_sha256") != _document_sha256(candidate)
        or file_sha256 != claim.get("sha256")
        or candidate.get("document_sha256") != claim.get("document_sha256")
        or path.stat().st_size != claim.get("bytes")
        or candidate.get("clock") != stitch["clock"]
        or candidate.get("permissions") != _FALSE_PERMISSIONS
        or candidate.get("effects")
        != {
            "candidate_audio_created": True,
            "model_run": True,
            "raw_stitch_mutated": False,
            "review_evidence_mutated": False,
            "separator_accepted": False,
            "separator_selected": False,
            "source_graph_mutated": False,
        }
        or not isinstance(bindings, Mapping)
        or bindings.get("remediation_plan_document_sha256")
        != v1_plan["document_sha256"]
        or bindings.get("stitch_document_sha256") != stitch["document_sha256"]
        or bindings.get("source_audio_sha256")
        != stitch["artifacts"]["source"]["sha256"]
        or bindings.get("raw_vocals_audio_sha256")
        != stitch["artifacts"]["vocals"]["sha256"]
        or bindings.get("raw_instrumental_audio_sha256")
        != stitch["artifacts"]["instrumental"]["sha256"]
        or bindings.get("raw_reconstruction_audio_sha256")
        != stitch["artifacts"]["reconstruction"]["sha256"]
        or not _sha256_hex(
            bindings.get("execution_state_sha256_before_candidate_report")
        )
        or candidate.get("summary")
        != {
            "verified_worker_window_count": len(v1_plan["windows"]),
            "patched_boundary_role_pair_count": sum(
                len(window["patch_target_roles"]) for window in v1_plan["windows"]
            ),
            "candidate_role_count": 3,
            "raw_control_count": 1,
            "raw_stitch_hashes_unchanged": True,
            "blind_boundary_review_required": True,
            "patch_edge_review_required": True,
            "complete_song_review_required": True,
        }
        or candidate.get("readiness")
        != {
            "worker_runs_complete": True,
            "candidate_audio_complete": True,
            "candidate_integrity_verified": True,
            "candidate_review_complete": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        }
    ):
        raise ValueError("private v1 join-remediation candidate differs")
    artifacts = candidate.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != set(_FULL_SONG_ROLES):
        raise ValueError("private v1 join-remediation candidate artifacts differ")
    for role in _FULL_SONG_ROLES:
        _verify_candidate_artifact(
            execution_root,
            artifacts[role],
            role=role,
            expected_frames=int(stitch["clock"]["frames"]),
        )


def _verify_resolved_review_bindings(
    remediation: Mapping[str, Any],
    *,
    stitch: Mapping[str, Any],
    stitch_sha256: str,
    execution: Mapping[str, Any],
    execution_sha256: str,
    candidate: Mapping[str, Any],
    candidate_sha256: str,
) -> None:
    bindings = remediation["bindings"]
    if (
        bindings["stitch_report_sha256"] != stitch_sha256
        or bindings["stitch_document_sha256"] != stitch["document_sha256"]
        or bindings["execution_report_sha256"] != execution_sha256
        or bindings["execution_state_sha256"] != execution["state_sha256"]
        or bindings["candidate_report_sha256"] != candidate_sha256
        or bindings["candidate_document_sha256"] != candidate["document_sha256"]
    ):
        raise ValueError("resolved join-remediation review input binding differs")
    unsafe = sum(
        remediation["overall_outcome_counts"][outcome]
        for outcome in ("raw_preferred", "neither", "cannot_tell")
    )
    if (
        unsafe != 0
        or remediation["readiness_evidence"]["all_patch_edges_candidate_or_equivalent"]
        is not True
        or remediation["readiness_evidence"][
            "all_complete_songs_candidate_or_equivalent"
        ]
        is not True
        or remediation["readiness_evidence"]["original_audible_joins_resolved"]
        is not False
        or remediation["readiness_evidence"]["publication_ready"] is not False
    ):
        raise ValueError("resolved join-remediation review is not safe to repatch")


def _verify_readiness_ledger(
    readiness: Mapping[str, Any],
    *,
    full_song_review: Mapping[str, Any],
    full_song_review_sha256: str,
    remediation: Mapping[str, Any],
    remediation_sha256: str,
    v1_plan: Mapping[str, Any],
) -> None:
    inputs = readiness.get("inputs")
    projection = readiness.get("readiness")
    policy = readiness.get("policy")
    gates = readiness.get("gates")
    assessment = _assess_join_remediation_review(remediation)
    full_song_assessment = readiness.get("full_song_duration_alignment_assessment")
    expected_audible = {
        role: full_song_review["boundary_summary"]["audible_join_boundaries_by_role"][
            role
        ]
        for role in _FULL_SONG_ROLES
    }
    if (
        readiness.get("schema") != READINESS_SCHEMA
        or readiness.get("evidence_scope") != "private_development_only"
        or readiness.get("document_sha256") != _document_sha256(readiness)
        or readiness.get("permissions") != _READINESS_PERMISSIONS
        or readiness.get("effects") != _READINESS_EFFECTS
        or not isinstance(inputs, Mapping)
        or inputs.get("full_song_review_result_sha256") != full_song_review_sha256
        or inputs.get("full_song_review_result_document_sha256")
        != full_song_review["document_sha256"]
        or inputs.get("full_song_join_remediation_review_result_sha256")
        != remediation_sha256
        or inputs.get("full_song_join_remediation_review_result_document_sha256")
        != remediation["document_sha256"]
        or inputs.get("full_song_alignment_result_sha256")
        != v1_plan["bindings"]["alignment_result_sha256"]
        or inputs.get("full_song_alignment_result_document_sha256")
        != v1_plan["bindings"]["alignment_document_sha256"]
        or readiness.get("full_song_join_remediation_assessment") != assessment
        or not isinstance(full_song_assessment, Mapping)
        or full_song_assessment.get("audible_join_boundaries_by_role")
        != expected_audible
        or full_song_assessment.get("gate_passed") is not False
        or full_song_assessment.get("acceptance_gate_closed") is not False
        or full_song_assessment.get("all_role_boundaries_clean") is not False
        or projection
        != {
            "experimental_studio_route_ready": False,
            "one_action_simple_route_ready": False,
            "open_gate_count": 8,
            "passed_gate_count": 3,
            "publication_ready": False,
            "required_gate_count": 11,
            "stage": "private_bounded_vocal_research",
        }
        or readiness.get("status") != "blocked_private_bounded_vocal_midi_evidence_only"
        or not isinstance(policy, Mapping)
        or policy.get("join_remediation_review_can_close_duration_alignment_gate")
        is not False
        or not isinstance(gates, list)
        or _gate_status(gates, "full_song_duration_and_alignment") != "open"
    ):
        raise ValueError("private publication-readiness ledger differs")


def _equivalent_boundary_role_pairs(
    remediation: Mapping[str, Any],
) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for unit in remediation["units"]:
        if unit["kind"] != "boundary_role_pair":
            continue
        parts = unit["unit_id"].split("-")
        if unit["resolved_choice"] == "equivalent":
            result.append((int(parts[1]), parts[2]))
    expected = remediation["counts_by_kind_and_outcome"]["boundary_role_pair"][
        "equivalent"
    ]
    if len(result) != expected or len(set(result)) != len(result):
        raise ValueError("equivalent join-remediation target inventory differs")
    return sorted(result)


def _verified_v1_patch_inventory(
    candidate: Mapping[str, Any],
    *,
    execution: Mapping[str, Any],
    execution_root: Path,
) -> dict[tuple[int, str], dict[str, Any]]:
    expected: dict[tuple[int, str], dict[str, Any]] = {}
    windows_by_index = {
        int(window["window_index"]): window for window in execution["windows"]
    }
    for patch in candidate.get("patches", []):
        if not isinstance(patch, Mapping):
            raise ValueError("private v1 candidate patch inventory differs")
        window = windows_by_index.get(patch.get("window_index"))
        role = patch.get("role")
        if window is None or role not in window["patch_target_roles"]:
            raise ValueError("private v1 candidate patch inventory differs")
        selected = _selected_attempt(window)
        output = selected["outputs"][role]
        key = (int(window["boundary_index"]), str(role))
        expected_patch = {
            "window_index": window["window_index"],
            "boundary_index": window["boundary_index"],
            "role": role,
            "start_frame": window["patch_start_frame"],
            "end_frame": window["patch_end_frame"],
            "edge_blend_frames": EDGE_BLEND_FRAMES,
            "worker_output_sha256": output["sha256"],
        }
        if any(patch.get(field) != value for field, value in expected_patch.items()):
            raise ValueError("private v1 candidate patch inventory differs")
        changed = patch.get("changed_sample_values_before_pcm24_rounding")
        if type(changed) is not int or changed < 1 or key in expected:
            raise ValueError("private v1 candidate patch inventory differs")
        worker_path = _selected_worker_path(execution_root, selected, role)
        expected[key] = {
            **expected_patch,
            "worker_output_bytes": output["bytes"],
            "worker_output_frames": output["frames"],
            "worker_output_path": worker_path,
        }
    expected_count = sum(
        len(item["patch_target_roles"]) for item in execution["windows"]
    )
    if len(expected) != expected_count:
        raise ValueError("private v1 candidate patch inventory differs")
    return expected


def _expanded_windows(
    pairs: list[tuple[int, str]],
    *,
    review: Mapping[str, Any],
    v1_plan: Mapping[str, Any],
    execution: Mapping[str, Any],
    v1_patches: Mapping[tuple[int, str], Mapping[str, Any]],
    total_frames: int,
) -> list[dict[str, Any]]:
    boundary_frames = {
        int(item["boundary_index"]): int(item["frame"]) for item in review["boundaries"]
    }
    original_audible = {
        (int(item["boundary_index"]), role)
        for item in review["boundaries"]
        for role in _ROLES
        if item["ratings"][role] == "audible_join"
    }
    plan_by_boundary = {
        int(item["boundary_index"]): item for item in v1_plan["windows"]
    }
    execution_by_boundary = {
        int(item["boundary_index"]): item for item in execution["windows"]
    }
    result: list[dict[str, Any]] = []
    for index, (boundary_index, role) in enumerate(pairs, start=1):
        if (boundary_index, role) not in original_audible:
            raise ValueError("equivalent target was not an original audible join")
        v1_window = plan_by_boundary.get(boundary_index)
        execution_window = execution_by_boundary.get(boundary_index)
        patch = v1_patches.get((boundary_index, role))
        if (
            v1_window is None
            or execution_window is None
            or patch is None
            or role not in v1_window["patch_target_roles"]
        ):
            raise ValueError("equivalent target has no sealed v1 worker output")
        boundary_frame = boundary_frames[boundary_index]
        patch_start = boundary_frame - PATCH_HALF_FRAMES
        patch_end = boundary_frame + PATCH_HALF_FRAMES
        if (
            patch_start < int(v1_window["source_start_frame"])
            or patch_end > int(v1_window["source_end_frame"])
            or patch_start < 0
            or patch_end > total_frames
            or patch_end - patch_start <= 2 * EDGE_BLEND_FRAMES
        ):
            raise ValueError("equivalent join cannot fit expanded v2 patch geometry")
        for other_key, other_patch in v1_patches.items():
            if other_key == (boundary_index, role) or other_key[1] != role:
                continue
            if (
                patch_start < int(other_patch["end_frame"])
                and int(other_patch["start_frame"]) < patch_end
            ):
                raise ValueError(
                    "expanded v2 patch overlaps a preserved same-role v1 patch"
                )
        selected = _selected_attempt(execution_window)
        authorisation = execution_window["authorisation_report"]
        local_start = patch_start - int(v1_window["source_start_frame"])
        local_end = patch_end - int(v1_window["source_start_frame"])
        result.append(
            {
                "window_index": index,
                "boundary_index": boundary_index,
                "boundary_frame": boundary_frame,
                "boundary_seconds": boundary_frame / TARGET_SAMPLE_RATE,
                "source_start_frame": v1_window["source_start_frame"],
                "source_end_frame": v1_window["source_end_frame"],
                "source_start_seconds": v1_window["source_start_seconds"],
                "source_end_seconds": v1_window["source_end_seconds"],
                "patch_start_frame": patch_start,
                "patch_end_frame": patch_end,
                "patch_start_seconds": patch_start / TARGET_SAMPLE_RATE,
                "patch_end_seconds": patch_end / TARGET_SAMPLE_RATE,
                "patch_target_role": role,
                "v1_window_index": v1_window["window_index"],
                "v1_selected_attempt": execution_window["selected_attempt"],
                "v1_selected_attempt_evidence_sha256": selected["evidence_sha256"],
                "v1_selected_attempt_receipt_sha256": selected["receipt_sha256"],
                "v1_selected_attempt_timing_sha256": selected["timing_sha256"],
                "v1_authorisation_report_sha256": authorisation["sha256"],
                "v1_authorisation_document_sha256": authorisation["document_sha256"],
                "v1_authorised_source_audio_sha256": authorisation["audio"]["sha256"],
                "v1_worker_output_sha256": patch["worker_output_sha256"],
                "v1_worker_output_bytes": patch["worker_output_bytes"],
                "v1_worker_output_frames": patch["worker_output_frames"],
                "worker_local_patch_start_frame": local_start,
                "worker_local_patch_end_frame": local_end,
                "worker_reuse_status": "sealed_v1_output_verified_no_model_call",
                "candidate_status": "not_created",
            }
        )
    return result


def _selected_attempt(window: Mapping[str, Any]) -> Mapping[str, Any]:
    selected = window.get("selected_attempt")
    attempts = window.get("attempts")
    if (
        window.get("status") != "verified_complete"
        or type(selected) is not int
        or selected < 1
        or not isinstance(attempts, list)
    ):
        raise ValueError("private v1 remediation selected attempt differs")
    matches = [
        item
        for item in attempts
        if isinstance(item, Mapping)
        and item.get("attempt") == selected
        and item.get("status") == "verified_complete"
    ]
    if len(matches) != 1:
        raise ValueError("private v1 remediation selected attempt differs")
    return matches[0]


def _verify_v1_authorisation(
    execution_root: Path,
    claim: Any,
    *,
    planned: Mapping[str, Any],
) -> None:
    if not isinstance(claim, Mapping) or not isinstance(claim.get("audio"), Mapping):
        raise ValueError("private v1 remediation authorisation differs")
    report_path = _private_child_regular(
        execution_root,
        claim.get("path"),
        "private v1 remediation authorisation report",
    )
    report_snapshot = _load_private_json_snapshot(
        report_path, "private v1 remediation authorisation report"
    )
    report = report_snapshot["document"]
    audio_claim = claim["audio"]
    excerpt = report.get("excerpt")
    local_input = report.get("original", {}).get("local_model_input")
    artifact = local_input.get("artifact") if isinstance(local_input, Mapping) else None
    geometry = local_input.get("geometry") if isinstance(local_input, Mapping) else None
    audio_path = _private_child_regular(
        execution_root,
        audio_claim.get("path"),
        "private v1 remediation authorised source audio",
    )
    if (
        report_snapshot["sha256"] != claim.get("sha256")
        or report_path.stat().st_size != claim.get("bytes")
        or report.get("schema") != "sunofriend.private-authorised-separation-excerpt.v1"
        or report.get("status") != "complete_review_required"
        or report.get("evidence_scope") != "private_development_only"
        or report.get("document_sha256") != claim.get("document_sha256")
        or report.get("document_sha256") != _document_sha256(report)
        or not isinstance(excerpt, Mapping)
        or excerpt.get("selection_policy") != V1_PLAN_POLICY_ID
        or excerpt.get("join_remediation_window_index") != planned["window_index"]
        or excerpt.get("boundary_index") != planned["boundary_index"]
        or excerpt.get("canonical_start_frame") != planned["source_start_frame"]
        or excerpt.get("canonical_end_frame") != planned["source_end_frame"]
        or not math.isclose(
            float(excerpt.get("start_seconds", math.nan)),
            planned["source_start_frame"] / TARGET_SAMPLE_RATE,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        )
        or not math.isclose(
            float(excerpt.get("end_seconds", math.nan)),
            planned["source_end_frame"] / TARGET_SAMPLE_RATE,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        )
        or not isinstance(artifact, Mapping)
        or artifact.get("path") != "LOCAL-MODEL-INPUT/source-44100.wav"
        or artifact.get("sha256") != audio_claim.get("sha256")
        or artifact.get("bytes") != audio_claim.get("bytes")
        or geometry
        != {
            "sample_rate": TARGET_SAMPLE_RATE,
            "channels": 2,
            "frames": int(planned["source_end_frame"])
            - int(planned["source_start_frame"]),
            "duration_seconds": (
                int(planned["source_end_frame"]) - int(planned["source_start_frame"])
            )
            / TARGET_SAMPLE_RATE,
        }
        or not _all_false(report.get("permissions"))
        or report.get("effects")
        != {
            "local_excerpt_created": True,
            "model_run": False,
            "source_audio_mutated": False,
            "source_graph_mutated": False,
        }
    ):
        raise ValueError("private v1 remediation authorisation differs")
    _verify_pcm24_audio(
        audio_path,
        audio_claim,
        expected_frames=int(planned["source_end_frame"])
        - int(planned["source_start_frame"]),
    )


def _selected_worker_path(
    execution_root: Path, selected: Mapping[str, Any], role: str
) -> Path:
    relative_attempt = selected.get("path")
    if not isinstance(relative_attempt, str):
        raise ValueError("private v1 selected worker path differs")
    return _private_child_regular(
        execution_root,
        f"{relative_attempt}/staging/quarantine/STEMS/{role}.wav",
        "private v1 selected worker output",
    )


def _verify_candidate_artifact(
    execution_root: Path,
    claim: Any,
    *,
    role: str,
    expected_frames: int,
) -> None:
    if not isinstance(claim, Mapping):
        raise ValueError("private v1 candidate artifact differs")
    path = _private_child_regular(
        execution_root,
        claim.get("path"),
        f"private v1 {role} candidate audio",
    )
    _verify_pcm24_audio(path, claim, expected_frames=expected_frames)
    geometry = claim.get("geometry")
    if not isinstance(geometry, Mapping) or geometry != {
        "sample_rate": TARGET_SAMPLE_RATE,
        "channels": 2,
        "sample_width_bytes": 3,
        "frames": expected_frames,
    }:
        raise ValueError("private v1 candidate artifact geometry differs")


def _verify_pcm24_audio(
    path: Path, claim: Mapping[str, Any], *, expected_frames: int
) -> None:
    import soundfile

    info = soundfile.info(path)
    if (
        _sha256(path) != claim.get("sha256")
        or path.stat().st_size != claim.get("bytes")
        or int(info.samplerate) != TARGET_SAMPLE_RATE
        or int(info.channels) != 2
        or int(info.frames) != expected_frames
        or info.subtype != "PCM_24"
    ):
        raise ValueError("private v1 sealed audio differs")


def _private_child_regular(root: Path, relative: Any, label: str) -> Path:
    if not isinstance(relative, str):
        raise ValueError(f"{label} path differs")
    pure = Path(relative)
    if pure.is_absolute() or not pure.parts or ".." in pure.parts:
        raise ValueError(f"{label} path differs")
    current = root
    for part in pure.parts[:-1]:
        current = current / part
        _require_private_directory(current, label)
    path = root / pure
    _require_private_regular(path, label)
    return path


def _private_child_directory(root: Path, relative: Any, label: str) -> Path:
    if not isinstance(relative, str):
        raise ValueError(f"{label} path differs")
    pure = Path(relative)
    if pure.is_absolute() or not pure.parts or ".." in pure.parts:
        raise ValueError(f"{label} path differs")
    current = root
    for part in pure.parts:
        current = current / part
        _require_private_directory(current, label)
    return current


def _gate_status(gates: list[Any], gate_id: str) -> str | None:
    matches = [
        item.get("status")
        for item in gates
        if isinstance(item, Mapping) and item.get("gate_id") == gate_id
    ]
    return matches[0] if len(matches) == 1 else None


def _require_disjoint_patch_regions(windows: list[Mapping[str, Any]]) -> None:
    for role in _ROLES:
        ordered = sorted(
            (item for item in windows if item["patch_target_role"] == role),
            key=lambda item: int(item["patch_start_frame"]),
        )
        for left, right in zip(ordered, ordered[1:]):
            if int(left["patch_end_frame"]) > int(right["patch_start_frame"]):
                raise ValueError(
                    "private v2 same-role join-remediation patch regions overlap"
                )


def _require_snapshot_unchanged(snapshot: Mapping[str, Any], label: str) -> None:
    current = _load_private_json_snapshot(snapshot["path"], label)
    if (
        current["sha256"] != snapshot["sha256"]
        or current["document"] != snapshot["document"]
    ):
        raise ValueError(f"{label} changed during v2 planning")


def _sha256_hex(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _all_false(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and bool(value)
        and all(item is False for item in value.values())
    )


__all__: tuple[str, ...] = ()
