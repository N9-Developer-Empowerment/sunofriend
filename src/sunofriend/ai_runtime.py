"""Licence-aware boundary for optional AI transcription and cleanup workers.

The main Sunofriend environment deliberately does not import PyTorch. Heavy or
licence-restricted models run in a separate Python 3.12 process and exchange
versioned JSON with the deterministic core. Transcription and cleanup adapters
remain optional and can be evaluated without becoming core dependencies.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol


AI_RUNTIME_SCHEMA = "sunofriend.ai-runtime.v1"
AI_REQUEST_SCHEMA = "sunofriend.ai-transcription-request.v1"
AI_CANDIDATE_SCHEMA = "sunofriend.ai-transcription-candidate.v1"
AI_REQUIREMENTS = (
    "runtime",
    "torch",
    "muscriptor",
    "muscriptor-checkpoint",
    "game",
    "rmvpe",
    "pesto",
    "demucs",
    "all",
)
GAME_MODEL_FILENAMES = (
    "config.json",
    "encoder.onnx",
    "segmenter.onnx",
    "estimator.onnx",
    "dur2bd.onnx",
    "bd2dur.onnx",
)
RMVPE_MODEL_SHA256 = "5370e71ac80af8b4b7c793d27efd51fd8bf962de3a7ede0766dac0befa3660fd"
PESTO_MODEL_SHA256 = "16c32e06ddd950e3e4866dfa3c7f8a87c4988f8adf43e57977b189f031f26f3e"
DEMUCS_HTDEMUCS_SHA256 = (
    "8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4"
)


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
        weights_license=(
            "Official v1.0.3 release asset; repository MIT; no separate "
            "checkpoint terms stated"
        ),
        package="onnxruntime",
        homepage="https://github.com/openvpi/GAME",
        distribution_policy=(
            "Use the pinned official release asset from an external model "
            "directory; record every component hash and do not vendor weights."
        ),
    ),
    "rmvpe": AIModelManifest(
        backend="rmvpe",
        name="RMVPE",
        tasks=("vocal-f0", "polyphonic-bleed"),
        code_license=("MIT (rmvpe-onnx adapter); Apache-2.0 (authors' reference code)"),
        weights_license=(
            "MIT-labelled lj1995/VoiceConversionWebUI rmvpe.onnx at "
            "b2c8cae96e3b05de46d36c5ef9970ef6cbccafba"
        ),
        package="rmvpe-onnx",
        homepage="https://github.com/NewComer00/rmvpe-onnx",
        distribution_policy=(
            "Keep the pinned ONNX checkpoint external, verify its canonical hash, "
            "and record its Hugging Face revision in every setup."
        ),
    ),
    "pesto": AIModelManifest(
        backend="pesto",
        name="PESTO",
        tasks=("vocal-f0", "instrument-f0", "realtime-pitch"),
        code_license="LGPL-3.0",
        weights_license=(
            "LGPL-3.0 repository checkpoint mir-1k_g7 at pinned commit "
            "62bc0c9702558f19af4593752947fb9db1eadac9"
        ),
        package="pesto-pitch",
        homepage="https://github.com/SonyCSLParis/pesto",
        distribution_policy=(
            "Keep PESTO optional in the isolated worker; download the pinned "
            "checkpoint explicitly, verify its hash and preserve frame evidence."
        ),
    ),
}


# Cleanup models have a different worker contract from transcription models.
# Keeping their manifests separate prevents an unsupported backend from being
# accepted by AITranscriptionRequest while still making it visible to
# `ai-doctor`.
AI_CLEANUP_MODEL_MANIFESTS: dict[str, AIModelManifest] = {
    "demucs": AIModelManifest(
        backend="demucs",
        name="Demucs htdemucs",
        tasks=("local-source-separation", "target-residual-cleanup"),
        code_license="MIT",
        weights_license=(
            "No separate pretrained-checkpoint licence identified in the "
            "official repository; private local evaluation only"
        ),
        package="demucs",
        homepage="https://github.com/facebookresearch/demucs",
        distribution_policy=(
            "Keep the exact official checkpoint external, hash-verify before "
            "deserialisation, never vendor or redistribute it, and do not "
            "promote its output without a listening review."
        ),
    ),
}


def _all_model_manifests() -> dict[str, AIModelManifest]:
    return {**AI_MODEL_MANIFESTS, **AI_CLEANUP_MODEL_MANIFESTS}


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
        if not math.isfinite(self.start_seconds):
            raise ValueError("start_seconds must be finite")
        if self.end_seconds is not None and not math.isfinite(self.end_seconds):
            raise ValueError("end_seconds must be finite")
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

    @classmethod
    def from_dict(
        cls, document: Mapping[str, Any], *, require_audio: bool = True
    ) -> AITranscriptionRequest:
        if document.get("schema") != AI_REQUEST_SCHEMA:
            raise ValueError(f"AI request schema must be {AI_REQUEST_SCHEMA}")
        roles = document.get("roles", ())
        options = document.get("options", {})
        if not isinstance(roles, list) or not all(
            isinstance(role, str) for role in roles
        ):
            raise ValueError("AI request roles must be a list of strings")
        if not isinstance(options, Mapping):
            raise ValueError("AI request options must be an object")
        request = cls(
            audio_path=str(document.get("audio_path", "")),
            backend=str(document.get("backend", "")),
            roles=tuple(roles),
            start_seconds=float(document.get("start_seconds", 0.0)),
            end_seconds=(
                None
                if document.get("end_seconds") is None
                else float(document["end_seconds"])
            ),
            options=dict(options),
        )
        request.validate(require_audio=require_audio)
        return request


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
        numeric = (self.start_seconds, self.end_seconds, self.pitch)
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError("AI note times and pitch must be finite")
        if self.confidence is not None and not math.isfinite(self.confidence):
            raise ValueError("AI note confidence must be finite")
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

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> AITranscriptionNote:
        note = cls(
            start_seconds=float(document["start_seconds"]),
            end_seconds=float(document["end_seconds"]),
            pitch=float(document["pitch"]),
            confidence=(
                None
                if document.get("confidence") is None
                else float(document["confidence"])
            ),
            instrument=(
                None
                if document.get("instrument") is None
                else str(document["instrument"])
            ),
            velocity=(
                None if document.get("velocity") is None else int(document["velocity"])
            ),
            source_event_id=(
                None
                if document.get("source_event_id") is None
                else str(document["source_event_id"])
            ),
        )
        note.validate()
        return note


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

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> AITranscriptionCandidate:
        if document.get("schema") != AI_CANDIDATE_SCHEMA:
            raise ValueError(f"AI candidate schema must be {AI_CANDIDATE_SCHEMA}")
        notes = document.get("notes", ())
        warnings = document.get("warnings", ())
        raw_artifacts = document.get("raw_artifacts", ())
        metadata = document.get("metadata", {})
        if not isinstance(notes, list) or not all(
            isinstance(note, Mapping) for note in notes
        ):
            raise ValueError("AI candidate notes must be a list of objects")
        if not isinstance(warnings, list) or not all(
            isinstance(warning, str) for warning in warnings
        ):
            raise ValueError("AI candidate warnings must be a list of strings")
        if not isinstance(raw_artifacts, list) or not all(
            isinstance(artifact, str) for artifact in raw_artifacts
        ):
            raise ValueError("AI candidate raw_artifacts must be a list of strings")
        if not isinstance(metadata, Mapping):
            raise ValueError("AI candidate metadata must be an object")
        candidate = cls(
            backend=str(document.get("backend", "")),
            model_version=str(document.get("model_version", "")),
            notes=tuple(AITranscriptionNote.from_dict(note) for note in notes),
            warnings=tuple(warnings),
            raw_artifacts=tuple(raw_artifacts),
            metadata=dict(metadata),
        )
        candidate.validate()
        return candidate


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


def _default_muscriptor_checkpoint() -> Path:
    return (
        Path.home()
        / ".local"
        / "share"
        / "sunofriend"
        / "models"
        / "muscriptor-small"
        / "model.safetensors"
    )


def resolve_muscriptor_checkpoint(value: str | Path | None = None) -> Path:
    """Resolve an already-downloaded MuScriptor checkpoint without networking."""

    configured = value or os.environ.get("SUNOFRIEND_MUSCRIPTOR_MODEL")
    candidate = (
        Path(configured).expanduser()
        if configured
        else _default_muscriptor_checkpoint()
    )
    if not candidate.is_file():
        source = "SUNOFRIEND_MUSCRIPTOR_MODEL" if configured else "default path"
        raise FileNotFoundError(
            f"MuScriptor checkpoint was not found via {source}: {candidate}"
        )
    if candidate.suffix.lower() != ".safetensors":
        raise ValueError("MuScriptor checkpoint must be a .safetensors file")
    return candidate.absolute()


def _default_game_home() -> Path:
    return Path.home() / ".local" / "share" / "sunofriend" / "checkouts" / "GAME-v1.0.3"


def _default_game_model() -> Path:
    return (
        Path.home()
        / ".local"
        / "share"
        / "sunofriend"
        / "models"
        / "game-1.0.3-small-onnx"
        / "GAME-1.0.3-small-onnx"
    )


def resolve_game_model(value: str | Path | None = None) -> Path:
    """Resolve an official local GAME ONNX bundle without networking."""

    configured = value or os.environ.get("SUNOFRIEND_GAME_MODEL")
    candidate = Path(configured).expanduser() if configured else _default_game_model()
    if not candidate.is_dir():
        source = "SUNOFRIEND_GAME_MODEL" if configured else "default path"
        raise FileNotFoundError(
            f"GAME model bundle was not found via {source}: {candidate}"
        )
    missing = [
        name for name in GAME_MODEL_FILENAMES if not (candidate / name).is_file()
    ]
    if missing:
        raise ValueError(
            "GAME model bundle is incomplete; missing: " + ", ".join(missing)
        )
    return candidate.absolute()


def _default_rmvpe_model() -> Path:
    return (
        Path.home()
        / ".local"
        / "share"
        / "sunofriend"
        / "models"
        / "rmvpe-onnx-0.2.3"
        / "rmvpe.onnx"
    )


def resolve_rmvpe_model(value: str | Path | None = None) -> Path:
    """Resolve the pinned local RMVPE ONNX checkpoint without networking."""

    configured = value or os.environ.get("SUNOFRIEND_RMVPE_MODEL")
    candidate = Path(configured).expanduser() if configured else _default_rmvpe_model()
    if not candidate.is_file():
        source = "SUNOFRIEND_RMVPE_MODEL" if configured else "default path"
        raise FileNotFoundError(
            f"RMVPE ONNX checkpoint was not found via {source}: {candidate}; "
            "run scripts/setup-rmvpe-model.sh"
        )
    if candidate.suffix.lower() != ".onnx":
        raise ValueError("RMVPE checkpoint must be an .onnx file")
    return candidate.absolute()


def _default_pesto_model() -> Path:
    return (
        Path.home()
        / ".local"
        / "share"
        / "sunofriend"
        / "models"
        / "pesto-pitch-2.0.1"
        / "mir-1k_g7.ckpt"
    )


def resolve_pesto_model(value: str | Path | None = None) -> Path:
    """Resolve the pinned local PESTO checkpoint without networking."""

    configured = value or os.environ.get("SUNOFRIEND_PESTO_MODEL")
    candidate = Path(configured).expanduser() if configured else _default_pesto_model()
    if not candidate.is_file():
        source = "SUNOFRIEND_PESTO_MODEL" if configured else "default path"
        raise FileNotFoundError(
            f"PESTO checkpoint was not found via {source}: {candidate}; "
            "run scripts/setup-pesto-model.sh"
        )
    if candidate.suffix.lower() != ".ckpt":
        raise ValueError("PESTO checkpoint must be a .ckpt file")
    return candidate.absolute()


def _default_demucs_model() -> Path:
    return (
        Path.home()
        / ".local"
        / "share"
        / "sunofriend"
        / "models"
        / "demucs-4.0.1-htdemucs"
        / "955717e8-8726e21a.th"
    )


def resolve_demucs_model(value: str | Path | None = None) -> Path:
    """Resolve the pinned official htdemucs checkpoint without networking."""

    configured = value or os.environ.get("SUNOFRIEND_DEMUCS_MODEL")
    candidate = Path(configured).expanduser() if configured else _default_demucs_model()
    if not candidate.is_file():
        source = "SUNOFRIEND_DEMUCS_MODEL" if configured else "default path"
        raise FileNotFoundError(
            f"Demucs htdemucs checkpoint was not found via {source}: {candidate}; "
            "run scripts/setup-demucs-model.sh after accepting its private-use notice"
        )
    if candidate.suffix.lower() != ".th":
        raise ValueError("Demucs checkpoint must be a .th file")
    return candidate.absolute()


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_game_bundle(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    for name in GAME_MODEL_FILENAMES:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        with (path / name).open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    return digest.hexdigest()


def collect_muscriptor_checkpoint() -> dict[str, Any]:
    """Report only local checkpoint/config evidence; never download weights."""

    try:
        checkpoint = resolve_muscriptor_checkpoint()
    except (FileNotFoundError, ValueError) as exc:
        return {
            "checkpoint_ready": False,
            "checkpoint_error": str(exc),
            "configuration": {
                "model_env": "SUNOFRIEND_MUSCRIPTOR_MODEL",
                "default_path": str(_default_muscriptor_checkpoint()),
            },
        }

    config = checkpoint.with_name("config.json")
    report: dict[str, Any] = {
        "checkpoint_ready": True,
        "checkpoint": str(checkpoint),
        "checkpoint_bytes": checkpoint.stat().st_size,
        "checkpoint_sha256": _sha256_file(checkpoint),
        "config_ready": config.is_file(),
        "config": str(config) if config.is_file() else None,
        "configuration": {
            "model_env": "SUNOFRIEND_MUSCRIPTOR_MODEL",
            "default_path": str(_default_muscriptor_checkpoint()),
        },
    }
    if config.is_file():
        report["config_sha256"] = _sha256_file(config)
        try:
            document = json.loads(config.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                raise ValueError("MuScriptor config must be a JSON object")
            model_type = document.get("model_type")
            variant = document.get("variant")
            if model_type != "muscriptor":
                raise ValueError("MuScriptor config model_type must be 'muscriptor'")
            if variant not in {"small", "medium", "large"}:
                raise ValueError(
                    "MuScriptor config variant must be small, medium or large"
                )
            report["variant"] = variant
            report["model_config"] = document
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            report["config_ready"] = False
            report["config_error"] = f"{type(exc).__name__}: {exc}"
    return report


def collect_game_model() -> dict[str, Any]:
    """Report the exact local GAME release bundle; never download it."""

    configured = os.environ.get("SUNOFRIEND_GAME_MODEL")
    try:
        model = resolve_game_model(configured)
    except (FileNotFoundError, ValueError) as exc:
        return {
            "checkpoint_ready": False,
            "checkpoint_error": str(exc),
            "configuration": {
                "model_env": "SUNOFRIEND_GAME_MODEL",
                "default_path": str(_default_game_model()),
            },
        }

    components = {
        name: {
            "bytes": (model / name).stat().st_size,
            "sha256": _sha256_file(model / name),
        }
        for name in GAME_MODEL_FILENAMES
    }
    report: dict[str, Any] = {
        "checkpoint_ready": True,
        "checkpoint": str(model),
        "checkpoint_bytes": sum(item["bytes"] for item in components.values()),
        "checkpoint_sha256": _sha256_game_bundle(model),
        "components": components,
        "config_ready": True,
        "configuration": {
            "model_env": "SUNOFRIEND_GAME_MODEL",
            "default_path": str(_default_game_model()),
        },
    }
    try:
        config = json.loads((model / "config.json").read_text(encoding="utf-8"))
        report["variant"] = "1.0.3-small-onnx"
        report["model_config"] = config
    except (OSError, json.JSONDecodeError) as exc:
        report["config_ready"] = False
        report["config_error"] = f"{type(exc).__name__}: {exc}"
    return report


def collect_rmvpe_model() -> dict[str, Any]:
    """Report the exact local RMVPE checkpoint; never download it."""

    configured = os.environ.get("SUNOFRIEND_RMVPE_MODEL")
    try:
        model = resolve_rmvpe_model(configured)
    except (FileNotFoundError, ValueError) as exc:
        return {
            "checkpoint_ready": False,
            "checkpoint_error": str(exc),
            "configuration": {
                "model_env": "SUNOFRIEND_RMVPE_MODEL",
                "default_path": str(_default_rmvpe_model()),
            },
        }

    sha256 = _sha256_file(model)
    return {
        "checkpoint_ready": sha256 == RMVPE_MODEL_SHA256,
        "checkpoint": str(model),
        "checkpoint_bytes": model.stat().st_size,
        "checkpoint_sha256": sha256,
        "expected_checkpoint_sha256": RMVPE_MODEL_SHA256,
        "checkpoint_error": (
            None
            if sha256 == RMVPE_MODEL_SHA256
            else "RMVPE checkpoint hash does not match the pinned canonical model"
        ),
        "variant": "rmvpe-onnx-0.2.3/canonical-rmvpe.onnx",
        "configuration": {
            "model_env": "SUNOFRIEND_RMVPE_MODEL",
            "default_path": str(_default_rmvpe_model()),
        },
    }


def collect_pesto_model() -> dict[str, Any]:
    """Report the exact local PESTO checkpoint; never download it."""

    configured = os.environ.get("SUNOFRIEND_PESTO_MODEL")
    try:
        model = resolve_pesto_model(configured)
    except (FileNotFoundError, ValueError) as exc:
        return {
            "checkpoint_ready": False,
            "checkpoint_error": str(exc),
            "configuration": {
                "model_env": "SUNOFRIEND_PESTO_MODEL",
                "default_path": str(_default_pesto_model()),
            },
        }

    sha256 = _sha256_file(model)
    return {
        "checkpoint_ready": sha256 == PESTO_MODEL_SHA256,
        "checkpoint": str(model),
        "checkpoint_bytes": model.stat().st_size,
        "checkpoint_sha256": sha256,
        "expected_checkpoint_sha256": PESTO_MODEL_SHA256,
        "checkpoint_error": (
            None
            if sha256 == PESTO_MODEL_SHA256
            else "PESTO checkpoint hash does not match the pinned mir-1k_g7 model"
        ),
        "variant": "pesto-pitch-2.0.1/mir-1k_g7",
        "configuration": {
            "model_env": "SUNOFRIEND_PESTO_MODEL",
            "default_path": str(_default_pesto_model()),
        },
    }


def collect_demucs_model() -> dict[str, Any]:
    """Report the exact local htdemucs checkpoint; never download it."""

    configured = os.environ.get("SUNOFRIEND_DEMUCS_MODEL")
    try:
        model = resolve_demucs_model(configured)
    except (FileNotFoundError, ValueError) as exc:
        return {
            "checkpoint_ready": False,
            "checkpoint_error": str(exc),
            "configuration": {
                "model_env": "SUNOFRIEND_DEMUCS_MODEL",
                "default_path": str(_default_demucs_model()),
            },
        }

    sha256 = _sha256_file(model)
    return {
        "checkpoint_ready": sha256 == DEMUCS_HTDEMUCS_SHA256,
        "checkpoint": str(model),
        "checkpoint_bytes": model.stat().st_size,
        "checkpoint_sha256": sha256,
        "expected_checkpoint_sha256": DEMUCS_HTDEMUCS_SHA256,
        "checkpoint_error": (
            None
            if sha256 == DEMUCS_HTDEMUCS_SHA256
            else "Demucs checkpoint hash does not match the pinned official htdemucs model"
        ),
        "variant": "demucs-4.0.1/htdemucs/955717e8",
        "configuration": {
            "model_env": "SUNOFRIEND_DEMUCS_MODEL",
            "default_path": str(_default_demucs_model()),
        },
    }


_RUNTIME_PROBE = r"""
import importlib.metadata
import json
import platform
import sys

packages = {}
for distribution in (
    "torch",
    "muscriptor",
    "einops",
    "numpy",
    "soundfile",
    "safetensors",
    "onnxruntime",
    "rmvpe-onnx",
    "soxr",
    "pesto-pitch",
    "torchaudio",
    "demucs",
):
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
                for name, manifest in _all_model_manifests().items()
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
                for name, manifest in _all_model_manifests().items()
            },
        }

    version_info = tuple(worker.get("python_info", (0, 0, 0)))
    torch_report = worker.get("torch", {})
    muscriptor_checkpoint = collect_muscriptor_checkpoint()
    backends = {
        "muscriptor": {
            "software_ready": bool(worker["packages"].get("muscriptor"))
            and bool(torch_report.get("importable")),
            "version": worker["packages"].get("muscriptor"),
            "manifest": asdict(AI_MODEL_MANIFESTS["muscriptor"]),
            **muscriptor_checkpoint,
        },
        "game": {
            "software_ready": bool(worker["packages"].get("onnxruntime"))
            and bool(worker["packages"].get("soxr")),
            "version": worker["packages"].get("onnxruntime"),
            "resampler_version": worker["packages"].get("soxr"),
            "home": str(
                Path(os.environ.get("SUNOFRIEND_GAME_HOME", _default_game_home()))
                .expanduser()
                .absolute()
            ),
            "home_ready": Path(
                os.environ.get("SUNOFRIEND_GAME_HOME", _default_game_home())
            )
            .expanduser()
            .is_dir(),
            "manifest": asdict(AI_MODEL_MANIFESTS["game"]),
            **collect_game_model(),
        },
        "rmvpe": {
            "software_ready": bool(worker["packages"].get("rmvpe-onnx"))
            and bool(worker["packages"].get("onnxruntime")),
            "version": worker["packages"].get("rmvpe-onnx"),
            "onnxruntime_version": worker["packages"].get("onnxruntime"),
            "manifest": asdict(AI_MODEL_MANIFESTS["rmvpe"]),
            **collect_rmvpe_model(),
        },
        "pesto": {
            "software_ready": bool(worker["packages"].get("pesto-pitch"))
            and bool(worker["packages"].get("torchaudio"))
            and bool(torch_report.get("importable")),
            "version": worker["packages"].get("pesto-pitch"),
            "torchaudio_version": worker["packages"].get("torchaudio"),
            "manifest": asdict(AI_MODEL_MANIFESTS["pesto"]),
            **collect_pesto_model(),
        },
        "demucs": {
            "software_ready": bool(worker["packages"].get("demucs"))
            and bool(torch_report.get("importable")),
            "version": worker["packages"].get("demucs"),
            "manifest": asdict(AI_CLEANUP_MODEL_MANIFESTS["demucs"]),
            **collect_demucs_model(),
        },
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


def collect_ai_runtime_fingerprint(
    python: str | Path | None = None,
) -> dict[str, Any]:
    """Collect path-free cache identity without inventorying model files.

    The full doctor report hashes configured checkpoints and is appropriate for
    setup diagnostics.  Cache lookup has already hash-pinned the explicitly
    requested checkpoint, so repeating the global model inventory would add a
    large unrelated file read to every verified hit.
    """

    executable = resolve_ai_python(python)
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
        raise ValueError(
            f"AI runtime fingerprint failed: {type(exc).__name__}: {exc}"
        ) from exc
    packages = worker.get("packages")
    torch = worker.get("torch")
    if not isinstance(packages, Mapping) or not isinstance(torch, Mapping):
        raise ValueError("AI runtime fingerprint is incomplete")
    version_info = tuple(worker.get("python_info", (0, 0, 0)))
    return {
        "schema": AI_RUNTIME_SCHEMA,
        "python": worker.get("python"),
        "platform": worker.get("platform"),
        "runtime_ready": version_info >= (3, 12),
        "packages": dict(packages),
        "torch": dict(torch),
        "torch_ready": bool(torch.get("importable")),
        "preferred_device": "mps" if torch.get("mps_available") else "cpu",
        "backends": {
            "muscriptor": {
                "software_ready": bool(packages.get("muscriptor"))
                and bool(torch.get("importable")),
                "version": packages.get("muscriptor"),
                "manifest": asdict(AI_MODEL_MANIFESTS["muscriptor"]),
            }
        },
        "scope": "path-free-runtime-version-and-device-fingerprint",
        "checkpoint_inventory_performed": False,
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
    if requirement == "muscriptor-checkpoint":
        muscriptor = backends.get("muscriptor", {})
        return bool(
            report.get("runtime_ready")
            and muscriptor.get("software_ready")
            and muscriptor.get("checkpoint_ready")
            and muscriptor.get("config_ready")
        )
    if requirement == "game":
        game = backends.get("game", {})
        return bool(
            report.get("runtime_ready")
            and game.get("software_ready")
            and game.get("checkpoint_ready")
            and game.get("config_ready")
        )
    if requirement == "rmvpe":
        rmvpe = backends.get("rmvpe", {})
        return bool(
            report.get("runtime_ready")
            and rmvpe.get("software_ready")
            and rmvpe.get("checkpoint_ready")
        )
    if requirement == "pesto":
        pesto = backends.get("pesto", {})
        return bool(
            report.get("runtime_ready")
            and pesto.get("software_ready")
            and pesto.get("checkpoint_ready")
        )
    if requirement == "demucs":
        demucs = backends.get("demucs", {})
        return bool(
            report.get("runtime_ready")
            and demucs.get("software_ready")
            and demucs.get("checkpoint_ready")
        )
    if requirement == "all":
        return all(
            ai_requirement_ready(report, capability)
            for capability in (
                "torch",
                "muscriptor-checkpoint",
                "game",
                "rmvpe",
                "pesto",
                "demucs",
            )
        )
    return bool(report.get("runtime_ready")) and bool(
        backends.get(requirement, {}).get("software_ready")
    )


__all__ = [
    "AI_CANDIDATE_SCHEMA",
    "AI_CLEANUP_MODEL_MANIFESTS",
    "AI_MODEL_MANIFESTS",
    "AI_REQUEST_SCHEMA",
    "AI_REQUIREMENTS",
    "AI_RUNTIME_SCHEMA",
    "GAME_MODEL_FILENAMES",
    "RMVPE_MODEL_SHA256",
    "PESTO_MODEL_SHA256",
    "DEMUCS_HTDEMUCS_SHA256",
    "AIModelManifest",
    "AITranscriptionBackend",
    "AITranscriptionCandidate",
    "AITranscriptionNote",
    "AITranscriptionRequest",
    "ai_requirement_ready",
    "collect_muscriptor_checkpoint",
    "collect_game_model",
    "collect_rmvpe_model",
    "collect_pesto_model",
    "collect_demucs_model",
    "collect_ai_diagnostics",
    "collect_ai_runtime_fingerprint",
    "resolve_ai_python",
    "resolve_muscriptor_checkpoint",
    "resolve_game_model",
    "resolve_rmvpe_model",
    "resolve_pesto_model",
    "resolve_demucs_model",
]
