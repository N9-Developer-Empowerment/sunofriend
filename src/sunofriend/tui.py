"""Textual local studio for guided Sunofriend workflows."""

from __future__ import annotations

import asyncio
import inspect
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from rich.markup import escape as escape_markup
    from textual import events, on, work
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.widgets import (
        Button,
        Checkbox,
        DataTable,
        Footer,
        Header,
        Input,
        Label,
        ProgressBar,
        RichLog,
        Static,
        TabbedContent,
        TabPane,
    )
except ImportError as exc:  # pragma: no cover - installation guard
    raise RuntimeError(
        "The Sunofriend TUI requires Textual. Reinstall Sunofriend or run "
        "`python -m pip install \"textual>=8.2,<9\"`."
    ) from exc

from . import __version__
from .diagnostics import collect_diagnostics
from .tui_model import (
    TuiProjectConfig,
    TuiProjectSnapshot,
    build_tui_midi_map,
    candidate_roots_field,
    format_tui_midi_map,
    load_tui_project,
    parse_candidate_roots,
    safe_activity_line,
    workbench_command,
)


class SunofriendTui(App[None]):
    """A guided terminal control surface over the CLI and visual Workbench."""

    TITLE = "Sunofriend Local Studio"
    SUB_TITLE = "stems → compared MIDI → song-interpretation WAV → GarageBand"
    ENABLE_COMMAND_PALETTE = True

    CSS = """
    Screen {
        background: #081019;
        color: #edf5f4;
    }

    Header {
        background: #0d1a26;
        color: #d9fff7;
    }

    #hero {
        height: 5;
        padding: 0 2;
        background: #102333;
        border-bottom: solid #2dd4bf;
    }

    #brand {
        color: #5eead4;
        text-style: bold;
        padding-top: 1;
    }

    #tagline {
        color: #9fb3c8;
    }

    #project-controls {
        height: auto;
        padding: 1 2;
        background: #0b1722;
        border-bottom: solid #233a4d;
    }

    .field-label {
        width: 18;
        padding: 1 1 0 0;
        color: #9fb3c8;
    }

    .field-row {
        height: 3;
    }

    .field-input {
        width: 1fr;
        margin-bottom: 1;
    }

    #button-row {
        height: auto;
        margin-top: 0;
    }

    Button {
        margin-right: 1;
        min-width: 18;
    }

    #load-project {
        background: #0f766e;
    }

    #open-studio {
        background: #2563eb;
    }

    #system-check {
        background: #7c3aed;
    }

    #stop-studio {
        background: #7f1d1d;
    }

    TabbedContent {
        height: 1fr;
        margin: 1 2 0 2;
    }

    TabPane {
        padding: 1;
        background: #0b1722;
    }

    #overview-grid {
        height: 1fr;
    }

    #project-summary {
        height: 9;
        padding: 1 2;
        margin-bottom: 1;
        background: #102333;
        border: round #2b5068;
    }

    #stem-table {
        height: 1fr;
        min-height: 10;
        border: round #2b5068;
    }

    #midi-map {
        width: 46%;
        min-width: 46;
        height: 1fr;
        padding: 1 2;
        margin-left: 1;
        overflow: auto;
        background: #0b1722;
        border: round #2dd4bf;
    }

    #stem-panel {
        width: 54%;
        height: 1fr;
    }

    #workflow-guide, #privacy-guide {
        padding: 1 2;
        margin-bottom: 1;
        background: #102333;
        border: round #2b5068;
    }

    #conversion-scope {
        padding: 1 2;
        margin-bottom: 1;
        background: #102333;
        border: round #2dd4bf;
    }

    #conversion-output-row {
        height: 3;
        margin-bottom: 1;
    }

    #conversion-confirm {
        margin: 0 1 1 1;
    }

    #conversion-actions {
        height: 3;
        margin-bottom: 1;
    }

    #conversion-progress {
        margin: 0 1;
    }

    #conversion-status {
        min-height: 4;
        padding: 1 2;
        margin-top: 1;
        background: #0b1722;
        border: round #2b5068;
    }

    #activity-log {
        height: 1fr;
        padding: 0 1;
        background: #050b11;
        border: round #2b5068;
    }

    #system-status {
        padding: 1 2;
        min-height: 9;
        background: #102333;
        border: round #2b5068;
    }

    #status-line {
        height: 1;
        padding: 0 2;
        color: #9fb3c8;
        background: #0d1a26;
    }

    Screen.compact #hero {
        display: none;
    }

    Screen.compact #project-controls {
        height: 7;
        padding: 0 1;
    }

    Screen.compact .field-row {
        height: 2;
    }

    Screen.compact .field-label {
        display: none;
    }

    Screen.compact .field-input {
        margin-bottom: 0;
    }

    Screen.compact #button-row {
        height: 3;
    }

    Screen.compact Button {
        width: 1fr;
        min-width: 10;
        margin-right: 1;
        padding: 0 1;
    }

    Screen.compact TabbedContent {
        margin: 0 1;
    }

    Screen.compact TabPane {
        padding: 0;
    }

    Screen.compact #project-summary {
        height: 7;
        margin-bottom: 0;
        padding: 0 1;
    }

    Screen.compact #overview-grid {
        layout: vertical;
    }

    Screen.compact #stem-panel {
        width: 1fr;
    }

    Screen.compact #midi-map {
        display: none;
    }

    Footer {
        background: #0d1a26;
    }
    """

    BINDINGS = [
        ("ctrl+r", "refresh_project", "Refresh"),
        ("f6", "open_visual_studio", "Visual Studio"),
        ("ctrl+d", "run_system_check", "System check"),
        ("ctrl+q", "request_quit", "Quit"),
    ]

    def __init__(
        self,
        *,
        project: str | Path | None = None,
        candidate_roots: tuple[str | Path, ...] = (),
        catalog_path: str | Path | None = None,
        state_dir: str | Path | None = None,
        soundfont_path: str | Path | None = None,
        initial_conversion_output: str | Path | None = None,
        developer_inspector: bool = True,
        conversion_runner: Any | None = None,
    ) -> None:
        super().__init__()
        self.initial_project = str(project) if project is not None else ""
        self.initial_candidate_roots = tuple(candidate_roots)
        self.catalog_path = catalog_path
        self.state_dir = state_dir
        self.soundfont_path = soundfont_path
        self.initial_conversion_output = (
            str(initial_conversion_output)
            if initial_conversion_output is not None
            else ""
        )
        self.developer_inspector = bool(developer_inspector)
        self._conversion_runner = conversion_runner
        self._conversion_running = False
        self._conversion_sequence = 0
        self._conversion_cancel_requested = asyncio.Event()
        self._conversion_done = asyncio.Event()
        self._conversion_done.set()
        self._suggested_conversion_output = ""
        self._conversion_last_phase = ""
        self._preserve_conversion_status = False
        self.snapshot: TuiProjectSnapshot | None = None
        self._workbench_process: asyncio.subprocess.Process | None = None
        self._workbench_launching = False
        self._workbench_launch_done = asyncio.Event()
        self._workbench_launch_done.set()
        self._project_loading = False
        self._stem_ids: list[str] = []
        self._project_load_sequence = 0
        self._midi_map_sequence = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="hero"):
            yield Static(f"♪  SUNOFRIEND  {__version__}", id="brand")
            yield Static(
                "A private local studio for comparing many MIDI methods, "
                "building a balanced song-interpretation WAV, and preparing "
                "a GarageBand handoff.",
                id="tagline",
            )
        with Vertical(id="project-controls"):
            with Horizontal(classes="field-row"):
                yield Label("Stem project", classes="field-label")
                yield Input(
                    value=self.initial_project,
                    placeholder="/path/to/song-key-bpm-tuning",
                    id="project-path",
                    classes="field-input",
                )
            with Horizontal(classes="field-row"):
                yield Label("MIDI result roots", classes="field-label")
                yield Input(
                    value=candidate_roots_field(self.initial_candidate_roots),
                    placeholder="Separate several local result folders with ;",
                    id="candidate-roots",
                    classes="field-input",
                )
            with Horizontal(id="button-row"):
                yield Button("Load / refresh project", id="load-project")
                yield Button(
                    "Open visual studio",
                    id="open-studio",
                    disabled=True,
                )
                yield Button("Run system check", id="system-check")
                yield Button(
                    "Stop visual studio",
                    id="stop-studio",
                    disabled=True,
                )
        with TabbedContent(initial="overview"):
            with TabPane("Project", id="overview"):
                yield Static(
                    "Choose a stem project above. Loading is read-only and "
                    "does not create a decision database.",
                    id="project-summary",
                )
                with Horizontal(id="overview-grid"):
                    with Vertical(id="stem-panel"):
                        yield DataTable(
                            id="stem-table",
                            cursor_type="row",
                            zebra_stripes=True,
                        )
                    yield Static(
                        "Select a stem to see the primary MIDI alternatives as "
                        "a compact contour and activity map.",
                        id="midi-map",
                    )
            with TabPane("Workflow", id="workflow"):
                with VerticalScroll():
                    yield Static(_WORKFLOW_GUIDE, id="workflow-guide")
                    yield Static(_PRIVACY_GUIDE, id="privacy-guide")
            with TabPane("Convert", id="convert"):
                with VerticalScroll():
                    yield Static(_CONVERSION_SCOPE, id="conversion-scope")
                    with Horizontal(id="conversion-output-row"):
                        yield Label(
                            "Fresh output folder",
                            classes="field-label",
                        )
                        yield Input(
                            value=self.initial_conversion_output,
                            placeholder=(
                                "/path/outside/source/song-sunofriend-midi-v1"
                            ),
                            id="conversion-output",
                            classes="field-input",
                        )
                    yield Checkbox(
                        (
                            "I confirm this is a new, separate output folder. "
                            "Keep my source stems and existing results unchanged."
                        ),
                        id="conversion-confirm",
                    )
                    with Horizontal(id="conversion-actions"):
                        yield Button(
                            "Convert all stems",
                            id="convert-all",
                            disabled=True,
                        )
                        yield Button(
                            "Cancel conversion",
                            id="cancel-conversion",
                            disabled=True,
                        )
                    yield ProgressBar(
                        total=1,
                        show_eta=False,
                        id="conversion-progress",
                    )
                    yield Static(
                        (
                            "Load a source project, choose a fresh output "
                            "folder and confirm the scope. Conversion starts "
                            "only when you press Convert all stems."
                        ),
                        id="conversion-status",
                    )
            with TabPane("System", id="system"):
                yield Static(
                    "Run the system check to inspect transcription, preview "
                    "and CoreMIDI readiness. No model is downloaded.",
                    id="system-status",
                )
            with TabPane("Activity", id="activity"):
                yield RichLog(
                    id="activity-log",
                    highlight=True,
                    markup=True,
                    wrap=True,
                    max_lines=500,
                )
        yield Static("Ready · local only · no telemetry", id="status-line")
        yield Footer()

    def on_mount(self) -> None:
        self._apply_responsive_layout(self.size.width, self.size.height)
        table = self.query_one("#stem-table", DataTable)
        table.add_column("Stem", key="stem", width=26)
        table.add_column("Role", key="role", width=12)
        table.add_column("MIDI", key="midi", width=7)
        table.add_column("Decision", key="decision", width=10)
        table.add_column("Selected", key="selected", width=8)
        table.add_column("Next", key="next", width=14)
        self._activity(
            "ready",
            "The TUI started. Temporary navigation and logs are memory-only.",
        )
        self._sync_conversion_controls(update_status=False)
        if self.initial_project:
            self._start_project_load()

    def on_resize(self, event: events.Resize) -> None:
        self._apply_responsive_layout(event.size.width, event.size.height)

    @on(Button.Pressed, "#load-project")
    def _load_pressed(self) -> None:
        self._start_project_load()

    @on(Button.Pressed, "#open-studio")
    def _open_pressed(self) -> None:
        self.action_open_visual_studio()

    @on(Button.Pressed, "#system-check")
    def _doctor_pressed(self) -> None:
        self.action_run_system_check()

    @on(Button.Pressed, "#stop-studio")
    async def _stop_pressed(self) -> None:
        await self._stop_visual_studio()

    @on(Button.Pressed, "#convert-all")
    def _convert_all_pressed(self) -> None:
        self.action_convert_all()

    @on(Button.Pressed, "#cancel-conversion")
    def _cancel_conversion_pressed(self) -> None:
        self._cancel_full_conversion()

    @on(Input.Changed, "#conversion-output")
    def _conversion_output_changed(self) -> None:
        if not self._conversion_running:
            self._preserve_conversion_status = False
        self._sync_conversion_controls(update_status=True)

    @on(Checkbox.Changed, "#conversion-confirm")
    def _conversion_confirmation_changed(self) -> None:
        if not self._conversion_running:
            self._preserve_conversion_status = False
        self._sync_conversion_controls(update_status=True)

    @on(DataTable.RowHighlighted, "#stem-table")
    def _stem_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = event.row_key.value
        if isinstance(key, str) and self.snapshot is not None:
            self._start_midi_map_load(str(key))

    def action_refresh_project(self) -> None:
        self._start_project_load()

    def action_run_system_check(self) -> None:
        self._run_system_check()

    def action_open_visual_studio(self) -> None:
        if self._conversion_running:
            self.notify(
                "Wait for conversion to finish or cancel it first",
                severity="warning",
            )
            return
        if self._project_loading:
            self.notify(
                "Wait for the current project scan to finish",
                severity="warning",
            )
            return
        if self.snapshot is None:
            self.notify("Load a project first", severity="warning")
            return
        if self._workbench_launching or self._workbench_process is not None:
            self.notify("The visual studio is already running", severity="warning")
            return
        self._workbench_launching = True
        self._workbench_launch_done.clear()
        self._set_project_controls_locked(True)
        self.query_one("#open-studio", Button).disabled = True
        self._run_visual_studio()

    def action_convert_all(self) -> None:
        if self._conversion_running:
            self.notify("A full conversion is already running", severity="warning")
            return
        if self._workbench_launching or self._workbench_process is not None:
            self.notify(
                "Stop the visual studio before starting conversion",
                severity="warning",
            )
            return
        problem = self._conversion_start_problem()
        if problem is not None:
            self._set_conversion_status(problem, error=True)
            self.notify(problem, severity="warning")
            self._sync_conversion_controls(update_status=False)
            return
        assert self.snapshot is not None
        try:
            from .tui_conversion import (
                FullConversionRequest,
                create_full_conversion_runner,
            )

            request = FullConversionRequest.create(
                self.snapshot.config.project,
                self.query_one("#conversion-output", Input).value,
            )
            if self._conversion_runner is None:
                self._conversion_runner = create_full_conversion_runner()
        except Exception as exc:
            message = _safe_exception_message(exc)
            self._set_conversion_status(message, error=True)
            self._activity("error", message)
            return
        self._conversion_running = True
        self._preserve_conversion_status = False
        self._conversion_sequence += 1
        sequence = self._conversion_sequence
        self._conversion_cancel_requested.clear()
        self._conversion_done.clear()
        self.query_one("#conversion-progress", ProgressBar).update(
            total=None,
            progress=0,
        )
        self._set_conversion_status(
            "Starting full conversion and verifying the fresh output folder…"
        )
        self._set_status("Full conversion starting · local only")
        self._activity(
            "conversion",
            (
                "Full conversion requested for all supported instrumental, "
                "lead-vocal and backing-vocal roles."
            ),
        )
        self._set_project_controls_locked(True)
        self._sync_conversion_controls(update_status=False)
        self._run_full_conversion(request, sequence)

    async def action_request_quit(self) -> None:
        if not await self._stop_full_conversion():
            return
        if await self._stop_visual_studio():
            self.exit()

    async def on_unmount(self) -> None:
        await self._stop_full_conversion(notify_timeout=False)
        await self._stop_visual_studio()

    def _start_project_load(self) -> None:
        if self._conversion_running:
            self.notify(
                "Cancel or finish conversion before changing the project",
                severity="warning",
            )
            return
        if self._workbench_launching or self._workbench_process is not None:
            self.notify(
                "Stop the visual studio before changing or refreshing its project",
                severity="warning",
            )
            return
        raw_project = self.query_one("#project-path", Input).value.strip()
        if not raw_project:
            self.notify("Choose a stem project directory", severity="warning")
            return
        roots = parse_candidate_roots(
            self.query_one("#candidate-roots", Input).value
        )
        config = TuiProjectConfig.create(
            raw_project,
            candidate_roots=roots,
            catalog_path=self.catalog_path,
            state_dir=self.state_dir,
            soundfont_path=self.soundfont_path,
            developer_inspector=self.developer_inspector,
        )
        self.query_one("#load-project", Button).disabled = True
        self.query_one("#open-studio", Button).disabled = True
        self._project_loading = True
        self._sync_conversion_controls(update_status=False)
        self._set_status("Reading and verifying the local project…")
        self._activity("project", "Verifying stems and MIDI candidates.")
        self._project_load_sequence += 1
        self._load_project_worker(config, self._project_load_sequence)

    @work(exclusive=True, group="project-load")
    async def _load_project_worker(
        self, config: TuiProjectConfig, sequence: int
    ) -> None:
        try:
            snapshot = await asyncio.to_thread(load_tui_project, config)
        except Exception as exc:
            if sequence != self._project_load_sequence:
                return
            self._project_loading = False
            studio_active = (
                self._workbench_launching or self._workbench_process is not None
            )
            self._set_project_controls_locked(studio_active)
            self.query_one("#open-studio", Button).disabled = (
                studio_active or self.snapshot is None
            )
            self._set_status("Project unavailable")
            self._sync_conversion_controls(update_status=True)
            self._activity("error", _safe_exception_message(exc))
            self.notify(_safe_exception_message(exc), severity="error", timeout=8)
            return
        if sequence != self._project_load_sequence:
            return
        self._apply_snapshot(snapshot)

    def _apply_snapshot(self, snapshot: TuiProjectSnapshot) -> None:
        self._project_loading = False
        self.snapshot = snapshot
        document = snapshot.document
        project = document["project"]
        counts = document["counts"]
        output_input = self.query_one("#conversion-output", Input)
        current_output = output_input.value.strip()
        if (
            not current_output
            or current_output == self._suggested_conversion_output
        ):
            suggestion = _suggest_fresh_conversion_output(snapshot.config.project)
            self._suggested_conversion_output = suggestion
            output_input.value = suggestion
        midi_ready = counts["midi_ready_stem_count"]
        missing_midi = counts["missing_midi_stem_count"]
        coverage_message = (
            f"[bold #facc15]Partial MIDI results:[/] {missing_midi} source "
            f"stem{'s' if missing_midi != 1 else ''} "
            "have no MIDI candidate. Use the [bold]Convert[/] tab's "
            "[bold]Convert all stems[/] action. Project loading and the visual "
            "studio only review existing results."
            if missing_midi
            else (
                "[#9fb3c8]Project loading and the visual studio review existing "
                "MIDI results. New conversion starts only from the explicit "
                "Convert tab action.[/]"
            )
        )
        self.query_one("#project-summary", Static).update(
            (
                f"[bold #5eead4]{project['name']}[/]\n"
                f"[bold]Key[/] {project.get('key') or 'unknown'}    "
                f"[bold]BPM[/] {_number(project.get('bpm'))}    "
                f"[bold]Tuning[/] {_number(project.get('tuning_hz'), suffix=' Hz')}\n"
                f"[bold]Source stems[/] {counts['stem_count']}    "
                f"[bold]MIDI-ready[/] {midi_ready}    "
                f"[bold]Missing MIDI[/] {missing_midi}\n"
                f"[bold]Reviewed MIDI-ready[/] "
                f"{counts['decision_recorded_stem_count']}/"
                f"{counts['candidate_stem_count']}    "
                f"[bold]Selected MIDI[/] {counts['selected_part_count']}\n"
                "[bold]Song-interpretation WAV[/] build and hear it in the "
                "[bold]Visual Studio[/]\n"
                f"{coverage_message}\n"
                f"[#9fb3c8]Next: {_next_step_text(document['next_step'])}[/]"
            )
        )
        table = self.query_one("#stem-table", DataTable)
        table.clear()
        self._stem_ids = []
        for row in document["stems"]:
            self._stem_ids.append(str(row["stem_id"]))
            table.add_row(
                str(row["label"]),
                str(row["role"]),
                f"{row['primary_candidate_count']}/{row['candidate_count']}",
                "yes" if row["decision_recorded"] else "not yet",
                str(row["selected_part_count"]),
                _attention_text(str(row["attention_code"])),
                key=str(row["stem_id"]),
            )
        studio_active = (
            self._workbench_launching or self._workbench_process is not None
        )
        self._set_project_controls_locked(studio_active)
        self.query_one("#open-studio", Button).disabled = studio_active
        self._set_status(
            f"Loaded {counts['stem_count']} source stems · "
            f"{midi_ready} MIDI-ready · {missing_midi} missing MIDI · "
            f"{counts['selected_part_count']} selected MIDI · local only"
        )
        self._sync_conversion_controls(
            update_status=not self._preserve_conversion_status
        )
        self._activity(
            "project",
            (
                f"Loaded {counts['stem_count']} source stems; "
                f"{midi_ready} MIDI-ready, {missing_midi} missing MIDI; "
                f"{sum(row['candidate_count'] for row in document['stems'])} "
                "existing MIDI candidates. Project loading ran no conversion "
                "and recorded no decision or feedback."
            ),
        )
        if self._stem_ids:
            first_midi_row = next(
                (
                    index
                    for index, row in enumerate(document["stems"])
                    if row["candidate_count"] > 0
                ),
                0,
            )
            table.move_cursor(row=first_midi_row, column=0)
            self._start_midi_map_load(self._stem_ids[first_midi_row])
        else:
            self.query_one("#midi-map", Static).update(
                "This project has no discovered MIDI candidates yet. "
                "Use the Convert tab's Convert all stems action. Project "
                "loading and the visual studio only review existing results."
            )

    def _start_midi_map_load(self, stem_id: str) -> None:
        self._midi_map_sequence += 1
        self._load_midi_map(stem_id, self._midi_map_sequence)

    @work(exclusive=True, group="midi-map")
    async def _load_midi_map(self, stem_id: str, sequence: int) -> None:
        snapshot = self.snapshot
        if snapshot is None:
            return
        target = self.query_one("#midi-map", Static)
        target.update("Reading the unchanged primary MIDI alternatives…")
        try:
            document = await asyncio.to_thread(
                build_tui_midi_map,
                snapshot,
                stem_id,
                width=56,
            )
        except Exception as exc:
            if sequence == self._midi_map_sequence and self.snapshot is snapshot:
                target.update(f"MIDI map unavailable: {_safe_exception_message(exc)}")
            return
        if (
            sequence == self._midi_map_sequence
            and self.snapshot is snapshot
        ):
            target.update(format_tui_midi_map(document))

    @work(exclusive=True, group="full-conversion")
    async def _run_full_conversion(self, request: Any, sequence: int) -> None:
        runner = self._conversion_runner
        if runner is None:
            self._finish_conversion_failure(
                sequence,
                "The full-conversion runner is unavailable.",
            )
            return
        loop = asyncio.get_running_loop()

        def on_progress(progress: Any) -> None:
            loop.call_soon_threadsafe(
                self._apply_conversion_progress,
                progress,
                sequence,
            )

        try:
            result = await runner.run(
                request,
                on_progress=on_progress,
                cancellation_requested=self._conversion_cancel_requested.is_set,
            )
        except Exception as exc:
            self._finish_conversion_failure(
                sequence,
                _safe_exception_message(exc),
            )
            return
        if sequence != self._conversion_sequence:
            return
        self._conversion_running = False
        self._conversion_done.set()
        self._set_project_controls_locked(False)
        self._sync_conversion_controls(update_status=False)
        if bool(getattr(result, "cancelled", False)):
            self.query_one("#conversion-progress", ProgressBar).update(
                total=1,
                progress=0,
            )
            self._set_conversion_status(
                (
                    "Conversion cancelled. The backend preserved any partial "
                    "diagnostic output, but it was not loaded as a MIDI result."
                )
            )
            self._set_status("Full conversion cancelled · source unchanged")
            self._activity(
                "conversion",
                "Conversion cancelled; no candidate root was loaded.",
            )
            return
        if not bool(getattr(result, "succeeded", False)):
            status = str(getattr(result, "status", "failed"))
            self._finish_conversion_failure(
                sequence,
                f"Full conversion finished with status: {status}.",
                controls_already_reset=True,
            )
            return
        total = max(1, int(getattr(result, "source_stem_count", 1) or 1))
        ready = max(0, int(getattr(result, "midi_ready_stem_count", 0) or 0))
        self.query_one("#conversion-progress", ProgressBar).update(
            total=total,
            progress=total,
        )
        roots = tuple(getattr(result, "candidate_roots", ()) or ())
        if not roots:
            self._finish_conversion_failure(
                sequence,
                (
                    "Conversion completed without a verified candidate root; "
                    "the project was not reloaded."
                ),
                controls_already_reset=True,
            )
            return
        self.query_one("#candidate-roots", Input).value = candidate_roots_field(
            roots
        )
        skipped = tuple(getattr(result, "skipped_roles", ()) or ())
        failed = tuple(getattr(result, "failed_roles", ()) or ())
        proxy = tuple(getattr(result, "proxy_roles", ()) or ())
        warnings = tuple(getattr(result, "warnings", ()) or ())
        detail = (
            f"Verified {ready} of {total} source stems as MIDI-ready"
            f"{f'; skipped {len(skipped)}' if skipped else ''}"
            f"{f'; failed {len(failed)}' if failed else ''}"
            f"{f'; warnings {len(warnings)}' if warnings else ''}."
        )
        tone = "[bold #facc15]Partial conversion complete.[/]" if (
            str(getattr(result, "status", "")) == "partial"
        ) else "[bold #5eead4]Full conversion complete.[/]"
        disclosures: list[str] = []
        if skipped:
            disclosures.append(
                f"Skipped role(s): {escape_markup(', '.join(map(str, skipped)))}."
            )
        if failed:
            disclosures.append(
                f"Failed role(s): {escape_markup(', '.join(map(str, failed)))}."
            )
        if proxy:
            disclosures.append(
                "Review-required proxy role(s): "
                f"{escape_markup(', '.join(map(str, proxy)))}."
            )
        for warning in warnings[:5]:
            disclosures.append(
                "Review note: "
                f"{escape_markup(str(warning).strip()[:500] or 'unspecified warning')}"
            )
        if len(warnings) > 5:
            disclosures.append(
                f"Review notes: {len(warnings) - 5} more omitted from this "
                "bounded completion view."
            )
        disclosure_text = "\n".join(disclosures)
        status_detail = f"{tone} {detail} Reloading this fresh result root now."
        if disclosure_text:
            status_detail += f"\n{disclosure_text}"
        self._set_conversion_status(status_detail)
        self._preserve_conversion_status = True
        self._set_status("Conversion complete · reloading verified MIDI results")
        activity_detail = (
            f"Conversion {getattr(result, 'status', 'complete')}: "
            f"{ready}/{total} source stems MIDI-ready. Reloading the "
            "project against the fresh candidate root."
        )
        if disclosure_text:
            activity_detail += f" {disclosure_text}"
        self._activity("conversion", activity_detail)
        self.query_one(TabbedContent).active = "overview"
        self._start_project_load()

    def _apply_conversion_progress(self, progress: Any, sequence: int) -> None:
        if sequence != self._conversion_sequence or not self._conversion_running:
            return
        completed = max(0, int(getattr(progress, "completed", 0) or 0))
        total = max(1, int(getattr(progress, "total", 1) or 1))
        completed = min(completed, total)
        phase = str(getattr(progress, "phase", "conversion") or "conversion")
        message = str(getattr(progress, "message", "") or "").strip()
        role = str(getattr(progress, "current_role", "") or "").strip()
        self.query_one("#conversion-progress", ProgressBar).update(
            total=total,
            progress=completed,
        )
        detail = f"{completed}/{total} · {phase}"
        if role:
            detail += f" · {role}"
        if message:
            detail += f"\n{message}"
        self._set_conversion_status(detail)
        self._set_status(
            f"Full conversion · {completed}/{total} · {role or phase}"
        )
        if phase != self._conversion_last_phase:
            self._conversion_last_phase = phase
            self._activity("conversion", f"{phase}: {message or role or 'running'}")

    @work(exclusive=True, group="conversion-cancel")
    async def _cancel_full_conversion(self) -> None:
        await self._request_conversion_cancel(wait=False)

    async def _request_conversion_cancel(self, *, wait: bool) -> None:
        if not self._conversion_running:
            return
        self._conversion_cancel_requested.set()
        self.query_one("#cancel-conversion", Button).disabled = True
        self._set_conversion_status(
            "Cancellation requested. Finishing the current safe boundary…"
        )
        self._set_status("Cancelling full conversion…")
        self._activity("conversion", "Cancellation requested.")
        runner = self._conversion_runner
        if runner is not None:
            try:
                cancelled = runner.cancel()
                if inspect.isawaitable(cancelled):
                    await cancelled
            except Exception as exc:
                self._activity(
                    "error",
                    f"Conversion cancellation warning: {_safe_exception_message(exc)}",
                )
        if wait:
            try:
                await asyncio.wait_for(
                    self._conversion_done.wait(),
                    timeout=10.0,
                )
            except asyncio.TimeoutError:
                pass

    async def _stop_full_conversion(self, *, notify_timeout: bool = True) -> bool:
        if not self._conversion_running:
            return True
        await self._request_conversion_cancel(wait=True)
        if not self._conversion_running:
            return True
        self._activity(
            "error",
            "Conversion is still stopping; terminal shutdown was deferred.",
        )
        if notify_timeout:
            self.notify(
                "Conversion is still stopping; try Quit again shortly",
                severity="warning",
            )
        return False

    def _finish_conversion_failure(
        self,
        sequence: int,
        message: str,
        *,
        controls_already_reset: bool = False,
    ) -> None:
        if sequence != self._conversion_sequence:
            return
        self._conversion_running = False
        self._conversion_done.set()
        if not controls_already_reset:
            self._set_project_controls_locked(False)
            self._sync_conversion_controls(update_status=False)
        self._set_conversion_status(message, error=True)
        self._set_status("Full conversion failed · source unchanged")
        self._activity("error", message)

    def _set_conversion_status(self, message: str, *, error: bool = False) -> None:
        try:
            target = self.query_one("#conversion-status", Static)
        except Exception:
            return
        prefix = "[bold #fb7185]Cannot convert.[/] " if error else ""
        target.update(f"{prefix}{message}")

    def _conversion_start_problem(self) -> str | None:
        if self.snapshot is None:
            return "Load and verify a source-stem project first."
        if self._project_loading:
            return "Wait for the current project load to finish."
        if self.snapshot.config.catalog_path is not None:
            return (
                "This session uses an explicit Workbench catalog, which would "
                "ignore newly generated automatic candidates. Relaunch the TUI "
                "without --catalog before using Convert all stems."
            )
        raw_project = self.query_one("#project-path", Input).value.strip()
        if not raw_project:
            return "Choose and load a source-stem project first."
        if Path(raw_project).expanduser().resolve() != self.snapshot.config.project:
            return "The project path changed. Load it before starting conversion."
        output_value = self.query_one("#conversion-output", Input).value.strip()
        if not output_value:
            return "Choose a fresh, separate conversion output folder."
        output = Path(output_value).expanduser().resolve()
        project = self.snapshot.config.project
        if output == project or project in output.parents:
            return "The conversion output must be outside the source project."
        if output.exists():
            return (
                "The conversion output already exists. Choose a new folder; "
                "Sunofriend will not overwrite or resume it from this action."
            )
        if not self.query_one("#conversion-confirm", Checkbox).value:
            return "Confirm the fresh-output and unchanged-source scope first."
        return None

    def _sync_conversion_controls(self, *, update_status: bool) -> None:
        try:
            output = self.query_one("#conversion-output", Input)
            confirmation = self.query_one("#conversion-confirm", Checkbox)
            convert = self.query_one("#convert-all", Button)
            cancel = self.query_one("#cancel-conversion", Button)
        except Exception:
            return
        studio_active = (
            self._workbench_launching or self._workbench_process is not None
        )
        locked = self._conversion_running or studio_active
        output.disabled = locked
        confirmation.disabled = locked
        problem = self._conversion_start_problem()
        convert.disabled = (
            locked
            or self._project_loading
            or problem is not None
        )
        cancel.disabled = not self._conversion_running
        try:
            self.query_one("#open-studio", Button).disabled = (
                self.snapshot is None
                or self._project_loading
                or self._conversion_running
                or studio_active
            )
        except Exception:
            pass
        if update_status and not self._conversion_running:
            if problem is None:
                self._set_conversion_status(
                    (
                        "Ready. Conversion will create a fresh result tree and "
                        "will start only when you press Convert all stems."
                    )
                )
            else:
                self._set_conversion_status(problem, error=True)

    @work(exclusive=True, group="system-check")
    async def _run_system_check(self) -> None:
        target = self.query_one("#system-status", Static)
        target.update("Checking the local audio and MIDI toolchain…")
        self._set_status("Running local capability checks…")
        self._activity("system", "Started the local capability check.")
        try:
            report = await asyncio.to_thread(
                collect_diagnostics,
                check_playback=True,
            )
        except Exception as exc:
            message = _safe_exception_message(exc)
            target.update(f"[bold red]System check failed[/]\n{message}")
            self._set_status("System check failed")
            self._activity("error", message)
            return
        target.update(_format_diagnostics(report))
        ready_count = sum(
            bool(report.get(name))
            for name in ("transcribe_ready", "preview_ready", "playback_ready")
        )
        self._set_status(f"System check complete · {ready_count}/3 capabilities ready")
        self._activity(
            "system",
            f"System check complete: {ready_count}/3 primary capabilities ready.",
        )

    @work(exclusive=True, group="visual-studio")
    async def _run_visual_studio(self) -> None:
        snapshot = self.snapshot
        if snapshot is None:
            self._workbench_launching = False
            self._workbench_launch_done.set()
            self._set_project_controls_locked(False)
            return
        command = workbench_command(snapshot.config)
        self.query_one("#open-studio", Button).disabled = True
        self._set_status("Starting the loopback visual studio…")
        self._activity(
            "studio",
            (
                "Starting Workbench with the read-only Developer Inspector enabled."
                if snapshot.config.developer_inspector
                else "Starting Workbench without the optional Developer Inspector."
            ),
        )
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except Exception as exc:
            self._workbench_launching = False
            self._workbench_launch_done.set()
            self._set_project_controls_locked(False)
            self.query_one("#open-studio", Button).disabled = self.snapshot is None
            self.query_one("#stop-studio", Button).disabled = True
            self._set_status("Visual studio could not start")
            self._activity("error", _safe_exception_message(exc))
            return
        self._workbench_process = process
        self._workbench_launching = False
        self._workbench_launch_done.set()
        self.query_one("#stop-studio", Button).disabled = False
        assert process.stdout is not None
        while True:
            raw = await process.stdout.readline()
            if not raw:
                break
            line = safe_activity_line(raw.decode("utf-8", errors="replace"))
            if line:
                self._activity("studio", line)
                if line.startswith("Sunofriend Workbench"):
                    self._set_status(
                        (
                            "Visual studio running · browser opened · "
                            "Inspector available"
                            if snapshot.config.developer_inspector
                            else "Visual studio running · browser opened"
                        )
                    )
        return_code = await process.wait()
        if self._workbench_process is process:
            self._workbench_process = None
            self._set_project_controls_locked(False)
            self.query_one("#open-studio", Button).disabled = self.snapshot is None
            self.query_one("#stop-studio", Button).disabled = True
            self._set_status(f"Visual studio stopped · exit {return_code}")
            self._activity("studio", f"Workbench stopped with exit {return_code}.")

    async def _stop_visual_studio(self) -> bool:
        if self._workbench_launching:
            try:
                await asyncio.wait_for(
                    self._workbench_launch_done.wait(),
                    timeout=2.0,
                )
            except asyncio.TimeoutError:
                self._activity(
                    "error",
                    "The visual studio launch is still pending; quit was deferred.",
                )
                self.notify(
                    "Visual studio is still starting; try Stop or Quit again",
                    severity="warning",
                )
                return False
        process = self._workbench_process
        if process is None:
            return True
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            self._activity("studio", "Stop requested for the local Workbench.")
            try:
                await asyncio.wait_for(asyncio.shield(process.wait()), timeout=2.0)
            except asyncio.TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
                self._activity(
                    "studio",
                    "Workbench did not stop within two seconds and was killed.",
                )
        if self._workbench_process is process:
            self._workbench_process = None
        try:
            self._set_project_controls_locked(False)
            self.query_one("#open-studio", Button).disabled = self.snapshot is None
            self.query_one("#stop-studio", Button).disabled = True
        except Exception:
            # The widgets may already be unmounted during terminal shutdown.
            pass
        return True

    def _activity(self, kind: str, message: str) -> None:
        try:
            log = self.query_one("#activity-log", RichLog)
        except Exception:
            return
        stamp = datetime.now().strftime("%H:%M:%S")
        colours = {
            "ready": "#5eead4",
            "project": "#60a5fa",
            "conversion": "#34d399",
            "system": "#c084fc",
            "studio": "#fbbf24",
            "error": "#fb7185",
        }
        colour = colours.get(kind, "#9fb3c8")
        log.write(f"[{colour}]{stamp} {kind.upper():7}[/] {message}")

    def _set_status(self, message: str) -> None:
        self.query_one("#status-line", Static).update(message)

    def _set_project_controls_locked(self, locked: bool) -> None:
        self.query_one("#project-path", Input).disabled = locked
        self.query_one("#candidate-roots", Input).disabled = locked
        self.query_one("#load-project", Button).disabled = locked
        try:
            self.query_one("#conversion-output", Input).disabled = locked
            self.query_one("#conversion-confirm", Checkbox).disabled = locked
        except Exception:
            pass
        self._sync_conversion_controls(update_status=False)

    def _apply_responsive_layout(self, width: int, height: int) -> None:
        compact = int(width) < 110 or int(height) < 44
        if compact:
            self.screen.add_class("compact")
        else:
            self.screen.remove_class("compact")
        labels = (
            ("Load", "Visual studio", "Check", "Stop")
            if compact
            else (
                "Load / refresh project",
                "Open visual studio",
                "Run system check",
                "Stop visual studio",
            )
        )
        for selector, label in zip(
            ("#load-project", "#open-studio", "#system-check", "#stop-studio"),
            labels,
        ):
            try:
                self.query_one(selector, Button).label = label
            except Exception:
                # Resize may arrive before the composed widgets are mounted.
                pass


def run_tui(
    *,
    project: str | Path | None = None,
    candidate_roots: tuple[str | Path, ...] = (),
    catalog_path: str | Path | None = None,
    state_dir: str | Path | None = None,
    soundfont_path: str | Path | None = None,
    initial_conversion_output: str | Path | None = None,
    developer_inspector: bool = True,
) -> int:
    """Run the local studio and return a CLI-compatible exit status."""

    app = SunofriendTui(
        project=project,
        candidate_roots=candidate_roots,
        catalog_path=catalog_path,
        state_dir=state_dir,
        soundfont_path=soundfont_path,
        initial_conversion_output=initial_conversion_output,
        developer_inspector=developer_inspector,
    )
    app.run()
    return 0


def _safe_exception_message(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:500]


def _suggest_fresh_conversion_output(project: Path) -> str:
    """Suggest but never create a fresh sibling output directory."""

    base = project.parent / f"{project.name}-sunofriend-midi-v1"
    if not base.exists():
        return str(base)
    stem = base.name.rsplit("-v1", 1)[0]
    for index in range(2, 1000):
        candidate = base.with_name(f"{stem}-v{index}")
        if not candidate.exists():
            return str(candidate)
    return str(base.with_name(f"{base.name}-fresh"))


def _number(value: Any, *, suffix: str = "") -> str:
    if value is None:
        return "unknown"
    number = float(value)
    rendered = str(int(number)) if number.is_integer() else f"{number:.3f}".rstrip("0")
    return f"{rendered}{suffix}"


def _attention_text(code: str) -> str:
    return {
        "no-candidates": "convert",
        "compare-candidates": "compare",
        "no-usable-selection": "no usable MIDI",
        "listening-inconclusive": "listen again",
        "no-active-selection": "choose",
        "hear-in-arrangement": "hear in mix",
        "ready-for-pack": "render WAV / pack",
    }.get(code, code.replace("-", " "))


def _next_step_text(step: dict[str, Any]) -> str:
    return {
        "compare-stem": "compare the next stem in the visual studio",
        "hear-arrangement": "hear the selected parts together",
        "compose-pack": (
            "build or reuse the song-interpretation WAV, then choose the "
            "GarageBand ZIP contents"
        ),
        "no-results": "convert stems or select useful MIDI",
    }.get(str(step.get("action")), "review the project")


def _format_diagnostics(report: dict[str, Any]) -> str:
    def state(name: str) -> str:
        return "[bold #5eead4]READY[/]" if report.get(name) else "[bold #fb7185]NEEDS SETUP[/]"

    outputs = report.get("midi_outputs") or []
    return (
        "[bold]Local capability dashboard[/]\n\n"
        f"Stem and vocal transcription    {state('transcribe_ready')}\n"
        f"Offline MIDI preview            {state('preview_ready')}\n"
        f"Live CoreMIDI instruments        {state('playback_ready')}\n\n"
        f"Python {report.get('python')} · Sunofriend {report.get('sunofriend_version')}\n"
        f"FluidSynth: {'available' if report.get('fluidsynth') else 'not found'}\n"
        f"SoundFont: {'available' if report.get('soundfont') else 'not found'}\n"
        f"CoreMIDI destinations: {len(outputs)}\n\n"
        "[#9fb3c8]This check downloads nothing and changes no project state.[/]"
    )


_WORKFLOW_GUIDE = """\
[bold #5eead4]One guided path, all the underlying power[/]

[bold]1 · Load[/] verifies stems, key, BPM, tuning, MIDI alternatives and saved
decisions. It records nothing.

[bold]2 · Convert[/] is ready now. It runs the full supported instrumental
conversion plus separate lead- and backing-vocal melody phases into one
required fresh output folder. It never overwrites the source or an old result.

[bold]3 · Compare and render[/] is ready now. [bold]Open visual studio[/]
launches the existing waveform and piano-roll Result Explorer, source/MIDI
playback, selected-arrangement mixer, the balanced MIDI-derived
song-interpretation WAV and explicit review controls.

The WAV is rendered from selected MIDI. Source stems provide timing, horizon
and level evidence but are not mixed into it. It is a creative interpolation
of melody, harmony, rhythm and structure, not waveform reconstruction.

[bold]4 · Understand[/] uses the optional Developer Inspector in that same local
site. It exposes application operations and before/after state, not Python-line
debugging, and cannot change choices or MIDI.

[bold]5 · Export[/] leaves the song-interpretation WAV available as its own
download and uses the existing GarageBand Pack Composer for exact selected
MIDI. Its basket is separate from playback, mixer state and review decisions;
only explicit choices enter the ZIP.

[bold]6 · Create[/] retains immutable Clip alternatives and review-before-write
contracts. The TUI will add guided forms without weakening those gates.
"""

_CONVERSION_SCOPE = """\
[bold #5eead4]Full-song conversion into a fresh result tree[/]

[bold]What runs[/]
• The full supported instrumental conversion runs in repair mode and retains
  comparison variants for each discovered role.
• Lead and backing vocals use their separate vocal-melody workflows.
• Near-silent stems, unsupported roles and failures are reported explicitly;
  they are never silently called successful MIDI.

[bold]Safety and confirmation[/]
The output must be a new folder outside the source project. Existing candidate
roots and source stems remain unchanged. Conversion starts only from the button
below, can be cancelled at a safe boundary, and a successful or partial verified
result is automatically reloaded for comparison. An explicit Workbench catalog
must be removed at relaunch because it would ignore newly discovered results.
"""

_PRIVACY_GUIDE = """\
[bold #60a5fa]Private by construction[/]

Everything runs locally. No audio, MIDI, review, activity log or feedback is
uploaded. Activity shown here is bounded and memory-only. Playback, highlighting
a row and opening a view are not musical preferences. Any future contribution
or aggregate learning remains a separate explicit-consent Phase 7 feature.
"""


__all__ = ["SunofriendTui", "run_tui"]
