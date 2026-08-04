#!/usr/bin/env python3
"""Verify or resolve a completed candidate-bound full-song review."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_candidate_full_song_review_result import (
    _resolve_private_candidate_full_song_review,
    _status_private_candidate_full_song_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--status", metavar="REVIEWED_JSON")
    action.add_argument("--resolve", metavar="REVIEWED_JSON")
    parser.add_argument("--review-package-dir", required=True)
    parser.add_argument("--v2-review-result", required=True)
    parser.add_argument("--v2-execution-dir", required=True)
    parser.add_argument("--v2-plan", required=True)
    parser.add_argument("--v1-execution-dir", required=True)
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--full-song-review-result", required=True)
    parser.add_argument("--v1-plan", required=True)
    parser.add_argument("--resolved-join-review-result", required=True)
    parser.add_argument("--publication-readiness", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()
    common = {
        "review_package_dir": args.review_package_dir,
        "v2_review_result_path": args.v2_review_result,
        "v2_execution_dir": args.v2_execution_dir,
        "v2_plan_path": args.v2_plan,
        "v1_execution_dir": args.v1_execution_dir,
        "stitch_package_dir": args.package_dir,
        "full_song_review_result_path": args.full_song_review_result,
        "v1_plan_path": args.v1_plan,
        "resolved_join_review_result_path": args.resolved_join_review_result,
        "publication_readiness_path": args.publication_readiness,
    }
    if args.status is not None:
        if args.out is not None:
            parser.error("--out is only valid with --resolve")
        result = _status_private_candidate_full_song_review(args.status, **common)
    else:
        if args.out is None:
            parser.error("--resolve requires --out")
        result = _resolve_private_candidate_full_song_review(
            args.resolve,
            out=args.out,
            **common,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
