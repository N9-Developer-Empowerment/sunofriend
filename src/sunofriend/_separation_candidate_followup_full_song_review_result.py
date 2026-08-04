"""Verify and resolve a follow-up candidate full-song boundary review.

The result records the listener's exact complete-song and all-boundary ratings
without selecting, accepting or publishing the candidate.  Every source
binding and the preceding targeted review pass are re-verified first.
"""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256
from ._separation_candidate_followup_full_song_review import (
    REPORT_NAME as PACKAGE_REPORT_NAME,
    SCHEMA as PACKAGE_SCHEMA,
    STATUS as PACKAGE_STATUS,
    _LIMITATIONS as PACKAGE_LIMITATIONS,
    _PACKAGE_EFFECTS,
    _PACKAGE_INTERPRETATION,
    _PACKAGE_READINESS,
    _verified_passing_targeted_result,
    _verify_completed_package,
    _verify_stitch_bound_to_v2,
)
from ._separation_candidate_full_song_review import (
    _verified_original_boundary_evidence,
)
from ._separation_candidate_join_remediation_review import _load_verified_inputs
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
from ._separation_full_song_review import (
    _load_stitch_report,
    _validate_completed_review,
    _verify_review_audio,
    _verify_stitch_audio,
)
from ._separation_full_song_stitch import (
    REPORT_NAME as STITCH_REPORT_NAME,
    REVIEW_NAME,
    REVIEW_SCHEMA,
    _immutable_review,
)


STATUS_SCHEMA = (
    "sunofriend.private-separation-candidate-followup-full-song-review-status.v1"
)
RESULT_SCHEMA = (
    "sunofriend.private-separation-candidate-followup-full-song-review-result.v1"
)
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


def _status_private_candidate_followup_full_song_review(
    review_path: str | Path, **kwargs: Any
) -> dict[str, Any]:
    """Verify a completed export without writing a result."""

    context = _load_completed_review(review_path, **kwargs)
    review = context["review_snapshot"]["document"]
    status: dict[str, Any] = {
        "schema": STATUS_SCHEMA,
        "status": "complete_review_verified_no_activation",
        "evidence_scope": "private_development_only",
        "bindings": _result_bindings(context),
        "reviewed_boundaries": len(review["units"]),
        "full_song_reviewed": True,
        "rating_counts_by_role": _boundary_counts(review),
        "candidate_identity": "review_derived_followup_join_remediation",
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": {**dict(_RESULT_EFFECTS), "review_record_created": False},
    }
    status["document_sha256"] = _document_sha256(status)
    return status


def _resolve_private_candidate_followup_full_song_review(
    review_path: str | Path, *, out: str | Path, **kwargs: Any
) -> dict[str, Any]:
    """Write a no-overwrite, non-activating full-song review result."""

    output = Path(out).expanduser().absolute()
    _require_private_directory(
        output.parent, "private follow-up full-song review result parent"
    )
    if os.path.lexists(output):
        raise FileExistsError(
            f"private follow-up full-song review result already exists: {output}"
        )
    context = _load_completed_review(review_path, **kwargs)
    _require_output_disjoint_from_inputs(
        output,
        evidence_roots=(
            context["package"],
            context["execution"],
            context["v2_execution"],
            context["targeted_package"],
            context["stitch_root"],
        ),
        evidence_paths=(
            context["review_snapshot"]["path"],
            context["seed_snapshot"]["path"],
            context["package_snapshot"]["path"],
            context["targeted_result_snapshot"]["path"],
            context["inputs"]["execution_snapshot"]["path"],
            context["inputs"]["candidate_snapshot"]["path"],
            context["inputs"]["v2_snapshot"]["path"],
            context["stitch_snapshot"]["path"],
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
        "candidate_identity": "review_derived_followup_join_remediation",
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
            "all_followup_boundaries_clean": all_boundaries_clean,
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
            "targeted_followup_listening_pass": True,
            "followup_complete_song_review_complete": True,
            "all_followup_boundaries_clean": all_boundaries_clean,
            "all_followup_full_song_roles_useful": all_roles_useful,
            "fresh_followup_alignment_review_eligible": True,
            "followup_alignment_complete": False,
            "original_audible_joins_resolved": False,
            "publication_ready": False,
        },
        "interpretation": {
            "ratings_are_human_listening_evidence": True,
            "review_completion_is_candidate_acceptance": False,
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
        _reverify_completed_review(context)
    except BaseException:
        if published:
            try:
                output.unlink()
            except FileNotFoundError:
                pass
        raise
    return {**result, "report": str(output)}


def _load_completed_review(
    review_path: str | Path,
    *,
    review_package_dir: str | Path,
    targeted_review_result_path: str | Path,
    targeted_reviewed_export_path: str | Path,
    targeted_review_package_dir: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    stitch_package_dir: str | Path,
) -> dict[str, Any]:
    import soundfile

    package = Path(review_package_dir).expanduser().absolute()
    targeted_package = Path(targeted_review_package_dir).expanduser().absolute()
    execution = Path(execution_dir).expanduser().absolute()
    v2_execution = Path(v2_execution_dir).expanduser().absolute()
    stitch_root = Path(stitch_package_dir).expanduser().absolute()
    for path, label in (
        (package, "private follow-up full-song review package"),
        (targeted_package, "private targeted follow-up review package"),
        (execution, "private follow-up execution root"),
        (v2_execution, "private v2 execution root"),
        (stitch_root, "private original stitch root"),
    ):
        _require_private_directory(path, label)
    inputs = _load_verified_inputs(execution, v2_execution)
    targeted_result = _verified_passing_targeted_result(
        targeted_review_result_path,
        reviewed_export_path=targeted_reviewed_export_path,
        targeted_review_package_dir=targeted_package,
        execution_dir=execution,
        v2_execution_dir=v2_execution,
    )
    targeted_result_snapshot = _load_private_json_snapshot(
        targeted_review_result_path, "private targeted follow-up review result"
    )
    stitch_snapshot = _load_private_json_snapshot(
        stitch_root / STITCH_REPORT_NAME, "private original stitch report"
    )
    stitch = _load_stitch_report(stitch_snapshot["path"])
    _verify_stitch_audio(stitch_root, stitch)
    _verify_stitch_bound_to_v2(stitch_snapshot, inputs=inputs)

    package_snapshot = _load_private_json_snapshot(
        package / PACKAGE_REPORT_NAME,
        "private follow-up full-song review package report",
    )
    package_report = package_snapshot["document"]
    source = {
        "inputs": inputs,
        "targeted_result": targeted_result,
        "targeted_result_snapshot": targeted_result_snapshot,
        "stitch": stitch,
        "stitch_snapshot": stitch_snapshot,
        "stitch_root": stitch_root,
    }
    _verify_package_report(package, package_report, source=source, soundfile=soundfile)

    seed_snapshot = _load_private_json_snapshot(
        package / "BOUNDARY-REVIEW" / REVIEW_NAME,
        "private follow-up full-song review seed",
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
        raise ValueError("private follow-up full-song review seed differs")
    review_snapshot = _load_private_json_snapshot(
        review_path, "reviewed follow-up full-song export"
    )
    review = review_snapshot["document"]
    if not _browser_json_equal(_immutable_review(review), _immutable_review(seed)):
        raise ValueError(
            "private follow-up full-song review export changed immutable evidence"
        )
    _validate_completed_review(
        review, boundary_count=int(package_report["clock"]["boundary_count"])
    )
    _verify_review_audio(package, review)
    context = {
        "package": package,
        "targeted_package": targeted_package,
        "execution": execution,
        "v2_execution": v2_execution,
        "stitch_root": stitch_root,
        "package_snapshot": package_snapshot,
        "package_report": package_report,
        "seed_snapshot": seed_snapshot,
        "seed": seed,
        "review_snapshot": review_snapshot,
        **source,
    }
    _reverify_completed_review(context)
    return context


def _verify_package_report(
    package: Path,
    report: Mapping[str, Any],
    *,
    source: Mapping[str, Any],
    soundfile: Any,
) -> None:
    inputs = source["inputs"]
    targeted = source["targeted_result"]
    targeted_snapshot = source["targeted_result_snapshot"]
    stitch = source["stitch"]
    stitch_snapshot = source["stitch_snapshot"]
    expected_bindings = {
        "targeted_review_result_sha256": targeted_snapshot["sha256"],
        "targeted_review_result_document_sha256": targeted["document_sha256"],
        "targeted_review_export_sha256": targeted["bindings"][
            "review_export_sha256"
        ],
        "followup_execution_report_sha256": inputs["execution_snapshot"]["sha256"],
        "followup_execution_document_sha256": inputs["execution"]["document_sha256"],
        "followup_candidate_report_sha256": inputs["candidate_snapshot"]["sha256"],
        "followup_candidate_document_sha256": inputs["candidate"]["document_sha256"],
        "v2_execution_report_sha256": inputs["v2_snapshot"]["sha256"],
        "v2_execution_document_sha256": inputs["v2"]["document_sha256"],
        "stitch_report_sha256": stitch_snapshot["sha256"],
        "stitch_document_sha256": stitch["document_sha256"],
    }
    if (
        report.get("schema") != PACKAGE_SCHEMA
        or report.get("status") != PACKAGE_STATUS
        or report.get("evidence_scope") != "private_development_only"
        or report.get("candidate_identity")
        != "review_derived_followup_join_remediation"
        or report.get("document_sha256") != _document_sha256(report)
        or report.get("bindings") != expected_bindings
        or report.get("permissions") != _FALSE_PERMISSIONS
        or report.get("effects") != _PACKAGE_EFFECTS
        or report.get("readiness") != _PACKAGE_READINESS
        or report.get("interpretation") != _PACKAGE_INTERPRETATION
        or report.get("limitations") != PACKAGE_LIMITATIONS
        or report.get("clock") != stitch["clock"]
    ):
        raise ValueError("private follow-up full-song review package differs")
    boundary_evidence = _verified_original_boundary_evidence(
        {"stitch": stitch, "stitch_root": source["stitch_root"]}
    )
    if report["clock"]["boundary_count"] != len(boundary_evidence["boundaries"]):
        raise ValueError("private follow-up full-song boundary count differs")
    _verify_completed_package(package, report, soundfile=soundfile)


def _reverify_completed_review(context: Mapping[str, Any]) -> None:
    import soundfile

    for snapshot, label in (
        (context["targeted_result_snapshot"], "private targeted follow-up review result"),
        (context["inputs"]["execution_snapshot"], "private follow-up execution"),
        (context["inputs"]["candidate_snapshot"], "private follow-up candidate"),
        (context["inputs"]["v2_snapshot"], "private v2 execution"),
        (context["stitch_snapshot"], "private original stitch report"),
        (context["package_snapshot"], "private follow-up full-song review package"),
        (context["seed_snapshot"], "private follow-up full-song review seed"),
        (context["review_snapshot"], "reviewed follow-up full-song export"),
    ):
        current = _load_private_json_snapshot(snapshot["path"], label)
        if current["sha256"] != snapshot["sha256"] or current["document"] != snapshot["document"]:
            raise ValueError(f"{label} changed")
    _verify_stitch_audio(context["stitch_root"], context["stitch"])
    _verify_stitch_bound_to_v2(context["stitch_snapshot"], inputs=context["inputs"])
    _verify_package_report(
        context["package"],
        context["package_report"],
        source=context,
        soundfile=soundfile,
    )


def _boundary_counts(review: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    return {
        role: {
            rating: sum(unit["ratings"][role] == rating for unit in review["units"])
            for rating in _BOUNDARY_RATINGS
        }
        for role in _RATED_ROLES
    }


def _result_bindings(context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "followup_review_package_report_sha256": context["package_snapshot"][
            "sha256"
        ],
        "followup_review_package_document_sha256": context["package_report"][
            "document_sha256"
        ],
        "followup_review_seed_sha256": context["seed_snapshot"]["sha256"],
        "followup_review_export_sha256": context["review_snapshot"]["sha256"],
        "followup_review_package_commitment": context["seed"]["package_commitment"],
        "targeted_review_result_sha256": context["targeted_result_snapshot"][
            "sha256"
        ],
        "targeted_review_result_document_sha256": context["targeted_result"][
            "document_sha256"
        ],
        "followup_execution_report_sha256": context["inputs"]["execution_snapshot"][
            "sha256"
        ],
        "followup_candidate_report_sha256": context["inputs"]["candidate_snapshot"][
            "sha256"
        ],
        "v2_execution_report_sha256": context["inputs"]["v2_snapshot"]["sha256"],
        "stitch_report_sha256": context["stitch_snapshot"]["sha256"],
    }


__all__: tuple[str, ...] = ()
