"""Single-source complete General MIDI patch pairs for Workbench reviews."""

from __future__ import annotations

import copy
from typing import Any


_COMPLETE_INSTRUMENT_PROGRAMS = {
    "bass": {
        "control": {
            "program": 38,
            "general_midi_number": 39,
            "label": "Synth Bass 1",
        },
        "challenger": {
            "program": 39,
            "general_midi_number": 40,
            "label": "Synth Bass 2",
        },
    },
    "keys": {
        "control": {
            "program": 4,
            "general_midi_number": 5,
            "label": "Electric Piano 1",
        },
        "challenger": {
            "program": 5,
            "general_midi_number": 6,
            "label": "Electric Piano 2",
        },
    },
}


def complete_instrument_roles() -> tuple[str, ...]:
    """Return supported roles in deterministic display order."""

    return tuple(_COMPLETE_INSTRUMENT_PROGRAMS)


def complete_instrument_programs(role: str) -> dict[str, dict[str, Any]]:
    """Return a defensive copy of the exact server-owned role policy."""

    checked = str(role).strip().lower()
    try:
        return copy.deepcopy(_COMPLETE_INSTRUMENT_PROGRAMS[checked])
    except KeyError as exc:
        raise ValueError(
            "complete-instrument review supports only bass or keys"
        ) from exc
