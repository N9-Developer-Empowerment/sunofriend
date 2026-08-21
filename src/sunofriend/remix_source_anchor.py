"""Versioned owner-anchor evidence for a dedicated remix source state."""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath
import re
from typing import Any, Mapping, Sequence

from .remix_anchor_preflight import (
    REMIX_ANCHOR_KINDS,
    REMIX_ANCHOR_PRESERVATION_REQUIREMENTS,
)
from .remix_source_state import (
    REMIX_SOURCE_STATE_SCHEMA,
    validate_remix_source_state,
)
from .source_receipt import document_sha256


REMIX_SOURCE_IDENTITY_SCHEMA = "sunofriend.remix-identity-state.v1"
REMIX_SOURCE_OWNER_REGISTRY_SCHEMA = "sunofriend.remix-owner-anchor-registry.v1"
REMIX_SOURCE_ANCHOR_PREFLIGHT_SCHEMA = "sunofriend.remix-anchor-preflight.v1"
REMIX_SOURCE_ANCHOR_CONFIRMATION_SCHEMA = "sunofriend.remix-anchor-confirmation.v1"

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def create_remix_source_anchor_preflight(
    source_state: Mapping[str, Any],
    *,
    separation_estimate: Mapping[str, Any],
    owner_label: str,
    anchor_kind: str,
    start_frame: int,
    end_frame: int,
    preservation_requirement: str,
    heard_source: bool,
    heard_estimate: bool,
) -> dict[str, Any]:
    """Create a pending anchor statement over a real remix source state."""

    state = validate_remix_source_state(source_state)
    control = state["source_control"]
    estimate = _estimate_record(separation_estimate)
    if estimate["geometry"] != control["geometry"]:
        raise ValueError("source control and separation estimate geometry differ")
    if heard_source is not True or heard_estimate is not True:
        raise ValueError("explicitly hear both original context and estimate")
    anchor = {
        "anchor_kind": _choice(anchor_kind, REMIX_ANCHOR_KINDS, "anchor kind"),
        "owner_label": _owner_text(owner_label, "owner label", 240),
        "preservation_requirement": _choice(
            preservation_requirement,
            REMIX_ANCHOR_PRESERVATION_REQUIREMENTS,
            "preservation requirement",
        ),
        "geometry": _anchor_geometry(
            estimate["geometry"], start_frame=start_frame, end_frame=end_frame
        ),
    }
    document: dict[str, Any] = {
        "schema": REMIX_SOURCE_ANCHOR_PREFLIGHT_SCHEMA,
        "status": "pending_explicit_owner_confirmation",
        "binding": {
            "source_state_schema": REMIX_SOURCE_STATE_SCHEMA,
            "source_state_sha256": state["document_sha256"],
        },
        "source_control": control,
        "separation_estimate": estimate,
        "proposed_anchor": anchor,
        "explicitly_heard": {"source_control": True, "separation_estimate": True},
        "method_natures": ["D", "H"],
        "authority": _pending_authority(),
        "effects": _false_effects(),
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_source_anchor_preflight(document, state)


def validate_remix_source_anchor_preflight(
    preflight: Mapping[str, Any], source_state: Mapping[str, Any]
) -> dict[str, Any]:
    state = validate_remix_source_state(source_state)
    document = _verified(preflight, REMIX_SOURCE_ANCHOR_PREFLIGHT_SCHEMA, "preflight")
    if set(document) != {
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
    }:
        raise ValueError("remix source anchor preflight fields changed")
    if document["status"] != "pending_explicit_owner_confirmation":
        raise ValueError("remix source anchor preflight status changed")
    if document["binding"] != {
        "source_state_schema": REMIX_SOURCE_STATE_SCHEMA,
        "source_state_sha256": state["document_sha256"],
    }:
        raise ValueError("remix source anchor preflight binding changed")
    control = _audio_record(document["source_control"], "source control")
    estimate = _estimate_record(document["separation_estimate"])
    if (
        control != state["source_control"]
        or estimate["geometry"] != control["geometry"]
    ):
        raise ValueError("remix source anchor audio identity changed")
    proposed = document["proposed_anchor"]
    if not isinstance(proposed, Mapping) or set(proposed) != {
        "anchor_kind",
        "owner_label",
        "preservation_requirement",
        "geometry",
    }:
        raise ValueError("remix source proposed anchor fields changed")
    _choice(proposed["anchor_kind"], REMIX_ANCHOR_KINDS, "anchor kind")
    _owner_text(proposed["owner_label"], "owner label", 240)
    _choice(
        proposed["preservation_requirement"],
        REMIX_ANCHOR_PRESERVATION_REQUIREMENTS,
        "preservation requirement",
    )
    geometry = proposed["geometry"]
    if not isinstance(geometry, Mapping):
        raise ValueError("anchor geometry must be an object")
    checked = _anchor_geometry(
        estimate["geometry"],
        start_frame=geometry.get("start_frame"),
        end_frame=geometry.get("end_frame"),
    )
    if geometry != checked:
        raise ValueError("remix source anchor geometry changed")
    if document["explicitly_heard"] != {
        "source_control": True,
        "separation_estimate": True,
    }:
        raise ValueError("remix source anchor requires explicit listening")
    if document["method_natures"] != ["D", "H"]:
        raise ValueError("remix source anchor method nature changed")
    if document["authority"] != _pending_authority():
        raise ValueError("pending remix source anchor cannot claim authority")
    if document["effects"] != _false_effects():
        raise ValueError("pending remix source anchor cannot claim effects")
    _reject_paths(document)
    return document


def confirm_remix_source_anchor_preflight(
    preflight: Mapping[str, Any],
    source_state: Mapping[str, Any],
    *,
    identity_state_id: str,
    registry_id: str,
) -> dict[str, Any]:
    """Create v1 identity, registry and confirmation documents."""

    state = validate_remix_source_state(source_state)
    pending = validate_remix_source_anchor_preflight(preflight, state)
    identity_id = _safe_id(identity_state_id, "identity_state_id")
    registry_name = _safe_id(registry_id, "registry_id")
    anchor_id = f"{identity_id}.anchor"
    if len(anchor_id) > 96:
        raise ValueError("identity_state_id is too long for its anchor identity")
    proposed = pending["proposed_anchor"]
    estimate = pending["separation_estimate"]
    identity = create_remix_source_identity_state(
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
    registry = create_remix_source_owner_registry(
        state, identity, registry_id=registry_name
    )
    receipt: dict[str, Any] = {
        "schema": REMIX_SOURCE_ANCHOR_CONFIRMATION_SCHEMA,
        "status": "complete_explicit_owner_anchor_no_remix",
        "binding": {
            "preflight_sha256": pending["document_sha256"],
            "source_state_sha256": state["document_sha256"],
            "identity_state_sha256": identity["document_sha256"],
            "owner_registry_sha256": registry["document_sha256"],
        },
        "owner_confirmation": {
            "identity_state_id": identity_id,
            "registry_id": registry_name,
            "composition_id": state["composition_id"],
            "group_id": state["group_id"],
            "anchor_id": anchor_id,
            "preservation_requirement": proposed["preservation_requirement"],
            "explicit_confirmation": True,
        },
        "authority": _confirmed_authority(),
        "effects": _false_effects(),
    }
    receipt["document_sha256"] = document_sha256(receipt)
    checked = validate_remix_source_anchor_confirmation(
        receipt, pending, state, identity, registry
    )
    return {
        "identity_state": identity,
        "owner_registry": registry,
        "confirmation": checked,
    }


def create_remix_source_identity_state(
    source_state: Mapping[str, Any],
    *,
    separation_estimates: Sequence[Mapping[str, Any]],
    owner_anchors: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    state = validate_remix_source_state(source_state)
    estimates = [_estimate_record(row) for row in separation_estimates]
    if not estimates:
        raise ValueError("remix source identity requires an estimate")
    _unique(estimates, "source_estimate_id", "separation estimate")
    anchors = [_anchor_record(row, estimates) for row in owner_anchors]
    if not anchors:
        raise ValueError("remix source identity requires an owner anchor")
    _unique(anchors, "anchor_id", "owner anchor")
    document: dict[str, Any] = {
        "schema": REMIX_SOURCE_IDENTITY_SCHEMA,
        "status": "complete_owner_anchored_no_remix",
        "binding": {
            "source_state_schema": REMIX_SOURCE_STATE_SCHEMA,
            "source_state_sha256": state["document_sha256"],
        },
        "method_natures": ["D", "H"],
        "separation_estimates": estimates,
        "owner_anchors": anchors,
        "model_used": False,
        "training_used": False,
        "network_used": False,
        "effects": _identity_effects(),
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_source_identity_state(document, state)


def validate_remix_source_identity_state(
    identity: Mapping[str, Any], source_state: Mapping[str, Any]
) -> dict[str, Any]:
    state = validate_remix_source_state(source_state)
    document = _verified(identity, REMIX_SOURCE_IDENTITY_SCHEMA, "identity")
    if set(document) != {
        "schema",
        "status",
        "binding",
        "method_natures",
        "separation_estimates",
        "owner_anchors",
        "model_used",
        "training_used",
        "network_used",
        "effects",
        "document_sha256",
    }:
        raise ValueError("remix source identity fields changed")
    if document["status"] != "complete_owner_anchored_no_remix" or document[
        "binding"
    ] != {
        "source_state_schema": REMIX_SOURCE_STATE_SCHEMA,
        "source_state_sha256": state["document_sha256"],
    }:
        raise ValueError("remix source identity binding or status changed")
    estimates = [_estimate_record(row) for row in document["separation_estimates"]]
    _unique(estimates, "source_estimate_id", "separation estimate")
    anchors = [_anchor_record(row, estimates) for row in document["owner_anchors"]]
    _unique(anchors, "anchor_id", "owner anchor")
    if (
        estimates != document["separation_estimates"]
        or anchors != document["owner_anchors"]
    ):
        raise ValueError("remix source identity evidence changed")
    if document["method_natures"] != ["D", "H"] or any(
        document[key] is not False
        for key in ("model_used", "training_used", "network_used")
    ):
        raise ValueError("remix source identity authority changed")
    if document["effects"] != _identity_effects():
        raise ValueError("remix source identity cannot claim effects")
    _reject_paths(document)
    return document


def create_remix_source_owner_registry(
    source_state: Mapping[str, Any],
    identity_state: Mapping[str, Any],
    *,
    registry_id: str,
) -> dict[str, Any]:
    state = validate_remix_source_state(source_state)
    identity = validate_remix_source_identity_state(identity_state, state)
    registry_name = _safe_id(registry_id, "registry_id")
    relationship = {
        "composition_id": state["composition_id"],
        "group_id": state["group_id"],
        "source_state_sha256": state["document_sha256"],
        "identity_state_sha256": identity["document_sha256"],
        "source_control_audio_sha256": state["source_control"]["audio_sha256"],
    }
    document: dict[str, Any] = {
        "schema": REMIX_SOURCE_OWNER_REGISTRY_SCHEMA,
        "status": "complete_owner_confirmed_registry",
        "registry_id": registry_name,
        "binding": {
            "source_state_schema": REMIX_SOURCE_STATE_SCHEMA,
            "source_state_sha256": state["document_sha256"],
            "identity_state_schema": REMIX_SOURCE_IDENTITY_SCHEMA,
            "identity_state_sha256": identity["document_sha256"],
        },
        "method_natures": ["D", "H"],
        "entries": [
            {
                **relationship,
                "relationship_sha256": document_sha256(relationship),
                "source_control_audio_bytes": state["source_control"]["audio_bytes"],
                "source_control_geometry": state["source_control"]["geometry"],
                "anchor_ids": sorted(
                    row["anchor_id"] for row in identity["owner_anchors"]
                ),
                "rights_scope": "owner_local_training",
                "cloud_training_approved": False,
            }
        ],
        "authority": {
            "owner_confirmed_relationships": True,
            "automatic_relationship_inference": False,
            "training_execution_authorized": False,
            "product_selection_authorized": False,
        },
        "privacy": {
            "local_training_approved": True,
            "cloud_training_approved": False,
            "paths_embedded": False,
        },
        "effects": {
            "sources_mutated": False,
            "remix_rendered": False,
            "training_started": False,
            "model_weights_changed": False,
        },
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_source_owner_registry(document, state, identity)


def validate_remix_source_owner_registry(
    registry: Mapping[str, Any],
    source_state: Mapping[str, Any],
    identity_state: Mapping[str, Any],
) -> dict[str, Any]:
    state = validate_remix_source_state(source_state)
    identity = validate_remix_source_identity_state(identity_state, state)
    document = _verified(registry, REMIX_SOURCE_OWNER_REGISTRY_SCHEMA, "registry")
    if set(document) != {
        "schema",
        "status",
        "registry_id",
        "binding",
        "method_natures",
        "entries",
        "authority",
        "privacy",
        "effects",
        "document_sha256",
    }:
        raise ValueError("remix source owner registry fields changed")
    registry_id = _safe_id(document["registry_id"], "registry_id")
    if document["binding"] != {
        "source_state_schema": REMIX_SOURCE_STATE_SCHEMA,
        "source_state_sha256": state["document_sha256"],
        "identity_state_schema": REMIX_SOURCE_IDENTITY_SCHEMA,
        "identity_state_sha256": identity["document_sha256"],
    }:
        raise ValueError("remix source owner registry binding changed")
    relationship = {
        "composition_id": state["composition_id"],
        "group_id": state["group_id"],
        "source_state_sha256": state["document_sha256"],
        "identity_state_sha256": identity["document_sha256"],
        "source_control_audio_sha256": state["source_control"]["audio_sha256"],
    }
    expected_entry = {
        **relationship,
        "relationship_sha256": document_sha256(relationship),
        "source_control_audio_bytes": state["source_control"]["audio_bytes"],
        "source_control_geometry": state["source_control"]["geometry"],
        "anchor_ids": sorted(row["anchor_id"] for row in identity["owner_anchors"]),
        "rights_scope": "owner_local_training",
        "cloud_training_approved": False,
    }
    if (
        document["status"] != "complete_owner_confirmed_registry"
        or document["registry_id"] != registry_id
        or document["method_natures"] != ["D", "H"]
        or document["entries"] != [expected_entry]
    ):
        raise ValueError("remix source owner registry evidence changed")
    if (
        document["authority"]
        != {
            "owner_confirmed_relationships": True,
            "automatic_relationship_inference": False,
            "training_execution_authorized": False,
            "product_selection_authorized": False,
        }
        or document["privacy"]
        != {
            "local_training_approved": True,
            "cloud_training_approved": False,
            "paths_embedded": False,
        }
        or document["effects"]
        != {
            "sources_mutated": False,
            "remix_rendered": False,
            "training_started": False,
            "model_weights_changed": False,
        }
    ):
        raise ValueError("remix source owner registry authority changed")
    _reject_paths(document)
    return document


def validate_remix_source_anchor_confirmation(
    confirmation: Mapping[str, Any],
    preflight: Mapping[str, Any],
    source_state: Mapping[str, Any],
    identity_state: Mapping[str, Any],
    owner_registry: Mapping[str, Any],
) -> dict[str, Any]:
    state = validate_remix_source_state(source_state)
    pending = validate_remix_source_anchor_preflight(preflight, state)
    identity = validate_remix_source_identity_state(identity_state, state)
    registry = validate_remix_source_owner_registry(owner_registry, state, identity)
    document = _verified(
        confirmation, REMIX_SOURCE_ANCHOR_CONFIRMATION_SCHEMA, "confirmation"
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
        raise ValueError("remix source anchor confirmation fields changed")
    if document["status"] != "complete_explicit_owner_anchor_no_remix" or document[
        "binding"
    ] != {
        "preflight_sha256": pending["document_sha256"],
        "source_state_sha256": state["document_sha256"],
        "identity_state_sha256": identity["document_sha256"],
        "owner_registry_sha256": registry["document_sha256"],
    }:
        raise ValueError("remix source anchor confirmation binding changed")
    owner = document["owner_confirmation"]
    if not isinstance(owner, Mapping) or set(owner) != {
        "identity_state_id",
        "registry_id",
        "composition_id",
        "group_id",
        "anchor_id",
        "preservation_requirement",
        "explicit_confirmation",
    }:
        raise ValueError("remix source owner confirmation fields changed")
    if owner != {
        "identity_state_id": owner["identity_state_id"],
        "registry_id": registry["registry_id"],
        "composition_id": state["composition_id"],
        "group_id": state["group_id"],
        "anchor_id": f"{owner['identity_state_id']}.anchor",
        "preservation_requirement": pending["proposed_anchor"][
            "preservation_requirement"
        ],
        "explicit_confirmation": True,
    }:
        raise ValueError("remix source explicit owner confirmation changed")
    _safe_id(owner["identity_state_id"], "identity_state_id")
    if identity["owner_anchors"][0]["anchor_id"] != owner["anchor_id"]:
        raise ValueError("remix source confirmed anchor projection changed")
    if document["authority"] != _confirmed_authority():
        raise ValueError("remix source confirmation cannot claim downstream authority")
    if document["effects"] != _false_effects():
        raise ValueError("remix source confirmation cannot claim effects")
    _reject_paths(document)
    return document


def _estimate_record(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("separation estimate must be an object")
    raw = dict(value)
    expected = {
        "source_estimate_id",
        "estimated_role",
        "audio_sha256",
        "audio_bytes",
        "geometry",
    }
    canonical = expected | {"source_kind", "role_interpretation"}
    if set(raw) not in (expected, canonical):
        raise ValueError("separation estimate fields changed")
    if set(raw) == canonical and (
        raw["source_kind"] != "separation_estimate"
        or raw["role_interpretation"] != "estimate_not_ground_truth"
    ):
        raise ValueError("source must remain a separation estimate")
    return {
        "source_estimate_id": _safe_id(raw["source_estimate_id"], "source_estimate_id"),
        "source_kind": "separation_estimate",
        "estimated_role": _owner_text(raw["estimated_role"], "estimated role", 80),
        "role_interpretation": "estimate_not_ground_truth",
        **_audio_record(
            {key: raw[key] for key in ("audio_sha256", "audio_bytes", "geometry")},
            "separation estimate",
        ),
    }


def _anchor_record(
    value: Any, estimates: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "anchor_id",
        "anchor_kind",
        "owner_label",
        "label_authority",
        "source_estimate_id",
        "geometry",
    }:
        raise ValueError("owner anchor fields changed")
    source_id = _safe_id(value["source_estimate_id"], "source_estimate_id")
    estimate = next(
        (row for row in estimates if row["source_estimate_id"] == source_id), None
    )
    if estimate is None:
        raise ValueError("owner anchor references an unknown separation estimate")
    geometry = value["geometry"]
    if not isinstance(geometry, Mapping):
        raise ValueError("owner anchor geometry must be an object")
    checked_geometry = _anchor_geometry(
        estimate["geometry"],
        start_frame=geometry.get("start_frame"),
        end_frame=geometry.get("end_frame"),
    )
    if value["label_authority"] != "explicit_owner_label":
        raise ValueError("owner anchor must remain an explicit owner label")
    return {
        "anchor_id": _safe_id(value["anchor_id"], "anchor_id"),
        "anchor_kind": _choice(value["anchor_kind"], REMIX_ANCHOR_KINDS, "anchor kind"),
        "owner_label": _owner_text(value["owner_label"], "owner label", 240),
        "label_authority": "explicit_owner_label",
        "source_estimate_id": source_id,
        "geometry": checked_geometry,
    }


def _audio_record(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "audio_sha256",
        "audio_bytes",
        "geometry",
    }:
        raise ValueError(f"{label} fields changed")
    sha = str(value["audio_sha256"])
    size = value["audio_bytes"]
    geometry = value["geometry"]
    if (
        not _SHA256.fullmatch(sha)
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size <= 0
    ):
        raise ValueError(f"{label} identity is invalid")
    if not isinstance(geometry, Mapping) or set(geometry) != {
        "sample_rate_hz",
        "channels",
        "frames",
    }:
        raise ValueError(f"{label} geometry fields changed")
    checked: dict[str, int] = {}
    for key in ("sample_rate_hz", "channels", "frames"):
        item = geometry[key]
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise ValueError(f"{label} geometry is invalid")
        checked[key] = item
    return {"audio_sha256": sha, "audio_bytes": size, "geometry": checked}


def _anchor_geometry(
    geometry: Mapping[str, Any], *, start_frame: Any, end_frame: Any
) -> dict[str, int]:
    if (
        isinstance(start_frame, bool)
        or not isinstance(start_frame, int)
        or isinstance(end_frame, bool)
        or not isinstance(end_frame, int)
        or start_frame < 0
        or end_frame <= start_frame
        or end_frame > geometry["frames"]
    ):
        raise ValueError("anchor frame window is outside the estimate")
    return {
        "sample_rate_hz": geometry["sample_rate_hz"],
        "start_frame": start_frame,
        "end_frame": end_frame,
    }


def _verified(value: Mapping[str, Any], schema: str, label: str) -> dict[str, Any]:
    document = dict(value)
    if document.get("schema") != schema:
        raise ValueError(f"{label} schema changed")
    expected = str(document.get("document_sha256", ""))
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if not _SHA256.fullmatch(expected) or document_sha256(unsigned) != expected:
        raise ValueError(f"{label} document SHA-256 changed")
    return document


def _safe_id(value: Any, label: str) -> str:
    text = str(value)
    if not _SAFE_ID.fullmatch(text):
        raise ValueError(f"{label} is not a safe identifier")
    return text


def _owner_text(value: Any, label: str, maximum: int) -> str:
    text = str(value).strip()
    if (
        not text
        or len(text) > maximum
        or "\n" in text
        or "\r" in text
        or _looks_like_path(text)
    ):
        raise ValueError(f"{label} must be one path-free bounded line")
    return text


def _choice(value: Any, allowed: Sequence[str], label: str) -> str:
    text = str(value)
    if text not in allowed:
        raise ValueError(f"{label} is unsupported")
    return text


def _unique(rows: Sequence[Mapping[str, Any]], key: str, label: str) -> None:
    values = [row[key] for row in rows]
    if len(values) != len(set(values)):
        raise ValueError(f"{label} identities must be unique")


def _pending_authority() -> dict[str, bool]:
    return {
        "owner_confirmation_recorded": False,
        "remix_render_authorized": False,
        "pairwise_label_created": False,
        "training_execution_authorized": False,
        "product_selection_authorized": False,
    }


def _confirmed_authority() -> dict[str, bool]:
    return {
        "owner_anchor_confirmed": True,
        "remix_render_authorized": False,
        "pairwise_label_created": False,
        "training_execution_authorized": False,
        "checkpoint_promotion_authorized": False,
        "product_selection_authorized": False,
    }


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


def _identity_effects() -> dict[str, bool]:
    return {
        "source_mutated": False,
        "estimate_mutated": False,
        "remix_rendered": False,
        "training_started": False,
        "model_weights_changed": False,
    }


def _looks_like_path(text: str) -> bool:
    return (
        text.startswith(("/", "~", "file:"))
        or "\\" in text
        or bool(re.match(r"^[A-Za-z]:", text))
        or PurePosixPath(text).is_absolute()
        or PureWindowsPath(text).is_absolute()
    )


def _reject_paths(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key != "paths_embedded" and any(
                word in str(key).lower()
                for word in ("path", "filename", "directory", "url")
            ):
                raise ValueError(
                    "remix source anchor evidence must not contain path fields"
                )
            _reject_paths(item)
    elif isinstance(value, list):
        for item in value:
            _reject_paths(item)
    elif isinstance(value, str) and _looks_like_path(value):
        raise ValueError("remix source anchor evidence must not contain paths")


__all__ = [
    "REMIX_SOURCE_ANCHOR_CONFIRMATION_SCHEMA",
    "REMIX_SOURCE_ANCHOR_PREFLIGHT_SCHEMA",
    "REMIX_SOURCE_IDENTITY_SCHEMA",
    "REMIX_SOURCE_OWNER_REGISTRY_SCHEMA",
    "confirm_remix_source_anchor_preflight",
    "create_remix_source_anchor_preflight",
    "create_remix_source_identity_state",
    "create_remix_source_owner_registry",
    "validate_remix_source_anchor_confirmation",
    "validate_remix_source_anchor_preflight",
    "validate_remix_source_identity_state",
    "validate_remix_source_owner_registry",
]
