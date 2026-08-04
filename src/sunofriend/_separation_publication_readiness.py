"""Fail-closed publication-readiness projection for private separation.

This owner-only projection turns the current cross-song evidence reports into
one machine-readable gate ledger.  It deliberately cannot accept a
separator or enable a product route: missing publication evidence remains an
explicit open gate instead of being inferred from MIDI agreement or a useful
human audition.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from ._separation_authorised_midi_comparison import (
    _document_sha256,
    _regular_json,
    _sha256,
)
from ._separation_cross_song_evidence_index import _ID_PATTERN
from ._separation_audio_quality_review import (
    POLICY_ID as AUDIO_QUALITY_POLICY_ID,
    RESULT_SCHEMA as AUDIO_QUALITY_RESULT_SCHEMA,
)
from ._separation_human_listening_coverage import (
    SCHEMA as HUMAN_LISTENING_SCHEMA,
)
from ._separation_full_song_resource_benchmark_result import (
    SCHEMA as RESOURCE_BENCHMARK_RESULT_SCHEMA,
    STATUS as RESOURCE_BENCHMARK_RESULT_STATUS,
)
from ._separation_normalized_midi_agreement import (
    SCHEMA as NORMALIZED_AGREEMENT_SCHEMA,
)
from ._separation_vocal_candidate_audition import _write_fresh_private_json


SCHEMA = "sunofriend.private-separation-publication-readiness.v2"
AUDIO_MINIMUM_POLICY_ID = "cross-song-kim-vocal-minimum-usable-v1"
_MAXIMUM_REPORT_BYTES = 2 * 1024 * 1024
_NON_SEVERE = frozenset(("low", "noticeable"))
_VOCAL_RETENTION = frozenset(
    ("substantially_complete", "partially_complete", "little_or_none", "cannot_tell")
)
_PROBLEM_SEVERITY = frozenset(("low", "noticeable", "severe", "cannot_tell"))


@dataclass(frozen=True)
class _LoadedJson:
    path: Path
    file_sha256: str
    document: dict[str, Any]


def _project_private_separation_publication_readiness(
    normalized_agreement_path: str | Path,
    human_listening_coverage_path: str | Path,
    *,
    separated_audio_quality_path: str | Path | None = None,
    resource_benchmark_result_path: str | Path | None = None,
    out: str | Path,
) -> dict[str, Any]:
    """Build one path-free ledger from the currently sealed acceptance work."""

    agreement = _load_normalized_agreement(normalized_agreement_path)
    listening = _load_human_listening_coverage(human_listening_coverage_path)
    audio_quality = (
        _load_separated_audio_quality(separated_audio_quality_path)
        if separated_audio_quality_path is not None
        else None
    )
    resource_benchmark = (
        _load_resource_benchmark_result(resource_benchmark_result_path)
        if resource_benchmark_result_path is not None
        else None
    )
    _require_listening_bound_to_agreement(listening, agreement)

    agreement_track_ids = {
        _safe_id(cell["track_id"], "agreement track ID")
        for cell in agreement.document["cells"]
    }
    listening_track_ids = {
        _safe_id(window["track_id"], "listening track ID")
        for window in listening.document["review_windows"]
    }
    if listening_track_ids != agreement_track_ids:
        raise ValueError("human-listening track coverage differs from agreement")
    _require_coverage_geometry(
        listening.document["coverage"],
        agreement_track_count=len(agreement_track_ids),
        review_window_count=len(listening.document["review_windows"]),
    )
    if audio_quality is not None:
        _require_audio_bound_to_agreement(audio_quality, agreement)

    document = _build_document(
        agreement=agreement,
        listening=listening,
        audio_quality=audio_quality,
        resource_benchmark=resource_benchmark,
    )
    document["document_sha256"] = _document_sha256(document)
    _reverify(agreement, listening, audio_quality, resource_benchmark)
    _write_fresh_private_json(Path(out), document)
    document["report"] = str(Path(out).expanduser().absolute())
    return document


def _load_normalized_agreement(path: str | Path) -> _LoadedJson:
    loaded = _load_json(path, "normalized MIDI agreement")
    document = loaded.document
    cells = document.get("cells")
    gate = document.get("publication_gate")
    contract = document.get("comparison_contract")
    if (
        document.get("schema") != NORMALIZED_AGREEMENT_SCHEMA
        or document.get("status")
        != "complete_pairwise_agreement_not_quality_or_acceptance"
        or document.get("evidence_scope") != "private_development_only"
        or document.get("document_sha256") != _document_sha256(document)
        or not isinstance(cells, list)
        or len(cells) < 2
        or not all(isinstance(cell, Mapping) for cell in cells)
        or not all(
            isinstance(cell.get("track_id"), str)
            and _ID_PATTERN.fullmatch(str(cell["track_id"])) is not None
            for cell in cells
        )
        or len({cell["track_id"] for cell in cells}) != len(cells)
        or not isinstance(gate, Mapping)
        or gate.get("status") != "open"
        or not isinstance(contract, Mapping)
        or contract.get("quality_comparison_permitted") is not False
        or contract.get("method_ranking_permitted") is not False
    ):
        raise ValueError("normalized MIDI agreement contract differs")
    _require_all_false(document.get("permissions"), "agreement permissions")
    _require_all_false(document.get("effects"), "agreement effects")
    return loaded


def _load_human_listening_coverage(path: str | Path) -> _LoadedJson:
    loaded = _load_json(path, "human-listening coverage")
    document = loaded.document
    coverage = document.get("coverage")
    gate = document.get("publication_gate")
    windows = document.get("review_windows")
    if (
        document.get("schema") != HUMAN_LISTENING_SCHEMA
        or document.get("status")
        != "complete_human_listening_projection_not_acceptance"
        or document.get("evidence_scope") != "private_development_only"
        or document.get("document_sha256") != _document_sha256(document)
        or not isinstance(coverage, Mapping)
        or coverage.get("cross_song_review_coverage_complete") is not True
        or coverage.get("all_reviews_record_focus_phrase_coverage") is not True
        or coverage.get("all_reviewed_tracks_are_bound_to_normalized_excerpt")
        is not True
        or not isinstance(windows, list)
        or not windows
        or not all(
            isinstance(window, Mapping)
            and isinstance(window.get("track_id"), str)
            and _ID_PATTERN.fullmatch(str(window["track_id"])) is not None
            for window in windows
        )
        or not isinstance(gate, Mapping)
        or gate.get("status") != "open"
    ):
        raise ValueError("human-listening coverage contract differs")
    _require_all_false(document.get("permissions"), "listening permissions")
    _require_all_false(document.get("effects"), "listening effects")
    return loaded


def _load_separated_audio_quality(path: str | Path) -> _LoadedJson:
    loaded = _load_json(path, "separated-audio quality result")
    document = loaded.document
    units = document.get("units")
    if (
        document.get("schema") != AUDIO_QUALITY_RESULT_SCHEMA
        or document.get("status") != "complete_review_no_activation"
        or document.get("evidence_scope") != "private_development_only"
        or document.get("policy_id") != AUDIO_QUALITY_POLICY_ID
        or document.get("document_sha256") != _document_sha256(document)
        or not isinstance(units, list)
        or len(units) < 2
        or document.get("unit_count") != len(units)
        or not all(isinstance(unit, Mapping) for unit in units)
    ):
        raise ValueError("separated-audio quality contract differs")
    _require_all_false(document.get("permissions"), "audio-quality permissions")
    _require_all_false(document.get("effects"), "audio-quality effects")
    track_ids: list[str] = []
    for unit in units:
        track_id = _safe_id(unit.get("track_id"), "audio-quality track ID")
        source_track_id = _safe_id(
            unit.get("source_track_id"), "audio-quality source track ID"
        )
        source_binding = unit.get("source_binding")
        ratings = unit.get("ratings_by_method")
        source_seconds = unit.get("source_seconds")
        if (
            not isinstance(source_binding, Mapping)
            or source_binding.get("track_id") != track_id
            or source_binding.get("source_track_id") != source_track_id
            or not isinstance(source_seconds, list)
            or len(source_seconds) != 2
            or source_seconds
            != [
                source_binding.get("start_seconds"),
                source_binding.get("end_seconds"),
            ]
            or not isinstance(ratings, Mapping)
            or "kim-vocal-2" not in ratings
            or not isinstance(ratings["kim-vocal-2"], Mapping)
            or set(ratings["kim-vocal-2"])
            != {"vocal_retention", "non_vocal_bleed", "artefacts"}
        ):
            raise ValueError("separated-audio quality unit differs")
        provider_id = _safe_id(
            source_binding.get("provider_id"), "audio-quality provider ID"
        )
        provider_method = f"provider-{provider_id}-broad-vocals"
        if (
            set(ratings) != {"kim-vocal-2", provider_method}
            or {unit.get("candidate_a_method"), unit.get("candidate_b_method")}
            != set(ratings)
        ):
            raise ValueError("separated-audio quality methods differ")
        for method_ratings in ratings.values():
            if (
                not isinstance(method_ratings, Mapping)
                or set(method_ratings)
                != {"vocal_retention", "non_vocal_bleed", "artefacts"}
                or method_ratings.get("vocal_retention") not in _VOCAL_RETENTION
                or method_ratings.get("non_vocal_bleed") not in _PROBLEM_SEVERITY
                or method_ratings.get("artefacts") not in _PROBLEM_SEVERITY
            ):
                raise ValueError("separated-audio quality ratings differ")
        for field in (
            "authorised_excerpt_sha256",
            "authorised_excerpt_document_sha256",
            "candidate_evaluation_sha256",
            "candidate_evaluation_document_sha256",
            "role_mapping_sha256",
            "role_mapping_document_sha256",
            "source_audio_sha256",
            "candidate_audio_sha256",
            "provider_audio_sha256",
        ):
            _sha256_hex(source_binding.get(field), f"audio-quality {field}")
        track_ids.append(track_id)
    if len(set(track_ids)) != len(track_ids):
        raise ValueError("separated-audio quality track IDs differ")
    return loaded


def _load_resource_benchmark_result(path: str | Path) -> _LoadedJson:
    loaded = _load_json(path, "full-song resource benchmark result")
    document = loaded.document
    coverage = document.get("coverage")
    readiness = document.get("readiness")
    protocol = document.get("protocol")
    machine = document.get("machine_class")
    candidate = document.get("candidate")
    aggregate = document.get("aggregate")
    repetitions = document.get("repetitions")
    bindings = document.get("bindings")
    if (
        document.get("schema") != RESOURCE_BENCHMARK_RESULT_SCHEMA
        or document.get("status") != RESOURCE_BENCHMARK_RESULT_STATUS
        or document.get("evidence_scope") != "private_development_only"
        or document.get("document_sha256") != _document_sha256(document)
        or not isinstance(coverage, Mapping)
        or coverage.get("all_required_measurements_observed") is not True
        or coverage.get("same_plan_checkpoint_runtime_device_and_machine_observed")
        is not True
        or coverage.get("serial_non_overlapping_execution_observed") is not True
        or type(coverage.get("controlled_repetitions_observed")) is not int
        or not 3 <= coverage["controlled_repetitions_observed"] <= 10
        or type(coverage.get("development_machine_thresholds_met")) is not bool
        or type(coverage.get("required_16_gib_acceptance_class_observed"))
        is not bool
        or not isinstance(readiness, Mapping)
        or readiness.get("controlled_repeated_benchmark_complete") is not True
        or readiness.get("development_machine_thresholds_met")
        is not coverage["development_machine_thresholds_met"]
        or type(readiness.get("resource_envelope_accepted")) is not bool
        or readiness.get("publication_ready") is not False
        or not isinstance(protocol, Mapping)
        or protocol.get("name") != "fresh-process-resource-measurement-v1"
        or protocol.get("serial_non_overlapping") is not True
        or protocol.get("distinct_process_scoped_nonces") is not True
        or protocol.get("operating_system_cache_controlled") is not False
        or protocol.get("planned_repetitions")
        != coverage["controlled_repetitions_observed"]
        or protocol.get("verified_repetitions")
        != coverage["controlled_repetitions_observed"]
        or not isinstance(repetitions, list)
        or len(repetitions) != coverage["controlled_repetitions_observed"]
        or not _valid_resource_repetitions(
            repetitions,
            expected_count=coverage["controlled_repetitions_observed"],
            aggregate_within=coverage["development_machine_thresholds_met"],
        )
        or not isinstance(machine, Mapping)
        or machine.get("architecture") != "arm64"
        or machine.get("hardware_family") != "Apple silicon"
        or type(machine.get("unified_memory_gib")) is not int
        or machine.get("class_id")
        != f"apple-silicon-{machine.get('unified_memory_gib')}gib"
        or coverage["required_16_gib_acceptance_class_observed"]
        is not (machine["unified_memory_gib"] == 16)
        or not isinstance(candidate, Mapping)
        or candidate.get("candidate_id") != "mlx-melroformer-kim-vocal-2"
        or candidate.get("device") not in {"cpu", "gpu"}
        or not isinstance(aggregate, Mapping)
        or not _valid_resource_aggregate(
            aggregate,
            expected_count=coverage["controlled_repetitions_observed"],
        )
        or not isinstance(bindings, Mapping)
        or set(bindings)
        != {
            "benchmark_plan_sha256",
            "benchmark_plan_document_sha256",
            "plan_report_sha256",
            "checkpoint_sha256",
            "runtime_executable_sha256",
        }
        or not all(_is_sha256(value) for value in bindings.values())
        or readiness["resource_envelope_accepted"]
        is not (
            coverage["development_machine_thresholds_met"]
            and coverage["required_16_gib_acceptance_class_observed"]
        )
    ):
        raise ValueError("full-song resource benchmark result differs")
    _require_all_false(document.get("permissions"), "resource permissions")
    _require_all_false(document.get("effects"), "resource effects")
    return loaded


def _valid_resource_repetitions(
    values: list[Any],
    *,
    expected_count: int,
    aggregate_within: bool,
) -> bool:
    if len(values) != expected_count:
        return False
    starts: list[int] = []
    finishes: list[int] = []
    nonces: list[str] = []
    within_thresholds: list[bool] = []
    for index, item in enumerate(values, start=1):
        if (
            not isinstance(item, Mapping)
            or set(item)
            != {
                "index",
                "report_sha256",
                "document_sha256",
                "nonce_sha256",
                "wall_started_unix_ns",
                "wall_finished_unix_ns",
                "within_frozen_thresholds",
            }
            or item.get("index") != index
            or type(item.get("within_frozen_thresholds")) is not bool
            or not all(
                _is_sha256(item.get(field))
                for field in (
                    "report_sha256",
                    "document_sha256",
                    "nonce_sha256",
                )
            )
            or type(item.get("wall_started_unix_ns")) is not int
            or type(item.get("wall_finished_unix_ns")) is not int
            or item["wall_started_unix_ns"] <= 0
            or item["wall_finished_unix_ns"] <= item["wall_started_unix_ns"]
        ):
            return False
        starts.append(item["wall_started_unix_ns"])
        finishes.append(item["wall_finished_unix_ns"])
        nonces.append(item["nonce_sha256"])
        within_thresholds.append(item["within_frozen_thresholds"])
    return (
        len(set(nonces)) == expected_count
        and all(earlier <= later for earlier, later in zip(finishes, starts[1:]))
        and all(within_thresholds) is aggregate_within
    )


def _valid_resource_aggregate(
    value: Mapping[str, Any], *, expected_count: int
) -> bool:
    summaries = (
        "parent_observed_full_song_wall_time_seconds",
        "wall_time_seconds_per_audio_minute",
        "summed_worker_model_call_seconds",
        "peak_process_rss_bytes",
        "peak_mlx_allocator_memory_bytes",
        "peak_total_unified_memory_bytes",
    )
    return (
        all(
            _valid_summary(value.get(field), expected_count=expected_count)
            for field in summaries
        )
        and isinstance(value.get("maximum_peak_total_unified_memory_gib"), (int, float))
        and not isinstance(value.get("maximum_peak_total_unified_memory_gib"), bool)
        and value["maximum_peak_total_unified_memory_gib"] > 0
        and value.get("timeouts_observed") == 0
        and value.get("oom_events_observed") == 0
        and isinstance(value.get("thermal_state_before"), list)
        and isinstance(value.get("thermal_state_after"), list)
        and len(value["thermal_state_before"]) == len(value["thermal_state_after"])
        and len(value["thermal_state_before"]) == expected_count
        and all(_valid_thermal(item) for item in value["thermal_state_before"])
        and all(_valid_thermal(item) for item in value["thermal_state_after"])
    )


def _valid_summary(value: Any, *, expected_count: int) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"count", "minimum", "median", "maximum"}
        and type(value.get("count")) is int
        and value["count"] == expected_count
        and all(
            isinstance(value.get(field), (int, float))
            and not isinstance(value.get(field), bool)
            and value[field] > 0
            for field in ("minimum", "median", "maximum")
        )
        and value["minimum"] <= value["median"] <= value["maximum"]
    )


def _valid_thermal(value: Any) -> bool:
    names = {0: "nominal", 1: "fair", 2: "serious", 3: "critical"}
    return (
        isinstance(value, Mapping)
        and set(value) == {"value", "name"}
        and type(value.get("value")) is int
        and value["value"] in names
        and value.get("name") == names[value["value"]]
    )


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _require_listening_bound_to_agreement(
    listening: _LoadedJson,
    agreement: _LoadedJson,
) -> None:
    inputs = listening.document.get("inputs")
    if (
        not isinstance(inputs, Mapping)
        or inputs.get("normalized_midi_agreement_sha256")
        != agreement.file_sha256
        or inputs.get("normalized_midi_agreement_document_sha256")
        != agreement.document.get("document_sha256")
    ):
        raise ValueError("human-listening coverage is not bound to agreement")


def _require_audio_bound_to_agreement(
    audio_quality: _LoadedJson,
    agreement: _LoadedJson,
) -> None:
    agreement_by_track = {
        cell["track_id"]: cell for cell in agreement.document["cells"]
    }
    audio_by_track = {
        unit["track_id"]: unit for unit in audio_quality.document["units"]
    }
    if set(audio_by_track) != set(agreement_by_track):
        raise ValueError("separated-audio track coverage differs from agreement")
    for track_id, unit in audio_by_track.items():
        agreement_binding = agreement_by_track[track_id].get("source_binding")
        audio_binding = unit["source_binding"]
        if not isinstance(agreement_binding, Mapping) or any(
            audio_binding.get(field) != agreement_binding.get(field)
            for field in (
                "authorised_excerpt_sha256",
                "authorised_excerpt_document_sha256",
                "role_mapping_sha256",
                "role_mapping_document_sha256",
            )
        ):
            raise ValueError("separated-audio source binding differs from agreement")
        if unit.get("source_track_id") != agreement_by_track[track_id].get(
            "source_track_id"
        ):
            raise ValueError("separated-audio source track differs from agreement")


def _require_coverage_geometry(
    coverage: Mapping[str, Any],
    *,
    agreement_track_count: int,
    review_window_count: int,
) -> None:
    agreement_count = _nonnegative_int(
        coverage.get("agreement_track_count"), "agreement track count"
    )
    reviewed_track_count = _nonnegative_int(
        coverage.get("reviewed_track_count"), "reviewed track count"
    )
    window_count = _nonnegative_int(
        coverage.get("review_window_count"), "review window count"
    )
    candidate_count = _nonnegative_int(
        coverage.get("reviewed_candidate_count"), "reviewed candidate count"
    )
    useful_count = _nonnegative_int(
        coverage.get("useful_for_focus_count"), "useful candidate count"
    )
    structured_count = _nonnegative_int(
        coverage.get("structured_focus_phrase_coverage_window_count"),
        "structured phrase-coverage window count",
    )
    if (
        agreement_count != agreement_track_count
        or reviewed_track_count != agreement_track_count
        or window_count != review_window_count
        or window_count < agreement_track_count
        or candidate_count < window_count
        or useful_count > candidate_count
        or structured_count != window_count
    ):
        raise ValueError("human-listening coverage geometry differs")


def _build_document(
    *,
    agreement: _LoadedJson,
    listening: _LoadedJson,
    audio_quality: _LoadedJson | None,
    resource_benchmark: _LoadedJson | None,
) -> dict[str, Any]:
    coverage = listening.document["coverage"]
    audio_assessment = (
        _assess_separated_audio_quality(audio_quality.document)
        if audio_quality is not None
        else None
    )
    resource_assessment = (
        _assess_resource_benchmark(resource_benchmark.document)
        if resource_benchmark is not None
        else None
    )
    passed = [
        _gate(
            "source_bound_cross_song_downstream_midi",
            "passed",
            "The same candidate/control MIDI contract was recomputed on two or more authorised songs.",
        ),
        _gate(
            "source_bound_cross_song_human_listening",
            "passed",
            "Every song in the normalized agreement has at least one completed focus-relative review.",
        ),
        _gate(
            "structured_phrase_completeness_review",
            "passed",
            "Every supplied review window records completeness separately from usefulness and source-line identity.",
        ),
    ]
    audio_gate = _gate(
        "separator_audio_quality_cross_song",
        "passed" if audio_assessment and audio_assessment["gate_passed"] else "open",
        (
            "Every source-bound Kim Vocal 2 excerpt was rated substantially complete with no severe non-vocal bleed or distracting artefacts."
            if audio_assessment and audio_assessment["gate_passed"]
            else (
                "The completed source-bound review did not meet the predeclared minimum of substantially complete vocals and no severe bleed or artefacts on every song."
                if audio_assessment
                else "The current cross-song acceptance evidence evaluates downstream vocal MIDI, not separated-audio fidelity and bleed."
            )
        ),
    )
    if audio_gate["status"] == "passed":
        passed.append(audio_gate)
        audio_open_gates: list[dict[str, str]] = []
    else:
        audio_open_gates = [audio_gate]
    open_gates = audio_open_gates + [
        _gate(
            "full_song_duration_and_alignment",
            "open",
            "Bounded excerpts do not prove full-song quality, clock alignment or drift.",
        ),
        _gate(
            "broad_role_coverage",
            "open",
            "The accepted evidence does not yet cover publishable drums, bass, keys, other and vocal outputs together.",
        ),
        _gate(
            "hidden_song_disjoint_test_set",
            "open",
            "The reviewed owner corpus is useful development evidence but is not a hidden test set.",
        ),
        _gate(
            "checkpoint_usage_and_distribution_terms",
            "open",
            "Checkpoint-specific product and redistribution permission has not been accepted by this evidence chain.",
        ),
        _gate(
            "offline_execution_acceptance",
            "open",
            "A clean installed-machine offline run has not been accepted for publication.",
        ),
        _gate(
            "resource_envelope_acceptance",
            "open",
            (
                "Three controlled full-song repetitions met the frozen ceilings on the development Mac, but the separately required 16 GiB acceptance class was not observed."
                if resource_assessment
                and resource_assessment["development_machine_thresholds_met"]
                and not resource_assessment[
                    "required_16_gib_acceptance_class_observed"
                ]
                else "Full-song time, memory, disk and failure-recovery limits have not been accepted."
            ),
        ),
        _gate(
            "public_cli_tui_simple_studio_route",
            "open",
            "No public finished-song separator route is enabled in the product contract.",
        ),
    ]
    gates = passed + open_gates
    inputs = {
        "normalized_midi_agreement_sha256": agreement.file_sha256,
        "normalized_midi_agreement_document_sha256": agreement.document[
            "document_sha256"
        ],
        "human_listening_coverage_sha256": listening.file_sha256,
        "human_listening_coverage_document_sha256": listening.document[
            "document_sha256"
        ],
    }
    if audio_quality is not None:
        inputs.update(
            {
                "separated_audio_quality_sha256": audio_quality.file_sha256,
                "separated_audio_quality_document_sha256": audio_quality.document[
                    "document_sha256"
                ],
            }
        )
    if resource_benchmark is not None:
        inputs.update(
            {
                "resource_benchmark_result_sha256": resource_benchmark.file_sha256,
                "resource_benchmark_result_document_sha256": resource_benchmark.document[
                    "document_sha256"
                ],
            }
        )
    return {
        "schema": SCHEMA,
        "status": "blocked_private_bounded_vocal_midi_evidence_only",
        "evidence_scope": "private_development_only",
        "inputs": inputs,
        "observed_scope": {
            "track_count": coverage["agreement_track_count"],
            "review_window_count": coverage["review_window_count"],
            "reviewed_candidate_count": coverage["reviewed_candidate_count"],
            "useful_for_focus_count": coverage["useful_for_focus_count"],
            "structured_focus_phrase_coverage_window_count": coverage[
                "structured_focus_phrase_coverage_window_count"
            ],
            "role_scope": ["vocals"],
            "duration_scope": "bounded_authorised_excerpts",
            "separated_audio_reviewed_track_count": (
                audio_assessment["reviewed_track_count"]
                if audio_assessment
                else 0
            ),
        },
        "readiness": {
            "stage": "private_bounded_vocal_research",
            "passed_gate_count": len(passed),
            "open_gate_count": len(open_gates),
            "required_gate_count": len(gates),
            "publication_ready": False,
            "experimental_studio_route_ready": False,
            "one_action_simple_route_ready": False,
        },
        "gates": gates,
        "separated_audio_quality_assessment": audio_assessment,
        "resource_benchmark_assessment": resource_assessment,
        "interpretation": {
            "private_separator_derived_midi_has_useful_evidence": True,
            "general_finished_song_separation_is_working": False,
            "midi_agreement_is_audio_separation_quality": False,
            "human_usefulness_is_accuracy": False,
            "passed_gate_is_separator_selection": False,
            "open_gate_can_be_inferred_from_other_evidence": False,
            "provider_preference_is_separator_selection": False,
            "development_resource_thresholds_are_resource_acceptance": False,
        },
        "policy": {
            "fail_closed": True,
            "input_file_hashes_verified": True,
            "input_document_hashes_verified": True,
            "paths_copied": False,
            "free_text_copied": False,
            "quality_score_computed": False,
            "minimum_usable_audio_policy_predeclared": True,
            "separator_selected": False,
            "product_route_enabled": False,
            "development_resource_result_can_close_acceptance_gate": False,
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
            "audio_created_or_mutated": False,
            "candidate_activated": False,
            "default_changed": False,
            "midi_created_or_mutated": False,
            "product_contract_mutated": False,
            "source_graph_mutated": False,
        },
        "limitations": [
            "This ledger summarizes only the exact supplied reports; it does not inspect audio or run a model.",
            "Its passed gates are bounded evidence milestones, not a percentage quality score or publication approval.",
            "Future gate closure must be supplied by a new typed, hash-bound evidence contract; caller assertions cannot close a gate.",
            "The separated-audio minimum is a bounded usability gate, not a model ranking, score-truth claim or general finished-song approval.",
            "A controlled development-machine resource result records progress but cannot substitute for the separate acceptance-class contract.",
        ],
    }


def _assess_resource_benchmark(document: Mapping[str, Any]) -> dict[str, Any]:
    coverage = document["coverage"]
    aggregate = document["aggregate"]
    return {
        "protocol": document["protocol"]["name"],
        "candidate_id": document["candidate"]["candidate_id"],
        "device": document["candidate"]["device"],
        "machine_class_id": document["machine_class"]["class_id"],
        "unified_memory_gib": document["machine_class"]["unified_memory_gib"],
        "controlled_repetitions_observed": coverage[
            "controlled_repetitions_observed"
        ],
        "development_machine_thresholds_met": coverage[
            "development_machine_thresholds_met"
        ],
        "required_16_gib_acceptance_class_observed": coverage[
            "required_16_gib_acceptance_class_observed"
        ],
        "resource_envelope_accepted": document["readiness"][
            "resource_envelope_accepted"
        ],
        "maximum_parent_wall_seconds": aggregate[
            "parent_observed_full_song_wall_time_seconds"
        ]["maximum"],
        "maximum_wall_seconds_per_audio_minute": aggregate[
            "wall_time_seconds_per_audio_minute"
        ]["maximum"],
        "maximum_peak_process_rss_bytes": aggregate["peak_process_rss_bytes"][
            "maximum"
        ],
        "maximum_peak_mlx_allocator_memory_bytes": aggregate[
            "peak_mlx_allocator_memory_bytes"
        ]["maximum"],
        "maximum_peak_total_unified_memory_bytes": aggregate[
            "peak_total_unified_memory_bytes"
        ]["maximum"],
        "maximum_peak_total_unified_memory_gib": aggregate[
            "maximum_peak_total_unified_memory_gib"
        ],
        "timeouts_observed": aggregate["timeouts_observed"],
        "oom_events_observed": aggregate["oom_events_observed"],
        "acceptance_gate_closed": False,
    }


def _assess_separated_audio_quality(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    cells = []
    for unit in sorted(document["units"], key=lambda item: item["track_id"]):
        ratings = unit["ratings_by_method"]["kim-vocal-2"]
        usable = (
            ratings.get("vocal_retention") == "substantially_complete"
            and ratings.get("non_vocal_bleed") in _NON_SEVERE
            and ratings.get("artefacts") in _NON_SEVERE
        )
        cells.append(
            {
                "track_id": unit["track_id"],
                "source_track_id": unit["source_track_id"],
                "kim_vocal_retention": ratings.get("vocal_retention"),
                "kim_non_vocal_bleed": ratings.get("non_vocal_bleed"),
                "kim_distracting_artefacts": ratings.get("artefacts"),
                "minimum_usable": usable,
            }
        )
    return {
        "policy_id": AUDIO_MINIMUM_POLICY_ID,
        "candidate_method": "kim-vocal-2",
        "reviewed_track_count": len(cells),
        "minimum_usable_track_count": sum(
            cell["minimum_usable"] is True for cell in cells
        ),
        "requirements": {
            "vocal_retention": "substantially_complete",
            "maximum_non_vocal_bleed": "noticeable",
            "maximum_distracting_artefacts": "noticeable",
            "all_source_bound_tracks_must_pass": True,
            "provider_preference_affects_gate": False,
        },
        "cells": cells,
        "gate_passed": bool(cells)
        and all(cell["minimum_usable"] is True for cell in cells),
    }


def _gate(gate_id: str, status: str, finding: str) -> dict[str, str]:
    return {"gate_id": gate_id, "status": status, "finding": finding}


def _load_json(value: str | Path, label: str) -> _LoadedJson:
    path = _regular_json(value, label)
    if path.stat().st_size > _MAXIMUM_REPORT_BYTES:
        raise ValueError(f"{label} is too large")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid JSON") from error
    if not isinstance(document, dict):
        raise ValueError(f"{label} must be a JSON object")
    return _LoadedJson(path=path, file_sha256=_sha256(path), document=document)


def _require_all_false(raw: Any, label: str) -> None:
    if (
        not isinstance(raw, Mapping)
        or not raw
        or any(value is not False for value in raw.values())
    ):
        raise ValueError(f"{label} differ")


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or _ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase ASCII token")
    return value


def _sha256_hex(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _reverify(
    agreement: _LoadedJson,
    listening: _LoadedJson,
    audio_quality: _LoadedJson | None,
    resource_benchmark: _LoadedJson | None,
) -> None:
    if _sha256(agreement.path) != agreement.file_sha256:
        raise ValueError("normalized MIDI agreement changed during projection")
    if _sha256(listening.path) != listening.file_sha256:
        raise ValueError("human-listening coverage changed during projection")
    if (
        audio_quality is not None
        and _sha256(audio_quality.path) != audio_quality.file_sha256
    ):
        raise ValueError("separated-audio quality changed during projection")
    if (
        resource_benchmark is not None
        and _sha256(resource_benchmark.path) != resource_benchmark.file_sha256
    ):
        raise ValueError("resource benchmark result changed during projection")


__all__ = [
    "AUDIO_MINIMUM_POLICY_ID",
    "SCHEMA",
    "_project_private_separation_publication_readiness",
]
