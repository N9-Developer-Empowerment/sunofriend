#!/usr/bin/env python3
"""Verify or resolve every eligible-variant full-song review."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_candidate_followup_variant_full_song_review_result import (
    _resolve_private_candidate_followup_variant_full_song_reviews,
    _status_private_candidate_followup_variant_full_song_reviews,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--status", action="store_true")
    action.add_argument("--resolve", action="store_true")
    parser.add_argument("--reviewed-export", action="append", required=True)
    parser.add_argument("--review-package-dir", required=True)
    parser.add_argument("--variant-review-result", required=True)
    parser.add_argument("--variant-reviewed-export", required=True)
    parser.add_argument("--variant-review-package-dir", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--execution-dir", required=True)
    parser.add_argument("--v2-execution-dir", required=True)
    parser.add_argument("--variant-execution-dir", required=True)
    parser.add_argument("--stitch-package-dir", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()
    kwargs = {
        "review_package_dir": args.review_package_dir,
        "variant_review_result_path": args.variant_review_result,
        "variant_reviewed_export_path": args.variant_reviewed_export,
        "variant_review_package_dir": args.variant_review_package_dir,
        "plan_path": args.plan,
        "execution_dir": args.execution_dir,
        "v2_execution_dir": args.v2_execution_dir,
        "variant_execution_dir": args.variant_execution_dir,
        "stitch_package_dir": args.stitch_package_dir,
    }
    if args.status:
        if args.out:
            parser.error("--out is valid only with --resolve")
        result = _status_private_candidate_followup_variant_full_song_reviews(
            args.reviewed_export, **kwargs
        )
    else:
        if not args.out:
            parser.error("--resolve requires --out")
        result = _resolve_private_candidate_followup_variant_full_song_reviews(
            args.reviewed_export, out=args.out, **kwargs
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
