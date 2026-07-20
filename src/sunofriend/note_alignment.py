"""Deterministic one-to-one onset alignment for note-like events.

The alignment kernel is deliberately independent of MIDI, AI candidates and
Workbench records.  Callers adapt their evidence to :class:`AlignmentEvent`
and select the pitch and label policies explicitly.  The result retains stable
source indices so later phrase diagnostics can explain every match without
mutating either input.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from numbers import Integral, Real
from typing import Literal, Sequence


PitchPolicy = Literal["rounded", "exact_integer"]
MatchingPolicy = Literal["earliest_compatible", "left_greedy_closest"]
_PITCH_POLICIES = frozenset({"rounded", "exact_integer"})
_MATCHING_POLICIES = frozenset({"earliest_compatible", "left_greedy_closest"})


@dataclass(frozen=True)
class AlignmentEvent:
    """One immutable note-onset observation with a caller-stable index."""

    source_index: int
    onset: float
    pitch: float
    label: str | None = None

    def __post_init__(self) -> None:
        source_index = _nonnegative_integer(
            self.source_index,
            "alignment event source_index",
        )
        onset = _finite_real(self.onset, "alignment event onset")
        if onset < 0:
            raise ValueError("alignment event onset must be non-negative")
        pitch = _finite_real(self.pitch, "alignment event pitch")
        if self.label is not None and not isinstance(self.label, str):
            raise ValueError("alignment event label must be text or null")
        object.__setattr__(self, "source_index", source_index)
        object.__setattr__(self, "onset", onset)
        object.__setattr__(self, "pitch", pitch)


@dataclass(frozen=True)
class AlignmentMatch:
    """One deterministic one-to-one pair in excerpt-local time."""

    left_index: int
    right_index: int
    left_onset_seconds: float
    right_onset_seconds: float
    onset_delta_seconds: float


@dataclass(frozen=True)
class AlignmentResult:
    """Matched pairs and stable source indices not used by any pair."""

    matches: tuple[AlignmentMatch, ...]
    unmatched_left_indices: tuple[int, ...]
    unmatched_right_indices: tuple[int, ...]


def align_events(
    left: Sequence[AlignmentEvent],
    right: Sequence[AlignmentEvent],
    *,
    left_offset: float,
    right_offset: float,
    tolerance: float,
    pitch_policy: PitchPolicy,
    require_exact_label: bool,
    matching_policy: MatchingPolicy = "earliest_compatible",
) -> AlignmentResult:
    """Align events once by pitch and excerpt-local onset.

    The default uses chronological earliest-compatible pairing within each
    pitch/label bucket to produce a deterministic maximum-cardinality
    one-to-one alignment. ``left_greedy_closest`` preserves the older
    left-order, nearest-unused metric used by existing v1 reports. The
    tolerance comparison is inclusive. Offsets are always explicit and are
    subtracted from event onsets before matching.
    """

    left_events = _validated_events(left, "left")
    right_events = _validated_events(right, "right")
    left_origin = _finite_real(left_offset, "left_offset")
    right_origin = _finite_real(right_offset, "right_offset")
    maximum_distance = _finite_real(tolerance, "tolerance")
    if maximum_distance < 0:
        raise ValueError("alignment tolerance must be non-negative")
    decimal_tolerance = Decimal(str(maximum_distance))
    if not isinstance(pitch_policy, str) or pitch_policy not in _PITCH_POLICIES:
        raise ValueError("alignment pitch_policy must be rounded or exact_integer")
    if not isinstance(require_exact_label, bool):
        raise ValueError("require_exact_label must be a boolean")
    if (
        not isinstance(matching_policy, str)
        or matching_policy not in _MATCHING_POLICIES
    ):
        raise ValueError(
            "alignment matching_policy must be earliest_compatible or "
            "left_greedy_closest"
        )
    if matching_policy == "left_greedy_closest":
        return _align_left_greedy_closest(
            left_events,
            right_events,
            left_offset=left_origin,
            right_offset=right_origin,
            tolerance=decimal_tolerance,
            pitch_policy=pitch_policy,
            require_exact_label=require_exact_label,
        )

    left_groups = _event_groups(
        left_events,
        offset=left_origin,
        pitch_policy=pitch_policy,
        require_exact_label=require_exact_label,
    )
    right_groups = _event_groups(
        right_events,
        offset=right_origin,
        pitch_policy=pitch_policy,
        require_exact_label=require_exact_label,
    )
    matched: list[tuple[Decimal, Decimal, int, int]] = []
    common_keys = set(left_groups) & set(right_groups)
    for key in sorted(common_keys, key=_group_sort_key):
        left_group = left_groups[key]
        right_group = right_groups[key]
        left_position = 0
        right_position = 0
        while left_position < len(left_group) and right_position < len(right_group):
            left_onset, left_event = left_group[left_position]
            right_onset, right_event = right_group[right_position]
            delta = right_onset - left_onset
            if abs(delta) <= decimal_tolerance:
                matched.append(
                    (
                        left_onset,
                        right_onset,
                        left_event.source_index,
                        right_event.source_index,
                    )
                )
                left_position += 1
                right_position += 1
            elif left_onset < right_onset:
                left_position += 1
            else:
                right_position += 1

    return _alignment_result(left_events, right_events, matched)


def _align_left_greedy_closest(
    left: Sequence[AlignmentEvent],
    right: Sequence[AlignmentEvent],
    *,
    left_offset: float,
    right_offset: float,
    tolerance: Decimal,
    pitch_policy: PitchPolicy,
    require_exact_label: bool,
) -> AlignmentResult:
    """Preserve legacy left-order, nearest-unused matching for v1 metrics."""

    right_rows = [
        (
            _event_key(
                event,
                pitch_policy=pitch_policy,
                require_exact_label=require_exact_label,
            ),
            Decimal(str(event.onset)) - Decimal(str(right_offset)),
            event,
        )
        for event in right
    ]
    used_right: set[int] = set()
    matched: list[tuple[Decimal, Decimal, int, int]] = []
    for left_event in left:
        left_key = _event_key(
            left_event,
            pitch_policy=pitch_policy,
            require_exact_label=require_exact_label,
        )
        left_onset = Decimal(str(left_event.onset)) - Decimal(str(left_offset))
        best: tuple[Decimal, AlignmentEvent] | None = None
        best_distance: Decimal | None = None
        for right_key, right_onset, right_event in right_rows:
            if right_event.source_index in used_right or right_key != left_key:
                continue
            distance = abs(right_onset - left_onset)
            if distance <= tolerance and (
                best_distance is None or distance < best_distance
            ):
                best = right_onset, right_event
                best_distance = distance
        if best is None:
            continue
        right_onset, right_event = best
        used_right.add(right_event.source_index)
        matched.append(
            (
                left_onset,
                right_onset,
                left_event.source_index,
                right_event.source_index,
            )
        )
    return _alignment_result(left, right, matched)


def _alignment_result(
    left: Sequence[AlignmentEvent],
    right: Sequence[AlignmentEvent],
    matched: Sequence[tuple[Decimal, Decimal, int, int]],
) -> AlignmentResult:
    matched_left = {value[2] for value in matched}
    matched_right = {value[3] for value in matched}
    matches = tuple(
        AlignmentMatch(
            left_index=left_index,
            right_index=right_index,
            left_onset_seconds=float(left_onset),
            right_onset_seconds=float(right_onset),
            onset_delta_seconds=float(right_onset - left_onset),
        )
        for left_onset, right_onset, left_index, right_index in sorted(
            matched,
            key=lambda value: (value[0], value[1], value[2], value[3]),
        )
    )
    return AlignmentResult(
        matches=matches,
        unmatched_left_indices=tuple(
            sorted(
                event.source_index
                for event in left
                if event.source_index not in matched_left
            )
        ),
        unmatched_right_indices=tuple(
            sorted(
                event.source_index
                for event in right
                if event.source_index not in matched_right
            )
        ),
    )


def _validated_events(
    values: Sequence[AlignmentEvent],
    side: str,
) -> tuple[AlignmentEvent, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"{side} alignment events must be a sequence")
    events = tuple(values)
    if any(not isinstance(event, AlignmentEvent) for event in events):
        raise ValueError(f"{side} alignment events contain a malformed value")
    indices = [event.source_index for event in events]
    if len(indices) != len(set(indices)):
        raise ValueError(f"{side} alignment event source indices must be unique")
    return events


def _event_groups(
    events: Sequence[AlignmentEvent],
    *,
    offset: float,
    pitch_policy: PitchPolicy,
    require_exact_label: bool,
) -> dict[tuple[int, str | None], list[tuple[Decimal, AlignmentEvent]]]:
    groups: dict[
        tuple[int, str | None],
        list[tuple[Decimal, AlignmentEvent]],
    ] = {}
    for event in events:
        key = _event_key(
            event,
            pitch_policy=pitch_policy,
            require_exact_label=require_exact_label,
        )
        local_onset = Decimal(str(event.onset)) - Decimal(str(offset))
        groups.setdefault(key, []).append((local_onset, event))
    for group in groups.values():
        group.sort(key=lambda value: (value[0], value[1].source_index))
    return groups


def _event_key(
    event: AlignmentEvent,
    *,
    pitch_policy: PitchPolicy,
    require_exact_label: bool,
) -> tuple[int, str | None]:
    return (
        _pitch_key(event.pitch, pitch_policy),
        event.label if require_exact_label else None,
    )


def _pitch_key(value: float, policy: PitchPolicy) -> int:
    if policy == "rounded":
        return round(value)
    if not value.is_integer():
        raise ValueError("exact_integer pitch policy requires integral pitches")
    return int(value)


def _group_sort_key(value: tuple[int, str | None]) -> tuple[int, int, str]:
    pitch, label = value
    return pitch, 0 if label is None else 1, label or ""


def _finite_real(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be a finite number")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{label} must be a finite number")
    return converted


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{label} must be a non-negative integer")
    converted = int(value)
    if converted < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return converted


__all__ = [
    "AlignmentEvent",
    "AlignmentMatch",
    "AlignmentResult",
    "MatchingPolicy",
    "PitchPolicy",
    "align_events",
]
