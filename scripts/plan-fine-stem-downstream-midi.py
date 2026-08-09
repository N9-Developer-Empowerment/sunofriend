#!/usr/bin/env python3
"""Write a bound downstream-MIDI plan without opening private audio."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_fine_stem_midi_plan import (  # noqa: E402
    build_fine_stem_midi_plan,
    validate_fine_stem_midi_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("integration_root", type=Path)
    parser.add_argument("outcome", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    root = args.integration_root.resolve(strict=True)
    outcome_path = args.outcome.resolve(strict=True)
    out = args.out.resolve()
    if out.name != "fine-stem-downstream-midi-plan-v1" or out.exists():
        raise RuntimeError("fresh exact downstream-MIDI plan root is required")
    report = json.loads(
        (root / "TECHNICAL/INTEGRATION-REPORT.json").read_text(encoding="utf-8")
    )
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    plan = validate_fine_stem_midi_plan(
        build_fine_stem_midi_plan(report=report, outcome=outcome)
    )
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(tempfile.mkdtemp(prefix=".fine-stem-midi-plan-", dir=out.parent))
    try:
        path = staging / "MIDI-PLAN.json"
        path.write_text(
            json.dumps(plan, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        path.chmod(0o600)
        staging.rename(out)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(json.dumps(plan, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
