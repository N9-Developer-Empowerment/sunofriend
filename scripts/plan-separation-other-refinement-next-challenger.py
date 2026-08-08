#!/usr/bin/env python3
"""Print the deterministic no-effects synth-first challenger plan."""

from __future__ import annotations

import json

from sunofriend.separation_other_refinement_next_challenger import (
    build_next_challenger_plan,
    validate_next_challenger_plan,
)


def main() -> int:
    plan = build_next_challenger_plan()
    validate_next_challenger_plan(plan)
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
