from __future__ import annotations

import json
import hashlib
import os
import struct
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import sunofriend._separation_melroformer_challenger_plan as melroformer
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS


def test_plan_is_exact_read_only_and_fail_closed() -> None:
    with (
        patch("socket.create_connection", side_effect=AssertionError("network")),
        patch("subprocess.run", side_effect=AssertionError("process")),
    ):
        plan = melroformer._build_private_melroformer_challenger_plan()

    assert plan["status"] == "blocked"
    assert plan["read_only"] is True
    assert plan["candidate"]["roles"] == ["vocals"]
    assert plan["candidate"]["broad_separator"] is False
    assert plan["candidate"]["derived_role_equation"] == (
        "instrumental = mixture - vocals"
    )
    assert plan["source"]["conversion_revision"] == (
        "64cbfcb004e39430e5f584552c05949440ec39ce"
    )
    assert plan["checkpoint"]["format"] == "safetensors"
    assert plan["checkpoint"]["published_sha256"] == (
        "312c38e5b698f8dfaa4d6064e8f79010744825828917871a9d22673a43eb7fe5"
    )
    assert plan["checkpoint"]["checkpoint_specific_terms_verified"] is True
    assert plan["checkpoint"]["download_permitted"] is False
    assert plan["checkpoint"]["static_inspection_contract_defined"] is True
    assert plan["licensing"]["explicit_user_approval_recorded"] is True
    assert plan["licensing"]["checkpoint_redistribution_approved"] is False
    assert plan["alternatives_reviewed"][0]["admitted"] is False
    assert plan["alternatives_reviewed"][1]["admitted"] is False
    assert plan["upstream_evidence"] == {
        "path": melroformer.UPSTREAM_EVIDENCE,
        "bytes": melroformer.UPSTREAM_EVIDENCE_BYTES,
        "sha256": melroformer.UPSTREAM_EVIDENCE_SHA256,
        "observed_at": "2026-08-01",
        "official_primary_sources_only": True,
        "checkpoint_terms_verified": True,
        "checkpoint_published_sha256_verified": True,
        "local_checkpoint_identity_verified": False,
        "verified_in_this_call": False,
        "verification_command": (
            "scripts/private-melroformer-upstream-evidence.py "
            "--repository-root /absolute/path/to/Sunofriend"
        ),
    }
    assert plan["runtime"]["installation_command"] is None
    assert plan["runtime"]["installation_permitted"] is False
    assert plan["runtime"]["exact_source_manifest_defined"] is True
    assert plan["runtime"]["dependency_lock_defined"] is True
    assert plan["runtime"]["dependency_license_audit_defined"] is True
    assert plan["runtime"]["worker_protocol_defined"] is True
    assert plan["runtime"]["network_denial_canary_implemented"] is True
    assert plan["runtime"]["network_denial_canary_passed_on_development_host"] is True
    assert (
        plan["runtime"]["network_denial_canary_latest_observation"]["evidence_sha256"]
        == "ff64dca9e59a8862b68202842ed1ede67e39bbcfb824bb97427620c23c658b86"
    )
    assert plan["runtime"]["network_denial_bound_to_model_worker"] is True
    assert plan["runtime"]["outbound_model_attempt_observation_implemented"] is False
    assert plan["runtime"]["pcm24_quarantine_implemented"] is True
    assert plan["runtime"]["pcm24_quarantine_synthetic_full_excerpt_passed"] is True
    assert plan["runtime"]["pcm24_quarantine_bound_to_worker"] is True
    assert plan["runtime"]["synthetic_worker_sandbox_implemented"] is True
    assert (
        plan["runtime"]["synthetic_worker_sandbox_latest_observation"][
            "evidence_sha256"
        ]
        == "8b1a91a95609d09175be6240af2a9d44f5bd8161249ebab01b9878e7cb406cb4"
    )
    assert plan["runtime"]["synthetic_worker_implemented"] is True
    assert plan["runtime"]["authorised_worker_sandbox_implemented"] is True
    assert (
        plan["runtime"]["authorised_worker_sandbox_latest_observation"][
            "evidence_sha256"
        ]
        == "3de1b71ef552cd46d1bff1784c4843b7709eeaf945cf3778e53737ca08f350a8"
    )
    assert plan["runtime"]["complete_python_import_closure_bound"] is True
    closure = plan["runtime"]["authorised_worker_sandbox_latest_observation"]
    assert closure["complete_python_import_closure_bound"] is True
    assert closure["python_module_count"] == 320
    assert closure["python_module_file_count"] == 277
    assert closure["python_unclassified_module_count"] == 0
    assert closure["native_non_module_loads_bound"] is False
    assert (
        plan["runtime"]["authorised_worker_sandbox_latest_observation"][
            "observation_persisted_owner_only"
        ]
        is True
    )
    assert plan["runtime"]["model_worker_implemented"] is True
    assert plan["runtime"]["synthetic_adapter_contract_defined"] is True
    assert plan["runtime"]["real_model_bridge_probe_implemented"] is True
    assert plan["runtime"]["real_adapter_implemented"] is True
    assert plan["runtime"]["synthetic_real_model_smoke_passed"] is True
    assert plan["runtime"]["real_adapter_maximum_probe_seconds"] == 8.0
    assert plan["runtime"]["full_excerpt_chunk_transport_implemented"] is True
    assert plan["runtime"]["synthetic_full_excerpt_smoke_passed"] is True
    assert plan["runtime"]["full_excerpt_smoke_measurement"]["chunk_count"] == 3
    assert plan["runtime"]["authorised_excerpt_smoke_passed"] is True
    assert (
        plan["evaluation_contract"]["latest_private_observation"][
            "quality_comparison_completed"
        ]
        is True
    )
    assert (
        plan["runtime"]["numeric_repeatability_observation"][
            "gpu_authorised_excerpt_same_process"
        ]["pcm24_projection_maximum_integer_difference"]
        == 1
    )
    assert (
        plan["runtime"]["numeric_repeatability_observation"][
            "cpu_full_excerpt_separate_processes"
        ]["byte_identical"]
        is True
    )
    assert plan["runtime"]["output_repeatability_policy"]["defined"] is True
    assert plan["runtime"]["output_repeatability_policy"]["default_mode"] == (
        "fast_gpu"
    )
    assert (
        plan["evaluation_contract"]["latest_private_observation"]["winner_selected"]
        is False
    )
    assert (
        plan["evaluation_contract"]["cross_song_downstream_vocal_midi_complete"] is True
    )
    downstream = plan["evaluation_contract"]["downstream_vocal_midi_observations"]
    assert [item["note_count"] for item in downstream] == [14, 23]
    assert all(item["equal_level_blind_review_prepared"] for item in downstream)
    assert not any(item["equal_level_blind_review_complete"] for item in downstream)
    assert not any(item["answer_key_opened_by_developer"] for item in downstream)
    assert not any(item["winner_selected"] for item in downstream)
    assert plan["source"]["upstream_from_pretrained_permitted"] is False
    assert plan["runtime"]["reported_parity_is_model_ground_truth_score"] is False
    conversion = plan["runtime"]["weight_conversion_parity"]
    assert conversion["status"] == "verified_exact_bf16_weight_conversion"
    assert conversion["source_state_dict_key_count"] == 684
    assert conversion["converted_tensor_count"] == 708
    assert conversion["packed_qkv_split_count"] == 12
    assert conversion["every_tensor_name_shape_and_bf16_payload_bit_exact"] is True
    assert conversion["inference_output_parity_independently_verified"] is False
    assert conversion["product_route_changed"] is False
    inference = plan["runtime"]["inference_output_parity"]
    assert inference["converted_bf16_runtime_output_parity_above_threshold"] is True
    assert inference["original_fp32_source_to_converted_mlx_above_threshold"] is False
    assert inference["pytorch_bf16_roundtrip_vs_mlx_bf16_sdr_db"] > 100.0
    assert inference["pytorch_original_fp32_vs_mlx_bf16_sdr_db"] < 40.0
    assert inference["upstream_reported_66_08_db_independently_reproduced"] is False
    assert inference["separator_quality_measured_by_this_gate"] is False
    assert inference["product_route_changed"] is False
    precision_review = plan["runtime"]["precision_listening_review"]
    assert precision_review["status"] == "prepared_unreviewed"
    assert precision_review["source_seconds"] == [191.0, 199.0]
    assert (
        precision_review["candidate_a_rms_dbfs"]
        == (precision_review["candidate_b_rms_dbfs"])
    )
    assert precision_review["answer_key_embedded_in_html"] is False
    assert precision_review["answer_key_opened_by_developer"] is False
    assert precision_review["human_listening_complete"] is False
    assert precision_review["winner_selected"] is False
    assert precision_review["product_route_changed"] is False
    assert plan["decision"]["checkpoint_published_identity_pinned"] is True
    assert plan["decision"]["checkpoint_local_identity_verified"] is False
    assert plan["decision"]["worker_start_permitted"] is False
    assert plan["decision"]["blockers"] == sorted(plan["decision"]["blockers"])
    assert {
        "checkpoint_local_hash_unverified",
        "checkpoint_companion_files_unverified",
        "runtime_source_materialisation_missing",
        "equal_level_human_listening_not_completed",
        "fp32_bf16_precision_listening_not_completed",
        "model_worker_hash_before_exec_path_toctou_not_closed",
        "outbound_model_attempt_observation_not_implemented",
    }.issubset(plan["decision"]["blockers"])
    assert "complete_worker_import_closure_not_bound" not in plan["decision"][
        "blockers"
    ]
    assert (
        "conversion_parity_not_independently_verified"
        not in plan["decision"]["blockers"]
    )
    assert all(value is False for value in plan["effects"].values())


def test_optional_local_observation_hashes_without_authorizing(tmp_path: Path) -> None:
    checkpoint = tmp_path / melroformer.CHECKPOINT_NAME
    checkpoint.write_bytes(b"not the published checkpoint")
    plan = melroformer._build_private_melroformer_challenger_plan(
        checkpoint_path=checkpoint
    )

    observed = plan["checkpoint"]["local_observation"]
    assert observed["provided"] is True
    assert observed["bytes"] == len(b"not the published checkpoint")
    assert observed["published_size_match"] is False
    assert observed["published_sha256_match"] is False
    assert observed["cryptographic_identity_verified"] is False
    assert plan["checkpoint"]["acquisition_status"] == "local_identity_mismatch"
    assert plan["decision"]["private_evaluation_eligible"] is False
    assert plan["effects"]["local_checkpoint_opened"] is True
    assert plan["effects"]["model_imported"] is False


def test_materialised_artifacts_complete_preflight_without_authorizing_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    encoded = json.dumps(
        {
            "weight": {"dtype": "BF16", "shape": [2], "data_offsets": [0, 4]},
            "__metadata__": None,
        },
        separators=(",", ":"),
    ).encode()
    checkpoint_contents = struct.pack("<Q", len(encoded)) + encoded + b"1234"
    checkpoint = tmp_path / melroformer.CHECKPOINT_NAME
    checkpoint.write_bytes(checkpoint_contents)
    companion_root = tmp_path / "companions"
    companion_root.mkdir()
    config = companion_root / melroformer.CONFIG_NAME
    license_file = companion_root / melroformer.LICENSE_NAME
    config.write_bytes(b"config")
    license_file.write_bytes(b"license")
    source_root = tmp_path / "source"
    source_root.mkdir()

    monkeypatch.setattr(
        melroformer, "CONVERSION_CHECKPOINT_BYTES", len(checkpoint_contents)
    )
    monkeypatch.setattr(
        melroformer,
        "CONVERSION_CHECKPOINT_SHA256",
        hashlib.sha256(checkpoint_contents).hexdigest(),
    )
    monkeypatch.setattr(melroformer, "CONFIG_BYTES", len(b"config"))
    monkeypatch.setattr(
        melroformer, "CONFIG_SHA256", hashlib.sha256(b"config").hexdigest()
    )
    monkeypatch.setattr(melroformer, "LICENSE_BYTES", len(b"license"))
    monkeypatch.setattr(
        melroformer, "LICENSE_SHA256", hashlib.sha256(b"license").hexdigest()
    )
    monkeypatch.setattr(
        melroformer,
        "_verify_private_melroformer_source_tree",
        lambda value: {"status": "verified_not_imported", "source_root": str(value)},
    )

    plan = melroformer._build_private_melroformer_challenger_plan(
        checkpoint_path=checkpoint,
        source_root=source_root,
        companion_root=companion_root,
    )

    assert plan["checkpoint"]["static_inspection_completed"] is True
    assert plan["checkpoint"]["static_inspection"]["tensor_count"] == 1
    assert (
        plan["checkpoint"]["static_inspection"][
            "mlx_null_metadata_compatibility_applied"
        ]
        is True
    )
    assert plan["source"]["runtime_source_materialised"] is True
    assert plan["companion_files"]["all_cryptographic_identities_verified"] is True
    assert plan["decision"]["artifact_preflight_complete"] is True
    assert plan["decision"]["private_evaluation_eligible"] is True
    assert plan["decision"]["worker_start_permitted"] is False
    assert (
        "full_excerpt_chunk_transport_not_implemented"
        not in plan["decision"]["blockers"]
    )
    assert (
        "pcm24_output_quarantine_not_bound_to_worker"
        not in plan["decision"]["blockers"]
    )
    assert "runtime_worker_not_implemented" not in plan["decision"]["blockers"]


def test_optional_local_observation_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.safetensors"
    link = tmp_path / "link.safetensors"
    target.write_bytes(b"checkpoint")
    link.symlink_to(target)
    with pytest.raises(ValueError, match="non-symlink regular file"):
        melroformer._build_private_melroformer_challenger_plan(checkpoint_path=link)


def test_private_plan_script_outputs_json_without_public_route() -> None:
    repository = Path(__file__).parents[1]
    script = repository / "scripts/private-melroformer-challenger.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--plan"],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(repository / "src")},
    )
    plan = json.loads(completed.stdout)
    assert plan["decision"]["run_status"] == (
        "bf16_runtime_parity_and_python_import_closure_verified_"
        "reviews_and_safety_pending"
    )
    assert plan["effects"]["network_used"] is False
    assert "private-melroformer-challenger" not in PUBLIC_COMMANDS
    assert "private-melroformer-challenger" not in DIRECT_TUI_COMMANDS
