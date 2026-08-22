#!/usr/bin/env python3
"""Read-only verification of one returned C0 request, result and artifact set."""

from __future__ import annotations

import argparse
import json

from sunofriend.gpu_canary_verifier import verify_c0_canary_round_trip


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request")
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument(
        "--repository-root",
        help="optional preserved checkout to validate; defaults to this repository",
    )
    args = parser.parse_args()
    verification = verify_c0_canary_round_trip(
        args.request,
        artifact_dir=args.artifact_dir,
        repository_root=args.repository_root,
    )
    print(json.dumps(verification, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
