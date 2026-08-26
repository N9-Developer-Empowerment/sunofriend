from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from sunofriend.remix_ranker_canary import (
    REMIX_RANKER_CHECKPOINT_SCHEMA,
    REMIX_RANKER_SYNTHETIC_FIXTURE_SCHEMA,
    REMIX_RANKER_TRAINING_REQUEST_SCHEMA,
    REMIX_RANKER_TRAINING_RESULT_SCHEMA,
    build_remix_ranker_canary_request,
    build_synthetic_remix_ranker_fixture,
    run_remix_ranker_canary,
    validate_remix_ranker_canary_result,
)
from sunofriend.remix_ranker_verifier import (
    REMIX_RANKER_VERIFICATION_SCHEMA,
    verify_remix_ranker_canary,
)
from sunofriend.source_receipt import document_sha256


def _rehash(document: dict) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)


def test_fixture_and_request_are_synthetic_bounded_and_disjoint() -> None:
    fixture = build_synthetic_remix_ranker_fixture()
    request = build_remix_ranker_canary_request()
    assert fixture == build_synthetic_remix_ranker_fixture()
    assert fixture["schema"] == REMIX_RANKER_SYNTHETIC_FIXTURE_SCHEMA
    assert len(fixture["examples"]) == 192
    train = {
        row["composition_id"] for row in fixture["examples"] if row["split"] == "train"
    }
    heldout = {
        row["composition_id"]
        for row in fixture["examples"]
        if row["split"] == "heldout"
    }
    assert train.isdisjoint(heldout)
    assert request["schema"] == REMIX_RANKER_TRAINING_REQUEST_SCHEMA
    assert request["dataset"]["synthetic"] is True
    assert request["dataset"]["real_snapshot_accepted"] is False
    assert request["limits"]["musicfm_allowed"] is False
    assert request["limits"]["audio_allowed"] is False
    assert request["limits"]["network_allowed"] is False
    assert request["limits"]["downloads_allowed"] is False
    assert not any(request["authority"].values())
    assert "/Users/" not in str(request)


def test_canary_records_constant_linear_mlp_shuffled_and_exact_resume() -> None:
    request = build_remix_ranker_canary_request()
    first = run_remix_ranker_canary(request)
    second = run_remix_ranker_canary(request)
    assert first == second
    assert first["schema"] == REMIX_RANKER_TRAINING_RESULT_SCHEMA
    assert first["status"] == "complete_synthetic_pipeline_canary"
    assert [row["arm_id"] for row in first["arms"]] == [
        "constant",
        "transparent_linear_clean",
        "transparent_mlp_clean",
        "transparent_mlp_serialized_resume",
        "transparent_mlp_shuffled",
    ]
    assert first["metrics"] == {
        "constant_heldout_accuracy": pytest.approx(0.453125),
        "transparent_linear_heldout_accuracy": pytest.approx(0.96875),
        "transparent_mlp_heldout_accuracy": pytest.approx(0.984375),
        "shuffled_mlp_heldout_accuracy": pytest.approx(0.59375),
        "mlp_minus_constant_accuracy": pytest.approx(0.53125),
        "mlp_minus_shuffled_accuracy": pytest.approx(0.390625),
        "maximum_resume_parameter_difference": 0.0,
    }
    assert all(first["acceptance"].values())
    assert first["checkpoint"]["document"]["schema"] == REMIX_RANKER_CHECKPOINT_SCHEMA
    assert (
        first["checkpoint"]["resumed_final_sha256"]
        == first["checkpoint"]["uninterrupted_final_sha256"]
    )
    assert first["privacy"]["synthetic_only"] is True
    assert first["authority"]["checkpoint_promoted"] is False
    assert first["authority"]["product_ranking_changed"] is False
    assert validate_remix_ranker_canary_result(first, request=request) == first


def test_request_result_checkpoint_and_authority_tampering_are_rejected() -> None:
    request = build_remix_ranker_canary_request()
    changed_request = deepcopy(request)
    changed_request["dataset"]["real_snapshot_accepted"] = True
    _rehash(changed_request)
    with pytest.raises(ValueError, match="fixed contract"):
        run_remix_ranker_canary(changed_request)

    result = run_remix_ranker_canary(request)
    changed = deepcopy(result)
    changed["authority"]["checkpoint_promoted"] = True
    _rehash(changed)
    with pytest.raises(ValueError, match="authority"):
        validate_remix_ranker_canary_result(changed, request=request)

    checkpoint = deepcopy(result)
    checkpoint["checkpoint"]["document"]["weights"][0] += 1.0
    _rehash(checkpoint["checkpoint"]["document"])
    _rehash(checkpoint)
    with pytest.raises(ValueError, match="checkpoint"):
        validate_remix_ranker_canary_result(checkpoint, request=request)

    changed_metrics = deepcopy(result)
    changed_metrics["metrics"]["mlp_minus_shuffled_accuracy"] = 0.25
    _rehash(changed_metrics)
    with pytest.raises(ValueError, match="derived metrics"):
        validate_remix_ranker_canary_result(changed_metrics, request=request)

    changed_arm = deepcopy(result)
    changed_arm["arms"][1]["steps"] = 299
    _rehash(changed_arm)
    with pytest.raises(ValueError, match="arm metric"):
        validate_remix_ranker_canary_result(changed_arm, request=request)


def test_independent_verifier_recomputes_exact_result_without_authority() -> None:
    request = build_remix_ranker_canary_request()
    result = run_remix_ranker_canary(request)
    verification = verify_remix_ranker_canary(request, result)
    assert verification["schema"] == REMIX_RANKER_VERIFICATION_SCHEMA
    assert verification["status"] == "verified_synthetic_technical_evidence"
    assert all(verification["checks"].values())
    assert verification["privacy"]["audio_read"] is False
    assert verification["privacy"]["real_snapshot_read"] is False
    assert verification["authority"] == {
        "technical_verification_only": True,
        "training_authorized": False,
        "checkpoint_promoted": False,
        "product_admitted": False,
    }

    forged = deepcopy(result)
    forged["metrics"]["constant_heldout_accuracy"] = 0.5
    forged["metrics"]["mlp_minus_constant_accuracy"] = (
        forged["metrics"]["transparent_mlp_heldout_accuracy"] - 0.5
    )
    _rehash(forged)
    with pytest.raises(ValueError, match="recomputation|acceptance|arm metric"):
        verify_remix_ranker_canary(request, forged)


def test_cli_creates_a_fresh_verifiable_owner_only_package(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    out = tmp_path / "canary"
    environment = {"PYTHONPATH": str(root / "src")}
    subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "run-remix-ranker-canary.py"),
            "--out-dir",
            str(out),
        ],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert out.stat().st_mode & 0o777 == 0o700
    assert {path.name for path in out.iterdir()} == {"request.json", "result.json"}
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in out.iterdir())
    verification = out / "verification.json"
    subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "verify-remix-ranker-canary.py"),
            str(out / "request.json"),
            str(out / "result.json"),
            "--out",
            str(verification),
        ],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert verification.stat().st_mode & 0o777 == 0o600
    assert json.loads(verification.read_text())["status"] == (
        "verified_synthetic_technical_evidence"
    )
