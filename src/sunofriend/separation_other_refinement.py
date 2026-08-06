"""Model-independent contract for refining grouped ``other`` in Studio.

This module deliberately selects, downloads and executes no separator.  It
defines the immutable parent/target/residual boundary that a later, separately
approved challenger must satisfy.  The first contract permits one requested
target at a time (guitar or keys) and always retains the exact residual.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
from types import MappingProxyType
from typing import Any, Mapping
import wave

from .audio_formats import file_sha256
from .separation_profiles import (
    OTHER_REFINEMENT_DEMUCS_MLX_PROFILE_ID,
    SCNET_RELEASE_PROFILE_ID,
    separation_profile,
)


OTHER_REFINEMENT_SCOPE_ID = "other-refinement-v1"
OTHER_REFINEMENT_PROFILE_ID = "other-target-residual-contract-v1"
OTHER_REFINEMENT_REGISTRY_SCHEMA = "sunofriend.other-refinement-registry.v1"
OTHER_REFINEMENT_PLAN_SCHEMA = "sunofriend.other-refinement-plan.v1"
OTHER_REFINEMENT_RESULT_SCHEMA = "sunofriend.other-refinement-result.v1"
OTHER_REFINEMENT_RESIDUAL_DEFINITION = (
    "persisted-parent-other-minus-persisted-requested-target-v1"
)
OTHER_REFINEMENT_TOLERANCE_LSB = 2
OTHER_REFINEMENT_SAMPLE_RATE = 44_100
OTHER_REFINEMENT_CHANNELS = 2
OTHER_REFINEMENT_PCM_BITS = 24
PCM24_SCALE = 8_388_608
PCM24_MIN = -8_388_608
PCM24_MAX = 8_388_607

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_NODE_ID_RE = re.compile(r"^node:[0-9a-f]{64}$")
_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,127}$")
_PLAN_FIELDS = frozenset(
    {
        "schema",
        "document_sha256",
        "plan_id",
        "status",
        "scope_id",
        "contract_profile_id",
        "parent",
        "request",
        "output_contract",
        "studio",
        "permissions",
        "effects",
        "blockers",
    }
)
_RESULT_FIELDS = frozenset(
    {
        "schema",
        "document_sha256",
        "status",
        "scope_id",
        "contract_profile_id",
        "plan_id",
        "plan_document_sha256",
        "parent",
        "request",
        "execution",
        "outputs",
        "additive_accounting",
        "review_status",
        "permissions",
        "effects",
        "limitations",
    }
)
_PERMISSIONS = MappingProxyType(
    {
        "model_execution_permitted": False,
        "checkpoint_download_permitted": False,
        "dependency_install_permitted": False,
        "public_execution_permitted": False,
        "source_graph_activation_permitted": False,
        "automatic_midi_activation_permitted": False,
        "automatic_candidate_selection_permitted": False,
        "automatic_model_promotion_permitted": False,
    }
)
_PLAN_EFFECTS = MappingProxyType(
    {
        "model_executed": False,
        "checkpoint_downloaded": False,
        "dependency_installed": False,
        "network_used": False,
        "audio_created": False,
        "source_graph_mutated": False,
        "midi_created": False,
        "candidate_selected": False,
    }
)
_TARGETS: Mapping[str, Mapping[str, str]] = MappingProxyType(
    {
        "guitar": MappingProxyType(
            {
                "target_id": "guitar",
                "canonical_role": "rhythm",
                "label": "Guitar target",
                "relative_path": "STEMS/guitar.wav",
            }
        ),
        "keys": MappingProxyType(
            {
                "target_id": "keys",
                "canonical_role": "keys",
                "label": "Keys target",
                "relative_path": "STEMS/keys.wav",
            }
        ),
    }
)
_BLOCKERS = (
    "The first target-separation candidate is pinned, but dependency and checkpoint installation still require explicit approval.",
    "The one allowed in-memory fractional-segment remediation has not passed installed-artifact compatibility under network denial.",
    "No candidate has passed offline model construction, resource and output-contract gates.",
    "Studio can describe and compare future candidates, but no refinement runner is exposed.",
)
_LIMITATIONS = (
    "Exact reconstruction proves accounting, not target isolation or musical usefulness.",
    "The requested target can contain bleed and the residual can retain target content.",
    "No parent, child, MIDI candidate or model is selected by this result.",
)


def other_refinement_registry() -> dict[str, Any]:
    """Return the Studio-only, non-executable refinement registration."""

    candidate = separation_profile(OTHER_REFINEMENT_DEMUCS_MLX_PROFILE_ID)
    return {
        "schema": OTHER_REFINEMENT_REGISTRY_SCHEMA,
        "scope_id": OTHER_REFINEMENT_SCOPE_ID,
        "profile_id": OTHER_REFINEMENT_PROFILE_ID,
        "status": "blocked",
        "release_tier": "studio_challenger",
        "registration_surface": "studio_only",
        "contract_available": True,
        "implementation_available": False,
        "executable": False,
        "candidate_profile_id": candidate.profile_id,
        "candidate_status": candidate.status,
        "candidate_setup_available": True,
        "candidate_setup_script": candidate.setup_script,
        "candidate_model_id": candidate.model_id,
        "candidate_model_revision": candidate.model_revision,
        "candidate_target_mapping": {
            "guitar": {
                "model_role": "guitar",
                "semantic_status": "direct_experimental_role",
            },
            "keys": {
                "model_role": "piano",
                "semantic_status": "disclosed_piano_proxy_not_general_keys",
            },
        },
        "parent_scope_id": "core-four-stems-v1",
        "parent_profile_id": SCNET_RELEASE_PROFILE_ID,
        "parent_role": "other",
        "supported_targets": [dict(value) for value in _TARGETS.values()],
        "one_target_per_run": True,
        "residual_role": "other",
        "residual_definition": OTHER_REFINEMENT_RESIDUAL_DEFINITION,
        "maximum_reconstruction_error_lsb": OTHER_REFINEMENT_TOLERANCE_LSB,
        "blockers": list(_BLOCKERS),
        "policy": {
            "parent_and_children_mutually_exclusive": True,
            "explicit_review_required_before_source_graph_activation": True,
            "parent_and_children_cannot_both_enter_midi": True,
            "candidate_comparison_selects_no_winner": True,
            "mixed_or_negative_feedback_disables_core_four": False,
            "registration_downloads_or_installs_nothing": True,
        },
    }


def build_other_refinement_plan(
    *,
    parent_profile_id: str,
    parent_report_sha256: str,
    parent_node_id: str,
    parent_audio_sha256: str,
    parent_geometry: Mapping[str, Any],
    target_id: str,
) -> dict[str, Any]:
    """Bind one exact core-four ``other`` asset to one requested target."""

    _safe_identifier(parent_profile_id, "parent_profile_id")
    if parent_profile_id != SCNET_RELEASE_PROFILE_ID:
        raise ValueError(
            "other-refinement parent profile must be the verified core-four profile"
        )
    _sha256(parent_report_sha256, "parent_report_sha256")
    _node_id(parent_node_id)
    _sha256(parent_audio_sha256, "parent_audio_sha256")
    geometry = _canonical_geometry(parent_geometry)
    target = _target(target_id)
    seed: dict[str, Any] = {
        "schema": OTHER_REFINEMENT_PLAN_SCHEMA,
        "status": "contract_only_no_execution",
        "scope_id": OTHER_REFINEMENT_SCOPE_ID,
        "contract_profile_id": OTHER_REFINEMENT_PROFILE_ID,
        "parent": {
            "scope_id": "core-four-stems-v1",
            "profile_id": parent_profile_id,
            "separation_report_sha256": parent_report_sha256,
            "node_id": parent_node_id,
            "role": "other",
            "audio_sha256": parent_audio_sha256,
            "geometry": geometry,
        },
        "request": {
            "target_id": target["target_id"],
            "canonical_target_role": target["canonical_role"],
            "one_target_only": True,
        },
        "output_contract": {
            "roles": [
                {
                    "kind": "requested_target",
                    "role": target["canonical_role"],
                    "declared_role": target["target_id"],
                    "relative_path": target["relative_path"],
                },
                {
                    "kind": "residual",
                    "role": "other",
                    "declared_role": "other_residual",
                    "relative_path": "STEMS/other-residual.wav",
                },
            ],
            "exact_role_count": 2,
            "clock_must_match_parent": True,
            "finite_samples_required": True,
            "bounded_pcm24_samples_required": True,
            "residual_definition": OTHER_REFINEMENT_RESIDUAL_DEFINITION,
            "reconstruction_equation": "parent_other = requested_target + residual",
            "maximum_reconstruction_error_lsb": OTHER_REFINEMENT_TOLERANCE_LSB,
            "reconstruction_is_separation_accuracy": False,
        },
        "studio": {
            "release_tier": "studio_challenger",
            "registration_surface": "studio_only",
            "candidate_roots_must_be_separate": True,
            "display_order_selects_no_winner": True,
            "explicit_review_required_before_activation": True,
            "parent_and_children_mutually_exclusive": True,
        },
        "permissions": dict(_PERMISSIONS),
        "effects": dict(_PLAN_EFFECTS),
        "blockers": list(_BLOCKERS),
    }
    seed["plan_id"] = f"sha256:{_document_sha256(seed)}"
    seed["document_sha256"] = _document_sha256(seed)
    return validate_other_refinement_plan(seed)


def validate_other_refinement_plan(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one path-free immutable refinement plan."""

    value = _json_copy(document)
    if set(value) != _PLAN_FIELDS:
        raise ValueError("other-refinement plan fields differ")
    if value.get("schema") != OTHER_REFINEMENT_PLAN_SCHEMA:
        raise ValueError("unsupported other-refinement plan schema")
    expected_hash = _document_sha256(value)
    if value.get("document_sha256") != expected_hash:
        raise ValueError("other-refinement plan document hash differs")
    plan_seed = dict(value)
    plan_seed.pop("document_sha256")
    plan_id = plan_seed.pop("plan_id", None)
    if plan_id != f"sha256:{_document_sha256(plan_seed)}":
        raise ValueError("other-refinement plan identity differs")
    if (
        value.get("status") != "contract_only_no_execution"
        or value.get("scope_id") != OTHER_REFINEMENT_SCOPE_ID
        or value.get("contract_profile_id") != OTHER_REFINEMENT_PROFILE_ID
    ):
        raise ValueError("other-refinement plan identity fields differ")

    parent = _exact_mapping(
        value.get("parent"),
        {
            "scope_id",
            "profile_id",
            "separation_report_sha256",
            "node_id",
            "role",
            "audio_sha256",
            "geometry",
        },
        "other-refinement parent",
    )
    if parent["scope_id"] != "core-four-stems-v1" or parent["role"] != "other":
        raise ValueError("other-refinement parent must be core-four grouped other")
    _safe_identifier(parent["profile_id"], "parent profile_id")
    if parent["profile_id"] != SCNET_RELEASE_PROFILE_ID:
        raise ValueError(
            "other-refinement parent profile must be the verified core-four profile"
        )
    _sha256(parent["separation_report_sha256"], "parent report SHA-256")
    _node_id(parent["node_id"])
    _sha256(parent["audio_sha256"], "parent audio SHA-256")
    _canonical_geometry(parent["geometry"])

    request = _exact_mapping(
        value.get("request"),
        {"target_id", "canonical_target_role", "one_target_only"},
        "other-refinement request",
    )
    target = _target(request["target_id"])
    if (
        request["canonical_target_role"] != target["canonical_role"]
        or request["one_target_only"] is not True
    ):
        raise ValueError("other-refinement request differs from its target contract")
    _validate_output_contract(value.get("output_contract"), target=target)
    _validate_studio_contract(value.get("studio"))
    if value.get("permissions") != dict(_PERMISSIONS):
        raise ValueError("other-refinement plan grants a permission")
    if value.get("effects") != dict(_PLAN_EFFECTS):
        raise ValueError("other-refinement plan effects differ")
    if value.get("blockers") != list(_BLOCKERS):
        raise ValueError("other-refinement plan blockers differ")
    _assert_no_private_absolute_path(value)
    return value


def build_other_refinement_result(
    plan: Mapping[str, Any],
    *,
    root: str | Path,
    parent_relative_path: str,
    target_relative_path: str,
    residual_relative_path: str,
    execution: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify already-persisted PCM24 outputs without running a backend."""

    import numpy as np

    bound_plan = validate_other_refinement_plan(plan)
    base = Path(root).expanduser().absolute()
    if not base.is_dir() or base.is_symlink():
        raise ValueError("other-refinement result root must be a real directory")
    target = _target(bound_plan["request"]["target_id"])
    expected_paths = {
        "parent": _safe_relative_path(parent_relative_path),
        "target": _safe_relative_path(target_relative_path),
        "residual": _safe_relative_path(residual_relative_path),
    }
    if str(expected_paths["target"]) != target["relative_path"]:
        raise ValueError("other-refinement target path differs from the plan")
    if str(expected_paths["residual"]) != "STEMS/other-residual.wav":
        raise ValueError("other-refinement residual path differs from the plan")
    paths = {
        name: _inside_regular_file(base, relative, label=name)
        for name, relative in expected_paths.items()
    }
    arrays: dict[str, Any] = {}
    artifacts: dict[str, dict[str, Any]] = {}
    for name, path in paths.items():
        array, geometry = _read_pcm24_integers(path, np=np)
        arrays[name] = array
        artifacts[name] = {
            "relative_path": str(expected_paths[name]),
            "sha256": file_sha256(path),
            "bytes": path.stat().st_size,
            "geometry": geometry,
            "peak": float(np.max(np.abs(array.astype(np.float64))) / PCM24_SCALE),
            "rms": float(
                np.sqrt(np.mean(np.square(array.astype(np.float64)))) / PCM24_SCALE
            ),
            "full_scale_sample_count": int(
                np.count_nonzero((array == PCM24_MIN) | (array == PCM24_MAX))
            ),
        }
    parent_binding = bound_plan["parent"]
    if artifacts["parent"]["sha256"] != parent_binding["audio_sha256"]:
        raise ValueError("other-refinement parent audio hash differs from the plan")
    if artifacts["parent"]["geometry"] != parent_binding["geometry"]:
        raise ValueError("other-refinement parent geometry differs from the plan")
    if not (
        artifacts["target"]["geometry"]
        == artifacts["residual"]["geometry"]
        == artifacts["parent"]["geometry"]
    ):
        raise ValueError("other-refinement output clocks differ")
    if not (
        arrays["target"].shape == arrays["residual"].shape == arrays["parent"].shape
    ):
        raise ValueError("other-refinement output shapes differ")
    reconstructed = arrays["target"].astype(np.int64) + arrays["residual"].astype(
        np.int64
    )
    error = arrays["parent"].astype(np.int64) - reconstructed
    maximum_error = int(np.max(np.abs(error)))
    rms_error = float(np.sqrt(np.mean(np.square(error.astype(np.float64)))))
    if maximum_error > OTHER_REFINEMENT_TOLERANCE_LSB:
        raise ValueError("other-refinement persisted reconstruction exceeds tolerance")
    if not np.any(arrays["parent"]):
        raise ValueError("other-refinement parent is silent")

    execution_value = _validate_execution(execution)
    result_effects = {
        "contract_validation_executed": True,
        "model_executed_by_validator": False,
        "checkpoint_downloaded_by_validator": False,
        "dependency_installed_by_validator": False,
        "network_used_by_validator": False,
        "audio_mutated_by_validator": False,
        "source_graph_mutated": False,
        "midi_created": False,
        "candidate_selected": False,
    }
    value: dict[str, Any] = {
        "schema": OTHER_REFINEMENT_RESULT_SCHEMA,
        "status": "complete_output_contract_evidence_no_activation",
        "scope_id": OTHER_REFINEMENT_SCOPE_ID,
        "contract_profile_id": OTHER_REFINEMENT_PROFILE_ID,
        "plan_id": bound_plan["plan_id"],
        "plan_document_sha256": bound_plan["document_sha256"],
        "parent": {
            "role": "other",
            **artifacts["parent"],
        },
        "request": dict(bound_plan["request"]),
        "execution": execution_value,
        "outputs": {
            "target": {
                "kind": "requested_target",
                "role": target["canonical_role"],
                "declared_role": target["target_id"],
                **artifacts["target"],
            },
            "residual": {
                "kind": "residual",
                "role": "other",
                "declared_role": "other_residual",
                "definition": OTHER_REFINEMENT_RESIDUAL_DEFINITION,
                "target_sha256": artifacts["target"]["sha256"],
                **artifacts["residual"],
            },
        },
        "additive_accounting": {
            "equation": "parent_other = requested_target + residual",
            "maximum_absolute_error_lsb": maximum_error,
            "root_mean_square_error_lsb": rms_error,
            "tolerance_lsb": OTHER_REFINEMENT_TOLERANCE_LSB,
            "passed": True,
            "used_for_separation_accuracy_claim": False,
        },
        "review_status": "not_reviewed",
        "permissions": dict(_PERMISSIONS),
        "effects": result_effects,
        "limitations": list(_LIMITATIONS),
    }
    value["document_sha256"] = _document_sha256(value)
    return validate_other_refinement_result(value, plan=bound_plan, root=base)


def validate_other_refinement_result(
    document: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Validate result identity and optionally re-hash every PCM24 artifact."""

    value = _json_copy(document)
    bound_plan = validate_other_refinement_plan(plan)
    if set(value) != _RESULT_FIELDS:
        raise ValueError("other-refinement result fields differ")
    if value.get("schema") != OTHER_REFINEMENT_RESULT_SCHEMA:
        raise ValueError("unsupported other-refinement result schema")
    if value.get("document_sha256") != _document_sha256(value):
        raise ValueError("other-refinement result document hash differs")
    if (
        value.get("status") != "complete_output_contract_evidence_no_activation"
        or value.get("scope_id") != OTHER_REFINEMENT_SCOPE_ID
        or value.get("contract_profile_id") != OTHER_REFINEMENT_PROFILE_ID
        or value.get("plan_id") != bound_plan["plan_id"]
        or value.get("plan_document_sha256") != bound_plan["document_sha256"]
    ):
        raise ValueError("other-refinement result plan binding differs")
    if value.get("request") != bound_plan["request"]:
        raise ValueError("other-refinement result request differs")
    _validate_execution(value.get("execution"))
    if value.get("permissions") != dict(_PERMISSIONS):
        raise ValueError("other-refinement result grants a permission")
    expected_effects = {
        "contract_validation_executed": True,
        "model_executed_by_validator": False,
        "checkpoint_downloaded_by_validator": False,
        "dependency_installed_by_validator": False,
        "network_used_by_validator": False,
        "audio_mutated_by_validator": False,
        "source_graph_mutated": False,
        "midi_created": False,
        "candidate_selected": False,
    }
    if value.get("effects") != expected_effects:
        raise ValueError("other-refinement result effects differ")
    if value.get("review_status") != "not_reviewed":
        raise ValueError("other-refinement result cannot manufacture a review")
    if value.get("limitations") != list(_LIMITATIONS):
        raise ValueError("other-refinement result limitations differ")
    accounting = _exact_mapping(
        value.get("additive_accounting"),
        {
            "equation",
            "maximum_absolute_error_lsb",
            "root_mean_square_error_lsb",
            "tolerance_lsb",
            "passed",
            "used_for_separation_accuracy_claim",
        },
        "other-refinement additive accounting",
    )
    if (
        accounting["equation"] != "parent_other = requested_target + residual"
        or type(accounting["maximum_absolute_error_lsb"]) is not int
        or accounting["maximum_absolute_error_lsb"] < 0
        or accounting["maximum_absolute_error_lsb"] > OTHER_REFINEMENT_TOLERANCE_LSB
        or not _finite_nonnegative(accounting["root_mean_square_error_lsb"])
        or accounting["tolerance_lsb"] != OTHER_REFINEMENT_TOLERANCE_LSB
        or accounting["passed"] is not True
        or accounting["used_for_separation_accuracy_claim"] is not False
    ):
        raise ValueError("other-refinement additive accounting differs")
    outputs = _exact_mapping(
        value.get("outputs"), {"target", "residual"}, "other-refinement outputs"
    )
    target_definition = _target(bound_plan["request"]["target_id"])
    target_output = _validate_artifact(
        outputs["target"],
        expected_kind="requested_target",
        expected_role=target_definition["canonical_role"],
        expected_declared_role=target_definition["target_id"],
    )
    residual_output = _validate_artifact(
        outputs["residual"],
        expected_kind="residual",
        expected_role="other",
        expected_declared_role="other_residual",
        residual=True,
    )
    parent = _validate_artifact(
        value.get("parent"),
        expected_kind=None,
        expected_role="other",
        expected_declared_role=None,
        parent=True,
    )
    if (
        parent["sha256"] != bound_plan["parent"]["audio_sha256"]
        or parent["geometry"] != bound_plan["parent"]["geometry"]
        or target_output["geometry"] != parent["geometry"]
        or residual_output["geometry"] != parent["geometry"]
        or residual_output["target_sha256"] != target_output["sha256"]
        or residual_output["definition"] != OTHER_REFINEMENT_RESIDUAL_DEFINITION
    ):
        raise ValueError("other-refinement result artifact binding differs")
    if root is not None:
        import numpy as np

        base = Path(root).expanduser().absolute()
        if not base.is_dir() or base.is_symlink():
            raise ValueError("other-refinement result root must be a real directory")
        arrays: dict[str, Any] = {}
        for label, artifact in (
            ("parent", parent),
            ("target", target_output),
            ("residual", residual_output),
        ):
            path = _inside_regular_file(
                base,
                _safe_relative_path(artifact["relative_path"]),
                label=label,
            )
            if (
                file_sha256(path) != artifact["sha256"]
                or path.stat().st_size != artifact["bytes"]
            ):
                raise ValueError(f"other-refinement {label} artifact changed")
            array, geometry = _read_pcm24_integers(path, np=np)
            arrays[label] = array
            peak = float(np.max(np.abs(array.astype(np.float64))) / PCM24_SCALE)
            rms = float(
                np.sqrt(np.mean(np.square(array.astype(np.float64)))) / PCM24_SCALE
            )
            full_scale = int(
                np.count_nonzero((array == PCM24_MIN) | (array == PCM24_MAX))
            )
            if (
                geometry != artifact["geometry"]
                or peak != artifact["peak"]
                or rms != artifact["rms"]
                or full_scale != artifact["full_scale_sample_count"]
            ):
                raise ValueError(f"other-refinement {label} PCM24 evidence differs")
        error = arrays["parent"].astype(np.int64) - (
            arrays["target"].astype(np.int64) + arrays["residual"].astype(np.int64)
        )
        maximum_error = int(np.max(np.abs(error)))
        rms_error = float(np.sqrt(np.mean(np.square(error.astype(np.float64)))))
        if (
            maximum_error != accounting["maximum_absolute_error_lsb"]
            or rms_error != accounting["root_mean_square_error_lsb"]
            or maximum_error > OTHER_REFINEMENT_TOLERANCE_LSB
        ):
            raise ValueError("other-refinement persisted additive accounting differs")
    _assert_no_private_absolute_path(value)
    return value


def create_other_refinement_synthetic_fixture(
    destination: str | Path,
    *,
    target_id: str = "guitar",
) -> dict[str, Any]:
    """Create deterministic target/residual PCM24 evidence without a model."""

    import numpy as np

    target = _target(target_id)
    root = Path(destination).expanduser().absolute()
    if os.path.lexists(root):
        raise FileExistsError(f"other-refinement fixture already exists: {root}")
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(mode=0o700)
    try:
        frames = 2 * OTHER_REFINEMENT_SAMPLE_RATE
        times = np.arange(frames, dtype=np.float64) / OTHER_REFINEMENT_SAMPLE_RATE
        guitar = np.zeros(frames, dtype=np.float64)
        for index, start in enumerate(
            range(0, frames, OTHER_REFINEMENT_SAMPLE_RATE // 2)
        ):
            length = min(OTHER_REFINEMENT_SAMPLE_RATE, frames - start)
            local = np.arange(length, dtype=np.float64) / OTHER_REFINEMENT_SAMPLE_RATE
            frequency = (196.0, 246.94165, 293.66477, 329.62756)[index % 4]
            pluck = (
                np.sin(2 * np.pi * frequency * local)
                + 0.36 * np.sin(2 * np.pi * frequency * 2 * local + 0.2)
                + 0.18 * np.sin(2 * np.pi * frequency * 3 * local + 0.5)
            ) * np.exp(-3.4 * local)
            guitar[start : start + length] += pluck
        guitar /= float(np.max(np.abs(guitar)))
        guitar_stereo = np.column_stack((guitar, np.roll(guitar, 23))) * 0.18

        keys = (
            np.sin(2 * np.pi * 220.0 * times)
            + 0.7 * np.sin(2 * np.pi * 277.18263 * times + 0.4)
            + 0.5 * np.sin(2 * np.pi * 329.62756 * times + 0.8)
        )
        keys *= 0.5 - 0.5 * np.cos(np.pi * np.minimum(times / 0.18, 1.0))
        keys /= float(np.max(np.abs(keys)))
        keys_stereo = np.column_stack((keys, np.roll(keys, 41))) * 0.12

        target_float, residual_float = (
            (guitar_stereo, keys_stereo)
            if target["target_id"] == "guitar"
            else (keys_stereo, guitar_stereo)
        )
        target_int = np.rint(target_float * PCM24_SCALE).astype(np.int32)
        residual_int = np.rint(residual_float * PCM24_SCALE).astype(np.int32)
        parent_wide = target_int.astype(np.int64) + residual_int.astype(np.int64)
        if int(parent_wide.min()) < PCM24_MIN or int(parent_wide.max()) > PCM24_MAX:
            raise RuntimeError("synthetic other-refinement parent exceeds PCM24")
        parent_int = parent_wide.astype(np.int32)
        relative_paths = {
            "parent": PurePosixPath("PARENT/other.wav"),
            "target": PurePosixPath(target["relative_path"]),
            "residual": PurePosixPath("STEMS/other-residual.wav"),
        }
        for name, values in (
            ("parent", parent_int),
            ("target", target_int),
            ("residual", residual_int),
        ):
            path = root.joinpath(*relative_paths[name].parts)
            _write_pcm24(path, values, np=np)
            path.chmod(0o600)
        parent_path = root.joinpath(*relative_paths["parent"].parts)
        geometry = {
            "sample_rate": OTHER_REFINEMENT_SAMPLE_RATE,
            "channels": OTHER_REFINEMENT_CHANNELS,
            "frames": frames,
            "duration_seconds": 2.0,
            "sample_width_bytes": 3,
        }
        parent_hash = file_sha256(parent_path)
        report_hash = hashlib.sha256(
            ("sunofriend.synthetic-core-four-parent.v1\0" + parent_hash).encode("ascii")
        ).hexdigest()
        parent_node_id = (
            "node:"
            + hashlib.sha256(
                ("synthetic-other-parent\0" + parent_hash).encode("ascii")
            ).hexdigest()
        )
        plan = build_other_refinement_plan(
            parent_profile_id=SCNET_RELEASE_PROFILE_ID,
            parent_report_sha256=report_hash,
            parent_node_id=parent_node_id,
            parent_audio_sha256=parent_hash,
            parent_geometry=geometry,
            target_id=target["target_id"],
        )
        plan_path = root / "other-refinement-plan.json"
        _write_json_exclusive(plan_path, plan)
        execution = {
            "kind": "model_free_synthetic",
            "profile_id": OTHER_REFINEMENT_PROFILE_ID,
            "backend_id": "deterministic-oscillator-fixture-v1",
            "runtime_identity_sha256": hashlib.sha256(
                Path(__file__).read_bytes()
            ).hexdigest(),
            "model_identity_sha256": None,
            "network_used": False,
            "model_executed": False,
            "installed_or_downloaded_during_contract_run": False,
        }
        result = build_other_refinement_result(
            plan,
            root=root,
            parent_relative_path=str(relative_paths["parent"]),
            target_relative_path=str(relative_paths["target"]),
            residual_relative_path=str(relative_paths["residual"]),
            execution=execution,
        )
        result_path = root / "other-refinement-synthetic-result.json"
        _write_json_exclusive(result_path, result)
        return {
            "status": result["status"],
            "root": str(root),
            "plan": str(plan_path),
            "result": str(result_path),
            "target_id": target["target_id"],
            "additive_accounting": dict(result["additive_accounting"]),
            "artifacts": {
                name: str(root.joinpath(*relative.parts))
                for name, relative in relative_paths.items()
            },
        }
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise


def _validate_output_contract(value: Any, *, target: Mapping[str, str]) -> None:
    contract = _exact_mapping(
        value,
        {
            "roles",
            "exact_role_count",
            "clock_must_match_parent",
            "finite_samples_required",
            "bounded_pcm24_samples_required",
            "residual_definition",
            "reconstruction_equation",
            "maximum_reconstruction_error_lsb",
            "reconstruction_is_separation_accuracy",
        },
        "other-refinement output contract",
    )
    expected_roles = [
        {
            "kind": "requested_target",
            "role": target["canonical_role"],
            "declared_role": target["target_id"],
            "relative_path": target["relative_path"],
        },
        {
            "kind": "residual",
            "role": "other",
            "declared_role": "other_residual",
            "relative_path": "STEMS/other-residual.wav",
        },
    ]
    if (
        contract["roles"] != expected_roles
        or contract["exact_role_count"] != 2
        or contract["clock_must_match_parent"] is not True
        or contract["finite_samples_required"] is not True
        or contract["bounded_pcm24_samples_required"] is not True
        or contract["residual_definition"] != OTHER_REFINEMENT_RESIDUAL_DEFINITION
        or contract["reconstruction_equation"]
        != "parent_other = requested_target + residual"
        or contract["maximum_reconstruction_error_lsb"]
        != OTHER_REFINEMENT_TOLERANCE_LSB
        or contract["reconstruction_is_separation_accuracy"] is not False
    ):
        raise ValueError("other-refinement output contract differs")


def _validate_studio_contract(value: Any) -> None:
    expected = {
        "release_tier": "studio_challenger",
        "registration_surface": "studio_only",
        "candidate_roots_must_be_separate": True,
        "display_order_selects_no_winner": True,
        "explicit_review_required_before_activation": True,
        "parent_and_children_mutually_exclusive": True,
    }
    if value != expected:
        raise ValueError("other-refinement Studio contract differs")


def _validate_execution(value: Any) -> dict[str, Any]:
    execution = _exact_mapping(
        value,
        {
            "kind",
            "profile_id",
            "backend_id",
            "runtime_identity_sha256",
            "model_identity_sha256",
            "network_used",
            "model_executed",
            "installed_or_downloaded_during_contract_run",
        },
        "other-refinement execution",
    )
    if execution["kind"] not in {"model_free_synthetic", "candidate_backend"}:
        raise ValueError("other-refinement execution kind differs")
    _safe_identifier(execution["profile_id"], "execution profile_id")
    _safe_identifier(execution["backend_id"], "execution backend_id")
    _sha256(execution["runtime_identity_sha256"], "runtime identity SHA-256")
    if execution["kind"] == "model_free_synthetic":
        if (
            execution["model_identity_sha256"] is not None
            or execution["model_executed"] is not False
        ):
            raise ValueError("model-free execution claims a model")
    else:
        _sha256(execution["model_identity_sha256"], "model identity SHA-256")
        if execution["model_executed"] is not True:
            raise ValueError("candidate execution does not disclose model execution")
    if (
        execution["network_used"] is not False
        or execution["installed_or_downloaded_during_contract_run"] is not False
    ):
        raise ValueError("other-refinement execution is not offline and preinstalled")
    return execution


def _validate_artifact(
    value: Any,
    *,
    expected_kind: str | None,
    expected_role: str,
    expected_declared_role: str | None,
    residual: bool = False,
    parent: bool = False,
) -> dict[str, Any]:
    common = {
        "role",
        "relative_path",
        "sha256",
        "bytes",
        "geometry",
        "peak",
        "rms",
        "full_scale_sample_count",
    }
    fields = set(common)
    if not parent:
        fields.update({"kind", "declared_role"})
    if residual:
        fields.update({"definition", "target_sha256"})
    artifact = _exact_mapping(value, fields, "other-refinement artifact")
    if artifact["role"] != expected_role:
        raise ValueError("other-refinement artifact role differs")
    if not parent and (
        artifact["kind"] != expected_kind
        or artifact["declared_role"] != expected_declared_role
    ):
        raise ValueError("other-refinement artifact declaration differs")
    _safe_relative_path(artifact["relative_path"])
    _sha256(artifact["sha256"], "artifact SHA-256")
    if type(artifact["bytes"]) is not int or artifact["bytes"] <= 44:
        raise ValueError("other-refinement artifact byte count differs")
    _canonical_geometry(artifact["geometry"])
    if not _finite_nonnegative(artifact["peak"]) or artifact["peak"] > 1.0:
        raise ValueError("other-refinement artifact peak differs")
    if not _finite_nonnegative(artifact["rms"]) or artifact["rms"] > 1.0:
        raise ValueError("other-refinement artifact RMS differs")
    if (
        type(artifact["full_scale_sample_count"]) is not int
        or artifact["full_scale_sample_count"] < 0
    ):
        raise ValueError("other-refinement full-scale count differs")
    if residual:
        _sha256(artifact["target_sha256"], "residual target SHA-256")
    return artifact


def _canonical_geometry(value: Any) -> dict[str, Any]:
    geometry = _exact_mapping(
        value,
        {
            "sample_rate",
            "channels",
            "frames",
            "duration_seconds",
            "sample_width_bytes",
        },
        "other-refinement geometry",
    )
    if (
        geometry["sample_rate"] != OTHER_REFINEMENT_SAMPLE_RATE
        or geometry["channels"] != OTHER_REFINEMENT_CHANNELS
        or type(geometry["frames"]) is not int
        or geometry["frames"] <= 0
        or geometry["sample_width_bytes"] != 3
        or not isinstance(geometry["duration_seconds"], (int, float))
        or isinstance(geometry["duration_seconds"], bool)
        or not math.isfinite(float(geometry["duration_seconds"]))
        or not math.isclose(
            float(geometry["duration_seconds"]),
            geometry["frames"] / OTHER_REFINEMENT_SAMPLE_RATE,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
    ):
        raise ValueError(
            "other-refinement audio must be canonical stereo 44.1 kHz PCM24"
        )
    geometry["duration_seconds"] = float(geometry["duration_seconds"])
    return geometry


def _read_pcm24_integers(path: Path, *, np: Any) -> tuple[Any, dict[str, Any]]:
    with wave.open(str(path), "rb") as reader:
        if (
            reader.getnchannels() != OTHER_REFINEMENT_CHANNELS
            or reader.getsampwidth() != 3
            or reader.getframerate() != OTHER_REFINEMENT_SAMPLE_RATE
            or reader.getcomptype() != "NONE"
        ):
            raise ValueError("other-refinement audio is not canonical PCM24")
        frames = reader.getnframes()
        contents = reader.readframes(frames)
        if reader.readframes(1):
            raise ValueError("other-refinement audio has undeclared frames")
    if len(contents) != frames * OTHER_REFINEMENT_CHANNELS * 3:
        raise ValueError("other-refinement PCM24 payload is truncated")
    packed = np.frombuffer(contents, dtype=np.uint8).reshape(-1, 3)
    unsigned = (
        packed[:, 0].astype(np.int32)
        | (packed[:, 1].astype(np.int32) << 8)
        | (packed[:, 2].astype(np.int32) << 16)
    )
    signed = np.where(unsigned & 0x800000, unsigned - 0x1000000, unsigned)
    return signed.astype(np.int32).reshape(frames, OTHER_REFINEMENT_CHANNELS), {
        "sample_rate": OTHER_REFINEMENT_SAMPLE_RATE,
        "channels": OTHER_REFINEMENT_CHANNELS,
        "frames": frames,
        "duration_seconds": frames / OTHER_REFINEMENT_SAMPLE_RATE,
        "sample_width_bytes": 3,
    }


def _write_pcm24(path: Path, values: Any, *, np: Any) -> None:
    integers = np.asarray(values)
    if integers.ndim != 2 or integers.shape[1] != OTHER_REFINEMENT_CHANNELS:
        raise ValueError("other-refinement PCM24 output geometry differs")
    if integers.size and (
        int(integers.min()) < PCM24_MIN or int(integers.max()) > PCM24_MAX
    ):
        raise ValueError("other-refinement PCM24 output exceeds its range")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(OTHER_REFINEMENT_CHANNELS)
        writer.setsampwidth(3)
        writer.setframerate(OTHER_REFINEMENT_SAMPLE_RATE)
        writer.writeframes(_pack_pcm24(integers, np=np))


def _pack_pcm24(values: Any, *, np: Any) -> bytes:
    integers = np.asarray(values)
    if integers.dtype.kind not in "iu":
        raise ValueError("other-refinement PCM24 packer requires integers")
    if integers.size and (
        int(integers.min()) < PCM24_MIN or int(integers.max()) > PCM24_MAX
    ):
        raise ValueError("other-refinement PCM24 sample exceeds its range")
    unsigned = integers.astype(np.int32, copy=False).reshape(-1) & 0xFFFFFF
    packed = np.empty((len(unsigned), 3), dtype=np.uint8)
    packed[:, 0] = unsigned & 0xFF
    packed[:, 1] = (unsigned >> 8) & 0xFF
    packed[:, 2] = (unsigned >> 16) & 0xFF
    return packed.tobytes()


def _inside_regular_file(root: Path, relative: PurePosixPath, *, label: str) -> Path:
    path = root.joinpath(*relative.parts)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"other-refinement {label} must be a regular file")
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"other-refinement {label} escapes its root") from exc
    return resolved


def _safe_relative_path(value: Any) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise ValueError("other-refinement path must be a relative string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError("other-refinement path must stay inside its root")
    if str(path) != value or any(not part for part in path.parts):
        raise ValueError("other-refinement path is not canonical")
    return path


def _target(value: Any) -> Mapping[str, str]:
    if not isinstance(value, str) or value not in _TARGETS:
        raise ValueError(
            "other-refinement target must be exactly one of: " + ", ".join(_TARGETS)
        )
    return _TARGETS[value]


def _exact_mapping(
    value: Any,
    fields: set[str] | frozenset[str],
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(fields):
        raise ValueError(f"{label} fields differ")
    return _json_copy(value)


def _safe_identifier(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SAFE_ID_RE.fullmatch(value):
        raise ValueError(f"{label} is invalid")


def _sha256(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} is invalid")


def _node_id(value: Any) -> None:
    if not isinstance(value, str) or not _NODE_ID_RE.fullmatch(value):
        raise ValueError("other-refinement parent node_id is invalid")


def _finite_nonnegative(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) >= 0.0
    )


def _assert_no_private_absolute_path(value: Any) -> None:
    if isinstance(value, Mapping):
        for item in value.values():
            _assert_no_private_absolute_path(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_private_absolute_path(item)
    elif isinstance(value, str) and (
        value.startswith(("/", "~/", "file://")) or re.match(r"^[A-Za-z]:[\\/]", value)
    ):
        raise ValueError("other-refinement document contains an absolute path")


def _document_sha256(document: Mapping[str, Any]) -> str:
    value = _json_copy(document)
    value.pop("document_sha256", None)
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _write_json_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    with path.open("xb") as handle:
        handle.write(
            (
                json.dumps(
                    value,
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                    allow_nan=False,
                )
                + "\n"
            ).encode("utf-8")
        )
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)


__all__ = [
    "OTHER_REFINEMENT_PLAN_SCHEMA",
    "OTHER_REFINEMENT_PROFILE_ID",
    "OTHER_REFINEMENT_REGISTRY_SCHEMA",
    "OTHER_REFINEMENT_RESIDUAL_DEFINITION",
    "OTHER_REFINEMENT_RESULT_SCHEMA",
    "OTHER_REFINEMENT_SCOPE_ID",
    "OTHER_REFINEMENT_TOLERANCE_LSB",
    "build_other_refinement_plan",
    "build_other_refinement_result",
    "create_other_refinement_synthetic_fixture",
    "other_refinement_registry",
    "validate_other_refinement_plan",
    "validate_other_refinement_result",
]
