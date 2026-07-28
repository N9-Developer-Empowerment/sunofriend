from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sunofriend.automatic_selection import AutomaticSelectionPlan
from sunofriend.simple_create import ProductionSimpleCreateRunner
from sunofriend.simple_create_contract import SimpleCreateRequest
from sunofriend.simple_result import SimpleResult
from sunofriend.tui_conversion_contract import FullConversionResult


class SimpleCreateRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_reuses_conversion_and_publishes_separate_automatic_result(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Song-B minor-113bpm-440hz"
            output = root / "fresh-output"
            project.mkdir()
            (project / "Song-bass-B minor-113bpm-440hz.wav").write_bytes(b"RIFF")
            conversion = _CompleteConversionRunner()
            runner = ProductionSimpleCreateRunner(conversion_runner=conversion)
            progress = []
            catalog = {
                "project_id": "project-simple",
                "setup": {"bpm": 113.0},
                "stems": [],
            }
            selection = AutomaticSelectionPlan(
                selected=({"stem_id": "bass"},),
                omitted=(),
                receipt={"schema": "selection"},
            )
            automatic_root = output / "AUTOMATIC-SONG"
            simple_result = _simple_result(automatic_root)

            with patch(
                "sunofriend.simple_create.load_tui_project",
                return_value=SimpleNamespace(catalog=catalog),
            ), patch(
                "sunofriend.simple_create.plan_automatic_selection",
                return_value=selection,
            ) as plan, patch(
                "sunofriend.simple_create.build_simple_result",
                return_value=simple_result,
            ) as build:
                result = await runner.run(
                    SimpleCreateRequest.create(project, output),
                    on_progress=progress.append,
                )

            self.assertTrue(result.succeeded)
            self.assertEqual(result.result_root, automatic_root)
            self.assertEqual(conversion.request.conversion_mode, "repair")
            self.assertTrue(conversion.request.evaluate_variants)
            self.assertTrue(conversion.request.include_vocals)
            plan.assert_called_once()
            self.assertEqual(
                plan.call_args.kwargs["result_root"],
                output.resolve(),
            )
            build.assert_called_once()
            self.assertEqual(
                build.call_args.kwargs["destination"],
                output.resolve() / "AUTOMATIC-SONG",
            )
            phases = {item.phase for item in progress}
            self.assertTrue(
                {
                    "preflight",
                    "convert",
                    "choose-defaults",
                    "render-midi",
                    "render-wav",
                    "package",
                    "complete",
                }.issubset(phases)
            )

    async def test_cancelled_conversion_never_plans_or_publishes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Song-C major-100bpm-440hz"
            output = root / "fresh-output"
            project.mkdir()
            (project / "Song-keys-C major-100bpm-440hz.wav").write_bytes(b"RIFF")
            conversion = _CancelledConversionRunner()
            runner = ProductionSimpleCreateRunner(conversion_runner=conversion)

            with patch(
                "sunofriend.simple_create.plan_automatic_selection"
            ) as plan:
                result = await runner.run(
                    SimpleCreateRequest.create(project, output),
                    on_progress=lambda _progress: None,
                )

            self.assertTrue(result.cancelled)
            plan.assert_not_called()
            self.assertFalse((output / "AUTOMATIC-SONG").exists())
            runner.cancel()
            self.assertTrue(conversion.cancel_called)


class _CompleteConversionRunner:
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
        request.output_dir.mkdir()
        summary = request.output_dir / "listen_all_summary.json"
        summary.write_text("{}", encoding="utf-8")
        return FullConversionResult(
            status="complete",
            output_dir=request.output_dir,
            candidate_roots=(request.output_dir,),
            converted_roles=("bass",),
            skipped_roles=(),
            failed_roles=(),
            proxy_roles=(),
            warnings=(),
            summary_paths=(summary,),
            source_stem_count=1,
            midi_ready_stem_count=1,
            candidate_count=1,
        )

    def cancel(self) -> None:
        self.cancel_called = True


class _CancelledConversionRunner:
    def __init__(self) -> None:
        self.cancel_called = False

    async def run(
        self,
        request,
        *,
        on_progress,
        cancellation_requested=None,
    ) -> FullConversionResult:
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
            source_stem_count=1,
            midi_ready_stem_count=0,
            candidate_count=0,
        )

    def cancel(self) -> None:
        self.cancel_called = True


def _simple_result(root: Path) -> SimpleResult:
    return SimpleResult(
        root=root,
        zip_path=root / "result.zip",
        combined_midi_path=root / "combined.mid",
        balanced_wav_path=root / "balanced.wav",
        manifest_path=root / "result.json",
        selected_count=1,
        omitted_count=0,
        manifest_sha256="a" * 64,
    )


if __name__ == "__main__":
    unittest.main()
