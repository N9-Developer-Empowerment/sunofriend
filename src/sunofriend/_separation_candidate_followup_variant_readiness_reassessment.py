"""Reassess every reviewed remediation variant without choosing between them."""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

from ._separation_authorised_excerpt import _document_sha256
from ._separation_candidate_followup_variant_full_song_alignment import (
    REPORT_NAME as ALIGNMENT_REPORT_NAME,
    SCHEMA as ALIGNMENT_SCHEMA,
    STATUS as ALIGNMENT_STATUS,
    VARIANT_SCHEMA as ALIGNMENT_VARIANT_SCHEMA,
    VARIANT_STATUS as ALIGNMENT_VARIANT_STATUS,
    _measure_private_candidate_followup_variant_full_song_alignments,
    _verify_written_package,
)
from ._separation_candidate_followup_variant_full_song_review_result import (
    RESULT_SCHEMA as REVIEW_RESULT_SCHEMA,
    RESULT_STATUS as REVIEW_RESULT_STATUS,
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
    "readiness-reassessment.v1"
)
STATUS = "independent_variant_evidence_reassessed_no_activation"
REPORT_NAME = (
    "private-separation-candidate-followup-variant-readiness-reassessment.json"
)
_FALSE_EFFECTS = {
    "audio_created_or_mutated": False,
    "candidate_accepted": False,
    "candidate_selected": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "readiness_record_created": True,
    "source_graph_mutated": False,
}


def _reassess_private_candidate_followup_variant_readiness(
    full_song_review_result_path: str | Path,
    *,
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
    """Combine each exact review/alignment pair without ranking a variant."""

    if isinstance(full_song_review_export_paths, (str, bytes, Path)):
        raise TypeError(
            "full_song_review_export_paths must be the complete review sequence"
        )
    reviewed_exports = list(full_song_review_export_paths)
    if not reviewed_exports:
        raise ValueError("no eligible-variant full-song reviews supplied")

    output = Path(out).expanduser().absolute()
    _require_private_directory(
        output.parent, "private multi-variant readiness result parent"
    )
    if os.path.lexists(output):
        raise FileExistsError(
            f"private multi-variant readiness result exists: {output}"
        )
    alignment_root = Path(alignment_package_dir).expanduser().absolute()
    _require_private_directory(
        alignment_root, "private eligible-variant alignment package"
    )
    alignment_kwargs = {
        "full_song_review_export_paths": reviewed_exports,
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
    derived = _derive_alignment_package(
        full_song_review_result_path, alignment_kwargs=alignment_kwargs
    )
    alignment_snapshot, alignment_children = _require_exact_alignment_package(
        alignment_root, derived=derived
    )
    review_snapshot = _load_private_json_snapshot(
        full_song_review_result_path,
        "private eligible-variant full-song review result",
    )
    review = review_snapshot["document"]
    alignment = alignment_snapshot["document"]
    if (
        review.get("schema") != REVIEW_RESULT_SCHEMA
        or review.get("status") != REVIEW_RESULT_STATUS
        or review.get("document_sha256") != _document_sha256(review)
        or review.get("reviewed_variant_ids") != alignment.get("aligned_variant_ids")
        or review.get("clock") != alignment.get("clock")
        or alignment["bindings"].get("variant_full_song_review_result_sha256")
        != review_snapshot["sha256"]
        or alignment["bindings"].get(
            "variant_full_song_review_result_document_sha256"
        )
        != review.get("document_sha256")
    ):
        raise ValueError("private multi-variant review and alignment binding differs")

    _require_output_disjoint_from_inputs(
        output,
        evidence_roots=(
            alignment_root,
            Path(full_song_review_package_dir).expanduser().absolute(),
            Path(variant_review_package_dir).expanduser().absolute(),
            Path(execution_dir).expanduser().absolute(),
            Path(v2_execution_dir).expanduser().absolute(),
            Path(variant_execution_dir).expanduser().absolute(),
            Path(stitch_package_dir).expanduser().absolute(),
        ),
        evidence_paths=(
            review_snapshot["path"],
            alignment_snapshot["path"],
            *(child["path"] for child in alignment_children),
        ),
    )

    review_by_variant = {
        item["variant_id"]: item for item in review["variant_results"]
    }
    alignment_by_variant = {
        child["document"]["variant_id"]: child
        for child in alignment_children
    }
    variant_evidence: list[dict[str, Any]] = []
    eligible_ids: list[str] = []
    for variant_id in alignment["aligned_variant_ids"]:
        reviewed = review_by_variant[variant_id]
        aligned_snapshot = alignment_by_variant[variant_id]
        aligned = aligned_snapshot["document"]
        all_roles_useful = reviewed["readiness_evidence"][
            "all_full_song_roles_useful"
        ]
        all_boundaries_clean = reviewed["readiness_evidence"][
            "all_boundaries_clean"
        ]
        alignment_passed = aligned["readiness_evidence"][
            "alignment_gate_passed"
        ]
        prerequisites_met = bool(
            all_roles_useful and all_boundaries_clean and alignment_passed
        )
        if prerequisites_met:
            eligible_ids.append(variant_id)
        variant_evidence.append(
            {
                "variant_id": variant_id,
                "bindings": {
                    "full_song_review_export_sha256": next(
                        item["review_export_sha256"]
                        for item in review["bindings"]["review_exports"]
                        if item["variant_id"] == variant_id
                    ),
                    "alignment_result_sha256": aligned_snapshot["sha256"],
                    "alignment_result_document_sha256": aligned[
                        "document_sha256"
                    ],
                },
                "evidence": {
                    "full_song_review_complete": True,
                    "all_full_song_roles_useful": all_roles_useful,
                    "all_original_boundaries_clean": all_boundaries_clean,
                    "alignment_complete": True,
                    "alignment_gate_passed": alignment_passed,
                    "technical_and_listening_prerequisites_met": prerequisites_met,
                },
                "readiness": {
                    "final_human_acceptance_review_eligible": prerequisites_met,
                    "final_human_acceptance_review_complete": False,
                    "original_audible_joins_resolved": False,
                    "selected": False,
                    "accepted": False,
                    "product_route_enabled": False,
                    "publication_ready": False,
                },
            }
        )

    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "candidate_identity": "reviewed_eligible_variants_remain_independent",
        "bindings": {
            "variant_full_song_review_result_sha256": review_snapshot["sha256"],
            "variant_full_song_review_result_document_sha256": review[
                "document_sha256"
            ],
            "variant_alignment_package_sha256": alignment_snapshot["sha256"],
            "variant_alignment_package_document_sha256": alignment[
                "document_sha256"
            ],
        },
        "clock": deepcopy(alignment["clock"]),
        "reviewed_variant_ids": list(alignment["aligned_variant_ids"]),
        "variant_evidence": variant_evidence,
        "readiness": {
            "reassessment_complete": True,
            "final_human_acceptance_review_eligible_variant_ids": eligible_ids,
            "final_human_acceptance_review_eligible_variant_count": len(
                eligible_ids
            ),
            "final_human_acceptance_review_complete": False,
            "variant_selected": False,
            "separator_accepted": False,
            "original_audible_joins_resolved": False,
            "product_route_enabled": False,
            "publication_ready": False,
        },
        "next_action": (
            "run_independent_final_human_acceptance_reviews_for_all_eligible_variants"
            if eligible_ids
            else "remediate_failed_variant_evidence"
        ),
        "interpretation": {
            "evidence_combination_adds_listening_evidence": False,
            "eligibility_is_variant_preference": False,
            "multiple_variants_may_remain_eligible": True,
            "package_order_is_preference": False,
            "prerequisites_met_is_final_acceptance": False,
            "automatic_winner_selected": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_FALSE_EFFECTS),
        "limitations": [
            "This report combines existing review and clock evidence; it adds no listening evidence.",
            "Every reviewed variant remains independent, including variants that fail a prerequisite.",
            "Eligibility permits only a separate explicit final human acceptance review.",
            "No variant is ranked, selected, accepted, published or exposed to a product route.",
        ],
    }
    result["document_sha256"] = _document_sha256(result)
    published = False
    try:
        _write_json_exclusive(output, result)
        published = True
        current_derived = _derive_alignment_package(
            full_song_review_result_path, alignment_kwargs=alignment_kwargs
        )
        current_alignment, current_children = _require_exact_alignment_package(
            alignment_root, derived=current_derived
        )
        current_review = _load_private_json_snapshot(
            review_snapshot["path"],
            "private eligible-variant full-song review result",
        )
        if (
            current_review["sha256"] != review_snapshot["sha256"]
            or current_review["document"] != review
            or current_alignment["sha256"] != alignment_snapshot["sha256"]
            or current_alignment["document"] != alignment
            or [child["sha256"] for child in current_children]
            != [child["sha256"] for child in alignment_children]
        ):
            raise ValueError("private multi-variant readiness evidence changed")
    except BaseException:
        if published:
            try:
                output.unlink()
            except FileNotFoundError:
                pass
        raise
    return {**result, "report": str(output)}


def _derive_alignment_package(
    full_song_review_result_path: str | Path,
    *,
    alignment_kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix="sunofriend-variant-alignment-reassessment-gate-"
    ) as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        package = root / "alignments"
        _measure_private_candidate_followup_variant_full_song_alignments(
            full_song_review_result_path,
            out_dir=package,
            **alignment_kwargs,
        )
        parent = _load_private_json_snapshot(
            package / ALIGNMENT_REPORT_NAME,
            "derived eligible-variant alignment package",
        )
        children = [
            _load_private_json_snapshot(
                package / item["report"],
                "derived independent variant alignment result",
            )
            for item in parent["document"]["variant_alignments"]
        ]
        return {"parent": parent, "children": children}


def _require_exact_alignment_package(
    root: Path, *, derived: Mapping[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    snapshot = _load_private_json_snapshot(
        root / ALIGNMENT_REPORT_NAME,
        "private eligible-variant alignment package",
    )
    document = snapshot["document"]
    if (
        document != derived["parent"]["document"]
        or document.get("schema") != ALIGNMENT_SCHEMA
        or document.get("status") != ALIGNMENT_STATUS
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("permissions") != _FALSE_PERMISSIONS
        or document.get("readiness_evidence", {}).get("variant_selected") is not False
    ):
        raise ValueError("private eligible-variant alignment package differs")
    _verify_written_package(root, document=document)
    children = [
        _load_private_json_snapshot(
            root / item["report"],
            "private independent variant alignment result",
        )
        for item in document["variant_alignments"]
    ]
    if len(children) != len(derived["children"]):
        raise ValueError("private independent variant alignment inventory differs")
    for current, expected in zip(children, derived["children"]):
        child = current["document"]
        if (
            current["sha256"] != expected["sha256"]
            or child != expected["document"]
            or child.get("schema") != ALIGNMENT_VARIANT_SCHEMA
            or child.get("status") != ALIGNMENT_VARIANT_STATUS
            or child.get("document_sha256") != _document_sha256(child)
            or child.get("permissions") != _FALSE_PERMISSIONS
            or child.get("readiness_evidence", {}).get("selected") is not False
        ):
            raise ValueError("private independent variant alignment result differs")
    return snapshot, children


__all__: tuple[str, ...] = ()
