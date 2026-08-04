#!/usr/bin/env python3
"""Resume the private bounded-worker queue for one sealed full-song plan."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_full_song_executor import (
    _execute_private_separation_full_song_queue,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run independently verified private Kim chunks from a sealed "
            "full-song plan. No result is selected, stitched or exposed to a "
            "product route."
        )
    )
    parser.add_argument("--plan", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--runtime-launcher", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--companion-root", required=True)
    parser.add_argument("--device", choices=("gpu", "cpu"), default="gpu")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true")
    group.add_argument("--maximum-chunks", type=int, default=1)
    args = parser.parse_args()
    result = _execute_private_separation_full_song_queue(
        args.plan,
        out_dir=args.out_dir,
        repository_root=args.repository_root,
        runtime_launcher_path=args.runtime_launcher,
        source_root=args.source_root,
        checkpoint_path=args.checkpoint,
        companion_root=args.companion_root,
        device=args.device,
        maximum_chunks=None if args.all else args.maximum_chunks,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "chunks_executed_this_invocation": result[
                    "chunks_executed_this_invocation"
                ],
                "summary": result["summary"],
                "permissions": result["permissions"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
