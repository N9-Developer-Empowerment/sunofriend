#!/usr/bin/env python3
"""Verify tracked official RoFormer release evidence without refreshing it."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_roformer_upstream_evidence import (
    _verify_private_roformer_upstream_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the exact tracked official GitHub evidence for the blocked "
            "BS-RoFormer challenger. This read-only command does not use the "
            "network, open release assets, install packages or run a model."
        )
    )
    parser.add_argument(
        "--repository-root",
        required=True,
        help="Sunofriend repository containing the tracked evidence snapshot",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            _verify_private_roformer_upstream_evidence(args.repository_root),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
