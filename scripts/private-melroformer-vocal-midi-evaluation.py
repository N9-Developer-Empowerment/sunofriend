#!/usr/bin/env python3
"""Evaluate one verified private MelRoFormer vocal with unchanged MIDI logic."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_melroformer_midi_evaluation import (
    _evaluate_private_melroformer_vocal_midi,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-observation", required=True)
    parser.add_argument("--control-comparison", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _evaluate_private_melroformer_vocal_midi(
        args.worker_observation,
        args.control_comparison,
        out_dir=args.out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "candidate_note_count": result["candidate"]["primary"][
                    "note_count"
                ],
                "comparisons_to_existing_controls": result[
                    "comparisons_to_existing_controls"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
