#!/usr/bin/env python3
"""Compose exact target-present reviews into the bounded canary cohort."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_target_presence_qualification import (  # noqa: E402
    compose_qualified_presence_package,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", action="append", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    manifest = compose_qualified_presence_package(
        source_roots=args.source_root, out=args.out
    )
    print(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
