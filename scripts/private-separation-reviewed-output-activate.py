#!/usr/bin/env python3
"""Explicitly activate exact reviewed private stems for bounded validation."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_reviewed_output_activation import (
    _activate_reviewed_output,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--import-assessment", required=True)
    parser.add_argument("--review-equivalence", required=True)
    parser.add_argument("--reviewed-export", required=True)
    parser.add_argument("--reviewed-package-dir", required=True)
    parser.add_argument("--candidate-package-report", required=True)
    parser.add_argument(
        "--confirm-reviewed-stems-useful",
        action="store_true",
        help="Confirm the bound human review found all complete-song roles useful.",
    )
    args = parser.parse_args()
    result = _activate_reviewed_output(
        args.project_root,
        assessment_path=args.import_assessment,
        equivalence_path=args.review_equivalence,
        reviewed_export_path=args.reviewed_export,
        reviewed_package_dir=args.reviewed_package_dir,
        candidate_package_report_path=args.candidate_package_report,
        confirm_reviewed_stems_useful=args.confirm_reviewed_stems_useful,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
