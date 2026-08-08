#!/usr/bin/env python3
"""Print bounded, non-loading evidence for the MVSep Mega-53 artifacts."""

from __future__ import annotations

import argparse
import json

from sunofriend.separation_other_refinement_next_challenger_evidence import (
    inspect_mega53_artifact_evidence,
    validate_mega53_artifact_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint")
    parser.add_argument("config")
    args = parser.parse_args()
    evidence = inspect_mega53_artifact_evidence(args.checkpoint, args.config)
    validate_mega53_artifact_evidence(evidence)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
