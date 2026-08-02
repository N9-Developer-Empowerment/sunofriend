#!/usr/bin/env python3
"""Run the model-free private macOS runtime process-image canary."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sunofriend._separation_checkpoint_canonical import plain
from sunofriend._separation_macos_process_image import (
    _run_private_macos_runtime_process_image_canary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    evidence = _run_private_macos_runtime_process_image_canary(
        runtime_path=args.runtime
    )
    encoded = json.dumps(plain(evidence), indent=2, sort_keys=True) + "\n"
    if args.out is None:
        print(encoded, end="")
    else:
        _write_private_observation(args.out, encoded)
        print(args.out.resolve(strict=True))
    return 0


def _write_private_observation(path: Path, encoded: str) -> None:
    destination = path.expanduser().absolute()
    destination.parent.mkdir(mode=0o700, parents=False, exist_ok=True)
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=False) as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)


if __name__ == "__main__":
    raise SystemExit(main())
