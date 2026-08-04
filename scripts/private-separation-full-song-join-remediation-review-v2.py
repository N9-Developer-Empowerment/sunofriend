#!/usr/bin/env python3
"""Create the sealed targeted review for the model-free v2 join candidate."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_full_song_join_remediation_review_v2 import (
    _prepare_private_join_remediation_review_v2,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create exactly two anonymous v1-versus-v2 boundary comparisons "
            "and four unchanged v2 patch-edge checks. The fresh owner-only "
            "package contains no complete-song review and cannot select or "
            "publish a candidate."
        )
    )
    parser.add_argument(
        "v2_execution_dir",
        help="completed model-free v2 remediation execution root",
    )
    parser.add_argument(
        "--v2-plan",
        required=True,
        help="exact owner-only v2 remediation plan used by that execution",
    )
    parser.add_argument(
        "--v1-execution-dir",
        required=True,
        help="completed preserved v1 remediation execution root",
    )
    parser.add_argument(
        "--full-song-review-result",
        required=True,
        help="exact private full-song review result used to derive the v2 plan",
    )
    parser.add_argument(
        "--v1-plan",
        required=True,
        help="exact private v1 join-remediation plan used by the authority chain",
    )
    parser.add_argument(
        "--resolved-join-review-result",
        required=True,
        help="resolved private v1 join-remediation review result",
    )
    parser.add_argument(
        "--publication-readiness",
        required=True,
        help="private publication-readiness ledger bound by the v2 plan",
    )
    parser.add_argument(
        "--package-dir",
        required=True,
        help="unchanged full-song stitch package",
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        help="fresh owner-only targeted review package",
    )
    args = parser.parse_args()

    result = _prepare_private_join_remediation_review_v2(
        args.v2_execution_dir,
        v2_plan_path=args.v2_plan,
        v1_execution_dir=args.v1_execution_dir,
        stitch_package_dir=args.package_dir,
        full_song_review_result_path=args.full_song_review_result,
        v1_plan_path=args.v1_plan,
        resolved_join_review_result_path=args.resolved_join_review_result,
        publication_readiness_path=args.publication_readiness,
        out_dir=args.out_dir,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "review_html": result["review_html"],
                "expected_counts": result["expected_counts"],
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
