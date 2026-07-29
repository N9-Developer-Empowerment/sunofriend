from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from sunofriend.listen_all import run_listen_all
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.pipeline import run_remake
from sunofriend.source_project import (
    SourceMetadata,
    SourcePart,
    build_source_project,
    load_prepared_project_context,
    write_source_project,
)
from sunofriend.source_receipt import canonical_json_bytes, document_sha256
from sunofriend.workbench_catalog import build_workbench_catalog


class PreparedProjectMetadataTests(unittest.TestCase):
    def test_absent_manifest_leaves_legacy_metadata_inference_available(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = (
                Path(temporary) / "Legacy Song-G major-150bpm-442hz"
            )
            project.mkdir()
            (project / "Legacy-bass-source.wav").write_bytes(b"RIFF-bass")

            self.assertIsNone(load_prepared_project_context(project))

            catalog = build_workbench_catalog(project)
            self.assertEqual(
                catalog["setup"],
                {
                    "bpm": 150.0,
                    "key": "G major",
                    "tuning_hz": 442.0,
                    "downbeat": None,
                    "files": [],
                },
            )

    def test_manifest_metadata_and_chord_evidence_are_authoritative(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = (
                Path(temporary) / "Wrong Name-C major-90bpm-432hz"
            )
            project.mkdir()
            chord = _write_prepared_manifest(
                project,
                metadata=SourceMetadata("B minor", 113.0, 440.0),
            )

            context = load_prepared_project_context(project)

            self.assertIsNotNone(context)
            assert context is not None
            self.assertEqual(context.metadata.key, "B minor")
            self.assertEqual(context.metadata.bpm, 113.0)
            self.assertEqual(context.metadata.tuning_hz, 440.0)
            self.assertEqual(context.chord_document, chord.resolve())

    def test_invalid_manifest_fails_closed_instead_of_falling_back(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = (
                Path(temporary) / "Fallback-G major-150bpm-440hz"
            )
            manifest = project / "INPUT/source-project.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text('{"schema": "wrong"}', encoding="utf-8")

            with self.assertRaisesRegex(
                ValueError, "unsupported source-project schema"
            ):
                build_workbench_catalog(project)

    def test_metadata_types_are_strict_even_with_a_matching_project_id(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "Prepared"
            project.mkdir()
            _write_prepared_manifest(
                project,
                metadata=SourceMetadata("B minor", 113.0, 440.0),
                include_chord=False,
            )
            manifest = project / "INPUT/source-project.json"
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document["metadata"]["bpm"] = True
            seed = {
                key: value
                for key, value in document.items()
                if key != "project_id"
            }
            document["project_id"] = f"sha256:{document_sha256(seed)}"
            manifest.write_bytes(canonical_json_bytes(document))

            with self.assertRaisesRegex(
                ValueError, "metadata.bpm.*finite positive"
            ):
                load_prepared_project_context(project)

    def test_changed_chord_document_fails_hash_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "Prepared"
            project.mkdir()
            chord = _write_prepared_manifest(
                project,
                metadata=SourceMetadata("B minor", 119.5, 440.0),
            )
            changed = bytearray(chord.read_bytes())
            changed[-1] ^= 1
            chord.write_bytes(changed)

            with self.assertRaisesRegex(
                ValueError, "hash does not match"
            ):
                load_prepared_project_context(project)

    def test_workbench_metadata_changes_without_changing_artifact_ids_or_order(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = (
                root / "Prepared-C major-120bpm-442hz"
            )
            candidates = root / "candidates"
            project.mkdir()
            candidates.mkdir()
            (project / "Prepared-bass-source.wav").write_bytes(b"RIFF-bass")
            for name, pitch in (
                ("bass-alpha.mid", 35),
                ("bass-zeta.mid", 38),
            ):
                write_midi_file(
                    candidates / name,
                    [
                        MidiTrack(
                            "Bass",
                            0,
                            38,
                            [NoteEvent(0.0, 0.5, pitch, 90)],
                        )
                    ],
                    bpm=120.0,
                )

            legacy = build_workbench_catalog(
                project, candidate_roots=[candidates]
            )
            chord = _write_prepared_manifest(
                project,
                metadata=SourceMetadata("B minor", 119.5, 440.0),
            )
            prepared = build_workbench_catalog(
                project, candidate_roots=[candidates]
            )

            self.assertEqual(prepared["setup"]["bpm"], 119.5)
            self.assertEqual(prepared["setup"]["key"], "B minor")
            self.assertEqual(prepared["setup"]["tuning_hz"], 440.0)
            self.assertEqual(
                prepared["setup"]["files"][0]["path"],
                str(chord.resolve()),
            )
            self.assertEqual(prepared["project_id"], legacy["project_id"])
            self.assertEqual(
                [stem["stem_id"] for stem in prepared["stems"]],
                [stem["stem_id"] for stem in legacy["stems"]],
            )
            self.assertEqual(
                [
                    candidate["candidate_id"]
                    for candidate in prepared["stems"][0]["candidates"]
                ],
                [
                    candidate["candidate_id"]
                    for candidate in legacy["stems"][0]["candidates"]
                ],
            )

    def test_listen_all_uses_manifest_metadata_and_exact_chord_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Prepared"
            project.mkdir()
            (project / "Prepared-bass-source.wav").touch()
            stray = project / "A_chords.pdf"
            stray.write_bytes(b"stray")
            chord = _write_prepared_manifest(
                project,
                metadata=SourceMetadata("B minor", 113.0, 440.0),
            )

            with patch(
                "sunofriend.listen_all._is_silent", return_value=True
            ):
                summary = run_listen_all(
                    project,
                    root / "out",
                    evaluate_outputs=False,
                    progress=lambda _message: None,
                )

            self.assertEqual(summary["bpm_nominal"], 113.0)
            self.assertEqual(summary["key"], "B minor")
            self.assertEqual(summary["tuning_hz"], 440.0)
            self.assertEqual(summary["chords_pdf"], str(chord.resolve()))

    def test_pipeline_uses_manifest_metadata_and_nested_chord_document(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Prepared"
            project.mkdir()
            _write_pulse_wav(project / "Prepared-bass-source.wav")
            chord = _write_prepared_manifest(
                project,
                metadata=SourceMetadata("B minor", 113.0, 440.0),
            )
            (project / "Wrong_chords.pdf").write_bytes(b"not a chart")

            result = run_remake(project, root / "out")

            self.assertEqual(result.report["metadata"]["key"], "B minor")
            self.assertEqual(result.report["metadata"]["bpm"], 113.0)
            self.assertEqual(result.report["metadata"]["tuning_hz"], 440.0)
            self.assertEqual(chord.parent.name, "context")

    def test_pipeline_accepts_declared_plain_text_chord_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "Prepared"
            project.mkdir()
            _write_pulse_wav(project / "Prepared-bass-source.wav")
            chord = _write_prepared_manifest(
                project,
                metadata=SourceMetadata("B minor", 113.0, 440.0),
                chord_suffix=".txt",
            )

            result = run_remake(project, root / "out")

            self.assertEqual(result.report["metadata"]["key"], "B minor")
            self.assertEqual(result.report["metadata"]["bpm"], 113.0)
            self.assertEqual(chord.suffix, ".txt")


def _write_prepared_manifest(
    project: Path,
    *,
    metadata: SourceMetadata,
    include_chord: bool = True,
    chord_suffix: str = ".pdf",
) -> Path:
    chord = project / f"INPUT/context/declared-chords{chord_suffix}"
    chord_record = None
    if include_chord:
        chord.parent.mkdir(parents=True, exist_ok=True)
        if chord_suffix == ".txt":
            chord.write_text(
                "Key: B minor\nBm | G | D | A\n",
                encoding="utf-8",
            )
        else:
            chord.write_bytes(
                b"(Key: B minor) Tj\n"
                b"(Bm    G    D    A) Tj\n"
                b"(Chords generated with Moises.ai) Tj\n"
            )
        chord_record = {
            "name": f"Declared chords{chord_suffix}",
            "path": f"INPUT/context/declared-chords{chord_suffix}",
            "sha256": hashlib.sha256(chord.read_bytes()).hexdigest(),
            "bytes": chord.stat().st_size,
        }
    source = SourcePart(
        source_id=f"sha256:{'1' * 64}",
        role="bass",
        original_name="bass.flac",
        original_path="INPUT/original/bass.flac",
        canonical_path="Prepared-bass-source.wav",
        receipt_path="INPUT/receipts/bass.json",
    )
    manifest = build_source_project(
        title="Prepared",
        metadata=metadata,
        rights_category="owned",
        source=source,
        chord_document=chord_record,
    )
    write_source_project(project / "INPUT/source-project.json", manifest)
    return chord


def _write_pulse_wav(path: Path) -> None:
    sample_rate = 8000
    total_frames = int(3.2 * sample_rate)
    samples = [0] * total_frames
    for pulse in (0.0, 0.8, 1.6, 2.4):
        start = int(pulse * sample_rate)
        for index in range(start, min(total_frames, start + 320)):
            samples[index] = 10000
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(
            b"".join(
                sample.to_bytes(2, "little", signed=True)
                for sample in samples
            )
        )


if __name__ == "__main__":
    unittest.main()
