"""Atomic preparation of a synchronized, top-level source-stem folder.

This is the multi-part sibling of :mod:`sunofriend.source_import`.  It keeps
the one-file receipt contract for every source while publishing all originals,
canonical PCM24 WAVs, receipts and the aggregate source-project manifest in one
no-replace directory rename.

The importer records clock evidence; it never shifts, pads, stretches,
resamples or normalizes a part.  A compatible clock comparison is evidence
about recorded origins only, not proof of a musical downbeat.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from .audio_formats import (
    DEFAULT_AUDIO_IMPORT_LIMITS,
    KNOWN_AUDIO_SUFFIXES,
    AudioImportLimits,
    AudioProbe,
    decode_timeout_seconds,
    decoder_capability_report,
    file_sha256,
    probe_stable_audio,
    resolve_executable,
    validate_local_source_path,
)
from .drum_roles import (
    resolve_drum_role_policy,
    validate_drum_role_policy,
)
from .source_import import (
    SourceImportPlan,
    _build_receipt,
    _create_staging_directory,
    _destination_path,
    _ffmpeg_decode_arguments,
    _is_relative_to,
    _nearest_existing_parent,
    _open_destination_parent,
    _parent_descriptor_matches,
    _publish_directory_no_replace,
    _receipt_arguments,
    _require_parent_descriptor,
    _resolve_chord_document,
    _run_decode,
    _safe_filename,
    _safe_stem,
    _validate_chord_document,
    _validate_canonical_geometry,
    _verify_decoder_identities,
    inspect_pcm24_wav,
)
from .source_project import (
    RIGHTS_CATEGORIES,
    SourceMetadata,
    SourcePart,
    build_source_project,
    resolve_source_metadata,
    write_source_project,
)
from .source_receipt import (
    canonical_json_bytes,
    document_sha256,
    validate_source_receipt_document,
    validate_source_receipt_files,
    write_source_receipt,
)
from .source_roles import (
    canonical_source_role,
    flat_v1_repeatable_source_role_ids,
    infer_source_roles,
    prepared_source_role_ids,
)


LEGACY_SOURCE_FOLDER_IMPORT_SCHEMA = "sunofriend.source-folder-import.v1"
SOURCE_FOLDER_IMPORT_SCHEMA = "sunofriend.source-folder-import.v2"
SOURCE_FOLDER_IMPORT_PLAN_SCHEMA = "sunofriend.source-folder-import-plan.v2"
COMPOSITE_DRUM_REFINEMENT_STATUS = "not-run-midi-family-variants-only"
COMPOSITE_DRUM_CONVERSION_STATUS = "supported-review-required"
MINIMUM_SOURCE_PARTS = 2
MAXIMUM_SOURCE_PARTS = 64
_REPEATABLE_ROLES = flat_v1_repeatable_source_role_ids()
_PREPARED_ROLES = prepared_source_role_ids()
_V2_AGGREGATE_FIELDS = frozenset(
    {
        "schema",
        "project_id",
        "parts",
        "drum_role_policy",
        "shadowed_roles",
        "warnings",
        "alignment",
        "decoder",
        "limits",
        "normalised",
        "network_used",
        "folder_import_id",
    }
)
_V2_PART_FIELDS = frozenset(
    {
        "source_id",
        "role",
        "role_source",
        "shape",
        "refinement_status",
        "conversion_status",
        "original_name",
        "original_path",
        "canonical_path",
        "receipt_path",
        "retained_origin_seconds",
        "retained_origin_basis",
        "decoded_duration_seconds",
        "decoded_frames",
        "sample_rate",
    }
)


@dataclass(frozen=True)
class SourceFolderPartPlan:
    """One source part inside an aggregate folder plan."""

    import_plan: SourceImportPlan
    role_source: str
    shape: str
    refinement_status: str
    conversion_status: str
    retained_origin_seconds: float | None
    retained_origin_basis: str | None

    def to_dict(self) -> dict[str, Any]:
        plan = self.import_plan
        return {
            "source": {
                "path": str(plan.source),
                "name": plan.source.name,
                "bytes": plan.probe.source_bytes,
                "sha256": plan.source_sha256,
                "probe": plan.probe.to_dict(),
            },
            "role": plan.role,
            "role_source": self.role_source,
            "shape": self.shape,
            "refinement_status": self.refinement_status,
            "conversion_status": self.conversion_status,
            "retained_origin_seconds": self.retained_origin_seconds,
            "retained_origin_basis": self.retained_origin_basis,
            "outputs": {
                "original": plan.original_relative_path,
                "canonical": plan.canonical_relative_path,
                "receipt": plan.receipt_relative_path,
            },
        }


@dataclass(frozen=True)
class SourceFolderImportPlan:
    """Read-only plan for one all-or-nothing stem-folder import."""

    source_folder: Path
    destination: Path
    parts: tuple[SourceFolderPartPlan, ...]
    ffmpeg: Path
    ffprobe: Path
    decoder_capabilities: Mapping[str, Any]
    limits: AudioImportLimits
    metadata: SourceMetadata
    rights_category: str
    title: str
    chord_document: Path | None
    chord_sha256: str | None
    chord_bytes: int
    chord_relative_path: str | None
    aggregate_receipt_relative_path: str
    project_relative_path: str
    origin_status: str
    origin_tolerance_seconds: float
    horizon_tolerance_seconds: float
    accept_unconfirmed_origin: bool
    required_free_bytes: int
    available_free_bytes: int
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        executable = self.origin_status == "compatible" or (
            self.origin_status == "unconfirmed"
            and self.accept_unconfirmed_origin
        )
        drum_role_policy = _drum_role_policy(
            part.import_plan.role for part in self.parts
        )
        return {
            "schema": SOURCE_FOLDER_IMPORT_PLAN_SCHEMA,
            "read_only": True,
            "network_used": False,
            "source_folder": str(self.source_folder),
            "destination": str(self.destination),
            "parts": [part.to_dict() for part in self.parts],
            "drum_role_policy": drum_role_policy,
            "shadowed_roles": list(drum_role_policy["shadowed_roles"]),
            "warnings": list(self.warnings),
            "context": {
                "title": self.title,
                "metadata": self.metadata.to_dict(),
                "rights_category": self.rights_category,
                "chord_document": (
                    str(self.chord_document)
                    if self.chord_document is not None
                    else None
                ),
                "chord_sha256": self.chord_sha256,
                "chord_bytes": self.chord_bytes,
            },
            "alignment": {
                "status": self.origin_status,
                "origin_tolerance_seconds": self.origin_tolerance_seconds,
                "horizon_tolerance_seconds": self.horizon_tolerance_seconds,
                "unconfirmed_origin_accepted": self.accept_unconfirmed_origin,
                "alignment_corrected": False,
                "downbeat_confirmed": False,
                "warnings": list(self.warnings),
            },
            "outputs": {
                "aggregate_receipt": self.aggregate_receipt_relative_path,
                "source_project": self.project_relative_path,
                "chord_document": self.chord_relative_path,
            },
            "decoder": dict(self.decoder_capabilities),
            "limits": {
                **self.limits.to_dict(),
                "minimum_source_parts": MINIMUM_SOURCE_PARTS,
                "maximum_source_parts": MAXIMUM_SOURCE_PARTS,
                "required_free_bytes": self.required_free_bytes,
                "available_free_bytes": self.available_free_bytes,
            },
            "executable": executable,
            "side_effects_if_executed": {
                "filesystem": [str(self.destination)],
                "network": [],
                "installs": [],
            },
        }


@dataclass(frozen=True)
class SourceFolderImportResult:
    root: Path
    canonicals: tuple[Path, ...]
    originals: tuple[Path, ...]
    receipts: tuple[Path, ...]
    aggregate_receipt: Path
    source_project: Path
    chord_document: Path | None
    source_ids: tuple[str, ...]
    origin_status: str


def plan_source_folder_import(
    source_folder: str | Path,
    destination: str | Path,
    *,
    ffmpeg: str | Path,
    ffprobe: str | Path,
    role_map: Mapping[str, str] | None = None,
    key: str | None = None,
    bpm: float | None = None,
    tuning_hz: float | None = None,
    chord_document: str | Path | None = None,
    discover_chords: bool = True,
    rights_category: str = "declined_to_state",
    title: str | None = None,
    accept_unconfirmed_origin: bool = False,
    limits: AudioImportLimits = DEFAULT_AUDIO_IMPORT_LIMITS,
    allow_conditional_format: bool = False,
) -> SourceFolderImportPlan:
    """Inspect a top-level stem folder without creating its destination."""

    if not isinstance(accept_unconfirmed_origin, bool):
        raise TypeError("accept_unconfirmed_origin must be an explicit boolean")
    folder = _source_folder_path(source_folder)
    destination_path = _folder_destination_path(destination, folder=folder)
    sources = _discover_top_level_sources(folder)
    roles, role_sources = _resolve_roles(sources, role_map=role_map)
    _validate_role_multiplicity(roles)

    ffmpeg_path = resolve_executable(ffmpeg)
    ffprobe_path = resolve_executable(ffprobe)
    capabilities = decoder_capability_report(
        ffmpeg=ffmpeg_path,
        ffprobe=ffprobe_path,
        timeout_seconds=limits.probe_timeout_seconds,
    )
    if not capabilities["policy"]["pcm24_encoder_available"]:
        raise RuntimeError("the selected FFmpeg build does not report pcm_s24le")

    probes: list[AudioProbe] = []
    source_hashes: list[str] = []
    for source in sources:
        probe, source_hash = probe_stable_audio(
            source,
            ffprobe=ffprobe_path,
            limits=limits,
            allow_conditional=allow_conditional_format,
        )
        probes.append(probe)
        source_hashes.append(source_hash)
    if len(source_hashes) != len(set(source_hashes)):
        raise ValueError(
            "source folder contains duplicate original audio content; "
            "each immutable source identity must be unique"
        )
    _verify_capability_identities(
        capabilities, ffmpeg=ffmpeg_path, ffprobe=ffprobe_path
    )

    metadata = _resolve_folder_metadata(
        folder,
        sources,
        key=key,
        bpm=bpm,
        tuning_hz=tuning_hz,
    )
    normalized_rights = str(rights_category).strip()
    if normalized_rights not in RIGHTS_CATEGORIES:
        raise ValueError(
            "rights_category must be one of: "
            + ", ".join(sorted(RIGHTS_CATEGORIES))
        )
    chord_path = _resolve_chord_document(
        sources[0],
        explicit=chord_document,
        discover=discover_chords,
    )
    chord_hash = file_sha256(chord_path) if chord_path is not None else None
    chord_bytes = chord_path.stat().st_size if chord_path is not None else 0
    chord_relative = (
        f"INPUT/context/{_safe_filename(chord_path.name)}"
        if chord_path is not None
        else None
    )

    canonical_names = _canonical_names(
        sources, roles=roles, source_hashes=source_hashes
    )
    original_names = [_safe_filename(source.name) for source in sources]
    if len(original_names) != len(
        {name.casefold() for name in original_names}
    ):
        raise ValueError(
            "source filenames collide after safe output-name normalization"
        )
    receipt_names = [
        f"{safe_name}.source-import.json" for safe_name in original_names
    ]

    origins = [_retained_origin(probe) for probe in probes]
    lowest_sample_rate = min(probe.sample_rate for probe in probes)
    origin_tolerance = max(0.010, 2.0 / lowest_sample_rate)
    horizon_tolerance = max(0.050, 2.0 / lowest_sample_rate)
    origin_status = _classify_origins(
        [value for value, _basis in origins],
        tolerance_seconds=origin_tolerance,
    )
    warnings: list[str] = []
    durations = [probe.duration_seconds for probe in probes]
    if max(durations) - min(durations) > horizon_tolerance:
        warnings.append(
            "decoded horizons differ beyond the comparison tolerance; "
            "the importer will preserve every part unchanged"
        )
    if origin_status == "unconfirmed":
        warnings.append(
            "one or more parts have no concrete decoded-origin evidence"
        )
    elif origin_status == "conflicting":
        warnings.append(
            "concrete decoded origins conflict; execution is blocked"
        )
    drum_role_policy = _drum_role_policy(roles)
    warnings.extend(drum_role_policy["warnings"])

    required_free = (
        sum(probe.source_bytes for probe in probes)
        + 2 * sum(probe.projected_pcm24_bytes for probe in probes)
        + chord_bytes
        + limits.minimum_free_space_headroom_bytes
    )
    available_free = shutil.disk_usage(
        _nearest_existing_parent(destination_path.parent)
    ).free
    if available_free < required_free:
        raise OSError(
            "insufficient free space for deterministic source-folder import: "
            f"need {required_free} bytes, found {available_free}"
        )
    resolved_title = (
        str(title).strip()
        if title is not None and str(title).strip()
        else folder.name
    )

    parts: list[SourceFolderPartPlan] = []
    for (
        source,
        role,
        role_source,
        probe,
        source_hash,
        original_name,
        canonical_name,
        receipt_name,
        origin,
    ) in zip(
        sources,
        roles,
        role_sources,
        probes,
        source_hashes,
        original_names,
        canonical_names,
        receipt_names,
        origins,
    ):
        shape, refinement_status, conversion_status = (
            _v2_part_processing_semantics(role)
        )
        per_part_required = (
            probe.source_bytes
            + 2 * probe.projected_pcm24_bytes
            + limits.minimum_free_space_headroom_bytes
        )
        import_plan = SourceImportPlan(
            source=source,
            destination=destination_path,
            ffmpeg=ffmpeg_path,
            ffprobe=ffprobe_path,
            source_sha256=source_hash,
            probe=probe,
            decoder_capabilities=capabilities,
            limits=limits,
            role=role,
            instrument_label=None,
            metadata=metadata,
            rights_category=normalized_rights,
            title=resolved_title,
            chord_document=None,
            chord_sha256=None,
            chord_bytes=0,
            original_relative_path=f"INPUT/original/{original_name}",
            canonical_relative_path=canonical_name,
            receipt_relative_path=f"INPUT/receipts/{receipt_name}",
            project_relative_path="INPUT/source-project.json",
            chord_relative_path=None,
            decode_timeout_seconds=decode_timeout_seconds(
                probe.duration_seconds, limits=limits
            ),
            required_free_bytes=per_part_required,
            available_free_bytes=available_free,
        )
        parts.append(
            SourceFolderPartPlan(
                import_plan=import_plan,
                role_source=role_source,
                shape=shape,
                refinement_status=refinement_status,
                conversion_status=conversion_status,
                retained_origin_seconds=origin[0],
                retained_origin_basis=origin[1],
            )
        )

    return SourceFolderImportPlan(
        source_folder=folder,
        destination=destination_path,
        parts=tuple(parts),
        ffmpeg=ffmpeg_path,
        ffprobe=ffprobe_path,
        decoder_capabilities=capabilities,
        limits=limits,
        metadata=metadata,
        rights_category=normalized_rights,
        title=resolved_title,
        chord_document=chord_path,
        chord_sha256=chord_hash,
        chord_bytes=chord_bytes,
        chord_relative_path=chord_relative,
        aggregate_receipt_relative_path="INPUT/source-folder-import.json",
        project_relative_path="INPUT/source-project.json",
        origin_status=origin_status,
        origin_tolerance_seconds=origin_tolerance,
        horizon_tolerance_seconds=horizon_tolerance,
        accept_unconfirmed_origin=accept_unconfirmed_origin,
        required_free_bytes=required_free,
        available_free_bytes=available_free,
        warnings=tuple(warnings),
    )


def execute_source_folder_import(
    plan: SourceFolderImportPlan,
) -> SourceFolderImportResult:
    """Execute one folder plan as a single atomic publication."""

    if not isinstance(plan, SourceFolderImportPlan):
        raise TypeError("plan must be a SourceFolderImportPlan")
    folder = _source_folder_path(plan.source_folder)
    if folder != plan.source_folder:
        raise ValueError("source folder changed after planning")
    destination = _folder_destination_path(plan.destination, folder=folder)
    if destination != plan.destination:
        raise ValueError(
            "source-folder destination path changed after planning"
        )
    _verify_capability_identities(
        plan.decoder_capabilities,
        ffmpeg=plan.ffmpeg,
        ffprobe=plan.ffprobe,
    )
    _verify_planned_sources(plan)
    _validate_execution_plan(plan)
    _verify_planned_chord(plan)
    if plan.origin_status == "conflicting":
        raise ValueError(
            "source parts have conflicting decoded origins and cannot be "
            "imported as one synchronized project"
        )
    if (
        plan.origin_status == "unconfirmed"
        and not plan.accept_unconfirmed_origin
    ):
        raise ValueError(
            "source-part origin is unconfirmed; explicitly accept "
            "unconfirmed origin evidence before execution"
        )
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(
            f"source-folder import destination already exists: {destination}"
        )
    available_free = shutil.disk_usage(
        _nearest_existing_parent(destination.parent)
    ).free
    if available_free < plan.required_free_bytes:
        raise OSError(
            "free space fell below the amount required by the folder plan"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination = _folder_destination_path(plan.destination, folder=folder)
    parent_fd = _open_destination_parent(destination.parent)
    staging: Path | None = None
    geometries: list[Mapping[str, Any]] = []
    receipts: list[Mapping[str, Any]] = []
    source_parts: list[SourcePart] = []
    copied_chord: Path | None = None
    try:
        staging = _create_staging_directory(parent_fd, destination)
        _require_parent_descriptor(destination.parent, parent_fd)
        (staging / "INPUT" / "original").mkdir(parents=True, exist_ok=False)
        (staging / "INPUT" / "receipts").mkdir(parents=True, exist_ok=False)

        for part in plan.parts:
            item = part.import_plan
            source = validate_local_source_path(item.source, limits=plan.limits)
            if source != item.source or file_sha256(source) != item.source_sha256:
                raise ValueError(
                    f"source audio changed after planning: {item.source.name}"
                )
            _verify_decoder_identities(item)
            original = staging / item.original_relative_path
            canonical = staging / item.canonical_relative_path
            receipt_path = staging / item.receipt_relative_path
            shutil.copyfile(source, original)
            if file_sha256(original) != item.source_sha256:
                raise RuntimeError(
                    f"copied original does not match: {item.source.name}"
                )
            arguments = _ffmpeg_decode_arguments(
                original,
                canonical,
                duration_seconds=item.probe.duration_seconds,
                maximum_output_bytes=plan.limits.maximum_canonical_bytes,
            )
            _run_decode(
                plan.ffmpeg,
                arguments,
                timeout_seconds=item.decode_timeout_seconds,
            )
            _verify_decoder_identities(item)
            _require_parent_descriptor(destination.parent, parent_fd)
            geometry = {
                **inspect_pcm24_wav(canonical),
                "container_bytes": canonical.stat().st_size,
            }
            _validate_canonical_geometry(item, geometry)
            receipt = _build_receipt(
                item,
                canonical_geometry=geometry,
                canonical_sha256=file_sha256(canonical),
                decoder_arguments=_receipt_arguments(arguments),
            )
            write_source_receipt(receipt_path, receipt)
            validate_source_receipt_files(receipt.to_dict(), root=staging)
            geometries.append(geometry)
            receipts.append(receipt.to_dict())
            source_parts.append(
                SourcePart(
                    source_id=receipt.source_id,
                    role=item.role,
                    instrument_label=item.instrument_label,
                    original_name=item.source.name,
                    original_path=item.original_relative_path,
                    canonical_path=item.canonical_relative_path,
                    receipt_path=item.receipt_relative_path,
                )
            )

        if plan.chord_document is not None:
            if plan.chord_relative_path is None:
                raise ValueError("folder plan lost its chord output path")
            copied_chord = staging / plan.chord_relative_path
            copied_chord.parent.mkdir(parents=True, exist_ok=False)
            shutil.copyfile(plan.chord_document, copied_chord)
            if file_sha256(copied_chord) != plan.chord_sha256:
                raise RuntimeError(
                    "copied chord document does not match its planned hash"
                )

        chord_record = (
            {
                "name": plan.chord_document.name,
                "path": plan.chord_relative_path,
                "sha256": plan.chord_sha256,
                "bytes": copied_chord.stat().st_size,
            }
            if copied_chord is not None
            and plan.chord_document is not None
            else None
        )
        project = build_source_project(
            title=plan.title,
            metadata=plan.metadata,
            rights_category=plan.rights_category,
            sources=tuple(source_parts),
            chord_document=chord_record,
        )
        project_path = staging / plan.project_relative_path
        write_source_project(project_path, project)
        aggregate = _build_aggregate_receipt(
            plan,
            geometries=geometries,
            receipts=receipts,
            project_id=project.to_dict()["project_id"],
        )
        aggregate_path = staging / plan.aggregate_receipt_relative_path
        _write_aggregate_receipt(aggregate_path, aggregate)
        validate_source_folder_receipt_files(aggregate, root=staging)

        _verify_planned_sources(plan)
        _verify_capability_identities(
            plan.decoder_capabilities,
            ffmpeg=plan.ffmpeg,
            ffprobe=plan.ffprobe,
        )
        _verify_planned_chord(plan)
        immutable = [
            *(
                staging / part.import_plan.original_relative_path
                for part in plan.parts
            ),
            *(
                staging / part.import_plan.canonical_relative_path
                for part in plan.parts
            ),
            *(
                staging / part.import_plan.receipt_relative_path
                for part in plan.parts
            ),
            project_path,
            aggregate_path,
        ]
        if copied_chord is not None:
            immutable.append(copied_chord)
        for path in immutable:
            path.chmod(0o444)
        _publish_directory_no_replace(
            staging,
            destination,
            parent_fd=parent_fd,
        )
    except BaseException:
        if staging is not None and _parent_descriptor_matches(
            destination.parent, parent_fd
        ):
            shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        os.close(parent_fd)

    return SourceFolderImportResult(
        root=destination,
        canonicals=tuple(
            destination / part.import_plan.canonical_relative_path
            for part in plan.parts
        ),
        originals=tuple(
            destination / part.import_plan.original_relative_path
            for part in plan.parts
        ),
        receipts=tuple(
            destination / part.import_plan.receipt_relative_path
            for part in plan.parts
        ),
        aggregate_receipt=(
            destination / plan.aggregate_receipt_relative_path
        ),
        source_project=destination / plan.project_relative_path,
        chord_document=(
            destination / plan.chord_relative_path
            if plan.chord_relative_path is not None
            else None
        ),
        source_ids=tuple(
            f"sha256:{part.import_plan.source_sha256}" for part in plan.parts
        ),
        origin_status=plan.origin_status,
    )


def import_source_folder(
    source_folder: str | Path,
    destination: str | Path,
    *,
    ffmpeg: str | Path,
    ffprobe: str | Path,
    **options: Any,
) -> SourceFolderImportResult:
    """Plan and execute one deterministic source-folder import."""

    plan = plan_source_folder_import(
        source_folder,
        destination,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        **options,
    )
    return execute_source_folder_import(plan)


def _source_folder_path(source_folder: str | Path) -> Path:
    text = os.fspath(source_folder)
    if "://" in text:
        raise ValueError("remote URLs are not accepted as source folders")
    folder = Path(text).expanduser().absolute()
    if folder.is_symlink():
        raise ValueError("symbolic-link source folders are not accepted")
    if not folder.is_dir():
        raise NotADirectoryError(
            f"source folder is not an existing directory: {folder}"
        )
    return folder.resolve()


def _discover_top_level_sources(folder: Path) -> tuple[Path, ...]:
    candidates = sorted(
        (
            entry
            for entry in folder.iterdir()
            if entry.suffix.casefold() in KNOWN_AUDIO_SUFFIXES
        ),
        key=lambda path: (path.name.casefold(), path.name),
    )
    if len(candidates) < MINIMUM_SOURCE_PARTS:
        raise ValueError(
            "source folder must contain at least two supported top-level "
            "audio assets"
        )
    if len(candidates) > MAXIMUM_SOURCE_PARTS:
        raise ValueError(
            f"source folder has {len(candidates)} top-level audio assets; "
            f"maximum is {MAXIMUM_SOURCE_PARTS}"
        )
    return tuple(candidates)


def _resolve_roles(
    sources: Sequence[Path],
    *,
    role_map: Mapping[str, str] | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    mapping: dict[str, str] = {}
    source_names = {source.name for source in sources}
    if role_map is not None:
        if not isinstance(role_map, Mapping):
            raise ValueError("role_map must be an object keyed by exact filename")
        for key, value in role_map.items():
            if not isinstance(key, str) or key not in source_names:
                raise ValueError(
                    "role_map keys must exactly match a top-level audio filename"
                )
            if not isinstance(value, str):
                raise ValueError("role_map values must be role strings")
            mapping[key] = value
    roles: list[str] = []
    sources_of_roles: list[str] = []
    for source in sources:
        if source.name in mapping:
            try:
                role = _production_role(mapping[source.name])
            except ValueError as exc:
                raise ValueError(
                    "unsupported prepared source role "
                    f"{mapping[source.name]!r} for {source.name!r}; "
                    "provide one unambiguous role from: "
                    + ", ".join(sorted(_PREPARED_ROLES))
                ) from exc
            role_source = "exact-role-map"
        else:
            matches = _infer_source_roles(source)
            if len(matches) != 1:
                detail = (
                    ", ".join(sorted(matches)) if matches else "none"
                )
                raise ValueError(
                    f"ambiguous stem role for {source.name!r} "
                    f"(matched: {detail}); provide an exact "
                    "filename-to-role mapping"
                )
            role = next(iter(matches))
            role_source = "filename"
        if role not in _PREPARED_ROLES:
            raise ValueError(
                f"unsupported prepared source role {role!r} for "
                f"{source.name!r}; allowed roles: "
                + ", ".join(sorted(_PREPARED_ROLES))
            )
        roles.append(role)
        sources_of_roles.append(role_source)
    return tuple(roles), tuple(sources_of_roles)


def _production_role(role: str) -> str:
    return canonical_source_role(role)


def _infer_source_roles(source: Path) -> set[str]:
    """Delegate conservative set-valued inference to the source registry."""

    return set(infer_source_roles(source))


def _validate_role_multiplicity(roles: Sequence[str]) -> None:
    counts: dict[str, int] = {}
    for role in roles:
        counts[role] = counts.get(role, 0) + 1
    duplicates = sorted(
        role
        for role, count in counts.items()
        if count > 1 and role not in _REPEATABLE_ROLES
    )
    if duplicates:
        raise ValueError(
            "only vocals and backing_vocals may repeat; duplicate role(s): "
            + ", ".join(duplicates)
        )


def _v2_part_processing_semantics(role: str) -> tuple[str, str, str]:
    """Return the immutable v2 shape/refinement/conversion contract."""

    if role == "drums":
        return (
            "composite",
            COMPOSITE_DRUM_REFINEMENT_STATUS,
            COMPOSITE_DRUM_CONVERSION_STATUS,
        )
    return (
        "leaf",
        "not-requested",
        "vocal-specialist" if role in _REPEATABLE_ROLES else "supported",
    )


def _resolve_folder_metadata(
    folder: Path,
    sources: Sequence[Path],
    *,
    key: str | None,
    bpm: float | None,
    tuning_hz: float | None,
) -> SourceMetadata:
    folder_metadata = resolve_source_metadata(
        folder, key=key, bpm=bpm, tuning_hz=tuning_hz
    )
    per_source = [
        resolve_source_metadata(
            source,
            key=key,
            bpm=bpm,
            tuning_hz=tuning_hz,
        )
        for source in sources
    ]
    return SourceMetadata(
        key=_one_metadata_value(
            "key",
            folder_metadata.key,
            [value.key for value in per_source],
        ),
        bpm=_one_metadata_value(
            "bpm",
            folder_metadata.bpm,
            [value.bpm for value in per_source],
        ),
        tuning_hz=_one_metadata_value(
            "tuning_hz",
            folder_metadata.tuning_hz,
            [value.tuning_hz for value in per_source],
        ),
    )


def _one_metadata_value(
    label: str,
    folder_value: Any,
    values: Sequence[Any],
) -> Any:
    if folder_value is not None:
        return folder_value
    known = {value for value in values if value is not None}
    if len(known) > 1:
        raise ValueError(
            f"source filenames contain conflicting {label} metadata"
        )
    return next(iter(known)) if known else None


def _canonical_names(
    sources: Sequence[Path],
    *,
    roles: Sequence[str],
    source_hashes: Sequence[str],
) -> tuple[str, ...]:
    names: list[str] = []
    for source, role in zip(sources, roles):
        stem = _safe_stem(source.stem)
        names.append(f"{stem}-{_safe_stem(role)}-canonical.wav")
    counts: dict[str, int] = {}
    for name in names:
        key = name.casefold()
        counts[key] = counts.get(key, 0) + 1
    result = tuple(
        (
            f"{Path(name).stem}-{source_hash[:12]}.wav"
            if counts[name.casefold()] > 1
            else name
        )
        for name, source_hash in zip(names, source_hashes)
    )
    if len(result) != len({name.casefold() for name in result}):
        raise ValueError(
            "canonical output names collide after deterministic naming"
        )
    return result


def _retained_origin(probe: AudioProbe) -> tuple[float | None, str | None]:
    if probe.stream_start_time_seconds is not None:
        start = probe.stream_start_time_seconds
        basis = "stream_start_time"
    elif probe.format_start_time_seconds is not None:
        start = probe.format_start_time_seconds
        basis = "format_start_time"
    else:
        return None, None
    return (
        start + probe.first_retained_source_sample / probe.sample_rate,
        basis,
    )


def _classify_origins(
    origins: Sequence[float | None],
    *,
    tolerance_seconds: float,
) -> str:
    known = [value for value in origins if value is not None]
    if len(known) >= 2 and max(known) - min(known) > tolerance_seconds:
        return "conflicting"
    if len(known) != len(origins):
        return "unconfirmed"
    return "compatible"


def _folder_destination_path(destination: str | Path, *, folder: Path) -> Path:
    path = _destination_path(destination)
    if path == folder or _is_relative_to(path, folder):
        raise ValueError(
            "source-folder import destination must be outside the source folder"
        )
    return path


def _verify_capability_identities(
    capabilities: Mapping[str, Any],
    *,
    ffmpeg: Path,
    ffprobe: Path,
) -> None:
    for name, executable in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe)):
        expected = capabilities[name]["sha256"]
        current = resolve_executable(executable)
        if current != executable or file_sha256(current) != expected:
            raise ValueError(
                f"{name} changed after the folder plan was created"
            )


def _verify_planned_sources(plan: SourceFolderImportPlan) -> None:
    current = _discover_top_level_sources(plan.source_folder)
    planned = tuple(part.import_plan.source for part in plan.parts)
    if current != planned:
        raise ValueError(
            "top-level source audio set changed after folder planning"
    )
    for part in plan.parts:
        item = part.import_plan
        current_probe, current_hash = probe_stable_audio(
            item.source,
            ffprobe=plan.ffprobe,
            limits=plan.limits,
            allow_conditional=item.probe.decision.policy_name.startswith(
                "conditional-"
            ),
        )
        if (
            current_probe.source != item.source
            or current_hash != item.source_sha256
        ):
            raise ValueError(
                f"source audio changed after planning: {item.source.name}"
            )
        if current_probe != item.probe:
            raise ValueError(
                f"source audio probe changed after planning: {item.source.name}"
            )


def _validate_execution_plan(plan: SourceFolderImportPlan) -> None:
    """Reject modified public plan fields before any output path is joined."""

    if not (
        MINIMUM_SOURCE_PARTS <= len(plan.parts) <= MAXIMUM_SOURCE_PARTS
    ):
        raise ValueError("source-folder plan must contain two to 64 parts")
    if not isinstance(plan.accept_unconfirmed_origin, bool):
        raise TypeError("accept_unconfirmed_origin must be an explicit boolean")
    if plan.aggregate_receipt_relative_path != (
        "INPUT/source-folder-import.json"
    ):
        raise ValueError("source-folder aggregate receipt path changed")
    if plan.project_relative_path != "INPUT/source-project.json":
        raise ValueError("source-project output path changed")

    roles: list[str] = []
    sources: list[Path] = []
    hashes: list[str] = []
    probes: list[AudioProbe] = []
    for part in plan.parts:
        if not isinstance(part, SourceFolderPartPlan):
            raise TypeError("folder plan parts must be SourceFolderPartPlan")
        item = part.import_plan
        if not isinstance(item, SourceImportPlan):
            raise TypeError("folder part import plan must be SourceImportPlan")
        if item.destination != plan.destination:
            raise ValueError("folder part destination changed after planning")
        if item.ffmpeg != plan.ffmpeg or item.ffprobe != plan.ffprobe:
            raise ValueError("folder part decoder path changed after planning")
        if item.decoder_capabilities != plan.decoder_capabilities:
            raise ValueError(
                "folder part decoder capabilities changed after planning"
            )
        if item.limits != plan.limits:
            raise ValueError("folder part import limits changed after planning")
        if (
            item.metadata != plan.metadata
            or item.rights_category != plan.rights_category
            or item.title != plan.title
        ):
            raise ValueError("folder part project context changed after planning")
        if (
            item.chord_document is not None
            or item.chord_sha256 is not None
            or item.chord_bytes != 0
            or item.chord_relative_path is not None
        ):
            raise ValueError(
                "folder parts must not carry independent chord documents"
            )
        if item.project_relative_path != plan.project_relative_path:
            raise ValueError("folder part source-project path changed")
        if item.role not in _PREPARED_ROLES:
            raise ValueError("folder part role changed to an unsupported value")
        if part.role_source not in {"filename", "exact-role-map"}:
            raise ValueError("folder part role provenance changed")
        if part.role_source == "filename":
            inferred = _infer_source_roles(item.source)
            if inferred != {item.role}:
                raise ValueError("filename-derived folder part role changed")

        (
            expected_shape,
            expected_refinement,
            expected_conversion,
        ) = _v2_part_processing_semantics(item.role)
        if (
            part.shape != expected_shape
            or part.refinement_status != expected_refinement
            or part.conversion_status != expected_conversion
        ):
            raise ValueError("folder part processing status changed")
        expected_origin, expected_basis = _retained_origin(item.probe)
        if (
            part.retained_origin_seconds != expected_origin
            or part.retained_origin_basis != expected_basis
        ):
            raise ValueError("folder part origin evidence changed")

        roles.append(item.role)
        sources.append(item.source)
        hashes.append(item.source_sha256)
        probes.append(item.probe)

    _validate_role_multiplicity(roles)
    canonical_names = _canonical_names(
        sources,
        roles=roles,
        source_hashes=hashes,
    )
    original_names = [_safe_filename(source.name) for source in sources]
    for part, canonical_name, original_name in zip(
        plan.parts,
        canonical_names,
        original_names,
    ):
        item = part.import_plan
        if item.original_relative_path != (
            f"INPUT/original/{original_name}"
        ):
            raise ValueError("folder part original output path changed")
        if item.canonical_relative_path != canonical_name:
            raise ValueError("folder part canonical output path changed")
        if item.receipt_relative_path != (
            f"INPUT/receipts/{original_name}.source-import.json"
        ):
            raise ValueError("folder part receipt output path changed")

    lowest_sample_rate = min(probe.sample_rate for probe in probes)
    origin_tolerance = max(0.010, 2.0 / lowest_sample_rate)
    horizon_tolerance = max(0.050, 2.0 / lowest_sample_rate)
    origin_status = _classify_origins(
        [_retained_origin(probe)[0] for probe in probes],
        tolerance_seconds=origin_tolerance,
    )
    if (
        plan.origin_tolerance_seconds != origin_tolerance
        or plan.horizon_tolerance_seconds != horizon_tolerance
        or plan.origin_status != origin_status
    ):
        raise ValueError("folder plan alignment evidence changed after planning")

    expected_chord_relative = (
        f"INPUT/context/{_safe_filename(plan.chord_document.name)}"
        if plan.chord_document is not None
        else None
    )
    if plan.chord_relative_path != expected_chord_relative:
        raise ValueError("folder plan chord output path changed")


def _verify_planned_chord(plan: SourceFolderImportPlan) -> None:
    if plan.chord_document is None:
        return
    chord = _validate_chord_document(plan.chord_document)
    if chord != plan.chord_document or file_sha256(chord) != plan.chord_sha256:
        raise ValueError("chord document changed after folder planning")


def _build_aggregate_receipt(
    plan: SourceFolderImportPlan,
    *,
    geometries: Sequence[Mapping[str, Any]],
    receipts: Sequence[Mapping[str, Any]],
    project_id: str,
) -> dict[str, Any]:
    durations = [
        geometry["frames"] / geometry["sample_rate"]
        for geometry in geometries
    ]
    horizon_spread = max(durations) - min(durations)
    horizon_warning = horizon_spread > plan.horizon_tolerance_seconds
    origins = [
        part.retained_origin_seconds
        for part in plan.parts
        if part.retained_origin_seconds is not None
    ]
    origin_spread = max(origins) - min(origins) if origins else None
    parts = []
    for part, geometry, receipt in zip(plan.parts, geometries, receipts):
        item = part.import_plan
        parts.append(
            {
                "source_id": receipt["source_id"],
                "role": item.role,
                "role_source": part.role_source,
                "shape": part.shape,
                "refinement_status": part.refinement_status,
                "conversion_status": part.conversion_status,
                "original_name": item.source.name,
                "original_path": item.original_relative_path,
                "canonical_path": item.canonical_relative_path,
                "receipt_path": item.receipt_relative_path,
                "retained_origin_seconds": part.retained_origin_seconds,
                "retained_origin_basis": part.retained_origin_basis,
                "decoded_duration_seconds": (
                    geometry["frames"] / geometry["sample_rate"]
                ),
                "decoded_frames": geometry["frames"],
                "sample_rate": geometry["sample_rate"],
            }
        )
    warnings = list(plan.warnings)
    if horizon_warning and not any(
        "horizons differ" in warning for warning in warnings
    ):
        warnings.append(
            "decoded horizons differ beyond the comparison tolerance; "
            "every part remains unchanged"
        )
    drum_role_policy = _drum_role_policy(
        part.import_plan.role for part in plan.parts
    )
    seed: dict[str, Any] = {
        "schema": SOURCE_FOLDER_IMPORT_SCHEMA,
        "project_id": project_id,
        "parts": parts,
        "drum_role_policy": drum_role_policy,
        "shadowed_roles": list(drum_role_policy["shadowed_roles"]),
        "warnings": warnings,
        "alignment": {
            "origin_status": plan.origin_status,
            "origin_tolerance_seconds": plan.origin_tolerance_seconds,
            "known_origin_count": len(origins),
            "missing_origin_count": len(plan.parts) - len(origins),
            "concrete_origin_spread_seconds": origin_spread,
            "unconfirmed_origin_accepted": (
                plan.origin_status == "unconfirmed"
                and plan.accept_unconfirmed_origin
            ),
            "horizon_tolerance_seconds": plan.horizon_tolerance_seconds,
            "decoded_horizon_spread_seconds": horizon_spread,
            "different_horizons": horizon_warning,
            "alignment_corrected": False,
            "downbeat_confirmed": False,
            "claim": (
                "recorded-origin evidence only; no shift, padding, stretch, "
                "resampling or musical-downbeat inference was applied"
            ),
            "warnings": warnings,
        },
        "decoder": {
            "ffmpeg": dict(plan.decoder_capabilities["ffmpeg"]),
            "ffprobe": dict(plan.decoder_capabilities["ffprobe"]),
            "network_protocols": ["file"],
            "normalization_filters": [],
        },
        "limits": {
            **plan.limits.to_dict(),
            "minimum_source_parts": MINIMUM_SOURCE_PARTS,
            "maximum_source_parts": MAXIMUM_SOURCE_PARTS,
            "required_free_bytes": plan.required_free_bytes,
        },
        "normalised": False,
        "network_used": False,
    }
    return {
        **seed,
        "folder_import_id": f"sha256:{document_sha256(seed)}",
    }


def _write_aggregate_receipt(
    path: Path, document: Mapping[str, Any]
) -> None:
    if path.exists():
        raise FileExistsError(f"aggregate receipt already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    validate_source_folder_receipt_document(document)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(canonical_json_bytes(document))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def validate_source_folder_receipt_document(
    document: Mapping[str, Any],
) -> None:
    """Validate an aggregate folder receipt without reading its assets."""

    schema = document.get("schema")
    if schema not in {
        LEGACY_SOURCE_FOLDER_IMPORT_SCHEMA,
        SOURCE_FOLDER_IMPORT_SCHEMA,
    }:
        raise ValueError("unsupported source-folder import receipt schema")
    if (
        schema == SOURCE_FOLDER_IMPORT_SCHEMA
        and set(document) != _V2_AGGREGATE_FIELDS
    ):
        raise ValueError(
            "source-folder v2 aggregate fields do not match its schema"
        )
    if document.get("normalised") is not False:
        raise ValueError("source-folder import must not be normalized")
    if document.get("network_used") is not False:
        raise ValueError("source-folder import must remain local")
    seed = {
        key: value
        for key, value in document.items()
        if key != "folder_import_id"
    }
    if document.get("folder_import_id") != (
        f"sha256:{document_sha256(seed)}"
    ):
        raise ValueError("folder import ID does not match receipt content")
    parts = document.get("parts")
    if not isinstance(parts, list) or not (
        MINIMUM_SOURCE_PARTS <= len(parts) <= MAXIMUM_SOURCE_PARTS
    ):
        raise ValueError("folder receipt must contain two to 64 source parts")
    roles: list[str] = []
    identities: list[str] = []
    for index, part in enumerate(parts):
        if not isinstance(part, Mapping):
            raise ValueError(f"folder receipt part {index} must be an object")
        if (
            schema == SOURCE_FOLDER_IMPORT_SCHEMA
            and set(part) != _V2_PART_FIELDS
        ):
            raise ValueError(
                f"folder receipt v2 part {index} fields do not match "
                "its schema"
            )
        role = str(part.get("role") or "")
        if role not in _PREPARED_ROLES:
            raise ValueError(f"folder receipt part {index} has invalid role")
        roles.append(role)
        source_id = str(part.get("source_id") or "")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", source_id):
            raise ValueError(
                f"folder receipt part {index} has invalid source_id"
            )
        identities.append(source_id)
        for key in ("original_path", "canonical_path", "receipt_path"):
            _safe_receipt_path(
                part.get(key), f"folder receipt part {index} {key}"
            )
        canonical = _safe_receipt_path(
            part.get("canonical_path"),
            f"folder receipt part {index} canonical_path",
        )
        if (
            len(canonical.parts) != 1
            or canonical.suffix.casefold() != ".wav"
            or f"-{role}-" not in canonical.name.casefold()
        ):
            raise ValueError(
                "folder canonical paths must be top-level role-marked WAVs"
            )
        if schema == SOURCE_FOLDER_IMPORT_SCHEMA:
            if part.get("role_source") not in {
                "filename",
                "exact-role-map",
            }:
                raise ValueError(
                    f"folder receipt v2 part {index} has invalid role_source"
                )
            expected_semantics = _v2_part_processing_semantics(role)
            if (
                part.get("shape"),
                part.get("refinement_status"),
                part.get("conversion_status"),
            ) != expected_semantics:
                raise ValueError(
                    f"folder receipt v2 part {index} processing semantics "
                    f"do not match role {role}"
                )
        elif role == "drums":
            if part.get("conversion_status") != (
                "unsupported-pending-s2-refinement"
            ):
                raise ValueError(
                    "legacy composite drums must remain pending S2 refinement"
                )
            if part.get("shape") != "composite":
                raise ValueError("legacy drums source part must be composite")
    if len(identities) != len(set(identities)):
        raise ValueError("folder receipt source identities must be unique")
    _validate_role_multiplicity(roles)
    receipt_warnings: list[str] | None = None
    if schema == SOURCE_FOLDER_IMPORT_SCHEMA:
        policy = document.get("drum_role_policy")
        validate_drum_role_policy(policy, roles=roles)
        if document.get("shadowed_roles") != policy["shadowed_roles"]:
            raise ValueError(
                "folder receipt shadowed roles do not match its drum policy"
            )
        warning_value = document.get("warnings")
        if not isinstance(warning_value, list) or not all(
            isinstance(warning, str) for warning in warning_value
        ):
            raise ValueError("folder receipt warnings must be a list of text")
        receipt_warnings = warning_value
        if any(
            warning not in receipt_warnings
            for warning in policy["warnings"]
        ):
            raise ValueError(
                "folder receipt warnings do not include its recorded policy "
                "warnings"
            )
    alignment = document.get("alignment")
    if not isinstance(alignment, Mapping):
        raise ValueError("folder receipt alignment must be an object")
    status = alignment.get("origin_status")
    if status not in {"compatible", "unconfirmed"}:
        raise ValueError(
            "published folder receipt origin must be compatible or accepted "
            "unconfirmed"
        )
    if (
        status == "unconfirmed"
        and alignment.get("unconfirmed_origin_accepted") is not True
    ):
        raise ValueError(
            "published unconfirmed origin must record explicit acceptance"
        )
    if alignment.get("alignment_corrected") is not False:
        raise ValueError("folder import must not claim alignment correction")
    if alignment.get("downbeat_confirmed") is not False:
        raise ValueError("folder import must not claim a confirmed downbeat")
    if (
        schema == SOURCE_FOLDER_IMPORT_SCHEMA
        and alignment.get("warnings") != receipt_warnings
    ):
        raise ValueError(
            "folder receipt alignment warnings must match aggregate warnings"
        )
    decoder = document.get("decoder")
    if not isinstance(decoder, Mapping):
        raise ValueError("folder receipt decoder must be an object")
    if decoder.get("network_protocols") != ["file"]:
        raise ValueError("folder receipt decoder must use only file protocol")
    if decoder.get("normalization_filters") != []:
        raise ValueError("folder receipt must not record normalization")


def validate_source_folder_receipt_files(
    document: Mapping[str, Any],
    *,
    root: str | Path,
) -> None:
    """Recheck every per-part receipt and immutable asset under ``root``."""

    validate_source_folder_receipt_document(document)
    base = Path(root).absolute().resolve()
    for index, part in enumerate(document["parts"]):
        receipt_relative = _safe_receipt_path(
            part["receipt_path"],
            f"folder receipt part {index} receipt_path",
        )
        receipt_path = _resolve_receipt_asset(
            base, receipt_relative, label="folder per-part receipt"
        )
        if not receipt_path.is_file():
            raise ValueError("folder per-part receipt is missing or unsafe")
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("folder per-part receipt is unreadable") from exc
        if not isinstance(receipt, Mapping):
            raise ValueError("folder per-part receipt must be an object")
        validate_source_receipt_document(receipt)
        if receipt["source_id"] != part["source_id"]:
            raise ValueError("aggregate and per-part source IDs disagree")
        if receipt["original"]["path"] != part["original_path"]:
            raise ValueError("aggregate and per-part original paths disagree")
        if receipt["canonical"]["path"] != part["canonical_path"]:
            raise ValueError("aggregate and per-part canonical paths disagree")
        for key in ("original_path", "canonical_path"):
            _resolve_receipt_asset(
                base,
                _safe_receipt_path(
                    part[key], f"folder receipt part {index} {key}"
                ),
                label=f"folder per-part {key}",
            )
        validate_source_receipt_files(receipt, root=base)


def _safe_receipt_path(value: Any, label: str) -> PurePosixPath:
    text = str(value or "")
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} must be a safe relative POSIX path")
    return path


def _drum_role_policy(roles: Iterable[str]) -> dict[str, object]:
    """Use the production drum policy without changing source-role evidence."""

    return resolve_drum_role_policy(roles)


def _resolve_receipt_asset(
    base: Path,
    relative: PurePosixPath,
    *,
    label: str,
) -> Path:
    current = base
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"{label} path must not contain symbolic links")
    resolved = current.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"{label} path escapes its root") from exc
    return resolved


__all__ = [
    "COMPOSITE_DRUM_CONVERSION_STATUS",
    "COMPOSITE_DRUM_REFINEMENT_STATUS",
    "LEGACY_SOURCE_FOLDER_IMPORT_SCHEMA",
    "MAXIMUM_SOURCE_PARTS",
    "MINIMUM_SOURCE_PARTS",
    "SOURCE_FOLDER_IMPORT_SCHEMA",
    "SOURCE_FOLDER_IMPORT_PLAN_SCHEMA",
    "SourceFolderImportPlan",
    "SourceFolderImportResult",
    "SourceFolderPartPlan",
    "execute_source_folder_import",
    "import_source_folder",
    "plan_source_folder_import",
    "validate_source_folder_receipt_document",
    "validate_source_folder_receipt_files",
]
