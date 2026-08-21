"""No-effects MusicFM feature-extraction plan for remix learning evidence."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .remix_feature_contract import validate_remix_operation_feature_manifest
from .remix_learning_contract import validate_remix_training_snapshot
from .remix_musicfm_fma import (
    MUSICFM_FMA_PROVIDER_ID,
    validate_musicfm_fma_admission_plan,
)
from .remix_musicfm_fma_evidence import (
    validate_musicfm_fma_readiness,
    validate_musicfm_fma_static_evidence,
)
from .remix_musicfm_fma_runtime import validate_musicfm_fma_runtime_plan
from .remix_musicfm_fma_runtime_resolution import (
    validate_musicfm_fma_runtime_resolution,
)
from .source_receipt import document_sha256


MUSICFM_REMIX_FEATURE_PLAN_SCHEMA = (
    "sunofriend.remix-musicfm-fma-feature-extraction-plan.v0"
)

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_CONTEXT_SECONDS = 2


def create_musicfm_remix_feature_plan(
    training_snapshot: Mapping[str, Any],
    operation_features: Mapping[str, Any],
    admission_plan: Mapping[str, Any],
    static_evidence: Mapping[str, Any],
    readiness: Mapping[str, Any],
    runtime_plan: Mapping[str, Any],
    runtime_resolution: Mapping[str, Any],
    *,
    resolver_report_bytes: bytes,
    repository_commit: str,
) -> dict[str, Any]:
    """Plan exact feature inputs while runtime and evidence gates stay closed."""

    checked = _validated_inputs(
        training_snapshot,
        operation_features,
        admission_plan,
        static_evidence,
        readiness,
        runtime_plan,
        runtime_resolution,
        resolver_report_bytes=resolver_report_bytes,
    )
    if not _COMMIT.fullmatch(str(repository_commit)):
        raise ValueError("repository_commit must be a full Git commit")
    document = _feature_plan_values(*checked, repository_commit=str(repository_commit))
    document["document_sha256"] = document_sha256(document)
    return validate_musicfm_remix_feature_plan(
        document,
        training_snapshot,
        operation_features,
        admission_plan,
        static_evidence,
        readiness,
        runtime_plan,
        runtime_resolution,
        resolver_report_bytes=resolver_report_bytes,
    )


def validate_musicfm_remix_feature_plan(
    feature_plan: Mapping[str, Any],
    training_snapshot: Mapping[str, Any],
    operation_features: Mapping[str, Any],
    admission_plan: Mapping[str, Any],
    static_evidence: Mapping[str, Any],
    readiness: Mapping[str, Any],
    runtime_plan: Mapping[str, Any],
    runtime_resolution: Mapping[str, Any],
    *,
    resolver_report_bytes: bytes,
) -> dict[str, Any]:
    checked = _validated_inputs(
        training_snapshot,
        operation_features,
        admission_plan,
        static_evidence,
        readiness,
        runtime_plan,
        runtime_resolution,
        resolver_report_bytes=resolver_report_bytes,
    )
    document = dict(feature_plan)
    if document.get("schema") != MUSICFM_REMIX_FEATURE_PLAN_SCHEMA:
        raise ValueError("unsupported MusicFM remix feature plan schema")
    supplied = document.get("document_sha256")
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if supplied != document_sha256(unsigned):
        raise ValueError("MusicFM remix feature plan document hash changed")
    repository_commit = str(document.get("repository_commit") or "")
    if not _COMMIT.fullmatch(repository_commit):
        raise ValueError("MusicFM remix feature plan commit changed")
    expected = _feature_plan_values(*checked, repository_commit=repository_commit)
    if unsigned != expected:
        raise ValueError("MusicFM remix feature plan evidence or authority changed")
    return document


def _validated_inputs(
    training_snapshot: Mapping[str, Any],
    operation_features: Mapping[str, Any],
    admission_plan: Mapping[str, Any],
    static_evidence: Mapping[str, Any],
    readiness: Mapping[str, Any],
    runtime_plan: Mapping[str, Any],
    runtime_resolution: Mapping[str, Any],
    *,
    resolver_report_bytes: bytes,
) -> tuple[dict[str, Any], ...]:
    snapshot = validate_remix_training_snapshot(training_snapshot)
    operation = validate_remix_operation_feature_manifest(operation_features, snapshot)
    admission = validate_musicfm_fma_admission_plan(admission_plan)
    static = validate_musicfm_fma_static_evidence(static_evidence, admission)
    ready = validate_musicfm_fma_readiness(readiness, admission, static)
    runtime = validate_musicfm_fma_runtime_plan(runtime_plan, admission, static, ready)
    resolution = validate_musicfm_fma_runtime_resolution(
        runtime_resolution,
        runtime,
        resolver_report_bytes=resolver_report_bytes,
    )
    return snapshot, operation, admission, static, ready, runtime, resolution


def _feature_plan_values(
    snapshot: Mapping[str, Any],
    operation: Mapping[str, Any],
    admission: Mapping[str, Any],
    static: Mapping[str, Any],
    readiness: Mapping[str, Any],
    runtime: Mapping[str, Any],
    resolution: Mapping[str, Any],
    *,
    repository_commit: str,
) -> dict[str, Any]:
    cases = _extraction_cases(snapshot)
    gates = {
        "training_snapshot_evidence_gate_passed": snapshot["evidence_gate"][
            "evidence_gate_passed"
        ]
        is True,
        "transparent_operation_baseline_available": True,
        "checkpoint_static_evidence_complete": True,
        "native_windows_dependency_closure_complete": False,
        "isolated_runtime_import_verified": False,
        "restricted_weights_only_load_verified": False,
        "synthetic_feature_clock_verified": False,
        "owner_audio_feature_extraction_authorized": False,
    }
    return {
        "schema": MUSICFM_REMIX_FEATURE_PLAN_SCHEMA,
        "status": "planned_blocked_before_feature_extraction",
        "repository_commit": repository_commit,
        "binding": {
            "training_snapshot_sha256": snapshot["document_sha256"],
            "operation_feature_manifest_sha256": operation["document_sha256"],
            "admission_plan_sha256": admission["document_sha256"],
            "static_evidence_sha256": static["document_sha256"],
            "readiness_sha256": readiness["document_sha256"],
            "runtime_plan_sha256": runtime["document_sha256"],
            "runtime_resolution_sha256": resolution["document_sha256"],
            "provider_id": MUSICFM_FMA_PROVIDER_ID,
        },
        "extractor": {
            "family": "MusicFM",
            "checkpoint_variant": "FMA",
            "checkpoint_sha256": static["artifacts"]["checkpoint"]["sha256"],
            "sample_rate_hz": 24_000,
            "channels": 1,
            "layer_index": 7,
            "feature_rate_hz": 25,
            "feature_dimension": 1_024,
            "output_dtype": "float32",
            "extractor_frozen": True,
            "gradient_into_extractor": False,
            "network_allowed": False,
        },
        "window_policy": {
            "anchor_context_seconds_before": _CONTEXT_SECONDS,
            "anchor_context_seconds_after": _CONTEXT_SECONDS,
            "clamp_to_audio_horizon": True,
            "crop_frames_use_original_audio_clock": True,
            "resample_only_inside_feature_derivative": True,
            "source_audio_mutation": False,
            "feature_frame_count": "measure_and_bind_after_synthetic_canary",
        },
        "cases": cases,
        "expected_feature_artifact": {
            "one_row_per_case_and_input_role": True,
            "input_roles": ["source_control", "target_estimate", "challenger"],
            "file_format": "npy",
            "dtype": "float32",
            "shape": [None, 1_024],
            "finite_values_required": True,
            "audio_sha256_binding_required": True,
            "feature_sha256_binding_required": True,
            "paths_in_manifest": False,
        },
        "gates": gates,
        "ready_for_feature_extraction": False,
        "missing": [key for key, passed in gates.items() if not passed],
        "next_gate": {
            "kind": "complete_native_windows_runtime_then_synthetic_feature_canary",
            "uses_private_audio": False,
            "downloads_dependencies": False,
            "installs_dependencies": False,
            "loads_model": False,
            "runs_inference": False,
            "starts_training": False,
        },
        "authority": {
            "dependency_install_authorized": False,
            "model_import_authorized": False,
            "model_load_authorized": False,
            "synthetic_inference_authorized": False,
            "private_audio_access_authorized": False,
            "feature_extraction_authorized": False,
            "training_execution_authorized": False,
            "checkpoint_promotion_authorized": False,
            "product_ordering_changed": False,
        },
        "effects": {
            "audio_opened": False,
            "audio_resampled": False,
            "model_loaded": False,
            "features_extracted": False,
            "training_started": False,
            "model_weights_changed": False,
        },
    }


def _extraction_cases(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for variant_set in snapshot["variant_sets"]:
        identity = variant_set["identity_state"]
        estimates = {
            row["source_estimate_id"]: row for row in identity["separation_estimates"]
        }
        control = variant_set["source_control"]
        for variant in variant_set["variants"]:
            request = variant["remix_request"]
            result = variant["remix_result"]
            operation = request["operations"][0]
            estimate = estimates[operation["source_estimate_id"]]
            geometry = control["geometry"]
            if (
                estimate["geometry"] != geometry
                or result["output"]["geometry"] != geometry
            ):
                raise ValueError("MusicFM feature inputs must share exact geometry")
            context_frames = _CONTEXT_SECONDS * geometry["sample_rate_hz"]
            crop_start = max(0, operation["start_frame"] - context_frames)
            crop_end = min(geometry["frames"], operation["end_frame"] + context_frames)
            rows.append(
                {
                    "case_id": document_sha256(
                        {
                            "variant_set_sha256": variant_set["document_sha256"],
                            "variant_id": variant["variant_id"],
                        }
                    ),
                    "variant_set_sha256": variant_set["document_sha256"],
                    "variant_family_id": variant_set["variant_family"][
                        "variant_family_id"
                    ],
                    "variant_id": variant["variant_id"],
                    "assignment": _variant_set_assignment(
                        snapshot, variant_set["document_sha256"]
                    ),
                    "anchor": {
                        "anchor_id": operation["anchor_id"],
                        "sample_rate_hz": geometry["sample_rate_hz"],
                        "start_frame": operation["start_frame"],
                        "end_frame": operation["end_frame"],
                    },
                    "crop": {
                        "start_frame": crop_start,
                        "end_frame": crop_end,
                    },
                    "inputs": {
                        "source_control": dict(control),
                        "target_estimate": {
                            "audio_sha256": estimate["audio_sha256"],
                            "audio_bytes": estimate["audio_bytes"],
                            "geometry": dict(estimate["geometry"]),
                            "role": estimate["estimated_role"],
                            "interpretation": "separation_estimate_not_ground_truth",
                        },
                        "challenger": dict(result["output"]),
                    },
                }
            )
    rows.sort(key=lambda row: (row["variant_set_sha256"], row["variant_id"]))
    return rows


def _variant_set_assignment(
    snapshot: Mapping[str, Any], variant_set_sha256: str
) -> dict[str, Any]:
    label_hashes = {
        label["document_sha256"]
        for label in snapshot["labels"]
        if label["binding"]["variant_set_sha256"] == variant_set_sha256
    }
    rows = [
        row
        for row in snapshot["assignments"]
        if row["label_document_sha256"] in label_hashes
    ]
    if not rows:
        raise ValueError("MusicFM feature case has no exact split assignment")
    identity_fields = {
        (
            row["composition_id"],
            row["group_id"],
            row["musical_state_sha256"],
            row["variant_family_id"],
            row["split"],
        )
        for row in rows
    }
    if len(identity_fields) != 1:
        raise ValueError("MusicFM feature case split evidence is inconsistent")
    composition, group, state, family, split = next(iter(identity_fields))
    return {
        "label_document_sha256s": sorted(label_hashes),
        "composition_id": composition,
        "group_id": group,
        "musical_state_sha256": state,
        "variant_family_id": family,
        "split": split,
    }


__all__ = [
    "MUSICFM_REMIX_FEATURE_PLAN_SCHEMA",
    "create_musicfm_remix_feature_plan",
    "validate_musicfm_remix_feature_plan",
]
