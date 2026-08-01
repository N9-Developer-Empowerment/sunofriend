#!/usr/bin/env python3
"""Probe the approved private Kim Vocal 2 bridge without audio inference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sunofriend._separation_melroformer_real_bridge import (
    MAXIMUM_PROBE_FRAMES,
    _infer_private_melroformer_excerpt,
    _infer_private_melroformer_probe,
    _load_private_authorised_excerpt,
    _load_private_melroformer_model,
)
from sunofriend._separation_checkpoint_canonical import plain


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--probe", action="store_true")
    action.add_argument("--synthetic-smoke", action="store_true")
    action.add_argument(
        "--authorised-excerpt",
        type=Path,
        metavar="REPORT",
        help="self-hashed private authorised-excerpt report; persists no audio",
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--companion-root", type=Path, required=True)
    parser.add_argument(
        "--synthetic-seconds",
        type=int,
        choices=(1, 2, 4, 8, 15),
        default=1,
        help="duration for --synthetic-smoke; 15 seconds exercises overlap transport",
    )
    parser.add_argument(
        "--authorisation-report-sha256",
        help="expected SHA-256 of --authorised-excerpt report bytes",
    )
    args = parser.parse_args()
    if not args.synthetic_smoke and args.synthetic_seconds != 1:
        parser.error("--synthetic-seconds is only valid with --synthetic-smoke")
    if bool(args.authorised_excerpt) != bool(args.authorisation_report_sha256):
        parser.error(
            "--authorised-excerpt and --authorisation-report-sha256 are required together"
        )
    handle = _load_private_melroformer_model(
        source_root=args.source_root,
        checkpoint_path=args.checkpoint,
        companion_root=args.companion_root,
    )
    if args.probe:
        result = dict(handle.evidence)
    elif args.authorised_excerpt:
        source, authorisation = _load_private_authorised_excerpt(
            handle,
            report_path=args.authorised_excerpt,
            expected_report_sha256=args.authorisation_report_sha256,
        )
        observation = _infer_private_melroformer_excerpt(
            handle, source, sample_rate=44_100
        )
        result = {
            "authorisation": plain(authorisation),
            "bridge": dict(handle.evidence),
            "inference": plain(observation.evidence),
        }
    else:
        np = handle.np
        frames = args.synthetic_seconds * 44_100
        timeline = np.arange(frames, dtype=np.float32) / np.float32(44_100.0)
        left = (
            0.18 * np.sin(2 * np.pi * 220 * timeline)
            + 0.07 * np.sin(2 * np.pi * 440 * timeline)
        ).astype(np.float32)
        right = (
            0.18 * np.sin(2 * np.pi * 220 * timeline + 0.15)
            + 0.07 * np.sin(2 * np.pi * 660 * timeline)
        ).astype(np.float32)
        source = np.stack([left, right], axis=1)
        infer = (
            _infer_private_melroformer_probe
            if frames <= MAXIMUM_PROBE_FRAMES
            else _infer_private_melroformer_excerpt
        )
        observation = infer(handle, source, sample_rate=44_100)
        result = {
            "bridge": dict(handle.evidence),
            "inference": plain(observation.evidence),
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
