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
    parser.add_argument(
        "--resource-benchmark-result",
        help=(
            "optional verified controlled full-song development resource result; "
            "it cannot substitute for the acceptance machine class"
        ),
    )
    parser.add_argument(
        "--full-song-review-result",
        help=(
            "optional verified complete-song and exact-boundary listening result; "
            "review completion cannot select or accept a separator"
        ),
    )
    parser.add_argument(
        "--full-song-alignment-result",
        help=(
            "optional verified source-to-reconstruction alignment and drift result; "
            "it is synchronization evidence, not separator quality"
        ),
    )
    parser.add_argument(
        "--full-song-join-remediation-review-result",
        help=(
            "optional verified targeted raw-versus-candidate join-remediation "
            "review; it is supplementary evidence and cannot replace clean "
            "ratings from a candidate-bound full-song review"
        ),
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = _project_private_separation_publication_readiness(
        args.normalized_midi_agreement,
        args.human_listening_coverage,
        separated_audio_quality_path=args.separated_audio_quality,
        resource_benchmark_result_path=args.resource_benchmark_result,
        full_song_review_result_path=args.full_song_review_result,
        full_song_alignment_result_path=args.full_song_alignment_result,
        full_song_join_remediation_review_result_path=(
            args.full_song_join_remediation_review_result
        ),
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
