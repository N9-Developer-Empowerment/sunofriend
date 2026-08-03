from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sunofriend._separation_authorised_midi_comparison import _document_sha256
from sunofriend._separation_cross_song_evidence_index import (
    EvidenceInput,
    SCHEMA,
    _index_cross_song_separation_evidence,
)
from sunofriend._separation_demucs_demo_evaluation import (
    PRIVATE_DEMUCS_DEMO_EVALUATION_SCHEMA,
)
from sunofriend._separation_demucs_midi_evaluation import (
    PRIVATE_DEMUCS_MIDI_EVALUATION_SCHEMA,
)
from sunofriend._separation_demucs_six_source_evaluation import (
    PRIVATE_DEMUCS_6S_EVALUATION_SCHEMA,
)
from sunofriend._separation_melroformer_midi_evaluation import (
    SCHEMA as MELROFORMER_MIDI_SCHEMA,
)


def test_index_is_deterministic_path_free_and_does_not_compare_or_choose(
    tmp_path: Path,
) -> None:
    evidence = _corpus(tmp_path)
    first = _index_cross_song_separation_evidence(
        evidence,
        out=tmp_path / "first.json",
    )
    second = _index_cross_song_separation_evidence(
        tuple(reversed(evidence)),
        out=tmp_path / "second.json",
    )

    assert first["schema"] == SCHEMA
    assert first["summary"] == {
        "entry_count": 4,
        "track_count": 2,
        "method_family_count": 3,
        "evidence_kind_counts": {
            "downstream_midi": 1,
            "provider_midi": 1,
            "separator_audio": 1,
            "vocal_midi": 1,
        },
        "report_schema_counts": {
            PRIVATE_DEMUCS_DEMO_EVALUATION_SCHEMA: 1,
            PRIVATE_DEMUCS_MIDI_EVALUATION_SCHEMA: 1,
            PRIVATE_DEMUCS_6S_EVALUATION_SCHEMA: 1,
            MELROFORMER_MIDI_SCHEMA: 1,
        },
    }
    assert first["document_sha256"] == second["document_sha256"]
    assert first["policy"]["metrics_compared_across_schemas"] is False
    assert first["policy"]["method_ranked_or_selected"] is False
    assert first["effects"]["midi_created_or_mutated"] is False
    persisted_text = (tmp_path / "first.json").read_text(encoding="utf-8")
    persisted = json.loads(persisted_text)
    assert persisted["document_sha256"] == _document_sha256(persisted)
    assert str(tmp_path) not in persisted_text
    assert all("report_path" not in entry for entry in persisted["entries"])


@pytest.mark.parametrize(
    ("section", "key"),
    [
        ("permissions", "production_eligible"),
        ("effects", "source_graph_mutated"),
    ],
)
def test_index_rejects_permission_or_active_effect(
    tmp_path: Path, section: str, key: str
) -> None:
    evidence = list(_corpus(tmp_path))
    bad_path = evidence[0].report
    report = json.loads(bad_path.read_text(encoding="utf-8"))
    if section == "effects" and report.get("effects") is None:
        report["effects"] = {}
    report[section][key] = True
    report["document_sha256"] = _document_sha256(report)
    bad_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="permission|active effect"):
        _index_cross_song_separation_evidence(
            evidence,
            out=tmp_path / "rejected.json",
        )
    assert not (tmp_path / "rejected.json").exists()


def test_index_rejects_report_tampering(tmp_path: Path) -> None:
    evidence = _corpus(tmp_path)
    report = json.loads(evidence[0].report.read_text(encoding="utf-8"))
    report["marker"] = "changed-without-self-hash"
    evidence[0].report.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="contract differs"):
        _index_cross_song_separation_evidence(
            evidence,
            out=tmp_path / "rejected.json",
        )


def test_index_requires_cross_song_multi_method_unique_reports(tmp_path: Path) -> None:
    evidence = _corpus(tmp_path)
    with pytest.raises(ValueError, match="at least 4"):
        _index_cross_song_separation_evidence(
            evidence[:3],
            out=tmp_path / "too-small.json",
        )

    one_track = tuple(
        EvidenceInput(
            track_id="same-track",
            method_family=item.method_family,
            evidence_kind=item.evidence_kind,
            report=item.report,
        )
        for item in evidence
    )
    with pytest.raises(ValueError, match="at least two track"):
        _index_cross_song_separation_evidence(
            one_track,
            out=tmp_path / "one-track.json",
        )

    duplicated = evidence + (
        EvidenceInput(
            track_id="track-c",
            method_family="another-method",
            evidence_kind=evidence[0].evidence_kind,
            report=evidence[0].report,
        ),
    )
    with pytest.raises(ValueError, match="same sealed report"):
        _index_cross_song_separation_evidence(
            duplicated,
            out=tmp_path / "duplicate.json",
        )


def _corpus(tmp_path: Path) -> tuple[EvidenceInput, ...]:
    rows = (
        (
            "track-a",
            "demucs",
            "separator_audio",
            PRIVATE_DEMUCS_DEMO_EVALUATION_SCHEMA,
            {},
        ),
        (
            "track-a",
            "demucs",
            "downstream_midi",
            PRIVATE_DEMUCS_MIDI_EVALUATION_SCHEMA,
            {},
        ),
        (
            "track-b",
            "provider-reference",
            "provider_midi",
            PRIVATE_DEMUCS_6S_EVALUATION_SCHEMA,
            {"midi_candidates_created": True},
        ),
        (
            "track-b",
            "kim-vocal-2",
            "vocal_midi",
            MELROFORMER_MIDI_SCHEMA,
            {
                "dry_proxy_audition_created": True,
                "inactive_midi_created": True,
                "register_hypothesis_auditions_created": True,
            },
        ),
    )
    result = []
    for index, (track, method, kind, schema, effects) in enumerate(rows):
        path = tmp_path / f"evidence-{index}.json"
        _write_report(path, schema=schema, marker=index, effects=effects)
        result.append(
            EvidenceInput(
                track_id=track,
                method_family=method,
                evidence_kind=kind,
                report=path,
            )
        )
    return tuple(result)


def _write_report(
    path: Path,
    *,
    schema: str,
    marker: int,
    effects: dict[str, bool],
) -> None:
    permissions = {
        "accepted": False,
        "automatic_promotion": False,
        "automatic_selection": False,
        "production_eligible": False,
        "public_result": False,
        "source_graph_activation": False,
    }
    document: dict[str, object] = {
        "schema": schema,
        "status": "complete_observation_not_acceptance",
        "evidence_scope": "private_development_only",
        "marker": marker,
        "permissions": permissions,
        "effects": copy.deepcopy(effects),
    }
    document["document_sha256"] = _document_sha256(document)
    path.write_text(json.dumps(document), encoding="utf-8")
