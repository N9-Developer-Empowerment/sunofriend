from __future__ import annotations

import copy
import json
from pathlib import Path
import wave

import pytest

from sunofriend.separation_other_refinement import (
    OTHER_REFINEMENT_PLAN_SCHEMA,
    OTHER_REFINEMENT_PROFILE_ID,
    OTHER_REFINEMENT_RESULT_SCHEMA,
    OTHER_REFINEMENT_SCOPE_ID,
    build_other_refinement_plan,
    create_other_refinement_synthetic_fixture,
    other_refinement_registry,
    validate_other_refinement_plan,
    validate_other_refinement_result,
)
from sunofriend.separation_alpha import main as separation_main
from sunofriend.separation_scopes import separation_capabilities


def _geometry() -> dict[str, object]:
    return {
        "sample_rate": 44_100,
        "channels": 2,
        "frames": 88_200,
        "duration_seconds": 2.0,
        "sample_width_bytes": 3,
    }


def _plan(*, target_id: str = "guitar") -> dict[str, object]:
    return build_other_refinement_plan(
        parent_profile_id="scnet-large-musdb-release-v1",
        parent_report_sha256="a" * 64,
        parent_node_id="node:" + "b" * 64,
        parent_audio_sha256="c" * 64,
        parent_geometry=_geometry(),
        target_id=target_id,
    )


def test_registry_is_opt_in_studio_execution_route() -> None:
    registry = other_refinement_registry()
    capabilities = separation_capabilities()

    assert registry["schema"] == "sunofriend.other-refinement-registry.v1"
    assert registry["scope_id"] == OTHER_REFINEMENT_SCOPE_ID
    assert registry["profile_id"] == OTHER_REFINEMENT_PROFILE_ID
    assert registry["status"] == "studio_challenger"
    assert registry["release_tier"] == "studio_challenger"
    assert registry["registration_surface"] == "studio_only"
    assert registry["contract_available"] is True
    assert registry["implementation_available"] is True
    assert registry["executable"] is True
    assert registry["candidate_profile_id"] == (
        "demucs-mlx-htdemucs-6s-other-refinement-v1"
    )
    assert registry["candidate_status"] == "studio_challenger"
    assert registry["candidate_setup_available"] is True
    assert registry["candidate_target_mapping"]["guitar"]["model_role"] == "guitar"
    assert registry["candidate_target_mapping"]["keys"] == {
        "model_role": "piano",
        "semantic_status": "disclosed_piano_proxy_not_general_keys",
    }
    assert registry["parent_profile_id"] == "scnet-large-musdb-release-v1"
    assert [item["target_id"] for item in registry["supported_targets"]] == [
        "guitar",
        "keys",
    ]
    assert registry["policy"]["parent_and_children_mutually_exclusive"] is True
    assert registry["policy"]["parent_and_children_cannot_both_enter_midi"] is True
    assert registry["policy"]["candidate_comparison_selects_no_winner"] is True
    assert capabilities["refinement_registry"] == registry
    assert OTHER_REFINEMENT_SCOPE_ID not in {
        item["id"] for item in capabilities["scopes"]
    }


def test_profiles_command_reports_executable_studio_challenger(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert separation_main(["profiles"]) == 0
    output = capsys.readouterr().out

    assert "Studio-only refinement contract" in output
    assert (
        "other-refinement-v1: studio_challenger "
        "(guitar, keys; executable: yes)" in output
    )


@pytest.mark.parametrize(
    ("target_id", "canonical_role"),
    [("guitar", "rhythm"), ("keys", "keys")],
)
def test_plan_binds_one_target_and_exact_residual(
    target_id: str,
    canonical_role: str,
) -> None:
    plan = _plan(target_id=target_id)

    assert plan["schema"] == OTHER_REFINEMENT_PLAN_SCHEMA
    assert plan["status"] == "contract_only_no_execution"
    assert plan["request"] == {
        "target_id": target_id,
        "canonical_target_role": canonical_role,
        "one_target_only": True,
    }
    assert [item["kind"] for item in plan["output_contract"]["roles"]] == [
        "requested_target",
        "residual",
    ]
    assert plan["output_contract"]["reconstruction_equation"] == (
        "parent_other = requested_target + residual"
    )
    assert plan["output_contract"]["reconstruction_is_separation_accuracy"] is False
    assert not any(plan["permissions"].values())
    assert not any(plan["effects"].values())
    assert validate_other_refinement_plan(plan) == plan
    assert _plan(target_id=target_id) == plan


@pytest.mark.parametrize("target_id", ["vocals", "drums", "bass", "other", "piano"])
def test_plan_rejects_unsupported_or_parent_roles(target_id: str) -> None:
    with pytest.raises(ValueError, match="target must be exactly one"):
        _plan(target_id=target_id)


def test_plan_accepts_only_the_verified_core_four_parent_profile() -> None:
    with pytest.raises(ValueError, match="verified core-four profile"):
        build_other_refinement_plan(
            parent_profile_id="demucs-mlx-htdemucs-v1",
            parent_report_sha256="a" * 64,
            parent_node_id="node:" + "b" * 64,
            parent_audio_sha256="c" * 64,
            parent_geometry=_geometry(),
            target_id="guitar",
        )


def test_plan_identity_and_parent_binding_are_immutable() -> None:
    plan = _plan()
    changed = copy.deepcopy(plan)
    changed["parent"]["audio_sha256"] = "d" * 64

    with pytest.raises(ValueError, match="document hash differs"):
        validate_other_refinement_plan(changed)

    assert "/Users/" not in json.dumps(plan, sort_keys=True)


def test_validator_preserves_only_the_known_pre_activation_blocker_snapshot() -> None:
    plan = _plan()
    historical = copy.deepcopy(plan)
    historical["blockers"] = [
        "The first target-separation candidate is pinned, but dependency and checkpoint installation still require explicit approval.",
        "The one allowed in-memory fractional-segment remediation has not passed installed-artifact compatibility under network denial.",
        "No candidate has passed offline model construction, resource and output-contract gates.",
        "Studio can describe and compare future candidates, but no refinement runner is exposed.",
    ]
    _reidentify_plan(historical)

    assert validate_other_refinement_plan(historical) == historical

    unknown = copy.deepcopy(historical)
    unknown["blockers"] = ["caller supplied blocker"]
    _reidentify_plan(unknown)
    with pytest.raises(ValueError, match="not a known snapshot"):
        validate_other_refinement_plan(unknown)


@pytest.mark.parametrize("target_id", ["guitar", "keys"])
def test_model_free_fixture_reconstructs_parent_exactly_and_repeats(
    tmp_path: Path,
    target_id: str,
) -> None:
    first = create_other_refinement_synthetic_fixture(
        tmp_path / "first",
        target_id=target_id,
    )
    second = create_other_refinement_synthetic_fixture(
        tmp_path / "second",
        target_id=target_id,
    )
    first_plan = json.loads(Path(first["plan"]).read_text(encoding="utf-8"))
    first_result = json.loads(Path(first["result"]).read_text(encoding="utf-8"))
    second_result = json.loads(Path(second["result"]).read_text(encoding="utf-8"))

    assert first_result["schema"] == OTHER_REFINEMENT_RESULT_SCHEMA
    assert first_result["execution"]["kind"] == "model_free_synthetic"
    assert first_result["execution"]["model_executed"] is False
    assert first_result["execution"]["network_used"] is False
    assert first_result["additive_accounting"] == {
        "equation": "parent_other = requested_target + residual",
        "maximum_absolute_error_lsb": 0,
        "root_mean_square_error_lsb": 0.0,
        "tolerance_lsb": 2,
        "passed": True,
        "used_for_separation_accuracy_claim": False,
    }
    assert first_result["review_status"] == "not_reviewed"
    assert not any(first_result["permissions"].values())
    assert first_result["effects"]["contract_validation_executed"] is True
    assert all(
        value is False
        for key, value in first_result["effects"].items()
        if key != "contract_validation_executed"
    )
    validate_other_refinement_result(
        first_result,
        plan=first_plan,
        root=first["root"],
    )
    assert len(first_result["parent"]["sha256"]) == 64
    assert len(first_result["outputs"]["target"]["sha256"]) == 64
    assert len(first_result["outputs"]["residual"]["sha256"]) == 64
    assert first_result["parent"]["sha256"] == second_result["parent"]["sha256"]
    assert (
        first_result["outputs"]["target"]["sha256"]
        == (second_result["outputs"]["target"]["sha256"])
    )
    assert (
        first_result["outputs"]["residual"]["sha256"]
        == (second_result["outputs"]["residual"]["sha256"])
    )
    assert first_result["document_sha256"] == second_result["document_sha256"]


def test_result_revalidation_detects_changed_audio(tmp_path: Path) -> None:
    fixture = create_other_refinement_synthetic_fixture(tmp_path / "fixture")
    plan = json.loads(Path(fixture["plan"]).read_text(encoding="utf-8"))
    result = json.loads(Path(fixture["result"]).read_text(encoding="utf-8"))
    target = Path(fixture["artifacts"]["target"])

    with wave.open(str(target), "rb") as reader:
        parameters = reader.getparams()
        frames = bytearray(reader.readframes(reader.getnframes()))
    frames[-1] ^= 1
    with wave.open(str(target), "wb") as writer:
        writer.setparams(parameters)
        writer.writeframes(frames)

    with pytest.raises(ValueError, match="target artifact changed"):
        validate_other_refinement_result(result, plan=plan, root=fixture["root"])


def test_fixture_refuses_to_replace_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()

    with pytest.raises(FileExistsError, match="already exists"):
        create_other_refinement_synthetic_fixture(output)


def _rehash(document: dict[str, object]) -> str:
    value = copy.deepcopy(document)
    value.pop("document_sha256", None)
    import hashlib

    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _reidentify_plan(document: dict[str, object]) -> None:
    seed = copy.deepcopy(document)
    seed.pop("document_sha256", None)
    seed.pop("plan_id", None)
    document["plan_id"] = "sha256:" + _rehash(seed)
    document["document_sha256"] = _rehash(document)
