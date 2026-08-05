#!/usr/bin/env python3
"""List explicit source-distinct private-pilot reviews without resolving them."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_song_disjoint_private_pilot_queue import (
    _build_song_disjoint_private_pilot_review_queue,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pipeline_root", nargs="+")
    parser.add_argument("--review", action="append", default=[])
    parser.add_argument("--review-dir", action="append", default=[])
    parser.add_argument("--out")
    args = parser.parse_args()
    result = _build_song_disjoint_private_pilot_review_queue(
        args.pipeline_root,
        review_paths=args.review,
        review_directories=args.review_dir,
        out=args.out,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
