from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
from typing import Any

import numpy as np
import pytest
import soundfile as sf

from sunofriend.audio_formats import file_sha256
from sunofriend.musical_state import (
    admit_vocal_phrase_capture,
    create_vocal_musical_state,
)
from sunofriend.source_receipt import canonical_json_bytes, document_sha256
from sunofriend.vocal_comp_render import (
    VOCAL_DRY_EDIT_MAP_SCHEMA,
    VOCAL_DRY_RENDER_PLAN_SCHEMA,
    create_dry_vocal_comp_plan,
    create_dry_vocal_render_authorization,
    render_dry_vocal_comp,
    validate_dry_vocal_comp_result,
    verify_dry_vocal_comp_round_trip,
)
from sunofriend.vocal_capture import create_vocal_capture
from sunofriend.vocal_phrase_decision import (
    create_phrase_decision,
    create_vocal_render_source_map,
    create_vocal_source_map as create_legacy_vocal_source_map,
    validate_phrase_decision,
)

create_vocal_source_map = create_vocal_render_source_map


SAMPLE_RATE = 8_000


def test_phrase_only_preview_preserves_song_placement_without_whole_song_claim(
    tmp_path: Path,
) -> None:
    state_path, state = _state(
        tmp_path,
        phrases=[("phrase-1", 1.0, 2.0, "The heart sees")],
        duration=4.0,
        stereo_reference=True,
    )
    decision = create_phrase_decision(
        state, "phrase-1", "human_take", source_id="take-001"
    )
    source_map = create_vocal_source_map(state, [decision])
    authorization = _authorization(
        state_path, source_map, render_scope="phrase_only", phrase_id="phrase-1"
    )

    plan = create_dry_vocal_comp_plan(
        state_path,
        source_map,
        authorization,
        render_scope="phrase_only",
        phrase_id="phrase-1",
    )

    assert plan["schema"] == VOCAL_DRY_RENDER_PLAN_SCHEMA
    assert plan["status"] == "ready_phrase_only_dry_uncorrected_preview"
    assert plan["coverage"] == {
        "reviewed_roster_phrase_count": 1,
        "rendered_phrase_count": 1,
        "source_segment_count": 1,
        "whole_song_coverage_claimed": False,
        "unresolved_count": 0,
        "undecided_count": 0,
    }
    assert plan["horizon"]["frames"] == SAMPLE_RATE
    assert plan["horizon"]["destination_origin_song_frame"] == SAMPLE_RATE
    assert plan["horizon"]["destination_end_song_frame"] == SAMPLE_RATE * 2
    assert plan["segments"][0]["destination_start_frame"] == 0
    assert plan["segments"][0]["destination_end_frame"] == SAMPLE_RATE
    assert plan["segments"][0]["song_destination_start_frame"] == SAMPLE_RATE
    assert plan["segments"][0]["song_destination_end_frame"] == SAMPLE_RATE * 2
    assert plan["joins"] == []

    with pytest.raises(ValueError, match="confirmation"):
        render_dry_vocal_comp(
            state_path,
            source_map,
            authorization,
            plan,
            out_dir=tmp_path / "not-created",
        )

    result = render_dry_vocal_comp(
        state_path,
        source_map,
        authorization,
        plan,
        out_dir=tmp_path / "phrase-preview",
        confirm_dry_uncorrected_render=True,
    )

    assert result["status"] == "complete_unreviewed_uncorrected_phrase_preview"
    assert result["render_scope"] == "phrase_only"
    assert result["phrase_id"] == "phrase-1"
    assert result["review"] == {
        "status": "not_reviewed",
        "playback_creates_decision": False,
        "join_review_complete": False,
        "selected_for_product": False,
    }
    assert result["processing"] == {
        "pitch_correction": False,
        "timing_correction": False,
        "resampling": False,
        "gain_trim": False,
        "normalisation": False,
        "limiting": False,
    }
    output, rate = sf.read(
        tmp_path / "phrase-preview/AUDIO/dry-vocal-phrase-preview.wav",
        dtype="int32",
        always_2d=True,
    )
    source, _ = sf.read(
        tmp_path / "state/SOURCES/takes/take-001.wav",
        dtype="int32",
        always_2d=True,
    )
    assert rate == SAMPLE_RATE
    np.testing.assert_array_equal(output, source[SAMPLE_RATE : SAMPLE_RATE * 2])
    edit_map = json.loads(
        (tmp_path / "phrase-preview/TECHNICAL/dry-vocal-edit-map.json").read_text()
    )
    assert edit_map["schema"] == VOCAL_DRY_EDIT_MAP_SCHEMA
    assert edit_map["render_scope"] == "phrase_only"
    assert edit_map["horizon"]["destination_origin_song_frame"] == SAMPLE_RATE
    review = (tmp_path / "phrase-preview/REVIEW/dry-vocal-comp-review.html").read_text()
    assert "Playback creates no decision" in review
    assert "No tuning, timing correction" in review
    assert "no whole-song coverage claim" in review

    verification = verify_dry_vocal_comp_round_trip(
        tmp_path / "phrase-preview", plan=plan, result=result
    )
    assert verification["status"] == "verified_technical_artifacts_unreviewed"
    assert all(verification["checks"].values())
    assert verification["authority"]["human_review_created"] is False

    tampered_audio = tmp_path / "tampered-audio"
    shutil.copytree(tmp_path / "phrase-preview", tampered_audio)
    with (tampered_audio / "AUDIO/dry-vocal-phrase-preview.wav").open("ab") as handle:
        handle.write(b"not-a-valid-receipted-suffix")
    with pytest.raises(ValueError, match="audio file differs"):
        verify_dry_vocal_comp_round_trip(tampered_audio, plan=plan, result=result)

    tampered_edit_map = tmp_path / "tampered-edit-map"
    shutil.copytree(tmp_path / "phrase-preview", tampered_edit_map)
    with (tampered_edit_map / "TECHNICAL/dry-vocal-edit-map.json").open("ab") as handle:
        handle.write(b"\n")
    with pytest.raises(ValueError, match="edit map differs"):
        verify_dry_vocal_comp_round_trip(tampered_edit_map, plan=plan, result=result)

    tampered_review = tmp_path / "tampered-review"
    shutil.copytree(tmp_path / "phrase-preview", tampered_review)
    with (tampered_review / "REVIEW/dry-vocal-comp-review.html").open("ab") as handle:
        handle.write(b"<!-- changed -->")
    with pytest.raises(ValueError, match="review page differs"):
        verify_dry_vocal_comp_round_trip(tampered_review, plan=plan, result=result)

    tampered_receipt = tmp_path / "tampered-receipt"
    shutil.copytree(tmp_path / "phrase-preview", tampered_receipt)
    with (tampered_receipt / "TECHNICAL/dry-vocal-render-receipt.json").open(
        "ab"
    ) as handle:
        handle.write(b"\n")
    with pytest.raises(ValueError, match="receipt file differs"):
        verify_dry_vocal_comp_round_trip(tampered_receipt, plan=plan, result=result)

    extra_file = tmp_path / "extra-file"
    shutil.copytree(tmp_path / "phrase-preview", extra_file)
    extra = extra_file / "TECHNICAL/undeclared.txt"
    extra.write_text("undeclared", encoding="utf-8")
    os.chmod(extra, 0o600)
    with pytest.raises(ValueError, match="file roster"):
        verify_dry_vocal_comp_round_trip(extra_file, plan=plan, result=result)

    linked_artifact = tmp_path / "linked-artifact"
    shutil.copytree(tmp_path / "phrase-preview", linked_artifact)
    linked_review = linked_artifact / "REVIEW/dry-vocal-comp-review.html"
    linked_review.unlink()
    linked_review.symlink_to("../TECHNICAL/dry-vocal-edit-map.json")
    with pytest.raises(ValueError, match="missing or linked"):
        verify_dry_vocal_comp_round_trip(linked_artifact, plan=plan, result=result)

    forged_authority = deepcopy(result)
    forged_authority["release_authority"] = True
    _rehash(forged_authority)
    with pytest.raises(ValueError, match="result fields"):
        validate_dry_vocal_comp_result(forged_authority, plan)

    forged_binding = deepcopy(result)
    forged_binding["binding"]["musical_state_sha256"] = "9" * 64
    _rehash(forged_binding)
    with pytest.raises(ValueError, match="exact binding"):
        validate_dry_vocal_comp_result(forged_binding, plan)

    forged_artifact = deepcopy(result)
    forged_artifact["artifacts"]["dry_vocal_wav"]["relative_path"] = (
        "AUDIO/release-master.wav"
    )
    _rehash(forged_artifact)
    with pytest.raises(ValueError, match="artifact identity"):
        validate_dry_vocal_comp_result(forged_artifact, plan)

    forged_edit_map = deepcopy(result)
    forged_edit_map["binding"]["edit_map_document_sha256"] = "8" * 64
    _rehash(forged_edit_map)
    with pytest.raises(ValueError, match="edit-map binding"):
        validate_dry_vocal_comp_result(forged_edit_map, plan)

    forged_effect = deepcopy(result)
    forged_effect["effects"]["human_review_created"] = True
    _rehash(forged_effect)
    with pytest.raises(ValueError, match="effects"):
        validate_dry_vocal_comp_result(forged_effect, plan)


def test_complete_render_requires_roster_declaration_and_handles_gaps(
    tmp_path: Path,
) -> None:
    state_path, state = _state(
        tmp_path,
        phrases=[
            ("phrase-1", 0.5, 1.0, "First line"),
            ("phrase-2", 1.5, 2.0, "Second line"),
        ],
        duration=3.0,
    )
    decisions = [
        create_phrase_decision(state, "phrase-1", "human_take", source_id="take-001"),
        create_phrase_decision(state, "phrase-2", "human_take", source_id="take-002"),
    ]
    source_map = create_vocal_source_map(state, decisions)
    authorization = _authorization(
        state_path, source_map, render_scope="complete_state_timeline", complete=True
    )
    with pytest.raises(ValueError, match="roster|coverage"):
        create_dry_vocal_comp_plan(
            state_path,
            source_map,
            authorization,
            render_scope="complete_state_timeline",
        )

    state = _declare_complete_roster(state_path)
    decisions = [
        create_phrase_decision(state, "phrase-1", "human_take", source_id="take-001"),
        create_phrase_decision(state, "phrase-2", "human_take", source_id="take-002"),
    ]
    source_map = create_vocal_source_map(state, decisions)
    authorization = _authorization(
        state_path, source_map, render_scope="complete_state_timeline", complete=True
    )
    plan = create_dry_vocal_comp_plan(
        state_path,
        source_map,
        authorization,
        render_scope="complete_state_timeline",
    )

    assert plan["horizon"]["frames"] == SAMPLE_RATE * 3
    assert plan["horizon"]["destination_origin_song_frame"] == 0
    assert [row["kind"] for row in plan["joins"]] == [
        "equal_power_silence_to_source",
        "separated_equal_power_guard_fades",
        "equal_power_source_to_silence",
    ]
    middle = plan["joins"][1]
    assert middle["gap_start_frame"] == SAMPLE_RATE
    assert middle["gap_end_frame"] == SAMPLE_RATE * 3 // 2
    assert middle["left_guard_frames"] == 80
    assert middle["right_guard_frames"] == 80

    result = render_dry_vocal_comp(
        state_path,
        source_map,
        authorization,
        plan,
        out_dir=tmp_path / "complete-comp",
        confirm_dry_uncorrected_render=True,
    )

    assert result["status"] == "complete_unreviewed_uncorrected"
    assert result["effects"]["audio_comp_rendered"] is True
    assert result["effects"]["join_preview_rendered"] is True
    assert result["effects"]["human_review_created"] is False
    assert result["effects"]["training_label_created"] is False
    info = sf.info(tmp_path / "complete-comp/AUDIO/dry-vocal-comp.wav")
    assert (info.samplerate, info.channels, info.frames, info.subtype) == (
        SAMPLE_RATE,
        1,
        SAMPLE_RATE * 3,
        "PCM_24",
    )
    values, _ = sf.read(
        tmp_path / "complete-comp/AUDIO/dry-vocal-comp.wav", always_2d=True
    )
    assert np.max(np.abs(values)) < 1.0
    assert np.count_nonzero(values[SAMPLE_RATE + 80 : SAMPLE_RATE * 3 // 2 - 80]) == 0
    assert (
        tmp_path / "complete-comp/TECHNICAL/dry-vocal-render-receipt.json"
    ).is_file()


def test_incomplete_map_and_contiguous_source_switch_fail_closed(
    tmp_path: Path,
) -> None:
    state_path, state = _state(
        tmp_path,
        phrases=[
            ("phrase-1", 0.0, 1.0, "First line"),
            ("phrase-2", 1.0, 2.0, "Second line"),
        ],
        duration=2.0,
    )
    state = _declare_complete_roster(state_path)
    first = create_phrase_decision(
        state, "phrase-1", "human_take", source_id="take-001"
    )
    partial = create_vocal_source_map(state, [first])
    with pytest.raises(ValueError, match="every phrase|complete"):
        _authorization(
            state_path,
            partial,
            render_scope="complete_state_timeline",
            complete=True,
        )

    switched = create_vocal_source_map(
        state,
        [
            first,
            create_phrase_decision(
                state, "phrase-2", "human_take", source_id="take-002"
            ),
        ],
    )
    switched_authorization = _authorization(
        state_path, switched, render_scope="complete_state_timeline", complete=True
    )
    with pytest.raises(ValueError, match="contiguous source switch"):
        create_dry_vocal_comp_plan(
            state_path,
            switched,
            switched_authorization,
            render_scope="complete_state_timeline",
        )

    continuous = create_vocal_source_map(
        state,
        [
            first,
            create_phrase_decision(
                state, "phrase-2", "human_take", source_id="take-001"
            ),
        ],
    )
    continuous_authorization = _authorization(
        state_path, continuous, render_scope="complete_state_timeline", complete=True
    )
    plan = create_dry_vocal_comp_plan(
        state_path,
        continuous,
        continuous_authorization,
        render_scope="complete_state_timeline",
    )
    assert [row["kind"] for row in plan["joins"]] == ["exact_continuous_same_source"]


def test_stale_source_plan_and_channel_mismatch_are_rejected(tmp_path: Path) -> None:
    state_path, state = _state(
        tmp_path,
        phrases=[("phrase-1", 1.0, 2.0, "The heart sees")],
        duration=4.0,
        stereo_reference=True,
    )
    human_map = create_vocal_source_map(
        state,
        [create_phrase_decision(state, "phrase-1", "human_take", source_id="take-001")],
    )
    authorization = _authorization(
        state_path, human_map, render_scope="phrase_only", phrase_id="phrase-1"
    )
    plan = create_dry_vocal_comp_plan(
        state_path,
        human_map,
        authorization,
        render_scope="phrase_only",
        phrase_id="phrase-1",
    )
    changed = deepcopy(plan)
    changed["segments"][0]["source_end_frame"] -= 1
    changed["document_sha256"] = document_sha256(
        {key: value for key, value in changed.items() if key != "document_sha256"}
    )
    with pytest.raises(ValueError, match="stale|altered"):
        render_dry_vocal_comp(
            state_path,
            human_map,
            authorization,
            changed,
            out_dir=tmp_path / "changed-plan",
            confirm_dry_uncorrected_render=True,
        )

    state = _declare_complete_roster(state_path)
    mixed_map = create_vocal_source_map(
        state,
        [create_phrase_decision(state, "phrase-1", "ai_fallback")],
    )
    with pytest.raises(ValueError, match="AI fallback"):
        _authorization(
            state_path,
            mixed_map,
            render_scope="phrase_only",
            phrase_id="phrase-1",
        )
    ai_authorization = _authorization(
        state_path,
        mixed_map,
        render_scope="phrase_only",
        phrase_id="phrase-1",
        ai=True,
    )
    # The phrase-only AI preview is honestly stereo and needs no conversion.
    ai_plan = create_dry_vocal_comp_plan(
        state_path,
        mixed_map,
        ai_authorization,
        render_scope="phrase_only",
        phrase_id="phrase-1",
    )
    assert ai_plan["horizon"]["channels"] == 2

    human_map = create_vocal_source_map(
        state,
        [create_phrase_decision(state, "phrase-1", "human_take", source_id="take-001")],
    )
    human_complete_authorization = _authorization(
        state_path, human_map, render_scope="complete_state_timeline", complete=True
    )
    with pytest.raises(ValueError, match="clock and channels"):
        create_dry_vocal_comp_plan(
            state_path,
            human_map,
            human_complete_authorization,
            render_scope="complete_state_timeline",
        )


def test_phrase_capture_uses_declared_source_frames_without_padding(
    tmp_path: Path,
) -> None:
    state_path, state = _state(
        tmp_path,
        phrases=[("phrase-1", 1.0, 2.0, "The heart sees")],
        duration=4.0,
    )
    capture_path = tmp_path / "capture.wav"
    capture_frames = SAMPLE_RATE + 800
    time = np.arange(capture_frames, dtype=np.float64) / SAMPLE_RATE
    capture_values = 0.12 * np.sin(2.0 * np.pi * 510.0 * time)
    sf.write(
        capture_path,
        capture_values,
        SAMPLE_RATE,
        format="WAV",
        subtype="PCM_24",
    )
    receipt = create_vocal_capture(
        state,
        capture_id="capture-001",
        phrase_id="phrase-1",
        cue_id="cue-001",
        cue_asset_sha256=state["vocal_performance_state"]["takes"][0]["audio"][
            "sha256"
        ],
        audio_sha256=file_sha256(capture_path),
        audio_bytes=capture_path.stat().st_size,
        sample_rate=SAMPLE_RATE,
        frame_count=capture_frames,
        phrase_start_frame=400,
        phrase_end_frame=400 + SAMPLE_RATE,
        destination_start_seconds=1.0,
        destination_end_seconds=2.0,
        pre_guard_frames=400,
        post_guard_frames=400,
        requested_processing={
            "echo_cancellation": False,
            "noise_suppression": False,
            "automatic_gain_control": False,
        },
        actual_processing={"sample_rate": SAMPLE_RATE, "channel_count": 1},
    )
    child = admit_vocal_phrase_capture(
        state_path,
        capture_wav=capture_path,
        capture_receipt=receipt,
        out_dir=tmp_path / "state-with-capture",
    )
    child_path = tmp_path / "state-with-capture/musical-state.json"
    source_id = "browser-capture-capture-001"
    source_map = create_vocal_source_map(
        child,
        [create_phrase_decision(child, "phrase-1", "human_take", source_id=source_id)],
    )
    authorization = _authorization(
        child_path, source_map, render_scope="phrase_only", phrase_id="phrase-1"
    )
    plan = create_dry_vocal_comp_plan(
        child_path,
        source_map,
        authorization,
        render_scope="phrase_only",
        phrase_id="phrase-1",
    )
    segment = plan["segments"][0]
    assert segment["source_start_frame"] == 400
    assert segment["source_end_frame"] == 400 + SAMPLE_RATE
    assert segment["available_pre_guard_frames"] == 400
    assert segment["available_post_guard_frames"] == 400
    assert segment["destination_start_frame"] == 0
    assert segment["song_destination_start_frame"] == SAMPLE_RATE

    render_dry_vocal_comp(
        child_path,
        source_map,
        authorization,
        plan,
        out_dir=tmp_path / "capture-preview",
        confirm_dry_uncorrected_render=True,
    )
    output, _ = sf.read(
        tmp_path / "capture-preview/AUDIO/dry-vocal-phrase-preview.wav",
        dtype="int32",
        always_2d=True,
    )
    source, _ = sf.read(capture_path, dtype="int32", always_2d=True)
    np.testing.assert_array_equal(output, source[400 : 400 + SAMPLE_RATE])


def test_render_map_reprojects_embedded_decisions_and_rejects_legacy_or_forgery(
    tmp_path: Path,
) -> None:
    state_path, state = _state(
        tmp_path,
        phrases=[("phrase-1", 1.0, 2.0, "The heart sees")],
        duration=3.0,
    )
    decision = create_phrase_decision(
        state, "phrase-1", "human_take", source_id="take-001"
    )
    legacy = create_legacy_vocal_source_map(state, [decision])
    with pytest.raises(ValueError, match="render source map fields|unsupported"):
        _authorization(
            state_path, legacy, render_scope="phrase_only", phrase_id="phrase-1"
        )

    render_map = create_vocal_render_source_map(state, [decision])
    forged = deepcopy(render_map)
    forged["segments"][0]["source_id"] = "take-002"
    forged["segments"][0]["source_audio_sha256"] = state["vocal_performance_state"][
        "takes"
    ][1]["audio"]["sha256"]
    forged["segments"][0]["decision_document_sha256"] = "9" * 64
    forged.pop("document_sha256")
    forged["document_sha256"] = document_sha256(forged)
    with pytest.raises(ValueError, match="exact decision projection"):
        _authorization(
            state_path, forged, render_scope="phrase_only", phrase_id="phrase-1"
        )

    expanded = deepcopy(decision)
    expanded["render_authority"] = True
    expanded.pop("document_sha256")
    expanded["document_sha256"] = document_sha256(expanded)
    with pytest.raises(ValueError, match="fields changed"):
        validate_phrase_decision(expanded, state)


def _authorization(
    state_path: Path,
    source_map: dict[str, Any],
    *,
    render_scope: str,
    phrase_id: str | None = None,
    complete: bool = False,
    ai: bool = False,
) -> dict[str, Any]:
    return create_dry_vocal_render_authorization(
        state_path,
        source_map,
        render_scope=render_scope,
        phrase_id=phrase_id,
        confirm_dry_uncorrected_scope=True,
        confirm_complete_intended_vocal_roster=complete,
        confirm_authorised_ai_fallback_render=ai,
    )


def _rehash(document: dict[str, Any]) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)


def _state(
    root: Path,
    *,
    phrases: list[tuple[str, float, float, str]],
    duration: float,
    stereo_reference: bool = False,
) -> tuple[Path, dict[str, Any]]:
    take_dir = root / "takes"
    take_dir.mkdir(mode=0o700)
    frames = round(duration * SAMPLE_RATE)
    time = np.arange(frames, dtype=np.float64) / SAMPLE_RATE
    for index, frequency in enumerate((220.0, 330.0), 1):
        values = 0.10 * np.sin(2.0 * np.pi * frequency * time)
        sf.write(
            take_dir / f"take-{index}.wav",
            values,
            SAMPLE_RATE,
            format="WAV",
            subtype="PCM_24",
        )
    lyrics = root / "lyrics.txt"
    lyrics.write_text("\n".join(row[3] for row in phrases), encoding="utf-8")
    timeline = root / "timeline.json"
    timeline.write_text(
        json.dumps(
            {
                "schema": "sunofriend.vocal-comp-timeline.v1",
                "status": "reviewed",
                "phrases": [
                    {
                        "phrase_id": phrase_id,
                        "start_seconds": start,
                        "end_seconds": end,
                        "lyrics": lyric,
                    }
                    for phrase_id, start, end, lyric in phrases
                ],
            }
        ),
        encoding="utf-8",
    )
    reference: Path | None = None
    if stereo_reference:
        reference = root / "reference.wav"
        reference_values = np.column_stack(
            (
                0.08 * np.sin(2.0 * np.pi * 440.0 * time),
                0.08 * np.sin(2.0 * np.pi * 550.0 * time),
            )
        )
        sf.write(
            reference,
            reference_values,
            SAMPLE_RATE,
            format="WAV",
            subtype="PCM_24",
        )
    state = create_vocal_musical_state(
        take_dir,
        out_dir=root / "state",
        lyrics=lyrics,
        phrase_timeline=timeline,
        rights_category="owned",
        processing_chain="dry",
        reference_vocal=reference,
        confirm_common_recorded_zero=True,
        confirm_timeline_reviewed=True,
    )
    return root / "state/musical-state.json", state


def _declare_complete_roster(path: Path) -> dict[str, Any]:
    state = json.loads(path.read_text(encoding="utf-8"))
    state["structure"]["coverage_scope"] = "reviewed_complete_intended_vocal_roster"
    state.pop("document_sha256", None)
    state["document_sha256"] = document_sha256(state)
    path.write_bytes(canonical_json_bytes(state))
    os.chmod(path, 0o600)
    return state
