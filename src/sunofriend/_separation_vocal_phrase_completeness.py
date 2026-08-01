"""Inactive phrase-time completeness evidence for vocal MIDI hypotheses."""

from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from ._separation_authorised_midi_comparison import (
    AUTHORISED_MIDI_COMPARISON_SCHEMA,
    _artifact_path,
    _document_sha256,
    _make_private_tree,
    _regular_json,
    _sha256,
    _verify_artifacts,
    _write_json,
)
from ._separation_authorised_role_mapping import _safe_token
from ._separation_authorised_vocal_leaves import (
    SCHEMA as VOCAL_LEAF_SCHEMA,
    _require_private_inactive,
)
from ._separation_demucs_refinement_evaluation import _validated_notes
from ._separation_melroformer_midi_evaluation import (
    SCHEMA as MELROFORMER_MIDI_SCHEMA,
    _load_control_notes,
    _validated_control_policy,
)
from .models import NoteEvent


SCHEMA = "sunofriend.private-vocal-phrase-completeness.v1"
_REPORT_NAME = "vocal-phrase-completeness.json"
_REGISTER_HYPOTHESES = (
    "dominant_line",
    "harmony_stack",
    "lowest_line",
    "top_line",
)
_MINIMUM_PROVIDER_SUPPORT = 2
_PHRASE_GAP_SECONDS = 0.350
_MINIMUM_MISSING_SPAN_SECONDS = 0.040
_ROUND_DIGITS = 6


def _evaluate_vocal_phrase_completeness(
    control_comparison_path: str | Path,
    melroformer_evaluation_path: str | Path,
    vocal_leaf_evaluation_path: str | Path,
    *,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Measure candidate time coverage against distinct provider-group activity."""

    inputs = _load_inputs(
        control_comparison_path,
        melroformer_evaluation_path,
        vocal_leaf_evaluation_path,
    )
    document = _build_document(inputs)
    _reverify_inputs(inputs)

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(
            f"Vocal phrase-completeness output already exists: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.building-", dir=destination.parent)
    )
    temporary.chmod(0o700)
    try:
        document["document_sha256"] = _document_sha256(document)
        _write_json(temporary / _REPORT_NAME, document)
        _make_private_tree(temporary)
        if os.path.lexists(destination):
            raise FileExistsError(
                "Vocal phrase-completeness output appeared during publication"
            )
        os.rename(temporary, destination)
        document["report"] = str(destination / _REPORT_NAME)
        return document
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _build_document(inputs: Mapping[str, Any]) -> dict[str, Any]:
    duration = float(inputs["duration_seconds"])
    provider_groups = {
        provider_id: _notes_to_intervals(notes, duration)
        for provider_id, notes in inputs["provider_group_notes"].items()
    }
    if len(provider_groups) < _MINIMUM_PROVIDER_SUPPORT:
        raise ValueError("at least two distinct provider groups are required")
    support_segments = _provider_support_segments(
        provider_groups,
        minimum_support=_MINIMUM_PROVIDER_SUPPORT,
    )
    consensus = _merge_intervals(
        tuple((item["start"], item["end"]) for item in support_segments)
    )
    consensus_seconds = _interval_duration(consensus)
    phrases = _phrase_intervals(consensus, gap_seconds=_PHRASE_GAP_SECONDS)

    target_intervals = {
        candidate_id: _notes_to_intervals(notes, duration)
        for candidate_id, notes in inputs["target_notes"].items()
    }
    candidates = {
        candidate_id: _candidate_observation(
            intervals,
            consensus=consensus,
            phrases=phrases,
            note_count=len(inputs["target_notes"][candidate_id]),
        )
        for candidate_id, intervals in sorted(target_intervals.items())
    }
    primary = target_intervals["primary"]
    lowest = target_intervals["lowest_line"]
    contrast = _candidate_contrast(primary, lowest, consensus)

    provider_observations = {}
    for provider_id, intervals in sorted(provider_groups.items()):
        provider_observations[provider_id] = {
            "broad_note_count": len(inputs["controls"][provider_id]),
            "leaf_primary_candidate_count": len(
                inputs["leaf_primary_notes"].get(provider_id, {})
            ),
            "union_active_seconds": _round(_interval_duration(intervals)),
            "one_vote_maximum": True,
        }

    return {
        "schema": SCHEMA,
        "status": "complete_observation_not_acceptance",
        "evidence_scope": "private_development_only",
        "inputs": {
            "control_comparison_sha256": inputs["control_sha256"],
            "control_comparison_document_sha256": inputs["control"][
                "document_sha256"
            ],
            "melroformer_evaluation_sha256": inputs["melroformer_sha256"],
            "melroformer_evaluation_document_sha256": inputs["melroformer"][
                "document_sha256"
            ],
            "vocal_leaf_evaluation_sha256": inputs["leaf_sha256"],
            "vocal_leaf_evaluation_document_sha256": inputs["leaf"][
                "document_sha256"
            ],
        },
        "policy": {
            "duration_seconds": _round(duration),
            "bpm": inputs["bpm"],
            "tuning_hz": inputs["tuning_hz"],
            "minimum_distinct_provider_group_support": (
                _MINIMUM_PROVIDER_SUPPORT
            ),
            "provider_vote_capped_at_one": True,
            "provider_group_activity": (
                "union of the broad vocal primary and every separate leaf "
                "primary from that provider"
            ),
            "phrase_gap_seconds": _PHRASE_GAP_SECONDS,
            "minimum_reported_missing_span_seconds": (
                _MINIMUM_MISSING_SPAN_SECONDS
            ),
            "pitch_correctness_evaluated": False,
            "singer_identity_inferred": False,
            "score_truth_claimed": False,
            "candidate_ranked_or_selected": False,
        },
        "provider_groups": provider_observations,
        "provider_consensus": {
            "active_seconds": _round(consensus_seconds),
            "interval_count": len(consensus),
            "phrase_count": len(phrases),
            "intervals": _serialise_intervals(consensus),
            "support_segments": _serialise_support_segments(support_segments),
        },
        "candidates": candidates,
        "primary_vs_lowest": contrast,
        "phrases": _phrase_observations(
            phrases,
            consensus=consensus,
            target_intervals=target_intervals,
            provider_groups=provider_groups,
        ),
        "observations": {
            "lowest_adds_consensus_activity_missing_from_primary": (
                contrast["lowest_only_consensus_seconds"] > 0.0
            ),
            "primary_and_lowest_together_leave_consensus_gaps": (
                contrast["neither_candidate_consensus_seconds"] > 0.0
            ),
            "coverage_is_activity_only_not_melody_accuracy": True,
            "automatic_acceptance": False,
        },
        "permissions": {
            "accepted": False,
            "automatic_promotion": False,
            "automatic_selection": False,
            "production_eligible": False,
            "public_result": False,
            "simple_mode_available": False,
            "source_graph_activation": False,
            "studio_import_available": False,
        },
        "effects": {
            "audio_created": False,
            "midi_created": False,
            "review_created": False,
            "source_audio_mutated": False,
            "source_graph_mutated": False,
        },
        "limitations": [
            "Agreement between estimated provider MIDI is not a score or clean-vocal ground truth.",
            "Activity coverage does not test pitch, octave, singer identity, expression or musical usefulness.",
            "Provider leaves from one pack share a single vote so extra leaves cannot inflate support.",
            "Distinct provider groups are not claimed to be statistically independent.",
            "A provider group is a union; one noisy leaf can extend that provider's activity.",
            "No missing span is filled and no candidate is merged, repaired, ranked or selected.",
        ],
        "next": {
            "human_listening_required_before_any_merge": True,
            "focused_review_created": False,
            "automatic_merge_allowed": False,
            "cross_song_repetition_required": True,
        },
    }


def _load_inputs(
    control_comparison_path: str | Path,
    melroformer_evaluation_path: str | Path,
    vocal_leaf_evaluation_path: str | Path,
) -> dict[str, Any]:
    control_path = _regular_json(control_comparison_path, "control comparison")
    control_root = control_path.parent
    control_sha256 = _sha256(control_path)
    control = json.loads(control_path.read_text(encoding="utf-8"))
    if (
        control.get("schema") != AUTHORISED_MIDI_COMPARISON_SCHEMA
        or control.get("document_sha256") != _document_sha256(control)
    ):
        raise ValueError("authorised MIDI controls differ")
    _require_private_inactive(control, "authorised MIDI controls")
    _verify_artifacts(control_root, control.get("artifacts"))
    bpm, tuning_hz = _validated_control_policy(control.get("policy"))
    controls = _load_control_notes(control_root, control)

    melroformer_path = _regular_json(
        melroformer_evaluation_path, "MelRoFormer MIDI evaluation"
    )
    melroformer_root = melroformer_path.parent
    melroformer_sha256 = _sha256(melroformer_path)
    melroformer = json.loads(melroformer_path.read_text(encoding="utf-8"))
    if (
        melroformer.get("schema") != MELROFORMER_MIDI_SCHEMA
        or melroformer.get("document_sha256") != _document_sha256(melroformer)
        or melroformer.get("controls", {}).get("comparison_sha256")
        != control_sha256
        or melroformer.get("controls", {}).get("document_sha256")
        != control.get("document_sha256")
    ):
        raise ValueError("MelRoFormer MIDI evaluation differs")
    _require_private_inactive(melroformer, "MelRoFormer MIDI evaluation")
    _verify_artifacts(melroformer_root, melroformer.get("artifacts"))
    if (
        float(melroformer.get("policy", {}).get("bpm", -1.0)) != bpm
        or float(melroformer.get("policy", {}).get("tuning_hz", -1.0))
        != tuning_hz
    ):
        raise ValueError("MelRoFormer MIDI policy differs")
    duration = _validated_duration(melroformer)
    target_notes = _load_target_notes(melroformer_root, melroformer)

    leaf_path = _regular_json(vocal_leaf_evaluation_path, "vocal leaf evaluation")
    leaf_root = leaf_path.parent
    leaf_sha256 = _sha256(leaf_path)
    leaf = json.loads(leaf_path.read_text(encoding="utf-8"))
    if (
        leaf.get("schema") != VOCAL_LEAF_SCHEMA
        or leaf.get("document_sha256") != _document_sha256(leaf)
        or leaf.get("inputs", {}).get("control_comparison_sha256")
        != control_sha256
        or leaf.get("inputs", {}).get("control_comparison_document_sha256")
        != control.get("document_sha256")
        or leaf.get("inputs", {}).get("melroformer_evaluation_sha256")
        != melroformer_sha256
        or leaf.get("inputs", {}).get("melroformer_evaluation_document_sha256")
        != melroformer.get("document_sha256")
    ):
        raise ValueError("vocal leaf evaluation differs")
    _require_private_inactive(leaf, "vocal leaf evaluation")
    _verify_artifacts(leaf_root, leaf.get("artifacts"))
    if (
        float(leaf.get("policy", {}).get("bpm", -1.0)) != bpm
        or float(leaf.get("policy", {}).get("tuning_hz", -1.0)) != tuning_hz
    ):
        raise ValueError("vocal leaf evaluation policy differs")
    leaf_primary_notes = _load_leaf_primary_notes(leaf_root, leaf, controls)
    provider_group_notes = {
        provider_id: tuple(controls[provider_id])
        + tuple(
            note
            for candidate_notes in leaf_primary_notes.get(provider_id, {}).values()
            for note in candidate_notes
        )
        for provider_id in controls
    }
    return {
        "control_path": control_path,
        "control_root": control_root,
        "control_sha256": control_sha256,
        "control": control,
        "melroformer_path": melroformer_path,
        "melroformer_root": melroformer_root,
        "melroformer_sha256": melroformer_sha256,
        "melroformer": melroformer,
        "leaf_path": leaf_path,
        "leaf_root": leaf_root,
        "leaf_sha256": leaf_sha256,
        "leaf": leaf,
        "bpm": bpm,
        "tuning_hz": tuning_hz,
        "duration_seconds": duration,
        "controls": controls,
        "leaf_primary_notes": leaf_primary_notes,
        "provider_group_notes": provider_group_notes,
        "target_notes": target_notes,
    }


def _validated_duration(document: Mapping[str, Any]) -> float:
    raw = (
        document.get("candidate", {})
        .get("method", {})
        .get("diagnostics", {})
        .get("duration_seconds")
    )
    if (
        isinstance(raw, bool)
        or not isinstance(raw, (int, float))
        or not math.isfinite(float(raw))
        or not 0.0 < float(raw) <= 15.1
    ):
        raise ValueError("MelRoFormer excerpt duration differs")
    return float(raw)


def _load_target_notes(
    root: Path, document: Mapping[str, Any]
) -> dict[str, tuple[NoteEvent, ...]]:
    candidate = document.get("candidate")
    if not isinstance(candidate, Mapping):
        raise ValueError("MelRoFormer target candidates are missing")
    primary = candidate.get("primary")
    if not isinstance(primary, Mapping):
        raise ValueError("MelRoFormer primary candidate is missing")
    result = {
        "primary": _load_note_claim(
            root,
            primary.get("notes"),
            expected_candidate="primary",
            expected_note_count=primary.get("note_count"),
        )
    }
    variants = candidate.get("register_hypotheses", {}).get("variants")
    if not isinstance(variants, Mapping) or set(variants) != set(
        _REGISTER_HYPOTHESES
    ):
        raise ValueError("MelRoFormer register hypotheses differ")
    for variant in _REGISTER_HYPOTHESES:
        payload = variants[variant]
        if not isinstance(payload, Mapping) or not isinstance(
            payload.get("candidate"), Mapping
        ):
            raise ValueError("MelRoFormer register hypothesis differs")
        persisted = payload["candidate"]
        result[variant] = _load_note_claim(
            root,
            persisted.get("notes"),
            expected_candidate=f"hypothesis-{variant}",
            expected_note_count=persisted.get("note_count"),
        )
    return result


def _load_leaf_primary_notes(
    root: Path,
    document: Mapping[str, Any],
    controls: Mapping[str, tuple[NoteEvent, ...]],
) -> dict[str, dict[str, tuple[NoteEvent, ...]]]:
    leaves = document.get("leaves")
    if not isinstance(leaves, Mapping) or not set(leaves).issubset(controls):
        raise ValueError("vocal leaf provider groups differ")
    result: dict[str, dict[str, tuple[NoteEvent, ...]]] = {}
    for provider_id, provider_leaves in sorted(leaves.items()):
        if not isinstance(provider_leaves, Mapping):
            raise ValueError("vocal leaf provider evidence differs")
        result[provider_id] = {}
        for leaf_id, leaf in sorted(provider_leaves.items()):
            adapters = leaf.get("adapters") if isinstance(leaf, Mapping) else None
            if not isinstance(adapters, Mapping) or set(adapters) != {
                "backing",
                "lead",
            }:
                raise ValueError("vocal leaf adapter evidence differs")
            for adapter_id, adapter in sorted(adapters.items()):
                if not isinstance(adapter, Mapping):
                    raise ValueError("vocal leaf adapter evidence differs")
                primary_variant = adapter.get("primary_variant")
                variants = adapter.get("variants")
                if (
                    not isinstance(primary_variant, str)
                    or not isinstance(variants, Mapping)
                    or not isinstance(variants.get(primary_variant), Mapping)
                ):
                    raise ValueError("vocal leaf primary evidence differs")
                candidate = variants[primary_variant].get("candidate")
                if not isinstance(candidate, Mapping):
                    raise ValueError("vocal leaf primary evidence differs")
                candidate_id = f"{leaf_id}/{adapter_id}/{primary_variant}"
                result[provider_id][candidate_id] = _load_note_claim(
                    root,
                    candidate.get("notes"),
                    expected_candidate=_safe_token(primary_variant),
                    expected_note_count=adapter.get("primary_note_count"),
                )
    return result


def _load_note_claim(
    root: Path,
    claim: Any,
    *,
    expected_candidate: str,
    expected_note_count: Any,
) -> tuple[NoteEvent, ...]:
    path = _artifact_path(root, claim, f"{expected_candidate} vocal note evidence")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("schema")
        != "sunofriend.private-authorised-midi-note-evidence.v1"
        or payload.get("role") != "vocals"
        or payload.get("candidate") != expected_candidate
        or not isinstance(payload.get("notes"), list)
        or isinstance(expected_note_count, bool)
        or not isinstance(expected_note_count, int)
    ):
        raise ValueError("vocal note evidence differs")
    try:
        notes = _validated_notes(
            tuple(
                NoteEvent(
                    start=float(note["start_seconds"]),
                    end=float(note["end_seconds"]),
                    pitch=int(note["pitch"]),
                    velocity=int(note["velocity"]),
                )
                for note in payload["notes"]
            )
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("vocal note evidence differs") from error
    if len(notes) != expected_note_count:
        raise ValueError("vocal note count differs")
    return notes


def _reverify_inputs(inputs: Mapping[str, Any]) -> None:
    for label in ("control", "melroformer", "leaf"):
        if _sha256(inputs[f"{label}_path"]) != inputs[f"{label}_sha256"]:
            raise ValueError(f"{label} evidence changed during analysis")
        _verify_artifacts(
            inputs[f"{label}_root"], inputs[label].get("artifacts")
        )


def _notes_to_intervals(
    notes: Sequence[NoteEvent], duration: float
) -> tuple[tuple[float, float], ...]:
    intervals = []
    for note in _validated_notes(notes):
        if note.start >= duration or note.end > duration + 1e-6:
            raise ValueError("vocal note exceeds the sealed excerpt duration")
        intervals.append((note.start, min(note.end, duration)))
    return _merge_intervals(tuple(intervals))


def _merge_intervals(
    intervals: Sequence[tuple[float, float]],
) -> tuple[tuple[float, float], ...]:
    ordered = sorted(intervals)
    merged: list[list[float]] = []
    for start, end in ordered:
        if (
            not math.isfinite(start)
            or not math.isfinite(end)
            or start < 0.0
            or end <= start
        ):
            raise ValueError("invalid activity interval")
        if not merged or start > merged[-1][1] + 1e-9:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return tuple((start, end) for start, end in merged)


def _provider_support_segments(
    groups: Mapping[str, Sequence[tuple[float, float]]],
    *,
    minimum_support: int,
) -> list[dict[str, Any]]:
    if minimum_support < 2 or len(groups) < minimum_support:
        raise ValueError("invalid provider-support policy")
    boundaries = sorted(
        {
            point
            for intervals in groups.values()
            for interval in intervals
            for point in interval
        }
    )
    segments: list[dict[str, Any]] = []
    for start, end in zip(boundaries, boundaries[1:]):
        midpoint = (start + end) / 2.0
        supporting = tuple(
            provider_id
            for provider_id, intervals in sorted(groups.items())
            if any(left <= midpoint < right for left, right in intervals)
        )
        if len(supporting) < minimum_support:
            continue
        if segments and segments[-1]["providers"] == list(supporting) and abs(
            float(segments[-1]["end"]) - start
        ) <= 1e-9:
            segments[-1]["end"] = end
        else:
            segments.append(
                {
                    "start": start,
                    "end": end,
                    "providers": list(supporting),
                    "support_count": len(supporting),
                }
            )
    return segments


def _phrase_intervals(
    consensus: Sequence[tuple[float, float]], *, gap_seconds: float
) -> tuple[tuple[float, float], ...]:
    phrases: list[list[float]] = []
    for start, end in consensus:
        if not phrases or start - phrases[-1][1] > gap_seconds:
            phrases.append([start, end])
        else:
            phrases[-1][1] = end
    return tuple((start, end) for start, end in phrases)


def _candidate_observation(
    intervals: Sequence[tuple[float, float]],
    *,
    consensus: Sequence[tuple[float, float]],
    phrases: Sequence[tuple[float, float]],
    note_count: int,
) -> dict[str, Any]:
    supported = _intersect_intervals(intervals, consensus)
    missing = tuple(
        interval
        for interval in _subtract_intervals(consensus, intervals)
        if interval[1] - interval[0] + 1e-9 >= _MINIMUM_MISSING_SPAN_SECONDS
    )
    consensus_seconds = _interval_duration(consensus)
    active_seconds = _interval_duration(intervals)
    supported_seconds = _interval_duration(supported)
    return {
        "note_count": note_count,
        "active_seconds": _round(active_seconds),
        "consensus_covered_seconds": _round(supported_seconds),
        "consensus_coverage_ratio": _ratio(supported_seconds, consensus_seconds),
        "activity_supported_by_consensus_ratio": _ratio(
            supported_seconds, active_seconds
        ),
        "reported_missing_span_count": len(missing),
        "reported_missing_spans": _serialise_intervals(missing),
        "phrase_count_with_any_coverage": sum(
            bool(_intersect_intervals(intervals, (phrase,))) for phrase in phrases
        ),
        "ranking_semantics": "none; time-activity diagnostic only",
    }


def _candidate_contrast(
    primary: Sequence[tuple[float, float]],
    lowest: Sequence[tuple[float, float]],
    consensus: Sequence[tuple[float, float]],
) -> dict[str, Any]:
    both = _intersect_intervals(_intersect_intervals(primary, lowest), consensus)
    primary_only = _intersect_intervals(
        _subtract_intervals(primary, lowest), consensus
    )
    lowest_only = _intersect_intervals(
        _subtract_intervals(lowest, primary), consensus
    )
    neither = _subtract_intervals(
        consensus, _merge_intervals(tuple(primary) + tuple(lowest))
    )
    return {
        "both_candidates_consensus_seconds": _round(_interval_duration(both)),
        "primary_only_consensus_seconds": _round(
            _interval_duration(primary_only)
        ),
        "lowest_only_consensus_seconds": _round(_interval_duration(lowest_only)),
        "neither_candidate_consensus_seconds": _round(_interval_duration(neither)),
        "reported_lowest_only_consensus_span_count": len(
            _reported_spans(lowest_only)
        ),
        "reported_lowest_only_consensus_spans": _serialise_intervals(
            _reported_spans(lowest_only)
        ),
        "reported_neither_candidate_consensus_span_count": len(
            _reported_spans(neither)
        ),
        "reported_neither_candidate_consensus_spans": _serialise_intervals(
            _reported_spans(neither)
        ),
        "automatic_merge_performed": False,
    }


def _phrase_observations(
    phrases: Sequence[tuple[float, float]],
    *,
    consensus: Sequence[tuple[float, float]],
    target_intervals: Mapping[str, Sequence[tuple[float, float]]],
    provider_groups: Mapping[str, Sequence[tuple[float, float]]],
) -> list[dict[str, Any]]:
    result = []
    for index, phrase in enumerate(phrases, start=1):
        phrase_consensus = _intersect_intervals(consensus, (phrase,))
        consensus_seconds = _interval_duration(phrase_consensus)
        providers = [
            provider_id
            for provider_id, intervals in sorted(provider_groups.items())
            if _intersect_intervals(intervals, phrase_consensus)
        ]
        result.append(
            {
                "phrase_id": f"phrase-{index:02d}",
                "start": _round(phrase[0]),
                "end": _round(phrase[1]),
                "consensus_active_seconds": _round(consensus_seconds),
                "providers_with_any_support": providers,
                "candidate_coverage_ratio": {
                    candidate_id: _ratio(
                        _interval_duration(
                            _intersect_intervals(intervals, phrase_consensus)
                        ),
                        consensus_seconds,
                    )
                    for candidate_id, intervals in sorted(target_intervals.items())
                },
            }
        )
    return result


def _intersect_intervals(
    left: Sequence[tuple[float, float]],
    right: Sequence[tuple[float, float]],
) -> tuple[tuple[float, float], ...]:
    result = []
    for left_start, left_end in left:
        for right_start, right_end in right:
            start = max(left_start, right_start)
            end = min(left_end, right_end)
            if end > start:
                result.append((start, end))
    return _merge_intervals(tuple(result))


def _subtract_intervals(
    base: Sequence[tuple[float, float]],
    removed: Sequence[tuple[float, float]],
) -> tuple[tuple[float, float], ...]:
    remaining = []
    for base_start, base_end in base:
        fragments = [(base_start, base_end)]
        for remove_start, remove_end in removed:
            next_fragments = []
            for start, end in fragments:
                if remove_end <= start or remove_start >= end:
                    next_fragments.append((start, end))
                    continue
                if remove_start > start:
                    next_fragments.append((start, min(remove_start, end)))
                if remove_end < end:
                    next_fragments.append((max(remove_end, start), end))
            fragments = next_fragments
        remaining.extend(fragments)
    return _merge_intervals(tuple(remaining))


def _interval_duration(intervals: Sequence[tuple[float, float]]) -> float:
    return sum(end - start for start, end in intervals)


def _serialise_intervals(
    intervals: Sequence[tuple[float, float]],
) -> list[dict[str, float]]:
    return [
        {"start": _round(start), "end": _round(end)} for start, end in intervals
    ]


def _serialise_support_segments(
    segments: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "start": _round(float(segment["start"])),
            "end": _round(float(segment["end"])),
            "providers": list(segment["providers"]),
            "support_count": int(segment["support_count"]),
        }
        for segment in segments
        if _round(float(segment["end"])) > _round(float(segment["start"]))
    ]


def _reported_spans(
    intervals: Sequence[tuple[float, float]],
) -> tuple[tuple[float, float], ...]:
    return tuple(
        interval
        for interval in intervals
        if interval[1] - interval[0] + 1e-9
        >= _MINIMUM_MISSING_SPAN_SECONDS
    )


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0.0:
        return None
    return _round(numerator / denominator)


def _round(value: float) -> float:
    return round(float(value), _ROUND_DIGITS)


__all__: Sequence[str] = ()
