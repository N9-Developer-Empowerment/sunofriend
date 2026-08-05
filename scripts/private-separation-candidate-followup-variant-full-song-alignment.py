#!/usr/bin/env python3
"""Measure every independently reviewed eligible variant's full-song clock."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_candidate_followup_variant_full_song_alignment import (
    _measure_private_candidate_followup_variant_full_song_alignments,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-song-review-result", required=True)
    parser.add_argument(
        "--full-song-reviewed-export", action="append", required=True
    )
    parser.add_argument("--full-song-review-package-dir", required=True)
    parser.add_argument("--variant-review-result", required=True)
    parser.add_argument("--variant-reviewed-export", required=True)
    parser.add_argument("--variant-review-package-dir", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--execution-dir", required=True)
    parser.add_argument("--v2-execution-dir", required=True)
    parser.add_argument("--variant-execution-dir", required=True)
    parser.add_argument("--stitch-package-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    result = _measure_private_candidate_followup_variant_full_song_alignments(
        args.full_song_review_result,
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
        out_dir=args.out_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
