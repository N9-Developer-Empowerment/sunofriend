from __future__ import annotations

import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import soundfile

from sunofriend.clip import read_midi_clips
from sunofriend.hybrid_report import (
    HYBRID_REPORT_SCHEMA,
    build_hybrid_report,
    write_hybrid_report,
)
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent


class _FakeSpectrum:
    def __init__(self, _path: str) -> None:
        pass

    def note_support(self, note: NoteEvent) -> float:
        return note.pitch / 127.0 + note.start / 1000.0


class HybridReportTests(unittest.TestCase):
    def _fixtures(self, root: Path) -> dict[str, object]:
        root.mkdir(parents=True, exist_ok=True)
        sample_rate = 8_000
        time = np.arange(sample_rate * 6, dtype=np.float64) / sample_rate
        audio = (0.1 * np.sin(2.0 * math.pi * 220.0 * time)).astype(np.float32)
        source = root / "private-source.wav"
        soundfile.write(source, audio, sample_rate, subtype="PCM_24")

        s0 = root / "s0.mid"
        m1 = root / "m1.mid"
        m3 = root / "m3.mid"
        write_midi_file(
            s0,
            [
                MidiTrack(
                    "S0",
                    0,
                    0,
                    [
                        NoteEvent(0.50, 1.00, 60, 80),
                        NoteEvent(1.96, 2.16, 72, 81),
                        NoteEvent(1.97, 2.20, 65, 81),
                        NoteEvent(2.50, 3.00, 62, 82),
                        NoteEvent(4.50, 5.00, 64, 84),
                    ],
                )
            ],
            bpm=120.0,
        )
        write_midi_file(
            m1,
            [
                MidiTrack(
                    "M1 main",
                    0,
                    0,
                    [
                        NoteEvent(0.55, 1.40, 60, 70),
                        NoteEvent(2.02, 2.22, 84, 71),
                        NoteEvent(2.03, 2.30, 65, 71),
                        NoteEvent(2.55, 3.05, 74, 72),
                        NoteEvent(3.50, 3.90, 67, 73),
                        NoteEvent(4.52, 5.02, 64, 74),
                    ],
                ),
                MidiTrack(
                    "M1 duplicate evidence",
                    1,
                    0,
                    [NoteEvent(4.53, 5.10, 64, 75)],
                ),
            ],
            bpm=120.0,
        )
        write_midi_file(
            m3,
            [
                MidiTrack(
                    "M3",
                    0,
                    0,
                    [
                        NoteEvent(0.49, 1.02, 60, 90),
                        NoteEvent(2.52, 3.02, 62, 91),
                        NoteEvent(3.80, 4.10, 69, 92),
                        NoteEvent(4.55, 5.05, 76, 93),
                    ],
                )
            ],
            bpm=120.0,
        )

        source_record = _identity(source)
        s0_notes = _midi_notes(s0)
        m1_notes = _midi_notes(m1)
        m3_notes = _midi_notes(m3)
        s0_evidence = root / "s0-provenance.json"
        _json(
            s0_evidence,
            {
                "schema_version": 1,
                "source_stem": str(source),
                "variant": "phrase_repaired",
                "conversion_mode": "repair",
                "counts": {"notes": len(s0_notes)},
                "notes": [
                    {
                        "start": note.start,
                        "end": note.end,
                        "pitch": note.pitch,
                        "velocity": note.velocity,
                    }
                    for note in s0_notes
                ],
            },
        )
        m1_evidence = root / "m1-label-split.json"
        m1_document = {
            "schema": "sunofriend.ai-label-split.v1",
            "status": "review-required",
            "operation": "ai-label-split",
            "bpm": 120.0,
            "label": "soprano_and_alto_sax",
            "source_run": {
                "backend": "muscriptor",
                "duration_seconds": 6.0,
                "request": {
                    "start_seconds": 0.0,
                    "end_seconds": 6.0,
                    "roles": ["soprano_and_alto_sax"],
                },
                "source": {
                    "bytes": 123456,
                    "sha256": "1" * 64,
                },
            },
            "artifacts": {"requested-label.mid": _identity(m1)},
            "evidence": {
                "detected_label_counts": {
                    "soprano_and_alto_sax": len(m1_notes),
                },
                "selected_note_count": len(m1_notes),
                "complement_note_count": 0,
                "selected_source_indices": list(range(len(m1_notes))),
                "complement_source_indices": [],
                "selection_policy": "exact-model-reported-instrument-label",
                "physical_instrument_identified": False,
            },
            "effects": {
                "automatic_promotion": False,
                "model_rerun": False,
                "source_run_mutated": False,
                "raw_candidate_mutated": False,
                "source_midi_mutated": False,
                "source_partition_events_deleted": 0,
                "source_partition_events_duplicated": 0,
                "source_request_control_byte_identical": True,
                "source_candidate_control_byte_identical": True,
                "unchanged_control_byte_identical": True,
                "selected_audition_velocities_written": len(m1_notes),
                "midi_rendering": {
                    "requested-label.mid": {
                        "source_event_count": len(m1_notes),
                        "rendered_midi_note_count": len(m1_notes),
                        "rendered_midi_note_signatures": _rendered_signatures(m1),
                        "integer_pitch_quantized_event_count": 0,
                        "onset_tick_quantized_event_count": 0,
                        "end_tick_quantized_event_count": 0,
                        "duration_tick_quantized_event_count": 0,
                        "minimum_duration_extended_event_count": 0,
                        "duplicate_same_pitch_tick_onset_collapsed_event_count": 0,
                        "same_pitch_overlap_truncated_event_count": 0,
                        "source_event_to_midi_note_count_delta": 0,
                        "lossless_event_render": True,
                    }
                },
            },
        }
        m1_document["report_sha256"] = _document_hash(m1_document)
        _json(m1_evidence, m1_document)
        m3_evidence = root / "m3-projection.json"
        _json(
            m3_evidence,
            {
                "schema": "sunofriend.phase5-review-projection.v1",
                "status": "complete",
                "source_excerpt": {
                    "start_seconds": 30.0,
                    "end_seconds": 36.0,
                    "duration_seconds": 6.0,
                    "codec": "pcm_s24le",
                    "sample_rate_hz": sample_rate,
                    "channels": 1,
                },
                "midi_transform": {
                    "operation": "midi-anchor",
                    "source_bpm": 120.0,
                    "target_bpm": 120.0,
                    "source_downbeat_seconds": 30.0,
                    "target_downbeat_beat": 0.0,
                    "shift_ticks": -28_800,
                    "semitones": 0,
                    "pitch_changed": 0,
                    "duration_changed": 0,
                    "velocity_changed": 0,
                    "note_count_changed": 0,
                },
                "roles": {
                    "vocals": {
                        "source_audio_sha256": "2" * 64,
                        "excerpt_audio_sha256": source_record["sha256"],
                        "source_midi_sha256": "3" * 64,
                        "projected_midi_sha256": _sha256(m3),
                        "note_count": len(m3_notes),
                        "pitch_velocity_duration_unchanged": True,
                    }
                },
                "effects": {
                    "model_rerun": False,
                    "source_audio_mutated": False,
                    "source_ai_run_mutated": False,
                    "automatic_selection": False,
                    "musical_repair": False,
                },
            },
        )
        phrase_review = root / "phrase-review.json"
        _json(
            phrase_review,
            {
                "schema": "sunofriend.melody-phrase-review.v1",
                "status": "review-required",
                "selection_policy": (
                    "human phrase choice; raw Basic Pitch and agreed-F0 boundary "
                    "candidates remain unchanged"
                ),
                "raw_candidates_mutated": False,
                "source": source_record,
                "bpm": 120.0,
                "role": "lead",
                "source_phrase_count": 3,
                "review_unit_count": 3,
                "phrase_count": 3,
                "segmentation": {
                    "policy": "consecutive-clusters-to-musical-length-v1",
                    "source_phrase_count": 3,
                    "review_unit_count": 3,
                    "minimum_bars": 1,
                    "maximum_bars": 8,
                    "beats_per_bar": 4,
                    "bar_seconds": 2.0,
                    "raw_phrase_records_mutated": False,
                    "bar_alignment": (
                        "duration-only; no unconfirmed downbeat was assumed"
                    ),
                    "short_unit_count": 0,
                    "long_unit_count": 0,
                    "warnings": [],
                },
                "phrases": [
                    {
                        "phrase_index": 0,
                        "start_seconds": 0.0,
                        "end_seconds": 2.0,
                        "duration_seconds": 2.0,
                        "duration_bars": 1.0,
                        "length_status": "within-range",
                        "source_phrase_indices": [0],
                        "source_phrase_count": 1,
                    },
                    {
                        "phrase_index": 1,
                        "start_seconds": 2.0,
                        "end_seconds": 4.0,
                        "duration_seconds": 2.0,
                        "duration_bars": 1.0,
                        "length_status": "within-range",
                        "source_phrase_indices": [1],
                        "source_phrase_count": 1,
                    },
                    {
                        "phrase_index": 2,
                        "start_seconds": 4.0,
                        "end_seconds": 6.0,
                        "duration_seconds": 2.0,
                        "duration_bars": 1.0,
                        "length_status": "within-range",
                        "source_phrase_indices": [2],
                        "source_phrase_count": 1,
                    },
                ],
                "repetition": {
                    "schema": "sunofriend.melody-review-repetition.v1",
                    "review_unit_count": 3,
                    "evaluated_pair_count": 3,
                    "accepted_pair_count": 0,
                    "evaluated_pairs": [
                        _rejected_repetition_pair(0, 0, 1, 2.0),
                        _rejected_repetition_pair(1, 0, 2, 4.0),
                        _rejected_repetition_pair(2, 1, 2, 2.0),
                    ],
                    "accepted_pairs": [],
                    "groups": [],
                    "raw_candidates_mutated": False,
                    "policy": {
                        "name": "exact-count-source-contour-repeat-v1",
                        "minimum_notes": 3,
                        "note_count": "exact",
                        "minimum_unit_duration_ratio": 0.8,
                        "minimum_pitch_match_ratio": 0.8,
                        "minimum_interval_match_ratio": 0.75,
                        "maximum_timing_p90_beats": 0.25,
                        "minimum_note_duration_similarity": 0.6,
                        "content_time_scale_range": [0.85, 1.15],
                        "absolute_pitch_required": True,
                        "automatic_selection": False,
                        "human_confirmation_required": True,
                    },
                },
            },
        )
        return {
            "source": source,
            "candidates": {"S0": s0, "M1": m1, "M3": m3},
            "evidence": {
                "S0": s0_evidence,
                "M1": m1_evidence,
                "M3": m3_evidence,
            },
            "phrase_review": phrase_review,
        }

    def _build(self, fixture: dict[str, object]) -> dict[str, object]:
        with mock.patch("sunofriend.hybrid_report.StemSpectrum", _FakeSpectrum):
            return build_hybrid_report(
                fixture["source"],
                role="lead",
                bpm=120.0,
                candidates=fixture["candidates"],
                evidence=fixture["evidence"],
                phrase_review=fixture["phrase_review"],
            )

    def test_builds_path_free_source_supported_disagreement_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self._fixtures(root)
            before = _tree_hashes(root)
            report = self._build(fixture)

            self.assertEqual(report["schema"], HYBRID_REPORT_SCHEMA)
            self.assertEqual(report["status"], "diagnostic-only")
            self.assertIn(
                "every phrase or review-unit gap",
                report["policies"]["cross_boundary_match_counting"],
            )
            self.assertEqual(
                [row["lane"] for row in report["candidates"]], ["S0", "M1", "M3"]
            )
            self.assertTrue(
                all(
                    isinstance(note["raw_source_support"], float)
                    for lane in report["candidates"]
                    for note in lane["notes"]
                )
            )
            pair_s0_m1 = report["pairwise"][0]
            self.assertGreater(pair_s0_m1["counts"]["exact_pitch_onset_matches"], 0)
            self.assertEqual(pair_s0_m1["counts"]["cross_phrase_boundary_matches"], 1)
            self.assertEqual(
                pair_s0_m1["outside_phrase_counts"]["cross_phrase_boundary_matches"],
                0,
            )
            self.assertEqual(
                [
                    row["cross_phrase_boundary_matches"]
                    for row in pair_s0_m1["per_phrase"]
                ],
                [1, 1, 0],
            )
            self.assertGreater(
                pair_s0_m1["counts"]["same_pitch_boundary_duration_disputes"], 0
            )
            self.assertEqual(
                [
                    row["same_pitch_boundary_duration_disputes"]
                    for row in pair_s0_m1["per_phrase"]
                ],
                [2, 1, 0],
            )
            self.assertGreater(
                pair_s0_m1["counts"]["octave_equivalent_onset_disputes"], 0
            )
            self.assertEqual(
                [
                    row["octave_equivalent_onset_disputes"]
                    for row in pair_s0_m1["per_phrase"]
                ],
                [1, 2, 0],
            )
            self.assertEqual(
                pair_s0_m1["outside_phrase_counts"]["octave_equivalent_onset_disputes"],
                0,
            )
            m1 = report["candidates"][1]
            self.assertGreater(m1["duplicate_evidence"]["group_count"], 0)
            self.assertEqual(len(report["ranked_disagreement_phrases"]), 3)
            self.assertEqual(
                [phrase["phrase_index"] for phrase in report["phrases"]],
                [0, 1, 2],
            )
            self.assertEqual(
                report["repetition_evidence"]["evaluated_pairs"][0][
                    "left_phrase_index"
                ],
                0,
            )
            self.assertEqual(report["chord_evidence"]["status"], "unavailable-unpinned")
            self.assertEqual(
                report["lineage"]["M1_full_mix_association"]["status"],
                "caller-supplied-derivation-unverified",
            )
            self.assertEqual(
                report["lineage"]["M3_original_source_midi"]["status"],
                "manifest-claimed-payload-unverified",
            )
            m3_verification = report["candidates"][2]["evidence"]["verification"]
            self.assertTrue(m3_verification["mutation_effect_claims_validated"])
            self.assertNotIn("mutation_effects_verified", m3_verification)
            self.assertTrue(
                any(
                    row["cross_phrase_boundary_match_references"] > 0
                    for row in report["ranked_disagreement_phrases"]
                )
            )
            self.assertEqual(report["effects"]["ai_inference_runs"], 0)
            self.assertEqual(report["effects"]["midi_files_created"], 0)
            self.assertFalse(report["effects"]["automatic_selection"])
            self.assertNotIn(str(root), json.dumps(report, sort_keys=True))
            self.assertEqual(_tree_hashes(root), before)

    def test_repeat_build_and_atomic_outputs_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self._fixtures(root)
            first = root / "reports" / "first.json"
            second = root / "reports" / "second.json"
            with mock.patch("sunofriend.hybrid_report.StemSpectrum", _FakeSpectrum):
                first_report = write_hybrid_report(
                    fixture["source"],
                    role="lead",
                    bpm=120.0,
                    candidates=fixture["candidates"],
                    evidence=fixture["evidence"],
                    phrase_review=fixture["phrase_review"],
                    output_path=first,
                )
                second_report = write_hybrid_report(
                    fixture["source"],
                    role="lead",
                    bpm=120.0,
                    candidates=fixture["candidates"],
                    evidence=fixture["evidence"],
                    phrase_review=fixture["phrase_review"],
                    output_path=second,
                )
            self.assertEqual(first_report, second_report)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with mock.patch("sunofriend.hybrid_report.StemSpectrum", _FakeSpectrum):
                with self.assertRaises(FileExistsError):
                    write_hybrid_report(
                        fixture["source"],
                        role="lead",
                        bpm=120.0,
                        candidates=fixture["candidates"],
                        evidence=fixture["evidence"],
                        phrase_review=fixture["phrase_review"],
                        output_path=first,
                    )

    def test_requires_exact_lane_names_and_distinct_midi(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixtures(Path(temporary))
            candidates = dict(fixture["candidates"])
            candidates.pop("M3")
            with self.assertRaisesRegex(ValueError, "exactly S0, M1 and M3"):
                with mock.patch("sunofriend.hybrid_report.StemSpectrum", _FakeSpectrum):
                    build_hybrid_report(
                        fixture["source"],
                        role="lead",
                        bpm=120.0,
                        candidates=candidates,
                        evidence=fixture["evidence"],
                        phrase_review=fixture["phrase_review"],
                    )
            candidates = dict(fixture["candidates"])
            candidates["M3"] = candidates["M1"]
            with self.assertRaisesRegex(ValueError, "must be distinct"):
                with mock.patch("sunofriend.hybrid_report.StemSpectrum", _FakeSpectrum):
                    build_hybrid_report(
                        fixture["source"],
                        role="lead",
                        bpm=120.0,
                        candidates=candidates,
                        evidence=fixture["evidence"],
                        phrase_review=fixture["phrase_review"],
                    )
            candidates = dict(fixture["candidates"])
            duplicate = Path(temporary) / "m3-copy.mid"
            duplicate.write_bytes(Path(candidates["M1"]).read_bytes())
            candidates["M3"] = duplicate
            with self.assertRaisesRegex(ValueError, "contents must be distinct"):
                with mock.patch("sunofriend.hybrid_report.StemSpectrum", _FakeSpectrum):
                    build_hybrid_report(
                        fixture["source"],
                        role="lead",
                        bpm=120.0,
                        candidates=candidates,
                        evidence=fixture["evidence"],
                        phrase_review=fixture["phrase_review"],
                    )

    def test_rejects_m1_or_m3_hash_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self._fixtures(root)
            m1_document = json.loads(Path(fixture["evidence"]["M1"]).read_text())
            m1_document["artifacts"]["requested-label.mid"]["sha256"] = "0" * 64
            _json(Path(fixture["evidence"]["M1"]), m1_document)
            with self.assertRaisesRegex(ValueError, "document hash"):
                self._build(fixture)

            fixture = self._fixtures(root / "second")
            m3_document = json.loads(Path(fixture["evidence"]["M3"]).read_text())
            m3_document["roles"]["vocals"]["excerpt_audio_sha256"] = "0" * 64
            _json(Path(fixture["evidence"]["M3"]), m3_document)
            with self.assertRaisesRegex(ValueError, "does not pin"):
                self._build(fixture)

    def test_rejects_s0_payload_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixtures(Path(temporary))
            path = Path(fixture["evidence"]["S0"])
            document = json.loads(path.read_text())
            document["notes"][0]["pitch"] += 1
            _json(path, document)
            with self.assertRaisesRegex(ValueError, "onsets do not match"):
                self._build(fixture)

    def test_rejects_m1_and_m3_timeline_or_role_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self._fixtures(root / "m1")
            m1_path = Path(fixture["evidence"]["M1"])
            m1_document = json.loads(m1_path.read_text())
            m1_document["source_run"]["duration_seconds"] = 5.0
            m1_document.pop("report_sha256")
            m1_document["report_sha256"] = _document_hash(m1_document)
            _json(m1_path, m1_document)
            with self.assertRaisesRegex(ValueError, "geometry"):
                self._build(fixture)

            fixture = self._fixtures(root / "m3-timing")
            m3_path = Path(fixture["evidence"]["M3"])
            m3_document = json.loads(m3_path.read_text())
            m3_document["midi_transform"]["target_bpm"] = 121.0
            _json(m3_path, m3_document)
            with self.assertRaisesRegex(ValueError, "timing"):
                self._build(fixture)

            fixture = self._fixtures(root / "m3-role")
            m3_path = Path(fixture["evidence"]["M3"])
            m3_document = json.loads(m3_path.read_text())
            m3_document["roles"]["keys"] = m3_document["roles"].pop("vocals")
            _json(m3_path, m3_document)
            with self.assertRaisesRegex(ValueError, "does not pin"):
                self._build(fixture)

    def test_accepts_m1_duplicate_collapse_and_verifies_raw_and_rendered_counts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixtures(Path(temporary))
            path = Path(fixture["evidence"]["M1"])
            document = json.loads(path.read_text())
            selected = document["evidence"]["selected_note_count"] + 1
            document["evidence"]["selected_note_count"] = selected
            document["evidence"]["selected_source_indices"].append(selected - 1)
            document["evidence"]["detected_label_counts"][document["label"]] = selected
            document["effects"]["selected_audition_velocities_written"] = selected
            render = document["effects"]["midi_rendering"]["requested-label.mid"]
            render["source_event_count"] = selected
            render["duplicate_same_pitch_tick_onset_collapsed_event_count"] = 1
            render["source_event_to_midi_note_count_delta"] = -1
            render["lossless_event_render"] = False
            _write_hashed_m1(path, document)

            report = self._build(fixture)
            verification = report["candidates"][1]["evidence"]["verification"]
            self.assertEqual(verification["raw_selected_event_count"], selected)
            self.assertEqual(verification["rendered_midi_note_count"], selected - 1)
            self.assertEqual(
                verification["duplicate_same_pitch_tick_onset_collapsed_event_count"],
                1,
            )

    def test_rejects_m1_rendered_note_expansion_claimed_as_lossless(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixtures(Path(temporary))
            midi_path = Path(fixture["candidates"]["M1"])
            clips = read_midi_clips(midi_path)
            tracks = [
                MidiTrack(
                    clip.title,
                    clip.instrument.channel,
                    clip.instrument.program,
                    [
                        NoteEvent(
                            note.source_start_seconds,
                            note.source_end_seconds,
                            note.pitch,
                            note.velocity,
                        )
                        for note in clip.notes
                    ],
                )
                for clip in clips
            ]
            tracks[0].notes.append(NoteEvent(5.50, 5.80, 71, 76))
            write_midi_file(midi_path, tracks, bpm=120.0)

            evidence_path = Path(fixture["evidence"]["M1"])
            document = json.loads(evidence_path.read_text())
            rendered = document["effects"]["midi_rendering"]["requested-label.mid"]
            rendered["rendered_midi_note_count"] += 1
            rendered["source_event_to_midi_note_count_delta"] = 1
            rendered["rendered_midi_note_signatures"] = _rendered_signatures(midi_path)
            document["artifacts"]["requested-label.mid"] = _identity(midi_path)
            _write_hashed_m1(evidence_path, document)

            with self.assertRaisesRegex(ValueError, "MIDI-render counts"):
                self._build(fixture)

    def test_rejects_m1_render_change_counter_above_event_population(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixtures(Path(temporary))
            evidence_path = Path(fixture["evidence"]["M1"])
            document = json.loads(evidence_path.read_text())
            rendered = document["effects"]["midi_rendering"]["requested-label.mid"]
            rendered["onset_tick_quantized_event_count"] = (
                rendered["source_event_count"] + 1
            )
            rendered["lossless_event_render"] = False
            _write_hashed_m1(evidence_path, document)

            with self.assertRaisesRegex(ValueError, "counters exceed"):
                self._build(fixture)

    def test_m1_same_song_derivation_is_explicitly_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixtures(Path(temporary))
            path = Path(fixture["evidence"]["M1"])
            document = json.loads(path.read_text())
            document["source_run"]["source"]["sha256"] = "f" * 64
            _write_hashed_m1(path, document)

            report = self._build(fixture)
            lineage = report["lineage"]["M1_full_mix_association"]
            self.assertEqual(lineage["full_mix_source"]["sha256"], "f" * 64)
            self.assertEqual(lineage["status"], "caller-supplied-derivation-unverified")
            self.assertFalse(
                report["interpretation"]["m1_same_song_derivation_verified"]
            )

    def test_rejects_tampered_m1_semantic_and_mutation_contracts(self) -> None:
        changes = (
            (lambda value: value.update({"status": "complete"}), "review-required"),
            (
                lambda value: value["source_run"].update({"backend": "other"}),
                "MuScriptor",
            ),
            (
                lambda value: value["effects"].update({"source_run_mutated": True}),
                "mutation or control",
            ),
            (
                lambda value: value["evidence"].update(
                    {"physical_instrument_identified": "false"}
                ),
                "exact-label partition",
            ),
            (
                lambda value: value["evidence"].update(
                    {
                        "selected_source_indices": [
                            item + 100
                            for item in value["evidence"]["selected_source_indices"]
                        ]
                    }
                ),
                "exact-label partition",
            ),
            (
                lambda value: value["effects"]["midi_rendering"][
                    "requested-label.mid"
                ].update({"lossless_event_render": False}),
                "lossless-render",
            ),
            (
                lambda value: value["source_run"]["source"].update(
                    {"sha256": "x" * 64}
                ),
                "SHA-256",
            ),
        )
        for index, (change, message) in enumerate(changes):
            with (
                self.subTest(message=message),
                tempfile.TemporaryDirectory() as temporary,
            ):
                fixture = self._fixtures(Path(temporary) / str(index))
                path = Path(fixture["evidence"]["M1"])
                document = json.loads(path.read_text())
                change(document)
                _write_hashed_m1(path, document)
                with self.assertRaisesRegex(ValueError, message):
                    self._build(fixture)

    def test_rejects_tampered_m3_projection_contracts(self) -> None:
        changes = (
            (
                lambda value: value["midi_transform"].update({"operation": "retime"}),
                "unsupported transform",
            ),
            (
                lambda value: value["midi_transform"].update({"semitones": 1}),
                "unsupported transform",
            ),
            (
                lambda value: value["midi_transform"].update({"shift_ticks": -1}),
                "timing",
            ),
            (
                lambda value: value["source_excerpt"].update(
                    {"sample_rate_hz": 44_100}
                ),
                "geometry",
            ),
            (
                lambda value: value["source_excerpt"].update({"codec": "pcm_s16le"}),
                "geometry",
            ),
            (
                lambda value: value["effects"].update({"source_audio_mutated": True}),
                "effects",
            ),
        )
        for index, (change, message) in enumerate(changes):
            with (
                self.subTest(message=message),
                tempfile.TemporaryDirectory() as temporary,
            ):
                fixture = self._fixtures(Path(temporary) / str(index))
                path = Path(fixture["evidence"]["M3"])
                document = json.loads(path.read_text())
                change(document)
                _json(path, document)
                with self.assertRaisesRegex(ValueError, message):
                    self._build(fixture)

    def test_projects_only_path_free_phrase_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixtures(Path(temporary))
            path = Path(fixture["phrase_review"])
            document = json.loads(path.read_text())
            document["segmentation"]["private_path"] = "/Users/example/private.wav"
            document["repetition"]["policy"]["private_path"] = "/private/policy"
            document["repetition"]["evaluated_pairs"][0]["private_path"] = (
                "/private/pair"
            )
            _json(path, document)

            report = self._build(fixture)
            rendered = json.dumps(report, sort_keys=True)
            self.assertNotIn("/Users/example", rendered)
            self.assertNotIn("/private/", rendered)
            self.assertNotIn("private_path", rendered)

            fixture = self._fixtures(Path(temporary) / "unsafe-s0")
            s0_path = Path(fixture["evidence"]["S0"])
            s0_document = json.loads(s0_path.read_text())
            s0_document["variant"] = "/Users/example/private.mid"
            _json(s0_path, s0_document)
            with self.assertRaisesRegex(ValueError, "path-free"):
                self._build(fixture)

    def test_rejects_inconsistent_repetition_and_segmentation_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self._fixtures(root / "status")
            path = Path(fixture["phrase_review"])
            document = json.loads(path.read_text())
            document["repetition"]["evaluated_pairs"][0]["status"] = "accepted"
            document["repetition"]["evaluated_pairs"][0]["rejection_reasons"] = []
            _json(path, document)
            with self.assertRaisesRegex(ValueError, "rejection reasons|status"):
                self._build(fixture)

            fixture = self._fixtures(root / "bar")
            path = Path(fixture["phrase_review"])
            document = json.loads(path.read_text())
            document["segmentation"]["bar_seconds"] = 999.0
            _json(path, document)
            with self.assertRaisesRegex(ValueError, "bar seconds"):
                self._build(fixture)

            fixture = self._fixtures(root / "lag")
            path = Path(fixture["phrase_review"])
            document = json.loads(path.read_text())
            document["repetition"]["evaluated_pairs"][0]["lag_seconds"] = 999.0
            _json(path, document)
            with self.assertRaisesRegex(ValueError, "lag disagrees"):
                self._build(fixture)

            fixture = self._fixtures(root / "duration-ratio")
            path = Path(fixture["phrase_review"])
            document = json.loads(path.read_text())
            document["repetition"]["evaluated_pairs"][0]["unit_duration_ratio"] = 0.5
            _json(path, document)
            with self.assertRaisesRegex(ValueError, "duration ratio disagrees"):
                self._build(fixture)

            fixture = self._fixtures(root / "length-counts")
            path = Path(fixture["phrase_review"])
            document = json.loads(path.read_text())
            document["segmentation"]["short_unit_count"] = 3
            _json(path, document)
            with self.assertRaisesRegex(ValueError, "length-status counts"):
                self._build(fixture)

            fixture = self._fixtures(root / "warnings")
            path = Path(fixture["phrase_review"])
            document = json.loads(path.read_text())
            document["segmentation"]["warnings"] = ["unrelated warning"]
            _json(path, document)
            with self.assertRaisesRegex(ValueError, "warnings disagree"):
                self._build(fixture)

            fixture = self._fixtures(root / "source-count")
            path = Path(fixture["phrase_review"])
            document = json.loads(path.read_text())
            document["segmentation"]["source_phrase_count"] = 0
            _json(path, document)
            with self.assertRaisesRegex(ValueError, "source phrase count"):
                self._build(fixture)

            fixture = self._fixtures(root / "accepted-mismatch")
            path = Path(fixture["phrase_review"])
            document = json.loads(path.read_text())
            pair = document["repetition"]["evaluated_pairs"][0]
            pair.update(
                {
                    "status": "accepted",
                    "left_note_count": 3,
                    "right_note_count": 3,
                    "pitch_match_ratio": 1.0,
                    "interval_match_ratio": 1.0,
                    "timing_p90_beats": 0.0,
                    "note_duration_similarity": 1.0,
                    "content_time_scale": 1.0,
                    "similarity_score": 1.0,
                    "rejection_reasons": [],
                }
            )
            accepted = json.loads(json.dumps(pair))
            accepted["right_phrase_index"] = 2
            accepted["lag_seconds"] = 4.0
            document["repetition"]["accepted_pair_count"] = 1
            document["repetition"]["accepted_pairs"] = [accepted]
            _json(path, document)
            with self.assertRaisesRegex(ValueError, "accepted pairs disagree"):
                self._build(fixture)

    def test_v1_rejects_non_lead_role_and_note_empty_midi(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self._fixtures(root / "role")
            with self.assertRaisesRegex(ValueError, "lead role only"):
                with mock.patch("sunofriend.hybrid_report.StemSpectrum", _FakeSpectrum):
                    build_hybrid_report(
                        fixture["source"],
                        role="backing",
                        bpm=120.0,
                        candidates=fixture["candidates"],
                        evidence=fixture["evidence"],
                        phrase_review=fixture["phrase_review"],
                    )

            fixture = self._fixtures(root / "empty")
            empty = root / "empty" / "empty.mid"
            write_midi_file(empty, [MidiTrack("empty", 0, 0, [])], bpm=120.0)
            fixture["candidates"]["M3"] = empty
            with self.assertRaisesRegex(ValueError, "no MIDI notes"):
                self._build(fixture)

            fixture = self._fixtures(root / "aiff")
            disguised = Path(fixture["source"])
            soundfile.write(
                disguised,
                np.zeros(8_000, dtype=np.float32),
                8_000,
                format="AIFF",
                subtype="PCM_24",
            )
            with self.assertRaisesRegex(ValueError, "WAV-family"):
                self._build(fixture)

    def test_rejects_phrase_source_bpm_role_and_geometry_changes(self) -> None:
        changes = (
            (lambda value: value["source"].update({"sha256": "0" * 64}), "source"),
            (lambda value: value.update({"bpm": 121.0}), "BPM"),
            (lambda value: value.update({"role": "backing"}), "role"),
            (lambda value: value["phrases"].pop(), "unit count"),
            (lambda value: value.update({"status": "complete"}), "unresolved"),
            (
                lambda value: value.update({"raw_candidates_mutated": True}),
                "raw candidates",
            ),
            (
                lambda value: value.update({"selection_policy": "automatic winner"}),
                "selection policy",
            ),
        )
        for index, (change, message) in enumerate(changes):
            with (
                self.subTest(message=message),
                tempfile.TemporaryDirectory() as temporary,
            ):
                fixture = self._fixtures(Path(temporary) / str(index))
                path = Path(fixture["phrase_review"])
                document = json.loads(path.read_text())
                change(document)
                _json(path, document)
                with self.assertRaisesRegex(ValueError, message):
                    self._build(fixture)

    def test_rejects_repetition_references_outside_source_phrase_namespace(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixtures(Path(temporary))
            path = Path(fixture["phrase_review"])
            document = json.loads(path.read_text())
            document["repetition"]["evaluated_pairs"][0]["right_phrase_index"] = 9
            _json(path, document)
            with self.assertRaisesRegex(ValueError, "unknown phrase index"):
                self._build(fixture)

    def test_rejects_non_finite_source_support(self) -> None:
        class BrokenSpectrum(_FakeSpectrum):
            def note_support(self, note: NoteEvent) -> float:
                return float("nan")

        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixtures(Path(temporary))
            with mock.patch("sunofriend.hybrid_report.StemSpectrum", BrokenSpectrum):
                with self.assertRaisesRegex(ValueError, "non-finite source support"):
                    build_hybrid_report(
                        fixture["source"],
                        role="lead",
                        bpm=120.0,
                        candidates=fixture["candidates"],
                        evidence=fixture["evidence"],
                        phrase_review=fixture["phrase_review"],
                    )

    def test_rejects_input_drift_during_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixtures(Path(temporary))
            with mock.patch(
                "sunofriend.hybrid_report._input_fingerprints",
                side_effect=[{"source": (1,)}, {"source": (2,)}],
            ):
                with self.assertRaisesRegex(ValueError, "input changed"):
                    self._build(fixture)

    def test_rejects_separate_s0_provenance_source_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self._fixtures(root)
            source_copy = root / "separate-identical-source.wav"
            source_copy.write_bytes(Path(fixture["source"]).read_bytes())
            evidence_path = Path(fixture["evidence"]["S0"])
            document = json.loads(evidence_path.read_text())
            document["source_stem"] = str(source_copy)
            _json(evidence_path, document)

            with self.assertRaisesRegex(ValueError, "does not match"):
                self._build(fixture)


def _midi_notes(path: Path) -> list[NoteEvent]:
    return sorted(
        (
            NoteEvent(
                note.source_start_seconds,
                note.source_end_seconds,
                note.pitch,
                note.velocity,
            )
            for clip in read_midi_clips(path)
            for note in clip.notes
        ),
        key=lambda note: (note.start, note.end, note.pitch, note.velocity),
    )


def _identity(path: Path) -> dict[str, object]:
    return {"bytes": path.stat().st_size, "sha256": _sha256(path)}


def _rendered_signatures(path: Path) -> list[dict[str, int]]:
    return sorted(
        (
            {
                "track_index": owner,
                "channel": clip.instrument.channel,
                "start_tick": round(note.start_beat * 480),
                "end_tick": round(note.end_beat * 480),
                "pitch": note.pitch,
                "velocity": note.velocity,
            }
            for owner, clip in enumerate(read_midi_clips(path))
            for note in clip.notes
        ),
        key=lambda row: (
            row["track_index"],
            row["channel"],
            row["start_tick"],
            row["end_tick"],
            row["pitch"],
            row["velocity"],
        ),
    )


def _rejected_repetition_pair(
    pair_index: int, left: int, right: int, lag_seconds: float
) -> dict[str, object]:
    return {
        "pair_index": pair_index,
        "status": "rejected",
        "left_phrase_index": left,
        "right_phrase_index": right,
        "lag_seconds": lag_seconds,
        "left_note_count": 2,
        "right_note_count": 2,
        "unit_duration_ratio": 1.0,
        "pitch_match_ratio": 0.0,
        "interval_match_ratio": 0.0,
        "timing_p90_beats": None,
        "note_duration_similarity": 0.0,
        "content_time_scale": None,
        "similarity_score": 0.1,
        "rejection_reasons": [
            "insufficient-notes",
            "absolute-pitch-mismatch",
            "contour-interval-mismatch",
            "onset-timing-mismatch",
            "note-duration-mismatch",
            "content-time-scale-mismatch",
        ],
        "absolute_pitch_required": True,
        "automatic_selection": False,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _document_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_hashed_m1(path: Path, value: dict[str, object]) -> None:
    value.pop("report_sha256", None)
    value["report_sha256"] = _document_hash(value)
    _json(path, value)


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): _sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


if __name__ == "__main__":
    unittest.main()
