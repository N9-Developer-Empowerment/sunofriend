"""Two-variant deterministic remix deltas for audio-native source state v1.

The first product slice deliberately edits only a hash-bound rhythm estimate
while preserving the separately confirmed melodic identity anchor.  Plans are
no-effect.  Rendering needs a second exact owner authorization and produces no
preference, training label, product selection or model change.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from .audio_formats import file_sha256
from .remix_delta import inspect_remix_audio
from .remix_source_anchor import (
    REMIX_SOURCE_ANCHOR_CONFIRMATION_SCHEMA,
    REMIX_SOURCE_IDENTITY_SCHEMA,
    REMIX_SOURCE_OWNER_REGISTRY_SCHEMA,
    validate_remix_source_anchor_confirmation,
    validate_remix_source_anchor_preflight,
    validate_remix_source_identity_state,
    validate_remix_source_owner_registry,
)
from .remix_source_state import REMIX_SOURCE_STATE_SCHEMA, validate_remix_source_state
from .source_receipt import canonical_json_bytes, document_sha256


REMIX_SOURCE_DELTA_PLAN_SCHEMA = "sunofriend.remix-source-delta-ab-plan.v0"
REMIX_SOURCE_DELTA_AUTHORIZATION_SCHEMA = (
    "sunofriend.remix-source-delta-ab-render-authorization.v0"
)
REMIX_SOURCE_DELTA_RESULT_SCHEMA = "sunofriend.remix-source-delta-ab-result.v0"
REMIX_SOURCE_DELTA_VERIFICATION_SCHEMA = (
    "sunofriend.remix-source-delta-ab-verification.v0"
)


def create_remix_source_delta_plan(
    source_state: Mapping[str, Any],
    anchor_preflight: Mapping[str, Any],
    identity_state: Mapping[str, Any],
    owner_registry: Mapping[str, Any],
    anchor_confirmation: Mapping[str, Any],
    *,
    target_estimate: Mapping[str, Any],
    variants: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Create a no-effect two-variant rhythm-delta plan."""

    state, preflight, identity, registry, confirmation = _evidence(
        source_state,
        anchor_preflight,
        identity_state,
        owner_registry,
        anchor_confirmation,
    )
    target = _target_record(target_estimate, state["source_control"])
    if target["audio_sha256"] in {
        row["audio_sha256"] for row in identity["separation_estimates"]
    }:
        raise ValueError("rhythm edit target must be distinct from the anchor estimate")
    checked_variants = _variant_records(variants, target["geometry"]["frames"])
    anchor = identity["owner_anchors"][0]
    document: dict[str, Any] = {
        "schema": REMIX_SOURCE_DELTA_PLAN_SCHEMA,
        "status": "ready_two_variant_rhythm_delta_no_render",
        "method_natures": ["D", "H"],
        "binding": {
            "source_state_schema": REMIX_SOURCE_STATE_SCHEMA,
            "source_state_sha256": state["document_sha256"],
            "anchor_preflight_sha256": preflight["document_sha256"],
            "identity_state_schema": REMIX_SOURCE_IDENTITY_SCHEMA,
            "identity_state_sha256": identity["document_sha256"],
            "owner_registry_schema": REMIX_SOURCE_OWNER_REGISTRY_SCHEMA,
            "owner_registry_sha256": registry["document_sha256"],
            "anchor_confirmation_schema": REMIX_SOURCE_ANCHOR_CONFIRMATION_SCHEMA,
            "anchor_confirmation_sha256": confirmation["document_sha256"],
        },
        "source_control": dict(state["source_control"]),
        "preserved_anchor": {
            "anchor_id": anchor["anchor_id"],
            "anchor_kind": anchor["anchor_kind"],
            "owner_label": anchor["owner_label"],
            "source_estimate_id": anchor["source_estimate_id"],
            "geometry": dict(anchor["geometry"]),
            "policy": "anchor_estimate_not_directly_edited",
            "separation_bleed_may_remain": True,
        },
        "target_estimate": target,
        "variant_family": {
            "operation": "source_plus_gain_delta_times_rhythm_estimate",
            "formula": "source + (gain - 1) * target_estimate",
            "musical_function": "rhythm",
            "one_variable": "rhythm_estimate_gain_envelope",
            "variants": checked_variants,
        },
        "render_policy": {
            "source_control_copy": "byte_exact",
            "candidate_encoding": "WAV_PCM_24",
            "sample_rate_or_channel_change": False,
            "normalisation": False,
            "limiting": False,
            "clipping_permitted": False,
        },
        "review_policy": {
            "original_and_both_variants_required": True,
            "hidden_ab_order": True,
            "playback_creates_decision": False,
            "review_creates_training_label": False,
            "separate_training_admission_required": True,
        },
        "authority": {
            "plan_only": True,
            "render_authorized": False,
            "training_execution_authorized": False,
            "product_selection_authorized": False,
            "checkpoint_promotion_authorized": False,
        },
        "effects": _plan_effects(),
        "model_used": False,
        "training_used": False,
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_source_delta_plan(
        document, state, preflight, identity, registry, confirmation
    )


def validate_remix_source_delta_plan(
    plan: Mapping[str, Any],
    source_state: Mapping[str, Any],
    anchor_preflight: Mapping[str, Any],
    identity_state: Mapping[str, Any],
    owner_registry: Mapping[str, Any],
    anchor_confirmation: Mapping[str, Any],
) -> dict[str, Any]:
    state, preflight, identity, registry, confirmation = _evidence(
        source_state,
        anchor_preflight,
        identity_state,
        owner_registry,
        anchor_confirmation,
    )
    document = _verified(plan, REMIX_SOURCE_DELTA_PLAN_SCHEMA, "delta plan")
    if set(document) != {
        "schema",
        "status",
        "method_natures",
        "binding",
        "source_control",
        "preserved_anchor",
        "target_estimate",
        "variant_family",
        "render_policy",
        "review_policy",
        "authority",
        "effects",
        "model_used",
        "training_used",
        "network_used",
        "document_sha256",
    }:
        raise ValueError("remix source delta plan fields changed")
    if document["status"] != "ready_two_variant_rhythm_delta_no_render":
        raise ValueError("remix source delta plan status changed")
    expected_binding = {
        "source_state_schema": REMIX_SOURCE_STATE_SCHEMA,
        "source_state_sha256": state["document_sha256"],
        "anchor_preflight_sha256": preflight["document_sha256"],
        "identity_state_schema": REMIX_SOURCE_IDENTITY_SCHEMA,
        "identity_state_sha256": identity["document_sha256"],
        "owner_registry_schema": REMIX_SOURCE_OWNER_REGISTRY_SCHEMA,
        "owner_registry_sha256": registry["document_sha256"],
        "anchor_confirmation_schema": REMIX_SOURCE_ANCHOR_CONFIRMATION_SCHEMA,
        "anchor_confirmation_sha256": confirmation["document_sha256"],
    }
    if (
        document["binding"] != expected_binding
        or document["source_control"] != state["source_control"]
    ):
        raise ValueError("remix source delta plan evidence binding changed")
    anchor = identity["owner_anchors"][0]
    if document["preserved_anchor"] != {
        "anchor_id": anchor["anchor_id"],
        "anchor_kind": anchor["anchor_kind"],
        "owner_label": anchor["owner_label"],
        "source_estimate_id": anchor["source_estimate_id"],
        "geometry": anchor["geometry"],
        "policy": "anchor_estimate_not_directly_edited",
        "separation_bleed_may_remain": True,
    }:
        raise ValueError("preserved remix anchor changed")
    target = _target_record(document["target_estimate"], state["source_control"])
    if target["audio_sha256"] in {
        row["audio_sha256"] for row in identity["separation_estimates"]
    }:
        raise ValueError("rhythm edit target must be distinct from anchor estimate")
    family = document["variant_family"]
    if not isinstance(family, Mapping) or set(family) != {
        "operation",
        "formula",
        "musical_function",
        "one_variable",
        "variants",
    }:
        raise ValueError("remix source variant family fields changed")
    if {key: family[key] for key in family if key != "variants"} != {
        "operation": "source_plus_gain_delta_times_rhythm_estimate",
        "formula": "source + (gain - 1) * target_estimate",
        "musical_function": "rhythm",
        "one_variable": "rhythm_estimate_gain_envelope",
    }:
        raise ValueError("remix source variant operation changed")
    variants = _variant_records(family["variants"], target["geometry"]["frames"])
    if variants != family["variants"]:
        raise ValueError("remix source variant projection changed")
    if document["render_policy"] != {
        "source_control_copy": "byte_exact",
        "candidate_encoding": "WAV_PCM_24",
        "sample_rate_or_channel_change": False,
        "normalisation": False,
        "limiting": False,
        "clipping_permitted": False,
    } or document["review_policy"] != {
        "original_and_both_variants_required": True,
        "hidden_ab_order": True,
        "playback_creates_decision": False,
        "review_creates_training_label": False,
        "separate_training_admission_required": True,
    }:
        raise ValueError("remix source delta policy changed")
    if (
        document["authority"]
        != {
            "plan_only": True,
            "render_authorized": False,
            "training_execution_authorized": False,
            "product_selection_authorized": False,
            "checkpoint_promotion_authorized": False,
        }
        or document["effects"] != _plan_effects()
    ):
        raise ValueError("remix source delta plan claims authority or effects")
    if document["method_natures"] != ["D", "H"] or any(
        document[key] is not False
        for key in ("model_used", "training_used", "network_used")
    ):
        raise ValueError("remix source delta plan method boundary changed")
    _reject_paths(document)
    return document


def create_remix_source_delta_render_authorization(
    plan: Mapping[str, Any], *, confirm_private_ab_preview: bool = False
) -> dict[str, Any]:
    """Authorize rendering once for the exact no-effect plan identity."""

    _verified(plan, REMIX_SOURCE_DELTA_PLAN_SCHEMA, "delta plan")
    if confirm_private_ab_preview is not True:
        raise ValueError(
            "explicit owner authorization for the private A/B preview is required"
        )
    document: dict[str, Any] = {
        "schema": REMIX_SOURCE_DELTA_AUTHORIZATION_SCHEMA,
        "status": "explicit_owner_one_private_ab_render",
        "binding": {"plan_sha256": plan["document_sha256"]},
        "owner_confirmation": {
            "one_exact_private_ab_preview": True,
            "anchor_estimate_is_not_direct_edit_target": True,
            "separation_bleed_may_remain": True,
        },
        "authority": {
            "render_one_exact_plan": True,
            "training_execution_authorized": False,
            "training_label_created": False,
            "product_selection_authorized": False,
            "checkpoint_promotion_authorized": False,
            "release_authorized": False,
        },
        "effects": _plan_effects(),
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_source_delta_render_authorization(document, plan)


def validate_remix_source_delta_render_authorization(
    authorization: Mapping[str, Any], plan: Mapping[str, Any]
) -> dict[str, Any]:
    checked = _verified(plan, REMIX_SOURCE_DELTA_PLAN_SCHEMA, "delta plan")
    document = _verified(
        authorization, REMIX_SOURCE_DELTA_AUTHORIZATION_SCHEMA, "render authorization"
    )
    if set(document) != {
        "schema",
        "status",
        "binding",
        "owner_confirmation",
        "authority",
        "effects",
        "network_used",
        "document_sha256",
    }:
        raise ValueError("remix delta render authorization fields changed")
    if (
        document["status"] != "explicit_owner_one_private_ab_render"
        or document["binding"] != {"plan_sha256": checked["document_sha256"]}
        or document["owner_confirmation"]
        != {
            "one_exact_private_ab_preview": True,
            "anchor_estimate_is_not_direct_edit_target": True,
            "separation_bleed_may_remain": True,
        }
        or document["authority"]
        != {
            "render_one_exact_plan": True,
            "training_execution_authorized": False,
            "training_label_created": False,
            "product_selection_authorized": False,
            "checkpoint_promotion_authorized": False,
            "release_authorized": False,
        }
        or document["effects"] != _plan_effects()
        or document["network_used"] is not False
    ):
        raise ValueError("remix delta render authorization changed")
    return document


def render_remix_source_delta(
    plan: Mapping[str, Any],
    authorization: Mapping[str, Any],
    *,
    source_audio: str | Path,
    target_estimate_audio: str | Path,
    out_dir: str | Path,
    expected_plan_sha256: str,
    confirm_render: bool = False,
) -> dict[str, Any]:
    """Render one fresh exact-control plus two-candidate private package."""

    checked = _verified(plan, REMIX_SOURCE_DELTA_PLAN_SCHEMA, "delta plan")
    auth = validate_remix_source_delta_render_authorization(authorization, checked)
    if checked["document_sha256"] != expected_plan_sha256:
        raise ValueError("remix delta plan identity changed")
    if confirm_render is not True:
        raise ValueError("separate exact render confirmation is required")
    source = _regular_audio(source_audio, checked["source_control"], "source control")
    target = _regular_audio(
        target_estimate_audio, checked["target_estimate"], "target estimate"
    )
    output = Path(out_dir).expanduser().resolve()
    if output.exists():
        raise FileExistsError("remix delta output already exists")
    for immutable in (source.parent.resolve(), target.parent.resolve()):
        try:
            output.relative_to(immutable)
        except ValueError:
            continue
        raise ValueError("remix delta output must be outside immutable source evidence")
    np, sf = _audio_dependencies()
    source_values, rate = sf.read(source, dtype="float64", always_2d=True)
    target_values, target_rate = sf.read(target, dtype="float64", always_2d=True)
    if rate != target_rate or source_values.shape != target_values.shape:
        raise ValueError("remix delta inputs no longer share exact geometry")
    candidates: dict[str, Any] = {}
    frame = np.arange(source_values.shape[0], dtype=np.float64)
    for variant in checked["variant_family"]["variants"]:
        points = variant["points"]
        db = np.interp(
            frame, [row["frame"] for row in points], [row["delta_db"] for row in points]
        )
        gain = np.power(10.0, db / 20.0)[:, None]
        values = source_values + (gain - 1.0) * target_values
        if (
            not np.isfinite(values).all()
            or float(np.max(np.abs(values), initial=0.0)) >= 1.0
        ):
            raise ValueError("remix delta candidate is non-finite or would clip")
        candidates[variant["variant_id"]] = values

    output.parent.mkdir(parents=True, exist_ok=True)
    output.parent.chmod(0o700)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.building-", dir=output.parent)
    )
    temporary.chmod(0o700)
    try:
        (temporary / "AUDIO").mkdir(mode=0o700)
        (temporary / "EVIDENCE").mkdir(mode=0o700)
        (temporary / "TECHNICAL").mkdir(mode=0o700)
        original = temporary / "AUDIO/original-context.wav"
        _copy_private(source, original)
        artifacts: dict[str, Any] = {
            "original": _record(original, temporary),
            "candidates": [],
        }
        for index, variant in enumerate(checked["variant_family"]["variants"]):
            path = temporary / f"AUDIO/candidate-{index + 1}.wav"
            sf.write(
                path,
                candidates[variant["variant_id"]],
                rate,
                subtype="PCM_24",
                format="WAV",
            )
            path.chmod(0o600)
            artifacts["candidates"].append(
                {"variant_id": variant["variant_id"], **_record(path, temporary)}
            )
        plan_path = temporary / "EVIDENCE/plan.json"
        auth_path = temporary / "EVIDENCE/render-authorization.json"
        _write_private(plan_path, canonical_json_bytes(checked))
        _write_private(auth_path, canonical_json_bytes(auth))
        artifacts["plan"] = _record(plan_path, temporary)
        artifacts["authorization"] = _record(auth_path, temporary)
        result: dict[str, Any] = {
            "schema": REMIX_SOURCE_DELTA_RESULT_SCHEMA,
            "status": "complete_unreviewed_two_variant_private_preview",
            "binding": {
                "plan_sha256": checked["document_sha256"],
                "authorization_sha256": auth["document_sha256"],
            },
            "artifacts": artifacts,
            "geometry": dict(checked["source_control"]["geometry"]),
            "processing": dict(checked["render_policy"]),
            "authority": {
                "human_review_created": False,
                "training_label_created": False,
                "training_execution_authorized": False,
                "product_selection_authorized": False,
                "checkpoint_promotion_authorized": False,
                "release_authorized": False,
            },
            "effects": {
                "source_mutated": False,
                "target_estimate_mutated": False,
                "two_audio_derivatives_rendered": True,
                "human_review_created": False,
                "training_started": False,
                "model_weights_changed": False,
                "product_selection_changed": False,
            },
            "model_used": False,
            "training_used": False,
            "network_used": False,
        }
        result["document_sha256"] = document_sha256(result)
        _write_private(
            temporary / "TECHNICAL/result.json", canonical_json_bytes(result)
        )
        temporary.rename(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return verify_remix_source_delta_result(output)


def verify_remix_source_delta_result(root_value: str | Path) -> dict[str, Any]:
    root = Path(root_value).expanduser().resolve(strict=True)
    expected = {
        "AUDIO/original-context.wav",
        "AUDIO/candidate-1.wav",
        "AUDIO/candidate-2.wav",
        "EVIDENCE/plan.json",
        "EVIDENCE/render-authorization.json",
        "TECHNICAL/result.json",
    }
    actual = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    if actual != expected or any(path.is_symlink() for path in root.rglob("*")):
        raise ValueError("remix source delta result file roster changed")
    result = _read_json(
        root / "TECHNICAL/result.json", REMIX_SOURCE_DELTA_RESULT_SCHEMA, "result"
    )
    if set(result) != {
        "schema",
        "status",
        "binding",
        "artifacts",
        "geometry",
        "processing",
        "authority",
        "effects",
        "model_used",
        "training_used",
        "network_used",
        "document_sha256",
    }:
        raise ValueError("remix source delta result fields changed")
    if result["status"] != "complete_unreviewed_two_variant_private_preview":
        raise ValueError("remix source delta result status changed")
    plan = _read_json(
        root / "EVIDENCE/plan.json", REMIX_SOURCE_DELTA_PLAN_SCHEMA, "plan"
    )
    auth = _read_json(
        root / "EVIDENCE/render-authorization.json",
        REMIX_SOURCE_DELTA_AUTHORIZATION_SCHEMA,
        "authorization",
    )
    validate_remix_source_delta_render_authorization(auth, plan)
    if result["binding"] != {
        "plan_sha256": plan["document_sha256"],
        "authorization_sha256": auth["document_sha256"],
    }:
        raise ValueError("remix source delta result binding changed")
    if set(result["artifacts"]) != {"original", "candidates", "plan", "authorization"}:
        raise ValueError("remix source delta artifact fields changed")
    if len(result["artifacts"]["candidates"]) != 2:
        raise ValueError("remix source delta candidate artifact roster changed")
    for record in [
        result["artifacts"]["original"],
        result["artifacts"]["plan"],
        result["artifacts"]["authorization"],
        *result["artifacts"]["candidates"],
    ]:
        _artifact(root, record, "result artifact")
    if (
        inspect_remix_audio(root / result["artifacts"]["original"]["path"])
        != plan["source_control"]
    ):
        raise ValueError("remix source delta original control changed")
    if [row["variant_id"] for row in result["artifacts"]["candidates"]] != [
        row["variant_id"] for row in plan["variant_family"]["variants"]
    ]:
        raise ValueError("remix source delta candidate roster changed")
    if (
        result["geometry"] != plan["source_control"]["geometry"]
        or result["processing"] != plan["render_policy"]
    ):
        raise ValueError("remix source delta geometry or processing changed")
    for row in result["artifacts"]["candidates"]:
        if set(row) != {"variant_id", "path", "bytes", "sha256"}:
            raise ValueError("remix source delta candidate artifact fields changed")
        observed = inspect_remix_audio(root / row["path"])
        if (
            observed["geometry"] != result["geometry"]
            or observed["audio_sha256"] != row["sha256"]
            or observed["audio_bytes"] != row["bytes"]
        ):
            raise ValueError("remix source delta candidate audio changed")
    if (
        result["authority"]
        != {
            "human_review_created": False,
            "training_label_created": False,
            "training_execution_authorized": False,
            "product_selection_authorized": False,
            "checkpoint_promotion_authorized": False,
            "release_authorized": False,
        }
        or result["effects"]
        != {
            "source_mutated": False,
            "target_estimate_mutated": False,
            "two_audio_derivatives_rendered": True,
            "human_review_created": False,
            "training_started": False,
            "model_weights_changed": False,
            "product_selection_changed": False,
        }
        or result["model_used"] is not False
        or result["training_used"] is not False
        or result["network_used"] is not False
    ):
        raise ValueError("remix source delta result authority expanded")
    return result


def _evidence(
    source_state: Mapping[str, Any],
    preflight: Mapping[str, Any],
    identity: Mapping[str, Any],
    registry: Mapping[str, Any],
    confirmation: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    state = validate_remix_source_state(source_state)
    checked_preflight = validate_remix_source_anchor_preflight(preflight, state)
    checked_identity = validate_remix_source_identity_state(identity, state)
    checked_registry = validate_remix_source_owner_registry(
        registry, state, checked_identity
    )
    checked_confirmation = validate_remix_source_anchor_confirmation(
        confirmation, checked_preflight, state, checked_identity, checked_registry
    )
    if len(checked_identity["owner_anchors"]) != 1:
        raise ValueError(
            "first source delta comparison requires exactly one owner anchor"
        )
    return (
        state,
        checked_preflight,
        checked_identity,
        checked_registry,
        checked_confirmation,
    )


def _target_record(
    value: Mapping[str, Any], control: Mapping[str, Any]
) -> dict[str, Any]:
    expected = {
        "source_estimate_id",
        "source_kind",
        "role_interpretation",
        "estimated_role",
        "musical_function",
        "audio_sha256",
        "audio_bytes",
        "geometry",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("rhythm target estimate fields changed")
    if (
        value["source_kind"] != "separation_estimate"
        or value["role_interpretation"] != "estimate_not_ground_truth"
        or value["estimated_role"] != "drums"
        or value["musical_function"] != "rhythm"
    ):
        raise ValueError("first source delta target must be a drums rhythm estimate")
    if value["geometry"] != control["geometry"]:
        raise ValueError("rhythm target estimate geometry differs from source")
    if (
        not isinstance(value["audio_sha256"], str)
        or len(value["audio_sha256"]) != 64
        or not isinstance(value["audio_bytes"], int)
        or value["audio_bytes"] <= 0
    ):
        raise ValueError("rhythm target estimate identity is invalid")
    for key in ("source_estimate_id",):
        if (
            not isinstance(value[key], str)
            or not value[key]
            or any(char in value[key] for char in "/\\")
        ):
            raise ValueError("rhythm target estimate identifier is invalid")
    return dict(value)


def _variant_records(
    values: Sequence[Mapping[str, Any]], frames: int
) -> list[dict[str, Any]]:
    if (
        not isinstance(values, Sequence)
        or isinstance(values, (str, bytes))
        or len(values) != 2
    ):
        raise ValueError("exactly two rhythm delta variants are required")
    result: list[dict[str, Any]] = []
    ids: set[str] = set()
    for value in values:
        if not isinstance(value, Mapping) or set(value) != {"variant_id", "points"}:
            raise ValueError("rhythm delta variant fields changed")
        variant_id = str(value["variant_id"])
        if (
            not variant_id
            or variant_id in ids
            or any(char in variant_id for char in "/\\")
        ):
            raise ValueError("rhythm delta variant identifier is invalid")
        ids.add(variant_id)
        points = value["points"]
        if not isinstance(points, list) or not 3 <= len(points) <= 8:
            raise ValueError("rhythm delta variant needs 3 to 8 points")
        checked_points: list[dict[str, Any]] = []
        last = -1
        for point in points:
            if not isinstance(point, Mapping) or set(point) != {"frame", "delta_db"}:
                raise ValueError("rhythm delta point fields changed")
            frame = point["frame"]
            delta = point["delta_db"]
            if (
                isinstance(frame, bool)
                or not isinstance(frame, int)
                or frame <= last
                or not 0 <= frame <= frames
            ):
                raise ValueError("rhythm delta point frame is invalid")
            if (
                isinstance(delta, bool)
                or not isinstance(delta, (int, float))
                or not math.isfinite(float(delta))
                or not -12.0 <= float(delta) <= 0.0
            ):
                raise ValueError("rhythm delta gain must stay between -12 and 0 dB")
            checked_points.append({"frame": frame, "delta_db": float(delta)})
            last = frame
        if (
            checked_points[0]["frame"] != 0
            or checked_points[-1]["frame"] != frames
            or not any(row["delta_db"] < 0 for row in checked_points)
        ):
            raise ValueError(
                "rhythm delta must span the full clock and contain a change"
            )
        result.append({"variant_id": variant_id, "points": checked_points})
    if result[0]["points"] == result[1]["points"]:
        raise ValueError("rhythm delta variants must differ")
    return result


def _verified(value: Mapping[str, Any], schema: str, label: str) -> dict[str, Any]:
    document = dict(value)
    if document.get("schema") != schema:
        raise ValueError(f"{label} schema changed")
    expected = document.get("document_sha256")
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if expected != document_sha256(unsigned):
        raise ValueError(f"{label} document SHA-256 changed")
    return document


def _read_json(path: Path, schema: str, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is missing or unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be readable JSON") from exc
    return _verified(value, schema, label)


def _regular_audio(value: str | Path, expected: Mapping[str, Any], label: str) -> Path:
    path = Path(value).expanduser().resolve(strict=True)
    if (
        path.is_symlink()
        or not path.is_file()
        or inspect_remix_audio(path)
        != {key: expected[key] for key in ("audio_sha256", "audio_bytes", "geometry")}
    ):
        raise ValueError(f"{label} identity changed")
    return path


def _record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def _artifact(root: Path, record: Mapping[str, Any], label: str) -> Path:
    relative = record.get("path")
    if not isinstance(relative, str):
        raise ValueError(f"{label} path changed")
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts:
        raise ValueError(f"{label} path escaped")
    path = (root / Path(*posix.parts)).resolve()
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size != record.get("bytes")
        or file_sha256(path) != record.get("sha256")
    ):
        raise ValueError(f"{label} identity changed")
    return path


def _copy_private(source: Path, destination: Path) -> None:
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with source.open("rb") as reader, os.fdopen(descriptor, "wb") as writer:
        shutil.copyfileobj(reader, writer)
        writer.flush()
        os.fsync(writer.fileno())


def _write_private(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _audio_dependencies() -> tuple[Any, Any]:
    try:
        import numpy as np
        import soundfile as sf
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("remix delta rendering needs NumPy and SoundFile") from exc
    return np, sf


def _plan_effects() -> dict[str, bool]:
    return {
        "source_mutated": False,
        "target_estimate_mutated": False,
        "audio_derivative_rendered": False,
        "human_review_created": False,
        "training_label_created": False,
        "training_started": False,
        "model_weights_changed": False,
        "product_selection_changed": False,
    }


def _reject_paths(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if any(
                token in str(key).casefold()
                for token in ("path", "filename", "directory", "url")
            ):
                raise ValueError(
                    "path-free remix source delta plan contains a path field"
                )
            _reject_paths(item)
    elif isinstance(value, list):
        for item in value:
            _reject_paths(item)
    elif isinstance(value, str) and (
        value.startswith(("/", "~", "file:")) or ":\\" in value
    ):
        raise ValueError("path-free remix source delta plan contains a local path")


__all__ = [
    "REMIX_SOURCE_DELTA_AUTHORIZATION_SCHEMA",
    "REMIX_SOURCE_DELTA_PLAN_SCHEMA",
    "REMIX_SOURCE_DELTA_RESULT_SCHEMA",
    "REMIX_SOURCE_DELTA_VERIFICATION_SCHEMA",
    "create_remix_source_delta_plan",
    "create_remix_source_delta_render_authorization",
    "render_remix_source_delta",
    "validate_remix_source_delta_plan",
    "validate_remix_source_delta_render_authorization",
    "verify_remix_source_delta_result",
]
