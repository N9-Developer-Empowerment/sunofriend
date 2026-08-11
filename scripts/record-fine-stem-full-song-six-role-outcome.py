#!/usr/bin/env python3
"""Record a completed recovered full-song review without opening audio."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_fine_stem_full_song_outcome import (  # noqa: E402
    record_full_song_six_role_outcome,
)


DEFAULT_PLAN = (
    Path.home()
    / ".local/share/sunofriend/separation/evidence"
    / "fine-stem-full-song-six-role-plan-v1/FULL-SONG-SIX-ROLE-PLAN.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recovery_root", type=Path)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    outcome = record_full_song_six_role_outcome(
        args.recovery_root,
        plan_path=args.plan,
        out_dir=args.out,
    )
    print(json.dumps(outcome, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
