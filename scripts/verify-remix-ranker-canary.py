#!/usr/bin/env python3
"""Independently recompute and verify synthetic remix-ranker JSON evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sunofriend.remix_ranker_verifier import verify_remix_ranker_canary
from sunofriend.source_receipt import canonical_json_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request")
    parser.add_argument("result")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    result = json.loads(Path(args.result).read_text(encoding="utf-8"))
    verification = verify_remix_ranker_canary(request, result)
    if args.out is None:
        print(json.dumps(verification, indent=2, sort_keys=True))
        return 0
    args.out.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with args.out.open("xb") as handle:
        handle.write(canonical_json_bytes(verification))
    args.out.chmod(0o600)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
