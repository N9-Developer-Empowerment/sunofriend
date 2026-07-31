#!/usr/bin/env python3
"""Run the copyright-safe private HTDemucs four-stem development canary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sunofriend._separation_demucs_demo_fixture import (
    _create_private_demucs_demo_fixture,
)
from sunofriend._separation_demucs_demo_evaluation import (
    _evaluate_private_demucs_demo_run,
)
from sunofriend._separation_demucs_private_run import (
    _run_private_demucs_four_stem_experiment,
)
from sunofriend.ai_runtime import resolve_ai_python, resolve_demucs_model


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create Sunofriend's copyright-safe 8-second mix and run the "
            "already-installed, hash-pinned private HTDemucs experiment. "
            "This never installs or downloads a model."
        )
    )
    parser.add_argument("--fixture-out", required=True)
    parser.add_argument("--run-out", required=True)
    parser.add_argument("--evaluation-out", required=True)
    parser.add_argument("--checkpoint")
    parser.add_argument("--python")
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    args = parser.parse_args()

    fixture = _create_private_demucs_demo_fixture(args.fixture_out)
    checkpoint = resolve_demucs_model(args.checkpoint)
    executable = resolve_ai_python(args.python)
    result = _run_private_demucs_four_stem_experiment(
        fixture["mixture_path"],
        out_dir=args.run_out,
        checkpoint_path=checkpoint,
        end_seconds=8.0,
        python=executable,
        timeout_seconds=args.timeout_seconds,
    )
    evaluation = _evaluate_private_demucs_demo_run(
        fixture["manifest"],
        result["report"],
        out_dir=args.evaluation_out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "fixture": fixture["manifest"],
                "experiment": result["report"],
                "evaluation": evaluation["report"],
                "estimated_stems": {
                    role: str(
                        Path(args.run_out).expanduser().absolute() / evidence["path"]
                    )
                    for role, evidence in result["estimated_stems"].items()
                },
                "reconstruction": result["additive_accounting"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
