#!/usr/bin/env python3
"""Print the deterministic no-effects Banquet runtime audit."""

from __future__ import annotations

import json

from sunofriend.separation_other_refinement_query_runtime import (
    build_query_runtime_audit,
    validate_query_runtime_audit,
)


def main() -> int:
    audit = build_query_runtime_audit()
    validate_query_runtime_audit(audit)
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
