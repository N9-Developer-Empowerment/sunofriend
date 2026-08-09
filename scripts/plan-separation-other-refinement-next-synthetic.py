#!/usr/bin/env python3
"""Print the immutable, no-effects Mega-53 generated-tensor plan."""

from __future__ import annotations

import json

from sunofriend.separation_other_refinement_next_synthetic_plan import (
    build_next_synthetic_plan,
    validate_next_synthetic_plan,
)


def main() -> int:
    plan = validate_next_synthetic_plan(build_next_synthetic_plan())
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
