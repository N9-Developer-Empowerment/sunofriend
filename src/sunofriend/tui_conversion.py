"""Cancellable production conversion runner used by the guided local TUI.

This module does not transcribe audio itself.  It launches the current
Sunofriend CLI with explicit argv, first for the whole instrumental folder and
then for each discovered lead/backing-vocal stem.  That process boundary keeps
the existing production policies intact and gives the TUI a safe way to stop a
long conversion without blocking its event loop.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .drum_roles import resolve_drum_role_policy
from .project_audio_inputs import (
    inspect_project_audio_inputs,
    prepared_project_input_problem,
)
from .tui_conversion_contract import (
    CancellationPredicate,
    FullConversionBusyError,
    FullConversionError,
    FullConversionProgress,
    FullConversionRequest,
    FullConversionResult,
    FullConversionRunner,
    FullConversionValidationError,
    ProgressCallback,
)


_CONVERSION_MODES = frozenset({"exact", "repair", "reconstruct"})
_ROLE_PROGRESS = re.compile(
    r"^(?P<role>[a-z][a-z0-9_]*): "
    r"(?P<state>ok|skipped|ERROR)(?:\s|$)"
)
_WARNING_LINE = re.compile(
    r"^(?:sunofriend:|warning:|evaluation warning:)",
    re.IGNORECASE,
)
# Basic Pitch logs these optional-backend notices even though Sunofriend pins
# and uses its ONNX path. They are not an incomplete conversion or user action.
_OPTIONAL_BASIC_PITCH_BACKEND_WARNING = re.compile(
    r"^WARNING:root:(?:tflite-runtime|Tensorflow) is not installed\.",
)
_PATH_FRAGMENT = re.compile(r"(?<![A-Za-z0-9])(?:/[^ \t\r\n:]+)+")
_TOKEN_FRAGMENT = re.compile(r"([#?&]token=)[^&#\s]+", re.IGNORECASE)
_MAX_CHILD_LINE = 500
_MAX_WARNING = 240
_MAX_SUMMARY_BYTES = 16 * 1024 * 1024
_TERMINATE_GRACE_SECONDS = 3.0


@dataclass(frozen=True)
class PlannedVocalConversion:
    """One separately published vocal transcription."""

    source: Path
    source_role: str
    cli_role: str
    output_token: str
    progress_label: str


@dataclass(frozen=True)
class FullConversionPlan:
    """Read-only plan derived from the same role map as ``listen-all``."""

    project: Path
    output_dir: Path
    instrumental_roles: tuple[str, ...]
    vocal_jobs: tuple[PlannedVocalConversion, ...]
    unsupported_roles: tuple[str, ...]
    proxy_roles: tuple[str, ...]
    shadowed_roles: tuple[str, ...]
    warnings: tuple[str, ...]
    source_stem_count: int

    @property
    def total(self) -> int:
        return len(self.instrumental_roles) + len(self.vocal_jobs)


@dataclass(frozen=True)
class _CommandOutcome:
    return_code: int
    warning_lines: tuple[str, ...]


@dataclass(frozen=True)
class _ReloadEvidence:
    source_stem_count: int
    midi_ready_stem_count: int
    candidate_count: int
    midi_ready_roles: tuple[str, ...] = ()


def plan_full_conversion(request: FullConversionRequest) -> FullConversionPlan:
    """Build a deterministic full-project plan without changing the filesystem."""

    _validate_request(request)

    # These are the production listen-all definitions.  Importing them here
    # ensures the TUI cannot silently drift from new supported role engines.
    from .listen_all import (
        CONSERVATIVE_ROLE_ENGINES,
        DRUM_PARTS,
        PITCHED_PARTS,
        _find_stem,
    )
    from .workbench_catalog import infer_role

    instrumental: list[str] = []
    used_sources: set[Path] = set()
    seen_roles: set[str] = set()
    for role in [*DRUM_PARTS, *PITCHED_PARTS]:
        source = _find_stem(request.project, role)
        if source is None or role in seen_roles:
            continue
        seen_roles.add(role)
        instrumental.append(role)
        used_sources.add(source.resolve())

    # Reconstruct mode can deliberately add chart/activity-derived pads from a
    # keys stem.  Repair (the guided default) never claims that as observed.
    if request.conversion_mode == "reconstruct":
        keys = _find_stem(request.project, "keys")
        pads = _find_stem(request.project, "pads")
        if keys is not None and pads is None:
            instrumental.append("pads")

    inventory = inspect_project_audio_inputs(request.project)
    vocal_sources: list[tuple[Path, str, str]] = []
    unsupported: list[str] = []
    source_stem_count = 0
    for source_row in inventory.sources:
        source = source_row.path
        role = (
            source_row.role
            if inventory.prepared_project
            else infer_role(source.stem) or "unclassified"
        )
        if role == "metronome":
            continue
        source_stem_count += 1
        resolved = source.resolve()
        if resolved in used_sources:
            continue
        if request.include_vocals and role == "vocals":
            vocal_sources.append((source, "vocals", "lead"))
            continue
        if request.include_vocals and role == "backing_vocals":
            vocal_sources.append((source, "backing_vocals", "backing"))
            continue
        unsupported.append(role)

    vocal_jobs: list[PlannedVocalConversion] = []
    role_totals: dict[str, int] = {}
    for _source, source_role, _cli_role in vocal_sources:
        role_totals[source_role] = role_totals.get(source_role, 0) + 1
    role_seen: dict[str, int] = {}
    for source, source_role, cli_role in vocal_sources:
        number = role_seen.get(source_role, 0) + 1
        role_seen[source_role] = number
        suffix = f"-{number:02d}" if role_totals[source_role] > 1 else ""
        vocal_jobs.append(
            PlannedVocalConversion(
                source=source.resolve(),
                source_role=source_role,
                cli_role=cli_role,
                output_token=f"{cli_role}{suffix}",
                progress_label=(
                    f"{source_role} {number}"
                    if role_totals[source_role] > 1
                    else source_role
                ),
            )
        )

    drum_policy = resolve_drum_role_policy(instrumental)
    return FullConversionPlan(
        project=request.project,
        output_dir=request.output_dir,
        instrumental_roles=tuple(instrumental),
        vocal_jobs=tuple(vocal_jobs),
        unsupported_roles=tuple(sorted(set(unsupported))),
        proxy_roles=tuple(
            role for role in instrumental if role in CONSERVATIVE_ROLE_ENGINES
        ),
        shadowed_roles=tuple(drum_policy["shadowed_roles"]),
        warnings=tuple(drum_policy["warnings"]),
        source_stem_count=source_stem_count,
    )


class ProductionFullConversionRunner:
    """One-at-a-time async runner over the production Sunofriend CLI."""

    def __init__(self) -> None:
        self._running = False
        self._cancel_event = threading.Event()
        self._process: asyncio.subprocess.Process | None = None

    async def run(
        self,
        request: FullConversionRequest,
        *,
        on_progress: ProgressCallback,
        cancellation_requested: CancellationPredicate | None = None,
    ) -> FullConversionResult:
        if self._running:
            raise FullConversionBusyError("a full conversion is already running")
        self._running = True
        self._cancel_event.clear()
        try:
            plan = plan_full_conversion(request)
            if plan.total == 0:
                raise FullConversionValidationError(
                    "No supported instrumental or vocal stems were found"
                )

            _emit(
                on_progress,
                FullConversionProgress(
                    completed=0,
                    total=plan.total,
                    phase="preflight",
                    message="Checking local convert and transcribe capabilities",
                ),
            )
            try:
                preflight = await self._run_preflight()
            except Exception as exc:
                raise FullConversionValidationError(
                    "The local convert/transcribe preflight could not complete. "
                    "No output folder was created."
                ) from exc
            _require_preflight(preflight, "transcribe")
            _emit(
                on_progress,
                FullConversionProgress(
                    completed=0,
                    total=plan.total,
                    phase="preflight",
                    message="Local transcribe capability is ready",
                ),
            )
            _require_preflight(preflight, "convert")
            _emit(
                on_progress,
                FullConversionProgress(
                    completed=0,
                    total=plan.total,
                    phase="preflight",
                    message="Local convert capability is ready",
                ),
            )
            if self._is_cancelled(cancellation_requested):
                return _cancelled_result(plan)

            _reserve_output_root(plan.output_dir)
            _emit(
                on_progress,
                FullConversionProgress(
                    completed=0,
                    total=plan.total,
                    phase="reserved",
                    message="Fresh private output folder reserved",
                ),
            )

            return await self._run_reserved(
                request,
                plan,
                on_progress=on_progress,
                cancellation_requested=cancellation_requested,
            )
        finally:
            self._process = None
            self._running = False

    def cancel(self) -> None:
        """Request cancellation and signal the active process immediately."""

        self._cancel_event.set()
        process = self._process
        if process is not None and process.returncode is None:
            _signal_process(process, signal.SIGTERM)

    async def _run_reserved(
        self,
        request: FullConversionRequest,
        plan: FullConversionPlan,
        *,
        on_progress: ProgressCallback,
        cancellation_requested: CancellationPredicate | None,
    ) -> FullConversionResult:
        converted: list[str] = []
        skipped: list[str] = list(plan.unsupported_roles)
        failed: list[str] = []
        warnings: list[str] = []
        warnings.extend(
            f"{role} uses the conservative "
            f"{_proxy_engine(role)} engine and remains review-required"
            for role in plan.proxy_roles
        )
        warnings.extend(
            f"{role} has no guided conversion engine and was not changed"
            for role in plan.unsupported_roles
        )
        summaries: list[Path] = []
        effective_shadowed_roles: tuple[str, ...] = ()
        completed = 0

        if plan.instrumental_roles:
            current_index = 0
            reported: set[str] = set()
            _emit(
                on_progress,
                FullConversionProgress(
                    completed=completed,
                    total=plan.total,
                    phase="instrumental",
                    message="Converting instrumental stems with listen-all",
                    current_role=plan.instrumental_roles[0],
                ),
            )

            def instrumental_line(line: str) -> None:
                nonlocal completed, current_index
                match = _ROLE_PROGRESS.match(line)
                if match is None:
                    return
                role = match.group("role")
                if role not in plan.instrumental_roles or role in reported:
                    return
                reported.add(role)
                completed += 1
                state = match.group("state").lower()
                message = {
                    "ok": f"{role} MIDI candidates created",
                    "skipped": f"{role} was skipped after source analysis",
                    "error": f"{role} conversion failed; other roles continue",
                }[state]
                _emit(
                    on_progress,
                    FullConversionProgress(
                        completed=completed,
                        total=plan.total,
                        phase="instrumental",
                        message=message,
                        current_role=role,
                    ),
                )
                current_index = max(
                    current_index,
                    plan.instrumental_roles.index(role) + 1,
                )
                if current_index < len(plan.instrumental_roles):
                    next_role = plan.instrumental_roles[current_index]
                    _emit(
                        on_progress,
                        FullConversionProgress(
                            completed=completed,
                            total=plan.total,
                            phase="instrumental",
                            message=f"Converting {next_role}",
                            current_role=next_role,
                        ),
                    )

            command = self._listen_all_command(request)
            outcome = await self._execute_command(
                command,
                on_line=instrumental_line,
                cancellation_requested=cancellation_requested,
            )
            if self._is_cancelled(cancellation_requested):
                return _cancelled_result(
                    plan,
                    converted=converted,
                    skipped=skipped,
                    failed=failed,
                    warnings=warnings,
                    summaries=summaries,
                )
            summary_path = (
                plan.output_dir
                / f"mode_{request.conversion_mode}"
                / "listen_all_summary.json"
            )
            instrumental_summary = _read_summary_optional(summary_path)
            if instrumental_summary is not None:
                summaries.append(summary_path)
                viable_instrumental_roles: list[str] = []
                for role in plan.instrumental_roles:
                    item = (
                        instrumental_summary.get("parts", {}).get(role, {})
                        if isinstance(instrumental_summary.get("parts"), Mapping)
                        else {}
                    )
                    status = str(item.get("status") or "missing")
                    if status == "ok" and _reported_midi_exists(
                        item.get("midi"),
                        plan.output_dir,
                    ):
                        _append_unique(converted, role)
                        note_count = item.get("notes")
                        if (
                            isinstance(note_count, int)
                            and not isinstance(note_count, bool)
                            and note_count > 0
                        ):
                            viable_instrumental_roles.append(role)
                    elif status.startswith("skipped:"):
                        _append_unique(skipped, role)
                    else:
                        _append_unique(failed, role)
                        if status == "ok":
                            warnings.append(
                                f"{role} reported success without a verified "
                                "MIDI file inside the fresh output"
                            )
                    if role not in reported:
                        completed += 1
                        _emit(
                            on_progress,
                            FullConversionProgress(
                                completed=min(completed, plan.total),
                                total=plan.total,
                                phase="instrumental",
                                message=_summary_role_message(role, status),
                                current_role=role,
                            ),
                        )
                effective_policy = resolve_drum_role_policy(
                    viable_instrumental_roles
                )
                effective_shadowed_roles = tuple(
                    effective_policy["shadowed_roles"]
                )
            else:
                for role in plan.instrumental_roles:
                    _append_unique(failed, role)
                    if role not in reported:
                        completed += 1
                        _emit(
                            on_progress,
                            FullConversionProgress(
                                completed=min(completed, plan.total),
                                total=plan.total,
                                phase="instrumental",
                                message=(
                                    f"{role} conversion did not publish a "
                                    "verified summary"
                                ),
                                current_role=role,
                            ),
                        )
                warnings.append(
                    "Instrumental conversion did not publish its verified summary"
                )
            warnings.extend(outcome.warning_lines)
            if outcome.return_code not in {0, 1}:
                warnings.append(
                    "Instrumental conversion exited before a complete result"
                )

        for vocal_job in plan.vocal_jobs:
            if self._is_cancelled(cancellation_requested):
                return _cancelled_result(
                    plan,
                    converted=converted,
                    skipped=skipped,
                    failed=failed,
                    warnings=warnings,
                    summaries=summaries,
                )
            _emit(
                on_progress,
                FullConversionProgress(
                    completed=completed,
                    total=plan.total,
                    phase="vocal",
                    message=f"Extracting {vocal_job.progress_label} melody",
                    current_role=vocal_job.progress_label,
                ),
            )
            vocal_out = (
                plan.output_dir / "vocals" / vocal_job.output_token
            )
            outcome = await self._execute_command(
                self._vocal_command(request, vocal_job, vocal_out),
                on_line=lambda _line: None,
                cancellation_requested=cancellation_requested,
            )
            if self._is_cancelled(cancellation_requested):
                return _cancelled_result(
                    plan,
                    converted=converted,
                    skipped=skipped,
                    failed=failed,
                    warnings=warnings,
                    summaries=summaries,
                )
            completed += 1
            summary_path = vocal_out / "vocal_summary.json"
            vocal_summary = _read_summary_optional(summary_path)
            if vocal_summary is not None:
                summaries.append(summary_path)
            if (
                outcome.return_code == 0
                and vocal_summary is not None
                and _vocal_has_midi(vocal_summary, plan.output_dir)
            ):
                _append_unique(converted, vocal_job.source_role)
                message = f"{vocal_job.progress_label} MIDI candidates created"
            elif outcome.return_code == 0 and vocal_summary is not None:
                _append_unique(skipped, vocal_job.source_role)
                message = (
                    f"{vocal_job.progress_label} had no publishable note evidence"
                )
            else:
                _append_unique(failed, vocal_job.source_role)
                message = f"{vocal_job.progress_label} conversion failed"
            warnings.extend(outcome.warning_lines)
            _emit(
                on_progress,
                FullConversionProgress(
                    completed=min(completed, plan.total),
                    total=plan.total,
                    phase="vocal",
                    message=message,
                    current_role=vocal_job.progress_label,
                ),
            )

        if self._is_cancelled(cancellation_requested):
            return _cancelled_result(
                plan,
                converted=converted,
                skipped=skipped,
                failed=failed,
                warnings=warnings,
                summaries=summaries,
            )

        _emit(
            on_progress,
            FullConversionProgress(
                completed=plan.total,
                total=plan.total,
                phase="reloading",
                message="Reloading the new MIDI candidates for review",
            ),
        )
        reload_evidence: _ReloadEvidence | None
        try:
            reload_evidence = await self._reload_candidates(request, plan)
        except Exception:
            reload_evidence = None
            warnings.append(
                "Conversion artifacts were preserved, but candidate reload failed"
            )

        candidate_roots: tuple[Path, ...] = ()
        missing_reloaded_roles: tuple[str, ...] = ()
        if reload_evidence is not None:
            if reload_evidence.candidate_count > 0:
                candidate_roots = (plan.output_dir,)
            elif converted:
                warnings.append(
                    "Converted roles were reported, but Workbench found no MIDI candidates"
                )
            missing_reloaded_roles = tuple(
                sorted(
                    set(converted) - set(reload_evidence.midi_ready_roles)
                )
            )
            if missing_reloaded_roles:
                warnings.append(
                    "Workbench reload found no MIDI candidate for converted "
                    f"role(s): {', '.join(missing_reloaded_roles)}"
                )

        if (
            failed
            or skipped
            or missing_reloaded_roles
            or reload_evidence is None
        ):
            status = "partial" if converted else "failed"
        else:
            status = "complete"
        if (
            reload_evidence is not None
            and converted
            and reload_evidence.candidate_count == 0
        ):
            status = "partial"

        result = FullConversionResult(
            status=status,
            output_dir=plan.output_dir,
            candidate_roots=candidate_roots,
            converted_roles=tuple(converted),
            skipped_roles=tuple(skipped),
            failed_roles=tuple(failed),
            proxy_roles=plan.proxy_roles,
            warnings=tuple(_deduplicate(warnings)),
            summary_paths=tuple(summaries),
            source_stem_count=(
                reload_evidence.source_stem_count
                if reload_evidence is not None
                else plan.source_stem_count
            ),
            midi_ready_stem_count=(
                reload_evidence.midi_ready_stem_count
                if reload_evidence is not None
                else 0
            ),
            candidate_count=(
                reload_evidence.candidate_count
                if reload_evidence is not None
                else 0
            ),
            preflight_ready=("transcribe", "convert"),
            shadowed_roles=effective_shadowed_roles,
        )
        _emit(
            on_progress,
            FullConversionProgress(
                completed=plan.total,
                total=plan.total,
                phase=result.status,
                message=(
                    "Conversion finished and new MIDI candidates are ready"
                    if result.succeeded
                    else "Conversion finished without a reviewable MIDI result"
                ),
            ),
        )
        return result

    async def _run_preflight(self) -> Mapping[str, Any]:
        from .diagnostics import collect_diagnostics

        return await asyncio.to_thread(
            collect_diagnostics,
            check_playback=False,
        )

    async def _reload_candidates(
        self,
        request: FullConversionRequest,
        plan: FullConversionPlan,
    ) -> _ReloadEvidence:
        from .tui_model import TuiProjectConfig, load_tui_project

        snapshot = await asyncio.to_thread(
            load_tui_project,
            TuiProjectConfig.create(
                request.project,
                candidate_roots=(plan.output_dir,),
            ),
        )
        counts = snapshot.document["counts"]
        output_candidate_count = 0
        output_ready_stems = 0
        output_ready_roles: set[str] = set()
        for stem in snapshot.catalog.get("stems", []):
            candidates = [
                candidate
                for candidate in stem.get("candidates", [])
                if _path_is_inside(
                    candidate.get("midi_path"),
                    plan.output_dir,
                )
            ]
            output_candidate_count += len(candidates)
            output_ready_stems += bool(candidates)
            if candidates:
                output_ready_roles.add(str(stem.get("role") or "unclassified"))
        return _ReloadEvidence(
            source_stem_count=int(counts["stem_count"]),
            midi_ready_stem_count=int(output_ready_stems),
            candidate_count=int(output_candidate_count),
            midi_ready_roles=tuple(sorted(output_ready_roles)),
        )

    async def _execute_command(
        self,
        command: Sequence[str],
        *,
        on_line: Callable[[str], None],
        cancellation_requested: CancellationPredicate | None,
    ) -> _CommandOutcome:
        """Run one unbuffered child while polling cancellation during silence."""

        environment = dict(os.environ)
        environment["PYTHONUNBUFFERED"] = "1"
        process_kwargs: dict[str, Any] = {}
        if os.name == "posix":
            process_kwargs["start_new_session"] = True
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=environment,
                **process_kwargs,
            )
        except OSError:
            return _CommandOutcome(
                return_code=127,
                warning_lines=("The local Sunofriend process could not start",),
            )
        self._process = process
        assert process.stdout is not None
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        warnings: list[str] = []

        async def read_output() -> None:
            try:
                while True:
                    raw = await process.stdout.readline()
                    if not raw:
                        break
                    await queue.put(
                        raw.decode("utf-8", errors="replace")[:_MAX_CHILD_LINE]
                    )
            finally:
                await queue.put(None)

        reader = asyncio.create_task(read_output())
        waiter = asyncio.create_task(process.wait())
        stream_closed = False
        termination_started: float | None = None
        killed = False
        loop = asyncio.get_running_loop()
        try:
            while not stream_closed or not waiter.done():
                if self._is_cancelled(cancellation_requested):
                    if termination_started is None:
                        termination_started = loop.time()
                        _signal_process(process, signal.SIGTERM)
                    elif (
                        not waiter.done()
                        and not killed
                        and loop.time() - termination_started
                        >= _TERMINATE_GRACE_SECONDS
                    ):
                        killed = True
                        _signal_process(
                            process,
                            getattr(signal, "SIGKILL", signal.SIGTERM),
                        )
                try:
                    line = await asyncio.wait_for(queue.get(), timeout=0.10)
                except asyncio.TimeoutError:
                    continue
                if line is None:
                    stream_closed = True
                    continue
                clean = line.strip()
                if not clean:
                    continue
                try:
                    on_line(clean)
                except Exception:
                    warnings.append(
                        "A progress observer failed; conversion continued"
                    )
                if (
                    _WARNING_LINE.match(clean)
                    and not _OPTIONAL_BASIC_PITCH_BACKEND_WARNING.match(clean)
                ):
                    warning = _safe_child_warning(clean)
                    if warning:
                        warnings.append(warning)
            return_code = await waiter
        except asyncio.CancelledError:
            await _terminate_and_reap_process(process, waiter)
            raise
        finally:
            if not reader.done():
                reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
            if not waiter.done():
                waiter.cancel()
            await asyncio.gather(waiter, return_exceptions=True)
            if self._process is process:
                self._process = None
        return _CommandOutcome(
            return_code=int(return_code),
            warning_lines=tuple(_deduplicate(warnings)),
        )

    def _listen_all_command(
        self,
        request: FullConversionRequest,
    ) -> tuple[str, ...]:
        command = [
            sys.executable,
            "-u",
            "-m",
            "sunofriend",
            "listen-all",
            str(request.project),
            "--out-dir",
            str(request.output_dir),
            "--conversion-mode",
            request.conversion_mode,
            "--max-iterations",
            str(request.max_iterations),
        ]
        if request.evaluate_variants:
            command.append("--evaluate-variants")
        return tuple(command)

    def _vocal_command(
        self,
        request: FullConversionRequest,
        job: PlannedVocalConversion,
        output_dir: Path,
    ) -> tuple[str, ...]:
        from .metadata import infer_project_metadata
        from .source_project import load_prepared_project_context

        prepared_context = load_prepared_project_context(request.project)
        metadata = (
            prepared_context.metadata
            if prepared_context is not None
            else infer_project_metadata(request.project)
        )
        command = [
            sys.executable,
            "-u",
            "-m",
            "sunofriend",
            "vocal-melody",
            str(job.source),
            "--role",
            job.cli_role,
            "--out-dir",
            str(output_dir),
        ]
        # A prepared active vocal can live under a content-addressed DERIVED
        # path whose parent name contains no musical metadata.  Pass the
        # project-bound values explicitly instead of asking vocal-melody to
        # infer them from that implementation path.
        if metadata.bpm is not None:
            command.extend(("--bpm", str(float(metadata.bpm))))
        if metadata.tuning_hz is not None:
            command.extend(("--tuning-hz", str(float(metadata.tuning_hz))))
        if metadata.key:
            command.extend(("--key", metadata.key))
        if prepared_context is not None and prepared_context.chord_document:
            command.extend(
                ("--chords-pdf", str(prepared_context.chord_document))
            )
        return tuple(command)

    def _is_cancelled(
        self,
        cancellation_requested: CancellationPredicate | None,
    ) -> bool:
        if self._cancel_event.is_set():
            return True
        if cancellation_requested is None:
            return False
        try:
            return bool(cancellation_requested())
        except Exception:
            # A broken cancellation channel fails safe instead of allowing an
            # unattended long-running local model process to continue.
            self._cancel_event.set()
            return True


def create_full_conversion_runner() -> FullConversionRunner:
    """Return the production runner behind the TUI injection boundary."""

    return ProductionFullConversionRunner()


def _validate_request(request: FullConversionRequest) -> None:
    if not request.project.is_dir():
        raise FullConversionValidationError(
            "The stem project directory does not exist"
        )
    input_problem = prepared_project_input_problem(request.project)
    if input_problem is not None:
        raise FullConversionValidationError(input_problem)
    if request.conversion_mode not in _CONVERSION_MODES:
        raise FullConversionValidationError(
            "conversion mode must be exact, repair, or reconstruct"
        )
    if not 1 <= int(request.max_iterations) <= 100:
        raise FullConversionValidationError(
            "maximum iterations must be between 1 and 100"
        )
    if os.path.lexists(request.output_dir):
        raise FullConversionValidationError(
            "The output folder already exists; choose a new folder so no "
            "earlier result can be overwritten"
        )
    if not request.output_dir.parent.is_dir():
        raise FullConversionValidationError(
            "The output folder's parent directory does not exist"
        )
    project = request.project.resolve()
    output = request.output_dir.resolve()
    if output == project or project in output.parents:
        raise FullConversionValidationError(
            "The output folder must be outside the source stem project"
        )


def _reserve_output_root(output: Path) -> None:
    try:
        output.mkdir(mode=0o700, parents=False, exist_ok=False)
        output.chmod(0o700)
    except FileExistsError as exc:
        raise FullConversionValidationError(
            "The output folder was created by another process; choose a new folder"
        ) from exc
    except OSError as exc:
        raise FullConversionValidationError(
            "The fresh output folder could not be created"
        ) from exc


def _require_preflight(report: Mapping[str, Any], capability: str) -> None:
    key = f"{capability}_ready"
    if bool(report.get(key)):
        return
    missing = report.get(f"missing_{capability}_packages") or []
    suffix = (
        f" Missing local packages: {', '.join(str(item) for item in missing)}."
        if isinstance(missing, list) and missing
        else ""
    )
    raise FullConversionValidationError(
        f"Local {capability} capability is not ready.{suffix} "
        f"Run `sunofriend doctor --require {capability}`. No model or package "
        "was downloaded and no output folder was created."
    )


def _cancelled_result(
    plan: FullConversionPlan,
    *,
    converted: Sequence[str] = (),
    skipped: Sequence[str] = (),
    failed: Sequence[str] = (),
    warnings: Sequence[str] = (),
    summaries: Sequence[Path] = (),
) -> FullConversionResult:
    output_exists = plan.output_dir.is_dir()
    message = (
        "Cancellation preserved the incomplete output folder for inspection; "
        "it is not loaded as a candidate root"
        if output_exists
        else "Cancellation completed before an output folder was created"
    )
    return FullConversionResult(
        status="cancelled",
        output_dir=plan.output_dir,
        candidate_roots=(),
        converted_roles=tuple(converted),
        skipped_roles=tuple(skipped),
        failed_roles=tuple(failed),
        proxy_roles=plan.proxy_roles,
        warnings=tuple(_deduplicate([*warnings, message])),
        summary_paths=tuple(summaries),
        source_stem_count=plan.source_stem_count,
        midi_ready_stem_count=0,
        candidate_count=0,
        preflight_ready=("transcribe", "convert"),
        shadowed_roles=plan.shadowed_roles,
    )


def _read_summary_optional(path: Path) -> dict[str, Any] | None:
    try:
        stat = path.stat()
        if not path.is_file() or stat.st_size > _MAX_SUMMARY_BYTES:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _vocal_has_midi(summary: Mapping[str, Any], root: Path) -> bool:
    candidates: list[Any] = [summary.get("primary_midi")]
    variants = summary.get("variants")
    if isinstance(variants, Mapping):
        for item in variants.values():
            if isinstance(item, Mapping) and item.get("status") == "ok":
                candidates.append(item.get("midi"))
    for value in candidates:
        if _reported_midi_exists(value, root):
            return True
    return False


def _reported_midi_exists(value: Any, root: Path) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        path = Path(value).expanduser().resolve()
    except OSError:
        return False
    return path.is_file() and root in path.parents


def _summary_role_message(role: str, status: str) -> str:
    if status == "ok":
        return f"{role} MIDI candidates created"
    if status.startswith("skipped:"):
        return f"{role} was skipped after source analysis"
    return f"{role} conversion did not publish a usable result"


def _proxy_engine(role: str) -> str:
    from .listen_all import CONSERVATIVE_ROLE_ENGINES

    return str(CONSERVATIVE_ROLE_ENGINES.get(role, "specialist"))


def _safe_child_warning(value: str) -> str:
    line = _TOKEN_FRAGMENT.sub(r"\1<hidden>", str(value).strip())
    line = _PATH_FRAGMENT.sub("<local-path>", line)
    line = " ".join(line.split())
    if len(line) > _MAX_WARNING:
        line = line[: _MAX_WARNING - 1] + "…"
    return line


def _path_is_inside(value: Any, root: Path) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        path = Path(value).expanduser().resolve()
    except OSError:
        return False
    return path != root and root in path.parents


def _signal_process(
    process: asyncio.subprocess.Process,
    requested_signal: signal.Signals,
) -> None:
    if process.returncode is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, requested_signal)
        elif requested_signal == signal.SIGTERM:
            process.terminate()
        else:
            process.kill()
    except (ProcessLookupError, PermissionError):
        pass


async def _terminate_and_reap_process(
    process: asyncio.subprocess.Process,
    waiter: asyncio.Task[int],
) -> None:
    """Boundedly stop a child when the owning async task is itself cancelled."""

    if process.returncode is not None:
        return
    _signal_process(process, signal.SIGTERM)
    try:
        await asyncio.wait_for(
            asyncio.shield(waiter),
            timeout=_TERMINATE_GRACE_SECONDS,
        )
        return
    except (asyncio.TimeoutError, asyncio.CancelledError):
        pass
    if process.returncode is None:
        _signal_process(
            process,
            getattr(signal, "SIGKILL", signal.SIGTERM),
        )
    try:
        await asyncio.wait_for(asyncio.shield(waiter), timeout=1.0)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        # The bounded cleanup contract has been exhausted. The process-group
        # kill above is the last safe local action available to this task.
        pass


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _deduplicate(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        clean = str(value).strip()
        if clean and clean not in result:
            result.append(clean)
    return result


def _emit(callback: ProgressCallback, progress: FullConversionProgress) -> None:
    try:
        callback(progress)
    except Exception:
        # Progress rendering is an observer.  It may not interrupt, select or
        # otherwise alter the deterministic conversion job.
        pass


__all__ = [
    "CancellationPredicate",
    "FullConversionBusyError",
    "FullConversionError",
    "FullConversionPlan",
    "FullConversionProgress",
    "FullConversionRequest",
    "FullConversionResult",
    "FullConversionRunner",
    "FullConversionValidationError",
    "PlannedVocalConversion",
    "ProductionFullConversionRunner",
    "ProgressCallback",
    "create_full_conversion_runner",
    "plan_full_conversion",
]
