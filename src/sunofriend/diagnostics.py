"""Machine-readable capability checks for users, agents, and CI."""

from __future__ import annotations

import sys
from importlib import metadata as importlib_metadata
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from . import __version__

CAPABILITIES = ("transcribe", "convert", "preview", "playback", "all")

_OPTIONAL_PACKAGES = (
    "numpy",
    "librosa",
    "soundfile",
    "basic-pitch",
    "onnxruntime",
    "scikit-learn",
    "coremltools",
    "setuptools",
    "mido",
    "python-rtmidi",
)
_CONVERT_PACKAGES = ("numpy", "librosa", "soundfile", "basic-pitch", "onnxruntime")


def collect_diagnostics(*, check_playback: bool = True) -> dict[str, Any]:
    """Inspect conversion, preview, and live-playback readiness.

    The report deliberately keeps each capability separate. A missing CoreMIDI
    destination must not make an otherwise usable file-conversion installation
    look broken to an automation client. ``check_playback=False`` avoids loading
    the live MIDI backend when a caller only needs an offline capability check.
    """

    from .render import RenderError, find_fluidsynth, find_soundfont

    result: dict[str, Any] = {
        "sunofriend_version": __version__,
        "python": sys.version.split()[0],
        "packages": {},
    }
    try:
        result["installed_distribution_version"] = importlib_metadata.version(
            "sunofriend"
        )
    except importlib_metadata.PackageNotFoundError:
        result["installed_distribution_version"] = None
    result["version_consistent"] = result["installed_distribution_version"] in {
        None,
        __version__,
    }

    for package in _OPTIONAL_PACKAGES:
        try:
            result["packages"][package] = importlib_metadata.version(package)
        except importlib_metadata.PackageNotFoundError:
            result["packages"][package] = None

    try:
        result["fluidsynth"] = find_fluidsynth()
        result["soundfont"] = find_soundfont()
        from .midi import MidiTrack, write_midi_file
        from .models import NoteEvent
        from .render import render_midi_to_wav

        with TemporaryDirectory(prefix="sunofriend_doctor_") as directory:
            midi = Path(directory) / "probe.mid"
            wav = Path(directory) / "probe.wav"
            write_midi_file(
                midi,
                [MidiTrack("Doctor", 0, 0, [NoteEvent(0.0, 0.1, 60, 90)])],
                bpm=120.0,
            )
            render_midi_to_wav(midi, wav)
            result["render_smoke_bytes"] = wav.stat().st_size
        result["render_ready"] = True
    except RenderError as exc:
        result["render_ready"] = False
        result["audio_error"] = str(exc)

    result["missing_transcribe_packages"] = [
        package
        for package in _CONVERT_PACKAGES
        if result["packages"][package] is None
    ]
    result["missing_convert_packages"] = list(
        result["missing_transcribe_packages"]
    )
    # Retain the original names for clients written against Sunofriend 0.3.
    result["missing_listen_packages"] = list(result["missing_convert_packages"])
    result["transcribe_ready"] = not result["missing_transcribe_packages"]
    result["convert_ready"] = (
        result["render_ready"] and result["transcribe_ready"]
    )
    result["listen_ready"] = result["convert_ready"]

    result["midi_check_skipped"] = not check_playback
    if check_playback:
        from .playback import PlaybackError, list_output_ports

        try:
            result["midi_outputs"] = list_output_ports()
            result["midi_ready"] = bool(result["midi_outputs"])
            if not result["midi_ready"]:
                result["midi_error"] = (
                    "No CoreMIDI outputs found. Enable an IAC Driver bus in "
                    "Audio MIDI Setup."
                )
        except PlaybackError as exc:
            result["midi_outputs"] = []
            result["midi_ready"] = False
            result["midi_error"] = str(exc)
    else:
        result["midi_outputs"] = []
        result["midi_ready"] = False
        result["midi_error"] = (
            "CoreMIDI check skipped because this offline capability does not "
            "require live MIDI playback."
        )

    result["preview_ready"] = result["render_ready"]
    result["playback_ready"] = result["midi_ready"]
    result["ready"] = result["convert_ready"] and result["playback_ready"]
    return result


def capability_ready(report: dict[str, Any], capability: str) -> bool:
    """Return whether one named doctor capability is usable."""

    readiness_keys = {
        "transcribe": "transcribe_ready",
        "convert": "convert_ready",
        "preview": "preview_ready",
        "playback": "playback_ready",
        "all": "ready",
    }
    try:
        return bool(report[readiness_keys[capability]])
    except KeyError as exc:
        raise ValueError(
            f"capability must be one of: {', '.join(CAPABILITIES)}"
        ) from exc


__all__ = ["CAPABILITIES", "capability_ready", "collect_diagnostics"]
