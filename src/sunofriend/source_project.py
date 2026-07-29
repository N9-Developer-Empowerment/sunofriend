"""Minimal source-project manifest used before legacy stem discovery."""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from .audio_formats import file_sha256
from .metadata import infer_project_metadata
from .source_receipt import canonical_json_bytes, document_sha256


SOURCE_PROJECT_SCHEMA = "sunofriend.source-project.v1"
SOURCE_PROJECT_RELATIVE_PATH = PurePosixPath("INPUT/source-project.json")
RIGHTS_CATEGORIES = frozenset(
    {
        "owned",
        "licensed",
        "authorised_private_use",
        "statutory_exception",
        "unknown",
        "declined_to_state",
    }
)

_ROLE_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("backing_vocals", ("backing vocals", "backing vocal", "bv", "bvox")),
    ("other_kit", ("other kit", "other drums", "percussion", "perc")),
    ("cymbals", ("cymbals", "cymbal", "crash", "ride")),
    ("vocals", ("vocals", "vocal", "voice")),
    ("drums", ("drums", "drum kit", "drumkit")),
    ("strings", ("strings", "string")),
    ("guitars", ("guitars", "guitar")),
    ("piano", ("piano",)),
    ("keys", ("keys", "keyboard")),
    ("synth", ("synth", "synthesizer")),
    ("bass", ("bass",)),
    ("kick", ("kick",)),
    ("snare", ("snare",)),
    ("hats", ("hi hat", "hi hats", "hihat", "hihats", "hat", "hats")),
    ("toms", ("toms", "tom")),
    ("lead", ("lead",)),
    ("wind", ("wind", "woodwind")),
    ("other", ("other", "residual")),
)


@dataclass(frozen=True)
class SourceMetadata:
    key: str | None
    bpm: float | None
    tuning_hz: float | None

    def __post_init__(self) -> None:
        for label, value in (("bpm", self.bpm), ("tuning_hz", self.tuning_hz)):
            if value is not None and (
                not math.isfinite(float(value)) or float(value) <= 0
            ):
                raise ValueError(f"{label} must be finite and positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "bpm": self.bpm,
            "tuning_hz": self.tuning_hz,
        }


@dataclass(frozen=True)
class SourcePart:
    source_id: str
    role: str
    original_name: str
    original_path: str
    canonical_path: str
    receipt_path: str
    instrument_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "role": self.role,
            "instrument_label": self.instrument_label,
            "original_name": self.original_name,
            "original_path": self.original_path,
            "canonical_path": self.canonical_path,
            "receipt_path": self.receipt_path,
            "origin": "original",
            "active": True,
        }


@dataclass(frozen=True)
class SourceProject:
    title: str
    metadata: SourceMetadata
    rights_category: str
    sources: tuple[SourcePart, ...]
    chord_document: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        seed = {
            "schema": SOURCE_PROJECT_SCHEMA,
            "title": self.title,
            "metadata": self.metadata.to_dict(),
            "rights": {
                "category": self.rights_category,
                "user_declaration_only": True,
                "verified_by_sunofriend": False,
            },
            "chord_document": (
                dict(self.chord_document)
                if self.chord_document is not None
                else None
            ),
            "sources": [source.to_dict() for source in self.sources],
        }
        project_id = f"sha256:{document_sha256(seed)}"
        return {**seed, "project_id": project_id}


@dataclass(frozen=True)
class PreparedProjectContext:
    """Strict, path-verified metadata declared by a prepared source project."""

    manifest_path: Path
    metadata: SourceMetadata
    chord_document: Path | None


def resolve_source_metadata(
    source: str | Path,
    *,
    key: str | None = None,
    bpm: float | None = None,
    tuning_hz: float | None = None,
) -> SourceMetadata:
    """Combine explicit values with existing filename/folder conventions."""

    path = Path(source)
    inferred_file = infer_project_metadata(path)
    inferred_folder = infer_project_metadata(path.parent)
    return SourceMetadata(
        key=(
            str(key).strip()
            if key is not None and str(key).strip()
            else inferred_file.key or inferred_folder.key
        ),
        bpm=(
            float(bpm)
            if bpm is not None
            else inferred_file.bpm
            if inferred_file.bpm is not None
            else inferred_folder.bpm
        ),
        tuning_hz=(
            float(tuning_hz)
            if tuning_hz is not None
            else inferred_file.tuning_hz
            if inferred_file.tuning_hz is not None
            else inferred_folder.tuning_hz
        ),
    )


def infer_source_role(value: str | Path) -> str:
    """Infer one conservative role while retaining ``mix`` as a safe fallback."""

    normalized = re.sub(
        r"[^a-z0-9]+", " ", Path(value).stem.casefold()
    ).strip()
    padded = f" {normalized} "
    for role, aliases in _ROLE_ALIASES:
        if any(f" {alias} " in padded for alias in aliases):
            return role
    return "mix"


def normalize_source_role(value: str | None, *, fallback_from: str | Path) -> str:
    role = (
        re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")
        if value is not None
        else infer_source_role(fallback_from)
    )
    if not role:
        raise ValueError("source role must not be empty")
    return role


def build_source_project(
    *,
    title: str,
    metadata: SourceMetadata,
    rights_category: str,
    source: SourcePart | None = None,
    sources: Sequence[SourcePart] = (),
    chord_document: Mapping[str, Any] | None = None,
) -> SourceProject:
    rights = str(rights_category).strip()
    if rights not in RIGHTS_CATEGORIES:
        raise ValueError(
            "rights_category must be one of: "
            + ", ".join(sorted(RIGHTS_CATEGORIES))
        )
    parts = tuple(sources)
    if source is not None:
        parts = (source, *parts)
    if not parts:
        raise ValueError("source-project must contain at least one source")
    identities = [part.source_id for part in parts]
    if len(identities) != len(set(identities)):
        raise ValueError("source-project source IDs must be unique")
    project = SourceProject(
        title=str(title).strip() or Path(parts[0].original_name).stem,
        metadata=metadata,
        rights_category=rights,
        sources=parts,
        chord_document=chord_document,
    )
    validate_source_project_document(project.to_dict())
    return project


def write_source_project(path: str | Path, project: SourceProject) -> Path:
    """Atomically create a minimal manifest without replacing existing state."""

    target = Path(path)
    if target.exists():
        raise FileExistsError(f"source-project manifest already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    document = project.to_dict()
    validate_source_project_document(document)
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(canonical_json_bytes(document))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def validate_source_project_document(document: Mapping[str, Any]) -> None:
    if document.get("schema") != SOURCE_PROJECT_SCHEMA:
        raise ValueError("unsupported source-project schema")
    project_id = str(document.get("project_id") or "")
    seed = {key: value for key, value in document.items() if key != "project_id"}
    if project_id != f"sha256:{document_sha256(seed)}":
        raise ValueError("source-project project_id does not match its content")
    rights = document.get("rights")
    if not isinstance(rights, Mapping):
        raise ValueError("source-project rights must be an object")
    if rights.get("category") not in RIGHTS_CATEGORIES:
        raise ValueError("source-project rights category is invalid")
    if rights.get("user_declaration_only") is not True:
        raise ValueError("rights must be labelled as a user declaration")
    if rights.get("verified_by_sunofriend") is not False:
        raise ValueError("Sunofriend must not claim to verify source rights")
    metadata = document.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError("source-project metadata must be an object")
    SourceMetadata(
        key=metadata.get("key"),
        bpm=metadata.get("bpm"),
        tuning_hz=metadata.get("tuning_hz"),
    )
    sources = document.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("source-project must contain at least one source")
    source_ids: list[str] = []
    for index, source in enumerate(sources):
        if not isinstance(source, Mapping):
            raise ValueError("source-project source must be an object")
        if source.get("origin") != "original" or source.get("active") is not True:
            raise ValueError(
                "minimal source-project sources must be active and original"
            )
        if not str(source.get("role") or "").strip():
            raise ValueError("source-project source role must not be empty")
        source_id = str(source.get("source_id") or "")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", source_id):
            raise ValueError("source-project source_id must be a SHA-256 identity")
        source_ids.append(source_id)
        for key in ("original_path", "canonical_path", "receipt_path"):
            _safe_relative_path(source.get(key), f"sources[{index}].{key}")
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("source-project source IDs must be unique")
    chord = document.get("chord_document")
    if chord is not None:
        if not isinstance(chord, Mapping):
            raise ValueError("chord_document must be an object or null")
        _safe_relative_path(chord.get("path"), "chord_document.path")
        sha256 = str(chord.get("sha256") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ValueError("chord_document.sha256 must be a lowercase SHA-256")


def discover_chord_document(source: str | Path) -> Path | None:
    """Return one unambiguous adjacent chord document, otherwise fail safely."""

    parent = Path(source).parent
    candidates = sorted(
        path
        for path in parent.iterdir()
        if path.is_file()
        and not path.is_symlink()
        and path.suffix.casefold() in {".pdf", ".txt"}
        and "chord" in path.stem.casefold()
    )
    if len(candidates) > 1:
        raise ValueError(
            "several adjacent chord documents were found; choose one explicitly"
        )
    return candidates[0] if candidates else None


def load_source_project(path: str | Path) -> dict[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError("source-project file must contain a JSON object")
    validate_source_project_document(document)
    return dict(document)


def load_prepared_project_context(
    project_root: str | Path,
) -> PreparedProjectContext | None:
    """Load authoritative prepared-project metadata, or return ``None``.

    The absence of ``INPUT/source-project.json`` deliberately means that
    callers should retain their legacy filename/folder inference unchanged.
    Once that reserved manifest path exists, however, its schema and metadata
    are authoritative, and declared chord path/size/hash problems fail closed.
    This lightweight context lookup does not attest source audio; immutable
    source/canonical evidence remains the responsibility of import receipts.
    """

    root = Path(project_root).expanduser().absolute()
    manifest = root.joinpath(*SOURCE_PROJECT_RELATIVE_PATH.parts)
    if manifest.is_symlink():
        raise ValueError("source-project manifest must not be a symbolic link")
    if not manifest.exists():
        return None
    if not manifest.is_file():
        raise ValueError("source-project manifest must be a regular file")
    _reject_relative_symlinks(
        root,
        SOURCE_PROJECT_RELATIVE_PATH,
        label="source-project manifest",
    )

    document = load_source_project(manifest)
    metadata_value = document["metadata"]
    if not isinstance(metadata_value, Mapping):
        # Kept explicit even though schema validation already enforces this:
        # this function is the boundary where prepared metadata becomes
        # authoritative application state.
        raise ValueError("source-project metadata must be an object")
    missing_metadata = {
        field
        for field in ("key", "bpm", "tuning_hz")
        if field not in metadata_value
    }
    if missing_metadata:
        raise ValueError(
            "source-project metadata is missing required field(s): "
            + ", ".join(sorted(missing_metadata))
        )
    metadata = SourceMetadata(
        key=_strict_optional_key(metadata_value.get("key")),
        bpm=_strict_optional_positive_number(
            metadata_value.get("bpm"),
            label="source-project metadata.bpm",
        ),
        tuning_hz=_strict_optional_positive_number(
            metadata_value.get("tuning_hz"),
            label="source-project metadata.tuning_hz",
        ),
    )

    if "chord_document" not in document:
        raise ValueError("source-project chord_document field is missing")
    chord_value = document["chord_document"]
    chord_document = (
        _resolve_declared_chord_document(root, chord_value)
        if chord_value is not None
        else None
    )
    return PreparedProjectContext(
        manifest_path=manifest.resolve(),
        metadata=metadata,
        chord_document=chord_document,
    )


def _strict_optional_key(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            "source-project metadata.key must be a non-empty string or null"
        )
    return value


def _strict_optional_positive_number(value: Any, *, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite positive number or null")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be a finite positive number or null")
    return number


def _resolve_declared_chord_document(
    root: Path,
    value: Any,
) -> Path:
    if not isinstance(value, Mapping):
        raise ValueError("chord_document must be an object or null")
    name = value.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("chord_document.name must be a non-empty string")
    relative = _safe_relative_path(value.get("path"), "chord_document.path")
    _reject_relative_symlinks(root, relative, label="chord document")
    path = root.joinpath(*relative.parts)
    resolved_root = root.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("chord document path escapes the project root") from exc
    if not resolved.is_file() or resolved.is_symlink():
        raise ValueError("declared chord document is missing or unsafe")
    if resolved.suffix.casefold() not in {".pdf", ".txt"}:
        raise ValueError("declared chord document must be PDF or plain text")

    expected_bytes = value.get("bytes")
    if (
        isinstance(expected_bytes, bool)
        or not isinstance(expected_bytes, int)
        or expected_bytes < 0
    ):
        raise ValueError("chord_document.bytes must be a non-negative integer")
    if resolved.stat().st_size != expected_bytes:
        raise ValueError("declared chord document byte size does not match")
    expected_sha256 = str(value.get("sha256") or "")
    if file_sha256(resolved) != expected_sha256:
        raise ValueError("declared chord document hash does not match")
    return resolved


def _reject_relative_symlinks(
    root: Path,
    relative: PurePosixPath,
    *,
    label: str,
) -> None:
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"{label} path must not contain symbolic links")


def _safe_relative_path(value: Any, label: str) -> PurePosixPath:
    path = PurePosixPath(str(value or ""))
    if not str(value or "") or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} must be a safe relative POSIX path")
    return path


__all__ = [
    "RIGHTS_CATEGORIES",
    "SOURCE_PROJECT_SCHEMA",
    "SOURCE_PROJECT_RELATIVE_PATH",
    "PreparedProjectContext",
    "SourceMetadata",
    "SourcePart",
    "SourceProject",
    "build_source_project",
    "discover_chord_document",
    "infer_source_role",
    "load_prepared_project_context",
    "load_source_project",
    "normalize_source_role",
    "resolve_source_metadata",
    "validate_source_project_document",
    "write_source_project",
]
