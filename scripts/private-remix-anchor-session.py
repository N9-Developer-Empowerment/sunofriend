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
    parser.add_argument("--project-state", required=True)
    parser.add_argument("--source-control", required=True)
    parser.add_argument("--separation-estimate", required=True)
    parser.add_argument("--source-estimate-id", required=True)
    parser.add_argument("--estimated-role", required=True)
    parser.add_argument(
        "--diagnostic-vocals",
        help="Optional synchronized vocal estimate for melody and phrasing audition",
    )
    parser.add_argument(
        "--diagnostic-drums",
        help="Optional synchronized drum estimate for groove audition",
    )
    parser.add_argument(
        "--diagnostic-bass",
        help="Optional synchronized bass estimate for bassline, groove and harmony audition",
    )
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--identity-state-id", required=True)
    parser.add_argument("--registry-id", required=True)
    parser.add_argument(
        "--composition-id",
        help="Legacy vocal-state compatibility only; source states already bind this ID",
    )
    parser.add_argument(
        "--group-id",
        help="Legacy vocal-state compatibility only; source states already bind this ID",
    )
    parser.add_argument("--title", default="Define what must stay recognisable")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    diagnostic_estimates = None
    if any((args.diagnostic_vocals, args.diagnostic_drums, args.diagnostic_bass)):
        diagnostic_estimates = {
            "grouped_other": args.separation_estimate,
            **({"vocals": args.diagnostic_vocals} if args.diagnostic_vocals else {}),
            **({"drums": args.diagnostic_drums} if args.diagnostic_drums else {}),
            **({"bass": args.diagnostic_bass} if args.diagnostic_bass else {}),
        }
    server = create_remix_anchor_server(
        _document(args.project_state),
        source_control=args.source_control,
        separation_estimate=args.separation_estimate,
        source_estimate_id=args.source_estimate_id,
        estimated_role=args.estimated_role,
        diagnostic_estimates=diagnostic_estimates,
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
