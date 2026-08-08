#!/usr/bin/env python3
"""Print non-importing static evidence for the Mega-53 wheel closure."""

from __future__ import annotations

import argparse
import json

from sunofriend.separation_other_refinement_next_runtime_evidence import (
    inspect_runtime_wheel_evidence,
    validate_runtime_wheel_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel_directory")
    args = parser.parse_args()
    evidence = inspect_runtime_wheel_evidence(args.wheel_directory)
    validate_runtime_wheel_evidence(evidence)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
