from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path
from unittest.mock import patch

from sunofriend.automatic_selection import plan_automatic_selection
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.simple_result import (
    SIMPLE_RESULT_SCHEMA,
    SimpleResultError,
    build_simple_result,
)


class SimpleResultTests(unittest.TestCase):
    def test_builds_exact_midi_balanced_wav_receipt_and_zip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Song-B minor-113bpm-440hz"
            conversion = root / "conversion"
            destination = conversion / "AUTOMATIC-SONG"
            project.mkdir()
            conversion.mkdir()
            source = project / "Song-bass-B minor-113bpm-440hz.wav"
            midi = conversion / "bass_listened.mid"
            preview = root / "preview.wav"
            _write_wav(source, sample=500)
            _write_wav(preview, sample=1000)
            _write_midi(midi)
            summary = conversion / "listen_all_summary.json"
            summary.write_text(
                json.dumps(
                    {"parts": {"bass": {"status": "ok", "midi": str(midi)}}}
                ),
                encoding="utf-8",
            )
            catalog = _catalog(project, source, midi)
            selection = plan_automatic_selection(
                catalog,
                (summary,),
                result_root=conversion,
            )
            fake_artifacts = _FakeArtifacts(preview)

            with patch(
                "sunofriend.simple_result.WorkbenchArtifacts",
                return_value=fake_artifacts,
            ), patch(
                "sunofriend.simple_result.build_balanced_midi_audition",
                side_effect=_fake_balanced_builder,
            ):
                result = build_simple_result(
                    catalog,
                    selection,
                    destination=destination,
                    artifact_cache_root=root / "cache",
                )

            self.assertEqual(result.selected_count, 1)
            self.assertEqual(result.omitted_count, 0)
            self.assertTrue(result.balanced_wav_path.is_file())
            self.assertTrue(result.combined_midi_path.is_file())
            exact_copy = destination / "MIDI" / "01-bass-automatic-primary.mid"
            self.assertEqual(exact_copy.read_bytes(), midi.read_bytes())
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], SIMPLE_RESULT_SCHEMA)
            self.assertEqual(manifest["workflow_status"], "automatic_complete")
            self.assertEqual(
                manifest["studio_review"]["status"],
                "not_reviewed",
            )
            self.assertTrue(manifest["effects"]["automatic_selection"])
            self.assertFalse(manifest["mix"]["source_audio_mixed_into_wav"])
            self.assertFalse(manifest["mix"]["release_master"])
            self.assertNotIn(str(project), json.dumps(manifest))
            with zipfile.ZipFile(result.zip_path) as archive:
                names = set(archive.namelist())
            self.assertIn("MIDI/01-bass-automatic-primary.mid", names)
            self.assertIn(
                "AUDIO/balanced-midi-song-interpretation.wav",
                names,
            )
            self.assertIn("sunofriend-result.json", names)

    def test_existing_destination_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "AUTOMATIC-SONG"
            destination.mkdir()
            with self.assertRaisesRegex(SimpleResultError, "already exists"):
                build_simple_result(
                    {},
                    plan=None,  # type: ignore[arg-type]
                    destination=destination,
                    artifact_cache_root=root / "cache",
                )

    def test_omitted_longest_source_still_sets_complete_song_horizon(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Song-B minor-113bpm-440hz"
            conversion = root / "conversion"
            destination = conversion / "AUTOMATIC-SONG"
            project.mkdir()
            conversion.mkdir()
            selected_source = project / "Song-bass-B minor-113bpm-440hz.wav"
            omitted_source = project / "Song-vocals-B minor-113bpm-440hz.wav"
            midi = conversion / "bass_listened.mid"
            preview = root / "preview.wav"
            _write_wav(selected_source, sample=500, frames=4_410)
            _write_wav(omitted_source, sample=700, frames=13_230)
            _write_wav(preview, sample=1000, frames=4_410)
            _write_midi(midi)
            summary = conversion / "listen_all_summary.json"
            summary.write_text(
                json.dumps(
                    {"parts": {"bass": {"status": "ok", "midi": str(midi)}}}
                ),
                encoding="utf-8",
            )
            catalog = _catalog(project, selected_source, midi)
            catalog["stems"].append(
                {
                    "stem_id": "stem-vocals",
                    "label": "Vocals",
                    "role": "vocals",
                    "source_path": str(omitted_source.resolve()),
                    "source": _record(omitted_source),
                    "candidates": [],
                }
            )
            selection = plan_automatic_selection(
                catalog,
                (summary,),
                result_root=conversion,
            )

            with patch(
                "sunofriend.simple_result.WorkbenchArtifacts",
                return_value=_FakeArtifacts(preview),
            ), patch(
                "sunofriend.simple_result.build_balanced_midi_audition",
                side_effect=_fake_balanced_builder,
            ):
                result = build_simple_result(
                    catalog,
                    selection,
                    destination=destination,
                    artifact_cache_root=root / "cache",
                )

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(result.selected_count, 1)
            self.assertEqual(result.omitted_count, 1)
            self.assertEqual(manifest["mix"]["output_frames"], 13_230)
            self.assertEqual(
                {
                    row["role"]: row["output_frames"]
                    for row in manifest["mix"]["project_source_horizons"]
                },
                {"bass": 4_410, "vocals": 13_230},
            )
            report = json.loads(
                (destination / "TECHNICAL" / "balanced-mix-report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(report["frames"], 13_230)


class _FakeArtifacts:
    def __init__(self, preview: Path) -> None:
        self.preview = preview

    def cached_candidate_preview(self, *_args, **_kwargs):
        return None

    def render_candidate_preview(self, *_args, **_kwargs):
        return {
            "cache_key": "c" * 64,
            "preview": _record(self.preview),
        }


def _fake_balanced_builder(
    lanes,
    *,
    output_path,
    report_path,
    recipe_path,
    output_frames,
):
    output = Path(output_path)
    source = Path(lanes[0]["preview_path"])
    output.write_bytes(source.read_bytes())
    report = {
        "schema": "sunofriend.workbench-balanced-mix-report.v3",
        "policy": "source-referenced-summed-group-balance-v3",
        "frames": output_frames,
        "effects": {"automatic_selection": False},
    }
    Path(report_path).write_text(json.dumps(report), encoding="utf-8")
    Path(recipe_path).write_text("GarageBand recipe\n", encoding="utf-8")
    return report


def _catalog(project: Path, source: Path, midi: Path) -> dict:
    return {
        "project_id": "project-simple",
        "name": project.name,
        "setup": {"bpm": 113.0, "key": "B minor", "tuning_hz": 440.0},
        "stems": [
            {
                "stem_id": "stem-bass",
                "label": "Bass",
                "role": "bass",
                "source_path": str(source.resolve()),
                "source": _record(source),
                "candidates": [
                    {
                        "candidate_id": "candidate-bass",
                        "label": "Production primary",
                        "process": "sunofriend-specialist",
                        "primary": True,
                        "diagnostic_only": False,
                        "audition_blocked": False,
                        "midi_path": str(midi.resolve()),
                        "midi": _record(midi),
                    }
                ],
            }
        ],
    }


def _record(path: Path) -> dict:
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def _write_midi(path: Path) -> None:
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
        bpm=113.0,
    )


def _write_wav(path: Path, *, sample: int, frames: int = 4_410) -> None:
    frame = int(sample).to_bytes(2, "little", signed=True)
    with wave.open(str(path), mode="wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(frame * frames)


if __name__ == "__main__":
    unittest.main()
