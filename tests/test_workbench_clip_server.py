from __future__ import annotations

import hashlib
import http.client
import io
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from urllib.parse import quote
from unittest.mock import patch

from sunofriend.clip import ClipNote, Instrument, MidiClip, TempoMap, TimeSignature
from sunofriend.cli import build_parser
from sunofriend.library import ClipLibrary
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.workbench_catalog import build_workbench_catalog
from sunofriend.workbench_server import create_workbench_server, run_workbench


class WorkbenchClipServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.catalog = _catalog(self.root)
        self.token = "phase6-clip-server-token"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_disabled_routes_are_404_and_project_reports_read_only_disabled(self) -> None:
        with _running_server(
            self.catalog,
            self.root / "disabled-state",
            self.token,
        ) as server:
            for method, route, body in (
                ("GET", "/api/clips", None),
                ("GET", "/api/clips/clip-1", None),
                (
                    "POST",
                    "/api/clip-artifact",
                    {"clip_id": "clip-1", "include_preview": False},
                ),
            ):
                with self.subTest(method=method, route=route):
                    status, _headers, payload = _json_request(
                        server,
                        method,
                        f"{route}?token={self.token}",
                        body,
                    )
                    self.assertEqual(status, 404)
                    self.assertEqual(payload, {"error": "workbench route not found"})

            status, _headers, project = _json_request(
                server,
                "GET",
                f"/api/project?token={self.token}",
            )
            self.assertEqual(status, 200)
            self.assertEqual(
                project["clip_library"],
                {
                    "enabled": False,
                    "read_only": True,
                    "reason": (
                        "Phase 6 Clip Library options were not supplied for this launch"
                    ),
                },
            )

    def test_enabled_project_browse_tags_detail_and_token_protection(self) -> None:
        fake = _FakeClipService(self.root / "fake-artifacts")
        with _running_server(
            self.catalog,
            self.root / "enabled-state",
            self.token,
            clip_service=fake,
        ) as server:
            for method, route, body in (
                ("GET", "/api/clips?token=wrong", None),
                ("GET", "/api/clips/clip-1?token=wrong", None),
                (
                    "POST",
                    "/api/clip-artifact?token=wrong",
                    {"clip_id": "clip-1", "include_preview": False},
                ),
            ):
                with self.subTest(route=route):
                    status, _headers, payload = _json_request(
                        server, method, route, body
                    )
                    self.assertEqual(status, 403)
                    self.assertEqual(
                        payload,
                        {"error": "invalid workbench session token"},
                    )

            status, _headers, project = _json_request(
                server,
                "GET",
                f"/api/project?token={self.token}",
            )
            self.assertEqual(status, 200)
            self.assertEqual(project["clip_library"], fake.capability_document)

            route = (
                f"/api/clips?token={self.token}&text=golden&role=bass"
                "&key=B+major&bpm=119&bpm_tolerance=0.5"
                "&tag=reviewed&tag=walking&limit=7&offset=2"
            )
            status, _headers, browse = _json_request(server, "GET", route)
            self.assertEqual(status, 200)
            self.assertEqual(browse["page"]["total"], 1)
            self.assertEqual(
                fake.browse_calls,
                [
                    {
                        "text": "golden",
                        "role": "bass",
                        "key": "B major",
                        "bpm": 119.0,
                        "bpm_tolerance": 0.5,
                        "tags": ("reviewed", "walking"),
                        "limit": 7,
                        "offset": 2,
                    }
                ],
            )

            encoded = quote("clip-1", safe="")
            status, _headers, detail = _json_request(
                server,
                "GET",
                f"/api/clips/{encoded}?token={self.token}",
            )
            self.assertEqual(status, 200)
            self.assertEqual(detail["clip"]["clip_id"], "clip-1")
            self.assertEqual(fake.detail_calls, ["clip-1"])
            self.assertNotIn(str(self.root), json.dumps(detail))
            self.assertNotIn('"path"', json.dumps(detail))

    def test_artifact_request_is_exact_and_media_are_path_free_range_capable(self) -> None:
        fake = _FakeClipService(self.root / "fake-artifacts")
        with _running_server(
            self.catalog,
            self.root / "artifact-state",
            self.token,
            clip_service=fake,
        ) as server:
            for body in (
                {"clip_id": "clip-1"},
                {
                    "clip_id": "clip-1",
                    "include_preview": False,
                    "gain": 1,
                },
            ):
                status, _headers, payload = _json_request(
                    server,
                    "POST",
                    f"/api/clip-artifact?token={self.token}",
                    body,
                )
                self.assertEqual(status, 400)
                self.assertEqual(payload, {"error": "invalid Clip artifact request"})
            self.assertEqual(fake.prepare_calls, [])

            status, _headers, midi_payload = _json_request(
                server,
                "POST",
                f"/api/clip-artifact?token={self.token}",
                {"clip_id": "clip-1", "include_preview": False},
            )
            self.assertEqual(status, 200)
            midi_artifact = midi_payload["artifact"]
            self.assertIsNone(midi_artifact["preview"])
            self.assertIn("url", midi_artifact["midi"])
            self.assertNotIn(str(self.root), json.dumps(midi_artifact))
            self.assertNotIn('"path"', json.dumps(midi_artifact))

            midi_url = midi_artifact["midi"]["url"]
            status, headers, midi_bytes = _request(server, "GET", midi_url)
            self.assertEqual(status, 200)
            self.assertEqual(midi_bytes, fake.midi_bytes)
            self.assertEqual(headers["accept-ranges"], "bytes")
            self.assertIn("midi", headers["content-type"])
            status, headers, ranged = _request(
                server,
                "GET",
                midi_url,
                headers={"Range": "bytes=0-3"},
            )
            self.assertEqual(status, 206)
            self.assertEqual(ranged, fake.midi_bytes[:4])
            self.assertEqual(
                headers["content-range"],
                f"bytes 0-3/{len(fake.midi_bytes)}",
            )

            status, _headers, preview_payload = _json_request(
                server,
                "POST",
                f"/api/clip-artifact?token={self.token}",
                {"clip_id": "clip-1", "include_preview": True},
            )
            self.assertEqual(status, 200)
            preview_artifact = preview_payload["artifact"]
            self.assertIn("url", preview_artifact["preview"])
            preview_url = preview_artifact["preview"]["url"]
            status, headers, preview_bytes = _request(server, "GET", preview_url)
            self.assertEqual(status, 200)
            self.assertEqual(preview_bytes, fake.preview_bytes)
            self.assertIn("wav", headers["content-type"])
            self.assertEqual(
                fake.prepare_calls,
                [
                    ("clip-1", False),
                    ("clip-1", True),
                ],
            )

            for public_file in (midi_artifact["midi"], preview_artifact["preview"]):
                media_id = _media_id(public_file["url"])
                record = server.media[media_id]
                self.assertTrue(record["_freeze_on_serve"])
                self.assertIn("path", record)

            # Registration copies and freezes the expected file identity.  A
            # later filesystem mutation fails rather than serving changed data.
            fake.midi_path.write_bytes(fake.midi_bytes + b"changed")
            status, _headers, changed = _request(server, "GET", midi_url)
            self.assertEqual(status, 409)
            self.assertIn(b"changed after it was catalogued", changed)

    def test_invalid_and_drift_failures_use_fixed_non_private_messages(self) -> None:
        fake = _FakeClipService(self.root / "fake-artifacts")
        with _running_server(
            self.catalog,
            self.root / "failure-state",
            self.token,
            clip_service=fake,
        ) as server:
            for query in (
                "unexpected=value",
                "role=bass&role=keys",
                "tag=",
                "&".join(f"tag=tag-{index}" for index in range(33)),
            ):
                status, _headers, payload = _json_request(
                    server,
                    "GET",
                    f"/api/clips?token={self.token}&{query}",
                )
                self.assertEqual(status, 400)
                self.assertEqual(payload, {"error": "invalid Clip Library search"})

            fake.failures["browse"] = ValueError("PRIVATE /Users/alice/search")
            status, _headers, payload = _json_request(
                server,
                "GET",
                f"/api/clips?token={self.token}",
            )
            self.assertEqual(status, 400)
            self.assertEqual(payload, {"error": "invalid Clip Library search"})

            fake.failures["browse"] = RuntimeError("PRIVATE /Users/alice/drift")
            status, _headers, payload = _json_request(
                server,
                "GET",
                f"/api/clips?token={self.token}",
            )
            self.assertEqual(status, 409)
            self.assertEqual(
                payload,
                {
                    "error": (
                        "Clip Library evidence changed or is unavailable; "
                        "restart the Workbench"
                    )
                },
            )

            fake.failures.pop("browse")
            fake.failures["detail"] = KeyError("PRIVATE /Users/alice/missing")
            status, _headers, payload = _json_request(
                server,
                "GET",
                f"/api/clips/missing?token={self.token}",
            )
            self.assertEqual(status, 404)
            self.assertEqual(payload, {"error": "Clip not found"})

            fake.failures["detail"] = RuntimeError("PRIVATE /Users/alice/object")
            status, _headers, payload = _json_request(
                server,
                "GET",
                f"/api/clips/clip-1?token={self.token}",
            )
            self.assertEqual(status, 409)
            self.assertEqual(
                payload,
                {
                    "error": (
                        "Clip Library evidence changed or is unavailable; "
                        "restart the Workbench"
                    )
                },
            )

            fake.failures.pop("detail")
            fake.failures["prepare"] = ValueError("PRIVATE /Users/alice/request")
            status, _headers, payload = _json_request(
                server,
                "POST",
                f"/api/clip-artifact?token={self.token}",
                {"clip_id": "clip-1", "include_preview": False},
            )
            self.assertEqual(status, 400)
            self.assertEqual(payload, {"error": "invalid Clip artifact request"})

            fake.failures["prepare"] = RuntimeError("PRIVATE renderer path")
            status, _headers, payload = _json_request(
                server,
                "POST",
                f"/api/clip-artifact?token={self.token}",
                {"clip_id": "clip-1", "include_preview": False},
            )
            self.assertEqual(status, 409)
            self.assertEqual(
                payload,
                {
                    "error": (
                        "Clip evidence changed or the local renderer is unavailable"
                    )
                },
            )
            self.assertNotIn("PRIVATE", json.dumps(payload))

    def test_capability_failure_makes_project_fail_closed_with_fixed_message(self) -> None:
        fake = _FakeClipService(self.root / "fake-artifacts")
        fake.failures["capability"] = RuntimeError("PRIVATE /Users/alice/gate")
        with _running_server(
            self.catalog,
            self.root / "capability-state",
            self.token,
            clip_service=fake,
        ) as server:
            status, _headers, payload = _json_request(
                server,
                "GET",
                f"/api/project?token={self.token}",
            )
            self.assertEqual(status, 409)
            self.assertEqual(
                payload,
                {
                    "error": (
                        "Workbench evidence changed or is unavailable; "
                        "restart the Workbench"
                    )
                },
            )

    def test_database_drift_fails_closed_on_every_clip_route(self) -> None:
        expected_errors = {
            "/api/project": (
                "Workbench evidence changed or is unavailable; restart the Workbench"
            ),
            "/api/clips": (
                "Clip Library evidence changed or is unavailable; restart the Workbench"
            ),
            "/api/clips/clip-1": (
                "Clip Library evidence changed or is unavailable; restart the Workbench"
            ),
            "/api/clip-artifact": (
                "Clip evidence changed or the local renderer is unavailable"
            ),
        }
        for drift in ("missing", "corrupt"):
            with self.subTest(drift=drift):
                root = self.root / drift
                root.mkdir()
                library = _clip_library(root)
                pack, acceptance = _phase6_acceptance(root)
                stderr = io.StringIO()
                with (
                    patch(
                        "sunofriend.workbench_clips.verify_garageband_pack_archive",
                        return_value={"status": "verified"},
                    ),
                    _running_server(
                        self.catalog,
                        root / "state",
                        self.token,
                        clip_library_path=library,
                        phase6_acceptance_path=acceptance,
                        phase6_pack_path=pack,
                    ) as server,
                    redirect_stderr(stderr),
                ):
                    database = library / "catalog.sqlite3"
                    if drift == "missing":
                        database.unlink()
                    else:
                        database.write_bytes(b"not a SQLite database")

                    requests = (
                        ("GET", "/api/project", None),
                        ("GET", "/api/clips", None),
                        ("GET", "/api/clips/clip-1", None),
                        (
                            "POST",
                            "/api/clip-artifact",
                            {"clip_id": "clip-1", "include_preview": False},
                        ),
                    )
                    for method, route, body in requests:
                        with self.subTest(drift=drift, route=route):
                            status, _headers, payload = _json_request(
                                server,
                                method,
                                f"{route}?token={self.token}",
                                body,
                            )
                            self.assertEqual(status, 409)
                            self.assertEqual(
                                payload,
                                {"error": expected_errors[route]},
                            )
                            self.assertNotIn(str(root), json.dumps(payload))
                self.assertNotIn("Traceback", stderr.getvalue())


class WorkbenchClipLaunchTests(unittest.TestCase):
    def test_phase6_flags_are_all_or_nothing_and_live_only(self) -> None:
        incomplete = (
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
                "must be supplied together",
            ):
                create_workbench_server(
                    {"project_id": "unused", "stems": []},
                    **values,
                )

        complete = {
            "clip_library_path": "/tmp/library",
            "phase6_acceptance_path": "/tmp/acceptance.json",
            "phase6_pack_path": "/tmp/pack.zip",
        }
        with self.assertRaisesRegex(ValueError, "live loopback Workbench"):
            run_workbench("/not-read", inspect_only=True, **complete)
        with self.assertRaisesRegex(ValueError, "live loopback Workbench"):
            run_workbench(
                "/not-read",
                export_review_path="/not-written.json",
                **complete,
            )

    def test_parser_exposes_three_explicit_phase6_flags(self) -> None:
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
            ]
        )
        self.assertEqual(parsed.clip_library, "/library")
        self.assertEqual(parsed.phase6_acceptance, "/acceptance.json")
        self.assertEqual(parsed.phase6_pack, "/pack.zip")

    def test_enabled_server_opens_service_with_cache_outside_library(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _catalog(root)
            state = root / "state"
            library = root / "library"
            acceptance = root / "acceptance.json"
            pack = root / "pack.zip"
            fake = _FakeClipService(root / "fake-artifacts")
            with patch(
                "sunofriend.workbench_server.WorkbenchClipService.open",
                return_value=fake,
            ) as opened:
                server = create_workbench_server(
                    catalog,
                    state_dir=state,
                    token="token",
                    clip_library_path=library,
                    phase6_acceptance_path=acceptance,
                    phase6_pack_path=pack,
                )
            try:
                opened.assert_called_once_with(
                    acceptance_result_path=acceptance,
                    garageband_pack_path=pack,
                    library_root=library,
                    cache_root=state.resolve() / "phase6-clip-cache",
                    soundfont_path=None,
                )
                cache = opened.call_args.kwargs["cache_root"]
                self.assertFalse(cache.is_relative_to(library.resolve()))
                self.assertIs(server.clip_service, fake)
            finally:
                server.server_close()


class _FakeClipService:
    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True)
        self.midi_bytes = b"MThd" + b"\0" * 40
        self.preview_bytes = b"RIFF" + b"\0" * 2048
        self.midi_path = root / "clip.mid"
        self.preview_path = root / "neutral-preview.wav"
        self.midi_path.write_bytes(self.midi_bytes)
        self.preview_path.write_bytes(self.preview_bytes)
        self.browse_calls: list[dict] = []
        self.detail_calls: list[str] = []
        self.prepare_calls: list[tuple[str, bool]] = []
        self.failures: dict[str, Exception] = {}
        self.capability_document = {
            "schema": "sunofriend.workbench-clip-capability.v1",
            "enabled": True,
            "read_only": True,
            "acceptance": {
                "status": "passed",
                "pack_sha256": "a" * 64,
            },
            "library": {"clip_count": 1, "lineage_count": 1},
            "effects": {"library_mutated": False},
        }

    def capability(self) -> dict:
        self._raise("capability")
        return json.loads(json.dumps(self.capability_document))

    def browse(self, **query) -> dict:
        self._raise("browse")
        self.browse_calls.append(query)
        return {
            "schema": "sunofriend.workbench-clip-browse.v1",
            "query": query,
            "page": {
                "limit": query["limit"],
                "offset": query["offset"],
                "total": 1,
                "returned": 1,
                "has_more": False,
            },
            "clips": [
                {
                    "clip_id": "clip-1",
                    "title": "Golden bass",
                    "role": "bass",
                    "key": "B major",
                    "bpm": 119.0,
                    "note_count": 12,
                    "duration_seconds": 8.0,
                    "tags": ["reviewed", "walking"],
                    "object_sha256": "b" * 64,
                }
            ],
            "effects": {"library_mutated": False},
        }

    def detail(self, clip_id: str) -> dict:
        self._raise("detail")
        self.detail_calls.append(clip_id)
        return {
            "schema": "sunofriend.workbench-clip-detail.v1",
            "clip": {
                "clip_id": clip_id,
                "title": "Golden bass",
                "object_sha256": "b" * 64,
                "duration_seconds": 8.0,
                "program": 38,
                "channel": 0,
            },
            "lineage": {"versions": [{"clip_id": clip_id, "revision": 1}]},
            "effects": {"library_mutated": False},
        }

    def prepare_artifact(self, clip_id: str, *, include_preview: bool) -> dict:
        self._raise("prepare")
        if not isinstance(clip_id, str) or not isinstance(include_preview, bool):
            raise ValueError("invalid")
        self.prepare_calls.append((clip_id, include_preview))
        midi = _file_record(self.midi_path)
        preview = _file_record(self.preview_path) if include_preview else None
        public = {
            "schema": "sunofriend.workbench-clip-artifact.v1",
            "artifact_id": "c" * 64,
            "clip": {"clip_id": clip_id, "object_sha256": "b" * 64},
            "timing_contract": {"resolved_mode": "musical", "export_bpm": 119.0},
            "midi": _without_path(midi),
            "preview": None if preview is None else _without_path(preview),
            "effects": {"library_mutated": False},
        }
        return {
            "schema": "sunofriend.workbench-clip-artifact-cache.v1",
            "midi": midi,
            "preview": preview,
            "public": public,
            "effects": {"library_mutated": False},
        }

    def _raise(self, operation: str) -> None:
        failure = self.failures.get(operation)
        if failure is not None:
            raise failure


class _running_server:
    def __init__(
        self,
        catalog: dict,
        state_dir: Path,
        token: str,
        *,
        clip_service: _FakeClipService | None = None,
        clip_library_path: Path | None = None,
        phase6_acceptance_path: Path | None = None,
        phase6_pack_path: Path | None = None,
    ) -> None:
        self.server = create_workbench_server(
            catalog,
            state_dir=state_dir,
            token=token,
            clip_library_path=clip_library_path,
            phase6_acceptance_path=phase6_acceptance_path,
            phase6_pack_path=phase6_pack_path,
        )
        if clip_service is not None:
            self.server.clip_service = clip_service
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self.server

    def __exit__(self, *_args) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def _request(
    server,
    method: str,
    route: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection(
        "127.0.0.1", server.server_port, timeout=10
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


def _catalog(root: Path) -> dict:
    project = root / "Clip Server Song-B major-119bpm-440hz"
    candidates = root / "candidates"
    project.mkdir()
    candidates.mkdir()
    source = project / "Clip Server Song-bass-B major-119bpm-440hz.wav"
    source.write_bytes(b"RIFF-phase6-source")
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


def _clip_library(root: Path) -> Path:
    library_root = root / "library"
    tempo = TempoMap.constant(119.0)
    ClipLibrary(library_root).add(
        MidiClip(
            title="Golden bass",
            tempo_map=tempo,
            time_signature=TimeSignature(),
            instrument=Instrument("bass", 38, 0),
            notes=(ClipNote.from_beats(0.0, 1.0, 38, 90, tempo),),
            clip_id="clip-1",
            tags=("reviewed",),
        )
    )
    return library_root


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


def _file_record(path: Path) -> dict:
    payload = path.read_bytes()
    return {
        "path": str(path),
        "name": path.name,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _without_path(record: dict) -> dict:
    return {key: value for key, value in record.items() if key != "path"}


def _media_id(url: str) -> str:
    return url.split("/media/", 1)[1].split("?", 1)[0]


if __name__ == "__main__":
    unittest.main()
