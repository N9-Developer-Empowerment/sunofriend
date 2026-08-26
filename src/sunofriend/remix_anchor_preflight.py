"""Explicit owner-anchor admission before controlled remix rendering.

This module is deliberately model- and audio-I/O-free.  It turns one exact
source/estimate relationship plus an explicit owner statement into the
identity and registry documents required by the deterministic remix lane.
Creating a preflight is not confirmation; confirmation is a separate call.
Neither operation renders audio, creates a preference label or starts training.
"""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath
import re
from typing import Any, Mapping

from .musical_state import MUSICAL_STATE_SCHEMA, validate_musical_state
from .remix_identity import (
    REMIX_IDENTITY_STATE_SCHEMA,
    create_remix_identity_state,
    validate_remix_identity_state,
)
from .remix_learning_contract import (
    REMIX_OWNER_REGISTRY_SCHEMA,
    create_remix_owner_registry,
    validate_remix_owner_registry,
)
from .source_receipt import document_sha256


REMIX_ANCHOR_PREFLIGHT_SCHEMA = "sunofriend.remix-anchor-preflight.v0"
REMIX_ANCHOR_CONFIRMATION_SCHEMA = "sunofriend.remix-anchor-confirmation.v0"

REMIX_ANCHOR_KINDS = (
    "motif",
    "bass_movement",
    "harmonic_event",
    "groove",
    "structural_relationship",
)
REMIX_ANCHOR_PRESERVATION_REQUIREMENTS = ("must_remain_recognisable",)

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def create_remix_anchor_preflight_state(
    musical_state: Mapping[str, Any],
    *,
    source_control: Mapping[str, Any],
    separation_estimate: Mapping[str, Any],
    owner_label: str,
    anchor_kind: str,
    start_frame: int,
    end_frame: int,
    preservation_requirement: str,
    heard_source: bool,
    heard_estimate: bool,
) -> dict[str, Any]:
    """Create a pending, path-free owner-anchor statement."""

    state = validate_musical_state(musical_state)
    control = _audio_record(source_control, "source control")
    estimate = _estimate_record(separation_estimate)
    if estimate["geometry"] != control["geometry"]:
        raise ValueError("source control and separation estimate geometry differ")
    label = _owner_text(owner_label, "owner label", maximum=240)
    kind = _choice(anchor_kind, REMIX_ANCHOR_KINDS, "anchor kind")
    requirement = _choice(
        preservation_requirement,
        REMIX_ANCHOR_PRESERVATION_REQUIREMENTS,
        "preservation requirement",
    )
    geometry = _anchor_geometry(
        estimate["geometry"], start_frame=start_frame, end_frame=end_frame
    )
    if heard_source is not True or heard_estimate is not True:
        raise ValueError("explicitly hear both original context and estimate")

    document: dict[str, Any] = {
        "schema": REMIX_ANCHOR_PREFLIGHT_SCHEMA,
        "status": "pending_explicit_owner_confirmation",
        "binding": {
            "musical_state_schema": MUSICAL_STATE_SCHEMA,
            "musical_state_sha256": state["document_sha256"],
        },
        "source_control": control,
        "separation_estimate": estimate,
        "proposed_anchor": {
            "anchor_kind": kind,
            "owner_label": label,
            "preservation_requirement": requirement,
            "geometry": geometry,
        },
        "explicitly_heard": {"source_control": True, "separation_estimate": True},
        "method_natures": ["D", "H"],
        "authority": {
            "owner_confirmation_recorded": False,
            "remix_render_authorized": False,
            "pairwise_label_created": False,
            "training_execution_authorized": False,
            "product_selection_authorized": False,
        },
        "effects": _false_effects(),
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_anchor_preflight_state(document, state)


def validate_remix_anchor_preflight_state(
    preflight: Mapping[str, Any], musical_state: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate a pending anchor statement against the exact Musical State."""

    state = validate_musical_state(musical_state)
    document = _verified_document(
        preflight, REMIX_ANCHOR_PREFLIGHT_SCHEMA, "anchor preflight"
    )
    expected_keys = {
        "schema",
        "status",
        "binding",
        "source_control",
        "separation_estimate",
        "proposed_anchor",
        "explicitly_heard",
        "method_natures",
        "authority",
        "effects",
        "document_sha256",
    }
    if set(document) != expected_keys:
        raise ValueError("anchor preflight fields changed")
    if document["status"] != "pending_explicit_owner_confirmation":
        raise ValueError("anchor preflight status changed")
    if document["binding"] != {
        "musical_state_schema": MUSICAL_STATE_SCHEMA,
        "musical_state_sha256": state["document_sha256"],
    }:
        raise ValueError("anchor preflight Musical State binding changed")
    control = _audio_record(document["source_control"], "source control")
    estimate = _estimate_record(document["separation_estimate"])
    if control["geometry"] != estimate["geometry"]:
        raise ValueError("source control and separation estimate geometry differ")
    anchor = dict(_mapping(document["proposed_anchor"], "proposed anchor"))
    if set(anchor) != {
        "anchor_kind",
        "owner_label",
        "preservation_requirement",
        "geometry",
    }:
        raise ValueError("proposed anchor fields changed")
    _choice(anchor["anchor_kind"], REMIX_ANCHOR_KINDS, "anchor kind")
    _owner_text(anchor["owner_label"], "owner label", maximum=240)
    _choice(
        anchor["preservation_requirement"],
        REMIX_ANCHOR_PRESERVATION_REQUIREMENTS,
        "preservation requirement",
    )
    checked_geometry = _anchor_geometry(
        estimate["geometry"],
        start_frame=anchor["geometry"].get("start_frame")
        if isinstance(anchor.get("geometry"), Mapping)
        else None,
        end_frame=anchor["geometry"].get("end_frame")
        if isinstance(anchor.get("geometry"), Mapping)
        else None,
    )
    if anchor["geometry"] != checked_geometry:
        raise ValueError("anchor preflight geometry changed")
    if document["explicitly_heard"] != {
        "source_control": True,
        "separation_estimate": True,
    }:
        raise ValueError("anchor preflight requires explicit listening")
    if document["method_natures"] != ["D", "H"]:
        raise ValueError("anchor preflight method nature changed")
    if document["authority"] != {
        "owner_confirmation_recorded": False,
        "remix_render_authorized": False,
        "pairwise_label_created": False,
        "training_execution_authorized": False,
        "product_selection_authorized": False,
    }:
        raise ValueError("pending anchor preflight cannot claim authority")
    if document["effects"] != _false_effects():
        raise ValueError("anchor preflight cannot claim downstream effects")
    _reject_paths(document)
    return document


def confirm_remix_anchor_preflight(
    preflight: Mapping[str, Any],
    musical_state: Mapping[str, Any],
    *,
    identity_state_id: str,
    registry_id: str,
    composition_id: str,
    group_id: str,
) -> dict[str, Any]:
    """Confirm one anchor and return exact identity, registry and receipt docs."""

    state = validate_musical_state(musical_state)
    pending = validate_remix_anchor_preflight_state(preflight, state)
    identity_id = _safe_id(identity_state_id, "identity_state_id")
    registry_name = _safe_id(registry_id, "registry_id")
    composition = _safe_id(composition_id, "composition_id")
    group = _safe_id(group_id, "group_id")
    estimate = pending["separation_estimate"]
    proposed = pending["proposed_anchor"]
    anchor_id = f"{identity_id}.anchor"
    if len(anchor_id) > 96:
        raise ValueError("identity_state_id is too long for its anchor identity")
    identity = create_remix_identity_state(
        state,
        separation_estimates=[estimate],
        owner_anchors=[
            {
                "anchor_id": anchor_id,
                "anchor_kind": proposed["anchor_kind"],
                "owner_label": proposed["owner_label"],
                "label_authority": "explicit_owner_label",
                "source_estimate_id": estimate["source_estimate_id"],
                "geometry": proposed["geometry"],
            }
        ],
    )
    registry = create_remix_owner_registry(
        registry_id=registry_name,
        entries=[
            {
                "composition_id": composition,
                "group_id": group,
                "musical_state": state,
                "identity_state": identity,
                "source_control": pending["source_control"],
                "rights_scope": "owner_local_training",
                "cloud_training_approved": False,
            }
        ],
    )
    receipt: dict[str, Any] = {
        "schema": REMIX_ANCHOR_CONFIRMATION_SCHEMA,
        "status": "complete_explicit_owner_anchor_no_remix",
        "binding": {
            "preflight_schema": REMIX_ANCHOR_PREFLIGHT_SCHEMA,
            "preflight_sha256": pending["document_sha256"],
            "musical_state_sha256": state["document_sha256"],
            "identity_state_schema": REMIX_IDENTITY_STATE_SCHEMA,
            "identity_state_sha256": identity["document_sha256"],
            "owner_registry_schema": REMIX_OWNER_REGISTRY_SCHEMA,
            "owner_registry_sha256": registry["document_sha256"],
        },
        "owner_confirmation": {
            "identity_state_id": identity_id,
            "registry_id": registry_name,
            "composition_id": composition,
            "group_id": group,
            "anchor_id": anchor_id,
            "preservation_requirement": proposed["preservation_requirement"],
            "explicit_confirmation": True,
        },
        "authority": {
            "owner_anchor_confirmed": True,
            "remix_render_authorized": False,
            "pairwise_label_created": False,
            "training_execution_authorized": False,
            "checkpoint_promotion_authorized": False,
            "product_selection_authorized": False,
        },
        "effects": _false_effects(),
    }
    receipt["document_sha256"] = document_sha256(receipt)
    checked_receipt = validate_remix_anchor_confirmation(
        receipt,
        pending,
        state,
        identity,
        registry,
    )
    return {
        "identity_state": identity,
        "owner_registry": registry,
        "confirmation": checked_receipt,
    }


def validate_remix_anchor_confirmation(
    confirmation: Mapping[str, Any],
    preflight: Mapping[str, Any],
    musical_state: Mapping[str, Any],
    identity_state: Mapping[str, Any],
    owner_registry: Mapping[str, Any],
) -> dict[str, Any]:
    """Revalidate an anchor confirmation against every embedded identity."""

    state = validate_musical_state(musical_state)
    pending = validate_remix_anchor_preflight_state(preflight, state)
    identity = validate_remix_identity_state(identity_state, state)
    registry = validate_remix_owner_registry(
        owner_registry, musical_states=[state], identity_states=[identity]
    )
    document = _verified_document(
        confirmation, REMIX_ANCHOR_CONFIRMATION_SCHEMA, "anchor confirmation"
    )
    if set(document) != {
        "schema",
        "status",
        "binding",
        "owner_confirmation",
        "authority",
        "effects",
        "document_sha256",
    }:
        raise ValueError("anchor confirmation fields changed")
    if document["status"] != "complete_explicit_owner_anchor_no_remix":
        raise ValueError("anchor confirmation status changed")
    expected_binding = {
        "preflight_schema": REMIX_ANCHOR_PREFLIGHT_SCHEMA,
        "preflight_sha256": pending["document_sha256"],
        "musical_state_sha256": state["document_sha256"],
        "identity_state_schema": REMIX_IDENTITY_STATE_SCHEMA,
        "identity_state_sha256": identity["document_sha256"],
        "owner_registry_schema": REMIX_OWNER_REGISTRY_SCHEMA,
        "owner_registry_sha256": registry["document_sha256"],
    }
    if document["binding"] != expected_binding:
        raise ValueError("anchor confirmation evidence binding changed")
    owner = dict(_mapping(document["owner_confirmation"], "owner confirmation"))
    if set(owner) != {
        "identity_state_id",
        "registry_id",
        "composition_id",
        "group_id",
        "anchor_id",
        "preservation_requirement",
        "explicit_confirmation",
    }:
        raise ValueError("owner confirmation fields changed")
    for key in ("identity_state_id", "registry_id", "composition_id", "group_id"):
        _safe_id(owner[key], key)
    if owner["anchor_id"] != f"{owner['identity_state_id']}.anchor":
        raise ValueError("confirmed anchor identity changed")
    if identity["owner_anchors"] != [
        {
            "anchor_id": owner["anchor_id"],
            "anchor_kind": pending["proposed_anchor"]["anchor_kind"],
            "owner_label": pending["proposed_anchor"]["owner_label"],
            "label_authority": "explicit_owner_label",
            "source_estimate_id": pending["separation_estimate"]["source_estimate_id"],
            "geometry": pending["proposed_anchor"]["geometry"],
        }
    ]:
        raise ValueError("confirmed owner anchor projection changed")
    if owner["registry_id"] != registry["registry_id"]:
        raise ValueError("confirmed owner registry identity changed")
    entry = registry["entries"][0]
    if (
        owner["composition_id"] != entry["composition_id"]
        or owner["group_id"] != entry["group_id"]
        or owner["preservation_requirement"]
        != pending["proposed_anchor"]["preservation_requirement"]
        or owner["explicit_confirmation"] is not True
    ):
        raise ValueError("explicit owner confirmation changed")
    if document["authority"] != {
        "owner_anchor_confirmed": True,
        "remix_render_authorized": False,
        "pairwise_label_created": False,
        "training_execution_authorized": False,
        "checkpoint_promotion_authorized": False,
        "product_selection_authorized": False,
    }:
        raise ValueError("anchor confirmation cannot claim downstream authority")
    if document["effects"] != _false_effects():
        raise ValueError("anchor confirmation cannot claim downstream effects")
    _reject_paths(document)
    return document


def _estimate_record(value: Any) -> dict[str, Any]:
    row = dict(_mapping(value, "separation estimate"))
    raw_keys = {
        "source_estimate_id",
        "estimated_role",
        "audio_sha256",
        "audio_bytes",
        "geometry",
    }
    canonical_keys = raw_keys | {"source_kind", "role_interpretation"}
    if set(row) not in (raw_keys, canonical_keys):
        raise ValueError("separation estimate fields changed")
    if set(row) == canonical_keys and (
        row["source_kind"] != "separation_estimate"
        or row["role_interpretation"] != "estimate_not_ground_truth"
    ):
        raise ValueError("source must remain a separation estimate")
    source_id = _safe_id(row["source_estimate_id"], "source_estimate_id")
    role = _owner_text(row["estimated_role"], "estimated role", maximum=80)
    audio = _audio_record(
        {key: row[key] for key in raw_keys},
        "separation estimate",
        extra_keys={"source_estimate_id", "estimated_role"},
    )
    return {
        "source_estimate_id": source_id,
        "source_kind": "separation_estimate",
        "estimated_role": role,
        "role_interpretation": "estimate_not_ground_truth",
        **audio,
    }


def _audio_record(
    value: Any, label: str, *, extra_keys: set[str] | None = None
) -> dict[str, Any]:
    row = dict(_mapping(value, label))
    expected = {"audio_sha256", "audio_bytes", "geometry"} | (extra_keys or set())
    if set(row) != expected:
        raise ValueError(f"{label} fields changed")
    if not _SHA256.fullmatch(str(row.get("audio_sha256", ""))):
        raise ValueError(f"{label} SHA-256 is invalid")
    if (
        isinstance(row.get("audio_bytes"), bool)
        or not isinstance(row.get("audio_bytes"), int)
        or row["audio_bytes"] <= 0
    ):
        raise ValueError(f"{label} byte count is invalid")
    geometry = dict(_mapping(row.get("geometry"), f"{label} geometry"))
    if set(geometry) != {"sample_rate_hz", "channels", "frames"} or any(
        isinstance(geometry.get(key), bool)
        or not isinstance(geometry.get(key), int)
        or geometry[key] <= 0
        for key in geometry
    ):
        raise ValueError(f"{label} geometry is invalid")
    return {
        "audio_sha256": str(row["audio_sha256"]),
        "audio_bytes": row["audio_bytes"],
        "geometry": geometry,
    }


def _anchor_geometry(
    estimate_geometry: Mapping[str, Any], *, start_frame: Any, end_frame: Any
) -> dict[str, int]:
    if (
        isinstance(start_frame, bool)
        or not isinstance(start_frame, int)
        or isinstance(end_frame, bool)
        or not isinstance(end_frame, int)
        or start_frame < 0
        or end_frame <= start_frame
        or end_frame > estimate_geometry["frames"]
    ):
        raise ValueError("anchor frame window is outside the estimate")
    return {
        "sample_rate_hz": estimate_geometry["sample_rate_hz"],
        "start_frame": start_frame,
        "end_frame": end_frame,
    }


def _owner_text(value: Any, label: str, *, maximum: int) -> str:
    text = str(value).strip()
    if not text or len(text) > maximum or "\n" in text or "\r" in text:
        raise ValueError(f"{label} must be one bounded line")
    if _looks_like_path(text):
        raise ValueError(f"{label} must not contain a path")
    return text


def _safe_id(value: Any, label: str) -> str:
    text = str(value)
    if not _SAFE_ID.fullmatch(text):
        raise ValueError(f"{label} is not a safe identifier")
    return text


def _choice(value: Any, allowed: tuple[str, ...], label: str) -> str:
    text = str(value)
    if text not in allowed:
        raise ValueError(f"{label} is unsupported")
    return text


def _verified_document(
    value: Mapping[str, Any], schema: str, label: str
) -> dict[str, Any]:
    document = dict(_mapping(value, label))
    if document.get("schema") != schema:
        raise ValueError(f"{label} schema changed")
    expected = str(document.get("document_sha256", ""))
    if not _SHA256.fullmatch(expected):
        raise ValueError(f"{label} document SHA-256 is invalid")
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if document_sha256(unsigned) != expected:
        raise ValueError(f"{label} document SHA-256 changed")
    return document


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _false_effects() -> dict[str, bool]:
    return {
        "source_mutated": False,
        "estimate_mutated": False,
        "remix_rendered": False,
        "pairwise_label_created": False,
        "training_started": False,
        "model_weights_changed": False,
        "product_selection_changed": False,
    }


def _looks_like_path(text: str) -> bool:
    if text.startswith(("/", "~", "file:")) or "\\" in text:
        return True
    if re.match(r"^[A-Za-z]:", text):
        return True
    return PurePosixPath(text).is_absolute() or PureWindowsPath(text).is_absolute()


def _reject_paths(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if any(
                word in str(key).lower()
                for word in ("path", "filename", "directory", "url")
            ):
                raise ValueError("anchor evidence must not contain path fields")
            _reject_paths(item)
    elif isinstance(value, list):
        for item in value:
            _reject_paths(item)
    elif isinstance(value, str) and _looks_like_path(value):
        raise ValueError("anchor evidence must not contain paths")


__all__ = [
    "REMIX_ANCHOR_CONFIRMATION_SCHEMA",
    "REMIX_ANCHOR_KINDS",
    "REMIX_ANCHOR_PREFLIGHT_SCHEMA",
    "REMIX_ANCHOR_PRESERVATION_REQUIREMENTS",
    "confirm_remix_anchor_preflight",
    "create_remix_anchor_preflight_state",
    "validate_remix_anchor_confirmation",
    "validate_remix_anchor_preflight_state",
]
