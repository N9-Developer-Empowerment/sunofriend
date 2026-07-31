#!/usr/bin/env python3
"""Run one private, inactive HTDemucs six-source development canary."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sunofriend._separation_demucs_private_run import (
    _run_private_demucs_six_source_experiment,
)
from sunofriend.ai_runtime import resolve_ai_python, resolve_demucs_6s_model


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run an already-installed, hash-pinned htdemucs_6s checkpoint on "
            "one bounded private excerpt. This never installs or downloads a "
            "model and creates no product, source-graph or Workbench result."
        )
    )
    parser.add_argument("audio")
    parser.add_argument("--out", required=True)
    parser.add_argument("--checkpoint")
    parser.add_argument("--python")
    parser.add_argument("--start-seconds", type=float, default=0.0)
    parser.add_argument("--end-seconds", type=float)
    parser.add_argument("--overlap", type=float, default=0.25)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    args = parser.parse_args()

    if os.environ.get("SUNOFRIEND_ACCEPT_DEMUCS_6S_PRIVATE_EVALUATION") != "1":
        raise SystemExit(
            "Set SUNOFRIEND_ACCEPT_DEMUCS_6S_PRIVATE_EVALUATION=1 only after "
            "accepting the private checkpoint notice in "
            "scripts/setup-demucs-6s-model.sh"
        )

    result = _run_private_demucs_six_source_experiment(
        args.audio,
        out_dir=args.out,
        checkpoint_path=resolve_demucs_6s_model(args.checkpoint),
        start_seconds=args.start_seconds,
        end_seconds=args.end_seconds,
        overlap=args.overlap,
        python=resolve_ai_python(args.python),
        timeout_seconds=args.timeout_seconds,
    )
    root = Path(args.out).expanduser().absolute()
    print(
        json.dumps(
            {
                "status": result["status"],
                "experiment": result["report"],
                "estimated_stems": {
                    role: str(root / evidence["path"])
                    for role, evidence in result["estimated_stems"].items()
                },
                "reconstruction": result["additive_accounting"],
                "permissions": result["permissions"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
