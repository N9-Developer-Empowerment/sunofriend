#!/usr/bin/env python3
"""Prepare completed private separation output for exact human review."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_private_developer_review_package import (
    _prepare_private_separation_developer_review_package,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--adapter-report", required=True)
    parser.add_argument("--design-report", required=True)
    parser.add_argument("--coverage-report", required=True)
    parser.add_argument("--plan-report", required=True)
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--runtime-launcher", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--companion-root", required=True)
    parser.add_argument("--execution-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    result = _prepare_private_separation_developer_review_package(
        args.request,
        adapter_report_path=args.adapter_report,
        design_report_path=args.design_report,
        coverage_report_path=args.coverage_report,
        plan_report_path=args.plan_report,
        repository_root=args.repository_root,
        runtime_launcher_path=args.runtime_launcher,
        source_root=args.source_root,
        checkpoint_path=args.checkpoint,
        companion_root=args.companion_root,
        execution_dir=args.execution_dir,
        out_dir=args.out_dir,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "review_html": result["review_html"],
                "stages": result["stages"],
                "stages_created_this_invocation": result[
                    "stages_created_this_invocation"
                ],
                "alignment_summary": result["alignment_summary"],
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
