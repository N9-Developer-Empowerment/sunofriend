from __future__ import annotations

import json
import hashlib
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile

from sunofriend._separation_authorised_excerpt import (
    __all__,
    _document_sha256,
    _run_authorised_separation_excerpt,
)
from sunofriend._separation_authorised_role_mapping import (
    __all__ as role_mapping_exports,
    _document_sha256 as _role_mapping_document_sha256,
    _map_authorised_excerpt_roles,
)
from sunofriend._separation_authorised_midi_comparison import (
    __all__ as midi_comparison_exports,
    _compare_authorised_role_midi,
    _document_sha256 as _midi_comparison_document_sha256,
)
from sunofriend._separation_authorised_narrow_other import (
    __all__ as narrow_other_exports,
    _compare_authorised_other_leaves,
    _document_sha256 as _narrow_other_document_sha256,
)
from sunofriend.models import NoteEvent


def _write_wave(path: Path, value: np.ndarray, sample_rate: int = 8_000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    soundfile.write(path, value, sample_rate, subtype="PCM_24")


def _corpus(root: Path, *, mismatched_provider_rate: bool = False) -> Path:
    track = root / "corpus" / "example-song"
    sample_rate = 8_000
    times = np.arange(sample_rate * 2, dtype=np.float64) / sample_rate
    roles = {
        "bass": 0.20 * np.sin(2.0 * np.pi * 110.0 * times),
        "drums": 0.08 * np.sin(2.0 * np.pi * 440.0 * times),
        "other": 0.10 * np.sin(2.0 * np.pi * 220.0 * times),
        "vocals": 0.06 * np.sin(2.0 * np.pi * 330.0 * times),
    }
    mixture = sum(roles.values())
    original = np.column_stack((mixture, mixture))
    _write_wave(track / "ORIGINAL" / "song.wav", original, sample_rate)
    for pack in ("PACK-A", "PACK-B"):
        rate = 8_100 if mismatched_provider_rate and pack == "PACK-B" else sample_rate
        if rate != sample_rate:
            other_times = np.arange(rate * 2, dtype=np.float64) / rate
            pack_roles = {
                "bass": 0.20 * np.sin(2.0 * np.pi * 110.0 * other_times),
                "drums": 0.08 * np.sin(2.0 * np.pi * 440.0 * other_times),
                "other": 0.10 * np.sin(2.0 * np.pi * 220.0 * other_times),
                "vocals": 0.06 * np.sin(2.0 * np.pi * 330.0 * other_times),
            }
        else:
            pack_roles = roles
        for role, values in pack_roles.items():
            _write_wave(
                track / pack / f"{role}.wav",
                np.column_stack((values, values)),
                rate,
            )
    document = {
        "schema": "sunofriend.authorised-separation-corpus.v1",
        "artist": {"name": "Owner", "soundcloud_profile": "https://example.test"},
        "permission": {
            "authority": "creator_and_copyright_holder",
            "scope": "test fixture",
            "allowed_use": "study",
            "condition": "credit Owner",
        },
        "tracks": [
            {
                "id": "example",
                "title": "Example",
                "directory": "example-song",
                "evaluation_state": "ready_for_excerpt_selection",
                "evaluation_excerpt": {
                    "start_seconds": 0.25,
                    "end_seconds": 1.25,
                    "selection_policy": "fixed active test interval",
                    "provider_packs": [
                        {"id": "pack-a", "directory": "PACK-A"},
                        {"id": "pack-b", "directory": "PACK-B"},
                    ],
                    "role_group_proposals": {
                        "pack-a": {
                            "bass": ["bass.wav"],
                            "drums": ["drums.wav"],
                            "other": ["other.wav"],
                            "vocals": ["vocals.wav"],
                        },
                        "pack-b": {
                            "bass": ["bass.wav"],
                            "drums": ["drums.wav"],
                            "other": ["other.wav"],
                            "vocals": ["vocals.wav"],
                        },
                    },
                },
            }
        ],
    }
    path = root / "corpus" / "corpus.json"
    path.write_text(json.dumps(document) + "\n")
    return path


def _fake_separator(
    audio: Path,
    *,
    out_dir: Path,
    checkpoint_path: Path,
    start_seconds: float,
    end_seconds: float,
    python: str | Path | None,
) -> dict:
    assert Path(checkpoint_path).is_file()
    assert soundfile.info(audio).samplerate == 44_100
    assert start_seconds == 0.0
    assert end_seconds == 1.0
    assert python == "fake-python"
    root = Path(out_dir)
    root.mkdir(parents=True)
    stem_dir = root / "ESTIMATED-STEMS"
    stem_dir.mkdir()
    sample_rate = 44_100
    times = np.arange(sample_rate, dtype=np.float64) / sample_rate
    estimates = {}
    for role, amplitude, frequency in (
        ("bass", 0.20, 110.0),
        ("drums", 0.08, 440.0),
        ("other", 0.10, 220.0),
        ("vocals", 0.06, 330.0),
    ):
        values = amplitude * np.sin(2.0 * np.pi * frequency * times)
        path = stem_dir / f"{role}.wav"
        _write_wave(path, np.column_stack((values, values)), sample_rate)
        estimates[role] = {
            "path": f"ESTIMATED-STEMS/{role}.wav",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    report = root / "private-separation-experiment.json"
    report.write_text(
        json.dumps(
            {
                "schema": "test-private-separator.v1",
                "status": "complete_review_required",
                "document_sha256": "a" * 64,
                "estimated_stems": estimates,
            }
        )
        + "\n"
    )
    return {
        "status": "complete_review_required",
        "report": str(report),
        "estimated_stems": {},
    }


def _fake_midi_refiner(**kwargs: object) -> SimpleNamespace:
    kind = str(kwargs["kind"])
    base_pitch = {"bass": 36, "drums": 36, "synth": 60}[kind]
    notes = [
        NoteEvent(0.0, 0.4, base_pitch, 96),
        NoteEvent(0.5, 0.9, base_pitch + (0 if kind == "drums" else 4), 84),
    ]
    out_dir = Path(str(kwargs["out_dir"]))
    out_dir.mkdir(parents=True)
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
        variants={"possible": [NoteEvent(0.25, 0.35, base_pitch, 60)]},
    )


def _fake_midi_renderer(_midi: Path, output: Path) -> Path:
    output.write_bytes(b"RIFF" + b"\0" * 64)
    return output


def _fake_midi_evaluator(
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


def _fake_vocal_transcriber(_source: Path) -> SimpleNamespace:
    primary = [
        NoteEvent(0.0, 0.4, 64, 90),
        NoteEvent(0.5, 0.9, 67, 82),
    ]
    return SimpleNamespace(
        notes=primary,
        primary_variant="phrase_repaired",
        variants={
            "phrase_repaired": primary,
            "contour_clean": [NoteEvent(0.0, 0.9, 64, 72)],
        },
        diagnostics=SimpleNamespace(
            to_dict=lambda: {"tracker": "test", "warnings": []}
        ),
    )


def test_authorised_excerpt_stages_aligned_packs_and_private_local_run() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        corpus = _corpus(root)
        checkpoint = root / "checkpoint.th"
        checkpoint.write_bytes(b"private-test-checkpoint")
        result = _run_authorised_separation_excerpt(
            corpus,
            "example",
            out_dir=root / "evaluation",
            checkpoint_path=checkpoint,
            python="fake-python",
            separator_runner=_fake_separator,
        )

        assert result["status"] == "complete_review_required"
        assert result["corpus"]["track_id"] == "example"
        assert result["corpus"]["preferred_credit"] == (
            "Music by Owner — https://example.test"
        )
        assert result["excerpt"]["geometry"] == {
            "sample_rate": 8_000,
            "channels": 2,
            "frames": 8_000,
            "duration_seconds": 1.0,
        }
        assert result["effects"]["midi_created"] is False
        assert result["permissions"]["accepted"] is False
        model_input = result["original"]["local_model_input"]
        assert model_input["geometry"]["sample_rate"] == 44_100
        assert model_input["geometry"]["frames"] == 44_100
        assert "resample_poly" in model_input["derivation"]["algorithm"]
        assert set(result["excerpt"]["role_group_proposals"]) == {
            "pack-a",
            "pack-b",
        }
        for pack in ("pack-a", "pack-b"):
            evidence = result["provider_packs"][pack]
            assert evidence["source_count"] == 4
            assert evidence["summed_source_count"] == 4
            alignment = evidence["pack_sum_alignment"]
            assert alignment["sample_correlation_at_recorded_zero"] > 0.999999

        report = Path(result["report"])
        persisted = json.loads(report.read_text())
        assert persisted["document_sha256"] == _document_sha256(persisted)
        assert persisted["local_separator"]["document_sha256"] == "a" * 64
        for relative, artifact in persisted["artifacts"].items():
            path = report.parent / relative
            assert path.is_file()
            assert path.stat().st_size == artifact["bytes"]
        for path in report.parent.rglob("*"):
            if path.is_file():
                assert (path.stat().st_mode & 0o777) == 0o600
            elif path.is_dir():
                assert (path.stat().st_mode & 0o777) == 0o700


def test_authorised_excerpt_rejects_geometry_mismatch_before_model_run() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        corpus = _corpus(root, mismatched_provider_rate=True)
        checkpoint = root / "checkpoint.th"
        checkpoint.write_bytes(b"private-test-checkpoint")
        called = False

        def separator(*_args: object, **_kwargs: object) -> dict:
            nonlocal called
            called = True
            return {}

        with pytest.raises(ValueError, match="geometry does not match"):
            _run_authorised_separation_excerpt(
                corpus,
                "example",
                out_dir=root / "evaluation",
                checkpoint_path=checkpoint,
                separator_runner=separator,
            )
        assert called is False
        assert not (root / "evaluation").exists()
        assert not list(root.glob(".evaluation.building-*"))


def test_authorised_excerpt_requires_fresh_output() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        corpus = _corpus(root)
        checkpoint = root / "checkpoint.th"
        checkpoint.write_bytes(b"private-test-checkpoint")
        destination = root / "evaluation"
        destination.mkdir()
        with pytest.raises(FileExistsError, match="already exists"):
            _run_authorised_separation_excerpt(
                corpus,
                "example",
                out_dir=destination,
                checkpoint_path=checkpoint,
                separator_runner=_fake_separator,
            )


def test_authorised_excerpt_has_no_product_import_and_exports_nothing() -> None:
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
        assert "_separation_authorised_excerpt" not in source
        assert "_separation_authorised_role_mapping" not in source
        assert "_separation_authorised_midi_comparison" not in source
        assert "_separation_authorised_narrow_other" not in source
    assert __all__ == ()
    assert role_mapping_exports == ()
    assert midi_comparison_exports == ()
    assert narrow_other_exports == ()


def test_authorised_role_mapping_partitions_and_ranks_synthetic_roles() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        corpus = _corpus(root)
        checkpoint = root / "checkpoint.th"
        checkpoint.write_bytes(b"private-test-checkpoint")
        excerpt = _run_authorised_separation_excerpt(
            corpus,
            "example",
            out_dir=root / "excerpt",
            checkpoint_path=checkpoint,
            python="fake-python",
            separator_runner=_fake_separator,
        )
        result = _map_authorised_excerpt_roles(
            excerpt["report"],
            out_dir=root / "mapping",
        )

        assert result["status"] == "complete_review_required"
        assert result["observations"]["all_proposed_roles_rank_first"] is True
        assert result["permissions"]["accepted"] is False
        assert result["effects"]["midi_created"] is False
        for pack in ("pack-a", "pack-b"):
            assert result["provider_partition_closure"][pack]["passed"] is True
            observations = result["comparisons_to_local_htdemucs"][pack][
                "proposed_role_observations"
            ]
            for role in ("bass", "drums", "other", "vocals"):
                assert observations[role]["rank"] == 1
                assert observations[role]["accepted"] is False
                assert result["groups"][pack][role]["artifact"]["bytes"] > 0

        report = Path(result["report"])
        persisted = json.loads(report.read_text())
        assert persisted["document_sha256"] == _role_mapping_document_sha256(persisted)
        for relative, artifact in persisted["artifacts"].items():
            path = report.parent / relative
            assert path.is_file()
            assert path.stat().st_size == artifact["bytes"]


def test_authorised_role_mapping_rejects_changed_source_artifact() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        corpus = _corpus(root)
        checkpoint = root / "checkpoint.th"
        checkpoint.write_bytes(b"private-test-checkpoint")
        excerpt = _run_authorised_separation_excerpt(
            corpus,
            "example",
            out_dir=root / "excerpt",
            checkpoint_path=checkpoint,
            separator_runner=_fake_separator,
            python="fake-python",
        )
        report = json.loads(Path(excerpt["report"]).read_text())
        relative = next(
            path
            for path in report["artifacts"]
            if path.startswith("PROVIDER-EXCERPTS/")
        )
        changed = Path(excerpt["report"]).parent / relative
        changed.write_bytes(changed.read_bytes() + b"tampered")

        with pytest.raises(ValueError, match="hash changed"):
            _map_authorised_excerpt_roles(
                excerpt["report"],
                out_dir=root / "mapping",
            )
        assert not (root / "mapping").exists()


def _synthetic_role_mapping(root: Path) -> dict:
    corpus = _corpus(root)
    checkpoint = root / "checkpoint.th"
    checkpoint.write_bytes(b"private-test-checkpoint")
    excerpt = _run_authorised_separation_excerpt(
        corpus,
        "example",
        out_dir=root / "excerpt",
        checkpoint_path=checkpoint,
        separator_runner=_fake_separator,
        python="fake-python",
    )
    return _map_authorised_excerpt_roles(
        excerpt["report"],
        out_dir=root / "mapping",
    )


def test_authorised_narrow_other_ranks_leaves_without_accepting() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        mapping = _synthetic_role_mapping(root)
        result = _compare_authorised_other_leaves(
            mapping["report"],
            out_dir=root / "narrow-other",
        )

        assert result["status"] == "complete_observation_not_acceptance"
        assert result["observations"]["leaf_counts"] == {
            "pack-a": 1,
            "pack-b": 1,
        }
        assert (
            result["observations"][
                "all_same_label_counterparts_rank_first_both_directions"
            ]
            is True
        )
        assert result["permissions"]["accepted"] is False
        assert result["effects"]["source_graph_mutated"] is False
        comparison = result["pairwise_audio_comparisons"]["pack-a__pack-b"]
        assert comparison["left_to_right_rankings"]["leaf-01"] == {
            "ranked_leaf_ids": ["leaf-01"],
            "nearest_leaf_id": "leaf-01",
            "nearest_evidence_similarity": 1.0,
            "margin_over_runner_up": 1.0,
            "accepted": False,
        }

        report = Path(result["report"])
        persisted = json.loads(report.read_text())
        assert persisted["document_sha256"] == _narrow_other_document_sha256(
            persisted
        )
        for relative, artifact in persisted["artifacts"].items():
            path = report.parent / relative
            assert path.is_file()
            assert path.stat().st_size == artifact["bytes"]


def test_authorised_narrow_other_rejects_changed_mapping_artifact() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        mapping = _synthetic_role_mapping(root)
        report = json.loads(Path(mapping["report"]).read_text())
        relative = next(iter(report["artifacts"]))
        changed = Path(mapping["report"]).parent / relative
        changed.write_bytes(changed.read_bytes() + b"tampered")

        with pytest.raises(ValueError, match="hash changed"):
            _compare_authorised_other_leaves(
                mapping["report"],
                out_dir=root / "narrow-other",
            )
        assert not (root / "narrow-other").exists()


def test_authorised_midi_comparison_runs_identical_inactive_paths() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        mapping = _synthetic_role_mapping(root)
        result = _compare_authorised_role_midi(
            mapping["report"],
            out_dir=root / "midi-comparison",
            bpm=120.0,
            tuning_hz=440.0,
            max_iterations=4,
            refiner=_fake_midi_refiner,
            renderer=_fake_midi_renderer,
            evaluator=_fake_midi_evaluator,
            vocal_transcriber=_fake_vocal_transcriber,
        )

        assert result["status"] == "complete_observation_not_acceptance"
        assert result["components"]["mode"] == "test_injected"
        assert (
            result["policy"]["same_role_uses_identical_settings_across_every_pack"]
            is True
        )
        assert result["permissions"] == {
            "accepted": False,
            "production_eligible": False,
            "automatic_selection": False,
            "automatic_promotion": False,
            "source_graph_activation": False,
            "public_result": False,
            "simple_mode_available": False,
            "studio_import_available": False,
        }
        assert set(result["packs"]) == {
            "local-htdemucs",
            "pack-a",
            "pack-b",
        }
        for pack in result["packs"].values():
            assert set(pack) == {"bass", "drums", "other", "vocals"}
            assert pack["bass"]["primary"]["note_count"] == 2
            assert pack["vocals"]["primary"]["note_count"] == 2
            assert (
                pack["drums"]["primary"]["independent_evaluation"][
                    "drum_family_map_supplied"
                ]
                is True
            )
        for pack in ("pack-a", "pack-b"):
            comparison = result["comparisons_to_local_htdemucs"][pack]
            assert comparison["bass"]["comparison"]["exact_pitch_onset"]["f1"] == 1.0
            assert comparison["drums"]["comparison"]["broad_family_onset"]["f1"] == 1.0

        report = Path(result["report"])
        persisted = json.loads(report.read_text())
        assert persisted["document_sha256"] == _midi_comparison_document_sha256(
            persisted
        )
        for relative, artifact in persisted["artifacts"].items():
            path = report.parent / relative
            assert path.is_file()
            assert path.stat().st_size == artifact["bytes"]


def test_authorised_midi_comparison_requires_complete_injection() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        mapping = _synthetic_role_mapping(root)
        with pytest.raises(ValueError, match="must all be injected together"):
            _compare_authorised_role_midi(
                mapping["report"],
                out_dir=root / "midi-comparison",
                bpm=120.0,
                tuning_hz=440.0,
                refiner=_fake_midi_refiner,
            )
        assert not (root / "midi-comparison").exists()


def test_authorised_midi_comparison_rejects_changed_mapping_artifact() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        mapping = _synthetic_role_mapping(root)
        report = json.loads(Path(mapping["report"]).read_text())
        relative = next(iter(report["artifacts"]))
        changed = Path(mapping["report"]).parent / relative
        changed.write_bytes(changed.read_bytes() + b"tampered")

        with pytest.raises(ValueError, match="hash changed"):
            _compare_authorised_role_midi(
                mapping["report"],
                out_dir=root / "midi-comparison",
                bpm=120.0,
                tuning_hz=440.0,
                refiner=_fake_midi_refiner,
                renderer=_fake_midi_renderer,
                evaluator=_fake_midi_evaluator,
                vocal_transcriber=_fake_vocal_transcriber,
            )
        assert not (root / "midi-comparison").exists()
