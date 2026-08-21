#!/usr/bin/env python3
"""Open one owner-only session for naming an exact remix identity anchor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sunofriend.remix_anchor_session import (
    create_remix_anchor_server,
    run_remix_anchor_server,
)


def _document(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Open a private listening page that records one explicit musical "
            "relationship a controlled remix must preserve."
        )
    )
    parser.add_argument("--musical-state", required=True)
    parser.add_argument("--source-control", required=True)
    parser.add_argument("--separation-estimate", required=True)
    parser.add_argument("--source-estimate-id", required=True)
    parser.add_argument("--estimated-role", required=True)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--identity-state-id", required=True)
    parser.add_argument("--registry-id", required=True)
    parser.add_argument("--composition-id", required=True)
    parser.add_argument("--group-id", required=True)
    parser.add_argument("--title", default="Define what must stay recognisable")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = create_remix_anchor_server(
        _document(args.musical_state),
        source_control=args.source_control,
        separation_estimate=args.separation_estimate,
        source_estimate_id=args.source_estimate_id,
        estimated_role=args.estimated_role,
        state_dir=args.state_dir,
        identity_state_id=args.identity_state_id,
        registry_id=args.registry_id,
        composition_id=args.composition_id,
        group_id=args.group_id,
        title=args.title,
        port=args.port,
    )
    run_remix_anchor_server(server, open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
