#!/usr/bin/env python3
"""Record a path-free zero-execution failure for a reviewed GPU request."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sunofriend.source_receipt import canonical_json_bytes
from sunofriend.vocal_pairwise_gpu_canary import (
    build_pairwise_gpu_pretraining_failure,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request")
    parser.add_argument(
        "--failure-stage",
        required=True,
        choices=(
            "cli_argument_validation",
            "request_preflight",
            "repository_preflight",
            "cuda_preflight",
        ),
    )
    parser.add_argument(
        "--failure-code",
        required=True,
        help="path-free stable identifier such as missing-out-dir",
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    receipt = build_pairwise_gpu_pretraining_failure(
        json.loads(Path(args.request).read_text(encoding="utf-8")),
        failure_stage=args.failure_stage,
        failure_code=args.failure_code,
    )
    target = Path(args.out).expanduser().absolute()
    if target.exists():
        raise SystemExit(f"output already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(canonical_json_bytes(receipt))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
