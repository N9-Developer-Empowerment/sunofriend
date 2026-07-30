from __future__ import annotations

import gc
import inspect
import os
import weakref
from pathlib import Path
from typing import Any, Mapping

import pytest
import sunofriend.separation_checkpoint_descriptor_lease as lease_module

from sunofriend.separation_checkpoint_descriptor_lease import (
    SeparationCheckpointDescriptorLease,
    SeparationCheckpointDescriptorLeaseObservation,
    SeparationCheckpointDescriptorLeaseTerminalReceipt,
    acquire_separation_checkpoint_descriptor_lease,
    close_separation_checkpoint_descriptor_lease,
    recheck_separation_checkpoint_descriptor_lease,
)
from tests._separation_checkpoint_fixtures import (
    canonical_sha256 as _canonical_sha256,
)
from tests._separation_checkpoint_fixtures import (
    checkpoint_fixture as _checkpoint_fixture,
)
from tests._separation_checkpoint_fixtures import (
    inspect_checkpoint as _inspect_checkpoint,
)
from tests._separation_checkpoint_fixtures import (
    inspection_kwargs as _inspection_kwargs,
)
from tests._separation_checkpoint_fixtures import torch_zip as _torch_zip


_PUBLIC_SURFACE = [
    "CHECKPOINT_DESCRIPTOR_LEASE_EXECUTION_SUPPORTED",
    "MAX_ACTIVE_CHECKPOINT_DESCRIPTOR_LEASES",
    "SEPARATION_CHECKPOINT_DESCRIPTOR_LEASE_ID",
    "SEPARATION_CHECKPOINT_DESCRIPTOR_LEASE_OBSERVATION_SCHEMA",
    "SEPARATION_CHECKPOINT_DESCRIPTOR_LEASE_RECEIPT_SCHEMA",
    "SeparationCheckpointDescriptorLease",
    "SeparationCheckpointDescriptorLeaseError",
    "SeparationCheckpointDescriptorLeaseObservation",
    "SeparationCheckpointDescriptorLeaseTerminalReceipt",
    "acquire_separation_checkpoint_descriptor_lease",
    "close_separation_checkpoint_descriptor_lease",
    "recheck_separation_checkpoint_descriptor_lease",
]
_FALSE_EFFECTS = {
    "checkpoint_loaded": False,
    "checkpoint_deserialized": False,
    "model_imported": False,
    "process_started": False,
    "network_used": False,
    "audio_read": False,
    "files_written": False,
    "publication_permitted": False,
    "selection_permitted": False,
    "acceptance_eligible": False,
    "promotion_eligible": False,
}


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _fixture(tmp_path: Path) -> dict[str, Any]:
    fixture = _checkpoint_fixture(tmp_path, _torch_zip())
    inspection = _inspect_checkpoint(fixture)
    return {
        **fixture,
        "checkpoint_inspection": inspection,
        "lease_kwargs": _inspection_kwargs(fixture),
    }


def _acquire(
    fixture: Mapping[str, Any],
) -> tuple[
    SeparationCheckpointDescriptorLease,
    SeparationCheckpointDescriptorLeaseObservation,
]:
    return acquire_separation_checkpoint_descriptor_lease(
        fixture["worker_request"],
        checkpoint_inspection=fixture["checkpoint_inspection"],
        trusted_checkpoint_inspection=fixture["checkpoint_inspection"],
        **fixture["lease_kwargs"],
    )


def test_facade_public_surface_signatures_and_type_ownership_are_exact() -> None:
    assert lease_module.__all__ == _PUBLIC_SURFACE
    assert {
        value.__name__: value.__module__
        for value in (
            SeparationCheckpointDescriptorLease,
            lease_module.SeparationCheckpointDescriptorLeaseError,
            SeparationCheckpointDescriptorLeaseObservation,
            SeparationCheckpointDescriptorLeaseTerminalReceipt,
        )
    } == {
        name: "sunofriend.separation_checkpoint_descriptor_lease"
        for name in (
            "SeparationCheckpointDescriptorLease",
            "SeparationCheckpointDescriptorLeaseError",
            "SeparationCheckpointDescriptorLeaseObservation",
            "SeparationCheckpointDescriptorLeaseTerminalReceipt",
        )
    }
    assert str(
        inspect.signature(acquire_separation_checkpoint_descriptor_lease)
    ) == (
        "(worker_request: 'Mapping[str, Any]', *, "
        "checkpoint_inspection: 'SeparationCheckpointInspection', "
        "trusted_checkpoint_inspection: 'SeparationCheckpointInspection', "
        "trusted_request: 'SeparationCheckpointInspectionRequest', "
        "trusted_preflight: 'Mapping[str, Any]', "
        "trusted_acceptance: 'Mapping[str, Any]', "
        "trusted_separation_request: 'Any', "
        "trusted_runtime_artifact: 'SeparationRuntimeArtifactIdentity') "
        "-> 'tuple[SeparationCheckpointDescriptorLease, "
        "SeparationCheckpointDescriptorLeaseObservation]'"
    )
    assert str(
        inspect.signature(recheck_separation_checkpoint_descriptor_lease)
    ) == (
        "(trusted_lease: 'SeparationCheckpointDescriptorLease') "
        "-> 'SeparationCheckpointDescriptorLeaseObservation'"
    )
    assert str(
        inspect.signature(close_separation_checkpoint_descriptor_lease)
    ) == (
        "(trusted_lease: 'SeparationCheckpointDescriptorLease') "
        "-> 'SeparationCheckpointDescriptorLeaseTerminalReceipt'"
    )
    assert "_reserve_separation_checkpoint_descriptor_fd5" not in (
        lease_module.__all__
    )
    assert "_release_separation_checkpoint_descriptor_fd5" not in (
        lease_module.__all__
    )


def test_observation_and_closed_receipt_match_exact_independent_oracles(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    lease, observation = _acquire(fixture)
    inspection = _plain(fixture["checkpoint_inspection"])
    request = fixture["trusted_request"]
    bindings = {
        "worker_request_sha256": request.request_sha256,
        "preflight_sha256": request.preflight_sha256,
        "acceptance_artifact_sha256": request.acceptance_artifact_sha256,
        "trusted_checkpoint_inspection_sha256": inspection[
            "inspection_sha256"
        ],
        "checkpoint_sha256": inspection["checkpoint"]["sha256"],
        "checkpoint_bytes": inspection["checkpoint"]["bytes"],
        "checkpoint_file_identity_sha256": _canonical_sha256(
            inspection["checkpoint"]["file_identity"]
        ),
        "classification_evidence_sha256": inspection["classification"][
            "classification_evidence_sha256"
        ],
        "archive_evidence_sha256": _canonical_sha256(
            inspection["archive"]
        ),
        "pickle_evidence_sha256": _canonical_sha256(inspection["pickle"]),
    }
    observation_payload = {
        "schema": (
            "sunofriend.separation-checkpoint-descriptor-lease-observation.v1"
        ),
        "lease_id": "private-parent-checkpoint-descriptor-lease-v1",
        "status": "retained_not_loaded",
        "evidence_scope": "private_development",
        "publication_scope": "private_local_contract_evidence",
        "execution_supported": False,
        "execution_permitted": False,
        "selection_permitted": False,
        "bindings": bindings,
        "classification": {
            "container_kind": inspection["classification"]["container_kind"],
            "confidence": inspection["classification"]["confidence"],
            "evidence_equal_to_trusted_inspection": True,
        },
        "descriptor": {
            "retained": True,
            "raw_descriptor_exposed": False,
            "inheritable": False,
            "shared_offset_reset_to_zero": True,
            "ancestor_descriptors_closed": True,
            "owner_pid_recorded_privately": True,
        },
        "limitations": [
            "checkpoint_descriptor_not_handed_to_loader",
            "checkpoint_descriptor_registry_state_is_in_process_convention",
            "checkpoint_immutable_snapshot_not_enforced",
            "checkpoint_in_place_mutation_remains_possible",
            "checkpoint_content_may_change_after_last_remeasurement",
            "lease_observation_is_historical_not_liveness_authority",
            (
                "future_handoff_requires_remeasure_and_install_under_same_"
                "lease_lock"
            ),
            "trusted_parent_pid_convention_not_kernel_enforced",
        ],
        "effects": {
            "checkpoint_descriptor_retained": True,
            "checkpoint_descriptor_closed": False,
            "ancestor_descriptors_closed": True,
            **_FALSE_EFFECTS,
        },
    }
    expected_observation = {
        **observation_payload,
        "observation_sha256": _canonical_sha256(observation_payload),
    }
    assert _plain(observation) == expected_observation

    receipt = close_separation_checkpoint_descriptor_lease(lease)
    receipt_payload = {
        "schema": (
            "sunofriend.separation-checkpoint-descriptor-lease-terminal-"
            "receipt.v1"
        ),
        "lease_id": "private-parent-checkpoint-descriptor-lease-v1",
        "status": "closed",
        "execution_supported": False,
        "execution_permitted": False,
        "selection_permitted": False,
        "bindings": {
            "lease_observation_sha256": expected_observation[
                "observation_sha256"
            ],
            **bindings,
        },
        "integrity": {
            "status": "verified_before_close_attempt",
            "reasons": [],
        },
        "cleanup": {
            "status": "complete",
            "reasons": [],
            "descriptor_close_attempted": True,
            "descriptor_close_call_succeeded": True,
        },
        "limitations": [
            "checkpoint_content_may_change_after_last_remeasurement",
            "descriptor_close_call_success_is_not_post_close_proof",
        ],
        "effects": {
            "checkpoint_descriptor_retained": False,
            "checkpoint_descriptor_close_attempted": True,
            "checkpoint_descriptor_close_call_succeeded": True,
            **_FALSE_EFFECTS,
        },
    }
    assert _plain(receipt) == {
        **receipt_payload,
        "receipt_sha256": _canonical_sha256(receipt_payload),
    }


def test_recheck_and_close_reset_the_owned_descriptor_offset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    lease, observation = _acquire(fixture)
    _known_lease, state = lease_module._known_state(lease)
    descriptor = state.descriptor
    assert descriptor is not None

    os.lseek(descriptor, 37, os.SEEK_SET)
    assert _plain(
        recheck_separation_checkpoint_descriptor_lease(lease)
    ) == _plain(observation)
    assert os.lseek(descriptor, 0, os.SEEK_CUR) == 0

    original_close = lease_module.os.close
    close_observations: list[tuple[int, int, tuple[int, int]]] = []

    def observed_close(value: int) -> None:
        measured = os.fstat(value)
        close_observations.append(
            (
                value,
                os.lseek(value, 0, os.SEEK_CUR),
                (measured.st_dev, measured.st_ino),
            )
        )
        original_close(value)

    os.lseek(descriptor, 19, os.SEEK_SET)
    monkeypatch.setattr(lease_module.os, "close", observed_close)
    assert close_separation_checkpoint_descriptor_lease(lease)[
        "status"
    ] == "closed"
    assert close_observations == [
        (descriptor, 0, state.file_identity[:2])
    ]


@pytest.mark.parametrize(
    ("hook_name", "replacement"),
    [
        ("_hash", lambda _value: "0" * 64),
        ("_file_identity_document", lambda _value: {"device": -1}),
    ],
)
def test_recheck_preserves_private_facade_integrity_hooks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    hook_name: str,
    replacement: Any,
) -> None:
    fixture = _fixture(tmp_path)
    lease, _observation = _acquire(fixture)
    monkeypatch.setattr(lease_module, hook_name, replacement)

    with pytest.raises(
        lease_module.SeparationCheckpointDescriptorLeaseError
    ) as captured:
        recheck_separation_checkpoint_descriptor_lease(lease)

    receipt = captured.value.receipt
    assert receipt["status"] == "integrity_failed"
    assert receipt["integrity"] == {
        "status": "failed",
        "reasons": ("lease_authority_binding_invalid",),
    }
    assert close_separation_checkpoint_descriptor_lease(lease) == receipt


def test_finalizer_does_not_close_a_reused_foreign_descriptor(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    decoy = tmp_path / "decoy.bin"
    decoy.write_bytes(b"not the checkpoint")
    lease, _observation = _acquire(fixture)
    _known_lease, state = lease_module._known_state(lease)
    descriptor = state.descriptor
    assert descriptor is not None
    expected_devino = state.file_identity[:2]
    lease_reference = weakref.ref(lease)
    del _known_lease

    os.close(descriptor)
    opened: list[int] = []
    for _attempt in range(64):
        reused = os.open(decoy, os.O_RDONLY)
        opened.append(reused)
        if reused == descriptor:
            break
    assert reused == descriptor
    observed = os.fstat(reused)
    assert (observed.st_dev, observed.st_ino) != expected_devino

    del lease
    for _attempt in range(3):
        gc.collect()
        if lease_reference() is None:
            break
    try:
        assert lease_reference() is None
        os.fstat(reused)
    finally:
        for opened_descriptor in opened:
            os.close(opened_descriptor)
