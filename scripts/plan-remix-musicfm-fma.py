#!/usr/bin/env python3
"""Print the no-effects MusicFM-FMA remix feature admission plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from sunofriend.remix_musicfm_fma import (  # noqa: E402
    create_musicfm_fma_admission_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-id", default="musicfm-fma-admission-001")
    args = parser.parse_args()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    plan = create_musicfm_fma_admission_plan(
        plan_id=args.plan_id,
        repository_commit=commit,
    )
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
