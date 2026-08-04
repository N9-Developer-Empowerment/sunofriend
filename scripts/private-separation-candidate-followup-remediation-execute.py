#!/usr/bin/env python3
"""Run shifted-context follow-up workers and build two unranked candidates."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_candidate_followup_remediation_executor import (
    _execute_private_candidate_followup_remediation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan")
    parser.add_argument("--targeted-review-result", required=True)
    parser.add_argument("--reviewed-export", required=True)
    parser.add_argument("--targeted-review-package-dir", required=True)
    parser.add_argument("--execution-dir", required=True)
    parser.add_argument("--v2-execution-dir", required=True)
    parser.add_argument("--package-dir", required=True)
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
        help="run all remaining shifted windows instead of only the next one",
    )
    args = parser.parse_args()
    result = _execute_private_candidate_followup_remediation(
        args.plan,
        targeted_review_result_path=args.targeted_review_result,
        reviewed_export_path=args.reviewed_export,
        targeted_review_package_dir=args.targeted_review_package_dir,
        execution_dir=args.execution_dir,
        v2_execution_dir=args.v2_execution_dir,
        stitch_package_dir=args.package_dir,
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
