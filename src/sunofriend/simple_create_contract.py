"""Typed orchestration contract for the one-action Simple workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


SimpleProgressCallback = Callable[["SimpleCreateProgress"], None]
SimpleCancellationPredicate = Callable[[], bool]


@dataclass(frozen=True)
class SimpleCreateRequest:
    """One explicit request for automatic MIDI plus a balanced WAV."""

    project: Path
    output_dir: Path
    state_dir: Path | None = None
    soundfont_path: Path | None = None

    @classmethod
    def create(
        cls,
        project: str | Path,
        output_dir: str | Path,
        *,
        state_dir: str | Path | None = None,
        soundfont_path: str | Path | None = None,
    ) -> "SimpleCreateRequest":
        return cls(
            project=Path(project).expanduser().resolve(),
            output_dir=Path(output_dir).expanduser().resolve(),
            state_dir=(
                Path(state_dir).expanduser().resolve()
                if state_dir is not None
                else None
            ),
            soundfont_path=(
                Path(soundfont_path).expanduser().resolve()
                if soundfont_path is not None
                else None
            ),
        )


@dataclass(frozen=True)
class SimpleCreateProgress:
    """Bounded path-free status suitable for a TUI progress view."""

    completed: int
    total: int
    phase: str
    message: str


@dataclass(frozen=True)
class SimpleCreateResult:
    """Final outcome of one Simple request."""

    status: str
    output_dir: Path
    result_root: Path | None
    zip_path: Path | None
    balanced_wav_path: Path | None
    combined_midi_path: Path | None
    manifest_path: Path | None
    selected_count: int
    omitted_count: int
    warnings: tuple[str, ...] = ()

    @property
    def succeeded(self) -> bool:
        return self.status in {"complete", "complete_with_warnings"}

    @property
    def cancelled(self) -> bool:
        return self.status == "cancelled"


class SimpleCreateRunner(Protocol):
    """Injectable runner boundary used by the terminal UI."""

    async def run(
        self,
        request: SimpleCreateRequest,
        *,
        on_progress: SimpleProgressCallback,
        cancellation_requested: SimpleCancellationPredicate | None = None,
    ) -> SimpleCreateResult:
        """Create one automatic result without recording human review."""

    def cancel(self) -> None:
        """Request cancellation at the next safe conversion boundary."""


__all__ = [
    "SimpleCancellationPredicate",
    "SimpleCreateProgress",
    "SimpleCreateRequest",
    "SimpleCreateResult",
    "SimpleCreateRunner",
    "SimpleProgressCallback",
]
