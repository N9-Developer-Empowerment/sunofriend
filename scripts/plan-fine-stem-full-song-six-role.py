#!/usr/bin/env python3
"""Write a fixed three-song six-role plan without opening source content."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sunofriend.separation_fine_stem_full_song_plan import (  # noqa: E402
    FULL_SONG_PLAN_DIRECTORY_NAME,
    FULL_SONG_PLAN_FILE_NAME,
    build_fine_stem_full_song_plan,
    validate_fine_stem_full_song_plan,
)
from sunofriend.separation_target_presence_review import (  # noqa: E402
    load_presence_manifest,
)


def _load_json(path: Path) -> dict:
    return json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))


def _source_observations(
    *,
    manifest: dict,
    source_root: Path,
    track_ids: set[str],
) -> dict[str, dict]:
    observations: dict[str, dict] = {}
    for track_id in track_ids:
        cases = [case for case in manifest["cases"] if case["track_id"] == track_id]
        if not cases:
            raise RuntimeError(
                f"selected track is absent from presence evidence: {track_id}"
            )
        sources = [case["source_input"] for case in cases]
        if any(source != sources[0] for source in sources[1:]):
            raise RuntimeError(
                "selected track has conflicting full-song source identities"
            )
        source = sources[0]
        path = (source_root / source["relative_path"]).resolve(strict=True)
        if source_root not in path.parents or not path.is_file():
            raise RuntimeError("selected full-song source escapes the source root")
        stat = path.stat()
        if stat.st_size != source["bytes"]:
            raise RuntimeError("selected full-song source byte count differs")
        observations[track_id] = {
            "absolute_path": path.as_posix(),
            "regular_file": True,
            "observed_bytes": stat.st_size,
            "content_opened": False,
        }
    return observations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("presence_root", type=Path)
    parser.add_argument("integration_outcome", type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--both-targets-track", required=True)
    parser.add_argument("--synth-track", required=True)
    parser.add_argument("--guitar-track", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    presence_root = args.presence_root.resolve(strict=True)
    source_root = args.source_root.resolve(strict=True)
    out = args.out.resolve()
    if out.name != FULL_SONG_PLAN_DIRECTORY_NAME or out.exists():
        raise RuntimeError("fresh exact full-song six-role plan root is required")
    manifest = load_presence_manifest(presence_root)
    result = _load_json(presence_root / "PRESENCE-RESULT.json")
    outcome = _load_json(args.integration_outcome)
    selections = {
        "both_targets": args.both_targets_track,
        "synth": args.synth_track,
        "guitar": args.guitar_track,
    }
    observations = _source_observations(
        manifest=manifest,
        source_root=source_root,
        track_ids=set(selections.values()),
    )
    plan = validate_fine_stem_full_song_plan(
        build_fine_stem_full_song_plan(
            presence_manifest=manifest,
            presence_result=result,
            integration_outcome=outcome,
            selections=selections,
            source_root=source_root.as_posix(),
            source_observations=observations,
        )
    )

    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(
        tempfile.mkdtemp(prefix=".fine-stem-full-song-plan-", dir=out.parent)
    )
    staging.chmod(0o700)
    try:
        path = staging / FULL_SONG_PLAN_FILE_NAME
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
