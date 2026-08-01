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
from .project_audio_inputs import prepared_project_input_problem
from .tui_listening_master_contract import LISTENING_MASTER_PROGRESS_TOTAL
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

_LISTENING_MASTER_QUIT_WAIT_SECONDS = 10.0
_STUDIO_TAB_IDS = frozenset(
    {
        "overview",
        "workflow",
        "convert",
        "master",
        "system",
        "activity",
    }
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

    #mode-switch-row {
        height: 3;
        margin-bottom: 1;
    }

    .mode-choice {
        min-width: 28;
        background: #1e293b;
        color: #cbd5e1;
    }

    .mode-choice.active-mode {
        background: #0f766e;
        color: #ffffff;
        text-style: bold;
    }

    #mode-description {
        width: 1fr;
        padding: 1 0 0 1;
        color: #9fb3c8;
    }

    .field-label {
        width: 18;
        padding: 1 1 0 0;
        color: #9fb3c8;
    }

    #project-path-label {
        width: 46;
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

    #simple-scope {
        padding: 1 2;
        margin-bottom: 1;
        background: #102333;
        border: round #5eead4;
    }

    #simple-output-row {
        height: 3;
        margin-bottom: 1;
    }

    #simple-actions {
        height: 3;
        margin-bottom: 1;
    }

    #create-simple {
        background: #0f766e;
    }

    #cancel-simple {
        background: #7f1d1d;
    }

    #simple-progress {
        margin: 0 1;
    }

    #simple-status {
        min-height: 6;
        padding: 1 2;
        margin-top: 1;
        background: #0b1722;
        border: round #2b5068;
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

    #master-scope {
        padding: 1 2;
        margin-bottom: 1;
        background: #102333;
        border: round #2dd4bf;
    }

    #master-confirm {
        margin: 0 1 1 1;
    }

    #master-actions {
        height: 3;
        margin-bottom: 1;
    }

    #master-progress {
        margin: 0 1;
    }

    #master-status {
        min-height: 8;
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

    Screen.compact #mode-description {
        display: none;
    }

    Footer {
        background: #0d1a26;
    }
    """

    BINDINGS = [
        ("f2", "switch_simple_mode", "Simple mode"),
        ("f3", "switch_studio_mode", "Studio mode"),
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
        initial_mode: str = "simple",
        developer_inspector: bool = True,
        conversion_runner: Any | None = None,
        simple_runner: Any | None = None,
        listening_master_runner: Any | None = None,
    ) -> None:
        super().__init__()
        if initial_mode not in {"simple", "studio"}:
            raise ValueError("TUI mode must be simple or studio")
        self.initial_mode = initial_mode
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
        self._simple_runner = simple_runner
        self._simple_running = False
        self._simple_sequence = 0
        self._simple_cancel_requested = asyncio.Event()
        self._simple_done = asyncio.Event()
        self._simple_done.set()
        self._suggested_simple_output = (
            _suggest_fresh_simple_output(Path(self.initial_project))
            if self.initial_project
            else ""
        )
        self._simple_last_phase = ""
        self._preserve_simple_status = False
        self._simple_start_after_load = False
        self._listening_master_runner = listening_master_runner
        self._listening_master_running = False
        self._listening_master_sequence = 0
        self._listening_master_done = asyncio.Event()
        self._listening_master_done.set()
        self._listening_master_last_phase = ""
        self._listening_master_progress_total = LISTENING_MASTER_PROGRESS_TOTAL
        self._preserve_listening_master_status = False
        self.snapshot: TuiProjectSnapshot | None = None
        self._workbench_process: asyncio.subprocess.Process | None = None
        self._workbench_launching = False
        self._workbench_launch_done = asyncio.Event()
        self._workbench_launch_done.set()
        self._project_loading = False
        self._stem_ids: list[str] = []
        self._project_load_sequence = 0
        self._midi_map_sequence = 0
        self._last_studio_tab = "overview"

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
                yield Label(
                    "Stem folder (top-level lower-case .wav files)",
                    id="project-path-label",
                    classes="field-label",
                )
                yield Input(
                    value=self.initial_project,
                    placeholder="/path/to/fresh-prepared-stems",
                    id="project-path",
                    classes="field-input",
                )
            with Horizontal(classes="field-row"):
                yield Label("Existing MIDI (Studio)", classes="field-label")
                yield Input(
                    value=candidate_roots_field(self.initial_candidate_roots),
                    placeholder="Optional; separate result folders with ;",
                    id="candidate-roots",
                    classes="field-input",
                )
            with Horizontal(id="mode-switch-row"):
                yield Label("Experience", classes="field-label")
                yield Button(
                    "Simple · Make my song",
                    id="switch-simple",
                    classes=(
                        "mode-choice active-mode"
                        if self.initial_mode == "simple"
                        else "mode-choice"
                    ),
                )
                yield Button(
                    "Studio · Compare & improve",
                    id="switch-studio",
                    classes=(
                        "mode-choice active-mode"
                        if self.initial_mode == "studio"
                        else "mode-choice"
                    ),
                )
                yield Static(
                    _mode_description(self.initial_mode),
                    id="mode-description",
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
        with TabbedContent(
            initial="simple" if self.initial_mode == "simple" else "overview",
            id="workspace-tabs",
        ):
            with TabPane("Make my song", id="simple"):
                with VerticalScroll():
                    yield Static(_SIMPLE_SCOPE, id="simple-scope")
                    with Horizontal(id="simple-output-row"):
                        yield Label(
                            "Fresh output folder",
                            classes="field-label",
                        )
                        yield Input(
                            value=self._suggested_simple_output,
                            placeholder=(
                                "/path/outside/source/song-sunofriend-song-v1"
                            ),
                            id="simple-output",
                            classes="field-input",
                        )
                    with Horizontal(id="simple-actions"):
                        yield Button(
                            "Create MIDI + WAV",
                            id="create-simple",
                            disabled=True,
                        )
                        yield Button(
                            "Cancel",
                            id="cancel-simple",
                            disabled=True,
                        )
                    yield ProgressBar(
                        total=6,
                        show_eta=False,
                        id="simple-progress",
                    )
                    yield Static(
                        (
                            "Choose a folder of stems above. Sunofriend will "
                            "use safe automatic primaries, make editable MIDI, "
                            "a balanced interpretation WAV and one starter ZIP."
                        ),
                        id="simple-status",
                    )
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
            with TabPane("Master", id="master"):
                with VerticalScroll():
                    yield Static(_LISTENING_MASTER_SCOPE, id="master-scope")
                    yield Checkbox(
                        (
                            "I understand this creates a separate comparative "
                            "challenger. The balanced control stays unchanged, "
                            "and this is not a release master or a preference."
                        ),
                        id="master-confirm",
                    )
                    with Horizontal(id="master-actions"):
                        yield Button(
                            "Create / reuse listening master",
                            id="create-listening-master",
                            disabled=True,
                        )
                    yield ProgressBar(
                        total=LISTENING_MASTER_PROGRESS_TOTAL,
                        show_eta=False,
                        id="master-progress",
                    )
                    yield Static(
                        (
                            "Load a project whose current selected MIDI already "
                            "has a verified balanced song-interpretation WAV. "
                            "Create that control in the Visual Studio first."
                        ),
                        id="master-status",
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
        self._sync_simple_controls(update_status=False)
        self._sync_conversion_controls(update_status=False)
        self._sync_listening_master_controls(update_status=False)
        self._sync_mode_switch(self.initial_mode)
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

    @on(Button.Pressed, "#switch-simple")
    def _switch_simple_pressed(self) -> None:
        self.action_switch_simple_mode()

    @on(Button.Pressed, "#switch-studio")
    def _switch_studio_pressed(self) -> None:
        self.action_switch_studio_mode()

    @on(TabbedContent.TabActivated, "#workspace-tabs")
    def _workspace_tab_activated(
        self,
        event: TabbedContent.TabActivated,
    ) -> None:
        active_tab = event.pane.id or ""
        if active_tab in _STUDIO_TAB_IDS:
            self._last_studio_tab = active_tab
            self._sync_mode_switch("studio")
        elif active_tab == "simple":
            self._sync_mode_switch("simple")

    @on(Button.Pressed, "#convert-all")
    def _convert_all_pressed(self) -> None:
        self.action_convert_all()

    @on(Button.Pressed, "#create-simple")
    def _create_simple_pressed(self) -> None:
        self.action_create_simple()

    @on(Button.Pressed, "#cancel-simple")
    def _cancel_simple_pressed(self) -> None:
        self._cancel_simple_create()

    @on(Input.Changed, "#project-path")
    def _project_path_changed(self) -> None:
        if self._simple_running:
            return
        raw_project = self.query_one("#project-path", Input).value.strip()
        simple_output = self.query_one("#simple-output", Input)
        if (
            raw_project
            and (
                not simple_output.value.strip()
                or simple_output.value.strip() == self._suggested_simple_output
            )
        ):
            self._suggested_simple_output = _suggest_fresh_simple_output(
                Path(raw_project).expanduser()
            )
            simple_output.value = self._suggested_simple_output
        self._preserve_simple_status = False
        self._sync_simple_controls(update_status=True)

    @on(Input.Changed, "#simple-output")
    def _simple_output_changed(self) -> None:
        if not self._simple_running:
            self._preserve_simple_status = False
        self._sync_simple_controls(update_status=True)

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

    @on(Button.Pressed, "#create-listening-master")
    def _create_listening_master_pressed(self) -> None:
        self.action_create_listening_master()

    @on(Checkbox.Changed, "#master-confirm")
    def _listening_master_confirmation_changed(self) -> None:
        if not self._listening_master_running:
            self._preserve_listening_master_status = False
        self._sync_listening_master_controls(update_status=True)

    @on(DataTable.RowHighlighted, "#stem-table")
    def _stem_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = event.row_key.value
        if isinstance(key, str) and self.snapshot is not None:
            self._start_midi_map_load(str(key))

    def action_refresh_project(self) -> None:
        self._start_project_load()

    def action_switch_simple_mode(self) -> None:
        """Show the one-action journey without changing project state."""

        self._switch_mode("simple")

    def action_switch_studio_mode(self) -> None:
        """Show the detailed workspace without changing project state."""

        self._switch_mode("studio")

    def _switch_mode(self, mode: str) -> None:
        tabs = self.query_one("#workspace-tabs", TabbedContent)
        active_tab = tabs.active or ""
        if mode == "simple":
            if active_tab in _STUDIO_TAB_IDS:
                self._last_studio_tab = active_tab
            if active_tab != "simple":
                tabs.active = "simple"
            self._sync_mode_switch("simple")
            return
        if mode != "studio":  # pragma: no cover - private contract guard
            raise ValueError("TUI mode must be simple or studio")
        if active_tab == "simple":
            target = (
                self._last_studio_tab
                if self._last_studio_tab in _STUDIO_TAB_IDS
                else "overview"
            )
            tabs.active = target
        self._sync_mode_switch("studio")

    def _sync_mode_switch(self, mode: str) -> None:
        simple = self.query_one("#switch-simple", Button)
        studio = self.query_one("#switch-studio", Button)
        simple.set_class(mode == "simple", "active-mode")
        studio.set_class(mode == "studio", "active-mode")
        self.query_one("#mode-description", Static).update(
            _mode_description(mode)
        )

    def action_run_system_check(self) -> None:
        if (
            self._simple_running
            or self._conversion_running
            or self._listening_master_running
        ):
            self.notify(
                "Wait for the current audio operation to finish",
                severity="warning",
            )
            return
        self._run_system_check()

    def action_open_visual_studio(self) -> None:
        if (
            self._simple_running
            or self._conversion_running
            or self._listening_master_running
        ):
            self.notify(
                "Wait for the current render operation to finish",
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

    def action_create_simple(self) -> None:
        if self._simple_running:
            self.notify("A Simple song is already being created", severity="warning")
            return
        if self._conversion_running or self._listening_master_running:
            self.notify(
                "Wait for the current audio operation to finish",
                severity="warning",
            )
            return
        if self._workbench_launching or self._workbench_process is not None:
            self.notify(
                "Stop the visual studio before creating a Simple song",
                severity="warning",
            )
            return
        problem = self._simple_start_problem(require_loaded=False)
        if problem is not None:
            self._set_simple_status(problem, error=True)
            self.notify(problem, severity="warning")
            self._sync_simple_controls(update_status=False)
            return
        raw_project = Path(
            self.query_one("#project-path", Input).value.strip()
        ).expanduser().resolve()
        if self.snapshot is None or self.snapshot.config.project != raw_project:
            self._simple_start_after_load = True
            self._set_simple_status(
                "Checking the source stems, BPM, key and tuning before starting…"
            )
            self._start_project_load()
            return
        try:
            from .simple_create import create_simple_create_runner
            from .simple_create_contract import SimpleCreateRequest

            request = SimpleCreateRequest.create(
                self.snapshot.config.project,
                self.query_one("#simple-output", Input).value,
                state_dir=self.state_dir,
                soundfont_path=self.soundfont_path,
            )
            if self._simple_runner is None:
                self._simple_runner = create_simple_create_runner()
        except Exception as exc:
            message = _safe_exception_message(exc)
            self._set_simple_status(message, error=True)
            self._activity("error", message)
            return
        self._simple_running = True
        self._simple_start_after_load = False
        self._preserve_simple_status = False
        self._simple_sequence += 1
        sequence = self._simple_sequence
        self._simple_cancel_requested.clear()
        self._simple_done.clear()
        self._simple_last_phase = ""
        self.query_one("#simple-progress", ProgressBar).update(
            total=6,
            progress=0,
        )
        self._set_simple_status(
            "Starting local conversion. This can take some time on a full song…"
        )
        self._set_status("Making automatic MIDI + WAV · local only")
        self._activity(
            "simple",
            (
                "Simple creation started with production repair conversion and "
                "automatic, unreviewed primary selection."
            ),
        )
        self._set_project_controls_locked(True)
        self._sync_simple_controls(update_status=False)
        self._run_simple_create(request, sequence)

    def action_convert_all(self) -> None:
        if self._conversion_running:
            self.notify("A full conversion is already running", severity="warning")
            return
        if self._simple_running:
            self.notify(
                "Wait for Simple creation to finish or cancel it first",
                severity="warning",
            )
            return
        if self._listening_master_running:
            self.notify(
                "Wait for the listening master to finish",
                severity="warning",
            )
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

    def action_create_listening_master(self) -> None:
        if self._listening_master_running:
            self.notify(
                "A listening master is already being verified",
                severity="warning",
            )
            return
        if self._simple_running:
            self.notify(
                "Wait for Simple creation to finish or cancel it first",
                severity="warning",
            )
            return
        if self._conversion_running:
            self.notify(
                "Wait for conversion to finish or cancel it first",
                severity="warning",
            )
            return
        if self._workbench_launching or self._workbench_process is not None:
            self.notify(
                "Stop the visual studio before creating a listening master",
                severity="warning",
            )
            return
        problem = self._listening_master_start_problem()
        if problem is not None:
            self._set_listening_master_status(problem, error=True)
            self.notify(problem, severity="warning")
            self._sync_listening_master_controls(update_status=False)
            return
        assert self.snapshot is not None
        try:
            from .tui_listening_master import (
                ListeningMasterRequest,
                create_listening_master_runner,
            )

            request = ListeningMasterRequest.create(self.snapshot)
            if self._listening_master_runner is None:
                self._listening_master_runner = create_listening_master_runner()
        except Exception as exc:
            message = _safe_exception_message(exc)
            self._set_listening_master_status(message, error=True)
            self._activity("error", message)
            return
        self._listening_master_running = True
        self._preserve_listening_master_status = False
        self._listening_master_sequence += 1
        sequence = self._listening_master_sequence
        self._listening_master_done.clear()
        self._listening_master_last_phase = ""
        self.query_one("#master-progress", ProgressBar).update(
            total=LISTENING_MASTER_PROGRESS_TOTAL,
            progress=0,
        )
        self._set_listening_master_status(
            "Verifying the exact current balanced control…"
        )
        self._set_status("Listening master starting · local only")
        self._activity(
            "master",
            (
                "Comparative listening master requested. This records no "
                "review, preference, MIDI choice or Pack change."
            ),
        )
        self._set_project_controls_locked(True)
        self._sync_listening_master_controls(update_status=False)
        self._run_listening_master(request, sequence)

    async def action_request_quit(self) -> None:
        if not await self._stop_simple_create():
            return
        if not await self._stop_full_conversion():
            return
        if not await self._wait_for_listening_master():
            return
        if await self._stop_visual_studio():
            self.exit()

    async def on_unmount(self) -> None:
        # Invalidate a project read before widgets are removed.  A slow
        # background load must not try to update an already unmounted screen.
        self._project_load_sequence += 1
        self._project_loading = False
        await self._stop_simple_create(notify_timeout=False)
        await self._stop_full_conversion(notify_timeout=False)
        await self._wait_for_listening_master(notify_timeout=False)
        await self._stop_visual_studio()

    def _start_project_load(self) -> None:
        if self._simple_running:
            self.notify(
                "Cancel or finish Simple creation before changing the project",
                severity="warning",
            )
            return
        if self._conversion_running:
            self.notify(
                "Cancel or finish conversion before changing the project",
                severity="warning",
            )
            return
        if self._listening_master_running:
            self.notify(
                "Wait for the listening master to finish before changing the project",
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
        self._sync_simple_controls(update_status=False)
        self._sync_conversion_controls(update_status=False)
        self._sync_listening_master_controls(update_status=False)
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
            self._simple_start_after_load = False
            studio_active = (
                self._workbench_launching or self._workbench_process is not None
            )
            self._set_project_controls_locked(studio_active)
            self.query_one("#open-studio", Button).disabled = (
                studio_active or self.snapshot is None
            )
            self._set_status("Project unavailable")
            self._sync_simple_controls(update_status=True)
            self._sync_conversion_controls(update_status=True)
            self._sync_listening_master_controls(update_status=True)
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
        simple_output = self.query_one("#simple-output", Input)
        current_simple_output = simple_output.value.strip()
        if (
            not current_simple_output
            or current_simple_output == self._suggested_simple_output
        ):
            simple_suggestion = _suggest_fresh_simple_output(snapshot.config.project)
            self._suggested_simple_output = simple_suggestion
            simple_output.value = simple_suggestion
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
        self._sync_simple_controls(
            update_status=not self._preserve_simple_status
        )
        self._sync_listening_master_controls(
            update_status=not self._preserve_listening_master_status
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
        if self._simple_start_after_load:
            self.call_after_refresh(self.action_create_simple)

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

    @work(exclusive=True, group="simple-create")
    async def _run_simple_create(self, request: Any, sequence: int) -> None:
        runner = self._simple_runner
        if runner is None:
            self._finish_simple_failure(
                sequence,
                "The Simple creation runner is unavailable.",
            )
            return
        loop = asyncio.get_running_loop()

        def on_progress(progress: Any) -> None:
            loop.call_soon_threadsafe(
                self._apply_simple_progress,
                progress,
                sequence,
            )

        try:
            result = await runner.run(
                request,
                on_progress=on_progress,
                cancellation_requested=self._simple_cancel_requested.is_set,
            )
        except Exception as exc:
            self._finish_simple_failure(
                sequence,
                _safe_exception_message(exc),
            )
            return
        if sequence != self._simple_sequence:
            return
        self._simple_running = False
        self._simple_done.set()
        self._set_project_controls_locked(False)
        self._sync_simple_controls(update_status=False)
        if bool(getattr(result, "cancelled", False)):
            self.query_one("#simple-progress", ProgressBar).update(
                total=6,
                progress=0,
            )
            self._set_simple_status(
                (
                    "Cancelled. Any incomplete conversion tree is preserved for "
                    "inspection, but it is not labelled as a finished Simple result."
                )
            )
            self._set_status("Simple creation cancelled · source unchanged")
            self._activity(
                "simple",
                "Simple creation cancelled; no automatic result was published.",
            )
            return
        if not bool(getattr(result, "succeeded", False)):
            self._finish_simple_failure(
                sequence,
                f"Simple creation finished with status: {getattr(result, 'status', 'failed')}.",
                controls_already_reset=True,
            )
            return
        self.query_one("#simple-progress", ProgressBar).update(
            total=6,
            progress=6,
        )
        selected_count = int(getattr(result, "selected_count", 0) or 0)
        omitted_count = int(getattr(result, "omitted_count", 0) or 0)
        warnings = tuple(getattr(result, "warnings", ()) or ())
        warning_lines = "\n".join(
            f"• {escape_markup(str(value)[:400])}" for value in warnings[:5]
        )
        if len(warnings) > 5:
            warning_lines += f"\n• {len(warnings) - 5} more note(s) in the receipt"
        status = (
            "[bold #5eead4]Your automatic song is ready.[/]\n"
            f"[bold]MIDI parts[/] {selected_count} automatic primaries\n"
            f"[bold]Roles without a safe default[/] {omitted_count}\n"
            f"[bold]Balanced WAV[/] "
            f"{escape_markup(str(getattr(result, 'balanced_wav_path', '')))}\n"
            f"[bold]GarageBand starter ZIP[/] "
            f"{escape_markup(str(getattr(result, 'zip_path', '')))}\n\n"
            "[#9fb3c8]These are automatic, unreviewed starting choices. "
            "Use Visual Studio when you want to compare alternatives and "
            "record feedback.[/]"
        )
        if warning_lines:
            status += f"\n\n[bold #facc15]Review notes[/]\n{warning_lines}"
        self._set_simple_status(status)
        self._preserve_simple_status = True
        self._set_status("Automatic MIDI + WAV ready · source unchanged")
        self._activity(
            "simple",
            (
                f"Simple result published with {selected_count} automatic "
                f"primary part(s) and {omitted_count} omitted role(s). No human "
                "review or feedback event was recorded."
            ),
        )
        output_dir = getattr(result, "output_dir", None)
        if output_dir is not None:
            self.query_one("#candidate-roots", Input).value = str(output_dir)
            self.query_one(TabbedContent).active = "simple"
            self._start_project_load()

    def _apply_simple_progress(self, progress: Any, sequence: int) -> None:
        if sequence != self._simple_sequence or not self._simple_running:
            return
        completed = max(0, int(getattr(progress, "completed", 0) or 0))
        total = max(1, int(getattr(progress, "total", 6) or 6))
        completed = min(completed, total)
        phase = str(getattr(progress, "phase", "create") or "create")
        message = str(getattr(progress, "message", "") or "").strip()
        self.query_one("#simple-progress", ProgressBar).update(
            total=total,
            progress=completed,
        )
        self._set_simple_status(
            f"{completed}/{total} · {phase}\n{message or 'Working locally…'}"
        )
        self._set_status(f"Make my song · {completed}/{total} · {phase}")
        if phase != self._simple_last_phase:
            self._simple_last_phase = phase
            self._activity("simple", f"{phase}: {message or 'running'}")

    @work(exclusive=True, group="simple-cancel")
    async def _cancel_simple_create(self) -> None:
        await self._request_simple_cancel(wait=False)

    async def _request_simple_cancel(self, *, wait: bool) -> None:
        if not self._simple_running:
            return
        self._simple_cancel_requested.set()
        self.query_one("#cancel-simple", Button).disabled = True
        self._set_simple_status(
            (
                "Cancellation requested. A model process will stop at its next "
                "safe boundary; a WAV already being verified must finish safely."
            )
        )
        self._set_status("Cancelling Simple creation…")
        self._activity("simple", "Cancellation requested.")
        runner = self._simple_runner
        if runner is not None:
            try:
                cancelled = runner.cancel()
                if inspect.isawaitable(cancelled):
                    await cancelled
            except Exception as exc:
                self._activity(
                    "error",
                    f"Simple cancellation warning: {_safe_exception_message(exc)}",
                )
        if wait:
            try:
                await asyncio.wait_for(
                    self._simple_done.wait(),
                    timeout=10.0,
                )
            except asyncio.TimeoutError:
                pass

    async def _stop_simple_create(self, *, notify_timeout: bool = True) -> bool:
        if not self._simple_running:
            return True
        await self._request_simple_cancel(wait=True)
        if not self._simple_running:
            return True
        self._activity(
            "error",
            "Simple creation is still stopping; terminal shutdown was deferred.",
        )
        if notify_timeout:
            self.notify(
                "Simple creation is still stopping; try Quit again shortly",
                severity="warning",
            )
        return False

    def _finish_simple_failure(
        self,
        sequence: int,
        message: str,
        *,
        controls_already_reset: bool = False,
    ) -> None:
        if sequence != self._simple_sequence:
            return
        self._simple_running = False
        self._simple_done.set()
        if not controls_already_reset:
            self._set_project_controls_locked(False)
            self._sync_simple_controls(update_status=False)
        self._set_simple_status(message, error=True)
        self._set_status("Simple creation failed · source unchanged")
        self._activity("error", message)

    def _set_simple_status(self, message: str, *, error: bool = False) -> None:
        try:
            target = self.query_one("#simple-status", Static)
        except Exception:
            return
        prefix = "[bold #fb7185]Cannot make the song.[/] " if error else ""
        target.update(f"{prefix}{message}")

    def _simple_start_problem(self, *, require_loaded: bool) -> str | None:
        if self._project_loading:
            return "Wait for the current project check to finish."
        if self.catalog_path is not None:
            return (
                "Simple mode discovers its exact production primaries from a "
                "fresh conversion. Relaunch without --catalog, or use Studio."
            )
        raw_project = self.query_one("#project-path", Input).value.strip()
        if not raw_project:
            return "Choose a folder containing top-level WAV stems."
        project = Path(raw_project).expanduser().resolve()
        if not project.is_dir():
            return "The stem project folder does not exist."
        input_problem = prepared_project_input_problem(project)
        if input_problem is not None:
            return input_problem
        if require_loaded and (
            self.snapshot is None or self.snapshot.config.project != project
        ):
            return "Wait for Sunofriend to finish checking the stem project."
        output_value = self.query_one("#simple-output", Input).value.strip()
        if not output_value:
            return "Choose a fresh, separate output folder."
        output = Path(output_value).expanduser().resolve()
        if output == project or project in output.parents:
            return "The Simple output must be outside the source project."
        if output.exists() or output.is_symlink():
            return (
                "The Simple output already exists. Choose a fresh folder; "
                "Sunofriend never overwrites a prior result."
            )
        return None

    def _sync_simple_controls(self, *, update_status: bool) -> None:
        try:
            output = self.query_one("#simple-output", Input)
            create = self.query_one("#create-simple", Button)
            cancel = self.query_one("#cancel-simple", Button)
        except Exception:
            return
        studio_active = (
            self._workbench_launching or self._workbench_process is not None
        )
        locked = (
            self._simple_running
            or self._conversion_running
            or self._listening_master_running
            or studio_active
        )
        output.disabled = locked
        problem = self._simple_start_problem(require_loaded=False)
        create.disabled = locked or self._project_loading or problem is not None
        cancel.disabled = not self._simple_running
        if update_status and not self._simple_running:
            if problem is None:
                self._set_simple_status(
                    (
                        "Ready. Press Create MIDI + WAV once. Sunofriend will "
                        "convert every supported stem, choose only production "
                        "primaries, balance the interpretation and make a ZIP."
                    )
                )
            else:
                self._set_simple_status(problem, error=True)

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
        shadowed = tuple(getattr(result, "shadowed_roles", ()) or ())
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
        if shadowed:
            disclosures.append(
                "Automatic-arrangement shadowed role(s): "
                f"{escape_markup(', '.join(map(str, shadowed)))}. "
                "Their MIDI remains available in Studio for comparison."
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
        input_problem = prepared_project_input_problem(
            self.snapshot.config.project
        )
        if input_problem is not None:
            return input_problem
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
        locked = (
            self._simple_running
            or self._conversion_running
            or self._listening_master_running
            or studio_active
        )
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
                or self._simple_running
                or self._conversion_running
                or self._listening_master_running
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

    @work(exclusive=True, group="listening-master")
    async def _run_listening_master(self, request: Any, sequence: int) -> None:
        runner = self._listening_master_runner
        if runner is None:
            self._finish_listening_master_failure(
                sequence,
                "The listening-master runner is unavailable.",
            )
            return
        loop = asyncio.get_running_loop()

        def on_progress(progress: Any) -> None:
            loop.call_soon_threadsafe(
                self._apply_listening_master_progress,
                progress,
                sequence,
            )

        try:
            result = await runner.run(
                request,
                on_progress=on_progress,
            )
        except Exception as exc:
            self._finish_listening_master_failure(
                sequence,
                _safe_exception_message(exc),
            )
            return
        if sequence != self._listening_master_sequence:
            return
        if not bool(getattr(result, "succeeded", False)):
            self._finish_listening_master_failure(
                sequence,
                (
                    "Listening master finished without a verified artifact "
                    f"(status: {getattr(result, 'status', 'failed')})."
                ),
            )
            return

        self._listening_master_running = False
        self._listening_master_done.set()
        self._set_project_controls_locked(False)
        self._sync_listening_master_controls(update_status=False)
        total = max(1, self._listening_master_progress_total)
        self.query_one("#master-progress", ProgressBar).update(
            total=total,
            progress=total,
        )
        summary = getattr(result, "summary", {}) or {}
        cache_hit = bool(getattr(result, "cache_hit", False))
        master_path = getattr(result, "master_path", None)
        receipt_path = getattr(result, "receipt_path", None)
        control_path = getattr(result, "balanced_control_path", None)
        policy = str(getattr(result, "policy", "fixed-policy") or "fixed-policy")
        selection_hash = str(
            getattr(result, "selection_manifest_sha256", "") or ""
        )
        balanced_hash = str(
            getattr(result, "balanced_arrangement_manifest_sha256", "") or ""
        )
        input_lufs = summary.get("input_integrated_lufs", "unknown")
        output_lufs = summary.get("output_integrated_lufs", "unknown")
        output_peak = summary.get("output_true_peak_dbtp", "unknown")
        status = (
            "[bold #5eead4]Verified listening master "
            f"{'reused' if cache_hit else 'created'}.[/]\n"
            f"[bold]Input control[/] {input_lufs} LUFS\n"
            f"[bold]Output[/] {output_lufs} LUFS · {output_peak} dBTP · PCM24\n"
            f"[bold]Policy[/] {escape_markup(policy)} · exact song horizon\n"
            "[bold]Meaning[/] mastered: true · release master: false\n"
            f"[bold]Selection[/] {selection_hash[:12] or 'unknown'}… · "
            f"[bold]balanced control[/] {balanced_hash[:12] or 'unknown'}…\n"
            f"[bold]Control WAV[/] "
            f"{escape_markup(str(control_path or 'unavailable'))}\n"
            f"[bold]Challenger WAV[/] "
            f"{escape_markup(str(master_path or 'unavailable'))}\n"
            f"[bold]Receipt[/] "
            f"{escape_markup(str(receipt_path or 'unavailable'))}\n\n"
            "[#9fb3c8]The balanced control, MIDI choices, reviews and Pack basket "
            "remain unchanged. Open the Visual Studio to hear and download both "
            "versions.[/]"
        )
        self._set_listening_master_status(status)
        self._preserve_listening_master_status = True
        self._set_status(
            f"Listening master {'reused' if cache_hit else 'created'} · "
            "control unchanged"
        )
        self._activity(
            "master",
            (
                f"Verified listening master {'reused' if cache_hit else 'created'}; "
                "mastered true, release master false, no preference recorded."
            ),
        )

    def _apply_listening_master_progress(
        self,
        progress: Any,
        sequence: int,
    ) -> None:
        if (
            sequence != self._listening_master_sequence
            or not self._listening_master_running
        ):
            return
        completed = max(0, int(getattr(progress, "completed", 0) or 0))
        total = max(
            1,
            int(
                getattr(
                    progress,
                    "total",
                    LISTENING_MASTER_PROGRESS_TOTAL,
                )
                or LISTENING_MASTER_PROGRESS_TOTAL
            ),
        )
        self._listening_master_progress_total = total
        completed = min(completed, total)
        phase = str(getattr(progress, "phase", "master") or "master")
        message = str(getattr(progress, "message", "") or "").strip()
        self.query_one("#master-progress", ProgressBar).update(
            total=total,
            progress=completed,
        )
        detail = f"{completed}/{total} · {phase}"
        if message:
            detail += f"\n{message}"
        self._set_listening_master_status(detail)
        self._set_status(f"Listening master · {completed}/{total} · {phase}")
        if phase != self._listening_master_last_phase:
            self._listening_master_last_phase = phase
            self._activity("master", f"{phase}: {message or 'running'}")

    async def _wait_for_listening_master(
        self,
        *,
        notify_timeout: bool = True,
    ) -> bool:
        if not self._listening_master_running:
            return True
        self._set_listening_master_status(
            (
                "The verified FFmpeg operation has no unsafe pseudo-cancel. "
                "Quit is waiting for its current bounded build to finish."
            )
        )
        self._set_status("Waiting for listening master safe completion…")
        try:
            await asyncio.wait_for(
                self._listening_master_done.wait(),
                timeout=_LISTENING_MASTER_QUIT_WAIT_SECONDS,
            )
        except asyncio.TimeoutError:
            pass
        if not self._listening_master_running:
            return True
        self._activity(
            "master",
            "Quit deferred while the listening master remains active.",
        )
        if notify_timeout:
            self.notify(
                "Listening master is still running; try Quit again after it finishes",
                severity="warning",
            )
        return False

    def _finish_listening_master_failure(
        self,
        sequence: int,
        message: str,
    ) -> None:
        if sequence != self._listening_master_sequence:
            return
        self._listening_master_running = False
        self._listening_master_done.set()
        self._set_project_controls_locked(False)
        self._sync_listening_master_controls(update_status=False)
        self._set_listening_master_status(message, error=True)
        self._set_status("Listening master unavailable · control unchanged")
        self._activity("error", message)

    def _set_listening_master_status(
        self,
        message: str,
        *,
        error: bool = False,
    ) -> None:
        try:
            target = self.query_one("#master-status", Static)
        except Exception:
            return
        prefix = "[bold #fb7185]Cannot master.[/] " if error else ""
        target.update(f"{prefix}{message}")

    def _listening_master_start_problem(self) -> str | None:
        if self.snapshot is None:
            return "Load and verify a project first."
        if self._project_loading:
            return "Wait for the current project load to finish."
        if self._simple_running:
            return "Wait for Simple creation to finish or cancel it first."
        if self._conversion_running:
            return "Wait for conversion to finish or cancel it first."
        raw_project = self.query_one("#project-path", Input).value.strip()
        if (
            not raw_project
            or Path(raw_project).expanduser().resolve()
            != self.snapshot.config.project
        ):
            return "The project path changed. Load it before mastering."
        current_roots = tuple(
            Path(root).expanduser().resolve()
            for root in parse_candidate_roots(
                self.query_one("#candidate-roots", Input).value
            )
        )
        if current_roots != self.snapshot.config.candidate_roots:
            return "The MIDI result roots changed. Load them before mastering."
        selected = int(
            self.snapshot.document.get("counts", {}).get(
                "selected_part_count",
                0,
            )
            or 0
        )
        if selected < 1:
            return (
                "Choose at least one MIDI part and create its balanced "
                "song-interpretation WAV in the Visual Studio first."
            )
        if not self.query_one("#master-confirm", Checkbox).value:
            return (
                "Confirm that this is a separate comparative challenger, not "
                "a release master or preference."
            )
        return None

    def _sync_listening_master_controls(self, *, update_status: bool) -> None:
        try:
            confirmation = self.query_one("#master-confirm", Checkbox)
            create = self.query_one("#create-listening-master", Button)
        except Exception:
            return
        studio_active = (
            self._workbench_launching or self._workbench_process is not None
        )
        locked = (
            self._listening_master_running
            or self._simple_running
            or self._conversion_running
            or studio_active
        )
        confirmation.disabled = locked
        problem = self._listening_master_start_problem()
        create.disabled = locked or self._project_loading or problem is not None
        if update_status and not self._listening_master_running:
            if problem is None:
                self._set_listening_master_status(
                    (
                        "Ready to verify the exact current balanced control, "
                        "then create or reuse its fixed-policy challenger."
                    )
                )
            else:
                self._set_listening_master_status(problem, error=True)

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
            "simple": "#5eead4",
            "conversion": "#34d399",
            "master": "#22d3ee",
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
        self.query_one("#system-check", Button).disabled = locked
        try:
            self.query_one("#simple-output", Input).disabled = locked
            self.query_one("#conversion-output", Input).disabled = locked
            self.query_one("#conversion-confirm", Checkbox).disabled = locked
            self.query_one("#master-confirm", Checkbox).disabled = locked
        except Exception:
            pass
        self._sync_simple_controls(update_status=False)
        self._sync_conversion_controls(update_status=False)
        self._sync_listening_master_controls(update_status=False)

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
    initial_mode: str = "simple",
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
        initial_mode=initial_mode,
        developer_inspector=developer_inspector,
    )
    app.run()
    return 0


def _safe_exception_message(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:500]


def _mode_description(mode: str) -> str:
    if mode == "simple":
        return (
            "Automatic, explicitly unreviewed MIDI + WAV + ZIP. "
            "Switching changes only this view."
        )
    if mode == "studio":
        return (
            "Compare, correct and export with explicit choices. "
            "Switching changes only this view."
        )
    raise ValueError("TUI mode must be simple or studio")


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


def _suggest_fresh_simple_output(project: Path) -> str:
    """Suggest but never create a fresh sibling Simple result directory."""

    expanded = project.expanduser()
    base = expanded.parent / f"{expanded.name}-sunofriend-song-v1"
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


_SIMPLE_SCOPE = """\
[bold #5eead4]Make a useful first version without learning the technical tools[/]

[bold]You provide[/] one folder containing top-level WAV stems. Put the BPM,
key and tuning in its name, for example [bold]My Song-B minor-113bpm-440hz[/].

[bold]Sunofriend makes[/]
• one exact automatic-primary MIDI file for every safely paired role;
• one combined General MIDI interpretation;
• one source-referenced balanced interpretation WAV; and
• a starter ZIP plus a plain-English receipt.

[bold]What “automatic” means[/]
Sunofriend uses only the primary result explicitly published by each production
repair conversion. It does not score all alternatives and invent a winner,
write a Workbench decision, or claim that you reviewed the result. Missing,
ambiguous, silent and diagnostic-only roles are listed instead of being hidden.

The WAV contains rendered MIDI only. Source stems provide timing, song length
and relative-level evidence; their audio is not mixed into it. The result is a
creative starting interpretation, not an exact reconstruction or release
master. Open [bold]Visual Studio[/] afterwards to compare methods, improve the
choices, record feedback and compose a reviewed GarageBand pack.
"""


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

[bold]4 · Master[/] is ready now. After the verified balanced WAV exists, the
[bold]Master[/] tab creates or reuses one fixed-policy PCM24 listening
challenger. It checks the current selection and control before and after the
render. The balanced gain-only WAV remains the control; the challenger is
labelled [bold]mastered: true[/] and [bold]release master: false[/] and records
no preference.

[bold]5 · Understand[/] uses the optional Developer Inspector in that same local
site. It exposes application operations and before/after state, not Python-line
debugging, and cannot change choices or MIDI.

[bold]6 · Export[/] leaves the song-interpretation WAV available as its own
download and uses the existing GarageBand Pack Composer for exact selected
MIDI. Its basket is separate from playback, mixer state and review decisions;
only explicit choices enter the ZIP.

[bold]7 · Create[/] retains immutable Clip alternatives and review-before-write
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

_LISTENING_MASTER_SCOPE = """\
[bold #5eead4]A separate listening challenger for the verified balanced WAV[/]

[bold]What runs[/]
• Sunofriend first finds the exact current selected-MIDI manifest and verified
  balanced v3 song-interpretation WAV. You cannot supply a different input.
• A path-free preflight checks the local audio runtime plus a pinned FFmpeg
  executable with the loudnorm filter.
• One fixed two-pass loudness policy creates PCM24 audio, preserves the exact
  frame horizon, verifies the encoded WAV, and writes a reproducibility receipt.
• An identical verified result is reused from the private content-addressed
  cache instead of being rendered again.

[bold]What does not happen[/]
The balanced gain-only WAV is never replaced or modified. MIDI, selections,
reviews, feedback, default choices and the GarageBand Pack basket do not change.
The new WAV is a comparative listening master, not a release master. This TUI
action records no A/B winner and makes no automatic recommendation.

[bold]Safe execution[/]
Project changes, conversion and Visual Studio launch are locked while the
synchronous verified FFmpeg build runs. Immediate cancellation is not claimed:
Quit waits for completion rather than abandoning potentially publishable work.
"""

_PRIVACY_GUIDE = """\
[bold #60a5fa]Private by construction[/]

Everything runs locally. No audio, MIDI, review, activity log or feedback is
uploaded. Activity shown here is bounded and memory-only. Playback, highlighting
a row and opening a view are not musical preferences. Any future contribution
or aggregate learning remains a separate explicit-consent Phase 7 feature.
"""


__all__ = ["SunofriendTui", "run_tui"]
