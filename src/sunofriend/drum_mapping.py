"""Review-only mapping from source-event timbre families to GM drum notes.

Drum MIDI pitch selects a kit piece rather than a musical pitch.  A kick or
snare stem can contain several distinct sounds even when the transcription
currently puts every hit on one note.  This module turns source-event cluster
evidence into a deterministic *proposal* for separate General MIDI notes.  It
never overwrites the supplied MIDI and it retains outliers on their original
note for human review.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Sequence


DRUM_MAPPING_SCHEMA = "sunofriend.gm-drum-family-mapping.v1"
MINIMUM_CHANGE_SCORE = 55.0
MINIMUM_CHANGE_ADVANTAGE = 8.0

# General MIDI percussion key map (channel 10 / zero-based channel 9).
GM_DRUM_NOTE_NAMES: dict[int, str] = {
    35: "Acoustic Bass Drum",
    36: "Bass Drum 1",
    37: "Side Stick",
    38: "Acoustic Snare",
    39: "Hand Clap",
    40: "Electric Snare",
    41: "Low Floor Tom",
    42: "Closed Hi-Hat",
    43: "High Floor Tom",
    44: "Pedal Hi-Hat",
    45: "Low Tom",
    46: "Open Hi-Hat",
    47: "Low-Mid Tom",
    48: "Hi-Mid Tom",
    49: "Crash Cymbal 1",
    50: "High Tom",
    51: "Ride Cymbal 1",
    52: "Chinese Cymbal",
    53: "Ride Bell",
    54: "Tambourine",
    55: "Splash Cymbal",
    56: "Cowbell",
    57: "Crash Cymbal 2",
    58: "Vibraslap",
    59: "Ride Cymbal 2",
    60: "Hi Bongo",
    61: "Low Bongo",
    62: "Mute Hi Conga",
    63: "Open Hi Conga",
    64: "Low Conga",
    65: "High Timbale",
    66: "Low Timbale",
    67: "High Agogo",
    68: "Low Agogo",
    69: "Cabasa",
    70: "Maracas",
    71: "Short Whistle",
    72: "Long Whistle",
    73: "Short Guiro",
    74: "Long Guiro",
    75: "Claves",
    76: "Hi Wood Block",
    77: "Low Wood Block",
    78: "Mute Cuica",
    79: "Open Cuica",
    80: "Mute Triangle",
    81: "Open Triangle",
}

_CANDIDATES: dict[str, tuple[int, ...]] = {
    "kick": (35, 36),
    "snare": (37, 38, 39, 40),
    "hat": (42, 44, 46),
    "cymbals": (49, 51, 52, 53, 55, 57, 59),
    "toms": (41, 43, 45, 47, 48, 50),
    "other_kit": tuple(range(35, 82)),
    "drums": tuple(range(35, 82)),
}


def drum_note_candidates(kind: str) -> tuple[int, ...]:
    """Return the stable candidate GM percussion notes for a drum role."""

    normalized = str(kind).strip().lower()
    try:
        return _CANDIDATES[normalized]
    except KeyError as exc:
        raise ValueError(f"No GM drum-note candidate set for role: {kind!r}") from exc


def propose_drum_family_mapping(
    *,
    kind: str,
    clip: Any,
    source_event_clusters: dict[str, Any],
    source_vectors: Sequence[Sequence[float]],
    candidate_vectors: dict[int, Sequence[float]],
) -> tuple[Any, dict[str, Any]]:
    """Return a separate proposed clip and deterministic mapping evidence.

    Candidate matching uses the same 20 explainable timbre features as source
    clustering.  The first 17 describe identity/timbre and contribute 80%; the
    final three describe attack/decay shape and contribute 20%.
    """

    import numpy as np

    candidates = drum_note_candidates(kind)
    missing = [note for note in candidates if note not in candidate_vectors]
    if missing:
        raise ValueError(f"Missing candidate vectors for GM drum notes: {missing}")
    source = np.asarray(source_vectors, dtype=np.float64)
    candidate = np.asarray(
        [candidate_vectors[note] for note in candidates], dtype=np.float64
    )
    if source.ndim != 2 or source.shape[1] < 20:
        raise ValueError("Source vectors must contain at least 20 timbre features")
    if candidate.ndim != 2 or candidate.shape[1] != source.shape[1]:
        raise ValueError("Candidate and source timbre vectors must have equal width")

    clusters = list(source_event_clusters.get("identity_candidate_clusters", []))
    if not clusters:
        raise ValueError("Source-event evidence contains no candidate timbre families")
    events = list(source_event_clusters.get("events", []))
    units = _mapping_units(clusters, events, source)
    unit_profiles = np.asarray([row["profile"] for row in units], dtype=np.float64)
    all_profiles = np.vstack([unit_profiles, candidate])
    scale = np.std(all_profiles, axis=0)
    scale = np.where(scale < 0.025, 0.025, scale)
    scored: dict[str, list[dict[str, Any]]] = {}
    for unit, unit_profile in zip(units, unit_profiles):
        rows = []
        for note, profile in zip(candidates, candidate):
            identity_distance = float(
                np.sqrt(np.mean(((profile[:17] - unit_profile[:17]) / scale[:17]) ** 2))
            )
            articulation_distance = float(
                np.sqrt(
                    np.mean(
                        ((profile[17:20] - unit_profile[17:20]) / scale[17:20]) ** 2
                    )
                )
            )
            identity_similarity = 1.0 / (1.0 + identity_distance)
            articulation_similarity = 1.0 / (1.0 + articulation_distance)
            combined = 0.80 * identity_similarity + 0.20 * articulation_similarity
            rows.append(
                {
                    "note": int(note),
                    "name": GM_DRUM_NOTE_NAMES[int(note)],
                    "combined_score": round(combined * 100.0, 3),
                    "timbre_similarity": round(identity_similarity * 100.0, 3),
                    "articulation_similarity": round(
                        articulation_similarity * 100.0, 3
                    ),
                }
            )
        rows.sort(key=lambda row: (-float(row["combined_score"]), int(row["note"])))
        scored[str(unit["unit_id"])] = rows

    assignments = _distinct_assignments(scored)
    mapping_rows = []
    for unit in units:
        unit_id = str(unit["unit_id"])
        distinct = assignments[unit_id]
        independent = scored[unit_id][0]
        source_pitch = int(unit["source_pitch"])
        existing = next(
            (row for row in scored[unit_id] if int(row["note"]) == source_pitch),
            None,
        )
        if existing is None:
            proposed = distinct
            change_reason = "existing note is outside this role's candidate set"
        else:
            advantage = float(distinct["combined_score"]) - float(
                existing["combined_score"]
            )
            if (
                int(distinct["note"]) != source_pitch
                and float(distinct["combined_score"]) >= MINIMUM_CHANGE_SCORE
                and advantage >= MINIMUM_CHANGE_ADVANTAGE
            ):
                proposed = distinct
                change_reason = (
                    "candidate cleared the absolute-score and improvement-margin "
                    "guardrails"
                )
            else:
                proposed = existing
                change_reason = (
                    "retained existing valid GM note because the alternative did "
                    "not clear both conservative change guardrails"
                )
        mapping_rows.append(
            {
                "mapping_unit_id": unit_id,
                "cluster_id": str(unit["cluster_id"]),
                "source_pitch": source_pitch,
                "event_count": int(unit["event_count"]),
                "event_indices": list(unit["event_indices"]),
                "medoid_event_index": int(unit["medoid_event_index"]),
                "assigned_note": int(proposed["note"]),
                "assigned_name": str(proposed["name"]),
                "assigned_score": float(proposed["combined_score"]),
                "existing_note_score": (
                    float(existing["combined_score"]) if existing is not None else None
                ),
                "change_from_existing": int(proposed["note"]) != source_pitch,
                "change_reason": change_reason,
                "independent_best_note": int(independent["note"]),
                "independent_best_name": str(independent["name"]),
                "distinct_candidate_note": int(distinct["note"]),
                "distinct_candidate_name": str(distinct["name"]),
                "distinct_candidate_score": float(distinct["combined_score"]),
                "distinct_assignment_changed_best": int(distinct["note"])
                != int(independent["note"]),
                "candidate_ranking": scored[unit_id],
            }
        )

    unit_to_note = {
        (row["cluster_id"], int(row["source_pitch"])): int(row["assigned_note"])
        for row in mapping_rows
    }
    event_by_note_index = {
        int(row["note_index"]): row for row in source_event_clusters.get("events", [])
    }
    changed_note_indices: list[int] = []
    outlier_note_indices: list[int] = []
    unanalyzed_note_indices: list[int] = []
    proposed_notes = []
    for note_index, note in enumerate(clip.notes):
        event = event_by_note_index.get(note_index)
        replacement_pitch = int(note.pitch)
        if event is None:
            unanalyzed_note_indices.append(note_index)
        elif bool(event.get("identity_outlier")):
            outlier_note_indices.append(note_index)
        elif (
            str(event.get("identity_candidate_cluster")),
            int(note.pitch),
        ) in unit_to_note:
            replacement_pitch = unit_to_note[
                (str(event["identity_candidate_cluster"]), int(note.pitch))
            ]
        if replacement_pitch != int(note.pitch):
            changed_note_indices.append(note_index)
        proposed_notes.append(replace(note, pitch=replacement_pitch))

    from .clip import Instrument

    proposed_clip = replace(
        clip,
        title=f"{clip.title} - GM drum-family proposal",
        instrument=Instrument(
            role=clip.instrument.role,
            program=0,
            channel=9,
            suggestions=tuple(row["assigned_name"] for row in mapping_rows),
        ),
        notes=tuple(proposed_notes),
    )
    evidence = {
        "schema": DRUM_MAPPING_SCHEMA,
        "operation": "gm-drum-family-mapping",
        "status": "complete",
        "review_required": True,
        "advisory_only": True,
        "kind": str(kind).strip().lower(),
        "method": {
            "candidate_notes": [
                {"note": note, "name": GM_DRUM_NOTE_NAMES[note]} for note in candidates
            ],
            "score": (
                "80% explainable timbre-feature similarity plus 20% attack/decay "
                "shape similarity; scores are relative audition evidence"
            ),
            "assignment": (
                "deterministic margin-first assignment keeps candidate timbre "
                "families on distinct GM notes when the candidate set permits"
            ),
            "mapping_units": (
                "Each persistent timbre family is split by existing MIDI note "
                "before matching, so a proposal cannot collapse already distinct "
                "kit pieces. Each unit uses the median of its event vectors."
            ),
            "change_guardrails": {
                "minimum_candidate_score": MINIMUM_CHANGE_SCORE,
                "minimum_advantage_over_existing_note": MINIMUM_CHANGE_ADVANTAGE,
                "policy": (
                    "A valid existing role note is retained unless a distinct "
                    "candidate clears both thresholds. Scores are relative evidence, "
                    "not calibrated confidence."
                ),
            },
            "outlier_policy": "retain the original MIDI note for review",
            "unanalyzed_event_policy": "retain the original MIDI note",
        },
        "summary": {
            "candidate_timbre_family_count": len(mapping_rows),
            "source_identity_cluster_count": len(clusters),
            "distinct_assigned_note_count": len(
                {row["assigned_note"] for row in mapping_rows}
            ),
            "midi_note_count": len(clip.notes),
            "proposed_note_change_count": len(changed_note_indices),
            "retained_outlier_note_count": len(outlier_note_indices),
            "retained_unanalyzed_note_count": len(unanalyzed_note_indices),
        },
        "family_mappings": mapping_rows,
        "effects": {
            "source_midi_overwritten": False,
            "timing_changed": False,
            "velocity_changed": False,
            "duration_changed": False,
            "channel_in_proposed_copy": 9,
            "changed_note_indices": changed_note_indices,
            "retained_outlier_note_indices": outlier_note_indices,
            "retained_unanalyzed_note_indices": unanalyzed_note_indices,
        },
        "warnings": [
            "GM drum-note sound varies with the selected drum kit and SoundFont; audition the proposed copy in GarageBand before accepting it.",
            "A separator artefact can form a coherent cluster. Distinct does not necessarily mean musically intended.",
            "The score/margin guardrails protect a valid existing GM note, but they are policy thresholds rather than learned confidence calibration.",
        ],
    }
    return proposed_clip, evidence


def _mapping_units(
    clusters: Sequence[dict[str, Any]],
    events: Sequence[dict[str, Any]],
    source: Any,
) -> list[dict[str, Any]]:
    """Split identity clusters by existing kit note and choose unit medoids."""

    import numpy as np

    units = []
    for cluster in clusters:
        cluster_id = str(cluster["cluster_id"])
        cluster_events = [
            row
            for row in events
            if row.get("identity_candidate_cluster") == cluster_id
            and not bool(row.get("identity_outlier"))
        ]
        by_pitch: dict[int, list[dict[str, Any]]] = {}
        for row in cluster_events:
            by_pitch.setdefault(int(row["pitch"]), []).append(row)
        for pitch, members in sorted(by_pitch.items()):
            event_indices = sorted(int(row["event_index"]) for row in members)
            if any(index < 0 or index >= len(source) for index in event_indices):
                raise ValueError("Source-event index is out of range")
            profile = np.median(source[event_indices], axis=0)
            medoid = min(
                event_indices,
                key=lambda index: (
                    float(np.sqrt(np.mean((source[index] - profile) ** 2))),
                    index,
                ),
            )
            units.append(
                {
                    "unit_id": f"{cluster_id}-P{pitch:03d}",
                    "cluster_id": cluster_id,
                    "source_pitch": pitch,
                    "event_count": len(event_indices),
                    "event_indices": event_indices,
                    "medoid_event_index": medoid,
                    "profile": profile,
                }
            )
    if not units:
        raise ValueError("Source-event evidence contains no retained mapping units")
    return units


def _distinct_assignments(
    scored: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    remaining = set(scored)
    used: set[int] = set()
    assignments: dict[str, dict[str, Any]] = {}
    while remaining:
        choices = []
        for cluster_id in sorted(remaining):
            available = [
                row for row in scored[cluster_id] if int(row["note"]) not in used
            ]
            if not available:
                available = list(scored[cluster_id])
            best = available[0]
            second_score = (
                float(available[1]["combined_score"]) if len(available) > 1 else 0.0
            )
            margin = float(best["combined_score"]) - second_score
            choices.append((margin, float(best["combined_score"]), cluster_id, best))
        choices.sort(key=lambda item: (-item[0], -item[1], item[2]))
        _, _, cluster_id, best = choices[0]
        assignments[cluster_id] = best
        used.add(int(best["note"]))
        remaining.remove(cluster_id)
    return assignments


__all__ = [
    "DRUM_MAPPING_SCHEMA",
    "GM_DRUM_NOTE_NAMES",
    "MINIMUM_CHANGE_ADVANTAGE",
    "MINIMUM_CHANGE_SCORE",
    "drum_note_candidates",
    "propose_drum_family_mapping",
]
