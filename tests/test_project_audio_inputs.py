from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sunofriend.project_audio_inputs import (
    inspect_project_audio_inputs,
    prepared_project_input_problem,
)


class ProjectAudioInputTests(unittest.TestCase):
    def test_empty_folder_requests_prepared_wav_stems(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)

            problem = prepared_project_input_problem(project)

            self.assertIn("no top-level WAV stems", problem or "")

    def test_one_non_wav_asset_points_to_single_asset_import(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "song.flac").touch()

            problem = prepared_project_input_problem(project)

            self.assertIn("source-import SOURCE", problem or "")
            self.assertIn("does not separate", problem or "")
            self.assertNotIn("source-import-folder", problem or "")

    def test_mixed_formats_are_not_silently_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "song-bass.wav").touch()
            (project / "song-keys.flac").touch()
            (project / "song-vocals.m4a").touch()

            inventory = inspect_project_audio_inputs(project)
            problem = prepared_project_input_problem(project)

            self.assertEqual(len(inventory.audio_files), 3)
            self.assertEqual(len(inventory.canonical_wavs), 1)
            self.assertEqual(len(inventory.unprepared_audio), 2)
            self.assertIn("source-import-folder", problem or "")
            self.assertIn("will not silently ignore", problem or "")

    def test_lower_case_top_level_wavs_are_conversion_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "song-bass.wav").touch()
            (project / "song-keys.wav").touch()
            nested = project / "INPUT" / "original"
            nested.mkdir(parents=True)
            (nested / "song-bass.flac").touch()

            inventory = inspect_project_audio_inputs(project)

            self.assertEqual(len(inventory.audio_files), 2)
            self.assertEqual(inventory.unprepared_audio, ())
            self.assertIsNone(prepared_project_input_problem(project))


if __name__ == "__main__":
    unittest.main()
