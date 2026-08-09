#!/usr/bin/env python3
"""Record the completed synth/guitar review portfolio without activation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_fine_stem_canary_outcome import (  # noqa: E402
    build_fine_stem_portfolio_outcome,
    validate_fine_stem_portfolio_outcome,
)


def _documents(root: Path) -> tuple[dict, dict]:
    package = root.resolve(strict=True)
    return (
        json.loads((package / "TECHNICAL/CANARY-REPORT.json").read_text()),
        json.loads((package / "REVIEW/FINE-STEM-LISTENING.json").read_text()),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--synth-root", required=True, type=Path)
    parser.add_argument("--guitar-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.name != "fine-stem-canary-portfolio-v1" or out.exists():
        raise RuntimeError("fresh exact fine-stem portfolio output is required")
    synth_report, synth_review = _documents(args.synth_root)
    guitar_report, guitar_review = _documents(args.guitar_root)
    outcome = validate_fine_stem_portfolio_outcome(
        build_fine_stem_portfolio_outcome(
            synth_report=synth_report,
            synth_review=synth_review,
            guitar_report=guitar_report,
            guitar_review=guitar_review,
        )
    )
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(tempfile.mkdtemp(prefix=".fine-stem-portfolio-", dir=out.parent))
    try:
        path = staging / "PORTFOLIO-OUTCOME.json"
        path.write_text(
            json.dumps(outcome, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        path.chmod(0o600)
        staging.rename(out)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(json.dumps(outcome, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
