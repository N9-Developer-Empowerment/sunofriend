#!/usr/bin/env python3
"""Launch the model-free MelRoFormer worker sandbox canary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sunofriend._separation_checkpoint_canonical import plain
from sunofriend._separation_melroformer_worker_sandbox import (
    _run_private_melroformer_synthetic_worker_canary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--staging-directory", type=Path, required=True)
    args = parser.parse_args()
    evidence = _run_private_melroformer_synthetic_worker_canary(
        repository_root=args.repository_root,
        runtime_path=args.runtime,
        staging_directory=args.staging_directory,
    )
    print(json.dumps(plain(evidence), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
