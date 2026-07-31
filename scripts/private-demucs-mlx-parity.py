#!/usr/bin/env python3
"""Plan or run private same-checkpoint Demucs-MLX parity."""

from __future__ import annotations

import argparse
import json
import os

from sunofriend._separation_demucs_mlx_parity import (
    _build_private_demucs_mlx_parity_plan,
    _run_private_demucs_mlx_parity,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare sealed PyTorch htdemucs_6s experiments with an in-memory "
            "MLX conversion of the same hash-pinned checkpoint. This command "
            "never installs packages, downloads weights or activates a separator."
        )
    )
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--reference-run", action="append", default=[])
    parser.add_argument("--out")
    parser.add_argument("--checkpoint")
    parser.add_argument("--python")
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    args = parser.parse_args()

    if args.plan:
        if args.reference_run or args.out:
            parser.error("--plan does not accept --reference-run or --out")
        result = _build_private_demucs_mlx_parity_plan(
            checkpoint_path=args.checkpoint,
            python=args.python,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if not args.reference_run or not args.out:
        parser.error("a run requires --reference-run and --out")
    if os.environ.get("SUNOFRIEND_ACCEPT_DEMUCS_MLX_PRIVATE_EVALUATION") != "1":
        raise SystemExit(
            "Set SUNOFRIEND_ACCEPT_DEMUCS_MLX_PRIVATE_EVALUATION=1 only after "
            "reviewing this command's --plan output and separately approving "
            "the optional runtime installation."
        )
    result = _run_private_demucs_mlx_parity(
        args.reference_run,
        out_dir=args.out,
        checkpoint_path=args.checkpoint,
        python=args.python,
        timeout_seconds=args.timeout_seconds,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "summary": result["summary"],
                "permissions": result["permissions"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
