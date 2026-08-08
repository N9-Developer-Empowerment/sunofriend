from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from sunofriend.separation_other_refinement_query_load_contract import (
    EXPECTED_CHECKPOINTS,
    EXPECTED_EFFECTS,
    EXPECTED_GUARDS,
    EXPECTED_MODEL_STATES,
    QUERY_BANDIT_SOURCE_REVISION,
    QUERY_MODEL_LOAD_REPORT_SCHEMA,
    QUERY_MODEL_LOAD_REPORT_STATUS,
    build_query_model_load_receipt,
    query_model_load_report_sha256,
    validate_query_model_load_report,
)


ROOT = Path(__file__).resolve().parents[1]


def _report() -> dict:
    models = {
        label: {
            **inventory,
            "keys_equal": True,
            "shapes_equal": True,
            "dtypes_equal": True,
            "strict_load_missing_keys": [],
            "strict_load_unexpected_keys": [],
            "architecture": (
                "pinned setup-C adapter, pretrained=False"
                if label == "banquet"
                else "OpenMIC PaSST, pretrained=False, 20 classes"
            ),
        }
        for label, inventory in EXPECTED_MODEL_STATES.items()
    }
    models["banquet"]["checkpoint_root_prefix_removed_for_load"] = "model."
    models["models_retained_until_process_exit"] = True
    report = {
        "schema": QUERY_MODEL_LOAD_REPORT_SCHEMA,
        "report_sha256": "",
        "status": QUERY_MODEL_LOAD_REPORT_STATUS,
        "source_revision": QUERY_BANDIT_SOURCE_REVISION,
        "runtime": {
            "numpy": "1.26.4",
            "python": "3.12.10",
            "torch": "2.2.2",
            "torchaudio": "2.2.2",
        },
        "checkpoints": EXPECTED_CHECKPOINTS,
        "models": models,
        "guards": EXPECTED_GUARDS,
        "effects": EXPECTED_EFFECTS,
    }
    report["report_sha256"] = query_model_load_report_sha256(report)
    return report


def test_model_load_report_contract_accepts_exact_evidence() -> None:
    report = _report()

    assert validate_query_model_load_report(report) == report


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("models", "banquet", "dtypes_equal"), False, "dtypes_equal"),
        (("guards", "network_attempts"), 1, "guards differ"),
        (("effects", "inference_runs"), 1, "effects differ"),
    ],
)
def test_model_load_report_contract_rejects_changed_evidence(
    path: tuple[str, ...], value: object, message: str
) -> None:
    report = copy.deepcopy(_report())
    target = report
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    report["report_sha256"] = query_model_load_report_sha256(report)

    with pytest.raises(ValueError, match=message):
        validate_query_model_load_report(report)


def test_model_load_receipt_preserves_the_no_inference_boundary(tmp_path: Path) -> None:
    receipt = build_query_model_load_receipt(
        _report(), published_root=tmp_path.resolve(), recorded_at="2026-08-08T12:00:00Z"
    )

    assert receipt["checkpoint_loaded"] is True
    assert receipt["model_constructed"] is True
    assert receipt["inference_performed"] is False
    assert receipt["audio_processed"] is False
    assert receipt["public_activation"] is False
    assert receipt["not_approved"] == [
        "inference",
        "audio_processing",
        "public_activation",
        "source_selection",
        "midi",
    ]


def test_model_load_receipt_script_refuses_to_overwrite(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    receipt_path = tmp_path / "receipt.json"
    report_path.write_text(json.dumps(_report()), encoding="utf-8")
    command = [
        sys.executable,
        str(ROOT / "scripts" / "record-separation-other-refinement-query-model-load.py"),
        "--report",
        str(report_path),
        "--receipt",
        str(receipt_path),
        "--published-root",
        str((tmp_path / "published").resolve()),
    ]
    environment = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }

    subprocess.run(command, cwd=ROOT, env=environment, check=True)
    repeated = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True)

    assert repeated.returncode != 0
    assert json.loads(receipt_path.read_text(encoding="utf-8"))["inference_performed"] is False
