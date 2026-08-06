#!/usr/bin/env python3
"""Create model-free PCM24 evidence for the Studio other-refinement contract."""

from __future__ import annotations

import argparse
import json

from sunofriend.separation_other_refinement import (
    create_other_refinement_synthetic_fixture,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="fresh local output directory")
    parser.add_argument(
        "--target",
        choices=("guitar", "keys"),
        default="guitar",
        help="one requested target to preserve beside the residual",
    )
    args = parser.parse_args()
    result = create_other_refinement_synthetic_fixture(
        args.out,
        target_id=args.target,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
