#!/usr/bin/env python3
"""Import reviewed private stems as inactive lineage in a fresh project."""

from __future__ import annotations

import argparse
import json

from sunofriend._separation_reviewed_output_import import _import_reviewed_output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--import-assessment", required=True)
    parser.add_argument("--review-equivalence", required=True)
    parser.add_argument("--reviewed-export", required=True)
    parser.add_argument("--reviewed-package-dir", required=True)
    parser.add_argument("--candidate-package-report", required=True)
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--ffprobe", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--rights-category", default="authorised_private_use")
    parser.add_argument("--title")
    parser.add_argument("--key")
    parser.add_argument("--bpm", type=float)
    parser.add_argument("--tuning-hz", type=float)
    parser.add_argument("--chord-document")
    args = parser.parse_args()
    result = _import_reviewed_output(
        args.import_assessment,
        equivalence_path=args.review_equivalence,
        reviewed_export_path=args.reviewed_export,
        reviewed_package_dir=args.reviewed_package_dir,
        candidate_package_report_path=args.candidate_package_report,
        ffmpeg=args.ffmpeg,
        ffprobe=args.ffprobe,
        out_dir=args.out_dir,
        rights_category=args.rights_category,
        title=args.title,
        key=args.key,
        bpm=args.bpm,
        tuning_hz=args.tuning_hz,
        chord_document=args.chord_document,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "root": result["root"],
                "report": result["report"],
                "source_graph": result["source_graph"],
                "rollback": result["rollback"],
                "readiness": result["readiness"],
                "next_action": result["next_action"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
