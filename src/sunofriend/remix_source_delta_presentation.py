"""Deterministic anonymous presentation for source-delta comparisons."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping


def resolve_remix_source_delta_display_variants(
    result: Mapping[str, Any], presentation_seed: Any
) -> dict[str, str]:
    """Map anonymous A/B labels to exactly two verified candidate IDs."""

    if isinstance(presentation_seed, bool) or not isinstance(presentation_seed, int):
        raise ValueError("presentation seed must be an integer")
    try:
        ordered = sorted(
            row["variant_id"] for row in result["artifacts"]["candidates"]
        )
        result_sha256 = result["document_sha256"]
    except (KeyError, TypeError) as exc:
        raise ValueError("source-delta presentation evidence changed") from exc
    if len(ordered) != 2 or len(set(ordered)) != 2:
        raise ValueError("source-delta presentation requires two distinct variants")
    if not isinstance(result_sha256, str) or len(result_sha256) != 64:
        raise ValueError("source-delta presentation result identity changed")
    digest = hashlib.sha256(f"{presentation_seed}:{result_sha256}".encode()).digest()
    if digest[0] & 1:
        ordered.reverse()
    return {"a": ordered[0], "b": ordered[1]}


__all__ = ["resolve_remix_source_delta_display_variants"]
