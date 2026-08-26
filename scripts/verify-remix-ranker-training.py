#!/usr/bin/env python3
"""Verify exact remix-ranker evidence without training, audio or network."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sunofriend.remix_ranker_training_verifier import verify_remix_ranker_training
from sunofriend.source_receipt import canonical_json_bytes


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("feature_manifest", type=Path)
    parser.add_argument("result", type=Path)
    parser.add_argument("--feature-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    verification = verify_remix_ranker_training(
        _load(args.request),
        _load(args.snapshot),
        _load(args.feature_manifest),
        _load(args.result),
        feature_root=args.feature_root,
    )
    args.out.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with args.out.open("xb") as handle:
        handle.write(canonical_json_bytes(verification))
    args.out.chmod(0o600)
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
