#!/usr/bin/env python3
"""Verify tracked private MelBand-RoFormer source/runtime evidence."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_melroformer_runtime_evidence import (
    _verify_private_melroformer_source_tree,
    _verify_tracked_melroformer_runtime_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--source-root")
    args = parser.parse_args()
    result = {
        "tracked": _verify_tracked_melroformer_runtime_evidence(args.repository_root)
    }
    if args.source_root:
        result["source_tree"] = _verify_private_melroformer_source_tree(args.source_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
