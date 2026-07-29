from __future__ import annotations

import json
import shutil
import stat
import sys
import tempfile
import unittest
import wave
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import sunofriend.source_import as source_import_module
from sunofriend.audio_formats import (
    AudioImportLimits,
    classify_audio_format,
    decoder_capability_report,
    file_sha256,
    probe_audio,
)
from sunofriend.source_import import (
    execute_source_import,
    inspect_pcm24_wav,
    plan_source_import,
)
from sunofriend.source_project import (
    SourceMetadata,
    SourcePart,
    build_source_project,
    load_source_project,
)
from sunofriend.source_receipt import validate_source_receipt_files


class SourceImportTests(unittest.TestCase):
    def test_format_policy_uses_suffix_container_and_codec_together(self) -> None:
        flac = classify_audio_format(
            ".flac", container_names=["flac"], codec="flac"
        )
        m4a = classify_audio_format(
            ".m4a",
            container_names=["mov", "mp4", "m4a"],
            codec="aac",
        )

        self.assertTrue(flac.lossless)
        self.assertFalse(m4a.lossless)
        with self.assertRaisesRegex(ValueError, "combination"):
            classify_audio_format(
                ".mp3", container_names=["wav"], codec="pcm_s24le"
            )
        with self.assertRaisesRegex(ValueError, "conditional"):
            classify_audio_format(
                ".caf", container_names=["caf"], codec="alac"
            )
        conditional = classify_audio_format(
            ".caf",
            container_names=["caf"],
            codec="alac",
            allow_conditional=True,
        )
        self.assertTrue(conditional.conditional)

    def test_capability_doctor_is_read_only_and_records_exact_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ffmpeg, ffprobe = _fake_toolchain(root)

            report = decoder_capability_report(
                ffmpeg=ffmpeg, ffprobe=ffprobe
            )

            self.assertTrue(report["read_only"])
            self.assertFalse(report["network_used"])
            self.assertTrue(report["policy"]["pcm24_encoder_available"])
            self.assertEqual(report["ffmpeg"]["path"], str(ffmpeg.resolve()))
            self.assertEqual(report["ffmpeg"]["sha256"], file_sha256(ffmpeg))
            self.assertEqual(
                sorted(root.iterdir()), sorted([ffmpeg, ffprobe])
            )

    def test_probe_rejects_symlink_and_mismatched_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ffmpeg, ffprobe = _fake_toolchain(root)
            source = root / "source.wav"
            _write_pcm24_wav(source)
            link = root / "linked.wav"
            link.symlink_to(source)

            with self.assertRaisesRegex(ValueError, "symbolic-link"):
                probe_audio(link, ffprobe=ffprobe)

            mismatched = root / "source.mp3"
            mismatched.write_bytes(source.read_bytes())
            with self.assertRaisesRegex(ValueError, "combination"):
                probe_audio(mismatched, ffprobe=ffprobe)

    def test_probe_rejects_encryption_and_multiple_audio_streams(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ffmpeg, ffprobe = _fake_toolchain(root)
            source = root / "source.wav"
            _write_pcm24_wav(source)
            encrypted = _probe_document()
            encrypted["streams"][0]["codec_tag_string"] = "enca"
            _write_fake_ffprobe(ffprobe, encrypted)

            with self.assertRaisesRegex(ValueError, "encrypted"):
                probe_audio(source, ffprobe=ffprobe)

            multiple = _probe_document()
            multiple["streams"].append(dict(multiple["streams"][0], index=1))
            _write_fake_ffprobe(ffprobe, multiple)
            with self.assertRaisesRegex(ValueError, "exactly one"):
                probe_audio(source, ffprobe=ffprobe)

    def test_plan_is_read_only_and_preserves_musical_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ffmpeg, ffprobe = _fake_toolchain(root)
            source = (
                root
                / "song"
                / "Example-bass-B major-120bpm-440hz.wav"
            )
            source.parent.mkdir()
            _write_pcm24_wav(source)
            chord = source.parent / "Example_chords.pdf"
            chord.write_bytes(b"%PDF-1.4\nexample chords\n")
            destination = root / "run"

            plan = plan_source_import(
                source,
                destination,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                rights_category="owned",
            )

            self.assertFalse(destination.exists())
            self.assertEqual(plan.role, "bass")
            self.assertEqual(plan.metadata.key, "B major")
            self.assertEqual(plan.metadata.bpm, 120.0)
            self.assertEqual(plan.metadata.tuning_hz, 440.0)
            self.assertEqual(plan.chord_document, chord.resolve())
            document = plan.to_dict()
            self.assertTrue(document["read_only"])
            self.assertEqual(document["side_effects_if_executed"]["network"], [])
            self.assertEqual(document["side_effects_if_executed"]["installs"], [])

    def test_execute_creates_pcm24_receipt_manifest_and_immutable_copies(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ffmpeg, ffprobe = _fake_toolchain(root)
            source = (
                root
                / "song"
                / "Example-bass-B major-120bpm-440hz.wav"
            )
            source.parent.mkdir()
            _write_pcm24_wav(source)
            original_hash = file_sha256(source)
            chord = source.parent / "Example_chords.pdf"
            chord.write_bytes(b"%PDF-1.4\nexample chords\n")
            destination = root / "run"
            plan = plan_source_import(
                source,
                destination,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                rights_category="authorised_private_use",
                instrument_label="buzzing synth bass",
            )

            result = execute_source_import(plan)

            self.assertEqual(file_sha256(source), original_hash)
            self.assertEqual(file_sha256(result.original), original_hash)
            self.assertEqual(
                inspect_pcm24_wav(result.canonical)["sample_width_bytes"], 3
            )
            receipt = json.loads(result.receipt.read_text(encoding="utf-8"))
            validate_source_receipt_files(receipt, root=result.root)
            self.assertFalse(receipt["network_used"])
            self.assertFalse(receipt["normalised"])
            self.assertEqual(
                receipt["decoder"]["network_protocols"], ["file"]
            )
            self.assertIn("<SOURCE>", receipt["decoder"]["arguments"])
            self.assertIn("<CANONICAL>", receipt["decoder"]["arguments"])
            self.assertIn("-fs", receipt["decoder"]["arguments"])
            self.assertIn(
                str(plan.limits.maximum_canonical_bytes),
                receipt["decoder"]["arguments"],
            )
            self.assertIn("-t", receipt["decoder"]["arguments"])
            self.assertIn("0.010000000", receipt["decoder"]["arguments"])
            self.assertEqual(receipt["decoder"]["normalization_filters"], [])
            self.assertEqual(receipt["canonical"]["sample_format"], "pcm_s24le")
            self.assertEqual(receipt["clock"]["decoded_frame_count"], 80)
            project = load_source_project(result.source_project)
            self.assertEqual(project["metadata"]["key"], "B major")
            self.assertEqual(project["sources"][0]["role"], "bass")
            self.assertEqual(
                project["sources"][0]["instrument_label"],
                "buzzing synth bass",
            )
            self.assertEqual(
                project["rights"]["category"], "authorised_private_use"
            )
            self.assertEqual(
                project["chord_document"]["sha256"], file_sha256(chord)
            )
            self.assertFalse(
                result.original.stat().st_mode & stat.S_IWUSR
            )
            self.assertFalse(
                result.canonical.stat().st_mode & stat.S_IWUSR
            )
            self.assertFalse(
                result.receipt.stat().st_mode & stat.S_IWUSR
            )
            self.assertFalse(
                result.source_project.stat().st_mode & stat.S_IWUSR
            )

    def test_two_imports_with_same_inputs_have_identical_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ffmpeg, ffprobe = _fake_toolchain(root)
            source = (
                root
                / "sources"
                / "Example-keys-C major-100bpm-440hz.wav"
            )
            _write_pcm24_wav(source)

            first = execute_source_import(
                plan_source_import(
                    source,
                    root / "run-1",
                    ffmpeg=ffmpeg,
                    ffprobe=ffprobe,
                    rights_category="owned",
                )
            )
            second = execute_source_import(
                plan_source_import(
                    source,
                    root / "run-2",
                    ffmpeg=ffmpeg,
                    ffprobe=ffprobe,
                    rights_category="owned",
                )
            )

            self.assertEqual(
                first.receipt.read_bytes(), second.receipt.read_bytes()
            )
            self.assertEqual(
                first.source_project.read_bytes(),
                second.source_project.read_bytes(),
            )

    def test_execute_rechecks_source_identity_and_cleans_failed_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ffmpeg, ffprobe = _fake_toolchain(root)
            source = root / "sources" / "source.wav"
            _write_pcm24_wav(source)
            destination = root / "run"
            plan = plan_source_import(
                source,
                destination,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                rights_category="owned",
            )
            source.write_bytes(source.read_bytes() + b"changed")

            with self.assertRaisesRegex(ValueError, "changed"):
                execute_source_import(plan)

            self.assertFalse(destination.exists())
            self.assertFalse(
                list(root.glob(f".{destination.name}.importing-*"))
            )

    def test_execute_rechecks_decoder_identity_before_decode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ffmpeg, ffprobe = _fake_toolchain(root)
            source = root / "sources" / "source.wav"
            _write_pcm24_wav(source)
            destination = root / "run"
            plan = plan_source_import(
                source,
                destination,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                rights_category="owned",
            )
            ffprobe.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            ffprobe.chmod(0o755)

            with self.assertRaisesRegex(ValueError, "ffprobe changed"):
                execute_source_import(plan)

            self.assertFalse(destination.exists())

    def test_execute_rechecks_decoder_identity_after_decode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ffmpeg, ffprobe = _fake_toolchain(
                root, mutate_after_decode=True
            )
            source = root / "sources" / "source.wav"
            _write_pcm24_wav(source)
            destination = root / "run"
            plan = plan_source_import(
                source,
                destination,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                rights_category="owned",
            )

            with self.assertRaisesRegex(ValueError, "ffmpeg changed"):
                execute_source_import(plan)

            self.assertFalse(destination.exists())
            self.assertFalse(
                list(root.glob(f".{destination.name}.importing-*"))
            )

    def test_decode_failure_removes_partial_atomic_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ffmpeg, ffprobe = _fake_toolchain(root, fail_decode=True)
            source = root / "sources" / "source.wav"
            _write_pcm24_wav(source)
            destination = root / "run"
            plan = plan_source_import(
                source,
                destination,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                rights_category="owned",
            )

            with self.assertRaisesRegex(RuntimeError, "exit code 12"):
                execute_source_import(plan)

            self.assertFalse(destination.exists())
            self.assertFalse(
                list(root.glob(f".{destination.name}.importing-*"))
            )

    def test_plan_accounts_for_original_canonical_chords_and_headroom(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ffmpeg, ffprobe = _fake_toolchain(root)
            source = root / "sources" / "source-bass.wav"
            _write_pcm24_wav(source)
            chord = source.parent / "song_chords.pdf"
            chord.write_bytes(b"%PDF-1.4\nchords\n")
            limits = AudioImportLimits(
                minimum_free_space_headroom_bytes=123
            )

            plan = plan_source_import(
                source,
                root / "run",
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                rights_category="owned",
                limits=limits,
            )

            self.assertEqual(plan.chord_bytes, chord.stat().st_size)
            self.assertEqual(
                plan.required_free_bytes,
                source.stat().st_size
                + 2 * plan.probe.projected_pcm24_bytes
                + chord.stat().st_size
                + 123,
            )

    def test_plan_rejects_destination_inside_source_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ffmpeg, ffprobe = _fake_toolchain(root)
            source = root / "sources" / "source.wav"
            _write_pcm24_wav(source)

            with self.assertRaisesRegex(ValueError, "outside"):
                plan_source_import(
                    source,
                    source.parent / "generated",
                    ffmpeg=ffmpeg,
                    ffprobe=ffprobe,
                    rights_category="owned",
                )

    def test_atomic_publish_preserves_destination_created_during_decode(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ffmpeg, ffprobe = _fake_toolchain(root)
            source = root / "sources" / "source.wav"
            _write_pcm24_wav(source)
            destination = root / "run"
            plan = plan_source_import(
                source,
                destination,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                rights_category="owned",
            )

            def decode_with_race(
                _ffmpeg: Path,
                arguments: list[str],
                *,
                timeout_seconds: float,
            ) -> None:
                self.assertGreater(timeout_seconds, 0)
                source_arg = Path(arguments[arguments.index("-i") + 1])
                shutil.copyfile(source_arg, Path(arguments[-1]))
                destination.mkdir()

            with (
                patch(
                    "sunofriend.source_import._run_decode",
                    side_effect=decode_with_race,
                ),
                self.assertRaisesRegex(FileExistsError, "became occupied"),
            ):
                execute_source_import(plan)

            self.assertTrue(destination.is_dir())
            self.assertEqual(list(destination.iterdir()), [])
            self.assertFalse(
                list(root.glob(f".{destination.name}.importing-*"))
            )

    def test_execute_rejects_mutated_or_redirected_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ffmpeg, ffprobe = _fake_toolchain(root)
            source = root / "sources" / "source.wav"
            _write_pcm24_wav(source)
            plan = plan_source_import(
                source,
                root / "prepared" / "run",
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                rights_category="owned",
            )

            mutated = replace(
                plan,
                destination=plan.source.parent / "unexpected-run",
            )
            with self.assertRaisesRegex(ValueError, "outside"):
                execute_source_import(mutated)

            redirect_target = source.parent / "redirected"
            redirect_target.mkdir()
            (root / "prepared").symlink_to(redirect_target)
            with self.assertRaisesRegex(ValueError, "changed"):
                execute_source_import(plan)

    def test_staging_cannot_follow_ancestor_symlink_inserted_after_open(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ffmpeg, ffprobe = _fake_toolchain(root)
            source = root / "sources" / "source.wav"
            _write_pcm24_wav(source)
            output_parent = root / "prepared"
            output_parent.mkdir()
            plan = plan_source_import(
                source,
                output_parent / "run",
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                rights_category="owned",
            )
            displaced_parent = root / "prepared-before-race"
            original_create = (
                source_import_module._create_staging_directory
            )

            def create_after_redirect(
                parent_fd: int,
                destination: Path,
            ) -> Path:
                output_parent.rename(displaced_parent)
                output_parent.symlink_to(source.parent)
                return original_create(parent_fd, destination)

            with (
                patch(
                    "sunofriend.source_import._create_staging_directory",
                    side_effect=create_after_redirect,
                ),
                self.assertRaisesRegex(ValueError, "parent changed"),
            ):
                execute_source_import(plan)

            self.assertFalse((source.parent / "run").exists())
            self.assertFalse(
                list(source.parent.glob(".run.importing-*"))
            )
            self.assertTrue(
                list(displaced_parent.glob(".run.importing-*"))
            )

    def test_empty_or_implausibly_short_decode_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ffmpeg, ffprobe = _fake_toolchain(root)
            source = root / "sources" / "source.wav"
            _write_pcm24_wav(source)

            for frame_count in (0, 1):
                with self.subTest(frame_count=frame_count):
                    destination = root / f"run-{frame_count}"
                    plan = plan_source_import(
                        source,
                        destination,
                        ffmpeg=ffmpeg,
                        ffprobe=ffprobe,
                        rights_category="owned",
                    )

                    def short_decode(
                        _ffmpeg: Path,
                        arguments: list[str],
                        *,
                        timeout_seconds: float,
                    ) -> None:
                        self.assertGreater(timeout_seconds, 0)
                        _write_pcm24_wav(
                            Path(arguments[-1]),
                            frame_count=frame_count,
                        )

                    with (
                        patch(
                            "sunofriend.source_import._run_decode",
                            side_effect=short_decode,
                        ),
                        self.assertRaisesRegex(RuntimeError, "shorter"),
                    ):
                        execute_source_import(plan)

                    self.assertFalse(destination.exists())

    def test_source_project_model_can_represent_several_prepared_stems(self) -> None:
        first = SourcePart(
            source_id=f"sha256:{'1' * 64}",
            role="bass",
            original_name="bass.flac",
            original_path="INPUT/original/bass.flac",
            canonical_path="INPUT/canonical/bass.wav",
            receipt_path="INPUT/receipts/bass.json",
        )
        second = SourcePart(
            source_id=f"sha256:{'2' * 64}",
            role="drums",
            original_name="drums.m4a",
            original_path="INPUT/original/drums.m4a",
            canonical_path="INPUT/canonical/drums.wav",
            receipt_path="INPUT/receipts/drums.json",
        )

        project = build_source_project(
            title="Several stems",
            metadata=SourceMetadata("B minor", 113.0, 440.0),
            rights_category="owned",
            sources=(first, second),
        ).to_dict()

        self.assertEqual(
            [row["role"] for row in project["sources"]],
            ["bass", "drums"],
        )

    def test_size_and_canonical_expansion_limits_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _ffmpeg, ffprobe = _fake_toolchain(root)
            source = root / "source.wav"
            _write_pcm24_wav(source)
            tiny_input = AudioImportLimits(
                maximum_input_bytes=10,
                minimum_free_space_headroom_bytes=0,
            )
            with self.assertRaisesRegex(ValueError, "maximum"):
                probe_audio(source, ffprobe=ffprobe, limits=tiny_input)

            tiny_canonical = AudioImportLimits(
                maximum_canonical_bytes=100,
                minimum_free_space_headroom_bytes=0,
            )
            with self.assertRaisesRegex(ValueError, "projected canonical"):
                probe_audio(
                    source, ffprobe=ffprobe, limits=tiny_canonical
                )

    @unittest.skipUnless(
        shutil.which("ffmpeg") and shutil.which("ffprobe"),
        "FFmpeg toolchain is not installed",
    )
    def test_installed_ffmpeg_produces_valid_pcm24_smoke_asset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "sources" / "real-smoke-kick.wav"
            _write_pcm24_wav(source)

            result = execute_source_import(
                plan_source_import(
                    source,
                    root / "run",
                    ffmpeg=Path(shutil.which("ffmpeg") or ""),
                    ffprobe=Path(shutil.which("ffprobe") or ""),
                    rights_category="owned",
                    discover_chords=False,
                )
            )
            repeated = execute_source_import(
                plan_source_import(
                    source,
                    root / "run-repeated",
                    ffmpeg=Path(shutil.which("ffmpeg") or ""),
                    ffprobe=Path(shutil.which("ffprobe") or ""),
                    rights_category="owned",
                    discover_chords=False,
                )
            )

            geometry = inspect_pcm24_wav(result.canonical)
            self.assertEqual(geometry["sample_width_bytes"], 3)
            self.assertEqual(geometry["sample_rate"], 8000)
            self.assertEqual(geometry["channels"], 1)
            self.assertEqual(
                file_sha256(result.canonical),
                file_sha256(repeated.canonical),
            )


def _write_pcm24_wav(path: Path, *, frame_count: int = 80) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(3)
        handle.setframerate(8000)
        handle.writeframes(b"\0\0\0" * frame_count)


def _fake_toolchain(
    root: Path,
    *,
    fail_decode: bool = False,
    mutate_after_decode: bool = False,
) -> tuple[Path, Path]:
    ffmpeg = root / "ffmpeg-fake"
    ffprobe = root / "ffprobe-fake"
    ffmpeg.write_text(
        f"""#!{sys.executable}
import shutil
import sys
if "-version" in sys.argv:
    print("ffmpeg version sunofriend-test")
elif "-formats" in sys.argv:
    print(" D  wav")
elif "-codecs" in sys.argv:
    print(" DEAI.S pcm_s24le PCM signed 24-bit little-endian")
else:
    source = sys.argv[sys.argv.index("-i") + 1]
    {"sys.exit(12)" if fail_decode else "shutil.copyfile(source, sys.argv[-1])"}
    {"open(sys.argv[0], 'a', encoding='utf-8').write(chr(10) + '# changed')" if mutate_after_decode else ""}
""",
        encoding="utf-8",
    )
    _write_fake_ffprobe(ffprobe, _probe_document())
    ffmpeg.chmod(0o755)
    return ffmpeg, ffprobe


def _probe_document() -> dict:
    return {
        "streams": [
            {
                "index": 0,
                "codec_name": "pcm_s24le",
                "codec_type": "audio",
                "sample_fmt": "s32",
                "sample_rate": "8000",
                "channels": 1,
                "channel_layout": "mono",
                "time_base": "1/8000",
                "start_pts": 0,
                "start_time": "0.000000",
                "duration_ts": 80,
                "duration": "0.010000",
                "initial_padding": 0,
                "trailing_padding": 0,
            }
        ],
        "format": {
            "format_name": "wav",
            "start_time": "0.000000",
            "duration": "0.010000",
        },
    }


def _write_fake_ffprobe(path: Path, probe_document: dict) -> None:
    path.write_text(
        f"""#!{sys.executable}
import sys
if "-version" in sys.argv:
    print("ffprobe version sunofriend-test")
else:
    print({json.dumps(json.dumps(probe_document))})
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
