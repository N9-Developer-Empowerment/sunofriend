#!/usr/bin/env python3
"""Inspect a staged six-source MLX candidate without loading its model."""

import argparse
import json
from pathlib import Path

from sunofriend.separation_other_refinement_demucs_mlx_inspection import (
    inspect_installation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installation_root", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect_installation(args.installation_root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
