#!/usr/bin/env python3
"""Measure private full-song source-to-reconstruction alignment and drift."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_full_song_alignment import (
    _measure_private_separation_full_song_alignment,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", help="verified private full-song stitch directory")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _measure_private_separation_full_song_alignment(
        args.package_dir,
        out=args.out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "readiness": result["readiness"],
                "summary": result["summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
