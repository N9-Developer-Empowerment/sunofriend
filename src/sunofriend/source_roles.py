"""Canonical source-role vocabulary and conservative filename inference.

Source roles enter Sunofriend through prepared source projects, legacy stem
folders, provider labels, MIDI Clips and General MIDI proxy descriptions.
Those external vocabularies are not the source-role vocabulary itself.  This
module therefore keeps one small, immutable set of source roles and lets
callers adapt external labels at their boundaries.

Inference is deliberately set-valued.  A filename such as ``bass and keys``
contains useful evidence for two roles; silently choosing one would lose
information.  Compound labels suppress only the broad aliases inside their
span, so ``backing vocals`` is one role while ``backing vocals and lead`` is
still correctly ambiguous.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence


class SourceRole(str, Enum):
    """Versioned Sunofriend source-role identifiers.

    Provider labels, Clip roles and General MIDI instrument families must be
    adapted to these identifiers rather than added to this enum.
    """

    BACKING_VOCALS = "backing_vocals"
    BASS = "bass"
    CYMBALS = "cymbals"
    DRUMS = "drums"
    HAT = "hat"
    KEYS = "keys"
    KICK = "kick"
    LEAD = "lead"
    OTHER = "other"
    OTHER_KIT = "other_kit"
    PIANO = "piano"
    RHYTHM = "rhythm"
    SNARE = "snare"
    STRINGS = "strings"
    SYNTH = "synth"
    TOMS = "toms"
    VOCALS = "vocals"
    WIND = "wind"

    MIX = "mix"
    PADS = "pads"
    METRONOME = "metronome"
    UNCLASSIFIED = "unclassified"


class SourceRolePolicy(str, Enum):
    """Mutually exclusive policy governing where a role may originate."""

    PREPARED_INPUT = "prepared-input"
    CONTEXT_ONLY = "context-only"
    DERIVED_ONLY = "derived-only"


@dataclass(frozen=True)
class SourceRoleDefinition:
    """Immutable definition for one canonical source role."""

    role: SourceRole
    aliases: tuple[str, ...]
    policy: SourceRolePolicy
    compound_aliases: tuple[str, ...] = ()
    flat_v1_repeatable: bool = False
    composite_supported: bool = False

    @property
    def role_id(self) -> str:
        return self.role.value

    @property
    def is_prepared(self) -> bool:
        return self.policy is SourceRolePolicy.PREPARED_INPUT

    @property
    def is_context(self) -> bool:
        return self.policy is SourceRolePolicy.CONTEXT_ONLY

    @property
    def is_derived(self) -> bool:
        return self.policy is SourceRolePolicy.DERIVED_ONLY

    # Descriptive aliases make policy checks readable at call sites without
    # weakening the mutually exclusive ``policy`` value.
    @property
    def accepts_prepared_input(self) -> bool:
        return self.is_prepared

    @property
    def context_only(self) -> bool:
        return self.is_context

    @property
    def derived_only(self) -> bool:
        return self.is_derived


def _normalise_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()


def _definition(
    role: SourceRole,
    *aliases: str,
    policy: SourceRolePolicy = SourceRolePolicy.PREPARED_INPUT,
    compounds: Sequence[str] = (),
    flat_v1_repeatable: bool = False,
    composite_supported: bool = False,
) -> SourceRoleDefinition:
    # The canonical identifier is always an alias.  Normalising here catches
    # accidental duplicate spellings while retaining a deterministic order.
    ordered = dict.fromkeys(
        _normalise_text(alias)
        for alias in (role.value, *aliases)
        if _normalise_text(alias)
    )
    compound_ordered = dict.fromkeys(
        _normalise_text(alias)
        for alias in compounds
        if _normalise_text(alias)
    )
    return SourceRoleDefinition(
        role=role,
        aliases=tuple(ordered),
        policy=policy,
        compound_aliases=tuple(compound_ordered),
        flat_v1_repeatable=flat_v1_repeatable,
        composite_supported=composite_supported,
    )


_DEFINITIONS = (
    _definition(
        SourceRole.BACKING_VOCALS,
        "backing vocal",
        "backing vocals",
        "bv",
        "bvox",
        compounds=("backing vocal", "backing vocals"),
        flat_v1_repeatable=True,
    ),
    _definition(SourceRole.BASS),
    _definition(
        SourceRole.CYMBALS,
        "cymbal",
        "crash",
        "ride",
        compounds=(
            "drum cymbal",
            "drum cymbals",
            "drums cymbal",
            "drums cymbals",
        ),
    ),
    _definition(
        SourceRole.DRUMS,
        "drum",
        "drum kit",
        "drumkit",
        "drum set",
        "drumset",
        compounds=("drum kit", "drum set"),
        composite_supported=True,
    ),
    _definition(
        SourceRole.HAT,
        "hats",
        "hi hat",
        "hi hats",
        "hihat",
        "hihats",
        compounds=(
            "drum hat",
            "drum hats",
            "drums hat",
            "drums hats",
            "drum hi hat",
            "drum hi hats",
            "drums hi hat",
            "drums hi hats",
        ),
    ),
    _definition(
        SourceRole.KEYS,
        "keyboard",
        "electric piano",
        compounds=("electric piano",),
    ),
    _definition(
        SourceRole.KICK,
        compounds=(
            "drum kick",
            "drums kick",
            "kick drum",
            "bass drum",
        ),
    ),
    _definition(SourceRole.LEAD),
    _definition(
        SourceRole.OTHER,
        "residual",
        composite_supported=True,
    ),
    _definition(
        SourceRole.OTHER_KIT,
        "other kit",
        "other drums",
        "percussion",
        "perc",
        compounds=(
            "other kit",
            "other drums",
            "drum other kit",
            "drums other kit",
            "drum percussion",
            "drums percussion",
        ),
    ),
    _definition(SourceRole.PIANO),
    _definition(SourceRole.RHYTHM, "guitar", "guitars"),
    _definition(
        SourceRole.SNARE,
        compounds=(
            "drum snare",
            "drums snare",
            "snare drum",
        ),
    ),
    _definition(SourceRole.STRINGS, "string"),
    _definition(SourceRole.SYNTH, "synthesizer"),
    _definition(
        SourceRole.TOMS,
        "tom",
        compounds=(
            "drum tom",
            "drum toms",
            "drums tom",
            "drums toms",
            "tom drum",
            "toms drum",
        ),
    ),
    _definition(
        SourceRole.VOCALS,
        "vocal",
        "voice",
        "lead vocal",
        "lead vocals",
        compounds=("lead vocal", "lead vocals"),
        flat_v1_repeatable=True,
        composite_supported=True,
    ),
    _definition(SourceRole.WIND, "woodwind", "brass"),
    _definition(
        SourceRole.MIX,
        "full mix",
        policy=SourceRolePolicy.CONTEXT_ONLY,
        compounds=("full mix",),
    ),
    _definition(
        SourceRole.PADS,
        "pad",
        policy=SourceRolePolicy.DERIVED_ONLY,
    ),
    _definition(
        SourceRole.METRONOME,
        "click track",
        "clicktrack",
        policy=SourceRolePolicy.CONTEXT_ONLY,
        compounds=("click track",),
    ),
    _definition(
        SourceRole.UNCLASSIFIED,
        policy=SourceRolePolicy.CONTEXT_ONLY,
    ),
)

_DEFINITIONS_BY_ID: Mapping[str, SourceRoleDefinition] = MappingProxyType(
    {definition.role_id: definition for definition in _DEFINITIONS}
)
_PREPARED_ROLE_IDS = frozenset(
    definition.role_id
    for definition in _DEFINITIONS
    if definition.is_prepared
)
_CONTEXT_ROLE_IDS = frozenset(
    definition.role_id
    for definition in _DEFINITIONS
    if definition.is_context
)
_DERIVED_ROLE_IDS = frozenset(
    definition.role_id
    for definition in _DEFINITIONS
    if definition.is_derived
)


def infer_source_roles(value: Any) -> frozenset[str]:
    """Return every conservatively inferred canonical role.

    The return type is intentionally a set: no ranking or priority is implied.
    Call :func:`canonical_source_role` only at a boundary that requires exactly
    one role and is prepared to reject ambiguity.
    """

    normalized = _normalise_value(value)
    if not normalized:
        return frozenset()

    compound_spans: list[tuple[int, int, str]] = []
    for definition in _DEFINITIONS:
        for alias in definition.compound_aliases:
            for match in _bounded_alias_matches(normalized, alias):
                compound_spans.append(
                    (match.start(), match.end(), definition.role_id)
                )

    matches = {role for _start, _end, role in compound_spans}
    for definition in _DEFINITIONS:
        for alias in definition.aliases:
            alias_matches = _bounded_alias_matches(normalized, alias)
            if any(
                not any(
                    start <= match.start()
                    and match.end() <= end
                    and compound_role != definition.role_id
                    for start, end, compound_role in compound_spans
                )
                for match in alias_matches
            ):
                matches.add(definition.role_id)
                break
    return frozenset(matches)


def canonical_source_role(
    value: Any,
    *,
    allow_unclassified: bool = False,
) -> str:
    """Resolve exactly one canonical source role or reject the label.

    ``allow_unclassified`` supplies the explicit context-only fallback when no
    role is present.  It never resolves a genuinely ambiguous label.
    """

    if isinstance(value, SourceRole):
        return value.value
    matches = infer_source_roles(value)
    if len(matches) == 1:
        return next(iter(matches))
    if not matches:
        if allow_unclassified:
            return SourceRole.UNCLASSIFIED.value
        raise ValueError(f"unrecognised source role: {value!r}")
    raise ValueError(
        f"ambiguous source role {value!r}; matched: "
        + ", ".join(sorted(matches))
    )


def source_role_definition(role: Any) -> SourceRoleDefinition:
    """Return the immutable definition for one canonical or aliased role."""

    role_id = canonical_source_role(role)
    return _DEFINITIONS_BY_ID[role_id]


def prepared_source_role_ids() -> frozenset[str]:
    """Return roles accepted as canonical prepared source inputs."""

    return _PREPARED_ROLE_IDS


def context_source_role_ids() -> frozenset[str]:
    """Return roles retained only as source-project context."""

    return _CONTEXT_ROLE_IDS


def derived_source_role_ids() -> frozenset[str]:
    """Return roles that production may derive but preparation cannot accept."""

    return _DERIVED_ROLE_IDS


def source_role_ids() -> frozenset[str]:
    """Return the complete canonical source-role vocabulary."""

    return frozenset(_DEFINITIONS_BY_ID)


def flat_v1_repeatable_source_role_ids() -> frozenset[str]:
    """Return roles that the flat source-project.v1 contract may repeat."""

    return frozenset(
        definition.role_id
        for definition in _DEFINITIONS
        if definition.flat_v1_repeatable
    )


def composite_source_role_ids() -> frozenset[str]:
    """Return roles whose future graph nodes may explicitly be composite."""

    return frozenset(
        definition.role_id
        for definition in _DEFINITIONS
        if definition.composite_supported
    )


def is_prepared_source_role(value: Any) -> bool:
    return _has_policy(value, SourceRolePolicy.PREPARED_INPUT)


def is_context_source_role(value: Any) -> bool:
    return _has_policy(value, SourceRolePolicy.CONTEXT_ONLY)


def is_derived_source_role(value: Any) -> bool:
    return _has_policy(value, SourceRolePolicy.DERIVED_ONLY)


def _has_policy(value: Any, policy: SourceRolePolicy) -> bool:
    try:
        return source_role_definition(value).policy is policy
    except ValueError:
        return False


def _normalise_value(value: Any) -> str:
    if isinstance(value, SourceRole):
        return _normalise_text(value.value)
    raw = str(value)
    # Workbench catalogues historically use URL-encoded spaces.  Decode only
    # this established representation; arbitrary percent decoding belongs at
    # an external-input boundary.
    raw = re.sub(r"%20", " ", raw, flags=re.IGNORECASE)
    try:
        # Keep a dotted role label such as ``electric.piano`` intact while
        # ignoring role-like directory names.  File extensions are harmless
        # bounded tokens after normalisation, whereas ``Path.stem`` would
        # incorrectly turn the label into only ``electric``.
        raw = Path(raw).name
    except (TypeError, ValueError):
        pass
    return _normalise_text(raw)


def _bounded_alias_matches(
    value: str,
    alias: str,
) -> tuple[re.Match[str], ...]:
    pattern = r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])"
    return tuple(re.finditer(pattern, value))


def iter_source_role_definitions() -> Iterable[SourceRoleDefinition]:
    """Iterate definitions in stable registry order."""

    return iter(_DEFINITIONS)


__all__ = [
    "SourceRole",
    "SourceRoleDefinition",
    "SourceRolePolicy",
    "canonical_source_role",
    "composite_source_role_ids",
    "context_source_role_ids",
    "derived_source_role_ids",
    "flat_v1_repeatable_source_role_ids",
    "infer_source_roles",
    "is_context_source_role",
    "is_derived_source_role",
    "is_prepared_source_role",
    "iter_source_role_definitions",
    "prepared_source_role_ids",
    "source_role_definition",
    "source_role_ids",
]
