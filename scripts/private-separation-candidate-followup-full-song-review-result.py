#!/usr/bin/env python3
"""Verify or resolve a completed follow-up full-song/all-boundary review."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_candidate_followup_full_song_review_result import (
    _resolve_private_candidate_followup_full_song_review,
    _status_private_candidate_followup_full_song_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--status", metavar="REVIEWED_JSON")
    action.add_argument("--resolve", metavar="REVIEWED_JSON")
    parser.add_argument("--review-package-dir", required=True)
    parser.add_argument("--targeted-review-result", required=True)
    parser.add_argument("--targeted-reviewed-export", required=True)
    parser.add_argument("--targeted-review-package-dir", required=True)
    parser.add_argument("--execution-dir", required=True)
    parser.add_argument("--v2-execution-dir", required=True)
    parser.add_argument("--stitch-package-dir", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()
    kwargs = {
        "review_package_dir": args.review_package_dir,
        "targeted_review_result_path": args.targeted_review_result,
        "targeted_reviewed_export_path": args.targeted_reviewed_export,
        "targeted_review_package_dir": args.targeted_review_package_dir,
        "execution_dir": args.execution_dir,
        "v2_execution_dir": args.v2_execution_dir,
        "stitch_package_dir": args.stitch_package_dir,
    }
    if args.status:
        if args.out:
            parser.error("--out is valid only with --resolve")
        result = _status_private_candidate_followup_full_song_review(
            args.status, **kwargs
        )
    else:
        if not args.out:
            parser.error("--resolve requires --out")
        result = _resolve_private_candidate_followup_full_song_review(
            args.resolve, out=args.out, **kwargs
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
