from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from sunofriend.remix_delta import inspect_remix_audio
from sunofriend.remix_source_anchor import (
    confirm_remix_source_anchor_preflight,
    create_remix_source_anchor_preflight,
)
from sunofriend.remix_source_delta import (
    create_remix_source_delta_plan,
    create_remix_source_delta_render_authorization,
    render_remix_source_delta,
)
from sunofriend.remix_source_delta_label import (
    REMIX_SOURCE_DELTA_PAIRWISE_LABEL_SCHEMA,
    RemixSourceDeltaReviewDecision,
    admit_remix_source_delta_pairwise_label,
    validate_remix_source_delta_pairwise_label,
)
from sunofriend.remix_source_state import create_remix_source_state
from sunofriend.source_receipt import canonical_json_bytes, document_sha256


def test_admits_exact_heard_identity_preserving_preference_without_training(
    tmp_path: Path,
) -> None:
    render_root = _render(tmp_path)
    decision = RemixSourceDeltaReviewDecision(
        presentation_seed=20260827,
        heard_control=True,
        heard_a=True,
        heard_b=True,
        outcome="a",
        identity_a="preserved",
        identity_b="preserved",
        reason_codes=("background_noise",),
        admit_owner_local_training=True,
        reviewed_at="2026-09-02T12:00:00Z",
    )

    output = tmp_path / "label"
    label = admit_remix_source_delta_pairwise_label(
        render_root, decision=decision, out_dir=output
    )

    assert label["schema"] == REMIX_SOURCE_DELTA_PAIRWISE_LABEL_SCHEMA
    assert label["status"] == "complete_explicit_owner_pairwise_label"
    assert label["left"]["variant_id"] == "gentle-rhythm-restraint"
    assert label["right"]["variant_id"] == "strong-rhythm-restraint"
    assert label["outcome"] == "left"
    assert label["identity_relationships"] == {
        "left": "preserved",
        "right": "preserved",
    }
    assert label["reason_codes"] == ["background_noise"]
    assert label["training"] == {
        "explicitly_admitted": True,
        "admission_scope": "owner_local_training",
        "training_eligible": False,
    }
    assert label["effects"]["training_label_created"] is True
    assert label["effects"]["training_started"] is False
    assert label["authority"]["training_execution_authorized"] is False
    assert label["authority"]["selected_for_product"] is False
    saved = output / "LABELS" / f"{label['document_sha256']}.json"
    assert saved.read_bytes() == canonical_json_bytes(label)
    assert validate_remix_source_delta_pairwise_label(label, render_root) == label


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("heard_control", False, "heard control, A and B"),
        ("heard_a", False, "heard control, A and B"),
        ("heard_b", False, "heard control, A and B"),
        ("admit_owner_local_training", False, "explicit local-training admission"),
    ],
)
def test_rejects_missing_listening_or_training_admission(
    tmp_path: Path, field: str, value: bool, message: str
) -> None:
    render_root = _render(tmp_path)
    values = {
        "presentation_seed": 20260827,
        "heard_control": True,
        "heard_a": True,
        "heard_b": True,
        "outcome": "a",
        "identity_a": "preserved",
        "identity_b": "preserved",
        "reason_codes": ("background_noise",),
        "admit_owner_local_training": True,
        "reviewed_at": "2026-09-02T12:00:00Z",
    }
    values[field] = value

    with pytest.raises(ValueError, match=message):
        admit_remix_source_delta_pairwise_label(
            render_root,
            decision=RemixSourceDeltaReviewDecision(**values),
            out_dir=tmp_path / "label",
        )


def test_label_revalidates_exact_render_and_rejects_tampering(tmp_path: Path) -> None:
    render_root = _render(tmp_path)
    decision = RemixSourceDeltaReviewDecision(
        presentation_seed=20260827,
        heard_control=True,
        heard_a=True,
        heard_b=True,
        outcome="a",
        identity_a="preserved",
        identity_b="preserved",
        reason_codes=("background_noise",),
        admit_owner_local_training=True,
        reviewed_at="2026-09-02T12:00:00Z",
    )
    label = admit_remix_source_delta_pairwise_label(
        render_root, decision=decision, out_dir=tmp_path / "label"
    )

    changed = deepcopy(label)
    changed["identity_relationships"]["right"] = "discarded"
    changed.pop("document_sha256")
    changed["document_sha256"] = document_sha256(changed)
    with pytest.raises(ValueError, match="identity relationship"):
        validate_remix_source_delta_pairwise_label(changed, render_root)

    (render_root / "AUDIO/candidate-2.wav").write_bytes(b"changed")
    with pytest.raises(ValueError, match="identity changed"):
        validate_remix_source_delta_pairwise_label(label, render_root)


def test_rejects_label_output_inside_immutable_render(tmp_path: Path) -> None:
    render_root = _render(tmp_path)
    decision = RemixSourceDeltaReviewDecision(
        presentation_seed=20260827,
        heard_control=True,
        heard_a=True,
        heard_b=True,
        outcome="a",
        identity_a="preserved",
        identity_b="preserved",
        reason_codes=("background_noise",),
        admit_owner_local_training=True,
        reviewed_at="2026-09-02T12:00:00Z",
    )

    with pytest.raises(ValueError, match="outside the immutable render"):
        admit_remix_source_delta_pairwise_label(
            render_root,
            decision=decision,
            out_dir=render_root / "LABEL",
        )


def _render(root: Path) -> Path:
    rate = 8_000
    frames = 16_000
    time = np.arange(frames, dtype=np.float64) / rate
    inputs = root / "inputs"
    inputs.mkdir()
    source_path = inputs / "source.wav"
    other_path = inputs / "other.wav"
    drums_path = inputs / "drums.wav"
    source = 0.20 * np.sin(2 * np.pi * 220 * time) + 0.08 * np.sin(
        2 * np.pi * 3 * time
    )
    other = 0.12 * np.sin(2 * np.pi * 220 * time)
    drums = 0.08 * np.sin(2 * np.pi * 3 * time)
    for path, values in (
        (source_path, source),
        (other_path, other),
        (drums_path, drums),
    ):
        sf.write(path, values, rate, subtype="PCM_24")
    source_record = inspect_remix_audio(source_path)
    other_record = inspect_remix_audio(other_path)
    drums_record = inspect_remix_audio(drums_path)
    state = create_remix_source_state(
        state_id="source-state",
        composition_id="composition",
        group_id="group",
        source_control=source_record,
        rights_category="owned",
        source_start_seconds=10.0,
        source_end_seconds=12.0,
        owner_local_training_approved=True,
    )
    preflight = create_remix_source_anchor_preflight(
        state,
        separation_estimate={
            "source_estimate_id": "grouped-other-estimate",
            "estimated_role": "grouped accompaniment estimate",
            **other_record,
        },
        owner_label="Keep the melody recognisable",
        anchor_kind="motif",
        start_frame=0,
        end_frame=8_000,
        preservation_requirement="must_remain_recognisable",
        heard_source=True,
        heard_estimate=True,
    )
    confirmed = confirm_remix_source_anchor_preflight(
        preflight,
        state,
        identity_state_id="identity",
        registry_id="registry",
    )
    plan = create_remix_source_delta_plan(
        state,
        preflight,
        confirmed["identity_state"],
        confirmed["owner_registry"],
        confirmed["confirmation"],
        target_estimate={
            "source_estimate_id": "drums-estimate",
            "source_kind": "separation_estimate",
            "role_interpretation": "estimate_not_ground_truth",
            "estimated_role": "drums",
            "musical_function": "rhythm",
            **drums_record,
        },
        variants=[
            {
                "variant_id": "gentle-rhythm-restraint",
                "points": [
                    {"frame": 0, "delta_db": -2.0},
                    {"frame": frames // 2, "delta_db": -2.0},
                    {"frame": frames, "delta_db": 0.0},
                ],
            },
            {
                "variant_id": "strong-rhythm-restraint",
                "points": [
                    {"frame": 0, "delta_db": -5.0},
                    {"frame": frames // 2, "delta_db": -5.0},
                    {"frame": frames, "delta_db": 0.0},
                ],
            },
        ],
    )
    authorization = create_remix_source_delta_render_authorization(
        plan, confirm_private_ab_preview=True
    )
    output = root / "render"
    render_remix_source_delta(
        plan,
        authorization,
        source_audio=source_path,
        target_estimate_audio=drums_path,
        out_dir=output,
        expected_plan_sha256=plan["document_sha256"],
        confirm_render=True,
    )
    return output
