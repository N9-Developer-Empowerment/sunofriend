from __future__ import annotations

import json
import math
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

from sunofriend.audio_formats import (
    decoder_capability_report,
    probe_audio,
)


FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


def _installed_encoder_available(encoder: str) -> bool:
    if FFMPEG is None or FFPROBE is None:
        return False
    completed = subprocess.run(
        [FFMPEG, "-hide_banner", "-encoders"],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode:
        return False
    for line in completed.stdout.splitlines():
        columns = line.split()
        if (
            len(columns) >= 2
            and len(columns[0]) == 6
            and columns[0][0] == "A"
            and columns[1] == encoder
        ):
            return True
    return False


class AudioFormatBoundaryTests(unittest.TestCase):
    def test_packet_edges_supply_skip_and_discard_padding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp3"
            source.write_bytes(b"fake mp3")
            invocation_log = root / "ffprobe-arguments.jsonl"
            ffprobe = root / "ffprobe-fake"
            _write_packet_ffprobe(
                ffprobe,
                invocation_log=invocation_log,
                stream_document=_probe_document(
                    suffix_format="mp3",
                    codec="mp3",
                ),
                first_packet_document={
                    "packets": [
                        {
                            "side_data_list": [
                                {
                                    "side_data_type": "Skip Samples",
                                    "skip_samples": 1105,
                                    "discard_padding": 0,
                                }
                            ]
                        }
                    ]
                },
                tail_packet_document={
                    "packets": [
                        {},
                        {
                            "side_data_list": [
                                {
                                    "side_data_type": "Skip Samples",
                                    "skip_samples": 0,
                                    "discard_padding": 227,
                                }
                            ]
                        },
                    ]
                },
            )

            result = probe_audio(source, ffprobe=ffprobe)

            self.assertEqual(result.skip_samples, 1105)
            self.assertEqual(result.discard_padding_samples, 227)
            invocations = [
                json.loads(line)
                for line in invocation_log.read_text(encoding="utf-8").splitlines()
            ]
            packet_calls = [
                arguments
                for arguments in invocations
                if "-show_packets" in arguments
            ]
            self.assertEqual(len(packet_calls), 2)
            for arguments in packet_calls:
                protocol_at = arguments.index("-protocol_whitelist")
                self.assertEqual(arguments[protocol_at + 1], "file")
                self.assertIn("-read_intervals", arguments)
            intervals = [
                arguments[arguments.index("-read_intervals") + 1]
                for arguments in packet_calls
            ]
            self.assertEqual(intervals[0], "%+#1")
            self.assertTrue(intervals[1].endswith("%+2.000000"))

    def test_probe_rejects_every_non_audio_stream_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.m4a"
            source.write_bytes(b"fake m4a")
            ffprobe = root / "ffprobe-fake"
            for stream_type in ("video", "data", "attachment", "subtitle"):
                with self.subTest(stream_type=stream_type):
                    document = _probe_document(
                        suffix_format="mov,mp4,m4a,3gp,3g2,mj2",
                        codec="aac",
                    )
                    document["streams"].append(
                        {
                            "index": 1,
                            "codec_name": "irrelevant",
                            "codec_type": stream_type,
                        }
                    )
                    _write_packet_ffprobe(
                        ffprobe,
                        invocation_log=root / f"{stream_type}.jsonl",
                        stream_document=document,
                        first_packet_document={"packets": []},
                        tail_packet_document={"packets": []},
                    )

                    with self.assertRaisesRegex(
                        ValueError, rf"non-audio streams.*{stream_type}"
                    ):
                        probe_audio(source, ffprobe=ffprobe)

    def test_capability_requires_exact_pcm24_row_with_encoder_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ffprobe = _write_version_only_ffprobe(root / "ffprobe-fake")
            ffmpeg = _write_capability_ffmpeg(
                root / "ffmpeg-fake",
                codecs=(
                    " D.AI.S pcm_s24le PCM signed 24-bit little-endian\n"
                    " DEAI.S pcm_s24le_planar PCM signed 24-bit planar\n"
                    " D..... decoy description mentions pcm_s24le\n"
                ),
            )

            unavailable = decoder_capability_report(
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
            )

            self.assertFalse(
                unavailable["policy"]["pcm24_encoder_available"]
            )

            _write_capability_ffmpeg(
                ffmpeg,
                codecs=(
                    " DEAI.S pcm_s24le PCM signed 24-bit little-endian\n"
                ),
            )
            available = decoder_capability_report(
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
            )
            self.assertTrue(available["policy"]["pcm24_encoder_available"])

    @unittest.skipUnless(
        _installed_encoder_available("aac"),
        "installed FFmpeg AAC encoder is unavailable",
    )
    def test_installed_ffmpeg_aac_priming_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.wav"
            encoded = root / "encoded.m4a"
            _write_sine_wav(source)
            _encode(source, encoded, encoder="aac")

            result = probe_audio(
                encoded,
                ffprobe=Path(FFPROBE or ""),
            )

            self.assertEqual(result.codec, "aac")
            self.assertGreater(result.skip_samples, 0)
            self.assertEqual(
                result.first_retained_source_sample,
                result.skip_samples,
            )

    @unittest.skipUnless(
        _installed_encoder_available("libmp3lame"),
        "installed FFmpeg libmp3lame encoder is unavailable",
    )
    def test_installed_ffmpeg_mp3_priming_and_tail_are_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.wav"
            encoded = root / "encoded.mp3"
            _write_sine_wav(source)
            _encode(source, encoded, encoder="libmp3lame")

            result = probe_audio(
                encoded,
                ffprobe=Path(FFPROBE or ""),
            )

            self.assertEqual(result.codec, "mp3")
            self.assertGreater(result.skip_samples, 0)
            self.assertGreater(result.discard_padding_samples, 0)
            self.assertEqual(
                result.decoder_padding_samples,
                result.discard_padding_samples,
            )


def _probe_document(
    *,
    suffix_format: str,
    codec: str,
) -> dict:
    return {
        "streams": [
            {
                "index": 0,
                "codec_name": codec,
                "codec_type": "audio",
                "sample_fmt": "fltp",
                "sample_rate": "44100",
                "channels": 2,
                "channel_layout": "stereo",
                "time_base": "1/44100",
                "start_pts": 0,
                "start_time": "0.000000",
                "duration_ts": 132300,
                "duration": "3.000000",
                "initial_padding": 0,
                "trailing_padding": 0,
            }
        ],
        "format": {
            "format_name": suffix_format,
            "start_time": "0.000000",
            "duration": "3.000000",
        },
    }


def _write_packet_ffprobe(
    path: Path,
    *,
    invocation_log: Path,
    stream_document: dict,
    first_packet_document: dict,
    tail_packet_document: dict,
) -> Path:
    path.write_text(
        f"""#!{sys.executable}
import json
import sys
arguments = sys.argv[1:]
with open({str(invocation_log)!r}, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(arguments) + "\\n")
if "-version" in arguments:
    print("ffprobe version sunofriend-boundary-test")
elif "-show_packets" in arguments:
    interval = arguments[arguments.index("-read_intervals") + 1]
    if interval.startswith("%"):
        print({json.dumps(json.dumps(first_packet_document))})
    else:
        print({json.dumps(json.dumps(tail_packet_document))})
else:
    print({json.dumps(json.dumps(stream_document))})
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _write_version_only_ffprobe(path: Path) -> Path:
    path.write_text(
        f"""#!{sys.executable}
print("ffprobe version sunofriend-boundary-test")
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _write_capability_ffmpeg(path: Path, *, codecs: str) -> Path:
    path.write_text(
        f"""#!{sys.executable}
import sys
if "-version" in sys.argv:
    print("ffmpeg version sunofriend-boundary-test")
elif "-formats" in sys.argv:
    print(" D  wav")
elif "-codecs" in sys.argv:
    print({codecs!r}, end="")
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _write_sine_wav(path: Path) -> None:
    sample_rate = 44100
    frame_count = sample_rate * 3 + 123
    amplitude = 12000
    frames = bytearray()
    for index in range(frame_count):
        sample = round(
            amplitude * math.sin(2.0 * math.pi * 440.0 * index / sample_rate)
        )
        frames.extend(struct.pack("<h", sample))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(frames)


def _encode(source: Path, target: Path, *, encoder: str) -> None:
    completed = subprocess.run(
        [
            FFMPEG or "",
            "-v",
            "error",
            "-y",
            "-protocol_whitelist",
            "file",
            "-i",
            str(source),
            "-map_metadata",
            "-1",
            "-vn",
            "-sn",
            "-dn",
            "-c:a",
            encoder,
            str(target),
        ],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode:
        raise AssertionError(
            f"FFmpeg {encoder} fixture encoding failed: {completed.stderr}"
        )


if __name__ == "__main__":
    unittest.main()
