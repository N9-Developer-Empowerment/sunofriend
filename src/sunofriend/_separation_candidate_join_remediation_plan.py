"""Plan a fresh join-remediation iteration from exact candidate review evidence.

This private-development contract consumes the resolved v2 candidate review,
its candidate-bound alignment result and the resulting failed readiness
reassessment.  It derives work only from explicit ``audible_join`` ratings.
It writes no audio, starts no model and cannot select or accept a separator.
"""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256
from ._separation_candidate_full_song_review import _verify_passing_v2_review_result
from ._separation_candidate_readiness_reassessment import (
    SCHEMA as REASSESSMENT_SCHEMA,
    STATUS as REASSESSMENT_STATUS,
    _CANDIDATE_IDENTITY,
    _FALSE_EFFECTS as REASSESSMENT_EFFECTS,
    _reverify_all,
    _verify_candidate_alignment_result,
    _verify_candidate_review_result,
)
from ._separation_full_song_executor import _require_private_directory
from ._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
    _require_output_disjoint_from_inputs,
)
from ._separation_full_song_join_remediation_plan import (
    EDGE_BLEND_FRAMES,
    TARGET_SAMPLE_RATE,
)
from ._separation_full_song_join_remediation_plan_v2 import (
    PATCH_HALF_FRAMES,
)
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
    _write_json_exclusive,
)
from ._separation_full_song_join_remediation_review_v2 import (
    _load_review_inputs,
)
from ._separation_melroformer_real_bridge import MAXIMUM_EXCERPT_FRAMES


SCHEMA = "sunofriend.private-separation-candidate-join-remediation-plan.v1"
STATUS = "planned_review_derived_join_reinference_no_model_run"
POLICY_ID = "candidate-review-audible-join-expanded-context-reinference-v1"
REPORT_NAME = "private-separation-candidate-join-remediation-plan.json"

_REPAIRABLE_ROLES = ("vocals", "instrumental")
_RATED_ROLES = (*_REPAIRABLE_ROLES, "reconstruction")
_FALSE_EFFECTS = {
    "audio_created_or_mutated": False,
    "candidate_audio_created": False,
    "model_run": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "review_evidence_mutated": False,
    "separator_accepted": False,
    "separator_selected": False,
    "source_graph_mutated": False,
    "v2_candidate_mutated": False,
}


def _plan_private_candidate_join_remediation(
    v2_review_result_path: str | Path,
    *,
    candidate_review_result_path: str | Path,
    candidate_alignment_result_path: str | Path,
    readiness_reassessment_path: str | Path,
    v2_execution_dir: str | Path,
    v2_plan_path: str | Path,
    v1_execution_dir: str | Path,
    stitch_package_dir: str | Path,
    full_song_review_result_path: str | Path,
    v1_plan_path: str | Path,
    resolved_join_review_result_path: str | Path,
    publication_readiness_path: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Write a sealed model-free plan from failed candidate-bound evidence."""

    output = Path(out).expanduser().absolute()
    if output.name != REPORT_NAME:
        raise ValueError(f"private candidate remediation filename must be {REPORT_NAME}")
    if os.path.lexists(output):
        raise FileExistsError(f"private candidate remediation plan exists: {output}")

    context = _load_review_inputs(
        v2_execution_dir,
        v2_plan_path=v2_plan_path,
        v1_execution_dir=v1_execution_dir,
        stitch_package_dir=stitch_package_dir,
        full_song_review_result_path=full_song_review_result_path,
        v1_plan_path=v1_plan_path,
        resolved_join_review_result_path=resolved_join_review_result_path,
        publication_readiness_path=publication_readiness_path,
    )
    v2_snapshot = _load_private_json_snapshot(
        v2_review_result_path, "private resolved v2 join review result"
    )
    review_snapshot = _load_private_json_snapshot(
        candidate_review_result_path, "private candidate full-song review result"
    )
    alignment_snapshot = _load_private_json_snapshot(
        candidate_alignment_result_path,
        "private candidate full-song alignment result",
    )
    reassessment_snapshot = _load_private_json_snapshot(
        readiness_reassessment_path,
        "private candidate readiness reassessment",
    )
    _verify_passing_v2_review_result(v2_snapshot, context=context)
    _verify_candidate_review_result(
        review_snapshot["document"], v2_snapshot=v2_snapshot, context=context
    )
    _verify_candidate_alignment_result(
        alignment_snapshot["document"], v2_snapshot=v2_snapshot, context=context
    )
    _verify_failed_join_reassessment(
        reassessment_snapshot["document"],
        reassessment_sha256=reassessment_snapshot["sha256"],
        v2_snapshot=v2_snapshot,
        review_snapshot=review_snapshot,
        alignment_snapshot=alignment_snapshot,
        context=context,
    )
    _require_output_disjoint_from_inputs(
        output,
        evidence_roots=(context["v1_root"], context["v2_root"], context["stitch_root"]),
        evidence_paths=(
            v2_snapshot["path"],
            review_snapshot["path"],
            alignment_snapshot["path"],
            reassessment_snapshot["path"],
            context["v2_snapshot"]["path"],
            context["v2_plan_snapshot"]["path"],
            context["stitch_snapshot"]["path"],
            context["v1_execution_snapshot"]["path"],
            context["v1_candidate_snapshot"]["path"],
            *context["authority_paths"],
        ),
    )

    review = review_snapshot["document"]
    audible = review["boundary_summary"]["audible_join_boundaries_by_role"]
    if audible["reconstruction"]:
        raise ValueError(
            "audible reconstruction joins require diagnosis before role remediation"
        )
    if any(
        review["boundary_summary"]["rating_counts_by_role"][role]["cannot_tell"]
        for role in _RATED_ROLES
    ):
        raise ValueError("cannot-tell candidate boundaries require human clarification")
    targets = _target_roles_by_boundary(audible)
    if not targets:
        raise ValueError("candidate review has no audible role join to remediate")

    clock = context["stitch"]["clock"]
    if int(clock["sample_rate"]) != TARGET_SAMPLE_RATE:
        raise ValueError("private candidate remediation source clock differs")
    total_frames = int(clock["frames"])
    if total_frames < MAXIMUM_EXCERPT_FRAMES:
        raise ValueError("private candidate remediation song is shorter than one window")
    prior_targets = _prior_v2_target_pairs(context["v2_plan"])
    boundary_rows = {
        int(row["boundary_index"]): row for row in review["boundaries"]
    }
    windows = [
        _window_plan(
            boundary_rows[boundary_index],
            target_roles=roles,
            prior_targets=prior_targets,
            total_frames=total_frames,
            window_index=index,
        )
        for index, (boundary_index, roles) in enumerate(sorted(targets.items()), start=1)
    ]
    _require_disjoint_patch_regions(windows)
    target_pairs = [
        (int(window["boundary_index"]), role)
        for window in windows
        for role in window["patch_target_roles"]
    ]
    outside_prior = [pair for pair in target_pairs if pair not in prior_targets]
    v2_report = context["v2_report"]

    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "candidate_identity": _CANDIDATE_IDENTITY,
        "bindings": {
            "v2_review_result_sha256": v2_snapshot["sha256"],
            "v2_review_result_document_sha256": v2_snapshot["document"][
                "document_sha256"
            ],
            "candidate_review_result_sha256": review_snapshot["sha256"],
            "candidate_review_result_document_sha256": review["document_sha256"],
            "candidate_alignment_result_sha256": alignment_snapshot["sha256"],
            "candidate_alignment_result_document_sha256": alignment_snapshot[
                "document"
            ]["document_sha256"],
            "readiness_reassessment_sha256": reassessment_snapshot["sha256"],
            "readiness_reassessment_document_sha256": reassessment_snapshot[
                "document"
            ]["document_sha256"],
            "v2_execution_report_sha256": context["v2_snapshot"]["sha256"],
            "v2_execution_document_sha256": v2_report["document_sha256"],
            "source_audio_sha256": context["stitch"]["artifacts"]["source"][
                "sha256"
            ],
            "v2_vocals_audio_sha256": v2_report["artifacts"]["vocals"]["sha256"],
            "v2_instrumental_audio_sha256": v2_report["artifacts"]["instrumental"]
            ["sha256"],
            "v2_reconstruction_audio_sha256": v2_report["artifacts"][
                "reconstruction"
            ]["sha256"],
        },
        "clock": deepcopy(clock),
        "protocol": {
            "source_window_frames": MAXIMUM_EXCERPT_FRAMES,
            "source_window_seconds": MAXIMUM_EXCERPT_FRAMES / TARGET_SAMPLE_RATE,
            "patch_half_frames": PATCH_HALF_FRAMES,
            "patch_duration_frames": 2 * PATCH_HALF_FRAMES,
            "patch_duration_seconds": 2 * PATCH_HALF_FRAMES / TARGET_SAMPLE_RATE,
            "edge_blend_frames": EDGE_BLEND_FRAMES,
            "edge_blend_seconds": EDGE_BLEND_FRAMES / TARGET_SAMPLE_RATE,
            "edge_blend_shape": "equal_power_old_to_new_then_new_to_old",
            "model_invocation": (
                "one future independent Kim Vocal 2 inference over the exact "
                "canonical source window per unique reviewed boundary"
            ),
            "candidate_policy": (
                "start from the verified v2 candidate; replace only each named "
                "audible role inside its patch, preserve all other v2 PCM24 "
                "samples, and recompute a diagnostic reconstruction"
            ),
            "source_windows_may_overlap": True,
            "patch_regions_must_not_overlap": True,
        },
        "windows": windows,
        "summary": {
            "human_rated_audible_role_join_count": len(target_pairs),
            "unique_boundary_count": len(windows),
            "planned_model_call_count": len(windows),
            "target_roles": [
                role
                for role in _REPAIRABLE_ROLES
                if any(role in window["patch_target_roles"] for window in windows)
            ],
            "outside_prior_v2_target_role_join_count": len(outside_prior),
            "private_listener_notes_copied": False,
            "v2_candidate_control_count": 1,
            "new_candidate_count": 0,
        },
        "required_future_review": {
            "blind_v2_candidate_versus_new_candidate_boundary_role_pairs": len(
                target_pairs
            ),
            "new_patch_edge_role_checks": 2 * len(target_pairs),
            "new_candidate_bound_complete_song_roles": list(_RATED_ROLES),
            "new_candidate_bound_full_song_review_required": True,
            "new_candidate_bound_alignment_required": True,
            "automatic_preference_inference": False,
        },
        "readiness": {
            "failed_candidate_review_verified": True,
            "passing_candidate_alignment_verified": True,
            "review_derived_targets_verified": True,
            "targeted_remediation_plan_ready": True,
            "remediation_worker_runs_complete": False,
            "new_candidate_created": False,
            "new_candidate_review_complete": False,
            "new_candidate_alignment_complete": False,
            "final_human_acceptance_review_eligible": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "interpretation": {
            "audible_join_rating_is_repair_success": False,
            "clean_reconstruction_overrides_role_join_rating": False,
            "alignment_pass_is_role_fidelity": False,
            "newly_observed_join_is_v2_regression": False,
            "automatic_winner_selected": False,
            "separator_accepted": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_FALSE_EFFECTS),
        "limitations": [
            "This plan creates no audio and runs no model.",
            "Targets come only from explicit audible-join ratings in the resolved candidate review.",
            "Some latest ratings concern regions outside the earlier v2 repatch; they are current human evidence, not proof of a v2 regression.",
            "A future candidate may introduce edge or continuity artefacts and needs targeted plus fresh full-song review.",
            "The plan cannot select, accept, publish or expose a separator to a product route.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)

    _reverify_all(v2_snapshot, review_snapshot, alignment_snapshot, context)
    current_reassessment = _load_private_json_snapshot(
        reassessment_snapshot["path"], "private candidate readiness reassessment"
    )
    if (
        current_reassessment["sha256"] != reassessment_snapshot["sha256"]
        or current_reassessment["document"] != reassessment_snapshot["document"]
    ):
        raise ValueError("private candidate readiness reassessment changed")
    if not output.parent.exists():
        output.parent.mkdir(parents=True, mode=0o700)
    _require_private_directory(output.parent, "private candidate remediation root")
    _write_json_exclusive(output, document)
    return {**document, "report": str(output)}


def _verify_failed_join_reassessment(
    document: Mapping[str, Any],
    *,
    reassessment_sha256: str,
    v2_snapshot: Mapping[str, Any],
    review_snapshot: Mapping[str, Any],
    alignment_snapshot: Mapping[str, Any],
    context: Mapping[str, Any],
) -> None:
    bindings = document.get("bindings")
    evidence = document.get("evidence")
    readiness = document.get("readiness")
    if (
        document.get("schema") != REASSESSMENT_SCHEMA
        or document.get("status") != REASSESSMENT_STATUS
        or document.get("evidence_scope") != "private_development_only"
        or document.get("candidate_identity") != _CANDIDATE_IDENTITY
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("clock") != context["stitch"]["clock"]
        or document.get("permissions") != _FALSE_PERMISSIONS
        or document.get("effects") != REASSESSMENT_EFFECTS
        or document.get("next_action") != "remediate_failed_candidate_evidence"
        or not isinstance(bindings, Mapping)
        or not isinstance(evidence, Mapping)
        or not isinstance(readiness, Mapping)
    ):
        raise ValueError("private candidate readiness reassessment differs")
    expected_bindings = {
        "v2_review_result_sha256": v2_snapshot["sha256"],
        "v2_review_result_document_sha256": v2_snapshot["document"][
            "document_sha256"
        ],
        "candidate_review_result_sha256": review_snapshot["sha256"],
        "candidate_review_result_document_sha256": review_snapshot["document"][
            "document_sha256"
        ],
        "candidate_alignment_result_sha256": alignment_snapshot["sha256"],
        "candidate_alignment_result_document_sha256": alignment_snapshot["document"]
        ["document_sha256"],
        "v2_execution_report_sha256": context["v2_snapshot"]["sha256"],
        "v2_execution_document_sha256": context["v2_report"]["document_sha256"],
        "stitch_report_sha256": context["stitch_snapshot"]["sha256"],
        "stitch_document_sha256": context["stitch"]["document_sha256"],
    }
    expected_evidence = {
        "targeted_v2_absolute_cleanliness_pass": True,
        "candidate_full_song_review_complete": True,
        "all_candidate_boundaries_clean": False,
        "all_candidate_full_song_roles_useful": True,
        "candidate_alignment_complete": True,
        "candidate_alignment_gate_passed": True,
        "technical_and_listening_prerequisites_met": False,
    }
    expected_readiness = {
        "reassessment_complete": True,
        "final_human_acceptance_review_eligible": False,
        "final_human_acceptance_review_complete": False,
        "original_audible_joins_resolved": False,
        "separator_selected": False,
        "separator_accepted": False,
        "product_route_enabled": False,
        "publication_ready": False,
    }
    if (
        bindings != expected_bindings
        or evidence != expected_evidence
        or readiness != expected_readiness
        or not isinstance(reassessment_sha256, str)
        or len(reassessment_sha256) != 64
    ):
        raise ValueError("private failed candidate readiness evidence differs")


def _target_roles_by_boundary(
    audible: Mapping[str, Any],
) -> dict[int, list[str]]:
    result: dict[int, list[str]] = {}
    for role in _REPAIRABLE_ROLES:
        values = audible.get(role)
        if not isinstance(values, list):
            raise ValueError("candidate audible-join evidence differs")
        for value in values:
            if type(value) is not int or value < 1:
                raise ValueError("candidate audible-join evidence differs")
            result.setdefault(value, []).append(role)
    return result


def _prior_v2_target_pairs(plan: Mapping[str, Any]) -> set[tuple[int, str]]:
    windows = plan.get("windows")
    if not isinstance(windows, list):
        raise ValueError("private v2 target inventory differs")
    pairs: set[tuple[int, str]] = set()
    for window in windows:
        if not isinstance(window, Mapping):
            raise ValueError("private v2 target inventory differs")
        role = window.get("patch_target_role")
        roles = window.get("patch_target_roles")
        if roles is None and isinstance(role, str):
            roles = [role]
        if (
            type(window.get("boundary_index")) is not int
            or not isinstance(roles, list)
            or any(role not in _REPAIRABLE_ROLES for role in roles)
        ):
            raise ValueError("private v2 target inventory differs")
        pairs.update((int(window["boundary_index"]), role) for role in roles)
    return pairs


def _window_plan(
    boundary: Mapping[str, Any],
    *,
    target_roles: list[str],
    prior_targets: set[tuple[int, str]],
    total_frames: int,
    window_index: int,
) -> dict[str, Any]:
    boundary_index = int(boundary["boundary_index"])
    boundary_frame = int(boundary["frame"])
    window_start = max(
        0,
        min(
            boundary_frame - MAXIMUM_EXCERPT_FRAMES // 2,
            total_frames - MAXIMUM_EXCERPT_FRAMES,
        ),
    )
    window_end = window_start + MAXIMUM_EXCERPT_FRAMES
    patch_start = boundary_frame - PATCH_HALF_FRAMES
    patch_end = boundary_frame + PATCH_HALF_FRAMES
    if (
        patch_start < window_start
        or patch_end > window_end
        or patch_start < 0
        or patch_end > total_frames
        or patch_end - patch_start <= 2 * EDGE_BLEND_FRAMES
    ):
        raise ValueError("audible join cannot fit candidate remediation geometry")
    roles = [role for role in _REPAIRABLE_ROLES if role in target_roles]
    return {
        "window_index": window_index,
        "boundary_index": boundary_index,
        "boundary_frame": boundary_frame,
        "boundary_seconds": boundary_frame / TARGET_SAMPLE_RATE,
        "source_start_frame": window_start,
        "source_end_frame": window_end,
        "source_start_seconds": window_start / TARGET_SAMPLE_RATE,
        "source_end_seconds": window_end / TARGET_SAMPLE_RATE,
        "patch_start_frame": patch_start,
        "patch_end_frame": patch_end,
        "patch_start_seconds": patch_start / TARGET_SAMPLE_RATE,
        "patch_end_seconds": patch_end / TARGET_SAMPLE_RATE,
        "patch_target_roles": roles,
        "previous_v2_target_roles": [
            role for role in roles if (boundary_index, role) in prior_targets
        ],
        "newly_observed_outside_v2_target_roles": [
            role for role in roles if (boundary_index, role) not in prior_targets
        ],
        "worker_output_roles": list(_REPAIRABLE_ROLES),
        "worker_status": "not_run",
        "candidate_status": "not_created",
    }


def _require_disjoint_patch_regions(windows: list[Mapping[str, Any]]) -> None:
    for left, right in zip(windows, windows[1:]):
        if int(left["patch_end_frame"]) > int(right["patch_start_frame"]):
            raise ValueError("private candidate remediation patch regions overlap")


__all__: tuple[str, ...] = ()
