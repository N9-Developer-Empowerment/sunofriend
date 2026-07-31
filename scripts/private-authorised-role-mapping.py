#!/usr/bin/env python3
"""Build review-only broad role groups from an authorised excerpt."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_authorised_role_mapping import (
    _map_authorised_excerpt_roles,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create common-rate broad-role auditions from provider excerpts "
            "and compare every proposed group to every local HTDemucs role. "
            "Names propose groups; audio evidence ranks them; nothing is selected."
        )
    )
    parser.add_argument("--excerpt-report", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _map_authorised_excerpt_roles(
        args.excerpt_report,
        out_dir=args.out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "observations": result["observations"],
                "proposed_role_observations": {
                    pack: evidence["proposed_role_observations"]
                    for pack, evidence in result[
                        "comparisons_to_local_htdemucs"
                    ].items()
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
