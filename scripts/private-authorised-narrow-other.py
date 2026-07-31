#!/usr/bin/env python3
"""Compare provider leaf stems inside an authorised broad other group."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_authorised_narrow_other import (
    _compare_authorised_other_leaves,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Stage every provider leaf provisionally assigned to broad other, "
            "then calculate all cross-provider audio rankings. Labels are "
            "observations only; this command never accepts or activates a mapping."
        )
    )
    parser.add_argument("--role-mapping", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _compare_authorised_other_leaves(
        args.role_mapping,
        out_dir=args.out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "observations": result["observations"],
                "same_label_counterpart_observations": result[
                    "same_label_counterpart_observations"
                ],
                "semantic_counterpart_observations": result[
                    "semantic_counterpart_observations"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
