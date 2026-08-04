"""Plan bounded re-inference around human-rated full-song chunk joins.

The raw stitch remains immutable evidence.  This contract turns only explicit
``audible_join`` ratings into a small set of source-clock windows that a later
private executor may re-infer.  It writes no audio, runs no model and cannot
change publication readiness.
"""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_full_song_alignment import (
    SCHEMA as ALIGNMENT_SCHEMA,
    STATUS as ALIGNMENT_STATUS,
)
from ._separation_full_song_executor import _require_private_regular
from ._separation_full_song_review import (
    SCHEMA as REVIEW_RESULT_SCHEMA,
    STATUS as REVIEW_RESULT_STATUS,
    _load_json,
    _load_stitch_report,
    _verify_stitch_audio,
    _write_json_atomic,
)
from ._separation_full_song_stitch import (
    REPORT_NAME as STITCH_REPORT_NAME,
    REVIEW_NAME,
    REVIEW_SCHEMA,
    _FALSE_PERMISSIONS,
)
from ._separation_melroformer_real_bridge import MAXIMUM_EXCERPT_FRAMES


SCHEMA = "sunofriend.private-separation-full-song-join-remediation-plan.v1"
STATUS = "planned_targeted_overlap_reinference_no_model_run"
POLICY_ID = "human-audible-join-centered-single-window-reinference-v1"
REPORT_NAME = "private-separation-full-song-join-remediation-plan.json"

TARGET_SAMPLE_RATE = 44_100
PATCH_HALF_FRAMES = TARGET_SAMPLE_RATE
EDGE_BLEND_FRAMES = TARGET_SAMPLE_RATE // 10
_REPAIRABLE_ROLES = ("vocals", "instrumental")
_RATED_ROLES = (*_REPAIRABLE_ROLES, "reconstruction")
_FALSE_EFFECTS = {
    "alignment_evidence_mutated": False,
    "audio_created_or_mutated": False,
    "model_run": False,
    "publication_state_mutated": False,
    "raw_stitch_mutated": False,
    "review_evidence_mutated": False,
    "separator_accepted": False,
    "separator_selected": False,
    "source_graph_mutated": False,
}


def _plan_private_separation_full_song_join_remediation(
    package_dir: str | Path,
    review_result_path: str | Path,
    alignment_result_path: str | Path,
    *,
    out: str | Path,
) -> dict[str, Any]:
    """Write a path-free plan for targeted, separately reviewed candidates."""

    package = Path(package_dir).expanduser().absolute()
    stitch_path = package / STITCH_REPORT_NAME
    stitch = _load_stitch_report(stitch_path)
    _verify_stitch_audio(package, stitch)

    review_path = Path(review_result_path).expanduser().absolute()
    alignment_path = Path(alignment_result_path).expanduser().absolute()
    _require_private_regular(review_path, "private full-song review result")
    _require_private_regular(alignment_path, "private full-song alignment result")
    review = _load_json(review_path, "private full-song review result")
    alignment = _load_json(alignment_path, "private full-song alignment result")
    review_seed_path = package / "BOUNDARY-REVIEW" / REVIEW_NAME
    review_seed = _load_json(review_seed_path, "private full-song review seed")

    output = Path(out).expanduser().absolute()
    if os.path.lexists(output):
        raise FileExistsError(f"private join-remediation plan exists: {output}")

    _verify_review_result(
        review,
        review_path=review_path,
        review_seed=review_seed,
        review_seed_path=review_seed_path,
        stitch=stitch,
        stitch_path=stitch_path,
    )
    _verify_alignment_result(
        alignment,
        alignment_path=alignment_path,
        stitch=stitch,
        stitch_path=stitch_path,
    )

    clock = stitch["clock"]
    sample_rate = int(clock["sample_rate"])
    total_frames = int(clock["frames"])
    if sample_rate != TARGET_SAMPLE_RATE:
        raise ValueError("private join-remediation source clock differs")
    if total_frames < MAXIMUM_EXCERPT_FRAMES:
        raise ValueError("private join-remediation song is shorter than one worker window")

    target_roles_by_boundary = _target_roles_by_boundary(review)
    if not target_roles_by_boundary:
        raise ValueError("private full-song review has no audible role join to remediate")
    if _audible_boundaries(review, "reconstruction"):
        raise ValueError(
            "audible reconstruction joins require diagnosis before role remediation"
        )

    boundary_rows = {
        int(row["boundary_index"]): row for row in review["boundaries"]
    }
    windows = [
        _window_plan(
            boundary_rows[index],
            target_roles=roles,
            total_frames=total_frames,
            window_index=window_index,
        )
        for window_index, (index, roles) in enumerate(
            sorted(target_roles_by_boundary.items()),
            start=1,
        )
    ]
    _require_disjoint_patch_regions(windows)
    target_pair_count = sum(len(window["patch_target_roles"]) for window in windows)

    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "stitch_report_sha256": _sha256(stitch_path),
            "stitch_document_sha256": stitch["document_sha256"],
            "review_result_sha256": _sha256(review_path),
            "review_document_sha256": review["document_sha256"],
            "review_seed_sha256": _sha256(review_seed_path),
            "alignment_result_sha256": _sha256(alignment_path),
            "alignment_document_sha256": alignment["document_sha256"],
            "source_audio_sha256": stitch["artifacts"]["source"]["sha256"],
            "raw_vocals_audio_sha256": stitch["artifacts"]["vocals"]["sha256"],
            "raw_instrumental_audio_sha256": stitch["artifacts"]["instrumental"][
                "sha256"
            ],
            "raw_reconstruction_audio_sha256": stitch["artifacts"][
                "reconstruction"
            ]["sha256"],
            "plan_document_sha256": stitch["bindings"]["plan_document_sha256"],
            "execution_state_sha256": stitch["bindings"]["execution_state_sha256"],
        },
        "clock": deepcopy(clock),
        "protocol": {
            "source_window_frames": MAXIMUM_EXCERPT_FRAMES,
            "source_window_seconds": MAXIMUM_EXCERPT_FRAMES / sample_rate,
            "patch_half_frames": PATCH_HALF_FRAMES,
            "patch_duration_frames": 2 * PATCH_HALF_FRAMES,
            "patch_duration_seconds": 2 * PATCH_HALF_FRAMES / sample_rate,
            "edge_blend_frames": EDGE_BLEND_FRAMES,
            "edge_blend_seconds": EDGE_BLEND_FRAMES / sample_rate,
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
        },
        "windows": windows,
        "summary": {
            "human_rated_audible_role_join_count": target_pair_count,
            "unique_boundary_count": len(windows),
            "planned_model_call_count": len(windows),
            "target_roles": [
                role
                for role in _REPAIRABLE_ROLES
                if any(role in window["patch_target_roles"] for window in windows)
            ],
            "private_listener_notes_copied": False,
            "raw_control_count": 1,
            "repaired_candidate_count": 0,
        },
        "required_future_review": {
            "blind_original_versus_repaired_boundary_role_pairs": target_pair_count,
            "repaired_patch_edge_role_checks": 2 * target_pair_count,
            "complete_song_roles": list(_RATED_ROLES),
            "automatic_preference_inference": False,
            "review_result_required_before_readiness_reassessment": True,
        },
        "readiness": {
            "source_clock_alignment_verified": True,
            "human_audible_join_targets_verified": True,
            "targeted_remediation_plan_ready": True,
            "remediation_worker_runs_complete": False,
            "repaired_candidates_created": False,
            "repaired_candidate_review_complete": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "interpretation": {
            "audible_join_rating_is_repair_success": False,
            "planned_reinference_is_separator_acceptance": False,
            "alignment_pass_is_stem_quality": False,
            "automatic_winner_selected": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_FALSE_EFFECTS),
        "limitations": [
            "This plan creates no audio and runs no model.",
            "The original raw stitch and completed human review remain immutable evidence.",
            "A later candidate can introduce new artefacts at either patch edge and must be reviewed.",
            "The plan does not close quality, full-song, licensing, offline, resource or product gates.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)
    _write_json_atomic(output, document)
    return {**document, "report": str(output)}


def _verify_review_result(
    review: Mapping[str, Any],
    *,
    review_path: Path,
    review_seed: Mapping[str, Any],
    review_seed_path: Path,
    stitch: Mapping[str, Any],
    stitch_path: Path,
) -> None:
    bindings = review.get("bindings")
    summary = review.get("boundary_summary")
    boundaries = review.get("boundaries")
    readiness = review.get("readiness")
    if (
        review.get("schema") != REVIEW_RESULT_SCHEMA
        or review.get("status") != REVIEW_RESULT_STATUS
        or review.get("evidence_scope") != "private_development_only"
        or review.get("document_sha256") != _document_sha256(review)
        or review.get("permissions") != _FALSE_PERMISSIONS
        or not _all_false(review.get("effects"))
        or not isinstance(bindings, Mapping)
        or bindings.get("stitch_report_sha256") != _sha256(stitch_path)
        or bindings.get("stitch_document_sha256") != stitch["document_sha256"]
        or bindings.get("review_seed_sha256") != _sha256(review_seed_path)
        or bindings.get("package_commitment")
        != review_seed.get("package_commitment")
        or bindings.get("plan_document_sha256")
        != stitch["bindings"]["plan_document_sha256"]
        or bindings.get("execution_state_sha256")
        != stitch["bindings"]["execution_state_sha256"]
        or review.get("clock") != stitch["clock"]
        or not isinstance(summary, Mapping)
        or not isinstance(boundaries, list)
        or not isinstance(readiness, Mapping)
        or readiness.get("exact_duration_and_frame_count_verified") is not True
        or readiness.get("full_song_and_boundary_listening_complete") is not True
        or len(boundaries) != stitch["clock"]["boundary_count"]
    ):
        raise ValueError("private full-song review result differs")
    _require_private_regular(review_path, "private full-song review result")

    boundary_claim = stitch["boundary_review"]
    if (
        review_seed.get("schema") != REVIEW_SCHEMA
        or review_seed.get("status") != "unreviewed"
        or review_seed.get("evidence_scope") != "private_development_only"
        or _sha256(review_seed_path) != boundary_claim.get("seed_sha256")
        or review_seed.get("package_commitment")
        != boundary_claim.get("package_commitment")
        or review_seed.get("permissions") != _FALSE_PERMISSIONS
    ):
        raise ValueError("private full-song review boundary seed differs")

    seed_units = review_seed.get("units")
    if not isinstance(seed_units, list) or len(seed_units) != len(boundaries):
        raise ValueError("private full-song review boundary seed differs")
    audible = {role: [] for role in _RATED_ROLES}
    counts = {
        role: {"audible_join": 0, "cannot_tell": 0, "clean": 0}
        for role in _RATED_ROLES
    }
    for index, (row, seed) in enumerate(zip(boundaries, seed_units), start=1):
        ratings = row.get("ratings") if isinstance(row, Mapping) else None
        if (
            not isinstance(row, Mapping)
            or not isinstance(seed, Mapping)
            or row.get("boundary_index") != index
            or row.get("boundary_index") != seed.get("boundary_index")
            or row.get("frame") != seed.get("frame")
            or row.get("seconds") != seed.get("seconds")
            or not isinstance(ratings, Mapping)
            or set(ratings) != set(_RATED_ROLES)
            or any(value not in {"clean", "audible_join"} for value in ratings.values())
        ):
            raise ValueError("private full-song reviewed boundary evidence differs")
        for role in _RATED_ROLES:
            counts[role][ratings[role]] += 1
            if ratings[role] == "audible_join":
                audible[role].append(index)
    if (
        summary.get("reviewed_boundaries") != len(boundaries)
        or summary.get("audible_join_boundaries_by_role") != audible
        or summary.get("rating_counts_by_role") != counts
    ):
        raise ValueError("private full-song audible-join summary differs")


def _verify_alignment_result(
    alignment: Mapping[str, Any],
    *,
    alignment_path: Path,
    stitch: Mapping[str, Any],
    stitch_path: Path,
) -> None:
    bindings = alignment.get("bindings")
    readiness = alignment.get("readiness")
    if (
        alignment.get("schema") != ALIGNMENT_SCHEMA
        or alignment.get("status") != ALIGNMENT_STATUS
        or alignment.get("evidence_scope") != "private_development_only"
        or alignment.get("document_sha256") != _document_sha256(alignment)
        or alignment.get("permissions") != _FALSE_PERMISSIONS
        or not _all_false(alignment.get("effects"))
        or alignment.get("clock") != stitch["clock"]
        or not isinstance(bindings, Mapping)
        or bindings.get("stitch_report_sha256") != _sha256(stitch_path)
        or bindings.get("stitch_document_sha256") != stitch["document_sha256"]
        or bindings.get("source_audio_sha256")
        != stitch["artifacts"]["source"]["sha256"]
        or bindings.get("reconstruction_audio_sha256")
        != stitch["artifacts"]["reconstruction"]["sha256"]
        or bindings.get("plan_document_sha256")
        != stitch["bindings"]["plan_document_sha256"]
        or bindings.get("execution_state_sha256")
        != stitch["bindings"]["execution_state_sha256"]
        or not isinstance(readiness, Mapping)
        or readiness.get("alignment_gate_passed") is not True
        or readiness.get("source_to_reconstruction_alignment_verified") is not True
        or readiness.get("drift_acceptance_complete") is not True
    ):
        raise ValueError("private full-song alignment result differs or did not pass")
    _require_private_regular(alignment_path, "private full-song alignment result")


def _target_roles_by_boundary(review: Mapping[str, Any]) -> dict[int, list[str]]:
    result: dict[int, list[str]] = {}
    for role in _REPAIRABLE_ROLES:
        for boundary in _audible_boundaries(review, role):
            result.setdefault(boundary, []).append(role)
    return result


def _audible_boundaries(review: Mapping[str, Any], role: str) -> list[int]:
    value = review["boundary_summary"]["audible_join_boundaries_by_role"][role]
    return [int(item) for item in value]


def _window_plan(
    boundary: Mapping[str, Any],
    *,
    target_roles: list[str],
    total_frames: int,
    window_index: int,
) -> dict[str, Any]:
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
        raise ValueError("audible join cannot fit the bounded remediation geometry")
    return {
        "window_index": window_index,
        "boundary_index": int(boundary["boundary_index"]),
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
        "patch_target_roles": [
            role for role in _REPAIRABLE_ROLES if role in target_roles
        ],
        "worker_output_roles": list(_REPAIRABLE_ROLES),
        "worker_status": "not_run",
        "candidate_status": "not_created",
    }


def _require_disjoint_patch_regions(windows: list[Mapping[str, Any]]) -> None:
    for left, right in zip(windows, windows[1:]):
        if int(left["patch_end_frame"]) > int(right["patch_start_frame"]):
            raise ValueError("private join-remediation patch regions overlap")


def _all_false(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and bool(value)
        and all(item is False for item in value.values())
    )


__all__: tuple[str, ...] = ()
