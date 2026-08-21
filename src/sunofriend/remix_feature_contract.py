"""Transparent operation features for the first remix-learning baseline."""

from __future__ import annotations

import math
import re
from typing import Any, Mapping

from .remix_learning_contract import validate_remix_training_snapshot
from .source_receipt import document_sha256


REMIX_OPERATION_FEATURE_MANIFEST_SCHEMA = (
    "sunofriend.remix-transparent-operation-feature-manifest.v0"
)
REMIX_TRAINING_READINESS_SCHEMA = "sunofriend.remix-training-readiness.v0"

REMIX_OPERATION_FEATURE_NAMES = [
    "anchor_duration_seconds",
    "envelope_point_count",
    "minimum_delta_db",
    "mean_delta_db",
    "absolute_delta_area_db_seconds",
    "maximum_absolute_slope_db_per_second",
]

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def create_remix_operation_feature_manifest(
    training_snapshot: Mapping[str, Any],
    *,
    feature_set_id: str,
    repository_commit: str,
) -> dict[str, Any]:
    """Create an inline metadata-only feature baseline from exact edit recipes."""

    snapshot = validate_remix_training_snapshot(training_snapshot)
    _safe_id(feature_set_id, "feature_set_id")
    if not _COMMIT.fullmatch(str(repository_commit)):
        raise ValueError("repository_commit must be a full 40-character Git commit")
    rows: list[dict[str, Any]] = []
    for variant_set in snapshot["variant_sets"]:
        sample_rate = variant_set["source_control"]["geometry"]["sample_rate_hz"]
        for variant in variant_set["variants"]:
            operation = variant["remix_request"]["operations"][0]
            features = _operation_features(operation, sample_rate)
            rows.append(
                {
                    "variant_set_sha256": variant_set["document_sha256"],
                    "variant_family_id": variant_set["variant_family"][
                        "variant_family_id"
                    ],
                    "variant_id": variant["variant_id"],
                    "variant_evidence_sha256": variant["variant_evidence_sha256"],
                    "remix_request_sha256": variant["remix_request"]["document_sha256"],
                    "remix_result_sha256": variant["remix_result"]["document_sha256"],
                    "output_audio_sha256": variant["remix_result"]["output"][
                        "audio_sha256"
                    ],
                    "features": features,
                }
            )
    rows.sort(key=lambda row: (row["variant_set_sha256"], row["variant_id"]))
    document: dict[str, Any] = {
        "schema": REMIX_OPERATION_FEATURE_MANIFEST_SCHEMA,
        "status": "complete_transparent_metadata_baseline",
        "feature_set_id": str(feature_set_id),
        "repository_commit": str(repository_commit),
        "training_snapshot_sha256": snapshot["document_sha256"],
        "extractor": {
            "name": "deterministic-gain-envelope-statistics-v1",
            "model_used": False,
            "checkpoint_used": False,
            "audio_decoded": False,
            "feature_names": list(REMIX_OPERATION_FEATURE_NAMES),
            "dtype": "float64-json-number",
        },
        "rows": rows,
        "authority": {
            "transparent_baseline_only": True,
            "frozen_audio_representation_admitted": False,
            "training_execution_authorized": False,
            "model_promotion_authorized": False,
            "product_ordering_changed": False,
        },
        "privacy": {
            "paths_embedded": False,
            "audio_embedded": False,
            "private_notes_embedded": False,
        },
        "effects": {
            "source_mutated": False,
            "remix_rendered": False,
            "training_started": False,
            "model_weights_changed": False,
        },
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_operation_feature_manifest(document, snapshot)


def validate_remix_operation_feature_manifest(
    manifest: Mapping[str, Any], training_snapshot: Mapping[str, Any]
) -> dict[str, Any]:
    snapshot = validate_remix_training_snapshot(training_snapshot)
    document = dict(manifest)
    if document.get("schema") != REMIX_OPERATION_FEATURE_MANIFEST_SCHEMA:
        raise ValueError("unsupported remix operation feature manifest schema")
    _verify_hash(document, "feature manifest")
    if set(document) != {
        "schema",
        "status",
        "feature_set_id",
        "repository_commit",
        "training_snapshot_sha256",
        "extractor",
        "rows",
        "authority",
        "privacy",
        "effects",
        "document_sha256",
    }:
        raise ValueError("remix operation feature manifest fields changed")
    if document.get("status") != "complete_transparent_metadata_baseline":
        raise ValueError("remix operation feature manifest status changed")
    _safe_id(document.get("feature_set_id"), "feature_set_id")
    if not _COMMIT.fullmatch(str(document.get("repository_commit", ""))):
        raise ValueError("repository_commit changed")
    if document.get("training_snapshot_sha256") != snapshot["document_sha256"]:
        raise ValueError("feature manifest snapshot binding changed")
    if document.get("extractor") != {
        "name": "deterministic-gain-envelope-statistics-v1",
        "model_used": False,
        "checkpoint_used": False,
        "audio_decoded": False,
        "feature_names": list(REMIX_OPERATION_FEATURE_NAMES),
        "dtype": "float64-json-number",
    }:
        raise ValueError("transparent feature extractor identity changed")
    expected = create_rows_from_snapshot(snapshot)
    if document.get("rows") != expected:
        raise ValueError("transparent feature rows changed from exact edit recipes")
    if document.get("authority") != {
        "transparent_baseline_only": True,
        "frozen_audio_representation_admitted": False,
        "training_execution_authorized": False,
        "model_promotion_authorized": False,
        "product_ordering_changed": False,
    }:
        raise ValueError("transparent feature authority changed")
    if document.get("privacy") != {
        "paths_embedded": False,
        "audio_embedded": False,
        "private_notes_embedded": False,
    } or document.get("effects") != {
        "source_mutated": False,
        "remix_rendered": False,
        "training_started": False,
        "model_weights_changed": False,
    }:
        raise ValueError("transparent feature privacy or effects changed")
    return document


def assess_remix_training_readiness(
    training_snapshot: Mapping[str, Any],
    operation_features: Mapping[str, Any],
) -> dict[str, Any]:
    """Describe exact remaining gates without granting model execution."""

    snapshot = validate_remix_training_snapshot(training_snapshot)
    manifest = validate_remix_operation_feature_manifest(operation_features, snapshot)
    evidence_passed = snapshot["evidence_gate"]["evidence_gate_passed"] is True
    gates = {
        "explicit_composition_disjoint_evidence_gate": evidence_passed,
        "transparent_operation_baseline_available": True,
        "frozen_audio_feature_manifest_admitted": False,
        "remix_training_request_result_verifier_implemented": False,
        "owner_blind_promotion_review_available": False,
    }
    document: dict[str, Any] = {
        "schema": REMIX_TRAINING_READINESS_SCHEMA,
        "status": "blocked_before_real_model_training",
        "binding": {
            "training_snapshot_sha256": snapshot["document_sha256"],
            "operation_feature_manifest_sha256": manifest["document_sha256"],
        },
        "gates": gates,
        "ready_for_real_weight_optimisation": False,
        "missing": [key for key, passed in gates.items() if not passed],
        "next_implementation": (
            "admit one reproducible frozen audio feature provider and implement "
            "the remix-specific bounded request, runner, result and verifier"
        ),
        "next_owner_evidence": (
            "create controlled variants and explicit three-way pairwise labels "
            "across composition-disjoint authorised songs"
        ),
        "authority": {
            "training_execution_authorized": False,
            "checkpoint_promotion_authorized": False,
            "product_ordering_changed": False,
        },
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_training_readiness(document, snapshot, manifest)


def validate_remix_training_readiness(
    readiness: Mapping[str, Any],
    training_snapshot: Mapping[str, Any],
    operation_features: Mapping[str, Any],
) -> dict[str, Any]:
    snapshot = validate_remix_training_snapshot(training_snapshot)
    manifest = validate_remix_operation_feature_manifest(operation_features, snapshot)
    document = dict(readiness)
    if document.get("schema") != REMIX_TRAINING_READINESS_SCHEMA:
        raise ValueError("unsupported remix training readiness schema")
    _verify_hash(document, "training readiness")
    if set(document) != {
        "schema",
        "status",
        "binding",
        "gates",
        "ready_for_real_weight_optimisation",
        "missing",
        "next_implementation",
        "next_owner_evidence",
        "authority",
        "document_sha256",
    }:
        raise ValueError("remix training readiness fields changed")
    expected = assess_values(snapshot, manifest)
    for key, value in expected.items():
        if document.get(key) != value:
            raise ValueError(f"remix training readiness {key} changed")
    return document


def create_rows_from_snapshot(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for variant_set in snapshot["variant_sets"]:
        sample_rate = variant_set["source_control"]["geometry"]["sample_rate_hz"]
        for variant in variant_set["variants"]:
            rows.append(
                {
                    "variant_set_sha256": variant_set["document_sha256"],
                    "variant_family_id": variant_set["variant_family"][
                        "variant_family_id"
                    ],
                    "variant_id": variant["variant_id"],
                    "variant_evidence_sha256": variant["variant_evidence_sha256"],
                    "remix_request_sha256": variant["remix_request"]["document_sha256"],
                    "remix_result_sha256": variant["remix_result"]["document_sha256"],
                    "output_audio_sha256": variant["remix_result"]["output"][
                        "audio_sha256"
                    ],
                    "features": _operation_features(
                        variant["remix_request"]["operations"][0], sample_rate
                    ),
                }
            )
    rows.sort(key=lambda row: (row["variant_set_sha256"], row["variant_id"]))
    return rows


def assess_values(
    snapshot: Mapping[str, Any], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    gates = {
        "explicit_composition_disjoint_evidence_gate": snapshot["evidence_gate"][
            "evidence_gate_passed"
        ]
        is True,
        "transparent_operation_baseline_available": True,
        "frozen_audio_feature_manifest_admitted": False,
        "remix_training_request_result_verifier_implemented": False,
        "owner_blind_promotion_review_available": False,
    }
    return {
        "status": "blocked_before_real_model_training",
        "binding": {
            "training_snapshot_sha256": snapshot["document_sha256"],
            "operation_feature_manifest_sha256": manifest["document_sha256"],
        },
        "gates": gates,
        "ready_for_real_weight_optimisation": False,
        "missing": [key for key, passed in gates.items() if not passed],
        "next_implementation": (
            "admit one reproducible frozen audio feature provider and implement "
            "the remix-specific bounded request, runner, result and verifier"
        ),
        "next_owner_evidence": (
            "create controlled variants and explicit three-way pairwise labels "
            "across composition-disjoint authorised songs"
        ),
        "authority": {
            "training_execution_authorized": False,
            "checkpoint_promotion_authorized": False,
            "product_ordering_changed": False,
        },
    }


def _operation_features(
    operation: Mapping[str, Any], sample_rate: int
) -> dict[str, Any]:
    points = operation["points"]
    start = operation["start_frame"]
    end = operation["end_frame"]
    duration = (end - start) / sample_rate
    signed_area = 0.0
    absolute_area = 0.0
    maximum_slope = 0.0
    for left, right in zip(points, points[1:]):
        seconds = (right["frame"] - left["frame"]) / sample_rate
        signed_area += seconds * (left["delta_db"] + right["delta_db"]) / 2.0
        absolute_area += (
            seconds * (abs(left["delta_db"]) + abs(right["delta_db"])) / 2.0
        )
        maximum_slope = max(
            maximum_slope,
            abs(right["delta_db"] - left["delta_db"]) / seconds,
        )
    values = [
        duration,
        float(len(points)),
        min(float(row["delta_db"]) for row in points),
        signed_area / duration,
        absolute_area,
        maximum_slope,
    ]
    if any(not math.isfinite(value) for value in values):
        raise ValueError("transparent operation features must be finite")
    return {
        "names": list(REMIX_OPERATION_FEATURE_NAMES),
        "values": values,
        "shape": [len(values)],
    }


def _verify_hash(document: Mapping[str, Any], label: str) -> None:
    supplied = document.get("document_sha256")
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if supplied != document_sha256(unsigned):
        raise ValueError(f"{label} document hash changed")


def _safe_id(value: Any, label: str) -> None:
    if not _SAFE_ID.fullmatch(str(value)):
        raise ValueError(f"{label} must be a safe path-free identifier")


__all__ = [
    "REMIX_OPERATION_FEATURE_MANIFEST_SCHEMA",
    "REMIX_OPERATION_FEATURE_NAMES",
    "REMIX_TRAINING_READINESS_SCHEMA",
    "assess_remix_training_readiness",
    "create_remix_operation_feature_manifest",
    "validate_remix_operation_feature_manifest",
    "validate_remix_training_readiness",
]
