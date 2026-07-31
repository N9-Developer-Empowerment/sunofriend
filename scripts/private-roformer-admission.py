#!/usr/bin/env python3
"""Verify exact RoFormer code/runtime planning evidence without enabling it."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_roformer_admission import (
    _build_private_roformer_admission,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bind an exact BS-RoFormer source checkout to Sunofriend's tracked "
            "runtime and licence evidence. This read-only command does not "
            "open weights, install packages, import a model or start a worker."
        )
    )
    parser.add_argument(
        "--repository-root",
        required=True,
        help="Sunofriend repository containing the exact tracked evidence",
    )
    parser.add_argument(
        "--source-tree",
        required=True,
        help="existing exact upstream v1.0.12 source checkout",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            _build_private_roformer_admission(
                repository_root=args.repository_root,
                source_tree=args.source_tree,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
