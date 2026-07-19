from __future__ import annotations

import http.client
import hashlib
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.workbench_catalog import build_workbench_catalog, public_catalog
from sunofriend.workbench_artifacts import WorkbenchArtifacts
from sunofriend.workbench_server import create_workbench_server
from sunofriend.workbench_store import WorkbenchStore


class WorkbenchCatalogTests(unittest.TestCase):
    def test_discovers_bounded_role_candidates_and_path_free_public_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Test Song-B minor-113bpm-440hz"
            candidates = root / "candidate-runs"
            project.mkdir()
            source = project / "Test Song-bass-B minor-113bpm-440hz.wav"
            source.write_bytes(b"RIFF-source-audio")

            for index, directory_name in enumerate(
                ("bass-baseline", "bass-muscriptor", "bass-hybrid", "bass-cleanup"),
                start=1,
            ):
                directory = candidates / directory_name
                directory.mkdir(parents=True)
                midi = directory / (
                    "bass_listened.mid" if index == 1 else "candidate.mid"
                )
                _write_midi(midi, pitch=35 + index)
                if index == 1:
                    midi.with_suffix(".preview.wav").write_bytes(b"RIFF-preview")

            catalog = build_workbench_catalog(
                project,
                candidate_roots=[candidates],
            )

            self.assertEqual(catalog["setup"]["bpm"], 113.0)
            self.assertEqual(catalog["setup"]["key"], "B minor")
            self.assertEqual(catalog["setup"]["tuning_hz"], 440.0)
            self.assertEqual(len(catalog["stems"]), 1)
            stem = catalog["stems"][0]
            self.assertEqual(stem["role"], "bass")
            self.assertEqual(stem["candidate_count"], 4)
            self.assertEqual(sum(item["primary"] for item in stem["candidates"]), 3)
            self.assertEqual(stem["candidates"][0]["process"], "sunofriend-specialist")
            self.assertIsNotNone(stem["candidates"][0]["preview"])

            public = public_catalog(catalog)
            rendered = json.dumps(public)
            self.assertNotIn(str(root), rendered)
            self.assertNotIn("source_path", rendered)
            self.assertNotIn("midi_path", rendered)

    def test_byte_identical_stems_keep_distinct_review_state_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "Duplicate Song-D minor-120bpm-440hz"
            project.mkdir()
            payload = b"RIFF-identical-silence"
            (project / "Duplicate Song-bass-D minor-120bpm-440hz.wav").write_bytes(
                payload
            )
            (project / "Duplicate Song-keys-D minor-120bpm-440hz.wav").write_bytes(
                payload
            )

            catalog = build_workbench_catalog(project)
            ids = {stem["stem_id"] for stem in catalog["stems"]}
            self.assertEqual(len(ids), 2)
            self.assertEqual({stem["role"] for stem in catalog["stems"]}, {"bass", "keys"})

    def test_automatic_discovery_rejects_symlinks_outside_explicit_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Symlink Song-D minor-120bpm-440hz"
            candidates = root / "candidates"
            outside = root / "outside"
            project.mkdir()
            candidates.mkdir()
            outside.mkdir()
            (project / "Symlink Song-bass-D minor-120bpm-440hz.wav").write_bytes(
                b"RIFF-source"
            )
            outside_midi = outside / "bass.mid"
            _write_midi(outside_midi, pitch=38)
            linked_midi = candidates / "bass.mid"
            linked_midi.symlink_to(outside_midi)

            with self.assertRaisesRegex(ValueError, "MIDI symlink escapes"):
                build_workbench_catalog(project, candidate_roots=[candidates])

            linked_midi.unlink()
            _write_midi(linked_midi, pitch=38)
            outside_preview = outside / "bass.preview.wav"
            outside_preview.write_bytes(b"RIFF-outside-preview")
            (candidates / "bass.preview.wav").symlink_to(outside_preview)
            with self.assertRaisesRegex(ValueError, "preview symlink escapes"):
                build_workbench_catalog(project, candidate_roots=[candidates])

    def test_explicit_catalog_requires_candidates_inside_named_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Song-E major-125bpm-440hz"
            candidate_root = root / "outputs"
            project.mkdir()
            candidate_root.mkdir()
            source = project / "Song-keys-E major-125bpm-440hz.wav"
            source.write_bytes(b"RIFF-source")
            midi = candidate_root / "keys.mid"
            _write_midi(midi, pitch=64)
            preview = candidate_root / "keys.wav"
            preview.write_bytes(b"RIFF-preview")
            document = root / "catalog.json"
            document.write_text(
                json.dumps(
                    {
                        "schema": "sunofriend.workbench-catalog.v1",
                        "stems": [
                            {
                                "source": str(source),
                                "role": "keys",
                                "candidates": [
                                    {
                                        "midi": str(midi),
                                        "preview": str(preview),
                                        "label": "Neutral keys candidate",
                                        "process": "test-process",
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "outside the explicit local"):
                build_workbench_catalog(project, catalog_path=document)

            catalog = build_workbench_catalog(
                project,
                candidate_roots=[candidate_root],
                catalog_path=document,
            )
            self.assertEqual(
                catalog["stems"][0]["candidates"][0]["label"],
                "Neutral keys candidate",
            )

    def test_ai_run_diagnostics_are_path_free_and_block_only_severe_bursts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "AI Song-B minor-119bpm-440hz"
            run_dir = root / "bass-muscriptor" / "run"
            project.mkdir()
            run_dir.mkdir(parents=True)
            source = project / "AI Song-bass-B minor-119bpm-440hz.wav"
            source.write_bytes(b"RIFF-private-source")
            checkpoint = root / "model.safetensors"
            checkpoint.write_bytes(b"checkpoint")
            config = root / "config.json"
            config.write_text(
                '{"model_type":"muscriptor","variant":"small"}',
                encoding="utf-8",
            )
            worker = root / "worker.py"
            worker.write_text("# pinned worker\n", encoding="utf-8")
            checkpoint_hash = _record(checkpoint)["sha256"]
            config_hash = _record(config)["sha256"]
            midi = run_dir / "candidate.mid"
            _write_midi(midi, pitch=40)
            request = {
                "schema": "sunofriend.ai-transcription-request.v1",
                "audio_path": str(source.resolve()),
                "backend": "muscriptor",
                "roles": [],
                "start_seconds": 0.0,
                "end_seconds": 15.0,
                "options": {
                    "model_sha256": checkpoint_hash,
                    "model_config_sha256": config_hash,
                },
            }
            notes = [
                {
                    "start_seconds": 8.54,
                    "end_seconds": 8.55,
                    "pitch": 36.0,
                    "confidence": None,
                    "instrument": "drums",
                    "velocity": None,
                    "source_event_id": str(index),
                }
                for index in range(80)
            ]
            candidate = {
                "schema": "sunofriend.ai-transcription-candidate.v1",
                "backend": "muscriptor",
                "model_version": "muscriptor-test-small",
                "notes": notes,
                "warnings": [],
                "raw_artifacts": [],
                "metadata": {
                    "checkpoint_sha256": checkpoint_hash,
                    "excerpt": {"duration_seconds": 15.0},
                },
            }
            (run_dir / "request.json").write_text(
                json.dumps(request), encoding="utf-8"
            )
            (run_dir / "candidate.json").write_text(
                json.dumps(candidate), encoding="utf-8"
            )
            (run_dir / "candidate.raw.json").write_text(
                json.dumps(candidate), encoding="utf-8"
            )
            # Deliberately benign stored metrics prove the Workbench recomputes
            # its safety gate from the verified candidate instead of trusting it.
            (run_dir / "candidate.quality.json").write_text(
                json.dumps(
                    {
                        "schema": "sunofriend.ai-candidate-quality.v1",
                        "status": "pass",
                        "promotion_allowed": True,
                        "metrics": {"note_count": len(notes)},
                        "warnings": [],
                    }
                ),
                encoding="utf-8",
            )
            artifacts = {
                name: _record(run_dir / name, relative=True)
                for name in (
                    "request.json",
                    "candidate.raw.json",
                    "candidate.json",
                    "candidate.quality.json",
                    "candidate.mid",
                )
            }
            execution = {"model_config_sha256": config_hash, "model_size": "small"}
            (run_dir / "run.json").write_text(
                json.dumps(
                    {
                        "schema": "sunofriend.ai-bakeoff-run.v1",
                        "status": "complete",
                        "run_id": "severe-fixture",
                        "backend": "muscriptor",
                        "elapsed_seconds": 2.5,
                        "note_count": len(notes),
                        "source": _record(source),
                        "worker": _record(worker),
                        "request": request,
                        "execution": execution,
                        "checkpoint": {
                            **_record(checkpoint),
                            "variant": "small",
                            "config": _record(config),
                        },
                        "artifacts": artifacts,
                    }
                ),
                encoding="utf-8",
            )

            catalog = build_workbench_catalog(project, candidate_roots=[run_dir.parent])
            discovered = catalog["stems"][0]["candidates"][0]
            self.assertTrue(discovered["audition_blocked"])
            self.assertTrue(discovered["diagnostic_only"])
            self.assertIn(
                "extreme-onset-burst", discovered["ai_diagnostics"]["severe_codes"]
            )
            self.assertFalse(discovered["ai_diagnostics"]["audition_safe"])
            rendered = json.dumps(public_catalog(catalog))
            self.assertNotIn(str(root), rendered)
            self.assertIn(
                "AI transcription diagnostics",
                Path("src/sunofriend/workbench.html").read_text(encoding="utf-8"),
            )

            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            stem = catalog["stems"][0]
            with self.assertRaisesRegex(ValueError, "diagnostic-only"):
                store.append(
                    catalog,
                    {
                        "event_type": "candidate_decision",
                        "stem_id": stem["stem_id"],
                        "candidate_id": discovered["candidate_id"],
                        "decision": "main",
                        "context": "solo",
                        "problem_tags": [],
                    },
                )

            legacy_state = {
                "stems": {
                    stem["stem_id"]: {
                        "main_candidate_id": discovered["candidate_id"],
                        "candidates": {
                            discovered["candidate_id"]: {"decision": "main"}
                        },
                    }
                }
            }
            workbench_artifacts = WorkbenchArtifacts(root / "state" / "artifacts")
            with self.assertRaisesRegex(ValueError, "diagnostic-only"):
                workbench_artifacts.render_arrangement(catalog, legacy_state)

            run_path = run_dir / "run.json"
            run_document = json.loads(run_path.read_text(encoding="utf-8"))
            del run_document["artifacts"]["candidate.json"]
            run_path.write_text(json.dumps(run_document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not pin candidate.json"):
                build_workbench_catalog(project, candidate_roots=[run_dir.parent])


class WorkbenchStoreTests(unittest.TestCase):
    def test_events_are_append_only_restore_state_and_redact_contribution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _small_catalog(root)
            database = root / "state" / "workbench.sqlite3"
            store = WorkbenchStore(database)
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            first = store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "main",
                    "context": "solo",
                    "problem_tags": ["missing_notes"],
                    "notes": "private note that must not be contributed",
                },
            )

            reopened = WorkbenchStore(database)
            state = reopened.current_state(catalog)
            saved = state["stems"][stem["stem_id"]]["candidates"][
                candidate["candidate_id"]
            ]
            self.assertEqual(saved["decision"], "main")
            self.assertEqual(
                state["stems"][stem["stem_id"]]["main_candidate_id"],
                candidate["candidate_id"],
            )
            self.assertEqual(state["event_count"], 1)

            reopened.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "needs_correction",
                    "context": "full_mix",
                    "problem_tags": ["wrong_pitch_or_octave"],
                    "notes": "second private note",
                },
            )
            events = reopened.events(catalog["project_id"])
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["event_id"], first["event_id"])
            self.assertEqual(events[0]["payload"]["decision"], "main")
            latest = reopened.current_state(catalog)["stems"][stem["stem_id"]]
            self.assertEqual(
                latest["candidates"][candidate["candidate_id"]]["decision"],
                "needs_correction",
            )
            self.assertIsNone(latest["main_candidate_id"])

            review = reopened.export_review(catalog)
            preview = json.dumps(review["contribution_preview"])
            self.assertNotIn(str(root), preview)
            self.assertNotIn("private note", preview)
            self.assertFalse(review["contribution_preview"]["submission_enabled"])
            self.assertEqual(
                review["contribution_preview"]["decision_event_count"], 2
            )


class WorkbenchServerTests(unittest.TestCase):
    def test_loopback_token_range_and_decision_api(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _small_catalog(root)
            server = create_workbench_server(
                catalog,
                state_dir=root / "state",
                token="test-token",
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=5
                )
                connection.request("GET", "/api/project?token=wrong")
                self.assertEqual(connection.getresponse().status, 403)
                connection.close()

                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=5
                )
                connection.request("GET", "/?token=test-token")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                page = response.read().decode("utf-8")
                self.assertIn("Synchronized source / candidate switcher", page)
                self.assertIn("Build GarageBand handoff", page)
                connection.close()

                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=5
                )
                connection.request("GET", "/api/project?token=test-token")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                payload = json.loads(response.read())
                stem = payload["stems"][0]
                candidate = stem["candidates"][0]
                connection.close()

                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=5
                )
                connection.request(
                    "GET",
                    stem["source_url"],
                    headers={"Range": "bytes=0-3"},
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 206)
                self.assertEqual(response.read(), b"RIFF")
                connection.close()

                Path(catalog["stems"][0]["source_path"]).write_bytes(
                    b"RIFF-source-edited-after-launch"
                )
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=5
                )
                connection.request("GET", stem["source_url"])
                response = connection.getresponse()
                self.assertEqual(response.status, 409)
                self.assertIn("changed after it was catalogued", response.read().decode())
                connection.close()

                body = json.dumps(
                    {
                        "event_type": "candidate_decision",
                        "stem_id": stem["stem_id"],
                        "candidate_id": candidate["candidate_id"],
                        "decision": "optional",
                        "context": "solo",
                        "problem_tags": [],
                    }
                )
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_port, timeout=5
                )
                connection.request(
                    "POST",
                    "/api/events?token=test-token",
                    body=body,
                    headers={"Content-Type": "application/json"},
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 201)
                saved = json.loads(response.read())
                self.assertEqual(
                    saved["state"]["stems"][stem["stem_id"]]["candidates"][
                        candidate["candidate_id"]
                    ]["decision"],
                    "optional",
                )
                connection.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


class WorkbenchArtifactTests(unittest.TestCase):
    def test_catalogued_midi_drift_blocks_preview_and_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _small_catalog(root)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"test-soundfont")
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": stem["stem_id"],
                    "candidate_id": candidate["candidate_id"],
                    "decision": "main",
                    "context": "solo",
                    "problem_tags": [],
                },
            )
            midi = Path(candidate["midi_path"])
            midi.write_bytes(midi.read_bytes() + b"changed")
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )

            with self.assertRaisesRegex(ValueError, "changed after it was catalogued"):
                artifacts.render_candidate_preview(
                    catalog, stem["stem_id"], candidate["candidate_id"]
                )
            with self.assertRaisesRegex(ValueError, "changed after it was catalogued"):
                artifacts.build_garageband_handoff(
                    catalog, store.current_state(catalog)
                )

    def test_neutral_preview_is_cached_and_never_changes_original_midi(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _small_catalog(root)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"test-soundfont")
            stem = catalog["stems"][0]
            candidate = stem["candidates"][0]
            original = Path(candidate["midi_path"]).read_bytes()
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )

            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_fake_render,
            ) as renderer:
                first = artifacts.render_candidate_preview(
                    catalog, stem["stem_id"], candidate["candidate_id"]
                )
                second = artifacts.render_candidate_preview(
                    catalog, stem["stem_id"], candidate["candidate_id"]
                )

            self.assertEqual(renderer.call_count, 1)
            self.assertFalse(first["cache_hit"])
            self.assertTrue(second["cache_hit"])
            self.assertEqual(first["preview"]["sha256"], second["preview"]["sha256"])
            self.assertEqual(Path(candidate["midi_path"]).read_bytes(), original)
            cached = artifacts.cached_candidate_preview(
                catalog, stem["stem_id"], candidate["candidate_id"]
            )
            self.assertIsNotNone(cached)
            self.assertEqual(cached["policy"], "role-neutral-general-midi-v1")
            different_soundfont = root / "different.sf2"
            different_soundfont.write_bytes(b"different-test-soundfont")
            other_renderer = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=different_soundfont
            )
            self.assertIsNone(
                other_renderer.cached_candidate_preview(
                    catalog, stem["stem_id"], candidate["candidate_id"]
                )
            )
            Path(second["preview"]["path"]).write_bytes(b"corrupt-cache")
            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_fake_render,
            ) as recovery_renderer:
                recovered = artifacts.render_candidate_preview(
                    catalog, stem["stem_id"], candidate["candidate_id"]
                )
            self.assertEqual(recovery_renderer.call_count, 1)
            self.assertFalse(recovered["cache_hit"])
            self.assertEqual(recovered["preview"]["bytes"], 2052)

            soundfont.write_bytes(b"changed-soundfont")
            with self.assertRaisesRegex(ValueError, "SoundFont changed"):
                artifacts.cached_candidate_preview(
                    catalog, stem["stem_id"], candidate["candidate_id"]
                )
            with self.assertRaisesRegex(ValueError, "SoundFont changed"):
                artifacts.render_candidate_preview(
                    catalog, stem["stem_id"], candidate["candidate_id"]
                )

    def test_arrangement_and_handoff_include_only_explicit_usable_choices(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = _multi_stem_catalog(root)
            soundfont = root / "test.sf2"
            soundfont.write_bytes(b"test-soundfont")
            store = WorkbenchStore(root / "state" / "workbench.sqlite3")
            bass_stem = next(stem for stem in catalog["stems"] if stem["role"] == "bass")
            keys_stem = next(stem for stem in catalog["stems"] if stem["role"] == "keys")
            bass = bass_stem["candidates"][0]
            keys_optional = keys_stem["candidates"][0]
            keys_rejected = keys_stem["candidates"][1]
            store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": bass_stem["stem_id"],
                    "candidate_id": bass["candidate_id"],
                    "decision": "main",
                    "context": "solo",
                    "problem_tags": [],
                    "notes": "private bass note",
                },
            )
            store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": keys_stem["stem_id"],
                    "candidate_id": keys_optional["candidate_id"],
                    "decision": "optional",
                    "context": "full_mix",
                    "problem_tags": [],
                },
            )
            store.append(
                catalog,
                {
                    "event_type": "candidate_decision",
                    "stem_id": keys_stem["stem_id"],
                    "candidate_id": keys_rejected["candidate_id"],
                    "decision": "reject",
                    "context": "full_mix",
                    "problem_tags": ["extra_notes"],
                    "notes": "private rejected note",
                },
            )
            artifacts = WorkbenchArtifacts(
                root / "state" / "artifacts", soundfont_path=soundfont
            )
            current = store.current_state(catalog)

            with patch(
                "sunofriend.workbench_artifacts.render_midi_to_wav",
                side_effect=_fake_render,
            ) as renderer:
                arrangement = artifacts.render_arrangement(catalog, current)
                handoff = artifacts.build_garageband_handoff(catalog, current)
                repeated = artifacts.build_garageband_handoff(catalog, current)

            self.assertEqual(renderer.call_count, 1)
            self.assertEqual(arrangement["track_count"], 2)
            self.assertEqual(len(arrangement["selection"]), 2)
            self.assertTrue(repeated["cache_hit"])
            with zipfile.ZipFile(handoff["zip"]["path"]) as archive:
                names = set(archive.namelist())
                self.assertIn("MIDI/01-bass-main.mid", names)
                self.assertIn("MIDI/02-keys-optional.mid", names)
                self.assertNotIn("MIDI/03-keys-reject.mid", names)
                self.assertEqual(
                    archive.read("MIDI/01-bass-main.mid"),
                    Path(bass["midi_path"]).read_bytes(),
                )
                self.assertEqual(
                    archive.read("MIDI/02-keys-optional.mid"),
                    Path(keys_optional["midi_path"]).read_bytes(),
                )
                manifest = archive.read(
                    "sunofriend-garageband-handoff.json"
                ).decode("utf-8")
                self.assertNotIn(str(root), manifest)
                self.assertNotIn("private bass note", manifest)
                self.assertNotIn("private rejected note", manifest)
                self.assertIn('"original_midi_mutated": false', manifest)


def _small_catalog(root: Path) -> dict:
    project = root / "Small Song-D minor-120bpm-440hz"
    candidates = root / "candidates"
    project.mkdir()
    candidates.mkdir()
    (project / "Small Song-bass-D minor-120bpm-440hz.wav").write_bytes(
        b"RIFF-source-audio"
    )
    midi = candidates / "bass_listened.mid"
    _write_midi(midi, pitch=38)
    midi.with_suffix(".preview.wav").write_bytes(b"RIFF-preview-audio")
    return build_workbench_catalog(project, candidate_roots=[candidates])


def _write_midi(path: Path, *, pitch: int) -> None:
    write_midi_file(
        path,
        [
            MidiTrack(
                name="Bass",
                channel=0,
                program=38,
                notes=[NoteEvent(start=0.0, end=0.5, pitch=pitch, velocity=90)],
            )
        ],
        bpm=120.0,
    )


def _multi_stem_catalog(root: Path) -> dict:
    project = root / "Multi Song-D minor-120bpm-440hz"
    candidates = root / "candidates"
    project.mkdir()
    candidates.mkdir()
    (project / "Multi Song-bass-D minor-120bpm-440hz.wav").write_bytes(
        b"RIFF-bass-source"
    )
    (project / "Multi Song-keys-D minor-120bpm-440hz.wav").write_bytes(
        b"RIFF-keys-source"
    )
    _write_midi(candidates / "bass_listened.mid", pitch=38)
    _write_midi(candidates / "keys_listened.mid", pitch=60)
    _write_midi(candidates / "keys_cleanup.mid", pitch=64)
    return build_workbench_catalog(project, candidate_roots=[candidates])


def _fake_render(midi_path, wav_path, **_kwargs):
    del midi_path
    destination = Path(wav_path)
    destination.write_bytes(b"RIFF" + b"\0" * 2048)
    return destination


def _record(path: Path, *, relative: bool = False) -> dict:
    return {
        "path": path.name if relative else str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


if __name__ == "__main__":
    unittest.main()
