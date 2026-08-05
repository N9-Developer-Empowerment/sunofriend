"""Seal the evidence-backed design for a private separation route.

This module turns a verified multi-song private-pilot coverage ledger into a
path-free design contract.  It does not execute a model, expose a product
entry point, create audio or make private separation output discoverable by
Simple, Studio, the TUI, the CLI or the source graph.
"""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256
from ._separation_full_song_executor import _require_private_directory
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
    _write_json_exclusive,
)
from ._separation_multi_song_private_pilot_coverage import (
    POLICY_ID as COVERAGE_POLICY_ID,
    SCHEMA as COVERAGE_SCHEMA,
    STATUS as COVERAGE_STATUS,
)


SCHEMA = "sunofriend.private-separation-route-design.v1"
STATUS = "private_only_integration_design_complete_no_activation"
POLICY_ID = "reviewed-private-separation-route-design-v1"
REPORT_NAME = "private-separation-route-design.json"
_ROLES = ("vocals", "instrumental", "reconstruction")
_FALSE_PERMISSIONS = {
    "additional_model_run": False,
    "automatic_selection": False,
    "checkpoint_distribution": False,
    "private_route_execution_available": False,
    "product_route_permitted": False,
    "publication_permitted": False,
    "simple_mode_available": False,
    "source_graph_activation": False,
    "studio_import_available": False,
    "tui_route_available": False,
}
_EFFECTS = {
    "audio_created_or_mutated": False,
    "coverage_evidence_mutated": False,
    "design_record_created": True,
    "human_review_completed_or_mutated": False,
    "model_run": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "separator_accepted": False,
    "separator_selected": False,
    "source_graph_mutated": False,
}
_COVERAGE_FALSE_PERMISSIONS = {
    "additional_model_run": False,
    "automatic_selection": False,
    "product_route_permitted": False,
    "publication_permitted": False,
    "simple_mode_available": False,
    "source_graph_activation": False,
    "studio_import_available": False,
    "tui_route_available": False,
}
_COVERAGE_EFFECTS = {
    "audio_created_or_mutated": False,
    "coverage_report_created": True,
    "human_review_completed_or_mutated": False,
    "model_run": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "separator_accepted": False,
    "separator_selected": False,
    "source_graph_mutated": False,
}
_COVERAGE_INTERPRETATION = {
    "two_distinct_sources_are_general_separator_acceptance": False,
    "useful_full_song_ratings_are_ground_truth_accuracy": False,
    "boundary_counts_are_a_quality_score": False,
    "inferential_statistics_permitted_for_this_small_nonrandom_set": False,
    "handoff_completion_is_product_integration": False,
    "separator_selected_or_accepted": False,
}


def _build_private_separation_route_design(
    coverage_report_path: str | Path,
    *,
    out: str | Path,
) -> dict[str, Any]:
    """Verify the evidence checkpoint and write one non-activating design."""

    output = Path(out).expanduser().absolute()
    if output.name != REPORT_NAME:
        raise ValueError(f"private separation route design filename must be {REPORT_NAME}")
    if os.path.lexists(output):
        raise FileExistsError(f"private separation route design exists: {output}")
    if not os.path.lexists(output.parent):
        output.parent.mkdir(parents=True, mode=0o700)
        output.parent.chmod(0o700)
    _require_private_directory(output.parent, "private separation route design root")

    coverage = _load_verified_coverage(coverage_report_path)
    if output == coverage["path"]:
        raise ValueError("private separation route design overlaps coverage evidence")
    document = _design_document(coverage)
    document["document_sha256"] = _document_sha256(document)

    rechecked = _load_verified_coverage(coverage_report_path)
    if (
        rechecked["sha256"] != coverage["sha256"]
        or rechecked["document"]["document_sha256"]
        != coverage["document"]["document_sha256"]
    ):
        raise ValueError("private separation coverage changed")
    _write_json_exclusive(output, document)
    return {**document, "report": str(output)}


def _load_verified_coverage(value: str | Path) -> dict[str, Any]:
    snapshot = _load_private_json_snapshot(
        value,
        "multi-song private separation coverage",
    )
    document = snapshot["document"]
    coverage = _mapping(document.get("coverage"), "coverage summary")
    checkpoint = _mapping(
        document.get("private_evaluation_checkpoint"),
        "private evaluation checkpoint",
    )
    cases = document.get("cases")
    if (
        snapshot["path"].name
        != "private-separation-multi-song-private-pilot-coverage.json"
        or document.get("schema") != COVERAGE_SCHEMA
        or document.get("status") != COVERAGE_STATUS
        or document.get("evidence_scope") != "private_development_only"
        or document.get("policy_id") != COVERAGE_POLICY_ID
        or document.get("document_sha256") != _document_sha256(document)
        or document.get("permissions") != _COVERAGE_FALSE_PERMISSIONS
        or document.get("effects") != _COVERAGE_EFFECTS
        or document.get("interpretation") != _COVERAGE_INTERPRETATION
        or not isinstance(cases, list)
    ):
        raise ValueError("multi-song private separation coverage differs")

    _validate_coverage_summary(coverage, cases=cases)
    if checkpoint != {
        "two_distinct_source_evidence_checkpoint_met": True,
        "minimum_song_disjoint_pilots_before_private_route_design": 2,
        "private_route_design_checkpoint_met": True,
        "next_action": "assess_a_separately_bounded_private_only_integration_design",
    }:
        raise ValueError("private separation route design checkpoint is not met")
    return snapshot


def _validate_coverage_summary(
    coverage: Mapping[str, Any],
    *,
    cases: list[Any],
) -> None:
    required_true = (
        "all_source_hashes_distinct",
        "all_song_disjoint_pilots_automatic_chain_verified",
        "all_song_disjoint_pilots_full_song_reviewed",
        "all_song_disjoint_pilots_full_song_roles_useful",
        "all_song_disjoint_pilots_two_stem_handoff_complete",
    )
    pilot_count = _positive_int(
        coverage.get("song_disjoint_pilot_count"),
        "song-disjoint pilot count",
    )
    reference_count = _positive_int(
        coverage.get("reference_case_count"),
        "reference case count",
    )
    source_count = _positive_int(
        coverage.get("distinct_source_count"),
        "distinct source count",
    )
    boundary_count = _positive_int(
        coverage.get("reviewed_song_disjoint_boundary_count"),
        "reviewed boundary count",
    )
    judgement_count = _positive_int(
        coverage.get("reviewed_role_boundary_judgement_count"),
        "reviewed role-boundary judgement count",
    )
    totals = _mapping(
        coverage.get("boundary_rating_totals"),
        "boundary rating totals",
    )
    if (
        set(coverage)
        != {
            "reference_case_count",
            "song_disjoint_pilot_count",
            "distinct_source_count",
            *required_true,
            "reviewed_song_disjoint_boundary_count",
            "reviewed_role_boundary_judgement_count",
            "boundary_rating_totals",
        }
        or reference_count != 1
        or pilot_count < 2
        or source_count != reference_count + pilot_count
        or any(coverage.get(key) is not True for key in required_true)
        or judgement_count != boundary_count * len(_ROLES)
        or set(totals) != {"audible_join", "cannot_tell", "clean"}
        or any(
            isinstance(totals.get(key), bool)
            or not isinstance(totals.get(key), int)
            or totals[key] < 0
            for key in totals
        )
        or sum(totals.values()) != judgement_count
        or len(cases) != source_count
    ):
        raise ValueError("multi-song private separation coverage summary differs")

    references = [case for case in cases if _case_kind(case) == "pragmatic_reference"]
    pilots = [
        case for case in cases if _case_kind(case) == "reviewed_song_disjoint_pilot"
    ]
    if len(references) != 1 or len(pilots) != pilot_count:
        raise ValueError("multi-song private separation cases differ")
    source_hashes = [_source_hash(case) for case in cases]
    track_ids: list[str] = []
    derived_boundaries = 0
    derived_audible = 0
    derived_uncertain = 0
    for case in pilots:
        if (
            case.get("exact_two_stem_handoff_complete") is not True
            or case.get("audio_sample_values_changed_in_handoff") is not False
            or case.get("full_song_ratings")
            != {role: "useful" for role in _ROLES}
        ):
            raise ValueError("reviewed private pilot case differs")
        boundary_total = _positive_int(
            case.get("reviewed_boundary_count"),
            "pilot reviewed boundary count",
        )
        derived_boundaries += boundary_total
        for key, label in (
            ("audible_join_boundaries_by_role", "audible join boundaries"),
            ("cannot_tell_boundaries_by_role", "uncertain boundaries"),
        ):
            by_role = _mapping(case.get(key), label)
            if set(by_role) != set(_ROLES):
                raise ValueError("reviewed private pilot boundary evidence differs")
            for role in _ROLES:
                indexes = by_role[role]
                if (
                    not isinstance(indexes, list)
                    or indexes != sorted(set(indexes))
                    or any(
                        isinstance(item, bool)
                        or not isinstance(item, int)
                        or item < 1
                        or item > boundary_total
                        for item in indexes
                    )
                ):
                    raise ValueError("reviewed private pilot boundary evidence differs")
                if key == "audible_join_boundaries_by_role":
                    derived_audible += len(indexes)
                else:
                    derived_uncertain += len(indexes)
        track_id = case.get("track_id")
        if not isinstance(track_id, str) or not track_id.strip():
            raise ValueError("reviewed private pilot track identity differs")
        track_ids.append(track_id)
    if (
        len(set(source_hashes)) != len(source_hashes)
        or len(set(track_ids)) != len(track_ids)
        or derived_boundaries != boundary_count
        or derived_audible != totals["audible_join"]
        or derived_uncertain != totals["cannot_tell"]
        or judgement_count - derived_audible - derived_uncertain != totals["clean"]
    ):
        raise ValueError("multi-song private separation case totals differ")


def _design_document(coverage: Mapping[str, Any]) -> dict[str, Any]:
    source = coverage["document"]
    summary = source["coverage"]
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            "coverage_report_sha256": coverage["sha256"],
            "coverage_document_sha256": source["document_sha256"],
        },
        "evidence_checkpoint": {
            "reviewed_song_disjoint_pilot_count": summary[
                "song_disjoint_pilot_count"
            ],
            "distinct_source_count_including_reference": summary[
                "distinct_source_count"
            ],
            "reviewed_boundary_count": summary[
                "reviewed_song_disjoint_boundary_count"
            ],
            "reviewed_role_boundary_judgement_count": summary[
                "reviewed_role_boundary_judgement_count"
            ],
            "all_full_song_roles_useful": summary[
                "all_song_disjoint_pilots_full_song_roles_useful"
            ],
            "all_two_stem_handoffs_complete": summary[
                "all_song_disjoint_pilots_two_stem_handoff_complete"
            ],
            "private_route_design_checkpoint_met": True,
        },
        "route_boundary": {
            "availability": "design_only",
            "audience": "private_local_developer_evaluation",
            "invocation": "future_explicit_opt_in_only",
            "network": "offline_after_separately_authorized_local_installation",
            "source": "one_locally_authorized_audio_asset_per_request",
            "canonical_audio": "pcm24_wav_44100_hz_stereo",
            "backend": "one_explicitly_configured_private_evaluation_checkpoint",
            "primary_outputs": ["vocals", "instrumental"],
            "diagnostic_outputs": ["reconstruction"],
            "output_state": "unreviewed_private_staging",
            "fresh_owner_only_output_required": True,
            "overwrite_permitted": False,
            "complete_song_and_boundary_review_required_before_handoff": True,
            "reviewed_output_import_is_a_separate_future_explicit_action": True,
        },
        "execution_guarantees_required_before_implementation": {
            "source_snapshot_hash_bound": True,
            "checkpoint_identity_hash_bound": True,
            "request_bound_chunking_and_resume": True,
            "bounded_cpu_memory_disk_and_runtime": True,
            "no_implicit_download_or_network": True,
            "no_unreviewed_source_graph_mutation": True,
            "no_automatic_candidate_selection": True,
            "no_silent_fallback_to_another_backend": True,
            "incomplete_attempts_preserved_as_diagnostics_only": True,
            "reconstruction_timing_checks_do_not_claim_separator_accuracy": True,
        },
        "mode_isolation": {
            "simple_can_discover_output": False,
            "studio_can_discover_output": False,
            "tui_can_execute_route": False,
            "public_cli_can_execute_route": False,
            "source_graph_can_import_output": False,
            "download_pack_can_include_output": False,
        },
        "staged_implementation": [
            {
                "stage": 1,
                "name": "sealed_backend_adapter_contract",
                "allowed_effect": "validate_configuration_and_build_an_execution_request_only",
                "model_run": False,
                "product_activation": False,
            },
            {
                "stage": 2,
                "name": "developer_only_private_execution",
                "allowed_effect": "create_unreviewed_owner_only_staging_audio",
                "model_run": True,
                "product_activation": False,
            },
            {
                "stage": 3,
                "name": "mandatory_private_listening_review",
                "allowed_effect": "bind_human_feedback_to_exact_staging_audio",
                "model_run": False,
                "product_activation": False,
            },
            {
                "stage": 4,
                "name": "separate_reviewed_import_assessment",
                "allowed_effect": "assess_but_not_enable_source_graph_import",
                "model_run": False,
                "product_activation": False,
            },
        ],
        "readiness": {
            "evidence_checkpoint_verified": True,
            "private_only_route_design_complete": True,
            "next_stage": "implement_stage_1_sealed_backend_adapter_contract",
            "private_execution_implemented": False,
            "private_execution_available": False,
            "product_integration_assessed": False,
            "product_integration_permitted": False,
            "public_release_permitted": False,
        },
        "permissions": deepcopy(_FALSE_PERMISSIONS),
        "effects": deepcopy(_EFFECTS),
        "limitations": [
            "The evidence is a small non-random private set reviewed by one listener and is not general separator accuracy.",
            "The design does not select or accept a separator or grant checkpoint redistribution rights.",
            "The design does not install dependencies, execute a model or create audio.",
            "Private execution still requires a separate fail-closed adapter and explicit local authorization.",
            "Simple, Studio, TUI, CLI, source-graph, download and public routes remain unchanged and disabled for separation.",
        ],
    }


def _case_kind(value: Any) -> str:
    if not isinstance(value, Mapping):
        raise ValueError("multi-song private separation case differs")
    kind = value.get("case_kind")
    if kind not in {"pragmatic_reference", "reviewed_song_disjoint_pilot"}:
        raise ValueError("multi-song private separation case differs")
    return kind


def _source_hash(value: Mapping[str, Any]) -> str:
    result = value.get("source_audio_sha256")
    if (
        not isinstance(result, str)
        or len(result) != 64
        or any(character not in "0123456789abcdef" for character in result)
    ):
        raise ValueError("multi-song private separation source hash differs")
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} differs")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} differs")
    return value


__all__: tuple[str, ...] = ()
