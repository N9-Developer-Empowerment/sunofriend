from __future__ import annotations

import hashlib
import http.client
import importlib.util
import io
import json
import os
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.workbench_catalog import build_workbench_catalog
from sunofriend.workbench_server import (
    _WorkbenchHandler,
    _freeze_verified_immutable_file,
    create_workbench_server,
)


@unittest.skipUnless(
    importlib.util.find_spec("numpy") and importlib.util.find_spec("soundfile"),
    "balanced arrangement server tests require numpy and soundfile",
)
class WorkbenchBalancedArrangementServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.catalog, self.soundfont = _catalog(self.root)
        self.state_dir = self.root / "state"
        self.token = "balanced-arrangement-test-token"
        self.render_patch = patch(
            "sunofriend.workbench_artifacts.render_midi_to_wav",
            side_effect=_render_preview,
        )
        self.renderer = self.render_patch.start()
        self.server = create_workbench_server(
            self.catalog,
            state_dir=self.state_dir,
            token=self.token,
            soundfont_path=self.soundfont,
        )
        for stem in self.catalog["stems"]:
            candidate = stem["candidates"][0]
            self.server.store.append(
                self.catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "main",
                    "context": "full_mix",
                    "problem_tags": [],
                    "notes": "private server fixture note",
                },
            )
        self._start_server()

    def tearDown(self) -> None:
        self._stop_server()
        self.render_patch.stop()
        self.temporary.cleanup()

    def test_success_is_path_free_state_neutral_and_restored_after_restart(
        self,
    ) -> None:
        status, _, initial = self._json_request(
            "GET",
            f"/api/project?token={self.token}",
        )
        self.assertEqual(status, 200)
        self.assertIsNone(initial["balanced_arrangement"])
        selection_sha256 = initial["decoded_arrangement_selection"][
            "selection_manifest_sha256"
        ]
        state_before = self.server.store.current_state(self.catalog)
        self.renderer.assert_not_called()

        status, _, payload = self._json_request(
            "POST",
            f"/api/balanced-arrangement?token={self.token}",
            {"selection_manifest_sha256": selection_sha256},
        )

        self.assertEqual(status, 200)
        artifact = payload["balanced_arrangement"]
        self.assertEqual(
            artifact["selection_manifest_sha256"],
            selection_sha256,
        )
        self.assertFalse(artifact["mastered"])
        self.assertFalse(artifact["cache_hit"])
        self.assertNotIn("_deferred_cache_claim", artifact)
        self.assertEqual(self.renderer.call_count, 2)
        self.assertEqual(
            set(artifact) & {"preview_url", "report_url", "recipe_url"},
            {"preview_url", "report_url", "recipe_url"},
        )
        serialized = json.dumps(artifact, sort_keys=True)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn("private server fixture note", serialized)
        _assert_no_paths(self, artifact)
        self.assertTrue(all(value is False for value in artifact["effects"].values()))
        self.assertEqual(
            self.server.store.current_state(self.catalog),
            state_before,
        )

        downloaded: dict[str, bytes] = {}
        for key in ("preview", "report", "recipe"):
            url = artifact[f"{key}_url"]
            self.assertTrue(url.startswith("/media/"))
            status, headers, body = self._request("GET", url)
            self.assertEqual(status, 200)
            self.assertEqual(headers["accept-ranges"], "bytes")
            self.assertEqual(len(body), artifact[key]["bytes"])
            self.assertEqual(
                hashlib.sha256(body).hexdigest(),
                artifact[key]["sha256"],
            )
            self.assertNotIn(str(self.root).encode("utf-8"), body)
            downloaded[key] = body

        receipt = json.loads(downloaded["report"])
        self.assertEqual(
            receipt["schema"],
            "sunofriend.workbench-balanced-mix-receipt.v1",
        )
        self.assertEqual(receipt["render_horizon"], artifact["render_horizon"])
        mix_lanes = artifact["mix_report"]["lanes"]
        horizon_lanes = artifact["render_horizon"]["lanes"]
        self.assertEqual(len(mix_lanes), 2)
        self.assertEqual(len(horizon_lanes), 2)
        for mix_lane, horizon_lane in zip(mix_lanes, horizon_lanes):
            self.assertEqual(
                mix_lane["selection_index"],
                horizon_lane["selection_index"],
            )
            self.assertEqual(
                mix_lane["garageband_pack_archive_member"],
                horizon_lane["garageband_pack_archive_member"],
            )
            self.assertRegex(
                mix_lane["garageband_pack_archive_member"],
                r"^MIDI/\d{2}-.+\.mid$",
            )
            self.assertIn("excluded_neutral_preview_tail_frames", horizon_lane)
            self.assertIn("padded_output_frames", horizon_lane)

        self._stop_server()
        self.token = "balanced-arrangement-restart-token"
        self.server = create_workbench_server(
            self.catalog,
            state_dir=self.state_dir,
            token=self.token,
            soundfont_path=self.soundfont,
        )
        self._start_server()

        status, _, restored = self._json_request(
            "GET",
            f"/api/project?token={self.token}",
        )

        self.assertEqual(status, 200)
        restored_artifact = restored["balanced_arrangement"]
        self.assertIsNotNone(restored_artifact)
        self.assertTrue(restored_artifact["cache_hit"])
        self.assertEqual(
            restored_artifact["selection_manifest_sha256"],
            selection_sha256,
        )
        for key in ("preview", "report", "recipe"):
            self.assertEqual(
                restored_artifact[key]["sha256"],
                artifact[key]["sha256"],
            )
            self.assertTrue(restored_artifact[f"{key}_url"].startswith("/media/"))
        self.assertEqual(self.renderer.call_count, 2)
        self.assertEqual(
            self.server.store.current_state(self.catalog),
            state_before,
        )
        _assert_no_paths(self, restored_artifact)

    def test_balanced_files_are_frozen_against_mutation_during_serve(self) -> None:
        status, _, project = self._json_request(
            "GET",
            f"/api/project?token={self.token}",
        )
        self.assertEqual(status, 200)
        selection_sha256 = project["decoded_arrangement_selection"][
            "selection_manifest_sha256"
        ]
        status, _, payload = self._json_request(
            "POST",
            f"/api/balanced-arrangement?token={self.token}",
            {"selection_manifest_sha256": selection_sha256},
        )
        self.assertEqual(status, 200)
        artifact = payload["balanced_arrangement"]
        records = {}
        for key in ("preview", "report", "recipe"):
            media_id = (
                artifact[f"{key}_url"]
                .split("/media/", 1)[1]
                .split("?", 1)[0]
            )
            record = self.server.media[media_id]
            self.assertTrue(record["_freeze_on_serve"])
            records[key] = record

        preview_record = records["preview"]
        expected = Path(str(preview_record["path"])).read_bytes()
        status, headers, body = self._request(
            "GET",
            artifact["preview_url"],
            headers={"Range": "bytes=10-29"},
        )
        self.assertEqual(status, 206)
        self.assertEqual(headers["content-range"], f"bytes 10-29/{len(expected)}")
        self.assertEqual(body, expected[10:30])
        status, headers, _body = self._request(
            "GET",
            artifact["preview_url"],
            headers={"Range": f"bytes={len(expected) + 1}-"},
        )
        self.assertEqual(status, 416)
        self.assertEqual(headers["content-range"], f"bytes */{len(expected)}")

        original_verifier = _freeze_verified_immutable_file

        def verify_then_mutate(handle: object, record: dict) -> object:
            frozen = original_verifier(handle, record)
            Path(str(record["path"])).write_bytes(
                b"mutated after the verified read"
            )
            return frozen

        with patch(
            "sunofriend.workbench_server._freeze_verified_immutable_file",
            side_effect=verify_then_mutate,
        ):
            status, _, body = self._request(
                "GET",
                artifact["preview_url"],
            )
        self.assertEqual(status, 200)
        self.assertEqual(body, expected)
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            artifact["preview"]["sha256"],
        )

        status, _, body = self._request(
            "GET",
            artifact["preview_url"],
        )
        self.assertEqual(status, 409)
        self.assertIn(b"changed after it was catalogued", body)

    def test_balanced_snapshot_storage_failure_is_controlled(self) -> None:
        status, _, project = self._json_request(
            "GET",
            f"/api/project?token={self.token}",
        )
        self.assertEqual(status, 200)
        selection_sha256 = project["decoded_arrangement_selection"][
            "selection_manifest_sha256"
        ]
        status, _, payload = self._json_request(
            "POST",
            f"/api/balanced-arrangement?token={self.token}",
            {"selection_manifest_sha256": selection_sha256},
        )
        self.assertEqual(status, 200)
        artifact = payload["balanced_arrangement"]

        with patch(
            "sunofriend.workbench_server._freeze_verified_immutable_file",
            side_effect=OSError("temporary storage unavailable"),
        ):
            status, _, body = self._request(
                "GET",
                artifact["preview_url"],
            )
        self.assertEqual(status, 503)
        self.assertIn(b"snapshot could not be created", body)

    def test_balanced_snapshot_closes_when_headers_disconnect(self) -> None:
        status, _, project = self._json_request(
            "GET",
            f"/api/project?token={self.token}",
        )
        self.assertEqual(status, 200)
        selection_sha256 = project["decoded_arrangement_selection"][
            "selection_manifest_sha256"
        ]
        status, _, payload = self._json_request(
            "POST",
            f"/api/balanced-arrangement?token={self.token}",
            {"selection_manifest_sha256": selection_sha256},
        )
        self.assertEqual(status, 200)
        artifact = payload["balanced_arrangement"]
        preview = next(
            record
            for record in self.server.media.values()
            if record.get("sha256") == artifact["preview"]["sha256"]
        )
        expected = Path(str(preview["path"])).read_bytes()

        class FrozenSnapshot:
            def __init__(self, payload: bytes) -> None:
                self.buffer = io.BytesIO(payload)
                self.closed = False

            def __enter__(self) -> FrozenSnapshot:
                return self

            def __exit__(self, *_args: object) -> None:
                self.closed = True
                self.buffer.close()

            def read(self, size: int = -1) -> bytes:
                return self.buffer.read(size)

            def seek(self, offset: int, whence: int = 0) -> int:
                return self.buffer.seek(offset, whence)

        snapshot = FrozenSnapshot(expected)
        with (
            patch(
                "sunofriend.workbench_server._freeze_verified_immutable_file",
                return_value=snapshot,
            ),
            patch.object(
                _WorkbenchHandler,
                "send_response",
                side_effect=BrokenPipeError("client disconnected"),
            ),
            self.assertRaises(http.client.RemoteDisconnected),
        ):
            self._request("GET", artifact["preview_url"])
        self.assertTrue(snapshot.closed)

    def test_request_requires_exact_current_lowercase_selection_hash(self) -> None:
        status, _, project = self._json_request(
            "GET",
            f"/api/project?token={self.token}",
        )
        self.assertEqual(status, 200)
        current_hash = project["decoded_arrangement_selection"][
            "selection_manifest_sha256"
        ]
        state_before = self.server.store.current_state(self.catalog)

        requests = (
            ({}, 400, "missing selection_manifest_sha256"),
            (
                {
                    "selection_manifest_sha256": current_hash,
                    "unexpected": True,
                },
                400,
                "unexpected unexpected",
            ),
            (
                {"selection_manifest_sha256": current_hash.upper()},
                400,
                "lowercase SHA-256",
            ),
            (
                {"selection_manifest_sha256": "0" * 64},
                409,
                "selected arrangement changed",
            ),
        )
        for request, expected_status, message in requests:
            with self.subTest(request=request):
                status, _, payload = self._json_request(
                    "POST",
                    f"/api/balanced-arrangement?token={self.token}",
                    request,
                )
                self.assertEqual(status, expected_status)
                self.assertIn(message, payload["error"])

        status, _, payload = self._json_request(
            "POST",
            "/api/balanced-arrangement?token=wrong",
            {"selection_manifest_sha256": current_hash},
        )
        self.assertEqual(status, 403)
        self.assertIn("token", payload["error"])
        self.renderer.assert_not_called()
        self.assertEqual(len(self.server.generated_media_ids), 0)
        self.assertEqual(
            self.server.store.current_state(self.catalog),
            state_before,
        )

    def test_developer_inspector_traces_balanced_render_as_effect_free(
        self,
    ) -> None:
        self._stop_server()
        self.server = create_workbench_server(
            self.catalog,
            state_dir=self.state_dir,
            token=self.token,
            soundfont_path=self.soundfont,
            developer_inspector=True,
        )
        self._start_server()
        status, _, project = self._json_request(
            "GET",
            f"/api/project?token={self.token}",
        )
        self.assertEqual(status, 200)
        selection_sha256 = project["decoded_arrangement_selection"][
            "selection_manifest_sha256"
        ]

        status, _, payload = self._json_request(
            "POST",
            f"/api/balanced-arrangement?token={self.token}",
            {"selection_manifest_sha256": selection_sha256},
        )

        self.assertEqual(status, 200)
        self.assertIn("balanced_arrangement", payload)
        trace = self.server.developer_trace
        self.assertIsNotNone(trace)
        operation = trace.snapshot()["recent_operations"][-1]
        self.assertEqual(operation["operation"], "arrangement.balance")
        self.assertEqual(
            operation["label"],
            "Render or reuse the source-referenced balanced audition",
        )
        self.assertEqual(operation["http_status"], 200)
        self.assertFalse(operation["durable_effect_possible"])
        self.assertIn(
            "sunofriend.workbench_artifacts.WorkbenchArtifacts.render_balanced_arrangement",
            operation["symbols"],
        )
        application_frames = [
            frame
            for frame in operation["frames"]
            if frame["stage"] == "application"
        ]
        self.assertEqual(len(application_frames), 1)
        self.assertEqual(application_frames[0]["facts"]["track_count"], 2)

    def test_selection_change_during_render_rejects_stale_media(self) -> None:
        status, _, project = self._json_request(
            "GET",
            f"/api/project?token={self.token}",
        )
        self.assertEqual(status, 200)
        selection_sha256 = project["decoded_arrangement_selection"][
            "selection_manifest_sha256"
        ]
        started = threading.Event()
        release = threading.Event()
        response: list[tuple[int, dict[str, str], dict]] = []

        def delayed_artifact(
            _catalog: dict,
            _state: dict,
            requested_sha256: str,
            *,
            promote_cache: bool = True,
        ) -> dict:
            self.assertFalse(promote_cache)
            started.set()
            self.assertTrue(release.wait(timeout=5))
            return {
                "selection_manifest_sha256": requested_sha256,
                "cache_key": "a" * 64,
                "_deferred_cache_claim": "b" * 32,
            }

        def request() -> None:
            response.append(
                self._json_request(
                    "POST",
                    f"/api/balanced-arrangement?token={self.token}",
                    {"selection_manifest_sha256": selection_sha256},
                )
            )

        with (
            patch.object(
                self.server.artifacts,
                "render_balanced_arrangement",
                side_effect=delayed_artifact,
            ),
            patch.object(
                self.server.artifacts,
                "discard_deferred_balanced_arrangement",
                side_effect=OSError("simulated best-effort cleanup failure"),
            ) as cleanup,
        ):
            worker = threading.Thread(target=request)
            worker.start()
            self.assertTrue(started.wait(timeout=5))
            stem = self.catalog["stems"][0]
            candidate = stem["candidates"][0]
            self.server.store.append(
                self.catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "reject",
                    "context": "full_mix",
                    "problem_tags": [],
                },
            )
            state_after_user_change = self.server.store.current_state(self.catalog)
            release.set()
            worker.join(timeout=5)

        cleanup.assert_called_once_with("a" * 64, "b" * 32)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(response), 1)
        status, _, payload = response[0]
        self.assertEqual(status, 409)
        self.assertIn("changed while", payload["error"])
        self.assertEqual(len(self.server.generated_media_ids), 0)
        self.assertEqual(
            self.server.store.current_state(self.catalog),
            state_after_user_change,
        )

    def test_stale_real_render_does_not_promote_or_prune_balanced_cache(
        self,
    ) -> None:
        status, _, project = self._json_request(
            "GET",
            f"/api/project?token={self.token}",
        )
        self.assertEqual(status, 200)
        selection_sha256 = project["decoded_arrangement_selection"][
            "selection_manifest_sha256"
        ]
        cache_root = self.state_dir / "artifacts" / "balanced-arrangements"
        cache_root.mkdir(mode=0o700, parents=True)
        sentinel_mtimes: dict[str, int] = {}
        for index in range(8):
            cache_key = f"{index + 1:064x}"
            entry = cache_root / cache_key
            entry.mkdir(mode=0o700)
            (entry / "sentinel.bin").write_bytes(bytes([index]))
            timestamp = 1_700_000_000_000_000_000 + index
            os.utime(entry, ns=(timestamp, timestamp))
            sentinel_mtimes[cache_key] = entry.stat().st_mtime_ns

        started = threading.Event()
        release = threading.Event()
        response: list[tuple[int, dict[str, str], dict]] = []
        built_cache_key: list[str] = []
        real_render = self.server.artifacts.render_balanced_arrangement

        def delayed_real_render(*args: object, **kwargs: object) -> dict:
            artifact = real_render(*args, **kwargs)
            cache_key = str(artifact["cache_key"])
            built_cache_key.append(cache_key)
            entry = cache_root / cache_key
            timestamp = 1_600_000_000_000_000_000
            os.utime(entry, ns=(timestamp, timestamp))
            started.set()
            self.assertTrue(release.wait(timeout=5))
            return artifact

        def request() -> None:
            response.append(
                self._json_request(
                    "POST",
                    f"/api/balanced-arrangement?token={self.token}",
                    {"selection_manifest_sha256": selection_sha256},
                )
            )

        with patch.object(
            self.server.artifacts,
            "render_balanced_arrangement",
            side_effect=delayed_real_render,
        ):
            worker = threading.Thread(target=request)
            worker.start()
            self.assertTrue(started.wait(timeout=5))
            stem = self.catalog["stems"][0]
            candidate = stem["candidates"][0]
            self.server.store.append(
                self.catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "reject",
                    "context": "full_mix",
                    "problem_tags": [],
                },
            )
            state_after_user_change = self.server.store.current_state(self.catalog)
            release.set()
            worker.join(timeout=5)

        self.assertFalse(worker.is_alive())
        self.assertEqual(len(response), 1)
        status, _, payload = response[0]
        self.assertEqual(status, 409)
        self.assertIn("changed while", payload["error"])
        self.assertEqual(len(built_cache_key), 1)
        built_entry = cache_root / built_cache_key[0]
        self.assertFalse(built_entry.exists())
        for cache_key, original_mtime in sentinel_mtimes.items():
            entry = cache_root / cache_key
            self.assertTrue(entry.is_dir(), cache_key)
            self.assertEqual(entry.stat().st_mtime_ns, original_mtime)
        self.assertEqual(
            len([entry for entry in cache_root.iterdir() if entry.is_dir()]),
            8,
        )
        self.assertEqual(len(self.server.generated_media_ids), 0)
        self.assertEqual(
            self.server.store.current_state(self.catalog),
            state_after_user_change,
        )

    def _start_server(self) -> None:
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()

    def _stop_server(self) -> None:
        server = getattr(self, "server", None)
        thread = getattr(self, "thread", None)
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join(timeout=5)
        self.server = None
        self.thread = None

    def _json_request(
        self,
        method: str,
        path: str,
        value: dict | None = None,
    ) -> tuple[int, dict[str, str], dict]:
        body = None if value is None else json.dumps(value).encode("utf-8")
        headers = {} if body is None else {"Content-Type": "application/json"}
        status, response_headers, payload = self._request(
            method,
            path,
            body=body,
            headers=headers,
        )
        return status, response_headers, json.loads(payload)

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            self.server.server_port,
            timeout=5,
        )
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return (
                response.status,
                {name.lower(): value for name, value in response.getheaders()},
                response.read(),
            )
        finally:
            connection.close()


def _catalog(root: Path) -> tuple[dict, Path]:
    project = root / "Balanced Server-D minor-120bpm-440hz"
    candidates = root / "candidates"
    project.mkdir()
    candidates.mkdir()
    _write_wav(
        project / "Balanced Server-kick-D minor-120bpm-440hz.wav",
        amplitude=0.05,
    )
    _write_wav(
        project / "Balanced Server-keys-D minor-120bpm-440hz.wav",
        amplitude=0.18,
    )
    _write_midi(candidates / "kick-listened.mid", channel=9, pitch=36)
    _write_midi(candidates / "keys-listened.mid", channel=0, pitch=60)
    soundfont = root / "test.sf2"
    soundfont.write_bytes(b"balanced-server-test-soundfont")
    return (
        build_workbench_catalog(project, candidate_roots=[candidates]),
        soundfont,
    )


def _write_midi(path: Path, *, channel: int, pitch: int) -> None:
    write_midi_file(
        path,
        [
            MidiTrack(
                name=path.stem,
                channel=channel,
                program=0,
                notes=[
                    NoteEvent(
                        start=index * 0.25,
                        end=index * 0.25 + 0.15,
                        pitch=pitch,
                        velocity=100,
                    )
                    for index in range(6)
                ],
            )
        ],
        bpm=120.0,
    )


def _render_preview(midi_path: Path, wav_path: Path, **_kwargs: object) -> None:
    amplitude = 0.80 if b"Kick" in Path(midi_path).read_bytes() else 0.12
    _write_wav(Path(wav_path), amplitude=amplitude)


def _write_wav(path: Path, *, amplitude: float, seconds: float = 1.5) -> None:
    sample_rate = 16_000
    frames = int(sample_rate * seconds)
    sample = int(amplitude * 32767).to_bytes(2, "little", signed=True)
    with wave.open(str(path), "wb") as destination:
        destination.setnchannels(2)
        destination.setsampwidth(2)
        destination.setframerate(sample_rate)
        destination.writeframes(sample * 2 * frames)


def _assert_no_paths(test: unittest.TestCase, value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            test.assertNotEqual(key, "path")
            test.assertFalse(key.endswith("_path"), key)
            _assert_no_paths(test, child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_paths(test, child)


if __name__ == "__main__":
    unittest.main()
