#!/usr/bin/env python3
"""Print the pure pinned Banquet forward contract; perform no model work."""

from __future__ import annotations

import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from sunofriend.separation_other_refinement_query_forward_contract import (  # noqa: E402
    build_query_forward_contract,
)


def main() -> int:
    json.dump(build_query_forward_contract(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
