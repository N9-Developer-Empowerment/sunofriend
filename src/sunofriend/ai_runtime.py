"""Licence-aware boundary for optional AI transcription workers.

The main Sunofriend environment deliberately does not import PyTorch. Heavy or
licence-restricted models run in a separate Python 3.12 process and exchange
versioned JSON with the deterministic core. Phase 1 initially exposes runtime
diagnostics and the candidate schema; individual model adapters can then be
added and evaluated without making them required dependencies.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol


AI_RUNTIME_SCHEMA = "sunofriend.ai-runtime.v1"
AI_REQUEST_SCHEMA = "sunofriend.ai-transcription-request.v1"
AI_CANDIDATE_SCHEMA = "sunofriend.ai-transcription-candidate.v1"
AI_REQUIREMENTS = ("runtime", "torch", "muscriptor", "game", "rmvpe", "all")


@dataclass(frozen=True)
class AIModelManifest:
    """Static distribution and licensing facts for one optional backend."""

    backend: str
    name: str
    tasks: tuple[str, ...]
    code_license: str
    weights_license: str
    package: str | None
    homepage: str
    distribution_policy: str


AI_MODEL_MANIFESTS: dict[str, AIModelManifest] = {
    "muscriptor": AIModelManifest(
        backend="muscriptor",
        name="MuScriptor",
        tasks=("multi-instrument", "full-mix", "stem"),
        code_license="MIT",
        weights_license="CC-BY-NC-4.0",
        package="muscriptor",
        homepage="https://github.com/muscriptor/muscriptor",
        distribution_policy=(
            "Install code in the optional worker; never bundle gated, "
            "non-commercial checkpoints with Sunofriend."
        ),
    ),
    "game": AIModelManifest(
        backend="game",
        name="GAME",
        tasks=("lead-vocal", "backing-vocal", "note-boundaries"),
        code_license="MIT",
        weights_license="checkpoint-specific; verify before use",
        package=None,
        homepage="https://github.com/openvpi/GAME",
        distribution_policy=(
            "Use an external checkout and explicitly recorded checkpoint; "
            "do not vendor either into the Apache-2.0 core."
        ),
    ),
    "rmvpe": AIModelManifest(
        backend="rmvpe",
        name="RMVPE",
        tasks=("vocal-f0", "polyphonic-bleed"),
        code_license="Apache-2.0",
        weights_license="checkpoint-specific; verify before use",
        package=None,
        homepage="https://github.com/Dream-High/RMVPE",
        distribution_policy=(
            "Use an external checkout until checkpoint provenance and "
            "redistribution terms have been recorded."
        ),
    ),
}


@dataclass(frozen=True)
class AITranscriptionRequest:
    """Model-neutral request passed to an isolated transcription backend."""

    audio_path: str
    backend: str
    roles: tuple[str, ...] = ()
    start_seconds: float = 0.0
    end_seconds: float | None = None
    options: Mapping[str, Any] = field(default_factory=dict)

    def validate(self, *, require_audio: bool = True) -> None:
        path = Path(self.audio_path)
        if not path.is_absolute():
            raise ValueError("AI transcription audio_path must be absolute")
        if require_audio and not path.is_file():
            raise ValueError(f"AI transcription audio does not exist: {path}")
        if self.backend not in AI_MODEL_MANIFESTS:
            raise ValueError(
                "backend must be one of: " + ", ".join(sorted(AI_MODEL_MANIFESTS))
            )
        if self.start_seconds < 0:
            raise ValueError("start_seconds must not be negative")
        if self.end_seconds is not None and self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be later than start_seconds")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": AI_REQUEST_SCHEMA,
            "audio_path": self.audio_path,
            "backend": self.backend,
            "roles": list(self.roles),
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "options": dict(self.options),
        }


@dataclass(frozen=True)
class AITranscriptionNote:
    """One raw model event before Sunofriend repairs or musical decoding."""

    start_seconds: float
    end_seconds: float
    pitch: float
    confidence: float | None = None
    instrument: str | None = None
    velocity: int | None = None
    source_event_id: str | None = None

    def validate(self) -> None:
        if self.start_seconds < 0 or self.end_seconds <= self.start_seconds:
            raise ValueError(
                "AI note must have a positive duration and non-negative start"
            )
        if not 0 <= self.pitch <= 127:
            raise ValueError("AI note pitch must be in the MIDI range 0..127")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("AI note confidence must be between 0 and 1")
        if self.velocity is not None and not 1 <= self.velocity <= 127:
            raise ValueError("AI note velocity must be between 1 and 127")


@dataclass(frozen=True)
class AITranscriptionCandidate:
    """Auditable raw result returned by one independent model backend."""

    backend: str
    model_version: str
    notes: tuple[AITranscriptionNote, ...]
    warnings: tuple[str, ...] = ()
    raw_artifacts: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.backend not in AI_MODEL_MANIFESTS:
            raise ValueError(f"unknown AI backend: {self.backend}")
        if not self.model_version.strip():
            raise ValueError("model_version is required")
        for note in self.notes:
            note.validate()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema": AI_CANDIDATE_SCHEMA,
            "backend": self.backend,
            "model_version": self.model_version,
            "notes": [asdict(note) for note in self.notes],
            "warnings": list(self.warnings),
            "raw_artifacts": list(self.raw_artifacts),
            "metadata": dict(self.metadata),
            "manifest": asdict(AI_MODEL_MANIFESTS[self.backend]),
        }


class AITranscriptionBackend(Protocol):
    """Contract implemented inside an optional model worker."""

    manifest: AIModelManifest

    def transcribe(
        self, request: AITranscriptionRequest
    ) -> AITranscriptionCandidate: ...


def _project_ai_python() -> Path:
    return Path(__file__).resolve().parents[2] / ".venv-ai" / "bin" / "python"


def resolve_ai_python(value: str | Path | None = None) -> Path:
    """Resolve the isolated worker interpreter without changing the core venv."""

    configured = value or os.environ.get("SUNOFRIEND_AI_PYTHON")
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            # Keep a virtual-environment launcher path intact. Resolving its
            # symlink would execute the base interpreter without the venv.
            return candidate.absolute()
        raise FileNotFoundError(
            f"AI Python was not found at {candidate}; run scripts/setup-ai-runtime.sh"
        )
    candidates = (
        Path.cwd() / ".venv-ai" / "bin" / "python",
        _project_ai_python(),
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.absolute()
    fallback = shutil.which("python3.12")
    if fallback:
        return Path(fallback).absolute()
    requested = candidates[0]
    raise FileNotFoundError(
        f"AI Python was not found at {requested}; run scripts/setup-ai-runtime.sh"
    )


_RUNTIME_PROBE = r"""
import importlib.metadata
import json
import platform
import sys

packages = {}
for distribution in ("torch", "muscriptor"):
    try:
        packages[distribution] = importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        packages[distribution] = None

torch_report = {
    "installed": packages["torch"] is not None,
    "importable": False,
    "version": packages["torch"],
    "mps_built": False,
    "mps_available": False,
    "error": None,
}
if torch_report["installed"]:
    try:
        import torch
        torch_report.update({
            "importable": True,
            "version": torch.__version__,
            "mps_built": torch.backends.mps.is_built(),
            "mps_available": torch.backends.mps.is_available(),
        })
    except Exception as exc:
        torch_report["error"] = f"{type(exc).__name__}: {exc}"

print(json.dumps({
    "python": sys.version.split()[0],
    "python_info": list(sys.version_info[:3]),
    "executable": sys.executable,
    "platform": platform.platform(),
    "packages": packages,
    "torch": torch_report,
}))
"""


def _external_backend_report(
    name: str, *, home_env: str, model_env: str
) -> dict[str, Any]:
    home_value = os.environ.get(home_env)
    model_value = os.environ.get(model_env)
    home = Path(home_value).expanduser() if home_value else None
    model = Path(model_value).expanduser() if model_value else None
    return {
        "software_ready": bool(home and home.is_dir()),
        "checkpoint_ready": bool(model and model.is_file()),
        "home": str(home.resolve()) if home and home.exists() else home_value,
        "checkpoint": str(model.resolve()) if model and model.exists() else model_value,
        "configuration": {"home_env": home_env, "model_env": model_env},
        "manifest": asdict(AI_MODEL_MANIFESTS[name]),
    }


def collect_ai_diagnostics(
    python: str | Path | None = None,
) -> dict[str, Any]:
    """Probe the isolated worker and optional model installations as JSON."""

    try:
        executable = resolve_ai_python(python)
    except FileNotFoundError as exc:
        return {
            "schema": AI_RUNTIME_SCHEMA,
            "runtime_ready": False,
            "runtime_error": str(exc),
            "backends": {
                name: {"software_ready": False, "manifest": asdict(manifest)}
                for name, manifest in AI_MODEL_MANIFESTS.items()
            },
        }

    try:
        completed = subprocess.run(
            [str(executable), "-c", _RUNTIME_PROBE],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        worker = json.loads(completed.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return {
            "schema": AI_RUNTIME_SCHEMA,
            "python_executable": str(executable),
            "runtime_ready": False,
            "runtime_error": f"{type(exc).__name__}: {exc}",
            "backends": {
                name: {"software_ready": False, "manifest": asdict(manifest)}
                for name, manifest in AI_MODEL_MANIFESTS.items()
            },
        }

    version_info = tuple(worker.get("python_info", (0, 0, 0)))
    torch_report = worker.get("torch", {})
    backends = {
        "muscriptor": {
            "software_ready": bool(worker["packages"].get("muscriptor"))
            and bool(torch_report.get("importable")),
            "checkpoint_ready": False,
            "checkpoint_note": (
                "Weights are gated and downloaded only after the user accepts "
                "the CC-BY-NC-4.0 terms; no checkpoint was probed."
            ),
            "version": worker["packages"].get("muscriptor"),
            "manifest": asdict(AI_MODEL_MANIFESTS["muscriptor"]),
        },
        "game": _external_backend_report(
            "game", home_env="SUNOFRIEND_GAME_HOME", model_env="SUNOFRIEND_GAME_MODEL"
        ),
        "rmvpe": _external_backend_report(
            "rmvpe",
            home_env="SUNOFRIEND_RMVPE_HOME",
            model_env="SUNOFRIEND_RMVPE_MODEL",
        ),
    }
    return {
        "schema": AI_RUNTIME_SCHEMA,
        "python_executable": str(executable),
        "python": worker.get("python"),
        "platform": worker.get("platform"),
        "runtime_ready": version_info >= (3, 12),
        "packages": worker.get("packages", {}),
        "torch": torch_report,
        "torch_ready": bool(torch_report.get("importable")),
        "preferred_device": "mps" if torch_report.get("mps_available") else "cpu",
        "backends": backends,
    }


def ai_requirement_ready(report: Mapping[str, Any], requirement: str) -> bool:
    """Evaluate one `ai-doctor --require` capability."""

    if requirement not in AI_REQUIREMENTS:
        raise ValueError("requirement must be one of: " + ", ".join(AI_REQUIREMENTS))
    if requirement == "runtime":
        return bool(report.get("runtime_ready"))
    if requirement == "torch":
        return bool(report.get("runtime_ready") and report.get("torch_ready"))
    backends = report.get("backends", {})
    if requirement == "all":
        return bool(report.get("runtime_ready") and report.get("torch_ready")) and all(
            bool(backends.get(name, {}).get("software_ready"))
            for name in AI_MODEL_MANIFESTS
        )
    return bool(report.get("runtime_ready")) and bool(
        backends.get(requirement, {}).get("software_ready")
    )


__all__ = [
    "AI_CANDIDATE_SCHEMA",
    "AI_MODEL_MANIFESTS",
    "AI_REQUEST_SCHEMA",
    "AI_REQUIREMENTS",
    "AI_RUNTIME_SCHEMA",
    "AIModelManifest",
    "AITranscriptionBackend",
    "AITranscriptionCandidate",
    "AITranscriptionNote",
    "AITranscriptionRequest",
    "ai_requirement_ready",
    "collect_ai_diagnostics",
    "resolve_ai_python",
]
