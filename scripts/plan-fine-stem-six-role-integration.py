#!/usr/bin/env python3
"""Print the no-effects six-role integration plan from exact local evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_fine_stem_integration_plan import (  # noqa: E402
    build_fine_stem_six_role_integration_plan,
    validate_fine_stem_six_role_integration_plan,
)


def _pair(root: Path) -> tuple[dict, dict]:
    package = root.resolve(strict=True)
    return (
        json.loads((package / "TECHNICAL/CANARY-REPORT.json").read_text()),
        json.loads((package / "REVIEW/FINE-STEM-LISTENING.json").read_text()),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-outcome", required=True, type=Path)
    parser.add_argument("--synth-root", required=True, type=Path)
    parser.add_argument("--guitar-root", required=True, type=Path)
    args = parser.parse_args()
    synth_report, synth_review = _pair(args.synth_root)
    guitar_report, guitar_review = _pair(args.guitar_root)
    outcome = json.loads(args.portfolio_outcome.resolve(strict=True).read_text())
    plan = validate_fine_stem_six_role_integration_plan(
        build_fine_stem_six_role_integration_plan(
            portfolio_outcome=outcome,
            synth_report=synth_report,
            synth_review=synth_review,
            guitar_report=guitar_report,
            guitar_review=guitar_review,
        )
    )
    print(json.dumps(plan, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
