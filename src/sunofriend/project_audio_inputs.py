"""Detect source folders that need explicit preparation before conversion.

Production conversion intentionally consumes lower-case, top-level ``.wav``
stems.  This small read-only boundary prevents a mixed-format folder from
appearing to work while FLAC, M4A, MP3, or other supported source parts are
silently ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .audio_formats import KNOWN_AUDIO_SUFFIXES


@dataclass(frozen=True)
class ProjectAudioInventory:
    """Top-level source-audio inventory without probing or writing files."""

    project: Path
    audio_files: tuple[Path, ...]
    canonical_wavs: tuple[Path, ...]
    unprepared_audio: tuple[Path, ...]


def inspect_project_audio_inputs(
    project: str | Path,
) -> ProjectAudioInventory:
    """Classify top-level audio paths using the public import suffix policy."""

    root = Path(project).expanduser().resolve()
    if not root.is_dir():
        return ProjectAudioInventory(root, (), (), ())
    audio = tuple(
        sorted(
            (
                path
                for path in root.iterdir()
                if path.suffix.casefold() in KNOWN_AUDIO_SUFFIXES
                and (path.is_file() or path.is_symlink())
            ),
            key=lambda path: (path.name.casefold(), path.name),
        )
    )
    canonical = tuple(
        path
        for path in audio
        if path.suffix == ".wav" and not path.is_symlink()
    )
    canonical_set = set(canonical)
    return ProjectAudioInventory(
        project=root,
        audio_files=audio,
        canonical_wavs=canonical,
        unprepared_audio=tuple(
            path for path in audio if path not in canonical_set
        ),
    )


def prepared_project_input_problem(project: str | Path) -> str | None:
    """Explain why a folder is not yet safe for WAV-only conversion."""

    inventory = inspect_project_audio_inputs(project)
    if inventory.unprepared_audio:
        if len(inventory.audio_files) == 1:
            return (
                "This folder contains one source audio file, not a prepared "
                "top-level .wav stem project. First run `sunofriend "
                "source-import SOURCE --out-dir FRESH --plan`. That command "
                "prepares one file; it does not separate a finished mix into "
                "stems."
            )
        return (
            f"This folder contains {len(inventory.audio_files)} supported audio "
            f"parts, but {len(inventory.unprepared_audio)} are not prepared "
            "lower-case top-level .wav stems. Sunofriend will not silently "
            "ignore them. First run `sunofriend source-import-folder "
            "SOURCE_FOLDER --out-dir FRESH --plan`, then execute that reviewed "
            "plan and load the fresh prepared folder."
        )
    if not inventory.canonical_wavs:
        return "The stem project folder contains no top-level WAV stems."
    return None


__all__ = [
    "ProjectAudioInventory",
    "inspect_project_audio_inputs",
    "prepared_project_input_problem",
]
