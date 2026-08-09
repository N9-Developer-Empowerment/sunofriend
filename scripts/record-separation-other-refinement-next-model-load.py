#!/usr/bin/env python3
"""Validate and bind a completed Mega-53 model-load report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from sunofriend.separation_other_refinement_next_model_load_contract import (
    build_model_load_receipt,
    validate_model_load_report,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--published-root", type=Path, required=True)
    args = parser.parse_args()
    report = validate_model_load_report(
        json.loads(args.report.read_text(encoding="utf-8"))
    )
    receipt = build_model_load_receipt(
        report,
        published_root=args.published_root.resolve(),
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )
    args.receipt.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
