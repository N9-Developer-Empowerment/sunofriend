"""Fail-closed publication-readiness projection for private separation.

This owner-only projection turns the current cross-song evidence reports into
one machine-readable gate ledger.  It deliberately cannot accept a
separator or enable a product route: missing publication evidence remains an
explicit open gate instead of being inferred from MIDI agreement or a useful
human audition.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from ._separation_authorised_midi_comparison import (
    _document_sha256,
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
from ._separation_full_song_review import (
    SCHEMA as FULL_SONG_REVIEW_RESULT_SCHEMA,
    STATUS as FULL_SONG_REVIEW_RESULT_STATUS,
)
from ._separation_full_song_alignment import (
    FEATURE_FRAME_MILLISECONDS as ALIGNMENT_FEATURE_FRAME_MILLISECONDS,
    FEATURE_HOP_MILLISECONDS as ALIGNMENT_FEATURE_HOP_MILLISECONDS,
    MAXIMUM_ACCEPTED_ABSOLUTE_LAG_MILLISECONDS,
    MAXIMUM_ACCEPTED_LAG_SPREAD_MILLISECONDS,
    MAXIMUM_SEARCH_LAG_MILLISECONDS,
    MINIMUM_ACCEPTED_WINDOW_CORRELATION,
    MINIMUM_ACTIVE_RMS_DBFS,
    POLICY_ID as FULL_SONG_ALIGNMENT_POLICY_ID,
    SCHEMA as FULL_SONG_ALIGNMENT_RESULT_SCHEMA,
    STATUS as FULL_SONG_ALIGNMENT_RESULT_STATUS,
    WINDOW_COUNT as ALIGNMENT_WINDOW_COUNT,
)
from ._separation_full_song_join_remediation_review import (
    POLICY_ID as JOIN_REMEDIATION_POLICY_ID,
    TARGET_SAMPLE_RATE as JOIN_REMEDIATION_SAMPLE_RATE,
)
from ._separation_full_song_join_remediation_review_result import (
    RESULT_SCHEMA as JOIN_REMEDIATION_RESULT_SCHEMA,
    RESULT_STATUS as JOIN_REMEDIATION_RESULT_STATUS,
    _write_json_exclusive,
)
from ._separation_full_song_executor import _require_private_directory
from ._separation_normalized_midi_agreement import (
    SCHEMA as NORMALIZED_AGREEMENT_SCHEMA,
)

SCHEMA = "sunofriend.private-separation-publication-readiness.v3"
AUDIO_MINIMUM_POLICY_ID = "cross-song-kim-vocal-minimum-usable-v1"
_MAXIMUM_REPORT_BYTES = 2 * 1024 * 1024
_NON_SEVERE = frozenset(("low", "noticeable"))
_VOCAL_RETENTION = frozenset(
    ("substantially_complete", "partially_complete", "little_or_none", "cannot_tell")
)
_PROBLEM_SEVERITY = frozenset(("low", "noticeable", "severe", "cannot_tell"))
_FULL_SONG_ROLES = ("vocals", "instrumental", "reconstruction")
_FULL_SONG_RATINGS = frozenset(
    ("useful", "noticeable_problems", "not_useful", "cannot_tell")
)
_BOUNDARY_RATINGS = frozenset(("clean", "audible_join", "cannot_tell"))
_JOIN_REMEDIATION_KINDS = (
    "boundary_role_pair",
    "patch_edge_pair",
    "complete_song_pair",
)
_JOIN_REMEDIATION_OUTCOMES = (
    "candidate_preferred",
    "raw_preferred",
    "equivalent",
    "neither",
    "cannot_tell",
)
_JOIN_REMEDIATION_UNIT_KEYS = frozenset(
    (
        "unit_id",
        "kind",
        "title",
        "focus",
        "source_window",
        "blind_choice",
        "candidate_a_identity",
        "candidate_b_identity",
        "resolved_choice",
        "notes",
    )
)
_JOIN_REMEDIATION_BINDING_KEYS = frozenset(
    (
        "answer_key_document_sha256",
        "answer_key_sha256",
        "audio_manifest_sha256",
        "candidate_document_sha256",
        "candidate_report_sha256",
        "execution_report_sha256",
        "execution_state_sha256",
        "review_export_sha256",
        "review_seed_sha256",
        "stitch_document_sha256",
        "stitch_report_sha256",
    )
)
_JOIN_REMEDIATION_EFFECT_KEYS = frozenset(
    (
        "candidate_audio_mutated",
        "candidate_audio_selected",
        "preference_inferred",
        "publication_state_mutated",
        "raw_stitch_mutated",
        "readiness_gate_closed",
        "review_evidence_mutated",
        "separator_accepted",
        "separator_selected",
        "source_graph_mutated",
    )
)
_JOIN_REMEDIATION_RESULT_KEYS = frozenset(
    (
        "schema",
        "status",
        "evidence_scope",
        "policy_id",
        "blind_review",
        "package_commitment",
        "bindings",
        "reviewed_unit_count",
        "counts_by_kind_and_outcome",
        "overall_outcome_counts",
        "units",
        "readiness_evidence",
        "interpretation",
        "verification_claims",
        "verification_limitations",
        "permissions",
        "effects",
        "document_sha256",
    )
)
_MAXIMUM_NOTES_CHARACTERS = 2_000
_FULL_SONG_PERMISSION_KEYS = frozenset(
    (
        "accepted",
        "automatic_selection",
        "product_route_permitted",
        "publication_permitted",
        "simple_mode_available",
        "source_graph_activation",
        "studio_import_available",
    )
)
_FULL_SONG_EFFECT_KEYS = frozenset(
    (
        "product_contract_mutated",
        "publication_state_mutated",
        "separator_accepted",
        "separator_selected",
        "source_audio_mutated",
        "source_graph_mutated",
        "stitched_audio_mutated",
    )
)
_ALIGNMENT_EFFECT_KEYS = frozenset(
    (
        "audio_created_or_mutated",
        "product_contract_mutated",
        "publication_state_mutated",
        "separator_accepted",
        "separator_selected",
        "source_graph_mutated",
    )
)


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
    full_song_review_result_path: str | Path | None = None,
    full_song_alignment_result_path: str | Path | None = None,
    full_song_join_remediation_review_result_path: str | Path | None = None,
    out: str | Path,
) -> dict[str, Any]:
    """Build one path-free ledger from the currently sealed acceptance work."""

    output = Path(out).expanduser().absolute()
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
    full_song_review = (
        _load_full_song_review_result(full_song_review_result_path)
        if full_song_review_result_path is not None
        else None
    )
    full_song_alignment = (
        _load_full_song_alignment_result(full_song_alignment_result_path)
        if full_song_alignment_result_path is not None
        else None
    )
    if (
        full_song_join_remediation_review_result_path is not None
        and full_song_review is None
    ):
        raise ValueError(
            "full-song join-remediation review result requires a full-song "
            "review result for the same raw stitch"
        )
    join_remediation_review = (
        _load_full_song_join_remediation_review_result(
            full_song_join_remediation_review_result_path
        )
        if full_song_join_remediation_review_result_path is not None
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
    if full_song_review is not None and full_song_alignment is not None:
        _require_alignment_bound_to_full_song_review(
            full_song_alignment,
            full_song_review,
        )
    if join_remediation_review is not None:
        assert full_song_review is not None
        _require_join_remediation_bound_to_full_song_review(
            join_remediation_review,
            full_song_review,
        )

    document = _build_document(
        agreement=agreement,
        listening=listening,
        audio_quality=audio_quality,
        resource_benchmark=resource_benchmark,
        full_song_review=full_song_review,
        full_song_alignment=full_song_alignment,
        join_remediation_review=join_remediation_review,
    )
    document["document_sha256"] = _document_sha256(document)
    _reverify(
        agreement,
        listening,
        audio_quality,
        resource_benchmark,
        full_song_review,
        full_song_alignment,
        join_remediation_review,
    )
    if not os.path.lexists(output.parent):
        output.parent.mkdir(parents=True, mode=0o700)
    _require_private_directory(
        output.parent,
        "private separation publication-readiness directory",
    )
    _write_json_exclusive(output, document)
    document["report"] = str(output)
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
        if set(ratings) != {"kim-vocal-2", provider_method} or {
            unit.get("candidate_a_method"),
            unit.get("candidate_b_method"),
        } != set(ratings):
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
        or type(coverage.get("required_16_gib_acceptance_class_observed")) is not bool
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


def _load_full_song_review_result(path: str | Path) -> _LoadedJson:
    loaded = _load_json(path, "full-song review result")
    document = loaded.document
    bindings = document.get("bindings")
    clock = document.get("clock")
    full_song = document.get("full_song")
    summary = document.get("boundary_summary")
    boundaries = document.get("boundaries")
    readiness = document.get("readiness")
    interpretation = document.get("interpretation")
    if (
        document.get("schema") != FULL_SONG_REVIEW_RESULT_SCHEMA
        or document.get("status") != FULL_SONG_REVIEW_RESULT_STATUS
        or document.get("evidence_scope") != "private_development_only"
        or document.get("document_sha256") != _document_sha256(document)
        or not isinstance(bindings, Mapping)
        or set(bindings)
        != {
            "stitch_report_sha256",
            "stitch_document_sha256",
            "review_seed_sha256",
            "review_export_sha256",
            "package_commitment",
            "plan_document_sha256",
            "execution_state_sha256",
        }
        or not all(_is_sha256(value) for value in bindings.values())
        or not _valid_full_song_clock(clock)
        or not _valid_full_song_ratings(full_song)
        or not isinstance(boundaries, list)
        or len(boundaries) != clock["boundary_count"]
        or not _valid_full_song_boundaries(
            boundaries,
            boundary_count=clock["boundary_count"],
            sample_rate=clock["sample_rate"],
            total_frames=clock["frames"],
        )
        or not _valid_full_song_boundary_summary(
            summary,
            boundaries=boundaries,
            boundary_count=clock["boundary_count"],
        )
        or readiness
        != {
            "worker_runs_complete": True,
            "stitched_outputs_complete": True,
            "exact_duration_and_frame_count_verified": True,
            "full_song_and_boundary_listening_complete": True,
            "full_song_quality_accepted": False,
            "publication_ready": False,
        }
        or interpretation
        != {
            "ratings_are_human_listening_evidence": True,
            "clean_boundary_is_separator_accuracy": False,
            "review_completion_is_quality_acceptance": False,
            "automatic_winner_selected": False,
            "separator_accepted": False,
        }
    ):
        raise ValueError("full-song review result differs")
    permissions = document.get("permissions")
    effects = document.get("effects")
    if (
        not isinstance(permissions, Mapping)
        or set(permissions) != _FULL_SONG_PERMISSION_KEYS
        or not isinstance(effects, Mapping)
        or set(effects) != _FULL_SONG_EFFECT_KEYS
    ):
        raise ValueError("full-song review result differs")
    _require_all_false(permissions, "full-song review permissions")
    _require_all_false(effects, "full-song review effects")
    return loaded


def _load_full_song_alignment_result(path: str | Path) -> _LoadedJson:
    loaded = _load_json(path, "full-song alignment result")
    document = loaded.document
    bindings = document.get("bindings")
    clock = document.get("clock")
    protocol = document.get("protocol")
    thresholds = document.get("thresholds")
    windows = document.get("windows")
    summary = document.get("summary")
    readiness = document.get("readiness")
    interpretation = document.get("interpretation")
    if (
        document.get("schema") != FULL_SONG_ALIGNMENT_RESULT_SCHEMA
        or document.get("status") != FULL_SONG_ALIGNMENT_RESULT_STATUS
        or document.get("evidence_scope") != "private_development_only"
        or document.get("policy_id") != FULL_SONG_ALIGNMENT_POLICY_ID
        or document.get("document_sha256") != _document_sha256(document)
        or not isinstance(bindings, Mapping)
        or set(bindings)
        != {
            "stitch_report_sha256",
            "stitch_document_sha256",
            "source_audio_sha256",
            "reconstruction_audio_sha256",
            "plan_document_sha256",
            "execution_state_sha256",
        }
        or not all(_is_sha256(value) for value in bindings.values())
        or not _valid_full_song_clock(clock)
        or not _valid_alignment_protocol(protocol)
        or not _valid_alignment_thresholds(thresholds)
        or not _valid_alignment_windows(
            windows,
            clock=clock,
            protocol=protocol,
        )
        or not _valid_alignment_summary_and_readiness(
            summary,
            readiness=readiness,
            windows=windows,
            thresholds=thresholds,
        )
        or interpretation
        != {
            "alignment_is_separator_quality": False,
            "reconstruction_similarity_is_role_fidelity": False,
            "gate_pass_is_separator_acceptance": False,
            "automatic_winner_selected": False,
        }
    ):
        raise ValueError("full-song alignment result differs")
    permissions = document.get("permissions")
    effects = document.get("effects")
    if (
        not isinstance(permissions, Mapping)
        or set(permissions) != _FULL_SONG_PERMISSION_KEYS
        or not isinstance(effects, Mapping)
        or set(effects) != _ALIGNMENT_EFFECT_KEYS
    ):
        raise ValueError("full-song alignment result differs")
    _require_all_false(permissions, "full-song alignment permissions")
    _require_all_false(effects, "full-song alignment effects")
    return loaded


def _load_full_song_join_remediation_review_result(
    path: str | Path,
) -> _LoadedJson:
    loaded = _load_json(path, "full-song join-remediation review result")
    document = loaded.document
    bindings = document.get("bindings")
    units = document.get("units")
    permissions = document.get("permissions")
    effects = document.get("effects")
    if (
        set(document) != _JOIN_REMEDIATION_RESULT_KEYS
        or document.get("schema") != JOIN_REMEDIATION_RESULT_SCHEMA
        or document.get("status") != JOIN_REMEDIATION_RESULT_STATUS
        or document.get("evidence_scope") != "private_development_only"
        or document.get("policy_id") != JOIN_REMEDIATION_POLICY_ID
        or document.get("blind_review") is not True
        or not _is_sha256(document.get("package_commitment"))
        or document.get("document_sha256") != _document_sha256(document)
        or not isinstance(bindings, Mapping)
        or set(bindings) != _JOIN_REMEDIATION_BINDING_KEYS
        or not all(_is_sha256(value) for value in bindings.values())
        or not isinstance(units, list)
        or not units
        or document.get("reviewed_unit_count") != len(units)
        or not isinstance(permissions, Mapping)
        or set(permissions) != _FULL_SONG_PERMISSION_KEYS
        or not isinstance(effects, Mapping)
        or set(effects) != _JOIN_REMEDIATION_EFFECT_KEYS
    ):
        raise ValueError("full-song join-remediation review result differs")
    _require_all_false(permissions, "join-remediation review permissions")
    _require_all_false(effects, "join-remediation review effects")
    expected_package_commitment = hashlib.sha256(
        (
            f"{bindings['answer_key_sha256']}:"
            f"{bindings['answer_key_document_sha256']}:"
            f"{bindings['audio_manifest_sha256']}"
        ).encode("ascii")
    ).hexdigest()
    if document["package_commitment"] != expected_package_commitment:
        raise ValueError("full-song join-remediation review package commitment differs")

    counts = {
        kind: {outcome: 0 for outcome in _JOIN_REMEDIATION_OUTCOMES}
        for kind in _JOIN_REMEDIATION_KINDS
    }
    overall = {outcome: 0 for outcome in _JOIN_REMEDIATION_OUTCOMES}
    unit_ids: list[str] = []
    for unit in units:
        kind, resolved = _validate_join_remediation_unit(unit)
        counts[kind][resolved] += 1
        overall[resolved] += 1
        unit_ids.append(str(unit["unit_id"]))
    if len(set(unit_ids)) != len(unit_ids):
        raise ValueError("full-song join-remediation review unit set differs")
    boundary_count = sum(counts["boundary_role_pair"].values())
    edge_count = sum(counts["patch_edge_pair"].values())
    song_count = sum(counts["complete_song_pair"].values())
    expected_readiness = {
        "human_join_remediation_review_complete": True,
        "all_targeted_join_pairs_candidate_preferred": (
            counts["boundary_role_pair"]["candidate_preferred"] == boundary_count
        ),
        "all_patch_edges_candidate_or_equivalent": (
            counts["patch_edge_pair"]["candidate_preferred"]
            + counts["patch_edge_pair"]["equivalent"]
            == edge_count
        ),
        "all_complete_songs_candidate_or_equivalent": (
            counts["complete_song_pair"]["candidate_preferred"]
            + counts["complete_song_pair"]["equivalent"]
            == song_count
        ),
        "readiness_reassessment_eligible": True,
        "original_audible_joins_resolved": False,
        "publication_ready": False,
    }
    expected_interpretation = {
        "choices_are_human_listening_evidence": True,
        "candidate_preference_is_join_elimination": False,
        "candidate_preference_is_separator_accuracy": False,
        "review_completion_is_quality_acceptance": False,
        "answer_key_opened_only_after_complete_review_verified": True,
        "automatic_winner_selected": False,
        "separator_accepted": False,
    }
    expected_claims = {
        "review_seed_and_export_bounded_single_read_snapshots": True,
        "review_seed_and_export_no_symlink_follow": True,
        "review_seed_and_export_identity_stable_before_after": True,
        "review_seed_and_export_owner_only_single_link": True,
        "public_semantics_reconstructed_from_verified_sources": True,
        "short_pcm24_pairs_verified_key_blind": True,
        "complete_song_records_verified_key_blind": True,
        "identical_short_pcm24_pairs_rejected": True,
        "answer_key_bounded_single_read_snapshot_verified": True,
        "answer_key_slot_identities_and_levels_verified": True,
        "result_temp_fsynced_before_no_overwrite_publication": True,
        "result_published_by_no_overwrite_hard_link": True,
    }
    expected_limitations = {
        "execution_candidate_and_stitch_json_snapshot_held": False,
        "wav_descriptors_snapshot_held_across_verification": False,
        "non_snapshot_private_inputs_assumed_quiescent": True,
    }
    if (
        document.get("counts_by_kind_and_outcome") != counts
        or document.get("overall_outcome_counts") != overall
        or boundary_count < 1
        or edge_count != 2 * boundary_count
        or song_count != len(_FULL_SONG_ROLES)
        or document.get("readiness_evidence") != expected_readiness
        or document.get("interpretation") != expected_interpretation
        or document.get("verification_claims") != expected_claims
        or document.get("verification_limitations") != expected_limitations
    ):
        raise ValueError("full-song join-remediation review result differs")
    return loaded


def _validate_join_remediation_unit(unit: Any) -> tuple[str, str]:
    if (
        not isinstance(unit, Mapping)
        or set(unit) != _JOIN_REMEDIATION_UNIT_KEYS
        or not isinstance(unit.get("unit_id"), str)
        or not isinstance(unit.get("title"), str)
        or not unit["title"]
        or not isinstance(unit.get("focus"), str)
        or not unit["focus"]
        or not isinstance(unit.get("notes"), str)
        or len(unit["notes"]) > 1_000
        or unit.get("kind") not in _JOIN_REMEDIATION_KINDS
        or {unit.get("candidate_a_identity"), unit.get("candidate_b_identity")}
        != {"candidate", "raw"}
        or unit.get("blind_choice")
        not in {"A", "B", "equivalent", "neither", "cannot_tell"}
    ):
        raise ValueError("full-song join-remediation review unit differs")
    kind = str(unit["kind"])
    parsed_kind, _boundary_index, _role, _edge = _parse_join_remediation_unit_id(
        str(unit["unit_id"])
    )
    if parsed_kind != kind:
        raise ValueError("full-song join-remediation review unit set differs")
    window = unit.get("source_window")
    if kind == "complete_song_pair":
        if window is not None:
            raise ValueError("full-song join-remediation review unit differs")
    elif not _valid_join_remediation_window(window):
        raise ValueError("full-song join-remediation review unit differs")
    choice = str(unit["blind_choice"])
    resolved = (
        f"{unit[f'candidate_{choice.lower()}_identity']}_preferred"
        if choice in {"A", "B"}
        else choice
    )
    if (
        resolved not in _JOIN_REMEDIATION_OUTCOMES
        or unit.get("resolved_choice") != resolved
    ):
        raise ValueError("full-song join-remediation review unit differs")
    return kind, resolved


def _parse_join_remediation_unit_id(
    unit_id: str,
) -> tuple[str, int | None, str, str | None]:
    parts = unit_id.split("-")
    if len(parts) == 3 and parts[0] == "boundary":
        kind = "boundary_role_pair"
        boundary_token, role, edge = parts[1], parts[2], None
    elif len(parts) == 4 and parts[0] == "edge":
        kind = "patch_edge_pair"
        boundary_token, role, edge = parts[1], parts[2], parts[3]
        if edge not in {"start", "end"}:
            raise ValueError("full-song join-remediation review unit set differs")
    elif len(parts) == 3 and parts[:2] == ["complete", "song"]:
        role = parts[2]
        if role not in _FULL_SONG_ROLES:
            raise ValueError("full-song join-remediation review unit set differs")
        return "complete_song_pair", None, role, None
    else:
        raise ValueError("full-song join-remediation review unit set differs")
    if role not in {"vocals", "instrumental"}:
        raise ValueError("full-song join-remediation review unit set differs")
    try:
        boundary_index = int(boundary_token)
    except ValueError as error:
        raise ValueError(
            "full-song join-remediation review unit set differs"
        ) from error
    if boundary_index < 1 or boundary_token != f"{boundary_index:02d}":
        raise ValueError("full-song join-remediation review unit set differs")
    return kind, boundary_index, role, edge


def _valid_join_remediation_window(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "start_frame",
        "end_frame",
        "start_seconds",
        "end_seconds",
    }:
        return False
    start = value.get("start_frame")
    end = value.get("end_frame")
    return (
        type(start) is int
        and type(end) is int
        and 0 <= start < end
        and _finite_number(value.get("start_seconds"))
        and _finite_number(value.get("end_seconds"))
        and math.isclose(
            float(value["start_seconds"]),
            start / 44_100,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        )
        and math.isclose(
            float(value["end_seconds"]),
            end / 44_100,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        )
    )


def _valid_alignment_protocol(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    window_seconds = value.get("window_seconds")
    return (
        value.get("comparison") == "canonical source versus diagnostic reconstruction"
        and value.get("feature") == "log spectral-band energy"
        and value.get("window_count") == ALIGNMENT_WINDOW_COUNT
        and _finite_number(window_seconds)
        and 0.0 < float(window_seconds) <= 8.0
        and value.get("feature_frame_milliseconds")
        == ALIGNMENT_FEATURE_FRAME_MILLISECONDS
        and value.get("feature_hop_milliseconds") == ALIGNMENT_FEATURE_HOP_MILLISECONDS
        and value.get("maximum_search_lag_milliseconds")
        == MAXIMUM_SEARCH_LAG_MILLISECONDS
        and value.get("lag_sign")
        == "positive means reconstruction is later than source"
        and value.get("source_and_reconstruction_gain_normalized_for_timing") is True
    )


def _valid_alignment_thresholds(value: Any) -> bool:
    return value == {
        "minimum_active_rms_dbfs": MINIMUM_ACTIVE_RMS_DBFS,
        "minimum_eligible_window_count": ALIGNMENT_WINDOW_COUNT,
        "all_song_thirds_required": True,
        "maximum_absolute_lag_milliseconds": MAXIMUM_ACCEPTED_ABSOLUTE_LAG_MILLISECONDS,
        "maximum_lag_spread_milliseconds": MAXIMUM_ACCEPTED_LAG_SPREAD_MILLISECONDS,
        "minimum_window_normalized_correlation": MINIMUM_ACCEPTED_WINDOW_CORRELATION,
    }


def _valid_alignment_windows(
    value: Any,
    *,
    clock: Mapping[str, Any],
    protocol: Mapping[str, Any],
) -> bool:
    if not isinstance(value, list) or len(value) != ALIGNMENT_WINDOW_COUNT:
        return False
    sample_rate = clock["sample_rate"]
    total_frames = clock["frames"]
    expected_window_frames = int(round(protocol["window_seconds"] * sample_rate))
    available_frames = total_frames - expected_window_frames
    expected_starts = [
        int(round(available_frames * index / (ALIGNMENT_WINDOW_COUNT - 1)))
        for index in range(ALIGNMENT_WINDOW_COUNT)
    ]
    for index, window in enumerate(value, start=1):
        expected_third = "early" if index <= 3 else "middle" if index <= 6 else "late"
        if not isinstance(window, Mapping):
            return False
        start = window.get("start_frame")
        end = window.get("end_frame")
        correlation = window.get("peak_normalized_correlation")
        lag = window.get("best_lag_milliseconds")
        if (
            window.get("window_index") != index
            or window.get("song_third") != expected_third
            or type(start) is not int
            or type(end) is not int
            or start != expected_starts[index - 1]
            or start < 0
            or end - start != expected_window_frames
            or end > total_frames
            or not _finite_number(window.get("start_seconds"))
            or not _finite_number(window.get("end_seconds"))
            or abs(float(window["start_seconds"]) - start / sample_rate) > 1.0e-6
            or abs(float(window["end_seconds"]) - end / sample_rate) > 1.0e-6
            or not _finite_number(window.get("source_rms_dbfs"))
            or not _finite_number(window.get("reconstruction_rms_dbfs"))
            or type(window.get("eligible")) is not bool
        ):
            return False
        if window["eligible"]:
            if (
                not _finite_number(correlation)
                or not -1.0 <= float(correlation) <= 1.0
                or not _finite_number(lag)
                or abs(float(lag)) > MAXIMUM_SEARCH_LAG_MILLISECONDS
                or window["source_rms_dbfs"] < MINIMUM_ACTIVE_RMS_DBFS
                or window["reconstruction_rms_dbfs"] < MINIMUM_ACTIVE_RMS_DBFS
            ):
                return False
        elif (correlation is None) is not (lag is None):
            return False
        elif correlation is not None and (
            not _finite_number(correlation)
            or not -1.0 <= float(correlation) <= 1.0
            or not _finite_number(lag)
            or abs(float(lag)) > MAXIMUM_SEARCH_LAG_MILLISECONDS
        ):
            return False
    return True


def _valid_alignment_summary_and_readiness(
    summary: Any,
    *,
    readiness: Any,
    windows: list[Mapping[str, Any]],
    thresholds: Mapping[str, Any],
) -> bool:
    if not isinstance(summary, Mapping) or not isinstance(readiness, Mapping):
        return False
    eligible = [window for window in windows if window["eligible"]]
    lags = [float(window["best_lag_milliseconds"]) for window in eligible]
    correlations = [float(window["peak_normalized_correlation"]) for window in eligible]
    coverage_complete = len(eligible) == ALIGNMENT_WINDOW_COUNT and {
        window["song_third"] for window in eligible
    } == {"early", "middle", "late"}
    maximum_absolute_lag = max((abs(value) for value in lags), default=None)
    lag_spread = max(lags) - min(lags) if lags else None
    minimum_correlation = min(correlations, default=-1.0)
    gate_passed = (
        coverage_complete
        and maximum_absolute_lag is not None
        and maximum_absolute_lag <= thresholds["maximum_absolute_lag_milliseconds"]
        and lag_spread is not None
        and lag_spread <= thresholds["maximum_lag_spread_milliseconds"]
        and minimum_correlation >= thresholds["minimum_window_normalized_correlation"]
    )
    expected_summary = {
        "eligible_window_count": len(eligible),
        "maximum_absolute_lag_milliseconds": maximum_absolute_lag,
        "lag_spread_milliseconds": lag_spread,
        "minimum_window_normalized_correlation": round(minimum_correlation, 6),
        "early_middle_late_coverage_complete": coverage_complete,
    }
    expected_readiness = {
        "exact_source_and_reconstruction_clock_verified": True,
        "source_to_reconstruction_alignment_verified": gate_passed,
        "drift_acceptance_complete": gate_passed,
        "alignment_gate_passed": gate_passed,
        "separator_accuracy_established": False,
        "publication_ready": False,
    }
    return summary == expected_summary and readiness == expected_readiness


def _require_alignment_bound_to_full_song_review(
    alignment: _LoadedJson,
    review: _LoadedJson,
) -> None:
    alignment_bindings = alignment.document["bindings"]
    review_bindings = review.document["bindings"]
    if (
        alignment_bindings["stitch_report_sha256"]
        != review_bindings["stitch_report_sha256"]
        or alignment_bindings["stitch_document_sha256"]
        != review_bindings["stitch_document_sha256"]
        or alignment_bindings["plan_document_sha256"]
        != review_bindings["plan_document_sha256"]
        or alignment_bindings["execution_state_sha256"]
        != review_bindings["execution_state_sha256"]
        or alignment.document["clock"] != review.document["clock"]
    ):
        raise ValueError("full-song alignment binding differs from review")


def _require_join_remediation_bound_to_full_song_review(
    remediation: _LoadedJson,
    review: _LoadedJson,
) -> None:
    remediation_bindings = remediation.document["bindings"]
    review_bindings = review.document["bindings"]
    if (
        remediation_bindings["stitch_report_sha256"]
        != review_bindings["stitch_report_sha256"]
        or remediation_bindings["stitch_document_sha256"]
        != review_bindings["stitch_document_sha256"]
    ):
        raise ValueError(
            "full-song join-remediation binding differs from original review"
        )

    clock = review.document["clock"]
    if clock["sample_rate"] != JOIN_REMEDIATION_SAMPLE_RATE:
        raise ValueError("full-song join-remediation clock differs from review policy")
    total_frames = clock["frames"]

    expected_pairs = {
        (boundary["boundary_index"], role): boundary["frame"]
        for boundary in review.document["boundaries"]
        for role in ("vocals", "instrumental")
        if boundary["ratings"][role] == "audible_join"
    }
    units = remediation.document["units"]
    observed_pairs: dict[tuple[int, str], Mapping[str, Any]] = {}
    observed_edges: set[tuple[int, str, str]] = set()
    complete_roles: set[str] = set()
    for unit in units:
        kind, boundary_index, role, edge = _parse_join_remediation_unit_id(
            unit["unit_id"]
        )
        if kind == "boundary_role_pair":
            assert boundary_index is not None
            observed_pairs[(boundary_index, role)] = unit
        elif kind == "patch_edge_pair":
            assert boundary_index is not None and edge is not None
            observed_edges.add((boundary_index, role, edge))
        else:
            complete_roles.add(role)
    expected_edges = {
        (boundary_index, role, edge)
        for boundary_index, role in expected_pairs
        for edge in ("start", "end")
    }
    if (
        set(observed_pairs) != set(expected_pairs)
        or observed_edges != expected_edges
        or complete_roles != set(_FULL_SONG_ROLES)
    ):
        raise ValueError(
            "full-song join-remediation unit set differs from original audible joins"
        )
    for key, unit in observed_pairs.items():
        window = unit["source_window"]
        boundary_frame = expected_pairs[key]
        expected_boundary_window = _join_remediation_window(
            centre_frame=boundary_frame,
            half_frames=2 * JOIN_REMEDIATION_SAMPLE_RATE,
            total_frames=total_frames,
        )
        expected_start_edge_window = _join_remediation_window(
            centre_frame=boundary_frame - JOIN_REMEDIATION_SAMPLE_RATE,
            half_frames=JOIN_REMEDIATION_SAMPLE_RATE,
            total_frames=total_frames,
        )
        expected_end_edge_window = _join_remediation_window(
            centre_frame=boundary_frame + JOIN_REMEDIATION_SAMPLE_RATE,
            half_frames=JOIN_REMEDIATION_SAMPLE_RATE,
            total_frames=total_frames,
        )
        if window != expected_boundary_window:
            raise ValueError(
                "full-song join-remediation window differs from original review"
            )
        start_edge = next(
            item
            for item in units
            if item["unit_id"] == f"edge-{key[0]:02d}-{key[1]}-start"
        )
        end_edge = next(
            item
            for item in units
            if item["unit_id"] == f"edge-{key[0]:02d}-{key[1]}-end"
        )
        if (
            start_edge["source_window"] != expected_start_edge_window
            or end_edge["source_window"] != expected_end_edge_window
        ):
            raise ValueError(
                "full-song join-remediation window differs from original review"
            )


def _join_remediation_window(
    *, centre_frame: int, half_frames: int, total_frames: int
) -> dict[str, int | float]:
    start = max(0, centre_frame - half_frames)
    end = min(total_frames, centre_frame + half_frames)
    return {
        "start_frame": start,
        "end_frame": end,
        "start_seconds": start / JOIN_REMEDIATION_SAMPLE_RATE,
        "end_seconds": end / JOIN_REMEDIATION_SAMPLE_RATE,
    }


def _valid_full_song_clock(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "boundary_count",
        "channels",
        "chunk_count",
        "crossfade_frames",
        "duration_seconds",
        "frames",
        "gap_frames",
        "overlap_frames",
        "sample_rate",
    }:
        return False
    integer_fields = (
        "boundary_count",
        "channels",
        "chunk_count",
        "crossfade_frames",
        "frames",
        "gap_frames",
        "overlap_frames",
        "sample_rate",
    )
    if any(type(value.get(field)) is not int for field in integer_fields):
        return False
    duration = value.get("duration_seconds")
    return (
        value["boundary_count"] >= 1
        and value["chunk_count"] == value["boundary_count"] + 1
        and value["frames"] > 0
        and value["sample_rate"] > 0
        and value.get("channels") in {1, 2}
        and value.get("crossfade_frames") == 0
        and value.get("gap_frames") == 0
        and value.get("overlap_frames") == 0
        and isinstance(duration, (int, float))
        and not isinstance(duration, bool)
        and duration > 0
        and math.isclose(
            duration,
            value["frames"] / value["sample_rate"],
            rel_tol=0.0,
            abs_tol=1e-9,
        )
    )


def _valid_full_song_ratings(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"heard_all", "ratings", "notes"}
        and value.get("heard_all") is True
        and isinstance(value.get("ratings"), Mapping)
        and set(value["ratings"]) == set(_FULL_SONG_ROLES)
        and all(rating in _FULL_SONG_RATINGS for rating in value["ratings"].values())
        and isinstance(value.get("notes"), str)
        and len(value["notes"]) <= _MAXIMUM_NOTES_CHARACTERS
    )


def _valid_full_song_boundaries(
    values: list[Any],
    *,
    boundary_count: int,
    sample_rate: int,
    total_frames: int,
) -> bool:
    previous_frame = 0
    for expected_index, item in enumerate(values, start=1):
        if (
            not isinstance(item, Mapping)
            or set(item) != {"boundary_index", "frame", "seconds", "ratings", "notes"}
            or type(item.get("boundary_index")) is not int
            or item.get("boundary_index") != expected_index
            or type(item.get("frame")) is not int
            or not previous_frame < item["frame"] < total_frames
            or not isinstance(item.get("seconds"), (int, float))
            or isinstance(item.get("seconds"), bool)
            or not math.isclose(
                item["seconds"],
                item["frame"] / sample_rate,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            or not isinstance(item.get("ratings"), Mapping)
            or set(item["ratings"]) != set(_FULL_SONG_ROLES)
            or any(
                rating not in _BOUNDARY_RATINGS for rating in item["ratings"].values()
            )
            or not isinstance(item.get("notes"), str)
            or len(item["notes"]) > _MAXIMUM_NOTES_CHARACTERS
        ):
            return False
        previous_frame = item["frame"]
    return len(values) == boundary_count


def _valid_full_song_boundary_summary(
    value: Any,
    *,
    boundaries: list[Any],
    boundary_count: int,
) -> bool:
    if (
        not isinstance(value, Mapping)
        or set(value)
        != {
            "reviewed_boundaries",
            "rating_counts_by_role",
            "audible_join_boundaries_by_role",
        }
        or value.get("reviewed_boundaries") != boundary_count
        or not isinstance(value.get("rating_counts_by_role"), Mapping)
        or set(value["rating_counts_by_role"]) != set(_FULL_SONG_ROLES)
        or not isinstance(value.get("audible_join_boundaries_by_role"), Mapping)
        or set(value["audible_join_boundaries_by_role"]) != set(_FULL_SONG_ROLES)
    ):
        return False
    for role in _FULL_SONG_ROLES:
        counts = value["rating_counts_by_role"][role]
        joins = value["audible_join_boundaries_by_role"][role]
        observed_counts = {rating: 0 for rating in sorted(_BOUNDARY_RATINGS)}
        observed_joins = []
        for boundary in boundaries:
            rating = boundary["ratings"][role]
            observed_counts[rating] += 1
            if rating == "audible_join":
                observed_joins.append(boundary["boundary_index"])
        if (
            not isinstance(counts, Mapping)
            or set(counts) != _BOUNDARY_RATINGS
            or any(type(counts.get(rating)) is not int for rating in _BOUNDARY_RATINGS)
            or any(counts[rating] < 0 for rating in _BOUNDARY_RATINGS)
            or dict(counts) != observed_counts
            or not isinstance(joins, list)
            or any(type(index) is not int for index in joins)
            or joins != observed_joins
        ):
            return False
    return True


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


def _valid_resource_aggregate(value: Mapping[str, Any], *, expected_count: int) -> bool:
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
        or inputs.get("normalized_midi_agreement_sha256") != agreement.file_sha256
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
    full_song_review: _LoadedJson | None,
    full_song_alignment: _LoadedJson | None,
    join_remediation_review: _LoadedJson | None,
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
    full_song_assessment = (
        _assess_full_song_review(full_song_review.document)
        if full_song_review is not None
        else None
    )
    alignment_assessment = (
        _assess_full_song_alignment(full_song_alignment.document)
        if full_song_alignment is not None
        else None
    )
    join_remediation_assessment = (
        _assess_join_remediation_review(join_remediation_review.document)
        if join_remediation_review is not None
        else None
    )
    if full_song_assessment is not None and alignment_assessment is not None:
        combined_gate_passed = (
            full_song_assessment["review_minimum_met"]
            and alignment_assessment["gate_passed"]
        )
        full_song_assessment.update(
            {
                "source_to_output_alignment_verified": alignment_assessment[
                    "source_to_reconstruction_alignment_verified"
                ],
                "drift_acceptance_complete": alignment_assessment[
                    "drift_acceptance_complete"
                ],
                "gate_passed": combined_gate_passed,
                "acceptance_gate_closed": combined_gate_passed,
            }
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
    full_song_gate = _gate(
        "full_song_duration_and_alignment",
        (
            "passed"
            if full_song_assessment and full_song_assessment["gate_passed"]
            else "open"
        ),
        (
            "The exact clock, complete-song listening minimum, clean role boundaries and source-to-reconstruction alignment/drift thresholds were all verified for this one owner-reviewed song."
            if full_song_assessment and full_song_assessment["gate_passed"]
            else (
                (
                    "The original full-song review still contains audible joins. "
                    "The bound targeted-remediation review found "
                    f"{join_remediation_assessment['candidate_preferred_boundary_role_count']} "
                    "candidate-preferred and "
                    f"{join_remediation_assessment['equivalent_boundary_role_count']} "
                    "equivalent boundary-role pairs"
                    + (
                        " with no raw-preferred, neither or cannot-tell outcome, but "
                        if join_remediation_assessment["no_heard_regression"]
                        else " and one or more non-safe outcomes, while "
                    )
                    + "comparative preference is not an absolute clean-boundary rating "
                    "and cannot replace a new candidate-bound full-song review."
                )
                if join_remediation_assessment is not None
                else "The full-song listening minimum was verified, but synchronized source-to-reconstruction alignment and drift evidence are still missing or outside the declared thresholds."
                if full_song_assessment and full_song_assessment["review_minimum_met"]
                else (
                    "Automated alignment passed, but exact full-song listening still requires every generated role to be useful and every role-boundary judgement to be clean."
                    if alignment_assessment and alignment_assessment["gate_passed"]
                    else (
                        "Exact duration and complete listening were verified, but the predeclared minimum requires every generated complete-song role to be useful and every role-boundary judgement to be clean."
                        if full_song_assessment
                        else "Bounded excerpts do not prove full-song quality, clock alignment or drift."
                    )
                )
            )
        ),
    )
    if full_song_gate["status"] == "passed":
        passed.append(full_song_gate)
        full_song_open_gates: list[dict[str, str]] = []
    else:
        full_song_open_gates = [full_song_gate]
    open_gates = (
        audio_open_gates
        + full_song_open_gates
        + [
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
    )
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
    if full_song_review is not None:
        inputs.update(
            {
                "full_song_review_result_sha256": full_song_review.file_sha256,
                "full_song_review_result_document_sha256": full_song_review.document[
                    "document_sha256"
                ],
            }
        )
    if full_song_alignment is not None:
        inputs.update(
            {
                "full_song_alignment_result_sha256": full_song_alignment.file_sha256,
                "full_song_alignment_result_document_sha256": full_song_alignment.document[
                    "document_sha256"
                ],
            }
        )
    if join_remediation_review is not None:
        inputs.update(
            {
                "full_song_join_remediation_review_result_sha256": (
                    join_remediation_review.file_sha256
                ),
                "full_song_join_remediation_review_result_document_sha256": (
                    join_remediation_review.document["document_sha256"]
                ),
            }
        )
    document = {
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
            "duration_scope": (
                "bounded_authorised_excerpts_plus_one_full_song"
                if full_song_assessment
                else "bounded_authorised_excerpts"
            ),
            "separated_audio_reviewed_track_count": (
                audio_assessment["reviewed_track_count"] if audio_assessment else 0
            ),
            "full_song_reviewed": full_song_assessment is not None,
            "full_song_review_duration_seconds": (
                full_song_assessment["duration_seconds"]
                if full_song_assessment
                else None
            ),
            "full_song_review_role_scope": (
                list(_FULL_SONG_ROLES) if full_song_assessment else []
            ),
            "full_song_alignment_measured": alignment_assessment is not None,
            "full_song_alignment_window_count": (
                alignment_assessment["window_count"] if alignment_assessment else 0
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
        "full_song_duration_alignment_assessment": full_song_assessment,
        "full_song_alignment_assessment": alignment_assessment,
        "interpretation": {
            "private_separator_derived_midi_has_useful_evidence": True,
            "general_finished_song_separation_is_working": False,
            "midi_agreement_is_audio_separation_quality": False,
            "human_usefulness_is_accuracy": False,
            "passed_gate_is_separator_selection": False,
            "open_gate_can_be_inferred_from_other_evidence": False,
            "provider_preference_is_separator_selection": False,
            "development_resource_thresholds_are_resource_acceptance": False,
            "full_song_review_completion_is_quality_acceptance": False,
            "full_song_gate_pass_is_separator_acceptance": False,
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
            "full_song_minimum_policy_predeclared": True,
            "full_song_review_can_select_or_accept_separator": False,
            "full_song_review_can_close_duration_alignment_gate": False,
            "alignment_result_alone_can_close_duration_alignment_gate": False,
            "matching_review_and_alignment_can_close_duration_alignment_gate": True,
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
            "One owner-reviewed full song plus a matching alignment result can close only the duration/alignment milestone; it cannot establish broad-role, hidden-set or general separator quality.",
        ],
    }
    if join_remediation_assessment is not None:
        document["observed_scope"].update(
            {
                "full_song_join_remediation_reviewed": True,
                "full_song_join_remediation_reviewed_unit_count": (
                    join_remediation_assessment["reviewed_unit_count"]
                ),
            }
        )
        document["full_song_join_remediation_assessment"] = join_remediation_assessment
        document["interpretation"][
            "join_remediation_preference_is_absolute_boundary_cleanliness"
        ] = False
        document["policy"][
            "join_remediation_review_can_close_duration_alignment_gate"
        ] = False
        document["limitations"].append(
            "A targeted raw-versus-candidate remediation preference is "
            "supplementary directional evidence; only a new candidate-bound "
            "full-song review can replace the original boundary ratings."
        )
    return document


def _assess_join_remediation_review(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    boundary_units = [
        unit for unit in document["units"] if unit["kind"] == "boundary_role_pair"
    ]
    candidate_preferred: dict[str, list[int]] = {
        "vocals": [],
        "instrumental": [],
    }
    improvement_not_evidenced: dict[str, list[int]] = {
        "vocals": [],
        "instrumental": [],
    }
    for unit in boundary_units:
        _kind, boundary_index, role, _edge = _parse_join_remediation_unit_id(
            unit["unit_id"]
        )
        assert boundary_index is not None
        target = (
            candidate_preferred
            if unit["resolved_choice"] == "candidate_preferred"
            else improvement_not_evidenced
        )
        target[role].append(boundary_index)
    for values in (*candidate_preferred.values(), *improvement_not_evidenced.values()):
        values.sort()

    boundary_counts = document["counts_by_kind_and_outcome"]["boundary_role_pair"]
    edge_counts = document["counts_by_kind_and_outcome"]["patch_edge_pair"]
    song_counts = document["counts_by_kind_and_outcome"]["complete_song_pair"]
    no_heard_regression = all(
        document["overall_outcome_counts"][outcome] == 0
        for outcome in ("raw_preferred", "neither", "cannot_tell")
    )
    return {
        "policy_id": document["policy_id"],
        "reviewed_unit_count": document["reviewed_unit_count"],
        "human_join_remediation_review_complete": True,
        "boundary_role_outcome_counts": dict(boundary_counts),
        "patch_edge_outcome_counts": dict(edge_counts),
        "complete_song_outcome_counts": dict(song_counts),
        "candidate_preferred_boundary_role_count": boundary_counts[
            "candidate_preferred"
        ],
        "equivalent_boundary_role_count": boundary_counts["equivalent"],
        "candidate_preferred_boundaries_by_role": candidate_preferred,
        "improvement_not_evidenced_boundaries_by_role": improvement_not_evidenced,
        "no_heard_regression": no_heard_regression,
        "non_safe_outcome_count": sum(
            document["overall_outcome_counts"][outcome]
            for outcome in ("raw_preferred", "neither", "cannot_tell")
        ),
        "all_patch_edges_candidate_or_equivalent": document["readiness_evidence"][
            "all_patch_edges_candidate_or_equivalent"
        ],
        "all_complete_songs_candidate_or_equivalent": document["readiness_evidence"][
            "all_complete_songs_candidate_or_equivalent"
        ],
        "absolute_boundary_cleanliness_established": False,
        "original_audible_joins_resolved": False,
        "can_close_duration_alignment_gate": False,
        "separator_accepted": False,
    }


def _assess_full_song_review(document: Mapping[str, Any]) -> dict[str, Any]:
    clock = document["clock"]
    full_song_ratings = document["full_song"]["ratings"]
    summary = document["boundary_summary"]
    rating_counts = summary["rating_counts_by_role"]
    audible_joins = summary["audible_join_boundaries_by_role"]
    all_outputs_useful = all(
        full_song_ratings[role] == "useful" for role in _FULL_SONG_ROLES
    )
    all_boundaries_clean = all(
        rating_counts[role]["clean"] == clock["boundary_count"]
        and rating_counts[role]["audible_join"] == 0
        and rating_counts[role]["cannot_tell"] == 0
        for role in _FULL_SONG_ROLES
    )
    return {
        "duration_seconds": clock["duration_seconds"],
        "frames": clock["frames"],
        "sample_rate": clock["sample_rate"],
        "channels": clock["channels"],
        "chunk_count": clock["chunk_count"],
        "boundary_count": clock["boundary_count"],
        "reviewed_boundaries": summary["reviewed_boundaries"],
        "full_song_ratings_by_role": {
            role: full_song_ratings[role] for role in _FULL_SONG_ROLES
        },
        "boundary_rating_counts_by_role": {
            role: {
                rating: rating_counts[role][rating]
                for rating in sorted(_BOUNDARY_RATINGS)
            }
            for role in _FULL_SONG_ROLES
        },
        "audible_join_boundaries_by_role": {
            role: list(audible_joins[role]) for role in _FULL_SONG_ROLES
        },
        "exact_duration_and_frame_count_verified": True,
        "full_song_and_boundary_listening_complete": True,
        "all_full_song_outputs_useful": all_outputs_useful,
        "all_role_boundaries_clean": all_boundaries_clean,
        "requirements": {
            "full_song_rating_for_every_generated_role": "useful",
            "boundary_rating_for_every_generated_role": "clean",
            "exact_duration_and_frame_count_required": True,
            "complete_full_song_and_boundary_listening_required": True,
            "review_notes_affect_gate": False,
        },
        "review_minimum_met": all_outputs_useful and all_boundaries_clean,
        "source_to_output_alignment_verified": False,
        "drift_acceptance_complete": False,
        "gate_passed": False,
        "acceptance_gate_closed": False,
        "separator_accepted": False,
    }


def _assess_full_song_alignment(document: Mapping[str, Any]) -> dict[str, Any]:
    summary = document["summary"]
    readiness = document["readiness"]
    return {
        "policy_id": document["policy_id"],
        "window_count": len(document["windows"]),
        "eligible_window_count": summary["eligible_window_count"],
        "early_middle_late_coverage_complete": summary[
            "early_middle_late_coverage_complete"
        ],
        "maximum_absolute_lag_milliseconds": summary[
            "maximum_absolute_lag_milliseconds"
        ],
        "lag_spread_milliseconds": summary["lag_spread_milliseconds"],
        "minimum_window_normalized_correlation": summary[
            "minimum_window_normalized_correlation"
        ],
        "source_to_reconstruction_alignment_verified": readiness[
            "source_to_reconstruction_alignment_verified"
        ],
        "drift_acceptance_complete": readiness["drift_acceptance_complete"],
        "gate_passed": readiness["alignment_gate_passed"],
        "separator_accuracy_established": False,
        "separator_accepted": False,
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
        "controlled_repetitions_observed": coverage["controlled_repetitions_observed"],
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
    path = Path(value).expanduser().absolute()
    if path.suffix.lower() != ".json":
        raise ValueError(f"{label} must be a non-empty regular JSON file")
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise ValueError(f"{label} cannot be opened without link protection")
    flags = os.O_RDONLY | no_follow | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ValueError(f"{label} must be a non-empty regular JSON file") from error
    try:
        os.set_inheritable(descriptor, False)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size <= 0
            or before.st_size > _MAXIMUM_REPORT_BYTES
        ):
            raise ValueError(
                f"{label} must be a non-empty regular JSON file no larger than "
                f"{_MAXIMUM_REPORT_BYTES} bytes"
            )
        contents = bytearray()
        while len(contents) <= _MAXIMUM_REPORT_BYTES:
            chunk = os.read(
                descriptor,
                min(64 * 1024, _MAXIMUM_REPORT_BYTES + 1 - len(contents)),
            )
            if not chunk:
                break
            contents.extend(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    payload = bytes(contents)
    if (
        _snapshot_identity(before) != _snapshot_identity(after)
        or len(payload) != before.st_size
        or len(payload) > _MAXIMUM_REPORT_BYTES
    ):
        raise ValueError(f"{label} changed while it was being read")
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid JSON") from error
    if not isinstance(document, dict):
        raise ValueError(f"{label} must be a JSON object")
    return _LoadedJson(
        path=path,
        file_sha256=hashlib.sha256(payload).hexdigest(),
        document=document,
    )


def _snapshot_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


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


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _reverify(
    agreement: _LoadedJson,
    listening: _LoadedJson,
    audio_quality: _LoadedJson | None,
    resource_benchmark: _LoadedJson | None,
    full_song_review: _LoadedJson | None,
    full_song_alignment: _LoadedJson | None,
    join_remediation_review: _LoadedJson | None,
) -> None:
    _require_unchanged(agreement, "normalized MIDI agreement")
    _require_unchanged(listening, "human-listening coverage")
    if audio_quality is not None:
        _require_unchanged(audio_quality, "separated-audio quality")
    if resource_benchmark is not None:
        _require_unchanged(resource_benchmark, "resource benchmark result")
    if full_song_review is not None:
        _require_unchanged(full_song_review, "full-song review result")
    if full_song_alignment is not None:
        _require_unchanged(full_song_alignment, "full-song alignment result")
    if join_remediation_review is not None:
        _require_unchanged(
            join_remediation_review,
            "full-song join-remediation review result",
        )


def _require_unchanged(loaded: _LoadedJson, label: str) -> None:
    current = _load_json(loaded.path, label)
    if current.file_sha256 != loaded.file_sha256:
        raise ValueError(f"{label} changed during projection")


__all__ = [
    "AUDIO_MINIMUM_POLICY_ID",
    "SCHEMA",
    "_project_private_separation_publication_readiness",
]
