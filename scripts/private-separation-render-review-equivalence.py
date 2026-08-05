#!/usr/bin/env python3
"""Reuse exact human review only for a one-LSB-equivalent PCM24 render."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_private_render_review_equivalence import (
    _bind_private_separation_render_review_equivalence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed-export", required=True)
    parser.add_argument("--reviewed-package-dir", required=True)
    parser.add_argument("--candidate-package-report", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _bind_private_separation_render_review_equivalence(
        args.reviewed_export,
        reviewed_package_dir=args.reviewed_package_dir,
        candidate_package_report_path=args.candidate_package_report,
        out=args.out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "comparisons": result["comparisons"],
                "prior_human_review": {
                    "fresh_audition_of_candidate_exact_bytes": result[
                        "prior_human_review"
                    ]["fresh_audition_of_candidate_exact_bytes"],
                    "review_evidence_applies_under_equivalence_policy": result[
                        "prior_human_review"
                    ]["review_evidence_applies_under_equivalence_policy"],
                    "full_song": result["prior_human_review"]["full_song"],
                },
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
