#!/usr/bin/env python3
"""Freeze a controlled private full-song resource benchmark plan."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_full_song_resource_benchmark import (
    DEFAULT_REPETITIONS,
    _prepare_private_full_song_resource_benchmark_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, help="sealed full-song plan JSON")
    parser.add_argument("--runtime-launcher", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--device", choices=("cpu", "gpu"), default="gpu")
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--out", required=True, help="fresh private plan JSON")
    args = parser.parse_args()
    result = _prepare_private_full_song_resource_benchmark_plan(
        args.plan,
        runtime_launcher_path=args.runtime_launcher,
        checkpoint_path=args.checkpoint,
        device=args.device,
        repetitions=args.repetitions,
        out=args.out,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
