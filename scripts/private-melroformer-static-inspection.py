#!/usr/bin/env python3
"""Inspect the exact private Kim Vocal 2 checkpoint without loading tensors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
)
from sunofriend._separation_safetensors_inspection import (
    _inspect_private_safetensors,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        required=True,
        help="Absolute path to the already-downloaded exact model.safetensors",
    )
    args = parser.parse_args()
    result = _inspect_private_safetensors(
        args.checkpoint,
        expected_bytes=CONVERSION_CHECKPOINT_BYTES,
        expected_sha256=CONVERSION_CHECKPOINT_SHA256,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
