"""Private Studio packaging for qualified six-role fine-stem evidence.

This module never loads a model, transcribes MIDI, or selects a source.  It
copies the exact reviewed PCM24 artifacts into a self-contained private
package and keeps the six-role audio set separate from the grouped-other MIDI
control so a Studio launch cannot accidentally double-count both forms.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any, Mapping

from .separation_fine_stem_canary_audio import file_sha256
from .separation_fine_stem_integration_outcome import (
    validate_fine_stem_integration_outcome,
)
from .separation_fine_stem_integration_plan import PERSISTED_ROLES
from .separation_fine_stem_integration_report import (
    validate_fine_stem_integration_report,
)
from .separation_fine_stem_integration_review import (
    validate_integration_review,
)
from .separation_fine_stem_midi_canary import (
    validate_fine_stem_midi_canary,
)
from .separation_fine_stem_midi_outcome import (
    validate_fine_stem_midi_outcome,
)
from .separation_fine_stem_synth_provider_midi_outcome import (
    validate_fine_stem_synth_provider_midi_outcome,
)
from .separation_fine_stem_studio_package_contract import (
    GUIDE_NAME,
    MIDI_CONTROL_CATALOG_NAME,
    PACKAGE_DIRECTORY_NAME,
    PACKAGE_MANIFEST_NAME,
    PACKAGE_SCHEMA,
    PACKAGE_STATUS,
    SIX_ROLE_CATALOG_NAME,
    cross_validate_evidence,
    midi_control_catalog,
    package_guide,
    package_records,
    six_role_catalog,
    studio_package_document_sha256,
    validate_private_studio_package_document,
)
from .workbench_catalog import build_workbench_catalog


_CASE_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,127}\Z")
_MAX_JSON_BYTES = 16 * 1024 * 1024


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    opened = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(opened)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"{label} is not a regular file")
        if metadata.st_size > _MAX_JSON_BYTES:
            raise ValueError(f"{label} exceeds the JSON size limit")
        chunks = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(opened, min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError(f"{label} changed while reading")
            chunks.append(chunk)
            remaining -= len(chunk)
    finally:
        os.close(opened)
    value = json.loads(b"".join(chunks).decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def _safe_relative_path(root: Path, relative: Any, *, label: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"{label} relative path differs")
    candidate_relative = Path(relative)
    if candidate_relative.is_absolute() or ".." in candidate_relative.parts:
        raise ValueError(f"{label} escapes its evidence root")
    candidate = (root / candidate_relative).resolve(strict=True)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} escapes its evidence root") from error
    metadata = candidate.lstat()
    if not stat.S_ISREG(metadata.st_mode) or candidate.is_symlink():
        raise ValueError(f"{label} is not a regular non-linked file")
    return candidate


def _verify_identity(root: Path, identity: Mapping[str, Any], *, label: str) -> Path:
    path = _safe_relative_path(root, identity.get("relative_path"), label=label)
    if path.stat().st_size != identity.get("bytes"):
        raise ValueError(f"{label} byte count differs")
    if file_sha256(path) != identity.get("sha256"):
        raise ValueError(f"{label} SHA-256 differs")
    return path


def _artifact(path: Path, root: Path) -> dict[str, Any]:
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def _copy_verified(
    source_root: Path,
    identity: Mapping[str, Any],
    destination: Path,
    *,
    package_root: Path,
    label: str,
) -> dict[str, Any]:
    source = _verify_identity(source_root, identity, label=label)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.parent.chmod(0o700)
    digest = hashlib.sha256()
    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        source_metadata = os.fstat(source_fd)
        if (
            not stat.S_ISREG(source_metadata.st_mode)
            or source_metadata.st_size != identity["bytes"]
        ):
            raise ValueError(f"{label} changed before copy")
        destination_fd = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        try:
            remaining = source_metadata.st_size
            while remaining:
                chunk = os.read(source_fd, min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError(f"{label} changed during copy")
                digest.update(chunk)
                view = memoryview(chunk)
                while view:
                    written = os.write(destination_fd, view)
                    view = view[written:]
                remaining -= len(chunk)
            os.fsync(destination_fd)
        finally:
            os.close(destination_fd)
    finally:
        os.close(source_fd)
    destination.chmod(0o600)
    if digest.hexdigest() != identity["sha256"]:
        raise ValueError(f"{label} changed during copy")
    return {
        **_artifact(destination, package_root),
        "sample_rate_hz": identity["sample_rate_hz"],
        "channels": identity["channels"],
        "frames": identity["frames"],
        "subtype": identity["subtype"],
    }


def _write_json(path: Path, value: Mapping[str, Any], root: Path) -> dict[str, Any]:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return _artifact(path, root)


def build_private_studio_package(
    integration_root: str | Path,
    integration_outcome_path: str | Path,
    midi_canary_root: str | Path,
    midi_outcome_path: str | Path,
    provider_midi_outcome_path: str | Path,
    *,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Build and atomically publish one exact private Studio package."""

    integration = Path(integration_root).expanduser().resolve(strict=True)
    midi_root = Path(midi_canary_root).expanduser().resolve(strict=True)
    destination = Path(out_dir).expanduser().absolute()
    if destination.name != PACKAGE_DIRECTORY_NAME:
        raise ValueError(
            f"private Studio output must be named {PACKAGE_DIRECTORY_NAME}"
        )
    if os.path.lexists(destination):
        raise FileExistsError(f"fresh private Studio output required: {destination}")

    report = validate_fine_stem_integration_report(
        _read_json(
            integration / "TECHNICAL/INTEGRATION-REPORT.json",
            label="six-role integration report",
        )
    )
    review = validate_integration_review(
        _read_json(
            integration / "REVIEW/SIX-ROLE-LISTENING.json",
            label="six-role integration review",
        ),
        report,
    )
    outcome = validate_fine_stem_integration_outcome(
        _read_json(Path(integration_outcome_path), label="six-role outcome")
    )
    midi_report = validate_fine_stem_midi_canary(
        _read_json(
            midi_root / "TECHNICAL/MIDI-CANARY-REPORT.json",
            label="downstream MIDI canary",
        )
    )
    midi_outcome = validate_fine_stem_midi_outcome(
        _read_json(Path(midi_outcome_path), label="downstream MIDI outcome")
    )
    provider_midi_outcome = validate_fine_stem_synth_provider_midi_outcome(
        _read_json(
            Path(provider_midi_outcome_path),
            label="provider synth MIDI outcome",
        )
    )
    cross_validate_evidence(
        report=report,
        review=review,
        outcome=outcome,
        midi_report=midi_report,
        midi_outcome=midi_outcome,
        provider_midi_outcome=provider_midi_outcome,
    )

    review_by_id = {case["case_id"]: case for case in review["cases"]}
    midi_by_id = {case["case_id"]: case for case in midi_report["cases"]}
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{PACKAGE_DIRECTORY_NAME}.building-",
            dir=destination.parent,
        )
    )
    staging.chmod(0o700)
    packaged_cases: list[dict[str, Any]] = []
    published = False
    try:
        for case in report["cases"]:
            case_id = str(case["case_id"])
            if not _CASE_ID.fullmatch(case_id):
                raise ValueError("private Studio case ID is not path-safe")
            case_root = staging / "CASES" / case_id
            case_root.mkdir(parents=True, mode=0o700)
            stem_artifacts = {}
            for role in PERSISTED_ROLES:
                stem_artifacts[role] = _copy_verified(
                    integration,
                    case["artifacts"][role],
                    case_root / "STEMS" / f"{role}.wav",
                    package_root=staging,
                    label=f"{case_id} {role}",
                )
            reference = _copy_verified(
                integration,
                case["artifacts"]["reference"],
                case_root / "REFERENCE" / "reference.wav",
                package_root=staging,
                label=f"{case_id} reference",
            )
            reconstruction = _copy_verified(
                integration,
                case["artifacts"]["reconstruction_check"],
                case_root / "DIAGNOSTIC" / "reconstruction-check.wav",
                package_root=staging,
                label=f"{case_id} reconstruction check",
            )
            midi_case = midi_by_id[case_id]
            grouped_other = _copy_verified(
                midi_root,
                midi_case["grouped_other_control"]["artifact"],
                case_root / "MIDI-CONTROL" / "grouped-other.wav",
                package_root=staging,
                label=f"{case_id} grouped-other MIDI control",
            )
            six_role_catalog_artifact = _write_json(
                case_root / SIX_ROLE_CATALOG_NAME,
                six_role_catalog(),
                staging,
            )
            midi_control_catalog_artifact = _write_json(
                case_root / MIDI_CONTROL_CATALOG_NAME,
                midi_control_catalog(),
                staging,
            )
            listened = review_by_id[case_id]
            target_role = str(case["reused_primary_role"])
            packaged_cases.append(
                {
                    "case_id": case_id,
                    "track_id": case["track_id"],
                    "title": case["title"],
                    "window_seconds": list(case["window_seconds"]),
                    "confirmed_present_target_role": target_role,
                    "review": {
                        "catastrophic_result": listened["catastrophic_result"],
                        "target_usefulness": listened["usefulness"][target_role],
                        "target_issues": dict(listened["issues"][target_role]),
                        "private_notes_copied": False,
                    },
                    "six_role_stems": stem_artifacts,
                    "reference": reference,
                    "reconstruction_diagnostic": reconstruction,
                    "grouped_other_midi_control": grouped_other,
                    "catalogs": {
                        "six_role_audio": six_role_catalog_artifact,
                        "grouped_other_midi_control": midi_control_catalog_artifact,
                    },
                    "studio": {
                        "project_root": f"CASES/{case_id}",
                        "six_role_catalog": f"CASES/{case_id}/{SIX_ROLE_CATALOG_NAME}",
                        "midi_control_catalog": f"CASES/{case_id}/{MIDI_CONTROL_CATALOG_NAME}",
                        "initial_source_selection": None,
                        "initial_midi_selection": None,
                    },
                }
            )

        guide_path = staging / GUIDE_NAME
        guide_path.write_text(
            package_guide([case["case_id"] for case in packaged_cases]),
            encoding="utf-8",
        )
        guide_path.chmod(0o600)
        document: dict[str, Any] = {
            "schema": PACKAGE_SCHEMA,
            "document_sha256": "",
            "status": PACKAGE_STATUS,
            "evidence_scope": "private_development_only",
            "bindings": {
                "integration_report_sha256": report["report_sha256"],
                "integration_review_document_sha256": review["document_sha256"],
                "integration_outcome_document_sha256": outcome["document_sha256"],
                "downstream_midi_canary_document_sha256": midi_report[
                    "document_sha256"
                ],
                "downstream_midi_outcome_document_sha256": midi_outcome[
                    "document_sha256"
                ],
                "provider_synth_midi_outcome_document_sha256": provider_midi_outcome[
                    "document_sha256"
                ],
            },
            "profile_ids": dict(report["profiles"]),
            "release_tier": "private_studio_challenger",
            "case_count": len(packaged_cases),
            "cases": packaged_cases,
            "guide": _artifact(guide_path, staging),
            "policy": {
                "audio_admission": "qualified_private_studio_audition",
                "midi_control": "grouped_other_retained_no_automatic_choice",
                "catalogs_are_mutually_exclusive": True,
                "six_role_reconstruction_roles": list(PERSISTED_ROLES),
                "grouped_other_definition": (
                    "sample-exact PCM24 sum of synth, guitar and residual other"
                ),
                "reconstruction_accounting_is_separation_accuracy": False,
                "automatic_winner_selection": False,
            },
            "known_limitations": [
                "the package contains eight reviewed 15-second cases, not full songs",
                "three confirmed-present synth cases retained some missing content",
                "grouped other can contain pitched non-synth and non-guitar material",
                "checkpoint terms and resource evidence do not permit a public six-role claim",
                "the package contains no MIDI candidates and makes no source choice",
            ],
            "boundaries": {
                "private_studio_audio_only": True,
                "public_activation": False,
                "source_selection": False,
                "midi_selection": False,
                "midi_created": False,
                "separator_model_loaded": False,
                "transcriber_run": False,
                "network_access": False,
                "hosting": False,
                "redistribution": False,
                "audio_upload": False,
            },
            "effects": {
                "private_audio_files_read": len(packaged_cases) * 9,
                "private_audio_files_copied": len(packaged_cases) * 9,
                "studio_catalogs_written": len(packaged_cases) * 2,
                "guide_files_written": 1,
                "checkpoint_loads": 0,
                "model_constructions": 0,
                "separator_inference_attempts": 0,
                "midi_transcription_attempts": 0,
                "midi_files_written": 0,
                "network_attempts": 0,
                "source_selections": 0,
                "public_activations": 0,
            },
        }
        document["document_sha256"] = studio_package_document_sha256(document)
        validate_private_studio_package_document(document)
        manifest = staging / PACKAGE_MANIFEST_NAME
        _write_json(manifest, document, staging)
        for directory, subdirectories, files in os.walk(staging):
            Path(directory).chmod(0o700)
            for name in subdirectories:
                (Path(directory) / name).chmod(0o700)
            for name in files:
                (Path(directory) / name).chmod(0o600)
        _verify_private_studio_package_contents(staging, document)
        os.rename(staging, destination)
        published = True
        verify_private_studio_package(destination)
        return copy.deepcopy(document)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        if published:
            shutil.rmtree(destination, ignore_errors=True)
        raise


def _verify_private_studio_package_contents(
    package: Path,
    document: Mapping[str, Any],
) -> None:
    for record in package_records(document):
        _verify_identity(package, record, label="private Studio package artifact")
    for case in document["cases"]:
        case_root = package / case["studio"]["project_root"]
        six_role = build_workbench_catalog(
            case_root,
            catalog_path=package / case["studio"]["six_role_catalog"],
        )
        midi_control = build_workbench_catalog(
            case_root,
            catalog_path=package / case["studio"]["midi_control_catalog"],
        )
        if (
            len(six_role["stems"]) != 6
            or any(stem["candidate_count"] != 0 for stem in six_role["stems"])
            or len(midi_control["stems"]) != 1
            or midi_control["stems"][0]["candidate_count"] != 0
        ):
            raise ValueError("private Studio catalog admission differs")


def verify_private_studio_package(root: str | Path) -> dict[str, Any]:
    """Re-hash a completed package and validate both Studio catalogs per case."""

    package = Path(root).expanduser().resolve(strict=True)
    if package.name != PACKAGE_DIRECTORY_NAME or not package.is_dir():
        raise ValueError("private Studio package root differs")
    document = validate_private_studio_package_document(
        _read_json(package / PACKAGE_MANIFEST_NAME, label="private Studio manifest")
    )
    _verify_private_studio_package_contents(package, document)
    return document


__all__ = [
    "GUIDE_NAME",
    "MIDI_CONTROL_CATALOG_NAME",
    "PACKAGE_DIRECTORY_NAME",
    "PACKAGE_MANIFEST_NAME",
    "PACKAGE_SCHEMA",
    "PACKAGE_STATUS",
    "SIX_ROLE_CATALOG_NAME",
    "build_private_studio_package",
    "studio_package_document_sha256",
    "validate_private_studio_package_document",
    "verify_private_studio_package",
]
