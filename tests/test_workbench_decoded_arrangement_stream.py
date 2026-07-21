from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
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
    DECODED_ARRANGEMENT_CHUNK_SCHEMA,
    DECODED_ARRANGEMENT_STREAM_SCHEMA,
    WorkbenchArtifacts,
)


@unittest.skipUnless(
    importlib.util.find_spec("numpy") and importlib.util.find_spec("soundfile"),
    "decoded arrangement streaming tests require numpy and soundfile",
)
class WorkbenchDecodedArrangementStreamTests(unittest.TestCase):
    def test_stream_snapshot_lru_refreshes_prepare_and_chunk_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, soundfont = _catalog(root)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )
            with (
                patch(
                    "sunofriend.workbench_artifacts.render_midi_to_wav",
                    side_effect=_render_preview,
                ),
                patch.object(module, "_DECODED_STREAM_CACHE_MAXIMUM_ENTRIES", 2),
                patch.object(
                    module, "_DECODED_STREAM_CACHE_MAXIMUM_BYTES", 1_000_000_000
                ),
            ):
                source = artifacts.prepare_decoded_arrangement_stream(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                    "source-only",
                )
                selected = artifacts.prepare_decoded_arrangement_stream(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                    "selected-midi",
                )
                parent = artifacts.root / "decoded-arrangement-streams"
                source_root = parent / source["stream_sha256"]
                selected_root = parent / selected["stream_sha256"]
                os.utime(source_root, ns=(1_000_000_000, 1_000_000_000))
                os.utime(selected_root, ns=(2_000_000_000, 2_000_000_000))

                refreshed = artifacts.prepare_decoded_arrangement_stream(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                    "source-only",
                )
                self.assertTrue(refreshed["cache_hit"])
                main = artifacts.prepare_decoded_arrangement_stream(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                    "main-only",
                )
                self.assertTrue(source_root.exists())
                self.assertFalse(selected_root.exists())

                main_root = parent / main["stream_sha256"]
                os.utime(source_root, ns=(1_000_000_000, 1_000_000_000))
                os.utime(main_root, ns=(2_000_000_000, 2_000_000_000))
                artifacts.prepare_decoded_arrangement_chunk(
                    catalog, current, source["stream_sha256"], 0
                )
                hybrid = artifacts.prepare_decoded_arrangement_stream(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                    "hybrid",
                )
                self.assertTrue(source_root.exists())
                self.assertFalse(main_root.exists())
                self.assertTrue((parent / hybrid["stream_sha256"]).exists())

    def test_stream_snapshot_quota_keeps_oversized_current_and_skips_unsafe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifacts = WorkbenchArtifacts(root / "artifacts")
            parent = artifacts.root / "decoded-arrangement-streams"
            parent.mkdir(parents=True)
            current = parent / ("a" * 64)
            old = parent / ("b" * 64)
            racy = parent / ("c" * 64)
            invalid = parent / "not-a-stream"
            for directory in (current, old, racy, invalid):
                directory.mkdir()
            (current / "large.audio").write_bytes(b"0123456789")
            (old / "old.audio").write_bytes(b"old")
            external = root / "external"
            external.mkdir()
            (external / "keep.txt").write_text("keep", encoding="utf-8")
            symlink = parent / ("d" * 64)
            symlink.symlink_to(external, target_is_directory=True)
            shared = artifacts.root / "decoded-arrangement-chunks" / ("e" * 64)
            shared.mkdir(parents=True)

            original_size = module._directory_regular_file_bytes

            def racing_size(path: Path) -> int:
                if path == racy:
                    raise OSError("directory disappeared during scan")
                return original_size(path)

            with (
                patch.object(module, "_DECODED_STREAM_CACHE_MAXIMUM_ENTRIES", 1),
                patch.object(module, "_DECODED_STREAM_CACHE_MAXIMUM_BYTES", 4),
                patch.object(
                    module,
                    "_directory_regular_file_bytes",
                    side_effect=racing_size,
                ),
            ):
                artifacts._touch_and_prune_decoded_stream_cache(current.name)

            self.assertTrue(current.exists())
            self.assertFalse(old.exists())
            self.assertTrue(racy.exists())
            self.assertTrue(invalid.exists())
            self.assertTrue(symlink.is_symlink())
            self.assertTrue((external / "keep.txt").exists())
            self.assertTrue(shared.exists())

    def test_verified_stream_fast_path_avoids_full_song_hashes_and_fails_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, soundfont = _catalog(root)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )
            stream = artifacts.prepare_decoded_arrangement_stream(
                catalog,
                current,
                selection["selection_manifest_sha256"],
                "source-only",
            )
            stream_root = (
                artifacts.root
                / "decoded-arrangement-streams"
                / stream["stream_sha256"]
            )
            private_record = json.loads(
                (stream_root / "record.json").read_text(encoding="utf-8")
            )
            snapshot = (
                stream_root / private_record["inputs"][0]["snapshot"]["path"]
            ).resolve()
            source_paths = {
                Path(stem["source"]["path"]).resolve() for stem in catalog["stems"]
            }

            with patch.object(module, "_sha256", wraps=module._sha256) as hasher:
                artifacts.prepare_decoded_arrangement_chunk(
                    catalog, current, stream["stream_sha256"], 0
                )
                artifacts.prepare_decoded_arrangement_chunk(
                    catalog, current, stream["stream_sha256"], 1
                )
            hashed = {Path(call.args[0]).resolve() for call in hasher.call_args_list}
            self.assertFalse(source_paths & hashed)
            self.assertNotIn(snapshot, hashed)

            with patch.object(module, "_sha256", wraps=module._sha256) as hasher:
                with self.assertRaisesRegex(ValueError, "out of range"):
                    artifacts.prepare_decoded_arrangement_chunk(
                        catalog, current, stream["stream_sha256"], 99
                    )
            hasher.assert_not_called()

            snapshot_stat = snapshot.stat()
            os.utime(
                snapshot,
                ns=(snapshot_stat.st_atime_ns, snapshot_stat.st_mtime_ns + 1),
            )
            with patch.object(module, "_sha256", wraps=module._sha256) as hasher:
                artifacts.prepare_decoded_arrangement_chunk(
                    catalog, current, stream["stream_sha256"], 2
                )
            hashed = {Path(call.args[0]).resolve() for call in hasher.call_args_list}
            self.assertIn(snapshot, hashed)
            self.assertTrue(source_paths & hashed)

            data = bytearray(snapshot.read_bytes())
            data[-1] ^= 1
            snapshot.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "missing or changed"):
                artifacts.prepare_decoded_arrangement_chunk(
                    catalog, current, stream["stream_sha256"], 2
                )
            self.assertNotIn(stream["stream_sha256"], artifacts._verified_stream_cache)

    def test_source_only_stream_is_exact_private_cached_and_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, soundfont = _catalog(root)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )

            with (
                patch.object(
                    artifacts,
                    "_soundfont",
                    side_effect=AssertionError("source-only must not load SoundFont"),
                ),
                patch.object(
                    artifacts,
                    "render_candidate_preview",
                    side_effect=AssertionError("source-only must not render MIDI"),
                ),
                patch.object(
                    module,
                    "_write_verified_private_snapshot",
                    wraps=module._write_verified_private_snapshot,
                ) as snapshot_writer,
            ):
                stream = artifacts.prepare_decoded_arrangement_stream(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                    "source-only",
                )
                cached = artifacts.prepare_decoded_arrangement_stream(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                    "source-only",
                )

            self.assertEqual(snapshot_writer.call_count, 2)
            self.assertEqual(stream["schema"], DECODED_ARRANGEMENT_STREAM_SCHEMA)
            self.assertFalse(stream["cache_hit"])
            self.assertTrue(cached["cache_hit"])
            self.assertEqual(stream["stream_sha256"], cached["stream_sha256"])
            self.assertEqual(stream["preset"], "source-only")
            self.assertIsNone(stream["renderer"])
            self.assertEqual(stream["anchor"]["sample_rate"], 8_000)
            self.assertEqual(stream["anchor"]["song_end_frame"], 88_003)
            self.assertEqual(stream["chunking"]["chunk_count"], 3)
            self.assertEqual(
                [
                    (chunk["anchor_start_frame"], chunk["anchor_end_frame"])
                    for chunk in stream["chunking"]["chunks"]
                ],
                [(0, 40_000), (40_000, 80_000), (80_000, 88_003)],
            )
            self.assertTrue(stream["chunking"]["chunks"][-1]["logical_end"])
            self.assertNotIn(str(root), json.dumps(stream, sort_keys=True))
            self.assertTrue(all(value is False for value in stream["effects"].values()))

            stream_root = (
                artifacts.root / "decoded-arrangement-streams" / stream["stream_sha256"]
            )
            private_record = json.loads(
                (stream_root / "record.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(private_record["inputs"]), 2)
            self.assertTrue(
                all(
                    not Path(item["snapshot"]["path"]).is_absolute()
                    for item in private_record["inputs"]
                )
            )
            self.assertEqual(stat.S_IMODE(stream_root.stat().st_mode), 0o700)
            self.assertEqual(
                stat.S_IMODE((stream_root / "record.json").stat().st_mode), 0o600
            )

            chunks = [
                artifacts.prepare_decoded_arrangement_chunk(
                    catalog, current, stream["stream_sha256"], index
                )
                for index in range(3)
            ]
            self.assertTrue(
                all(
                    chunk["schema"] == DECODED_ARRANGEMENT_CHUNK_SCHEMA
                    for chunk in chunks
                )
            )
            self.assertEqual(
                [chunk["anchor"]["start_frame"] for chunk in chunks],
                [0, 40_000, 80_000],
            )
            self.assertEqual(
                [chunk["anchor"]["end_frame"] for chunk in chunks],
                [40_000, 80_000, 88_003],
            )
            self.assertTrue(chunks[-1]["anchor"]["logical_end"])
            self.assertEqual(chunks[-1]["anchor"]["end_frame"], 88_003)
            self.assertTrue(
                any(
                    track["silence_padded_frames"] > 0 for track in chunks[-1]["tracks"]
                )
            )
            self.assertTrue(
                all(
                    chunk["aggregate_output_bytes"]
                    <= module._DECODED_STREAM_CHUNK_MAXIMUM_OUTPUT_BYTES
                    for chunk in chunks
                )
            )
            for chunk in chunks:
                self.assertTrue(
                    all(value is False for value in chunk["effects"].values())
                )

            damaged = Path(chunks[1]["tracks"][0]["audio"]["path"])
            original_sha256 = chunks[1]["tracks"][0]["audio"]["sha256"]
            damaged.write_bytes(b"tampered decoded chunk")
            rebuilt = artifacts.prepare_decoded_arrangement_chunk(
                catalog, current, stream["stream_sha256"], 1
            )
            self.assertFalse(rebuilt["cache_hit"])
            self.assertEqual(rebuilt["tracks"][0]["audio"]["sha256"], original_sha256)

    def test_hybrid_stream_pins_role_neutral_previews_and_rechecks_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, soundfont = _catalog(root)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )
            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_render_preview,
            ) as renderer:
                stream = artifacts.prepare_decoded_arrangement_stream(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                    "hybrid",
                )

            self.assertEqual(renderer.call_count, 2)
            self.assertEqual(
                [track["kind"] for track in stream["tracks"]],
                ["source", "source", "selected_midi", "selected_midi"],
            )
            self.assertEqual(
                [track["role"] for track in stream["tracks"][-2:]],
                ["bass", "pluck"],
            )
            self.assertEqual(
                stream["renderer"],
                {
                    "policy": module._RENDER_POLICY,
                    "soundfont_sha256": _sha256(soundfont),
                },
            )
            stream_root = (
                artifacts.root / "decoded-arrangement-streams" / stream["stream_sha256"]
            )
            self.assertNotIn(
                str(root),
                (stream_root / "manifest.json").read_text(encoding="utf-8"),
            )
            first = artifacts.prepare_decoded_arrangement_chunk(
                catalog, current, stream["stream_sha256"], 0
            )
            self.assertEqual(len(first["tracks"]), 4)

            role_changed = copy.deepcopy(current)
            role_changed["stems"]["stem-a"]["role"] = "synth bass"
            with self.assertRaisesRegex(ValueError, "selection changed"):
                artifacts.prepare_decoded_arrangement_chunk(
                    catalog, role_changed, stream["stream_sha256"], 0
                )

            soundfont.write_bytes(b"changed soundfont")
            with self.assertRaisesRegex(ValueError, "SoundFont changed"):
                artifacts.prepare_decoded_arrangement_chunk(
                    catalog, current, stream["stream_sha256"], 0
                )

    def test_validation_adapts_chunk_size_and_rejects_unsafe_plans(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, soundfont = _catalog(root)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )
            with self.assertRaisesRegex(ValueError, "must be exactly"):
                artifacts.prepare_decoded_arrangement_stream(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                    "custom",
                )
            with self.assertRaisesRegex(ValueError, "selection changed"):
                artifacts.prepare_decoded_arrangement_stream(
                    catalog, current, "0" * 64, "source-only"
                )

            with patch.object(
                module,
                "_decoded_audio_info",
                return_value={
                    "sample_rate": 8_000,
                    "channels": 1,
                    "frames": 8_000 * 1_200 + 1,
                },
            ):
                with self.assertRaisesRegex(ValueError, "up to 20 minutes"):
                    artifacts.prepare_decoded_arrangement_stream(
                        catalog,
                        current,
                        selection["selection_manifest_sha256"],
                        "source-only",
                    )

            with patch.object(
                module, "_DECODED_STREAM_CHUNK_MAXIMUM_OUTPUT_BYTES", 100_000
            ):
                adaptive = artifacts.prepare_decoded_arrangement_stream(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                    "source-only",
                )
            self.assertLess(adaptive["chunking"]["chunk_seconds"], 5.0)
            self.assertLessEqual(
                adaptive["chunking"]["maximum_pcm16_output_bytes"], 100_000
            )

            fresh_artifacts = WorkbenchArtifacts(
                root / "small-state" / "artifacts", soundfont_path=soundfont
            )
            with patch.object(
                module, "_DECODED_STREAM_CHUNK_MAXIMUM_OUTPUT_BYTES", 9_000
            ):
                with self.assertRaisesRegex(ValueError, "more than 480"):
                    fresh_artifacts.prepare_decoded_arrangement_stream(
                        catalog,
                        current,
                        selection["selection_manifest_sha256"],
                        "source-only",
                    )

            oversized = copy.deepcopy(catalog)
            for stem in oversized["stems"]:
                stem["source"]["bytes"] = module._DECODED_LOOP_MAXIMUM_INPUT_BYTES
            oversized_selection = artifacts.decoded_arrangement_selection_manifest(
                oversized, current
            )
            with patch.object(
                module,
                "_decoded_audio_modules",
                side_effect=AssertionError("oversized request must fail before decode"),
            ) as audio_modules:
                with self.assertRaisesRegex(ValueError, "2 GiB aggregate"):
                    artifacts.prepare_decoded_arrangement_stream(
                        oversized,
                        current,
                        oversized_selection["selection_manifest_sha256"],
                        "source-only",
                    )
            audio_modules.assert_not_called()

            crowded_stems = []
            crowded_current = {"stems": {}}
            for index in range(25):
                source = root / f"crowded-{index:02d}.wav"
                _write_pcm_wav(
                    source,
                    sample_rate=8_000,
                    channels=1,
                    frames=100 + index,
                )
                stem_id = f"crowded-{index:02d}"
                crowded_stems.append(
                    {
                        "stem_id": stem_id,
                        "role": "percussion",
                        "source_path": str(source.resolve()),
                        "source": _record(source),
                        "candidates": [],
                    }
                )
                crowded_current["stems"][stem_id] = {"candidates": {}}
            crowded_catalog = {
                "project_id": "crowded-stream-project",
                "setup": {"bpm": 120.0},
                "stems": crowded_stems,
            }
            crowded_selection = artifacts.decoded_arrangement_selection_manifest(
                crowded_catalog, crowded_current
            )
            with self.assertRaisesRegex(ValueError, "at most 24"):
                artifacts.prepare_decoded_arrangement_stream(
                    crowded_catalog,
                    crowded_current,
                    crowded_selection["selection_manifest_sha256"],
                    "source-only",
                )

    def test_chunk_memory_budget_uses_browser_anchor_rate(self) -> None:
        inputs = [
            {
                "sample_rate": 8_000,
                "channels": 2,
            }
        ]
        with patch.object(
            module,
            "_DECODED_STREAM_TWO_CHUNK_FLOAT_MAXIMUM_BYTES",
            1_000_000,
        ):
            plan = module._decoded_stream_chunk_plan(
                anchor_sample_rate=48_000,
                anchor_song_end_frame=480_000,
                inputs=inputs,
            )

        self.assertLessEqual(plan["chunk_anchor_frames"], 62_500)
        self.assertLessEqual(plan["maximum_two_chunk_float_bytes"], 1_000_000)
        self.assertEqual(
            module._decoded_browser_two_chunk_float_bytes(
                plan["chunk_anchor_frames"], inputs
            ),
            plan["chunk_anchor_frames"] * 2 * 4 * 2,
        )

    def test_chunk_family_uses_shared_rebuildable_quota_and_stream_tamper_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, soundfont = _catalog(root)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )
            stream = artifacts.prepare_decoded_arrangement_stream(
                catalog,
                current,
                selection["selection_manifest_sha256"],
                "source-only",
            )
            with patch.object(module, "_DECODED_LOOP_CACHE_MAXIMUM_ENTRIES", 1):
                first = artifacts.prepare_decoded_arrangement_chunk(
                    catalog, current, stream["stream_sha256"], 0
                )
                second = artifacts.prepare_decoded_arrangement_chunk(
                    catalog, current, stream["stream_sha256"], 1
                )
            self.assertFalse(Path(first["tracks"][0]["audio"]["path"]).exists())
            self.assertTrue(Path(second["tracks"][0]["audio"]["path"]).exists())

            stream_root = (
                artifacts.root / "decoded-arrangement-streams" / stream["stream_sha256"]
            )
            private_record = json.loads(
                (stream_root / "record.json").read_text(encoding="utf-8")
            )
            snapshot = stream_root / private_record["inputs"][0]["snapshot"]["path"]
            snapshot.write_bytes(b"tampered stream snapshot")
            with self.assertRaisesRegex(ValueError, "missing or changed"):
                artifacts.prepare_decoded_arrangement_chunk(
                    catalog, current, stream["stream_sha256"], 1
                )
            rebuilt = artifacts.prepare_decoded_arrangement_stream(
                catalog,
                current,
                selection["selection_manifest_sha256"],
                "source-only",
            )
            self.assertFalse(rebuilt["cache_hit"])
            self.assertEqual(rebuilt["stream_sha256"], stream["stream_sha256"])


def _catalog(root: Path) -> tuple[dict, dict, Path]:
    source_a = root / "source-a.wav"
    source_b = root / "source-b.wav"
    _write_pcm_wav(source_a, sample_rate=8_000, channels=1, frames=88_003)
    _write_pcm_wav(source_b, sample_rate=16_000, channels=2, frames=160_000)
    midi_a = root / "candidate-a.mid"
    midi_b = root / "candidate-b.mid"
    _write_midi(midi_a, pitch=40, program=4)
    _write_midi(midi_b, pitch=67, program=48)
    soundfont = root / "test.sf2"
    soundfont.write_bytes(b"decoded-stream-test-soundfont")
    catalog = {
        "project_id": "decoded-stream-project",
        "setup": {"bpm": 120.0},
        "stems": [
            _stem("stem-a", "keys", source_a, "candidate-a", midi_a),
            _stem("stem-b", "strings", source_b, "candidate-b", midi_b),
            {
                "stem_id": "stem-a-duplicate",
                "role": "percussion",
                "source_path": str(source_a.resolve()),
                "source": _record(source_a),
                "candidates": [],
            },
        ],
    }
    current = {
        "stems": {
            "stem-a": {
                "role": "bass",
                "main_candidate_id": "candidate-a",
                "candidates": {"candidate-a": {"decision": "main"}},
            },
            "stem-b": {
                "role": "pluck",
                "main_candidate_id": None,
                "candidates": {"candidate-b": {"decision": "optional"}},
            },
            "stem-a-duplicate": {"role": "percussion", "candidates": {}},
        }
    }
    return catalog, current, soundfont


def _stem(stem_id: str, role: str, source: Path, candidate_id: str, midi: Path) -> dict:
    return {
        "stem_id": stem_id,
        "role": role,
        "source_path": str(source.resolve()),
        "source": _record(source),
        "candidates": [
            {
                "candidate_id": candidate_id,
                "midi_path": str(midi.resolve()),
                "midi": _record(midi),
                "audition_blocked": False,
                "process": "test-process",
            }
        ],
    }


def _write_midi(path: Path, *, pitch: int, program: int) -> None:
    write_midi_file(
        path,
        [
            MidiTrack(
                "Fixture",
                0,
                program,
                [NoteEvent(start=0.0, end=11.0, pitch=pitch, velocity=88)],
            )
        ],
        bpm=120.0,
    )


def _render_preview(_midi_path: Path, wav_path: Path, **_kwargs: object) -> None:
    _write_pcm_wav(Path(wav_path), sample_rate=16_000, channels=2, frames=48_000)


def _write_pcm_wav(path: Path, *, sample_rate: int, channels: int, frames: int) -> None:
    sample = int(0.25 * 32767).to_bytes(2, "little", signed=True)
    with wave.open(str(path), "wb") as destination:
        destination.setnchannels(channels)
        destination.setsampwidth(2)
        destination.setframerate(sample_rate)
        destination.writeframes(sample * channels * frames)


def _record(path: Path) -> dict:
    return {
        "path": str(path.resolve()),
        "name": path.name,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
