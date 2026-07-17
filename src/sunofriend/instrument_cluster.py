"""Deterministic advisory clustering for MIDI-aligned source events.

The report groups events by candidate timbre family and by articulation shape,
then marks unusually isolated timbres for review.  These labels are evidence,
not instrument recognition: v1 never removes a MIDI note, changes an existing
instrument ranking, or excludes a sample from a generated bank.
"""

from __future__ import annotations

import hashlib
import html
import math
from collections import Counter
from pathlib import Path
from typing import Any, Sequence


SOURCE_EVENT_CLUSTER_SCHEMA = "sunofriend.source-event-clusters.v1"
IDENTITY_FEATURE_COUNT = 17
EXPLAINABLE_IDENTITY_WEIGHT = 0.70
LEARNED_IDENTITY_WEIGHT = 0.30


def cluster_source_events(
    segments: Sequence[Any],
    timbre_vectors: Sequence[Sequence[float]],
    *,
    sample_rate: int,
    source_path: str | Path,
    midi_path: str | Path,
    feature_names: Sequence[str],
    embedding_model: Any | None = None,
    selected_note_indices: Sequence[int] = (),
) -> dict[str, Any]:
    """Create immutable advisory timbre, articulation and outlier evidence."""

    import numpy as np

    if len(segments) != len(timbre_vectors):
        raise ValueError("segments and timbre_vectors must have equal length")
    if not segments:
        raise ValueError("At least one source event is required for clustering")
    matrix = np.asarray(timbre_vectors, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1] < 20:
        raise ValueError("Each source event must have at least 20 timbre features")
    if len(feature_names) != matrix.shape[1]:
        raise ValueError("feature_names must describe every timbre-vector value")
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")

    explainable_distance = _normalized_feature_distance(
        matrix[:, :IDENTITY_FEATURE_COUNT]
    )
    learned_embeddings = None
    learned_distance = None
    if embedding_model is not None:
        learned_embeddings = np.asarray(
            [
                _pooled_embedding(
                    embedding_model.fingerprint(segment.samples, sample_rate)
                )
                for segment in segments
            ],
            dtype=np.float64,
        )
        learned_distance = _normalized_cosine_distance(learned_embeddings)
        identity_distance = (
            EXPLAINABLE_IDENTITY_WEIGHT * explainable_distance
            + LEARNED_IDENTITY_WEIGHT * learned_distance
        )
    else:
        identity_distance = explainable_distance

    outliers, outlier_threshold, nearest_distances = _identity_outliers(
        identity_distance
    )
    retained = [index for index in range(len(segments)) if index not in outliers]
    if retained:
        retained_distance = identity_distance[np.ix_(retained, retained)]
        retained_labels, retained_medoids, identity_silhouette = _choose_clusters(
            retained_distance,
            maximum_clusters=4,
            minimum_silhouette=0.18,
        )
    else:
        retained_labels, retained_medoids, identity_silhouette = [], [], 0.0
    identity_labels: list[int | None] = [None] * len(segments)
    identity_medoids: dict[int, int] = {}
    for local_index, label in enumerate(retained_labels):
        identity_labels[retained[local_index]] = label
    for label, local_medoid in enumerate(retained_medoids):
        identity_medoids[label] = retained[local_medoid]
    identity_labels, identity_medoids = _canonicalize_labels(
        identity_labels, identity_medoids, segments
    )

    articulation_matrix = np.asarray(
        [
            [
                math.log1p(_duration(segment)),
                float(vector[17]),
                float(vector[18]),
                float(vector[19]),
                math.log1p(max(float(segment.rms), 0.0)),
                float(segment.velocity) / 127.0,
            ]
            for segment, vector in zip(segments, matrix)
        ],
        dtype=np.float64,
    )
    articulation_distance = _normalized_feature_distance(articulation_matrix)
    articulation_labels, articulation_medoids, articulation_silhouette = (
        _choose_clusters(
            articulation_distance,
            maximum_clusters=3,
            minimum_silhouette=0.20,
        )
    )
    articulation_labels_optional: list[int | None] = [
        int(value) for value in articulation_labels
    ]
    articulation_medoid_map = {
        label: medoid for label, medoid in enumerate(articulation_medoids)
    }
    articulation_labels_optional, articulation_medoid_map = _canonicalize_labels(
        articulation_labels_optional, articulation_medoid_map, segments
    )
    articulation_labels = [int(value) for value in articulation_labels_optional]

    selected = {int(value) for value in selected_note_indices}
    event_rows = []
    for index, (segment, vector) in enumerate(zip(segments, matrix)):
        identity_label = identity_labels[index]
        identity_medoid = (
            identity_medoids[int(identity_label)]
            if identity_label is not None
            else None
        )
        articulation_label = articulation_labels[index]
        articulation_medoid = articulation_medoid_map[articulation_label]
        event_rows.append(
            {
                "event_index": index,
                "note_index": int(segment.note_index),
                "start_seconds": _round(float(segment.start_seconds), 6),
                "end_seconds": _round(float(segment.end_seconds), 6),
                "duration_seconds": _round(_duration(segment), 6),
                "pitch": int(segment.pitch),
                "velocity": int(segment.velocity),
                "rms": _round(float(segment.rms), 8),
                "isolated": bool(segment.isolated),
                "overlap_count": int(segment.overlap_count),
                "selected_for_sample_pack": int(segment.note_index) in selected,
                "identity_candidate_cluster": (
                    f"I{int(identity_label) + 1}"
                    if identity_label is not None
                    else None
                ),
                "identity_medoid_event_index": identity_medoid,
                "identity_distance_to_medoid": (
                    _round(float(identity_distance[index, identity_medoid]), 6)
                    if identity_medoid is not None
                    else None
                ),
                "nearest_identity_event_distance": _round(
                    float(nearest_distances[index]), 6
                )
                if math.isfinite(float(nearest_distances[index]))
                else None,
                "identity_outlier": index in outliers,
                "outlier_reason": (
                    "Nearest-event timbre distance exceeds the robust review threshold; "
                    "this can be a rare valid articulation, bleed or an artefact."
                    if index in outliers
                    else None
                ),
                "articulation_cluster": f"A{articulation_label + 1}",
                "articulation_medoid_event_index": articulation_medoid,
                "articulation_descriptor": _articulation_descriptor(segment, vector),
                "timbre_vector": [_round(float(value), 8) for value in vector.tolist()],
            }
        )

    identity_clusters = _identity_cluster_summaries(
        event_rows, identity_medoids, segments
    )
    articulation_clusters = _articulation_cluster_summaries(
        event_rows, articulation_medoid_map
    )
    source = Path(source_path).expanduser()
    midi = Path(midi_path).expanduser()
    report: dict[str, Any] = {
        "schema": SOURCE_EVENT_CLUSTER_SCHEMA,
        "operation": "source-event-cluster",
        "status": "complete",
        "advisory_only": True,
        "effects": {
            "midi_notes_changed": 0,
            "instrument_ranking_changed": False,
            "sample_events_removed": 0,
            "automatic_outlier_rejection": False,
        },
        "source": {
            "path": str(source.resolve()),
            "sha256": _sha256(source),
            "sample_rate": int(sample_rate),
        },
        "midi": {"path": str(midi.resolve()), "sha256": _sha256(midi)},
        "method": {
            "feature_order": [str(value) for value in feature_names],
            "identity_features": [
                str(value) for value in feature_names[:IDENTITY_FEATURE_COUNT]
            ],
            "identity_distance": (
                "robust-scaled explainable timbre distance"
                if embedding_model is None
                else "70% robust-scaled explainable timbre distance plus 30% "
                "OpenL3 cosine distance"
            ),
            "identity_clustering": (
                "deterministic k-medoids; one to four clusters; smallest model "
                "within 0.025 silhouette of the best; minimum accepted silhouette 0.18"
            ),
            "outlier_policy": (
                "review-only nearest-neighbour threshold: maximum of 0.75, p90, "
                "and median plus three scaled MAD; disabled below five events"
            ),
            "articulation_features": [
                "log_duration",
                "peak_timing_ratio",
                "tail_level_ratio",
                "crest_log",
                "log_rms",
                "midi_velocity",
            ],
            "articulation_clustering": (
                "independent deterministic k-medoids; one to three clusters; "
                "minimum accepted silhouette 0.20"
            ),
            "learned_embedding": (
                {
                    "model": embedding_model.model_record(),
                    "weight": LEARNED_IDENTITY_WEIGHT,
                    "raw_event_embeddings_stored": False,
                }
                if embedding_model is not None
                else None
            ),
        },
        "summary": {
            "source_event_count": len(event_rows),
            "identity_candidate_cluster_count": len(identity_clusters),
            "articulation_cluster_count": len(articulation_clusters),
            "identity_outlier_count": len(outliers),
            "identity_silhouette": _round(identity_silhouette, 6),
            "articulation_silhouette": _round(articulation_silhouette, 6),
            "outlier_review_threshold": (
                _round(outlier_threshold, 6)
                if math.isfinite(outlier_threshold)
                else None
            ),
            "selected_sample_event_count": sum(
                bool(row["selected_for_sample_pack"]) for row in event_rows
            ),
        },
        "identity_candidate_clusters": identity_clusters,
        "articulation_clusters": articulation_clusters,
        "events": event_rows,
        "warnings": [
            "A candidate timbre family is not proof of a physical instrument; pitch, effects, bleed and separator artefacts can create clusters.",
            "An outlier is retained and may be a musically important rare articulation. Review it by ear before excluding any sample.",
        ],
    }
    if learned_embeddings is not None and learned_distance is not None:
        report["summary"]["learned_event_embedding_count"] = len(learned_embeddings)
    return report


def source_event_clusters_svg(report: dict[str, Any]) -> str:
    """Render a compact pitch/timeline view of event-cluster evidence."""

    events = list(report.get("events", []))
    width, height = 1200, 480
    left, right, top, bottom = 80, 30, 60, 120
    plot_width = width - left - right
    plot_height = height - top - bottom
    maximum_time = max((float(row["end_seconds"]) for row in events), default=1.0)
    pitches = [int(row["pitch"]) for row in events] or [60]
    low_pitch, high_pitch = min(pitches), max(pitches)
    pitch_span = max(1, high_pitch - low_pitch)
    colors = ("#23c9ff", "#ffd166", "#8ce99a", "#c77dff", "#ff9f1c")
    chunks = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#101820"/>',
        '<text x="80" y="30" fill="#ffffff" font-family="sans-serif" font-size="20">Source-event timbre and articulation review</text>',
        '<text x="80" y="50" fill="#b8c4ce" font-family="sans-serif" font-size="12">Colour = candidate timbre family; label = articulation group; red = retained outlier</text>',
    ]
    for pitch in range(low_pitch, high_pitch + 1):
        y = top + (high_pitch - pitch) / pitch_span * plot_height
        chunks.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="#283845" stroke-width="1"/>'
        )
        chunks.append(
            f'<text x="{left - 12}" y="{y + 4:.1f}" text-anchor="end" fill="#9fb3c2" font-family="sans-serif" font-size="10">{pitch}</text>'
        )
    for row in events:
        x = left + float(row["start_seconds"]) / maximum_time * plot_width
        event_width = max(
            3.0,
            float(row["duration_seconds"]) / maximum_time * plot_width,
        )
        y = top + (high_pitch - int(row["pitch"])) / pitch_span * plot_height - 7
        cluster = row.get("identity_candidate_cluster")
        if row.get("identity_outlier"):
            fill = "#ff5c5c"
        elif cluster:
            fill = colors[(int(str(cluster)[1:]) - 1) % len(colors)]
        else:
            fill = "#6c757d"
        title = html.escape(
            f"Event {row['event_index']}: {cluster or 'outlier'}, "
            f"{row['articulation_cluster']}, {row['articulation_descriptor']}"
        )
        chunks.extend(
            [
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{event_width:.1f}" height="14" rx="3" fill="{fill}" stroke="#ffffff" stroke-width="0.6"><title>{title}</title></rect>',
                f'<text x="{x + event_width / 2:.1f}" y="{y + 11:.1f}" text-anchor="middle" fill="#101820" font-family="sans-serif" font-size="8">{html.escape(str(row["articulation_cluster"]))}</text>',
            ]
        )
    legend_y = height - 82
    for index, cluster in enumerate(report.get("identity_candidate_clusters", [])):
        x = left + index * 210
        fill = colors[index % len(colors)]
        chunks.append(
            f'<rect x="{x}" y="{legend_y}" width="14" height="14" fill="{fill}"/>'
        )
        chunks.append(
            f'<text x="{x + 20}" y="{legend_y + 12}" fill="#ffffff" font-family="sans-serif" font-size="12">{html.escape(str(cluster["cluster_id"]))}: {cluster["event_count"]} events</text>'
        )
    chunks.append(
        f'<text x="{left}" y="{height - 28}" fill="#b8c4ce" font-family="sans-serif" font-size="11">Advisory only: no MIDI note, instrument rank or sample selection was changed.</text>'
    )
    chunks.append("</svg>")
    return "\n".join(chunks) + "\n"


def _normalized_feature_distance(matrix: Any) -> Any:
    import numpy as np

    values = np.asarray(matrix, dtype=np.float64)
    count = len(values)
    if count <= 1:
        return np.zeros((count, count), dtype=np.float64)
    median = np.median(values, axis=0)
    mad = np.median(np.abs(values - median), axis=0) * 1.4826
    standard_deviation = np.std(values, axis=0)
    scale = np.maximum.reduce(
        [mad, standard_deviation * 0.25, np.full(values.shape[1], 0.025)]
    )
    standardized = (values - median) / scale
    distance = np.sqrt(
        np.mean(
            (standardized[:, None, :] - standardized[None, :, :]) ** 2,
            axis=2,
        )
    )
    return _normalize_distance_matrix(distance)


def _normalized_cosine_distance(matrix: Any) -> Any:
    import numpy as np

    values = np.asarray(matrix, dtype=np.float64)
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    values = values / np.maximum(norms, 1e-12)
    distance = np.clip(1.0 - values @ values.T, 0.0, 2.0)
    return _normalize_distance_matrix(distance)


def _normalize_distance_matrix(distance: Any) -> Any:
    import numpy as np

    values = np.asarray(distance, dtype=np.float64)
    if len(values) <= 1:
        return values
    upper = values[np.triu_indices(len(values), 1)]
    positive = upper[upper > 1e-12]
    scale = float(np.median(positive)) if len(positive) else 1.0
    values = values / max(scale, 1e-12)
    np.fill_diagonal(values, 0.0)
    return values


def _identity_outliers(distance: Any) -> tuple[set[int], float, Any]:
    import numpy as np

    count = len(distance)
    if count <= 1:
        return set(), float("inf"), np.full(count, np.inf, dtype=np.float64)
    masked = np.asarray(distance, dtype=np.float64).copy()
    np.fill_diagonal(masked, np.inf)
    nearest = np.min(masked, axis=1)
    if count < 5:
        return set(), float("inf"), nearest
    median = float(np.median(nearest))
    mad = float(np.median(np.abs(nearest - median)) * 1.4826)
    percentile_90 = float(np.percentile(nearest, 90))
    threshold = max(0.75, percentile_90, median + 3.0 * mad)
    return (
        {index for index, value in enumerate(nearest) if float(value) > threshold},
        threshold,
        nearest,
    )


def _choose_clusters(
    distance: Any,
    *,
    maximum_clusters: int,
    minimum_silhouette: float,
) -> tuple[list[int], list[int], float]:
    count = len(distance)
    if count <= 1:
        return [0] * count, ([0] if count else []), 0.0
    candidates = []
    for clusters in range(2, min(maximum_clusters, count // 2) + 1):
        labels, medoids = _kmedoids(distance, clusters)
        sizes = Counter(labels)
        if min(sizes.values()) < 2:
            continue
        score = _silhouette(distance, labels)
        candidates.append((score, clusters, labels, medoids))
    if not candidates:
        medoid = _single_medoid(distance)
        return [0] * count, [medoid], 0.0
    best_score = max(item[0] for item in candidates)
    if best_score < minimum_silhouette:
        medoid = _single_medoid(distance)
        return [0] * count, [medoid], 0.0
    acceptable = [item for item in candidates if item[0] >= best_score - 0.025]
    score, _, labels, medoids = min(acceptable, key=lambda item: item[1])
    return labels, medoids, float(score)


def _kmedoids(distance: Any, clusters: int) -> tuple[list[int], list[int]]:
    import numpy as np

    count = len(distance)
    medoids = [_single_medoid(distance)]
    while len(medoids) < clusters:
        remaining = [index for index in range(count) if index not in medoids]
        next_medoid = max(
            remaining,
            key=lambda index: (
                float(np.min(distance[index, medoids])),
                -index,
            ),
        )
        medoids.append(next_medoid)
    for _ in range(50):
        labels = _assign(distance, medoids)
        updated = []
        for label in range(clusters):
            members = [index for index, value in enumerate(labels) if value == label]
            if not members:
                updated.append(medoids[label])
                continue
            updated.append(
                min(
                    members,
                    key=lambda index: (
                        float(np.sum(distance[index, members])),
                        index,
                    ),
                )
            )
        if updated == medoids:
            break
        medoids = updated
    labels = _assign(distance, medoids)
    return labels, medoids


def _assign(distance: Any, medoids: Sequence[int]) -> list[int]:
    return [
        min(
            range(len(medoids)),
            key=lambda label: (float(distance[index, medoids[label]]), label),
        )
        for index in range(len(distance))
    ]


def _single_medoid(distance: Any) -> int:
    import numpy as np

    if not len(distance):
        return 0
    return min(
        range(len(distance)),
        key=lambda index: (float(np.sum(distance[index])), index),
    )


def _silhouette(distance: Any, labels: Sequence[int]) -> float:
    import numpy as np

    unique = sorted(set(labels))
    if len(unique) <= 1:
        return 0.0
    values = []
    for index, label in enumerate(labels):
        own = [other for other, value in enumerate(labels) if value == label]
        if len(own) <= 1:
            values.append(0.0)
            continue
        own_without = [other for other in own if other != index]
        within = float(np.mean(distance[index, own_without]))
        between = min(
            float(
                np.mean(
                    distance[
                        index,
                        [
                            other
                            for other, value in enumerate(labels)
                            if value == other_label
                        ],
                    ]
                )
            )
            for other_label in unique
            if other_label != label
        )
        denominator = max(within, between)
        values.append((between - within) / denominator if denominator else 0.0)
    return float(np.mean(values))


def _canonicalize_labels(
    labels: Sequence[int | None],
    medoids: dict[int, int],
    segments: Sequence[Any],
) -> tuple[list[int | None], dict[int, int]]:
    ordered = sorted(
        medoids,
        key=lambda label: (
            min(
                float(segments[index].start_seconds)
                for index, value in enumerate(labels)
                if value == label
            ),
            medoids[label],
        ),
    )
    mapping = {old: new for new, old in enumerate(ordered)}
    canonical_labels = [
        (mapping[int(value)] if value is not None else None) for value in labels
    ]
    canonical_medoids = {mapping[old]: medoids[old] for old in ordered}
    return canonical_labels, canonical_medoids


def _identity_cluster_summaries(
    events: Sequence[dict[str, Any]],
    medoids: dict[int, int],
    segments: Sequence[Any],
) -> list[dict[str, Any]]:
    import numpy as np

    rows = []
    for label in sorted(medoids):
        cluster_id = f"I{label + 1}"
        members = [
            row for row in events if row["identity_candidate_cluster"] == cluster_id
        ]
        rows.append(
            {
                "cluster_id": cluster_id,
                "event_count": len(members),
                "event_indices": [int(row["event_index"]) for row in members],
                "medoid_event_index": medoids[label],
                "first_start_seconds": min(
                    float(row["start_seconds"]) for row in members
                ),
                "pitch_range": [
                    min(int(row["pitch"]) for row in members),
                    max(int(row["pitch"]) for row in members),
                ],
                "median_duration_seconds": _round(
                    float(np.median([row["duration_seconds"] for row in members])), 6
                ),
                "median_rms": _round(
                    float(np.median([row["rms"] for row in members])), 8
                ),
                "articulation_counts": dict(
                    sorted(
                        Counter(row["articulation_cluster"] for row in members).items()
                    )
                ),
                "medoid_descriptor": _articulation_descriptor(
                    segments[medoids[label]],
                    events[medoids[label]]["timbre_vector"],
                ),
            }
        )
    return rows


def _articulation_cluster_summaries(
    events: Sequence[dict[str, Any]], medoids: dict[int, int]
) -> list[dict[str, Any]]:
    import numpy as np

    rows = []
    for label in sorted(medoids):
        cluster_id = f"A{label + 1}"
        members = [row for row in events if row["articulation_cluster"] == cluster_id]
        rows.append(
            {
                "cluster_id": cluster_id,
                "event_count": len(members),
                "event_indices": [int(row["event_index"]) for row in members],
                "medoid_event_index": medoids[label],
                "medoid_descriptor": events[medoids[label]]["articulation_descriptor"],
                "descriptor_counts": dict(
                    sorted(
                        Counter(
                            row["articulation_descriptor"] for row in members
                        ).items()
                    )
                ),
                "median_duration_seconds": _round(
                    float(np.median([row["duration_seconds"] for row in members])), 6
                ),
            }
        )
    return rows


def _pooled_embedding(fingerprint: Any) -> Any:
    import numpy as np

    embeddings = np.asarray(fingerprint.embeddings, dtype=np.float64)
    rms = np.asarray(fingerprint.rms, dtype=np.float64)
    if not len(embeddings):
        raise ValueError("OpenL3 event fingerprint contains no windows")
    weights = np.maximum(rms[: len(embeddings)], 1e-12)
    pooled = np.average(embeddings, axis=0, weights=weights)
    return pooled / max(float(np.linalg.norm(pooled)), 1e-12)


def _articulation_descriptor(segment: Any, vector: Sequence[float]) -> str:
    duration = _duration(segment)
    duration_label = (
        "transient"
        if duration < 0.18
        else "short"
        if duration < 0.45
        else "medium"
        if duration < 1.20
        else "sustained"
    )
    peak = float(vector[17])
    peak_label = (
        "early-peak" if peak <= 0.25 else "mid-peak" if peak <= 0.70 else "late-peak"
    )
    tail = float(vector[18])
    tail_label = (
        "decaying-tail"
        if tail < 0.20
        else "shaped-tail"
        if tail < 0.55
        else "sustained-tail"
    )
    return f"{duration_label}/{peak_label}/{tail_label}"


def _duration(segment: Any) -> float:
    return max(0.0, float(segment.end_seconds) - float(segment.start_seconds))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _round(value: float, digits: int) -> float:
    return round(value, digits) if math.isfinite(value) else 0.0


__all__ = [
    "SOURCE_EVENT_CLUSTER_SCHEMA",
    "cluster_source_events",
    "source_event_clusters_svg",
]
