#!/usr/bin/env python3
"""Repository entry point for the changed-function CRAP ratchet."""

from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from devtools.code_risk_ratchet import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
