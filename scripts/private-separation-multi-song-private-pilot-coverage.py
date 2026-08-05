#!/usr/bin/env python3
"""Verify reviewed source-distinct private pilots into one coverage ledger."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_multi_song_private_pilot_coverage import (
    _build_multi_song_private_pilot_coverage,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pragmatic-authorization",
        required=True,
        help="exact sealed pragmatic private-pilot authorization",
    )
    parser.add_argument(
        "--pilot",
        action="append",
        nargs=3,
        required=True,
        metavar=("EVIDENCE", "REVIEW_RESULT", "HANDOFF_DIR"),
        help=(
            "one automatic pilot envelope, its authorised review result and "
            "its exact two-stem handoff; repeat for additional songs"
        ),
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _build_multi_song_private_pilot_coverage(
        args.pragmatic_authorization,
        pilots=args.pilot,
        out=args.out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "coverage": result["coverage"],
                "private_evaluation_checkpoint": result[
                    "private_evaluation_checkpoint"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
