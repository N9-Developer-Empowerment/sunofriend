"""Copyright-safe active four-role fixture for core-four activation evidence."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
from typing import Any

from .separation_demucs_mlx_worker import (
    PCM24_MAX,
    PCM24_MIN,
    PCM24_SCALE,
    write_pcm24_integers,
)


FIXTURE_SCHEMA = "sunofriend.core-four-synthetic-fixture.v1"
FIXTURE_POLICY_ID = "active-mathematical-four-role-60-second-v1"
SAMPLE_RATE = 44_100
DURATION_SECONDS = 60.0
FRAMES = int(SAMPLE_RATE * DURATION_SECONDS)
ROLES = ("vocals", "drums", "bass", "other")


def create_core_four_synthetic_fixture(destination: str | Path) -> dict[str, Any]:
    """Create deterministic active vocals, drums, bass and other references."""

    import numpy as np

    root = Path(destination).expanduser().absolute()
    if os.path.lexists(root):
        raise FileExistsError(f"core-four synthetic fixture already exists: {root}")
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(mode=0o700)
    try:
        references = _render_roles(np=np)
        truth_root = root / "GROUND-TRUTH"
        truth_root.mkdir(mode=0o700)
        outputs: dict[str, dict[str, Any]] = {}
        role_integers: dict[str, Any] = {}
        for role in ROLES:
            integers = _quantize(references[role], np=np)
            role_integers[role] = integers
            path = truth_root / f"{role}.wav"
            outputs[role] = {
                "path": str(path.relative_to(root)),
                **write_pcm24_integers(path, integers, np=np),
            }
        source_wide = sum(
            role_integers[role].astype(np.int64) for role in ROLES
        )
        if (
            int(source_wide.min()) < PCM24_MIN
            or int(source_wide.max()) > PCM24_MAX
        ):
            raise ValueError("synthetic four-role sum exceeds PCM24")
        source = source_wide.astype(np.int32)
        source_path = root / "core-four-synthetic-demo.wav"
        source_identity = {
            "path": str(source_path.relative_to(root)),
            **write_pcm24_integers(source_path, source, np=np),
        }
        reconstructed = sum(
            role_integers[role].astype(np.int64) for role in ROLES
        )
        if not np.array_equal(reconstructed, source.astype(np.int64)):
            raise RuntimeError("synthetic ground-truth references do not reconstruct")
        document: dict[str, Any] = {
            "schema": FIXTURE_SCHEMA,
            "policy_id": FIXTURE_POLICY_ID,
            "source_kind": (
                "fixed mathematical oscillators and seeded deterministic noise; "
                "no recordings, samples, lyrics or third-party audio"
            ),
            "geometry": {
                "sample_rate": SAMPLE_RATE,
                "channels": 2,
                "frames": FRAMES,
                "duration_seconds": DURATION_SECONDS,
                "pcm_bits": 24,
            },
            "roles": list(ROLES),
            "all_roles_active": all(
                bool(np.any(role_integers[role])) for role in ROLES
            ),
            "source": source_identity,
            "ground_truth": outputs,
            "additive_accounting": {
                "exact_pcm24_sum": True,
                "maximum_absolute_error_lsb": 0,
            },
            "permissions": {
                "bounded_local_model_evaluation": True,
                "profile_activation": False,
                "automatic_model_promotion": False,
                "automatic_midi_activation": False,
                "public_audio_upload": False,
            },
        }
        document["document_sha256"] = _document_sha256(document)
        manifest = root / "synthetic-fixture.json"
        manifest.write_text(
            json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        return {
            **document,
            "root": str(root),
            "manifest": str(manifest),
            "source_path": str(source_path),
            "ground_truth_paths": {
                role: str(truth_root / f"{role}.wav") for role in ROLES
            },
        }
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise


def _render_roles(*, np: Any) -> dict[str, Any]:
    rng = np.random.default_rng(0)

    bass = np.zeros(FRAMES, dtype=np.float64)
    bass_notes = (55.0, 65.406, 73.416, 49.0)
    note_frames = SAMPLE_RATE
    for index, start in enumerate(range(0, FRAMES, note_frames)):
        end = min(FRAMES, start + note_frames)
        local = np.arange(end - start, dtype=np.float64) / SAMPLE_RATE
        frequency = bass_notes[index % len(bass_notes)]
        envelope = np.minimum(1.0, local / 0.025) * np.exp(-0.32 * local)
        bass[start:end] = envelope * (
            np.sin(2 * np.pi * frequency * local)
            + 0.24 * np.sin(2 * np.pi * frequency * 2 * local)
        )
    bass = _peak_scaled(bass, 0.13, np=np)
    bass_stereo = np.column_stack((bass, bass))

    drums = np.zeros((FRAMES, 2), dtype=np.float64)
    beat = SAMPLE_RATE // 2
    for beat_index, start in enumerate(range(0, FRAMES, beat)):
        kick_length = min(int(0.22 * SAMPLE_RATE), FRAMES - start)
        kick_time = np.arange(kick_length, dtype=np.float64) / SAMPLE_RATE
        kick = np.sin(
            2
            * np.pi
            * (88.0 * kick_time - 34.0 * np.square(kick_time))
        ) * np.exp(-18.0 * kick_time)
        drums[start : start + kick_length] += 0.12 * kick[:, None]
        if beat_index % 2:
            snare_length = min(int(0.16 * SAMPLE_RATE), FRAMES - start)
            snare_time = np.arange(snare_length, dtype=np.float64) / SAMPLE_RATE
            snare = rng.standard_normal(snare_length) * np.exp(-25.0 * snare_time)
            drums[start : start + snare_length, 0] += 0.045 * snare
            drums[start : start + snare_length, 1] += 0.052 * snare
        for offset in (0, beat // 2):
            hat_start = start + offset
            if hat_start >= FRAMES:
                continue
            hat_length = min(int(0.045 * SAMPLE_RATE), FRAMES - hat_start)
            hat_time = np.arange(hat_length, dtype=np.float64) / SAMPLE_RATE
            noise = rng.standard_normal(hat_length)
            high = np.concatenate(([noise[0]], np.diff(noise)))
            hat = high * np.exp(-70.0 * hat_time)
            drums[hat_start : hat_start + hat_length, 0] += 0.018 * hat
            drums[hat_start : hat_start + hat_length, 1] += 0.014 * hat
    drums = _peak_scaled(drums, 0.16, np=np)

    other = np.zeros((FRAMES, 2), dtype=np.float64)
    chord_roots = (220.0, 261.626, 293.665, 196.0)
    chord_frames = 2 * SAMPLE_RATE
    for index, start in enumerate(range(0, FRAMES, chord_frames)):
        end = min(FRAMES, start + chord_frames)
        local = np.arange(end - start, dtype=np.float64) / SAMPLE_RATE
        root = chord_roots[index % len(chord_roots)]
        chord = sum(
            np.sin(2 * np.pi * root * ratio * local + phase)
            for ratio, phase in ((1.0, 0.0), (1.25, 0.4), (1.5, 0.8))
        )
        envelope = np.minimum(1.0, local / 0.12) * np.minimum(
            1.0, (end - start) / SAMPLE_RATE - local
        )
        other[start:end, 0] = chord * envelope
        other[start:end, 1] = np.roll(chord, 37) * envelope
    other = _peak_scaled(other, 0.14, np=np)

    vocals = np.zeros((FRAMES, 2), dtype=np.float64)
    melody = (220.0, 246.942, 277.183, 329.628, 293.665, 246.942)
    phrase_frames = 4 * SAMPLE_RATE
    syllable_frames = int(0.48 * SAMPLE_RATE)
    for phrase_index, phrase_start in enumerate(range(0, FRAMES, phrase_frames)):
        for note_index in range(7):
            start = phrase_start + note_index * syllable_frames
            if start >= min(FRAMES, phrase_start + int(3.5 * SAMPLE_RATE)):
                break
            end = min(FRAMES, start + syllable_frames)
            local = np.arange(end - start, dtype=np.float64) / SAMPLE_RATE
            frequency = melody[(phrase_index + note_index) % len(melody)]
            vibrato_phase = 2 * np.pi * frequency * local + 0.028 * np.sin(
                2 * np.pi * 5.1 * local
            )
            voiced = (
                np.sin(vibrato_phase)
                + 0.38 * np.sin(2 * vibrato_phase + 0.2)
                + 0.16 * np.sin(3 * vibrato_phase + 0.6)
            )
            envelope = np.sin(np.pi * np.arange(end - start) / max(1, end - start))
            vocals[start:end, 0] += voiced * envelope
            vocals[start:end, 1] += 0.94 * voiced * envelope
    vocals = _peak_scaled(vocals, 0.15, np=np)

    return {
        "vocals": vocals.astype(np.float32),
        "drums": drums.astype(np.float32),
        "bass": bass_stereo.astype(np.float32),
        "other": other.astype(np.float32),
    }


def _peak_scaled(value: Any, target: float, *, np: Any) -> Any:
    peak = float(np.max(np.abs(value)))
    if not math.isfinite(peak) or peak <= 0:
        raise ValueError("synthetic role is silent or non-finite")
    return value * (target / peak)


def _quantize(value: Any, *, np: Any) -> Any:
    if not np.all(np.isfinite(value)):
        raise ValueError("synthetic role contains non-finite audio")
    return np.rint(value * PCM24_SCALE).astype(np.int32)


def _document_sha256(document: dict[str, Any]) -> str:
    value = dict(document)
    value.pop("document_sha256", None)
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "DURATION_SECONDS",
    "FIXTURE_POLICY_ID",
    "FIXTURE_SCHEMA",
    "FRAMES",
    "ROLES",
    "SAMPLE_RATE",
    "create_core_four_synthetic_fixture",
]
