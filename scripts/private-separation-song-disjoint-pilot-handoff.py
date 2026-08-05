#!/usr/bin/env python3
"""Create an exact private two-stem handoff after song-disjoint review."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_song_disjoint_private_pilot_handoff import (
    _prepare_private_song_disjoint_pilot_handoff,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-result", required=True)
    parser.add_argument("--reviewed-export", required=True)
    parser.add_argument("--pilot-evidence", required=True)
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    result = _prepare_private_song_disjoint_pilot_handoff(
        args.review_result,
        reviewed_export_path=args.reviewed_export,
        pilot_evidence_path=args.pilot_evidence,
        package_dir=args.package_dir,
        out_dir=args.out_dir,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "handoff_dir": result["handoff_dir"],
                "report": result["report"],
                "primary_roles": result["handoff"]["primary_roles"],
                "diagnostic_roles": result["handoff"]["diagnostic_roles"],
                "publication_ready": result["readiness"]["publication_ready"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
