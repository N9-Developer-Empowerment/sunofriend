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
    VOCAL_PERFORMANCE_STATE_SCHEMA_V3,
    admit_vocal_phrase_capture,
    create_vocal_musical_state,
    validate_musical_state,
)
from sunofriend.source_receipt import canonical_json_bytes, document_sha256
from sunofriend.vocal_capture import (
    VOCAL_CAPTURE_SCHEMA,
    create_vocal_capture,
)


SAMPLE_RATE = 8_000
PHRASE_ID = "cause-the-heart-sees-exactly-what-it-wants-to-see"
PHRASE_TEXT = "'Cause the heart sees exactly what it wants to see"
PHRASE_START = 47.62
PHRASE_END = 56.12
DESTINATION_START_FRAME = round(PHRASE_START * SAMPLE_RATE)
DESTINATION_END_FRAME = round(PHRASE_END * SAMPLE_RATE)
PHRASE_FRAMES = DESTINATION_END_FRAME - DESTINATION_START_FRAME
PRE_GUARD_FRAMES = SAMPLE_RATE // 2
POST_GUARD_FRAMES = SAMPLE_RATE // 2
CAPTURE_FRAMES = PRE_GUARD_FRAMES + PHRASE_FRAMES + POST_GUARD_FRAMES


def test_admit_short_capture_creates_v3_without_mutating_v2_evidence(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    base_manifest_path = fixture["base_manifest"]
    base_dir = base_manifest_path.parent
    base = validate_musical_state(base_manifest_path, root=base_dir)
    base_manifest_bytes = base_manifest_path.read_bytes()
    base_artifacts = _artifact_snapshot(base, base_dir)

    out_dir = tmp_path / "derived-v3"
    result = admit_vocal_phrase_capture(
        base_manifest_path,
        capture_wav=fixture["capture_wav"],
        capture_receipt=fixture["capture_receipt"],
        out_dir=out_dir,
        label="Browser attempt 1",
    )

    assert base_manifest_path.read_bytes() == base_manifest_bytes
    assert _artifact_snapshot(base, base_dir) == base_artifacts
    assert result["schema"] == MUSICAL_STATE_SCHEMA
    assert result["status"] == "complete_unreviewed_no_selection"
    assert result["document_sha256"] != base["document_sha256"]
    assert result["lineage"]["operation"] == "admit_vocal_phrase_capture"
    assert result["lineage"]["parent"]["schema"] == MUSICAL_STATE_SCHEMA
    assert result["lineage"]["parent"]["document_sha256"] == base["document_sha256"]
    assert result["lineage"]["admitted_capture"] == {
        "schema": VOCAL_CAPTURE_SCHEMA,
        "document_sha256": fixture["receipt"]["document_sha256"],
        "audio_sha256": fixture["receipt"]["audio"]["sha256"],
    }
    parent_manifest_record = result["lineage"]["parent"]["manifest"]
    assert (
        out_dir / parent_manifest_record["path"]
    ).read_bytes() == base_manifest_bytes
    assert parent_manifest_record["sha256"] == file_sha256(base_manifest_path)

    vocal = result["vocal_performance_state"]
    base_vocal = base["vocal_performance_state"]
    assert vocal["schema"] == VOCAL_PERFORMANCE_STATE_SCHEMA_V3
    assert base_vocal["schema"] == VOCAL_PERFORMANCE_STATE_SCHEMA
    for key, value in base_vocal.items():
        if key != "schema":
            assert vocal[key] == value
    assert len(vocal["phrase_captures"]) == 1
    admitted = vocal["phrase_captures"][0]
    assert admitted["source_id"] == fixture["receipt"]["capture"]["source_id"]
    assert admitted["source_class"] == "human_vocal_phrase_capture"
    assert admitted["label"] == "Browser attempt 1"
    assert admitted["review_status"] == "stored_unreviewed"
    assert admitted["phrase"] == fixture["receipt"]["phrase"]
    assert admitted["placement"] == fixture["receipt"]["placement"]
    assert admitted["audio_properties"] == {
        "format": "WAV",
        "subtype": "PCM_24",
        "sample_rate": SAMPLE_RATE,
        "channels": 1,
        "frames": CAPTURE_FRAMES,
        "duration_seconds": CAPTURE_FRAMES / SAMPLE_RATE,
    }
    assert admitted["authority"] == fixture["receipt"]["authority"]
    assert admitted["capture_receipt"]["schema"] == VOCAL_CAPTURE_SCHEMA
    assert (
        admitted["capture_receipt"]["document_sha256"]
        == fixture["receipt"]["document_sha256"]
    )

    copied_audio = out_dir / admitted["audio"]["path"]
    copied_receipt = out_dir / admitted["capture_receipt"]["artifact"]["path"]
    assert copied_audio.read_bytes() == fixture["capture_wav"].read_bytes()
    assert copied_receipt.read_bytes() == fixture["capture_receipt"].read_bytes()
    assert admitted["audio"]["sha256"] == file_sha256(fixture["capture_wav"])
    assert admitted["audio"]["bytes"] == fixture["capture_wav"].stat().st_size

    assert (
        _artifact_snapshot(base, base_dir)
        == _artifact_snapshot(result, out_dir)[: len(base_artifacts)]
    )
    source_ids = [row["source_id"] for row in vocal["takes"]]
    if vocal["reference"] is not None:
        source_ids.append(vocal["reference"]["source_id"])
    source_ids.extend(row["source_id"] for row in vocal["phrase_captures"])
    assert len(source_ids) == len(set(source_ids))
    assert vocal["explicit_phrase_decisions"] == []
    assert vocal["edit_maps"] == []
    assert vocal["correction_derivatives"] == []
    assert result["training"]["explicit_labels"] == []
    assert result["training"]["training_eligible"] is False
    assert not any(result["effects"].values())
    assert (
        validate_musical_state(out_dir / "musical-state.json", root=out_dir) == result
    )

    assert os.stat(out_dir).st_mode & 0o777 == 0o700
    for path in out_dir.rglob("*"):
        expected_mode = 0o700 if path.is_dir() else 0o600
        assert os.stat(path).st_mode & 0o777 == expected_mode


def test_admission_is_fresh_and_does_not_overwrite_existing_output(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    out_dir = tmp_path / "existing"
    out_dir.mkdir()
    marker = out_dir / "keep.txt"
    marker.write_text("user-owned\n", encoding="utf-8")

    with pytest.raises(ValueError, match="exists|fresh"):
        _admit(fixture, out_dir)

    assert marker.read_text(encoding="utf-8") == "user-owned\n"
    assert list(out_dir.iterdir()) == [marker]


def test_second_admission_appends_a_sibling_without_changing_the_first(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    first_dir = tmp_path / "first-derived"
    first = _admit(fixture, first_dir)
    first_bytes = (first_dir / "musical-state.json").read_bytes()
    first_capture = deepcopy(first["vocal_performance_state"]["phrase_captures"][0])

    second_wav = tmp_path / "browser-capture-002.wav"
    time = np.arange(CAPTURE_FRAMES, dtype=np.float64) / SAMPLE_RATE
    audio = (0.10 * np.sin(2.0 * np.pi * 233.08 * time)).astype(np.float32)
    soundfile.write(second_wav, audio, SAMPLE_RATE, subtype="PCM_24")
    second_arguments = _capture_arguments(second_wav)
    second_arguments["capture_id"] = "attempt-002"
    second_receipt = create_vocal_capture(first, **second_arguments)
    second_receipt_path = tmp_path / "browser-capture-002.json"
    second_receipt_path.write_text(
        json.dumps(second_receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    second_dir = tmp_path / "second-derived"
    result = admit_vocal_phrase_capture(
        first_dir / "musical-state.json",
        capture_wav=second_wav,
        capture_receipt=second_receipt_path,
        out_dir=second_dir,
    )

    assert (first_dir / "musical-state.json").read_bytes() == first_bytes
    captures = result["vocal_performance_state"]["phrase_captures"]
    assert len(captures) == 2
    assert captures[0] == first_capture
    assert captures[1]["source_id"] == second_receipt["capture"]["source_id"]
    assert result["lineage"]["parent"]["schema"] == MUSICAL_STATE_SCHEMA
    assert result["lineage"]["parent"]["document_sha256"] == first["document_sha256"]
    assert (
        validate_musical_state(second_dir / "musical-state.json", root=second_dir)
        == result
    )


def test_admission_rejects_wav_bytes_that_do_not_match_receipt(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    with fixture["capture_wav"].open("r+b") as handle:
        handle.seek(-1, os.SEEK_END)
        final = handle.read(1)
        handle.seek(-1, os.SEEK_END)
        handle.write(bytes([final[0] ^ 0xFF]))

    with pytest.raises(
        ValueError, match="audio.*SHA-256|capture.*SHA-256|audio.*hash|WAV.*hash"
    ):
        _admit(fixture, tmp_path / "wrong-hash")


def test_admission_rejects_wav_geometry_that_disagrees_with_receipt(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    wrong = tmp_path / "wrong-geometry.wav"
    soundfile.write(
        wrong,
        np.zeros(CAPTURE_FRAMES, dtype=np.float32),
        SAMPLE_RATE * 2,
        subtype="PCM_24",
    )
    receipt_arguments = _capture_arguments(wrong)
    receipt = create_vocal_capture(fixture["base"], **receipt_arguments)
    receipt_path = tmp_path / "wrong-geometry-receipt.json"
    receipt_path.write_bytes(canonical_json_bytes(receipt))

    with pytest.raises(ValueError, match="geometry|frame|audio"):
        admit_vocal_phrase_capture(
            fixture["base_manifest"],
            capture_wav=wrong,
            capture_receipt=receipt_path,
            out_dir=tmp_path / "wrong-geometry-output",
        )


def test_admission_rejects_receipt_bound_to_another_musical_state(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    other = _create_base_state(tmp_path / "other-base", bpm=97.0)

    with pytest.raises(ValueError, match="musical.state|state.*SHA-256|state.*hash"):
        admit_vocal_phrase_capture(
            other / "musical-state.json",
            capture_wav=fixture["capture_wav"],
            capture_receipt=fixture["capture_receipt"],
            out_dir=tmp_path / "cross-state-output",
        )


@pytest.mark.parametrize("linked_input", ("capture_wav", "capture_receipt"))
def test_admission_rejects_symlinked_capture_evidence(
    tmp_path: Path, linked_input: str
) -> None:
    fixture = _fixture(tmp_path)
    original = fixture[linked_input]
    linked = tmp_path / f"linked-{original.name}"
    linked.symlink_to(original)
    arguments = {
        "capture_wav": fixture["capture_wav"],
        "capture_receipt": fixture["capture_receipt"],
    }
    arguments[linked_input] = linked

    with pytest.raises(ValueError, match="linked|symlink|unsafe"):
        admit_vocal_phrase_capture(
            fixture["base_manifest"],
            out_dir=tmp_path / f"linked-{linked_input}-output",
            **arguments,
        )


def test_admission_rejects_tampered_capture_receipt_document(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    changed = deepcopy(fixture["receipt"])
    changed["placement"]["source_phrase_start_frame"] += 1
    fixture["capture_receipt"].write_bytes(canonical_json_bytes(changed))

    with pytest.raises(ValueError, match="document SHA-256|document.*hash"):
        _admit(fixture, tmp_path / "tampered-receipt")


@pytest.mark.parametrize(
    "label",
    ("/Users/private/take.wav", "C:/Users/private/take.wav", "../take.wav"),
)
def test_admission_rejects_path_like_labels(tmp_path: Path, label: str) -> None:
    fixture = _fixture(tmp_path)
    with pytest.raises(ValueError, match="label|path|portable"):
        admit_vocal_phrase_capture(
            fixture["base_manifest"],
            capture_wav=fixture["capture_wav"],
            capture_receipt=fixture["capture_receipt"],
            out_dir=tmp_path / "unsafe-label",
            label=label,
        )


def test_v3_validation_rejects_silent_decision_or_product_authority(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    out_dir = tmp_path / "derived"
    result = _admit(fixture, out_dir)

    mutations: tuple[tuple[Callable[[dict[str, Any]], None], str], ...] = (
        (
            lambda row: row["vocal_performance_state"][
                "explicit_phrase_decisions"
            ].append({"phrase_id": PHRASE_ID, "outcome": "human_take"}),
            "decision",
        ),
        (
            lambda row: row["vocal_performance_state"]["phrase_captures"][0][
                "authority"
            ].update({"selection_authority": "human"}),
            "authority|selection",
        ),
        (
            lambda row: row["effects"].update({"audio_comp_rendered": True}),
            "effect|render",
        ),
        (
            lambda row: row["training"].update({"training_eligible": True}),
            "training",
        ),
    )
    for mutate, message in mutations:
        changed = deepcopy(result)
        mutate(changed)
        _rehash(changed)
        with pytest.raises(ValueError, match=message):
            validate_musical_state(changed)


def test_duplicate_capture_source_id_is_not_silently_admitted_twice(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    first_dir = tmp_path / "first"
    result = _admit(fixture, first_dir)
    changed = deepcopy(result)
    changed["vocal_performance_state"]["phrase_captures"].append(
        deepcopy(changed["vocal_performance_state"]["phrase_captures"][0])
    )
    _rehash(changed)

    with pytest.raises(ValueError, match="duplicate|source.*ID|already.*admitted"):
        validate_musical_state(changed)


def _admit(fixture: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    return admit_vocal_phrase_capture(
        fixture["base_manifest"],
        capture_wav=fixture["capture_wav"],
        capture_receipt=fixture["capture_receipt"],
        out_dir=out_dir,
    )


def _fixture(tmp_path: Path) -> dict[str, Any]:
    base_dir = _create_base_state(tmp_path / "base")
    base_manifest = base_dir / "musical-state.json"
    base = validate_musical_state(base_manifest, root=base_dir)
    capture_wav = tmp_path / "browser-capture.wav"
    time = np.arange(CAPTURE_FRAMES, dtype=np.float64) / SAMPLE_RATE
    audio = (0.12 * np.sin(2.0 * np.pi * 220.0 * time)).astype(np.float32)
    soundfile.write(capture_wav, audio, SAMPLE_RATE, subtype="PCM_24")
    receipt = create_vocal_capture(base, **_capture_arguments(capture_wav))
    capture_receipt = tmp_path / "browser-capture.json"
    capture_receipt.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "base": base,
        "base_manifest": base_manifest,
        "capture_wav": capture_wav,
        "capture_receipt": capture_receipt,
        "receipt": receipt,
    }


def _create_base_state(root: Path, *, bpm: float = 86.00005160003096) -> Path:
    take_dir = root / "inputs" / "takes"
    take_dir.mkdir(parents=True)
    frames = round(60.0 * SAMPLE_RATE)
    time = np.arange(frames, dtype=np.float64) / SAMPLE_RATE
    for index, frequency in enumerate((196.0, 220.0), 1):
        audio = (0.08 * np.sin(2.0 * np.pi * frequency * time)).astype(np.float32)
        soundfile.write(
            take_dir / f"attempt-{index:02d}.wav",
            audio,
            SAMPLE_RATE,
            subtype="PCM_24",
        )
    lyrics = root / "inputs" / "lyrics.txt"
    lyrics.write_text(PHRASE_TEXT + "\n", encoding="utf-8")
    timeline = root / "inputs" / "timeline.json"
    timeline.write_text(
        json.dumps(
            {
                "schema": VOCAL_COMP_TIMELINE_SCHEMA,
                "status": "reviewed",
                "phrases": [
                    {
                        "phrase_id": PHRASE_ID,
                        "start_seconds": PHRASE_START,
                        "end_seconds": PHRASE_END,
                        "lyrics": PHRASE_TEXT,
                    }
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    out_dir = root / "musical-state"
    create_vocal_musical_state(
        take_dir,
        out_dir=out_dir,
        lyrics=lyrics,
        phrase_timeline=timeline,
        rights_category="owned",
        processing_chain="dry",
        bpm=bpm,
        confirm_common_recorded_zero=True,
        confirm_timeline_reviewed=True,
    )
    return out_dir


def _capture_arguments(capture_wav: Path) -> dict[str, Any]:
    return {
        "capture_id": "attempt-001",
        "phrase_id": PHRASE_ID,
        "cue_id": "backing-plus-reviewed-melody",
        "cue_asset_sha256": "a" * 64,
        "audio_sha256": file_sha256(capture_wav),
        "audio_bytes": capture_wav.stat().st_size,
        "sample_rate": SAMPLE_RATE,
        "frame_count": CAPTURE_FRAMES,
        "phrase_start_frame": PRE_GUARD_FRAMES,
        "phrase_end_frame": PRE_GUARD_FRAMES + PHRASE_FRAMES,
        "destination_start_seconds": PHRASE_START,
        "destination_end_seconds": PHRASE_END,
        "pre_guard_frames": PRE_GUARD_FRAMES,
        "post_guard_frames": POST_GUARD_FRAMES,
        "requested_processing": {
            "echo_cancellation": False,
            "noise_suppression": False,
            "automatic_gain_control": False,
        },
        "actual_processing": {
            "echo_cancellation": False,
            "noise_suppression": False,
            "automatic_gain_control": False,
            "sample_rate": SAMPLE_RATE,
            "channel_count": 1,
        },
    }


def _artifact_snapshot(
    manifest: dict[str, Any], root: Path
) -> list[tuple[str, int, str]]:
    records = sorted(_file_records(manifest), key=lambda row: str(row["path"]))
    return [
        (
            str(row["path"]),
            int(row["bytes"]),
            file_sha256(root / str(row["path"])),
        )
        for row in records
        if not str(row["path"]).startswith(
            ("LINEAGE/", "RECEIPTS/", "SOURCES/phrase-captures/")
        )
    ]


def _file_records(value: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if {"path", "bytes", "sha256"}.issubset(value):
            records.append(value)
        for item in value.values():
            records.extend(_file_records(item))
    elif isinstance(value, list):
        for item in value:
            records.extend(_file_records(item))
    return records


def _rehash(document: dict[str, Any]) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)
