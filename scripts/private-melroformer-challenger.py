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
            "optionally hash and statically inspect the already-present exact "
            "Safetensors file; this does not deserialize tensors or permit execution"
        ),
    )
    parser.add_argument(
        "--source-root",
        help="optionally verify the materialised exact audited MLX-Audio source tree",
    )
    parser.add_argument(
        "--companion-root",
        help="optionally verify the checkpoint config.json and LICENSE directory",
    )
    args = parser.parse_args()
    result = _build_private_melroformer_challenger_plan(
        checkpoint_path=args.checkpoint,
        source_root=args.source_root,
        companion_root=args.companion_root,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
