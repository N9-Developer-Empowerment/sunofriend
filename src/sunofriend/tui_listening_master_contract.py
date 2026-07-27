"""Typed native-TUI contract for one comparative Listening Master.

The request deliberately accepts only a loaded TUI snapshot.  It exposes no
mastering targets, filter graph, output path, or release-master switch.  The
production runner therefore remains a thin orchestration layer over the same
fixed-policy Workbench service used by the browser Workbench.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from .tui_model import TuiProjectSnapshot


ListeningMasterProgressCallback = Callable[["ListeningMasterProgress"], None]
LISTENING_MASTER_PROGRESS_TOTAL = 4


@dataclass(frozen=True)
class ListeningMasterRequest:
    """One explicit request to master the snapshot's current balanced control."""

    snapshot: TuiProjectSnapshot

    @classmethod
    def create(
        cls,
        snapshot: TuiProjectSnapshot,
    ) -> "ListeningMasterRequest":
        """Create a parameter-free request from one loaded local project."""

        if not isinstance(snapshot, TuiProjectSnapshot):
            raise TypeError("listening-master request requires a TUI project snapshot")
        return cls(snapshot=snapshot)


@dataclass(frozen=True)
class ListeningMasterProgress:
    """Fixed, path-free progress suitable for TUI status and activity views."""

    completed: int
    total: int
    phase: str
    message: str


@dataclass(frozen=True)
class ListeningMasterResult:
    """Verified private paths plus path-free mastering evidence."""

    status: str
    cache_hit: bool
    balanced_control_path: Path
    master_path: Path
    receipt_path: Path
    cache_key: str
    selection_manifest_sha256: str
    balanced_arrangement_manifest_sha256: str
    listening_master_manifest_sha256: str
    policy: str
    summary: Mapping[str, Any]
    mastered: bool
    release_master: bool
    effects: Mapping[str, bool]
    preflight_ready: tuple[str, ...] = ()

    @property
    def succeeded(self) -> bool:
        return self.status == "complete"


class ListeningMasterRunner(Protocol):
    """Async one-at-a-time runner boundary consumed by the Textual app."""

    async def run(
        self,
        request: ListeningMasterRequest,
        *,
        on_progress: ListeningMasterProgressCallback,
    ) -> ListeningMasterResult:
        """Reuse or create the exact current comparative Listening Master."""


class ListeningMasterError(RuntimeError):
    """Base class for native-TUI Listening Master failures."""


class ListeningMasterBusyError(ListeningMasterError):
    """The same production runner is already serving another request."""


class ListeningMasterUnavailableError(ListeningMasterError):
    """The current selection has no verified balanced v3 control."""


class ListeningMasterConflictError(ListeningMasterError):
    """The selection or balanced control changed during the operation."""


__all__ = [
    "LISTENING_MASTER_PROGRESS_TOTAL",
    "ListeningMasterBusyError",
    "ListeningMasterConflictError",
    "ListeningMasterError",
    "ListeningMasterProgress",
    "ListeningMasterProgressCallback",
    "ListeningMasterRequest",
    "ListeningMasterResult",
    "ListeningMasterRunner",
    "ListeningMasterUnavailableError",
]
