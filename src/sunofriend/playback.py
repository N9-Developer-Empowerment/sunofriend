"""Live CoreMIDI playback for auditioning Sunofriend MIDI in GarageBand.

GarageBand can receive these messages on an armed software-instrument track
through an enabled IAC Driver bus.  ``mido`` and ``python-rtmidi`` are optional
so conversion and library operations remain usable without MIDI hardware.
"""
from __future__ import annotations

from pathlib import Path


class PlaybackError(RuntimeError):
    pass


def list_output_ports() -> list[str]:
    """Return available CoreMIDI output names in stable display order."""
    try:
        import mido
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise PlaybackError(
            "Live MIDI needs the midi extra: pip install -e '.[midi]'"
        ) from exc
    try:
        return sorted(mido.get_output_names(), key=str.casefold)
    except Exception as exc:  # backend import/initialisation errors vary by mido version
        raise PlaybackError(
            "CoreMIDI backend is unavailable. Install the midi extra "
            "(`pip install -e '.[midi]'`) and verify python-rtmidi can load. "
            f"Backend error: {exc}"
        ) from exc


def choose_output_port(requested: str | None, available: list[str] | None = None) -> str:
    """Resolve an exact or unique case-insensitive substring port name."""
    ports = list_output_ports() if available is None else list(available)
    if not ports:
        raise PlaybackError(
            "No CoreMIDI outputs are available. In Audio MIDI Setup, open MIDI "
            "Studio, double-click IAC Driver, enable 'Device is online', then "
            "arm a GarageBand software-instrument track."
        )
    if requested is None:
        if len(ports) == 1:
            return ports[0]
        iac = [name for name in ports if "iac" in name.casefold()]
        if len(iac) == 1:
            return iac[0]
        raise PlaybackError(
            "More than one MIDI output is available; choose one with --port. "
            f"Available: {', '.join(ports)}"
        )
    exact = [name for name in ports if name.casefold() == requested.casefold()]
    if exact:
        return exact[0]
    matches = [name for name in ports if requested.casefold() in name.casefold()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise PlaybackError(
            f"MIDI output {requested!r} was not found. Available: {', '.join(ports)}"
        )
    raise PlaybackError(
        f"MIDI output {requested!r} is ambiguous. Matches: {', '.join(matches)}"
    )


def play_midi(path: str | Path, port: str | None = None) -> str:
    """Play a Standard MIDI File to a CoreMIDI destination in real time.

    Tempo changes in the file are honoured by ``MidiFile.play``.  A reset is
    sent even after Ctrl-C so a GarageBand instrument cannot be left sustaining.
    Returns the resolved output-port name.
    """
    try:
        import mido
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise PlaybackError(
            "Live MIDI needs the midi extra: pip install -e '.[midi]'"
        ) from exc

    midi_path = Path(path)
    if not midi_path.is_file():
        raise PlaybackError(f"MIDI file not found: {midi_path}")
    port_name = choose_output_port(port)
    try:
        midi = mido.MidiFile(str(midi_path))
        with mido.open_output(port_name) as output:
            try:
                for message in midi.play(meta_messages=False):
                    output.send(message)
            finally:
                output.reset()
    except (OSError, ValueError, EOFError) as exc:
        raise PlaybackError(f"Could not play {midi_path} to {port_name}: {exc}") from exc
    return port_name


__all__ = ["PlaybackError", "choose_output_port", "list_output_ports", "play_midi"]
