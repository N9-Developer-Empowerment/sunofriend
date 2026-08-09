#!/usr/bin/env python3
"""Print non-loading static evidence for one exact SW checkpoint/config pair."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_bs_roformer_sw_evidence import (  # noqa: E402
    inspect_sw_artifact_evidence,
    validate_sw_artifact_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("config", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    evidence = inspect_sw_artifact_evidence(args.checkpoint, args.config)
    validate_sw_artifact_evidence(evidence)
    payload = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.out is None:
        print(payload, end="")
    else:
        if args.out.exists():
            raise FileExistsError("SW static-evidence output must be fresh")
        args.out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        args.out.write_text(payload, encoding="utf-8")
        args.out.chmod(0o600)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
