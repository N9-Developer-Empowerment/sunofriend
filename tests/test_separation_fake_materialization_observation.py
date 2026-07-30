from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

import sunofriend._separation_fake_executor_darwin as executor_module
from sunofriend._separation_checkpoint_canonical import (
    canonical_sha256,
    deep_freeze,
    plain,
)
from tests.test_separation_fake_execution_quarantine import (
    _records_and_tree,
    _verify,
)


def _observation(tmp_path: Path):
    request, launch_v1, launch_v2, launch_v3, result, directory = (
        _records_and_tree(tmp_path)
    )
    quarantine = _verify(
        (request, launch_v1, launch_v2, launch_v3, result),
        directory,
    )
    outputs = [
        {
            "slot_id": claim["slot_id"],
            "sha256": claim["sha256"],
            "bytes": claim["bytes"],
            "file_identity_sha256": observed["file_identity_sha256"],
        }
        for claim, observed in zip(result["outputs"], quarantine["outputs"])
    ]
    payload = {
        "schema": executor_module._MATERIALIZATION_SCHEMA,
        "status": "exclusive_parent_creation_verified",
        "run_nonce": launch_v3["run_nonce"],
        "fake_worker_result_v2_sha256": result["result_sha256"],
        "quarantine_verification_sha256": quarantine[
            "verification_sha256"
        ],
        "fresh_private_root_created_exclusively": True,
        "fresh_quarantine_created_exclusively": True,
        "output_files_created_exclusively": True,
        "output_files_created_by_parent": True,
        "worker_created_output_files": False,
        "owner_only_permissions": True,
        "read_only_reopen_verified": True,
        "publication_permitted": False,
        "selection_permitted": False,
        "outputs": outputs,
    }
    observation = executor_module._materialization_observation(
        deep_freeze(
            {
                **payload,
                "observation_sha256": canonical_sha256(payload),
            }
        )
    )
    return (
        request,
        launch_v1,
        launch_v2,
        launch_v3,
        result,
        quarantine,
        observation,
    )


def test_materialization_observation_is_exact_path_free_and_self_hashed(
    tmp_path: Path,
) -> None:
    (
        _request,
        _launch_v1,
        _launch_v2,
        launch_v3,
        result,
        quarantine,
        observation,
    ) = _observation(tmp_path)

    assert (
        executor_module._validate_fake_execution_materialization_observation(
            observation,
            fake_launch_plan_v3=launch_v3,
            fake_worker_result_v2=result,
            quarantine=quarantine,
        )
        is observation
    )
    document = plain(observation)
    observation_sha256 = document.pop("observation_sha256")
    assert observation_sha256 == canonical_sha256(document)
    assert not any(
        isinstance(item, str)
        and (item.startswith(("/", "~/", "../", "./")) or "://" in item)
        for item in _values(document)
    )
    mutable_document = plain(observation)
    frozen_copy = executor_module._materialization_observation(
        mutable_document
    )
    mutable_document["publication_permitted"] = True
    assert frozen_copy["publication_permitted"] is False
    assert (
        executor_module._validate_fake_execution_materialization_observation(
            frozen_copy,
            fake_launch_plan_v3=launch_v3,
            fake_worker_result_v2=result,
            quarantine=quarantine,
        )
        is frozen_copy
    )
    with pytest.raises(ValueError, match="exact observation"):
        (
            executor_module
            ._validate_fake_execution_materialization_observation(
                plain(observation),
                fake_launch_plan_v3=launch_v3,
                fake_worker_result_v2=result,
                quarantine=quarantine,
            )
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "result_binding",
        "quarantine_binding",
        "file_identity",
        "publication",
        "output_order",
    ),
)
def test_materialization_observation_rejects_rehashed_tampering(
    mutation: str,
    tmp_path: Path,
) -> None:
    (
        _request,
        _launch_v1,
        _launch_v2,
        launch_v3,
        result,
        quarantine,
        observation,
    ) = _observation(tmp_path)
    document = plain(observation)
    document.pop("observation_sha256")
    if mutation == "result_binding":
        document["fake_worker_result_v2_sha256"] = "f" * 64
    elif mutation == "quarantine_binding":
        document["quarantine_verification_sha256"] = "e" * 64
    elif mutation == "file_identity":
        document["outputs"][0]["file_identity_sha256"] = "d" * 64
    elif mutation == "publication":
        document["publication_permitted"] = True
    else:
        document["outputs"] = list(reversed(document["outputs"]))
    document["observation_sha256"] = canonical_sha256(document)
    tampered = executor_module._materialization_observation(
        deep_freeze(document)
    )

    with pytest.raises(ValueError):
        (
            executor_module
            ._validate_fake_execution_materialization_observation(
                tampered,
                fake_launch_plan_v3=launch_v3,
                fake_worker_result_v2=result,
                quarantine=quarantine,
            )
        )


def test_terminal_receipt_requires_exact_materialization_observation(
    tmp_path: Path,
) -> None:
    (
        request,
        launch_v1,
        launch_v2,
        launch_v3,
        result,
        quarantine,
        observation,
    ) = _observation(tmp_path)
    core = executor_module._FakeExecutionCore(
        fake_worker_request=request,
        fake_launch_plan_v1=launch_v1,
        blocked_fake_launch_plan_v2=launch_v2,
        fake_launch_plan_v3=launch_v3,
        fake_worker_result_v2=result,
        native_execution={},  # type: ignore[arg-type]
        private_root_descriptor=-1,
        private_root_identity=(0, 0),
    )

    with pytest.raises(ValueError, match="exact observation"):
        executor_module._terminal_receipt(
            core=core,
            lease_receipt={},
            materialization=plain(observation),  # type: ignore[arg-type]
            quarantine=quarantine,
        )


def _values(value: Any) -> list[Any]:
    if isinstance(value, Mapping):
        return [
            item
            for nested in value.values()
            for item in [nested, *_values(nested)]
        ]
    if isinstance(value, (tuple, list)):
        return [item for nested in value for item in _values(nested)]
    return [value]
