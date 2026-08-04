"""Combine exact follow-up review and alignment evidence without activation."""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import tempfile
from typing import Any

from ._separation_authorised_excerpt import _document_sha256
from ._separation_candidate_followup_full_song_alignment import (
    _measure_private_candidate_followup_full_song_alignment,
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


SCHEMA = "sunofriend.private-separation-candidate-followup-readiness-reassessment.v1"
STATUS = "evidence_reassessed_no_activation"
REPORT_NAME = "private-separation-candidate-followup-readiness-reassessment.json"
_FALSE_EFFECTS = {
    "audio_created_or_mutated": False,
    "candidate_accepted": False,
    "candidate_selected": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "readiness_record_created": True,
    "source_graph_mutated": False,
}


def _reassess_private_candidate_followup_readiness(
    full_song_review_result_path: str | Path,
    *,
    alignment_result_path: str | Path,
    full_song_review_export_path: str | Path,
    full_song_review_package_dir: str | Path,
    targeted_review_result_path: str | Path,
    targeted_reviewed_export_path: str | Path,
    targeted_review_package_dir: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    stitch_package_dir: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Write one exact evidence reassessment without approving the candidate."""

    output = Path(out).expanduser().absolute()
    _require_private_directory(
        output.parent, "private follow-up readiness result parent"
    )
    if os.path.lexists(output):
        raise FileExistsError(f"private follow-up readiness result exists: {output}")

    alignment_kwargs = {
        "full_song_review_export_path": full_song_review_export_path,
        "full_song_review_package_dir": full_song_review_package_dir,
        "targeted_review_result_path": targeted_review_result_path,
        "targeted_reviewed_export_path": targeted_reviewed_export_path,
        "targeted_review_package_dir": targeted_review_package_dir,
        "execution_dir": execution_dir,
        "v2_execution_dir": v2_execution_dir,
        "stitch_package_dir": stitch_package_dir,
    }
    with tempfile.TemporaryDirectory(prefix="sunofriend-followup-alignment-gate-") as temporary:
        temporary_root = Path(temporary)
        temporary_root.chmod(0o700)
        derived_alignment = _measure_private_candidate_followup_full_song_alignment(
            full_song_review_result_path,
            out=temporary_root / "alignment.json",
            **alignment_kwargs,
        )
        derived_alignment.pop("report", None)
    alignment_snapshot = _load_private_json_snapshot(
        alignment_result_path, "private follow-up alignment result"
    )
    if alignment_snapshot["document"] != derived_alignment:
        raise ValueError("private follow-up alignment result differs")
    full_review_snapshot = _load_private_json_snapshot(
        full_song_review_result_path,
        "private follow-up full-song review result",
    )
    full_review = full_review_snapshot["document"]
    if (
        derived_alignment["bindings"][
            "followup_full_song_review_result_sha256"
        ]
        != full_review_snapshot["sha256"]
        or derived_alignment["bindings"][
            "followup_full_song_review_result_document_sha256"
        ]
        != full_review.get("document_sha256")
    ):
        raise ValueError("private follow-up review and alignment binding differs")

    evidence_roots = tuple(
        Path(value).expanduser().absolute()
        for value in (
            full_song_review_package_dir,
            targeted_review_package_dir,
            execution_dir,
            v2_execution_dir,
            stitch_package_dir,
        )
    )
    _require_output_disjoint_from_inputs(
        output,
        evidence_roots=evidence_roots,
        evidence_paths=(full_review_snapshot["path"], alignment_snapshot["path"]),
    )

    review_readiness = full_review["readiness_evidence"]
    alignment_readiness = derived_alignment["readiness_evidence"]
    all_boundaries_clean = review_readiness["all_followup_boundaries_clean"]
    all_roles_useful = review_readiness[
        "all_followup_full_song_roles_useful"
    ]
    alignment_passed = alignment_readiness["alignment_gate_passed"]
    prerequisites_met = bool(
        all_boundaries_clean and all_roles_useful and alignment_passed
    )
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "candidate_identity": "review_derived_followup_join_remediation",
        "bindings": {
            "followup_full_song_review_result_sha256": full_review_snapshot[
                "sha256"
            ],
            "followup_full_song_review_result_document_sha256": full_review[
                "document_sha256"
            ],
            "followup_alignment_result_sha256": alignment_snapshot["sha256"],
            "followup_alignment_result_document_sha256": derived_alignment[
                "document_sha256"
            ],
            "followup_execution_report_sha256": derived_alignment["bindings"][
                "followup_execution_report_sha256"
            ],
            "followup_candidate_report_sha256": derived_alignment["bindings"][
                "followup_candidate_report_sha256"
            ],
            "stitch_report_sha256": derived_alignment["bindings"][
                "stitch_report_sha256"
            ],
        },
        "clock": deepcopy(derived_alignment["clock"]),
        "evidence": {
            "targeted_followup_listening_pass": True,
            "followup_full_song_review_complete": True,
            "all_followup_boundaries_clean": all_boundaries_clean,
            "all_followup_full_song_roles_useful": all_roles_useful,
            "followup_alignment_complete": True,
            "followup_alignment_gate_passed": alignment_passed,
            "technical_and_listening_prerequisites_met": prerequisites_met,
        },
        "readiness": {
            "reassessment_complete": True,
            "final_human_acceptance_review_eligible": prerequisites_met,
            "final_human_acceptance_review_complete": False,
            "original_audible_joins_resolved": False,
            "separator_selected": False,
            "separator_accepted": False,
            "product_route_enabled": False,
            "publication_ready": False,
        },
        "next_action": (
            "run_explicit_final_followup_candidate_acceptance_review"
            if prerequisites_met
            else "remediate_failed_followup_candidate_evidence"
        ),
        "interpretation": {
            "evidence_combination_adds_listening_evidence": False,
            "clean_boundaries_are_separator_accuracy": False,
            "alignment_gate_pass_is_separator_acceptance": False,
            "useful_full_song_roles_are_publication_approval": False,
            "prerequisites_met_is_final_acceptance": False,
            "automatic_winner_selected": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_FALSE_EFFECTS),
        "limitations": [
            "This report combines existing evidence; it adds no listening evidence.",
            "Boundary cleanliness, overall usefulness and alignment remain distinct claims.",
            "A separate explicit human acceptance review must resolve the original audible-join gate.",
            "No separator is selected, accepted, published or exposed to a product route.",
        ],
    }
    result["document_sha256"] = _document_sha256(result)
    published = False
    try:
        _write_json_exclusive(output, result)
        published = True
        for snapshot, label in (
            (full_review_snapshot, "private follow-up full-song review result"),
            (alignment_snapshot, "private follow-up alignment result"),
        ):
            current = _load_private_json_snapshot(snapshot["path"], label)
            if (
                current["sha256"] != snapshot["sha256"]
                or current["document"] != snapshot["document"]
            ):
                raise ValueError(f"{label} changed")
    except BaseException:
        if published:
            try:
                output.unlink()
            except FileNotFoundError:
                pass
        raise
    return {**result, "report": str(output)}


__all__: tuple[str, ...] = ()
