"""Advisory velocity-layer and round-robin evidence for source events.

The analysis consumes the immutable source-event cluster report.  It discovers
repeatable dynamics and alternate recordings, but deliberately does not alter
MIDI velocities, sample selection, SoundFont zones or drum-family mappings.
"""

from __future__ import annotations

import html
import math
from collections import defaultdict
from typing import Any, Sequence


SOURCE_EVENT_DYNAMICS_SCHEMA = "sunofriend.source-event-dynamics.v1"
MINIMUM_LAYER_EVENTS = 8
MINIMUM_EVENTS_PER_LAYER = 4
MINIMUM_LAYER_FRACTION = 0.20
MINIMUM_LAYER_RMS_GAP_DB = 3.0
MINIMUM_ROUND_ROBIN_EVENTS = 3
MAXIMUM_ROUND_ROBIN_CANDIDATES = 3


def analyze_source_event_dynamics(
    source_event_clusters: dict[str, Any],
) -> dict[str, Any]:
    """Discover conservative layer and alternate-sample candidates."""

    import numpy as np

    events = list(source_event_clusters.get("events", []))
    if not events:
        raise ValueError("Source-event cluster report contains no events")
    grouped: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        cluster = event.get("identity_candidate_cluster")
        if cluster is None or bool(event.get("identity_outlier")):
            continue
        grouped[
            (
                str(cluster),
                int(event["pitch"]),
                str(event["articulation_cluster"]),
            )
        ].append(event)

    units = []
    event_assignments: dict[int, dict[str, Any]] = {}
    round_robin_sets = []
    for cluster_id, pitch, articulation_id in sorted(grouped):
        members = sorted(
            grouped[(cluster_id, pitch, articulation_id)],
            key=lambda row: (float(row["start_seconds"]), int(row["event_index"])),
        )
        unit_id = f"{cluster_id}-P{pitch:03d}-{articulation_id}"
        layers, split = _velocity_layers(members)
        layer_rows = []
        for layer_index, layer_events in enumerate(layers, 1):
            layer_id = f"L{layer_index}"
            round_robin = _round_robin_candidates(layer_events)
            candidate_indices = list(round_robin["candidate_event_indices"])
            if candidate_indices:
                round_robin_sets.append(
                    {
                        "unit_id": unit_id,
                        "layer_id": layer_id,
                        **round_robin,
                    }
                )
            velocities = [int(row["velocity"]) for row in layer_events]
            rms_db = [_rms_db(row) for row in layer_events]
            layer_rows.append(
                {
                    "layer_id": layer_id,
                    "event_count": len(layer_events),
                    "event_indices": [int(row["event_index"]) for row in layer_events],
                    "note_indices": [int(row["note_index"]) for row in layer_events],
                    "velocity_range": [min(velocities), max(velocities)],
                    "median_velocity": _round(float(np.median(velocities)), 3),
                    "rms_db_range": [
                        _round(min(rms_db), 3),
                        _round(max(rms_db), 3),
                    ],
                    "median_rms_db": _round(float(np.median(rms_db)), 3),
                    "round_robin": round_robin,
                }
            )
            for event in layer_events:
                event_index = int(event["event_index"])
                event_assignments[event_index] = {
                    "unit_id": unit_id,
                    "layer_id": layer_id,
                    "round_robin_candidate": event_index in candidate_indices,
                }
        units.append(
            {
                "unit_id": unit_id,
                "identity_candidate_cluster": cluster_id,
                "pitch": pitch,
                "articulation_cluster": articulation_id,
                "event_count": len(members),
                "velocity_layer_candidate": len(layers) == 2,
                "velocity_split": split,
                "layers": layer_rows,
            }
        )

    event_rows = []
    for event in events:
        assignment = event_assignments.get(int(event["event_index"]))
        event_rows.append(
            {
                "event_index": int(event["event_index"]),
                "note_index": int(event["note_index"]),
                "start_seconds": float(event["start_seconds"]),
                "pitch": int(event["pitch"]),
                "velocity": int(event["velocity"]),
                "rms": float(event["rms"]),
                "rms_db": _round(_rms_db(event), 3),
                "identity_candidate_cluster": event.get("identity_candidate_cluster"),
                "articulation_cluster": event.get("articulation_cluster"),
                "identity_outlier": bool(event.get("identity_outlier")),
                "isolated": bool(event.get("isolated")),
                "analysis_unit": assignment["unit_id"] if assignment else None,
                "velocity_layer": assignment["layer_id"] if assignment else None,
                "round_robin_candidate": (
                    bool(assignment["round_robin_candidate"]) if assignment else False
                ),
            }
        )

    layer_candidates = [row for row in units if row["velocity_layer_candidate"]]
    selected_round_robins = {
        index for row in round_robin_sets for index in row["candidate_event_indices"]
    }
    return {
        "schema": SOURCE_EVENT_DYNAMICS_SCHEMA,
        "operation": "source-event-dynamics",
        "status": "complete",
        "advisory_only": True,
        "source": source_event_clusters.get("source"),
        "midi": source_event_clusters.get("midi"),
        "method": {
            "comparison_unit": (
                "same candidate timbre family, MIDI pitch and articulation group"
            ),
            "velocity_layers": {
                "minimum_unit_events": MINIMUM_LAYER_EVENTS,
                "minimum_events_per_layer": MINIMUM_EVENTS_PER_LAYER,
                "minimum_fraction_per_layer": MINIMUM_LAYER_FRACTION,
                "minimum_median_rms_gap_db": MINIMUM_LAYER_RMS_GAP_DB,
                "split_selection": (
                    "largest adjacent RMS-dB gap; ties favour the "
                    "most balanced split and then the earlier threshold"
                ),
            },
            "round_robin": {
                "minimum_isolated_events_per_layer": MINIMUM_ROUND_ROBIN_EVENTS,
                "maximum_candidates": MAXIMUM_ROUND_ROBIN_CANDIDATES,
                "selection": (
                    "explainable-timbre medoid followed by deterministic diverse "
                    "central events; the most distant 20% are excluded from selection"
                ),
            },
        },
        "summary": {
            "source_event_count": len(events),
            "comparable_unit_count": len(units),
            "velocity_layer_candidate_unit_count": len(layer_candidates),
            "velocity_layer_count": sum(len(row["layers"]) for row in units),
            "round_robin_candidate_set_count": len(round_robin_sets),
            "round_robin_candidate_event_count": len(selected_round_robins),
            "retained_outlier_count": sum(
                bool(row.get("identity_outlier")) for row in events
            ),
            "unassigned_event_count": sum(
                row["analysis_unit"] is None for row in event_rows
            ),
        },
        "units": units,
        "round_robin_candidate_sets": round_robin_sets,
        "events": event_rows,
        "effects": {
            "midi_notes_changed": 0,
            "midi_velocities_changed": 0,
            "sample_events_added": 0,
            "sample_events_removed": 0,
            "soundfont_zones_changed": 0,
            "drum_family_mapping_changed": False,
        },
        "warnings": [
            "Velocity layers are source-loudness groups, not proof that the original instrument used separately recorded dynamic samples.",
            "Round-robin candidates can contain bleed, room sound or phrase context. Listen before adding any event to a sample instrument.",
            "MIDI velocity can already be derived from source level, so layer evidence is not an independent accuracy score.",
        ],
    }


def source_event_dynamics_svg(report: dict[str, Any]) -> str:
    """Render source RMS, layer and alternate-sample evidence as SVG."""

    events = list(report.get("events", []))
    width, height = 1200, 500
    left, right, top, bottom = 80, 30, 65, 100
    plot_width = width - left - right
    plot_height = height - top - bottom
    maximum_time = max((float(row["start_seconds"]) for row in events), default=1.0)
    rms_values = [float(row["rms_db"]) for row in events] or [-60.0]
    low_db = math.floor(min(rms_values) / 5.0) * 5.0
    high_db = math.ceil(max(rms_values) / 5.0) * 5.0
    if high_db <= low_db:
        high_db = low_db + 5.0
    colors = {"L1": "#23c9ff", "L2": "#ffd166"}
    chunks = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#101820"/>',
        '<text x="80" y="30" fill="#ffffff" font-family="sans-serif" font-size="20">Source-event dynamics and alternate-sample review</text>',
        '<text x="80" y="51" fill="#b8c4ce" font-family="sans-serif" font-size="12">Y = source RMS dB; colour = candidate velocity layer; white ring = round-robin candidate; red = retained outlier</text>',
    ]
    for db in range(int(low_db), int(high_db) + 1, 5):
        y = top + (high_db - db) / (high_db - low_db) * plot_height
        chunks.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="#283845" stroke-width="1"/>'
        )
        chunks.append(
            f'<text x="{left - 12}" y="{y + 4:.1f}" text-anchor="end" fill="#9fb3c2" font-family="sans-serif" font-size="10">{db} dB</text>'
        )
    for row in events:
        x = left + float(row["start_seconds"]) / max(maximum_time, 1e-9) * plot_width
        y = top + (high_db - float(row["rms_db"])) / (high_db - low_db) * plot_height
        if row["identity_outlier"]:
            fill = "#ff5c5c"
        else:
            fill = colors.get(str(row.get("velocity_layer")), "#6c757d")
        stroke = "#ffffff" if row["round_robin_candidate"] else "#101820"
        stroke_width = 2.5 if row["round_robin_candidate"] else 0.8
        title = html.escape(
            f"Event {row['event_index']}; {row.get('analysis_unit') or 'unassigned'}; "
            f"{row.get('velocity_layer') or 'no layer'}; velocity {row['velocity']}"
        )
        chunks.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"><title>{title}</title></circle>'
        )
    summary = report.get("summary", {})
    chunks.extend(
        [
            f'<text x="{left}" y="{height - 54}" fill="#ffffff" font-family="sans-serif" font-size="12">{summary.get("velocity_layer_candidate_unit_count", 0)} two-layer units; {summary.get("round_robin_candidate_set_count", 0)} alternate-sample sets; {summary.get("round_robin_candidate_event_count", 0)} selected candidate events</text>',
            f'<text x="{left}" y="{height - 30}" fill="#b8c4ce" font-family="sans-serif" font-size="11">Advisory only: MIDI, sample selection, SoundFont zones and drum mappings are unchanged.</text>',
            "</svg>",
        ]
    )
    return "\n".join(chunks) + "\n"


def _velocity_layers(
    events: Sequence[dict[str, Any]],
) -> tuple[list[list[dict[str, Any]]], dict[str, Any] | None]:
    import numpy as np

    ordered = sorted(events, key=lambda row: (_rms_db(row), int(row["event_index"])))
    count = len(ordered)
    if count < MINIMUM_LAYER_EVENTS:
        return [list(events)], None
    minimum_count = max(
        MINIMUM_EVENTS_PER_LAYER,
        int(math.ceil(count * MINIMUM_LAYER_FRACTION)),
    )
    if count < minimum_count * 2:
        return [list(events)], None
    candidates = []
    for split_index in range(minimum_count, count - minimum_count + 1):
        low = ordered[:split_index]
        high = ordered[split_index:]
        low_median = float(np.median([_rms_db(row) for row in low]))
        high_median = float(np.median([_rms_db(row) for row in high]))
        median_gap = high_median - low_median
        adjacent_gap = _rms_db(high[0]) - _rms_db(low[-1])
        boundary = (_rms_db(low[-1]) + _rms_db(high[0])) / 2.0
        imbalance = abs(len(low) - len(high))
        candidates.append((adjacent_gap, imbalance, boundary, median_gap, low, high))
    _, _, boundary, median_gap, low, high = min(
        candidates,
        key=lambda item: (-item[0], item[1], item[2]),
    )
    if median_gap < MINIMUM_LAYER_RMS_GAP_DB:
        return [list(events)], None
    low = sorted(low, key=lambda row: int(row["event_index"]))
    high = sorted(high, key=lambda row: int(row["event_index"]))
    velocity_boundary = int(
        round(
            (
                float(np.median([int(row["velocity"]) for row in low]))
                + float(np.median([int(row["velocity"]) for row in high]))
            )
            / 2.0
        )
    )
    return [low, high], {
        "rms_boundary_db": _round(boundary, 3),
        "median_rms_gap_db": _round(median_gap, 3),
        "suggested_velocity_boundary": max(1, min(126, velocity_boundary)),
        "applied_automatically": False,
    }


def _round_robin_candidates(events: Sequence[dict[str, Any]]) -> dict[str, Any]:
    import numpy as np

    isolated = [row for row in events if bool(row.get("isolated"))]
    if len(isolated) < MINIMUM_ROUND_ROBIN_EVENTS:
        return {
            "status": "insufficient-isolated-events",
            "eligible_event_count": len(isolated),
            "candidate_event_indices": [],
            "candidate_note_indices": [],
            "timbre_distance_p50": None,
            "timbre_distance_p90": None,
        }
    vectors = np.asarray(
        [row["timbre_vector"][:17] for row in isolated], dtype=np.float64
    )
    scale = np.std(vectors, axis=0)
    scale = np.where(scale < 0.025, 0.025, scale)
    standardized = (vectors - np.median(vectors, axis=0)) / scale
    distance = np.sqrt(
        np.mean(
            (standardized[:, None, :] - standardized[None, :, :]) ** 2,
            axis=2,
        )
    )
    medoid = min(
        range(len(isolated)),
        key=lambda index: (
            float(np.sum(distance[index])),
            int(isolated[index]["event_index"]),
        ),
    )
    central_count = max(
        MINIMUM_ROUND_ROBIN_EVENTS,
        int(math.ceil(len(isolated) * 0.8)),
    )
    central = sorted(
        range(len(isolated)),
        key=lambda index: (
            distance[medoid, index],
            int(isolated[index]["event_index"]),
        ),
    )[:central_count]
    selected = [medoid]
    while len(selected) < min(MAXIMUM_ROUND_ROBIN_CANDIDATES, len(central)):
        remaining = [index for index in central if index not in selected]
        selected.append(
            max(
                remaining,
                key=lambda index: (
                    float(np.min(distance[index, selected])),
                    -int(isolated[index]["event_index"]),
                ),
            )
        )
    upper = distance[np.triu_indices(len(isolated), 1)]
    return {
        "status": "candidate-set",
        "eligible_event_count": len(isolated),
        "candidate_event_indices": [
            int(isolated[index]["event_index"]) for index in selected
        ],
        "candidate_note_indices": [
            int(isolated[index]["note_index"]) for index in selected
        ],
        "excluded_extreme_event_count": len(isolated) - len(central),
        "timbre_distance_p50": _round(float(np.percentile(upper, 50)), 6),
        "timbre_distance_p90": _round(float(np.percentile(upper, 90)), 6),
        "sample_selection_changed": False,
    }


def _rms_db(event: dict[str, Any]) -> float:
    return 20.0 * math.log10(max(float(event["rms"]), 1e-12))


def _round(value: float, digits: int) -> float:
    return round(value, digits) if math.isfinite(value) else 0.0


__all__ = [
    "SOURCE_EVENT_DYNAMICS_SCHEMA",
    "analyze_source_event_dynamics",
    "source_event_dynamics_svg",
]
