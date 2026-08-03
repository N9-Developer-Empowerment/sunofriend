"""Coverage shape for one sealed private separation evidence index.

This report answers whether like-for-like cross-song or cross-method cells
exist. It does not read report bodies, normalize metrics, score a method or
turn coverage into acceptance.
"""

from __future__ import annotations

from itertools import combinations
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from ._separation_authorised_midi_comparison import (
    _document_sha256,
    _regular_json,
    _sha256,
)
from ._separation_cross_song_evidence_index import (
    SCHEMA as INDEX_SCHEMA,
    _ID_PATTERN,
    _MAXIMUM_ENTRIES,
    _MINIMUM_ENTRIES,
    _SCHEMA_BY_KIND,
)
from ._separation_vocal_candidate_audition import _write_fresh_private_json


SCHEMA = "sunofriend.private-separation-corpus-coverage.v1"
_MAX_INDEX_BYTES = 1024 * 1024
_HEX_DIGITS = frozenset("0123456789abcdef")
_ENTRY_KEYS = frozenset(
    {
        "track_id",
        "method_family",
        "evidence_kind",
        "report_schema",
        "report_sha256",
        "report_document_sha256",
        "report_bytes",
        "status",
    }
)


def _assess_private_separation_corpus_coverage(
    evidence_index_path: str | Path,
    *,
    out: str | Path,
) -> dict[str, Any]:
    """Describe the index's comparison topology without comparing metrics."""

    index_path, index_file_sha256, index = _load_index(evidence_index_path)
    document = _build_document(
        index=index,
        index_file_sha256=index_file_sha256,
    )
    document["document_sha256"] = _document_sha256(document)
    if _sha256(index_path) != index_file_sha256:
        raise ValueError("private separation evidence index changed during assessment")
    _write_fresh_private_json(Path(out), document)
    document["report"] = str(Path(out).expanduser().absolute())
    return document


def _load_index(path: str | Path) -> tuple[Path, str, dict[str, Any]]:
    index_path = _regular_json(path, "private separation evidence index")
    if index_path.stat().st_size > _MAX_INDEX_BYTES:
        raise ValueError("private separation evidence index is too large")
    file_sha256 = _sha256(index_path)
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(
            "private separation evidence index is not valid JSON"
        ) from error
    if (
        not isinstance(index, dict)
        or index.get("schema") != INDEX_SCHEMA
        or index.get("status") != "complete_catalogue_not_comparison_or_acceptance"
        or index.get("evidence_scope") != "private_development_only"
        or index.get("document_sha256") != _document_sha256(index)
    ):
        raise ValueError("private separation evidence index contract differs")
    _validate_inactive_index(index)
    _validate_entries_and_summary(index)
    return index_path, file_sha256, index


def _validate_inactive_index(index: Mapping[str, Any]) -> None:
    policy = index.get("policy")
    permissions = index.get("permissions")
    effects = index.get("effects")
    if (
        not isinstance(policy, Mapping)
        or not isinstance(permissions, Mapping)
        or not permissions
        or not isinstance(effects, Mapping)
        or not effects
    ):
        raise ValueError("private separation evidence index policy differs")
    required_policy = {
        "identifiers_are_caller_declared": True,
        "source_reports_self_hash_verified": True,
        "source_report_files_hash_verified": True,
        "heterogeneous_metrics_normalized": False,
        "metrics_compared_across_schemas": False,
        "cross_song_acceptance_evaluated": False,
        "method_ranked_or_selected": False,
        "automatic_selection": False,
        "automatic_promotion": False,
        "production_eligible": False,
        "public_result": False,
    }
    if any(policy.get(key) is not value for key, value in required_policy.items()):
        raise ValueError("private separation evidence index policy differs")
    if any(value is not False for value in permissions.values()):
        raise ValueError("private separation evidence index grants a permission")
    if any(value is not False for value in effects.values()):
        raise ValueError("private separation evidence index records an active effect")


def _validate_entries_and_summary(index: Mapping[str, Any]) -> None:
    entries = index.get("entries")
    summary = index.get("summary")
    if (
        not isinstance(entries, list)
        or not _MINIMUM_ENTRIES <= len(entries) <= _MAXIMUM_ENTRIES
        or not isinstance(summary, Mapping)
    ):
        raise ValueError("private separation evidence index entry count differs")
    identities: set[tuple[str, str, str]] = set()
    report_hashes: set[str] = set()
    document_hashes: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping) or frozenset(entry) != _ENTRY_KEYS:
            raise ValueError("private separation evidence index entry shape differs")
        track_id = _safe_id(entry.get("track_id"), "track ID")
        method_family = _safe_id(entry.get("method_family"), "method-family ID")
        evidence_kind = entry.get("evidence_kind")
        report_schema = entry.get("report_schema")
        if (
            not isinstance(evidence_kind, str)
            or _SCHEMA_BY_KIND.get(evidence_kind) != report_schema
            or entry.get("status") != "complete_observation_not_acceptance"
            or not _sha256_value(entry.get("report_sha256"))
            or not _sha256_value(entry.get("report_document_sha256"))
            or isinstance(entry.get("report_bytes"), bool)
            or not isinstance(entry.get("report_bytes"), int)
            or not 0 < int(entry["report_bytes"]) <= 2 * 1024 * 1024
        ):
            raise ValueError("private separation evidence index entry differs")
        identity = (track_id, method_family, evidence_kind)
        if (
            identity in identities
            or str(entry["report_sha256"]) in report_hashes
            or str(entry["report_document_sha256"]) in document_hashes
        ):
            raise ValueError("private separation evidence index duplicates evidence")
        identities.add(identity)
        report_hashes.add(str(entry["report_sha256"]))
        document_hashes.add(str(entry["report_document_sha256"]))
    ordered = sorted(
        entries,
        key=lambda entry: (
            entry["track_id"],
            entry["method_family"],
            entry["evidence_kind"],
            entry["report_sha256"],
        ),
    )
    if entries != ordered:
        raise ValueError("private separation evidence index order differs")
    expected_summary = {
        "entry_count": len(entries),
        "track_count": len({entry["track_id"] for entry in entries}),
        "method_family_count": len({entry["method_family"] for entry in entries}),
        "evidence_kind_counts": _counts(entries, "evidence_kind"),
        "report_schema_counts": _counts(entries, "report_schema"),
    }
    if dict(summary) != expected_summary:
        raise ValueError("private separation evidence index summary differs")


def _build_document(
    *,
    index: Mapping[str, Any],
    index_file_sha256: str,
) -> dict[str, Any]:
    entries = tuple(index["entries"])
    groups = _coverage_groups(entries)
    cross_song_group_count = sum(1 for group in groups if group["cross_song_repeat"])
    multi_method_group_count = sum(
        1 for group in groups if group["multi_method_repeat"]
    )
    paired_track_count = sum(
        int(group["paired_cross_method_track_count"]) for group in groups
    )
    rectangle_count = sum(
        int(group["complete_two_track_two_method_rectangle_count"]) for group in groups
    )
    unresolved = [
        "normalized_metric_contract_not_present",
        "hidden_test_set_not_represented",
        "checkpoint_licensing_not_evaluated",
        "human_listening_not_evaluated",
        "offline_and_resource_acceptance_not_evaluated",
    ]
    if cross_song_group_count == 0:
        unresolved.insert(0, "no_same_schema_cross_song_repeat")
    if multi_method_group_count == 0:
        unresolved.insert(0, "no_same_schema_cross_method_pair")
    if rectangle_count == 0:
        unresolved.insert(0, "no_same_schema_cross_song_multi_method_rectangle")
    return {
        "schema": SCHEMA,
        "status": "complete_coverage_observation_not_comparison_or_acceptance",
        "evidence_scope": "private_development_only",
        "inputs": {
            "evidence_index_schema": INDEX_SCHEMA,
            "evidence_index_sha256": index_file_sha256,
            "evidence_index_document_sha256": index["document_sha256"],
        },
        "catalogue_summary": dict(index["summary"]),
        "coverage_groups": groups,
        "coverage_summary": {
            "group_count": len(groups),
            "same_schema_cross_song_group_count": cross_song_group_count,
            "same_schema_multi_method_group_count": multi_method_group_count,
            "paired_cross_method_track_count": paired_track_count,
            "complete_two_track_two_method_rectangle_count": rectangle_count,
            "normalized_metric_contract_count": 0,
        },
        "publication_gate": {
            "status": "open",
            "cross_method_quality_comparison_ready": False,
            "unresolved_or_out_of_scope": unresolved,
        },
        "policy": {
            "coverage_only": True,
            "identifiers_are_caller_declared": True,
            "report_bodies_read": False,
            "heterogeneous_metrics_normalized": False,
            "metrics_compared": False,
            "method_ranked_or_selected": False,
            "cross_song_acceptance_evaluated": False,
            "automatic_selection": False,
            "automatic_promotion": False,
            "production_eligible": False,
            "public_result": False,
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
            "report_content_copied": False,
            "source_graph_mutated": False,
        },
        "limitations": [
            "Coverage cells show only caller-declared track and method labels bound to sealed report identities.",
            "A shared evidence kind and schema establishes a common report contract, not comparable musical quality metrics.",
            "A cross-song repeat, cross-method pair or complete rectangle is topology evidence only and cannot rank a method.",
            "This report does not read source report bodies or evaluate audio, MIDI, listening decisions, licensing, offline operation or resources.",
            "The publication gate remains open even if a future complete rectangle exists until a separate normalized metric and acceptance contract is reviewed.",
        ],
    }


def _coverage_groups(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for entry in entries:
        key = (str(entry["evidence_kind"]), str(entry["report_schema"]))
        grouped.setdefault(key, []).append(entry)
    result = []
    for (evidence_kind, report_schema), rows in sorted(grouped.items()):
        tracks = sorted({str(row["track_id"]) for row in rows})
        methods = sorted({str(row["method_family"]) for row in rows})
        methods_by_track = {
            track: {
                str(row["method_family"]) for row in rows if row["track_id"] == track
            }
            for track in tracks
        }
        tracks_by_method = {
            method: {
                str(row["track_id"]) for row in rows if row["method_family"] == method
            }
            for method in methods
        }
        paired_track_count = sum(
            1 for values in methods_by_track.values() if len(values) >= 2
        )
        repeated_method_count = sum(
            1 for values in tracks_by_method.values() if len(values) >= 2
        )
        rectangle_count = sum(
            len(methods_by_track[left] & methods_by_track[right])
            * (len(methods_by_track[left] & methods_by_track[right]) - 1)
            // 2
            for left, right in combinations(tracks, 2)
        )
        cross_song = len(tracks) >= 2
        multi_method = len(methods) >= 2
        result.append(
            {
                "evidence_kind": evidence_kind,
                "report_schema": report_schema,
                "entry_count": len(rows),
                "track_count": len(tracks),
                "method_family_count": len(methods),
                "cells": [
                    {
                        "track_id": str(row["track_id"]),
                        "method_family": str(row["method_family"]),
                    }
                    for row in sorted(
                        rows,
                        key=lambda row: (row["track_id"], row["method_family"]),
                    )
                ],
                "cross_song_repeat": cross_song,
                "multi_method_repeat": multi_method,
                "paired_cross_method_track_count": paired_track_count,
                "repeated_cross_song_method_count": repeated_method_count,
                "complete_two_track_two_method_rectangle_count": rectangle_count,
                "coverage_shape": _coverage_shape(
                    cross_song=cross_song,
                    multi_method=multi_method,
                    paired_track_count=paired_track_count,
                    repeated_method_count=repeated_method_count,
                    rectangle_count=rectangle_count,
                ),
                "metric_comparison_permitted": False,
            }
        )
    return result


def _coverage_shape(
    *,
    cross_song: bool,
    multi_method: bool,
    paired_track_count: int,
    repeated_method_count: int,
    rectangle_count: int,
) -> str:
    if rectangle_count:
        return "cross_song_multi_method_rectangle_unscored"
    if cross_song and multi_method and paired_track_count and repeated_method_count:
        return "cross_song_and_paired_without_rectangle"
    if cross_song and multi_method:
        return "unpaired_cross_song_multi_method"
    if cross_song:
        return "cross_song_same_method"
    if multi_method:
        return "single_song_multi_method"
    return "single_song_single_method"


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or _ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"private separation evidence index {label} differs")
    return value


def _sha256_value(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX_DIGITS for character in value)
    )


def _counts(entries: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    values = sorted({str(entry[key]) for entry in entries})
    return {
        value: sum(1 for entry in entries if entry[key] == value) for value in values
    }


__all__: tuple[str, ...] = ()
