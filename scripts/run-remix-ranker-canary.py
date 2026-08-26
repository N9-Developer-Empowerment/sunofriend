#!/usr/bin/env python3
"""Run and print the fixed synthetic-only remix-ranker canary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sunofriend.remix_ranker_canary import (
    build_remix_ranker_canary_request,
    run_remix_ranker_canary,
)
from sunofriend.source_receipt import canonical_json_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="create a fresh request/result evidence directory",
    )
    args = parser.parse_args()
    request = build_remix_ranker_canary_request()
    result = run_remix_ranker_canary(request)
    if args.out_dir is None:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    args.out_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, document in (("request.json", request), ("result.json", result)):
        path = args.out_dir / name
        with path.open("xb") as handle:
            handle.write(canonical_json_bytes(document))
        path.chmod(0o600)
    print(args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
