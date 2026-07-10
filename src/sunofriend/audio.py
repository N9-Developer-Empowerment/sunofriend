from __future__ import annotations

import math
import wave
from pathlib import Path

from .grid import quantize_time, seconds_to_beats
from .models import StemAnalysis, StemEvent


def analyze_stem_activity(
    path: str | Path,
    bpm: float,
    grid_subdiv: int = 4,
    threshold_ratio: float = 0.24,
    min_gap_beats: float = 0.5,
) -> StemAnalysis:
    path = Path(path)
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        sample_rate = handle.getframerate()
        frame_count = handle.getnframes()
        duration = frame_count / sample_rate
        hop_seconds = 60.0 / bpm / grid_subdiv
        hop_frames = max(1, int(round(hop_seconds * sample_rate)))
        envelope = _read_rms_envelope(handle, channels, sample_width, hop_frames)

    if not envelope:
        return StemAnalysis(path=path, sample_rate=sample_rate, duration_seconds=duration, hop_seconds=hop_seconds, peak_rms=0.0, events=[])

    peak = max(envelope)
    threshold = max(peak * threshold_ratio, 0.01)
    raw_events = _events_from_envelope(envelope, threshold=threshold, hop_seconds=hop_seconds, bpm=bpm)
    events = _dedupe_events(raw_events, bpm=bpm, min_gap_beats=min_gap_beats, grid_subdiv=grid_subdiv)
    return StemAnalysis(path=path, sample_rate=sample_rate, duration_seconds=round(duration, 3), hop_seconds=hop_seconds, peak_rms=peak, events=events)


def _read_rms_envelope(
    handle: wave.Wave_read,
    channels: int,
    sample_width: int,
    hop_frames: int,
) -> list[float]:
    envelope: list[float] = []
    max_abs = float((1 << (sample_width * 8 - 1)) - 1) if sample_width > 1 else 128.0

    while True:
        data = handle.readframes(hop_frames)
        if not data:
            break
        rms = _rms_from_pcm(data, sample_width)
        if rms is None:
            envelope.append(0.0)
            continue
        envelope.append(rms / max_abs)
    return envelope


def _rms_from_pcm(data: bytes, sample_width: int) -> float | None:
    square_sum = 0
    count = 0
    if sample_width == 1:
        for byte in data:
            sample = byte - 128
            square_sum += sample * sample
            count += 1
    elif sample_width == 2:
        for i in range(0, len(data) - 1, 2):
            sample = int.from_bytes(data[i : i + 2], "little", signed=True)
            square_sum += sample * sample
            count += 1
    elif sample_width == 3:
        for i in range(0, len(data) - 2, 3):
            chunk = data[i : i + 3]
            sign = b"\xff" if chunk[2] & 0x80 else b"\x00"
            sample = int.from_bytes(chunk + sign, "little", signed=True)
            square_sum += sample * sample
            count += 1
    elif sample_width == 4:
        for i in range(0, len(data) - 3, 4):
            sample = int.from_bytes(data[i : i + 4], "little", signed=True)
            square_sum += sample * sample
            count += 1
    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")

    if count == 0:
        return None
    return math.sqrt(square_sum / count)


def _samples_from_pcm(data: bytes, sample_width: int) -> list[int]:
    if sample_width == 1:
        return [byte - 128 for byte in data]
    if sample_width == 2:
        return [int.from_bytes(data[i : i + 2], "little", signed=True) for i in range(0, len(data) - 1, 2)]
    if sample_width == 3:
        samples = []
        for i in range(0, len(data) - 2, 3):
            chunk = data[i : i + 3]
            sign = b"\xff" if chunk[2] & 0x80 else b"\x00"
            samples.append(int.from_bytes(chunk + sign, "little", signed=True))
        return samples
    if sample_width == 4:
        return [int.from_bytes(data[i : i + 4], "little", signed=True) for i in range(0, len(data) - 3, 4)]
    raise ValueError(f"Unsupported WAV sample width: {sample_width}")


def _downmix(values: list[int], channels: int) -> list[int]:
    frames = len(values) // channels
    mixed = []
    for frame in range(frames):
        start = frame * channels
        mixed.append(sum(values[start : start + channels]) // channels)
    return mixed


def _events_from_envelope(envelope: list[float], threshold: float, hop_seconds: float, bpm: float) -> list[StemEvent]:
    events: list[StemEvent] = []
    index = 0
    while index < len(envelope):
        if envelope[index] < threshold:
            index += 1
            continue
        start = index
        best = index
        best_value = envelope[index]
        while index < len(envelope) and envelope[index] >= threshold:
            if envelope[index] > best_value:
                best = index
                best_value = envelope[index]
            index += 1
        time = best * hop_seconds
        events.append(StemEvent(time=time, beat=seconds_to_beats(time, bpm), strength=best_value))
        if index == start:
            index += 1
    return events


def _dedupe_events(
    events: list[StemEvent],
    bpm: float,
    min_gap_beats: float,
    grid_subdiv: int,
) -> list[StemEvent]:
    by_time: dict[float, StemEvent] = {}
    min_gap_seconds = 60.0 / bpm * min_gap_beats
    for event in sorted(events, key=lambda item: item.strength, reverse=True):
        snapped = quantize_time(event.time, bpm=bpm, subdiv=grid_subdiv)
        if any(abs(snapped - existing) < min_gap_seconds for existing in by_time):
            continue
        by_time[snapped] = StemEvent(time=snapped, beat=seconds_to_beats(snapped, bpm), strength=event.strength)
    return [by_time[key] for key in sorted(by_time)]
