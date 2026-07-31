"""Pure safety-contract plan for the blocked private BS-RoFormer candidate.

The candidate reuses Sunofriend's existing parent-bound checkpoint inspector
and worker request/result schemas.  This module only describes the intended
binding.  It opens no file, imports no model runtime and starts no process.
"""

from __future__ import annotations

from typing import Any

from ._separation_roformer_source import (
    SOURCE_MANIFEST,
    SOURCE_MANIFEST_SHA256,
    SOURCE_REVISION,
)
from ._separation_roformer_worker_protocol import (
    ROFORMER_WORKER_MAXIMUM_CASES,
    ROFORMER_WORKER_MAXIMUM_SECONDS,
    ROFORMER_WORKER_OUTPUT_ALLOWLIST,
    ROFORMER_WORKER_PROTOCOL_SCHEMA,
    ROFORMER_WORKER_ROLES,
)
from .separation_checkpoint_inspection import (
    CHECKPOINT_STATIC_INSPECTION_EXECUTION_SUPPORTED,
    MAX_CHECKPOINT_BYTES,
    MAX_PICKLE_BYTES,
    MAX_PICKLE_GLOBALS,
    MAX_PICKLE_OPCODES,
    MAX_ZIP_MEMBERS,
    MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES,
    SEPARATION_CHECKPOINT_INSPECTION_ID,
    SEPARATION_CHECKPOINT_INSPECTION_SCHEMA,
)
from .separation_worker_contract import (
    SEPARATION_WORKER_ISOLATION_POLICY,
    SEPARATION_WORKER_REQUEST_SCHEMA,
    SEPARATION_WORKER_RESULT_SCHEMA,
)


ROFORMER_CONTRACT_PLAN_SCHEMA = "sunofriend.private-roformer-safety-contract-plan.v1"
ROFORMER_CONTRACT_PLAN_ID = "private-bs-roformer-four-stem-contract-v1"
ROFORMER_ADMISSION_SCHEMA = "sunofriend.private-roformer-admission.v1"
ROFORMER_ADMISSION_POLICY = "private-bs-roformer-code-runtime-admission-v1"


def _build_private_roformer_contract_plan(*, checkpoint_bytes: int) -> dict[str, Any]:
    """Return the non-authorising contract for one future excerpt worker."""

    return {
        "schema": ROFORMER_CONTRACT_PLAN_SCHEMA,
        "contract_id": ROFORMER_CONTRACT_PLAN_ID,
        "status": "defined_not_implemented",
        "read_only": True,
        "source_boundary": {
            "implementation": (
                "sunofriend._separation_roformer_source."
                "_verify_private_roformer_source_tree"
            ),
            "revision": SOURCE_REVISION,
            "manifest": {
                "path": SOURCE_MANIFEST,
                "sha256": SOURCE_MANIFEST_SHA256,
            },
            "fixed_files": 3,
            "package_initializer_permitted": False,
            "model_import_permitted_by_verification": False,
            "verified_checkout_present": False,
        },
        "code_runtime_admission": {
            "implementation": (
                "sunofriend._separation_roformer_admission."
                "_build_private_roformer_admission"
            ),
            "schema": ROFORMER_ADMISSION_SCHEMA,
            "policy": ROFORMER_ADMISSION_POLICY,
            "path_free": True,
            "implemented": True,
            "applied_to_durable_runtime": False,
            "authorizes_installation": False,
            "authorizes_checkpoint_access": False,
            "authorizes_execution": False,
        },
        "checkpoint_inspection": {
            "implementation": (
                "sunofriend.separation_checkpoint_inspection."
                "inspect_separation_checkpoint"
            ),
            "schema": SEPARATION_CHECKPOINT_INSPECTION_SCHEMA,
            "inspection_id": SEPARATION_CHECKPOINT_INSPECTION_ID,
            "declared_format": "torch-state-dict",
            "published_checkpoint_within_byte_limit": (
                0 < checkpoint_bytes <= MAX_CHECKPOINT_BYTES
            ),
            "limits": {
                "checkpoint_bytes": MAX_CHECKPOINT_BYTES,
                "zip_members": MAX_ZIP_MEMBERS,
                "zip_total_uncompressed_bytes": (MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES),
                "pickle_bytes": MAX_PICKLE_BYTES,
                "pickle_opcodes": MAX_PICKLE_OPCODES,
                "pickle_globals": MAX_PICKLE_GLOBALS,
            },
            "required_evidence": [
                "exact parent-issued worker request",
                "non-inheritable descriptor-pinned checkpoint identity",
                "full observed SHA-256 and byte count",
                "bounded stored-only Torch ZIP inventory",
                "pickle opcode and global inventory without deserialization",
                "candidate-specific profile registered only after observation",
            ],
            "applied_to_candidate": False,
            "checkpoint_loaded": False,
            "checkpoint_deserialized": False,
            "authorizes_loading": False,
            "authorizes_execution": False,
            "execution_supported": (CHECKPOINT_STATIC_INSPECTION_EXECUTION_SUPPORTED),
        },
        "worker": {
            "protocol_implementation": (
                "sunofriend._separation_roformer_worker_protocol."
                "_build_private_roformer_worker_protocol"
            ),
            "protocol_schema": ROFORMER_WORKER_PROTOCOL_SCHEMA,
            "request_schema": SEPARATION_WORKER_REQUEST_SCHEMA,
            "result_schema": SEPARATION_WORKER_RESULT_SCHEMA,
            "isolation_policy": SEPARATION_WORKER_ISOLATION_POLICY,
            "runtime_environment": "fresh .venv-roformer-private",
            "source": {
                "kind": "canonical PCM24 WAV excerpt",
                "sample_rate": 44_100,
                "channels": 2,
                "maximum_seconds": ROFORMER_WORKER_MAXIMUM_SECONDS,
                "maximum_cases": ROFORMER_WORKER_MAXIMUM_CASES,
                "read_only": True,
            },
            "roles": list(ROFORMER_WORKER_ROLES),
            "output_allowlist": list(ROFORMER_WORKER_OUTPUT_ALLOWLIST),
            "output_geometry": {
                "format": "PCM24 WAV",
                "sample_rate": 44_100,
                "channels": 2,
                "exact_source_frame_horizon_required": True,
            },
            "controls": {
                "seed": 0,
                "network_denied_and_observed": True,
                "child_processes_denied": True,
                "input_and_checkpoint_read_only": True,
                "fresh_private_quarantine_required": True,
                "parent_verifies_every_output_hash_and_geometry": True,
                "publication_permitted": False,
                "automatic_selection_permitted": False,
            },
            "protocol_implemented": True,
            "executable_adapter_implemented": False,
            "execution_permitted": False,
        },
        "readiness": {
            "exact_source_manifest_defined": True,
            "source_tree_verified": False,
            "code_runtime_admission_implemented": True,
            "code_runtime_admission_applied": False,
            "checkpoint_inspection_contract_defined": True,
            "worker_request_result_contract_defined": True,
            "roformer_worker_protocol_implemented": True,
            "candidate_static_inspection_completed": False,
            "worker_implemented": False,
            "private_evaluation_eligible": False,
        },
        "effects": {
            "filesystem_accessed": False,
            "filesystem_written": False,
            "network_used": False,
            "package_installed": False,
            "checkpoint_downloaded": False,
            "checkpoint_opened": False,
            "checkpoint_deserialized": False,
            "model_imported": False,
            "process_started": False,
            "product_route_changed": False,
        },
    }
