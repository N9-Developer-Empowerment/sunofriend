"""Deterministic synthetic canary for the provisional vocal pairwise ranker.

This changes tiny synthetic weights only.  It never reads audio, consumes a
real label, selects a take, or promotes a checkpoint.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from typing import Any, Mapping, Sequence

from .source_receipt import canonical_json_bytes, document_sha256


SYNTHETIC_PAIRWISE_FIXTURE_SCHEMA = "sunofriend.synthetic-vocal-pairwise.v1"
PAIRWISE_CANARY_REQUEST_SCHEMA = "sunofriend.vocal-pairwise-canary-request.v1"
PAIRWISE_CANARY_RESULT_SCHEMA = "sunofriend.vocal-pairwise-canary-result.v1"

_SEED = 20_260_820
_FEATURE_COUNT = 6
_COMPOSITIONS = 12
_EXAMPLES_PER_COMPOSITION = 16
_TRAIN_COMPOSITIONS = 8
_CHECKPOINT_STEP = 120
_FINAL_STEP = 300
_LEARNING_RATE = 0.2


def build_synthetic_pairwise_fixture(seed: int = _SEED) -> dict[str, Any]:
    """Build composition-disjoint feature deltas with no audio or private data."""

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("synthetic pairwise seed must be an integer")
    generator = random.Random(seed)
    true_weights = [1.5, -1.0, 0.8, 0.4, -0.6, 0.2]
    examples: list[dict[str, Any]] = []
    for composition_index in range(_COMPOSITIONS):
        split = "train" if composition_index < _TRAIN_COMPOSITIONS else "heldout"
        for example_index in range(_EXAMPLES_PER_COMPOSITION):
            features = [generator.uniform(-1.0, 1.0) for _ in true_weights]
            margin = sum(
                feature * weight for feature, weight in zip(features, true_weights)
            )
            examples.append(
                {
                    "example_id": f"c{composition_index:02d}-p{example_index:02d}",
                    "composition_id": f"synthetic-composition-{composition_index:02d}",
                    "group_id": f"synthetic-session-{composition_index:02d}",
                    "split": split,
                    "feature_delta": features,
                    "label": 1 if margin >= 0.0 else 0,
                }
            )
    document: dict[str, Any] = {
        "schema": SYNTHETIC_PAIRWISE_FIXTURE_SCHEMA,
        "seed": seed,
        "synthetic": True,
        "feature_count": _FEATURE_COUNT,
        "composition_count": _COMPOSITIONS,
        "group_count": _COMPOSITIONS,
        "examples": examples,
        "privacy": {
            "audio_used": False,
            "real_labels_used": False,
            "paths_embedded": False,
        },
    }
    document["document_sha256"] = document_sha256(document)
    return document


def build_pairwise_ranker_canary_request() -> dict[str, Any]:
    fixture = build_synthetic_pairwise_fixture()
    document: dict[str, Any] = {
        "schema": PAIRWISE_CANARY_REQUEST_SCHEMA,
        "status": "planned_synthetic_training_only",
        "experiment_id": "vocal-pairwise-ranker-synthetic-001",
        "method_natures": ["D", "T"],
        "dataset": {
            "schema": SYNTHETIC_PAIRWISE_FIXTURE_SCHEMA,
            "sha256": fixture["document_sha256"],
            "synthetic": True,
            "feature_shape": [
                _COMPOSITIONS * _EXAMPLES_PER_COMPOSITION,
                _FEATURE_COUNT,
            ],
            "composition_disjoint": True,
            "group_disjoint": True,
        },
        "model": {
            "name": "provisional-linear-vocal-pairwise-ranker",
            "feature_count": _FEATURE_COUNT,
            "parameter_count": _FEATURE_COUNT,
            "authority": "pipeline_canary_only",
        },
        "training": {
            "optimiser": "full_batch_gradient_descent",
            "learning_rate": _LEARNING_RATE,
            "checkpoint_step": _CHECKPOINT_STEP,
            "final_step": _FINAL_STEP,
            "clean_arm": True,
            "shuffled_label_control": True,
            "exact_serialized_resume": True,
        },
        "limits": {
            "maximum_examples": _COMPOSITIONS * _EXAMPLES_PER_COMPOSITION,
            "maximum_features": _FEATURE_COUNT,
            "maximum_steps_per_arm": _FINAL_STEP,
            "maximum_arms": 3,
            "network_allowed": False,
            "downloads_allowed": False,
        },
        "authority": {
            "real_training_authorized": False,
            "private_audio_authorized": False,
            "checkpoint_promotion_authorized": False,
            "product_ranking_authorized": False,
        },
    }
    document["document_sha256"] = document_sha256(document)
    return document


def run_pairwise_ranker_canary(
    request: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Exercise clean, shuffled and exact serialized-resume arms."""

    expected = build_pairwise_ranker_canary_request()
    supplied = expected if request is None else dict(request)
    _validate_exact_request(supplied, expected)
    fixture = build_synthetic_pairwise_fixture()
    train = [row for row in fixture["examples"] if row["split"] == "train"]
    heldout = [row for row in fixture["examples"] if row["split"] == "heldout"]

    clean_weights = _train(train, end_step=_FINAL_STEP)
    checkpoint_weights = _train(train, end_step=_CHECKPOINT_STEP)
    checkpoint = {
        "schema": "sunofriend.synthetic-vocal-pairwise-checkpoint.v1",
        "request_document_sha256": supplied["document_sha256"],
        "dataset_sha256": fixture["document_sha256"],
        "step": _CHECKPOINT_STEP,
        "weights": checkpoint_weights,
        "synthetic_only": True,
    }
    checkpoint_bytes = canonical_json_bytes(checkpoint)
    reloaded = json.loads(checkpoint_bytes.decode("utf-8"))
    resumed_weights = _train(
        train,
        start_step=int(reloaded["step"]),
        end_step=_FINAL_STEP,
        initial_weights=reloaded["weights"],
    )

    shuffled_labels = [int(row["label"]) for row in train]
    random.Random(_SEED + 1).shuffle(shuffled_labels)
    shuffled_rows = [
        {**row, "label": shuffled_labels[index]} for index, row in enumerate(train)
    ]
    shuffled_weights = _train(shuffled_rows, end_step=_FINAL_STEP)

    clean_accuracy = _accuracy(clean_weights, heldout)
    shuffled_accuracy = _accuracy(shuffled_weights, heldout)
    max_resume_difference = max(
        abs(left - right) for left, right in zip(clean_weights, resumed_weights)
    )
    acceptance = {
        "clean_heldout_accuracy_at_least_0_85": clean_accuracy >= 0.85,
        "clean_advantage_at_least_0_20": clean_accuracy - shuffled_accuracy >= 0.20,
        "exact_resume": max_resume_difference == 0.0,
        "all_metrics_finite": all(
            math.isfinite(value)
            for value in (clean_accuracy, shuffled_accuracy, max_resume_difference)
        ),
    }
    document: dict[str, Any] = {
        "schema": PAIRWISE_CANARY_RESULT_SCHEMA,
        "status": "complete_pipeline_canary" if all(acceptance.values()) else "failed",
        "request_document_sha256": supplied["document_sha256"],
        "dataset_sha256": fixture["document_sha256"],
        "method_natures": ["D", "T"],
        "metrics": {
            "clean_heldout_accuracy": clean_accuracy,
            "shuffled_heldout_accuracy": shuffled_accuracy,
            "clean_minus_shuffled_accuracy": clean_accuracy - shuffled_accuracy,
            "maximum_resume_parameter_difference": max_resume_difference,
        },
        "checkpoint": {
            "step": _CHECKPOINT_STEP,
            "serialized_bytes": len(checkpoint_bytes),
            "sha256": hashlib.sha256(checkpoint_bytes).hexdigest(),
            "resumed_final_sha256": _weights_sha256(resumed_weights),
            "uninterrupted_final_sha256": _weights_sha256(clean_weights),
        },
        "arms": [
            {
                "arm_id": "clean_uninterrupted",
                "steps": _FINAL_STEP,
                "heldout_accuracy": clean_accuracy,
            },
            {
                "arm_id": "clean_serialized_resume",
                "steps": _FINAL_STEP,
                "heldout_accuracy": _accuracy(resumed_weights, heldout),
            },
            {
                "arm_id": "shuffled_label_control",
                "steps": _FINAL_STEP,
                "heldout_accuracy": shuffled_accuracy,
            },
        ],
        "acceptance": acceptance,
        "privacy": {
            "audio_used": False,
            "real_labels_used": False,
            "paths_embedded": False,
            "network_used": False,
            "downloads_used": False,
        },
        "authority": {
            "technical_completion_only": True,
            "real_training_authorized": False,
            "checkpoint_promoted": False,
            "product_ranking_changed": False,
            "vocal_source_selected": False,
        },
    }
    document["document_sha256"] = document_sha256(document)
    return validate_pairwise_ranker_canary_result(document, request=supplied)


def validate_pairwise_ranker_canary_result(
    value: Mapping[str, Any], *, request: Mapping[str, Any]
) -> dict[str, Any]:
    document = dict(value)
    expected_request = build_pairwise_ranker_canary_request()
    _validate_exact_request(request, expected_request)
    if document.get("schema") != PAIRWISE_CANARY_RESULT_SCHEMA:
        raise ValueError("unsupported pairwise canary result schema")
    supplied_hash = str(document.get("document_sha256", ""))
    without_hash = dict(document)
    without_hash.pop("document_sha256", None)
    if document_sha256(without_hash) != supplied_hash:
        raise ValueError("pairwise canary result document hash changed")
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
        raise ValueError("pairwise canary result fields changed")
    if document.get("request_document_sha256") != request["document_sha256"]:
        raise ValueError("pairwise canary result does not bind the request")
    if document.get("dataset_sha256") != request["dataset"]["sha256"]:
        raise ValueError("pairwise canary result does not bind the fixture")
    if document.get("method_natures") != ["D", "T"]:
        raise ValueError("pairwise canary result method nature changed")
    metrics = document.get("metrics")
    if not isinstance(metrics, Mapping) or any(
        not isinstance(value, (int, float)) or not math.isfinite(float(value))
        for value in metrics.values()
    ):
        raise ValueError("pairwise canary metrics must be finite")
    if (
        not 0.0 <= float(metrics["clean_heldout_accuracy"]) <= 1.0
        or not 0.0 <= float(metrics["shuffled_heldout_accuracy"]) <= 1.0
    ):
        raise ValueError("pairwise canary accuracy is outside 0-1")
    if float(metrics["clean_minus_shuffled_accuracy"]) != float(
        metrics["clean_heldout_accuracy"]
    ) - float(metrics["shuffled_heldout_accuracy"]):
        raise ValueError("pairwise canary accuracy advantage changed")
    acceptance = document.get("acceptance")
    if (
        not isinstance(acceptance, Mapping)
        or set(acceptance)
        != {
            "clean_heldout_accuracy_at_least_0_85",
            "clean_advantage_at_least_0_20",
            "exact_resume",
            "all_metrics_finite",
        }
        or any(not isinstance(item, bool) for item in acceptance.values())
    ):
        raise ValueError("pairwise canary acceptance fields changed")
    expected_status = (
        "complete_pipeline_canary" if all(acceptance.values()) else "failed"
    )
    if document.get("status") != expected_status:
        raise ValueError("pairwise canary status does not match acceptance")
    calculated = {
        "clean_heldout_accuracy_at_least_0_85": float(metrics["clean_heldout_accuracy"])
        >= 0.85,
        "clean_advantage_at_least_0_20": float(metrics["clean_minus_shuffled_accuracy"])
        >= 0.20,
        "exact_resume": float(metrics["maximum_resume_parameter_difference"]) == 0.0,
        "all_metrics_finite": True,
    }
    if dict(acceptance) != calculated:
        raise ValueError("pairwise canary acceptance does not match metrics")
    arms = document.get("arms")
    if not isinstance(arms, list) or [row.get("arm_id") for row in arms] != [
        "clean_uninterrupted",
        "clean_serialized_resume",
        "shuffled_label_control",
    ]:
        raise ValueError("pairwise canary arm roster changed")
    if any(row.get("steps") != 300 for row in arms):
        raise ValueError("pairwise canary arm steps changed")
    if (
        arms[0].get("heldout_accuracy") != metrics["clean_heldout_accuracy"]
        or arms[1].get("heldout_accuracy") != metrics["clean_heldout_accuracy"]
        or arms[2].get("heldout_accuracy") != metrics["shuffled_heldout_accuracy"]
    ):
        raise ValueError("pairwise canary arm metrics changed")
    checkpoint = document.get("checkpoint")
    if (
        not isinstance(checkpoint, Mapping)
        or checkpoint.get("step") != 120
        or checkpoint.get("resumed_final_sha256")
        != checkpoint.get("uninterrupted_final_sha256")
        or not isinstance(checkpoint.get("serialized_bytes"), int)
        or checkpoint.get("serialized_bytes") <= 0
        or any(
            not isinstance(checkpoint.get(key), str)
            or len(checkpoint[key]) != 64
            or any(character not in "0123456789abcdef" for character in checkpoint[key])
            for key in (
                "sha256",
                "resumed_final_sha256",
                "uninterrupted_final_sha256",
            )
        )
    ):
        raise ValueError("pairwise canary checkpoint/resume identity changed")
    if document.get("privacy") != {
        "audio_used": False,
        "real_labels_used": False,
        "paths_embedded": False,
        "network_used": False,
        "downloads_used": False,
    }:
        raise ValueError("pairwise canary privacy boundary changed")
    if document.get("authority") != {
        "technical_completion_only": True,
        "real_training_authorized": False,
        "checkpoint_promoted": False,
        "product_ranking_changed": False,
        "vocal_source_selected": False,
    }:
        raise ValueError("pairwise canary authority changed")
    expected_fixed_evidence = _recompute_fixed_local_evidence(request)
    if any(
        document[key] != expected
        for key, expected in expected_fixed_evidence.items()
    ):
        raise ValueError(
            "pairwise canary evidence differs from the independently fixed fixture result"
        )
    return document


def _recompute_fixed_local_evidence(request: Mapping[str, Any]) -> dict[str, Any]:
    """Re-run the tiny fixed fixture instead of trusting self-consistent claims."""

    fixture = build_synthetic_pairwise_fixture()
    train = [row for row in fixture["examples"] if row["split"] == "train"]
    heldout = [row for row in fixture["examples"] if row["split"] == "heldout"]
    clean_weights = _train(train, end_step=_FINAL_STEP)
    checkpoint_weights = _train(train, end_step=_CHECKPOINT_STEP)
    checkpoint_document = {
        "schema": "sunofriend.synthetic-vocal-pairwise-checkpoint.v1",
        "request_document_sha256": request["document_sha256"],
        "dataset_sha256": fixture["document_sha256"],
        "step": _CHECKPOINT_STEP,
        "weights": checkpoint_weights,
        "synthetic_only": True,
    }
    checkpoint_bytes = canonical_json_bytes(checkpoint_document)
    resumed_weights = _train(
        train,
        start_step=_CHECKPOINT_STEP,
        end_step=_FINAL_STEP,
        initial_weights=json.loads(checkpoint_bytes.decode("utf-8"))["weights"],
    )
    shuffled_labels = [int(row["label"]) for row in train]
    random.Random(_SEED + 1).shuffle(shuffled_labels)
    shuffled_weights = _train(
        [
            {**row, "label": shuffled_labels[index]}
            for index, row in enumerate(train)
        ],
        end_step=_FINAL_STEP,
    )
    clean_accuracy = _accuracy(clean_weights, heldout)
    shuffled_accuracy = _accuracy(shuffled_weights, heldout)
    maximum_resume_difference = max(
        abs(left - right) for left, right in zip(clean_weights, resumed_weights)
    )
    return {
        "metrics": {
            "clean_heldout_accuracy": clean_accuracy,
            "shuffled_heldout_accuracy": shuffled_accuracy,
            "clean_minus_shuffled_accuracy": clean_accuracy - shuffled_accuracy,
            "maximum_resume_parameter_difference": maximum_resume_difference,
        },
        "checkpoint": {
            "step": _CHECKPOINT_STEP,
            "serialized_bytes": len(checkpoint_bytes),
            "sha256": hashlib.sha256(checkpoint_bytes).hexdigest(),
            "resumed_final_sha256": _weights_sha256(resumed_weights),
            "uninterrupted_final_sha256": _weights_sha256(clean_weights),
        },
    }


def _validate_exact_request(
    value: Mapping[str, Any], expected: Mapping[str, Any]
) -> None:
    document = dict(value)
    supplied_hash = str(document.get("document_sha256", ""))
    without_hash = dict(document)
    without_hash.pop("document_sha256", None)
    if document_sha256(without_hash) != supplied_hash:
        raise ValueError("pairwise canary request document hash changed")
    if document != expected:
        raise ValueError("pairwise canary request differs from the fixed contract")


def _train(
    examples: Sequence[Mapping[str, Any]],
    *,
    end_step: int,
    start_step: int = 0,
    initial_weights: Sequence[float] | None = None,
) -> list[float]:
    weights = (
        [0.0] * _FEATURE_COUNT
        if initial_weights is None
        else [float(value) for value in initial_weights]
    )
    if len(weights) != _FEATURE_COUNT or not 0 <= start_step <= end_step <= _FINAL_STEP:
        raise ValueError(
            "synthetic canary training state is outside the fixed contract"
        )
    for _step in range(start_step, end_step):
        gradient = [0.0] * _FEATURE_COUNT
        for row in examples:
            features = row["feature_delta"]
            logit = sum(weight * feature for weight, feature in zip(weights, features))
            probability = 1.0 / (1.0 + math.exp(-logit))
            error = probability - int(row["label"])
            for index, feature in enumerate(features):
                gradient[index] += error * feature
        for index in range(_FEATURE_COUNT):
            weights[index] -= _LEARNING_RATE * gradient[index] / len(examples)
        if any(not math.isfinite(value) for value in weights):
            raise RuntimeError("synthetic pairwise canary produced non-finite weights")
    return weights


def _accuracy(weights: Sequence[float], examples: Sequence[Mapping[str, Any]]) -> float:
    correct = 0
    for row in examples:
        score = sum(
            weight * feature for weight, feature in zip(weights, row["feature_delta"])
        )
        correct += int((score >= 0.0) == bool(row["label"]))
    return correct / len(examples)


def _weights_sha256(weights: Sequence[float]) -> str:
    return hashlib.sha256(canonical_json_bytes({"weights": list(weights)})).hexdigest()
