#!/usr/bin/env python3
"""Write the exact no-effects 12-attempt provider synth MIDI plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_fine_stem_synth_provider_midi_plan import (  # noqa: E402
    build_fine_stem_synth_provider_midi_plan,
    validate_fine_stem_synth_provider_midi_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request_root", type=Path)
    parser.add_argument("qualification_root", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    request_root = args.request_root.resolve(strict=True)
    qualification_root = args.qualification_root.resolve(strict=True)
    out = args.out.resolve()
    if out.exists():
        raise FileExistsError("fresh provider synth MIDI plan path is required")
    request = json.loads(
        (request_root / "SYNTH-BOTTLENECK-REQUEST.json").read_text(encoding="utf-8")
    )
    qualification = json.loads(
        (qualification_root / "TECHNICAL/PROVIDER-QUALIFICATION.json").read_text(
            encoding="utf-8"
        )
    )
    outcome = json.loads(
        (qualification_root / "TECHNICAL/PROVIDER-PRESENCE-OUTCOME.json").read_text(
            encoding="utf-8"
        )
    )
    plan = validate_fine_stem_synth_provider_midi_plan(
        build_fine_stem_synth_provider_midi_plan(
            request=request,
            qualification=qualification,
            outcome=outcome,
        )
    )
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = out.with_suffix(out.suffix + ".tmp")
    temporary.write_text(
        json.dumps(plan, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    temporary.replace(out)
    print(json.dumps(plan, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
