#!/usr/bin/env python3
"""Compare one private six-source run with authorised provider leaves."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_demucs_six_source_evaluation import (
    _evaluate_private_demucs_six_source_provider_midi,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create private audio/MIDI comparisons between guitar, piano, other "
            "and residual outputs from one six-source run and every provider "
            "leaf in one exact authorised narrow-other report."
        )
    )
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--narrow-other", required=True)
    parser.add_argument("--bpm", type=float, required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _evaluate_private_demucs_six_source_provider_midi(
        args.experiment,
        args.narrow_other,
        bpm=args.bpm,
        out_dir=args.out,
    )
    summary = {
        role: {
            "audio_nearest_leaf_id": evidence["audio_nearest_leaf_id"],
            "midi_nearest_leaf_id": evidence["midi_nearest_leaf_id"],
            "same_nearest_leaf": evidence["same_nearest_leaf"],
        }
        for role, evidence in result["rankings"].items()
    }
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "review": result["review"],
                "nearest_provider_leaves": summary,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
