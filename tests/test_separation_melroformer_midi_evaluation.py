from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import sunofriend._separation_melroformer_midi_evaluation as evaluation
import sunofriend.evaluate as production_evaluate
import sunofriend.render as production_render
from sunofriend._separation_authorised_midi_comparison import (
    AUTHORISED_MIDI_COMPARISON_SCHEMA,
    _document_sha256,
)
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS
from sunofriend.models import NoteEvent


def test_applies_unchanged_vocal_policy_and_keeps_result_inactive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker_report, worker_document = _worker_fixture(tmp_path / "worker")
    control_report = _control_fixture(tmp_path / "controls")
    monkeypatch.setattr(
        evaluation,
        "_validate_private_melroformer_authorised_worker",
        lambda _: worker_document,
    )
    transcription = SimpleNamespace(
        notes=(NoteEvent(0.1, 0.5, 64, 90),),
        primary_variant="consensus",
        diagnostics=SimpleNamespace(to_dict=lambda: {"fixture": True}),
    )
    observed_configs = []

    def transcribe(path: Path, *, config: object) -> object:
        observed_configs.append(config)
        return transcription

    monkeypatch.setattr(evaluation, "transcribe_vocal_melody", transcribe)
    monkeypatch.setattr(
        production_evaluate,
        "evaluate_stem_midi",
        lambda *args, **kwargs: {"schema": "fixture-evaluation"},
    )

    def render(_midi: Path, output: Path) -> None:
        output.write_bytes(b"fixture-render")

    monkeypatch.setattr(production_render, "render_midi_to_wav", render)
    monkeypatch.setattr(
        evaluation,
        "_production_component_identity",
        lambda: {"mode": "test_injected", "production_identity_captured": False},
    )

    result = evaluation._evaluate_private_melroformer_vocal_midi(
        worker_report,
        control_report,
        out_dir=tmp_path / "result",
    )

    assert result["status"] == "complete_observation_not_acceptance"
    assert result["candidate"]["primary"]["note_count"] == 1
    assert set(result["comparisons_to_existing_controls"]) == {
        "local-htdemucs",
        "moises",
        "suno-a",
        "suno-b",
    }
    assert result["policy"]["tracker_mode"] == "pyin"
    assert result["policy"]["bpm"] == 136.0
    assert observed_configs[0].bpm == 136.0
    assert result["policy"]["same_production_vocal_settings_as_controls"] is True
    assert all(value is False for value in result["permissions"].values())
    assert result["effects"]["worker_rerun"] is False
    assert Path(result["report"]).is_file()


def test_rejects_a_changed_worker_vocal_before_transcription(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker_report, worker_document = _worker_fixture(tmp_path / "worker")
    control_report = _control_fixture(tmp_path / "controls")
    monkeypatch.setattr(
        evaluation,
        "_validate_private_melroformer_authorised_worker",
        lambda _: worker_document,
    )
    vocals = worker_report.parent / "output" / "STEMS" / "vocals.wav"
    vocals.write_bytes(b"changed")

    with pytest.raises(ValueError, match="hash changed"):
        evaluation._evaluate_private_melroformer_vocal_midi(
            worker_report,
            control_report,
            out_dir=tmp_path / "result",
        )


def test_private_melroformer_midi_evaluation_has_no_public_route() -> None:
    assert "private-melroformer-vocal-midi-evaluation" not in PUBLIC_COMMANDS
    assert "private-melroformer-vocal-midi-evaluation" not in DIRECT_TUI_COMMANDS


def test_control_policy_accepts_a_distinct_sealed_song_tempo() -> None:
    assert evaluation._validated_control_policy(
        {
            "bpm": 114.0,
            "tuning_hz": 440.0,
            "vocal_role_uses_separate_production_dominant_contour": True,
            "same_role_uses_identical_settings_across_every_pack": True,
        }
    ) == (114.0, 440.0)


@pytest.mark.parametrize("bpm", [True, float("nan"), 19.9, 400.1])
def test_control_policy_rejects_invalid_tempo(bpm: object) -> None:
    with pytest.raises(ValueError, match="policy differs"):
        evaluation._validated_control_policy(
            {
                "bpm": bpm,
                "tuning_hz": 440.0,
                "vocal_role_uses_separate_production_dominant_contour": True,
                "same_role_uses_identical_settings_across_every_pack": True,
            }
        )


def _worker_fixture(root: Path) -> tuple[Path, dict[str, object]]:
    vocals = root / "output" / "STEMS" / "vocals.wav"
    vocals.parent.mkdir(parents=True)
    vocals.write_bytes(b"fixture-vocals")
    vocals_sha = hashlib.sha256(vocals.read_bytes()).hexdigest()
    document: dict[str, object] = {
        "evidence_sha256": "a" * 64,
        "quarantine": {
            "outputs": [
                {"role": "instrumental", "bytes": 1, "sha256": "b" * 64},
                {"role": "vocals", "bytes": vocals.stat().st_size, "sha256": vocals_sha},
            ]
        },
        "model": {
            "candidate_id": "mlx-melroformer-kim-vocal-2",
            "checkpoint_sha256": "c" * 64,
        },
        "artifacts": {"authorisation_report_sha256": "d" * 64},
        "conclusion": {
            "network_denial_bound_to_model_worker": True,
            "pcm24_quarantine_bound_to_model_worker": True,
        },
    }
    report = root / "authorised-worker-observation.json"
    report.write_text("{}\n", encoding="utf-8")
    return report, document


def _control_fixture(root: Path) -> Path:
    root.mkdir()
    packs = {}
    artifacts = {}
    for index, pack_id in enumerate(
        ("local-htdemucs", "moises", "suno-a", "suno-b")
    ):
        relative = f"{pack_id}/vocals/primary.notes.json"
        path = root / relative
        path.parent.mkdir(parents=True)
        payload = {
            "schema": "sunofriend.private-authorised-midi-note-evidence.v1",
            "role": "vocals",
            "candidate": "primary",
            "source_sha256": str(index) * 64,
            "notes": [
                {
                    "start_seconds": 0.1,
                    "end_seconds": 0.5,
                    "pitch": 64,
                    "velocity": 90,
                }
            ],
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        artifact = {
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        artifacts[relative] = {
            "bytes": artifact["bytes"],
            "sha256": artifact["sha256"],
        }
        packs[pack_id] = {"vocals": {"primary": {"notes": artifact}}}
    document = {
        "schema": AUTHORISED_MIDI_COMPARISON_SCHEMA,
        "policy": {
            "bpm": 136.0,
            "tuning_hz": 440.0,
            "vocal_role_uses_separate_production_dominant_contour": True,
            "same_role_uses_identical_settings_across_every_pack": True,
        },
        "packs": packs,
        "artifacts": artifacts,
    }
    document["document_sha256"] = _document_sha256(document)
    report = root / "authorised-midi-comparison.json"
    report.write_text(json.dumps(document), encoding="utf-8")
    return report
