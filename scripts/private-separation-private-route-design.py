#!/usr/bin/env python3
"""Seal a private-only separation route design without activating it."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_private_route_design import (
    _build_private_separation_route_design,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--coverage-report",
        required=True,
        help="exact owner-only multi-song private-pilot coverage report",
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _build_private_separation_route_design(
        args.coverage_report,
        out=args.out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "evidence_checkpoint": result["evidence_checkpoint"],
                "route_boundary": result["route_boundary"],
                "readiness": result["readiness"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
