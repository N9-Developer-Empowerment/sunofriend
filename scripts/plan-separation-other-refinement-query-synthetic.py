#!/usr/bin/env python3
"""Print the deterministic no-effects Banquet synthetic-forward plan."""

from __future__ import annotations

import json

from sunofriend.separation_other_refinement_query_synthetic_plan import (
    build_query_synthetic_plan,
)


def main() -> int:
    print(json.dumps(build_query_synthetic_plan(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
