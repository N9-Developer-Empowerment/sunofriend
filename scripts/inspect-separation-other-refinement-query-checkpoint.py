#!/usr/bin/env python3
"""Print non-loading static evidence for one downloaded Banquet checkpoint."""

from __future__ import annotations

import argparse
import json

from sunofriend.separation_other_refinement_query_evidence import (
    inspect_query_checkpoint_evidence,
    validate_query_checkpoint_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint")
    args = parser.parse_args()
    evidence = inspect_query_checkpoint_evidence(args.checkpoint)
    validate_query_checkpoint_evidence(evidence)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
