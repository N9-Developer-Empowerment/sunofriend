from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from sunofriend.remix_delta import (
    REMIX_COMPARISON_PLAN_SCHEMA,
    REMIX_COMPARISON_RESULT_SCHEMA,
    create_remix_comparison_plan,
    inspect_remix_audio,
    render_remix_comparison,
    resolve_remix_comparison_review,
    validate_remix_comparison_result,
)
from sunofriend.remix_identity import (
    REMIX_IDENTITY_STATE_SCHEMA,
    create_remix_request,
    create_remix_result,
)
from sunofriend.source_receipt import document_sha256


def test_exact_source_control_and_one_target_delta_render(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    source_path, target_path = _audio_fixture(tmp_path)
    identity = _identity(inspect_remix_audio(target_path))
    request = _request(identity)
    plan = create_remix_comparison_plan(
        request, identity, source_control=inspect_remix_audio(source_path)
    )

    assert plan["schema"] == REMIX_COMPARISON_PLAN_SCHEMA
    assert plan["render_policy"]["normalisation"] is False
    assert plan["render_policy"]["limiting"] is False
    assert plan["review_policy"]["playback_creates_decision"] is False
    assert not any(plan["effects"].values())

    original_bytes = source_path.read_bytes()
    output = tmp_path / "comparison"
    result = render_remix_comparison(
        plan,
        request,
        identity,
        source_audio=source_path,
        target_estimate_audio=target_path,
        out_dir=output,
    )

    assert result["schema"] == REMIX_COMPARISON_RESULT_SCHEMA
    assert result["status"] == "complete_unreviewed_deterministic_comparison"
    assert result["review_status"] == "not_reviewed"
    assert result["owner_identity_preserved"] is None
    assert result["selected_for_product"] is False
    assert result["model_used"] is False
    assert result["training_used"] is False
    assert result["network_used"] is False
    assert (output / "AUDIO/source-control.wav").read_bytes() == original_bytes
    assert (output / "AUDIO/delta-challenger.wav").is_file()
    assert (output / "REVIEW/remix-review.html").is_file()
    assert (output / "TECHNICAL/remix-comparison.json").is_file()
    assert validate_remix_comparison_result(result, plan, request, identity) == result

    source, _ = sf.read(source_path, always_2d=True, dtype="float64")
    target, _ = sf.read(target_path, always_2d=True, dtype="float64")
    challenger, _ = sf.read(
        output / "AUDIO/delta-challenger.wav", always_2d=True, dtype="float64"
    )
    expected = source.copy()
    frame = np.arange(800, 1_600)
    delta_db = np.interp(frame, [800, 1_200, 1_600], [0.0, -6.0, 0.0])
    expected[800:1_600] += target[800:1_600] * (
        np.power(10.0, delta_db / 20.0)[:, None] - 1.0
    )
    assert np.max(np.abs(challenger - expected)) <= 2.0 / (2**23)
    assert np.max(np.abs(challenger[:800] - source[:800])) <= 2.0 / (2**23)
    assert np.max(np.abs(challenger[1_600:] - source[1_600:])) <= 2.0 / (2**23)
    assert np.max(np.abs(challenger[900:1_500] - source[900:1_500])) > 0.01

    review_html = (output / "REVIEW/remix-review.html").read_text()
    assert "Playback saves nothing and creates no preference" in review_html
    assert "Export explicit review JSON" in review_html
    assert "The accompaniment hook that makes the song recognisable" in review_html

    reviewed = json.loads(
        (output / "REVIEW/remix-review.seed.json").read_text(encoding="utf-8")
    )
    reviewed.pop("document_sha256")
    reviewed.update(
        status="complete_explicit_owner_review_no_selection",
        questions={
            "heard_source_control": True,
            "heard_delta_challenger": True,
            "identity_relationship": "preserved",
            "musical_usefulness": "useful",
        },
        label_authority="explicit_owner_listening_decision",
        selected_for_product=False,
        training_eligible=False,
    )
    review = resolve_remix_comparison_review(reviewed, result, plan, request, identity)
    assert review["status"] == "complete_explicit_owner_review_no_selection"
    assert review["owner_anchor_labels"] == [
        {
            "anchor_id": "chorus-accompaniment-hook",
            "heard": True,
            "identity_relationship": "preserved",
            "musical_usefulness": "useful",
        }
    ]
    assert review["selected_for_product"] is False
    assert review["training_eligible"] is False

    playback_only = deepcopy(reviewed)
    playback_only["questions"]["heard_delta_challenger"] = False
    with pytest.raises(ValueError, match="hearing both"):
        resolve_remix_comparison_review(playback_only, result, plan, request, identity)

    repeated_output = tmp_path / "comparison-repeat"
    repeated = render_remix_comparison(
        plan,
        request,
        identity,
        source_audio=source_path,
        target_estimate_audio=target_path,
        out_dir=repeated_output,
    )
    assert repeated == result
    for relative in (
        "AUDIO/source-control.wav",
        "AUDIO/delta-challenger.wav",
        "REVIEW/remix-review.seed.json",
        "REVIEW/remix-review.html",
        "TECHNICAL/remix-comparison.json",
    ):
        assert (repeated_output / relative).read_bytes() == (
            output / relative
        ).read_bytes()


def test_render_fails_closed_on_drift_existing_output_and_shared_parent(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    source_path, target_path = _audio_fixture(tmp_path)
    identity = _identity(inspect_remix_audio(target_path))
    request = _request(identity)
    plan = create_remix_comparison_plan(
        request, identity, source_control=inspect_remix_audio(source_path)
    )
    changed_target = tmp_path / "changed-target.wav"
    target, rate = sf.read(target_path, always_2d=True)
    target[10, 0] += 0.01
    sf.write(changed_target, target, rate, subtype="PCM_24")
    with pytest.raises(ValueError, match="target estimate does not match"):
        render_remix_comparison(
            plan,
            request,
            identity,
            source_audio=source_path,
            target_estimate_audio=changed_target,
            out_dir=tmp_path / "drift",
        )
    assert not (tmp_path / "drift").exists()

    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        render_remix_comparison(
            plan,
            request,
            identity,
            source_audio=source_path,
            target_estimate_audio=target_path,
            out_dir=existing,
        )

    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    with pytest.raises(PermissionError, match="owner-only"):
        render_remix_comparison(
            plan,
            request,
            identity,
            source_audio=source_path,
            target_estimate_audio=target_path,
            out_dir=shared / "result",
        )


@pytest.mark.parametrize(
    "points",
    (
        [
            {"frame": 800, "delta_db": -1.0},
            {"frame": 1_600, "delta_db": 0.0},
        ],
        [
            {"frame": 800, "delta_db": 0.0},
            {"frame": 1_200, "delta_db": 1.0},
            {"frame": 1_600, "delta_db": 0.0},
        ],
        [
            {"frame": 800, "delta_db": 0.0},
            {"frame": 1_200, "delta_db": -13.0},
            {"frame": 1_600, "delta_db": 0.0},
        ],
    ),
)
def test_delta_envelope_is_attenuation_only_and_returns_to_unity(
    points: list[dict[str, float | int]],
) -> None:
    identity = _identity(
        {
            "audio_sha256": "a" * 64,
            "audio_bytes": 10_000,
            "geometry": {"sample_rate_hz": 8_000, "channels": 1, "frames": 3_200},
        }
    )
    with pytest.raises(ValueError, match="-12|0 dB|edges"):
        create_remix_request(
            identity,
            anchor_id="chorus-accompaniment-hook",
            source_estimate_id="grouped-other-estimate-001",
            delta_envelope_points=points,
        )


def test_result_rejects_forged_review_or_selection_claim() -> None:
    source_record = {
        "audio_sha256": "c" * 64,
        "audio_bytes": 10_000,
        "geometry": {"sample_rate_hz": 8_000, "channels": 1, "frames": 3_200},
    }
    identity = _identity({**source_record, "audio_sha256": "a" * 64})
    request = _request(identity)
    plan = create_remix_comparison_plan(request, identity, source_control=source_record)
    result = _synthetic_result(plan, request, identity)
    changed = deepcopy(result)
    changed["review_status"] = "reviewed"
    changed["owner_identity_preserved"] = True
    changed["selected_for_product"] = True
    _rehash(changed)
    with pytest.raises(ValueError, match="authority"):
        validate_remix_comparison_result(changed, plan, request, identity)


def _audio_fixture(root: Path) -> tuple[Path, Path]:
    sample_rate = 8_000
    frames = 3_200
    time = np.arange(frames, dtype=np.float64) / sample_rate
    target = 0.12 * np.sin(2 * np.pi * 220.0 * time)
    backing = 0.10 * np.sin(2 * np.pi * 330.0 * time)
    source = target + backing
    source_path = root / "source.wav"
    target_path = root / "target.wav"
    sf.write(source_path, source, sample_rate, subtype="PCM_24")
    sf.write(target_path, target, sample_rate, subtype="PCM_24")
    return source_path, target_path


def _identity(target: dict[str, object]) -> dict[str, object]:
    document: dict[str, object] = {
        "schema": REMIX_IDENTITY_STATE_SCHEMA,
        "status": "complete_owner_anchored_no_remix",
        "binding": {
            "musical_state_schema": "sunofriend.musical-state.v0",
            "musical_state_sha256": "1" * 64,
        },
        "method_natures": ["D", "H"],
        "separation_estimates": [
            {
                "source_estimate_id": "grouped-other-estimate-001",
                "source_kind": "separation_estimate",
                "estimated_role": "grouped_other",
                "role_interpretation": "estimate_not_ground_truth",
                **target,
            }
        ],
        "owner_anchors": [
            {
                "anchor_id": "chorus-accompaniment-hook",
                "anchor_kind": "motif",
                "owner_label": (
                    "The accompaniment hook that makes the song recognisable"
                ),
                "label_authority": "explicit_owner_label",
                "source_estimate_id": "grouped-other-estimate-001",
                "geometry": {
                    "sample_rate_hz": target["geometry"]["sample_rate_hz"],  # type: ignore[index]
                    "start_frame": 800,
                    "end_frame": 1_600,
                },
            }
        ],
        "model_used": False,
        "training_used": False,
        "network_used": False,
        "effects": {
            "identity_state_created": False,
            "remix_audio_derivative_rendered": False,
            "human_review_created": False,
            "selection_created": False,
            "training_label_created": False,
        },
    }
    document["document_sha256"] = document_sha256(document)
    return document


def _request(identity: dict[str, object]) -> dict[str, object]:
    return create_remix_request(
        identity,
        anchor_id="chorus-accompaniment-hook",
        source_estimate_id="grouped-other-estimate-001",
        delta_envelope_points=[
            {"frame": 800, "delta_db": 0.0},
            {"frame": 1_200, "delta_db": -6.0},
            {"frame": 1_600, "delta_db": 0.0},
        ],
    )


def _synthetic_result(
    plan: dict[str, object],
    request: dict[str, object],
    identity: dict[str, object],
) -> dict[str, object]:
    challenger = {
        "audio_sha256": "f" * 64,
        "audio_bytes": 10_000,
        "geometry": plan["source_control"]["geometry"],  # type: ignore[index]
        "relative_path": "AUDIO/delta-challenger.wav",
        "encoding": "WAV_PCM_24",
    }
    remix_result = create_remix_result(
        request,
        identity,
        output_audio_sha256=challenger["audio_sha256"],
        output_audio_bytes=challenger["audio_bytes"],
        output_geometry=challenger["geometry"],
    )
    package_binding = document_sha256(
        {
            "comparison_plan_sha256": plan["document_sha256"],
            "remix_result_sha256": remix_result["document_sha256"],
            "source_control_sha256": plan["source_control"]["audio_sha256"],  # type: ignore[index]
            "challenger_sha256": challenger["audio_sha256"],
        }
    )
    result: dict[str, object] = {
        "schema": REMIX_COMPARISON_RESULT_SCHEMA,
        "status": "complete_unreviewed_deterministic_comparison",
        "binding": {
            "comparison_plan_sha256": plan["document_sha256"],
            "identity_state_sha256": identity["document_sha256"],
            "remix_request_sha256": request["document_sha256"],
            "remix_result_sha256": remix_result["document_sha256"],
            "package_binding_sha256": package_binding,
        },
        "artifacts": {
            "source_control": {
                **plan["source_control"],  # type: ignore[dict-item]
                "relative_path": "AUDIO/source-control.wav",
                "copy_policy": "byte_exact",
            },
            "challenger": challenger,
            "review_seed": {
                "relative_path": "REVIEW/remix-review.seed.json",
                "sha256": "a" * 64,
                "bytes": 100,
            },
            "review_html": {
                "relative_path": "REVIEW/remix-review.html",
                "sha256": "b" * 64,
                "bytes": 100,
            },
        },
        "signal": {
            "challenger_sample_peak": 0.2,
            "normalised": False,
            "limited": False,
            "clipped": False,
        },
        "review_status": "not_reviewed",
        "owner_identity_preserved": None,
        "selected_for_product": False,
        "model_used": False,
        "training_used": False,
        "network_used": False,
        "effects": {
            "source_mutated": False,
            "target_estimate_mutated": False,
            "audio_derivative_rendered": True,
            "review_page_created": True,
            "human_review_created": False,
            "selection_created": False,
            "training_label_created": False,
            "model_weights_changed": False,
        },
    }
    result["document_sha256"] = document_sha256(result)
    return result


def _rehash(document: dict[str, object]) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)
