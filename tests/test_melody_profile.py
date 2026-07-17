from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Optional

from sunofriend.melody_profile import (
    PROFILE_POLICY,
    PROFILE_SCHEMA,
    build_personal_melody_profile,
    load_personal_melody_profile,
    rank_melody_alternatives,
)


def _context(*, agreement: float = 0.45, density: float = 3.0) -> dict:
    return {
        "duration_bars": 2.0,
        "mean_agreement_ratio": agreement,
        "mean_selection_score": 0.7,
        "combined_note_density_per_bar": density,
        "alternative_names": ["basic-pitch", "game-boundary", "combined"],
    }


def _correction(
    selected: str,
    *,
    context: Optional[dict] = None,
    propagated: bool = False,
    status: str = "reviewed",
) -> dict:
    choice = {
        "phrase_index": 0,
        "selected": selected,
        "reviewed": True,
    }
    if context is not None:
        choice["ranking_context"] = context
    choices = [choice]
    if propagated:
        choice["propagated_from_phrase_index"] = 1
        source = {
            "phrase_index": 1,
            "selected": selected,
            "reviewed": True,
        }
        if context is not None:
            source["ranking_context"] = context
        choices.insert(0, source)
    return {
        "format": "sunofriend-melody-corrections-v1",
        "source_stem_sha256": f"source-{selected}",
        "review": {
            "format": "sunofriend.melody-phrase-review.v1",
            "status": status,
            "tracker_run_sha256": f"tracker-{selected}",
            "choices": choices,
        },
    }


class MelodyProfileTests(unittest.TestCase):
    def test_builds_deterministic_advisory_profile_from_reviewed_choices(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manual = root / "manual.json"
            propagated = root / "propagated.json"
            manual.write_text(
                json.dumps(_correction("game-boundary", context=_context())),
                encoding="utf-8",
            )
            propagated.write_text(
                json.dumps(
                    _correction(
                        "combined",
                        context=_context(agreement=0.8, density=5.0),
                        propagated=True,
                    )
                ),
                encoding="utf-8",
            )
            first = root / "profile-first.json"
            second = root / "profile-second.json"

            result = build_personal_melody_profile(
                [manual, propagated],
                out_path=first,
            )
            build_personal_melody_profile(
                [propagated, manual],
                out_path=second,
            )

            self.assertEqual(result["explicit_choice_count"], 3)
            self.assertEqual(result["contextual_observation_count"], 3)
            profile, record = load_personal_melody_profile(first)
            self.assertEqual(profile["schema"], PROFILE_SCHEMA)
            self.assertEqual(profile["policy"]["name"], PROFILE_POLICY)
            self.assertTrue(profile["policy"]["advisory_only"])
            self.assertFalse(profile["policy"]["automatic_selection"])
            self.assertEqual(
                profile["alternative_counts"]["game-boundary"],
                {"choices": 1, "weighted_choices": 1.0},
            )
            self.assertEqual(
                profile["alternative_counts"]["combined"],
                {"choices": 2, "weighted_choices": 1.5},
            )
            self.assertEqual(record["sha256"], result["profile_sha256"])
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_similar_context_ranks_history_without_changing_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            correction = root / "reviewed.json"
            correction.write_text(
                json.dumps(_correction("game-boundary", context=_context())),
                encoding="utf-8",
            )
            profile_path = root / "profile.json"
            build_personal_melody_profile([correction], out_path=profile_path)
            profile, _ = load_personal_melody_profile(profile_path)

            ranking = rank_melody_alternatives(
                profile,
                _context(),
                ["basic-pitch", "game-boundary", "combined"],
            )

            self.assertEqual(ranking["history_first"], "game-boundary")
            self.assertEqual(ranking["ranking"][0]["name"], "game-boundary")
            self.assertFalse(ranking["automatic_selection"])
            self.assertFalse(ranking["candidate_order_changed"])
            self.assertFalse(ranking["default_selection_changed"])
            self.assertIn("not confidence", ranking["score_meaning"])

    def test_global_only_legacy_choice_remains_usable_with_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            correction = root / "legacy-reviewed.json"
            correction.write_text(
                json.dumps(_correction("combined")),
                encoding="utf-8",
            )
            profile_path = root / "profile.json"

            result = build_personal_melody_profile(
                [correction],
                out_path=profile_path,
            )
            profile, _ = load_personal_melody_profile(profile_path)
            ranking = rank_melody_alternatives(
                profile,
                _context(),
                ["basic-pitch", "game-boundary", "combined"],
            )

            self.assertEqual(result["contextual_observation_count"], 0)
            self.assertTrue(result["warnings"])
            self.assertEqual(ranking["history_first"], "combined")

    def test_rejects_unreviewed_duplicate_and_mutated_policy_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unreviewed = root / "unreviewed.json"
            unreviewed.write_text(
                json.dumps(_correction("combined", status="unreviewed")),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "explicitly reviewed"):
                build_personal_melody_profile(
                    [unreviewed],
                    out_path=root / "unreviewed-profile.json",
                )

            reviewed = root / "reviewed.json"
            reviewed.write_text(
                json.dumps(_correction("combined", context=_context())),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unique by hash"):
                build_personal_melody_profile(
                    [reviewed, reviewed],
                    out_path=root / "duplicate-profile.json",
                )

            profile_path = root / "profile.json"
            build_personal_melody_profile([reviewed], out_path=profile_path)
            profile = json.loads(profile_path.read_text())
            profile["policy"]["automatic_selection"] = True
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "policy is invalid"):
                load_personal_melody_profile(profile_path)


if __name__ == "__main__":
    unittest.main()
