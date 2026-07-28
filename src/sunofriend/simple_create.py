"""Production runner for Sunofriend's one-action Simple workflow."""

from __future__ import annotations

import asyncio
from typing import Any

from .automatic_selection import plan_automatic_selection
from .simple_create_contract import (
    SimpleCancellationPredicate,
    SimpleCreateProgress,
    SimpleCreateRequest,
    SimpleCreateResult,
    SimpleCreateRunner,
    SimpleProgressCallback,
)
from .simple_result import SIMPLE_RESULT_DIRECTORY, build_simple_result
from .tui_conversion import create_full_conversion_runner
from .tui_conversion_contract import FullConversionRequest, FullConversionRunner
from .tui_model import TuiProjectConfig, load_tui_project
from .workbench_store import default_workbench_state_dir


_PROGRESS_TOTAL = 6


class ProductionSimpleCreateRunner:
    """Convert, choose exact production primaries, render and package."""

    def __init__(
        self,
        *,
        conversion_runner: FullConversionRunner | None = None,
    ) -> None:
        self._conversion_runner = conversion_runner or create_full_conversion_runner()
        self._running = False

    async def run(
        self,
        request: SimpleCreateRequest,
        *,
        on_progress: SimpleProgressCallback,
        cancellation_requested: SimpleCancellationPredicate | None = None,
    ) -> SimpleCreateResult:
        if self._running:
            raise RuntimeError("a Simple song is already being created")
        self._running = True
        try:
            _emit(
                on_progress,
                0,
                "preflight",
                "Checking the source folder and local audio tools",
            )
            conversion_request = FullConversionRequest.create(
                request.project,
                request.output_dir,
                conversion_mode="repair",
                evaluate_variants=True,
                include_vocals=True,
            )

            def conversion_progress(progress: Any) -> None:
                message = str(getattr(progress, "message", "") or "Converting stems")
                role = str(getattr(progress, "current_role", "") or "")
                if role:
                    message = f"{message} · {role}"
                _emit(on_progress, 1, "convert", message)

            _emit(
                on_progress,
                1,
                "convert",
                "Converting all supported instrumental and vocal stems",
            )
            conversion = await self._conversion_runner.run(
                conversion_request,
                on_progress=conversion_progress,
                cancellation_requested=cancellation_requested,
            )
            if conversion.cancelled:
                return SimpleCreateResult(
                    status="cancelled",
                    output_dir=request.output_dir,
                    result_root=None,
                    zip_path=None,
                    balanced_wav_path=None,
                    combined_midi_path=None,
                    manifest_path=None,
                    selected_count=0,
                    omitted_count=0,
                    warnings=tuple(conversion.warnings),
                )
            if not conversion.succeeded:
                raise RuntimeError(
                    "conversion finished without any verified MIDI result"
                )
            if cancellation_requested is not None and cancellation_requested():
                return SimpleCreateResult(
                    status="cancelled",
                    output_dir=request.output_dir,
                    result_root=None,
                    zip_path=None,
                    balanced_wav_path=None,
                    combined_midi_path=None,
                    manifest_path=None,
                    selected_count=0,
                    omitted_count=0,
                    warnings=tuple(conversion.warnings),
                )

            _emit(
                on_progress,
                2,
                "choose-defaults",
                "Matching exact production primaries to their source stems",
            )
            snapshot = await asyncio.to_thread(
                load_tui_project,
                TuiProjectConfig.create(
                    request.project,
                    candidate_roots=tuple(conversion.candidate_roots),
                    state_dir=request.state_dir,
                    soundfont_path=request.soundfont_path,
                ),
            )
            selection = await asyncio.to_thread(
                plan_automatic_selection,
                snapshot.catalog,
                conversion.summary_paths,
                result_root=request.output_dir,
            )
            _emit(
                on_progress,
                3,
                "render-midi",
                f"Building {len(selection.selected)} exact MIDI parts and one GM proxy",
            )
            state_root = request.state_dir or default_workbench_state_dir(
                snapshot.catalog
            )
            _emit(
                on_progress,
                4,
                "render-wav",
                "Rendering the source-referenced balanced MIDI interpretation",
            )
            result = await asyncio.to_thread(
                build_simple_result,
                snapshot.catalog,
                selection,
                destination=request.output_dir / SIMPLE_RESULT_DIRECTORY,
                artifact_cache_root=state_root / "artifacts",
                soundfont_path=request.soundfont_path,
            )
            _emit(
                on_progress,
                5,
                "package",
                "Verifying the MIDI, WAV, receipt and starter ZIP",
            )
            warnings = list(conversion.warnings)
            if selection.omitted:
                warnings.append(
                    f"{len(selection.omitted)} source role(s) had no safe automatic "
                    "primary and are listed in the result receipt"
                )
            if conversion.proxy_roles:
                warnings.append(
                    "Conservative creative proxy role(s) need listening review: "
                    + ", ".join(conversion.proxy_roles)
                )
            status = "complete_with_warnings" if warnings else "complete"
            _emit(
                on_progress,
                _PROGRESS_TOTAL,
                "complete",
                "Automatic MIDI and balanced WAV are ready",
            )
            return SimpleCreateResult(
                status=status,
                output_dir=request.output_dir,
                result_root=result.root,
                zip_path=result.zip_path,
                balanced_wav_path=result.balanced_wav_path,
                combined_midi_path=result.combined_midi_path,
                manifest_path=result.manifest_path,
                selected_count=result.selected_count,
                omitted_count=result.omitted_count,
                warnings=tuple(dict.fromkeys(warnings)),
            )
        finally:
            self._running = False

    def cancel(self) -> None:
        self._conversion_runner.cancel()


def create_simple_create_runner() -> SimpleCreateRunner:
    """Return the production Simple workflow runner."""

    return ProductionSimpleCreateRunner()


def _emit(
    callback: SimpleProgressCallback,
    completed: int,
    phase: str,
    message: str,
) -> None:
    try:
        callback(
            SimpleCreateProgress(
                completed=max(0, min(_PROGRESS_TOTAL, int(completed))),
                total=_PROGRESS_TOTAL,
                phase=str(phase),
                message=str(message)[:500],
            )
        )
    except Exception:
        # Display callbacks must never change the production audio operation.
        return


__all__ = [
    "ProductionSimpleCreateRunner",
    "create_simple_create_runner",
]
