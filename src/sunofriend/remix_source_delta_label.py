"""Explicit owner labels for one exact source-delta A/B audition.

The module owns anonymous presentation recovery, exact render binding,
path-free label construction and private atomic persistence.  It creates one
training-corpus label only; it never starts training, changes model weights or
selects a product remix.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any, Literal, Mapping

from .remix_source_delta import verify_remix_source_delta_result
from .source_receipt import canonical_json_bytes, document_sha256


REMIX_SOURCE_DELTA_PAIRWISE_LABEL_SCHEMA = (
    "sunofriend.remix-source-delta-pairwise-preference-label.v0"
)

PairwiseOutcome = Literal["a", "b", "equivalent", "neither", "cannot_tell"]
IdentityRelationship = Literal[
    "preserved", "partly_preserved", "lost", "cannot_tell"
]

_OUTCOMES = frozenset({"a", "b", "equivalent", "neither", "cannot_tell"})
_IDENTITY_RELATIONSHIPS = frozenset(
    {"preserved", "partly_preserved", "lost", "cannot_tell"}
)
_REASON_CODES = frozenset(
    {
        "background_noise",
        "change_more_useful",
        "identity_better_preserved",
        "separation_artifact",
        "change_inaudible",
        "both_unusable",
        "unable_to_compare",
        "energy_shape",
        "groove_fit",
        "arrangement_fit",
        "other",
    }
)


@dataclass(frozen=True)
class RemixSourceDeltaReviewDecision:
    """The complete human authority required to admit one local label."""

    presentation_seed: int
    heard_control: bool
    heard_a: bool
    heard_b: bool
    outcome: PairwiseOutcome
    identity_a: IdentityRelationship
    identity_b: IdentityRelationship
    reason_codes: tuple[str, ...]
    admit_owner_local_training: bool
    reviewed_at: str | None = None


def admit_remix_source_delta_pairwise_label(
    render_root: str | Path,
    *,
    decision: RemixSourceDeltaReviewDecision,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Verify, create and atomically save one explicit owner-local label."""

    render = Path(render_root).expanduser().resolve(strict=True)
    result, plan = _verified_render(render)
    label = _create_label(result, plan, decision)
    validate_remix_source_delta_pairwise_label(label, render)
    output = Path(out_dir).expanduser().resolve()
    if output.exists():
        raise FileExistsError("remix source-delta label output already exists")
    if output == render or render in output.parents:
        raise ValueError(
            "remix source-delta label output must stay outside the immutable render"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.building-", dir=output.parent)
    )
    temporary.chmod(0o700)
    try:
        labels = temporary / "LABELS"
        labels.mkdir(mode=0o700)
        destination = labels / f"{label['document_sha256']}.json"
        destination.write_bytes(canonical_json_bytes(label))
        destination.chmod(0o600)
        temporary.rename(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return label


def validate_remix_source_delta_pairwise_label(
    label: Mapping[str, Any], render_root: str | Path
) -> dict[str, Any]:
    """Revalidate a path-free label against the exact local render bytes."""

    result, plan = _verified_render(render_root)
    document = _verified_label(label)
    _validate_structure(document)
    if document["binding"] != _binding(result, plan):
        raise ValueError("remix source-delta label evidence binding changed")
    seed = document["presentation"].get("seed")
    mapping = _display_variant_ids(result, seed)
    if document["presentation"] != {
        "seed": seed,
        "reviewed_at": document["presentation"].get("reviewed_at"),
        "display_variant_ids": mapping,
    }:
        raise ValueError("remix source-delta presentation evidence changed")
    expected_left, expected_right = _variant_sides(result, plan, mapping)
    if document["left"] != expected_left or document["right"] != expected_right:
        raise ValueError("remix source-delta label variant evidence changed")
    expected_control = _control_record(result)
    if document["control"] != expected_control:
        raise ValueError("remix source-delta label control evidence changed")
    _validate_decision(document)
    return document


def _create_label(
    result: Mapping[str, Any],
    plan: Mapping[str, Any],
    decision: RemixSourceDeltaReviewDecision,
) -> dict[str, Any]:
    _validate_requested_decision(decision)
    mapping = _display_variant_ids(result, decision.presentation_seed)
    left, right = _variant_sides(result, plan, mapping)
    document: dict[str, Any] = {
        "schema": REMIX_SOURCE_DELTA_PAIRWISE_LABEL_SCHEMA,
        "status": "complete_explicit_owner_pairwise_label",
        "method_natures": ["D", "H"],
        "binding": _binding(result, plan),
        "control": _control_record(result),
        "left": left,
        "right": right,
        "listening": {
            "heard_control": True,
            "heard_left": True,
            "heard_right": True,
            "playback_implies_label": False,
        },
        "outcome": {"a": "left", "b": "right"}.get(
            decision.outcome, decision.outcome
        ),
        "identity_relationships": {
            "left": decision.identity_a,
            "right": decision.identity_b,
        },
        "reason_codes": list(decision.reason_codes),
        "presentation": {
            "seed": decision.presentation_seed,
            "reviewed_at": decision.reviewed_at,
            "display_variant_ids": mapping,
        },
        "training": {
            "explicitly_admitted": True,
            "admission_scope": "owner_local_training",
            "training_eligible": False,
        },
        "authority": {
            "automatic_preference": False,
            "selected_for_product": False,
            "training_execution_authorized": False,
            "checkpoint_promotion_authorized": False,
        },
        "effects": {
            "training_label_created": True,
            "training_started": False,
            "model_weights_changed": False,
            "product_selection_changed": False,
            "audio_mutated": False,
        },
        "privacy": {
            "owner_local_only": True,
            "paths_embedded": False,
            "audio_embedded": False,
            "cloud_training_approved": False,
        },
        "model_used": False,
        "training_used": False,
        "network_used": False,
    }
    document["document_sha256"] = document_sha256(document)
    return document


def _verified_render(
    root_value: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = Path(root_value).expanduser().resolve(strict=True)
    result = verify_remix_source_delta_result(root)
    try:
        plan = json.loads((root / "EVIDENCE/plan.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("remix source-delta plan JSON is unreadable") from exc
    if not isinstance(plan, dict) or result["binding"]["plan_sha256"] != plan.get(
        "document_sha256"
    ):
        raise ValueError("remix source-delta result plan binding changed")
    return result, plan


def _binding(result: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
    source = plan["binding"]
    return {
        "render_result_sha256": result["document_sha256"],
        "plan_sha256": plan["document_sha256"],
        "source_state_sha256": source["source_state_sha256"],
        "anchor_preflight_sha256": source["anchor_preflight_sha256"],
        "identity_state_sha256": source["identity_state_sha256"],
        "owner_registry_sha256": source["owner_registry_sha256"],
        "anchor_confirmation_sha256": source["anchor_confirmation_sha256"],
        "variant_family_sha256": document_sha256(plan["variant_family"]),
    }


def _display_variant_ids(
    result: Mapping[str, Any], presentation_seed: Any
) -> dict[str, str]:
    if isinstance(presentation_seed, bool) or not isinstance(presentation_seed, int):
        raise ValueError("presentation seed must be an integer")
    ordered = sorted(
        row["variant_id"] for row in result["artifacts"]["candidates"]
    )
    digest = hashlib.sha256(
        f"{presentation_seed}:{result['document_sha256']}".encode()
    ).digest()
    if digest[0] & 1:
        ordered.reverse()
    return {"a": ordered[0], "b": ordered[1]}


def _variant_sides(
    result: Mapping[str, Any],
    plan: Mapping[str, Any],
    mapping: Mapping[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    artifacts = {
        row["variant_id"]: row for row in result["artifacts"]["candidates"]
    }
    specifications = {
        row["variant_id"]: row for row in plan["variant_family"]["variants"]
    }

    def side(display_id: str) -> dict[str, Any]:
        variant_id = mapping[display_id]
        artifact = artifacts[variant_id]
        specification = specifications[variant_id]
        return {
            "variant_id": variant_id,
            "audio_sha256": artifact["sha256"],
            "audio_bytes": artifact["bytes"],
            "variant_specification_sha256": document_sha256(specification),
        }

    return side("a"), side("b")


def _control_record(result: Mapping[str, Any]) -> dict[str, Any]:
    original = result["artifacts"]["original"]
    return {
        "audio_sha256": original["sha256"],
        "audio_bytes": original["bytes"],
        "geometry": dict(result["geometry"]),
    }


def _validate_requested_decision(decision: RemixSourceDeltaReviewDecision) -> None:
    if not all((decision.heard_control, decision.heard_a, decision.heard_b)):
        raise ValueError("pairwise label requires heard control, A and B")
    if decision.admit_owner_local_training is not True:
        raise ValueError("pairwise label requires explicit local-training admission")
    _validate_values(
        decision.outcome,
        decision.identity_a,
        decision.identity_b,
        decision.reason_codes,
    )
    if isinstance(decision.presentation_seed, bool) or not isinstance(
        decision.presentation_seed, int
    ):
        raise ValueError("presentation seed must be an integer")
    if decision.reviewed_at is not None and not decision.reviewed_at.strip():
        raise ValueError("reviewed_at must be non-empty text or null")


def _verified_label(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("remix source-delta label must be an object")
    document = dict(value)
    if document.get("schema") != REMIX_SOURCE_DELTA_PAIRWISE_LABEL_SCHEMA:
        raise ValueError("remix source-delta label schema changed")
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if document.get("document_sha256") != document_sha256(unsigned):
        raise ValueError("remix source-delta label identity changed")
    return document


def _validate_structure(document: Mapping[str, Any]) -> None:
    expected = {
        "schema",
        "status",
        "method_natures",
        "binding",
        "control",
        "left",
        "right",
        "listening",
        "outcome",
        "identity_relationships",
        "reason_codes",
        "presentation",
        "training",
        "authority",
        "effects",
        "privacy",
        "model_used",
        "training_used",
        "network_used",
        "document_sha256",
    }
    if set(document) != expected or document["status"] != (
        "complete_explicit_owner_pairwise_label"
    ):
        raise ValueError("remix source-delta label fields or status changed")
    if document["method_natures"] != ["D", "H"]:
        raise ValueError("remix source-delta label method nature changed")


def _validate_decision(document: Mapping[str, Any]) -> None:
    if document["listening"] != {
        "heard_control": True,
        "heard_left": True,
        "heard_right": True,
        "playback_implies_label": False,
    }:
        raise ValueError("pairwise label requires heard control, A and B")
    identities = document["identity_relationships"]
    if not isinstance(identities, Mapping) or set(identities) != {"left", "right"}:
        raise ValueError("pairwise identity relationship fields changed")
    _validate_values(
        document["outcome"],
        identities["left"],
        identities["right"],
        document["reason_codes"],
        stored=True,
    )
    if document["training"] != {
        "explicitly_admitted": True,
        "admission_scope": "owner_local_training",
        "training_eligible": False,
    }:
        raise ValueError("pairwise training admission or eligibility changed")
    if document["authority"] != {
        "automatic_preference": False,
        "selected_for_product": False,
        "training_execution_authorized": False,
        "checkpoint_promotion_authorized": False,
    }:
        raise ValueError("pairwise label authority changed")
    if document["effects"] != {
        "training_label_created": True,
        "training_started": False,
        "model_weights_changed": False,
        "product_selection_changed": False,
        "audio_mutated": False,
    }:
        raise ValueError("pairwise label effects changed")
    if document["privacy"] != {
        "owner_local_only": True,
        "paths_embedded": False,
        "audio_embedded": False,
        "cloud_training_approved": False,
    }:
        raise ValueError("pairwise label privacy boundary changed")
    if any(
        document[key] is not False
        for key in ("model_used", "training_used", "network_used")
    ):
        raise ValueError("pairwise label claims model, training or network use")


def _validate_values(
    outcome: Any,
    left_identity: Any,
    right_identity: Any,
    reason_codes: Any,
    *,
    stored: bool = False,
) -> None:
    allowed_outcomes = {"left", "right", "equivalent", "neither", "cannot_tell"}
    if outcome not in (allowed_outcomes if stored else _OUTCOMES):
        raise ValueError("pairwise outcome is invalid")
    if left_identity not in _IDENTITY_RELATIONSHIPS or right_identity not in (
        _IDENTITY_RELATIONSHIPS
    ):
        raise ValueError("pairwise identity relationship is invalid")
    if (
        not isinstance(reason_codes, (list, tuple))
        or not 1 <= len(reason_codes) <= 4
        or len(reason_codes) != len(set(reason_codes))
        or any(reason not in _REASON_CODES for reason in reason_codes)
    ):
        raise ValueError("pairwise label requires one to four supported reasons")


__all__ = [
    "REMIX_SOURCE_DELTA_PAIRWISE_LABEL_SCHEMA",
    "RemixSourceDeltaReviewDecision",
    "admit_remix_source_delta_pairwise_label",
    "validate_remix_source_delta_pairwise_label",
]
