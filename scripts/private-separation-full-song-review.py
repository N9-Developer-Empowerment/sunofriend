#!/usr/bin/env python3
"""Resolve one completed private full-song and chunk-boundary review."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_full_song_review import (
    _resolve_private_separation_full_song_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolve", required=True, metavar="REVIEWED_JSON")
    parser.add_argument(
        "--package-dir",
        required=True,
        help="unchanged private full-song stitch directory",
    )
    parser.add_argument("--out", required=True, help="fresh private result JSON")
    args = parser.parse_args()
    result = _resolve_private_separation_full_song_review(
        args.resolve,
        package_dir=args.package_dir,
        out=args.out,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
