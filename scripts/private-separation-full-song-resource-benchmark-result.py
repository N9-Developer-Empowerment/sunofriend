#!/usr/bin/env python3
"""Verify all frozen private resource repetitions and write one result."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_full_song_resource_benchmark_result import (
    _verify_private_full_song_resource_benchmark,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-plan", required=True)
    parser.add_argument(
        "--repetition-report",
        required=True,
        action="append",
        help="repeat once for every frozen repetition slot",
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _verify_private_full_song_resource_benchmark(
        args.benchmark_plan,
        args.repetition_report,
        out=args.out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "coverage": result["coverage"],
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
