from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
import wave
import zipfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.workbench_artifacts import WorkbenchArtifacts
from sunofriend.workbench_catalog import build_workbench_catalog
from sunofriend.workbench_mix import BALANCED_MIX_POLICY, garageband_mix_recipe
from sunofriend.workbench_store import WorkbenchStore


_AUDIO_DEPENDENCIES_AVAILABLE = bool(
    importlib.util.find_spec("numpy") and importlib.util.find_spec("soundfile")
)


@unittest.skipUnless(
    _AUDIO_DEPENDENCIES_AVAILABLE,
    "balanced arrangement tests require numpy and soundfile",
)
class WorkbenchBalancedArrangementTests(unittest.TestCase):
    def test_missing_balanced_cache_skips_all_selection_and_input_work(self) -> None:
        for cache_state in ("absent", "empty"):
            with self.subTest(cache_state=cache_state):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    artifacts = WorkbenchArtifacts(root / "artifacts")
                    if cache_state == "empty":
                        (artifacts.root / "balanced-arrangements").mkdir()

                    with (
                        patch(
                            "sunofriend.workbench_artifacts."
                            "_decoded_arrangement_selection"
                        ) as selection_builder,
                        patch.object(
                            artifacts, "_verify_selection"
                        ) as selection_verifier,
                        patch.object(
                            artifacts, "_verify_catalog_record"
                        ) as input_verifier,
                        patch.object(
                            artifacts, "_available_soundfont_sha256"
                        ) as soundfont_verifier,
                        patch.object(
                            artifacts, "cached_candidate_preview"
                        ) as preview_verifier,
                        patch.object(
                            artifacts, "render_candidate_preview"
                        ) as preview_renderer,
                    ):
                        result = artifacts.cached_balanced_arrangement({}, {})

                    self.assertIsNone(result)
                    selection_builder.assert_not_called()
                    selection_verifier.assert_not_called()
                    input_verifier.assert_not_called()
                    soundfont_verifier.assert_not_called()
                    preview_verifier.assert_not_called()
                    preview_renderer.assert_not_called()

    def test_irrelevant_balanced_cache_skips_large_input_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _catalog(root)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"balanced-test-soundfont")
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "main",
                    "context": "full_mix",
                    "problem_tags": [],
                },
            )
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts",
                soundfont_path=soundfont,
            )
            stale_root = artifacts.root / "balanced-arrangements" / ("0" * 64)
            stale_root.mkdir(parents=True)
            (stale_root / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema": "sunofriend.workbench-balanced-arrangement.v1",
                        "project_id": catalog["project_id"],
                        "selection_manifest_sha256": "f" * 64,
                        "bpm": 120.0,
                        "policy": "source-referenced-selected-midi-balance-v1",
                        "render_horizon_policy": (
                            "longest-verified-source-stem-v1"
                        ),
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(artifacts, "_verify_selection") as selection_verifier,
                patch.object(
                    artifacts, "_verify_catalog_record"
                ) as input_verifier,
                patch.object(
                    artifacts, "_available_soundfont_sha256"
                ) as soundfont_verifier,
                patch.object(
                    artifacts, "cached_candidate_preview"
                ) as preview_verifier,
                patch.object(
                    artifacts, "render_candidate_preview"
                ) as preview_renderer,
            ):
                result = artifacts.cached_balanced_arrangement(
                    catalog,
                    store.current_state(catalog),
                )

            self.assertIsNone(result)
            selection_verifier.assert_not_called()
            input_verifier.assert_not_called()
            soundfont_verifier.assert_not_called()
            preview_verifier.assert_not_called()
            preview_renderer.assert_not_called()

    def test_non_object_balanced_manifest_is_skipped_without_breaking_project_read(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, artifacts, _selection_sha256 = (
                _balanced_fixture(root)
            )
            corrupt_root = (
                artifacts.root / "balanced-arrangements" / ("0" * 64)
            )
            corrupt_root.mkdir(parents=True)
            (corrupt_root / "manifest.json").write_text(
                "[]\n",
                encoding="utf-8",
            )

            self.assertIsNone(
                artifacts.cached_balanced_arrangement(catalog, current)
            )

    def test_balanced_arrangement_is_separate_cached_and_path_free(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _catalog(root)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"balanced-test-soundfont")
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            original_midi = {}
            for stem in catalog["stems"]:
                candidate = stem["candidates"][0]
                original_midi[str(candidate["candidate_id"])] = Path(
                    str(candidate["midi_path"])
                ).read_bytes()
                store.append(
                    catalog,
                    {
                        "event_type": "candidate_decision",
                        "stem_id": stem["stem_id"],
                        "candidate_id": candidate["candidate_id"],
                        "decision": "main",
                        "context": "full_mix",
                        "problem_tags": [],
                        "notes": "private listening note",
                    },
                )
            current = store.current_state(catalog)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts",
                soundfont_path=soundfont,
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )
            manifest_sha256 = selection["selection_manifest_sha256"]

            self.assertIsNone(
                artifacts.cached_balanced_arrangement(catalog, current)
            )
            self.assertIsNone(artifacts.cached_arrangement(catalog, current))
            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_render_preview,
            ) as renderer:
                first = artifacts.render_balanced_arrangement(
                    catalog,
                    current,
                    manifest_sha256,
                )
                second = artifacts.render_balanced_arrangement(
                    catalog,
                    current,
                    manifest_sha256,
                )

            self.assertEqual(renderer.call_count, 2)
            self.assertFalse(first["cache_hit"])
            self.assertTrue(second["cache_hit"])
            self.assertEqual(
                first["schema"],
                "sunofriend.workbench-balanced-arrangement.v1",
            )
            self.assertEqual(
                first["policy"],
                BALANCED_MIX_POLICY,
            )
            horizon = first["render_horizon"]
            self.assertEqual(horizon["policy"], "longest-verified-source-stem-v1")
            self.assertEqual(horizon["sample_rate"], 16_000)
            self.assertEqual(horizon["output_frames"], 32_000)
            self.assertEqual(horizon["maximum_source_frames"], 32_000)
            self.assertEqual(horizon["maximum_neutral_preview_frames"], 32_000)
            self.assertEqual(horizon["excluded_neutral_preview_tail_frames"], 0)
            self.assertEqual(horizon["padded_output_frames"], 0)
            self.assertEqual(len(horizon["sources"]), 2)
            self.assertEqual(len(horizon["lanes"]), 2)
            self.assertTrue(
                all(row["owns_output_horizon"] for row in horizon["sources"])
            )
            self.assertTrue(
                all(
                    row["neutral_preview_frames"] == 32_000
                    and row["excluded_neutral_preview_tail_frames"] == 0
                    and row["padded_output_frames"] == 0
                    for row in horizon["lanes"]
                )
            )
            self.assertEqual(first["mix_report"]["frames"], 32_000)
            self.assertEqual(first["selection_manifest_sha256"], manifest_sha256)
            self.assertFalse(first["mastered"])
            self.assertTrue(Path(first["preview"]["path"]).is_file())
            self.assertTrue(Path(first["report"]["path"]).is_file())
            self.assertTrue(Path(first["recipe"]["path"]).is_file())
            receipt = json.loads(
                Path(first["report"]["path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(
                receipt["schema"],
                "sunofriend.workbench-balanced-mix-receipt.v1",
            )
            self.assertEqual(receipt["project_id"], catalog["project_id"])
            self.assertEqual(
                receipt["selection_manifest_sha256"],
                manifest_sha256,
            )
            self.assertEqual(receipt["renderer"], first["renderer"])
            self.assertEqual(receipt["render_horizon"], horizon)
            self.assertEqual(receipt["mix_report"], first["mix_report"])
            self.assertEqual(
                receipt["recipe"]["sha256"],
                first["recipe"]["sha256"],
            )
            self.assertNotIn("path", receipt["recipe"])
            self.assertEqual(first["mix_report"]["effects"], first["effects"])
            self.assertTrue(
                all(value is False for value in first["effects"].values())
            )
            self.assertLessEqual(
                first["mix_report"]["output"]["post_master"][
                    "sample_peak_dbfs"
                ],
                -0.999,
            )
            self.assertEqual(
                first["mix_report"]["output"]["post_master"][
                    "full_scale_sample_count"
                ],
                0,
            )
            self.assertLess(
                next(
                    lane
                    for lane in first["mix_report"]["lanes"]
                    if lane["role"] == "kick"
                )["garageband_track_trim_db"],
                0.0,
            )

            manifest_path = Path(first["preview"]["path"]).parent / "manifest.json"
            manifest_text = manifest_path.read_text(encoding="utf-8")
            report_text = Path(first["report"]["path"]).read_text(encoding="utf-8")
            self.assertNotIn(str(root), manifest_text)
            self.assertNotIn(str(root), report_text)
            self.assertNotIn("private listening note", manifest_text)
            self.assertNotIn("private listening note", report_text)
            self.assertIsNone(artifacts.cached_arrangement(catalog, current))
            cached = artifacts.cached_balanced_arrangement(catalog, current)
            self.assertIsNotNone(cached)
            self.assertTrue(cached["cache_hit"])

            for stem in catalog["stems"]:
                candidate = stem["candidates"][0]
                self.assertEqual(
                    Path(str(candidate["midi_path"])).read_bytes(),
                    original_midi[str(candidate["candidate_id"])],
                )

            Path(first["preview"]["path"]).write_bytes(b"corrupt")
            self.assertIsNone(
                artifacts.cached_balanced_arrangement(catalog, current)
            )
            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_render_preview,
            ) as recovery_renderer:
                recovered = artifacts.render_balanced_arrangement(
                    catalog,
                    current,
                    manifest_sha256,
                )
            self.assertEqual(recovery_renderer.call_count, 0)
            self.assertFalse(recovered["cache_hit"])
            self.assertNotEqual(
                hashlib.sha256(b"corrupt").hexdigest(),
                recovered["preview"]["sha256"],
            )

    def test_gate_membership_change_after_maximum_boost_remains_cacheable(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Gate Song-D minor-120bpm-440hz"
            candidates = root / "gate-candidates"
            project.mkdir()
            candidates.mkdir()
            source = (
                project
                / "Gate Song-keys-D minor-120bpm-440hz.wav"
            )
            _write_level_blocks(source, levels_dbfs=(-65.0, -72.0, -72.0))
            _write_midi(
                candidates / "keys-listened.mid",
                channel=0,
                pitch=60,
            )
            catalog = build_workbench_catalog(
                project,
                candidate_roots=[candidates],
            )
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"balanced-test-soundfont")
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "main",
                    "context": "full_mix",
                    "problem_tags": [],
                },
            )
            current = store.current_state(catalog)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts",
                soundfont_path=soundfont,
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog,
                current,
            )

            def render_gate_fixture(
                _midi_path: Path,
                wav_path: Path,
                **_kwargs: object,
            ) -> None:
                _write_level_blocks(
                    Path(wav_path),
                    levels_dbfs=(-65.0, -72.0, -72.0),
                )

            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=render_gate_fixture,
            ):
                result = artifacts.render_balanced_arrangement(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                )

            output = result["mix_report"]["output"]
            self.assertEqual(output["master_output_gain_db"], 12.0)
            self.assertEqual(
                output["normalisation_limit"],
                "maximum_positive_boost",
            )
            self.assertEqual(
                output["pre_master"]["active_block_count"],
                1,
            )
            self.assertEqual(
                output["post_master"]["active_block_count"],
                3,
            )
            self.assertNotAlmostEqual(
                output["post_master"]["gated_rms_dbfs"],
                (
                    output["pre_master"]["gated_rms_dbfs"]
                    + output["master_output_gain_db"]
                ),
                delta=0.01,
            )

            fresh = WorkbenchArtifacts(
                artifacts.root,
                soundfont_path=soundfont,
            )
            cached = fresh.cached_balanced_arrangement(catalog, current)
            self.assertIsNotNone(cached)
            self.assertTrue(cached["cache_hit"])

    def test_balanced_arrangement_uses_source_song_horizon_not_preview_tail(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _catalog(root)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"balanced-test-soundfont")
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            for stem in catalog["stems"]:
                candidate = stem["candidates"][0]
                store.append(
                    catalog,
                    {
                        "event_type": "candidate_decision",
                        "stem_id": stem["stem_id"],
                        "candidate_id": candidate["candidate_id"],
                        "decision": "main",
                        "context": "full_mix",
                        "problem_tags": [],
                    },
                )
            current = store.current_state(catalog)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts",
                soundfont_path=soundfont,
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )

            def render_with_tail(
                midi_path: Path,
                wav_path: Path,
                **_kwargs: object,
            ) -> None:
                payload = Path(midi_path).read_bytes()
                amplitude = 0.8 if b"Kick" in payload else 0.12
                _write_wav(Path(wav_path), amplitude=amplitude, seconds=3.0)

            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=render_with_tail,
            ):
                result = artifacts.render_balanced_arrangement(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                )

            self.assertEqual(result["mix_report"]["frames"], 32_000)
            horizon = result["render_horizon"]
            self.assertEqual(horizon["policy"], "longest-verified-source-stem-v1")
            self.assertEqual(horizon["sample_rate"], 16_000)
            self.assertEqual(horizon["output_frames"], 32_000)
            self.assertEqual(horizon["maximum_source_frames"], 32_000)
            self.assertEqual(horizon["maximum_neutral_preview_frames"], 48_000)
            self.assertEqual(
                horizon["excluded_neutral_preview_tail_frames"],
                16_000,
            )
            self.assertEqual(horizon["padded_output_frames"], 0)
            self.assertTrue(
                all(
                    row["neutral_preview_frames"] == 48_000
                    and row["excluded_neutral_preview_tail_frames"] == 16_000
                    and row["padded_output_frames"] == 0
                    for row in horizon["lanes"]
                )
            )
            with wave.open(result["preview"]["path"], "rb") as preview:
                self.assertEqual(preview.getnframes(), 32_000)

    def test_exact_maximum_boost_boundary_builds_and_reuses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Boundary Song-D minor-120bpm-440hz"
            candidates = root / "boundary-candidates"
            project.mkdir()
            candidates.mkdir()
            amplitude = 10.0 ** (-30.0 / 20.0)
            _write_float_constant(
                project / "Boundary Song-keys-D minor-120bpm-440hz.wav",
                amplitude=amplitude,
            )
            _write_midi(candidates / "keys-listened.mid", channel=0, pitch=60)
            catalog = build_workbench_catalog(
                project,
                candidate_roots=[candidates],
            )
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"balanced-test-soundfont")
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "main",
                    "context": "full_mix",
                    "problem_tags": [],
                },
            )
            current = store.current_state(catalog)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts",
                soundfont_path=soundfont,
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog,
                current,
            )

            def render_boundary(
                _midi_path: Path,
                wav_path: Path,
                **_kwargs: object,
            ) -> None:
                _write_float_constant(Path(wav_path), amplitude=amplitude)

            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=render_boundary,
            ):
                result = artifacts.render_balanced_arrangement(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                )

            output = result["mix_report"]["output"]
            self.assertEqual(output["pre_master"]["gated_rms_dbfs"], -30.0)
            self.assertEqual(output["raw_normalisation_gain_db"], 12.0)
            self.assertEqual(output["requested_normalisation_gain_db"], 12.0)
            self.assertEqual(output["master_output_gain_db"], 12.0)
            self.assertIsNone(output["normalisation_limit"])
            fresh = WorkbenchArtifacts(
                artifacts.root,
                soundfont_path=soundfont,
            )
            cached = fresh.cached_balanced_arrangement(catalog, current)
            self.assertIsNotNone(cached)
            self.assertTrue(cached["cache_hit"])

    def test_exact_drum_guard_boundary_builds_and_reuses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Guard Song-D minor-120bpm-440hz"
            candidates = root / "guard-candidates"
            project.mkdir()
            candidates.mkdir()
            # The tiny offset survives FLOAT32 encoding while the public
            # six-decimal overlap delta lands exactly on +16 dB. That makes the
            # required guard exactly −18 dB instead of one micro-dB beyond it.
            levels = {"kick": -14.0000004, "keys": -30.0}
            for role, level_dbfs in levels.items():
                _write_float_constant(
                    project / (
                        f"Guard Song-{role}-D minor-120bpm-440hz.wav"
                    ),
                    amplitude=10.0 ** (level_dbfs / 20.0),
                )
                _write_midi(
                    candidates / f"{role}-listened.mid",
                    channel=9 if role == "kick" else 0,
                    pitch=36 if role == "kick" else 60,
                )
            catalog = build_workbench_catalog(
                project,
                candidate_roots=[candidates],
            )
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"balanced-test-soundfont")
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            for stem in catalog["stems"]:
                candidate = stem["candidates"][0]
                store.append(
                    catalog,
                    {
                        "event_type": "candidate_decision",
                        "stem_id": stem["stem_id"],
                        "candidate_id": candidate["candidate_id"],
                        "decision": "main",
                        "context": "full_mix",
                        "problem_tags": [],
                    },
                )
            current = store.current_state(catalog)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts",
                soundfont_path=soundfont,
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog,
                current,
            )

            def render_guard_boundary(
                midi_path: Path,
                wav_path: Path,
                **_kwargs: object,
            ) -> None:
                payload = Path(midi_path).read_bytes().lower()
                role = "kick" if b"kick" in payload else "keys"
                _write_float_constant(
                    Path(wav_path),
                    amplitude=10.0 ** (levels[role] / 20.0),
                )

            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=render_guard_boundary,
            ):
                result = artifacts.render_balanced_arrangement(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                )

            drum_bus = result["mix_report"]["drum_bus"]
            self.assertEqual(drum_bus["required_guard_gain_db"], -18.0)
            self.assertEqual(drum_bus["guard_gain_db"], -18.0)
            self.assertFalse(drum_bus["guard_clamped"])
            fresh = WorkbenchArtifacts(
                artifacts.root,
                soundfont_path=soundfont,
            )
            cached = fresh.cached_balanced_arrangement(catalog, current)
            self.assertIsNotNone(cached)
            self.assertTrue(cached["cache_hit"])

    def test_longest_unselected_source_owns_horizon_and_is_snapshotted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _catalog(root, unselected_vocal_seconds=4.0)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"balanced-test-soundfont")
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            selected_stems = [
                stem for stem in catalog["stems"] if stem["candidates"]
            ]
            self.assertEqual(len(selected_stems), 2)
            self.assertEqual(len(catalog["stems"]), 3)
            for stem in selected_stems:
                candidate = stem["candidates"][0]
                store.append(
                    catalog,
                    {
                        "event_type": "candidate_decision",
                        "stem_id": stem["stem_id"],
                        "candidate_id": candidate["candidate_id"],
                        "decision": "main",
                        "context": "full_mix",
                        "problem_tags": [],
                    },
                )
            current = store.current_state(catalog)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts",
                soundfont_path=soundfont,
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog,
                current,
            )
            snapshot_labels: list[str] = []
            original_snapshot = (
                __import__(
                    "sunofriend.workbench_artifacts",
                    fromlist=["_write_verified_private_snapshot"],
                )._write_verified_private_snapshot
            )

            def observe_snapshot(
                source: Path,
                record: dict,
                destination: Path,
                *,
                label: str,
            ) -> Path:
                snapshot_labels.append(label)
                return original_snapshot(
                    source,
                    record,
                    destination,
                    label=label,
                )

            with (
                patch(
                    "sunofriend.workbench_artifacts.render_midi_to_wav",
                    side_effect=_render_preview,
                ),
                patch(
                    "sunofriend.workbench_artifacts."
                    "_write_verified_private_snapshot",
                    side_effect=observe_snapshot,
                ),
            ):
                result = artifacts.render_balanced_arrangement(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                )

            horizon = result["render_horizon"]
            self.assertEqual(horizon["output_frames"], 64_000)
            self.assertEqual(horizon["maximum_source_frames"], 64_000)
            self.assertEqual(len(horizon["sources"]), 3)
            self.assertEqual(len(horizon["lanes"]), 2)
            owner = next(
                row for row in horizon["sources"] if row["owns_output_horizon"]
            )
            self.assertIn("vocals", owner["roles"])
            self.assertEqual(owner["source_frames"], 64_000)
            self.assertTrue(
                all(row["padded_output_frames"] == 32_000 for row in horizon["lanes"])
            )
            self.assertEqual(snapshot_labels.count("source audio"), 3)
            self.assertEqual(
                len(
                    result["input_fingerprints"]["project_sources"]
                ),
                3,
            )
            self.assertEqual(
                len(result["mix_report"]["source_groups"]),
                2,
            )
            self.assertNotIn(
                owner["source_sha256"],
                {
                    row["source_sha256"]
                    for row in result["mix_report"]["source_groups"]
                },
            )

    def test_zero_frame_unselected_source_is_rejected_before_mix_build(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _catalog(root, unselected_vocal_seconds=0.0)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"balanced-test-soundfont")
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            for stem in catalog["stems"]:
                if not stem["candidates"]:
                    continue
                candidate = stem["candidates"][0]
                store.append(
                    catalog,
                    {
                        "event_type": "candidate_decision",
                        "stem_id": stem["stem_id"],
                        "candidate_id": candidate["candidate_id"],
                        "decision": "main",
                        "context": "full_mix",
                        "problem_tags": [],
                    },
                )
            current = store.current_state(catalog)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts",
                soundfont_path=soundfont,
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog,
                current,
            )

            with (
                patch(
                    "sunofriend.workbench_artifacts.render_midi_to_wav",
                    side_effect=_render_preview,
                ),
                patch(
                    "sunofriend.workbench_artifacts.build_balanced_midi_audition"
                ) as mix_builder,
                self.assertRaisesRegex(
                    ValueError,
                    "must contain at least one audio frame",
                ),
            ):
                artifacts.render_balanced_arrangement(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                )
            mix_builder.assert_not_called()

    def test_unselected_source_counts_toward_early_two_gib_input_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _catalog(root, unselected_vocal_seconds=4.0)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"balanced-test-soundfont")
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            for stem in catalog["stems"]:
                if not stem["candidates"]:
                    stem["source"]["bytes"] = 2 * 1024 * 1024 * 1024
                    continue
                candidate = stem["candidates"][0]
                store.append(
                    catalog,
                    {
                        "event_type": "candidate_decision",
                        "stem_id": stem["stem_id"],
                        "candidate_id": candidate["candidate_id"],
                        "decision": "main",
                        "context": "full_mix",
                        "problem_tags": [],
                    },
                )
            current = store.current_state(catalog)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts",
                soundfont_path=soundfont,
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog,
                current,
            )
            with (
                patch(
                    "sunofriend.workbench_artifacts.render_midi_to_wav"
                ) as renderer,
                self.assertRaisesRegex(ValueError, "2 GiB"),
            ):
                artifacts.render_balanced_arrangement(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                )
            renderer.assert_not_called()

    def test_mixed_preview_lengths_report_each_lane_padding_and_exclusion(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _catalog(root)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"balanced-test-soundfont")
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            for stem in catalog["stems"]:
                candidate = stem["candidates"][0]
                store.append(
                    catalog,
                    {
                        "event_type": "candidate_decision",
                        "stem_id": stem["stem_id"],
                        "candidate_id": candidate["candidate_id"],
                        "decision": "main",
                        "context": "full_mix",
                        "problem_tags": [],
                    },
                )
            current = store.current_state(catalog)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts",
                soundfont_path=soundfont,
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog,
                current,
            )

            def render_mixed_lengths(
                midi_path: Path,
                wav_path: Path,
                **_kwargs: object,
            ) -> None:
                payload = Path(midi_path).read_bytes()
                if b"Kick" in payload:
                    _write_wav(Path(wav_path), amplitude=0.5, seconds=1.0)
                else:
                    _write_wav(Path(wav_path), amplitude=0.12, seconds=3.0)

            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=render_mixed_lengths,
            ):
                result = artifacts.render_balanced_arrangement(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                )

            horizon_by_index = {
                row["selection_index"]: row
                for row in result["render_horizon"]["lanes"]
            }
            index_by_role = {
                row["role"]: row["selection_index"]
                for row in result["input_fingerprints"]["selected_lanes"]
            }
            kick = horizon_by_index[index_by_role["kick"]]
            keys = horizon_by_index[index_by_role["keys"]]
            self.assertEqual(kick["neutral_preview_frames"], 16_000)
            self.assertEqual(kick["padded_output_frames"], 16_000)
            self.assertEqual(kick["excluded_neutral_preview_tail_frames"], 0)
            self.assertEqual(keys["neutral_preview_frames"], 48_000)
            self.assertEqual(keys["padded_output_frames"], 0)
            self.assertEqual(
                keys["excluded_neutral_preview_tail_frames"],
                16_000,
            )

    def test_same_role_optional_numbering_matches_pack_and_legacy_handoff(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _same_role_catalog(root)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"balanced-test-soundfont")
            stem = catalog["stems"][0]
            self.assertEqual(len(stem["candidates"]), 2)
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            for index, candidate in enumerate(stem["candidates"]):
                store.append(
                    catalog,
                    {
                        "event_type": "candidate_decision",
                        "stem_id": stem["stem_id"],
                        "candidate_id": candidate["candidate_id"],
                        "decision": "main" if index == 0 else "optional",
                        "context": "full_mix",
                        "problem_tags": [],
                    },
                )
            current = store.current_state(catalog)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts",
                soundfont_path=soundfont,
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog,
                current,
            )
            expected_members = [
                "MIDI/01-keys-main.mid",
                "MIDI/02-keys-optional.mid",
            ]
            self.assertEqual(
                [
                    row["garageband_pack_archive_member"]
                    for row in selection["selected_midi"]
                ],
                expected_members,
            )
            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_render_preview,
            ):
                balanced = artifacts.render_balanced_arrangement(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                )
                handoff = artifacts.build_garageband_handoff(catalog, current)
            self.assertEqual(
                [
                    lane["garageband_pack_archive_member"]
                    for lane in balanced["mix_report"]["lanes"]
                ],
                expected_members,
            )
            plan = artifacts.garageband_pack_plan(catalog, current)
            selected_items = [
                item for item in plan["items"] if item["kind"] == "selected_midi"
            ]
            self.assertEqual(
                [item["selection_index"] for item in selected_items],
                [1, 2],
            )
            self.assertEqual(
                [
                    item["garageband_pack_archive_member"]
                    for item in selected_items
                ],
                expected_members,
            )
            self.assertEqual(
                [item["archive_paths"][0] for item in selected_items],
                expected_members,
            )
            with zipfile.ZipFile(handoff["zip"]["path"]) as archive:
                self.assertTrue(set(expected_members).issubset(archive.namelist()))

    def test_manifest_and_receipt_tampering_fail_closed(self) -> None:
        tamper_kinds = (
            "unknown-path",
            "effects",
            "renderer",
            "selection",
            "horizon",
            "receipt",
        )
        for tamper_kind in tamper_kinds:
            with self.subTest(tamper_kind=tamper_kind):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    catalog = _catalog(root)
                    soundfont = root / "test.sf2"
                    soundfont.write_bytes(b"balanced-test-soundfont")
                    store = WorkbenchStore(root / "state" / "workbench.sqlite3")
                    stem = catalog["stems"][0]
                    candidate = stem["candidates"][0]
                    store.append(
                        catalog,
                        {
                            "event_type": "candidate_decision",
                            "stem_id": stem["stem_id"],
                            "candidate_id": candidate["candidate_id"],
                            "decision": "main",
                            "context": "full_mix",
                            "problem_tags": [],
                        },
                    )
                    current = store.current_state(catalog)
                    artifacts = WorkbenchArtifacts(
                        root / "state" / "artifacts",
                        soundfont_path=soundfont,
                    )
                    selection = artifacts.decoded_arrangement_selection_manifest(
                        catalog,
                        current,
                    )
                    with patch(
                        "sunofriend.workbench_artifacts.render_midi_to_wav",
                        side_effect=_render_preview,
                    ):
                        result = artifacts.render_balanced_arrangement(
                            catalog,
                            current,
                            selection["selection_manifest_sha256"],
                        )
                    cache_key = result["cache_key"]
                    manifest_path = (
                        Path(result["preview"]["path"]).parent / "manifest.json"
                    )
                    manifest = json.loads(
                        manifest_path.read_text(encoding="utf-8")
                    )
                    if tamper_kind == "unknown-path":
                        manifest["source_path"] = str(root / "private.wav")
                    elif tamper_kind == "effects":
                        manifest["effects"]["feedback_recorded"] = True
                    elif tamper_kind == "renderer":
                        manifest["renderer"]["backend"] = "forged renderer"
                    elif tamper_kind == "selection":
                        manifest["selection"][0]["selection_index"] = 2
                    elif tamper_kind == "horizon":
                        manifest["render_horizon"]["output_frames"] += 1
                    else:
                        receipt_path = Path(result["report"]["path"])
                        receipt = json.loads(
                            receipt_path.read_text(encoding="utf-8")
                        )
                        receipt["local_path"] = str(root / "private.wav")
                        receipt["receipt_sha256"] = _json_hash(
                            {
                                key: value
                                for key, value in receipt.items()
                                if key != "receipt_sha256"
                            }
                        )
                        receipt_path.write_text(
                            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8",
                        )
                        manifest["report"]["bytes"] = receipt_path.stat().st_size
                        manifest["report"]["sha256"] = _sha256(receipt_path)
                    manifest["manifest_sha256"] = _json_hash(
                        {
                            key: value
                            for key, value in manifest.items()
                            if key != "manifest_sha256"
                        }
                    )
                    manifest_path.write_text(
                        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )

                    self.assertIsNone(
                        artifacts._load_balanced_arrangement(cache_key)
                    )

    def test_self_rehashed_lane_trim_with_regenerated_recipe_fails_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _catalog_value, _current, artifacts, result = (
                _rendered_balanced_fixture(root)
            )
            cache_root, manifest, receipt = _balanced_cache_documents(result)
            manifest["mix_report"]["lanes"][0][
                "garageband_track_trim_db"
            ] += 9.0
            receipt["mix_report"] = deepcopy(manifest["mix_report"])
            recipe_path = cache_root / "garageband-mix-recipe.md"
            recipe_path.write_text(
                garageband_mix_recipe(manifest["mix_report"]),
                encoding="utf-8",
            )
            _update_artifact_record(
                manifest,
                receipt,
                key="recipe",
                path=recipe_path,
            )
            _write_balanced_cache_documents(cache_root, manifest, receipt)

            self.assertIsNone(
                artifacts._load_balanced_arrangement(result["cache_key"])
            )

    def test_self_rehashed_arbitrary_source_groups_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _catalog_value, _current, artifacts, result = (
                _rendered_balanced_fixture(root)
            )
            cache_root, manifest, receipt = _balanced_cache_documents(result)
            manifest["mix_report"]["source_groups"] = [
                {"arbitrary": "self-rehashed"}
            ]
            receipt["mix_report"] = deepcopy(manifest["mix_report"])
            _write_balanced_cache_documents(cache_root, manifest, receipt)

            self.assertIsNone(
                artifacts._load_balanced_arrangement(result["cache_key"])
            )

    def test_self_rehashed_drum_bus_forgery_fails_closed(self) -> None:
        tamper_kinds = (
            "policy",
            "before-guard-metrics",
            "non-drum-reference-metrics",
            "after-guard-metrics",
            "after-guard-non-drum-metrics",
            "zero-overlap-with-finite-statistics",
            "positive-overlap-zero-active-before-drum",
            "positive-overlap-zero-active-before-non-drum",
        )
        for tamper_kind in tamper_kinds:
            with self.subTest(tamper_kind=tamper_kind):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    _catalog_value, _current, artifacts, result = (
                        _rendered_balanced_fixture(
                            root,
                            select_all=True,
                        )
                    )
                    cache_root, manifest, receipt = (
                        _balanced_cache_documents(result)
                    )
                    drum_bus = manifest["mix_report"]["drum_bus"]
                    self.assertTrue(drum_bus["target_applicable"])
                    if tamper_kind == "policy":
                        drum_bus["policy"] = "self-rehashed forged policy"
                    elif tamper_kind == "before-guard-metrics":
                        drum_bus["before_guard"] = {"forged": "metrics"}
                    elif tamper_kind == "non-drum-reference-metrics":
                        drum_bus["non_drum_reference"] = {
                            "forged": "metrics"
                        }
                    elif tamper_kind == "after-guard-metrics":
                        drum_bus["after_guard"] = {"forged": "metrics"}
                    elif tamper_kind == "after-guard-non-drum-metrics":
                        drum_bus["after_guard_non_drum_reference"] = {
                            "forged": "metrics"
                        }
                    elif tamper_kind == "zero-overlap-with-finite-statistics":
                        self.assertGreater(
                            drum_bus["before_guard_overlap"][
                                "overlap_block_count"
                            ],
                            0,
                        )
                        drum_bus["before_guard_overlap"][
                            "overlap_block_count"
                        ] = 0
                        drum_bus["after_guard_overlap"][
                            "overlap_block_count"
                        ] = 0
                        self.assertIsNotNone(
                            drum_bus["before_guard_overlap"][
                                "drum_vs_non_drum_median_db"
                            ]
                        )
                        self.assertIsNotNone(
                            drum_bus["before_guard_overlap"][
                                "drum_vs_non_drum_p95_db"
                            ]
                        )
                    else:
                        metric_key = (
                            "before_guard"
                            if tamper_kind.endswith("before-drum")
                            else "non_drum_reference"
                        )
                        metrics = drum_bus[metric_key]
                        metrics["active_block_count"] = 0
                        metrics["gated_rms_dbfs"] = None
                        metrics["active_block_p95_dbfs"] = None
                        if metric_key == "non_drum_reference":
                            drum_bus["after_guard_non_drum_reference"] = (
                                deepcopy(metrics)
                            )
                    receipt["mix_report"] = deepcopy(
                        manifest["mix_report"]
                    )
                    _write_balanced_cache_documents(
                        cache_root,
                        manifest,
                        receipt,
                    )

                    self.assertIsNone(
                        artifacts._load_balanced_arrangement(
                            result["cache_key"]
                        )
                    )

    def test_self_rehashed_altered_recipe_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _catalog_value, _current, artifacts, result = (
                _rendered_balanced_fixture(root)
            )
            cache_root, manifest, receipt = _balanced_cache_documents(result)
            recipe_path = cache_root / "garageband-mix-recipe.md"
            recipe_path.write_text(
                recipe_path.read_text(encoding="utf-8")
                + "\nForged track instruction.\n",
                encoding="utf-8",
            )
            _update_artifact_record(
                manifest,
                receipt,
                key="recipe",
                path=recipe_path,
            )
            _write_balanced_cache_documents(cache_root, manifest, receipt)

            self.assertIsNone(
                artifacts._load_balanced_arrangement(result["cache_key"])
            )

    def test_self_rehashed_pcm24_wav_replacement_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _catalog_value, _current, artifacts, result = (
                _rendered_balanced_fixture(root)
            )
            cache_root, manifest, receipt = _balanced_cache_documents(result)
            preview_path = cache_root / "balanced-selected-midi-preview.wav"
            _replace_wav_content(preview_path, subtype="PCM_24")
            _update_artifact_record(
                manifest,
                receipt,
                key="preview",
                path=preview_path,
            )
            _write_balanced_cache_documents(cache_root, manifest, receipt)

            self.assertIsNone(
                artifacts._load_balanced_arrangement(result["cache_key"])
            )

    def test_self_rehashed_pcm16_wav_replacement_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _catalog_value, _current, artifacts, result = (
                _rendered_balanced_fixture(root)
            )
            cache_root, manifest, receipt = _balanced_cache_documents(result)
            preview_path = cache_root / "balanced-selected-midi-preview.wav"
            _replace_wav_content(preview_path, subtype="PCM_16")
            _update_artifact_record(
                manifest,
                receipt,
                key="preview",
                path=preview_path,
            )
            _write_balanced_cache_documents(cache_root, manifest, receipt)

            self.assertIsNone(
                artifacts._load_balanced_arrangement(result["cache_key"])
            )

    def test_cached_balance_binds_exact_current_neutral_preview_fingerprint(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, artifacts, result = _rendered_balanced_fixture(root)
            cache_root, manifest, receipt = _balanced_cache_documents(result)
            forged_preview_sha256 = "f" * 64
            self.assertNotEqual(
                manifest["input_fingerprints"]["selected_lanes"][0][
                    "neutral_preview_sha256"
                ],
                forged_preview_sha256,
            )
            manifest["input_fingerprints"]["selected_lanes"][0][
                "neutral_preview_sha256"
            ] = forged_preview_sha256
            manifest["render_horizon"]["lanes"][0][
                "neutral_preview_sha256"
            ] = forged_preview_sha256
            manifest["mix_report"]["lanes"][0][
                "preview_sha256"
            ] = forged_preview_sha256
            key_payload = _balanced_key_payload_from_manifest(manifest)
            forged_cache_key = _json_hash(key_payload)
            manifest["cache_key"] = forged_cache_key
            _write_balanced_cache_documents(cache_root, manifest, receipt)
            forged_root = cache_root.with_name(forged_cache_key)
            cache_root.rename(forged_root)

            fresh = WorkbenchArtifacts(
                artifacts.root,
                soundfont_path=root / "test.sf2",
            )
            self.assertIsNotNone(
                fresh._load_balanced_arrangement(forged_cache_key)
            )
            self.assertIsNone(
                fresh.cached_balanced_arrangement(catalog, current)
            )

    def test_fresh_instance_reclaims_only_authenticated_stale_deferred_cache(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, artifacts, result = _rendered_balanced_fixture(
                root,
                promote_cache=False,
            )
            cache_root = (
                artifacts.root
                / "balanced-arrangements"
                / result["cache_key"]
            )
            marker_path = cache_root / ".deferred-cache.json"
            self.assertTrue(marker_path.is_file())

            fresh = WorkbenchArtifacts(
                artifacts.root,
                soundfont_path=root / "test.sf2",
            )
            self.assertIsNone(
                fresh.cached_balanced_arrangement(catalog, current)
            )
            self.assertTrue(cache_root.is_dir())
            self.assertTrue(marker_path.is_file())

            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            marker["created_ns"] = 0
            marker_path.write_text(
                json.dumps(marker, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            after_restart = WorkbenchArtifacts(
                artifacts.root,
                soundfont_path=root / "test.sf2",
            )
            self.assertIsNone(
                after_restart.cached_balanced_arrangement(catalog, current)
            )
            self.assertFalse(cache_root.exists())

    def test_repeat_cache_poll_uses_verified_stat_signatures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _catalog(root)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"balanced-test-soundfont")
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "main",
                    "context": "full_mix",
                    "problem_tags": [],
                },
            )
            current = store.current_state(catalog)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts",
                soundfont_path=soundfont,
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog,
                current,
            )
            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_render_preview,
            ):
                artifacts.render_balanced_arrangement(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                )
            with patch(
                "sunofriend.workbench_artifacts._sha256",
                side_effect=AssertionError("repeat poll must not rehash inputs"),
            ):
                cached = artifacts.cached_balanced_arrangement(catalog, current)
            self.assertIsNotNone(cached)
            self.assertTrue(cached["cache_hit"])

    def test_deferred_promotion_verifies_then_touches_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _catalog(root)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"balanced-test-soundfont")
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "main",
                    "context": "full_mix",
                    "problem_tags": [],
                },
            )
            current = store.current_state(catalog)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts",
                soundfont_path=soundfont,
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog,
                current,
            )
            with (
                patch(
                    "sunofriend.workbench_artifacts.render_midi_to_wav",
                    side_effect=_render_preview,
                ),
                patch.object(
                    artifacts,
                    "_touch_and_prune_balanced_cache",
                    wraps=artifacts._touch_and_prune_balanced_cache,
                ) as touch,
            ):
                result = artifacts.render_balanced_arrangement(
                    catalog,
                    current,
                    selection["selection_manifest_sha256"],
                    promote_cache=False,
                )
                touch.assert_not_called()
                promoted = artifacts.promote_balanced_arrangement(
                    result["cache_key"],
                    claim_token=result["_deferred_cache_claim"],
                )
                touch.assert_called_once_with(result["cache_key"])
            self.assertEqual(promoted["cache_key"], result["cache_key"])
            self.assertFalse(
                (
                    artifacts.root
                    / "balanced-arrangements"
                    / result["cache_key"]
                    / ".deferred-cache.json"
                ).exists()
            )

    def test_last_stale_claim_removes_only_its_fresh_hidden_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, artifacts, selection_sha256 = _balanced_fixture(root)
            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_render_preview,
            ):
                result = artifacts.render_balanced_arrangement(
                    catalog,
                    current,
                    selection_sha256,
                    promote_cache=False,
                )

            cache_root = (
                artifacts.root
                / "balanced-arrangements"
                / result["cache_key"]
            )
            claim = result["_deferred_cache_claim"]
            self.assertTrue(cache_root.is_dir())
            self.assertTrue((cache_root / ".deferred-cache.json").is_file())
            self.assertIsNone(
                artifacts.cached_balanced_arrangement(catalog, current)
            )
            self.assertNotIn(
                claim,
                (cache_root / "manifest.json").read_text(encoding="utf-8"),
            )
            self.assertNotIn(
                claim,
                (cache_root / "balanced-mix-receipt.json").read_text(
                    encoding="utf-8"
                ),
            )

            self.assertTrue(
                artifacts.discard_deferred_balanced_arrangement(
                    result["cache_key"],
                    claim,
                )
            )
            self.assertFalse(cache_root.exists())

    def test_established_cache_never_grants_a_stale_deletion_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, artifacts, selection_sha256 = _balanced_fixture(root)
            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_render_preview,
            ):
                established = artifacts.render_balanced_arrangement(
                    catalog,
                    current,
                    selection_sha256,
                )
                deferred = artifacts.render_balanced_arrangement(
                    catalog,
                    current,
                    selection_sha256,
                    promote_cache=False,
                )

            cache_root = (
                artifacts.root
                / "balanced-arrangements"
                / established["cache_key"]
            )
            self.assertTrue(deferred["cache_hit"])
            self.assertNotIn("_deferred_cache_claim", deferred)
            self.assertFalse((cache_root / ".deferred-cache.json").exists())
            self.assertTrue(cache_root.is_dir())

    def test_concurrent_deferred_adopter_beats_stale_creator_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, artifacts, selection_sha256 = _balanced_fixture(root)
            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_render_preview,
            ):
                creator = artifacts.render_balanced_arrangement(
                    catalog,
                    current,
                    selection_sha256,
                    promote_cache=False,
                )
                adopter = artifacts.render_balanced_arrangement(
                    catalog,
                    current,
                    selection_sha256,
                    promote_cache=False,
                )

            self.assertNotEqual(
                creator["_deferred_cache_claim"],
                adopter["_deferred_cache_claim"],
            )
            self.assertFalse(
                artifacts.discard_deferred_balanced_arrangement(
                    creator["cache_key"],
                    creator["_deferred_cache_claim"],
                )
            )
            cache_root = (
                artifacts.root
                / "balanced-arrangements"
                / creator["cache_key"]
            )
            self.assertTrue(cache_root.is_dir())
            promoted = artifacts.promote_balanced_arrangement(
                adopter["cache_key"],
                claim_token=adopter["_deferred_cache_claim"],
            )
            self.assertEqual(promoted["cache_key"], creator["cache_key"])
            self.assertFalse((cache_root / ".deferred-cache.json").exists())
            self.assertFalse(
                artifacts.discard_deferred_balanced_arrangement(
                    creator["cache_key"],
                    creator["_deferred_cache_claim"],
                )
            )
            self.assertTrue(cache_root.is_dir())

    def test_pruning_never_evicts_an_in_flight_deferred_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, current, artifacts, selection_sha256 = _balanced_fixture(root)
            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_render_preview,
            ):
                deferred = artifacts.render_balanced_arrangement(
                    catalog,
                    current,
                    selection_sha256,
                    promote_cache=False,
                )

            parent = artifacts.root / "balanced-arrangements"
            deferred_root = parent / deferred["cache_key"]
            established_keys = [f"{index + 1:064x}" for index in range(9)]
            for cache_key in established_keys:
                entry = parent / cache_key
                entry.mkdir(mode=0o700)
                (entry / "sentinel.bin").write_bytes(b"x")

            artifacts._touch_and_prune_balanced_cache(established_keys[-1])

            self.assertTrue(deferred_root.is_dir())
            self.assertTrue(
                (deferred_root / ".deferred-cache.json").is_file()
            )
            self.assertLessEqual(
                sum(
                    entry.is_dir()
                    and not (entry / ".deferred-cache.json").exists()
                    for entry in parent.iterdir()
                ),
                8,
            )
            self.assertTrue(
                artifacts.discard_deferred_balanced_arrangement(
                    deferred["cache_key"],
                    deferred["_deferred_cache_claim"],
                )
            )

    def test_balanced_arrangement_rejects_stale_selection_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _catalog(root)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"balanced-test-soundfont")
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "main",
                    "context": "full_mix",
                    "problem_tags": [],
                },
            )
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts",
                soundfont_path=soundfont,
            )
            with self.assertRaisesRegex(
                ValueError,
                "selection changed",
            ):
                artifacts.render_balanced_arrangement(
                    catalog,
                    store.current_state(catalog),
                    "0" * 64,
                )


def _catalog(
    root: Path,
    *,
    unselected_vocal_seconds: float | None = None,
) -> dict:
    project = root / "Balance Song-D minor-120bpm-440hz"
    candidates = root / "candidates"
    project.mkdir()
    candidates.mkdir()
    _write_wav(
        project / "Balance Song-kick-D minor-120bpm-440hz.wav",
        amplitude=0.04,
    )
    _write_wav(
        project / "Balance Song-keys-D minor-120bpm-440hz.wav",
        amplitude=0.18,
    )
    if unselected_vocal_seconds is not None:
        _write_wav(
            project / "Balance Song-vocals-D minor-120bpm-440hz.wav",
            amplitude=0.11,
            seconds=unselected_vocal_seconds,
        )
    _write_midi(candidates / "kick-listened.mid", channel=9, pitch=36)
    _write_midi(candidates / "keys-listened.mid", channel=0, pitch=60)
    return build_workbench_catalog(project, candidate_roots=[candidates])


def _balanced_fixture(
    root: Path,
    *,
    select_all: bool = False,
) -> tuple[dict, dict, WorkbenchArtifacts, str]:
    catalog = _catalog(root)
    soundfont = root / "test.sf2"
    soundfont.write_bytes(b"balanced-test-soundfont")
    store = WorkbenchStore(root / "state" / "workbench.sqlite3")
    selected_stems = catalog["stems"] if select_all else catalog["stems"][:1]
    for stem in selected_stems:
        candidate = stem["candidates"][0]
        store.append(
            catalog,
            {
                "event_type": "candidate_decision",
                "stem_id": stem["stem_id"],
                "candidate_id": candidate["candidate_id"],
                "decision": "main",
                "context": "full_mix",
                "problem_tags": [],
            },
        )
    current = store.current_state(catalog)
    artifacts = WorkbenchArtifacts(
        root / "state" / "artifacts",
        soundfont_path=soundfont,
    )
    selection = artifacts.decoded_arrangement_selection_manifest(
        catalog,
        current,
    )
    return (
        catalog,
        current,
        artifacts,
        str(selection["selection_manifest_sha256"]),
    )


def _rendered_balanced_fixture(
    root: Path,
    *,
    promote_cache: bool = True,
    select_all: bool = False,
) -> tuple[dict, dict, WorkbenchArtifacts, dict]:
    catalog, current, artifacts, selection_sha256 = _balanced_fixture(
        root,
        select_all=select_all,
    )
    with patch(
        "sunofriend.workbench_artifacts.render_midi_to_wav",
        side_effect=_render_preview,
    ):
        result = artifacts.render_balanced_arrangement(
            catalog,
            current,
            selection_sha256,
            promote_cache=promote_cache,
        )
    return catalog, current, artifacts, result


def _balanced_cache_documents(
    result: dict,
) -> tuple[Path, dict, dict]:
    cache_root = Path(str(result["preview"]["path"])).parent
    manifest = json.loads(
        (cache_root / "manifest.json").read_text(encoding="utf-8")
    )
    receipt = json.loads(
        (cache_root / "balanced-mix-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    return cache_root, manifest, receipt


def _update_artifact_record(
    manifest: dict,
    receipt: dict,
    *,
    key: str,
    path: Path,
) -> None:
    manifest[key]["bytes"] = path.stat().st_size
    manifest[key]["sha256"] = _sha256(path)
    receipt[key] = {
        "filename": manifest[key]["name"],
        "bytes": manifest[key]["bytes"],
        "sha256": manifest[key]["sha256"],
    }


def _write_balanced_cache_documents(
    cache_root: Path,
    manifest: dict,
    receipt: dict,
) -> None:
    for key in (
        "project_id",
        "selection_manifest_sha256",
        "bpm",
        "policy",
        "render_horizon_policy",
        "selection",
        "renderer",
        "input_fingerprints",
        "render_horizon",
        "mix_report",
        "mastered",
        "mastering_boundary",
        "effects",
    ):
        receipt[key] = deepcopy(manifest[key])
    receipt["receipt_sha256"] = _json_hash(
        {
            key: value
            for key, value in receipt.items()
            if key != "receipt_sha256"
        }
    )
    receipt_path = cache_root / "balanced-mix-receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest["report"]["bytes"] = receipt_path.stat().st_size
    manifest["report"]["sha256"] = _sha256(receipt_path)
    manifest["manifest_sha256"] = _json_hash(
        {
            key: value
            for key, value in manifest.items()
            if key != "manifest_sha256"
        }
    )
    (cache_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _balanced_key_payload_from_manifest(manifest: dict) -> dict:
    return {
        key: deepcopy(manifest[key])
        for key in (
            "schema",
            "project_id",
            "selection_manifest_sha256",
            "bpm",
            "policy",
            "render_horizon_policy",
            "soundfont_sha256",
            "selection",
            "renderer",
            "input_fingerprints",
        )
    }


def _replace_wav_content(path: Path, *, subtype: str) -> None:
    import numpy as np
    import soundfile

    info = soundfile.info(str(path))
    replacement = np.full(
        (int(info.frames), int(info.channels)),
        0.03125,
        dtype=np.float32,
    )
    soundfile.write(
        str(path),
        replacement,
        int(info.samplerate),
        format="WAV",
        subtype=subtype,
    )


def _write_float_constant(
    path: Path,
    *,
    amplitude: float,
    sample_rate: int = 16_000,
    seconds: float = 2.0,
) -> None:
    import numpy as np
    import soundfile

    frames = int(round(sample_rate * seconds))
    audio = np.full((frames, 1), amplitude, dtype=np.float32)
    soundfile.write(
        str(path),
        audio,
        sample_rate,
        format="WAV",
        subtype="FLOAT",
    )


def _same_role_catalog(root: Path) -> dict:
    project = root / "Same Role Song-D minor-120bpm-440hz"
    candidates = root / "same-role-candidates"
    project.mkdir()
    candidates.mkdir()
    _write_wav(
        project / "Same Role Song-keys-D minor-120bpm-440hz.wav",
        amplitude=0.16,
    )
    _write_midi(candidates / "keys-first-listened.mid", channel=0, pitch=60)
    _write_midi(candidates / "keys-second-listened.mid", channel=0, pitch=67)
    return build_workbench_catalog(project, candidate_roots=[candidates])


def _write_midi(path: Path, *, channel: int, pitch: int) -> None:
    write_midi_file(
        path,
        [
            MidiTrack(
                name=path.stem,
                channel=channel,
                program=0,
                notes=[
                    NoteEvent(
                        start=index * 0.25,
                        end=index * 0.25 + 0.15,
                        pitch=pitch,
                        velocity=100,
                    )
                    for index in range(6)
                ],
            )
        ],
        bpm=120.0,
    )


def _render_preview(midi_path: Path, wav_path: Path, **_kwargs: object) -> None:
    payload = Path(midi_path).read_bytes()
    amplitude = 0.8 if b"Kick" in payload else 0.12
    _write_wav(Path(wav_path), amplitude=amplitude)


def _write_wav(path: Path, *, amplitude: float, seconds: float = 2.0) -> None:
    sample_rate = 16_000
    frames = int(sample_rate * seconds)
    sample = int(amplitude * 32767).to_bytes(2, "little", signed=True)
    with wave.open(str(path), "wb") as destination:
        destination.setnchannels(2)
        destination.setsampwidth(2)
        destination.setframerate(sample_rate)
        destination.writeframes(sample * 2 * frames)


def _write_level_blocks(
    path: Path,
    *,
    levels_dbfs: tuple[float, ...],
    sample_rate: int = 16_000,
) -> None:
    block_frames = int(round(sample_rate * 0.4))
    frames = bytearray()
    for level_dbfs in levels_dbfs:
        amplitude = 10.0 ** (float(level_dbfs) / 20.0)
        sample = int(round(amplitude * 32767)).to_bytes(
            2,
            "little",
            signed=True,
        )
        frames.extend(sample * 2 * block_frames)
    with wave.open(str(path), "wb") as destination:
        destination.setnchannels(2)
        destination.setsampwidth(2)
        destination.setframerate(sample_rate)
        destination.writeframes(bytes(frames))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_hash(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


if __name__ == "__main__":
    unittest.main()
