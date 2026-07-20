from __future__ import annotations

import hashlib
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from sunofriend.workbench_server import (
    _read_verified_immutable_bytes,
    create_workbench_server,
)

from tests.test_workbench_pack_artifacts import _pack_catalog


class WorkbenchPhraseLinkServerTests(unittest.TestCase):
    def test_verified_phrase_payload_is_an_immutable_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "phrase.wav"
            original = b"RIFF-pinned-phrase"
            path.write_bytes(original)
            record = _record(path, media_kind="audio")
            with path.open("rb") as handle:
                snapshot = _read_verified_immutable_bytes(handle, record)

            path.write_bytes(b"changed after verification")

            self.assertEqual(snapshot, original)
            self.assertEqual(hashlib.sha256(snapshot).hexdigest(), record["sha256"])

    def test_capability_serves_only_pinned_page_and_audio_without_recording_state(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _pack_catalog(root)
            package = root / "phrase-review"
            audio_dir = package / "audio"
            audio_dir.mkdir(parents=True)
            html = package / "melody_phrase_review.html"
            audio = audio_dir / "unit 01-source.wav"
            private_manifest = package / "phrase_review.json"
            html.write_text(
                '<!doctype html><audio src="audio/unit 01-source.wav"></audio>',
                encoding="utf-8",
            )
            audio.write_bytes(b"RIFF-private-phrase-audio")
            private_manifest.write_text('{"private":true}', encoding="utf-8")
            stem = catalog["stems"][0]
            stem["_phrase_review_link"] = {
                "public": {
                    "schema": "sunofriend.workbench-phrase-review-link.v1",
                    "link_sha256": "1" * 64,
                    "candidate_map": {},
                    "lineage": {},
                    "ranges": [
                        {
                            "phrase_index": 0,
                            "start_seconds": 0.5,
                            "end_seconds": 4.7,
                            "diagnostic_reference_count": 47,
                        }
                    ],
                    "effects": {
                        "feedback_recorded": False,
                        "automatic_selection": False,
                    },
                    "private_page": True,
                },
                "entrypoint": html.name,
                "files": {
                    html.name: _record(html, media_kind="html"),
                    "audio/unit 01-source.wav": _record(audio, media_kind="audio"),
                },
            }
            server = create_workbench_server(
                catalog,
                state_dir=root / "state",
                token="phrase-token",
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                status, headers, body = _request(
                    server.server_port,
                    "/api/project?token=phrase-token",
                )
                self.assertEqual(status, 200)
                project = json.loads(body)
                rendered = json.dumps(project, sort_keys=True)
                self.assertNotIn(str(root), rendered)
                public_stem = next(
                    row for row in project["stems"] if row["stem_id"] == stem["stem_id"]
                )
                link = public_stem["phrase_review_link"]
                review_url = link["review_url"]
                self.assertTrue(review_url.startswith("/phrase-review/"))
                self.assertNotIn("phrase-token", review_url)
                self.assertNotIn("?", review_url)

                status, headers, body = _request(server.server_port, review_url)
                self.assertEqual(status, 200)
                self.assertEqual(body, html.read_bytes())
                self.assertIn("text/html", headers["content-type"])
                self.assertIn("connect-src 'none'", headers["content-security-policy"])
                self.assertIn(
                    "sandbox allow-scripts allow-same-origin allow-downloads allow-modals",
                    headers["content-security-policy"],
                )
                self.assertIn("form-action 'none'", headers["content-security-policy"])
                self.assertNotIn(
                    "allow-top-navigation", headers["content-security-policy"]
                )
                self.assertEqual(headers["permissions-policy"], "autoplay=()")
                self.assertEqual(headers["cache-control"], "no-store")

                base = review_url.rsplit("/", 1)[0]
                status, headers, body = _request(
                    server.server_port,
                    base + "/audio/unit%2001-source.wav",
                    headers={"Range": "bytes=0-3"},
                )
                self.assertEqual(status, 206)
                self.assertEqual(body, b"RIFF")
                self.assertEqual(headers["accept-ranges"], "bytes")
                self.assertEqual(
                    headers["content-range"],
                    f"bytes 0-3/{audio.stat().st_size}",
                )
                self.assertIn("connect-src 'none'", headers["content-security-policy"])

                status, _, _ = _request(
                    server.server_port,
                    base + "/phrase_review.json",
                )
                self.assertEqual(status, 404)
                status, _, _ = _request(
                    server.server_port,
                    "/phrase-review/not-the-capability/melody_phrase_review.html",
                )
                self.assertEqual(status, 404)
                status, _, _ = _request(
                    server.server_port,
                    base + "/audio/%FF.wav",
                )
                self.assertEqual(status, 404)

                audio.write_bytes(audio.read_bytes() + b"changed")
                status, _, body = _request(
                    server.server_port,
                    base + "/audio/unit%2001-source.wav",
                )
                self.assertEqual(status, 409)
                self.assertIn("changed after it was catalogued", body.decode())

                self.assertEqual(server.store.current_state(catalog)["event_count"], 0)
                private_review = server.store.export_review(catalog)
                self.assertNotIn("phrase_review_link", json.dumps(private_review))
                plan = server.artifacts.garageband_pack_plan(
                    catalog,
                    server.store.current_state(catalog),
                )
                self.assertFalse(
                    any(item["kind"] == "phrase_review" for item in plan["items"])
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


def _record(path: Path, *, media_kind: str) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "media_kind": media_kind,
    }


def _request(
    port: int,
    path: str,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request("GET", path, headers=headers or {})
    response = connection.getresponse()
    status = response.status
    response_headers = {key.lower(): value for key, value in response.getheaders()}
    body = response.read()
    connection.close()
    return status, response_headers, body


if __name__ == "__main__":
    unittest.main()
