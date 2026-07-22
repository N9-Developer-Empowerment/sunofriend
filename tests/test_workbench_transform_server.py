from __future__ import annotations

import copy
import hashlib
import http.client
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from dataclasses import replace
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
from sunofriend.workbench_server import create_workbench_server, run_workbench
from sunofriend.workbench_transform import (
    WorkbenchClipTransformConflictError,
    WorkbenchClipTransformNotFoundError,
)


_DISABLED_CAPABILITY = {
    "enabled": False,
    "immutable_versions_only": True,
    "reason": "Clip transforms were not explicitly enabled for this launch",
}
_INVALID = {"error": "invalid Clip transform request"}
_NOT_FOUND = {"error": "Clip not found"}
_STALE = {
    "error": (
        "Clip transform preview changed; preview again before creating a version"
    )
}
_DRIFT = {
    "error": (
        "Clip transform evidence changed or is unavailable; restart the Workbench"
    )
}


class WorkbenchClipTransformLaunchTests(unittest.TestCase):
    def test_parser_exposes_explicit_transform_opt_in_and_excludes_reuse(self) -> None:
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
                "--enable-clip-transforms",
            ]
        )
        self.assertTrue(parsed.enable_clip_transforms)
        self.assertFalse(parsed.enable_clip_reuse_plan)
        default = build_parser().parse_args(["workbench", "/project"])
        self.assertFalse(default.enable_clip_transforms)

        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            build_parser().parse_args(
                [
                    "workbench",
                    "/project",
                    "--enable-clip-reuse-plan",
                    "--enable-clip-transforms",
                ]
            )

    def test_transform_opt_in_requires_phase6_trio_and_live_server(self) -> None:
        catalog = {"project_id": "unused", "stems": []}
        with self.assertRaisesRegex(ValueError, "--enable-clip-transforms requires"):
            create_workbench_server(catalog, enable_clip_transforms=True)

        complete = {
            "clip_library_path": "/tmp/library",
            "phase6_acceptance_path": "/tmp/acceptance.json",
            "phase6_pack_path": "/tmp/pack.zip",
            "enable_clip_transforms": True,
        }
        with self.assertRaisesRegex(ValueError, "live loopback Workbench"):
            run_workbench("/not-read", inspect_only=True, **complete)

        with self.assertRaisesRegex(ValueError, "mutually exclusive"):
            create_workbench_server(
                catalog,
                enable_clip_reuse_plan=True,
                **complete,
            )

    def test_enabled_launch_opens_transform_service_against_gated_clip_service(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _catalog(root)
            clip_service = object()
            transform_service = object()
            library = root / "library"
            acceptance = root / "acceptance.json"
            pack_path = root / "pack.zip"
            with (
                patch(
                    "sunofriend.workbench_server.WorkbenchClipService.open",
                    return_value=clip_service,
                ),
                patch(
                    "sunofriend.workbench_server.WorkbenchClipTransformService.open",
                    return_value=transform_service,
                ) as opened,
            ):
                server = create_workbench_server(
                    catalog,
                    state_dir=root / "state",
                    token="token",
                    clip_library_path=library,
                    phase6_acceptance_path=acceptance,
                    phase6_pack_path=pack_path,
                    enable_clip_transforms=True,
                )
            try:
                opened.assert_called_once_with(
                    clip_service=clip_service,
                    library_root=library,
                )
                self.assertIs(server.clip_transform_service, transform_service)
                self.assertIsNone(server.clip_reuse_service)
            finally:
                server.server_close()


class WorkbenchClipTransformServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.catalog = _catalog(self.root)
        self.token = "phase6-transform-server-token"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_disabled_routes_are_always_404_and_project_explains_opt_in(self) -> None:
        with _running_server(
            self.catalog,
            self.root / "disabled-state",
            self.token,
        ) as server:
            for route, body in (
                ("/api/clip-transform-projection", b"{"),
                ("/api/clip-transform-action", b"x" * (64 * 1024 + 1)),
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
            self.assertEqual(project["clip_transforms"], _DISABLED_CAPABILITY)

    def test_preview_and_create_have_canonical_envelopes_and_exact_bodies(self) -> None:
        service = _FakeTransformService()
        with _running_server(
            self.catalog,
            self.root / "enabled-state",
            self.token,
            transform_service=service,
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
            self.assertEqual(project["clip_transforms"], service.capability_document)

            preview_request = _preview_request()
            status, preview = _json_request(
                server,
                "POST",
                f"/api/clip-transform-projection?token={self.token}",
                preview_request,
            )
            self.assertEqual(status, 200)
            self.assertEqual(preview, {"projection": service.projection_document})
            self.assertEqual(service.preview_calls, [preview_request])

            create_request = _create_request()
            status, created = _json_request(
                server,
                "POST",
                f"/api/clip-transform-action?token={self.token}",
                create_request,
            )
            self.assertEqual(status, 201)
            self.assertEqual(created, {"result": service.result_document})
            self.assertEqual(service.create_calls, [create_request])
            self.assertEqual(
                service.lock_observations,
                [
                    ("capability", True),
                    ("preview", True),
                    ("create", True),
                ],
            )
            self.assertNotIn(self.token, json.dumps(preview))
            self.assertNotIn(str(self.root), json.dumps(created))

    def test_routes_are_token_size_and_type_protected_with_fixed_errors(self) -> None:
        service = _FakeTransformService()
        with _running_server(
            self.catalog,
            self.root / "protected-state",
            self.token,
            transform_service=service,
        ) as server:
            for route in (
                "/api/clip-transform-projection",
                "/api/clip-transform-action",
            ):
                status, payload = _json_request(
                    server,
                    "POST",
                    f"{route}?token=wrong",
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
            self.assertEqual(service.preview_calls, [])
            self.assertEqual(service.create_calls, [])

    def test_service_failures_are_mapped_to_fixed_path_free_responses(self) -> None:
        cases = (
            (
                "preview",
                WorkbenchClipTransformNotFoundError("PRIVATE /Users/alice"),
                404,
                _NOT_FOUND,
            ),
            (
                "create",
                WorkbenchClipTransformConflictError("PRIVATE /Users/alice"),
                409,
                _STALE,
            ),
            (
                "preview",
                OSError("PRIVATE /Users/alice"),
                409,
                _DRIFT,
            ),
            (
                "create",
                ValueError("PRIVATE /Users/alice"),
                400,
                _INVALID,
            ),
        )
        for index, (operation, failure, expected_status, expected) in enumerate(cases):
            with self.subTest(operation=operation, failure=type(failure).__name__):
                service = _FakeTransformService()
                service.failures[operation] = failure
                with _running_server(
                    self.catalog,
                    self.root / f"failure-state-{index}",
                    self.token,
                    transform_service=service,
                ) as server:
                    route = (
                        "/api/clip-transform-projection"
                        if operation == "preview"
                        else "/api/clip-transform-action"
                    )
                    body = _preview_request() if operation == "preview" else _create_request()
                    status, payload = _json_request(
                        server,
                        "POST",
                        f"{route}?token={self.token}",
                        body,
                    )
                    self.assertEqual(status, expected_status)
                    self.assertEqual(payload, expected)
                    self.assertNotIn("PRIVATE", json.dumps(payload))
                    self.assertNotIn("/Users/", json.dumps(payload))

    def test_developer_trace_records_preview_as_zero_effect_and_create_as_append(
        self,
    ) -> None:
        service = _FakeTransformService()
        with _running_server(
            self.catalog,
            self.root / "developer-state",
            self.token,
            transform_service=service,
            developer_inspector=True,
        ) as server:
            private_id = "/Users/alice/private.mid"
            preview = _preview_request()
            preview["parent_clip_id"] = private_id
            status, _ = _json_request(
                server,
                "POST",
                f"/api/clip-transform-projection?token={self.token}",
                preview,
            )
            self.assertEqual(status, 200)
            status, _ = _json_request(
                server,
                "POST",
                f"/api/clip-transform-action?token={self.token}",
                _create_request(),
            )
            self.assertEqual(status, 201)
            status, snapshot = _json_request(
                server,
                "GET",
                f"/api/developer-snapshot?token={self.token}",
            )
            self.assertEqual(status, 200)
            operations = snapshot["runtime"]["trace"]["recent_operations"][-2:]
            self.assertEqual(
                [row["operation"] for row in operations],
                ["clip_transform.preview", "clip_transform.create"],
            )
            self.assertEqual(
                [row["durable_effect_possible"] for row in operations],
                [False, True],
            )
            self.assertNotIn(
                "sunofriend.library.ClipLibrary.append_version_if_state",
                operations[0]["symbols"],
            )
            self.assertIn(
                "sunofriend.library.ClipLibrary.append_version_if_state",
                operations[1]["symbols"],
            )
            self.assertTrue(snapshot["runtime"]["clip_transforms_enabled"])
            self.assertFalse(snapshot["effects"]["clip_version_appended"])
            encoded = json.dumps(snapshot, sort_keys=True)
            self.assertNotIn(private_id, encoded)
            self.assertNotIn(self.token, encoded)

    def test_two_servers_racing_exact_create_return_created_and_replayed(self) -> None:
        with _real_transform_server_pair(
            self.catalog,
            self.root,
            self.token,
        ) as pair:
            first = _real_transform_create_request(
                pair.first,
                self.token,
                pair.parent_object_sha256,
                target_bpm=100,
            )
            second = _real_transform_create_request(
                pair.second,
                self.token,
                pair.parent_object_sha256,
                target_bpm=100,
            )
            self.assertEqual(first, second)

            outcomes = _race_transform_actions(
                (pair.first, pair.second),
                (first, second),
                self.token,
            )

            self.assertEqual([status for status, _payload in outcomes], [201, 201])
            self.assertEqual(
                sorted(payload["result"]["status"] for _status, payload in outcomes),
                ["created", "replayed"],
            )
            for _status, payload in outcomes:
                self.assertEqual(set(payload), {"result"})
                _assert_path_free_response(
                    self,
                    payload,
                    root=self.root,
                    token=self.token,
                )
            self.assertEqual(
                len(ClipLibrary(pair.library_root, read_only=True).list()),
                2,
            )

    def test_second_server_replays_exact_create_after_first_server_commits(self) -> None:
        with _real_transform_server_pair(
            self.catalog,
            self.root,
            self.token,
        ) as pair:
            first = _real_transform_create_request(
                pair.first,
                self.token,
                pair.parent_object_sha256,
                target_bpm=100,
            )
            second = _real_transform_create_request(
                pair.second,
                self.token,
                pair.parent_object_sha256,
                target_bpm=100,
            )

            first_status, first_payload = _json_request(
                pair.first,
                "POST",
                f"/api/clip-transform-action?token={self.token}",
                first,
            )
            second_status, second_payload = _json_request(
                pair.second,
                "POST",
                f"/api/clip-transform-action?token={self.token}",
                second,
            )

            self.assertEqual(first_status, 201)
            self.assertEqual(first_payload["result"]["status"], "created")
            self.assertEqual(second_status, 201)
            self.assertEqual(set(second_payload), {"result"})
            self.assertEqual(second_payload["result"]["status"], "replayed")
            self.assertTrue(second_payload["result"]["replayed"])
            self.assertTrue(
                all(
                    value is False
                    for value in second_payload["result"]["effects"].values()
                )
            )
            _assert_path_free_response(
                self,
                second_payload,
                root=self.root,
                token=self.token,
            )
            self.assertEqual(
                len(ClipLibrary(pair.library_root, read_only=True).list()),
                2,
            )

    def test_two_servers_racing_different_transforms_create_one_and_conflict_one(
        self,
    ) -> None:
        with _real_transform_server_pair(
            self.catalog,
            self.root,
            self.token,
        ) as pair:
            first = _real_transform_create_request(
                pair.first,
                self.token,
                pair.parent_object_sha256,
                target_bpm=100,
            )
            second = _real_transform_create_request(
                pair.second,
                self.token,
                pair.parent_object_sha256,
                target_bpm=90,
            )

            outcomes = _race_transform_actions(
                (pair.first, pair.second),
                (first, second),
                self.token,
            )

            self.assertEqual([status for status, _payload in outcomes], [201, 409])
            created = next(payload for status, payload in outcomes if status == 201)
            conflict = next(payload for status, payload in outcomes if status == 409)
            self.assertEqual(set(created), {"result"})
            self.assertEqual(created["result"]["status"], "created")
            self.assertEqual(conflict, _STALE)
            _assert_path_free_response(
                self,
                conflict,
                root=self.root,
                token=self.token,
            )
            self.assertEqual(
                len(ClipLibrary(pair.library_root, read_only=True).list()),
                2,
            )

    def test_cross_instance_replay_path_rejects_an_unrelated_external_append(
        self,
    ) -> None:
        with _real_transform_server_pair(
            self.catalog,
            self.root,
            self.token,
        ) as pair:
            request = _real_transform_create_request(
                pair.second,
                self.token,
                pair.parent_object_sha256,
                target_bpm=100,
            )
            library = ClipLibrary(pair.library_root)
            parent = library.get("clip-1")
            library.add(
                replace(
                    parent,
                    clip_id="unrelated-external-clip",
                    parent_clip_id=None,
                    revision=1,
                )
            )

            status, payload = _json_request(
                pair.second,
                "POST",
                f"/api/clip-transform-action?token={self.token}",
                request,
            )

            self.assertEqual(status, 409)
            self.assertEqual(payload, _STALE)
            self.assertEqual(len(library.list(limit=10_000)), 2)
            self.assertFalse(
                any(
                    row.clip_id.startswith("sf-transform-")
                    for row in library.list(limit=10_000)
                )
            )


class _FakeTransformService:
    def __init__(self) -> None:
        self.preview_calls: list[dict] = []
        self.create_calls: list[dict] = []
        self.failures: dict[str, Exception] = {}
        self.lock_probe = None
        self.lock_observations: list[tuple[str, bool]] = []
        self.capability_document = {
            "schema": "sunofriend.workbench-clip-transform-capability.v1",
            "enabled": True,
            "explicit_opt_in": True,
            "immutable_versions_only": True,
            "actions": {"preview": True, "create": True},
        }
        self.projection_document = {
            "schema": "sunofriend.workbench-clip-transform-preview.v1",
            "projection_sha256": "d" * 64,
            "effects": {"library_mutated": False},
        }
        self.result_document = {
            "schema": "sunofriend.workbench-clip-transform-result.v1",
            "child": {"clip_id": "clip-child", "object_sha256": "e" * 64},
            "effects": {"library_mutated": True},
        }

    def capability(self) -> dict:
        self._record_lock("capability")
        return copy.deepcopy(self.capability_document)

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
        transform_service: _FakeTransformService | None = None,
        developer_inspector: bool = False,
    ) -> None:
        self.server = create_workbench_server(
            catalog,
            state_dir=state_dir,
            token=token,
            developer_inspector=developer_inspector,
        )
        self.server.clip_transform_service = transform_service
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self.server

    def __exit__(self, *_args) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class _real_transform_server_pair:
    def __init__(self, catalog: dict, root: Path, token: str) -> None:
        self.root = root
        self.token = token
        self.library_root, self.parent_object_sha256 = _real_clip_library(root)
        pack, acceptance = _real_phase6_acceptance(root)
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
                "phase6_pack_path": pack,
                "enable_clip_transforms": True,
            }
            self.first = create_workbench_server(
                catalog,
                state_dir=root / "real-transform-state-first",
                **common,
            )
            self.second = create_workbench_server(
                catalog,
                state_dir=root / "real-transform-state-second",
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


def _real_transform_create_request(
    server,
    token: str,
    parent_object_sha256: str,
    *,
    target_bpm: float,
) -> dict:
    project_status, project = _json_request(
        server,
        "GET",
        f"/api/project?token={token}",
    )
    if project_status != 200:
        raise AssertionError(f"project capability failed: {project_status} {project}")
    preview_request = {
        "parent_clip_id": "clip-1",
        "parent_object_sha256": parent_object_sha256,
        "library_state_sha256": project["clip_transforms"]["library"][
            "state_sha256"
        ],
        "transform": {
            "kind": "bpm",
            "target_bpm": target_bpm,
            "timing_mode": "musical",
        },
    }
    preview_status, preview_payload = _json_request(
        server,
        "POST",
        f"/api/clip-transform-projection?token={token}",
        preview_request,
    )
    if preview_status != 200:
        raise AssertionError(
            f"transform preview failed: {preview_status} {preview_payload}"
        )
    preview = preview_payload["projection"]
    return {
        "action": "create",
        "parent_clip_id": preview["parent"]["clip_id"],
        "parent_object_sha256": preview["parent"]["object_sha256"],
        "library_state_sha256": preview["library"]["state_sha256"],
        "projection_sha256": preview["projection_sha256"],
        "transform": dict(preview["transform"]),
    }


def _race_transform_actions(
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
            f"/api/clip-transform-action?token={token}",
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
            raise AssertionError("transform race request did not finish")
    return sorted(outcomes, key=lambda row: row[0])


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


def _preview_request() -> dict:
    return {
        "parent_clip_id": "clip-parent",
        "parent_object_sha256": "a" * 64,
        "library_state_sha256": "b" * 64,
        "transform": {
            "kind": "key",
            "target_key": "D minor",
            "direction": "nearest",
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


def _catalog(root: Path) -> dict:
    project = root / "Transform Server Song-B major-119bpm-440hz"
    candidates = root / "candidates"
    project.mkdir()
    candidates.mkdir()
    source = project / "Transform Server Song-bass-B major-119bpm-440hz.wav"
    source.write_bytes(b"RIFF-phase6-transform-source")
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
        )
    )
    return build_workbench_catalog(
        project,
        candidate_roots=[candidates],
        catalog_path=catalog_path,
    )


def _real_clip_library(root: Path) -> tuple[Path, str]:
    library_root = root / "real-transform-library"
    tempo = TempoMap.constant(119.0)
    parent = MidiClip(
        title="Private transform parent",
        tempo_map=tempo,
        time_signature=TimeSignature(),
        instrument=Instrument("bass", 38, 0),
        notes=(ClipNote.from_beats(0.0, 1.0, 38, 90, tempo),),
        provenance=Provenance(source_uri="/Users/alice/private-transform.wav"),
        clip_id="clip-1",
    )
    summary = ClipLibrary(library_root).add(parent)
    return library_root, summary.object_hash


def _real_phase6_acceptance(root: Path) -> tuple[Path, Path]:
    pack = root / "real-transform-accepted.zip"
    pack.write_bytes(b"exact accepted transform pack")
    pack_sha256 = hashlib.sha256(pack.read_bytes()).hexdigest()
    acceptance = root / "real-transform-acceptance.json"
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
                    "sha256": pack_sha256,
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
