#!/usr/bin/env python3
"""Run one authorised, local-only MusicFM private feature extraction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.remix_musicfm_private_features import (  # noqa: E402
    run_musicfm_private_features,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("training_snapshot", type=Path)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    snapshot = json.loads(args.training_snapshot.read_text(encoding="utf-8"))
    result = run_musicfm_private_features(
        request,
        snapshot,
        runtime_root=args.runtime_root,
        inputs={
            "control": args.control,
            "left": args.left,
            "right": args.right,
        },
        out_dir=args.out_dir,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
