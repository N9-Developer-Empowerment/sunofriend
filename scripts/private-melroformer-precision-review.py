#!/usr/bin/env python3
"""Create or resolve the private Kim Vocal 2 FP32/BF16 listening gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sunofriend._separation_melroformer_precision_review import (
    _resolve_private_melroformer_precision_review,
    _run_private_melroformer_precision_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--create",
        action="store_true",
        help="run the exact CPU pair and create one fresh blinded review",
    )
    action.add_argument(
        "--resolve",
        type=Path,
        metavar="REVIEWED_JSON",
        help="verify and resolve one user-exported complete review",
    )
    parser.add_argument("--mlx-source-root", type=Path)
    parser.add_argument("--source-checkpoint", type=Path)
    parser.add_argument("--converted-checkpoint", type=Path)
    parser.add_argument("--companion-root", type=Path)
    parser.add_argument("--authorisation-report", type=Path)
    parser.add_argument("--authorisation-report-sha256")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--package-dir", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    if args.create:
        required = {
            "--mlx-source-root": args.mlx_source_root,
            "--source-checkpoint": args.source_checkpoint,
            "--converted-checkpoint": args.converted_checkpoint,
            "--companion-root": args.companion_root,
            "--authorisation-report": args.authorisation_report,
            "--authorisation-report-sha256": args.authorisation_report_sha256,
            "--out-dir": args.out_dir,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            parser.error("--create requires " + ", ".join(missing))
        if args.package_dir is not None or args.out is not None:
            parser.error("--package-dir and --out are only valid with --resolve")
        result = _run_private_melroformer_precision_review(
            mlx_source_root=args.mlx_source_root,
            source_checkpoint=args.source_checkpoint,
            converted_checkpoint=args.converted_checkpoint,
            companion_root=args.companion_root,
            authorisation_report=args.authorisation_report,
            authorisation_report_sha256=args.authorisation_report_sha256,
            out_dir=args.out_dir,
        )
    else:
        if args.package_dir is None or args.out is None:
            parser.error("--resolve requires --package-dir and --out")
        create_only = (
            args.mlx_source_root,
            args.source_checkpoint,
            args.converted_checkpoint,
            args.companion_root,
            args.authorisation_report,
            args.authorisation_report_sha256,
            args.out_dir,
        )
        if any(value is not None for value in create_only):
            parser.error("model and --out-dir arguments are only valid with --create")
        result = _resolve_private_melroformer_precision_review(
            args.resolve,
            package_dir=args.package_dir,
            out=args.out,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
