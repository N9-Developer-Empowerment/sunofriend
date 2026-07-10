from __future__ import annotations


def seconds_per_beat(bpm: float) -> float:
    if bpm <= 0:
        raise ValueError("BPM must be greater than zero")
    return 60.0 / bpm


def seconds_per_bar(bpm: float, beats_per_bar: int = 4) -> float:
    if beats_per_bar <= 0:
        raise ValueError("beats_per_bar must be greater than zero")
    return seconds_per_beat(bpm) * beats_per_bar


def quantize_time(seconds: float, bpm: float, subdiv: int = 4) -> float:
    if subdiv <= 0:
        raise ValueError("subdiv must be greater than zero")
    grid = seconds_per_beat(bpm) / subdiv
    return round(seconds / grid) * grid


def seconds_to_beats(seconds: float, bpm: float) -> float:
    return seconds / seconds_per_beat(bpm)


def beats_to_seconds(beats: float, bpm: float) -> float:
    return beats * seconds_per_beat(bpm)
