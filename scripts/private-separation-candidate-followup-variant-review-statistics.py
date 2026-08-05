#!/usr/bin/env python3
"""Describe uncertainty in one resolved private follow-up variant review."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_candidate_followup_variant_review_statistics import (
    _analyze_private_candidate_followup_variant_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant-review-result", required=True)
    parser.add_argument("--reviewed-export", required=True)
    parser.add_argument("--variant-review-package-dir", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--execution-dir", required=True)
    parser.add_argument("--v2-execution-dir", required=True)
    parser.add_argument("--variant-execution-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _analyze_private_candidate_followup_variant_review(
        args.variant_review_result,
        reviewed_export_path=args.reviewed_export,
        variant_review_package_dir=args.variant_review_package_dir,
        plan_path=args.plan,
        execution_dir=args.execution_dir,
        v2_execution_dir=args.v2_execution_dir,
        variant_execution_dir=args.variant_execution_dir,
        out=args.out,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
