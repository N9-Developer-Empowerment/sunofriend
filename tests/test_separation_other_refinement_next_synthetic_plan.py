from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from sunofriend.separation_other_refinement_next_synthetic_plan import (
    ALIGNED_CHUNK_SIZE,
    ALIGNED_STEP_SIZE,
    ALIGNMENT_QUANTUM,
    NATIVE_ROLES,
    STFT_HOP_LENGTH,
    SYNTH_ROLE_INDEX,
    build_next_synthetic_plan,
    validate_next_synthetic_plan,
)


ROOT = Path(__file__).resolve().parents[1]


def test_plan_resolves_both_chunk_and_overlap_step_clocks() -> None:
    plan = build_next_synthetic_plan()
    alignment = plan["alignment_contract"]

    assert alignment["published_chunk_size"] == 882_000
    assert alignment["published_step_size"] == 441_000
    assert alignment["published_chunk_is_valid"] is False
    assert alignment["published_step_is_valid"] is False
    assert ALIGNED_CHUNK_SIZE == 881_664
    assert ALIGNED_STEP_SIZE == 440_832
    assert ALIGNED_CHUNK_SIZE % ALIGNMENT_QUANTUM == 0
    assert ALIGNED_STEP_SIZE % STFT_HOP_LENGTH == 0
    assert alignment["adjustment_samples"] == -336
    assert alignment["generated_input_padding_samples"] == 0
    assert alignment["generated_output_crop_samples"] == 0


def test_plan_is_single_use_generated_only_and_awaits_approval() -> None:
    plan = build_next_synthetic_plan()

    assert plan["status"] == "awaiting_explicit_generated_tensor_forward_approval"
    assert plan["registered"] is False
    assert plan["executable"] is False
    assert len(NATIVE_ROLES) == 53
    assert NATIVE_ROLES[SYNTH_ROLE_INDEX] == "synth"
    assert plan["proposed_single_run"]["inference_attempt_limit"] == 1
    assert plan["proposed_single_run"]["input"]["shape"] == [1, 2, 881_664]
    assert plan["proposed_single_run"]["expected_output"]["shape"] == [
        1,
        53,
        2,
        881_664,
    ]
    assert plan["next_approval"]["required"] is True
    assert plan["next_approval"]["received"] is False
    assert plan["next_approval"]["authorizes_inference_attempts"] == 1
    assert plan["next_approval"]["authorizes_private_audio"] is False
    assert plan["failure_policy"]["failure_grants_automatic_retry"] is False
    assert not any(plan["effects"].values())
    assert validate_next_synthetic_plan(plan) == plan


def test_plan_rejects_authority_or_alignment_mutation() -> None:
    changed = copy.deepcopy(build_next_synthetic_plan())
    changed["next_approval"]["authorizes_song_processing"] = True

    with pytest.raises(ValueError, match="differs from the reviewed plan"):
        validate_next_synthetic_plan(changed)


def test_plan_script_only_prints_the_contract() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(
                ROOT
                / "scripts"
                / "plan-separation-other-refinement-next-synthetic.py"
            ),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == build_next_synthetic_plan()


def test_public_capability_binds_the_exact_no_effects_plan() -> None:
    capability = json.loads(
        (ROOT / "website" / "public" / "agent-capabilities.json").read_text(
            encoding="utf-8"
        )
    )
    published = capability["experiments"]["finished_mix_separation"][
        "other_refinement"
    ]["next_synth_challenger"]["synthetic_forward_plan"]
    plan = build_next_synthetic_plan()

    assert published["schema"] == plan["schema"]
    assert published["status"] == plan["status"]
    assert published["document_sha256"] == plan["document_sha256"]
    assert published["aligned_chunk_size"] == plan["alignment_contract"][
        "aligned_chunk_size"
    ]
    assert published["aligned_step_size"] == plan["alignment_contract"][
        "aligned_step_size"
    ]
    assert published["target_role_zero_based_index"] == SYNTH_ROLE_INDEX
    assert published["inference_attempt_limit"] == 1
    assert published["automatic_retry"] is False
    assert published["inference_authorized"] is False
