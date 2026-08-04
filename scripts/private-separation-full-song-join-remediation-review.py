#!/usr/bin/env python3
"""Create the private blind review for targeted join-remediation candidates."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_full_song_join_remediation_review import (
    _prepare_private_join_remediation_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create a fresh blind raw-versus-remediated review covering every "
            "target boundary, both edges of every patch and all complete roles."
        )
    )
    parser.add_argument("execution_dir", help="completed remediation execution root")
    parser.add_argument("--package-dir", required=True, help="unchanged raw stitch package")
    parser.add_argument("--out-dir", required=True, help="fresh owner-only review package")
    args = parser.parse_args()
    result = _prepare_private_join_remediation_review(
        args.execution_dir,
        package_dir=args.package_dir,
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
