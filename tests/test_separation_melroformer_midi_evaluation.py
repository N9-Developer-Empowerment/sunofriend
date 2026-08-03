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
from sunofriend._separation_checkpoint_canonical import canonical_json_bytes
from sunofriend._separation_melroformer_upstream_evidence import (
    CONVERSION_CHECKPOINT_BYTES,
    CONVERSION_CHECKPOINT_SHA256,
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
    lead_transcription = SimpleNamespace(
        notes=(NoteEvent(0.1, 0.5, 64, 90),),
        primary_variant="consensus",
        diagnostics=SimpleNamespace(to_dict=lambda: {"fixture": True}),
    )
    backing_transcription = SimpleNamespace(
        variants={
            "lowest_line": (NoteEvent(0.1, 0.5, 52, 90),),
            "dominant_line": (NoteEvent(0.1, 0.5, 64, 90),),
            "top_line": (NoteEvent(0.1, 0.5, 76, 90),),
            "harmony_stack": (
                NoteEvent(0.1, 0.5, 52, 90),
                NoteEvent(0.1, 0.5, 64, 90),
                NoteEvent(0.1, 0.5, 76, 90),
            ),
        },
        diagnostics=SimpleNamespace(to_dict=lambda: {"voices": 3}),
    )
    observed_configs = []

    def transcribe(path: Path, *, config: object) -> object:
        observed_configs.append(config)
        return (
            lead_transcription
            if getattr(config, "role") == "lead"
            else backing_transcription
        )

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
    assert result["policy"]["polyphonic_tracker"] == "basic_pitch"
    assert result["policy"]["bpm"] == 136.0
    assert [config.role for config in observed_configs] == ["lead", "backing"]
    assert all(config.bpm == 136.0 for config in observed_configs)
    hypotheses = result["candidate"]["register_hypotheses"]["variants"]
    assert set(hypotheses) == {
        "lowest_line",
        "dominant_line",
        "top_line",
        "harmony_stack",
    }
    assert hypotheses["lowest_line"]["candidate"]["note_count"] == 1
    assert result["policy"]["lead_backing_role_assignment_inferred"] is False
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


def test_accepts_native_attempt_evidence_without_promoting_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, outputs = _native_attempt_fixture(tmp_path / "native")
    monkeypatch.setattr(
        evaluation,
        "_inspect_attempt_pcm24",
        lambda _root, *, role: next(item for item in outputs if item["role"] == role),
    )

    worker, vocals = evaluation._load_verified_vocal_source(report)

    assert vocals == report.parent / "staging/quarantine/STEMS/vocals.wav"
    assert worker["candidate_id"] == "mlx-melroformer-kim-vocal-2"
    assert worker["checkpoint_sha256"] == CONVERSION_CHECKPOINT_SHA256
    assert worker["vocal_pcm24_sha256"] == _digest("native-vocals")
    assert worker["network_denial_bound_to_model_worker"] is True
    assert worker["pcm24_quarantine_bound_to_model_worker"] is True


def test_rejects_changed_native_attempt_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, outputs = _native_attempt_fixture(tmp_path / "native")
    monkeypatch.setattr(
        evaluation,
        "_inspect_attempt_pcm24",
        lambda _root, *, role: next(item for item in outputs if item["role"] == role),
    )
    document = json.loads(report.read_text(encoding="utf-8"))
    document["permissions"]["accepted"] = True
    report.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="native attempt evidence differs"):
        evaluation._load_verified_vocal_source(report)


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


def test_control_notes_accept_two_known_independent_packs(tmp_path: Path) -> None:
    report = _control_fixture(
        tmp_path / "controls",
        pack_ids=("local-htdemucs", "moises"),
    )
    document = json.loads(report.read_text(encoding="utf-8"))

    result = evaluation._load_control_notes(report.parent, document)

    assert list(result) == ["local-htdemucs", "moises"]


@pytest.mark.parametrize(
    "pack_ids",
    [
        ("local-htdemucs",),
        ("moises", "suno-a"),
        ("local-htdemucs", "unknown"),
    ],
)
def test_control_notes_reject_insufficient_or_unknown_control_sets(
    tmp_path: Path, pack_ids: tuple[str, ...]
) -> None:
    report = _control_fixture(tmp_path / "controls", pack_ids=pack_ids)
    document = json.loads(report.read_text(encoding="utf-8"))

    with pytest.raises(ValueError, match="controls differ"):
        evaluation._load_control_notes(report.parent, document)


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


def _native_attempt_fixture(root: Path) -> tuple[Path, list[dict[str, object]]]:
    root.mkdir(parents=True)
    request_sha256 = _digest("request")
    receipt_payload: dict[str, object] = {
        "schema": "sunofriend.private-melroformer-native-coordinator.v1",
        "status": "private_native_worker_complete_and_terminal",
        "request_sha256": request_sha256,
        "lifecycle": {"terminal": True},
        "permissions": {"accepted": False},
    }
    terminal_receipt_sha256 = hashlib.sha256(
        canonical_json_bytes(receipt_payload)
    ).hexdigest()
    receipt = {
        **receipt_payload,
        "receipt_sha256": terminal_receipt_sha256,
    }
    receipt_path = root / "native-attempt-receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    receipt_path.chmod(0o600)
    outputs: list[dict[str, object]] = [
        {
            "role": role,
            "bytes": 3_969_044,
            "sha256": _digest(f"native-{role}"),
            "geometry": {
                "sample_rate": 44_100,
                "channels": 2,
                "sample_width_bytes": 3,
                "frames": 661_500,
            },
        }
        for role in ("instrumental", "vocals")
    ]
    payload: dict[str, object] = {
        "schema": "sunofriend.private-kim-native-attempt-evidence.v1",
        "status": "private_native_attempt_verified_not_selected",
        "evidence_scope": "private_local_execution_and_output_binding_only",
        "candidate_id": "mlx-melroformer-kim-vocal-2",
        "bindings": {
            "request_sha256": request_sha256,
            "terminal_receipt_sha256": terminal_receipt_sha256,
            "worker_source_sha256": _digest("worker"),
            "checkpoint_sha256": CONVERSION_CHECKPOINT_SHA256,
            "checkpoint_bytes": CONVERSION_CHECKPOINT_BYTES,
            "authorisation_report_sha256": _digest("authorisation"),
            "source_manifest_sha256": _digest("source"),
            "companion_manifest_sha256": _digest("companions"),
        },
        "outputs": outputs,
        "conclusion": {
            "native_execution_terminal": True,
            "network_denial_bound_to_model_worker": True,
            "pcm24_quarantine_bound_to_model_worker": True,
            "parent_staging_verification_complete": True,
            "checkpoint_remeasured_and_closed": True,
            "listening_quality_established": False,
        },
        "permissions": {
            "accepted": False,
            "automatic_selection": False,
            "source_graph_activation": False,
            "simple_mode_available": False,
            "studio_import_available": False,
            "product_route_permitted": False,
            "publication_permitted": False,
        },
        "limitations": ["fixture"],
    }
    document = {
        **payload,
        "evidence_sha256": hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
    }
    report = root / "native-attempt-evidence.json"
    report.write_text(json.dumps(document), encoding="utf-8")
    report.chmod(0o600)
    return report, outputs


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _control_fixture(
    root: Path,
    *,
    pack_ids: tuple[str, ...] = (
        "local-htdemucs",
        "moises",
        "suno-a",
        "suno-b",
    ),
) -> Path:
    root.mkdir()
    packs = {}
    artifacts = {}
    for index, pack_id in enumerate(pack_ids):
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
