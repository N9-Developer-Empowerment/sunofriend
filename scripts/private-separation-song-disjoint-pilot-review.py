#!/usr/bin/env python3
"""Verify or resolve one completed source-distinct private-pilot review."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_song_disjoint_private_pilot_review import (
    _resolve_private_song_disjoint_pilot_review,
    _status_private_song_disjoint_pilot_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--status", metavar="REVIEWED_JSON")
    action.add_argument("--resolve", metavar="REVIEWED_JSON")
    parser.add_argument("--pilot-evidence", required=True)
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()
    common = {
        "pilot_evidence_path": args.pilot_evidence,
        "package_dir": args.package_dir,
    }
    if args.status is not None:
        if args.out is not None:
            parser.error("--out is valid only with --resolve")
        result = _status_private_song_disjoint_pilot_review(
            args.status,
            **common,
        )
    else:
        if args.out is None:
            parser.error("--resolve requires --out")
        result = _resolve_private_song_disjoint_pilot_review(
            args.resolve,
            out=args.out,
            **common,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
