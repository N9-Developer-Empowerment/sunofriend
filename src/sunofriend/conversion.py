"""Shared conversion-mode and note-provenance contracts.

MIDI itself cannot explain whether a note was heard in a stem, repaired from
weak evidence, or composed from musical structure.  Sunofriend therefore
writes a small JSON sidecar beside generated MIDI.  Keeping this information
out of :class:`~sunofriend.models.NoteEvent` preserves the stable note API used
by the legacy pipeline and GarageBand exporter.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping

from .models import NoteEvent

ConversionMode = Literal["exact", "repair", "reconstruct"]
NoteOrigin = Literal["observed", "repaired", "inferred"]
ConfidenceTier = Literal["main", "possible", "uncertain"]
ConfidenceBasis = Literal["measured", "policy", "aggregate"]

CONVERSION_MODES: tuple[ConversionMode, ...] = ("exact", "repair", "reconstruct")


def validate_conversion_mode(value: str) -> ConversionMode:
    mode = str(value).strip().lower()
    if mode not in CONVERSION_MODES:
        choices = ", ".join(CONVERSION_MODES)
        raise ValueError(f"conversion_mode must be one of: {choices}")
    return mode  # type: ignore[return-value]


@dataclass(frozen=True)
class NoteProvenance:
    """Serializable evidence attached to one emitted MIDI note."""

    start: float
    end: float
    pitch: int
    velocity: int
    origin: NoteOrigin
    confidence: float
    tier: ConfidenceTier = "main"
    confidence_basis: ConfidenceBasis = "measured"
    family: str | None = None
    sources: tuple[str, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (math.isfinite(self.start) and math.isfinite(self.end)):
            raise ValueError("provenance times must be finite")
        if self.end <= self.start:
            raise ValueError("provenance end must be after start")
        if not 0 <= int(self.pitch) <= 127:
            raise ValueError("provenance pitch must be between 0 and 127")
        if not 1 <= int(self.velocity) <= 127:
            raise ValueError("provenance velocity must be between 1 and 127")
        confidence = float(self.confidence)
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.origin not in {"observed", "repaired", "inferred"}:
            raise ValueError(f"unknown note origin: {self.origin}")
        if self.tier not in {"main", "possible", "uncertain"}:
            raise ValueError(f"unknown confidence tier: {self.tier}")
        if self.confidence_basis not in {"measured", "policy", "aggregate"}:
            raise ValueError(f"unknown confidence basis: {self.confidence_basis}")
        object.__setattr__(self, "pitch", int(self.pitch))
        object.__setattr__(self, "velocity", int(self.velocity))
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "sources", tuple(str(item) for item in self.sources))
        object.__setattr__(self, "details", dict(self.details))

    @classmethod
    def from_note(
        cls,
        note: NoteEvent,
        *,
        origin: NoteOrigin,
        confidence: float,
        tier: ConfidenceTier = "main",
        confidence_basis: ConfidenceBasis = "measured",
        family: str | None = None,
        sources: Iterable[str] = (),
        details: Mapping[str, Any] | None = None,
    ) -> "NoteProvenance":
        return cls(
            start=note.start,
            end=note.end,
            pitch=note.pitch,
            velocity=note.velocity,
            origin=origin,
            confidence=confidence,
            tier=tier,
            confidence_basis=confidence_basis,
            family=family,
            sources=tuple(sources),
            details=details or {},
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["sources"] = list(self.sources)
        value["details"] = dict(self.details)
        return value


def provenance_for_notes(
    notes: Iterable[NoteEvent],
    *,
    origin: NoteOrigin,
    confidence: float,
    tier: ConfidenceTier = "main",
    confidence_basis: ConfidenceBasis = "measured",
    family: str | None = None,
    sources: Iterable[str] = (),
) -> list[NoteProvenance]:
    return [
        NoteProvenance.from_note(
            note,
            origin=origin,
            confidence=confidence,
            tier=tier,
            confidence_basis=confidence_basis,
            family=family,
            sources=sources,
        )
        for note in notes
    ]


def retarget_note_provenance(
    notes: Iterable[NoteEvent],
    records: Iterable[NoteProvenance],
    *,
    mark_changed_as_repaired: bool = False,
) -> list[NoteProvenance]:
    """Align provenance with the exact normalized notes that will be emitted."""

    available = list(records)
    result: list[NoteProvenance] = []
    for note in notes:
        if not available:
            break
        index = min(
            range(len(available)),
            key=lambda item: (
                available[item].pitch != note.pitch,
                abs(available[item].start - note.start),
            ),
        )
        record = available.pop(index)
        changed = (
            record.pitch != note.pitch
            or abs(record.start - note.start) > 1e-6
            or abs(record.end - note.end) > 1e-6
            or record.velocity != note.velocity
        )
        result.append(
            NoteProvenance.from_note(
                note,
                origin=(
                    "repaired"
                    if mark_changed_as_repaired and changed and record.origin == "observed"
                    else record.origin
                ),
                confidence=record.confidence,
                tier=record.tier,
                confidence_basis=record.confidence_basis,
                family=record.family,
                sources=record.sources,
                details=record.details,
            )
        )
    return result


def write_note_provenance(
    path: str | Path,
    records: Iterable[NoteProvenance],
    *,
    conversion_mode: str,
    source_stem: str | Path,
    variant: str,
) -> Path:
    """Atomically write the provenance sidecar for a generated MIDI variant."""

    mode = validate_conversion_mode(conversion_mode)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    values = list(records)
    document = {
        "schema_version": 1,
        "conversion_mode": mode,
        "variant": str(variant),
        "source_stem": str(Path(source_stem)),
        "counts": {
            "notes": len(values),
            "observed": sum(item.origin == "observed" for item in values),
            "repaired": sum(item.origin == "repaired" for item in values),
            "inferred": sum(item.origin == "inferred" for item in values),
            "main": sum(item.tier == "main" for item in values),
            "possible": sum(item.tier == "possible" for item in values),
            "uncertain": sum(item.tier == "uncertain" for item in values),
            "measured_confidence": sum(
                item.confidence_basis == "measured" for item in values
            ),
            "policy_confidence": sum(
                item.confidence_basis == "policy" for item in values
            ),
            "aggregate_confidence": sum(
                item.confidence_basis == "aggregate" for item in values
            ),
        },
        "notes": [item.to_dict() for item in values],
    }
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
    return path


def partition_cross_stem_leakage(
    notes: Iterable[NoteEvent],
    records: Iterable[NoteProvenance],
    reference_records: Mapping[str, Iterable[NoteProvenance]],
    *,
    tolerance_seconds: float = 0.025,
    confidence_margin: float = 0.12,
    weak_confidence: float = 0.55,
) -> tuple[list[NoteEvent], list[NoteProvenance], list[NoteEvent], list[NoteProvenance]]:
    """Quarantine weak events better explained by another separated stem.

    Coincidence alone is not enough: real drums often strike together.  An
    event is moved only when it is already weak/possible and a nearby event in
    another stem has materially stronger absolute evidence.  Nothing is
    discarded; the fourth return value records the explaining stem/family.
    """

    if tolerance_seconds <= 0:
        raise ValueError("tolerance_seconds must be positive")
    if confidence_margin < 0:
        raise ValueError("confidence_margin must be non-negative")
    notes_by_key = {
        (round(note.start, 6), note.pitch): note
        for note in notes
    }
    references = [
        (part, record)
        for part, values in reference_records.items()
        for record in values
    ]
    main_notes: list[NoteEvent] = []
    main_records: list[NoteProvenance] = []
    uncertain_notes: list[NoteEvent] = []
    uncertain_records: list[NoteProvenance] = []
    for record in records:
        note = notes_by_key.get((round(record.start, 6), record.pitch))
        if note is None:
            note = min(
                notes_by_key.values(),
                key=lambda value: (
                    value.pitch != record.pitch,
                    abs(value.start - record.start),
                ),
                default=None,
            )
        if note is None:
            continue
        nearby = [
            (part, other)
            for part, other in references
            if abs(other.start - record.start) <= tolerance_seconds
        ]
        explaining = max(nearby, key=lambda item: item[1].confidence, default=None)
        weak = record.tier != "main" or record.confidence < weak_confidence
        dominated = bool(
            explaining
            and explaining[1].confidence >= record.confidence + confidence_margin
        )
        similarity = (
            _leakage_feature_similarity(record, explaining[1])
            if explaining is not None
            else 0.0
        )
        if weak and dominated and similarity >= 0.90:
            part, other = explaining
            details = dict(record.details)
            details["possible_leakage"] = {
                "stem": part,
                "family": other.family,
                "confidence": other.confidence,
                "offset_ms": round((record.start - other.start) * 1000.0, 3),
                "feature_similarity": round(similarity, 6),
            }
            uncertain_notes.append(note)
            uncertain_records.append(
                NoteProvenance.from_note(
                    note,
                    origin=record.origin,
                    confidence=record.confidence,
                    tier="uncertain",
                    confidence_basis=record.confidence_basis,
                    family=record.family,
                    sources=(*record.sources, "cross-stem-leakage"),
                    details=details,
                )
            )
        else:
            main_notes.append(note)
            main_records.append(record)
    return main_notes, main_records, uncertain_notes, uncertain_records


def _leakage_feature_similarity(
    candidate: NoteProvenance,
    reference: NoteProvenance,
) -> float:
    """Compare aligned spectral evidence; timing coincidence is insufficient."""

    required = (
        "dominant_hz",
        "spectral_centroid_hz",
        "low_ratio",
        "mid_ratio",
        "high_ratio",
    )
    if any(key not in candidate.details or key not in reference.details for key in required):
        return 0.0
    try:
        candidate_vector = [
            math.log1p(max(0.0, float(candidate.details["dominant_hz"]))) / 10.0,
            math.log1p(max(0.0, float(candidate.details["spectral_centroid_hz"]))) / 10.0,
            float(candidate.details["low_ratio"]),
            float(candidate.details["mid_ratio"]),
            float(candidate.details["high_ratio"]),
        ]
        reference_vector = [
            math.log1p(max(0.0, float(reference.details["dominant_hz"]))) / 10.0,
            math.log1p(max(0.0, float(reference.details["spectral_centroid_hz"]))) / 10.0,
            float(reference.details["low_ratio"]),
            float(reference.details["mid_ratio"]),
            float(reference.details["high_ratio"]),
        ]
    except (TypeError, ValueError):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in candidate_vector))
    right_norm = math.sqrt(sum(value * value for value in reference_vector))
    if left_norm <= 1e-9 or right_norm <= 1e-9:
        return 0.0
    return max(
        0.0,
        min(
            1.0,
            sum(left * right for left, right in zip(candidate_vector, reference_vector))
            / (left_norm * right_norm),
        ),
    )


def partition_uncertain_families(
    notes: Iterable[NoteEvent],
    records: Iterable[NoteProvenance],
    *,
    families: Iterable[str] = ("unknown",),
    confidence_floor: float = 0.40,
) -> tuple[list[NoteEvent], list[NoteProvenance], list[NoteEvent], list[NoteProvenance]]:
    """Move unknown or very weak semantic classifications to an audition track."""

    uncertain_families = {str(value) for value in families}
    records = list(records)
    notes = list(notes)
    main_notes: list[NoteEvent] = []
    main_records: list[NoteProvenance] = []
    uncertain_notes: list[NoteEvent] = []
    uncertain_records: list[NoteProvenance] = []
    for note in notes:
        record = min(
            records,
            key=lambda value: (
                value.pitch != note.pitch,
                abs(value.start - note.start),
            ),
            default=None,
        )
        is_uncertain = bool(
            record is None
            or record.family in uncertain_families
            or record.confidence < confidence_floor
        )
        if is_uncertain:
            uncertain_notes.append(note)
            if record is not None:
                uncertain_records.append(
                    NoteProvenance.from_note(
                        note,
                        origin=record.origin,
                        confidence=record.confidence,
                        tier="uncertain",
                        confidence_basis=record.confidence_basis,
                        family=record.family,
                        sources=record.sources,
                        details=record.details,
                    )
                )
        else:
            main_notes.append(note)
            main_records.append(record)
    return main_notes, main_records, uncertain_notes, uncertain_records


__all__ = [
    "CONVERSION_MODES",
    "ConfidenceTier",
    "ConfidenceBasis",
    "ConversionMode",
    "NoteOrigin",
    "NoteProvenance",
    "provenance_for_notes",
    "retarget_note_provenance",
    "partition_cross_stem_leakage",
    "partition_uncertain_families",
    "validate_conversion_mode",
    "write_note_provenance",
]
