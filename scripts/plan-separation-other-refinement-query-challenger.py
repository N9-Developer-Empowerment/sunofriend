#!/usr/bin/env python3
"""Print the no-effects Banquet query-challenger plan."""

from __future__ import annotations

import json

from sunofriend.separation_other_refinement_query_challenger import (
    build_query_challenger_plan,
    validate_query_challenger_plan,
)


def main() -> int:
    plan = build_query_challenger_plan()
    validate_query_challenger_plan(plan)
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
