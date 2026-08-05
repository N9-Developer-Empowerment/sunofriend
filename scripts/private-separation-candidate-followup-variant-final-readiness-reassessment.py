#!/usr/bin/env python3
"""Reassess exact final-acceptance evidence for a bounded private pilot."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_candidate_followup_variant_final_readiness_reassessment import (
    _reassess_private_candidate_followup_variant_final_readiness,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final-acceptance-result", required=True)
    parser.add_argument(
        "--final-acceptance-reviewed-export", action="append", required=True
    )
    parser.add_argument("--review-package-dir", required=True)
    parser.add_argument("--readiness-result", required=True)
    parser.add_argument("--full-song-review-result", required=True)
    parser.add_argument("--alignment-package-dir", required=True)
    parser.add_argument("--full-song-reviewed-export", action="append", required=True)
    parser.add_argument("--full-song-review-package-dir", required=True)
    parser.add_argument("--variant-review-result", required=True)
    parser.add_argument("--variant-reviewed-export", required=True)
    parser.add_argument("--variant-review-package-dir", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--execution-dir", required=True)
    parser.add_argument("--v2-execution-dir", required=True)
    parser.add_argument("--variant-execution-dir", required=True)
    parser.add_argument("--stitch-package-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _reassess_private_candidate_followup_variant_final_readiness(
        args.final_acceptance_result,
        final_acceptance_review_export_paths=(args.final_acceptance_reviewed_export),
        review_package_dir=args.review_package_dir,
        readiness_result_path=args.readiness_result,
        full_song_review_result_path=args.full_song_review_result,
        alignment_package_dir=args.alignment_package_dir,
        full_song_review_export_paths=args.full_song_reviewed_export,
        full_song_review_package_dir=args.full_song_review_package_dir,
        variant_review_result_path=args.variant_review_result,
        variant_reviewed_export_path=args.variant_reviewed_export,
        variant_review_package_dir=args.variant_review_package_dir,
        plan_path=args.plan,
        execution_dir=args.execution_dir,
        v2_execution_dir=args.v2_execution_dir,
        variant_execution_dir=args.variant_execution_dir,
        stitch_package_dir=args.stitch_package_dir,
        out=args.out,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
