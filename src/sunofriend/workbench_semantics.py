"""Shared explicit-decision semantics for Workbench projections."""

from __future__ import annotations


TERMINAL_NO_SELECTION_OUTCOMES = frozenset({"none_usable", "cannot_tell"})


def terminal_no_selection_outcome(value: object) -> bool:
    """Return whether an outcome explicitly suppresses every MIDI selection."""

    return isinstance(value, str) and value in TERMINAL_NO_SELECTION_OUTCOMES
