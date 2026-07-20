from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from sunofriend import workbench_artifacts as module
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.workbench_artifacts import (
    DECODED_STEM_LOOP_SCHEMA,
    WorkbenchArtifacts,
)


class WorkbenchDecodedStemLoopTests(unittest.TestCase):
    @unittest.skipUnless(
        importlib.util.find_spec("numpy") and importlib.util.find_spec("soundfile"),
        "decoded-loop audio tests require the optional convert dependencies",
    )
    def test_pcm24_source_and_short_preview_build_deterministic_padded_pcm16(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, soundfont = _catalog(root)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            original_midi_sha256 = _sha256(Path(candidate["midi_path"]))

            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_render_short_stereo_preview,
            ) as renderer:
                first = artifacts.prepare_decoded_stem_loop(
                    catalog,
                    stem["stem_id"],
                    [candidate["candidate_id"]],
                    0.25,
                    1.25,
                )
                second = artifacts.prepare_decoded_stem_loop(
                    catalog,
                    stem["stem_id"],
                    [candidate["candidate_id"]],
                    0.25000001,
                    1.25000001,
                )

            self.assertEqual(renderer.call_count, 1)
            self.assertEqual(first["schema"], DECODED_STEM_LOOP_SCHEMA)
            self.assertFalse(first["cache_hit"])
            self.assertTrue(second["cache_hit"])
            self.assertEqual(first["cache_key"], second["cache_key"])
            self.assertEqual(
                [track["audio"]["sha256"] for track in first["tracks"]],
                [track["audio"]["sha256"] for track in second["tracks"]],
            )
            self.assertEqual(
                [track["kind"] for track in first["tracks"]],
                ["source", "candidate"],
            )

            source_track, candidate_track = first["tracks"]
            self.assertEqual(source_track["sample_rate"], 8_000)
            self.assertEqual(source_track["channels"], 1)
            self.assertEqual(source_track["frames"], 8_000)
            self.assertEqual(source_track["silence_padded_frames"], 0)
            self.assertEqual(candidate_track["sample_rate"], 16_000)
            self.assertEqual(candidate_track["channels"], 2)
            self.assertEqual(candidate_track["frames"], 16_000)
            self.assertEqual(candidate_track["silence_padded_frames"], 8_000)
            self.assertEqual(candidate_track["candidate_id"], candidate["candidate_id"])

            soundfile = _soundfile()
            for track in first["tracks"]:
                info = soundfile.info(track["audio"]["path"])
                self.assertEqual(info.format, "WAV")
                self.assertEqual(info.subtype, "PCM_16")
                self.assertEqual(info.frames, track["frames"])
            candidate_audio, _ = soundfile.read(
                candidate_track["audio"]["path"], dtype="float32", always_2d=True
            )
            self.assertTrue((candidate_audio[:8_000] != 0.0).any())
            self.assertTrue((candidate_audio[8_000:] == 0.0).all())

            cache_dir = Path(source_track["audio"]["path"]).parent
            manifest_path = cache_dir / "manifest.json"
            serialized = manifest_path.read_text(encoding="utf-8")
            stored = json.loads(serialized)
            self.assertNotIn(str(root), serialized)
            self.assertEqual(
                [track["audio"]["path"] for track in stored["tracks"]],
                ["00-source.wav", "01-candidate.wav"],
            )
            self.assertEqual(stat.S_IMODE(cache_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(cache_dir.parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(manifest_path.stat().st_mode), 0o600)
            for track in first["tracks"]:
                self.assertEqual(
                    stat.S_IMODE(Path(track["audio"]["path"]).stat().st_mode),
                    0o600,
                )
            self.assertEqual(_sha256(Path(candidate["midi_path"])), original_midi_sha256)
            self.assertEqual(
                first["effects"],
                {
                    "event_appended": False,
                    "feedback_recorded": False,
                    "midi_mutated": False,
                    "selection_changed": False,
                },
            )

            expected_candidate_sha256 = candidate_track["audio"]["sha256"]
            Path(candidate_track["audio"]["path"]).write_bytes(b"corrupt-loop-cache")
            with patch.object(
                artifacts,
                "render_candidate_preview",
                side_effect=AssertionError("neutral preview should be reused"),
            ):
                rebuilt = artifacts.prepare_decoded_stem_loop(
                    catalog,
                    stem["stem_id"],
                    [candidate["candidate_id"]],
                    0.25,
                    1.25,
                )
            self.assertFalse(rebuilt["cache_hit"])
            self.assertEqual(
                rebuilt["tracks"][1]["audio"]["sha256"],
                expected_candidate_sha256,
            )

    def test_invalid_windows_candidate_ids_and_blocked_candidate_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, soundfont = _catalog(root)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            stem = catalog["stems"][0]
            candidate_id = stem["candidates"][0]["candidate_id"]

            invalid_calls = (
                ((candidate_id,), -0.1, 1.0, "start"),
                ((candidate_id,), 0.0, 0.49, "between 0.5 and 15.0"),
                ((candidate_id,), 0.0, 15.01, "between 0.5 and 15.0"),
                ((candidate_id,), float("nan"), 1.0, "finite"),
                ((candidate_id,), 90_000.0, 90_001.0, "first 24 hours"),
                ((), 0.0, 1.0, "at least one"),
                ((candidate_id, candidate_id), 0.0, 1.0, "unique"),
                (tuple(f"candidate-{index}" for index in range(7)), 0.0, 1.0, "at most 6"),
                (("unknown-candidate",), 0.0, 1.0, "does not belong"),
            )
            for candidate_ids, start, end, message in invalid_calls:
                with self.subTest(candidate_ids=candidate_ids, start=start, end=end):
                    with self.assertRaisesRegex(ValueError, message):
                        artifacts.prepare_decoded_stem_loop(
                            catalog,
                            stem["stem_id"],
                            candidate_ids,
                            start,
                            end,
                        )
            with self.assertRaisesRegex(ValueError, "unknown workbench stem_id"):
                artifacts.prepare_decoded_stem_loop(
                    catalog, "unknown-stem", [candidate_id], 0.0, 1.0
                )

            stem["candidates"][0]["audition_blocked"] = True
            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav"
            ) as renderer:
                with self.assertRaisesRegex(ValueError, "candidate audition is blocked"):
                    artifacts.prepare_decoded_stem_loop(
                        catalog, stem["stem_id"], [candidate_id], 0.0, 1.0
                    )
            renderer.assert_not_called()

    def test_aggregate_input_limit_counts_midi_and_soundfont_before_rendering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, soundfont = _catalog(root)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            declared_total = (
                int(stem["source"]["bytes"])
                + int(candidate["midi"]["bytes"])
                + soundfont.stat().st_size
            )

            with (
                patch.object(
                    module,
                    "_DECODED_LOOP_MAXIMUM_INPUT_BYTES",
                    declared_total - 1,
                ),
                patch.object(
                    module,
                    "_decoded_audio_modules",
                    side_effect=AssertionError(
                        "audio dependencies must not load for an oversized request"
                    ),
                ) as audio_modules,
                patch.object(
                    artifacts,
                    "render_candidate_preview",
                    side_effect=AssertionError(
                        "an oversized request must fail before preview rendering"
                    ),
                ) as renderer,
            ):
                with self.assertRaisesRegex(ValueError, "2 GiB aggregate"):
                    artifacts.prepare_decoded_stem_loop(
                        catalog,
                        stem["stem_id"],
                        [candidate["candidate_id"]],
                        0.0,
                        1.0,
                    )

            audio_modules.assert_not_called()
            renderer.assert_not_called()

    def test_catalogued_midi_drift_is_rejected_before_audio_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, soundfont = _catalog(root)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            midi_path = Path(candidate["midi_path"])
            midi_path.write_bytes(midi_path.read_bytes() + b"drift")
            with self.assertRaisesRegex(ValueError, "candidate MIDI changed"):
                artifacts.prepare_decoded_stem_loop(
                    catalog,
                    stem["stem_id"],
                    [candidate["candidate_id"]],
                    0.0,
                    1.0,
                )

    @unittest.skipUnless(
        importlib.util.find_spec("numpy") and importlib.util.find_spec("soundfile"),
        "decoded-loop audio tests require the optional convert dependencies",
    )
    def test_source_drift_during_preview_render_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, soundfont = _catalog(root)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            source_path = Path(stem["source_path"])

            def render_then_drift(_midi_path, wav_path, **_kwargs):
                _write_pcm_wav(
                    Path(wav_path),
                    sample_rate=16_000,
                    channels=1,
                    frames=16_000,
                )
                source_path.write_bytes(source_path.read_bytes() + b"drift")

            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=render_then_drift,
            ):
                with self.assertRaisesRegex(ValueError, "source audio changed"):
                    artifacts.prepare_decoded_stem_loop(
                        catalog,
                        stem["stem_id"],
                        [candidate["candidate_id"]],
                        0.0,
                        1.0,
                    )
            self.assertFalse((artifacts.root / "decoded-stem-loops").exists())

    @unittest.skipUnless(
        importlib.util.find_spec("numpy") and importlib.util.find_spec("soundfile"),
        "decoded-loop audio tests require the optional convert dependencies",
    )
    def test_mixed_renderer_preview_and_unverified_decode_path_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, soundfont = _catalog(root)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_render_short_stereo_preview,
            ):
                preview = artifacts.render_candidate_preview(
                    catalog, stem["stem_id"], candidate["candidate_id"]
                )

            mismatched = {**preview, "soundfont_sha256": "0" * 64}
            with patch.object(
                artifacts, "cached_candidate_preview", return_value=mismatched
            ):
                with self.assertRaisesRegex(ValueError, "same current SoundFont"):
                    artifacts.prepare_decoded_stem_loop(
                        catalog,
                        stem["stem_id"],
                        [candidate["candidate_id"]],
                        0.0,
                        1.0,
                    )

            source_path = Path(stem["source_path"])
            original = source_path.read_bytes()
            real_reader = module._read_padded_audio_window
            seen_paths: list[Path] = []

            def replace_restore_then_read(np, soundfile, path, **kwargs):
                seen_paths.append(Path(path))
                source_path.write_bytes(b"temporary replacement")
                source_path.write_bytes(original)
                return real_reader(np, soundfile, path, **kwargs)

            with patch(
                "sunofriend.workbench_artifacts._read_padded_audio_window",
                side_effect=replace_restore_then_read,
            ):
                result = artifacts.prepare_decoded_stem_loop(
                    catalog,
                    stem["stem_id"],
                    [candidate["candidate_id"]],
                    0.0,
                    1.0,
                )
            self.assertTrue(seen_paths)
            self.assertTrue(
                all(path.name.startswith(".verified-input-") for path in seen_paths)
            )
            self.assertFalse(
                any(
                    path.name.startswith(".verified-input-")
                    for path in Path(result["tracks"][0]["audio"]["path"])
                    .parent.iterdir()
                )
            )

    @unittest.skipUnless(
        importlib.util.find_spec("numpy") and importlib.util.find_spec("soundfile"),
        "decoded-loop audio tests require the optional convert dependencies",
    )
    def test_private_decoded_loop_cache_evicts_old_windows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, soundfont = _catalog(root)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            stem = catalog["stems"][0]
            candidate_id = stem["candidates"][0]["candidate_id"]
            with (
                patch(
                    "sunofriend.workbench_artifacts.render_midi_to_wav",
                    side_effect=_render_short_stereo_preview,
                ),
                patch(
                    "sunofriend.workbench_artifacts._DECODED_LOOP_CACHE_MAXIMUM_ENTRIES",
                    1,
                ),
            ):
                first = artifacts.prepare_decoded_stem_loop(
                    catalog, stem["stem_id"], [candidate_id], 0.0, 1.0
                )
                second = artifacts.prepare_decoded_stem_loop(
                    catalog, stem["stem_id"], [candidate_id], 1.0, 2.0
                )
            cache_root = artifacts.root / "decoded-stem-loops"
            entries = [path for path in cache_root.iterdir() if path.is_dir()]
            self.assertEqual([path.name for path in entries], [second["cache_key"]])
            self.assertNotEqual(first["cache_key"], second["cache_key"])

    def test_neutral_preview_renders_from_verified_midi_and_soundfont_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, soundfont = _catalog(root)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            midi_path = Path(candidate["midi_path"])
            original_midi = midi_path.read_bytes()
            original_soundfont = soundfont.read_bytes()
            real_read_midi = module.read_midi_clips
            seen: dict[str, Path] = {}

            def read_snapshot(path, **kwargs):
                seen["midi"] = Path(path)
                midi_path.write_bytes(b"temporary MIDI replacement")
                midi_path.write_bytes(original_midi)
                return real_read_midi(path, **kwargs)

            def render_with_snapshot(_midi_path, wav_path, **kwargs):
                seen["soundfont"] = Path(kwargs["soundfont_path"])
                soundfont.write_bytes(b"temporary SoundFont replacement")
                soundfont.write_bytes(original_soundfont)
                _write_pcm_wav(
                    Path(wav_path), sample_rate=16_000, channels=1, frames=16_000
                )

            with (
                patch(
                    "sunofriend.workbench_artifacts.read_midi_clips",
                    side_effect=read_snapshot,
                ),
                patch(
                    "sunofriend.workbench_artifacts.render_midi_to_wav",
                    side_effect=render_with_snapshot,
                ),
            ):
                preview = artifacts.render_candidate_preview(
                    catalog, stem["stem_id"], candidate["candidate_id"]
                )

            self.assertEqual(seen["midi"].name, ".verified-source.mid")
            self.assertEqual(seen["soundfont"].name, ".verified-soundfont.sf2")
            self.assertTrue(Path(preview["preview"]["path"]).is_file())
            self.assertFalse(
                any(
                    path.name.startswith(".verified-")
                    for path in Path(preview["preview"]["path"]).parent.iterdir()
                )
            )


def _catalog(root: Path) -> tuple[dict, Path]:
    source = root / "private-source.wav"
    _write_pcm_wav(
        source,
        sample_rate=8_000,
        channels=1,
        frames=16_000,
        sample_width=3,
    )
    midi = root / "candidate.mid"
    write_midi_file(
        midi,
        [
            MidiTrack(
                name="Keys",
                channel=0,
                program=4,
                notes=[
                    NoteEvent(
                        start=0.0,
                        end=1.5,
                        pitch=60,
                        velocity=88,
                    )
                ],
            )
        ],
        bpm=120.0,
    )
    soundfont = root / "test.sf2"
    soundfont.write_bytes(b"test-soundfont")
    source_record = _record(source)
    midi_record = _record(midi)
    return (
        {
            "project_id": "project-decoded-loop-test",
            "setup": {"bpm": 120.0},
            "stems": [
                {
                    "stem_id": "stem-decoded-loop-test",
                    "role": "keys",
                    "source_path": str(source.resolve()),
                    "source": source_record,
                    "candidates": [
                        {
                            "candidate_id": "candidate-decoded-loop-test",
                            "midi_path": str(midi.resolve()),
                            "midi": midi_record,
                            "audition_blocked": False,
                        }
                    ],
                }
            ],
        },
        soundfont,
    )


def _render_short_stereo_preview(_midi_path, wav_path, **_kwargs) -> None:
    _write_pcm_wav(
        Path(wav_path), sample_rate=16_000, channels=2, frames=12_000
    )


def _write_pcm_wav(
    path: Path,
    *,
    sample_rate: int,
    channels: int,
    frames: int,
    sample_width: int = 2,
) -> None:
    maximum = (1 << (sample_width * 8 - 1)) - 1
    sample = int(maximum * 0.25).to_bytes(sample_width, "little", signed=True)
    frame = sample * channels
    with wave.open(str(path), "wb") as destination:
        destination.setnchannels(channels)
        destination.setsampwidth(sample_width)
        destination.setframerate(sample_rate)
        destination.writeframes(frame * frames)


def _record(path: Path) -> dict:
    return {
        "path": str(path.resolve()),
        "name": path.name,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _soundfile():
    import soundfile

    return soundfile


if __name__ == "__main__":
    unittest.main()
