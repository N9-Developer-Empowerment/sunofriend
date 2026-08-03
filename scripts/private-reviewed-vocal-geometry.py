#!/usr/bin/env python3
"""Compare note geometry among useful candidates in one sealed vocal review."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_reviewed_vocal_geometry import (
    _compare_reviewed_vocal_geometry,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-resolution", required=True)
    parser.add_argument("--candidate-set", required=True)
    parser.add_argument("--melroformer-evaluation", required=True)
    parser.add_argument("--vocal-leaf-evaluation", required=True)
    parser.add_argument("--phrase-completeness", required=True)
    parser.add_argument("--authorised-excerpt", required=True)
    parser.add_argument("--onset-tolerance-ms", type=float, default=80.0)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _compare_reviewed_vocal_geometry(
        args.review_resolution,
        args.candidate_set,
        args.melroformer_evaluation,
        args.vocal_leaf_evaluation,
        args.phrase_completeness,
        args.authorised_excerpt,
        out=args.out,
        tolerance_seconds=args.onset_tolerance_ms / 1000.0,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "focus": result["focus"],
                "candidate_count": result["policy"]["candidate_count"],
                "pair_count": result["observations"]["pair_count"],
                "candidate_ranked_or_selected": result["policy"][
                    "candidate_ranked_or_selected"
                ],
                "automatic_merge": result["policy"]["automatic_merge"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
