#!/usr/bin/env python3
"""Create the exact request for one MusicFM synthetic frozen-feature canary."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.remix_musicfm_canary import (  # noqa: E402
    create_musicfm_synthetic_canary_request,
)
from sunofriend.source_receipt import canonical_json_bytes  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("setup_receipt", type=Path)
    parser.add_argument("--repository-commit")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    raw = args.setup_receipt.read_bytes()
    commit = args.repository_commit or _current_commit()
    request = create_musicfm_synthetic_canary_request(
        repository_commit=commit,
        setup_receipt_sha256=hashlib.sha256(raw).hexdigest(),
        setup_receipt_bytes=len(raw),
    )
    args.out.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with args.out.open("xb") as handle:
        handle.write(canonical_json_bytes(request))
    if os.name != "nt":
        args.out.chmod(0o600)
    return 0


def _current_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
