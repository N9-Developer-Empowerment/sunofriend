#!/usr/bin/env python3
"""Project current private separation evidence onto publication gates."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_publication_readiness import (
    _project_private_separation_publication_readiness,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("normalized_midi_agreement")
    parser.add_argument("human_listening_coverage")
    parser.add_argument(
        "--separated-audio-quality",
        help=(
            "optional resolved, source-bound blind audio-quality result; "
            "preference never selects a separator"
        ),
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _project_private_separation_publication_readiness(
        args.normalized_midi_agreement,
        args.human_listening_coverage,
        separated_audio_quality_path=args.separated_audio_quality,
        out=args.out,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": result["report"],
                "readiness": result["readiness"],
                "open_gates": [
                    gate["gate_id"]
                    for gate in result["gates"]
                    if gate["status"] == "open"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
