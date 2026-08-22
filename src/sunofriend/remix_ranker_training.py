"""Bounded remix-ranker training contracts over frozen feature artifacts.

The real-data path accepts only the existing explicit owner-label snapshot and
keeps execution blocked until its evidence gate passes.  The synthetic path
uses the same frozen-feature artifact and request/result shapes, but carries no
owner-label, musical, checkpoint-promotion or product authority.
"""

from __future__ import annotations

from contextlib import contextmanager
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import re
import socket
import time
from typing import Any, Iterator, Mapping, Optional, Sequence

from .remix_learning_contract import validate_remix_training_snapshot
from .source_receipt import canonical_json_bytes, document_sha256


REMIX_SYNTHETIC_TRAINING_SNAPSHOT_SCHEMA = (
    "sunofriend.synthetic-remix-pairwise-training-snapshot.v0"
)
REMIX_FROZEN_FEATURE_VECTOR_SCHEMA = "sunofriend.remix-frozen-feature-vector.v0"
REMIX_FROZEN_FEATURE_MANIFEST_SCHEMA = "sunofriend.remix-frozen-feature-manifest.v0"
REMIX_RANKER_BOUND_REQUEST_SCHEMA = "sunofriend.remix-ranker-training-request.v1"
REMIX_RANKER_BOUND_CHECKPOINT_SCHEMA = "sunofriend.remix-ranker-checkpoint.v1"
REMIX_RANKER_BOUND_RESULT_SCHEMA = "sunofriend.remix-ranker-training-result.v1"

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.json$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SPLITS = ("train", "validation", "test")
_OPERATION_FEATURE_NAMES = (
    "anchor_duration_seconds",
    "envelope_point_count",
    "minimum_delta_db",
    "mean_delta_db",
    "absolute_delta_area_db_seconds",
    "maximum_absolute_slope_db_per_second",
)
_SEED = 20_260_822
_COMPOSITIONS = 12
_PAIRS_PER_COMPOSITION = 8
_FROZEN_DIMENSION = 8
_CHECKPOINT_STEP = 120
_FINAL_STEP = 300
_LEARNING_RATE = 0.15


def build_synthetic_remix_training_snapshot(seed: int = _SEED) -> dict[str, Any]:
    """Create a split-safe fixture whose labels are explicitly non-human."""

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("synthetic training seed must be an integer")
    generator = random.Random(seed)
    frozen_weights = (1.4, -0.9, 0.7, 0.5, -0.6, 0.35, 0.25, -0.2)
    operation_weights = (0.15, -0.05, -0.12, -0.18, -0.08, 0.04)
    examples: list[dict[str, Any]] = []
    for composition_index in range(_COMPOSITIONS):
        split = (
            "train"
            if composition_index < 8
            else "validation"
            if composition_index < 10
            else "test"
        )
        composition_id = f"synthetic-composition-{composition_index:02d}"
        group_id = f"synthetic-group-{composition_index:02d}"
        musical_state_sha256 = hashlib.sha256(
            f"synthetic-state:{composition_index}".encode("ascii")
        ).hexdigest()
        for pair_index in range(_PAIRS_PER_COMPOSITION):
            pair_id = f"c{composition_index:02d}-p{pair_index:02d}"
            family_id = f"synthetic-family-{pair_id}"
            left_id = f"synthetic-left-{pair_id}"
            right_id = f"synthetic-right-{pair_id}"
            left_evidence = hashlib.sha256(left_id.encode("ascii")).hexdigest()
            right_evidence = hashlib.sha256(right_id.encode("ascii")).hexdigest()
            left_frozen = [generator.uniform(-1.0, 1.0) for _ in frozen_weights]
            right_frozen = [generator.uniform(-1.0, 1.0) for _ in frozen_weights]
            left_operation = _synthetic_operation_features(generator)
            right_operation = _synthetic_operation_features(generator)
            frozen_delta = [a - b for a, b in zip(left_frozen, right_frozen)]
            operation_delta = [a - b for a, b in zip(left_operation, right_operation)]
            margin = sum(a * b for a, b in zip(frozen_delta, frozen_weights))
            margin += sum(a * b for a, b in zip(operation_delta, operation_weights))
            examples.append(
                {
                    "pair_id": pair_id,
                    "composition_id": composition_id,
                    "group_id": group_id,
                    "musical_state_sha256": musical_state_sha256,
                    "variant_family_id": family_id,
                    "split": split,
                    "left": {
                        "variant_id": left_id,
                        "variant_evidence_sha256": left_evidence,
                        "operation_features": left_operation,
                    },
                    "right": {
                        "variant_id": right_id,
                        "variant_evidence_sha256": right_evidence,
                        "operation_features": right_operation,
                    },
                    "outcome": "left" if margin >= 0.0 else "right",
                    "label_authority": "synthetic_fixture_only",
                }
            )
            # Feature values are returned separately by the deterministic helper.
            examples[-1]["left"]["_fixture_frozen_values"] = left_frozen
            examples[-1]["right"]["_fixture_frozen_values"] = right_frozen
    public_examples = []
    for row in examples:
        clean = json.loads(json.dumps(row))
        clean["left"].pop("_fixture_frozen_values")
        clean["right"].pop("_fixture_frozen_values")
        public_examples.append(clean)
    document: dict[str, Any] = {
        "schema": REMIX_SYNTHETIC_TRAINING_SNAPSHOT_SCHEMA,
        "status": "complete_synthetic_fixture_no_owner_authority",
        "seed": seed,
        "examples": public_examples,
        "split_policy": {
            "composition_disjoint": True,
            "group_disjoint": True,
            "musical_state_disjoint": True,
            "variant_family_disjoint": True,
        },
        "privacy": {
            "synthetic_only": True,
            "audio_used": False,
            "owner_labels_used": False,
            "paths_embedded": False,
        },
        "authority": {
            "real_training_authorized": False,
            "checkpoint_promotion_authorized": False,
            "product_ordering_authorized": False,
        },
    }
    document["document_sha256"] = document_sha256(document)
    return validate_synthetic_remix_training_snapshot(document)


def synthetic_frozen_values(seed: int = _SEED) -> dict[str, list[float]]:
    """Rebuild the private-to-the-fixture vectors omitted from its snapshot."""

    generator = random.Random(seed)
    values: dict[str, list[float]] = {}
    for composition_index in range(_COMPOSITIONS):
        for pair_index in range(_PAIRS_PER_COMPOSITION):
            pair_id = f"c{composition_index:02d}-p{pair_index:02d}"
            left = [generator.uniform(-1.0, 1.0) for _ in range(_FROZEN_DIMENSION)]
            right = [generator.uniform(-1.0, 1.0) for _ in range(_FROZEN_DIMENSION)]
            _synthetic_operation_features(generator)
            _synthetic_operation_features(generator)
            values[
                hashlib.sha256(f"synthetic-left-{pair_id}".encode("ascii")).hexdigest()
            ] = left
            values[
                hashlib.sha256(f"synthetic-right-{pair_id}".encode("ascii")).hexdigest()
            ] = right
    return values


def validate_synthetic_remix_training_snapshot(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    document = _verified(value, REMIX_SYNTHETIC_TRAINING_SNAPSHOT_SCHEMA, "snapshot")
    if (
        set(document)
        != {
            "schema",
            "status",
            "seed",
            "examples",
            "split_policy",
            "privacy",
            "authority",
            "document_sha256",
        }
        or document.get("status") != "complete_synthetic_fixture_no_owner_authority"
    ):
        raise ValueError("synthetic remix snapshot fields or status changed")
    if isinstance(document.get("seed"), bool) or not isinstance(
        document.get("seed"), int
    ):
        raise ValueError("synthetic remix snapshot seed changed")
    rows = document.get("examples")
    if not isinstance(rows, list) or not rows:
        raise ValueError("synthetic remix snapshot needs examples")
    expected_keys = {
        "pair_id",
        "composition_id",
        "group_id",
        "musical_state_sha256",
        "variant_family_id",
        "split",
        "left",
        "right",
        "outcome",
        "label_authority",
    }
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != expected_keys:
            raise ValueError("synthetic remix example fields changed")
        for key in ("pair_id", "composition_id", "group_id", "variant_family_id"):
            _safe_id(row.get(key), key)
        _sha(row.get("musical_state_sha256"), "musical state")
        if row.get("split") not in _SPLITS or row.get("outcome") not in {
            "left",
            "right",
        }:
            raise ValueError("synthetic remix split or outcome changed")
        if row.get("label_authority") != "synthetic_fixture_only":
            raise ValueError("synthetic fixture cannot claim owner label authority")
        for side_name in ("left", "right"):
            side = row.get(side_name)
            if not isinstance(side, Mapping) or set(side) != {
                "variant_id",
                "variant_evidence_sha256",
                "operation_features",
            }:
                raise ValueError("synthetic remix side fields changed")
            _safe_id(side.get("variant_id"), "variant_id")
            _sha(side.get("variant_evidence_sha256"), "variant evidence")
            _finite_vector(
                side.get("operation_features"), len(_OPERATION_FEATURE_NAMES)
            )
        if (
            row["left"]["variant_evidence_sha256"]
            == row["right"]["variant_evidence_sha256"]
        ):
            raise ValueError("synthetic pair requires two variants")
    _validate_disjoint_examples(rows)
    if (
        document.get("split_policy")
        != {
            "composition_disjoint": True,
            "group_disjoint": True,
            "musical_state_disjoint": True,
            "variant_family_disjoint": True,
        }
        or document.get("privacy")
        != {
            "synthetic_only": True,
            "audio_used": False,
            "owner_labels_used": False,
            "paths_embedded": False,
        }
        or document.get("authority")
        != {
            "real_training_authorized": False,
            "checkpoint_promotion_authorized": False,
            "product_ordering_authorized": False,
        }
    ):
        raise ValueError("synthetic snapshot boundary changed")
    return document


def write_frozen_feature_vector(
    path: Path, *, variant_evidence_sha256: str, values: Sequence[float]
) -> dict[str, Any]:
    """Write one immutable JSON feature vector and return its artifact record."""

    target = Path(path)
    if target.exists() or target.is_symlink():
        raise ValueError("frozen feature artifact must be fresh")
    _sha(variant_evidence_sha256, "variant evidence")
    vector = _finite_vector(values)
    document: dict[str, Any] = {
        "schema": REMIX_FROZEN_FEATURE_VECTOR_SCHEMA,
        "variant_evidence_sha256": variant_evidence_sha256,
        "dtype": "float64-json-number",
        "shape": [len(vector)],
        "values": vector,
    }
    document["document_sha256"] = document_sha256(document)
    data = canonical_json_bytes(document)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with target.open("xb") as handle:
        handle.write(data)
    target.chmod(0o600)
    return {
        "filename": target.name,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def create_remix_frozen_feature_manifest(
    snapshot: Mapping[str, Any],
    *,
    feature_root: Path,
    rows: Sequence[Mapping[str, Any]],
    feature_set_id: str,
    repository_commit: str,
    extractor: Mapping[str, Any],
    synthetic_only: bool,
) -> dict[str, Any]:
    checked_snapshot, kind = _validate_snapshot(snapshot)
    _safe_id(feature_set_id, "feature_set_id")
    _commit(repository_commit)
    root = _real_directory(feature_root, "feature_root")
    checked_extractor = _validate_extractor(extractor)
    expected_variants = _snapshot_variant_hashes(checked_snapshot, kind)
    checked_rows = _validate_feature_rows(
        rows, root, checked_extractor["feature_dimension"]
    )
    if {row["variant_evidence_sha256"] for row in checked_rows} != expected_variants:
        raise ValueError(
            "frozen feature manifest must cover every exact snapshot variant once"
        )
    if synthetic_only is not (kind == "synthetic"):
        raise ValueError("synthetic feature status must match snapshot kind")
    document: dict[str, Any] = {
        "schema": REMIX_FROZEN_FEATURE_MANIFEST_SCHEMA,
        "status": "complete_frozen_features_admitted",
        "feature_set_id": feature_set_id,
        "repository_commit": repository_commit,
        "snapshot": {
            "schema": checked_snapshot["schema"],
            "sha256": checked_snapshot["document_sha256"],
        },
        "extractor": checked_extractor,
        "rows": sorted(checked_rows, key=lambda row: row["variant_evidence_sha256"]),
        "admission": {
            "artifact_hashes_verified": True,
            "shapes_verified": True,
            "finite_values_verified": True,
            "extractor_frozen": True,
            "gradient_into_extractor": False,
            "synthetic_only": synthetic_only,
        },
        "privacy": {
            "paths_embedded": False,
            "audio_embedded": False,
            "private_notes_embedded": False,
        },
        "authority": {
            "feature_use_only": True,
            "training_execution_authorized": False,
            "checkpoint_promotion_authorized": False,
            "product_ordering_authorized": False,
        },
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_frozen_feature_manifest(
        document, checked_snapshot, feature_root=root
    )


def validate_remix_frozen_feature_manifest(
    value: Mapping[str, Any], snapshot: Mapping[str, Any], *, feature_root: Path
) -> dict[str, Any]:
    checked_snapshot, kind = _validate_snapshot(snapshot)
    document = _verified(
        value, REMIX_FROZEN_FEATURE_MANIFEST_SCHEMA, "feature manifest"
    )
    if (
        set(document)
        != {
            "schema",
            "status",
            "feature_set_id",
            "repository_commit",
            "snapshot",
            "extractor",
            "rows",
            "admission",
            "privacy",
            "authority",
            "document_sha256",
        }
        or document.get("status") != "complete_frozen_features_admitted"
    ):
        raise ValueError("frozen feature manifest fields or status changed")
    _safe_id(document.get("feature_set_id"), "feature_set_id")
    _commit(document.get("repository_commit"))
    if document.get("snapshot") != {
        "schema": checked_snapshot["schema"],
        "sha256": checked_snapshot["document_sha256"],
    }:
        raise ValueError("frozen feature manifest snapshot binding changed")
    extractor = _validate_extractor(document.get("extractor"))
    root = _real_directory(feature_root, "feature_root")
    rows = _validate_feature_rows(
        document.get("rows"), root, extractor["feature_dimension"]
    )
    if rows != document.get("rows") or {
        row["variant_evidence_sha256"] for row in rows
    } != _snapshot_variant_hashes(checked_snapshot, kind):
        raise ValueError("frozen feature manifest row roster changed")
    if (
        document.get("admission")
        != {
            "artifact_hashes_verified": True,
            "shapes_verified": True,
            "finite_values_verified": True,
            "extractor_frozen": True,
            "gradient_into_extractor": False,
            "synthetic_only": kind == "synthetic",
        }
        or document.get("privacy")
        != {
            "paths_embedded": False,
            "audio_embedded": False,
            "private_notes_embedded": False,
        }
        or document.get("authority")
        != {
            "feature_use_only": True,
            "training_execution_authorized": False,
            "checkpoint_promotion_authorized": False,
            "product_ordering_authorized": False,
        }
    ):
        raise ValueError("frozen feature admission, privacy or authority changed")
    return document


def create_remix_ranker_training_request(
    snapshot: Mapping[str, Any],
    feature_manifest: Mapping[str, Any],
    *,
    feature_root: Path,
    request_id: str,
    repository_commit: str,
    dependency_contract_sha256: str,
) -> dict[str, Any]:
    checked_snapshot, kind = _validate_snapshot(snapshot)
    manifest = validate_remix_frozen_feature_manifest(
        feature_manifest, checked_snapshot, feature_root=feature_root
    )
    _safe_id(request_id, "request_id")
    _commit(repository_commit)
    _sha(dependency_contract_sha256, "dependency contract")
    if manifest["repository_commit"] != repository_commit:
        raise ValueError("request and feature manifest repository commits differ")
    summary = _snapshot_summary(checked_snapshot, kind)
    real_gate_passed = (
        kind == "real"
        and checked_snapshot["evidence_gate"]["evidence_gate_passed"] is True
    )
    synthetic_canary = kind == "synthetic"
    status = (
        "planned_synthetic_contract_canary"
        if synthetic_canary
        else "blocked_pending_explicit_real_training_authority"
        if real_gate_passed
        else "blocked_insufficient_real_evidence"
    )
    document: dict[str, Any] = {
        "schema": REMIX_RANKER_BOUND_REQUEST_SCHEMA,
        "status": status,
        "request_id": request_id,
        "repository_commit": repository_commit,
        "dependency_contract_sha256": dependency_contract_sha256,
        "bindings": {
            "snapshot_schema": checked_snapshot["schema"],
            "snapshot_sha256": checked_snapshot["document_sha256"],
            "feature_manifest_sha256": manifest["document_sha256"],
        },
        "dataset": {
            **summary,
            "evidence_gate_passed": synthetic_canary or real_gate_passed,
            "training_eligible": synthetic_canary,
        },
        "model": {
            "name": "pairwise-linear-probe-v1",
            "input_dimension": manifest["extractor"]["feature_dimension"]
            + len(_OPERATION_FEATURE_NAMES),
            "loss": "binary_cross_entropy",
        },
        "training": {
            "seed": _SEED,
            "optimiser": "deterministic_full_batch_gradient_descent",
            "learning_rate": _LEARNING_RATE,
            "checkpoint_step": _CHECKPOINT_STEP,
            "final_step": _FINAL_STEP,
            "clean_arm": True,
            "serialized_resume_arm": True,
            "shuffled_label_control": True,
        },
        "baselines": [
            "constant_majority",
            "smallest_absolute_change",
            "largest_attenuation",
            "operation_linear",
        ],
        "limits": {
            "maximum_examples": 256,
            "maximum_feature_dimension": 64,
            "maximum_steps_per_arm": 500,
            "maximum_feature_bytes": 8_000_000,
            "maximum_result_bytes": 2_000_000,
            "maximum_wall_seconds": 30.0,
            "network_allowed": False,
            "downloads_allowed": False,
            "audio_allowed": False,
        },
        "authority": {
            "synthetic_fixture_optimisation_authorized": synthetic_canary,
            "real_weight_optimisation_authorized": False,
            "source_mutation_authorized": False,
            "remix_render_authorized": False,
            "checkpoint_promotion_authorized": False,
            "product_ordering_authorized": False,
            "automatic_preference_authorized": False,
        },
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_ranker_training_request(
        document, checked_snapshot, manifest, feature_root=feature_root
    )


def validate_remix_ranker_training_request(
    value: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    feature_manifest: Mapping[str, Any],
    *,
    feature_root: Path,
) -> dict[str, Any]:
    checked_snapshot, kind = _validate_snapshot(snapshot)
    manifest = validate_remix_frozen_feature_manifest(
        feature_manifest, checked_snapshot, feature_root=feature_root
    )
    document = _verified(value, REMIX_RANKER_BOUND_REQUEST_SCHEMA, "training request")
    if set(document) != {
        "schema",
        "status",
        "request_id",
        "repository_commit",
        "dependency_contract_sha256",
        "bindings",
        "dataset",
        "model",
        "training",
        "baselines",
        "limits",
        "authority",
        "document_sha256",
    }:
        raise ValueError("remix ranker request fields changed")
    _safe_id(document.get("request_id"), "request_id")
    _commit(document.get("repository_commit"))
    _sha(document.get("dependency_contract_sha256"), "dependency contract")
    if document["repository_commit"] != manifest["repository_commit"] or document.get(
        "bindings"
    ) != {
        "snapshot_schema": checked_snapshot["schema"],
        "snapshot_sha256": checked_snapshot["document_sha256"],
        "feature_manifest_sha256": manifest["document_sha256"],
    }:
        raise ValueError("remix ranker request binding changed")
    summary = _snapshot_summary(checked_snapshot, kind)
    evidence_gate_passed = (
        kind == "synthetic"
        or checked_snapshot["evidence_gate"]["evidence_gate_passed"] is True
    )
    expected_status = (
        "planned_synthetic_contract_canary"
        if kind == "synthetic"
        else "blocked_pending_explicit_real_training_authority"
        if evidence_gate_passed
        else "blocked_insufficient_real_evidence"
    )
    if document.get("status") != expected_status or document.get("dataset") != {
        **summary,
        "evidence_gate_passed": evidence_gate_passed,
        "training_eligible": kind == "synthetic",
    }:
        raise ValueError("remix ranker eligibility or split summary changed")
    expected_model = {
        "name": "pairwise-linear-probe-v1",
        "input_dimension": manifest["extractor"]["feature_dimension"]
        + len(_OPERATION_FEATURE_NAMES),
        "loss": "binary_cross_entropy",
    }
    if (
        document.get("model") != expected_model
        or document.get("training")
        != {
            "seed": _SEED,
            "optimiser": "deterministic_full_batch_gradient_descent",
            "learning_rate": _LEARNING_RATE,
            "checkpoint_step": _CHECKPOINT_STEP,
            "final_step": _FINAL_STEP,
            "clean_arm": True,
            "serialized_resume_arm": True,
            "shuffled_label_control": True,
        }
        or document.get("baselines")
        != [
            "constant_majority",
            "smallest_absolute_change",
            "largest_attenuation",
            "operation_linear",
        ]
    ):
        raise ValueError("remix ranker model, training or baseline contract changed")
    if document.get("limits") != {
        "maximum_examples": 256,
        "maximum_feature_dimension": 64,
        "maximum_steps_per_arm": 500,
        "maximum_feature_bytes": 8_000_000,
        "maximum_result_bytes": 2_000_000,
        "maximum_wall_seconds": 30.0,
        "network_allowed": False,
        "downloads_allowed": False,
        "audio_allowed": False,
    } or document.get("authority") != {
        "synthetic_fixture_optimisation_authorized": kind == "synthetic",
        "real_weight_optimisation_authorized": False,
        "source_mutation_authorized": False,
        "remix_render_authorized": False,
        "checkpoint_promotion_authorized": False,
        "product_ordering_authorized": False,
        "automatic_preference_authorized": False,
    }:
        raise ValueError("remix ranker limits or authority changed")
    if (
        summary["total_examples"] > document["limits"]["maximum_examples"]
        or expected_model["input_dimension"]
        > document["limits"]["maximum_feature_dimension"]
    ):
        raise ValueError("remix ranker request exceeds data resource ceiling")
    return document


def run_remix_ranker_training(
    request: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    feature_manifest: Mapping[str, Any],
    *,
    feature_root: Path,
    repository_commit: str,
) -> dict[str, Any]:
    """Run the synthetic fixture only; real execution needs a later authority gate."""

    started = time.monotonic()
    checked = validate_remix_ranker_training_request(
        request, snapshot, feature_manifest, feature_root=feature_root
    )
    checked_snapshot, kind = _validate_snapshot(snapshot)
    manifest = validate_remix_frozen_feature_manifest(
        feature_manifest, checked_snapshot, feature_root=feature_root
    )
    if checked["repository_commit"] != repository_commit:
        raise ValueError("runner repository commit differs from exact request")
    if kind != "synthetic" or checked["status"] != "planned_synthetic_contract_canary":
        raise ValueError("real remix training remains ineligible and is not executable")
    examples, feature_bytes = _load_examples(
        checked_snapshot, kind, manifest, Path(feature_root)
    )
    if feature_bytes > checked["limits"]["maximum_feature_bytes"]:
        raise ValueError("frozen feature artifacts exceed request ceiling")
    train = [row for row in examples if row["split"] == "train"]
    evaluation = [row for row in examples if row["split"] in {"validation", "test"}]
    with _deny_network() as network_attempts:
        constant = _constant_prediction(train)
        operation_weights = _train(train, _operation_delta, _FINAL_STEP)
        clean_weights = _train(train, _combined_delta, _FINAL_STEP)
        partial = _train(train, _combined_delta, _CHECKPOINT_STEP)
        checkpoint = _checkpoint(checked, partial)
        reloaded = json.loads(canonical_json_bytes(checkpoint).decode("utf-8"))
        resumed_weights = _train(
            train,
            _combined_delta,
            _FINAL_STEP,
            start_step=reloaded["step"],
            initial_weights=reloaded["weights"],
        )
        shuffled_rows = [dict(row) for row in train]
        shuffled_labels = [int(row["label"]) for row in shuffled_rows]
        random.Random(_SEED + 1).shuffle(shuffled_labels)
        for row, label in zip(shuffled_rows, shuffled_labels):
            row["label"] = label
        shuffled_weights = _train(shuffled_rows, _combined_delta, _FINAL_STEP)
    if network_attempts:
        raise RuntimeError("remix ranker attempted network access")
    predictions = {
        "constant_majority": _predictions(evaluation, constant=constant),
        "smallest_absolute_change": _heuristic_predictions(evaluation, "smallest"),
        "largest_attenuation": _heuristic_predictions(evaluation, "attenuation"),
        "operation_linear": _predictions(
            evaluation, weights=operation_weights, feature_fn=_operation_delta
        ),
        "combined_clean": _predictions(
            evaluation, weights=clean_weights, feature_fn=_combined_delta
        ),
        "combined_resumed": _predictions(
            evaluation, weights=resumed_weights, feature_fn=_combined_delta
        ),
        "combined_shuffled": _predictions(
            evaluation, weights=shuffled_weights, feature_fn=_combined_delta
        ),
    }
    metrics = {name: _prediction_metrics(rows) for name, rows in predictions.items()}
    resume_difference = max(abs(a - b) for a, b in zip(clean_weights, resumed_weights))
    swap_error = _maximum_swap_error(evaluation, clean_weights)
    wall_seconds = time.monotonic() - started
    if wall_seconds > checked["limits"]["maximum_wall_seconds"]:
        raise RuntimeError("remix ranker exceeded wall-time ceiling")
    result: dict[str, Any] = {
        "schema": REMIX_RANKER_BOUND_RESULT_SCHEMA,
        "status": "complete_synthetic_training_pipeline_unpromoted",
        "request_sha256": checked["document_sha256"],
        "snapshot_sha256": checked_snapshot["document_sha256"],
        "feature_manifest_sha256": manifest["document_sha256"],
        "repository_commit": repository_commit,
        "checkpoints": {
            "resume_checkpoint": checkpoint,
            "operation_linear_weights": operation_weights,
            "combined_clean_weights": clean_weights,
            "combined_resumed_weights": resumed_weights,
            "combined_shuffled_weights": shuffled_weights,
        },
        "predictions": predictions,
        "metrics": metrics,
        "controls": {
            "maximum_resume_parameter_difference": resume_difference,
            "maximum_left_right_swap_probability_error": swap_error,
            "clean_minus_shuffled_test_accuracy": metrics["combined_clean"][
                "test_accuracy"
            ]
            - metrics["combined_shuffled"]["test_accuracy"],
            "all_values_finite": True,
        },
        "resource_receipt": {
            "examples": len(examples),
            "feature_artifact_bytes": feature_bytes,
            "wall_seconds": wall_seconds,
            "network_attempts": len(network_attempts),
            "downloads": 0,
            "audio_files_opened": 0,
        },
        "privacy": {
            "synthetic_only": True,
            "owner_labels_used": False,
            "private_audio_used": False,
            "paths_embedded": False,
        },
        "authority": {
            "technical_evidence_only": True,
            "checkpoint_promoted": False,
            "product_admitted": False,
            "product_ordering_changed": False,
            "remix_rendered": False,
        },
    }
    result["document_sha256"] = document_sha256(result)
    encoded = canonical_json_bytes(result)
    if len(encoded) > checked["limits"]["maximum_result_bytes"]:
        raise RuntimeError("remix ranker result exceeds byte ceiling")
    return validate_remix_ranker_training_result(
        result, checked, checked_snapshot, manifest, feature_root=feature_root
    )


def validate_remix_ranker_training_result(
    value: Mapping[str, Any],
    request: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    feature_manifest: Mapping[str, Any],
    *,
    feature_root: Path,
) -> dict[str, Any]:
    checked = validate_remix_ranker_training_request(
        request, snapshot, feature_manifest, feature_root=feature_root
    )
    checked_snapshot, kind = _validate_snapshot(snapshot)
    manifest = validate_remix_frozen_feature_manifest(
        feature_manifest, checked_snapshot, feature_root=feature_root
    )
    document = _verified(value, REMIX_RANKER_BOUND_RESULT_SCHEMA, "training result")
    if set(document) != {
        "schema",
        "status",
        "request_sha256",
        "snapshot_sha256",
        "feature_manifest_sha256",
        "repository_commit",
        "checkpoints",
        "predictions",
        "metrics",
        "controls",
        "resource_receipt",
        "privacy",
        "authority",
        "document_sha256",
    }:
        raise ValueError("remix ranker result fields changed")
    if (
        kind != "synthetic"
        or document.get("status") != "complete_synthetic_training_pipeline_unpromoted"
        or document.get("request_sha256") != checked["document_sha256"]
        or document.get("snapshot_sha256") != checked_snapshot["document_sha256"]
        or document.get("feature_manifest_sha256") != manifest["document_sha256"]
        or document.get("repository_commit") != checked["repository_commit"]
    ):
        raise ValueError("remix ranker result binding or status changed")
    checkpoints = document.get("checkpoints")
    if not isinstance(checkpoints, Mapping) or set(checkpoints) != {
        "resume_checkpoint",
        "operation_linear_weights",
        "combined_clean_weights",
        "combined_resumed_weights",
        "combined_shuffled_weights",
    }:
        raise ValueError("remix ranker checkpoint roster changed")
    _validate_checkpoint(checkpoints["resume_checkpoint"], checked)
    dimensions = {
        "operation_linear_weights": len(_OPERATION_FEATURE_NAMES),
        "combined_clean_weights": checked["model"]["input_dimension"],
        "combined_resumed_weights": checked["model"]["input_dimension"],
        "combined_shuffled_weights": checked["model"]["input_dimension"],
    }
    for name, width in dimensions.items():
        _finite_vector(checkpoints[name], width)
    resume_difference = max(
        abs(a - b)
        for a, b in zip(
            checkpoints["combined_clean_weights"],
            checkpoints["combined_resumed_weights"],
        )
    )
    predictions = document.get("predictions")
    expected_names = {
        "constant_majority",
        "smallest_absolute_change",
        "largest_attenuation",
        "operation_linear",
        "combined_clean",
        "combined_resumed",
        "combined_shuffled",
    }
    if not isinstance(predictions, Mapping) or set(predictions) != expected_names:
        raise ValueError("remix ranker prediction roster changed")
    metrics = document.get("metrics")
    if not isinstance(metrics, Mapping) or set(metrics) != expected_names:
        raise ValueError("remix ranker metric roster changed")
    for name in sorted(expected_names):
        _validate_prediction_rows(predictions[name])
        if metrics[name] != _prediction_metrics(predictions[name]):
            raise ValueError("remix ranker metrics changed from predictions")
    controls = document.get("controls")
    if (
        not isinstance(controls, Mapping)
        or controls
        != {
            "maximum_resume_parameter_difference": resume_difference,
            "maximum_left_right_swap_probability_error": controls.get(
                "maximum_left_right_swap_probability_error"
            ),
            "clean_minus_shuffled_test_accuracy": metrics["combined_clean"][
                "test_accuracy"
            ]
            - metrics["combined_shuffled"]["test_accuracy"],
            "all_values_finite": True,
        }
        or not _finite_number(controls.get("maximum_left_right_swap_probability_error"))
        or controls["maximum_left_right_swap_probability_error"] > 1e-12
    ):
        raise ValueError("remix ranker control evidence changed")
    receipt = document.get("resource_receipt")
    if (
        not isinstance(receipt, Mapping)
        or set(receipt)
        != {
            "examples",
            "feature_artifact_bytes",
            "wall_seconds",
            "network_attempts",
            "downloads",
            "audio_files_opened",
        }
        or receipt.get("examples") != checked["dataset"]["total_examples"]
        or not _finite_number(receipt.get("wall_seconds"))
        or receipt["wall_seconds"] < 0
        or receipt["wall_seconds"] > checked["limits"]["maximum_wall_seconds"]
        or receipt.get("network_attempts") != 0
        or receipt.get("downloads") != 0
        or receipt.get("audio_files_opened") != 0
        or isinstance(receipt.get("feature_artifact_bytes"), bool)
        or not isinstance(receipt.get("feature_artifact_bytes"), int)
        or receipt["feature_artifact_bytes"] <= 0
        or receipt["feature_artifact_bytes"]
        > checked["limits"]["maximum_feature_bytes"]
    ):
        raise ValueError("remix ranker resource or offline receipt changed")
    if document.get("privacy") != {
        "synthetic_only": True,
        "owner_labels_used": False,
        "private_audio_used": False,
        "paths_embedded": False,
    } or document.get("authority") != {
        "technical_evidence_only": True,
        "checkpoint_promoted": False,
        "product_admitted": False,
        "product_ordering_changed": False,
        "remix_rendered": False,
    }:
        raise ValueError("remix ranker privacy or product authority changed")
    return document


def _validate_snapshot(value: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    if value.get("schema") == REMIX_SYNTHETIC_TRAINING_SNAPSHOT_SCHEMA:
        return validate_synthetic_remix_training_snapshot(value), "synthetic"
    return validate_remix_training_snapshot(value), "real"


def _snapshot_variant_hashes(snapshot: Mapping[str, Any], kind: str) -> set[str]:
    if kind == "synthetic":
        return {
            row[side]["variant_evidence_sha256"]
            for row in snapshot["examples"]
            for side in ("left", "right")
        }
    return {
        row["variant_evidence_sha256"]
        for variant_set in snapshot["variant_sets"]
        for row in variant_set["variants"]
    }


def _snapshot_summary(snapshot: Mapping[str, Any], kind: str) -> dict[str, Any]:
    if kind == "synthetic":
        rows = snapshot["examples"]
        excluded = 0
    else:
        assignments = {
            row["label_document_sha256"]: row for row in snapshot["assignments"]
        }
        rows = [
            {
                "split": assignments[label["document_sha256"]]["split"],
                "composition_id": assignments[label["document_sha256"]][
                    "composition_id"
                ],
                "group_id": assignments[label["document_sha256"]]["group_id"],
                "variant_family_id": assignments[label["document_sha256"]][
                    "variant_family_id"
                ],
                "musical_state_sha256": label["binding"]["musical_state_sha256"],
                "outcome": label["outcome"],
            }
            for label in snapshot["labels"]
            if label["outcome"] in {"left", "right"}
        ]
        excluded = len(snapshot["labels"]) - len(rows)
    counts = Counter(row["split"] for row in rows)
    return {
        "kind": kind,
        "total_examples": len(rows),
        "decisive_examples": len(rows),
        "excluded_non_directional_examples": excluded,
        "split_counts": {name: counts[name] for name in _SPLITS},
        "split_policy": {
            "composition_disjoint": True,
            "group_disjoint": True,
            "musical_state_disjoint": True,
            "variant_family_disjoint": True,
        },
    }


def _validate_disjoint_examples(rows: Sequence[Mapping[str, Any]]) -> None:
    for key in (
        "composition_id",
        "group_id",
        "musical_state_sha256",
        "variant_family_id",
    ):
        seen: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            seen[str(row[key])].add(str(row["split"]))
        if any(len(splits) != 1 for splits in seen.values()):
            raise ValueError(f"synthetic {key} must be split-disjoint")
    if any(not any(row["split"] == split for row in rows) for split in _SPLITS):
        raise ValueError("synthetic fixture requires train, validation and test")


def _validate_extractor(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "name",
        "source_revision",
        "checkpoint_sha256",
        "license_spdx",
        "layer",
        "sample_rate_hz",
        "feature_rate_hz",
        "pooling",
        "feature_dimension",
        "dtype",
        "extractor_frozen",
        "gradient_into_extractor",
    }:
        raise ValueError("frozen extractor fields changed")
    _safe_id(value.get("name"), "extractor name")
    _commit(value.get("source_revision"))
    _sha(value.get("checkpoint_sha256"), "extractor checkpoint")
    _safe_id(value.get("license_spdx"), "extractor license")
    _safe_id(value.get("layer"), "extractor layer")
    for key in ("sample_rate_hz", "feature_dimension"):
        if (
            isinstance(value.get(key), bool)
            or not isinstance(value.get(key), int)
            or value[key] <= 0
        ):
            raise ValueError(f"extractor {key} changed")
    if (
        not _finite_number(value.get("feature_rate_hz"))
        or value["feature_rate_hz"] <= 0
        or value.get("pooling") not in {"mean_over_anchor", "synthetic_fixed_vector"}
        or value.get("dtype") != "float64-json-number"
        or value.get("extractor_frozen") is not True
        or value.get("gradient_into_extractor") is not False
    ):
        raise ValueError("frozen extractor geometry or authority changed")
    return dict(value)


def _validate_feature_rows(
    values: Any, root: Path, dimension: int
) -> list[dict[str, Any]]:
    if (
        not isinstance(values, Sequence)
        or isinstance(values, (str, bytes))
        or not values
    ):
        raise ValueError("frozen feature rows must be non-empty")
    rows = []
    seen = set()
    for raw in values:
        if not isinstance(raw, Mapping) or set(raw) != {
            "variant_evidence_sha256",
            "artifact",
            "shape",
            "dtype",
            "finite",
        }:
            raise ValueError("frozen feature row fields changed")
        variant_hash = _sha(raw.get("variant_evidence_sha256"), "variant evidence")
        if variant_hash in seen:
            raise ValueError("frozen feature manifest repeats a variant")
        seen.add(variant_hash)
        artifact = raw.get("artifact")
        if (
            not isinstance(artifact, Mapping)
            or set(artifact) != {"filename", "bytes", "sha256"}
            or not _SAFE_FILENAME.fullmatch(str(artifact.get("filename", "")))
            or isinstance(artifact.get("bytes"), bool)
            or not isinstance(artifact.get("bytes"), int)
            or artifact["bytes"] <= 0
        ):
            raise ValueError("frozen feature artifact record changed")
        _sha(artifact.get("sha256"), "feature artifact")
        path = root / artifact["filename"]
        if path.is_symlink() or not path.is_file() or path.parent.resolve() != root:
            raise ValueError("frozen feature artifact escaped exact root")
        data = path.read_bytes()
        if (
            len(data) != artifact["bytes"]
            or hashlib.sha256(data).hexdigest() != artifact["sha256"]
        ):
            raise ValueError("frozen feature artifact hash or size changed")
        vector = _load_feature_document(data, variant_hash, dimension)
        if (
            raw.get("shape") != [dimension]
            or raw.get("dtype") != "float64-json-number"
            or raw.get("finite") is not True
            or len(vector) != dimension
        ):
            raise ValueError("frozen feature row shape, dtype or finite gate changed")
        rows.append(
            {
                "variant_evidence_sha256": variant_hash,
                "artifact": dict(artifact),
                "shape": [dimension],
                "dtype": "float64-json-number",
                "finite": True,
            }
        )
    return rows


def _load_feature_document(
    data: bytes, variant_hash: str, dimension: int
) -> list[float]:
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("frozen feature artifact is not canonical JSON") from exc
    if (
        canonical_json_bytes(document) != data
        or not isinstance(document, Mapping)
        or document.get("schema") != REMIX_FROZEN_FEATURE_VECTOR_SCHEMA
    ):
        raise ValueError("frozen feature artifact encoding or schema changed")
    checked = _verified(document, REMIX_FROZEN_FEATURE_VECTOR_SCHEMA, "feature vector")
    if (
        set(checked)
        != {
            "schema",
            "variant_evidence_sha256",
            "dtype",
            "shape",
            "values",
            "document_sha256",
        }
        or checked.get("variant_evidence_sha256") != variant_hash
        or checked.get("dtype") != "float64-json-number"
        or checked.get("shape") != [dimension]
    ):
        raise ValueError("frozen feature vector binding changed")
    return _finite_vector(checked.get("values"), dimension)


def _load_examples(
    snapshot: Mapping[str, Any], kind: str, manifest: Mapping[str, Any], root: Path
) -> tuple[list[dict[str, Any]], int]:
    if kind != "synthetic":
        raise ValueError("real feature loading is not executable in this increment")
    by_hash = {}
    total_bytes = 0
    dimension = manifest["extractor"]["feature_dimension"]
    for row in manifest["rows"]:
        artifact = row["artifact"]
        data = (root / artifact["filename"]).read_bytes()
        total_bytes += len(data)
        by_hash[row["variant_evidence_sha256"]] = _load_feature_document(
            data, row["variant_evidence_sha256"], dimension
        )
    examples = []
    for source in snapshot["examples"]:
        examples.append(
            {
                "pair_id": source["pair_id"],
                "composition_id": source["composition_id"],
                "group_id": source["group_id"],
                "musical_state_sha256": source["musical_state_sha256"],
                "variant_family_id": source["variant_family_id"],
                "split": source["split"],
                "left_operation": list(source["left"]["operation_features"]),
                "right_operation": list(source["right"]["operation_features"]),
                "left_frozen": by_hash[source["left"]["variant_evidence_sha256"]],
                "right_frozen": by_hash[source["right"]["variant_evidence_sha256"]],
                "label": 1 if source["outcome"] == "left" else 0,
            }
        )
    return examples, total_bytes


def _train(
    rows: Sequence[Mapping[str, Any]],
    feature_fn: Any,
    end_step: int,
    *,
    start_step: int = 0,
    initial_weights: Optional[Sequence[float]] = None,
) -> list[float]:
    width = len(feature_fn(rows[0]))
    weights = (
        [0.0] * width
        if initial_weights is None
        else [float(value) for value in initial_weights]
    )
    for _ in range(start_step, end_step):
        gradient = [0.0] * width
        for row in rows:
            features = feature_fn(row)
            error = _sigmoid(sum(a * b for a, b in zip(weights, features))) - int(
                row["label"]
            )
            for index, feature in enumerate(features):
                gradient[index] += error * feature
        scale = _LEARNING_RATE / len(rows)
        weights = [weight - scale * grad for weight, grad in zip(weights, gradient)]
    return weights


def _operation_delta(row: Mapping[str, Any]) -> list[float]:
    return [a - b for a, b in zip(row["left_operation"], row["right_operation"])]


def _combined_delta(row: Mapping[str, Any]) -> list[float]:
    return _operation_delta(row) + [
        a - b for a, b in zip(row["left_frozen"], row["right_frozen"])
    ]


def _constant_prediction(rows: Sequence[Mapping[str, Any]]) -> int:
    return 1 if sum(int(row["label"]) for row in rows) * 2 >= len(rows) else 0


def _predictions(
    rows: Sequence[Mapping[str, Any]],
    *,
    weights: Optional[Sequence[float]] = None,
    feature_fn: Optional[Any] = None,
    constant: Optional[int] = None,
) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        probability = (
            float(constant)
            if constant is not None
            else _sigmoid(sum(a * b for a, b in zip(weights or [], feature_fn(row))))
        )
        output.append(_prediction_row(row, probability))
    return output


def _heuristic_predictions(
    rows: Sequence[Mapping[str, Any]], kind: str
) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        left, right = row["left_operation"], row["right_operation"]
        if kind == "smallest":
            probability = 1.0 if abs(left[4]) <= abs(right[4]) else 0.0
        else:
            probability = 1.0 if left[3] <= right[3] else 0.0
        output.append(_prediction_row(row, probability))
    return output


def _prediction_row(row: Mapping[str, Any], probability: float) -> dict[str, Any]:
    if not _finite_number(probability):
        raise ValueError("prediction probability must be finite")
    return {
        "pair_id": row["pair_id"],
        "composition_id": row["composition_id"],
        "split": row["split"],
        "label": int(row["label"]),
        "left_probability": probability,
        "predicted_label": 1 if probability >= 0.5 else 0,
    }


def _prediction_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    metrics = {}
    for split in ("validation", "test"):
        subset = [row for row in rows if row["split"] == split]
        metrics[f"{split}_accuracy"] = sum(
            row["label"] == row["predicted_label"] for row in subset
        ) / len(subset)
        by_composition = defaultdict(list)
        for row in subset:
            by_composition[row["composition_id"]].append(row)
        metrics[f"{split}_per_composition_accuracy"] = {
            key: sum(item["label"] == item["predicted_label"] for item in values)
            / len(values)
            for key, values in sorted(by_composition.items())
        }
    return metrics


def _validate_prediction_rows(rows: Any) -> None:
    if not isinstance(rows, list) or not rows:
        raise ValueError("prediction rows must be non-empty")
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or set(row)
            != {
                "pair_id",
                "composition_id",
                "split",
                "label",
                "left_probability",
                "predicted_label",
            }
            or row.get("split") not in {"validation", "test"}
            or row.get("label") not in {0, 1}
            or row.get("predicted_label") not in {0, 1}
            or not _finite_number(row.get("left_probability"))
            or not 0.0 <= row["left_probability"] <= 1.0
            or row["predicted_label"] != (1 if row["left_probability"] >= 0.5 else 0)
        ):
            raise ValueError("prediction row fields or values changed")


def _maximum_swap_error(
    rows: Sequence[Mapping[str, Any]], weights: Sequence[float]
) -> float:
    maximum = 0.0
    for row in rows:
        margin = sum(a * b for a, b in zip(weights, _combined_delta(row)))
        maximum = max(maximum, abs(_sigmoid(-margin) - (1.0 - _sigmoid(margin))))
    return maximum


def _checkpoint(request: Mapping[str, Any], weights: Sequence[float]) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema": REMIX_RANKER_BOUND_CHECKPOINT_SCHEMA,
        "request_sha256": request["document_sha256"],
        "architecture": request["model"]["name"],
        "step": _CHECKPOINT_STEP,
        "weights": list(weights),
        "synthetic_only": True,
        "product_admitted": False,
    }
    document["document_sha256"] = document_sha256(document)
    return document


def _validate_checkpoint(value: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    document = _verified(value, REMIX_RANKER_BOUND_CHECKPOINT_SCHEMA, "checkpoint")
    if (
        set(document)
        != {
            "schema",
            "request_sha256",
            "architecture",
            "step",
            "weights",
            "synthetic_only",
            "product_admitted",
            "document_sha256",
        }
        or document.get("request_sha256") != request["document_sha256"]
        or document.get("architecture") != request["model"]["name"]
        or document.get("step") != _CHECKPOINT_STEP
        or document.get("synthetic_only") is not True
        or document.get("product_admitted") is not False
    ):
        raise ValueError("remix ranker checkpoint binding or authority changed")
    _finite_vector(document.get("weights"), request["model"]["input_dimension"])
    return document


def _synthetic_operation_features(generator: random.Random) -> list[float]:
    duration = generator.uniform(0.5, 4.0)
    points = float(generator.randint(3, 7))
    minimum = generator.uniform(-9.0, -0.5)
    mean = minimum * generator.uniform(0.3, 0.8)
    area = abs(mean) * duration
    slope = abs(minimum) / generator.uniform(0.1, 1.0)
    return [duration, points, minimum, mean, area, slope]


@contextmanager
def _deny_network() -> Iterator[list[str]]:
    attempts: list[str] = []
    original_connect = socket.socket.connect
    original_create = socket.create_connection
    original_getaddrinfo = socket.getaddrinfo

    def denied(*args: Any, **kwargs: Any) -> Any:
        attempts.append("network")
        raise RuntimeError("network is disabled for remix ranker training")

    socket.socket.connect = denied  # type: ignore[assignment]
    socket.create_connection = denied  # type: ignore[assignment]
    socket.getaddrinfo = denied  # type: ignore[assignment]
    try:
        yield attempts
    finally:
        socket.socket.connect = original_connect  # type: ignore[assignment]
        socket.create_connection = original_create  # type: ignore[assignment]
        socket.getaddrinfo = original_getaddrinfo  # type: ignore[assignment]


def _real_directory(path: Path, label: str) -> Path:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError(f"{label} must be an existing non-symlink directory")
    return candidate.resolve()


def _finite_vector(value: Any, length: Optional[int] = None) -> list[float]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or not value
        or (length is not None and len(value) != length)
    ):
        raise ValueError("feature vector shape changed")
    if any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(float(item))
        for item in value
    ):
        raise ValueError("feature vector must contain finite numbers")
    return [float(item) for item in value]


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, value))))


def _verified(value: Mapping[str, Any], schema: str, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    document = dict(value)
    if document.get("schema") != schema:
        raise ValueError(f"unsupported {label} schema")
    supplied = _sha(document.get("document_sha256"), f"{label} document")
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if document_sha256(unsigned) != supplied:
        raise ValueError(f"{label} document hash changed")
    return document


def _safe_id(value: Any, label: str) -> str:
    text = str(value)
    if not _SAFE_ID.fullmatch(text):
        raise ValueError(f"{label} must be a safe path-free identifier")
    return text


def _sha(value: Any, label: str) -> str:
    text = str(value)
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{label} SHA-256 is invalid")
    return text


def _commit(value: Any) -> str:
    text = str(value)
    if not _COMMIT.fullmatch(text):
        raise ValueError("repository_commit must be a full Git commit")
    return text


__all__ = [
    "REMIX_FROZEN_FEATURE_MANIFEST_SCHEMA",
    "REMIX_FROZEN_FEATURE_VECTOR_SCHEMA",
    "REMIX_RANKER_BOUND_CHECKPOINT_SCHEMA",
    "REMIX_RANKER_BOUND_REQUEST_SCHEMA",
    "REMIX_RANKER_BOUND_RESULT_SCHEMA",
    "REMIX_SYNTHETIC_TRAINING_SNAPSHOT_SCHEMA",
    "build_synthetic_remix_training_snapshot",
    "create_remix_frozen_feature_manifest",
    "create_remix_ranker_training_request",
    "run_remix_ranker_training",
    "synthetic_frozen_values",
    "validate_remix_frozen_feature_manifest",
    "validate_remix_ranker_training_request",
    "validate_remix_ranker_training_result",
    "validate_synthetic_remix_training_snapshot",
    "write_frozen_feature_vector",
]
