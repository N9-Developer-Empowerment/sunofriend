from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

import pytest

from sunofriend.separation_acceptance import (
    SEPARATION_ACCEPTANCE_SCHEMA,
    SEPARATION_HIDDEN_MANIFEST_SCHEMA,
    canonical_json_bytes,
    deployment_profile_id,
    freeze_separation_acceptance_thresholds,
    load_separation_acceptance_thresholds,
    separation_acceptance_artifact_sha256,
    validate_separation_acceptance_thresholds,
    verify_hidden_evaluation_manifest,
)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _settings_hash(settings: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(settings)).hexdigest()


def _identity(
    identity_id: str,
    *,
    checkpoint: bool,
) -> dict[str, Any]:
    settings = {"batch_size": 1, "normalise": False}
    checkpoint_value: dict[str, Any]
    if checkpoint:
        checkpoint_value = {
            "kind": "checkpoint",
            "checkpoint_id": f"{identity_id}:checkpoint",
            "format": "safetensors",
            "sha256": _digest(f"{identity_id}:weights"),
            "bytes": 1_048_576,
            "weights_license_expression": "CC-BY-4.0",
            "weights_terms_sha256": _digest(
                f"{identity_id}:weights-terms"
            ),
        }
    else:
        checkpoint_value = {
            "kind": "deterministic-no-checkpoint",
            "reason_code": "deterministic-no-checkpoint",
        }
    return {
        "identity_id": identity_id,
        "backend_id": f"{identity_id}:backend",
        "package_name": "synthetic-package",
        "package_version": "1.2.3",
        "package_commit": _digest(f"{identity_id}:commit")[:40],
        "package_source_sha256": _digest(f"{identity_id}:source"),
        "worker_sha256": _digest(f"{identity_id}:worker"),
        "runtime": {
            "runtime_id": "cpython",
            "runtime_version": "3.11.13",
            "python_version": "3.11.13",
            "dependency_lock_sha256": _digest(
                f"{identity_id}:lock"
            ),
        },
        "device": {
            "platform": "macos",
            "machine": "arm64",
            "accelerator": "mps",
        },
        "checkpoint": checkpoint_value,
        "settings": settings,
        "settings_sha256": _settings_hash(settings),
        "seed_policy": "fixed-seed-per-song-role-v1",
        "code_license_expression": "Apache-2.0",
        "code_terms_sha256": _digest(f"{identity_id}:code-terms"),
        "training_data_license_expression": "CC-BY-4.0",
        "training_data_terms_sha256": _digest(
            f"{identity_id}:training-terms"
        ),
    }


def _higher(minimum: float = 0.7) -> dict[str, Any]:
    return {
        "direction": "higher_is_better",
        "aggregate_minimum_candidate": minimum,
        "aggregate_minimum_candidate_minus_baseline": 0.02,
        "per_song_minimum_candidate": max(0.0, minimum - 0.15),
        "per_song_minimum_candidate_minus_baseline": -0.05,
        "catastrophic_regression_limit": 0.1,
    }


def _timing(
    maximum: float,
    regression: float,
    catastrophic: float,
) -> dict[str, Any]:
    return {
        "direction": "lower_is_better",
        "aggregate_maximum_candidate": maximum,
        "aggregate_maximum_candidate_minus_baseline": regression,
        "per_song_maximum_candidate": maximum * 1.5,
        "per_song_maximum_candidate_minus_baseline": regression * 1.5,
        "catastrophic_regression_limit": catastrophic,
    }


def _pitched_role(role_id: str) -> dict[str, Any]:
    return {
        "role_prepared_id": role_id,
        "kind": "pitched",
        "minimum_ground_truth_pairs": 8,
        "catastrophic_failures_allowed": 0,
        "missing_or_nonfinite": "fail",
        "paired_policy": "paired-same-song-role-pair-v1",
        "aggregate_policy": (
            "median-over-eligible-song-role-pairs-v1"
        ),
        "metrics": {
            "onset_f1": _higher(),
            "exact_pitch_accuracy": _higher(0.65),
            "octave_accuracy": _higher(0.75),
            "onset_error_median_ms": _timing(50.0, 10.0, 80.0),
            "onset_error_p95_ms": _timing(120.0, 30.0, 200.0),
        },
    }


def _percussion_role(role_id: str) -> dict[str, Any]:
    return {
        "role_prepared_id": role_id,
        "kind": "percussion",
        "minimum_ground_truth_pairs": 8,
        "catastrophic_failures_allowed": 0,
        "missing_or_nonfinite": "fail",
        "paired_policy": "paired-same-song-role-pair-v1",
        "aggregate_policy": (
            "median-over-eligible-song-role-pairs-v1"
        ),
        "metrics": {
            "onset_f1": _higher(),
            "exact_pitch_accuracy": {
                "status": "not_applicable",
                "reason": "percussion-role",
            },
            "octave_accuracy": {
                "status": "not_applicable",
                "reason": "percussion-role",
            },
            "onset_error_median_ms": _timing(35.0, 8.0, 60.0),
            "onset_error_p95_ms": _timing(90.0, 20.0, 150.0),
            "drum_family_onset_f1": _higher(0.72),
        },
    }


def _manifest() -> tuple[dict[str, Any], dict[str, Any]]:
    development_identities = sorted(
        _digest(f"development-song-{index}") for index in range(12)
    )
    development_sources = sorted(
        _digest(f"development-source-{index}") for index in range(12)
    )
    development_split_id = "synthetic-development-split-v1"
    development_split_sha256 = hashlib.sha256(
        canonical_json_bytes(
            {
                "split_id": development_split_id,
                "song_identity_sha256s": development_identities,
                "source_sha256s": development_sources,
            }
        )
    ).hexdigest()
    songs: list[dict[str, Any]] = []
    groups = (
        ["acoustic"] * 4
        + ["electronic_ai_generated"] * 4
        + ["mixed"] * 4
    )
    for index, group in enumerate(groups):
        songs.append(
            {
                "song_id": f"hidden-song-{index:02d}",
                "song_identity_sha256": _digest(
                    f"hidden-song-identity-{index}"
                ),
                "group": group,
                "source_sha256": _digest(f"hidden-source-{index}"),
                "rights_profile_id": "synthetic-private-evaluation-v1",
                "rights_evidence_sha256": _digest(
                    f"hidden-rights-evidence-{index}"
                ),
                "authorised_for_evaluation": True,
                "roles": [
                    {
                        "role_prepared_id": "role-prepared:bass",
                        "ground_truth_sha256": _digest(
                            f"hidden-bass-{index}"
                        ),
                    },
                    {
                        "role_prepared_id": "role-prepared:kick",
                        "ground_truth_sha256": _digest(
                            f"hidden-kick-{index}"
                        ),
                    },
                ],
            }
        )
    split_id = "synthetic-hidden-split-v1"
    split_sha256 = hashlib.sha256(
        canonical_json_bytes(
            {"split_id": split_id, "songs": songs}
        )
    ).hexdigest()
    manifest = {
        "schema": SEPARATION_HIDDEN_MANIFEST_SCHEMA,
        "manifest_id": "synthetic-hidden-manifest-v1",
        "split_id": split_id,
        "dataset_id": "synthetic-private-dataset-v1",
        "dataset_license_expression": "LicenseRef-Synthetic-Evaluation",
        "dataset_terms_sha256": _digest("synthetic-dataset-terms"),
        "development_split_id": development_split_id,
        "development_split_sha256": development_split_sha256,
        "development_song_identity_sha256s": development_identities,
        "development_source_sha256s": development_sources,
        "songs": songs,
    }
    raw = canonical_json_bytes(manifest)
    expected = {
        "hidden": True,
        "manifest_id": manifest["manifest_id"],
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "split_id": split_id,
        "split_sha256": split_sha256,
        "total_songs": 12,
        "groups": {
            "acoustic": 4,
            "electronic_ai_generated": 4,
            "mixed": 4,
        },
        "unit": "unique-song-role-pair",
        "ground_truth_pairs_by_role": {
            "role-prepared:bass": 12,
            "role-prepared:kick": 12,
        },
        "dataset_id": manifest["dataset_id"],
        "dataset_license_expression": manifest[
            "dataset_license_expression"
        ],
        "dataset_terms_sha256": manifest["dataset_terms_sha256"],
        "authorised_for_evaluation": True,
        "excluded_development_split_id": development_split_id,
        "excluded_development_split_sha256": development_split_sha256,
    }
    return manifest, expected


def _licence_entries(
    identities: dict[str, Any],
    hidden: dict[str, Any],
    human: dict[str, Any],
) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    identity_values = [
        identities["candidate_separator"],
        identities["baseline_separator"],
        *identities["downstream_midi_by_role"].values(),
        identities["metric_evaluator"],
    ]
    for identity in identity_values:
        unique.setdefault(identity["identity_id"], identity)
    evidence: dict[str, dict[str, str]] = {}
    for identity_id, identity in unique.items():
        evidence[f"{identity_id}:code"] = {
            "component_kind": "code",
            "license_expression": identity["code_license_expression"],
            "terms_sha256": identity["code_terms_sha256"],
        }
        evidence[f"{identity_id}:training-data"] = {
            "component_kind": "dataset",
            "license_expression": identity[
                "training_data_license_expression"
            ],
            "terms_sha256": identity["training_data_terms_sha256"],
        }
        if identity["checkpoint"]["kind"] == "checkpoint":
            evidence[f"{identity_id}:weights"] = {
                "component_kind": "weights",
                "license_expression": identity["checkpoint"][
                    "weights_license_expression"
                ],
                "terms_sha256": identity["checkpoint"][
                    "weights_terms_sha256"
                ],
            }
    evidence[f"dataset:{hidden['dataset_id']}"] = {
        "component_kind": "dataset",
        "license_expression": hidden["dataset_license_expression"],
        "terms_sha256": hidden["dataset_terms_sha256"],
    }
    renderer = human["renderer"]
    evidence[f"renderer:{renderer['renderer_id']}:code"] = {
        "component_kind": "code",
        "license_expression": renderer["license_expression"],
        "terms_sha256": renderer["terms_sha256"],
    }
    soundfont = human["soundfont"]
    evidence[f"soundfont:{soundfont['soundfont_id']}"] = {
        "component_kind": "dataset",
        "license_expression": soundfont["license_expression"],
        "terms_sha256": soundfont["terms_sha256"],
    }
    level_matcher = human["level_matcher"]
    evidence[
        f"level-matcher:{level_matcher['level_matcher_id']}:code"
    ] = {
        "component_kind": "code",
        "license_expression": level_matcher["license_expression"],
        "terms_sha256": level_matcher["terms_sha256"],
    }
    return [
        {
            "subject_id": subject_id,
            **evidence[subject_id],
            "allowed_use": {
                "local_evaluation": True,
                "local_inference": True,
                "commercial_use": False,
            },
            "redistribution": {
                "component": False,
                "derived_outputs": True,
            },
        }
        for subject_id in sorted(evidence)
    ]


def _fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    manifest, hidden = _manifest()
    deployment = {
        "deployment_id": "synthetic-local-evaluation",
        "platform": "macos-local",
        "local_processing": True,
        "commercial_use_requested": False,
        "component_redistribution_requested": False,
        "derived_output_redistribution_requested": False,
        "components_bundled_with_apache_package": False,
    }
    profile_id = deployment_profile_id(deployment)
    candidate = _identity("candidate-separator", checkpoint=True)
    baseline = _identity("baseline-separator", checkpoint=True)
    midi = _identity("downstream-midi", checkpoint=False)
    evaluator = _identity("metric-evaluator", checkpoint=False)
    evaluator["seed_policy"] = "deterministic-no-randomness-v1"
    identities = {
        "candidate_separator": candidate,
        "baseline_separator": baseline,
        "downstream_midi_by_role": {
            "role-prepared:bass": midi,
            "role-prepared:kick": midi,
        },
        "metric_evaluator": evaluator,
    }
    human = {
        "blind": True,
        "level_matched": True,
        "renderer": {
            "renderer_id": "synthetic-renderer",
            "version": "1.0.0",
            "source_sha256": _digest("renderer-source"),
            "license_expression": "Apache-2.0",
            "terms_sha256": _digest("renderer-terms"),
        },
        "soundfont": {
            "soundfont_id": "synthetic-soundfont",
            "sha256": _digest("soundfont"),
            "license_expression": "CC0-1.0",
            "terms_sha256": _digest("soundfont-terms"),
        },
        "level_matcher": {
            "level_matcher_id": "synthetic-level-matcher",
            "version": "1.0.0",
            "source_sha256": _digest("level-matcher-source"),
            "license_expression": "Apache-2.0",
            "terms_sha256": _digest("level-matcher-terms"),
        },
        "assignment_policy": "blind-randomised-withheld-key-v1",
        "level_policy": "integrated-lufs-and-rms-matched-v1",
        "audition_window_policy": (
            "fixed-pre-registered-song-role-windows-v1"
        ),
        "audition_manifest_id": "synthetic-audition-manifest-v1",
        "audition_manifest_sha256": _digest("audition-manifest"),
        "assignment_seed_commitment_sha256": _digest(
            "assignment-seed-commitment"
        ),
        "answer_key_commitment_sha256": _digest(
            "answer-key-commitment"
        ),
        "loop_policy": "same-window-one-loop-before-response-v1",
        "label_policy": "opaque-random-labels-withheld-key-v1",
        "answer_key_separate": True,
        "response_policy": "candidate-baseline-cannot-tell-v1",
        "statistical_policy": {
            "valid_unit_policy": (
                "one-song-role-window-with-minimum-reviewers-v1"
            ),
            "reviewer_resolution_policy": (
                "strict-majority-ties-become-cannot-tell-v1"
            ),
            "cannot_tell_policy": (
                "included-as-equivalent-for-noninferiority-"
                "excluded-from-preference-v1"
            ),
            "noninferiority_test": (
                "one-sided-clopper-pearson-baseline-preferred-"
                "upper-bound-v1"
            ),
            "preference_test": (
                "one-sided-exact-binomial-candidate-vs-baseline-"
                "excluding-cannot-tell-v1"
            ),
        },
        "maximum_rms_mismatch_db": 0.5,
        "maximum_lufs_mismatch_lu": 0.5,
        "minimum_songs": 8,
        "minimum_roles": 2,
        "minimum_reviewers": 2,
        "minimum_valid_units": 16,
        "cannot_tell_share_max": 0.25,
        "noninferiority": {
            "required": True,
            "candidate_or_equivalent_share_min": 0.65,
            "baseline_preferred_share_max": 0.35,
            "confidence_level": 0.95,
            "alpha": 0.05,
        },
        "preference": {
            "claim_mode": "separate-preferred-claim-only",
            "candidate_preferred_count_min": 10,
            "candidate_preferred_share_min": 0.6,
            "exact_binomial_alpha": 0.05,
        },
    }
    document = freeze_separation_acceptance_thresholds(
        profile_id=profile_id,
        registration={
            "protocol": "pre-registered-before-hidden-evaluation-v1",
            "frozen_at_utc": "2026-07-29T12:00:00Z",
            "hidden_results_seen": False,
            "changes_after_freeze_allowed": False,
            "development_data_only_for_calibration": True,
            "development_split_id": hidden[
                "excluded_development_split_id"
            ],
            "development_split_sha256": hidden[
                "excluded_development_split_sha256"
            ],
        },
        deployment_profile=deployment,
        identities=identities,
        hidden_evaluation_set=hidden,
        role_promotion={
            "role-prepared:bass": _pitched_role(
                "role-prepared:bass"
            ),
            "role-prepared:kick": _percussion_role(
                "role-prepared:kick"
            ),
        },
        resource_gates={
            "protocol": "fresh-process-resource-measurement-v1",
            "repetitions": 3,
            "mac_classes": [
                {
                    "class_id": "apple-silicon-16gib",
                    "os_name": "macOS",
                    "os_version": "15.5",
                    "os_build": "24F74",
                    "runtime": "cpython-3.11.13",
                    "device": "mps",
                    "architecture": "arm64",
                    "hardware_family": "Apple silicon",
                    "unified_memory_gib": 16,
                    "wall_time_seconds_per_audio_minute_max": 120.0,
                    "single_song_wall_time_seconds_max": 900.0,
                    "peak_unified_memory_gib_max": 12.0,
                    "timeout_is_failure": True,
                    "oom_is_failure": True,
                }
            ],
        },
        offline_gate={
            "policy": "postinstall-os-deny-and-observe-v1",
            "explicit_install_completed": True,
            "implicit_downloads_allowed": False,
            "os_network_denial_enforced": True,
            "outbound_attempt_observation_enabled": True,
            "attempts": 2,
            "maximum_attempted_outbound_connections": 0,
            "maximum_successful_outbound_connections": 0,
            "any_failure_fails_gate": True,
        },
        human_listening=human,
        licence_gate={
            "deployment_profile_id": profile_id,
            "entries": _licence_entries(identities, hidden, human),
            "all_components_covered": True,
            "any_failure_fails_gate": True,
        },
        decision_rule={
            "policy": "conjunctive-role-specific-promotion-v1",
            "technical_metrics_required": True,
            "resource_gates_required": True,
            "offline_gate_required": True,
            "human_noninferiority_required": True,
            "licence_gate_required": True,
            "preference_claim_separate": True,
            "cross_role_averaging_allowed": False,
            "waivers_allowed": False,
            "promotion_scope": "role-specific",
            "missing_or_nonfinite": "fail",
        },
    )
    return json.loads(canonical_json_bytes(document)), manifest


def _rehash(document: dict[str, Any]) -> None:
    document["artifact_sha256"] = (
        separation_acceptance_artifact_sha256(document)
    )


def test_freeze_returns_valid_deeply_immutable_canonical_projection() -> None:
    document, _manifest_value = _fixture()
    checked = validate_separation_acceptance_thresholds(document)
    assert checked["schema"] == SEPARATION_ACCEPTANCE_SCHEMA
    assert checked["status"] == "frozen"
    with pytest.raises(TypeError):
        checked["status"] = "passed"  # type: ignore[index]
    with pytest.raises(TypeError):
        checked["offline_gate"]["attempts"] = 3  # type: ignore[index]
    assert isinstance(checked["resource_gates"]["mac_classes"], tuple)


def test_artifact_hash_detects_tamper_and_excludes_only_self_hash() -> None:
    document, _manifest_value = _fixture()
    original_hash = document["artifact_sha256"]
    document["artifact_sha256"] = _digest("arbitrary-self-hash")
    assert separation_acceptance_artifact_sha256(document) == original_hash
    document["offline_gate"]["attempts"] = 3
    with pytest.raises(ValueError, match="artifact_sha256"):
        validate_separation_acceptance_thresholds(document)


@pytest.mark.parametrize("placeholder", ["TBD", "unknown", "placeholder"])
def test_placeholders_are_rejected(placeholder: str) -> None:
    document, _manifest_value = _fixture()
    document["identities"]["candidate_separator"][
        "package_name"
    ] = placeholder
    with pytest.raises(ValueError, match="placeholder"):
        separation_acceptance_artifact_sha256(document)


def test_identity_and_settings_drift_fail_closed() -> None:
    document, _manifest_value = _fixture()
    document["identities"]["candidate_separator"][
        "package_version"
    ] = "9.9.9"
    _rehash(document)
    validate_separation_acceptance_thresholds(document)
    document["identities"]["candidate_separator"]["settings"][
        "batch_size"
    ] = 2
    _rehash(document)
    with pytest.raises(ValueError, match="settings_sha256"):
        validate_separation_acceptance_thresholds(document)


@pytest.mark.parametrize(
    ("setting_key", "setting_value"),
    [
        ("checkpoint_path", "/Users/example/private/model.bin"),
        ("model_url", "https://example.invalid/model"),
        ("api_key", "private-credential"),
        ("access-token", "private-credential"),
        ("model_id", "../private/model"),
    ],
)
def test_identity_settings_reject_paths_urls_and_secret_fields(
    setting_key: str,
    setting_value: str,
) -> None:
    document, _manifest_value = _fixture()
    settings = document["identities"]["candidate_separator"]["settings"]
    settings[setting_key] = setting_value
    document["identities"]["candidate_separator"]["settings_sha256"] = (
        _settings_hash(settings)
    )
    with pytest.raises(ValueError, match="private|path|URL|secret"):
        _rehash(document)
        validate_separation_acceptance_thresholds(document)


def test_candidate_and_baseline_must_be_operationally_distinct() -> None:
    document, _manifest_value = _fixture()
    candidate = document["identities"]["candidate_separator"]
    baseline = copy.deepcopy(candidate)
    baseline["identity_id"] = "relabeled-baseline"
    baseline["backend_id"] = "relabeled-baseline:backend"
    document["identities"]["baseline_separator"] = baseline
    document["licence_gate"]["entries"] = _licence_entries(
        document["identities"],
        document["hidden_evaluation_set"],
        document["human_listening"],
    )
    _rehash(document)
    with pytest.raises(ValueError, match="operationally distinct"):
        validate_separation_acceptance_thresholds(document)


def test_public_artifact_rejects_paths_and_urls_outside_settings() -> None:
    document, _manifest_value = _fixture()
    document["identities"]["candidate_separator"]["identity_id"] = (
        "candidate:/users/alice/private-model"
    )
    with pytest.raises(ValueError, match="private path or URL"):
        separation_acceptance_artifact_sha256(document)

    document, _manifest_value = _fixture()
    document["human_listening"]["renderer"]["license_expression"] = (
        "https://example.invalid/private-terms"
    )
    with pytest.raises(ValueError, match="private path or URL"):
        separation_acceptance_artifact_sha256(document)


def test_metric_evaluator_must_have_no_randomness() -> None:
    document, _manifest_value = _fixture()
    document["identities"]["metric_evaluator"]["seed_policy"] = (
        "fixed-seed-per-song-role-v1"
    )
    _rehash(document)
    with pytest.raises(ValueError, match="deterministic-no-randomness"):
        validate_separation_acceptance_thresholds(document)


def test_python_312_is_a_valid_isolated_worker_identity() -> None:
    document, _manifest_value = _fixture()
    runtime = document["identities"]["candidate_separator"]["runtime"]
    runtime["runtime_version"] = "3.12.4"
    runtime["python_version"] = "3.12.4"
    document["resource_gates"]["mac_classes"][0]["runtime"] = (
        "cpython-3.12.4"
    )
    _rehash(document)
    validate_separation_acceptance_thresholds(document)


def test_hidden_coverage_and_role_aliases_fail_closed() -> None:
    document, _manifest_value = _fixture()
    document["hidden_evaluation_set"]["groups"]["acoustic"] = 3
    document["hidden_evaluation_set"]["groups"]["mixed"] = 5
    _rehash(document)
    with pytest.raises(ValueError, match="four songs"):
        validate_separation_acceptance_thresholds(document)
    document, _manifest_value = _fixture()
    role = document["role_promotion"].pop("role-prepared:bass")
    document["role_promotion"]["role-prepared:basses"] = role
    _rehash(document)
    with pytest.raises(ValueError, match="role-prepared"):
        validate_separation_acceptance_thresholds(document)


def test_metric_direction_nonfinite_and_catastrophic_waiver_rejected() -> None:
    document, _manifest_value = _fixture()
    onset = document["role_promotion"]["role-prepared:bass"]["metrics"][
        "onset_f1"
    ]
    onset["direction"] = "lower_is_better"
    _rehash(document)
    with pytest.raises(ValueError, match="higher_is_better"):
        validate_separation_acceptance_thresholds(document)
    document, _manifest_value = _fixture()
    document["role_promotion"]["role-prepared:bass"][
        "catastrophic_failures_allowed"
    ] = 1
    _rehash(document)
    with pytest.raises(ValueError, match="exactly zero"):
        validate_separation_acceptance_thresholds(document)
    document, _manifest_value = _fixture()
    document["human_listening"]["maximum_rms_mismatch_db"] = math.inf
    with pytest.raises(ValueError, match="non-finite"):
        separation_acceptance_artifact_sha256(document)


def test_policy_numbers_have_one_canonical_json_type() -> None:
    document, _manifest_value = _fixture()
    document["human_listening"]["maximum_rms_mismatch_db"] = 1
    _rehash(document)
    with pytest.raises(ValueError, match="JSON float"):
        validate_separation_acceptance_thresholds(document)

    document, _manifest_value = _fixture()
    document["human_listening"]["maximum_rms_mismatch_db"] = -0.0
    _rehash(document)
    with pytest.raises(ValueError, match="negative zero"):
        validate_separation_acceptance_thresholds(document)


def test_boolean_values_cannot_masquerade_as_zero_counts() -> None:
    document, _manifest_value = _fixture()
    document["role_promotion"]["role-prepared:bass"][
        "catastrophic_failures_allowed"
    ] = False
    _rehash(document)
    with pytest.raises(ValueError, match="integer"):
        validate_separation_acceptance_thresholds(document)

    document, _manifest_value = _fixture()
    document["offline_gate"][
        "maximum_attempted_outbound_connections"
    ] = False
    _rehash(document)
    with pytest.raises(ValueError, match="integer"):
        validate_separation_acceptance_thresholds(document)


def test_percussion_pitch_metrics_must_be_explicit_not_applicable() -> None:
    document, _manifest_value = _fixture()
    document["role_promotion"]["role-prepared:kick"]["metrics"][
        "exact_pitch_accuracy"
    ] = _higher()
    _rehash(document)
    with pytest.raises(ValueError, match="not_applicable"):
        validate_separation_acceptance_thresholds(document)


def test_resource_gate_requires_exact_16_gib_arm64_class() -> None:
    document, _manifest_value = _fixture()
    document["resource_gates"]["mac_classes"][0][
        "unified_memory_gib"
    ] = 24
    _rehash(document)
    with pytest.raises(ValueError, match="16 GiB"):
        validate_separation_acceptance_thresholds(document)


def test_resource_gate_is_bound_to_candidate_runtime_and_device() -> None:
    document, _manifest_value = _fixture()
    document["resource_gates"]["mac_classes"][0]["runtime"] = (
        "cpython-3.10.0"
    )
    _rehash(document)
    with pytest.raises(ValueError, match="candidate separator"):
        validate_separation_acceptance_thresholds(document)


@pytest.mark.parametrize(
    ("field_name", "weakened"),
    [
        ("implicit_downloads_allowed", True),
        ("os_network_denial_enforced", False),
        ("outbound_attempt_observation_enabled", False),
        ("maximum_attempted_outbound_connections", 1),
        ("maximum_successful_outbound_connections", 1),
        ("any_failure_fails_gate", False),
    ],
)
def test_offline_gate_cannot_be_weakened(
    field_name: str,
    weakened: Any,
) -> None:
    document, _manifest_value = _fixture()
    document["offline_gate"][field_name] = weakened
    _rehash(document)
    with pytest.raises(ValueError):
        validate_separation_acceptance_thresholds(document)


def test_licence_coverage_identity_and_deployment_permissions_are_bound() -> None:
    document, _manifest_value = _fixture()
    document["licence_gate"]["entries"].pop()
    _rehash(document)
    with pytest.raises(ValueError, match="coverage mismatch"):
        validate_separation_acceptance_thresholds(document)
    document, _manifest_value = _fixture()
    document["licence_gate"]["entries"][0]["terms_sha256"] = _digest(
        "drift"
    )
    _rehash(document)
    with pytest.raises(ValueError, match="identity drift"):
        validate_separation_acceptance_thresholds(document)
    document, _manifest_value = _fixture()
    document["deployment_profile"]["commercial_use_requested"] = True
    document["profile_id"] = deployment_profile_id(
        document["deployment_profile"]
    )
    document["licence_gate"]["deployment_profile_id"] = document[
        "profile_id"
    ]
    _rehash(document)
    with pytest.raises(ValueError, match="commercial use"):
        validate_separation_acceptance_thresholds(document)


def test_human_rule_requires_blind_level_matching_and_separate_preference() -> None:
    document, _manifest_value = _fixture()
    document["human_listening"]["answer_key_separate"] = False
    _rehash(document)
    with pytest.raises(ValueError, match="answer_key_separate"):
        validate_separation_acceptance_thresholds(document)
    document, _manifest_value = _fixture()
    document["human_listening"]["noninferiority"]["required"] = False
    _rehash(document)
    with pytest.raises(ValueError, match="required"):
        validate_separation_acceptance_thresholds(document)
    document, _manifest_value = _fixture()
    document["human_listening"]["preference"][
        "claim_mode"
    ] = "promotion-gate"
    _rehash(document)
    with pytest.raises(ValueError, match="separate claim"):
        validate_separation_acceptance_thresholds(document)


def test_human_window_assignment_answer_and_statistics_are_committed() -> None:
    document, _manifest_value = _fixture()
    document["human_listening"][
        "answer_key_commitment_sha256"
    ] = document["human_listening"]["audition_manifest_sha256"]
    _rehash(document)
    with pytest.raises(ValueError, match="distinct hashes"):
        validate_separation_acceptance_thresholds(document)

    document, _manifest_value = _fixture()
    document["human_listening"]["statistical_policy"][
        "cannot_tell_policy"
    ] = "discard-all-cannot-tell-v1"
    _rehash(document)
    with pytest.raises(ValueError, match="statistical policy"):
        validate_separation_acceptance_thresholds(document)


def test_registration_timestamp_must_be_a_real_date() -> None:
    document, _manifest_value = _fixture()
    document["registration"]["frozen_at_utc"] = "2026-99-99T99:99:99Z"
    _rehash(document)
    with pytest.raises(ValueError, match="real whole-second"):
        validate_separation_acceptance_thresholds(document)


def test_profile_hash_mismatch_is_rejected() -> None:
    document, _manifest_value = _fixture()
    document["deployment_profile"]["deployment_id"] = (
        "different-deployment"
    )
    _rehash(document)
    with pytest.raises(ValueError, match="profile_id"):
        validate_separation_acceptance_thresholds(document)


def test_bounded_canonical_load_rejects_duplicates_and_symlinks(
    tmp_path: Path,
) -> None:
    document, _manifest_value = _fixture()
    artifact = tmp_path / "acceptance.json"
    artifact.write_bytes(canonical_json_bytes(document))
    loaded = load_separation_acceptance_thresholds(artifact)
    assert loaded["artifact_sha256"] == document["artifact_sha256"]

    noncanonical = tmp_path / "noncanonical.json"
    noncanonical.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical"):
        load_separation_acceptance_thresholds(noncanonical)

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema":"x","schema":"y"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_separation_acceptance_thresholds(duplicate)

    symlink = tmp_path / "link.json"
    try:
        os.symlink(artifact, symlink)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable")
    with pytest.raises(ValueError, match="non-symlink"):
        load_separation_acceptance_thresholds(symlink)


def test_hidden_manifest_is_rehashed_and_counts_are_derived(
    tmp_path: Path,
) -> None:
    document, manifest = _fixture()
    path = tmp_path / "hidden-manifest.json"
    path.write_bytes(canonical_json_bytes(manifest))
    derived = verify_hidden_evaluation_manifest(
        path,
        acceptance_artifact=document,
    )
    assert derived["total_songs"] == 12
    assert derived["groups"]["electronic_ai_generated"] == 4
    assert derived["ground_truth_pairs_by_role"][
        "role-prepared:kick"
    ] == 12


def test_hidden_manifest_rejects_claim_tamper_and_development_overlap(
    tmp_path: Path,
) -> None:
    document, manifest = _fixture()
    path = tmp_path / "hidden-manifest.json"
    manifest["songs"][0]["group"] = "mixed"
    path.write_bytes(canonical_json_bytes(manifest))
    with pytest.raises(ValueError, match="groups"):
        verify_hidden_evaluation_manifest(
            path,
            acceptance_artifact=document,
        )

    document, manifest = _fixture()
    manifest["songs"][0]["song_identity_sha256"] = manifest[
        "development_song_identity_sha256s"
    ][0]
    path.write_bytes(canonical_json_bytes(manifest))
    with pytest.raises(ValueError, match="must not overlap"):
        verify_hidden_evaluation_manifest(
            path,
            acceptance_artifact=document,
        )


def test_hidden_manifest_rejects_source_overlap_and_duplicate_sources(
    tmp_path: Path,
) -> None:
    document, manifest = _fixture()
    path = tmp_path / "hidden-manifest.json"
    manifest["songs"][0]["source_sha256"] = manifest[
        "development_source_sha256s"
    ][0]
    path.write_bytes(canonical_json_bytes(manifest))
    with pytest.raises(ValueError, match="source audio must not overlap"):
        verify_hidden_evaluation_manifest(
            path,
            acceptance_artifact=document,
        )

    document, manifest = _fixture()
    manifest["songs"][1]["source_sha256"] = manifest["songs"][0][
        "source_sha256"
    ]
    path.write_bytes(canonical_json_bytes(manifest))
    with pytest.raises(ValueError, match="source hashes must be unique"):
        verify_hidden_evaluation_manifest(
            path,
            acceptance_artifact=document,
        )


def test_hidden_manifest_requires_independent_ground_truth_per_role(
    tmp_path: Path,
) -> None:
    document, manifest = _fixture()
    first_bass_hash = manifest["songs"][0]["roles"][0][
        "ground_truth_sha256"
    ]
    manifest["songs"][1]["roles"][0][
        "ground_truth_sha256"
    ] = first_bass_hash
    path = tmp_path / "hidden-manifest.json"
    path.write_bytes(canonical_json_bytes(manifest))
    with pytest.raises(ValueError, match="independent hashes"):
        verify_hidden_evaluation_manifest(
            path,
            acceptance_artifact=document,
        )


def test_hidden_manifest_requires_per_song_evaluation_rights(
    tmp_path: Path,
) -> None:
    document, manifest = _fixture()
    manifest["songs"][0]["authorised_for_evaluation"] = False
    path = tmp_path / "hidden-manifest.json"
    path.write_bytes(canonical_json_bytes(manifest))
    with pytest.raises(ValueError, match="authorised_for_evaluation"):
        verify_hidden_evaluation_manifest(
            path,
            acceptance_artifact=document,
        )


def test_manifest_verifier_requires_the_complete_untampered_artifact(
    tmp_path: Path,
) -> None:
    document, manifest = _fixture()
    document["offline_gate"]["attempts"] = 3
    path = tmp_path / "hidden-manifest.json"
    path.write_bytes(canonical_json_bytes(manifest))
    with pytest.raises(ValueError, match="artifact_sha256"):
        verify_hidden_evaluation_manifest(
            path,
            acceptance_artifact=document,
        )


def test_manifest_role_counts_below_eight_fail_even_if_claimed(
    tmp_path: Path,
) -> None:
    document, manifest = _fixture()
    for song in manifest["songs"][7:]:
        song["roles"] = [
            role
            for role in song["roles"]
            if role["role_prepared_id"] != "role-prepared:kick"
        ]
    manifest["split_sha256"] = _digest("not-a-schema-field")
    path = tmp_path / "hidden-manifest.json"
    path.write_bytes(canonical_json_bytes(manifest))
    with pytest.raises(ValueError):
        verify_hidden_evaluation_manifest(
            path,
            acceptance_artifact=document,
        )
