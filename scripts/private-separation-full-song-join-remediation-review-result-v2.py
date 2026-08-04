#!/usr/bin/env python3
"""Verify or resolve one completed targeted v2 join-remediation review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex

from sunofriend._separation_full_song_join_remediation_review_result import (
    _PrivateJsonSnapshotError,
)
from sunofriend._separation_full_song_join_remediation_review_result_v2 import (
    _resolve_private_join_remediation_review_v2,
    _status_private_join_remediation_review_v2,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--status", type=Path, metavar="REVIEWED_JSON")
    action.add_argument("--resolve", type=Path, metavar="REVIEWED_JSON")
    parser.add_argument("--review-package-dir", type=Path, required=True)
    parser.add_argument("--v2-execution-dir", type=Path, required=True)
    parser.add_argument("--v2-plan", type=Path, required=True)
    parser.add_argument("--v1-execution-dir", type=Path, required=True)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--full-song-review-result", type=Path, required=True)
    parser.add_argument("--v1-plan", type=Path, required=True)
    parser.add_argument("--resolved-join-review-result", type=Path, required=True)
    parser.add_argument("--publication-readiness", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    common = {
        "review_package_dir": args.review_package_dir,
        "v2_execution_dir": args.v2_execution_dir,
        "v2_plan_path": args.v2_plan,
        "v1_execution_dir": args.v1_execution_dir,
        "stitch_package_dir": args.package_dir,
        "full_song_review_result_path": args.full_song_review_result,
        "v1_plan_path": args.v1_plan,
        "resolved_join_review_result_path": args.resolved_join_review_result,
        "publication_readiness_path": args.publication_readiness,
    }
    try:
        if args.status is not None:
            if args.out is not None:
                parser.error("--out is valid only with --resolve")
            result = _status_private_join_remediation_review_v2(args.status, **common)
            output = _cli_status_summary(result)
        else:
            if args.out is None:
                parser.error("--resolve requires --out")
            result = _resolve_private_join_remediation_review_v2(
                args.resolve, out=args.out, **common
            )
            output = _cli_resolution_summary(result)
    except _PrivateJsonSnapshotError as error:
        parser.exit(2, _snapshot_error_message(parser.prog, error))
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


def _cli_status_summary(result: dict[str, object]) -> dict[str, object]:
    return {
        key: result[key]
        for key in (
            "status",
            "reviewed_units",
            "counts_by_kind",
            "audio_references_verified",
            "answer_key_opened",
            "identity_mapping_revealed",
            "verification_claims",
            "verification_limitations",
            "document_sha256",
        )
    }


def _cli_resolution_summary(result: dict[str, object]) -> dict[str, object]:
    return {
        key: result[key]
        for key in (
            "status",
            "report",
            "reviewed_unit_count",
            "counts",
            "readiness_evidence",
            "verification_claims",
            "verification_limitations",
            "document_sha256",
        )
    }


def _snapshot_error_message(program: str, error: _PrivateJsonSnapshotError) -> str:
    message = f"{program}: error: {error}\n"
    if error.chmod_recommended:
        command = shlex.join(["chmod", "600", str(error.path)])
        message += (
            "Secure this owner-owned, single-link private file and retry. "
            "A safe permission command is:\n"
            f"  {command}\n"
        )
    return message


if __name__ == "__main__":
    raise SystemExit(main())
