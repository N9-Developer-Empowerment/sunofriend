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
from sunofriend._separation_demucs_refinement_evaluation import (
    __all__,
    _document_sha256,
    _evaluate_private_demucs_production_refinement,
)
from sunofriend._separation_demucs_private_run import (
    PRIVATE_DEMUCS_EXPERIMENT_SCHEMA,
    _document_sha256 as _experiment_document_sha256,
)
from sunofriend.midi import MidiTrack, write_midi_file
from sunofriend.models import NoteEvent


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


def _fake_refiner(**kwargs: object) -> SimpleNamespace:
    source = Path(str(kwargs["stem_path"]))
    kind = str(kwargs["kind"])
    out_dir = Path(str(kwargs["out_dir"]))
    estimated = "ESTIMATED-STEMS" in source.parts
    base_pitch = {"bass": 36, "drums": 36, "synth": 60}[kind]
    notes = [
        NoteEvent(0.02 if estimated else 0.0, 0.5, base_pitch, 100),
        NoteEvent(1.0, 1.4, base_pitch + (0 if kind == "drums" else 4), 88),
    ]
    out_dir.mkdir(parents=True, exist_ok=True)
    midi_path = out_dir / f"{kind}_listened.mid"
    channel, program = (9, 0) if kind == "drums" else (0, 38)
    write_midi_file(
        midi_path,
        [MidiTrack(kind, channel, program, notes)],
        bpm=float(kwargs["bpm"]),
    )
    (out_dir / f"{kind}_iterations.json").write_text("[]\n")
    return SimpleNamespace(
        notes=notes,
        score=0.75,
        history=[
            SimpleNamespace(
                iteration=0,
                score=0.75,
                note_count=len(notes),
                detail={"test": True},
            )
        ],
        midi_path=midi_path,
        variants={"possible": [NoteEvent(2.0, 2.2, base_pitch, 60)]},
    )


def _fake_renderer(_midi: Path, output: Path, **_kwargs: object) -> Path:
    Path(output).write_bytes(b"RIFF" + b"\0" * 64)
    return Path(output)


def _fake_evaluator(
    _source: Path,
    notes: list[NoteEvent] | tuple[NoteEvent, ...],
    **kwargs: object,
) -> dict:
    return {
        "schema": "test-independent-evaluation.v1",
        "kind": kwargs["kind"],
        "note_count": len(notes),
        "drum_family_map_supplied": kwargs.get("pitch_family_map") is not None,
    }


def test_private_refinement_runs_primary_variants_renderer_and_evaluator() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        fixture = _create_private_demucs_demo_fixture(root / "fixture")
        experiment = _experiment(root / "experiment", fixture)
        result = _evaluate_private_demucs_production_refinement(
            fixture["manifest"],
            experiment,
            out_dir=root / "evaluation",
            max_iterations=4,
            refiner=_fake_refiner,
            renderer=_fake_renderer,
            evaluator=_fake_evaluator,
        )

        assert result["status"] == "complete_observation_not_acceptance"
        assert result["policy"]["measurement_layer"] == (
            "production_refine_stem_repair_loop"
        )
        assert result["policy"]["full_refine_stem_pipeline_run"] is True
        assert result["policy"]["independent_audio_to_midi_evaluator_run"] is True
        assert result["policy"]["renderer_used_for_every_primary_and_variant"] is True
        assert result["policy"]["vocals_in_scope"] is False
        assert result["components"] == {
            "mode": "test_injected",
            "production_identity_captured": False,
        }
        assert result["permissions"]["accepted"] is False
        assert result["effects"]["source_graph_mutated"] is False
        for role in ("bass", "drums", "other"):
            evidence = result["roles"][role]
            assert evidence["reference"]["note_count"] == 2
            assert evidence["estimate"]["note_count"] == 2
            assert evidence["reference"]["variants"]["possible"]["note_count"] == 1
            assert evidence["clean_to_estimate_midi_comparison"]["counts"] == {
                "reference": 2,
                "estimate": 2,
                "false_positive_against_silence": None,
            }
            if role == "drums":
                assert evidence["reference"]["independent_evaluation"][
                    "drum_family_map_supplied"
                ] is True

        report = Path(result["report"])
        persisted = json.loads(report.read_text())
        assert persisted["document_sha256"] == _document_sha256(persisted)
        assert len(persisted["artifacts"]) == 42
        for relative, artifact in persisted["artifacts"].items():
            path = report.parent / relative
            assert path.is_file()
            assert _sha256(path) == artifact["sha256"]
        for path in report.parent.rglob("*"):
            if path.is_file():
                assert (path.stat().st_mode & 0o777) == 0o600
            elif path.is_dir():
                assert (path.stat().st_mode & 0o777) == 0o700


def test_private_refinement_requires_fresh_output_and_complete_injection() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        fixture = _create_private_demucs_demo_fixture(root / "fixture")
        experiment = _experiment(root / "experiment", fixture)
        destination = root / "evaluation"
        _evaluate_private_demucs_production_refinement(
            fixture["manifest"],
            experiment,
            out_dir=destination,
            refiner=_fake_refiner,
            renderer=_fake_renderer,
            evaluator=_fake_evaluator,
        )
        with pytest.raises(FileExistsError, match="already exists"):
            _evaluate_private_demucs_production_refinement(
                fixture["manifest"],
                experiment,
                out_dir=destination,
                refiner=_fake_refiner,
                renderer=_fake_renderer,
                evaluator=_fake_evaluator,
            )
        with pytest.raises(ValueError, match="must all be injected together"):
            _evaluate_private_demucs_production_refinement(
                fixture["manifest"],
                experiment,
                out_dir=root / "partial",
                refiner=_fake_refiner,
            )


@pytest.mark.parametrize("value", [0, -1, 1.5, True])
def test_private_refinement_rejects_invalid_iteration_limit(value: object) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        _evaluate_private_demucs_production_refinement(
            "fixture.json",
            "experiment.json",
            out_dir="evaluation",
            max_iterations=value,  # type: ignore[arg-type]
        )


def test_private_refinement_cleans_partial_output_after_component_failure() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        fixture = _create_private_demucs_demo_fixture(root / "fixture")
        experiment = _experiment(root / "experiment", fixture)
        destination = root / "evaluation"

        def fail_renderer(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("render failed")

        with pytest.raises(RuntimeError, match="render failed"):
            _evaluate_private_demucs_production_refinement(
                fixture["manifest"],
                experiment,
                out_dir=destination,
                refiner=_fake_refiner,
                renderer=fail_renderer,
                evaluator=_fake_evaluator,
            )
        assert not destination.exists()
        assert not list(root.glob(".evaluation.building-*"))


def test_private_refinement_rejects_non_note_component_output_cleanly() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        fixture = _create_private_demucs_demo_fixture(root / "fixture")
        experiment = _experiment(root / "experiment", fixture)
        destination = root / "evaluation"

        def invalid_refiner(**kwargs: object) -> SimpleNamespace:
            result = _fake_refiner(**kwargs)
            result.notes = [object()]
            return result

        with pytest.raises(ValueError, match="invalid NoteEvent"):
            _evaluate_private_demucs_production_refinement(
                fixture["manifest"],
                experiment,
                out_dir=destination,
                refiner=invalid_refiner,
                renderer=_fake_renderer,
                evaluator=_fake_evaluator,
            )
        assert not destination.exists()


def test_private_refinement_rejects_changed_estimate_before_output() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        fixture = _create_private_demucs_demo_fixture(root / "fixture")
        experiment = _experiment(root / "experiment", fixture)
        report = json.loads(experiment.read_text())
        estimate = experiment.parent / report["estimated_stems"]["bass"]["path"]
        estimate.write_bytes(estimate.read_bytes() + b"tampered")
        destination = root / "evaluation"

        with pytest.raises(ValueError, match="bass estimate hash changed"):
            _evaluate_private_demucs_production_refinement(
                fixture["manifest"],
                experiment,
                out_dir=destination,
                refiner=_fake_refiner,
                renderer=_fake_renderer,
                evaluator=_fake_evaluator,
            )
        assert not destination.exists()


def test_private_refinement_has_no_product_import_and_exports_nothing() -> None:
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
        assert "_separation_demucs_refinement_evaluation" not in source
    assert __all__ == ()
