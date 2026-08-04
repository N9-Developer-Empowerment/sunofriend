"""Verify and resolve one candidate-bound full-song listening review.

This records fresh listener evidence for the exact v2 candidate package.  It
does not select or accept the candidate, resolve alignment, close the original
join gate or enable any product/publication route.
"""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_candidate_full_song_review import (
    REPORT_NAME as PACKAGE_REPORT_NAME,
    SCHEMA as PACKAGE_SCHEMA,
    STATUS as PACKAGE_STATUS,
    _LIMITATIONS as PACKAGE_LIMITATIONS,
    _PACKAGE_EFFECTS,
    _PACKAGE_INTERPRETATION,
    _PACKAGE_READINESS,
    _require_review_result_unchanged,
    _verified_original_boundary_evidence,
    _verify_completed_package,
    _verify_passing_v2_review_result,
)
from ._separation_full_song_executor import _require_private_directory
from ._separation_full_song_join_remediation_executor_v2 import (
    _FALSE_PERMISSIONS,
    _require_output_disjoint_from_inputs,
)
from ._separation_full_song_join_remediation_review_result import (
    _browser_json_equal,
    _load_private_json_snapshot,
    _write_json_exclusive,
)
from ._separation_full_song_join_remediation_review_v2 import (
    _load_review_inputs,
    _reverify_inputs,
)
from ._separation_full_song_review import (
    _validate_completed_review,
    _verify_review_audio,
)
from ._separation_full_song_stitch import (
    REVIEW_NAME,
    REVIEW_SCHEMA,
    _immutable_review,
)


STATUS_SCHEMA = "sunofriend.private-separation-candidate-full-song-review-status.v1"
RESULT_SCHEMA = "sunofriend.private-separation-candidate-full-song-review-result.v1"
RESULT_STATUS = "complete_review_no_activation"
_RATED_ROLES = ("vocals", "instrumental", "reconstruction")
_BOUNDARY_RATINGS = ("audible_join", "cannot_tell", "clean")
_RESULT_EFFECTS = {
    "candidate_accepted": False,
    "candidate_selected": False,
    "package_audio_mutated": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "review_record_created": True,
    "source_audio_mutated": False,
    "source_graph_mutated": False,
}


def _status_private_candidate_full_song_review(
    review_path: str | Path,
    **kwargs: Any,
) -> dict[str, Any]:
    """Verify one complete export and its exact package without writing."""

    context = _load_completed_candidate_review(review_path, **kwargs)
    review = context["review_snapshot"]["document"]
    status: dict[str, Any] = {
        "schema": STATUS_SCHEMA,
        "status": "complete_review_verified_no_activation",
        "evidence_scope": "private_development_only",
        "bindings": _result_bindings(context),
        "reviewed_boundaries": len(review["units"]),
        "full_song_reviewed": True,
        "rating_counts_by_role": _boundary_counts(review),
        "answer_key_required": False,
        "candidate_identity": "v2_expanded_context_join_remediation",
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": {
            **dict(_RESULT_EFFECTS),
            "review_record_created": False,
        },
    }
    status["document_sha256"] = _document_sha256(status)
    return status


def _resolve_private_candidate_full_song_review(
    review_path: str | Path,
    *,
    out: str | Path,
    **kwargs: Any,
) -> dict[str, Any]:
    """Write a no-overwrite, non-activating result for one complete review."""

    output = Path(out).expanduser().absolute()
    _require_private_directory(
        output.parent, "private candidate full-song review result parent"
    )
    if os.path.lexists(output):
        raise FileExistsError(
            f"private candidate full-song review result already exists: {output}"
        )
    context = _load_completed_candidate_review(review_path, **kwargs)
    _require_output_disjoint_from_inputs(
        output,
        evidence_roots=(
            context["package"],
            context["source_context"]["v1_root"],
            context["source_context"]["v2_root"],
            context["source_context"]["stitch_root"],
        ),
        evidence_paths=(
            context["review_snapshot"]["path"],
            context["seed_snapshot"]["path"],
            context["package_snapshot"]["path"],
            context["v2_result_snapshot"]["path"],
            context["source_context"]["v2_snapshot"]["path"],
            context["source_context"]["v2_plan_snapshot"]["path"],
            context["source_context"]["stitch_snapshot"]["path"],
            context["source_context"]["v1_execution_snapshot"]["path"],
            context["source_context"]["v1_candidate_snapshot"]["path"],
            *context["source_context"]["authority_paths"],
        ),
    )
    review = context["review_snapshot"]["document"]
    counts = _boundary_counts(review)
    audible = {
        role: [
            unit["boundary_index"]
            for unit in review["units"]
            if unit["ratings"][role] == "audible_join"
        ]
        for role in _RATED_ROLES
    }
    all_boundaries_clean = all(
        counts[role]["clean"] == len(review["units"]) for role in _RATED_ROLES
    )
    all_roles_useful = all(
        review["full_song"]["ratings"][role] == "useful"
        for role in _RATED_ROLES
    )
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "status": RESULT_STATUS,
        "evidence_scope": "private_development_only",
        "candidate_identity": "v2_expanded_context_join_remediation",
        "bindings": _result_bindings(context),
        "clock": deepcopy(context["package_report"]["clock"]),
        "full_song": {
            "heard_all": True,
            "ratings": deepcopy(review["full_song"]["ratings"]),
            "notes": review["full_song"]["notes"],
        },
        "boundary_summary": {
            "reviewed_boundaries": len(review["units"]),
            "rating_counts_by_role": counts,
            "audible_join_boundaries_by_role": audible,
            "all_candidate_boundaries_clean": all_boundaries_clean,
        },
        "boundaries": [
            {
                "boundary_index": unit["boundary_index"],
                "frame": unit["frame"],
                "seconds": unit["seconds"],
                "ratings": deepcopy(unit["ratings"]),
                "notes": unit["notes"],
            }
            for unit in review["units"]
        ],
        "readiness_evidence": {
            "targeted_v2_absolute_cleanliness_pass": True,
            "new_candidate_full_song_review_complete": True,
            "all_candidate_boundaries_clean": all_boundaries_clean,
            "all_candidate_full_song_roles_useful": all_roles_useful,
            "fresh_candidate_bound_alignment_review_eligible": True,
            "new_candidate_alignment_complete": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "interpretation": {
            "ratings_are_human_listening_evidence": True,
            "full_song_review_completion_is_candidate_acceptance": False,
            "clean_boundaries_are_separator_accuracy": False,
            "alignment_still_requires_fresh_review": True,
            "automatic_winner_selected": False,
            "separator_accepted": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_RESULT_EFFECTS),
    }
    result["document_sha256"] = _document_sha256(result)
    published = False
    try:
        _write_json_exclusive(output, result)
        published = True
        _reverify_completed_candidate_review(context)
    except BaseException:
        if published:
            try:
                output.unlink()
            except FileNotFoundError:
                pass
        raise
    return {**result, "report": str(output)}


def _load_completed_candidate_review(
    review_path: str | Path,
    *,
    review_package_dir: str | Path,
    v2_review_result_path: str | Path,
    v2_execution_dir: str | Path,
    v2_plan_path: str | Path,
    v1_execution_dir: str | Path,
    stitch_package_dir: str | Path,
    full_song_review_result_path: str | Path,
    v1_plan_path: str | Path,
    resolved_join_review_result_path: str | Path,
    publication_readiness_path: str | Path,
) -> dict[str, Any]:
    import soundfile

    package = Path(review_package_dir).expanduser().absolute()
    _require_private_directory(package, "private candidate full-song review package")
    source_context = _load_review_inputs(
        v2_execution_dir,
        v2_plan_path=v2_plan_path,
        v1_execution_dir=v1_execution_dir,
        stitch_package_dir=stitch_package_dir,
        full_song_review_result_path=full_song_review_result_path,
        v1_plan_path=v1_plan_path,
        resolved_join_review_result_path=resolved_join_review_result_path,
        publication_readiness_path=publication_readiness_path,
    )
    v2_result_snapshot = _load_private_json_snapshot(
        v2_review_result_path, "private resolved v2 join review result"
    )
    _verify_passing_v2_review_result(v2_result_snapshot, context=source_context)

    package_snapshot = _load_private_json_snapshot(
        package / PACKAGE_REPORT_NAME,
        "private candidate full-song review package report",
    )
    package_report = package_snapshot["document"]
    _verify_package_report(
        package,
        package_report,
        package_sha256=package_snapshot["sha256"],
        source_context=source_context,
        v2_result_snapshot=v2_result_snapshot,
        soundfile=soundfile,
    )

    seed_snapshot = _load_private_json_snapshot(
        package / "BOUNDARY-REVIEW" / REVIEW_NAME,
        "private candidate full-song review seed",
    )
    seed = seed_snapshot["document"]
    if (
        seed.get("schema") != REVIEW_SCHEMA
        or seed.get("status") != "unreviewed"
        or seed_snapshot["sha256"]
        != package_report["boundary_review"]["seed_sha256"]
        or seed.get("package_commitment")
        != package_report["boundary_review"]["package_commitment"]
    ):
        raise ValueError("private candidate full-song review seed differs")

    review_snapshot = _load_private_json_snapshot(
        review_path, "reviewed candidate full-song export"
    )
    review = review_snapshot["document"]
    if not _browser_json_equal(_immutable_review(review), _immutable_review(seed)):
        raise ValueError(
            "private candidate full-song review export changed immutable evidence"
        )
    _validate_completed_review(
        review, boundary_count=int(package_report["clock"]["boundary_count"])
    )
    _verify_review_audio(package, review)

    context = {
        "package": package,
        "package_snapshot": package_snapshot,
        "package_report": package_report,
        "seed_snapshot": seed_snapshot,
        "seed": seed,
        "review_snapshot": review_snapshot,
        "v2_result_snapshot": v2_result_snapshot,
        "source_context": source_context,
    }
    _reverify_completed_candidate_review(context)
    return context


def _verify_package_report(
    package: Path,
    report: Mapping[str, Any],
    *,
    package_sha256: str,
    source_context: Mapping[str, Any],
    v2_result_snapshot: Mapping[str, Any],
    soundfile: Any,
) -> None:
    expected_bindings = {
        "v2_review_result_sha256": v2_result_snapshot["sha256"],
        "v2_review_result_document_sha256": v2_result_snapshot["document"][
            "document_sha256"
        ],
        "v2_execution_report_sha256": source_context["v2_snapshot"]["sha256"],
        "v2_execution_document_sha256": source_context["v2_report"][
            "document_sha256"
        ],
        "stitch_report_sha256": source_context["stitch_snapshot"]["sha256"],
        "stitch_document_sha256": source_context["stitch"]["document_sha256"],
        "targeted_review_package_commitment": v2_result_snapshot["document"][
            "package_commitment"
        ],
    }
    if (
        report.get("schema") != PACKAGE_SCHEMA
        or report.get("status") != PACKAGE_STATUS
        or report.get("evidence_scope") != "private_development_only"
        or report.get("candidate_identity")
        != "v2_expanded_context_join_remediation"
        or report.get("document_sha256") != _document_sha256(report)
        or report.get("bindings") != expected_bindings
        or report.get("permissions") != _FALSE_PERMISSIONS
        or report.get("effects") != _PACKAGE_EFFECTS
        or report.get("readiness") != _PACKAGE_READINESS
        or report.get("interpretation") != _PACKAGE_INTERPRETATION
        or report.get("limitations") != PACKAGE_LIMITATIONS
        or report.get("clock") != source_context["stitch"]["clock"]
        or package_sha256 != _sha256(package / PACKAGE_REPORT_NAME)
    ):
        raise ValueError("private candidate full-song review package differs")
    boundary_evidence = _verified_original_boundary_evidence(source_context)
    if report.get("clock", {}).get("boundary_count") != len(
        boundary_evidence["boundaries"]
    ):
        raise ValueError("private candidate full-song review boundary count differs")
    _verify_completed_package(package, report, soundfile=soundfile)


def _reverify_completed_candidate_review(context: Mapping[str, Any]) -> None:
    import soundfile

    _require_review_result_unchanged(context["v2_result_snapshot"])
    _reverify_inputs(context["source_context"])
    current_package = _load_private_json_snapshot(
        context["package_snapshot"]["path"],
        "private candidate full-song review package report",
    )
    if (
        current_package["sha256"] != context["package_snapshot"]["sha256"]
        or current_package["document"] != context["package_report"]
    ):
        raise ValueError("private candidate full-song review package changed")
    _verify_package_report(
        context["package"],
        context["package_report"],
        package_sha256=context["package_snapshot"]["sha256"],
        source_context=context["source_context"],
        v2_result_snapshot=context["v2_result_snapshot"],
        soundfile=soundfile,
    )
    for snapshot, label in (
        (context["seed_snapshot"], "private candidate full-song review seed"),
        (context["review_snapshot"], "reviewed candidate full-song export"),
    ):
        current = _load_private_json_snapshot(snapshot["path"], label)
        if (
            current["sha256"] != snapshot["sha256"]
            or current["document"] != snapshot["document"]
        ):
            raise ValueError(f"{label} changed")


def _boundary_counts(review: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    return {
        role: {
            rating: sum(
                unit["ratings"][role] == rating for unit in review["units"]
            )
            for rating in _BOUNDARY_RATINGS
        }
        for role in _RATED_ROLES
    }


def _result_bindings(context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_review_package_report_sha256": context["package_snapshot"][
            "sha256"
        ],
        "candidate_review_package_document_sha256": context["package_report"][
            "document_sha256"
        ],
        "candidate_review_seed_sha256": context["seed_snapshot"]["sha256"],
        "candidate_review_export_sha256": context["review_snapshot"]["sha256"],
        "candidate_review_package_commitment": context["seed"][
            "package_commitment"
        ],
        "v2_review_result_sha256": context["v2_result_snapshot"]["sha256"],
        "v2_review_result_document_sha256": context["v2_result_snapshot"][
            "document"
        ]["document_sha256"],
        "v2_execution_report_sha256": context["source_context"]["v2_snapshot"][
            "sha256"
        ],
        "v2_execution_document_sha256": context["source_context"]["v2_report"][
            "document_sha256"
        ],
    }


__all__: tuple[str, ...] = ()
