from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from sunofriend.cli import build_parser, main


class SourceImportCliTests(unittest.TestCase):
    def test_parser_exposes_explicit_tools_context_and_read_only_plan(self) -> None:
        args = build_parser().parse_args(
            [
                "source-import",
                "bass.flac",
                "--out-dir",
                "fresh-import",
                "--role",
                "bass",
                "--instrument-label",
                "buzzing synth bass",
                "--key",
                "B minor",
                "--bpm",
                "113",
                "--tuning-hz",
                "440",
                "--rights-category",
                "owned",
                "--plan",
            ]
        )

        self.assertEqual(args.source, "bass.flac")
        self.assertEqual(args.out_dir, "fresh-import")
        self.assertEqual(args.role, "bass")
        self.assertEqual(args.instrument_label, "buzzing synth bass")
        self.assertEqual(args.key, "B minor")
        self.assertEqual(args.bpm, 113.0)
        self.assertEqual(args.tuning_hz, 440.0)
        self.assertEqual(args.rights_category, "owned")
        self.assertTrue(args.plan)

    @patch("sunofriend.audio_formats.decoder_capability_report")
    def test_source_doctor_prints_read_only_capability(
        self, capability_report: Mock
    ) -> None:
        capability_report.return_value = {
            "schema": "sunofriend.audio-decoder-capability.v1",
            "read_only": True,
            "network_used": False,
            "policy": {"pcm24_encoder_available": True},
        }
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            result = main(
                [
                    "source-doctor",
                    "--ffmpeg",
                    "/tools/ffmpeg",
                    "--ffprobe",
                    "/tools/ffprobe",
                ]
            )

        self.assertEqual(result, 0)
        document = json.loads(stdout.getvalue())
        self.assertTrue(document["requirement_ready"])
        self.assertTrue(document["read_only"])
        self.assertFalse(document["network_used"])
        capability_report.assert_called_once_with(
            ffmpeg="/tools/ffmpeg",
            ffprobe="/tools/ffprobe",
            timeout_seconds=30.0,
        )

    @patch("sunofriend.source_import.plan_source_import")
    def test_source_import_plan_does_not_execute(
        self, plan_source_import: Mock
    ) -> None:
        plan = Mock()
        plan.to_dict.return_value = {
            "schema": "sunofriend.source-import-plan.v1",
            "read_only": True,
            "network_used": False,
        }
        plan_source_import.return_value = plan
        stdout = io.StringIO()

        with (
            patch("sunofriend.source_import.execute_source_import") as execute,
            redirect_stdout(stdout),
        ):
            result = main(
                [
                    "source-import",
                    "bass.flac",
                    "--out-dir",
                    "fresh-import",
                    "--role",
                    "bass",
                    "--rights-category",
                    "licensed",
                    "--plan",
                ]
            )

        self.assertEqual(result, 0)
        self.assertTrue(json.loads(stdout.getvalue())["read_only"])
        execute.assert_not_called()
        plan_source_import.assert_called_once()
        call = plan_source_import.call_args
        self.assertEqual(call.args, ("bass.flac", "fresh-import"))
        self.assertEqual(call.kwargs["role"], "bass")
        self.assertEqual(call.kwargs["rights_category"], "licensed")


if __name__ == "__main__":
    unittest.main()
