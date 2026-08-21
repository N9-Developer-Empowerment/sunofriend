#!/usr/bin/env python3
"""Build exact native-Windows MusicFM setup documents from retained evidence."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.remix_musicfm_fma_windows_setup import (  # noqa: E402
    create_windows_asset_manifest,
    create_windows_install_lock,
)
from sunofriend.source_receipt import canonical_json_bytes  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    lock = create_windows_install_lock(
        args.report.read_bytes(),
        args.receipt.read_bytes(),
        repository_commit=commit,
    )
    assets = create_windows_asset_manifest(repository_commit=commit)
    args.out_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, document in (
        ("native-windows-install-lock.json", lock),
        ("asset-download-manifest.json", assets),
    ):
        path = args.out_dir / name
        with path.open("xb") as handle:
            handle.write(canonical_json_bytes(document))
        path.chmod(0o600)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
