from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from sunofriend.clip import read_midi_clips
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.midi_role_split import (
    create_midi_role_split,
    resolve_midi_role_split,
)
from sunofriend.models import NoteEvent


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MidiRoleSplitTests(unittest.TestCase):
    def _fixtures(self, root: Path) -> tuple[Path, Path, Path, Path]:
        primary = root / "primary.mid"
        secondary = root / "secondary.mid"
        source = root / "target.wav"
        source.write_bytes(b"RIFF-role-split-test")
        write_midi_file(
            primary,
            [
                MidiTrack(
                    "electric_bass",
                    0,
                    33,
                    [
                        NoteEvent(0.0, 0.5, 35, 90),
                        NoteEvent(0.5, 1.0, 33, 91),
                        NoteEvent(1.0, 1.15, 43, 92),
                        NoteEvent(1.2, 1.35, 54, 93),
                    ],
                )
            ],
            bpm=113,
        )
        write_midi_file(
            secondary,
            [
                MidiTrack(
                    "electric_bass",
                    0,
                    33,
                    [
                        NoteEvent(0.95, 1.15, 55, 80),
                        NoteEvent(0.95, 1.15, 43, 70),
                    ],
                )
            ],
            bpm=113,
        )
        clusters = root / "source_event_clusters.json"
        clusters.write_text(
            json.dumps(
                {
                    "schema": "sunofriend.source-event-clusters.v1",
                    "status": "complete",
                    "midi": {"path": str(primary), "sha256": _sha256(primary)},
                    "source": {"path": str(source), "sha256": _sha256(source)},
                    "summary": {
                        "source_event_count": 4,
                        "identity_candidate_cluster_count": 2,
                    },
                    "identity_candidate_clusters": [
                        {
                            "cluster_id": "I1",
                            "event_count": 2,
                            "event_indices": [0, 1],
                            "median_duration_seconds": 0.5,
                            "pitch_range": [33, 35],
                        },
                        {
                            "cluster_id": "I2",
                            "event_count": 1,
                            "event_indices": [2],
                            "median_duration_seconds": 0.15,
                            "pitch_range": [43, 43],
                        },
                    ],
                    "events": [
                        {
                            "note_index": 0,
                            "identity_candidate_cluster": "I1",
                            "identity_outlier": False,
                        },
                        {
                            "note_index": 1,
                            "identity_candidate_cluster": "I1",
                            "identity_outlier": False,
                        },
                        {
                            "note_index": 2,
                            "identity_candidate_cluster": "I2",
                            "identity_outlier": False,
                        },
                        {
                            "note_index": 3,
                            "identity_candidate_cluster": None,
                            "identity_outlier": True,
                        },
                    ],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return primary, secondary, source, clusters

    def test_split_preserves_primary_and_retains_independent_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary, secondary, source, clusters = self._fixtures(root)
            output = root / "split"
            report = create_midi_role_split(
                primary,
                clusters,
                out_dir=output,
                body_cluster="I1",
                secondary_midi_path=secondary,
                secondary_audio_path=source,
                render_preview=False,
            )

            self.assertEqual(report["status"], "review-required")
            self.assertEqual(report["evidence"]["body_note_count"], 2)
            self.assertEqual(report["evidence"]["primary_complement_note_count"], 2)
            self.assertEqual(report["evidence"]["primary_complement_outlier_count"], 1)
            self.assertEqual(report["evidence"]["secondary_note_count"], 2)
            self.assertEqual(
                report["evidence"]["secondary_maximum_simultaneous_notes"], 2
            )
            self.assertEqual(
                report["effects"]["primary_notes_changed_in_strict_partition"], 0
            )
            self.assertFalse(report["effects"]["automatic_role_selection"])
            self.assertFalse(report["physical_instrument_identified"])

            strict = read_midi_clips(output / "two-role-primary-partition.mid")
            independent = read_midi_clips(output / "two-role-independent-pluck.mid")
            self.assertEqual([len(clip.notes) for clip in strict], [2, 2])
            self.assertEqual([len(clip.notes) for clip in independent], [2, 2])
            primary_notes = read_midi_clips(primary)[0].notes
            strict_notes = tuple(note for clip in strict for note in clip.notes)
            self.assertEqual(
                sorted(
                    (note.start_beat, note.duration_beats, note.pitch, note.velocity)
                    for note in primary_notes
                ),
                sorted(
                    (note.start_beat, note.duration_beats, note.pitch, note.velocity)
                    for note in strict_notes
                ),
            )
            self.assertEqual(
                _sha256(output / "primary-unchanged.mid"), _sha256(primary)
            )
            seed = json.loads((output / "midi_role_split_review.json").read_text())
            self.assertEqual(seed["status"], "unreviewed")
            self.assertTrue(all(not choice["reviewed"] for choice in seed["choices"]))
            page = (output / "midi_role_split_review.html").read_text()
            self.assertIn("Export review JSON", page)
            self.assertIn("independent residual pluck", page)

            with self.assertRaisesRegex(FileExistsError, "already exists"):
                create_midi_role_split(
                    primary,
                    clusters,
                    out_dir=output,
                    body_cluster="I1",
                    render_preview=False,
                )

    def test_mismatched_evidence_is_rejected_before_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary, _, _, clusters = self._fixtures(root)
            document = json.loads(clusters.read_text())
            document["midi"]["sha256"] = "0" * 64
            clusters.write_text(json.dumps(document), encoding="utf-8")
            output = root / "rejected"

            with self.assertRaisesRegex(ValueError, "hash"):
                create_midi_role_split(
                    primary,
                    clusters,
                    out_dir=output,
                    body_cluster="I1",
                    render_preview=False,
                )
            self.assertFalse(output.exists())

    def test_review_hash_pins_the_cleanup_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary, _, source, clusters = self._fixtures(root)
            cleanup_report = root / "ai_cleanup.json"
            cleanup_report.write_text('{"status":"complete"}\n', encoding="utf-8")
            review = root / "ai_cleanup_review.reviewed.json"
            review.write_text(
                json.dumps(
                    {
                        "schema": "sunofriend.ai-cleanup-review.v1",
                        "status": "reviewed",
                        "overall_decision": "learned_target_main",
                        "overall_notes": "Two bass roles.",
                        "reviewed_at": "2026-07-18T19:12:37Z",
                        "experiment": {
                            "cleanup_report_sha256": _sha256(cleanup_report)
                        },
                        "choices": [{"id": "source", "reviewed": True}],
                    }
                ),
                encoding="utf-8",
            )

            report = create_midi_role_split(
                primary,
                clusters,
                out_dir=root / "reviewed",
                body_cluster="I1",
                cleanup_review_path=review,
                render_preview=False,
            )
            self.assertEqual(
                report["reviewed_cleanup"]["overall_decision"],
                "learned_target_main",
            )
            self.assertEqual(
                report["reviewed_cleanup"]["cleanup_report_sha256"],
                _sha256(cleanup_report),
            )
            self.assertEqual(
                report["inputs"]["cluster_source_audio"]["sha256"], _sha256(source)
            )

    def test_complete_review_resolves_to_an_exact_primary_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary, secondary, source, clusters = self._fixtures(root)
            role_split = root / "role-split"
            create_midi_role_split(
                primary,
                clusters,
                out_dir=role_split,
                body_cluster="I1",
                secondary_midi_path=secondary,
                secondary_audio_path=source,
                render_preview=False,
            )
            seed = json.loads((role_split / "midi_role_split_review.json").read_text())
            seed["status"] = "reviewed"
            seed["reviewed_at"] = "2026-07-18T19:46:51Z"
            seed["overall_decision"] = "keep_primary"
            for choice in seed["choices"]:
                choice["reviewed"] = True
                choice["role"] = "both"
                choice["usefulness"] = "main"
            reviewed = root / "reviewed.json"
            reviewed.write_text(json.dumps(seed), encoding="utf-8")

            resolved = resolve_midi_role_split(
                reviewed,
                role_split,
                out_dir=root / "resolved",
            )

            self.assertEqual(resolved["status"], "complete")
            self.assertEqual(resolved["decision"], "keep_primary")
            self.assertEqual(resolved["selection_source"], "explicit-user-review")
            self.assertEqual(
                _sha256(root / "resolved" / "recommended.mid"), _sha256(primary)
            )
            self.assertEqual(resolved["effects"]["recommended_midi_notes_changed"], 0)
            self.assertFalse(resolved["effects"]["instrument_selected"])
            self.assertTrue((root / "resolved" / "RECOMMENDATION.md").is_file())

            with self.assertRaisesRegex(FileExistsError, "already exists"):
                resolve_midi_role_split(
                    reviewed,
                    role_split,
                    out_dir=root / "resolved",
                )

    def test_resolution_rejects_tampered_source_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary, _, _, clusters = self._fixtures(root)
            role_split = root / "role-split"
            create_midi_role_split(
                primary,
                clusters,
                out_dir=role_split,
                body_cluster="I1",
                render_preview=False,
            )
            seed = json.loads((role_split / "midi_role_split_review.json").read_text())
            seed["status"] = "reviewed"
            seed["overall_decision"] = "keep_primary"
            for choice in seed["choices"]:
                choice.update(reviewed=True, role="both", usefulness="main")
            reviewed = root / "reviewed.json"
            reviewed.write_text(json.dumps(seed), encoding="utf-8")
            (role_split / "body.mid").write_bytes(b"tampered")

            with self.assertRaisesRegex(ValueError, "artifact (size|hash) changed"):
                resolve_midi_role_split(
                    reviewed,
                    role_split,
                    out_dir=root / "rejected-resolution",
                )
            self.assertFalse((root / "rejected-resolution").exists())

    def test_review_pins_and_resolves_the_strict_partition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary, _, _, clusters = self._fixtures(root)
            role_split = root / "role-split"
            create_midi_role_split(
                primary,
                clusters,
                out_dir=role_split,
                body_cluster="I1",
                render_preview=False,
            )
            seed = json.loads((role_split / "midi_role_split_review.json").read_text())
            seed["status"] = "reviewed"
            seed["overall_decision"] = "strict_partition"
            for choice in seed["choices"]:
                choice.update(reviewed=True, role="both", usefulness="main")
            reviewed = root / "reviewed.json"
            reviewed.write_text(json.dumps(seed), encoding="utf-8")

            resolved = resolve_midi_role_split(
                reviewed,
                role_split,
                out_dir=root / "resolved",
            )

            self.assertEqual(resolved["decision"], "strict_partition")
            self.assertEqual(
                _sha256(root / "resolved" / "recommended.mid"),
                _sha256(role_split / "two-role-primary-partition.mid"),
            )

    def test_resolution_rejects_an_unpinned_legacy_challenger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary, _, _, clusters = self._fixtures(root)
            role_split = root / "role-split"
            create_midi_role_split(
                primary,
                clusters,
                out_dir=role_split,
                body_cluster="I1",
                render_preview=False,
            )
            seed = json.loads((role_split / "midi_role_split_review.json").read_text())
            seed["status"] = "reviewed"
            seed["overall_decision"] = "strict_partition"
            del seed["experiment"]["candidate_midi_sha256"]
            for choice in seed["choices"]:
                choice.update(reviewed=True, role="both", usefulness="main")
            reviewed = root / "reviewed.json"
            reviewed.write_text(json.dumps(seed), encoding="utf-8")

            source_seed = role_split / "midi_role_split_review.json"
            source = json.loads(source_seed.read_text())
            del source["experiment"]["candidate_midi_sha256"]
            source_seed.write_text(json.dumps(source), encoding="utf-8")
            source_report_path = role_split / "midi_role_split.json"
            source_report = json.loads(source_report_path.read_text())
            seed_record = source_report["artifacts"]["midi_role_split_review.json"]
            seed_record["bytes"] = source_seed.stat().st_size
            seed_record["sha256"] = _sha256(source_seed)
            source_report_path.write_text(json.dumps(source_report), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "does not pin"):
                resolve_midi_role_split(
                    reviewed,
                    role_split,
                    out_dir=root / "rejected-resolution",
                )


if __name__ == "__main__":
    unittest.main()
