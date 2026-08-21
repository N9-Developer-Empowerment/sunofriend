#!/usr/bin/env python3
"""Print the no-effects Windows MusicFM-FMA runtime plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.remix_musicfm_fma_runtime import (  # noqa: E402
    create_musicfm_fma_runtime_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admission-plan", type=Path, required=True)
    parser.add_argument("--static-evidence", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    args = parser.parse_args()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    plan = create_musicfm_fma_runtime_plan(
        json.loads(args.admission_plan.read_text(encoding="utf-8")),
        json.loads(args.static_evidence.read_text(encoding="utf-8")),
        json.loads(args.readiness.read_text(encoding="utf-8")),
        repository_commit=commit,
    )
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
