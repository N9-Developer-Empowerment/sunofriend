from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sunofriend.workbench_catalog import build_workbench_catalog, public_catalog
from sunofriend.workbench_phrase_links import (
    WORKBENCH_PHRASE_REVIEW_LINK_SCHEMA,
    build_workbench_phrase_review_link,
)


def _record(path: Path, *, relative: str | None = None) -> dict[str, object]:
    payload = path.read_bytes()
    return {
        "path": relative if relative is not None else str(path.resolve()),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


class _Fixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.allowed = root / "allowed"
        self.review_root = self.allowed / "phrase-review"
        self.review_root.mkdir(parents=True)
        self.source = root / "project" / "lead.wav"
        self.source.parent.mkdir()
        self.source.write_bytes(b"current exact lead source")
        self.candidates: dict[str, Path] = {}
        for lane in ("S0", "M1", "M3"):
            path = self.allowed / "midi" / f"{lane}.mid"
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(f"distinct {lane} MIDI".encode())
            self.candidates[lane] = path

        self.artifact_paths: list[str] = []
        self.phrases: list[dict[str, object]] = []
        for index, (start, end) in enumerate(((0.5, 1.5), (2.0, 3.0)), start=1):
            token = f"unit-{index:02d}"
            source_audio = f"audio/{token}-source.wav"
            midi_audio = f"audio/{token}-combined.wav"
            overlay_audio = f"audio/{token}-combined-source-plus-midi.wav"
            midi = f"midi/{token}-combined.mid"
            evaluation = f"evaluation/{token}-combined.json"
            for relative, payload in (
                (source_audio, b"source excerpt"),
                (midi_audio, b"MIDI only WAV"),
                (overlay_audio, b"overlay WAV"),
                (midi, b"phrase MIDI"),
                (evaluation, b"{}"),
            ):
                path = self.review_root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload + str(index).encode())
                self.artifact_paths.append(relative)
            self.phrases.append(
                {
                    "phrase_index": index - 1,
                    "start_seconds": start,
                    "end_seconds": end,
                    "duration_seconds": 1.0,
                    "window_start_seconds": start - 0.25,
                    "window_end_seconds": end + 0.25,
                    "source_audio": source_audio,
                    "alternative_names": ["combined"],
                    "alternatives": {
                        "combined": {
                            "label": "Combined",
                            "note_count": 2,
                            "midi": midi,
                            "audio": midi_audio,
                            "overlay_audio": overlay_audio,
                            "evaluation": evaluation,
                        }
                    },
                }
            )
        self.html = self.review_root / "melody_phrase_review.html"
        self.html.write_text(
            '<!doctype html><h1>Review</h1><section id="phrase-0"></section>'
            '<section id="phrase-1"></section>',
            encoding="utf-8",
        )
        self.artifact_paths.append(self.html.name)
        self.extra = self.review_root / "private-diagnostic.json"
        self.extra.write_text("{}", encoding="utf-8")
        self.artifact_paths.append(self.extra.name)

        source_record = _record(self.source)
        self.review: dict[str, object] = {
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
            "review_unit_count": 2,
            "phrase_count": 2,
            "alternative_names": ["combined"],
            "phrases": self.phrases,
            "html": self.html.name,
            "artifacts": {
                relative: _record(self.review_root / relative, relative=relative)
                for relative in sorted(self.artifact_paths)
            },
        }
        self.review_path = self.review_root / "phrase_review.json"
        self._write_review()

        midi_rows = []
        for lane in ("S0", "M1", "M3"):
            midi_rows.append(
                {
                    "lane": lane,
                    "midi": {
                        key: value
                        for key, value in _record(self.candidates[lane]).items()
                        if key != "path"
                    },
                    "duplicate_evidence": {"group_count": 0, "groups": []},
                }
            )
        pairwise = [
            {
                "left_lane": "S0",
                "right_lane": "M1",
                "per_phrase": [
                    {
                        "phrase_index": 0,
                        "cross_phrase_boundary_matches": 1,
                        "same_pitch_boundary_duration_disputes": 0,
                        "octave_equivalent_onset_disputes": 0,
                        "S0_only_notes": 1,
                        "M1_only_notes": 1,
                    },
                    {
                        "phrase_index": 1,
                        "cross_phrase_boundary_matches": 0,
                        "same_pitch_boundary_duration_disputes": 0,
                        "octave_equivalent_onset_disputes": 0,
                        "S0_only_notes": 0,
                        "M1_only_notes": 1,
                    },
                ],
            },
            {
                "left_lane": "S0",
                "right_lane": "M3",
                "per_phrase": [
                    {
                        "phrase_index": 0,
                        "cross_phrase_boundary_matches": 0,
                        "same_pitch_boundary_duration_disputes": 1,
                        "octave_equivalent_onset_disputes": 0,
                        "S0_only_notes": 0,
                        "M3_only_notes": 0,
                    },
                    {
                        "phrase_index": 1,
                        "cross_phrase_boundary_matches": 0,
                        "same_pitch_boundary_duration_disputes": 0,
                        "octave_equivalent_onset_disputes": 0,
                        "S0_only_notes": 0,
                        "M3_only_notes": 0,
                    },
                ],
            },
            {
                "left_lane": "M1",
                "right_lane": "M3",
                "per_phrase": [
                    {
                        "phrase_index": 0,
                        "cross_phrase_boundary_matches": 0,
                        "same_pitch_boundary_duration_disputes": 0,
                        "octave_equivalent_onset_disputes": 0,
                        "M1_only_notes": 0,
                        "M3_only_notes": 0,
                    },
                    {
                        "phrase_index": 1,
                        "cross_phrase_boundary_matches": 0,
                        "same_pitch_boundary_duration_disputes": 0,
                        "octave_equivalent_onset_disputes": 1,
                        "M1_only_notes": 0,
                        "M3_only_notes": 1,
                    },
                ],
            },
        ]
        review_identity = _record(self.review_path)
        self.report: dict[str, object] = {
            "schema": "sunofriend.hybrid-candidate-report.v1",
            "status": "diagnostic-only",
            "role": "lead",
            "bpm": 120.0,
            "source": {
                key: value for key, value in source_record.items() if key != "path"
            },
            "phrase_review": {
                "schema": "sunofriend.melody-phrase-review.v1",
                "review_unit_count": 2,
                "bytes": review_identity["bytes"],
                "sha256": review_identity["sha256"],
            },
            "candidates": midi_rows,
            "phrases": [
                {
                    "phrase_index": 0,
                    "start_seconds": 0.5,
                    "end_seconds": 1.5,
                    "duration_seconds": 1.0,
                },
                {
                    "phrase_index": 1,
                    "start_seconds": 2.0,
                    "end_seconds": 3.0,
                    "duration_seconds": 1.0,
                },
            ],
            "pairwise": pairwise,
            "ranked_disagreement_phrases": [
                {
                    "phrase_index": 0,
                    "start_seconds": 0.5,
                    "end_seconds": 1.5,
                    "duration_seconds": 1.0,
                    "disagreement_evidence_count": 4,
                    "cross_phrase_boundary_match_references": 1,
                    "same_pitch_boundary_duration_disputes": 1,
                    "octave_equivalent_onset_disputes": 0,
                    "lane_only_note_references": 2,
                    "duplicate_groups": 0,
                },
                {
                    "phrase_index": 1,
                    "start_seconds": 2.0,
                    "end_seconds": 3.0,
                    "duration_seconds": 1.0,
                    "disagreement_evidence_count": 3,
                    "cross_phrase_boundary_match_references": 0,
                    "same_pitch_boundary_duration_disputes": 0,
                    "octave_equivalent_onset_disputes": 1,
                    "lane_only_note_references": 2,
                    "duplicate_groups": 0,
                },
            ],
            "lineage": {
                "comparison_source": {"status": "hash-and-size-verified"},
                "M1_full_mix_association": {
                    "status": "caller-supplied-derivation-unverified"
                },
                "M3_original_source_midi": {
                    "status": "manifest-claimed-payload-unverified"
                },
            },
            "interpretation": {
                "agreement_is_accuracy": False,
                "source_support_is_selection": False,
                "octave_equivalence_is_agreement": False,
                "ranking_is_preference": False,
                "review_required_before_hybrid_midi": True,
                "m1_same_song_derivation_verified": False,
                "m3_original_source_midi_payload_verified": False,
            },
            "effects": {
                "ai_inference_runs": 0,
                "midi_files_created": 0,
                "midi_notes_mutated": 0,
                "source_audio_mutated": False,
                "raw_candidates_mutated": False,
                "automatic_selection": False,
                "automatic_promotion": False,
                "default_changed": False,
            },
        }
        self.report_path = self.allowed / "hybrid-report.json"
        self._write_report()
        self.stem = {
            "stem_id": "stem-lead-001",
            "source_path": str(self.source),
            "source": _record(self.source),
            "candidates": [
                {
                    "candidate_id": f"candidate-{lane.lower()}",
                    "midi_path": str(path),
                    "midi": _record(path),
                }
                for lane, path in self.candidates.items()
            ],
        }

    def _write_review(self) -> None:
        self.review_path.write_text(
            json.dumps(self.review, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def sync_review(self) -> None:
        self._write_review()
        identity = _record(self.review_path)
        review_record = self.report["phrase_review"]
        assert isinstance(review_record, dict)
        review_record["bytes"] = identity["bytes"]
        review_record["sha256"] = identity["sha256"]
        self._write_report()

    def _write_report(self) -> None:
        self.report_path.write_text(
            json.dumps(self.report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def build(self) -> dict[str, object]:
        return build_workbench_phrase_review_link(
            self.stem,
            self.report_path,
            self.review_path,
            allowed_candidate_roots=[self.allowed],
        )

    def catalog_document(self) -> dict[str, object]:
        return {
            "schema": "sunofriend.workbench-catalog.v1",
            "stems": [
                {
                    "source": str(self.source),
                    "role": "vocals",
                    "candidates": [
                        {"midi": str(self.candidates[lane])}
                        for lane in ("S0", "M1", "M3")
                    ],
                    "phrase_review_link": {
                        "hybrid_report": str(self.report_path),
                        "phrase_review_manifest": str(self.review_path),
                    },
                }
            ],
        }

    def write_catalog(self, document: dict[str, object] | None = None) -> Path:
        path = self.root / "workbench-catalog.json"
        path.write_text(
            json.dumps(document or self.catalog_document(), indent=2) + "\n",
            encoding="utf-8",
        )
        return path


class WorkbenchPhraseReviewLinkTests(unittest.TestCase):
    def test_builds_path_free_projection_and_narrow_media_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            before = {
                path: path.read_bytes()
                for path in fixture.root.rglob("*")
                if path.is_file()
            }

            result = fixture.build()

            public = result["public"]
            self.assertEqual(public["schema"], WORKBENCH_PHRASE_REVIEW_LINK_SCHEMA)
            self.assertEqual(public["stem_id"], "stem-lead-001")
            self.assertEqual(list(public["candidate_map"]), ["S0", "M1", "M3"])
            self.assertEqual(
                [row["diagnostic_reference_count"] for row in public["ranges"]],
                [4, 3],
            )
            self.assertEqual(public["phrase_review"]["alternative_names"], ["combined"])
            self.assertEqual(result["entrypoint"], "melody_phrase_review.html")
            self.assertEqual(len(result["files"]), 7)
            self.assertEqual(
                {record["media_kind"] for record in result["files"].values()},
                {"html", "audio"},
            )
            self.assertFalse(
                any(
                    relative.endswith((".json", ".mid", ".midi"))
                    for relative in result["files"]
                )
            )
            self.assertNotIn(str(fixture.root), json.dumps(public, sort_keys=True))
            self.assertNotIn("path", json.dumps(public, sort_keys=True).lower())
            self.assertRegex(public["link_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(
                before,
                {
                    path: path.read_bytes()
                    for path in fixture.root.rglob("*")
                    if path.is_file()
                },
            )

    def test_accepts_a_guide_assisted_alternative_on_only_its_guided_unit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            phrase = fixture.review["phrases"][0]
            phrase["alternative_names"].append("guide-assisted")
            records = {
                "midi": "midi/unit-01-guide-assisted.mid",
                "audio": "audio/unit-01-guide-assisted.wav",
                "overlay_audio": "audio/unit-01-guide-assisted-source-plus-midi.wav",
                "evaluation": "evaluation/unit-01-guide-assisted.json",
            }
            for name, relative in records.items():
                path = fixture.review_root / relative
                path.write_bytes(f"guided {name}".encode())
                fixture.review["artifacts"][relative] = _record(path, relative=relative)
            phrase["alternatives"]["guide-assisted"] = {
                "label": "Guide assisted",
                "note_count": 2,
                **records,
            }
            fixture.review["alternative_names"].append("guide-assisted")
            fixture.sync_review()

            result = fixture.build()

            self.assertEqual(len(result["files"]), 9)
            self.assertIn(records["audio"], result["files"])
            self.assertNotIn(records["midi"], result["files"])

    def test_rejects_a_private_path_disguised_as_an_alternative_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            fixture.review["alternative_names"].append("/Users/alice/private-guide.wav")
            fixture.sync_review()

            with self.assertRaisesRegex(ValueError, "alternative name is invalid"):
                fixture.build()

    def test_requires_explicit_documents_and_candidate_midi_inside_allowed_roots(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            outside = fixture.root / "outside.json"
            outside.write_bytes(fixture.report_path.read_bytes())
            with self.assertRaisesRegex(ValueError, "allowed candidate roots"):
                build_workbench_phrase_review_link(
                    fixture.stem,
                    outside,
                    fixture.review_path,
                    allowed_candidate_roots=[fixture.allowed],
                )

            moved = fixture.root / "outside.mid"
            moved.write_bytes(fixture.candidates["S0"].read_bytes())
            candidate = fixture.stem["candidates"][0]
            candidate["midi_path"] = str(moved)
            candidate["midi"] = _record(moved)
            with self.assertRaisesRegex(ValueError, "allowed candidate roots"):
                fixture.build()

    def test_rejects_absolute_parent_and_unpinned_phrase_artifact_paths(self) -> None:
        for invalid in ("/tmp/escape.wav", "../escape.wav", "audio/./escape.wav"):
            with (
                self.subTest(invalid=invalid),
                tempfile.TemporaryDirectory() as directory,
            ):
                fixture = _Fixture(Path(directory))
                fixture.review["phrases"][0]["source_audio"] = invalid
                fixture.sync_review()
                with self.assertRaisesRegex(ValueError, "path"):
                    fixture.build()

        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            fixture.review["phrases"][0]["source_audio"] = "audio/unpinned.wav"
            fixture.sync_review()
            with self.assertRaisesRegex(ValueError, "not pinned"):
                fixture.build()

    def test_validates_every_manifest_artifact_including_unexposed_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            fixture.extra.write_text('{"changed":true}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "artifact changed"):
                fixture.build()

    def test_rejects_a_phrase_page_without_every_review_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            fixture.html.write_text(
                '<!doctype html><section id="phrase-0"></section>',
                encoding="utf-8",
            )
            fixture.review["artifacts"][fixture.html.name] = _record(
                fixture.html, relative=fixture.html.name
            )
            fixture.sync_review()
            with self.assertRaisesRegex(ValueError, "no phrase-1 anchor"):
                fixture.build()

    def test_rejects_source_candidate_and_review_identity_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            fixture.source.write_bytes(b"source drift")
            with self.assertRaisesRegex(ValueError, "source changed"):
                fixture.build()

        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            fixture.candidates["M1"].write_bytes(b"candidate drift")
            with self.assertRaisesRegex(ValueError, "candidate MIDI changed"):
                fixture.build()

        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            review_record = fixture.report["phrase_review"]
            assert isinstance(review_record, dict)
            review_record["sha256"] = "0" * 64
            fixture._write_report()
            with self.assertRaisesRegex(ValueError, "does not pin"):
                fixture.build()

    def test_rejects_non_diagnostic_lineage_or_effect_contracts(self) -> None:
        cases = (
            ("status", "complete"),
            ("automatic_selection", True),
            ("automatic_selection", 0),
            ("M1_full_mix_association", "verified"),
        )
        for field, value in cases:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                fixture = _Fixture(Path(directory))
                if field == "status":
                    fixture.report["status"] = value
                elif field == "automatic_selection":
                    effects = fixture.report["effects"]
                    assert isinstance(effects, dict)
                    effects[field] = value
                else:
                    lineage = fixture.report["lineage"]
                    assert isinstance(lineage, dict)
                    record = lineage[field]
                    assert isinstance(record, dict)
                    record["status"] = value
                fixture._write_report()
                with self.assertRaises(ValueError):
                    fixture.build()

    def test_rejects_phrase_geometry_and_ranked_count_inconsistency(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            fixture.review["phrases"][1]["phrase_index"] = 2
            fixture.sync_review()
            with self.assertRaisesRegex(ValueError, "contiguous from zero"):
                fixture.build()

        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            phrases = fixture.report["phrases"]
            assert isinstance(phrases, list)
            phrases[0]["start_seconds"] = 0.500000001
            fixture._write_report()
            with self.assertRaisesRegex(ValueError, "geometry"):
                fixture.build()

        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            ranked = fixture.report["ranked_disagreement_phrases"]
            assert isinstance(ranked, list)
            ranked[0]["disagreement_evidence_count"] = 5
            fixture._write_report()
            with self.assertRaisesRegex(ValueError, "count"):
                fixture.build()

    def test_rejects_file_drift_during_projection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            from sunofriend import workbench_phrase_links

            original = workbench_phrase_links._ranked_ranges

            def mutate(*args, **kwargs):
                result = original(*args, **kwargs)
                fixture.candidates["S0"].write_bytes(b"changed after mapping")
                return result

            with (
                mock.patch(
                    "sunofriend.workbench_phrase_links._ranked_ranges",
                    side_effect=mutate,
                ),
                self.assertRaisesRegex(ValueError, "changed during verification"),
            ):
                fixture.build()

    def test_duplicate_current_candidate_mapping_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            duplicate = copy.deepcopy(fixture.stem["candidates"][0])
            duplicate["candidate_id"] = "candidate-s0-duplicate"
            fixture.stem["candidates"].append(duplicate)
            with self.assertRaisesRegex(ValueError, "map uniquely"):
                fixture.build()

    def test_explicit_catalog_link_builds_a_path_free_public_projection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            catalog = build_workbench_catalog(
                fixture.source.parent,
                candidate_roots=[fixture.allowed],
                catalog_path=fixture.write_catalog(),
            )

            self.assertIn("_phrase_review_link", catalog["stems"][0])
            public = public_catalog(catalog)
            public_link = public["stems"][0]["phrase_review_link"]
            self.assertEqual(public_link["schema"], WORKBENCH_PHRASE_REVIEW_LINK_SCHEMA)
            self.assertEqual(len(public_link["ranges"]), 2)
            self.assertEqual(set(public_link["candidate_map"]), {"S0", "M1", "M3"})
            self.assertNotIn(str(fixture.root), json.dumps(public, sort_keys=True))
            self.assertNotIn("_phrase_review_link", json.dumps(public, sort_keys=True))

    def test_catalog_phrase_link_is_explicit_and_root_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            document = fixture.catalog_document()
            document["stems"][0].pop("phrase_review_link")
            catalog = build_workbench_catalog(
                fixture.source.parent,
                candidate_roots=[fixture.allowed],
                catalog_path=fixture.write_catalog(document),
            )
            self.assertNotIn("_phrase_review_link", catalog["stems"][0])
            self.assertNotIn("phrase_review_link", public_catalog(catalog)["stems"][0])

        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            document = fixture.catalog_document()
            link = document["stems"][0]["phrase_review_link"]
            link["unexpected"] = True
            with self.assertRaisesRegex(ValueError, "must contain exactly"):
                build_workbench_catalog(
                    fixture.source.parent,
                    candidate_roots=[fixture.allowed],
                    catalog_path=fixture.write_catalog(document),
                )

        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory))
            outside = fixture.root / "outside-report.json"
            outside.write_bytes(fixture.report_path.read_bytes())
            document = fixture.catalog_document()
            link = document["stems"][0]["phrase_review_link"]
            link["hybrid_report"] = str(outside)
            with self.assertRaisesRegex(ValueError, "outside the explicit local"):
                build_workbench_catalog(
                    fixture.source.parent,
                    candidate_roots=[fixture.allowed],
                    catalog_path=fixture.write_catalog(document),
                )


if __name__ == "__main__":
    unittest.main()
