#!/usr/bin/env python3
"""Catalogue sealed private separation evidence across songs and methods."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sunofriend._separation_cross_song_evidence_index import (
    EvidenceInput,
    _index_cross_song_separation_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence",
        action="append",
        nargs=4,
        metavar=("TRACK_ID", "METHOD_FAMILY", "KIND", "REPORT_JSON"),
        required=True,
        help="repeat for each sealed report",
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _index_cross_song_separation_evidence(
        [
            EvidenceInput(
                track_id=track_id,
                method_family=method_family,
                evidence_kind=kind,
                report=Path(report),
            )
            for track_id, method_family, kind, report in args.evidence
        ],
        out=args.out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                **result["summary"],
                "method_ranked_or_selected": result["policy"][
                    "method_ranked_or_selected"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
