#!/usr/bin/env python3
"""Verify exact private Kim Vocal 2 source-to-MLX weight conversion parity."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sunofriend._separation_melroformer_conversion_parity import (
    _verify_private_melroformer_weight_conversion,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-checkpoint", type=Path, required=True)
    parser.add_argument("--converted-checkpoint", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.out.is_absolute():
        parser.error("--out must be an absolute fresh path")
    report = _verify_private_melroformer_weight_conversion(
        args.source_checkpoint, args.converted_checkpoint
    )
    payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
    args.out.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(
        args.out,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
