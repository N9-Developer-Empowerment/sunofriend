from __future__ import annotations

import asyncio
import hashlib
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

from sunofriend.tui_conversion import (
    FullConversionRequest,
    FullConversionValidationError,
    ProductionFullConversionRunner,
    _CommandOutcome,
    _ReloadEvidence,
    plan_full_conversion,
)


class _ScriptedRunner(ProductionFullConversionRunner):
    def __init__(
        self,
        *,
        preflight: dict | None = None,
        reload_candidate_count: int = 12,
        reload_roles: tuple[str, ...] = (
            "kick",
            "bass",
            "wind",
            "rhythm",
            "other",
            "backing_vocals",
            "vocals",
        ),
    ) -> None:
        super().__init__()
        self.commands: list[tuple[str, ...]] = []
        self.preflight_calls = 0
        self.preflight = preflight or {
            "transcribe_ready": True,
            "convert_ready": True,
        }
        self.reload_calls = 0
        self.reload_candidate_count = reload_candidate_count
        self.reload_roles = reload_roles

    async def _run_preflight(self):
        self.preflight_calls += 1
        return dict(self.preflight)

    async def _execute_command(
        self,
        command,
        *,
        on_line,
        cancellation_requested,
    ):
        command = tuple(command)
        self.commands.append(command)
        if "listen-all" in command:
            output = Path(command[command.index("--out-dir") + 1])
            mode = command[command.index("--conversion-mode") + 1]
            summary = output / f"mode_{mode}" / "listen_all_summary.json"
            summary.parent.mkdir(parents=True, exist_ok=True)
            roles = ("kick", "bass", "wind", "rhythm", "other")
            parts = {}
            for role in roles:
                midi = summary.parent / f"{role}_listened.mid"
                midi.write_bytes(b"MThd-scripted")
                parts[role] = {
                    "status": "ok",
                    "midi": str(midi),
                    "notes": 2,
                }
                on_line(f"{role}: ok score=0.5 notes=2")
            summary.write_text(
                json.dumps(
                    {
                        "status": "complete",
                        "parts": parts,
                        "successful_parts": len(parts),
                    }
                ),
                encoding="utf-8",
            )
            return _CommandOutcome(0, ())

        self.assert_vocal_command(command)
        output = Path(command[command.index("--out-dir") + 1])
        output.mkdir(parents=True, exist_ok=True)
        role = command[command.index("--role") + 1]
        token = "lead_vocal" if role == "lead" else "backing_vocal"
        midi = output / f"{token}_melody.mid"
        midi.write_bytes(b"MThd-scripted-vocal")
        (output / "vocal_summary.json").write_text(
            json.dumps(
                {
                    "primary_midi": str(midi),
                    "variants": {},
                }
            ),
            encoding="utf-8",
        )
        return _CommandOutcome(0, ())

    @staticmethod
    def assert_vocal_command(command: tuple[str, ...]) -> None:
        if "vocal-melody" not in command:
            raise AssertionError(f"unexpected command: {command!r}")

    async def _reload_candidates(self, request, plan):
        self.reload_calls += 1
        return _ReloadEvidence(
            source_stem_count=plan.source_stem_count,
            midi_ready_stem_count=plan.total,
            candidate_count=self.reload_candidate_count,
            midi_ready_roles=self.reload_roles,
        )


class _SilentRunner(ProductionFullConversionRunner):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()

    async def _run_preflight(self):
        return {"transcribe_ready": True, "convert_ready": True}

    async def _execute_command(
        self,
        command,
        *,
        on_line,
        cancellation_requested,
    ):
        self.started.set()
        while not self._cancel_event.is_set():
            await asyncio.sleep(0.01)
        return _CommandOutcome(-15, ())

    async def _reload_candidates(self, request, plan):
        raise AssertionError("cancelled jobs must not reload candidates")


class FullConversionPlanTests(unittest.TestCase):
    def test_pupsies_style_sixteen_stems_all_receive_a_planned_route(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Pupsies-B major-119bpm-440hz"
            project.mkdir()
            roles = (
                "backing_vocals",
                "bass",
                "cymbals",
                "hat",
                "keys",
                "kick",
                "lead",
                "other",
                "other_kit",
                "piano",
                "rhythm",
                "snare",
                "strings",
                "toms",
                "vocals",
                "wind",
            )
            for role in roles:
                (project / f"Pupsies-{role}-B major-119bpm-440hz.wav").touch()
            (project / "Pupsies-metronome-B major-119bpm-440hz.wav").touch()

            plan = plan_full_conversion(
                FullConversionRequest.create(project, root / "fresh-output")
            )

            self.assertEqual(plan.source_stem_count, 16)
            self.assertEqual(plan.total, 16)
            self.assertEqual(plan.unsupported_roles, ())
            self.assertEqual(
                set(plan.instrumental_roles),
                set(roles) - {"vocals", "backing_vocals"},
            )
            self.assertEqual(
                {job.source_role for job in plan.vocal_jobs},
                {"vocals", "backing_vocals"},
            )

    def test_plan_inherits_standard_proxy_roles_and_separate_vocals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = _project_fixture(root, include_unknown=True)
            request = FullConversionRequest.create(project, root / "fresh-output")
            plan = plan_full_conversion(request)

            self.assertEqual(
                plan.instrumental_roles,
                ("kick", "bass", "wind", "rhythm", "other"),
            )
            self.assertEqual(plan.proxy_roles, ("wind", "rhythm", "other"))
            self.assertEqual(
                [(job.source_role, job.cli_role) for job in plan.vocal_jobs],
                [("backing_vocals", "backing"), ("vocals", "lead")],
            )
            self.assertEqual(plan.unsupported_roles, ("unclassified",))
            self.assertEqual(plan.total, 7)
            self.assertEqual(plan.source_stem_count, 8)

    def test_output_inside_project_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = _project_fixture(root)
            request = FullConversionRequest.create(
                project,
                project / "generated-midi",
            )
            with self.assertRaisesRegex(
                FullConversionValidationError,
                "outside the source",
            ):
                plan_full_conversion(request)


class FullConversionRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_runs_full_instrumental_then_vocals_and_reloads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = _project_fixture(root)
            output = root / "new complete MIDI"
            source_hashes = _source_hashes(project)
            request = FullConversionRequest.create(project, output)
            runner = _ScriptedRunner()
            progress = []

            result = await runner.run(
                request,
                on_progress=progress.append,
            )

            self.assertEqual(result.status, "complete")
            self.assertEqual(
                result.converted_roles,
                (
                    "kick",
                    "bass",
                    "wind",
                    "rhythm",
                    "other",
                    "backing_vocals",
                    "vocals",
                ),
            )
            self.assertEqual(result.proxy_roles, ("wind", "rhythm", "other"))
            self.assertEqual(result.skipped_roles, ())
            self.assertEqual(result.failed_roles, ())
            self.assertEqual(result.candidate_roots, (output.resolve(),))
            self.assertEqual(result.candidate_count, 12)
            self.assertEqual(runner.preflight_calls, 1)
            self.assertEqual(runner.reload_calls, 1)
            self.assertEqual(len(runner.commands), 3)

            listen = runner.commands[0]
            self.assertEqual(listen[:4], (sys.executable, "-u", "-m", "sunofriend"))
            self.assertIn("listen-all", listen)
            self.assertNotIn("--parts", listen)
            self.assertIn("--evaluate-variants", listen)
            self.assertIn("--conversion-mode", listen)
            self.assertEqual(
                [
                    command[command.index("--role") + 1]
                    for command in runner.commands[1:]
                ],
                ["backing", "lead"],
            )
            self.assertEqual(_source_hashes(project), source_hashes)
            self.assertTrue(output.is_dir())
            if os.name == "posix":
                self.assertEqual(
                    stat.S_IMODE(output.stat().st_mode),
                    0o700,
                )
            self.assertEqual(progress[-1].phase, "complete")
            self.assertEqual(progress[-1].completed, progress[-1].total)
            self.assertTrue(
                all(
                    "review-required" in warning
                    for warning in result.warnings
                )
            )

    async def test_unknown_role_is_reported_as_partial_not_silently_lost(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = _project_fixture(root, include_unknown=True)
            runner = _ScriptedRunner()

            result = await runner.run(
                FullConversionRequest.create(project, root / "fresh-output"),
                on_progress=lambda _progress: None,
            )

            self.assertEqual(result.status, "partial")
            self.assertIn("unclassified", result.skipped_roles)
            self.assertTrue(
                any(
                    "no guided conversion engine" in warning
                    for warning in result.warnings
                )
            )

    async def test_incomplete_workbench_role_reload_cannot_report_complete(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = _project_fixture(root)
            runner = _ScriptedRunner(reload_roles=("kick",))

            result = await runner.run(
                FullConversionRequest.create(project, root / "fresh-output"),
                on_progress=lambda _progress: None,
            )

            self.assertEqual(result.status, "partial")
            self.assertTrue(
                any(
                    "no MIDI candidate for converted role" in warning
                    and "vocals" in warning
                    for warning in result.warnings
                )
            )

    async def test_zero_candidate_reload_does_not_publish_candidate_root(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = _project_fixture(root)
            runner = _ScriptedRunner(
                reload_candidate_count=0,
                reload_roles=(),
            )

            result = await runner.run(
                FullConversionRequest.create(project, root / "fresh-output"),
                on_progress=lambda _progress: None,
            )

            self.assertEqual(result.status, "partial")
            self.assertEqual(result.candidate_roots, ())
            self.assertTrue(
                any(
                    "Workbench found no MIDI candidates" in warning
                    for warning in result.warnings
                )
            )

    async def test_existing_output_fails_before_preflight_or_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = _project_fixture(root)
            output = root / "existing"
            output.mkdir()
            sentinel = output / "keep.txt"
            sentinel.write_text("unchanged", encoding="utf-8")
            runner = _ScriptedRunner()

            with self.assertRaisesRegex(
                FullConversionValidationError,
                "already exists",
            ):
                await runner.run(
                    FullConversionRequest.create(project, output),
                    on_progress=lambda _progress: None,
                )

            self.assertEqual(runner.preflight_calls, 0)
            self.assertEqual(runner.commands, [])
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "unchanged")

    async def test_failed_preflight_creates_no_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = _project_fixture(root)
            output = root / "fresh-output"
            runner = _ScriptedRunner(
                preflight={
                    "transcribe_ready": False,
                    "convert_ready": False,
                    "missing_transcribe_packages": ["basic-pitch"],
                }
            )

            with self.assertRaisesRegex(
                FullConversionValidationError,
                "doctor --require transcribe",
            ):
                await runner.run(
                    FullConversionRequest.create(project, output),
                    on_progress=lambda _progress: None,
                )

            self.assertFalse(output.exists())
            self.assertEqual(runner.commands, [])

    async def test_cancel_preserves_partial_root_and_does_not_reload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = _project_fixture(root)
            output = root / "cancelled-output"
            runner = _SilentRunner()
            task = asyncio.create_task(
                runner.run(
                    FullConversionRequest.create(project, output),
                    on_progress=lambda _progress: None,
                )
            )
            await asyncio.wait_for(runner.started.wait(), timeout=2.0)
            runner.cancel()

            result = await asyncio.wait_for(task, timeout=2.0)

            self.assertEqual(result.status, "cancelled")
            self.assertEqual(result.candidate_roots, ())
            self.assertTrue(output.is_dir())
            self.assertTrue(
                any("preserved" in warning for warning in result.warnings)
            )

    async def test_real_silent_child_is_cancelled_without_waiting_for_output(self) -> None:
        if os.name != "posix":
            self.skipTest("process-group cancellation assertion is POSIX-only")
        runner = ProductionFullConversionRunner()
        command = (
            sys.executable,
            "-u",
            "-c",
            "import time; time.sleep(30)",
        )
        task = asyncio.create_task(
            runner._execute_command(
                command,
                on_line=lambda _line: None,
                cancellation_requested=None,
            )
        )
        for _ in range(100):
            if runner._process is not None:
                break
            await asyncio.sleep(0.01)
        runner.cancel()

        outcome = await asyncio.wait_for(task, timeout=5.0)

        self.assertNotEqual(outcome.return_code, 0)

    async def test_cancelling_execute_task_reaps_its_child_process(self) -> None:
        if os.name != "posix":
            self.skipTest("process-group cancellation assertion is POSIX-only")
        runner = ProductionFullConversionRunner()
        task = asyncio.create_task(
            runner._execute_command(
                (
                    sys.executable,
                    "-u",
                    "-c",
                    "import time; time.sleep(30)",
                ),
                on_line=lambda _line: None,
                cancellation_requested=None,
            )
        )
        for _ in range(100):
            if runner._process is not None:
                break
            await asyncio.sleep(0.01)
        process = runner._process
        self.assertIsNotNone(process)

        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5.0)

        self.assertIsNotNone(process.returncode)
        self.assertIsNone(runner._process)

    async def test_child_warning_is_bounded_and_redacted(self) -> None:
        runner = ProductionFullConversionRunner()
        secret = "warning: /private/song.wav?token=super-secret " + ("x" * 800)
        outcome = await runner._execute_command(
            (
                sys.executable,
                "-u",
                "-c",
                f"print({secret!r})",
            ),
            on_line=lambda _line: None,
            cancellation_requested=None,
        )

        self.assertEqual(outcome.return_code, 0)
        self.assertEqual(len(outcome.warning_lines), 1)
        warning = outcome.warning_lines[0]
        self.assertNotIn("/private", warning)
        self.assertNotIn("super-secret", warning)
        self.assertLessEqual(len(warning), 240)

    async def test_reload_counts_only_candidates_from_the_fresh_output(self) -> None:
        from sunofriend.midi import MidiTrack, write_midi_file
        from sunofriend.models import NoteEvent

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Reload-B major-119bpm-440hz"
            project.mkdir()
            (project / "Reload-bass-B major-119bpm-440hz.wav").write_bytes(
                b"source"
            )
            write_midi_file(
                project / "Reload-bass-old-B major-119bpm-440hz.mid",
                [
                    MidiTrack(
                        "Bass",
                        0,
                        38,
                        [NoteEvent(0.0, 0.5, 35, 80)],
                    )
                ],
                bpm=119,
            )
            output = root / "fresh-output"
            request = FullConversionRequest.create(project, output)
            plan = plan_full_conversion(request)
            output.mkdir()
            fresh = output / "mode_repair" / "bass_listened.mid"
            fresh.parent.mkdir()
            write_midi_file(
                fresh,
                [
                    MidiTrack(
                        "Bass",
                        0,
                        38,
                        [NoteEvent(0.0, 0.5, 40, 80)],
                    )
                ],
                bpm=119,
            )

            evidence = await ProductionFullConversionRunner()._reload_candidates(
                request,
                plan,
            )

            self.assertEqual(evidence.source_stem_count, 1)
            self.assertEqual(evidence.midi_ready_stem_count, 1)
            self.assertEqual(evidence.candidate_count, 1)


def _project_fixture(root: Path, *, include_unknown: bool = False) -> Path:
    project = root / "TUI Conversion-B major-119bpm-440hz"
    project.mkdir()
    roles = (
        "kick",
        "bass",
        "wind",
        "rhythm",
        "other",
        "backing_vocals",
        "vocals",
        "metronome",
    )
    for role in roles:
        (project / f"TUI Conversion-{role}-B major-119bpm-440hz.wav").write_bytes(
            f"source-{role}".encode("utf-8")
        )
    if include_unknown:
        (project / "TUI Conversion-texture-B major-119bpm-440hz.wav").write_bytes(
            b"source-texture"
        )
    return project


def _source_hashes(project: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(project.glob("*.wav"))
    }


if __name__ == "__main__":
    unittest.main()
