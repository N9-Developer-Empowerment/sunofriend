#!/usr/bin/env python3
"""Prepare the two source-only cases needed to complete fine-stem presence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_target_presence_addition_plan import (  # noqa: E402
    build_target_presence_addition_plan,
)
from sunofriend.separation_target_presence_review import (  # noqa: E402
    prepare_addition_presence_review,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-rights", action="store_true")
    args = parser.parse_args()
    if args.plan:
        if args.execute or args.confirm_rights or args.source_root or args.out:
            parser.error("--plan has no audio or output arguments")
        print(
            json.dumps(
                build_target_presence_addition_plan(), indent=2, sort_keys=True
            )
        )
        return 0
    if not args.execute or not args.confirm_rights:
        parser.error("preparation requires --execute --confirm-rights")
    if args.source_root is None or args.out is None:
        parser.error("preparation requires --source-root and --out")
    manifest = prepare_addition_presence_review(
        source_root=args.source_root, out=args.out
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
