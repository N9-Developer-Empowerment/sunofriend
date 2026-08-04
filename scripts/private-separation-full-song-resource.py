#!/usr/bin/env python3
"""Measure coarse verified resource evidence for one private full-song run."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_full_song_resource import (
    _observe_private_separation_full_song_resources,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--execution", required=True)
    parser.add_argument("--stitch", required=True)
    parser.add_argument("--out", required=True, help="fresh private report JSON")
    args = parser.parse_args()
    result = _observe_private_separation_full_song_resources(
        args.plan,
        args.execution,
        args.stitch,
        out=args.out,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
