#!/usr/bin/env python3
"""Build a sealed blind page for both second-remediation variants."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_candidate_followup_variant_review import (
    _prepare_private_candidate_followup_variant_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan")
    parser.add_argument("--execution-dir", required=True)
    parser.add_argument("--v2-execution-dir", required=True)
    parser.add_argument("--variant-execution-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    result = _prepare_private_candidate_followup_variant_review(
        args.plan,
        execution_dir=args.execution_dir,
        v2_execution_dir=args.v2_execution_dir,
        variant_execution_dir=args.variant_execution_dir,
        out_dir=args.out_dir,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "review_html": result["review_html"],
                "report": result["report"],
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
