#!/usr/bin/env python3
"""Record the completed provider synth presence review without effects."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_fine_stem_synth_provider_outcome import (  # noqa: E402
    build_fine_stem_synth_provider_outcome,
    validate_fine_stem_synth_provider_outcome,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    package = args.root.resolve(strict=True)
    report = json.loads(
        (package / "TECHNICAL/PROVIDER-QUALIFICATION.json").read_text(encoding="utf-8")
    )
    review = json.loads(
        (package / "REVIEW/PROVIDER-PRESENCE.json").read_text(encoding="utf-8")
    )
    outcome = validate_fine_stem_synth_provider_outcome(
        build_fine_stem_synth_provider_outcome(report=report, review=review)
    )
    path = package / "TECHNICAL/PROVIDER-PRESENCE-OUTCOME.json"
    if path.exists():
        raise FileExistsError("provider presence outcome already exists")
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(outcome, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    temporary.replace(path)
    print(json.dumps(outcome, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
