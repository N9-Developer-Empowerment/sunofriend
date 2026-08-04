#!/usr/bin/env python3
"""Run exact review-derived private windows and build a new v2-based candidate."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_candidate_join_remediation_executor import (
    _execute_private_candidate_join_remediation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", help="sealed candidate join-remediation plan")
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
    parser.add_argument("--source-plan", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--runtime-launcher", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--companion-root", required=True)
    parser.add_argument("--device", choices=("gpu", "cpu"), default="gpu")
    parser.add_argument(
        "--all",
        action="store_true",
        help="run every remaining window instead of only the next one",
    )
    args = parser.parse_args()
    result = _execute_private_candidate_join_remediation(
        args.plan,
        v2_review_result_path=args.v2_review_result,
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
        source_plan_path=args.source_plan,
        out_dir=args.out_dir,
        repository_root=args.repository_root,
        runtime_launcher_path=args.runtime_launcher,
        source_root=args.source_root,
        checkpoint_path=args.checkpoint,
        companion_root=args.companion_root,
        device=args.device,
        maximum_windows=None if args.all else 1,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "candidate_report": result["candidate_report_path"],
                "worker_report": result["worker_report"],
                "summary": result["summary"],
                "windows_executed_this_invocation": result[
                    "windows_executed_this_invocation"
                ],
                "permissions": result["permissions"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
