#!/usr/bin/env python3
"""Prepare a full-song queue for the bounded private Kim worker."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_full_song_plan import (
    _prepare_private_separation_full_song_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Convert one owner-authorised original into gap-free 44.1 kHz "
            "worker chunks. This creates no separator result and enables no "
            "product route."
        )
    )
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--track-id", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    result = _prepare_private_separation_full_song_plan(
        args.corpus,
        args.track_id,
        out_dir=args.out_dir,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "track_id": result["corpus"]["track_id"],
                "canonical_clock": result["canonical_clock"],
                "chunking": result["chunking"],
                "readiness": result["readiness"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
