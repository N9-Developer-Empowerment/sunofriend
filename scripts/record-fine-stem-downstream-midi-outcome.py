#!/usr/bin/env python3
"""Record the completed downstream-MIDI review without opening audio."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_fine_stem_midi_outcome import (  # noqa: E402
    build_fine_stem_midi_outcome,
    validate_fine_stem_midi_outcome,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("midi_canary_root", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    root = args.midi_canary_root.resolve(strict=True)
    out = args.out.resolve()
    if out.name != "fine-stem-downstream-midi-outcome-v1" or out.exists():
        raise RuntimeError("fresh exact downstream-MIDI outcome root is required")
    report = json.loads(
        (root / "TECHNICAL/MIDI-CANARY-REPORT.json").read_text(encoding="utf-8")
    )
    review = json.loads(
        (root / "REVIEW/MIDI-LISTENING.json").read_text(encoding="utf-8")
    )
    outcome = validate_fine_stem_midi_outcome(
        build_fine_stem_midi_outcome(
            report=report,
            review=review,
            source_reference_present_during_completed_review=False,
            repaired_page_source_reference_present=True,
        )
    )
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(tempfile.mkdtemp(prefix=".fine-stem-midi-outcome-", dir=out.parent))
    try:
        path = staging / "MIDI-OUTCOME.json"
        path.write_text(
            json.dumps(outcome, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        path.chmod(0o600)
        staging.rename(out)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(json.dumps(outcome, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
