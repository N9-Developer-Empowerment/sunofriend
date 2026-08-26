#!/usr/bin/env python3
"""Print a no-effects MusicFM remix feature-extraction plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.remix_musicfm_feature_plan import (  # noqa: E402
    create_musicfm_remix_feature_plan,
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--training-snapshot", type=Path, required=True)
    parser.add_argument("--operation-features", type=Path, required=True)
    parser.add_argument("--admission-plan", type=Path, required=True)
    parser.add_argument("--static-evidence", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--runtime-plan", type=Path, required=True)
    parser.add_argument("--runtime-resolution", type=Path, required=True)
    parser.add_argument("--resolver-report", type=Path, required=True)
    args = parser.parse_args()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    plan = create_musicfm_remix_feature_plan(
        _json(args.training_snapshot),
        _json(args.operation_features),
        _json(args.admission_plan),
        _json(args.static_evidence),
        _json(args.readiness),
        _json(args.runtime_plan),
        _json(args.runtime_resolution),
        resolver_report_bytes=args.resolver_report.read_bytes(),
        repository_commit=commit,
    )
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
