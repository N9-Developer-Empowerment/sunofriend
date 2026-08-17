"""Backend-neutral planning and evidence for full-song generation."""

from __future__ import annotations

import hashlib
import math
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import urlsplit, urlunsplit

from .audio_formats import file_sha256, validate_local_source_path
from .source_project import RIGHTS_CATEGORIES
from .source_receipt import canonical_json_bytes, document_sha256
from .song_generation_providers import registered_provider_ids


SONG_GENERATION_PLAN_SCHEMA = "sunofriend.song-generation-plan.v1"
SONG_GENERATION_REQUEST_SCHEMA = "sunofriend.song-generation-request.v1"
SONG_GENERATION_RECEIPT_SCHEMA = "sunofriend.song-generation-receipt.v1"
SONG_GENERATION_BACKEND = "ace-step-api"
SONG_GENERATION_CANDIDATE_COUNT = 2

_MAXIMUM_LYRICS_BYTES = 256 * 1024
_MAXIMUM_STYLE_BYTES = 32 * 1024
_MAXIMUM_VOCAL_LANGUAGE_BYTES = 64
_SUPPORTED_OUTPUT_FORMATS = frozenset({"flac", "mp3", "opus", "aac", "wav", "wav32"})
_ENVIRONMENT_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


@dataclass(frozen=True)
class SongGenerationPlan:
    """Read-only, hash-bound plan for one two-candidate generation request."""

    reference: Path
    reference_sha256: str
    reference_bytes: int
    lyrics_path: Path
    lyrics_sha256: str
    lyrics_bytes: int
    lyrics: str
    style_description: str
    reference_strength: float
    style_strength: float
    destination: Path
    rights_category: str
    backend: str
    backend_configuration: Mapping[str, Any]
    vocal_language: str
    output_format: str
    seed: int | None
    bpm: int | None
    key: str | None
    time_signature: str | None
    duration_seconds: float | None
    candidate_count: int = SONG_GENERATION_CANDIDATE_COUNT

    def request_document(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "schema": SONG_GENERATION_REQUEST_SCHEMA,
            "task": "reference_conditioned_full_song",
            "inputs": {
                "reference": {
                    "name": self.reference.name,
                    "bytes": self.reference_bytes,
                    "sha256": self.reference_sha256,
                    "scope": "complete_song_or_excerpt",
                },
                "annotated_lyrics": {
                    "name": self.lyrics_path.name,
                    "bytes": self.lyrics_bytes,
                    "sha256": self.lyrics_sha256,
                    "text": self.lyrics,
                },
                "style_description": self.style_description,
            },
            "controls": {
                "reference_strength": self.reference_strength,
                "style_description_strength": self.style_strength,
                "candidate_count": self.candidate_count,
                "musical_metadata": {
                    "bpm": self.bpm,
                    "key": self.key,
                    "time_signature": self.time_signature,
                    "duration_seconds": self.duration_seconds,
                    "policy": "explicit_values_override_backend_inference",
                },
                "duration_policy": (
                    "explicit_seconds"
                    if self.duration_seconds is not None
                    else "model_selected_from_lyrics_style_and_arrangement"
                ),
                "seed": self.seed,
            },
            "vocals": {
                "language": self.vocal_language,
                "reference_identity_policy": "best_effort_then_abstract_traits",
                "additional_vocals_allowed": True,
            },
            "output": {
                "kind": "complete_listener_ready_song",
                "format": self.output_format,
                "stems_required": False,
                "midi_required": False,
            },
            "backend": {
                "id": self.backend,
                **dict(self.backend_configuration),
            },
            "authority": {
                "category": self.rights_category,
                "affirmation": "authorised_for_private_personal_processing",
                "execution_confirmation_required": True,
            },
        }
        document["request_sha256"] = document_sha256(document)
        return document

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SONG_GENERATION_PLAN_SCHEMA,
            "read_only": True,
            "request": self.request_document(),
            "local_inputs": {
                "reference_path": str(self.reference),
                "lyrics_path": str(self.lyrics_path),
            },
            "destination": str(self.destination),
            "execution_requires": ["--execute", "--confirm-rights"],
            "side_effects_if_executed": {
                "filesystem": [str(self.destination)],
                "network": [str(self.backend_configuration["api_base_url"])],
                "installs": [],
            },
        }


@dataclass(frozen=True)
class BackendCandidate:
    """One backend-produced candidate saved below the execution root."""

    path: Path
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class BackendRun:
    """Sanitised evidence returned by a concrete generation backend."""

    backend_id: str
    candidates: Sequence[BackendCandidate]
    request_mapping: Mapping[str, Any]
    execution_evidence: Mapping[str, Any]
    exact_reproduction_available: bool


class SongGenerationBackend(Protocol):
    """Small interchangeable boundary implemented by local, cloud or API engines."""

    backend_id: str

    def generate(self, plan: SongGenerationPlan, root: Path) -> BackendRun:
        """Generate and save candidates below ``root`` without replacing files."""


@dataclass(frozen=True)
class SongGenerationResult:
    root: Path
    request: Path
    receipt: Path
    candidates: tuple[Path, ...]
    status: str


class SongGenerationExecutionError(RuntimeError):
    """Execution failure whose durable receipt remains available for inspection."""

    def __init__(self, message: str, *, receipt: Path) -> None:
        super().__init__(message)
        self.receipt = receipt


def plan_song_generation(
    reference: str | Path,
    lyrics: str | Path,
    destination: str | Path,
    *,
    style_description: str,
    reference_strength: float,
    style_strength: float,
    rights_category: str = "authorised_private_use",
    backend: str = SONG_GENERATION_BACKEND,
    api_base_url: str = "http://127.0.0.1:8001",
    api_key_env: str = "SUNOFRIEND_MUSIC_API_TOKEN",
    model: str = "acestep-v15-base",
    vocal_language: str = "en",
    output_format: str = "wav",
    inference_steps: int = 32,
    seed: int | None = None,
    bpm: int | None = None,
    key: str | None = None,
    time_signature: str | None = None,
    duration_seconds: float | None = None,
    timeout_seconds: float = 7200.0,
    poll_seconds: float = 5.0,
) -> SongGenerationPlan:
    """Inspect a generation request without creating files or using the network."""

    reference_path = validate_local_source_path(reference)
    reference_size, reference_hash = _stable_file_identity(reference_path)
    lyrics_path, lyrics_text, lyrics_size, lyrics_hash = _read_lyrics(lyrics)
    destination_path = _fresh_destination(destination)
    style = _bounded_text(
        style_description,
        label="style description",
        maximum_bytes=_MAXIMUM_STYLE_BYTES,
    )
    reference_value = _strength(reference_strength, "reference strength")
    style_value = _strength(style_strength, "style-description strength")
    rights = str(rights_category).strip()
    if rights not in RIGHTS_CATEGORIES:
        raise ValueError(
            "rights_category must be one of: " + ", ".join(sorted(RIGHTS_CATEGORIES))
        )
    if rights != "authorised_private_use":
        raise ValueError(
            "song generation currently requires rights_category="
            "authorised_private_use"
        )
    backend_id = str(backend).strip()
    registered_backends = registered_provider_ids()
    if backend_id not in registered_backends:
        raise ValueError(
            f"unsupported song-generation backend {backend_id!r}; "
            "available for reference-conditioned generation: "
            + ", ".join(registered_backends)
            + "; run `sunofriend song-providers` for evaluated providers and "
            "their capability limits"
        )
    base_url = _api_base_url(api_base_url)
    token_environment = str(api_key_env).strip()
    if not _ENVIRONMENT_NAME.fullmatch(token_environment):
        raise ValueError("api_key_env must be an uppercase environment variable name")
    selected_model = _bounded_text(model, label="model", maximum_bytes=256)
    if "base" not in selected_model.casefold():
        raise ValueError(
            "the first ACE-Step adapter requires a Base model so the independent "
            "style-strength guidance mapping is effective"
        )
    language = _bounded_text(
        vocal_language,
        label="vocal language",
        maximum_bytes=_MAXIMUM_VOCAL_LANGUAGE_BYTES,
    )
    audio_format = str(output_format).strip().casefold()
    if audio_format not in _SUPPORTED_OUTPUT_FORMATS:
        raise ValueError(
            "output_format must be one of: "
            + ", ".join(sorted(_SUPPORTED_OUTPUT_FORMATS))
        )
    if (
        isinstance(inference_steps, bool)
        or int(inference_steps) != inference_steps
        or not 1 <= inference_steps <= 200
    ):
        raise ValueError("inference_steps must be an integer from 1 to 200")
    if seed is not None and (isinstance(seed, bool) or int(seed) != seed or seed < 0):
        raise ValueError("seed must be a non-negative integer or omitted")
    selected_bpm = _optional_integer(
        bpm,
        "bpm",
        minimum=20,
        maximum=400,
    )
    selected_key = _optional_bounded_text(key, label="key", maximum_bytes=128)
    selected_time_signature = _optional_time_signature(time_signature)
    selected_duration = (
        _positive_number(duration_seconds, "duration_seconds", maximum=600.0)
        if duration_seconds is not None
        else None
    )
    if selected_duration is not None and selected_duration < 10.0:
        raise ValueError("duration_seconds must be at least 10")
    timeout = _positive_number(timeout_seconds, "timeout_seconds", maximum=86400.0)
    polling = _positive_number(poll_seconds, "poll_seconds", maximum=60.0)
    if polling >= timeout:
        raise ValueError("poll_seconds must be less than timeout_seconds")
    guidance_scale = round(1.0 + 9.0 * style_value, 6)
    backend_configuration = {
        "api_base_url": base_url,
        "api_key_env": token_environment,
        "transport": "multipart_file_upload",
        "model": selected_model,
        "inference_steps": int(inference_steps),
        "timeout_seconds": timeout,
        "poll_seconds": polling,
        "strength_mapping": {
            "reference_strength": {
                "parameter": "audio_cover_strength",
                "value": reference_value,
            },
            "style_description_strength": {
                "parameter": "guidance_scale",
                "value": guidance_scale,
                "effective_for_model": True,
            },
        },
        "musical_metadata_mapping": {
            "bpm": "bpm",
            "key": "key_scale",
            "time_signature": "time_signature",
            "duration_seconds": "audio_duration",
            "missing_values": "ace_step_lm_inference",
        },
    }
    return SongGenerationPlan(
        reference=reference_path,
        reference_sha256=reference_hash,
        reference_bytes=reference_size,
        lyrics_path=lyrics_path,
        lyrics_sha256=lyrics_hash,
        lyrics_bytes=lyrics_size,
        lyrics=lyrics_text,
        style_description=style,
        reference_strength=reference_value,
        style_strength=style_value,
        destination=destination_path,
        rights_category=rights,
        backend=backend_id,
        backend_configuration=backend_configuration,
        vocal_language=language,
        output_format=audio_format,
        seed=int(seed) if seed is not None else None,
        bpm=selected_bpm,
        key=selected_key,
        time_signature=selected_time_signature,
        duration_seconds=selected_duration,
    )


def execute_song_generation(
    plan: SongGenerationPlan,
    *,
    confirm_rights: bool = False,
    backend: SongGenerationBackend | None = None,
) -> SongGenerationResult:
    """Execute a reviewed plan and retain a success or failure receipt."""

    if confirm_rights is not True:
        raise ValueError("song generation requires explicit rights confirmation")
    _recheck_plan_inputs(plan)
    root = _create_execution_root(plan.destination)
    request_path = root / "generation-request.json"
    receipt_path = root / "generation-receipt.json"
    request = plan.request_document()
    _write_new_json(request_path, request)
    run_id = str(uuid.uuid4())
    started_at = _utc_now()
    started = time.monotonic()
    concrete = backend or _default_backend(plan)
    try:
        run = concrete.generate(plan, root)
        if run.backend_id != plan.backend:
            raise ValueError("generation backend identity changed after planning")
        if len(run.candidates) != plan.candidate_count:
            raise ValueError(
                f"backend returned {len(run.candidates)} candidates; "
                f"expected {plan.candidate_count}"
            )
        candidate_records = _candidate_records(root, run.candidates)
        finished_at = _utc_now()
        receipt = _receipt_document(
            plan,
            request=request,
            run_id=run_id,
            status="complete",
            started_at=started_at,
            finished_at=finished_at,
            elapsed_seconds=time.monotonic() - started,
            candidates=candidate_records,
            backend_request=run.request_mapping,
            backend_evidence=run.execution_evidence,
            exact_reproduction_available=run.exact_reproduction_available,
            error=None,
        )
        _write_new_json(receipt_path, receipt)
        return SongGenerationResult(
            root=root,
            request=request_path,
            receipt=receipt_path,
            candidates=tuple(candidate.path for candidate in run.candidates),
            status="complete",
        )
    except Exception as exc:
        finished_at = _utc_now()
        failure = _receipt_document(
            plan,
            request=request,
            run_id=run_id,
            status="failed",
            started_at=started_at,
            finished_at=finished_at,
            elapsed_seconds=time.monotonic() - started,
            candidates=[],
            backend_request={},
            backend_evidence={},
            exact_reproduction_available=False,
            error={"type": type(exc).__name__, "message": str(exc)},
        )
        if not receipt_path.exists():
            _write_new_json(receipt_path, failure)
        raise SongGenerationExecutionError(str(exc), receipt=receipt_path) from exc


def _default_backend(plan: SongGenerationPlan) -> SongGenerationBackend:
    if plan.backend == SONG_GENERATION_BACKEND:
        from .song_generation_ace_step import AceStepApiBackend

        token = os.environ.get(str(plan.backend_configuration["api_key_env"])) or None
        return AceStepApiBackend(api_token=token)
    raise ValueError(f"no adapter is installed for backend: {plan.backend}")


def _receipt_document(
    plan: SongGenerationPlan,
    *,
    request: Mapping[str, Any],
    run_id: str,
    status: str,
    started_at: str,
    finished_at: str,
    elapsed_seconds: float,
    candidates: Sequence[Mapping[str, Any]],
    backend_request: Mapping[str, Any],
    backend_evidence: Mapping[str, Any],
    exact_reproduction_available: bool,
    error: Mapping[str, Any] | None,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema": SONG_GENERATION_RECEIPT_SCHEMA,
        "run_id": run_id,
        "status": status,
        "request_sha256": request["request_sha256"],
        "backend": {
            "id": plan.backend,
            "request_mapping": dict(backend_request),
            "execution_evidence": dict(backend_evidence),
        },
        "timing": {
            "started_at": started_at,
            "finished_at": finished_at,
            "elapsed_seconds": round(max(0.0, float(elapsed_seconds)), 6),
        },
        "candidates": list(candidates),
        "candidate_count": len(candidates),
        "reproduction": {
            "exact_available": bool(exact_reproduction_available),
            "requested_seed": plan.seed,
        },
        "effects": {
            "network_used": True,
            "input_audio_modified": False,
            "lyrics_modified": False,
            "candidate_selected": False,
            "stems_created": False,
            "midi_created": False,
        },
        "authority": {
            "category": plan.rights_category,
            "confirmed_for_private_personal_processing": True,
        },
        "error": dict(error) if error is not None else None,
    }
    receipt["receipt_sha256"] = document_sha256(receipt)
    return receipt


def _candidate_records(
    root: Path, candidates: Sequence[BackendCandidate]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    resolved_root = root.resolve()
    for index, candidate in enumerate(candidates, start=1):
        path = candidate.path
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"candidate {index} is missing or unsafe")
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(f"candidate {index} escapes the execution root") from exc
        size, digest = _stable_file_identity(resolved)
        if size <= 0:
            raise ValueError(f"candidate {index} is empty")
        records.append(
            {
                "index": index,
                "path": relative.as_posix(),
                "bytes": size,
                "sha256": digest,
                "metadata": dict(candidate.metadata),
            }
        )
    return records


def _recheck_plan_inputs(plan: SongGenerationPlan) -> None:
    reference = validate_local_source_path(plan.reference)
    size, digest = _stable_file_identity(reference)
    if reference != plan.reference or size != plan.reference_bytes or digest != plan.reference_sha256:
        raise ValueError("reference audio changed after planning")
    lyrics_path, text, lyrics_size, lyrics_hash = _read_lyrics(plan.lyrics_path)
    if (
        lyrics_path != plan.lyrics_path
        or text != plan.lyrics
        or lyrics_size != plan.lyrics_bytes
        or lyrics_hash != plan.lyrics_sha256
    ):
        raise ValueError("annotated lyrics changed after planning")
    if plan.candidate_count != SONG_GENERATION_CANDIDATE_COUNT:
        raise ValueError("candidate count changed after planning")
    if plan.destination.exists() or plan.destination.is_symlink():
        raise FileExistsError(
            f"song-generation destination already exists: {plan.destination}"
        )


def _read_lyrics(value: str | Path) -> tuple[Path, str, int, str]:
    path = Path(value).expanduser().absolute()
    if path.is_symlink():
        raise ValueError("annotated lyrics must not be a symbolic link")
    if not path.is_file():
        raise FileNotFoundError(f"annotated lyrics are not an existing file: {path}")
    path = path.resolve()
    before = path.stat()
    if before.st_size <= 0:
        raise ValueError("annotated lyrics are empty")
    if before.st_size > _MAXIMUM_LYRICS_BYTES:
        raise ValueError(
            f"annotated lyrics exceed the {_MAXIMUM_LYRICS_BYTES}-byte limit"
        )
    payload = path.read_bytes()
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ValueError("annotated lyrics changed while being read")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("annotated lyrics must be UTF-8 text") from exc
    if "\x00" in text or not text.strip():
        raise ValueError("annotated lyrics must contain non-NUL text")
    return path, text, len(payload), hashlib.sha256(payload).hexdigest()


def _stable_file_identity(path: Path) -> tuple[int, str]:
    before = path.stat()
    digest = file_sha256(path)
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ValueError(f"file changed while hashing: {path.name}")
    return after.st_size, digest


def _fresh_destination(value: str | Path) -> Path:
    text = os.fspath(value)
    if "://" in text:
        raise ValueError("song-generation destination must be a local path")
    path = Path(text).expanduser().absolute()
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"song-generation destination already exists: {path}")
    resolved = path.resolve(strict=False)
    if resolved == Path(resolved.anchor):
        raise ValueError("song-generation destination cannot be a filesystem root")
    return resolved


def _create_execution_root(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(mode=0o700, exist_ok=False)
    return destination.resolve()


def _write_new_json(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(canonical_json_bytes(document))


def _strength(value: float, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number from 0 to 1")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(f"{label} must be finite and between 0 and 1")
    return round(number, 6)


def _positive_number(value: float, label: str, *, maximum: float) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a positive number")
    number = float(value)
    if not math.isfinite(number) or number <= 0 or number > maximum:
        raise ValueError(f"{label} must be greater than 0 and no more than {maximum}")
    return number


def _optional_integer(
    value: int | None,
    label: str,
    *,
    minimum: int,
    maximum: int,
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or int(value) != value:
        raise ValueError(f"{label} must be a whole number or omitted")
    number = int(value)
    if not minimum <= number <= maximum:
        raise ValueError(f"{label} must be from {minimum} to {maximum}")
    return number


def _optional_bounded_text(
    value: str | None,
    *,
    label: str,
    maximum_bytes: int,
) -> str | None:
    if value is None:
        return None
    return _bounded_text(value, label=label, maximum_bytes=maximum_bytes)


def _optional_time_signature(value: str | None) -> str | None:
    selected = _optional_bounded_text(
        value,
        label="time_signature",
        maximum_bytes=16,
    )
    if selected is None:
        return None
    if not re.fullmatch(r"[1-9][0-9]?(?:/[1-9][0-9]?)?", selected):
        raise ValueError("time_signature must look like 4 or 4/4")
    return selected


def _bounded_text(value: str, *, label: str, maximum_bytes: int) -> str:
    text = str(value).strip()
    if not text or "\x00" in text:
        raise ValueError(f"{label} must contain non-NUL text")
    if len(text.encode("utf-8")) > maximum_bytes:
        raise ValueError(f"{label} exceeds the {maximum_bytes}-byte limit")
    return text


def _api_base_url(value: str) -> str:
    text = str(value).strip().rstrip("/")
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("api_base_url must be an absolute HTTP or HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("api_base_url must not contain credentials, query or fragment")
    if parsed.scheme == "http" and parsed.hostname.casefold() not in _LOOPBACK_HOSTS:
        raise ValueError("non-loopback song-generation APIs must use HTTPS")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = [
    "BackendCandidate",
    "BackendRun",
    "SONG_GENERATION_BACKEND",
    "SONG_GENERATION_CANDIDATE_COUNT",
    "SONG_GENERATION_PLAN_SCHEMA",
    "SONG_GENERATION_RECEIPT_SCHEMA",
    "SONG_GENERATION_REQUEST_SCHEMA",
    "SongGenerationBackend",
    "SongGenerationExecutionError",
    "SongGenerationPlan",
    "SongGenerationResult",
    "execute_song_generation",
    "plan_song_generation",
]
