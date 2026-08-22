#!/usr/bin/env python3
"""Create one fixed path-free synthetic vocal-ranker CUDA request."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sunofriend.source_receipt import canonical_json_bytes
from sunofriend.vocal_pairwise_gpu_canary import (
    build_pairwise_gpu_canary_request,
    validate_pairwise_gpu_pretraining_failure,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-commit", required=True)
    parser.add_argument(
        "--execution-attempt-id",
        help="32 lowercase hex characters identifying one authorised execution",
    )
    parser.add_argument(
        "--prior-failure-receipt",
        help="optional path-free receipt proving a prior request never trained",
    )
    parser.add_argument("--out")
    args = parser.parse_args()
    prior_failure = None
    if args.prior_failure_receipt:
        prior_failure = validate_pairwise_gpu_pretraining_failure(
            json.loads(Path(args.prior_failure_receipt).read_text(encoding="utf-8"))
        )
    request = build_pairwise_gpu_canary_request(
        args.repository_commit,
        execution_attempt_id=args.execution_attempt_id,
        prior_failure_receipt=prior_failure,
    )
    if args.out:
        target = Path(args.out).expanduser().absolute()
        if target.exists():
            raise SystemExit(f"output already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(canonical_json_bytes(request))
    else:
        print(json.dumps(request, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
