from __future__ import annotations

import json
import unittest

from sunofriend.workbench_home import WORKBENCH_HOME_SCHEMA, build_workbench_home


def _candidate(candidate_id: str, *, primary: bool = True) -> dict:
    return {
        "candidate_id": candidate_id,
        "primary": primary,
        "label": f"private process label {candidate_id}",
        "process": "private-process-metric",
        "midi": {"path": f"/private/{candidate_id}.mid", "sha256": "a" * 64},
    }


def _stem(stem_id: str, role: str, candidates: list[dict]) -> dict:
    return {
        "stem_id": stem_id,
        "role": role,
        "candidate_count": len(candidates),
        "source": {"path": f"/private/{stem_id}.wav", "sha256": "b" * 64},
        "candidates": candidates,
    }


def _state(*stems: dict) -> dict:
    return {"stems": {stem["stem_id"]: stem for stem in stems}, "event_count": 0}


def _stem_state(
    stem_id: str,
    *,
    role: str,
    candidates: dict | None = None,
    main_candidate_id: str | None = None,
    outcome: str | None = None,
) -> dict:
    return {
        "stem_id": stem_id,
        "role": role,
        "candidates": candidates or {},
        "main_candidate_id": main_candidate_id,
        "outcome": {"value": outcome} if outcome else None,
        "auditioned_candidates": [],
    }


class WorkbenchHomeTests(unittest.TestCase):
    def test_first_unreviewed_candidate_stem_is_the_only_next_step(self) -> None:
        catalog = {
            "project_id": "project-1",
            "stems": [
                _stem("noise", "other kit", []),
                _stem("bass", "bass", [_candidate("bass-a")]),
                _stem("keys", "keys", [_candidate("keys-a")]),
            ],
        }
        current = _state(
            _stem_state("noise", role="other kit"),
            _stem_state("bass", role="synth bass body"),
            _stem_state("keys", role="keys"),
        )

        home = build_workbench_home(catalog, current)

        self.assertEqual(home["schema"], WORKBENCH_HOME_SCHEMA)
        self.assertEqual(
            home["next_step"],
            {
                "action": "compare-stem",
                "reason_code": "unreviewed-candidate-stem",
                "stem_id": "bass",
            },
        )
        self.assertEqual(home["stems"][0]["attention_code"], "no-candidates")
        self.assertEqual(home["stems"][1]["heard_role"], "synth bass body")
        self.assertEqual(home["stems"][1]["attention_code"], "compare-candidates")
        self.assertEqual(home["counts"]["decision_recorded_stem_count"], 0)

    def test_recorded_reject_correction_and_outcome_are_not_called_selected(self) -> None:
        candidates = [_candidate("a"), _candidate("b"), _candidate("c")]
        catalog = {
            "project_id": "project-2",
            "stems": [_stem("keys", "keys", candidates)],
        }
        current = _state(
            _stem_state(
                "keys",
                role="melody plus accompaniment",
                candidates={
                    "a": {
                        "decision": "needs_correction",
                        "context": "solo",
                        "notes": "private note",
                    },
                    "b": {"decision": "reject", "context": "solo"},
                },
                outcome="none_usable",
            )
        )

        home = build_workbench_home(catalog, current)
        row = home["stems"][0]

        self.assertTrue(row["decision_recorded"])
        self.assertEqual(row["selected_part_count"], 0)
        self.assertEqual(row["decision_counts"]["needs_correction"], 1)
        self.assertEqual(row["decision_counts"]["reject"], 1)
        self.assertEqual(row["outcome"], "none_usable")
        self.assertEqual(row["attention_code"], "no-usable-selection")
        self.assertEqual(
            home["next_step"]["reason_code"], "explicit-no-selection-outcomes"
        )

    def test_solo_selection_routes_to_arrangement_then_full_mix_routes_to_pack(self) -> None:
        catalog = {
            "project_id": "project-3",
            "stems": [
                _stem(
                    "bass",
                    "bass",
                    [_candidate("advanced", primary=False), _candidate("main")],
                )
            ],
        }
        solo = _state(
            _stem_state(
                "bass",
                role="body and pluck",
                candidates={
                    "main": {"decision": "main", "context": "solo"},
                    "advanced": {"decision": "optional", "context": "full_mix"},
                },
                main_candidate_id="main",
            )
        )

        home = build_workbench_home(catalog, solo)

        self.assertEqual(home["stems"][0]["main"]["display_letter"], "A")
        self.assertEqual(home["stems"][0]["optional"][0]["display_letter"], "B")
        self.assertEqual(home["counts"]["selected_main_count"], 1)
        self.assertEqual(home["counts"]["selected_optional_count"], 1)
        self.assertEqual(home["counts"]["selected_needing_full_mix_count"], 1)
        self.assertEqual(home["stems"][0]["attention_code"], "hear-in-arrangement")
        self.assertEqual(home["next_step"]["action"], "hear-arrangement")

        solo["stems"]["bass"]["candidates"]["main"]["context"] = "full_mix"
        confirmed = build_workbench_home(catalog, solo)

        self.assertEqual(confirmed["stems"][0]["attention_code"], "ready-for-pack")
        self.assertEqual(
            confirmed["next_step"],
            {
                "action": "compose-pack",
                "reason_code": "selected-parts-confirmed-in-full-mix",
            },
        )

    def test_home_projection_is_path_free_and_excludes_private_candidate_evidence(self) -> None:
        catalog = {
            "project_id": "project-4",
            "root": "/private/song",
            "stems": [_stem("lead", "lead", [_candidate("candidate-a")])],
        }
        current = _state(
            _stem_state(
                "lead",
                role="lead melody",
                candidates={
                    "candidate-a": {
                        "decision": "main",
                        "context": "full_mix",
                        "notes": "secret listening note",
                        "problem_tags": ["missing_notes"],
                    }
                },
                main_candidate_id="candidate-a",
            )
        )

        payload = json.dumps(build_workbench_home(catalog, current), sort_keys=True)

        self.assertNotIn("/private/", payload)
        self.assertNotIn("secret listening note", payload)
        self.assertNotIn("private process label", payload)
        self.assertNotIn("private-process-metric", payload)
        self.assertNotIn("missing_notes", payload)

    def test_path_like_free_form_role_is_redacted_from_home_projection(self) -> None:
        catalog = {
            "project_id": "project-role-path",
            "stems": [_stem("lead", "lead", [_candidate("lead-a")])],
        }
        for role in (
            "melody /Users/alice/private/song.wav",
            "source=/Users/alice/private/song.wav",
            "(/Users/alice/private/song.wav)",
        ):
            with self.subTest(role=role):
                current = _state(_stem_state("lead", role=role))
                home = build_workbench_home(catalog, current)
                self.assertEqual(home["stems"][0]["heard_role"], "custom role")
                self.assertTrue(home["stems"][0]["heard_role_redacted"])
                self.assertNotIn("/Users/alice", json.dumps(home))

    def test_musical_role_with_non_path_slash_is_preserved(self) -> None:
        catalog = {
            "project_id": "project-role-slash",
            "stems": [_stem("bass", "bass", [_candidate("bass-a")])],
        }
        current = _state(_stem_state("bass", role="bass / pluck"))

        home = build_workbench_home(catalog, current)

        self.assertEqual(home["stems"][0]["heard_role"], "bass / pluck")
        self.assertFalse(home["stems"][0]["heard_role_redacted"])

    def test_home_declares_zero_effects_and_temporary_audition_reset(self) -> None:
        home = build_workbench_home(
            {"project_id": "project-5", "stems": []},
            _state(),
        )

        self.assertEqual(home["next_step"]["action"], "no-results")
        self.assertFalse(home["temporary_state_restored"])
        self.assertEqual(
            home["temporary_state_not_restored"],
            ["playhead", "loop", "mixer visibility", "mute", "solo", "level"],
        )
        self.assertEqual(set(home["effects"].values()), {False})

    def test_terminal_no_selection_outcome_does_not_create_a_review_loop(self) -> None:
        catalog = {
            "project_id": "project-6",
            "stems": [_stem("lead", "lead", [_candidate("lead-a")])],
        }
        current = _state(
            _stem_state("lead", role="lead", outcome="none_usable")
        )

        home = build_workbench_home(catalog, current)

        self.assertEqual(home["stems"][0]["attention_code"], "no-usable-selection")
        self.assertEqual(
            home["next_step"],
            {
                "action": "no-results",
                "reason_code": "explicit-no-selection-outcomes",
            },
        )

    def test_terminal_outcome_defensively_suppresses_legacy_active_selection(
        self,
    ) -> None:
        catalog = {
            "project_id": "project-terminal-barrier",
            "stems": [_stem("lead", "lead", [_candidate("lead-a")])],
        }
        current = _state(
            _stem_state(
                "lead",
                role="lead",
                candidates={
                    "lead-a": {
                        "decision": "main",
                        "context": "full_mix",
                    }
                },
                main_candidate_id="lead-a",
                outcome="none_usable",
            )
        )

        home = build_workbench_home(catalog, current)
        row = home["stems"][0]

        self.assertEqual(home["counts"]["selected_part_count"], 0)
        self.assertIsNone(row["main"])
        self.assertEqual(row["inactive_selected_count"], 1)
        self.assertEqual(row["attention_code"], "no-usable-selection")
        self.assertEqual(home["next_step"]["action"], "no-results")

    def test_unresolved_empty_selection_precedes_a_ready_pack(self) -> None:
        catalog = {
            "project_id": "project-7",
            "stems": [
                _stem("bass", "bass", [_candidate("bass-a")]),
                _stem("keys", "keys", [_candidate("keys-a")]),
            ],
        }
        current = _state(
            _stem_state(
                "bass",
                role="bass",
                candidates={"bass-a": {"decision": "main", "context": "full_mix"}},
                main_candidate_id="bass-a",
            ),
            _stem_state(
                "keys",
                role="keys",
                candidates={
                    "keys-a": {"decision": "needs_correction", "context": "solo"}
                },
            ),
        )

        home = build_workbench_home(catalog, current)

        self.assertEqual(home["stems"][1]["attention_code"], "no-active-selection")
        self.assertEqual(home["next_step"]["action"], "compare-stem")
        self.assertEqual(home["next_step"]["stem_id"], "keys")

    def test_stale_candidate_state_is_not_a_current_decision(self) -> None:
        catalog = {
            "project_id": "project-8",
            "stems": [_stem("bass", "bass", [_candidate("current")])],
        }
        current = _state(
            _stem_state(
                "bass",
                role="bass",
                candidates={"removed": {"decision": "reject", "context": "solo"}},
            )
        )

        home = build_workbench_home(catalog, current)

        self.assertFalse(home["stems"][0]["decision_recorded"])
        self.assertEqual(home["next_step"]["reason_code"], "unreviewed-candidate-stem")

    def test_blocked_diagnostic_candidate_is_not_an_active_selection(self) -> None:
        blocked = _candidate("burst")
        blocked["audition_blocked"] = True
        catalog = {
            "project_id": "project-9",
            "stems": [_stem("lead", "lead", [blocked])],
        }
        current = _state(
            _stem_state(
                "lead",
                role="lead",
                candidates={"burst": {"decision": "main", "context": "full_mix"}},
                main_candidate_id="burst",
            )
        )

        home = build_workbench_home(catalog, current)

        self.assertEqual(home["counts"]["selected_part_count"], 0)
        self.assertEqual(home["stems"][0]["blocked_selected_count"], 1)
        self.assertEqual(home["stems"][0]["attention_code"], "no-active-selection")
        self.assertEqual(home["next_step"]["action"], "compare-stem")


if __name__ == "__main__":
    unittest.main()
