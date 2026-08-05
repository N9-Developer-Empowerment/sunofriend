"""Prepare a non-executable handoff for a bounded private separation pilot.

The handoff is deliberately an evidence-only design record.  It re-derives the
complete final-readiness result from the human exports and immutable evidence
chain, binds every independently ready candidate in canonical order and stops
before a new source, worker, model or product route can be introduced.
"""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path, PurePath
import re
import tempfile
from typing import Any, Mapping, Sequence

from ._separation_authorised_excerpt import _document_sha256
from ._separation_candidate_followup_remediation_executor import (
    CANDIDATE_REPORT_NAME,
    CANDIDATES_DIRECTORY,
    REPORT_NAME as EXECUTION_REPORT_NAME,
    SCHEMA as EXECUTION_SCHEMA,
    STATUS_COMPLETE as EXECUTION_STATUS,
)
from ._separation_candidate_followup_variant_final_readiness_reassessment import (
    SCHEMA as READINESS_SCHEMA,
    STATUS as READINESS_STATUS,
    _reassess_private_candidate_followup_variant_final_readiness,
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
    "private-pilot-handoff-plan.v1"
)
STATUS = "private_pilot_handoff_planned_no_execution"
POLICY_ID = "accepted-candidate-reference-only-private-pilot-handoff-v1"
REPORT_NAME = (
    "private-separation-candidate-followup-variant-private-pilot-handoff-plan.json"
)
_CANDIDATE_SCHEMA = (
    "sunofriend.private-separation-candidate-followup-remediation-candidates.v1"
)
_CANDIDATE_STATUS = "candidate_variants_complete_review_required"
_ROLES = ("vocals", "instrumental", "reconstruction")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FALSE_EFFECTS = {
    "audio_created_or_mutated": False,
    "candidate_selected": False,
    "handoff_plan_created": True,
    "model_run": False,
    "pilot_execution_started": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "review_evidence_mutated": False,
    "source_graph_mutated": False,
}


def _prepare_private_candidate_followup_variant_pilot_handoff(
    final_readiness_result_path: str | Path,
    *,
    final_acceptance_result_path: str | Path,
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
    """Bind all ready reference candidates without authorising pilot execution."""

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
    if output.name != REPORT_NAME:
        raise ValueError(f"private pilot handoff filename must be {REPORT_NAME}")
    _require_private_directory(output.parent, "private pilot handoff parent")
    if os.path.lexists(output):
        raise FileExistsError(f"private pilot handoff exists: {output}")

    verification_kwargs = {
        "final_acceptance_result_path": final_acceptance_result_path,
        "final_acceptance_review_export_paths": acceptance_exports,
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
    derived = _derive_final_readiness_result(verification_kwargs)
    supplied = _load_private_json_snapshot(
        final_readiness_result_path, "private final readiness reassessment"
    )
    readiness = supplied["document"]
    if supplied["sha256"] != derived["sha256"] or readiness != derived["document"]:
        raise ValueError("private final readiness reassessment differs")
    if (
        readiness.get("schema") != READINESS_SCHEMA
        or readiness.get("status") != READINESS_STATUS
        or readiness.get("document_sha256") != _document_sha256(readiness)
        or readiness.get("permissions") != _FALSE_PERMISSIONS
    ):
        raise ValueError("private final readiness reassessment differs")

    ready_ids = list(readiness["private_pilot_readiness"]["ready_variant_ids"])
    if (
        not ready_ids
        or readiness["private_pilot_readiness"].get("bounded_private_pilot_available")
        is not True
    ):
        raise ValueError("no candidate is ready for a bounded private pilot")
    if len(ready_ids) != len(set(ready_ids)):
        raise ValueError("private pilot ready candidate inventory differs")

    variant_root = Path(variant_execution_dir).expanduser().absolute()
    candidate_snapshot = _load_private_json_snapshot(
        variant_root / CANDIDATES_DIRECTORY / CANDIDATE_REPORT_NAME,
        "private follow-up candidate variants",
    )
    candidates = candidate_snapshot["document"]
    execution_snapshot = _load_private_json_snapshot(
        variant_root / EXECUTION_REPORT_NAME,
        "private follow-up remediation execution",
    )
    execution = execution_snapshot["document"]
    _require_candidate_documents(
        candidates,
        candidate_sha256=candidate_snapshot["sha256"],
        execution=execution,
    )

    candidate_ids = [item["variant_id"] for item in candidates["variants"]]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("private pilot candidate inventory differs")
    ready_set = set(ready_ids)
    canonical_ready_ids = [item for item in candidate_ids if item in ready_set]
    if canonical_ready_ids != ready_ids or any(
        item not in candidate_ids for item in ready_ids
    ):
        raise ValueError("private pilot ready candidate order differs")

    readiness_by_id = {
        item["variant_id"]: item for item in readiness["variant_evidence"]
    }
    candidate_by_id = {item["variant_id"]: item for item in candidates["variants"]}
    handoff_variants = [
        _handoff_variant(
            variant_id,
            index=index,
            candidate=candidate_by_id[variant_id],
            readiness=readiness_by_id[variant_id],
            clock=candidates["clock"],
        )
        for index, variant_id in enumerate(ready_ids, start=1)
    ]

    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "candidate_identity": "ready_reference_candidates_not_ranked_or_selected",
        "bindings": {
            "final_readiness_result_sha256": supplied["sha256"],
            "final_readiness_result_document_sha256": readiness["document_sha256"],
            "final_acceptance_result_sha256": readiness["bindings"][
                "final_acceptance_result_sha256"
            ],
            "variant_execution_report_sha256": execution_snapshot["sha256"],
            "variant_execution_document_sha256": execution["document_sha256"],
            "candidate_report_sha256": candidate_snapshot["sha256"],
            "candidate_document_sha256": candidates["document_sha256"],
        },
        "clock": deepcopy(candidates["clock"]),
        "ready_variant_ids": ready_ids,
        "handoff_variants": handoff_variants,
        "private_pilot_handoff": {
            "handoff_plan_complete": True,
            "ready_variant_count": len(ready_ids),
            "all_ready_variants_included": True,
            "caller_subset_allowed": False,
            "caller_preferred_order_allowed": False,
            "variant_selected": False,
            "reference_candidate_audio_bound_by_hash": True,
            "reference_candidate_audio_copied": False,
            "new_source_bound": False,
            "new_track_id_bound": False,
            "pilot_request_schema_implemented": False,
            "pilot_execution_authorised": False,
            "model_or_worker_execution_permitted": False,
            "reusable_separator_strategy_established": False,
            "separator_accepted_as_product_default": False,
            "product_route_enabled": False,
            "publication_ready": False,
        },
        "required_future_request": {
            "explicit_authorised_local_source": True,
            "immutable_source_and_clock_binding": True,
            "fresh_owner_only_output_root": True,
            "exact_checkpoint_runtime_and_machine_binding": True,
            "bounded_resource_and_failure_policy": True,
            "all_ready_reference_candidates_retained_without_preference": True,
            "fresh_track_specific_human_review": True,
            "automatic_generalisation_from_this_song": False,
        },
        "publication_boundary": deepcopy(readiness["publication_boundary"]),
        "next_action": "design_source_bound_song_disjoint_private_pilot_request",
        "interpretation": {
            "this_is_a_handoff_design_record": True,
            "this_is_a_pilot_execution_request": False,
            "candidate_artifacts_are_reference_evidence_only": True,
            "accepted_candidate_means_reusable_strategy": False,
            "package_order_is_preference": False,
            "automatic_winner_selected": False,
            "private_pilot_handoff_is_product_activation": False,
            "private_pilot_handoff_is_publication_permission": False,
        },
        "permissions": dict(_FALSE_PERMISSIONS),
        "effects": dict(_FALSE_EFFECTS),
        "limitations": [
            "This plan creates no audio, copies no candidate and starts no model or worker.",
            "The accepted variants are exact song-specific reference evidence, not proven reusable separator strategies.",
            "A later pilot request must bind one separately authorised local source and retain every ready reference candidate without caller preference.",
            "Fresh track-specific listening is required; current acceptance cannot be transferred to another song.",
            "No Simple, Studio, CLI, TUI, source-graph or publication route is enabled.",
            "Keep every evidence tree quiescent because JSON and WAV inputs are not one atomic snapshot.",
        ],
    }
    result["document_sha256"] = _document_sha256(result)

    _require_output_disjoint_from_inputs(
        output,
        evidence_roots=(
            Path(review_package_dir).expanduser().absolute(),
            Path(alignment_package_dir).expanduser().absolute(),
            Path(full_song_review_package_dir).expanduser().absolute(),
            Path(variant_review_package_dir).expanduser().absolute(),
            Path(execution_dir).expanduser().absolute(),
            Path(v2_execution_dir).expanduser().absolute(),
            variant_root,
            Path(stitch_package_dir).expanduser().absolute(),
        ),
        evidence_paths=(
            supplied["path"],
            Path(final_acceptance_result_path).expanduser().absolute(),
            Path(readiness_result_path).expanduser().absolute(),
            Path(full_song_review_result_path).expanduser().absolute(),
            Path(variant_review_result_path).expanduser().absolute(),
            Path(variant_reviewed_export_path).expanduser().absolute(),
            Path(plan_path).expanduser().absolute(),
            execution_snapshot["path"],
            candidate_snapshot["path"],
            *(Path(path).expanduser().absolute() for path in acceptance_exports),
            *(Path(path).expanduser().absolute() for path in full_song_exports),
        ),
    )

    published = False
    try:
        _write_json_exclusive(output, result)
        published = True
        current_derived = _derive_final_readiness_result(verification_kwargs)
        current_supplied = _load_private_json_snapshot(
            supplied["path"], "private final readiness reassessment"
        )
        current_execution = _load_private_json_snapshot(
            execution_snapshot["path"], "private follow-up remediation execution"
        )
        current_candidates = _load_private_json_snapshot(
            candidate_snapshot["path"], "private follow-up candidate variants"
        )
        if (
            current_derived["sha256"] != derived["sha256"]
            or current_derived["document"] != derived["document"]
            or current_supplied["sha256"] != supplied["sha256"]
            or current_supplied["document"] != readiness
            or current_execution["sha256"] != execution_snapshot["sha256"]
            or current_execution["document"] != execution
            or current_candidates["sha256"] != candidate_snapshot["sha256"]
            or current_candidates["document"] != candidates
        ):
            raise ValueError("private pilot handoff evidence changed")
    except BaseException:
        if published:
            try:
                output.unlink()
            except FileNotFoundError:
                pass
        raise
    return {**result, "report": str(output)}


def _derive_final_readiness_result(
    verification_kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    arguments = dict(verification_kwargs)
    final_acceptance_result_path = arguments.pop("final_acceptance_result_path")
    with tempfile.TemporaryDirectory(
        prefix="sunofriend-private-pilot-handoff-readiness-gate-"
    ) as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        result_path = root / "readiness.json"
        _reassess_private_candidate_followup_variant_final_readiness(
            final_acceptance_result_path,
            out=result_path,
            **arguments,
        )
        return _load_private_json_snapshot(
            result_path, "derived private final readiness reassessment"
        )


def _require_candidate_documents(
    candidates: Mapping[str, Any],
    *,
    candidate_sha256: str,
    execution: Mapping[str, Any],
) -> None:
    variants = candidates.get("variants")
    if (
        candidates.get("schema") != _CANDIDATE_SCHEMA
        or candidates.get("status") != _CANDIDATE_STATUS
        or candidates.get("document_sha256") != _document_sha256(candidates)
        or candidates.get("permissions") != _FALSE_PERMISSIONS
        or not isinstance(candidates.get("clock"), Mapping)
        or not isinstance(variants, list)
        or not variants
        or execution.get("schema") != EXECUTION_SCHEMA
        or execution.get("status") != EXECUTION_STATUS
        or execution.get("document_sha256") != _document_sha256(execution)
        or execution.get("permissions") != _FALSE_PERMISSIONS
        or execution.get("bindings", {}).get("candidate_report_sha256")
        != candidate_sha256
        or execution.get("bindings", {}).get("candidate_document_sha256")
        != candidates.get("document_sha256")
    ):
        raise ValueError("private pilot candidate evidence differs")


def _handoff_variant(
    variant_id: str,
    *,
    index: int,
    candidate: Mapping[str, Any],
    readiness: Mapping[str, Any],
    clock: Mapping[str, Any],
) -> dict[str, Any]:
    if (
        readiness.get("readiness", {}).get("bounded_private_pilot_ready") is not True
        or readiness.get("evidence", {}).get("explicit_private_pilot_acceptance")
        is not True
    ):
        raise ValueError("private pilot ready candidate evidence differs")
    artifacts = candidate.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != set(_ROLES):
        raise ValueError("private pilot candidate artifact inventory differs")
    definition = candidate.get("definition")
    if (
        candidate.get("selected") is not False
        or not isinstance(definition, Mapping)
        or definition.get("variant_id") != variant_id
    ):
        raise ValueError("private pilot candidate definition differs")
    return {
        "canonical_index": index,
        "variant_id": variant_id,
        "reference_candidate_definition": _candidate_definition_projection(definition),
        "reference_artifacts": {
            role: _artifact_projection(artifacts[role], clock=clock) for role in _ROLES
        },
        "review_binding": deepcopy(dict(readiness["bindings"])),
        "readiness_evidence": deepcopy(dict(readiness["evidence"])),
        "pilot_boundary": {
            "reference_evidence_only": True,
            "candidate_selected": False,
            "new_source_bound": False,
            "model_execution_permitted": False,
            "reusable_separator_strategy_established": False,
            "product_route_enabled": False,
            "publication_ready": False,
        },
    }


def _artifact_projection(
    claim: Mapping[str, Any], *, clock: Mapping[str, Any]
) -> dict[str, Any]:
    path = claim.get("path")
    geometry = claim.get("geometry")
    if (
        not isinstance(path, str)
        or not path
        or path in {".", ".."}
        or "/" in path
        or "\\" in path
        or "\x00" in path
        or PurePath(path).is_absolute()
        or len(PurePath(path).parts) != 1
        or not isinstance(geometry, Mapping)
        or geometry.get("sample_rate") != clock.get("sample_rate")
        or geometry.get("channels") != clock.get("channels")
        or geometry.get("frames") != clock.get("frames")
        or geometry.get("sample_width_bytes") != 3
        or type(claim.get("bytes")) is not int
        or claim["bytes"] <= 0
        or not _valid_sha256(claim.get("sha256"))
        or not _valid_sha256(claim.get("pcm24_int32_sequence_sha256"))
    ):
        raise ValueError("private pilot candidate audio claim differs")
    return {
        "sha256": claim["sha256"],
        "bytes": claim["bytes"],
        "pcm24_int32_sequence_sha256": claim["pcm24_int32_sequence_sha256"],
        "geometry": {
            "sample_rate": geometry["sample_rate"],
            "channels": geometry["channels"],
            "frames": geometry["frames"],
            "sample_width_bytes": geometry["sample_width_bytes"],
        },
    }


def _candidate_definition_projection(definition: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "variant_id",
        "reinference_source",
        "failed_edge_source",
        "failed_edge_blend_frames",
    }
    if (
        set(definition) != expected
        or not isinstance(definition.get("variant_id"), str)
        or not isinstance(definition.get("reinference_source"), str)
        or not isinstance(definition.get("failed_edge_source"), str)
        or type(definition.get("failed_edge_blend_frames")) is not int
        or definition["failed_edge_blend_frames"] < 1
    ):
        raise ValueError("private pilot candidate definition differs")
    return {name: definition[name] for name in sorted(expected)}


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


__all__: tuple[str, ...] = ()
