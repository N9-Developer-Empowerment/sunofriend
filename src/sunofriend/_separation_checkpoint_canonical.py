"""Pure canonical JSON helpers for private checkpoint evidence.

This module performs no filesystem, descriptor, model, process, network,
audio or write operation.  Callers retain their own schema, authority and
path-free validation boundaries.
"""

from __future__ import annotations

import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping


def canonical_json_bytes(
    value: Any,
    *,
    error_message: str | None = None,
) -> bytes:
    """Return the exact ASCII canonical JSON encoding used by V1 records."""

    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as exc:
        if error_message is None:
            raise
        raise ValueError(error_message) from exc


def canonical_sha256(
    value: Any,
    *,
    error_message: str | None = None,
) -> str:
    """Hash the exact canonical JSON byte representation."""

    return hashlib.sha256(
        canonical_json_bytes(value, error_message=error_message)
    ).hexdigest()


def plain(value: Any) -> Any:
    """Recursively copy mappings and sequences into mutable JSON containers."""

    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def deep_freeze(value: Any) -> Any:
    """Recursively freeze JSON dictionaries and lists."""

    if isinstance(value, dict):
        return MappingProxyType(
            {key: deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(deep_freeze(item) for item in value)
    return value
