#!/usr/bin/env python3
"""Reassess exact follow-up review and alignment evidence without activation."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_candidate_followup_readiness_reassessment import (
    _reassess_private_candidate_followup_readiness,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-song-review-result", required=True)
    parser.add_argument("--alignment-result", required=True)
    parser.add_argument("--full-song-reviewed-export", required=True)
    parser.add_argument("--full-song-review-package-dir", required=True)
    parser.add_argument("--targeted-review-result", required=True)
    parser.add_argument("--targeted-reviewed-export", required=True)
    parser.add_argument("--targeted-review-package-dir", required=True)
    parser.add_argument("--execution-dir", required=True)
    parser.add_argument("--v2-execution-dir", required=True)
    parser.add_argument("--stitch-package-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _reassess_private_candidate_followup_readiness(
        args.full_song_review_result,
        alignment_result_path=args.alignment_result,
        full_song_review_export_path=args.full_song_reviewed_export,
        full_song_review_package_dir=args.full_song_review_package_dir,
        targeted_review_result_path=args.targeted_review_result,
        targeted_reviewed_export_path=args.targeted_reviewed_export,
        targeted_review_package_dir=args.targeted_review_package_dir,
        execution_dir=args.execution_dir,
        v2_execution_dir=args.v2_execution_dir,
        stitch_package_dir=args.stitch_package_dir,
        out=args.out,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
