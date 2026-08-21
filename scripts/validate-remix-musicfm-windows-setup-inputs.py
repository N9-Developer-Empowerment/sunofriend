#!/usr/bin/env python3
"""Validate exact native-Windows MusicFM setup inputs before network writes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.remix_musicfm_fma_windows_setup import (  # noqa: E402
    validate_windows_asset_manifest,
    validate_windows_install_lock,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("install_lock", type=Path)
    parser.add_argument("asset_manifest", type=Path)
    args = parser.parse_args()
    report = args.report.read_bytes()
    receipt = args.receipt.read_bytes()
    lock = json.loads(args.install_lock.read_text(encoding="utf-8"))
    assets = json.loads(args.asset_manifest.read_text(encoding="utf-8"))
    validate_windows_install_lock(lock, report, receipt)
    validate_windows_asset_manifest(assets)
    if lock["repository_commit"] != assets["repository_commit"]:
        raise ValueError("MusicFM Windows setup documents bind different commits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
