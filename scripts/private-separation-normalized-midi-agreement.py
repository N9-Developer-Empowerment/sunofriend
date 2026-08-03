#!/usr/bin/env python3
"""Recompute one source-bound MIDI agreement pair across private songs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sunofriend._separation_normalized_midi_agreement import (
    MidiAgreementInput,
    _normalize_private_separation_midi_agreement,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_index")
    parser.add_argument("--candidate-method", required=True)
    parser.add_argument("--control-method", required=True)
    parser.add_argument("--control-id", required=True)
    parser.add_argument(
        "--comparison",
        action="append",
        nargs=5,
        metavar=(
            "TRACK_ID",
            "CANDIDATE_REPORT",
            "CONTROL_REPORT",
            "ROLE_MAPPING_REPORT",
            "AUTHORISED_EXCERPT_REPORT",
        ),
        required=True,
        help="repeat for each song; at least two are required",
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _normalize_private_separation_midi_agreement(
        args.evidence_index,
        [
            MidiAgreementInput(
                track_id=track_id,
                candidate_report=Path(candidate),
                control_comparison=Path(control),
                role_mapping=Path(mapping),
                authorised_excerpt=Path(excerpt),
            )
            for track_id, candidate, control, mapping, excerpt in args.comparison
        ],
        candidate_method_family=args.candidate_method,
        control_method_family=args.control_method,
        control_id=args.control_id,
        out=args.out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "observations": result["observations"],
                "publication_gate": result["publication_gate"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
