from __future__ import annotations

import copy
import hashlib
import http.client
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from sunofriend.clip import ClipNote, Instrument, MidiClip, TempoMap, TimeSignature
from sunofriend.cli import build_parser
from sunofriend.library import ClipLibrary
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.workbench_catalog import build_workbench_catalog
from sunofriend.workbench_reuse import WorkbenchClipReuseStore
from sunofriend.workbench_server import create_workbench_server


_DISABLED_CAPABILITY = {
    "enabled": False,
    "proposal_only": True,
    "reason": "Clip reuse planning was not explicitly enabled for this launch",
}
_INVALID_ACTION = {"error": "invalid Clip reuse action"}
_STALE_PLAN = {
    "error": "Clip reuse plan changed; reload the proposal before trying again"
}
_DRIFT = {
    "error": (
        "Clip reuse evidence changed or is unavailable; restart the Workbench"
    )
}
_UNKNOWN_CLIP = {"error": "Clip not found"}
_UNKNOWN_PLACEMENT = {"error": "Clip reuse placement not found"}
_EFFECT_KEYS = {
    "reuse_plan_changed",
    "placement_added",
    "placement_removed",
    "library_changed",
    "clip_changed",
    "midi_changed",
    "transform_applied",
    "decisions_changed",
    "current_arrangement_changed",
    "pack_changed",
    "feedback_changed",
    "audition_preference_recorded",
    "submission_changed",
}


class WorkbenchClipReuseLaunchTests(unittest.TestCase):
    def test_parser_requires_an_explicit_reuse_opt_in(self) -> None:
        parsed = build_parser().parse_args(
            [
                "workbench",
                "/project",
                "--clip-library",
                "/library",
                "--phase6-acceptance",
                "/acceptance.json",
                "--phase6-pack",
                "/pack.zip",
                "--enable-clip-reuse-plan",
            ]
        )
        self.assertTrue(parsed.enable_clip_reuse_plan)

        default = build_parser().parse_args(["workbench", "/project"])
        self.assertFalse(default.enable_clip_reuse_plan)

    def test_reuse_opt_in_requires_all_three_phase6_inputs(self) -> None:
        incomplete = (
            {},
            {"clip_library_path": "/tmp/library"},
            {"phase6_acceptance_path": "/tmp/acceptance.json"},
            {"phase6_pack_path": "/tmp/pack.zip"},
            {
                "clip_library_path": "/tmp/library",
                "phase6_acceptance_path": "/tmp/acceptance.json",
            },
        )
        for values in incomplete:
            with self.subTest(values=values), self.assertRaisesRegex(
                ValueError,
                "requires|must be supplied together",
            ):
                create_workbench_server(
                    {"project_id": "unused", "setup": {"bpm": 119}, "stems": []},
                    enable_clip_reuse_plan=True,
                    **values,
                )

    def test_reuse_opt_in_rejects_a_non_positive_project_bpm(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _catalog(root)
            catalog["setup"]["bpm"] = 0.0
            library, _object_hash = _clip_library(root)
            pack, acceptance = _phase6_acceptance(root)
            with (
                patch(
                    "sunofriend.workbench_clips.verify_garageband_pack_archive",
                    return_value={"status": "verified"},
                ),
                self.assertRaisesRegex(ValueError, "positive.*BPM|BPM.*positive"),
            ):
                create_workbench_server(
                    catalog,
                    state_dir=root / "state",
                    token="token",
                    clip_library_path=library,
                    phase6_acceptance_path=acceptance,
                    phase6_pack_path=pack,
                    enable_clip_reuse_plan=True,
                )


class WorkbenchClipReuseServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.catalog = _catalog(self.root)
        self.library, self.object_hash = _clip_library(self.root)
        self.pack, self.acceptance = _phase6_acceptance(self.root)
        self.token = "phase6-reuse-server-token"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_disabled_routes_are_404_and_create_no_reuse_database(self) -> None:
        for label, phase6_enabled in (("ordinary", False), ("read-only", True)):
            with self.subTest(label=label):
                state = self.root / f"{label}-state"
                options = (
                    {
                        "clip_library_path": self.library,
                        "phase6_acceptance_path": self.acceptance,
                        "phase6_pack_path": self.pack,
                    }
                    if phase6_enabled
                    else {}
                )
                with _running_server(
                    self.catalog,
                    state,
                    self.token,
                    enable_clip_reuse_plan=False,
                    **options,
                ) as server:
                    status, _headers, payload = _json_request(
                        server,
                        "GET",
                        f"/api/clip-reuse-plan?token={self.token}",
                    )
                    self.assertEqual(status, 404)
                    self.assertEqual(payload, {"error": "workbench route not found"})
                    status, _headers, payload = _json_request(
                        server,
                        "POST",
                        f"/api/clip-reuse-action?token={self.token}",
                        {},
                    )
                    self.assertEqual(status, 404)
                    self.assertEqual(payload, {"error": "workbench route not found"})
                    status, _headers, project = _json_request(
                        server,
                        "GET",
                        f"/api/project?token={self.token}",
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(project["clip_reuse_plan"], _DISABLED_CAPABILITY)
                self.assertFalse((state / "phase6-reuse" / "reuse.sqlite3").exists())

    def test_enabled_project_and_empty_plan_are_explicit_and_path_free(self) -> None:
        state = self.root / "enabled-capability-state"
        with self._server(state) as server:
            status, _headers, project = _json_request(
                server,
                "GET",
                f"/api/project?token={self.token}",
            )
            self.assertEqual(status, 200)
            capability = project["clip_reuse_plan"]
            self.assertTrue(capability["enabled"])
            self.assertTrue(capability["proposal_only"])
            self.assertTrue(capability["explicit_opt_in"])
            self.assertTrue(capability["source_clips_read_only"])
            self.assertIn("target_project", capability)
            self.assertIn("target_grid", capability)
            self.assertIn("actions", capability)
            self.assertIn("limits", capability)
            self.assertEqual(capability["actions"], {"place": True, "remove": True})
            self.assertEqual(
                capability["target_project"]["project_id"],
                self.catalog["project_id"],
            )
            self.assertEqual(capability["target_project"]["bpm"], 119.0)
            self.assertEqual(capability["target_grid"]["ticks_per_beat"], 480)

            plan = _get_plan(server, self.token)
            self.assertEqual(
                plan["schema"], "sunofriend.workbench-clip-reuse-plan.v1"
            )
            self.assertEqual(plan["revision"], 0)
            self.assertEqual(plan["event_count"], 0)
            self.assertEqual(plan["active_placement_count"], 0)
            self.assertEqual(plan["placements"], [])
            self.assertEqual(plan["status"], "empty")
            self.assertTrue(plan["plan_id"])
            self.assertRegex(plan["binding_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(plan["plan_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(
                plan["target_project"]["project_id"], self.catalog["project_id"]
            )
            self.assertEqual(plan["target_project"]["bpm"], 119.0)
            self.assertEqual(
                plan["target_grid"],
                {
                    "numerator": 4,
                    "denominator": 4,
                    "beats_per_bar": 4,
                    "ticks_per_beat": 480,
                    "origin": "recorded-zero",
                    "downbeat_status": "unconfirmed",
                    "tick_in_beat_supported": False,
                },
            )
            self.assertEqual(
                plan["limits"],
                {
                    "maximum_active_placements": 64,
                    "maximum_events_per_plan": 512,
                    "maximum_clip_note_count": 20_000,
                    "maximum_total_note_count": 40_000,
                    "maximum_end_seconds": 1_200,
                },
            )
            self.assertEqual(set(plan["effects"]), _EFFECT_KEYS)
            self.assertTrue(all(value is False for value in plan["effects"].values()))
            self.assertFalse(
                (state / "phase6-reuse" / "reuse.sqlite3").exists()
            )
            # The ordinary project payload intentionally carries tokenized local
            # media URLs.  The new capability and plan projections must not.
            _assert_path_free(self, capability, root=self.root, token=self.token)
            _assert_path_free(self, plan, root=self.root, token=self.token)

    def test_token_protection_and_exact_action_bodies(self) -> None:
        with self._server(self.root / "request-state") as server:
            status, _headers, payload = _json_request(
                server,
                "GET",
                "/api/clip-reuse-plan?token=wrong",
            )
            self.assertEqual(status, 403)
            self.assertEqual(payload, {"error": "invalid workbench session token"})
            status, _headers, payload = _json_request(
                server,
                "POST",
                "/api/clip-reuse-action?token=wrong",
                {},
            )
            self.assertEqual(status, 403)
            self.assertEqual(payload, {"error": "invalid workbench session token"})

            plan = _get_plan(server, self.token)
            valid = _place_request(plan, self.object_hash)
            invalid = (
                {},
                {key: value for key, value in valid.items() if key != "target"},
                {**valid, "gain": 1.0},
                {**valid, "action": "copy"},
                {**valid, "target": {"bar": 1, "beat": 1}},
                {
                    **valid,
                    "target": {
                        "bar": 1,
                        "beat": 1,
                        "tick_in_beat": 0,
                        "start_tick": 0,
                    },
                },
                {**valid, "target": {"bar": 0, "beat": 1, "tick_in_beat": 0}},
                {**valid, "target": {"bar": 1, "beat": 5, "tick_in_beat": 0}},
                {**valid, "target": {"bar": 1, "beat": 1, "tick_in_beat": 1}},
                {
                    "action": "remove",
                    "plan_id": plan["plan_id"],
                    "plan_sha256": plan["plan_sha256"],
                    "expected_revision": plan["revision"],
                },
            )
            for body in invalid:
                with self.subTest(body=body):
                    status, _headers, payload = _json_request(
                        server,
                        "POST",
                        f"/api/clip-reuse-action?token={self.token}",
                        body,
                    )
                    self.assertEqual(status, 400)
                    self.assertEqual(payload, _INVALID_ACTION)

            malformed_bodies = (
                b"{",
                b"[]",
                b"x" * (64 * 1024 + 1),
            )
            for body in malformed_bodies:
                with self.subTest(body_size=len(body)):
                    status, _headers, encoded = _request(
                        server,
                        "POST",
                        f"/api/clip-reuse-action?token={self.token}",
                        body=body,
                        headers={"Content-Type": "application/json"},
                    )
                    self.assertEqual(status, 400)
                    self.assertEqual(
                        json.loads(encoded.decode("utf-8")),
                        _INVALID_ACTION,
                    )
            self.assertEqual(_get_plan(server, self.token)["revision"], 0)

    def test_place_remove_restart_and_distinct_placements(self) -> None:
        state = self.root / "restart-state"
        with self._server(state) as server:
            empty = _get_plan(server, self.token)
            first_response = _post_action(
                server,
                self.token,
                _place_request(empty, self.object_hash, bar=2, beat=3),
            )
            _assert_action_response(
                self,
                first_response,
                added=True,
                root=self.root,
                token=self.token,
            )
            reuse_directory = state / "phase6-reuse"
            reuse_database = reuse_directory / "reuse.sqlite3"
            self.assertTrue(reuse_database.is_file())
            self.assertEqual(reuse_directory.stat().st_mode & 0o777, 0o700)
            self.assertEqual(reuse_database.stat().st_mode & 0o777, 0o600)
            first = first_response["plan"]
            self.assertEqual(first["revision"], 1)
            self.assertNotEqual(first["plan_sha256"], empty["plan_sha256"])
            self.assertEqual(len(first["placements"]), 1)
            first_placement = first["placements"][0]
            self.assertEqual(first_placement["clip"]["clip_id"], "clip-1")
            self.assertEqual(
                first_placement["clip"]["object_sha256"], self.object_hash
            )
            self.assertEqual(first_placement["target"]["bar"], 2)
            self.assertEqual(first_placement["target"]["beat"], 3)
            self.assertEqual(first_placement["target"]["tick_in_beat"], 0)
            self.assertEqual(_placement_start_tick(first_placement), 2_880)
            self.assertFalse(
                first_placement["compatibility"]["transform_applied"]
            )
            self.assertFalse(first_placement["compatibility"]["render_ready"])
            first_warning_codes = {
                warning["code"]
                for warning in first_placement["compatibility"]["warnings"]
            }
            self.assertIn("project-downbeat-unconfirmed", first_warning_codes)
            self.assertIn("project-time-signature-unconfirmed", first_warning_codes)
            self.assertIn("instrument-not-attached", first_warning_codes)
            self.assertNotIn("placement-overlap", first_warning_codes)

            second_response = _post_action(
                server,
                self.token,
                _place_request(first, self.object_hash, bar=2, beat=3),
            )
            second = second_response["plan"]
            self.assertEqual(second["revision"], 2)
            self.assertEqual(len(second["placements"]), 2)
            placement_ids = {
                placement["placement_id"] for placement in second["placements"]
            }
            self.assertEqual(len(placement_ids), 2)
            second_placement = next(
                placement
                for placement in second["placements"]
                if placement["placement_id"] != first_placement["placement_id"]
            )
            self.assertIn(
                "placement-overlap",
                {
                    warning["code"]
                    for warning in second_placement["compatibility"]["warnings"]
                },
            )

            remove_response = _post_action(
                server,
                self.token,
                _remove_request(second, first_placement["placement_id"]),
            )
            _assert_action_response(
                self,
                remove_response,
                removed=True,
                root=self.root,
                token=self.token,
            )
            removed = remove_response["plan"]
            self.assertEqual(removed["revision"], 3)
            self.assertEqual(len(removed["placements"]), 1)
            self.assertNotEqual(
                removed["placements"][0]["placement_id"],
                first_placement["placement_id"],
            )
            saved_identity = (
                removed["plan_id"],
                removed["plan_sha256"],
                removed["revision"],
                removed["placements"],
            )

        reuse_database = state / "phase6-reuse" / "reuse.sqlite3"
        self.assertTrue(reuse_database.is_file())
        self.assertGreaterEqual(_append_only_row_count(reuse_database), 3)
        with self._server(state) as restarted:
            persisted = _get_plan(restarted, self.token)
            self.assertEqual(
                (
                    persisted["plan_id"],
                    persisted["plan_sha256"],
                    persisted["revision"],
                    persisted["placements"],
                ),
                saved_identity,
            )

    def test_append_only_database_rejects_update_and_delete(self) -> None:
        state = self.root / "append-only-state"
        with self._server(state) as server:
            plan = _get_plan(server, self.token)
            _post_action(
                server,
                self.token,
                _place_request(plan, self.object_hash),
            )

        database = state / "phase6-reuse" / "reuse.sqlite3"
        for store_file in database.parent.glob("reuse.sqlite3*"):
            self.assertEqual(store_file.stat().st_mode & 0o777, 0o600)
        for statement in (
            "UPDATE clip_reuse_events SET event_type = 'remove'",
            "DELETE FROM clip_reuse_events",
        ):
            with self.subTest(statement=statement):
                with sqlite3.connect(database) as connection:
                    with self.assertRaisesRegex(
                        sqlite3.IntegrityError,
                        "append-only",
                    ):
                        connection.execute(statement)

        with self._server(state) as restarted:
            plan = _get_plan(restarted, self.token)
            self.assertEqual(plan["revision"], 1)
            self.assertEqual(plan["event_count"], 1)
            self.assertEqual(plan["active_placement_count"], 1)

    def test_corrupt_append_only_row_fails_closed(self) -> None:
        state = self.root / "corrupt-row-state"
        with self._server(state) as server:
            plan = _get_plan(server, self.token)
            _post_action(
                server,
                self.token,
                _place_request(plan, self.object_hash),
            )

        database = state / "phase6-reuse" / "reuse.sqlite3"
        with sqlite3.connect(database) as connection:
            connection.execute(
                """
                INSERT INTO clip_reuse_events (
                    event_id, schema_name, created_at, project_id,
                    plan_id, binding_sha256, revision, event_type,
                    placement_id, previous_plan_sha256,
                    resulting_plan_sha256, payload_json
                )
                SELECT
                    'reuse-event-corrupt', 'invalid-schema', created_at,
                    project_id, plan_id, binding_sha256, revision + 1,
                    'place', 'reuse-placement-corrupt', resulting_plan_sha256,
                    resulting_plan_sha256, '{}'
                FROM clip_reuse_events
                WHERE revision = 1
                """
            )

        with self._server(state) as restarted:
            status, _headers, payload = _json_request(
                restarted,
                "GET",
                f"/api/clip-reuse-plan?token={self.token}",
            )
            self.assertEqual(status, 409)
            self.assertEqual(payload, _DRIFT)

    def test_two_server_instances_append_only_one_stale_plan_action(self) -> None:
        state = self.root / "two-server-race-state"
        with self._server(state) as first, self._server(state) as second:
            first_plan = _get_plan(first, self.token)
            second_plan = _get_plan(second, self.token)
            self.assertEqual(first_plan, second_plan)
            barrier = threading.Barrier(3)
            outcomes: list[tuple[int, dict]] = []
            outcomes_lock = threading.Lock()

            def submit(server, body: dict) -> None:
                barrier.wait(timeout=5)
                status, _headers, payload = _json_request(
                    server,
                    "POST",
                    f"/api/clip-reuse-action?token={self.token}",
                    body,
                )
                with outcomes_lock:
                    outcomes.append((status, payload))

            threads = [
                threading.Thread(
                    target=submit,
                    args=(first, _place_request(first_plan, self.object_hash)),
                ),
                threading.Thread(
                    target=submit,
                    args=(second, _place_request(second_plan, self.object_hash)),
                ),
            ]
            for thread in threads:
                thread.start()
            barrier.wait(timeout=5)
            for thread in threads:
                thread.join(timeout=20)
                self.assertFalse(thread.is_alive())

            self.assertEqual(sorted(status for status, _payload in outcomes), [201, 409])
            conflict = next(payload for status, payload in outcomes if status == 409)
            self.assertEqual(conflict, _STALE_PLAN)
            current = _get_plan(first, self.token)
            self.assertEqual(current["revision"], 1)
            self.assertEqual(current["event_count"], 1)
            self.assertEqual(current["active_placement_count"], 1)

    def test_event_513_is_rejected_before_store_creation(self) -> None:
        database = self.root / "event-limit-state" / "reuse.sqlite3"
        store = WorkbenchClipReuseStore(database)
        with self.assertRaisesRegex(ValueError, "event limit"):
            store.append(
                project_id="project",
                plan_id="reuse-plan-" + "a" * 64,
                binding_sha256="b" * 64,
                expected_revision=512,
                expected_plan_sha256="c" * 64,
                event_type="place",
                placement_id="reuse-placement-test",
                payload={},
                resulting_plan_sha256="d" * 64,
            )
        self.assertFalse(database.exists())

    def test_stale_plan_and_object_pins_are_conflicts(self) -> None:
        with self._server(self.root / "stale-state") as server:
            empty = _get_plan(server, self.token)
            current = _post_action(
                server,
                self.token,
                _place_request(empty, self.object_hash),
            )["plan"]
            current_body = _place_request(current, self.object_hash, bar=2)
            stale = (
                {**current_body, "plan_id": _different(current["plan_id"])},
                {
                    **current_body,
                    "plan_sha256": _different(current["plan_sha256"]),
                },
                {**current_body, "expected_revision": current["revision"] - 1},
                {**current_body, "clip_object_sha256": "f" * 64},
            )
            for body in stale:
                with self.subTest(body=body):
                    status, _headers, payload = _json_request(
                        server,
                        "POST",
                        f"/api/clip-reuse-action?token={self.token}",
                        body,
                    )
                    self.assertEqual(status, 409)
                    self.assertEqual(payload, _STALE_PLAN)
            self.assertEqual(
                _get_plan(server, self.token)["plan_sha256"],
                current["plan_sha256"],
            )

    def test_plan_orders_by_target_and_a_changed_binding_starts_empty(self) -> None:
        state = self.root / "binding-and-order-state"
        with self._server(state) as server:
            plan = _get_plan(server, self.token)
            later = _post_action(
                server,
                self.token,
                _place_request(plan, self.object_hash, bar=3),
            )["plan"]
            ordered = _post_action(
                server,
                self.token,
                _place_request(later, self.object_hash, bar=1),
            )["plan"]
            self.assertEqual(
                [item["target"]["start_tick"] for item in ordered["placements"]],
                [0, 3_840],
            )
            original_plan_id = ordered["plan_id"]

        changed_catalog = copy.deepcopy(self.catalog)
        changed_catalog["setup"]["key"] = "C major"
        with _running_server(
            changed_catalog,
            state,
            self.token,
            clip_library_path=self.library,
            phase6_acceptance_path=self.acceptance,
            phase6_pack_path=self.pack,
            enable_clip_reuse_plan=True,
        ) as restarted:
            changed = _get_plan(restarted, self.token)
            self.assertEqual(changed["restore_status"], "empty-new-scope")
            self.assertEqual(changed["revision"], 0)
            self.assertEqual(changed["placements"], [])
            self.assertNotEqual(changed["plan_id"], original_plan_id)

    def test_unknown_clip_and_placement_are_fixed_404s(self) -> None:
        with self._server(self.root / "unknown-state") as server:
            plan = _get_plan(server, self.token)
            unknown_clip = _place_request(plan, "e" * 64)
            unknown_clip["clip_id"] = "clip-that-does-not-exist"
            status, _headers, payload = _json_request(
                server,
                "POST",
                f"/api/clip-reuse-action?token={self.token}",
                unknown_clip,
            )
            self.assertEqual(status, 404)
            self.assertEqual(payload, _UNKNOWN_CLIP)

            placed = _post_action(
                server,
                self.token,
                _place_request(plan, self.object_hash),
            )["plan"]
            missing_placement = _different(placed["placements"][0]["placement_id"])
            status, _headers, payload = _json_request(
                server,
                "POST",
                f"/api/clip-reuse-action?token={self.token}",
                _remove_request(placed, missing_placement),
            )
            self.assertEqual(status, 404)
            self.assertEqual(payload, _UNKNOWN_PLACEMENT)

    def test_reuse_writes_are_separate_from_decisions_pack_and_clips(self) -> None:
        state = self.root / "separation-state"
        library_before = _tree_fingerprint(self.library)
        source_before = _file_sha256(Path(self.catalog["stems"][0]["source_path"]))
        candidate_before = _file_sha256(
            Path(self.catalog["stems"][0]["candidates"][0]["midi_path"])
        )
        with self._server(state) as server:
            project_before = _project(server, self.token)
            status, _headers, pack_before = _json_request(
                server,
                "GET",
                f"/api/garageband-pack-plan?token={self.token}",
            )
            self.assertEqual(status, 200)
            events_before = server.store.events(self.catalog["project_id"])
            workbench_database_before = _file_sha256(server.store.path)

            plan = _get_plan(server, self.token)
            response = _post_action(
                server,
                self.token,
                _place_request(plan, self.object_hash),
            )
            _assert_action_response(
                self,
                response,
                added=True,
                root=self.root,
                token=self.token,
            )

            project_after = _project(server, self.token)
            status, _headers, pack_after = _json_request(
                server,
                "GET",
                f"/api/garageband-pack-plan?token={self.token}",
            )
            self.assertEqual(status, 200)
            self.assertEqual(events_before, server.store.events(self.catalog["project_id"]))
            self.assertEqual(workbench_database_before, _file_sha256(server.store.path))
            self.assertEqual(pack_before, pack_after)
            for key in (
                "state",
                "home",
                "contribution_preview",
                "review_status",
                "selected_midi_overlap",
                "decoded_arrangement_selection",
                "arrangement",
            ):
                self.assertEqual(project_before[key], project_after[key])

        self.assertEqual(library_before, _tree_fingerprint(self.library))
        self.assertEqual(
            source_before,
            _file_sha256(Path(self.catalog["stems"][0]["source_path"])),
        )
        self.assertEqual(
            candidate_before,
            _file_sha256(
                Path(self.catalog["stems"][0]["candidates"][0]["midi_path"])
            ),
        )
        reuse_database = state / "phase6-reuse" / "reuse.sqlite3"
        self.assertTrue(reuse_database.is_file())
        self.assertNotEqual(
            reuse_database.resolve(),
            (state / "workbench.sqlite3").resolve(),
        )

    def test_fixed_bounds_reject_the_65th_placement_and_twenty_minute_end(self) -> None:
        with self._server(self.root / "placement-limit-state") as server:
            plan = _get_plan(server, self.token)
            for _index in range(64):
                plan = _post_action(
                    server,
                    self.token,
                    _place_request(plan, self.object_hash),
                )["plan"]
            self.assertEqual(plan["revision"], 64)
            self.assertEqual(len(plan["placements"]), 64)
            status, _headers, payload = _json_request(
                server,
                "POST",
                f"/api/clip-reuse-action?token={self.token}",
                _place_request(plan, self.object_hash),
            )
            self.assertEqual(status, 400)
            self.assertEqual(payload, _INVALID_ACTION)
            self.assertEqual(_get_plan(server, self.token)["revision"], 64)

        with self._server(self.root / "duration-limit-state") as server:
            plan = _get_plan(server, self.token)
            for bar in (10_000, 10**400):
                with self.subTest(bar_digits=len(str(bar))):
                    status, _headers, payload = _json_request(
                        server,
                        "POST",
                        f"/api/clip-reuse-action?token={self.token}",
                        _place_request(plan, self.object_hash, bar=bar),
                    )
                    self.assertEqual(status, 400)
                    self.assertEqual(payload, _INVALID_ACTION)
            self.assertEqual(_get_plan(server, self.token)["revision"], 0)

        with self._server(self.root / "exact-duration-boundary-state") as server:
            plan = _get_plan(server, self.token)
            exact = _post_action(
                server,
                self.token,
                _place_request(plan, self.object_hash, bar=595, beat=4),
            )["plan"]
            self.assertEqual(
                exact["placements"][0]["target"]["nominal_end_tick"],
                1_142_400,
            )

        with self._server(self.root / "after-duration-boundary-state") as server:
            plan = _get_plan(server, self.token)
            status, _headers, payload = _json_request(
                server,
                "POST",
                f"/api/clip-reuse-action?token={self.token}",
                _place_request(plan, self.object_hash, bar=596, beat=1),
            )
            self.assertEqual(status, 400)
            self.assertEqual(payload, _INVALID_ACTION)
            self.assertEqual(_get_plan(server, self.token)["revision"], 0)

    def test_confirmed_project_downbeat_is_disclosed_but_not_applied(self) -> None:
        catalog = json.loads(json.dumps(self.catalog))
        catalog["setup"]["downbeat"] = 0.75
        with _running_server(
            catalog,
            self.root / "confirmed-downbeat-state",
            self.token,
            clip_library_path=self.library,
            phase6_acceptance_path=self.acceptance,
            phase6_pack_path=self.pack,
            enable_clip_reuse_plan=True,
        ) as server:
            plan = _get_plan(server, self.token)
            plan_warning_codes = {
                warning["code"] for warning in plan["warnings"]
            }
            self.assertIn("project-downbeat-not-applied", plan_warning_codes)
            self.assertNotIn("project-downbeat-unconfirmed", plan_warning_codes)

            placed = _post_action(
                server,
                self.token,
                _place_request(plan, self.object_hash),
            )["plan"]
            compatibility_codes = {
                warning["code"]
                for warning in placed["placements"][0]["compatibility"]["warnings"]
            }
            self.assertIn("project-downbeat-not-applied", compatibility_codes)
            self.assertNotIn("project-downbeat-unconfirmed", compatibility_codes)

    def test_note_count_and_total_note_instance_bounds(self) -> None:
        large_root = self.root / "large-note-count"
        large_root.mkdir()
        large_library, large_hash = _clip_library(
            large_root,
            clip_id="clip-too-large",
            note_count=20_001,
        )
        with self._server(
            self.root / "large-note-state",
            library=large_library,
        ) as server:
            plan = _get_plan(server, self.token)
            status, _headers, payload = _json_request(
                server,
                "POST",
                f"/api/clip-reuse-action?token={self.token}",
                _place_request(
                    plan,
                    large_hash,
                    clip_id="clip-too-large",
                ),
            )
            self.assertEqual(status, 400)
            self.assertEqual(payload, _INVALID_ACTION)
            self.assertEqual(_get_plan(server, self.token)["revision"], 0)

        instance_root = self.root / "note-instances"
        instance_root.mkdir()
        instance_library, instance_hash = _clip_library(
            instance_root,
            clip_id="clip-ten-thousand",
            note_count=10_000,
        )
        with self._server(
            self.root / "note-instance-state",
            library=instance_library,
        ) as server:
            plan = _get_plan(server, self.token)
            for bar in range(1, 5):
                plan = _post_action(
                    server,
                    self.token,
                    _place_request(
                        plan,
                        instance_hash,
                        clip_id="clip-ten-thousand",
                        bar=bar,
                    ),
                )["plan"]
            self.assertEqual(plan["revision"], 4)
            status, _headers, payload = _json_request(
                server,
                "POST",
                f"/api/clip-reuse-action?token={self.token}",
                _place_request(
                    plan,
                    instance_hash,
                    clip_id="clip-ten-thousand",
                    bar=5,
                ),
            )
            self.assertEqual(status, 400)
            self.assertEqual(payload, _INVALID_ACTION)
            self.assertEqual(_get_plan(server, self.token)["revision"], 4)

    def test_library_drift_fails_closed_with_a_fixed_conflict(self) -> None:
        with self._server(self.root / "drift-state") as server:
            object_path = self.library / "objects" / self.object_hash[:2] / (
                f"{self.object_hash}.json"
            )
            object_path.write_bytes(b"changed immutable object")
            for method, route, body in (
                ("GET", "/api/clip-reuse-plan", None),
                (
                    "POST",
                    "/api/clip-reuse-action",
                    {
                        "action": "place",
                        "plan_id": "unavailable",
                        "plan_sha256": "0" * 64,
                        "expected_revision": 0,
                        "clip_id": "clip-1",
                        "clip_object_sha256": self.object_hash,
                        "target": {"bar": 1, "beat": 1, "tick_in_beat": 0},
                    },
                ),
            ):
                with self.subTest(method=method):
                    status, _headers, payload = _json_request(
                        server,
                        method,
                        f"{route}?token={self.token}",
                        body,
                    )
                    self.assertEqual(status, 409)
                    self.assertEqual(payload, _DRIFT)
                    _assert_path_free(self, payload, root=self.root, token=self.token)

    def test_source_and_setup_file_drift_fail_closed(self) -> None:
        evidence_files = {
            "source": Path(self.catalog["stems"][0]["source_path"]),
            "setup": Path(self.catalog["setup"]["files"][0]["path"]),
        }
        for label, evidence_path in evidence_files.items():
            with self.subTest(label=label):
                original = evidence_path.read_bytes()
                try:
                    with self._server(self.root / f"{label}-drift-state") as server:
                        _get_plan(server, self.token)
                        evidence_path.write_bytes(original + b"changed")
                        status, _headers, payload = _json_request(
                            server,
                            "GET",
                            f"/api/clip-reuse-plan?token={self.token}",
                        )
                        self.assertEqual(status, 409)
                        self.assertEqual(payload, _DRIFT)
                finally:
                    evidence_path.write_bytes(original)

    def test_developer_inspector_reports_reuse_state_without_an_effect(self) -> None:
        with self._server(
            self.root / "developer-state",
            developer_inspector=True,
        ) as server:
            plan = _get_plan(server, self.token)
            _post_action(
                server,
                self.token,
                _place_request(plan, self.object_hash),
            )
            status, _headers, snapshot = _json_request(
                server,
                "GET",
                f"/api/developer-snapshot?token={self.token}",
            )
            self.assertEqual(status, 200)
            runtime = snapshot["runtime"]
            self.assertTrue(runtime["clip_reuse_plan_enabled"])
            self.assertEqual(runtime["clip_reuse_plan_revision"], 1)
            self.assertEqual(runtime["clip_reuse_active_placement_count"], 1)
            durable = snapshot["current"]["durable_state"]["clip_reuse_plan"]
            self.assertTrue(durable["enabled"])
            self.assertTrue(durable["proposal_only"])
            self.assertEqual(durable["revision"], 1)
            self.assertEqual(durable["active_placement_count"], 1)
            operations = {
                row["operation"]
                for row in runtime["trace"]["recent_operations"]
            }
            self.assertIn("clip_reuse.read", operations)
            self.assertIn("clip_reuse.change", operations)
            self.assertFalse(snapshot["effects"]["clip_reuse_plan_changed"])
            _assert_path_free(self, snapshot, root=self.root, token=self.token)

            before = _get_plan(server, self.token)
            status, _headers, _snapshot = _json_request(
                server,
                "GET",
                f"/api/developer-snapshot?token={self.token}",
            )
            self.assertEqual(status, 200)
            after = _get_plan(server, self.token)
            self.assertEqual(before, after)

    def _server(
        self,
        state_dir: Path,
        *,
        library: Path | None = None,
        developer_inspector: bool = False,
    ) -> _running_server:
        return _running_server(
            self.catalog,
            state_dir,
            self.token,
            clip_library_path=self.library if library is None else library,
            phase6_acceptance_path=self.acceptance,
            phase6_pack_path=self.pack,
            enable_clip_reuse_plan=True,
            developer_inspector=developer_inspector,
        )


class _running_server:
    def __init__(
        self,
        catalog: dict,
        state_dir: Path,
        token: str,
        *,
        clip_library_path: Path | None = None,
        phase6_acceptance_path: Path | None = None,
        phase6_pack_path: Path | None = None,
        enable_clip_reuse_plan: bool = False,
        developer_inspector: bool = False,
    ) -> None:
        self._verification_patch = patch(
            "sunofriend.workbench_clips.verify_garageband_pack_archive",
            return_value={"status": "verified"},
        )
        self._verification_patch.start()
        try:
            self.server = create_workbench_server(
                catalog,
                state_dir=state_dir,
                token=token,
                clip_library_path=clip_library_path,
                phase6_acceptance_path=phase6_acceptance_path,
                phase6_pack_path=phase6_pack_path,
                enable_clip_reuse_plan=enable_clip_reuse_plan,
                developer_inspector=developer_inspector,
            )
        except Exception:
            self._verification_patch.stop()
            raise
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self.server

    def __exit__(self, *_args) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self._verification_patch.stop()


def _request(
    server,
    method: str,
    route: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection(
        "127.0.0.1", server.server_port, timeout=20
    )
    try:
        connection.request(method, route, body=body, headers=headers or {})
        response = connection.getresponse()
        return (
            response.status,
            {name.lower(): value for name, value in response.getheaders()},
            response.read(),
        )
    finally:
        connection.close()


def _json_request(
    server,
    method: str,
    route: str,
    value: dict | None = None,
) -> tuple[int, dict[str, str], dict]:
    body = None if value is None else json.dumps(value).encode("utf-8")
    headers = {} if body is None else {"Content-Type": "application/json"}
    status, response_headers, payload = _request(
        server,
        method,
        route,
        body=body,
        headers=headers,
    )
    return status, response_headers, json.loads(payload.decode("utf-8"))


def _project(server, token: str) -> dict:
    status, _headers, payload = _json_request(
        server,
        "GET",
        f"/api/project?token={token}",
    )
    if status != 200:
        raise AssertionError(f"project request failed with {status}: {payload}")
    return payload


def _get_plan(server, token: str) -> dict:
    status, _headers, payload = _json_request(
        server,
        "GET",
        f"/api/clip-reuse-plan?token={token}",
    )
    if status != 200:
        raise AssertionError(f"reuse plan request failed with {status}: {payload}")
    if set(payload) != {"plan"}:
        raise AssertionError(f"unexpected reuse plan response: {payload}")
    return payload["plan"]


def _post_action(server, token: str, request: dict) -> dict:
    status, _headers, payload = _json_request(
        server,
        "POST",
        f"/api/clip-reuse-action?token={token}",
        request,
    )
    if status != 201:
        raise AssertionError(f"reuse action failed with {status}: {payload}")
    if set(payload) != {"operation", "plan", "effects"}:
        raise AssertionError(f"unexpected reuse action response: {payload}")
    return payload


def _place_request(
    plan: dict,
    object_hash: str,
    *,
    clip_id: str = "clip-1",
    bar: int = 1,
    beat: int = 1,
) -> dict:
    return {
        "action": "place",
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "expected_revision": plan["revision"],
        "clip_id": clip_id,
        "clip_object_sha256": object_hash,
        "target": {"bar": bar, "beat": beat, "tick_in_beat": 0},
    }


def _remove_request(plan: dict, placement_id: str) -> dict:
    return {
        "action": "remove",
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "expected_revision": plan["revision"],
        "placement_id": placement_id,
    }


def _assert_action_response(
    case: unittest.TestCase,
    payload: dict,
    *,
    added: bool = False,
    removed: bool = False,
    root: Path,
    token: str,
) -> None:
    effects = payload["effects"]
    case.assertEqual(payload["operation"], "place" if added else "remove")
    case.assertTrue(effects["reuse_plan_changed"])
    case.assertIs(effects["placement_added"], added)
    case.assertIs(effects["placement_removed"], removed)
    expected_true = {"reuse_plan_changed"}
    if added:
        expected_true.add("placement_added")
    if removed:
        expected_true.add("placement_removed")
    case.assertEqual(set(effects), _EFFECT_KEYS)
    case.assertEqual(
        {key for key, value in effects.items() if value is True},
        expected_true,
    )
    case.assertTrue(
        all(effects[key] is False for key in _EFFECT_KEYS - expected_true)
    )
    case.assertTrue(all(isinstance(value, bool) for value in effects.values()))
    _assert_path_free(case, payload, root=root, token=token)


def _placement_start_tick(placement: dict) -> int:
    if "start_tick" in placement:
        return int(placement["start_tick"])
    return int(placement["target"]["start_tick"])


def _different(value: str) -> str:
    if not value:
        return "different"
    replacement = "0" if value[-1] != "0" else "1"
    return value[:-1] + replacement


def _append_only_row_count(database: Path) -> int:
    with sqlite3.connect(database) as connection:
        tables = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        counts = [
            int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in tables
        ]
    return max(counts, default=0)


def _assert_path_free(
    case: unittest.TestCase,
    payload: object,
    *,
    root: Path,
    token: str,
) -> None:
    encoded = json.dumps(payload, sort_keys=True)
    case.assertNotIn(str(root), encoded)
    case.assertNotIn(str(root.resolve()), encoded)
    case.assertNotIn(token, encoded)
    case.assertFalse(_contains_key(payload, "path"))


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


def _catalog(root: Path) -> dict:
    project = root / "Reuse Server Song-B major-119bpm-440hz"
    candidates = root / "candidates"
    project.mkdir()
    candidates.mkdir()
    source = project / "Reuse Server Song-bass-B major-119bpm-440hz.wav"
    source.write_bytes(b"RIFF-phase6-reuse-source")
    (project / "chords.txt").write_text("B major\n", encoding="utf-8")
    midi = candidates / "bass.mid"
    write_midi_file(
        midi,
        [MidiTrack("Bass", 0, 38, [NoteEvent(0.0, 0.5, 38, 90)])],
        bpm=119.0,
    )
    catalog_path = root / "catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "schema": "sunofriend.workbench-catalog.v1",
                "stems": [
                    {
                        "source": str(source),
                        "role": "bass",
                        "candidates": [{"midi": str(midi), "label": "Method A"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return build_workbench_catalog(
        project,
        candidate_roots=[candidates],
        catalog_path=catalog_path,
    )


def _clip_library(
    root: Path,
    *,
    clip_id: str = "clip-1",
    note_count: int = 1,
) -> tuple[Path, str]:
    library_root = root / "library"
    tempo = TempoMap.constant(119.0)
    note = ClipNote.from_beats(0.0, 1.0, 38, 90, tempo)
    summary = ClipLibrary(library_root).add(
        MidiClip(
            title="Golden bass",
            tempo_map=tempo,
            time_signature=TimeSignature(),
            instrument=Instrument("bass", 38, 0),
            notes=(note,) * note_count,
            clip_id=clip_id,
            tags=("reviewed",),
        )
    )
    return library_root, summary.object_hash


def _phase6_acceptance(root: Path) -> tuple[Path, Path]:
    pack = root / "accepted.zip"
    pack.write_bytes(b"exact accepted pack")
    acceptance = root / "acceptance.json"
    acceptance.write_text(
        json.dumps(
            {
                "schema": (
                    "sunofriend.workbench-garageband-pack-acceptance-result.v1"
                ),
                "operation": "garageband-pack-acceptance-resolve",
                "status": "passed",
                "phase6_read_only_clip_entry_ready": True,
                "explicit_hybrid_construction_ready": False,
                "pack": {
                    "name": "sunofriend-garageband-pack.zip",
                    "bytes": pack.stat().st_size,
                    "sha256": _file_sha256(pack),
                },
                "developer_evidence": {"code_binding_sha256": "a" * 64},
                "tutorial": {"completed": True, "slide_count": 8},
                "quiz": {
                    "question_count": 10,
                    "score": 10,
                    "pass_score": 10,
                    "passed": True,
                },
                "acceptance_checks": [
                    {
                        "check_id": "garageband-pack",
                        "outcome": "passed",
                        "pass_count": 6,
                        "issue_count": 0,
                        "cannot_tell_count": 0,
                    },
                    {
                        "check_id": "local-usability",
                        "outcome": "passed",
                        "pass_count": 6,
                        "issue_count": 0,
                        "cannot_tell_count": 0,
                    },
                ],
                "remaining_local_studio_acceptance_gates": [],
                "effects": {
                    "tutorial_changed_project": False,
                    "quiz_selected_candidate": False,
                    "feedback_recorded": False,
                    "musical_selection_changed": False,
                    "pack_basket_changed": False,
                    "midi_mutated": False,
                    "candidate_promoted": False,
                    "default_changed": False,
                    "data_submitted": False,
                    "phase6_started_automatically": False,
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return pack, acceptance


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_fingerprint(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _file_sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
        # SQLite read-only WAL clients may update shared-memory coordination
        # bytes.  They do not mutate the catalog or immutable Clip objects.
        and not path.name.endswith(("-shm", "-wal"))
    }
