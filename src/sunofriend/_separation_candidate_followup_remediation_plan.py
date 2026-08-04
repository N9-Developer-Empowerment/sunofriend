"""Plan a second bounded candidate iteration from the failed blind review."""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import re
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256
from ._separation_candidate_followup_full_song_review import (
    _verified_exact_targeted_result,
)
from ._separation_candidate_join_remediation_review import (
    _load_verified_inputs,
    _validated_patches,
)
from ._separation_full_song_executor import _require_private_directory
from ._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
    _require_output_disjoint_from_inputs,
)
from ._separation_full_song_join_remediation_plan import TARGET_SAMPLE_RATE
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
    _write_json_exclusive,
)
from ._separation_melroformer_real_bridge import MAXIMUM_EXCERPT_FRAMES


SCHEMA = "sunofriend.private-separation-candidate-followup-remediation-plan.v2"
STATUS = "planned_failed_blind_review_remediation_no_model_run"
POLICY_ID = "failed-followup-review-shifted-context-variant-search-v2"
REPORT_NAME = "private-separation-candidate-followup-remediation-plan.json"
CONTEXT_SHIFT_FRAMES = 2 * TARGET_SAMPLE_RATE
EXTENDED_EDGE_BLEND_FRAMES = TARGET_SAMPLE_RATE // 4
_ROLES = ("vocals", "instrumental")
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
}
_EDGE_ID = re.compile(r"^edge-(?P<boundary>[0-9]+)-(?P<role>vocals|instrumental)-(?P<edge>start|end)$")


def _plan_private_candidate_followup_remediation(
    targeted_review_result_path: str | Path,
    *,
    reviewed_export_path: str | Path,
    targeted_review_package_dir: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Write a model-free plan from exact failed identity-resolved evidence."""

    output = Path(out).expanduser().absolute()
    if output.name != REPORT_NAME:
        raise ValueError(f"private follow-up remediation filename must be {REPORT_NAME}")
    if os.path.lexists(output):
        raise FileExistsError(f"private follow-up remediation plan exists: {output}")
    if not output.parent.exists():
        output.parent.mkdir(parents=True, mode=0o700)
        output.parent.chmod(0o700)
    _require_private_directory(output.parent, "private follow-up remediation plan root")

    execution = Path(execution_dir).expanduser().absolute()
    v2_execution = Path(v2_execution_dir).expanduser().absolute()
    review_package = Path(targeted_review_package_dir).expanduser().absolute()
    inputs = _load_verified_inputs(execution, v2_execution)
    result = _verified_exact_targeted_result(
        targeted_review_result_path,
        reviewed_export_path=reviewed_export_path,
        targeted_review_package_dir=review_package,
        execution_dir=execution,
        v2_execution_dir=v2_execution,
    )
    result_snapshot = _load_private_json_snapshot(
        targeted_review_result_path, "private targeted follow-up review result"
    )
    readiness = result["readiness_evidence"]
    if readiness["targeted_followup_listening_pass"] is not False:
        raise ValueError("passing targeted follow-up review needs no remediation plan")
    if readiness["all_complete_songs_followup_or_equivalent"] is not True:
        raise ValueError("complete-song regression requires broader candidate diagnosis")
    if (
        readiness["targeted_followup_review_complete"] is not True
        or readiness["fresh_all_boundaries_review_eligible"] is not False
        or readiness["fresh_alignment_eligible"] is not False
    ):
        raise ValueError("private failed targeted follow-up readiness differs")

    _require_output_disjoint_from_inputs(
        output,
        evidence_roots=(execution, v2_execution, review_package),
        evidence_paths=(
            result_snapshot["path"],
            Path(reviewed_export_path).expanduser().absolute(),
            inputs["execution_snapshot"]["path"],
            inputs["candidate_snapshot"]["path"],
            inputs["v2_snapshot"]["path"],
        ),
    )
    clock = inputs["execution"]["clock"]
    if int(clock["sample_rate"]) != TARGET_SAMPLE_RATE:
        raise ValueError("private follow-up remediation clock differs")
    patches = _validated_patches(
        inputs["candidate"],
        total_frames=int(clock["frames"]),
        boundary_count=int(clock["boundary_count"]),
    )
    actions = _derive_actions(result, patches=patches)
    model_boundaries = sorted(
        {
            boundary
            for (boundary, _), action in actions.items()
            if action["model_call_required"]
        }
    )
    windows = [
        _window(
            boundary,
            actions={
                role: actions[(boundary, role)]
                for role in _ROLES
                if (boundary, role) in actions
            },
            patches=patches,
            total_frames=int(clock["frames"]),
            window_index=index,
        )
        for index, boundary in enumerate(sorted({key[0] for key in actions}), start=1)
    ]
    action_counts: dict[str, int] = {}
    for action in actions.values():
        name = str(action["action"])
        action_counts[name] = action_counts.get(name, 0) + 1

    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "candidate_identity": "review_derived_followup_join_remediation",
        "bindings": {
            "targeted_review_result_sha256": result_snapshot["sha256"],
            "targeted_review_result_document_sha256": result["document_sha256"],
            "targeted_review_export_sha256": result["bindings"][
                "review_export_sha256"
            ],
            "followup_execution_report_sha256": inputs["execution_snapshot"][
                "sha256"
            ],
            "followup_execution_document_sha256": inputs["execution"][
                "document_sha256"
            ],
            "followup_candidate_report_sha256": inputs["candidate_snapshot"][
                "sha256"
            ],
            "followup_candidate_document_sha256": inputs["candidate"][
                "document_sha256"
            ],
            "v2_execution_report_sha256": inputs["v2_snapshot"]["sha256"],
            "v2_execution_document_sha256": inputs["v2"]["document_sha256"],
        },
        "clock": deepcopy(clock),
        "protocol": {
            "source_window_frames": MAXIMUM_EXCERPT_FRAMES,
            "source_window_seconds": MAXIMUM_EXCERPT_FRAMES / TARGET_SAMPLE_RATE,
            "candidate_base": "exact_review_derived_followup_candidate",
            "control_revert_source": "exact_immutable_v2_candidate",
            "reinference": "independent_shifted_context_model_call_per_unique_boundary",
            "reinference_context_direction": "later",
            "reinference_context_shift_frames": CONTEXT_SHIFT_FRAMES,
            "reinference_context_shift_seconds": CONTEXT_SHIFT_FRAMES
            / TARGET_SAMPLE_RATE,
            "edge_policy": (
                "preserve the preferred centre while exploring edge-aware blend "
                "and reinference variants; do not silently choose a winner"
            ),
            "candidate_variants": [
                {
                    "variant_id": "shifted-context-standard-edge",
                    "reinference_source": "shifted_context_worker",
                    "failed_edge_source": "shifted_context_worker",
                    "failed_edge_blend_frames": 4410,
                },
                {
                    "variant_id": "preserved-centre-extended-edge",
                    "reinference_source": "shifted_context_worker",
                    "failed_edge_source": "exact_followup_candidate_patch",
                    "failed_edge_blend_frames": EXTENDED_EDGE_BLEND_FRAMES,
                },
            ],
            "automatic_preference_inference": False,
        },
        "windows": windows,
        "summary": {
            "remediation_role_boundary_count": len(actions),
            "unique_boundary_count": len(windows),
            "planned_model_call_count": len(model_boundaries),
            "candidate_variant_count": 2,
            "model_boundaries": model_boundaries,
            "action_counts": action_counts,
            "successful_followup_boundary_pairs_preserved": sum(
                unit["kind"] == "boundary_role_pair"
                and unit["resolved_choice"] == "followup_candidate_preferred"
                and (int(unit["unit_id"].split("-")[1]), unit["unit_id"].split("-")[2])
                not in actions
                for unit in result["units"]
            ),
            "private_listener_notes_copied": False,
        },
        "required_future_review": {
            "all_remediated_role_boundaries_require_blind_comparison": True,
            "all_new_patch_edges_require_blind_comparison": True,
            "complete_song_roles_require_blind_comparison": [
                "vocals",
                "instrumental",
                "reconstruction",
            ],
            "fresh_all_boundary_review_after_targeted_pass": True,
            "fresh_alignment_after_full_review": True,
        },
        "readiness": {
            "failed_targeted_review_verified": True,
            "remediation_plan_complete": True,
            "remediation_execution_complete": False,
            "new_candidate_created": False,
            "new_candidate_review_complete": False,
            "new_candidate_alignment_complete": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "interpretation": {
            "equivalent_means_original_join_resolved": False,
            "neither_means_followup_edge_passed": False,
            "v2_preference_is_automatic_global_revert": False,
            "automatic_winner_selected": False,
            "separator_accepted": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_FALSE_EFFECTS),
        "limitations": [
            "This plan creates no audio and runs no model.",
            "Shifted context is required because repeating the earlier deterministic window would duplicate its worker output.",
            "Two explicit candidate variants preserve competing edge hypotheses; neither is preferred automatically.",
            "The plan preserves the complete-song pass but does not treat it as separator acceptance.",
            "Equivalent formerly-audible joins remain unresolved under the current gate.",
            "Neither-rated patch edges require new evidence rather than assumed smoothing.",
            "Every future candidate remains subject to fresh blind listening.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)
    _write_json_exclusive(output, document)
    return {**document, "report": str(output)}


def _derive_actions(
    result: Mapping[str, Any],
    *,
    patches: Mapping[tuple[int, str], Mapping[str, Any]],
) -> dict[tuple[int, str], dict[str, Any]]:
    actions: dict[tuple[int, str], dict[str, Any]] = {}
    for unit in result["units"]:
        kind = unit["kind"]
        outcome = unit["resolved_choice"]
        if outcome == "cannot_tell":
            raise ValueError("cannot-tell review evidence requires human clarification")
        if kind == "complete_song_pair":
            if outcome not in {"followup_candidate_preferred", "equivalent"}:
                raise ValueError("complete-song regression requires broader diagnosis")
            continue
        if kind == "boundary_role_pair":
            _, boundary_text, role = unit["unit_id"].split("-")
            key = (int(boundary_text), role)
            if key not in patches:
                raise ValueError("private failed boundary is not a candidate patch")
            if outcome == "followup_candidate_preferred":
                continue
            if outcome == "v2_control_preferred":
                actions[key] = {
                    "action": "revert_patch_to_v2_control",
                    "model_call_required": False,
                    "boundary_outcome": outcome,
                    "failed_edges": [],
                }
            elif outcome in {"equivalent", "neither"}:
                actions[key] = {
                    "action": "reinfer_role_boundary",
                    "model_call_required": True,
                    "boundary_outcome": outcome,
                    "failed_edges": [],
                }
            continue
        match = _EDGE_ID.fullmatch(unit["unit_id"])
        if kind != "patch_edge_pair" or match is None:
            raise ValueError("private targeted review unit identity differs")
        key = (int(match.group("boundary")), match.group("role"))
        if key not in patches:
            raise ValueError("private failed edge is not a candidate patch")
        if outcome in {"followup_candidate_preferred", "equivalent"}:
            continue
        current = actions.setdefault(
            key,
            {
                "action": "edge_aware_reinference_and_blend_search",
                "model_call_required": True,
                "boundary_outcome": "followup_candidate_preferred",
                "failed_edges": [],
            },
        )
        if current["action"] != "revert_patch_to_v2_control":
            current["action"] = "edge_aware_reinference_and_blend_search"
            current["model_call_required"] = True
        current["failed_edges"].append(
            {"edge": match.group("edge"), "outcome": outcome}
        )
    if not actions:
        raise ValueError("failed targeted review has no bounded remediation target")
    return actions


def _window(
    boundary: int,
    *,
    actions: Mapping[str, Mapping[str, Any]],
    patches: Mapping[tuple[int, str], Mapping[str, Any]],
    total_frames: int,
    window_index: int,
) -> dict[str, Any]:
    relevant = [patches[(boundary, role)] for role in actions]
    centre = sum(
        int(patch["patch_start_frame"]) + int(patch["patch_end_frame"])
        for patch in relevant
    ) // (2 * len(relevant))
    model_call_required = any(
        action["model_call_required"] for action in actions.values()
    )
    unshifted_start = max(
        0,
        min(
            centre - MAXIMUM_EXCERPT_FRAMES // 2,
            total_frames - MAXIMUM_EXCERPT_FRAMES,
        ),
    )
    requested_shift = CONTEXT_SHIFT_FRAMES if model_call_required else 0
    start = max(
        0,
        min(
            unshifted_start + requested_shift,
            total_frames - MAXIMUM_EXCERPT_FRAMES,
        ),
    )
    end = start + MAXIMUM_EXCERPT_FRAMES
    return {
        "window_index": window_index,
        "boundary_index": boundary,
        "source_start_frame": start,
        "source_end_frame": end,
        "source_start_seconds": start / TARGET_SAMPLE_RATE,
        "source_end_seconds": end / TARGET_SAMPLE_RATE,
        "model_call_required": model_call_required,
        "unshifted_source_start_frame": unshifted_start,
        "actual_context_shift_frames": start - unshifted_start,
        "role_actions": {
            role: {
                **deepcopy(action),
                "patch_start_frame": int(patches[(boundary, role)]["patch_start_frame"]),
                "patch_end_frame": int(patches[(boundary, role)]["patch_end_frame"]),
                "edge_blend_frames": int(patches[(boundary, role)]["edge_blend_frames"]),
            }
            for role, action in sorted(actions.items())
        },
        "candidate_status": "not_created",
    }


__all__: tuple[str, ...] = ()
