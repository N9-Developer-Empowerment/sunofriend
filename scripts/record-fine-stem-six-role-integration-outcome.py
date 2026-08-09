#!/usr/bin/env python3
"""Record one completed six-role review without activation or audio access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_fine_stem_integration_outcome import (  # noqa: E402
    build_fine_stem_integration_outcome,
    validate_fine_stem_integration_outcome,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("integration_root", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    root = args.integration_root.resolve(strict=True)
    out = args.out.resolve()
    if out.name != "fine-stem-six-role-integration-outcome-v1" or out.exists():
        raise RuntimeError("fresh exact six-role integration outcome is required")
    report = json.loads(
        (root / "TECHNICAL/INTEGRATION-REPORT.json").read_text(encoding="utf-8")
    )
    review = json.loads(
        (root / "REVIEW/SIX-ROLE-LISTENING.json").read_text(encoding="utf-8")
    )
    outcome = validate_fine_stem_integration_outcome(
        build_fine_stem_integration_outcome(report=report, review=review)
    )
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(tempfile.mkdtemp(prefix=".six-role-outcome-", dir=out.parent))
    try:
        path = staging / "INTEGRATION-OUTCOME.json"
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
