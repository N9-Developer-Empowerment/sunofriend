from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from sunofriend.cli import build_parser
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.workbench_catalog import build_workbench_catalog
from sunofriend.workbench_developer import (
    WorkbenchDeveloperTrace,
    artifact_cache_summary,
    build_developer_snapshot,
    developer_code_step_for_route,
    developer_operation_for_route,
    trace_response_facts,
)
from sunofriend.workbench_server import create_workbench_server
from sunofriend.workbench_store import WorkbenchStore, fold_workbench_events


class WorkbenchDeveloperServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.catalog = _catalog(self.root)
        self.token = "developer-secret-token"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_inspector_is_disabled_by_default(self) -> None:
        with _running_server(
            self.catalog,
            self.root / "disabled-state",
            self.token,
            developer_inspector=False,
        ) as server:
            status, payload = _request(
                server, "GET", f"/api/developer-snapshot?token={self.token}"
            )
            self.assertEqual(status, 404)
            self.assertEqual(payload, {"error": "workbench route not found"})

            status, project = _request(
                server, "GET", f"/api/project?token={self.token}"
            )
            self.assertEqual(status, 200)
            self.assertEqual(
                project["developer"],
                {
                    "enabled": False,
                    "read_only": True,
                    "snapshot_endpoint": None,
                },
            )

    def test_snapshot_is_read_only_path_note_and_token_free(self) -> None:
        state_dir = self.root / "enabled-state"
        with _running_server(
            self.catalog,
            state_dir,
            self.token,
            developer_inspector=True,
        ) as server:
            status, project = _request(
                server, "GET", f"/api/project?token={self.token}"
            )
            self.assertEqual(status, 200)
            self.assertEqual(
                project["developer"],
                {
                    "enabled": True,
                    "read_only": True,
                    "snapshot_endpoint": "/api/developer-snapshot",
                },
            )
            stem = self.catalog["stems"][0]
            candidate = stem["candidates"][0]
            private_note = (
                "PRIVATE_NOTE /Users/alice/private/song.wav " + self.token
            )
            status, _ = _request(
                server,
                "POST",
                f"/api/events?token={self.token}",
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "main",
                    "context": "solo",
                    "problem_tags": ["missing_notes"],
                    "notes": private_note,
                },
            )
            self.assertEqual(status, 201)
            before_events = server.store.events(self.catalog["project_id"])
            before_basket_rows = _pack_row_count(server.store.path)
            before_artifacts = sorted(
                path.relative_to(server.artifacts.root).as_posix()
                for path in server.artifacts.root.rglob("*")
            )

            status, snapshot = _request(
                server, "GET", f"/api/developer-snapshot?token={self.token}"
            )
            self.assertEqual(status, 200)
            self.assertEqual(
                snapshot["schema"],
                "sunofriend.workbench-developer-snapshot.v1",
            )
            encoded = json.dumps(snapshot, sort_keys=True)
            self.assertNotIn("PRIVATE_NOTE", encoded)
            self.assertNotIn("/Users/alice", encoded)
            self.assertNotIn(self.token, encoded)
            self.assertNotIn('"notes"', encoded)
            self.assertFalse(snapshot["effects"]["workbench_event_appended"])
            self.assertFalse(snapshot["effects"]["artifact_built"])
            self.assertEqual(
                snapshot["current"]["durable_state"]["decision_event_count"],
                1,
            )
            saved = snapshot["current"]["derived_state"]["stems"][0][
                "saved_candidates"
            ][0]
            self.assertEqual(saved["decision"], "main")
            self.assertEqual(saved["problem_tags"], ["missing_notes"])
            nodes = snapshot["code_flow"]["nodes"]
            self.assertEqual(len(nodes), 5)
            self.assertTrue(all(node["symbols"] for node in nodes))
            self.assertTrue(
                all(
                    "/" not in symbol and "\\" not in symbol
                    for node in nodes
                    for symbol in node["symbols"]
                )
            )
            replay = snapshot["state_replay"]
            self.assertEqual(replay["total_event_count"], 1)
            self.assertEqual(len(replay["frames"]), 2)
            self.assertEqual(
                replay["frames"][-1]["event"]["event_type"],
                "candidate_decision",
            )
            self.assertEqual(replay["frames"][-1]["after"]["event_count"], 1)
            self.assertEqual(
                replay["frames"][-1]["after"]["changed_stem"][
                    "main_candidate_id"
                ],
                candidate["candidate_id"],
            )
            operations = snapshot["runtime"]["trace"]["recent_operations"]
            self.assertEqual(
                [row["operation"] for row in operations],
                ["project.read", "decision.append"],
            )
            self.assertEqual(before_events, server.store.events(self.catalog["project_id"]))
            self.assertEqual(before_basket_rows, _pack_row_count(server.store.path))
            self.assertEqual(
                before_artifacts,
                sorted(
                    path.relative_to(server.artifacts.root).as_posix()
                    for path in server.artifacts.root.rglob("*")
                ),
            )

            status, second = _request(
                server, "GET", f"/api/developer-snapshot?token={self.token}"
            )
            self.assertEqual(status, 200)
            self.assertEqual(
                second["runtime"]["trace"]["recent_operations"], operations
            )

    def test_endpoint_remains_token_protected_and_get_only(self) -> None:
        with _running_server(
            self.catalog,
            self.root / "protected-state",
            self.token,
            developer_inspector=True,
        ) as server:
            status, _ = _request(
                server, "GET", "/api/developer-snapshot?token=wrong"
            )
            self.assertEqual(status, 403)
            status, _ = _request(
                server,
                "POST",
                f"/api/developer-snapshot?token={self.token}",
                {},
            )
            self.assertEqual(status, 404)


class WorkbenchDeveloperTraceTests(unittest.TestCase):
    def test_clip_routes_have_static_read_only_operation_identities(self) -> None:
        self.assertEqual(
            developer_operation_for_route("/api/clips"),
            "clip_library.browse",
        )
        self.assertEqual(
            developer_operation_for_route("/api/clips/clip-1"),
            "clip_library.detail",
        )
        self.assertEqual(
            developer_code_step_for_route("/api/clips/clip-1"),
            "clip_library.detail",
        )
        self.assertEqual(
            developer_operation_for_route("/api/clip-artifact"),
            "clip_library.artifact",
        )
        self.assertEqual(
            trace_response_facts(
                "/api/clips",
                {
                    "schema": "sunofriend.workbench-clip-browse.v1",
                    "page": {"returned": 3},
                },
            ),
            {
                "schema": "sunofriend.workbench-clip-browse.v1",
                "item_count": 3,
            },
        )

    def test_clip_reuse_routes_have_separate_read_and_durable_change_identities(
        self,
    ) -> None:
        self.assertEqual(
            developer_operation_for_route("/api/clip-reuse-plan"),
            "clip_reuse.read",
        )
        self.assertEqual(
            developer_code_step_for_route("/api/clip-reuse-plan"),
            "clip_reuse.read",
        )
        self.assertEqual(
            developer_operation_for_route("/api/clip-reuse-action"),
            "clip_reuse.change",
        )
        self.assertEqual(
            developer_code_step_for_route("/api/clip-reuse-action"),
            "clip_reuse.change",
        )

        trace = WorkbenchDeveloperTrace()
        read = trace.begin("GET", "clip_reuse.read")
        change = trace.begin("POST", "clip_reuse.change")
        trace.complete(read, 200)
        trace.complete(change, 201)
        operations = trace.snapshot()["recent_operations"]

        self.assertFalse(operations[0]["durable_effect_possible"])
        self.assertTrue(operations[1]["durable_effect_possible"])
        self.assertIn(
            "sunofriend.workbench_reuse.WorkbenchClipReuseService.plan",
            operations[0]["symbols"],
        )
        self.assertIn(
            "sunofriend.workbench_reuse.WorkbenchClipReuseService.apply",
            operations[1]["symbols"],
        )

    def test_clip_reuse_response_facts_accept_get_and_post_wrappers_only(self) -> None:
        plan = {
            "schema": "sunofriend.workbench-clip-reuse-plan.v1",
            "revision": 4,
            "placements": [
                {
                    "placement_id": "placement-1",
                    "private_path": "/Users/alice/private/clip.mid",
                },
                {
                    "placement_id": "placement-2",
                    "notes": "private listening note",
                },
            ],
        }
        expected = {
            "schema": "sunofriend.workbench-clip-reuse-plan.v1",
            "plan_revision": 4,
            "active_placement_count": 2,
        }

        self.assertEqual(
            trace_response_facts("/api/clip-reuse-plan", {"plan": plan}),
            expected,
        )
        self.assertEqual(
            trace_response_facts(
                "/api/clip-reuse-action",
                {
                    "operation": {
                        "action": "place",
                        "source_path": "/Users/alice/private/clip.mid",
                    },
                    "plan": plan,
                    "effects": {
                        "reuse_plan_changed": True,
                        "private_note": "must not be traced",
                    },
                },
            ),
            expected,
        )

    def test_clip_reuse_snapshot_is_a_path_free_bounded_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            catalog = _catalog(Path(temporary))
            current = fold_workbench_events(catalog, [])
            snapshot = build_developer_snapshot(
                catalog,
                current,
                events=[],
                arrangement_selection=None,
                pack_plan=None,
                clip_reuse_plan={
                    "schema": "sunofriend.workbench-clip-reuse-plan.v1",
                    "proposal_only": True,
                    "plan_id": "plan-6.1",
                    "binding_sha256": "a" * 64,
                    "plan_sha256": "b" * 64,
                    "revision": 7,
                    "restore_status": "restored-exact-scope",
                    "binding": {
                        "source_path": "/Users/alice/private/song.wav",
                        "private_note": "binding details stay private",
                    },
                    "placements": [
                        {
                            "placement_id": "placement-1",
                            "source_path": "/Users/alice/private/clip.mid",
                        },
                        {
                            "placement_id": "placement-2",
                            "notes": "private listening note",
                        },
                    ],
                },
                trace={},
                runtime={
                    "clip_reuse_plan_enabled": True,
                    "clip_reuse_plan_revision": 7,
                    "clip_reuse_active_placement_count": 2,
                    "source_path": "/Users/alice/private/song.wav",
                    "placements": [{"private": "must not escape"}],
                },
                cache={"families": []},
            )

            self.assertEqual(
                snapshot["current"]["durable_state"]["clip_reuse_plan"],
                {
                    "enabled": True,
                    "proposal_only": True,
                    "plan_id": "plan-6.1",
                    "binding_sha256": "a" * 64,
                    "plan_sha256": "b" * 64,
                    "revision": 7,
                    "active_placement_count": 2,
                    "restore_status": "restored-exact-scope",
                },
            )
            self.assertEqual(
                {
                    key: snapshot["runtime"][key]
                    for key in (
                        "clip_reuse_plan_enabled",
                        "clip_reuse_plan_revision",
                        "clip_reuse_active_placement_count",
                    )
                },
                {
                    "clip_reuse_plan_enabled": True,
                    "clip_reuse_plan_revision": 7,
                    "clip_reuse_active_placement_count": 2,
                },
            )
            self.assertFalse(snapshot["effects"]["clip_reuse_plan_changed"])
            encoded = json.dumps(snapshot, sort_keys=True)
            for forbidden in (
                "/Users/alice",
                "private listening note",
                "binding details stay private",
                '"placements"',
                '"source_path"',
            ):
                self.assertNotIn(forbidden, encoded)

    def test_trace_is_bounded_and_has_running_then_completed_state(self) -> None:
        trace = WorkbenchDeveloperTrace()
        active = trace.begin("POST", "preview.render")
        self.assertIsNotNone(active)
        running = trace.snapshot()
        self.assertEqual(running["active_operations"][0]["status"], "running")
        trace.checkpoint(active, "result", "artifact.prepare", {"cache_hit": False})
        trace.complete(active, 200)
        self.assertEqual(trace.snapshot()["recent_operations"][-1]["status"], "completed")

        for _ in range(140):
            sequence = trace.begin("GET", "project.read")
            trace.complete(sequence, 200)
        snapshot = trace.snapshot()
        self.assertEqual(len(snapshot["recent_operations"]), 128)
        self.assertEqual(snapshot["dropped_completed_count"], 13)

    def test_cache_summary_does_not_follow_or_name_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previews = root / "previews"
            previews.mkdir()
            (previews / ("a" * 64)).mkdir()
            (previews / ("." + "b" * 64 + ".building-one")).mkdir()
            outside = root / "outside-private"
            outside.mkdir()
            (previews / "private-link").symlink_to(outside, target_is_directory=True)

            summary = artifact_cache_summary(root, verified_stream_entries=2)
            encoded = json.dumps(summary, sort_keys=True)
            preview = next(
                row for row in summary["families"] if row["family"] == "previews"
            )
            self.assertEqual(preview["completed_entry_count"], 1)
            self.assertEqual(preview["building_entry_count"], 1)
            self.assertGreaterEqual(preview["ignored_entry_count"], 1)
            self.assertNotIn("private-link", encoded)
            self.assertNotIn("outside-private", encoded)

    def test_state_replay_is_bounded_and_uses_the_shared_reducer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            catalog = _catalog(Path(temporary))
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            events = [
                {
                    "event_type": "candidate_auditioned",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "payload": {},
                }
                for _ in range(140)
            ]
            current = fold_workbench_events(catalog, events)
            snapshot = build_developer_snapshot(
                catalog,
                current,
                events=events,
                arrangement_selection=None,
                pack_plan=None,
                trace={},
                runtime={},
                cache={"families": []},
            )

            replay = snapshot["state_replay"]
            self.assertEqual(replay["frame_limit"], 128)
            self.assertEqual(len(replay["frames"]), 128)
            self.assertEqual(replay["retained_event_count"], 127)
            self.assertEqual(replay["omitted_event_count"], 13)
            self.assertEqual(replay["frames"][0]["after"]["event_count"], 13)
            self.assertEqual(replay["frames"][-1]["after"]["event_count"], 140)


class WorkbenchDeveloperReducerTests(unittest.TestCase):
    def test_production_store_and_pure_reducer_derive_identical_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _catalog(root)
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "optional",
                    "context": "full_mix",
                    "problem_tags": ["poor_timing"],
                    "notes": "private reducer note",
                },
            )
            events = store.events(catalog["project_id"])

            self.assertEqual(
                store.current_state(catalog),
                fold_workbench_events(catalog, events),
            )


class WorkbenchDeveloperCliTests(unittest.TestCase):
    def test_cli_flag_is_opt_in(self) -> None:
        parser = build_parser()
        disabled = parser.parse_args(["workbench", "/tmp/project"])
        enabled = parser.parse_args(
            ["workbench", "/tmp/project", "--developer-inspector"]
        )
        self.assertFalse(disabled.developer_inspector)
        self.assertTrue(enabled.developer_inspector)


class _running_server:
    def __init__(
        self,
        catalog: dict,
        state_dir: Path,
        token: str,
        *,
        developer_inspector: bool,
    ) -> None:
        self.server = create_workbench_server(
            catalog,
            state_dir=state_dir,
            token=token,
            developer_inspector=developer_inspector,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )

    def __enter__(self):
        self.thread.start()
        return self.server

    def __exit__(self, *_args) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def _request(server, method: str, route: str, value: dict | None = None):
    connection = http.client.HTTPConnection(
        "127.0.0.1", server.server_port, timeout=10
    )
    headers = {}
    payload = None
    if value is not None:
        payload = json.dumps(value)
        headers["Content-Type"] = "application/json"
    connection.request(method, route, body=payload, headers=headers)
    response = connection.getresponse()
    body = json.loads(response.read().decode("utf-8"))
    status = response.status
    connection.close()
    return status, body


def _catalog(root: Path) -> dict:
    project = root / "Developer Song-D minor-120bpm-440hz"
    candidates = root / "candidates"
    project.mkdir()
    candidates.mkdir()
    source = project / "Developer Song-bass-D minor-120bpm-440hz.wav"
    source.write_bytes(b"RIFF-developer-source")
    midi = candidates / "bass.mid"
    write_midi_file(
        midi,
        [MidiTrack("Bass", 0, 33, [NoteEvent(0.0, 0.5, 38, 90)])],
        bpm=120.0,
    )
    document = root / "catalog.json"
    document.write_text(
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
        catalog_path=document,
    )


def _pack_row_count(database: Path) -> int:
    import sqlite3

    with sqlite3.connect(str(database)) as connection:
        row = connection.execute("SELECT COUNT(*) FROM pack_selection_events").fetchone()
    return int(row[0])


if __name__ == "__main__":
    unittest.main()
