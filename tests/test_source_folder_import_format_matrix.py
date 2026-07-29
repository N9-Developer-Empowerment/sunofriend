from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

from sunofriend.source_folder_import import (
    execute_source_folder_import,
    plan_source_folder_import,
)
from sunofriend.source_import import inspect_pcm24_wav


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg toolchain is not installed",
)
class InstalledFfmpegFolderFormatMatrixTests(unittest.TestCase):
    def test_each_portable_format_prepares_one_atomic_two_part_project(
        self,
    ) -> None:
        ffmpeg = Path(shutil.which("ffmpeg") or "")
        ffprobe = Path(shutil.which("ffprobe") or "")
        formats = (
            ("wav-pcm24", ".wav", ("-c:a", "pcm_s24le")),
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
        admitted: list[str] = []

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bass_seed = root / "bass-seed.wav"
            keys_seed = root / "keys-seed.wav"
            _write_seed(bass_seed, sample=1)
            _write_seed(keys_seed, sample=2)

            for label, suffix, encoder_args in formats:
                with self.subTest(format=label):
                    source = root / f"sources-{label}"
                    source.mkdir()
                    encoded = (
                        (bass_seed, source / f"part-bass{suffix}"),
                        (keys_seed, source / f"part-keys{suffix}"),
                    )
                    if not all(
                        _encode(
                            ffmpeg,
                            seed,
                            target,
                            encoder_args=encoder_args,
                        )
                        for seed, target in encoded
                    ):
                        continue
                    admitted.append(label)

                    plan = plan_source_folder_import(
                        source,
                        root / f"prepared-{label}",
                        ffmpeg=ffmpeg,
                        ffprobe=ffprobe,
                        rights_category="owned",
                        discover_chords=False,
                        accept_unconfirmed_origin=True,
                    )
                    self.assertNotEqual(plan.origin_status, "conflicting")
                    result = execute_source_folder_import(plan)

                    self.assertEqual(len(result.canonicals), 2)
                    self.assertEqual(
                        {
                            part.import_plan.role
                            for part in plan.parts
                        },
                        {"bass", "keys"},
                    )
                    for canonical, part in zip(
                        result.canonicals, plan.parts
                    ):
                        geometry = inspect_pcm24_wav(canonical)
                        self.assertEqual(geometry["sample_width_bytes"], 3)
                        self.assertEqual(
                            geometry["sample_rate"],
                            part.import_plan.probe.sample_rate,
                        )
                        self.assertEqual(geometry["channels"], 2)
                    receipt = json.loads(
                        result.aggregate_receipt.read_text(encoding="utf-8")
                    )
                    self.assertFalse(receipt["normalised"])
                    self.assertFalse(receipt["network_used"])

        self.assertIn("wav-pcm24", admitted)
        self.assertIn("aiff-pcm24", admitted)
        self.assertIn("flac", admitted)
        self.assertIn("m4a-alac", admitted)
        self.assertGreaterEqual(len(expected), 6)
        self.assertEqual(set(admitted), expected)


def _write_seed(path: Path, *, sample: int) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(3)
        handle.setframerate(44100)
        frame = int(sample).to_bytes(3, "little", signed=True) * 2
        handle.writeframes(frame * 11025)


def _encode(
    ffmpeg: Path,
    source: Path,
    destination: Path,
    *,
    encoder_args: tuple[str, ...],
) -> bool:
    completed = subprocess.run(
        [
            str(ffmpeg),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            *encoder_args,
            str(destination),
        ],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30.0,
    )
    return completed.returncode == 0


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
