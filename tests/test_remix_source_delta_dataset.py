from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_remix_source_delta_label import _render
from sunofriend.remix_delta import inspect_remix_audio
from sunofriend.remix_learning_contract import REMIX_EVIDENCE_GATES
from sunofriend.remix_source_delta_dataset import (
    REMIX_SOURCE_DELTA_TRAINING_SNAPSHOT_SCHEMA,
    create_remix_source_delta_training_snapshot,
    validate_remix_source_delta_training_snapshot,
)
from sunofriend.remix_source_delta_label import (
    RemixSourceDeltaReviewDecision,
    admit_remix_source_delta_pairwise_label,
)
from sunofriend.remix_source_state import create_remix_source_state
from sunofriend.source_receipt import document_sha256


def test_real_label_enters_path_free_split_safe_snapshot_without_training(
    tmp_path: Path,
) -> None:
    example = _example(tmp_path)

    snapshot = create_remix_source_delta_training_snapshot(
        snapshot_id="source-delta-pilot-001",
        examples=[{**example, "split": "train"}],
    )

    assert snapshot["schema"] == REMIX_SOURCE_DELTA_TRAINING_SNAPSHOT_SCHEMA
    assert snapshot["status"] == "training_ineligible"
    assert snapshot["labels"] == [example["label"]]
    assert snapshot["source_states"] == [example["source_state"]]
    assert snapshot["assignments"][0]["split"] == "train"
    assert snapshot["evidence_gate"]["thresholds"] == REMIX_EVIDENCE_GATES
    assert snapshot["evidence_gate"]["observed"]["explicit_labels"] == 1
    assert snapshot["evidence_gate"]["evidence_gate_passed"] is False
    assert snapshot["readiness"]["next_gate"] == "collect_owner_labels"
    assert snapshot["authority"]["training_execution_authorized"] is False
    assert snapshot["effects"]["training_started"] is False
    assert "/Users/" not in str(snapshot)
    assert str(tmp_path) not in str(snapshot)
    assert validate_remix_source_delta_training_snapshot(snapshot) == snapshot


def test_snapshot_rechecks_exact_render_before_admission(tmp_path: Path) -> None:
    example = _example(tmp_path)
    candidate = example["render_root"] / "AUDIO/candidate-2.wav"
    candidate.write_bytes(b"changed")

    with pytest.raises(ValueError, match="identity changed"):
        create_remix_source_delta_training_snapshot(
            snapshot_id="changed-render",
            examples=[{**example, "split": "train"}],
        )


def test_snapshot_rejects_changed_source_binding(tmp_path: Path) -> None:
    example = _example(tmp_path)
    changed = deepcopy(example["source_state"])
    changed["composition_id"] = "another-composition"
    changed.pop("document_sha256")
    changed["document_sha256"] = document_sha256(changed)

    with pytest.raises(ValueError, match="source-state binding"):
        create_remix_source_delta_training_snapshot(
            snapshot_id="changed-source",
            examples=[{**example, "source_state": changed, "split": "train"}],
        )


def test_snapshot_validator_rejects_training_authority(tmp_path: Path) -> None:
    example = _example(tmp_path)
    snapshot = create_remix_source_delta_training_snapshot(
        snapshot_id="authority-test",
        examples=[{**example, "split": "train"}],
    )
    changed = deepcopy(snapshot)
    changed["authority"]["training_execution_authorized"] = True
    changed.pop("document_sha256")
    changed["document_sha256"] = document_sha256(changed)

    with pytest.raises(ValueError, match="authority|effects"):
        validate_remix_source_delta_training_snapshot(changed)


def _example(root: Path) -> dict:
    render_root = _render(root)
    source_record = inspect_remix_audio(root / "inputs/source.wav")
    source_state = create_remix_source_state(
        state_id="source-state",
        composition_id="composition",
        group_id="group",
        source_control=source_record,
        rights_category="owned",
        source_start_seconds=10.0,
        source_end_seconds=12.0,
        owner_local_training_approved=True,
    )
    label = admit_remix_source_delta_pairwise_label(
        render_root,
        decision=RemixSourceDeltaReviewDecision(
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
        ),
        out_dir=root / "label",
    )
    return {
        "label": label,
        "render_root": render_root,
        "source_state": source_state,
    }
