#!/usr/bin/env python3
"""Verify an existing exact RoFormer source checkout without importing it."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_roformer_source import (
    _verify_private_roformer_source_tree,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-tree",
        required=True,
        help="Existing local checkout at the registered v1.0.12 revision",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            _verify_private_roformer_source_tree(args.source_tree),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
