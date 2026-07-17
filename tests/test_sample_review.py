from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile

from sunofriend.instrument_dynamics import (
    analyze_source_event_dynamics,
    source_event_dynamics_svg,
)
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.sample_review import (
    SAMPLE_BOUNDARY_REVIEW_SCHEMA,
    SAMPLE_PACK_REVIEW_SCHEMA,
    SAMPLE_PACK_V3_SCHEMA,
    _application_features,
    _mapping_candidate_specs,
    apply_sample_boundary_review,
    apply_sample_pack_review,
    create_sample_boundary_review,
    create_sample_pack_review,
)
from sunofriend.soundfont import SoundFontZone, inspect_soundfont, write_soundfont


SAMPLE_RATE = 16_000


class SamplePackReviewTests(unittest.TestCase):
    def test_mapping_candidates_flag_layers_outside_source_velocity_range(self):
        candidates = _mapping_candidate_specs(
            {
                "velocity_boundary": 116,
                "layers": [
                    {"primary_event_index": 13},
                    {"primary_event_index": 25},
                ],
            },
            boundaries=[96, 104, 116, 120, 124],
            source_velocity_range=[102, 120],
        )
        by_id = {row["mapping_id"]: row for row in candidates}

        self.assertIn("lower layer", by_id["layered-096"]["source_midi_warning"])
        self.assertIsNone(by_id["layered-104"]["source_midi_warning"])
        self.assertIsNone(by_id["layered-116"]["source_midi_warning"])
        self.assertIn("upper layer", by_id["layered-120"]["source_midi_warning"])
        self.assertIn("upper layer", by_id["layered-124"]["source_midi_warning"])
        self.assertIsNone(by_id["single-low"]["source_midi_warning"])
        self.assertIsNone(by_id["single-high"]["source_midi_warning"])

    def test_application_features_report_only_accepted_features(self):
        features = _application_features(
            [
                {
                    "velocity_layers_applied": False,
                    "layers": [{"accepted_event_indices": [10]}],
                }
            ],
            [],
        )

        self.assertEqual(features["reviewed_sample_replacement_count"], 1)
        self.assertEqual(features["velocity_layer_unit_count"], 0)
        self.assertEqual(features["round_robin_layer_count"], 0)
        self.assertEqual(features["garageband_alternate_bank_count"], 0)

    def test_review_then_apply_keeps_v2_and_builds_layered_ab_variants(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_pack = _write_v2_fixture(root)
            baseline_hash = _tree_hash(source_pack)
            review_dir = root / "review"

            seed = create_sample_pack_review(source_pack, out_dir=review_dir)

            self.assertEqual(seed["schema"], SAMPLE_PACK_REVIEW_SCHEMA)
            self.assertEqual(seed["status"], "unreviewed")
            self.assertEqual(seed["summary"]["review_unit_count"], 1)
            self.assertEqual(seed["summary"]["velocity_layer_unit_count"], 1)
            self.assertEqual(seed["summary"]["context_audio_file_count"], 12)
            self.assertEqual(
                seed["review_evidence"]["context_policy"]["role_audition_mode"],
                "repeated-beat",
            )
            self.assertEqual(seed["review_evidence"]["audio_file_count"], 18)
            self.assertTrue((review_dir / "sample_pack_review.html").is_file())
            self.assertEqual(len(list((review_dir / "review-audio").glob("*.wav"))), 6)
            self.assertEqual(
                len(list((review_dir / "review-audio").rglob("*.wav"))), 18
            )
            page = (review_dir / "sample_pack_review.html").read_text()
            self.assertIn("Mark all current choices reviewed", page)
            self.assertIn("Export review JSON", page)
            self.assertIn("Repeated two-bar beat", page)
            self.assertIn("Source rhythm and surrounding stem", page)
            self.assertNotIn("ei === 0 ? 'checked' : ''", page)
            self.assertIn(
                "Choose one primary source for every layer you accept.", page
            )
            self.assertEqual(_tree_hash(source_pack), baseline_hash)

            repeat_seed = create_sample_pack_review(
                source_pack, out_dir=root / "review-repeat"
            )
            self.assertEqual(
                seed["review_evidence"]["manifest_sha256"],
                repeat_seed["review_evidence"]["manifest_sha256"],
            )

            reviewed = json.loads(
                (review_dir / "sample_pack_review.seed.json").read_text()
            )
            reviewed["status"] = "reviewed"
            reviewed["units"][0]["decision"] = "accept"
            for layer in reviewed["units"][0]["layers"]:
                proposed = layer["candidate_event_indices"]
                layer["primary_event_index"] = proposed[0]
                layer["accepted_event_indices"] = proposed[:2]
            reviewed_path = review_dir / "sample_pack_review.reviewed.json"
            _write_json(reviewed_path, reviewed)

            output = root / "v3"
            report = apply_sample_pack_review(
                reviewed_path,
                out_dir=output,
                render_preview=False,
                instrument_name="Reviewed Kick",
            )

            self.assertEqual(report["schema"], SAMPLE_PACK_V3_SCHEMA)
            self.assertEqual(report["format_version"], 3)
            self.assertTrue(report["experimental"])
            self.assertFalse(report["baseline"]["mutated"])
            self.assertEqual(report["review"]["accepted_unit_count"], 1)
            self.assertEqual(report["effects"]["accepted_source_events_added"], 4)
            self.assertEqual(report["effects"]["soundfont_zone_count_before"], 1)
            self.assertEqual(report["effects"]["soundfont_zone_count_after"], 2)
            self.assertEqual(report["effects"]["midi_velocities_changed"], 0)
            self.assertEqual(report["applied_features"]["velocity_layer_unit_count"], 1)
            self.assertEqual(report["applied_features"]["round_robin_layer_count"], 2)
            self.assertEqual(
                report["applied_features"]["garageband_alternate_bank_count"], 1
            )
            self.assertTrue(report["soundfont"]["velocity_layers"])
            self.assertTrue(report["sfz"]["round_robin"])
            self.assertEqual(_tree_hash(source_pack), baseline_hash)
            self.assertEqual(
                _sha(output / "baseline-v2/sunofriend-instrument-v2.sf2"),
                _sha(source_pack / "sunofriend-instrument.sf2"),
            )
            self.assertEqual(
                inspect_soundfont(output / "sunofriend-instrument.sf2")["sample_count"],
                2,
            )
            sfz = (output / "sunofriend-instrument.sfz").read_text()
            self.assertIn("seq_length=2 seq_position=1", sfz)
            self.assertIn("seq_length=2 seq_position=2", sfz)
            self.assertIn("lovel=0", sfz)
            self.assertEqual(len(report["garageband_alternates"]), 1)
            self.assertTrue(
                (output / "garageband-alternates/alternate-02.sf2").is_file()
            )
            self.assertTrue((output / "garageband-ab-audition.mid").is_file())
            self.assertTrue((output / "garageband-performance-ab.mid").is_file())
            self.assertTrue((output / "garageband-performance-source.wav").is_file())
            self.assertTrue((output / "garageband-velocity-sweep.mid").is_file())
            performance = report["performance_audition"]
            self.assertEqual(performance["bars"], 8)
            self.assertEqual(performance["note_count"], 16)
            self.assertEqual(performance["source_channel"], 9)
            self.assertEqual(performance["output_channel"], 0)
            self.assertEqual(performance["selected_pitches"], [36])
            self.assertEqual(performance["pitch_changes"], 0)
            self.assertEqual(performance["velocity_changes"], 0)
            self.assertFalse(performance["source_midi_mutated"])
            self.assertEqual(
                performance["source_reference_wav"],
                "garageband-performance-source.wav",
            )
            sweep = report["velocity_sweep"]
            self.assertEqual(sweep["status"], "audition-only")
            self.assertFalse(sweep["mapping_changed"])
            self.assertEqual(sweep["unit_count"], 1)
            boundary = sweep["units"][0]["accepted_boundary"]
            self.assertEqual(
                sweep["units"][0]["transition_pair"], [boundary, boundary + 1]
            )
            self.assertIn(boundary, sweep["units"][0]["velocities"])
            self.assertIn(boundary + 1, sweep["units"][0]["velocities"])

            second = root / "v3-repeat"
            second_report = apply_sample_pack_review(
                reviewed_path,
                out_dir=second,
                render_preview=False,
                instrument_name="Reviewed Kick",
            )
            self.assertEqual(
                report["soundfont"]["sha256"], second_report["soundfont"]["sha256"]
            )
            self.assertEqual(report["sfz"]["sha256"], second_report["sfz"]["sha256"])
            self.assertEqual(
                report["performance_audition"]["midi_sha256"],
                second_report["performance_audition"]["midi_sha256"],
            )
            self.assertEqual(
                report["performance_audition"]["source_reference_sha256"],
                second_report["performance_audition"]["source_reference_sha256"],
            )
            self.assertEqual(
                report["velocity_sweep"]["midi_sha256"],
                second_report["velocity_sweep"]["midi_sha256"],
            )

    def test_unreviewed_or_tampered_choices_cannot_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_pack = _write_v2_fixture(root)
            review_dir = root / "review"
            create_sample_pack_review(source_pack, out_dir=review_dir)
            seed_path = review_dir / "sample_pack_review.seed.json"

            with self.assertRaisesRegex(ValueError, "status 'reviewed'"):
                apply_sample_pack_review(
                    seed_path, out_dir=root / "unreviewed-output", render_preview=False
                )
            self.assertFalse((root / "unreviewed-output").exists())

            reviewed = json.loads(seed_path.read_text())
            reviewed["status"] = "reviewed"
            reviewed["units"][0]["decision"] = "reject"
            changed_audio = (
                review_dir
                / reviewed["units"][0]["layers"][0]["event_options"][0]["audio"]
            )
            original_audio = changed_audio.read_bytes()
            changed_audio.write_bytes(b"changed after review")
            changed_review = review_dir / "changed-audio.json"
            _write_json(changed_review, reviewed)
            with self.assertRaisesRegex(ValueError, "event audio changed"):
                apply_sample_pack_review(
                    changed_review,
                    out_dir=root / "changed-audio-output",
                    render_preview=False,
                )
            self.assertFalse((root / "changed-audio-output").exists())
            changed_audio.write_bytes(original_audio)

            reviewed["units"][0]["decision"] = "accept"
            for layer in reviewed["units"][0]["layers"]:
                layer["primary_event_index"] = 9999
                layer["accepted_event_indices"] = [9999]
            tampered = review_dir / "tampered.json"
            _write_json(tampered, reviewed)
            with self.assertRaisesRegex(ValueError, "not proposed"):
                apply_sample_pack_review(
                    tampered, out_dir=root / "tampered-output", render_preview=False
                )
            self.assertFalse((root / "tampered-output").exists())

    def test_pitched_review_uses_a_short_sampler_phrase(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_pack = _write_v2_fixture(root, kind="bass")
            review_dir = root / "review"

            seed = create_sample_pack_review(source_pack, out_dir=review_dir)

            policy = seed["review_evidence"]["context_policy"]
            self.assertEqual(policy["kind"], "bass")
            self.assertEqual(policy["bpm"], 120.0)
            self.assertEqual(policy["role_audition_mode"], "pitched-phrase")
            option = seed["units"][0]["layers"][0]["event_options"][0]
            role = option["context_audio"]["role_audition"]
            self.assertEqual(role["mode"], "pitched-phrase")
            self.assertTrue((review_dir / role["audio"]).is_file())
            self.assertIn(
                "Short sampler pitch phrase",
                (review_dir / "sample_pack_review.html").read_text(),
            )

    def test_boundary_review_requires_an_explicit_hash_pinned_choice(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_pack = _write_v2_fixture(root)
            review_dir = root / "sample-review"
            create_sample_pack_review(source_pack, out_dir=review_dir)
            sample_review = json.loads(
                (review_dir / "sample_pack_review.seed.json").read_text()
            )
            sample_review["status"] = "reviewed"
            sample_review["units"][0]["decision"] = "accept"
            for layer in sample_review["units"][0]["layers"]:
                primary = layer["candidate_event_indices"][0]
                layer["primary_event_index"] = primary
                layer["accepted_event_indices"] = [primary]
            sample_review_path = review_dir / "sample.reviewed.json"
            _write_json(sample_review_path, sample_review)
            source_v3 = root / "source-v3"
            source_report = apply_sample_pack_review(
                sample_review_path,
                out_dir=source_v3,
                render_preview=False,
                instrument_name="Boundary Fixture",
            )
            source_hash = _tree_hash(source_v3)

            boundary_dir = root / "boundary-review"
            seed = create_sample_boundary_review(
                source_v3, out_dir=boundary_dir, render_preview=False
            )

            self.assertEqual(seed["schema"], SAMPLE_BOUNDARY_REVIEW_SCHEMA)
            self.assertEqual(seed["status"], "unreviewed")
            self.assertEqual(seed["summary"]["review_unit_count"], 1)
            self.assertIsNone(seed["units"][0]["selected_mapping_id"])
            self.assertGreaterEqual(len(seed["units"][0]["candidates"]), 4)
            self.assertEqual(seed["units"][0]["candidates"][0]["mode"], "single-low")
            self.assertEqual(
                seed["units"][0]["candidates"][-1]["mode"], "single-high"
            )
            self.assertTrue(seed["units"][0]["source_midi_velocity_range"])
            self.assertTrue(seed["units"][0]["sweep_velocities"])
            tone = seed["units"][0]["tone_comparison"]
            self.assertTrue((boundary_dir / tone["midi"]).is_file())
            self.assertEqual(
                tone["pattern"],
                "repeated two-bar beat; one fixed MIDI pitch and velocity",
            )
            page = (boundary_dir / "sample_boundary_review.html").read_text()
            self.assertIn("Mark all mapping choices reviewed", page)
            self.assertIn("Same velocity, same repeated beat", page)
            self.assertIn("one source for every velocity", page)
            self.assertIn("deliberately not selected", page)
            self.assertEqual(_tree_hash(source_v3), source_hash)

            with self.assertRaisesRegex(ValueError, "status 'reviewed'"):
                apply_sample_boundary_review(
                    boundary_dir / "sample_boundary_review.seed.json",
                    out_dir=root / "unreviewed-boundary-output",
                    render_preview=False,
                )
            self.assertFalse((root / "unreviewed-boundary-output").exists())

            legacy_boundary = json.loads(
                (boundary_dir / "sample_boundary_review.seed.json").read_text()
            )
            legacy_boundary["schema"] = "sunofriend.sample-boundary-review.v1"
            legacy_boundary["status"] = "reviewed"
            legacy_path = boundary_dir / "legacy-boundary.reviewed.json"
            _write_json(legacy_path, legacy_boundary)
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                apply_sample_boundary_review(
                    legacy_path,
                    out_dir=root / "legacy-boundary-output",
                    render_preview=False,
                )

            reviewed = json.loads(
                (boundary_dir / "sample_boundary_review.seed.json").read_text()
            )
            reviewed["status"] = "reviewed"
            reviewed["units"][0]["selected_mapping_id"] = "single-low"
            reviewed["summary"]["reviewed_unit_count"] = 1
            reviewed["effects"]["layer_mappings_changed"] = 1
            boundary_review_path = boundary_dir / "boundary.reviewed.json"
            _write_json(boundary_review_path, reviewed)

            output = root / "boundary-applied-v3"
            report = apply_sample_boundary_review(
                boundary_review_path,
                out_dir=output,
                render_preview=False,
            )

            self.assertEqual(report["operation"], "sample-pack-boundary-apply")
            self.assertIsNone(report["accepted_units"][0]["velocity_boundary"])
            self.assertFalse(report["accepted_units"][0]["velocity_layers_applied"])
            self.assertEqual(len(report["accepted_units"][0]["layers"]), 1)
            self.assertEqual(report["effects"]["velocity_boundaries_changed"], 0)
            self.assertEqual(report["effects"]["velocity_layers_removed"], 1)
            self.assertEqual(report["effects"]["active_source_events_removed"], 1)
            self.assertEqual(report["effects"]["new_source_events_introduced"], 0)
            self.assertEqual(
                report["effects"]["source_samples_changed_by_boundary_review"], 0
            )
            self.assertEqual(report["boundary_review"]["changed_unit_count"], 1)
            self.assertEqual(report["boundary_review"]["velocity_layers_removed"], 1)
            self.assertIsNone(report["velocity_sweep"])
            self.assertTrue((output / "reviewed_boundary_decisions.json").is_file())
            self.assertEqual(_tree_hash(source_v3), source_hash)
            self.assertEqual(
                source_report["review"]["sha256"], report["review"]["sha256"]
            )

            layered_review = json.loads(
                (boundary_dir / "sample_boundary_review.seed.json").read_text()
            )
            layered_review["status"] = "reviewed"
            layered_review["summary"]["reviewed_unit_count"] = 1
            layered_candidate = next(
                row
                for row in layered_review["units"][0]["candidates"]
                if row["mode"] == "layered" and not row["is_current"]
            )
            layered_review["units"][0]["selected_mapping_id"] = layered_candidate[
                "mapping_id"
            ]
            layered_path = boundary_dir / "layered-boundary.reviewed.json"
            _write_json(layered_path, layered_review)
            layered_report = apply_sample_boundary_review(
                layered_path,
                out_dir=root / "layered-boundary-v3",
                render_preview=False,
            )
            self.assertEqual(
                layered_report["accepted_units"][0]["velocity_boundary"],
                layered_candidate["boundary"],
            )
            self.assertEqual(
                layered_report["effects"]["velocity_boundaries_changed"], 1
            )
            self.assertEqual(layered_report["effects"]["velocity_layers_removed"], 0)

            candidate = boundary_dir / reviewed["units"][0]["candidates"][0][
                "soundfont"
            ]
            candidate.write_bytes(candidate.read_bytes() + b"tampered")
            with self.assertRaisesRegex(ValueError, "boundary evidence changed"):
                apply_sample_boundary_review(
                    boundary_review_path,
                    out_dir=root / "tampered-boundary-output",
                    render_preview=False,
                )
            self.assertFalse((root / "tampered-boundary-output").exists())

    def test_legacy_review_without_context_audio_still_applies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_pack = _write_v2_fixture(root)
            review_dir = root / "review"
            create_sample_pack_review(source_pack, out_dir=review_dir)

            legacy = json.loads(
                (review_dir / "sample_pack_review.seed.json").read_text()
            )
            for unit in legacy["units"]:
                for layer in unit["layers"]:
                    for option in layer["event_options"]:
                        option.pop("context_audio")
            manifest_path = review_dir / "review_audio_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["files"] = [
                row for row in manifest["files"] if row["purpose"] == "isolated-event"
            ]
            manifest.pop("context_policy")
            _write_json(manifest_path, manifest)
            evidence = legacy["review_evidence"]
            evidence["manifest_sha256"] = _sha(manifest_path)
            evidence["audio_file_count"] = len(manifest["files"])
            evidence.pop("context_audio_file_count")
            evidence.pop("context_policy")
            evidence.pop("isolated_audio_file_count")
            legacy["status"] = "reviewed"
            legacy["units"][0]["decision"] = "accept"
            for layer in legacy["units"][0]["layers"]:
                primary = layer["candidate_event_indices"][0]
                layer["primary_event_index"] = primary
                layer["accepted_event_indices"] = [primary]
            reviewed = review_dir / "legacy.reviewed.json"
            _write_json(reviewed, legacy)

            report = apply_sample_pack_review(
                reviewed, out_dir=root / "v3", render_preview=False
            )

            self.assertEqual(report["status"], "complete")
            self.assertEqual(report["review"]["accepted_unit_count"], 1)


def _write_v2_fixture(root: Path, *, kind: str = "kick") -> Path:
    stem = root / "source.wav"
    midi = root / "source.mid"
    duration = 8.3
    audio = np.zeros(round(duration * SAMPLE_RATE), dtype=np.float32)
    notes = []
    events = []
    for index in range(16):
        start_seconds = index * 0.5
        end_seconds = start_seconds + 0.12
        amplitude = (
            0.08 + (index % 3) * 0.002 if index < 8 else 0.35 + (index % 3) * 0.004
        )
        start = round(start_seconds * SAMPLE_RATE)
        end = round(end_seconds * SAMPLE_RATE)
        times = np.arange(end - start, dtype=np.float32) / SAMPLE_RATE
        values = amplitude * np.sin(2.0 * np.pi * 80.0 * times)
        audio[start:end] = values.astype(np.float32)
        velocity = 48 + index % 3 if index < 8 else 108 + index % 3
        notes.append(NoteEvent(start_seconds, end_seconds, 36, velocity))
        events.append(
            {
                "event_index": index,
                "note_index": index,
                "start_seconds": start_seconds,
                "end_seconds": end_seconds,
                "duration_seconds": 0.12,
                "pitch": 36,
                "velocity": velocity,
                "rms": amplitude / np.sqrt(2.0),
                "isolated": True,
                "overlap_count": 0,
                "identity_candidate_cluster": "I1",
                "identity_distance_to_medoid": 0.05 + index * 0.01,
                "articulation_cluster": "A1",
                "identity_outlier": False,
                "timbre_vector": [0.1 + (index % 4) * 0.005] * 20,
            }
        )
    soundfile.write(stem, audio, SAMPLE_RATE)
    write_midi_file(
        midi,
        [
            MidiTrack(
                kind.title(),
                channel=9 if kind == "kick" else 0,
                program=0 if kind == "kick" else 33,
                notes=notes,
            )
        ],
        bpm=120.0,
    )
    source_record = {
        "path": str(stem.resolve()),
        "sha256": _sha(stem),
        "sample_rate": SAMPLE_RATE,
    }
    midi_record = {"path": str(midi.resolve()), "sha256": _sha(midi)}
    clusters = {
        "schema": "sunofriend.source-event-clusters.v1",
        "source": source_record,
        "midi": midi_record,
        "events": events,
    }
    dynamics = analyze_source_event_dynamics(clusters)

    pack = root / "sample-pack-v2"
    samples = pack / "samples"
    samples.mkdir(parents=True)
    sample = samples / "kick.wav"
    soundfile.write(sample, audio[: round(0.12 * SAMPLE_RATE)], SAMPLE_RATE)
    summary = write_soundfont(
        pack / "sunofriend-instrument.sf2",
        [SoundFontZone(sample, root_key=36, low_key=36, high_key=36)],
        name="Fixture Kick",
    ).to_dict()
    base_row = {
        "file": "samples/kick.wav",
        "pitch": 36,
        "low_key": 36,
        "high_key": 36,
        "low_velocity": 0,
        "high_velocity": 127,
        "velocity": 100,
        "tuning": {"pitch_correction_cents": 0, "status": "disabled"},
    }
    report = {
        "operation": "sample-pack",
        "format_version": 2,
        "status": "complete",
        "stem": str(stem.resolve()),
        "midi": str(midi.resolve()),
        "kind": kind,
        "sample_rate": SAMPLE_RATE,
        "auto_tune": False,
        "instrument_name": "Fixture Kick",
        "samples": [base_row],
        "soundfont": summary,
        "artifacts": {"soundfont": "sunofriend-instrument.sf2"},
    }
    _write_json(pack / "sample_pack.json", report)
    _write_json(pack / "source_event_clusters.json", clusters)
    _write_json(pack / "source_event_dynamics.json", dynamics)
    (pack / "source_event_dynamics.svg").write_text(source_event_dynamics_svg(dynamics))
    return pack


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(value for value in path.rglob("*") if value.is_file()):
        digest.update(str(item.relative_to(path)).encode())
        digest.update(item.read_bytes())
    return digest.hexdigest()


if __name__ == "__main__":
    unittest.main()
