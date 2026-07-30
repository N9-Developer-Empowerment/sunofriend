"""Pure checkpoint-deserialization admission policy.

This module consumes only synthetic, reported evidence records.  V1 does not
cross-bind those reports to acceptance, preflight or worker-request authority,
so it can never authorize a worker.  It does not
inspect a checkpoint, open a file, import a model package, deserialize bytes or
start a process.  Declared checkpoint format and independently classified
container kind remain separate so an existing identity cannot be silently
reinterpreted after inspection.

Unsafe-pickle exception metadata is recorded for future design review, but it
cannot waive the categorical executable-pickle blocker.  Exact-global metadata
does not constrain an ordinary ``torch.load(..., weights_only=False)`` call.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence


SEPARATION_CHECKPOINT_POLICY_SCHEMA = "sunofriend.separation-checkpoint-policy.v1"
SEPARATION_CHECKPOINT_POLICY_ID = "private-development-checkpoint-policy-v1"
CHECKPOINT_EXECUTION_POLICY_SUPPORTED = False
DEMUCS_HTDEMUCS_CHECKPOINT_SHA256 = (
    "8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4"
)

# V1 deliberately has no qualifying unsafe-pickle provider.  Adding one is a
# code review and release decision, never a caller-supplied boolean.
SUPPORTED_UNSAFE_PICKLE_PROVIDER_IDS: frozenset[str] = frozenset()
_KNOWN_CHECKPOINTS = {
    DEMUCS_HTDEMUCS_CHECKPOINT_SHA256: {
        "policy_id": "demucs-4.0.1-htdemucs-955717e8-v1",
        "classified_container_kind": "torch-pickle-model-package",
        "terms_verified": False,
        "allowed_use_verified": False,
    }
}

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._+:-]{0,191}$")
_GLOBAL_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){1,31}$"
)
_URL_RE = re.compile(r"(?:[A-Za-z][A-Za-z0-9+.-]*://|www\.)")
_WINDOWS_RE = re.compile(r"^[A-Za-z]:[\\/]")
_MAX_CHECKPOINT_BYTES = 8 * 1024 * 1024 * 1024

_DECLARED_FORMATS = frozenset(
    {
        "coreml",
        "onnx",
        "safetensors",
        "torch-pickle-model-package",
        "torch-state-dict",
    }
)
_CONTAINER_KINDS = frozenset({*_DECLARED_FORMATS, "uninspected"})
_DESERIALIZATION_MODES = frozenset(
    {
        "coreml-model-load",
        "onnx-graph-load",
        "safetensors-tensor-load",
        "torch-load-pickle-model-package",
        "torch-load-state-dict",
    }
)
_ALLOWED_USES = frozenset(
    {
        "private_development",
        "hidden_evaluation",
        "derived_output_redistribution",
        "component_redistribution",
        "commercial_use",
    }
)
_EXPECTED_LOADER_MODE = {
    "coreml": "coreml-model-load",
    "onnx": "onnx-graph-load",
    "safetensors": "safetensors-tensor-load",
    "torch-pickle-model-package": "torch-load-pickle-model-package",
    "torch-state-dict": "torch-load-state-dict",
}


@dataclass(frozen=True)
class SeparationCheckpointTermsEvidence:
    """Path-free reported terms and allowed-use claims."""

    terms_sha256: str | None
    terms_verified: bool
    license_expression: str | None
    allowed_uses: Sequence[str]
    allowed_use_evidence_sha256: str | None
    allowed_use_verified: bool

    def __post_init__(self) -> None:
        if self.terms_sha256 is not None:
            _sha(self.terms_sha256, "checkpoint terms sha256")
        _boolean(self.terms_verified, "checkpoint terms verified")
        if self.license_expression is not None:
            _license_expression(
                self.license_expression, "checkpoint licence expression"
            )
        uses = _sorted_unique(self.allowed_uses, "checkpoint allowed uses")
        if any(item not in _ALLOWED_USES for item in uses):
            raise ValueError("checkpoint allowed use is unsupported")
        object.__setattr__(self, "allowed_uses", uses)
        if self.allowed_use_evidence_sha256 is not None:
            _sha(
                self.allowed_use_evidence_sha256,
                "checkpoint allowed-use evidence sha256",
            )
        _boolean(self.allowed_use_verified, "checkpoint allowed-use verified")
        if self.terms_verified and self.terms_sha256 is None:
            raise ValueError("verified checkpoint terms require a terms hash")
        if self.allowed_use_verified and self.allowed_use_evidence_sha256 is None:
            raise ValueError(
                "verified checkpoint allowed use requires an evidence hash"
            )


@dataclass(frozen=True)
class SeparationCheckpointLoaderEvidence:
    """Reported loader identity and requested deserialization mode."""

    loader_id: str
    loader_sha256: str
    deserialization_mode: str
    weights_only: bool | str = True

    def __post_init__(self) -> None:
        _identifier(self.loader_id, "checkpoint loader id")
        _sha(self.loader_sha256, "checkpoint loader sha256")
        if self.deserialization_mode not in _DESERIALIZATION_MODES:
            raise ValueError("checkpoint deserialization mode is unsupported")
        if (
            not isinstance(self.weights_only, bool)
            and self.weights_only != "not_applicable"
        ):
            raise ValueError(
                "checkpoint weights-only mode must be true, false or not_applicable"
            )


@dataclass(frozen=True)
class SeparationUnsafePickleExceptionEvidence:
    """Explicit, checkpoint-bound private-development exception evidence."""

    explicitly_approved: bool = False
    evidence_scope: str = "none"
    approval_sha256: str | None = None
    provider_id: str | None = None
    provider_sha256: str | None = None
    provider_qualification_sha256: str | None = None
    exact_globals: Sequence[str] = ()
    exact_globals_sha256: str | None = None
    checkpoint_sha256: str | None = None

    def __post_init__(self) -> None:
        _boolean(self.explicitly_approved, "unsafe pickle explicit approval")
        if self.evidence_scope not in {"none", "private_development"}:
            raise ValueError("unsafe pickle exception scope is invalid")
        for value, label in (
            (self.approval_sha256, "unsafe pickle approval sha256"),
            (self.provider_sha256, "unsafe pickle provider sha256"),
            (
                self.provider_qualification_sha256,
                "unsafe pickle provider qualification sha256",
            ),
            (self.exact_globals_sha256, "unsafe pickle exact-globals sha256"),
            (self.checkpoint_sha256, "unsafe pickle checkpoint sha256"),
        ):
            if value is not None:
                _sha(value, label)
        if self.provider_id is not None:
            _identifier(self.provider_id, "unsafe pickle provider id")
        globals_value = _sorted_unique(self.exact_globals, "unsafe pickle globals")
        for item in globals_value:
            if not _GLOBAL_RE.fullmatch(item):
                raise ValueError("unsafe pickle global is invalid")
        object.__setattr__(self, "exact_globals", globals_value)
        if self.exact_globals_sha256 is not None and (
            self.exact_globals_sha256 != _hash_array(globals_value)
        ):
            raise ValueError("unsafe pickle exact-globals hash is invalid")


@dataclass(frozen=True)
class SeparationCheckpointEvidence:
    """Synthetic checkpoint reports; not authority or execution evidence."""

    checkpoint_id: str
    declared_format: str
    classified_container_kind: str
    checkpoint_sha256: str
    checkpoint_bytes: int
    classification_evidence_sha256: str
    terms: SeparationCheckpointTermsEvidence
    loader: SeparationCheckpointLoaderEvidence
    unsafe_pickle_exception: SeparationUnsafePickleExceptionEvidence

    def __post_init__(self) -> None:
        _identifier(self.checkpoint_id, "checkpoint id")
        if self.declared_format not in _DECLARED_FORMATS:
            raise ValueError("declared checkpoint format is unsupported")
        if self.classified_container_kind not in _CONTAINER_KINDS:
            raise ValueError("classified checkpoint container kind is unsupported")
        _sha(self.checkpoint_sha256, "checkpoint sha256")
        _positive_int(self.checkpoint_bytes, "checkpoint bytes")
        _sha(
            self.classification_evidence_sha256,
            "checkpoint classification evidence sha256",
        )
        if type(self.terms) is not SeparationCheckpointTermsEvidence:
            raise ValueError("checkpoint terms must be exact parent evidence")
        if type(self.loader) is not SeparationCheckpointLoaderEvidence:
            raise ValueError("checkpoint loader must be exact parent evidence")
        if (
            type(self.unsafe_pickle_exception)
            is not SeparationUnsafePickleExceptionEvidence
        ):
            raise ValueError(
                "unsafe pickle exception must be exact parent evidence"
            )


@dataclass(frozen=True, init=False)
class SeparationCheckpointPolicyRecord(Mapping[str, Any]):
    """Validated, deeply immutable checkpoint-policy decision."""

    _document: Mapping[str, Any]
    _evidence: SeparationCheckpointEvidence

    def __getitem__(self, key: str) -> Any:
        return self._document[key]

    def __iter__(self) -> Any:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


def build_separation_checkpoint_policy(
    evidence: SeparationCheckpointEvidence,
) -> SeparationCheckpointPolicyRecord:
    """Evaluate one synthetic report without inspecting checkpoint bytes."""

    checked = _exact_reported_evidence(evidence)
    terms = checked.terms
    loader = checked.loader
    unsafe = checked.unsafe_pickle_exception
    known = _KNOWN_CHECKPOINTS.get(checked.checkpoint_sha256)
    classified_kind = (
        known["classified_container_kind"] if known is not None else "uninspected"
    )
    exception_complete = _unsafe_exception_complete(checked)
    blockers: set[str] = set()
    advisories: set[str] = set()
    blockers.update(
        {
            "checkpoint_execution_policy_not_implemented",
            "trusted_evidence_cross_binding_unimplemented",
        }
    )

    if classified_kind == "uninspected":
        blockers.add("checkpoint_container_uninspected")
    if checked.declared_format != classified_kind:
        blockers.add("checkpoint_format_classification_mismatch")
    if checked.classified_container_kind != classified_kind:
        blockers.add("checkpoint_reported_classification_disagrees")
    terms_verified = bool(
        terms.terms_verified
        and known is not None
        and known["terms_verified"] is True
    )
    allowed_use_verified = bool(
        terms.allowed_use_verified
        and known is not None
        and known["allowed_use_verified"] is True
    )
    if not terms_verified:
        blockers.add("checkpoint_terms_unverified")
    if (
        not allowed_use_verified
        or "private_development" not in terms.allowed_uses
    ):
        blockers.add("checkpoint_allowed_use_unverified")

    expected_mode = _EXPECTED_LOADER_MODE.get(classified_kind)
    if expected_mode is None or loader.deserialization_mode != expected_mode:
        blockers.add("checkpoint_loader_mode_incompatible")
    if classified_kind == "torch-state-dict":
        if loader.weights_only is not True:
            blockers.add("checkpoint_weights_only_required")
    elif classified_kind == "torch-pickle-model-package":
        if loader.weights_only is not False:
            blockers.add("checkpoint_pickle_requires_unsafe_mode")
        blockers.update(
            {
                "checkpoint_is_pickle_model_package",
                "unsafe_deserialization_not_approved",
            }
        )
        if exception_complete:
            advisories.add("unsafe_pickle_exception_metadata_recorded_only")
    elif classified_kind != "uninspected" and loader.weights_only != "not_applicable":
        blockers.add("checkpoint_weights_only_policy_mismatch")

    if unsafe.explicitly_approved and not exception_complete:
        blockers.add("unsafe_pickle_exception_incomplete")
    if unsafe.explicitly_approved and (
        unsafe.provider_id not in SUPPORTED_UNSAFE_PICKLE_PROVIDER_IDS
    ):
        blockers.add("unsafe_pickle_provider_unsupported")
    if unsafe.explicitly_approved and (
        classified_kind != "torch-pickle-model-package"
    ):
        blockers.add("unsafe_pickle_exception_not_applicable")

    blocker_list = tuple(sorted(blockers))
    advisory_list = tuple(sorted(advisories))
    payload = {
        "schema": SEPARATION_CHECKPOINT_POLICY_SCHEMA,
        "policy_id": SEPARATION_CHECKPOINT_POLICY_ID,
        "evidence_scope": "private_development",
        "publication_scope": "private_local_contract_evidence",
        "public_redacted_projection_available": False,
        "evidence_authority": "synthetic_contract_only",
        "reported_evidence_trusted": False,
        "checkpoint_execution_policy_supported": (
            CHECKPOINT_EXECUTION_POLICY_SUPPORTED
        ),
        "checkpoint": {
            "checkpoint_id": checked.checkpoint_id,
            "declared_format": checked.declared_format,
            "reported_container_kind": checked.classified_container_kind,
            "classified_container_kind": classified_kind,
            "sha256": checked.checkpoint_sha256,
            "bytes": checked.checkpoint_bytes,
            "classification_evidence_sha256": (
                checked.classification_evidence_sha256
            ),
            "known_checkpoint_policy_id": (
                known["policy_id"] if known is not None else None
            ),
        },
        "terms": {
            **_terms_document(terms),
            "policy_terms_verified": terms_verified,
            "policy_allowed_use_verified": allowed_use_verified,
        },
        "loader": _loader_document(loader),
        "unsafe_pickle_exception": _unsafe_document(
            unsafe,
            complete=exception_complete,
        ),
        "decision": {
            "status": "blocked",
            "run_status": "not_run",
            "private_development_checkpoint_eligible": False,
            "worker_start_permitted": False,
            "blockers": blocker_list,
            "advisories": advisory_list,
        },
        "effects": {
            "filesystem_inspected": False,
            "checkpoint_opened": False,
            "checkpoint_loaded": False,
            "checkpoint_deserialized": False,
            "model_imported": False,
            "process_started": False,
            "network_used": False,
            "audio_read": False,
            "files_written": False,
            "publication_permitted": False,
        },
    }
    _path_free(payload, "checkpoint policy")
    document = {**payload, "policy_sha256": _hash(payload)}
    return _new_record(document, checked)


def validate_separation_checkpoint_policy(
    document: Mapping[str, Any],
    *,
    reported_evidence: SeparationCheckpointEvidence,
) -> SeparationCheckpointPolicyRecord:
    """Validate a projection against the same exact synthetic report."""

    expected = build_separation_checkpoint_policy(reported_evidence)
    value = _json_object(document, "checkpoint policy")
    if value != _thaw(expected):
        raise ValueError("checkpoint policy does not match reported evidence")
    return _new_record(value, reported_evidence)


def separation_checkpoint_policy_sha256(document: Mapping[str, Any]) -> str:
    """Return the canonical policy hash after excluding its self-hash."""

    value = _json_object(document, "checkpoint policy")
    value.pop("policy_sha256", None)
    return _hash(value)


def _unsafe_exception_complete(evidence: SeparationCheckpointEvidence) -> bool:
    value = evidence.unsafe_pickle_exception
    known = _KNOWN_CHECKPOINTS.get(evidence.checkpoint_sha256)
    classified_kind = (
        known["classified_container_kind"] if known is not None else "uninspected"
    )
    return bool(
        classified_kind == "torch-pickle-model-package"
        and evidence.loader.weights_only is False
        and evidence.loader.deserialization_mode
        == "torch-load-pickle-model-package"
        and value.explicitly_approved
        and value.evidence_scope == "private_development"
        and value.approval_sha256 is not None
        and value.provider_id is not None
        and value.provider_sha256 is not None
        and value.provider_qualification_sha256 is not None
        and value.exact_globals
        and value.exact_globals_sha256 == _hash_array(value.exact_globals)
        and value.checkpoint_sha256 == evidence.checkpoint_sha256
    )


def _terms_document(value: SeparationCheckpointTermsEvidence) -> dict[str, Any]:
    return {
        "reported_terms_sha256": value.terms_sha256,
        "reported_terms_verified": value.terms_verified,
        "reported_license_expression": value.license_expression,
        "reported_allowed_uses": list(value.allowed_uses),
        "reported_allowed_use_evidence_sha256": (
            value.allowed_use_evidence_sha256
        ),
        "reported_allowed_use_verified": value.allowed_use_verified,
    }


def _loader_document(value: SeparationCheckpointLoaderEvidence) -> dict[str, Any]:
    return {
        "loader_id": value.loader_id,
        "loader_sha256": value.loader_sha256,
        "deserialization_mode": value.deserialization_mode,
        "weights_only": value.weights_only,
    }


def _unsafe_document(
    value: SeparationUnsafePickleExceptionEvidence,
    *,
    complete: bool,
) -> dict[str, Any]:
    provider_supported = bool(
        value.provider_id in SUPPORTED_UNSAFE_PICKLE_PROVIDER_IDS
    )
    return {
        "explicitly_approved": value.explicitly_approved,
        "evidence_scope": value.evidence_scope,
        "approval_sha256": value.approval_sha256,
        "provider_id": value.provider_id,
        "provider_sha256": value.provider_sha256,
        "provider_qualification_sha256": value.provider_qualification_sha256,
        "exact_globals": list(value.exact_globals),
        "exact_globals_sha256": value.exact_globals_sha256,
        "checkpoint_sha256": value.checkpoint_sha256,
        "reported_evidence_complete": complete,
        "qualifying_provider_supported": provider_supported,
        "qualified_for_private_development": bool(
            complete and provider_supported
        ),
        "waives_pickle_blocker": False,
    }


def _exact_reported_evidence(value: Any) -> SeparationCheckpointEvidence:
    if type(value) is not SeparationCheckpointEvidence:
        raise ValueError("checkpoint policy requires exact synthetic evidence")
    return value


def _new_record(
    document: Mapping[str, Any],
    evidence: SeparationCheckpointEvidence,
) -> SeparationCheckpointPolicyRecord:
    value = _json_object(document, "checkpoint policy")
    if value.get("schema") != SEPARATION_CHECKPOINT_POLICY_SCHEMA:
        raise ValueError("unsupported checkpoint policy schema")
    if value.get("policy_sha256") != separation_checkpoint_policy_sha256(value):
        raise ValueError("checkpoint policy hash is invalid")
    _path_free(value, "checkpoint policy")
    decision = value.get("decision")
    if (
        not isinstance(decision, dict)
        or decision.get("status") != "blocked"
        or decision.get("run_status") != "not_run"
        or decision.get("private_development_checkpoint_eligible") is not False
        or decision.get("worker_start_permitted") is not False
        or value.get("checkpoint_execution_policy_supported") is not False
    ):
        raise ValueError("checkpoint policy must remain blocked and not run")
    blockers = decision.get("blockers")
    advisories = decision.get("advisories")
    if (
        not isinstance(blockers, list)
        or blockers != sorted(set(blockers))
        or not isinstance(advisories, list)
        or advisories != sorted(set(advisories))
    ):
        raise ValueError("checkpoint policy decisions must be sorted and unique")
    effects = value.get("effects")
    if not isinstance(effects, dict) or any(item is not False for item in effects.values()):
        raise ValueError("checkpoint policy effects must all be false")
    record = object.__new__(SeparationCheckpointPolicyRecord)
    object.__setattr__(record, "_document", _freeze(value))
    object.__setattr__(record, "_evidence", evidence)
    return record


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


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise ValueError(f"{label} is not a lowercase SHA-256")
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ValueError(f"{label} is invalid")
    return value


def _license_expression(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 256
        or value != value.strip()
        or any(
            character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ._+():-"
            for character in value
        )
    ):
        raise ValueError(f"{label} is invalid")
    return value


def _positive_int(value: Any, label: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
        or value > _MAX_CHECKPOINT_BYTES
    ):
        raise ValueError(f"{label} must be a positive integer")
    return value


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _sorted_unique(values: Sequence[str], label: str) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)) or len(values) > 256:
        raise ValueError(f"{label} must be an array")
    checked = tuple(values)
    if any(
        not isinstance(item, str) or len(item.encode("utf-8")) > 256
        for item in checked
    ):
        raise ValueError(f"{label} must contain text")
    if checked != tuple(sorted(set(checked))):
        raise ValueError(f"{label} must be sorted and unique")
    return checked


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
    "CHECKPOINT_EXECUTION_POLICY_SUPPORTED",
    "DEMUCS_HTDEMUCS_CHECKPOINT_SHA256",
    "SEPARATION_CHECKPOINT_POLICY_ID",
    "SEPARATION_CHECKPOINT_POLICY_SCHEMA",
    "SUPPORTED_UNSAFE_PICKLE_PROVIDER_IDS",
    "SeparationCheckpointEvidence",
    "SeparationCheckpointLoaderEvidence",
    "SeparationCheckpointPolicyRecord",
    "SeparationCheckpointTermsEvidence",
    "SeparationUnsafePickleExceptionEvidence",
    "build_separation_checkpoint_policy",
    "separation_checkpoint_policy_sha256",
    "validate_separation_checkpoint_policy",
]
