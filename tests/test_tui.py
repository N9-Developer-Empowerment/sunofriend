from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Input,
    ProgressBar,
    Static,
    TabbedContent,
)

from sunofriend.cli import build_parser, main
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.tui import SunofriendTui
from sunofriend.tui_conversion_contract import (
    FullConversionProgress,
    FullConversionResult,
)
from sunofriend.tui_listening_master_contract import (
    ListeningMasterProgress,
    ListeningMasterResult,
)
from sunofriend.simple_create_contract import (
    SimpleCreateProgress,
    SimpleCreateResult,
)


class TuiCliTests(unittest.TestCase):
    def test_parser_accepts_interactive_or_preconfigured_launch(self) -> None:
        parser = build_parser()
        empty = parser.parse_args(["tui"])
        configured = parser.parse_args(
            [
                "tui",
                "/music/song",
                "--candidate-root",
                "/music/results-a",
                "--candidate-root",
                "/music/results-b",
                "--conversion-output",
                "/music/fresh-results",
                "--no-developer-inspector",
            ]
        )

        self.assertIsNone(empty.project)
        self.assertIsNone(empty.conversion_output)
        self.assertEqual(empty.mode, "simple")
        self.assertTrue(empty.developer_inspector)
        self.assertEqual(configured.project, "/music/song")
        self.assertEqual(
            configured.candidate_root,
            ["/music/results-a", "/music/results-b"],
        )
        self.assertEqual(configured.conversion_output, "/music/fresh-results")
        self.assertEqual(configured.mode, "simple")
        self.assertFalse(configured.developer_inspector)

    @patch("sunofriend.tui.run_tui", return_value=0)
    def test_cli_dispatches_to_tui(self, run_tui) -> None:
        result = main(
            [
                "tui",
                "/music/song",
                "--candidate-root",
                "/music/results",
            ]
        )

        self.assertEqual(result, 0)
        run_tui.assert_called_once_with(
            project="/music/song",
            candidate_roots=("/music/results",),
            catalog_path=None,
            state_dir=None,
            soundfont_path=None,
            initial_conversion_output=None,
            initial_mode="simple",
            developer_inspector=True,
        )


class TuiInteractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_app_is_guided_and_keeps_studio_disabled(self) -> None:
        app = SunofriendTui()
        async with app.run_test(size=(140, 44)) as pilot:
            await pilot.pause()
            self.assertIn("song-interpretation WAV", app.SUB_TITLE)
            self.assertIn(
                "song-interpretation WAV",
                str(app.query_one("#tagline", Static).render()),
            )
            self.assertEqual(app.query_one("#project-path", Input).value, "")
            self.assertTrue(app.query_one("#open-studio", Button).disabled)
            self.assertEqual(app.query_one(TabbedContent).active, "simple")
            self.assertIn(
                "automatic",
                str(app.query_one("#simple-scope", Static).render()).lower(),
            )
            self.assertIn(
                "Choose a stem project",
                str(app.query_one("#project-summary", Static).render()),
            )

    async def test_explicit_mode_switch_is_two_way_and_navigation_only(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "state-that-must-not-exist"
            app = SunofriendTui(state_dir=state)

            async with app.run_test(size=(150, 50)) as pilot:
                tabs = app.query_one("#workspace-tabs", TabbedContent)
                simple = app.query_one("#switch-simple", Button)
                studio = app.query_one("#switch-studio", Button)
                description = app.query_one("#mode-description", Static)

                self.assertEqual(tabs.active, "simple")
                self.assertTrue(simple.has_class("active-mode"))
                self.assertFalse(studio.has_class("active-mode"))
                self.assertIn(
                    "switching changes only this view",
                    str(description.render()).lower(),
                )

                studio.press()
                await pilot.pause()
                self.assertEqual(tabs.active, "overview")
                self.assertFalse(simple.has_class("active-mode"))
                self.assertTrue(studio.has_class("active-mode"))

                tabs.active = "convert"
                await pilot.pause()
                await pilot.press("f2")
                await pilot.pause()
                self.assertEqual(tabs.active, "simple")

                await pilot.press("f3")
                await pilot.pause()
                self.assertEqual(tabs.active, "convert")
                self.assertTrue(studio.has_class("active-mode"))

                self.assertIsNone(app.snapshot)
                self.assertIsNone(app._workbench_process)
                self.assertFalse(state.exists())

    async def test_simple_mode_needs_one_explicit_create_action_and_no_review_event(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, _candidates = _fixture(root)
            output = root / "automatic-song-output"
            state = root / "state-that-must-not-exist"
            runner = _CompletingSimpleRunner()
            app = SunofriendTui(
                project=project,
                state_dir=state,
                simple_runner=runner,
            )

            async with app.run_test(size=(150, 50)) as pilot:
                for _ in range(100):
                    await pilot.pause(0.02)
                    if app.snapshot is not None and not app._project_loading:
                        break
                self.assertFalse(app._project_loading)
                app.query_one("#simple-output", Input).value = str(output)
                await pilot.pause()
                create = app.query_one("#create-simple", Button)
                self.assertFalse(create.disabled)
                self.assertNotIn("confirm", str(create.label).lower())
                create.press()

                for _ in range(200):
                    await pilot.pause(0.02)
                    if not app._simple_running and runner.request is not None:
                        break

                self.assertEqual(runner.request.project, project.resolve())
                self.assertEqual(runner.request.output_dir, output.resolve())
                self.assertIn(
                    "automatic song is ready",
                    str(app.query_one("#simple-status", Static).render()).lower(),
                )
                self.assertEqual(app.query_one(TabbedContent).active, "simple")
                self.assertFalse((state / "workbench.sqlite3").exists())

    async def test_unmount_discards_a_slow_project_refresh(self) -> None:
        from sunofriend.tui_model import load_tui_project as real_load

        with tempfile.TemporaryDirectory() as temporary:
            project, candidates = _fixture(Path(temporary))
            calls = 0

            def delayed_second_load(config):
                nonlocal calls
                calls += 1
                if calls == 2:
                    time.sleep(0.25)
                return real_load(config)

            app = SunofriendTui(project=project, candidate_roots=(candidates,))
            with patch(
                "sunofriend.tui.load_tui_project",
                side_effect=delayed_second_load,
            ):
                async with app.run_test(size=(150, 50)) as pilot:
                    for _ in range(100):
                        await pilot.pause(0.02)
                        if app.snapshot is not None:
                            break
                    self.assertIsNotNone(app.snapshot)
                    app.action_refresh_project()
                    await pilot.pause(0.01)

            self.assertEqual(calls, 2)

    async def test_simple_mode_requires_whole_mixed_folder_preparation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "mixed-source-parts"
            project.mkdir()
            (project / "song-bass.wav").touch()
            (project / "song-keys.flac").touch()
            output = root / "must-not-exist"
            app = SunofriendTui(project=project)

            async with app.run_test(size=(150, 50)) as pilot:
                app.query_one("#simple-output", Input).value = str(output)
                await pilot.pause()

                create = app.query_one("#create-simple", Button)
                status = str(
                    app.query_one("#simple-status", Static).render()
                ).lower()
                self.assertTrue(create.disabled)
                self.assertIn("will not silently ignore", status)
                self.assertIn("source-import-folder", status)
                self.assertFalse(output.exists())

    async def test_project_load_populates_dashboard_and_midi_map(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, candidates = _fixture(Path(temporary))
            state = Path(temporary) / "state-that-must-not-be-created"
            app = SunofriendTui(
                project=project,
                candidate_roots=(candidates,),
                state_dir=state,
            )

            async with app.run_test(size=(150, 50)) as pilot:
                for _ in range(100):
                    await pilot.pause(0.02)
                    if app.snapshot is not None:
                        break
                self.assertIsNotNone(app.snapshot)
                table = app.query_one("#stem-table", DataTable)
                self.assertEqual(table.row_count, 2)
                self.assertFalse(app.query_one("#open-studio", Button).disabled)
                self.assertFalse(state.exists())
                summary = str(
                    app.query_one("#project-summary", Static).render()
                )
                self.assertIn("Source stems", summary)
                self.assertIn("MIDI-ready", summary)
                self.assertIn("Missing MIDI", summary)
                self.assertIn("Partial MIDI results", summary)
                self.assertIn("Convert all stems", summary)
                self.assertIn("Song-interpretation WAV", summary)
                self.assertIn("only review existing results", summary)
                for _ in range(100):
                    await pilot.pause(0.02)
                    rendered = str(app.query_one("#midi-map", Static).render())
                    if "Primary MIDI alternatives" in rendered:
                        break
                self.assertIn("Primary MIDI alternatives", rendered)
                self.assertIn("activity", rendered)

    async def test_full_conversion_requires_confirmation_then_reloads_fresh_root(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _fixture(root)
            output = root / "fresh-full-result"
            runner = _CompletingConversionRunner()
            app = SunofriendTui(
                project=project,
                candidate_roots=(candidates,),
                initial_conversion_output=output,
                conversion_runner=runner,
            )

            async with app.run_test(size=(150, 50)) as pilot:
                for _ in range(100):
                    await pilot.pause(0.02)
                    if app.snapshot is not None:
                        break
                self.assertEqual(
                    app.query_one("#conversion-output", Input).value,
                    str(output),
                )
                self.assertIsNone(runner.request)
                convert = app.query_one("#convert-all", Button)
                self.assertTrue(convert.disabled)
                self.assertIn(
                    "full supported instrumental conversion",
                    str(app.query_one("#conversion-scope", Static).render()),
                )

                app.query_one("#conversion-confirm", Checkbox).value = True
                await pilot.pause()
                self.assertFalse(convert.disabled)
                convert.press()

                for _ in range(200):
                    await pilot.pause(0.02)
                    if (
                        not app._conversion_running
                        and app.snapshot is not None
                        and app.snapshot.config.candidate_roots
                        == (output.resolve(),)
                    ):
                        break

                self.assertIsNotNone(runner.request)
                self.assertEqual(runner.request.project, project.resolve())
                self.assertEqual(runner.request.output_dir, output.resolve())
                self.assertEqual(
                    app.snapshot.config.candidate_roots,
                    (output.resolve(),),
                )
                self.assertEqual(
                    app.query_one("#candidate-roots", Input).value,
                    str(output.resolve()),
                )
                self.assertIn(
                    "conversion complete",
                    str(app.query_one("#conversion-status", Static).render()).lower(),
                )
                conversion_status = str(
                    app.query_one("#conversion-status", Static).render()
                )
                self.assertIn(
                    "Skipped role(s): backing_vocals",
                    conversion_status,
                )
                self.assertIn(
                    "Review-required proxy role(s): bass",
                    conversion_status,
                )
                self.assertIn("conservative keys engine", conversion_status)
                progress = app.query_one("#conversion-progress", ProgressBar)
                self.assertEqual(progress.progress, progress.total)
                self.assertFalse(
                    app.query_one("#project-path", Input).disabled
                )

    async def test_cancel_stops_conversion_and_does_not_reload_partial_output(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _fixture(root)
            output = root / "cancelled-full-result"
            runner = _CancellableConversionRunner()
            app = SunofriendTui(
                project=project,
                candidate_roots=(candidates,),
                initial_conversion_output=output,
                conversion_runner=runner,
            )

            async with app.run_test(size=(150, 50)) as pilot:
                for _ in range(100):
                    await pilot.pause(0.02)
                    if app.snapshot is not None:
                        break
                app.query_one("#conversion-confirm", Checkbox).value = True
                await pilot.pause()
                app.query_one("#convert-all", Button).press()
                for _ in range(100):
                    await pilot.pause(0.02)
                    if runner.started.is_set():
                        break

                self.assertTrue(app._conversion_running)
                self.assertTrue(app.query_one("#project-path", Input).disabled)
                self.assertTrue(
                    app.query_one("#conversion-output", Input).disabled
                )
                app.query_one("#cancel-conversion", Button).press()
                for _ in range(100):
                    await pilot.pause(0.02)
                    if not app._conversion_running:
                        break

                self.assertTrue(runner.cancel_called)
                self.assertEqual(
                    app.snapshot.config.candidate_roots,
                    (candidates.resolve(),),
                )
                self.assertIn(
                    "cancelled",
                    str(app.query_one("#conversion-status", Static).render()).lower(),
                )
                self.assertFalse(app.query_one("#project-path", Input).disabled)
                self.assertFalse(
                    app.query_one("#conversion-output", Input).disabled
                )

    async def test_quit_cancels_and_reaps_active_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _fixture(root)
            runner = _CancellableConversionRunner()
            app = SunofriendTui(
                project=project,
                candidate_roots=(candidates,),
                initial_conversion_output=root / "quit-cancelled-result",
                conversion_runner=runner,
            )

            async with app.run_test(size=(130, 44)) as pilot:
                for _ in range(100):
                    await pilot.pause(0.02)
                    if app.snapshot is not None:
                        break
                app.query_one("#conversion-confirm", Checkbox).value = True
                await pilot.pause()
                app.query_one("#convert-all", Button).press()
                for _ in range(100):
                    await pilot.pause(0.02)
                    if runner.started.is_set():
                        break

                await app.action_request_quit()

                self.assertTrue(runner.cancel_called)
                self.assertFalse(app._conversion_running)
                self.assertTrue(app._conversion_done.is_set())

    async def test_conversion_rejects_existing_output(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _fixture(root)
            existing = root / "existing-output"
            existing.mkdir()
            app = SunofriendTui(
                project=project,
                candidate_roots=(candidates,),
                initial_conversion_output=existing,
            )
            async with app.run_test(size=(140, 48)) as pilot:
                for _ in range(100):
                    await pilot.pause(0.02)
                    if app.snapshot is not None:
                        break
                app.query_one("#conversion-confirm", Checkbox).value = True
                await pilot.pause()

                self.assertTrue(app.query_one("#convert-all", Button).disabled)
                self.assertIn(
                    "already exists",
                    str(app.query_one("#conversion-status", Static).render()),
                )

    async def test_conversion_rejects_explicit_catalog_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _fixture(root)
            source = project / "TUI Song-bass-D minor-120bpm-440hz.wav"
            midi = candidates / "bass-listened" / "bass_listened.mid"
            catalog = root / "catalog.json"
            catalog.write_text(
                json.dumps(
                    {
                        "schema": "sunofriend.workbench-catalog.v1",
                        "stems": [
                            {
                                "source": str(source),
                                "role": "bass",
                                "candidates": [{"midi": str(midi)}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            app = SunofriendTui(
                project=project,
                candidate_roots=(candidates,),
                catalog_path=catalog,
                initial_conversion_output=root / "fresh-output",
            )
            async with app.run_test(size=(140, 48)) as pilot:
                for _ in range(100):
                    await pilot.pause(0.02)
                    if app.snapshot is not None:
                        break
                app.query_one("#conversion-confirm", Checkbox).value = True
                await pilot.pause()

                self.assertTrue(app.query_one("#convert-all", Button).disabled)
                status = str(
                    app.query_one("#conversion-status", Static).render()
                )
                self.assertIn("explicit Workbench catalog", status)
                self.assertIn("without --catalog", status)

    async def test_listening_master_requires_confirmation_and_reports_challenger(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _fixture(root)
            runner = _CompletingListeningMasterRunner(root)
            app = SunofriendTui(
                project=project,
                candidate_roots=(candidates,),
                listening_master_runner=runner,
            )

            async with app.run_test(size=(150, 50)) as pilot:
                for _ in range(100):
                    await pilot.pause(0.02)
                    if app.snapshot is not None:
                        break
                self.assertIsNotNone(app.snapshot)
                assert app.snapshot is not None
                app.snapshot.document["counts"]["selected_part_count"] = 1
                app._sync_listening_master_controls(update_status=True)

                create = app.query_one(
                    "#create-listening-master",
                    Button,
                )
                self.assertTrue(create.disabled)
                scope = str(app.query_one("#master-scope", Static).render())
                self.assertIn("balanced gain-only WAV", scope)
                self.assertIn("release master", scope)
                self.assertIn("Immediate cancellation is not claimed", scope)

                app.query_one("#master-confirm", Checkbox).value = True
                await pilot.pause()
                self.assertFalse(create.disabled)
                create.press()

                for _ in range(100):
                    await pilot.pause(0.02)
                    if not app._listening_master_running and runner.request:
                        break

                self.assertIs(runner.request.snapshot, app.snapshot)
                status = str(app.query_one("#master-status", Static).render())
                self.assertIn("Verified listening master created", status)
                self.assertIn("-21.5 LUFS", status)
                self.assertIn("-16.0 LUFS", status)
                self.assertIn("-1.0 dBTP", status)
                self.assertIn("release master: false", status)
                self.assertIn(str(runner.master_path), status)
                self.assertFalse(app.query_one("#project-path", Input).disabled)
                self.assertFalse(app.query_one("#open-studio", Button).disabled)
                progress = app.query_one("#master-progress", ProgressBar)
                self.assertEqual(progress.progress, progress.total)

    async def test_listening_master_locks_competing_operations_while_running(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _fixture(root)
            runner = _BlockingListeningMasterRunner()
            app = SunofriendTui(
                project=project,
                candidate_roots=(candidates,),
                listening_master_runner=runner,
            )

            async with app.run_test(size=(110, 34)) as pilot:
                for _ in range(100):
                    await pilot.pause(0.02)
                    if app.snapshot is not None:
                        break
                assert app.snapshot is not None
                app.snapshot.document["counts"]["selected_part_count"] = 1
                app.query_one("#master-confirm", Checkbox).value = True
                app._sync_listening_master_controls(update_status=True)
                app.query_one("#create-listening-master", Button).press()
                for _ in range(100):
                    await pilot.pause(0.02)
                    if runner.started.is_set():
                        break

                self.assertTrue(app._listening_master_running)
                self.assertTrue(app.query_one("#project-path", Input).disabled)
                self.assertTrue(app.query_one("#candidate-roots", Input).disabled)
                self.assertTrue(app.query_one("#convert-all", Button).disabled)
                self.assertTrue(app.query_one("#open-studio", Button).disabled)
                self.assertTrue(app.query_one("#system-check", Button).disabled)

                with patch(
                    "sunofriend.tui._LISTENING_MASTER_QUIT_WAIT_SECONDS",
                    0.01,
                ):
                    await pilot.press("ctrl+q")
                    await pilot.pause(0.03)
                self.assertTrue(app._listening_master_running)
                self.assertIn(
                    "no unsafe pseudo-cancel",
                    str(app.query_one("#master-status", Static).render()),
                )

                runner.release.set()
                for _ in range(100):
                    await pilot.pause(0.02)
                    if not app._listening_master_running:
                        break
                self.assertFalse(app.query_one("#project-path", Input).disabled)

    async def test_stale_project_worker_cannot_replace_newer_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_project, old_candidates = _fixture(root / "old")
            new_project, new_candidates = _fixture(root / "new")
            from sunofriend.tui_model import load_tui_project as real_load

            def delayed_load(config):
                if config.project == old_project.resolve():
                    time.sleep(0.2)
                return real_load(config)

            app = SunofriendTui(
                project=old_project,
                candidate_roots=(old_candidates,),
            )
            with patch("sunofriend.tui.load_tui_project", side_effect=delayed_load):
                async with app.run_test(size=(110, 34)) as pilot:
                    app.query_one("#project-path", Input).value = str(new_project)
                    app.query_one("#candidate-roots", Input).value = str(
                        new_candidates
                    )
                    app._start_project_load()
                    for _ in range(100):
                        await pilot.pause(0.02)
                        if (
                            app.snapshot is not None
                            and app.snapshot.config.project == new_project.resolve()
                        ):
                            break
                    await pilot.pause(0.25)
                    self.assertIsNotNone(app.snapshot)
                    self.assertEqual(
                        app.snapshot.config.project,
                        new_project.resolve(),
                    )

    async def test_studio_cannot_open_old_snapshot_during_new_project_scan(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_project, old_candidates = _fixture(root / "old")
            new_project, new_candidates = _fixture(root / "new")
            from sunofriend.tui_model import load_tui_project as real_load

            load_started = threading.Event()
            release_load = threading.Event()

            def delayed_new_load(config):
                if config.project == new_project.resolve():
                    load_started.set()
                    if not release_load.wait(timeout=5.0):
                        raise TimeoutError("test did not release the project load")
                return real_load(config)

            app = SunofriendTui(
                project=old_project,
                candidate_roots=(old_candidates,),
            )
            async with app.run_test(size=(140, 44)) as pilot:
                for _ in range(100):
                    await pilot.pause(0.02)
                    if app.snapshot is not None:
                        break
                old_snapshot = app.snapshot
                app.query_one("#project-path", Input).value = str(new_project)
                app.query_one("#candidate-roots", Input).value = str(
                    new_candidates
                )
                with patch(
                    "sunofriend.tui.load_tui_project",
                    side_effect=delayed_new_load,
                ):
                    app._start_project_load()
                    try:
                        self.assertTrue(
                            await asyncio.to_thread(load_started.wait, 2.0),
                            "new project load did not start",
                        )
                        self.assertTrue(app._project_loading)
                        self.assertIs(app.snapshot, old_snapshot)
                        with patch.object(
                            app,
                            "_run_visual_studio",
                        ) as launch:
                            app.action_open_visual_studio()
                            launch.assert_not_called()
                        self.assertFalse(app._workbench_launching)
                    finally:
                        release_load.set()
                    for _ in range(100):
                        await pilot.pause(0.02)
                        if (
                            app.snapshot is not None
                            and app.snapshot.config.project
                            == new_project.resolve()
                        ):
                            break

                self.assertFalse(app._project_loading)
                self.assertEqual(
                    app.snapshot.config.project,
                    new_project.resolve(),
                )
                self.assertFalse(app.query_one("#open-studio", Button).disabled)

    async def test_stop_terminates_and_reaps_workbench_process(self) -> None:
        app = SunofriendTui()
        fake = _FakeProcess()
        async with app.run_test(size=(80, 24)):
            app._workbench_process = fake
            await app._stop_visual_studio()
            self.assertTrue(fake.terminated)
            self.assertTrue(fake.waited)
            self.assertIsNone(app._workbench_process)

    async def test_running_studio_locks_project_and_blocks_project_switch(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _fixture(root / "current")
            other_project, other_candidates = _fixture(root / "other")
            app = SunofriendTui(project=project, candidate_roots=(candidates,))
            async with app.run_test(size=(140, 44)) as pilot:
                for _ in range(100):
                    await pilot.pause(0.02)
                    if app.snapshot is not None:
                        break
                original_snapshot = app.snapshot
                app._workbench_launching = True
                app._set_project_controls_locked(True)
                app.query_one("#project-path", Input).value = str(other_project)
                app.query_one("#candidate-roots", Input).value = str(
                    other_candidates
                )

                app._start_project_load()
                await pilot.pause(0.05)

                self.assertIs(app.snapshot, original_snapshot)
                self.assertTrue(app.query_one("#project-path", Input).disabled)
                self.assertTrue(app.query_one("#load-project", Button).disabled)
                app._workbench_launching = False
                app._set_project_controls_locked(False)

    async def test_failed_studio_launch_unlocks_project_controls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, candidates = _fixture(Path(temporary))
            app = SunofriendTui(project=project, candidate_roots=(candidates,))
            async with app.run_test(size=(140, 44)) as pilot:
                for _ in range(100):
                    await pilot.pause(0.02)
                    if app.snapshot is not None:
                        break
                with patch(
                    "sunofriend.tui.asyncio.create_subprocess_exec",
                    side_effect=OSError("launch unavailable"),
                ):
                    app.action_open_visual_studio()
                    for _ in range(100):
                        await pilot.pause(0.02)
                        if not app._workbench_launching:
                            break

                self.assertFalse(app.query_one("#project-path", Input).disabled)
                self.assertFalse(app.query_one("#load-project", Button).disabled)
                self.assertTrue(app.query_one("#stop-studio", Button).disabled)

    async def test_f6_opens_studio_without_editing_focused_path(self) -> None:
        app = SunofriendTui()
        async with app.run_test(size=(120, 44)) as pilot:
            project = app.query_one("#project-path", Input)
            project.value = "/tmp/some project"
            project.focus()
            with patch.object(app, "action_open_visual_studio") as open_action:
                await pilot.press("f6")
                await pilot.pause()

            self.assertEqual(project.value, "/tmp/some project")
            open_action.assert_called_once_with()

    async def test_narrow_terminal_retains_keyboard_dashboard(self) -> None:
        app = SunofriendTui(initial_mode="studio")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("tab", "tab", "tab")
            await pilot.pause()
            self.assertIsNotNone(app.focused)
            table = app.query_one("#stem-table", DataTable)
            status = app.query_one("#status-line", Static)
            footer = app.query_one(Footer)
            self.assertTrue(app.screen.has_class("compact"))
            self.assertGreaterEqual(table.region.height, 3)
            self.assertLess(table.region.y, status.region.y)
            self.assertLess(status.region.y, footer.region.y)
            self.assertEqual(
                app.query_one("#midi-map", Static).styles.display,
                "none",
            )
            self.assertIsNotNone(app.query_one("#activity-log"))

    async def test_compact_layout_covers_height_breakpoint(self) -> None:
        app = SunofriendTui(initial_mode="studio")
        async with app.run_test(size=(110, 34)) as pilot:
            await pilot.pause()
            table = app.query_one("#stem-table", DataTable)
            status = app.query_one("#status-line", Static)

            self.assertTrue(app.screen.has_class("compact"))
            self.assertGreaterEqual(table.region.height, 3)
            self.assertLess(table.region.y, status.region.y)


def _fixture(root: Path) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    project = root / "TUI Song-D minor-120bpm-440hz"
    candidates = root / "outputs"
    project.mkdir()
    (project / "TUI Song-bass-D minor-120bpm-440hz.wav").write_bytes(
        b"RIFF-local-source"
    )
    (project / "TUI Song-backing-vocals-D minor-120bpm-440hz.wav").write_bytes(
        b"RIFF-local-vocal-source"
    )
    midi = candidates / "bass-listened" / "bass_listened.mid"
    midi.parent.mkdir(parents=True)
    write_midi_file(
        midi,
        [
            MidiTrack(
                "Bass",
                0,
                32,
                [
                    NoteEvent(0.0, 0.4, 38, 90),
                    NoteEvent(0.5, 0.9, 41, 88),
                ],
            )
        ],
        bpm=120.0,
    )
    return project, candidates


class _FakeProcess:
    def __init__(self) -> None:
        self.returncode = None
        self.terminated = False
        self.killed = False
        self.waited = False

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    async def wait(self) -> int:
        self.waited = True
        return int(self.returncode or 0)


class _CompletingConversionRunner:
    def __init__(self) -> None:
        self.request = None
        self.cancel_called = False

    async def run(
        self,
        request,
        *,
        on_progress,
        cancellation_requested=None,
    ) -> FullConversionResult:
        self.request = request
        on_progress(
            FullConversionProgress(
                completed=1,
                total=2,
                phase="instrumental",
                message="Converted bass.",
                current_role="bass",
            )
        )
        midi = request.output_dir / "mode_repair" / "selected_bass"
        _write_conversion_midi(midi / "bass_listened.mid")
        on_progress(
            FullConversionProgress(
                completed=2,
                total=2,
                phase="reload",
                message="Verified fresh result root.",
            )
        )
        return FullConversionResult(
            status="complete",
            output_dir=request.output_dir,
            candidate_roots=(request.output_dir,),
            converted_roles=("bass",),
            skipped_roles=("backing_vocals",),
            failed_roles=(),
            proxy_roles=("bass",),
            warnings=(
                "bass uses the conservative keys engine and remains review-required",
            ),
            summary_paths=(),
            source_stem_count=2,
            midi_ready_stem_count=1,
            candidate_count=1,
        )

    def cancel(self) -> None:
        self.cancel_called = True


class _CancellableConversionRunner:
    def __init__(self) -> None:
        self.request = None
        self.cancel_called = False
        self.started = asyncio.Event()

    async def run(
        self,
        request,
        *,
        on_progress,
        cancellation_requested=None,
    ) -> FullConversionResult:
        self.request = request
        self.started.set()
        on_progress(
            FullConversionProgress(
                completed=0,
                total=2,
                phase="instrumental",
                message="Starting bass.",
                current_role="bass",
            )
        )
        while not (cancellation_requested and cancellation_requested()):
            await asyncio.sleep(0.01)
        request.output_dir.mkdir(parents=True, exist_ok=True)
        return FullConversionResult(
            status="cancelled",
            output_dir=request.output_dir,
            candidate_roots=(),
            converted_roles=(),
            skipped_roles=(),
            failed_roles=(),
            proxy_roles=(),
            warnings=("cancelled",),
            summary_paths=(),
            source_stem_count=2,
            midi_ready_stem_count=0,
            candidate_count=0,
        )

    def cancel(self) -> None:
        self.cancel_called = True


class _CompletingSimpleRunner:
    def __init__(self) -> None:
        self.request = None
        self.cancel_called = False

    async def run(
        self,
        request,
        *,
        on_progress,
        cancellation_requested=None,
    ) -> SimpleCreateResult:
        self.request = request
        on_progress(
            SimpleCreateProgress(
                completed=1,
                total=6,
                phase="convert",
                message="Converting stems",
            )
        )
        root = request.output_dir / "AUTOMATIC-SONG"
        midi = root / "MIDI" / "combined-gm-interpretation.mid"
        wav = root / "AUDIO" / "balanced-midi-song-interpretation.wav"
        manifest = root / "sunofriend-result.json"
        archive = root / "sunofriend-automatic-midi-and-wav.zip"
        midi.parent.mkdir(parents=True, exist_ok=True)
        wav.parent.mkdir(parents=True, exist_ok=True)
        _write_conversion_midi(midi)
        wav.write_bytes(b"RIFF-test")
        manifest.write_text("{}", encoding="utf-8")
        archive.write_bytes(b"PK-test")
        on_progress(
            SimpleCreateProgress(
                completed=6,
                total=6,
                phase="complete",
                message="Automatic result ready",
            )
        )
        return SimpleCreateResult(
            status="complete",
            output_dir=request.output_dir,
            result_root=root,
            zip_path=archive,
            balanced_wav_path=wav,
            combined_midi_path=midi,
            manifest_path=manifest,
            selected_count=1,
            omitted_count=1,
        )

    def cancel(self) -> None:
        self.cancel_called = True


class _CompletingListeningMasterRunner:
    def __init__(self, root: Path) -> None:
        self.request = None
        self.master_path = root / "listening-master.wav"
        self.receipt_path = root / "listening-master-receipt.json"
        self.control_path = root / "balanced-selected-midi-preview.wav"
        for path in (self.master_path, self.receipt_path, self.control_path):
            path.write_bytes(b"private-test-artifact")

    async def run(self, request, *, on_progress) -> ListeningMasterResult:
        self.request = request
        on_progress(
            ListeningMasterProgress(
                completed=1,
                total=4,
                phase="preflight",
                message="Checking SoundFile, FFmpeg, and loudnorm",
            )
        )
        on_progress(
            ListeningMasterProgress(
                completed=4,
                total=4,
                phase="complete",
                message="Comparative Listening Master verified and published",
            )
        )
        return ListeningMasterResult(
            status="complete",
            cache_hit=False,
            balanced_control_path=self.control_path,
            master_path=self.master_path,
            receipt_path=self.receipt_path,
            cache_key="a" * 64,
            selection_manifest_sha256="b" * 64,
            balanced_arrangement_manifest_sha256="c" * 64,
            listening_master_manifest_sha256="d" * 64,
            policy="ffmpeg-loudnorm-two-pass-fixed-horizon-v1",
            summary={
                "input_integrated_lufs": -21.5,
                "output_integrated_lufs": -16.0,
                "output_true_peak_dbtp": -1.0,
            },
            mastered=True,
            release_master=False,
            effects={"selection_changed": False},
            preflight_ready=("soundfile", "ffmpeg", "loudnorm"),
        )


class _BlockingListeningMasterRunner:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def run(self, request, *, on_progress) -> ListeningMasterResult:
        self.started.set()
        on_progress(
            ListeningMasterProgress(
                completed=2,
                total=4,
                phase="build",
                message="Creating the fixed-policy private listening challenger",
            )
        )
        await self.release.wait()
        root = request.snapshot.config.project
        master = root / "test-listening-master.wav"
        receipt = root / "test-listening-master.json"
        control = root / "test-balanced-control.wav"
        for path in (master, receipt, control):
            path.write_bytes(b"test")
        return ListeningMasterResult(
            status="complete",
            cache_hit=True,
            balanced_control_path=control,
            master_path=master,
            receipt_path=receipt,
            cache_key="a" * 64,
            selection_manifest_sha256="b" * 64,
            balanced_arrangement_manifest_sha256="c" * 64,
            listening_master_manifest_sha256="d" * 64,
            policy="ffmpeg-loudnorm-two-pass-fixed-horizon-v1",
            summary={
                "input_integrated_lufs": -20.0,
                "output_integrated_lufs": -16.0,
                "output_true_peak_dbtp": -1.0,
            },
            mastered=True,
            release_master=False,
            effects={"selection_changed": False},
        )


def _write_conversion_midi(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_midi_file(
        path,
        [
            MidiTrack(
                "Bass",
                0,
                38,
                [NoteEvent(0.0, 0.5, 38, 90)],
            )
        ],
        bpm=120.0,
    )
