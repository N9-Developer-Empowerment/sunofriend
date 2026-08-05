from __future__ import annotations

from copy import deepcopy
import hashlib
import os
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest

import sunofriend._separation_reviewed_output_import as reviewed_import
from sunofriend.derived_source_receipt import (
    DERIVED_SOURCE_RECEIPT_SCHEMA,
    validate_derived_source_receipt_files,
)
from sunofriend.source_lineage import (
    SourceGraphError,
    build_source_graph_revision,
    load_source_graph,
    resolve_active_sources,
    write_source_graph_revision,
)
from sunofriend.source_project import (
    SourceMetadata,
    SourcePart,
    build_source_project,
    write_source_project,
)
from sunofriend.source_receipt import (
    SourceImportReceipt,
    canonical_json_bytes,
    write_source_receipt,
)


def test_imports_reviewed_stems_as_inactive_lineage_with_mix_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)

    result = _run(context)

    root = context["output"]
    graph = load_source_graph(root)
    active = resolve_active_sources(graph, project_root=root)
    assert [node.role for node in active] == ["mix"]
    assert graph.activation["mode"] == "unchanged"
    assert {node.role for node in graph.nodes if node.origin == "derived"} == {
        "vocals",
        "other",
    }
    assert result["rollback"] == {
        "original_mix_retained": True,
        "original_mix_remains_active": True,
        "reviewed_stems_are_inactive": True,
        "external_path_dependencies": False,
    }
    assert all(asset["active"] is False for asset in result["reviewed_assets"])
    assert result["readiness"]["source_graph_activation_permitted"] is False
    assert result["readiness"]["midi_conversion_of_imported_stems_permitted"] is False
    assert Path(result["report"]).stat().st_mode & 0o777 == 0o444
    assert not any(root.rglob("*reconstruction*.wav"))
    for asset in result["reviewed_assets"]:
        receipt_path = root / asset["receipt_path"]
        receipt = __import__("json").loads(receipt_path.read_text(encoding="utf-8"))
        assert receipt["schema"] == DERIVED_SOURCE_RECEIPT_SCHEMA
        validate_derived_source_receipt_files(receipt, root=root)

    group = graph.refinement_groups[0]
    activated = build_source_graph_revision(
        graph,
        active_node_ids=group.child_node_ids,
        activation={
            "mode": "reviewed",
            "group_id": group.group_id,
            "reviewed": True,
            "selected_node_ids": list(group.child_node_ids),
        },
    )
    write_source_graph_revision(
        root,
        activated,
        expected_current_graph_id=graph.graph_id,
    )
    assert {node.role for node in resolve_active_sources(activated, project_root=root)} == {
        "vocals",
        "other",
    }


def test_rejects_existing_destination_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    context["output"].mkdir(mode=0o700)

    with pytest.raises(FileExistsError, match="destination exists"):
        _run(context)

    assert list(context["output"].iterdir()) == []


def test_rejects_assessment_candidate_binding_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    context["assessment"]["document"]["bindings"][
        "candidate_package_report_sha256"
    ] = "0" * 64

    with pytest.raises(ValueError, match="assessment binding differs"):
        _run(context)

    assert not context["output"].exists()


def test_active_derived_receipt_must_match_parent_asset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(tmp_path, monkeypatch)
    _run(context)
    root = context["output"]
    graph = load_source_graph(root)
    group = graph.refinement_groups[0]
    activated = build_source_graph_revision(
        graph,
        active_node_ids=group.child_node_ids,
        activation={
            "mode": "reviewed",
            "group_id": group.group_id,
            "reviewed": True,
            "selected_node_ids": list(group.child_node_ids),
        },
    )
    derived = next(node for node in graph.nodes if node.origin == "derived")
    receipt_path = root / derived.asset.receipt_path
    receipt = __import__("json").loads(receipt_path.read_text(encoding="utf-8"))
    receipt["parent"]["asset_id"] = f"sha256:{'0' * 64}"
    receipt_path.chmod(0o600)
    receipt_path.write_bytes(canonical_json_bytes(receipt))
    receipt_path.chmod(0o444)

    with pytest.raises(SourceGraphError, match="lineage does not match"):
        resolve_active_sources(activated, project_root=root)


def _run(context: dict[str, object]) -> dict[str, object]:
    return reviewed_import._import_reviewed_output(
        context["assessment_path"],
        equivalence_path=context["equivalence_path"],
        reviewed_export_path=context["reviewed_export"],
        reviewed_package_dir=context["reviewed_package"],
        candidate_package_report_path=context["candidate_report"],
        ffmpeg="/fake/ffmpeg",
        ffprobe="/fake/ffprobe",
        out_dir=context["output"],
        title="Private test import",
        key="B minor",
        bpm=113,
        tuning_hz=440,
    )


def _context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    os.chmod(tmp_path, 0o700)
    candidate_root = tmp_path / "candidate"
    stitch_root = candidate_root / "STITCH"
    stitch_root.mkdir(parents=True, mode=0o700)
    source = _write_pcm24(stitch_root / "source.wav", value=10)
    vocals = _write_pcm24(stitch_root / "vocals.wav", value=20)
    instrumental = _write_pcm24(stitch_root / "instrumental.wav", value=-10)
    reconstruction = _write_pcm24(stitch_root / "reconstruction.wav", value=10)
    artifacts = {
        role: _artifact(path)
        for role, path in {
            "source": source,
            "vocals": vocals,
            "instrumental": instrumental,
            "reconstruction": reconstruction,
        }.items()
    }
    candidate = {
        "sha256": "b" * 64,
        "document": {"document_sha256": "c" * 64},
        "stitch_root": stitch_root,
        "stitch": {
            "artifacts": artifacts,
            "clock": {
                "sample_rate": 44_100,
                "channels": 2,
                "frames": 32,
                "boundary_count": 1,
            },
        },
    }
    reviewed_assets = [
        {
            "candidate_role": "vocals",
            "source_role": "vocals",
            "declared_role": "vocals",
            "audio_sha256": artifacts["vocals"]["sha256"],
            "pcm24_int32_sequence_sha256": "1" * 64,
            "geometry": artifacts["vocals"]["geometry"],
            "shape": "leaf",
            "origin": "derived",
        },
        {
            "candidate_role": "instrumental",
            "source_role": "other",
            "declared_role": "instrumental",
            "audio_sha256": artifacts["instrumental"]["sha256"],
            "pcm24_int32_sequence_sha256": "2" * 64,
            "geometry": artifacts["instrumental"]["geometry"],
            "shape": "leaf",
            "origin": "derived",
        },
    ]
    assessment = {
        "sha256": "d" * 64,
        "document": {
            "document_sha256": "e" * 64,
            "bindings": {
                "candidate_package_report_sha256": candidate["sha256"],
                "candidate_package_document_sha256": candidate["document"][
                    "document_sha256"
                ],
                "source_audio_sha256": artifacts["source"]["sha256"],
                "review_equivalence_document_sha256": "f" * 64,
            },
            "future_import_contract": {
                "initial_activation_mode": "unchanged",
                "automatic_activation_permitted": False,
            },
            "readiness": {"private_import_implementation_eligible": True},
            "reviewed_assets": reviewed_assets,
        },
    }
    context: dict[str, object] = {
        "assessment_path": tmp_path / "assessment.json",
        "equivalence_path": tmp_path / "equivalence.json",
        "reviewed_export": tmp_path / "reviewed.json",
        "reviewed_package": tmp_path / "reviewed-package",
        "candidate_report": candidate_root / "package.json",
        "output": tmp_path / "prepared-private-project",
        "candidate": candidate,
        "assessment": assessment,
    }
    monkeypatch.setattr(
        reviewed_import,
        "_load_verified_reviewed_output_import_assessment",
        lambda *_args, **_kwargs: deepcopy(context["assessment"]),
    )
    monkeypatch.setattr(
        reviewed_import,
        "_load_candidate_package",
        lambda *_args, **_kwargs: deepcopy(context["candidate"]),
    )
    monkeypatch.setattr(
        reviewed_import,
        "plan_source_import",
        lambda source, destination, **_kwargs: SimpleNamespace(
            source=Path(source),
            destination=Path(destination),
        ),
    )
    monkeypatch.setattr(
        reviewed_import,
        "execute_source_import",
        lambda plan: _fake_source_import(plan),
    )
    return context


def _fake_source_import(plan: SimpleNamespace) -> SimpleNamespace:
    root = plan.destination
    root.mkdir(mode=0o700)
    original = root / "INPUT/original/source.wav"
    canonical = root / "INPUT/canonical/source.wav"
    original.parent.mkdir(parents=True)
    canonical.parent.mkdir(parents=True)
    original.write_bytes(plan.source.read_bytes())
    canonical.write_bytes(plan.source.read_bytes())
    sha256 = hashlib.sha256(original.read_bytes()).hexdigest()
    canonical_sha256 = hashlib.sha256(canonical.read_bytes()).hexdigest()
    receipt_path = root / "INPUT/source-import.json"
    receipt = SourceImportReceipt(
        source_id=f"sha256:{sha256}",
        original={"path": "INPUT/original/source.wav", "sha256": sha256},
        canonical={
            "path": "INPUT/canonical/source.wav",
            "sha256": canonical_sha256,
            "sample_format": "pcm_s24le",
            "sample_width_bytes": 3,
        },
        clock={},
        decoder={"network_protocols": ["file"], "arguments": []},
        limits={},
    )
    write_source_receipt(receipt_path, receipt)
    project = build_source_project(
        title="Private test import",
        metadata=SourceMetadata(key="B minor", bpm=113, tuning_hz=440),
        rights_category="authorised_private_use",
        source=SourcePart(
            source_id=receipt.source_id,
            role="mix",
            original_name="source.wav",
            original_path="INPUT/original/source.wav",
            canonical_path="INPUT/canonical/source.wav",
            receipt_path="INPUT/source-import.json",
        ),
    )
    write_source_project(root / "INPUT/source-project.json", project)
    for path in (original, canonical, receipt_path, root / "INPUT/source-project.json"):
        path.chmod(0o444)
    return SimpleNamespace(root=root)


def _write_pcm24(path: Path, *, value: int) -> Path:
    channels = 2
    frames = 32
    data = bytearray()
    encoded = int(value).to_bytes(3, "little", signed=True)
    for _frame in range(frames):
        data.extend(encoded * channels)
    fmt = struct.pack(
        "<HHIIHH",
        1,
        channels,
        44_100,
        44_100 * channels * 3,
        channels * 3,
        24,
    )
    body = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    body += b"data" + struct.pack("<I", len(data)) + bytes(data)
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body) + 4) + b"WAVE" + body)
    return path


def _artifact(path: Path) -> dict[str, object]:
    return {
        "path": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "geometry": {
            "sample_rate": 44_100,
            "channels": 2,
            "frames": 32,
            "sample_width_bytes": 3,
        },
    }
