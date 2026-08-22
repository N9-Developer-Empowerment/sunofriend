"""Independent, no-training verifier for bounded remix-ranker evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .remix_ranker_training import (
    _combined_delta,
    _constant_prediction,
    _deny_network,
    _heuristic_predictions,
    _load_examples,
    _operation_delta,
    _predictions,
    _validate_snapshot,
    validate_remix_frozen_feature_manifest,
    validate_remix_ranker_training_request,
    validate_remix_ranker_training_result,
)
from .source_receipt import document_sha256


REMIX_RANKER_BOUND_VERIFICATION_SCHEMA = (
    "sunofriend.remix-ranker-training-verification.v1"
)


def verify_remix_ranker_training(
    request: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    feature_manifest: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    feature_root: Path,
) -> dict[str, Any]:
    """Rehash inputs and recompute predictions/metrics without optimisation."""

    checked_request = validate_remix_ranker_training_request(
        request, snapshot, feature_manifest, feature_root=feature_root
    )
    checked_snapshot, kind = _validate_snapshot(snapshot)
    manifest = validate_remix_frozen_feature_manifest(
        feature_manifest, checked_snapshot, feature_root=feature_root
    )
    supplied = validate_remix_ranker_training_result(
        result,
        checked_request,
        checked_snapshot,
        manifest,
        feature_root=feature_root,
    )
    with _deny_network() as network_attempts:
        examples, feature_bytes = _load_examples(
            checked_snapshot, kind, manifest, Path(feature_root).resolve()
        )
        train = [row for row in examples if row["split"] == "train"]
        evaluation = [row for row in examples if row["split"] in {"validation", "test"}]
        weights = supplied["checkpoints"]
        recomputed = {
            "constant_majority": _predictions(
                evaluation, constant=_constant_prediction(train)
            ),
            "smallest_absolute_change": _heuristic_predictions(evaluation, "smallest"),
            "largest_attenuation": _heuristic_predictions(evaluation, "attenuation"),
            "operation_linear": _predictions(
                evaluation,
                weights=weights["operation_linear_weights"],
                feature_fn=_operation_delta,
            ),
            "combined_clean": _predictions(
                evaluation,
                weights=weights["combined_clean_weights"],
                feature_fn=_combined_delta,
            ),
            "combined_resumed": _predictions(
                evaluation,
                weights=weights["combined_resumed_weights"],
                feature_fn=_combined_delta,
            ),
            "combined_shuffled": _predictions(
                evaluation,
                weights=weights["combined_shuffled_weights"],
                feature_fn=_combined_delta,
            ),
        }
    if network_attempts:
        raise RuntimeError("remix ranker verifier attempted network access")
    if recomputed != supplied["predictions"]:
        raise ValueError(
            "remix ranker predictions differ from strict checkpoint recomputation"
        )
    if feature_bytes != supplied["resource_receipt"]["feature_artifact_bytes"]:
        raise ValueError("remix ranker feature byte receipt changed")
    document: dict[str, Any] = {
        "schema": REMIX_RANKER_BOUND_VERIFICATION_SCHEMA,
        "status": "verified_synthetic_training_evidence_unpromoted",
        "request_sha256": checked_request["document_sha256"],
        "snapshot_sha256": checked_snapshot["document_sha256"],
        "feature_manifest_sha256": manifest["document_sha256"],
        "result_sha256": supplied["document_sha256"],
        "checks": {
            "document_hashes_exact": True,
            "feature_artifacts_hash_shape_dtype_finite": True,
            "composition_group_state_family_disjoint": True,
            "checkpoint_shapes_strict": True,
            "predictions_recomputed_without_training": True,
            "resume_parameters_exact": supplied["controls"][
                "maximum_resume_parameter_difference"
            ]
            == 0.0,
            "left_right_swap_check_passed": supplied["controls"][
                "maximum_left_right_swap_probability_error"
            ]
            <= 1e-12,
            "shuffled_label_control_present": True,
            "clean_minus_shuffled_at_least_0_20": supplied["controls"][
                "clean_minus_shuffled_test_accuracy"
            ]
            >= 0.20,
            "clean_test_accuracy_at_least_0_80": supplied["metrics"]["combined_clean"][
                "test_accuracy"
            ]
            >= 0.80,
            "clean_beats_every_deterministic_baseline": supplied["metrics"][
                "combined_clean"
            ]["test_accuracy"]
            > max(
                supplied["metrics"][name]["test_accuracy"]
                for name in (
                    "constant_majority",
                    "smallest_absolute_change",
                    "largest_attenuation",
                    "operation_linear",
                )
            ),
            "deterministic_baselines_present": True,
            "resource_and_offline_receipt_within_request": True,
        },
        "execution": {
            "training_performed_by_verifier": False,
            "network_used": False,
            "network_attempts": 0,
            "downloads_used": False,
            "audio_opened": False,
        },
        "authority": {
            "technical_verification_only": True,
            "real_training_authorized": False,
            "checkpoint_promoted": False,
            "product_admitted": False,
            "product_ordering_changed": False,
        },
    }
    if not all(document["checks"].values()):
        raise ValueError("remix ranker verification checks did not all pass")
    document["document_sha256"] = document_sha256(document)
    return document


__all__ = [
    "REMIX_RANKER_BOUND_VERIFICATION_SCHEMA",
    "verify_remix_ranker_training",
]
