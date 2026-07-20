from __future__ import annotations

import hashlib
import http.client
import importlib.util
import json
import math
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.workbench_catalog import build_workbench_catalog
from sunofriend.workbench_server import create_workbench_server


class WorkbenchDecodedLoopServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.catalog, soundfont = _catalog(self.root)
        self.token = "decoded-loop-test-token"
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
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.render_patch.stop()
        self.temporary.cleanup()

    @unittest.skipUnless(
        importlib.util.find_spec("numpy") and importlib.util.find_spec("soundfile"),
        "decoded loop integration requires optional numpy and soundfile",
    )
    def test_path_free_loop_media_range_state_and_tamper_contract(self) -> None:
        stem = self.catalog["stems"][0]
        candidate_ids = [
            candidate["candidate_id"] for candidate in stem["candidates"]
        ]
        current = self.server.store.current_state(self.catalog)
        plan = self.server.artifacts.garageband_pack_plan(self.catalog, current)
        pack_scope = plan["basket_scope_sha256"]
        event_count = current["event_count"]
        pack_selection = self.server.store.current_pack_selection(
            self.catalog["project_id"], pack_scope
        )

        status, _, payload = self._json_request(
            "POST",
            f"/api/decoded-loop?token={self.token}",
            {
                "stem_id": stem["stem_id"],
                "candidate_ids": candidate_ids,
                "start_seconds": 0.25,
                "end_seconds": 1.25,
            },
        )

        self.assertEqual(status, 200)
        loop = payload["loop"]
        self.assertEqual(
            set(loop),
            {
                "schema",
                "stem_id",
                "candidate_ids",
                "start_seconds",
                "end_seconds",
                "duration_seconds",
                "cache_hit",
                "effects",
                "tracks",
            },
        )
        self.assertEqual(
            loop["schema"], "sunofriend.workbench-decoded-stem-loop.v1"
        )
        self.assertEqual(loop["stem_id"], stem["stem_id"])
        self.assertEqual(loop["candidate_ids"], candidate_ids)
        self.assertEqual(
            [track["kind"] for track in loop["tracks"]],
            ["source", "candidate", "candidate"],
        )
        self.assertEqual(
            [track.get("candidate_id") for track in loop["tracks"][1:]],
            candidate_ids,
        )
        self.assertEqual(
            loop["effects"],
            {
                "event_appended": False,
                "feedback_recorded": False,
                "midi_mutated": False,
                "selection_changed": False,
            },
        )
        serialized = json.dumps(loop)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn('"path"', serialized)

        audio_urls = [track["audio_url"] for track in loop["tracks"]]
        self.assertEqual(len(set(audio_urls)), 3)
        for track, audio_url in zip(loop["tracks"], audio_urls):
            self.assertIn("audio", track)
            expected_track_keys = {
                "track_id",
                "kind",
                "sample_rate",
                "channels",
                "frames",
                "start_frame",
                "silence_padded_frames",
                "audio",
                "audio_url",
            }
            if track["kind"] == "candidate":
                expected_track_keys.add("candidate_id")
            self.assertEqual(set(track), expected_track_keys)
            self.assertEqual(set(track["audio"]), {"name", "bytes", "sha256"})
            self.assertNotIn("path", track["audio"])
            self.assertEqual(track["audio"]["sha256"], _url_media_sha(self.server, audio_url))
            status, headers, body = self._request("GET", audio_url)
            self.assertEqual(status, 200)
            self.assertEqual(headers["accept-ranges"], "bytes")
            self.assertEqual(body[:4], b"RIFF")
            self.assertEqual(len(body), track["audio"]["bytes"])
            self.assertEqual(
                hashlib.sha256(body).hexdigest(), track["audio"]["sha256"]
            )

        status, headers, body = self._request(
            "GET",
            audio_urls[1],
            headers={"Range": "bytes=0-3"},
        )
        self.assertEqual(status, 206)
        self.assertEqual(body, b"RIFF")
        self.assertEqual(
            headers["content-range"],
            f"bytes 0-3/{loop['tracks'][1]['audio']['bytes']}",
        )

        self.assertEqual(
            self.server.store.current_state(self.catalog)["event_count"],
            event_count,
        )
        self.assertEqual(
            self.server.store.current_pack_selection(
                self.catalog["project_id"], pack_scope
            ),
            pack_selection,
        )

        tampered_media_id = _media_id(audio_urls[-1])
        tampered_record = self.server.media[tampered_media_id]
        tampered_path = Path(str(tampered_record["path"]))
        tampered_path.write_bytes(tampered_path.read_bytes() + b"tampered")
        status, _, body = self._request("GET", audio_urls[-1])
        self.assertEqual(status, 409)
        self.assertIn(b"changed after it was catalogued", body)
        self.assertEqual(
            self.server.store.current_state(self.catalog)["event_count"],
            event_count,
        )
        self.assertEqual(
            self.server.store.current_pack_selection(
                self.catalog["project_id"], pack_scope
            ),
            pack_selection,
        )

    def test_static_transport_auth_and_invalid_requests_fail_closed(self) -> None:
        status, headers, _ = self._request("GET", f"/?token={self.token}")
        self.assertEqual(status, 200)
        self.assertIn(
            "script-src 'self' 'unsafe-inline'",
            headers["content-security-policy"],
        )

        status, headers, body = self._request("GET", "/workbench-transport.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers["content-type"])
        self.assertEqual(headers["cache-control"], "no-store")
        self.assertIn(b"SunofriendWorkbenchTransport", body)

        stem = self.catalog["stems"][0]
        candidate_ids = [
            candidate["candidate_id"] for candidate in stem["candidates"]
        ]
        valid = {
            "stem_id": stem["stem_id"],
            "candidate_ids": candidate_ids,
            "start_seconds": 0.0,
            "end_seconds": 1.0,
        }
        event_count = self.server.store.current_state(self.catalog)["event_count"]

        status, _, payload = self._json_request(
            "POST",
            "/api/decoded-loop?token=wrong",
            valid,
        )
        self.assertEqual(status, 403)
        self.assertIn("token", payload["error"])
        self.renderer.assert_not_called()

        invalid_requests = (
            ({**valid, "unexpected": True}, "unexpected unexpected"),
            (
                {key: value for key, value in valid.items() if key != "end_seconds"},
                "missing end_seconds",
            ),
            ({**valid, "candidate_ids": candidate_ids[0]}, "must be a sequence"),
            ({**valid, "start_seconds": True}, "finite numbers"),
            (
                {**valid, "candidate_ids": [candidate_ids[0], candidate_ids[0]]},
                "must be unique",
            ),
            ({**valid, "candidate_ids": ["unknown-candidate"]}, "does not belong"),
            ({**valid, "stem_id": "unknown-stem"}, "unknown workbench stem_id"),
        )
        for request, message in invalid_requests:
            with self.subTest(message=message):
                status, _, payload = self._json_request(
                    "POST",
                    f"/api/decoded-loop?token={self.token}",
                    request,
                )
                self.assertEqual(status, 400)
                self.assertIn(message, payload["error"])

        self.renderer.assert_not_called()
        self.assertEqual(
            self.server.store.current_state(self.catalog)["event_count"],
            event_count,
        )

    def _json_request(
        self,
        method: str,
        path: str,
        value: dict,
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
    project = root / "Decoded Loop-B major-120bpm-440hz"
    candidates = root / "candidate-runs"
    project.mkdir()
    candidates.mkdir()
    source = project / "Decoded Loop-keys-B major-120bpm-440hz.wav"
    _write_pcm_wav(source, sample_rate=16_000, frames=32_000, tone_hz=196.0)

    first = candidates / "keys-baseline.mid"
    second = candidates / "keys-ai.mid"
    _write_midi(first, pitch=60)
    _write_midi(second, pitch=64)
    catalog_path = root / "workbench-catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "schema": "sunofriend.workbench-catalog.v1",
                "stems": [
                    {
                        "source": str(source),
                        "role": "keys",
                        "candidates": [
                            {"midi": str(first), "label": "Baseline"},
                            {"midi": str(second), "label": "AI alternative"},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    soundfont = root / "test.sf2"
    soundfont.write_bytes(b"decoded-loop-test-soundfont")
    return (
        build_workbench_catalog(
            project,
            candidate_roots=[candidates],
            catalog_path=catalog_path,
        ),
        soundfont,
    )


def _write_midi(path: Path, *, pitch: int) -> None:
    write_midi_file(
        path,
        [
            MidiTrack(
                name="Keys",
                channel=0,
                program=4,
                notes=[
                    NoteEvent(start=0.0, end=1.5, pitch=pitch, velocity=88),
                ],
            )
        ],
        bpm=120.0,
    )


def _render_valid_neutral_preview(midi_path, wav_path, **_kwargs) -> Path:
    digest = hashlib.sha256(Path(midi_path).read_bytes()).digest()
    tone_hz = 220.0 + digest[0]
    destination = Path(wav_path)
    _write_pcm_wav(
        destination,
        sample_rate=16_000,
        frames=32_000,
        tone_hz=tone_hz,
    )
    return destination


def _write_pcm_wav(
    path: Path,
    *,
    sample_rate: int,
    frames: int,
    tone_hz: float,
) -> None:
    samples = bytearray()
    for frame in range(frames):
        value = int(8_000 * math.sin(2.0 * math.pi * tone_hz * frame / sample_rate))
        samples.extend(value.to_bytes(2, "little", signed=True))
    with wave.open(str(path), "wb") as destination:
        destination.setnchannels(1)
        destination.setsampwidth(2)
        destination.setframerate(sample_rate)
        destination.writeframes(bytes(samples))


def _media_id(audio_url: str) -> str:
    return urlparse(audio_url).path.removeprefix("/media/")


def _url_media_sha(server, audio_url: str) -> str:
    return str(server.media[_media_id(audio_url)]["sha256"])


if __name__ == "__main__":
    unittest.main()
