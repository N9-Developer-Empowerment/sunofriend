"""Dependency-free policy for broad and explicit drum source roles."""

from __future__ import annotations

from typing import Any, Iterable, Mapping


DRUM_LEAF_PARTS = ("kick", "snare", "hat", "cymbals", "toms", "other_kit")
DRUM_PARTS = (*DRUM_LEAF_PARTS, "drums")
DRUM_ROLE_POLICY_SCHEMA = "sunofriend.drum-role-policy.v1"
COMPOSITE_DRUM_PROCESSING_KIND = "other_kit"
COMPOSITE_DRUM_CLASSIFICATION_LIMITATION = (
    "A composite drums stem is classified as one dominant drum family per "
    "detected onset; coincident layered hits can collapse to one MIDI note."
)
_DRUM_ROLE_POLICY_FIELDS = frozenset(
    {
        "schema",
        "composite_role",
        "classifier_alias",
        "explicit_leaf_roles",
        "shadowed_roles",
        "precedence",
        "midi_family_variants_only",
        "audio_children_created",
        "warnings",
    }
)
_DRUM_ROLE_POLICY_FACT_FIELDS = (
    "schema",
    "composite_role",
    "classifier_alias",
    "explicit_leaf_roles",
    "shadowed_roles",
    "precedence",
    "midi_family_variants_only",
    "audio_children_created",
)


def resolve_drum_role_policy(roles: Iterable[str]) -> dict[str, object]:
    """Return the non-destructive broad/leaf drum precedence policy."""

    available = {str(role) for role in roles}
    explicit = tuple(role for role in DRUM_LEAF_PARTS if role in available)
    shadowed = ("drums",) if "drums" in available and explicit else ()
    warnings: list[str] = []
    if "drums" in available:
        warnings.append(
            "Composite drums conversion is review-required. "
            + COMPOSITE_DRUM_CLASSIFICATION_LIMITATION
        )
    if shadowed:
        warnings.append(
            "Composite drums is retained for Studio review but shadowed in "
            "automatic arrangements because explicit drum-family source "
            f"roles are present: {', '.join(explicit)}. This prevents doubled "
            "drum hits; Sunofriend does not infer a complementary broad-stem "
            "residual."
        )
    return {
        "schema": DRUM_ROLE_POLICY_SCHEMA,
        "composite_role": "drums",
        "classifier_alias": COMPOSITE_DRUM_PROCESSING_KIND,
        "explicit_leaf_roles": list(explicit),
        "shadowed_roles": list(shadowed),
        "precedence": (
            "explicit-leaves-over-composite"
            if shadowed
            else "composite-review-required"
            if "drums" in available
            else "not-applicable"
        ),
        "midi_family_variants_only": "drums" in available,
        "audio_children_created": False,
        "warnings": warnings,
    }


def validate_drum_role_policy(
    document: Mapping[str, Any],
    *,
    roles: Iterable[str],
) -> None:
    """Validate versioned policy facts while treating warnings as prose.

    Warning text is hash-pinned by its enclosing immutable receipt, but it is
    not a stable policy fact. This lets a valid old receipt remain verifiable
    after user-facing wording improves.
    """

    if not isinstance(document, Mapping):
        raise ValueError("drum role policy must be an object")
    if set(document) != _DRUM_ROLE_POLICY_FIELDS:
        raise ValueError("drum role policy fields do not match its schema")
    expected = resolve_drum_role_policy(roles)
    for field in _DRUM_ROLE_POLICY_FACT_FIELDS:
        if document.get(field) != expected[field]:
            raise ValueError(
                f"drum role policy {field} does not match its source roles"
            )
    warnings = document.get("warnings")
    if not isinstance(warnings, list) or not all(
        isinstance(warning, str) for warning in warnings
    ):
        raise ValueError("drum role policy warnings must be a list of text")


__all__ = [
    "COMPOSITE_DRUM_CLASSIFICATION_LIMITATION",
    "COMPOSITE_DRUM_PROCESSING_KIND",
    "DRUM_LEAF_PARTS",
    "DRUM_PARTS",
    "DRUM_ROLE_POLICY_SCHEMA",
    "resolve_drum_role_policy",
    "validate_drum_role_policy",
]
