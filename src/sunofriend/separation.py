"""Controlled, dependency-free parent runner for separation experiments.

This is deliberately *not* a general model runner.  The only backend accepted
by :func:`run_separation` is the exact deterministic
:class:`FakeSeparationBackend` defined here.  It exists for tests, demos and
receipt integration only, and its output is always marked for human review.

An in-process Python protocol cannot prove that an arbitrary real model made
no network calls or writes outside its output directory.  Real separation
backends therefore remain unsupported until a future isolated worker can
provide independently verified network and filesystem-effect evidence.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import platform
import re
import shutil
import stat
import tempfile
import threading
import time
import wave
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

from .separation_contract import (
    SeparationBackend,
    SeparationBackendOutput,
    SeparationError,
    SeparationRequest,
    SeparationResult,
    SeparationRunReceipt,
    build_separation_run_receipt,
)
from .source_receipt import canonical_json_bytes


FAKE_SEPARATION_BACKEND_ID = "sunofriend-fake"
SEPARATION_QUALITY_SCHEMA = "sunofriend.separation-quality.v1"
SEPARATION_RECEIPT_FILENAME = "separation-run.json"
SEPARATION_QUALITY_RELATIVE_PATH = "QUALITY/separation-quality.json"
SEPARATION_RUN_PLAN_SCHEMA = "sunofriend.separation-run-plan.v1"
SEPARATION_RUNNER_SCHEMA = "sunofriend.separation-parent.v1"
SEPARATION_RUNNER_VERSION = "1"
REAL_SEPARATION_BACKENDS_SUPPORTED = False
SEPARATION_CACHE_REPLAY_SUPPORTED = False

_COMMIT_RE = re.compile(r"^[0-9a-f]{7,64}$")
_SAFE_IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,127}$")
_FAKE_OUTCOMES = frozenset({"complete", "failed", "cancelled"})
_PRIVATE_DIRECTORY_MODE = 0o700
_PRIVATE_FILE_MODE = 0o600
_ZERO_WRITE_FRAMES = 65_536
_COPY_BYTES = 1024 * 1024
_MAX_RUNNER_MODULE_BYTES = 16 * 1024 * 1024
_MAX_CHECKPOINT_BYTES = 16 * 1024**3
_MAX_AGGREGATE_OUTPUT_BYTES = 32 * 1024**3
_MAX_TERMINAL_FILE_COUNT = 130
_FREE_SPACE_RESERVE_BYTES = 256 * 1024**2
_QUALITY_AND_RECEIPT_RESERVE_BYTES = 16 * 1024**2

_FAKE_PACKAGE = "sunofriend"
_FAKE_CODE_LICENSE = "Apache-2.0"
_FAKE_TRAINING_NOTE = (
    "Deterministic test and demo fake; no model and no training data"
)
_CHECKPOINT_WEIGHTS_LICENSE = "Test fixture only"
_CHECKPOINT_DISTRIBUTION = (
    "Local test and demo fixture; never bundled or downloaded"
)


class _CancellationRequested(Exception):
    pass


@dataclass(frozen=True)
class SeparationCancellationToken:
    """Exact parent-owned cancellation state; it executes no caller code."""

    _event: threading.Event = field(
        default_factory=threading.Event,
        repr=False,
        compare=False,
    )

    def request_cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()


@dataclass(frozen=True)
class _ParentCancellationProbe:
    token: SeparationCancellationToken

    def __post_init__(self) -> None:
        if type(self.token) is not SeparationCancellationToken:
            raise ValueError("cancellation token must be parent-owned")

    def __call__(self) -> bool:
        return self.token.is_cancelled


@dataclass(frozen=True)
class _OwnedDirectory:
    path: Path
    device: int
    inode: int


@dataclass(frozen=True)
class SeparationRunMetadata:
    """Non-executable context; all attested identity is derived internally."""

    cancellation_token: SeparationCancellationToken | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if (
            self.cancellation_token is not None
            and type(self.cancellation_token)
            is not SeparationCancellationToken
        ):
            raise ValueError("cancellation_token must be parent-owned")


@dataclass(frozen=True)
class SeparationRunPlan:
    """Canonical path-free identity of one parent-runner invocation."""

    request_fingerprint_sha256: str
    runner: Mapping[str, Any]
    backend: Mapping[str, Any]
    checkpoint: Mapping[str, Any]
    runtime: Mapping[str, Any]
    device: str
    command: tuple[str, ...]
    requested_roles: tuple[str, ...]
    settings: Mapping[str, Any]
    seed: int | None
    schema: str = SEPARATION_RUN_PLAN_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SEPARATION_RUN_PLAN_SCHEMA:
            raise ValueError("unsupported separation run-plan schema")
        if not re.fullmatch(
            r"[0-9a-f]{64}",
            self.request_fingerprint_sha256,
        ):
            raise ValueError(
                "request_fingerprint_sha256 must be a lowercase SHA-256"
            )
        for field_name in (
            "runner",
            "backend",
            "checkpoint",
            "runtime",
            "settings",
        ):
            value = _freeze_json(getattr(self, field_name), field_name)
            if not isinstance(value, Mapping):
                raise ValueError(f"{field_name} must be a JSON object")
            object.__setattr__(self, field_name, value)
        if not _SAFE_IDENTIFIER_RE.fullmatch(self.device):
            raise ValueError("device must be a safe identifier")
        command = tuple(self.command)
        if not command:
            raise ValueError("command must not be empty")
        for index, token in enumerate(command):
            if not isinstance(token, str) or not token:
                raise ValueError(f"command[{index}] must be non-empty text")
            _reject_path_or_url(token, f"command[{index}]")
        object.__setattr__(self, "command", command)
        roles = tuple(self.requested_roles)
        if not roles or roles != tuple(sorted(roles)):
            raise ValueError(
                "requested_roles must use non-empty canonical order"
            )
        object.__setattr__(self, "requested_roles", roles)
        if self.seed is not None and (
            isinstance(self.seed, bool) or not isinstance(self.seed, int)
        ):
            raise ValueError("seed must be an integer or null")

    @classmethod
    def create(
        cls,
        request: SeparationRequest,
        metadata: SeparationRunMetadata,
    ) -> "SeparationRunPlan":
        """Bind all path-free parent-runner inputs before filesystem work."""

        del metadata
        module_path = Path(__file__).resolve()
        module_sha256, _ = _hash_bounded_regular_file(
            module_path,
            maximum_bytes=_MAX_RUNNER_MODULE_BYTES,
            cancellation_probe=None,
            label="separation runner module",
        )
        package_version = _installed_package_version()
        runtime = _actual_runtime_identity()
        return cls(
            request_fingerprint_sha256=request.fingerprint_sha256,
            runner={
                "schema": SEPARATION_RUNNER_SCHEMA,
                "version": SEPARATION_RUNNER_VERSION,
                "module": "sunofriend.separation",
                "module_sha256": module_sha256,
                "package": _FAKE_PACKAGE,
                "package_version": package_version,
                "backend_policy": "controlled-fake-only",
                "cache_replay": "unsupported",
            },
            backend={
                "backend_id": request.backend_id,
                "class": (
                    "sunofriend.separation.FakeSeparationBackend"
                ),
                "module_sha256": module_sha256,
                "package": _FAKE_PACKAGE,
                "version": package_version,
                # The receipt schema names this field commit. The controlled
                # fake has no model repository, so the actual executing module
                # hash prefix is used and the full hash remains in this plan.
                "commit": module_sha256[:40],
                "code_license": _FAKE_CODE_LICENSE,
                "training_data_note": _FAKE_TRAINING_NOTE,
            },
            checkpoint={
                "checkpoint_id": request.checkpoint_id,
                "sha256": request.checkpoint_sha256,
                "weights_license": _CHECKPOINT_WEIGHTS_LICENSE,
                "distribution_policy": _CHECKPOINT_DISTRIBUTION,
            },
            runtime=runtime,
            device="cpu",
            command=("sunofriend-fake-separation",),
            requested_roles=request.requested_roles,
            settings=request.settings,
            seed=request.seed,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "request_fingerprint_sha256": (
                self.request_fingerprint_sha256
            ),
            "runner": _thaw_json(self.runner),
            "backend": _thaw_json(self.backend),
            "checkpoint": _thaw_json(self.checkpoint),
            "runtime": _thaw_json(self.runtime),
            "device": self.device,
            "command": list(self.command),
            "requested_roles": list(self.requested_roles),
            "settings": _thaw_json(self.settings),
            "seed": self.seed,
        }

    @property
    def plan_sha256(self) -> str:
        return hashlib.sha256(
            canonical_json_bytes(self.to_dict())
        ).hexdigest()

    @property
    def run_id(self) -> str:
        return f"separation-run:{self.plan_sha256}"

    def validate_run_id(self, value: str) -> None:
        if value != self.run_id:
            raise ValueError("run_id is not bound to the separation run plan")


@dataclass(frozen=True)
class FakeSeparationBackend:
    """Deterministic test/demo backend that never invokes a model.

    A complete fake run copies the source into each requested target and writes
    a same-clock silent residual.  This closes the reconstruction arithmetic,
    but it is not useful separation and is never promotable as model evidence.
    """

    outcome: str = "complete"
    cancel_after_roles: int | None = None

    def __post_init__(self) -> None:
        if self.outcome not in _FAKE_OUTCOMES:
            raise ValueError(
                "fake separation outcome must be complete, failed or cancelled"
            )
        if self.cancel_after_roles is not None and (
            isinstance(self.cancel_after_roles, bool)
            or not isinstance(self.cancel_after_roles, int)
            or self.cancel_after_roles < 0
        ):
            raise ValueError("cancel_after_roles must be a non-negative integer")

    @property
    def backend_id(self) -> str:
        return FAKE_SEPARATION_BACKEND_ID

    def run(
        self,
        request: SeparationRequest,
        *,
        cancellation_requested: Callable[[], bool] | None = None,
    ) -> SeparationResult:
        if (
            cancellation_requested is not None
            and type(cancellation_requested)
            is not _ParentCancellationProbe
        ):
            raise ValueError(
                "fake backend accepts only the parent-owned cancellation probe"
            )
        probe = cancellation_requested
        if _cancelled(probe):
            return _fake_cancelled_result()
        if self.outcome == "failed":
            return SeparationResult(
                status="failed",
                error=SeparationError(
                    code="fake_backend_failed",
                    message="Controlled fake backend was asked to fail",
                    retryable=False,
                ),
            )
        if self.outcome == "cancelled":
            return _fake_cancelled_result()

        # Late import keeps the parent module independent of optional model
        # packages and avoids treating quality inspection as backend inference.
        from .separation_quality import inspect_pcm_wav

        try:
            _ensure_not_cancelled(probe)
            source_inspection = inspect_pcm_wav(request.source_path)
            _ensure_not_cancelled(probe)
            outputs: list[SeparationBackendOutput] = []
            for index, role in enumerate(request.requested_roles):
                if (
                    self.cancel_after_roles is not None
                    and index >= self.cancel_after_roles
                ):
                    return _fake_cancelled_result()
                _ensure_not_cancelled(probe)
                target = (
                    request.output_dir / "STEMS" / f"{role}-target.wav"
                )
                residual = (
                    request.output_dir
                    / "RESIDUALS"
                    / f"{role}-residual.wav"
                )
                _make_private_directory(target.parent)
                _make_private_directory(residual.parent)
                _copy_file_cancellable(
                    request.source_path,
                    target,
                    cancellation_probe=probe,
                )
                _write_silent_wave(
                    residual,
                    channels=source_inspection.geometry.channels,
                    sample_width_bytes=source_inspection.sample_width_bytes,
                    sample_rate=source_inspection.geometry.sample_rate,
                    frames=source_inspection.geometry.frames,
                    cancellation_probe=probe,
                )
                outputs.append(
                    SeparationBackendOutput(
                        role=role,
                        target_path=target,
                        residual_path=residual,
                    )
                )
        except _CancellationRequested:
            return _fake_cancelled_result()
        return SeparationResult(status="complete", outputs=tuple(outputs))


def run_separation(
    request: SeparationRequest,
    backend: SeparationBackend,
    metadata: SeparationRunMetadata,
) -> SeparationRunReceipt:
    """Run the controlled fake and atomically publish one terminal tree."""

    started = time.monotonic()
    request.validate()
    if type(backend) is not FakeSeparationBackend:
        raise RuntimeError(
            "real separation backends are unsupported; a future isolated "
            "worker must verify network and outside-output effects"
        )
    if backend.backend_id != request.backend_id:
        raise ValueError(
            "separation backend ID does not match the request"
        )
    if request.backend_id != FAKE_SEPARATION_BACKEND_ID:
        raise RuntimeError(
            "the in-process runner is restricted to the controlled fake backend"
        )

    token = metadata.cancellation_token or SeparationCancellationToken()
    probe = _ParentCancellationProbe(token)
    plan = SeparationRunPlan.create(request, metadata)
    _reject_inputs_inside_output_root(request)
    _require_fresh_output_destination(request.output_dir)
    source_before, checkpoint_before, source_bytes = (
        _verify_immutable_inputs(request, cancellation_probe=probe)
    )
    _resource_preflight(request, source_bytes=source_bytes)
    work = _create_private_sibling(request.output_dir, purpose="work")
    try:
        _ensure_not_cancelled(probe)
        result = backend.run(
            replace(request, output_dir=work.path),
            cancellation_requested=probe,
        )
        effects = _immutable_input_effects(
            request,
            source_before=source_before,
            checkpoint_before=checkpoint_before,
        )
        if effects["source_mutated"] or effects["checkpoint_mutated"]:
            return _finish_nonloadable_run(
                request,
                plan,
                work=work,
                started=started,
                status="failed",
                error=SeparationError(
                    code="immutable_input_changed",
                    message=(
                        "Source or checkpoint changed during the controlled "
                        "fake run"
                    ),
                    retryable=False,
                ),
                effects=effects,
            )
        if result.status != "complete":
            assert result.error is not None
            return _finish_nonloadable_run(
                request,
                plan,
                work=work,
                started=started,
                status=result.status,
                error=result.error,
                effects=effects,
            )
        return _finish_complete_run(
            request,
            result,
            plan,
            work=work,
            source_before=source_before,
            checkpoint_before=checkpoint_before,
            cancellation_probe=probe,
            started=started,
        )
    except _CancellationRequested:
        effects = _immutable_input_effects(
            request,
            source_before=source_before,
            checkpoint_before=checkpoint_before,
        )
        return _finish_nonloadable_run(
            request,
            plan,
            work=work,
            started=started,
            status="cancelled",
            error=SeparationError(
                code="cancelled",
                message="Controlled fake separation was cancelled",
                retryable=True,
            ),
            effects=effects,
        )
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        effects = _immutable_input_effects(
            request,
            source_before=source_before,
            checkpoint_before=checkpoint_before,
        )
        return _finish_nonloadable_run(
            request,
            plan,
            work=work,
            started=started,
            status="failed",
            error=SeparationError(
                code="invalid_backend_output",
                message="Controlled fake backend output failed validation",
                retryable=False,
            ),
            effects=effects,
        )
    finally:
        _safe_remove_owned_tree(work)


def _finish_complete_run(
    request: SeparationRequest,
    result: SeparationResult,
    plan: SeparationRunPlan,
    *,
    work: "_OwnedDirectory",
    source_before: str,
    checkpoint_before: str,
    cancellation_probe: _ParentCancellationProbe,
    started: float,
) -> SeparationRunReceipt:
    from .separation_quality import (
        evaluate_target_residual_reconstruction,
        inspect_pcm_wav,
    )

    work_root = _require_owned_directory(work)
    actual_roles = tuple(output.role for output in result.outputs)
    if not set(actual_roles) <= set(request.requested_roles):
        raise ValueError("backend returned an unrequested source role")

    target_documents: list[dict[str, Any]] = []
    residual_documents: list[dict[str, Any]] = []
    reconstruction_pairs: list[tuple[str, Path, Path]] = []
    claimed_paths: set[Path] = set()
    staged_pairs: list[tuple[str, Path, Path]] = []
    for output in result.outputs:
        target = _confined_regular_wave(
            output.target_path,
            output_root=work_root,
        )
        residual = _confined_regular_wave(
            output.residual_path,
            output_root=work_root,
        )
        if target in claimed_paths or residual in claimed_paths:
            raise ValueError("backend output paths must be unique")
        claimed_paths.update((target, residual))
        staged_pairs.append((output.role, target, residual))

    _require_exact_backend_tree(
        work_root,
        declared_paths=claimed_paths,
    )

    publish = _create_private_sibling(request.output_dir, purpose="publish")
    published = False
    published_casefold_paths: set[str] = set()
    try:
        publish_root = _require_owned_directory(publish)
        for role, staged_target, staged_residual in staged_pairs:
            _ensure_not_cancelled(cancellation_probe)
            target_relative = f"STEMS/{role}-target.wav"
            residual_relative = f"RESIDUALS/{role}-residual.wav"
            for relative in (target_relative, residual_relative):
                folded = relative.casefold()
                if folded in published_casefold_paths:
                    raise ValueError(
                        "published backend filenames collide "
                        "case-insensitively"
                    )
                published_casefold_paths.add(folded)
            target = publish_root / target_relative
            residual = publish_root / residual_relative
            _make_private_directory(target.parent)
            _make_private_directory(residual.parent)
            os.replace(staged_target, target)
            os.replace(staged_residual, residual)
            target.chmod(_PRIVATE_FILE_MODE)
            residual.chmod(_PRIVATE_FILE_MODE)
            target_inspection = inspect_pcm_wav(target)
            _ensure_not_cancelled(cancellation_probe)
            residual_inspection = inspect_pcm_wav(residual)
            _ensure_not_cancelled(cancellation_probe)
            _require_source_geometry(
                target_inspection.geometry,
                request,
                label=f"target for {role}",
            )
            _require_source_geometry(
                residual_inspection.geometry,
                request,
                label=f"residual for {role}",
            )
            target_documents.append(
                target_inspection.to_artifact_dict(
                    role,
                    target_relative,
                )
            )
            residual_documents.append(
                residual_inspection.to_artifact_dict(
                    role,
                    residual_relative,
                    residual_target_sha256=target_inspection.sha256,
                )
            )
            reconstruction_pairs.append((role, target, residual))

        if not _safe_remove_owned_tree(work):
            raise ValueError("backend staging identity changed")
        _ensure_not_cancelled(cancellation_probe)
        reconstruction = evaluate_target_residual_reconstruction(
            request.source_path,
            reconstruction_pairs,
        )
        _ensure_not_cancelled(cancellation_probe)
        _cross_check_reconstruction_hashes(
            reconstruction,
            source_sha256=request.canonical_sha256,
            targets=target_documents,
            residuals=residual_documents,
        )
        leakage = {
            role: {
                "status": "not_measured",
                "metric": None,
                "score": None,
                "reference_id": None,
            }
            for role in actual_roles
        }
        quality_document = {
            "schema": SEPARATION_QUALITY_SCHEMA,
            "status": "review_required",
            "run_id": plan.run_id,
            "run_plan_sha256": plan.plan_sha256,
            "run_plan": plan.to_dict(),
            "source": {
                "canonical_sha256": request.canonical_sha256,
                "geometry": request.source_geometry.to_dict(),
            },
            "roles": list(actual_roles),
            "artifacts": {
                "targets": target_documents,
                "residuals": residual_documents,
            },
            "reconstruction": reconstruction.to_dict(),
            "leakage": leakage,
            "reconstruction_is_accuracy_evidence": False,
            "limitations": [
                "The controlled fake is for tests and demos only.",
                "Reconstruction closure is not separation-accuracy evidence.",
                "Leakage was not measured.",
                "This in-process fake must not be promoted as a real model run.",
            ],
        }
        quality_path = publish_root / SEPARATION_QUALITY_RELATIVE_PATH
        _atomic_write_new(
            quality_path,
            canonical_json_bytes(quality_document),
        )
        quality_sha256, _ = _hash_bounded_regular_file(
            quality_path,
            maximum_bytes=_QUALITY_AND_RECEIPT_RESERVE_BYTES,
            cancellation_probe=cancellation_probe,
            label="separation quality",
        )
        final_effects = _immutable_input_effects(
            request,
            source_before=source_before,
            checkpoint_before=checkpoint_before,
        )
        if (
            final_effects["source_mutated"]
            or final_effects["checkpoint_mutated"]
        ):
            raise ValueError(
                "immutable input changed before receipt publication"
            )
        _require_runner_code_unchanged(plan)
        quality_receipt = {
            "path": SEPARATION_QUALITY_RELATIVE_PATH,
            "sha256": quality_sha256,
            "status": "review_required",
            "reconstruction": {
                "maximum_absolute_error": (
                    reconstruction.maximum_absolute_error
                ),
                "rms_error": reconstruction.rms_error,
                "threshold": reconstruction.threshold,
                "passed": reconstruction.passed,
            },
            "leakage": leakage,
            "reconstruction_is_accuracy_evidence": False,
        }
        receipt = _build_receipt(
            request,
            plan,
            wall_time_seconds=_elapsed_seconds(started),
            status="complete",
            actual_roles=actual_roles,
            outputs={
                "targets": target_documents,
                "residuals": residual_documents,
            },
            quality=quality_receipt,
            effects=final_effects,
            error=None,
        )
        _atomic_write_new(
            publish_root / SEPARATION_RECEIPT_FILENAME,
            receipt.canonical_bytes(),
        )
        _revalidate_complete_terminal_tree(
            publish,
            request=request,
            plan=plan,
            receipt=receipt,
            quality_document=quality_document,
            cancellation_probe=cancellation_probe,
        )
        _ensure_not_cancelled(cancellation_probe)
        _publish_owned_tree(publish, request.output_dir)
        published = True
        return receipt
    finally:
        if not published:
            _safe_remove_owned_tree(publish)


def _finish_nonloadable_run(
    request: SeparationRequest,
    plan: SeparationRunPlan,
    *,
    work: "_OwnedDirectory",
    started: float,
    status: str,
    error: SeparationError,
    effects: Mapping[str, bool],
) -> SeparationRunReceipt:
    _safe_remove_owned_tree(work)
    publish = _create_private_sibling(request.output_dir, purpose="terminal")
    published = False
    receipt = _build_receipt(
        request,
        plan,
        wall_time_seconds=_elapsed_seconds(started),
        status=status,
        actual_roles=(),
        outputs={"targets": [], "residuals": []},
        quality=None,
        effects=effects,
        error=error,
    )
    try:
        publish_root = _require_owned_directory(publish)
        _atomic_write_new(
            publish_root / SEPARATION_RECEIPT_FILENAME,
            receipt.canonical_bytes(),
        )
        _require_exact_terminal_tree(
            publish_root,
            files={SEPARATION_RECEIPT_FILENAME},
            directories=set(),
        )
        _publish_owned_tree(publish, request.output_dir)
        published = True
        return receipt
    finally:
        if not published:
            _safe_remove_owned_tree(publish)


def _build_receipt(
    request: SeparationRequest,
    plan: SeparationRunPlan,
    *,
    wall_time_seconds: float,
    status: str,
    actual_roles: tuple[str, ...],
    outputs: Mapping[str, Any],
    quality: Mapping[str, Any] | None,
    effects: Mapping[str, bool],
    error: SeparationError | None,
) -> SeparationRunReceipt:
    run_id = plan.run_id
    plan.validate_run_id(run_id)
    return build_separation_run_receipt(
        run_id=run_id,
        run_plan_sha256=plan.plan_sha256,
        run_plan=plan.to_dict(),
        request_fingerprint_sha256=request.fingerprint_sha256,
        status=status,
        loadable=status == "complete",
        source={
            "source_id": request.source_id,
            "source_sha256": request.source_sha256,
            "canonical_sha256": request.canonical_sha256,
            "geometry": request.source_geometry.to_dict(),
        },
        scope={
            "mode": request.scope,
            "parent_node_id": request.parent_node_id,
        },
        backend={
            "backend_id": request.backend_id,
            "package": plan.backend["package"],
            "version": plan.backend["version"],
            "commit": plan.backend["commit"],
            "code_license": plan.backend["code_license"],
            "training_data_note": plan.backend["training_data_note"],
        },
        checkpoint={
            "checkpoint_id": request.checkpoint_id,
            "sha256": request.checkpoint_sha256,
            "weights_license": plan.checkpoint["weights_license"],
            "hash_verified_before_load": True,
            "distribution_policy": plan.checkpoint["distribution_policy"],
        },
        roles={
            "requested": list(request.requested_roles),
            "actual": list(actual_roles),
        },
        execution={
            "runtime": _thaw_json(plan.runtime),
            "device": plan.device,
            "settings": _thaw_json(request.settings),
            "seed": request.seed,
            "wall_time_seconds": wall_time_seconds,
            "command": list(plan.command),
            "network_used": False,
        },
        outputs=outputs,
        quality=quality,
        effects=effects,
        error=error,
    )


def _verify_immutable_inputs(
    request: SeparationRequest,
    *,
    cancellation_probe: _ParentCancellationProbe,
) -> tuple[str, str, int]:
    from .separation_quality import inspect_pcm_wav

    _ensure_not_cancelled(cancellation_probe)
    _require_regular_non_symlink(request.source_path, "source")
    _require_regular_non_symlink(request.checkpoint_path, "checkpoint")
    source = inspect_pcm_wav(request.source_path)
    _ensure_not_cancelled(cancellation_probe)
    if source.sha256 != request.canonical_sha256:
        raise ValueError("source canonical SHA-256 does not match the request")
    _require_source_geometry(source.geometry, request, label="source")
    source_bytes = request.source_path.lstat().st_size
    checkpoint_sha256, _ = _hash_bounded_regular_file(
        request.checkpoint_path,
        maximum_bytes=_MAX_CHECKPOINT_BYTES,
        cancellation_probe=cancellation_probe,
        label="checkpoint",
    )
    if checkpoint_sha256 != request.checkpoint_sha256:
        raise ValueError("checkpoint SHA-256 does not match the request")
    return source.sha256, checkpoint_sha256, source_bytes


def _immutable_input_effects(
    request: SeparationRequest,
    *,
    source_before: str,
    checkpoint_before: str,
) -> dict[str, bool]:
    source_mutated = True
    checkpoint_mutated = True
    try:
        _require_regular_non_symlink(request.source_path, "source")
        source_hash, _ = _hash_bounded_regular_file(
            request.source_path,
            maximum_bytes=_MAX_AGGREGATE_OUTPUT_BYTES,
            cancellation_probe=None,
            label="source",
        )
        source_mutated = source_hash != source_before
    except (OSError, ValueError):
        pass
    try:
        _require_regular_non_symlink(
            request.checkpoint_path,
            "checkpoint",
        )
        checkpoint_hash, _ = _hash_bounded_regular_file(
            request.checkpoint_path,
            maximum_bytes=_MAX_CHECKPOINT_BYTES,
            cancellation_probe=None,
            label="checkpoint",
        )
        checkpoint_mutated = checkpoint_hash != checkpoint_before
    except (OSError, ValueError):
        pass
    return {
        "checkpoint_mutated": checkpoint_mutated,
        "model_downloaded": False,
        "network_used": False,
        "outside_output_writes": False,
        "source_mutated": source_mutated,
    }


def _require_source_geometry(
    geometry: Any,
    request: SeparationRequest,
    *,
    label: str,
) -> None:
    expected = request.source_geometry
    if (
        geometry.sample_rate != expected.sample_rate
        or geometry.channels != expected.channels
        or geometry.frames != expected.frames
    ):
        raise ValueError(f"{label} geometry does not match the request")
    tolerance = max(1.0 / expected.sample_rate, 1e-9)
    if abs(geometry.duration_seconds - expected.duration_seconds) > tolerance:
        raise ValueError(f"{label} duration does not match the request")


def _require_fresh_output_destination(path: Path) -> None:
    parent = path.parent
    _require_directory_non_symlink(parent, "output parent")
    if parent.resolve(strict=True) != parent:
        raise ValueError("output parent changed after request construction")
    try:
        path.lstat()
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError(
            "separation output directory must be fresh and absent"
        )


def _reject_inputs_inside_output_root(request: SeparationRequest) -> None:
    output_root = request.output_dir
    for path, label in (
        (request.source_path, "source"),
        (request.checkpoint_path, "checkpoint"),
    ):
        if path == output_root or output_root in path.parents:
            raise ValueError(
                f"{label} must not be inside the separation output root"
            )


def _create_private_sibling(
    output_path: Path,
    *,
    purpose: str,
) -> _OwnedDirectory:
    _require_fresh_output_destination(output_path)
    created = Path(
        tempfile.mkdtemp(
            prefix=f".{output_path.name}.{purpose}-",
            dir=str(output_path.parent),
        )
    ).resolve()
    created.chmod(_PRIVATE_DIRECTORY_MODE)
    details = created.lstat()
    if details.st_dev != output_path.parent.lstat().st_dev:
        shutil.rmtree(created)
        raise ValueError("separation staging must share the output filesystem")
    return _OwnedDirectory(
        path=created,
        device=details.st_dev,
        inode=details.st_ino,
    )


def _require_owned_directory(owner: _OwnedDirectory) -> Path:
    details = owner.path.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
        raise ValueError("owned staging path is no longer a directory")
    if (details.st_dev, details.st_ino) != (owner.device, owner.inode):
        raise ValueError("owned staging directory identity changed")
    resolved = owner.path.resolve(strict=True)
    if resolved != owner.path:
        raise ValueError("owned staging directory changed location")
    if stat.S_IMODE(details.st_mode) & 0o077:
        raise ValueError("owned staging directory must remain private")
    return resolved


def _safe_remove_owned_tree(owner: _OwnedDirectory) -> bool:
    try:
        details = owner.path.lstat()
    except FileNotFoundError:
        return True
    if (
        stat.S_ISLNK(details.st_mode)
        or not stat.S_ISDIR(details.st_mode)
        or (details.st_dev, details.st_ino) != (owner.device, owner.inode)
    ):
        return False
    shutil.rmtree(owner.path)
    return True


def _publish_owned_tree(owner: _OwnedDirectory, output_path: Path) -> None:
    _require_owned_directory(owner)
    _require_fresh_output_destination(output_path)
    _fsync_tree(owner.path)
    _require_owned_directory(owner)
    _require_fresh_output_destination(output_path)
    os.rename(owner.path, output_path)
    _fsync_directory(output_path.parent)


def _make_private_directory(path: Path) -> None:
    path.mkdir(mode=_PRIVATE_DIRECTORY_MODE, parents=True, exist_ok=True)
    path.chmod(_PRIVATE_DIRECTORY_MODE)


def _confined_regular_wave(
    path: Path,
    *,
    output_root: Path,
) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = output_root / candidate
    try:
        details = candidate.lstat()
    except OSError as exc:
        raise ValueError("backend WAV output is unavailable") from exc
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise ValueError(
            "backend WAV output must be a regular non-symlink file"
        )
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(output_root)
    except ValueError as exc:
        raise ValueError(
            "backend WAV output escaped the private output directory"
        ) from exc
    if resolved.suffix.casefold() != ".wav":
        raise ValueError("backend output must use a WAV filename")
    if details.st_nlink != 1:
        raise ValueError("backend WAV output must not be hard-linked")
    return resolved


def _require_exact_backend_tree(
    staging_root: Path,
    *,
    declared_paths: set[Path],
) -> None:
    observed_files: set[Path] = set()
    observed_directories: set[str] = set()
    casefold_paths: set[str] = set()
    for directory, directory_names, file_names in os.walk(
        staging_root, topdown=True, followlinks=False
    ):
        parent = Path(directory)
        for name in directory_names:
            candidate = parent / name
            details = candidate.lstat()
            if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(
                details.st_mode
            ):
                raise ValueError(
                    "backend staging tree contains an unsafe directory"
                )
            if stat.S_IMODE(details.st_mode) & 0o077:
                raise ValueError(
                    "backend staging directories must remain private"
                )
            relative = candidate.relative_to(staging_root).as_posix()
            folded = relative.casefold()
            if folded in casefold_paths:
                raise ValueError(
                    "backend artifact names collide case-insensitively"
                )
            casefold_paths.add(folded)
            observed_directories.add(relative)
        for name in file_names:
            candidate = parent / name
            details = candidate.lstat()
            if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(
                details.st_mode
            ):
                raise ValueError(
                    "backend staging tree contains a non-regular file"
                )
            resolved = candidate.resolve(strict=True)
            try:
                relative = resolved.relative_to(staging_root).as_posix()
            except ValueError as exc:
                raise ValueError(
                    "backend artifact escaped the private staging root"
                ) from exc
            folded = relative.casefold()
            if folded in casefold_paths:
                raise ValueError(
                    "backend artifact names collide case-insensitively"
                )
            casefold_paths.add(folded)
            observed_files.add(resolved)
    expected_directories: set[str] = set()
    for path in declared_paths:
        relative = path.relative_to(staging_root)
        for parent in relative.parents:
            if parent != Path("."):
                expected_directories.add(parent.as_posix())
    if (
        observed_files != declared_paths
        or observed_directories != expected_directories
    ):
        raise ValueError(
            "backend staging tree contains undeclared or missing entries"
        )


def _require_exact_terminal_tree(
    root: Path,
    *,
    files: set[str],
    directories: set[str],
) -> None:
    observed_files: set[str] = set()
    observed_directories: set[str] = set()
    folded: set[str] = set()
    for directory, directory_names, file_names in os.walk(
        root, topdown=True, followlinks=False
    ):
        parent = Path(directory)
        for name in directory_names:
            candidate = parent / name
            details = candidate.lstat()
            if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(
                details.st_mode
            ):
                raise ValueError("terminal tree contains an unsafe directory")
            relative = candidate.relative_to(root).as_posix()
            if relative.casefold() in folded:
                raise ValueError("terminal paths collide case-insensitively")
            folded.add(relative.casefold())
            observed_directories.add(relative)
        for name in file_names:
            candidate = parent / name
            details = candidate.lstat()
            if (
                stat.S_ISLNK(details.st_mode)
                or not stat.S_ISREG(details.st_mode)
                or details.st_nlink != 1
            ):
                raise ValueError("terminal tree contains an unsafe file")
            relative = candidate.relative_to(root).as_posix()
            if relative.casefold() in folded:
                raise ValueError("terminal paths collide case-insensitively")
            folded.add(relative.casefold())
            observed_files.add(relative)
    if observed_files != files or observed_directories != directories:
        raise ValueError("terminal tree contains undeclared entries")


def _resource_preflight(
    request: SeparationRequest,
    *,
    source_bytes: int,
) -> None:
    role_count = len(request.requested_roles)
    terminal_files = role_count * 2 + 2
    if terminal_files > _MAX_TERMINAL_FILE_COUNT:
        raise ValueError("separation terminal file count exceeds its bound")
    aggregate = (
        source_bytes * role_count * 2
        + _QUALITY_AND_RECEIPT_RESERVE_BYTES
    )
    if aggregate > _MAX_AGGREGATE_OUTPUT_BYTES:
        raise ValueError("projected separation output exceeds its hard bound")
    available = shutil.disk_usage(request.output_dir.parent).free
    if available < aggregate + _FREE_SPACE_RESERVE_BYTES:
        raise ValueError(
            "insufficient free space for bounded separation output and reserve"
        )


def _hash_bounded_regular_file(
    path: Path,
    *,
    maximum_bytes: int,
    cancellation_probe: _ParentCancellationProbe | None,
    label: str,
) -> tuple[str, int]:
    _require_regular_non_symlink(path, label)
    before = path.lstat()
    if before.st_size <= 0 or before.st_size > maximum_bytes:
        raise ValueError(f"{label} exceeds its file-size bound")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
        ) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ):
            raise ValueError(f"{label} changed while it was opened")
        while True:
            _ensure_not_cancelled(cancellation_probe)
            chunk = handle.read(_COPY_BYTES)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(handle.fileno())
    current = path.lstat()
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    if identity != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or identity != (
        current.st_dev,
        current.st_ino,
        current.st_size,
        current.st_mtime_ns,
    ):
        raise ValueError(f"{label} changed while it was hashed")
    return digest.hexdigest(), before.st_size


def _cross_check_reconstruction_hashes(
    reconstruction: Any,
    *,
    source_sha256: str,
    targets: list[dict[str, Any]],
    residuals: list[dict[str, Any]],
) -> None:
    target_by_role = {item["role"]: item for item in targets}
    residual_by_role = {item["role"]: item for item in residuals}
    evidence_by_role = {
        item.role: item for item in reconstruction.per_role
    }
    if (
        set(evidence_by_role) != set(target_by_role)
        or set(evidence_by_role) != set(residual_by_role)
    ):
        raise ValueError("reconstruction evidence roles do not bind artifacts")
    for role, evidence in evidence_by_role.items():
        if (
            evidence.source_sha256 != source_sha256
            or evidence.target_sha256 != target_by_role[role]["sha256"]
            or evidence.residual_sha256
            != residual_by_role[role]["sha256"]
        ):
            raise ValueError(
                "reconstruction hashes do not bind persisted artifacts"
            )


def _require_runner_code_unchanged(plan: SeparationRunPlan) -> None:
    current, _ = _hash_bounded_regular_file(
        Path(__file__).resolve(),
        maximum_bytes=_MAX_RUNNER_MODULE_BYTES,
        cancellation_probe=None,
        label="separation runner module",
    )
    if current != plan.runner["module_sha256"]:
        raise ValueError("separation runner module changed during the run")


def _revalidate_complete_terminal_tree(
    publish: _OwnedDirectory,
    *,
    request: SeparationRequest,
    plan: SeparationRunPlan,
    receipt: SeparationRunReceipt,
    quality_document: Mapping[str, Any],
    cancellation_probe: _ParentCancellationProbe,
) -> None:
    from .separation_quality import inspect_pcm_wav

    root = _require_owned_directory(publish)
    expected_files = {
        SEPARATION_QUALITY_RELATIVE_PATH,
        SEPARATION_RECEIPT_FILENAME,
    }
    expected_directories = {"QUALITY", "STEMS", "RESIDUALS"}
    for collection in ("targets", "residuals"):
        for expected in receipt.outputs[collection]:
            _ensure_not_cancelled(cancellation_probe)
            relative = expected["path"]
            candidate = _confined_regular_wave(
                root / relative,
                output_root=root,
            )
            inspected = inspect_pcm_wav(candidate)
            residual_target = (
                expected["target_sha256"]
                if collection == "residuals"
                else None
            )
            actual = inspected.to_artifact_dict(
                expected["role"],
                relative,
                residual_target_sha256=residual_target,
            )
            if actual != _thaw_json(expected):
                raise ValueError(
                    "terminal WAV evidence changed before publication"
                )
            expected_files.add(relative)
    plan.validate_run_id(receipt.run_id)
    if (
        _thaw_json(receipt.run_plan) != plan.to_dict()
        or receipt.run_plan_sha256 != plan.plan_sha256
        or quality_document["run_plan"] != plan.to_dict()
        or quality_document["run_plan_sha256"] != plan.plan_sha256
        or quality_document["run_id"] != plan.run_id
    ):
        raise ValueError("quality run-plan binding is invalid")
    quality_path = root / SEPARATION_QUALITY_RELATIVE_PATH
    quality_hash, _ = _hash_bounded_regular_file(
        quality_path,
        maximum_bytes=_QUALITY_AND_RECEIPT_RESERVE_BYTES,
        cancellation_probe=cancellation_probe,
        label="separation quality",
    )
    if quality_hash != receipt.quality["sha256"]:
        raise ValueError("quality hash changed before publication")
    if quality_path.read_bytes() != canonical_json_bytes(quality_document):
        raise ValueError("quality JSON is not canonical")
    receipt_path = root / SEPARATION_RECEIPT_FILENAME
    if receipt_path.read_bytes() != receipt.canonical_bytes():
        raise ValueError("receipt changed before publication")
    _require_exact_terminal_tree(
        root,
        files=expected_files,
        directories=expected_directories,
    )
    _require_runner_code_unchanged(plan)
    final_effects = _immutable_input_effects(
        request,
        source_before=request.canonical_sha256,
        checkpoint_before=request.checkpoint_sha256,
    )
    if final_effects["source_mutated"] or final_effects["checkpoint_mutated"]:
        raise ValueError("immutable input changed before terminal publication")


def _fsync_tree(root: Path) -> None:
    for directory, _, file_names in os.walk(
        root, topdown=False, followlinks=False
    ):
        parent = Path(directory)
        for name in file_names:
            descriptor = os.open(parent / name, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        _fsync_directory(parent)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _elapsed_seconds(started: float) -> float:
    return max(0.0, time.monotonic() - started)


def _actual_runtime_identity() -> dict[str, str]:
    return {
        "name": "python",
        "implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "system": platform.system() or "unknown",
        "machine": platform.machine() or "unknown",
    }


def _installed_package_version() -> str:
    try:
        return importlib.metadata.version(_FAKE_PACKAGE)
    except importlib.metadata.PackageNotFoundError:
        return "uninstalled"


def _require_regular_non_symlink(path: Path, label: str) -> None:
    try:
        details = path.lstat()
    except OSError as exc:
        raise ValueError(f"{label} file is unavailable") from exc
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise ValueError(f"{label} must be a regular non-symlink file")


def _require_directory_non_symlink(path: Path, label: str) -> None:
    try:
        details = path.lstat()
    except OSError as exc:
        raise ValueError(f"{label} is unavailable") from exc
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
        raise ValueError(f"{label} must be a regular non-symlink directory")


def _write_silent_wave(
    path: Path,
    *,
    channels: int,
    sample_width_bytes: int,
    sample_rate: int,
    frames: int,
    cancellation_probe: _ParentCancellationProbe | None,
) -> None:
    if path.exists():
        raise FileExistsError("fake residual WAV already exists")
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(sample_width_bytes)
        writer.setframerate(sample_rate)
        remaining = frames
        frame = b"\x00" * (channels * sample_width_bytes)
        while remaining:
            _ensure_not_cancelled(cancellation_probe)
            count = min(remaining, _ZERO_WRITE_FRAMES)
            writer.writeframesraw(frame * count)
            remaining -= count
        writer.writeframes(b"")
    path.chmod(_PRIVATE_FILE_MODE)


def _copy_file_cancellable(
    source: Path,
    destination: Path,
    *,
    cancellation_probe: _ParentCancellationProbe | None,
) -> None:
    if destination.exists():
        raise FileExistsError("fake target WAV already exists")
    with source.open("rb") as reader, destination.open("xb") as writer:
        os.fchmod(writer.fileno(), _PRIVATE_FILE_MODE)
        while True:
            _ensure_not_cancelled(cancellation_probe)
            chunk = reader.read(_COPY_BYTES)
            if not chunk:
                break
            writer.write(chunk)
        writer.flush()
        os.fsync(writer.fileno())
    destination.chmod(_PRIVATE_FILE_MODE)


def _atomic_write_new(path: Path, content: bytes) -> None:
    _make_private_directory(path.parent)
    if path.exists():
        raise FileExistsError("separation evidence already exists")
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("xb") as handle:
            os.fchmod(handle.fileno(), _PRIVATE_FILE_MODE)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(_PRIVATE_FILE_MODE)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def _fake_cancelled_result() -> SeparationResult:
    return SeparationResult(
        status="cancelled",
        error=SeparationError(
            code="cancelled",
            message="Controlled fake separation was cancelled",
            retryable=True,
        ),
    )


def _cancelled(probe: _ParentCancellationProbe | None) -> bool:
    return probe is not None and probe()


def _ensure_not_cancelled(
    probe: _ParentCancellationProbe | None,
) -> None:
    if _cancelled(probe):
        raise _CancellationRequested


def _reject_path_or_url(value: str, label: str) -> None:
    if (
        "/" in value
        or "\\" in value
        or value.startswith("~")
        or "://" in value
        or "\x00" in value
    ):
        raise ValueError(f"{label} must not contain a path or URL")


def _freeze_json(value: Any, label: str) -> Any:
    if value is None or isinstance(value, (bool, str, int, float)):
        if isinstance(value, float) and not (
            float("-inf") < value < float("inf")
        ):
            raise ValueError(f"{label} contains a non-finite number")
        if isinstance(value, str):
            _reject_path_or_url(value, label)
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError(f"{label} contains an invalid key")
            frozen[key] = _freeze_json(item, f"{label}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_json(item, f"{label}[{index}]")
            for index, item in enumerate(value)
        )
    raise ValueError(f"{label} must contain only JSON values")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


__all__ = [
    "FAKE_SEPARATION_BACKEND_ID",
    "REAL_SEPARATION_BACKENDS_SUPPORTED",
    "SEPARATION_CACHE_REPLAY_SUPPORTED",
    "SEPARATION_QUALITY_RELATIVE_PATH",
    "SEPARATION_QUALITY_SCHEMA",
    "SEPARATION_RECEIPT_FILENAME",
    "SEPARATION_RUNNER_SCHEMA",
    "SEPARATION_RUNNER_VERSION",
    "SEPARATION_RUN_PLAN_SCHEMA",
    "FakeSeparationBackend",
    "SeparationCancellationToken",
    "SeparationRunMetadata",
    "SeparationRunPlan",
    "run_separation",
]
