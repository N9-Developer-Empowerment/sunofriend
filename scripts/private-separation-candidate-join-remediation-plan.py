#!/usr/bin/env python3
"""Plan a fresh candidate join-remediation iteration without running a model."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_candidate_join_remediation_plan import (
    _plan_private_candidate_join_remediation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v2-review-result", required=True)
    parser.add_argument("--candidate-review-result", required=True)
    parser.add_argument("--candidate-alignment-result", required=True)
    parser.add_argument("--readiness-reassessment", required=True)
    parser.add_argument("--v2-execution-dir", required=True)
    parser.add_argument("--v2-plan", required=True)
    parser.add_argument("--v1-execution-dir", required=True)
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--full-song-review-result", required=True)
    parser.add_argument("--v1-plan", required=True)
    parser.add_argument("--resolved-join-review-result", required=True)
    parser.add_argument("--publication-readiness", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _plan_private_candidate_join_remediation(
        args.v2_review_result,
        candidate_review_result_path=args.candidate_review_result,
        candidate_alignment_result_path=args.candidate_alignment_result,
        readiness_reassessment_path=args.readiness_reassessment,
        v2_execution_dir=args.v2_execution_dir,
        v2_plan_path=args.v2_plan,
        v1_execution_dir=args.v1_execution_dir,
        stitch_package_dir=args.package_dir,
        full_song_review_result_path=args.full_song_review_result,
        v1_plan_path=args.v1_plan,
        resolved_join_review_result_path=args.resolved_join_review_result,
        publication_readiness_path=args.publication_readiness,
        out=args.out,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
