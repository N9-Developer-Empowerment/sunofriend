#!/usr/bin/env python3
"""Plan targeted private re-inference for human-rated full-song joins."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_full_song_join_remediation_plan import (
    _plan_private_separation_full_song_join_remediation,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify one stitch, completed human review and passing alignment "
            "result, then plan bounded candidate-only join remediation."
        )
    )
    parser.add_argument(
        "package_dir",
        help="unchanged private full-song stitch and review package",
    )
    parser.add_argument("--review-result", required=True)
    parser.add_argument("--alignment-result", required=True)
    parser.add_argument("--out", required=True, help="fresh owner-only plan JSON")
    args = parser.parse_args()
    result = _plan_private_separation_full_song_join_remediation(
        args.package_dir,
        args.review_result,
        args.alignment_result,
        out=args.out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "summary": result["summary"],
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
