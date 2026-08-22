from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf

from sunofriend.audio_formats import file_sha256
from sunofriend.musical_state import (
    VOCAL_COMP_TIMELINE_SCHEMA,
    admit_vocal_phrase_capture,
    create_vocal_musical_state,
)
from sunofriend.source_receipt import canonical_json_bytes, document_sha256
from sunofriend.vocal_capture import create_vocal_capture
from sunofriend.vocal_comp_continuation import (
    VOCAL_CONTINUATION_PLAN_SCHEMA,
    create_vocal_continuation_plan,
    create_vocal_continuation_review,
    create_vocal_continuation_render_authorization,
    render_vocal_continuation,
    validate_vocal_continuation_plan,
    validate_vocal_continuation_review,
)
from sunofriend.vocal_phrase_decision import create_phrase_decision


SAMPLE_RATE = 8_000


def test_plan_binds_reviewed_base_latest_state_and_exact_browser_capture(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    plan = create_vocal_continuation_plan(
        fixture["base_binding"], fixture["state_path"], fixture["decision"]
    )

    assert plan["schema"] == VOCAL_CONTINUATION_PLAN_SCHEMA
    assert (
        plan["binding"]["musical_state_sha256"] == fixture["state"]["document_sha256"]
    )
    assert (
        plan["binding"]["phrase_decision_sha256"]
        == fixture["decision"]["document_sha256"]
    )
    assert plan["binding"]["base_audio_sha256"] == file_sha256(fixture["base_audio"])
    assert plan["scope"]["carried_base_phrase_ids"] == ["phrase-1", "phrase-2"]
    assert plan["scope"]["appended_phrase_id"] == "phrase-3"
    assert plan["segments"][1]["source_id"] == "browser-capture-attempt-002"
    assert plan["join"] == {
        "song_time_seconds": 1.5,
        "destination_frame": SAMPLE_RATE,
        "policy": "exact_boundary_concatenation_no_fade",
        "review_status": "not_reviewed",
        "automatic_join_acceptance": False,
    }
    assert not any(plan["processing"].values())
    assert not any(plan["effects"].values())
    assert plan["authority"]["separate_owner_render_authorization_required"] is True
    assert (
        validate_vocal_continuation_plan(
            plan,
            fixture["base_binding"],
            fixture["state_path"],
            fixture["decision"],
        )
        == plan
    )

    with pytest.raises(ValueError, match="explicitly authorize"):
        create_vocal_continuation_render_authorization(plan)


def test_render_needs_exact_authority_and_is_sample_exact_unreviewed_preview(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    plan = create_vocal_continuation_plan(
        fixture["base_binding"], fixture["state_path"], fixture["decision"]
    )
    authorization = create_vocal_continuation_render_authorization(
        plan, confirm_dry_uncorrected_preview=True
    )
    output = tmp_path / "three-phrase-output"

    with pytest.raises(ValueError, match="separate confirmation"):
        render_vocal_continuation(
            fixture["base_binding"],
            fixture["state_path"],
            fixture["decision"],
            plan,
            authorization,
            out_dir=output,
            expected_plan_sha256=plan["document_sha256"],
        )
    assert not output.exists()

    with pytest.raises(ValueError, match="outside immutable source evidence"):
        render_vocal_continuation(
            fixture["base_binding"],
            fixture["state_path"],
            fixture["decision"],
            plan,
            authorization,
            out_dir=fixture["base_audio"].parent / "forbidden-output",
            expected_plan_sha256=plan["document_sha256"],
            confirm_dry_uncorrected_render=True,
        )

    verification = render_vocal_continuation(
        fixture["base_binding"],
        fixture["state_path"],
        fixture["decision"],
        plan,
        authorization,
        out_dir=output,
        expected_plan_sha256=plan["document_sha256"],
        confirm_dry_uncorrected_render=True,
    )

    assert verification["status"] == "technically_verified_unreviewed_preview"
    assert verification["checks"]["exact_concatenation"] is True
    assert verification["checks"]["join_reviewed"] is False
    base, _ = sf.read(fixture["base_audio"], dtype="int32", always_2d=True)
    capture, _ = sf.read(fixture["capture_audio"], dtype="int32", always_2d=True)
    rendered, _ = sf.read(
        output / "AUDIO/dry-three-phrase-continuation.wav",
        dtype="int32",
        always_2d=True,
    )
    expected = np.concatenate((base, capture[400:4400]), axis=0)
    np.testing.assert_array_equal(rendered, expected)
    page = (output / "REVIEW/dry-continuation-review.html").read_text(encoding="utf-8")
    assert "Playback creates no decision" in page
    assert "No tuning, timing correction" in page


def test_stale_decision_tampering_and_base_authority_expansion_fail_closed(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    stale = create_phrase_decision(
        fixture["parent_state"],
        "phrase-3",
        "human_take",
        source_id="browser-capture-attempt-001",
    )
    with pytest.raises(ValueError, match="musical state|binding"):
        create_vocal_continuation_plan(
            fixture["base_binding"], fixture["state_path"], stale
        )

    plan = create_vocal_continuation_plan(
        fixture["base_binding"], fixture["state_path"], fixture["decision"]
    )
    tampered = deepcopy(plan)
    tampered["join"]["review_status"] = "reviewed"
    _rehash(tampered)
    with pytest.raises(ValueError, match="stale|altered"):
        validate_vocal_continuation_plan(
            tampered,
            fixture["base_binding"],
            fixture["state_path"],
            fixture["decision"],
        )

    base = json.loads(fixture["base_binding"].read_text(encoding="utf-8"))
    base["authority"]["comp_render_authorized"] = True
    _rehash(base)
    expanded = tmp_path / "expanded-base.json"
    expanded.write_bytes(canonical_json_bytes(base))
    with pytest.raises(ValueError, match="excessive authority"):
        create_vocal_continuation_plan(
            expanded, fixture["state_path"], fixture["decision"]
        )


def test_explicit_phrase_and_natural_join_review_make_exact_preview_next_base(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    plan = create_vocal_continuation_plan(
        fixture["base_binding"], fixture["state_path"], fixture["decision"]
    )
    authorization = create_vocal_continuation_render_authorization(
        plan, confirm_dry_uncorrected_preview=True
    )
    output = tmp_path / "reviewed-three-phrase-output"
    render_vocal_continuation(
        fixture["base_binding"],
        fixture["state_path"],
        fixture["decision"],
        plan,
        authorization,
        out_dir=output,
        expected_plan_sha256=plan["document_sha256"],
        confirm_dry_uncorrected_render=True,
    )

    review = create_vocal_continuation_review(
        output,
        plan,
        phrase_outcome="usable",
        join_outcome="natural",
        heard_full_preview=True,
    )

    assert review["decision"] == {
        "phrase_3": "usable",
        "join_at_reviewed_boundary": "natural",
        "whole_excerpt": "usable_as_next_iteration_base",
    }
    assert review["authority"]["usable_as_next_iteration_base"] is True
    assert review["authority"]["join_accepted_for_this_exact_dry_excerpt"] is True
    assert review["authority"]["release_authorized"] is False
    assert review["authority"]["training_label_created"] is False
    assert not any(review["effects"].values())
    assert (
        validate_vocal_continuation_review(review, output_dir=output, plan=plan)
        == review
    )

    excessive = deepcopy(review)
    excessive["authority"]["release_authorized"] = True
    _rehash(excessive)
    with pytest.raises(ValueError, match="altered|excessive"):
        validate_vocal_continuation_review(excessive, output_dir=output, plan=plan)

    with pytest.raises(ValueError, match="full preview"):
        create_vocal_continuation_review(
            output,
            plan,
            phrase_outcome="usable",
            join_outcome="natural",
            heard_full_preview=False,
        )


def _fixture(root: Path) -> dict[str, Any]:
    takes = root / "takes"
    takes.mkdir()
    frames = SAMPLE_RATE * 3
    time = np.arange(frames, dtype=np.float64) / SAMPLE_RATE
    for index, frequency in enumerate((190.0, 240.0), 1):
        sf.write(
            takes / f"take-{index}.wav",
            0.08 * np.sin(2.0 * np.pi * frequency * time),
            SAMPLE_RATE,
            subtype="PCM_24",
        )
    lyrics = root / "lyrics.txt"
    lyrics.write_text("First\nSecond\nThird\n", encoding="utf-8")
    timeline = root / "timeline.json"
    timeline.write_text(
        json.dumps(
            {
                "schema": VOCAL_COMP_TIMELINE_SCHEMA,
                "status": "reviewed",
                "phrases": [
                    {
                        "phrase_id": "phrase-1",
                        "start_seconds": 0.5,
                        "end_seconds": 1.0,
                        "lyrics": "First",
                    },
                    {
                        "phrase_id": "phrase-2",
                        "start_seconds": 1.1,
                        "end_seconds": 1.5,
                        "lyrics": "Second",
                    },
                    {
                        "phrase_id": "phrase-3",
                        "start_seconds": 1.5,
                        "end_seconds": 2.0,
                        "lyrics": "Third",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    parent_path = root / "state/musical-state.json"
    parent_state = create_vocal_musical_state(
        takes,
        out_dir=parent_path.parent,
        lyrics=lyrics,
        phrase_timeline=timeline,
        rights_category="owned",
        processing_chain="dry",
        confirm_common_recorded_zero=True,
        confirm_timeline_reviewed=True,
    )
    first_audio = root / "capture-1.wav"
    second_audio = root / "capture-2.wav"
    capture_frames = 4_800
    capture_time = np.arange(capture_frames, dtype=np.float64) / SAMPLE_RATE
    sf.write(
        first_audio,
        0.07 * np.sin(2.0 * np.pi * 280.0 * capture_time),
        SAMPLE_RATE,
        subtype="PCM_24",
    )
    first_receipt = _capture_receipt(parent_state, first_audio, "attempt-001")
    parent_state = admit_vocal_phrase_capture(
        parent_path,
        capture_wav=first_audio,
        capture_receipt=first_receipt,
        out_dir=root / "state-with-capture-1",
    )
    parent_path = root / "state-with-capture-1/musical-state.json"

    sf.write(
        second_audio,
        0.09 * np.sin(2.0 * np.pi * 320.0 * capture_time),
        SAMPLE_RATE,
        subtype="PCM_24",
    )
    second_receipt = _capture_receipt(parent_state, second_audio, "attempt-002")
    state = admit_vocal_phrase_capture(
        parent_path,
        capture_wav=second_audio,
        capture_receipt=second_receipt,
        out_dir=root / "state-with-capture-2",
    )
    state_path = root / "state-with-capture-2/musical-state.json"
    decision = create_phrase_decision(
        state,
        "phrase-3",
        "human_take",
        source_id="browser-capture-attempt-002",
    )
    base_binding, base_audio = _base(root)
    return {
        "state": state,
        "state_path": state_path,
        "parent_state": parent_state,
        "decision": decision,
        "capture_audio": second_audio,
        "base_binding": base_binding,
        "base_audio": base_audio,
    }


def _capture_receipt(
    state: dict[str, Any], path: Path, capture_id: str
) -> dict[str, Any]:
    return create_vocal_capture(
        state,
        capture_id=capture_id,
        phrase_id="phrase-3",
        cue_id="take-001",
        cue_asset_sha256=state["vocal_performance_state"]["takes"][0]["audio"][
            "sha256"
        ],
        audio_sha256=file_sha256(path),
        audio_bytes=path.stat().st_size,
        sample_rate=SAMPLE_RATE,
        frame_count=4_800,
        phrase_start_frame=400,
        phrase_end_frame=4_400,
        destination_start_seconds=1.5,
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


def _base(root: Path) -> tuple[Path, Path]:
    folder = root / "base"
    folder.mkdir()
    base_audio = folder / "two-phrase.wav"
    time = np.arange(SAMPLE_RATE, dtype=np.float64) / SAMPLE_RATE
    sf.write(
        base_audio,
        0.06 * np.sin(2.0 * np.pi * 210.0 * time),
        SAMPLE_RATE,
        subtype="PCM_24",
    )
    audio_sha = file_sha256(base_audio)
    receipt = {
        "schema": "sunofriend.private-vocal-tail-reviewed-render-result.v0",
        "status": "complete_tail_reviewed_excerpt_pending_whole_reconfirmation",
        "artifacts": {"audio": {"sha256": audio_sha}},
        "processing": {
            "gain_trim": False,
            "limiting": False,
            "normalisation": False,
            "pitch_correction": False,
            "resampling": False,
            "timing_correction": False,
        },
        "network_used": False,
    }
    _rehash(receipt)
    receipt_path = folder / "receipt.json"
    receipt_path.write_bytes(canonical_json_bytes(receipt))
    review = {
        "schema": "sunofriend.private-vocal-excerpt-review-result.v0",
        "status": "complete_explicit_owner_usable_base",
        "binding": {"audio_sha256": audio_sha},
        "decision": {"outcome": "usable_base"},
        "authority": {"usable_as_next_iteration_base": True},
        "effects": {
            "audio_mutated": False,
            "audio_rendered": False,
            "source_choice_changed": False,
            "training_label_created": False,
        },
        "network_used": False,
    }
    _rehash(review)
    review_path = folder / "review.json"
    review_path.write_bytes(canonical_json_bytes(review))
    binding = {
        "schema": "sunofriend.private-vocal-continuation-base-binding.v0",
        "status": "complete_immutable_usable_base_reference",
        "scope": {
            "phrase_ids": ["phrase-1", "phrase-2"],
            "song_start_seconds": 0.5,
            "song_end_seconds": 1.5,
        },
        "artifacts": {
            "audio": {"path": base_audio.name, "sha256": audio_sha},
            "usable_base_review": {
                "path": review_path.name,
                "file_sha256": file_sha256(review_path),
                "document_sha256": review["document_sha256"],
            },
            "render_receipt": {
                "path": receipt_path.name,
                "file_sha256": file_sha256(receipt_path),
                "document_sha256": receipt["document_sha256"],
            },
        },
        "authority": {
            "usable_as_next_iteration_base": True,
            "decisions_migrated": False,
            "phrase_3_take_selected": False,
            "comp_render_authorized": False,
            "pitch_correction_authorized": False,
            "timing_correction_authorized": False,
            "training_label_created": False,
        },
        "effects": {
            "source_mutated": False,
            "decision_created": False,
            "audio_rendered": False,
            "correction_applied": False,
            "training_started": False,
        },
        "network_used": False,
    }
    _rehash(binding)
    binding_path = folder / "base-binding.json"
    binding_path.write_bytes(canonical_json_bytes(binding))
    return binding_path, base_audio


def _rehash(document: dict[str, Any]) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)
