from __future__ import annotations

from unittest.mock import patch

from sunofriend._separation_roformer_challenger_plan import CHECKPOINT_BYTES
from sunofriend._separation_roformer_contract_plan import (
    _build_private_roformer_contract_plan,
)
from sunofriend.separation_checkpoint_inspection import (
    MAX_CHECKPOINT_BYTES,
    SEPARATION_CHECKPOINT_INSPECTION_SCHEMA,
)
from sunofriend.separation_worker_contract import (
    SEPARATION_WORKER_REQUEST_SCHEMA,
    SEPARATION_WORKER_RESULT_SCHEMA,
)


def test_roformer_contract_reuses_bounded_non_authorising_safety_schemas() -> None:
    with (
        patch("builtins.open", side_effect=AssertionError("filesystem")),
        patch("socket.create_connection", side_effect=AssertionError("network")),
        patch("subprocess.run", side_effect=AssertionError("process")),
    ):
        plan = _build_private_roformer_contract_plan(checkpoint_bytes=CHECKPOINT_BYTES)

    inspection = plan["checkpoint_inspection"]
    worker = plan["worker"]
    admission = plan["code_runtime_admission"]
    assert plan["status"] == "defined_not_implemented"
    assert plan["source_boundary"]["fixed_files"] == 3
    assert plan["source_boundary"]["verified_checkout_present"] is False
    assert plan["source_boundary"]["model_import_permitted_by_verification"] is False
    assert admission["implemented"] is True
    assert admission["applied_to_durable_runtime"] is False
    assert admission["authorizes_installation"] is False
    assert admission["authorizes_checkpoint_access"] is False
    assert admission["authorizes_execution"] is False
    assert inspection["schema"] == SEPARATION_CHECKPOINT_INSPECTION_SCHEMA
    assert inspection["limits"]["checkpoint_bytes"] == MAX_CHECKPOINT_BYTES
    assert inspection["published_checkpoint_within_byte_limit"] is True
    assert inspection["applied_to_candidate"] is False
    assert inspection["checkpoint_loaded"] is False
    assert inspection["checkpoint_deserialized"] is False
    assert inspection["authorizes_loading"] is False
    assert inspection["authorizes_execution"] is False
    assert worker["request_schema"] == SEPARATION_WORKER_REQUEST_SCHEMA
    assert worker["result_schema"] == SEPARATION_WORKER_RESULT_SCHEMA
    assert worker["roles"] == ["drums", "bass", "other", "vocals"]
    assert worker["output_allowlist"] == [
        "STEMS/drums.wav",
        "STEMS/bass.wav",
        "STEMS/other.wav",
        "STEMS/vocals.wav",
    ]
    assert worker["source"]["maximum_seconds"] == 15.0
    assert worker["implemented"] is False
    assert worker["execution_permitted"] is False
    assert all(value is False for value in plan["effects"].values())


def test_roformer_contract_fails_size_admission_without_side_effects() -> None:
    plan = _build_private_roformer_contract_plan(
        checkpoint_bytes=MAX_CHECKPOINT_BYTES + 1
    )

    assert (
        plan["checkpoint_inspection"]["published_checkpoint_within_byte_limit"] is False
    )
    assert plan["readiness"]["private_evaluation_eligible"] is False
    assert plan["worker"]["execution_permitted"] is False
