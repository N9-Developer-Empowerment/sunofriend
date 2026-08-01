#!/usr/bin/env python3
"""Run exact private Kim Vocal 2 PyTorch-to-MLX output parity."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sunofriend._separation_melroformer_inference_parity import (
    _run_private_melroformer_inference_parity,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mlx-source-root", type=Path, required=True)
    parser.add_argument("--source-checkpoint", type=Path, required=True)
    parser.add_argument("--converted-checkpoint", type=Path, required=True)
    parser.add_argument("--companion-root", type=Path, required=True)
    parser.add_argument("--authorisation-report", type=Path, required=True)
    parser.add_argument("--authorisation-report-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.out.is_absolute():
        parser.error("--out must be an absolute fresh path")
    report = _run_private_melroformer_inference_parity(
        mlx_source_root=args.mlx_source_root,
        source_checkpoint=args.source_checkpoint,
        converted_checkpoint=args.converted_checkpoint,
        companion_root=args.companion_root,
        authorisation_report=args.authorisation_report,
        authorisation_report_sha256=args.authorisation_report_sha256,
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
