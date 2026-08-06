"""Offline worker for Sunofriend's public experimental two-stem alpha."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import time
import wave

from sunofriend._separation_melroformer_real_bridge import (
    MAXIMUM_EXCERPT_FRAMES,
    MINIMUM_PROBE_FRAMES,
    _infer_private_melroformer_excerpt,
    _load_private_melroformer_model,
)


SAMPLE_RATE = 44_100
CHANNELS = 2
TARGET_PEAK = 0.99
MAXIMUM_PRE_ATTENUATION_PEAK = 4.0


def chunk_boundaries(frames: int) -> list[tuple[int, int]]:
    if frames < MINIMUM_PROBE_FRAMES:
        raise ValueError("source is too short for experimental separation")
    count = math.ceil(frames / MAXIMUM_EXCERPT_FRAMES)
    if count == 1:
        return [(0, frames)]
    boundaries = [
        (index * MAXIMUM_EXCERPT_FRAMES, min(frames, (index + 1) * MAXIMUM_EXCERPT_FRAMES))
        for index in range(count)
    ]
    if boundaries[-1][1] - boundaries[-1][0] < MINIMUM_PROBE_FRAMES:
        final_end = boundaries[-1][1]
        final_start = final_end - MINIMUM_PROBE_FRAMES
        previous_start, _ = boundaries[-2]
        boundaries[-2] = (previous_start, final_start)
        boundaries[-1] = (final_start, final_end)
    if any(
        end - start < MINIMUM_PROBE_FRAMES
        or end - start > MAXIMUM_EXCERPT_FRAMES
        for start, end in boundaries
    ):
        raise ValueError("source cannot be partitioned into supported chunks")
    return boundaries


def decode_pcm24(contents: bytes, *, np):
    packed = np.frombuffer(contents, dtype=np.uint8).reshape(-1, 3)
    unsigned = (
        packed[:, 0].astype(np.int32)
        | (packed[:, 1].astype(np.int32) << 8)
        | (packed[:, 2].astype(np.int32) << 16)
    )
    signed = np.where(unsigned & 0x800000, unsigned - 0x1000000, unsigned)
    return (signed.astype(np.float32) / 8_388_608.0).reshape(-1, CHANNELS)


def pack_pcm24(values, *, np) -> bytes:
    unsigned = values.astype(np.int32).reshape(-1) & 0xFFFFFF
    packed = np.empty((len(unsigned), 3), dtype=np.uint8)
    packed[:, 0] = unsigned & 0xFF
    packed[:, 1] = (unsigned >> 8) & 0xFF
    packed[:, 2] = (unsigned >> 16) & 0xFF
    return packed.tobytes()


def _read_source(path: Path, *, np):
    with wave.open(str(path), "rb") as reader:
        if (
            reader.getnchannels() != CHANNELS
            or reader.getsampwidth() != 3
            or reader.getframerate() != SAMPLE_RATE
            or reader.getcomptype() != "NONE"
        ):
            raise ValueError("worker source must be PCM24 stereo 44.1 kHz WAV")
        frames = reader.getnframes()
        contents = reader.readframes(frames)
        if reader.readframes(1):
            raise ValueError("worker source contains undeclared frames")
    audio = decode_pcm24(contents, np=np)
    if audio.shape != (frames, CHANNELS):
        raise ValueError("worker source geometry differs")
    return audio


def _write_wave(path: Path, values, *, np) -> dict[str, object]:
    quantized = np.clip(
        np.rint(values.astype(np.float64) * 8_388_608.0),
        -8_388_608,
        8_388_607,
    ).astype(np.int32)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(CHANNELS)
        writer.setsampwidth(3)
        writer.setframerate(SAMPLE_RATE)
        block = 65_536
        for start in range(0, len(quantized), block):
            writer.writeframes(pack_pcm24(quantized[start : start + block], np=np))
    return {
        "frames": len(quantized),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "quantized": quantized,
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    import numpy as np

    started = time.perf_counter()
    source_path = args.source.expanduser().absolute()
    destination = args.destination.expanduser().absolute()
    result_path = args.result.expanduser().absolute()
    if result_path.parent != destination:
        raise ValueError("worker result must be directly inside destination")
    source = _read_source(source_path, np=np)
    boundaries = chunk_boundaries(len(source))
    handle = _load_private_melroformer_model(
        source_root=args.source_root,
        checkpoint_path=args.checkpoint,
        companion_root=args.companion_root,
        device=args.device,
    )
    raw = destination / "TEMP/worker-raw"
    raw.mkdir(parents=True, exist_ok=False)
    vocal_path = raw / "vocals.f32"
    instrumental_path = raw / "instrumental.f32"
    chunks: list[dict[str, object]] = []
    peak = float(np.max(np.abs(source)))
    with vocal_path.open("wb") as vocal_stream, instrumental_path.open("wb") as instrumental_stream:
        for index, (start, end) in enumerate(boundaries):
            observation = _infer_private_melroformer_excerpt(
                handle,
                np.ascontiguousarray(source[start:end], dtype=np.float32),
                sample_rate=SAMPLE_RATE,
            )
            vocals = np.asarray(observation.vocals, dtype=np.float32)
            instrumental = np.asarray(observation.instrumental, dtype=np.float32)
            if vocals.shape != source[start:end].shape or instrumental.shape != vocals.shape:
                raise ValueError("worker output geometry differs")
            local_peak = max(
                float(np.max(np.abs(vocals))),
                float(np.max(np.abs(instrumental))),
            )
            if not math.isfinite(local_peak) or local_peak > MAXIMUM_PRE_ATTENUATION_PEAK:
                raise ValueError("worker output peak exceeds the public persistence bound")
            peak = max(peak, local_peak)
            vocal_stream.write(vocals.tobytes(order="C"))
            instrumental_stream.write(instrumental.tobytes(order="C"))
            chunks.append(
                {
                    "index": index,
                    "start_frame": start,
                    "end_frame": end,
                    "frames": end - start,
                    "inference_seconds": observation.evidence["measurement"]["inference_seconds"],
                    "peak_memory_bytes": observation.evidence["measurement"]["peak_memory_bytes"],
                }
            )
            handle.mx.clear_cache()
    expected_raw_bytes = len(source) * CHANNELS * 4
    if vocal_path.stat().st_size != expected_raw_bytes or instrumental_path.stat().st_size != expected_raw_bytes:
        raise ValueError("worker raw output byte count differs")
    vocals = np.memmap(vocal_path, mode="r", dtype=np.float32, shape=source.shape)
    instrumental = np.memmap(
        instrumental_path, mode="r", dtype=np.float32, shape=source.shape
    )
    gain = min(1.0, TARGET_PEAK / peak) if peak else 1.0
    source_scaled = source * gain
    vocal_scaled = np.asarray(vocals) * gain
    instrumental_scaled = np.asarray(instrumental) * gain
    (destination / "STEMS").mkdir(exist_ok=False)
    (destination / "SOURCE").mkdir(exist_ok=False)
    (destination / "AUDIO").mkdir(exist_ok=False)
    source_claim = _write_wave(
        destination / "SOURCE/source-reference.wav", source_scaled, np=np
    )
    vocal_claim = _write_wave(destination / "STEMS/vocals.wav", vocal_scaled, np=np)
    instrumental_claim = _write_wave(
        destination / "STEMS/instrumental.wav", instrumental_scaled, np=np
    )
    reconstruction_int = (
        vocal_claim.pop("quantized").astype(np.int64)
        + instrumental_claim.pop("quantized").astype(np.int64)
    )
    reconstruction = np.clip(
        reconstruction_int, -8_388_608, 8_388_607
    ).astype(np.float64) / 8_388_608.0
    reconstruction_claim = _write_wave(
        destination / "AUDIO/reconstruction-check.wav", reconstruction, np=np
    )
    source_quantized = source_claim.pop("quantized")
    reconstruction_quantized = reconstruction_claim.pop("quantized")
    maximum_error_lsb = int(
        np.max(
            np.abs(
                source_quantized.astype(np.int64)
                - reconstruction_quantized.astype(np.int64)
            )
        )
    )
    if maximum_error_lsb > 2:
        raise ValueError("persisted stems exceed the reconstruction tolerance")
    del vocals, instrumental
    vocal_path.unlink()
    instrumental_path.unlink()
    raw.rmdir()
    document: dict[str, object] = {
        "schema": "sunofriend.experimental-separation-worker.v1",
        "status": "complete_unreviewed",
        "sample_rate": SAMPLE_RATE,
        "channels": CHANNELS,
        "frames": len(source),
        "duration_seconds": len(source) / SAMPLE_RATE,
        "chunk_policy": "contiguous_maximum_15_seconds_no_crossfade_v1",
        "chunks": chunks,
        "level_management": {
            "policy": "shared_linear_attenuation_if_pcm_range_exceeded",
            "original_maximum_absolute_peak": peak,
            "shared_linear_gain": gain,
            "target_peak": TARGET_PEAK,
        },
        "additive_accounting": {
            "equation": "source_reference = vocals + instrumental within PCM24 rounding",
            "maximum_absolute_error_lsb": maximum_error_lsb,
            "tolerance_lsb": 2,
            "passed": True,
        },
        "outputs": {
            "source_reference": source_claim,
            "vocals": vocal_claim,
            "instrumental": instrumental_claim,
            "reconstruction_check": reconstruction_claim,
        },
        "runtime": {
            "device": args.device,
            "checkpoint_sha256": handle.evidence["checkpoint"]["sha256"],
            "source_revision": handle.evidence["source"]["revision"],
            "network_used": False,
        },
        "elapsed_seconds": time.perf_counter() - started,
    }
    result_path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return document


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--companion-root", type=Path, required=True)
    parser.add_argument("--device", choices=("gpu", "cpu"), default="gpu")
    return parser


def main() -> int:
    run(build_parser().parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
