"""Native-TUI orchestration for the fixed comparative Listening Master.

This module owns no DSP policy.  It reads the append-only Workbench event state,
locates the already verified balanced MIDI control, and delegates artifact
creation and verification to :class:`WorkbenchListeningMasterService`.
Publication is protected by the same selection-manifest and balanced-manifest
compare-and-swap boundary as the browser Workbench.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from .listening_master import check_listening_master_dependencies
from .tui_listening_master_contract import (
    LISTENING_MASTER_PROGRESS_TOTAL,
    ListeningMasterBusyError,
    ListeningMasterConflictError,
    ListeningMasterError,
    ListeningMasterProgress,
    ListeningMasterProgressCallback,
    ListeningMasterRequest,
    ListeningMasterResult,
    ListeningMasterRunner,
    ListeningMasterUnavailableError,
)
from .workbench_artifacts import WorkbenchArtifacts
from .workbench_listening_master import WorkbenchListeningMasterService
from .workbench_store import (
    default_workbench_state_dir,
    fold_workbench_events,
    read_workbench_events_read_only,
)


_PREFLIGHT_READY = ("soundfile", "ffmpeg", "loudnorm")


class ProductionListeningMasterRunner:
    """One-at-a-time async adapter over verified Workbench services."""

    def __init__(self, *, ffmpeg_path: str | Path | None = None) -> None:
        self._ffmpeg_path = (
            Path(ffmpeg_path).expanduser().resolve()
            if ffmpeg_path is not None
            else None
        )
        self._running = False

    async def run(
        self,
        request: ListeningMasterRequest,
        *,
        on_progress: ListeningMasterProgressCallback,
    ) -> ListeningMasterResult:
        if self._running:
            raise ListeningMasterBusyError(
                "a comparative Listening Master is already being prepared"
            )
        if not isinstance(request, ListeningMasterRequest):
            raise TypeError("listening-master runner requires a typed request")

        self._running = True
        try:
            _emit(
                on_progress,
                completed=0,
                phase="inspect",
                message="Finding the current verified song-interpretation control",
            )
            context = await asyncio.to_thread(
                _open_context,
                request,
                self._ffmpeg_path,
            )
            initial = await asyncio.to_thread(_read_current_inputs, context)
            cached = await asyncio.to_thread(
                context.service.cached,
                initial.balanced,
            )
            if cached is not None:
                final = await asyncio.to_thread(_read_current_inputs, context)
                _require_same_inputs(initial, final)
                _require_result_binding(cached, final)
                _emit(
                    on_progress,
                    completed=LISTENING_MASTER_PROGRESS_TOTAL,
                    phase="reused",
                    message="Verified cached comparative Listening Master reused",
                )
                return _build_result(
                    cached,
                    final,
                    cache_hit=True,
                    preflight_ready=(),
                )

            _emit(
                on_progress,
                completed=1,
                phase="preflight",
                message="Checking SoundFile, FFmpeg, and loudnorm",
            )
            try:
                await asyncio.to_thread(
                    check_listening_master_dependencies,
                    self._ffmpeg_path,
                )
            except (OSError, RuntimeError, ValueError) as exc:
                raise ListeningMasterError(
                    "Listening Master dependencies are not ready: "
                    f"{str(exc).strip() or exc.__class__.__name__}"
                ) from exc

            _emit(
                on_progress,
                completed=2,
                phase="build",
                message="Creating the fixed-policy private listening challenger",
            )
            try:
                prepared = await asyncio.to_thread(
                    context.service.prepare,
                    initial.balanced,
                )
            except (OSError, RuntimeError, ValueError) as exc:
                try:
                    failed = await asyncio.to_thread(
                        _read_current_inputs,
                        context,
                    )
                except (
                    ListeningMasterConflictError,
                    ListeningMasterUnavailableError,
                ):
                    raise ListeningMasterConflictError(
                        "The selected arrangement or balanced control changed "
                        "while the Listening Master was being created"
                    ) from exc
                if not _same_inputs(initial, failed):
                    raise ListeningMasterConflictError(
                        "The selected arrangement or balanced control changed "
                        "while the Listening Master was being created"
                    ) from exc
                raise ListeningMasterError(
                    "The comparative Listening Master could not be created"
                ) from exc

            cache_key = str(prepared.get("cache_key", ""))
            token_value = prepared.get("_pending_token")
            pending_token = (
                str(token_value) if isinstance(token_value, str) else None
            )
            try:
                _emit(
                    on_progress,
                    completed=3,
                    phase="verify",
                    message="Rechecking the exact selection and balanced control",
                )
                final = await asyncio.to_thread(_read_current_inputs, context)
                _require_same_inputs(initial, final)
                _require_result_binding(prepared, final)
                if pending_token is None:
                    promoted = await asyncio.to_thread(
                        context.service.cached,
                        final.balanced,
                    )
                    if promoted is None:
                        raise ListeningMasterError(
                            "The verified Listening Master cache disappeared"
                        )
                else:
                    promoted = await asyncio.to_thread(
                        context.service.promote,
                        cache_key,
                        pending_token,
                    )
                    pending_token = None
                _require_result_binding(promoted, final)
                try:
                    published_state = await asyncio.to_thread(
                        _read_current_inputs,
                        context,
                    )
                except (
                    ListeningMasterConflictError,
                    ListeningMasterUnavailableError,
                ) as exc:
                    raise ListeningMasterConflictError(
                        "The selected arrangement or balanced control changed "
                        "while the Listening Master was being published; reload "
                        "the project"
                    ) from exc
                _require_same_inputs(initial, published_state)
                _require_result_binding(promoted, published_state)
                final = published_state
            except BaseException:
                if pending_token is not None:
                    try:
                        await asyncio.to_thread(
                            context.service.discard,
                            cache_key,
                            pending_token,
                        )
                    except (OSError, RuntimeError, ValueError):
                        pass
                raise

            cache_hit = prepared.get("cache_hit") is True
            _emit(
                on_progress,
                completed=LISTENING_MASTER_PROGRESS_TOTAL,
                phase="complete",
                message=(
                    "Verified cached comparative Listening Master reused"
                    if cache_hit
                    else "Comparative Listening Master verified and published"
                ),
            )
            return _build_result(
                promoted,
                final,
                cache_hit=cache_hit,
                preflight_ready=_PREFLIGHT_READY,
            )
        finally:
            self._running = False


class _ListeningMasterContext:
    def __init__(
        self,
        *,
        request: ListeningMasterRequest,
        state_root: Path,
        artifacts: WorkbenchArtifacts,
        service: WorkbenchListeningMasterService,
    ) -> None:
        self.request = request
        self.state_root = state_root
        self.artifacts = artifacts
        self.service = service


class _CurrentInputs:
    def __init__(
        self,
        *,
        selection_sha256: str,
        balanced_manifest_sha256: str,
        balanced: Mapping[str, Any],
    ) -> None:
        self.selection_sha256 = selection_sha256
        self.balanced_manifest_sha256 = balanced_manifest_sha256
        self.balanced = balanced


def _open_context(
    request: ListeningMasterRequest,
    ffmpeg_path: Path | None,
) -> _ListeningMasterContext:
    snapshot = request.snapshot
    state_root = (
        snapshot.config.state_dir
        or default_workbench_state_dir(snapshot.catalog)
    ).resolve()
    artifact_root = state_root / "artifacts"
    if (
        artifact_root.is_symlink()
        or not artifact_root.is_dir()
    ):
        raise ListeningMasterUnavailableError(
            "Create the current balanced song-interpretation WAV before its "
            "comparative Listening Master"
        )
    artifacts = WorkbenchArtifacts(
        artifact_root,
        soundfont_path=snapshot.config.soundfont_path,
    )
    return _ListeningMasterContext(
        request=request,
        state_root=state_root,
        artifacts=artifacts,
        service=WorkbenchListeningMasterService(
            artifact_root,
            ffmpeg_path=ffmpeg_path,
        ),
    )


def _read_current_inputs(context: _ListeningMasterContext) -> _CurrentInputs:
    catalog = context.request.snapshot.catalog
    database = context.state_root / "workbench.sqlite3"
    events = (
        read_workbench_events_read_only(
            database,
            str(catalog["project_id"]),
        )
        if database.is_file()
        else []
    )
    current = fold_workbench_events(catalog, events)
    selection = context.artifacts.decoded_arrangement_selection_manifest(
        catalog,
        current,
    )
    selection_sha256 = str(selection["selection_manifest_sha256"])
    balanced = context.artifacts.cached_balanced_arrangement(catalog, current)
    if balanced is None:
        raise ListeningMasterUnavailableError(
            "Create the current balanced song-interpretation WAV before its "
            "comparative Listening Master"
        )
    balanced_manifest_sha256 = str(balanced.get("manifest_sha256", ""))
    if (
        str(balanced.get("selection_manifest_sha256", ""))
        != selection_sha256
    ):
        raise ListeningMasterConflictError(
            "The balanced song interpretation does not match the current selection"
        )
    return _CurrentInputs(
        selection_sha256=selection_sha256,
        balanced_manifest_sha256=balanced_manifest_sha256,
        balanced=balanced,
    )


def _same_inputs(left: _CurrentInputs, right: _CurrentInputs) -> bool:
    return bool(
        left.selection_sha256 == right.selection_sha256
        and left.balanced_manifest_sha256
        == right.balanced_manifest_sha256
    )


def _require_same_inputs(
    initial: _CurrentInputs,
    final: _CurrentInputs,
) -> None:
    if not _same_inputs(initial, final):
        raise ListeningMasterConflictError(
            "The selected arrangement or balanced song interpretation changed; "
            "reload the project and retry"
        )


def _require_result_binding(
    result: Mapping[str, Any],
    current: _CurrentInputs,
) -> None:
    if (
        str(result.get("selection_manifest_sha256", ""))
        != current.selection_sha256
        or str(
            result.get("balanced_arrangement_manifest_sha256", "")
        )
        != current.balanced_manifest_sha256
    ):
        raise ListeningMasterConflictError(
            "The Listening Master does not bind the exact current control"
        )


def _build_result(
    artifact: Mapping[str, Any],
    current: _CurrentInputs,
    *,
    cache_hit: bool,
    preflight_ready: tuple[str, ...],
) -> ListeningMasterResult:
    try:
        balanced_path = Path(str(current.balanced["preview"]["path"])).resolve()
        master_path = Path(str(artifact["master"]["path"])).resolve()
        receipt_path = Path(str(artifact["receipt"]["path"])).resolve()
        summary = deepcopy(dict(artifact["summary"]))
        effects = {
            str(key): bool(value)
            for key, value in dict(artifact["effects"]).items()
        }
        result = ListeningMasterResult(
            status="complete",
            cache_hit=bool(cache_hit),
            balanced_control_path=balanced_path,
            master_path=master_path,
            receipt_path=receipt_path,
            cache_key=str(artifact["cache_key"]),
            selection_manifest_sha256=current.selection_sha256,
            balanced_arrangement_manifest_sha256=(
                current.balanced_manifest_sha256
            ),
            listening_master_manifest_sha256=str(
                artifact["manifest_sha256"]
            ),
            policy=str(artifact["policy"]),
            summary=summary,
            mastered=artifact["mastered"] is True,
            release_master=artifact["release_master"] is True,
            effects=effects,
            preflight_ready=preflight_ready,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ListeningMasterError(
            "Verified Listening Master result is incomplete"
        ) from exc
    if (
        not result.mastered
        or result.release_master
        or not result.master_path.is_file()
        or not result.receipt_path.is_file()
        or not result.balanced_control_path.is_file()
    ):
        raise ListeningMasterError(
            "Verified Listening Master result is incomplete"
        )
    return result


def _emit(
    callback: ListeningMasterProgressCallback,
    *,
    completed: int,
    phase: str,
    message: str,
) -> None:
    callback(
        ListeningMasterProgress(
            completed=completed,
            total=LISTENING_MASTER_PROGRESS_TOTAL,
            phase=phase,
            message=message,
        )
    )


def create_listening_master_runner() -> ListeningMasterRunner:
    """Return the production native-TUI runner."""

    return ProductionListeningMasterRunner()


__all__ = [
    "ProductionListeningMasterRunner",
    "create_listening_master_runner",
]
