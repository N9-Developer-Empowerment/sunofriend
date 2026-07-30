from __future__ import annotations

import hashlib
import runpy
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from sunofriend.separation_checkpoint_inspection import (
    SeparationCheckpointInspection,
    SeparationCheckpointInspectionRequest,
    separation_checkpoint_inspection_sha256,
)
from sunofriend.separation_checkpoint_policy import (
    SeparationCheckpointEvidence,
    SeparationCheckpointLoaderEvidence,
    SeparationCheckpointPolicyRecord,
    SeparationCheckpointTermsEvidence,
    SeparationUnsafePickleExceptionEvidence,
    build_separation_checkpoint_policy,
)
from sunofriend.separation_execution_admission import (
    SeparationIsolationEvidence,
    SeparationOutputBoundaryEvidence,
    SeparationResourceLimitEvidence,
    SeparationRuntimeClosureEvidence,
    build_separation_execution_admission,
)
from sunofriend.separation_execution_admission_binding import (
    TRUSTED_CHECKPOINT_ADMISSION_EXECUTION_SUPPORTED,
    SeparationExecutionAdmissionBindingRecord,
    build_separation_execution_admission_binding,
    separation_execution_admission_binding_sha256,
    validate_separation_execution_admission_binding,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _reported_checkpoint_policy(
    inspection: SeparationCheckpointInspection,
    *,
    classification_evidence_sha256: str | None = None,
) -> SeparationCheckpointPolicyRecord:
    checkpoint = inspection["checkpoint"]
    evidence = SeparationCheckpointEvidence(
        checkpoint_id=checkpoint["checkpoint_id"],
        declared_format=checkpoint["declared_format"],
        classified_container_kind="uninspected",
        checkpoint_sha256=checkpoint["sha256"],
        checkpoint_bytes=checkpoint["bytes"],
        classification_evidence_sha256=(
            classification_evidence_sha256
            or inspection["classification"]["classification_evidence_sha256"]
        ),
        terms=SeparationCheckpointTermsEvidence(
            terms_sha256=None,
            terms_verified=False,
            license_expression=None,
            allowed_uses=(),
            allowed_use_evidence_sha256=None,
            allowed_use_verified=False,
        ),
        loader=SeparationCheckpointLoaderEvidence(
            loader_id="test-static-checkpoint-loader",
            loader_sha256=_sha("loader"),
            deserialization_mode="torch-load-state-dict",
            weights_only=True,
        ),
        unsafe_pickle_exception=SeparationUnsafePickleExceptionEvidence(),
    )
    return build_separation_checkpoint_policy(evidence)


def _runtime() -> SeparationRuntimeClosureEvidence:
    return SeparationRuntimeClosureEvidence(
        runtime_artifact_sha256=_sha("runtime artifact"),
        runtime_measurements_sha256=_sha("runtime measurements"),
        closure_evidence_sha256=_sha("reported closure"),
        base_standard_library_bound=True,
        pyvenv_home_bound=True,
        native_dynamic_libraries_bound=True,
        accelerator_runtime_bound=True,
    )


def _isolation() -> SeparationIsolationEvidence:
    return SeparationIsolationEvidence(
        provider_id="reported-test-provider",
        provider_sha256=_sha("provider"),
        provider_available=True,
        fail_closed=True,
        network_denial_enforced=True,
        network_denial_evidence_sha256=_sha("network denial"),
        outbound_attempt_observation_enabled=True,
        outbound_attempt_observer_sha256=_sha("network observer"),
        model_descendant_policy="deny_all_model_descendants",
        model_descendant_denial_enforced=True,
        model_descendant_attempt_observation_enabled=True,
        model_descendant_evidence_sha256=_sha("descendant evidence"),
    )


def _output() -> SeparationOutputBoundaryEvidence:
    return SeparationOutputBoundaryEvidence(
        mode="staging_and_quarantine",
        policy_sha256=_sha("output policy"),
        exact_output_fds_bound=False,
        exact_output_fds_evidence_sha256=None,
        fresh_private_staging=True,
        quarantine_before_validation=True,
        parent_output_verification_required=True,
        publication_disabled=True,
        staging_evidence_sha256=_sha("staging"),
    )


def _resources() -> SeparationResourceLimitEvidence:
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
    return SeparationResourceLimitEvidence(
        hard_limits=hard,
        hard_enforced=tuple(sorted(hard)),
        advisory_limits={"thread_count": 32},
        observed_limits=tuple(sorted({*hard, "thread_count"})),
        observation_evidence_sha256=_sha("resource observer"),
    )


def _fixture(tmp_path: Path, *, model_pickle: bool = False) -> dict[str, Any]:
    namespace = runpy.run_path(
        str(Path(__file__).with_name("test_separation_checkpoint_inspection.py"))
    )
    pickle_data = namespace["_model_pickle"]() if model_pickle else b"\x80\x02}."
    checkpoint_bytes = namespace["_torch_zip"](pickle_data=pickle_data)
    checkpoint = namespace["_fixture"](tmp_path, checkpoint_bytes)
    inspection = namespace["_inspect"](checkpoint)
    policy = _reported_checkpoint_policy(inspection)
    runtime = _runtime()
    isolation = _isolation()
    output = _output()
    resources = _resources()
    admission = build_separation_execution_admission(
        checkpoint_policy=policy,
        runtime=runtime,
        isolation=isolation,
        output=output,
        resources=resources,
    )
    values = {
        "execution_admission": admission,
        "checkpoint_policy": policy,
        "runtime": runtime,
        "isolation": isolation,
        "output": output,
        "resources": resources,
        "checkpoint_inspection": inspection,
        "trusted_checkpoint_inspection": inspection,
        "trusted_checkpoint_inspection_request": checkpoint["trusted_request"],
    }
    binding = build_separation_execution_admission_binding(**values)
    return {
        **checkpoint,
        **values,
        "binding": binding,
    }


def _binding_kwargs(fixture: dict[str, Any]) -> dict[str, Any]:
    return {
        key: fixture[key]
        for key in (
            "execution_admission",
            "checkpoint_policy",
            "runtime",
            "isolation",
            "output",
            "resources",
            "checkpoint_inspection",
            "trusted_checkpoint_inspection",
            "trusted_checkpoint_inspection_request",
        )
    }


def test_cross_binding_is_private_immutable_blocked_and_additive(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    value = fixture["binding"]
    v1_blockers = set(
        fixture["execution_admission"]["decision"]["blockers"]
    )

    assert type(value) is SeparationExecutionAdmissionBindingRecord
    assert TRUSTED_CHECKPOINT_ADMISSION_EXECUTION_SUPPORTED is False
    assert value["status"] == "blocked"
    assert value["run_status"] == "not_run"
    assert value["execution_permitted"] is False
    assert value["reported_claims_trusted"] is False
    assert value["public_redacted_projection_available"] is False
    assert v1_blockers.issubset(value["decision"]["blockers"])
    assert {
        "checkpoint_descriptor_not_carried_to_loader",
        "checkpoint_path_to_loader_toctou_unresolved",
        "static_checkpoint_inspection_not_load_authority",
    }.issubset(value["decision"]["blockers"])
    assert value["checkpoint_static_inspection"][
        "checkpoint_descriptor_transport"
    ] == "not_carried_to_loader"
    assert value["checkpoint_static_inspection"][
        "checkpoint_path_to_loader_toctou"
    ] == "unresolved"
    assert value["checkpoint_static_inspection"]["authorizes_loading"] is False
    assert value["checkpoint_static_inspection"]["authorizes_execution"] is False
    assert all(effect is False for effect in value["effects"].values())
    assert value["binding_sha256"] == (
        separation_execution_admission_binding_sha256(value)
    )
    assert str(tmp_path) not in repr(_plain(value))

    checked = validate_separation_execution_admission_binding(
        _plain(value),
        **_binding_kwargs(fixture),
    )
    assert _plain(checked) == _plain(value)
    with pytest.raises(TypeError):
        value["decision"]["status"] = "admitted"  # type: ignore[index]


@pytest.mark.parametrize(
    "replacement",
    [
        "plain_admission",
        "plain_inspection",
        "forged_request",
    ],
)
def test_serialized_or_forged_inputs_cannot_supply_parent_authority(
    tmp_path: Path,
    replacement: str,
) -> None:
    fixture = _fixture(tmp_path)
    values = _binding_kwargs(fixture)
    if replacement == "plain_admission":
        values["execution_admission"] = _plain(
            fixture["execution_admission"]
        )
        message = "exact canonical V1 record"
    elif replacement == "plain_inspection":
        values["checkpoint_inspection"] = _plain(
            fixture["checkpoint_inspection"]
        )
        message = "exact parent-issued record"
    else:
        original = fixture["trusted_checkpoint_inspection_request"]
        forged = object.__new__(SeparationCheckpointInspectionRequest)
        for name in (
            "worker_request",
            "request_sha256",
            "preflight_sha256",
            "acceptance_artifact_sha256",
            "checkpoint_path",
            "checkpoint_id",
            "declared_format",
            "checkpoint_sha256",
            "checkpoint_bytes",
        ):
            object.__setattr__(forged, name, getattr(original, name))
        values["trusted_checkpoint_inspection_request"] = forged
        message = "lacks parent-process authority"

    with pytest.raises(ValueError, match=message):
        build_separation_execution_admission_binding(**values)


def test_inspection_request_and_admission_substitution_fail_cross_binding(
    tmp_path: Path,
) -> None:
    first = _fixture(tmp_path / "first")
    second = _fixture(tmp_path / "second", model_pickle=True)

    substituted_request = _binding_kwargs(first)
    substituted_request["trusted_checkpoint_inspection_request"] = second[
        "trusted_checkpoint_inspection_request"
    ]
    with pytest.raises(ValueError, match="exact parent request"):
        build_separation_execution_admission_binding(**substituted_request)

    substituted_inspection = _binding_kwargs(first)
    substituted_inspection["checkpoint_inspection"] = second[
        "checkpoint_inspection"
    ]
    substituted_inspection["trusted_checkpoint_inspection"] = second[
        "checkpoint_inspection"
    ]
    substituted_inspection[
        "trusted_checkpoint_inspection_request"
    ] = second["trusted_checkpoint_inspection_request"]
    with pytest.raises(ValueError, match="does not bind trusted"):
        build_separation_execution_admission_binding(**substituted_inspection)


def test_policy_classification_evidence_must_bind_static_inspection(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    policy = _reported_checkpoint_policy(
        fixture["checkpoint_inspection"],
        classification_evidence_sha256=_sha("caller substitution"),
    )
    admission = build_separation_execution_admission(
        checkpoint_policy=policy,
        runtime=fixture["runtime"],
        isolation=fixture["isolation"],
        output=fixture["output"],
        resources=fixture["resources"],
    )
    values = _binding_kwargs(fixture)
    values["checkpoint_policy"] = policy
    values["execution_admission"] = admission

    with pytest.raises(ValueError, match="bind trusted static inspection"):
        build_separation_execution_admission_binding(**values)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.__setitem__("execution_permitted", True),
        lambda value: value["bindings"].__setitem__(
            "checkpoint_inspection_sha256", _sha("substitute inspection")
        ),
        lambda value: value["decision"]["blockers"].remove(
            "checkpoint_descriptor_not_carried_to_loader"
        ),
        lambda value: value["checkpoint_static_inspection"].__setitem__(
            "checkpoint_descriptor_transport", "inherited_fd_5"
        ),
    ],
)
def test_rehashed_wrapper_tampering_cannot_enable_or_claim_transport(
    tmp_path: Path,
    mutation: Any,
) -> None:
    fixture = _fixture(tmp_path)
    document = _plain(fixture["binding"])
    mutation(document)
    document["binding_sha256"] = (
        separation_execution_admission_binding_sha256(document)
    )

    with pytest.raises(ValueError, match="does not match trusted evidence"):
        validate_separation_execution_admission_binding(
            document,
            **_binding_kwargs(fixture),
        )


def test_rehashed_same_type_inspection_classification_forgery_is_rejected(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    original = fixture["checkpoint_inspection"]
    document = _plain(original)
    document["classification"]["container_kind"] = (
        "torch-zip-pickle-model-package"
    )
    document["classification"]["confidence"] = "strong_static_evidence"
    document["classification"]["reason_codes"] = ["caller_substitution"]
    document["classification"]["classification_evidence_sha256"] = _sha(
        "caller classification"
    )
    document["inspection_sha256"] = separation_checkpoint_inspection_sha256(
        document
    )
    forged = object.__new__(SeparationCheckpointInspection)
    object.__setattr__(forged, "_document", document)
    object.__setattr__(forged, "_request", original._request)  # noqa: SLF001
    object.__setattr__(  # noqa: SLF001
        forged,
        "_authority",
        original._authority,  # noqa: SLF001
    )
    values = _binding_kwargs(fixture)
    values["checkpoint_inspection"] = forged

    with pytest.raises(ValueError, match="exact trusted parent observation"):
        build_separation_execution_admission_binding(**values)


def test_binding_module_has_no_io_execution_or_loader_surface() -> None:
    import ast
    import sunofriend.separation_execution_admission_binding as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_imports = {
        "asyncio",
        "ctypes",
        "importlib",
        "multiprocessing",
        "os",
        "pathlib",
        "pickle",
        "runpy",
        "socket",
        "subprocess",
        "torch",
        "urllib",
        "zipfile",
    }
    forbidden_calls = {
        "compile",
        "eval",
        "exec",
        "__import__",
        "open",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {
                alias.name.split(".", 1)[0] for alias in node.names
            }.intersection(forbidden_imports)
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".", 1)[0] not in forbidden_imports
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_calls
