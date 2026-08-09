"""Pure, no-effects plan for one Mega-53 generated-tensor forward.

Building this document performs no package import, checkpoint load, tensor
allocation or model call.  It exists so the exact alignment repair and the
single-use authority can be reviewed before any inference is permitted.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from .separation_other_refinement_next_model_load_contract import (
    CHECKPOINT,
    CONFIG,
    PROFILE_ID,
    SOURCE,
)


SYNTHETIC_PLAN_SCHEMA = "sunofriend.mega53-generated-tensor-forward-plan.v1"
SYNTHETIC_PLAN_STATUS = "awaiting_explicit_generated_tensor_forward_approval"
MODEL_LOAD_REPORT_SHA256 = (
    "798b5250eacf18d3f6193fde9d5c613ee68520490aed663395313a47eea4d666"
)
PUBLISHED_CHUNK_SIZE = 882_000
STFT_HOP_LENGTH = 512
NUM_OVERLAP = 2
ALIGNMENT_QUANTUM = STFT_HOP_LENGTH * NUM_OVERLAP
ALIGNED_CHUNK_SIZE = 881_664
ALIGNED_STEP_SIZE = 440_832
SAMPLE_RATE_HZ = 44_100
SYNTH_ROLE_INDEX = 38
MAXIMUM_ELAPSED_SECONDS = 900
MAXIMUM_PEAK_MLX_MEMORY_BYTES = 30 * 1024**3
MAXIMUM_RECONSTRUCTION_ERROR = 2**-20

NATIVE_ROLES = (
    "accordion",
    "acoustic-guitar",
    "back-vocal",
    "banjo",
    "bass",
    "bassoon",
    "bells",
    "bowed_strings",
    "brass",
    "cello",
    "clarinet",
    "congas",
    "digital-piano",
    "dobro",
    "double-bass",
    "drums",
    "electric-guitar",
    "flute",
    "french-horn",
    "glockenspiel",
    "guitar",
    "harmonica",
    "harp",
    "harpsichord",
    "hh",
    "keys",
    "kick",
    "lead-vocal",
    "mandolin",
    "marimba",
    "oboe",
    "organ",
    "percussion",
    "piano",
    "saxophone",
    "sitar",
    "snare",
    "strings",
    "synth",
    "tambourine",
    "timpani",
    "toms",
    "triangle",
    "trombone",
    "trumpet",
    "tuba",
    "ukulele",
    "viola",
    "violin",
    "vocal",
    "wind",
    "wind-chimes",
    "woodwind",
)


def synthetic_plan_sha256(value: dict[str, Any]) -> str:
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


def build_next_synthetic_plan() -> dict[str, Any]:
    """Return the immutable plan without exercising any approved capability."""

    plan: dict[str, Any] = {
        "schema": SYNTHETIC_PLAN_SCHEMA,
        "document_sha256": "",
        "status": SYNTHETIC_PLAN_STATUS,
        "checked_on": "2026-08-09",
        "scope_id": "other-refinement-next-v1",
        "profile_id": PROFILE_ID,
        "registered": False,
        "executable": False,
        "evidence_binding": {
            "checkpoint": CHECKPOINT,
            "config": CONFIG,
            "source": SOURCE,
            "model_load_report_sha256": MODEL_LOAD_REPORT_SHA256,
            "native_roles": list(NATIVE_ROLES),
            "native_role_count": len(NATIVE_ROLES),
            "target_role": "synth",
            "target_role_zero_based_index": SYNTH_ROLE_INDEX,
        },
        "alignment_contract": {
            "published_chunk_size": PUBLISHED_CHUNK_SIZE,
            "published_step_size": PUBLISHED_CHUNK_SIZE // NUM_OVERLAP,
            "stft_hop_length": STFT_HOP_LENGTH,
            "num_overlap": NUM_OVERLAP,
            "published_chunk_is_valid": False,
            "published_step_is_valid": False,
            "rule": (
                "largest sample count not exceeding the published chunk that is "
                "divisible by stft_hop_length * num_overlap"
            ),
            "alignment_quantum": ALIGNMENT_QUANTUM,
            "aligned_chunk_size": ALIGNED_CHUNK_SIZE,
            "aligned_step_size": ALIGNED_STEP_SIZE,
            "aligned_chunk_hops": ALIGNED_CHUNK_SIZE // STFT_HOP_LENGTH,
            "aligned_step_hops": ALIGNED_STEP_SIZE // STFT_HOP_LENGTH,
            "adjustment_samples": ALIGNED_CHUNK_SIZE - PUBLISHED_CHUNK_SIZE,
            "adjustment_seconds": (
                ALIGNED_CHUNK_SIZE - PUBLISHED_CHUNK_SIZE
            ) / SAMPLE_RATE_HZ,
            "generated_input_padding_samples": 0,
            "generated_output_crop_samples": 0,
            "verified_source_or_artifact_mutated": False,
        },
        "proposed_single_run": {
            "configuration_count": 1,
            "inference_attempt_limit": 1,
            "automatic_retry": False,
            "device": "mlx_apple_silicon",
            "machine": "Apple M3 Max with 36 GB unified memory",
            "network_denial": "operating_system_and_python_guards",
            "checkpoint_reload_count": 1,
            "model_construction_count": 1,
            "forward_call_count": 1,
            "input": {
                "origin": "generated_in_memory_only",
                "generator": "six fixed-frequency stereo sinusoids with seed-0 phases",
                "random_seed": 0,
                "shape": [1, 2, ALIGNED_CHUNK_SIZE],
                "dtype": "float32",
                "sample_rate_hz": SAMPLE_RATE_HZ,
                "duration_seconds": ALIGNED_CHUNK_SIZE / SAMPLE_RATE_HZ,
            },
            "expected_output": {
                "shape": [1, len(NATIVE_ROLES), 2, ALIGNED_CHUNK_SIZE],
                "dtype": "float32",
                "target_projection_shape": [1, 2, ALIGNED_CHUNK_SIZE],
                "target_role": "synth",
            },
            "audio_files_read": 0,
            "audio_files_written": 0,
            "persisted_audio": False,
            "only_persisted_output": "JSON objective report",
        },
        "objective_acceptance": {
            "exact_model_identity": True,
            "exact_role_order": True,
            "exact_output_shape_and_dtype": True,
            "all_output_samples_finite": True,
            "synth_and_residual_peaks_recorded": True,
            "residual_definition": "generated_input - native_synth_estimate",
            "maximum_in_memory_reconstruction_error": MAXIMUM_RECONSTRUCTION_ERROR,
            "maximum_elapsed_seconds": MAXIMUM_ELAPSED_SECONDS,
            "maximum_peak_mlx_memory_bytes": MAXIMUM_PEAK_MLX_MEMORY_BYTES,
            "network_attempts": 0,
            "audio_open_attempts": 0,
            "musical_usefulness_gate": False,
        },
        "failure_policy": {
            "objective_failure_is_retained": True,
            "failure_grants_automatic_retry": False,
            "failure_grants_configuration_search": False,
            "failure_grants_song_processing": False,
            "failure_grants_activation": False,
        },
        "next_approval": {
            "required": True,
            "received": False,
            "exact_text": (
                "I approve one network-denied MLX generated-tensor objective forward "
                "for bs-roformer-mega-53-synth-v1 on the Apple M3 Max 36 GB class, "
                "including one exact reload of the verified local checkpoint and "
                "construction of the verified 53-stem model, using only one generated "
                "in-memory stereo float32 tensor of 881,664 samples (seed 0) and the "
                "frozen 512-hop, overlap-2 alignment contract. I approve persisting "
                "only the JSON objective report. No private audio, persisted audio, "
                "song processing, public activation, source selection, MIDI, hosting, "
                "redistribution or automatic retry is approved."
            ),
            "authorizes_checkpoint_reloads": 1,
            "authorizes_model_constructions": 1,
            "authorizes_inference_attempts": 1,
            "authorizes_generated_tensor_processing": True,
            "authorizes_private_audio": False,
            "authorizes_song_processing": False,
            "authorizes_persisted_audio": False,
            "authorizes_public_activation": False,
            "authorizes_source_selection": False,
            "authorizes_midi": False,
            "authorizes_hosting": False,
            "authorizes_redistribution": False,
        },
        "effects": {
            "package_imports": 0,
            "checkpoint_loads": 0,
            "model_constructions": 0,
            "generated_tensors_created": 0,
            "inference_attempts": 0,
            "audio_reads": 0,
            "audio_writes": 0,
            "network_attempts": 0,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
        },
    }
    plan["document_sha256"] = synthetic_plan_sha256(plan)
    return plan


def validate_next_synthetic_plan(value: dict[str, Any]) -> dict[str, Any]:
    expected = build_next_synthetic_plan()
    if value != expected:
        raise ValueError("Mega-53 generated-tensor plan differs from the reviewed plan")
    alignment = value["alignment_contract"]
    if alignment["aligned_chunk_size"] % ALIGNMENT_QUANTUM:
        raise ValueError("Mega-53 aligned chunk does not preserve the overlap clock")
    if alignment["aligned_step_size"] % STFT_HOP_LENGTH:
        raise ValueError("Mega-53 aligned step does not preserve the STFT clock")
    if NATIVE_ROLES[SYNTH_ROLE_INDEX] != "synth":
        raise ValueError("Mega-53 synth role mapping differs")
    if any(value["effects"].values()):
        raise ValueError("Mega-53 generated-tensor plan must have no effects")
    return copy.deepcopy(value)


__all__ = [
    "ALIGNED_CHUNK_SIZE",
    "ALIGNED_STEP_SIZE",
    "ALIGNMENT_QUANTUM",
    "MODEL_LOAD_REPORT_SHA256",
    "NATIVE_ROLES",
    "NUM_OVERLAP",
    "PUBLISHED_CHUNK_SIZE",
    "STFT_HOP_LENGTH",
    "SYNTHETIC_PLAN_SCHEMA",
    "SYNTHETIC_PLAN_STATUS",
    "SYNTH_ROLE_INDEX",
    "build_next_synthetic_plan",
    "synthetic_plan_sha256",
    "validate_next_synthetic_plan",
]
