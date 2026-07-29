"""Backend-neutral contracts for local source-separation experiments.

This module deliberately contains no audio, model, NumPy or Torch imports.
Heavy backends exchange path-bearing request/result DTOs with a future parent
runner.  The parent runner is responsible for persistence, hashing artifacts
and constructing a path-free, shareable separation-run receipt.  New receipts
use v2; the validator retains strict read compatibility with canonical v1
receipts whose leakage evidence was represented by bounded floats.

The receipt contract is intentionally strict:

* only terminal runs can be represented;
* only ``complete`` runs are loadable;
* every target has one same-role, same-clock residual;
* the residual is defined from persisted evidence;
* failed, cancelled and abandoned runs expose no artifacts; and
* the semantic receipt hash excludes only ``receipt_sha256`` itself.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol, Sequence

from .source_roles import canonical_source_role, prepared_source_role_ids


SEPARATION_REQUEST_SCHEMA = "sunofriend.separation-request.v1"
SEPARATION_RUN_SCHEMA_V1 = "sunofriend.separation-run.v1"
SEPARATION_RUN_SCHEMA_V2 = "sunofriend.separation-run.v2"
SEPARATION_RUN_SCHEMA = SEPARATION_RUN_SCHEMA_V2
SEPARATION_RUN_SCHEMAS = frozenset(
    {SEPARATION_RUN_SCHEMA_V1, SEPARATION_RUN_SCHEMA_V2}
)
SEPARATION_RESIDUAL_DEFINITION = (
    "persisted-source-minus-persisted-target-v1"
)
SEPARATION_TERMINAL_STATUSES = frozenset(
    {"complete", "failed", "cancelled", "abandoned"}
)
SEPARATION_FAILURE_STATUSES = frozenset(
    SEPARATION_TERMINAL_STATUSES - {"complete"}
)
SEPARATION_QUALITY_STATUSES = frozenset(
    {"passed", "review_required"}
)

SeparationCancellationPredicate = Callable[[], bool]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA256_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_RUN_ID_RE = re.compile(r"^separation-run:[0-9a-f]{64}$")
_NODE_ID_RE = re.compile(r"^node:[0-9a-f]{64}$")
_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,127}$")
_QUALIFIED_ID_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$"
)
_ERROR_CODE_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{7,64}$")
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[a-zA-Z]:[\\/]")
_PRIVATE_PATH_FRAGMENT_RE = re.compile(
    r"(?:^|[\s'\"(])(?:/Users/|/home/|/private/|/var/folders/)"
)
_FORBIDDEN_PATH_KEYS = frozenset(
    {
        "path",
        "source_path",
        "checkpoint_path",
        "command_path",
        "output_path",
        "working_directory",
        "cwd",
        "home",
    }
)
_RECEIPT_FIELDS_V1 = frozenset(
    {
        "schema",
        "receipt_sha256",
        "run_id",
        "request_fingerprint_sha256",
        "status",
        "loadable",
        "source",
        "scope",
        "backend",
        "checkpoint",
        "roles",
        "execution",
        "outputs",
        "quality",
        "effects",
        "error",
    }
)
_RECEIPT_FIELDS_V2 = frozenset(
    set(_RECEIPT_FIELDS_V1) | {"run_plan_sha256", "run_plan"}
)
_RUN_PLAN_SCHEMA = "sunofriend.separation-run-plan.v1"
_RUN_PLAN_FIELDS = frozenset(
    {
        "schema",
        "request_fingerprint_sha256",
        "runner",
        "backend",
        "checkpoint",
        "runtime",
        "device",
        "command",
        "requested_roles",
        "settings",
        "seed",
    }
)
_RUNNER_FIELDS = frozenset(
    {
        "schema",
        "version",
        "module",
        "module_sha256",
        "package",
        "package_version",
        "backend_policy",
        "cache_replay",
    }
)
_PLAN_BACKEND_FIELDS = frozenset(
    {
        "backend_id",
        "class",
        "module_sha256",
        "package",
        "version",
        "commit",
        "code_license",
        "training_data_note",
    }
)
_PLAN_CHECKPOINT_FIELDS = frozenset(
    {
        "checkpoint_id",
        "sha256",
        "weights_license",
        "distribution_policy",
    }
)
_SOURCE_FIELDS = frozenset(
    {
        "source_id",
        "source_sha256",
        "canonical_sha256",
        "geometry",
    }
)
_SCOPE_FIELDS = frozenset({"mode", "parent_node_id"})
_BACKEND_FIELDS = frozenset(
    {
        "backend_id",
        "package",
        "version",
        "commit",
        "code_license",
        "training_data_note",
    }
)
_CHECKPOINT_FIELDS = frozenset(
    {
        "checkpoint_id",
        "sha256",
        "weights_license",
        "hash_verified_before_load",
        "distribution_policy",
    }
)
_ROLES_FIELDS = frozenset({"requested", "actual"})
_EXECUTION_FIELDS = frozenset(
    {
        "runtime",
        "device",
        "settings",
        "seed",
        "wall_time_seconds",
        "command",
        "network_used",
    }
)
_OUTPUT_FIELDS = frozenset({"targets", "residuals"})
_ARTIFACT_FIELDS = frozenset(
    {
        "role",
        "path",
        "sha256",
        "geometry",
        "peak",
        "rms",
        "silence_fraction",
        "clipped_samples",
    }
)
_RESIDUAL_FIELDS = frozenset(
    set(_ARTIFACT_FIELDS) | {"target_sha256", "definition"}
)
_QUALITY_FIELDS = frozenset(
    {
        "path",
        "sha256",
        "status",
        "reconstruction",
        "leakage",
        "reconstruction_is_accuracy_evidence",
    }
)
_RECONSTRUCTION_FIELDS = frozenset(
    {
        "maximum_absolute_error",
        "rms_error",
        "threshold",
        "passed",
    }
)
_LEAKAGE_FIELDS = frozenset(
    {"status", "metric", "score", "reference_id"}
)
_LEAKAGE_STATUSES = frozenset({"measured", "not_measured"})
_EFFECT_FIELDS = frozenset(
    {
        "network_used",
        "model_downloaded",
        "source_mutated",
        "checkpoint_mutated",
        "outside_output_writes",
    }
)
_ERROR_FIELDS = frozenset({"code", "message", "retryable"})
_GEOMETRY_FIELDS = frozenset(
    {"sample_rate", "channels", "frames", "duration_seconds"}
)


@dataclass(frozen=True)
class SeparationAudioGeometry:
    """Clock and shape of one persisted audio asset."""

    sample_rate: int
    channels: int
    frames: int
    duration_seconds: float

    def __post_init__(self) -> None:
        _validate_geometry(self.to_dict(), "audio geometry")

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "frames": self.frames,
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(
        cls, document: Mapping[str, Any]
    ) -> "SeparationAudioGeometry":
        value = _mapping(document, "audio geometry")
        _exact_fields(value, _GEOMETRY_FIELDS, "audio geometry")
        return cls(
            sample_rate=_strict_int(
                value["sample_rate"], "audio geometry.sample_rate"
            ),
            channels=_strict_int(
                value["channels"], "audio geometry.channels"
            ),
            frames=_strict_int(value["frames"], "audio geometry.frames"),
            duration_seconds=_finite_float(
                value["duration_seconds"],
                "audio geometry.duration_seconds",
            ),
        )


@dataclass(frozen=True)
class SeparationRequest:
    """Path-bearing request consumed only by a local separation runner."""

    source_path: Path
    output_dir: Path
    checkpoint_path: Path
    source_id: str
    source_sha256: str
    canonical_sha256: str
    source_geometry: SeparationAudioGeometry
    scope: str
    parent_node_id: str | None
    backend_id: str
    checkpoint_id: str
    checkpoint_sha256: str
    requested_roles: tuple[str, ...]
    settings: Mapping[str, Any] = field(default_factory=dict)
    seed: int | None = None
    offline_required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_path", Path(self.source_path))
        object.__setattr__(self, "output_dir", Path(self.output_dir))
        object.__setattr__(
            self, "checkpoint_path", Path(self.checkpoint_path)
        )
        object.__setattr__(
            self, "requested_roles", tuple(self.requested_roles)
        )
        object.__setattr__(self, "settings", _freeze_json(self.settings))
        self.validate()

    @classmethod
    def create(
        cls,
        *,
        source_path: str | Path,
        output_dir: str | Path,
        checkpoint_path: str | Path,
        source_id: str,
        source_sha256: str,
        canonical_sha256: str,
        source_geometry: SeparationAudioGeometry | Mapping[str, Any],
        scope: str,
        parent_node_id: str | None,
        backend_id: str,
        checkpoint_id: str,
        checkpoint_sha256: str,
        requested_roles: Sequence[str],
        settings: Mapping[str, Any] | None = None,
        seed: int | None = None,
        offline_required: bool = True,
    ) -> "SeparationRequest":
        """Resolve request paths without reading, creating or changing them."""

        geometry = (
            source_geometry
            if isinstance(source_geometry, SeparationAudioGeometry)
            else SeparationAudioGeometry.from_dict(source_geometry)
        )
        return cls(
            source_path=Path(source_path).expanduser().resolve(),
            output_dir=Path(output_dir).expanduser().resolve(),
            checkpoint_path=Path(checkpoint_path).expanduser().resolve(),
            source_id=source_id,
            source_sha256=source_sha256,
            canonical_sha256=canonical_sha256,
            source_geometry=geometry,
            scope=scope,
            parent_node_id=parent_node_id,
            backend_id=backend_id,
            checkpoint_id=checkpoint_id,
            checkpoint_sha256=checkpoint_sha256,
            requested_roles=tuple(sorted(requested_roles)),
            settings=settings or {},
            seed=seed,
            offline_required=offline_required,
        )

    def validate(self) -> None:
        """Validate the deterministic request without touching the filesystem."""

        for value, label in (
            (self.source_path, "source_path"),
            (self.output_dir, "output_dir"),
            (self.checkpoint_path, "checkpoint_path"),
        ):
            if not value.is_absolute():
                raise ValueError(
                    f"separation request {label} must be absolute"
                )
        if self.source_path == self.output_dir:
            raise ValueError(
                "separation request source_path and output_dir must differ"
            )
        if self.checkpoint_path == self.output_dir:
            raise ValueError(
                "separation request checkpoint_path and output_dir must differ"
            )
        _source_identity(
            self.source_id,
            self.source_sha256,
            label="separation request source",
        )
        _sha256(self.canonical_sha256, "canonical_sha256")
        _sha256(self.checkpoint_sha256, "checkpoint_sha256")
        _safe_identifier(self.backend_id, "backend_id")
        _safe_identifier(self.checkpoint_id, "checkpoint_id")
        _validate_scope(
            {"mode": self.scope, "parent_node_id": self.parent_node_id}
        )
        _canonical_roles(
            self.requested_roles,
            "requested_roles",
            require_sorted=True,
            allow_empty=False,
        )
        _validate_json_value(
            self.settings, "settings", forbid_private_paths=True
        )
        if self.seed is not None:
            _strict_int(self.seed, "seed")
        if self.offline_required is not True:
            raise ValueError(
                "separation requests must require offline inference"
            )

    def fingerprint_document(self) -> dict[str, Any]:
        """Return the path-free inputs used for cache/request identity."""

        return {
            "schema": SEPARATION_REQUEST_SCHEMA,
            "source": {
                "source_id": self.source_id,
                "source_sha256": self.source_sha256,
                "canonical_sha256": self.canonical_sha256,
                "geometry": self.source_geometry.to_dict(),
            },
            "scope": {
                "mode": self.scope,
                "parent_node_id": self.parent_node_id,
            },
            "backend_id": self.backend_id,
            "checkpoint": {
                "checkpoint_id": self.checkpoint_id,
                "sha256": self.checkpoint_sha256,
            },
            "requested_roles": list(self.requested_roles),
            "settings": _thaw_json(self.settings),
            "seed": self.seed,
            "offline_required": True,
        }

    @property
    def fingerprint_sha256(self) -> str:
        return separation_request_fingerprint_sha256(
            source=self.fingerprint_document()["source"],
            scope=self.fingerprint_document()["scope"],
            backend_id=self.backend_id,
            checkpoint_id=self.checkpoint_id,
            checkpoint_sha256=self.checkpoint_sha256,
            requested_roles=self.requested_roles,
            settings=self.settings,
            seed=self.seed,
        )


@dataclass(frozen=True)
class SeparationBackendOutput:
    """Private paths returned by one backend for later parent verification."""

    role: str
    target_path: Path
    residual_path: Path
    residual_definition: str = SEPARATION_RESIDUAL_DEFINITION

    def __post_init__(self) -> None:
        role = _canonical_role(self.role, "backend output role")
        object.__setattr__(self, "role", role)
        target = Path(self.target_path)
        residual = Path(self.residual_path)
        object.__setattr__(self, "target_path", target)
        object.__setattr__(self, "residual_path", residual)
        if target == residual:
            raise ValueError(
                "backend target_path and residual_path must differ"
            )
        if self.residual_definition != SEPARATION_RESIDUAL_DEFINITION:
            raise ValueError("unsupported separation residual definition")


@dataclass(frozen=True)
class SeparationError:
    """Path-free terminal error safe to copy into a public receipt."""

    code: str
    message: str
    retryable: bool

    def __post_init__(self) -> None:
        _validate_error(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }


@dataclass(frozen=True)
class SeparationResult:
    """Backend result DTO; not itself a persisted or shareable receipt."""

    status: str
    outputs: tuple[SeparationBackendOutput, ...] = ()
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    error: SeparationError | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "outputs", tuple(self.outputs))
        object.__setattr__(
            self, "diagnostics", _freeze_json(self.diagnostics)
        )
        if self.status not in SEPARATION_TERMINAL_STATUSES:
            raise ValueError("separation result status must be terminal")
        roles = [output.role for output in self.outputs]
        if len(set(roles)) != len(roles):
            raise ValueError("separation result output roles must be unique")
        if roles != sorted(roles):
            raise ValueError(
                "separation result outputs must use canonical role order"
            )
        _validate_json_value(
            self.diagnostics,
            "separation result diagnostics",
            forbid_private_paths=True,
        )
        if self.status == "complete":
            if not self.outputs:
                raise ValueError(
                    "complete separation result requires outputs"
                )
            if self.error is not None:
                raise ValueError(
                    "complete separation result must not contain an error"
                )
        else:
            if self.outputs:
                raise ValueError(
                    "non-complete separation result must not publish outputs"
                )
            if self.error is None:
                raise ValueError(
                    "non-complete separation result requires an error"
                )

    @property
    def succeeded(self) -> bool:
        return self.status == "complete"

    @property
    def cancelled(self) -> bool:
        return self.status == "cancelled"


class SeparationBackend(Protocol):
    """Injectable, model-neutral boundary used by a future parent runner."""

    @property
    def backend_id(self) -> str:
        """Return the stable backend identifier bound into the request."""

    def run(
        self,
        request: SeparationRequest,
        *,
        cancellation_requested: (
            SeparationCancellationPredicate | None
        ) = None,
    ) -> SeparationResult:
        """Run offline separation without installing or downloading a model."""


@dataclass(frozen=True)
class SeparationRunReceipt:
    """Immutable validated representation of one shareable terminal receipt."""

    receipt_sha256: str
    run_id: str
    request_fingerprint_sha256: str
    status: str
    loadable: bool
    source: Mapping[str, Any]
    scope: Mapping[str, Any]
    backend: Mapping[str, Any]
    checkpoint: Mapping[str, Any]
    roles: Mapping[str, Any]
    execution: Mapping[str, Any]
    outputs: Mapping[str, Any]
    quality: Mapping[str, Any] | None
    effects: Mapping[str, Any]
    error: Mapping[str, Any] | None
    run_plan_sha256: str | None = None
    run_plan: Mapping[str, Any] | None = None
    schema: str = SEPARATION_RUN_SCHEMA

    def __post_init__(self) -> None:
        for name in (
            "source",
            "scope",
            "backend",
            "checkpoint",
            "roles",
            "execution",
            "outputs",
            "effects",
        ):
            object.__setattr__(
                self, name, _freeze_json(getattr(self, name))
            )
        if self.quality is not None:
            object.__setattr__(
                self, "quality", _freeze_json(self.quality)
            )
        if self.error is not None:
            object.__setattr__(self, "error", _freeze_json(self.error))
        if self.run_plan is not None:
            object.__setattr__(
                self, "run_plan", _freeze_json(self.run_plan)
            )
        validate_separation_run_receipt(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        document = {
            "schema": self.schema,
            "receipt_sha256": self.receipt_sha256,
            "run_id": self.run_id,
            "request_fingerprint_sha256": (
                self.request_fingerprint_sha256
            ),
            "status": self.status,
            "loadable": self.loadable,
            "source": _thaw_json(self.source),
            "scope": _thaw_json(self.scope),
            "backend": _thaw_json(self.backend),
            "checkpoint": _thaw_json(self.checkpoint),
            "roles": _thaw_json(self.roles),
            "execution": _thaw_json(self.execution),
            "outputs": _thaw_json(self.outputs),
            "quality": (
                None
                if self.quality is None
                else _thaw_json(self.quality)
            ),
            "effects": _thaw_json(self.effects),
            "error": (
                None if self.error is None else _thaw_json(self.error)
            ),
        }
        if self.schema == SEPARATION_RUN_SCHEMA_V2:
            document["run_plan_sha256"] = self.run_plan_sha256
            document["run_plan"] = (
                None
                if self.run_plan is None
                else _thaw_json(self.run_plan)
            )
        return document

    def canonical_bytes(self) -> bytes:
        """Return the canonical complete receipt, including its self-hash."""

        return _canonical_json_bytes(self.to_dict())

    @classmethod
    def from_dict(
        cls, document: Mapping[str, Any]
    ) -> "SeparationRunReceipt":
        canonical = validate_separation_run_receipt(document)
        return cls(
            schema=canonical["schema"],
            receipt_sha256=canonical["receipt_sha256"],
            run_id=canonical["run_id"],
            request_fingerprint_sha256=canonical[
                "request_fingerprint_sha256"
            ],
            status=canonical["status"],
            loadable=canonical["loadable"],
            source=canonical["source"],
            scope=canonical["scope"],
            backend=canonical["backend"],
            checkpoint=canonical["checkpoint"],
            roles=canonical["roles"],
            execution=canonical["execution"],
            outputs=canonical["outputs"],
            quality=canonical["quality"],
            effects=canonical["effects"],
            error=canonical["error"],
            run_plan_sha256=canonical.get("run_plan_sha256"),
            run_plan=canonical.get("run_plan"),
        )

    @classmethod
    def from_json(
        cls, value: str | bytes
    ) -> "SeparationRunReceipt":
        try:
            text = (
                value.decode("utf-8")
                if isinstance(value, bytes)
                else value
            )
            document = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                "separation receipt must be valid UTF-8 JSON"
            ) from exc
        if not isinstance(document, Mapping):
            raise ValueError("separation receipt must contain one JSON object")
        return cls.from_dict(document)


def build_separation_run_receipt(
    *,
    run_id: str,
    run_plan_sha256: str,
    run_plan: Mapping[str, Any],
    request_fingerprint_sha256: str,
    status: str,
    loadable: bool,
    source: Mapping[str, Any],
    scope: Mapping[str, Any],
    backend: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    roles: Mapping[str, Any],
    execution: Mapping[str, Any],
    outputs: Mapping[str, Any],
    quality: Mapping[str, Any] | None,
    effects: Mapping[str, Any],
    error: Mapping[str, Any] | SeparationError | None,
) -> SeparationRunReceipt:
    """Canonicalize, self-hash and freeze one terminal receipt."""

    plan_document = _validate_run_plan(
        run_plan,
        run_plan_sha256=run_plan_sha256,
        run_id=run_id,
    )
    _sha256(
        request_fingerprint_sha256, "request_fingerprint_sha256"
    )
    if status not in SEPARATION_TERMINAL_STATUSES:
        raise ValueError("separation receipt status must be terminal")
    if not isinstance(loadable, bool) or loadable is not (
        status == "complete"
    ):
        raise ValueError(
            "separation receipt status/loadable relationship is invalid"
        )
    source_document = _validate_source(source)
    scope_document = _validate_scope(scope)
    backend_document = _validate_backend(
        backend, require_commit=status == "complete"
    )
    checkpoint_document = _validate_checkpoint(
        checkpoint, require_verified=status == "complete"
    )
    roles_document = _validate_roles(
        roles, allow_actual_empty=status != "complete"
    )
    execution_document = _validate_execution(execution)
    effects_document = _validate_effects(effects)
    if (
        effects_document["network_used"]
        is not execution_document["network_used"]
    ):
        raise ValueError(
            "execution and effects network_used values must match"
        )
    outputs_value = _mapping(outputs, "outputs")
    _exact_fields(outputs_value, _OUTPUT_FIELDS, "outputs")
    if status == "complete":
        targets = _validate_artifacts(
            outputs_value["targets"],
            label="outputs.targets",
            residual=False,
            source_geometry=source_document["geometry"],
        )
        residuals = _validate_artifacts(
            outputs_value["residuals"],
            label="outputs.residuals",
            residual=True,
            source_geometry=source_document["geometry"],
        )
        _validate_target_residual_pairs(
            targets,
            residuals,
            actual_roles=roles_document["actual"],
        )
        quality_document = _validate_quality(
            quality,
            actual_roles=roles_document["actual"],
            schema=SEPARATION_RUN_SCHEMA,
        )
        _require_quality_status_for_outputs(
            targets, residuals, quality_document
        )
        _require_quality_status_for_requested_roles(
            roles_document,
            quality_document,
        )
        all_paths = [
            *(item["path"] for item in targets),
            *(item["path"] for item in residuals),
            quality_document["path"],
        ]
        _require_unique_artifact_paths(all_paths)
        if error is not None:
            raise ValueError(
                "complete separation receipt must not contain an error"
            )
        if execution_document["network_used"] is not False:
            raise ValueError(
                "complete separation receipt must record offline inference"
            )
        if any(effects_document.values()):
            raise ValueError(
                "complete separation receipt must record no forbidden effects"
            )
        outputs_document = {
            "targets": targets,
            "residuals": residuals,
        }
        error_document = None
    else:
        if (
            outputs_value["targets"] != []
            or outputs_value["residuals"] != []
        ):
            raise ValueError(
                "non-loadable separation receipt must expose no artifacts"
            )
        if quality is not None:
            raise ValueError(
                "non-loadable separation receipt must expose no quality artifact"
            )
        error_value = (
            error.to_dict()
            if isinstance(error, SeparationError)
            else error
        )
        error_document = _validate_error(error_value)
        outputs_document = {"targets": [], "residuals": []}
        quality_document = None

    unsigned = {
        "schema": SEPARATION_RUN_SCHEMA,
        "run_id": run_id,
        "request_fingerprint_sha256": request_fingerprint_sha256,
        "status": status,
        "loadable": loadable,
        "source": source_document,
        "scope": scope_document,
        "backend": backend_document,
        "checkpoint": checkpoint_document,
        "roles": roles_document,
        "execution": execution_document,
        "outputs": outputs_document,
        "quality": quality_document,
        "effects": effects_document,
        "error": error_document,
    }
    expected_fingerprint = separation_request_fingerprint_sha256(
        source=source_document,
        scope=scope_document,
        backend_id=backend_document["backend_id"],
        checkpoint_id=checkpoint_document["checkpoint_id"],
        checkpoint_sha256=checkpoint_document["sha256"],
        requested_roles=roles_document["requested"],
        settings=execution_document["settings"],
        seed=execution_document["seed"],
    )
    if request_fingerprint_sha256 != expected_fingerprint:
        raise ValueError(
            "request_fingerprint_sha256 does not bind the separation request"
        )
    _cross_bind_run_plan(
        plan_document,
        request_fingerprint_sha256=request_fingerprint_sha256,
        backend=backend_document,
        checkpoint=checkpoint_document,
        roles=roles_document,
        execution=execution_document,
    )
    unsigned["run_plan_sha256"] = run_plan_sha256
    unsigned["run_plan"] = plan_document
    document = {
        **unsigned,
        "receipt_sha256": separation_run_receipt_sha256(unsigned),
    }
    return SeparationRunReceipt.from_dict(document)


def separation_run_receipt_sha256(
    document: Mapping[str, Any],
) -> str:
    """Hash a receipt's semantic content, excluding only its self-hash."""

    value = _mapping(document, "separation receipt")
    unsigned = {
        key: _thaw_json(item)
        for key, item in value.items()
        if key != "receipt_sha256"
    }
    return hashlib.sha256(_canonical_json_bytes(unsigned)).hexdigest()


def separation_request_fingerprint_sha256(
    *,
    source: Mapping[str, Any],
    scope: Mapping[str, Any],
    backend_id: str,
    checkpoint_id: str,
    checkpoint_sha256: str,
    requested_roles: Sequence[str],
    settings: Mapping[str, Any],
    seed: int | None,
) -> str:
    """Return the path-free cache/request identity used by the parent runner."""

    source_document = _validate_source(source)
    scope_document = _validate_scope(scope)
    backend = _safe_identifier(backend_id, "backend_id")
    checkpoint = _safe_identifier(checkpoint_id, "checkpoint_id")
    checkpoint_hash = _sha256(
        checkpoint_sha256, "checkpoint_sha256"
    )
    roles = _canonical_roles(
        requested_roles,
        "requested_roles",
        require_sorted=True,
        allow_empty=False,
    )
    settings_document = _mapping(settings, "settings")
    _validate_json_value(
        settings_document, "settings", forbid_private_paths=True
    )
    if seed is not None:
        seed = _strict_int(seed, "seed")
    document = {
        "schema": SEPARATION_REQUEST_SCHEMA,
        "source": source_document,
        "scope": scope_document,
        "backend_id": backend,
        "checkpoint": {
            "checkpoint_id": checkpoint,
            "sha256": checkpoint_hash,
        },
        "requested_roles": roles,
        "settings": _thaw_json(settings_document),
        "seed": seed,
        "offline_required": True,
    }
    return hashlib.sha256(_canonical_json_bytes(document)).hexdigest()


def validate_separation_run_receipt(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a strict canonical copy of one valid shareable receipt."""

    value = _mapping(document, "separation receipt")
    if "schema" not in value:
        raise ValueError("separation receipt is missing schema")
    schema = str(value["schema"])
    if schema not in SEPARATION_RUN_SCHEMAS:
        raise ValueError(
            "separation receipt schema must be one of "
            + ", ".join(sorted(SEPARATION_RUN_SCHEMAS))
        )
    _exact_fields(
        value,
        (
            _RECEIPT_FIELDS_V2
            if schema == SEPARATION_RUN_SCHEMA_V2
            else _RECEIPT_FIELDS_V1
        ),
        "separation receipt",
    )
    _sha256(value["receipt_sha256"], "receipt_sha256")
    if (
        separation_run_receipt_sha256(value)
        != value["receipt_sha256"]
    ):
        raise ValueError("separation receipt SHA-256 does not match")
    if schema == SEPARATION_RUN_SCHEMA_V2:
        run_plan = _validate_run_plan(
            value["run_plan"],
            run_plan_sha256=value["run_plan_sha256"],
            run_id=value["run_id"],
        )
        run_plan_sha256 = str(value["run_plan_sha256"])
    else:
        _run_id(value["run_id"])
        run_plan = None
        run_plan_sha256 = None
    _sha256(
        value["request_fingerprint_sha256"],
        "request_fingerprint_sha256",
    )
    status = str(value["status"])
    if status not in SEPARATION_TERMINAL_STATUSES:
        raise ValueError("separation receipt status must be terminal")
    if not isinstance(value["loadable"], bool):
        raise ValueError("separation receipt loadable must be boolean")
    expected_loadable = status == "complete"
    if value["loadable"] is not expected_loadable:
        raise ValueError(
            "separation receipt status/loadable relationship is invalid"
        )

    source = _validate_source(value["source"])
    scope = _validate_scope(value["scope"])
    backend = _validate_backend(
        value["backend"], require_commit=status == "complete"
    )
    checkpoint = _validate_checkpoint(
        value["checkpoint"], require_verified=status == "complete"
    )
    roles = _validate_roles(
        value["roles"], allow_actual_empty=status != "complete"
    )
    execution = _validate_execution(value["execution"])
    effects = _validate_effects(value["effects"])
    if effects["network_used"] is not execution["network_used"]:
        raise ValueError(
            "execution and effects network_used values must match"
        )
    outputs = _mapping(value["outputs"], "outputs")
    _exact_fields(outputs, _OUTPUT_FIELDS, "outputs")

    if status == "complete":
        targets = _validate_artifacts(
            outputs["targets"],
            label="outputs.targets",
            residual=False,
            source_geometry=source["geometry"],
        )
        residuals = _validate_artifacts(
            outputs["residuals"],
            label="outputs.residuals",
            residual=True,
            source_geometry=source["geometry"],
        )
        _validate_target_residual_pairs(
            targets,
            residuals,
            actual_roles=roles["actual"],
        )
        quality = _validate_quality(
            value["quality"],
            actual_roles=roles["actual"],
            schema=schema,
        )
        _require_quality_status_for_outputs(targets, residuals, quality)
        _require_quality_status_for_requested_roles(roles, quality)
        all_paths = [
            *(item["path"] for item in targets),
            *(item["path"] for item in residuals),
            quality["path"],
        ]
        _require_unique_artifact_paths(all_paths)
        if value["error"] is not None:
            raise ValueError(
                "complete separation receipt must not contain an error"
            )
        if execution["network_used"] is not False:
            raise ValueError(
                "complete separation receipt must record offline inference"
            )
        if any(effects.values()):
            raise ValueError(
                "complete separation receipt must record no forbidden effects"
            )
        outputs_document = {
            "targets": targets,
            "residuals": residuals,
        }
        error = None
    else:
        if outputs["targets"] != [] or outputs["residuals"] != []:
            raise ValueError(
                "non-loadable separation receipt must expose no artifacts"
            )
        if value["quality"] is not None:
            raise ValueError(
                "non-loadable separation receipt must expose no quality artifact"
            )
        error = _validate_error(value["error"])
        outputs_document = {"targets": [], "residuals": []}
        quality = None

    expected_fingerprint = separation_request_fingerprint_sha256(
        source=source,
        scope=scope,
        backend_id=backend["backend_id"],
        checkpoint_id=checkpoint["checkpoint_id"],
        checkpoint_sha256=checkpoint["sha256"],
        requested_roles=roles["requested"],
        settings=execution["settings"],
        seed=execution["seed"],
    )
    if value["request_fingerprint_sha256"] != expected_fingerprint:
        raise ValueError(
            "request_fingerprint_sha256 does not bind the separation request"
        )
    if run_plan is not None:
        _cross_bind_run_plan(
            run_plan,
            request_fingerprint_sha256=value[
                "request_fingerprint_sha256"
            ],
            backend=backend,
            checkpoint=checkpoint,
            roles=roles,
            execution=execution,
        )

    canonical = {
        "schema": schema,
        "receipt_sha256": str(value["receipt_sha256"]),
        "run_id": str(value["run_id"]),
        "request_fingerprint_sha256": str(
            value["request_fingerprint_sha256"]
        ),
        "status": status,
        "loadable": expected_loadable,
        "source": source,
        "scope": scope,
        "backend": backend,
        "checkpoint": checkpoint,
        "roles": roles,
        "execution": execution,
        "outputs": outputs_document,
        "quality": quality,
        "effects": effects,
        "error": error,
    }
    if schema == SEPARATION_RUN_SCHEMA_V2:
        canonical["run_plan_sha256"] = run_plan_sha256
        canonical["run_plan"] = run_plan
    _validate_json_value(
        canonical,
        "separation receipt",
        forbid_private_paths=True,
        allowed_artifact_paths=frozenset(all_paths)
        if status == "complete"
        else frozenset(),
    )
    # Canonical validation must not silently normalize a signed document.
    if canonical != _thaw_json(value):
        raise ValueError("separation receipt is not in canonical form")
    return canonical


def _validate_run_plan(
    value: Any,
    *,
    run_plan_sha256: Any,
    run_id: Any,
) -> dict[str, Any]:
    plan = _mapping(value, "run_plan")
    _exact_fields(plan, _RUN_PLAN_FIELDS, "run_plan")
    _validate_json_value(plan, "run_plan", forbid_private_paths=True)
    _validate_run_plan_strings(plan, "run_plan")
    claimed_hash = _sha256(run_plan_sha256, "run_plan_sha256")
    raw_hash = hashlib.sha256(
        _canonical_run_plan_json_bytes(plan)
    ).hexdigest()
    if claimed_hash != raw_hash:
        raise ValueError("run_plan_sha256 does not match run_plan")
    if _run_id(run_id) != f"separation-run:{raw_hash}":
        raise ValueError("run_id does not bind run_plan_sha256")
    if plan["schema"] != _RUN_PLAN_SCHEMA:
        raise ValueError(f"run_plan.schema must be {_RUN_PLAN_SCHEMA}")
    request_fingerprint = _sha256(
        plan["request_fingerprint_sha256"],
        "run_plan.request_fingerprint_sha256",
    )

    runner = _mapping(plan["runner"], "run_plan.runner")
    _exact_fields(runner, _RUNNER_FIELDS, "run_plan.runner")
    if runner["schema"] != "sunofriend.separation-parent.v1":
        raise ValueError("run_plan.runner.schema is unsupported")
    runner_version = _plan_text(
        runner["version"], "run_plan.runner.version"
    )
    runner_module = _qualified_identifier(
        runner["module"], "run_plan.runner.module"
    )
    module_sha256 = _sha256(
        runner["module_sha256"], "run_plan.runner.module_sha256"
    )
    runner_document = {
        "schema": "sunofriend.separation-parent.v1",
        "version": runner_version,
        "module": runner_module,
        "module_sha256": module_sha256,
        "package": _safe_identifier(
            runner["package"], "run_plan.runner.package"
        ),
        "package_version": _plan_text(
            runner["package_version"],
            "run_plan.runner.package_version",
        ),
        "backend_policy": _plan_text(
            runner["backend_policy"],
            "run_plan.runner.backend_policy",
        ),
        "cache_replay": _plan_text(
            runner["cache_replay"],
            "run_plan.runner.cache_replay",
        ),
    }
    backend = _mapping(plan["backend"], "run_plan.backend")
    _exact_fields(backend, _PLAN_BACKEND_FIELDS, "run_plan.backend")
    backend_module_sha256 = _sha256(
        backend["module_sha256"], "run_plan.backend.module_sha256"
    )
    backend_class = _qualified_identifier(
        backend["class"], "run_plan.backend.class"
    )
    commit = str(backend["commit"])
    if not _COMMIT_RE.fullmatch(commit):
        raise ValueError(
            "run_plan.backend.commit must be lowercase hexadecimal"
        )
    backend_document = {
        "backend_id": _safe_identifier(
            backend["backend_id"], "run_plan.backend.backend_id"
        ),
        "class": backend_class,
        "module_sha256": backend_module_sha256,
        "package": _safe_identifier(
            backend["package"], "run_plan.backend.package"
        ),
        "version": _plan_text(
            backend["version"], "run_plan.backend.version"
        ),
        "commit": commit,
        "code_license": _plan_text(
            backend["code_license"], "run_plan.backend.code_license"
        ),
        "training_data_note": _plan_text(
            backend["training_data_note"],
            "run_plan.backend.training_data_note",
        ),
    }
    checkpoint = _mapping(
        plan["checkpoint"], "run_plan.checkpoint"
    )
    _exact_fields(
        checkpoint, _PLAN_CHECKPOINT_FIELDS, "run_plan.checkpoint"
    )
    checkpoint_document = {
        "checkpoint_id": _safe_identifier(
            checkpoint["checkpoint_id"],
            "run_plan.checkpoint.checkpoint_id",
        ),
        "sha256": _sha256(
            checkpoint["sha256"], "run_plan.checkpoint.sha256"
        ),
        "weights_license": _plan_text(
            checkpoint["weights_license"],
            "run_plan.checkpoint.weights_license",
        ),
        "distribution_policy": _plan_text(
            checkpoint["distribution_policy"],
            "run_plan.checkpoint.distribution_policy",
        ),
    }

    runtime = _mapping(plan["runtime"], "run_plan.runtime")
    if not runtime:
        raise ValueError("run_plan.runtime must not be empty")
    _validate_json_value(
        runtime, "run_plan.runtime", forbid_private_paths=True
    )
    runtime_document = _thaw_json(runtime)
    device = _safe_identifier(plan["device"], "run_plan.device")
    command_value = plan["command"]
    if (
        not isinstance(command_value, list)
        or not command_value
        or not all(isinstance(token, str) and token for token in command_value)
    ):
        raise ValueError("run_plan.command must be a non-empty string list")
    command = [
        _plan_command_token(token, f"run_plan.command[{index}]")
        for index, token in enumerate(command_value)
    ]
    roles = _canonical_roles(
        plan["requested_roles"],
        "run_plan.requested_roles",
        require_sorted=True,
        allow_empty=False,
    )
    settings = _mapping(plan["settings"], "run_plan.settings")
    _validate_json_value(
        settings, "run_plan.settings", forbid_private_paths=True
    )
    seed = plan["seed"]
    if seed is not None:
        seed = _strict_int(seed, "run_plan.seed")

    canonical = {
        "schema": _RUN_PLAN_SCHEMA,
        "request_fingerprint_sha256": request_fingerprint,
        "runner": runner_document,
        "backend": backend_document,
        "checkpoint": checkpoint_document,
        "runtime": runtime_document,
        "device": device,
        "command": command,
        "requested_roles": roles,
        "settings": _thaw_json(settings),
        "seed": seed,
    }
    _validate_json_value(
        canonical, "run_plan", forbid_private_paths=True
    )
    if canonical != _thaw_json(plan):
        raise ValueError("run_plan is not in canonical form")
    return canonical


def _cross_bind_run_plan(
    plan: Mapping[str, Any],
    *,
    request_fingerprint_sha256: Any,
    backend: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    roles: Mapping[str, Any],
    execution: Mapping[str, Any],
) -> None:
    if (
        plan["request_fingerprint_sha256"]
        != request_fingerprint_sha256
    ):
        raise ValueError("run_plan does not bind the request fingerprint")
    for field_name in (
        "backend_id",
        "package",
        "version",
        "commit",
        "code_license",
        "training_data_note",
    ):
        if plan["backend"][field_name] != backend[field_name]:
            raise ValueError(
                f"run_plan does not bind backend.{field_name}"
            )
    for field_name in (
        "checkpoint_id",
        "sha256",
        "weights_license",
        "distribution_policy",
    ):
        if plan["checkpoint"][field_name] != checkpoint[field_name]:
            raise ValueError(
                f"run_plan does not bind checkpoint.{field_name}"
            )
    if plan["requested_roles"] != roles["requested"]:
        raise ValueError("run_plan does not bind roles.requested")
    for field_name in (
        "runtime",
        "device",
        "command",
        "settings",
        "seed",
    ):
        if plan[field_name] != execution[field_name]:
            raise ValueError(
                f"run_plan does not bind execution.{field_name}"
            )


def _validate_source(value: Any) -> dict[str, Any]:
    source = _mapping(value, "source")
    _exact_fields(source, _SOURCE_FIELDS, "source")
    source_sha256 = _sha256(source["source_sha256"], "source.source_sha256")
    _source_identity(
        source["source_id"], source_sha256, label="source"
    )
    canonical_sha256 = _sha256(
        source["canonical_sha256"], "source.canonical_sha256"
    )
    geometry = SeparationAudioGeometry.from_dict(
        _mapping(source["geometry"], "source.geometry")
    ).to_dict()
    return {
        "source_id": str(source["source_id"]),
        "source_sha256": source_sha256,
        "canonical_sha256": canonical_sha256,
        "geometry": geometry,
    }


def _validate_scope(value: Any) -> dict[str, Any]:
    scope = _mapping(value, "scope")
    _exact_fields(scope, _SCOPE_FIELDS, "scope")
    mode = str(scope["mode"])
    if mode not in {"broad", "refinement"}:
        raise ValueError("scope.mode must be broad or refinement")
    parent = scope["parent_node_id"]
    if parent is not None and not _NODE_ID_RE.fullmatch(str(parent)):
        raise ValueError(
            "scope.parent_node_id must be a canonical node identity"
        )
    if mode == "refinement" and parent is None:
        raise ValueError(
            "refinement scope requires a parent_node_id"
        )
    return {"mode": mode, "parent_node_id": parent}


def _validate_backend(
    value: Any, *, require_commit: bool
) -> dict[str, Any]:
    backend = _mapping(value, "backend")
    _exact_fields(backend, _BACKEND_FIELDS, "backend")
    backend_id = _safe_identifier(
        backend["backend_id"], "backend.backend_id"
    )
    package = _safe_identifier(backend["package"], "backend.package")
    version = _nonempty_text(backend["version"], "backend.version")
    commit_value = backend["commit"]
    if require_commit and commit_value is None:
        raise ValueError("complete separation backend requires a commit")
    if commit_value is not None and not _COMMIT_RE.fullmatch(
        str(commit_value)
    ):
        raise ValueError(
            "backend.commit must be a lowercase hexadecimal commit"
        )
    code_license = _nonempty_text(
        backend["code_license"], "backend.code_license"
    )
    training_note = _nonempty_text(
        backend["training_data_note"],
        "backend.training_data_note",
    )
    _reject_private_path_string(version, "backend.version")
    _reject_private_path_string(code_license, "backend.code_license")
    _reject_private_path_string(
        training_note, "backend.training_data_note"
    )
    return {
        "backend_id": backend_id,
        "package": package,
        "version": version,
        "commit": (
            None if commit_value is None else str(commit_value)
        ),
        "code_license": code_license,
        "training_data_note": training_note,
    }


def _validate_checkpoint(
    value: Any, *, require_verified: bool
) -> dict[str, Any]:
    checkpoint = _mapping(value, "checkpoint")
    _exact_fields(checkpoint, _CHECKPOINT_FIELDS, "checkpoint")
    checkpoint_id = _safe_identifier(
        checkpoint["checkpoint_id"], "checkpoint.checkpoint_id"
    )
    sha256 = _sha256(checkpoint["sha256"], "checkpoint.sha256")
    weights_license = _nonempty_text(
        checkpoint["weights_license"], "checkpoint.weights_license"
    )
    distribution = _nonempty_text(
        checkpoint["distribution_policy"],
        "checkpoint.distribution_policy",
    )
    if not isinstance(checkpoint["hash_verified_before_load"], bool):
        raise ValueError(
            "checkpoint.hash_verified_before_load must be boolean"
        )
    if require_verified and checkpoint["hash_verified_before_load"] is not True:
        raise ValueError(
            "checkpoint hash must be verified before model loading"
        )
    _reject_private_path_string(
        weights_license, "checkpoint.weights_license"
    )
    _reject_private_path_string(
        distribution, "checkpoint.distribution_policy"
    )
    return {
        "checkpoint_id": checkpoint_id,
        "sha256": sha256,
        "weights_license": weights_license,
        "hash_verified_before_load": checkpoint[
            "hash_verified_before_load"
        ],
        "distribution_policy": distribution,
    }


def _validate_roles(
    value: Any, *, allow_actual_empty: bool
) -> dict[str, list[str]]:
    roles = _mapping(value, "roles")
    _exact_fields(roles, _ROLES_FIELDS, "roles")
    requested = _canonical_roles(
        roles["requested"],
        "roles.requested",
        require_sorted=True,
        allow_empty=False,
    )
    actual = _canonical_roles(
        roles["actual"],
        "roles.actual",
        require_sorted=True,
        allow_empty=allow_actual_empty,
    )
    if not set(actual) <= set(requested):
        raise ValueError(
            "roles.actual must be a subset of roles.requested"
        )
    return {"requested": requested, "actual": actual}


def _validate_execution(value: Any) -> dict[str, Any]:
    execution = _mapping(value, "execution")
    _exact_fields(execution, _EXECUTION_FIELDS, "execution")
    runtime = _mapping(execution["runtime"], "execution.runtime")
    if not runtime:
        raise ValueError("execution.runtime must not be empty")
    _validate_json_value(
        runtime, "execution.runtime", forbid_private_paths=True
    )
    device = _safe_identifier(execution["device"], "execution.device")
    settings = _mapping(execution["settings"], "execution.settings")
    _validate_json_value(
        settings, "execution.settings", forbid_private_paths=True
    )
    seed = execution["seed"]
    if seed is not None:
        seed = _strict_int(seed, "execution.seed")
    wall_time = _finite_float(
        execution["wall_time_seconds"],
        "execution.wall_time_seconds",
    )
    if wall_time < 0:
        raise ValueError(
            "execution.wall_time_seconds must not be negative"
        )
    command_value = execution["command"]
    if (
        not isinstance(command_value, list)
        or not command_value
        or not all(isinstance(token, str) and token for token in command_value)
    ):
        raise ValueError(
            "execution.command must be a non-empty list of strings"
        )
    command = [
        _safe_command_token(token, f"execution.command[{index}]")
        for index, token in enumerate(command_value)
    ]
    if not isinstance(execution["network_used"], bool):
        raise ValueError("execution.network_used must be boolean")
    return {
        "runtime": _thaw_json(runtime),
        "device": device,
        "settings": _thaw_json(settings),
        "seed": seed,
        "wall_time_seconds": wall_time,
        "command": command,
        "network_used": execution["network_used"],
    }


def _validate_artifacts(
    value: Any,
    *,
    label: str,
    residual: bool,
    source_geometry: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list")
    expected_fields = _RESIDUAL_FIELDS if residual else _ARTIFACT_FIELDS
    output: list[dict[str, Any]] = []
    for index, item_value in enumerate(value):
        item_label = f"{label}[{index}]"
        item = _mapping(item_value, item_label)
        _exact_fields(item, expected_fields, item_label)
        role = _canonical_role(item["role"], f"{item_label}.role")
        path = str(
            _safe_relative_path(item["path"], f"{item_label}.path")
        )
        if not path.casefold().endswith(".wav"):
            raise ValueError(f"{item_label}.path must name a WAV artifact")
        sha256 = _sha256(item["sha256"], f"{item_label}.sha256")
        geometry = SeparationAudioGeometry.from_dict(
            _mapping(item["geometry"], f"{item_label}.geometry")
        ).to_dict()
        _require_same_geometry(
            source_geometry, geometry, f"{item_label}.geometry"
        )
        peak = _bounded_float(
            item["peak"], f"{item_label}.peak", minimum=0.0, maximum=1.0
        )
        rms = _bounded_float(
            item["rms"], f"{item_label}.rms", minimum=0.0, maximum=1.0
        )
        if rms > peak + 1e-12:
            raise ValueError(f"{item_label}.rms must not exceed peak")
        silence_fraction = _bounded_float(
            item["silence_fraction"],
            f"{item_label}.silence_fraction",
            minimum=0.0,
            maximum=1.0,
        )
        clipped_samples = _strict_int(
            item["clipped_samples"], f"{item_label}.clipped_samples"
        )
        if clipped_samples < 0 or clipped_samples > (
            geometry["frames"] * geometry["channels"]
        ):
            raise ValueError(
                f"{item_label}.clipped_samples is outside its geometry"
            )
        artifact = {
            "role": role,
            "path": path,
            "sha256": sha256,
            "geometry": geometry,
            "peak": peak,
            "rms": rms,
            "silence_fraction": silence_fraction,
            "clipped_samples": clipped_samples,
        }
        if residual:
            artifact["target_sha256"] = _sha256(
                item["target_sha256"],
                f"{item_label}.target_sha256",
            )
            if item["definition"] != SEPARATION_RESIDUAL_DEFINITION:
                raise ValueError(
                    f"{item_label}.definition is unsupported"
                )
            artifact["definition"] = SEPARATION_RESIDUAL_DEFINITION
        output.append(artifact)
    roles = [item["role"] for item in output]
    if len(set(roles)) != len(roles):
        raise ValueError(f"{label} roles must be unique")
    if roles != sorted(roles):
        raise ValueError(f"{label} must use canonical role order")
    return output


def _validate_target_residual_pairs(
    targets: Sequence[Mapping[str, Any]],
    residuals: Sequence[Mapping[str, Any]],
    *,
    actual_roles: Sequence[str],
) -> None:
    target_by_role = {item["role"]: item for item in targets}
    residual_by_role = {item["role"]: item for item in residuals}
    expected = set(actual_roles)
    if set(target_by_role) != expected:
        raise ValueError(
            "target roles must exactly match roles.actual"
        )
    if set(residual_by_role) != expected:
        raise ValueError(
            "residual roles must exactly match roles.actual"
        )
    for role in sorted(expected):
        if (
            residual_by_role[role]["target_sha256"]
            != target_by_role[role]["sha256"]
        ):
            raise ValueError(
                f"residual for {role} is not bound to its target hash"
            )


def _validate_quality(
    value: Any,
    *,
    actual_roles: Sequence[str],
    schema: str,
) -> dict[str, Any]:
    quality = _mapping(value, "quality")
    _exact_fields(quality, _QUALITY_FIELDS, "quality")
    path = str(_safe_relative_path(quality["path"], "quality.path"))
    if not path.casefold().endswith(".json"):
        raise ValueError("quality.path must name a JSON artifact")
    sha256 = _sha256(quality["sha256"], "quality.sha256")
    status = str(quality["status"])
    if status not in SEPARATION_QUALITY_STATUSES:
        raise ValueError("quality.status is unsupported")
    if quality["reconstruction_is_accuracy_evidence"] is not False:
        raise ValueError(
            "reconstruction_is_accuracy_evidence must be false"
        )
    reconstruction = _mapping(
        quality["reconstruction"], "quality.reconstruction"
    )
    _exact_fields(
        reconstruction,
        _RECONSTRUCTION_FIELDS,
        "quality.reconstruction",
    )
    maximum_error = _finite_float(
        reconstruction["maximum_absolute_error"],
        "quality.reconstruction.maximum_absolute_error",
    )
    rms_error = _finite_float(
        reconstruction["rms_error"],
        "quality.reconstruction.rms_error",
    )
    threshold = _finite_float(
        reconstruction["threshold"],
        "quality.reconstruction.threshold",
    )
    if min(maximum_error, rms_error, threshold) < 0:
        raise ValueError(
            "quality reconstruction values must not be negative"
        )
    if threshold <= 0:
        raise ValueError(
            "quality.reconstruction.threshold must be positive"
        )
    if rms_error > maximum_error + 1e-15:
        raise ValueError(
            "quality reconstruction rms_error must not exceed "
            "maximum_absolute_error"
        )
    if not isinstance(reconstruction["passed"], bool):
        raise ValueError(
            "quality.reconstruction.passed must be boolean"
        )
    if reconstruction["passed"] != (maximum_error <= threshold):
        raise ValueError(
            "quality reconstruction pass flag does not match its threshold"
        )
    if not reconstruction["passed"] and status != "review_required":
        raise ValueError(
            "failed reconstruction requires review_required quality status"
        )
    leakage = _mapping(quality["leakage"], "quality.leakage")
    leakage_document: dict[str, Any] = {}
    for role, evidence_value in leakage.items():
        canonical = _canonical_role(role, "quality.leakage role")
        if canonical != role:
            raise ValueError(
                "quality.leakage keys must be canonical roles"
            )
        if schema == SEPARATION_RUN_SCHEMA_V1:
            leakage_document[canonical] = _bounded_float(
                evidence_value,
                f"quality.leakage.{canonical}",
                minimum=0.0,
                maximum=1.0,
            )
            continue
        evidence = _mapping(
            evidence_value,
            f"quality.leakage.{canonical}",
        )
        _exact_fields(
            evidence,
            _LEAKAGE_FIELDS,
            f"quality.leakage.{canonical}",
        )
        evidence_status = str(evidence["status"])
        if evidence_status not in _LEAKAGE_STATUSES:
            raise ValueError(
                f"quality.leakage.{canonical}.status is unsupported"
            )
        if evidence_status == "not_measured":
            if any(
                evidence[field] is not None
                for field in ("metric", "score", "reference_id")
            ):
                raise ValueError(
                    f"quality.leakage.{canonical} not_measured evidence "
                    "must not claim a metric, score or reference"
                )
            leakage_document[canonical] = {
                "status": "not_measured",
                "metric": None,
                "score": None,
                "reference_id": None,
            }
            continue
        metric = _safe_identifier(
            evidence["metric"],
            f"quality.leakage.{canonical}.metric",
        )
        score = _bounded_float(
            evidence["score"],
            f"quality.leakage.{canonical}.score",
            minimum=0.0,
            maximum=1.0,
        )
        reference_id = str(evidence["reference_id"])
        if not _SHA256_ID_RE.fullmatch(reference_id):
            raise ValueError(
                f"quality.leakage.{canonical}.reference_id must be a "
                "SHA-256 identity"
            )
        leakage_document[canonical] = {
            "status": "measured",
            "metric": metric,
            "score": score,
            "reference_id": reference_id,
        }
    if list(leakage_document) != sorted(leakage_document):
        raise ValueError(
            "quality.leakage must use canonical role order"
        )
    if set(leakage_document) != set(actual_roles):
        raise ValueError(
            "quality.leakage roles must exactly match roles.actual"
        )
    if (
        schema == SEPARATION_RUN_SCHEMA_V2
        and any(
            evidence["status"] == "not_measured"
            for evidence in leakage_document.values()
        )
        and status != "review_required"
    ):
        raise ValueError(
            "unmeasured leakage requires review_required quality status"
        )
    if schema == SEPARATION_RUN_SCHEMA_V2 and status == "passed":
        raise ValueError(
            "v2 quality cannot be passed without a hashed acceptance "
            "profile binding; use review_required"
        )
    return {
        "path": path,
        "sha256": sha256,
        "status": status,
        "reconstruction": {
            "maximum_absolute_error": maximum_error,
            "rms_error": rms_error,
            "threshold": threshold,
            "passed": reconstruction["passed"],
        },
        "leakage": leakage_document,
        "reconstruction_is_accuracy_evidence": False,
    }


def _require_quality_status_for_outputs(
    targets: Sequence[Mapping[str, Any]],
    residuals: Sequence[Mapping[str, Any]],
    quality: Mapping[str, Any],
) -> None:
    if quality["status"] != "passed":
        return
    for artifact in (*targets, *residuals):
        if (
            artifact["rms"] == 0.0
            or artifact["silence_fraction"] == 1.0
            or artifact["clipped_samples"] > 0
        ):
            raise ValueError(
                "silent or clipped output requires review_required "
                "quality status"
            )


def _require_quality_status_for_requested_roles(
    roles: Mapping[str, Sequence[str]],
    quality: Mapping[str, Any],
) -> None:
    if (
        set(roles["actual"]) != set(roles["requested"])
        and quality["status"] != "review_required"
    ):
        raise ValueError(
            "missing requested roles require review_required quality status"
        )


def _validate_effects(value: Any) -> dict[str, bool]:
    effects = _mapping(value, "effects")
    _exact_fields(effects, _EFFECT_FIELDS, "effects")
    output: dict[str, bool] = {}
    for field_name in sorted(_EFFECT_FIELDS):
        if not isinstance(effects[field_name], bool):
            raise ValueError(f"effects.{field_name} must be boolean")
        output[field_name] = effects[field_name]
    return output


def _validate_error(value: Any) -> dict[str, Any]:
    error = _mapping(value, "error")
    _exact_fields(error, _ERROR_FIELDS, "error")
    code = str(error["code"])
    if not _ERROR_CODE_RE.fullmatch(code):
        raise ValueError("error.code is invalid")
    message = _nonempty_text(error["message"], "error.message")
    _reject_private_path_string(message, "error.message")
    if not isinstance(error["retryable"], bool):
        raise ValueError("error.retryable must be boolean")
    return {
        "code": code,
        "message": message,
        "retryable": error["retryable"],
    }


def _validate_geometry(
    value: Mapping[str, Any], label: str
) -> None:
    geometry = _mapping(value, label)
    _exact_fields(geometry, _GEOMETRY_FIELDS, label)
    sample_rate = _strict_int(
        geometry["sample_rate"], f"{label}.sample_rate"
    )
    channels = _strict_int(geometry["channels"], f"{label}.channels")
    frames = _strict_int(geometry["frames"], f"{label}.frames")
    duration = _finite_float(
        geometry["duration_seconds"], f"{label}.duration_seconds"
    )
    if not 1 <= sample_rate <= 768_000:
        raise ValueError(f"{label}.sample_rate is outside bounds")
    if not 1 <= channels <= 64:
        raise ValueError(f"{label}.channels is outside bounds")
    if frames <= 0:
        raise ValueError(f"{label}.frames must be positive")
    if duration <= 0:
        raise ValueError(f"{label}.duration_seconds must be positive")
    expected = frames / sample_rate
    if abs(duration - expected) > max(1.0 / sample_rate, 1e-9):
        raise ValueError(
            f"{label}.duration_seconds does not match frames/sample_rate"
        )


def _require_same_geometry(
    source: Mapping[str, Any],
    artifact: Mapping[str, Any],
    label: str,
) -> None:
    for field_name in ("sample_rate", "channels", "frames"):
        if artifact[field_name] != source[field_name]:
            raise ValueError(f"{label} does not match source geometry")
    tolerance = max(1.0 / int(source["sample_rate"]), 1e-9)
    if (
        abs(
            float(artifact["duration_seconds"])
            - float(source["duration_seconds"])
        )
        > tolerance
    ):
        raise ValueError(f"{label} does not match source duration")


def _canonical_roles(
    value: Any,
    label: str,
    *,
    require_sorted: bool,
    allow_empty: bool,
) -> list[str]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{label} must be a list of canonical roles")
    roles = [_canonical_role(role, f"{label} item") for role in value]
    if not allow_empty and not roles:
        raise ValueError(f"{label} must not be empty")
    if len(set(roles)) != len(roles):
        raise ValueError(f"{label} roles must be unique")
    if require_sorted and roles != sorted(roles):
        raise ValueError(f"{label} must use canonical role order")
    return roles


def _canonical_role(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a canonical role")
    try:
        canonical = canonical_source_role(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be a canonical role") from exc
    if canonical != value or canonical not in prepared_source_role_ids():
        raise ValueError(f"{label} must be a prepared canonical role")
    return canonical


def _source_identity(
    source_id: Any, source_sha256: Any, *, label: str
) -> None:
    identity = str(source_id)
    sha256 = _sha256(source_sha256, f"{label}.source_sha256")
    if not _SHA256_ID_RE.fullmatch(identity):
        raise ValueError(
            f"{label}.source_id must be a SHA-256 identity"
        )
    if identity != f"sha256:{sha256}":
        raise ValueError(
            f"{label}.source_id must bind source_sha256"
        )


def _run_id(value: Any) -> str:
    text = str(value)
    if not _RUN_ID_RE.fullmatch(text):
        raise ValueError(
            "run_id must be a separation-run SHA-256 identity"
        )
    return text


def _sha256(value: Any, label: str) -> str:
    text = str(value)
    if not _SHA256_RE.fullmatch(text):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return text


def _safe_identifier(value: Any, label: str) -> str:
    text = str(value)
    if not _SAFE_ID_RE.fullmatch(text):
        raise ValueError(f"{label} must be a safe identifier")
    return text


def _qualified_identifier(value: Any, label: str) -> str:
    text = str(value)
    if not _QUALIFIED_ID_RE.fullmatch(text):
        raise ValueError(f"{label} must be a safe qualified identifier")
    _reject_private_path_string(text, label)
    return text


def _safe_relative_path(value: Any, label: str) -> PurePosixPath:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a safe relative POSIX path")
    text = value
    path = PurePosixPath(text)
    if (
        not text
        or text != text.strip()
        or unicodedata.normalize("NFC", text) != text
        or "\\" in text
        or "\x00" in text
        or path.is_absolute()
        or str(path) != text
        or path == PurePosixPath(".")
        or ".." in path.parts
        or "~" in path.parts
        or "://" in text
    ):
        raise ValueError(f"{label} must be a safe relative POSIX path")
    return path


def _require_unique_artifact_paths(paths: Sequence[str]) -> None:
    """Reject exact, case-insensitive and Unicode-equivalent path aliases."""

    collision_keys = [
        unicodedata.normalize("NFC", path).casefold()
        for path in paths
    ]
    if len(set(collision_keys)) != len(collision_keys):
        raise ValueError(
            "separation receipt artifact paths must be unique after "
            "Unicode NFC normalization and casefolding"
        )


def _safe_command_token(value: str, label: str) -> str:
    if (
        "/" in value
        or "\\" in value
        or value.startswith("~")
        or "://" in value
        or "\x00" in value
        or _WINDOWS_ABSOLUTE_RE.match(value)
    ):
        raise ValueError(f"{label} must not contain a path or URL")
    _reject_private_path_string(value, label)
    return value


def _plan_command_token(value: str, label: str) -> str:
    token = _safe_command_token(value, label)
    if "<" in token or ">" in token:
        raise ValueError(f"{label} must not contain a placeholder")
    return token


def _plan_text(value: Any, label: str) -> str:
    text = _nonempty_text(value, label)
    _reject_private_path_string(text, label)
    if "<" in text or ">" in text:
        raise ValueError(f"{label} must not contain a placeholder")
    return text


def _validate_run_plan_strings(value: Any, label: str) -> None:
    if isinstance(value, str):
        if (
            "/" in value
            or "\\" in value
            or "://" in value
            or "<" in value
            or ">" in value
        ):
            raise ValueError(
                f"{label} must not contain a path, URL or placeholder"
            )
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _validate_run_plan_strings(item, f"{label}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_run_plan_strings(item, f"{label}[{index}]")


def _validate_json_value(
    value: Any,
    label: str,
    *,
    forbid_private_paths: bool,
    allowed_artifact_paths: frozenset[str] = frozenset(),
) -> None:
    if value is None or isinstance(value, (bool, str, int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"{label} contains a non-finite number")
        if isinstance(value, str) and forbid_private_paths:
            if value not in allowed_artifact_paths:
                _reject_private_path_string(value, label)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError(f"{label} contains an invalid object key")
            if (
                forbid_private_paths
                and (
                    key in _FORBIDDEN_PATH_KEYS
                    or key.endswith("_path")
                )
                and not (
                    key == "path"
                    and isinstance(item, str)
                    and item in allowed_artifact_paths
                )
            ):
                raise ValueError(
                    f"{label} must not contain private path field {key}"
                )
            _validate_json_value(
                item,
                f"{label}.{key}",
                forbid_private_paths=forbid_private_paths,
                allowed_artifact_paths=allowed_artifact_paths,
            )
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_json_value(
                item,
                f"{label}[{index}]",
                forbid_private_paths=forbid_private_paths,
                allowed_artifact_paths=allowed_artifact_paths,
            )
        return
    raise ValueError(f"{label} must contain only finite JSON values")


def _reject_private_path_string(value: str, label: str) -> None:
    if (
        value.startswith(("/", "~"))
        or _WINDOWS_ABSOLUTE_RE.match(value)
        or _PRIVATE_PATH_FRAGMENT_RE.search(value)
        or value.startswith("file://")
    ):
        raise ValueError(f"{label} must not expose a private path")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _exact_fields(
    value: Mapping[str, Any],
    expected: frozenset[str],
    label: str,
) -> None:
    actual = set(value)
    if actual != set(expected):
        missing = sorted(set(expected) - actual)
        extra = sorted(actual - set(expected))
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if extra:
            detail.append("unexpected " + ", ".join(extra))
        raise ValueError(f"{label} fields are invalid: {'; '.join(detail)}")


def _strict_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _finite_float(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def _bounded_float(
    value: Any,
    label: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    number = _finite_float(value, label)
    if not minimum <= number <= maximum:
        raise ValueError(f"{label} is outside bounds")
    return number


def _nonempty_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _freeze_json(value: Any) -> Any:
    _validate_json_value(
        value, "immutable value", forbid_private_paths=False
    )
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(item) for item in value]
    return value


def _canonical_json_bytes(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            _thaw_json(document),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _canonical_run_plan_json_bytes(
    document: Mapping[str, Any],
) -> bytes:
    """Match the repository canonical form used by SeparationRunPlan."""

    return (
        json.dumps(
            _thaw_json(document),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


__all__ = [
    "SEPARATION_FAILURE_STATUSES",
    "SEPARATION_QUALITY_STATUSES",
    "SEPARATION_REQUEST_SCHEMA",
    "SEPARATION_RESIDUAL_DEFINITION",
    "SEPARATION_RUN_SCHEMA",
    "SEPARATION_RUN_SCHEMAS",
    "SEPARATION_RUN_SCHEMA_V1",
    "SEPARATION_RUN_SCHEMA_V2",
    "SEPARATION_TERMINAL_STATUSES",
    "SeparationAudioGeometry",
    "SeparationBackend",
    "SeparationBackendOutput",
    "SeparationCancellationPredicate",
    "SeparationError",
    "SeparationRequest",
    "SeparationResult",
    "SeparationRunReceipt",
    "build_separation_run_receipt",
    "separation_run_receipt_sha256",
    "separation_request_fingerprint_sha256",
    "validate_separation_run_receipt",
]
