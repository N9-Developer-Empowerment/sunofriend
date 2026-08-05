#!/usr/bin/env python3
"""Assess reviewed private stems for a future safe import without importing."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_reviewed_output_import_assessment import (
    _assess_reviewed_output_import,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-equivalence", required=True)
    parser.add_argument("--reviewed-export", required=True)
    parser.add_argument("--reviewed-package-dir", required=True)
    parser.add_argument("--candidate-package-report", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _assess_reviewed_output_import(
        args.review_equivalence,
        reviewed_export_path=args.reviewed_export,
        reviewed_package_dir=args.reviewed_package_dir,
        candidate_package_report_path=args.candidate_package_report,
        out=args.out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "assessment": result["assessment"],
                "readiness": result["readiness"],
                "next_action": result["next_action"],
                "permissions": result["permissions"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
