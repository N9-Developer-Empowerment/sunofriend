"""Headless MIDI -> audio rendering through FluidSynth + a GM SoundFont.

This is the "proxy instrument" used by the listen/refine loop: candidate MIDI
is rendered to audio here (fast, no GarageBand involved) and compared against
the original stem in feature space. The final .mid is what goes to GarageBand.

FluidSynth binary lookup order:
  1. SUNOFRIEND_FLUIDSYNTH env var
  2. `fluidsynth` on PATH
SoundFont lookup order:
  1. SUNOFRIEND_SF2 env var
  2. common install locations (Linux apt, macOS Homebrew)
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_SF2_CANDIDATES = [
    "/usr/share/sounds/sf2/FluidR3_GM.sf2",
    "/usr/share/sounds/sf2/default-GM.sf2",
    "/usr/local/share/soundfonts/FluidR3_GM.sf2",
    "/opt/homebrew/share/soundfonts/default.sf2",
    "/usr/local/share/fluidsynth/sf2/FluidR3_GM.sf2",
]


class RenderError(RuntimeError):
    pass


def find_fluidsynth() -> str:
    override = os.environ.get("SUNOFRIEND_FLUIDSYNTH")
    if override and Path(override).exists():
        return override
    found = shutil.which("fluidsynth")
    if found:
        return found
    raise RenderError(
        "fluidsynth binary not found. Install it (macOS: `brew install fluidsynth`) "
        "or set SUNOFRIEND_FLUIDSYNTH to its path."
    )


def find_soundfont() -> str:
    override = os.environ.get("SUNOFRIEND_SF2")
    if override and Path(override).exists():
        return override
    for candidate in _SF2_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise RenderError(
        "No GM SoundFont found. Download FluidR3_GM.sf2 (or any GM .sf2) and set "
        "SUNOFRIEND_SF2 to its path."
    )


def render_midi_to_wav(
    midi_path: str | Path,
    wav_path: str | Path,
    sample_rate: int = 44100,
    gain: float = 0.7,
    timeout_seconds: float = 120.0,
) -> Path:
    """Render a MIDI file to a WAV file. Returns the output path."""
    midi_path = Path(midi_path)
    wav_path = Path(wav_path)
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    if not midi_path.exists():
        raise RenderError(f"MIDI file not found: {midi_path}")

    command = [
        find_fluidsynth(),
        "-ni",                      # no shell, no MIDI-in
        "-g", str(gain),
        "-r", str(sample_rate),
        "-F", str(wav_path),        # fast file rendering, no audio device
        find_soundfont(),
        str(midi_path),
    ]
    env = dict(os.environ)
    extra_lib = os.environ.get("SUNOFRIEND_FLUIDSYNTH_LIB")
    if extra_lib:
        env["LD_LIBRARY_PATH"] = extra_lib + ":" + env.get("LD_LIBRARY_PATH", "")
    result = subprocess.run(
        command, capture_output=True, text=True, timeout=timeout_seconds, env=env
    )
    if result.returncode != 0 or not wav_path.exists() or wav_path.stat().st_size < 1024:
        raise RenderError(
            f"fluidsynth failed (exit {result.returncode}): {result.stderr.strip()[:500]}"
        )
    return wav_path


def is_available() -> bool:
    try:
        find_fluidsynth()
        find_soundfont()
        return True
    except RenderError:
        return False
