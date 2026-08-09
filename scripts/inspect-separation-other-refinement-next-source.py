#!/usr/bin/env python3
"""Inspect and safely extract the pinned BS-RoFormer source archive."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sunofriend.separation_other_refinement_next_source_evidence import (
    inspect_source_archive,
    validate_source_evidence,
    verify_extracted_source_tree,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--extract-root", type=Path, required=True)
    args = parser.parse_args()
    evidence = inspect_source_archive(args.archive, extract_root=args.extract_root)
    validate_source_evidence(evidence)
    verify_extracted_source_tree(evidence, args.extract_root)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
