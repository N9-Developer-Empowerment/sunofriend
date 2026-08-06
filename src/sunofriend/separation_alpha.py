"""Public, opt-in local finished-mix separation coordinator.

The default remains the pinned two-stem Kim Vocal 2 MLX profile. Role-driven
scopes also expose the explicitly selected SCNet-large core-four public preview.
The original Demucs MLX baseline and its first PyTorch fallback remain blocked
after exhausting their bounded objective remediation budgets.

This is not a claim of ground-truth separation and it does not silently feed
the generated stems into MIDI conversion.  The musician listens first, then
decides whether the stems are useful enough for a separate Sunofriend run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ._separation_melroformer_artifacts import (
    _inspect_companion_files,
    _inspect_local_checkpoint,
)
from ._separation_melroformer_runtime_evidence import (
    _verify_private_melroformer_source_tree,
)
from ._separation_safetensors_inspection import _inspect_private_safetensors
from .audio_formats import (
    DEFAULT_AUDIO_IMPORT_LIMITS,
    AudioProbe,
    decoder_capability_report,
    file_sha256,
    probe_stable_audio,
    resolve_executable,
)
from .source_import import _ffmpeg_decode_arguments
from .source_project import RIGHTS_CATEGORIES
from .separation_review import render_review_html, render_start_here
from .separation_profiles import (
    CORE_FOUR_FALLBACK_PROFILE_ID,
    CORE_FOUR_PROFILE_ID,
    KIM_VOCAL_PROFILE_ID,
    SCNET_RELEASE_PROFILE_ID,
    SeparationProfileSpec,
    profile_for_scope,
    separation_profile,
)
from .separation_other_refinement_demucs_mlx_run import (
    execute_installed_other_refinement,
    plan_installed_other_refinement,
)
from .separation_scopes import (
    DEFAULT_SCOPE_ID,
    FULL_STEM_SCOPE_ID,
    SeparationScopeSpec,
    require_executable_scope,
    separation_capabilities,
    separation_scope,
)


SCHEMA = "sunofriend.experimental-separation-alpha.v1"
PLAN_SCHEMA = "sunofriend.experimental-separation-plan.v1"
PROFILE_NAME = KIM_VOCAL_PROFILE_ID
CORE_FOUR_PROFILE_IDS = frozenset(
    {CORE_FOUR_PROFILE_ID, CORE_FOUR_FALLBACK_PROFILE_ID, SCNET_RELEASE_PROFILE_ID}
)
MODEL_ID = "mlx-community/mel-roformer-kim-vocal-2-mlx"
MODEL_REVISION = "64cbfcb004e39430e5f584552c05949440ec39ce"
FEEDBACK_URL = (
    "https://github.com/N9-Developer-Empowerment/sunofriend/issues/new"
    "?template=daw-ai-compatibility.yml"
)
MINIMUM_FREE_HEADROOM_BYTES = 1024**3


@dataclass(frozen=True)
class SeparationProfile:
    repository_root: Path
    runtime_python: Path
    model_root: Path
    source_root: Path
    checkpoint: Path
    companion_root: Path
    profile_id: str = PROFILE_NAME
    backend: str = "mlx-audio-mel-roformer"
    model_config: Path | None = None
    installation_receipt: Path | None = None


@dataclass(frozen=True)
class SeparationPlan:
    source: Path
    output: Path
    source_sha256: str
    probe: AudioProbe
    ffmpeg: Path
    ffprobe: Path
    decoder: Mapping[str, Any]
    profile: SeparationProfile
    scope: SeparationScopeSpec
    device: str
    rights_category: str
    required_free_bytes: int
    available_free_bytes: int
    activation_canary: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PLAN_SCHEMA,
            "status": "ready_explicit_execution_required",
            "experimental": True,
            "activation_canary": self.activation_canary,
            "source": {
                "name": self.source.name,
                "bytes": self.probe.source_bytes,
                "sha256": self.source_sha256,
                "probe": self.probe.to_dict(),
            },
            "output": str(self.output),
            "separator": {
                "scope_id": self.scope.scope_id,
                "profile_id": self.profile.profile_id,
                "model_id": self.scope.model_id,
                "model_revision": self.scope.model_revision,
                "device": self.device,
                "roles": [role.role_id for role in self.scope.roles],
                "role_details": [role.to_dict() for role in self.scope.roles],
                "diagnostic": "reconstruction-check",
            },
            "rights": {
                "category": self.rights_category,
                "confirmation_required_for_execution": True,
            },
            "resources": {
                "required_free_bytes": self.required_free_bytes,
                "available_free_bytes": self.available_free_bytes,
            },
            "effects_if_executed": {
                "writes": [str(self.output)],
                "network": [],
                "installs": [],
                "uploads": [],
            },
            "limitations": list(self.scope.limitations),
        }


WorkerRunner = Callable[[SeparationPlan, Path], Mapping[str, Any]]


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_profile(
    *,
    root: str | Path | None = None,
    runtime_python: str | Path | None = None,
    model_root: str | Path | None = None,
    profile_id: str = PROFILE_NAME,
) -> SeparationProfile:
    spec = separation_profile(profile_id)
    repo = Path(root).expanduser().absolute() if root else repository_root()
    data_root = (
        Path(
            os.environ.get(
                "SUNOFRIEND_SEPARATION_ROOT",
                str(Path.home() / ".local/share/sunofriend/separation"),
            )
        )
        .expanduser()
        .absolute()
    )
    model = (
        Path(
            model_root
            or os.environ.get("SUNOFRIEND_SEPARATION_MODEL_ROOT", "")
            or data_root / spec.profile_id
        )
        .expanduser()
        .absolute()
    )
    runtime = (
        Path(
            runtime_python
            or os.environ.get("SUNOFRIEND_SEPARATION_PYTHON", "")
            or model / "runtime/bin/python"
        )
        .expanduser()
        .absolute()
    )
    if spec.profile_id in CORE_FOUR_PROFILE_IDS:
        if spec.profile_id == SCNET_RELEASE_PROFILE_ID:
            checkpoint = model / "model/SCNet-large.th"
            model_config = model / "model/scnet-large-config.yaml"
            companion_root = model
        elif spec.profile_id == CORE_FOUR_FALLBACK_PROFILE_ID:
            checkpoint = model / "model/955717e8-8726e21a.th"
            model_config = model / "model/htdemucs.yaml"
            companion_root = model / "model"
        else:
            checkpoint = model / "model/htdemucs.safetensors"
            model_config = model / "model/htdemucs_config.json"
            companion_root = model / "model"
        return SeparationProfile(
            repository_root=repo,
            runtime_python=runtime,
            model_root=model,
            source_root=model / "TERMS",
            checkpoint=checkpoint,
            companion_root=companion_root,
            profile_id=spec.profile_id,
            backend=spec.backend,
            model_config=model_config,
            installation_receipt=model / "INSTALLATION.json",
        )
    return SeparationProfile(
        repository_root=repo,
        runtime_python=runtime,
        model_root=model,
        source_root=model / "mlx-audio-source",
        checkpoint=model / "model.safetensors",
        companion_root=model / "checkpoint-directory",
        profile_id=spec.profile_id,
        backend=spec.backend,
    )


def separation_doctor(profile: SeparationProfile) -> dict[str, Any]:
    """Read-only verification of platform, runtime and exact local artifacts."""

    checks: dict[str, dict[str, Any]] = {}
    machine = platform.machine().casefold()
    system = platform.system()
    checks["platform"] = {
        "ready": system == "Darwin" and machine == "arm64",
        "system": system,
        "machine": machine,
        "required": "macOS on Apple silicon",
    }
    checks["repository"] = {
        "ready": (profile.repository_root / "pyproject.toml").is_file(),
    }
    spec = separation_profile(profile.profile_id)
    checks["runtime"] = _runtime_check(
        profile.runtime_python,
        expected_packages=(
            spec.packages() if profile.profile_id in CORE_FOUR_PROFILE_IDS else None
        ),
        expected_pytorch=(
            spec.backend in {"demucs-infer", "scnet-official-release-adapter"}
        ),
    )
    if profile.profile_id in CORE_FOUR_PROFILE_IDS:
        _add_core_four_checks(checks, profile=profile, spec=spec)
        setup_command = f"{spec.setup_script} --install --accept-model-terms"
        if spec.profile_id == SCNET_RELEASE_PROFILE_ID:
            setup_command += " --accept-checkpoint-use"
    else:
        checks["source_overlay"] = _safe_check(
            lambda: _verify_private_melroformer_source_tree(profile.source_root)
        )
        checks["checkpoint"] = _safe_check(
            lambda: _require_verified_checkpoint(profile.checkpoint)
        )
        checks["companions"] = _safe_check(
            lambda: _require_verified_companions(profile.companion_root)
        )
        setup_command = (
            "scripts/setup-separation-alpha-macos.sh --install --accept-model-terms"
        )
    required = [item for item in checks.values() if not item.get("advisory")]
    ready = all(bool(item.get("ready")) for item in required)
    return {
        "schema": "sunofriend.experimental-separation-doctor.v1",
        "status": "ready" if ready else "setup_required",
        "ready": ready,
        "experimental": True,
        "profile": spec.to_dict(),
        "checks": checks,
        "setup_command": setup_command,
        "effects": {
            "filesystem_write": False,
            "network_used": False,
            "model_loaded": False,
            "audio_processed": False,
        },
    }


def plan_separation(
    source: str | Path,
    output: str | Path,
    *,
    rights_category: str,
    scope_id: str = DEFAULT_SCOPE_ID,
    device: str | None = None,
    ffmpeg: str | Path = "ffmpeg",
    ffprobe: str | Path = "ffprobe",
    profile: SeparationProfile | None = None,
    activation_canary: bool = False,
) -> SeparationPlan:
    if rights_category not in RIGHTS_CATEGORIES - {"unknown", "declined_to_state"}:
        raise ValueError(
            "separation requires one affirmative rights category: "
            "owned, licensed, authorised_private_use or statutory_exception"
        )
    if activation_canary:
        if scope_id != FULL_STEM_SCOPE_ID:
            raise ValueError("activation canaries are limited to core-four-stems-v1")
        scope = separation_scope(scope_id)
    else:
        scope = require_executable_scope(scope_id)
    selected = profile or resolve_profile(
        profile_id=profile_for_scope(scope_id).profile_id
    )
    runtime_device = str(
        dict(separation_profile(selected.profile_id).inference_settings).get(
            "device", "gpu"
        )
    )
    fixed_device = "gpu" if runtime_device in {"gpu", "mlx-gpu"} else runtime_device
    if device is None:
        device = str(fixed_device)
    if device not in {"gpu", "cpu"}:
        raise ValueError("separation device must be gpu or cpu")
    if selected.profile_id != scope.worker_profile_id:
        raise ValueError("separation profile does not match the selected scope")
    if scope_id == FULL_STEM_SCOPE_ID and device != fixed_device:
        raise ValueError(
            f"core-four profile {selected.profile_id} requires fixed {fixed_device} inference"
        )
    doctor = separation_doctor(selected)
    if not doctor["ready"]:
        missing = ", ".join(
            name for name, item in doctor["checks"].items() if not item.get("ready")
        )
        raise RuntimeError(
            f"experimental separation setup is not ready ({missing}); run "
            f"{doctor['setup_command']}"
        )
    ffmpeg_path = resolve_executable(ffmpeg)
    ffprobe_path = resolve_executable(ffprobe)
    decoder = decoder_capability_report(ffmpeg=ffmpeg_path, ffprobe=ffprobe_path)
    if not decoder["policy"]["pcm24_encoder_available"]:
        raise RuntimeError("the selected FFmpeg build does not provide pcm_s24le")
    probe, digest = probe_stable_audio(source, ffprobe=ffprobe_path)
    destination = Path(output).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"separation output already exists: {destination}")
    parent = _nearest_existing_parent(destination.parent)
    available = shutil.disk_usage(parent).free
    frames = int(probe.duration_seconds * 44_100 + 0.999999)
    required = max(
        MINIMUM_FREE_HEADROOM_BYTES,
        probe.source_bytes + frames * 40,
    )
    if available < required:
        raise OSError(
            f"insufficient free space: need {required} bytes, found {available}"
        )
    return SeparationPlan(
        source=Path(source).expanduser().absolute().resolve(),
        output=destination,
        source_sha256=digest,
        probe=probe,
        ffmpeg=ffmpeg_path,
        ffprobe=ffprobe_path,
        decoder=decoder,
        profile=selected,
        scope=scope,
        device=device,
        rights_category=rights_category,
        required_free_bytes=required,
        available_free_bytes=available,
        activation_canary=activation_canary,
    )


def execute_separation(
    plan: SeparationPlan,
    *,
    confirm_rights: bool,
    worker_runner: WorkerRunner | None = None,
) -> dict[str, Any]:
    """Execute a verified plan into one fresh, atomically published folder."""

    if confirm_rights is not True:
        raise PermissionError(
            "execution requires --confirm-rights for audio you may process"
        )
    if os.path.lexists(plan.output):
        raise FileExistsError(f"separation output already exists: {plan.output}")
    if file_sha256(plan.source) != plan.source_sha256:
        raise ValueError("source audio changed after the separation plan")
    doctor = separation_doctor(plan.profile)
    if not doctor["ready"]:
        raise RuntimeError("experimental separation setup changed after planning")
    plan.output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{plan.output.name}.building-",
            dir=plan.output.parent,
        )
    )
    try:
        canonical = staging / "TEMP/source-44100-stereo-pcm24.wav"
        canonical.parent.mkdir(parents=True, exist_ok=False)
        arguments = _ffmpeg_decode_arguments(
            plan.source,
            canonical,
            duration_seconds=plan.probe.duration_seconds,
            maximum_output_bytes=DEFAULT_AUDIO_IMPORT_LIMITS.maximum_canonical_bytes,
        )
        if plan.scope.scope_id == FULL_STEM_SCOPE_ID:
            codec_index = arguments.index("-c:a")
            arguments[codec_index:codec_index] = ["-ar", "44100", "-ac", "2"]
        _run_command(
            [str(plan.ffmpeg), *arguments],
            timeout=max(120.0, min(1800.0, plan.probe.duration_seconds * 4.0)),
            label="FFmpeg canonical decode",
        )
        run_worker = worker_runner or _run_worker
        worker = dict(run_worker(plan, staging))
        if worker.get("status") != "complete_unreviewed":
            raise RuntimeError("experimental separation worker did not complete")
        shutil.rmtree(staging / "TEMP", ignore_errors=True)
        report = _build_report(plan, worker=worker, doctor=doctor, root=staging)
        technical = staging / "TECHNICAL"
        technical.mkdir(exist_ok=True)
        _write_json(technical / "separation-report.json", report)
        (staging / "START-HERE.txt").write_text(
            render_start_here(report), encoding="utf-8"
        )
        review_dir = staging / "REVIEW"
        review_dir.mkdir(exist_ok=True)
        (review_dir / "separation_review.html").write_text(
            render_review_html(report), encoding="utf-8"
        )
        os.replace(staging, plan.output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    stems = {
        role.role_id: str(plan.output / role.relative_path) for role in plan.scope.roles
    }
    result = {
        **report,
        "root": str(plan.output),
        "start_here": str(plan.output / "START-HERE.txt"),
        "review_html": str(plan.output / "REVIEW/separation_review.html"),
        "stems": stems,
    }
    # Preserve the first alpha's convenient top-level return keys.
    result.update(stems)
    return result


def _run_worker(plan: SeparationPlan, staging: Path) -> Mapping[str, Any]:
    result = staging / "worker-result.json"
    if plan.profile.profile_id in CORE_FOUR_PROFILE_IDS:
        if plan.profile.model_config is None:
            raise RuntimeError("core-four model configuration path is missing")
        spec = separation_profile(plan.profile.profile_id)
        worker_command = [
            str(plan.profile.runtime_python),
            str(plan.profile.repository_root / spec.worker_script),
            "--source",
            str(staging / "TEMP/source-44100-stereo-pcm24.wav"),
            "--destination",
            str(staging),
            "--result",
            str(result),
            "--model-root",
            str(plan.profile.companion_root),
            "--network-denial-enforced",
        ]
        sandbox = Path("/usr/bin/sandbox-exec")
        if not sandbox.is_file():
            raise RuntimeError("core-four execution requires macOS network denial")
        command = [
            str(sandbox),
            "-p",
            "(version 1)(deny network*)(allow default)",
            *worker_command,
        ]
        timeout = min(900.0, plan.probe.duration_seconds * 2.0)
    else:
        command = [
            str(plan.profile.runtime_python),
            str(plan.profile.repository_root / "src/sunofriend/separation_worker.py"),
            "--source",
            str(staging / "TEMP/source-44100-stereo-pcm24.wav"),
            "--destination",
            str(staging),
            "--result",
            str(result),
            "--source-root",
            str(plan.profile.source_root),
            "--checkpoint",
            str(plan.profile.checkpoint),
            "--companion-root",
            str(plan.profile.companion_root),
            "--device",
            plan.device,
        ]
        timeout = max(900.0, min(7200.0, plan.probe.duration_seconds * 30.0))
    environment = dict(os.environ)
    source_path = str(plan.profile.repository_root / "src")
    environment["PYTHONPATH"] = (
        source_path
        if not environment.get("PYTHONPATH")
        else source_path + os.pathsep + environment["PYTHONPATH"]
    )
    environment.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "NO_PROXY": "*",
            "no_proxy": "*",
            "PIP_NO_INDEX": "1",
            "PYTHONNOUSERSITE": "1",
        }
    )
    _run_command(
        command,
        timeout=timeout,
        label="local separation worker",
        env=environment,
    )
    try:
        document = json.loads(result.read_text(encoding="utf-8"))
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("separation worker result is missing or invalid") from exc
    if plan.profile.profile_id in CORE_FOUR_PROFILE_IDS:
        _validate_core_four_worker_evidence(document, plan=plan)
    result.unlink()
    return document


def _build_report(
    plan: SeparationPlan,
    *,
    worker: Mapping[str, Any],
    doctor: Mapping[str, Any],
    root: Path,
) -> dict[str, Any]:
    role_details = [role.to_dict() for role in plan.scope.roles]
    activation_canary = bool(getattr(plan, "activation_canary", False))
    profile_id = getattr(
        getattr(plan, "profile", None), "profile_id", plan.scope.worker_profile_id
    )
    expected_paths = {role.role_id: role.relative_path for role in plan.scope.roles}
    expected_paths.update(
        {
            "source_reference": "SOURCE/source-reference.wav",
            "reconstruction_check": "AUDIO/reconstruction-check.wav",
        }
    )
    worker_outputs = _validated_worker_outputs(
        worker,
        expected_roles=tuple(expected_paths),
    )
    outputs: dict[str, dict[str, Any]] = {}
    for role, relative in expected_paths.items():
        path = root / relative
        if not path.is_file():
            raise RuntimeError(f"separation worker omitted {relative}")
        claim = {
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
        reported = worker_outputs[role]
        if (
            reported.get("bytes") != claim["bytes"]
            or reported.get("sha256") != claim["sha256"]
        ):
            raise RuntimeError(
                f"separation worker claim differs from persisted {relative}"
            )
        outputs[role] = claim
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "complete_unreviewed",
        "review_status": "not_reviewed",
        "quality_status": "human_listening_required",
        "experimental": True,
        "evidence_scope": (
            "bounded_activation_canary" if activation_canary else "public_opt_in_result"
        ),
        "local_only": True,
        "source": {
            "name": plan.source.name,
            "bytes": plan.probe.source_bytes,
            "sha256": plan.source_sha256,
            "duration_seconds": plan.probe.duration_seconds,
        },
        "rights": {
            "category": plan.rights_category,
            "confirmed_before_execution": True,
        },
        "separator": {
            "scope_id": plan.scope.scope_id,
            "profile_id": profile_id,
            "profile_status": separation_profile(profile_id).status,
            "scope_label": plan.scope.label,
            "roles": [role.role_id for role in plan.scope.roles],
            "role_details": role_details,
            "model_id": plan.scope.model_id,
            "model_revision": plan.scope.model_revision,
            "worker_profile_id": plan.scope.worker_profile_id,
            "device": plan.device,
            "worker": worker,
        },
        "outputs": outputs,
        "doctor": {
            "status": doctor["status"],
            "exact_profile_verified": doctor["ready"],
        },
        "feedback": {
            "local_review": "REVIEW/separation_review.html",
            "public_report_url": FEEDBACK_URL,
            "audio_uploaded_automatically": False,
            "review_uploaded_automatically": False,
        },
        "activation": {
            "canary_evidence_only": activation_canary,
            "profile_status_changed": False,
            "public_access_changed": False,
            "automatic_model_promotion": False,
            "automatic_midi_activation": False,
        },
        "next_steps": [
            "Open START-HERE.txt and listen in the local review page.",
            "Use the stems only if your listening review finds them useful.",
            "Put useful stems in a new folder before running Sunofriend create or Studio.",
            "Share text-only observations through the public feedback link if you choose.",
        ],
        "limitations": [
            *plan.scope.limitations,
            "A good reconstruction check proves additive accounting, not stem accuracy.",
            "Feedback is advisory and never silently changes a model or musical default.",
        ],
    }
    document["document_sha256"] = _document_sha256(document)
    return document


def _validated_worker_outputs(
    worker: Mapping[str, Any], *, expected_roles: tuple[str, ...]
) -> Mapping[str, Mapping[str, Any]]:
    outputs = worker.get("outputs")
    if (
        worker.get("status") != "complete_unreviewed"
        or not isinstance(outputs, Mapping)
        or set(outputs) != set(expected_roles)
        or any(not isinstance(outputs[role], Mapping) for role in expected_roles)
    ):
        raise RuntimeError("separation worker output contract differs")
    return outputs


def _add_core_four_checks(
    checks: dict[str, dict[str, Any]],
    *,
    profile: SeparationProfile,
    spec: SeparationProfileSpec,
) -> None:
    if profile.model_config is None or profile.installation_receipt is None:
        checks["profile_paths"] = {
            "ready": False,
            "reason": "core-four profile paths are incomplete",
        }
        return
    weights = spec.artifact("weights")
    if spec.profile_id == CORE_FOUR_PROFILE_ID:
        checks["weights"] = _safe_check(
            lambda: _inspect_private_safetensors(
                profile.checkpoint,
                expected_bytes=weights.bytes,
                expected_sha256=weights.sha256,
            )
        )
        checks["config"] = _safe_check(
            lambda: _require_core_four_config(profile.model_config, spec=spec)
        )
    elif spec.profile_id == SCNET_RELEASE_PROFILE_ID:
        checks["weights"] = _safe_check(
            lambda: _require_artifact_identity(
                profile.checkpoint,
                expected_bytes=weights.bytes,
                expected_sha256=weights.sha256,
            )
        )
        checks["config"] = _safe_check(
            lambda: _require_scnet_core_four_config(profile.model_config, spec=spec)
        )
        checks["compatibility_receipt"] = _safe_check(
            lambda: _require_scnet_compatibility_receipt(
                profile.model_root / "COMPATIBILITY.json", spec=spec
            )
        )
    else:
        checks["weights"] = _safe_check(
            lambda: _require_artifact_identity(
                profile.checkpoint,
                expected_bytes=weights.bytes,
                expected_sha256=weights.sha256,
            )
        )
        checks["config"] = _safe_check(
            lambda: _require_fallback_core_four_config(profile.model_config, spec=spec)
        )
    for artifact in spec.artifacts:
        if artifact.name in {"weights", "config"}:
            continue
        name = artifact.name
        checks[name] = _safe_check(
            lambda artifact=artifact: _require_artifact_identity(
                profile.model_root / artifact.relative_path,
                expected_bytes=artifact.bytes,
                expected_sha256=artifact.sha256,
            )
        )
    checks["terms_receipt"] = _safe_check(
        lambda: _require_installation_receipt(profile.installation_receipt, spec=spec)
    )
    checks["network_denial"] = {
        "ready": Path("/usr/bin/sandbox-exec").is_file(),
        "required": "/usr/bin/sandbox-exec",
    }
    memory_bytes = _system_memory_bytes()
    benchmark_memory_bytes = (
        36 * 1024**3 if spec.profile_id == SCNET_RELEASE_PROFILE_ID else 16 * 1024**3
    )
    verified_supported_class = memory_bytes == benchmark_memory_bytes
    checks["machine_class"] = {
        "ready": True,
        "advisory": True,
        "memory_bytes": memory_bytes,
        "benchmark_memory_bytes": benchmark_memory_bytes,
        "verified_supported_class": verified_supported_class,
        "verified_16_gib_class": memory_bytes == 16 * 1024**3,
        "warning": (
            None
            if verified_supported_class
            else "this Apple-silicon memory class is accessible but unverified; 12 GiB supervision remains active"
        ),
    }


def _require_fallback_core_four_config(
    path: Path, *, spec: SeparationProfileSpec
) -> Mapping[str, Any]:
    artifact = spec.artifact("config")
    identity = _require_artifact_identity(
        path,
        expected_bytes=artifact.bytes,
        expected_sha256=artifact.sha256,
    )
    if path.read_text(encoding="utf-8") != "models: ['955717e8']\n":
        raise ValueError("fallback core-four local repository binding differs")
    return {
        **identity,
        "status": "verified",
        "model": "htdemucs",
        "signature": "955717e8",
        "local_repository": True,
    }


def _require_scnet_core_four_config(
    path: Path, *, spec: SeparationProfileSpec
) -> Mapping[str, Any]:
    artifact = spec.artifact("config")
    identity = _require_artifact_identity(
        path,
        expected_bytes=artifact.bytes,
        expected_sha256=artifact.sha256,
    )
    return {
        **identity,
        "status": "verified",
        "model": "SCNet-large",
        "sources": ["drums", "bass", "other", "vocals"],
        "channels": 2,
        "sample_rate": 44_100,
        "compatibility_receipt_required": True,
    }


def _require_scnet_compatibility_receipt(
    path: Path, *, spec: SeparationProfileSpec
) -> Mapping[str, Any]:
    identity = _require_artifact_identity(
        path,
        expected_bytes=path.stat().st_size,
        expected_sha256=file_sha256(path),
    )
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("SCNet compatibility receipt is invalid") from exc
    compatibility = receipt.get("compatibility")
    effects = receipt.get("effects")
    artifacts = receipt.get("artifacts")
    expected_artifacts = {
        item.relative_path: {"bytes": item.bytes, "sha256": item.sha256}
        for item in spec.artifacts
    }
    if (
        receipt.get("schema") != "sunofriend.scnet-compatibility.v1"
        or receipt.get("status") != "passed"
        or receipt.get("profile_id") != spec.profile_id
        or receipt.get("source_revision") != spec.runtime_source_revision
        or receipt.get("runtime_packages") != dict(spec.packages())
        or artifacts != expected_artifacts
        or not isinstance(compatibility, Mapping)
        or compatibility.get("roles") != ["drums", "bass", "other", "vocals"]
        or compatibility.get("channels") != 2
        or compatibility.get("sample_rate") != 44_100
        or compatibility.get("strict_state_dict") is not True
        or compatibility.get("remediation_cycles") != 1
        or not isinstance(effects, Mapping)
        or effects.get("network_denied_by_parent_sandbox") is not True
        or effects.get("forward_passes") != 0
        or effects.get("audio_reads") != []
    ):
        raise ValueError("SCNet compatibility receipt contract differs")
    return {**identity, "status": "verified", "strict_state_dict": True}


def _require_core_four_config(
    path: Path, *, spec: SeparationProfileSpec
) -> Mapping[str, Any]:
    artifact = spec.artifact("config")
    identity = _require_artifact_identity(
        path,
        expected_bytes=artifact.bytes,
        expected_sha256=artifact.sha256,
    )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("core-four model config is invalid JSON") from exc
    kwargs = document.get("kwargs")
    if (
        document.get("model_class") != "BagOfModelsMLX"
        or document.get("num_models") != 1
        or document.get("sub_model_class") != "HTDemucsMLX"
        or not isinstance(kwargs, Mapping)
        or kwargs.get("sources") != ["drums", "bass", "other", "vocals"]
        or kwargs.get("audio_channels") != 2
        or kwargs.get("samplerate") != 44_100
        or kwargs.get("segment") != "39/5"
    ):
        raise ValueError("core-four model config role or clock contract differs")
    return {
        **identity,
        "status": "verified",
        "model_class": document["model_class"],
        "sources": list(kwargs["sources"]),
        "channels": kwargs["audio_channels"],
        "sample_rate": kwargs["samplerate"],
    }


def _require_artifact_identity(
    path: Path, *, expected_bytes: int, expected_sha256: str
) -> Mapping[str, Any]:
    attached = path.lstat()
    if path.is_symlink() or not path.is_file() or attached.st_nlink != 1:
        raise ValueError(f"profile artifact must be a single-link regular file: {path}")
    if attached.st_size != expected_bytes or file_sha256(path) != expected_sha256:
        raise ValueError(f"profile artifact identity differs: {path}")
    return {
        "status": "verified",
        "path": str(path),
        "bytes": attached.st_size,
        "sha256": expected_sha256,
    }


def _require_installation_receipt(
    path: Path, *, spec: SeparationProfileSpec
) -> Mapping[str, Any]:
    identity = _require_artifact_identity(
        path,
        expected_bytes=path.stat().st_size,
        expected_sha256=file_sha256(path),
    )
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("core-four installation receipt is invalid") from exc
    common_matches = (
        receipt.get("schema") == "sunofriend.separation-installation.v1"
        and receipt.get("profile_id") == spec.profile_id
        and receipt.get("model_terms_accepted") is True
        and receipt.get("model_revision") == spec.model_revision
        and receipt.get("runtime_source_revision") == spec.runtime_source_revision
    )
    if spec.profile_id == SCNET_RELEASE_PROFILE_ID:
        profile_matches = (
            receipt.get("checkpoint_use_accepted") is True
            and receipt.get("upstream_model_resolution_enabled") is False
            and receipt.get("compatibility_network_denied") is True
            and receipt.get("compatibility_remediation_cycles") == 1
            and receipt.get("inference_performed") is False
            and receipt.get("audio_processed") is False
        )
    else:
        profile_matches = (
            receipt.get("runtime_wheel_sha256") == spec.runtime_wheel_sha256
            and receipt.get("runtime_packages") == dict(spec.packages())
            and receipt.get("upstream_first_run_conversion_enabled") is False
            and receipt.get("inference_network_resolution_enabled") is False
        )
    if not common_matches or not profile_matches:
        raise ValueError("core-four installation receipt contract differs")
    return {**identity, "status": "verified", "terms_accepted": True}


def _system_memory_bytes() -> int | None:
    try:
        completed = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "hw.memsize"],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        value = int(completed.stdout.strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    return value if completed.returncode == 0 and value > 0 else None


def _validate_core_four_worker_evidence(
    worker: Mapping[str, Any], *, plan: SeparationPlan
) -> None:
    spec = separation_profile(plan.profile.profile_id)
    expected_settings = dict(spec.inference_settings)
    expected_runtime_device = expected_settings.get("device", "mlx-gpu")
    expected_pytorch = spec.backend in {
        "demucs-infer",
        "scnet-official-release-adapter",
    }
    runtime = worker.get("runtime")
    model = worker.get("model")
    accounting = worker.get("additive_accounting")
    correction = worker.get("native_other_correction")
    resources = worker.get("resources")
    outputs = worker.get("outputs")
    frames = worker.get("frames")
    duration = worker.get("duration_seconds")
    expected_outputs = {
        *spec.supported_roles,
        "source_reference",
        "reconstruction_check",
    }
    runtime_identity_matches = (
        model.get("source_revision") == spec.runtime_source_revision
        if spec.profile_id == SCNET_RELEASE_PROFILE_ID and isinstance(model, Mapping)
        else (
            isinstance(runtime, Mapping)
            and runtime.get("source_revision") == spec.runtime_source_revision
            and runtime.get("wheel_sha256") == spec.runtime_wheel_sha256
        )
    )
    if (
        worker.get("schema") != "sunofriend.experimental-core-four-worker.v1"
        or worker.get("profile_id") != spec.profile_id
        or worker.get("roles") != list(spec.supported_roles)
        or worker.get("sample_rate") != 44_100
        or worker.get("channels") != 2
        or not isinstance(frames, int)
        or isinstance(frames, bool)
        or frames <= 0
        or type(duration) not in (int, float)
        or not math.isclose(float(duration), frames / 44_100, abs_tol=1e-12)
        or worker.get("inference") != expected_settings
        or not isinstance(runtime, Mapping)
        or runtime.get("backend") != spec.backend
        or not runtime_identity_matches
        or runtime.get("packages") != dict(spec.packages())
        or runtime.get("system") != "Darwin"
        or str(runtime.get("machine", "")).casefold() != "arm64"
        or runtime.get("device") != expected_runtime_device
        or runtime.get("pytorch_present") is not expected_pytorch
        or runtime.get("network_denial_enforced") is not True
        or runtime.get("network_used") is not False
        or not isinstance(model, Mapping)
        or model.get("model_id") != spec.model_id
        or model.get("weights_sha256") != spec.artifact("weights").sha256
        or model.get("config_sha256") != spec.artifact("config").sha256
        or model.get("model_revision") != spec.model_revision
        or model.get("source_order") != ["drums", "bass", "other", "vocals"]
        or model.get("named_or_network_model_resolution") is not False
        or worker.get("source_unchanged") is not True
        or worker.get("model_artifacts_unchanged") is not True
        or not isinstance(outputs, Mapping)
        or set(outputs) != expected_outputs
        or not isinstance(accounting, Mapping)
        or accounting.get("passed") is not True
        or accounting.get("maximum_absolute_error_lsb", 3) > 2
        or not isinstance(correction, Mapping)
        or correction.get("used_for_separation_accuracy_claim") is not False
        or not isinstance(resources, Mapping)
    ):
        raise RuntimeError("core-four worker objective evidence contract differs")
    if spec.profile_id == CORE_FOUR_PROFILE_ID:
        model_contract_matches = (
            model.get("segment_config_value") == "39/5"
            and model.get("auto_convert") is False
        )
    elif spec.profile_id == SCNET_RELEASE_PROFILE_ID:
        model_contract_matches = (
            model.get("checkpoint_local_only") is True
            and model.get("checkpoint_weights_only") is True
            and model.get("checkpoint_mmap") is True
            and model.get("strict_state_dict") is True
            and model.get("compatibility_remediation_cycles") == 1
        )
    else:
        model_contract_matches = (
            model.get("segment_verified_numeric") is True
            and model.get("explicit_local_repo") is True
        )
    if not model_contract_matches:
        raise RuntimeError("core-four worker model loading contract differs")
    for role in expected_outputs:
        output = outputs[role]
        if (
            not isinstance(output, Mapping)
            or output.get("frames") != frames
            or output.get("channels") != 2
            or output.get("sample_rate") != 44_100
            or output.get("sample_width_bytes") != 3
        ):
            raise RuntimeError("core-four persisted output clock contract differs")
    for key in ("rms", "peak"):
        value = correction.get(key)
        if type(value) not in (int, float) or not math.isfinite(float(value)):
            raise RuntimeError("core-four native-other correction metric is invalid")
    peak_memory = resources.get("peak_unified_memory_bytes")
    if not isinstance(peak_memory, int) or not 0 <= peak_memory <= 12 * 1024**3:
        raise RuntimeError("core-four worker exceeded the 12 GiB memory ceiling")
    duration = plan.probe.duration_seconds
    elapsed = worker.get("elapsed_seconds")
    limit = min(900.0, duration * 2.0)
    if (
        type(elapsed) not in (int, float)
        or not math.isfinite(float(elapsed))
        or float(elapsed) > limit
    ):
        raise RuntimeError("core-four worker exceeded the runtime ceiling")


def _runtime_check(
    path: Path,
    *,
    expected_packages: Mapping[str, str] | None = None,
    expected_pytorch: bool = False,
) -> dict[str, Any]:
    if not path.is_file() or not os.access(path, os.X_OK):
        return {"ready": False, "reason": "runtime Python is missing"}
    try:
        package_probe = ""
        if expected_packages:
            names = json.dumps(sorted(expected_packages))
            package_probe = (
                "; import importlib.metadata as m, importlib.util as u, json; "
                f"print(json.dumps({{n:m.version(n) for n in {names}}},sort_keys=True)); "
                "print('torch_present=' + str(u.find_spec('torch') is not None))"
            )
        completed = subprocess.run(
            [
                str(path),
                "-c",
                "import sys; print('.'.join(map(str,sys.version_info[:3])))"
                + package_probe,
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            env={**os.environ, "PYTHONNOUSERSITE": "1"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ready": False, "reason": type(exc).__name__}
    lines = completed.stdout.splitlines()
    version = lines[0].strip() if lines else ""
    ready = completed.returncode == 0 and version.startswith(("3.12.", "3.13."))
    packages: dict[str, str] = {}
    if expected_packages and len(lines) >= 2:
        try:
            packages = json.loads(lines[1])
        except json.JSONDecodeError:
            ready = False
        if packages != dict(expected_packages):
            ready = False
    torch_present = None
    if expected_packages:
        torch_present = len(lines) >= 3 and lines[2].strip() == "torch_present=True"
        if torch_present is not expected_pytorch:
            ready = False
    return {
        "ready": ready,
        "version": version,
        "returncode": completed.returncode,
        "packages": packages,
        "expected_packages": dict(expected_packages or {}),
        "pytorch_present": torch_present,
    }


def _require_verified_checkpoint(path: Path) -> Mapping[str, Any]:
    value = _inspect_local_checkpoint(path)
    if not value["cryptographic_identity_verified"]:
        raise ValueError("checkpoint identity differs")
    return value


def _require_verified_companions(path: Path) -> Mapping[str, Any]:
    value = _inspect_companion_files(path)
    if not value["all_cryptographic_identities_verified"]:
        raise ValueError("companion identities differ")
    return value


def _safe_check(operation: Callable[[], Mapping[str, Any]]) -> dict[str, Any]:
    try:
        value = operation()
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        return {"ready": False, "reason": str(exc)}
    return {"ready": True, "verified": True, **dict(value)}


def _run_command(
    command: Sequence[str],
    *,
    timeout: float,
    label: str,
    env: Mapping[str, str] | None = None,
) -> None:
    completed = subprocess.run(
        list(command),
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        env=dict(env) if env is not None else None,
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(
            f"{label} failed with exit code {completed.returncode}: "
            f"{detail[:2000] or 'no diagnostic output'}"
        )


def _nearest_existing_parent(path: Path) -> Path:
    current = path
    while not current.exists():
        if current.parent == current:
            raise FileNotFoundError(f"no existing parent for {path}")
        current = current.parent
    return current


def _document_sha256(document: Mapping[str, Any]) -> str:
    value = dict(document)
    value.pop("document_sha256", None)
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sunofriend-separate",
        description="Experimental local finished-mix separation.",
    )
    parser.add_argument("--runtime-python")
    parser.add_argument("--model-root")
    subparsers = parser.add_subparsers(dest="command", required=True)
    profiles = subparsers.add_parser(
        "profiles", help="show immutable profiles and separation scopes"
    )
    profiles.add_argument("--json", action="store_true")
    doctor = subparsers.add_parser("doctor", help="check setup without loading a model")
    doctor.add_argument("--json", action="store_true")
    doctor.add_argument(
        "--scope",
        choices=tuple(item["id"] for item in separation_capabilities()["scopes"]),
        default=DEFAULT_SCOPE_ID,
    )
    separate = subparsers.add_parser("separate", help="plan or run local separation")
    separate.add_argument("source")
    separate.add_argument("--out", required=True)
    separate.add_argument(
        "--scope",
        choices=tuple(item["id"] for item in separation_capabilities()["scopes"]),
        default=DEFAULT_SCOPE_ID,
    )
    separate.add_argument(
        "--rights-category",
        required=True,
        choices=sorted(RIGHTS_CATEGORIES - {"unknown", "declined_to_state"}),
    )
    separate.add_argument("--device", choices=("gpu", "cpu"))
    separate.add_argument("--ffmpeg", default="ffmpeg")
    separate.add_argument("--ffprobe", default="ffprobe")
    separate.add_argument("--execute", action="store_true")
    separate.add_argument("--confirm-rights", action="store_true")
    separate.add_argument("--open-review", action="store_true")
    refine = subparsers.add_parser(
        "refine-other",
        help="plan or run the installed Studio guitar/keys challenger",
    )
    refine.add_argument("parent_root")
    refine.add_argument("--target", choices=("guitar", "keys"), required=True)
    refine.add_argument("--out", required=True)
    refine.add_argument("--execute", action="store_true")
    refine.add_argument("--confirm-rights", action="store_true")
    refine.add_argument("--open-review", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "profiles":
        result = separation_capabilities()
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Sunofriend separation scopes and profiles")
            for scope in result["scopes"]:
                roles = ", ".join(role["id"] for role in scope["roles"])
                print(f"- {scope['id']}: {scope['status']} ({roles})")
                for blocker in scope["blockers"]:
                    print(f"  blocker: {blocker}")
            print("Profiles")
            for item in result["profile_registry"]["profiles"]:
                print(
                    f"- {item['profile_id']}: {item['status']} -> "
                    f"{item['target_release_tier']}"
                )
            refinement = result["refinement_registry"]
            targets = ", ".join(
                item["target_id"] for item in refinement["supported_targets"]
            )
            print("Studio-only refinement contract")
            print(
                f"- {refinement['scope_id']}: {refinement['status']} "
                f"({targets}; executable: {'yes' if refinement['executable'] else 'no'})"
            )
            for blocker in refinement["blockers"]:
                print(f"  blocker: {blocker}")
        return 0
    if args.command == "refine-other":
        try:
            plan = plan_installed_other_refinement(
                args.parent_root,
                target_id=args.target,
                output=args.out,
            )
            if not args.execute:
                print(json.dumps(plan, indent=2, sort_keys=True))
                print(
                    "\nPlan only. Repeat with --execute --confirm-rights to run "
                    "the installed model offline."
                )
                return 0
            print(
                "Running the installed Studio challenger offline. This creates one "
                "requested target and an exact residual; it activates neither."
            )
            result = execute_installed_other_refinement(
                plan,
                confirm_rights=args.confirm_rights,
                model_root=args.model_root,
                runtime_python=args.runtime_python,
            )
        except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
            print(f"sunofriend-separate: {exc}", file=sys.stderr)
            return 2
        print(f"Complete: {result['root']}")
        print(f"Listen first: {result['review_html']}")
        print("No source or MIDI was selected; no audio was uploaded.")
        if args.open_review:
            webbrowser.open(Path(result["review_html"]).as_uri())
        return 0
    selected_scope = args.scope if hasattr(args, "scope") else DEFAULT_SCOPE_ID
    profile = resolve_profile(
        runtime_python=args.runtime_python,
        model_root=args.model_root,
        profile_id=profile_for_scope(selected_scope).profile_id,
    )
    if args.command == "doctor":
        result = separation_doctor(profile)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Experimental separation: {result['status']}")
            for name, check in result["checks"].items():
                state = "ready" if check.get("ready") else "needs attention"
                print(f"- {name}: {state}")
            if not result["ready"]:
                print(f"Next: {result['setup_command']}")
        return 0 if result["ready"] else 2
    try:
        plan = plan_separation(
            args.source,
            args.out,
            rights_category=args.rights_category,
            scope_id=args.scope,
            device=args.device,
            ffmpeg=args.ffmpeg,
            ffprobe=args.ffprobe,
            profile=profile,
        )
        if not args.execute:
            print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
            print(
                "\nPlan only. Repeat with --execute --confirm-rights to process locally."
            )
            return 0
        print(
            "Running the local experimental separator. The model is loaded offline; "
            "a full song can take several minutes."
        )
        result = execute_separation(plan, confirm_rights=args.confirm_rights)
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        print(f"sunofriend-separate: {exc}", file=sys.stderr)
        return 2
    print(f"Complete: {result['root']}")
    print(f"Listen first: {result['review_html']}")
    print("Result is experimental and unreviewed; no audio was uploaded.")
    if args.open_review:
        webbrowser.open(Path(result["review_html"]).as_uri())
    return 0


__all__ = [
    "PLAN_SCHEMA",
    "PROFILE_NAME",
    "SCHEMA",
    "SeparationPlan",
    "SeparationProfile",
    "build_parser",
    "execute_separation",
    "main",
    "plan_separation",
    "resolve_profile",
    "separation_doctor",
]


if __name__ == "__main__":
    raise SystemExit(main())
