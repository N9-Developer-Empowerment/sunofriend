#!/usr/bin/env python3
"""Verify or resolve a completed private join-remediation blind review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex

from sunofriend._separation_full_song_join_remediation_review_result import (
    _PrivateJsonSnapshotError,
    _resolve_private_join_remediation_review,
    _status_private_join_remediation_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--status",
        type=Path,
        metavar="REVIEWED_JSON",
        help="verify one completed export without opening the answer key",
    )
    action.add_argument(
        "--resolve",
        type=Path,
        metavar="REVIEWED_JSON",
        help="verify one completed export, then resolve its blind identities",
    )
    parser.add_argument(
        "--review-package-dir",
        type=Path,
        required=True,
        help="the original unchanged blind-review package",
    )
    parser.add_argument(
        "--execution-dir",
        type=Path,
        required=True,
        help="the unchanged targeted-remediation execution root",
    )
    parser.add_argument(
        "--stitch-package-dir",
        type=Path,
        required=True,
        help="the unchanged raw full-song stitch package",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="fresh owner-only result JSON; required only with --resolve",
    )
    args = parser.parse_args()
    common = {
        "review_package_dir": args.review_package_dir,
        "execution_dir": args.execution_dir,
        "stitch_package_dir": args.stitch_package_dir,
    }
    try:
        if args.status is not None:
            if args.out is not None:
                parser.error("--out is valid only with --resolve")
            result = _status_private_join_remediation_review(args.status, **common)
            output = _cli_status_summary(result)
        else:
            if args.out is None:
                parser.error("--resolve requires --out")
            result = _resolve_private_join_remediation_review(
                args.resolve,
                out=args.out,
                **common,
            )
            output = _cli_resolution_summary(result)
    except _PrivateJsonSnapshotError as error:
        parser.exit(2, _snapshot_error_message(parser.prog, error))
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


def _cli_status_summary(result: dict[str, object]) -> dict[str, object]:
    return {
        "status": result["status"],
        "reviewed_units": result["reviewed_units"],
        "counts_by_kind": result["counts_by_kind"],
        "audio_references_verified": result["audio_references_verified"],
        "answer_key_opened": result["answer_key_opened"],
        "identity_mapping_revealed": result["identity_mapping_revealed"],
        "verification_claims": result["verification_claims"],
        "verification_limitations": result["verification_limitations"],
        "document_sha256": result["document_sha256"],
    }


def _cli_resolution_summary(result: dict[str, object]) -> dict[str, object]:
    return {
        "status": result["status"],
        "report": result["report"],
        "reviewed_unit_count": result["reviewed_unit_count"],
        "counts_by_kind_and_outcome": result["counts_by_kind_and_outcome"],
        "overall_outcome_counts": result["overall_outcome_counts"],
        "readiness_evidence": result["readiness_evidence"],
        "verification_claims": result["verification_claims"],
        "verification_limitations": result["verification_limitations"],
        "document_sha256": result["document_sha256"],
    }


def _snapshot_error_message(
    program: str,
    error: _PrivateJsonSnapshotError,
) -> str:
    message = f"{program}: error: {error}\n"
    if error.chmod_recommended:
        # macOS /bin/chmod does not accept GNU's ``--`` option terminator.  The
        # snapshot loader has already resolved this to an absolute path, and
        # shlex.join quotes it as one shell argument, so a leading option and
        # shell metacharacters cannot change the command's meaning.
        command = shlex.join(["chmod", "600", str(error.path)])
        message += (
            "Secure this owner-owned, single-link private file and retry. "
            "A safe permission command is:\n"
            f"  {command}\n"
        )
    return message


if __name__ == "__main__":
    raise SystemExit(main())
