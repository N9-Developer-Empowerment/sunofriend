from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from sunofriend.cli import main
from sunofriend.clip import Provenance, read_midi_clips
from sunofriend.library import ClipLibrary
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent


class ClipCliTests(unittest.TestCase):
    def test_import_search_transform_and_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            midi = root / "bass.mid"
            library = root / "library"
            output = root / "variant.mid"
            write_midi_file(
                midi,
                [MidiTrack("Bass", 0, 38, [NoteEvent(0.0, 0.5, 38, 100)])],
                bpm=120,
            )

            imported_stdout = io.StringIO()
            with redirect_stdout(imported_stdout):
                result = main(
                    [
                        "clip-import", str(midi), "--library", str(library),
                        "--key", "D minor", "--role", "bass", "--tag", "golden",
                    ]
                )
            self.assertEqual(result, 0)
            original_id = json.loads(imported_stdout.getvalue())[0]["clip_id"]

            transformed_stdout = io.StringIO()
            with redirect_stdout(transformed_stdout):
                result = main(
                    [
                        "clip-transform", original_id, "--library", str(library),
                        "--target-key", "F major", "--target-bpm", "130",
                        "--timing-mode", "musical", "--out", str(output),
                    ]
                )
            self.assertEqual(result, 0)
            transformed = json.loads(transformed_stdout.getvalue())
            final_clip = ClipLibrary(library).get(transformed["clip_id"])

            self.assertTrue(output.is_file())
            self.assertEqual(str(final_clip.key), "F major")
            self.assertEqual(final_clip.bpm, 130.0)
            self.assertEqual(final_clip.revision, 3)  # key and BPM are auditable versions
            self.assertEqual(len(ClipLibrary(library).list()), 3)

            instrument_stdout = io.StringIO()
            with redirect_stdout(instrument_stdout):
                result = main(
                    [
                        "clip-instrument", final_clip.clip_id, "--library", str(library),
                        "--suggest", "Upright Jazz Bass", "--suggest", "Sub Bass",
                    ]
                )
            self.assertEqual(result, 0)
            instrument_id = json.loads(instrument_stdout.getvalue())["clip_id"]
            profiled = ClipLibrary(library).get(instrument_id)
            self.assertEqual(profiled.instrument.suggestions[0], "Upright Jazz Bass")
            self.assertEqual(profiled.revision, 4)
            self.assertEqual(profiled.transform_recipe.parameters_dict["program"], 38)
            self.assertEqual(profiled.transform_recipe.parameters_dict["channel"], 0)

            listed_stdout = io.StringIO()
            with redirect_stdout(listed_stdout):
                result = main(
                    [
                        "clip-list", "--library", str(library), "--role", "bass",
                        "--key", "F major",
                    ]
                )
            self.assertEqual(result, 0)
            self.assertIn(
                json.loads(listed_stdout.getvalue())[0]["clip_id"],
                {final_clip.clip_id, profiled.clip_id},
            )

    def test_export_reports_stem_locked_garageband_tempo_and_musical_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            midi = root / "source.mid"
            library_path = root / "library"
            write_midi_file(
                midi,
                [MidiTrack("Bass", 0, 38, [NoteEvent(0.175, 0.675, 38, 100)])],
                bpm=130.016,
            )
            imported = read_midi_clips(midi, key="D minor", role="bass")[0]
            clip = replace(
                imported,
                provenance=Provenance(
                    source_uri=str(midi),
                    converter="test",
                    details={"timing_mode": "stem_locked", "garageband_bpm": 130.0},
                ),
            ).with_content_id()
            ClipLibrary(library_path).add(clip)

            stem_output = root / "stem.mid"
            stem_stdout = io.StringIO()
            with redirect_stdout(stem_stdout):
                result = main(
                    [
                        "clip-export", clip.clip_id, "--library", str(library_path),
                        "--out", str(stem_output),
                    ]
                )
            self.assertEqual(result, 0)
            self.assertIn("timing mode: stem_locked", stem_stdout.getvalue())
            self.assertIn("set GarageBand tempo to: 130", stem_stdout.getvalue())

            musical_output = root / "musical.mid"
            musical_stdout = io.StringIO()
            with redirect_stdout(musical_stdout):
                result = main(
                    [
                        "clip-export", clip.clip_id, "--library", str(library_path),
                        "--out", str(musical_output), "--timing-mode", "musical",
                    ]
                )
            self.assertEqual(result, 0)
            self.assertIn("timing mode: musical", musical_stdout.getvalue())
            self.assertIn("musical tempo starts at:", musical_stdout.getvalue())
            self.assertNotIn("set GarageBand tempo to:", musical_stdout.getvalue())

    def test_import_rejects_midi_without_notes_before_creating_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            midi = root / "empty.mid"
            library = root / "library"
            write_midi_file(midi, [MidiTrack("Empty", 0, 0, [])], bpm=120)

            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                main(["clip-import", str(midi), "--library", str(library)])

            self.assertEqual(raised.exception.code, 2)
            self.assertFalse(library.exists())

    def test_invalid_later_bpm_does_not_persist_key_transform(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            library, original_id = self._import_bass(root)

            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                main(
                    [
                        "clip-transform", original_id, "--library", str(library),
                        "--target-key", "F major", "--target-bpm", "0",
                    ]
                )

            self.assertEqual(raised.exception.code, 2)
            catalog = ClipLibrary(library)
            self.assertEqual([item.clip_id for item in catalog.list()], [original_id])
            self.assertEqual([item.clip_id for item in catalog.versions(original_id)], [original_id])

    def test_output_write_failure_does_not_persist_transform_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            library, original_id = self._import_bass(root)
            output = root / "variant.mid"

            with (
                patch("sunofriend.clip.write_clip_midi", side_effect=OSError("disk full")),
                redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as raised,
            ):
                main(
                    [
                        "clip-transform", original_id, "--library", str(library),
                        "--target-key", "F major", "--target-bpm", "130",
                        "--out", str(output),
                    ]
                )

            self.assertEqual(raised.exception.code, 2)
            self.assertFalse(output.exists())
            catalog = ClipLibrary(library)
            self.assertEqual([item.clip_id for item in catalog.list()], [original_id])
            self.assertEqual([item.clip_id for item in catalog.versions(original_id)], [original_id])

    @staticmethod
    def _import_bass(root: Path) -> tuple[Path, str]:
        midi = root / "bass.mid"
        library = root / "library"
        write_midi_file(
            midi,
            [MidiTrack("Bass", 0, 38, [NoteEvent(0.0, 0.5, 38, 100)])],
            bpm=120,
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = main(
                [
                    "clip-import", str(midi), "--library", str(library),
                    "--key", "D minor", "--role", "bass",
                ]
            )
        if result != 0:
            raise AssertionError(f"clip-import returned {result}")
        return library, json.loads(stdout.getvalue())[0]["clip_id"]


if __name__ == "__main__":
    unittest.main()
