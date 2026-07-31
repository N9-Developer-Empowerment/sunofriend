#!/usr/bin/env python3
"""Print the fail-closed plan for one exact private RoFormer challenger."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_roformer_challenger_plan import (
    _build_private_roformer_challenger_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect Sunofriend's exact BS-RoFormer v1.0.12 candidate plan. "
            "This command never downloads weights, installs packages, imports "
            "a model, starts a worker or activates a separator."
        )
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        required=True,
        help="print the read-only candidate and its unresolved blockers",
    )
    parser.add_argument(
        "--checkpoint",
        help=(
            "optionally hash an already-present local candidate file; this "
            "does not establish official identity or permit execution"
        ),
    )
    args = parser.parse_args()
    result = _build_private_roformer_challenger_plan(checkpoint_path=args.checkpoint)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
