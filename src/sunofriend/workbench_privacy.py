"""Shared privacy guards for path-free Workbench projections."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


_LOCAL_PATH_PATTERN = re.compile(
    r"(?ix)(?:\bfile:|(?<!\s)[/\\]|[/\\](?!\s)|\b[a-z]:(?!\s)|"
    r"\.(?:wav|wave|aif|aiff|flac|mp3|m4a|ogg|mid|midi|sf2|sfz|aupreset)"
    r"(?![A-Za-z0-9]))"
)


def contains_local_path(value: Any) -> bool:
    """Return whether free-form text appears to contain a local filesystem path."""

    return bool(_LOCAL_PATH_PATTERN.search(str(value or "")))


def path_free_role(
    value: Any,
    *,
    fallback: str = "unclassified",
) -> tuple[str, bool]:
    """Return a musical-role label safe for path-free UI and export surfaces."""

    if value is None:
        return fallback, False
    if not isinstance(value, str):
        return "custom role", True
    text = value.strip()
    if (
        not text
        or len(text) > 80
        or any(ord(character) < 32 for character in text)
        or contains_local_path(text)
    ):
        return "custom role", True
    return text, False


def validated_role(value: str, *, maximum: int = 80) -> str:
    """Reject new role tags that contain a local path instead of storing a leak."""

    text = value.strip()
    if not text:
        raise ValueError("role must not be empty")
    if len(text) > maximum:
        raise ValueError(f"role must be at most {maximum} characters")
    if any(ord(character) < 32 for character in text):
        raise ValueError("role must be one line without control characters")
    if contains_local_path(text):
        raise ValueError(
            "role must describe a musical role and must not contain a local path"
        )
    return text


def path_free_browser_state(current: Any) -> Any:
    """Copy current local state while redacting only path-like role labels."""

    projected = deepcopy(current)
    if not isinstance(projected, dict):
        return projected
    stems = projected.get("stems")
    if not isinstance(stems, dict):
        return projected
    for state in stems.values():
        if not isinstance(state, dict):
            continue
        state["role"], state["role_redacted"] = path_free_role(state.get("role"))
    return projected
