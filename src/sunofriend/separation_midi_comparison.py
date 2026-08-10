"""Shared audio, MIDI and publication primitives for private comparisons."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import stat
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from .models import NoteEvent
from .separation_fine_stem_canary_audio import (
    PCM24_MAX,
    PCM24_MIN,
    PCM24_SCALE,
    file_sha256,
)


SAMPLE_RATE_HZ = 44_100
FRAMES = 661_500
TRANSCRIPTION_PARAMETERS = {
    "onset_threshold": 0.5,
    "frame_threshold": 0.3,
    "min_note_ms": 60.0,
}

Transcriber = Callable[..., Sequence[NoteEvent]]
Renderer = Callable[[Path, Path], Any]


def regular_inside(root: Path, relative: str, label: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise ValueError(f"{label} must use a relative path")
    root = root.resolve(strict=True)
    path = (root / relative).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} escapes its evidence root") from error
    details = path.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise ValueError(f"{label} is not a regular non-link file")
    return path


def verify_audio_identity(
    root: Path, identity: Mapping[str, Any], label: str
) -> Path:
    import soundfile as sf

    path = regular_inside(root, str(identity.get("relative_path", "")), label)
    if path.stat().st_size != identity.get("bytes"):
        raise ValueError(f"{label} byte count changed")
    if file_sha256(path) != identity.get("sha256"):
        raise ValueError(f"{label} SHA-256 changed")
    info = sf.info(path)
    if (
        info.samplerate != identity.get("sample_rate_hz")
        or info.channels != identity.get("channels")
        or info.frames != identity.get("frames")
        or info.subtype != identity.get("subtype")
        or info.samplerate != SAMPLE_RATE_HZ
        or info.channels != 2
        or info.frames != FRAMES
        or info.subtype != "PCM_24"
    ):
        raise ValueError(f"{label} PCM24 geometry changed")
    return path


def read_pcm24_integer(path: Path) -> np.ndarray:
    import soundfile as sf

    value = sf.read(path, dtype="float64", always_2d=True)[0]
    if value.shape != (FRAMES, 2) or not np.isfinite(value).all():
        raise ValueError("fine-stem MIDI input samples differ")
    integer = np.rint(value * PCM24_SCALE).astype(np.int64)
    if integer.min(initial=0) < PCM24_MIN or integer.max(initial=0) > PCM24_MAX:
        raise ValueError("fine-stem MIDI input exceeds PCM24")
    return integer


def audio_artifact(path: Path) -> dict[str, Any]:
    return {
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "channels": 2,
        "frames": FRAMES,
        "subtype": "PCM_24",
    }


def write_pcm24(path: Path, integer: np.ndarray) -> dict[str, Any]:
    import soundfile as sf

    value = np.asarray(integer, dtype=np.int64)
    if (
        value.shape != (FRAMES, 2)
        or value.min(initial=0) < PCM24_MIN
        or value.max(initial=0) > PCM24_MAX
    ):
        raise ValueError("fine-stem MIDI PCM24 output differs")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.path.lexists(path):
        raise FileExistsError(f"fine-stem MIDI artifact already exists: {path}")
    sf.write(
        path,
        value.astype(np.float64) / PCM24_SCALE,
        SAMPLE_RATE_HZ,
        format="WAV",
        subtype="PCM_24",
    )
    path.chmod(0o600)
    persisted = sf.read(path, dtype="float64", always_2d=True)[0]
    persisted_integer = np.rint(persisted * PCM24_SCALE).astype(np.int64)
    if not np.array_equal(persisted_integer, value):
        raise RuntimeError("fine-stem MIDI PCM24 persistence changed samples")
    return audio_artifact(path)


def artifact(path: Path, root: Path) -> dict[str, Any]:
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def validated_notes(values: Sequence[NoteEvent]) -> list[NoteEvent]:
    result: list[NoteEvent] = []
    for value in values:
        note = NoteEvent(
            start=float(value.start),
            end=float(value.end),
            pitch=int(value.pitch),
            velocity=int(value.velocity),
        )
        if (
            not math.isfinite(note.start)
            or not math.isfinite(note.end)
            or note.start < 0
            or note.end <= note.start
            or note.end > 15.25
            or not 0 <= note.pitch <= 127
            or not 1 <= note.velocity <= 127
        ):
            raise ValueError("fine-stem MIDI transcriber returned an invalid note")
        result.append(note)
    result.sort(key=lambda item: (item.start, item.pitch, item.end, item.velocity))
    return result


def write_notes(path: Path, notes: Sequence[NoteEvent]) -> dict[str, Any]:
    payload = {
        "schema": "sunofriend.fine-stem-downstream-midi-notes.v1",
        "notes": [
            {
                "start": note.start,
                "end": note.end,
                "pitch": note.pitch,
                "velocity": note.velocity,
            }
            for note in notes
        ],
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return payload


def render_to_fixed_float(
    midi_path: Path,
    raw_path: Path,
    *,
    notes: Sequence[NoteEvent],
    render: Renderer,
) -> tuple[np.ndarray, str]:
    import soundfile as sf

    if not notes:
        return np.zeros((FRAMES, 2), dtype=np.float64), "silence_no_notes"
    render(midi_path, raw_path)
    value, sample_rate = sf.read(raw_path, dtype="float64", always_2d=True)
    if sample_rate != SAMPLE_RATE_HZ or not np.isfinite(value).all():
        raise RuntimeError("neutral MIDI renderer clock or samples differ")
    if value.shape[1] == 1:
        value = np.repeat(value, 2, axis=1)
    if value.shape[1] != 2:
        raise RuntimeError("neutral MIDI renderer channel count differs")
    fixed = np.zeros((FRAMES, 2), dtype=np.float64)
    copied = min(FRAMES, len(value))
    fixed[:copied] = value[:copied]
    return fixed, "fluidsynth_dry_general_midi"


def match_preview_loudness(
    values: Mapping[str, np.ndarray],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Loudness-match two or more neutral previews without ranking them."""

    if len(values) < 2:
        raise ValueError("at least two preview arms are required")
    ordered = {
        key: np.asarray(value, dtype=np.float64) for key, value in values.items()
    }
    if any(value.shape != (FRAMES, 2) for value in ordered.values()):
        raise ValueError("preview geometry differs")
    rms = {
        key: float(np.sqrt(np.mean(np.square(value))))
        for key, value in ordered.items()
    }
    peaks = {
        key: float(np.max(np.abs(value), initial=0.0))
        for key, value in ordered.items()
    }
    target = 10 ** (-24.0 / 20.0)
    nonzero = [key for key, value in rms.items() if value > 1e-12]
    if len(nonzero) == len(ordered):
        achievable = [
            rms[key] * (0.7 / peaks[key]) if peaks[key] > 0 else target
            for key in nonzero
        ]
        matched = min(target, *achievable)
        gains = {key: matched / value for key, value in rms.items()}
        status = "matched"
    else:
        gains = {
            key: (
                min(target / value, 0.7 / peaks[key])
                if value > 1e-12 and peaks[key] > 0
                else 1.0
            )
            for key, value in rms.items()
        }
        status = "not_applicable_one_or_more_silent"
    integers = {
        key: np.rint(np.clip(value * gains[key], -0.7, 0.7) * PCM24_SCALE).astype(
            np.int64
        )
        for key, value in ordered.items()
    }
    post_rms = {
        key: float(
            np.sqrt(np.mean(np.square(value.astype(np.float64) / PCM24_SCALE)))
        )
        for key, value in integers.items()
    }
    return integers, {
        "policy": "all-arm RMS matched at or below -24 dBFS with -3.10 dBFS peak cap",
        "status": status,
        "pre_rms": rms,
        "pre_peak": peaks,
        "gains": gains,
        "post_rms": post_rms,
    }


def make_private(root: Path) -> None:
    for directory, child_directories, files in os.walk(root):
        Path(directory).chmod(0o700)
        for name in child_directories:
            (Path(directory) / name).chmod(0o700)
        for name in files:
            (Path(directory) / name).chmod(0o600)


__all__ = [
    "FRAMES",
    "Renderer",
    "SAMPLE_RATE_HZ",
    "TRANSCRIPTION_PARAMETERS",
    "Transcriber",
    "artifact",
    "audio_artifact",
    "make_private",
    "match_preview_loudness",
    "read_pcm24_integer",
    "regular_inside",
    "render_to_fixed_float",
    "validated_notes",
    "verify_audio_identity",
    "write_notes",
    "write_pcm24",
]
