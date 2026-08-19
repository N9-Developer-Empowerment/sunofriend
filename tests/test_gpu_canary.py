from __future__ import annotations

from sunofriend.gpu_canary import (
    EXPERIMENT_ID,
    SYNTHETIC_FIXTURE_SCHEMA,
    build_c0_canary_request,
    build_synthetic_fixture,
)
from sunofriend.gpu_worker_contract import validate_gpu_worker_request
from sunofriend.source_receipt import document_sha256


def test_synthetic_fixture_is_deterministic_and_group_disjoint() -> None:
    first = build_synthetic_fixture()
    second = build_synthetic_fixture()

    assert first == second
    assert first["schema"] == SYNTHETIC_FIXTURE_SCHEMA
    assert len(first["examples"]) == 256
    train_groups = {
        row["group_id"] for row in first["examples"] if row["split"] == "train"
    }
    heldout_groups = {
        row["group_id"] for row in first["examples"] if row["split"] == "heldout"
    }
    assert len(train_groups) == 12
    assert len(heldout_groups) == 4
    assert train_groups.isdisjoint(heldout_groups)


def test_c0_request_binds_fixture_and_safe_rtx_ceilings() -> None:
    fixture = build_synthetic_fixture()
    request = build_c0_canary_request("a" * 40)

    assert request["experiment_id"] == EXPERIMENT_ID
    assert request["method_natures"] == ["D", "T"]
    assert request["dataset"]["sha256"] == document_sha256(fixture)
    assert request["authorised_asset_hashes"] == [document_sha256(fixture)]
    assert request["execution_policy"] == {
        "network_allowed": False,
        "downloads_allowed": False,
        "maximum_retries": 0,
        "cublas_workspace_config": ":4096:8",
    }
    assert request["resource_ceiling"]["maximum_gpu_bytes"] == 4_294_967_296
    assert request["training"]["maximum_steps_per_arm"] == 200
    assert request["training"]["shuffled_label_control"] is True
    assert validate_gpu_worker_request(request) == request
