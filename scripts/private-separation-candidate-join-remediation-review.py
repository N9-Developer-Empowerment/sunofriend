#!/usr/bin/env python3
"""Create a blind v2-control versus review-derived follow-up review."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_candidate_join_remediation_review import (
    _prepare_private_candidate_join_remediation_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("execution_dir", help="completed follow-up execution root")
    parser.add_argument("--v2-execution-dir", required=True, help="immutable v2 control root")
    parser.add_argument("--out-dir", required=True, help="fresh owner-only review package")
    args = parser.parse_args()
    result = _prepare_private_candidate_join_remediation_review(
        args.execution_dir,
        v2_execution_dir=args.v2_execution_dir,
        out_dir=args.out_dir,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "review_html": result["review_html"],
                "expected_counts": result["expected_counts"],
                "permissions": result["permissions"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
