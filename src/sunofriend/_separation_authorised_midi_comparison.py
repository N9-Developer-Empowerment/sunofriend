"""Inactive identical-settings MIDI bake-off for authorised role groups."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import shutil
import stat
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ._separation_authorised_role_mapping import (
    AUTHORISED_ROLE_MAPPING_SCHEMA,
    _document_sha256 as _mapping_document_sha256,
)
from ._separation_demucs_midi_metrics import (
    _compare_drum_hits,
    _compare_note_events,
)
from ._separation_demucs_refinement_evaluation import (
    _drum_hits,
    _evaluation_document,
    _validated_notes,
)
from .evaluate import V2_DRUM_PITCH_FAMILIES
from .midi import MidiTrack, write_midi_file
from .models import NoteEvent


AUTHORISED_MIDI_COMPARISON_SCHEMA = "sunofriend.private-authorised-midi-comparison.v1"
_REPORT_NAME = "authorised-midi-comparison.json"
_ROLES = ("bass", "drums", "other", "vocals")
_REFINE_KINDS = {"bass": "bass", "drums": "drums", "other": "synth"}
_PROGRAMS = {
    "bass": (0, 38),
    "drums": (9, 0),
    "other": (0, 81),
    "vocals": (2, 73),
}
_ONSET_TOLERANCE_SECONDS = 0.040


def _compare_authorised_role_midi(
    role_mapping_report_path: str | Path,
    *,
    out_dir: str | Path,
    bpm: float,
    tuning_hz: float,
    max_iterations: int = 30,
    refiner: Callable[..., Any] | None = None,
    renderer: Callable[..., Any] | None = None,
    evaluator: Callable[..., Any] | None = None,
    vocal_transcriber: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run the same role-specific production path for every mapped pack."""

    bpm = _positive_finite(bpm, "bpm")
    tuning_hz = _positive_finite(tuning_hz, "tuning_hz")
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int):
        raise ValueError("max_iterations must be a positive integer")
    if max_iterations <= 0:
        raise ValueError("max_iterations must be a positive integer")

    mapping_path = _regular_json(role_mapping_report_path, "role mapping report")
    mapping_root = mapping_path.parent
    mapping_sha256 = _sha256(mapping_path)
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    if mapping.get("schema") != AUTHORISED_ROLE_MAPPING_SCHEMA:
        raise ValueError("unsupported authorised role mapping schema")
    if mapping.get("document_sha256") != _mapping_document_sha256(mapping):
        raise ValueError("authorised role mapping document hash changed")
    _verify_artifacts(mapping_root, mapping.get("artifacts"))
    if mapping.get("observations", {}).get("all_proposed_roles_rank_first") is not True:
        raise ValueError("role proposals do not all rank first in audio evidence")
    if (
        mapping.get("next", {}).get("inactive_downstream_midi_comparison_allowed")
        is not True
    ):
        raise ValueError("role mapping does not allow inactive MIDI comparison")
    group_sources = _group_sources(mapping_root, mapping)

    injected = (refiner, renderer, evaluator, vocal_transcriber)
    if any(value is not None for value in injected) and not all(
        value is not None for value in injected
    ):
        raise ValueError(
            "refiner, renderer, evaluator and vocal_transcriber must all be injected together"
        )
    uses_production_components = not any(value is not None for value in injected)
    if uses_production_components:
        from .evaluate import evaluate_stem_midi
        from .loop import refine_stem
        from .render import render_midi_to_wav
        from .vocal import VocalConfig, transcribe_vocal_melody

        refine = refine_stem
        render = render_midi_to_wav
        evaluate = evaluate_stem_midi

        def transcribe_vocal(path: Path) -> Any:
            return transcribe_vocal_melody(
                path,
                config=VocalConfig(
                    role="lead",
                    tuning_hz=tuning_hz,
                    tuning_source="authorised-midi-comparison-explicit",
                    bpm=bpm,
                    tracker_mode="pyin",
                    phrase_repair=True,
                ),
            )

    else:
        assert (
            refiner is not None
            and renderer is not None
            and evaluator is not None
            and vocal_transcriber is not None
        )
        refine = refiner
        render = renderer
        evaluate = evaluator
        transcribe_vocal = vocal_transcriber

    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(
            f"Authorised MIDI comparison already exists: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.building-",
            dir=destination.parent,
        )
    )
    temporary.chmod(0o700)
    try:
        observations: dict[str, Any] = {}
        primary_notes: dict[str, dict[str, tuple[NoteEvent, ...]]] = {}
        for pack_id in sorted(group_sources):
            observations[pack_id] = {}
            primary_notes[pack_id] = {}
            for role in _ROLES:
                source_path = group_sources[pack_id][role]
                role_out = temporary / _safe_token(pack_id) / role
                role_out.mkdir(parents=True, mode=0o700)
                started = time.monotonic()
                if role == "vocals":
                    transcription = transcribe_vocal(source_path)
                    notes = _validated_notes(transcription.notes)
                    variants = {
                        name: _validated_notes(values)
                        for name, values in sorted(transcription.variants.items())
                        if name != transcription.primary_variant
                    }
                    method = {
                        "pipeline": "production_vocal_dominant_contour",
                        "primary_variant": transcription.primary_variant,
                        "diagnostics": transcription.diagnostics.to_dict(),
                    }
                    internal_history = []
                    internal_score = None
                else:
                    result = refine(
                        stem_path=source_path,
                        kind=_REFINE_KINDS[role],
                        bpm=bpm,
                        output_bpm=bpm,
                        out_dir=role_out / "REFINE-WORK",
                        max_iterations=max_iterations,
                        conversion_mode="repair",
                    )
                    notes = _validated_notes(result.notes)
                    variants = {
                        name: _validated_notes(values)
                        for name, values in sorted(result.variants.items())
                    }
                    internal_history = [
                        {
                            "iteration": int(record.iteration),
                            "score": float(record.score),
                            "note_count": int(record.note_count),
                            "detail": dict(record.detail),
                        }
                        for record in result.history
                    ]
                    internal_score = float(result.score)
                    method = {
                        "pipeline": "production_refine_stem_repair_loop",
                        "processing_kind": _REFINE_KINDS[role],
                    }

                primary = _persist_candidate(
                    root=temporary,
                    role_out=role_out,
                    label="primary",
                    source=source_path,
                    role=role,
                    notes=notes,
                    bpm=bpm,
                    render=render,
                    evaluate=evaluate,
                )
                variant_evidence = {}
                for name, variant_notes in variants.items():
                    variant_evidence[name] = _persist_candidate(
                        root=temporary,
                        role_out=role_out,
                        label=f"variant-{_safe_token(name)}",
                        source=source_path,
                        role=role,
                        notes=variant_notes,
                        bpm=bpm,
                        render=render,
                        evaluate=evaluate,
                    )
                observations[pack_id][role] = {
                    "source": _mapping_source_evidence(
                        mapping_root,
                        mapping,
                        pack_id,
                        role,
                    ),
                    "method": method,
                    "conversion_mode": "repair",
                    "primary": primary,
                    "variants": variant_evidence,
                    "internal_refinement_score": internal_score,
                    "internal_refinement_history": internal_history,
                    "elapsed_seconds": round(time.monotonic() - started, 6),
                }
                primary_notes[pack_id][role] = notes

        comparisons: dict[str, Any] = {}
        local_id = "local-htdemucs"
        if local_id not in primary_notes:
            raise ValueError("role mapping is missing local-htdemucs groups")
        for pack_id in sorted(primary_notes):
            if pack_id == local_id:
                continue
            comparisons[pack_id] = {}
            for role in _ROLES:
                local_notes = primary_notes[local_id][role]
                provider_notes = primary_notes[pack_id][role]
                if role == "drums":
                    metrics = _compare_drum_hits(
                        _drum_hits(local_notes),
                        _drum_hits(provider_notes),
                        tolerance_seconds=_ONSET_TOLERANCE_SECONDS,
                    )
                else:
                    metrics = _compare_note_events(
                        local_notes,
                        provider_notes,
                        tolerance_seconds=_ONSET_TOLERANCE_SECONDS,
                    )
                comparisons[pack_id][role] = {
                    "local_note_count": len(local_notes),
                    "provider_note_count": len(provider_notes),
                    "comparison": metrics,
                    "reference_semantics": (
                        "local HTDemucs MIDI is a relative comparison baseline, not score truth"
                    ),
                }

        for path, artifact in mapping["artifacts"].items():
            _require_hash(
                mapping_root / path,
                artifact["sha256"],
                f"mapping artifact {path}",
            )
        if _sha256(mapping_path) != mapping_sha256:
            raise ValueError("role mapping report changed during MIDI comparison")

        document: dict[str, Any] = {
            "schema": AUTHORISED_MIDI_COMPARISON_SCHEMA,
            "status": "complete_observation_not_acceptance",
            "evidence_scope": "private_development_only",
            "source_role_mapping": {
                "report_path": str(mapping_path),
                "report_sha256": mapping_sha256,
                "document_sha256": mapping["document_sha256"],
            },
            "policy": {
                "bpm": bpm,
                "tuning_hz": tuning_hz,
                "max_iterations": max_iterations,
                "conversion_mode": "repair",
                "onset_tolerance_ms": _ONSET_TOLERANCE_SECONDS * 1000.0,
                "same_role_uses_identical_settings_across_every_pack": True,
                "pitched_and_drum_roles_use_refine_stem": True,
                "vocal_role_uses_separate_production_dominant_contour": True,
                "absolute_ground_truth_claimed": False,
                "local_htdemucs_is_relative_baseline_only": True,
            },
            "components": (
                _production_component_identity()
                if uses_production_components
                else {
                    "mode": "test_injected",
                    "production_identity_captured": False,
                }
            ),
            "packs": observations,
            "comparisons_to_local_htdemucs": comparisons,
            "permissions": {
                "accepted": False,
                "production_eligible": False,
                "automatic_selection": False,
                "automatic_promotion": False,
                "source_graph_activation": False,
                "public_result": False,
                "simple_mode_available": False,
                "studio_import_available": False,
            },
            "effects": {
                "source_audio_mutated": False,
                "inactive_midi_created": True,
                "dry_proxy_auditions_created": True,
                "source_graph_mutated": False,
            },
            "limitations": [
                "Local HTDemucs MIDI is a relative baseline, not score truth.",
                "The broad vocal group is reduced to a dominant monophonic contour.",
                "The broad other group can contain several simultaneous instruments.",
                "Dry General MIDI auditions do not represent the final GarageBand instrument choice.",
                "A 15-second excerpt cannot establish full-song or cross-song acceptance.",
                "No process or provider is selected by these metrics.",
            ],
            "next": {
                "human_listening_required": True,
                "cross_song_repetition_required": True,
                "studio_import_created": False,
            },
        }
        document["artifacts"] = _artifacts(temporary)
        document["document_sha256"] = _document_sha256(document)
        report_path = temporary / _REPORT_NAME
        _write_json(report_path, document)
        _make_private_tree(temporary)
        if os.path.lexists(destination):
            raise FileExistsError(
                f"Authorised MIDI comparison output appeared during run: {destination}"
            )
        os.rename(temporary, destination)
        document["report"] = str(destination / _REPORT_NAME)
        return document
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _persist_candidate(
    *,
    root: Path,
    role_out: Path,
    label: str,
    source: Path,
    role: str,
    notes: Sequence[NoteEvent],
    bpm: float,
    render: Callable[..., Any],
    evaluate: Callable[..., Any],
) -> dict[str, Any]:
    values = _validated_notes(notes)
    notes_path = role_out / f"{label}.notes.json"
    _write_json(
        notes_path,
        {
            "schema": "sunofriend.private-authorised-midi-note-evidence.v1",
            "role": role,
            "candidate": label,
            "source_sha256": _sha256(source),
            "notes": [_note_document(note) for note in values],
        },
    )
    independent = evaluate(
        source,
        values,
        kind=("lead" if role == "vocals" else _REFINE_KINDS[role]),
        pitch_family_map=(V2_DRUM_PITCH_FAMILIES if role == "drums" else None),
    )
    result = {
        "status": "ok" if values else "no_evidence",
        "note_count": len(values),
        "notes": _artifact(root, notes_path),
        "independent_evaluation": _evaluation_document(independent),
        "midi": None,
        "render": None,
    }
    if not values:
        return result
    midi_path = role_out / f"{label}.mid"
    channel, program = _PROGRAMS[role]
    write_midi_file(
        midi_path,
        [MidiTrack(f"{role} {label}", channel, program, values)],
        bpm=bpm,
    )
    render_path = role_out / f"{label}.wav"
    render(midi_path, render_path)
    _require_nonempty_regular(render_path, f"{role} {label} render")
    result["midi"] = _artifact(root, midi_path)
    result["render"] = _artifact(root, render_path)
    return result


def _group_sources(
    root: Path, mapping: Mapping[str, Any]
) -> dict[str, dict[str, Path]]:
    raw = mapping.get("groups")
    if not isinstance(raw, Mapping) or "local-htdemucs" not in raw:
        raise ValueError("role mapping groups are missing")
    result = {}
    for pack_id, roles in raw.items():
        if not isinstance(roles, Mapping) or set(roles) != set(_ROLES):
            raise ValueError(f"{pack_id} does not contain four role groups")
        result[pack_id] = {}
        for role in _ROLES:
            result[pack_id][role] = _artifact_path(
                root,
                roles[role].get("artifact"),
                f"{pack_id} {role} group",
            )
    return result


def _mapping_source_evidence(
    root: Path,
    mapping: Mapping[str, Any],
    pack_id: str,
    role: str,
) -> dict[str, Any]:
    raw = mapping["groups"][pack_id][role]["artifact"]
    path = _artifact_path(root, raw, f"{pack_id} {role} group")
    return {
        "mapping_artifact": dict(raw),
        "verified_path": str(path),
        "sha256": _sha256(path),
    }


def _production_component_identity() -> dict[str, Any]:
    from . import evaluate, loop, render, vocal
    from .render import find_fluidsynth, find_soundfont

    modules = {}
    for name, module in (
        ("refiner", loop),
        ("evaluator", evaluate),
        ("renderer", render),
        ("vocal", vocal),
    ):
        path = Path(module.__file__).resolve(strict=True)
        modules[name] = {"path": str(path), "sha256": _sha256(path)}
    fluidsynth = Path(find_fluidsynth()).resolve(strict=True)
    soundfont = Path(find_soundfont()).expanduser().resolve(strict=True)
    return {
        "mode": "existing_production_apis",
        "production_identity_captured": True,
        "modules": modules,
        "fluidsynth": {"path": str(fluidsynth), "sha256": _sha256(fluidsynth)},
        "soundfont": {
            "path": str(soundfont),
            "sha256": _sha256(soundfont),
            "bytes": soundfont.stat().st_size,
        },
        "packages": {
            name: _package_version(name)
            for name in ("basic-pitch", "librosa", "mido", "numpy", "soundfile")
        },
    }


def _verify_artifacts(root: Path, raw: Any) -> None:
    if not isinstance(raw, Mapping) or not raw:
        raise ValueError("role mapping artifact manifest is missing")
    for relative, evidence in raw.items():
        if not isinstance(evidence, Mapping):
            raise ValueError("invalid role mapping artifact evidence")
        path = _inside(root, str(relative), "role mapping artifact")
        _require_hash(path, str(evidence.get("sha256", "")), "role mapping artifact")
        if path.stat().st_size != evidence.get("bytes"):
            raise ValueError(f"role mapping artifact byte count changed: {relative}")


def _artifact_path(root: Path, raw: Any, label: str) -> Path:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{label} evidence is missing")
    path = _inside(root, str(raw.get("path", "")), label)
    _require_hash(path, str(raw.get("sha256", "")), label)
    if path.stat().st_size != raw.get("bytes"):
        raise ValueError(f"{label} byte count changed")
    return path


def _inside(root: Path, relative: str, label: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise ValueError(f"{label} must use a relative artifact path")
    root = root.resolve(strict=True)
    path = (root / relative).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} escapes its evidence root") from error
    details = path.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise ValueError(f"{label} is not a regular non-link file")
    return path


def _regular_json(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser().absolute()
    try:
        details = path.lstat()
    except OSError as error:
        raise ValueError(f"{label} must be a non-empty regular JSON file") from error
    if (
        stat.S_ISLNK(details.st_mode)
        or not stat.S_ISREG(details.st_mode)
        or details.st_size <= 0
        or path.suffix.lower() != ".json"
    ):
        raise ValueError(f"{label} must be a non-empty regular JSON file")
    return path


def _require_nonempty_regular(path: Path, label: str) -> None:
    details = path.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise ValueError(f"{label} is not a regular non-link file")
    if details.st_size <= 0:
        raise ValueError(f"{label} is empty")


def _note_document(note: NoteEvent) -> dict[str, Any]:
    return {
        "start_seconds": note.start,
        "end_seconds": note.end,
        "pitch": note.pitch,
        "velocity": note.velocity,
    }


def _positive_finite(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{label} must be positive and finite")
    return result


def _safe_token(value: str) -> str:
    token = "".join(character if character.isalnum() else "-" for character in value)
    token = "-".join(part for part in token.split("-") if part).lower()
    if not token:
        raise ValueError("name does not contain a safe filename token")
    return token


def _artifact(root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }


def _artifacts(root: Path) -> dict[str, Any]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("MIDI comparison output contains a symbolic link")
        if path.is_file() and path.name != _REPORT_NAME:
            result[path.relative_to(root).as_posix()] = {
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
    return result


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _require_hash(path: Path, expected: str, label: str) -> None:
    actual = _sha256(path)
    if actual != expected:
        raise ValueError(f"{label} hash changed: expected {expected}, got {actual}")


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            document,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _make_private_tree(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("MIDI comparison output contains a symbolic link")
        path.chmod(0o700 if path.is_dir() else 0o600)
    root.chmod(0o700)


def _document_sha256(document: Mapping[str, Any]) -> str:
    canonical = dict(document)
    canonical.pop("document_sha256", None)
    payload = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


__all__: tuple[str, ...] = ()
