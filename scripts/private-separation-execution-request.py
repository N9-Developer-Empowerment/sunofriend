#!/usr/bin/env python3
"""Bind one authorised song plan to the private adapter without inference."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_private_execution_request import (
    _build_private_separation_execution_request,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter-report", required=True)
    parser.add_argument("--design-report", required=True)
    parser.add_argument("--coverage-report", required=True)
    parser.add_argument("--plan-report", required=True)
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--runtime-launcher", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--companion-root", required=True)
    parser.add_argument("--device", choices=("gpu", "cpu"), required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _build_private_separation_execution_request(
        args.adapter_report,
        design_report_path=args.design_report,
        coverage_report_path=args.coverage_report,
        plan_report_path=args.plan_report,
        repository_root=args.repository_root,
        runtime_launcher_path=args.runtime_launcher,
        source_root=args.source_root,
        checkpoint_path=args.checkpoint,
        companion_root=args.companion_root,
        device=args.device,
        out=args.out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "plan_report": result["plan_report"],
                "request": {
                    key: result["request"][key]
                    for key in (
                        "track_id",
                        "track_title",
                        "rights_authority",
                        "candidate_id",
                        "device",
                        "primary_roles",
                        "diagnostic_roles",
                        "canonical_clock",
                        "chunking",
                    )
                },
                "readiness": result["readiness"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
