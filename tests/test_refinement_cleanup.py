from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sunofriend.loop import refine_stem
from sunofriend.models import NoteEvent


class RefinementCleanupTests(unittest.TestCase):
    def test_failed_render_removes_iteration_workdir(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workdir = root / "iterations"
            workdir.mkdir()
            with patch(
                "sunofriend.loop.tempfile.mkdtemp", return_value=str(workdir)
            ), patch(
                "sunofriend.transcribe_drums.transcribe_drum_stem",
                return_value=[NoteEvent(0.0, 0.1, 36, 100)],
            ), patch(
                "sunofriend.loop.compare.extract_onsets", return_value=[]
            ), patch(
                "sunofriend.loop.render_midi_to_wav",
                side_effect=RuntimeError("render failed"),
            ):
                with self.assertRaisesRegex(RuntimeError, "render failed"):
                    refine_stem(
                        root / "kick.wav",
                        kind="kick",
                        bpm=120.0,
                        out_dir=root / "output",
                    )

            self.assertFalse(workdir.exists())


if __name__ == "__main__":
    unittest.main()
