import dataclasses
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from sunofriend.clip import (
    ChordEvent,
    ClipNote,
    Instrument,
    KeySignature,
    MidiClip,
    Provenance,
    TempoMap,
    TempoPoint,
    TimeSignature,
    WarpPoint,
    read_midi_clips,
    write_clip_midi,
)
from sunofriend.library import ClipLibrary
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent
from sunofriend.transform import remap_mode, retime_bpm, transpose, transpose_same_mode


def make_clip(*, role="bass", channel=0, tags=("golden",)):
    tempo_map = TempoMap(
        (TempoPoint(0.0, 120.0),),
        (WarpPoint(0.0, 0.0), WarpPoint(4.0, 2.04), WarpPoint(8.0, 3.98)),
    )
    notes = (
        ClipNote.from_beats(0.0, 1.0, 60, 100, tempo_map),
        ClipNote.from_beats(1.0, 1.0, 64, 96, tempo_map),
        ClipNote.from_beats(2.0, 1.0, 67, 92, tempo_map),
        ClipNote.from_beats(3.0, 1.0, 71, 90, tempo_map),
    )
    return MidiClip(
        title="Golden bass",
        tempo_map=tempo_map,
        time_signature=TimeSignature(4, 4),
        instrument=Instrument(role, program=33, channel=channel, suggestions=("Picked Bass", "Finger Bass")),
        notes=notes,
        key=KeySignature("C", "major"),
        chords=(ChordEvent(0.0, 4.0, "C", 0.0, 2.04),),
        provenance=Provenance(
            source_uri="file:///move-your-body/bass.wav",
            source_stem="bass.wav",
            converter="basic-pitch",
            details={"model": "test", "confidence": 0.92, "analysis": {"take": 1}},
        ),
        clip_id="golden-bass-v1",
        engine_version="test-engine-1",
        tags=tags,
    )


class ClipModelTests(unittest.TestCase):
    def test_json_roundtrip_keeps_dual_timing_and_schema(self):
        clip = make_clip()
        encoded = clip.to_json()
        decoded = MidiClip.from_json(encoded)

        self.assertEqual(decoded, clip)
        self.assertEqual(json.loads(encoded)["schema_version"], 1)
        self.assertAlmostEqual(decoded.notes[1].start_beat, 1.0)
        self.assertAlmostEqual(decoded.notes[1].source_start_seconds, 0.51)
        self.assertEqual(decoded.instrument.suggestions, ("Picked Bass", "Finger Bass"))
        self.assertEqual(decoded.provenance.details_dict["model"], "test")
        self.assertEqual(decoded.provenance.details_dict["analysis"], {"take": 1})
        with self.assertRaises(dataclasses.FrozenInstanceError):
            decoded.title = "changed"

    def test_unknown_json_schema_is_rejected(self):
        document = make_clip().to_dict()
        document["schema_version"] = 99
        with self.assertRaisesRegex(ValueError, "Unsupported clip schema"):
            MidiClip.from_dict(document)

    def test_content_id_is_deterministic_and_includes_catalog_metadata(self):
        clip = make_clip()
        first = dataclasses.replace(clip, clip_id="temporary").with_content_id()
        second = dataclasses.replace(clip, clip_id="another").with_content_id()
        tagged = dataclasses.replace(clip, clip_id="temporary", tags=("different",)).with_content_id()

        self.assertEqual(first.clip_id, second.clip_id)
        self.assertNotEqual(first.clip_id, tagged.clip_id)

    def test_tempo_and_warp_maps_are_bidirectional(self):
        tempo_map = TempoMap(
            (TempoPoint(0, 120), TempoPoint(4, 60)),
            (WarpPoint(0, 0.1), WarpPoint(4, 2.2), WarpPoint(8, 6.3)),
        )
        self.assertAlmostEqual(tempo_map.musical_seconds_at(6), 4.0)
        self.assertAlmostEqual(tempo_map.beat_at_musical_seconds(4.0), 6.0)
        self.assertAlmostEqual(tempo_map.source_seconds_at(6), 4.25)
        self.assertAlmostEqual(tempo_map.beat_at_source_seconds(4.25), 6.0)


class MidiInterchangeTests(unittest.TestCase):
    def test_clip_midi_export_is_deterministic_and_roundtrips(self):
        clip = make_clip()
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.mid"
            second = Path(tmp) / "second.mid"
            write_clip_midi(first, clip)
            write_clip_midi(second, clip)
            imported = read_midi_clips(first)

            self.assertEqual(first.read_bytes(), second.read_bytes())

        self.assertEqual(len(imported), 1)
        result = imported[0]
        self.assertEqual(result.title, clip.title)
        self.assertEqual(result.key, KeySignature("C", "major"))
        self.assertEqual(result.time_signature, TimeSignature(4, 4))
        self.assertEqual(result.instrument.program, 33)
        self.assertEqual([note.pitch for note in result.notes], [60, 64, 67, 71])
        self.assertEqual([note.start_beat for note in result.notes], [0.0, 1.0, 2.0, 3.0])
        self.assertEqual(result.chords[0].symbol, "C")

    def test_garageband_bpm_override_requires_stem_locked_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "only valid for a stem_locked"):
                write_clip_midi(
                    Path(tmp) / "invalid.mid",
                    make_clip(),
                    timing_mode="musical",
                    garageband_bpm=130,
                )

    def test_stem_locked_export_preserves_source_seconds_and_lead_in(self):
        tempo_map = TempoMap(
            (TempoPoint(0.0, 130.016),),
            (WarpPoint(0.0, 0.175), WarpPoint(4.0, 2.021),),
            offset_seconds=0.175,
        )
        clip = MidiClip(
            title="Stem-locked kick",
            tempo_map=tempo_map,
            time_signature=TimeSignature(),
            instrument=Instrument("kick", channel=9),
            notes=(
                ClipNote(0.0, 0.1, 36, 110, 0.175, 0.225),
                ClipNote(1.0, 0.1, 36, 108, 0.637, 0.687),
            ),
            provenance=Provenance(
                details={"timing_mode": "stem_locked", "garageband_bpm": 130.0}
            ),
        )

        with tempfile.TemporaryDirectory() as tmp:
            automatic = Path(tmp) / "automatic.mid"
            musical = Path(tmp) / "musical.mid"
            write_clip_midi(automatic, clip)
            write_clip_midi(musical, clip, timing_mode="musical")
            restored = read_midi_clips(automatic)[0]
            beat_only = read_midi_clips(musical)[0]

        tick_seconds = 60.0 / (130.0 * 480.0)
        for expected, note in zip(clip.notes, restored.notes):
            self.assertAlmostEqual(
                note.source_start_seconds,
                expected.source_start_seconds,
                delta=tick_seconds / 2 + 1e-6,
            )
            self.assertAlmostEqual(
                note.source_end_seconds,
                expected.source_end_seconds,
                delta=tick_seconds / 2 + 1e-6,
            )
        self.assertAlmostEqual(restored.bpm, 130.0, places=3)
        self.assertAlmostEqual(beat_only.notes[0].source_start_seconds, 0.0, places=6)

    def test_auto_export_follows_latest_bpm_timing_contract(self):
        tempo_map = TempoMap.constant(120)
        original = MidiClip(
            title="Retiming",
            tempo_map=tempo_map,
            time_signature=TimeSignature(),
            instrument=Instrument("bass", 38, 0),
            notes=(ClipNote.from_beats(2.0, 1.0, 48, 90, tempo_map),),
            provenance=Provenance(
                details={"timing_mode": "stem_locked", "garageband_bpm": 120.0}
            ),
        )
        musical = transpose(retime_bpm(original, 240, mode="musical"), 2)
        locked = transpose(retime_bpm(original, 240, mode="stem_locked"), 2)

        with tempfile.TemporaryDirectory() as tmp:
            musical_path = Path(tmp) / "musical.mid"
            locked_path = Path(tmp) / "locked.mid"
            write_clip_midi(musical_path, musical)
            write_clip_midi(locked_path, locked)
            musical_result = read_midi_clips(musical_path)[0]
            locked_result = read_midi_clips(locked_path)[0]

        self.assertAlmostEqual(musical_result.bpm, 240.0, places=3)
        self.assertAlmostEqual(musical_result.notes[0].start_beat, 2.0, places=6)
        self.assertAlmostEqual(musical_result.notes[0].source_start_seconds, 0.5, places=6)
        self.assertAlmostEqual(locked_result.bpm, 240.0, places=3)
        self.assertAlmostEqual(locked_result.notes[0].start_beat, 4.0, places=6)
        self.assertAlmostEqual(locked_result.notes[0].source_start_seconds, 1.0, places=6)

    def test_reader_imports_files_from_existing_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "arrangement.mid"
            write_midi_file(
                path,
                [
                    MidiTrack("Drums", 9, 0, [NoteEvent(0.0, 0.1, 36, 110)]),
                    MidiTrack("Bass", 0, 38, [NoteEvent(0.4, 0.8, 43, 95)]),
                ],
                bpm=150,
            )
            clips = read_midi_clips(path, key="D minor")

        self.assertEqual([clip.title for clip in clips], ["Drums", "Bass"])
        self.assertEqual(clips[0].instrument.role, "drums")
        self.assertEqual(clips[0].notes[0].pitch, 36)
        self.assertEqual(clips[0].instrument.suggestions[0], "Modern 909")
        self.assertEqual(clips[1].instrument.program, 38)
        self.assertAlmostEqual(clips[1].notes[0].start_beat, 1.0)
        self.assertEqual(clips[1].key, KeySignature("D", "minor"))


class TransformTests(unittest.TestCase):
    def test_same_mode_transpose_versions_clip_and_preserves_drum_pitches(self):
        clip = make_clip()
        shifted = transpose_same_mode(clip, "D", direction="up")

        self.assertEqual(shifted.key, KeySignature("D", "major"))
        self.assertEqual([note.pitch for note in shifted.notes], [62, 66, 69, 73])
        self.assertEqual(shifted.chords[0].symbol, "D")
        self.assertEqual(shifted.parent_clip_id, clip.clip_id)
        self.assertEqual(shifted.revision, 2)
        self.assertEqual(shifted.transform_recipe.operation, "transpose_same_mode")

        flat = transpose_same_mode(clip, "Bb", direction="down")
        self.assertEqual(flat.key, KeySignature("Bb", "major"))
        self.assertEqual(flat.chords[0].symbol, "Bb")

        drums = make_clip(role="drums", channel=9)
        transposed_drums = transpose(drums, 5)
        self.assertEqual(
            [note.pitch for note in transposed_drums.notes],
            [note.pitch for note in drums.notes],
        )

    def test_major_to_minor_uses_scale_degrees_and_chord_quality(self):
        clip = make_clip()
        minor = remap_mode(clip, "minor")

        self.assertEqual(minor.key, KeySignature("C", "minor"))
        self.assertEqual(minor.chords[0].symbol, "Cm")
        self.assertEqual([note.pitch for note in minor.notes], [60, 63, 67, 70])
        self.assertEqual(minor.transform_recipe.parameters_dict["chord_aware"], True)

    def test_bpm_modes_make_time_semantics_explicit(self):
        straight = TempoMap.constant(120)
        clip = MidiClip(
            title="Timing",
            tempo_map=straight,
            time_signature=TimeSignature(),
            instrument=Instrument("lead", 80, 0),
            notes=(ClipNote.from_beats(2, 1, 72, 100, straight),),
            clip_id="timing-v1",
        )

        musical = retime_bpm(clip, 240, mode="musical")
        locked = retime_bpm(clip, 240, mode="stem_locked")

        self.assertEqual(musical.notes[0].start_beat, 2)
        self.assertAlmostEqual(musical.notes[0].source_start_seconds, 0.5)
        self.assertAlmostEqual(musical.notes[0].source_end_seconds, 0.75)
        self.assertAlmostEqual(locked.notes[0].source_start_seconds, 1.0)
        self.assertAlmostEqual(locked.notes[0].source_end_seconds, 1.5)
        self.assertAlmostEqual(locked.notes[0].start_beat, 4.0)
        self.assertAlmostEqual(locked.notes[0].duration_beats, 2.0)
        self.assertEqual(locked.transform_recipe.parameters_dict["timing_mode"], "stem_locked")


class LibraryTests(unittest.TestCase):
    def test_catalog_add_get_search_and_versions(self):
        clip = make_clip()
        child = transpose_same_mode(clip, "D", direction="up")
        with tempfile.TemporaryDirectory() as tmp:
            library = ClipLibrary(tmp)
            first_summary = library.add(clip)
            second_summary = library.add_version(clip.clip_id, child)

            self.assertEqual(library.get(clip.clip_id), clip)
            self.assertTrue(library.object_path(first_summary.object_hash).exists())
            self.assertEqual(library.add(clip), first_summary)  # idempotent
            self.assertEqual([item.clip_id for item in library.versions(child.clip_id)], [clip.clip_id, child.clip_id])
            self.assertEqual(library.search(key="D major")[0].clip_id, child.clip_id)
            self.assertEqual(library.search(tags=["golden"])[0].lineage_id, clip.clip_id)
            self.assertEqual(len(library.list()), 2)
            self.assertEqual(second_summary.revision, 2)

    def test_catalog_rejects_mutating_an_existing_clip_id(self):
        clip = make_clip()
        with tempfile.TemporaryDirectory() as tmp:
            library = ClipLibrary(tmp)
            library.add(clip)
            changed = dataclasses.replace(clip, title="Not immutable")
            with self.assertRaisesRegex(ValueError, "different immutable content"):
                library.add(changed)

    def test_read_only_catalog_supports_verified_queries_and_versions(self):
        clip = make_clip()
        child = transpose_same_mode(clip, "D", direction="up")
        with tempfile.TemporaryDirectory() as tmp:
            writable = ClipLibrary(tmp)
            first = writable.add(clip)
            writable.add_version(clip.clip_id, child)

            library = ClipLibrary(tmp, read_only=True)

            self.assertTrue(library.read_only)
            self.assertEqual(library.get(clip.clip_id), clip)
            self.assertEqual([item.clip_id for item in library.list()], [child.clip_id, clip.clip_id])
            self.assertEqual(library.search(key="D major")[0].clip_id, child.clip_id)
            self.assertEqual(
                [item.clip_id for item in library.versions(child.clip_id)],
                [clip.clip_id, child.clip_id],
            )

            library.object_path(first.object_hash).write_bytes(b"changed outside the library")
            with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                library.get(clip.clip_id)

    def test_read_only_catalog_uses_two_sqlite_write_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            writable = ClipLibrary(tmp)
            writable.add(make_clip())
            library = ClipLibrary(tmp, read_only=True)

            with library._connect() as connection:
                self.assertEqual(connection.execute("PRAGMA query_only").fetchone()[0], 1)
                connection.execute("PRAGMA query_only = OFF")
                with self.assertRaisesRegex(sqlite3.OperationalError, "readonly"):
                    connection.execute("DELETE FROM clips")

    def test_read_only_catalog_rejects_every_library_write(self):
        clip = make_clip()
        child = transpose_same_mode(clip, "D", direction="up")
        with tempfile.TemporaryDirectory() as tmp:
            writable = ClipLibrary(tmp)
            summary = writable.add(clip)
            library = ClipLibrary(tmp, read_only=True)

            with self.assertRaisesRegex(PermissionError, "read-only; cannot add clips"):
                library.add(clip)
            with self.assertRaisesRegex(PermissionError, "read-only; cannot add clip versions"):
                library.add_version(clip.clip_id, child)
            with self.assertRaisesRegex(PermissionError, "read-only; cannot store clip objects"):
                library._store_object(summary.object_hash, clip.canonical_bytes())

    def test_read_only_catalog_never_creates_missing_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing_root = Path(tmp) / "missing-library"
            with self.assertRaisesRegex(FileNotFoundError, "root does not exist"):
                ClipLibrary(missing_root, read_only=True)
            self.assertFalse(missing_root.exists())

            missing_database = Path(tmp) / "missing-database"
            missing_database.mkdir()
            with self.assertRaisesRegex(FileNotFoundError, "database does not exist"):
                ClipLibrary(missing_database, read_only=True)
            self.assertFalse((missing_database / "catalog.sqlite3").exists())
            self.assertFalse((missing_database / "objects").exists())

            missing_objects = Path(tmp) / "missing-objects"
            ClipLibrary(missing_objects)
            (missing_objects / "objects").rmdir()
            with self.assertRaisesRegex(FileNotFoundError, "objects directory does not exist"):
                ClipLibrary(missing_objects, read_only=True)
            self.assertFalse((missing_objects / "objects").exists())

    def test_read_only_catalog_does_not_initialize_or_migrate_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "objects").mkdir()
            with sqlite3.connect(root / "catalog.sqlite3") as connection:
                connection.execute("CREATE TABLE unrelated (value TEXT)")
                journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

            with self.assertRaisesRegex(RuntimeError, "schema is missing required columns"):
                ClipLibrary(root, read_only=True)

            with sqlite3.connect(root / "catalog.sqlite3") as connection:
                self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], journal_mode)
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
            self.assertEqual(tables, {"unrelated"})


if __name__ == "__main__":
    unittest.main()
