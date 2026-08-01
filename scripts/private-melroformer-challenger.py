#!/usr/bin/env python3
"""Print the fail-closed plan for the private Kim Vocal 2 MLX candidate."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_melroformer_challenger_plan import (
    _build_private_melroformer_challenger_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect Sunofriend's exact MLX MelBand-RoFormer Kim Vocal 2 "
            "candidate plan. This command never downloads weights, installs "
            "packages, imports a model, starts a worker or activates a separator."
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
            "optionally hash an already-present local Safetensors file; this "
            "does not inspect tensors or permit execution"
        ),
    )
    args = parser.parse_args()
    result = _build_private_melroformer_challenger_plan(
        checkpoint_path=args.checkpoint
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
