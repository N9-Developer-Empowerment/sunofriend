#!/usr/bin/env python3
"""Open one review-only controlled remix comparison on localhost."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sunofriend.remix_comparison_session import (
    create_remix_comparison_server,
    run_remix_comparison_server,
)


def _document(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _candidates(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--candidate must use CANDIDATE_ID=/path/to/audio.wav")
        candidate_id, raw_path = value.split("=", 1)
        if not candidate_id or not raw_path or candidate_id in result:
            raise ValueError("candidate IDs and paths must be unique and non-empty")
        result[candidate_id] = Path(raw_path)
    if len(result) != 2:
        raise ValueError("repeat --candidate exactly twice")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Open an owner-only, review-only page for original context and one "
            "stable hidden A/B remix pair."
        )
    )
    parser.add_argument("--source-state", required=True)
    parser.add_argument("--anchor-preflight", required=True)
    parser.add_argument("--identity-state", required=True)
    parser.add_argument("--owner-registry", required=True)
    parser.add_argument("--anchor-confirmation", required=True)
    parser.add_argument("--original-audio", required=True)
    parser.add_argument(
        "--candidate",
        action="append",
        required=True,
        help="Repeat exactly twice as CANDIDATE_ID=/path/to/audio.wav",
    )
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--title", default="Controlled remix review")
    parser.add_argument(
        "--goal",
        default="Make the remix more useful while keeping the song recognisable.",
    )
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--presentation-seed", type=int)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = create_remix_comparison_server(
        _document(args.source_state),
        _document(args.anchor_preflight),
        _document(args.identity_state),
        _document(args.owner_registry),
        _document(args.anchor_confirmation),
        original_audio=args.original_audio,
        candidate_audio=_candidates(args.candidate),
        state_dir=args.state_dir,
        title=args.title,
        goal=args.goal,
        port=args.port,
        presentation_seed=args.presentation_seed,
    )
    run_remix_comparison_server(server, open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
