from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sunofriend.render import RenderError, render_midi_to_wav


class RenderMidiToWavTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary_directory.name)
        self.midi = self.root / "input.mid"
        self.midi.write_bytes(b"MThd")
        self.soundfont = self.root / "test.sf2"
        self.soundfont.write_bytes(b"soundfont")
        self.renderer = self.root / "pinned-fluidsynth"
        self.renderer.write_text("#!/bin/sh\n", encoding="utf-8")
        self.renderer.chmod(0o755)

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    @staticmethod
    def _successful_render(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        output = Path(command[command.index("-F") + 1])
        output.write_bytes(b"WAV" + (b"\0" * 2048))
        return subprocess.CompletedProcess(command, returncode=0, stdout="", stderr="")

    def test_explicit_fluidsynth_path_is_used_without_lookup(self) -> None:
        output = self.root / "explicit.wav"

        with (
            patch(
                "sunofriend.render.find_fluidsynth",
                side_effect=AssertionError("lookup must not be called"),
            ) as lookup,
            patch(
                "sunofriend.render.subprocess.run",
                side_effect=self._successful_render,
            ) as run,
        ):
            rendered = render_midi_to_wav(
                self.midi,
                output,
                soundfont_path=self.soundfont,
                fluidsynth_path=self.renderer,
            )

        self.assertEqual(rendered, output)
        lookup.assert_not_called()
        command = run.call_args.args[0]
        self.assertEqual(command[0], str(self.renderer))
        self.assertGreater(output.stat().st_size, 1024)

    def test_default_fluidsynth_path_uses_lookup(self) -> None:
        output = self.root / "default.wav"

        with (
            patch(
                "sunofriend.render.find_fluidsynth",
                return_value=str(self.renderer),
            ) as lookup,
            patch(
                "sunofriend.render.subprocess.run",
                side_effect=self._successful_render,
            ) as run,
        ):
            rendered = render_midi_to_wav(
                self.midi,
                output,
                soundfont_path=self.soundfont,
            )

        self.assertEqual(rendered, output)
        lookup.assert_called_once_with()
        self.assertEqual(run.call_args.args[0][0], str(self.renderer))
        self.assertGreater(output.stat().st_size, 1024)

    def test_invalid_explicit_fluidsynth_path_fails_before_rendering(self) -> None:
        missing_renderer = self.root / "missing-fluidsynth"

        with (
            patch("sunofriend.render.find_fluidsynth") as lookup,
            patch("sunofriend.render.subprocess.run") as run,
        ):
            with self.assertRaisesRegex(
                RenderError,
                "FluidSynth executable not found or not executable",
            ):
                render_midi_to_wav(
                    self.midi,
                    self.root / "invalid.wav",
                    soundfont_path=self.soundfont,
                    fluidsynth_path=missing_renderer,
                )

        lookup.assert_not_called()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
