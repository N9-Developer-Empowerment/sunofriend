#!/usr/bin/env python3
"""Print the no-effects Banquet reference-query canary plan."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_other_refinement_query_reference_plan import (  # noqa: E402
    build_query_reference_plan,
)


if __name__ == "__main__":
    print(json.dumps(build_query_reference_plan(), indent=2, sort_keys=True))
