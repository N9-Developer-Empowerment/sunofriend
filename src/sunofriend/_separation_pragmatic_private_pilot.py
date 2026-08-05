"""Authorize one evidence-bound separation candidate for a bounded private pilot.

This policy deliberately separates microscopic diagnostic gates from whole-song
musical utility.  It preserves the immutable blind-review result, but allows an
explicit human absolute-quality assessment to advance the unchanged follow-up
control when later variants showed no audible advantage.  It does not publish,
activate, or expose separation in Simple or Studio mode.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import os
from pathlib import Path
from typing import Any, Mapping

from ._separation_authorised_excerpt import _document_sha256
from ._separation_candidate_followup_overlap_add_plan import (
    _validated_failed_variant_evidence,
)
from ._separation_candidate_followup_variant_full_song_review import (
    _verified_exact_variant_result,
)
from ._separation_candidate_followup_variant_review import (
    _input_bindings,
    _load_verified_variant_inputs,
)
from ._separation_full_song_executor import _require_private_directory
from ._separation_full_song_join_remediation_executor_v2 import (
    _require_output_disjoint_from_inputs,
)
from ._separation_full_song_join_remediation_review_result import (
    _load_private_json_snapshot,
    _write_json_exclusive,
)


SCHEMA = "sunofriend.private-separation-pragmatic-private-pilot.v1"
STATUS = "bounded_private_pilot_authorized_with_known_minor_join_limitations"
POLICY_ID = "whole-song-utility-over-microscopic-edge-v1"
REPORT_NAME = "private-separation-pragmatic-private-pilot.json"
_QUALITY_CHOICES = ("good", "good_enough", "good_or_good_enough")
_ROLES = ("vocals", "instrumental", "reconstruction")
_PERMISSIONS = {
    "bounded_private_pilot_use": True,
    "product_route_permitted": False,
    "publication_permitted": False,
    "simple_mode_available": False,
    "source_graph_activation": False,
    "studio_import_available": False,
}
_EFFECTS = {
    "audio_created_or_mutated": False,
    "candidate_selected_for_bounded_private_pilot": True,
    "model_run": False,
    "product_contract_mutated": False,
    "publication_state_mutated": False,
    "review_evidence_mutated": False,
    "source_graph_mutated": False,
}


def _authorize_pragmatic_private_pilot(
    variant_review_result_path: str | Path,
    *,
    reviewed_export_path: str | Path,
    variant_review_package_dir: str | Path,
    plan_path: str | Path,
    execution_dir: str | Path,
    v2_execution_dir: str | Path,
    variant_execution_dir: str | Path,
    overall_audio_quality: str,
    listener_assessed_separator_accuracy: str,
    joins_generally_noticeable: bool,
    joins_detectable_when_cued_with_concentrated_headphones: bool,
    joins_reduce_musical_usefulness: bool,
    patch_edge_beat_ambiguity_present: bool,
    out: str | Path,
) -> dict[str, Any]:
    """Write one no-overwrite, evidence-bound private-pilot authorization."""

    output = Path(out).expanduser().absolute()
    if output.name != REPORT_NAME:
        raise ValueError(f"private pilot filename must be {REPORT_NAME}")
    if os.path.lexists(output):
        raise FileExistsError(f"private pilot report exists: {output}")
    if not output.parent.exists():
        output.parent.mkdir(parents=True, mode=0o700)
        output.parent.chmod(0o700)
    _require_private_directory(output.parent, "private pilot report root")

    package = Path(variant_review_package_dir).expanduser().absolute()
    _require_private_directory(package, "private variant review package")
    context = _load_verified_variant_inputs(
        plan_path,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
        variant_execution_dir=variant_execution_dir,
    )
    result = _verified_exact_variant_result(
        variant_review_result_path,
        reviewed_export_path=reviewed_export_path,
        variant_review_package_dir=package,
        plan_path=plan_path,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
        variant_execution_dir=variant_execution_dir,
    )
    known_variant_ids = [
        str(item["variant_id"])
        for item in context["plan"]["protocol"]["candidate_variants"]
    ]
    failed_variants = _validated_failed_variant_evidence(
        result, known_variant_ids=known_variant_ids
    )
    assessment = _validated_absolute_assessment(
        {
            "overall_audio_quality": overall_audio_quality,
            "listener_assessed_separator_accuracy": (
                listener_assessed_separator_accuracy
            ),
            "joins_generally_noticeable": joins_generally_noticeable,
            "joins_detectable_when_cued_with_concentrated_headphones": (
                joins_detectable_when_cued_with_concentrated_headphones
            ),
            "joins_reduce_musical_usefulness": joins_reduce_musical_usefulness,
            "patch_edge_beat_ambiguity_present": patch_edge_beat_ambiguity_present,
        }
    )
    review_summary = _validated_review_summary(result)
    _require_pragmatic_gate(assessment, review_summary=review_summary)

    candidate = context["inputs"]["candidate"]
    artifacts = candidate.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != set(_ROLES):
        raise ValueError("private follow-up control artifact inventory differs")
    selected_artifacts = {
        role: _path_free_artifact_binding(artifacts[role], role=role)
        for role in _ROLES
    }

    result_snapshot = _load_private_json_snapshot(
        variant_review_result_path, "private follow-up variant review result"
    )
    reviewed_export = Path(reviewed_export_path).expanduser().absolute()
    _require_output_disjoint_from_inputs(
        output,
        evidence_roots=(
            context["base_root"],
            context["v2_root"],
            context["variant_root"],
            package,
        ),
        evidence_paths=(
            result_snapshot["path"],
            reviewed_export,
            context["plan_snapshot"]["path"],
            context["execution_snapshot"]["path"],
            context["candidates_snapshot"]["path"],
            context["inputs"]["execution_snapshot"]["path"],
            context["inputs"]["candidate_snapshot"]["path"],
            context["inputs"]["v2_snapshot"]["path"],
        ),
    )

    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": "private_development_only",
        "policy_id": POLICY_ID,
        "bindings": {
            **_input_bindings(context),
            "variant_review_result_sha256": result_snapshot["sha256"],
            "variant_review_result_document_sha256": result["document_sha256"],
            "variant_review_export_sha256": result["bindings"][
                "review_export_sha256"
            ],
        },
        "human_absolute_assessment": assessment,
        "comparative_review_summary": review_summary,
        "historical_strict_gate": {
            "passed": False,
            "eligible_variant_ids": [],
            "failed_variants": failed_variants,
            "preserved_unchanged": True,
        },
        "pragmatic_private_pilot_gate": {
            "passed": True,
            "selected_candidate_identity": "followup_control",
            "selection_scope": "bounded_private_pilot_only",
            "basis": [
                "explicit whole-song quality and usefulness assessment passed",
                "joins are not generally noticeable and do not reduce musical usefulness",
                "no tested replacement variant was preferred over the follow-up control",
                "microscopic patch-edge ambiguity is retained as diagnostic evidence",
            ],
            "overlap_add_fallback_deferred": True,
            "new_model_run_required": False,
        },
        "selected_candidate": {
            "identity": "followup_control",
            "candidate_report_sha256": context["inputs"]["candidate_snapshot"][
                "sha256"
            ],
            "candidate_document_sha256": candidate["document_sha256"],
            "artifacts": selected_artifacts,
        },
        "readiness": {
            "bounded_private_pilot_ready": True,
            "whole_song_utility_gate_passed": True,
            "microscopic_edge_diagnostics_resolved": False,
            "ground_truth_separator_accuracy_established": False,
            "public_product_acceptance_complete": False,
            "publication_ready": False,
        },
        "interpretation": {
            "listener_assessment_is_ground_truth_accuracy": False,
            "strict_variant_gate_is_private_pilot_veto": False,
            "microscopic_edge_units_are_diagnostics": True,
            "normal_listening_and_musical_usefulness_drive_private_pilot": True,
            "followup_control_is_best_separator_proven": False,
            "followup_control_is_stable_available_pilot_candidate": True,
        },
        "permissions": dict(_PERMISSIONS),
        "effects": dict(_EFFECTS),
        "limitations": [
            "The listener-assessed separator accuracy is a holistic judgement, not ground truth measurement.",
            "Cued concentrated headphone listening can still reveal joins.",
            "Beat-coincident edges can make isolated artifact classification ambiguous.",
            "The strict blind-review choices remain unchanged and retain zero eligible replacement variants.",
            "This authorization is private and bounded; it does not enable Simple, Studio, public download or publication.",
            "No audio is copied or changed and no model is run by this command.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)

    rechecked_context = _load_verified_variant_inputs(
        plan_path,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
        variant_execution_dir=variant_execution_dir,
    )
    rechecked_result = _verified_exact_variant_result(
        variant_review_result_path,
        reviewed_export_path=reviewed_export_path,
        variant_review_package_dir=package,
        plan_path=plan_path,
        execution_dir=execution_dir,
        v2_execution_dir=v2_execution_dir,
        variant_execution_dir=variant_execution_dir,
    )
    if (
        _input_bindings(rechecked_context) != _input_bindings(context)
        or rechecked_result != result
    ):
        raise ValueError("private pilot evidence changed")

    _write_json_exclusive(output, document)
    return {
        **document,
        "report": str(output),
        "pilot_audio": {
            role: str(context["base_paths"][role]) for role in _ROLES
        },
    }


def _validated_absolute_assessment(raw: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "overall_audio_quality",
        "listener_assessed_separator_accuracy",
        "joins_generally_noticeable",
        "joins_detectable_when_cued_with_concentrated_headphones",
        "joins_reduce_musical_usefulness",
        "patch_edge_beat_ambiguity_present",
    }
    if set(raw) != expected:
        raise ValueError("private pilot absolute assessment fields differ")
    assessment = dict(raw)
    if (
        assessment["overall_audio_quality"] not in _QUALITY_CHOICES
        or assessment["listener_assessed_separator_accuracy"]
        not in _QUALITY_CHOICES
        or any(
            not isinstance(assessment[key], bool)
            for key in expected
            if key
            not in {
                "overall_audio_quality",
                "listener_assessed_separator_accuracy",
            }
        )
    ):
        raise ValueError("private pilot absolute assessment values differ")
    return assessment


def _validated_review_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    units = result.get("units")
    if not isinstance(units, list) or not units:
        raise ValueError("private pilot comparative units differ")
    counts = Counter(item.get("resolved_choice") for item in units)
    if any(not isinstance(choice, str) for choice in counts):
        raise ValueError("private pilot comparative choice differs")
    candidate_preference_count = sum(
        count
        for choice, count in counts.items()
        if choice not in {"equivalent", "neither", "followup_control_preferred"}
    )
    return {
        "reviewed_unit_count": len(units),
        "choice_counts": dict(sorted(counts.items())),
        "followup_control_preference_count": counts["followup_control_preferred"],
        "replacement_variant_preference_count": candidate_preference_count,
        "replacement_variant_showed_audible_advantage": (
            candidate_preference_count > 0
        ),
    }


def _require_pragmatic_gate(
    assessment: Mapping[str, Any], *, review_summary: Mapping[str, Any]
) -> None:
    if (
        assessment["overall_audio_quality"] not in _QUALITY_CHOICES
        or assessment["listener_assessed_separator_accuracy"]
        not in _QUALITY_CHOICES
        or assessment["joins_generally_noticeable"] is not False
        or assessment["joins_reduce_musical_usefulness"] is not False
        or review_summary["replacement_variant_preference_count"] != 0
        or review_summary["followup_control_preference_count"] < 1
    ):
        raise ValueError("pragmatic bounded private-pilot gate is not met")


def _path_free_artifact_binding(raw: Any, *, role: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"private follow-up control {role} artifact differs")
    geometry = raw.get("geometry")
    if (
        not isinstance(geometry, Mapping)
        or not isinstance(raw.get("sha256"), str)
        or not isinstance(raw.get("pcm24_int32_sequence_sha256"), str)
        or int(raw.get("bytes", 0)) <= 0
        or int(geometry.get("frames", 0)) <= 0
        or int(geometry.get("sample_rate", 0)) <= 0
    ):
        raise ValueError(f"private follow-up control {role} artifact differs")
    return {
        "role": role,
        "sha256": str(raw["sha256"]),
        "pcm24_int32_sequence_sha256": str(raw["pcm24_int32_sequence_sha256"]),
        "bytes": int(raw["bytes"]),
        "geometry": deepcopy(dict(geometry)),
    }


__all__: tuple[str, ...] = ()
