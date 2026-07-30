"""Parent-only quarantine verification for fake execution Result V2.

This verifier is intentionally distinct from the historical fake-worker V1
wrapper.  It accepts only the execution-era V3 plan and complete Result V2,
then reuses the audited descriptor-level file and PCM24 checks.  It creates no
files, starts no process and grants no publication or selection authority.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

from ._separation_checkpoint_canonical import (
    canonical_sha256 as _hash,
    deep_freeze as _freeze,
    plain as _plain,
)
from ._separation_fake_execution_records import (
    _SeparationFakeLaunchPlanV3Record,
    _SeparationFakeWorkerResultV2Record,
    _validate_prepared_separation_fake_launch_plan_v3_record_shape,
    _validate_separation_fake_worker_result_v2_record_shape,
)
from ._separation_fake_launch_v2_records import (
    _SeparationFakeLaunchPlanV2Record,
)
from ._separation_fake_transport_records import (
    _SeparationFakeLaunchPlanRecord,
    _SeparationFakeWorkerRequestRecord,
)
from ._separation_fake_worker_protocol import (
    _file_identity,
    _identity_sha256,
    _verified_quarantine_directory,
    _verify_one_output,
)


__all__: tuple[str, ...] = ()

_QUARANTINE_V2_SCHEMA = (
    "sunofriend.separation-fake-execution-quarantine-verification.v2"
)
_QUARANTINE_V2_POLICY_ID = "parent-descriptor-quarantine-observation-v2"


def _verify_fake_execution_quarantine_v2(
    *,
    fake_worker_request: _SeparationFakeWorkerRequestRecord,
    fake_launch_plan_v1: _SeparationFakeLaunchPlanRecord,
    blocked_fake_launch_plan_v2: _SeparationFakeLaunchPlanV2Record,
    fake_launch_plan_v3: _SeparationFakeLaunchPlanV3Record,
    fake_worker_result_v2: _SeparationFakeWorkerResultV2Record,
    quarantine_directory_descriptor: int,
    readable_descriptors: Mapping[str, int],
) -> Mapping[str, Any]:
    """Verify an exact Result V2 tree through already-open descriptors."""

    plan = _validate_prepared_separation_fake_launch_plan_v3_record_shape(
        fake_launch_plan_v3,
        fake_worker_request=fake_worker_request,
        fake_launch_plan_v1=fake_launch_plan_v1,
        blocked_fake_launch_plan_v2=blocked_fake_launch_plan_v2,
    )
    result = _validate_separation_fake_worker_result_v2_record_shape(
        fake_worker_result_v2,
        fake_launch_plan_v3=plan,
    )
    slots = list(plan["output_slots"])
    claims = list(result["outputs"])
    slot_ids = [item["slot_id"] for item in slots]
    if type(readable_descriptors) is not dict:
        raise ValueError("V2 quarantine descriptors must be an exact dictionary")
    descriptors_by_slot = dict(readable_descriptors)
    if set(descriptors_by_slot) != set(slot_ids):
        raise ValueError(
            "V2 quarantine descriptors must cover every exact output slot"
        )
    descriptors = list(descriptors_by_slot.values())
    if (
        any(type(item) is not int or item < 0 for item in descriptors)
        or type(quarantine_directory_descriptor) is not int
        or quarantine_directory_descriptor < 0
        or quarantine_directory_descriptor in descriptors
        or len(set(descriptors)) != len(descriptors)
    ):
        raise ValueError(
            "V2 quarantine descriptors must be distinct non-negative integers"
        )

    directory_before = _verified_quarantine_directory(
        quarantine_directory_descriptor
    )
    expected_names = {f"{item['slot_id']}.wav" for item in slots}
    try:
        observed_names = sorted(os.listdir(quarantine_directory_descriptor))
    except OSError as exc:
        raise ValueError("V2 quarantine directory could not be listed") from exc
    if observed_names != sorted(expected_names):
        raise ValueError("V2 quarantine tree does not match exact output slots")

    claims_by_slot = {item["slot_id"]: item for item in claims}
    verified: list[dict[str, Any]] = []
    observed_file_objects: set[tuple[int, int]] = set()
    total_bytes = 0
    for slot in slots:
        slot_id = slot["slot_id"]
        claim = claims_by_slot[slot_id]
        if any(
            claim[key] != slot[key]
            for key in ("slot_id", "role", "artifact_kind")
        ):
            raise ValueError("Result V2 output does not match its exact slot")
        evidence = _verify_one_output(
            descriptors_by_slot[slot_id],
            claim,
            directory_descriptor=quarantine_directory_descriptor,
            entry_name=f"{slot_id}.wav",
            maximum_bytes=slot["maximum_bytes"],
        )
        file_object = tuple(evidence.pop("_file_object_identity"))
        if file_object in observed_file_objects:
            raise ValueError("V2 quarantine slots must use distinct file objects")
        observed_file_objects.add(file_object)
        total_bytes += evidence["bytes"]
        verified.append(evidence)

    directory_after = _verified_quarantine_directory(
        quarantine_directory_descriptor
    )
    if _file_identity(directory_before) != _file_identity(directory_after):
        raise ValueError("V2 quarantine directory changed during verification")
    parent_outputs = [
        {
            key: _plain(claim[key])
            for key in (
                "role",
                "slot_id",
                "artifact_kind",
                "sha256",
                "bytes",
                "geometry",
            )
        }
        for claim in claims
    ]
    quarantine_identity_sha256 = _hash(
        {
            "directory_identity_sha256": _identity_sha256(directory_after),
            "fake_launch_plan_v3_sha256": plan["plan_sha256"],
            "fake_worker_result_v2_sha256": result["result_sha256"],
        }
    )
    observed_entry_set_sha256 = _hash(
        [
            {
                "entry_name": f"{item['slot_id']}.wav",
                "file_identity_sha256": item["file_identity_sha256"],
                "sha256": item["sha256"],
                "bytes": item["bytes"],
            }
            for item in verified
        ]
    )
    payload = {
        "schema": _QUARANTINE_V2_SCHEMA,
        "policy_id": _QUARANTINE_V2_POLICY_ID,
        "status": "verified",
        "evidence_scope": "private_parent_observation",
        "run_nonce": plan["run_nonce"],
        "fake_launch_plan_v3_sha256": plan["plan_sha256"],
        "fake_worker_result_v2_sha256": result["result_sha256"],
        "publication_permitted": False,
        "selection_permitted": False,
        "acceptance_eligible": False,
        "promotion_eligible": False,
        "worker_created_output_files": False,
        "output_files_observed_by_parent": True,
        "ordinary_file_immutable_backing_proven": False,
        "quarantine_identity_sha256": quarantine_identity_sha256,
        "observed_entry_set_sha256": observed_entry_set_sha256,
        "output_count": len(verified),
        "total_bytes": total_bytes,
        "outputs": verified,
        "parent_outputs": parent_outputs,
        "effects": {
            "filesystem_accessed": True,
            "files_created": False,
            "files_modified": False,
            "process_started": False,
            "checkpoint_accessed": False,
            "model_imported": False,
            "audio_read": False,
            "network_used": False,
            "publication_permitted": False,
            "selection_permitted": False,
        },
        "limitations": [
            "verification_is_one_parent_observation",
            "result_v2_is_worker_report_not_execution_or_provenance_evidence",
            "ordinary_files_can_change_after_verification",
            "fresh_quarantine_creation_is_not_proven_by_this_verifier",
            "parent_materializer_must_separately_prove_exclusive_creation",
            "verification_does_not_authorize_publication_or_selection",
        ],
    }
    return _freeze(
        {
            **payload,
            "verification_sha256": _hash(payload),
        }
    )
