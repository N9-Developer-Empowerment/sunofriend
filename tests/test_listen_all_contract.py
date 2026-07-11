from __future__ import annotations

import tempfile
import unittest
import wave
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from sunofriend.beatgrid import Grid
from sunofriend.cli import main
from sunofriend.listen_all import CHANNELS, _is_silent, run_listen_all
from sunofriend.listen_all import _make_library_clip
from sunofriend.clip import KeySignature
from sunofriend.library import ClipLibrary
from sunofriend.loop import RefineResult
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent


class ListenAllContractTests(unittest.TestCase):
    def test_keys_and_pads_use_distinct_preview_channels_and_programs(self):
        self.assertEqual(CHANNELS["keys"], (1, 7))
        self.assertEqual(CHANNELS["pads"], (6, 89))

    def test_borderline_peak_with_negligible_rms_is_treated_as_bleed(self):
        try:
            import numpy  # noqa: F401
            import soundfile  # noqa: F401
        except ImportError as exc:
            self.skipTest(f"optional audio dependencies are unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bleed = root / "bleed.wav"
            audible = root / "audible.wav"
            samples = [0] * 8000
            samples[4000] = 190  # ~0.0058 peak, effectively zero whole-file RMS
            self._write_pcm16(bleed, samples)
            loud = [0] * 8000
            loud[4000:4080] = [3000] * 80  # sparse but clearly audible peak
            self._write_pcm16(audible, loud)

            self.assertTrue(_is_silent(bleed))
            self.assertFalse(_is_silent(audible))

    @staticmethod
    def _write_pcm16(path: Path, samples: list[int]) -> None:
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(
                b"".join(sample.to_bytes(2, "little", signed=True) for sample in samples)
            )

    def test_selected_run_does_not_overwrite_any_full_run_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "Example-D minor-120bpm-440hz"
            out = root / "out"
            folder.mkdir()
            (folder / "Example-kick-D minor-120bpm-440hz.wav").touch()
            out.mkdir()
            existing_manifest = out / "listen_all_summary.json"
            existing_arrangement = out / "full_arrangement.mid"
            existing_part = out / "kick_listened.mid"
            existing_iterations = out / "kick_iterations.json"
            existing_manifest.write_text("golden", encoding="utf-8")
            existing_arrangement.write_bytes(b"golden")
            existing_part.write_bytes(b"golden part")
            existing_iterations.write_text("golden iterations", encoding="utf-8")

            notes = [NoteEvent(0.0, 0.08, 36, 100)]

            def fake_refine(**kwargs):
                work = Path(kwargs["out_dir"])
                work.mkdir(parents=True, exist_ok=True)
                midi = work / "kick_listened.mid"
                write_midi_file(midi, [MidiTrack("Kick", 9, 0, notes)], bpm=120)
                (work / "kick_iterations.json").write_text("[]", encoding="utf-8")
                return RefineResult(notes=notes, score=1.0, history=[], midi_path=midi)

            with patch("sunofriend.listen_all._is_silent", return_value=False), patch(
                "sunofriend.loop.refine_stem", side_effect=fake_refine
            ):
                summary = run_listen_all(
                    folder,
                    out,
                    parts=["kick"],
                    library=root / "library",
                    progress=lambda _: None,
                )

            self.assertEqual(existing_manifest.read_text(encoding="utf-8"), "golden")
            self.assertEqual(existing_arrangement.read_bytes(), b"golden")
            self.assertEqual(existing_part.read_bytes(), b"golden part")
            self.assertEqual(
                existing_iterations.read_text(encoding="utf-8"), "golden iterations"
            )
            self.assertEqual(summary["status"], "complete")
            mode_root = out / "mode_repair"
            self.assertTrue((mode_root / "listen_all_summary_kick.json").is_file())
            self.assertTrue((mode_root / "selected_arrangement_kick.mid").is_file())
            selected_part = mode_root / "selected_kick" / "kick_listened.mid"
            selected_iterations = mode_root / "selected_kick" / "kick_iterations.json"
            self.assertTrue(selected_part.is_file())
            self.assertTrue(selected_iterations.is_file())
            self.assertEqual(Path(summary["parts"]["kick"]["midi"]), selected_part)
            clip_id = summary["parts"]["kick"]["library_clip_id"]
            clip = ClipLibrary(root / "library").get(clip_id)
            self.assertEqual(clip.instrument.role, "kick")
            self.assertEqual(clip.key, KeySignature("D", "minor"))
            self.assertEqual(clip.notes[0].source_start_seconds, 0.0)

    def test_full_rerun_removes_stale_artifacts_for_newly_silent_part(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "Example-B major-119bpm-440hz"
            out = root / "out"
            folder.mkdir()
            out.mkdir()
            (folder / "Example-lead-B major-119bpm-440hz.wav").touch()
            mode_root = out / "mode_repair"
            mode_root.mkdir()
            stale_midi = mode_root / "lead_listened.mid"
            stale_iterations = mode_root / "lead_iterations.json"
            stale_provenance = mode_root / "lead_provenance.json"
            stale_evaluation = mode_root / "lead_evaluation.json"
            variants = mode_root / "variants"
            variants.mkdir()
            stale_variant = variants / "lead-uncertain.mid"
            stale_midi.write_bytes(b"old lead")
            stale_iterations.write_text("old iterations", encoding="utf-8")
            stale_provenance.write_text("old provenance", encoding="utf-8")
            stale_evaluation.write_text("old evaluation", encoding="utf-8")
            stale_variant.write_bytes(b"old variant")

            with patch("sunofriend.listen_all._is_silent", return_value=True):
                summary = run_listen_all(folder, out, progress=lambda _: None)

            self.assertEqual(summary["parts"]["lead"]["status"], "skipped: near-silent stem")
            self.assertFalse(stale_midi.exists())
            self.assertFalse(stale_iterations.exists())
            self.assertFalse(stale_provenance.exists())
            self.assertFalse(stale_evaluation.exists())
            self.assertFalse(stale_variant.exists())

    def test_no_output_rerun_removes_stale_selected_part_and_arrangement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "Example-B major-119bpm-440hz"
            folder.mkdir()
            mode_root = root / "out/mode_repair"
            publish_dir = mode_root / "selected_kick"
            variants = publish_dir / "variants"
            variants.mkdir(parents=True)
            stale_part = publish_dir / "kick_listened.mid"
            stale_sidecar = publish_dir / "kick_provenance.json"
            stale_variant = variants / "kick-possible.mid"
            stale_arrangement = mode_root / "selected_arrangement_kick.mid"
            stale_part.write_bytes(b"stale")
            stale_sidecar.write_text("stale", encoding="utf-8")
            stale_variant.write_bytes(b"stale")
            stale_arrangement.write_bytes(b"stale")

            summary = run_listen_all(
                folder,
                root / "out",
                parts=["kick"],
                progress=lambda _: None,
            )

            self.assertEqual(summary["status"], "no-output")
            self.assertFalse(stale_part.exists())
            self.assertFalse(stale_sidecar.exists())
            self.assertFalse(stale_variant.exists())
            self.assertFalse(stale_arrangement.exists())

    def test_failed_full_rerun_does_not_leave_previous_public_midi(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "Example-B major-119bpm-440hz"
            folder.mkdir()
            (folder / "Example-kick-B major-119bpm-440hz.wav").touch()
            mode_root = root / "out/mode_repair"
            mode_root.mkdir(parents=True)
            stale_part = mode_root / "kick_listened.mid"
            stale_arrangement = mode_root / "full_arrangement.mid"
            stale_part.write_bytes(b"stale")
            stale_arrangement.write_bytes(b"stale")

            with patch("sunofriend.listen_all._is_silent", return_value=False), patch(
                "sunofriend.loop.refine_stem", side_effect=RuntimeError("conversion failed")
            ):
                summary = run_listen_all(
                    folder,
                    root / "out",
                    progress=lambda _: None,
                )

            self.assertEqual(summary["status"], "failed")
            self.assertFalse(stale_part.exists())
            self.assertFalse(stale_arrangement.exists())

    def test_library_archive_id_covers_all_immutable_clip_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stem = root / "kick.wav"
            midi = root / "kick.mid"
            stem.touch()
            notes = [NoteEvent(0.0, 0.08, 36, 100)]
            write_midi_file(midi, [MidiTrack("Kick", 9, 0, notes)], bpm=120)
            arguments = {
                "title": "Example - kick",
                "name": "kick",
                "kind": "kick",
                "stem": stem,
                "midi": midi,
                "notes": notes,
                "key": "D minor",
                "grid": Grid(120),
                "daw_bpm": 120,
            }

            first = _make_library_clip(score=1.0, **arguments)
            repeated = _make_library_clip(score=1.0, **arguments)
            rescored = _make_library_clip(score=0.9, **arguments)
            library = ClipLibrary(root / "library")

            self.assertEqual(first.clip_id, repeated.clip_id)
            self.assertNotEqual(first.clip_id, rescored.clip_id)
            library.add(first)
            library.add(repeated)
            library.add(rescored)
            self.assertEqual(len(library.list()), 2)

    def test_cli_returns_failure_when_listen_all_produces_no_output(self):
        summary = {"status": "no-output", "set_garageband_tempo_to": 120.0}
        stdout = StringIO()
        with patch("sunofriend.render.is_available", return_value=True), patch(
            "sunofriend.listen_all.run_listen_all", return_value=summary
        ), redirect_stdout(stdout):
            result = main(["listen-all", "unused", "--out-dir", "unused"])

        self.assertEqual(result, 2)
        self.assertIn("set GarageBand tempo to: 120.0", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
