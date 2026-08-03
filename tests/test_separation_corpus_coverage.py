from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sunofriend._separation_authorised_midi_comparison import _document_sha256
from sunofriend._separation_corpus_coverage import (
    SCHEMA,
    _assess_private_separation_corpus_coverage,
)
from sunofriend._separation_cross_song_evidence_index import (
    SCHEMA as INDEX_SCHEMA,
    _SCHEMA_BY_KIND,
)


def test_current_shape_is_cross_song_but_not_cross_method_comparable(
    tmp_path: Path,
) -> None:
    index_path = _write_index(tmp_path / "index.json", _current_entries())

    result = _assess_private_separation_corpus_coverage(
        index_path,
        out=tmp_path / "coverage.json",
    )

    assert result["schema"] == SCHEMA
    assert result["catalogue_summary"]["entry_count"] == 6
    assert result["coverage_summary"] == {
        "group_count": 4,
        "same_schema_cross_song_group_count": 2,
        "same_schema_multi_method_group_count": 0,
        "paired_cross_method_track_count": 0,
        "complete_two_track_two_method_rectangle_count": 0,
        "normalized_metric_contract_count": 0,
    }
    groups = {group["evidence_kind"]: group for group in result["coverage_groups"]}
    assert groups["provider_midi"]["coverage_shape"] == "cross_song_same_method"
    assert groups["vocal_midi"]["coverage_shape"] == "cross_song_same_method"
    assert groups["separator_audio"]["coverage_shape"] == ("single_song_single_method")
    assert all(
        group["metric_comparison_permitted"] is False
        for group in result["coverage_groups"]
    )
    assert result["publication_gate"]["status"] == "open"
    unresolved = result["publication_gate"]["unresolved_or_out_of_scope"]
    assert "no_same_schema_cross_method_pair" in unresolved
    assert "no_same_schema_cross_song_multi_method_rectangle" in unresolved
    assert result["policy"]["method_ranked_or_selected"] is False
    persisted_text = (tmp_path / "coverage.json").read_text(encoding="utf-8")
    persisted = json.loads(persisted_text)
    assert persisted["document_sha256"] == _document_sha256(persisted)
    assert str(tmp_path) not in persisted_text


def test_complete_rectangle_is_topology_only_and_still_not_comparison_ready(
    tmp_path: Path,
) -> None:
    entries = [
        _entry(track, method, "provider_midi", index)
        for index, (track, method) in enumerate(
            (
                ("track-a", "method-a"),
                ("track-a", "method-b"),
                ("track-b", "method-a"),
                ("track-b", "method-b"),
            ),
            start=1,
        )
    ]
    index_path = _write_index(tmp_path / "index.json", entries)

    result = _assess_private_separation_corpus_coverage(
        index_path,
        out=tmp_path / "coverage.json",
    )

    group = result["coverage_groups"][0]
    assert group["coverage_shape"] == "cross_song_multi_method_rectangle_unscored"
    assert group["paired_cross_method_track_count"] == 2
    assert group["repeated_cross_song_method_count"] == 2
    assert group["complete_two_track_two_method_rectangle_count"] == 1
    assert group["metric_comparison_permitted"] is False
    assert result["coverage_summary"]["same_schema_multi_method_group_count"] == 1
    assert result["publication_gate"]["cross_method_quality_comparison_ready"] is False
    unresolved = result["publication_gate"]["unresolved_or_out_of_scope"]
    assert "no_same_schema_cross_method_pair" not in unresolved
    assert "no_same_schema_cross_song_multi_method_rectangle" not in unresolved
    assert "normalized_metric_contract_not_present" in unresolved


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("active_permission", "grants a permission"),
        ("active_effect", "active effect"),
        ("summary", "summary differs"),
    ],
)
def test_coverage_rejects_active_or_inconsistent_index(
    tmp_path: Path, change: str, message: str
) -> None:
    index_path = _write_index(tmp_path / "index.json", _current_entries())
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if change == "active_permission":
        index["permissions"]["production_eligible"] = True
    elif change == "active_effect":
        index["effects"]["candidate_activated"] = True
    else:
        index["summary"]["track_count"] += 1
    index["document_sha256"] = _document_sha256(index)
    index_path.write_text(json.dumps(index), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        _assess_private_separation_corpus_coverage(
            index_path,
            out=tmp_path / "rejected.json",
        )
    assert not (tmp_path / "rejected.json").exists()


def test_coverage_rejects_index_tampering(tmp_path: Path) -> None:
    index_path = _write_index(tmp_path / "index.json", _current_entries())
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["limitations"] = ["changed without a new self hash"]
    index_path.write_text(json.dumps(index), encoding="utf-8")

    with pytest.raises(ValueError, match="contract differs"):
        _assess_private_separation_corpus_coverage(
            index_path,
            out=tmp_path / "rejected.json",
        )


def test_coverage_rejects_duplicate_document_identity(tmp_path: Path) -> None:
    entries = _current_entries()
    entries[1]["report_document_sha256"] = entries[0]["report_document_sha256"]
    index_path = _write_index(tmp_path / "index.json", entries)

    with pytest.raises(ValueError, match="duplicates evidence"):
        _assess_private_separation_corpus_coverage(
            index_path,
            out=tmp_path / "rejected.json",
        )
    assert not (tmp_path / "rejected.json").exists()


def _current_entries() -> list[dict[str, object]]:
    rows = (
        ("synthetic-demo", "demucs", "separator_audio"),
        ("synthetic-demo", "demucs", "downstream_midi"),
        ("be-alone", "provider-reference", "provider_midi"),
        ("i-am-a-alien", "provider-reference", "provider_midi"),
        ("be-alone", "kim-vocal-2", "vocal_midi"),
        ("i-am-a-alien", "kim-vocal-2", "vocal_midi"),
    )
    return [
        _entry(track, method, kind, index)
        for index, (track, method, kind) in enumerate(rows, start=1)
    ]


def _entry(
    track: str,
    method: str,
    kind: str,
    marker: int,
) -> dict[str, object]:
    return {
        "track_id": track,
        "method_family": method,
        "evidence_kind": kind,
        "report_schema": _SCHEMA_BY_KIND[kind],
        "report_sha256": f"{marker:064x}",
        "report_document_sha256": f"{marker + 1000:064x}",
        "report_bytes": marker * 100,
        "status": "complete_observation_not_acceptance",
    }


def _write_index(path: Path, entries: list[dict[str, object]]) -> Path:
    ordered = sorted(
        copy.deepcopy(entries),
        key=lambda entry: (
            entry["track_id"],
            entry["method_family"],
            entry["evidence_kind"],
            entry["report_sha256"],
        ),
    )
    document: dict[str, object] = {
        "schema": INDEX_SCHEMA,
        "status": "complete_catalogue_not_comparison_or_acceptance",
        "evidence_scope": "private_development_only",
        "summary": {
            "entry_count": len(ordered),
            "track_count": len({entry["track_id"] for entry in ordered}),
            "method_family_count": len({entry["method_family"] for entry in ordered}),
            "evidence_kind_counts": _counts(ordered, "evidence_kind"),
            "report_schema_counts": _counts(ordered, "report_schema"),
        },
        "entries": ordered,
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
        "limitations": [],
    }
    document["document_sha256"] = _document_sha256(document)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _counts(entries: list[dict[str, object]], key: str) -> dict[str, int]:
    values = sorted({str(entry[key]) for entry in entries})
    return {
        value: sum(1 for entry in entries if entry[key] == value) for value in values
    }
