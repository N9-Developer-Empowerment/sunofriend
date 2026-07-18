from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sunofriend.instrument_preference import (
    FEEDBACK_SCHEMA,
    PROFILE_POLICY,
    PROFILE_SCHEMA,
    build_personal_instrument_profile,
    load_personal_instrument_profile,
    rank_instrument_preferences,
    record_instrument_patch_feedback,
)


class InstrumentPreferenceTests(unittest.TestCase):
    def _bundle(self, root: Path, *, kind: str = "keys") -> Path:
        bundle = root / "bundle"
        bundle.mkdir()
        (bundle / "performance.mid").write_bytes(b"MThd\x00fixture-midi")
        (bundle / "instrument_bundle.json").write_text(
            json.dumps(
                {
                    "operation": "instrument-bundle",
                    "format": "sunofriend-instrument-bundle-v1",
                    "format_version": 1,
                    "status": "complete",
                    "kind": kind,
                    "stem": "/private/song-keys.wav",
                    "midi": "/private/keys.mid",
                    "source_instrument_status": "texture-only",
                }
            ),
            encoding="utf-8",
        )
        (bundle / "instrument_recipe.json").write_text(
            json.dumps(
                {
                    "format": "sunofriend-instrument-bundle-v1",
                    "format_version": 1,
                    "kind": kind,
                }
            ),
            encoding="utf-8",
        )
        return bundle

    def test_records_explicit_hash_pinned_feedback_without_mutating_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = self._bundle(root)
            original_midi = (bundle / "performance.mid").read_bytes()
            output = root / "small-time-piano.json"

            result = record_instrument_patch_feedback(
                bundle,
                patch_name="Small Time Piano",
                out_path=output,
                decision="preferred",
                listening_context="full-mix",
                compared_with=["sunofriend-instrument", "Small Time Piano"],
                notes="Consistent and every note audible.",
            )

            feedback = json.loads(output.read_text())
            self.assertEqual(feedback["schema"], FEEDBACK_SCHEMA)
            self.assertEqual(feedback["status"], "reviewed")
            self.assertEqual(feedback["choice"]["patch_name"], "Small Time Piano")
            self.assertEqual(feedback["choice"]["decision"], "preferred")
            self.assertEqual(
                feedback["choice"]["compared_with"],
                ["sunofriend-instrument", "Small Time Piano"],
            )
            self.assertFalse(feedback["effects"]["automatic_patch_selection"])
            self.assertFalse(feedback["effects"]["playability_gate_bypassed"])
            self.assertEqual(result["feedback_sha256"], _sha256(output))
            self.assertEqual((bundle / "performance.mid").read_bytes(), original_midi)

    def test_profile_is_deterministic_advisory_and_ranks_full_mix_choice(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = self._bundle(root)
            preferred = root / "preferred.json"
            rejected = root / "rejected.json"
            record_instrument_patch_feedback(
                bundle,
                patch_name="Small Time Piano",
                out_path=preferred,
                decision="preferred",
                listening_context="full-mix",
            )
            record_instrument_patch_feedback(
                bundle,
                patch_name="Church Organ",
                out_path=rejected,
                decision="rejected",
                listening_context="solo",
            )
            first = root / "profile-first.json"
            second = root / "profile-second.json"

            result = build_personal_instrument_profile(
                [preferred, rejected], out_path=first
            )
            build_personal_instrument_profile(
                [rejected, preferred], out_path=second
            )
            profile, record = load_personal_instrument_profile(first)
            ranking = rank_instrument_preferences(profile, "keys")

            self.assertEqual(profile["schema"], PROFILE_SCHEMA)
            self.assertEqual(profile["policy"]["name"], PROFILE_POLICY)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(result["profile_sha256"], record["sha256"])
            self.assertEqual(ranking["history_first"], "Small Time Piano")
            self.assertEqual(ranking["ranking"][0]["weighted_score"], 1.0)
            self.assertEqual(ranking["ranking"][1]["weighted_score"], -0.5)
            self.assertFalse(ranking["automatic_selection"])
            self.assertFalse(ranking["match_ranking_changed"])
            self.assertFalse(ranking["playability_gate_bypassed"])
            self.assertIn("not confidence", ranking["score_meaning"])

    def test_rejects_duplicate_unreviewed_and_mutated_profile_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = self._bundle(root)
            feedback = root / "feedback.json"
            record_instrument_patch_feedback(
                bundle,
                patch_name="Small Time Piano",
                out_path=feedback,
            )
            with self.assertRaisesRegex(ValueError, "unique by hash"):
                build_personal_instrument_profile(
                    [feedback, feedback], out_path=root / "duplicate.json"
                )

            document = json.loads(feedback.read_text())
            document["status"] = "unreviewed"
            feedback.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "explicitly reviewed"):
                build_personal_instrument_profile(
                    [feedback], out_path=root / "unreviewed.json"
                )

            feedback.unlink()
            record_instrument_patch_feedback(
                bundle,
                patch_name="Small Time Piano",
                out_path=feedback,
            )
            profile_path = root / "profile.json"
            build_personal_instrument_profile([feedback], out_path=profile_path)
            profile = json.loads(profile_path.read_text())
            profile["policy"]["automatic_selection"] = True
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "policy is invalid"):
                load_personal_instrument_profile(profile_path)

    def test_rejects_incomplete_zero_effect_and_hash_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = self._bundle(root)
            feedback = root / "feedback.json"
            record_instrument_patch_feedback(
                bundle,
                patch_name="Small Time Piano",
                out_path=feedback,
            )

            document = json.loads(feedback.read_text())
            document["effects"] = {}
            feedback.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "effects are invalid"):
                build_personal_instrument_profile(
                    [feedback], out_path=root / "empty-effects-profile.json"
                )

            feedback.unlink()
            record_instrument_patch_feedback(
                bundle,
                patch_name="Small Time Piano",
                out_path=feedback,
            )
            document = json.loads(feedback.read_text())
            document["bundle"]["report"]["sha256"] = "not-a-sha256"
            feedback.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "bundle report is invalid"):
                build_personal_instrument_profile(
                    [feedback], out_path=root / "bad-hash-profile.json"
                )

    def test_rejects_profile_with_incomplete_effect_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = self._bundle(root)
            feedback = root / "feedback.json"
            profile_path = root / "profile.json"
            record_instrument_patch_feedback(
                bundle,
                patch_name="Small Time Piano",
                out_path=feedback,
            )
            build_personal_instrument_profile([feedback], out_path=profile_path)

            profile = json.loads(profile_path.read_text())
            profile["effects"] = {}
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "effects are invalid"):
                load_personal_instrument_profile(profile_path)


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
