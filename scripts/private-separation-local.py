#!/usr/bin/env python3
"""Check, start, or finish Sunofriend's experimental local two-stem workflow."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sunofriend._separation_private_local_workflow import (
    _check_private_separation_local_profile,
    _finish_private_separation_local_workflow,
    _resolve_private_separation_local_profile,
    _start_private_separation_local_workflow,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        default=str(Path.cwd()),
        help="Sunofriend checkout containing the accepted private evidence profile",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "doctor",
        help="reverify the installed private profile without writing or running a model",
    )
    start = commands.add_parser(
        "start",
        help="prepare a request, then run only with the explicit --execute action",
    )
    start.add_argument("--corpus", required=True)
    start.add_argument("--track-id", required=True)
    start.add_argument("--out-dir", required=True)
    start.add_argument("--device", choices=("gpu", "cpu"), default="gpu")
    start.add_argument(
        "--execute",
        action="store_true",
        help="run the sealed local model; omit to prepare and preflight only",
    )
    chunks = start.add_mutually_exclusive_group()
    chunks.add_argument(
        "--all",
        action="store_true",
        help="process every remaining chunk in this invocation",
    )
    chunks.add_argument("--maximum-chunks", type=int, default=1)
    finish = commands.add_parser(
        "finish",
        help="verify a completed review, import inactive stems, then advance only with explicit confirmations",
    )
    finish.add_argument("--start-root", required=True)
    finish.add_argument("--reviewed-export", required=True)
    finish.add_argument("--project-out")
    finish.add_argument("--validation-out")
    finish.add_argument("--ffmpeg")
    finish.add_argument("--ffprobe")
    finish.add_argument("--soundfont")
    finish.add_argument("--max-iterations", type=int, default=8)
    finish.add_argument("--rights-category", default="authorised_private_use")
    finish.add_argument("--title")
    finish.add_argument("--key")
    finish.add_argument("--bpm", type=float)
    finish.add_argument("--tuning-hz", type=float)
    finish.add_argument("--chord-document")
    finish.add_argument(
        "--confirm-reviewed-stems-useful",
        action="store_true",
        help="confirm the exact bound review found all complete-song roles useful",
    )
    finish.add_argument(
        "--confirm-private-midi-validation",
        action="store_true",
        help="explicitly run private MIDI plus interpretation WAV and ZIP creation",
    )
    args = parser.parse_args()

    if args.command == "doctor":
        result = _check_private_separation_local_profile(
            _resolve_private_separation_local_profile(args.repository_root)
        )
    elif args.command == "start":
        result = _start_private_separation_local_workflow(
            args.corpus,
            args.track_id,
            out_dir=args.out_dir,
            repository_root=args.repository_root,
            device=args.device,
            execute=args.execute,
            maximum_chunks=None if args.all else args.maximum_chunks,
        )
    else:
        result = asyncio.run(
            _finish_private_separation_local_workflow(
                args.start_root,
                args.reviewed_export,
                repository_root=args.repository_root,
                project_out=args.project_out,
                validation_out=args.validation_out,
                ffmpeg=args.ffmpeg,
                ffprobe=args.ffprobe,
                soundfont_path=args.soundfont,
                max_iterations=args.max_iterations,
                rights_category=args.rights_category,
                title=args.title,
                key=args.key,
                bpm=args.bpm,
                tuning_hz=args.tuning_hz,
                chord_document=args.chord_document,
                confirm_reviewed_stems_useful=(args.confirm_reviewed_stems_useful),
                confirm_private_midi_validation=(args.confirm_private_midi_validation),
            )
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
