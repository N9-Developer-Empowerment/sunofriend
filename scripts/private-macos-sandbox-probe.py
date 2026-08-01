#!/usr/bin/env python3
"""Run Sunofriend's model-free private macOS network-denial canary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sunofriend._separation_checkpoint_canonical import plain
from sunofriend._separation_macos_sandbox_probe import (
    _run_private_macos_network_denial_canary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime",
        type=Path,
        help="exact Python runtime to exercise; defaults to this interpreter",
    )
    args = parser.parse_args()
    evidence = _run_private_macos_network_denial_canary(runtime_path=args.runtime)
    print(json.dumps(plain(evidence), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
