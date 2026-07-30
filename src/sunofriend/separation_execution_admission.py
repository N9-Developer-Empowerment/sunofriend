"""Pure, non-executing separation admission decision.

All inputs are synthetic, exact parent evidence records.  The module performs
no filesystem, process, network, checkpoint, model, audio, import,
deserialization or write operation.

V1 intentionally has no supported isolation provider and no complete runtime
closure capability.  Caller-supplied ``enforced`` or ``available`` booleans
therefore cannot make a worker eligible.  Every decision is ``blocked`` and
``not_run`` until those code-owned capabilities are implemented and reviewed.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .separation_checkpoint_policy import (
    SeparationCheckpointPolicyRecord,
    build_separation_checkpoint_policy,
    separation_checkpoint_policy_sha256,
)


SEPARATION_EXECUTION_ADMISSION_SCHEMA = (
    "sunofriend.separation-execution-admission.v1"
)
SEPARATION_EXECUTION_ADMISSION_POLICY_ID = (
    "private-development-execution-admission-v1"
)

REAL_SEPARATION_EXECUTION_SUPPORTED = False
RUNTIME_CLOSURE_CAPABILITY_SUPPORTED = False
OUTPUT_BOUNDARY_CAPABILITY_SUPPORTED = False
RESOURCE_LIMIT_CAPABILITY_SUPPORTED = False
SUPPORTED_ISOLATION_PROVIDER_IDS: frozenset[str] = frozenset()
SUPPORTED_DESCENDANT_POLICY_PROVIDER_IDS: frozenset[str] = frozenset()

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._+:-]{0,191}$")
_URL_RE = re.compile(r"(?:[A-Za-z][A-Za-z0-9+.-]*://|www\.)")
_WINDOWS_RE = re.compile(r"^[A-Za-z]:[\\/]")
_OUTPUT_MODES = frozenset({"exact_output_fds", "staging_and_quarantine"})
_DESCENDANT_POLICIES = frozenset(
    {
        "deny_all_model_descendants",
        "allow_exact_observed_model_descendants",
        "unresolved",
    }
)
_REQUIRED_HARD_LIMITS = frozenset(
    {
        "file_count",
        "cpu_time_seconds",
        "memory_bytes",
        "open_file_count",
        "output_bytes",
        "per_output_bytes",
        "process_count",
        "stderr_bytes",
        "stdout_bytes",
        "wall_time_seconds",
    }
)
_MAX_LIMIT_ENTRIES = 64
_MAX_LIMIT_VALUE = (1 << 63) - 1


@dataclass(frozen=True)
class SeparationRuntimeClosureEvidence:
    """Synthetic reported claims about runtime closure.

    V1 records these claims but cannot treat them as complete because the
    code-owned closure capability is false.
    """

    runtime_artifact_sha256: str
    runtime_measurements_sha256: str
    closure_evidence_sha256: str | None
    base_standard_library_bound: bool
    pyvenv_home_bound: bool
    native_dynamic_libraries_bound: bool
    accelerator_runtime_bound: bool

    def __post_init__(self) -> None:
        _sha(self.runtime_artifact_sha256, "runtime artifact sha256")
        _sha(self.runtime_measurements_sha256, "runtime measurements sha256")
        if self.closure_evidence_sha256 is not None:
            _sha(self.closure_evidence_sha256, "runtime closure evidence sha256")
        for value, label in (
            (self.base_standard_library_bound, "base standard library bound"),
            (self.pyvenv_home_bound, "pyvenv home bound"),
            (
                self.native_dynamic_libraries_bound,
                "native dynamic libraries bound",
            ),
            (self.accelerator_runtime_bound, "accelerator runtime bound"),
        ):
            _boolean(value, label)


@dataclass(frozen=True)
class SeparationIsolationEvidence:
    """Synthetic network, attempt-observer and descendant-control reports."""

    provider_id: str | None
    provider_sha256: str | None
    provider_available: bool
    fail_closed: bool
    network_denial_enforced: bool
    network_denial_evidence_sha256: str | None
    outbound_attempt_observation_enabled: bool
    outbound_attempt_observer_sha256: str | None
    model_descendant_policy: str
    model_descendant_denial_enforced: bool
    model_descendant_attempt_observation_enabled: bool
    model_descendant_evidence_sha256: str | None

    def __post_init__(self) -> None:
        if self.provider_id is not None:
            _identifier(self.provider_id, "isolation provider id")
        for value, label in (
            (self.provider_sha256, "isolation provider sha256"),
            (
                self.network_denial_evidence_sha256,
                "network denial evidence sha256",
            ),
            (
                self.outbound_attempt_observer_sha256,
                "outbound attempt observer sha256",
            ),
            (
                self.model_descendant_evidence_sha256,
                "model descendant evidence sha256",
            ),
        ):
            if value is not None:
                _sha(value, label)
        for value, label in (
            (self.provider_available, "isolation provider available"),
            (self.fail_closed, "isolation fail closed"),
            (self.network_denial_enforced, "network denial enforced"),
            (
                self.outbound_attempt_observation_enabled,
                "outbound attempt observation enabled",
            ),
            (
                self.model_descendant_denial_enforced,
                "model descendant denial enforced",
            ),
            (
                self.model_descendant_attempt_observation_enabled,
                "model descendant attempt observation enabled",
            ),
        ):
            _boolean(value, label)
        if self.model_descendant_policy not in _DESCENDANT_POLICIES:
            raise ValueError("model descendant policy is unsupported")


@dataclass(frozen=True)
class SeparationOutputBoundaryEvidence:
    """One synthetic exact-FD or staging-and-quarantine output report."""

    mode: str
    policy_sha256: str
    exact_output_fds_bound: bool
    exact_output_fds_evidence_sha256: str | None
    fresh_private_staging: bool
    quarantine_before_validation: bool
    parent_output_verification_required: bool
    publication_disabled: bool
    staging_evidence_sha256: str | None

    def __post_init__(self) -> None:
        if self.mode not in _OUTPUT_MODES:
            raise ValueError("output boundary mode is unsupported")
        _sha(self.policy_sha256, "output boundary policy sha256")
        for value, label in (
            (
                self.exact_output_fds_evidence_sha256,
                "exact output descriptors evidence sha256",
            ),
            (self.staging_evidence_sha256, "output staging evidence sha256"),
        ):
            if value is not None:
                _sha(value, label)
        for value, label in (
            (self.exact_output_fds_bound, "exact output descriptors bound"),
            (self.fresh_private_staging, "fresh private staging"),
            (
                self.quarantine_before_validation,
                "quarantine before validation",
            ),
            (
                self.parent_output_verification_required,
                "parent output verification required",
            ),
            (self.publication_disabled, "publication disabled"),
        ):
            _boolean(value, label)


@dataclass(frozen=True)
class SeparationResourceLimitEvidence:
    """Synthetic hard, advisory and observable resource-limit reports."""

    hard_limits: Mapping[str, int]
    hard_enforced: Sequence[str]
    advisory_limits: Mapping[str, int]
    observed_limits: Sequence[str]
    observation_evidence_sha256: str | None

    def __post_init__(self) -> None:
        hard = _limit_map(self.hard_limits, "hard limits")
        advisory = _limit_map(self.advisory_limits, "advisory limits")
        if set(hard) & set(advisory):
            raise ValueError("hard and advisory resource limits must be disjoint")
        enforced = _sorted_unique(self.hard_enforced, "hard enforced limits")
        observed = _sorted_unique(self.observed_limits, "observed limits")
        if not set(enforced).issubset(hard):
            raise ValueError("hard enforcement names must bind hard limits")
        if not set(observed).issubset(set(hard) | set(advisory)):
            raise ValueError("observed names must bind declared limits")
        if self.observation_evidence_sha256 is not None:
            _sha(
                self.observation_evidence_sha256,
                "resource observation evidence sha256",
            )
        object.__setattr__(self, "hard_limits", _freeze(hard))
        object.__setattr__(self, "hard_enforced", enforced)
        object.__setattr__(self, "advisory_limits", _freeze(advisory))
        object.__setattr__(self, "observed_limits", observed)


@dataclass(frozen=True, init=False)
class SeparationExecutionAdmissionRecord(Mapping[str, Any]):
    """Validated, deeply immutable blocked/not-run decision."""

    _document: Mapping[str, Any]
    _checkpoint_policy: SeparationCheckpointPolicyRecord
    _runtime: SeparationRuntimeClosureEvidence
    _isolation: SeparationIsolationEvidence
    _output: SeparationOutputBoundaryEvidence
    _resources: SeparationResourceLimitEvidence

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


def build_separation_execution_admission(
    *,
    checkpoint_policy: SeparationCheckpointPolicyRecord,
    runtime: SeparationRuntimeClosureEvidence,
    isolation: SeparationIsolationEvidence,
    output: SeparationOutputBoundaryEvidence,
    resources: SeparationResourceLimitEvidence,
) -> SeparationExecutionAdmissionRecord:
    """Build one path-free decision without starting or loading anything."""

    checkpoint = _exact_checkpoint_policy(checkpoint_policy)
    runtime = _exact_type(
        runtime, SeparationRuntimeClosureEvidence, "runtime closure evidence"
    )
    isolation = _exact_type(
        isolation, SeparationIsolationEvidence, "isolation evidence"
    )
    output = _exact_type(
        output, SeparationOutputBoundaryEvidence, "output boundary evidence"
    )
    resources = _exact_type(
        resources, SeparationResourceLimitEvidence, "resource-limit evidence"
    )

    blockers = set(checkpoint["decision"]["blockers"])
    advisories = set(checkpoint["decision"]["advisories"])
    blockers.update(
        {
            "backend_accelerator_readiness_unimplemented",
            "filesystem_confinement_unimplemented",
            "input_read_only_enforcement_unimplemented",
            "isolation_canary_binding_unimplemented",
            "isolation_provider_qualification_unimplemented",
            "outside_output_write_denial_unimplemented",
            "parent_output_verification_unimplemented",
            "preexec_runtime_remeasurement_binding_unimplemented",
            "real_transport_unimplemented",
            "resource_memory_closure_unimplemented",
            "trusted_launch_plan_binding_unimplemented",
            "trusted_preflight_binding_unimplemented",
            "trusted_runtime_artifact_binding_unimplemented",
            "trusted_worker_request_binding_unimplemented",
        }
    )

    caller_runtime_complete = bool(
        runtime.closure_evidence_sha256 is not None
        and runtime.base_standard_library_bound
        and runtime.pyvenv_home_bound
        and runtime.native_dynamic_libraries_bound
        and runtime.accelerator_runtime_bound
    )
    runtime_complete = bool(
        RUNTIME_CLOSURE_CAPABILITY_SUPPORTED and caller_runtime_complete
    )
    if not runtime_complete:
        blockers.add("runtime_closure_incomplete")

    provider_supported = bool(
        isolation.provider_available
        and isolation.provider_id in SUPPORTED_ISOLATION_PROVIDER_IDS
        and isolation.provider_sha256 is not None
        and isolation.fail_closed
    )
    if not provider_supported:
        blockers.add("isolation_provider_unavailable")

    network_denial_ready = bool(
        provider_supported
        and isolation.network_denial_enforced
        and isolation.network_denial_evidence_sha256 is not None
    )
    attempt_observation_ready = bool(
        provider_supported
        and isolation.outbound_attempt_observation_enabled
        and isolation.outbound_attempt_observer_sha256 is not None
    )
    if not network_denial_ready:
        blockers.add("network_denial_unproven")
    if not attempt_observation_ready:
        blockers.add("network_attempt_observation_unavailable")

    descendant_provider_supported = bool(
        provider_supported
        and isolation.provider_id in SUPPORTED_DESCENDANT_POLICY_PROVIDER_IDS
    )
    descendant_policy_ready = bool(
        descendant_provider_supported
        and isolation.model_descendant_policy
        in {
            "deny_all_model_descendants",
            "allow_exact_observed_model_descendants",
        }
        and isolation.model_descendant_denial_enforced
        and isolation.model_descendant_attempt_observation_enabled
        and isolation.model_descendant_evidence_sha256 is not None
    )
    if not descendant_policy_ready:
        blockers.add("model_descendant_policy_unproven")

    caller_output_ready = _output_ready(output)
    output_ready = bool(
        OUTPUT_BOUNDARY_CAPABILITY_SUPPORTED and caller_output_ready
    )
    if not output_ready:
        blockers.add("output_boundary_incomplete")
    if output.mode == "exact_output_fds":
        blockers.add("output_transport_mismatch_unresolved")

    resource_document, resources_ready = _resource_document(resources)
    if not resources_ready["hard_limits_complete"]:
        blockers.add("resource_hard_limits_incomplete")
    if not resources_ready["hard_enforcement_complete"]:
        blockers.add("resource_hard_enforcement_unproven")
    if not resources_ready["hard_observation_complete"]:
        blockers.add("resource_observation_incomplete")
    if not RESOURCE_LIMIT_CAPABILITY_SUPPORTED:
        blockers.add("resource_enforcement_capability_unimplemented")
    if resources.advisory_limits:
        advisories.add("advisory_resource_limits_not_hard_enforced")

    # This literal capability is the final non-bypassable V1 gate.
    if not REAL_SEPARATION_EXECUTION_SUPPORTED:
        blockers.add("real_execution_not_implemented")

    blocker_list = tuple(sorted(blockers))
    advisory_list = tuple(sorted(advisories))
    payload = {
        "schema": SEPARATION_EXECUTION_ADMISSION_SCHEMA,
        "policy_id": SEPARATION_EXECUTION_ADMISSION_POLICY_ID,
        "evidence_scope": "private_development",
        "publication_scope": "private_local_contract_evidence",
        "public_redacted_projection_available": False,
        "evidence_authority": "synthetic_contract_only",
        "reported_claims_trusted": False,
        "status": "blocked",
        "run_status": "not_run",
        "real_execution_supported": REAL_SEPARATION_EXECUTION_SUPPORTED,
        "execution_permitted": False,
        "bindings": {
            "checkpoint_policy_sha256": checkpoint["policy_sha256"],
            "checkpoint_sha256": checkpoint["checkpoint"]["sha256"],
            "runtime_artifact_sha256": runtime.runtime_artifact_sha256,
            "runtime_measurements_sha256": runtime.runtime_measurements_sha256,
            "output_policy_sha256": output.policy_sha256,
        },
        "checkpoint": {
            "status": checkpoint["decision"]["status"],
            "blockers": list(checkpoint["decision"]["blockers"]),
            "advisories": list(checkpoint["decision"]["advisories"]),
        },
        "runtime_closure": {
            "capability_supported": RUNTIME_CLOSURE_CAPABILITY_SUPPORTED,
            "caller_evidence_complete": caller_runtime_complete,
            "closure_complete": runtime_complete,
            "closure_evidence_sha256": runtime.closure_evidence_sha256,
            "base_standard_library_bound": (
                runtime.base_standard_library_bound
            ),
            "pyvenv_home_bound": runtime.pyvenv_home_bound,
            "native_dynamic_libraries_bound": (
                runtime.native_dynamic_libraries_bound
            ),
            "accelerator_runtime_bound": runtime.accelerator_runtime_bound,
        },
        "isolation": {
            "provider": {
                "provider_id": isolation.provider_id,
                "provider_sha256": isolation.provider_sha256,
                "caller_available": isolation.provider_available,
                "fail_closed": isolation.fail_closed,
                "code_supported": provider_supported,
            },
            "network_denial": {
                "caller_enforced": isolation.network_denial_enforced,
                "evidence_sha256": isolation.network_denial_evidence_sha256,
                "ready": network_denial_ready,
            },
            "outbound_attempt_observation": {
                "caller_enabled": (
                    isolation.outbound_attempt_observation_enabled
                ),
                "observer_sha256": (
                    isolation.outbound_attempt_observer_sha256
                ),
                "ready": attempt_observation_ready,
            },
            "model_descendants": {
                "policy": isolation.model_descendant_policy,
                "caller_denial_enforced": (
                    isolation.model_descendant_denial_enforced
                ),
                "caller_attempt_observation_enabled": (
                    isolation.model_descendant_attempt_observation_enabled
                ),
                "evidence_sha256": (
                    isolation.model_descendant_evidence_sha256
                ),
                "provider_code_supported": descendant_provider_supported,
                "ready": descendant_policy_ready,
            },
        },
        "output_boundary": {
            **_output_document(output),
            "capability_supported": OUTPUT_BOUNDARY_CAPABILITY_SUPPORTED,
            "caller_evidence_complete": caller_output_ready,
            "ready": output_ready,
        },
        "resource_limits": {
            **resource_document,
            "capability_supported": RESOURCE_LIMIT_CAPABILITY_SUPPORTED,
        },
        "decision": {
            "status": "blocked",
            "run_status": "not_run",
            "blockers": blocker_list,
            "advisories": advisory_list,
        },
        "effects": {
            "filesystem_accessed": False,
            "process_started": False,
            "worker_started": False,
            "checkpoint_opened": False,
            "checkpoint_loaded": False,
            "checkpoint_deserialized": False,
            "model_imported": False,
            "inference_started": False,
            "network_used": False,
            "audio_read": False,
            "outputs_created": False,
            "quarantine_created": False,
            "files_written": False,
            "publication_permitted": False,
            "acceptance_eligible": False,
            "promotion_eligible": False,
        },
    }
    _path_free(payload, "execution admission")
    document = {**payload, "admission_sha256": _hash(payload)}
    return _new_record(
        document,
        checkpoint=checkpoint,
        runtime=runtime,
        isolation=isolation,
        output=output,
        resources=resources,
    )


def validate_separation_execution_admission(
    document: Mapping[str, Any],
    *,
    checkpoint_policy: SeparationCheckpointPolicyRecord,
    runtime: SeparationRuntimeClosureEvidence,
    isolation: SeparationIsolationEvidence,
    output: SeparationOutputBoundaryEvidence,
    resources: SeparationResourceLimitEvidence,
) -> SeparationExecutionAdmissionRecord:
    """Validate a projection against all exact synthetic evidence."""

    expected = build_separation_execution_admission(
        checkpoint_policy=checkpoint_policy,
        runtime=runtime,
        isolation=isolation,
        output=output,
        resources=resources,
    )
    value = _json_object(document, "execution admission")
    if value != _thaw(expected):
        raise ValueError("execution admission does not match reported evidence")
    return _new_record(
        value,
        checkpoint=checkpoint_policy,
        runtime=runtime,
        isolation=isolation,
        output=output,
        resources=resources,
    )


def separation_execution_admission_sha256(document: Mapping[str, Any]) -> str:
    """Return the canonical admission hash after excluding its self-hash."""

    value = _json_object(document, "execution admission")
    value.pop("admission_sha256", None)
    return _hash(value)


def _exact_checkpoint_policy(
    value: Any,
) -> SeparationCheckpointPolicyRecord:
    if type(value) is not SeparationCheckpointPolicyRecord:
        raise ValueError("admission requires an exact checkpoint policy record")
    if value["policy_sha256"] != separation_checkpoint_policy_sha256(value):
        raise ValueError("checkpoint policy hash is invalid")
    expected = build_separation_checkpoint_policy(value._evidence)
    if _thaw(value) != _thaw(expected):
        raise ValueError("checkpoint policy record is not canonical")
    decision = value["decision"]
    if (
        value["checkpoint_execution_policy_supported"] is not False
        or decision["status"] != "blocked"
        or decision["run_status"] != "not_run"
        or decision["private_development_checkpoint_eligible"] is not False
        or decision["worker_start_permitted"] is not False
        or any(item is not False for item in value["effects"].values())
    ):
        raise ValueError("checkpoint policy cannot authorize execution")
    return value


def _exact_type(value: Any, kind: type[Any], label: str) -> Any:
    if type(value) is not kind:
        raise ValueError(f"{label} must be exact parent evidence")
    return value


def _output_ready(value: SeparationOutputBoundaryEvidence) -> bool:
    if value.mode == "exact_output_fds":
        return bool(
            value.exact_output_fds_bound
            and value.exact_output_fds_evidence_sha256 is not None
            and value.parent_output_verification_required
            and value.publication_disabled
            and not value.fresh_private_staging
            and not value.quarantine_before_validation
            and value.staging_evidence_sha256 is None
        )
    return bool(
        not value.exact_output_fds_bound
        and value.exact_output_fds_evidence_sha256 is None
        and value.fresh_private_staging
        and value.quarantine_before_validation
        and value.parent_output_verification_required
        and value.publication_disabled
        and value.staging_evidence_sha256 is not None
    )


def _output_document(value: SeparationOutputBoundaryEvidence) -> dict[str, Any]:
    return {
        "mode": value.mode,
        "policy_sha256": value.policy_sha256,
        "exact_output_fds": {
            "bound": value.exact_output_fds_bound,
            "evidence_sha256": value.exact_output_fds_evidence_sha256,
        },
        "staging_and_quarantine": {
            "fresh_private_staging": value.fresh_private_staging,
            "quarantine_before_validation": (
                value.quarantine_before_validation
            ),
            "parent_output_verification_required": (
                value.parent_output_verification_required
            ),
            "publication_disabled": value.publication_disabled,
            "evidence_sha256": value.staging_evidence_sha256,
        },
    }


def _resource_document(
    value: SeparationResourceLimitEvidence,
) -> tuple[dict[str, Any], dict[str, bool]]:
    hard = _thaw(value.hard_limits)
    advisory = _thaw(value.advisory_limits)
    enforced = set(value.hard_enforced)
    observed = set(value.observed_limits)
    readiness = {
        "hard_limits_complete": _REQUIRED_HARD_LIMITS.issubset(hard),
        "hard_enforcement_complete": set(hard) == enforced,
        "hard_observation_complete": (
            set(hard).issubset(observed)
            and value.observation_evidence_sha256 is not None
        ),
    }
    return (
        {
            "hard": [
                {
                    "name": name,
                    "limit": hard[name],
                    "enforced": name in enforced,
                }
                for name in sorted(hard)
            ],
            "advisory": [
                {
                    "name": name,
                    "limit": advisory[name],
                    "observed": name in observed,
                }
                for name in sorted(advisory)
            ],
            "observed": [
                {"name": name, "observed": True} for name in sorted(observed)
            ],
            "observation_evidence_sha256": value.observation_evidence_sha256,
            "readiness": readiness,
        },
        readiness,
    )


def _new_record(
    document: Mapping[str, Any],
    *,
    checkpoint: SeparationCheckpointPolicyRecord,
    runtime: SeparationRuntimeClosureEvidence,
    isolation: SeparationIsolationEvidence,
    output: SeparationOutputBoundaryEvidence,
    resources: SeparationResourceLimitEvidence,
) -> SeparationExecutionAdmissionRecord:
    value = _json_object(document, "execution admission")
    if value.get("schema") != SEPARATION_EXECUTION_ADMISSION_SCHEMA:
        raise ValueError("unsupported execution admission schema")
    if value.get("admission_sha256") != separation_execution_admission_sha256(
        value
    ):
        raise ValueError("execution admission hash is invalid")
    if (
        value.get("status") != "blocked"
        or value.get("run_status") != "not_run"
        or value.get("real_execution_supported") is not False
        or value.get("execution_permitted") is not False
        or value.get("reported_claims_trusted") is not False
    ):
        raise ValueError("execution admission must remain blocked and not run")
    blockers = value.get("decision", {}).get("blockers")
    advisories = value.get("decision", {}).get("advisories")
    if (
        not isinstance(blockers, list)
        or blockers != sorted(set(blockers))
        or not isinstance(advisories, list)
        or advisories != sorted(set(advisories))
    ):
        raise ValueError("execution decisions must be sorted and unique")
    effects = value.get("effects")
    if not isinstance(effects, dict) or any(item is not False for item in effects.values()):
        raise ValueError("execution admission effects must all be false")
    _path_free(value, "execution admission")
    record = object.__new__(SeparationExecutionAdmissionRecord)
    object.__setattr__(record, "_document", _freeze(value))
    object.__setattr__(record, "_checkpoint_policy", checkpoint)
    object.__setattr__(record, "_runtime", runtime)
    object.__setattr__(record, "_isolation", isolation)
    object.__setattr__(record, "_output", output)
    object.__setattr__(record, "_resources", resources)
    return record


def _limit_map(value: Any, label: str) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    plain = _thaw(value)
    if not isinstance(plain, dict):
        raise ValueError(f"{label} must be an object")
    if len(plain) > _MAX_LIMIT_ENTRIES:
        raise ValueError(f"{label} exceeds supported entry count")
    result: dict[str, int] = {}
    for name, limit in plain.items():
        _identifier(name, f"{label} name")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit <= 0
            or limit > _MAX_LIMIT_VALUE
        ):
            raise ValueError(f"{label} values must be positive integers")
        result[name] = limit
    return {name: result[name] for name in sorted(result)}


def _sorted_unique(values: Sequence[str], label: str) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)) or len(values) > _MAX_LIMIT_ENTRIES:
        raise ValueError(f"{label} must be an array")
    checked = tuple(values)
    if any(not isinstance(item, str) for item in checked):
        raise ValueError(f"{label} must contain text")
    if checked != tuple(sorted(set(checked))):
        raise ValueError(f"{label} must be sorted and unique")
    return checked


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


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise ValueError(f"{label} is not a lowercase SHA-256")
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ValueError(f"{label} is invalid")
    return value


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _path_free(value: Any, label: str) -> None:
    if isinstance(value, str):
        if (
            _URL_RE.search(value)
            or value.startswith(("/", "~"))
            or _WINDOWS_RE.match(value)
            or "/" in value
            or "\\" in value
            or "\0" in value
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
    elif value is not None and not isinstance(value, (bool, int)):
        raise ValueError(f"{label} contains a non-canonical value")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
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
    "OUTPUT_BOUNDARY_CAPABILITY_SUPPORTED",
    "REAL_SEPARATION_EXECUTION_SUPPORTED",
    "RUNTIME_CLOSURE_CAPABILITY_SUPPORTED",
    "RESOURCE_LIMIT_CAPABILITY_SUPPORTED",
    "SEPARATION_EXECUTION_ADMISSION_POLICY_ID",
    "SEPARATION_EXECUTION_ADMISSION_SCHEMA",
    "SUPPORTED_DESCENDANT_POLICY_PROVIDER_IDS",
    "SUPPORTED_ISOLATION_PROVIDER_IDS",
    "SeparationExecutionAdmissionRecord",
    "SeparationIsolationEvidence",
    "SeparationOutputBoundaryEvidence",
    "SeparationResourceLimitEvidence",
    "SeparationRuntimeClosureEvidence",
    "build_separation_execution_admission",
    "separation_execution_admission_sha256",
    "validate_separation_execution_admission",
]
