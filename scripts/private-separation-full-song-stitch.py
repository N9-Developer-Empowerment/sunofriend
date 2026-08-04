#!/usr/bin/env python3
"""Create an exact private stitch and boundary-review package."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_full_song_stitch import (
    _stitch_private_separation_full_song,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify and concatenate one complete private chunk execution, then "
            "prepare a boundary-listening page. No separator is selected."
        )
    )
    parser.add_argument("--plan", required=True)
    parser.add_argument("--execution", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    result = _stitch_private_separation_full_song(
        args.plan,
        args.execution,
        out_dir=args.out_dir,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "review_html": result["review_html"],
                "clock": result["clock"],
                "readiness": result["readiness"],
                "permissions": result["permissions"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
