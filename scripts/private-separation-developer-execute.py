#!/usr/bin/env python3
"""Preflight by default, or explicitly run a sealed private separation request."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_private_developer_execution import (
    _run_private_separation_developer_execution,
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
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--device", choices=("gpu", "cpu"), required=True)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="explicitly run bounded model chunks; omit for read-only preflight",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true")
    group.add_argument("--maximum-chunks", type=int, default=1)
    args = parser.parse_args()
    result = _run_private_separation_developer_execution(
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
        out_dir=args.out_dir,
        device=args.device,
        maximum_chunks=None if args.all else args.maximum_chunks,
        execute=args.execute,
    )
    summary = {
        "schema": result["schema"],
        "status": result["status"],
        "readiness": result["readiness"],
        "permissions": result["permissions"],
    }
    if "proposed_output" in result:
        summary["proposed_output"] = result["proposed_output"]
    if "execution" in result:
        execution = result["execution"]
        summary["execution"] = {
            "output_directory": execution.get("output_directory"),
            "report": execution.get("report"),
            "chunks_executed_this_invocation": execution.get(
                "chunks_executed_this_invocation"
            ),
            "summary": execution.get("summary"),
        }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
