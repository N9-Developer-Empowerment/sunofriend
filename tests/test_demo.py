from __future__ import annotations

import asyncio
import hashlib
import io
import json
import tempfile
import unittest
import wave
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sunofriend.cli import build_parser, main
from sunofriend.demo import (
    DEMO_BPM,
    DEMO_DURATION_SECONDS,
    DEMO_KEY,
    DEMO_PROJECT_SCHEMA,
    DEMO_SAMPLE_RATE,
    DemoError,
    create_demo,
    create_demo_project,
    demo_project_path,
)
from sunofriend.simple_create_contract import SimpleCreateResult
from sunofriend.tui_conversion import plan_full_conversion
from sunofriend.tui_conversion_contract import FullConversionRequest


class DemoProjectTests(unittest.TestCase):
    def test_builds_deterministic_copyright_safe_stems(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_output = root / "first-result"
            second_output = root / "second-result"

            first = create_demo_project(first_output)
            second = create_demo_project(second_output)

            self.assertFalse(first_output.exists())
            self.assertFalse(second_output.exists())
            self.assertEqual(len(first.stems), 6)
            self.assertEqual(
                [_sha256(path) for path in first.stems],
                [_sha256(path) for path in second.stems],
            )
            self.assertEqual(
                first.manifest_path.read_bytes(),
                second.manifest_path.read_bytes(),
            )
            manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], DEMO_PROJECT_SCHEMA)
            self.assertEqual(manifest["project"]["bpm"], DEMO_BPM)
            self.assertEqual(manifest["project"]["key"], DEMO_KEY)
            self.assertFalse(
                manifest["copyright_safety"]["third_party_recordings"]
            )
            self.assertFalse(manifest["copyright_safety"]["third_party_samples"])
            for stem in first.stems:
                with wave.open(str(stem), "rb") as handle:
                    self.assertEqual(handle.getnchannels(), 1)
                    self.assertEqual(handle.getsampwidth(), 2)
                    self.assertEqual(handle.getframerate(), DEMO_SAMPLE_RATE)
                    self.assertEqual(
                        handle.getnframes(),
                        int(DEMO_SAMPLE_RATE * DEMO_DURATION_SECONDS),
                    )
                self.assertGreater(stem.stat().st_size, 44)

    def test_generated_project_is_discovered_by_normal_conversion_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "result"
            project = create_demo_project(output)

            plan = plan_full_conversion(
                FullConversionRequest.create(project.root, output)
            )

            self.assertEqual(plan.project, project.root)
            self.assertEqual(
                set(plan.instrumental_roles),
                {"kick", "snare", "hat", "bass", "keys", "lead"},
            )
            self.assertEqual(plan.vocal_jobs, ())
            self.assertEqual(plan.unsupported_roles, ())
            self.assertEqual(plan.source_stem_count, 6)

    def test_never_overwrites_result_or_matching_source_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            existing_output = root / "existing-result"
            existing_output.mkdir()
            with self.assertRaisesRegex(DemoError, "output already exists"):
                create_demo_project(existing_output)

            output = root / "fresh-result"
            demo_project_path(output).mkdir()
            with self.assertRaisesRegex(DemoError, "source folder already exists"):
                create_demo_project(output)
            self.assertFalse(output.exists())

    def test_rejects_an_existing_symlink_without_following_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "missing-target"
            output = root / "existing-link"
            output.symlink_to(target)

            with self.assertRaisesRegex(DemoError, "output already exists"):
                create_demo_project(output)

            self.assertTrue(output.is_symlink())
            self.assertFalse(target.exists())


class DemoWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_runs_the_production_simple_contract_and_reports_outputs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "automatic-result"
            state = root / "state"
            soundfont = root / "soundfont.sf2"
            runner = _FakeSimpleRunner()
            progress = []

            result = await create_demo(
                output,
                state_dir=state,
                soundfont_path=soundfont,
                simple_runner=runner,
                on_progress=progress.append,
            )

            self.assertTrue(result.succeeded)
            self.assertEqual(runner.request.project, demo_project_path(output))
            self.assertEqual(runner.request.output_dir, output.resolve())
            self.assertEqual(runner.request.state_dir, state.resolve())
            self.assertEqual(runner.request.soundfont_path, soundfont.resolve())
            self.assertEqual(progress[0].phase, "generate-demo")
            self.assertEqual(progress[-1].phase, "complete")
            self.assertTrue(all(item.total == 7 for item in progress))
            summary = result.as_dict()
            self.assertEqual(summary["workflow"]["mode"], "simple")
            self.assertTrue(summary["workflow"]["automatic"])
            self.assertEqual(
                summary["workflow"]["review_status"],
                "not_reviewed",
            )
            self.assertFalse(summary["workflow"]["source_audio_mixed_into_wav"])
            self.assertEqual(
                summary["outputs"]["listen_first"],
                str(
                    (
                        output
                        / "AUTOMATIC-SONG"
                        / "AUDIO"
                        / "balanced.wav"
                    ).resolve()
                ),
            )
            self.assertEqual(summary["selected_midi_parts"], 6)


class DemoCliTests(unittest.TestCase):
    def test_parser_requires_one_fresh_output_and_accepts_render_options(
        self,
    ) -> None:
        args = build_parser().parse_args(
            [
                "demo",
                "--out-dir",
                "/music/my-demo",
                "--state-dir",
                "/music/state",
                "--soundfont",
                "/music/neutral.sf2",
            ]
        )

        self.assertEqual(args.command, "demo")
        self.assertEqual(args.out_dir, "/music/my-demo")
        self.assertEqual(args.state_dir, "/music/state")
        self.assertEqual(args.soundfont, "/music/neutral.sf2")

    @patch("sunofriend.cli._run_demo", return_value=0)
    def test_cli_dispatches_to_demo(self, run_demo) -> None:
        result = main(["demo", "--out-dir", "/music/my-demo"])

        self.assertEqual(result, 0)
        run_demo.assert_called_once()
        self.assertEqual(run_demo.call_args.args[0].out_dir, "/music/my-demo")

    def test_create_parser_exposes_the_same_automatic_workflow(self) -> None:
        args = build_parser().parse_args(
            [
                "create",
                "/music/my-stems",
                "--out-dir",
                "/music/my-result",
                "--state-dir",
                "/music/state",
                "--soundfont",
                "/music/neutral.sf2",
            ]
        )

        self.assertEqual(args.command, "create")
        self.assertEqual(args.project, "/music/my-stems")
        self.assertEqual(args.out_dir, "/music/my-result")
        self.assertEqual(args.state_dir, "/music/state")
        self.assertEqual(args.soundfont, "/music/neutral.sf2")

    @patch("sunofriend.cli._run_create", return_value=0)
    def test_cli_dispatches_to_create(self, run_create) -> None:
        result = main(
            [
                "create",
                "/music/my-stems",
                "--out-dir",
                "/music/my-result",
            ]
        )

        self.assertEqual(result, 0)
        run_create.assert_called_once()
        self.assertEqual(
            run_create.call_args.args[0].project,
            "/music/my-stems",
        )

    def test_create_runs_the_production_runner_and_prints_result_contract(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Song-C major-120bpm-440hz"
            output = root / "fresh-result"
            project.mkdir()
            (project / "Song-bass-C major-120bpm-440hz.wav").write_bytes(
                b"RIFF"
            )
            runner = _FakeSimpleRunner()
            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch(
                "sunofriend.simple_create.create_simple_create_runner",
                return_value=runner,
            ), redirect_stdout(stdout), redirect_stderr(stderr):
                result = main(
                    [
                        "create",
                        str(project),
                        "--out-dir",
                        str(output),
                    ]
                )

            self.assertEqual(result, 0)
            self.assertEqual(runner.request.project, project.resolve())
            self.assertEqual(runner.request.output_dir, output.resolve())
            self.assertIn("[6/6] complete:", stderr.getvalue())
            document = json.loads(stdout.getvalue())
            self.assertEqual(
                document["schema"],
                "sunofriend.simple-create-cli-result.v1",
            )
            self.assertEqual(document["source_project"], str(project.resolve()))
            self.assertEqual(document["workflow"]["review_status"], "not_reviewed")
            self.assertFalse(document["workflow"]["source_audio_mixed_into_wav"])

    def test_demo_rejects_an_empty_required_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "fresh-result"
            runner = _FakeSimpleRunner(empty_artifact="balanced")

            with self.assertRaisesRegex(DemoError, "listening WAV"):
                asyncio.run(create_demo(output, simple_runner=runner))


class _FakeSimpleRunner:
    def __init__(self, *, empty_artifact: str | None = None) -> None:
        self.request = None
        self.empty_artifact = empty_artifact

    async def run(
        self,
        request,
        *,
        on_progress,
        cancellation_requested=None,
    ) -> SimpleCreateResult:
        self.request = request
        self.assert_fresh(request.output_dir)
        result_root = request.output_dir / "AUTOMATIC-SONG"
        midi_root = result_root / "MIDI"
        audio_root = result_root / "AUDIO"
        midi_root.mkdir(parents=True)
        audio_root.mkdir()
        combined = midi_root / "combined.mid"
        balanced = audio_root / "balanced.wav"
        archive = result_root / "starter.zip"
        manifest = result_root / "result.json"
        combined.write_bytes(b"MThd")
        balanced.write_bytes(b"" if self.empty_artifact == "balanced" else b"RIFF")
        archive.write_bytes(b"PK")
        manifest.write_text("{}", encoding="utf-8")
        on_progress(
            type(
                "Progress",
                (),
                {
                    "completed": 6,
                    "total": 6,
                    "phase": "complete",
                    "message": "Automatic MIDI and balanced WAV are ready",
                },
            )()
        )
        return SimpleCreateResult(
            status="complete",
            output_dir=request.output_dir,
            result_root=result_root,
            zip_path=archive,
            balanced_wav_path=balanced,
            combined_midi_path=combined,
            manifest_path=manifest,
            selected_count=6,
            omitted_count=0,
        )

    def cancel(self) -> None:
        return None

    @staticmethod
    def assert_fresh(output: Path) -> None:
        if output.exists():
            raise AssertionError("the production request did not receive a fresh root")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
