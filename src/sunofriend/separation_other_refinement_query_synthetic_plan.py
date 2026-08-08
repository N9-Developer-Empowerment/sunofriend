"""No-effects plan for the first Banquet adapter forward check.

The document is intentionally executable-data-free: building it imports no
model runtime, opens no checkpoint or audio, and performs no inference.  A
later runner must validate this exact plan before it can use generated tensors.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .separation_other_refinement_query_forward_contract import (
    build_query_forward_contract,
)
from .separation_other_refinement_query_load_contract import (
    EXPECTED_CHECKPOINTS,
    QUERY_BANDIT_SOURCE_REVISION,
    QUERY_PROFILE_ID,
)
from .separation_other_refinement_query_synthetic_report_contract import (
    MODEL_LOAD_REPORT_SHA256,
    QUERY_SYNTHETIC_PLAN_SCHEMA,
    build_query_synthetic_report_contract,
)


QUERY_SYNTHETIC_PLAN_STATUS = "blocked_pending_explicit_synthetic_inference_approval"


def query_synthetic_plan_sha256(value: dict[str, Any]) -> str:
    """Return the canonical plan digest with its self-hash omitted."""

    payload = {key: item for key, item in value.items() if key != "document_sha256"}
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def build_query_synthetic_plan() -> dict[str, Any]:
    """Build the immutable plan without performing any approved action."""

    forward_contract = build_query_forward_contract()
    report_contract = build_query_synthetic_report_contract()
    plan: dict[str, Any] = {
        "schema": QUERY_SYNTHETIC_PLAN_SCHEMA,
        "document_sha256": "",
        "status": QUERY_SYNTHETIC_PLAN_STATUS,
        "checked_on": "2026-08-08",
        "scope_id": "other-query-refinement-v1",
        "profile_id": QUERY_PROFILE_ID,
        "release_tier": "studio_challenger",
        "registered": False,
        "executable": False,
        "evidence_binding": {
            "source_revision": QUERY_BANDIT_SOURCE_REVISION,
            "model_load_report_sha256": MODEL_LOAD_REPORT_SHA256,
            "checkpoints": EXPECTED_CHECKPOINTS,
            "forward_contract_schema": forward_contract["schema"],
            "forward_contract_document_sha256": forward_contract[
                "document_sha256"
            ],
            "report_contract_schema": report_contract["schema"],
            "report_contract_document_sha256": report_contract[
                "document_sha256"
            ],
        },
        "implementation_boundary": {
            "load_adapter_has_forward_method": False,
            "implemented_modules": {
                "evidence_contract": (
                    "separation_other_refinement_query_load_contract.py"
                ),
                "state_compatible_topology": (
                    "separation_other_refinement_query_model_adapter.py"
                ),
                "restricted_checkpoint_loading": (
                    "separation_other_refinement_query_model_loading.py"
                ),
                "source_bound_forward_contract": (
                    "separation_other_refinement_query_forward_contract.py"
                ),
                "reusable_effects_guard": (
                    "separation_other_refinement_query_execution_guard.py"
                ),
                "synthetic_report_contract": (
                    "separation_other_refinement_query_synthetic_report_contract.py"
                ),
                "synthetic_report_validation": (
                    "separation_other_refinement_query_synthetic_report_validation.py"
                ),
                "synthetic_report_receipt": (
                    "separation_other_refinement_query_synthetic_report_receipt.py"
                ),
                "synthetic_report_compatibility_facade": (
                    "separation_other_refinement_query_synthetic_report.py"
                ),
                "synthetic_report_receipt_cli": (
                    "record-separation-other-refinement-query-synthetic.py"
                ),
                "guarded_evidence_cli": (
                    "verify-separation-other-refinement-query-model-load.py"
                ),
            },
            "next_implementation_must_separate": [
                "forward_math_implementation",
                "synthetic_forward_runner",
            ],
            "upstream_cli_allowed": False,
            "upstream_download_or_checkpoint_loader_allowed": False,
            "public_profile_or_registry_change": False,
        },
        "proposed_single_run": {
            "configuration_count": 1,
            "remediation_cycle_limit": 1,
            "device": "cpu",
            "torch_context": "torch.inference_mode()",
            "random_seed": report_contract["generated_inputs"]["random_seed"],
            "network_denial": "operating_system_and_python_guards",
            "checkpoint_load_contract": (
                "reload the two exact local checkpoints using the already-verified "
                "weights-only CPU contract"
            ),
            "input_origin": report_contract["generated_inputs"]["origin"],
            "mixture": report_contract["generated_inputs"]["mixture"],
            "query": report_contract["generated_inputs"]["query"],
            "audio_files_read": 0,
            "audio_files_written": 0,
            "only_persisted_output": "JSON objective report",
        },
        "objective_acceptance": {
            "output_is_stereo_float32_on_input_clock": True,
            "output_shape_is_exactly": [1, 2, 88_200],
            "all_output_samples_are_finite": True,
            "target_and_residual_peaks_are_recorded": True,
            "residual_definition": "generated_mixture - requested_target",
            "target_plus_residual_reconstructs_generated_mixture": True,
            "maximum_in_memory_reconstruction_error": report_contract["ceilings"][
                "maximum_reconstruction_error"
            ],
            "network_attempts": 0,
            "unapproved_checkpoint_open_attempts": 0,
            "audio_open_attempts": 0,
            "timeout_seconds": report_contract["ceilings"][
                "maximum_elapsed_seconds"
            ],
            "peak_resident_set_bytes_ceiling": report_contract["ceilings"][
                "maximum_peak_resident_set_bytes"
            ],
            "musical_usefulness_gate": False,
        },
        "stop_conditions": [
            "checkpoint or model identity differs",
            "network access is attempted",
            "an audio file is opened",
            "output clock or shape differs",
            "a non-finite sample is produced",
            "reconstruction accounting fails",
            "the 180-second or 12-GiB ceiling is exceeded",
        ],
        "next_approval": {
            "required": True,
            "exact_text": (
                "I approve one network-denied, CPU-only synthetic Banquet forward "
                "run, including reloading the two exact verified local checkpoints, "
                "using generated in-memory tensors only (2-second mixture, 10-second "
                "query, seed 0), with no private audio, no persisted audio, no public "
                "activation, no source selection and no MIDI."
            ),
            "authorizes_inference_runs": 1,
            "authorizes_exact_checkpoint_reloads": 2,
            "authorizes_generated_tensor_processing": True,
            "authorizes_private_audio": False,
            "authorizes_persisted_audio": False,
            "authorizes_song_processing": False,
            "authorizes_public_activation": False,
            "authorizes_source_selection": False,
            "authorizes_midi": False,
        },
        "effects": {
            "network_used_by_plan": False,
            "checkpoint_opened_by_plan": False,
            "model_constructed_by_plan": False,
            "inference_runs": 0,
            "generated_tensors_created": False,
            "audio_reads": 0,
            "audio_writes": 0,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
        },
    }
    plan["document_sha256"] = query_synthetic_plan_sha256(plan)
    return plan


def validate_query_synthetic_plan(value: dict[str, Any]) -> dict[str, Any]:
    """Reject mutation or accidental expansion of the proposed authority."""

    expected = build_query_synthetic_plan()
    if value != expected:
        raise ValueError("query synthetic plan differs from the reviewed plan")
    if value["document_sha256"] != query_synthetic_plan_sha256(value):
        raise ValueError("query synthetic plan document hash differs")
    return value


__all__ = [
    "MODEL_LOAD_REPORT_SHA256",
    "QUERY_SYNTHETIC_PLAN_SCHEMA",
    "QUERY_SYNTHETIC_PLAN_STATUS",
    "build_query_synthetic_plan",
    "query_synthetic_plan_sha256",
    "validate_query_synthetic_plan",
]
