#!/usr/bin/env python3
"""Build exact native-Windows MusicFM setup documents from retained evidence."""

from __future__ import annotations

import argparse
import os
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
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument("--out-dir", type=Path)
    output.add_argument("--stdout-bundle", action="store_true")
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
    if args.stdout_bundle:
        sys.stdout.buffer.write(
            canonical_json_bytes({"install_lock": lock, "asset_manifest": assets})
        )
        return 0
    assert args.out_dir is not None
    args.out_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, document in (
        ("native-windows-install-lock.json", lock),
        ("asset-download-manifest.json", assets),
    ):
        path = args.out_dir / name
        with path.open("xb") as handle:
            handle.write(canonical_json_bytes(document))
            handle.flush()
            os.fsync(handle.fileno())
        # Windows uses owner ACLs rather than POSIX mode bits; applying a Unix
        # 0600 mode to a OneDrive-backed handoff can make the next process lose
        # access.  Keep the explicit owner-only mode on POSIX only.
        if os.name != "nt":
            path.chmod(0o600)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
