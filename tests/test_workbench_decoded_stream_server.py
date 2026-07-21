from __future__ import annotations

import hashlib
import http.client
import importlib.util
import json
import tempfile
import threading
import unittest
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sunofriend import workbench_server as server_module
from sunofriend.workbench_server import create_workbench_server

from .test_workbench_decoded_loop_server import (
    _catalog,
    _media_id,
    _render_valid_neutral_preview,
)


class WorkbenchDecodedStreamServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.catalog, soundfont = _catalog(self.root)
        self.token = "decoded-stream-test-token"
        self.server = create_workbench_server(
            self.catalog,
            state_dir=self.root / "state",
            token=self.token,
            soundfont_path=soundfont,
        )
        self.render_patch = patch(
            "sunofriend.workbench_artifacts.render_midi_to_wav",
            side_effect=_render_valid_neutral_preview,
        )
        self.renderer = self.render_patch.start()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.render_patch.stop()
        self.temporary.cleanup()

    def _select_main(self) -> dict:
        stem = self.catalog["stems"][0]
        candidate = stem["candidates"][0]
        self.server.store.append(
            self.catalog,
            {
                "event_type": "candidate_decision",
                "stem_id": stem["stem_id"],
                "candidate_id": candidate["candidate_id"],
                "decision": "main",
                "context": "solo",
                "problem_tags": [],
            },
        )
        current = self.server.store.current_state(self.catalog)
        return self.server.artifacts.decoded_arrangement_selection_manifest(
            self.catalog, current
        )

    def test_strict_stream_and_chunk_requests_fail_before_rendering(self) -> None:
        manifest = self._select_main()
        valid = {
            "selection_manifest_sha256": manifest["selection_manifest_sha256"],
            "preset": "source-only",
        }
        event_count = self.server.store.current_state(self.catalog)["event_count"]
        existing_media = dict(self.server.media)

        for path, request in (
            ("/api/decoded-arrangement-stream?token=wrong", valid),
            (
                "/api/decoded-arrangement-chunk?token=wrong",
                {"stream_sha256": "0" * 64, "chunk_index": 0},
            ),
        ):
            with self.subTest(path=path):
                status, _, payload = self._json_request("POST", path, request)
                self.assertEqual(status, 403)
                self.assertIn("token", payload["error"])

        invalid_streams = (
            ({**valid, "track_ids": []}, "unexpected track_ids"),
            ({"preset": "source-only"}, "missing selection_manifest_sha256"),
            ({**valid, "selection_manifest_sha256": True}, "lowercase SHA-256"),
            (
                {**valid, "selection_manifest_sha256": int("1" * 64)},
                "lowercase SHA-256",
            ),
            ({**valid, "selection_manifest_sha256": "A" * 64}, "lowercase SHA-256"),
            ({**valid, "preset": "custom"}, "must be exactly"),
        )
        for request, message in invalid_streams:
            with self.subTest(message=message):
                status, _, payload = self._json_request(
                    "POST",
                    f"/api/decoded-arrangement-stream?token={self.token}",
                    request,
                )
                self.assertEqual(status, 400)
                self.assertIn(message, payload["error"])

        invalid_chunks = (
            ({"stream_sha256": "0" * 64}, "missing chunk_index"),
            (
                {"stream_sha256": "0" * 64, "chunk_index": True},
                "must be an integer",
            ),
            (
                {"stream_sha256": "0" * 64, "chunk_index": 0.0},
                "must be an integer",
            ),
            (
                {"stream_sha256": int("1" * 64), "chunk_index": 0},
                "lowercase SHA-256",
            ),
            (
                {"stream_sha256": "A" * 64, "chunk_index": 0},
                "lowercase SHA-256",
            ),
            (
                {"stream_sha256": "0" * 64, "chunk_index": 0, "gain": 1},
                "unexpected gain",
            ),
            (
                {"stream_sha256": "0" * 64, "chunk_index": 0},
                "stream is not active",
            ),
        )
        for request, message in invalid_chunks:
            with self.subTest(message=message):
                status, _, payload = self._json_request(
                    "POST",
                    f"/api/decoded-arrangement-chunk?token={self.token}",
                    request,
                )
                self.assertEqual(status, 400)
                self.assertIn(message, payload["error"])

        self.renderer.assert_not_called()
        self.assertEqual(self.server.media, existing_media)
        self.assertEqual(
            self.server.store.current_state(self.catalog)["event_count"],
            event_count,
        )

    @unittest.skipUnless(
        importlib.util.find_spec("numpy") and importlib.util.find_spec("soundfile"),
        "decoded stream integration requires optional numpy and soundfile",
    )
    def test_source_only_stream_chunk_is_path_free_range_capable_and_neutral(self) -> None:
        manifest = self._select_main()
        before = self.server.store.current_state(self.catalog)
        status, _, payload = self._json_request(
            "POST",
            f"/api/decoded-arrangement-stream?token={self.token}",
            {
                "selection_manifest_sha256": manifest[
                    "selection_manifest_sha256"
                ],
                "preset": "source-only",
            },
        )
        self.assertEqual(status, 200)
        stream = payload["stream"]
        self.assertEqual(
            stream["schema"],
            "sunofriend.workbench-decoded-arrangement-stream.v1",
        )
        self.assertEqual(stream["preset"], "source-only")
        self.assertIsNone(stream["renderer"])
        self.assertTrue(stream["preset_track_ids"])
        self.assertEqual(stream["preset_track_ids"], [stream["tracks"][0]["track_id"]])
        self.assertGreater(stream["anchor"]["song_end_frame"], 0)
        self.assertGreaterEqual(stream["chunking"]["chunk_count"], 1)
        self.assertLessEqual(stream["chunking"]["chunk_seconds"], 5)
        self.assertTrue(all(value is False for value in stream["effects"].values()))
        serialized = json.dumps(stream)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn('"path"', serialized)
        self.renderer.assert_not_called()

        for invalid_index in (-1, stream["chunking"]["chunk_count"]):
            with self.subTest(invalid_index=invalid_index):
                existing_media = dict(self.server.media)
                status, _, invalid = self._json_request(
                    "POST",
                    f"/api/decoded-arrangement-chunk?token={self.token}",
                    {
                        "stream_sha256": stream["stream_sha256"],
                        "chunk_index": invalid_index,
                    },
                )
                self.assertEqual(status, 400)
                self.assertIn("out of range", invalid["error"])
                self.assertEqual(self.server.media, existing_media)

        status, _, chunk_payload = self._json_request(
            "POST",
            f"/api/decoded-arrangement-chunk?token={self.token}",
            {"stream_sha256": stream["stream_sha256"], "chunk_index": 0},
        )
        self.assertEqual(status, 200)
        chunk = chunk_payload["chunk"]
        self.assertEqual(
            chunk["schema"],
            "sunofriend.workbench-decoded-arrangement-chunk.v1",
        )
        self.assertEqual(chunk["stream_sha256"], stream["stream_sha256"])
        self.assertEqual(chunk["preset"], "source-only")
        self.assertEqual(chunk["anchor"]["start_frame"], 0)
        self.assertGreater(chunk["anchor"]["end_frame"], 0)
        self.assertEqual(
            [track["track_id"] for track in chunk["tracks"]],
            stream["preset_track_ids"],
        )
        self.assertNotIn(str(self.root), json.dumps(chunk))
        self.assertNotIn('"path"', json.dumps(chunk))

        audio_url = chunk["tracks"][0]["audio_url"]
        status, headers, body = self._request(
            "GET", audio_url, headers={"Range": "bytes=0-3"}
        )
        self.assertEqual(status, 206)
        self.assertEqual(body, b"RIFF")
        self.assertEqual(headers["accept-ranges"], "bytes")
        status, _, body = self._request("GET", audio_url)
        self.assertEqual(status, 200)
        self.assertEqual(
            hashlib.sha256(body).hexdigest(), chunk["tracks"][0]["audio"]["sha256"]
        )
        whole_body = body

        status, headers, body = self._request(
            "GET", audio_url, headers={"Range": "bytes=-4"}
        )
        self.assertEqual(status, 206)
        self.assertEqual(body, whole_body[-4:])
        self.assertEqual(
            headers["content-range"],
            f"bytes {len(whole_body) - 4}-{len(whole_body) - 1}/{len(whole_body)}",
        )

        status, headers, body = self._request(
            "GET", audio_url, headers={"Range": "bytes=4-"}
        )
        self.assertEqual(status, 206)
        self.assertEqual(body, whole_body[4:])
        self.assertEqual(
            headers["content-range"],
            f"bytes 4-{len(whole_body) - 1}/{len(whole_body)}",
        )

        status, headers, body = self._request(
            "GET", audio_url, headers={"Range": "bytes=0-1,4-5"}
        )
        self.assertEqual(status, 416)
        self.assertEqual(headers["content-range"], f"bytes */{len(whole_body)}")
        self.assertIn(b"unsupported byte range", body)
        self.assertEqual(self.server.store.current_state(self.catalog), before)
        self.renderer.assert_not_called()

        record = self.server.media[_media_id(audio_url)]
        Path(str(record["path"])).write_bytes(Path(str(record["path"])).read_bytes() + b"x")
        status, _, body = self._request("GET", audio_url)
        self.assertEqual(status, 409)
        self.assertIn(b"changed after it was catalogued", body)

    @unittest.skipUnless(
        importlib.util.find_spec("numpy") and importlib.util.find_spec("soundfile"),
        "decoded stream integration requires optional numpy and soundfile",
    )
    def test_chunk_rejects_selection_changed_after_plan(self) -> None:
        manifest = self._select_main()
        status, _, payload = self._json_request(
            "POST",
            f"/api/decoded-arrangement-stream?token={self.token}",
            {
                "selection_manifest_sha256": manifest[
                    "selection_manifest_sha256"
                ],
                "preset": "source-only",
            },
        )
        self.assertEqual(status, 200)
        stream_sha256 = payload["stream"]["stream_sha256"]

        stem = self.catalog["stems"][0]
        self.server.store.append(
            self.catalog,
            {
                "event_type": "role_tag",
                "stem_id": stem["stem_id"],
                "role": "changed keys role",
            },
        )
        existing_media = dict(self.server.media)
        status, _, stale = self._json_request(
            "POST",
            f"/api/decoded-arrangement-chunk?token={self.token}",
            {"stream_sha256": stream_sha256, "chunk_index": 0},
        )
        self.assertEqual(status, 409)
        self.assertIn("changed", stale["error"])
        self.assertEqual(self.server.media, existing_media)

    def _json_request(
        self, method: str, path: str, value: dict
    ) -> tuple[int, dict[str, str], dict]:
        status, headers, body = self._request(
            method,
            path,
            body=json.dumps(value).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        return status, headers, json.loads(body)

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=10
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


class WorkbenchGeneratedMediaRegistryTests(unittest.TestCase):
    def test_active_stream_refresh_is_bounded_to_the_expected_plan(self) -> None:
        handler = object.__new__(server_module._WorkbenchHandler)
        first = "1" * 64
        second = "2" * 64
        fake_server = SimpleNamespace(
            state_lock=threading.RLock(),
            decoded_stream_plans=OrderedDict(
                (
                    (first, {"stream_sha256": first}),
                    (second, {"stream_sha256": second}),
                )
            ),
        )
        handler.server = fake_server

        handler._refresh_decoded_stream_plan(
            first, fake_server.decoded_stream_plans[first]
        )

        self.assertEqual(list(fake_server.decoded_stream_plans), [second, first])
        self.assertEqual(
            fake_server.decoded_stream_plans[first], {"stream_sha256": first}
        )
        with self.assertRaisesRegex(ValueError, "not active"):
            handler._refresh_decoded_stream_plan(
                first, {"stream_sha256": first, "changed": True}
            )

    def test_generated_registry_is_bounded_and_refreshes_registration_recency(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = {}
            for name in ("catalog", "generated-a", "generated-b", "generated-c"):
                path = root / f"{name}.wav"
                path.write_bytes(name.encode("utf-8"))
                payload = path.read_bytes()
                records[name] = {
                    "path": str(path),
                    "name": path.name,
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }

            fake_server = SimpleNamespace(
                state_lock=threading.RLock(),
                media={"catalog": dict(records["catalog"])},
                catalog_media_ids=frozenset({"catalog"}),
                generated_media_ids=OrderedDict(),
            )
            handler = object.__new__(server_module._WorkbenchHandler)
            handler.server = fake_server

            with patch.object(server_module, "_MAX_GENERATED_MEDIA_RECORDS", 2):
                handler._register_generated_media(
                    "generated-a", records["generated-a"]
                )
                handler._register_generated_media(
                    "generated-b", records["generated-b"]
                )
                self.assertEqual(
                    list(fake_server.generated_media_ids),
                    ["generated-a", "generated-b"],
                )

                # Registering an existing capability again makes it most recent.
                handler._register_generated_media(
                    "generated-a", records["generated-a"]
                )
                handler._register_generated_media(
                    "generated-c", records["generated-c"]
                )

            self.assertEqual(
                list(fake_server.generated_media_ids),
                ["generated-a", "generated-c"],
            )
            self.assertEqual(
                set(fake_server.media),
                {"catalog", "generated-a", "generated-c"},
            )
            self.assertEqual(fake_server.media["catalog"], records["catalog"])
            self.assertNotIn("generated-b", fake_server.media)
            self.assertTrue(
                all(Path(record["path"]).exists() for record in records.values())
            )


if __name__ == "__main__":
    unittest.main()
