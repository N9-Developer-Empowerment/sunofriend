"""Private production-refinement parity for the synthetic Demucs canary.

The earlier downstream-MIDI observation stops after seed transcription.  This
module takes the three broad roles supported by :func:`loop.refine_stem`
through the same repair loop, MIDI renderer and independent semantic evaluator
used by the product.  Results remain private, inactive and non-promotable.

Vocals are deliberately absent: Sunofriend's vocal melody path is separate
from ``refine_stem`` and was already exercised by the seed observation.  A
report must not describe that separate path as production-refinement parity.
"""

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

from ._separation_demucs_demo_evaluation import (
    _inside,
    _require_hash,
    _validate_documents,
)
from ._separation_demucs_midi_metrics import (
    _compare_drum_hits,
    _compare_note_events,
)
from .evaluate import V2_DRUM_PITCH_FAMILIES
from .midi import MidiTrack, write_midi_file
from .models import NoteEvent
from .transcribe_drums import DrumHit


PRIVATE_DEMUCS_REFINEMENT_EVALUATION_SCHEMA = (
    "sunofriend.private-demucs-production-refinement-evaluation.v1"
)
_REPORT_NAME = "private-demucs-production-refinement-evaluation.json"
_ROLES = ("bass", "drums", "other")
_BPM = 120.0
_ONSET_TOLERANCE_SECONDS = 0.040
_PROCESSING_KINDS = {
    "bass": "bass",
    "drums": "drums",
    "other": "synth",
}
_PROGRAMS = {
    "bass": (0, 38),
    "drums": (9, 0),
    "other": (0, 81),
}


def _evaluate_private_demucs_production_refinement(
    fixture_manifest_path: str | Path,
    experiment_report_path: str | Path,
    *,
    out_dir: str | Path,
    max_iterations: int = 30,
    refiner: Callable[..., Any] | None = None,
    renderer: Callable[..., Any] | None = None,
    evaluator: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run production refinement parity without activating any result."""

    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int):
        raise ValueError("max_iterations must be a positive integer")
    if max_iterations <= 0:
        raise ValueError("max_iterations must be a positive integer")

    fixture_path = _regular_json(fixture_manifest_path, "fixture manifest")
    experiment_path = _regular_json(experiment_report_path, "experiment report")
    destination = Path(out_dir).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(
            f"Private production-refinement evaluation already exists: {destination}"
        )

    fixture_file_sha256 = _sha256(fixture_path)
    experiment_file_sha256 = _sha256(experiment_path)
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    experiment = json.loads(experiment_path.read_text(encoding="utf-8"))
    _validate_documents(fixture, experiment)
    fixture_root = fixture_path.parent
    experiment_root = experiment_path.parent

    role_paths: dict[str, dict[str, Path]] = {}
    expected_hashes: dict[Path, str] = {}
    for role in _ROLES:
        reference = _inside(
            fixture_root,
            fixture["references"][role]["path"],
            f"{role} reference",
        )
        estimate = _inside(
            experiment_root,
            experiment["estimated_stems"][role]["path"],
            f"{role} estimate",
        )
        reference_hash = fixture["references"][role]["sha256"]
        estimate_hash = experiment["estimated_stems"][role]["sha256"]
        _require_hash(reference, reference_hash, f"{role} reference")
        _require_hash(estimate, estimate_hash, f"{role} estimate")
        role_paths[role] = {"reference": reference, "estimate": estimate}
        expected_hashes[reference] = reference_hash
        expected_hashes[estimate] = estimate_hash

    uses_production_components = refiner is None and renderer is None and evaluator is None
    if any(value is not None for value in (refiner, renderer, evaluator)) and not all(
        value is not None for value in (refiner, renderer, evaluator)
    ):
        raise ValueError("refiner, renderer and evaluator must all be injected together")
    if uses_production_components:
        from .evaluate import evaluate_stem_midi
        from .loop import refine_stem
        from .render import render_midi_to_wav

        refine = refine_stem
        render = render_midi_to_wav
        evaluate = evaluate_stem_midi
    else:
        assert refiner is not None and renderer is not None and evaluator is not None
        refine = refiner
        render = renderer
        evaluate = evaluator

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.building-",
            dir=destination.parent,
        )
    )
    temporary.chmod(0o700)
    try:
        observations: dict[str, dict[str, Any]] = {}
        result_notes: dict[str, dict[str, tuple[NoteEvent, ...]]] = {}
        for role in _ROLES:
            observations[role] = {}
            result_notes[role] = {}
            for side in ("reference", "estimate"):
                source = role_paths[role][side]
                role_out = temporary / side.upper() / role
                role_out.mkdir(parents=True, mode=0o700)
                started = time.monotonic()
                result = refine(
                    stem_path=source,
                    kind=_PROCESSING_KINDS[role],
                    bpm=_BPM,
                    output_bpm=_BPM,
                    out_dir=role_out,
                    max_iterations=max_iterations,
                    conversion_mode="repair",
                )
                notes = _validated_notes(result.notes)
                midi_path = Path(result.midi_path) if result.midi_path else None
                if midi_path is None or not midi_path.is_file():
                    raise ValueError(f"{role} {side} refinement did not write MIDI")
                if not _is_inside(temporary, midi_path):
                    raise ValueError(f"{role} {side} refinement wrote MIDI outside output")

                primary_notes_path = role_out / "primary.notes.json"
                _write_json(
                    primary_notes_path,
                    {
                        "schema": "sunofriend.private-refined-note-evidence.v1",
                        "role": role,
                        "side": side,
                        "variant": "primary",
                        "source_sha256": expected_hashes[source],
                        "notes": [_note_document(note) for note in notes],
                    },
                )
                primary_render = role_out / "primary.wav"
                render(midi_path, primary_render)
                _require_regular_nonempty(primary_render, f"{role} {side} render")
                independent = evaluate(
                    source,
                    notes,
                    kind=_PROCESSING_KINDS[role],
                    pitch_family_map=(
                        V2_DRUM_PITCH_FAMILIES if role == "drums" else None
                    ),
                )

                variants: dict[str, Any] = {}
                for variant_name, raw_variant_notes in sorted(result.variants.items()):
                    variant_notes = _validated_notes(raw_variant_notes)
                    token = _safe_token(variant_name)
                    variant_midi = role_out / f"variant-{token}.mid"
                    channel, program = _PROGRAMS[role]
                    write_midi_file(
                        variant_midi,
                        [
                            MidiTrack(
                                name=f"{role} {side} {variant_name}",
                                channel=channel,
                                program=program,
                                notes=variant_notes,
                            )
                        ],
                        bpm=_BPM,
                    )
                    variant_notes_path = role_out / f"variant-{token}.notes.json"
                    _write_json(
                        variant_notes_path,
                        {
                            "schema": "sunofriend.private-refined-note-evidence.v1",
                            "role": role,
                            "side": side,
                            "variant": variant_name,
                            "source_sha256": expected_hashes[source],
                            "notes": [
                                _note_document(note) for note in variant_notes
                            ],
                        },
                    )
                    variant_render = role_out / f"variant-{token}.wav"
                    render(variant_midi, variant_render)
                    _require_regular_nonempty(
                        variant_render,
                        f"{role} {side} {variant_name} render",
                    )
                    variant_evaluation = evaluate(
                        source,
                        variant_notes,
                        kind=_PROCESSING_KINDS[role],
                        pitch_family_map=(
                            V2_DRUM_PITCH_FAMILIES if role == "drums" else None
                        ),
                    )
                    variants[variant_name] = {
                        "note_count": len(variant_notes),
                        "midi": _artifact(temporary, variant_midi),
                        "notes": _artifact(temporary, variant_notes_path),
                        "render": _artifact(temporary, variant_render),
                        "independent_evaluation": _evaluation_document(
                            variant_evaluation
                        ),
                    }

                history = [
                    {
                        "iteration": int(record.iteration),
                        "score": float(record.score),
                        "note_count": int(record.note_count),
                        "detail": dict(record.detail),
                    }
                    for record in result.history
                ]
                observations[role][side] = {
                    "source_path": str(source),
                    "source_sha256": expected_hashes[source],
                    "processing_kind": _PROCESSING_KINDS[role],
                    "conversion_mode": "repair",
                    "note_count": len(notes),
                    "refinement_score": float(result.score),
                    "iterations": history,
                    "elapsed_seconds": round(time.monotonic() - started, 6),
                    "primary_midi": _artifact(temporary, midi_path),
                    "primary_notes": _artifact(temporary, primary_notes_path),
                    "primary_render": _artifact(temporary, primary_render),
                    "independent_evaluation": _evaluation_document(independent),
                    "variants": variants,
                }
                result_notes[role][side] = notes

        for path, expected_hash in expected_hashes.items():
            _require_hash(path, expected_hash, f"{path.name} refinement input")
        if _sha256(fixture_path) != fixture_file_sha256:
            raise ValueError("fixture manifest changed during refinement evaluation")
        if _sha256(experiment_path) != experiment_file_sha256:
            raise ValueError("experiment report changed during refinement evaluation")

        role_results: dict[str, Any] = {}
        for role in _ROLES:
            reference_notes = result_notes[role]["reference"]
            estimate_notes = result_notes[role]["estimate"]
            if role == "drums":
                comparison = _compare_drum_hits(
                    _drum_hits(reference_notes),
                    _drum_hits(estimate_notes),
                    tolerance_seconds=_ONSET_TOLERANCE_SECONDS,
                )
            else:
                comparison = _compare_note_events(
                    reference_notes,
                    estimate_notes,
                    tolerance_seconds=_ONSET_TOLERANCE_SECONDS,
                )
            role_results[role] = {
                "processing_kind": _PROCESSING_KINDS[role],
                "reference": observations[role]["reference"],
                "estimate": observations[role]["estimate"],
                "clean_to_estimate_midi_comparison": comparison,
            }

        document: dict[str, Any] = {
            "schema": PRIVATE_DEMUCS_REFINEMENT_EVALUATION_SCHEMA,
            "status": "complete_observation_not_acceptance",
            "evidence_scope": "private_development_only",
            "fixture": {
                "manifest_path": str(fixture_path),
                "manifest_sha256": fixture_file_sha256,
                "document_sha256": fixture["document_sha256"],
            },
            "experiment": {
                "report_path": str(experiment_path),
                "report_sha256": experiment_file_sha256,
                "document_sha256": experiment["document_sha256"],
            },
            "policy": {
                "measurement_layer": "production_refine_stem_repair_loop",
                "full_refine_stem_pipeline_run": True,
                "independent_audio_to_midi_evaluator_run": True,
                "renderer_used_for_every_primary_and_variant": True,
                "conversion_mode": "repair",
                "bpm": _BPM,
                "max_iterations": max_iterations,
                "onset_tolerance_ms": _ONSET_TOLERANCE_SECONDS * 1000.0,
                "vocals_in_scope": False,
                "vocal_reason": (
                    "the production vocal melody pipeline is separate from refine_stem"
                ),
                "absolute_ground_truth_claimed": False,
                "clean_reference_refinement_is_relative_baseline": True,
            },
            "components": (
                _production_component_identity()
                if uses_production_components
                else {
                    "mode": "test_injected",
                    "production_identity_captured": False,
                }
            ),
            "roles": role_results,
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
                "experiment_audio_mutated": False,
                "midi_candidates_activated": False,
                "source_graph_mutated": False,
            },
            "limitations": [
                "Clean-reference refinement is a relative baseline, not score truth.",
                "The broad other role contains keys and lead, so one synth proxy cannot establish instrument ownership.",
                "Composite drums can preserve onset timing while changing inferred drum family.",
                "The rendered General MIDI proxy measures the current loop, not the timbre a user will choose in GarageBand.",
                "Vocals require a separate production-path parity increment.",
                "A synthetic eight-second fixture cannot establish cross-song separator acceptance.",
                "No human listening result, hidden-set result or production threshold is included.",
            ],
            "next": {
                "authorised_real_excerpt_evaluation_required": True,
                "separate_vocal_pipeline_parity_required": True,
                "studio_import_created": False,
            },
        }
        document["artifacts"] = _artifacts(temporary)
        document["document_sha256"] = _document_sha256(document)
        report_path = temporary / _REPORT_NAME
        _write_json(report_path, document)
        _make_private_tree(temporary)
        os.replace(temporary, destination)
        document["report"] = str(destination / _REPORT_NAME)
        return document
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _validated_notes(values: Sequence[NoteEvent]) -> tuple[NoteEvent, ...]:
    supplied = tuple(values)
    for note in supplied:
        if (
            not isinstance(note, NoteEvent)
            or not math.isfinite(note.start)
            or not math.isfinite(note.end)
            or note.start < 0
            or note.end <= note.start
            or isinstance(note.pitch, bool)
            or not isinstance(note.pitch, int)
            or not 0 <= note.pitch <= 127
            or isinstance(note.velocity, bool)
            or not isinstance(note.velocity, int)
            or not 1 <= note.velocity <= 127
        ):
            raise ValueError("refinement returned an invalid NoteEvent")
    return tuple(
        sorted(
            supplied,
            key=lambda note: (note.start, note.pitch, note.end, note.velocity),
        )
    )


def _drum_hits(notes: Sequence[NoteEvent]) -> tuple[DrumHit, ...]:
    return tuple(
        DrumHit(
            time=note.start,
            gm_pitch=note.pitch,
            velocity=note.velocity,
            strength=note.velocity / 127.0,
            family=V2_DRUM_PITCH_FAMILIES.get(note.pitch, "unknown"),
            tier="main",
            provenance="refine_stem-final-midi",
            source_time=note.start,
        )
        for note in notes
    )


def _evaluation_document(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    if not isinstance(value, Mapping):
        raise ValueError("independent evaluator returned a non-mapping result")
    return dict(value)


def _production_component_identity() -> dict[str, Any]:
    from . import evaluate, loop, render
    from .render import find_fluidsynth, find_soundfont

    modules = {}
    for name, module in (("refiner", loop), ("evaluator", evaluate), ("renderer", render)):
        path = Path(module.__file__).resolve(strict=True)
        modules[name] = {"path": str(path), "sha256": _sha256(path)}
    fluidsynth = Path(find_fluidsynth()).resolve(strict=True)
    soundfont = Path(find_soundfont()).expanduser().resolve(strict=True)
    return {
        "mode": "existing_production_apis",
        "production_identity_captured": True,
        "apis": {
            "refiner": "sunofriend.loop.refine_stem",
            "renderer": "sunofriend.render.render_midi_to_wav",
            "evaluator": "sunofriend.evaluate.evaluate_stem_midi",
        },
        "modules": modules,
        "fluidsynth": {
            "path": str(fluidsynth),
            "sha256": _sha256(fluidsynth),
        },
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


def _regular_json(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser().absolute()
    try:
        details = path.lstat()
    except OSError as error:
        raise ValueError(
            f"{label} must be a non-empty regular non-link JSON file"
        ) from error
    if (
        stat.S_ISLNK(details.st_mode)
        or not stat.S_ISREG(details.st_mode)
        or details.st_size <= 0
        or path.suffix.lower() != ".json"
    ):
        raise ValueError(f"{label} must be a non-empty regular non-link JSON file")
    return path


def _safe_token(value: str) -> str:
    token = "".join(character if character.isalnum() else "-" for character in value)
    token = "-".join(part for part in token.split("-") if part).lower()
    if not token:
        raise ValueError("variant name does not contain a safe filename token")
    return token


def _note_document(note: NoteEvent) -> dict[str, Any]:
    return {
        "start_seconds": note.start,
        "end_seconds": note.end,
        "pitch": note.pitch,
        "velocity": note.velocity,
    }


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
            raise ValueError("private refinement evaluation contains a symbolic link")
        if path.is_file() and path.name != _REPORT_NAME:
            result[path.relative_to(root).as_posix()] = {
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
    return result


def _require_regular_nonempty(path: Path, label: str) -> None:
    details = path.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise ValueError(f"{label} is not a regular non-link file")
    if details.st_size <= 0:
        raise ValueError(f"{label} is empty")


def _is_inside(root: Path, path: Path) -> bool:
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
        return True
    except (OSError, ValueError):
        return False


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


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
            raise ValueError("private refinement evaluation contains a symbolic link")
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
