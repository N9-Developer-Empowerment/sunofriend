from __future__ import annotations

import copy
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
    ARRANGEMENT_SELECTION_SCHEMA,
    DECODED_ARRANGEMENT_LOOP_SCHEMA,
    WorkbenchArtifacts,
    decoded_arrangement_selection_manifest,
)


class WorkbenchDecodedArrangementSelectionTests(unittest.TestCase):
    def test_manifest_is_canonical_path_free_and_context_neutral(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            catalog, current, _soundfont = _catalog(Path(temporary))

            manifest = decoded_arrangement_selection_manifest(catalog, current)

            self.assertEqual(manifest["schema"], ARRANGEMENT_SELECTION_SCHEMA)
            self.assertEqual(len(manifest["sources"]), 2)
            self.assertEqual(len(manifest["selected_midi"]), 2)
            self.assertEqual(
                manifest["sources"][0]["stem_ids"],
                ["stem-a", "stem-a-duplicate"],
            )
            self.assertEqual(
                manifest["sources"][0]["roles"],
                ["bass", "percussion"],
            )
            source_ids = [item["track_id"] for item in manifest["sources"]]
            midi_ids = [item["track_id"] for item in manifest["selected_midi"]]
            self.assertEqual(manifest["groups"]["source-only"], source_ids)
            self.assertEqual(manifest["groups"]["selected-midi"], midi_ids)
            self.assertEqual(manifest["groups"]["hybrid"], source_ids + midi_ids)
            self.assertEqual(manifest["groups"]["main-only"], [midi_ids[0]])
            self.assertEqual(
                [item["role"] for item in manifest["selected_midi"]],
                ["bass", "pluck"],
            )
            serialized = json.dumps(manifest, sort_keys=True)
            self.assertNotIn(str(temporary), serialized)
            self.assertNotIn("private", serialized)
            self.assertNotIn("context", serialized)
            self.assertNotIn("process", serialized)

            context_only = copy.deepcopy(current)
            first = catalog["stems"][0]["candidates"][0]["candidate_id"]
            context_only["stems"][catalog["stems"][0]["stem_id"]]["candidates"][first][
                "context"
            ] = "full_mix"
            context_only["stems"][catalog["stems"][0]["stem_id"]]["candidates"][first][
                "notes"
            ] = "different private note"
            self.assertEqual(
                decoded_arrangement_selection_manifest(catalog, context_only)[
                    "selection_manifest_sha256"
                ],
                manifest["selection_manifest_sha256"],
            )

            changed_role = copy.deepcopy(current)
            changed_role["stems"][catalog["stems"][0]["stem_id"]]["role"] = "synth bass"
            self.assertNotEqual(
                decoded_arrangement_selection_manifest(catalog, changed_role)[
                    "selection_manifest_sha256"
                ],
                manifest["selection_manifest_sha256"],
            )

            inconsistent = copy.deepcopy(catalog)
            inconsistent["stems"][2]["source"]["bytes"] += 1
            with self.assertRaisesRegex(
                ValueError, "duplicate source hash has inconsistent byte counts"
            ):
                decoded_arrangement_selection_manifest(inconsistent, current)

    def test_role_override_has_its_own_neutral_preview_cache_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, _current, soundfont = _catalog(root)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_render_preview,
            ) as renderer:
                default = artifacts.render_candidate_preview(
                    catalog, stem["stem_id"], candidate["candidate_id"]
                )
                bass = artifacts.render_candidate_preview(
                    catalog,
                    stem["stem_id"],
                    candidate["candidate_id"],
                    role_override="bass",
                )

            self.assertEqual(renderer.call_count, 2)
            self.assertEqual(default["role"], "keys")
            self.assertEqual(default["program"], 4)
            self.assertEqual(bass["role"], "bass")
            self.assertEqual(bass["program"], 33)
            self.assertNotEqual(default["cache_key"], bass["cache_key"])
            self.assertEqual(
                artifacts.cached_candidate_preview(
                    catalog,
                    stem["stem_id"],
                    candidate["candidate_id"],
                    role_override="bass",
                )["cache_key"],
                bass["cache_key"],
            )

    def test_stale_empty_oversized_and_too_many_track_requests_fail_early(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, soundfont = _catalog(root)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            manifest = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )
            with self.assertRaisesRegex(ValueError, "selection changed"):
                artifacts.prepare_decoded_arrangement_loop(
                    catalog, current, "0" * 64, 0.0, 1.0
                )
            with self.assertRaisesRegex(ValueError, "between 0.5 and 15.0"):
                artifacts.prepare_decoded_arrangement_loop(
                    catalog,
                    current,
                    manifest["selection_manifest_sha256"],
                    0.0,
                    0.49,
                )

            empty = {"stems": {}}
            empty_manifest = decoded_arrangement_selection_manifest(catalog, empty)
            with self.assertRaisesRegex(ValueError, "at least one candidate"):
                artifacts.prepare_decoded_arrangement_loop(
                    catalog,
                    empty,
                    empty_manifest["selection_manifest_sha256"],
                    0.0,
                    1.0,
                )

            crowded_catalog, crowded_current = _crowded_selection(catalog, current)
            crowded_manifest = decoded_arrangement_selection_manifest(
                crowded_catalog, crowded_current
            )
            with self.assertRaisesRegex(ValueError, "at most 24"):
                artifacts.prepare_decoded_arrangement_loop(
                    crowded_catalog,
                    crowded_current,
                    crowded_manifest["selection_manifest_sha256"],
                    0.0,
                    1.0,
                )

            oversized = copy.deepcopy(catalog)
            oversized_source_sha256 = oversized["stems"][0]["source"]["sha256"]
            for stem in oversized["stems"]:
                if stem["source"]["sha256"] == oversized_source_sha256:
                    stem["source"]["bytes"] = module._DECODED_LOOP_MAXIMUM_INPUT_BYTES
            oversized_manifest = decoded_arrangement_selection_manifest(
                oversized, current
            )
            with (
                patch.object(
                    module,
                    "_decoded_audio_modules",
                    side_effect=AssertionError("audio modules must not load"),
                ) as audio_modules,
                patch.object(
                    artifacts,
                    "render_candidate_preview",
                    side_effect=AssertionError("preview must not render"),
                ) as renderer,
            ):
                with self.assertRaisesRegex(ValueError, "2 GiB aggregate"):
                    artifacts.prepare_decoded_arrangement_loop(
                        oversized,
                        current,
                        oversized_manifest["selection_manifest_sha256"],
                        0.0,
                        1.0,
                    )
            audio_modules.assert_not_called()
            renderer.assert_not_called()


@unittest.skipUnless(
    importlib.util.find_spec("numpy") and importlib.util.find_spec("soundfile"),
    "decoded arrangement audio tests require numpy and soundfile",
)
class WorkbenchDecodedArrangementArtifactTests(unittest.TestCase):
    def test_byte_identical_selected_midi_remain_distinct_role_lanes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, soundfont = _catalog(root)
            first_candidate = catalog["stems"][0]["candidates"][0]
            second_candidate = catalog["stems"][1]["candidates"][0]
            first_midi = Path(first_candidate["midi_path"])
            second_midi = Path(second_candidate["midi_path"])
            second_midi.write_bytes(first_midi.read_bytes())
            second_candidate["midi"] = _record(second_midi)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )

            selected = selection["selected_midi"]
            self.assertEqual(selected[0]["midi_sha256"], selected[1]["midi_sha256"])
            self.assertNotEqual(selected[0]["track_id"], selected[1]["track_id"])
            self.assertEqual([item["role"] for item in selected], ["bass", "pluck"])
            self.assertEqual(
                selection["groups"]["selected-midi"],
                [item["track_id"] for item in selected],
            )
            self.assertEqual(
                selection["groups"]["main-only"],
                [selected[0]["track_id"]],
            )

            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_render_preview,
            ) as renderer:
                arrangement = artifacts.prepare_decoded_arrangement_loop(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                    0.0,
                    1.0,
                )

            self.assertEqual(renderer.call_count, 2)
            midi_tracks = [
                track
                for track in arrangement["tracks"]
                if track["kind"] == "selected_midi"
            ]
            self.assertEqual(
                [track["track_id"] for track in midi_tracks],
                [item["track_id"] for item in selected],
            )
            self.assertEqual(
                [track["role"] for track in midi_tracks],
                ["bass", "pluck"],
            )
            bass_preview = artifacts.cached_candidate_preview(
                catalog,
                "stem-a",
                "candidate-a",
                role_override="bass",
            )
            pluck_preview = artifacts.cached_candidate_preview(
                catalog,
                "stem-b",
                "candidate-b",
                role_override="pluck",
            )
            self.assertIsNotNone(bass_preview)
            self.assertIsNotNone(pluck_preview)
            self.assertNotEqual(
                bass_preview["cache_key"],
                pluck_preview["cache_key"],
            )
            self.assertNotEqual(bass_preview["program"], pluck_preview["program"])

    def test_exact_twenty_four_track_boundary_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, soundfont = _catalog(root)
            catalog, current = _crowded_selection(
                catalog, current, candidate_count=21
            )
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )
            self.assertEqual(len(selection["sources"]), 2)
            self.assertEqual(len(selection["selected_midi"]), 22)

            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_render_preview,
            ):
                arrangement = artifacts.prepare_decoded_arrangement_loop(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                    0.0,
                    1.0,
                )

            self.assertEqual(len(arrangement["tracks"]), 24)
            self.assertEqual(len(arrangement["groups"]["hybrid"]), 24)

    def test_build_is_private_deterministic_padded_and_tamper_rebuilt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, soundfont = _catalog(root)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )
            original_midis = {
                Path(candidate["midi_path"]): _sha256(Path(candidate["midi_path"]))
                for stem in catalog["stems"]
                for candidate in stem["candidates"]
            }

            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_render_preview,
            ) as renderer:
                first = artifacts.prepare_decoded_arrangement_loop(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                    0.25,
                    1.25,
                )
                second = artifacts.prepare_decoded_arrangement_loop(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                    0.25000001,
                    1.25000001,
                )

            self.assertEqual(renderer.call_count, 2)
            self.assertEqual(first["schema"], DECODED_ARRANGEMENT_LOOP_SCHEMA)
            self.assertFalse(first["cache_hit"])
            self.assertTrue(second["cache_hit"])
            self.assertEqual(first["cache_key"], second["cache_key"])
            self.assertEqual(first["groups"], selection["groups"])
            self.assertEqual(len(first["tracks"]), 4)
            self.assertEqual(
                [track["kind"] for track in first["tracks"]],
                ["source", "source", "selected_midi", "selected_midi"],
            )
            self.assertEqual(
                [track.get("role") for track in first["tracks"][-2:]],
                ["bass", "pluck"],
            )
            self.assertTrue(
                any(track["silence_padded_frames"] > 0 for track in first["tracks"])
            )
            self.assertTrue(all(value is False for value in first["effects"].values()))

            cache_dir = Path(first["tracks"][0]["audio"]["path"]).parent
            manifest_path = cache_dir / "manifest.json"
            serialized = manifest_path.read_text(encoding="utf-8")
            self.assertNotIn(str(root), serialized)
            self.assertEqual(stat.S_IMODE(cache_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(manifest_path.stat().st_mode), 0o600)
            self.assertFalse(
                any(path.name.startswith(".verified-") for path in cache_dir.iterdir())
            )
            for track in first["tracks"]:
                self.assertEqual(
                    stat.S_IMODE(Path(track["audio"]["path"]).stat().st_mode),
                    0o600,
                )
            for midi_path, digest in original_midis.items():
                self.assertEqual(_sha256(midi_path), digest)

            damaged = Path(first["tracks"][1]["audio"]["path"])
            expected_sha256 = first["tracks"][1]["audio"]["sha256"]
            damaged.write_bytes(b"tampered arrangement cache")
            with patch.object(
                artifacts,
                "render_candidate_preview",
                side_effect=AssertionError(
                    "verified neutral previews should be reused"
                ),
            ):
                rebuilt = artifacts.prepare_decoded_arrangement_loop(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                    0.25,
                    1.25,
                )
            self.assertFalse(rebuilt["cache_hit"])
            self.assertEqual(rebuilt["tracks"][1]["audio"]["sha256"], expected_sha256)

    def test_decode_reads_verified_snapshots_and_shared_cache_quota_applies(
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
            real_reader = module._read_padded_audio_window
            seen: list[Path] = []

            def observe_snapshot(np, soundfile, path, **kwargs):
                seen.append(Path(path))
                return real_reader(np, soundfile, path, **kwargs)

            with (
                patch(
                    "sunofriend.workbench_artifacts.render_midi_to_wav",
                    side_effect=_render_preview,
                ),
                patch(
                    "sunofriend.workbench_artifacts._read_padded_audio_window",
                    side_effect=observe_snapshot,
                ),
            ):
                arrangement = artifacts.prepare_decoded_arrangement_loop(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                    0.0,
                    1.0,
                )
            self.assertEqual(len(seen), 4)
            self.assertTrue(
                all(path.name.startswith(".verified-input-") for path in seen)
            )
            self.assertFalse(
                any(
                    path.name.startswith(".verified-input-")
                    for path in Path(
                        arrangement["tracks"][0]["audio"]["path"]
                    ).parent.iterdir()
                )
            )

            first_stem = catalog["stems"][0]
            first_candidate = first_stem["candidates"][0]
            with patch.object(module, "_DECODED_LOOP_CACHE_MAXIMUM_ENTRIES", 1):
                stem_loop = artifacts.prepare_decoded_stem_loop(
                    catalog,
                    first_stem["stem_id"],
                    [first_candidate["candidate_id"]],
                    1.0,
                    2.0,
                )
            self.assertFalse(
                Path(arrangement["tracks"][0]["audio"]["path"]).parent.exists()
            )
            self.assertTrue(
                Path(stem_loop["tracks"][0]["audio"]["path"]).parent.exists()
            )

    def test_output_limit_fails_without_publishing_partial_cache(self) -> None:
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
                patch.object(module, "_DECODED_LOOP_MAXIMUM_OUTPUT_BYTES", 128),
            ):
                with self.assertRaisesRegex(ValueError, "64 MiB limit"):
                    artifacts.prepare_decoded_arrangement_loop(
                        catalog,
                        current,
                        selection["selection_manifest_sha256"],
                        0.0,
                        1.0,
                    )
            cache_root = artifacts.root / "decoded-arrangement-loops"
            self.assertFalse(
                cache_root.exists()
                and any(path.is_dir() for path in cache_root.iterdir())
            )


def _catalog(root: Path) -> tuple[dict, dict, Path]:
    source_a = root / "source-a.wav"
    source_b = root / "source-b.wav"
    _write_pcm_wav(source_a, sample_rate=8_000, channels=1, frames=16_000)
    _write_pcm_wav(source_b, sample_rate=16_000, channels=2, frames=12_000)
    midi_a = root / "candidate-a.mid"
    midi_b = root / "candidate-b.mid"
    _write_midi(midi_a, pitch=40, program=4)
    _write_midi(midi_b, pitch=67, program=48)
    soundfont = root / "test.sf2"
    soundfont.write_bytes(b"decoded-arrangement-test-soundfont")
    stems = [
        _stem("stem-a", "keys", source_a, "candidate-a", midi_a),
        _stem("stem-b", "strings", source_b, "candidate-b", midi_b),
        {
            "stem_id": "stem-a-duplicate",
            "role": "percussion",
            "source_path": str(source_a.resolve()),
            "source": _record(source_a),
            "candidates": [],
        },
    ]
    catalog = {
        "project_id": "decoded-arrangement-project",
        "setup": {"bpm": 120.0},
        "stems": stems,
    }
    current = {
        "stems": {
            "stem-a": {
                "role": "bass",
                "main_candidate_id": "candidate-a",
                "candidates": {
                    "candidate-a": {
                        "decision": "main",
                        "context": "solo",
                        "notes": "private bass note",
                    }
                },
            },
            "stem-b": {
                "role": "pluck",
                "main_candidate_id": None,
                "candidates": {
                    "candidate-b": {
                        "decision": "optional",
                        "context": "full_mix",
                    }
                },
            },
            "stem-a-duplicate": {"role": "percussion", "candidates": {}},
        },
        "event_count": 2,
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
                "process": "private-test-process",
            }
        ],
    }


def _crowded_selection(
    catalog: dict,
    current: dict,
    *,
    candidate_count: int = 24,
) -> tuple[dict, dict]:
    crowded_catalog = copy.deepcopy(catalog)
    crowded_current = copy.deepcopy(current)
    stem = crowded_catalog["stems"][0]
    template = stem["candidates"][0]
    stem["candidates"] = []
    decisions = {}
    for index in range(candidate_count):
        candidate_id = f"crowded-candidate-{index:02d}"
        stem["candidates"].append({**template, "candidate_id": candidate_id})
        decisions[candidate_id] = {"decision": "main" if index == 0 else "optional"}
    crowded_current["stems"][stem["stem_id"]] = {
        "role": "bass",
        "main_candidate_id": "crowded-candidate-00",
        "candidates": decisions,
    }
    return crowded_catalog, crowded_current


def _write_midi(path: Path, *, pitch: int, program: int) -> None:
    write_midi_file(
        path,
        [
            MidiTrack(
                "Fixture",
                0,
                program,
                [NoteEvent(start=0.0, end=2.0, pitch=pitch, velocity=88)],
            )
        ],
        bpm=120.0,
    )


def _render_preview(_midi_path: Path, wav_path: Path, **_kwargs: object) -> None:
    _write_pcm_wav(Path(wav_path), sample_rate=16_000, channels=2, frames=12_000)


def _write_pcm_wav(path: Path, *, sample_rate: int, channels: int, frames: int) -> None:
    sample = int(0.25 * 32767).to_bytes(2, "little", signed=True)
    frame = sample * channels
    with wave.open(str(path), "wb") as destination:
        destination.setnchannels(channels)
        destination.setsampwidth(2)
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


if __name__ == "__main__":
    unittest.main()
