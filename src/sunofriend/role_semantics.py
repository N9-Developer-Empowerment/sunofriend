"""Shared, conservative musical-role semantics.

Role labels enter Sunofriend through several independent paths: stem catalogues,
MIDI imports, Clip metadata, Workbench timelines, neutral rendering and
audition balancing.  Those paths must agree about whether a role belongs on
General MIDI channel 10 (zero-based channel 9).

The classifier is deliberately token-aware and conservative.  It recognises
canonical drum/percussion names and ordinary descriptive variants, while
avoiding substring guesses (for example ``kickoff`` or ``tomorrow``).  Pitched
steel drums are kept melodic, and a generic non-musical ``tool kit`` is not
mistaken for a drum kit.
"""

from __future__ import annotations

import re
from typing import Any


_DRUM_TOKENS = frozenset(
    {
        "cymbal",
        "cymbals",
        "agogo",
        "bongo",
        "bongos",
        "cabasa",
        "clap",
        "claps",
        "clave",
        "claves",
        "conga",
        "congas",
        "cowbell",
        "drum",
        "drums",
        "guiro",
        "hat",
        "hats",
        "hihat",
        "hihats",
        "kick",
        "maraca",
        "maracas",
        "perc",
        "percussion",
        "rimshot",
        "shaker",
        "tambourine",
        "triangle",
        "woodblock",
        "snare",
        "tom",
        "toms",
    }
)
_DRUM_COMPACT_TOKENS = frozenset({"drumkit", "drumset", "otherkit"})
_EXACT_KIT_ROLES = frozenset({"kit", "other kit"})


def normalize_role(value: Any) -> str:
    """Return a stable, token-separated role label for semantic checks."""

    return re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()


def is_drum_role(value: Any) -> bool:
    """Return whether ``value`` denotes an unpitched drum/percussion role.

    MIDI channel 10 is an unpitched percussion mapping, so pitched steel drums
    deliberately return ``False`` even though their name contains ``drum``.
    ``kit`` is accepted only as the complete musical shorthand or in the
    canonical ``other kit`` role; descriptive drum-kit labels are recognised
    through their explicit ``drum``/``drumkit`` token.
    """

    normalized = normalize_role(value)
    if not normalized:
        return False
    tokens = tuple(normalized.split())
    token_set = set(tokens)

    if "steel" in token_set and token_set & {"drum", "drums"}:
        return False
    if normalized == "tool kit":
        return False
    if normalized in _EXACT_KIT_ROLES:
        return True
    return bool(token_set & (_DRUM_TOKENS | _DRUM_COMPACT_TOKENS))


__all__ = ["is_drum_role", "normalize_role"]
