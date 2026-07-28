"""Typed orchestration contract for the one-action Simple workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


SimpleProgressCallback = Callable[["SimpleCreateProgress"], None]
SimpleCancellationPredicate = Callable[[], bool]
SIMPLE_CREATE_CLI_RESULT_SCHEMA = "sunofriend.simple-create-cli-result.v1"


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


def simple_create_result_document(
    result: SimpleCreateResult,
    *,
    project: str | Path,
) -> dict:
    """Return the stable path-bearing CLI summary for one Simple run."""

    return {
        "schema": SIMPLE_CREATE_CLI_RESULT_SCHEMA,
        "status": result.status,
        "source_project": str(Path(project).expanduser().resolve()),
        "workflow": {
            "mode": "simple",
            "automatic": True,
            "review_status": "not_reviewed",
            "review_recommended": True,
            "source_audio_mixed_into_wav": False,
            "release_master": False,
        },
        "outputs": {
            "root": str(result.result_root) if result.result_root is not None else None,
            "listen_first": (
                str(result.balanced_wav_path)
                if result.balanced_wav_path is not None
                else None
            ),
            "combined_midi": (
                str(result.combined_midi_path)
                if result.combined_midi_path is not None
                else None
            ),
            "starter_zip": (
                str(result.zip_path) if result.zip_path is not None else None
            ),
            "receipt": (
                str(result.manifest_path)
                if result.manifest_path is not None
                else None
            ),
        },
        "selected_midi_parts": result.selected_count,
        "omitted_source_roles": result.omitted_count,
        "warnings": list(result.warnings),
        "next_step": (
            "Listen to outputs.listen_first, then open the individual MIDI "
            "files in GarageBand. Use Studio only if you want to compare "
            "alternatives or record feedback."
            if result.succeeded
            else "The automatic result is incomplete; inspect the warnings and "
            "use a new output path for any retry."
        ),
    }


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
    "SIMPLE_CREATE_CLI_RESULT_SCHEMA",
    "SimpleCancellationPredicate",
    "SimpleCreateProgress",
    "SimpleCreateRequest",
    "SimpleCreateResult",
    "SimpleCreateRunner",
    "SimpleProgressCallback",
    "simple_create_result_document",
]
