"""Read-only plan for a query-conditioned grouped-other challenger.

The plan deliberately downloads, installs and executes nothing.  It records
the exact public evidence that can be inspected before asking for a capped
checkpoint-evidence download or any later runtime approval.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


QUERY_CHALLENGER_PLAN_SCHEMA = "sunofriend.other-refinement-query-challenger-plan.v1"
QUERY_CHALLENGER_SCOPE_ID = "other-query-refinement-v1"
QUERY_CHALLENGER_PROPOSED_PROFILE_ID = "query-bandit-ev-pre-aug-v1"


def _document_sha256(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "document_sha256"}
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_query_challenger_plan() -> dict[str, Any]:
    """Return the deterministic no-effects candidate plan."""

    plan: dict[str, Any] = {
        "schema": QUERY_CHALLENGER_PLAN_SCHEMA,
        "document_sha256": "",
        "status": "blocked_pending_runtime_qualification",
        "checked_on": "2026-08-07",
        "scope_id": QUERY_CHALLENGER_SCOPE_ID,
        "proposed_profile_id": QUERY_CHALLENGER_PROPOSED_PROFILE_ID,
        "release_tier": "studio_challenger",
        "registered": False,
        "executable": False,
        "candidate": {
            "name": "Banquet query-conditioned music source separation",
            "source_repository": "https://github.com/kwatcharasupat/query-bandit",
            "source_revision": "79ed5bb75e5c3a40cd319d9d990cee913fc65c26",
            "source_license": "MIT",
            "checkpoint_record": "https://doi.org/10.5281/zenodo.13694558",
            "checkpoint_record_id": 13694558,
            "checkpoint_file": "ev-pre-aug.ckpt",
            "checkpoint_bytes": 645_470_187,
            "checkpoint_md5": "4dfb91d6d27c2dfd4992a15070915541",
            "checkpoint_sha256": (
                "657295888781e62ef50593002720d2edb3858b9e5bbfabf0c54f715a0da4b9e2"
            ),
            "checkpoint_license": "CC-BY-NC-SA-4.0",
            "training_dataset": "MoisesDB",
            "training_dataset_license": "CC-BY-NC-SA-4.0",
            "model_sample_rate_hz": 44_100,
            "query_duration_seconds": 10.0,
            "reported_trainable_parameters": 24_900_000,
            "upstream_cpu_flag_available": True,
            "apple_silicon_runtime_verified": False,
            "pytorch_lightning_pickle_checkpoint": True,
            "checkpoint_evidence": {
                "schema": ("sunofriend.other-refinement-query-checkpoint-evidence.v1"),
                "evidence_sha256": (
                    "4730e077ec4b7531d454ec3cb6f153a564342fca58e12f4719a44aafb7dd5381"
                ),
                "network_denied_static_inspection": True,
                "archive_member_count": 3_491,
                "data_pickle_bytes": 452_701,
                "pickle_protocol": 2,
                "pickle_opcode_count": 120_149,
                "pickle_globals": [
                    "collections OrderedDict",
                    "torch DoubleStorage",
                    "torch FloatStorage",
                    "torch._utils _rebuild_tensor_v2",
                ],
                "application_model_globals_observed": False,
                "checkpoint_deserialized": False,
                "loading_safety_established": False,
                "authorizes_loading": False,
            },
        },
        "target_contract": {
            "parent_scope_id": "core-four-stems-v1",
            "parent_profile_id": "scnet-large-musdb-release-v1",
            "parent_role": "other",
            "one_target_per_run": True,
            "query_audio_required": True,
            "query_frozen_before_inference": True,
            "provider_estimates_allowed_as_queries": False,
            "targets": {
                "guitar": {
                    "label": "Guitar family",
                    "training_classes": [
                        "acoustic_guitar",
                        "clean_electric_guitar",
                        "distorted_electric_guitar",
                    ],
                },
                "keyboard_synth": {
                    "label": "Keyboard and synthesizer family",
                    "training_classes": [
                        "electric_piano",
                        "organ_electric_organ",
                        "synth_pad",
                        "synth_lead",
                    ],
                    "acoustic_piano_is_required": False,
                },
            },
            "persisted_outputs": ["requested_target", "exact_residual"],
            "reconstruction_equation": "parent_other = requested_target + residual",
            "reconstruction_is_separation_accuracy": False,
            "automatic_query_or_target_selection": False,
            "automatic_source_or_midi_activation": False,
        },
        "bounded_evaluation": {
            "configuration_count": 1,
            "remediation_cycle_count": 1,
            "fixed_query_count": 2,
            "query_families": ["guitar", "keyboard_synth"],
            "case_count": 10,
            "case_duration_seconds": 15,
            "guitar_windows": "reuse only reviewed instrument-present windows",
            "keyboard_synth_windows": (
                "freeze new broad keyboard, organ and synth windows before inference"
            ),
            "provider_stems_are_comparison_cues_not_ground_truth": True,
            "provider_stems_are_not_query_inputs": True,
            "mixed_or_negative_feedback_blocks_studio_access": False,
            "poor_results_trigger_unbounded_query_search": False,
            "midi_use_requires_later_explicit_selection": True,
        },
        "objective_gates": [
            "exact source, checkpoint and runtime identities",
            "checkpoint SHA-256 and safe weights-only static inspection",
            "all dependencies hash-locked",
            "network-denied model construction and inference",
            "finite stereo 44.1 kHz output on the parent clock",
            "requested target plus persisted residual reconstruct within two PCM24 LSBs",
            "no crash or OOM inside the declared resource ceiling",
            "no source mutation, upload, automatic selection or MIDI activation",
        ],
        "licence_boundary": {
            "local_noncommercial_research_only": True,
            "hosted_conversion_service": False,
            "checkpoint_redistribution": False,
            "commercial_default": False,
            "reason": (
                "The published checkpoint and training dataset declare "
                "CC-BY-NC-SA-4.0; user approval cannot remove those terms."
            ),
        },
        "approvals": {
            "public_source_metadata_inspection": True,
            "checkpoint_evidence_download": True,
            "network_denied_weights_only_static_inspection": True,
            "dependency_installation": False,
            "checkpoint_loading": False,
            "model_inference": False,
            "private_audio_processing": False,
            "public_execution": False,
            "source_activation": False,
            "midi_activation": False,
        },
        "blockers": [
            "Dependency identities and hashes have not been reviewed or approved for installation.",
            "Static opcode evidence does not establish restricted-loader compatibility or loading safety.",
            "Apple-silicon CPU compatibility, runtime pins and resources are unverified.",
            "Two copyright-safe, song-disjoint 10-second query exemplars are not yet frozen.",
            "No keyboard/synth-aware ten-case evaluation definition is frozen.",
        ],
        "completed_approval_phrase": (
            "I approve a capped evidence-only download of Banquet ev-pre-aug.ckpt "
            "up to 700 MiB, acknowledge its CC-BY-NC-SA-4.0 noncommercial boundary, "
            "and approve network-denied weights-only static inspection. This does not "
            "approve dependency installation, model loading, inference, song processing, "
            "public activation, source selection or MIDI."
        ),
        "effects": {
            "network_used_by_plan": False,
            "checkpoint_downloaded": False,
            "dependency_installed": False,
            "model_loaded": False,
            "model_executed": False,
            "audio_read": False,
            "audio_created": False,
            "candidate_selected": False,
            "source_graph_mutated": False,
            "midi_created": False,
        },
    }
    plan["document_sha256"] = _document_sha256(plan)
    return plan


def validate_query_challenger_plan(value: dict[str, Any]) -> dict[str, Any]:
    """Reject plan mutation or accidental capability expansion."""

    expected = build_query_challenger_plan()
    if value != expected:
        raise ValueError("query challenger plan differs from the reviewed plan")
    if value["document_sha256"] != _document_sha256(value):
        raise ValueError("query challenger plan document hash differs")
    return value
