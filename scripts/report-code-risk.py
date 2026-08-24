#!/usr/bin/env python3
"""Repository entry point for the deterministic CRAP1 report."""

from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from devtools.code_risk import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
