#!/usr/bin/env python3
"""Compare separate authorised vocal leaves with their broad MIDI baselines."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_authorised_vocal_leaves import (
    _evaluate_authorised_vocal_leaves,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role-mapping", required=True)
    parser.add_argument("--control-comparison", required=True)
    parser.add_argument("--melroformer-evaluation", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _evaluate_authorised_vocal_leaves(
        args.role_mapping,
        args.control_comparison,
        args.melroformer_evaluation,
        out_dir=args.out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "baselines": result["baselines"],
                "observations": result["observations"],
                "next": result["next"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
