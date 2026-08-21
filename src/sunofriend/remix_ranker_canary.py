"""Deterministic synthetic canary for the bounded remix comparison ranker.

The canary optimises tiny synthetic weights over transparent operation-like
features.  It cannot consume a real training snapshot, audio or frozen-model
features and grants no product or checkpoint authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from typing import Any, Mapping, Sequence

from .source_receipt import canonical_json_bytes, document_sha256


REMIX_RANKER_SYNTHETIC_FIXTURE_SCHEMA = "sunofriend.synthetic-remix-ranker.v0"
REMIX_RANKER_TRAINING_REQUEST_SCHEMA = "sunofriend.remix-ranker-training-request.v0"
REMIX_RANKER_CHECKPOINT_SCHEMA = "sunofriend.synthetic-remix-ranker-checkpoint.v0"
REMIX_RANKER_TRAINING_RESULT_SCHEMA = "sunofriend.remix-ranker-training-result.v0"

_SEED = 20_260_821
_FEATURE_COUNT = 6
_HIDDEN_COUNT = 8
_COMPOSITIONS = 12
_EXAMPLES_PER_COMPOSITION = 16
_TRAIN_COMPOSITIONS = 8
_CHECKPOINT_STEP = 120
_FINAL_STEP = 300
_LEARNING_RATE = 0.2


def build_synthetic_remix_ranker_fixture(seed: int = _SEED) -> dict[str, Any]:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("synthetic remix seed must be an integer")
    generator = random.Random(seed)
    true_weights = [1.5, -1.0, 0.8, 0.4, -0.6, 0.2]
    examples: list[dict[str, Any]] = []
    for composition_index in range(_COMPOSITIONS):
        split = "train" if composition_index < _TRAIN_COMPOSITIONS else "heldout"
        for pair_index in range(_EXAMPLES_PER_COMPOSITION):
            features = [generator.uniform(-1.0, 1.0) for _ in true_weights]
            margin = sum(a * b for a, b in zip(features, true_weights))
            examples.append(
                {
                    "pair_id": f"c{composition_index:02d}-p{pair_index:02d}",
                    "composition_id": f"synthetic-composition-{composition_index:02d}",
                    "group_id": f"synthetic-group-{composition_index:02d}",
                    "split": split,
                    "transparent_feature_delta": features,
                    "label": 1 if margin >= 0.0 else 0,
                }
            )
    document: dict[str, Any] = {
        "schema": REMIX_RANKER_SYNTHETIC_FIXTURE_SCHEMA,
        "seed": seed,
        "synthetic": True,
        "feature_names": [
            "duration_delta",
            "point_count_delta",
            "minimum_gain_delta",
            "mean_gain_delta",
            "absolute_delta_area",
            "maximum_slope_delta",
        ],
        "examples": examples,
        "privacy": {
            "audio_used": False,
            "real_labels_used": False,
            "real_snapshot_used": False,
            "paths_embedded": False,
        },
    }
    document["document_sha256"] = document_sha256(document)
    return document


def build_remix_ranker_canary_request() -> dict[str, Any]:
    fixture = build_synthetic_remix_ranker_fixture()
    document: dict[str, Any] = {
        "schema": REMIX_RANKER_TRAINING_REQUEST_SCHEMA,
        "status": "planned_synthetic_training_only",
        "experiment_id": "remix-ranker-transparent-synthetic-001",
        "method_natures": ["D", "T"],
        "dataset": {
            "schema": REMIX_RANKER_SYNTHETIC_FIXTURE_SCHEMA,
            "sha256": fixture["document_sha256"],
            "synthetic": True,
            "real_snapshot_accepted": False,
            "feature_shape": [
                _COMPOSITIONS * _EXAMPLES_PER_COMPOSITION,
                _FEATURE_COUNT,
            ],
            "composition_disjoint": True,
            "group_disjoint": True,
        },
        "models": {
            "constant": {"trained": False, "parameter_count": 0},
            "transparent_linear": {"parameter_count": _FEATURE_COUNT},
            "transparent_mlp": {
                "trainable_parameter_count": _HIDDEN_COUNT,
                "fixed_hidden_features": _HIDDEN_COUNT,
                "authority": "pipeline_canary_only",
            },
        },
        "training": {
            "optimiser": "full_batch_gradient_descent",
            "learning_rate": _LEARNING_RATE,
            "checkpoint_step": _CHECKPOINT_STEP,
            "final_step": _FINAL_STEP,
            "linear_clean_arm": True,
            "mlp_clean_arm": True,
            "shuffled_label_control": True,
            "exact_serialized_resume": True,
        },
        "limits": {
            "maximum_examples": _COMPOSITIONS * _EXAMPLES_PER_COMPOSITION,
            "maximum_features": _FEATURE_COUNT,
            "maximum_steps_per_arm": _FINAL_STEP,
            "maximum_optimised_arms": 4,
            "maximum_checkpoint_bytes": 16_384,
            "network_allowed": False,
            "downloads_allowed": False,
            "musicfm_allowed": False,
            "audio_allowed": False,
        },
        "authority": {
            "real_training_authorized": False,
            "real_snapshot_authorized": False,
            "private_audio_authorized": False,
            "checkpoint_promotion_authorized": False,
            "product_ranking_authorized": False,
            "remix_render_authorized": False,
        },
    }
    document["document_sha256"] = document_sha256(document)
    return document


def run_remix_ranker_canary(
    request: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    expected = build_remix_ranker_canary_request()
    supplied = expected if request is None else dict(request)
    _validate_request(supplied, expected)
    fixture = build_synthetic_remix_ranker_fixture()
    train = [row for row in fixture["examples"] if row["split"] == "train"]
    heldout = [row for row in fixture["examples"] if row["split"] == "heldout"]

    constant = _constant_accuracy(train, heldout)
    linear_weights = _train(train, _raw_features, end_step=_FINAL_STEP)
    linear_accuracy = _accuracy(linear_weights, heldout, _raw_features)
    mlp_weights = _train(train, _hidden_features, end_step=_FINAL_STEP)
    partial = _train(train, _hidden_features, end_step=_CHECKPOINT_STEP)
    checkpoint = _checkpoint(supplied, fixture, partial)
    checkpoint_bytes = canonical_json_bytes(checkpoint)
    if len(checkpoint_bytes) > supplied["limits"]["maximum_checkpoint_bytes"]:
        raise ValueError("synthetic remix checkpoint exceeds request ceiling")
    reloaded = json.loads(checkpoint_bytes.decode("utf-8"))
    resumed = _train(
        train,
        _hidden_features,
        start_step=reloaded["step"],
        end_step=_FINAL_STEP,
        initial_weights=reloaded["weights"],
    )
    labels = [int(row["label"]) for row in train]
    random.Random(_SEED + 1).shuffle(labels)
    shuffled_rows = [{**row, "label": labels[i]} for i, row in enumerate(train)]
    shuffled = _train(shuffled_rows, _hidden_features, end_step=_FINAL_STEP)
    mlp_accuracy = _accuracy(mlp_weights, heldout, _hidden_features)
    resumed_accuracy = _accuracy(resumed, heldout, _hidden_features)
    shuffled_accuracy = _accuracy(shuffled, heldout, _hidden_features)
    resume_difference = max(abs(a - b) for a, b in zip(mlp_weights, resumed))
    metrics = {
        "constant_heldout_accuracy": constant,
        "transparent_linear_heldout_accuracy": linear_accuracy,
        "transparent_mlp_heldout_accuracy": mlp_accuracy,
        "shuffled_mlp_heldout_accuracy": shuffled_accuracy,
        "mlp_minus_constant_accuracy": mlp_accuracy - constant,
        "mlp_minus_shuffled_accuracy": mlp_accuracy - shuffled_accuracy,
        "maximum_resume_parameter_difference": resume_difference,
    }
    acceptance = {
        "linear_beats_constant": linear_accuracy > constant,
        "mlp_heldout_accuracy_at_least_0_80": mlp_accuracy >= 0.80,
        "mlp_advantage_over_shuffled_at_least_0_20": mlp_accuracy - shuffled_accuracy
        >= 0.20,
        "exact_resume": resume_difference == 0.0 and resumed_accuracy == mlp_accuracy,
        "all_metrics_finite": all(math.isfinite(value) for value in metrics.values()),
    }
    document: dict[str, Any] = {
        "schema": REMIX_RANKER_TRAINING_RESULT_SCHEMA,
        "status": "complete_synthetic_pipeline_canary"
        if all(acceptance.values())
        else "failed",
        "request_document_sha256": supplied["document_sha256"],
        "dataset_sha256": fixture["document_sha256"],
        "method_natures": ["D", "T"],
        "metrics": metrics,
        "checkpoint": {
            "document": checkpoint,
            "serialized_bytes": len(checkpoint_bytes),
            "serialized_sha256": hashlib.sha256(checkpoint_bytes).hexdigest(),
            "resumed_final_sha256": _weights_sha256(resumed),
            "uninterrupted_final_sha256": _weights_sha256(mlp_weights),
        },
        "arms": [
            {
                "arm_id": "constant",
                "trained": False,
                "steps": 0,
                "heldout_accuracy": constant,
            },
            {
                "arm_id": "transparent_linear_clean",
                "trained": True,
                "steps": _FINAL_STEP,
                "heldout_accuracy": linear_accuracy,
            },
            {
                "arm_id": "transparent_mlp_clean",
                "trained": True,
                "steps": _FINAL_STEP,
                "heldout_accuracy": mlp_accuracy,
            },
            {
                "arm_id": "transparent_mlp_serialized_resume",
                "trained": True,
                "steps": _FINAL_STEP,
                "heldout_accuracy": resumed_accuracy,
            },
            {
                "arm_id": "transparent_mlp_shuffled",
                "trained": True,
                "steps": _FINAL_STEP,
                "heldout_accuracy": shuffled_accuracy,
            },
        ],
        "acceptance": acceptance,
        "privacy": {
            "synthetic_only": True,
            "audio_used": False,
            "real_labels_used": False,
            "real_snapshot_used": False,
            "musicfm_used": False,
            "network_used": False,
            "downloads_used": False,
            "paths_embedded": False,
        },
        "authority": {
            "technical_completion_only": True,
            "real_training_authorized": False,
            "checkpoint_promoted": False,
            "product_ranking_changed": False,
            "remix_rendered": False,
        },
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_ranker_canary_result(document, request=supplied)


def validate_remix_ranker_canary_result(
    value: Mapping[str, Any], *, request: Mapping[str, Any]
) -> dict[str, Any]:
    expected = build_remix_ranker_canary_request()
    _validate_request(request, expected)
    document = _verified(value, REMIX_RANKER_TRAINING_RESULT_SCHEMA, "result")
    if set(document) != {
        "schema",
        "status",
        "request_document_sha256",
        "dataset_sha256",
        "method_natures",
        "metrics",
        "checkpoint",
        "arms",
        "acceptance",
        "privacy",
        "authority",
        "document_sha256",
    }:
        raise ValueError("synthetic remix result fields changed")
    if (
        document.get("request_document_sha256") != request["document_sha256"]
        or document.get("dataset_sha256") != request["dataset"]["sha256"]
    ):
        raise ValueError("synthetic remix result binding changed")
    metrics = _mapping(document.get("metrics"), "metrics")
    if set(metrics) != {
        "constant_heldout_accuracy",
        "transparent_linear_heldout_accuracy",
        "transparent_mlp_heldout_accuracy",
        "shuffled_mlp_heldout_accuracy",
        "mlp_minus_constant_accuracy",
        "mlp_minus_shuffled_accuracy",
        "maximum_resume_parameter_difference",
    } or any(
        isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not math.isfinite(float(v))
        for v in metrics.values()
    ):
        raise ValueError("synthetic remix metrics changed")
    calculated = {
        "linear_beats_constant": metrics["transparent_linear_heldout_accuracy"]
        > metrics["constant_heldout_accuracy"],
        "mlp_heldout_accuracy_at_least_0_80": metrics[
            "transparent_mlp_heldout_accuracy"
        ]
        >= 0.80,
        "mlp_advantage_over_shuffled_at_least_0_20": metrics[
            "mlp_minus_shuffled_accuracy"
        ]
        >= 0.20,
        "exact_resume": metrics["maximum_resume_parameter_difference"] == 0.0,
        "all_metrics_finite": True,
    }
    if metrics["mlp_minus_constant_accuracy"] != (
        metrics["transparent_mlp_heldout_accuracy"]
        - metrics["constant_heldout_accuracy"]
    ) or metrics["mlp_minus_shuffled_accuracy"] != (
        metrics["transparent_mlp_heldout_accuracy"]
        - metrics["shuffled_mlp_heldout_accuracy"]
    ):
        raise ValueError("synthetic remix derived metrics changed")
    if document.get("acceptance") != calculated:
        raise ValueError("synthetic remix acceptance changed")
    expected_status = (
        "complete_synthetic_pipeline_canary" if all(calculated.values()) else "failed"
    )
    if document.get("status") != expected_status or document.get("method_natures") != [
        "D",
        "T",
    ]:
        raise ValueError("synthetic remix result status changed")
    checkpoint = _mapping(document.get("checkpoint"), "checkpoint evidence")
    checkpoint_document = _validate_checkpoint(checkpoint.get("document"), request)
    checkpoint_bytes = canonical_json_bytes(checkpoint_document)
    if checkpoint != {
        "document": checkpoint_document,
        "serialized_bytes": len(checkpoint_bytes),
        "serialized_sha256": hashlib.sha256(checkpoint_bytes).hexdigest(),
        "resumed_final_sha256": checkpoint.get("resumed_final_sha256"),
        "uninterrupted_final_sha256": checkpoint.get("uninterrupted_final_sha256"),
    } or checkpoint.get("resumed_final_sha256") != checkpoint.get(
        "uninterrupted_final_sha256"
    ):
        raise ValueError("synthetic remix checkpoint/resume evidence changed")
    for key in ("resumed_final_sha256", "uninterrupted_final_sha256"):
        _sha(checkpoint.get(key), key)
    arms = document.get("arms")
    if not isinstance(arms, list) or [row.get("arm_id") for row in arms] != [
        "constant",
        "transparent_linear_clean",
        "transparent_mlp_clean",
        "transparent_mlp_serialized_resume",
        "transparent_mlp_shuffled",
    ]:
        raise ValueError("synthetic remix arm roster changed")
    expected_arms = [
        {
            "arm_id": "constant",
            "trained": False,
            "steps": 0,
            "heldout_accuracy": metrics["constant_heldout_accuracy"],
        },
        {
            "arm_id": "transparent_linear_clean",
            "trained": True,
            "steps": _FINAL_STEP,
            "heldout_accuracy": metrics["transparent_linear_heldout_accuracy"],
        },
        {
            "arm_id": "transparent_mlp_clean",
            "trained": True,
            "steps": _FINAL_STEP,
            "heldout_accuracy": metrics["transparent_mlp_heldout_accuracy"],
        },
        {
            "arm_id": "transparent_mlp_serialized_resume",
            "trained": True,
            "steps": _FINAL_STEP,
            "heldout_accuracy": metrics["transparent_mlp_heldout_accuracy"],
        },
        {
            "arm_id": "transparent_mlp_shuffled",
            "trained": True,
            "steps": _FINAL_STEP,
            "heldout_accuracy": metrics["shuffled_mlp_heldout_accuracy"],
        },
    ]
    if arms != expected_arms:
        raise ValueError("synthetic remix resume arm metric changed")
    if document.get("privacy") != {
        "synthetic_only": True,
        "audio_used": False,
        "real_labels_used": False,
        "real_snapshot_used": False,
        "musicfm_used": False,
        "network_used": False,
        "downloads_used": False,
        "paths_embedded": False,
    } or document.get("authority") != {
        "technical_completion_only": True,
        "real_training_authorized": False,
        "checkpoint_promoted": False,
        "product_ranking_changed": False,
        "remix_rendered": False,
    }:
        raise ValueError("synthetic remix privacy or authority changed")
    return document


def _checkpoint(
    request: Mapping[str, Any], fixture: Mapping[str, Any], weights: Sequence[float]
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema": REMIX_RANKER_CHECKPOINT_SCHEMA,
        "request_document_sha256": request["document_sha256"],
        "dataset_sha256": fixture["document_sha256"],
        "model": "transparent-fixed-hidden-mlp",
        "step": _CHECKPOINT_STEP,
        "weights": list(weights),
        "synthetic_only": True,
        "product_admitted": False,
    }
    document["document_sha256"] = document_sha256(document)
    return document


def _validate_checkpoint(value: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    document = _verified(
        _mapping(value, "checkpoint"), REMIX_RANKER_CHECKPOINT_SCHEMA, "checkpoint"
    )
    if set(document) != {
        "schema",
        "request_document_sha256",
        "dataset_sha256",
        "model",
        "step",
        "weights",
        "synthetic_only",
        "product_admitted",
        "document_sha256",
    }:
        raise ValueError("synthetic remix checkpoint fields changed")
    weights = document.get("weights")
    if (
        document.get("request_document_sha256") != request["document_sha256"]
        or document.get("dataset_sha256") != request["dataset"]["sha256"]
        or document.get("model") != "transparent-fixed-hidden-mlp"
        or document.get("step") != _CHECKPOINT_STEP
        or not isinstance(weights, list)
        or len(weights) != _HIDDEN_COUNT
        or any(
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(float(v))
            for v in weights
        )
        or document.get("synthetic_only") is not True
        or document.get("product_admitted") is not False
    ):
        raise ValueError("synthetic remix checkpoint identity or authority changed")
    return document


def _validate_request(value: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    supplied = _verified(value, REMIX_RANKER_TRAINING_REQUEST_SCHEMA, "request")
    if supplied != expected:
        raise ValueError("synthetic remix training request changed from fixed contract")


def _train(
    rows: Sequence[Mapping[str, Any]],
    feature_fn: Any,
    *,
    end_step: int,
    start_step: int = 0,
    initial_weights: Sequence[float] | None = None,
) -> list[float]:
    width = len(feature_fn(rows[0]))
    weights = (
        [0.0] * width
        if initial_weights is None
        else [float(v) for v in initial_weights]
    )
    for _ in range(start_step, end_step):
        gradient = [0.0] * width
        for row in rows:
            features = feature_fn(row)
            probability = _sigmoid(sum(a * b for a, b in zip(weights, features)))
            error = probability - int(row["label"])
            for index, feature in enumerate(features):
                gradient[index] += error * feature
        scale = _LEARNING_RATE / len(rows)
        weights = [weight - scale * grad for weight, grad in zip(weights, gradient)]
    return weights


def _raw_features(row: Mapping[str, Any]) -> list[float]:
    return [float(v) for v in row["transparent_feature_delta"]]


def _hidden_features(row: Mapping[str, Any]) -> list[float]:
    raw = _raw_features(row)
    return [math.tanh(1.5 * value) for value in raw] + [
        math.tanh(raw[0] + raw[2]),
        math.tanh(raw[1] - raw[4]),
    ]


def _constant_accuracy(
    train: Sequence[Mapping[str, Any]], heldout: Sequence[Mapping[str, Any]]
) -> float:
    label = 1 if sum(int(row["label"]) for row in train) * 2 >= len(train) else 0
    return sum(int(row["label"]) == label for row in heldout) / len(heldout)


def _accuracy(
    weights: Sequence[float], rows: Sequence[Mapping[str, Any]], feature_fn: Any
) -> float:
    return sum(
        (_sigmoid(sum(a * b for a, b in zip(weights, feature_fn(row)))) >= 0.5)
        == bool(row["label"])
        for row in rows
    ) / len(rows)


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, value))))


def _weights_sha256(weights: Sequence[float]) -> str:
    return hashlib.sha256(canonical_json_bytes({"weights": list(weights)})).hexdigest()


def _verified(value: Mapping[str, Any], schema: str, label: str) -> dict[str, Any]:
    document = dict(value)
    if document.get("schema") != schema:
        raise ValueError(f"unsupported synthetic remix {label} schema")
    supplied = _sha(document.get("document_sha256"), f"{label} document")
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if document_sha256(unsigned) != supplied:
        raise ValueError(f"synthetic remix {label} document hash changed")
    return document


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"synthetic remix {label} must be an object")
    return value


def _sha(value: Any, label: str) -> str:
    text = str(value)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise ValueError(f"synthetic remix {label} SHA-256 is invalid")
    return text


__all__ = [
    "REMIX_RANKER_CHECKPOINT_SCHEMA",
    "REMIX_RANKER_SYNTHETIC_FIXTURE_SCHEMA",
    "REMIX_RANKER_TRAINING_REQUEST_SCHEMA",
    "REMIX_RANKER_TRAINING_RESULT_SCHEMA",
    "build_remix_ranker_canary_request",
    "build_synthetic_remix_ranker_fixture",
    "run_remix_ranker_canary",
    "validate_remix_ranker_canary_result",
]
