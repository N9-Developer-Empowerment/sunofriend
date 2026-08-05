#!/usr/bin/env python3
"""Check or start Sunofriend's experimental local two-stem workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sunofriend._separation_private_local_workflow import (
    _check_private_separation_local_profile,
    _resolve_private_separation_local_profile,
    _start_private_separation_local_workflow,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        default=str(Path.cwd()),
        help="Sunofriend checkout containing the accepted private evidence profile",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "doctor",
        help="reverify the installed private profile without writing or running a model",
    )
    start = commands.add_parser(
        "start",
        help="prepare a request, then run only with the explicit --execute action",
    )
    start.add_argument("--corpus", required=True)
    start.add_argument("--track-id", required=True)
    start.add_argument("--out-dir", required=True)
    start.add_argument("--device", choices=("gpu", "cpu"), default="gpu")
    start.add_argument(
        "--execute",
        action="store_true",
        help="run the sealed local model; omit to prepare and preflight only",
    )
    chunks = start.add_mutually_exclusive_group()
    chunks.add_argument(
        "--all",
        action="store_true",
        help="process every remaining chunk in this invocation",
    )
    chunks.add_argument("--maximum-chunks", type=int, default=1)
    args = parser.parse_args()

    if args.command == "doctor":
        result = _check_private_separation_local_profile(
            _resolve_private_separation_local_profile(args.repository_root)
        )
    else:
        result = _start_private_separation_local_workflow(
            args.corpus,
            args.track_id,
            out_dir=args.out_dir,
            repository_root=args.repository_root,
            device=args.device,
            execute=args.execute,
            maximum_chunks=None if args.all else args.maximum_chunks,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
