from __future__ import annotations

import json
import hashlib
import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from sunofriend.clip import (
    ClipNote,
    Instrument,
    MidiNoteLimitError,
    MidiClip,
    TempoMap,
    TempoPoint,
    TimeSignature,
    read_midi_clips,
    write_clip_midi,
)
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.workbench_catalog import build_workbench_catalog
from sunofriend.workbench_artifacts import selected_candidates
from sunofriend.workbench_timeline import (
    build_arrangement_timeline,
    build_stem_timeline,
)


class WorkbenchTimelineTests(unittest.TestCase):
    def test_pcm_waveform_and_multiple_midi_methods_are_path_free_and_deterministic(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _timeline_fixture(root)
            catalog = build_workbench_catalog(
                project, candidate_roots=[candidates]
            )
            stem = catalog["stems"][0]

            first = build_stem_timeline(
                catalog, stem["stem_id"], waveform_bins=64
            )
            second = build_stem_timeline(
                catalog, stem["stem_id"], waveform_bins=64
            )

            self.assertEqual(first, second)
            self.assertEqual(first["schema"], "sunofriend.workbench-timeline.v1")
            expected_hash_document = dict(first)
            expected_hash = expected_hash_document.pop("timeline_sha256")
            canonical = json.dumps(
                expected_hash_document,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
            self.assertEqual(expected_hash, hashlib.sha256(canonical).hexdigest())
            self.assertEqual(first["source"]["status"], "available")
            self.assertEqual(first["source"]["bin_count"], 64)
            self.assertEqual(first["source"]["sample_rate"], 8000)
            self.assertEqual(first["source"]["channels"], 1)
            self.assertAlmostEqual(first["source"]["duration_seconds"], 2.0)
            self.assertEqual(len(first["source"]["peaks"]), 64)
            self.assertTrue(
                all(
                    -1.0 <= minimum <= maximum <= 1.0
                    for minimum, maximum in first["source"]["peaks"]
                )
            )

            self.assertEqual(len(first["candidates"]), 2)
            by_pitch = {
                lane["tracks"][0]["notes"][0]["pitch"]: lane
                for lane in first["candidates"]
            }
            self.assertEqual(set(by_pitch), {38, 50})
            for lane in by_pitch.values():
                self.assertEqual(lane["status"], "available")
                self.assertEqual(lane["note_count"], 2)
                self.assertEqual(lane["track_count"], 2)
                self.assertEqual(lane["display_mode"], "piano-roll")
                self.assertEqual(lane["note_representation"], "note-on-off-only")
                self.assertEqual(lane["source_relationship"], "catalog-association-only")
                self.assertEqual(lane["tempo_points"], [{"beat": 0.0, "bpm": 120.0}])
                self.assertEqual(
                    lane["time_signature"], {"numerator": 4, "denominator": 4}
                )
                self.assertEqual(
                    {track["channel"] for track in lane["tracks"]}, {0, 1}
                )
                self.assertEqual(
                    {
                        note["velocity"]
                        for track in lane["tracks"]
                        for note in track["notes"]
                    },
                    {72, 96},
                )
                self.assertEqual(
                    {track["title"] for track in lane["tracks"]},
                    {"Bass body", "Bass detail"},
                )

            rendered = json.dumps(first, sort_keys=True)
            self.assertNotIn(str(root), rendered)
            self.assertNotIn("path", rendered)
            self.assertEqual(
                first["policies"]["candidate_order"], "catalog-order-unchanged"
            )
            self.assertIn("note-on/off", first["policies"]["midi_expression"])
            self.assertEqual(
                first["candidate_scope"],
                {
                    "mode": "primary-default",
                    "source_projection": "included",
                    "available_candidate_count": 2,
                    "returned_candidate_count": 2,
                },
            )
            self.assertEqual(
                first["effects"],
                {
                    "source_audio_mutated": False,
                    "source_midi_mutated": False,
                    "midi_created": False,
                    "candidate_order_changed": False,
                    "automatic_selection": False,
                    "automatic_ranking": False,
                    "default_selection_changed": False,
                },
            )

    def test_invalid_pcm_waveform_remains_an_explicit_unavailable_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Invalid Wave-D minor-120bpm-440hz"
            candidates = root / "candidates"
            project.mkdir()
            candidates.mkdir()
            (project / "Invalid Wave-bass-D minor-120bpm-440hz.wav").write_bytes(
                b"RIFF-not-a-complete-wave"
            )
            _write_candidate(candidates / "bass_specialist.mid", root_pitch=38)
            catalog = build_workbench_catalog(
                project, candidate_roots=[candidates]
            )

            timeline = build_stem_timeline(
                catalog, catalog["stems"][0]["stem_id"]
            )

            self.assertEqual(timeline["source"]["status"], "unavailable")
            self.assertEqual(
                timeline["source"]["reason_code"],
                "unsupported-or-invalid-pcm-wav",
            )
            self.assertEqual(timeline["source"]["peaks"], [])
            self.assertEqual(timeline["candidates"][0]["status"], "available")
            self.assertGreater(timeline["duration_seconds"], 0.0)

    def test_truncated_pcm_data_is_not_reported_as_a_valid_waveform(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Truncated Wave-D minor-120bpm-440hz"
            candidates = root / "candidates"
            project.mkdir()
            candidates.mkdir()
            source = project / "Truncated Wave-bass-D minor-120bpm-440hz.wav"
            _write_pcm_wav(source)
            source.write_bytes(source.read_bytes()[:-128])
            _write_candidate(candidates / "bass_specialist.mid", root_pitch=38)
            catalog = build_workbench_catalog(
                project, candidate_roots=[candidates]
            )

            timeline = build_stem_timeline(
                catalog, catalog["stems"][0]["stem_id"]
            )

            self.assertEqual(timeline["source"]["status"], "unavailable")
            self.assertEqual(
                timeline["source"]["reason_code"], "truncated-pcm-data"
            )
            self.assertEqual(timeline["source"]["peaks"], [])

    def test_invalid_midi_is_retained_as_unavailable_without_hiding_other_lanes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Invalid MIDI-D minor-120bpm-440hz"
            candidates = root / "candidates"
            project.mkdir()
            candidates.mkdir()
            _write_pcm_wav(
                project / "Invalid MIDI-bass-D minor-120bpm-440hz.wav"
            )
            (candidates / "bass_broken.mid").write_bytes(b"not-midi")
            _write_candidate(candidates / "bass_specialist.mid", root_pitch=38)
            catalog = build_workbench_catalog(
                project, candidate_roots=[candidates]
            )

            timeline = build_stem_timeline(
                catalog, catalog["stems"][0]["stem_id"]
            )

            statuses = {lane["status"] for lane in timeline["candidates"]}
            self.assertEqual(statuses, {"available", "unavailable"})
            broken = next(
                lane for lane in timeline["candidates"] if lane["status"] == "unavailable"
            )
            self.assertEqual(broken["reason_code"], "unsupported-or-invalid-midi")
            self.assertIsNone(broken["note_count"])
            self.assertEqual(broken["tracks"], [])

    def test_note_free_midi_is_retained_as_an_explicit_empty_lane(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Empty MIDI-D minor-120bpm-440hz"
            candidates = root / "candidates"
            project.mkdir()
            candidates.mkdir()
            _write_pcm_wav(project / "Empty MIDI-bass-D minor-120bpm-440hz.wav")
            write_midi_file(
                candidates / "bass_empty.mid",
                [MidiTrack("Empty bass", 0, 33, [])],
                bpm=120.0,
            )
            catalog = build_workbench_catalog(project, candidate_roots=[candidates])

            timeline = build_stem_timeline(
                catalog, catalog["stems"][0]["stem_id"]
            )
            lane = timeline["candidates"][0]

            self.assertEqual(lane["status"], "empty")
            self.assertEqual(lane["reason_code"], "no-note-events")
            self.assertEqual(lane["display_mode"], "piano-roll")
            self.assertEqual(lane["tracks"], [])

    def test_default_scope_is_primary_only_and_advanced_is_loaded_explicitly(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Bounded Song-D minor-120bpm-440hz"
            candidates = root / "candidates"
            project.mkdir()
            candidates.mkdir()
            _write_pcm_wav(project / "Bounded Song-bass-D minor-120bpm-440hz.wav")
            for index in range(5):
                _write_candidate(
                    candidates / f"bass_method_{index}.mid",
                    root_pitch=36 + index,
                )
            catalog = build_workbench_catalog(project, candidate_roots=[candidates])
            stem = catalog["stems"][0]

            default = build_stem_timeline(catalog, stem["stem_id"])
            advanced = next(
                candidate for candidate in stem["candidates"] if not candidate["primary"]
            )
            explicit = build_stem_timeline(
                catalog,
                stem["stem_id"],
                candidate_ids=[advanced["candidate_id"]],
            )

            self.assertEqual(len(default["candidates"]), 3)
            self.assertTrue(all(lane["primary"] for lane in default["candidates"]))
            self.assertEqual(default["candidate_scope"]["available_candidate_count"], 5)
            self.assertEqual(explicit["candidate_scope"]["mode"], "explicit")
            self.assertEqual(
                [lane["candidate_id"] for lane in explicit["candidates"]],
                [advanced["candidate_id"]],
            )

    def test_candidate_only_expansion_does_not_rebuild_source_waveform(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _timeline_fixture(root)
            catalog = build_workbench_catalog(project, candidate_roots=[candidates])
            stem = catalog["stems"][0]
            candidate_id = stem["candidates"][0]["candidate_id"]

            with patch("sunofriend.workbench_timeline._source_timeline") as source:
                timeline = build_stem_timeline(
                    catalog,
                    stem["stem_id"],
                    candidate_ids=[candidate_id],
                    include_source=False,
                )

            source.assert_not_called()
            self.assertEqual(timeline["source"]["status"], "reference-only")
            self.assertEqual(
                timeline["source"]["reason_code"],
                "source-projection-not-requested",
            )
            self.assertEqual(
                timeline["candidate_scope"]["source_projection"],
                "reference-only",
            )

    def test_variable_tempo_uses_embedded_tempo_map_for_note_seconds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Tempo Song-D minor-120bpm-440hz"
            candidates = root / "candidates"
            project.mkdir()
            candidates.mkdir()
            _write_pcm_wav(project / "Tempo Song-bass-D minor-120bpm-440hz.wav")
            tempo_map = TempoMap(
                (TempoPoint(0.0, 120.0), TempoPoint(4.0, 60.0))
            )
            clip = MidiClip(
                title="Variable tempo bass",
                tempo_map=tempo_map,
                time_signature=TimeSignature(4, 4),
                instrument=Instrument("bass", 33, 0),
                notes=(ClipNote.from_beats(5.0, 0.5, 45, 90, tempo_map),),
            )
            write_clip_midi(candidates / "bass_variable_tempo.mid", clip)
            catalog = build_workbench_catalog(project, candidate_roots=[candidates])

            timeline = build_stem_timeline(
                catalog, catalog["stems"][0]["stem_id"]
            )
            lane = timeline["candidates"][0]
            note = lane["tracks"][0]["notes"][0]

            self.assertEqual(
                lane["tempo_points"],
                [{"beat": 0.0, "bpm": 120.0}, {"beat": 4.0, "bpm": 60.0}],
            )
            self.assertAlmostEqual(note["start_seconds"], 3.0)
            self.assertAlmostEqual(note["end_seconds"], 3.5)

    def test_drum_track_uses_drum_grid_and_preserves_midi_pitch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Drum Song-D minor-120bpm-440hz"
            candidates = root / "candidates"
            project.mkdir()
            candidates.mkdir()
            _write_pcm_wav(project / "Drum Song-kick-D minor-120bpm-440hz.wav")
            write_midi_file(
                candidates / "kick_specialist.mid",
                [
                    MidiTrack(
                        "Kick family",
                        9,
                        0,
                        [NoteEvent(start=0.0, end=0.1, pitch=36, velocity=110)],
                    )
                ],
                bpm=120.0,
            )
            catalog = build_workbench_catalog(project, candidate_roots=[candidates])

            timeline = build_stem_timeline(
                catalog, catalog["stems"][0]["stem_id"]
            )
            lane = timeline["candidates"][0]
            track = lane["tracks"][0]

            self.assertEqual(lane["display_mode"], "drum-grid")
            self.assertEqual(track["display_mode"], "drum-grid")
            self.assertEqual(track["channel"], 9)
            self.assertEqual(track["notes"][0]["pitch"], 36)

    def test_non_wav_source_is_explicitly_unavailable_without_hiding_midi(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "FLAC Song-D minor-120bpm-440hz"
            candidates = root / "candidates"
            project.mkdir()
            candidates.mkdir()
            (project / "FLAC Song-bass-D minor-120bpm-440hz.flac").write_bytes(
                b"fLaC-placeholder"
            )
            _write_candidate(candidates / "bass_specialist.mid", root_pitch=38)
            catalog = build_workbench_catalog(project, candidate_roots=[candidates])

            timeline = build_stem_timeline(
                catalog, catalog["stems"][0]["stem_id"]
            )

            self.assertEqual(timeline["source"]["status"], "unavailable")
            self.assertEqual(
                timeline["source"]["reason_code"], "unsupported-audio-container"
            )
            self.assertEqual(timeline["candidates"][0]["status"], "available")

    def test_stereo_24_bit_waveform_geometry_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "PCM Song-D minor-120bpm-440hz"
            candidates = root / "candidates"
            project.mkdir()
            candidates.mkdir()
            _write_pcm_wav_24_stereo(
                project / "PCM Song-bass-D minor-120bpm-440hz.wav"
            )
            _write_candidate(candidates / "bass_specialist.mid", root_pitch=38)
            catalog = build_workbench_catalog(project, candidate_roots=[candidates])

            timeline = build_stem_timeline(
                catalog, catalog["stems"][0]["stem_id"], waveform_bins=64
            )

            self.assertEqual(timeline["source"]["status"], "available")
            self.assertEqual(timeline["source"]["channels"], 2)
            self.assertEqual(timeline["source"]["sample_width_bits"], 24)
            self.assertEqual(len(timeline["source"]["peaks"]), 64)

    def test_note_limit_is_explicit_and_does_not_silently_truncate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _timeline_fixture(root)
            catalog = build_workbench_catalog(project, candidate_roots=[candidates])

            with patch("sunofriend.workbench_timeline.MAX_TIMELINE_NOTES", 1):
                timeline = build_stem_timeline(
                    catalog, catalog["stems"][0]["stem_id"]
                )

            for lane in timeline["candidates"]:
                self.assertEqual(lane["status"], "unavailable")
                self.assertEqual(
                    lane["reason_code"], "note-count-exceeds-visual-limit"
                )
                self.assertEqual(lane["note_count"], 2)
                self.assertTrue(lane["note_count_is_lower_bound"])
                self.assertEqual(lane["tracks"], [])

            candidate_path = Path(
                catalog["stems"][0]["candidates"][0]["midi_path"]
            )
            with self.assertRaises(MidiNoteLimitError):
                read_midi_clips(candidate_path, max_notes=1)

    def test_midi_byte_limit_is_checked_before_note_materialisation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _timeline_fixture(root)
            catalog = build_workbench_catalog(project, candidate_roots=[candidates])

            with patch(
                "sunofriend.workbench_timeline.MAX_TIMELINE_MIDI_BYTES", 1
            ):
                with patch(
                    "sunofriend.workbench_timeline.read_midi_clips"
                ) as reader:
                    timeline = build_stem_timeline(
                        catalog, catalog["stems"][0]["stem_id"]
                    )

            reader.assert_not_called()
            for lane in timeline["candidates"]:
                self.assertEqual(lane["status"], "unavailable")
                self.assertEqual(
                    lane["reason_code"], "midi-file-exceeds-visual-limit"
                )
                self.assertIsNone(lane["note_count"])
                self.assertEqual(lane["tracks"], [])

    def test_midi_note_budget_stops_compact_unmatched_running_status_events(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "dense-running-status.mid"
            track = (
                b"\x00\x90\x3c\x40"
                + b"\x00\x3d\x40"
                + b"\x00\x3e\x40"
                + b"\x00\x3f\x40"
                + b"\x00\xff\x2f\x00"
            )
            path.write_bytes(
                b"MThd"
                + struct.pack(">IHHH", 6, 0, 1, 480)
                + b"MTrk"
                + struct.pack(">I", len(track))
                + track
            )

            with self.assertRaises(MidiNoteLimitError) as raised:
                read_midi_clips(path, max_notes=2)

            self.assertEqual(raised.exception.minimum_count, 3)

    def test_input_mutation_after_catalogue_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _timeline_fixture(root)
            catalog = build_workbench_catalog(
                project, candidate_roots=[candidates]
            )
            stem = catalog["stems"][0]
            candidate_path = Path(stem["candidates"][0]["midi_path"])
            candidate_path.write_bytes(candidate_path.read_bytes() + b"changed")

            with self.assertRaisesRegex(
                ValueError, "candidate MIDI changed after it was catalogued"
            ):
                build_stem_timeline(catalog, stem["stem_id"])

    def test_arrangement_timeline_is_path_free_and_context_neutral(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _arrangement_fixture(root)
            catalog = build_workbench_catalog(project, candidate_roots=[candidates])
            solo_state = _selected_state(catalog, context="solo")
            full_mix_state = _selected_state(catalog, context="full_mix")

            solo = build_arrangement_timeline(
                catalog, selected_candidates(catalog, solo_state)
            )
            full_mix = build_arrangement_timeline(
                catalog, selected_candidates(catalog, full_mix_state)
            )

            self.assertEqual(solo, full_mix)
            self.assertEqual(
                solo["schema"],
                "sunofriend.workbench-arrangement-timeline.v1",
            )
            self.assertEqual(solo["source_lane_count"], 2)
            self.assertEqual(solo["selected_midi_lane_count"], 2)
            self.assertEqual(solo["rendered_note_count"], 4)
            self.assertEqual(
                {lane["role"] for lane in solo["midi_lanes"]}, {"bass", "keys"}
            )
            self.assertEqual(
                {lane["decision"] for lane in solo["midi_lanes"]}, {"main"}
            )
            self.assertNotIn("decision_context", json.dumps(solo))
            self.assertNotIn(str(root), json.dumps(solo))
            expected_document = dict(solo)
            expected_hash = expected_document.pop("timeline_sha256")
            canonical = json.dumps(
                expected_document,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
            self.assertEqual(expected_hash, hashlib.sha256(canonical).hexdigest())
            self.assertFalse(solo["effects"]["feedback_recorded"])
            self.assertFalse(solo["effects"]["selection_changed"])

            role_state = json.loads(json.dumps(solo_state))
            role_state["stems"][catalog["stems"][0]["stem_id"]]["role"] = (
                "bass body"
            )
            role_changed = build_arrangement_timeline(
                catalog, selected_candidates(catalog, role_state)
            )
            decision_state = json.loads(json.dumps(solo_state))
            first_stem_state = decision_state["stems"][
                catalog["stems"][0]["stem_id"]
            ]
            first_candidate_id = first_stem_state["main_candidate_id"]
            first_stem_state["main_candidate_id"] = None
            first_stem_state["candidates"][first_candidate_id][
                "decision"
            ] = "optional"
            decision_changed = build_arrangement_timeline(
                catalog, selected_candidates(catalog, decision_state)
            )
            self.assertNotEqual(
                solo["selection_sha256"], role_changed["selection_sha256"]
            )
            self.assertNotEqual(
                solo["selection_sha256"], decision_changed["selection_sha256"]
            )

    def test_arrangement_projects_only_active_main_and_optional_choices(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _timeline_fixture(root)
            for index, name in enumerate(
                ("repair", "correction", "rejected", "unreviewed"), start=2
            ):
                _write_candidate(
                    candidates / f"bass_{name}.mid", root_pitch=38 + index * 5
                )
            catalog = build_workbench_catalog(
                project, candidate_roots=[candidates]
            )
            stem = catalog["stems"][0]
            rows = stem["candidates"]
            self.assertEqual(len(rows), 6)
            state = {
                "stems": {
                    stem["stem_id"]: {
                        "role": "bass",
                        "main_candidate_id": rows[1]["candidate_id"],
                        "candidates": {
                            rows[0]["candidate_id"]: {
                                "decision": "main",
                                "context": "solo",
                            },
                            rows[1]["candidate_id"]: {
                                "decision": "main",
                                "context": "solo",
                            },
                            rows[2]["candidate_id"]: {
                                "decision": "optional",
                                "context": "solo",
                            },
                            rows[3]["candidate_id"]: {
                                "decision": "needs_correction",
                                "context": "solo",
                            },
                            rows[4]["candidate_id"]: {
                                "decision": "reject",
                                "context": "solo",
                            },
                        },
                    }
                }
            }

            selection = selected_candidates(catalog, state)
            timeline = build_arrangement_timeline(catalog, selection)

            expected = {rows[1]["candidate_id"], rows[2]["candidate_id"]}
            self.assertEqual(
                {item["candidate_id"] for item in selection}, expected
            )
            self.assertEqual(
                {lane["candidate_id"] for lane in timeline["midi_lanes"]},
                expected,
            )
            self.assertEqual(
                {lane["decision"] for lane in timeline["midi_lanes"]},
                {"main", "optional"},
            )

    def test_arrangement_timeline_groups_duplicate_sources_not_selected_midi(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Shared Source-D minor-120bpm-440hz"
            candidates = root / "candidates"
            project.mkdir()
            candidates.mkdir()
            source = project / "Shared Source-mixed-D minor-120bpm-440hz.wav"
            _write_pcm_wav(source)
            bass = candidates / "bass-body.mid"
            pluck = candidates / "pluck-line.mid"
            _write_candidate(bass, root_pitch=38)
            _write_candidate(pluck, root_pitch=62)
            catalog_path = root / "catalog.json"
            catalog_path.write_text(
                json.dumps(
                    {
                        "schema": "sunofriend.workbench-catalog.v1",
                        "stems": [
                            {
                                "source": str(source),
                                "role": "bass body",
                                "candidates": [{"midi": str(bass)}],
                            },
                            {
                                "source": str(source),
                                "role": "pluck",
                                "candidates": [{"midi": str(pluck)}],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            catalog = build_workbench_catalog(
                project,
                candidate_roots=[candidates],
                catalog_path=catalog_path,
            )
            state = _selected_state(catalog, context="solo")

            timeline = build_arrangement_timeline(
                catalog, selected_candidates(catalog, state)
            )

            self.assertEqual(timeline["source_lane_count"], 1)
            self.assertEqual(timeline["selected_midi_lane_count"], 2)
            source_lane = timeline["sources"][0]
            self.assertEqual(source_lane["duplicate_catalog_source_count"], 2)
            self.assertEqual(set(source_lane["roles"]), {"bass body", "pluck"})
            self.assertEqual(len(source_lane["stem_ids"]), 2)
            self.assertEqual(len(timeline["midi_lanes"]), 2)

    def test_arrangement_timeline_enforces_aggregate_note_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _timeline_fixture(root)
            catalog = build_workbench_catalog(project, candidate_roots=[candidates])
            state = _selected_state(catalog, context="solo")

            with patch(
                "sunofriend.workbench_timeline.MAX_ARRANGEMENT_TIMELINE_NOTES",
                1,
            ):
                timeline = build_arrangement_timeline(
                    catalog, selected_candidates(catalog, state)
                )

            lane = timeline["midi_lanes"][0]
            self.assertEqual(lane["status"], "unavailable")
            self.assertEqual(
                lane["reason_code"],
                "note-count-exceeds-arrangement-visual-budget",
            )
            self.assertEqual(lane["note_count"], 2)
            self.assertTrue(lane["note_count_is_lower_bound"])
            self.assertEqual(timeline["rendered_note_count"], 0)

    def test_oversized_arrangement_lane_does_not_hide_later_small_lane(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Budget Song-D minor-120bpm-440hz"
            candidates = root / "budget-candidates"
            project.mkdir()
            candidates.mkdir()
            _write_pcm_wav(project / "Budget Song-bass-D minor-120bpm-440hz.wav")
            _write_pcm_wav(
                project / "Budget Song-keys-D minor-120bpm-440hz.wav",
                frequency=220.0,
            )
            _write_dense_candidate(
                candidates / "bass_specialist.mid", root_pitch=38, note_count=4
            )
            _write_dense_candidate(
                candidates / "keys_muscriptor.mid", root_pitch=60, note_count=1
            )
            catalog = build_workbench_catalog(
                project, candidate_roots=[candidates]
            )
            state = _selected_state(catalog, context="solo")

            with patch(
                "sunofriend.workbench_timeline.MAX_ARRANGEMENT_TIMELINE_NOTES",
                3,
            ):
                timeline = build_arrangement_timeline(
                    catalog, selected_candidates(catalog, state)
                )

            first, second = timeline["midi_lanes"]
            self.assertEqual(first["role"], "bass")
            self.assertEqual(first["status"], "unavailable")
            self.assertEqual(
                first["reason_code"],
                "note-count-exceeds-arrangement-visual-budget",
            )
            self.assertEqual(second["role"], "keys")
            self.assertEqual(second["status"], "available")
            self.assertEqual(second["note_count"], 1)
            self.assertEqual(timeline["rendered_note_count"], 1)

    def test_empty_arrangement_still_exposes_source_reference_lanes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _timeline_fixture(root)
            catalog = build_workbench_catalog(project, candidate_roots=[candidates])

            timeline = build_arrangement_timeline(catalog, [])

            self.assertEqual(timeline["source_lane_count"], 1)
            self.assertEqual(timeline["selected_midi_lane_count"], 0)
            self.assertEqual(timeline["midi_lanes"], [])
            self.assertEqual(timeline["selection"], [])
            self.assertEqual(timeline["sources"][0]["status"], "available")

    def test_unknown_stem_and_invalid_resolution_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, candidates = _timeline_fixture(root)
            catalog = build_workbench_catalog(
                project, candidate_roots=[candidates]
            )
            with self.assertRaisesRegex(ValueError, "unknown workbench stem_id"):
                build_stem_timeline(catalog, "missing")
            with self.assertRaisesRegex(ValueError, "between 64 and 4096"):
                build_stem_timeline(
                    catalog, catalog["stems"][0]["stem_id"], waveform_bins=8
                )
            candidate_id = catalog["stems"][0]["candidates"][0]["candidate_id"]
            with self.assertRaisesRegex(ValueError, "must be unique"):
                build_stem_timeline(
                    catalog,
                    catalog["stems"][0]["stem_id"],
                    candidate_ids=[candidate_id, candidate_id],
                )
            with self.assertRaisesRegex(ValueError, "unknown candidate_id"):
                build_stem_timeline(
                    catalog,
                    catalog["stems"][0]["stem_id"],
                    candidate_ids=["missing"],
                )


def _timeline_fixture(root: Path) -> tuple[Path, Path]:
    project = root / "Visual Song-D minor-120bpm-440hz"
    candidates = root / "candidates"
    project.mkdir()
    candidates.mkdir()
    _write_pcm_wav(project / "Visual Song-bass-D minor-120bpm-440hz.wav")
    _write_candidate(candidates / "bass_specialist.mid", root_pitch=38)
    _write_candidate(candidates / "bass_muscriptor.mid", root_pitch=50)
    return project, candidates


def _arrangement_fixture(root: Path) -> tuple[Path, Path]:
    project = root / "Arrangement Song-D minor-120bpm-440hz"
    candidates = root / "arrangement-candidates"
    project.mkdir()
    candidates.mkdir()
    _write_pcm_wav(project / "Arrangement Song-bass-D minor-120bpm-440hz.wav")
    _write_pcm_wav(
        project / "Arrangement Song-keys-D minor-120bpm-440hz.wav",
        frequency=220.0,
    )
    _write_candidate(candidates / "bass_specialist.mid", root_pitch=38)
    _write_candidate(candidates / "keys_muscriptor.mid", root_pitch=60)
    return project, candidates


def _selected_state(catalog: dict, *, context: str) -> dict:
    stems = {}
    for stem in catalog["stems"]:
        candidate = stem["candidates"][0]
        candidate_id = candidate["candidate_id"]
        stems[stem["stem_id"]] = {
            "role": stem["role"],
            "main_candidate_id": candidate_id,
            "candidates": {
                candidate_id: {
                    "decision": "main",
                    "context": context,
                }
            },
        }
    return {"stems": stems}


def _write_candidate(path: Path, *, root_pitch: int) -> None:
    write_midi_file(
        path,
        [
            MidiTrack(
                "Bass body",
                0,
                33,
                [
                    NoteEvent(
                        start=0.25,
                        end=0.75,
                        pitch=root_pitch,
                        velocity=96,
                    )
                ],
            ),
            MidiTrack(
                "Bass detail",
                1,
                38,
                [
                    NoteEvent(
                        start=1.0,
                        end=1.5,
                        pitch=root_pitch + 7,
                        velocity=72,
                    )
                ],
            ),
        ],
        bpm=120.0,
    )


def _write_dense_candidate(
    path: Path, *, root_pitch: int, note_count: int
) -> None:
    write_midi_file(
        path,
        [
            MidiTrack(
                "Dense line",
                0,
                0,
                [
                    NoteEvent(
                        start=index * 0.25,
                        end=index * 0.25 + 0.2,
                        pitch=root_pitch + index,
                        velocity=88,
                    )
                    for index in range(note_count)
                ],
            )
        ],
        bpm=120.0,
    )


def _write_pcm_wav(path: Path, *, frequency: float = 110.0) -> None:
    sample_rate = 8000
    frames = []
    for index in range(sample_rate * 2):
        value = int(
            round(math.sin(index * 2.0 * math.pi * frequency / sample_rate) * 24000)
        )
        frames.append(struct.pack("<h", value))
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(b"".join(frames))


def _write_pcm_wav_24_stereo(path: Path) -> None:
    sample_rate = 8000
    frames = bytearray()
    for index in range(sample_rate):
        left = int(round(math.sin(index * 2.0 * math.pi * 110.0 / sample_rate) * 5_000_000))
        right = int(round(math.sin(index * 2.0 * math.pi * 220.0 / sample_rate) * 3_000_000))
        frames.extend(left.to_bytes(3, "little", signed=True))
        frames.extend(right.to_bytes(3, "little", signed=True))
    block_align = 2 * 3
    pcm_subformat = bytes.fromhex("0100000000001000800000aa00389b71")
    format_data = (
        struct.pack(
            "<HHIIHHH",
            0xFFFE,
            2,
            sample_rate,
            sample_rate * block_align,
            block_align,
            24,
            22,
        )
        + struct.pack("<HI", 24, 3)
        + pcm_subformat
    )
    format_chunk = b"fmt " + struct.pack("<I", len(format_data)) + format_data
    data_chunk = b"data" + struct.pack("<I", len(frames)) + bytes(frames)
    riff_payload = b"WAVE" + format_chunk + data_chunk
    path.write_bytes(
        b"RIFF" + struct.pack("<I", len(riff_payload)) + riff_payload
    )


if __name__ == "__main__":
    unittest.main()
