#!/usr/bin/env python3
"""Verify retained MusicFM synthetic artifacts without model loading."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.remix_musicfm_canary import (  # noqa: E402
    verify_musicfm_synthetic_canary_round_trip,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    verification = verify_musicfm_synthetic_canary_round_trip(args.output_dir, request)
    print(json.dumps(verification, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
