"""Plan a global overlap-add fallback after a strict zero-eligible review.

This is a private-development planning boundary.  It verifies the completed
36-unit review and its immutable evidence chain, but it does not run a model,
create audio, choose a candidate, or enable source separation anywhere in the
product.
"""

from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from ._separation_authorised_excerpt import _document_sha256
from ._separation_candidate_followup_full_song_review import (
    _verify_stitch_bound_to_v2,
)
from ._separation_candidate_followup_variant_full_song_review import (
    _verified_exact_variant_result,
)
from ._separation_candidate_followup_variant_review import (
    _input_bindings,
    _load_verified_variant_inputs,
)
from ._separation_full_song_executor import _require_private_directory
from ._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
    _require_output_disjoint_from_inputs,
)
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
    _write_json_exclusive,
)
from ._separation_full_song_stitch import REPORT_NAME as STITCH_REPORT_NAME
from ._separation_full_song_review import _load_stitch_report, _verify_stitch_audio
from ._separation_melroformer_real_bridge import MAXIMUM_EXCERPT_FRAMES


SCHEMA = "sunofriend.private-separation-candidate-followup-overlap-add-plan.v1"
STATUS = "planned_zero_eligible_global_overlap_add_fallback_no_model_run"
POLICY_ID = "strict-zero-eligible-review-global-overlap-add-fallback-v1"
REPORT_NAME = "private-separation-candidate-followup-overlap-add-plan.json"
TARGET_SAMPLE_RATE = 44_100
MINIMUM_OVERLAP_FRAMES = 2 * TARGET_SAMPLE_RATE
MAXIMUM_WINDOW_COUNT = 64
_CANDIDATE_ROLES = ("vocals", "instrumental")
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


def _plan_private_candidate_followup_overlap_add(
    variant_review_result_path: str | Path,
    *,
    reviewed_export_path: str | Path,
    variant_review_package_dir: str | Path,
    plan_path: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    variant_execution_dir: str | Path,
    stitch_package_dir: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Write one no-overwrite, model-free global overlap-add plan."""

    output = Path(out).expanduser().absolute()
    if output.name != REPORT_NAME:
        raise ValueError(f"private overlap-add plan filename must be {REPORT_NAME}")
    if os.path.lexists(output):
        raise FileExistsError(f"private overlap-add plan exists: {output}")
    if not output.parent.exists():
        output.parent.mkdir(parents=True, mode=0o700)
        output.parent.chmod(0o700)
    _require_private_directory(output.parent, "private overlap-add plan root")

    review_package = Path(variant_review_package_dir).expanduser().absolute()
    stitch_root = Path(stitch_package_dir).expanduser().absolute()
    _require_private_directory(review_package, "private variant review package")
    _require_private_directory(stitch_root, "private original stitch package")

    context = _load_verified_variant_inputs(
        plan_path,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
        variant_execution_dir=variant_execution_dir,
    )
    result = _verified_exact_variant_result(
        variant_review_result_path,
        reviewed_export_path=reviewed_export_path,
        variant_review_package_dir=review_package,
        plan_path=plan_path,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
        variant_execution_dir=variant_execution_dir,
    )
    known_variant_ids = [
        str(item["variant_id"])
        for item in context["plan"]["protocol"]["candidate_variants"]
    ]
    failed_variant_evidence = _validated_failed_variant_evidence(
        result, known_variant_ids=known_variant_ids
    )

    stitch_snapshot = _load_private_json_snapshot(
        stitch_root / STITCH_REPORT_NAME, "private original stitch report"
    )
    stitch = _load_stitch_report(stitch_snapshot["path"])
    _verify_stitch_audio(stitch_root, stitch)
    _verify_stitch_bound_to_v2(stitch_snapshot, inputs=context["inputs"])
    clock = _validated_clock(stitch["clock"])
    windows = _balanced_overlap_windows(
        total_frames=clock["frames"],
        window_frames=MAXIMUM_EXCERPT_FRAMES,
        minimum_overlap_frames=MINIMUM_OVERLAP_FRAMES,
    )
    original_targets = _original_audible_targets(context)

    result_snapshot = _load_private_json_snapshot(
        variant_review_result_path, "private follow-up variant review result"
    )
    reviewed_export = Path(reviewed_export_path).expanduser().absolute()
    _require_output_disjoint_from_inputs(
        output,
        evidence_roots=(
            context["base_root"],
            context["v2_root"],
            context["variant_root"],
            review_package,
            stitch_root,
        ),
        evidence_paths=(
            result_snapshot["path"],
            reviewed_export,
            context["plan_snapshot"]["path"],
            context["execution_snapshot"]["path"],
            context["candidates_snapshot"]["path"],
            context["inputs"]["execution_snapshot"]["path"],
            context["inputs"]["candidate_snapshot"]["path"],
            context["inputs"]["v2_snapshot"]["path"],
            stitch_snapshot["path"],
        ),
    )

    overlaps = [int(item["overlap_with_previous_frames"]) for item in windows[1:]]
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            **_input_bindings(context),
            "variant_review_result_sha256": result_snapshot["sha256"],
            "variant_review_result_document_sha256": result["document_sha256"],
            "variant_review_export_sha256": result["bindings"]["review_export_sha256"],
            "stitch_report_sha256": stitch_snapshot["sha256"],
            "stitch_document_sha256": stitch["document_sha256"],
        },
        "clock": deepcopy(clock),
        "failed_variant_evidence": failed_variant_evidence,
        "protocol": {
            "strategy": "independent_full_song_overlapping_windows",
            "source_window_frames": MAXIMUM_EXCERPT_FRAMES,
            "source_window_seconds": MAXIMUM_EXCERPT_FRAMES / TARGET_SAMPLE_RATE,
            "window_count": len(windows),
            "minimum_requested_overlap_frames": MINIMUM_OVERLAP_FRAMES,
            "minimum_requested_overlap_seconds": (
                MINIMUM_OVERLAP_FRAMES / TARGET_SAMPLE_RATE
            ),
            "actual_overlap_frames_minimum": min(overlaps),
            "actual_overlap_frames_maximum": max(overlaps),
            "actual_overlap_seconds_minimum": min(overlaps) / TARGET_SAMPLE_RATE,
            "actual_overlap_seconds_maximum": max(overlaps) / TARGET_SAMPLE_RATE,
            "window_placement": (
                "minimum-count whole-song coverage with evenly distributed "
                "integer starts and exact first/last source bounds"
            ),
            "worker_output_roles": list(_CANDIDATE_ROLES),
            "role_pairing": "both roles come from the same worker window",
            "blend_policy": "complementary-raised-cosine-constant-sum-v1",
            "blend_claim": (
                "overlap weights sum to one; this is not a quality or "
                "seamlessness claim"
            ),
            "reconstruction": "integer-sum written vocals plus instrumental",
            "post_hoc_role_patches": False,
            "automatic_preference_inference": False,
        },
        "windows": windows,
        "original_audible_role_boundaries": original_targets,
        "summary": {
            "failed_candidate_variant_count": len(known_variant_ids),
            "eligible_candidate_variant_count": 0,
            "planned_model_call_count": len(windows),
            "planned_model_calls_authorized": False,
            "planned_overlap_transition_count": len(windows) - 1,
            "original_audible_role_boundary_count": len(original_targets),
            "private_listener_notes_copied": False,
        },
        "required_future_review": {
            "compare_against_exact_first_followup_control": True,
            "all_original_audible_role_boundaries": True,
            "all_overlap_transitions": True,
            "complete_song_roles": ["vocals", "instrumental", "reconstruction"],
            "separate_absolute_questions": [
                "artifact_audible",
                "artifact_musically_acceptable",
                "candidate_useful_in_song_context",
                "difference_large_enough_to_matter",
            ],
            "fresh_all_original_boundaries_after_targeted_pass": True,
            "fresh_alignment_after_full_review": True,
        },
        "readiness": {
            "failed_variant_review_verified": True,
            "overlap_add_plan_complete": True,
            "overlap_add_execution_authorized": False,
            "overlap_add_execution_complete": False,
            "new_candidate_created": False,
            "new_candidate_review_complete": False,
            "new_candidate_alignment_complete": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "interpretation": {
            "strict_comparative_gate_not_met": True,
            "local_patch_strategy_proven_unusable": False,
            "neither_choice_means_audio_unusable": False,
            "contextual_musical_usefulness_remains_possible": True,
            "contextual_absolute_review_precedes_expensive_fallback": True,
            "overlap_add_is_accepted": False,
            "automatic_winner_selected": False,
            "separator_accepted": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_FALSE_EFFECTS),
        "limitations": [
            "This plan runs no model and creates no audio.",
            "The failed local variants remain immutable evidence and are not selected.",
            "A neither or equivalent comparison is not evidence that either sample is musically unusable.",
            "Short isolated transition judgements may differ from whole-song usefulness.",
            "Overlap-add changes the whole candidate, so every original boundary needs fresh listening.",
            "Constant-sum weighting controls gain geometry but does not prove clean joins or stem fidelity.",
            "Every planned worker window needs fresh audited execution and resource evidence.",
            "No product or publication route is enabled.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)

    rechecked_context = _load_verified_variant_inputs(
        plan_path,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
        variant_execution_dir=variant_execution_dir,
    )
    rechecked_result = _verified_exact_variant_result(
        variant_review_result_path,
        reviewed_export_path=reviewed_export_path,
        variant_review_package_dir=review_package,
        plan_path=plan_path,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
        variant_execution_dir=variant_execution_dir,
    )
    rechecked_stitch = _load_private_json_snapshot(
        stitch_root / STITCH_REPORT_NAME, "private original stitch report"
    )
    if (
        _input_bindings(rechecked_context) != _input_bindings(context)
        or rechecked_result != result
        or rechecked_stitch["sha256"] != stitch_snapshot["sha256"]
    ):
        raise ValueError("private overlap-add planning evidence changed")

    _write_json_exclusive(output, document)
    return {**document, "report": str(output)}


def _validated_clock(raw: Mapping[str, Any]) -> dict[str, Any]:
    clock = dict(raw)
    if (
        int(clock.get("sample_rate", 0)) != TARGET_SAMPLE_RATE
        or int(clock.get("channels", 0)) != 2
        or int(clock.get("frames", 0)) <= MAXIMUM_EXCERPT_FRAMES
    ):
        raise ValueError("private overlap-add source clock differs")
    return clock


def _balanced_overlap_windows(
    *,
    total_frames: int,
    window_frames: int,
    minimum_overlap_frames: int,
) -> list[dict[str, Any]]:
    """Cover a clock exactly with the fewest evenly spaced overlapping windows."""

    if (
        total_frames <= window_frames
        or window_frames <= 0
        or minimum_overlap_frames <= 0
        or minimum_overlap_frames >= window_frames
    ):
        raise ValueError("private overlap-add window geometry differs")
    maximum_hop = window_frames - minimum_overlap_frames
    span = total_frames - window_frames
    transition_count = (span + maximum_hop - 1) // maximum_hop
    window_count = transition_count + 1
    if window_count > MAXIMUM_WINDOW_COUNT:
        raise ValueError("private overlap-add window count exceeds bound")
    starts = [
        round(Fraction(index * span, transition_count)) for index in range(window_count)
    ]
    if starts[0] != 0 or starts[-1] + window_frames != total_frames:
        raise ValueError("private overlap-add endpoint coverage differs")
    if any(right <= left for left, right in zip(starts, starts[1:])):
        raise ValueError("private overlap-add window starts are not increasing")

    windows: list[dict[str, Any]] = []
    for index, start in enumerate(starts):
        end = start + window_frames
        previous_overlap = (
            0 if index == 0 else starts[index - 1] + window_frames - start
        )
        next_overlap = 0 if index == len(starts) - 1 else end - starts[index + 1]
        if index > 0 and previous_overlap < minimum_overlap_frames:
            raise ValueError("private overlap-add minimum overlap is not met")
        windows.append(
            {
                "window_index": index + 1,
                "source_start_frame": start,
                "source_end_frame": end,
                "source_start_seconds": start / TARGET_SAMPLE_RATE,
                "source_end_seconds": end / TARGET_SAMPLE_RATE,
                "overlap_with_previous_frames": previous_overlap,
                "overlap_with_next_frames": next_overlap,
                "status": "not_run",
            }
        )
    return windows


def _validated_failed_variant_evidence(
    result: Mapping[str, Any], *, known_variant_ids: Sequence[str]
) -> list[dict[str, Any]]:
    readiness = result.get("readiness_evidence")
    gate = result.get("candidate_gate_evidence")
    eligible = result.get("fresh_all_boundary_review_eligible_variant_ids")
    units = result.get("units")
    if (
        not known_variant_ids
        or len(set(known_variant_ids)) != len(known_variant_ids)
        or not isinstance(readiness, Mapping)
        or readiness.get("variant_review_complete") is not True
        or readiness.get("one_or_more_variants_eligible_for_fresh_all_boundary_review")
        is not False
        or eligible != []
        or not isinstance(gate, Mapping)
        or set(gate) != set(known_variant_ids)
        or not isinstance(units, list)
        or len(units) != int(result.get("reviewed_unit_count", -1))
        or any(unit.get("resolved_choice") == "cannot_tell" for unit in units)
    ):
        raise ValueError(
            "private failed variant review is not a complete zero-eligible gate"
        )

    summaries: list[dict[str, Any]] = []
    for variant_id in known_variant_ids:
        evidence = gate[variant_id]
        checks = (
            evidence.get("targeted_checks") if isinstance(evidence, Mapping) else None
        )
        if (
            not isinstance(checks, list)
            or evidence.get("eligible_for_fresh_all_boundary_review") is not False
            or evidence.get("selected") is not False
            or evidence.get("accepted") is not False
            or evidence.get("all_targeted_checks_pass") is not False
        ):
            raise ValueError("private failed variant gate evidence differs")
        failed_checks = [
            {
                "boundary_index": int(item["boundary_index"]),
                "role": str(item["role"]),
                "action": str(item["action"]),
                "boundary_gate_pass": bool(item["boundary_gate_pass"]),
                "edge_gate_pass": bool(item["edge_gate_pass"]),
                "failed_edges": list(item["failed_edges"]),
                "outcomes": dict(item["outcomes"]),
            }
            for item in checks
            if item.get("pass") is False
        ]
        if not failed_checks:
            raise ValueError("private ineligible variant has no failed targeted check")
        summaries.append(
            {
                "variant_id": variant_id,
                "eligible_for_fresh_all_boundary_review": False,
                "failed_targeted_checks": failed_checks,
                "complete_song_outcomes": dict(evidence["complete_song_outcomes"]),
                "all_complete_songs_candidate_or_equivalent": bool(
                    evidence["all_complete_songs_candidate_or_equivalent"]
                ),
                "selected": False,
                "accepted": False,
            }
        )
    return summaries


def _original_audible_targets(context: Mapping[str, Any]) -> list[dict[str, Any]]:
    patches = context["inputs"]["candidate"].get("patches")
    if not isinstance(patches, list) or len(patches) != 10:
        raise ValueError("private original audible role-boundary inventory differs")
    targets = [
        {
            "boundary_index": int(item["boundary_index"]),
            "role": str(item["role"]),
            "source_start_frame": int(item["patch_start_frame"]),
            "source_end_frame": int(item["patch_end_frame"]),
        }
        for item in patches
    ]
    if (
        any(item["role"] not in _CANDIDATE_ROLES for item in targets)
        or len({(item["boundary_index"], item["role"]) for item in targets})
        != len(targets)
        or any(
            item["source_end_frame"] <= item["source_start_frame"] for item in targets
        )
    ):
        raise ValueError("private original audible role-boundary targets differ")
    return sorted(targets, key=lambda item: (item["boundary_index"], item["role"]))


__all__: tuple[str, ...] = ()
