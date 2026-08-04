#!/usr/bin/env python3
"""Run exactly one fresh private full-song resource benchmark repetition."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_full_song_resource_benchmark_run import (
    _run_private_full_song_resource_benchmark_repetition,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-plan", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--repetition", required=True, type=int)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--runtime-launcher", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--companion-root", required=True)
    args = parser.parse_args()
    result = _run_private_full_song_resource_benchmark_repetition(
        args.benchmark_plan,
        args.plan,
        repetition_index=args.repetition,
        out_dir=args.out_dir,
        repository_root=args.repository_root,
        runtime_launcher_path=args.runtime_launcher,
        source_root=args.source_root,
        checkpoint_path=args.checkpoint,
        companion_root=args.companion_root,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "repetition": result["repetition"],
                "measurements": result["measurements"],
                "readiness": result["readiness"],
                "permissions": result["permissions"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
