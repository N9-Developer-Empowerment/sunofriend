"""Path-free catalogue of heterogeneous private separation evidence.

The index proves that multiple songs and method families have sealed evidence.
It deliberately does not normalize unlike metrics, rank a method or turn any
private-development report into a product decision.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from ._separation_authorised_midi_comparison import (
    _document_sha256,
    _regular_json,
    _sha256,
)
from ._separation_demucs_demo_evaluation import (
    PRIVATE_DEMUCS_DEMO_EVALUATION_SCHEMA,
)
from ._separation_demucs_midi_evaluation import (
    PRIVATE_DEMUCS_MIDI_EVALUATION_SCHEMA,
)
from ._separation_demucs_six_source_evaluation import (
    PRIVATE_DEMUCS_6S_EVALUATION_SCHEMA,
)
from ._separation_melroformer_midi_evaluation import SCHEMA as MELROFORMER_MIDI_SCHEMA
from ._separation_vocal_candidate_audition import _write_fresh_private_json


SCHEMA = "sunofriend.private-cross-song-separation-evidence-index.v1"
_MAX_REPORT_BYTES = 2 * 1024 * 1024
_MINIMUM_ENTRIES = 4
_ID_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?")
_SCHEMA_BY_KIND = {
    "separator_audio": PRIVATE_DEMUCS_DEMO_EVALUATION_SCHEMA,
    "downstream_midi": PRIVATE_DEMUCS_MIDI_EVALUATION_SCHEMA,
    "provider_midi": PRIVATE_DEMUCS_6S_EVALUATION_SCHEMA,
    "vocal_midi": MELROFORMER_MIDI_SCHEMA,
}
_ALLOWED_TRUE_EFFECTS = {
    PRIVATE_DEMUCS_DEMO_EVALUATION_SCHEMA: frozenset(),
    PRIVATE_DEMUCS_MIDI_EVALUATION_SCHEMA: frozenset(),
    PRIVATE_DEMUCS_6S_EVALUATION_SCHEMA: frozenset({"midi_candidates_created"}),
    MELROFORMER_MIDI_SCHEMA: frozenset(
        {
            "dry_proxy_audition_created",
            "inactive_midi_created",
            "register_hypothesis_auditions_created",
        }
    ),
}


@dataclass(frozen=True)
class EvidenceInput:
    """One caller-labelled, sealed private evidence report."""

    track_id: str
    method_family: str
    evidence_kind: str
    report: Path


@dataclass(frozen=True)
class _LoadedEvidence:
    source: EvidenceInput
    report_schema: str
    report_sha256: str
    report_document_sha256: str
    report_bytes: int


def _index_cross_song_separation_evidence(
    evidence: Sequence[EvidenceInput],
    *,
    out: str | Path,
) -> dict[str, Any]:
    """Validate and catalogue sealed reports without comparing their metrics."""

    loaded = tuple(_load_evidence(item) for item in evidence)
    _validate_corpus(loaded)
    document = _build_document(loaded)
    document["document_sha256"] = _document_sha256(document)
    _reverify_reports(loaded)
    _write_fresh_private_json(Path(out), document)
    document["report"] = str(Path(out).expanduser().absolute())
    return document


def _load_evidence(item: EvidenceInput) -> _LoadedEvidence:
    track_id = _safe_id(item.track_id, "track ID")
    method_family = _safe_id(item.method_family, "method-family ID")
    expected_schema = _SCHEMA_BY_KIND.get(item.evidence_kind)
    if expected_schema is None:
        raise ValueError(f"unsupported evidence kind: {item.evidence_kind}")
    path = _regular_json(item.report, "private separation evidence report")
    size = path.stat().st_size
    if size > _MAX_REPORT_BYTES:
        raise ValueError("private separation evidence report is too large")
    file_sha256 = _sha256(path)
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(
            "private separation evidence report is not valid JSON"
        ) from error
    if not isinstance(report, dict):
        raise ValueError("private separation evidence report must be a JSON object")
    if (
        report.get("schema") != expected_schema
        or report.get("status") != "complete_observation_not_acceptance"
        or report.get("evidence_scope") != "private_development_only"
        or report.get("document_sha256") != _document_sha256(report)
    ):
        raise ValueError("private separation evidence report contract differs")
    _validate_inactive_report(report)
    return _LoadedEvidence(
        source=EvidenceInput(
            track_id=track_id,
            method_family=method_family,
            evidence_kind=item.evidence_kind,
            report=path,
        ),
        report_schema=expected_schema,
        report_sha256=file_sha256,
        report_document_sha256=str(report["document_sha256"]),
        report_bytes=size,
    )


def _validate_inactive_report(report: Mapping[str, Any]) -> None:
    permissions = report.get("permissions")
    if not isinstance(permissions, Mapping) or not permissions:
        raise ValueError("private separation evidence permissions differ")
    if any(value is not False for value in permissions.values()):
        raise ValueError("private separation evidence report grants a permission")
    effects = report.get("effects")
    if effects is None:
        return
    if not isinstance(effects, Mapping) or any(
        not isinstance(value, bool) for value in effects.values()
    ):
        raise ValueError("private separation evidence effects differ")
    allowed_true = _ALLOWED_TRUE_EFFECTS[str(report["schema"])]
    unexpected_true = {
        str(key)
        for key, value in effects.items()
        if value is True and key not in allowed_true
    }
    if unexpected_true:
        raise ValueError("private separation evidence report has an active effect")


def _validate_corpus(evidence: Sequence[_LoadedEvidence]) -> None:
    if len(evidence) < _MINIMUM_ENTRIES:
        raise ValueError(f"at least {_MINIMUM_ENTRIES} evidence reports are required")
    track_ids = {item.source.track_id for item in evidence}
    method_families = {item.source.method_family for item in evidence}
    if len(track_ids) < 2:
        raise ValueError("cross-song evidence requires at least two track IDs")
    if len(method_families) < 2:
        raise ValueError("multi-method evidence requires at least two method families")
    identities = [
        (
            item.source.track_id,
            item.source.method_family,
            item.source.evidence_kind,
        )
        for item in evidence
    ]
    if len(identities) != len(set(identities)):
        raise ValueError("evidence track, method and kind identities must be unique")
    report_hashes = [item.report_sha256 for item in evidence]
    if len(report_hashes) != len(set(report_hashes)):
        raise ValueError("the same sealed report cannot be catalogued twice")


def _build_document(evidence: Sequence[_LoadedEvidence]) -> dict[str, Any]:
    ordered = sorted(
        evidence,
        key=lambda item: (
            item.source.track_id,
            item.source.method_family,
            item.source.evidence_kind,
            item.report_sha256,
        ),
    )
    entries = [
        {
            "track_id": item.source.track_id,
            "method_family": item.source.method_family,
            "evidence_kind": item.source.evidence_kind,
            "report_schema": item.report_schema,
            "report_sha256": item.report_sha256,
            "report_document_sha256": item.report_document_sha256,
            "report_bytes": item.report_bytes,
            "status": "complete_observation_not_acceptance",
        }
        for item in ordered
    ]
    return {
        "schema": SCHEMA,
        "status": "complete_catalogue_not_comparison_or_acceptance",
        "evidence_scope": "private_development_only",
        "summary": {
            "entry_count": len(entries),
            "track_count": len({entry["track_id"] for entry in entries}),
            "method_family_count": len({entry["method_family"] for entry in entries}),
            "evidence_kind_counts": _counts(entries, "evidence_kind"),
            "report_schema_counts": _counts(entries, "report_schema"),
        },
        "entries": entries,
        "policy": {
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
            "This is a path-free integrity catalogue, not a metric comparison, quality score or acceptance report.",
            "Track and method-family identifiers are caller-declared labels, not independently inferred identities.",
            "Metrics from different report schemas remain heterogeneous and must not be compared as if they share one scale.",
            "The index copies hashes and bounded metadata only; it does not copy source audio, MIDI, report bodies or filesystem paths.",
            "Catalogue membership does not imply checkpoint licensing, publication permission, product eligibility or human musical approval.",
            "Outstanding human listening reviews remain separate evidence gates.",
        ],
    }


def _counts(entries: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    values = {str(entry[key]) for entry in entries}
    return {
        value: sum(1 for entry in entries if entry[key] == value)
        for value in sorted(values)
    }


def _safe_id(value: str, label: str) -> str:
    if not isinstance(value, str) or _ID_PATTERN.fullmatch(value) is None:
        raise ValueError(
            f"{label} must be a lowercase ASCII token with letters, digits or hyphens"
        )
    return value


def _reverify_reports(evidence: Sequence[_LoadedEvidence]) -> None:
    for item in evidence:
        path = item.source.report
        try:
            details = path.lstat()
        except OSError as error:
            raise ValueError(
                "private separation evidence report disappeared"
            ) from error
        if (
            not path.is_file()
            or path.is_symlink()
            or details.st_size != item.report_bytes
            or _sha256(path) != item.report_sha256
        ):
            raise ValueError(
                "private separation evidence report changed during indexing"
            )


__all__: tuple[str, ...] = ()
