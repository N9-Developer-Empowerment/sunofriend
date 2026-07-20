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

from sunofriend import workbench_artifacts as artifacts_module
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.workbench_artifacts import WorkbenchArtifacts
from sunofriend.workbench_catalog import build_workbench_catalog
from sunofriend.workbench_server import create_workbench_server


class WorkbenchPhase56ArtifactHardeningTests(unittest.TestCase):
    def test_preview_input_budget_stops_fanout_and_discards_crossing_render(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, soundfont = _catalog(root, candidate_count=3)
            current = _selected_state(catalog, selected_count=3)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )
            stem = catalog["stems"][0]
            declared_bytes = (
                int(stem["source"]["bytes"])
                + sum(
                    int(candidate["midi"]["bytes"])
                    for candidate in stem["candidates"]
                )
                + soundfont.stat().st_size
            )
            created: list[Path] = []

            def render_preview(*_args, **_kwargs):
                index = len(created) + 1
                cache_key = f"{index:064x}"
                cache_dir = artifacts.root / "previews" / cache_key
                cache_dir.mkdir(parents=True)
                preview_path = cache_dir / "neutral-preview.wav"
                preview_path.write_bytes(bytes([index]) * 60)
                created.append(cache_dir)
                return {
                    "cache_key": cache_key,
                    "cache_hit": False,
                    "preview": _record(preview_path),
                }

            with (
                patch.object(
                    artifacts_module,
                    "_DECODED_LOOP_MAXIMUM_INPUT_BYTES",
                    declared_bytes + 100,
                ),
                patch.object(
                    artifacts,
                    "cached_candidate_preview",
                    return_value=None,
                ),
                patch.object(
                    artifacts,
                    "render_candidate_preview",
                    side_effect=render_preview,
                ) as renderer,
            ):
                with self.assertRaisesRegex(ValueError, "2 GiB aggregate"):
                    artifacts.prepare_decoded_arrangement_loop(
                        catalog,
                        current,
                        selection["selection_manifest_sha256"],
                        0.0,
                        1.0,
                    )

            self.assertEqual(renderer.call_count, 2)
            self.assertEqual(len(created), 2)
            self.assertTrue(created[0].is_dir())
            self.assertFalse(created[1].exists())

    @unittest.skipUnless(
        importlib.util.find_spec("numpy") and importlib.util.find_spec("soundfile"),
        "decoded arrangement output preflight needs numpy and soundfile",
    )
    def test_pcm16_output_limit_fails_before_decoded_cache_build(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, soundfont = _catalog(root, candidate_count=1)
            current = _selected_state(catalog, selected_count=1)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            selection = artifacts.decoded_arrangement_selection_manifest(
                catalog, current
            )

            with (
                patch(
                    "sunofriend.workbench_artifacts.render_midi_to_wav",
                    side_effect=_render_preview,
                ),
                patch.object(
                    artifacts_module, "_DECODED_LOOP_MAXIMUM_OUTPUT_BYTES", 128
                ),
                patch.object(
                    artifacts,
                    "_private_building_directory",
                    side_effect=AssertionError(
                        "decoded cache build must not start above the output limit"
                    ),
                ) as private_builder,
            ):
                with self.assertRaisesRegex(ValueError, "64 MiB limit"):
                    artifacts.prepare_decoded_arrangement_loop(
                        catalog,
                        current,
                        selection["selection_manifest_sha256"],
                        0.0,
                        1.0,
                    )

            private_builder.assert_not_called()
            self.assertFalse(
                (artifacts.root / "decoded-arrangement-loops").exists()
            )

    def test_cache_lookup_ignores_building_directory_and_takes_artifact_lock(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, soundfont = _catalog(root, candidate_count=1)
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_render_preview,
            ):
                rendered = artifacts.render_candidate_preview(
                    catalog, stem["stem_id"], candidate["candidate_id"]
                )
            cache_dir = artifacts.root / "previews" / rendered["cache_key"]
            building = cache_dir.with_name(
                f".{rendered['cache_key']}.building-regression"
            )
            cache_dir.rename(building)
            self.assertIsNone(
                artifacts.cached_candidate_preview(
                    catalog, stem["stem_id"], candidate["candidate_id"]
                )
            )
            building.rename(cache_dir)

            entered = threading.Event()
            finished = threading.Event()
            result: list[dict | None] = []

            def lookup() -> None:
                entered.set()
                result.append(
                    artifacts.cached_candidate_preview(
                        catalog, stem["stem_id"], candidate["candidate_id"]
                    )
                )
                finished.set()

            with artifacts._lock:
                worker = threading.Thread(target=lookup)
                worker.start()
                self.assertTrue(entered.wait(timeout=1.0))
                self.assertFalse(finished.wait(timeout=0.05))
            worker.join(timeout=2.0)

            self.assertFalse(worker.is_alive())
            self.assertTrue(finished.is_set())
            self.assertEqual(result[0]["cache_key"], rendered["cache_key"])


class WorkbenchPhase56ServerRoleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.catalog, soundfont = _catalog(self.root, candidate_count=1)
        self.token = "phase56-release-hardening-token"
        self.server = create_workbench_server(
            self.catalog,
            state_dir=self.root / "state",
            token=self.token,
            soundfont_path=soundfont,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5.0)
        self.temporary.cleanup()

    def test_render_preview_uses_saved_role_and_project_finds_same_cache(self) -> None:
        stem = self.catalog["stems"][0]
        candidate = stem["candidates"][0]
        self.server.store.append(
            self.catalog,
            {
                "event_type": "role_tag",
                "stem_id": stem["stem_id"],
                "role": "bass",
            },
        )
        with patch(
            "sunofriend.workbench_artifacts.render_midi_to_wav",
            side_effect=_render_preview,
        ):
            status, payload = self._json_request(
                "POST",
                f"/api/render-preview?token={self.token}",
                {
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                },
            )
        self.assertEqual(status, 200)
        self.assertEqual(payload["preview"]["role"], "bass")
        self.assertEqual(payload["preview"]["program"], 33)

        status, project = self._json_request(
            "GET", f"/api/project?token={self.token}"
        )
        self.assertEqual(status, 200)
        cached = project["stems"][0]["candidates"][0]["neutral_preview"]
        self.assertIsNotNone(cached)
        self.assertEqual(cached["role"], "bass")
        self.assertEqual(cached["cache_key"], payload["preview"]["cache_key"])

    def test_role_change_during_render_returns_conflict_without_media(self) -> None:
        stem = self.catalog["stems"][0]
        candidate = stem["candidates"][0]
        self.server.store.append(
            self.catalog,
            {
                "event_type": "role_tag",
                "stem_id": stem["stem_id"],
                "role": "bass",
            },
        )
        existing_media = set(self.server.media)

        def render_then_change(midi_path, wav_path, **kwargs):
            result = _render_preview(midi_path, wav_path, **kwargs)
            self.server.store.append(
                self.catalog,
                {
                    "event_type": "role_tag",
                    "stem_id": stem["stem_id"],
                    "role": "strings",
                },
            )
            return result

        with patch(
            "sunofriend.workbench_artifacts.render_midi_to_wav",
            side_effect=render_then_change,
        ):
            status, payload = self._json_request(
                "POST",
                f"/api/render-preview?token={self.token}",
                {
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                },
            )

        self.assertEqual(status, 409)
        self.assertIn("role changed", payload["error"])
        self.assertEqual(set(self.server.media), existing_media)

    def _json_request(
        self, method: str, path: str, value: dict | None = None
    ) -> tuple[int, dict]:
        body = json.dumps(value).encode("utf-8") if value is not None else None
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=5
        )
        try:
            connection.request(
                method,
                path,
                body=body,
                headers={"Content-Type": "application/json"} if body else {},
            )
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()


def _catalog(root: Path, *, candidate_count: int) -> tuple[dict, Path]:
    project = root / "Release Hardening-B major-120bpm-440hz"
    candidates = root / "candidates"
    project.mkdir()
    candidates.mkdir()
    source = project / "Release Hardening-keys-B major-120bpm-440hz.wav"
    _write_pcm_wav(source, sample_rate=16_000, frames=32_000, tone_hz=196.0)
    rows = []
    for index in range(candidate_count):
        midi = candidates / f"keys-candidate-{index + 1}.mid"
        _write_midi(midi, pitch=60 + index)
        rows.append({"midi": str(midi), "label": f"Candidate {index + 1}"})
    catalog_path = root / "workbench-catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "schema": "sunofriend.workbench-catalog.v1",
                "stems": [
                    {
                        "source": str(source),
                        "role": "keys",
                        "candidates": rows,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    soundfont = root / "test.sf2"
    soundfont.write_bytes(b"phase56-release-hardening-soundfont")
    return (
        build_workbench_catalog(
            project,
            candidate_roots=[candidates],
            catalog_path=catalog_path,
        ),
        soundfont,
    )


def _selected_state(catalog: dict, *, selected_count: int) -> dict:
    stem = catalog["stems"][0]
    candidates = stem["candidates"][:selected_count]
    return {
        "stems": {
            stem["stem_id"]: {
                "role": "keys",
                "main_candidate_id": candidates[0]["candidate_id"],
                "candidates": {
                    candidate["candidate_id"]: {
                        "decision": "main" if index == 0 else "optional",
                        "selection_active": True,
                    }
                    for index, candidate in enumerate(candidates)
                },
            }
        },
        "event_count": selected_count,
    }


def _write_midi(path: Path, *, pitch: int) -> None:
    write_midi_file(
        path,
        [
            MidiTrack(
                "Keys",
                0,
                4,
                [NoteEvent(start=0.0, end=2.0, pitch=pitch, velocity=88)],
            )
        ],
        bpm=120.0,
    )


def _render_preview(_midi_path: Path, wav_path: Path, **_kwargs) -> Path:
    destination = Path(wav_path)
    _write_pcm_wav(
        destination,
        sample_rate=16_000,
        frames=32_000,
        tone_hz=261.63,
    )
    return destination


def _write_pcm_wav(
    path: Path, *, sample_rate: int, frames: int, tone_hz: float
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


def _record(path: Path) -> dict:
    payload = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "name": path.name,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


if __name__ == "__main__":
    unittest.main()
