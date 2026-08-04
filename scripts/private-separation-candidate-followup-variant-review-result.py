#!/usr/bin/env python3
"""Verify or resolve a completed blind second-remediation variant review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex

from sunofriend._separation_candidate_followup_variant_review_result import (
    _resolve_private_candidate_followup_variant_review,
    _status_private_candidate_followup_variant_review,
)
from sunofriend._separation_full_song_join_remediation_review_result import (
    _PrivateJsonSnapshotError,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--status", type=Path, metavar="REVIEWED_JSON")
    action.add_argument("--resolve", type=Path, metavar="REVIEWED_JSON")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--review-package-dir", type=Path, required=True)
    parser.add_argument("--execution-dir", type=Path, required=True)
    parser.add_argument("--v2-execution-dir", type=Path, required=True)
    parser.add_argument("--variant-execution-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    common = {
        "plan_path": args.plan,
        "review_package_dir": args.review_package_dir,
        "execution_dir": args.execution_dir,
        "v2_execution_dir": args.v2_execution_dir,
        "variant_execution_dir": args.variant_execution_dir,
    }
    try:
        if args.status is not None:
            if args.out is not None:
                parser.error("--out is valid only with --resolve")
            result = _status_private_candidate_followup_variant_review(
                args.status, **common
            )
            output = {
                key: result[key]
                for key in (
                    "status",
                    "reviewed_units",
                    "counts_by_kind",
                    "audio_references_verified",
                    "unique_audio_files_verified",
                    "pcm24_identical_short_pairs",
                    "pcm24_identical_complete_song_pairs",
                    "answer_key_opened",
                    "identity_mapping_revealed",
                    "verification_claims",
                    "document_sha256",
                )
            }
        else:
            if args.out is None:
                parser.error("--resolve requires --out")
            result = _resolve_private_candidate_followup_variant_review(
                args.resolve, out=args.out, **common
            )
            output = {
                key: result[key]
                for key in (
                    "status",
                    "report",
                    "reviewed_unit_count",
                    "pcm24_identical_short_pairs",
                    "pcm24_identical_complete_song_pairs",
                    "counts_by_kind_and_outcome",
                    "overall_outcome_counts",
                    "fresh_all_boundary_review_eligible_variant_ids",
                    "readiness_evidence",
                    "verification_claims",
                    "document_sha256",
                )
            }
    except _PrivateJsonSnapshotError as error:
        message = f"{parser.prog}: error: {error}\n"
        if error.chmod_recommended:
            message += (
                "Secure this private file and retry:\n  "
                + shlex.join(["chmod", "600", str(error.path)])
                + "\n"
            )
        parser.exit(2, message)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
