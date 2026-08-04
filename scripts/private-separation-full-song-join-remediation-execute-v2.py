#!/usr/bin/env python3
"""Build a model-free v2 candidate from sealed v1 join evidence."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_full_song_join_remediation_executor_v2 import (
    _execute_private_separation_full_song_join_remediation_v2,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Re-derive one expanded-context v2 plan from its complete private "
            "evidence chain, reuse the sealed v1 worker WAVs without running a "
            "model, and create a separate review-required candidate."
        )
    )
    parser.add_argument("plan", help="sealed model-free v2 plan JSON")
    parser.add_argument("--package-dir", required=True, help="unchanged stitch package")
    parser.add_argument("--full-song-review-result", required=True)
    parser.add_argument("--v1-plan", required=True)
    parser.add_argument("--v1-execution", required=True)
    parser.add_argument("--v1-candidate", required=True)
    parser.add_argument("--resolved-join-review-result", required=True)
    parser.add_argument("--publication-readiness", required=True)
    parser.add_argument("--out-dir", required=True, help="fresh owner-only output root")
    args = parser.parse_args()

    result = _execute_private_separation_full_song_join_remediation_v2(
        args.plan,
        package_dir=args.package_dir,
        full_song_review_result_path=args.full_song_review_result,
        v1_plan_path=args.v1_plan,
        v1_execution_report_path=args.v1_execution,
        v1_candidate_report_path=args.v1_candidate,
        resolved_join_review_result_path=args.resolved_join_review_result,
        publication_readiness_path=args.publication_readiness,
        out_dir=args.out_dir,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "summary": result["summary"],
                "readiness": result["readiness"],
                "permissions": result["permissions"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
