#!/usr/bin/env python3
"""Bind an explicit completed-listening statement to one private review."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_target_presence_review import (  # noqa: E402
    attest_completed_presence_listening,
    load_presence_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--explicit-user-review-complete", action="store_true")
    args = parser.parse_args()
    if not args.explicit_user_review_complete:
        parser.error("explicit user review completion statement is required")
    root = args.root.resolve(strict=True)
    result_path = root / "PRESENCE-RESULT.json"
    backup_path = root / "PRESENCE-RESULT.pre-listening-attestation.json"
    if not result_path.is_file() or backup_path.exists():
        raise RuntimeError("fresh exact presence listening attestation is required")
    raw = json.loads(result_path.read_text(encoding="utf-8"))
    manifest = load_presence_manifest(root)
    value = attest_completed_presence_listening(
        raw,
        manifest,
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )
    shutil.copyfile(result_path, backup_path)
    backup_path.chmod(0o600)
    temporary = result_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    temporary.replace(result_path)
    print(json.dumps(value, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
