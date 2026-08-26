from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from test_remix_feature_contract import _snapshot
from test_remix_musicfm_fma_runtime import _evidence
from test_remix_musicfm_fma_runtime_resolution import _report
from sunofriend.remix_feature_contract import create_remix_operation_feature_manifest
from sunofriend.remix_musicfm_fma_runtime import create_musicfm_fma_runtime_plan
from sunofriend.remix_musicfm_fma_runtime_resolution import (
    create_musicfm_fma_runtime_resolution,
)
from sunofriend.remix_musicfm_feature_plan import (
    MUSICFM_REMIX_FEATURE_PLAN_SCHEMA,
    create_musicfm_remix_feature_plan,
    validate_musicfm_remix_feature_plan,
)
from sunofriend.source_receipt import document_sha256


def _plan_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple:
    snapshot = _snapshot()
    operation = create_remix_operation_feature_manifest(
        snapshot,
        feature_set_id="transparent-remix-baseline-001",
        repository_commit="7" * 40,
    )
    admission, static, readiness = _evidence(tmp_path, monkeypatch)
    runtime = create_musicfm_fma_runtime_plan(
        admission, static, readiness, repository_commit="6" * 40
    )
    report = _report()
    resolution = create_musicfm_fma_runtime_resolution(
        runtime, resolver_report_bytes=report, repository_commit="5" * 40
    )
    return (
        snapshot,
        operation,
        admission,
        static,
        readiness,
        runtime,
        resolution,
        report,
    )


def test_feature_plan_binds_exact_inputs_but_grants_no_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _plan_inputs(tmp_path, monkeypatch)
    plan = create_musicfm_remix_feature_plan(
        *inputs[:-1], resolver_report_bytes=inputs[-1], repository_commit="4" * 40
    )

    assert plan["schema"] == MUSICFM_REMIX_FEATURE_PLAN_SCHEMA
    assert plan["status"] == "planned_blocked_before_feature_extraction"
    assert len(plan["cases"]) == 2
    assert plan["extractor"]["feature_dimension"] == 1_024
    assert plan["extractor"]["extractor_frozen"] is True
    assert plan["cases"][0]["crop"] == {"start_frame": 0, "end_frame": 32_000}
    assert plan["cases"][0]["assignment"]["split"] == "train"
    assert len(plan["cases"][0]["assignment"]["label_document_sha256s"]) == 1
    assert plan["cases"][0]["inputs"]["target_estimate"]["interpretation"] == (
        "separation_estimate_not_ground_truth"
    )
    assert plan["ready_for_feature_extraction"] is False
    assert all(value is False for value in plan["authority"].values())
    assert all(value is False for value in plan["effects"].values())
    assert (
        validate_musicfm_remix_feature_plan(
            plan, *inputs[:-1], resolver_report_bytes=inputs[-1]
        )
        == plan
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda row: row["authority"].update(feature_extraction_authorized=True),
        lambda row: row["effects"].update(features_extracted=True),
        lambda row: row["extractor"].update(gradient_into_extractor=True),
        lambda row: row["gates"].update(
            native_windows_dependency_closure_complete=True
        ),
        lambda row: row["cases"][0]["crop"].update(start_frame=1),
    ],
)
def test_feature_plan_rejects_rehashed_authority_or_input_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutate
) -> None:
    inputs = _plan_inputs(tmp_path, monkeypatch)
    plan = create_musicfm_remix_feature_plan(
        *inputs[:-1], resolver_report_bytes=inputs[-1], repository_commit="4" * 40
    )
    changed = deepcopy(plan)
    mutate(changed)
    changed.pop("document_sha256")
    changed["document_sha256"] = document_sha256(changed)
    with pytest.raises(ValueError, match="evidence or authority"):
        validate_musicfm_remix_feature_plan(
            changed, *inputs[:-1], resolver_report_bytes=inputs[-1]
        )
