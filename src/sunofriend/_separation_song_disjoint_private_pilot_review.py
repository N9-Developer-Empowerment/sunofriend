"""Resolve the exact human review for one source-distinct private pilot.

The existing full-song resolver remains the authority for browser, stitch and
audio verification.  This module adds only the narrow policy decision needed
by the song-disjoint pilot: useful complete-song vocals, instrumental and
reconstruction permit private evaluation of this exact output.  Boundary
ratings remain visible diagnostics and never become public product authority.
"""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256, _sha256
from ._separation_full_song_executor import _require_private_directory
from ._separation_full_song_join_remediation_review_result import (
    _write_json_exclusive,
)
from ._separation_full_song_review import (
    SCHEMA as FULL_SONG_REVIEW_SCHEMA,
    STATUS as FULL_SONG_REVIEW_STATUS,
    _FALSE_EFFECTS as FULL_SONG_FALSE_EFFECTS,
    _resolve_private_separation_full_song_review,
)
from ._separation_full_song_stitch import _FALSE_PERMISSIONS
from ._separation_song_disjoint_private_pilot import (
    _load_verified_song_disjoint_private_pilot_evidence,
)


STATUS_SCHEMA = "sunofriend.private-separation-song-disjoint-pilot-review-status.v1"
RESULT_SCHEMA = "sunofriend.private-separation-song-disjoint-pilot-review-result.v1"
RESULT_STATUS_AUTHORIZED = "bounded_private_pilot_output_use_authorized"
RESULT_STATUS_NOT_AUTHORIZED = "bounded_private_pilot_output_use_not_authorized"
POLICY_ID = "complete-song-utility-with-boundary-diagnostics-v1"
REPORT_NAME = "private-separation-song-disjoint-pilot-review-result.json"
_RATED_ROLES = ("vocals", "instrumental", "reconstruction")


def _status_private_song_disjoint_pilot_review(
    review_path: str | Path,
    *,
    pilot_evidence_path: str | Path,
    package_dir: str | Path,
) -> dict[str, Any]:
    """Verify a complete browser export without writing a durable result."""

    context = _load_completed_pilot_review(
        review_path,
        pilot_evidence_path=pilot_evidence_path,
        package_dir=package_dir,
    )
    assessment = _assessment(context["review_result"])
    document: dict[str, Any] = {
        "schema": STATUS_SCHEMA,
        "status": "complete_review_verified_no_activation",
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": _result_bindings(context),
        "review_summary": _review_summary(context["review_result"]),
        "assessment_preview": {
            "all_generated_full_song_roles_useful": assessment[
                "all_generated_full_song_roles_useful"
            ],
            "would_authorize_bounded_private_pilot_output_use": assessment[
                "bounded_private_pilot_output_use_permitted"
            ],
            "boundary_findings_are_an_automatic_veto": False,
        },
        "permissions": {
            **dict(_FALSE_PERMISSIONS),
            "bounded_private_pilot_output_use": False,
        },
        "effects": _effects(result_created=False, output_authorized=False),
    }
    document["document_sha256"] = _document_sha256(document)
    return document


def _resolve_private_song_disjoint_pilot_review(
    review_path: str | Path,
    *,
    pilot_evidence_path: str | Path,
    package_dir: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Write one path-free private-pilot decision without changing audio."""

    output = Path(out).expanduser().absolute()
    if output.name != REPORT_NAME:
        raise ValueError(f"song-disjoint pilot review filename must be {REPORT_NAME}")
    _require_private_directory(
        output.parent,
        "song-disjoint private pilot review result parent",
    )
    if os.path.lexists(output):
        raise FileExistsError(
            f"song-disjoint private pilot review result exists: {output}"
        )

    context = _load_completed_pilot_review(
        review_path,
        pilot_evidence_path=pilot_evidence_path,
        package_dir=package_dir,
    )
    _require_output_disjoint(output, context=context)
    review_result = context["review_result"]
    assessment = _assessment(review_result)
    permitted = assessment["bounded_private_pilot_output_use_permitted"]
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "status": (
            RESULT_STATUS_AUTHORIZED if permitted else RESULT_STATUS_NOT_AUTHORIZED
        ),
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": _result_bindings(context),
        "clock": deepcopy(review_result["clock"]),
        "review_summary": _review_summary(review_result),
        "private_pilot_assessment": assessment,
        "readiness": {
            "automatic_pilot_evidence_complete": True,
            "human_full_song_and_boundary_review_complete": True,
            "whole_song_utility_conclusion_ready": True,
            "bounded_private_pilot_output_use_permitted": permitted,
            "separator_accuracy_ground_truth_established": False,
            "public_product_acceptance_complete": False,
            "publication_ready": False,
        },
        "interpretation": {
            "complete_song_usefulness_drives_this_private_pilot_gate": True,
            "boundary_ratings_are_retained_diagnostics": True,
            "audible_or_uncertain_boundary_is_an_automatic_veto": False,
            "boundary_cleanliness_is_separator_accuracy": False,
            "listener_notes_copied": False,
            "separator_selected_or_accepted": False,
        },
        "permissions": {
            **dict(_FALSE_PERMISSIONS),
            "bounded_private_pilot_output_use": permitted,
        },
        "effects": _effects(
            result_created=True,
            output_authorized=permitted,
        ),
        "limitations": [
            "This decision applies only to the exact reviewed private pilot output.",
            "Audible and cannot-tell boundary ratings remain preserved as diagnostics.",
            "Complete-song usefulness is human evidence, not ground-truth separator accuracy.",
            "No audio, browser review, source graph or product contract is changed.",
            "Simple, Studio, TUI, CLI, download and publication routes remain disabled.",
        ],
    }
    result["document_sha256"] = _document_sha256(result)

    rechecked = _load_completed_pilot_review(
        review_path,
        pilot_evidence_path=pilot_evidence_path,
        package_dir=package_dir,
    )
    if _context_identity(rechecked) != _context_identity(context):
        raise ValueError("song-disjoint private pilot review evidence changed")
    _write_json_exclusive(output, result)
    return {**result, "report": str(output)}


def _load_completed_pilot_review(
    review_path: str | Path,
    *,
    pilot_evidence_path: str | Path,
    package_dir: str | Path,
) -> dict[str, Any]:
    pilot = _load_verified_song_disjoint_private_pilot_evidence(
        pilot_evidence_path
    )
    package = Path(package_dir).expanduser().absolute()
    _require_private_directory(package, "song-disjoint private pilot stitch package")
    review = Path(review_path).expanduser().absolute()

    with tempfile.TemporaryDirectory(
        prefix="sunofriend-song-disjoint-review-"
    ) as temporary_name:
        temporary = Path(temporary_name)
        temporary.chmod(0o700)
        verified = _resolve_private_separation_full_song_review(
            review,
            package_dir=package,
            out=temporary / "verified-full-song-review.json",
        )
        review_result = {
            key: deepcopy(value)
            for key, value in verified.items()
            if key != "report"
        }

    pilot_document = pilot["document"]
    pilot_bindings = pilot_document["bindings"]
    bindings = review_result.get("bindings")
    if (
        review_result.get("schema") != FULL_SONG_REVIEW_SCHEMA
        or review_result.get("status") != FULL_SONG_REVIEW_STATUS
        or review_result.get("evidence_scope") != "private_development_only"
        or review_result.get("document_sha256")
        != _document_sha256(review_result)
        or review_result.get("permissions") != _FALSE_PERMISSIONS
        or review_result.get("effects") != FULL_SONG_FALSE_EFFECTS
        or not isinstance(bindings, Mapping)
        or bindings.get("stitch_report_sha256")
        != pilot_bindings["pilot_stitch_sha256"]
        or bindings.get("stitch_document_sha256")
        != pilot_bindings["pilot_stitch_document_sha256"]
        or bindings.get("review_seed_sha256")
        != pilot_bindings["pilot_review_seed_sha256"]
        or bindings.get("package_commitment")
        != pilot_bindings["pilot_review_package_commitment"]
        or bindings.get("review_export_sha256") != _sha256(review)
        or review_result.get("clock")
        != pilot_document["automatic_execution"]["clock"]
        or review_result.get("readiness", {}).get(
            "full_song_and_boundary_listening_complete"
        )
        is not True
        or len(review_result.get("boundaries", []))
        != pilot_document["human_review"]["boundary_count"]
    ):
        raise ValueError("song-disjoint private pilot review binding differs")
    return {
        "pilot_snapshot": pilot,
        "package": package,
        "review_path": review,
        "review_result": review_result,
    }


def _review_summary(review_result: Mapping[str, Any]) -> dict[str, Any]:
    counts = deepcopy(review_result["boundary_summary"]["rating_counts_by_role"])
    audible = deepcopy(
        review_result["boundary_summary"]["audible_join_boundaries_by_role"]
    )
    cannot_tell = {
        role: [
            item["boundary_index"]
            for item in review_result["boundaries"]
            if item["ratings"][role] == "cannot_tell"
        ]
        for role in _RATED_ROLES
    }
    return {
        "full_song_heard_all": True,
        "full_song_ratings": deepcopy(review_result["full_song"]["ratings"]),
        "reviewed_boundary_count": review_result["boundary_summary"][
            "reviewed_boundaries"
        ],
        "boundary_rating_counts_by_role": counts,
        "audible_join_boundaries_by_role": audible,
        "cannot_tell_boundaries_by_role": cannot_tell,
        "all_boundaries_clean": all(
            counts[role]["clean"]
            == review_result["boundary_summary"]["reviewed_boundaries"]
            for role in _RATED_ROLES
        ),
        "listener_notes_copied": False,
    }


def _assessment(review_result: Mapping[str, Any]) -> dict[str, Any]:
    ratings = review_result["full_song"]["ratings"]
    all_useful = all(ratings[role] == "useful" for role in _RATED_ROLES)
    return {
        "all_generated_full_song_roles_useful": all_useful,
        "bounded_private_pilot_output_use_permitted": all_useful,
        "selection_scope": "this_exact_reviewed_private_output_only",
        "boundary_findings_retained_as_diagnostics": True,
        "boundary_findings_are_an_automatic_veto": False,
        "model_run_required": False,
        "next_action": (
            "continue_bounded_multi_song_private_evaluation"
            if all_useful
            else "retain_output_for_diagnosis_or_bounded_remediation"
        ),
    }


def _result_bindings(context: Mapping[str, Any]) -> dict[str, Any]:
    pilot = context["pilot_snapshot"]
    pilot_document = pilot["document"]
    review_result = context["review_result"]
    return {
        "pilot_evidence_sha256": pilot["sha256"],
        "pilot_evidence_document_sha256": pilot_document["document_sha256"],
        "pilot_stitch_sha256": pilot_document["bindings"]["pilot_stitch_sha256"],
        "pilot_stitch_document_sha256": pilot_document["bindings"][
            "pilot_stitch_document_sha256"
        ],
        "pilot_review_seed_sha256": pilot_document["bindings"][
            "pilot_review_seed_sha256"
        ],
        "pilot_review_package_commitment": pilot_document["bindings"][
            "pilot_review_package_commitment"
        ],
        "review_export_sha256": review_result["bindings"][
            "review_export_sha256"
        ],
        "verified_full_song_review_document_sha256": review_result[
            "document_sha256"
        ],
    }


def _effects(*, result_created: bool, output_authorized: bool) -> dict[str, bool]:
    return {
        "audio_created_or_mutated": False,
        "bounded_private_pilot_output_authorized": output_authorized,
        "human_review_completed_or_mutated": False,
        "model_run": False,
        "product_contract_mutated": False,
        "publication_state_mutated": False,
        "review_result_created": result_created,
        "separator_accepted": False,
        "separator_selected": False,
        "source_graph_mutated": False,
    }


def _context_identity(context: Mapping[str, Any]) -> tuple[str, ...]:
    pilot = context["pilot_snapshot"]
    review_result = context["review_result"]
    return (
        pilot["sha256"],
        pilot["document"]["document_sha256"],
        review_result["bindings"]["review_export_sha256"],
        review_result["document_sha256"],
    )


def _require_output_disjoint(
    output: Path,
    *,
    context: Mapping[str, Any],
) -> None:
    pilot_path = Path(context["pilot_snapshot"]["path"]).resolve(strict=True)
    review_path = Path(context["review_path"]).resolve(strict=True)
    package = Path(context["package"]).resolve(strict=True)
    if output in {pilot_path, review_path} or package in output.parents:
        raise ValueError("song-disjoint private pilot review output overlaps evidence")


__all__: tuple[str, ...] = ()
