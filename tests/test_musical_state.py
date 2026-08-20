from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pytest
import soundfile

from sunofriend.audio_formats import file_sha256
from sunofriend.musical_state import (
    MUSICAL_STATE_SCHEMA,
    VOCAL_COMP_TIMELINE_SCHEMA,
    VOCAL_PERFORMANCE_STATE_SCHEMA,
    create_vocal_musical_state,
    plan_vocal_musical_state,
    validate_musical_state,
)
from sunofriend.source_receipt import document_sha256


def test_vocal_musical_state_preserves_audio_native_unreviewed_evidence(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    source_hashes = {
        path.name: file_sha256(path) for path in fixture["take_dir"].glob("*.wav")
    }

    plan = plan_vocal_musical_state(
        fixture["take_dir"],
        lyrics=fixture["lyrics"],
        phrase_timeline=fixture["timeline"],
        reference_vocal=fixture["reference"],
        rights_category="owned",
        processing_chain="same-gentle-chain",
        bpm=96.0,
        confirm_common_recorded_zero=True,
        confirm_timeline_reviewed=True,
    )

    assert plan["schema"] == MUSICAL_STATE_SCHEMA
    assert plan["status"] == "ready_no_midi_required"
    assert plan["method_natures"] == ["D", "H"]
    assert plan["midi_required"] is False
    assert plan["network_used"] is False
    assert not any(plan["effects"].values())

    out_dir = tmp_path / "musical-state"
    result = create_vocal_musical_state(
        fixture["take_dir"],
        out_dir=out_dir,
        lyrics=fixture["lyrics"],
        phrase_timeline=fixture["timeline"],
        reference_vocal=fixture["reference"],
        rights_category="owned",
        processing_chain="same-gentle-chain",
        bpm=96.0,
        confirm_common_recorded_zero=True,
        confirm_timeline_reviewed=True,
    )

    manifest_path = out_dir / "musical-state.json"
    persisted = manifest_path.read_text(encoding="utf-8")
    assert result["schema"] == MUSICAL_STATE_SCHEMA
    assert result["status"] == "complete_unreviewed_no_selection"
    assert result["method_natures"] == ["D", "H"]
    assert str(tmp_path) not in persisted
    assert os.stat(out_dir).st_mode & 0o777 == 0o700
    assert os.stat(manifest_path).st_mode & 0o777 == 0o600

    vocal = result["vocal_performance_state"]
    assert vocal["schema"] == VOCAL_PERFORMANCE_STATE_SCHEMA
    assert vocal["selection_authority"] == "human_only"
    assert vocal["explicit_phrase_decisions"] == []
    assert vocal["edit_maps"] == []
    assert vocal["correction_derivatives"] == []
    assert result["optional_derived_evidence"] == {"midi": [], "notes": []}
    assert result["training"]["explicit_labels"] == []
    assert result["training"]["training_eligible"] is False
    assert result["network_used"] is False
    assert not any(result["effects"].values())
    assert validate_musical_state(manifest_path, root=out_dir) == result

    assert source_hashes == {
        path.name: file_sha256(path) for path in fixture["take_dir"].glob("*.wav")
    }
    copied_hashes = {row["label"]: row["audio"]["sha256"] for row in vocal["takes"]}
    assert copied_hashes == source_hashes


def test_wavex_reference_is_accepted_as_exact_hash_bound_wav(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    wavex = tmp_path / "reference-wavex.wav"
    samples = np.zeros(8_000 * 2, dtype=np.float32)
    soundfile.write(wavex, samples, 8_000, subtype="PCM_24", format="WAVEX")

    plan = plan_vocal_musical_state(
        fixture["take_dir"],
        lyrics=fixture["lyrics"],
        phrase_timeline=fixture["timeline"],
        reference_vocal=wavex,
        rights_category="owned",
        processing_chain="dry",
        confirm_common_recorded_zero=True,
        confirm_timeline_reviewed=True,
    )

    assert plan["reference_vocal"]["audio"]["format"] == "WAV"
    assert plan["reference_vocal"]["audio"]["subtype"] == "PCM_24"


def test_vocal_musical_state_requires_explicit_alignment_and_review(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    arguments = {
        "lyrics": fixture["lyrics"],
        "phrase_timeline": fixture["timeline"],
        "rights_category": "owned",
        "processing_chain": "dry",
    }

    with pytest.raises(ValueError, match="confirm_common_recorded_zero"):
        plan_vocal_musical_state(fixture["take_dir"], **arguments)
    with pytest.raises(ValueError, match="confirm_timeline_reviewed"):
        plan_vocal_musical_state(
            fixture["take_dir"],
            confirm_common_recorded_zero=True,
            **arguments,
        )


def test_vocal_musical_state_detects_copied_audio_tampering(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    out_dir, _ = _create_state(tmp_path, fixture)
    copied_take = out_dir / "SOURCES" / "takes" / "take-001.wav"
    with copied_take.open("r+b") as handle:
        original = handle.read(1)
        handle.seek(0)
        handle.write(bytes([original[0] ^ 0xFF]))

    with pytest.raises(ValueError, match="artifact hash changed"):
        validate_musical_state(out_dir / "musical-state.json", root=out_dir)


@pytest.mark.parametrize(
    ("path_value", "description"),
    (
        ("/Users/private/lyrics.txt", "POSIX absolute path"),
        ("C:/Users/private/lyrics.txt", "Windows absolute path"),
    ),
)
def test_vocal_musical_state_rejects_absolute_paths(
    tmp_path: Path,
    path_value: str,
    description: str,
) -> None:
    fixture = _fixture(tmp_path)
    _, manifest = _create_state(tmp_path, fixture)
    changed = deepcopy(manifest)
    changed["lyrics"]["canonical"]["path"] = path_value
    _rehash(changed)

    with pytest.raises(ValueError, match="absolute path|safe and relative"):
        validate_musical_state(changed)


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda state: state["optional_derived_evidence"]["midi"].append(
                {"artifact_id": "unreviewed-midi"}
            ),
            "note evidence",
        ),
        (
            lambda state: state["training"].update({"training_eligible": True}),
            "training eligible",
        ),
        (
            lambda state: state["effects"].update({"audio_comp_rendered": True}),
            "product effect",
        ),
        (
            lambda state: state["vocal_performance_state"][
                "explicit_phrase_decisions"
            ].append({"phrase_id": "phrase-001", "selected_take": "take-001"}),
            "explicit phrase decision",
        ),
    ),
    ids=("midi", "training", "render", "selection"),
)
def test_unreviewed_vocal_state_rejects_derived_authority_claims(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    fixture = _fixture(tmp_path)
    _, manifest = _create_state(tmp_path, fixture)
    changed = deepcopy(manifest)
    mutate(changed)
    _rehash(changed)

    with pytest.raises(ValueError, match=message):
        validate_musical_state(changed)


def _fixture(tmp_path: Path) -> dict[str, Path]:
    take_dir = tmp_path / "takes"
    take_dir.mkdir()
    sample_rate = 8_000
    seconds = 1.25
    time = np.arange(round(sample_rate * seconds), dtype=np.float64) / sample_rate
    for index, frequency in enumerate((196.0, 220.0), 1):
        audio = (0.15 * np.sin(2.0 * np.pi * frequency * time)).astype(np.float32)
        soundfile.write(
            take_dir / f"attempt-{index:02d}.wav",
            audio,
            sample_rate,
            subtype="PCM_24",
        )
    reference = tmp_path / "reference-vocal.wav"
    reference_audio = (0.10 * np.sin(2.0 * np.pi * 233.08 * time)).astype(np.float32)
    soundfile.write(reference, reference_audio, sample_rate, subtype="PCM_24")

    lyrics = tmp_path / "lyrics.txt"
    lyrics.write_text("And tell myself those comforting lies\n", encoding="utf-8")
    timeline = tmp_path / "reviewed-timeline.json"
    timeline.write_text(
        json.dumps(
            {
                "schema": VOCAL_COMP_TIMELINE_SCHEMA,
                "status": "reviewed",
                "phrases": [
                    {
                        "phrase_id": "phrase-001",
                        "start_seconds": 0.20,
                        "end_seconds": 0.90,
                        "lyrics": "And tell myself those comforting lies",
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "take_dir": take_dir,
        "reference": reference,
        "lyrics": lyrics,
        "timeline": timeline,
    }


def _create_state(
    tmp_path: Path, fixture: dict[str, Path]
) -> tuple[Path, dict[str, Any]]:
    out_dir = tmp_path / "state-for-validation"
    manifest = create_vocal_musical_state(
        fixture["take_dir"],
        out_dir=out_dir,
        lyrics=fixture["lyrics"],
        phrase_timeline=fixture["timeline"],
        reference_vocal=fixture["reference"],
        rights_category="owned",
        processing_chain="dry",
        confirm_common_recorded_zero=True,
        confirm_timeline_reviewed=True,
    )
    return out_dir, manifest


def _rehash(document: dict[str, Any]) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)
