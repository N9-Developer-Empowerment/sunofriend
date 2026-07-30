from __future__ import annotations

from collections.abc import Mapping

import pytest

from sunofriend.separation_checkpoint_policy import (
    DEMUCS_HTDEMUCS_CHECKPOINT_SHA256,
    SeparationCheckpointEvidence,
    SeparationCheckpointLoaderEvidence,
    SeparationCheckpointTermsEvidence,
    SeparationUnsafePickleExceptionEvidence,
    build_separation_checkpoint_policy,
)
from sunofriend.separation_execution_admission import (
    OUTPUT_BOUNDARY_CAPABILITY_SUPPORTED,
    REAL_SEPARATION_EXECUTION_SUPPORTED,
    RESOURCE_LIMIT_CAPABILITY_SUPPORTED,
    RUNTIME_CLOSURE_CAPABILITY_SUPPORTED,
    SUPPORTED_DESCENDANT_POLICY_PROVIDER_IDS,
    SUPPORTED_ISOLATION_PROVIDER_IDS,
    SeparationIsolationEvidence,
    SeparationOutputBoundaryEvidence,
    SeparationResourceLimitEvidence,
    SeparationRuntimeClosureEvidence,
    build_separation_execution_admission,
    separation_execution_admission_sha256,
    validate_separation_execution_admission,
)


def _sha(character: str) -> str:
    return character * 64


def _checkpoint_policy():
    evidence = SeparationCheckpointEvidence(
        checkpoint_id="htdemucs-955717e8",
        declared_format="torch-state-dict",
        classified_container_kind="torch-state-dict",
        checkpoint_sha256=DEMUCS_HTDEMUCS_CHECKPOINT_SHA256,
        checkpoint_bytes=84_000_000,
        classification_evidence_sha256=_sha("a"),
        terms=SeparationCheckpointTermsEvidence(
            terms_sha256=None,
            terms_verified=False,
            license_expression=None,
            allowed_uses=(),
            allowed_use_evidence_sha256=None,
            allowed_use_verified=False,
        ),
        loader=SeparationCheckpointLoaderEvidence(
            loader_id="demucs-states-load-model",
            loader_sha256=_sha("b"),
            deserialization_mode="torch-load-pickle-model-package",
            weights_only=False,
        ),
        unsafe_pickle_exception=SeparationUnsafePickleExceptionEvidence(),
    )
    return build_separation_checkpoint_policy(evidence)


def _runtime(*, all_claimed: bool = True) -> SeparationRuntimeClosureEvidence:
    return SeparationRuntimeClosureEvidence(
        runtime_artifact_sha256=_sha("c"),
        runtime_measurements_sha256=_sha("d"),
        closure_evidence_sha256=_sha("e") if all_claimed else None,
        base_standard_library_bound=all_claimed,
        pyvenv_home_bound=all_claimed,
        native_dynamic_libraries_bound=all_claimed,
        accelerator_runtime_bound=all_claimed,
    )


def _isolation(*, all_claimed: bool = True) -> SeparationIsolationEvidence:
    return SeparationIsolationEvidence(
        provider_id="reported-macos-provider",
        provider_sha256=_sha("f"),
        provider_available=all_claimed,
        fail_closed=all_claimed,
        network_denial_enforced=all_claimed,
        network_denial_evidence_sha256=_sha("1") if all_claimed else None,
        outbound_attempt_observation_enabled=all_claimed,
        outbound_attempt_observer_sha256=_sha("2") if all_claimed else None,
        model_descendant_policy=(
            "deny_all_model_descendants" if all_claimed else "unresolved"
        ),
        model_descendant_denial_enforced=all_claimed,
        model_descendant_attempt_observation_enabled=all_claimed,
        model_descendant_evidence_sha256=_sha("3") if all_claimed else None,
    )


def _exact_output() -> SeparationOutputBoundaryEvidence:
    return SeparationOutputBoundaryEvidence(
        mode="exact_output_fds",
        policy_sha256=_sha("4"),
        exact_output_fds_bound=True,
        exact_output_fds_evidence_sha256=_sha("5"),
        fresh_private_staging=False,
        quarantine_before_validation=False,
        parent_output_verification_required=True,
        publication_disabled=True,
        staging_evidence_sha256=None,
    )


def _staging_output() -> SeparationOutputBoundaryEvidence:
    return SeparationOutputBoundaryEvidence(
        mode="staging_and_quarantine",
        policy_sha256=_sha("6"),
        exact_output_fds_bound=False,
        exact_output_fds_evidence_sha256=None,
        fresh_private_staging=True,
        quarantine_before_validation=True,
        parent_output_verification_required=True,
        publication_disabled=True,
        staging_evidence_sha256=_sha("7"),
    )


def _resources(*, complete: bool = True) -> SeparationResourceLimitEvidence:
    hard = {
        "cpu_time_seconds": 3_600,
        "file_count": 64,
        "memory_bytes": 8_000_000_000,
        "open_file_count": 64,
        "output_bytes": 2_000_000_000,
        "per_output_bytes": 500_000_000,
        "process_count": 1,
        "stderr_bytes": 1_048_576,
        "stdout_bytes": 1_048_576,
        "wall_time_seconds": 3_600,
    }
    if not complete:
        hard.pop("memory_bytes")
    names = tuple(sorted(hard))
    return SeparationResourceLimitEvidence(
        hard_limits=hard,
        hard_enforced=names,
        advisory_limits={
            "thread_count": 32,
            "unified_memory_bytes": 8_000_000_000,
        },
        observed_limits=tuple(
            sorted({*hard, "thread_count"})
        ),
        observation_evidence_sha256=_sha("8"),
    )


def _build(
    *,
    output: SeparationOutputBoundaryEvidence | None = None,
    runtime: SeparationRuntimeClosureEvidence | None = None,
    isolation: SeparationIsolationEvidence | None = None,
    resources: SeparationResourceLimitEvidence | None = None,
):
    return build_separation_execution_admission(
        checkpoint_policy=_checkpoint_policy(),
        runtime=runtime or _runtime(),
        isolation=isolation or _isolation(),
        output=output or _staging_output(),
        resources=resources or _resources(),
    )


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def test_current_htdemucs_style_admission_is_blocked_not_run() -> None:
    admission = _build()
    blockers = set(admission["decision"]["blockers"])

    assert {
        "checkpoint_terms_unverified",
        "checkpoint_is_pickle_model_package",
        "unsafe_deserialization_not_approved",
        "isolation_provider_unavailable",
        "runtime_closure_incomplete",
    }.issubset(blockers)
    assert {
        "network_denial_unproven",
        "network_attempt_observation_unavailable",
        "model_descendant_policy_unproven",
        "filesystem_confinement_unimplemented",
        "input_read_only_enforcement_unimplemented",
        "outside_output_write_denial_unimplemented",
        "trusted_preflight_binding_unimplemented",
        "trusted_runtime_artifact_binding_unimplemented",
        "trusted_launch_plan_binding_unimplemented",
        "trusted_worker_request_binding_unimplemented",
        "preexec_runtime_remeasurement_binding_unimplemented",
        "isolation_provider_qualification_unimplemented",
        "isolation_canary_binding_unimplemented",
        "parent_output_verification_unimplemented",
        "real_transport_unimplemented",
        "backend_accelerator_readiness_unimplemented",
        "resource_memory_closure_unimplemented",
        "real_execution_not_implemented",
    }.issubset(blockers)
    assert admission["status"] == "blocked"
    assert admission["run_status"] == "not_run"
    assert admission["execution_permitted"] is False
    assert admission["publication_scope"] == "private_local_contract_evidence"
    assert admission["public_redacted_projection_available"] is False
    assert all(item is False for item in admission["effects"].values())


def test_caller_success_claims_cannot_enable_code_owned_capabilities() -> None:
    admission = _build()

    assert REAL_SEPARATION_EXECUTION_SUPPORTED is False
    assert RUNTIME_CLOSURE_CAPABILITY_SUPPORTED is False
    assert OUTPUT_BOUNDARY_CAPABILITY_SUPPORTED is False
    assert RESOURCE_LIMIT_CAPABILITY_SUPPORTED is False
    assert not SUPPORTED_ISOLATION_PROVIDER_IDS
    assert not SUPPORTED_DESCENDANT_POLICY_PROVIDER_IDS
    assert admission["runtime_closure"]["caller_evidence_complete"] is True
    assert admission["runtime_closure"]["closure_complete"] is False
    assert admission["isolation"]["provider"]["caller_available"] is True
    assert admission["isolation"]["provider"]["code_supported"] is False
    assert admission["isolation"]["network_denial"]["caller_enforced"] is True
    assert admission["isolation"]["network_denial"]["ready"] is False
    assert (
        admission["isolation"]["outbound_attempt_observation"]["caller_enabled"]
        is True
    )
    assert (
        admission["isolation"]["outbound_attempt_observation"]["ready"] is False
    )
    assert admission["output_boundary"]["caller_evidence_complete"] is True
    assert admission["output_boundary"]["ready"] is False
    assert admission["resource_limits"]["capability_supported"] is False


def test_network_denial_and_attempt_observation_are_separate_controls() -> None:
    evidence = _isolation(all_claimed=False)
    admission = _build(isolation=evidence)

    assert admission["isolation"]["network_denial"] == {
        "caller_enforced": False,
        "evidence_sha256": None,
        "ready": False,
    }
    assert admission["isolation"]["outbound_attempt_observation"] == {
        "caller_enabled": False,
        "observer_sha256": None,
        "ready": False,
    }
    assert admission["isolation"]["model_descendants"]["policy"] == "unresolved"
    assert (
        admission["isolation"]["model_descendants"]["provider_code_supported"]
        is False
    )


@pytest.mark.parametrize(
    ("output", "caller_complete", "extra_blocker"),
    [
        (_exact_output(), True, "output_transport_mismatch_unresolved"),
        (_staging_output(), True, None),
        (
            SeparationOutputBoundaryEvidence(
                mode="staging_and_quarantine",
                policy_sha256=_sha("9"),
                exact_output_fds_bound=False,
                exact_output_fds_evidence_sha256=None,
                fresh_private_staging=True,
                quarantine_before_validation=False,
                parent_output_verification_required=True,
                publication_disabled=True,
                staging_evidence_sha256=_sha("a"),
            ),
            False,
            None,
        ),
    ],
)
def test_output_modes_are_distinguished_without_authorising(
    output: SeparationOutputBoundaryEvidence,
    caller_complete: bool,
    extra_blocker: str | None,
) -> None:
    admission = _build(output=output)

    assert admission["output_boundary"]["mode"] == output.mode
    assert (
        admission["output_boundary"]["caller_evidence_complete"]
        is caller_complete
    )
    assert admission["output_boundary"]["ready"] is False
    assert "output_boundary_incomplete" in admission["decision"]["blockers"]
    if extra_blocker is not None:
        assert extra_blocker in admission["decision"]["blockers"]


def test_resources_are_sorted_and_keep_hard_advisory_observed_distinct() -> None:
    admission = _build()
    value = admission["resource_limits"]

    assert tuple(item["name"] for item in value["hard"]) == tuple(
        sorted(item["name"] for item in value["hard"])
    )
    assert tuple(item["name"] for item in value["advisory"]) == tuple(
        sorted(item["name"] for item in value["advisory"])
    )
    assert tuple(item["name"] for item in value["observed"]) == tuple(
        sorted(item["name"] for item in value["observed"])
    )
    assert value["readiness"]["hard_limits_complete"] is True
    assert value["readiness"]["hard_enforcement_complete"] is True
    assert value["readiness"]["hard_observation_complete"] is True
    assert (
        "advisory_resource_limits_not_hard_enforced"
        in admission["decision"]["advisories"]
    )

    incomplete = _build(resources=_resources(complete=False))
    assert (
        incomplete["resource_limits"]["readiness"]["hard_limits_complete"]
        is False
    )
    assert "resource_hard_limits_incomplete" in incomplete["decision"]["blockers"]


def test_resource_inputs_are_bounded() -> None:
    with pytest.raises(ValueError, match="positive integers"):
        SeparationResourceLimitEvidence(
            hard_limits={"wall_time_seconds": 1 << 64},
            hard_enforced=("wall_time_seconds",),
            advisory_limits={},
            observed_limits=("wall_time_seconds",),
            observation_evidence_sha256=_sha("b"),
        )
    with pytest.raises(ValueError, match="entry count"):
        SeparationResourceLimitEvidence(
            hard_limits={f"limit_{index}": 1 for index in range(65)},
            hard_enforced=(),
            advisory_limits={},
            observed_limits=(),
            observation_evidence_sha256=None,
        )


def test_admission_is_deeply_immutable_sorted_and_self_hashed() -> None:
    checkpoint = _checkpoint_policy()
    runtime = _runtime()
    isolation = _isolation()
    output = _staging_output()
    resources = _resources()
    admission = build_separation_execution_admission(
        checkpoint_policy=checkpoint,
        runtime=runtime,
        isolation=isolation,
        output=output,
        resources=resources,
    )

    assert admission["admission_sha256"] == separation_execution_admission_sha256(
        admission
    )
    assert admission["decision"]["blockers"] == tuple(
        sorted(admission["decision"]["blockers"])
    )
    with pytest.raises(TypeError):
        admission["decision"]["status"] = "admitted"

    plain = _plain(admission)
    assert validate_separation_execution_admission(
        plain,
        checkpoint_policy=checkpoint,
        runtime=runtime,
        isolation=isolation,
        output=output,
        resources=resources,
    ) == admission
    plain["execution_permitted"] = True
    with pytest.raises(ValueError, match="does not match reported evidence"):
        validate_separation_execution_admission(
            plain,
            checkpoint_policy=checkpoint,
            runtime=runtime,
            isolation=isolation,
            output=output,
            resources=resources,
        )


def test_plain_checkpoint_mapping_cannot_reach_admission() -> None:
    with pytest.raises(ValueError, match="exact checkpoint policy"):
        build_separation_execution_admission(
            checkpoint_policy=_plain(_checkpoint_policy()),  # type: ignore[arg-type]
            runtime=_runtime(),
            isolation=_isolation(),
            output=_staging_output(),
            resources=_resources(),
        )
