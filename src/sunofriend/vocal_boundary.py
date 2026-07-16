"""Conservative note boundaries over independently agreed vocal F0.

Boundary models answer *when* a note may start or end. They do not become
pitch authority here: a proposal is usable only when pYIN and RMVPE agree on
the pitch throughout enough of its interval. Every proposal and rejection is
retained so this repair can be audited without changing any raw candidate.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from statistics import median
from typing import Any, Mapping, Sequence

from .models import NoteEvent


VOCAL_BOUNDARY_REPAIR_SCHEMA = "sunofriend.vocal-boundary-repair.v1"


@dataclass(frozen=True)
class BoundaryProposal:
    provider: str
    source_event_id: str
    start_seconds: float
    end_seconds: float
    pitch: float
    confidence: float | None = None
    velocity: int | None = None

    def __post_init__(self) -> None:
        values = (self.start_seconds, self.end_seconds, self.pitch)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("boundary proposal times and pitch must be finite")
        if self.start_seconds < 0 or self.end_seconds <= self.start_seconds:
            raise ValueError("boundary proposal must have positive duration")
        if not 0 <= self.pitch <= 127:
            raise ValueError("boundary proposal pitch must be in MIDI range")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("boundary proposal confidence must be between 0 and 1")
        if self.velocity is not None and not 1 <= self.velocity <= 127:
            raise ValueError("boundary proposal velocity must be in MIDI range")


@dataclass(frozen=True)
class BoundaryRepairConfig:
    agreement_tolerance_cents: float = 70.0
    boundary_pitch_tolerance_cents: float = 70.0
    maximum_pitch_mad_cents: float = 45.0
    minimum_support_ratio: float = 0.35
    minimum_support_frames: int = 5
    maximum_edge_gap_ms: float = 180.0
    minimum_note_ms: float = 65.0
    phrase_gap_beats: float = 0.75

    def __post_init__(self) -> None:
        for name in (
            "agreement_tolerance_cents",
            "boundary_pitch_tolerance_cents",
            "maximum_pitch_mad_cents",
            "maximum_edge_gap_ms",
            "minimum_note_ms",
            "phrase_gap_beats",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not 0 < self.minimum_support_ratio <= 1:
            raise ValueError("minimum_support_ratio must be in (0, 1]")
        if self.minimum_support_frames <= 0:
            raise ValueError("minimum_support_frames must be positive")


def repair_vocal_boundaries(
    alignment: Sequence[Mapping[str, Any]],
    proposals: Sequence[BoundaryProposal],
    *,
    bpm: float,
    config: BoundaryRepairConfig | None = None,
) -> tuple[dict[str, list[NoteEvent]], dict[str, Any]]:
    """Validate boundary proposals against pYIN/RMVPE pitch agreement.

    Variants are returned for each boundary provider plus ``combined``. The
    combined result is a deterministic monophonic selection across providers;
    raw model notes are never rewritten.
    """

    if not math.isfinite(bpm) or bpm <= 0:
        raise ValueError("bpm must be finite and positive")
    policy = config or BoundaryRepairConfig()
    timeline = _validated_timeline(alignment)
    hop = _timeline_hop(timeline)
    audited = [
        _audit_proposal(proposal, timeline, hop=hop, config=policy)
        for proposal in proposals
    ]
    accepted = [record for record in audited if record["status"] == "accepted"]
    providers = sorted({proposal.provider for proposal in proposals})
    selected_records: dict[str, list[dict[str, Any]]] = {}
    for provider in providers:
        selected_records[provider] = _select_monophonic(
            [record for record in accepted if record["provider"] == provider]
        )
    selected_records["combined"] = _select_monophonic(accepted)

    variants: dict[str, list[NoteEvent]] = {}
    phrase_documents: dict[str, list[dict[str, Any]]] = {}
    selected_ids: dict[str, set[str]] = {}
    for name, records in selected_records.items():
        notes = _records_to_notes(records)
        variants[name] = notes
        selected_ids[name] = {record["proposal_id"] for record in records}
        phrase_documents[name] = _phrase_records(
            records,
            notes,
            bpm=bpm,
            phrase_gap_beats=policy.phrase_gap_beats,
        )

    for record in audited:
        record["selected_variants"] = [
            name
            for name in sorted(selected_ids)
            if record["proposal_id"] in selected_ids[name]
        ]

    rejection_counts: dict[str, int] = {}
    for record in audited:
        for reason in record["reasons"]:
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
    document = {
        "schema": VOCAL_BOUNDARY_REPAIR_SCHEMA,
        "policy": {
            "name": "sunofriend-agreed-f0-boundary-repair-v1",
            "pitch_authority": "pyin+rmvpe agreement only",
            "boundary_authority": providers,
            "agreement_tolerance_cents": policy.agreement_tolerance_cents,
            "boundary_pitch_tolerance_cents": (
                policy.boundary_pitch_tolerance_cents
            ),
            "maximum_pitch_mad_cents": policy.maximum_pitch_mad_cents,
            "minimum_support_ratio": policy.minimum_support_ratio,
            "minimum_support_frames": policy.minimum_support_frames,
            "maximum_edge_gap_ms": policy.maximum_edge_gap_ms,
            "minimum_note_ms": policy.minimum_note_ms,
            "monophonic_selection": "weighted non-overlapping interval v1",
            "raw_candidates_mutated": False,
        },
        "summary": {
            "proposals": len(audited),
            "accepted_before_monophonic_selection": len(accepted),
            "rejected": len(audited) - len(accepted),
            "rejection_counts": dict(sorted(rejection_counts.items())),
            "variant_notes": {
                name: len(notes) for name, notes in sorted(variants.items())
            },
            "phrase_counts": {
                name: len(phrases)
                for name, phrases in sorted(phrase_documents.items())
            },
        },
        "proposals": audited,
        "phrases": phrase_documents,
        "variants": {
            name: [_note_document(note) for note in notes]
            for name, notes in sorted(variants.items())
        },
    }
    return variants, document


def _validated_timeline(
    alignment: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    values = list(alignment)
    times = [float(record["time_seconds"]) for record in values]
    if any(not math.isfinite(value) or value < 0 for value in times):
        raise ValueError("alignment times must be finite and non-negative")
    if any(right <= left for left, right in zip(times, times[1:])):
        raise ValueError("alignment times must be strictly increasing")
    return values


def _timeline_hop(timeline: Sequence[Mapping[str, Any]]) -> float:
    gaps = [
        float(right["time_seconds"]) - float(left["time_seconds"])
        for left, right in zip(timeline, timeline[1:])
    ]
    return float(median(gaps)) if gaps else 0.01


def _agreement_frame(
    record: Mapping[str, Any],
    tolerance_cents: float,
) -> dict[str, float] | None:
    observations = record.get("observations", {})
    if not isinstance(observations, Mapping):
        return None
    pyin = observations.get("pyin")
    rmvpe = observations.get("rmvpe")
    if not isinstance(pyin, Mapping) or not isinstance(rmvpe, Mapping):
        return None
    if pyin.get("status") != "voiced" or rmvpe.get("status") != "voiced":
        return None
    pyin_midi = pyin.get("fractional_midi")
    rmvpe_midi = rmvpe.get("fractional_midi")
    if pyin_midi is None or rmvpe_midi is None:
        return None
    pyin_midi = float(pyin_midi)
    rmvpe_midi = float(rmvpe_midi)
    difference_cents = abs(pyin_midi - rmvpe_midi) * 100.0
    if difference_cents > tolerance_cents:
        return None
    pyin_confidence = float(pyin.get("confidence", 0.0))
    rmvpe_confidence = float(rmvpe.get("confidence", 0.0))
    # These confidence values come from different, uncalibrated estimators.
    # Agreement is a pitch relation, so neither model gets a larger vote.
    agreed_midi = (pyin_midi + rmvpe_midi) / 2.0
    return {
        "time_seconds": float(record["time_seconds"]),
        "midi": agreed_midi,
        "difference_cents": difference_cents,
        "confidence": (pyin_confidence + rmvpe_confidence) / 2.0,
    }


def _audit_proposal(
    proposal: BoundaryProposal,
    timeline: Sequence[Mapping[str, Any]],
    *,
    hop: float,
    config: BoundaryRepairConfig,
) -> dict[str, Any]:
    proposal_id = f"{proposal.provider}:{proposal.source_event_id}"
    interval_frames = [
        record
        for record in timeline
        if proposal.start_seconds <= float(record["time_seconds"]) < proposal.end_seconds
    ]
    support = [
        frame
        for record in interval_frames
        if (
            frame := _agreement_frame(
                record,
                config.agreement_tolerance_cents,
            )
        )
        is not None
    ]
    duration = proposal.end_seconds - proposal.start_seconds
    support_ratio = len(support) / len(interval_frames) if interval_frames else 0.0
    midis = [frame["midi"] for frame in support]
    pair_differences = [frame["difference_cents"] for frame in support]
    confidence_values = [frame["confidence"] for frame in support]
    centre = float(median(midis)) if midis else None
    pitch_mad_cents = (
        float(median(abs(value - centre) for value in midis)) * 100.0
        if centre is not None
        else None
    )
    pitch_error_cents = (
        abs(centre - proposal.pitch) * 100.0 if centre is not None else None
    )
    start_gap_ms = (
        max(0.0, support[0]["time_seconds"] - proposal.start_seconds) * 1000.0
        if support
        else None
    )
    end_gap_ms = (
        max(0.0, proposal.end_seconds - support[-1]["time_seconds"] - hop)
        * 1000.0
        if support
        else None
    )
    reasons: list[str] = []
    if duration * 1000.0 < config.minimum_note_ms:
        reasons.append("below-minimum-duration")
    if len(support) < config.minimum_support_frames:
        reasons.append("insufficient-agreement-frames")
    if support_ratio < config.minimum_support_ratio:
        reasons.append("insufficient-agreement-coverage")
    if start_gap_ms is not None and start_gap_ms > config.maximum_edge_gap_ms:
        reasons.append("unsupported-start-boundary")
    if end_gap_ms is not None and end_gap_ms > config.maximum_edge_gap_ms:
        reasons.append("unsupported-end-boundary")
    if (
        pitch_mad_cents is not None
        and pitch_mad_cents > config.maximum_pitch_mad_cents
    ):
        reasons.append("unstable-agreed-pitch")
    if (
        pitch_error_cents is not None
        and pitch_error_cents > config.boundary_pitch_tolerance_cents
    ):
        reasons.append("boundary-pitch-disagrees")
    output_pitch = _nearest_midi(centre) if centre is not None else None
    velocity = proposal.velocity or (
        max(1, min(127, round((proposal.confidence or 0.70) * 127)))
    )
    stability = (
        0.0
        if pitch_mad_cents is None
        else max(0.0, 1.0 - pitch_mad_cents / config.maximum_pitch_mad_cents)
    )
    pitch_match = (
        0.0
        if pitch_error_cents is None
        else max(
            0.0,
            1.0 - pitch_error_cents / config.boundary_pitch_tolerance_cents,
        )
    )
    mean_confidence = (
        sum(confidence_values) / len(confidence_values)
        if confidence_values
        else 0.0
    )
    # Do not rank with cross-model confidence: pYIN probabilities and RMVPE
    # activations are not calibrated to one another.
    score = 0.50 * support_ratio + 0.30 * stability + 0.20 * pitch_match
    return {
        "proposal_id": proposal_id,
        "provider": proposal.provider,
        "source_event_id": proposal.source_event_id,
        "status": "accepted" if not reasons else "rejected",
        "reasons": reasons,
        "boundary": {
            "start_seconds": proposal.start_seconds,
            "end_seconds": proposal.end_seconds,
            "pitch": proposal.pitch,
            "confidence": proposal.confidence,
            "velocity": proposal.velocity,
        },
        "support": {
            "interval_frames": len(interval_frames),
            "agreement_frames": len(support),
            "agreement_ratio": round(support_ratio, 9),
            "median_midi": None if centre is None else round(centre, 9),
            "pitch_mad_cents": (
                None if pitch_mad_cents is None else round(pitch_mad_cents, 6)
            ),
            "boundary_pitch_error_cents": (
                None if pitch_error_cents is None else round(pitch_error_cents, 6)
            ),
            "pair_difference_median_cents": (
                None
                if not pair_differences
                else round(float(median(pair_differences)), 6)
            ),
            "start_gap_ms": None if start_gap_ms is None else round(start_gap_ms, 6),
            "end_gap_ms": None if end_gap_ms is None else round(end_gap_ms, 6),
            "mean_confidence": round(mean_confidence, 9),
        },
        "output": (
            None
            if output_pitch is None
            else {
                "start_seconds": proposal.start_seconds,
                "end_seconds": proposal.end_seconds,
                "pitch": output_pitch,
                "velocity": velocity,
            }
        ),
        "selection_score": round(score, 9),
    }


def _select_monophonic(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Weighted interval scheduling without altering accepted boundaries."""

    ordered = sorted(
        records,
        key=lambda record: (
            record["output"]["end_seconds"],
            record["output"]["start_seconds"],
            record["provider"],
            record["proposal_id"],
        ),
    )
    predecessors: list[int] = []
    for index, record in enumerate(ordered):
        start = float(record["output"]["start_seconds"])
        predecessor = -1
        for candidate_index in range(index - 1, -1, -1):
            if float(ordered[candidate_index]["output"]["end_seconds"]) <= start:
                predecessor = candidate_index
                break
        predecessors.append(predecessor)

    totals = [0.0] * (len(ordered) + 1)
    choices = [False] * len(ordered)
    for index, record in enumerate(ordered, start=1):
        duration = (
            float(record["output"]["end_seconds"])
            - float(record["output"]["start_seconds"])
        )
        weight = duration * (1.0 + float(record["selection_score"])) + 0.03
        include = weight + totals[predecessors[index - 1] + 1]
        exclude = totals[index - 1]
        if include > exclude + 1e-12:
            totals[index] = include
            choices[index - 1] = True
        else:
            totals[index] = exclude

    selected: list[dict[str, Any]] = []
    index = len(ordered) - 1
    while index >= 0:
        record = ordered[index]
        duration = (
            float(record["output"]["end_seconds"])
            - float(record["output"]["start_seconds"])
        )
        weight = duration * (1.0 + float(record["selection_score"])) + 0.03
        include = weight + totals[predecessors[index] + 1]
        exclude = totals[index]
        if choices[index] and include > exclude + 1e-12:
            selected.append(record)
            index = predecessors[index]
        else:
            index -= 1
    return sorted(
        selected,
        key=lambda record: (
            record["output"]["start_seconds"],
            record["output"]["pitch"],
            record["provider"],
        ),
    )


def _records_to_notes(records: Sequence[Mapping[str, Any]]) -> list[NoteEvent]:
    notes = [
        NoteEvent(
            start=float(record["output"]["start_seconds"]),
            end=float(record["output"]["end_seconds"]),
            pitch=int(record["output"]["pitch"]),
            velocity=int(record["output"]["velocity"]),
        )
        for record in records
    ]
    # The interval schedule is non-overlapping. Small floating-point boundary
    # discrepancies are clipped deterministically for explicit monophony.
    for index in range(len(notes) - 1):
        if notes[index].end > notes[index + 1].start:
            notes[index] = replace(notes[index], end=notes[index + 1].start)
    return notes


def _phrase_records(
    records: Sequence[Mapping[str, Any]],
    notes: Sequence[NoteEvent],
    *,
    bpm: float,
    phrase_gap_beats: float,
) -> list[dict[str, Any]]:
    if not notes:
        return []
    gap_seconds = max(0.35, 60.0 / bpm * phrase_gap_beats)
    groups: list[list[int]] = [[0]]
    for index in range(1, len(notes)):
        if notes[index].start - notes[index - 1].end > gap_seconds:
            groups.append([index])
        else:
            groups[-1].append(index)
    phrases: list[dict[str, Any]] = []
    for index, group in enumerate(groups):
        selected_records = [records[note_index] for note_index in group]
        score = sum(
            float(record["selection_score"]) for record in selected_records
        ) / len(selected_records)
        phrases.append(
            {
                "phrase_index": index,
                "start_seconds": notes[group[0]].start,
                "end_seconds": notes[group[-1]].end,
                "note_count": len(group),
                "providers": sorted(
                    {str(record["provider"]) for record in selected_records}
                ),
                "mean_selection_score": round(score, 9),
                "mean_agreement_ratio": round(
                    sum(
                        float(record["support"]["agreement_ratio"])
                        for record in selected_records
                    )
                    / len(selected_records),
                    9,
                ),
            }
        )
    ranked = sorted(
        range(len(phrases)),
        key=lambda position: (
            -phrases[position]["mean_selection_score"],
            phrases[position]["start_seconds"],
        ),
    )
    ranks = {position: rank + 1 for rank, position in enumerate(ranked)}
    for position, phrase in enumerate(phrases):
        phrase["confidence_rank"] = ranks[position]
    return phrases


def _note_document(note: NoteEvent) -> dict[str, Any]:
    return {
        "start_seconds": note.start,
        "end_seconds": note.end,
        "pitch": note.pitch,
        "velocity": note.velocity,
    }


def _nearest_midi(value: float) -> int:
    return max(0, min(127, int(math.floor(value + 0.5))))


__all__ = [
    "BoundaryProposal",
    "BoundaryRepairConfig",
    "VOCAL_BOUNDARY_REPAIR_SCHEMA",
    "repair_vocal_boundaries",
]
