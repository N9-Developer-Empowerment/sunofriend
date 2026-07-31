#!/usr/bin/env python3
"""Run identical inactive MIDI processing over authorised role groups."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_authorised_midi_comparison import (
    _compare_authorised_role_midi,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the production repair loop or vocal contour under identical "
            "per-role settings for every mapped provider and local group. "
            "Outputs are private, inactive and unselected."
        )
    )
    parser.add_argument("--role-mapping", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--bpm", type=float, required=True)
    parser.add_argument("--tuning-hz", type=float, required=True)
    parser.add_argument("--max-iterations", type=int, default=30)
    args = parser.parse_args()
    result = _compare_authorised_role_midi(
        args.role_mapping,
        out_dir=args.out,
        bpm=args.bpm,
        tuning_hz=args.tuning_hz,
        max_iterations=args.max_iterations,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "note_counts": {
                    pack: {
                        role: evidence["primary"]["note_count"]
                        for role, evidence in roles.items()
                    }
                    for pack, roles in result["packs"].items()
                },
                "comparisons_to_local_htdemucs": result[
                    "comparisons_to_local_htdemucs"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
