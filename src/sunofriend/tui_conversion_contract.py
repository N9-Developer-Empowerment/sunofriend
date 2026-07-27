"""Typed contract for guided full-project conversion in the local TUI.

The contract is deliberately independent of Textual.  The terminal UI can
inject a fake runner in tests, while the production implementation remains a
thin cancellable orchestration layer over the existing Sunofriend CLI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


ProgressCallback = Callable[["FullConversionProgress"], None]
CancellationPredicate = Callable[[], bool]


@dataclass(frozen=True)
class FullConversionRequest:
    """One explicit request to create a new full-project result tree."""

    project: Path
    output_dir: Path
    conversion_mode: str = "repair"
    evaluate_variants: bool = True
    max_iterations: int = 8
    include_vocals: bool = True

    @classmethod
    def create(
        cls,
        project: str | Path,
        output_dir: str | Path,
        *,
        conversion_mode: str = "repair",
        evaluate_variants: bool = True,
        max_iterations: int = 8,
        include_vocals: bool = True,
    ) -> "FullConversionRequest":
        """Resolve user-entered paths without creating or changing either."""

        return cls(
            project=Path(project).expanduser().resolve(),
            output_dir=Path(output_dir).expanduser().resolve(),
            conversion_mode=str(conversion_mode),
            evaluate_variants=bool(evaluate_variants),
            max_iterations=int(max_iterations),
            include_vocals=bool(include_vocals),
        )


@dataclass(frozen=True)
class FullConversionProgress:
    """Path-free progress suitable for the TUI activity and status views."""

    completed: int
    total: int
    phase: str
    message: str
    current_role: str | None = None


@dataclass(frozen=True)
class FullConversionResult:
    """Outcome of one conversion request.

    ``candidate_roots`` is populated only after a non-cancelled result tree has
    been reloaded through the normal Workbench catalogue projection.
    """

    status: str
    output_dir: Path
    candidate_roots: tuple[Path, ...]
    converted_roles: tuple[str, ...]
    skipped_roles: tuple[str, ...]
    failed_roles: tuple[str, ...]
    proxy_roles: tuple[str, ...]
    warnings: tuple[str, ...]
    summary_paths: tuple[Path, ...]
    source_stem_count: int
    midi_ready_stem_count: int
    candidate_count: int
    preflight_ready: tuple[str, ...] = ()

    @property
    def succeeded(self) -> bool:
        return self.status in {"complete", "partial"}

    @property
    def cancelled(self) -> bool:
        return self.status == "cancelled"


class FullConversionRunner(Protocol):
    """Async runner boundary consumed by the Textual application."""

    async def run(
        self,
        request: FullConversionRequest,
        *,
        on_progress: ProgressCallback,
        cancellation_requested: CancellationPredicate | None = None,
    ) -> FullConversionResult:
        """Run one conversion outside the UI callback and return its result."""

    def cancel(self) -> None:
        """Request bounded termination while preserving partial output."""


class FullConversionError(RuntimeError):
    """Base class for guided conversion failures."""


class FullConversionValidationError(FullConversionError, ValueError):
    """The request violates the fresh-output or project safety contract."""


class FullConversionBusyError(FullConversionError):
    """The same runner is already processing another request."""


__all__ = [
    "CancellationPredicate",
    "FullConversionBusyError",
    "FullConversionError",
    "FullConversionProgress",
    "FullConversionRequest",
    "FullConversionResult",
    "FullConversionRunner",
    "FullConversionValidationError",
    "ProgressCallback",
]
