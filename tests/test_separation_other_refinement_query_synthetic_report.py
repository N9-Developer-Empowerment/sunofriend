from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from sunofriend.separation_other_refinement_query_synthetic_report import (
    EXPECTED_GENERATED_INPUTS,
    EXPECTED_GUARDS,
    EXPECTED_RUNTIME,
    build_query_synthetic_receipt,
    build_query_synthetic_report_contract,
    query_synthetic_report_sha256,
    validate_query_synthetic_report,
    validate_query_synthetic_report_contract,
)


ROOT = Path(__file__).resolve().parents[1]
PLAN_SHA256 = "a" * 64


def _report(*, forward_completed: bool = True) -> dict[str, object]:
    contract = build_query_synthetic_report_contract()
    if forward_completed:
        result = {
            "forward_completed": True,
            "output_shape": [1, 2, 88_200],
            "output_dtype": "float32",
            "output_sample_rate_hz": 44_100,
            "all_output_samples_finite": True,
            "target_peak": 0.25,
            "residual_peak": 0.4,
            "maximum_reconstruction_error": 5e-7,
            "residual_definition": "generated_mixture - requested_target",
            "elapsed_seconds": 12.5,
            "peak_resident_set_bytes": 4_000_000_000,
            "failure_code": "none",
        }
        gates = {name: "pass" for name in contract["objective_gates"]["names"]}
        status = "objective_pass"
    else:
        result = {
            "forward_completed": False,
            "output_shape": None,
            "output_dtype": None,
            "output_sample_rate_hz": None,
            "all_output_samples_finite": None,
            "target_peak": None,
            "residual_peak": None,
            "maximum_reconstruction_error": None,
            "residual_definition": None,
            "elapsed_seconds": 2.0,
            "peak_resident_set_bytes": 3_000_000_000,
            "failure_code": "forward_exception",
        }
        gates = {
            "checkpoint_and_model_identity": "pass",
            "network_denied": "pass",
            "no_audio_access": "pass",
            "forward_completed": "fail",
            "output_shape_and_clock": "not_reached",
            "finite_output": "not_reached",
            "target_and_residual_peaks_recorded": "not_reached",
            "reconstruction_accounting": "not_reached",
            "elapsed_time_ceiling": "pass",
            "peak_memory_ceiling": "pass",
        }
        status = "objective_failure_recorded"
    report: dict[str, object] = {
        "schema": contract["report_schema"],
        "report_sha256": "",
        "status": status,
        "evidence_binding": {
            **contract["identity"],
            "synthetic_plan_document_sha256": PLAN_SHA256,
            "report_contract_document_sha256": contract["document_sha256"],
        },
        "attempt": contract["attempt_contract"],
        "runtime": EXPECTED_RUNTIME,
        "generated_inputs": EXPECTED_GENERATED_INPUTS,
        "guards": EXPECTED_GUARDS,
        "result": result,
        "objective_gates": gates,
        "decision": {
            "objective_gates_passed": forward_completed,
            "result_retained": True,
            "eligible_for_separate_next_plan": forward_completed,
            "automatic_retry_or_remediation": False,
            "subjective_feedback_considered": False,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
        },
        "effects": {
            "checkpoint_loaded": True,
            "model_constructed": True,
            "generated_tensors_created": True,
            "inference_attempts": 1,
            "inference_completions": 1 if forward_completed else 0,
            "audio_reads": 0,
            "audio_writes": 0,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
        },
    }
    report["report_sha256"] = query_synthetic_report_sha256(report)
    return report


def test_report_contract_has_no_effects_and_forbids_feedback_gating() -> None:
    contract = build_query_synthetic_report_contract()
    source = (
        ROOT
        / "src"
        / "sunofriend"
        / "separation_other_refinement_query_synthetic_report.py"
    ).read_text(encoding="utf-8")

    assert contract["status"] == "validator_ready_inference_unapproved"
    assert contract["attempt_contract"]["inference_attempt_limit"] == 1
    assert contract["decision_policy"]["subjective_feedback_fields_allowed"] is False
    assert contract["decision_policy"]["automatic_retry_or_remediation"] is False
    assert contract["effects"]["inference_runs"] == 0
    assert contract["effects"]["checkpoint_opened"] is False
    assert "import torch" not in source
    assert "import torchaudio" not in source
    assert "import numpy" not in source
    assert validate_query_synthetic_report_contract(contract) == contract


def test_report_contract_rejects_authority_expansion() -> None:
    contract = copy.deepcopy(build_query_synthetic_report_contract())
    contract["decision_policy"]["automatic_retry_or_remediation"] = True

    with pytest.raises(ValueError, match="report contract differs"):
        validate_query_synthetic_report_contract(contract)


@pytest.mark.parametrize("forward_completed", [True, False])
def test_validator_accepts_pass_or_retained_failure(
    forward_completed: bool,
) -> None:
    report = _report(forward_completed=forward_completed)

    assert validate_query_synthetic_report(
        report,
        expected_plan_sha256=PLAN_SHA256,
    ) == report


def test_validator_rejects_subjective_or_retry_authority() -> None:
    report = _report()
    report["usefulness_rating"] = 5
    report["report_sha256"] = query_synthetic_report_sha256(report)
    with pytest.raises(ValueError, match="report fields differ"):
        validate_query_synthetic_report(
            report,
            expected_plan_sha256=PLAN_SHA256,
        )

    report = _report(forward_completed=False)
    report["decision"]["automatic_retry_or_remediation"] = True  # type: ignore[index]
    report["report_sha256"] = query_synthetic_report_sha256(report)
    with pytest.raises(ValueError, match="decision projection differs"):
        validate_query_synthetic_report(
            report,
            expected_plan_sha256=PLAN_SHA256,
        )


def test_validator_rejects_a_mislabelled_objective_failure() -> None:
    report = _report(forward_completed=False)
    report["result"]["failure_code"] = "output_contract"  # type: ignore[index]
    report["report_sha256"] = query_synthetic_report_sha256(report)

    with pytest.raises(ValueError, match="failure code differs from objective gates"):
        validate_query_synthetic_report(
            report,
            expected_plan_sha256=PLAN_SHA256,
        )


def test_failure_receipt_grants_no_retry_or_product_authority(tmp_path: Path) -> None:
    receipt = build_query_synthetic_receipt(
        _report(forward_completed=False),
        expected_plan_sha256=PLAN_SHA256,
        published_root=tmp_path.resolve(),
        recorded_at="2026-08-08T12:00:00+00:00",
    )

    assert receipt["status"] == (
        "synthetic_objective_failure_retained_no_retry_authority"
    )
    assert receipt["result_retained"] is True
    assert receipt["retry_authorized"] is False
    assert receipt["public_activation"] is False
    assert receipt["source_selection"] is False
    assert receipt["midi_created"] is False


def test_plan_script_is_no_effects_and_receipt_cli_writes_exclusively(
    tmp_path: Path,
) -> None:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    plan = subprocess.run(
        [
            sys.executable,
            str(
                ROOT
                / "scripts"
                / "plan-separation-other-refinement-query-synthetic-report.py"
            ),
        ],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(plan.stdout) == build_query_synthetic_report_contract()

    report_path = tmp_path / "report.json"
    receipt_path = tmp_path / "receipt.json"
    report_path.write_text(
        json.dumps(_report(forward_completed=False)),
        encoding="utf-8",
    )
    command = [
        sys.executable,
        str(
            ROOT
            / "scripts"
            / "record-separation-other-refinement-query-synthetic.py"
        ),
        "--report",
        str(report_path),
        "--receipt",
        str(receipt_path),
        "--published-root",
        str(tmp_path.resolve()),
        "--expected-plan-sha256",
        PLAN_SHA256,
    ]
    subprocess.run(command, cwd=ROOT, env=environment, check=True)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["retry_authorized"] is False

    repeated = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert repeated.returncode != 0
