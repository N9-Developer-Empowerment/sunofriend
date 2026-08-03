#!/usr/bin/env python3
"""Project completed human phrase reviews onto normalized song evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sunofriend._separation_human_listening_coverage import (
    HumanListeningInput,
    _project_private_separation_human_listening_coverage,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("normalized_midi_agreement")
    parser.add_argument(
        "--review",
        action="append",
        nargs=2,
        metavar=("TRACK_ID", "REVIEW_RESOLUTION"),
        required=True,
        help="repeat for every completed phrase-level human review",
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _project_private_separation_human_listening_coverage(
        args.normalized_midi_agreement,
        [
            HumanListeningInput(
                track_id=track_id,
                review_resolution=Path(review_resolution),
            )
            for track_id, review_resolution in args.review
        ],
        out=args.out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "coverage": result["coverage"],
                "publication_gate": result["publication_gate"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
