from __future__ import annotations

import copy
import hashlib
import runpy
import stat
from pathlib import Path
from typing import Any, Mapping

import pytest

from sunofriend.separation_launch_contract import (
    REAL_WORKER_EXECUTION_SUPPORTED,
    SEPARATION_DESCRIPTOR_POLICY_SHA256,
    SEPARATION_LAUNCH_ENVIRONMENT_SHA256,
    SEPARATION_PRIVATE_ISOLATION_TEMPLATE_SHA256,
    SeparationSupervisorAuthority,
    SeparationSupervisorObservation,
    advance_separation_lifecycle,
    build_separation_launch_plan,
    build_separation_terminal_receipt,
    create_separation_lifecycle,
    separation_launch_plan_sha256,
    validate_separation_launch_plan,
    validate_separation_lifecycle,
    validate_separation_terminal_receipt,
)
from sunofriend.separation_runtime_artifact import (
    SeparationRuntimeArtifactParentEvidence,
    build_separation_runtime_artifact,
    separation_runtime_artifact_sha256,
    separation_runtime_measurements_sha256,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _plain(value: Any) -> Any:
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _fixture(tmp_path: Path) -> dict[str, Any]:
    namespace = runpy.run_path(
        str(Path(__file__).with_name("test_separation_worker_contract.py"))
    )
    runtime_namespace = runpy.run_path(
        str(Path(__file__).with_name("test_separation_runtime_artifact.py"))
    )
    fixture = namespace["_fixture"](tmp_path)
    runtime_inputs = runtime_namespace["_inputs"]()
    fixture["runtime_artifact"] = runtime_inputs["trusted_runtime_artifact"]
    isolation = copy.deepcopy(fixture["isolation"])
    isolation.update(
        {
            "environment_sha256": SEPARATION_LAUNCH_ENVIRONMENT_SHA256,
            "file_descriptor_policy_sha256": (
                SEPARATION_DESCRIPTOR_POLICY_SHA256
            ),
            "profile_sha256": SEPARATION_PRIVATE_ISOLATION_TEMPLATE_SHA256,
        }
    )
    fixture["worker_request"] = namespace["_rebuild_request"](
        fixture, isolation=isolation
    )
    fixture["isolation"] = isolation
    request = fixture["worker_request"]
    runtime_inputs["worker_request_sha256"] = request["request_sha256"]
    runtime_inputs["preflight_sha256"] = fixture["preflight"]["preflight_sha256"]
    runtime_inputs["worker"] = runtime_namespace["_file"](
        request["paths"]["worker_path"],
        "registered worker",
        inode=3_001,
        size=request["identities"]["worker"]["bytes"],
    )
    runtime_inputs["worker"]["sha256"] = request["identities"]["worker"]["sha256"]
    runtime_inputs["dependency_lock"] = runtime_namespace["_file"](
        request["paths"]["dependency_lock_path"],
        "registered dependency lock",
        inode=3_002,
        size=request["identities"]["dependency_lock"]["bytes"],
    )
    runtime_inputs["dependency_lock"]["sha256"] = request["identities"][
        "dependency_lock"
    ]["sha256"]
    runtime_inputs["ancestor_directories"] = _runtime_ancestors(runtime_inputs)
    measurements = separation_runtime_measurements_sha256(
        launcher_chain=runtime_inputs["launcher_chain"],
        ancestor_directories=runtime_inputs["ancestor_directories"],
        final_native_executable=runtime_inputs["final_native_executable"],
        pyvenv_config=runtime_inputs["pyvenv_config"],
        site_packages=runtime_inputs["site_packages"],
        worker=runtime_inputs["worker"],
        dependency_lock=runtime_inputs["dependency_lock"],
    )
    runtime_parent = SeparationRuntimeArtifactParentEvidence(
        worker_request_sha256=request["request_sha256"],
        preflight_sha256=fixture["preflight"]["preflight_sha256"],
        measurements_sha256=measurements,
    )
    runtime_inputs["trusted_parent_evidence"] = runtime_parent
    runtime_document = build_separation_runtime_artifact(**runtime_inputs)
    trusted = {
        "trusted_preflight": fixture["preflight"],
        "trusted_acceptance": fixture["acceptance"],
        "trusted_separation_request": fixture["separation_request"],
        "trusted_runtime_artifact": fixture["runtime_artifact"],
    }
    fixture["trusted"] = trusted
    fixture["runtime_document"] = runtime_document
    fixture["runtime_parent"] = runtime_parent
    fixture["runtime_inputs"] = runtime_inputs
    fixture["plan"] = build_separation_launch_plan(
        worker_request=fixture["worker_request"],
        runtime_artifact=runtime_document,
        trusted_runtime_parent_evidence=runtime_parent,
        **trusted,
    )
    fixture["supervisor"] = SeparationSupervisorAuthority(
        authority_id="sunofriend-parent-supervisor",
        observer_id=isolation["observer_id"],
        observer_sha256=isolation["observer_sha256"],
    )
    return fixture


def _runtime_ancestors(inputs: Mapping[str, Any]) -> list[dict[str, Any]]:
    logical_paths = [
        *(item["canonical_path"] for item in inputs["launcher_chain"]),
        inputs["pyvenv_config"]["path"],
        inputs["site_packages"]["path"],
        inputs["worker"]["path"],
        inputs["dependency_lock"]["path"],
    ]
    paths: set[str] = set()
    for leaf in logical_paths:
        parent = Path(leaf).parent
        while True:
            paths.add(parent.as_posix())
            if parent == Path("/"):
                break
            parent = parent.parent
    return [
        {
            "canonical_path": path,
            "kind": "directory",
            "lstat": {
                "device": 17,
                "inode": 5_000 + index,
                "mode": stat.S_IFDIR | 0o755,
                "size": 512,
                "mtime_ns": 1_000_000,
                "ctime_ns": 1_000_001,
            },
            "canonical_resolved_path": path,
        }
        for index, path in enumerate(
            sorted(paths, key=lambda item: (len(Path(item).parts), item))
        )
    ]


def _observation(
    fixture: dict[str, Any], event: str, facts: dict[str, Any]
) -> SeparationSupervisorObservation:
    supervisor = fixture["supervisor"]
    return SeparationSupervisorObservation(
        authority_id=supervisor.authority_id,
        observer_sha256=supervisor.observer_sha256,
        event=event,
        facts=facts,
    )


def _advance(
    fixture: dict[str, Any],
    lifecycle: Any,
    event: str,
    facts: dict[str, Any],
) -> Any:
    return advance_separation_lifecycle(
        lifecycle,
        launch_plan=fixture["plan"],
        trusted_supervisor=fixture["supervisor"],
        observation=_observation(fixture, event, facts),
    )


def _reap_facts(
    handle: str | None,
    *,
    exit_code: int = 0,
    termination_kind: str | None = None,
    termination_signal_sent: bool = False,
    kill_escalation_sent: bool = False,
) -> dict[str, Any]:
    if handle is None:
        return {
            "process_handle_sha256": None,
            "reap_disposition": "not_started",
            "exit_code": None,
            "cleanup_sequence": [
                "not_started",
                "observer_closed",
                "process_tree_empty",
            ],
            "exit_observed": False,
            "wait_completed": False,
            "process_reaped": False,
            "observer_closed": True,
            "process_tree_empty": True,
            "termination_kind": termination_kind,
            "termination_signal_sent": False,
            "kill_escalation_sent": False,
            "termination_cleanup_sequence": (
                ["not_started"] if termination_kind else []
            ),
        }
    if termination_kind:
        termination_sequence = (
            [
                "termination_recorded",
                "process_group_signalled",
                "grace_period_observed",
                "kill_escalation_checked",
            ]
            if termination_signal_sent
            else ["termination_recorded", "process_already_exited"]
        )
        termination_sequence.extend(
            [
                "handle_matched",
                "exit_observed",
                "wait_completed",
                "process_reaped",
                "observer_closed",
                "process_tree_empty",
            ]
        )
    else:
        termination_sequence = []
    return {
        "process_handle_sha256": handle,
        "reap_disposition": "reaped",
        "exit_code": exit_code,
        "cleanup_sequence": [
            "handle_matched",
            "exit_observed",
            "wait_completed",
            "process_reaped",
            "observer_closed",
            "process_tree_empty",
        ],
        "exit_observed": True,
        "wait_completed": True,
        "process_reaped": True,
        "observer_closed": True,
        "process_tree_empty": True,
        "termination_kind": termination_kind,
        "termination_signal_sent": termination_signal_sent,
        "kill_escalation_sent": kill_escalation_sent,
        "termination_cleanup_sequence": termination_sequence,
    }


def _release_facts(lease: str | None) -> dict[str, Any]:
    if lease is None:
        return {
            "lease_sha256": None,
            "release_disposition": "not_acquired",
            "release_observed": False,
            "release_sequence": ["not_acquired"],
        }
    return {
        "lease_sha256": lease,
        "release_disposition": "released",
        "release_observed": True,
        "release_sequence": ["lease_matched", "release_observed"],
    }


def _normal_to_inference_finished(fixture: dict[str, Any]) -> Any:
    request = fixture["worker_request"]
    lease, handle = _sha("lease"), _sha("handle")
    lifecycle = create_separation_lifecycle(
        launch_plan=fixture["plan"],
        trusted_supervisor=fixture["supervisor"],
    )
    lifecycle = _advance(
        fixture, lifecycle, "lease_acquired", {"lease_sha256": lease}
    )
    lifecycle = _advance(
        fixture,
        lifecycle,
        "process_handle_acquired",
        _process_handle_facts(lease, handle),
    )
    lifecycle = _advance(
        fixture,
        lifecycle,
        "process_exec_observed",
        _process_exec_facts(fixture, lease, handle),
    )
    lifecycle = _advance(
        fixture,
        lifecycle,
        "process_started",
        _process_started_facts(fixture, lease, handle),
    )
    lifecycle = _advance(
        fixture,
        lifecycle,
        "checkpoint_verified",
        {
            "process_handle_sha256": handle,
            "checkpoint_sha256": request["identities"]["checkpoint"]["sha256"],
        },
    )
    lifecycle = _advance(
        fixture,
        lifecycle,
        "model_loaded",
        {
            "process_handle_sha256": handle,
            "checkpoint_sha256": request["identities"]["checkpoint"]["sha256"],
        },
    )
    for event in ("inference_started", "inference_finished"):
        lifecycle = _advance(
            fixture,
            lifecycle,
            event,
            {
                "process_handle_sha256": handle,
                "worker_request_sha256": request["request_sha256"],
            },
        )
    return lifecycle


def _normal_to_reaped(fixture: dict[str, Any]) -> Any:
    lifecycle = _normal_to_inference_finished(fixture)
    handle = lifecycle["resources"]["process_handle_sha256"]
    return _advance(fixture, lifecycle, "process_reaped", _reap_facts(handle))


def _process_started_facts(
    fixture: dict[str, Any], lease: str, handle: str
) -> dict[str, Any]:
    plan = fixture["plan"]
    return {
        "lease_sha256": lease,
        "process_handle_sha256": handle,
        "handle_kind": "parent_supervised_process",
        "argv_sha256": plan["argv_sha256"],
        "environment_sha256": plan["environment"]["sha256"],
        "descriptor_policy_sha256": plan["descriptor_policy"]["sha256"],
        "isolation_template_sha256": plan["isolation_template"]["sha256"],
        "process_policy_sha256": plan["process_policy"]["sha256"],
        "output_staging_sha256": plan["output_staging"]["sha256"],
        "runtime_sha256": plan["identity_bindings"]["runtime_sha256"],
        "runtime_launcher_chain_sha256": plan["identity_bindings"][
            "runtime_launcher_chain_sha256"
        ],
        "runtime_artifact_sha256": plan["identity_bindings"][
            "runtime_artifact_sha256"
        ],
        "runtime_parent_measurements_sha256": plan["identity_bindings"][
            "runtime_parent_measurements_sha256"
        ],
        "preexec_runtime_measurements_sha256": plan["identity_bindings"][
            "runtime_parent_measurements_sha256"
        ],
        "runtime_remeasurement_observed": True,
        "executable_identity_sha256": plan["identity_bindings"]["runtime_sha256"],
        "descriptor_installation_sha256": plan["descriptor_policy"]["sha256"],
        "descriptor_installation_observed": True,
        "process_policy_observed": True,
        "output_staging_observed": True,
        "exec_observed": True,
        "worker_handshake_sha256": plan["worker_request_sha256"],
        "handshake_observed": True,
    }


def _process_handle_facts(lease: str, handle: str) -> dict[str, Any]:
    return {
        "lease_sha256": lease,
        "process_handle_sha256": handle,
        "handle_kind": "parent_supervised_process",
    }


def _process_exec_facts(
    fixture: dict[str, Any], lease: str, handle: str
) -> dict[str, Any]:
    facts = _process_started_facts(fixture, lease, handle)
    facts["worker_handshake_sha256"] = None
    facts["handshake_observed"] = False
    return facts


def _finish(fixture: dict[str, Any], lifecycle: Any) -> Any:
    lease = lifecycle["resources"]["lease_sha256"]
    lifecycle = _advance(
        fixture, lifecycle, "lease_released", _release_facts(lease)
    )
    return _advance(fixture, lifecycle, "terminal", {})


def test_plan_is_exact_immutable_and_explicitly_non_executing(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    plan = fixture["plan"]
    request = fixture["worker_request"]

    assert REAL_WORKER_EXECUTION_SUPPORTED is False
    assert plan["real_worker_execution_supported"] is False
    assert plan["argv"] == (
        request["paths"]["runtime_python_path"],
        "-I",
        "-B",
        request["paths"]["worker_path"],
        "--request-fd",
        "3",
        "--result-fd",
        "4",
    )
    assert plan["environment"]["inherit_parent"] is False
    assert plan["environment"]["sha256"] == SEPARATION_LAUNCH_ENVIRONMENT_SHA256
    assert plan["descriptor_policy"]["template_sha256"] == (
        SEPARATION_DESCRIPTOR_POLICY_SHA256
    )
    assert plan["isolation_template"]["sha256"] == (
        SEPARATION_PRIVATE_ISOLATION_TEMPLATE_SHA256
    )
    assert [row["descriptor"] for row in plan["descriptor_policy"]["value"][
        "descriptors"
    ]] == [0, 1, 2, 3, 4]
    with pytest.raises(TypeError):
        plan["environment"]["values"]["TZ"] = "Europe/London"

    assert validate_separation_launch_plan(
        plan,
        worker_request=request,
        runtime_artifact=fixture["runtime_document"],
        trusted_runtime_parent_evidence=fixture["runtime_parent"],
        **fixture["trusted"],
    ) == plan


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("environment_sha256", _sha("caller environment")),
        ("file_descriptor_policy_sha256", _sha("caller descriptors")),
        ("profile_sha256", _sha("caller profile")),
    ],
)
def test_plan_rejects_worker_request_not_bound_to_code_owned_policy(
    tmp_path: Path, field: str, replacement: str
) -> None:
    namespace = runpy.run_path(
        str(Path(__file__).with_name("test_separation_worker_contract.py"))
    )
    fixture = _fixture(tmp_path)
    isolation = copy.deepcopy(fixture["isolation"])
    isolation[field] = replacement
    request = namespace["_rebuild_request"](fixture, isolation=isolation)

    with pytest.raises(ValueError, match="runtime artifact|exact launch policy"):
        build_separation_launch_plan(
            worker_request=request,
            runtime_artifact=fixture["runtime_document"],
            trusted_runtime_parent_evidence=fixture["runtime_parent"],
            **fixture["trusted"],
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda plan: plan["argv"].append("--caller-argument"),
        lambda plan: plan["environment"]["values"].__setitem__("PATH", "/tmp"),
        lambda plan: plan["descriptor_policy"]["value"]["descriptors"][3].__setitem__(
            "maximum_bytes", 9_999_999
        ),
        lambda plan: plan["identity_bindings"].__setitem__(
            "runtime_sha256", _sha("substitute runtime")
        ),
        lambda plan: plan["identity_bindings"].__setitem__(
            "runtime_artifact_sha256", _sha("substitute runtime artifact")
        ),
    ],
)
def test_plan_rejects_resigned_policy_and_identity_mutations(
    tmp_path: Path, mutation: Any
) -> None:
    fixture = _fixture(tmp_path)
    document = _plain(fixture["plan"])
    mutation(document)
    document["plan_sha256"] = separation_launch_plan_sha256(document)

    with pytest.raises(ValueError, match="trusted exact policy"):
        validate_separation_launch_plan(
            document,
            worker_request=fixture["worker_request"],
            runtime_artifact=fixture["runtime_document"],
            trusted_runtime_parent_evidence=fixture["runtime_parent"],
            **fixture["trusted"],
        )


def test_plan_rejects_resigned_runtime_artifact_and_parent_measurement(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    artifact = _plain(fixture["runtime_document"])
    substituted = _sha("substituted parent measurements")
    artifact["bindings"]["parent_measurements_sha256"] = substituted
    artifact["artifact_sha256"] = separation_runtime_artifact_sha256(artifact)
    substituted_parent = SeparationRuntimeArtifactParentEvidence(
        worker_request_sha256=fixture["worker_request"]["request_sha256"],
        preflight_sha256=fixture["preflight"]["preflight_sha256"],
        measurements_sha256=substituted,
    )

    with pytest.raises(ValueError, match="measurements|parent-owned"):
        build_separation_launch_plan(
            worker_request=fixture["worker_request"],
            runtime_artifact=artifact,
            trusted_runtime_parent_evidence=substituted_parent,
            **fixture["trusted"],
        )


def test_process_start_requires_fresh_runtime_and_descriptor_observations(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    lease, handle = _sha("lease"), _sha("handle")
    lifecycle = create_separation_lifecycle(
        launch_plan=fixture["plan"],
        trusted_supervisor=fixture["supervisor"],
    )
    lifecycle = _advance(
        fixture, lifecycle, "lease_acquired", {"lease_sha256": lease}
    )
    with pytest.raises(ValueError, match="parent-owned process handle"):
        _advance(
            fixture,
            lifecycle,
            "process_exec_observed",
            _process_exec_facts(fixture, lease, handle),
        )
    lifecycle = _advance(
        fixture,
        lifecycle,
        "process_handle_acquired",
        _process_handle_facts(lease, handle),
    )
    for field, replacement in (
        ("preexec_runtime_measurements_sha256", _sha("stale measurements")),
        ("runtime_remeasurement_observed", False),
        ("descriptor_installation_sha256", _sha("other descriptors")),
        ("descriptor_installation_observed", False),
        ("exec_observed", False),
    ):
        facts = _process_exec_facts(fixture, lease, handle)
        facts[field] = replacement
        with pytest.raises(ValueError, match="exact observed launch"):
            _advance(fixture, lifecycle, "process_exec_observed", facts)
    with pytest.raises(ValueError, match="prior exec observation"):
        _advance(
            fixture,
            lifecycle,
            "process_started",
            _process_started_facts(fixture, lease, handle),
        )
    lifecycle = _advance(
        fixture,
        lifecycle,
        "process_exec_observed",
        _process_exec_facts(fixture, lease, handle),
    )
    for field, replacement in (
        ("worker_handshake_sha256", _sha("stale handshake")),
        ("handshake_observed", False),
    ):
        facts = _process_started_facts(fixture, lease, handle)
        facts[field] = replacement
        with pytest.raises(ValueError, match="exact observed launch"):
            _advance(fixture, lifecycle, "process_started", facts)


def test_replay_rejects_reordered_parent_resource_observations(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    lifecycle = _normal_to_reaped(fixture)
    observations = list(lifecycle._observations)
    observations[1], observations[2] = observations[2], observations[1]

    with pytest.raises(ValueError, match="bind supervisor ledger"):
        validate_separation_lifecycle(
            lifecycle,
            launch_plan=fixture["plan"],
            trusted_supervisor=fixture["supervisor"],
            trusted_observations=observations,
        )


def test_normal_lifecycle_requires_all_milestones_and_cleanup(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    lifecycle = _finish(fixture, _normal_to_reaped(fixture))
    states = [
        event["target_state"]
        for event in lifecycle["events"]
        if event["event_type"] == "milestone"
    ]

    assert states == [
        "planned",
        "lease_acquired",
        "process_started",
        "checkpoint_verified",
        "model_loaded",
        "inference_started",
        "inference_finished",
        "process_reaped",
        "lease_released",
        "terminal",
    ]
    assert lifecycle["outcome"] == "execution_finished_unvalidated"
    assert lifecycle["resources"]["process_cleanup_complete"] is True
    assert lifecycle["resources"]["lease_cleanup_complete"] is True
    assert [event["sequence"] for event in lifecycle["events"]] == list(
        range(len(lifecycle["events"]))
    )
    assert validate_separation_lifecycle(
        lifecycle,
        launch_plan=fixture["plan"],
        trusted_supervisor=fixture["supervisor"],
    ) == lifecycle

    receipt = build_separation_terminal_receipt(
        lifecycle,
        launch_plan=fixture["plan"],
        trusted_supervisor=fixture["supervisor"],
    )
    assert receipt["terminal_outcome"] == "execution_finished_unvalidated"
    assert receipt["result_boundary"] == {
        "scope": "launch_cleanup_only",
        "task_success_proven": False,
        "worker_result_validated": False,
        "post_input_immutability_verified": False,
        "parent_outputs_verified": False,
        "outputs_quarantined": False,
        "publication_permitted": False,
        "acceptance_eligible": False,
        "promotion_eligible": False,
    }
    assert receipt["process_cleanup"]["process_tree_empty"] is True
    assert receipt["lease_cleanup"]["release_observed"] is True
    assert validate_separation_terminal_receipt(
        receipt,
        lifecycle=lifecycle,
        launch_plan=fixture["plan"],
        trusted_supervisor=fixture["supervisor"],
    ) == receipt

    resigned = _plain(receipt)
    resigned["result_boundary"]["worker_result_validated"] = True
    resigned_payload = copy.deepcopy(resigned)
    resigned_payload.pop("receipt_sha256")
    resigned["receipt_sha256"] = _hash_json(resigned_payload)
    with pytest.raises(ValueError, match="does not match trusted lifecycle"):
        validate_separation_terminal_receipt(
            resigned,
            lifecycle=lifecycle,
            launch_plan=fixture["plan"],
            trusted_supervisor=fixture["supervisor"],
        )


@pytest.mark.parametrize("kind", ["cancelled", "failed", "timed_out"])
def test_termination_branch_still_requires_reap_and_release(
    tmp_path: Path, kind: str
) -> None:
    fixture = _fixture(tmp_path)
    lease, handle = _sha("lease"), _sha("handle")
    lifecycle = create_separation_lifecycle(
        launch_plan=fixture["plan"],
        trusted_supervisor=fixture["supervisor"],
    )
    lifecycle = _advance(
        fixture, lifecycle, "lease_acquired", {"lease_sha256": lease}
    )
    lifecycle = _advance(
        fixture,
        lifecycle,
        "process_handle_acquired",
        _process_handle_facts(lease, handle),
    )
    lifecycle = _advance(
        fixture,
        lifecycle,
        "process_exec_observed",
        _process_exec_facts(fixture, lease, handle),
    )
    lifecycle = _advance(
        fixture,
        lifecycle,
        "process_started",
        _process_started_facts(fixture, lease, handle),
    )
    lifecycle = _advance(
        fixture,
        lifecycle,
        kind,
        {
            "code": f"{kind}_by_supervisor",
            "message": f"Supervisor recorded {kind}",
            "retryable": kind == "timed_out",
        },
    )

    with pytest.raises(ValueError, match="expected lifecycle milestone process_reaped"):
        _advance(fixture, lifecycle, "lease_released", _release_facts(lease))
    lifecycle = _advance(
        fixture,
        lifecycle,
        "process_reaped",
        _reap_facts(
            handle,
            exit_code=-15,
            termination_kind=kind,
            termination_signal_sent=True,
        ),
    )
    lifecycle = _finish(fixture, lifecycle)
    assert lifecycle["outcome"] == kind
    assert lifecycle["termination"]["kind"] == kind


@pytest.mark.parametrize(
    ("stage", "kind"),
    [
        ("pre_spawn", "failed"),
        ("post_spawn_pre_exec", "cancelled"),
        ("post_spawn_pre_exec", "failed"),
        ("post_exec_pre_handshake", "timed_out"),
    ],
)
def test_early_termination_cannot_lose_a_created_process_handle(
    tmp_path: Path, stage: str, kind: str
) -> None:
    fixture = _fixture(tmp_path)
    lease, handle = _sha("early lease"), _sha("early handle")
    lifecycle = create_separation_lifecycle(
        launch_plan=fixture["plan"],
        trusted_supervisor=fixture["supervisor"],
    )
    lifecycle = _advance(
        fixture, lifecycle, "lease_acquired", {"lease_sha256": lease}
    )
    if stage != "pre_spawn":
        lifecycle = _advance(
            fixture,
            lifecycle,
            "process_handle_acquired",
            _process_handle_facts(lease, handle),
        )
    if stage == "post_exec_pre_handshake":
        lifecycle = _advance(
            fixture,
            lifecycle,
            "process_exec_observed",
            _process_exec_facts(fixture, lease, handle),
        )
    lifecycle = _advance(
        fixture,
        lifecycle,
        kind,
        {
            "code": f"{stage}_{kind}",
            "message": f"Supervisor recorded {kind} during {stage}",
            "retryable": kind == "timed_out",
        },
    )
    expected_handle = None if stage == "pre_spawn" else handle
    if expected_handle is not None:
        with pytest.raises(ValueError, match="bind process handle"):
            _advance(
                fixture,
                lifecycle,
                "process_reaped",
                _reap_facts(None, termination_kind=kind),
            )
    lifecycle = _advance(
        fixture,
        lifecycle,
        "process_reaped",
        _reap_facts(
            expected_handle,
            exit_code=1,
            termination_kind=kind,
            termination_signal_sent=kind != "failed" and expected_handle is not None,
        ),
    )
    lifecycle = _finish(fixture, lifecycle)
    assert lifecycle["outcome"] == kind


def test_cancel_after_exit_before_release_is_recorded_without_cleanup_race(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    lifecycle = _normal_to_reaped(fixture)
    lifecycle = _advance(
        fixture,
        lifecycle,
        "cancelled",
        {
            "code": "cancel_after_exit",
            "message": "Supervisor cancelled before release",
            "retryable": False,
        },
    )
    lifecycle = _finish(fixture, lifecycle)

    assert lifecycle["outcome"] == "cancelled"
    assert [
        event["event_type"] for event in lifecycle["events"][-4:]
    ] == ["milestone", "termination", "milestone", "milestone"]


def test_cancel_after_release_is_too_late_for_advance_and_replay(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    lifecycle = _normal_to_reaped(fixture)
    lifecycle = _advance(
        fixture,
        lifecycle,
        "lease_released",
        _release_facts(lifecycle["resources"]["lease_sha256"]),
    )
    observation = _observation(
        fixture,
        "cancelled",
        {
            "code": "late_cancel",
            "message": "Cancellation arrived after release",
            "retryable": False,
        },
    )
    with pytest.raises(ValueError, match="after lease release"):
        advance_separation_lifecycle(
            lifecycle,
            launch_plan=fixture["plan"],
            trusted_supervisor=fixture["supervisor"],
            observation=observation,
        )

    document = _plain(lifecycle)
    termination = {
        "kind": "cancelled",
        **_plain(observation.facts),
    }
    event = {
        "sequence": len(document["events"]),
        "event_type": "termination",
        "source_state": "lease_released",
        "target_state": "lease_released",
        "outcome": "cancelled",
        "prior_state_sha256": document["lifecycle_sha256"],
        "authority_id": fixture["supervisor"].authority_id,
        "observer_sha256": fixture["supervisor"].observer_sha256,
        "facts": {},
        "termination": termination,
    }
    event["event_sha256"] = _hash_json(event)
    document.update(
        {
            "outcome": "cancelled",
            "termination": termination,
            "events": [*document["events"], event],
        }
    )
    document["lifecycle_sha256"] = _hash_json(
        {key: value for key, value in document.items() if key != "lifecycle_sha256"}
    )
    with pytest.raises(ValueError, match="termination event is not allowed"):
        validate_separation_lifecycle(
            document,
            launch_plan=fixture["plan"],
            trusted_supervisor=fixture["supervisor"],
            trusted_observations=(*lifecycle._observations, observation),
        )


def test_prestart_cancel_traverses_explicit_no_resource_cleanup_barriers(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    lifecycle = create_separation_lifecycle(
        launch_plan=fixture["plan"],
        trusted_supervisor=fixture["supervisor"],
    )
    lifecycle = _advance(
        fixture,
        lifecycle,
        "cancelled",
        {
            "code": "cancel_before_lease",
            "message": "Supervisor cancelled before launch",
            "retryable": False,
        },
    )
    lifecycle = _advance(
        fixture,
        lifecycle,
        "process_reaped",
        _reap_facts(None, termination_kind="cancelled"),
    )
    lifecycle = _advance(
        fixture, lifecycle, "lease_released", _release_facts(None)
    )
    lifecycle = _advance(fixture, lifecycle, "terminal", {})
    assert lifecycle["outcome"] == "cancelled"


def test_unvalidated_finish_branch_rejects_nonzero_exit(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    lifecycle = _normal_to_inference_finished(fixture)
    handle = lifecycle["resources"]["process_handle_sha256"]
    with pytest.raises(ValueError, match="zero exit code"):
        _advance(
            fixture,
            lifecycle,
            "process_reaped",
            _reap_facts(handle, exit_code=1),
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("wait_completed", False),
        ("observer_closed", False),
        ("process_tree_empty", False),
        (
            "cleanup_sequence",
            [
                "handle_matched",
                "wait_completed",
                "exit_observed",
                "process_reaped",
                "observer_closed",
                "process_tree_empty",
            ],
        ),
    ],
)
def test_reap_requires_handle_exit_wait_reap_observer_close_and_empty_tree(
    tmp_path: Path, field: str, replacement: Any
) -> None:
    fixture = _fixture(tmp_path)
    lifecycle = _normal_to_inference_finished(fixture)
    handle = lifecycle["resources"]["process_handle_sha256"]
    facts = _reap_facts(handle)
    facts[field] = replacement

    with pytest.raises(ValueError, match="cleanup evidence"):
        _advance(fixture, lifecycle, "process_reaped", facts)


def _hash_json(value: Any) -> str:
    import json

    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def test_hash_chain_rejects_sequence_prior_state_and_worker_claims(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    lifecycle = _normal_to_reaped(fixture)
    for mutate, message in (
        (
            lambda item: item["events"][3].__setitem__("sequence", 99),
            "sequence",
        ),
        (
            lambda item: item["events"][3].__setitem__(
                "prior_state_sha256", _sha("forged prior state")
            ),
            "prior state",
        ),
    ):
        document = _plain(lifecycle)
        mutate(document)
        with pytest.raises(ValueError, match=message):
            validate_separation_lifecycle(
                document,
                launch_plan=fixture["plan"],
                trusted_supervisor=fixture["supervisor"],
                trusted_observations=lifecycle._observations,
            )

    with pytest.raises(ValueError, match="parent-owned exact observation"):
        advance_separation_lifecycle(
            lifecycle,
            launch_plan=fixture["plan"],
            trusted_supervisor=fixture["supervisor"],
            observation={  # type: ignore[arg-type]
                "authority_id": fixture["supervisor"].authority_id,
                "observer_sha256": fixture["supervisor"].observer_sha256,
                "event": "lease_released",
                "facts": _release_facts(_sha("lease")),
            },
        )


def test_terminal_receipt_is_path_free_and_cannot_be_built_early(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    lifecycle = _normal_to_reaped(fixture)
    with pytest.raises(ValueError, match="terminal lifecycle"):
        build_separation_terminal_receipt(
            lifecycle,
            launch_plan=fixture["plan"],
            trusted_supervisor=fixture["supervisor"],
        )

    receipt = _plain(
        build_separation_terminal_receipt(
            _finish(fixture, lifecycle),
            launch_plan=fixture["plan"],
            trusted_supervisor=fixture["supervisor"],
        )
    )
    receipt["process_cleanup"]["debug_path"] = "/private/source.wav"
    with pytest.raises(ValueError, match="does not match"):
        validate_separation_terminal_receipt(
            receipt,
            lifecycle=_finish(fixture, _normal_to_reaped(fixture)),
            launch_plan=fixture["plan"],
            trusted_supervisor=fixture["supervisor"],
        )
