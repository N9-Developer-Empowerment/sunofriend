#!/usr/bin/env python3
"""Compare clean and estimated private Demucs stems through MIDI extraction."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_demucs_midi_evaluation import (
    _evaluate_private_demucs_downstream_midi,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run existing Sunofriend transcribers on the clean synthetic "
            "references and matching private Demucs estimates. This creates "
            "review evidence and inactive MIDI only."
        )
    )
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    result = _evaluate_private_demucs_downstream_midi(
        args.fixture,
        args.experiment,
        out_dir=args.out,
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
                        "comparison": evidence["comparison"],
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
