#!/usr/bin/env python3
"""Write the no-audio request for the source-present synth bottleneck test."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_fine_stem_synth_bottleneck_plan import (  # noqa: E402
    build_fine_stem_synth_bottleneck_plan,
    validate_fine_stem_synth_bottleneck_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("midi_canary_root", type=Path)
    parser.add_argument("integration_root", type=Path)
    parser.add_argument("midi_outcome", type=Path)
    parser.add_argument(
        "--provider-corpus",
        type=Path,
        default=ROOT / "stem_examples/corpus.json",
    )
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    midi_root = args.midi_canary_root.resolve(strict=True)
    integration_root = args.integration_root.resolve(strict=True)
    outcome_path = args.midi_outcome.resolve(strict=True)
    corpus_path = args.provider_corpus.resolve(strict=True)
    out = args.out.resolve()
    if out.name != "fine-stem-synth-bottleneck-request-v1" or out.exists():
        raise RuntimeError("fresh exact synth bottleneck request root is required")
    midi_report = json.loads(
        (midi_root / "TECHNICAL/MIDI-CANARY-REPORT.json").read_text(encoding="utf-8")
    )
    integration_report = json.loads(
        (integration_root / "TECHNICAL/INTEGRATION-REPORT.json").read_text(
            encoding="utf-8"
        )
    )
    plan = validate_fine_stem_synth_bottleneck_plan(
        build_fine_stem_synth_bottleneck_plan(
            midi_report=midi_report,
            midi_outcome=json.loads(outcome_path.read_text(encoding="utf-8")),
            integration_report=integration_report,
            provider_corpus=json.loads(corpus_path.read_text(encoding="utf-8")),
        )
    )
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(tempfile.mkdtemp(prefix=".synth-bottleneck-", dir=out.parent))
    try:
        path = staging / "SYNTH-BOTTLENECK-REQUEST.json"
        path.write_text(
            json.dumps(plan, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        path.chmod(0o600)
        staging.rename(out)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(json.dumps(plan, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
