#!/usr/bin/env python3
"""Bind automatic evidence for one source-distinct private separation pilot."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_song_disjoint_private_pilot import (
    _bind_song_disjoint_private_pilot_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pragmatic-authorization", required=True)
    parser.add_argument("--reference-v2-execution", required=True)
    parser.add_argument("--pilot-request", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--execution", required=True)
    parser.add_argument("--request-completion-binding", required=True)
    parser.add_argument("--stitch-package-dir", required=True)
    parser.add_argument("--alignment-result", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _bind_song_disjoint_private_pilot_evidence(
        args.pragmatic_authorization,
        reference_v2_execution_path=args.reference_v2_execution,
        pilot_request_path=args.pilot_request,
        plan_report_path=args.plan,
        execution_report_path=args.execution,
        request_completion_binding_path=args.request_completion_binding,
        stitch_package_dir=args.stitch_package_dir,
        alignment_result_path=args.alignment_result,
        out=args.out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "review_html": result["review_html"],
                "source_distinction": result["source_distinction"],
                "automatic_execution": result["automatic_execution"],
                "human_review": result["human_review"],
                "readiness": result["readiness"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
