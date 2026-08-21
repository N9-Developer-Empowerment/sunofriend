"""Audio-native source identity for controlled remix work.

The original Musical State v0 is deliberately vocal-specific.  A controlled
remix must not invent lyrics or vocal takes merely to bind an authorised source
excerpt.  This module supplies the smallest path-free source state needed by
the remix identity, rendering and learning contracts.
"""

from __future__ import annotations

import math
from pathlib import PurePosixPath, PureWindowsPath
import re
from typing import Any, Mapping

from .musical_state import MUSICAL_STATE_SCHEMA, validate_musical_state
from .source_receipt import document_sha256


REMIX_SOURCE_STATE_SCHEMA = "sunofriend.remix-source-state.v0"
REMIX_PROJECT_STATE_SCHEMAS = frozenset(
    {MUSICAL_STATE_SCHEMA, REMIX_SOURCE_STATE_SCHEMA}
)

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def create_remix_source_state(
    *,
    state_id: str,
    composition_id: str,
    group_id: str,
    source_control: Mapping[str, Any],
    rights_category: str,
    source_start_seconds: float,
    source_end_seconds: float,
    owner_local_training_approved: bool,
    cloud_training_approved: bool = False,
) -> dict[str, Any]:
    """Create one owner-authorised, path-free source excerpt identity."""

    state_name = _safe_id(state_id, "state_id")
    composition = _safe_id(composition_id, "composition_id")
    group = _safe_id(group_id, "group_id")
    control = _audio_record(source_control)
    start = _finite_number(source_start_seconds, "source_start_seconds")
    end = _finite_number(source_end_seconds, "source_end_seconds")
    duration = control["geometry"]["frames"] / control["geometry"]["sample_rate_hz"]
    if (
        start < 0
        or end <= start
        or abs((end - start) - duration) > 0.5 / control["geometry"]["sample_rate_hz"]
    ):
        raise ValueError("source excerpt clock does not match exact audio geometry")
    if rights_category != "owned":
        raise ValueError("remix source v0 currently requires owner-controlled audio")
    if owner_local_training_approved is not True:
        raise ValueError("owner-local training approval must be explicit")
    if cloud_training_approved is not False:
        raise ValueError("cloud training requires a separate future authorization")

    document: dict[str, Any] = {
        "schema": REMIX_SOURCE_STATE_SCHEMA,
        "status": "complete_owner_authorised_source_no_anchor",
        "state_id": state_name,
        "composition_id": composition,
        "group_id": group,
        "source_control": control,
        "clock": {
            "origin": "bounded_source_excerpt_zero",
            "source_start_seconds": start,
            "source_end_seconds": end,
            "duration_seconds": duration,
        },
        "authorization": {
            "rights_category": "owned",
            "rights_confirmed": True,
            "owner_local_training_approved": True,
            "cloud_training_approved": False,
        },
        "method_natures": ["D", "H"],
        "authority": {
            "owner_anchor_confirmed": False,
            "remix_render_authorized": False,
            "pairwise_label_created": False,
            "training_execution_authorized": False,
            "product_selection_authorized": False,
        },
        "effects": {
            "source_mutated": False,
            "remix_rendered": False,
            "training_started": False,
            "model_weights_changed": False,
            "product_selection_changed": False,
        },
    }
    document["document_sha256"] = document_sha256(document)
    return validate_remix_source_state(document)


def validate_remix_source_state(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one path-free remix source identity."""

    document = dict(value)
    if set(document) != {
        "schema",
        "status",
        "state_id",
        "composition_id",
        "group_id",
        "source_control",
        "clock",
        "authorization",
        "method_natures",
        "authority",
        "effects",
        "document_sha256",
    }:
        raise ValueError("remix source state fields changed")
    if document.get("schema") != REMIX_SOURCE_STATE_SCHEMA:
        raise ValueError("unsupported remix source state schema")
    expected_sha = str(document.get("document_sha256", ""))
    unsigned = dict(document)
    unsigned.pop("document_sha256", None)
    if not _SHA256.fullmatch(expected_sha) or document_sha256(unsigned) != expected_sha:
        raise ValueError("remix source state document SHA-256 changed")
    if document["status"] != "complete_owner_authorised_source_no_anchor":
        raise ValueError("remix source state status changed")
    for key in ("state_id", "composition_id", "group_id"):
        _safe_id(document[key], key)
    control = _audio_record(document["source_control"])
    if control != document["source_control"]:
        raise ValueError("remix source audio identity changed")
    clock = document["clock"]
    if not isinstance(clock, Mapping) or set(clock) != {
        "origin",
        "source_start_seconds",
        "source_end_seconds",
        "duration_seconds",
    }:
        raise ValueError("remix source clock fields changed")
    start = _finite_number(clock["source_start_seconds"], "source_start_seconds")
    end = _finite_number(clock["source_end_seconds"], "source_end_seconds")
    duration = control["geometry"]["frames"] / control["geometry"]["sample_rate_hz"]
    if (
        clock["origin"] != "bounded_source_excerpt_zero"
        or start < 0
        or end <= start
        or clock["duration_seconds"] != duration
        or abs((end - start) - duration) > 0.5 / control["geometry"]["sample_rate_hz"]
    ):
        raise ValueError("remix source clock does not match exact audio geometry")
    if document["authorization"] != {
        "rights_category": "owned",
        "rights_confirmed": True,
        "owner_local_training_approved": True,
        "cloud_training_approved": False,
    }:
        raise ValueError("remix source authorization changed")
    if document["method_natures"] != ["D", "H"]:
        raise ValueError("remix source method nature changed")
    if document["authority"] != {
        "owner_anchor_confirmed": False,
        "remix_render_authorized": False,
        "pairwise_label_created": False,
        "training_execution_authorized": False,
        "product_selection_authorized": False,
    }:
        raise ValueError("remix source state cannot claim downstream authority")
    if document["effects"] != {
        "source_mutated": False,
        "remix_rendered": False,
        "training_started": False,
        "model_weights_changed": False,
        "product_selection_changed": False,
    }:
        raise ValueError("remix source state cannot claim downstream effects")
    _reject_paths(document)
    return document


def validate_remix_project_state(value: Mapping[str, Any]) -> dict[str, Any]:
    """Accept the legacy vocal foundation or the dedicated remix source state."""

    schema = value.get("schema") if isinstance(value, Mapping) else None
    if schema == MUSICAL_STATE_SCHEMA:
        return validate_musical_state(value)
    if schema == REMIX_SOURCE_STATE_SCHEMA:
        return validate_remix_source_state(value)
    raise ValueError("unsupported remix project state schema")


def _audio_record(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "audio_sha256",
        "audio_bytes",
        "geometry",
    }:
        raise ValueError("source control fields changed")
    sha = str(value.get("audio_sha256", ""))
    size = value.get("audio_bytes")
    geometry = value.get("geometry")
    if not _SHA256.fullmatch(sha):
        raise ValueError("source control SHA-256 is invalid")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ValueError("source control byte count is invalid")
    if not isinstance(geometry, Mapping) or set(geometry) != {
        "sample_rate_hz",
        "channels",
        "frames",
    }:
        raise ValueError("source control geometry fields changed")
    checked_geometry: dict[str, int] = {}
    for key in ("sample_rate_hz", "channels", "frames"):
        item = geometry.get(key)
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise ValueError("source control geometry is invalid")
        checked_geometry[key] = item
    return {
        "audio_sha256": sha,
        "audio_bytes": size,
        "geometry": checked_geometry,
    }


def _safe_id(value: Any, label: str) -> str:
    text = str(value)
    if not _SAFE_ID.fullmatch(text):
        raise ValueError(f"{label} is not a safe identifier")
    return text


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be finite")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


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
            if any(
                word in str(key).lower()
                for word in ("path", "filename", "directory", "url")
            ):
                raise ValueError("remix source state must not contain path fields")
            _reject_paths(item)
    elif isinstance(value, list):
        for item in value:
            _reject_paths(item)
    elif isinstance(value, str) and _looks_like_path(value):
        raise ValueError("remix source state must not contain paths")


__all__ = [
    "REMIX_PROJECT_STATE_SCHEMAS",
    "REMIX_SOURCE_STATE_SCHEMA",
    "create_remix_source_state",
    "validate_remix_project_state",
    "validate_remix_source_state",
]
