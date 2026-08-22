#!/usr/bin/env python3
"""Run one exact synthetic remix-ranker request; real requests fail closed."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from sunofriend.remix_ranker_training import run_remix_ranker_training
from sunofriend.source_receipt import canonical_json_bytes


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("feature_manifest", type=Path)
    parser.add_argument("--feature-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    result = run_remix_ranker_training(
        _load(args.request),
        _load(args.snapshot),
        _load(args.feature_manifest),
        feature_root=args.feature_root,
        repository_commit=head,
    )
    args.out.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with args.out.open("xb") as handle:
        handle.write(canonical_json_bytes(result))
    args.out.chmod(0o600)
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
