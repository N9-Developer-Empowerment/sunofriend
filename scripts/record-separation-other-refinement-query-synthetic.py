#!/usr/bin/env python3
"""Validate one synthetic report and exclusively write its narrow receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from sunofriend.separation_other_refinement_query_synthetic_report_receipt import (
    build_query_synthetic_receipt,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--published-root", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    receipt = build_query_synthetic_receipt(
        report,
        expected_plan_sha256=args.expected_plan_sha256,
        published_root=args.published_root,
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )
    with args.receipt.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
