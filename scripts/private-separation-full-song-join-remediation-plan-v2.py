#!/usr/bin/env python3
"""Plan a model-free expanded-context repatch for equivalent v1 joins."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_full_song_join_remediation_plan_v2 import (
    _plan_private_separation_full_song_join_remediation_v2,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the raw stitch, v1 join-remediation chain, resolved human "
            "review and open readiness ledger, then plan a wider model-free "
            "repatch only for equivalent boundary-role outcomes."
        )
    )
    parser.add_argument("package_dir", help="unchanged private full-song stitch")
    parser.add_argument("--full-song-review-result", required=True)
    parser.add_argument("--v1-plan", required=True)
    parser.add_argument("--v1-execution", required=True)
    parser.add_argument("--v1-candidate", required=True)
    parser.add_argument("--resolved-join-review-result", required=True)
    parser.add_argument("--publication-readiness", required=True)
    parser.add_argument("--out", required=True, help="fresh owner-only v2 plan JSON")
    args = parser.parse_args()

    result = _plan_private_separation_full_song_join_remediation_v2(
        args.package_dir,
        full_song_review_result_path=args.full_song_review_result,
        v1_plan_path=args.v1_plan,
        v1_execution_report_path=args.v1_execution,
        v1_candidate_report_path=args.v1_candidate,
        resolved_join_review_result_path=args.resolved_join_review_result,
        publication_readiness_path=args.publication_readiness,
        out=args.out,
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
