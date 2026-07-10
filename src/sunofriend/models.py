from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProjectMetadata:
    key: str | None
    bpm: float | None
    tuning_hz: float | None


@dataclass(frozen=True)
class ChordChart:
    key: str | None
    chords: list[str]


@dataclass(frozen=True)
class ChordSegment:
    start: float
    end: float
    name: str
    pitch_classes: tuple[int, ...]

    @property
    def root_pc(self) -> int:
        return self.pitch_classes[0]


@dataclass(frozen=True)
class StemEvent:
    time: float
    beat: float
    strength: float


@dataclass(frozen=True)
class StemAnalysis:
    path: Path
    sample_rate: int
    duration_seconds: float
    hop_seconds: float
    peak_rms: float
    events: list[StemEvent]


@dataclass(frozen=True)
class NoteEvent:
    start: float
    end: float
    pitch: int
    velocity: int


@dataclass(frozen=True)
class PipelineResult:
    files: list[Path]
    report: dict[str, Any]
