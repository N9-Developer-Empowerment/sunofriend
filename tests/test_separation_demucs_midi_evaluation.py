from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from sunofriend._separation_demucs_demo_fixture import (
    _create_private_demucs_demo_fixture,
)
from sunofriend._separation_demucs_midi_evaluation import (
    __all__,
    _document_sha256 as _midi_evaluation_document_sha256,
    _evaluate_private_demucs_downstream_midi,
)
from sunofriend._separation_demucs_midi_metrics import (
    _compare_drum_hits,
    _compare_note_events,
)
from sunofriend._separation_demucs_private_run import (
    PRIVATE_DEMUCS_EXPERIMENT_SCHEMA,
    _document_sha256 as _experiment_document_sha256,
)
from sunofriend.models import NoteEvent
from sunofriend.transcribe_drums import DrumHit, DrumTranscription


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _experiment(root: Path, fixture: dict) -> Path:
    stem_dir = root / "ESTIMATED-STEMS"
    stem_dir.mkdir(parents=True)
    estimated = {}
    for role, source in fixture["reference_paths"].items():
        target = stem_dir / f"{role}.wav"
        shutil.copyfile(source, target)
        estimated[role] = {
            "path": f"ESTIMATED-STEMS/{role}.wav",
            "sha256": _sha256(target),
        }
    document = {
        "schema": PRIVATE_DEMUCS_EXPERIMENT_SCHEMA,
        "status": "complete_review_required",
        "evidence_scope": "private_development_only",
        "source": {"sha256": fixture["mixture"]["sha256"]},
        "backend": {
            "checkpoint_sha256": "a" * 64,
            "worker_sha256": "b" * 64,
        },
        "estimated_stems": estimated,
        "permissions": {
            "accepted": False,
            "production_eligible": False,
            "automatic_selection": False,
            "automatic_promotion": False,
            "source_graph_activation": False,
            "public_result": False,
            "simple_mode_available": False,
            "studio_import_available": False,
        },
    }
    document["document_sha256"] = _experiment_document_sha256(document)
    path = root / "private-separation-experiment.json"
    path.write_text(json.dumps(document, sort_keys=True) + "\n")
    return path


def _pitched(path: Path, kind: str) -> list[NoteEvent]:
    estimated = path.parent.parent.name == "experiment"
    if kind == "bass":
        return [
            NoteEvent(0.02 if estimated else 0.0, 0.8, 36, 100),
            NoteEvent(1.0, 1.8, 31 if not estimated else 43, 90),
        ]
    return [
        NoteEvent(0.0, 0.7, 60, 90),
        NoteEvent(0.0, 0.7, 64 if not estimated else 65, 80),
    ]


def _drums(path: Path) -> DrumTranscription:
    estimated = path.parent.parent.name == "experiment"
    hits = (
        DrumHit(0.0, 36, 100, 1.0, family="kick_high"),
        DrumHit(
            0.52 if estimated else 0.5,
            42 if not estimated else 39,
            85,
            0.8,
            family="hat_closed" if not estimated else "unknown",
        ),
    )
    return DrumTranscription("drums", 22_050, hits, ())


def _vocals(path: Path) -> SimpleNamespace:
    estimated = path.parent.parent.name == "experiment"
    return SimpleNamespace(
        notes=[NoteEvent(2.0, 2.4, 69, 70)] if estimated else [],
        primary_variant="contour_clean",
        diagnostics=SimpleNamespace(warnings=()),
    )


def test_private_midi_evaluation_is_relative_inactive_and_auditable() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        fixture = _create_private_demucs_demo_fixture(root / "fixture")
        experiment = _experiment(root / "experiment", fixture)
        result = _evaluate_private_demucs_downstream_midi(
            fixture["manifest"],
            experiment,
            out_dir=root / "evaluation",
            pitched_transcriber=_pitched,
            drum_transcriber=_drums,
            vocal_transcriber=_vocals,
        )

        assert result["status"] == "complete_observation_not_acceptance"
        assert result["policy"]["absolute_ground_truth_claimed"] is False
        assert result["policy"]["measurement_layer"] == "seed_transcriber_only"
        assert result["policy"]["full_refine_stem_pipeline_run"] is False
        assert result["next"]["full_production_refinement_parity_required"] is True
        assert result["permissions"]["accepted"] is False
        assert result["effects"]["source_graph_mutated"] is False
        assert result["transcribers"] == {
            "mode": "test_injected",
            "production_identity_captured": False,
        }
        assert result["roles"]["bass"]["comparison"]["counts"]["reference"] == 2
        assert result["roles"]["bass"]["comparison"]["counts"]["estimate"] == 2
        assert (
            result["roles"]["vocals"]["comparison"]["counts"][
                "false_positive_against_silence"
            ]
            == 1
        )
        assert (
            result["roles"]["drums"]["comparison"]["articulation_family_onset"]["f1"]
            < result["roles"]["drums"]["comparison"]["onset_only"]["f1"]
        )

        report = Path(result["report"])
        persisted = json.loads(report.read_text())
        assert persisted["document_sha256"] == _midi_evaluation_document_sha256(
            persisted
        )
        evaluation_root = report.parent
        for role in ("bass", "drums", "other", "vocals"):
            for side in ("REFERENCE", "ESTIMATE"):
                assert (evaluation_root / side / f"{role}.mid").is_file()
                assert (evaluation_root / side / f"{role}.notes.json").is_file()
        for path in evaluation_root.rglob("*"):
            if path.is_file():
                assert (path.stat().st_mode & 0o777) == 0o600
        tolerance_seconds = result["policy"]["onset_tolerance_ms"] / 1000.0
        for role in ("bass", "other", "vocals"):
            reference = _load_notes(
                evaluation_root / "REFERENCE" / f"{role}.notes.json"
            )
            estimate = _load_notes(evaluation_root / "ESTIMATE" / f"{role}.notes.json")
            assert (
                _compare_note_events(
                    reference,
                    estimate,
                    tolerance_seconds=tolerance_seconds,
                )
                == result["roles"][role]["comparison"]
            )
        reference_hits = _load_hits(evaluation_root / "REFERENCE" / "drums.notes.json")
        estimate_hits = _load_hits(evaluation_root / "ESTIMATE" / "drums.notes.json")
        assert (
            _compare_drum_hits(
                reference_hits,
                estimate_hits,
                tolerance_seconds=tolerance_seconds,
            )
            == result["roles"]["drums"]["comparison"]
        )


def test_private_midi_evaluation_requires_fresh_output() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        fixture = _create_private_demucs_demo_fixture(root / "fixture")
        experiment = _experiment(root / "experiment", fixture)
        destination = root / "evaluation"
        _evaluate_private_demucs_downstream_midi(
            fixture["manifest"],
            experiment,
            out_dir=destination,
            pitched_transcriber=_pitched,
            drum_transcriber=_drums,
            vocal_transcriber=_vocals,
        )
        with pytest.raises(FileExistsError, match="already exists"):
            _evaluate_private_demucs_downstream_midi(
                fixture["manifest"],
                experiment,
                out_dir=destination,
                pitched_transcriber=_pitched,
                drum_transcriber=_drums,
                vocal_transcriber=_vocals,
            )


def test_private_midi_evaluation_rejects_partial_transcriber_injection() -> None:
    with pytest.raises(ValueError, match="must all be injected together"):
        _evaluate_private_demucs_downstream_midi(
            "fixture.json",
            "experiment.json",
            out_dir="evaluation",
            pitched_transcriber=_pitched,
        )


def test_private_midi_evaluation_rejects_changed_estimate_before_output() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        fixture = _create_private_demucs_demo_fixture(root / "fixture")
        experiment = _experiment(root / "experiment", fixture)
        report = json.loads(experiment.read_text())
        estimate = experiment.parent / report["estimated_stems"]["bass"]["path"]
        estimate.write_bytes(estimate.read_bytes() + b"tampered")
        destination = root / "evaluation"

        with pytest.raises(ValueError, match="bass estimate hash changed"):
            _evaluate_private_demucs_downstream_midi(
                fixture["manifest"],
                experiment,
                out_dir=destination,
                pitched_transcriber=_pitched,
                drum_transcriber=_drums,
                vocal_transcriber=_vocals,
            )
        assert not destination.exists()


def test_private_midi_evaluation_has_no_product_import() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "src/sunofriend/cli.py",
        "src/sunofriend/tui.py",
        "src/sunofriend/tui_conversion.py",
        "src/sunofriend/simple_create.py",
        "src/sunofriend/workbench_server.py",
        "src/sunofriend/__init__.py",
    ):
        source = (root / relative).read_text(encoding="utf-8")
        assert "_separation_demucs_midi_evaluation" not in source
        assert "_separation_demucs_midi_metrics" not in source


def test_private_midi_evaluation_exports_nothing() -> None:
    assert __all__ == ()


def _load_notes(path: Path) -> list[NoteEvent]:
    document = json.loads(path.read_text())
    return [
        NoteEvent(
            row["start_seconds"],
            row["end_seconds"],
            row["pitch"],
            row["velocity"],
        )
        for row in document["notes"]
    ]


def _load_hits(path: Path) -> list[DrumHit]:
    document = json.loads(path.read_text())
    return [
        DrumHit(
            row["time_seconds"],
            row["gm_pitch"],
            row["velocity"],
            row["strength"],
            family=row["family"],
            tier=row["tier"],
            provenance=row["provenance"],
            source_time=row["source_time_seconds"],
        )
        for row in document["drum_hits"]
    ]
