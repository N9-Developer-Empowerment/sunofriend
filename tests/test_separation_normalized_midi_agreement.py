from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sunofriend._separation_authorised_excerpt import AUTHORISED_EXCERPT_SCHEMA
from sunofriend._separation_authorised_midi_comparison import (
    AUTHORISED_MIDI_COMPARISON_SCHEMA,
    _document_sha256,
)
from sunofriend._separation_authorised_role_mapping import (
    AUTHORISED_ROLE_MAPPING_SCHEMA,
)
from sunofriend._separation_cross_song_evidence_index import (
    SCHEMA as INDEX_SCHEMA,
    _SCHEMA_BY_KIND,
)
from sunofriend._separation_demucs_midi_metrics import _compare_note_events
from sunofriend._separation_melroformer_midi_evaluation import (
    SCHEMA as MELROFORMER_MIDI_SCHEMA,
)
from sunofriend._separation_normalized_midi_agreement import (
    MidiAgreementInput,
    SCHEMA,
    _normalize_private_separation_midi_agreement,
)
from sunofriend.models import NoteEvent


def test_normalizes_two_source_bound_songs_without_ranking(tmp_path: Path) -> None:
    comparisons = [
        _comparison(tmp_path, "track-a", source_track_id="track-a-source"),
        _comparison(tmp_path, "track-b", source_track_id="track-b"),
    ]
    index = _index(tmp_path, comparisons)

    result = _normalize_private_separation_midi_agreement(
        index,
        [item[0] for item in comparisons],
        candidate_method_family="kim-vocal-2",
        control_method_family="provider-reference",
        control_id="moises",
        out=tmp_path / "agreement.json",
    )

    assert result["schema"] == SCHEMA
    assert result["observations"] == {
        "song_count": 2,
        "same_method_pair_repeated_across_songs": True,
        "all_metric_schemas_identical": True,
        "aggregate_quality_score_computed": False,
        "winner_selected": False,
    }
    assert [cell["track_id"] for cell in result["cells"]] == [
        "track-a",
        "track-b",
    ]
    assert result["cells"][0]["source_track_id"] == "track-a-source"
    assert all(
        cell["agreement"]["schema"]
        == "sunofriend.private-demucs-midi-note-metrics.v1"
        for cell in result["cells"]
    )
    assert result["comparison_contract"]["pairwise_agreement_comparison_permitted"]
    assert not result["comparison_contract"]["quality_comparison_permitted"]
    assert result["publication_gate"]["status"] == "open"
    persisted_text = (tmp_path / "agreement.json").read_text(encoding="utf-8")
    persisted = json.loads(persisted_text)
    assert persisted["document_sha256"] == _document_sha256(persisted)
    assert str(tmp_path) not in persisted_text


def test_rejects_candidate_not_bound_to_same_authorised_excerpt(
    tmp_path: Path,
) -> None:
    comparisons = [
        _comparison(tmp_path, "track-a", wrong_authorisation=True),
        _comparison(tmp_path, "track-b"),
    ]
    index = _index(tmp_path, comparisons)

    with pytest.raises(ValueError, match="not bound to one authorised excerpt"):
        _normalize_private_separation_midi_agreement(
            index,
            [item[0] for item in comparisons],
            candidate_method_family="kim-vocal-2",
            control_method_family="provider-reference",
            control_id="moises",
            out=tmp_path / "rejected.json",
        )
    assert not (tmp_path / "rejected.json").exists()


def test_rejects_sealed_metric_that_does_not_match_note_evidence(
    tmp_path: Path,
) -> None:
    comparisons = [
        _comparison(tmp_path, "track-a", wrong_sealed_metric=True),
        _comparison(tmp_path, "track-b"),
    ]
    index = _index(tmp_path, comparisons)

    with pytest.raises(ValueError, match="sealed candidate/control"):
        _normalize_private_separation_midi_agreement(
            index,
            [item[0] for item in comparisons],
            candidate_method_family="kim-vocal-2",
            control_method_family="provider-reference",
            control_id="moises",
            out=tmp_path / "rejected.json",
        )


def test_requires_indexed_provider_topology_for_every_song(tmp_path: Path) -> None:
    comparisons = [
        _comparison(tmp_path, "track-a"),
        _comparison(tmp_path, "track-b"),
    ]
    index = _index(tmp_path, comparisons, omit_provider_for="track-b")

    with pytest.raises(ValueError, match="absent from the index"):
        _normalize_private_separation_midi_agreement(
            index,
            [item[0] for item in comparisons],
            candidate_method_family="kim-vocal-2",
            control_method_family="provider-reference",
            control_id="moises",
            out=tmp_path / "rejected.json",
        )


def _comparison(
    root: Path,
    track_id: str,
    *,
    source_track_id: str | None = None,
    wrong_authorisation: bool = False,
    wrong_sealed_metric: bool = False,
) -> tuple[MidiAgreementInput, Path]:
    directory = root / track_id
    directory.mkdir()
    control_notes = (
        NoteEvent(start=0.0, end=0.5, pitch=60, velocity=90),
        NoteEvent(start=1.0, end=1.5, pitch=62, velocity=88),
    )
    candidate_notes = (
        NoteEvent(start=0.01, end=0.52, pitch=60, velocity=91),
        NoteEvent(start=1.02, end=1.48, pitch=62, velocity=87),
    )
    local_artifact = _note_artifact(directory, "local.notes.json", control_notes)
    moises_artifact = _note_artifact(directory, "moises.notes.json", control_notes)
    candidate_artifact = _note_artifact(
        directory, "candidate.notes.json", candidate_notes
    )

    excerpt_path = directory / "authorised-excerpt.json"
    excerpt = _base_report(
        schema=AUTHORISED_EXCERPT_SCHEMA,
        status="complete_review_required",
        extra={"excerpt": {"start_seconds": 10.0, "end_seconds": 25.0}},
    )
    _write_hashed(excerpt_path, excerpt)

    mapping_path = directory / "role-mapping.json"
    mapping = _base_report(
        schema=AUTHORISED_ROLE_MAPPING_SCHEMA,
        status="complete_review_required",
        extra={
            "source_excerpt": {
                "track_id": source_track_id or track_id,
                "start_seconds": 10.0,
                "end_seconds": 25.0,
                "report_sha256": _sha(excerpt_path),
                "document_sha256": excerpt["document_sha256"],
            }
        },
    )
    _write_hashed(mapping_path, mapping)

    control_path = directory / "control.json"
    control = _base_report(
        schema=AUTHORISED_MIDI_COMPARISON_SCHEMA,
        status="complete_observation_not_acceptance",
        extra={
            "source_role_mapping": {
                "report_sha256": _sha(mapping_path),
                "document_sha256": mapping["document_sha256"],
            },
            "policy": {
                "bpm": 120.0,
                "tuning_hz": 440.0,
                "onset_tolerance_ms": 40.0,
                "same_role_uses_identical_settings_across_every_pack": True,
                "vocal_role_uses_separate_production_dominant_contour": True,
            },
            "packs": {
                "local-htdemucs": {
                    "vocals": {"primary": {"notes": local_artifact}}
                },
                "moises": {"vocals": {"primary": {"notes": moises_artifact}}},
            },
        },
    )
    _write_hashed(control_path, control)

    metrics = _compare_note_events(
        control_notes, candidate_notes, tolerance_seconds=0.040
    )
    if wrong_sealed_metric:
        metrics = json.loads(json.dumps(metrics))
        metrics["exact_pitch_onset"]["f1"] = 0.0
    candidate_path = directory / "candidate.json"
    candidate = _base_report(
        schema=MELROFORMER_MIDI_SCHEMA,
        status="complete_observation_not_acceptance",
        extra={
            "worker": {
                "authorisation_report_sha256": (
                    "f" * 64 if wrong_authorisation else _sha(excerpt_path)
                )
            },
            "controls": {
                "comparison_sha256": _sha(control_path),
                "document_sha256": control["document_sha256"],
            },
            "policy": {
                "bpm": 120.0,
                "tuning_hz": 440.0,
                "onset_tolerance_ms": 40.0,
                "absolute_ground_truth_claimed": False,
                "winner_selected": False,
            },
            "candidate": {"primary": {"notes": candidate_artifact}},
            "comparisons_to_existing_controls": {
                "moises": {
                    "control_note_count": len(control_notes),
                    "candidate_note_count": len(candidate_notes),
                    "comparison": metrics,
                    "reference_semantics": (
                        "control MIDI is a relative comparison baseline, not score truth"
                    ),
                }
            },
        },
    )
    _write_hashed(candidate_path, candidate)
    return (
        MidiAgreementInput(
            track_id=track_id,
            candidate_report=candidate_path,
            control_comparison=control_path,
            role_mapping=mapping_path,
            authorised_excerpt=excerpt_path,
        ),
        candidate_path,
    )


def _index(
    root: Path,
    comparisons: list[tuple[MidiAgreementInput, Path]],
    *,
    omit_provider_for: str | None = None,
) -> Path:
    entries = []
    marker = 1
    for source, candidate_path in comparisons:
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        entries.append(
            _index_entry(
                source.track_id,
                "kim-vocal-2",
                "vocal_midi",
                _sha(candidate_path),
                candidate["document_sha256"],
                candidate_path.stat().st_size,
            )
        )
        if source.track_id != omit_provider_for:
            marker += 1
            entries.append(
                _index_entry(
                    source.track_id,
                    "provider-reference",
                    "provider_midi",
                    f"{marker:064x}",
                    f"{marker + 1000:064x}",
                    marker * 10,
                )
            )
    if len(entries) < 4:
        entries.append(
            _index_entry(
                "topology-only",
                "provider-reference",
                "provider_midi",
                "e" * 64,
                "d" * 64,
                10,
            )
        )
    entries.sort(
        key=lambda row: (
            row["track_id"],
            row["method_family"],
            row["evidence_kind"],
            row["report_sha256"],
        )
    )
    document = {
        "schema": INDEX_SCHEMA,
        "status": "complete_catalogue_not_comparison_or_acceptance",
        "evidence_scope": "private_development_only",
        "summary": {
            "entry_count": len(entries),
            "track_count": len({row["track_id"] for row in entries}),
            "method_family_count": len({row["method_family"] for row in entries}),
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
        "permissions": _permissions(),
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
    path = root / "index.json"
    _write_hashed(path, document)
    return path


def _base_report(
    *, schema: str, status: str, extra: dict[str, object]
) -> dict[str, object]:
    return {
        "schema": schema,
        "status": status,
        "evidence_scope": "private_development_only",
        **extra,
        "permissions": _permissions(),
        "effects": {"source_graph_mutated": False},
    }


def _permissions() -> dict[str, bool]:
    return {
        "accepted": False,
        "automatic_promotion": False,
        "automatic_selection": False,
        "production_eligible": False,
        "public_result": False,
        "simple_mode_available": False,
        "source_graph_activation": False,
        "studio_import_available": False,
    }


def _note_artifact(
    root: Path, name: str, notes: tuple[NoteEvent, ...]
) -> dict[str, object]:
    path = root / name
    payload = {
        "schema": "sunofriend.private-authorised-midi-note-evidence.v1",
        "role": "vocals",
        "candidate": "primary",
        "notes": [
            {
                "start_seconds": note.start,
                "end_seconds": note.end,
                "pitch": note.pitch,
                "velocity": note.velocity,
            }
            for note in notes
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return {"path": name, "sha256": _sha(path), "bytes": path.stat().st_size}


def _index_entry(
    track: str,
    method: str,
    kind: str,
    file_sha: str,
    document_sha: str,
    size: int,
) -> dict[str, object]:
    return {
        "track_id": track,
        "method_family": method,
        "evidence_kind": kind,
        "report_schema": _SCHEMA_BY_KIND[kind],
        "report_sha256": file_sha,
        "report_document_sha256": document_sha,
        "report_bytes": size,
        "status": "complete_observation_not_acceptance",
    }


def _counts(rows: list[dict[str, object]], key: str) -> dict[str, int]:
    return {
        value: sum(1 for row in rows if row[key] == value)
        for value in sorted({str(row[key]) for row in rows})
    }


def _write_hashed(path: Path, document: dict[str, object]) -> None:
    document["document_sha256"] = _document_sha256(document)
    path.write_text(json.dumps(document), encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
