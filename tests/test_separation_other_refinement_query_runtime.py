from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from sunofriend.separation_other_refinement_query_runtime import (
    build_query_runtime_audit,
    validate_query_runtime_audit,
)


ROOT = Path(__file__).resolve().parents[1]


def test_query_runtime_audit_names_hidden_artifact_and_forbids_loaders() -> None:
    audit = build_query_runtime_audit()

    assert audit["status"] == (
        "blocked_pending_explicit_synthetic_inference_approval"
    )
    assert audit["registered"] is False
    assert audit["executable"] is False
    assert audit["source_audit"]["query_bandit"]["revision"] == (
        "79ed5bb75e5c3a40cd319d9d990cee913fc65c26"
    )
    assert audit["source_audit"]["query_bandit"][
        "checkpoint_lightning_version_observed_statically"
    ] == "2.1.3"
    passt = audit["required_artifacts"]["passt_openmic"]
    assert passt["published_bytes"] == 341_546_630
    assert passt["sha256"] == (
        "dc229428753176e8be0373d25887116fc15b490af86f671cecf9ed76a0f287da"
    )
    assert passt["evidence_sha256"] == (
        "990348267a373e2fe62c2fc87a13914411d7fe763b160568c87127a315f58362"
    )
    assert passt["evidence_complete"] is True
    assert passt["evidence_only_download_approved"] is True
    assert passt["network_denied_static_inspection_complete"] is True
    assert passt["loaded"] is True
    assert audit["required_artifacts"]["banquet"]["loaded"] is True
    contract = audit["restricted_loading_contract"]
    assert contract["use_upstream_train_cli"] is False
    assert contract["use_lightning_load_from_checkpoint"] is False
    assert contract["use_upstream_passt_download_helper"] is False
    assert contract["use_unrestricted_torch_load"] is False
    assert "weights_only=True" in contract["banquet_loader"]
    assert "weights_only=True" in contract["passt_loader"]
    assert audit["proposed_runtime_identity"]["model_artifact_hashes_complete"] is True
    runtime = audit["proposed_runtime_identity"]
    assert runtime["runtime_dependency_hashes_complete"] is True
    assert runtime["wheel_evidence"]["package_count"] == 28
    assert runtime["wheel_evidence"]["wheel_bytes"] == 99_354_620
    assert runtime["wheel_evidence"]["requirements_sha256"] == (
        "28249f5d6ab80d4b72a5f256ac435f3a2d150b1baa30d751754af44049c33b92"
    )
    assert runtime["wheel_evidence"]["dependency_installed"] is False
    assert runtime["wheel_evidence"]["packages_imported"] is False
    assert runtime["installation_approved"] is True
    assert runtime["installation_complete"] is True
    assert runtime["apple_silicon_import_verified"] is True
    import_evidence = runtime["import_evidence"]
    assert import_evidence["locked_package_count"] == 28
    assert import_evidence["target"] == "CPython 3.12.10, macOS arm64"
    assert import_evidence["dependency_installed"] is True
    assert import_evidence["network_denied"] is True
    assert import_evidence["network_attempts"] == 0
    assert import_evidence["checkpoint_open_attempts"] == 0
    assert import_evidence["torch_load_calls"] == 0
    assert import_evidence["audio_open_attempts"] == 0
    assert import_evidence["checkpoint_loaded"] is False
    assert import_evidence["model_constructed"] is False
    load = runtime["model_load_evidence"]
    assert load["status"] == (
        "two_exact_models_constructed_and_strictly_loaded_network_denied"
    )
    assert load["model_load_report_sha256"] == (
        "12c028e88afdb94a22aa4344b75fb63a23386fd4f2292d9bf9aac0405b12dced"
    )
    assert load["network_attempts"] == 0
    assert load["audio_open_attempts"] == 0
    assert load["checkpoint_loaded"] is True
    assert load["model_constructed"] is True
    assert load["inference_runs"] == 0
    for model_name in ("banquet", "passt"):
        assert load[model_name]["keys_equal"] is True
        assert load[model_name]["shapes_equal"] is True
        assert load[model_name]["dtypes_equal"] is True
        assert load[model_name]["strict_load_missing_keys"] == []
        assert load[model_name]["strict_load_unexpected_keys"] == []
    assert audit["next_gate"]["kind"] == (
        "review_network_denied_synthetic_adapter_inference_plan"
    )
    assert audit["next_gate"]["plan_command"] == (
        "python3 scripts/plan-separation-other-refinement-query-synthetic.py"
    )
    assert audit["next_gate"]["dependency_artifact_download_approved"] is True
    assert audit["next_gate"]["dependency_artifact_download_complete"] is True
    assert audit["next_gate"]["dependency_installation"] is True
    assert audit["next_gate"]["package_import"] is True
    assert audit["next_gate"]["model_loading"] is True
    assert audit["next_gate"]["model_construction"] is True
    assert not any(
        value is True
        for key, value in audit["effects"].items()
        if key not in {"inference_runs", "audio_reads", "audio_writes"}
    )
    assert audit["effects"]["inference_runs"] == 0
    assert validate_query_runtime_audit(audit) == audit


def test_query_runtime_audit_rejects_authority_expansion() -> None:
    audit = build_query_runtime_audit()
    changed = copy.deepcopy(audit)
    changed["next_gate"]["inference"] = True

    with pytest.raises(ValueError, match="differs from the reviewed audit"):
        validate_query_runtime_audit(changed)


def test_query_runtime_plan_script_is_read_only() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(
                ROOT
                / "scripts"
                / "plan-separation-other-refinement-query-runtime.py"
            ),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    document = json.loads(result.stdout)

    assert document == build_query_runtime_audit()
    assert document["effects"]["network_used_by_plan"] is False
    assert document["effects"]["artifact_downloaded_by_plan"] is False


def test_restricted_model_load_script_has_no_inference_or_audio_interface() -> None:
    runner_source = (
        ROOT
        / "scripts"
        / "verify-separation-other-refinement-query-model-load.py"
    ).read_text(encoding="utf-8")
    adapter_source = (
        ROOT
        / "src"
        / "sunofriend"
        / "separation_other_refinement_query_model_adapter.py"
    ).read_text(encoding="utf-8")
    loading_source = (
        ROOT
        / "src"
        / "sunofriend"
        / "separation_other_refinement_query_model_loading.py"
    ).read_text(encoding="utf-8")
    combined_source = runner_source + adapter_source + loading_source

    assert "def forward" not in combined_source
    assert 'parser.add_argument("--banquet"' in runner_source
    assert 'parser.add_argument("--passt"' in runner_source
    assert 'parser.add_argument("--audio"' not in combined_source
    assert "class BanquetLoadAdapter" in adapter_source
    assert "class BanquetLoadAdapter" not in runner_source
    assert "load_query_models" in runner_source
    assert "torch.load" not in adapter_source
    assert "argparse" not in adapter_source
    assert "sys.addaudithook" not in adapter_source
    assert "socket" not in loading_source
    assert "urllib.request" not in loading_source
    assert "sys.addaudithook" in runner_source
    assert "pretrained=False" in adapter_source
    assert "weights_only=True" in loading_source
    assert 'map_location="cpu"' in loading_source
    assert '"inference_runs": 0' in runner_source
    assert '"audio_reads": 0' in runner_source
    assert '"public_activation": False' in runner_source


def test_restricted_model_load_requires_its_explicit_acceptance_flag() -> None:
    source = (
        ROOT
        / "scripts"
        / "setup-separation-other-refinement-query-runtime-macos.sh"
    ).read_text(encoding="utf-8")

    assert "--construct-and-load-models" in source
    assert "--accept-restricted-model-load" in source
    assert "deny network*" in source
    assert "MODEL-LOAD-REPORT.json" in source
    assert "record-separation-other-refinement-query-model-load.py" in source
    assert "No inference or audio ran" in source
