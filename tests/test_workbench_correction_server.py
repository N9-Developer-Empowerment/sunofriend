from __future__ import annotations

import copy
import hashlib
import http.client
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from sunofriend.clip import (
    ClipNote,
    Instrument,
    MidiClip,
    Provenance,
    TempoMap,
    TimeSignature,
)
from sunofriend.cli import build_parser
from sunofriend.library import ClipLibrary
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.workbench_catalog import build_workbench_catalog
from sunofriend.workbench_correction import (
    WorkbenchClipCorrectionConflictError,
    WorkbenchClipCorrectionNotFoundError,
)
from sunofriend.workbench_deletion import (
    CLIP_NOTE_DELETION_RESULT_SCHEMA,
    CLIP_NOTE_DELETION_SUMMARY_SCHEMA,
)
from sunofriend.workbench_onset import (
    CLIP_NOTE_ONSET_RESULT_SCHEMA,
    CLIP_NOTE_ONSET_SUMMARY_SCHEMA,
)
from sunofriend.workbench_developer import (
    developer_code_step_for_route,
    developer_operation_for_route,
    trace_response_facts,
)
from sunofriend.workbench_server import create_workbench_server, run_workbench


_WINDOW_ROUTE = "/api/clip-note-correction-window"
_PROJECTION_ROUTE = "/api/clip-note-correction-projection"
_ACTION_ROUTE = "/api/clip-note-correction-action"
_DISABLED_CAPABILITY = {
    "enabled": False,
    "immutable_versions_only": True,
    "reason": "Clip note corrections were not explicitly enabled for this launch",
}
_INVALID = {"error": "invalid Clip note correction request"}
_NOT_FOUND = {"error": "Clip or note not found"}
_STALE = {
    "error": (
        "Clip correction evidence changed; load the note window and preview again"
    )
}
_DRIFT = {
    "error": (
        "Clip correction evidence changed or is unavailable; restart the Workbench"
    )
}


class WorkbenchClipCorrectionLaunchTests(unittest.TestCase):
    def test_parser_exposes_separate_opt_in_and_excludes_other_write_modes(
        self,
    ) -> None:
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
                "--enable-clip-corrections",
            ]
        )
        self.assertTrue(parsed.enable_clip_corrections)
        self.assertFalse(parsed.enable_clip_reuse_plan)
        self.assertFalse(parsed.enable_clip_transforms)
        default = build_parser().parse_args(["workbench", "/project"])
        self.assertFalse(default.enable_clip_corrections)

        for competing_flag in (
            "--enable-clip-reuse-plan",
            "--enable-clip-transforms",
        ):
            with (
                self.subTest(competing_flag=competing_flag),
                redirect_stderr(StringIO()),
                self.assertRaises(SystemExit),
            ):
                build_parser().parse_args(
                    [
                        "workbench",
                        "/project",
                        competing_flag,
                        "--enable-clip-corrections",
                    ]
                )

    def test_correction_opt_in_requires_phase6_trio_and_live_server(self) -> None:
        catalog = {"project_id": "unused", "stems": []}
        with self.assertRaisesRegex(ValueError, "--enable-clip-corrections requires"):
            create_workbench_server(catalog, enable_clip_corrections=True)

        complete = {
            "clip_library_path": "/tmp/library",
            "phase6_acceptance_path": "/tmp/acceptance.json",
            "phase6_pack_path": "/tmp/pack.zip",
            "enable_clip_corrections": True,
        }
        with self.assertRaisesRegex(ValueError, "live loopback Workbench"):
            run_workbench("/not-read", inspect_only=True, **complete)

        for enabled in (
            {"enable_clip_reuse_plan": True},
            {"enable_clip_transforms": True},
        ):
            with self.subTest(enabled=enabled), self.assertRaisesRegex(
                ValueError, "mutually exclusive"
            ):
                create_workbench_server(catalog, **enabled, **complete)

    def test_enabled_launch_opens_correction_service_against_gated_clip_service(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _catalog(root)
            clip_service = object()
            correction_service = object()
            library = root / "library"
            acceptance = root / "acceptance.json"
            pack_path = root / "pack.zip"
            with (
                patch(
                    "sunofriend.workbench_server.WorkbenchClipService.open",
                    return_value=clip_service,
                ),
                patch(
                    "sunofriend.workbench_server.WorkbenchClipCorrectionService.open",
                    return_value=correction_service,
                ) as opened,
            ):
                server = create_workbench_server(
                    catalog,
                    state_dir=root / "state",
                    token="token",
                    clip_library_path=library,
                    phase6_acceptance_path=acceptance,
                    phase6_pack_path=pack_path,
                    enable_clip_corrections=True,
                )
            try:
                opened.assert_called_once_with(
                    clip_service=clip_service,
                    library_root=library,
                )
                self.assertIs(server.clip_correction_service, correction_service)
                self.assertIsNone(server.clip_reuse_service)
                self.assertIsNone(server.clip_transform_service)
            finally:
                server.server_close()


class WorkbenchClipCorrectionServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.catalog = _catalog(self.root)
        self.token = "phase6-correction-server-token"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_disabled_routes_are_404_before_body_parsing_and_change_nothing(
        self,
    ) -> None:
        with _running_server(
            self.catalog,
            self.root / "disabled-state",
            self.token,
        ) as server:
            before_event_count = len(
                server.store.events(str(self.catalog["project_id"]))
            )
            for route, body in (
                (_WINDOW_ROUTE, b"{"),
                (_PROJECTION_ROUTE, b"[]"),
                (_ACTION_ROUTE, b"x" * (64 * 1024 + 1)),
            ):
                status, payload = _raw_json_request(
                    server,
                    "POST",
                    f"{route}?token={self.token}",
                    body,
                )
                self.assertEqual(status, 404)
                self.assertEqual(payload, {"error": "workbench route not found"})

            status, project = _json_request(
                server,
                "GET",
                f"/api/project?token={self.token}",
            )
            self.assertEqual(status, 200)
            self.assertEqual(project["clip_corrections"], _DISABLED_CAPABILITY)
            self.assertEqual(
                len(server.store.events(str(self.catalog["project_id"]))),
                before_event_count,
            )
            self.assertIsNone(server.clip_correction_service)

    def test_window_preview_and_create_use_fixed_envelopes_under_the_state_lock(
        self,
    ) -> None:
        service = _FakeCorrectionService()
        with _running_server(
            self.catalog,
            self.root / "enabled-state",
            self.token,
            correction_service=service,
        ) as server:
            guard = _ObservedLock()
            server.state_lock = guard
            service.lock_probe = lambda: guard.held

            status, project = _json_request(
                server,
                "GET",
                f"/api/project?token={self.token}",
            )
            self.assertEqual(status, 200)
            self.assertEqual(project["clip_corrections"], service.capability_document)

            window_request = _window_request()
            status, window = _json_request(
                server,
                "POST",
                f"{_WINDOW_ROUTE}?token={self.token}",
                window_request,
            )
            self.assertEqual(status, 200)
            self.assertEqual(window, {"window": service.window_document})
            self.assertEqual(service.window_calls, [window_request])

            preview_request = _preview_request()
            status, preview = _json_request(
                server,
                "POST",
                f"{_PROJECTION_ROUTE}?token={self.token}",
                preview_request,
            )
            self.assertEqual(status, 200)
            self.assertEqual(preview, {"projection": service.projection_document})
            self.assertEqual(service.preview_calls, [preview_request])

            create_request = _create_request()
            status, created = _json_request(
                server,
                "POST",
                f"{_ACTION_ROUTE}?token={self.token}",
                create_request,
            )
            self.assertEqual(status, 201)
            self.assertEqual(created, {"result": service.result_document})
            self.assertEqual(service.create_calls, [create_request])
            self.assertEqual(
                service.lock_observations,
                [
                    ("capability", True),
                    ("window", True),
                    ("preview", True),
                    ("create", True),
                ],
            )
            _assert_path_free_response(
                self,
                created,
                root=self.root,
                token=self.token,
            )

    def test_routes_require_token_object_json_and_bounded_body(self) -> None:
        service = _FakeCorrectionService()
        with _running_server(
            self.catalog,
            self.root / "protected-state",
            self.token,
            correction_service=service,
        ) as server:
            for route in (_WINDOW_ROUTE, _PROJECTION_ROUTE, _ACTION_ROUTE):
                for suffix in ("", "?token=wrong"):
                    status, payload = _json_request(
                        server,
                        "POST",
                        f"{route}{suffix}",
                        {},
                    )
                    self.assertEqual(status, 403)
                    self.assertEqual(
                        payload,
                        {"error": "invalid workbench session token"},
                    )
                for malformed in (b"{", b"[]", b"x" * (64 * 1024 + 1)):
                    status, payload = _raw_json_request(
                        server,
                        "POST",
                        f"{route}?token={self.token}",
                        malformed,
                    )
                    self.assertEqual(status, 400)
                    self.assertEqual(payload, _INVALID)
            self.assertEqual(service.window_calls, [])
            self.assertEqual(service.preview_calls, [])
            self.assertEqual(service.create_calls, [])

    def test_early_rejections_do_not_claim_a_correction_service_checkpoint(
        self,
    ) -> None:
        cases = (
            ("disabled", None, b"{}", 404),
            ("malformed", _FakeCorrectionService(), b"{", 400),
        )
        for name, service, body, expected_status in cases:
            with self.subTest(name=name), _running_server(
                self.catalog,
                self.root / f"early-rejection-{name}",
                self.token,
                correction_service=service,
                developer_inspector=True,
            ) as server:
                status, _payload = _raw_json_request(
                    server,
                    "POST",
                    f"{_ACTION_ROUTE}?token={self.token}",
                    body,
                )
                self.assertEqual(status, expected_status)
                operation = server.developer_trace.snapshot()[
                    "recent_operations"
                ][-1]
                self.assertEqual(operation["operation"], "clip_correction.create")
                self.assertEqual(operation["http_status"], expected_status)
                self.assertEqual(
                    [frame["code_step"] for frame in operation["frames"]],
                    ["request.post"],
                )
                self.assertNotIn(
                    "clip_correction.create",
                    [frame["code_step"] for frame in operation["frames"]],
                )
                if service is not None:
                    self.assertEqual(service.create_calls, [])

    def test_service_failures_map_to_fixed_path_free_400_404_and_409(self) -> None:
        cases = (
            (
                "window",
                WorkbenchClipCorrectionNotFoundError("PRIVATE /Users/alice"),
                404,
                _NOT_FOUND,
            ),
            (
                "preview",
                WorkbenchClipCorrectionConflictError("PRIVATE /Users/alice"),
                409,
                _STALE,
            ),
            ("create", OSError("PRIVATE /Users/alice"), 409, _DRIFT),
            ("window", ValueError("PRIVATE /Users/alice"), 400, _INVALID),
        )
        route_by_operation = {
            "window": _WINDOW_ROUTE,
            "preview": _PROJECTION_ROUTE,
            "create": _ACTION_ROUTE,
        }
        body_by_operation = {
            "window": _window_request,
            "preview": _preview_request,
            "create": _create_request,
        }
        for index, (operation, failure, expected_status, expected) in enumerate(cases):
            with self.subTest(operation=operation, failure=type(failure).__name__):
                service = _FakeCorrectionService()
                service.failures[operation] = failure
                with _running_server(
                    self.catalog,
                    self.root / f"failure-state-{index}",
                    self.token,
                    correction_service=service,
                    developer_inspector=True,
                ) as server:
                    status, payload = _json_request(
                        server,
                        "POST",
                        f"{route_by_operation[operation]}?token={self.token}",
                        body_by_operation[operation](),
                    )
                    self.assertEqual(status, expected_status)
                    self.assertEqual(payload, expected)
                    self.assertNotIn("PRIVATE", json.dumps(payload))
                    self.assertNotIn("/Users/", json.dumps(payload))
                    traced = server.developer_trace.snapshot()[
                        "recent_operations"
                    ][-1]
                    self.assertEqual(traced["http_status"], expected_status)
                    self.assertEqual(
                        [frame["code_step"] for frame in traced["frames"]],
                        [
                            "request.post",
                            "validate",
                            developer_code_step_for_route(
                                route_by_operation[operation]
                            ),
                        ],
                    )

    def test_developer_inspector_marks_only_create_as_durable(self) -> None:
        service = _FakeCorrectionService()
        with _running_server(
            self.catalog,
            self.root / "developer-state",
            self.token,
            correction_service=service,
            developer_inspector=True,
        ) as server:
            private = "/Users/alice/private.mid"
            window = _window_request()
            window["parent_clip_id"] = private
            requests = (
                (_WINDOW_ROUTE, window),
                (_PROJECTION_ROUTE, _preview_request()),
                (_ACTION_ROUTE, _create_request()),
            )
            for route, body in requests:
                status, _payload = _json_request(
                    server,
                    "POST",
                    f"{route}?token={self.token}",
                    body,
                )
                self.assertEqual(status, 201 if route == _ACTION_ROUTE else 200)

            status, snapshot = _json_request(
                server,
                "GET",
                f"/api/developer-snapshot?token={self.token}",
            )
            self.assertEqual(status, 200)
            operations = snapshot["runtime"]["trace"]["recent_operations"][-3:]
            self.assertEqual(
                [row["operation"] for row in operations],
                [
                    "clip_correction.window",
                    "clip_correction.preview",
                    "clip_correction.create",
                ],
            )
            self.assertEqual(
                [row["durable_effect_possible"] for row in operations],
                [False, False, True],
            )
            self.assertNotIn(
                "sunofriend.library.ClipLibrary.append_version_if_state",
                operations[1]["symbols"],
            )
            self.assertIn(
                "sunofriend.library.ClipLibrary.append_version_if_state",
                operations[2]["symbols"],
            )
            self.assertTrue(snapshot["runtime"]["clip_corrections_enabled"])
            self.assertFalse(snapshot["effects"]["clip_version_appended"])
            encoded = json.dumps(snapshot, sort_keys=True)
            self.assertNotIn(private, encoded)
            self.assertNotIn(self.token, encoded)

    def test_python_developer_route_contract_is_static_and_path_free(self) -> None:
        expected = (
            (_WINDOW_ROUTE, "clip_correction.window", False),
            (_PROJECTION_ROUTE, "clip_correction.preview", False),
            (_ACTION_ROUTE, "clip_correction.create", True),
        )
        for route, operation, appended in expected:
            with self.subTest(route=route):
                self.assertEqual(developer_operation_for_route(route), operation)
                self.assertEqual(developer_code_step_for_route(route), operation)
                wrapper = (
                    "window"
                    if route == _WINDOW_ROUTE
                    else "projection"
                    if route == _PROJECTION_ROUTE
                    else "result"
                )
                facts = trace_response_facts(
                    route,
                    {
                        wrapper: {
                            "schema": f"private-{operation}",
                            "path": "/Users/alice/private.mid",
                            "effects": {"library_mutated": appended},
                        }
                    },
                )
                self.assertEqual(
                    facts,
                    {
                        "schema": f"private-{operation}",
                        "clip_version_appended": appended,
                    },
                )

    def test_real_create_replay_restart_and_detail_summary_are_exact(self) -> None:
        library_root, parent_hash = _real_clip_library(self.root)
        pack_path, acceptance = _real_phase6_acceptance(self.root)
        common = {
            "token": self.token,
            "clip_library_path": library_root,
            "phase6_acceptance_path": acceptance,
            "phase6_pack_path": pack_path,
            "enable_clip_corrections": True,
        }
        with patch(
            "sunofriend.workbench_clips.verify_garageband_pack_archive",
            return_value={"status": "verified"},
        ):
            with _running_real_server(
                self.catalog,
                self.root / "real-create-state",
                **common,
            ) as first:
                request = _real_correction_create_request(
                    first,
                    self.token,
                    parent_hash,
                    target_pitch=62,
                )
                status, created = _json_request(
                    first,
                    "POST",
                    f"{_ACTION_ROUTE}?token={self.token}",
                    request,
                )
                self.assertEqual(status, 201)
                self.assertEqual(created["result"]["status"], "created")
                self.assertFalse(created["result"]["replayed"])
                child_id = created["result"]["child"]["clip_id"]
                status, replayed = _json_request(
                    first,
                    "POST",
                    f"{_ACTION_ROUTE}?token={self.token}",
                    request,
                )
                self.assertEqual(status, 201)
                self.assertEqual(replayed["result"]["status"], "replayed")
                self.assertTrue(replayed["result"]["replayed"])
                self.assertTrue(
                    all(
                        value is False
                        for value in replayed["result"]["effects"].values()
                    )
                )
                self.assertEqual(len(ClipLibrary(library_root, read_only=True).list()), 2)

            with _running_real_server(
                self.catalog,
                self.root / "real-restart-state",
                **common,
            ) as restarted:
                status, detail = _json_request(
                    restarted,
                    "GET",
                    f"/api/clips/{child_id}?token={self.token}",
                )
                self.assertEqual(status, 200)
                summary = detail["correction_summary"]
                self.assertEqual(summary["operation"], "correct_note_pitches")
                self.assertEqual(summary["parent_clip_id"], "clip-1")
                self.assertEqual(summary["child_clip_id"], child_id)
                self.assertEqual(summary["changed_note_count"], 1)
                self.assertEqual(summary["changes"][0]["after_pitch"], 62)
                self.assertEqual(detail["lineage"]["version_count"], 2)
                self.assertEqual(detail["lineage"]["current_clip_id"], child_id)
                _assert_path_free_response(
                    self,
                    detail,
                    root=self.root,
                    token=self.token,
                )

    def test_stale_second_projection_conflicts_without_a_second_child(self) -> None:
        with _real_correction_server_pair(
            self.catalog,
            self.root,
            self.token,
        ) as pair:
            first = _real_correction_create_request(
                pair.first,
                self.token,
                pair.parent_object_sha256,
                target_pitch=62,
            )
            stale = _real_correction_create_request(
                pair.first,
                self.token,
                pair.parent_object_sha256,
                target_pitch=63,
            )
            first_status, _first_payload = _json_request(
                pair.first,
                "POST",
                f"{_ACTION_ROUTE}?token={self.token}",
                first,
            )
            stale_status, stale_payload = _json_request(
                pair.first,
                "POST",
                f"{_ACTION_ROUTE}?token={self.token}",
                stale,
            )
            self.assertEqual(first_status, 201)
            self.assertEqual(stale_status, 409)
            self.assertEqual(stale_payload, _STALE)
            self.assertEqual(len(ClipLibrary(pair.library_root, read_only=True).list()), 2)

    def test_two_servers_racing_identical_create_return_created_and_replayed(
        self,
    ) -> None:
        with _real_correction_server_pair(
            self.catalog,
            self.root,
            self.token,
        ) as pair:
            first = _real_correction_create_request(
                pair.first,
                self.token,
                pair.parent_object_sha256,
                target_pitch=62,
            )
            second = _real_correction_create_request(
                pair.second,
                self.token,
                pair.parent_object_sha256,
                target_pitch=62,
            )
            self.assertEqual(first, second)
            outcomes = _race_correction_actions(
                (pair.first, pair.second),
                (first, second),
                self.token,
            )
            self.assertEqual([status for status, _payload in outcomes], [201, 201])
            self.assertEqual(
                sorted(payload["result"]["status"] for _status, payload in outcomes),
                ["created", "replayed"],
            )
            self.assertEqual(len(ClipLibrary(pair.library_root, read_only=True).list()), 2)
            for _status, payload in outcomes:
                _assert_path_free_response(
                    self,
                    payload,
                    root=self.root,
                    token=self.token,
                )

    def test_two_servers_racing_different_corrections_create_only_one_child(
        self,
    ) -> None:
        with _real_correction_server_pair(
            self.catalog,
            self.root,
            self.token,
        ) as pair:
            first = _real_correction_create_request(
                pair.first,
                self.token,
                pair.parent_object_sha256,
                target_pitch=62,
            )
            second = _real_correction_create_request(
                pair.second,
                self.token,
                pair.parent_object_sha256,
                target_pitch=63,
            )
            outcomes = _race_correction_actions(
                (pair.first, pair.second),
                (first, second),
                self.token,
            )
            self.assertEqual([status for status, _payload in outcomes], [201, 409])
            self.assertEqual(next(payload for status, payload in outcomes if status == 409), _STALE)
            self.assertEqual(len(ClipLibrary(pair.library_root, read_only=True).list()), 2)

    def test_real_deletion_create_replay_restart_and_detail_summary_are_exact(
        self,
    ) -> None:
        library_root, parent_hash = _real_clip_library(self.root)
        pack_path, acceptance = _real_phase6_acceptance(self.root)
        common = {
            "token": self.token,
            "clip_library_path": library_root,
            "phase6_acceptance_path": acceptance,
            "phase6_pack_path": pack_path,
            "enable_clip_corrections": True,
        }
        with patch(
            "sunofriend.workbench_clips.verify_garageband_pack_archive",
            return_value={"status": "verified"},
        ):
            with _running_real_server(
                self.catalog,
                self.root / "real-deletion-create-state",
                **common,
            ) as first:
                request = _real_deletion_create_request(
                    first,
                    self.token,
                    parent_hash,
                    editable_index=0,
                )
                status, created = _json_request(
                    first,
                    "POST",
                    f"{_ACTION_ROUTE}?token={self.token}",
                    request,
                )
                self.assertEqual(status, 201)
                result = created["result"]
                self.assertEqual(result["schema"], CLIP_NOTE_DELETION_RESULT_SCHEMA)
                self.assertEqual(result["status"], "created")
                self.assertFalse(result["replayed"])
                self.assertEqual(
                    {key for key, value in result["effects"].items() if value},
                    {
                        "library_mutated",
                        "child_clip_created",
                        "correction_applied",
                        "note_deleted",
                        "note_count_changed",
                    },
                )
                child_id = result["child"]["clip_id"]
                status, replayed = _json_request(
                    first,
                    "POST",
                    f"{_ACTION_ROUTE}?token={self.token}",
                    request,
                )
                self.assertEqual(status, 201)
                self.assertEqual(replayed["result"]["status"], "replayed")
                self.assertTrue(replayed["result"]["replayed"])
                self.assertTrue(
                    all(
                        value is False
                        for value in replayed["result"]["effects"].values()
                    )
                )
                self.assertEqual(
                    len(ClipLibrary(library_root, read_only=True).list()), 2
                )
                _assert_path_free_response(
                    self,
                    created,
                    root=self.root,
                    token=self.token,
                )

            with _running_real_server(
                self.catalog,
                self.root / "real-deletion-restart-state",
                **common,
            ) as restarted:
                status, detail = _json_request(
                    restarted,
                    "GET",
                    f"/api/clips/{child_id}?token={self.token}",
                )
                self.assertEqual(status, 200)
                summary = detail["correction_summary"]
                self.assertEqual(summary["schema"], CLIP_NOTE_DELETION_SUMMARY_SCHEMA)
                self.assertEqual(summary["operation"], "delete_clip_notes")
                self.assertEqual(summary["parent_clip_id"], "clip-1")
                self.assertEqual(summary["child_clip_id"], child_id)
                self.assertEqual(summary["changed_note_count"], 1)
                self.assertEqual(summary["changes"][0]["pitch"], 60)
                self.assertEqual(detail["lineage"]["version_count"], 2)
                self.assertEqual(detail["lineage"]["current_clip_id"], child_id)
                _assert_path_free_response(
                    self,
                    detail,
                    root=self.root,
                    token=self.token,
                )
                replay_status, restarted_replay = _json_request(
                    restarted,
                    "POST",
                    f"{_ACTION_ROUTE}?token={self.token}",
                    request,
                )
                self.assertEqual(replay_status, 201)
                self.assertEqual(restarted_replay["result"]["status"], "replayed")
                self.assertTrue(restarted_replay["result"]["replayed"])
                self.assertTrue(
                    all(
                        value is False
                        for value in restarted_replay["result"]["effects"].values()
                    )
                )
                self.assertEqual(
                    len(ClipLibrary(library_root, read_only=True).list()), 2
                )

    def test_two_servers_racing_identical_deletion_create_and_replay(
        self,
    ) -> None:
        with _real_correction_server_pair(
            self.catalog,
            self.root,
            self.token,
        ) as pair:
            first = _real_deletion_create_request(
                pair.first,
                self.token,
                pair.parent_object_sha256,
                editable_index=0,
            )
            second = _real_deletion_create_request(
                pair.second,
                self.token,
                pair.parent_object_sha256,
                editable_index=0,
            )
            self.assertEqual(first, second)
            outcomes = _race_correction_actions(
                (pair.first, pair.second),
                (first, second),
                self.token,
            )
            self.assertEqual([status for status, _payload in outcomes], [201, 201])
            self.assertEqual(
                sorted(
                    payload["result"]["status"]
                    for _status, payload in outcomes
                ),
                ["created", "replayed"],
            )
            self.assertEqual(
                len(ClipLibrary(pair.library_root, read_only=True).list()), 2
            )
            for _status, payload in outcomes:
                _assert_path_free_response(
                    self,
                    payload,
                    root=self.root,
                    token=self.token,
                )

    def test_two_servers_racing_different_deletions_create_only_one_child(
        self,
    ) -> None:
        with _real_correction_server_pair(
            self.catalog,
            self.root,
            self.token,
        ) as pair:
            first = _real_deletion_create_request(
                pair.first,
                self.token,
                pair.parent_object_sha256,
                editable_index=0,
            )
            second = _real_deletion_create_request(
                pair.second,
                self.token,
                pair.parent_object_sha256,
                editable_index=1,
            )
            outcomes = _race_correction_actions(
                (pair.first, pair.second),
                (first, second),
                self.token,
            )
            self.assertEqual([status for status, _payload in outcomes], [201, 409])
            self.assertEqual(
                next(payload for status, payload in outcomes if status == 409),
                _STALE,
            )
            self.assertEqual(
                len(ClipLibrary(pair.library_root, read_only=True).list()), 2
            )

    def test_real_onset_create_replay_restart_and_detail_summary_are_exact(
        self,
    ) -> None:
        library_root, parent_hash = _real_clip_library(self.root)
        pack_path, acceptance = _real_phase6_acceptance(self.root)
        common = {
            "token": self.token,
            "clip_library_path": library_root,
            "phase6_acceptance_path": acceptance,
            "phase6_pack_path": pack_path,
            "enable_clip_corrections": True,
        }
        with patch(
            "sunofriend.workbench_clips.verify_garageband_pack_archive",
            return_value={"status": "verified"},
        ):
            with _running_real_server(
                self.catalog,
                self.root / "real-onset-create-state",
                **common,
            ) as first:
                request = _real_onset_create_request(
                    first,
                    self.token,
                    parent_hash,
                    tick_delta=30,
                )
                status, created = _json_request(
                    first,
                    "POST",
                    f"{_ACTION_ROUTE}?token={self.token}",
                    request,
                )
                self.assertEqual(status, 201)
                self.assertEqual(
                    created["result"]["schema"], CLIP_NOTE_ONSET_RESULT_SCHEMA
                )
                self.assertEqual(created["result"]["status"], "created")
                self.assertEqual(
                    created["result"]["diff"]["changes"][0]["tick_delta"], 30
                )
                child_id = created["result"]["child"]["clip_id"]
                status, replayed = _json_request(
                    first,
                    "POST",
                    f"{_ACTION_ROUTE}?token={self.token}",
                    request,
                )
                self.assertEqual(status, 201)
                self.assertEqual(replayed["result"]["status"], "replayed")
                self.assertTrue(
                    all(
                        value is False
                        for value in replayed["result"]["effects"].values()
                    )
                )
                self.assertEqual(
                    len(ClipLibrary(library_root, read_only=True).list()), 2
                )

            with _running_real_server(
                self.catalog,
                self.root / "real-onset-restart-state",
                **common,
            ) as restarted:
                status, detail = _json_request(
                    restarted,
                    "GET",
                    f"/api/clips/{child_id}?token={self.token}",
                )
                self.assertEqual(status, 200)
                summary = detail["correction_summary"]
                self.assertEqual(summary["schema"], CLIP_NOTE_ONSET_SUMMARY_SCHEMA)
                self.assertEqual(summary["operation"], "shift_note_onsets")
                self.assertEqual(summary["parent_clip_id"], "clip-1")
                self.assertEqual(summary["child_clip_id"], child_id)
                self.assertEqual(summary["changed_note_count"], 1)
                self.assertEqual(summary["changes"][0]["tick_delta"], 30)
                self.assertTrue(
                    all(value is False for value in summary["effects"].values())
                )
                _assert_path_free_response(
                    self,
                    detail,
                    root=self.root,
                    token=self.token,
                )

    def test_two_servers_racing_identical_onset_create_and_replay(self) -> None:
        with _real_correction_server_pair(
            self.catalog,
            self.root,
            self.token,
        ) as pair:
            first = _real_onset_create_request(
                pair.first,
                self.token,
                pair.parent_object_sha256,
                tick_delta=30,
            )
            second = _real_onset_create_request(
                pair.second,
                self.token,
                pair.parent_object_sha256,
                tick_delta=30,
            )
            self.assertEqual(first, second)
            outcomes = _race_correction_actions(
                (pair.first, pair.second),
                (first, second),
                self.token,
            )
            self.assertEqual([status for status, _payload in outcomes], [201, 201])
            self.assertEqual(
                sorted(payload["result"]["status"] for _status, payload in outcomes),
                ["created", "replayed"],
            )
            self.assertEqual(
                len(ClipLibrary(pair.library_root, read_only=True).list()), 2
            )

    def test_two_servers_racing_different_onsets_create_only_one_child(self) -> None:
        with _real_correction_server_pair(
            self.catalog,
            self.root,
            self.token,
        ) as pair:
            first = _real_onset_create_request(
                pair.first,
                self.token,
                pair.parent_object_sha256,
                tick_delta=30,
            )
            second = _real_onset_create_request(
                pair.second,
                self.token,
                pair.parent_object_sha256,
                tick_delta=60,
            )
            outcomes = _race_correction_actions(
                (pair.first, pair.second),
                (first, second),
                self.token,
            )
            self.assertEqual([status for status, _payload in outcomes], [201, 409])
            self.assertEqual(
                next(payload for status, payload in outcomes if status == 409),
                _STALE,
            )
            self.assertEqual(
                len(ClipLibrary(pair.library_root, read_only=True).list()), 2
            )


class _FakeCorrectionService:
    def __init__(self) -> None:
        self.window_calls: list[dict] = []
        self.preview_calls: list[dict] = []
        self.create_calls: list[dict] = []
        self.failures: dict[str, Exception] = {}
        self.lock_probe = None
        self.lock_observations: list[tuple[str, bool]] = []
        self.capability_document = {
            "schema": "sunofriend.workbench-clip-correction-capability.v1",
            "enabled": True,
            "scope": "bounded-pitch-only-immutable-child",
            "actions": {"window": True, "preview": True, "create": True},
        }
        self.window_document = {
            "schema": "sunofriend.workbench-clip-correction-window.v1",
            "window_sha256": "c" * 64,
            "effects": {"library_mutated": False},
        }
        self.projection_document = {
            "schema": "sunofriend.workbench-clip-correction-preview.v1",
            "projection_sha256": "d" * 64,
            "effects": {"library_mutated": False},
        }
        self.result_document = {
            "schema": "sunofriend.workbench-clip-correction-result.v1",
            "child": {"clip_id": "clip-child", "object_sha256": "e" * 64},
            "effects": {"library_mutated": True},
        }

    def capability(self) -> dict:
        self._record_lock("capability")
        return copy.deepcopy(self.capability_document)

    def window(self, request) -> dict:
        self._record_lock("window")
        self._raise("window")
        self.window_calls.append(copy.deepcopy(dict(request)))
        return copy.deepcopy(self.window_document)

    def preview(self, request) -> dict:
        self._record_lock("preview")
        self._raise("preview")
        self.preview_calls.append(copy.deepcopy(dict(request)))
        return copy.deepcopy(self.projection_document)

    def create(self, request) -> dict:
        self._record_lock("create")
        self._raise("create")
        self.create_calls.append(copy.deepcopy(dict(request)))
        return copy.deepcopy(self.result_document)

    def correction_summary(self, _clip_id: str) -> None:
        return None

    def _raise(self, operation: str) -> None:
        failure = self.failures.get(operation)
        if failure is not None:
            raise failure

    def _record_lock(self, operation: str) -> None:
        if self.lock_probe is not None:
            self.lock_observations.append((operation, bool(self.lock_probe())))


class _ObservedLock:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._depth = 0

    @property
    def held(self) -> bool:
        return self._depth > 0

    def __enter__(self):
        self._lock.acquire()
        self._depth += 1
        return self

    def __exit__(self, *_args) -> None:
        self._depth -= 1
        self._lock.release()


class _running_server:
    def __init__(
        self,
        catalog: dict,
        state_dir: Path,
        token: str,
        *,
        correction_service: _FakeCorrectionService | None = None,
        developer_inspector: bool = False,
    ) -> None:
        self.server = create_workbench_server(
            catalog,
            state_dir=state_dir,
            token=token,
            developer_inspector=developer_inspector,
        )
        self.server.clip_correction_service = correction_service
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self.server

    def __exit__(self, *_args) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class _running_real_server:
    def __init__(self, catalog: dict, state_dir: Path, **options) -> None:
        self.server = create_workbench_server(
            catalog,
            state_dir=state_dir,
            **options,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self.server

    def __exit__(self, *_args) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class _real_correction_server_pair:
    def __init__(self, catalog: dict, root: Path, token: str) -> None:
        self.root = root
        self.library_root, self.parent_object_sha256 = _real_clip_library(root)
        pack_path, acceptance = _real_phase6_acceptance(root)
        self._verification_patch = patch(
            "sunofriend.workbench_clips.verify_garageband_pack_archive",
            return_value={"status": "verified"},
        )
        self._verification_patch.start()
        try:
            common = {
                "token": token,
                "clip_library_path": self.library_root,
                "phase6_acceptance_path": acceptance,
                "phase6_pack_path": pack_path,
                "enable_clip_corrections": True,
            }
            self.first = create_workbench_server(
                catalog,
                state_dir=root / "real-correction-state-first",
                **common,
            )
            self.second = create_workbench_server(
                catalog,
                state_dir=root / "real-correction-state-second",
                **common,
            )
        except Exception:
            self._verification_patch.stop()
            raise
        self._threads = [
            threading.Thread(target=server.serve_forever, daemon=True)
            for server in (self.first, self.second)
        ]

    def __enter__(self):
        for thread in self._threads:
            thread.start()
        return self

    def __exit__(self, *_args) -> None:
        for server in (self.first, self.second):
            server.shutdown()
            server.server_close()
        for thread in self._threads:
            thread.join(timeout=5)
        self._verification_patch.stop()


def _real_correction_create_request(
    server,
    token: str,
    parent_object_sha256: str,
    *,
    target_pitch: int,
) -> dict:
    project_status, project = _json_request(
        server,
        "GET",
        f"/api/project?token={token}",
    )
    if project_status != 200:
        raise AssertionError(f"project capability failed: {project_status} {project}")
    window_request = {
        "parent_clip_id": "clip-1",
        "parent_object_sha256": parent_object_sha256,
        "library_state_sha256": project["clip_corrections"]["library"][
            "state_sha256"
        ],
        "window": {"start_tick": 0, "end_tick": 960},
    }
    window_status, window_payload = _json_request(
        server,
        "POST",
        f"{_WINDOW_ROUTE}?token={token}",
        window_request,
    )
    if window_status != 200:
        raise AssertionError(f"correction window failed: {window_status} {window_payload}")
    window = window_payload["window"]
    editable = [note for note in window["notes"] if note["editable"]]
    if not editable:
        raise AssertionError("correction window did not return an editable note")
    preview_request = {
        **window_request,
        "window_sha256": window["window_sha256"],
        "correction": {
            "kind": "pitch_patch",
            "changes": [
                {
                    "note_ref": editable[0]["note_ref"],
                    "target_pitch": target_pitch,
                }
            ],
        },
    }
    preview_status, preview_payload = _json_request(
        server,
        "POST",
        f"{_PROJECTION_ROUTE}?token={token}",
        preview_request,
    )
    if preview_status != 200:
        raise AssertionError(
            f"correction preview failed: {preview_status} {preview_payload}"
        )
    return {
        "action": "create",
        **preview_request,
        "projection_sha256": preview_payload["projection"]["projection_sha256"],
    }


def _real_deletion_create_request(
    server,
    token: str,
    parent_object_sha256: str,
    *,
    editable_index: int,
) -> dict:
    project_status, project = _json_request(
        server,
        "GET",
        f"/api/project?token={token}",
    )
    if project_status != 200:
        raise AssertionError(f"project capability failed: {project_status} {project}")
    base_request = {
        "parent_clip_id": "clip-1",
        "parent_object_sha256": parent_object_sha256,
        "library_state_sha256": project["clip_corrections"]["library"][
            "state_sha256"
        ],
        "window": {"start_tick": 0, "end_tick": 960},
    }
    window_status, window_payload = _json_request(
        server,
        "POST",
        f"{_WINDOW_ROUTE}?token={token}",
        {**base_request, "correction_kind": "note_delete_patch"},
    )
    if window_status != 200:
        raise AssertionError(
            f"deletion window failed: {window_status} {window_payload}"
        )
    window = window_payload["window"]
    editable = [note for note in window["notes"] if note["editable"]]
    if editable_index >= len(editable):
        raise AssertionError("deletion window did not return enough editable notes")
    preview_request = {
        **base_request,
        "window_sha256": window["window_sha256"],
        "correction": {
            "kind": "note_delete_patch",
            "changes": [{"note_ref": editable[editable_index]["note_ref"]}],
        },
    }
    preview_status, preview_payload = _json_request(
        server,
        "POST",
        f"{_PROJECTION_ROUTE}?token={token}",
        preview_request,
    )
    if preview_status != 200:
        raise AssertionError(
            f"deletion preview failed: {preview_status} {preview_payload}"
        )
    return {
        "action": "create",
        **preview_request,
        "projection_sha256": preview_payload["projection"]["projection_sha256"],
    }


def _real_onset_create_request(
    server,
    token: str,
    parent_object_sha256: str,
    *,
    tick_delta: int,
) -> dict:
    project_status, project = _json_request(
        server,
        "GET",
        f"/api/project?token={token}",
    )
    if project_status != 200:
        raise AssertionError(f"project capability failed: {project_status} {project}")
    base_request = {
        "parent_clip_id": "clip-1",
        "parent_object_sha256": parent_object_sha256,
        "library_state_sha256": project["clip_corrections"]["library"][
            "state_sha256"
        ],
        "window": {"start_tick": 0, "end_tick": 960},
    }
    window_status, window_payload = _json_request(
        server,
        "POST",
        f"{_WINDOW_ROUTE}?token={token}",
        {**base_request, "correction_kind": "note_onset_shift_patch"},
    )
    if window_status != 200:
        raise AssertionError(
            f"onset window failed: {window_status} {window_payload}"
        )
    window = window_payload["window"]
    editable = [note for note in window["notes"] if note["editable"]]
    if not editable:
        raise AssertionError("onset window did not return an editable note")
    source = editable[0]
    preview_request = {
        **base_request,
        "window_sha256": window["window_sha256"],
        "correction": {
            "kind": "note_onset_shift_patch",
            "changes": [
                {
                    "note_ref": source["note_ref"],
                    "target_start_tick": source["start_tick"] + tick_delta,
                }
            ],
        },
    }
    preview_status, preview_payload = _json_request(
        server,
        "POST",
        f"{_PROJECTION_ROUTE}?token={token}",
        preview_request,
    )
    if preview_status != 200:
        raise AssertionError(
            f"onset preview failed: {preview_status} {preview_payload}"
        )
    return {
        "action": "create",
        **preview_request,
        "projection_sha256": preview_payload["projection"]["projection_sha256"],
    }


def _race_correction_actions(
    servers: tuple,
    requests: tuple[dict, dict],
    token: str,
) -> list[tuple[int, dict]]:
    barrier = threading.Barrier(3)
    lock = threading.Lock()
    outcomes: list[tuple[int, dict]] = []

    def submit(server, request: dict) -> None:
        barrier.wait(timeout=5)
        outcome = _json_request(
            server,
            "POST",
            f"{_ACTION_ROUTE}?token={token}",
            request,
        )
        with lock:
            outcomes.append(outcome)

    threads = [
        threading.Thread(target=submit, args=(server, request))
        for server, request in zip(servers, requests)
    ]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=20)
        if thread.is_alive():
            raise AssertionError("correction race request did not finish")
    return sorted(outcomes, key=lambda row: row[0])


def _window_request() -> dict:
    return {
        "parent_clip_id": "clip-parent",
        "parent_object_sha256": "a" * 64,
        "library_state_sha256": "b" * 64,
        "window": {"start_tick": 0, "end_tick": 960},
    }


def _preview_request() -> dict:
    return {
        **_window_request(),
        "window_sha256": "c" * 64,
        "correction": {
            "kind": "pitch_patch",
            "changes": [{"note_ref": "e" * 64, "target_pitch": 62}],
        },
    }


def _create_request() -> dict:
    return {
        "action": "create",
        **_preview_request(),
        "projection_sha256": "d" * 64,
    }


def _json_request(
    server,
    method: str,
    route: str,
    value: dict | None = None,
) -> tuple[int, dict]:
    body = None if value is None else json.dumps(value).encode("utf-8")
    return _raw_json_request(server, method, route, body)


def _raw_json_request(
    server,
    method: str,
    route: str,
    body: bytes | None,
) -> tuple[int, dict]:
    connection = http.client.HTTPConnection(
        "127.0.0.1", server.server_port, timeout=10
    )
    try:
        connection.request(
            method,
            route,
            body=body,
            headers={} if body is None else {"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()


def _assert_path_free_response(
    case: unittest.TestCase,
    payload: dict,
    *,
    root: Path,
    token: str,
) -> None:
    encoded = json.dumps(payload, sort_keys=True)
    case.assertNotIn(str(root), encoded)
    case.assertNotIn("/Users/alice", encoded)
    case.assertNotIn(token, encoded)


def _catalog(root: Path) -> dict:
    project = root / "Correction Server Song-B major-119bpm-440hz"
    candidates = root / "candidates"
    project.mkdir()
    candidates.mkdir()
    source = project / "Correction Server Song-keys-B major-119bpm-440hz.wav"
    source.write_bytes(b"RIFF-phase6-correction-source")
    midi = candidates / "keys.mid"
    write_midi_file(
        midi,
        [MidiTrack("Keys", 0, 4, [NoteEvent(0.0, 0.5, 60, 90)])],
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
                        "role": "keys",
                        "candidates": [{"midi": str(midi), "label": "Method A"}],
                    }
                ],
            }
        )
    )
    return build_workbench_catalog(
        project,
        candidate_roots=[candidates],
        catalog_path=catalog_path,
    )


def _real_clip_library(root: Path) -> tuple[Path, str]:
    library_root = root / "real-correction-library"
    tempo = TempoMap.constant(119.0)
    parent = MidiClip(
        title="Private correction parent",
        tempo_map=tempo,
        time_signature=TimeSignature(),
        instrument=Instrument("keys", 4, 0),
        notes=(
            ClipNote.from_beats(0.0, 1.0, 60, 90, tempo),
            ClipNote.from_beats(1.0, 1.0, 64, 84, tempo),
            ClipNote.from_beats(2.0, 1.0, 67, 80, tempo),
        ),
        provenance=Provenance(source_uri="/Users/alice/private-correction.wav"),
        clip_id="clip-1",
    )
    summary = ClipLibrary(library_root).add(parent)
    return library_root, summary.object_hash


def _real_phase6_acceptance(root: Path) -> tuple[Path, Path]:
    pack = root / "real-correction-accepted.zip"
    pack.write_bytes(b"exact accepted correction pack")
    acceptance = root / "real-correction-acceptance.json"
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
                    "sha256": hashlib.sha256(pack.read_bytes()).hexdigest(),
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


if __name__ == "__main__":
    unittest.main()
