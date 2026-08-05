"""Reassess exact final-acceptance evidence for a bounded private pilot.

This projection deliberately stops before product integration.  It re-runs the
complete final-acceptance resolver from the human exports and immutable
evidence chain, requires the supplied result to be exact, and records which
independent candidates are ready only for a private pilot.  It never ranks or
selects a variant and cannot enable or publish a separator.
"""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

from ._separation_authorised_excerpt import _document_sha256
from ._separation_candidate_followup_variant_final_acceptance_review_result import (
    RESULT_SCHEMA as ACCEPTANCE_RESULT_SCHEMA,
    RESULT_STATUS as ACCEPTANCE_RESULT_STATUS,
    _resolve_private_candidate_followup_variant_final_acceptance_reviews,
)
from ._separation_candidate_followup_variant_readiness_reassessment import (
    SCHEMA as READINESS_SCHEMA,
    STATUS as READINESS_STATUS,
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


SCHEMA = (
    "sunofriend.private-separation-candidate-followup-variant-"
    "final-readiness-reassessment.v1"
)
STATUS = "private_pilot_readiness_reassessed_publication_blocked"
REPORT_NAME = (
    "private-separation-candidate-followup-variant-final-readiness-reassessment.json"
)
_FALSE_EFFECTS = {
    "acceptance_record_mutated": False,
    "audio_created_or_mutated": False,
    "candidate_accepted_by_this_operation": False,
    "candidate_selected": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "readiness_record_created": True,
    "source_graph_mutated": False,
}
_UNRESOLVED_PUBLICATION_BOUNDARIES = (
    "cross_song_separated_audio_quality",
    "broad_role_coverage",
    "hidden_song_disjoint_test_set",
    "checkpoint_usage_and_distribution_terms",
    "offline_execution_acceptance",
    "resource_envelope_acceptance_on_16_gib_class",
    "public_cli_tui_simple_studio_route",
)


def _reassess_private_candidate_followup_variant_final_readiness(
    final_acceptance_result_path: str | Path,
    *,
    final_acceptance_review_export_paths: Sequence[str | Path],
    review_package_dir: str | Path,
    readiness_result_path: str | Path,
    full_song_review_result_path: str | Path,
    alignment_package_dir: str | Path,
    full_song_review_export_paths: Sequence[str | Path],
    full_song_review_package_dir: str | Path,
    variant_review_result_path: str | Path,
    variant_reviewed_export_path: str | Path,
    variant_review_package_dir: str | Path,
    plan_path: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    variant_execution_dir: str | Path,
    stitch_package_dir: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Project exact private-pilot readiness without choosing a candidate."""

    if isinstance(final_acceptance_review_export_paths, (str, bytes, Path)):
        raise TypeError(
            "final_acceptance_review_export_paths must be the complete review sequence"
        )
    if isinstance(full_song_review_export_paths, (str, bytes, Path)):
        raise TypeError(
            "full_song_review_export_paths must be the complete review sequence"
        )
    acceptance_exports = list(final_acceptance_review_export_paths)
    full_song_exports = list(full_song_review_export_paths)
    if not acceptance_exports:
        raise ValueError("no final acceptance reviews supplied")
    if not full_song_exports:
        raise ValueError("no eligible-variant full-song reviews supplied")

    output = Path(out).expanduser().absolute()
    _require_private_directory(
        output.parent, "private final readiness reassessment parent"
    )
    if os.path.lexists(output):
        raise FileExistsError(f"private final readiness reassessment exists: {output}")

    verification_kwargs = {
        "review_package_dir": review_package_dir,
        "readiness_result_path": readiness_result_path,
        "full_song_review_result_path": full_song_review_result_path,
        "alignment_package_dir": alignment_package_dir,
        "full_song_review_export_paths": full_song_exports,
        "full_song_review_package_dir": full_song_review_package_dir,
        "variant_review_result_path": variant_review_result_path,
        "variant_reviewed_export_path": variant_reviewed_export_path,
        "variant_review_package_dir": variant_review_package_dir,
        "plan_path": plan_path,
        "execution_dir": execution_dir,
        "v2_execution_dir": v2_execution_dir,
        "variant_execution_dir": variant_execution_dir,
        "stitch_package_dir": stitch_package_dir,
    }
    derived = _derive_final_acceptance_result(
        acceptance_exports,
        verification_kwargs=verification_kwargs,
    )
    supplied = _load_private_json_snapshot(
        final_acceptance_result_path,
        "private final acceptance review result",
    )
    acceptance = supplied["document"]
    if supplied["sha256"] != derived["sha256"] or acceptance != derived["document"]:
        raise ValueError("private final acceptance review result differs")
    if (
        acceptance.get("schema") != ACCEPTANCE_RESULT_SCHEMA
        or acceptance.get("status") != ACCEPTANCE_RESULT_STATUS
        or acceptance.get("document_sha256") != _document_sha256(acceptance)
        or acceptance.get("permissions") != _FALSE_PERMISSIONS
    ):
        raise ValueError("private final acceptance review result differs")

    readiness_snapshot = _load_private_json_snapshot(
        readiness_result_path,
        "private multi-variant readiness reassessment",
    )
    readiness = readiness_snapshot["document"]
    if (
        readiness.get("schema") != READINESS_SCHEMA
        or readiness.get("status") != READINESS_STATUS
        or readiness.get("document_sha256") != _document_sha256(readiness)
        or readiness.get("permissions") != _FALSE_PERMISSIONS
        or acceptance["bindings"].get("readiness_result_sha256")
        != readiness_snapshot["sha256"]
        or acceptance["bindings"].get("readiness_result_document_sha256")
        != readiness["document_sha256"]
    ):
        raise ValueError("private final acceptance readiness binding differs")

    reviewed_ids = list(acceptance["reviewed_variant_ids"])
    eligible_ids = list(
        readiness["readiness"]["final_human_acceptance_review_eligible_variant_ids"]
    )
    if reviewed_ids != eligible_ids:
        raise ValueError("private final acceptance variant inventory differs")
    readiness_by_id = {
        item["variant_id"]: item for item in readiness["variant_evidence"]
    }
    acceptance_by_id = {
        item["variant_id"]: item for item in acceptance["variant_results"]
    }
    if set(readiness_by_id) != set(readiness["reviewed_variant_ids"]):
        raise ValueError("private final acceptance readiness inventory differs")
    if set(acceptance_by_id) != set(reviewed_ids):
        raise ValueError("private final acceptance result inventory differs")

    accepted_ids = list(acceptance["private_pilot_acceptance"]["accepted_variant_ids"])
    if any(variant_id not in reviewed_ids for variant_id in accepted_ids):
        raise ValueError("private final acceptance accepted inventory differs")
    accepted_set = set(accepted_ids)
    variant_evidence: list[dict[str, Any]] = []
    for variant_id in reviewed_ids:
        prerequisite = readiness_by_id[variant_id]
        decision = acceptance_by_id[variant_id]
        prerequisites_met = prerequisite["evidence"].get(
            "technical_and_listening_prerequisites_met"
        )
        accepted = decision["decision_evidence"].get("accepted_for_private_pilot")
        if prerequisites_met is not True or type(accepted) is not bool:
            raise ValueError("private final acceptance readiness evidence differs")
        if accepted != (variant_id in accepted_set):
            raise ValueError("private final acceptance accepted inventory differs")
        variant_evidence.append(
            {
                "variant_id": variant_id,
                "bindings": {
                    "final_acceptance_review_export_sha256": next(
                        item["review_export_sha256"]
                        for item in acceptance["bindings"]["review_exports"]
                        if item["variant_id"] == variant_id
                    ),
                },
                "evidence": {
                    "technical_and_listening_prerequisites_met": True,
                    "final_human_acceptance_review_complete": True,
                    "all_required_answers_affirmative": decision["decision_evidence"][
                        "all_required_answers_affirmative"
                    ],
                    "explicit_private_pilot_acceptance": accepted,
                    "negative_answer_ids": list(
                        decision["decision_evidence"]["negative_answer_ids"]
                    ),
                    "uncertain_answer_ids": list(
                        decision["decision_evidence"]["uncertain_answer_ids"]
                    ),
                },
                "readiness": {
                    "bounded_private_pilot_ready": accepted,
                    "candidate_scope_full_song_prerequisites_passed": True,
                    "original_audible_joins_resolved": False,
                    "selected": False,
                    "separator_accepted_as_product_default": False,
                    "product_route_enabled": False,
                    "publication_ready": False,
                },
            }
        )

    not_ready_ids = [
        variant_id for variant_id in reviewed_ids if variant_id not in accepted_set
    ]
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "candidate_identity": "independent_private_pilot_candidates_not_ranked",
        "bindings": {
            "final_acceptance_result_sha256": supplied["sha256"],
            "final_acceptance_result_document_sha256": acceptance["document_sha256"],
            "final_acceptance_review_package_report_sha256": acceptance["bindings"][
                "final_acceptance_review_package_report_sha256"
            ],
            "readiness_result_sha256": readiness_snapshot["sha256"],
            "readiness_result_document_sha256": readiness["document_sha256"],
            "variant_full_song_review_result_sha256": acceptance["bindings"][
                "variant_full_song_review_result_sha256"
            ],
            "variant_alignment_package_sha256": acceptance["bindings"][
                "variant_alignment_package_sha256"
            ],
        },
        "clock": deepcopy(acceptance["clock"]),
        "reviewed_variant_ids": reviewed_ids,
        "variant_evidence": variant_evidence,
        "private_pilot_readiness": {
            "reassessment_complete": True,
            "ready_variant_ids": accepted_ids,
            "ready_variant_count": len(accepted_ids),
            "not_ready_variant_ids": not_ready_ids,
            "not_ready_variant_count": len(not_ready_ids),
            "zero_one_or_multiple_ready_variants_allowed": True,
            "bounded_private_pilot_available": bool(accepted_ids),
            "variant_selected": False,
            "separator_accepted_as_product_default": False,
            "original_audible_joins_resolved": False,
            "product_route_enabled": False,
            "publication_ready": False,
        },
        "publication_boundary": {
            "reassessment_closes_publication_gate": False,
            "unresolved_or_separately_evidenced_items": list(
                _UNRESOLVED_PUBLICATION_BOUNDARIES
            ),
            "current_global_gate_status_recomputed": False,
        },
        "next_action": (
            "prepare_bounded_private_pilot_without_product_activation"
            if accepted_ids
            else "return_to_bounded_remediation"
        ),
        "interpretation": {
            "private_pilot_readiness_requires_prerequisites_and_explicit_acceptance": True,
            "negative_and_uncertain_answers_preserved": True,
            "variants_remain_independent": True,
            "package_order_is_preference": False,
            "automatic_winner_selected": False,
            "private_pilot_readiness_is_separator_selection": False,
            "private_pilot_readiness_is_product_activation": False,
            "private_pilot_readiness_is_publication_permission": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_FALSE_EFFECTS),
        "limitations": [
            "This report re-verifies existing human and technical evidence; it adds no listening evidence.",
            "A ready candidate may be used only in a separately bounded private pilot.",
            "No candidate is ranked or selected, even when more than one candidate is ready.",
            "Candidate-scoped readiness does not resolve the global publication ledger or enable a product route.",
            "Keep every evidence tree quiescent because JSON and WAV inputs are not one atomic snapshot.",
        ],
    }
    result["document_sha256"] = _document_sha256(result)

    package_root = Path(review_package_dir).expanduser().absolute()
    alignment_root = Path(alignment_package_dir).expanduser().absolute()
    full_song_root = Path(full_song_review_package_dir).expanduser().absolute()
    variant_review_root = Path(variant_review_package_dir).expanduser().absolute()
    execution_root = Path(execution_dir).expanduser().absolute()
    v2_execution_root = Path(v2_execution_dir).expanduser().absolute()
    variant_execution_root = Path(variant_execution_dir).expanduser().absolute()
    stitch_root = Path(stitch_package_dir).expanduser().absolute()
    _require_output_disjoint_from_inputs(
        output,
        evidence_roots=(
            package_root,
            alignment_root,
            full_song_root,
            variant_review_root,
            execution_root,
            v2_execution_root,
            variant_execution_root,
            stitch_root,
        ),
        evidence_paths=(
            supplied["path"],
            readiness_snapshot["path"],
            Path(full_song_review_result_path).expanduser().absolute(),
            Path(variant_review_result_path).expanduser().absolute(),
            Path(variant_reviewed_export_path).expanduser().absolute(),
            Path(plan_path).expanduser().absolute(),
            *(Path(path).expanduser().absolute() for path in acceptance_exports),
            *(Path(path).expanduser().absolute() for path in full_song_exports),
        ),
    )

    published = False
    try:
        _write_json_exclusive(output, result)
        published = True
        current_derived = _derive_final_acceptance_result(
            acceptance_exports,
            verification_kwargs=verification_kwargs,
        )
        current_supplied = _load_private_json_snapshot(
            supplied["path"], "private final acceptance review result"
        )
        current_readiness = _load_private_json_snapshot(
            readiness_snapshot["path"],
            "private multi-variant readiness reassessment",
        )
        if (
            current_derived["sha256"] != derived["sha256"]
            or current_derived["document"] != derived["document"]
            or current_supplied["sha256"] != supplied["sha256"]
            or current_supplied["document"] != acceptance
            or current_readiness["sha256"] != readiness_snapshot["sha256"]
            or current_readiness["document"] != readiness
        ):
            raise ValueError("private final readiness evidence changed")
    except BaseException:
        if published:
            try:
                output.unlink()
            except FileNotFoundError:
                pass
        raise
    return {**result, "report": str(output)}


def _derive_final_acceptance_result(
    reviewed_export_paths: Sequence[str | Path],
    *,
    verification_kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix="sunofriend-final-acceptance-readiness-gate-"
    ) as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        result_path = root / "resolved.json"
        _resolve_private_candidate_followup_variant_final_acceptance_reviews(
            reviewed_export_paths,
            out=result_path,
            **verification_kwargs,
        )
        return _load_private_json_snapshot(
            result_path,
            "derived private final acceptance review result",
        )


__all__: tuple[str, ...] = ()
