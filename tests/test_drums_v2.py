"""Deterministic tests for multiband/stereo drum transcription v2."""
from __future__ import annotations

import tempfile
import unittest
import math
from dataclasses import replace
from pathlib import Path

try:
    import numpy as np
    import soundfile as sf

    import librosa  # noqa: F401

    AUDIO = True
except Exception:  # pragma: no cover - optional audio environment
    AUDIO = False

from sunofriend.transcribe_drums import (
    GM,
    DrumHit,
    DrumHitFeatures,
    DrumTranscription,
    _classify_features,
    _make_candidates,
    _measure_features,
    complete_hat_pattern,
    transcribe_drum_stem,
    transcribe_drum_stem_detailed,
)


SR = 22050


def _feature(**changes: float) -> DrumHitFeatures:
    values = {
        "peak_dbfs": -12.0,
        "rms_dbfs": -20.0,
        "absolute_confidence": 0.9,
        "onset_strength": 1.0,
        "dominant_hz": 100.0,
        "spectral_centroid_hz": 500.0,
        "spectral_flatness": 0.02,
        "low_ratio": 0.4,
        "mid_ratio": 0.5,
        "high_ratio": 0.1,
        "decay_seconds": 0.08,
        "strongest_channel": 0,
    }
    values.update(changes)
    return DrumHitFeatures(**values)


def _hit(time: float, *, tier: str = "main") -> DrumHit:
    return DrumHit(
        time=time,
        gm_pitch=GM["hat_closed"],
        velocity=82,
        strength=0.8,
        family="hat_closed",
        tier=tier,
    )


class DrumFamilyTests(unittest.TestCase):
    def test_two_kick_and_snare_families(self):
        self.assertEqual(
            _classify_features("kick", _feature(dominant_hz=55.0)),
            ("kick_deep", GM["kick_deep"]),
        )
        self.assertEqual(
            _classify_features("kick", _feature(dominant_hz=112.0)),
            ("kick_high", GM["kick_high"]),
        )
        self.assertEqual(
            _classify_features(
                "snare",
                _feature(spectral_centroid_hz=1200.0, high_ratio=0.12),
            ),
            ("snare_body", GM["snare_body"]),
        )
        self.assertEqual(
            _classify_features(
                "snare",
                _feature(spectral_centroid_hz=3600.0, high_ratio=0.5),
            ),
            ("snare_bright", GM["snare_bright"]),
        )

    def test_existing_hat_cymbal_and_tom_variants(self):
        self.assertEqual(
            _classify_features("hat", _feature(decay_seconds=0.05))[0],
            "hat_closed",
        )
        self.assertEqual(
            _classify_features("hat", _feature(decay_seconds=0.3))[0],
            "hat_open",
        )
        self.assertEqual(
            _classify_features("cymbals", _feature(decay_seconds=0.3))[0],
            "ride",
        )
        self.assertEqual(
            _classify_features("cymbals", _feature(decay_seconds=0.8))[0],
            "crash",
        )
        expected = ((70, "tom_floor"), (110, "tom_low"), (170, "tom_mid"), (230, "tom_high"))
        for dominant, family in expected:
            with self.subTest(dominant=dominant):
                self.assertEqual(
                    _classify_features("toms", _feature(dominant_hz=dominant))[0],
                    family,
                )

    def test_other_kit_has_meaningful_families_and_retains_unknown(self):
        kick = _feature(
            dominant_hz=58.0,
            spectral_centroid_hz=100.0,
            low_ratio=0.85,
            mid_ratio=0.14,
            high_ratio=0.01,
        )
        hat = _feature(
            dominant_hz=7000.0,
            spectral_centroid_hz=6500.0,
            low_ratio=0.01,
            mid_ratio=0.1,
            high_ratio=0.89,
            decay_seconds=0.05,
        )
        uncertain = _feature(
            dominant_hz=420.0,
            spectral_centroid_hz=480.0,
            low_ratio=0.2,
            mid_ratio=0.3,
            high_ratio=0.1,
            spectral_flatness=0.3,
        )
        self.assertEqual(_classify_features("other_kit", kick)[0], "kick_deep")
        self.assertEqual(_classify_features("other_kit", hat)[0], "hat_closed")
        self.assertEqual(
            _classify_features("other_kit", uncertain),
            ("unknown", GM["unknown"]),
        )


@unittest.skipUnless(AUDIO, "librosa/numpy/soundfile unavailable")
class DrumAudioEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="sf_drums_v2_")
        self.directory = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _burst(
        audio: np.ndarray,
        time: float,
        frequency: float,
        amplitude: float,
        *,
        decay: float = 50.0,
    ) -> None:
        length = int(0.075 * SR)
        x = np.arange(length) / SR
        signal = amplitude * np.sin(2.0 * np.pi * frequency * x) * np.exp(-decay * x)
        start = int(time * SR)
        audio[..., start : start + length] += signal

    def _write(self, name: str, audio: np.ndarray) -> Path:
        path = self.directory / name
        # soundfile expects frames x channels whereas production stores them as
        # channels x frames after loading.
        values = audio.T if audio.ndim == 2 else audio
        sf.write(path, values, SR, subtype="FLOAT")
        return path

    def test_multiband_timing_and_two_kick_families(self):
        audio = np.zeros(SR * 3, dtype=float)
        self._burst(audio, 0.5, 55.0, 0.75)
        self._burst(audio, 1.5, 118.0, 0.75)
        result = transcribe_drum_stem_detailed(str(self._write("two-kicks.wav", audio)), "kick")

        self.assertEqual(len(result.main_hits), 2)
        self.assertTrue(any(abs(hit.time - 0.5) < 0.025 for hit in result.main_hits))
        self.assertTrue(any(abs(hit.time - 1.5) < 0.025 for hit in result.main_hits))
        self.assertEqual({hit.family for hit in result.main_hits}, {"kick_deep", "kick_high"})

    def test_stereo_antiphase_hit_is_not_cancelled(self):
        left = np.zeros(SR * 2, dtype=float)
        self._burst(left, 0.7, 60.0, 0.7)
        stereo = np.vstack((left, -left))  # a mono average would be exact silence
        result = transcribe_drum_stem_detailed(
            str(self._write("antiphase.wav", stereo)), "kick"
        )

        self.assertTrue(any(abs(hit.time - 0.7) < 0.025 for hit in result.main_hits))
        matched = min(result.main_hits, key=lambda hit: abs(hit.time - 0.7))
        self.assertIn(matched.features.strongest_channel, (0, 1))
        self.assertGreater(matched.features.low_ratio, 0.5)

    def test_feature_window_uses_unpadded_timestamp(self):
        source = np.zeros((2, SR), dtype=float)
        # Deliberately put a different timbre exactly 50 ms before the target.
        # The old padded-coordinate bug analysed this 5 kHz sound for the hit.
        prior_start = int(0.15 * SR)
        prior_length = int(0.045 * SR)
        x_prior = np.arange(prior_length) / SR
        source[0, prior_start : prior_start + prior_length] = 0.7 * np.sin(
            2.0 * np.pi * 5000.0 * x_prior
        )
        target_start = int(0.20 * SR)
        target_length = int(0.08 * SR)
        x_target = np.arange(target_length) / SR
        source[0, target_start : target_start + target_length] = 0.8 * np.sin(
            2.0 * np.pi * 55.0 * x_target
        )

        features = _measure_features(source, SR, 0.20, 1.0)

        self.assertLess(features.dominant_hz, 80.0)
        self.assertGreater(features.low_ratio, 0.85)
        self.assertLess(features.high_ratio, 0.05)

    def test_main_and_possible_tiers_and_legacy_conservatism(self):
        audio = np.zeros(SR * 3, dtype=float)
        self._burst(audio, 0.5, 55.0, 0.8)
        self._burst(audio, 1.5, 55.0, 0.01)
        path = self._write("confidence.wav", audio)

        detailed = transcribe_drum_stem_detailed(
            str(path), "kick", possible_delta=0.04
        )
        legacy = transcribe_drum_stem(str(path), "kick")

        self.assertTrue(any(abs(hit.time - 0.5) < 0.025 for hit in detailed.main_hits))
        weak = [hit for hit in detailed.possible_hits if abs(hit.time - 1.5) < 0.03]
        self.assertEqual(len(weak), 1)
        self.assertLess(weak[0].peak_dbfs, -48.0)
        self.assertFalse(any(abs(note.start - 1.5) < 0.03 for note in legacy))
        self.assertTrue(
            any(
                abs(note.start - 1.5) < 0.03
                for note in detailed.to_notes(include_possible=True)
            )
        )

    def test_absolute_dbfs_is_separate_from_relative_velocity(self):
        base = np.zeros(SR * 3, dtype=float)
        for time, amplitude in ((0.4, 0.8), (1.2, 0.4), (2.0, 0.2)):
            self._burst(base, time, 60.0, amplitude)
        loud = transcribe_drum_stem_detailed(str(self._write("loud.wav", base)), "kick")
        quiet = transcribe_drum_stem_detailed(
            str(self._write("quiet.wav", base * 0.25)), "kick"
        )

        self.assertEqual(
            [hit.velocity for hit in loud.main_hits],
            [hit.velocity for hit in quiet.main_hits],
        )
        level_differences = [
            loud_hit.peak_dbfs - quiet_hit.peak_dbfs
            for loud_hit, quiet_hit in zip(loud.main_hits, quiet.main_hits)
        ]
        self.assertTrue(all(abs(value - 12.041) < 0.05 for value in level_differences))

    def test_possible_search_depth_does_not_change_main_velocities(self):
        audio = np.zeros(SR * 3, dtype=float)
        for time, amplitude in ((0.4, 0.8), (1.2, 0.35), (2.0, 0.01)):
            self._burst(audio, time, 60.0, amplitude)
        path = self._write("stable-main-velocity.wav", audio)

        normal = transcribe_drum_stem_detailed(str(path), "kick")
        sensitive = transcribe_drum_stem_detailed(
            str(path), "kick", possible_delta=0.02
        )

        self.assertEqual(
            [(round(hit.time, 3), hit.velocity) for hit in normal.main_hits],
            [(round(hit.time, 3), hit.velocity) for hit in sensitive.main_hits],
        )

    def test_hat_flux_ringing_within_thirty_ms_is_one_candidate(self):
        source = np.zeros((1, SR), dtype=float)
        start = int(0.29 * SR)
        source[0, start : start + int(0.08 * SR)] = np.hanning(int(0.08 * SR))
        onset_env = np.ones(100, dtype=float)

        candidates = _make_candidates(
            source,
            SR,
            "hat",
            onset_env,
            np.asarray([50, 53]),  # 17.4 ms apart at the production hop size
            np.asarray([50, 53]),
            0,
            1.0,
        )

        self.assertEqual(len(candidates), 1)


class HatPatternCompletionTests(unittest.TestCase):
    def test_exact_adds_and_promotes_nothing(self):
        source = DrumTranscription(
            "hat",
            SR,
            (_hit(0.0), _hit(2.0), _hit(4.0)),
            (_hit(6.01, tier="possible"),),
        )
        self.assertIs(complete_hat_pattern(source, bpm=120.0, mode="exact"), source)

    def test_repair_promotes_only_recurring_possible_slot(self):
        source = DrumTranscription(
            "hat",
            SR,
            (_hit(0.0), _hit(2.0), _hit(6.0)),
            (_hit(4.01, tier="possible"), _hit(4.26, tier="possible")),
        )

        repaired = complete_hat_pattern(source, bpm=120.0, mode="repair")

        promoted = [hit for hit in repaired.main_hits if hit.provenance == "repaired"]
        self.assertEqual(len(promoted), 1)
        self.assertAlmostEqual(promoted[0].time, 4.0)
        self.assertEqual(len(repaired.possible_hits), 1)
        self.assertAlmostEqual(repaired.possible_hits[0].time, 4.26)

    def test_reconstruct_fills_only_section_supported_slot_and_tags_it(self):
        source = DrumTranscription(
            "hat",
            SR,
            (_hit(0.0), _hit(2.0), _hit(6.0)),
            (),
        )

        completed = complete_hat_pattern(source, bpm=120.0, mode="reconstruct")

        inferred = [hit for hit in completed.main_hits if hit.provenance == "inferred"]
        self.assertEqual(len(inferred), 1)
        self.assertAlmostEqual(inferred[0].time, 4.0)
        self.assertEqual(inferred[0].family, "hat_closed")
        self.assertEqual(inferred[0].gm_pitch, GM["hat_closed"])

    def test_repair_deduplicates_possible_hits_in_one_grid_slot(self):
        quieter = _hit(4.01, tier="possible")
        louder = replace(
            _hit(4.03, tier="possible"),
            velocity=105,
            strength=0.95,
            family="hat_open",
            gm_pitch=GM["hat_open"],
        )
        source = DrumTranscription(
            "hat",
            SR,
            (_hit(0.0), _hit(2.0), _hit(6.0)),
            (quieter, louder),
        )

        repaired = complete_hat_pattern(source, bpm=120.0, mode="repair")

        promoted = [hit for hit in repaired.main_hits if hit.provenance == "repaired"]
        self.assertEqual(len(promoted), 1)
        self.assertEqual(promoted[0].velocity, 105)
        self.assertEqual(len(repaired.possible_hits), 1)

    def test_recurrence_does_not_promote_non_hat_residue(self):
        residue = replace(
            _hit(4.01, tier="possible"),
            features=_feature(
                absolute_confidence=0.2,
                spectral_centroid_hz=900.0,
                high_ratio=0.1,
            ),
        )
        source = DrumTranscription(
            "hat",
            SR,
            (_hit(0.0), _hit(2.0), _hit(6.0)),
            (residue,),
        )

        repaired = complete_hat_pattern(source, bpm=120.0, mode="repair")

        self.assertFalse(any(hit.provenance == "repaired" for hit in repaired.main_hits))
        self.assertEqual(repaired.possible_hits, (residue,))

    def test_warped_grid_drives_slot_index_and_repaired_time(self):
        def time_of(beat: float) -> float:
            return 0.5 * beat + 0.001 * beat * beat

        def beat_of(time: float) -> float:
            return (-0.5 + math.sqrt(0.25 + 0.004 * time)) / 0.002

        source = DrumTranscription(
            "hat",
            SR,
            (_hit(time_of(0.0)), _hit(time_of(4.0)), _hit(time_of(12.0))),
            (_hit(time_of(8.0) + 0.01, tier="possible"),),
        )

        repaired = complete_hat_pattern(
            source,
            bpm=120.0,
            mode="repair",
            beat_of=beat_of,
            time_of=time_of,
        )

        promoted = [hit for hit in repaired.main_hits if hit.provenance == "repaired"]
        self.assertEqual(len(promoted), 1)
        self.assertAlmostEqual(promoted[0].time, time_of(8.0), places=6)
        self.assertNotAlmostEqual(promoted[0].time, 4.0, places=3)


if __name__ == "__main__":
    unittest.main()
