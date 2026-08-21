#!/usr/bin/env python3
"""Open one owner-only controlled-remix A/B review session."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sunofriend.remix_pairwise_session import (
    create_remix_pairwise_review_server,
    run_remix_pairwise_review_server,
)


def _document(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _variant_paths(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--variant-audio must use VARIANT_ID=/path/to/audio.wav")
        variant_id, raw_path = value.split("=", 1)
        if not variant_id or not raw_path or variant_id in result:
            raise ValueError("variant audio IDs and paths must be unique and non-empty")
        result[variant_id] = Path(raw_path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Open a private neutral A/B page for one exact controlled remix pair."
    )
    parser.add_argument("--owner-registry", required=True)
    parser.add_argument("--musical-state", required=True)
    parser.add_argument("--variant-set", required=True)
    parser.add_argument("--identity-state", required=True)
    parser.add_argument("--control-audio", required=True)
    parser.add_argument(
        "--variant-audio",
        action="append",
        required=True,
        help="Repeat exactly twice as VARIANT_ID=/path/to/audio.wav",
    )
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--title", default="Remix A/B review")
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--presentation-seed", type=int)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = create_remix_pairwise_review_server(
        _document(args.musical_state),
        _document(args.owner_registry),
        _document(args.variant_set),
        _document(args.identity_state),
        control_audio=args.control_audio,
        variant_audio=_variant_paths(args.variant_audio),
        state_dir=args.state_dir,
        title=args.title,
        port=args.port,
        presentation_seed=args.presentation_seed,
    )
    run_remix_pairwise_review_server(server, open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
