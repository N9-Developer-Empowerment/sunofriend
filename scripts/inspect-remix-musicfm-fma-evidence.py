#!/usr/bin/env python3
"""Inspect exact MusicFM-FMA files without loading model code or weights."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.remix_musicfm_fma_evidence import (  # noqa: E402
    inspect_musicfm_fma_static_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--statistics", type=Path, required=True)
    parser.add_argument("--conformer-config", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    evidence = inspect_musicfm_fma_static_evidence(
        plan,
        checkpoint_path=args.checkpoint,
        statistics_path=args.statistics,
        conformer_config_path=args.conformer_config,
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
