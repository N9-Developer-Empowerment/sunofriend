"""Frozen acceptance contracts for separation-backend promotion.

This module is deliberately independent of audio, model and numerical
libraries.  It defines the evidence that must be registered *before* a hidden
separation evaluation begins.  It does not choose thresholds, install a model,
run an evaluation or ship a production profile.

The contract has two important hashes:

* ``profile_id`` is the SHA-256 identity of the deployment profile; and
* ``artifact_sha256`` is the SHA-256 identity of the complete acceptance
  document excluding only that self-hash field.

Hidden-set coverage is never accepted from claims alone.  Call
``verify_hidden_evaluation_manifest`` with the complete frozen artifact and
the canonical manifest file to rehash it and derive song, group and
song-role-pair counts from the manifest records.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import unicodedata
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .source_roles import prepared_source_role_ids


SEPARATION_ACCEPTANCE_SCHEMA = (
    "sunofriend.separation-acceptance-thresholds.v1"
)
SEPARATION_HIDDEN_MANIFEST_SCHEMA = (
    "sunofriend.separation-hidden-evaluation-manifest.v1"
)
SEPARATION_ACCEPTANCE_AGGREGATE_POLICY = (
    "median-over-eligible-song-role-pairs-v1"
)
SEPARATION_ACCEPTANCE_PAIRED_POLICY = "paired-same-song-role-pair-v1"
SEPARATION_ACCEPTANCE_OFFLINE_POLICY = (
    "postinstall-os-deny-and-observe-v1"
)
SEPARATION_ACCEPTANCE_DECISION_POLICY = (
    "conjunctive-role-specific-promotion-v1"
)

MAX_ACCEPTANCE_BYTES = 2 * 1024 * 1024
MAX_HIDDEN_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_HIDDEN_SONGS = 10_000
MAX_GROUND_TRUTH_ROLES_PER_SONG = 64

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PROFILE_ID_RE = re.compile(r"^separation-profile:[0-9a-f]{64}$")
_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._+:/-]{0,191}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{7,64}$")
_VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._+-]{0,63}$")
_OS_BUILD_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,63}$")
_SETTING_TEXT_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._+:/-]{0,191}$"
)
_PRIVATE_SETTING_KEY_RE = re.compile(
    r"(?:^|_)(?:api_key|apikey|authorization|credential|password|path|"
    r"secret|token|uri|url)(?:$|_)",
    re.IGNORECASE,
)
_WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")
_PYTHON_VERSION_RE = re.compile(
    r"^3\.(?:9|10|11|12)(?:\.[0-9]+)?$"
)
_UTC_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)
_ROLE_PREPARED_RE = re.compile(
    r"^role-prepared:([a-z][a-z0-9_]*)$"
)
_FORBIDDEN_TEXT = frozenset(
    {
        "changeme",
        "n/a",
        "na",
        "none",
        "null",
        "placeholder",
        "tbd",
        "todo",
        "unknown",
    }
)
_GROUPS = (
    "acoustic",
    "electronic_ai_generated",
    "mixed",
)
_PERCUSSION_ROLES = frozenset(
    {
        "cymbals",
        "drums",
        "hat",
        "kick",
        "other_kit",
        "snare",
        "toms",
    }
)
_TOP_FIELDS = frozenset(
    {
        "schema",
        "status",
        "profile_id",
        "artifact_sha256",
        "registration",
        "deployment_profile",
        "identities",
        "hidden_evaluation_set",
        "role_promotion",
        "resource_gates",
        "offline_gate",
        "human_listening",
        "licence_gate",
        "decision_rule",
    }
)
_REGISTRATION_FIELDS = frozenset(
    {
        "protocol",
        "frozen_at_utc",
        "hidden_results_seen",
        "changes_after_freeze_allowed",
        "development_data_only_for_calibration",
        "development_split_id",
        "development_split_sha256",
    }
)
_DEPLOYMENT_FIELDS = frozenset(
    {
        "deployment_id",
        "platform",
        "local_processing",
        "commercial_use_requested",
        "component_redistribution_requested",
        "derived_output_redistribution_requested",
        "components_bundled_with_apache_package",
    }
)
_IDENTITIES_FIELDS = frozenset(
    {
        "candidate_separator",
        "baseline_separator",
        "downstream_midi_by_role",
        "metric_evaluator",
    }
)
_IDENTITY_FIELDS = frozenset(
    {
        "identity_id",
        "backend_id",
        "package_name",
        "package_version",
        "package_commit",
        "package_source_sha256",
        "worker_sha256",
        "runtime",
        "device",
        "checkpoint",
        "settings",
        "settings_sha256",
        "seed_policy",
        "code_license_expression",
        "code_terms_sha256",
        "training_data_license_expression",
        "training_data_terms_sha256",
    }
)
_RUNTIME_FIELDS = frozenset(
    {
        "runtime_id",
        "runtime_version",
        "python_version",
        "dependency_lock_sha256",
    }
)
_DEVICE_FIELDS = frozenset({"platform", "machine", "accelerator"})
_CHECKPOINT_FIELDS = frozenset(
    {
        "kind",
        "checkpoint_id",
        "format",
        "sha256",
        "bytes",
        "weights_license_expression",
        "weights_terms_sha256",
    }
)
_NO_CHECKPOINT_FIELDS = frozenset({"kind", "reason_code"})
_HIDDEN_FIELDS = frozenset(
    {
        "hidden",
        "manifest_id",
        "manifest_sha256",
        "split_id",
        "split_sha256",
        "total_songs",
        "groups",
        "unit",
        "ground_truth_pairs_by_role",
        "dataset_id",
        "dataset_license_expression",
        "dataset_terms_sha256",
        "authorised_for_evaluation",
        "excluded_development_split_id",
        "excluded_development_split_sha256",
    }
)
_ROLE_PROMOTION_FIELDS = frozenset(
    {
        "role_prepared_id",
        "kind",
        "minimum_ground_truth_pairs",
        "catastrophic_failures_allowed",
        "missing_or_nonfinite",
        "paired_policy",
        "aggregate_policy",
        "metrics",
    }
)
_PITCHED_METRICS = frozenset(
    {
        "onset_f1",
        "exact_pitch_accuracy",
        "octave_accuracy",
        "onset_error_median_ms",
        "onset_error_p95_ms",
    }
)
_PERCUSSION_METRICS = frozenset(
    set(_PITCHED_METRICS) | {"drum_family_onset_f1"}
)
_HIGHER_FIELDS = frozenset(
    {
        "direction",
        "aggregate_minimum_candidate",
        "aggregate_minimum_candidate_minus_baseline",
        "per_song_minimum_candidate",
        "per_song_minimum_candidate_minus_baseline",
        "catastrophic_regression_limit",
    }
)
_TIMING_FIELDS = frozenset(
    {
        "direction",
        "aggregate_maximum_candidate",
        "aggregate_maximum_candidate_minus_baseline",
        "per_song_maximum_candidate",
        "per_song_maximum_candidate_minus_baseline",
        "catastrophic_regression_limit",
    }
)
_NOT_APPLICABLE_FIELDS = frozenset({"status", "reason"})
_RESOURCE_FIELDS = frozenset(
    {"protocol", "repetitions", "mac_classes"}
)
_MAC_CLASS_FIELDS = frozenset(
    {
        "class_id",
        "os_name",
        "os_version",
        "os_build",
        "runtime",
        "device",
        "architecture",
        "hardware_family",
        "unified_memory_gib",
        "wall_time_seconds_per_audio_minute_max",
        "single_song_wall_time_seconds_max",
        "peak_unified_memory_gib_max",
        "timeout_is_failure",
        "oom_is_failure",
    }
)
_OFFLINE_FIELDS = frozenset(
    {
        "policy",
        "explicit_install_completed",
        "implicit_downloads_allowed",
        "os_network_denial_enforced",
        "outbound_attempt_observation_enabled",
        "attempts",
        "maximum_attempted_outbound_connections",
        "maximum_successful_outbound_connections",
        "any_failure_fails_gate",
    }
)
_HUMAN_FIELDS = frozenset(
    {
        "blind",
        "level_matched",
        "renderer",
        "soundfont",
        "level_matcher",
        "assignment_policy",
        "level_policy",
        "audition_window_policy",
        "audition_manifest_id",
        "audition_manifest_sha256",
        "assignment_seed_commitment_sha256",
        "answer_key_commitment_sha256",
        "loop_policy",
        "label_policy",
        "answer_key_separate",
        "response_policy",
        "statistical_policy",
        "maximum_rms_mismatch_db",
        "maximum_lufs_mismatch_lu",
        "minimum_songs",
        "minimum_roles",
        "minimum_reviewers",
        "minimum_valid_units",
        "cannot_tell_share_max",
        "noninferiority",
        "preference",
    }
)
_RENDERER_FIELDS = frozenset(
    {
        "renderer_id",
        "version",
        "source_sha256",
        "license_expression",
        "terms_sha256",
    }
)
_SOUNDFONT_FIELDS = frozenset(
    {
        "soundfont_id",
        "sha256",
        "license_expression",
        "terms_sha256",
    }
)
_LEVEL_MATCHER_FIELDS = frozenset(
    {
        "level_matcher_id",
        "version",
        "source_sha256",
        "license_expression",
        "terms_sha256",
    }
)
_STATISTICAL_POLICY_FIELDS = frozenset(
    {
        "valid_unit_policy",
        "reviewer_resolution_policy",
        "cannot_tell_policy",
        "noninferiority_test",
        "preference_test",
    }
)
_NONINFERIORITY_FIELDS = frozenset(
    {
        "required",
        "candidate_or_equivalent_share_min",
        "baseline_preferred_share_max",
        "confidence_level",
        "alpha",
    }
)
_PREFERENCE_FIELDS = frozenset(
    {
        "claim_mode",
        "candidate_preferred_count_min",
        "candidate_preferred_share_min",
        "exact_binomial_alpha",
    }
)
_LICENCE_FIELDS = frozenset(
    {
        "deployment_profile_id",
        "entries",
        "all_components_covered",
        "any_failure_fails_gate",
    }
)
_LICENCE_ENTRY_FIELDS = frozenset(
    {
        "subject_id",
        "component_kind",
        "license_expression",
        "terms_sha256",
        "allowed_use",
        "redistribution",
    }
)
_ALLOWED_USE_FIELDS = frozenset(
    {"local_evaluation", "local_inference", "commercial_use"}
)
_REDISTRIBUTION_FIELDS = frozenset(
    {"component", "derived_outputs"}
)
_DECISION_FIELDS = frozenset(
    {
        "policy",
        "technical_metrics_required",
        "resource_gates_required",
        "offline_gate_required",
        "human_noninferiority_required",
        "licence_gate_required",
        "preference_claim_separate",
        "cross_role_averaging_allowed",
        "waivers_allowed",
        "promotion_scope",
        "missing_or_nonfinite",
    }
)
_MANIFEST_FIELDS = frozenset(
    {
        "schema",
        "manifest_id",
        "split_id",
        "dataset_id",
        "dataset_license_expression",
        "dataset_terms_sha256",
        "development_split_id",
        "development_split_sha256",
        "development_song_identity_sha256s",
        "development_source_sha256s",
        "songs",
    }
)
_MANIFEST_SONG_FIELDS = frozenset(
    {
        "song_id",
        "song_identity_sha256",
        "group",
        "source_sha256",
        "rights_profile_id",
        "rights_evidence_sha256",
        "authorised_for_evaluation",
        "roles",
    }
)
_MANIFEST_ROLE_FIELDS = frozenset(
    {"role_prepared_id", "ground_truth_sha256"}
)


def canonical_json_bytes(document: Mapping[str, Any]) -> bytes:
    """Return the repository's stable JSON representation."""

    return (
        json.dumps(
            _plain(document),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def separation_acceptance_artifact_sha256(
    document: Mapping[str, Any],
) -> str:
    """Hash an acceptance artifact excluding only its self-hash field."""

    payload = _plain(_mapping(document, "acceptance artifact"))
    payload.pop("artifact_sha256", None)
    _reject_invalid_tree(payload, "acceptance artifact")
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def deployment_profile_id(profile: Mapping[str, Any]) -> str:
    """Return the content identity for one strict deployment profile."""

    checked = _mapping(profile, "deployment_profile")
    _exact_fields(checked, _DEPLOYMENT_FIELDS, "deployment_profile")
    _reject_invalid_tree(checked, "deployment_profile")
    digest = hashlib.sha256(canonical_json_bytes(checked)).hexdigest()
    return f"separation-profile:{digest}"


def freeze_separation_acceptance_thresholds(
    *,
    profile_id: str,
    registration: Mapping[str, Any],
    deployment_profile: Mapping[str, Any],
    identities: Mapping[str, Any],
    hidden_evaluation_set: Mapping[str, Any],
    role_promotion: Mapping[str, Any],
    resource_gates: Mapping[str, Any],
    offline_gate: Mapping[str, Any],
    human_listening: Mapping[str, Any],
    licence_gate: Mapping[str, Any],
    decision_rule: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Construct, self-hash and validate a frozen acceptance artifact.

    Every input is required and keyword-only.  This helper intentionally has
    no threshold defaults: choosing numbers is a pre-registration decision,
    not a library policy.
    """

    document = {
        "schema": SEPARATION_ACCEPTANCE_SCHEMA,
        "status": "frozen",
        "profile_id": profile_id,
        "artifact_sha256": "",
        "registration": _plain(registration),
        "deployment_profile": _plain(deployment_profile),
        "identities": _plain(identities),
        "hidden_evaluation_set": _plain(hidden_evaluation_set),
        "role_promotion": _plain(role_promotion),
        "resource_gates": _plain(resource_gates),
        "offline_gate": _plain(offline_gate),
        "human_listening": _plain(human_listening),
        "licence_gate": _plain(licence_gate),
        "decision_rule": _plain(decision_rule),
    }
    document["artifact_sha256"] = (
        separation_acceptance_artifact_sha256(document)
    )
    return validate_separation_acceptance_thresholds(document)


def validate_separation_acceptance_thresholds(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Validate and return an immutable canonical copy."""

    value = _plain(_mapping(document, "acceptance artifact"))
    _exact_fields(value, _TOP_FIELDS, "acceptance artifact")
    _reject_invalid_tree(value, "acceptance artifact")
    if value["schema"] != SEPARATION_ACCEPTANCE_SCHEMA:
        raise ValueError("unsupported separation acceptance schema")
    if value["status"] != "frozen":
        raise ValueError("acceptance status must be frozen")
    profile_id = _profile_id(value["profile_id"], "profile_id")
    artifact_hash = _sha256(
        value["artifact_sha256"], "artifact_sha256"
    )

    deployment = _validate_deployment_profile(
        value["deployment_profile"]
    )
    if profile_id != deployment_profile_id(deployment):
        raise ValueError("profile_id does not match deployment_profile")
    registration = _validate_registration(value["registration"])
    identities = _validate_identities(value["identities"])
    hidden = _validate_hidden_evaluation_set(
        value["hidden_evaluation_set"]
    )
    if (
        hidden["excluded_development_split_id"]
        != registration["development_split_id"]
        or hidden["excluded_development_split_sha256"]
        != registration["development_split_sha256"]
    ):
        raise ValueError(
            "hidden set does not bind the registered development split"
        )
    if hidden["split_id"] == registration["development_split_id"]:
        raise ValueError("development and hidden split IDs must differ")
    if hidden["split_sha256"] == registration["development_split_sha256"]:
        raise ValueError("development and hidden split hashes must differ")
    roles = _validate_role_promotion(value["role_promotion"])
    if set(identities["downstream_midi_by_role"]) != set(roles):
        raise ValueError(
            "downstream_midi_by_role must exactly match promoted roles"
        )
    for role_id, role in roles.items():
        claimed = hidden["ground_truth_pairs_by_role"].get(role_id)
        if claimed is None or claimed < role["minimum_ground_truth_pairs"]:
            raise ValueError(
                f"hidden coverage is insufficient for {role_id}"
            )
    resources = _validate_resource_gates(
        value["resource_gates"],
        candidate_identity=identities["candidate_separator"],
    )
    _validate_offline_gate(value["offline_gate"])
    human = _validate_human_listening(value["human_listening"])
    if human["minimum_songs"] > hidden["total_songs"]:
        raise ValueError(
            "human listening minimum_songs exceeds the hidden set"
        )
    if human["minimum_roles"] > len(roles):
        raise ValueError(
            "human listening minimum_roles exceeds promoted roles"
        )
    if human["minimum_valid_units"] < (
        human["minimum_songs"] * human["minimum_roles"]
    ):
        raise ValueError(
            "human listening minimum_valid_units is too small"
        )
    _validate_licence_gate(
        value["licence_gate"],
        profile_id=profile_id,
        deployment=deployment,
        identities=identities,
        hidden=hidden,
        human=human,
    )
    _validate_decision_rule(value["decision_rule"])
    if not resources:
        raise ValueError("at least one resource gate is required")
    expected_hash = separation_acceptance_artifact_sha256(value)
    if artifact_hash != expected_hash:
        raise ValueError("artifact_sha256 does not match acceptance artifact")
    return _freeze(value)


def load_separation_acceptance_thresholds(
    path: str | Path,
    *,
    maximum_bytes: int = MAX_ACCEPTANCE_BYTES,
) -> Mapping[str, Any]:
    """Load a bounded canonical regular file and validate it."""

    value, raw = _load_canonical_json(
        path,
        maximum_bytes=maximum_bytes,
        label="separation acceptance artifact",
    )
    checked = validate_separation_acceptance_thresholds(value)
    if raw != canonical_json_bytes(checked):
        raise ValueError(
            "separation acceptance artifact is not canonical JSON"
        )
    return checked


def verify_hidden_evaluation_manifest(
    path: str | Path,
    *,
    acceptance_artifact: Mapping[str, Any],
    maximum_bytes: int = MAX_HIDDEN_MANIFEST_BYTES,
) -> Mapping[str, Any]:
    """Rehash a strict hidden manifest and derive its coverage.

    ``acceptance_artifact`` must be the complete frozen and self-hashed policy,
    not a freely supplied hidden-set fragment.  The returned mapping is
    immutable and contains only derived evidence.  No result scores or audio
    paths are read.
    """

    frozen = validate_separation_acceptance_thresholds(
        acceptance_artifact
    )
    expected = frozen["hidden_evaluation_set"]
    manifest, raw = _load_canonical_json(
        path,
        maximum_bytes=maximum_bytes,
        label="hidden evaluation manifest",
    )
    _exact_fields(manifest, _MANIFEST_FIELDS, "hidden manifest")
    _reject_invalid_tree(manifest, "hidden manifest")
    if manifest["schema"] != SEPARATION_HIDDEN_MANIFEST_SCHEMA:
        raise ValueError("unsupported hidden evaluation manifest schema")
    for field_name in (
        "manifest_id",
        "split_id",
        "dataset_id",
        "development_split_id",
    ):
        _safe_id(manifest[field_name], f"hidden manifest.{field_name}")
    _sha256(
        manifest["development_split_sha256"],
        "hidden manifest.development_split_sha256",
    )
    _license_expression(
        manifest["dataset_license_expression"],
        "hidden manifest.dataset_license_expression",
    )
    _sha256(
        manifest["dataset_terms_sha256"],
        "hidden manifest.dataset_terms_sha256",
    )
    if raw != canonical_json_bytes(manifest):
        raise ValueError("hidden evaluation manifest is not canonical JSON")

    development_identities = _sequence(
        manifest["development_song_identity_sha256s"],
        "hidden manifest.development_song_identity_sha256s",
    )
    if (
        not development_identities
        or len(development_identities) > MAX_HIDDEN_SONGS
    ):
        raise ValueError(
            "development song identity commitment must be bounded and non-empty"
        )
    checked_development_identities = [
        _sha256(
            item,
            (
                "hidden manifest.development_song_identity_sha256s"
                f"[{index}]"
            ),
        )
        for index, item in enumerate(development_identities)
    ]
    if checked_development_identities != sorted(
        set(checked_development_identities)
    ):
        raise ValueError(
            "development song identities must be sorted and unique"
        )
    development_sources = _sequence(
        manifest["development_source_sha256s"],
        "hidden manifest.development_source_sha256s",
    )
    if (
        not development_sources
        or len(development_sources) > MAX_HIDDEN_SONGS
        or len(development_sources) != len(checked_development_identities)
    ):
        raise ValueError(
            "development source commitment must be bounded, non-empty and "
            "match the song-identity count"
        )
    checked_development_sources = [
        _sha256(
            item,
            f"hidden manifest.development_source_sha256s[{index}]",
        )
        for index, item in enumerate(development_sources)
    ]
    if checked_development_sources != sorted(
        set(checked_development_sources)
    ):
        raise ValueError(
            "development source hashes must be sorted and unique"
        )
    development_split_hash = hashlib.sha256(
        canonical_json_bytes(
            {
                "split_id": manifest["development_split_id"],
                "song_identity_sha256s": checked_development_identities,
                "source_sha256s": checked_development_sources,
            }
        )
    ).hexdigest()
    if development_split_hash != manifest["development_split_sha256"]:
        raise ValueError(
            "development split hash does not match its song identities"
        )
    if (
        manifest["development_split_id"]
        != expected["excluded_development_split_id"]
        or manifest["development_split_sha256"]
        != expected["excluded_development_split_sha256"]
    ):
        raise ValueError(
            "hidden manifest development exclusion does not match frozen policy"
        )

    songs = _sequence(manifest["songs"], "hidden manifest.songs")
    if len(songs) < 12 or len(songs) > MAX_HIDDEN_SONGS:
        raise ValueError("hidden manifest must contain 12..10000 songs")
    song_ids: list[str] = []
    seen_song_ids: set[str] = set()
    group_counts = {group: 0 for group in _GROUPS}
    role_counts: dict[str, int] = {}
    ground_truth_hashes_by_role: dict[str, set[str]] = {}
    canonical_songs: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    hidden_song_identities: set[str] = set()
    hidden_sources: set[str] = set()
    development_identity_set = set(checked_development_identities)
    development_source_set = set(checked_development_sources)
    for index, raw_song in enumerate(songs):
        song = _mapping(raw_song, f"hidden manifest.songs[{index}]")
        _exact_fields(
            song,
            _MANIFEST_SONG_FIELDS,
            f"hidden manifest.songs[{index}]",
        )
        song_id = _safe_id(
            song["song_id"],
            f"hidden manifest.songs[{index}].song_id",
        )
        if song_id in seen_song_ids:
            raise ValueError("hidden manifest song_id values must be unique")
        song_ids.append(song_id)
        seen_song_ids.add(song_id)
        song_identity = _sha256(
            song["song_identity_sha256"],
            f"hidden manifest.songs[{index}].song_identity_sha256",
        )
        if song_identity in hidden_song_identities:
            raise ValueError(
                "hidden manifest song identities must be unique"
            )
        if song_identity in development_identity_set:
            raise ValueError(
                "development and hidden song identities must not overlap"
            )
        hidden_song_identities.add(song_identity)
        group = str(song["group"])
        if group not in _GROUPS:
            raise ValueError("hidden manifest song group is invalid")
        group_counts[group] += 1
        source_hash = _sha256(
            song["source_sha256"],
            f"hidden manifest.songs[{index}].source_sha256",
        )
        if source_hash in hidden_sources:
            raise ValueError(
                "hidden manifest source hashes must be unique"
            )
        if source_hash in development_source_set:
            raise ValueError(
                "development and hidden source audio must not overlap"
            )
        hidden_sources.add(source_hash)
        rights_profile_id = _safe_id(
            song["rights_profile_id"],
            f"hidden manifest.songs[{index}].rights_profile_id",
        )
        rights_evidence_hash = _sha256(
            song["rights_evidence_sha256"],
            f"hidden manifest.songs[{index}].rights_evidence_sha256",
        )
        _require_exact_bool(
            song,
            "authorised_for_evaluation",
            True,
            f"hidden manifest.songs[{index}]",
        )
        role_values = _sequence(
            song["roles"],
            f"hidden manifest.songs[{index}].roles",
        )
        if (
            not role_values
            or len(role_values) > MAX_GROUND_TRUTH_ROLES_PER_SONG
        ):
            raise ValueError(
                "hidden manifest song roles must be a bounded non-empty list"
            )
        role_ids: list[str] = []
        canonical_roles: list[dict[str, Any]] = []
        for role_index, raw_role in enumerate(role_values):
            role = _mapping(
                raw_role,
                f"hidden manifest.songs[{index}].roles[{role_index}]",
            )
            _exact_fields(
                role,
                _MANIFEST_ROLE_FIELDS,
                f"hidden manifest.songs[{index}].roles[{role_index}]",
            )
            role_id = _role_prepared_id(
                role["role_prepared_id"],
                (
                    f"hidden manifest.songs[{index}]."
                    f"roles[{role_index}].role_prepared_id"
                ),
            )
            if role_id in role_ids:
                raise ValueError(
                    "hidden manifest song roles must be unique"
                )
            pair = (song_id, role_id)
            if pair in seen_pairs:
                raise ValueError(
                    "hidden manifest song-role pairs must be unique"
                )
            seen_pairs.add(pair)
            role_ids.append(role_id)
            role_counts[role_id] = role_counts.get(role_id, 0) + 1
            ground_truth_hash = _sha256(
                role["ground_truth_sha256"],
                (
                    f"hidden manifest.songs[{index}]."
                    f"roles[{role_index}].ground_truth_sha256"
                ),
            )
            seen_ground_truth = ground_truth_hashes_by_role.setdefault(
                role_id, set()
            )
            if ground_truth_hash in seen_ground_truth:
                raise ValueError(
                    f"hidden manifest ground truth for {role_id} must "
                    "use independent hashes"
                )
            seen_ground_truth.add(ground_truth_hash)
            canonical_roles.append(_plain(role))
        if role_ids != sorted(role_ids):
            raise ValueError(
                "hidden manifest song roles must be sorted by role_prepared_id"
            )
        canonical_songs.append(
            {
                "song_id": song_id,
                "song_identity_sha256": song_identity,
                "group": group,
                "source_sha256": source_hash,
                "rights_profile_id": rights_profile_id,
                "rights_evidence_sha256": rights_evidence_hash,
                "authorised_for_evaluation": True,
                "roles": canonical_roles,
            }
        )
    if song_ids != sorted(song_ids):
        raise ValueError("hidden manifest songs must be sorted by song_id")
    if any(group_counts[group] < 4 for group in _GROUPS):
        raise ValueError(
            "hidden manifest groups need at least four songs each"
        )

    manifest_hash = hashlib.sha256(raw).hexdigest()
    split_hash = hashlib.sha256(
        canonical_json_bytes(
            {
                "split_id": manifest["split_id"],
                "songs": canonical_songs,
            }
        )
    ).hexdigest()
    comparisons = {
        "manifest_id": manifest["manifest_id"],
        "manifest_sha256": manifest_hash,
        "split_id": manifest["split_id"],
        "split_sha256": split_hash,
        "total_songs": len(canonical_songs),
        "groups": group_counts,
        "ground_truth_pairs_by_role": dict(sorted(role_counts.items())),
        "dataset_id": manifest["dataset_id"],
        "dataset_license_expression": manifest[
            "dataset_license_expression"
        ],
        "dataset_terms_sha256": manifest["dataset_terms_sha256"],
    }
    for field_name in (
        "manifest_id",
        "manifest_sha256",
        "split_id",
        "split_sha256",
        "total_songs",
        "groups",
        "ground_truth_pairs_by_role",
        "dataset_id",
        "dataset_license_expression",
        "dataset_terms_sha256",
    ):
        if comparisons[field_name] != expected[field_name]:
            raise ValueError(
                f"hidden manifest derived {field_name} does not match "
                "the frozen acceptance artifact"
            )
    for role_id, count in role_counts.items():
        if role_id in expected["ground_truth_pairs_by_role"] and count < 8:
            raise ValueError(
                f"hidden manifest has fewer than eight pairs for {role_id}"
            )
    return _freeze(comparisons)


def _validate_registration(value: Any) -> Mapping[str, Any]:
    registration = _mapping(value, "registration")
    _exact_fields(registration, _REGISTRATION_FIELDS, "registration")
    if registration["protocol"] != (
        "pre-registered-before-hidden-evaluation-v1"
    ):
        raise ValueError("registration protocol is invalid")
    timestamp = _text(registration["frozen_at_utc"], "frozen_at_utc")
    if not _UTC_RE.fullmatch(timestamp):
        raise ValueError("frozen_at_utc must be a whole-second UTC timestamp")
    try:
        datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError(
            "frozen_at_utc must be a real whole-second UTC timestamp"
        ) from exc
    _require_exact_bool(
        registration,
        "hidden_results_seen",
        False,
        "registration",
    )
    _require_exact_bool(
        registration,
        "changes_after_freeze_allowed",
        False,
        "registration",
    )
    _require_exact_bool(
        registration,
        "development_data_only_for_calibration",
        True,
        "registration",
    )
    _safe_id(
        registration["development_split_id"],
        "registration.development_split_id",
    )
    _sha256(
        registration["development_split_sha256"],
        "registration.development_split_sha256",
    )
    return registration


def _validate_deployment_profile(value: Any) -> Mapping[str, Any]:
    profile = _mapping(value, "deployment_profile")
    _exact_fields(profile, _DEPLOYMENT_FIELDS, "deployment_profile")
    _safe_id(profile["deployment_id"], "deployment_id")
    if profile["platform"] != "macos-local":
        raise ValueError("deployment platform must be macos-local")
    _require_exact_bool(
        profile, "local_processing", True, "deployment_profile"
    )
    for field_name in (
        "commercial_use_requested",
        "component_redistribution_requested",
        "derived_output_redistribution_requested",
    ):
        _boolean(profile[field_name], f"deployment_profile.{field_name}")
    _require_exact_bool(
        profile,
        "components_bundled_with_apache_package",
        False,
        "deployment_profile",
    )
    return profile


def _validate_identities(value: Any) -> Mapping[str, Any]:
    identities = _mapping(value, "identities")
    _exact_fields(identities, _IDENTITIES_FIELDS, "identities")
    candidate = _validate_identity(
        identities["candidate_separator"],
        "identities.candidate_separator",
    )
    baseline = _validate_identity(
        identities["baseline_separator"],
        "identities.baseline_separator",
    )
    if candidate["identity_id"] == baseline["identity_id"]:
        raise ValueError("candidate and baseline identities must differ")
    if _operational_identity_sha256(candidate) == (
        _operational_identity_sha256(baseline)
    ):
        raise ValueError(
            "candidate and baseline must be operationally distinct"
        )
    downstream = _mapping(
        identities["downstream_midi_by_role"],
        "identities.downstream_midi_by_role",
    )
    if not downstream:
        raise ValueError("downstream_midi_by_role must not be empty")
    downstream_checked: dict[str, Mapping[str, Any]] = {}
    for role_id in sorted(downstream):
        checked_role = _role_prepared_id(
            role_id, "downstream_midi_by_role key"
        )
        downstream_checked[checked_role] = _validate_identity(
            downstream[role_id],
            f"identities.downstream_midi_by_role.{role_id}",
        )
    evaluator = _validate_identity(
        identities["metric_evaluator"],
        "identities.metric_evaluator",
    )
    if evaluator["checkpoint"] != {
        "kind": "deterministic-no-checkpoint",
        "reason_code": "deterministic-no-checkpoint",
    }:
        raise ValueError(
            "metric_evaluator must be a deterministic no-checkpoint identity"
        )
    if evaluator["seed_policy"] != "deterministic-no-randomness-v1":
        raise ValueError(
            "metric_evaluator must use deterministic-no-randomness-v1"
        )

    by_id: dict[str, Mapping[str, Any]] = {}
    for identity in (
        candidate,
        baseline,
        *downstream_checked.values(),
        evaluator,
    ):
        identity_id = identity["identity_id"]
        previous = by_id.get(identity_id)
        if previous is not None and _plain(previous) != _plain(identity):
            raise ValueError("one identity_id describes different identities")
        by_id[identity_id] = identity
    return {
        "candidate_separator": candidate,
        "baseline_separator": baseline,
        "downstream_midi_by_role": downstream_checked,
        "metric_evaluator": evaluator,
    }


def _validate_identity(value: Any, label: str) -> Mapping[str, Any]:
    identity = _mapping(value, label)
    _exact_fields(identity, _IDENTITY_FIELDS, label)
    for field_name in ("identity_id", "backend_id", "package_name"):
        _safe_id(identity[field_name], f"{label}.{field_name}")
    _version(
        identity["package_version"], f"{label}.package_version"
    )
    commit = _text(
        identity["package_commit"], f"{label}.package_commit"
    )
    if not _COMMIT_RE.fullmatch(commit) or set(commit) == {"0"}:
        raise ValueError(
            f"{label}.package_commit must be a non-zero commit hash"
        )
    for field_name in ("package_source_sha256", "worker_sha256"):
        _sha256(identity[field_name], f"{label}.{field_name}")

    runtime = _mapping(identity["runtime"], f"{label}.runtime")
    _exact_fields(runtime, _RUNTIME_FIELDS, f"{label}.runtime")
    _safe_id(runtime["runtime_id"], f"{label}.runtime.runtime_id")
    _version(
        runtime["runtime_version"],
        f"{label}.runtime.runtime_version",
    )
    python_version = _text(
        runtime["python_version"], f"{label}.runtime.python_version"
    )
    if not _PYTHON_VERSION_RE.fullmatch(python_version):
        raise ValueError(
            f"{label}.runtime.python_version is outside the supported range"
        )
    _sha256(
        runtime["dependency_lock_sha256"],
        f"{label}.runtime.dependency_lock_sha256",
    )

    device = _mapping(identity["device"], f"{label}.device")
    _exact_fields(device, _DEVICE_FIELDS, f"{label}.device")
    if device["platform"] != "macos":
        raise ValueError(f"{label}.device.platform must be macos")
    if device["machine"] not in {"arm64", "x86_64"}:
        raise ValueError(f"{label}.device.machine is invalid")
    if device["accelerator"] not in {"cpu", "mps"}:
        raise ValueError(f"{label}.device.accelerator is invalid")

    checkpoint = _mapping(identity["checkpoint"], f"{label}.checkpoint")
    kind = checkpoint.get("kind")
    if kind == "checkpoint":
        _exact_fields(checkpoint, _CHECKPOINT_FIELDS, f"{label}.checkpoint")
        _safe_id(
            checkpoint["checkpoint_id"],
            f"{label}.checkpoint.checkpoint_id",
        )
        if checkpoint["format"] not in {
            "safetensors",
            "torch-state-dict",
            "onnx",
            "coreml",
        }:
            raise ValueError(f"{label}.checkpoint.format is invalid")
        _sha256(checkpoint["sha256"], f"{label}.checkpoint.sha256")
        _positive_integer(
            checkpoint["bytes"], f"{label}.checkpoint.bytes"
        )
        _license_expression(
            checkpoint["weights_license_expression"],
            f"{label}.checkpoint.weights_license_expression",
        )
        _sha256(
            checkpoint["weights_terms_sha256"],
            f"{label}.checkpoint.weights_terms_sha256",
        )
    elif kind == "deterministic-no-checkpoint":
        _exact_fields(
            checkpoint,
            _NO_CHECKPOINT_FIELDS,
            f"{label}.checkpoint",
        )
        if checkpoint["reason_code"] != "deterministic-no-checkpoint":
            raise ValueError(
                f"{label}.checkpoint reason_code must identify the "
                "deterministic no-checkpoint control"
            )
    else:
        raise ValueError(f"{label}.checkpoint kind is invalid")

    settings = _mapping(identity["settings"], f"{label}.settings")
    if not settings:
        raise ValueError(f"{label}.settings must not be empty")
    _validate_settings_tree(settings, f"{label}.settings")
    settings_hash = _sha256(
        identity["settings_sha256"], f"{label}.settings_sha256"
    )
    if settings_hash != hashlib.sha256(
        canonical_json_bytes(settings)
    ).hexdigest():
        raise ValueError(f"{label}.settings_sha256 does not match settings")
    if identity["seed_policy"] not in {
        "fixed-seed-per-song-role-v1",
        "deterministic-no-randomness-v1",
    }:
        raise ValueError(f"{label}.seed_policy is invalid")
    _license_expression(
        identity["code_license_expression"],
        f"{label}.code_license_expression",
    )
    _sha256(
        identity["code_terms_sha256"],
        f"{label}.code_terms_sha256",
    )
    _license_expression(
        identity["training_data_license_expression"],
        f"{label}.training_data_license_expression",
    )
    _sha256(
        identity["training_data_terms_sha256"],
        f"{label}.training_data_terms_sha256",
    )
    return identity


def _operational_identity_sha256(identity: Mapping[str, Any]) -> str:
    """Hash only fields that can change one evaluated program's behaviour."""

    payload = {
        "package_source_sha256": identity["package_source_sha256"],
        "worker_sha256": identity["worker_sha256"],
        "runtime": identity["runtime"],
        "device": identity["device"],
        "checkpoint": identity["checkpoint"],
        "settings": identity["settings"],
        "settings_sha256": identity["settings_sha256"],
        "seed_policy": identity["seed_policy"],
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _validate_hidden_evaluation_set(value: Any) -> Mapping[str, Any]:
    hidden = _mapping(value, "hidden_evaluation_set")
    _exact_fields(hidden, _HIDDEN_FIELDS, "hidden_evaluation_set")
    _require_exact_bool(
        hidden, "hidden", True, "hidden_evaluation_set"
    )
    for field_name in (
        "manifest_id",
        "split_id",
        "dataset_id",
        "excluded_development_split_id",
    ):
        _safe_id(hidden[field_name], f"hidden_evaluation_set.{field_name}")
    for field_name in (
        "manifest_sha256",
        "split_sha256",
        "dataset_terms_sha256",
        "excluded_development_split_sha256",
    ):
        _sha256(hidden[field_name], f"hidden_evaluation_set.{field_name}")
    total_songs = _integer(
        hidden["total_songs"], "hidden_evaluation_set.total_songs"
    )
    if total_songs < 12 or total_songs > MAX_HIDDEN_SONGS:
        raise ValueError("hidden evaluation requires 12..10000 songs")
    groups = _mapping(hidden["groups"], "hidden_evaluation_set.groups")
    _exact_fields(groups, frozenset(_GROUPS), "hidden_evaluation_set.groups")
    group_total = 0
    for group in _GROUPS:
        count = _integer(
            groups[group], f"hidden_evaluation_set.groups.{group}"
        )
        if count < 4:
            raise ValueError("every hidden group needs at least four songs")
        group_total += count
    if group_total != total_songs:
        raise ValueError("hidden group counts must sum to total_songs")
    if hidden["unit"] != "unique-song-role-pair":
        raise ValueError(
            "hidden evaluation unit must be unique-song-role-pair"
        )
    counts = _mapping(
        hidden["ground_truth_pairs_by_role"],
        "hidden_evaluation_set.ground_truth_pairs_by_role",
    )
    if not counts:
        raise ValueError("hidden ground-truth role counts must not be empty")
    for role_id, raw_count in counts.items():
        _role_prepared_id(
            role_id,
            "hidden_evaluation_set.ground_truth_pairs_by_role key",
        )
        count = _integer(
            raw_count,
            (
                "hidden_evaluation_set.ground_truth_pairs_by_role."
                f"{role_id}"
            ),
        )
        if count < 8 or count > total_songs:
            raise ValueError(
                "every hidden promoted role needs 8..total_songs pairs"
            )
    _license_expression(
        hidden["dataset_license_expression"],
        "hidden_evaluation_set.dataset_license_expression",
    )
    _require_exact_bool(
        hidden,
        "authorised_for_evaluation",
        True,
        "hidden_evaluation_set",
    )
    return hidden


def _validate_role_promotion(value: Any) -> Mapping[str, Any]:
    roles = _mapping(value, "role_promotion")
    if not roles:
        raise ValueError("role_promotion must not be empty")
    checked: dict[str, Mapping[str, Any]] = {}
    for role_key in sorted(roles):
        role_id = _role_prepared_id(role_key, "role_promotion key")
        role = _mapping(roles[role_key], f"role_promotion.{role_key}")
        _exact_fields(
            role, _ROLE_PROMOTION_FIELDS, f"role_promotion.{role_key}"
        )
        if role["role_prepared_id"] != role_id:
            raise ValueError(
                "role promotion key and role_prepared_id must match"
            )
        short_role = role_id.split(":", 1)[1]
        expected_kind = (
            "percussion"
            if short_role in _PERCUSSION_ROLES
            else "pitched"
        )
        if role["kind"] != expected_kind:
            raise ValueError(
                f"{role_id} must use kind={expected_kind}"
            )
        minimum = _integer(
            role["minimum_ground_truth_pairs"],
            f"role_promotion.{role_id}.minimum_ground_truth_pairs",
        )
        if minimum < 8:
            raise ValueError(
                "role promotion minimum ground truth pairs must be >= 8"
            )
        catastrophic_failures = _integer(
            role["catastrophic_failures_allowed"],
            f"role_promotion.{role_id}.catastrophic_failures_allowed",
        )
        if catastrophic_failures != 0:
            raise ValueError(
                "catastrophic_failures_allowed must be exactly zero"
            )
        if role["missing_or_nonfinite"] != "fail":
            raise ValueError("missing or non-finite metrics must fail")
        if role["paired_policy"] != SEPARATION_ACCEPTANCE_PAIRED_POLICY:
            raise ValueError("role promotion paired policy is invalid")
        if (
            role["aggregate_policy"]
            != SEPARATION_ACCEPTANCE_AGGREGATE_POLICY
        ):
            raise ValueError("role promotion aggregate policy is invalid")
        _validate_role_metrics(
            role["metrics"],
            kind=expected_kind,
            label=f"role_promotion.{role_id}.metrics",
        )
        checked[role_id] = role
    return checked


def _validate_role_metrics(
    value: Any,
    *,
    kind: str,
    label: str,
) -> None:
    metrics = _mapping(value, label)
    required = (
        _PERCUSSION_METRICS if kind == "percussion" else _PITCHED_METRICS
    )
    _exact_fields(metrics, required, label)
    _validate_higher_metric(metrics["onset_f1"], f"{label}.onset_f1")
    _validate_timing_metric(
        metrics["onset_error_median_ms"],
        f"{label}.onset_error_median_ms",
    )
    _validate_timing_metric(
        metrics["onset_error_p95_ms"],
        f"{label}.onset_error_p95_ms",
    )
    median = metrics["onset_error_median_ms"]
    p95 = metrics["onset_error_p95_ms"]
    for field_name in (
        "aggregate_maximum_candidate",
        "aggregate_maximum_candidate_minus_baseline",
        "per_song_maximum_candidate",
        "per_song_maximum_candidate_minus_baseline",
        "catastrophic_regression_limit",
    ):
        if p95[field_name] < median[field_name]:
            raise ValueError(
                "p95 timing thresholds must not be smaller than median "
                "timing thresholds"
            )
    if kind == "pitched":
        _validate_higher_metric(
            metrics["exact_pitch_accuracy"],
            f"{label}.exact_pitch_accuracy",
        )
        _validate_higher_metric(
            metrics["octave_accuracy"],
            f"{label}.octave_accuracy",
        )
    else:
        for metric_name in ("exact_pitch_accuracy", "octave_accuracy"):
            metric = _mapping(
                metrics[metric_name], f"{label}.{metric_name}"
            )
            if set(metric) != set(_NOT_APPLICABLE_FIELDS):
                raise ValueError(
                    "percussion pitch and octave metrics must be explicitly "
                    "not_applicable"
                )
            _exact_fields(
                metric,
                _NOT_APPLICABLE_FIELDS,
                f"{label}.{metric_name}",
            )
            if metric != {
                "status": "not_applicable",
                "reason": "percussion-role",
            }:
                raise ValueError(
                    "percussion pitch and octave metrics must be explicitly "
                    "not_applicable"
                )
        _validate_higher_metric(
            metrics["drum_family_onset_f1"],
            f"{label}.drum_family_onset_f1",
        )


def _validate_higher_metric(value: Any, label: str) -> None:
    metric = _mapping(value, label)
    _exact_fields(metric, _HIGHER_FIELDS, label)
    if metric["direction"] != "higher_is_better":
        raise ValueError(f"{label} direction must be higher_is_better")
    for field_name in (
        "aggregate_minimum_candidate",
        "per_song_minimum_candidate",
        "catastrophic_regression_limit",
    ):
        number = _finite_number(metric[field_name], f"{label}.{field_name}")
        if number < 0.0 or number > 1.0:
            raise ValueError(f"{label}.{field_name} must be within 0..1")
    for field_name in (
        "aggregate_minimum_candidate_minus_baseline",
        "per_song_minimum_candidate_minus_baseline",
    ):
        number = _finite_number(metric[field_name], f"{label}.{field_name}")
        if number < -1.0 or number > 1.0:
            raise ValueError(f"{label}.{field_name} must be within -1..1")
    if (
        metric["per_song_minimum_candidate"]
        > metric["aggregate_minimum_candidate"]
    ):
        raise ValueError(
            f"{label} per-song candidate minimum cannot exceed aggregate "
            "candidate minimum"
        )
    if (
        metric["per_song_minimum_candidate_minus_baseline"]
        > metric["aggregate_minimum_candidate_minus_baseline"]
    ):
        raise ValueError(
            f"{label} per-song delta minimum cannot exceed aggregate delta "
            "minimum"
        )


def _validate_timing_metric(value: Any, label: str) -> None:
    metric = _mapping(value, label)
    _exact_fields(metric, _TIMING_FIELDS, label)
    if metric["direction"] != "lower_is_better":
        raise ValueError(f"{label} direction must be lower_is_better")
    aggregate_maximum = _finite_number(
        metric["aggregate_maximum_candidate"],
        f"{label}.aggregate_maximum_candidate",
    )
    per_song_maximum = _finite_number(
        metric["per_song_maximum_candidate"],
        f"{label}.per_song_maximum_candidate",
    )
    catastrophic = _finite_number(
        metric["catastrophic_regression_limit"],
        f"{label}.catastrophic_regression_limit",
    )
    aggregate_delta = _finite_number(
        metric["aggregate_maximum_candidate_minus_baseline"],
        f"{label}.aggregate_maximum_candidate_minus_baseline",
    )
    per_song_delta = _finite_number(
        metric["per_song_maximum_candidate_minus_baseline"],
        f"{label}.per_song_maximum_candidate_minus_baseline",
    )
    if aggregate_maximum <= 0.0 or aggregate_maximum > 1000.0:
        raise ValueError(
            f"{label}.aggregate_maximum_candidate is unreasonable"
        )
    if (
        per_song_maximum < aggregate_maximum
        or per_song_maximum > 1000.0
    ):
        raise ValueError(
            f"{label}.per_song_maximum_candidate is unreasonable"
        )
    if not -1000.0 <= aggregate_delta <= 1000.0:
        raise ValueError(
            f"{label}.aggregate candidate-minus-baseline is unreasonable"
        )
    if (
        per_song_delta < aggregate_delta
        or per_song_delta > 1000.0
    ):
        raise ValueError(
            f"{label}.per-song candidate-minus-baseline is unreasonable"
        )
    if catastrophic < max(0.0, per_song_delta) or catastrophic > 1000.0:
        raise ValueError(
            f"{label}.catastrophic_regression_limit is unreasonable"
        )


def _validate_resource_gates(
    value: Any,
    *,
    candidate_identity: Mapping[str, Any],
) -> Sequence[Mapping[str, Any]]:
    gates = _mapping(value, "resource_gates")
    _exact_fields(gates, _RESOURCE_FIELDS, "resource_gates")
    if gates["protocol"] != "fresh-process-resource-measurement-v1":
        raise ValueError("resource gate protocol is invalid")
    repetitions = _integer(gates["repetitions"], "resource_gates.repetitions")
    if repetitions < 3 or repetitions > 100:
        raise ValueError("resource gate repetitions must be 3..100")
    classes = _sequence(gates["mac_classes"], "resource_gates.mac_classes")
    if not classes or len(classes) > 32:
        raise ValueError("resource gates require 1..32 Mac classes")
    class_ids: list[str] = []
    has_16_gib_arm = False
    checked: list[Mapping[str, Any]] = []
    candidate_runtime = candidate_identity["runtime"]
    required_runtime = (
        f"{candidate_runtime['runtime_id']}-"
        f"{candidate_runtime['runtime_version']}"
    )
    candidate_device = candidate_identity["device"]
    for index, raw_class in enumerate(classes):
        label = f"resource_gates.mac_classes[{index}]"
        mac = _mapping(raw_class, label)
        _exact_fields(mac, _MAC_CLASS_FIELDS, label)
        class_id = _safe_id(mac["class_id"], f"{label}.class_id")
        if class_id in class_ids:
            raise ValueError("resource class_id values must be unique")
        class_ids.append(class_id)
        if mac["os_name"] != "macOS":
            raise ValueError(f"{label}.os_name must be macOS")
        _version(mac["os_version"], f"{label}.os_version")
        os_build = _text(mac["os_build"], f"{label}.os_build")
        if not _OS_BUILD_RE.fullmatch(os_build):
            raise ValueError(f"{label}.os_build is invalid")
        runtime = _safe_id(mac["runtime"], f"{label}.runtime")
        if runtime != required_runtime:
            raise ValueError(
                f"{label}.runtime does not match candidate separator"
            )
        if mac["device"] != candidate_device["accelerator"]:
            raise ValueError(
                f"{label}.device does not match candidate separator"
            )
        if mac["architecture"] != candidate_device["machine"]:
            raise ValueError(
                f"{label}.architecture does not match candidate separator"
            )
        if mac["architecture"] != "arm64":
            raise ValueError(f"{label}.architecture must be arm64")
        if mac["hardware_family"] != "Apple silicon":
            raise ValueError(
                f"{label}.hardware_family must be Apple silicon"
            )
        memory = _integer(
            mac["unified_memory_gib"], f"{label}.unified_memory_gib"
        )
        if memory < 8 or memory > 512:
            raise ValueError(f"{label}.unified_memory_gib is unreasonable")
        wall_per_minute = _finite_number(
            mac["wall_time_seconds_per_audio_minute_max"],
            f"{label}.wall_time_seconds_per_audio_minute_max",
        )
        wall_single = _finite_number(
            mac["single_song_wall_time_seconds_max"],
            f"{label}.single_song_wall_time_seconds_max",
        )
        peak = _finite_number(
            mac["peak_unified_memory_gib_max"],
            f"{label}.peak_unified_memory_gib_max",
        )
        if wall_per_minute <= 0.0 or wall_per_minute > 7200.0:
            raise ValueError(f"{label} per-minute wall ceiling is invalid")
        if wall_single <= 0.0 or wall_single > 86_400.0:
            raise ValueError(f"{label} single-song wall ceiling is invalid")
        if peak <= 0.0 or peak > float(memory):
            raise ValueError(f"{label} peak memory ceiling is invalid")
        _require_exact_bool(mac, "timeout_is_failure", True, label)
        _require_exact_bool(mac, "oom_is_failure", True, label)
        if memory == 16:
            has_16_gib_arm = True
        checked.append(mac)
    if class_ids != sorted(class_ids):
        raise ValueError("resource Mac classes must be sorted by class_id")
    if not has_16_gib_arm:
        raise ValueError(
            "resource gates must include an arm64 16 GiB Apple-silicon Mac"
        )
    return checked


def _validate_offline_gate(value: Any) -> Mapping[str, Any]:
    gate = _mapping(value, "offline_gate")
    _exact_fields(gate, _OFFLINE_FIELDS, "offline_gate")
    if gate["policy"] != SEPARATION_ACCEPTANCE_OFFLINE_POLICY:
        raise ValueError("offline gate policy is invalid")
    _require_exact_bool(
        gate, "explicit_install_completed", True, "offline_gate"
    )
    _require_exact_bool(
        gate, "implicit_downloads_allowed", False, "offline_gate"
    )
    _require_exact_bool(
        gate, "os_network_denial_enforced", True, "offline_gate"
    )
    _require_exact_bool(
        gate,
        "outbound_attempt_observation_enabled",
        True,
        "offline_gate",
    )
    attempts = _integer(gate["attempts"], "offline_gate.attempts")
    if attempts < 2 or attempts > 100:
        raise ValueError("offline gate attempts must be 2..100")
    for field_name in (
        "maximum_attempted_outbound_connections",
        "maximum_successful_outbound_connections",
    ):
        maximum_connections = _integer(
            gate[field_name], f"offline_gate.{field_name}"
        )
        if maximum_connections != 0:
            raise ValueError(f"offline_gate.{field_name} must be zero")
    _require_exact_bool(
        gate, "any_failure_fails_gate", True, "offline_gate"
    )
    return gate


def _validate_human_listening(value: Any) -> Mapping[str, Any]:
    human = _mapping(value, "human_listening")
    _exact_fields(human, _HUMAN_FIELDS, "human_listening")
    _require_exact_bool(human, "blind", True, "human_listening")
    _require_exact_bool(
        human, "level_matched", True, "human_listening"
    )
    renderer = _mapping(
        human["renderer"], "human_listening.renderer"
    )
    _exact_fields(
        renderer, _RENDERER_FIELDS, "human_listening.renderer"
    )
    _safe_id(renderer["renderer_id"], "renderer.renderer_id")
    _version(renderer["version"], "renderer.version")
    _sha256(renderer["source_sha256"], "renderer.source_sha256")
    _license_expression(
        renderer["license_expression"], "renderer.license_expression"
    )
    _sha256(renderer["terms_sha256"], "renderer.terms_sha256")
    soundfont = _mapping(
        human["soundfont"], "human_listening.soundfont"
    )
    _exact_fields(
        soundfont, _SOUNDFONT_FIELDS, "human_listening.soundfont"
    )
    _safe_id(soundfont["soundfont_id"], "soundfont.soundfont_id")
    _sha256(soundfont["sha256"], "soundfont.sha256")
    _license_expression(
        soundfont["license_expression"],
        "soundfont.license_expression",
    )
    _sha256(soundfont["terms_sha256"], "soundfont.terms_sha256")
    level_matcher = _mapping(
        human["level_matcher"], "human_listening.level_matcher"
    )
    _exact_fields(
        level_matcher,
        _LEVEL_MATCHER_FIELDS,
        "human_listening.level_matcher",
    )
    _safe_id(
        level_matcher["level_matcher_id"],
        "level_matcher.level_matcher_id",
    )
    _version(level_matcher["version"], "level_matcher.version")
    _sha256(
        level_matcher["source_sha256"], "level_matcher.source_sha256"
    )
    _license_expression(
        level_matcher["license_expression"],
        "level_matcher.license_expression",
    )
    _sha256(
        level_matcher["terms_sha256"], "level_matcher.terms_sha256"
    )
    if human["assignment_policy"] != (
        "blind-randomised-withheld-key-v1"
    ):
        raise ValueError("human assignment policy is invalid")
    if human["level_policy"] != (
        "integrated-lufs-and-rms-matched-v1"
    ):
        raise ValueError("human level policy is invalid")
    if human["audition_window_policy"] != (
        "fixed-pre-registered-song-role-windows-v1"
    ):
        raise ValueError("human audition-window policy is invalid")
    _safe_id(
        human["audition_manifest_id"],
        "human_listening.audition_manifest_id",
    )
    commitment_fields = (
        "audition_manifest_sha256",
        "assignment_seed_commitment_sha256",
        "answer_key_commitment_sha256",
    )
    commitment_hashes = [
        _sha256(
            human[field_name], f"human_listening.{field_name}"
        )
        for field_name in commitment_fields
    ]
    if len(set(commitment_hashes)) != len(commitment_hashes):
        raise ValueError(
            "human listening commitments must use distinct hashes"
        )
    if human["loop_policy"] != (
        "same-window-one-loop-before-response-v1"
    ):
        raise ValueError("human loop policy is invalid")
    if human["label_policy"] != (
        "opaque-random-labels-withheld-key-v1"
    ):
        raise ValueError("human label policy is invalid")
    _require_exact_bool(
        human, "answer_key_separate", True, "human_listening"
    )
    if human["response_policy"] != (
        "candidate-baseline-cannot-tell-v1"
    ):
        raise ValueError("human response policy is invalid")
    statistical = _mapping(
        human["statistical_policy"],
        "human_listening.statistical_policy",
    )
    _exact_fields(
        statistical,
        _STATISTICAL_POLICY_FIELDS,
        "human_listening.statistical_policy",
    )
    expected_statistical = {
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
    }
    if statistical != expected_statistical:
        raise ValueError("human statistical policy is invalid")
    rms = _finite_number(
        human["maximum_rms_mismatch_db"],
        "human_listening.maximum_rms_mismatch_db",
    )
    lufs = _finite_number(
        human["maximum_lufs_mismatch_lu"],
        "human_listening.maximum_lufs_mismatch_lu",
    )
    if rms < 0.0 or rms > 1.0 or lufs < 0.0 or lufs > 1.0:
        raise ValueError("human level mismatch limits must be within 0..1")
    minimum_songs = _integer(
        human["minimum_songs"], "human_listening.minimum_songs"
    )
    minimum_roles = _integer(
        human["minimum_roles"], "human_listening.minimum_roles"
    )
    minimum_reviewers = _integer(
        human["minimum_reviewers"],
        "human_listening.minimum_reviewers",
    )
    minimum_units = _integer(
        human["minimum_valid_units"],
        "human_listening.minimum_valid_units",
    )
    if minimum_songs < 8:
        raise ValueError("human listening minimum_songs must be >= 8")
    if minimum_roles < 1:
        raise ValueError("human listening minimum_roles must be >= 1")
    if minimum_reviewers < 2:
        raise ValueError("human listening minimum_reviewers must be >= 2")
    if minimum_units < 16:
        raise ValueError("human listening minimum_valid_units must be >= 16")
    cannot_tell = _finite_number(
        human["cannot_tell_share_max"],
        "human_listening.cannot_tell_share_max",
    )
    if cannot_tell < 0.0 or cannot_tell > 0.5:
        raise ValueError("cannot-tell cap must be within 0..0.5")

    noninferiority = _mapping(
        human["noninferiority"], "human_listening.noninferiority"
    )
    _exact_fields(
        noninferiority,
        _NONINFERIORITY_FIELDS,
        "human_listening.noninferiority",
    )
    _require_exact_bool(
        noninferiority,
        "required",
        True,
        "human_listening.noninferiority",
    )
    equivalent = _finite_number(
        noninferiority["candidate_or_equivalent_share_min"],
        "noninferiority.candidate_or_equivalent_share_min",
    )
    baseline = _finite_number(
        noninferiority["baseline_preferred_share_max"],
        "noninferiority.baseline_preferred_share_max",
    )
    confidence = _finite_number(
        noninferiority["confidence_level"],
        "noninferiority.confidence_level",
    )
    alpha = _finite_number(
        noninferiority["alpha"], "noninferiority.alpha"
    )
    if equivalent < 0.5 or equivalent > 1.0:
        raise ValueError(
            "candidate-or-equivalent noninferiority minimum is invalid"
        )
    if baseline < 0.0 or baseline > 0.5:
        raise ValueError(
            "baseline-preferred noninferiority maximum is invalid"
        )
    if alpha <= 0.0 or alpha > 0.1:
        raise ValueError("noninferiority alpha must be within (0, 0.1]")
    if confidence < 0.9 or confidence >= 1.0:
        raise ValueError("noninferiority confidence level is invalid")
    if not math.isclose(confidence, 1.0 - alpha, abs_tol=1e-12):
        raise ValueError(
            "noninferiority confidence_level must equal 1 - alpha"
        )
    if baseline > 1.0 - equivalent:
        raise ValueError(
            "noninferiority shares describe an inconsistent acceptance band"
        )

    preference = _mapping(
        human["preference"], "human_listening.preference"
    )
    _exact_fields(
        preference, _PREFERENCE_FIELDS, "human_listening.preference"
    )
    if preference["claim_mode"] != "separate-preferred-claim-only":
        raise ValueError("preference must remain a separate claim")
    count = _integer(
        preference["candidate_preferred_count_min"],
        "preference.candidate_preferred_count_min",
    )
    share = _finite_number(
        preference["candidate_preferred_share_min"],
        "preference.candidate_preferred_share_min",
    )
    preference_alpha = _finite_number(
        preference["exact_binomial_alpha"],
        "preference.exact_binomial_alpha",
    )
    if count < 1 or count > minimum_units:
        raise ValueError("candidate preferred count threshold is invalid")
    if share <= 0.5 or share > 1.0:
        raise ValueError("candidate preferred share must be within (0.5, 1]")
    if preference_alpha <= 0.0 or preference_alpha > 0.05:
        raise ValueError(
            "preference exact-binomial alpha must be within (0, 0.05]"
        )
    return human


def _validate_licence_gate(
    value: Any,
    *,
    profile_id: str,
    deployment: Mapping[str, Any],
    identities: Mapping[str, Any],
    hidden: Mapping[str, Any],
    human: Mapping[str, Any],
) -> None:
    gate = _mapping(value, "licence_gate")
    _exact_fields(gate, _LICENCE_FIELDS, "licence_gate")
    if gate["deployment_profile_id"] != profile_id:
        raise ValueError(
            "licence gate deployment_profile_id does not match profile_id"
        )
    _require_exact_bool(
        gate, "all_components_covered", True, "licence_gate"
    )
    _require_exact_bool(
        gate, "any_failure_fails_gate", True, "licence_gate"
    )
    expected = _expected_licence_components(
        identities=identities,
        hidden=hidden,
        human=human,
    )
    entries = _sequence(gate["entries"], "licence_gate.entries")
    if not entries or len(entries) > 512:
        raise ValueError("licence gate entries must be a bounded list")
    subject_ids: list[str] = []
    actual: dict[str, Mapping[str, Any]] = {}
    for index, raw_entry in enumerate(entries):
        label = f"licence_gate.entries[{index}]"
        entry = _mapping(raw_entry, label)
        _exact_fields(entry, _LICENCE_ENTRY_FIELDS, label)
        subject_id = _safe_id(entry["subject_id"], f"{label}.subject_id")
        if subject_id in actual:
            raise ValueError("licence gate subject_id values must be unique")
        subject_ids.append(subject_id)
        if entry["component_kind"] not in {"code", "weights", "dataset"}:
            raise ValueError(f"{label}.component_kind is invalid")
        _license_expression(
            entry["license_expression"], f"{label}.license_expression"
        )
        _sha256(entry["terms_sha256"], f"{label}.terms_sha256")
        allowed = _mapping(entry["allowed_use"], f"{label}.allowed_use")
        _exact_fields(allowed, _ALLOWED_USE_FIELDS, f"{label}.allowed_use")
        redistribution = _mapping(
            entry["redistribution"], f"{label}.redistribution"
        )
        _exact_fields(
            redistribution,
            _REDISTRIBUTION_FIELDS,
            f"{label}.redistribution",
        )
        for field_name in _ALLOWED_USE_FIELDS:
            _boolean(
                allowed[field_name], f"{label}.allowed_use.{field_name}"
            )
        for field_name in _REDISTRIBUTION_FIELDS:
            _boolean(
                redistribution[field_name],
                f"{label}.redistribution.{field_name}",
            )
        if not allowed["local_evaluation"] or not allowed["local_inference"]:
            raise ValueError(
                f"{label} must permit local evaluation and inference"
            )
        if (
            deployment["commercial_use_requested"]
            and not allowed["commercial_use"]
        ):
            raise ValueError(f"{label} does not permit requested commercial use")
        if (
            deployment["component_redistribution_requested"]
            and not redistribution["component"]
        ):
            raise ValueError(
                f"{label} does not permit requested component redistribution"
            )
        if (
            deployment["derived_output_redistribution_requested"]
            and not redistribution["derived_outputs"]
        ):
            raise ValueError(
                f"{label} does not permit requested output redistribution"
            )
        actual[subject_id] = entry
    if subject_ids != sorted(subject_ids):
        raise ValueError("licence gate entries must be sorted by subject_id")
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise ValueError(
            "licence gate component coverage mismatch "
            f"(missing={missing}, extra={extra})"
        )
    for subject_id, evidence in expected.items():
        entry = actual[subject_id]
        for field_name in (
            "component_kind",
            "license_expression",
            "terms_sha256",
        ):
            if entry[field_name] != evidence[field_name]:
                raise ValueError(
                    f"licence gate identity drift for {subject_id}"
                )


def _expected_licence_components(
    *,
    identities: Mapping[str, Any],
    hidden: Mapping[str, Any],
    human: Mapping[str, Any],
) -> dict[str, dict[str, str]]:
    by_id: dict[str, Mapping[str, Any]] = {}
    identity_values = [
        identities["candidate_separator"],
        identities["baseline_separator"],
        *identities["downstream_midi_by_role"].values(),
        identities["metric_evaluator"],
    ]
    for identity in identity_values:
        by_id.setdefault(identity["identity_id"], identity)
    expected: dict[str, dict[str, str]] = {}
    for identity_id, identity in sorted(by_id.items()):
        expected[f"{identity_id}:code"] = {
            "component_kind": "code",
            "license_expression": identity["code_license_expression"],
            "terms_sha256": identity["code_terms_sha256"],
        }
        expected[f"{identity_id}:training-data"] = {
            "component_kind": "dataset",
            "license_expression": identity[
                "training_data_license_expression"
            ],
            "terms_sha256": identity["training_data_terms_sha256"],
        }
        checkpoint = identity["checkpoint"]
        if checkpoint["kind"] == "checkpoint":
            expected[f"{identity_id}:weights"] = {
                "component_kind": "weights",
                "license_expression": checkpoint[
                    "weights_license_expression"
                ],
                "terms_sha256": checkpoint["weights_terms_sha256"],
            }
    expected[f"dataset:{hidden['dataset_id']}"] = {
        "component_kind": "dataset",
        "license_expression": hidden["dataset_license_expression"],
        "terms_sha256": hidden["dataset_terms_sha256"],
    }
    renderer = human["renderer"]
    expected[f"renderer:{renderer['renderer_id']}:code"] = {
        "component_kind": "code",
        "license_expression": renderer["license_expression"],
        "terms_sha256": renderer["terms_sha256"],
    }
    soundfont = human["soundfont"]
    expected[f"soundfont:{soundfont['soundfont_id']}"] = {
        "component_kind": "dataset",
        "license_expression": soundfont["license_expression"],
        "terms_sha256": soundfont["terms_sha256"],
    }
    level_matcher = human["level_matcher"]
    expected[
        f"level-matcher:{level_matcher['level_matcher_id']}:code"
    ] = {
        "component_kind": "code",
        "license_expression": level_matcher["license_expression"],
        "terms_sha256": level_matcher["terms_sha256"],
    }
    return expected


def _validate_decision_rule(value: Any) -> Mapping[str, Any]:
    rule = _mapping(value, "decision_rule")
    _exact_fields(rule, _DECISION_FIELDS, "decision_rule")
    if rule["policy"] != SEPARATION_ACCEPTANCE_DECISION_POLICY:
        raise ValueError("decision rule policy is invalid")
    for field_name in (
        "technical_metrics_required",
        "resource_gates_required",
        "offline_gate_required",
        "human_noninferiority_required",
        "licence_gate_required",
        "preference_claim_separate",
    ):
        _require_exact_bool(rule, field_name, True, "decision_rule")
    for field_name in (
        "cross_role_averaging_allowed",
        "waivers_allowed",
    ):
        _require_exact_bool(rule, field_name, False, "decision_rule")
    if rule["promotion_scope"] != "role-specific":
        raise ValueError("decision promotion scope must be role-specific")
    if rule["missing_or_nonfinite"] != "fail":
        raise ValueError("decision missing/non-finite policy must be fail")
    return rule


def _load_canonical_json(
    path: str | Path,
    *,
    maximum_bytes: int,
    label: str,
) -> tuple[dict[str, Any], bytes]:
    if (
        isinstance(maximum_bytes, bool)
        or not isinstance(maximum_bytes, int)
        or maximum_bytes < 1
    ):
        raise ValueError("maximum_bytes must be a positive integer")
    file_path = Path(path)
    try:
        file_stat = file_path.lstat()
    except OSError as exc:
        raise ValueError(f"{label} is missing") from exc
    if stat.S_ISLNK(file_stat.st_mode) or not stat.S_ISREG(file_stat.st_mode):
        raise ValueError(f"{label} must be a regular non-symlink file")
    if file_stat.st_size < 2 or file_stat.st_size > maximum_bytes:
        raise ValueError(f"{label} exceeds its byte bound")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(file_path, flags)
    try:
        opened_stat = os.fstat(descriptor)
        if not stat.S_ISREG(opened_stat.st_mode):
            raise ValueError(f"{label} must remain a regular file")
        if (
            opened_stat.st_dev != file_stat.st_dev
            or opened_stat.st_ino != file_stat.st_ino
        ):
            raise ValueError(f"{label} changed while opening")
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > maximum_bytes:
            raise ValueError(f"{label} exceeds its byte bound")
        final_stat = os.fstat(descriptor)
        if (
            final_stat.st_size != len(raw)
            or final_stat.st_mtime_ns != opened_stat.st_mtime_ns
        ):
            raise ValueError(f"{label} changed while reading")
    finally:
        os.close(descriptor)
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain one JSON object")
    return value, raw


def _reject_duplicate_pairs(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _validate_settings_tree(value: Any, label: str) -> None:
    """Validate path-free, secret-free backend settings.

    Settings are part of the public acceptance identity.  They may contain
    structured model parameters, but never a machine path, URL, credential or
    free-form private note.
    """

    if isinstance(value, Mapping):
        if not value:
            raise ValueError(f"{label} must not contain empty objects")
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{label} object keys must be strings")
            _text(key, f"{label} key")
            if not _SETTING_TEXT_RE.fullmatch(key):
                raise ValueError(f"{label} contains an invalid setting key")
            normalized_key = re.sub(
                r"[^a-z0-9]+", "_", key.casefold()
            )
            if _PRIVATE_SETTING_KEY_RE.search(normalized_key):
                raise ValueError(
                    f"{label} contains a private path, URL or secret key"
                )
            _validate_settings_tree(item, f"{label}.{key}")
        return
    if isinstance(value, (list, tuple)):
        if not value:
            raise ValueError(f"{label} must not contain empty arrays")
        for index, item in enumerate(value):
            _validate_settings_tree(item, f"{label}[{index}]")
        return
    if isinstance(value, bool) or isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value) or (
            value == 0.0 and math.copysign(1.0, value) < 0.0
        ):
            raise ValueError(
                f"{label} must contain finite canonical numbers"
            )
        return
    if isinstance(value, str):
        text = _text(value, label)
        folded = text.casefold()
        if (
            text.startswith(("/", "~", "./", "../"))
            or _WINDOWS_ABSOLUTE_PATH_RE.match(text)
            or "://" in text
            or folded.startswith("file:")
            or "/users/" in folded
            or "\\users\\" in folded
        ):
            raise ValueError(
                f"{label} must not contain a private path or URL"
            )
        if not _SETTING_TEXT_RE.fullmatch(text):
            raise ValueError(f"{label} must be bounded setting text")
        return
    raise ValueError(f"{label} contains an unsupported setting value")


def _reject_invalid_tree(value: Any, label: str) -> None:
    if value is None:
        raise ValueError(f"{label} must not contain null")
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{label} must not contain non-finite numbers")
        return
    if isinstance(value, str):
        text = _text(value, label)
        folded = text.casefold()
        if (
            folded in _FORBIDDEN_TEXT
            or "placeholder" in folded
            or "${" in text
            or "<tbd" in folded
        ):
            raise ValueError(f"{label} contains placeholder text")
        return
    if isinstance(value, Mapping):
        if not value:
            raise ValueError(f"{label} must not contain empty objects")
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError(f"{label} object keys must be non-empty strings")
            if unicodedata.normalize("NFC", key) != key:
                raise ValueError(
                    f"{label} object keys must use NFC-normalized text"
                )
            _reject_invalid_tree(item, f"{label}.{key}")
        return
    if isinstance(value, (list, tuple)):
        if not value:
            raise ValueError(f"{label} must not contain empty arrays")
        for index, item in enumerate(value):
            _reject_invalid_tree(item, f"{label}[{index}]")
        return
    raise ValueError(f"{label} contains an unsupported value")


def _exact_fields(
    value: Mapping[str, Any],
    fields: frozenset[str],
    label: str,
) -> None:
    actual = set(value)
    if actual != set(fields):
        missing = sorted(set(fields) - actual)
        extra = sorted(actual - set(fields))
        raise ValueError(
            f"{label} fields are invalid (missing={missing}, extra={extra})"
        )


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, (list, tuple)) or isinstance(value, str):
        raise ValueError(f"{label} must be an array")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    if not value or value != value.strip() or len(value) > 512:
        raise ValueError(f"{label} must be bounded non-blank text")
    if any(ord(character) < 32 for character in value):
        raise ValueError(f"{label} must not contain control characters")
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError(f"{label} must use NFC-normalized text")
    _reject_private_path_or_url(value, label)
    return value


def _reject_private_path_or_url(value: str, label: str) -> None:
    folded = value.casefold()
    embedded_private_roots = (
        ":/applications/",
        ":/home/",
        ":/library/",
        ":/private/",
        ":/tmp/",
        ":/users/",
        ":/var/",
        ":/volumes/",
    )
    if (
        value.startswith(("/", "~", "./", "../"))
        or _WINDOWS_ABSOLUTE_PATH_RE.match(value)
        or "://" in value
        or folded.startswith("file:")
        or "/users/" in folded
        or "\\users\\" in folded
        or any(root in folded for root in embedded_private_roots)
    ):
        raise ValueError(f"{label} must not contain a private path or URL")


def _safe_id(value: Any, label: str) -> str:
    text = _text(value, label)
    if not _SAFE_ID_RE.fullmatch(text):
        raise ValueError(f"{label} must be a safe identifier")
    return text


def _version(value: Any, label: str) -> str:
    text = _text(value, label)
    if not _VERSION_RE.fullmatch(text):
        raise ValueError(f"{label} must be a version identifier")
    return text


def _profile_id(value: Any, label: str) -> str:
    text = _text(value, label)
    if not _PROFILE_ID_RE.fullmatch(text):
        raise ValueError(f"{label} must be a separation-profile hash identity")
    if text.endswith("0" * 64):
        raise ValueError(f"{label} must not contain a zero hash")
    return text


def _sha256(value: Any, label: str) -> str:
    text = _text(value, label)
    if not _SHA256_RE.fullmatch(text) or set(text) == {"0"}:
        raise ValueError(f"{label} must be a non-zero lowercase SHA-256")
    return text


def _role_prepared_id(value: Any, label: str) -> str:
    text = _text(value, label)
    match = _ROLE_PREPARED_RE.fullmatch(text)
    if match is None or match.group(1) not in prepared_source_role_ids():
        raise ValueError(f"{label} must be an exact role-prepared identifier")
    return text


def _license_expression(value: Any, label: str) -> str:
    text = _text(value, label)
    if len(text) > 256 or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9 .()+:/-]{0,255}", text
    ):
        raise ValueError(f"{label} must be a bounded licence expression")
    return text


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _positive_integer(value: Any, label: str) -> int:
    number = _integer(value, label)
    if number <= 0:
        raise ValueError(f"{label} must be positive")
    return number


def _finite_number(value: Any, label: str) -> float:
    if not isinstance(value, float):
        raise ValueError(f"{label} must be a JSON float")
    number = value
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    if number == 0.0 and math.copysign(1.0, number) < 0.0:
        raise ValueError(f"{label} must not be negative zero")
    return number


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _require_exact_bool(
    value: Mapping[str, Any],
    field_name: str,
    expected: bool,
    label: str,
) -> None:
    actual = _boolean(value[field_name], f"{label}.{field_name}")
    if actual is not expected:
        raise ValueError(f"{label}.{field_name} must be {expected}")


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("object keys must be strings")
            if unicodedata.normalize("NFC", key) != key:
                raise ValueError("object keys must use NFC-normalized text")
            result[key] = _plain(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        frozen = {
            key: _freeze(value[key])
            for key in sorted(value)
        }
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


# Concise aliases retain discoverability without creating a second contract.
hash_separation_acceptance_thresholds = (
    separation_acceptance_artifact_sha256
)
validate_separation_acceptance = (
    validate_separation_acceptance_thresholds
)
freeze_separation_acceptance = freeze_separation_acceptance_thresholds
load_separation_acceptance = load_separation_acceptance_thresholds


__all__ = [
    "MAX_ACCEPTANCE_BYTES",
    "MAX_HIDDEN_MANIFEST_BYTES",
    "SEPARATION_ACCEPTANCE_AGGREGATE_POLICY",
    "SEPARATION_ACCEPTANCE_DECISION_POLICY",
    "SEPARATION_ACCEPTANCE_OFFLINE_POLICY",
    "SEPARATION_ACCEPTANCE_PAIRED_POLICY",
    "SEPARATION_ACCEPTANCE_SCHEMA",
    "SEPARATION_HIDDEN_MANIFEST_SCHEMA",
    "canonical_json_bytes",
    "deployment_profile_id",
    "freeze_separation_acceptance",
    "freeze_separation_acceptance_thresholds",
    "hash_separation_acceptance_thresholds",
    "load_separation_acceptance",
    "load_separation_acceptance_thresholds",
    "separation_acceptance_artifact_sha256",
    "validate_separation_acceptance",
    "validate_separation_acceptance_thresholds",
    "verify_hidden_evaluation_manifest",
]
