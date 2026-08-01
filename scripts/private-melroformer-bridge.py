#!/usr/bin/env python3
"""Probe the approved private Kim Vocal 2 bridge without audio inference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sunofriend._separation_melroformer_real_bridge import (
    _load_private_melroformer_model,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true", required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--companion-root", type=Path, required=True)
    args = parser.parse_args()
    handle = _load_private_melroformer_model(
        source_root=args.source_root,
        checkpoint_path=args.checkpoint,
        companion_root=args.companion_root,
    )
    print(json.dumps(dict(handle.evidence), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
