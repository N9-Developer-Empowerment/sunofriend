from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.test_remix_learning_snapshot_contract import _evidence
from sunofriend.remix_training_dataset import prepare_remix_training_dataset
from sunofriend.remix_training_dataset import (
    validate_remix_training_dataset_preparation,
)


def test_preparation_derives_assignments_and_reports_exact_shortfalls() -> None:
    first = _evidence("101")
    second = _evidence("102")

    prepared = prepare_remix_training_dataset(
        snapshot_id="owner-pilot-001",
        labels=[first[3], second[3]],
        owner_registries=[first[1], second[1]],
        variant_sets=[first[2], second[2]],
        composition_splits={
            "composition-101": "train",
            "composition-102": "validation",
        },
    )

    snapshot = prepared["snapshot"]
    assert {
        row["composition_id"]: row["split"] for row in snapshot["assignments"]
    } == {
        "composition-101": "train",
        "composition-102": "validation",
    }
    assert snapshot["evidence_gate"]["evidence_gate_passed"] is False
    readiness = prepared["readiness"]
    assert readiness["status"] == "collecting_owner_labels"
    assert readiness["shortfalls"]["explicit_labels"] == 198
    assert readiness["shortfalls"]["directional_labels"] == 118
    assert readiness["shortfalls"]["test_compositions"] == 1
    assert readiness["next_gate"] == "collect_owner_labels"
    assert readiness["authority"]["training_execution_authorized"] is False
    assert not any(readiness["effects"].values())


def test_preparation_rejects_missing_or_unused_composition_split() -> None:
    fixture, registry, variants, label = _evidence("201")
    common = {
        "snapshot_id": "owner-pilot-002",
        "labels": [label],
        "owner_registries": [registry],
        "variant_sets": [variants],
    }

    with pytest.raises(ValueError, match="missing.*composition"):
        prepare_remix_training_dataset(**common, composition_splits={})
    with pytest.raises(ValueError, match="unused.*composition"):
        prepare_remix_training_dataset(
            **common,
            composition_splits={
                "composition-201": "train",
                "composition-unused": "test",
            },
        )


def test_preparation_revalidates_embedded_evidence_before_deriving_split() -> None:
    fixture, registry, variants, label = _evidence("301")
    changed = deepcopy(label)
    changed["binding"]["variant_family_id"] = "forged-family"

    with pytest.raises(ValueError, match="hash|label|binding|variant"):
        prepare_remix_training_dataset(
            snapshot_id="owner-pilot-003",
            labels=[changed],
            owner_registries=[registry],
            variant_sets=[variants],
            composition_splits={"composition-301": "train"},
        )


def test_cli_writes_one_fresh_private_path_free_preparation(tmp_path: Path) -> None:
    fixture, registry, variants, label = _evidence("401")
    inputs = {}
    for name, value in (
        ("label", label),
        ("registry", registry),
        ("variants", variants),
    ):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        inputs[name] = path
    output = tmp_path / "prepared.json"
    script = Path(__file__).parents[1] / "scripts" / "prepare-remix-training-dataset.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--snapshot-id",
            "owner-pilot-004",
            "--label",
            str(inputs["label"]),
            "--owner-registry",
            str(inputs["registry"]),
            "--variant-set",
            str(inputs["variants"]),
            "--split",
            "composition-401=train",
            "--out",
            str(output),
        ],
        cwd=Path(__file__).parents[1],
        env={**os.environ, "PYTHONPATH": "src"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    prepared = validate_remix_training_dataset_preparation(
        json.loads(output.read_text(encoding="utf-8"))
    )
    assert prepared["readiness"]["next_gate"] == "collect_owner_labels"
    assert output.stat().st_mode & 0o777 == 0o600
    assert str(tmp_path) not in output.read_text(encoding="utf-8")
