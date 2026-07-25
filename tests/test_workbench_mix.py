from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import tempfile
import unittest
import wave
from pathlib import Path
from typing import Any

from sunofriend.workbench_mix import (
    BALANCED_MIX_POLICY,
    BALANCED_MIX_REPORT_SCHEMA,
    build_balanced_midi_audition,
    is_drum_role,
)


_AUDIO_DEPENDENCIES_AVAILABLE = bool(
    importlib.util.find_spec("numpy") and importlib.util.find_spec("soundfile")
)


@unittest.skipUnless(
    _AUDIO_DEPENDENCIES_AVAILABLE,
    "balanced MIDI audition tests require numpy and soundfile",
)
class BalancedMidiAuditionTests(unittest.TestCase):
    def test_drum_guard_peak_report_repeat_and_inputs_are_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            kick_source = _write_tone(
                root / "kick-source.wav",
                amplitude=0.40,
                frequency=61.0,
            )
            keys_source = _write_tone(
                root / "keys-source.wav",
                amplitude=0.20,
                frequency=233.0,
            )
            kick_preview = _write_tone(
                root / "kick-preview.wav",
                amplitude=0.20,
                frequency=67.0,
            )
            keys_preview = _write_tone(
                root / "keys-preview.wav",
                amplitude=0.20,
                frequency=241.0,
            )
            lanes = [
                _lane(
                    "kick",
                    source=kick_source,
                    preview=kick_preview,
                    index=1,
                ),
                _lane(
                    "keys",
                    source=keys_source,
                    preview=keys_preview,
                    index=2,
                ),
            ]
            inputs = {
                path: path.read_bytes()
                for path in (
                    kick_source,
                    keys_source,
                    kick_preview,
                    keys_preview,
                )
            }

            first, first_files = _build(root, "first", lanes)
            second, second_files = _build(root, "second", lanes)

            self.assertEqual(first["schema"], BALANCED_MIX_REPORT_SCHEMA)
            self.assertEqual(first["policy"], BALANCED_MIX_POLICY)
            self.assertFalse(first["mastered"])
            self.assertTrue(first["path_free_report"])
            self.assertEqual(first, second)
            self.assertEqual(
                first_files["audio"].read_bytes(),
                second_files["audio"].read_bytes(),
            )
            self.assertEqual(
                first_files["report"].read_bytes(),
                second_files["report"].read_bytes(),
            )
            self.assertEqual(
                first_files["recipe"].read_bytes(),
                second_files["recipe"].read_bytes(),
            )

            lanes_by_role = {lane["role"]: lane for lane in first["lanes"]}
            kick = lanes_by_role["kick"]
            keys = lanes_by_role["keys"]
            self.assertLess(first["drum_bus"]["guard_gain_db"], 0.0)
            self.assertLess(kick["garageband_track_trim_db"], keys["garageband_track_trim_db"])
            self.assertEqual(
                kick["garageband_track_trim_db"],
                round(
                    kick["source_match_gain_db"] + kick["drum_bus_gain_db"],
                    6,
                ),
            )
            self.assertEqual(keys["drum_bus_gain_db"], 0.0)

            post_master = first["output"]["post_master"]
            self.assertLessEqual(
                post_master["sample_peak_dbfs"],
                first["limits"]["sample_peak_ceiling_dbfs"] + 0.001,
            )
            self.assertEqual(post_master["full_scale_sample_count"], 0)
            self.assertEqual(
                first["effects"],
                {
                    "source_audio_mutated": False,
                    "midi_mutated": False,
                    "selection_changed": False,
                    "feedback_recorded": False,
                    "event_appended": False,
                    "automatic_selection": False,
                    "automatic_ranking": False,
                    "default_selection_changed": False,
                },
            )
            self.assertEqual(
                {
                    key: value
                    for key, value in first["processing"].items()
                    if key
                    in {
                        "compression",
                        "limiter",
                        "equalisation",
                        "saturation",
                        "reverb",
                        "chorus",
                        "stereo_widening",
                    }
                },
                {
                    "compression": False,
                    "limiter": False,
                    "equalisation": False,
                    "saturation": False,
                    "reverb": False,
                    "chorus": False,
                    "stereo_widening": False,
                },
            )
            self.assertEqual(
                json.loads(first_files["report"].read_text(encoding="utf-8")),
                first,
            )
            _assert_path_free(self, first, root)
            self.assertNotIn(
                str(root),
                first_files["recipe"].read_text(encoding="utf-8"),
            )
            recipe_text = first_files["recipe"].read_text(encoding="utf-8")
            for lane in first["lanes"]:
                self.assertIn(
                    str(lane["garageband_pack_archive_member"]),
                    recipe_text,
                )
                self.assertIn(
                    f"Track {int(lane['selection_index']):02d}",
                    recipe_text,
                )

            import numpy as np
            import soundfile

            values, _sample_rate = soundfile.read(
                str(first_files["audio"]),
                dtype="float64",
                always_2d=True,
            )
            self.assertGreater(values.size, 0)
            self.assertEqual(int(np.count_nonzero(np.abs(values) >= 1.0)), 0)
            measured_peak = float(np.max(np.abs(values)))
            ceiling = 10.0 ** (
                (first["limits"]["sample_peak_ceiling_dbfs"] + 0.002) / 20.0
            )
            self.assertLessEqual(measured_peak, ceiling)

            for path, original in inputs.items():
                self.assertEqual(path.read_bytes(), original)

    def test_one_two_and_four_coherent_lanes_keep_source_group_level_stable(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = _write_tone(
                root / "shared-source.wav",
                amplitude=0.18,
                frequency=127.0,
            )
            preview = _write_tone(
                root / "shared-preview.wav",
                amplitude=0.10,
                frequency=251.0,
            )
            reports: dict[int, dict[str, Any]] = {}
            files_by_count: dict[int, dict[str, Path]] = {}
            for lane_count in (1, 2, 4):
                reports[lane_count], files_by_count[lane_count] = _build(
                    root,
                    f"coherent-{lane_count}",
                    [
                        _lane(
                            "keys",
                            source=source,
                            preview=preview,
                            index=index,
                        )
                        for index in range(1, lane_count + 1)
                    ],
                )

            reference_level = reports[1]["source_groups"][0][
                "after_calibration"
            ]["gated_rms_dbfs"]
            reference_gain = reports[1]["lanes"][0][
                "raw_source_match_gain_db"
            ]
            for lane_count, report in reports.items():
                self.assertEqual(report["policy"], BALANCED_MIX_POLICY)
                self.assertEqual(len(report["source_groups"]), 1)
                group = report["source_groups"][0]
                self.assertEqual(group["source_sha256"], _sha256(source))
                self.assertEqual(group["selected_lane_count"], lane_count)
                self.assertEqual(group["clamped_lane_count"], 0)
                self.assertAlmostEqual(
                    group["after_calibration"]["gated_rms_dbfs"],
                    reference_level,
                    places=5,
                )
                self.assertAlmostEqual(
                    group["residual_level_error_db"],
                    0.0,
                    places=5,
                )
                expected_calibration = -20.0 * math.log10(lane_count)
                self.assertAlmostEqual(
                    group["calibration_gain_db"],
                    expected_calibration,
                    places=5,
                )
                for lane in report["lanes"]:
                    self.assertEqual(
                        lane["source_duplicate_count"],
                        lane_count,
                    )
                    self.assertAlmostEqual(
                        lane["source_group_calibration_gain_db"],
                        expected_calibration,
                        places=5,
                    )
                    self.assertAlmostEqual(
                        lane["raw_source_match_gain_db"] - reference_gain,
                        expected_calibration,
                        places=5,
                    )
                _assert_path_free(self, report, root)

            self.assertEqual(
                files_by_count[1]["audio"].read_bytes(),
                files_by_count[2]["audio"].read_bytes(),
            )
            self.assertEqual(
                files_by_count[1]["audio"].read_bytes(),
                files_by_count[4]["audio"].read_bytes(),
            )

    def test_drum_role_aliases_receive_the_drum_bus_guard(self) -> None:
        self.assertTrue(is_drum_role("percussion"))
        self.assertTrue(is_drum_role("Kick drum"))
        self.assertTrue(is_drum_role("electronic-drum-kit"))
        self.assertTrue(is_drum_role("drumkit"))
        self.assertFalse(is_drum_role("keys"))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            keys_source = _write_tone(
                root / "keys-source.wav",
                amplitude=0.10,
                frequency=211.0,
            )
            keys_preview = _write_tone(
                root / "keys-preview.wav",
                amplitude=0.10,
                frequency=223.0,
            )
            for index, role in enumerate(("percussion", "Kick drum"), start=1):
                with self.subTest(role=role):
                    drum_source = _write_tone(
                        root / f"drum-source-{index}.wav",
                        amplitude=0.50,
                        frequency=71.0 + index,
                    )
                    drum_preview = _write_tone(
                        root / f"drum-preview-{index}.wav",
                        amplitude=0.10,
                        frequency=83.0 + index,
                    )
                    report, _ = _build(
                        root,
                        f"role-{index}",
                        [
                            _lane(
                                role,
                                source=drum_source,
                                preview=drum_preview,
                                index=1,
                            ),
                            _lane(
                                "keys",
                                source=keys_source,
                                preview=keys_preview,
                                index=2,
                            ),
                        ],
                    )
                    lane = next(
                        item for item in report["lanes"] if item["role"] == role
                    )
                    self.assertLess(lane["drum_bus_gain_db"], 0.0)
                    self.assertTrue(report["drum_bus"]["target_applicable"])
                    self.assertTrue(report["drum_bus"]["target_met"])

    def test_extreme_drum_guard_clamp_reports_unmet_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            drum_source = _write_tone(
                root / "drum-source.wav",
                amplitude=0.80,
                frequency=67.0,
            )
            keys_source = _write_tone(
                root / "keys-source.wav",
                amplitude=0.001,
                frequency=211.0,
            )
            drum_preview = _write_tone(
                root / "drum-preview.wav",
                amplitude=0.10,
                frequency=73.0,
            )
            keys_preview = _write_tone(
                root / "keys-preview.wav",
                amplitude=0.10,
                frequency=229.0,
            )
            report, _ = _build(
                root,
                "guard-clamped",
                [
                    _lane(
                        "percussion",
                        source=drum_source,
                        preview=drum_preview,
                        index=1,
                    ),
                    _lane(
                        "keys",
                        source=keys_source,
                        preview=keys_preview,
                        index=2,
                    ),
                ],
            )

            drum_bus = report["drum_bus"]
            self.assertEqual(drum_bus["guard_gain_db"], -18.0)
            self.assertLess(drum_bus["required_guard_gain_db"], -18.0)
            self.assertTrue(drum_bus["guard_clamped"])
            self.assertTrue(drum_bus["target_applicable"])
            self.assertFalse(drum_bus["overlap_median_target_met"])
            self.assertFalse(drum_bus["target_met"])
            self.assertGreater(
                drum_bus["after_guard_overlap"][
                    "drum_vs_non_drum_median_db"
                ],
                -2.0,
            )
            _assert_path_free(self, report, root)

    def test_drum_guard_uses_time_aligned_overlap_not_independent_medians(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            keys_source = _write_tone_segments(
                root / "keys-source.wav",
                [(0.50, 211.0, 0.4), (0.02, 211.0, 0.4)],
            )
            keys_preview = _write_tone_segments(
                root / "keys-preview.wav",
                [(0.50, 223.0, 0.4), (0.02, 223.0, 0.4)],
            )
            drum_source = _write_tone_segments(
                root / "drum-source.wav",
                [(0.0, 71.0, 0.4), (0.10, 71.0, 0.4)],
            )
            drum_preview = _write_tone_segments(
                root / "drum-preview.wav",
                [(0.0, 83.0, 0.4), (0.10, 83.0, 0.4)],
            )

            report, _ = _build(
                root,
                "time-aligned-overlap",
                [
                    _lane(
                        "kick",
                        source=drum_source,
                        preview=drum_preview,
                        index=1,
                    ),
                    _lane(
                        "keys",
                        source=keys_source,
                        preview=keys_preview,
                        index=2,
                    ),
                ],
            )

            drum_bus = report["drum_bus"]
            # Whole-song independently gated medians make the drum appear
            # quieter because they compare its body with the keys intro.
            self.assertLess(
                drum_bus["before_guard"]["gated_rms_dbfs"],
                drum_bus["non_drum_reference"]["gated_rms_dbfs"],
            )
            # The paired body window exposes the actual masking relationship.
            self.assertEqual(
                drum_bus["before_guard_overlap"]["overlap_block_count"],
                1,
            )
            self.assertGreater(
                drum_bus["before_guard_overlap"][
                    "drum_vs_non_drum_median_db"
                ],
                13.0,
            )
            self.assertLess(drum_bus["guard_gain_db"], -15.0)
            self.assertLessEqual(
                drum_bus["after_guard_overlap"][
                    "drum_vs_non_drum_median_db"
                ],
                -2.0 + 1e-6,
            )
            self.assertTrue(drum_bus["target_met"])

    def test_drum_guard_is_not_applied_when_buses_never_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            keys = _write_tone_segments(
                root / "keys.wav",
                [(0.20, 211.0, 0.4), (0.0, 211.0, 0.4)],
            )
            drums = _write_tone_segments(
                root / "drums.wav",
                [(0.0, 71.0, 0.4), (0.20, 71.0, 0.4)],
            )

            report, _ = _build(
                root,
                "non-overlap",
                [
                    _lane("kick", source=drums, preview=drums, index=1),
                    _lane("keys", source=keys, preview=keys, index=2),
                ],
            )

            drum_bus = report["drum_bus"]
            self.assertEqual(
                drum_bus["before_guard_overlap"]["overlap_block_count"],
                0,
            )
            self.assertEqual(drum_bus["required_guard_gain_db"], 0.0)
            self.assertEqual(drum_bus["guard_gain_db"], 0.0)
            self.assertFalse(drum_bus["target_applicable"])
            self.assertIsNone(drum_bus["target_met"])

    def test_fixed_overlap_cohort_retains_absolute_gate_floor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            amplitude = 10.0 ** (-53.0 / 20.0)
            drums = _write_float_values(
                root / "quiet-drums.wav",
                values=[amplitude] * 6_400,
                sample_rate=8_000,
            )
            keys = _write_float_values(
                root / "quiet-keys.wav",
                values=[amplitude] * 6_400,
                sample_rate=8_000,
            )

            report, _ = _build(
                root,
                "absolute-overlap-floor",
                [
                    _lane(
                        "percussion",
                        source=drums,
                        preview=drums,
                        index=1,
                    ),
                    _lane(
                        "keys",
                        source=keys,
                        preview=keys,
                        index=2,
                    ),
                ],
            )

            drum_bus = report["drum_bus"]
            before = drum_bus["before_guard_overlap"]
            after = drum_bus["after_guard_overlap"]
            self.assertEqual(before["drum_gate_dbfs"], -70.0)
            self.assertEqual(after["drum_gate_dbfs"], -70.0)
            self.assertEqual(before["non_drum_gate_dbfs"], -70.0)
            self.assertEqual(after["non_drum_gate_dbfs"], -70.0)
            self.assertEqual(drum_bus["guard_gain_db"], -2.0)
            self.assertEqual(after["drum_vs_non_drum_median_db"], -2.0)
            self.assertTrue(drum_bus["target_met"])

    def test_overlap_p95_restrains_a_sparse_drum_peak(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            keys = _write_tone_segments(
                root / "keys.wav",
                [(0.10, 211.0, 0.4), (0.10, 211.0, 0.4)],
            )
            drums = _write_tone_segments(
                root / "drums.wav",
                [(0.10, 71.0, 0.4), (0.80, 71.0, 0.4)],
            )

            report, _ = _build(
                root,
                "sparse-drum-peak",
                [
                    _lane("kick", source=drums, preview=drums, index=1),
                    _lane("keys", source=keys, preview=keys, index=2),
                ],
            )

            drum_bus = report["drum_bus"]
            self.assertEqual(
                drum_bus["before_guard_overlap"]["overlap_block_count"],
                2,
            )
            self.assertGreater(
                drum_bus["before_guard_overlap"]["drum_vs_non_drum_p95_db"],
                drum_bus["before_guard_overlap"][
                    "drum_vs_non_drum_median_db"
                ],
            )
            self.assertLessEqual(
                drum_bus["after_guard_overlap"]["drum_vs_non_drum_p95_db"],
                3.0 + 1e-6,
            )
            self.assertTrue(drum_bus["overlap_p95_target_met"])

    def test_silent_preview_is_rejected_without_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = _write_tone(
                root / "source.wav",
                amplitude=0.20,
                frequency=173.0,
            )
            preview = _write_tone(
                root / "silent-preview.wav",
                amplitude=0.0,
                frequency=211.0,
            )
            source_before = source.read_bytes()
            preview_before = preview.read_bytes()
            files = _output_files(root, "silent")

            with self.assertRaisesRegex(
                ValueError,
                "selected neutral MIDI preview is silent",
            ):
                build_balanced_midi_audition(
                    [_lane("keys", source=source, preview=preview, index=1)],
                    output_path=files["audio"],
                    report_path=files["report"],
                    recipe_path=files["recipe"],
                )

            self.assertFalse(files["audio"].exists())
            self.assertFalse(files["report"].exists())
            self.assertFalse(files["recipe"].exists())
            self.assertEqual(source.read_bytes(), source_before)
            self.assertEqual(preview.read_bytes(), preview_before)

    def test_full_scale_neutral_preview_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = _write_tone(
                root / "source.wav",
                amplitude=0.20,
                frequency=173.0,
            )
            preview = _write_tone(
                root / "full-scale-preview.wav",
                amplitude=1.0,
                frequency=250.0,
            )
            files = _output_files(root, "full-scale")

            with self.assertRaisesRegex(
                ValueError,
                "contains full-scale samples",
            ):
                build_balanced_midi_audition(
                    [_lane("keys", source=source, preview=preview, index=1)],
                    output_path=files["audio"],
                    report_path=files["report"],
                    recipe_path=files["recipe"],
                )

            self.assertFalse(files["audio"].exists())
            self.assertFalse(files["report"].exists())
            self.assertFalse(files["recipe"].exists())

    def test_excluded_loud_preview_tail_does_not_attenuate_audible_horizon(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = _write_tone(
                root / "source.wav",
                amplitude=0.20,
                frequency=173.0,
            )
            preview = _write_tone_segments(
                root / "preview-with-loud-tail.wav",
                [
                    (0.20, 211.0, 0.8),
                    (0.95, 211.0, 0.8),
                ],
            )
            files = _output_files(root, "bounded-tail")

            report = build_balanced_midi_audition(
                [_lane("keys", source=source, preview=preview, index=1)],
                output_path=files["audio"],
                report_path=files["report"],
                recipe_path=files["recipe"],
                output_frames=6_400,
            )

            lane = report["lanes"][0]
            self.assertAlmostEqual(lane["raw_source_match_gain_db"], 0.0, places=2)
            self.assertAlmostEqual(lane["source_match_gain_db"], 0.0, places=2)
            self.assertEqual(lane["source_metrics"]["frames"], 6_400)
            self.assertEqual(lane["preview_metrics"]["frames"], 6_400)
            self.assertLess(lane["preview_metrics"]["sample_peak_dbfs"], -13.0)
            with wave.open(str(files["audio"]), "rb") as rendered:
                self.assertEqual(rendered.getnframes(), 6_400)

    def test_drum_only_and_non_drum_only_leave_bus_guard_at_unity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = _write_tone(
                root / "source.wav",
                amplitude=0.25,
                frequency=101.0,
            )
            preview = _write_tone(
                root / "preview.wav",
                amplitude=0.15,
                frequency=199.0,
            )

            drum_only, _ = _build(
                root,
                "drum-only",
                [_lane("kick", source=source, preview=preview, index=1)],
            )
            non_drum_only, _ = _build(
                root,
                "non-drum-only",
                [_lane("keys", source=source, preview=preview, index=1)],
            )

            for report in (drum_only, non_drum_only):
                self.assertEqual(report["drum_bus"]["guard_gain_db"], 0.0)
                self.assertFalse(report["processing"]["drum_bus_gain"])
                self.assertIsNotNone(report["output"]["post_master"]["gated_rms_dbfs"])
                self.assertEqual(
                    report["output"]["post_master"]["full_scale_sample_count"],
                    0,
                )
            self.assertIsNone(
                drum_only["drum_bus"]["non_drum_reference"]["gated_rms_dbfs"]
            )
            self.assertIsNone(
                non_drum_only["drum_bus"]["before_guard"]["gated_rms_dbfs"]
            )

    def test_more_than_twenty_four_lanes_is_rejected_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = _write_tone(
                root / "source.wav",
                amplitude=0.20,
                frequency=109.0,
            )
            preview = _write_tone(
                root / "preview.wav",
                amplitude=0.20,
                frequency=227.0,
            )
            lanes = [
                _lane("keys", source=source, preview=preview, index=index)
                for index in range(25)
            ]
            files = _output_files(root, "too-many")

            with self.assertRaisesRegex(ValueError, "at most 24 selected lanes"):
                build_balanced_midi_audition(
                    lanes,
                    output_path=files["audio"],
                    report_path=files["report"],
                    recipe_path=files["recipe"],
                )

            self.assertFalse(files["audio"].exists())
            self.assertFalse(files["report"].exists())
            self.assertFalse(files["recipe"].exists())

    def test_dense_twenty_four_lane_mix_can_attenuate_to_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = _write_tone(
                root / "dense-source.wav",
                amplitude=0.90,
                frequency=109.0,
            )
            preview = _write_tone(
                root / "dense-preview.wav",
                amplitude=0.90,
                frequency=109.0,
            )
            lanes = [
                _lane("keys", source=source, preview=preview, index=index)
                for index in range(1, 25)
            ]
            # Model 24 independently separated stems whose rendered previews
            # happen to add coherently. The source identity, not the local test
            # pathname, defines the balance group.
            for index, lane in enumerate(lanes, start=1):
                lane["source_sha256"] = hashlib.sha256(
                    f"independent-source-{index}".encode("utf-8")
                ).hexdigest()

            report, _ = _build(root, "dense-24", lanes)

            output = report["output"]
            self.assertLess(output["raw_normalisation_gain_db"], -24.0)
            self.assertEqual(
                output["master_output_gain_db"],
                output["requested_normalisation_gain_db"],
            )
            self.assertTrue(output["normalisation_target_met"])
            self.assertAlmostEqual(
                output["post_master"]["gated_rms_dbfs"],
                report["limits"]["audition_target_gated_rms_dbfs"],
                delta=report["limits"]["normalisation_target_tolerance_db"],
            )
            self.assertIsNone(output["normalisation_limit"])
            self.assertNotIn("master_gain_db", report["limits"])
            self.assertEqual(
                report["limits"]["maximum_normalisation_boost_db"],
                12.0,
            )

    def test_maximum_positive_boost_cap_reports_unmet_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            quiet = _write_tone(
                root / "quiet.wav",
                amplitude=0.005,
                frequency=211.0,
            )

            report, _ = _build(
                root,
                "maximum-positive-boost",
                [_lane("keys", source=quiet, preview=quiet, index=1)],
            )

            output = report["output"]
            target = report["limits"]["audition_target_gated_rms_dbfs"]
            self.assertGreater(
                output["raw_normalisation_gain_db"],
                report["limits"]["maximum_normalisation_boost_db"],
            )
            self.assertEqual(output["requested_normalisation_gain_db"], 12.0)
            self.assertEqual(output["master_output_gain_db"], 12.0)
            self.assertEqual(
                output["normalisation_limit"],
                "maximum_positive_boost",
            )
            self.assertFalse(output["normalisation_target_met"])
            self.assertLess(output["post_master_target_error_db"], 0.0)
            self.assertEqual(
                output["post_master_target_error_db"],
                round(output["post_master"]["gated_rms_dbfs"] - target, 6),
            )

    def test_one_sample_tail_uses_a_full_analysis_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sample_rate = 8_000
            block_frames = int(round(sample_rate * 0.4))
            values = [0.1] * (block_frames * 2) + [0.8]
            audio = _write_float_values(
                root / "partial-tail.wav",
                values=values,
                sample_rate=sample_rate,
            )

            report, _ = _build(
                root,
                "partial-tail",
                [_lane("keys", source=audio, preview=audio, index=1)],
            )

            output = report["output"]
            self.assertEqual(output["pre_master"]["block_count"], 3)
            self.assertAlmostEqual(
                output["pre_master"]["gated_rms_dbfs"],
                -20.0,
                delta=0.001,
            )
            self.assertAlmostEqual(
                output["raw_normalisation_gain_db"],
                2.0,
                delta=0.001,
            )
            self.assertGreater(output["master_output_gain_db"], 0.0)
            self.assertEqual(
                output["normalisation_limit"],
                "sample_peak_ceiling",
            )

    def test_short_source_and_preview_share_padded_analysis_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            short_source = _write_float_values(
                root / "short-source.wav",
                values=[0.1] * 1_600,
                sample_rate=8_000,
            )
            short_preview = _write_float_values(
                root / "short-preview.wav",
                values=[0.1] * 1_600,
                sample_rate=8_000,
            )
            long_source = _write_float_values(
                root / "long-source.wav",
                values=[0.1] * 6_400,
                sample_rate=8_000,
            )
            long_preview = _write_float_values(
                root / "long-preview.wav",
                values=[0.1] * 6_400,
                sample_rate=8_000,
            )

            report, _ = _build(
                root,
                "unequal-duration",
                [
                    _lane(
                        "keys",
                        source=short_source,
                        preview=short_preview,
                        index=1,
                    ),
                    _lane(
                        "strings",
                        source=long_source,
                        preview=long_preview,
                        index=2,
                    ),
                ],
            )

            short_lane = report["lanes"][0]
            self.assertEqual(
                short_lane["source_metrics"]["gated_rms_dbfs"],
                short_lane["preview_metrics"]["gated_rms_dbfs"],
            )
            self.assertEqual(
                short_lane["source_group_calibration_gain_db"],
                0.0,
            )
            self.assertEqual(short_lane["source_match_gain_db"], 0.0)

    def test_sample_peak_ceiling_reports_unmet_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transient = _write_impulse_train(
                root / "transient.wav",
                amplitude=0.80,
                impulses_per_block=8,
            )

            report, _ = _build(
                root,
                "sample-peak-ceiling",
                [_lane("keys", source=transient, preview=transient, index=1)],
            )

            output = report["output"]
            limits = report["limits"]
            self.assertEqual(
                output["requested_normalisation_gain_db"],
                output["raw_normalisation_gain_db"],
            )
            self.assertLess(
                output["available_sample_peak_room_db"],
                output["requested_normalisation_gain_db"],
            )
            self.assertEqual(
                output["master_output_gain_db"],
                output["available_sample_peak_room_db"],
            )
            self.assertEqual(
                output["normalisation_limit"],
                "sample_peak_ceiling",
            )
            self.assertFalse(output["normalisation_target_met"])
            self.assertLess(output["post_master_target_error_db"], 0.0)
            self.assertLessEqual(
                output["post_master"]["sample_peak_dbfs"],
                limits["sample_peak_ceiling_dbfs"] + 0.001,
            )
            self.assertEqual(
                output["post_master"]["full_scale_sample_count"],
                0,
            )

    def test_silent_source_fallback_is_role_specific_and_deterministic(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            silent_drum_source = _write_tone(
                root / "silent-drum-source.wav",
                amplitude=0.0,
                frequency=71.0,
            )
            silent_keys_source = _write_tone(
                root / "silent-keys-source.wav",
                amplitude=0.0,
                frequency=211.0,
                seconds=0.4,
            )
            drum_preview = _write_tone(
                root / "drum-preview.wav",
                amplitude=0.10,
                frequency=83.0,
            )
            keys_preview = _write_tone(
                root / "keys-preview.wav",
                amplitude=0.10,
                frequency=223.0,
            )
            lanes = [
                _lane(
                    "kick",
                    source=silent_drum_source,
                    preview=drum_preview,
                    index=1,
                ),
                _lane(
                    "keys",
                    source=silent_keys_source,
                    preview=keys_preview,
                    index=2,
                ),
            ]

            first, first_files = _build(root, "silent-fallback-1", lanes)
            second, second_files = _build(root, "silent-fallback-2", lanes)

            fallback_reason = (
                "source stem had no measurable active blocks; conservative "
                "role fallback used"
            )
            by_role = {lane["role"]: lane for lane in first["lanes"]}
            for role, expected_gain in (("kick", -6.0), ("keys", 0.0)):
                lane = by_role[role]
                self.assertIsNone(lane["source_metrics"]["gated_rms_dbfs"])
                self.assertEqual(
                    lane["provisional_source_match_gain_db"],
                    expected_gain,
                )
                self.assertEqual(lane["source_group_calibration_gain_db"], 0.0)
                self.assertEqual(lane["source_match_gain_db"], expected_gain)
                self.assertEqual(lane["fallback_reason"], fallback_reason)

            self.assertEqual(first, second)
            self.assertEqual(
                first_files["audio"].read_bytes(),
                second_files["audio"].read_bytes(),
            )
            self.assertEqual(
                first_files["report"].read_bytes(),
                second_files["report"].read_bytes(),
            )
            self.assertEqual(
                first_files["recipe"].read_bytes(),
                second_files["recipe"].read_bytes(),
            )
            _assert_path_free(self, first, root)

    def test_destination_and_input_path_collisions_fail_before_writing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination_collisions = {
                "output-report": ("output", "report"),
                "output-recipe": ("output", "recipe"),
                "report-recipe": ("report", "recipe"),
                "temporary-report": ("temporary", "report"),
                "temporary-recipe": ("temporary", "recipe"),
            }
            for name, (first_name, second_name) in destination_collisions.items():
                with self.subTest(name=name):
                    paths, source, preview = _collision_fixture(root / name)
                    paths[second_name] = paths[first_name]
                    before = _file_tree(root / name)
                    with self.assertRaisesRegex(ValueError, "must differ"):
                        build_balanced_midi_audition(
                            [_lane("keys", source=source, preview=preview, index=1)],
                            output_path=paths["output"],
                            report_path=paths["report"],
                            recipe_path=paths["recipe"],
                        )
                    self.assertEqual(_file_tree(root / name), before)

            for input_name in ("source", "preview"):
                for destination_name in (
                    "output",
                    "report",
                    "recipe",
                    "temporary",
                ):
                    name = f"{input_name}-{destination_name}"
                    with self.subTest(name=name):
                        case_root = root / name
                        paths, source, preview = _collision_fixture(
                            case_root,
                            input_name=input_name,
                            input_destination=destination_name,
                        )
                        before = _file_tree(case_root)
                        with self.assertRaisesRegex(
                            ValueError,
                            "must not overwrite input audio",
                        ):
                            build_balanced_midi_audition(
                                [
                                    _lane(
                                        "keys",
                                        source=source,
                                        preview=preview,
                                        index=1,
                                    )
                                ],
                                output_path=paths["output"],
                                report_path=paths["report"],
                                recipe_path=paths["recipe"],
                            )
                        self.assertEqual(_file_tree(case_root), before)


def _build(
    root: Path,
    name: str,
    lanes: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Path]]:
    files = _output_files(root, name)
    report = build_balanced_midi_audition(
        lanes,
        output_path=files["audio"],
        report_path=files["report"],
        recipe_path=files["recipe"],
    )
    for path in files.values():
        if not path.is_file():
            raise AssertionError(f"balanced audition did not create {path.name}")
    return report, files


def _output_files(root: Path, name: str) -> dict[str, Path]:
    output = root / name
    return {
        "audio": output / "balanced.wav",
        "report": output / "balanced.json",
        "recipe": output / "garageband.txt",
    }


def _lane(
    role: str,
    *,
    source: Path,
    preview: Path,
    index: int,
) -> dict[str, Any]:
    candidate_id = f"candidate-{index:02d}"
    return {
        "track_id": f"track-{index:02d}",
        "stem_id": f"stem-{index:02d}",
        "candidate_id": candidate_id,
        "role": role,
        "decision": "main" if index == 1 else "optional",
        "selection_index": index,
        "garageband_pack_archive_member": (
            f"MIDI/{index:02d}-{role.casefold().replace(' ', '-')}-"
            f"{'main' if index == 1 else 'optional'}.mid"
        ),
        "source_path": str(source),
        "source_sha256": _sha256(source),
        "source_bytes": source.stat().st_size,
        "source_midi_sha256": hashlib.sha256(
            f"immutable-midi-{candidate_id}".encode("utf-8")
        ).hexdigest(),
        "preview_path": str(preview),
        "preview_sha256": _sha256(preview),
        "preview_bytes": preview.stat().st_size,
        "neutral_preview_cache_key": hashlib.sha256(
            f"neutral-preview-{candidate_id}".encode("utf-8")
        ).hexdigest(),
    }


def _write_tone(
    path: Path,
    *,
    amplitude: float,
    frequency: float,
    sample_rate: int = 8_000,
    seconds: float = 0.8,
) -> Path:
    frames = int(round(sample_rate * seconds))
    samples = bytearray()
    for frame in range(frames):
        value = int(
            round(
                max(-1.0, min(1.0, amplitude))
                * 32767
                * math.sin(2.0 * math.pi * frequency * frame / sample_rate)
            )
        )
        samples.extend(value.to_bytes(2, "little", signed=True))
    with wave.open(str(path), "wb") as destination:
        destination.setnchannels(1)
        destination.setsampwidth(2)
        destination.setframerate(sample_rate)
        destination.writeframes(bytes(samples))
    return path


def _write_tone_segments(
    path: Path,
    segments: list[tuple[float, float, float]],
    *,
    sample_rate: int = 8_000,
) -> Path:
    samples = bytearray()
    for amplitude, frequency, seconds in segments:
        frames = int(round(sample_rate * seconds))
        for frame in range(frames):
            value = int(
                round(
                    max(-1.0, min(1.0, amplitude))
                    * 32767
                    * math.sin(
                        2.0 * math.pi * frequency * frame / sample_rate
                    )
                )
            )
            samples.extend(value.to_bytes(2, "little", signed=True))
    with wave.open(str(path), "wb") as destination:
        destination.setnchannels(1)
        destination.setsampwidth(2)
        destination.setframerate(sample_rate)
        destination.writeframes(bytes(samples))
    return path


def _write_float_values(
    path: Path,
    *,
    values: list[float],
    sample_rate: int,
) -> Path:
    import numpy as np
    import soundfile

    audio = np.asarray(values, dtype=np.float32).reshape((-1, 1))
    soundfile.write(
        str(path),
        audio,
        sample_rate,
        format="WAV",
        subtype="FLOAT",
    )
    return path


def _write_impulse_train(
    path: Path,
    *,
    amplitude: float,
    impulses_per_block: int,
    sample_rate: int = 8_000,
    block_seconds: float = 0.4,
    block_count: int = 2,
) -> Path:
    block_frames = int(round(sample_rate * block_seconds))
    samples = bytearray()
    for frame in range(block_frames * block_count):
        block_frame = frame % block_frames
        value = (
            int(round(max(-1.0, min(1.0, amplitude)) * 32767))
            if block_frame < impulses_per_block
            else 0
        )
        samples.extend(value.to_bytes(2, "little", signed=True))
    with wave.open(str(path), "wb") as destination:
        destination.setnchannels(1)
        destination.setsampwidth(2)
        destination.setframerate(sample_rate)
        destination.writeframes(bytes(samples))
    return path


def _collision_fixture(
    root: Path,
    *,
    input_name: str | None = None,
    input_destination: str | None = None,
) -> tuple[dict[str, Path], Path, Path]:
    root.mkdir(parents=True)
    output = root / "balanced.wav"
    paths = {
        "output": output,
        "report": root / "balanced.json",
        "recipe": root / "garageband.txt",
        "temporary": output.with_name(f".{output.name}.float-tmp.wav"),
    }
    source = root / "source.wav"
    preview = root / "preview.wav"
    if input_name is not None:
        if input_destination is None:
            raise AssertionError("input collision requires a destination")
        if input_name == "source":
            source = paths[input_destination]
        elif input_name == "preview":
            preview = paths[input_destination]
        else:
            raise AssertionError(f"unsupported input name: {input_name}")
    source = _write_tone(source, amplitude=0.20, frequency=173.0)
    preview = _write_tone(preview, amplitude=0.20, frequency=211.0)
    return paths, source, preview


def _file_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _assert_path_free(
    test: unittest.TestCase,
    value: Any,
    root: Path,
) -> None:
    serialized = json.dumps(value, sort_keys=True)
    test.assertNotIn(str(root), serialized)

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                test.assertNotEqual(key, "path")
                test.assertFalse(key.endswith("_path"), key)
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
