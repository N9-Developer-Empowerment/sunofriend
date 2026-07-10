from __future__ import annotations

import re
from pathlib import Path

from .models import ProjectMetadata


METADATA_RE = re.compile(
    r"-(?P<key>[A-G](?:#|b)?\s+(?:major|minor))-(?P<bpm>\d+(?:\.\d+)?)bpm-(?P<tuning>\d+(?:\.\d+)?)hz",
    re.IGNORECASE,
)


def infer_project_metadata(path: str | Path) -> ProjectMetadata:
    text = Path(path).name
    match = METADATA_RE.search(text)
    if not match:
        return ProjectMetadata(key=None, bpm=None, tuning_hz=None)

    return ProjectMetadata(
        key=_normalize_key(match.group("key")),
        bpm=float(match.group("bpm")),
        tuning_hz=float(match.group("tuning")),
    )


def _normalize_key(key: str) -> str:
    root, mode = key.split(maxsplit=1)
    return f"{root[0].upper()}{root[1:]} {mode.lower()}"
