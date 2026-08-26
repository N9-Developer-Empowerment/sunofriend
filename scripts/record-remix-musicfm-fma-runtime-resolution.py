#!/usr/bin/env python3
"""Record a metadata-only MusicFM wheel resolution as partial evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.remix_musicfm_fma_runtime_resolution import (  # noqa: E402
    create_musicfm_fma_runtime_resolution,
)
from sunofriend.source_receipt import canonical_json_bytes  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-plan", type=Path, required=True)
    parser.add_argument("--resolver-report", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    resolution = create_musicfm_fma_runtime_resolution(
        json.loads(args.runtime_plan.read_text(encoding="utf-8")),
        resolver_report_bytes=args.resolver_report.read_bytes(),
        repository_commit=commit,
    )
    rendered = canonical_json_bytes(resolution)
    if args.out is None:
        sys.stdout.buffer.write(rendered)
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with args.out.open("xb") as handle:
        handle.write(rendered)
    args.out.chmod(0o600)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
