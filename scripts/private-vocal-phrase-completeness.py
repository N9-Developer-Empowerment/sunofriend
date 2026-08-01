#!/usr/bin/env python3
"""Measure inactive phrase-time coverage for private vocal MIDI evidence."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_vocal_phrase_completeness import (
    _evaluate_vocal_phrase_completeness,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-comparison", required=True)
    parser.add_argument("--melroformer-evaluation", required=True)
    parser.add_argument("--vocal-leaf-evaluation", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _evaluate_vocal_phrase_completeness(
        args.control_comparison,
        args.melroformer_evaluation,
        args.vocal_leaf_evaluation,
        out_dir=args.out,
    )
    consensus = result["provider_consensus"]
    candidate_fields = (
        "note_count",
        "consensus_covered_seconds",
        "consensus_coverage_ratio",
        "activity_supported_by_consensus_ratio",
        "phrase_count_with_any_coverage",
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "provider_consensus": {
                    "active_seconds": consensus["active_seconds"],
                    "interval_count": consensus["interval_count"],
                    "phrase_count": consensus["phrase_count"],
                },
                "primary": {
                    field: result["candidates"]["primary"][field]
                    for field in candidate_fields
                },
                "lowest_line": {
                    field: result["candidates"]["lowest_line"][field]
                    for field in candidate_fields
                },
                "primary_vs_lowest": result["primary_vs_lowest"],
                "next": result["next"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
