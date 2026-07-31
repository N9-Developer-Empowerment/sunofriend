#!/usr/bin/env python3
"""Run synthetic Demucs pairs through production MIDI refinement."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_demucs_refinement_evaluation import (
    _evaluate_private_demucs_production_refinement,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run clean and estimated synthetic bass, drums and other stems "
            "through production refine_stem, rendering and independent MIDI "
            "evaluation. Results remain private and inactive."
        )
    )
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-iterations", type=int, default=30)
    args = parser.parse_args()

    result = _evaluate_private_demucs_production_refinement(
        args.fixture,
        args.experiment,
        out_dir=args.out,
        max_iterations=args.max_iterations,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "roles": {
                    role: {
                        "reference_note_count": evidence["reference"]["note_count"],
                        "estimate_note_count": evidence["estimate"]["note_count"],
                        "comparison": evidence[
                            "clean_to_estimate_midi_comparison"
                        ],
                    }
                    for role, evidence in result["roles"].items()
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
