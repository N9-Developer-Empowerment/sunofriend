#!/usr/bin/env python3
"""Read-only verification of one returned synthetic vocal-ranker CUDA run."""

from __future__ import annotations

import argparse
import json

from sunofriend.vocal_pairwise_gpu_verifier import (
    verify_pairwise_gpu_canary_round_trip,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request")
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument(
        "--repository-root",
        help="optional preserved exact-commit checkout; defaults to this repository",
    )
    args = parser.parse_args()
    verification = verify_pairwise_gpu_canary_round_trip(
        args.request,
        artifact_dir=args.artifact_dir,
        repository_root=args.repository_root,
    )
    print(json.dumps(verification, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
