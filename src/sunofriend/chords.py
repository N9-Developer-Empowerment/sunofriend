from __future__ import annotations

import csv
import itertools
import re
from pathlib import Path

from .grid import seconds_per_beat
from .models import ChordChart, ChordSegment, NoteEvent

NOTE_TO_PC = {
    "C": 0,
    "B#": 0,
    "C#": 1,
    "DB": 1,
    "D": 2,
    "D#": 3,
    "EB": 3,
    "E": 4,
    "FB": 4,
    "F": 5,
    "E#": 5,
    "F#": 6,
    "GB": 6,
    "G": 7,
    "G#": 8,
    "AB": 8,
    "A": 9,
    "A#": 10,
    "BB": 10,
    "B": 11,
    "CB": 11,
}

MAJOR_SCALE = (0, 2, 4, 5, 7, 9, 11)
MINOR_SCALE = (0, 2, 3, 5, 7, 8, 10)
CHORD_TOKEN_RE = re.compile(r"^[A-G](?:#|b)?(?:m|min|maj7|maj|m7|7|sus2|sus4|sus|dim|aug|add9)?$", re.I)


def extract_chords_from_moises_pdf(path: str | Path) -> ChordChart:
    data = Path(path).read_bytes()
    strings = [_decode_pdf_literal(match.group(1)) for match in re.finditer(rb"\((.*?)\)\s*Tj", data, re.S)]

    key: str | None = None
    chords: list[str] = []
    for text in strings:
        text = " ".join(text.split())
        if not text:
            continue
        if text.lower().startswith("key:"):
            key = text.split(":", 1)[1].strip()
            continue
        if "chords generated" in text.lower():
            break

        tokens = text.split()
        if tokens and all(_looks_like_chord(token) for token in tokens):
            chords.extend(tokens)

    if not chords:
        raise ValueError(f"No chord names found in {path}")
    return ChordChart(key=key, chords=chords)


def write_chord_csv(path: str | Path, segments: list[ChordSegment]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["start", "end", "chord"])
        for segment in segments:
            writer.writerow([f"{segment.start:.3f}", f"{segment.end:.3f}", segment.name])


def make_chord_segments(chords: list[str], duration_seconds: float, bpm: float | None = None) -> list[ChordSegment]:
    if not chords:
        raise ValueError("At least one chord is required")
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be greater than zero")

    if bpm:
        beat = seconds_per_beat(bpm)
        total_beats = max(len(chords), round(duration_seconds / beat))
        boundaries = [round(index * total_beats / len(chords)) * beat for index in range(len(chords) + 1)]
        boundaries[0] = 0.0
        boundaries[-1] = duration_seconds
    else:
        step = duration_seconds / len(chords)
        boundaries = [index * step for index in range(len(chords))] + [duration_seconds]

    segments = []
    for index, chord in enumerate(chords):
        pcs = parse_chord_name(chord)
        if not pcs:
            continue
        start = boundaries[index]
        end = boundaries[index + 1]
        if end <= start:
            end = min(duration_seconds, start + seconds_per_beat(bpm)) if bpm else start
        segments.append(ChordSegment(start=start, end=end, name=chord, pitch_classes=tuple(pcs)))
    return segments


def parse_key(key_name: str | None) -> set[int] | None:
    if not key_name:
        return None
    match = re.match(r"^\s*([A-Ga-g])([#b]?)(?:\s+)?(.*)$", key_name)
    if not match:
        return None
    root = _normalize_root(match.group(1), match.group(2))
    if root not in NOTE_TO_PC:
        return None

    mode = match.group(3).strip().lower()
    intervals = MINOR_SCALE if mode.startswith("min") or mode == "m" else MAJOR_SCALE
    root_pc = NOTE_TO_PC[root]
    return {(root_pc + interval) % 12 for interval in intervals}


def parse_chord_name(chord_name: str | None) -> list[int] | None:
    if chord_name is None:
        return None
    name = str(chord_name).strip()
    if not name or name.upper() in {"N", "NC", "N.C.", "-", "NO"}:
        return None

    name = name.split("/", 1)[0].strip()
    match = re.match(r"^([A-Ga-g])([#b]?)(.*)$", name)
    if not match:
        return None

    root = _normalize_root(match.group(1), match.group(2))
    suffix = match.group(3).strip().lower()
    if root not in NOTE_TO_PC:
        return None
    root_pc = NOTE_TO_PC[root]

    if suffix.startswith(("maj7", "ma7")):
        intervals = [0, 4, 7, 11]
    elif suffix.startswith(("m7", "min7", "-7")):
        intervals = [0, 3, 7, 10]
    elif suffix.startswith(("m", "min", "-")) and not suffix.startswith(("maj", "ma")):
        intervals = [0, 3, 7]
    elif suffix.startswith("sus2"):
        intervals = [0, 2, 7]
    elif suffix.startswith(("sus4", "sus")):
        intervals = [0, 5, 7]
    elif suffix.startswith("dim"):
        intervals = [0, 3, 6]
    elif suffix.startswith(("aug", "+")):
        intervals = [0, 4, 8]
    elif suffix.startswith("7"):
        intervals = [0, 4, 7, 10]
    else:
        intervals = [0, 4, 7]

    if "add9" in suffix or suffix.endswith("9"):
        intervals.append(14)

    pcs: list[int] = []
    for interval in intervals:
        pc = (root_pc + interval) % 12
        if pc not in pcs:
            pcs.append(pc)
    return pcs


def choose_voicing(
    pcs: list[int] | tuple[int, ...],
    previous: list[int] | None,
    low: int = 48,
    high: int = 76,
    target_mid: float = 62.0,
    max_span: int = 24,
) -> list[int]:
    candidate_lists = [[pitch for pitch in range(low, high + 1) if pitch % 12 == pc] for pc in pcs]
    candidates: list[tuple[float, list[int]]] = []
    for combo in itertools.product(*candidate_lists):
        voicing = sorted(set(combo))
        if len(voicing) != len(pcs):
            continue
        span = max(voicing) - min(voicing)
        if span > max_span:
            continue
        center = sum(voicing) / len(voicing)
        cost = abs(center - target_mid) * 0.4 + span * 0.2
        if previous:
            old = sorted(previous)
            movement = sum(abs(a - b) for a, b in zip(voicing, old))
            movement += abs(len(voicing) - len(old)) * 8
            cost += movement
        candidates.append((cost, voicing))
    if not candidates:
        return []
    return min(candidates, key=lambda item: item[0])[1]


def generate_pad_notes(segments: list[ChordSegment], velocity: int = 72) -> list[NoteEvent]:
    notes: list[NoteEvent] = []
    previous: list[int] | None = None
    for segment in segments:
        voicing = choose_voicing(segment.pitch_classes, previous)
        previous = voicing
        for pitch in voicing:
            notes.append(NoteEvent(segment.start, segment.end, pitch, velocity))
    return notes


def chord_at_time(segments: list[ChordSegment], time_seconds: float) -> ChordSegment | None:
    for segment in segments:
        if segment.start <= time_seconds < segment.end:
            return segment
    if segments and time_seconds >= segments[-1].end:
        return segments[-1]
    return None


def _looks_like_chord(token: str) -> bool:
    return bool(CHORD_TOKEN_RE.match(token)) and parse_chord_name(token) is not None


def _normalize_root(letter: str, accidental: str) -> str:
    return f"{letter.upper()}{accidental.replace('b', 'B')}".upper()


def _decode_pdf_literal(raw: bytes) -> str:
    text = raw.decode("latin-1", errors="ignore")
    text = text.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
    return text
