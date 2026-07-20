from __future__ import annotations

import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sunofriend.workbench_store import (
    WORKBENCH_PACK_BASKET_SCHEMA,
    WORKBENCH_PACK_SELECTION_SCHEMA,
    WorkbenchPackStateConflictError,
    WorkbenchStore,
)


PROJECT_ID = "pack-project"
SCOPE_SHA256 = "a" * 64
BASKET_SHA256 = "b" * 64
PLAN_SHA256 = "c" * 64


class WorkbenchPackStoreTests(unittest.TestCase):
    def test_pack_selection_is_append_only_restorable_and_revision_guarded(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "workbench.sqlite3"
            first_store = WorkbenchStore(database)
            second_store = WorkbenchStore(database)
            basket = _basket(
                included_item_ids=["midi:bass:main", "bundle:bass:portable"],
                source_audio_opt_in=True,
            )
            unchanged = copy.deepcopy(basket)

            first = first_store.save_pack_selection(
                PROJECT_ID, basket, PLAN_SHA256, expected_revision=0
            )

            self.assertEqual(basket, unchanged)
            self.assertEqual({key: first[key] for key in basket}, basket)
            self.assertEqual(first["revision"], 1)
            self.assertEqual(first["saved_plan_sha256"], PLAN_SHA256)
            self.assertTrue(first["saved"])
            self.assertTrue(first["event_id"])
            self.assertTrue(first["saved_at"].endswith("Z"))
            self.assertEqual(
                second_store.current_pack_selection(PROJECT_ID, SCOPE_SHA256),
                first,
            )

            with self.assertRaises(WorkbenchPackStateConflictError) as raised:
                second_store.save_pack_selection(
                    PROJECT_ID, basket, "d" * 64, expected_revision=0
                )
            self.assertEqual(raised.exception.expected_revision, 0)
            self.assertEqual(raised.exception.current_revision, 1)
            self.assertEqual(
                first_store.current_pack_selection(PROJECT_ID, SCOPE_SHA256),
                first,
            )

            revised_basket = _basket(
                included_item_ids=["bundle:bass:portable", "midi:bass:main"],
                source_audio_opt_in=False,
                basket_sha256="e" * 64,
            )
            revised = second_store.save_pack_selection(
                PROJECT_ID, revised_basket, "f" * 64, expected_revision=1
            )
            self.assertEqual(revised["revision"], 2)
            self.assertNotEqual(revised["event_id"], first["event_id"])
            self.assertEqual(
                revised["included_item_ids"],
                ["bundle:bass:portable", "midi:bass:main"],
            )
            self.assertFalse(revised["source_audio_opt_in"])
            self.assertEqual(
                first_store.current_pack_selection(PROJECT_ID, SCOPE_SHA256),
                revised,
            )
            self.assertIsNone(first_store.current_pack_selection(PROJECT_ID, "0" * 64))
            self.assertIsNone(
                first_store.current_pack_selection("another-project", SCOPE_SHA256)
            )

            with sqlite3.connect(database) as connection:
                rows = connection.execute(
                    """
                    SELECT revision, schema_name, basket_json
                    FROM pack_selection_events
                    ORDER BY sequence
                    """
                ).fetchall()
            self.assertEqual([row[0] for row in rows], [1, 2])
            self.assertEqual(
                {row[1] for row in rows}, {WORKBENCH_PACK_SELECTION_SCHEMA}
            )
            self.assertEqual(json.loads(rows[0][2]), basket)
            self.assertEqual(json.loads(rows[1][2]), revised_basket)

    def test_pack_rows_do_not_change_decisions_reviews_or_contributions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "workbench.sqlite3"
            store = WorkbenchStore(database)
            project = _project()
            fixed_time = "2026-07-20T12:34:56Z"
            with patch("sunofriend.workbench_store._utc_now", return_value=fixed_time):
                decision = store.append(
                    project,
                    {
                        "event_type": "candidate_decision",
                        "stem_id": "bass",
                        "candidate_id": "bass-main",
                        "decision": "main",
                        "context": "full_mix",
                        "problem_tags": [],
                    },
                )
                events_before = store.events(PROJECT_ID)
                state_before = store.current_state(project)
                review_before = store.export_review(project)

                store.save_pack_selection(
                    PROJECT_ID,
                    _basket(included_item_ids=["midi:bass-main"]),
                    PLAN_SHA256,
                    expected_revision=0,
                )

                events_after = store.events(PROJECT_ID)
                state_after = store.current_state(project)
                review_after = store.export_review(project)

            self.assertEqual(events_before, [decision])
            self.assertEqual(events_after, events_before)
            self.assertEqual(state_after, state_before)
            self.assertEqual(
                json.dumps(review_after, sort_keys=True, separators=(",", ":")),
                json.dumps(review_before, sort_keys=True, separators=(",", ":")),
            )
            contribution_json = json.dumps(review_after["contribution_preview"])
            self.assertNotIn(WORKBENCH_PACK_SELECTION_SCHEMA, contribution_json)
            self.assertNotIn("basket_scope_sha256", contribution_json)
            self.assertNotIn("included_item_ids", contribution_json)
            with sqlite3.connect(database) as connection:
                decision_count = connection.execute(
                    "SELECT COUNT(*) FROM decision_events"
                ).fetchone()[0]
                pack_count = connection.execute(
                    "SELECT COUNT(*) FROM pack_selection_events"
                ).fetchone()[0]
            self.assertEqual(decision_count, 1)
            self.assertEqual(pack_count, 1)

    def test_pack_basket_validation_rejects_noncanonical_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "workbench.sqlite3"
            store = WorkbenchStore(database)
            base = _basket(included_item_ids=["midi:one"])

            invalid_baskets: list[tuple[str, object]] = []
            missing = copy.deepcopy(base)
            missing.pop("basket_sha256")
            invalid_baskets.append(("missing field", missing))
            extra = {**base, "revision": 1}
            invalid_baskets.append(("extra field", extra))
            wrong_schema = {**base, "schema": "sunofriend.wrong.v1"}
            invalid_baskets.append(("schema", wrong_schema))
            wrong_project = {**base, "project_id": "another-project"}
            invalid_baskets.append(("project", wrong_project))
            wrong_scope = {**base, "basket_scope_sha256": "A" * 64}
            invalid_baskets.append(("scope hash", wrong_scope))
            wrong_basket_hash = {**base, "basket_sha256": "b" * 63}
            invalid_baskets.append(("basket hash", wrong_basket_hash))
            not_a_list = {**base, "included_item_ids": ("midi:one",)}
            invalid_baskets.append(("item list", not_a_list))
            non_text_item = {**base, "included_item_ids": [1]}
            invalid_baskets.append(("non-text item", non_text_item))
            empty_item = {**base, "included_item_ids": [""]}
            invalid_baskets.append(("empty item", empty_item))
            padded_item = {**base, "included_item_ids": [" midi:one"]}
            invalid_baskets.append(("padded item", padded_item))
            duplicate_item = {
                **base,
                "included_item_ids": ["midi:one", "midi:one"],
            }
            invalid_baskets.append(("duplicate item", duplicate_item))
            long_item = {**base, "included_item_ids": ["x" * 513]}
            invalid_baskets.append(("long item", long_item))
            non_boolean_opt_in = {**base, "source_audio_opt_in": 1}
            invalid_baskets.append(("source opt-in", non_boolean_opt_in))
            invalid_baskets.append(("not an object", []))

            for label, basket in invalid_baskets:
                with self.subTest(label=label):
                    with self.assertRaises(ValueError):
                        store.save_pack_selection(
                            PROJECT_ID,
                            basket,  # type: ignore[arg-type]
                            PLAN_SHA256,
                            expected_revision=0,
                        )

            for label, plan_sha256, expected_revision in (
                ("plan hash", "not-a-hash", 0),
                ("negative revision", PLAN_SHA256, -1),
                ("boolean revision", PLAN_SHA256, True),
                ("floating revision", PLAN_SHA256, 0.0),
            ):
                with self.subTest(label=label):
                    with self.assertRaises(ValueError):
                        store.save_pack_selection(
                            PROJECT_ID,
                            base,
                            plan_sha256,
                            expected_revision,  # type: ignore[arg-type]
                        )

            for project_id, scope in (
                ("", SCOPE_SHA256),
                (" padded", SCOPE_SHA256),
                (PROJECT_ID, "not-a-hash"),
            ):
                with self.subTest(project_id=project_id, scope=scope):
                    with self.assertRaises(ValueError):
                        store.current_pack_selection(project_id, scope)

            with sqlite3.connect(database) as connection:
                count = connection.execute(
                    "SELECT COUNT(*) FROM pack_selection_events"
                ).fetchone()[0]
            self.assertEqual(count, 0)


def _basket(
    *,
    included_item_ids: list[str],
    source_audio_opt_in: bool = False,
    basket_sha256: str = BASKET_SHA256,
) -> dict[str, object]:
    return {
        "schema": WORKBENCH_PACK_BASKET_SCHEMA,
        "project_id": PROJECT_ID,
        "basket_scope_sha256": SCOPE_SHA256,
        "included_item_ids": list(included_item_ids),
        "source_audio_opt_in": source_audio_opt_in,
        "basket_sha256": basket_sha256,
    }


def _project() -> dict[str, object]:
    return {
        "project_id": PROJECT_ID,
        "name": "Pack Store Test",
        "root": "/private/test-project",
        "setup": {"bpm": 120.0, "key": "C major", "tuning_hz": 440.0},
        "catalog_source": "test",
        "stems": [
            {
                "stem_id": "bass",
                "role": "bass",
                "review_context_sha256": "1" * 64,
                "review_question": None,
                "listening_focus": [],
                "candidate_count": 1,
                "source": {"sha256": "2" * 64},
                "candidates": [
                    {
                        "candidate_id": "bass-main",
                        "midi": {"sha256": "3" * 64},
                        "preview": None,
                        "process": "specialist",
                    }
                ],
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
