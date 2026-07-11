"""Lidl semantic golden: noisy AI stems, drum identity, and role separation.

Move Your Body remains the sub-millisecond/long-song GarageBand timing golden.
Lidl deliberately exercises the harder semantic case identified by listening:
two kick/snare timbres, weak separator residue, a mixed other-kit stem, walking
bass, and layered keys.  Tests skip cleanly when the user's local golden audio
or generated acceptance folder is not present.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from sunofriend.evaluate import evaluate_stem_midi
from sunofriend.transcribe_drums import transcribe_drum_stem_detailed


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/Lidl-B major-119bpm-440hz"
KICK = SOURCE / "Lidl-kick-B major-119bpm-440hz.wav"
DRUM_SUMMARY = (
    ROOT
    / "work/lidl-v2/mode_repair/listen_all_summary_bass-cymbals-hat-keys-kick-other-kit-pads-snare-strings-toms.json"
)
KICK_V2 = (
    ROOT
    / "work/lidl-v2/mode_repair/selected_bass-cymbals-hat-keys-kick-other-kit-pads-snare-strings-toms/kick_listened.mid"
)
PITCHED_SUMMARY = DRUM_SUMMARY
EXACT_SUMMARY = (
    ROOT / "work/lidl-v2/mode_exact/listen_all_summary_bass-keys-kick-pads.json"
)
RECONSTRUCT_ROOT = (
    ROOT / "work/lidl-v2/mode_reconstruct/selected_bass-hat-keys-pads-strings"
)


@unittest.skipUnless(
    KICK.is_file() and KICK_V2.is_file(),
    "local Lidl semantic stem/output is unavailable; run the v2 acceptance conversion",
)
class LidlStemToMidiGoldenTests(unittest.TestCase):
    def test_kick_has_two_families_and_independent_audio_recall(self):
        try:
            import librosa  # noqa: F401
            import numpy  # noqa: F401
            import soundfile  # noqa: F401
            import mido  # noqa: F401
        except Exception as exc:
            self.skipTest(f"optional audio/MIDI dependency unavailable: {exc}")

        transcription = transcribe_drum_stem_detailed(str(KICK), "kick")
        report = evaluate_stem_midi(
            KICK,
            KICK_V2,
            kind="kick",
            pitch_family_map={35: "kick_high", 36: "kick_deep"},
        )

        families = report.drums.family_counts
        self.assertGreaterEqual(report.note_count, 235)
        self.assertLessEqual(report.note_count, 245)
        self.assertGreaterEqual(families.get("kick_deep", 0), 160)
        self.assertGreaterEqual(families.get("kick_high", 0), 50)
        self.assertGreaterEqual(len(transcription.possible_hits), 8)
        self.assertGreaterEqual(report.onsets.strong.f1, 0.78)
        self.assertGreaterEqual(report.onsets.possible.f1, 0.82)
        self.assertLessEqual(report.onsets.timing.absolute_error_p95_ms, 25.0)
        self.assertLessEqual(abs(report.onsets.timing.drift_ms), 10.0)


@unittest.skipUnless(
    DRUM_SUMMARY.is_file() and PITCHED_SUMMARY.is_file(),
    "run the isolated Lidl v2 acceptance conversion to enable manifest checks",
)
class LidlPublishedV2ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.drums = json.loads(DRUM_SUMMARY.read_text(encoding="utf-8"))
        cls.pitched = json.loads(PITCHED_SUMMARY.read_text(encoding="utf-8"))
        cls.exact = (
            json.loads(EXACT_SUMMARY.read_text(encoding="utf-8"))
            if EXACT_SUMMARY.is_file()
            else None
        )

    def test_garageband_tempo_and_drum_uncertainty_contract(self):
        self.assertEqual(self.drums["set_garageband_tempo_to"], 119.0)
        parts = self.drums["parts"]
        self.assertEqual(set(parts["kick"]["semantic_metrics"]["families"]), {
            "kick_deep", "kick_high"
        })
        # Lidl contains real layered drum strikes.  Timing coincidence alone
        # must not quarantine them as cross-stem leakage.
        self.assertNotIn("leakage_uncertain", parts["toms"]["variants"])
        self.assertEqual(parts["toms"]["notes"], 91)
        self.assertGreater(parts["other_kit"]["variants"]["uncertain"]["notes"], 0)
        recognised = parts["other_kit"]["semantic_metrics"]["families"]
        self.assertGreaterEqual(len(recognised), 6)
        self.assertNotIn("unknown", recognised)

    def test_bass_and_keys_publish_auditionable_roles(self):
        parts = self.pitched["parts"]
        bass = parts["bass"]
        self.assertIn("raw_verified", bass["variants"])
        self.assertIn("root_safe", bass["variants"])
        self.assertGreaterEqual(bass["semantic_metrics"]["octave_accuracy"], 0.75)
        self.assertGreaterEqual(
            bass["semantic_metrics"]["contour_direction_accuracy"], 0.65
        )

        keys = parts["keys"]
        variants = keys["variants"]
        self.assertEqual(
            keys["notes"],
            variants["melody"]["notes"] + variants["accompaniment"]["notes"],
        )
        self.assertGreater(variants["uncertain"]["notes"], 0)
        self.assertGreater(variants["full_evidence"]["notes"], keys["notes"])

        self.assertEqual(parts["pads"]["status"], "skipped: no observed pads stem in repair mode")
        self.assertEqual(parts["strings"]["status"], "ok")

    def test_exact_mode_keeps_only_observed_confident_roles(self):
        if self.exact is None:
            self.skipTest("exact Lidl acceptance output missing")
        parts = self.exact["parts"]
        self.assertEqual(parts["pads"]["status"], "skipped: no observed pads stem in exact mode")
        keys = parts["keys"]
        self.assertEqual(
            keys["notes"],
            keys["variants"]["melody"]["notes"]
            + keys["variants"]["accompaniment"]["notes"],
        )
        self.assertGreater(keys["variants"]["uncertain"]["notes"], 0)

    @unittest.skipUnless(RECONSTRUCT_ROOT.is_dir(), "reconstruct acceptance output missing")
    def test_reconstruct_mode_labels_every_inferred_note(self):
        for part in ("bass", "pads"):
            document = json.loads(
                (RECONSTRUCT_ROOT / f"{part}_provenance.json").read_text(encoding="utf-8")
            )
            self.assertEqual(document["counts"]["notes"], document["counts"]["inferred"])
            self.assertEqual(document["counts"]["observed"], 0)
        hats = json.loads(
            (RECONSTRUCT_ROOT / "hat_provenance.json").read_text(encoding="utf-8")
        )
        self.assertGreater(hats["counts"]["observed"], 0)
        self.assertGreater(hats["counts"]["repaired"], 0)
        self.assertGreater(hats["counts"]["inferred"], 0)


if __name__ == "__main__":
    unittest.main()
