"""Assess reviewed private stems for a future provenance-safe import.

This is stage four of the private separation route. It verifies the exact
candidate package and its inherited human-review evidence, then records the
shape of a possible source-graph handoff. It creates no audio, receipt, graph
node, selection, activation, or user-facing product route.
"""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256
from ._separation_full_song_executor import _require_private_directory
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
    _write_json_exclusive,
)
from ._separation_private_developer_review_package import _FALSE_PERMISSIONS
from ._separation_private_render_review_equivalence import (
    _load_candidate_package,
    _load_verified_render_review_equivalence,
    _require_output_disjoint,
)


SCHEMA = "sunofriend.private-separation-reviewed-output-import-assessment.v1"
STATUS = "reviewed_output_import_assessed_implementation_required_no_activation"
REPORT_NAME = "private-separation-reviewed-output-import-assessment.json"
POLICY_ID = "reviewed-two-stem-provenance-safe-import-assessment-v1"
_PRIMARY_ROLES = ("vocals", "instrumental")
_EXPECTED_SOURCE_ROLES = {
    "vocals": {"source_role": "vocals", "declared_role": "vocals"},
    "instrumental": {"source_role": "other", "declared_role": "instrumental"},
}
_PERMISSIONS = {
    **_FALSE_PERMISSIONS,
    "private_import_implementation_may_be_designed": True,
}


def _assess_reviewed_output_import(
    equivalence_path: str | Path,
    *,
    reviewed_export_path: str | Path,
    reviewed_package_dir: str | Path,
    candidate_package_report_path: str | Path,
    out: str | Path,
) -> dict[str, Any]:
    """Write one path-free, non-activating reviewed-output assessment."""

    candidate = _load_candidate_package(candidate_package_report_path)
    equivalence = _load_verified_render_review_equivalence(
        equivalence_path,
        reviewed_export_path=reviewed_export_path,
        reviewed_package_dir=reviewed_package_dir,
        candidate_package_report_path=candidate_package_report_path,
    )
    document = equivalence["document"]
    _verify_import_prerequisites(document, candidate=candidate)

    output = Path(out).expanduser().absolute()
    if output.name != REPORT_NAME:
        raise ValueError(f"reviewed-output assessment filename must be {REPORT_NAME}")
    _require_private_directory(output.parent, "reviewed-output assessment root")
    if os.path.lexists(output):
        raise FileExistsError(f"reviewed-output assessment exists: {output}")
    _require_output_disjoint(
        output,
        reviewed_export=Path(reviewed_export_path).expanduser().absolute(),
        reviewed_package=Path(reviewed_package_dir).expanduser().absolute(),
        candidate_stitch_root=candidate["stitch_root"],
    )

    result = _assessment_document(
        equivalence=equivalence,
        candidate=candidate,
    )
    _write_json_exclusive(output, result)
    return {**result, "report": str(output)}


def _load_verified_reviewed_output_import_assessment(
    value: str | Path,
    *,
    equivalence_path: str | Path,
    reviewed_export_path: str | Path,
    reviewed_package_dir: str | Path,
    candidate_package_report_path: str | Path,
) -> dict[str, Any]:
    """Rebuild one assessment and require exact persisted equality."""

    snapshot = _load_private_json_snapshot(
        value,
        "reviewed-output import assessment",
    )
    with tempfile.TemporaryDirectory(prefix="sunofriend-verify-import-assessment-") as name:
        temporary = Path(name)
        temporary.chmod(0o700)
        rebuilt = _assess_reviewed_output_import(
            equivalence_path,
            reviewed_export_path=reviewed_export_path,
            reviewed_package_dir=reviewed_package_dir,
            candidate_package_report_path=candidate_package_report_path,
            out=temporary / REPORT_NAME,
        )
    expected = {key: item for key, item in rebuilt.items() if key != "report"}
    if snapshot["document"] != expected:
        raise ValueError("reviewed-output import assessment differs")
    return snapshot


def _verify_import_prerequisites(
    document: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any],
) -> None:
    prior = document["prior_human_review"]
    full_song = prior["full_song"]
    boundary_summary = prior["boundary_summary"]
    clock = document["clock"]
    if (
        document["readiness"]["prior_human_review_verified"] is not True
        or document["readiness"]["candidate_render_pcm24_equivalence_verified"]
        is not True
        or prior["review_evidence_applies_under_equivalence_policy"] is not True
        or full_song["heard_all"] is not True
        or any(full_song["ratings"].get(role) != "useful" for role in (*_PRIMARY_ROLES, "reconstruction"))
        or boundary_summary["reviewed_boundaries"] != clock["boundary_count"]
        or candidate["document"]["readiness"]["alignment_gate_passed"] is not True
        or candidate["document"]["readiness"]["exact_stitch_complete"] is not True
    ):
        raise ValueError("reviewed output import prerequisites are incomplete")

    stitch = candidate["stitch"]
    for role in (*_PRIMARY_ROLES, "reconstruction"):
        comparison = document["comparisons"][role]
        artifact = stitch["artifacts"][role]
        if (
            comparison["candidate_audio_sha256"] != artifact["sha256"]
            or comparison["sample_rate"] != clock["sample_rate"]
            or comparison["channels"] != clock["channels"]
            or comparison["frames"] != clock["frames"]
            or comparison["maximum_absolute_pcm24_lsb_difference"] > 1
        ):
            raise ValueError("reviewed output import audio binding differs")


def _assessment_document(
    *,
    equivalence: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    evidence = equivalence["document"]
    stitch = candidate["stitch"]
    assets = []
    for role in _PRIMARY_ROLES:
        artifact = stitch["artifacts"][role]
        assets.append(
            {
                "candidate_role": role,
                **_EXPECTED_SOURCE_ROLES[role],
                "audio_sha256": artifact["sha256"],
                "pcm24_int32_sequence_sha256": artifact[
                    "pcm24_int32_sequence_sha256"
                ],
                "geometry": deepcopy(artifact["geometry"]),
                "shape": "leaf",
                "origin": "derived",
            }
        )
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "review_equivalence_report_sha256": equivalence["sha256"],
            "review_equivalence_document_sha256": evidence["document_sha256"],
            "candidate_package_report_sha256": candidate["sha256"],
            "candidate_package_document_sha256": candidate["document"][
                "document_sha256"
            ],
            "candidate_stitch_report_sha256": evidence["bindings"][
                "candidate_stitch_report_sha256"
            ],
            "candidate_stitch_document_sha256": stitch["document_sha256"],
            "source_audio_sha256": stitch["artifacts"]["source"]["sha256"],
            "review_package_commitment": candidate["document"]["bindings"][
                "review_package_commitment"
            ],
        },
        "clock": deepcopy(stitch["clock"]),
        "reviewed_assets": assets,
        "diagnostic_assets_not_proposed_for_import": [
            {
                "candidate_role": "reconstruction",
                "audio_sha256": stitch["artifacts"]["reconstruction"]["sha256"],
                "reason": "timing_and_sum_diagnostic_not_an_independent_stem",
            }
        ],
        "future_import_contract": {
            "target": "fresh_or_existing_prepared_single_mix_source_project",
            "required_parent_role": "mix",
            "parent_source_sha256_must_match": stitch["artifacts"]["source"][
                "sha256"
            ],
            "original_mix_retained": True,
            "generated_assets_copied_into_project_immutably": True,
            "external_path_dependencies_permitted": False,
            "derived_receipt_required_per_asset": True,
            "append_only_source_graph_revision_required": True,
            "refinement_coverage": "complete",
            "initial_activation_mode": "unchanged",
            "separate_reviewed_activation_required": True,
            "automatic_activation_permitted": False,
            "rollback_to_original_mix_required": True,
        },
        "assessment": {
            "full_song_roles_reviewed_useful": True,
            "all_boundaries_reviewed": True,
            "alignment_gate_passed": True,
            "sample_equivalence_gate_passed": True,
            "two_primary_stems_available": True,
            "technical_import_contract_implementation_eligible": True,
        },
        "readiness": {
            "reviewed_output_import_assessment_complete": True,
            "private_import_implementation_eligible": True,
            "private_import_implementation_complete": False,
            "private_output_import_permitted": False,
            "source_graph_activation_permitted": False,
            "product_integration_permitted": False,
            "public_release_permitted": False,
        },
        "next_action": "implement_separate_private_reviewed_output_importer",
        "permissions": dict(_PERMISSIONS),
        "effects": {
            "assessment_record_created": True,
            "audio_created_or_mutated": False,
            "candidate_accepted_or_selected": False,
            "product_contract_mutated": False,
            "source_graph_mutated": False,
        },
        "limitations": [
            "This assessment is not an import and creates no prepared project or source-graph revision.",
            "Instrumental is proposed as canonical role other with declared role instrumental because instrumental is not a prepared source role.",
            "The reconstruction remains diagnostic and must not be imported as a third independent stem.",
            "One reviewed private song does not establish general separator accuracy or public readiness.",
            "Simple, Studio, TUI, public CLI, downloads and publication remain disabled for separation.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)
    return document


__all__: tuple[str, ...] = ()
