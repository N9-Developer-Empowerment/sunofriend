#!/usr/bin/env python3
"""Run one approved, local-only MelRoFormer excerpt under the fixed sandbox."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sunofriend._separation_checkpoint_canonical import plain
from sunofriend._separation_melroformer_authorised_worker import (
    _run_private_melroformer_authorised_worker,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--companion-root", type=Path, required=True)
    parser.add_argument("--authorised-excerpt", type=Path, required=True)
    parser.add_argument("--authorisation-report-sha256", required=True)
    parser.add_argument("--staging-directory", type=Path, required=True)
    parser.add_argument("--device", choices=("gpu", "cpu"), default="gpu")
    args = parser.parse_args()
    evidence = _run_private_melroformer_authorised_worker(
        repository_root=args.repository_root,
        runtime_path=args.runtime,
        source_root=args.source_root,
        checkpoint_path=args.checkpoint,
        companion_root=args.companion_root,
        authorisation_report_path=args.authorised_excerpt,
        expected_authorisation_report_sha256=args.authorisation_report_sha256,
        staging_directory=args.staging_directory,
        device=args.device,
    )
    print(json.dumps(plain(evidence), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
