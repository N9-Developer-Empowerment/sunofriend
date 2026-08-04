#!/usr/bin/env python3
"""Build the gated full-song and all-boundary follow-up review package."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_candidate_followup_full_song_review import (
    _build_private_candidate_followup_full_song_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targeted-review-result", required=True)
    parser.add_argument("--reviewed-export", required=True)
    parser.add_argument("--targeted-review-package-dir", required=True)
    parser.add_argument("--execution-dir", required=True)
    parser.add_argument("--v2-execution-dir", required=True)
    parser.add_argument("--stitch-package-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    result = _build_private_candidate_followup_full_song_review(
        args.targeted_review_result,
        reviewed_export_path=args.reviewed_export,
        targeted_review_package_dir=args.targeted_review_package_dir,
        execution_dir=args.execution_dir,
        v2_execution_dir=args.v2_execution_dir,
        stitch_package_dir=args.stitch_package_dir,
        out_dir=args.out_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
