from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

from sunofriend.audio_formats import file_sha256
from sunofriend.source_import import (
    execute_source_import,
    inspect_pcm24_wav,
    plan_source_import,
)


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg toolchain is not installed",
)
class InstalledFfmpegFormatMatrixTests(unittest.TestCase):
    def test_portable_container_codec_matrix_decodes_to_pcm24(self) -> None:
        ffmpeg = Path(shutil.which("ffmpeg") or "")
        ffprobe = Path(shutil.which("ffprobe") or "")
        formats = (
            ("aiff-pcm24", ".aiff", ("-c:a", "pcm_s24be")),
            ("flac", ".flac", ("-c:a", "flac")),
            ("m4a-alac", ".m4a", ("-c:a", "alac")),
            ("m4a-aac", ".m4a", ("-c:a", "aac", "-b:a", "192k")),
            ("mp3", ".mp3", ("-c:a", "libmp3lame", "-b:a", "192k")),
            ("ogg-vorbis", ".ogg", ("-c:a", "libvorbis", "-q:a", "5")),
            ("ogg-opus", ".opus", ("-c:a", "libopus", "-b:a", "128k")),
        )
        available_encoders = _available_audio_encoders(ffmpeg)
        expected = {
            label
            for label, _suffix, encoder_args in formats
            if encoder_args[1] in available_encoders
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "sources"
            source_root.mkdir()
            seed = source_root / "seed-keys-B minor-113bpm-440hz.wav"
            _write_seed(seed)
            admitted: list[str] = []

            for label, suffix, encoder_args in formats:
                with self.subTest(format=label):
                    source = (
                        source_root
                        / f"matrix-{label}-keys-B minor-113bpm-440hz{suffix}"
                    )
                    completed = subprocess.run(
                        [
                            str(ffmpeg),
                            "-nostdin",
                            "-hide_banner",
                            "-loglevel",
                            "error",
                            "-i",
                            str(seed),
                            *encoder_args,
                            str(source),
                        ],
                        check=False,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=30.0,
                    )
                    if completed.returncode:
                        # Decoder policy remains portable; fixture encoders are
                        # allowed to vary between installed FFmpeg builds.
                        continue
                    admitted.append(label)
                    original_hash = file_sha256(source)
                    result = execute_source_import(
                        plan_source_import(
                            source,
                            root / f"run-{label}",
                            ffmpeg=ffmpeg,
                            ffprobe=ffprobe,
                            rights_category="owned",
                            discover_chords=False,
                        )
                    )

                    self.assertEqual(file_sha256(source), original_hash)
                    self.assertEqual(file_sha256(result.original), original_hash)
                    geometry = inspect_pcm24_wav(result.canonical)
                    receipt = json.loads(result.receipt.read_text(encoding="utf-8"))
                    self.assertEqual(geometry["sample_width_bytes"], 3)
                    self.assertEqual(
                        geometry["sample_rate"],
                        receipt["original"]["sample_rate"],
                    )
                    self.assertEqual(geometry["channels"], 2)
                    self.assertFalse(receipt["normalised"])
                    self.assertFalse(receipt["network_used"])
                    self.assertEqual(
                        receipt["canonical"]["sample_format"], "pcm_s24le"
                    )
                    declared_frames = math.ceil(
                        receipt["original"]["duration_seconds"]
                        * receipt["original"]["sample_rate"]
                    )
                    self.assertLessEqual(
                        receipt["clock"]["decoded_frame_count"],
                        declared_frames + 1,
                    )
                    if label in {"m4a-aac", "mp3"}:
                        self.assertGreater(
                            receipt["clock"]["skip_samples"],
                            0,
                            label,
                        )
                        self.assertEqual(
                            receipt["clock"]["decoded_frame_count"],
                            11025,
                        )

            self.assertIn("aiff-pcm24", admitted)
            self.assertIn("flac", admitted)
            self.assertIn("m4a-alac", admitted)
            self.assertGreaterEqual(len(expected), 5)
            self.assertEqual(set(admitted), expected)


def _write_seed(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(3)
        handle.setframerate(44100)
        handle.writeframes(b"\0\0\0" * 2 * 11025)


def _available_audio_encoders(ffmpeg: Path) -> set[str]:
    completed = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-encoders"],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30.0,
    )
    return {
        columns[1]
        for line in completed.stdout.splitlines()
        if len(columns := line.split()) >= 2
        and len(columns[0]) == 6
        and columns[0][0] == "A"
    }


if __name__ == "__main__":
    unittest.main()
