#!/usr/bin/env python3
"""Validate exact native-Windows MusicFM setup inputs before network writes."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.remix_musicfm_fma_windows_setup import (  # noqa: E402
    validate_windows_asset_manifest,
    validate_windows_install_lock,
)


def _read_bytes(path: Path) -> bytes:
    """Tolerate only a short transient Windows/OneDrive read lock."""

    for attempt in range(5):
        try:
            return path.read_bytes()
        except PermissionError:
            if os.name != "nt" or attempt == 4:
                raise
            time.sleep(0.25)
    raise AssertionError("unreachable")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("install_lock", type=Path)
    parser.add_argument("asset_manifest", type=Path)
    args = parser.parse_args()
    report = _read_bytes(args.report)
    receipt = _read_bytes(args.receipt)
    lock = json.loads(_read_bytes(args.install_lock).decode("utf-8-sig"))
    assets = json.loads(_read_bytes(args.asset_manifest).decode("utf-8-sig"))
    validate_windows_install_lock(lock, report, receipt)
    validate_windows_asset_manifest(assets)
    if lock["repository_commit"] != assets["repository_commit"]:
        raise ValueError("MusicFM Windows setup documents bind different commits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
