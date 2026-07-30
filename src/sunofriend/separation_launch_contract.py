"""Pure launch planning and supervisor-owned lifecycle evidence.

This module deliberately cannot execute a worker.  It turns an already
validated separation worker request into an exact private launch plan and
records a path-free, hash-chained lifecycle.  A later executor may implement
the plan, but it must supply parent/supervisor observations back to this
contract; worker-authored state is never accepted as lifecycle authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .separation_runtime_artifact import (
    SeparationRuntimeArtifactParentEvidence,
    validate_separation_runtime_artifact,
)
from .separation_worker_contract import (
    SEPARATION_WORKER_ISOLATION_POLICY,
    validate_separation_worker_request,
)


REAL_WORKER_EXECUTION_SUPPORTED = False

SEPARATION_LAUNCH_PLAN_SCHEMA = "sunofriend.separation-launch-plan.v1"
SEPARATION_LIFECYCLE_SCHEMA = "sunofriend.separation-launch-lifecycle.v1"
SEPARATION_TERMINAL_RECEIPT_SCHEMA = (
    "sunofriend.separation-launch-terminal-receipt.v1"
)
SEPARATION_LAUNCH_POLICY_ID = "private-development-launch-v1"
SEPARATION_DESCRIPTOR_POLICY_ID = "sealed-control-descriptors-v1"

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._+:-]{0,191}$")
_URL_RE = re.compile(r"(?:[A-Za-z][A-Za-z0-9+.-]*://|www\.)")
_WINDOWS_RE = re.compile(r"^[A-Za-z]:[\\/]")

_STATES = (
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
)
_UNVALIDATED_FINISH = "execution_finished_unvalidated"
_OUTCOMES = frozenset(
    {"running", _UNVALIDATED_FINISH, "cancelled", "failed", "timed_out"}
)
_TERMINATIONS = frozenset({"cancelled", "failed", "timed_out"})
_RESOURCE_EVENTS = frozenset({"process_handle_acquired", "process_exec_observed"})
_MAX_EVENTS = 64
_MAX_EVENT_BYTES = 16_384
_MAX_LIFECYCLE_BYTES = 262_144
_MAX_MESSAGE_CHARACTERS = 1_024

_ENVIRONMENT = {
    "HOME": "/private/var/empty",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "NO_PROXY": "*",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONHASHSEED": "0",
    "PYTHONNOUSERSITE": "1",
    "TZ": "UTC",
}
_DESCRIPTOR_POLICY = {
    "policy_id": SEPARATION_DESCRIPTOR_POLICY_ID,
    "inherit_unlisted_descriptors": False,
    "descriptors": [
        {"descriptor": 0, "purpose": "null_read", "direction": "parent_to_worker"},
        {
            "descriptor": 1,
            "purpose": "bounded_stdout_capture",
            "direction": "worker_to_parent",
            "maximum_bytes": 1_048_576,
        },
        {
            "descriptor": 2,
            "purpose": "bounded_stderr_capture",
            "direction": "worker_to_parent",
            "maximum_bytes": 1_048_576,
        },
        {
            "descriptor": 3,
            "purpose": "sealed_canonical_worker_request",
            "direction": "parent_to_worker",
            "maximum_bytes": 1_048_576,
        },
        {
            "descriptor": 4,
            "purpose": "bounded_worker_result",
            "direction": "worker_to_parent",
            "maximum_bytes": 16_777_216,
        },
    ],
}
_PRIVATE_ISOLATION_TEMPLATE = {
    "policy_id": SEPARATION_LAUNCH_POLICY_ID,
    "worker_isolation_policy_id": SEPARATION_WORKER_ISOLATION_POLICY,
    "evidence_scope": "private_development",
    "network": "deny",
    "child_processes": "deny",
    "source_checkpoint_worker_runtime_lock": "read_only",
    "output": "request_allowlist_only",
    "environment": "replace_with_exact_allowlist",
    "descriptors": SEPARATION_DESCRIPTOR_POLICY_ID,
    "observer": "parent_supervisor_only",
    "publication": "none",
}

SEPARATION_LAUNCH_ENVIRONMENT_SHA256 = ""
SEPARATION_DESCRIPTOR_POLICY_SHA256 = ""
SEPARATION_PRIVATE_ISOLATION_TEMPLATE_SHA256 = ""


@dataclass(frozen=True)
class SeparationSupervisorAuthority:
    """Parent-owned authority that may attest lifecycle observations."""

    authority_id: str
    observer_id: str
    observer_sha256: str

    def __post_init__(self) -> None:
        _identifier(self.authority_id, "authority id")
        _identifier(self.observer_id, "observer id")
        _sha(self.observer_sha256, "observer sha256")


@dataclass(frozen=True)
class SeparationSupervisorObservation:
    """One parent-observed milestone or termination request."""

    authority_id: str
    observer_sha256: str
    event: str
    facts: Mapping[str, Any]

    def __post_init__(self) -> None:
        _identifier(self.authority_id, "observation authority id")
        _sha(self.observer_sha256, "observation observer sha256")
        _identifier(self.event, "observation event")
        facts = _json_object(self.facts, "observation facts")
        _path_free(facts, "observation facts")
        object.__setattr__(self, "facts", _freeze(facts))


@dataclass(frozen=True, init=False)
class SeparationLaunchPlanRecord(Mapping[str, Any]):
    """A fully validated parent-owned launch plan, not arbitrary plan JSON."""

    _document: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


@dataclass(frozen=True, init=False)
class SeparationLifecycleRecord(Mapping[str, Any]):
    """Validated public state plus a non-serialized supervisor ledger."""

    _document: Mapping[str, Any]
    _observations: tuple[SeparationSupervisorObservation, ...]

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


def _static_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


SEPARATION_LAUNCH_ENVIRONMENT_SHA256 = _static_hash(_ENVIRONMENT)
SEPARATION_DESCRIPTOR_POLICY_SHA256 = _static_hash(_DESCRIPTOR_POLICY)
SEPARATION_PRIVATE_ISOLATION_TEMPLATE_SHA256 = _static_hash(
    _PRIVATE_ISOLATION_TEMPLATE
)


def build_separation_launch_plan(
    *,
    worker_request: Mapping[str, Any],
    trusted_preflight: Mapping[str, Any],
    trusted_acceptance: Mapping[str, Any],
    trusted_separation_request: Any,
    trusted_runtime_artifact: Any,
    runtime_artifact: Mapping[str, Any],
    trusted_runtime_parent_evidence: SeparationRuntimeArtifactParentEvidence,
) -> Mapping[str, Any]:
    """Build the only supported, exact, non-executing launch plan."""

    request = _trusted_worker_request(
        worker_request=worker_request,
        trusted_preflight=trusted_preflight,
        trusted_acceptance=trusted_acceptance,
        trusted_separation_request=trusted_separation_request,
        trusted_runtime_artifact=trusted_runtime_artifact,
    )
    runtime = _trusted_runtime_record(
        runtime_artifact=runtime_artifact,
        trusted_runtime_artifact=trusted_runtime_artifact,
        trusted_runtime_parent_evidence=trusted_runtime_parent_evidence,
        request=request,
    )
    payload = _expected_launch_payload(request, runtime)
    return _new_plan_record({**payload, "plan_sha256": _hash(payload)})


def validate_separation_launch_plan(
    document: Mapping[str, Any],
    *,
    worker_request: Mapping[str, Any],
    trusted_preflight: Mapping[str, Any],
    trusted_acceptance: Mapping[str, Any],
    trusted_separation_request: Any,
    trusted_runtime_artifact: Any,
    runtime_artifact: Mapping[str, Any],
    trusted_runtime_parent_evidence: SeparationRuntimeArtifactParentEvidence,
) -> Mapping[str, Any]:
    """Validate every plan value against trusted request and code-owned policy."""

    request = _trusted_worker_request(
        worker_request=worker_request,
        trusted_preflight=trusted_preflight,
        trusted_acceptance=trusted_acceptance,
        trusted_separation_request=trusted_separation_request,
        trusted_runtime_artifact=trusted_runtime_artifact,
    )
    value = _json_object(document, "launch plan")
    runtime = _trusted_runtime_record(
        runtime_artifact=runtime_artifact,
        trusted_runtime_artifact=trusted_runtime_artifact,
        trusted_runtime_parent_evidence=trusted_runtime_parent_evidence,
        request=request,
    )
    expected = _expected_launch_payload(request, runtime)
    _fields(value, set(expected) | {"plan_sha256"}, "launch plan")
    if {key: value[key] for key in expected} != expected:
        raise ValueError("launch plan does not match trusted exact policy")
    if _sha(value["plan_sha256"], "launch plan sha256") != _hash(expected):
        raise ValueError("launch plan hash is invalid")
    return _new_plan_record(value)


def separation_launch_plan_sha256(document: Mapping[str, Any]) -> str:
    value = _json_object(document, "launch plan")
    value.pop("plan_sha256", None)
    return _hash(value)


def create_separation_lifecycle(
    *,
    launch_plan: Mapping[str, Any],
    trusted_supervisor: SeparationSupervisorAuthority,
) -> Mapping[str, Any]:
    """Create a path-free lifecycle whose first state is ``planned``."""

    plan = _basic_plan(launch_plan)
    supervisor = _trusted_supervisor(trusted_supervisor, plan)
    base = _lifecycle_base(plan, supervisor)
    prior = _lifecycle_hash(
        base=base,
        current_state=None,
        outcome="running",
        resources=_empty_resources(),
        termination=None,
        events=[],
    )
    event = _event(
        sequence=0,
        event_type="milestone",
        source_state=None,
        target_state="planned",
        outcome="running",
        prior_state_sha256=prior,
        authority=supervisor,
        facts={},
        termination=None,
    )
    payload = {
        **base,
        "current_state": "planned",
        "outcome": "running",
        "resources": _empty_resources(),
        "termination": None,
        "events": [event],
    }
    return validate_separation_lifecycle(
        {**payload, "lifecycle_sha256": _hash(payload)},
        launch_plan=plan,
        trusted_supervisor=supervisor,
        trusted_observations=(),
    )


def advance_separation_lifecycle(
    lifecycle: Mapping[str, Any],
    *,
    launch_plan: Mapping[str, Any],
    trusted_supervisor: SeparationSupervisorAuthority,
    observation: SeparationSupervisorObservation,
) -> Mapping[str, Any]:
    """Apply one supervisor-observed milestone; this never performs the action."""

    plan = _basic_plan(launch_plan)
    supervisor = _trusted_supervisor(trusted_supervisor, plan)
    current = validate_separation_lifecycle(
        lifecycle,
        launch_plan=plan,
        trusted_supervisor=supervisor,
        trusted_observations=_trusted_lifecycle_observations(lifecycle),
    )
    observed = _trusted_observation(observation, supervisor)
    if observed.event in _TERMINATIONS:
        return _record_termination(current, plan, supervisor, observed)
    if observed.event in _RESOURCE_EVENTS:
        return _record_resource(current, plan, supervisor, observed)
    if current["current_state"] == "terminal":
        raise ValueError("terminal lifecycle cannot advance")
    target = observed.event
    if target not in _STATES or target == "planned":
        raise ValueError("observation is not a lifecycle milestone")
    source = current["current_state"]
    termination = _thaw(current["termination"])
    expected = _next_milestone(source, termination is not None)
    if target != expected:
        raise ValueError(f"expected lifecycle milestone {expected}")
    resources = _thaw(current["resources"])
    facts = _validate_milestone_facts(
        target=target,
        facts=_thaw(observed.facts),
        plan=plan,
        resources=resources,
        termination=termination,
    )
    resources = _apply_resources(target, facts, resources)
    outcome = current["outcome"]
    if target == "terminal":
        outcome = (
            termination["kind"] if termination is not None else _UNVALIDATED_FINISH
        )
    event = _event(
        sequence=len(current["events"]),
        event_type="milestone",
        source_state=source,
        target_state=target,
        outcome=outcome,
        prior_state_sha256=current["lifecycle_sha256"],
        authority=supervisor,
        facts=facts,
        termination=None,
    )
    payload = {
        **_lifecycle_base(plan, supervisor),
        "current_state": target,
        "outcome": outcome,
        "resources": resources,
        "termination": termination,
        "events": [*_thaw(current["events"]), event],
    }
    observations = (*_trusted_lifecycle_observations(current), observed)
    return validate_separation_lifecycle(
        {**payload, "lifecycle_sha256": _hash(payload)},
        launch_plan=plan,
        trusted_supervisor=supervisor,
        trusted_observations=observations,
    )


def validate_separation_lifecycle(
    document: Mapping[str, Any],
    *,
    launch_plan: Mapping[str, Any],
    trusted_supervisor: SeparationSupervisorAuthority,
    trusted_observations: Sequence[SeparationSupervisorObservation] | None = None,
) -> SeparationLifecycleRecord:
    """Replay and validate the complete parent-owned hash chain."""

    plan = _basic_plan(launch_plan)
    supervisor = _trusted_supervisor(trusted_supervisor, plan)
    if trusted_observations is None:
        trusted_observations = _trusted_lifecycle_observations(document)
    observations = _observation_ledger(trusted_observations, supervisor)
    value = _json_object(document, "launch lifecycle")
    _fields(
        value,
        {
            "schema",
            "lifecycle_sha256",
            "launch_plan_sha256",
            "worker_request_sha256",
            "supervisor",
            "current_state",
            "outcome",
            "resources",
            "termination",
            "events",
        },
        "launch lifecycle",
    )
    base = _lifecycle_base(plan, supervisor)
    if any(value[key] != expected for key, expected in base.items()):
        raise ValueError("lifecycle does not bind launch plan and supervisor")
    events = value["events"]
    if not isinstance(events, list) or not events or len(events) > _MAX_EVENTS:
        raise ValueError("lifecycle events must be a non-empty array")
    if len(observations) != len(events) - 1:
        raise ValueError("serialized lifecycle does not bind supervisor ledger")

    state: str | None = None
    outcome = "running"
    resources = _empty_resources()
    termination: dict[str, Any] | None = None
    prior_events: list[dict[str, Any]] = []
    prior_hash = _lifecycle_hash(
        base=base,
        current_state=state,
        outcome=outcome,
        resources=resources,
        termination=termination,
        events=prior_events,
    )
    for sequence, raw_event in enumerate(events):
        event = _validate_event(
            raw_event,
            sequence=sequence,
            prior_state_sha256=prior_hash,
            authority=supervisor,
        )
        if sequence:
            _bind_event_to_observation(event, observations[sequence - 1])
        state, outcome, resources, termination = _replay_event(
            event=event,
            state=state,
            outcome=outcome,
            resources=resources,
            termination=termination,
            plan=plan,
        )
        prior_events.append(event)
        prior_hash = _lifecycle_hash(
            base=base,
            current_state=state,
            outcome=outcome,
            resources=resources,
            termination=termination,
            events=prior_events,
        )

    if (
        value["current_state"] != state
        or value["outcome"] != outcome
        or value["resources"] != resources
        or value["termination"] != termination
    ):
        raise ValueError("lifecycle summary contradicts replayed events")
    if state not in _STATES or outcome not in _OUTCOMES:
        raise ValueError("lifecycle state or outcome is invalid")
    _path_free(value, "launch lifecycle")
    if _sha(value["lifecycle_sha256"], "lifecycle sha256") != prior_hash:
        raise ValueError("lifecycle hash is invalid")
    if len(_canonical_json(value)) > _MAX_LIFECYCLE_BYTES:
        raise ValueError("lifecycle exceeds supported size")
    return _new_lifecycle_record(value, observations)


def build_separation_terminal_receipt(
    lifecycle: Mapping[str, Any],
    *,
    launch_plan: Mapping[str, Any],
    trusted_supervisor: SeparationSupervisorAuthority,
) -> Mapping[str, Any]:
    """Derive a path-free cleanup receipt; it contains no acceptance claim."""

    plan = _basic_plan(launch_plan)
    supervisor = _trusted_supervisor(trusted_supervisor, plan)
    checked = validate_separation_lifecycle(
        lifecycle,
        launch_plan=plan,
        trusted_supervisor=supervisor,
        trusted_observations=_trusted_lifecycle_observations(lifecycle),
    )
    if checked["current_state"] != "terminal":
        raise ValueError("terminal receipt requires terminal lifecycle")
    reap = _latest_milestone(checked["events"], "process_reaped")
    release = _latest_milestone(checked["events"], "lease_released")
    payload = {
        "schema": SEPARATION_TERMINAL_RECEIPT_SCHEMA,
        "launch_plan_sha256": plan["plan_sha256"],
        "worker_request_sha256": plan["worker_request_sha256"],
        "lifecycle_sha256": checked["lifecycle_sha256"],
        "terminal_outcome": checked["outcome"],
        "result_boundary": {
            "scope": "launch_cleanup_only",
            "task_success_proven": False,
            "worker_result_validated": False,
            "post_input_immutability_verified": False,
            "parent_outputs_verified": False,
            "outputs_quarantined": False,
            "publication_permitted": False,
            "acceptance_eligible": False,
            "promotion_eligible": False,
        },
        "event_count": len(checked["events"]),
        "last_event_sha256": checked["events"][-1]["event_sha256"],
        "supervisor": _thaw(checked["supervisor"]),
        "process_cleanup": _thaw(reap["facts"]),
        "lease_cleanup": _thaw(release["facts"]),
        "termination": _thaw(checked["termination"]),
    }
    return _freeze({**payload, "receipt_sha256": _hash(payload)})


def validate_separation_terminal_receipt(
    document: Mapping[str, Any],
    *,
    lifecycle: Mapping[str, Any],
    launch_plan: Mapping[str, Any],
    trusted_supervisor: SeparationSupervisorAuthority,
) -> Mapping[str, Any]:
    expected = build_separation_terminal_receipt(
        lifecycle,
        launch_plan=launch_plan,
        trusted_supervisor=trusted_supervisor,
    )
    value = _json_object(document, "terminal receipt")
    if value != _thaw(expected):
        raise ValueError("terminal receipt does not match trusted lifecycle")
    _path_free(value, "terminal receipt")
    return _freeze(value)


def _expected_launch_payload(
    request: Mapping[str, Any], runtime_artifact: Mapping[str, Any]
) -> dict[str, Any]:
    isolation = request["isolation"]
    expected_hashes = {
        "environment_sha256": SEPARATION_LAUNCH_ENVIRONMENT_SHA256,
        "file_descriptor_policy_sha256": SEPARATION_DESCRIPTOR_POLICY_SHA256,
        "profile_sha256": SEPARATION_PRIVATE_ISOLATION_TEMPLATE_SHA256,
    }
    if any(isolation[key] != expected for key, expected in expected_hashes.items()):
        raise ValueError("worker request isolation does not bind exact launch policy")
    paths = request["paths"]
    argv = [
        paths["runtime_python_path"],
        "-I",
        "-B",
        paths["worker_path"],
        "--request-fd",
        "3",
        "--result-fd",
        "4",
    ]
    descriptor_policy = _descriptor_policy_for(request)
    process_policy = {
        "shell": False,
        "path_search": False,
        "close_fds": True,
        "pass_fds": [3, 4],
        "working_directory": "/private/var/empty",
        "start_new_session": True,
        "process_group": "new_session",
        "umask": "077",
        "timeout_seconds": 3_600,
        "termination_grace_seconds": 5,
        "termination_sequence": [
            "request_termination",
            "observe_grace_period",
            "check_process_group",
            "kill_process_group_if_running",
            "wait_and_reap",
        ],
    }
    output_staging = {
        "root_path": request["paths"]["output_dir"],
        "directory_mode": "0700",
        "file_mode": "0600",
        "overwrite": False,
        "publication": "none",
        "allowlist": _thaw(request["output_allowlist"]),
    }
    runtime = request["identities"]["runtime"]
    return {
        "schema": SEPARATION_LAUNCH_PLAN_SCHEMA,
        "real_worker_execution_supported": REAL_WORKER_EXECUTION_SUPPORTED,
        "worker_request_sha256": request["request_sha256"],
        "preflight_id": request["preflight"]["preflight_id"],
        "preflight_sha256": request["preflight"]["preflight_sha256"],
        "separation_request_fingerprint_sha256": request[
            "separation_request_fingerprint_sha256"
        ],
        "argv": argv,
        "argv_sha256": _hash_array(argv),
        "environment": {
            "inherit_parent": False,
            "values": dict(_ENVIRONMENT),
            "sha256": SEPARATION_LAUNCH_ENVIRONMENT_SHA256,
        },
        "descriptor_policy": {
            "value": descriptor_policy,
            "template_sha256": SEPARATION_DESCRIPTOR_POLICY_SHA256,
            "sha256": _hash(descriptor_policy),
        },
        "isolation_template": {
            "value": _thaw(_PRIVATE_ISOLATION_TEMPLATE),
            "sha256": SEPARATION_PRIVATE_ISOLATION_TEMPLATE_SHA256,
        },
        "process_policy": {
            "value": process_policy,
            "sha256": _hash(process_policy),
        },
        "output_staging": {
            "value": output_staging,
            "sha256": _hash(output_staging),
        },
        "identity_bindings": {
            "source_sha256": request["identities"]["source"]["canonical_sha256"],
            "checkpoint_sha256": request["identities"]["checkpoint"]["sha256"],
            "worker_sha256": request["identities"]["worker"]["sha256"],
            "runtime_sha256": request["identities"]["runtime"]["sha256"],
            "runtime_launcher_chain_sha256": runtime[
                "verified_launcher_chain_sha256"
            ],
            "runtime_artifact_sha256": runtime_artifact["artifact_sha256"],
            "runtime_parent_measurements_sha256": runtime_artifact["bindings"][
                "parent_measurements_sha256"
            ],
            "dependency_lock_sha256": request["identities"]["dependency_lock"][
                "sha256"
            ],
            "observer_id": request["isolation"]["observer_id"],
            "observer_sha256": request["isolation"]["observer_sha256"],
        },
    }


def _descriptor_policy_for(request: Mapping[str, Any]) -> dict[str, Any]:
    policy = _thaw(_DESCRIPTOR_POLICY)
    identities = {
        0: _static_hash({"purpose": "null_read"}),
        1: _static_hash({"purpose": "bounded_stdout_capture", "maximum": 1_048_576}),
        2: _static_hash({"purpose": "bounded_stderr_capture", "maximum": 1_048_576}),
        3: request["request_sha256"],
        4: _static_hash(
            {
                "purpose": "bounded_worker_result",
                "worker_request_sha256": request["request_sha256"],
                "maximum": 16_777_216,
            }
        ),
    }
    for item in policy["descriptors"]:
        item["identity_sha256"] = identities[item["descriptor"]]
    return policy


def _trusted_worker_request(**values: Any) -> Mapping[str, Any]:
    document = values["worker_request"]
    trusted = {key: item for key, item in values.items() if key != "worker_request"}
    return validate_separation_worker_request(document, **trusted)


def _trusted_runtime_record(
    *,
    runtime_artifact: Mapping[str, Any],
    trusted_runtime_artifact: Any,
    trusted_runtime_parent_evidence: SeparationRuntimeArtifactParentEvidence,
    request: Mapping[str, Any],
) -> Mapping[str, Any]:
    checked = validate_separation_runtime_artifact(
        runtime_artifact,
        trusted_runtime_artifact=trusted_runtime_artifact,
        trusted_parent_evidence=trusted_runtime_parent_evidence,
        trusted_worker_request_sha256=request["request_sha256"],
        trusted_preflight_sha256=request["preflight"]["preflight_sha256"],
    )
    identities = request["identities"]
    runtime_identity = checked["bindings"]["trusted_runtime_identity"]
    expected_runtime = identities["runtime"]
    if (
        runtime_identity["sha256"] != expected_runtime["sha256"]
        or runtime_identity["bytes"] != expected_runtime["bytes"]
        or runtime_identity["verified_launcher_chain_sha256"]
        != expected_runtime["verified_launcher_chain_sha256"]
        or checked["files"]["worker"]["sha256"]
        != identities["worker"]["sha256"]
        or checked["files"]["worker"]["bytes"] != identities["worker"]["bytes"]
        or checked["files"]["worker"]["path"] != request["paths"]["worker_path"]
        or checked["files"]["dependency_lock"]["sha256"]
        != identities["dependency_lock"]["sha256"]
        or checked["files"]["dependency_lock"]["bytes"]
        != identities["dependency_lock"]["bytes"]
        or checked["files"]["dependency_lock"]["path"]
        != request["paths"]["dependency_lock_path"]
    ):
        raise ValueError("runtime artifact does not bind worker request identities")
    return checked


def _new_plan_record(document: Mapping[str, Any]) -> SeparationLaunchPlanRecord:
    record = object.__new__(SeparationLaunchPlanRecord)
    object.__setattr__(record, "_document", _freeze(_json_object(document, "launch plan")))
    return record


def _new_lifecycle_record(
    document: Mapping[str, Any],
    observations: Sequence[SeparationSupervisorObservation],
) -> SeparationLifecycleRecord:
    record = object.__new__(SeparationLifecycleRecord)
    object.__setattr__(
        record,
        "_document",
        _freeze(_json_object(document, "launch lifecycle")),
    )
    object.__setattr__(record, "_observations", tuple(observations))
    return record


def _trusted_lifecycle_observations(
    value: Any,
) -> tuple[SeparationSupervisorObservation, ...]:
    if type(value) is not SeparationLifecycleRecord:
        raise ValueError("lifecycle must be a parent-owned validated record")
    return value._observations


def _observation_ledger(
    values: Sequence[SeparationSupervisorObservation],
    authority: SeparationSupervisorAuthority,
) -> tuple[SeparationSupervisorObservation, ...]:
    if not isinstance(values, (list, tuple)) or len(values) >= _MAX_EVENTS:
        raise ValueError("supervisor observation ledger is invalid")
    return tuple(_trusted_observation(value, authority) for value in values)


def _bind_event_to_observation(
    event: Mapping[str, Any], observation: SeparationSupervisorObservation
) -> None:
    if event["event_type"] == "termination":
        expected = {
            "kind": observation.event,
            **_termination_facts(observation.event, _thaw(observation.facts)),
        }
        if (
            event["target_state"] != event["source_state"]
            or event["facts"] != {}
            or event["termination"] != expected
        ):
            raise ValueError("serialized termination does not bind supervisor ledger")
    elif event["event_type"] == "resource":
        if (
            event["target_state"] != observation.event
            or event["facts"] != _thaw(observation.facts)
            or event["termination"] is not None
        ):
            raise ValueError("serialized resource does not bind supervisor ledger")
    elif (
        event["event_type"] != "milestone"
        or event["target_state"] != observation.event
        or event["facts"] != _thaw(observation.facts)
        or event["termination"] is not None
    ):
        raise ValueError("serialized milestone does not bind supervisor ledger")


def _basic_plan(document: Mapping[str, Any]) -> Mapping[str, Any]:
    if type(document) is not SeparationLaunchPlanRecord:
        raise ValueError("launch plan must be a parent-owned validated plan")
    value = _json_object(document, "launch plan")
    if value.get("schema") != SEPARATION_LAUNCH_PLAN_SCHEMA:
        raise ValueError("unsupported launch plan schema")
    if value.get("real_worker_execution_supported") is not False:
        raise ValueError("launch plan cannot claim execution support")
    if separation_launch_plan_sha256(value) != value.get("plan_sha256"):
        raise ValueError("launch plan hash is invalid")
    if (
        value.get("environment")
        != {
            "inherit_parent": False,
            "values": _ENVIRONMENT,
            "sha256": SEPARATION_LAUNCH_ENVIRONMENT_SHA256,
        }
        or value.get("isolation_template")
        != {
            "value": _PRIVATE_ISOLATION_TEMPLATE,
            "sha256": SEPARATION_PRIVATE_ISOLATION_TEMPLATE_SHA256,
        }
    ):
        raise ValueError("launch plan code-owned policy is invalid")
    descriptors = value.get("descriptor_policy")
    if (
        not isinstance(descriptors, dict)
        or descriptors.get("template_sha256")
        != SEPARATION_DESCRIPTOR_POLICY_SHA256
        or descriptors.get("sha256") != _hash(descriptors.get("value", {}))
    ):
        raise ValueError("launch plan descriptor policy is invalid")
    argv = value.get("argv")
    if not isinstance(argv, list) or value.get("argv_sha256") != _hash_array(argv):
        raise ValueError("launch plan argv hash is invalid")
    for key in ("process_policy", "output_staging"):
        item = value.get(key)
        if (
            not isinstance(item, dict)
            or item.get("sha256") != _hash(item.get("value", {}))
        ):
            raise ValueError(f"launch plan {key} hash is invalid")
    return document


def _trusted_supervisor(
    value: Any, plan: Mapping[str, Any]
) -> SeparationSupervisorAuthority:
    if type(value) is not SeparationSupervisorAuthority:
        raise ValueError("supervisor must be a parent-owned exact authority")
    bindings = plan["identity_bindings"]
    if (
        value.observer_id != bindings["observer_id"]
        or value.observer_sha256 != bindings["observer_sha256"]
    ):
        raise ValueError("supervisor does not bind launch observer")
    return value


def _trusted_observation(
    value: Any, authority: SeparationSupervisorAuthority
) -> SeparationSupervisorObservation:
    if type(value) is not SeparationSupervisorObservation:
        raise ValueError("observation must be a parent-owned exact observation")
    if (
        value.authority_id != authority.authority_id
        or value.observer_sha256 != authority.observer_sha256
    ):
        raise ValueError("observation does not bind supervisor")
    return value


def _lifecycle_base(
    plan: Mapping[str, Any], authority: SeparationSupervisorAuthority
) -> dict[str, Any]:
    return {
        "schema": SEPARATION_LIFECYCLE_SCHEMA,
        "launch_plan_sha256": plan["plan_sha256"],
        "worker_request_sha256": plan["worker_request_sha256"],
        "supervisor": {
            "authority_id": authority.authority_id,
            "observer_id": authority.observer_id,
            "observer_sha256": authority.observer_sha256,
        },
    }


def _record_termination(
    current: Mapping[str, Any],
    plan: Mapping[str, Any],
    supervisor: SeparationSupervisorAuthority,
    observed: SeparationSupervisorObservation,
) -> Mapping[str, Any]:
    if current["current_state"] in {"lease_released", "terminal"}:
        raise ValueError("lifecycle cannot accept termination after lease release")
    if current["termination"] is not None:
        raise ValueError("termination has already been recorded")
    facts = _termination_facts(observed.event, _thaw(observed.facts))
    termination = {"kind": observed.event, **facts}
    event = _event(
        sequence=len(current["events"]),
        event_type="termination",
        source_state=current["current_state"],
        target_state=current["current_state"],
        outcome=observed.event,
        prior_state_sha256=current["lifecycle_sha256"],
        authority=supervisor,
        facts={},
        termination=termination,
    )
    payload = {
        **_lifecycle_base(plan, supervisor),
        "current_state": current["current_state"],
        "outcome": observed.event,
        "resources": _thaw(current["resources"]),
        "termination": termination,
        "events": [*_thaw(current["events"]), event],
    }
    observations = (*_trusted_lifecycle_observations(current), observed)
    return validate_separation_lifecycle(
        {**payload, "lifecycle_sha256": _hash(payload)},
        launch_plan=plan,
        trusted_supervisor=supervisor,
        trusted_observations=observations,
    )


def _record_resource(
    current: Mapping[str, Any],
    plan: Mapping[str, Any],
    supervisor: SeparationSupervisorAuthority,
    observed: SeparationSupervisorObservation,
) -> Mapping[str, Any]:
    if current["current_state"] != "lease_acquired" or current["termination"] is not None:
        raise ValueError("process resource observation is not allowed in this state")
    resources = _thaw(current["resources"])
    facts = _validate_resource_facts(
        event=observed.event,
        facts=_thaw(observed.facts),
        plan=plan,
        resources=resources,
    )
    if observed.event == "process_handle_acquired":
        resources["process_handle_sha256"] = facts["process_handle_sha256"]
    else:
        resources["exec_observed"] = True
    event = _event(
        sequence=len(current["events"]),
        event_type="resource",
        source_state="lease_acquired",
        target_state=observed.event,
        outcome="running",
        prior_state_sha256=current["lifecycle_sha256"],
        authority=supervisor,
        facts=facts,
        termination=None,
    )
    payload = {
        **_lifecycle_base(plan, supervisor),
        "current_state": "lease_acquired",
        "outcome": "running",
        "resources": resources,
        "termination": None,
        "events": [*_thaw(current["events"]), event],
    }
    observations = (*_trusted_lifecycle_observations(current), observed)
    return validate_separation_lifecycle(
        {**payload, "lifecycle_sha256": _hash(payload)},
        launch_plan=plan,
        trusted_supervisor=supervisor,
        trusted_observations=observations,
    )


def _next_milestone(state: str, terminating: bool) -> str:
    if terminating:
        if _STATES.index(state) < _STATES.index("process_reaped"):
            return "process_reaped"
        if state == "process_reaped":
            return "lease_released"
        if state == "lease_released":
            return "terminal"
        raise ValueError("termination cleanup state is invalid")
    index = _STATES.index(state)
    if index + 1 >= len(_STATES):
        raise ValueError("terminal lifecycle cannot advance")
    return _STATES[index + 1]


def _validate_milestone_facts(
    *,
    target: str,
    facts: Mapping[str, Any],
    plan: Mapping[str, Any],
    resources: Mapping[str, Any],
    termination: Mapping[str, Any] | None,
) -> dict[str, Any]:
    facts = _json_object(facts, f"{target} facts")
    if target == "lease_acquired":
        _fields(facts, {"lease_sha256"}, "lease acquired facts")
        _sha(facts["lease_sha256"], "lease sha256")
    elif target == "process_started":
        facts = _process_launch_facts(
            facts=facts,
            plan=plan,
            resources=resources,
            handshake=True,
        )
        if resources["exec_observed"] is not True:
            raise ValueError("process start requires prior exec observation")
    elif target == "checkpoint_verified":
        _fields(
            facts,
            {"process_handle_sha256", "checkpoint_sha256"},
            "checkpoint verified facts",
        )
        _process_binding(facts, resources)
        if facts["checkpoint_sha256"] != plan["identity_bindings"][
            "checkpoint_sha256"
        ]:
            raise ValueError("checkpoint observation does not bind launch identity")
    elif target == "model_loaded":
        _fields(
            facts,
            {"process_handle_sha256", "checkpoint_sha256"},
            "model loaded facts",
        )
        _process_binding(facts, resources)
        if facts["checkpoint_sha256"] != plan["identity_bindings"][
            "checkpoint_sha256"
        ]:
            raise ValueError("model load does not bind verified checkpoint")
    elif target in {"inference_started", "inference_finished"}:
        _fields(
            facts,
            {"process_handle_sha256", "worker_request_sha256"},
            f"{target} facts",
        )
        _process_binding(facts, resources)
        if facts["worker_request_sha256"] != plan["worker_request_sha256"]:
            raise ValueError("inference observation does not bind worker request")
    elif target == "process_reaped":
        facts = _reap_facts(facts, resources, termination)
    elif target == "lease_released":
        facts = _release_facts(facts, resources)
    elif target == "terminal":
        _fields(facts, set(), "terminal facts")
    else:
        raise ValueError("unsupported lifecycle milestone")
    _path_free(facts, f"{target} facts")
    return facts


def _validate_resource_facts(
    *,
    event: str,
    facts: Mapping[str, Any],
    plan: Mapping[str, Any],
    resources: Mapping[str, Any],
) -> dict[str, Any]:
    facts = _json_object(facts, f"{event} facts")
    if event == "process_handle_acquired":
        _fields(
            facts,
            {"lease_sha256", "process_handle_sha256", "handle_kind"},
            "process handle facts",
        )
        if resources["process_handle_sha256"] is not None:
            raise ValueError("process handle has already been acquired")
        if facts["lease_sha256"] != resources["lease_sha256"]:
            raise ValueError("process handle does not bind acquired lease")
        _sha(facts["process_handle_sha256"], "process handle sha256")
        if facts["handle_kind"] != "parent_supervised_process":
            raise ValueError("process handle kind is invalid")
    elif event == "process_exec_observed":
        if resources["exec_observed"] is True:
            raise ValueError("process exec has already been observed")
        facts = _process_launch_facts(
            facts=facts,
            plan=plan,
            resources=resources,
            handshake=False,
        )
    else:
        raise ValueError("process resource event is invalid")
    _path_free(facts, f"{event} facts")
    return facts


def _process_launch_facts(
    *,
    facts: Mapping[str, Any],
    plan: Mapping[str, Any],
    resources: Mapping[str, Any],
    handshake: bool,
) -> dict[str, Any]:
    facts = _json_object(facts, "process launch facts")
    expected = {
        "lease_sha256": resources["lease_sha256"],
        "process_handle_sha256": resources["process_handle_sha256"],
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
        "worker_handshake_sha256": (
            plan["worker_request_sha256"] if handshake else None
        ),
        "handshake_observed": handshake,
    }
    _fields(facts, set(expected), "process launch facts")
    if resources["process_handle_sha256"] is None:
        raise ValueError("process launch requires parent-owned process handle")
    if any(facts[key] != value for key, value in expected.items()):
        raise ValueError("process start does not bind exact observed launch")
    return facts


def _reap_facts(
    facts: dict[str, Any],
    resources: Mapping[str, Any],
    termination: Mapping[str, Any] | None,
) -> dict[str, Any]:
    expected = {
        "process_handle_sha256",
        "reap_disposition",
        "exit_code",
        "cleanup_sequence",
        "exit_observed",
        "wait_completed",
        "process_reaped",
        "observer_closed",
        "process_tree_empty",
        "termination_kind",
        "termination_signal_sent",
        "kill_escalation_sent",
        "termination_cleanup_sequence",
    }
    _fields(facts, expected, "process reaped facts")
    handle = resources["process_handle_sha256"]
    if facts["process_handle_sha256"] != handle:
        raise ValueError("reap observation does not bind process handle")
    if handle is None:
        required = {
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
            "termination_kind": termination["kind"] if termination else None,
            "termination_signal_sent": False,
            "kill_escalation_sent": False,
            "termination_cleanup_sequence": (
                ["not_started"] if termination else []
            ),
        }
    else:
        _sha(handle, "process handle sha256")
        exit_code = facts["exit_code"]
        if type(exit_code) is not int or not -255 <= exit_code <= 255:
            raise ValueError("exit code is invalid")
        signal_sent = facts["termination_signal_sent"]
        kill_sent = facts["kill_escalation_sent"]
        if not isinstance(signal_sent, bool) or not isinstance(kill_sent, bool):
            raise ValueError("termination signal evidence must be boolean")
        if kill_sent and not signal_sent:
            raise ValueError("kill escalation cannot precede termination signal")
        if termination:
            termination_sequence = (
                [
                    "termination_recorded",
                    "process_group_signalled",
                    "grace_period_observed",
                    "kill_escalation_checked",
                ]
                if signal_sent
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
        required = {
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
            "termination_kind": termination["kind"] if termination else None,
            "termination_signal_sent": signal_sent,
            "kill_escalation_sent": kill_sent,
            "termination_cleanup_sequence": termination_sequence,
        }
        if termination is None and (signal_sent or kill_sent):
            raise ValueError("normal reap cannot claim termination signals")
        if termination is None and exit_code != 0:
            raise ValueError("unvalidated execution finish requires zero exit code")
    if any(facts[key] != value for key, value in required.items()):
        raise ValueError("process reap cleanup evidence is incomplete or out of order")
    return facts


def _release_facts(
    facts: dict[str, Any], resources: Mapping[str, Any]
) -> dict[str, Any]:
    _fields(
        facts,
        {
            "lease_sha256",
            "release_disposition",
            "release_observed",
            "release_sequence",
        },
        "lease released facts",
    )
    lease = resources["lease_sha256"]
    if facts["lease_sha256"] != lease:
        raise ValueError("lease release does not bind acquired lease")
    if lease is None:
        required = {
            "release_disposition": "not_acquired",
            "release_observed": False,
            "release_sequence": ["not_acquired"],
        }
    else:
        _sha(lease, "lease sha256")
        required = {
            "release_disposition": "released",
            "release_observed": True,
            "release_sequence": ["lease_matched", "release_observed"],
        }
    if any(facts[key] != value for key, value in required.items()):
        raise ValueError("lease release evidence is incomplete or out of order")
    return facts


def _process_binding(
    facts: Mapping[str, Any], resources: Mapping[str, Any]
) -> None:
    handle = resources["process_handle_sha256"]
    if handle is None or facts["process_handle_sha256"] != handle:
        raise ValueError("observation does not bind parent process handle")


def _apply_resources(
    target: str, facts: Mapping[str, Any], resources: Mapping[str, Any]
) -> dict[str, Any]:
    updated = dict(resources)
    if target == "lease_acquired":
        updated["lease_sha256"] = facts["lease_sha256"]
    elif target == "process_started":
        updated["handshake_observed"] = True
    elif target == "process_reaped":
        updated["process_cleanup_complete"] = True
    elif target == "lease_released":
        updated["lease_cleanup_complete"] = True
    return updated


def _replay_event(
    *,
    event: Mapping[str, Any],
    state: str | None,
    outcome: str,
    resources: Mapping[str, Any],
    termination: Mapping[str, Any] | None,
    plan: Mapping[str, Any],
) -> tuple[str, str, dict[str, Any], dict[str, Any] | None]:
    if state is None:
        if (
            event["event_type"] != "milestone"
            or event["source_state"] is not None
            or event["target_state"] != "planned"
            or event["facts"] != {}
            or event["termination"] is not None
            or event["outcome"] != "running"
        ):
            raise ValueError("first lifecycle event must establish planned state")
        return "planned", "running", dict(resources), None
    if event["source_state"] != state:
        raise ValueError("lifecycle event source state is invalid")
    if event["event_type"] == "resource":
        if (
            state != "lease_acquired"
            or termination is not None
            or event["target_state"] not in _RESOURCE_EVENTS
            or event["termination"] is not None
            or event["outcome"] != "running"
        ):
            raise ValueError("process resource event is not allowed")
        facts = _validate_resource_facts(
            event=event["target_state"],
            facts=event["facts"],
            plan=plan,
            resources=resources,
        )
        resources = dict(resources)
        if event["target_state"] == "process_handle_acquired":
            resources["process_handle_sha256"] = facts["process_handle_sha256"]
        else:
            resources["exec_observed"] = True
        return state, outcome, resources, None
    if event["event_type"] == "termination":
        if termination is not None or state in {"lease_released", "terminal"}:
            raise ValueError("termination event is not allowed")
        item = _termination_facts(
            event["termination"]["kind"],
            {
                "code": event["termination"]["code"],
                "message": event["termination"]["message"],
                "retryable": event["termination"]["retryable"],
            },
        )
        expected = {"kind": event["termination"]["kind"], **item}
        if (
            event["target_state"] != state
            or event["facts"] != {}
            or event["termination"] != expected
            or event["outcome"] != expected["kind"]
        ):
            raise ValueError("termination event is inconsistent")
        return state, expected["kind"], dict(resources), expected
    if event["event_type"] != "milestone":
        raise ValueError("lifecycle event type is invalid")
    target = _next_milestone(state, termination is not None)
    if event["target_state"] != target or event["termination"] is not None:
        raise ValueError("lifecycle milestone order is invalid")
    facts = _validate_milestone_facts(
        target=target,
        facts=event["facts"],
        plan=plan,
        resources=resources,
        termination=termination,
    )
    resources = _apply_resources(target, facts, resources)
    next_outcome = outcome
    if target == "terminal":
        next_outcome = (
            termination["kind"] if termination else _UNVALIDATED_FINISH
        )
    if event["outcome"] != next_outcome:
        raise ValueError("lifecycle event outcome is invalid")
    return target, next_outcome, resources, dict(termination) if termination else None


def _termination_facts(kind: str, facts: Mapping[str, Any]) -> dict[str, Any]:
    if kind not in _TERMINATIONS:
        raise ValueError("termination kind is invalid")
    value = _json_object(facts, "termination facts")
    _fields(value, {"code", "message", "retryable"}, "termination facts")
    _identifier(value["code"], "termination code")
    _path_free(value["message"], "termination message")
    if (
        not isinstance(value["message"], str)
        or len(value["message"]) > _MAX_MESSAGE_CHARACTERS
    ):
        raise ValueError("termination message exceeds supported size")
    if not isinstance(value["retryable"], bool):
        raise ValueError("termination retryable must be boolean")
    return value


def _event(
    *,
    sequence: int,
    event_type: str,
    source_state: str | None,
    target_state: str,
    outcome: str,
    prior_state_sha256: str,
    authority: SeparationSupervisorAuthority,
    facts: Mapping[str, Any],
    termination: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload = {
        "sequence": sequence,
        "event_type": event_type,
        "source_state": source_state,
        "target_state": target_state,
        "outcome": outcome,
        "prior_state_sha256": prior_state_sha256,
        "authority_id": authority.authority_id,
        "observer_sha256": authority.observer_sha256,
        "facts": _thaw(facts),
        "termination": _thaw(termination),
    }
    return {**payload, "event_sha256": _hash(payload)}


def _validate_event(
    value: Any,
    *,
    sequence: int,
    prior_state_sha256: str,
    authority: SeparationSupervisorAuthority,
) -> dict[str, Any]:
    event = _json_object(value, "lifecycle event")
    if len(_canonical_json(event)) > _MAX_EVENT_BYTES:
        raise ValueError("lifecycle event exceeds supported size")
    _fields(
        event,
        {
            "sequence",
            "event_type",
            "source_state",
            "target_state",
            "outcome",
            "prior_state_sha256",
            "authority_id",
            "observer_sha256",
            "facts",
            "termination",
            "event_sha256",
        },
        "lifecycle event",
    )
    if type(event["sequence"]) is not int or event["sequence"] != sequence:
        raise ValueError("lifecycle event sequence is not monotonic")
    if event["prior_state_sha256"] != prior_state_sha256:
        raise ValueError("lifecycle event prior state hash is invalid")
    if (
        event["authority_id"] != authority.authority_id
        or event["observer_sha256"] != authority.observer_sha256
    ):
        raise ValueError("lifecycle event is not supervisor-authored")
    payload = dict(event)
    claimed = payload.pop("event_sha256")
    if _sha(claimed, "event sha256") != _hash(payload):
        raise ValueError("lifecycle event hash is invalid")
    _path_free(event, "lifecycle event")
    return event


def _lifecycle_hash(
    *,
    base: Mapping[str, Any],
    current_state: str | None,
    outcome: str,
    resources: Mapping[str, Any],
    termination: Mapping[str, Any] | None,
    events: Sequence[Mapping[str, Any]],
) -> str:
    return _hash(
        {
            **_thaw(base),
            "current_state": current_state,
            "outcome": outcome,
            "resources": _thaw(resources),
            "termination": _thaw(termination),
            "events": _thaw(events),
        }
    )


def _empty_resources() -> dict[str, Any]:
    return {
        "lease_sha256": None,
        "process_handle_sha256": None,
        "exec_observed": False,
        "handshake_observed": False,
        "process_cleanup_complete": False,
        "lease_cleanup_complete": False,
    }


def _latest_milestone(
    events: Sequence[Mapping[str, Any]], target: str
) -> Mapping[str, Any]:
    matching = [
        event
        for event in events
        if event["event_type"] == "milestone" and event["target_state"] == target
    ]
    if len(matching) != 1:
        raise ValueError(f"terminal lifecycle requires exactly one {target} milestone")
    return matching[0]


def _json_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    plain = _thaw(value)
    if not isinstance(plain, dict) or any(not isinstance(key, str) for key in plain):
        raise ValueError(f"{label} must be a string-keyed object")
    _canonical_json(plain)
    return plain


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("value must be finite canonical JSON") from exc


def _hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _hash_array(value: Sequence[Any]) -> str:
    return hashlib.sha256(_canonical_json(list(value))).hexdigest()


def _fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields are invalid")


def _identifier(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not _ID_RE.fullmatch(value)
        or value != value.strip()
    ):
        raise ValueError(f"{label} is invalid")
    return value


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise ValueError(f"{label} is not a lowercase SHA-256")
    return value


def _path_free(value: Any, label: str) -> None:
    if isinstance(value, str):
        if (
            _URL_RE.search(value)
            or value.startswith(("/", "~"))
            or _WINDOWS_RE.match(value)
            or "/" in value
            or "\\" in value
        ):
            raise ValueError(f"{label} contains a path or URL")
    elif isinstance(value, Mapping):
        for key, item in value.items():
            if key == "path" or key.endswith("_path"):
                raise ValueError(f"{label} contains a path field")
            _path_free(item, f"{label}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _path_free(item, f"{label}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{label} contains a non-finite number")
    elif value is not None and not isinstance(value, (bool, int, float)):
        raise ValueError(f"{label} contains a non-JSON value")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


__all__ = [
    "REAL_WORKER_EXECUTION_SUPPORTED",
    "SEPARATION_DESCRIPTOR_POLICY_ID",
    "SEPARATION_DESCRIPTOR_POLICY_SHA256",
    "SEPARATION_LAUNCH_ENVIRONMENT_SHA256",
    "SEPARATION_LAUNCH_PLAN_SCHEMA",
    "SEPARATION_LAUNCH_POLICY_ID",
    "SEPARATION_LIFECYCLE_SCHEMA",
    "SEPARATION_PRIVATE_ISOLATION_TEMPLATE_SHA256",
    "SEPARATION_TERMINAL_RECEIPT_SCHEMA",
    "SeparationLaunchPlanRecord",
    "SeparationLifecycleRecord",
    "SeparationSupervisorAuthority",
    "SeparationSupervisorObservation",
    "advance_separation_lifecycle",
    "build_separation_launch_plan",
    "build_separation_terminal_receipt",
    "create_separation_lifecycle",
    "separation_launch_plan_sha256",
    "validate_separation_launch_plan",
    "validate_separation_lifecycle",
    "validate_separation_terminal_receipt",
]
