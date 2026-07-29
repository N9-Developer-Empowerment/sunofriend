from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from sunofriend.project_audio_inputs import (
    inspect_project_audio_inputs,
    prepared_project_input_problem,
)
from sunofriend.source_lineage import (
    SourceGraphAsset,
    build_source_graph_node,
    build_source_graph_revision,
    build_source_refinement_group,
    load_source_graph,
    write_source_graph_revision,
)
from sunofriend.source_project import (
    SourceMetadata,
    SourcePart,
    build_source_project,
    write_source_project,
)
from sunofriend.source_receipt import (
    SOURCE_IMPORT_SCHEMA,
    canonical_json_bytes,
)


def _identity(character: str) -> str:
    return f"sha256:{character * 64}"


def _write_source_evidence(
    root: Path,
    *,
    original_path: str,
    canonical_path: str,
    receipt_path: str,
    content: bytes,
) -> str:
    original = root / original_path
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(b"original-" + content)
    canonical = root / canonical_path
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_bytes(b"canonical-" + content)
    original_sha = hashlib.sha256(original.read_bytes()).hexdigest()
    receipt = {
        "schema": SOURCE_IMPORT_SCHEMA,
        "source_id": f"sha256:{original_sha}",
        "original": {
            "path": original_path,
            "sha256": original_sha,
        },
        "canonical": {
            "path": canonical_path,
            "sha256": hashlib.sha256(canonical.read_bytes()).hexdigest(),
            "sample_format": "pcm_s24le",
            "sample_width_bytes": 3,
        },
        "clock": {},
        "decoder": {
            "network_protocols": ["file"],
            "arguments": [],
        },
        "limits": {},
        "normalised": False,
        "network_used": False,
    }
    receipt_file = root / receipt_path
    receipt_file.parent.mkdir(parents=True, exist_ok=True)
    receipt_file.write_bytes(canonical_json_bytes(receipt))
    return receipt["source_id"]


def _prepared_project(root: Path) -> None:
    input_root = root / "INPUT"
    input_root.mkdir(parents=True)
    drums_id = _write_source_evidence(
        root,
        original_path="INPUT/original/drums.flac",
        canonical_path="song-drums-source.wav",
        receipt_path="INPUT/receipts/drums.json",
        content=b"drums",
    )
    bass_id = _write_source_evidence(
        root,
        original_path="INPUT/original/bass.flac",
        canonical_path="song-bass-source.wav",
        receipt_path="INPUT/receipts/bass.json",
        content=b"bass",
    )
    parts = (
        SourcePart(
            source_id=drums_id,
            role="drums",
            original_name="drums.flac",
            original_path="INPUT/original/drums.flac",
            canonical_path="song-drums-source.wav",
            receipt_path="INPUT/receipts/drums.json",
        ),
        SourcePart(
            source_id=bass_id,
            role="bass",
            original_name="bass.flac",
            original_path="INPUT/original/bass.flac",
            canonical_path="song-bass-source.wav",
            receipt_path="INPUT/receipts/bass.json",
        ),
    )
    project = build_source_project(
        title="Inventory",
        metadata=SourceMetadata(key="B minor", bpm=113, tuning_hz=440),
        rights_category="owned",
        sources=parts,
    )
    write_source_project(input_root / "source-project.json", project)


class ProjectAudioInputTests(unittest.TestCase):
    def test_empty_folder_requests_prepared_wav_stems(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)

            problem = prepared_project_input_problem(project)

            self.assertIn("no top-level WAV stems", problem or "")

    def test_one_non_wav_asset_points_to_single_asset_import(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "song.flac").touch()

            problem = prepared_project_input_problem(project)

            self.assertIn("source-import SOURCE", problem or "")
            self.assertIn("does not separate", problem or "")
            self.assertNotIn("source-import-folder", problem or "")

    def test_mixed_formats_are_not_silently_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "song-bass.wav").touch()
            (project / "song-keys.flac").touch()
            (project / "song-vocals.m4a").touch()

            inventory = inspect_project_audio_inputs(project)
            problem = prepared_project_input_problem(project)

            self.assertEqual(len(inventory.audio_files), 3)
            self.assertEqual(len(inventory.canonical_wavs), 1)
            self.assertEqual(len(inventory.unprepared_audio), 2)
            self.assertIn("source-import-folder", problem or "")
            self.assertIn("will not silently ignore", problem or "")

    def test_lower_case_top_level_wavs_are_conversion_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "song-bass.wav").touch()
            (project / "song-keys.wav").touch()
            nested = project / "INPUT" / "original"
            nested.mkdir(parents=True)
            (nested / "song-bass.flac").touch()

            inventory = inspect_project_audio_inputs(project)

            self.assertEqual(len(inventory.audio_files), 2)
            self.assertEqual(inventory.unprepared_audio, ())
            self.assertIsNone(prepared_project_input_problem(project))

    def test_prepared_manifest_ignores_undeclared_top_level_wav(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            _prepared_project(project)
            (project / "undeclared-keys-source.wav").touch()

            inventory = inspect_project_audio_inputs(project)

            self.assertTrue(inventory.prepared_project)
            self.assertEqual(inventory.source_graph_revision, 1)
            self.assertEqual(
                [source.role for source in inventory.sources],
                ["drums", "bass"],
            )
            self.assertNotIn(
                project / "undeclared-keys-source.wav",
                inventory.canonical_wavs,
            )

    def test_active_graph_uses_nested_children_not_inactive_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            _prepared_project(project)
            base = load_source_graph(project)
            parent = next(node for node in base.nodes if node.role == "drums")
            refined = project / "REFINED"
            refined.mkdir()
            children = []
            for role in ("kick", "snare"):
                canonical_path = f"REFINED/{role}.wav"
                receipt_path = f"REFINED/{role}.json"
                asset_id = _write_source_evidence(
                    project,
                    original_path=f"REFINED/original/{role}.bin",
                    canonical_path=canonical_path,
                    receipt_path=receipt_path,
                    content=role.encode("ascii"),
                )
                children.append(
                    build_source_graph_node(
                        parent_node_id=parent.node_id,
                        role=role,
                        declared_role=role,
                        shape="leaf",
                        origin="derived",
                        asset=SourceGraphAsset(
                            asset_id=asset_id,
                            canonical_path=canonical_path,
                            receipt_path=receipt_path,
                        ),
                        derivation={
                            "process": "test-refinement",
                            "evidence_id": _identity("e"),
                        },
                    )
                )
            group = build_source_refinement_group(
                parent_node_id=parent.node_id,
                child_node_ids=tuple(child.node_id for child in children),
                evidence_id=_identity("e"),
                coverage="complete",
            )
            active = tuple(
                node_id
                for node_id in base.active_node_ids
                if node_id != parent.node_id
            ) + tuple(child.node_id for child in children)
            revision = build_source_graph_revision(
                base,
                append_nodes=tuple(children),
                append_refinement_groups=(group,),
                active_node_ids=active,
                activation={
                    "mode": "automatic_complete",
                    "group_id": group.group_id,
                    "reviewed": False,
                    "selected_node_ids": [
                        child.node_id for child in children
                    ],
                },
            )
            write_source_graph_revision(
                project,
                revision,
                expected_current_graph_id=base.graph_id,
            )

            inventory = inspect_project_audio_inputs(project)

            self.assertEqual(inventory.source_graph_revision, 2)
            self.assertEqual(
                {source.role for source in inventory.sources},
                {"bass", "kick", "snare"},
            )
            self.assertNotIn(
                project / "song-drums-source.wav",
                inventory.canonical_wavs,
            )
            self.assertIn(
                (project / "REFINED" / "kick.wav").resolve(),
                inventory.canonical_wavs,
            )


if __name__ == "__main__":
    unittest.main()
